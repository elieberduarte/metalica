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
        b = Barra(inicio=(x_f, 0.0, z), fim=(x_f, 6000.0, z), perfil="U 100×50×3,00 (FF)", papel="banzo",
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
