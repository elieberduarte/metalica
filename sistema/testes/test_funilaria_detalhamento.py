# -*- coding: utf-8 -*-
"""Rufos e calhas no detalhamento: a barra comprida solta de funilaria não é mais
agulhamento — sai com o nome RF/CL, na camada 2D RUFOS/CALHAS, no quadro dela do desenho
de extras, na categoria "Rufos e calhas" e fora do peso de aço do resumo."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido                        # noqa: E402


def _barra(x0, x1, y, largura, altura, perfil):
    """Caixa ao longo de x (4 vértices por ponta), deitada: a funilaria como vem do IFC."""
    vs = []
    for x in (x0, x1):
        for dy, dz in ((0, 0), (largura, 0), (largura, altura), (0, altura)):
            vs.append((float(x), float(y + dy), float(dz) + 3000.0))
    faces = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome=perfil, camada="Vigas", vertices=vs, faces=faces,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"perfil": perfil},
                             "propriedades": {"Steel & Graphics Common": {"Grade": "ALUZINC", "Profile": perfil}}})


def test_rufo_e_calha_saem_do_agulhamento():
    from nucleo2d.detalhar import detalhar
    doc = Documento(nome="t")
    doc.add(_barra(0, 12000, 0, 300, 100, "RUFO CHAPEU 1"))
    doc.add(_barra(0, 12000, 5000, 300, 100, "RUFO CHAPEU 1"))
    doc.add(_barra(0, 9000, 9000, 450, 260, "CALHA 1"))
    r = detalhar(doc, grupos=["extras", "agulhamentos"], converter=False)
    pos = {p["marca"]: p for p in r["posicoes"]}
    assert pos["RUFO CHAPEU 1"]["tipo"] == "rufo" and pos["RUFO CHAPEU 1"]["nome"] == "RF1" and pos["RUFO CHAPEU 1"]["quantidade"] == 2
    assert pos["CALHA 1"]["tipo"] == "calha" and pos["CALHA 1"]["nome"] == "CL1"
    ext = r["desenhos"]["extras"]
    camadas = {e.camada for e in ext.entidades.values()}
    assert "RUFOS" in camadas and "CALHAS" in camadas
    textos = {getattr(e, "texto", "") for e in ext.entidades.values()}
    assert "RUFOS" in textos and "CALHAS" in textos
    ag = r["desenhos"].get("agulhamentos")
    assert ag is None or not any(e.camada in ("RUFOS", "CALHAS") for e in ag.entidades.values())
    assert not any("RUFO" in a for a in r.get("avisos", []))       # sem aviso de peso teórico


def test_categoria_e_resumo_fora_do_aco():
    from nucleo2d.detalhe.base import _categoria, PREFIXO_NOME, CATEGORIAS
    from saida.resumos import FORA_DO_ACO, _FAMILIA_DO_TIPO, FAMILIAS

    class P:
        classe, perfil = "barra", "RUFO CHAPEU 2"
    assert _categoria(P(), "") == "RUFOS" and "RUFOS" in CATEGORIAS
    assert PREFIXO_NOME["rufo"] == "RF" and PREFIXO_NOME["calha"] == "CL"
    assert _FAMILIA_DO_TIPO["rufo"] == "funilaria" and "funilaria" in FAMILIAS and "funilaria" in FORA_DO_ACO


def _calha_u(x0, x1, y, largura, altura, t, perfil, camada="Calhas"):
    """A calha em U de chapa fina, extrudada ao longo de x, como o TecnoMETAL a exporta: o nome da peça ("cl.") no
    lugar do perfil e a seção de chapa ida e volta (8 pontos)."""
    sec = [(0, altura), (0, 0), (largura, 0), (largura, altura), (largura - t, altura), (largura - t, t), (t, t), (t, altura)]
    vs = [(float(x), float(y + a), float(b) + 3000.0) for x in (x0, x1) for a, b in sec]
    n = len(sec)
    faces = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return Solido(nome=perfil, camada=camada, vertices=vs, faces=faces,
                  atributos={"tipo_ifc": "IfcMember", "marcas": {"perfil": perfil},
                             "propriedades": {"SteelXData": {"ElementName": "PL%gx%gx%g" % (t, x1 - x0, 0), "ModelRole": "CALHA",
                                                             "SinglePartMark": perfil}}})


def test_calha_do_ifc_com_desenvolvimento_e_peso_teorico():
    """Mall 09/11 (usuário: "as calhas precisa ter o comprimento total, normalmente orçamento com o desenvolvimento ou
    largura que é comprado a chapa da bobina"): a calha "cl." do TecnoMETAL saía no Resumo de materiais com o
    desenvolvimento "—", 0 m² e no aviso "posições sem peso teórico". A seção de chapa fina dá o desenvolvimento
    (contorno / 2 − t, mm inteiro de cima) e a espessura; a lista e o resumo levam os dois."""
    from nucleo2d import detalhar as det
    from saida.lista_producao import _linha_posicao
    from saida.resumos import funilaria_da_lista
    doc = Documento(nome="t")
    doc.add(_calha_u(0, 9000, 0, 300, 200, 0.5, "cl."))
    lev = det.levantar(doc, regra_tercas=False)
    p = next(p for p in lev["posicoes"] if p.perfil == "cl.")
    # contorno da seção 1.399 → meio 699,5; t = 349,5 / 699,5 = 0,4996; desenvolvimento 699,0 → 699
    assert getattr(p, "chapa_fina", None) == (699, 0.5), getattr(p, "chapa_fina", None)
    assert not p.sem_peso_teorico
    assert not any("sem peso teórico" in a for a in lev["avisos"]), lev["avisos"]
    assert abs(p.peso - 699 * 9000 * 0.5 * 7.85e-6) < 0.01
    linha = _linha_posicao(p, "RUFOS")
    assert linha["largura"] == 699 and linha["espessura"] == 0.5 and linha["area_m2"] > 6.2
    linha["nome"] = linha["nome"] or "CL1"              # o nome de produção (a lista do sistema o dá)
    f = funilaria_da_lista({"posicoes": [linha]})[0]
    assert f["tipo"] == "Calha" and f["desenvolvimento"] == 699 and abs(f["comprimento"] - 9000) < 1
    assert abs(f["ml"] - 9.0) < 0.01 and abs(f["m2"] - 6.291) < 0.01


def test_barra_grossa_de_perfil_desconhecido_nao_vira_chapa_fina():
    """O limite da regra: a seção de 3 mm (um dobrado de nome desconhecido) não é calha nem rufo."""
    from nucleo2d import detalhar as det
    doc = Documento(nome="t")
    doc.add(_calha_u(0, 6000, 0, 150, 60, 3.0, "XYZ 99", camada="Vigas"))
    lev = det.levantar(doc, regra_tercas=False)
    p = next(p for p in lev["posicoes"] if p.perfil == "XYZ 99")
    assert getattr(p, "chapa_fina", None) is None
