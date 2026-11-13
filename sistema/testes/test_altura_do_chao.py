# -*- coding: utf-8 -*-
"""A altura do chão sem o local da obra (usuário, 13/11: "o terreno não habilita a parte de ajuste fino que já temos quando
não tem uma imagem de satélite importada, poderia deixar essa ferramenta disponível a mão para isso mesmo sem ter um terreno
importado"; escolhido: a altura e o ajuste de 5 cm valem para o chão liso do 3D e a sombra; os planos do chão seguem só com
imagem). saida/local_obra.py: `chao` no projeto ({cota?, ajuste?}, mm) sem o local; o local novo herda; Tirar o local
devolve a altura ao chão."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import local_obra as L                       # noqa: E402

LUGAR = {"lat": -24.9555, "lon": -53.4552, "ponto": [0, 0], "norte": 0, "fonte": "esri"}


class G:
    """O gerente de projetos de mentira: o projeto.json num dicionário."""
    def __init__(self, pasta): self.p, self._pasta = {}, pasta
    def ler(self, s): return dict(self.p)
    def tocar(self, s, **k): self.p.update(k)
    def pasta(self, s): return self._pasta


def test_altura_sem_local_fica_no_projeto(tmp_path):
    g = G(str(tmp_path))
    e = L.rota_post(g, "obra", ["chao"], {"cota": -500, "ajuste": 100}, lambda *a: None)
    assert e["terreno"] is None and e["chao"] == {"cota": -500.0, "ajuste": 100.0}
    assert g.p["chao"] == {"cota": -500.0, "ajuste": 100.0}
    assert L.estado(g, "obra")["chao"] == {"cota": -500.0, "ajuste": 100.0}
    # de volta ao automático: o chão some do projeto (o pé da obra)
    e = L.rota_post(g, "obra", ["chao"], {}, lambda *a: None)
    assert e["chao"] is None and g.p["chao"] is None


def test_o_local_novo_herda_a_altura_do_chao(tmp_path):
    g = G(str(tmp_path))
    L.gravar_chao(g, "obra", {"cota": -500, "ajuste": -50})
    e = L.gravar(g, "obra", dict(LUGAR))                   # a busca do painel manda o lugar sem a altura
    assert e["terreno"]["cota"] == -500.0 and e["terreno"]["ajuste"] == -50.0
    assert g.p["chao"] is None                             # uma altura só: a do local
    # o local que já tem a altura dele não pega a do chão
    g2 = G(str(tmp_path))
    L.gravar_chao(g2, "obra", {"cota": -500})
    assert L.gravar(g2, "obra", dict(LUGAR, cota=0))["terreno"]["cota"] == 0.0


def test_com_local_a_altura_do_chao_e_a_do_local(tmp_path):
    g = G(str(tmp_path))
    L.gravar(g, "obra", dict(LUGAR, cota=-30))
    e = L.gravar_chao(g, "obra", {"ajuste": 50})
    assert "cota" not in e["terreno"] and e["terreno"]["ajuste"] == 50.0 and e["terreno"]["lat"] == LUGAR["lat"]
    assert not g.p.get("chao")


def test_tirar_o_local_devolve_a_altura_ao_chao(tmp_path):
    g = G(str(tmp_path))
    L.gravar(g, "obra", dict(LUGAR, cota=-1200, ajuste=-200))
    e = L.rota_post(g, "obra", ["esquecer"], {}, lambda *a: None)
    assert e["terreno"] is None and e["chao"] == {"cota": -1200.0, "ajuste": -200.0}
    # sem altura no local: nada no chão
    g2 = G(str(tmp_path))
    L.gravar(g2, "obra", dict(LUGAR))
    assert L.esquecer(g2, "obra")["chao"] is None


@pytest.mark.parametrize("corpo, erro", [({"cota": "abc"}, "número"), ({"ajuste": 200_000}, "100 m"),
                                         ({"cota": float("inf")}, "número")])
def test_altura_invalida(tmp_path, corpo, erro):
    with pytest.raises(L.ErroTerreno, match=erro):
        L.gravar_chao(G(str(tmp_path)), "obra", corpo)
