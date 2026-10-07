"""A verificação de cada peça do modelo pela norma — etapa 4 do plano da análise estrutural (07/10/2026).

A peça é o membro: as barras do esqueleto que vêm da mesma entidade do modelo (`ids[0]` — o banzo inteiro, partido nos
nós em que as almas chegam, é uma peça só). As barras sem entidade (hipótese de travamento, sanfona) são peças de uma
barra.

1. **Comprimentos de flambagem pelos travamentos.** Ao longo da peça, um nó trava a direção da altura da seção (ey)
   quando chega nele uma barra de outra peça com componente nessa direção (≥ 25%); o mesmo para a direção da largura
   (ez). As pontas e os apoios contam como travados. Lx (flambagem em torno do eixo forte, o deslocamento em ey) é o
   maior trecho entre travamentos em ey; Ly (eixo fraco) o maior entre travamentos em ez; Lb da flexão = Ly. K = 1 —
   a análise já tem a 2ª ordem global com as imperfeições (NBR 8800, 4.9.7).
2. **Resistências** pelas rotinas do sistema, com cache por (perfil, aço, Lx, Ly): laminado e tubo pela NBR 8800
   (`nucleo/nbr8800.py`: compressão com χ e Q, tração na seção bruta, flexão nos dois eixos com FLA, FLM e FLT,
   cortante); U e Ue formados a frio pela NBR 14762 (MRD, `nucleo/nbr14762.py`); barra redonda só à tração.
3. **Esforços** das combinações últimas — os da 2ª ordem quando ela foi feita — em 9 seções de cada barra, com o B1 do
   P-δ (NBR 8800, Anexo D: B1 = Cm / (1 − N/Ne) ≥ 1, Ne = π²EI/L² da peça no plano da flexão; Cm = 0,6 − 0,4·M1/M2
   na peça de uma barra sem carga transversal, 1,0 nas outras).
4. **Uso** = a pior das verificações em cada seção: a interação N + M (NBR 8800, 5.5.1.2; linear na NBR 14762) e o
   cortante nos dois planos; e a esbeltez da peça quando passa do limite (KL/r ≤ 200 se comprime de fato, ≤ 300 só
   tracionada) — a esbeltez é limite, não uso da resistência.
   Uso 1,00 = 100% da resistência de cálculo.

Unidades: m, kN, kN·m (as rotinas da norma trabalham em cm e kN·cm: a conversão é aqui).
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional

import numpy as np

COS_TRAVA = 0.25
ESBELTEZ_COMPRESSAO = 200.0
ESBELTEZ_TRACAO = 300.0
TIPOS_TUBO = ("tubo",)
# as resistências por (perfil, aço, Lx, Ly): ficam entre um cálculo e outro (o servidor mantém o módulo carregado) — a
# verificação e a estimativa da troca de perfil usam as mesmas
CACHE: Dict[tuple, dict] = {}


def _n(v: float, d: int) -> str:
    """o número com vírgula (o texto vai para a tela)"""
    return ("%.*f" % (d, v)).replace(".", ",")


# ------------------------------------------------------------------ as peças e os travamentos

def _cadeia(bs: List[int], barras: List[dict]) -> Optional[List[int]]:
    """os nós da peça em ordem (as barras em fila); None se a peça ramifica"""
    if len(bs) == 1:
        return [barras[bs[0]]["a"], barras[bs[0]]["b"]]
    viz: Dict[int, List[int]] = collections.defaultdict(list)
    for i in bs:
        viz[barras[i]["a"]].append(i)
        viz[barras[i]["b"]].append(i)
    pontas = [no for no, l in viz.items() if len(l) == 1]
    if len(pontas) != 2 or any(len(l) > 2 for l in viz.values()):
        return None
    seq, usadas, no = [pontas[0]], set(), pontas[0]
    while True:
        prox = [i for i in viz[no] if i not in usadas]
        if not prox:
            break
        i = prox[0]
        usadas.add(i)
        no = barras[i]["b"] if barras[i]["a"] == no else barras[i]["a"]
        seq.append(no)
    return seq if len(usadas) == len(bs) else None


def pecas_do_modelo(M: dict) -> List[dict]:
    """as peças (membros) com as barras em ordem, o comprimento e os comprimentos de flambagem pelos travamentos"""
    nos, barras = M["nos"], M["barras"]
    grupos: Dict[str, List[int]] = collections.OrderedDict()
    for i, br in enumerate(barras):
        grupos.setdefault(br["ids"][0] if br.get("ids") else "barra:%d" % i, []).append(i)
    no_barras: Dict[int, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        no_barras[br["a"]].append(i)
        no_barras[br["b"]].append(i)
    apoiados = {int(ap["no"]) for ap in M["apoios"]}
    out = []
    for chave, bs in grupos.items():
        seq = _cadeia(bs, barras)
        partes = [(chave, bs, seq)] if seq is not None else [("%s/%d" % (chave, i), [i], [barras[i]["a"], barras[i]["b"]]) for i in bs]
        for ch, bs_, seq_ in partes:
            out.append(_peca(ch, bs_, seq_, nos, barras, no_barras, apoiados))
    return out


def _peca(chave, bs, seq, nos, barras, no_barras, apoiados) -> dict:
    meus = set(bs)
    # a barra da peça entre seq[k] e seq[k+1]
    ordem = []
    for a, b in zip(seq, seq[1:]):
        i = next(i for i in bs if {barras[i]["a"], barras[i]["b"]} == {a, b})
        ordem.append(i)
    s = [0.0]
    for i in ordem:
        s.append(s[-1] + barras[i]["L"])
    trava_y, trava_z = [], []
    for k, no in enumerate(seq):
        if k in (0, len(seq) - 1) or no in apoiados:
            trava_y.append(s[k]); trava_z.append(s[k])
            continue
        R = barras[ordem[k - 1]]["R"]
        ty = tz = False
        for j in no_barras[no]:
            if j in meus:
                continue
            o = barras[j]
            d = nos[o["b"]] - nos[o["a"]]
            nd = float(np.linalg.norm(d))
            if nd < 1e-9:
                continue
            d = d / nd
            ty = ty or abs(float(d @ R[1])) >= COS_TRAVA
            tz = tz or abs(float(d @ R[2])) >= COS_TRAVA
        if ty:
            trava_y.append(s[k])
        if tz:
            trava_z.append(s[k])
    br0 = barras[ordem[0]]
    return {"chave": chave, "barras": ordem, "nos": list(seq), "L": s[-1],
            "Lx": max(b - a for a, b in zip(trava_y, trava_y[1:])), "Ly": max(b - a for a, b in zip(trava_z, trava_z[1:])),
            "travamentos": [len(trava_y) - 2, len(trava_z) - 2], "perfil": br0["perfil"], "papel": br0.get("papel_trelica") or br0["papel"],
            "marca": br0.get("marca"), "duplo": bool(br0.get("duplo")), "hipotese": bool(br0.get("hipotese")), "aco_modelo": br0.get("aco") or ""}


# ------------------------------------------------------------------ as resistências (com cache)

def aco_da_peca(pc: dict, P: dict, tipo: str) -> str:
    from nucleo import materiais as mat
    if tipo in TIPOS_TUBO and P.get("aco_tubos"):
        return P["aco_tubos"]
    a = pc.get("aco_modelo") or ""
    return a if a in mat.ACOS else mat.ACO_PADRAO


def resistencias(nome: str, aco_nome: str, Lx: float, Ly: float, L: float, cache: dict) -> dict:
    """as resistências de cálculo de um perfil com os comprimentos de flambagem (m): kN e kN·m"""
    chave = (nome, aco_nome, round(Lx, 2), round(Ly, 2))
    if chave in cache:
        return cache[chave]
    from nucleo import materiais as mat, nbr8800, nbr14762, perfis_fabrica
    from nucleo.base import ErroDeDados
    from nucleo3d.calculo_ifc import _perfil_de
    r = {"perfil": nome, "aco": aco_nome, "Lx": round(Lx, 3), "Ly": round(Ly, 3), "obs": [], "erro": None, "norma": "NBR 8800",
         "Nc": 0.0, "Nt": 0.0, "Mz": None, "My": None, "Vy": None, "Vz": None, "linear": False, "redonda": False}
    try:
        p = _perfil_de(nome, "", {}, {})
        if p is None:
            raise ErroDeDados("perfil fora do catálogo")
        a = mat.aco(aco_nome)
        r["fy"] = a.fy * 10.0
        r["tipo"] = p.tipo
        r["lam"] = max(Lx * 100 / p.rx if p.rx else 0.0, Ly * 100 / p.ry if p.ry else 0.0)
        modo = perfis_fabrica.tipo_de_verificacao(p)
        circular = p.tipo == "tubo" and not (p.bf or 0)
        if modo == "redonda":
            r.update(norma="NBR 8800", redonda=True)
            rt = nbr8800.tracao(p, a, N_Sd=1.0, L=max(Lx, Ly) * 100, rosqueada=bool(p.dados.get("rosqueada")))
            r["Nt"] = float(rt.dados["N_Rd"])
            r["obs"].append("barra redonda: só tração (a compressão não é resistida)")
        elif modo == "frio":
            r.update(norma="NBR 14762", linear=True)
            sec = perfis_fabrica.secao_frio(p)
            r["Nc"] = float(nbr14762.compressao_mrd(sec, a, N_Sd=1.0, KxLx=Lx * 100, KyLy=Ly * 100, KtLt=Ly * 100).Rd)
            r["Nt"] = float(sec.A * a.fy / nbr14762.GAMA)
            r["Mz"] = float(nbr14762.flexao_mrd(sec, a, M_Sd=1.0, Lb=Ly * 100, Lt=Ly * 100).Rd) / 100.0
            Wy = p.Wy or (p.Iy / max((p.bf or 1.0) / 10.0 / 2.0, 1e-6))
            r["My"] = Wy * a.fy / 1.10 / 100.0
            r["Vy"] = float(nbr14762.cisalhamento(sec, a, V_Sd=1.0).Rd)
            r["Vz"] = 0.6 * a.fy * 2 * (p.bf or 0) / 10.0 * (p.tf or p.tw or 0) / 10.0 / 1.10
            r["obs"].append("formado a frio: compressão e flexão pelo MRD; flexão no eixo fraco elástica (W·fy/1,10); interação linear (9.8.2.4)")
        else:
            cant = p.tipo == "L"
            rc = nbr8800.compressao(p, a, Lx=Lx * 100, Ly=Ly * 100, N_Sd=1.0, cantoneira_simplificada=cant)
            d = rc.dados
            r.update(Nc=float(d["N_Rd"]), chi=d.get("chi"), Q=d.get("Q"), lambda0=d.get("lambda_0"), Ne=d.get("Ne"),
                     modo=d.get("modo_critico"))
            r["Nt"] = float(nbr8800.tracao(p, a, N_Sd=1.0, L=max(Lx, Ly) * 100).dados["N_Rd"])
            for eixo, k in (("x", "Mz"), ("y", "My")):
                try:
                    if cant:
                        raise ErroDeDados("cantoneira")
                    rf = nbr8800.flexao(p, a, M_Sd=1.0, Lb=Ly * 100, Cb=1.0, eixo="x" if (circular and eixo == "y") else eixo)
                    r[k] = float(rf.dados["M_Rd"]) / 100.0
                    r["gov_" + k] = rf.dados.get("governa")
                except ErroDeDados:
                    W = (p.Wx if eixo == "x" else p.Wy) or p.Wx
                    r[k] = W * a.fy / 1.10 / 100.0
                    r["obs"].append("flexão em %s elástica (W·fy/1,10): a NBR 8800 não cobre este caso" % ("z" if eixo == "x" else "y"))
            try:
                r["Vy"] = float(nbr8800.cisalhamento(p, a, V_Sd=1.0, Lv=max(L, 0.1) * 100 / 2.0).Rd)
            except ErroDeDados:
                r["Vy"] = 0.6 * a.fy * (p.Aw or p.A / 2) / 1.10
            if p.tipo in TIPOS_TUBO:
                r["Vz"] = r["Vy"] if circular or abs((p.d or 0) - (p.bf or 0)) < 1e-6 else \
                    0.6 * a.fy * 2 * (p.bf or 0) / 10.0 * (p.tw or 0) / 10.0 / 1.10
            else:
                r["Vz"] = 0.6 * a.fy * 2 * (p.bf or 0) / 10.0 * (p.tf or 0) / 10.0 / 1.10
                r["obs"].append("cortante no plano fraco pelas mesas: 0,6·fy·2·bf·tf/1,10")
            if p.tipo == "L":
                r["obs"].append("cantoneira simples: compressão pela esbeltez equivalente (E.1.4); flexão elástica")
            r["obs"].append("tração pela seção bruta (sem furos: a ruptura da seção líquida fica para as ligações)")
    except (ErroDeDados, KeyError, ValueError, ZeroDivisionError) as e:
        r["erro"] = str(e) or e.__class__.__name__
    r = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
    cache[chave] = r
    return r


# ------------------------------------------------------------------ a verificação

def verificar(M: dict, sol: dict, combs: Dict[str, dict], so2: Optional[dict] = None) -> dict:
    """a verificação de todas as peças nas combinações últimas: {pecas, resistencias, uso_barras {comb: [uso]}, uso_env,
    comb_env, combinacoes, primeira_ordem, instaveis}"""
    from nucleo3d import analise_estrutural as AE
    barras, P = M["barras"], M["par"]
    n = len(barras)
    so2 = so2 or {}
    elu_todas = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    instaveis = [c for c in elu_todas if (so2.get(c) or {}).get("instavel")]
    elu = [c for c in elu_todas if c not in instaveis]
    pecas = pecas_do_modelo(M)
    cache = CACHE
    lista_res: List[dict] = []
    idx_res: Dict[tuple, int] = {}
    # as resistências de cada peça e, por barra, as da peça dela
    pk = np.zeros(n, int)
    cols = ("Nc", "Nt", "Mz", "My", "Vy", "Vz")
    RB = np.zeros((n, 6))
    linear = np.zeros(n, bool)
    redonda = np.zeros(n, bool)
    valida = np.zeros(n, bool)
    Iz = np.array([br["sec"]["Iz"] for br in barras])
    Iy = np.array([br["sec"]["Iy"] for br in barras])
    for j, pc in enumerate(pecas):
        tipo = barras[pc["barras"][0]]["sec"].get("tipo") or ""
        aco = aco_da_peca(pc, P, tipo)
        res = resistencias(pc["perfil"], aco, pc["Lx"], pc["Ly"], pc["L"], cache)
        ch = (pc["perfil"], aco, round(pc["Lx"], 2), round(pc["Ly"], 2))
        if ch not in idx_res:
            idx_res[ch] = len(lista_res)
            lista_res.append(res)
        pc.update(aco=aco, res=idx_res[ch])
        fator = 2.0 if pc["duplo"] else 1.0
        for i in pc["barras"]:
            pk[i] = j
            if res["erro"] is None:
                valida[i] = True
                RB[i] = [fator * float(res[c] or 0.0) for c in cols]
                linear[i] = bool(res["linear"])
                redonda[i] = bool(res["redonda"])
        if pc["duplo"]:
            pc.setdefault("obs", []).append("perfil duplo: resistência = 2 × a de um perfil (sem a flambagem do conjunto)")
    npc = len(pecas)
    X = AE.estacoes(M)
    S = X.shape[1]
    ne = len(elu)
    E = np.zeros((ne, n, S, 6))
    W = np.zeros((ne, n, 3))
    for e, c in enumerate(elu):
        f, w = AE.esforcos_da_combinacao(M, sol, c, combs[c], so2)
        E[e] = AE.esforcos_lote(f, w, X)
        W[e] = w
    N = E[..., 0]
    # B1 por peça e combinação (Anexo D)
    Lx = np.array([pc["Lx"] for pc in pecas])
    Ly = np.array([pc["Ly"] for pc in pecas])
    b0 = np.array([pc["barras"][0] for pc in pecas], int)
    Ne_z = math.pi ** 2 * AE.E_ACO * Iz[b0] / np.maximum(Lx, 1e-6) ** 2          # kN (I da seção já conta o duplo)
    Ne_y = math.pi ** 2 * AE.E_ACO * Iy[b0] / np.maximum(Ly, 1e-6) ** 2
    Nc_pc = np.zeros((ne, npc))
    if ne and n:
        np.maximum.at(Nc_pc, (slice(None), pk), np.clip(-N.min(axis=2), 0.0, None))
    Cm_z = np.ones((ne, npc))
    Cm_y = np.ones((ne, npc))
    for j, pc in enumerate(pecas):
        if len(pc["barras"]) != 1:
            continue
        i = pc["barras"][0]
        sem_transversal = np.hypot(W[:, i, 1], W[:, i, 2]) < 1e-6
        for k, Cm in ((5, Cm_z), (4, Cm_y)):
            Ma, Mb = E[:, i, 0, k], E[:, i, -1, k]
            M2 = np.maximum(np.abs(Ma), np.abs(Mb))
            razao = np.where(M2 > 1e-9, -(Ma * Mb) / np.maximum(M2 * M2, 1e-18), 0.0)
            Cm[:, j] = np.where(sem_transversal, 0.6 - 0.4 * razao, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        B1z = np.where(Nc_pc < Ne_z, Cm_z / (1.0 - Nc_pc / Ne_z), np.inf)
        B1y = np.where(Nc_pc < Ne_y, Cm_y / (1.0 - Nc_pc / Ne_y), np.inf)
    B1z, B1y = np.maximum(B1z, 1.0), np.maximum(B1y, 1.0)
    # o uso em cada seção
    Nc_b, Nt_b, Mz_b, My_b, Vy_b, Vz_b = (RB[:, k][None, :, None] for k in range(6))
    with np.errstate(divide="ignore", invalid="ignore"):
        rn = np.where(N < 0, np.where(Nc_b > 0, -N / Nc_b, np.inf), N / np.where(Nt_b > 0, Nt_b, np.nan))
        rn = np.where(redonda[None, :, None], np.abs(N) / np.where(Nt_b > 0, Nt_b, np.nan), rn)
        bz = B1z[:, pk][:, :, None]
        by = B1y[:, pk][:, :, None]
        rmz = np.where(Mz_b > 0, bz * np.abs(E[..., 5]) / Mz_b, 0.0)
        rmy = np.where(My_b > 0, by * np.abs(E[..., 4]) / My_b, 0.0)
        rm = np.nan_to_num(rmz, nan=np.inf) + np.nan_to_num(rmy, nan=np.inf)
        inter = np.where(linear[None, :, None], rn + rm, np.where(rn >= 0.2, rn + 8.0 / 9.0 * rm, rn / 2.0 + rm))
        inter = np.where(redonda[None, :, None], rn, inter)
        rv = np.maximum(np.where(Vy_b > 0, np.abs(E[..., 1]) / Vy_b, 0.0), np.where(Vz_b > 0, np.abs(E[..., 2]) / Vz_b, 0.0))
        rv = np.where(redonda[None, :, None], 0.0, rv)
    inter = np.nan_to_num(inter, nan=0.0, posinf=99.0)
    uso_st = np.maximum(inter, rv)
    uso_bc = uso_st.max(axis=2) if S else np.zeros((ne, n))                       # (ne, n)
    uso_bc[:, ~valida] = 0.0
    # por peça: a pior combinação, barra e seção; a esbeltez
    saida_pecas = []
    for j, pc in enumerate(pecas):
        bs = pc["barras"]
        res = lista_res[pc["res"]]
        obs = list(pc.pop("obs", []))
        item = {k: pc[k] for k in ("chave", "perfil", "aco", "papel", "marca", "res", "travamentos")}
        item.update(b0=int(bs[0]), nb=len(bs), L=round(pc["L"], 3), Lx=round(pc["Lx"], 3), Ly=round(pc["Ly"], 3))
        if pc["hipotese"]:
            item["hipotese"] = True
        if res["erro"] is not None:
            item.update(uso=None, verif="não verificada", obs=obs + ["não verificada: %s" % res["erro"]])
            saida_pecas.append(item)
            continue
        # a regra da esbeltez de barra comprimida (≤ 200) vale para a peça que comprime de fato — não para a viga com
        # uma compressão residual do pórtico
        nc_max = float(Nc_pc[:, j].max()) if ne else 0.0
        comprime = nc_max > max(0.5, 0.01 * float(res["Nt"] or 0.0) * (2.0 if pc["duplo"] else 1.0))
        lam = float(res.get("lam") or 0.0)
        lim = 0.0 if res["redonda"] else (ESBELTEZ_COMPRESSAO if comprime else ESBELTEZ_TRACAO)
        uso_esb = lam / lim if lim else 0.0
        for Lf, ntr, eixo in ((pc["Lx"], pc["travamentos"][0], "altura da seção (eixo forte)"),
                              (pc["Ly"], pc["travamentos"][1], "largura da seção (eixo fraco)")):
            if nc_max > 0.5 and ntr == 0 and len(bs) > 1 and Lf > 3.0:
                obs.append(("nenhuma barra trava a peça na direção da %s ao longo dos %s m: comprimida (até %s kN), ela "
                            "flamba nesse comprimento — trave (mão-francesa, linha de corrente, contraventamento) ou confira "
                            "a restrição que as outras peças dão") % (eixo, _n(Lf, 2), _n(nc_max, 1)))
        if ne:
            sub = uso_st[:, bs, :]                                                     # (ne, nb, S)
            e, kb, ks = np.unravel_index(int(np.argmax(sub)), sub.shape)
            flamba = not (np.isfinite(B1z[e, j]) and np.isfinite(B1y[e, j]))
            if flamba:
                # a peça passa da carga de flambagem elástica: o lugar que conta é o da maior compressão
                kb, ks = np.unravel_index(int(np.argmin(N[e][bs])), N[e][bs].shape)
            i = bs[kb]
            u = float(sub[e, kb, ks]) if not flamba else 99.0
            ee = E[e, i, ks]
            verif = ("flambagem (N ≥ Ne)" if flamba else "cortante" if rv[e, i, ks] > inter[e, i, ks]
                     else ("tração (barra redonda)" if res["redonda"] else "N + M"))
            item.update(comb=elu[e], barra=int(i), x=round(float(X[i, ks] / max(X[i, -1], 1e-9)), 2),
                        esf={"N": round(float(ee[0]), 2), "Vy": round(float(ee[1]), 2), "Vz": round(float(ee[2]), 2),
                             "My": round(float(ee[4]), 3), "Mz": round(float(ee[5]), 3)},
                        B1=[round(float(min(B1z[e, j], 99.0)), 3), round(float(min(B1y[e, j], 99.0)), 3)],
                        Cm=[round(float(Cm_z[e, j]), 3), round(float(Cm_y[e, j]), 3)],
                        Ne=[round(float(Ne_z[j]), 1), round(float(Ne_y[j]), 1)],
                        partes={"N": round(float(rn[e, i, ks]) if np.isfinite(rn[e, i, ks]) else 99.0, 3),
                                "Mz": round(float(np.nan_to_num(rmz[e, i, ks], posinf=99.0)), 3),
                                "My": round(float(np.nan_to_num(rmy[e, i, ks], posinf=99.0)), 3),
                                "V": round(float(rv[e, i, ks]), 3)})
            if flamba:
                obs.append(("a compressão (%s kN) passa da carga de flambagem elástica da peça (Ne = %s kN no eixo "
                            "%s): instável") % (_n(nc_max, 1), _n(min(Ne_z[j], Ne_y[j]), 1), "forte" if Ne_z[j] < Ne_y[j] else "fraco"))
            if res["redonda"] and float(N[:, bs, :].min()) < -0.5:
                obs.append(("comprimida em alguma combinação (até %s kN): a barra redonda só trabalha à tração — num X, a "
                            "diagonal comprimida sai e a outra leva a força das duas") % _n(float(N[:, bs, :].min()), 1))
        else:
            u, verif = 0.0, "sem combinação"
        if uso_esb > 1.0 and uso_esb > u:
            # a esbeltez é um limite (passa ou não), não um uso da resistência: entra só quando passa do limite
            u, verif = uso_esb, "esbeltez"
        item.update(uso=round(min(u, 99.0), 3), verif=verif, lam=round(lam, 1), lam_lim=lim, obs=obs)
        saida_pecas.append(item)
    uso_env = uso_bc.max(axis=0) if ne else np.zeros(n)
    comb_env = [elu[int(k)] for k in np.argmax(uso_bc, axis=0)] if ne else [None] * n
    # a esbeltez também colore a barra (não depende da combinação)
    for pc, it in zip(pecas, saida_pecas):
        if it.get("verif") == "esbeltez":   # só quando passou do limite
            for i in pc["barras"]:
                uso_env[i] = max(uso_env[i], it["uso"])
    return {"pecas": saida_pecas, "resistencias": lista_res,
            "uso_barras": {c: np.round(np.minimum(uso_bc[e], 99.0), 3).tolist() for e, c in enumerate(elu)},
            "uso_env": np.round(np.minimum(uso_env, 99.0), 3).tolist(), "comb_env": comb_env,
            "peca_da_barra": pk.tolist(), "combinacoes": elu, "instaveis": instaveis,
            "primeira_ordem": not any((so2.get(c) or {}).get("pontas") is not None for c in elu)}


def por_grupo(ver: dict, barras: List[dict]) -> List[dict]:
    """o pior uso por grupo (função + perfil original — o grupo da troca de perfil)"""
    from nucleo3d.analise_estrutural import chave_do_grupo
    g: Dict[str, dict] = {}
    for j, pc in enumerate(ver["pecas"]):
        br = barras[pc["b0"]]
        if br.get("hipotese"):
            continue
        k = chave_do_grupo(br)
        it = g.setdefault(k, {"chave": k, "uso": -1.0, "peca": None, "pecas": 0, "nao_passam": 0, "verif": None})
        it["pecas"] += 1
        u = pc.get("uso")
        if u is None:
            continue
        if u > 1.0:
            it["nao_passam"] += 1
        if u > it["uso"]:
            it.update(uso=u, peca=j, verif=pc.get("verif"), comb=pc.get("comb"))
    return sorted(g.values(), key=lambda x: -x["uso"])


__all__ = ["verificar", "pecas_do_modelo", "resistencias", "por_grupo"]
