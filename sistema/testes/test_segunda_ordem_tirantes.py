# -*- coding: utf-8 -*-
"""A 2ª ordem com os tirantes só à tração (nucleo3d/segunda_ordem.py), nos casos em que ela errava (12/11):

* o liga-desliga dos tirantes ciclava e a combinação saía "instável" sem ser (tesoura 20×40 do configurador, V0 45,
  ELU V↑ cpi+0,2: 30 passos sem convergir; Madrid 04/11: 6 ↔ 7 tirantes);
* o Δ1 era medido com todos os tirantes e o Δ2 sem os comprimidos — a razão media a troca de rigidez (galpão de 12 m,
  ELU V↓ cpi−0,3: Δ2/Δ1 = 1,93 "grande"; Madrid B2: 3,24);
* Δ1 de décimos de mm dava razão de ruído (Madrid, tesoura leve: Δ1 = 0,1 mm → "grande");
* a matriz singular já no 1º passo saía como "carga crítica atingida" — era mecanismo (Madrid N.3, 10/11)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d import segunda_ordem as SO  # noqa: E402
from test_segunda_ordem_verificacao import SEC, _barra, _pilar  # noqa: E402


def _galpao(**kw):
    from test_galpao import _cap16
    from nucleo.galpao import dimensionar
    from nucleo3d import de_projeto
    p = dimensionar(_cap16(v0=45.0, base_rotulada=False, **kw))
    r = AE.calcular(de_projeto.modelo_do_galpao(p), {"base": "engastada", "telha": 0.105, "sobrecarga": p.cargas["sobrecarga"],
                                                      "v0": 45.0, "categoria": "II", "classe": "B", "modelo_vento": "fechado"})
    return r["segunda_ordem"]["combinacoes"]


@pytest.fixture(scope="module")
def tesoura():
    return _galpao(tipo_portico="treliçado")


@pytest.fixture(scope="module")
def pe_direito_12():
    return _galpao(pe_direito=12.0)


def test_tirantes_que_oscilam_congelam_e_a_combinacao_converge(tesoura):
    r = tesoura["ELU V↑ cpi+0,2"]
    assert r["convergiu"] and r["instavel"] is None, r
    assert r["iteracoes"] < SO.MAX_ITERACOES
    assert all(x["convergiu"] for x in tesoura.values())


def test_delta1_com_os_mesmos_tirantes_desligados(pe_direito_12, tesoura):
    r = pe_direito_12["ELU V↓ cpi−0,3"]
    assert r["tirantes_desligados"] > 0
    assert r["razao"] < 1.10, r                         # era 1,93 ("grande") com Δ1 de todos os tirantes ligados
    assert max(x["razao"] for x in tesoura.values() if x.get("razao")) < 1.10


def test_delta1_de_decimos_de_mm_nao_da_razao():
    M = _pilar()
    Pcr = np.pi ** 2 * SO.FATOR_RIGIDEZ * AE.E_ACO * SEC["Iz"] / (4 * 6.0 ** 2)
    topo = len(M["nos"]) - 1
    casos = {"G": {"dist": {}, "nodal": {}, "nos": {topo: np.array([0, 0, -0.5 * Pcr])}},
             "V1": {"dist": {}, "nodal": {}, "nos": {topo: np.array([0.05, 0, 0])}}}       # Δ1 ≈ 0,2 mm
    sol = AE.resolver(M, casos)
    r = SO.analisar(M, sol, {"ELU V1": {"tipo": "ELU", "fatores": {"G": 1.0, "V1": 1.0}, "descricao": ""}})["ELU V1"]
    assert r["delta1_mm"] < 0.5 and r["instavel"] is None
    assert "razao" not in r and "não se mede" in r["razao_nota"]


def test_mecanismo_no_primeiro_passo_nao_e_carga_critica():
    # pilar de base rotulada segurado em x só por um tirante, que o vento comprime: na 1ª ordem o tirante trabalha (estável);
    # na 2ª ele sai (só tração) e o pilar gira em torno da base já no 1º passo — mecanismo, não carga crítica
    nos = np.array([[0, 0, 0], [0, 0, 6], [6, 0, 0], [0, 6, 0]], float)
    tirante = dict(SEC, A=1.27e-4, Iz=1.3e-9, Iy=1.3e-9, J=2.6e-9, Wz=2e-7, Wy=2e-7, redonda=True)
    bs = [_barra(nos, 0, 1), _barra(nos, 1, 2, sec=tirante, ids=("t1",), papel="contraventamento"),
          _barra(nos, 1, 3, sec=tirante, ids=("t2",), papel="contraventamento")]
    M = {"nos": nos, "barras": bs, "par": dict(AE.PARAMETROS_PADRAO),
         "apoios": [{"no": n, "tipo": "rotulada", "chave": str(n)} for n in (0, 2, 3)]}
    casos = {"G": {"dist": {}, "nodal": {}, "nos": {1: np.array([0, 0, -10.0])}},
             "V1": {"dist": {}, "nodal": {}, "nos": {1: np.array([2.0, 0, 0])}}}            # empurra o topo para o tirante
    sol = AE.resolver(M, casos)
    assert sol["instavel"] is None
    r = SO.analisar(M, sol, {"ELU V1": {"tipo": "ELU", "fatores": {"G": 1.0, "V1": 1.0}, "descricao": ""}})["ELU V1"]
    assert r["instavel"] and "mecanismo" in r["instavel"] and "carga crítica atingida" not in r["instavel"], r["instavel"]
    assert 1 in r["mecanismo_nos"]
