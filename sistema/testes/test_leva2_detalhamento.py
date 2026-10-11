# -*- coding: utf-8 -*-
"""Leva 2 da auditoria de 30/09 (o detalhamento), rodada 1 — 11/10/2026:

* D1: os furos da mesa oposta (+e2) não somem — inferidos pelo parafuso que a atravessa, na vista "baixo", e desenhados
  numa vista própria na célula;
* D2: chapas de mesmo perfil, furos e volume a 1 % mas contorno diferente (o chanfro) não viram a mesma marca; a dobrada
  espelhada é a outra mão (marca própria, decisão do usuário); a chapa plana virada do avesso continua a mesma;
* D6: a terça "Ue" e a de papel "terça" (Tekla, planta) são terças — antes viravam agulhamento;
* D11: a polegada só para a chapa de comércio (5,0 e 6,0 mm não viram 3/16" e 1/4")."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo2d import detalhar as det                    # noqa: E402
from nucleo2d.desenho import Desenho, Texto             # noqa: E402
from nucleo2d.detalhe import base as B                  # noqa: E402
from nucleo3d.modelo import Documento, Solido           # noqa: E402
from saida.detalhamento import Posicao                  # noqa: E402
from test_detalhamento import perfil_u                   # noqa: E402
from test_detalhar2d import _caixa_solida, _solido       # noqa: E402


# ------------------------------------------------------------------ D1
def _parafuso(doc, v, f):
    b = Solido(nome="BOLT (A) 12x35", vertices=v, faces=f)
    b.atributos["tipo_ifc"] = "IfcMechanicalFastener"
    b.atributos["criado_no_editor"] = True          # o do IFC já traz o furo modelado na barra; o do editor, não
    doc.add(b)


def _u_com_parafusos_nas_duas_mesas():
    """U 150 × 50 × 3 de 2 m (alma em z = 0, mesas em y = 0 e y = 150) com um parafuso atravessando cada mesa"""
    doc = Documento(nome="d1")
    v, f = perfil_u(2000.0, 150.0, 50.0, 3.0)
    doc.add(_solido("U 150x50x3", "IfcBeam", v, f, "V1", "V1", "U 150x50x3"))
    _parafuso(doc, *_caixa_solida(12, 45, 12, dx=494, dy=150 - 20, dz=19))    # na mesa de y = 150, em x = 500
    _parafuso(doc, *_caixa_solida(12, 45, 12, dx=1494, dy=-25, dz=19))         # na de y = 0, em x = 1500
    return doc


def test_d1_furo_de_cada_mesa_na_vista_dela():
    doc = _u_com_parafusos_nas_duas_mesas()
    pos = det.levantar(doc, regra_tercas=False)["posicoes"][0]
    por_vista = {f.vista: f for f in pos.furos}
    assert set(por_vista) == {"topo", "baixo"}, [(f.vista, f.x) for f in pos.furos]
    # as duas mesas não se confundem: um furo em cada, em pontas diferentes da peça
    assert {round(por_vista["topo"].x), round(por_vista["baixo"].x)} == {500, 1500}


def test_d1_celula_desenha_a_mesa_de_baixo():
    doc = _u_com_parafusos_nas_duas_mesas()
    pos = det.levantar(doc, regra_tercas=False)["posicoes"][0]
    from nucleo2d.detalhe.celulas import desenho_da_posicao
    d = Desenho()
    desenho_da_posicao(pos, d, 0.0, 0.0)
    textos = [e.texto for e in d.entidades.values() if isinstance(e, Texto)]
    assert any(t.startswith("VISTA DE CIMA") for t in textos)
    assert any(t.startswith("MESA DE BAIXO") for t in textos), textos


# ------------------------------------------------------------------ D2
def _chapa(marca, contorno, classe="chapa"):
    xs, ys = [q[0] for q in contorno], [q[1] for q in contorno]
    return Posicao(marca=marca, tipo_ifc="IfcPlate", perfil="CH 9,5", material="ASTM A36", quantidade=1, classe=classe,
                   L=max(xs) - min(xs), H=max(ys) - min(ys), T=9.5, espessura=9.5, comprimento=max(xs) - min(xs),
                   volume=300.0 * 300.0 * 9.5, contorno=list(contorno))


QUADRADA = [(0, 0), (300, 0), (300, 300), (0, 300)]
CHANFRO = [(0, 0), (280, 0), (300, 20), (300, 300), (0, 300)]
CHANFRO_ESPELHADO = [(20, 0), (300, 0), (300, 300), (0, 300), (0, 20)]


def _fundir(*ps):
    return B.fundir_posicoes_iguais(list(ps), {})


def test_d2_chanfro_pequeno_nao_vira_a_mesma_marca():
    assert len(_fundir(_chapa("CH1", QUADRADA), _chapa("CH2", CHANFRO))) == 2       # 0,2 % do volume, contorno outro


def test_d2_mesma_chapa_girada_ou_virada_junta():
    girada = [(300 - x, 300 - y) for x, y in CHANFRO]
    assert len(_fundir(_chapa("CH1", CHANFRO), _chapa("CH2", girada))) == 1
    assert len(_fundir(_chapa("CH1", CHANFRO), _chapa("CH2", CHANFRO_ESPELHADO))) == 1   # plana: a mesma, do avesso
    ruido = [(x + 0.4, y - 0.3) for x, y in QUADRADA]
    assert len(_fundir(_chapa("CH1", QUADRADA), _chapa("CH2", ruido))) == 1


def test_d2_dobrada_espelhada_e_a_outra_mao():
    a, b = _chapa("CD1", CHANFRO, "chapa_dobrada"), _chapa("CD2", CHANFRO_ESPELHADO, "chapa_dobrada")
    assert len(_fundir(a, b)) == 2


# ------------------------------------------------------------------ D6
def _barra(perfil, H, L=6000.0, conjuntos=(), papel=""):
    p = Posicao(marca="B1", tipo_ifc="IfcBeam", perfil=perfil, classe="barra", H=H, L=L, comprimento=L, conjuntos=list(conjuntos))
    p.papel = papel
    return p


def test_d6_terca_ue_e_terca():
    assert B._eh_terca(_barra("Ue 150×60×20×2,00", 150.0), "")
    assert B._eh_terca(_barra("UE150x60x20x2", 150.0), "")
    assert B._eh_terca(_barra("U 150x50x3", 150.0), "")                       # a de antes continua


def test_d6_papel_terca_vale_mesmo_dentro_de_conjunto():
    assert not B._eh_terca(_barra("W 150x13", 150.0, conjuntos=["B5"]), "")   # sem papel: viga do conjunto
    assert B._eh_terca(_barra("W 150x13", 150.0, conjuntos=["B5"], papel="terça"), "")
    assert B._eh_terca(_barra("Ue 200x75x25x2,65", 200.0, conjuntos=["B5"], papel="longarina"), "")
    assert not B._eh_terca(_barra("Ue 150x60x20x2", 150.0, conjuntos=["T1"], papel="viga"), "")   # banzo da tesoura


# ------------------------------------------------------------------ D11
def test_d11_polegada_so_na_chapa_de_comercio():
    def rot(t):
        return B._rotulo_espessura(Posicao(marca="x", tipo_ifc="IfcPlate", classe="chapa", T=t, espessura=t))
    assert rot(6.3) == '#1/4"' and rot(4.75) == '#3/16"' and rot(9.5) == '#3/8"'
    assert rot(5.0) == "#5 mm" and rot(6.0) == "#6 mm" and rot(2.65) == "#2,65 mm"


# ------------------------------------------------------------------ rodada 2 (11/10/2026)
def test_d4_furo_padrao_da_norma_e_oblongo_da_puncao():
    import fabrica
    assert fabrica.furo_padrao_mm(12) == 13.5 and fabrica.furo_padrao_mm(16) == 17.5
    assert fabrica.furo_padrao_mm(24) == 25.5 and fabrica.furo_padrao_mm(25.4) == 27.4       # acima de 24: d + 2
    # o oblongo da terça é a punção: 25 × 13 para M12, venha o furo do IFC (Ø13) ou da norma (Ø13,5)
    assert fabrica.oblongo_do_furo(13.0) == (25.0, 13.0) == fabrica.oblongo_do_furo(13.5)
    from nucleo import acessorios as A
    assert A.furo_mm("M12") == 13.5 and A.oblongo_mm("M12") == 25.0


def test_d5_gabarito_fora_da_peca_avisa():
    from saida.detalhamento import Furo
    p = Posicao(marca="T", tipo_ifc="IfcBeam", classe="barra", L=6000.0, H=100.0)
    assert B.conferir_gabarito(p, [Furo("redondo", 40, 25, 13.5), Furo("redondo", 40, 75, 13.5)]) == []
    ruins = B.conferir_gabarito(p, [Furo("redondo", 10, 5, 13.5), Furo("redondo", 10, 30, 13.5)])
    assert any("Tab. 14" in r for r in ruins) and any("2,7 d" in r for r in ruins)


def test_d9_nomes_guardados_entre_um_detalhar_e_outro():
    from nucleo2d.detalhe.nomes import numerar_estavel as N
    assert N(["a", "b", "c"], None, "T") == {"a": "T1", "b": "T2", "c": "T3"}          # sem anteriores: em sequência
    # a "b" saiu, a "d" entrou: as que ficaram mantêm o número, a nova vai depois do maior
    assert N(["c", "a", "d"], {"a": "T1", "b": "T2", "c": "T3"}, "T") == {"c": "T3", "a": "T1", "d": "T4"}
    assert N(["x", "y"], {"x": "S.T.4", "y": "lixo"}, "S.T.") == {"x": "S.T.4", "y": "S.T.5"}


# ------------------------------------------------------------------ rodada 3: D3 (11/10/2026)
def _t_soldado():
    """chapa 200 × 100 × 10 deitada e uma nervura de 100 × 80 × 6 em pé no meio dela: um T, filete dos dois lados"""
    base = _solido("PLATE 200x100x10", "IfcPlate", *_caixa_solida(200, 100, 10), "P1", "S1", "PLATE 200x100x10")
    alma = _solido("PLATE 100x80x6", "IfcPlate", *_caixa_solida(100, 6, 80, dx=50, dy=47, dz=10), "P2", "S1", "PLATE 100x80x6")
    return base, alma


def test_d3_cordao_do_t_pela_parte_menos_espessa():
    from nucleo2d.detalhe.montagens import cordoes_de_solda
    base, alma = _t_soldado()
    g = {"tipo": "soldadas", "pecas": [base.id, alma.id], "_nomes": {base.id: "CH1", alma.id: "CH2"}}
    cs = cordoes_de_solda(g, {base.id: base, alma.id: alma})
    assert len(cs) == 1
    c = cs[0]
    assert abs(c["comprimento"] - 100.0) < 0.6 and c["lados"] == 2
    assert c["perna"] == 3.0                     # a menos espessa (6 mm) → 3 mm (NBR 8800:2024, Tabela 11)
    assert c["nomes"] == ("CH1", "CH2")


def test_d3_perna_minima_da_tabela_11():
    from nucleo import materiais as mat
    assert [mat.perna_minima(t / 10) * 10 for t in (6.3, 8.0, 12.5, 16.0, 19.0, 25.0)] == [3.0, 5.0, 5.0, 6.0, 6.0, 8.0]


def test_d3_simbolo_de_solda_na_camada_solda():
    from nucleo2d.detalhe.base import _Papel, simbolo_solda
    d = Desenho()
    p = _Papel(d, {}, 0.0, 0.0)
    simbolo_solda(p, 10.0, 0.0, 0.0, 50.0, 80.0, 3.0, 100.0)
    ents = list(d.entidades.values())
    assert ents and all(e.camada == "SOLDA" for e in ents)
    assert sorted(e.texto for e in ents if isinstance(e, Texto)) == ["100", "3"]
    assert sum(1 for e in ents if getattr(e, "fechada", False)) == 2          # os dois triângulos: filete dos dois lados
