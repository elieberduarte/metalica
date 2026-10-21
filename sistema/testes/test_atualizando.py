# -*- coding: utf-8 -*-
"""O bloqueio "atualizando" (21/10/2026, pedido do usuário na remontagem do Posto V2 por fora do programa): enquanto uma
tarefa demorada atualiza o projeto — deste processo ou de outro (um script, outra janela) — o projeto tem atualizando.json,
a lista o mostra com a etapa, a barra das telas mostra a etapa de outro processo, e todo POST de fora é recusado.
A marca expira (gravada há mais de 15 min) e some quando o processo que a gravou morreu."""
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                                    # noqa: E402
from nucleo.base import ErroDeDados                               # noqa: E402
from projetos import Projetos, ATUALIZANDO, _pid_vivo             # noqa: E402
import app                                                        # noqa: E402


def _outro_processo():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _regravar(cam, **campos):
    with open(cam, encoding="utf-8") as f:
        d = json.load(f)
    d.update(campos)
    with open(cam, "w", encoding="utf-8") as f:
        json.dump(d, f)


def test_pid_vivo():
    assert _pid_vivo(os.getpid())
    p = _outro_processo()
    try:
        assert _pid_vivo(p.pid)
    finally:
        p.kill(); p.wait()
    time.sleep(0.3)
    assert not _pid_vivo(p.pid)


def test_marca_le_expira_e_some_com_o_processo_morto():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        s = g.criar("Obra")["slug"]
        assert g.atualizando(s) is None and g.resumo(s)["atualizando"] is None
        g.marcar_atualizando(s, "montando as treliças…", 0.4, quem="eu")
        a = g.atualizando(s)
        assert a and a["etapa"] == "montando as treliças…" and a["fracao"] == 0.4 and a["este_processo"] and a["mesma_maquina"]
        assert g.resumo(s)["atualizando"]["etapa"] == "montando as treliças…"
        cam = os.path.join(raiz, s, ATUALIZANDO)
        # gravado há mais de 15 min: não vale mais (a tarefa que travou não prende o projeto para sempre)
        _regravar(cam, quando=time.time() - 2000)
        assert g.atualizando(s) is None
        # de outro processo vivo: vale, e não é este processo
        p = _outro_processo()
        try:
            _regravar(cam, quando=time.time(), pid=p.pid)
            a = g.atualizando(s)
            assert a and not a["este_processo"] and a["pid"] == p.pid
        finally:
            p.kill(); p.wait()
        time.sleep(0.3)
        assert g.atualizando(s) is None                           # o processo morreu: a marca não vale
        g.marcar_atualizando(s, "x")
        g.desmarcar_atualizando(s)
        assert not os.path.exists(cam)
        g.desmarcar_atualizando(s)                                # de novo: não reclama


def test_servidor_grava_no_progresso_recusa_post_de_fora_e_mostra_a_etapa_do_outro():
    with tempfile.TemporaryDirectory() as raiz:
        antes = app.PROJETOS
        app.PROJETOS = raiz
        try:
            g = app._gerente()
            s = g.criar("Obra")["slug"]
            cam = os.path.join(raiz, s, ATUALIZANDO)
            # a tarefa deste processo: a 1ª etapa (menos de 1 s) não grava; a fração grava; o fim apaga
            app._progresso(s, "começando…")
            assert not os.path.exists(cam)
            app._progresso(s, "desenhando (2 de 4)", fracao=0.5)
            assert os.path.exists(cam) and g.atualizando(s)["este_processo"]
            assert app.progresso_do_projeto(s)["fracao"] == 0.5          # a deste processo, como sempre
            # a tarefa deste processo não recusa os próprios POST
            app._fim_progresso(s)
            assert not os.path.exists(cam)
            t = app._tarefa_padrao("/api/projetos/%s/renomear" % s)
            assert t and not os.path.exists(cam)
            app._fim_tarefa_padrao(t)
            # outro processo atualizando: o POST é recusado, a barra mostra a etapa dele, a lista o diz
            p = _outro_processo()
            try:
                g.marcar_atualizando(s, "montando as treliças…", 0.3, quem="script")
                _regravar(cam, pid=p.pid)
                with pytest.raises(ErroDeDados) as e:
                    app._tarefa_padrao("/api/projetos/%s/renomear" % s)
                assert "sendo atualizado" in str(e.value) and "montando as treliças" in str(e.value)
                pr = app.progresso_do_projeto(s)
                assert pr["etapa"] == "montando as treliças…" and pr["externo"] and pr["fracao"] == 0.3 and pr["quem"] == "script"
                assert g.resumo(s)["atualizando"]["etapa"] == "montando as treliças…"
            finally:
                p.kill(); p.wait()
            time.sleep(0.3)
            # o outro processo morreu: tudo volta ao normal sem apagar nada à mão
            t = app._tarefa_padrao("/api/projetos/%s/renomear" % s)
            assert t
            app._fim_tarefa_padrao(t)
            assert app.progresso_do_projeto(s) == {"etapa": "", "ha_s": 0}
            # um projeto que não existe: o progresso e a tarefa não quebram
            assert app.progresso_do_projeto("nao-existe") == {"etapa": "", "ha_s": 0}
            app._progresso("nao-existe", "x", fracao=0.1)
            app._fim_progresso("nao-existe")
        finally:
            app.PROJETOS = antes
            app._fim_progresso(s)
