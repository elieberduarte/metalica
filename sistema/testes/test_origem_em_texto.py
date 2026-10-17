# -*- coding: utf-8 -*-
"""Regressão (16/10): o Verificar apoios caía no PRATI CD - Metálica — o script da obra (13/10) gravou em
`atributos.origem` o nome do DXF como texto ("PRATI CD - 09.10.2026.dxf, folhas 7…") em 1.086 peças, e o sistema lia
`origem` sempre como dicionário (apoios._elementos, alma_na_face._blocos — o mesmo caminho da regra 3.1 das tesouras —,
telhas, modelagem, esforços). nucleo3d.modelo.origem_de devolve sempre um dicionário."""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.dirname(os.path.abspath(__file__))
for p in (RAIZ, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

from nucleo3d.modelo import Barra, Solido                                  # noqa: E402

TEXTO = "PRATI CD - 09.10.2026.dxf, folhas 7 (locação de placas) e 8–10 (fachadas)"


def _modelo_prati():
    """a tesoura do teste da troca por grupo (origem em dicionário) + peças como as do script do PRATI (origem em
    texto): um pilar, uma terça e um sólido (a placa)"""
    from test_troca_por_grupo import _modelo
    doc = _modelo(z=85000.0)
    doc.add(Barra(nome="PILAR", inicio=(0, 0, 0), fim=(0, 0, 85000.0), perfil="W 250×32,7", papel="pilar",
                  atributos={"origem": TEXTO}))
    doc.add(Barra(nome="TERÇA", inicio=(0, 3000, 86200.0), fim=(5000, 3000, 86200.0), perfil="Ue 150×60×20×2,00",
                  papel="terça", atributos={"origem": TEXTO}))
    doc.add(Barra(nome="ALMA", inicio=(0, 1500, 85000.0), fim=(0, 3000, 86000.0), perfil="U 100×50×3,00 (FF)",
                  papel="diagonal", atributos={"origem": TEXTO, "papel_trelica": "diagonal"}))
    doc.add(Solido(nome="PLACA", vertices=[(0, 0, 0), (300, 0, 0), (300, 300, 0), (0, 300, 0), (0, 0, 20), (300, 0, 20),
                                            (300, 300, 20), (0, 300, 20)],
                   faces=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]],
                   atributos={"origem": TEXTO}))
    return doc


def test_origem_de_sempre_dicionario():
    from nucleo3d.modelo import origem_de
    assert origem_de(Barra(atributos={"origem": TEXTO})) == {}
    assert origem_de(Barra(atributos={"origem": {"peca": "T1"}})) == {"peca": "T1"}
    assert origem_de(Barra(atributos={})) == {}
    assert origem_de({"atributos": {"origem": TEXTO}}) == {}
    assert origem_de(None) == {}


def test_verificar_apoios_com_origem_em_texto():
    from nucleo3d import apoios
    r = apoios.verificar(_modelo_prati())
    assert isinstance(r, dict)


def test_regras_e_encaixe_com_origem_em_texto():
    from nucleo3d import alma_na_face, regras_trelica
    doc = _modelo_prati()
    ents = list(doc.entidades.values())
    regras_trelica.conferir(ents)
    alma_na_face.encaixar(ents)
    alma_na_face.aparar(ents)
    regras_trelica.aplicar(ents)


def test_troca_por_grupo_com_origem_em_texto():
    from nucleo3d import troca_por_grupo
    r = troca_por_grupo.aplicar(_modelo_prati(), [{"grupo": "diagonais", "forma": "dupla", "para": "L 40×3 (FF)"}])
    assert r["novas"]
