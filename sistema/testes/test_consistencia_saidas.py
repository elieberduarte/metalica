# -*- coding: utf-8 -*-
"""saida/consistencia.py: a conferência das saídas de uma obra (auditoria de números da ME-Sooro, 16/10/2026).

Uma obra mínima montada à mão — duas tesouras montadas de duas metades (T1 = M2), uma família de terças desenhada
uma vez (T.C.1 = M18 / M19), chapas — com os arquivos como o programa grava. A coerente não pode ter achado; cada
defeito que a auditoria achou na Sooro, injetado, tem de ser pego pela conferência certa."""
import copy
import csv
import json
import os
import tempfile

import pytest

from saida import consistencia as C

CAB_ROM = ["Nome", "Posicao", "Conjuntos", "Tipo", "Perfil / chapa", "Material", "Qtd", "Comprimento (mm)", "Largura (mm)",
           "Espessura (mm)", "Furos", "Parafusos", "Peso unit (kg)", "Peso total (kg)", "Observacoes", "Fase", "Acabamento"]


def _rom(nome, pos, tipo, perfil, qtd, pu):
    return {"Nome": nome, "Posicao": pos, "Conjuntos": "", "Tipo": tipo, "Perfil / chapa": perfil, "Material": "A36",
            "Qtd": str(qtd), "Comprimento (mm)": "1000", "Largura (mm)": "", "Espessura (mm)": "", "Furos": "",
            "Parafusos": "", "Peso unit (kg)": f"{pu:.3f}".replace(".", ","), "Peso total (kg)": f"{qtd * pu:.2f}".replace(".", ","),
            "Observacoes": "", "Fase": "", "Acabamento": ""}


def obra_coerente() -> dict:
    # M2 = meia-tesoura (4 metades = 2 tesouras montadas): 1 banzo B1 (P1) + 2 chapas CH2 (P13) por metade
    # M18, M19 = terças (família T.C.1): 1 perfil cada; 3 + 1 = 4
    rom = [_rom("B1", "P1", "Barra", "U150", 4, 20.0), _rom("CH2", "P13", "Chapa", "PLATE 270x120x6", 8, 1.63),
           _rom("TC1", "P20", "Barra", "U150x50", 3, 30.0), _rom("TC2", "P21", "Barra", "U150x50", 1, 31.0)]
    cj = [{"Nome": "T1", "Conjunto": "M2", "Categoria": "TESOURAS", "Instancias": "4", "Pecas por unidade": "3",
           "Composicao": "1× P1, 2× P13", "Peso unitario (kg)": "23,26", "Peso total (kg)": "93,04"},
          {"Nome": "T.C.1", "Conjunto": "M18", "Categoria": "TERÇAS", "Instancias": "3", "Pecas por unidade": "1",
           "Composicao": "1× P20", "Peso unitario (kg)": "30,00", "Peso total (kg)": "90,00"},
          {"Nome": "T.C.1", "Conjunto": "M19", "Categoria": "TERÇAS", "Instancias": "1", "Pecas por unidade": "1",
           "Composicao": "1× P21", "Peso unitario (kg)": "31,00", "Peso total (kg)": "31,00"}]
    total = 4 * 20 + 8 * 1.63 + 3 * 30 + 31
    lista = {"posicoes": [{"nome": r["Nome"], "quantidade": int(r["Qtd"]), "peso_total": float(r["Peso total (kg)"].replace(",", "."))}
                          for r in rom],
             "totais": {"peso": round(total, 2), "pecas": 16, "categorias": [{"categoria": "PERFIS", "peso": 80 + 90 + 31},
                                                                            {"categoria": "CHAPAS", "peso": 13.04}]},
             "telhas": []}
    perfis = [{"Perfil": "U150", "Posicoes": "B1 TC1 TC2", "Pecas": "8", "Peso (kg)": "201,00", "Comprimento total (m)": "8,00"}]
    chapas = [{"Perfil": "#6", "Posicoes": "CH2", "Pecas": "8", "Peso (kg)": "13,04"}]
    item = lambda nome, q, classe="Chapa", peso=0: {"nome": nome, "quantidade": q, "classe": classe, "peso": peso}   # noqa: E731
    pranchas = [
        {"numero": 3, "celulas": [
            {"titulo": "T1 – 02x", "copia": False, "marca": "M2 + M2", "item": item("T1", 2, "Conjunto")},
            {"titulo": "CH2 – 08x", "copia": True, "marca": "P13", "item": item("CH2", 8, peso=1.63)}]},
        {"numero": 9, "celulas": [
            {"titulo": "T.C.1 – 04x", "copia": False, "marca": "M18 / M19", "item": item("T.C.1", 4, "Conjunto")}]},
        {"numero": 11, "celulas": [
            {"titulo": "B1 – 04x", "copia": False, "marca": "P1", "item": item("B1", 4, "Barra", 20.0)},
            {"titulo": "CH2 – 08x", "copia": False, "marca": "P13", "item": item("CH2", 8, peso=1.63)}]},
    ]
    entidades = ([{"id": f"b{i}", "atributos": {"marcas": {"posicao": "P1"}}} for i in range(4)]
                 + [{"id": f"c{i}", "atributos": {"marcas": {"posicao": "P13"}}} for i in range(8)]
                 + [{"id": f"t{i}", "atributos": {"marcas": {"posicao": "P20"}}} for i in range(3)]
                 + [{"id": "t9", "atributos": {"marcas": {"posicao": "P21"}}}])
    return {"rom": rom, "cj": cj, "lista": lista, "perfis": perfis, "chapas": chapas, "pranchas": pranchas, "entidades": entidades}


def gravar(o: dict) -> str:
    pasta = tempfile.mkdtemp(prefix="consistencia_")
    det = os.path.join(pasta, "detalhamento")
    os.makedirs(det)
    os.makedirs(os.path.join(pasta, "desenhos-2d"))

    def csv_(nome, linhas, cab=None):
        with open(os.path.join(det, nome), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cab or list(linhas[0]), delimiter=";")
            w.writeheader()
            w.writerows(linhas)
    csv_("romaneio.csv", o["rom"], CAB_ROM)
    csv_("conjuntos.csv", o["cj"])
    csv_("resumo-perfis.csv", o["perfis"])
    csv_("resumo-chapas.csv", o["chapas"])
    with open(os.path.join(det, "lista-de-materiais.json"), "w", encoding="utf-8") as f:
        json.dump(o["lista"], f)
    with open(os.path.join(pasta, "desenhos-2d", "pranchas.desenho.json"), "w", encoding="utf-8") as f:
        json.dump({"entidades": [], "metadados": {"pranchas": o["pranchas"]}}, f)
    with open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump({"entidades": o["entidades"]}, f)
    return pasta


def confs(o):
    return {a["conferencia"] for a in C.conferir(gravar(o))}


def test_obra_coerente_sem_achado():
    assert C.conferir(gravar(obra_coerente())) == []


def test_copia_local_com_a_quantidade_de_uma_tesoura_so():
    """Sooro, N02/Q04: "CH2 08x" na prancha de 3 tesouras montadas eram 24 peças"""
    o = obra_coerente()
    o["pranchas"][0]["celulas"][1]["item"]["quantidade"] = 4          # a composição de UMA metade
    a = C.conferir(gravar(o))
    assert [x["conferencia"] for x in a] == ["copias"] and "levam 8" in a[0]["texto"]


def test_nome_de_conjunto_que_e_outro_conjunto():
    """Sooro, N01/M02: a prancha "T4" desenha M8 + M9, e o T4 da planta e do romaneio é M6"""
    o = obra_coerente()
    o["cj"].append(dict(o["cj"][0], Nome="T4", Conjunto="M6", Instancias="0"))
    o["pranchas"][0]["celulas"][0]["item"]["nome"] = "T4"
    assert "nomes" in confs(o)


def test_celula_de_fabricacao_com_quantidade_errada_ou_duplicada():
    o = obra_coerente()
    o["pranchas"][2]["celulas"][1]["item"]["quantidade"] = 6
    assert confs(o) == {"fabricacao"}
    o = obra_coerente()
    o["pranchas"][1]["celulas"].append(copy.deepcopy(o["pranchas"][2]["celulas"][0]))   # B1 fabricado em duas pranchas
    assert "fabricacao" in confs(o)


def test_conjuntos_desenhados_que_nao_somam_as_instancias():
    o = obra_coerente()
    o["pranchas"][0]["celulas"][0]["item"]["quantidade"] = 1          # 1 tesoura montada = 2 metades, eram 4
    assert "fabricacao" in confs(o)


def test_quantidade_do_romaneio_diferente_da_lista_e_do_3d():
    o = obra_coerente()
    o["lista"]["posicoes"][0]["quantidade"] = 5
    assert "quantidades" in confs(o)
    o = obra_coerente()
    o["entidades"].append({"id": "b9", "atributos": {"marcas": {"posicao": "P1"}}})
    assert "quantidades" in confs(o)


def test_posicao_do_3d_separada_em_variantes_no_romaneio():
    """Água Gelada: o detalhamento separou P48 em "P48" (260) e "P48 (b)" (68); o 3D tem 328 com P48 — não é divergência"""
    o = obra_coerente()
    o["rom"][1] = _rom("CH2", "P13", "Chapa", "PLATE 270x120x6", 6, 1.63)
    o["rom"].append(_rom("CH2b", "P13 (b)", "Chapa", "PLATE 270x120x6", 2, 1.63))
    no_3d = lambda o: [x["texto"] for x in C.conferir(gravar(o)) if "no 3D" in x["texto"]]   # noqa: E731
    assert no_3d(o) == []
    o["entidades"].append({"id": "c9", "atributos": {"marcas": {"posicao": "P13"}}})
    assert no_3d(o) == ["CH2 + CH2b (P13): 8 no romaneio × 9 peças no 3D"]

def test_pesos_que_nao_fecham():
    o = obra_coerente()
    o["lista"]["totais"]["peso"] += 30
    assert "pesos" in confs(o)
    o = obra_coerente()
    o["perfis"][0]["Peso (kg)"] = "150,00"
    assert "pesos" in confs(o)


def test_posicao_sem_prancha():
    o = obra_coerente()
    o["rom"].append(_rom("CH9", "P30", "Chapa", "PLATE 100x100x8", 2, 0.6))
    o["lista"]["posicoes"].append({"nome": "CH9", "quantidade": 2, "peso_total": 1.2})
    o["lista"]["totais"]["peso"] += 1.2
    o["chapas"][0]["Peso (kg)"] = "14,24"
    o["lista"]["totais"]["categorias"][1]["peso"] += 1.2
    a = C.conferir(gravar(o))
    assert [x["conferencia"] for x in a] == ["nomes"] and "CH9" in a[0]["texto"]


def test_celula_tipica_de_varias_posicoes_e_celula_so_com_titulo():
    """Sala dos Compressores: "A.T.1, A.T.2 – 04x" é uma célula só para as duas cantoneiras iguais (2 + 2), e a da
    cumeeira vem sem item, só com o título "CU1 – 32x" — nenhuma das duas é posição sem prancha"""
    o = obra_coerente()
    o["rom"] += [_rom("A.T.1", "P40", "Barra", "L50X50X2.25", 2, 2.0), _rom("A.T.2", "P41", "Barra", "L50X50X2.25", 2, 2.0),
                 _rom("CU1", "P50", "Telha", "TELHA TP40", 3, 1.0)]
    o["lista"]["posicoes"] += [{"nome": "A.T.1", "quantidade": 2, "peso_total": 4.0}, {"nome": "A.T.2", "quantidade": 2, "peso_total": 4.0},
                               {"nome": "CU1", "quantidade": 3, "peso_total": 3.0}]
    o["lista"]["totais"]["peso"] += 11.0
    o["lista"]["totais"]["categorias"][0]["peso"] += 11.0
    o["perfis"][0]["Peso (kg)"] = "212,00"
    o["pranchas"][2]["celulas"] += [
        {"titulo": "A.T.1, A.T.2 – 04x   (sem furo)", "copia": False, "marca": "TÍPICO L50X50X2.25",
         "item": {"nome": "A.T.1, A.T.2", "quantidade": 4, "classe": "Barra", "peso": 2.0}},
        {"titulo": "CU1 – 03x", "copia": False, "marca": None, "item": None}]
    assert C.conferir(gravar(o)) == []
    o["pranchas"][2]["celulas"][-2]["item"]["quantidade"] = 2          # a típica com a quantidade de uma só
    assert confs(o) == {"fabricacao"}


def test_obra_real_me_sooro_se_houver():
    """A cópia da Sooro detalhada no teste de 16/10 (se estiver nesta máquina): pega o Q04 e o N01."""
    pasta = os.path.join(os.environ.get("TEMP", ""), "metalica_obras_teste", "me-sooro-teste-ifc")
    if not os.path.isdir(pasta):
        pytest.skip("sem a cópia da ME-Sooro nesta máquina")
    a = C.conferir(pasta)
    assert any(x["conferencia"] == "copias" and "CH2" in x["texto"] for x in a)
    assert any(x["conferencia"] == "nomes" and "T4" in x["texto"] for x in a)
