# -*- coding: utf-8 -*-
"""Testes do núcleo 2D: documento de desenho e motor de vistas (corte e projeção)."""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados                                    # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Documento, Solido            # noqa: E402
from nucleo2d.desenho import (Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota,  # noqa: E402
                              Hachura, Chamada, formatar_mm, escala_sugerida)
from nucleo2d.vistas import Vista, gerar, vista_padrao                # noqa: E402


def _projecao(d):
    return [e for e in d.entidades.values() if e.camada in ("VISTA", "VISTA-FINA")]


def _secoes(d):
    return [e for e in d.por_tipo("polilinha") if e.camada == "CORTE"]


def _cubo(x0, y0, z0, a, nome="C", camada="Estrutura"):
    v = [(x0, y0, z0), (x0 + a, y0, z0), (x0 + a, y0 + a, z0), (x0, y0 + a, z0),
         (x0, y0, z0 + a), (x0 + a, y0, z0 + a), (x0 + a, y0 + a, z0 + a), (x0, y0 + a, z0 + a)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome=nome, camada=camada, vertices=v, faces=f)


# ------------------------------------------------------------------ desenho

def test_desenho_ida_e_volta_e_caixa():
    d = Desenho(nome="T", escala=25)
    d.add(Linha(a=(0, 0), b=(100, 0)))
    d.add(Circulo(centro=(50, 50), raio=10, camada="FURO"))
    d.add(Arco(centro=(0, 0), raio=20, inicio=0, fim=90))
    d.add(Texto(posicao=(10, 10), texto="P1", altura=3))
    d.add(Cota(p1=(0, 0), p2=(100, 0), deslocamento=-10))
    d.add(Hachura(contornos=[[(0, 0), (10, 0), (10, 10), (0, 10)]]))
    d.add(Chamada(alvo=(5, 5), posicao=(30, 30), texto="solda"))
    d.add(Polilinha(vertices=[(0, 0), (1, 1), (2, 0)], fechada=True, camada="CORTE"))
    assert d.tamanho == 8 and "CORTE" in d.camadas and "FURO" in d.camadas
    (x0, y0), (x1, y1) = d.caixa()
    assert x0 == 0 and x1 == 100 and y0 == 0 and y1 == 60
    volta = Desenho.de_dict(json.loads(json.dumps(d.dict())))
    assert volta.tamanho == 8 and volta.escala == 25 and volta.caixa() == d.caixa()
    assert volta.por_tipo("cota")[0].valor() == 100
    assert isinstance(volta.por_tipo("linha")[0].a, tuple)


def test_desenho_para_dxf_aplica_escala_no_que_e_de_papel():
    d = Desenho(nome="T", escala=20)
    d.add(Texto(posicao=(0, 0), texto="abc", altura=2.5))
    d.add(Cota(p1=(0, 0), p2=(1000, 0), deslocamento=10))
    d.add(Circulo(centro=(0, 0), raio=6.5, camada="FURO"))
    dxf = d.para_dxf().dxf()
    assert "CIRCLE" in dxf and "TEXT" in dxf and "\n40\n50.0000\n" in dxf      # 2,5 mm × 20
    assert "\n1\n1000\n" in dxf                                                  # valor da cota
    assert "\n8\nFURO\n" in dxf and "\n8\nCOTA\n" in dxf
    # camada oculta não sai
    d.camadas["FURO"].visivel = False
    assert "CIRCLE" not in d.para_dxf().dxf()


def test_formatos():
    assert formatar_mm(1000.0) == "1000" and formatar_mm(12.34) == "12,3" and formatar_mm(99.97) == "100"
    assert escala_sugerida(3000, 2000) == 5 and escala_sugerida(20000, 8000) == 50
    assert escala_sugerida(0, 0) == 20


# ------------------------------------------------------------------- vistas

def test_eixos_da_vista_formam_triedro_direito():
    for normal, acima in (((0, 1, 0), None), ((1, 0, 0), None), ((0, 0, -1), None), ((0, 0, 1), (0, 1, 0))):
        u, v, w = Vista(normal=normal, acima=acima).eixos()
        cruz = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        # u × v aponta para o observador, que está em -w
        assert all(abs(cruz[i] + w[i]) < 1e-9 for i in range(3)), (normal, cruz, w)
    # olhando para +Y com Z para cima, a direita é +X
    u, v, w = Vista(normal=(0, 1, 0)).eixos()
    assert abs(u[0] - 1) < 1e-9 and abs(v[2] - 1) < 1e-9
    try:
        Vista(normal=(0, 0, 1), acima=(0, 0, 1)).eixos()
    except ErroDeDados:
        pass
    else:
        raise AssertionError("acima paralelo à normal devia ser recusado")


def test_corte_de_um_cubo_da_secao_quadrada_hachurada_e_rotulada():
    doc = Documento(nome="t")
    doc.add(_cubo(0, 0, 0, 1000, nome="Bloco"))
    d = gerar(doc, Vista(origem=(0, 500, 0), normal=(0, 1, 0)))
    cortes = _secoes(d)
    assert len(cortes) == 1 and cortes[0].fechada
    pts = cortes[0].vertices
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert abs(max(xs) - min(xs) - 1000) < 1e-6 and abs(max(ys) - min(ys) - 1000) < 1e-6
    assert min(xs) == 0 and min(ys) == 0                       # origem no canto inferior esquerdo
    assert len(d.por_tipo("hachura")) == 1
    rot = d.por_tipo("texto")
    assert len(rot) == 1 and rot[0].texto == "Bloco" and rot[0].atributos.get("rotulo")
    assert cortes[0].atributos["origem"] and cortes[0].atributos["nome"] == "Bloco"
    # a metade removida (y < 500) não projeta nada: só a seção e a face de trás,
    # encadeada numa polilinha fechada de 4 lados
    proj = _projecao(d)
    assert len(proj) == 1 and proj[0].tipo == "polilinha" and proj[0].fechada and len(proj[0].vertices) == 4
    assert d.vistas[0]["pecas_cortadas"] == 1


def test_projecao_de_frente_de_um_cubo_e_profundidade():
    doc = Documento(nome="t")
    doc.add(_cubo(0, 0, 0, 1000, nome="A"))
    doc.add(_cubo(0, 5000, 0, 500, nome="B"))                   # 5 m atrás
    frente = vista_padrao("frente", doc.caixa())
    d = gerar(doc, frente)
    nomes = {l.atributos["nome"] for l in _projecao(d)}
    assert nomes == {"A", "B"} and not _secoes(d)                # sem corte, sem seção
    # a silhueta do cubo A visto de frente é um quadrado: uma polilinha fechada de 4
    # vértices (as arestas internas não aparecem)
    quad = [l for l in _projecao(d) if l.atributos["nome"] == "A" and l.camada == "VISTA"]
    assert len(quad) == 1 and quad[0].tipo == "polilinha" and quad[0].fechada and len(quad[0].vertices) == 4
    # com profundidade de 2 m, B fica de fora
    frente.profundidade = 2000
    d2 = gerar(doc, frente)
    assert {l.atributos["nome"] for l in _projecao(d2)} == {"A"}


def test_corte_aparado_na_profundidade_e_lado_removido():
    doc = Documento(nome="t")
    doc.add(_cubo(0, 0, 0, 1000, nome="A"))
    # plano em y = 500, olhando para +y, profundidade 200: a seção aparece e as arestas
    # que seguem para y = 1000 são aparadas em y = 700
    d = gerar(doc, Vista(origem=(0, 500, 0), normal=(0, 1, 0), profundidade=200))
    assert d.vistas[0]["pecas_cortadas"] == 1
    # peça inteira do lado removido: vista vazia → erro claro
    try:
        gerar(doc, Vista(origem=(0, 2000, 0), normal=(0, 1, 0)))
    except ErroDeDados as e:
        assert "não alcança" in str(e)
    else:
        raise AssertionError("vista sem peça devia avisar")


def test_vista_de_barra_e_chapa_parametricas():
    doc = Documento(nome="t")
    doc.add(Barra(nome="P1", inicio=(0, 0, 0), fim=(0, 0, 3000), perfil="W 310×38,7", papel="pilar"))
    doc.add(Chapa(nome="CH1", origem=(0, 0, 3000), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                  contorno=[(-150, -150), (150, -150), (150, 150), (-150, 150)], espessura=16,
                  furos=[{"x": 0, "y": 0, "diametro": 20}]))
    # corte horizontal a 1,5 m: a seção do W (um I) com a alma e as mesas
    d = gerar(doc, Vista(origem=(0, 0, 1500), normal=(0, 0, -1), acima=(0, 1, 0)))
    secoes = _secoes(d)
    assert len(secoes) == 1 and secoes[0].atributos["perfil"] == "W 310×38,7"
    pts = secoes[0].vertices
    assert len(pts) >= 12                                          # o I tem 12 cantos
    larg = max(p[0] for p in pts) - min(p[0] for p in pts)
    alt = max(p[1] for p in pts) - min(p[1] for p in pts)
    # bf × d do W 310×38,7; a orientação em planta depende do triedro da barra
    assert sorted((round(larg), round(alt))) == [165, 310], (larg, alt)
    # vista de topo: a chapa aparece com o furo
    topo = vista_padrao("topo", doc.caixa())
    d2 = gerar(doc, topo)
    assert any(l.atributos["nome"] == "CH1" for l in _projecao(d2))


def test_entidades_escolhidas_e_camada_oculta():
    doc = Documento(nome="t")
    a = doc.add(_cubo(0, 0, 0, 1000, nome="A"))
    b = doc.add(_cubo(3000, 0, 0, 1000, nome="B", camada="Telhas"))
    frente = vista_padrao("frente", doc.caixa())
    frente.entidades = [a.id]
    assert {l.atributos["nome"] for l in _projecao(gerar(doc, frente))} == {"A"}
    frente.entidades = None
    doc.camadas["Telhas"].visivel = False
    assert {l.atributos["nome"] for l in _projecao(gerar(doc, frente))} == {"A"}


def test_definicao_de_vista_serializa():
    v = Vista(origem=(1, 2, 3), normal=(0, 1, 0), profundidade=1500, nome="Corte A")
    d = Vista.de_dict(json.loads(json.dumps(v.dict())))
    assert d.origem == (1.0, 2.0, 3.0) and d.profundidade == 1500 and d.nome == "Corte A"
    try:
        Vista.de_dict({"normal": [0, 1]})
    except ErroDeDados:
        pass
    else:
        raise AssertionError("normal com 2 componentes devia ser recusada")
    for tipo in ("frente", "tras", "esquerda", "direita", "topo", "inferior"):
        assert vista_padrao(tipo, ((0, 0, 0), (1, 1, 1))).tipo == tipo


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)
