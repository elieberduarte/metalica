# -*- coding: utf-8 -*-
"""Tesouras treliçadas: malha, modelo de análise e o galpão inteiro dimensionado."""
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import analise, galpao, tesouras          # noqa: E402
from nucleo.base import ErroDeDados                   # noqa: E402
from nucleo.modelo_galpao import DadosGalpao          # noqa: E402

SECOES = {"banzo superior": (12.0, 300.0), "banzo inferior": (12.0, 300.0),
          "diagonal": (4.0, 20.0), "montante": (4.0, 20.0), "pilar": (85.0, 12000.0)}


def _dados(**kw) -> DadosGalpao:
    base = dict(tipo_portico="treliçado (tesoura)", base_rotulada=False,
                ligacao_tesoura="apoiada", vao=20.0, comprimento=40.0)
    base.update(kw)
    return DadosGalpao(**base)


# ------------------------------------------------------------------ 1. geometria

@pytest.mark.parametrize("formato", list(tesouras.FORMATOS))
@pytest.mark.parametrize("diagonais", list(tesouras.DIAGONAIS))
def test_malha_fecha_em_triangulos(formato, diagonais):
    """Toda malha tem de ser conexa e sem nó solto: nó de treliça com uma barra só cai."""
    inc = 0.25 if formato == "triangular" else 0.10
    t = tesouras.geometria(2000.0, inc, formato, diagonais, paineis=4)
    ligacoes = {n.nome: 0 for n in t.nos}
    for b in t.barras:
        assert b.i in ligacoes and b.j in ligacoes, "barra apontando para nó inexistente"
        ligacoes[b.i] += 1
        ligacoes[b.j] += 1
    soltos = [n for n, k in ligacoes.items() if k < 2]
    assert not soltos, "nós com menos de duas barras: %s" % soltos
    assert len({frozenset((b.i, b.j)) for b in t.barras}) == len(t.barras), "barra repetida"


def test_simetria_e_medidas():
    t = tesouras.geometria(2000.0, 0.10, "trapezoidal", "Howe", altura_apoio=80.0, paineis=5)
    assert t.altura_apoio == 80.0
    assert t.altura_cumeeira == pytest.approx(80.0 + 1000.0 * 0.10)
    assert t.paineis == 5 and len(t.do_papel("banzo superior")) == 10
    # o desenho fecha: o banzo superior sobe e desce a mesma coisa
    ys = [t.no("TS%d" % k).y for k in range(11)]
    assert ys == pytest.approx(ys[::-1])
    assert t.comprimento_total("banzo superior") > t.vao        # inclinado, é mais longo


def test_banzos_paralelos_tem_altura_constante():
    t = tesouras.geometria(1800.0, 0.12, "banzos paralelos", "Warren", altura_apoio=120.0,
                           paineis=4)
    for k in range(2 * t.paineis + 1):
        sup = t.no("TS%d" % k)
        inf = [n for n in t.nos if n.banzo == "inferior" and abs(n.x - sup.x) < 1e-6]
        if inf:
            assert (sup.y - inf[0].y) == pytest.approx(120.0)


def test_paineis_seguem_o_passo_das_tercas():
    """O nó do banzo superior tem de cair perto da terça: é ali que a carga chega."""
    t = tesouras.geometria(2400.0, 0.10, "trapezoidal", "Pratt", espacamento_tercas=160.0)
    assert 140.0 < t.painel < 185.0


def test_geometria_recusa_o_impossivel():
    with pytest.raises(ErroDeDados, match="[Ff]ormato"):
        tesouras.geometria(2000.0, 0.10, "arco")
    with pytest.raises(ErroDeDados, match="iagonais"):
        tesouras.geometria(2000.0, 0.10, "trapezoidal", "Vierendeel")
    # tesoura triangular de telhado quase plano não vence o vão
    with pytest.raises(ErroDeDados, match="altura"):
        tesouras.geometria(2000.0, 0.05, "triangular", "Howe")


# ------------------------------------------------------------- 2. modelo de análise

def test_modelo_equilibra_a_carga():
    t = tesouras.geometria(2000.0, 0.10, "trapezoidal", "Howe", paineis=4)
    m = tesouras.montar(t, 600.0, SECOES, base_rotulada=False, ligacao="apoiada")
    for rot in m.dados["barras_agua_esq"] + m.dados["barras_agua_dir"]:
        m.distribuida("G", rot, -0.05, "global_y")
    r = analise.resolver(m, "G")
    vertical = sum(v[1] for v in r.reacoes.values())
    assert vertical == pytest.approx(0.05 * t.comprimento_total("banzo superior"), rel=0.02)


def test_joelho_rigido_faz_portico():
    """Com o joelho rígido o pórtico resiste ao vento mesmo com base rotulada."""
    t = tesouras.geometria(2000.0, 0.10, "trapezoidal", "Pratt", paineis=4)
    m = tesouras.montar(t, 600.0, SECOES, base_rotulada=True, ligacao="rígida")
    for rot in m.dados["barras_pilar_esq"]:
        m.distribuida("V", rot, 0.02, "global_x")
    r = analise.resolver(m, "V")
    # base rotulada: momento nulo no apoio, e a força horizontal se divide pelos dois
    assert all(abs(v[2]) < 1e-6 for v in r.reacoes.values())
    assert sum(abs(v[0]) for v in r.reacoes.values()) > 0.0


def test_tesoura_apoiada_em_base_rotulada_e_mecanismo():
    t = tesouras.geometria(2000.0, 0.10, "trapezoidal", "Howe", paineis=4)
    with pytest.raises(ErroDeDados, match="mecanismo"):
        tesouras.montar(t, 600.0, SECOES, base_rotulada=True, ligacao="apoiada")


def test_menor_perfil_respeita_esbeltez_e_espessura():
    perf, r = tesouras.menor_perfil(("Ue", "U"), "ASTM A572 Gr.50", 80.0, 0.0, 0.0,
                                    200.0, 200.0, "Banzo")
    assert perf is not None and r.ok
    assert tesouras._espessura(perf) >= tesouras.MIN_ESPESSURA
    assert max(200.0, 200.0) / min(perf.rx, perf.ry) <= 200.0


# --------------------------------------------------------- 3. galpão inteiro

@pytest.mark.parametrize("formato, diagonais, ligacao, rotulada, inclinacao", [
    ("trapezoidal", "Howe", "apoiada", False, 10.0),
    ("trapezoidal", "Pratt", "rígida", True, 10.0),
    ("banzos paralelos", "Warren", "apoiada", False, 10.0),
    ("triangular", "Howe", "apoiada", False, 30.0),
])
def test_galpao_trelicado_fecha(formato, diagonais, ligacao, rotulada, inclinacao):
    p = galpao.dimensionar(_dados(formato_tesoura=formato, diagonais_tesoura=diagonais,
                                  ligacao_tesoura=ligacao, base_rotulada=rotulada,
                                  inclinacao=inclinacao))
    assert not p.erros, p.erros
    nomes = {e.nome for e in p.elementos}
    assert {"Banzo superior da tesoura", "Banzo inferior da tesoura", "Pilar"} <= nomes
    reprovados = [(e.nome, round(e.razao, 2)) for e in p.elementos if not e.ok]
    assert not reprovados, reprovados
    assert p.base is not None, "a base do pilar ficou sem dimensionamento"
    assert 10.0 < p.resumo_pesos["kg_por_m2"] < 45.0, p.resumo_pesos


def test_tesoura_pesa_menos_que_alma_cheia():
    """É a razão de existir da tesoura: o mesmo galpão com menos aço."""
    trelicado = galpao.dimensionar(_dados())
    alma = galpao.dimensionar(DadosGalpao(vao=20.0, comprimento=40.0))
    assert not trelicado.erros and not alma.erros
    assert trelicado.resumo_pesos["kg_por_m2"] < alma.resumo_pesos["kg_por_m2"]


def test_banzo_inferior_comprime_sob_succao():
    """O caso que governa a tesoura de galpão leve: sucção invertendo o banzo inferior."""
    p = galpao.dimensionar(_dados())
    banzo = p.elemento("Banzo inferior")
    assert banzo.esforcos["N_compressao_kN"] > 0
    assert "sucção" in banzo.esforcos["caso"]
    # e ele só passa porque há travamento lateral: as linhas têm de estar na lista
    assert p.esforcos["linhas_de_travamento"] >= 1
    assert p.elemento("Travamento do banzo inferior") is not None
    assert any(x.marca == "TV" for x in p.lista_material)


def test_lista_de_material_tem_a_tesoura_toda():
    p = galpao.dimensionar(_dados())
    t = p.esforcos["geometria_tesoura"]
    marcas = {x.marca for x in p.lista_material}
    assert {"BS", "BI", "P1", "T1"} <= marcas
    # diagonais e montantes vão agrupados por comprimento, e a soma tem de bater com o
    # número de barras da malha vezes o número de tesouras
    for papel, prefixo in (("diagonal", "D"), ("montante", "M")):
        na_lista = sum(x.quantidade for x in p.lista_material
                       if x.marca[:1] == prefixo and x.marca[1:].isdigit())
        assert na_lista == len(t.do_papel(papel)) * p.dados.n_porticos, papel
    # o peso da tesoura confere com o comprimento das barras que ela tem
    pecas = [x for x in p.lista_material if x.marca in ("BS", "BI")]
    esperado = t.comprimento_total("banzo superior") / 100.0 * p.dados.n_porticos
    assert sum(x.quantidade * x.comprimento_m for x in pecas if x.marca == "BS") \
        == pytest.approx(esperado, rel=0.01)


def test_altura_do_beiral_sobe_com_a_tesoura():
    """O pé-direito é o banzo inferior; a parede ainda sobe a altura da tesoura."""
    d = _dados(altura_tesoura=1.2)
    assert d.altura_beiral == pytest.approx(d.pe_direito + 1.2)
    assert d.altura_cumeeira == pytest.approx(d.pe_direito + 1.2 + d.vao / 2 * 0.10)


def test_modelo_3d_e_desenho_mostram_a_tesoura():
    from nucleo3d import de_projeto
    from saida import desenhos
    p = galpao.dimensionar(_dados())
    doc = de_projeto.modelo_do_galpao(p)
    papeis = {b.papel for b in doc.barras}
    assert {"banzo", "diagonal", "montante"} <= papeis
    elementos = {(b.atributos or {}).get("elemento") for b in doc.barras}
    assert "Banzo superior da tesoura" in elementos
    d = desenhos.portico(p)
    assert d.nome == "portico-trelicado"


def test_mapa_de_esforcos_cobre_as_familias():
    from nucleo3d import mapa_esforcos as me
    p = galpao.dimensionar(_dados())
    mapa = me.mapa_de_esforcos(p)
    assert mapa["ok"]
    for nome in ("Banzo superior da tesoura", "Diagonal da tesoura", "Pilar"):
        e = mapa["elementos"][nome]
        assert e["barras"], "%s sem barras no pórtico" % nome
        assert e["valores"][me.ENVOLTORIA]["N"] > 0


def test_pranchas_nao_detalham_ligacao_que_nao_existe():
    """Chapa de topo de joelho e de cumeeira são do pórtico de alma cheia."""
    from saida import desenhos
    nomes = {x[0] for x in desenhos.catalogo_de(galpao.dimensionar(_dados()))}
    assert "04-LIGACAO-VIGA-PILAR" not in nomes and "05-LIGACAO-CUMEEIRA" not in nomes
    alma = {x[0] for x in desenhos.catalogo_de(DadosGalpao())}
    assert {"04-LIGACAO-VIGA-PILAR", "05-LIGACAO-CUMEEIRA"} <= alma


def test_memorial_conta_a_estrutura_certa():
    from saida import memorial
    p = galpao.dimensionar(_dados(formato_tesoura="banzos paralelos",
                                  diagonais_tesoura="Warren"))
    html = memorial.montar_html(p)
    assert "Tesoura banzos paralelos" in html
    assert "Warren" in html
    assert "alma cheia" not in html.split("Sistema estrutural")[1][:400]


# ------------------------------------------------ 4. perfil por elemento

def test_perfil_forcado_e_verificado_e_reprova_com_aviso():
    """O perfil escolhido pelo usuário é verificado como qualquer outro; reprovado, fica
    no resultado com a razão e a lista dos que passam ao lado."""
    p = galpao.dimensionar(_dados(perfil_terca="Ue 75×40×15×1,20"))
    terca = p.elemento("Terça")
    assert terca.perfil == "Ue 75×40×15×1,20" and not terca.ok
    assert any("terça escolhida" in a.lower() for a in p.avisos)
    assert terca.alternativas and terca.alternativas[0]["ok"]
    assert all("massa" in a for a in terca.alternativas)


def test_perfil_forcado_de_familia_errada_e_recusado():
    with pytest.raises(ErroDeDados, match="aceita I"):
        DadosGalpao(perfil_viga="Ue 100×50×17×2,00").validar()
    with pytest.raises(ErroDeDados, match="catálogo"):
        DadosGalpao(perfil_pilar="W 999×1").validar()


def test_banzos_duplos_contam_duas_pecas():
    p = galpao.dimensionar(_dados(perfil_banzo_superior="Ue 200×75×20×2,65", banzos_duplos=True))
    bs = p.elemento("Banzo superior")
    assert bs.perfil == "Ue 200×75×20×2,65" and bs.geometria["pecas_por_barra"] == 2
    assert bs.resultado.dados.get("n") == 2
    peca = next(x for x in p.lista_material if x.marca == "BS")
    assert peca.quantidade == 2 * 2 * p.dados.n_porticos and "duplo" in peca.descricao
    # cada elemento da tesoura traz os perfis do catálogo verificados, quem passa primeiro
    for nome in ("Banzo superior", "Banzo inferior", "Diagonal", "Montante"):
        alt = p.elemento(nome).alternativas
        assert alt and alt[0]["ok"] and "massa" in alt[0]
