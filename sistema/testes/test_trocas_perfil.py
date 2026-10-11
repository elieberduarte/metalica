# -*- coding: utf-8 -*-
"""As trocas de perfil da análise aplicadas ao modelo 3D e à planta (nucleo3d/trocas_perfil.py, etapa 6, 11/10/2026)."""
import pytest

from nucleo3d import trocas_perfil as TP
from nucleo3d.modelo import Barra, Documento


def _doc():
    doc = Documento(nome="trocas")
    doc.add(Barra(inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 250×32,7", papel="pilar", atributos={"origem_2d": "p1"}))
    doc.add(Barra(inicio=(0, 0, 6000), fim=(6000, 0, 6000), perfil="W 150×22,5", papel="viga", atributos={"origem_2d": "v1"}))
    for papel in ("banzo_sup", "diagonal", "montante"):
        doc.add(Barra(inicio=(0, 0, 6000), fim=(1000, 0, 6500), perfil="TQ 50×50×2,0", papel="banzo" if papel.startswith("banzo") else papel,
                      atributos={"papel_trelica": papel, "elemento": "trelica"}))
    return doc


def _planta():
    return {"entidades": [
        {"id": "p1", "tipo": "polilinha", "atributos": {"elemento": "pilar", "material": "aco", "secao": {"perfil": "W 250×32,7", "aco": "ASTM A572 Gr.50"}}},
        {"id": "v1", "tipo": "linha", "atributos": {"elemento": "viga", "material": "aco", "alinhamento": "topo", "secao": {"perfil": "W 150×22,5"}}},
        {"id": "t1", "tipo": "linha", "atributos": {"elemento": "trelica", "material": "aco",
                                                     "perfis": {"banzo_sup": "TQ 50×50×2,0", "banzo_inf": "TQ 50×50×2,0", "diagonal": "TQ 50×50×2,0"}}},
        {"id": "c1", "tipo": "polilinha", "atributos": {"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular"}}},
    ]}


def test_a_chave_e_a_mesma_da_analise():
    from nucleo3d.analise_estrutural import chave_do_grupo
    b = Barra(inicio=(0, 0, 0), fim=(1, 0, 0), perfil="TQ 50×50×2,0", papel="banzo", atributos={"papel_trelica": "banzo_inf"})
    assert TP.chave_da_barra(b) == chave_do_grupo({"papel": "banzo", "papel_trelica": "banzo_inf", "perfil": "TQ 50×50×2,0"})


def test_planta_troca_pilar_viga_e_a_diagonal_sem_levar_o_montante():
    pl = _planta()
    feitas, alin = TP.aplicar_na_planta(pl, {"pilar|W 250×32,7": "W 360×44,6", "diagonal|TQ 50×50×2,0": "TQ 60×60×2,0"})
    e = {x["id"]: x["atributos"] for x in pl["entidades"]}
    assert e["p1"]["secao"] == {"perfil": "W 360×44,6", "aco": "ASTM A572 Gr.50"}          # o aço fica
    assert e["v1"]["secao"]["perfil"] == "W 150×22,5"                                       # sem troca
    assert e["t1"]["perfis"]["diagonal"] == "TQ 60×60×2,0"
    assert e["t1"]["perfis"]["montante"] == "TQ 50×50×2,0"          # antes vinha da diagonal: não muda junto
    assert e["t1"]["perfis"]["banzo_sup"] == "TQ 50×50×2,0"
    assert feitas["pilar|W 250×32,7"] == 1 and feitas["diagonal|TQ 50×50×2,0"] == 1
    assert alin == {"v1": "topo"}
    assert e["c1"]["secao"] == {"tipo": "retangular"}                                       # o concreto não entra


def test_modelo_troca_as_barras_e_a_viga_pela_face_de_cima_fica_no_nivel():
    from nucleo3d.geometria import resolver_perfil as perfil
    doc = _doc()
    trocas = {"viga|W 150×22,5": "W 200×41,7", "diagonal|TQ 50×50×2,0": "TQ 60×60×2,0"}
    feitas = TP.aplicar_no_modelo(doc, trocas, {"v1": "topo"})
    por = {(b.atributos.get("papel_trelica") or b.papel): b for b in doc.entidades.values()}
    assert por["viga"].perfil == "W 200×41,7" and por["diagonal"].perfil == "TQ 60×60×2,0"
    assert por["montante"].perfil == "TQ 50×50×2,0" and por["pilar"].perfil == "W 250×32,7"
    dh = (perfil("W 200×41,7").d - perfil("W 150×22,5").d) / 2
    assert por["viga"].inicio[2] == pytest.approx(6000 - dh) and por["viga"].fim[2] == pytest.approx(6000 - dh)
    assert feitas == {"viga|W 150×22,5": 1, "diagonal|TQ 50×50×2,0": 1}


def test_sanfona_pelas_premissas_e_o_que_fica_so_na_analise():
    par = {"cobertura_movel": True, "perfil_sanfona": "TQ 50×50×2,0"}
    trocas = {"contraventamento|TQ 50×50×2,0": "TQ 40×40×2,0", "terça|Ue 150×60×20×2,00": "Ue 200×75×25×2,65"}
    fp = TP.aplicar_nos_parametros(par, trocas)
    assert par["perfil_sanfona"] == "TQ 40×40×2,0"
    linhas, ficam = TP.resumo({}, {}, fp, trocas)
    assert ficam == {"terça|Ue 150×60×20×2,00": "Ue 200×75×25×2,65"}                       # a terça de hipótese
    assert any("sanfona" in l for l in linhas)
