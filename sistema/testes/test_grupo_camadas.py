# -*- coding: utf-8 -*-
"""Os grupos de camadas (19/10/2026, o usuário no Mercado: "criar uma layer com as telhas, calhas e rufos agrupadas no
mesmo elemento e também criar uma ferramenta para agrupar layers onde seja possível desabilitar a layer de um grupo todo
de uma vez"): o grupo gravado na camada, levado ao 3D leve do modo ver, e o lançamento de telhas pondo as camadas dele no
grupo da cobertura."""
from nucleo3d import telhas_cobertura as T
from nucleo3d.modelo import Barra, Camada, Documento


def test_o_grupo_da_camada_vai_e_volta_no_modelo():
    doc = Documento()
    doc.camadas["Telhas"] = Camada(nome="Telhas", grupo="Cobertura")
    doc.camadas["Pilares"] = Camada(nome="Pilares")
    de_novo = Documento.de_dict(doc.dict())
    assert de_novo.camadas["Telhas"].grupo == "Cobertura"
    assert de_novo.camadas["Pilares"].grupo == ""
    # o modelo antigo (sem o campo) abre com a camada solta
    d = doc.dict()
    d["camadas"]["Pilares"].pop("grupo")
    assert Documento.de_dict(d).camadas["Pilares"].grupo == ""


def _telhado_com_platibanda():
    doc = Documento()
    for i in range(6):
        b = Barra(inicio=(i * 1400.0, 0.0, 7000.0 - i * 70.0), fim=(i * 1400.0, 6000.0, 7000.0 - i * 70.0),
                  perfil="U 100×40×2,65 (FF)", papel="terça", camada="Terças")
        b.atributos = {"origem": {"sigla": "TC1"}}
        doc.add(b)
    for z in (6400.0, 7900.0):
        b = Barra(inicio=(7550.0, 0.0, z), fim=(7550.0, 6000.0, z), perfil="U 100×50×3,00 (FF)", papel="banzo",
                  camada="Platibanda", rotacao=270.0)
        b.atributos = {"origem": {"peca": "P.1"}, "conjunto": "P.1"}
        doc.add(b)
    return doc


def test_o_lancamento_de_telhas_agrupa_a_cobertura():
    """as camadas do que o lançamento faz (telhas, calhas, rufos) no grupo da cobertura; a estrutura fica solta"""
    doc = _telhado_com_platibanda()
    T.lancar(doc)
    grupos = {n: c.grupo for n, c in doc.camadas.items()}
    assert {"Telhas", "Calhas", "Rufos"} <= set(grupos)
    assert grupos["Telhas"] == grupos["Calhas"] == grupos["Rufos"] == T.GRUPO_COBERTURA
    assert grupos["Terças"] == "" and grupos["Platibanda"] == ""


def test_a_camada_que_ja_tem_grupo_fica_nele():
    doc = _telhado_com_platibanda()
    doc.camadas["Telhas"] = Camada(nome="Telhas", grupo="Meu grupo")
    T.lancar(doc)
    assert doc.camadas["Telhas"].grupo == "Meu grupo"
    assert doc.camadas["Calhas"].grupo == T.GRUPO_COBERTURA
