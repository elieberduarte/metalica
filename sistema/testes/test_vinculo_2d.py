# -*- coding: utf-8 -*-
"""GER-04 (sistema/testes/REGRAS.md; usuário, 26/10): o projeto modelado em 3D a partir de DXF tem o DXF importado no 2D e
o 3D vinculado a ele (projeto.planta_modelo, o que a tela dividida lê) — nucleo3d/vinculo_2d.py.

E a trava da versão: nas obras do desenvolvimento, a conferência não acha mais apontamentos que na fotografia aceita
(Projeto/bateria/vinculo-2d.json). Aceitar depois de conferir: python testes/test_vinculo_2d.py --aceitar"""
import json
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from nucleo3d import vinculo_2d as V  # noqa: E402

FOTOGRAFIA = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "Projeto", "bateria", "vinculo-2d.json")
DESL = (-37000.0, -4600.0)        # o modelo = o desenho + DESL


def _projeto(pasta, projeto, linhas_desenho, barras):
    os.makedirs(os.path.join(pasta, "desenhos-2d"), exist_ok=True)
    with open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8") as f:
        json.dump(projeto, f, ensure_ascii=False)
    des = {"nome": "desenho", "entidades": [{"id": "l%d" % k, "tipo": "linha", "camada": "metalica", "atributos": {"origem": "dxf"},
                                              "a": a, "b": b} for k, (a, b) in enumerate(linhas_desenho)]}
    with open(os.path.join(pasta, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8") as f:
        json.dump(des, f)
    ents = []
    for k, (a, b, extra) in enumerate(barras):
        e = {"id": "b%d" % k, "tipo": "barra", "camada": "Terças", "inicio": [a[0], a[1], 6000.0], "fim": [b[0], b[1], 6000.0]}
        if extra:
            e["atributos"] = {"origem": extra}
        ents.append(e)
    with open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump({"entidades": ents}, f)


def _galpao(pasta, planta_modelo=None, fonte=None, deslize=(0.0, 0.0), projeto_extra=None):
    """as 6 terças do DXF (linhas a cada 1,5 m) e as 6 barras do 3D em cima delas, levadas por DESL (+ deslize)"""
    linhas = [([0.0, 1500.0 * i], [12000.0, 1500.0 * i]) for i in range(6)]
    barras = [((a[0] + DESL[0] + deslize[0], a[1] + DESL[1] + deslize[1]), (b[0] + DESL[0] + deslize[0], b[1] + DESL[1] + deslize[1]),
               {"fonte_2d": fonte} if fonte else None) for a, b in linhas]
    projeto = {"nome": "Galpão", "dxf_recebido": "GALPAO.dxf", **(projeto_extra or {})}
    if planta_modelo is not None:
        projeto["planta_modelo"] = planta_modelo
    _projeto(pasta, projeto, linhas, barras)


def test_vinculado_e_em_cima_do_desenho_passa(tmp_path):
    _galpao(str(tmp_path), {"desenho": "desenho", "deslocamento": list(DESL)})
    r = V.conferir(str(tmp_path))
    assert r["aplica"] and r["barras"] == 6 and r["fora"] == 0 and r["apontamentos"] == []


def test_sem_vinculo_aponta(tmp_path):
    """o Hangar, os galpões da Hora Certa, o Moinho… (26/10): montados do DXF por script, sem o planta_modelo"""
    _galpao(str(tmp_path))
    r = V.conferir(str(tmp_path))
    assert r["aplica"] and len(r["apontamentos"]) == 1 and "não está ligado" in r["apontamentos"][0]["texto"]


def test_deslocamento_errado_aponta_que_o_3d_nao_cai_no_desenho(tmp_path):
    """o vínculo gravado, mas com o 3D 750 mm fora do lugar: as barras ficam no meio do vão entre as linhas do DXF"""
    _galpao(str(tmp_path), {"desenho": "desenho", "deslocamento": list(DESL)}, deslize=(0.0, 750.0))
    r = V.conferir(str(tmp_path))
    assert r["fora"] == 6 and any("não cai em cima do desenho" in a["texto"] for a in r["apontamentos"])


def test_planta_da_peca_que_o_vinculo_nao_conhece_aponta(tmp_path):
    _galpao(str(tmp_path), {"desenho": "desenho", "deslocamento": list(DESL), "fontes": {"tercas": [0.0, 0.0]}}, fonte="mezanino")
    r = V.conferir(str(tmp_path))
    assert any('planta "mezanino"' in a["texto"] for a in r["apontamentos"])


def test_planta_girada_no_desenho(tmp_path):
    """26/10, Galpão Novo da Hora Certa: a cobertura G1 desenha os eixos A–Q no sentido de x, girada −90° em relação ao 3D.
    As terças deitadas no desenho ficam em pé no modelo: modelo = gira(desenho, −90°) + deslocamento da planta"""
    pasta = str(tmp_path)
    linhas = [([0.0, 1500.0 * i], [12000.0, 1500.0 * i]) for i in range(6)]
    t = (5000.0, 80000.0)
    gira = lambda p: (p[1] + t[0], -p[0] + t[1])                  # noqa: E731
    barras = [(gira(a), gira(b), {"fonte_2d": "G1"}) for a, b in linhas]
    pm = {"desenho": "desenho", "deslocamento": [0.0, 0.0], "fontes": {"G1": {"deslocamento": list(t), "giro": -90}}}
    _projeto(pasta, {"nome": "Galpão", "dxf_recebido": "GALPAO.dxf", "planta_modelo": pm}, linhas, barras)
    r = V.conferir(pasta)
    assert r["barras"] == 6 and r["fora"] == 0 and r["apontamentos"] == []
    # o giro trocado (+90°) ou sem o giro, o mesmo deslocamento põe o 3D fora do desenho — as barras estão longe do centro do
    # giro, então o sentido conta (o mesmo do dividida.js: aoDesenho)
    pm["fontes"]["G1"] = {"deslocamento": list(t), "giro": 90}
    _projeto(pasta, {"nome": "Galpão", "dxf_recebido": "GALPAO.dxf", "planta_modelo": pm}, linhas, barras)
    assert V.conferir(pasta)["fora"] == 6
    pm["fontes"]["G1"] = list(t)
    _projeto(pasta, {"nome": "Galpão", "dxf_recebido": "GALPAO.dxf", "planta_modelo": pm}, linhas, barras)
    assert any("não cai em cima do desenho" in a["texto"] for a in V.conferir(pasta)["apontamentos"])
    # e o gravar guarda o giro
    V.gravar(pasta, "desenho", (0.0, 0.0), fontes={"G1": {"deslocamento": list(t), "giro": -90}})
    assert V.conferir(pasta)["apontamentos"] == []


def _com_chave(pasta, quantas):
    """as primeiras `quantas` barras com a chave do traço do desenho de baixo delas (atributos.origem_2d = o id do traço)"""
    caminho = os.path.join(pasta, "modelo.json")
    with open(caminho, encoding="utf-8") as f:
        m = json.load(f)
    for k, e in enumerate(m["entidades"][:quantas]):
        e.setdefault("atributos", {})["origem_2d"] = "l%d" % k
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(m, f)


def test_ligado_pela_chave_do_tracado_passa(tmp_path):
    """o outro jeito de ligar (o Hangar, o Ortobio, o CD Bom Dia, as Docas — 26/10): sem planta_modelo, cada peça com a chave
    do traço da Montagem ou da planta de lançamento; a primeira conferência (a6cc391) acusava essas 4 obras por engano"""
    _galpao(str(tmp_path))
    _com_chave(str(tmp_path), 6)
    r = V.conferir(str(tmp_path))
    assert r["apontamentos"] == [] and r["por_chave"] == 6


def test_ligado_pela_chave_so_pela_metade_aponta(tmp_path):
    _galpao(str(tmp_path))
    _com_chave(str(tmp_path), 3)
    r = V.conferir(str(tmp_path))
    assert len(r["apontamentos"]) == 1 and "só 3 de 6 barras" in r["apontamentos"][0]["texto"]


def test_projeto_so_do_ifc_nao_se_aplica(tmp_path):
    _projeto(str(tmp_path), {"nome": "Sooro", "tipo": "ifc", "origem_ifc": "x.ifc"}, [], [])
    assert V.conferir(str(tmp_path)) == {"aplica": False, "barras": 0, "fora": 0, "apontamentos": []}


def test_gravar_pelo_script_da_obra(tmp_path):
    """o script de obra grava o vínculo pelo código comum (como a montagem pela planta) e a conferência passa"""
    _galpao(str(tmp_path))
    V.gravar(str(tmp_path), "desenho", DESL, fontes={"planta": (0, 0)})
    with open(os.path.join(str(tmp_path), "projeto.json"), encoding="utf-8") as f:
        assert json.load(f)["planta_modelo"]["deslocamento"] == list(DESL)
    assert V.conferir(str(tmp_path))["apontamentos"] == []
    with pytest.raises(FileNotFoundError):
        V.gravar(str(tmp_path), "nao-existe", DESL)


# ---- a trava da versão -------------------------------------------------------------------------------------------------

def _raiz_dev():
    """a pasta de obras do desenvolvimento (Documentos/Metálica, também com o OneDrive)"""
    base = os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica")
    if not os.path.isdir(base):
        base = os.path.join(os.path.expanduser("~"), "Documents", "Metálica")
    return base


def _contagem(raiz):
    return {r["obra"]: len(r["apontamentos"]) for r in V.conferir_obras(raiz) if r["aplica"]}


def test_obras_do_desenvolvimento_nao_pioram():
    if not os.path.isfile(FOTOGRAFIA):
        pytest.skip("sem a fotografia aceita (Projeto/bateria/vinculo-2d.json)")
    raiz = _raiz_dev()
    if not os.path.isdir(raiz):
        pytest.skip("sem a pasta de obras do desenvolvimento")
    with open(FOTOGRAFIA, encoding="utf-8") as f:
        aceita = json.load(f)["obras"]
    agora = _contagem(raiz)
    piores = {o: (aceita.get(o, 0), n) for o, n in agora.items() if n > aceita.get(o, 0)}
    assert not piores, ("GER-04: obra modelada do DXF sem o vínculo 2D × 3D, ou com mais apontamentos que na fotografia "
                        "aceita (aceita → agora): %s. Gravar o vínculo (nucleo3d/vinculo_2d.gravar) ou, se estiver certo, "
                        "python testes/test_vinculo_2d.py --aceitar" % piores)


if __name__ == "__main__" and "--aceitar" in sys.argv:
    res = _contagem(_raiz_dev())
    os.makedirs(os.path.dirname(FOTOGRAFIA), exist_ok=True)
    with open(FOTOGRAFIA, "w", encoding="utf-8") as f:
        json.dump({"regra": "GER-04", "obras": res}, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("aceita:", FOTOGRAFIA, {o: n for o, n in res.items() if n})
