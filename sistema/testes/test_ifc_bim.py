# -*- coding: utf-8 -*-
"""A informação de produção do editor 3D no IFC (14/10/2026, o lado BIM): fase, acabamento, peça principal, ligação e
soldas saem no Pset_MetalicaCalculo; fase, acabamento e peça principal voltam na reimportação."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Documento  # noqa: E402
from ifc.exportar import exportar  # noqa: E402
from ifc.importar import importar  # noqa: E402


def test_fase_acabamento_e_principal_vao_e_voltam_pelo_ifc(tmp_path):
    doc = Documento()
    b = Barra(nome="viga", inicio=(0, 0, 0), fim=(6000, 0, 0), perfil="W 310×38,7", papel="viga",
              atributos={"marcas": {"posicao": "P7", "conjunto": "M3", "instancia": "c1", "principal": True},
                         "fase": "Lote 2", "acabamento": "galvanizado a fogo",
                         "ligacao": {"id": "L1", "tipo": "chapa_topo_joelho"},
                         "soldas": {"P9": {"tipo": "filete", "perna": 6, "lados": 2, "local": "fabrica"}}})
    doc.add(b)
    arq = str(tmp_path / "bim.ifc")
    exportar(doc, arq)
    texto = open(arq, encoding="utf-8", errors="replace").read()
    for frase in ("'Fase'", "Lote 2", "'Acabamento'", "'PecaPrincipal'", "chapa_topo_joelho", "P9: filete 6 mm 2 lados"):
        assert frase in texto, frase
    volta = importar(arq)
    peca = next(e for e in volta.entidades.values() if ((e.atributos or {}).get("marcas") or {}).get("posicao") == "P7")
    assert peca.atributos.get("fase") == "Lote 2"
    assert peca.atributos.get("acabamento") == "galvanizado a fogo"
    assert peca.atributos["marcas"].get("principal") is True


def test_lista_de_materiais_leva_fase_acabamento_e_solda_de_obra(tmp_path):
    import csv
    from nucleo2d import detalhar as det
    from nucleo3d import producao
    from saida import lista_producao as lp
    banzo = Barra(inicio=(0, 0, 0), fim=(3000, 0, 0), perfil="W 250×32,7", papel="viga",
                  atributos={"fase": "Lote 1", "acabamento": "pintura"})
    montante = Barra(inicio=(1500, 0, 129), fim=(1500, 0, 1129), perfil="W 250×32,7", papel="pilar",
                     atributos={"fase": "Lote 2"})
    doc = Documento()
    doc.add(banzo)
    doc.add(montante)
    for i, patch in producao.numerar(doc)["mudancas"].items():
        doc.entidades[i].atributos = dict(doc.entidades[i].atributos, **{k: v for k, v in patch.items() if v is not None})
    pb = banzo.atributos["marcas"]["posicao"]
    montante.atributos["soldas"] = {pb: producao.normalizar_definicao({"tipo": "filete", "perna": 6, "lados": 1, "local": "obra"})}
    lev = det.levantar(doc, regra_tercas=False)
    lista = lp.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"], projeto={"nome": "T"})
    linha = next(li for li in lista["posicoes"] if li["marca"] == pb)
    assert linha["fase"] == "Lote 1" and linha["acabamento"] == "pintura"
    assert len(lista["soldas_obra"]) == 1 and lista["soldas_obra"][0]["quantidade"] == 1
    arqs = lp.gravar(str(tmp_path), lista, lev["posicoes"], lev["acessorios"])
    rom = list(csv.reader(open(arqs["romaneio"], encoding="utf-8-sig"), delimiter=";"))
    assert rom[0][-2:] == ["Fase", "Acabamento"]
    sold = list(csv.reader(open(arqs["soldas"], encoding="utf-8-sig"), delimiter=";"))
    assert any(r[7] == "obra" for r in sold[1:])
