# -*- coding: utf-8 -*-
"""Tesouras treliçadas: malha, modelo de análise e o galpão inteiro dimensionado."""
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


def test_banzo_continuo_so_tem_ponta_no_apoio_e_na_cumeeira():
    """N1 (14/10): o banzo é contínuo; a ligação de ponta dele é no apoio e na emenda da
    cumeeira (os banzos saem inteiros por água). Os trechos entre essas pontas passam
    corridos pelos nós; diagonais e montantes têm sempre ponta ligada."""
    t = tesouras.geometria(2000.0, 0.10, "trapezoidal", "Howe", paineis=4)
    bs = t.do_papel("banzo superior")
    pontas = [b.rotulo for b in bs if tesouras.barra_de_ponta(t, b)]
    # 8 painéis: bs1 e bs8 no apoio, bs4 e bs5 chegam na cumeeira (x = 1 000 cm)
    assert pontas == ["bs1", "bs4", "bs5", "bs8"], pontas
    bi = t.do_papel("banzo inferior")
    assert tesouras.barra_de_ponta(t, bi[0]) and tesouras.barra_de_ponta(t, bi[-1])
    assert not all(tesouras.barra_de_ponta(t, b) for b in bi)
    assert all(tesouras.barra_de_ponta(t, b) for b in t.do_papel("diagonal") + t.do_papel("montante"))


def test_verificar_barra_ruptura_so_com_a_tracao_das_pontas():
    """Ue 100×50×17×2,00, A572: tração de 40 kN no trecho corrido e 20 kN nas pontas.

      escoamento com 40 kN: 4,417 × 34,5 / 1,10 = 138,5 kN → 0,289
      ruptura com 20 kN (Ct = 0,50 sem a ligação no modelo): 0,50 × 4,417 × 45/1,65
        = 60,23 kN → 0,332 (antes, com os 40 kN do trecho corrido: 0,664)"""
    from nucleo import perfis_fabrica
    ue = perfis_fabrica.perfil_de_fabrica("Ue 100x50x17x2")
    r = tesouras.verificar_barra(ue, "ASTM A572 Gr.50", 0.0, 40.0, 0.0, 150.0, 150.0, 1,
                                 "Banzo inferior", [], Nt_ponta=20.0)
    ve = next(v for v in r.verificacoes if v.titulo.startswith("Tração — escoamento"))
    vr = [v for v in r.verificacoes if v.titulo.startswith("Tração — ruptura")]
    assert ve.Sd == pytest.approx(40.0) and ve.Rd == pytest.approx(138.5, rel=0.005)
    assert "seção líquida não se aplica" in ve.observacao
    assert len(vr) == 1 and vr[0].Sd == pytest.approx(20.0) and vr[0].Rd == pytest.approx(60.23, rel=0.005)
    assert "barras de ponta" in vr[0].observacao and r.dados["N_t_ponta"] == 20.0
    assert r.razao == pytest.approx(20.0 / 60.23, rel=0.005)
    # sem tração nas pontas: só o escoamento
    r0 = tesouras.verificar_barra(ue, "ASTM A572 Gr.50", 0.0, 40.0, 0.0, 150.0, 150.0, 1,
                                  "Banzo inferior", [], Nt_ponta=0.0)
    assert not any(v.titulo.startswith("Tração — ruptura") for v in r0.verificacoes)
    # diagonal (Nt_ponta None): a ruptura com o Nt inteiro
    rd = tesouras.verificar_barra(ue, "ASTM A572 Gr.50", 0.0, 40.0, 0.0, 150.0, 150.0, 1, "Diagonal", [])
    assert next(v for v in rd.verificacoes if v.titulo.startswith("Tração — ruptura")).Sd == pytest.approx(40.0)


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
    # N1/N11 (14/10): a tração passou a verificar a ruptura da seção líquida só nas barras
    # com ponta ligada (diagonais, montantes e as pontas dos banzos: apoio e emenda da
    # cumeeira) e o passo do travamento do banzo inferior é o mais aberto que deixa passar o
    # perfil mais leve (antes o laço engrossava o banzo para não fechar a malha). Com isso o
    # trapezoidal-Howe, que antes só fechava com banzos duplos (banzo inferior
    # Ue 200×75×25×4,75 a 1,03), fecha com Ue simples (Ue 150×75×20×3,00 a 0,92), e os quatro
    # casos fecham sem banzos duplos
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


def test_analise_3d_carrega_o_galpao_gerado():
    """A análise 3D só põe telha, sobrecarga e vento no banzo de cima marcado (papel_trelica) e só
    prende na terça a barra de papel "corrente": o galpão gerado não tinha nenhum dos dois — a
    análise acusava mecanismo, ou, pelo Lançar estrutura, calculava sem carga e dava 22 % de uso
    (verde falso). Análise de 20/10, caso do projeto "Fabrica" (20×40, Pratt, V0 45)."""
    from nucleo3d import analise_estrutural as AE
    from nucleo3d import de_projeto
    d = _dados(comprimento=20.0, diagonais_tesoura="Pratt", v0=45.0)
    p = galpao.dimensionar(d)
    doc = de_projeto.modelo_do_galpao(p)
    correntes = [b for b in doc.barras if (b.atributos or {}).get("marca") == "TC"]
    assert correntes and all(b.papel == "corrente" for b in correntes)
    sup = [b for b in doc.barras if (b.atributos or {}).get("papel_trelica") == "banzo_sup"]
    assert len({b.atributos["origem_2d"] for b in sup}) == p.dados.n_porticos
    r = AE.calcular(doc, {"base": "engastada", "telha": 0.105, "sobrecarga": p.cargas["sobrecarga"],
                          "v0": d.v0, "categoria": "II", "classe": "B", "modelo_vento": "fechado"})
    assert not r["instavel"]
    assert not any("não tem banzo superior" in a for a in r["avisos"])
    # carregado de verdade: o banzo de cima trabalha (o cálculo do galpão dá ~98 %; sem carga dava ~0)
    uso_sup = max(pc["uso"] for pc in r["verificacao"]["pecas"] if pc.get("papel") == "banzo_sup")
    assert uso_sup > 0.5, uso_sup


def test_terca_escora_do_contraventamento_e_x_nas_linhas_de_terca():
    """A terça na linha do nó do X da cobertura é montante da treliça de contraventamento: na
    análise 3D do 20×40 (V0 45) dava 160 % com N = 24 kN e o cálculo nunca a verificava à
    compressão. Agora: flexo-compressão (NBR 14762, 9.9); quando a terça comum não passa, só
    essas terças, nos vãos contraventados, ganham perfil próprio (T2), no cálculo, na lista e
    no 3D — e o X do 3D cai nas linhas de terça (caía entre elas)."""
    from nucleo3d import de_projeto
    p = galpao.dimensionar(_dados(diagonais_tesoura="Pratt", v0=45.0))
    terca, esc = p.elemento("Terça"), p.elemento("Terça-escora do contraventamento")
    assert terca.esforcos["N_escora_kN"] > 20.0
    assert esc is not None and esc.ok and esc.perfil != terca.perfil
    assert any("Flexo-compressão" in v.titulo for v in esc.resultado.verificacoes)
    lista = {x.marca: x.quantidade for x in p.lista_material}
    assert lista["T2"] == esc.geometria["quantidade"]
    assert lista["T1"] + lista["T2"] == terca.geometria["linhas"] * 2 * (p.dados.n_porticos - 1)
    doc = de_projeto.modelo_do_galpao(p)
    t2 = [b for b in doc.barras if b.atributos.get("marca") == "T2"]
    assert len(t2) == lista["T2"] and all(b.perfil == esc.perfil for b in t2)
    meia = de_projeto._Construtor(p, True, True)._ys_tercas()[0]
    ys_terca = {round(y) for y in meia} | {round(20000 - y) for y in meia}
    nos_x = {round(b.inicio[1]) for b in doc.barras if b.atributos.get("marca") == "CC"}
    assert nos_x - {0, 20000} <= ys_terca


def test_vento_na_faixa_de_parede_acima_do_pilar():
    """Tesoura apoiada: a parede sobe do topo do pilar ao beiral (a altura da tesoura no apoio),
    e o vento dessa faixa não entrava no pórtico — o momento na base saía ~20 % menor que na
    análise 3D (94,6 × 113,7 kN·m no 20×40)."""
    from nucleo import analise
    p = galpao.dimensionar(_dados(diagonais_tesoura="Pratt", v0=45.0))
    h = galpao.faixa_acima_do_pilar(p.dados)
    assert h > 0.5
    modelo = p.esforcos["modelo"]
    nodais = [c for nome, cs in modelo.casos.items() if nome.startswith("Vcpi") for c in cs
              if getattr(c, "tipo", "") == "nodal" and abs(getattr(c, "Fx", 0.0)) > 0]
    assert len(nodais) >= 2
    assert galpao.faixa_acima_do_pilar(_dados(ligacao_tesoura="rígida")) == 0.0


def test_terca_assentada_no_banzo_de_cima():
    """O 3D da tesoura assentava a terça e a telha pela altura do W de referência da viga (W 360
    no galpão de 20 m): a terça ficava ~75 mm acima do banzo."""
    import math
    from nucleo3d import de_projeto
    from saida import desenhos as dsn
    p = galpao.dimensionar(_dados())
    doc = de_projeto.modelo_do_galpao(p)
    d_bs = dsn._perfil(p.elemento("Banzo superior da tesoura").perfil).d
    d_t = dsn._perfil(p.elemento("Terça").perfil).d
    g = de_projeto._Construtor(p, True, True)
    for t in [b for b in doc.barras if b.papel == "terça" and b.atributos.get("agua") == 1][:5]:
        y, z = t.inicio[1], t.inicio[2]
        # distância ao eixo da água (z = hb + i·y), perpendicular a ele
        dist = (z - g.hb - g.i * y) / math.sqrt(1 + g.i ** 2)
        assert abs(dist - (d_bs / 2 + d_t / 2)) < 2.0, (dist, d_bs, d_t)


def test_x_vertical_sobe_ate_o_beiral_na_tesoura_apoiada():
    """Na tesoura apoiada o X da cobertura fica no banzo de cima (o beiral, 0,8 m acima do pilar),
    mas o X das paredes acabava no topo do pilar: a força longitudinal descia dobrando o montante de
    apoio no eixo fraco — na análise 3D do 20×40, deslocabilidade grande (Δ2/Δ1 = 1,44). O X
    vertical vai até o beiral, no cálculo (comprimento) e no 3D."""
    import math
    from nucleo3d import analise_estrutural as AE
    from nucleo3d import de_projeto
    d = _dados(diagonais_tesoura="Pratt", v0=45.0)
    p = galpao.dimensionar(d)
    cv = p.elemento("Contraventamento vertical")
    assert abs(cv.geometria["comprimento_m"] - math.hypot(p.dados.espacamento_porticos, p.dados.altura_beiral)) < 0.01
    doc = de_projeto.modelo_do_galpao(p)
    topo = max(max(b.inicio[2], b.fim[2]) for b in doc.barras if b.atributos.get("marca") == "CV")
    assert abs(topo - p.dados.altura_beiral * 1000.0) < 1.0
    r = AE.calcular(doc, {"base": "engastada", "telha": 0.105, "sobrecarga": p.cargas["sobrecarga"],
                          "v0": d.v0, "categoria": "II", "classe": "B", "modelo_vento": "fechado"})
    assert r["segunda_ordem"]["resumo"]["razao_max"] < 1.4


def _analise_3d(p, d, base):
    from nucleo3d import analise_estrutural as AE
    from nucleo3d import de_projeto
    doc = de_projeto.modelo_do_galpao(p)
    r = AE.calcular(doc, {"base": base, "telha": 0.105, "sobrecarga": p.cargas["sobrecarga"],
                          "v0": d.v0, "categoria": "II", "classe": "B", "modelo_vento": "fechado"})
    usos = {}
    for pc in r["verificacao"]["pecas"]:
        usos[pc.get("marca")] = max(usos.get(pc.get("marca"), 0.0), pc.get("uso") or 0.0)
    return doc, r, usos


def test_oitao_apoiado_vira_viga_de_oitao():
    """O oitão não tinha estrutura: a análise 3D jogava o vento dele no pilar de canto. Agora pilaretes
    nas linhas do X da cobertura e longarinas de oitão. Com o topo do pilarete apoiado (à escolha,
    usuário 20/10), a viga de oitão substitui a tesoura das pontas e o pilarete leva o peso dela."""
    d = _dados(diagonais_tesoura="Pratt", v0=45.0, topo_pilar_oitao="apoiado")
    p = galpao.dimensionar(d)
    po, vo = p.elemento("Pilar de oitão"), p.elemento("Viga de oitão")
    assert po is not None and vo is not None and po.esforcos["topo"] == "apoiado" and po.esforcos["N_kN"] > 0
    lista = {x.marca: x.quantidade for x in p.lista_material}
    assert lista["VO"] == 4 and lista["P2"] == 4 and lista.get("LO")
    doc, r, usos = _analise_3d(p, d, "engastada")
    tesouras = {b.atributos.get("origem_2d") for b in doc.barras if b.atributos.get("papel_trelica")}
    assert len(tesouras) == p.dados.n_porticos - 2
    assert sum(1 for b in doc.barras if b.atributos.get("marca") == "VO") == 4
    # as linhas de travamento do banzo de baixo do vão da ponta se ancoram no pilarete de oitão e, por cima,
    # na viga de oitão (o triângulo no plano vertical): só com a de baixo, Δ2/Δ1 = 2,13 no 3D; com as duas, ~1,46
    tv_ponta = [b for b in doc.barras if b.atributos.get("marca") == "TV" and min(b.inicio[0], b.fim[0]) < 1.0]
    assert tv_ponta
    assert sum(1 for b in doc.barras if b.atributos.get("elemento") == "Ancoragem do travamento do banzo inferior")         == lista["TVA"]
    assert r["segunda_ordem"]["resumo"]["razao_max"] < 1.6
    assert not r["instavel"] and usos["PO"] < 1.1 and usos["VO"] < 1.1, usos


def test_oitao_solto_e_o_padrao_do_alma_cheia():
    """Por padrão a ponta fica igual aos outros pórticos e o topo do pilarete é solto
    na vertical (furo oblongo): na análise 3D o trecho de cima fica sem rigidez axial — passa o vento,
    não o peso. Com a ligação curta que se tentou antes, Δ2/Δ1 ia a 9."""
    from nucleo.modelo_galpao import DadosGalpao
    d = DadosGalpao(comprimento=40.0)
    p = galpao.dimensionar(d)
    po = p.elemento("Pilar de oitão")
    assert po.esforcos["topo"] == "solto" and p.elemento("Viga de oitão") is None
    doc, r, usos = _analise_3d(p, d, "articulada")
    pos = [b for b in doc.barras if b.atributos.get("marca") == "PO"]
    assert pos and all(b.atributos.get("topo_oblongo") for b in pos)
    assert sum(1 for b in doc.barras if b.papel == "viga") == 2 * p.dados.n_porticos
    # com a escora de beiral, 1,20 (sem ela, 1,42; com a ligação curta que se tentou antes, 9)
    assert r["segunda_ordem"]["resumo"]["razao_max"] < 1.4
    assert usos["PO"] < 1.1, usos


def test_topo_do_pilar_de_oitao_a_escolha():
    import pytest
    from nucleo.base import ErroDeDados
    from nucleo.modelo_galpao import DadosGalpao
    assert galpao.dimensionar(DadosGalpao(topo_pilar_oitao="apoiado")).elemento("Viga de oitão") is not None
    assert galpao.dimensionar(_dados(topo_pilar_oitao="solto")).elemento("Viga de oitão") is None
    # o padrão é solto nos dois tipos
    assert galpao.dimensionar(_dados()).elemento("Viga de oitão") is None
    assert galpao.dimensionar(_dados()).elemento("Pilar de oitão").esforcos["topo"] == "solto"
    with pytest.raises(ErroDeDados, match="oitão"):
        DadosGalpao(topo_pilar_oitao="pendurado").validar()


def test_maos_francesas_da_viga_de_alma_cheia():
    """A viga de alma cheia sob sucção é verificada com a mesa de baixo travada a cada vão/4 (até 3 m) por
    mãos-francesas que não existiam no 3D nem na lista (usuário, 20/10: gerar). Agora estão nos dois, nos
    pórticos internos, da mesa de baixo à terça; a análise 3D não as põe na linha pelo eixo."""
    from nucleo.modelo_galpao import DadosGalpao
    from nucleo3d import de_projeto
    from nucleo3d.analitico import _linhas_do
    p = galpao.dimensionar(DadosGalpao(comprimento=40.0))
    mf = p.elemento("Mão-francesa da viga")
    assert mf is not None and mf.ok and mf.geometria["Lb_m"] <= 3.0
    lista = {x.marca: x.quantidade for x in p.lista_material}
    doc = de_projeto.modelo_do_galpao(p)
    no_3d = [b for b in doc.barras if b.atributos.get("marca") == "MF"]
    assert lista["MF"] == mf.geometria["quantidade"] == len(no_3d)
    assert all(b.papel == "mão-francesa" for b in no_3d)
    assert not any(ln["papel"] == "mão-francesa" for ln in _linhas_do(doc))


def test_longarina_da_ponta_leva_a_reacao_do_pilar_de_canto():
    """A longarina lateral dos vãos das pontas leva, comprimida, a reação do pilar de canto (que dobra no
    eixo fraco com o vento do oitão) — na análise 3D do 20×40, 8,6 kN e 113 %; o cálculo só a verificava à
    flexão. Agora flexo-compressão (NBR 14762, 9.9) e, se a comum não passa, perfil próprio nesses vãos (L2)."""
    from nucleo.modelo_galpao import DadosGalpao
    from nucleo3d import de_projeto
    p = galpao.dimensionar(DadosGalpao(comprimento=40.0))
    lg, l2 = p.elemento("Longarina"), p.elemento("Longarina dos vãos das pontas")
    assert 7.0 < lg.esforcos["N_ponta_kN"] < 10.0
    assert l2 is not None and l2.ok and any("Flexo-compressão" in v.titulo for v in l2.resultado.verificacoes)
    lista = {x.marca: x.quantidade for x in p.lista_material}
    assert lista["L1"] + lista["L2"] == lg.geometria["fiadas_por_lado"] * 2 * (p.dados.n_porticos - 1)
    doc = de_projeto.modelo_do_galpao(p)
    no_3d = [b for b in doc.barras if b.atributos.get("marca") == "L2"]
    assert len(no_3d) == lista["L2"] and {b.atributos["vao"] for b in no_3d} == {1, p.dados.n_porticos - 1}


def test_longarinas_com_o_peso_do_fechamento():
    """A verificação da terça reaproveitada para a parede não tinha o peso do fechamento no eixo fraco
    (inclinação 0): a longarina de oitão ia a 145 % na análise 3D por ele. Agora flexão oblíqua (9.8.2.5)."""
    from nucleo.modelo_galpao import DadosGalpao
    for d in (DadosGalpao(comprimento=40.0), _dados(diagonais_tesoura="Pratt", v0=45.0)):
        p = galpao.dimensionar(d)
        for nome in ("Longarina", "Longarina de oitão"):
            e = p.elemento(nome)
            v = [x for x in e.resultado.verificacoes if x.titulo.startswith("Flexão oblíqua — vento")]
            assert v and v[0].ok, (nome, e.perfil)


def test_longarina_de_oitao_com_folga_e_correntes_aos_montantes():
    """A longarina de oitão virava tirante entre os montantes quando o pórtico da ponta abre e fecha com o
    vento (26 kN, 227 % na análise 3D): ligações com furo oblongo ao longo dela. E as correntes dela, presas
    na viga da ponta, eram puxadas quando o vento levanta o telhado: agora terminam em tirantes inclinados
    até os montantes vizinhos (pilarete ou pilar de canto)."""
    from nucleo.modelo_galpao import DadosGalpao
    d = DadosGalpao(comprimento=40.0)
    p = galpao.dimensionar(d)
    doc, r, usos = _analise_3d(p, d, "articulada")
    lo = [b for b in doc.barras if b.atributos.get("marca") == "LO"]
    assert lo and all(b.atributos.get("folga_axial") for b in lo)
    assert any(b.atributos.get("elemento") == "Tirante da corrente de oitão" for b in doc.barras)
    assert usos["LO"] < 1.1 and usos["L1"] < 1.1 and usos.get("L2", 0) < 1.1, usos


def test_x_vertical_em_paineis_no_galpao_alto():
    """Com pé-direito de 10–12 m o tirante do X vertical não cabia nem com ø32 e o galpão saía reprovado
    (achado 18 da análise de 20/10). Agora o X vai em painéis na altura, com escora em tubo nos nós."""
    from nucleo.modelo_galpao import DadosGalpao
    from nucleo3d import de_projeto
    p = galpao.dimensionar(DadosGalpao(vao=30.0, pe_direito=10.0))
    cv, ev = p.elemento("Contraventamento vertical"), p.elemento("Escora do contraventamento vertical")
    assert cv.ok and cv.geometria["paineis_verticais"] >= 2
    assert ev is not None and ev.ok
    lista = {x.marca: x.quantidade for x in p.lista_material}
    doc = de_projeto.modelo_do_galpao(p)
    assert sum(1 for b in doc.barras if b.atributos.get("marca") == "CV") == lista["CV"]
    assert sum(1 for b in doc.barras if b.atributos.get("marca") == "EV") == lista["EV"]
    assert galpao.dimensionar(DadosGalpao()).elemento("Contraventamento vertical").geometria["paineis_verticais"] == 1


def test_escora_de_beiral():
    """Sem escora de beiral a força longitudinal de cada pórtico ia ao X pelas terças e longarinas, flexíveis
    nessa direção: na análise 3D do 20×40 de alma cheia, Δ2/Δ1 = 1,42 (com ela, 1,20)."""
    from nucleo.modelo_galpao import DadosGalpao
    d = DadosGalpao(comprimento=40.0)
    p = galpao.dimensionar(d)
    eb = p.elemento("Escora de beiral")
    assert eb is not None and eb.ok
    lista = {x.marca: x.quantidade for x in p.lista_material}
    doc, r, usos = _analise_3d(p, d, "articulada")
    assert sum(1 for b in doc.barras if b.atributos.get("marca") == "EB") == lista["EB"] == 2 * (p.dados.n_porticos - 1)
    assert r["segunda_ordem"]["resumo"]["razao_max"] < 1.3 and not r["segunda_ordem"]["resumo"]["instaveis"]
    assert max(usos.values()) < 1.0, usos
