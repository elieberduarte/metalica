# -*- coding: utf-8 -*-
"""Módulo de arquitetura — a parede dentro do modelo 3D (fase 1b, 30/10/2026): a definição em `atributos.arq`, o
`regenerar` pelo motor, a altura pelos níveis (ARQ-03), a área do ambiente pelas faces internas (ARQ-06), os códigos das
esquadrias e a casa piloto."""
import json

import pytest

from arquitetura import modelo as M
from arquitetura.piloto import montar_casa
from nucleo3d.modelo import Documento

NIVEIS = [{"nome": "Térreo", "cota": 0, "laje": 100}, {"nome": "Superior", "cota": 3350, "laje": 350}]


def _doc():
    d = Documento(nome="teste")
    M.definir_niveis(d, NIVEIS)
    return d


def test_parede_vai_do_piso_ao_fundo_da_laje_de_cima():
    """ARQ-03: base no piso do térreo (0), topo no fundo da laje do superior (3350 − 350 = 3000)"""
    d = _doc()
    p = M.nova_parede(d, (0, 0), (4000, 0), "EXT20", "Térreo", "Superior")
    M.regenerar(d)
    zs = [v[2] for v in p.vertices]
    assert (min(zs), max(zs)) == (0, 3000)
    assert p.atributos["arq"]["altura"] == [0, 3000]


def test_nivel_que_nao_existe_vira_aviso_e_nao_quebra():
    d = _doc()
    M.nova_parede(d, (0, 0), (4000, 0), "EXT20", "Térreo", "Mezanino", nome="P1")
    r = M.regenerar(d)
    assert any("Mezanino" in a for a in r["avisos"])


def test_ambiente_tem_area_pelas_faces_internas():
    """sala de 4,00 × 3,00 pelos eixos, cercada de internas de 15: por dentro 3,85 × 2,85 = 10,97 m²"""
    d = _doc()
    for a, b in [((0, 0), (4000, 0)), ((4000, 0), (4000, 3000)), ((4000, 3000), (0, 3000)), ((0, 3000), (0, 0))]:
        M.nova_parede(d, a, b, "INT15", "Térreo", "Superior")
    amb = M.novo_ambiente(d, "Sala", (0, 4000, 0, 3000), "Térreo", "porcelanato")
    M.regenerar(d)
    assert amb.atributos["arq"]["interno"] == [75, 3925, 75, 2925]
    assert amb.atributos["arq"]["area"] == pytest.approx(10.97)
    assert amb.nome == "Sala — 10,97 m²"


def test_ambiente_pela_face_de_fora_da_externa():
    """o retângulo pela face de fora (como a planta da casa): a externa de 20 recua 20 cm inteiros"""
    d = _doc()
    M.nova_parede(d, (100, 0), (100, 3000), "EXT20", "Térreo", "Superior")
    amb = M.novo_ambiente(d, "Quarto", (0, 3000, 0, 3000), "Térreo")
    M.regenerar(d)
    assert amb.atributos["arq"]["interno"][0] == 200


def test_esquadrias_saem_da_parede_com_codigo_por_tipo_e_medida():
    d = _doc()
    M.nova_parede(d, (0, 0), (6000, 0), "EXT20", "Térreo", "Superior", vaos=[
        {"tipo": "janela", "u": 500, "largura": 1500, "altura": 1200, "peitoril": 1100},
        {"tipo": "janela", "u": 3000, "largura": 1500, "altura": 1200, "peitoril": 1100},
        {"tipo": "porta", "u": 5000, "largura": 800, "altura": 2100}])
    r = M.regenerar(d)
    esq = [e for e in d.entidades.values() if (e.atributos.get("arq") or {}).get("elemento") == "esquadria"]
    assert r["esquadrias"] == 3 and len(esq) == 3
    assert sorted(e.atributos["arq"]["codigo"] for e in esq) == ["J1", "J1", "P1"]
    # refazer não duplica
    M.regenerar(d)
    assert len([e for e in d.entidades.values() if (e.atributos.get("arq") or {}).get("elemento") == "esquadria"]) == 3


def test_ida_e_volta_pelo_modelo_json():
    """a definição sobrevive à gravação: o modelo lido de volta regenera igual"""
    d = montar_casa()
    d2 = Documento.de_dict(json.loads(json.dumps(d.dict())))
    r = M.regenerar(d2)
    assert r == {"paredes": 25, "esquadrias": 26, "lajes": 3, "ambientes": 15, "avisos": []}


def test_casa_piloto():
    """a casa alto padrão: as camadas ARQ —, sem aviso, e as áreas da sugestão de planta"""
    d = montar_casa()
    r = d.metadados["arquitetura"]["piloto"]["resumo"]
    assert r["avisos"] == [] and r["paredes"] == 25 and r["ambientes"] == 15
    assert all(c.startswith("ARQ — ") for c in {e.camada for e in d.entidades.values()})
    areas = {e.atributos["arq"]["nome"]: e.atributos["arq"]["area"] for e in d.entidades.values()
             if e.atributos["arq"]["elemento"] == "ambiente" and e.atributos["arq"]["nivel"] == "Superior"}
    assert areas["Suíte master"] == pytest.approx(21.04)        # a mesma da prova (c)
    assert areas["Closet"] == pytest.approx(5.51)
    # todas as malhas fechadas e com vértices
    assert all(e.vertices and e.faces for e in d.entidades.values())
