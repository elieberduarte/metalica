# -*- coding: utf-8 -*-
"""A cobertura retrátil aberta e retraída no celular (saida/pacote_celular.py, 19/10).

O celular só lê — ver aberta/retraída no computador grava o modelo, e lá não pode. Então o pacote leva as duas
situações: o modelo3d.mcel de sempre na situação gravada e a outra montada numa cópia do modelo, com as fichas dela
(as tesouras mudam de lugar). O modelo do projeto não é tocado. O modelo é o pequeno de test_cobertura_movel."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d import cobertura_movel as CM                       # noqa: E402
from saida.pacote_celular import gerar_pacote, ler_cabecalho_arquivo   # noqa: E402
from test_cobertura_movel import PAR, _modelo                     # noqa: E402


def _projeto(tmp_path, situacao="aberta", cobertura=True):
    proj = tmp_path / "obra"
    proj.mkdir(exist_ok=True)
    doc = _modelo()
    if cobertura:
        CM.aplicar(doc, PAR, situacao)
    (proj / "modelo.json").write_text(json.dumps(doc.dict()), encoding="utf-8")
    (proj / "projeto.json").write_text(json.dumps({"nome": "Cobertura", "analise_parametros": PAR}), encoding="utf-8")
    return proj




def test_o_pacote_leva_as_duas_situacoes_sem_mexer_no_modelo(tmp_path):
    proj = _projeto(tmp_path, "aberta")
    antes = (proj / "modelo.json").read_text(encoding="utf-8")
    dest = tmp_path / "pacote"
    m = gerar_pacote(str(proj), str(dest), "obra")
    cm = m.get("cobertura_movel")
    assert cm and cm["atual"] == "aberta"
    assert cm["situacoes"]["aberta"] == {"modelo": "modelo3d.mcel", "pecas": "pecas.json"}
    assert cm["situacoes"]["retraida"] == {"modelo": "modelo3d-retraida.mcel", "pecas": "pecas-retraida.json"}
    nomes = {a["nome"] for a in m["arquivos"]}
    assert {"modelo3d.mcel", "modelo3d-retraida.mcel", "pecas.json", "pecas-retraida.json"} <= nomes   # vão para a obra
    a = ler_cabecalho_arquivo(str(dest / "modelo3d.mcel"))["numeros"]["pecas"]
    r = ler_cabecalho_arquivo(str(dest / "modelo3d-retraida.mcel"))["numeros"]["pecas"]
    assert a == r                                                    # as mesmas peças, só a posição muda
    assert (dest / "modelo3d.mcel").read_bytes() != (dest / "modelo3d-retraida.mcel").read_bytes()
    assert (dest / "pecas.json").read_text(encoding="utf-8") != (dest / "pecas-retraida.json").read_text(encoding="utf-8")
    assert (proj / "modelo.json").read_text(encoding="utf-8") == antes   # o celular não grava no projeto


def test_a_situacao_trocada_no_pc_chega_ao_celular(tmp_path):
    proj = _projeto(tmp_path, "aberta")
    dest = tmp_path / "pacote"
    gerar_pacote(str(proj), str(dest), "obra")
    time.sleep(0.05)
    _projeto(tmp_path, "retraida")                                   # o PC gravou o modelo retraído
    os.utime(proj / "modelo.json", (time.time() + 5, time.time() + 5))
    m = gerar_pacote(str(proj), str(dest), "obra")
    cm = m["cobertura_movel"]
    assert cm["atual"] == "retraida" and cm["situacoes"]["aberta"]["modelo"] == "modelo3d-aberta.mcel"
    assert (dest / "modelo3d-aberta.mcel").exists() and not (dest / "modelo3d-retraida.mcel").exists()


def test_sem_cobertura_retratil_nada_a_mais(tmp_path):
    proj = _projeto(tmp_path, cobertura=False)
    dest = tmp_path / "pacote"
    dest.mkdir()
    (dest / "modelo3d-retraida.mcel").write_bytes(b"velho")          # de quando o projeto tinha cobertura
    m = gerar_pacote(str(proj), str(dest), "obra")
    assert "cobertura_movel" not in m
    assert not (dest / "modelo3d-retraida.mcel").exists()


def test_pacote_de_antes_e_refeito_quando_o_formato_muda(tmp_path, monkeypatch):
    """O usuário não viu aberta/retraída no celular (19/10): o pacote da Kaefer era de antes e, sem o projeto mudar,
    não era refeito. O formato do pacote entra na assinatura dele — subiu, o pacote velho volta à fila."""
    from celular import servidor as S
    from saida import pacote_celular as P
    dados = tmp_path / "dados"
    dados.mkdir()
    _projeto(dados, "aberta")
    c = S.Celular(str(dados), str(tmp_path / "trabalho"), porta=0, host="127.0.0.1")
    antes = c._assinatura("obra")
    assert antes and antes == c._assinatura("obra")
    monkeypatch.setattr(P, "FORMATO_PACOTE", P.FORMATO_PACOTE + 1)
    assert c._assinatura("obra") != antes
