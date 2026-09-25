# -*- coding: utf-8 -*-
"""Rufos e calhas no detalhamento: a barra comprida solta de funilaria não é mais
agulhamento — sai com o nome RF/CL, na camada 2D RUFOS/CALHAS, no quadro dela do desenho
de extras, na categoria "Rufos e calhas" e fora do peso de aço do resumo."""
import math
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
