# -*- coding: utf-8 -*-
"""Lançamento da estrutura sobre o arquitetônico (0.8.29): arquitetônico em milímetro real
e travado, malha de eixos, eixos lidos da camada EIXO, lançamento nos eixos com marcas, e a
coerência entre o motor do galpão e o cálculo do modelo 3D no modelo lançado."""
import collections
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo.base import ErroDeDados                             # noqa: E402
from nucleo2d.desenho import Desenho, Linha, Texto              # noqa: E402
from nucleo3d import calculo_ifc, lancamento as L               # noqa: E402
from nucleo3d.modelo import Barra                               # noqa: E402


# ------------------------------------------------------------ vãos e malha

def test_ler_vaos():
    assert L.ler_vaos("5x6000") == [6000.0] * 5
    assert L.ler_vaos("3×6m + 7,5m") == [6000.0] * 3 + [7500.0]
    assert L.ler_vaos("6000 600cm 6") == [6000.0, 6000.0, 6000.0]       # número pequeno é metro
    with pytest.raises(ErroDeDados):
        L.ler_vaos("seis metros")


def test_malha_e_leitura_dos_eixos_girada():
    """A malha girada 30° e deslocada volta como os mesmos eixos: 6 números, 2 letras,
    posições a 6 m e vão de 15 m, direção g = (cos 30°, sen 30°)."""
    m = L.malha_de_eixos((1000.0, 2000.0), "5x6000", "15000", angulo=30.0, escala=100)
    tipos = collections.Counter(e.tipo for e in m.entidades.values())
    assert tipos == {"linha": 8, "circulo": 8, "texto": 8, "cota": 7}
    ex = L.eixos_do_desenho(m)
    assert [n["nome"] for n in ex["numeros"]] == ["1", "2", "3", "4", "5", "6"]
    assert [l["nome"] for l in ex["letras"]] == ["A", "B"]
    assert ex["eixo_g"] == pytest.approx([math.cos(math.radians(30)), math.sin(math.radians(30))], abs=1e-6)
    ps = [n["pos"] for n in ex["numeros"]]
    assert [b - a for a, b in zip(ps, ps[1:])] == pytest.approx([6000.0] * 5, abs=0.2)
    assert ex["letras"][1]["pos"] - ex["letras"][0]["pos"] == pytest.approx(15000.0, abs=0.2)


def test_bolinhas_e_cotas_da_malha_nao_se_cruzam():
    """As cotas ficam entre a obra e as bolinhas: a mais afastada ainda antes da bolinha."""
    m = L.malha_de_eixos((0.0, 0.0), "2x6000", "12000", escala=100)
    bol = [e for e in m.entidades.values() if e.tipo == "circulo"]
    raio = bol[0].raio
    y_bolinhas = min(c.centro[1] for c in bol if abs(c.centro[0]) < 1.0 or c.centro[1] < -100.0) + raio
    cotas = [e for e in m.entidades.values() if e.tipo == "cota" and abs(e.p1[1] - e.p2[1]) < 1e-6]
    linhas_de_cota = [c.p1[1] - (-c.deslocamento) * 100.0 for c in cotas]          # deslocamento negativo = para baixo
    assert all(y > y_bolinhas for y in linhas_de_cota), (linhas_de_cota, y_bolinhas)


def test_eixos_desenhados_a_mao_com_nomes_nas_bolinhas():
    """Linhas soltas na camada EIXO, com os nomes em textos junto das pontas: números na
    família com dígitos, letras na outra, mesmo com mais letras que números."""
    d = Desenho(nome="t", escala=100)
    for i, x in enumerate((0.0, 7000.0, 14000.0)):
        d.add(Linha(camada="EIXO", a=(x, -1500.0), b=(x, 21500.0)))
        d.add(Texto(camada="EIXO", posicao=(x, -2000.0), texto=str(i + 1)))
    for j, y in enumerate((0.0, 5000.0, 10000.0, 15000.0, 20000.0)):
        d.add(Linha(camada="EIXO", a=(-1500.0, y), b=(15500.0, y)))
        d.add(Texto(camada="EIXO", posicao=(-2000.0, y), texto="ABCDE"[j]))
    ex = L.eixos_do_desenho(d)
    assert [n["nome"] for n in ex["numeros"]] == ["1", "2", "3"]
    assert [l["nome"] for l in ex["letras"]] == list("ABCDE")
    g = L.geometria_dos_eixos(ex)
    assert g["vao"] == pytest.approx(20000.0) and g["comprimento"] == pytest.approx(14000.0)
    assert any("intermediários" in a for a in g["avisos"])


def test_eixos_sem_nomes_e_nao_perpendiculares():
    d = Desenho(nome="t", escala=100)
    for x in (0.0, 6000.0, 12000.0):
        d.add(Linha(camada="EIXO", a=(x, 0.0), b=(x, 10000.0)))
    for y in (0.0, 10000.0):
        d.add(Linha(camada="EIXO", a=(0.0, y), b=(12000.0, y)))
    ex = L.eixos_do_desenho(d)
    assert [n["nome"] for n in ex["numeros"]] == ["1", "2", "3"]            # a família com mais linhas
    assert [l["nome"] for l in ex["letras"]] == ["A", "B"]
    torto = Desenho(nome="t", escala=100)
    for x in (0.0, 6000.0):
        torto.add(Linha(camada="EIXO", a=(x, 0.0), b=(x, 10000.0)))
    for y in (0.0, 10000.0):
        torto.add(Linha(camada="EIXO", a=(0.0, y), b=(12000.0, y + 1500.0)))
    with pytest.raises(ErroDeDados):
        L.eixos_do_desenho(torto)


# ------------------------------------------------------------ arquitetônico

def _dxf_cm(caminho):
    ezdxf = pytest.importorskip("ezdxf")
    d = ezdxf.new("R2010"); d.header["$INSUNITS"] = 5
    m = d.modelspace()
    X0, Y0 = 350000.0, 780000.0
    m.add_lwpolyline([(X0, Y0), (X0 + 3000, Y0), (X0 + 3000, Y0 + 1500), (X0, Y0 + 1500)], close=True, dxfattribs={"layer": "PAREDE"})
    m.add_text("DEPÓSITO", dxfattribs={"layer": "TEXTO", "height": 40, "insert": (X0 + 1300, Y0 + 750)})
    d.saveas(caminho)
    return open(caminho, "rb").read()


def test_arquitetonico_dxf_em_mm_na_origem_e_travado(tmp_path):
    dados = _dxf_cm(str(tmp_path / "a.dxf"))
    des, r = L.ler_arquitetonico(dados, "dxf")
    (x0, y0), (x1, y1) = des.caixa()
    assert (x0, y0) == pytest.approx((0.0, 0.0), abs=1.0)                  # trazido para a origem
    assert (x1, y1) == pytest.approx((30000.0, 15000.0), abs=1.0)          # centímetro → milímetro
    assert r["largura_m"] == pytest.approx(30.0, abs=0.01)
    arq = {k: c for k, c in des.camadas.items() if k.startswith(L.PREFIXO_ARQ)}
    assert arq and all(c.bloqueada and c.cor == L.COR_ARQ for c in arq.values())
    segs = L.segmentos_da_referencia(des)
    assert len(segs) == 4                                                   # o retângulo; o texto fica de fora
    # a planta nova guarda os eixos da anterior
    velho = Desenho(nome="p", escala=100)
    velho.add(Linha(camada="EIXO", a=(0.0, 0.0), b=(0.0, 10000.0)))
    velho.add(Linha(camada="ARQ PAREDE", a=(0.0, 0.0), b=(1.0, 1.0)))
    nova = L.desenho_de_lancamento(des, velho.dict())
    assert sum(1 for e in nova.entidades.values() if e.camada == "EIXO") == 1
    assert sum(1 for e in nova.entidades.values() if e.camada == "ARQ PAREDE") == 1   # a velha não volta


def test_arquitetonico_formato_recusado():
    with pytest.raises(ErroDeDados):
        L.ler_arquitetonico(b"xx", "dwg")


# ------------------------------------------------------------ lançar

@pytest.fixture(scope="module")
def lancado():
    ex = L.eixos_do_desenho(L.malha_de_eixos((150.0, 150.0), "5x6000", "15000", escala=100))
    return L.lancar(ex, {"sistema": "treliçado"}, nome="Teste")


def test_lancar_trelicado_nos_eixos(lancado):
    r = lancado
    doc = r["doc"]
    s = r["resumo"]
    assert s["dimensionado"] and s["ok"] and s["porticos"] == 6 and s["vao_m"] == pytest.approx(15.0)
    # padrão da tesoura: apoiada, com a base engastada (a combinação estável)
    assert r["dados"].ligacao_tesoura == "apoiada" and r["dados"].base_rotulada is False
    pilares = [b for b in doc.barras if b.papel == "pilar"]
    assert len(pilares) == 12
    xs = sorted({round(b.inicio[0]) for b in pilares})
    ys = sorted({round(b.inicio[1]) for b in pilares})
    assert xs == [150, 6150, 12150, 18150, 24150, 30150] and ys == [150, 15150]
    # marcas em todas as peças de aço; as seis tesouras iguais são um conjunto só
    assert all((b.atributos.get("marcas") or {}).get("posicao") for b in doc.barras)
    conj_tes = {b.atributos["marcas"]["conjunto"] for b in doc.barras if b.papel == "banzo"}
    assert len(conj_tes) == 1
    conj_pil = {b.atributos["marcas"]["conjunto"] for b in pilares}
    placas = [c for c in doc.chapas if c.atributos.get("marca") == "CH3"]
    assert len(placas) == 12 and {c.atributos["marcas"]["conjunto"] for c in placas} == conj_pil
    # correntes e travamento com o papel que o cálculo e o detalhamento leem
    papeis = collections.Counter(b.papel for b in doc.barras)
    assert papeis["corrente"] > 0 and papeis["travamento"] > 0 and papeis.get("barra", 0) == 0


def test_tercas_nos_nos_da_tesoura_sem_duplicar_a_cumeeira(lancado):
    doc = lancado["doc"]
    bs = [b for b in doc.barras if b.papel == "banzo" and b.atributos.get("portico") == 1
          and b.atributos.get("familia") == "banzo superior"]
    nos = {round(p[1]) for b in bs for p in (b.inicio, b.fim)}
    tercas = [b for b in doc.barras if b.papel == "terça" and b.atributos.get("vao") == 1]
    ys = [round((b.inicio[1] + b.fim[1]) / 2) for b in tercas]
    # o centro da terça fica sobre o nó (a menos do afastamento na normal da água, < 25 mm em 10 %)
    assert all(min(abs(y - n) for n in nos) < 25 for y in ys), (sorted(ys), sorted(nos))
    chaves = collections.Counter((round(b.inicio[1]), round(b.inicio[2])) for b in tercas)
    assert max(chaves.values()) == 1                                          # nenhuma terça em dobro


def test_modelo_lancado_no_calculo_do_3d(lancado):
    """O cálculo do modelo 3D enxerga o que o galpão montou: as correntes (uma linha por vão,
    não duas), o travamento do banzo inferior e todas as tesouras."""
    doc = lancado["doc"]
    c = calculo_ifc.calcular(doc, calculo_ifc.nomes_das_barras(doc), {"v0": 40.0, "categoria": "II"})
    assert c["ok"] and c["resumo"]["tesouras"] == 6
    tercas = [e for e in c["elementos"].values() if e["tipo"] == "terca"]
    assert tercas and all(e["dimensionamento"]["correntes"] == 1 for e in tercas)
    banzo_inf = [e for e in c["elementos"].values() if e["tipo"] == "banzo" and e.get("posicao") == "inferior"]
    assert banzo_inf and all(e["dimensionamento"].get("Ly_cm", 0) < 1500.0 for e in banzo_inf)
    # nenhuma barra da tesoura reprova no modelo 3D quando o galpão a aprovou
    for e in c["elementos"].values():
        if e["tipo"] in ("banzo", "diagonal", "montante"):
            assert e["aproveitamento"] <= 1.0, (e["titulo"], e["aproveitamento"], e["governa"])
    assert not any("não reconhecido" in a for a in c["avisos"])


def test_lancar_alma_cheia():
    ex = L.eixos_do_desenho(L.malha_de_eixos((0.0, 0.0), "4x6000", "12000", escala=100))
    r = L.lancar(ex, {"sistema": "alma cheia", "pe_direito": 5.0})
    doc = r["doc"]
    papeis = collections.Counter(b.papel for b in doc.barras)
    assert papeis["pilar"] == 10 and papeis["viga"] == 10
    vigas = [b for b in doc.barras if b.papel == "viga"]
    conj = {b.atributos["marcas"]["conjunto"] for b in vigas}
    chapas_viga = [c for c in doc.chapas if c.atributos["marcas"]["conjunto"] in conj]
    assert chapas_viga, "mísulas e chapas de topo no conjunto da viga"


def test_lancar_sem_eixos_suficientes():
    ex = {"eixo_g": [1, 0], "perp_g": [0, 1], "numeros": [{"nome": "1", "pos": 0.0}], "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 10000.0}]}
    with pytest.raises(ErroDeDados):
        L.lancar(ex, {})


def test_espacamento_diferente_usa_o_maior():
    ex = L.eixos_do_desenho(L.malha_de_eixos((0.0, 0.0), "5000 7000 5000", "12000", escala=100))
    dg, geo, _p = L.dados_do_galpao(ex, {"sistema": "alma cheia"})
    assert dg.espacamento_porticos == pytest.approx(7.0)
    assert any("maior" in a for a in geo["avisos"])


# ------------------------------------------------------------ nomes de fábrica das barras redondas

def test_barras_redondas_do_galpao_no_calculo():
    from nucleo import perfis_fabrica as pf
    p16 = pf.perfil_de_fabrica("Barra ø 16 mm")
    assert p16.dados["d"] == pytest.approx(16.0) and p16.nome == "Barra ø 16 mm"
    assert pf.perfil_de_fabrica("Barra redonda ø 13 mm").dados["d"] == pytest.approx(13.0)
    assert pf.perfil_de_fabrica("FE RED 3/8''") is not None
    assert pf.perfil_de_fabrica("BARRA CHATA 50X6") is None


def test_arquitetonico_pdf_escala_pelas_cotas(tmp_path):
    """Planta impressa em PDF a 1:100 (com as cotas da malha): lida de volta sem escala
    informada, a escala sai das cotas e as medidas voltam ao milímetro real."""
    from nucleo2d.pranchas import pdf_dos_desenhos
    m = L.malha_de_eixos((0.0, 0.0), "5x6000", "15000", escala=100)
    m.escala = 100.0
    caminho = pdf_dos_desenhos([m], str(tmp_path / "planta.pdf"))
    des, r = L.ler_arquitetonico(open(caminho, "rb").read(), "pdf")
    assert r["escala"] == "1:100" and r["fonte_escala"] == "pelas cotas", r
    linhas = [e for e in des.entidades.values() if e.tipo == "linha"]
    maior = max(math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1]) for e in linhas)
    assert maior == pytest.approx(30000.0 + 2 * 1500.0, rel=0.02)          # o eixo com letra, de ponta a ponta
