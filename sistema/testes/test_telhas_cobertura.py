# -*- coding: utf-8 -*-
"""As telhas lançadas em cima das terças (nucleo3d/telhas_cobertura.py, 12/10/2026)."""
import pytest

from nucleo3d.modelo import Barra, Documento
from nucleo3d import telhas_cobertura as T

PERFIL = "U 100×40×2,65 (FF)"


def _terca(doc, x, z, sigla, y0=0.0, y1=6000.0):
    b = Barra(inicio=(x, y0, z), fim=(x, y1, z), perfil=PERFIL, papel="terça", camada="Terças")
    b.atributos = {"origem": {"sigla": sigla}}
    doc.add(b)
    return b


def _agua(doc, x0, n, z0, inclinacao, passo=1400.0, sigla="TC1"):
    for i in range(n):
        _terca(doc, x0 + i * passo, z0 + i * passo * inclinacao, sigla)


def test_agua_reta_de_5_por_cento():
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    r = T.lancar(doc)
    assert r["panos"] == 5
    assert r["fora_do_plano"] == []
    assert [a["caida_pct"] for a in r["aguas"]] == [5.0]
    # a área: 5 vãos de 1,4 m (inclinados) por 6 m
    assert abs(r["area_m2"] - 5 * 1.4017 * 6.0) < 0.1
    # as chapas no sentido da caída: 6 m ao longo das terças / 1.020 mm = 6 chapas, cada uma da primeira à última terça
    chapas = [s for s in doc.solidos if s.camada == "Telhas"]
    assert r["chapas"] == 6 and len(chapas) == 6
    for ch in chapas:
        xs = [round(v[0], 3) for v in ch.vertices]
        assert min(xs) == 0.0 and max(xs) == 7000.0                    # desce a água inteira (x 0 → 7.000)
        assert max(v[1] for v in ch.vertices) - min(v[1] for v in ch.vertices) <= 1020.0 + 1
    assert abs(sum(max(v[1] for v in c.vertices) - min(v[1] for v in c.vertices) for c in chapas) - 6000.0) < 1


def test_terca_erguida_no_meio_da_agua():
    doc = Documento()
    _agua(doc, 0.0, 7, 7000.0, 0.05)
    alta = [b for b in doc.barras if abs(b.inicio[0] - 4200.0) < 1][0]
    alta.inicio = (alta.inicio[0], alta.inicio[1], alta.inicio[2] + 80.0)
    alta.fim = (alta.fim[0], alta.fim[1], alta.fim[2] + 80.0)
    r = T.lancar(doc)
    assert len(r["fora_do_plano"]) == 1
    assert 70 <= r["fora_do_plano"][0]["desvio"] <= 90


def test_calha_terca_baixa_e_transicao_no_meio():
    """duas águas que descem para uma calha (a transição em x 7000): a telha não passa por cima dela, e a terça da
    água da direita, encostada na calha 100 mm abaixo do plano dela, é apontada"""
    doc = Documento()
    _agua(doc, 1400.0, 4, 7000.0 + 4 * 1400 * 0.05, -0.05)                  # 1400…5600, descendo até a calha
    _terca(doc, 7100.0, 7000.0 - 0.05 * 100 - 100.0 + 5.0, "TC2")          # junto da calha, 100 mm abaixo
    _agua(doc, 8500.0, 4, 7000.0 + 0.05 * 1500, 0.05, sigla="TC2")         # 8500…12700, subindo
    for z in (6000.0, 6900.0):
        tr = Barra(inicio=(7000.0, -500.0, z), fim=(7000.0, 6500.0, z), perfil="U 150×70×4,75 (FF)", papel="banzo", camada="Treliças")
        tr.atributos = {"origem": {"planta": "TRANSIÇÃO 1", "peca": "TRANSIÇÃO 1#1"}}
        doc.add(tr)
    r = T.lancar(doc)
    # nenhum pano entre x 5600 e 7100 (por cima da transição)
    entre = [s for s in doc.solidos if s.camada == "Telhas" and min(v[0] for v in s.vertices) < 7000 < max(v[0] for v in s.vertices)]
    assert entre == []
    baixas = [f for f in r["fora_do_plano"] if f["sigla"] == "TC2" and abs(f["ponto"][0] - 7100) < 1]
    assert baixas and -110 <= baixas[0]["desvio"] <= -90


def test_relancar_tira_os_panos_anteriores():
    doc = Documento()
    _agua(doc, 0.0, 4, 7000.0, 0.05)
    T.lancar(doc)
    T.lancar(doc)
    assert len([s for s in doc.solidos if (s.atributos or {}).get("telha_lancada")]) == 6     # 6 chapas de 1,02 m


def _tesoura(doc, y, z, x0=-500.0, x1=14000.0, nome="TESOURA 1"):
    """o banzo de cima de uma tesoura atravessada (ao longo de x), com o topo em z"""
    b = Barra(inicio=(x0, y, z - 20.0), fim=(x1, y, z - 20.0), perfil="U 100×40×2,25 (FF)", papel="banzo", camada="Treliças", rotacao=90.0)
    b.atributos = {"origem": {"planta": nome, "peca": nome + "#1"}}
    doc.add(b)
    return b


def test_terca_da_calha_sobe_ao_plano_com_suporte():
    """a água sobe 5 % a partir da calha (a transição em x 7000); a terça da calha corre em cima da transição, sentada
    nela, 100 mm abaixo do plano — sobe, e os suportes de terça vão em cima do banzo da transição"""
    doc = Documento()
    _agua(doc, 8500.0, 5, 7100.0, 0.05, sigla="TC2")
    lo, hi = T._ext_z(Barra(inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=PERFIL))
    z_plano = 7100.0 - 0.05 * 1400 + hi                       # o topo da terça em x 7100 no plano da água
    baixa = _terca(doc, 7100.0, z_plano - 100.0 - hi, "TC2")
    tr = Barra(inicio=(7000.0, -500.0, 0), fim=(7000.0, 6500.0, 0), perfil="U 150×70×4,75 (FF)", papel="banzo", camada="Treliças")
    _lo_t, hi_t = T._ext_z(tr)
    z_tr = baixa.inicio[2] + lo - hi_t                          # o topo da transição no fundo da terça
    tr.inicio, tr.fim = (7000.0, -500.0, z_tr), (7000.0, 6500.0, z_tr)
    tr.atributos = {"origem": {"planta": "TRANSIÇÃO 1", "peca": "TRANSIÇÃO 1#1"}}
    doc.add(tr)
    tercas = [b for b in doc.barras if b.papel == "terça"]
    r = T.alinhar_tercas(tercas, doc.barras)
    assert len(r["calha"]) == 1 and 95 <= r["calha"][0]["mm"] <= 105
    assert abs(baixa.inicio[2] + hi - z_plano) < 5
    assert len(r["suportes"]) >= 2
    for a, b, apoio in r["suportes"]:
        assert apoio == "TRANSIÇÃO 1" and 95 <= b[2] - a[2] <= 105
    assert T.lancar(doc)["fora_do_plano"] == []


def test_terca_torta_fica_nivelada_no_apoio():
    """as vizinhas niveladas; a do meio sobe 200 mm de uma ponta à outra, apoiada só na tesoura de y 0"""
    doc = Documento()
    _tesoura(doc, 0.0, 7000.0 + 0.05 * 1400 * 0)               # a tesoura de y 0 (topo a 7000 em x 0, plana para o teste)
    for i in range(5):
        x = i * 1400.0
        z = 7000.0
        lo, _hi = T._ext_z(Barra(inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=PERFIL))
        b = _terca(doc, x, z - lo, "TC%d" % (i + 1))
        if i == 2:
            b.fim = (b.fim[0], b.fim[1], b.fim[2] + 200.0)
    torta = [b for b in doc.barras if b.papel == "terça" and abs(b.inicio[0] - 2800.0) < 1][0]
    r = T.alinhar_tercas([b for b in doc.barras if b.papel == "terça"], doc.barras)
    assert [t["sigla"] for t in r["tortas"]] == ["TC3"]
    assert abs(torta.fim[2] - torta.inicio[2]) < 1


def test_terca_baixa_no_meio_da_agua_fica_como_esta():
    """a terça 80 mm abaixo no meio de uma água reta, sentada na tesoura que passa: é apontamento, não se mexe"""
    doc = Documento()
    _agua(doc, 0.0, 7, 7000.0, 0.05)
    baixa = [b for b in doc.barras if abs(b.inicio[0] - 4200.0) < 1][0]
    baixa.inicio = (baixa.inicio[0], baixa.inicio[1], baixa.inicio[2] - 80.0)
    baixa.fim = (baixa.fim[0], baixa.fim[1], baixa.fim[2] - 80.0)
    lo, _hi = T._ext_z(baixa)
    _tesoura(doc, 3000.0, baixa.inicio[2] + lo, x0=-500.0, x1=9000.0)
    z0 = baixa.inicio[2]
    r = T.alinhar_tercas([b for b in doc.barras if b.papel == "terça"], doc.barras)
    assert r["calha"] == [] and baixa.inicio[2] == z0
    assert any(abs(f["desvio"] + 80) <= 10 for f in T.lancar(doc)["fora_do_plano"])


def test_ondas_da_chapa_no_sentido_da_caida():
    """a chapa tem as ondas da TP 40 (40 mm, 4 por 1.020 mm) correndo na caída: em cada terça o mesmo perfil"""
    doc = Documento()
    _agua(doc, 0.0, 3, 7000.0, 0.05)
    T.lancar(doc)
    ch = [s for s in doc.solidos if s.camada == "Telhas"][0]
    em_x0 = sorted(v for v in ch.vertices if abs(v[0]) < 0.01)
    alturas = sorted({round(v[2] - min(z[2] for z in em_x0)) for v in em_x0})
    assert alturas[-1] - alturas[1] == 40                               # a crista da onda 40 mm acima da chapa
    cristas = [v for v in em_x0 if round(v[2] - min(z[2] for z in em_x0)) == alturas[-1]]
    assert len(cristas) == 8                                            # 4 ondas, 2 pontos na crista de cada


def test_calha_no_vale_em_v():
    """duas águas de 5 % descem até a mesma terça (x 4200): a calha ao longo dela"""
    doc = Documento()
    for i in range(7):
        x = i * 1400.0
        _terca(doc, x, 7000.0 + abs(x - 4200.0) * 0.05, "TC%d" % (i + 1))
    r = T.lancar(doc)
    assert r["calhas_vale"] == 1
    calha = [s for s in doc.solidos if s.camada == "Calhas"][0]
    # 17/10: centrada na terça, 150 de afastamento entre as telhas + 100 de cobrimento de cada lado = 350 mm, e por baixo
    # da ponta das telhas (antes: 300 mm, 50 mm por cima da telha)
    assert min(v[0] for v in calha.vertices) == pytest.approx(4200.0 - 175.0, abs=1)
    assert max(v[0] for v in calha.vertices) == pytest.approx(4200.0 + 175.0, abs=1)
    telhas = _telhado(doc)
    pontas = [v for s in telhas for v in s.vertices if 3900.0 < v[0] < 4500.0]
    assert pontas and all(abs(v[0] - 4200.0) >= 75.0 - 1 for v in pontas)  # as telhas param a 75 mm do eixo
    assert max(v[2] for v in calha.vertices) < min(v[2] for v in pontas)


def _ext(doc, direcao):
    """quanto os banzos da treliça se estendem do eixo na direção (a face em que a telha encosta)"""
    from nucleo3d.regras_trelica import _extensao
    return max(_extensao(b, direcao) for b in doc.barras if b.papel == "banzo")


def test_fechamento_duplo_no_painel():
    """o painel da testeira em x −200 (banzos a 6,00 e 7,60), o telhado à direita dele: a TP 40 em pé nas duas faces"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    for z in (6000.0, 7600.0):
        b = Barra(inicio=(-200.0, 0.0, z), fim=(-200.0, 6000.0, z), perfil="U 100×40×2,25 (FF)", papel="banzo", camada="Treliças")
        b.atributos = {"origem": {"planta": "PAINEL 1", "peca": "PAINEL 1#1"}}
        doc.add(b)
    r = T.lancar(doc)
    fech = [s for s in doc.solidos if (s.atributos or {}).get("fechamento")]
    # o fechamento é duplo: 6 m de painel / 1.020 mm = 6 chapas em cada face
    assert r["fechamentos"] == 12 and len(fech) == 12
    fora = [f for f in fech if f.atributos["face"] == "fora"]
    dentro = [f for f in fech if f.atributos["face"] == "dentro"]
    assert len(fora) == 6 and len(dentro) == 6
    ext_f, ext_d = _ext(doc, (-1.0, 0.0, 0.0)), _ext(doc, (1.0, 0.0, 0.0))
    for f in fora:
        assert max(v[0] for v in f.vertices) <= -200.0 - ext_f + 0.5     # do lado de fora (sem telhado)
    for f in dentro:
        assert min(v[0] for v in f.vertices) >= -200.0 + ext_d - 0.5     # do lado do telhado
    for f in fech:
        assert min(v[2] for v in f.vertices) <= 5950.0 and max(v[2] for v in f.vertices) >= 7650.0


import pytest  # noqa: E402


@pytest.mark.parametrize("peca,esperado", [("P.3#1", 12), ("VT.1", 12), ("T.7#1", 0), ("MT.2#38800", 0)])
def test_fechamento_na_platibanda_com_os_nomes_da_regra(peca, esperado):
    """Mercado Hermes, 19/10 ("precisamos lançar as telhas"): as platibandas com os nomes da regra 7 das tesouras (P.n,
    VT.n) não ganhavam fechamento nenhum — o gerador só conhecia os nomes do Posto (PAINEL, TRANSIÇÃO…). A tesoura (T.n,
    MT.n) no perímetro fica de fora: no Mercado ela encosta no fechamento ou na parede de concreto"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    for z in (6000.0, 7600.0):
        b = Barra(inicio=(-200.0, 0.0, z), fim=(-200.0, 6000.0, z), perfil="U 100×40×2,25 (FF)", papel="banzo", camada="Treliças")
        b.atributos = {"origem": {"peca": peca}, "conjunto": peca}
        doc.add(b)
    r = T.lancar(doc)
    assert r["fechamentos"] == esperado


def test_telha_segue_sob_o_telhado_de_cima():
    """a água de baixo acaba numa terça a 0,44 m de outra 4 m acima: a telha de baixo segue até 50 mm antes dela"""
    doc = Documento()
    _agua(doc, 0.0, 4, 7000.0, 0.05)
    _terca(doc, -440.0, 11000.0, "TC9")
    _terca(doc, -1600.0, 11000.0, "TC9")
    T.lancar(doc)
    baixas = [s for s in doc.solidos if s.camada == "Telhas" and max(v[2] for v in s.vertices) < 9000]
    assert min(min(v[0] for v in s.vertices) for s in baixas) <= -380.0


def test_borda_escalonada_vira_chapa_recortada():
    """a terça de cima acaba 2 m antes da de baixo (a borda diagonal): a ponta é coberta por chapas recortadas na diagonal,
    com as ondas, em vez de uma placa lisa"""
    doc = Documento()
    _terca(doc, 0.0, 7000.0, "TC1", y1=6000.0)
    _terca(doc, 1400.0, 7070.0, "TC2", y1=4000.0)
    r = T.lancar(doc)
    assert r["recortes"] >= 2
    rec = [s for s in doc.solidos if (s.atributos or {}).get("recorte")]
    assert rec and all(min(v[1] for v in s.vertices) >= 4000.0 - 1 for s in rec)

def test_telha_ao_lado_aponta_o_degrau_e_a_dobra():
    """a telha ao lado (12/10): na água reta nada; com a terça do meio 50 mm acima da reta das vizinhas num pedaço
    dela, a chapa dobra ali (50 mm) e a do lado, que passa pelo pedaço certo, fica num degrau"""
    doc = Documento()
    _agua(doc, 0.0, 5, 7000.0, 0.05)
    assert T.lancar(doc)["ao_lado"] == []
    doc = Documento()
    for i in range(5):
        x, z = i * 1400.0, 7000.0 + i * 1400.0 * 0.05
        if i == 2:
            _terca(doc, x, z + 50.0, "TC1", 0.0, 3060.0)
            _terca(doc, x, z, "TC1", 3060.0, 6000.0)
        else:
            _terca(doc, x, z, "TC1")
    r = T.lancar(doc)
    dobras = [a for a in r["ao_lado"] if a["tipo"] == "dobra"]
    degraus = [a for a in r["ao_lado"] if a["tipo"] == "degrau"]
    assert dobras and 40 <= abs(dobras[0]["mm"]) <= 60 and abs(dobras[0]["ponto"][0] - 2800) < 5
    assert degraus and 40 <= abs(degraus[0]["mm"]) <= 60

# ------------------------------------------------------------------ a cobertura do Posto CB revista pelo 3D (17/10/2026)
def _banzo(doc, a, b, nome, perfil="U 150×70×4,75 (FF)"):
    tr = Barra(inicio=a, fim=b, perfil=perfil, papel="banzo", camada="Treliças")
    tr.atributos = {"origem": {"planta": nome, "peca": nome + "#1"}}
    doc.add(tr)
    return tr


def _telhado(doc):
    return [s for s in doc.solidos if s.camada == "Telhas" and not (s.atributos or {}).get("fechamento")]


def test_borda_escalonada_pela_linha_emendada():
    """a terça de baixo emendada no apoio bem onde a de cima acaba (a linha x 30,13 do Posto, partida na tesoura de y 11,45,
    junto da TRANSIÇÃO 16): a borda vai até a ponta da LINHA — com a ponta do pedaço, o triângulo não saía e a telha parava
    em degraus de até 1,3 m da borda"""
    doc = Documento()
    _terca(doc, 0.0, 7000.0, "TC1", y1=2000.0)
    _terca(doc, 0.0, 7000.0, "TC1", y0=2000.0, y1=6000.0)
    _terca(doc, 1400.0, 7070.0, "TC2", y0=2000.0, y1=6000.0)
    r = T.lancar(doc)
    rec = [s for s in doc.solidos if (s.atributos or {}).get("recorte")]
    assert r["recortes"] >= 2 and rec
    assert min(min(v[1] for v in s.vertices) for s in rec) <= 1.0      # a borda chega na ponta da linha (y 0)


def test_telha_ate_a_face_da_parede_diagonal():
    """a última terça antes da parede em diagonal, sem terça do outro lado (a x 35,34 do Posto, junto da TRANSIÇÃO 16 e da
    TRANSIÇÃO 1): a telha segue em chapas recortadas até 100 mm da face; antes ficava o triângulo aberto (até 1,25 m)"""
    doc = Documento()
    _agua(doc, 0.0, 3, 7000.0, 0.05)
    _banzo(doc, (2900.0, 0.0, 8000.0), (4400.0, 6000.0, 8000.0), "TRANSIÇÃO 9")
    T.lancar(doc)

    def face(y):
        return 2900.0 + 1500.0 * y / 6000.0
    alem = [s for s in _telhado(doc) if max(v[0] for v in s.vertices) > 3300.0]
    assert alem, "a telha não passou da última terça (x 2800)"
    for s in _telhado(doc):
        for v in s.vertices:
            assert v[0] <= face(v[1]) + 1.0                             # nada passa da parede
    # a parede paralela mais perto (a TRELIÇA 6 do Posto, a borda do telhado ao lado da TRANSIÇÃO 16) segura a telha
    doc2 = Documento()
    _agua(doc2, 0.0, 3, 7000.0, 0.05)
    _banzo(doc2, (2900.0, 0.0, 8000.0), (4400.0, 6000.0, 8000.0), "TRANSIÇÃO 9")
    _banzo(doc2, (3000.0, 0.0, 7600.0), (3000.0, 6000.0, 7600.0), "TRELIÇA 6", perfil="U 100×40×2,25 (FF)")
    T.lancar(doc2)
    assert not [s for s in _telhado(doc2) if max(v[0] for v in s.vertices) > 2850.0]


def test_linha_da_calha_emendada_sobe_inteira():
    """a terça da calha emendada (a x 34,06 do Posto): o pedaço da ponta, ao lado da água, sobe ao plano; o resto da
    linha, fora de qualquer água, subia nada — a telha fazia um degrau de 133 mm na emenda. A linha sobe inteira"""
    doc = Documento()
    for i in range(5):
        x = 8500.0 + i * 1400.0
        _terca(doc, x, 7100.0 + i * 1400.0 * 0.05, "TC2", y1=700.0)
    lo, hi = T._ext_z(Barra(inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=PERFIL))
    z_plano = 7100.0 - 0.05 * 1400 + hi
    ponta = _terca(doc, 7100.0, z_plano - 100.0 - hi, "TC2", y1=700.0)
    resto = _terca(doc, 7100.0, z_plano - 100.0 - hi, "TC2", y0=700.0, y1=6000.0)
    tr = Barra(inicio=(7000.0, -500.0, 0), fim=(7000.0, 6500.0, 0), perfil="U 150×70×4,75 (FF)", papel="banzo", camada="Treliças")
    _lo_t, hi_t = T._ext_z(tr)
    z_tr = ponta.inicio[2] + lo - hi_t
    tr.inicio, tr.fim = (7000.0, -500.0, z_tr), (7000.0, 6500.0, z_tr)
    tr.atributos = {"origem": {"planta": "TRANSIÇÃO 8", "peca": "TRANSIÇÃO 8#1"}}
    doc.add(tr)
    z0 = resto.inicio[2]
    T.alinhar_tercas([b for b in doc.barras if b.papel == "terça"], doc.barras)
    assert abs(ponta.inicio[2] + hi - z_plano) < 5
    assert abs(resto.inicio[2] - ponta.inicio[2]) < 2 and abs(resto.fim[2] - ponta.fim[2]) < 2 and resto.inicio[2] > z0 + 90


def test_linha_emendada_nao_sobe_para_dentro_de_outra_peca():
    """a mesma linha, mas com uma peça em pé atravessando o resto dela logo acima (os montantes da tesoura de cima da
    TRANSIÇÃO 3 do Posto, na linha da calha ao norte da TRANSIÇÃO 1): subir a poria dentro da peça — fica, e a conferência
    aponta o degrau"""
    doc = Documento()
    for i in range(5):
        x = 8500.0 + i * 1400.0
        _terca(doc, x, 7100.0 + i * 1400.0 * 0.05, "TC2", y1=700.0)
    lo, hi = T._ext_z(Barra(inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=PERFIL))
    z_plano = 7100.0 - 0.05 * 1400 + hi
    ponta = _terca(doc, 7100.0, z_plano - 100.0 - hi, "TC2", y1=700.0)
    resto = _terca(doc, 7100.0, z_plano - 100.0 - hi, "TC2", y0=700.0, y1=6000.0)
    tr = Barra(inicio=(7000.0, -500.0, 0), fim=(7000.0, 6500.0, 0), perfil="U 150×70×4,75 (FF)", papel="banzo", camada="Treliças")
    _lo_t, hi_t = T._ext_z(tr)
    z_tr = ponta.inicio[2] + lo - hi_t
    tr.inicio, tr.fim = (7000.0, -500.0, z_tr), (7000.0, 6500.0, z_tr)
    tr.atributos = {"origem": {"planta": "TRANSIÇÃO 3", "peca": "TRANSIÇÃO 3#1"}}
    doc.add(tr)
    z0 = resto.inicio[2]
    for y in (2000.0, 3500.0, 5000.0):                           # os montantes: do pé da terça até 1,4 m acima
        m = Barra(inicio=(7100.0, y, z0 - 70.0), fim=(7100.0, y, z0 + 1400.0), perfil="L 2\"×3/16\"", papel="montante", camada="Treliças")
        m.atributos = {"origem": {"planta": "TRANSIÇÃO 3 (tesoura de cima)", "peca": "TRANSIÇÃO 3 (tesoura de cima)#1"}}
        doc.add(m)
    T.alinhar_tercas([b for b in doc.barras if b.papel == "terça"], doc.barras)
    assert resto.inicio[2] == z0


def test_trelica_acima_da_telha_no_meio_do_telhado_e_revestida():
    """a treliça com telhado dos dois lados e o banzo de cima 0,4 m acima da telha (a TRANSIÇÃO 1 do Posto; as tesouras
    de cima das TRANSIÇÕES 2/3/5/6): o corte BB manda "REVESTIR … COM TELHA OU RUFO" e "RUFO MOLDURA" no topo — a telha em
    pé nas duas faces, da telha até o topo, e o rufo; antes ficava a treliça pelada atravessando a telha"""
    doc = Documento()
    for i in range(5):
        _terca(doc, i * 1400.0, 7000.0 + i * 1400.0 * 0.05, "TC1", y0=-3000.0, y1=3000.0)
    _banzo(doc, (-500.0, 0.0, 6000.0), (6100.0, 0.0, 6000.0), "TRANSIÇÃO 1")
    _banzo(doc, (-500.0, 0.0, 7800.0), (6100.0, 0.0, 7800.0), "TRANSIÇÃO 1")
    r = T.lancar(doc)
    rev = [s for s in doc.solidos if (s.atributos or {}).get("revestimento")]
    assert r["revestimentos"] == len(rev) >= 2
    assert {v[1] > 0 for s in rev for v in s.vertices} == {True, False}      # nas duas faces
    for s in rev:
        assert max(v[2] for v in s.vertices) > 7800.0 and min(v[2] for v in s.vertices) > 7000.0
    rufo = [s for s in doc.solidos if (s.atributos or {}).get("rufo_lancado")]
    assert rufo and 5000.0 <= r["rufo_ml"] * 1000.0 <= 6600.0
    # o banzo de baixo (sob a telha) e uma tesoura comum (o topo sob a telha) não ganham nada
    doc2 = Documento()
    for i in range(5):
        _terca(doc2, i * 1400.0, 7000.0 + i * 1400.0 * 0.05, "TC1", y0=-3000.0, y1=3000.0)
    _tesoura(doc2, 0.0, 6990.0, x0=-500.0, x1=6100.0)
    assert T.lancar(doc2)["revestimentos"] == 0


# ------------------------------------------------------------------ a calha em todo encontro das águas baixas (17/10)
def test_vale_com_a_terca_do_fundo_baixa_ao_lado_ganha_calha():
    """a terça do fundo 100 mm abaixo da vizinha a 0,45 m (a linha x 10,06 do Posto): antes, nem vale de duas terças (o
    vão entre elas não era plano) nem V (vizinha a menos de 1 m) — a linha inteira sem calha. Agora: a calha centrada no
    vão, 350 mm, as telhas a 150 mm uma da outra e por cima dela"""
    doc = Documento()
    for i in range(4):                                         # a água da esquerda desce 5 % até x 4200
        _terca(doc, i * 1400.0, 7210.0 - i * 1400.0 * 0.05, "TC1")
    _terca(doc, 4650.0, 7000.0 - 100.0, "TC2")                  # a do fundo, 0,45 m adiante e 100 mm abaixo
    for i in range(4):                                         # a da direita sobe 5 % a partir de x 6050
        _terca(doc, 6050.0 + i * 1400.0, 6990.0 + i * 1400.0 * 0.05, "TC3")
    T.lancar(doc)
    calhas = [s for s in doc.solidos if s.camada == "Calhas"]
    assert calhas, "o vale ficou sem calha"
    xs = [v[0] for s in calhas for v in s.vertices]
    assert max(xs) - min(xs) == pytest.approx(350.0, abs=2) and (min(xs) + max(xs)) / 2 == pytest.approx(4425.0, abs=2)
    esq = max(v[0] for s in _telhado(doc) for v in s.vertices if v[0] < 4425.0)
    dir_ = min(v[0] for s in _telhado(doc) for v in s.vertices if v[0] > 4425.0)
    assert dir_ - esq == pytest.approx(150.0, abs=2)               # o afastamento entre as telhas
    assert esq - min(xs) >= 99.0 and max(xs) - dir_ >= 99.0         # o cobrimento de cada lado
    assert max(v[2] for s in calhas for v in s.vertices) < 7000.0 - 100.0 + 60.0


def test_calha_da_parede_por_baixo_da_ponta_da_telha():
    """a água desce até a parede (o frontão da TRANSIÇÃO 3 do Posto, na linha da calha): a telha para a 100 mm da face e a
    calha fica encostada na parede, por baixo da ponta da telha (antes: 50 mm por cima da telha)"""
    doc = Documento()
    for i in range(4):
        _terca(doc, i * 1400.0, 7210.0 - i * 1400.0 * 0.05, "TC1")
    _banzo(doc, (5000.0, -500.0, 8000.0), (5000.0, 6500.0, 8000.0), "TRANSIÇÃO 3 (tesoura de cima)")
    for i in range(3):
        _terca(doc, 5800.0 + i * 1400.0, 7000.0 + i * 1400.0 * 0.05, "TC2")
    T.lancar(doc)
    calhas = [s for s in doc.solidos if s.camada == "Calhas" and max(v[0] for v in s.vertices) < 5000.0]
    assert calhas
    ponta = max(v[0] for s in _telhado(doc) for v in s.vertices if v[0] < 5000.0)
    z_ponta = min(v[2] for s in _telhado(doc) for v in s.vertices if abs(v[0] - ponta) < 1.0)
    c = calhas[0]
    assert max(v[0] for v in c.vertices) > ponta + 50.0              # a calha vai além da ponta da telha, até a parede
    assert min(v[0] for v in c.vertices) <= ponta - 99.0             # e entra 100 mm por baixo dela
    assert max(v[2] for v in c.vertices) < z_ponta


def test_terca_baixa_no_meio_da_agua_nao_vira_calha():
    """o par da cumeeira com uma das terças 85 mm abaixo (x 42,07 do Posto): as águas não descem até ela — não é vale, não
    leva calha (fica o apontamento da telha ao lado)"""
    doc = Documento()
    xs = [0.0, 1280.0, 2560.0, 2910.0, 4190.0, 5470.0]
    zs = [7150.0, 7214.0, 7279.0, 7195.0, 7214.0, 7148.0]
    for x, z in zip(xs, zs):
        _terca(doc, x, z, "TC1")
    T.lancar(doc)
    assert not [s for s in doc.solidos if s.camada == "Calhas"]


def _painel(doc, peca, x=-200.0, zs=(6000.0, 7600.0)):
    for z in zs:
        b = Barra(inicio=(x, 0.0, z), fim=(x, 6000.0, z), perfil="U 100×40×2,25 (FF)", papel="banzo", camada="Platibanda")
        b.atributos = {"origem": {"peca": peca}, "conjunto": peca}
        doc.add(b)


@pytest.mark.parametrize("z_baixo,esperado", [(5900.0, 12), (6900.0, 0)])
def test_fechamento_no_degrau_entre_dois_telhados(z_baixo, esperado):
    """Mercado Hermes, 19/10 ("faltou fechamento em telha nesses espaços"): a platibanda com telhado dos dois lados em
    planta — o de cima do lado de dentro e o de baixo (o anexo, a faixa norte) no pé dela — ficava sem fechamento, como se
    estivesse no meio do telhado. O de baixo no pé (5,90 com o banzo de baixo a 6,00) é o lado de fora; com a telha dos
    dois lados acima do banzo de baixo (6,90) a treliça atravessa o telhado e segue sem (é o revestimento)"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    _agua(doc, -6200.0, 5, z_baixo, 0.0, sigla="TC7")             # o telhado de baixo, à esquerda, até x −600
    _painel(doc, "P.5")
    r = T.lancar(doc)
    assert r["fechamentos"] == esperado
    fora = [s for s in doc.solidos if (s.atributos or {}).get("face") == "fora"]
    assert len(fora) == esperado // 2
    for f in fora:
        assert max(v[0] for v in f.vertices) <= -200.0 - _ext(doc, (-1.0, 0.0, 0.0)) + 0.5    # a do telhado de baixo


@pytest.mark.parametrize("peca,esperado", [("P.13", 12), ("PAINEL 3", 0)])
def test_platibanda_sem_telhado_de_lado_nenhum(peca, esperado):
    """Mercado Hermes, 19/10: a faixa em volta do terraço (P.13, P.14) não tem telhado de lado nenhum e ficava sem
    fechamento. A P.n (platibanda/fechamento pela regra 7) fecha, com o lado de fora o mais longe da obra; o painel do
    Posto sem telhado continua de fora"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    _painel(doc, peca, x=-5000.0)
    r = T.lancar(doc)
    assert r["fechamentos"] == esperado
    for f in [s for s in doc.solidos if (s.atributos or {}).get("face") == "fora"]:
        assert max(v[0] for v in f.vertices) <= -5000.0 - _ext(doc, (-1.0, 0.0, 0.0)) + 0.5   # para fora da obra


def test_fechamento_encosta_na_face_da_trelica():
    """Mercado Hermes, 19/10 ("veja porque os fechamentos laterais estão ficando afastados da estrutura"): a telha do
    fechamento ficava a 110 mm do eixo da treliça em qualquer perfil — 60 mm de folga na U 100×50. Agora o fundo da onda
    encosta na face das barras, dos dois lados"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    for z in (6000.0, 7600.0):
        b = Barra(inicio=(-200.0, 0.0, z), fim=(-200.0, 6000.0, z), perfil="U 100×50×3,00 (FF)", papel="banzo",
                  camada="Platibanda", rotacao=270.0)
        b.atributos = {"origem": {"peca": "P.1"}, "conjunto": "P.1"}
        doc.add(b)
    T.lancar(doc)
    fech = [s for s in doc.solidos if (s.atributos or {}).get("fechamento")]
    assert fech
    for f in fech:
        if f.atributos["face"] == "fora":
            assert max(v[0] for v in f.vertices) == pytest.approx(-200.0 - _ext(doc, (-1.0, 0.0, 0.0)), abs=0.5)
        else:
            assert min(v[0] for v in f.vertices) == pytest.approx(-200.0 + _ext(doc, (1.0, 0.0, 0.0)), abs=0.5)


@pytest.mark.parametrize("acima,por_cima", [(0.0, True), (1000.0, False)])
def test_telha_passa_por_cima_do_fechamento_na_linha_dela(acima, por_cima):
    """Mercado Hermes, 19/10, o degrau da ala para o galpão ("essa passa por cima da lateral externa", "essa não tem"): a
    treliça de fechamento logo depois da última terça, com o topo na linha da telha, ficava com a faixa aberta entre a
    terça e ela e o fechamento subindo até a telha. Agora a telha segue por cima da treliça e passa da telha de fora
    (a onda e 50 mm), e o fechamento para embaixo dela. A platibanda que sobe acima da telha continua como era"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)                              # sobe até x 7000 (a última terça)
    from nucleo3d.telhas_cobertura import _topo_da_terca
    t = [b for b in doc.barras if abs(b.inicio[0] - 7000.0) < 1][0]
    x_f = 7322.0
    plano = t.inicio[2] + _topo_da_terca(t) + 0.05 * (x_f - 7000.0)   # a linha da telha no eixo da treliça
    topo = Barra(inicio=(x_f, 0.0, 0.0), fim=(x_f, 6000.0, 0.0), perfil="U 100×50×3,00 (FF)", papel="banzo",
                 camada="Platibanda", rotacao=270.0)
    z_sup = plano + acima - T._ext_z(topo)[1]
    for z in (z_sup - 1100.0, z_sup):
        # 5 mm além da ponta das terças (a P.15 do Mercado vai até a face do pilar, a terça para antes)
        b = Barra(inicio=(x_f, 0.0, z), fim=(x_f, 6005.0, z), perfil="U 100×50×3,00 (FF)", papel="banzo",
                  camada="Platibanda", rotacao=270.0)
        b.atributos = {"origem": {"peca": "P.15"}, "conjunto": "P.15"}
        doc.add(b)
    T.lancar(doc)
    telhado = [s for s in doc.solidos if (s.atributos or {}).get("telha_lancada") and not s.atributos.get("fechamento")]
    fora = [s for s in doc.solidos if (s.atributos or {}).get("face") == "fora"]
    x_max = max(v[0] for s in telhado for v in s.vertices)
    x_fora = max(v[0] for s in fora for v in s.vertices)          # a crista da onda do fechamento de fora
    if por_cima:
        assert x_max >= x_fora + 40.0                             # passa da telha de fora
        z_fundo = min(v[2] for s in telhado for v in s.vertices if v[0] > x_f - 1.0)
        assert max(v[2] for s in fora for v in s.vertices) <= z_fundo + 1.0     # o fechamento para embaixo dela
    else:
        assert x_max <= 7000.0 + 1.0                              # a telha para na última terça, como antes


def _platibanda(doc, x, z_inf, z_sup, peca="P.1"):
    for z in (z_inf, z_sup):
        b = Barra(inicio=(x, 0.0, z), fim=(x, 6000.0, z), perfil="U 100×50×3,00 (FF)", papel="banzo", camada="Platibanda",
                  rotacao=270.0)
        b.atributos = {"origem": {"peca": peca}, "conjunto": peca}
        doc.add(b)


def test_calha_da_parede_na_borda_baixa_contra_a_platibanda():
    """Mercado Hermes, 19/10 ("pode lançar as calhas e rufos"): a água que desce para a platibanda P.n no fim do telhado
    não tinha calha (o gerador só conhecia a parede do Posto, a transição entre duas terças). Agora a telha para a 100 mm
    da telha de dentro do fechamento e a calha fica encostada nele, por baixo da ponta da telha; o contra-rufo do
    fechamento entra nela e o topo leva o rufo capa"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0 + 5 * 1400 * 0.05, -0.05)           # desce até x 7000
    _platibanda(doc, 7550.0, 6400.0, 7900.0)
    r = T.lancar(doc)
    assert r["calhas_parede"] >= 1
    calha = [s for s in doc.solidos if s.camada == "Calhas"]
    assert calha
    face = 7550.0 - T._afastamento_das_faces(doc)("P.1", (-1.0, 0.0)) - 46.0      # a crista da telha de dentro
    assert max(v[0] for c in calha for v in c.vertices) == pytest.approx(face, abs=1)
    telhado = [s for s in doc.solidos if (s.atributos or {}).get("telha_lancada") and not s.atributos.get("fechamento")]
    assert max(v[0] for s in telhado for v in s.vertices) == pytest.approx(face - 100.0, abs=1)
    rufos = {(s.atributos or {}).get("rufo") for s in doc.solidos if (s.atributos or {}).get("rufo_lancado")}
    assert {"capa", "contra-rufo"} <= rufos


@pytest.mark.parametrize("caso,esperado", [("encosta", "encosto"), ("degrau", "encosto")])
def test_rufos_do_fechamento(caso, esperado):
    """Mercado Hermes, 19/10: o encosto onde a telha do telhado encosta na platibanda (a água sobe até ela, o topo 1 m
    acima). No degrau (a P.5 sobre o anexo, a P.15 sobre a calha) o fechamento de fora acabava no banzo de baixo e uma
    chapa alta fechava até o telhado de baixo — "aqui não vai calha, será puxado a telha", "baixar a telha e reduzir o
    tamanho": agora a telha de fora desce até 50 mm da crista da telha de baixo e o pé leva o encosto"""
    doc = Documento()
    if caso == "encosta":
        _agua(doc, 0.0, 6, 7000.0, 0.05)                          # sobe até x 7000 (7350)
        _platibanda(doc, 7300.0, 6800.0, 8400.0)
    else:
        _agua(doc, 0.0, 6, 7000.0, 0.05)
        _agua(doc, -6200.0, 5, 5500.0, 0.0, sigla="TC7")           # o telhado de baixo, 1 m abaixo do pé do fechamento
        _platibanda(doc, -200.0, 6600.0, 7600.0, peca="P.5")
    T.lancar(doc)
    rufos = [s for s in doc.solidos if (s.atributos or {}).get("rufo") == esperado]
    assert rufos
    assert all(s.camada == "Rufos" and s.atributos["corte"] % 50 == 0 for s in rufos)
    assert not any((s.atributos or {}).get("rufo") == "pingadeira" for s in doc.solidos)
    if caso == "degrau":
        fora = [s for s in doc.solidos if (s.atributos or {}).get("face") == "fora"]
        crista = 5500.0 + T._topo_da_terca(doc.barras[-3]) + 46.0          # a telha de baixo (o fundo + a onda)
        assert min(v[2] for s in fora for v in s.vertices) == pytest.approx(crista + 50.0, abs=2.0)


def _platibanda_em_x(doc, y, z_inf, z_sup, partes=3, x0=0.0, x1=7000.0, peca="P.2"):
    """a platibanda ao longo de x (o lado da água), com os banzos em `partes` barras"""
    for z in (z_inf, z_sup):
        for k in range(partes):
            xa, xb = x0 + (x1 - x0) * k / partes, x0 + (x1 - x0) * (k + 1) / partes
            b = Barra(inicio=(xa, y, z), fim=(xb, y, z), perfil="U 100×50×3,00 (FF)", papel="banzo", camada="Platibanda",
                      rotacao=270.0)
            b.atributos = {"origem": {"peca": peca}, "conjunto": peca}
            doc.add(b)


def test_rufo_acompanha_a_telha_e_e_uma_peca_so():
    """Mercado Hermes, 19/10 ("os rufos laterais da doca ficaram picotados, precisam ser uma peça só", "o rufo deve
    acompanhar a telha"): na platibanda ao longo da água o encosto ficava na altura do meio de cada barra do banzo —
    degraus, um pedaço por barra. Agora a altura vai nas pontas de cada trecho e os trechos seguidos viram uma peça"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)                              # sobe 350 mm de x 0 a 7000
    _platibanda_em_x(doc, -200.0, 6600.0, 8600.0)
    T.lancar(doc)
    enc = [s for s in doc.solidos if (s.atributos or {}).get("rufo") == "encosto"]
    assert len(enc) == 1
    vs = enc[0].vertices
    z_em = lambda x: min(v[2] for v in vs if abs(v[0] - x) < 1.0)
    assert z_em(7000.0) - z_em(0.0) == pytest.approx(350.0, abs=5.0)
    assert enc[0].atributos["comprimento"] == 7000


def test_capa_e_encosto_inteiros_perto_do_topo():
    """Mercado Hermes, 19/10 ("as peças de rufo/calhas devem ser peças inteiriças, não deve ser feita essa quebra em
    peças menores/picadas"): onde a telha chegava perto do topo a capa virava "capa com encosto" e o lado saía em
    pedaços de tipos diferentes. Agora o lado tem uma capa inteira e um encosto inteiro, que para na capa"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.0)
    _platibanda_em_x(doc, -200.0, 6500.0, 7300.0)
    T.lancar(doc)
    rufos = [s for s in doc.solidos if (s.atributos or {}).get("rufo_lancado")]
    assert sorted(s.nome.split(" (")[0] for s in rufos) == ["Rufo capa", "Rufo de encosto"]
    capa = [s for s in rufos if s.atributos["rufo"] == "capa"][0]
    enc = [s for s in rufos if s.atributos["rufo"] == "encosto"][0]
    assert max(v[2] for v in enc.vertices) <= max(v[2] for v in capa.vertices) + 1.0


def test_rufo_segue_a_telha_com_a_platibanda_passando_do_telhado():
    """Mercado Hermes, 19/10 ("quando a cobertura tem uma inclinação o rufo deve seguir a inclinação da telha", "uma
    beirada do rufo ficou acima"): a platibanda vai além do telhado nas duas pontas; a altura do rufo vinha das pontas da
    barra e, com elas fora do telhado, do meio — o rufo ficava reto. Agora é lida ao longo dele"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)                              # sobe 350 mm de x 0 a 7000
    _platibanda_em_x(doc, -200.0, 6600.0, 8600.0, partes=1, x0=-1500.0, x1=8500.0)
    T.lancar(doc)
    enc = [s for s in doc.solidos if (s.atributos or {}).get("rufo") == "encosto"]
    assert len(enc) == 1
    vs = enc[0].vertices
    xs = sorted({round(v[0]) for v in vs})
    z_em = lambda x: min(v[2] for v in vs if abs(v[0] - x) < 1.0)
    inclinacao = (z_em(xs[-1]) - z_em(xs[0])) / (xs[-1] - xs[0])
    assert inclinacao == pytest.approx(0.05, abs=0.005)


def test_contra_rufo_sobe_acima_da_telha_e_calha_inteira():
    """Mercado Hermes, 19/10 ("na caixa d'água o rufo ficou embaixo da telha"): o contra-rufo parava 150 mm acima da
    calha, embaixo da ponta da telha; agora sobe RUFO_ENCOSTO acima da crista dela. E as terças partidas em duas (uma
    calha por pedaço de terça) dão uma calha só ("as peças de rufo/calhas devem ser peças inteiriças")"""
    doc = Documento()
    for i in range(6):
        x = i * 1400.0
        for y0, y1 in ((0.0, 3000.0), (3000.0, 6000.0)):
            _terca(doc, x, 7000.0 + 5 * 1400 * 0.05 - x * 0.05, "TC1", y0=y0, y1=y1)
    _platibanda(doc, 7550.0, 6400.0, 7900.0)
    T.lancar(doc)
    calhas = [s for s in doc.solidos if s.camada == "Calhas"]
    assert len(calhas) == 1
    telhado = [s for s in doc.solidos if (s.atributos or {}).get("telha_lancada") and not s.atributos.get("fechamento")]
    crista = max(v[2] for s in telhado for v in s.vertices if v[0] > 6900.0)
    cr = [s for s in doc.solidos if (s.atributos or {}).get("rufo") == "contra-rufo"]
    assert cr and max(v[2] for v in cr[0].vertices) >= crista + 100.0


def test_calha_aberta_em_cima():
    """Mercado Hermes, 19/10 ("ficou um tubo fechado"): a calha era uma caixa fechada; agora o fundo e as duas abas"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0 + 5 * 1400 * 0.05, -0.05)
    _platibanda(doc, 7550.0, 6400.0, 7900.0)
    T.lancar(doc)
    for c in [s for s in doc.solidos if s.camada == "Calhas"]:
        topo = max(v[2] for v in c.vertices)
        xs = [v[0] for v in c.vertices]
        no_alto = [v[0] for v in c.vertices if v[2] > topo - 1.0]
        assert all(min(abs(x - min(xs)), abs(x - max(xs))) <= T.CALHA_ESP + 0.5 for x in no_alto)


def test_capas_em_meia_esquadria_no_canto():
    """Mercado Hermes, 19/10 (a conferência do modelo): nas quinas a capa de cada lado corria até o eixo da outra treliça e
    as abas atravessavam ela (P.13 × P.14, P.12 × P.10/P.11, P.9 × P.3/P.6). Agora as duas vão até o encontro dos eixos e
    terminam em meia-esquadria: nenhuma chapa da capa de um lado entra na outra treliça"""
    doc = Documento()
    _agua(doc, 0.0, 6, 7000.0, 0.05)
    for peca, a, b in (("P.1", (-200.0, -200.0), (-200.0, 6000.0)), ("P.2", (-200.0, -200.0), (7000.0, -200.0))):
        for z in (6600.0, 8600.0):
            br = Barra(inicio=(a[0], a[1], z), fim=(b[0], b[1], z), perfil="U 100×50×3,00 (FF)", papel="banzo",
                       camada="Platibanda", rotacao=270.0)
            br.atributos = {"origem": {"peca": peca}, "conjunto": peca}
            doc.add(br)
    T.lancar(doc)
    capas = {s.atributos["painel"]: s for s in doc.solidos if (s.atributos or {}).get("rufo") == "capa"}
    assert set(capas) == {"P.1", "P.2"} and all(s.atributos.get("cantos") == 1 for s in capas.values())
    # a capa da P.1 (ao longo de y): do lado de dentro (x > −150) não passa da face de dentro da P.2 (y −150)
    assert all(v[1] >= -150.0 - 1.0 for v in capas["P.1"].vertices if v[0] > -150.0)
    assert all(v[0] >= -150.0 - 1.0 for v in capas["P.2"].vertices if v[1] > -150.0)



# ------------------------------------------------------------------ Posto V2 (21/10/2026): o telhamento redondo
def _cobertura_em_planta(doc):
    """a união das chapas de telha em planta (shapely)"""
    from shapely.geometry import MultiPoint
    from shapely.ops import unary_union
    return unary_union([MultiPoint([v[:2] for v in s.vertices]).convex_hull for s in _telhado(doc)])


def test_sem_fresta_onde_as_pontas_das_tercas_quase_coincidem():
    """As pontas das terças vizinhas emendadas na mesma tesoura caem a poucos cm umas das outras (Posto V2: y 33,20, 39,03,
    48,41…): o trecho curto entre elas era pulado e ficava a fresta na água inteira ("frestas entre telhas")."""
    doc = Documento()
    for i, x in enumerate((0.0, 1400.0, 2800.0)):
        dy = (0.0, 25.0, -20.0)[i]                         # a emenda de cada linha 2–2,5 cm deslocada
        _terca(doc, x, 7000.0 + 0.05 * x, "TC1", 0.0, 3000.0 + dy)
        _terca(doc, x, 7000.0 + 0.05 * x, "TC2", 3000.0 + dy, 6000.0)
    T.lancar(doc)
    from shapely.geometry import box
    falta = box(100.0, 50.0, 2700.0, 5950.0).difference(_cobertura_em_planta(doc))
    assert falta.area < 1.0, "fresta de %.0f mm² entre as chapas" % falta.area


def test_telha_passa_por_cima_da_terca_cortada_pela_trelica_de_baixo():
    """A treliça que passa por baixo da telha corta a linha de terça (a PAINEL 12 do Posto em x 19,87: 90 mm sem terça):
    a telha continua por cima do vão; antes, a faixa sem telha de uma ponta à outra da água."""
    doc = Documento()
    for x in (0.0, 1400.0, 2800.0):
        z = 7000.0 + 0.05 * x
        if x == 1400.0:
            _terca(doc, x, z, "TC1", 0.0, 2955.0)
            _terca(doc, x, z, "TC1", 3045.0, 6000.0)        # 90 mm sem terça
        else:
            _terca(doc, x, z, "TC1")
    T.lancar(doc)
    from shapely.geometry import box
    falta = box(100.0, 50.0, 2700.0, 5950.0).difference(_cobertura_em_planta(doc))
    assert falta.area < 1.0, "a faixa sem telha sobre o vão da terça (%.0f mm²)" % falta.area


def test_telha_ate_a_platibanda_quase_paralela_com_terca_junto():
    """A platibanda reta 9,6° fora da direção das terças (a PAINEL 12 da abertura oval do Posto) era tomada por paralela e a
    telha parava na última terça; e onde ela fica a mais de 1,6 m da última terça, a terça inclinada que corre junto dela
    apoia a ponta — a telha vai até 100 mm da face. Sem a terça junto, além de 1,6 m não vai (a faixa sem terça fica de
    apontamento)."""
    import math
    def montar(com_terca_junto):
        doc = Documento()
        _agua(doc, 0.0, 3, 7000.0, 0.05)                                      # terças em x 0, 1400, 2800 (y 0–6000)
        ang = math.radians(9.6)
        a, b = (3000.0, 0.0), (3000.0 + 6000.0 * math.tan(ang), 6000.0)      # a face vai de 0,2 a 1,2 m da última terça
        _banzo(doc, (a[0], a[1], 7600.0), (b[0], b[1], 7600.0), "PAINEL 12")
        if com_terca_junto:
            t = Barra(inicio=(a[0] - 250.0, 0.0, 7150.0), fim=(b[0] - 250.0, 6000.0, 7150.0), perfil=PERFIL, papel="terça", camada="Terças")
            t.atributos = {"origem": {"sigla": "TC13"}}
            doc.add(t)
        T.lancar(doc)
        return doc, a, b
    doc, a, b = montar(False)
    face = lambda y: a[0] + (b[0] - a[0]) * y / 6000.0
    assert max(v[0] for s in _telhado(doc) for v in s.vertices) > 3300.0, "a telha parou na última terça"
    for s_ in _telhado(doc):
        for v in s_.vertices:
            assert v[0] <= face(v[1]) + 1.0                                   # nada passa da face
    # mais longe (a 1,9–2,4 m): só com a terça junto da platibanda
    def longe(com):
        doc = Documento()
        _agua(doc, 0.0, 3, 7000.0, 0.05)
        _banzo(doc, (4700.0, 0.0, 7600.0), (5200.0, 6000.0, 7600.0), "PAINEL 12")
        if com:
            t = Barra(inicio=(4450.0, 0.0, 7150.0), fim=(4950.0, 6000.0, 7150.0), perfil=PERFIL, papel="terça", camada="Terças")
            t.atributos = {"origem": {"sigla": "TC13"}}
            doc.add(t)
        T.lancar(doc)
        return max(v[0] for s in _telhado(doc) for v in s.vertices)
    assert longe(True) > 4300.0 and longe(False) < 2900.0


def test_chapa_reta_por_cima_da_terca_fora_da_reta():
    """A terça 80 mm abaixo da reta no meio da água partia a chapa (a dobra de mais de 4 %) e a telha descia até ela —
    o "trecho caído" do Posto V2. A telha é reta: passa na reta da água, inteira, e a terça fica apontada (fora do plano;
    a conferência da telha ao lado continua acusando a dobra, pela telha assentada nas terças)."""
    doc = Documento()
    _agua(doc, 0.0, 7, 7000.0, 0.05)
    baixa = [b for b in doc.barras if abs(b.inicio[0] - 4200.0) < 1][0]
    baixa.inicio = (baixa.inicio[0], baixa.inicio[1], baixa.inicio[2] - 80.0)
    baixa.fim = (baixa.fim[0], baixa.fim[1], baixa.fim[2] - 80.0)
    r = T.lancar(doc)
    assert len(r["fora_do_plano"]) == 1 and r["endireitadas"] >= 1
    assert any(a["tipo"] == "dobra" for a in r["ao_lado"])
    for s_ in _telhado(doc):
        xs = [v[0] for v in s_.vertices]
        assert min(xs) < 1.0 and max(xs) > 8399.0                           # a chapa inteira, sem partir na terça baixa
        for v in s_.vertices:
            reta = 7000.0 + 0.05 * v[0] + T._topo_da_terca(baixa)
            assert v[2] >= reta - 5.0                                         # nada desce da reta



def test_telha_ate_a_platibanda_curva():
    """A platibanda curva (o banzo calandrado dos PAINÉIS 8, 9, 10, 20 e 21 do Posto, um sólido com o eixo guardado) não
    contava como parede: a telha parava na última terça e ficavam as falhas nas bordas curvas (usuário, 21/10, vista de
    cima). Agora a telha vai até 100 mm da face, em pedaços que acompanham a curva."""
    import math
    from nucleo3d.modelo import Solido
    doc = Documento()
    _agua(doc, 0.0, 3, 7000.0, 0.05)                                         # x 0, 1400, 2800 (y 0–6000)
    R, cx, cy = 6000.0, -2000.0, 3000.0                                        # o arco: x = cx + √(R² − (y − cy)²)
    eixo = [[cx + R * math.cos(a), cy + R * math.sin(a), 7600.0] for a in [math.radians(-40 + 2 * k) for k in range(41)]]
    sol = Solido(nome="U 100×40×2,25 (FF)", camada="Treliças", vertices=[tuple(v) for v in eixo], faces=[])
    sol.atributos = {"banzo": {"perfil": "U 100×40×2,25 (FF)", "rotacao": 270.0, "eixo": eixo},
                     "origem": {"planta": "PAINEL 20", "peca": "PAINEL 20#1"}, "calandrada": {"raio": R}}
    doc.add(sol)
    T.lancar(doc)
    curva = lambda y: cx + math.sqrt(max(0.0, R * R - (y - cy) ** 2))
    tel = _telhado(doc)
    assert max(v[0] for s_ in tel for v in s_.vertices) > curva(3000.0) - 400.0, "a telha não chegou na platibanda curva"
    for s_ in tel:
        for v in s_.vertices:
            assert v[0] <= curva(v[1]) + 1.0                                  # nada passa da curva


def test_telha_ate_a_telha_vizinha_de_outra_direcao():
    """Sem parede no caminho (a PAINEL 12 do Posto desce abaixo da telha no norte da abertura oval), entre a última terça e
    a telha que já chega pelo outro lado — de outra direção de terças — ficava o triângulo sem telha. Agora a telha vai até
    ela, passando 100 mm por baixo."""
    doc = Documento()
    for x in (0.0, 1400.0):                                                    # a água A: terças em y, x 0 e 1400
        _terca(doc, x, 7000.0 + 0.05 * x, "TC1", 0.0, 3000.0)
    for y in (0.0, 1400.0, 2800.0):                                            # a água B: terças em x, de 2900 a 6000
        b = Barra(inicio=(2900.0, y, 7070.0), fim=(6000.0, y, 7070.0), perfil=PERFIL, papel="terça", camada="Terças")
        b.atributos = {"origem": {"sigla": "TC2"}}
        doc.add(b)
    T.lancar(doc)
    from shapely.geometry import box
    falta = box(100.0, 100.0, 2850.0, 2700.0).difference(_cobertura_em_planta(doc))
    assert falta.area < 1.0, "o vão entre as duas telhas ficou sem telha (%.0f mm²)" % falta.area


def test_uma_chapa_por_faixa_com_as_tercas_emendadas_em_estacoes_diferentes():
    """A telha do projeto vai inteira da calha até a cumeeira (a paginação do Posto V2, folha 12: 341 telhas). As linhas de
    terça emendadas em tesouras diferentes (a estação de uma a 2,5 m, da outra a 3,3 m) e o beiral que começa noutra
    estação partiam a faixa em duas ou três chapas, e o beiral sobre a calha virava uma tira de 150 mm sozinha (350 no
    Posto V2: 174 das telhas do projetista saíam partidas)."""
    doc = Documento()
    for i in range(4):
        x, z = i * 1400.0, 7210.0 - i * 1400.0 * 0.05
        if i == 1:
            _terca(doc, x, z, "TC1", 0.0, 3300.0)
            _terca(doc, x, z, "TC1", 3300.0, 6000.0)
        elif i == 3:
            _terca(doc, x, z, "TC1", 0.0, 2500.0)
            _terca(doc, x, z, "TC1", 2500.0, 6000.0)
        else:
            _terca(doc, x, z, "TC1")
    _banzo(doc, (5000.0, -500.0, 8000.0), (5000.0, 6500.0, 8000.0), "TRANSIÇÃO 3 (tesoura de cima)")
    for i in range(3):
        _terca(doc, 5800.0 + i * 1400.0, 7000.0 + i * 1400.0 * 0.05, "TC2")
    T.lancar(doc)
    chapas = [s for s in _telhado(doc) if max(v[0] for v in s.vertices) < 5000.0]
    assert len(chapas) == 6, "a água de 6 m em %d chapas (6 faixas de 1.020 mm)" % len(chapas)
    for s in chapas:
        xs = [v[0] for v in s.vertices]
        assert min(xs) < 1.0 and max(xs) > 4700.0, "a chapa de x %.0f a %.0f: não vai da primeira terça até o beiral" % (min(xs), max(xs))


def test_recorte_na_ponta_da_chapa_e_a_mesma_telha():
    """A telha que chega na parede diagonal é uma telha só, cortada na diagonal (a paginação do Posto V2, folha 12: a
    fileira da borda é uma telha do comprimento até a parede). O recorte saía como peça à parte na ponta da chapa — duas
    telhas na lista para cada fileira da borda."""
    doc = Documento()
    _agua(doc, 0.0, 3, 7000.0, 0.05)
    _banzo(doc, (2900.0, 0.0, 8000.0), (4400.0, 6000.0, 8000.0), "TRANSIÇÃO 9")
    r = T.lancar(doc)
    chapas = _telhado(doc)
    assert len(chapas) == 6, "6 faixas em %d peças" % len(chapas)
    for s in chapas:
        assert min(v[0] for v in s.vertices) < 1.0                       # da primeira terça
        assert max(v[0] for v in s.vertices) > 2900.0                    # até a parede, cortada na diagonal
        assert (s.atributos or {}).get("recorte")
    assert r["recortes"] == 6


def test_a_telha_do_projeto_fica_no_modelo():
    """A telha do projeto (a TR40 0,50 Galvalume do Posto V2, largura útil 1.000 mm pela paginação) fica no modelo: o
    relançamento sem telha usa a mesma, e cada chapa leva a largura e a massa por m² (a lista tira a área e o peso)."""
    tr40 = {"nome": "TR40 0,50 mm Galvalume", "modelo": "TR40", "largura_util": 1000.0, "massa_m2": 4.71}
    doc = Documento()
    _agua(doc, 0.0, 3, 7000.0, 0.05)
    T.lancar(doc, tr40)
    T.lancar(doc)
    chapas = _telhado(doc)
    assert len(chapas) == 6 and all(s.nome == "TR40 0,50 mm Galvalume" for s in chapas)
    assert all(s.atributos["largura"] == 1000 and s.atributos["massa_m2"] == 4.71 for s in chapas)
