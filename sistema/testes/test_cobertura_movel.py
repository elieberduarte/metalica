"""A cobertura retrátil no 3D (nucleo3d/cobertura_movel.py): as tesouras e a sanfona da análise, aberta e retraída.

Modelo pequeno no formato da planta (de_planta_estrutura._trelica): 4 pilares, 2 vigas-trilho ao longo de Y e uma tesoura
lançada sobre elas, de X = 0 a X = 10 m.
"""
import collections

import pytest

from nucleo3d import analise_estrutural as AE
from nucleo3d import cobertura_movel as CM
from nucleo3d.modelo import Barra, Documento

PAR = {"movel_n": 5, "movel_comprimento_aberta": 10.0, "movel_comprimento_retraida": 2.0, "movel_peso_total_kg": 500.0,
       "vento": False, "telha": 0.0}


def _modelo():
    doc = Documento(nome="teste")
    for x in (0.0, 10000.0):
        for y in (0.0, 10000.0):
            doc.add(Barra(inicio=(x, y, 0.0), fim=(x, y, 5000.0), perfil="W 250×32,7", papel="pilar", atributos={"elemento": "pilar"}))
        doc.add(Barra(inicio=(x, 0.0, 5000.0), fim=(x, 10000.0, 5000.0), perfil="W 150×22,5", papel="viga", atributos={"elemento": "viga"}))
    y = 2000.0
    base = {"elemento": "trelica", "marca": "T1", "origem_2d": "t1", "planta": "planta"}
    for A, B, p in (((0, y, 5000), (5000, y, 5000), "banzo_inf"), ((5000, y, 5000), (10000, y, 5000), "banzo_inf"),
                    ((0, y, 5800), (5000, y, 6500), "banzo_sup"),
                    ((5000, y, 6500), (10000, y, 5800), "banzo_sup"), ((0, y, 5000), (0, y, 5800), "montante"),
                    ((10000, y, 5000), (10000, y, 5800), "montante"), ((5000, y, 5000), (5000, y, 6500), "montante"),
                    ((0, y, 5800), (5000, y, 5000), "diagonal"), ((5000, y, 5000), (10000, y, 5800), "diagonal")):
        doc.add(Barra(inicio=tuple(map(float, A)), fim=tuple(map(float, B)), perfil="TQ 50×50×2,0", camada="Treliças",
                      papel="banzo" if p.startswith("banzo") else p, atributos=dict(base, papel_trelica=p)))
    return doc


def _contar(doc):
    return collections.Counter((e.atributos or {}).get("elemento") for e in doc.entidades.values())


def _ys_das_tesouras(doc):
    return sorted({round(e.inicio[1]) for e in doc.entidades.values() if (e.atributos or {}).get("elemento") == "trelica"})


def test_aberta_retraida_e_de_novo_aberta():
    doc = _modelo()
    r = CM.aplicar(doc, PAR, "aberta")
    assert r["tesouras"] == 5 and r["sanfona"] == 16             # 4 pares de vizinhas × 2 lados × X
    c = _contar(doc)
    assert c["trelica"] == 45 and c["sanfona"] == 16 and c["pilar"] == 4 and c["viga"] == 2
    assert _ys_das_tesouras(doc) == [0, 2500, 5000, 7500, 10000]   # as das pontas rentes aos pilares
    CM.aplicar(doc, PAR, "retraida")
    ys = _ys_das_tesouras(doc)
    assert len(ys) == 5 and min(ys) == 0 and max(ys) == 2000        # empilhadas nos 2 m da ponta de Y menor
    assert _contar(doc)["trelica"] == 45 and _contar(doc)["sanfona"] == 16
    CM.aplicar(doc, PAR, "aberta")
    assert _contar(doc) == c                                         # nada sobra da situação anterior
    # cada peça gerada sabe a posição e a situação; as tesouras mantêm a planta (a sincronização troca e gera de novo)
    ger = [e for e in doc.entidades.values() if CM.gerada(e)]
    assert len(ger) == 61 and all(e.atributos["cobertura_movel"]["situacao"] == "aberta" for e in ger)
    assert all(e.atributos.get("planta") == "planta" for e in ger)


def test_a_analise_le_a_mesma_cobertura_com_o_3d_gerado():
    """com as cópias no 3D, a análise usa só a primeira de molde (não soma as 5 do 3D às 5 dela) e dá o mesmo resultado"""
    par = dict(PAR, cobertura_movel=True)
    antes = AE.calcular(_modelo(), par)
    doc = _modelo()
    CM.aplicar(doc, par, "retraida")
    depois = AE.calcular(doc, par)
    for r in (antes, depois):
        assert r["movel"]["n"] == 5 and not r["instavel"]
        assert sum(1 for b in r["barras"] if b["elemento"] == "trelica") == 5 * sum(
            1 for b in AE.montar(_modelo(), dict(par, cobertura_movel=False))["barras"] if b["elemento"] == "trelica")
    pp_a, pp_d = antes["equilibrio"]["PP"]["cargas_kN"][2], depois["equilibrio"]["PP"]["cargas_kN"][2]
    assert pp_d == pytest.approx(pp_a, rel=1e-3)
    fz = lambda r: sorted(e["Fz_max"][0] for e in r["reacoes_envoltoria"])
    assert fz(depois) == pytest.approx(fz(antes), rel=1e-2, abs=0.05)


def test_sem_tesoura_apoiada_e_erro_de_dados():
    from nucleo.base import ErroDeDados
    doc = Documento(nome="vazio")
    doc.add(Barra(inicio=(0, 0, 0), fim=(0, 0, 5000), perfil="W 250×32,7", papel="pilar", atributos={"elemento": "pilar"}))
    with pytest.raises(ErroDeDados):
        CM.aplicar(doc, PAR, "aberta")


def test_a_planta_acompanha_a_situacao():
    """as linhas das tesouras na planta, na posição de cada situação; a lançada vai para a camada do molde (escondida)"""
    from nucleo2d.desenho import Desenho, Linha
    doc = _modelo()
    des = Desenho(nome="planta")
    des.add(Linha(id="t1", camada="ESTRUTURA", a=(0.0, 2000.0), b=(10000.0, 2000.0), atributos={"elemento": "trelica", "marca": "T1"}))
    CM.aplicar(doc, PAR, "aberta")
    assert CM.na_planta(des, doc) is True
    ys = sorted(e.a[1] for e in des.entidades.values() if (e.atributos or {}).get("cobertura_movel") and e.tipo == "linha")
    assert ys == [0.0, 2500.0, 5000.0, 7500.0, 10000.0]
    assert des.entidades["t1"].camada == CM.CAMADA_MOLDE and not des.camadas[CM.CAMADA_MOLDE].visivel
    assert CM.na_planta(des, doc) is False                          # sem mudança, nada muda (ids fixos)
    CM.aplicar(doc, PAR, "retraida")
    assert CM.na_planta(des, doc) is True
    ys = sorted(e.a[1] for e in des.entidades.values() if (e.atributos or {}).get("cobertura_movel") and e.tipo == "linha")
    assert ys == [0.0, 500.0, 1000.0, 1500.0, 2000.0]
    assert "RETRAÍDA" in des.entidades["cobertura-movel-texto"].texto


def test_troca_de_perfil_so_na_analise():
    """o grupo (função|perfil original) ganha o perfil novo nas barras todas; o nome fora do catálogo vira aviso"""
    par = {"vento": False, "telha": 0.0, "trocas_perfil": {"pilar|W 250×32,7": "W 360×51,0", "viga|W 150×22,5": "Perfil Que Não Existe"}}
    r = AE.calcular(_modelo(), par)
    pil = [b for b in r["barras"] if b["papel"] == "pilar"]
    assert pil and all(b["perfil"] == "W 360×51,0" and b["perfil_original"] == "W 250×32,7" for b in pil)
    assert all(b["perfil"] == "W 150×22,5" and "perfil_original" not in b for b in r["barras"] if b["papel"] == "viga")
    assert any("ignorada" in a and "Perfil Que Não Existe" in a for a in r["avisos"])
    g = {x["chave"]: x for x in r["grupos_perfis"]}
    assert g["pilar|W 250×32,7"]["atual"] == "W 360×51,0" and g["pilar|W 250×32,7"]["alternativas"]
    sem = AE.calcular(_modelo(), {"vento": False, "telha": 0.0})
    pior = lambda rr: max(rr["envoltoria"][i]["sigma"] for i, b in enumerate(rr["barras"]) if b["papel"] == "pilar")
    assert pior(r) < pior(sem)                                      # o pilar mais pesado trabalha menos
