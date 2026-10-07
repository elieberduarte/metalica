"""A etapa 4 da análise estrutural: a 2ª ordem (nucleo3d/segunda_ordem.py) e a verificação por peça
(nucleo3d/verificacao_pecas.py) contra os casos de livro — o pilar em balanço com P e H (amplificação 1/(1 − P/Pcr) e o
momento na base H·L + P·Δ), a carga acima da crítica, os comprimentos de flambagem pelos travamentos e o uso de um pilar
comprimido igual a N/Nc,Rd da NBR 8800."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d import segunda_ordem as SO  # noqa: E402
from nucleo3d import verificacao_pecas as VP  # noqa: E402

SEC = {"A": 0.01, "Iz": 1e-4, "Iy": 2e-5, "J": 1e-6, "Wz": 1e-3, "Wy": 2e-4, "kg_m": 0.0, "tipo": "I"}


def _barra(nos, a, b, sec=SEC, ids=("p",), papel="pilar", perfil="", rot=0.0):
    return {"a": a, "b": b, "L": float(np.linalg.norm(nos[b] - nos[a])), "papel": papel, "sec": sec,
            "R": AE._eixos(nos[a], nos[b], rot), "soltos": [], "papel_trelica": None, "elemento": None, "grupo": None,
            "marca": None, "perfil": perfil, "ids": list(ids), "aco": "ASTM A572 Gr.50"}


def _pilar(L=6.0, nel=8, sec=SEC, perfil=""):
    nos = np.array([[0, 0, L * k / nel] for k in range(nel + 1)], float)
    bs = [_barra(nos, k, k + 1, sec=sec, perfil=perfil) for k in range(nel)]
    return {"nos": nos, "barras": bs, "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"}], "par": dict(AE.PARAMETROS_PADRAO)}


def _segunda(M, P, H):
    topo = len(M["nos"]) - 1
    casos = {"G": {"dist": {}, "nodal": {}, "nos": {topo: np.array([0, 0, -P])}},
             "V1": {"dist": {}, "nodal": {}, "nos": {topo: np.array([H, 0, 0])}}}
    sol = AE.resolver(M, casos)
    combs = {"ELU V1": {"tipo": "ELU", "fatores": {"G": 1.0, "V1": 1.0}, "descricao": ""}}
    return sol, combs, SO.analisar(M, sol, combs)["ELU V1"]


def test_lote_igual_a_rigidez_de_uma_barra():
    M = _pilar(L=5.0, nel=1)
    lt = AE._lote(M)
    k = AE._k_local_lote(lt)[0]
    assert np.allclose(k, AE._rigidez_local(5.0, SEC["A"], SEC["Iy"], SEC["Iz"], SEC["J"]))
    g = AE._kg_local_lote(lt, np.array([-10.0]))[0]
    assert np.allclose(g, g.T)
    # o giro de corpo rígido da barra (v = ψ·x, θz = ψ) sob compressão dá o par de forças N·ψ nas pontas
    psi, L = 1e-3, 5.0
    u = np.zeros(12)
    u[1], u[5], u[7], u[11] = 0.0, psi, psi * L, psi
    f = g @ u
    assert f[1] == pytest.approx(10.0 * psi, rel=1e-9) and f[7] == pytest.approx(-10.0 * psi, rel=1e-9)


@pytest.mark.parametrize("fracao", [0.1, 0.3, 0.5])
def test_amplificacao_do_pilar_em_balanco(fracao):
    """Δ2/Δ1 ≈ 1/(1 − P/Pcr), Pcr = π²·0,8EI/(2L)² (a rigidez reduzida da 2ª ordem)"""
    M = _pilar()
    Pcr = math.pi ** 2 * SO.FATOR_RIGIDEZ * AE.E_ACO * SEC["Iz"] / (4 * 6.0 ** 2)
    _sol, _c, r = _segunda(M, fracao * Pcr, 1.0)
    assert r["instavel"] is None and r["convergiu"]
    assert r["razao"] == pytest.approx(1.0 / (1.0 - fracao), rel=0.02)
    assert r["classe"] == SO.classe_de_deslocabilidade(r["razao"])


def test_momento_de_2a_ordem_ao_longo_do_pilar():
    """o diagrama fecha nas duas pontas de cada barra: M(z) = H·(L − z) + P·(Δtopo − Δz) — o cortante da ponta sai dos
    momentos (cortantes_na_corda), não das forças nos eixos indeformados"""
    M = _pilar()
    Pcr = math.pi ** 2 * SO.FATOR_RIGIDEZ * AE.E_ACO * SEC["Iz"] / (4 * 6.0 ** 2)
    P, H = 0.5 * Pcr, 1.0
    _sol, _c, r = _segunda(M, P, H)
    d = r["U"].reshape(-1, 6)[:, 0]
    Ht = H + r["nocional"]["H_kN"]                    # combinação com vento: sem nocional (4.10.7.1.1)
    e = AE.esforcos_lote(r["pontas"], np.zeros((8, 3)), AE.estacoes(M))
    for k in range(8):
        z = 6.0 * (k + 1) / 8
        esperado = Ht * (6.0 - z) + P * (d[-1] - d[k + 1])
        assert abs(e[k, -1, 5]) == pytest.approx(esperado, abs=1e-3 * Ht * 6.0)     # a tolerância da iteração (0,1%)
    assert abs(e[0, 0, 5]) == pytest.approx(Ht * 6.0 + P * d[-1], rel=1e-3)
    # a reação horizontal é a força aplicada (com a nocional): o equilíbrio global no eixo indeformado
    assert -r["reacoes"][0][0] == pytest.approx(Ht, rel=1e-3)                    # H_kN vem arredondado


def test_acima_da_carga_critica_e_instavel():
    M = _pilar()
    Pcr = math.pi ** 2 * SO.FATOR_RIGIDEZ * AE.E_ACO * SEC["Iz"] / (4 * 6.0 ** 2)
    _sol, _c, r = _segunda(M, 1.05 * Pcr, 1.0)
    assert r["instavel"]
    assert "pontas" not in r


def test_correcao_da_corda_nao_muda_a_1a_ordem():
    M = _pilar(nel=4)
    casos = {"q": {"dist": {k: np.array([2.0, 0, -1.0]) for k in range(4)}, "nodal": {}, "nos": {4: np.array([3.0, 1.0, -5.0])}}}
    sol = AE.resolver(M, casos)
    p = sol["pontas"][:, 0, :]
    w = sol["w"][:, 0, :]
    q = SO.cortantes_na_corda(p, AE._lote(M)["L"], w[:, 1], w[:, 2])
    assert np.allclose(q, p, atol=1e-9)


def test_comprimentos_de_flambagem_pelos_travamentos():
    """pilar de 6 m (a altura da seção em X) com uma viga chegando no meio na direção Y: trava só o eixo fraco"""
    nos = np.array([[0, 0, 0], [0, 0, 3], [0, 0, 6], [0, 4, 3]], float)
    bs = [_barra(nos, 0, 1, ids=("P",)), _barra(nos, 1, 2, ids=("P",)), _barra(nos, 1, 3, ids=("V",), papel="viga")]
    assert abs(bs[0]["R"][1][0]) == pytest.approx(1.0)          # ey (a altura) em X, ez em Y
    M = {"nos": nos, "barras": bs, "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"}], "par": dict(AE.PARAMETROS_PADRAO)}
    pecas = {p["chave"]: p for p in VP.pecas_do_modelo(M)}
    assert pecas["P"]["L"] == pytest.approx(6.0)
    assert pecas["P"]["Lx"] == pytest.approx(6.0) and pecas["P"]["Ly"] == pytest.approx(3.0)
    assert pecas["P"]["travamentos"] == [0, 1]
    assert pecas["P"]["barras"] == [0, 1]


def test_uso_do_pilar_comprimido_e_N_sobre_Nc_Rd():
    """1ª ordem, só compressão: o uso é N/Nc,Rd da NBR 8800 com Lx = Ly = a altura do pilar (nada o trava)"""
    from nucleo import materiais as mat, nbr8800
    from nucleo3d.calculo_ifc import _perfil_de
    perfil = "W 250×32,7"
    sec = AE._secao(perfil, False, {})
    M = _pilar(L=4.0, nel=2, sec=sec, perfil=perfil)
    Nrd = nbr8800.compressao(_perfil_de(perfil, "", {}, {}), mat.aco("ASTM A572 Gr.50"), Lx=400.0, Ly=400.0, N_Sd=1.0).dados["N_Rd"]
    P = 0.5 * Nrd
    sol = AE.resolver(M, {"G": {"dist": {}, "nodal": {}, "nos": {2: np.array([0, 0, -P])}}})
    combs = {"ELU": {"tipo": "ELU", "fatores": {"G": 1.0}, "descricao": ""}}
    v = VP.verificar(M, sol, combs, None)
    pc = v["pecas"][0]
    assert v["primeira_ordem"] and pc["Lx"] == pytest.approx(4.0) and pc["Ly"] == pytest.approx(4.0)
    assert pc["uso"] == pytest.approx(0.5, abs=2e-3)
    assert pc["verif"] == "N + M" and pc["comb"] == "ELU"
    assert v["resistencias"][pc["res"]]["Nc"] == pytest.approx(Nrd, rel=1e-3)
    # em balanço (topo livre), essa carga passa da crítica do eixo fraco (π²·0,8EI/(2L)² ≈ 117 kN): a 2ª ordem acusa e
    # a combinação sai da verificação
    # a combinação só gravitacional vira duas na 2ª ordem: a imperfeição em X e em Y (NBR 8800:2024, 4.10.7.1.1)
    so2 = SO.analisar(M, sol, combs)
    assert sorted(so2) == ["ELU ·X", "ELU ·Y"] and so2["ELU ·Y"]["nocional"]["dir"] in ([0.0, 1.0], [0.0, -1.0])
    c2 = SO.combinacoes_da_analise(combs, so2)
    assert list(c2) == ["ELU ·X", "ELU ·Y"]
    # o eixo fraco (Y, a imperfeição em Y) passa da crítica; o forte (X) não
    assert so2["ELU ·Y"]["instavel"] and not so2["ELU ·X"]["instavel"]
    assert VP.verificar(M, sol, c2, so2)["instaveis"] == ["ELU ·Y"]
    # abaixo da crítica: as nocionais dão um pouco de flexão, amplificada; o uso sobe um pouco acima de N/(2·Nc,Rd)
    sol = AE.resolver(M, {"G": {"dist": {}, "nodal": {}, "nos": {2: np.array([0, 0, -0.1 * Nrd])}}})
    so2 = SO.analisar(M, sol, combs)
    c2 = SO.combinacoes_da_analise(combs, so2)
    assert so2["ELU ·Y"]["instavel"] is None and so2["ELU ·Y"]["razao"] > 1.2
    v2 = VP.verificar(M, sol, c2, so2)
    assert not v2["primeira_ordem"] and 0.05 < v2["pecas"][0]["uso"] < 0.15


def test_vento_sem_nocional_e_com_ela_na_grande_deslocabilidade():
    """nas combinações com vento a norma dispensa as nocionais (4.10.7.1.1); com nocionais_no_vento (4.10.7.2) elas entram"""
    M = _pilar()
    _sol, _c, r = _segunda(M, 1.0, 1.0)
    assert r["nocional"]["H_kN"] == 0.0 and r["imperfeicao"] == "vento"
    sol, combs, _r = _segunda(M, 10.0, 1.0)
    r2 = SO.analisar(M, sol, combs, nocionais_no_vento=True)["ELU V1"]
    assert r2["nocional"]["H_kN"] == pytest.approx(0.03, abs=1e-3) and r2["nocional"]["dir"] == [1.0, 0.0]


def test_barra_redonda_so_a_tracao():
    from nucleo3d.calculo_ifc import _perfil_de  # noqa: F401 — o catálogo carregado
    r = VP.resistencias("Barra redonda 12,5", "ASTM A36", 5.0, 5.0, 5.0, {})
    assert r["redonda"] and r["Nc"] == 0.0 and r["Nt"] > 0 and r["erro"] is None


def test_ligacao_viga_pilar_fecha_com_o_topo_do_pilar():
    """pórtico de um vão com H no topo: o momento que a ligação transmite (a ponta da viga) é o do topo do pilar"""
    nos = np.array([[0, 0, 0], [0, 0, 4], [6, 0, 4], [6, 0, 0]], float)
    bs = [_barra(nos, 0, 1, ids=("P1",)), _barra(nos, 1, 2, ids=("V",), papel="viga"), _barra(nos, 3, 2, ids=("P2",))]
    M = {"nos": nos, "barras": bs, "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"}, {"no": 3, "tipo": "engastada", "chave": "6000,0"}],
         "par": dict(AE.PARAMETROS_PADRAO)}
    sol = AE.resolver(M, {"V1": {"dist": {}, "nodal": {}, "nos": {1: np.array([10.0, 0, 0])}}})
    combs = {"ELU V1": {"tipo": "ELU", "fatores": {"V1": 1.0}, "descricao": ""}}
    lig = AE.ligacoes_viga_pilar(M, sol, combs)
    assert len(lig) == 2
    e = AE.esforcos_lote(sol["pontas"][:, 0, :], sol["w"][:, 0, :], AE.estacoes(M))
    topo_p1 = abs(e[0, -1, 5])
    l1 = next(l for l in lig if l["no"] == 1)
    assert l1["max"]["Mz"][0] == pytest.approx(topo_p1, abs=1e-3)              # a saída vem com 3 casas
    assert l1["max"]["Mz"][1]["comb"] == "ELU V1"


def test_apoio_da_tesoura_soma_a_carga():
    """treliça triangular apoiada no topo de dois pilares: a soma vertical que ela entrega nos apoios é a carga"""
    nos = np.array([[0, 0, 0], [0, 0, 3], [6, 0, 3], [6, 0, 0], [3, 0, 4.5]], float)
    bs = [_barra(nos, 0, 1, ids=("P1",)), _barra(nos, 3, 2, ids=("P2",))]
    for a, b, papel in ((1, 4, "banzo_sup"), (4, 2, "banzo_sup"), (1, 2, "banzo_inf")):
        br = _barra(nos, a, b, ids=("T",) if papel == "banzo_inf" else ("T%d" % a,), papel="banzo")
        br.update(elemento="trelica", papel_trelica=papel, grupo="T1", soltos=[4, 5, 10, 11])
        bs.append(br)
    M = {"nos": nos, "barras": bs, "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"}, {"no": 3, "tipo": "engastada", "chave": "6000,0"}],
         "par": dict(AE.PARAMETROS_PADRAO)}
    sol = AE.resolver(M, {"G": {"dist": {}, "nodal": {}, "nos": {4: np.array([0, 0, -12.0])}}})
    combs = {"ELU G": {"tipo": "ELU", "fatores": {"G": 1.0}, "descricao": ""}}
    r = AE.apoios_das_tesouras(M, sol, combs)
    assert r["n"] == 2
    assert sum(a["Fv_max"][0] for a in r["apoios"]) == pytest.approx(12.0, rel=1e-6)
    assert all(a["Fv_max"][0] == pytest.approx(6.0, rel=1e-6) for a in r["apoios"])
