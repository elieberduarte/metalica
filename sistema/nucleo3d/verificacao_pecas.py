"""A verificação de cada peça do modelo pela norma — etapa 4 do plano da análise estrutural (07/10/2026).

A peça é o membro: as barras do esqueleto que vêm da mesma entidade do modelo (`ids[0]` — o banzo inteiro, partido nos
nós em que as almas chegam, é uma peça só). As barras sem entidade (hipótese de travamento, sanfona) são peças de uma
barra.

1. **Comprimentos de flambagem pelos travamentos.** Ao longo da peça, um nó trava a direção da altura da seção (ey)
   quando chega nele uma barra de outra peça com componente nessa direção (≥ 25%); o mesmo para a direção da largura
   (ez). As pontas e os apoios contam como travados. Lx (flambagem em torno do eixo forte, o deslocamento em ey) é o
   maior trecho entre travamentos em ey; Ly (eixo fraco) o maior entre travamentos em ez; Lb da flexão = Ly. K = 1 —
   a análise já tem a 2ª ordem global com as imperfeições (NBR 8800:2024, 4.10.7).
2. **Resistências** pelas rotinas do sistema, com cache por (perfil, aço, Lx, Ly): laminado e tubo pela NBR 8800
   (`nucleo/nbr8800.py`: compressão com χ e Q, tração na seção bruta, flexão nos dois eixos com FLA, FLM e FLT,
   cortante); U e Ue formados a frio pela NBR 14762 (MRD, `nucleo/nbr14762.py`); barra redonda só à tração.
3. **Esforços** das combinações últimas — os da 2ª ordem quando ela foi feita — em 9 seções de cada barra, com o B1 do
   P-δ (NBR 8800:2024, Anexo C: B1 = Cm / (1 − N/Ne) ≥ 1, Ne = π²EI/L² da peça no plano da flexão; Cm = 0,6 − 0,4·M1/M2
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


T_MIN_16239 = 2.5          # mm: a parede mínima dos procedimentos de ligação da ABNT NBR 16239:2013 (6.1.2-h)


def _k_trelicas_tubulares(M: dict, pecas: List[dict]) -> List[str]:
    """o comprimento de flambagem nas treliças só de tubos pela ABNT NBR 16239:2013, 4.8 — banzos 0,9·L; diagonais e
    montantes soldados no perímetro 0,90·L (β > 0,60) ou 0,75·L (β ≤ 0,60), β = largura da alma / largura do banzo.
    A 4.8 vale para treliças com os nós projetados pela Seção 6 (4.1, 4.2): se alguma parede tem menos de 2,5 mm
    (6.1.2-h) os nós ficam fora da norma — K = 1 e o apontamento. Muda pc["Lx"], pc["Ly"] no lugar (guarda K)."""
    from nucleo3d.calculo_ifc import _perfil_de
    barras = M["barras"]
    dims: Dict[str, Optional[tuple]] = {}

    def dim(nome):
        if nome not in dims:
            p = _perfil_de(nome or "", "", {}, {})
            dims[nome] = (p.tipo, float(p.d or 0), float(p.bf or p.d or 0), float(p.tw or p.tf or 0)) if p is not None else None
        return dims[nome]
    por_trel: Dict[str, List[dict]] = collections.defaultdict(list)
    for pc in pecas:
        br = barras[pc["barras"][0]]
        if br.get("elemento") == "trelica":
            por_trel[br.get("grupo") or ""].append(pc)
    avisos, finas = [], set()
    no_banzo: Dict[int, float] = {}
    for g, pcs in por_trel.items():
        ds = [dim(pc["perfil"]) for pc in pcs]
        if not ds or any(d is None or d[0] != "tubo" for d in ds):
            continue
        tmin = min(d[3] for d in ds)
        if tmin < T_MIN_16239 - 1e-9:
            finas.add(min((pc["perfil"] for pc in pcs), key=lambda nm: dim(nm)[3]))
            continue
        for pc in pcs:
            if pc["papel"] in ("banzo_sup", "banzo_inf", "banzo"):
                for i in pc["barras"]:
                    for no in (barras[i]["a"], barras[i]["b"]):
                        no_banzo[no] = max(no_banzo.get(no, 0.0), dim(pc["perfil"])[1])
        for pc in pcs:
            d = dim(pc["perfil"])
            if pc["papel"] in ("banzo_sup", "banzo_inf", "banzo"):
                K, ref = 0.9, "banzo"
            else:
                b0 = max([no_banzo.get(no, 0.0) for no in (pc["nos"][0], pc["nos"][-1])] + [1e-9])
                beta = max(d[1], d[2]) / b0 if b0 > 1e-6 else 1.0
                K, ref = (0.90 if beta > 0.60 else 0.75), "β = %.2f" % beta
            pc.update(K=K, Lx=pc["Lx"] * K, Ly=pc["Ly"] * K)
            pc.setdefault("obs", []).append("K = %.2f (NBR 16239, 4.8: treliça de tubos, %s)" % (K, ref))
    if finas:
        avisos.append(("treliça de tubos com parede abaixo de 2,5 mm (%s): os nós soldados ficam fora dos procedimentos da "
                       "ABNT NBR 16239:2013 (6.1.2-h) — as ligações entre os tubos não têm verificação pela norma e os "
                       "comprimentos de flambagem ficaram com K = 1 (a 4.8 vale para nós projetados pela Seção 6). "
                       "Apontamento para o fabricante e o engenheiro") % ", ".join(sorted(finas)))
    return avisos


# ------------------------------------------------------------------ as resistências (com cache)

def aco_da_peca(pc: dict, P: dict, tipo: str) -> str:
    from nucleo import materiais as mat
    if tipo in TIPOS_TUBO and P.get("aco_tubos"):
        return P["aco_tubos"]
    a = pc.get("aco_modelo") or ""
    return a if a in mat.ACOS else mat.ACO_PADRAO


#: Os parafusos de uma mesma ligação na ponta da peça: até esta distância (m) do anterior ao longo da barra. É o
#: espaçamento máximo entre parafusos da NBR 8800:2024, 6.3.10 (24·t e nunca mais de 300 mm): o furo mais longe que isso
#: já é de outra ligação (a terça, a presilha) e não entra no ℓc.
ESPACAMENTO_MAX_PARAFUSOS = 0.300


def _parafusos(furos: List[dict]) -> List[dict]:
    """os parafusos (x ao longo da barra, m; d, mm) a partir dos furos: os furos do mesmo parafuso (as duas paredes do U,
    a aba e a chapa) viram um — pelo parafuso ligado a eles ou, no furo solto, pelo mesmo eixo (a distância entre os
    pontos, fora da direção do furo, menor que o diâmetro do furo)"""
    por_id: Dict[str, List[dict]] = collections.defaultdict(list)
    soltos: List[List[dict]] = []
    for f in furos:
        if f.get("parafuso"):
            por_id[f["parafuso"]].append(f)
            continue
        p = np.array(f["ponto"], float)
        for g in soltos:
            q = np.array(g[0]["ponto"], float)
            e = np.array(g[0]["eixo"], float)
            w = p - q
            if float(np.linalg.norm(w - (w @ e) * e)) * 1000.0 < max(f["d_furo"], g[0]["d_furo"]):
                g.append(f)
                break
        else:
            soltos.append([f])
    return [{"x": float(np.mean([f["x"] for f in g])), "d": max(f["d"] for f in g)} for g in list(por_id.values()) + soltos]


def ligacao_da_peca(M: dict, pc: dict) -> Optional[dict]:
    """a ligação parafusada da peça pelos furos do 3D (N1, 14/10/2026), no contrato de nucleo.nbr8800.tracao: {lc (cm),
    n_parafusos (na linha, na direção da força), d_parafuso (cm), soldada, fonte}. Em cada ponta, os parafusos a partir do
    mais perto dela, enquanto o seguinte estiver a até ESPACAMENTO_MAX_PARAFUSOS do anterior; ℓc = do primeiro ao último ao
    longo da barra. Das duas pontas vale a de menor ℓc (o menor C_t = 1 − e_c/ℓc). Sem furo na peça: None (o núcleo adota
    o C_t sem ligação, nucleo.nbr8800.ct_sem_ligacao: A_c/A_g na cantoneira e no U laminados, 0,50 no U/Ue e 0,40 na
    cantoneira formados a frio)"""
    barras = M["barras"]
    br0 = barras[pc["barras"][0]]
    ent = br0["ids"][0] if br0.get("ids") else None
    reg = (M.get("furos_por_peca") or {}).get(ent) if ent else None
    if not reg or not reg.get("furos"):
        return None
    Lp = float(reg["L"])
    pfs = _parafusos(reg["furos"])
    pontas = []
    for lado in (0, 1):
        ds = sorted(((p["x"] if lado == 0 else Lp - p["x"]), p["d"]) for p in pfs if (p["x"] <= Lp / 2.0) == (lado == 0))
        if not ds:
            continue
        grupo = [ds[0]]
        for d_, dm in ds[1:]:
            if d_ - grupo[-1][0] > ESPACAMENTO_MAX_PARAFUSOS + 1e-9:
                break
            grupo.append((d_, dm))
        dmax = max(dm for _, dm in grupo)
        linha: List[float] = []                            # as posições na linha (os lado a lado contam uma vez)
        for d_, _dm in grupo:
            if not linha or d_ - linha[-1] > dmax / 1000.0:
                linha.append(d_)
        pontas.append({"lc": (grupo[-1][0] - grupo[0][0]) * 100.0, "n": len(linha), "d": dmax, "lado": "início" if lado == 0 else "fim"})
    if not pontas:
        return None
    pt = min(pontas, key=lambda q: (q["lc"], q["n"]))
    return {"lc": round(pt["lc"], 2), "n_parafusos": int(pt["n"]), "d_parafuso": round(pt["d"] / 10.0, 4), "soldada": False,
            "fonte": "parafusos do 3D: %d na linha, Ø%s mm, ℓc = %s cm (ponta do %s da peça)" % (
                pt["n"], _n(pt["d"], 1).replace(",0", ""), _n(pt["lc"], 1), pt["lado"])}


def resistencias(nome: str, aco_nome: str, Lx: float, Ly: float, L: float, cache: dict,
                 ligacao: Optional[dict] = None) -> dict:
    """as resistências de cálculo de um perfil com os comprimentos de flambagem (m): kN e kN·m. `ligacao`: a ligação
    parafusada da peça (ligacao_da_peca) — o C_t da tração na cantoneira e no U; sem ela, o núcleo adota
    nbr8800.ct_sem_ligacao(perfil) (A_c/A_g no laminado; 0,50/0,40 no formado a frio)"""
    chave = (nome, aco_nome, round(Lx, 2), round(Ly, 2), _chave_ligacao(ligacao))
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
        kw_lig = {"ligacao": ligacao} if ligacao else {}
        r["fy"] = a.fy * 10.0
        r["tipo"] = p.tipo
        r["lam"] = max(Lx * 100 / p.rx if p.rx else 0.0, Ly * 100 / p.ry if p.ry else 0.0)
        modo = perfis_fabrica.tipo_de_verificacao(p)
        circular = p.tipo == "tubo" and not (p.bf or 0)
        if modo == "redonda":
            r.update(norma="NBR 8800", redonda=True)
            rt = nbr8800.tracao(p, a, N_Sd=1.0, L=max(Lx, Ly) * 100, rosqueada=bool(p.dados.get("rosqueada")), **kw_lig)
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
            rt = nbr8800.tracao(p, a, N_Sd=1.0, L=max(Lx, Ly) * 100, **kw_lig)
            r["Nt"] = float(rt.dados["N_Rd"])
            r["Ct"] = rt.dados.get("Ct")
            if ligacao and ligacao.get("fonte"):
                r["ligacao"] = ligacao["fonte"]
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
            aberta = nbr8800.ligada_por_um_elemento(p)
            if ligacao and ligacao.get("ponta_ligada") is False:
                r["obs"].append("tração no trecho corrido da peça (ponta_ligada = não): sem ligação na seção")
            elif ligacao and aberta:
                r["obs"].append("tração: ruptura da seção líquida com C_t = %s pela ligação (%s)" % (_n(float(r["Ct"] or 0), 2), ligacao.get("fonte") or "informada"))
            elif aberta:
                r["obs"].append("tração: sem parafusos na peça no 3D — C_t = %s adotado (NBR 8800:2024, 5.2.5-c)" % _n(float(r["Ct"] or 0), 2))
            else:
                r["obs"].append("tração pela seção bruta (sem furos: a ruptura da seção líquida fica para as ligações)")
    except (ErroDeDados, KeyError, ValueError, ZeroDivisionError) as e:
        r["erro"] = str(e) or e.__class__.__name__
    r = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
    cache[chave] = r
    return r


#: A ligação do trecho corrido do banzo contínuo (contrato de nucleo.nbr8800.tracao): sem ligação na seção.
PONTA_CORRIDA = {"ponta_ligada": False}
PAPEIS_BANZO = ("banzo", "banzo_sup", "banzo_inf")


def banzo_continuo(barras: List[dict], pc: dict) -> bool:
    """a peça é banzo de treliça partido em vários trechos (a cadeia passa pelos nós das almas)"""
    br0 = barras[pc["barras"][0]]
    return len(pc["barras"]) > 1 and (br0.get("papel_trelica") in PAPEIS_BANZO or br0.get("papel") == "banzo")


def _chave_ligacao(ligacao: Optional[dict]):
    return None if not ligacao else tuple(sorted((k, v) for k, v in ligacao.items() if k != "fonte"))


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
    # só as peças de aço: o concreto do pré-moldado (análise global, 09/10) não se verifica pela NBR 8800
    pecas = [pc for pc in pecas_do_modelo(M) if not barras[pc["barras"][0]]["sec"].get("concreto")]
    avisos_k = _k_trelicas_tubulares(M, pecas)
    cache = CACHE
    lista_res: List[dict] = []
    idx_res: Dict[tuple, int] = {}
    # as resistências de cada peça e, por barra, as da peça dela
    # a barra fora de toda peça verificada (o concreto do pré-moldado) fica com -1: antes ficava 0 e a normal dela entrava no
    # B1 da primeira peça (a coluna HP do BRAMAIS recebia os 1.892 kN de um pilar de concreto, 09/10)
    pk = np.full(n, -1, int)
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
        lig = ligacao_da_peca(M, pc)
        res = resistencias(pc["perfil"], aco, pc["Lx"], pc["Ly"], pc["L"], cache, ligacao=lig)
        ch = (pc["perfil"], aco, round(pc["Lx"], 2), round(pc["Ly"], 2), _chave_ligacao(lig))
        if lig:
            pc["ligacao"] = lig["fonte"]
        if ch not in idx_res:
            idx_res[ch] = len(lista_res)
            lista_res.append(res)
        pc.update(aco=aco, res=idx_res[ch])
        # o banzo contínuo (decisão do usuário, 14/10): a ruptura da seção líquida só vale nas pontas da peça (a emenda, o
        # apoio) — os trechos extremos da cadeia ficam com a resistência de ponta ligada; os do meio, corridos, com
        # ponta_ligada = False (sem furo de ligação na seção)
        meio = None
        if banzo_continuo(barras, pc):
            lig_meio = dict(PONTA_CORRIDA)
            meio = resistencias(pc["perfil"], aco, pc["Lx"], pc["Ly"], pc["L"], cache, ligacao=lig_meio)
            ch_m = (pc["perfil"], aco, round(pc["Lx"], 2), round(pc["Ly"], 2), _chave_ligacao(lig_meio))
            if ch_m not in idx_res:
                idx_res[ch_m] = len(lista_res)
                lista_res.append(meio)
            pc["res_meio"] = idx_res[ch_m]
            pc.setdefault("obs", []).append("banzo contínuo: a ruptura da seção líquida só nos trechos das pontas da peça; "
                                            "os do meio, corridos, sem ligação na seção")
        fator = 2.0 if pc["duplo"] else 1.0
        extremos = {pc["barras"][0], pc["barras"][-1]}
        for i in pc["barras"]:
            pk[i] = j
            if res["erro"] is None:
                valida[i] = True
                r_i = meio if (meio is not None and meio["erro"] is None and i not in extremos) else res
                RB[i] = [fator * float((r_i if c == "Nt" else res)[c] or 0.0) for c in cols]
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
    # B1 por peça e combinação (NBR 8800:2024, Anexo C; 1,0 na tração)
    Lx = np.array([pc["Lx"] for pc in pecas])
    Ly = np.array([pc["Ly"] for pc in pecas])
    b0 = np.array([pc["barras"][0] for pc in pecas], int)
    Ne_z = math.pi ** 2 * AE.E_ACO * Iz[b0] / np.maximum(Lx, 1e-6) ** 2          # kN (I da seção já conta o duplo)
    Ne_y = math.pi ** 2 * AE.E_ACO * Iy[b0] / np.maximum(Ly, 1e-6) ** 2
    Nc_pc = np.zeros((ne, npc))
    if ne and n:
        dentro = pk >= 0
        np.maximum.at(Nc_pc, (slice(None), pk[dentro]), np.clip(-N.min(axis=2), 0.0, None)[:, dentro])
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
        pk0 = np.where(pk >= 0, pk, 0)
        if not npc:                                       # nenhuma peça de aço (o pré-moldado só de concreto)
            B1z = B1y = np.ones((ne, 1))
        bz = B1z[:, pk0][:, :, None]
        by = B1y[:, pk0][:, :, None]
        rmz = np.where(Mz_b > 0, bz * np.abs(E[..., 5]) / Mz_b, 0.0)
        rmy = np.where(My_b > 0, by * np.abs(E[..., 4]) / My_b, 0.0)
        rm = np.nan_to_num(rmz, nan=np.inf) + np.nan_to_num(rmy, nan=np.inf)
        inter = np.where(linear[None, :, None], rn + rm, np.where(rn >= 0.2, rn + 8.0 / 9.0 * rm, rn / 2.0 + rm))
        inter = np.where(redonda[None, :, None], rn, inter)
        rv = np.maximum(np.where(Vy_b > 0, np.abs(E[..., 1]) / Vy_b, 0.0), np.where(Vz_b > 0, np.abs(E[..., 2]) / Vz_b, 0.0))
        rv = np.where(redonda[None, :, None], 0.0, rv)
    inter = np.nan_to_num(inter, nan=0.0, posinf=99.0)
    uso_st = np.maximum(inter, rv)
    # a viga com mísula (o galpão gerado): no trecho dela a seção é a da mísula, mais alta, e quem a
    # verifica é a ligação do joelho; o W sozinho só a partir do fim dela (o mesmo critério do
    # cálculo do galpão — antes a viga do galpão padrão dava 164 % no joelho)
    com_misula = set()
    nos_m = np.asarray(M["nos"], float)
    for i, br in enumerate(barras):
        m = br.get("misula")
        if not m or not S:
            continue
        a, b = nos_m[br["a"]], nos_m[br["b"]]
        frac = X[i] / max(float(X[i, -1]), 1e-9)
        pos = a[None, :] + frac[:, None] * (b - a)[None, :]
        # os nós da análise estão em m; o ponto e o comprimento da mísula, em mm (o 3D)
        p0 = np.asarray(m["ponto"], float) / 1000.0
        dentro = np.linalg.norm(pos - p0[None, :], axis=1) < (float(m["comprimento_mm"]) - 1.0) / 1000.0
        if dentro.any():
            uso_st[:, i, dentro] = 0.0
            com_misula.add(i)
    uso_bc = uso_st.max(axis=2) if S else np.zeros((ne, n))                       # (ne, n)
    uso_bc[:, ~valida] = 0.0
    # por peça: a pior combinação, barra e seção; a esbeltez
    saida_pecas = []
    for j, pc in enumerate(pecas):
        bs = pc["barras"]
        res = lista_res[pc["res"]]
        obs = list(pc.pop("obs", []))
        item = {k: pc[k] for k in ("chave", "perfil", "aco", "papel", "marca", "res", "travamentos")}
        if pc.get("K"):
            item["K"] = pc["K"]
        item.update(b0=int(bs[0]), nb=len(bs), L=round(pc["L"], 3), Lx=round(pc["Lx"], 3), Ly=round(pc["Ly"], 3))
        for k in ("res_meio", "ligacao"):                 # o trecho corrido do banzo e a ligação parafusada do 3D (N1)
            if k in pc:
                item[k] = pc[k]
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
        if com_misula & set(bs):
            obs.append("trecho da mísula verificado na ligação do joelho: o perfil conferido do fim da mísula em diante")
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
            "peca_da_barra": pk.tolist(), "combinacoes": elu, "instaveis": instaveis, "avisos": avisos_k,
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
