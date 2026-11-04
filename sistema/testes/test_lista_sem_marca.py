# -*- coding: utf-8 -*-
"""A peça sem marca de posição não vira UMA posição pelo nome — e a chapa sai com a espessura, não com a própria marca.

Mall Av. Londrina (IFC4 do SteelX, 04/11/2026): o SteelX grava MainPartMark "indefinido" e nenhum SinglePartMark em 170
peças, e o nome delas é o perfil. As barras de malha (sólidos IfcMember) caíam numa posição só, com o comprimento da 1ª
e a quantidade de todas — Ue 400×70×25×3,75 dava 10,56 m / 177 kg (o certo 204,88 m / 3.383 kg), Ue 300×70×25×2,25
166 m / 1.413 kg (o certo 71,26 m / 598). A correção de 03/10 (dd3ff55, os 480 U 150×50 da Portaria a 34,2 m, 143,7 t)
só olhava a barra paramétrica. E as chapas do SteelX vinham com o perfil = a marca ("ch.12", "pb.2"), sem a espessura: a
conferência do RESUMO (só o que começa com "CH ") as lia como perfis."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                          # noqa: E402
from nucleo3d.modelo import Chapa, Documento, Solido          # noqa: E402
from test_detalhamento import perfil_u                        # noqa: E402


def _ue(nome, L, dy, posicao=None):
    v, f = perfil_u(L, 400.0, 70.0, 3.75)
    s = Solido(nome=nome, camada="Barras", vertices=[(x, y + dy, z) for x, y, z in v], faces=f)
    s.material = "ASTM A36"
    s.atributos["tipo_ifc"] = "IfcMember"
    s.atributos["marcas"] = {"posicao": posicao or "", "conjunto": "", "perfil": "Ue 400×70×25×3,75"}
    return s


def _obra():
    """Como o SteelX entrega: Ue de malha sem marca, de comprimentos diferentes (pórtico, 528 mm a 14,4 m), duas iguais;
    uma barra com marca de verdade; e as chapas paramétricas com o perfil igual à marca."""
    doc = Documento(nome="mall")
    for i, L in enumerate((528.0, 14400.0, 14400.0, 6250.0)):
        doc.add(_ue("Ue 400x70x25x3,75mm", L, i * 1000.0))
    doc.add(_ue("Ue 400x70x25x3,75mm", 3000.0, 9000.0, posicao="tc.9"))
    for i, (marca, t) in enumerate((("ch.12", 8.0), ("ch.12", 8.0), ("ch.1", 3.0))):
        c = Chapa(nome=marca, camada="Chapas", origem=(i * 1000.0, 20000.0, 0.0),
                  contorno=[(0, 0), (300, 0), (300, 200), (0, 200)], espessura=t)
        c.atributos["tipo_ifc"] = "IfcPlate"
        c.atributos["marcas"] = {"posicao": marca, "conjunto": "", "perfil": marca}
        doc.add(c)
    return doc


def _barras(lev):
    return [p for p in lev["posicoes"] if p.classe not in ("chapa", "chapa_dobrada")]


def test_barra_de_malha_sem_marca_separada_pelo_comprimento():
    lev = det.levantar(_obra())
    sem = sorted((round(p.comprimento), p.quantidade) for p in _barras(lev) if p.marca != "tc.9")
    assert sem == [(528, 1), (6250, 1), (14400, 2)], sem


def test_o_comprimento_total_e_o_peso_batem_com_as_pecas():
    lev = det.levantar(_obra())
    total_m = sum(p.comprimento * p.quantidade for p in _barras(lev)) / 1000.0
    assert abs(total_m - (0.528 + 14.4 * 2 + 6.25 + 3.0)) < 0.01, total_m


def test_a_barra_com_marca_continua_com_a_marca():
    lev = det.levantar(_obra())
    assert [p.quantidade for p in lev["posicoes"] if p.marca == "tc.9"] == [1]


def test_chapa_com_o_perfil_igual_a_marca_sai_pela_espessura():
    lev = det.levantar(_obra())
    ch = {p.marca: p for p in lev["posicoes"] if p.classe in ("chapa", "chapa_dobrada")}
    assert ch["ch.12"].perfil == "CH 8" and ch["ch.12"].quantidade == 2, (ch["ch.12"].perfil, ch["ch.12"].quantidade)
    assert ch["ch.1"].perfil == "CH 3", ch["ch.1"].perfil


def test_toco_de_ue_mais_curto_que_a_altura_sai_pelo_eixo():
    """Mall (04/11, depois da separação): as 6 Ue 500×75×25×3,00 paramétricas de 250 e 248 mm (vigas, sem marca) saíam com
    680 mm — a maior aresta da alma é a altura (500), e o reconhecimento do toco (o B.14 de 155 mm num W250) só valia para
    o laminado: "Ue 500" não casava com o U seguido do número. +2,58 m e +42 kg na Ue 500 do RESUMO."""
    from nucleo3d.modelo import Barra
    doc = Documento(nome="toco")
    for i, (L, eixo) in enumerate(((250.0, (1, 0, 0)), (248.0, (0, 1, 0)), (6000.0, (1, 0, 0)))):
        o = (0.0, i * 2000.0, 3000.0)
        b = Barra(nome="Ue 500×75×25×3,00", camada="Barras", inicio=o,
                  fim=(o[0] + eixo[0] * L, o[1] + eixo[1] * L, o[2]), perfil="Ue 500×75×25×3,00", papel="viga")
        doc.add(b)
    lev = det.levantar(doc)
    assert sorted(round(p.comprimento) for p in lev["posicoes"]) == [248, 250, 6000], \
        [(p.marca, p.comprimento) for p in lev["posicoes"]]
