# -*- coding: utf-8 -*-
"""A chapa de aço que segura a calha ("SC1 suporte de calha #3 × 70") é aço, não funilaria.

SESI Chapecó (auditor-de-numeros, 02/11, N22): o `_RE_CALHA` da `ifc.importar.funilaria` pegava o "calha" de "suporte de
calha". Os 200 suportes SC1–SC4 (chapa #3, 207,8 kg) iam para a categoria RUFOS, a camada 2D CALHAS e a marca CL1–CL4.
O resumo os tirava do aço (133.677,1 × 133.884,8 da lista) e os mostrava em "Rufos e calhas"."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifc.importar import camada_semantica, funilaria      # noqa: E402


def test_quem_segura_a_funilaria_nao_e_funilaria():
    for nome in ("SC1 suporte de calha #3 × 70", "SUP. CALHA", "Suporte p/ calha", "Suportes das calhas",
                 "Apoio da calha", "Mão francesa da calha", "Cantoneira de rufo", "Gancho de calha"):
        assert funilaria(nome) == "", nome
        assert camada_semantica("IfcPlate", nome) == "Chapas", nome
    for nome, f in (("Calha CM4 (chapa galv. #1,0, corte A)", "calha"), ("CALHA 1", "calha"), ("RUFO CHAPEU 1", "rufo"),
                    ("CONTRARRUFO 2", "rufo"), ("CUMEEIRA I7.5", "rufo")):
        assert funilaria(nome) == f, nome


def test_no_resumo_o_suporte_fica_no_aco():
    from nucleo3d.modelo import Barra, Chapa, Documento
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    doc = Documento(nome="sesi-suporte")
    doc.add(Barra(nome="V", inicio=(0.0, 0.0, 6000.0), fim=(6000.0, 0.0, 6000.0), perfil="W 200×19,3", papel="viga"))
    for k in range(4):           # como o telhas_sesi.py grava: chapa solta, conjunto SC1, camada da cobertura
        doc.add(Chapa(nome="SC1 suporte de calha #3 × 70", camada="Coberturas — Suportes de calha",
                      origem=(1000.0 * k, 500.0, 6100.0), eixo_x=(0.0, 1.0, 0.0), eixo_y=(1.0, 0.0, 0.0),
                      contorno=[(0, -35), (683, -35), (683, 35), (0, 35)], espessura=3.0,
                      atributos={"conjunto": "SC1", "marcas": {"conjunto": "SC1", "perfil": "SC1 suporte de calha #3 × 70",
                                                               "nome_conjunto": "SC1"}}))
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    sc = [p for p in r["objetos_posicoes"] if "suporte de calha" in (p.perfil or "")]
    assert sc and all(cat[p.marca] == "CHAPAS" for p in sc), [(p.marca, p.perfil, cat[p.marca]) for p in sc]
    assert all(r["camadas"].get(p.marca) != "CALHAS" for p in sc), [(p.marca, r["camadas"].get(p.marca)) for p in sc]
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "s"})
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
    R = resumos.levantar_resumos(doc, lev, lista, r.get("nomes") or {}, {})
    aco = R["numeros"]["peso_aco"]
    assert abs(aco - lista["totais"]["peso"]) < 0.1, (aco, lista["totais"]["peso"])
    assert not R.get("funilaria"), R.get("funilaria")
    assert abs(R["perfis_kg"] + R["chaparia_total"]["kg"] - aco) < 0.1
