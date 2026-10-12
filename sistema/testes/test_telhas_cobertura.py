# -*- coding: utf-8 -*-
"""As telhas lançadas em cima das terças (nucleo3d/telhas_cobertura.py, 12/10/2026)."""
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
    assert all(4040 <= v[0] <= 4360 for v in calha.vertices)            # 300 mm centrada na terça


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
    for f in fora:
        assert max(v[0] for v in f.vertices) <= -200.0 - 100.0          # do lado de fora (sem telhado)
    for f in dentro:
        assert min(v[0] for v in f.vertices) >= -200.0 + 100.0          # do lado do telhado
    for f in fech:
        assert min(v[2] for v in f.vertices) <= 5950.0 and max(v[2] for v in f.vertices) >= 7650.0


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
