# -*- coding: utf-8 -*-
"""O IFC do modelo com as cores do Pintar do modo ver (usuário, 19/10, abrindo o IFC do Mercado no Trimble Connect: "como
fazer para exportar ... com a estrutura de uma cor e a cobertura de outra, igual temos no modo ver"). Antes o arquivo saía
com a cor do material/camada (o concreto do Tekla azul, o aço nos tons de azul das camadas) e o visualizador agrupava pelas
camadas do modelo. Com a pintura, cada peça sai com a cor do grupo e na camada (layer) com o nome dele."""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from ifc.exportar import para_texto                                          # noqa: E402
from nucleo3d.modelo import Barra, Documento, Solido                          # noqa: E402


def _doc():
    doc = Documento()
    a = doc.add(Barra(nome="Tesoura", inicio=(0, 0, 0), fim=(3000, 0, 0), perfil="U 100×50×3,00 (FF)", papel="banzo",
                      camada="Tesouras"))
    b = doc.add(Barra(nome="Terca", inicio=(0, 0, 500), fim=(0, 3000, 500), perfil="Ue 150×60×20×2,00", papel="terça",
                      camada="Tercas"))
    c = doc.add(Solido(nome="Pilar", camada="200 Pre-Fabricado",
                       vertices=[(0, 0, 0), (300, 0, 0), (300, 300, 0), (0, 300, 0), (0, 0, 900), (300, 0, 900),
                                 (300, 300, 900), (0, 300, 900)],
                       faces=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]))
    d = doc.add(Barra(nome="Fora", inicio=(0, 0, 900), fim=(1000, 0, 900), perfil="U 100×50×3,00 (FF)", papel="viga",
                      camada="Platibanda"))
    return doc, a, b, c, d


def _camadas(texto):
    return set(re.findall(r"IFCPRESENTATIONLAYERWITHSTYLE\('([^']*)'", texto))


PINTURA = lambda a, b, c: {"modo": "sistema", "grupos": [                       # noqa: E731
    {"nome": "Metalica", "cor": "#8b5cf6", "ids": [a.id, b.id]},
    {"nome": "Pre-moldado", "cor": "#8f969e", "ids": [c.id]}]}


def test_sem_pintura_o_ifc_sai_com_as_camadas_do_modelo():
    doc, *_ = _doc()
    assert _camadas(para_texto(doc)) == {"Tesouras", "Tercas", "200 Pre-Fabricado", "Platibanda"}


def test_com_a_pintura_do_modo_ver_cada_peca_sai_com_a_cor_e_a_camada_do_grupo():
    doc, a, b, c, d = _doc()
    texto = para_texto(doc, pintura=PINTURA(a, b, c))
    assert _camadas(texto) == {"Metalica", "Pre-moldado", "Platibanda"}      # a peça fora da pintura fica na camada dela
    # a cor do grupo: 0x8b/255 = 0,545…; 0x5c/255 = 0,361…; 0xf6/255 = 0,965…
    assert re.search(r"IFCCOLOURRGB\(\$,0\.545\d*,0\.36\d*,0\.96\d*\)", texto)
    assert re.search(r"IFCCOLOURRGB\(\$,0\.56\d*,0\.58\d*,0\.61\d*\)", texto)
    assert "IFCSURFACESTYLE('Metalica'" in texto and "IFCSURFACESTYLE('Pre-moldado'" in texto


def test_rota_passa_a_pintura_ao_exportador():
    import app
    doc, a, b, c, d = _doc()
    r = app.exportar_ifc({"documento": doc.dict(), "nome": "teste-pintura", "pintura": PINTURA(a, b, c)})
    assert r["entidades"] == 4
    pasta = os.path.dirname(r["arquivo"]["url"])
    caminhos = [os.path.join(dp, f) for dp, _d, fs in os.walk(os.path.join(app.BASE, "projetos", "modelos"))
                for f in fs if f == r["arquivo"]["nome"]] if pasta else []
    if caminhos:
        texto = open(caminhos[0], encoding="ascii").read()
        assert {"Metalica", "Pre-moldado"} <= _camadas(texto)
