# -*- coding: utf-8 -*-
"""Leitura do projeto recebido por quadros (plano de 01/10, etapas 3 a 6): a Montagem com os quadros
tipados (web/cad/montagem.js) é lida de volta em milímetros reais (nucleo3d/leitura_quadros.py), a
pré-análise aponta o que falta, o banco de detalhes dá as variantes (nucleo/banco_detalhes.py) e o 3D
sai pelos quadros com a tesoura como bloco (nucleo3d/de_quadros.py).

O projeto daqui é sintético e pequeno: uma tesoura plana de 6 m em dois pórticos, duas linhas de terça,
quatro pilares de concreto numa locação desenhada noutro canto do DXF e um corte com os níveis. A
portaria do Projeto Hermes (o caso real) foi conferida à parte: as cinco tesouras lidas pelos quadros
são as mesmas barras da leitura usada no modelo montado, e o 3D bate peça a peça nas tesouras, terças
e suportes de terça."""
import math

import pytest

from nucleo import banco_detalhes
from nucleo3d import de_quadros
from nucleo3d import leitura_quadros as lq

MARGEM = lq.MARGEM


# ------------------------------------------------------------------ a montagem como o operador faria

def _linha(x0, y0, x1, y1, camada="0"):
    return {"tipo": "linha", "camada": camada, "a": [x0, y0], "b": [x1, y1]}


def _texto(x, y, s, alt=60.0, camada="TEXTO"):
    return {"tipo": "texto", "camada": camada, "posicao": [x, y], "texto": s, "altura": alt}


def _ret(cx, cy, w, h, camada="PILAR"):
    return {"tipo": "polilinha", "camada": camada, "fechada": True,
            "vertices": [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]]}


def _pontos(e):
    t = e["tipo"]
    if t == "linha":
        return [e["a"], e["b"]]
    if t == "polilinha":
        return e["vertices"]
    if t == "texto":
        return [e["posicao"]]
    return [e["centro"]]


class _Montagem:
    """o desenho "montagem" com os quadros um embaixo do outro e o envio de cada área (o que
    copiarParaQuadro do montagem.js grava: a escala, a caixa na Original e o canto no quadro)"""

    def __init__(self):
        self.quadros = []
        self.entidades = []
        self.y = 0.0

    def quadro(self, tipo, nome="", escala=50):
        q = {"id": "q%d" % (len(self.quadros) + 1), "tipo": tipo, "nome": nome, "escala": escala,
             "w": 2000.0, "h": 2000.0, "x": 0.0, "y": self.y}
        self.y -= 2100.0
        self.quadros.append(q)
        return q

    def enviar(self, q, ents, dx_papel=0.0):
        pts = [p for e in ents for p in _pontos(e)]
        bx0, by1 = min(p[0] for p in pts), max(p[1] for p in pts)
        by0, bx1 = min(p[1] for p in pts), max(p[0] for p in pts)
        s = q["escala"]
        env = {"id": "e%d" % (sum(len(x.get("envios") or []) for x in self.quadros) + 1), "desenho": "planta-de-lançamento",
               "caixa": [[bx0, by0], [bx1, by1]], "ox": MARGEM["lado"] + dx_papel, "oy": -MARGEM["topo"], "escala": s}
        q.setdefault("envios", []).append(env)
        q["fonte"] = {"desenho": "planta-de-lançamento", "caixa": env["caixa"]}

        def f(p):
            return [q["x"] + env["ox"] + (p[0] - bx0) / s, q["y"] + env["oy"] - (by1 - p[1]) / s]
        for e in ents:
            n = dict(e)
            if e["tipo"] == "linha":
                n["a"], n["b"] = f(e["a"]), f(e["b"])
            elif e["tipo"] == "polilinha":
                n["vertices"] = [f(v) for v in e["vertices"]]
            elif e["tipo"] == "texto":
                n["posicao"] = f(e["posicao"])
                n["altura"] = e["altura"] / s
            n["atributos"] = {"quadro": q["id"], "envio": env["id"]}
            self.entidades.append(n)

    def desenho(self, ligacoes=None, parametros=None):
        return {"nome": "Montagem", "escala": 1, "entidades": self.entidades,
                "metadados": {"montagem": {"versao": 1, "original": "planta-de-lançamento", "quadros": self.quadros,
                                           "ligacoes": ligacoes or {}, "parametros": parametros or {}}}}


def _tesoura(x0=0.0, y0=0.0, legenda=True, nome="T01", qtd=2):
    """a elevação de uma tesoura plana de 6 m × 0,84 m: banzos em linha dupla (U deitado, 40 mm), a alma
    em linha simples (cantoneira), o título e a legenda dos perfis embaixo"""
    e = []
    for y in (0.0, 40.0, 800.0, 840.0):
        e.append(_linha(x0, y0 + y, x0 + 6000.0, y0 + y, "TESOURA"))
    for x in (1000.0, 3000.0, 5000.0):
        e.append(_linha(x0 + x, y0 + 40.0, x0 + x, y0 + 800.0, "TESOURA"))
    for xa, xb in ((1000.0, 2000.0), (3000.0, 2000.0), (3000.0, 4000.0), (5000.0, 4000.0)):
        e.append(_linha(x0 + xa, y0 + 40.0, x0 + xb, y0 + 800.0, "TESOURA"))
    e.append(_texto(x0, y0 - 300.0, "Tesoura - %s - %dx" % (nome, qtd), 80.0, "FOLHA"))
    if legenda:
        e.append(_texto(x0, y0 - 420.0, "BANZO U100x40#2mm"))
        e.append(_texto(x0, y0 - 540.0, "DIAG./MONT. L25x25#11"))
    return e


def _planta():
    """duas tesouras (em pé, 6 m em y) a 5 m uma da outra, as marcas, duas terças de 5,2 m e os nomes dos pilares"""
    e = []
    for x in (0.0, 5000.0):
        e += [_linha(x - 50.0, 0.0, x - 50.0, 6000.0, "TESOURA"), _linha(x + 50.0, 0.0, x + 50.0, 6000.0, "TESOURA")]
        e.append(_texto(x + 150.0, 3000.0, "T01", 150.0))
    for y in (1000.0, 5000.0):
        e += [_linha(-100.0, y - 25.0, 5100.0, y - 25.0, "TERÇA"), _linha(-100.0, y + 25.0, 5100.0, y + 25.0, "TERÇA")]
        e.append(_texto(2500.0, y + 100.0, "TC01", 120.0))
    for k, (x, y) in enumerate(((0.0, 0.0), (5000.0, 0.0), (0.0, 6000.0), (5000.0, 6000.0))):
        e.append(_texto(x + 200.0, y - 250.0, "P%d" % (k + 1), 120.0, "PILAR TEXTO"))
    return e


def _lista_tercas():
    return [_texto(20000.0, 0.0, "Terça - TC01 - 2x", 60.0), _texto(20000.0, -120.0, "U100x50X17#12", 60.0)]


def _locacao(dx=100000.0):
    e = []
    for k, (x, y) in enumerate(((0.0, 0.0), (5000.0, 0.0), (0.0, 6000.0), (5000.0, 6000.0))):
        e.append(_ret(x + dx, y, 300.0, 300.0))
        e.append(_texto(x + dx + 200.0, y - 250.0, "P%d" % (k + 1), 120.0, "PILAR TEXTO"))
        e.append(_texto(x + dx + 200.0, y - 400.0, "30/30", 90.0, "PILAR TEXTO"))
    return e


def _corte():
    return [_linha(0.0, 0.0, 6000.0, 0.0, "CORTE"), _texto(6200.0, 0.0, "±0,00"), _texto(6200.0, 4000.0, "+4,00"),
            _linha(0.0, 4000.0, 6000.0, 4000.0, "CORTE")]


def _montagem(legenda=True, marca_extra=False, ligacoes=None, parametros=None):
    M = _Montagem()
    qp = M.quadro("tesouras_pos", escala=100)
    qt = M.quadro("tercas", escala=100)
    ql = M.quadro("locacao", escala=100)
    qc = M.quadro("corte", escala=50)
    M.quadro("ligacoes", escala=10)
    q1 = M.quadro("tesoura", "T01", escala=25)
    planta = _planta()
    if marca_extra:
        planta.append(_texto(2500.0, 3000.0, "T09", 150.0))
    M.enviar(qp, planta)
    M.enviar(qt, planta)
    M.enviar(qt, _lista_tercas(), dx_papel=80.0)          # a lista mandada ao lado, sem substituir
    M.enviar(ql, _locacao())
    M.enviar(qc, _corte())
    M.enviar(q1, _tesoura(-30000.0, 20000.0, legenda=legenda))
    return M.desenho(ligacoes=ligacoes, parametros=parametros)


# ------------------------------------------------------------------ do papel para o real

def test_entidades_voltam_para_as_coordenadas_da_original():
    des = _montagem()
    reais = lq.entidades_reais(des)
    q = next(q for q in des["metadados"]["montagem"]["quadros"] if q["tipo"] == "tesouras_pos")
    linhas = [e for e in reais[q["id"]] if e["tipo"] == "linha"]
    assert any(abs(e["a"][0] - (-50.0)) < 1e-6 and abs(e["a"][1]) < 1e-6 and abs(e["b"][1] - 6000.0) < 1e-6 for e in linhas)
    # o segundo envio (a lista, ao lado) volta para o lugar dele, não sobre a planta
    qt = next(q for q in des["metadados"]["montagem"]["quadros"] if q["tipo"] == "tercas")
    lista = next(e for e in reais[qt["id"]] if e["tipo"] == "texto" and e["texto"].startswith("Terça"))
    assert lista["posicao"] == pytest.approx([20000.0, 0.0])
    # o texto volta com a altura real (60 mm)
    assert lista["altura"] == pytest.approx(60.0)


def test_ponto_real_volta_ao_papel_do_quadro():
    des = _montagem()
    q = next(q for q in des["metadados"]["montagem"]["quadros"] if q["tipo"] == "tercas")
    p = lq._para_papel(q, (20000.0, 0.0))
    texto = next(e for e in des["entidades"] if e["tipo"] == "texto" and e["texto"].startswith("Terça"))
    assert p == pytest.approx(texto["posicao"], abs=0.01)


# ------------------------------------------------------------------ a leitura de cada quadro

def test_leitura_dos_quadros():
    r = lq.ler(_montagem())
    por = {q["tipo"]: q for q in r["quadros"]}
    t = por["tesoura"]["leitura"]
    assert t["nome"] == "T01" and t["qtd"] == 2
    assert t["banzo"]["perfil"].startswith("U 100×40×2")
    assert t["alma"]["perfil"] == 'L 1"×1/8"'
    assert t["contagem"] == {"banzo": 2, "montante": 3, "diagonal": 4}
    assert t["comprimento"] == pytest.approx(6000.0, abs=1.0)
    pos = por["tesouras_pos"]["leitura"]
    assert pos["contagem"] == {"T01": 2} and all("linha" in m for m in pos["marcas"])
    ter = por["tercas"]["leitura"]
    assert ter["tabela"]["TC01"]["qtd"] == 2 and ter["tabela"]["TC01"]["perfil"].startswith("Ue 100×50×17")
    assert len(ter["linhas"]) == 2 and ter["contagem"] == {"TC01": 2}
    loc = por["locacao"]["leitura"]
    assert sorted(p["nome"] for p in loc["pilares"]) == ["P1", "P2", "P3", "P4"]
    assert all(p["concreto"] == [300, 300] and p["achou_secao"] for p in loc["pilares"])
    # a locação foi desenhada 100 m ao lado: os nomes em comum com a planta a trazem para o lugar
    assert r["referencia"]["locacao"]["dx"] == pytest.approx(-100000.0, abs=1.0)
    assert r["referencia"]["base"] == 0.0 and r["referencia"]["topo"] == 4000.0
    # sem variante escolhida para o suporte de terça: o único erro
    assert [a["codigo"] for a in r["apontamentos"] if a["nivel"] == "erro"] == ["ligacao_sem_variante:suporte_terca"]


def test_pre_analise_aponta_legenda_e_marca_sem_quadro():
    r = lq.ler(_montagem(legenda=False, marca_extra=True, ligacoes={"suporte_terca": "ST1"}))
    cods = {a["codigo"] for a in r["apontamentos"] if a["nivel"] == "erro"}
    assert "sem_legenda" in cods and "marca_sem_quadro" in cods
    a = next(a for a in r["apontamentos"] if a["codigo"] == "marca_sem_quadro")
    assert "T09" in a["msg"] and a.get("papel")              # o clique leva ao ponto no quadro


def test_perfil_escrito_na_grafia_do_advance():
    assert lq.perfil_escrito("U100x40#2mm")["perfil"].startswith("U 100×40×2")
    assert lq.perfil_escrito("L 100x50 E=3.75mm")["perfil"].startswith("L 100×50×3,75")


# ------------------------------------------------------------------ o banco de detalhes

def test_banco_de_detalhes(tmp_path):
    b = banco_detalhes.lista(str(tmp_path))
    ids = {v["id"] for v in b["variantes"]}
    assert {"ST1", "SC1", "CASTANHA16"} <= ids
    v = banco_detalhes.salvar(str(tmp_path), {"id": "st 2", "funcao": "suporte_terca", "nome": "ST2",
                                              "colocacao": {"peca": "L 100x50x3,75", "comprimento": "150"}})
    assert v["id"] == "ST2" and v["colocacao"]["comprimento"] == 150.0
    assert banco_detalhes.variante("ST2", str(tmp_path))["colocacao"]["peca"] == "L 100x50x3,75"
    assert banco_detalhes.excluir(str(tmp_path), "ST2") and banco_detalhes.variante("ST2", str(tmp_path)) is None
    with pytest.raises(ValueError):
        banco_detalhes.salvar(str(tmp_path), {"id": "X1", "funcao": "outra"})


# ------------------------------------------------------------------ o 3D pelos quadros

def test_gerar_3d_pelos_quadros():
    r = de_quadros.gerar(_montagem(ligacoes={"suporte_terca": "ST1", "base_pilar": "APOIO-CONCRETO"}))
    doc, s = r["doc"], r["resumo"]
    assert s["tesouras"] == {"T01": 2}
    assert s["tercas"] == 2 and s["pilares"] == 4
    assert s["suportes_terca"] == 4                         # cada terça em cada tesoura
    banzos = [b for b in doc.barras if b.papel == "banzo"]
    assert len(banzos) == 4
    # a tesoura em pé na linha da planta (6 m em y), o banzo de baixo no topo dos pilares
    for b in banzos:
        assert abs(b.inicio[0] - b.fim[0]) < 1.0 and abs(abs(b.fim[1] - b.inicio[1]) - 6000.0) < 1.0
    z_baixo = min(min(b.inicio[2], b.fim[2]) for b in banzos)
    assert 4000.0 < z_baixo < 4060.0
    # a L da alma dupla nas paredes do U (banzo em U)
    alma = [b for b in doc.barras if b.papel in ("montante", "diagonal")]
    assert len(alma) == 2 * 2 * 7
    # as terças em cima do banzo de cima, ao longo de x
    for t in (b for b in doc.barras if b.papel == "terça"):
        assert abs(t.inicio[1] - t.fim[1]) < 1.0 and t.inicio[2] > 4800.0
    # os pilares de concreto só de apoio, da base ao topo
    pil = [e for e in doc.entidades.values() if getattr(e, "tipo", "") == "solido" and (e.atributos or {}).get("concreto")]
    assert len(pil) == 4 and all((p.atributos or {}).get("calcular") is False for p in pil)
    zs = [v[2] for p in pil for v in p.vertices]
    assert min(zs) == pytest.approx(0.0) and max(zs) == pytest.approx(4000.0)
    # o pilar cai embaixo da ponta da tesoura (a locação trazida pelos nomes)
    xs = sorted({round(sum(v[0] for v in p.vertices) / len(p.vertices)) for p in pil})
    xb = sorted({round(b.inicio[0]) for b in banzos})
    assert all(min(abs(x - y) for y in xb) < 60 for x in xs)
    # o encaixe de fábrica entrou nas almas
    assert s["encaixe"].get("pontas", 0) > 0


def test_suporte_de_terca_encostado_na_alma_da_terca():
    r = de_quadros.gerar(_montagem(ligacoes={"suporte_terca": "ST1"}))
    from nucleo3d import geometria as G
    doc = r["doc"]
    sts = [b for b in doc.barras if b.papel == "suporte"]
    tercas = [b for b in doc.barras if b.papel == "terça"]
    for st in sts:
        v = G.malha_barra(st)[0]
        ys = [p[1] for p in v]
        zs = [p[2] for p in v]
        assert max(zs) - min(zs) == pytest.approx(100.0, abs=0.5)      # a aba de 100 em pé
        assert max(ys) - min(ys) == pytest.approx(50.0, abs=0.5)       # a de 50 deitada
        t = min(tercas, key=lambda t: abs(t.inicio[1] - (min(ys) + max(ys)) / 2))
        vt = G.malha_barra(t)[0]
        ty = [p[1] for p in vt]
        # encostada numa face da terça, por fora
        assert min(abs(min(ys) - max(ty)), abs(max(ys) - min(ty))) < 0.5
        assert min(zs) == pytest.approx(min(p[2] for p in vt), abs=0.5)  # o pé na altura do fundo da terça


def test_gerar_sem_marca_avisa():
    r = de_quadros.gerar(_montagem(marca_extra=True, ligacoes={"suporte_terca": "ST1"}))
    assert any("T09" in a for a in r["avisos"])


# ------------------------------------------------------------------ revisão da Original

def test_revisao_mostra_o_que_mudou_na_area_do_quadro():
    des = _montagem()
    m = des["metadados"]["montagem"]
    r00 = {"entidades": _planta() + _lista_tercas() + _locacao() + _corte() + _tesoura(-30000.0, 20000.0)}
    r01 = {"entidades": [e for e in r00["entidades"] if not (e["tipo"] == "texto" and e["texto"] == "TC01" and e["posicao"][1] > 5000.0)]
           + [_linha(1000.0, 5500.0, 4000.0, 5500.0, "TERÇA")]}         # fora da área do corte (desenhado no mesmo canto)
    desenhos = {"planta-de-lançamento": r00, "planta-de-lançamento-r01": r01}
    m["original"] = "planta-de-lançamento-r01"
    m["revisoes"] = [{"nome": "planta-de-lançamento-r01", "rotulo": "R01"}]
    aps = lq.comparar_revisao(m, desenhos.__getitem__)
    por = {a["rotulo"]: a for a in aps}
    # a planta foi mandada para a posição das tesouras e para as terças: as duas áreas mudaram (a marca TC01 de
    # cima saiu, uma linha entrou — as duas longe do corte, desenhado no mesmo canto); a locação e a tesoura não
    assert set(por) == {"Posição das tesouras", "Posição das terças"}
    assert "1 objeto(s) novo(s), 1 que saíram" in por["Posição das terças"]["msg"]
    assert por["Posição das terças"]["envio"] and por["Posição das terças"]["codigo"] == "revisao_mudou"
    # sem revisão nova (a original de sempre), nada a apontar
    m["original"] = "planta-de-lançamento"
    assert lq.comparar_revisao(m, desenhos.__getitem__) == []


def test_conferencia_projeto_modelo():
    r = de_quadros.gerar(_montagem(ligacoes={"suporte_terca": "ST1"}))
    conf = {c["peca"]: c for c in r["resumo"]["conferencia"]}
    assert conf["T01"] == {"peca": "T01", "projeto": 2, "planta": 2, "modelo": 2, "confere": True}
    assert conf["TC01"]["projeto"] == 2 and conf["TC01"]["modelo"] == 2 and conf["TC01"]["confere"]


# ------------------------------------------------------------------ viga treliçada

def test_viga_trelicada_com_nota_depois_da_quantidade():
    """a viga painel tem quadro próprio ("Viga treliçada", pedido de 01/10: "não tem a viga painel para importar"):
    lida como a tesoura, com a quantidade no meio do título, e colocada pela marca VP1 da planta"""
    M = _Montagem()
    qp = M.quadro("tesouras_pos", escala=100)
    qv = M.quadro("viga", "VP1", escala=25)
    planta = [_linha(-50.0, 0.0, -50.0, 6000.0, "VIGA"), _linha(50.0, 0.0, 50.0, 6000.0, "VIGA"),
              _texto(150.0, 3000.0, "VP1", 150.0)]
    M.enviar(qp, planta)
    elev = [e for e in _tesoura(-30000.0, 20000.0) if e["tipo"] != "texto" or not e["texto"].startswith("Tesoura")]
    elev.append(_texto(-30000.0, 19700.0, "Viga painel VP1 - 01X - cuidar lado da cantoneira", 80.0, "FOLHA"))
    M.enviar(qv, elev)
    r = lq.ler(M.desenho(parametros={"topo": 3000.0}))
    v = next(q for q in r["quadros"] if q["tipo"] == "viga")
    assert v["rotulo"] == "Viga treliçada VP1"
    assert v["leitura"]["nome"] == "VP01" and v["leitura"]["qtd"] == 1
    assert next(q for q in r["quadros"] if q["tipo"] == "tesouras_pos")["leitura"]["contagem"] == {"VP01": 1}
    g = de_quadros.gerar(M.desenho(parametros={"topo": 3000.0}))
    assert g["resumo"]["tesouras"] == {"VP01": 1}
    assert {c["peca"]: c["confere"] for c in g["resumo"]["conferencia"]} == {"VP01": True}
