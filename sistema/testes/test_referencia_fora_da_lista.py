# -*- coding: utf-8 -*-
"""A referência de outro projeto (o arquitetônico, o concreto do TQS) fica só no 3D: fora da lista de materiais, do
Quadro 8 (pré-moldados), dos acessórios e da compra.

O auditor-de-numeros achou isso em duas obras, de dois jeitos:
- Hora Certa · Galpão Novo, N06 de 30/10: os 798 sólidos "ARQ — " do arquitetônico de referência (`atributos.
  referencia_arquitetonica`) iam ao Quadro 8 como concreto/vidro, 5.789 t (o painel isotérmico a 2.500 kg/m³, o piso de
  3.145 t);
- SESI Chapecó, N29 e N09 de 02/11: o ACM (323,7 t), o vidro (104 t) e o drywall como concreto no Quadro 8; e os letreiros
  e murais da comunicação visual (IfcBuildingElementProxy, material só com a cor, "CV #000000") contados como "Porca 1\""
  na compra.
O Mall Av. Londrina marca a referência com `atributos.referencia` ("concreto TQS V4 (27/05/2026)", "arquitetônico Verri &
Galvão…"), e a Vicente Residence também ("deck — não é aço (fica fora da lista)").

O concreto que É do projeto (o pré-moldado, a laje alveolar do Capitão) continua no Quadro 8 (test_fora_do_aco)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import detalhar as det                          # noqa: E402
from nucleo2d.detalhe.base import _fixadores, referencia_de_outro_projeto  # noqa: E402
from nucleo3d import producao                                 # noqa: E402
from nucleo3d.modelo import Solido                            # noqa: E402
from test_detalhar2d import _modelo                           # noqa: E402
from test_fora_do_aco import _caixa                           # noqa: E402


def _ref(nome, tipo_ifc, camada, material, dims, desloc=(0.0, 0.0, 0.0), **atributos):
    v, f = _caixa(*dims, dx=desloc[0], dy=desloc[1], dz=desloc[2])
    s = Solido(nome=nome, camada=camada, vertices=v, faces=f)
    s.material = material
    s.atributos["tipo_ifc"] = tipo_ifc
    s.atributos.update(atributos)
    return s


def _obra():
    """O aço do teste do detalhamento + a referência como chega nas obras (os nomes, camadas e materiais de lá)."""
    doc = _modelo()
    arq = {"referencia_arquitetonica": True, "elemento_arq": "parede", "fonte": "ARQ", "id_arq": "x"}
    # Galpão Novo: a parede de fachada e o vidro
    doc.add(_ref("Painel isotérmico fachada A", "IfcWall", "ARQ — Paredes de fachada", "Concreto",
                 (30000.0, 100.0, 9000.0), (0.0, 20000.0, 0.0), **arq))
    doc.add(_ref("Vidro da recepção", "IfcWindow", "ARQ — Vidros e esquadrias", "Vidro",
                 (4000.0, 10.0, 2500.0), (0.0, 21000.0, 0.0), **arq))
    # SESI: o ACM da platibanda e o letreiro sem material (só a cor), que ia à compra como porca
    doc.add(_ref("Platibanda fachada A — ACM e estrutura", "IfcBuildingElementProxy", "ARQ — Platibandas", "ACM",
                 (20000.0, 300.0, 1200.0), (0.0, 22000.0, 9000.0), **arq))
    doc.add(_ref("Letreiro SESI Escola de Referência", "IfcBuildingElementProxy", "ARQ — Comunicação visual",
                 "CV #000000", (40.0, 20.0, 30.0), (0.0, 23000.0, 3000.0), **arq))
    # a viga do arquitetônico sem material: com o tipo de peça, viraria posição de aço
    doc.add(_ref("Viga do arquitetônico", "IfcMember", "ARQ — Vigas de concreto", "",
                 (6000.0, 150.0, 400.0), (0.0, 24000.0, 4000.0), **arq))
    # Mall: o concreto do TQS e a alvenaria do arquitetônico pela `referencia`
    doc.add(_ref("V101", "IfcBeam", "ARQ — Pilares e vigas", "Concreto C30", (7000.0, 200.0, 600.0),
                 (0.0, 25000.0, 0.0), referencia="concreto TQS V4 (27/05/2026)", exportar=False))
    doc.add(_ref("Parede", "IfcWall", "ARQ — Paredes", "Alvenaria", (5000.0, 140.0, 3000.0), (0.0, 26000.0, 0.0),
                 referencia="arquitetônico Verri & Galvão EXE R1 (12/05/2026)", exportar=False))
    # o concreto do próprio projeto (o pré-moldado): fica no Quadro 8
    doc.add(_ref("LAJE ALVEOLAR", "IfcBeam", "IfcBeam", "CONCRETE/FCK 30", (7880.0, 1245.0, 200.0), (0.0, 30000.0, 0.0)))
    return doc


REFERENCIAS = {"Painel isotérmico fachada A", "Vidro da recepção", "Platibanda fachada A — ACM e estrutura",
               "Letreiro SESI Escola de Referência", "Viga do arquitetônico", "V101", "Parede"}


def test_referencia_fica_fora_do_quadro_8_e_o_pre_moldado_continua():
    lev = det.levantar(_obra())
    nomes = {g["nome"] for g in lev["fora_do_aco"]}
    assert not (nomes & REFERENCIAS), nomes & REFERENCIAS
    assert "LAJE ALVEOLAR" in nomes


def test_referencia_nao_vira_posicao_de_aco_nem_acessorio():
    doc = _obra()
    lev = det.levantar(doc)
    marcas = {p.marca for p in lev["posicoes"]} | {p.nome for p in lev["posicoes"]}
    assert not (marcas & REFERENCIAS), marcas & REFERENCIAS
    # o letreiro sem material ia aos acessórios (e à compra como porca solta)
    assert not any("Letreiro" in str(k) or k == "IfcBuildingElementProxy" for k in lev["acessorios"]), lev["acessorios"]
    assert not any(referencia_de_outro_projeto(f) for f in _fixadores(doc))


def test_o_peso_de_aco_e_o_mesmo_com_e_sem_a_referencia():
    so_aco = det.levantar(_modelo())
    com_ref = det.levantar(_obra())
    peso = lambda lev: round(sum(p.peso * p.quantidade for p in lev["posicoes"]), 1)  # noqa: E731
    assert peso(com_ref) == peso(so_aco)
    assert len(com_ref["posicoes"]) == len(so_aco["posicoes"])


def test_o_aviso_diz_quantas_ficaram_so_no_3d():
    lev = det.levantar(_obra())
    aviso = [a for a in lev["avisos"] if "referência" in a]
    assert aviso and aviso[0].startswith("7 peça(s)"), lev["avisos"]


def test_a_mesma_escolha_nas_entidades_de_producao():
    """nucleo3d.producao faz a mesma escolha do levantamento (sem montar malha): a referência sem material também fica de fora."""
    nomes = {e.nome for e in producao.pecas_de_producao(_obra())}
    assert not (nomes & REFERENCIAS), nomes & REFERENCIAS


def test_o_motivo():
    doc = _obra()
    por_nome = {e.nome: e for e in doc.entidades.values()}
    assert referencia_de_outro_projeto(por_nome["Vidro da recepção"]) == "arquitetônico de referência"
    assert referencia_de_outro_projeto(por_nome["V101"]) == "concreto TQS V4 (27/05/2026)"
    assert referencia_de_outro_projeto(por_nome["LAJE ALVEOLAR"]) == ""
