# -*- coding: utf-8 -*-
"""O botão Cancelar da barra segue o servidor também depois de apertado (D03 do usuario-desastrado, causa 3, 13/11: a tela
ficava "cancelando…" até o fim e depois abria o resultado, sem dizer que a tarefa já estava gravando quando o cancelamento
foi pedido). progresso.estadoDoCancelar e progresso.recadoDoFim."""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))

SCRIPT = r"""
const { estadoDoCancelar: e, recadoDoFim: r } = await import(%s);
console.log(JSON.stringify({
  sem_pedido: e({ etapa: 'desenhando', cancelando: false }, 'Cancelar'),
  pedido_de_outra_tela: e({ etapa: 'desenhando', cancelando: true }, 'Cancelar'),
  ja_cancelando: e({ etapa: 'desenhando', cancelando: true }, 'cancelando…'),
  entrou_na_gravacao: e({ etapa: 'gravando os desenhos', cancelando: true, gravando: true }, 'cancelando…'),
  ja_terminando: e({ etapa: 'gravando os desenhos', cancelando: true, gravando: true }, 'terminando de gravar…'),
  nada: e(null, 'Cancelar'),
  recado_terminando: r('terminando de gravar…', { gravando: true }),
  recado_cancelando_gravava: r('cancelando…', { gravando: true }),
  recado_cancelou: r('cancelando…', { gravando: false }),
  recado_sem_pedido: r('Cancelar', { gravando: true }),
}));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node no computador")
def test_o_botao_vira_terminando_de_gravar_e_o_fim_avisa():
    pasta = tempfile.mkdtemp(prefix="cancelar_d03_")
    try:
        script = os.path.join(pasta, "t.mjs")
        url = "file:///" + os.path.join(WEB, "progresso.js").replace("\\", "/")
        open(script, "w", encoding="utf-8").write(SCRIPT % json.dumps(url))
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    assert a["sem_pedido"] is None and a["nada"] is None, a
    assert a["pedido_de_outra_tela"] == "cancelando", a          # o pedido de outra tela também aparece aqui
    assert a["ja_cancelando"] is None, a
    assert a["entrou_na_gravacao"] == "terminando", a            # a causa 3: antes ficava "cancelando…"
    assert a["ja_terminando"] is None, a
    assert "terminou" in a["recado_terminando"] and "terminou" in a["recado_cancelando_gravava"], a
    assert a["recado_cancelou"] == "" and a["recado_sem_pedido"] == "", a
