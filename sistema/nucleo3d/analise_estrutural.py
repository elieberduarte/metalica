"""Análise estrutural do modelo — o motor único para qualquer modelo (plano de 06/10/2026, etapas 1 a 3).

O pedido do usuário (06/10): "um unifilar para ver como as cargas atuam na estrutura… os mapas de esforços, onde estão as
maiores tensões… essa é a parte em que o sistema vai se provar capaz de analisar e dimensionar uma estrutura", com o
cálculo de um engenheiro estrutural como gabarito (Cobertura Quadra Kaefer).

O caminho:

1. **Modelo analítico** — o esqueleto de nós e barras de `nucleo3d.analitico` (as pontas juntadas, as almas nos banzos, as
   pontas levadas ao apoio). Cada barra ganha a seção do catálogo **na orientação da peça**: o eixo local y é a altura da
   seção (`geometria.base_local` com o `rotacao` da barra — o motor de `esforcos.py` ignorava o giro, e o W do pilar
   trabalhava sempre no eixo X).
2. **Rótulas** por condensação estática: as almas das treliças (montantes e diagonais) rotuladas nas duas pontas; a
   tesoura rotulada onde ela apoia na viga ou no pilar; a viga rígida ou rotulada no pilar (parâmetro).
3. **Apoios** no pé dos pilares: articulados (3 translações) ou engastados (6), por parâmetro, com exceções por pilar.
4. **Cargas** em casos: peso próprio (distribuído na barra); telha e sobrecarga por área, pela área de influência de cada
   nó do banzo superior das tesouras (com ou sem terças — sem elas, a carga chega nos nós do banzo); vento de cobertura
   isolada a duas águas (NBR 6123:2023, 7.2, Tabela 25: carregamentos 1 e 2, nos dois sentidos perpendiculares à geratriz;
   atrito 7.2.2 no sentido da geratriz).
5. **Combinações** últimas normais e de serviço da NBR 8800 (γ e ψ de `nucleo.cargas`).
6. **Resultados**: deslocamentos, reações e, por barra, os esforços nas pontas e a carga distribuída de cada caso — o
   diagrama de qualquer combinação sai por superposição (N, Vy, Vz, T, My, Mz ao longo da barra) — e o mapa de tensões
   σ = |N|/A + |Mz|/Wz + |My|/Wy (a fibra mais solicitada, em MPa) por combinação e na envoltória.

Unidades: m, kN, kN·m, kN/m², MPa nas tensões. O verificador da NBR 8800 por barra (flambagem, flexo-compressão) é a
etapa 4; aqui a tensão é o mapa de onde a estrutura trabalha mais.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

E_ACO = 200e6           # kN/m²
G_ACO = 77e6            # kN/m²
G_GRAV = 9.81e-3        # kN por kg

PARAMETROS_PADRAO = {
    # apoios e ligações
    # o pé de todos os pilares: articulada | engastada. Engastada por padrão: na cobertura com a tesoura só apoiada
    # (rotulada) sobre a viga, a base articulada deixa a direção transversal sem nada que a trave (mecanismo) — Kaefer, 06/10
    "base": "engastada",
    "bases": {},                        # exceções por pilar: {"x,y" (mm, arredondado): "engastada"}
    "viga_pilar": "rigida",             # rigida | rotulada
    "alma_rotulada": True,              # montantes e diagonais das treliças rotulados nas pontas…
    "rotula_alma": "no_plano",          # …só no plano da treliça (no_plano) ou nas duas direções (total) — rotulada nas
                                        # duas, a alma não segura o banzo inferior fora do plano e ele desliza (mecanismo)
    "tesoura_rotulada_no_apoio": True,  # a treliça rotulada onde apoia na viga ou no pilar
    # o travamento da cobertura que o modelo ainda não tem (hipótese declarada): com tesouras e sem terças, terças ligando
    # os nós do banzo superior de tesouras vizinhas e um X de contraventamento nos vãos das pontas — sem eles cada
    # tesoura gira em torno da linha dos apoios (mecanismo). Ficam marcadas como "hipótese" na análise
    "travamento_hipotese": "auto",      # auto | sim | nao
    "perfil_terca_hipotese": "Ue 150×60×20×2,00",
    "perfil_contravento_hipotese": "Barra redonda 12,5",
    # cargas (kN/m²)
    "telha": 0.10,                      # telha + terças/fixações, por área de cobertura (na inclinação)
    "sobrecarga": 0.25,                 # NBR 8800 B.5.1 (projeção horizontal)
    "carga_extra": 0.0,                 # permanente extra por área (forro, instalações)
    # vento (NBR 6123:2023)
    "vento": True,
    "v0": 45.0,                         # m/s — a confirmar pelo mapa de isopletas do local
    "s1": 1.0,
    "categoria": "III",
    "classe": None,                     # None: pela maior dimensão (A ≤ 20 m, B ≤ 50 m, C)
    "s3": 1.0,
    "modelo_vento": "isolada",          # isolada (7.2, Tabela 25)
    # cobertura retrátil (06/10, Kaefer: produto do fabricante, lona, as tesouras correm sobre as vigas-trilho): a tesoura
    # lançada é o molde; a análise monta as duas situações — aberta (n tesouras ao longo de `comprimento_aberta`) e
    # retraída (as n empilhadas em `comprimento_retraida`, na ponta `lado_retraida`) — com o peso total do fabricante, a
    # sanfona (o X entre tesouras vizinhas nos dois planos laterais) e o vento nas abas laterais de lona
    "cobertura_movel": False,
    "movel_n": 38,
    "movel_comprimento_aberta": 38.0,
    "movel_comprimento_retraida": 6.0,
    "movel_lado_retraida": "y_menor",   # y_menor | y_maior (a ponta da pilha, na planta)
    "movel_peso_total_kg": 7800.0,      # o peso total informado pelo fabricante (tesouras + lona)
    "perfil_sanfona": "TQ 50×50×2,0",   # o braço da sanfona (o X entre tesouras vizinhas)
    "configuracao": "aberta",           # a situação calculada (o calcular faz as duas)
    # troca de perfil só na análise (o "e se", pedido de 06/10): {"função|perfil": "perfil novo"} — a função é o papel na
    # treliça (banzo_sup, banzo_inf, montante, diagonal) ou o papel da peça (pilar, viga…); o 3D não muda
    "trocas_perfil": {},
    # aço
    "fy_mpa": 345.0,                    # para o mapa de tensões (ASTM A572 Gr.50; o tubo leve pode ser outro)
}

ALMA = ("montante", "diagonal")


# ------------------------------------------------------------------ geometria e seção

def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def _secao(nome: str, duplo: bool, cache: dict) -> Optional[dict]:
    """A, Iz (forte), Iy (fraca), J em m; Wz, Wy em m³; kg/m — pelo catálogo"""
    if nome not in cache:
        from nucleo3d.calculo_ifc import _perfil_de
        p = _perfil_de(nome or "", "", {}, {})
        s = None
        if p is not None and (p.A or 0) > 0:
            A = p.A * 1e-4
            Ix, Iy = (p.Ix or 0) * 1e-8, (p.Iy or 0) * 1e-8
            Wx, Wy = (p.Wx or 0) * 1e-6, (p.Wy or 0) * 1e-6
            if Ix <= 0:                                   # barra redonda: só a área
                Ix = Iy = A * A / (4 * math.pi)
            if Iy <= 0:
                Iy = Ix
            r = math.sqrt(A / math.pi)
            if Wx <= 0:
                Wx = Ix / max(r, 1e-6)
            if Wy <= 0:
                Wy = Wx if abs(Ix - Iy) < 1e-12 else Iy / max(r, 1e-6)
            J = (p.dados.get("J") or p.J or 0) * 1e-8 if hasattr(p, "dados") else (p.J or 0) * 1e-8
            s = {"A": A, "Iz": Ix, "Iy": Iy, "J": J or min(Ix, Iy) * 0.01, "Wz": Wx, "Wy": Wy,
                 "kg_m": p.massa or A * 7850.0, "tipo": getattr(p, "tipo", "")}
        cache[nome] = s
    s = cache[nome]
    if s is None:
        return None
    if not duplo:
        return s
    return {k: (v * 2.0 if isinstance(v, float) else v) for k, v in s.items()}


def _eixos(a: np.ndarray, b: np.ndarray, rotacao: float) -> np.ndarray:
    """(3, 3): ex (ao longo), ey (a altura da seção), ez — o mesmo triedro do 3D (geometria.base_local)"""
    from nucleo3d.geometria import base_local
    d = b - a
    u, v, w = base_local(tuple(d.tolist()), rotacao or 0.0)
    ex = np.array(w, float)
    ey = np.array(v, float)
    ez = np.cross(ex, ey)
    return np.stack([ex, ey, ez])


def _rigidez_local(L, A, Iy, Iz, J) -> np.ndarray:
    """12×12 da barra de pórtico espacial; graus por ponta: ux uy uz rx ry rz (local)"""
    k = np.zeros((12, 12))
    EA, GJ = E_ACO * A / L, G_ACO * J / L

    def por(i, j, v):
        k[i, j] = v
        k[j, i] = v
    for i, j, v in ((0, 0, EA), (6, 6, EA), (0, 6, -EA), (3, 3, GJ), (9, 9, GJ), (3, 9, -GJ)):
        por(i, j, v)
    for (v1, r1, v2, r2), I, s in (((1, 5, 7, 11), Iz, 1.0), ((2, 4, 8, 10), Iy, -1.0)):
        EI = E_ACO * I
        a, b, c, d = 12 * EI / L ** 3, 6 * EI / L ** 2, 4 * EI / L, 2 * EI / L
        por(v1, v1, a); por(v2, v2, a); por(v1, v2, -a)
        por(v1, r1, s * b); por(v1, r2, s * b); por(v2, r1, -s * b); por(v2, r2, -s * b)
        por(r1, r1, c); por(r2, r2, c); por(r1, r2, d)
    return k


def _engaste_perfeito(L: float, w: np.ndarray) -> np.ndarray:
    """as forças dos nós sobre a barra bi-engastada com a carga uniforme w = (wx, wy, wz) local (kN/m)"""
    wx, wy, wz = w
    f = np.zeros(12)
    f[0] = f[6] = -wx * L / 2
    f[1] = f[7] = -wy * L / 2
    f[5], f[11] = -wy * L * L / 12, wy * L * L / 12
    f[2] = f[8] = -wz * L / 2
    f[4], f[10] = wz * L * L / 12, -wz * L * L / 12
    return f


def _condensar(k: np.ndarray, f0: np.ndarray, soltos: Sequence[int]):
    """a rigidez e o engaste perfeito com os graus `soltos` liberados (rótula): (k_c, f0_c, recuperar)"""
    if not soltos:
        return k, f0, None
    r = list(soltos)
    m = [i for i in range(12) if i not in r]
    krr = k[np.ix_(r, r)]
    try:
        inv = np.linalg.inv(krr)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(krr)
    kmr = k[np.ix_(m, r)]
    kc = np.zeros((12, 12))
    kc[np.ix_(m, m)] = k[np.ix_(m, m)] - kmr @ inv @ k[np.ix_(r, m)]
    fc = np.zeros(12)
    fc[m] = f0[m] - kmr @ inv @ f0[r]
    return kc, fc, (r, m, inv, k[np.ix_(r, m)])


# ------------------------------------------------------------------ o modelo

def montar(doc, par: Optional[dict] = None) -> dict:
    """o modelo analítico pronto para resolver: nós (m), barras (seção, eixos, rótulas), apoios, origem das peças"""
    from nucleo3d import analitico as AN
    P = dict(PARAMETROS_PADRAO, **(par or {}))
    if P.get("cobertura_movel"):
        doc = _sem_copias_da_cobertura(doc)
    an = AN.analitico(doc)
    nos = np.array(an["nos"], float) / 1000.0
    ents = doc.entidades
    cache: Dict[str, Optional[dict]] = {}
    barras: List[dict] = []
    avisos: List[str] = []
    sem_secao = collections.Counter()
    for br in an["barras"]:
        ent = ents.get(br["ids"][0]) if br.get("ids") else None
        a, b = nos[br["a"]], nos[br["b"]]
        L = float(np.linalg.norm(b - a))
        if L < 1e-4:
            continue
        sec = _secao(br.get("perfil") or "", bool(br.get("duplo")), cache)
        if sec is None:
            sem_secao[br.get("perfil") or "?"] += 1
            continue
        at = (getattr(ent, "atributos", None) or {}) if ent is not None else {}
        barras.append({
            "a": int(br["a"]), "b": int(br["b"]), "L": L, "papel": br.get("papel") or "barra",
            "papel_trelica": at.get("papel_trelica"), "elemento": at.get("elemento"), "grupo": at.get("origem_2d") or br.get("grupo"),
            "marca": at.get("marca") or at.get("peca"), "perfil": br.get("perfil") or "", "ids": list(br.get("ids") or []),
            "sec": sec, "duplo": bool(br.get("duplo")), "R": _eixos(a, b, float(getattr(ent, "rotacao", 0.0) or 0.0) if ent is not None else 0.0),
            "soltos": [],
        })
    for nome, n in sem_secao.items():
        avisos.append("%d barra(s) com o perfil \"%s\" fora do catálogo ficaram fora da análise" % (n, nome))
    movel = None
    if P.get("cobertura_movel"):
        # os pilares como estão no 3D (o esqueleto leva o topo deles à ponta da viga, uns centímetros além do eixo)
        pil3d = [np.array(getattr(e, "fim", (0, 0, 0)), float) / 1000.0 for e in ents.values()
                 if getattr(e, "papel", "") == "pilar" and hasattr(e, "inicio")]
        nos, barras, movel = _cobertura_movel(nos, barras, P, cache, avisos, pil3d)
    if movel is None:
        hip = _travamento_hipotese(nos, barras, P, cache, avisos)
        barras += hip
    _trocar_perfis(barras, P, cache, avisos)
    # quem chega em cada nó
    no_barras: Dict[int, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        no_barras[br["a"]].append(i)
        no_barras[br["b"]].append(i)
    papeis_no = {n: {barras[i]["papel"] for i in bs} for n, bs in no_barras.items()}
    # o plano de cada treliça (a normal horizontal), pelos banzos dela
    normal_trel: Dict[str, np.ndarray] = {}
    dirs: Dict[str, List[np.ndarray]] = collections.defaultdict(list)
    for br in barras:
        if br["elemento"] == "trelica" and br["papel"] == "banzo":
            v = (nos[br["b"]] - nos[br["a"]])[:2]
            if np.linalg.norm(v) > 1e-6:
                v = _unit(v)
                dirs[br["grupo"]].append(v if v[0] + 1e-3 * v[1] >= 0 else -v)
    for g, vs in dirs.items():
        u = _unit(np.mean(vs, axis=0))
        normal_trel[g] = np.array([-u[1], u[0], 0.0])
    # a mesma peça partida em vários trechos (nos nós em que outras chegam): a divisão do meio é contínua — rótula só nas
    # pontas reais da peça (o perfil externo da tesoura, partido pela mão-francesa e pelo banzo, virava um pêndulo)
    trechos_no = collections.Counter()
    for br in barras:
        if br["ids"]:
            trechos_no[(br["ids"][0], br["a"])] += 1
            trechos_no[(br["ids"][0], br["b"])] += 1
    # rótulas
    for br in barras:
        for ponta, no in (("a", br["a"]), ("b", br["b"])):
            if br["ids"] and trechos_no[(br["ids"][0], no)] >= 2:
                continue                                      # meio da peça: contínua
            soltar = False
            if P["alma_rotulada"] and br["papel"] in ALMA:
                nrm = normal_trel.get(br["grupo"])
                if P.get("rotula_alma", "no_plano") == "no_plano" and nrm is not None:
                    # só o giro em torno da normal ao plano da treliça: ry (eixo y local) ou rz, o que estiver alinhado
                    base = 0 if ponta == "a" else 6
                    br["soltos"] += [base + (5 if abs(br["R"][2] @ nrm) >= abs(br["R"][1] @ nrm) else 4)]
                    continue
                soltar = True
            elif P["tesoura_rotulada_no_apoio"] and br["elemento"] == "trelica" and papeis_no[no] & {"viga", "pilar"}:
                soltar = True
            elif P["viga_pilar"] == "rotulada" and br["papel"] == "viga" and "pilar" in papeis_no[no]:
                soltar = True
            if soltar:
                base = 0 if ponta == "a" else 6
                br["soltos"] += [base + 4, base + 5]          # ry, rz da ponta (a torção fica)
    # apoios: o pé dos pilares (o nó mais baixo de cada um, na cota mais baixa dos pilares)
    pes = []
    zp = [min(nos[br["a"]][2], nos[br["b"]][2]) for br in barras if br["papel"] == "pilar"]
    z0 = min(zp) if zp else (float(nos[:, 2].min()) if len(nos) else 0.0)
    for br in barras:
        if br["papel"] != "pilar":
            continue
        n = br["a"] if nos[br["a"]][2] <= nos[br["b"]][2] else br["b"]
        if abs(nos[n][2] - z0) <= 0.05 and n not in pes:
            pes.append(n)
    if not pes:
        # sem pilar: os nós mais baixos
        pes = [int(i) for i in np.where(np.abs(nos[:, 2] - nos[:, 2].min()) < 0.05)[0]]
        avisos.append("o modelo não tem pilares: os apoios foram os nós mais baixos")
    apoios = []
    for n in pes:
        chave = "%d,%d" % (round(nos[n][0] * 1000), round(nos[n][1] * 1000))
        tipo = (P.get("bases") or {}).get(chave) or P["base"]
        apoios.append({"no": int(n), "tipo": tipo, "chave": chave})
    return {"nos": nos, "barras": barras, "apoios": apoios, "avisos": avisos, "par": P, "resumo_esqueleto": an["resumo"],
            "movel": movel}


def chave_do_grupo(br: dict, perfil: Optional[str] = None) -> str:
    """o grupo de uma barra para a troca de perfil: a função (o papel na treliça ou o da peça) e o perfil original"""
    return "%s|%s" % (br.get("papel_trelica") or br.get("papel") or "barra", perfil if perfil is not None else br.get("perfil_original") or br.get("perfil") or "")


def _trocar_perfis(barras: List[dict], P: dict, cache: dict, avisos: List[str]) -> None:
    """a troca de perfil da análise: cada barra do grupo ganha a seção do perfil novo (e guarda o original)"""
    trocas = P.get("trocas_perfil") or {}
    if not trocas:
        return
    fora, feitas = set(), collections.Counter()
    for br in barras:
        novo = trocas.get(chave_do_grupo(br))
        if not novo or novo == br["perfil"]:
            continue
        sec = _secao(novo, bool(br.get("duplo")), cache)
        if sec is None:
            fora.add(novo)
            continue
        br["perfil_original"] = br["perfil"]
        br["perfil"], br["sec"] = novo, sec
        feitas[chave_do_grupo(br)] += 1
    for k, n in feitas.items():
        f, p0 = k.split("|", 1)
        avisos.append("perfil trocado só na análise: %s %s → %s (%d barras; o modelo 3D não muda)" % (f, p0, trocas[k], n))
    for nome in sorted(fora):
        avisos.append("troca de perfil ignorada: \"%s\" não está no catálogo" % nome)


ESPESSURA_MIN_SUGESTAO = 1.5          # mm: a sugestão não oferece tubo de parede mais fina (a solda da treliça); digitar pode


def grupos_de_perfis(r: dict, outras: Sequence[dict] = (), limite: int = 20) -> List[dict]:
    """os grupos (função + perfil original) do resultado, com as alternativas do catálogo (mesma família) e, em cada uma,
    o uso ESTIMADO com os esforços da combinação que governa cada barra do grupo (N, Mz, My, nas situações todas):

    * σ elástica = |N|/A + |Mz|/Wz + |My|/Wy (o mesmo mapa da tela), em MPa;
    * uso = a interação da NBR 8800 (5.5.1.2) com N_Rd da compressão pela norma (χ e Q, flambagem com o comprimento da
      barra entre nós, K = 1) ou da tração (A·fy/1,10) e M_Rd = W·fy/1,10 — tira da lista o tubo de parede fina que passa
      na tensão e flamba muito antes.

    É estimativa: com o perfil novo os esforços se redistribuem (o recalcular confirma), o comprimento de flambagem é o
    da barra (fora do plano o banzo pode ter mais) e a flexão não tem FLT/FLM — a verificação completa é a etapa 4.
    Cada alternativa: [nome, kg/m, σ estimada MPa, uso estimado (1 = 100%)]; a lista: as mais pesadas das que não passam
    logo abaixo da mais leve que passa (a referência) e as que passam, da mais leve para cima."""
    from nucleo import catalogo, materiais as mat, nbr8800
    from nucleo3d.calculo_ifc import _perfil_de
    fy = float((r.get("parametros") or {}).get("fy_mpa") or 345.0)
    try:
        aco = next(a for a in mat.ACOS.values() if abs(a.fy * 10.0 - fy) < 0.5)
    except StopIteration:
        aco = mat.aco(mat.ACO_PADRAO)
    fyk = fy * 1000.0                                            # kN/m²
    grupos: Dict[str, dict] = {}
    for res in (r, *outras):
        for i, b in enumerate(res["barras"]):
            if b.get("hipotese"):
                continue
            k = chave_do_grupo(b)
            g = grupos.setdefault(k, {"chave": k, "funcao": k.split("|", 1)[0], "perfil": k.split("|", 1)[1], "atual": b["perfil"],
                                      "barras": 0, "duplo": bool(b.get("duplo")), "_esf": []})
            if res is r:
                g["barras"] += 1
            N, Mz, My = res["envoltoria"][i].get("esf") or [0.0, 0.0, 0.0]
            g["_esf"].append((float(N), abs(float(Mz)), abs(float(My)), float(b["L"])))
    secoes: Dict[str, Optional[dict]] = {}
    perfis: Dict[str, object] = {}
    ncrd: Dict[tuple, float] = {}

    def secao(nome, duplo):
        return _secao(nome, duplo, secoes)

    def nc_rd(nome, L, n):
        """N_c,Rd (kN) pela NBR 8800 com Lx = Ly = L (m); 0 se a norma não cobre (barra redonda)"""
        chave = (nome, round(L * 20) / 20)
        if chave not in ncrd:
            if nome not in perfis:
                perfis[nome] = _perfil_de(nome, "", {}, {})
            p = perfis[nome]
            try:
                v = float(nbr8800.compressao(p, aco, Lx=chave[1] * 100.0, Ly=chave[1] * 100.0, N_Sd=1.0).dados["N_Rd"])
            except Exception:                                    # noqa: BLE001 — a norma não cobre: não resiste à compressão
                v = 0.0
            ncrd[chave] = v
        return ncrd[chave] * n

    def criticas(g):
        """as barras que podem governar: maior σ, maior compressão e maior compressão × L² (a flambagem)"""
        s0 = secao(g["atual"], g["duplo"])
        E = g["_esf"]
        if s0 is None:
            return E[:12]
        sig = lambda e: abs(e[0]) / s0["A"] + e[1] / s0["Wz"] + e[2] / s0["Wy"]
        esc = set()
        for f in (sig, lambda e: max(0.0, -e[0]), lambda e: max(0.0, -e[0]) * e[3] ** 2):
            esc.update(sorted(range(len(E)), key=lambda j: -f(E[j]))[:4])
        return [E[j] for j in esc]

    def estimar(nome, g, crit, com_uso=True):
        sec = secao(nome, g["duplo"])
        if sec is None:
            return None
        n = 2 if g["duplo"] else 1
        sig = max(abs(N) / sec["A"] + Mz / sec["Wz"] + My / sec["Wy"] for N, Mz, My, L in g["_esf"]) / 1000.0
        if not com_uso:
            return sig, None
        uso = 0.0
        mz_rd, my_rd = sec["Wz"] * fyk / 1.10, sec["Wy"] * fyk / 1.10
        for N, Mz, My, L in crit:
            n_rd = nc_rd(nome, L, n) if N < 0 else sec["A"] * fyk / 1.10
            rn = abs(N) / n_rd if n_rd > 0 else (0.0 if abs(N) < 1e-6 else 99.0)
            rm = Mz / mz_rd + My / my_rd
            uso = max(uso, rn + 8.0 / 9.0 * rm if rn >= 0.2 else rn / 2.0 + rm)
        return sig, uso
    for g in grupos.values():
        crit = criticas(g)
        try:
            alts = catalogo.alternativas(g["perfil"], modo="todos", limite=5000)
        except Exception:                                       # noqa: BLE001 — fora do catálogo: só o campo livre
            alts = []
        cand = []
        for a in alts:
            if 0 < float(a.get("espessura") or 99.0) < ESPESSURA_MIN_SUGESTAO:
                continue                                         # parede fina demais para solda de treliça (prática)
            e = estimar(a["nome"], g, crit, com_uso=False)
            if e is not None:
                cand.append([a["nome"], round(float(a.get("massa") or 0.0), 2), e[0]])
        cand.sort(key=lambda a: (a[1], a[2]))
        passam, nao = [], []
        for a in cand:
            if a[2] > fy:                                        # nem a tensão passa: não precisa da flambagem
                nao.append(a + [None])
                continue
            _s, uso = estimar(a[0], g, crit)
            (passam if uso <= 1.0 else nao).append(a + [uso])
            if len(passam) >= limite:
                break
        if passam:
            leve = passam[0][1]
            lista = [a for a in nao if a[1] <= leve][-4:] + passam
        else:
            lista = sorted(nao, key=lambda a: (a[3] if a[3] is not None else 9e9, a[2]))[:limite]
            lista.sort(key=lambda a: a[1])
        g["alternativas"] = [[a[0], a[1], round(a[2], 1), None if a[3] is None else round(a[3], 3)] for a in lista]
        atual = estimar(g["atual"], g, crit)
        g["estimativa_atual"] = [round(atual[0], 1), round(atual[1], 3)] if atual else None
        g["mais_leve_que_passa"] = passam[0][0] if passam else None
        del g["_esf"]
    return sorted(grupos.values(), key=lambda g: g["chave"])


def _sem_copias_da_cobertura(doc):
    """o modelo sem a cobertura retrátil gerada no 3D (nucleo3d/cobertura_movel.py): a análise monta a dela — fica só a
    primeira tesoura gerada, levada de volta à posição da planta (o deslocamento `d` que a cópia guardou), que serve de
    molde, e a sanfona do 3D sai. Na posição da planta a tesoura está apoiada como foi lançada; empilhada (retraída) a
    primeira fica a centímetros da ponta da viga e o esqueleto não a apoia"""
    import copy
    from nucleo3d.cobertura_movel import _mover

    def cm(e):
        return (getattr(e, "atributos", None) or {}).get("cobertura_movel")

    def fica(e):
        c = cm(e)
        if not c:
            return True
        return (e.atributos or {}).get("elemento") == "trelica" and int(c.get("k", 0)) == 0
    if not any(cm(e) for e in doc.entidades.values()):
        return doc
    ents = {}
    for k, e in doc.entidades.items():
        if not fica(e):
            continue
        c = cm(e)
        if c and any(c.get("d") or ()):
            e = copy.deepcopy(e)
            _mover(e, [-v for v in c["d"]])
            e.atributos = dict(e.atributos, cobertura_movel=dict(c, d=[0.0, 0.0, 0.0]))
        ents[k] = e
    from nucleo3d.modelo import Documento
    return Documento(nome=doc.nome, unidade=doc.unidade, entidades=ents, camadas=doc.camadas, materiais=doc.materiais,
                     projeto=doc.projeto, metadados=doc.metadados)


def _cobertura_movel(nos: np.ndarray, barras: List[dict], P: dict, cache: dict, avisos: List[str], pilares_3d=()):
    """as tesouras da cobertura retrátil na situação `P["configuracao"]`: a primeira tesoura lançada é o molde, copiada
    em n posições ao longo das vigas-trilho; as lançadas saem da análise. Devolve (nos, barras, info)"""
    trel = [i for i, br in enumerate(barras) if br.get("elemento") == "trelica"]
    if not trel:
        avisos.append("cobertura retrátil: o modelo não tem tesoura lançada para servir de molde — calculado sem ela")
        return nos, barras, None
    grupos = collections.OrderedDict()
    for i in trel:
        grupos.setdefault(barras[i]["grupo"], []).append(i)
    g0, molde = next(iter(grupos.items()))
    usados_fora = collections.Counter()
    for i, br in enumerate(barras):
        if br.get("elemento") != "trelica":
            usados_fora[br["a"]] += 1
            usados_fora[br["b"]] += 1
    nos_molde = sorted({barras[i][k] for i in molde for k in ("a", "b")})
    apoio = [n for n in nos_molde if usados_fora[n]]                 # os nós da tesoura que são da viga/pilar
    if len(apoio) < 2:
        avisos.append("cobertura retrátil: a tesoura molde não está apoiada nas vigas — calculado sem ela")
        return nos, barras, None
    pts = nos[nos_molde]
    d = pts[:, :2].max(0) - pts[:, :2].min(0)
    u = _unit(np.array([d[0], d[1]]))
    n = np.array([-u[1], u[0]])
    t0 = float(nos[apoio[0]][:2] @ n)
    # o trilho: as vigas paralelas a n (a extensão delas ao longo de n)
    vigas = [i for i, br in enumerate(barras) if br["papel"] == "viga"]
    tv = [float(nos[barras[i][k]][:2] @ n) for i in vigas for k in ("a", "b")
          if abs(((nos[barras[i]["b"]] - nos[barras[i]["a"]])[:2] @ u)) < 0.05 * barras[i]["L"]]
    if not tv:
        avisos.append("cobertura retrátil: não achei as vigas-trilho ao longo do comprimento — calculado sem ela")
        return nos, barras, None
    tmin, tmax = min(tv), max(tv)
    # de pilar a pilar: as tesouras das pontas no eixo dos últimos pilares, como estão no 3D (a viga passa uns
    # centímetros do pilar e o esqueleto leva o topo do pilar à ponta dela)
    tp = [float(p[:2] @ n) for p in pilares_3d]
    tp = [t for t in tp if tmin - 0.5 <= t <= tmax + 0.5]
    if len(tp) >= 2 and max(tp) - min(tp) > 0.5 * (tmax - tmin):
        tmin, tmax = min(tp), max(tp)
    N = max(2, int(P.get("movel_n") or 38))
    La = min(float(P.get("movel_comprimento_aberta") or (tmax - tmin)), tmax - tmin)
    Lr = min(float(P.get("movel_comprimento_retraida") or 6.0), La)
    ponta_menor = (P.get("movel_lado_retraida") or "y_menor") == "y_menor"
    # o eixo n aponta para o Y maior ou menor? a ponta da pilha em coordenada t
    sinal_y = 1.0 if n[1] >= 0 else -1.0
    if abs(n[1]) < 1e-6:
        sinal_y = 1.0 if n[0] >= 0 else -1.0
    t_ponta = (tmin if sinal_y > 0 else tmax) if ponta_menor else (tmax if sinal_y > 0 else tmin)
    para_dentro = 1.0 if t_ponta == tmin else -1.0
    conf = P.get("configuracao") or "aberta"
    Lc = La if conf == "aberta" else Lr
    # a primeira e a última rentes aos pilares das pontas (pedido de 06/10): n tesouras, n − 1 vãos no comprimento
    passo = Lc / (N - 1)
    posicoes = [t_ponta + para_dentro * k * passo for k in range(N)]
    # fora as tesouras lançadas
    fora = set(trel)
    novas_barras = [br for i, br in enumerate(barras) if i not in fora]
    lista_nos = [np.array(p) for p in nos]

    def no_na_viga(p):
        """o nó da viga no ponto p (cria e parte a viga se preciso)"""
        for k, q in enumerate(lista_nos):
            if float(np.linalg.norm(q - p)) < 0.02:
                return k
        for j, br in enumerate(novas_barras):
            if br["papel"] != "viga":
                continue
            a, b = lista_nos[br["a"]], lista_nos[br["b"]]
            ab = b - a
            L2 = float(ab @ ab)
            if L2 < 1e-9:
                continue
            tt = float((p - a) @ ab) / L2
            if not (0.0 < tt < 1.0):
                continue
            if float(np.linalg.norm(a + ab * tt - p)) > 0.05:
                continue
            k = len(lista_nos)
            lista_nos.append(a + ab * tt)
            b2 = dict(br, a=k, L=float(np.linalg.norm(lista_nos[br["b"]] - lista_nos[k])), soltos=[s_ for s_ in br["soltos"] if s_ >= 6])
            br.update(b=k, L=float(np.linalg.norm(lista_nos[k] - lista_nos[br["a"]])), soltos=[s_ for s_ in br["soltos"] if s_ < 6])
            novas_barras.append(b2)
            return k
        k = len(lista_nos)
        lista_nos.append(np.array(p))
        avisos.append("cobertura retrátil: um apoio da tesoura ficou fora das vigas (%.2f; %.2f)" % (p[0], p[1]))
        return k
    # o peso: o total do fabricante dividido pelas tesouras, sobre o peso dos perfis do molde
    kg_molde = sum(barras[i]["sec"]["kg_m"] * barras[i]["L"] for i in molde)
    kg_alvo = float(P.get("movel_peso_total_kg") or 0.0) / N if P.get("movel_peso_total_kg") else kg_molde
    fator = kg_alvo / kg_molde if kg_molde > 0 else 1.0
    tesouras = []
    for k, t in enumerate(posicoes):
        dt = (t - t0) * np.array([n[0], n[1], 0.0])
        mapa = {}
        for no in nos_molde:
            if no in apoio:
                mapa[no] = no_na_viga(nos[no] + dt)
            else:
                mapa[no] = len(lista_nos)
                lista_nos.append(nos[no] + dt)
        g = "movel%02d" % (k + 1)
        for i in molde:
            br = barras[i]
            novas_barras.append(dict(br, a=mapa[br["a"]], b=mapa[br["b"]], grupo=g, soltos=[], pp_fator=fator,
                                     ids=["%s#%d" % (br["ids"][0] if br["ids"] else "t", k)], marca=br.get("marca")))
        # os dois lados: o apoio e o topo do montante externo (o nó mais alto em cima do apoio)
        lados = []
        for ap in apoio:
            pa = nos[ap]
            cima = [no for no in nos_molde if no != ap and float(np.linalg.norm((nos[no] - pa)[:2])) < 0.35]
            topo = max(cima, key=lambda no: nos[no][2]) if cima else None
            if topo is not None:
                lados.append((mapa[topo], mapa[ap]))
        # a faixa de lona de cada tesoura (meio vão de cada lado; as das pontas, só o de dentro)
        tesouras.append({"grupo": g, "t": t, "lados": lados, "faixa": passo / 2.0 if k in (0, N - 1) else passo})
    # a sanfona: o X entre tesouras vizinhas em cada plano lateral
    sec_s = _secao(P.get("perfil_sanfona") or "TQ 50×50×2,0", False, cache)
    nos_arr = np.array(lista_nos)
    ns = 0
    if sec_s is not None:
        for t1, t2 in zip(tesouras, tesouras[1:]):
            for (top1, bot1), (top2, bot2) in zip(t1["lados"], t2["lados"]):
                for a, b in ((top1, bot2), (bot1, top2)):
                    A, B = nos_arr[a], nos_arr[b]
                    L = float(np.linalg.norm(B - A))
                    if L < 1e-3:
                        continue
                    novas_barras.append({"a": int(a), "b": int(b), "L": L, "papel": "contraventamento", "papel_trelica": None,
                                         "elemento": "sanfona", "grupo": "sanfona", "marca": None, "perfil": P.get("perfil_sanfona"),
                                         "ids": [], "sec": sec_s, "R": _eixos(A, B, 0.0), "soltos": [4, 5, 10, 11]})
                    ns += 1
    altura_aba = float(np.mean([nos_arr[top][2] - nos_arr[bot][2] for t_ in tesouras for top, bot in t_["lados"]])) if tesouras else 0.0
    info = {"configuracao": conf, "n": N, "comprimento_m": round(Lc, 3), "passo_m": round(passo, 4), "peso_tesoura_kg": round(kg_alvo, 1),
            "peso_perfis_molde_kg": round(kg_molde, 1), "fator_peso": round(fator, 4), "sanfona_barras": ns,
            "altura_aba_m": round(altura_aba, 3), "tesouras": tesouras, "u": u.tolist(), "n_dir": n.tolist(),
            "lancadas_fora": len(grupos), "t0": t0, "molde_grupo": g0,
            "molde_ids": sorted({i_ for i in molde for i_ in barras[i]["ids"]})}
    avisos.append(("cobertura retrátil, situação %s: %d tesouras (molde %s) a cada %.3f m em %.2f m; peso de cada %.1f kg "
                   "(%.0f kg ÷ %d; os perfis do molde pesam %.1f kg); sanfona com %d braços %s; as %d tesouras lançadas no "
                   "modelo ficaram fora (a cobertura é do fabricante)")
                  % (conf, N, barras[molde[0]].get("marca") or "", passo, Lc, kg_alvo, float(P.get("movel_peso_total_kg") or 0), N,
                     kg_molde, ns, P.get("perfil_sanfona"), len(grupos)))
    return nos_arr, novas_barras, info


def _travamento_hipotese(nos: np.ndarray, barras: List[dict], P: dict, cache: dict, avisos: List[str]) -> List[dict]:
    """as terças e o contraventamento de hipótese (barras só da análise), quando o modelo tem tesouras e não tem terças"""
    modo = P.get("travamento_hipotese", "auto")
    tem_terca = any(br["papel"] in ("terça", "terca") for br in barras)
    sup = [i for i, br in enumerate(barras) if br.get("papel_trelica") == "banzo_sup"]
    if modo == "nao" or not sup or (modo == "auto" and tem_terca):
        return []
    sec_t = _secao(P["perfil_terca_hipotese"], False, cache)
    sec_c = _secao(P["perfil_contravento_hipotese"], False, cache)
    if sec_t is None or sec_c is None:
        avisos.append("os perfis do travamento de hipótese não estão no catálogo: a análise segue sem eles")
        return []
    # os nós do banzo superior de cada tesoura, em ordem ao longo do vão
    por_trel: Dict[str, set] = collections.defaultdict(set)
    for i in sup:
        por_trel[barras[i]["grupo"]].update((barras[i]["a"], barras[i]["b"]))
    trel = []
    for g, ns in por_trel.items():
        pts = nos[list(ns)]
        d = pts[:, :2].max(0) - pts[:, :2].min(0)
        u = _unit(np.array([d[0], d[1]])) if np.linalg.norm(d) > 1e-6 else np.array([1.0, 0.0])
        if abs(u[0]) >= abs(u[1]):
            u = np.array([1.0, 0.0]) * np.sign(u[0] or 1)
        n = np.array([-u[1], u[0]])
        lista = sorted(ns, key=lambda k: float(nos[k][:2] @ u))
        trel.append({"g": g, "nos": lista, "u": u, "n": n, "off": float(pts[:, :2].mean(0) @ n)})
    trel.sort(key=lambda t: t["off"])
    novas: List[dict] = []

    def barra(a, b, papel, sec, perfil):
        A, B = nos[a], nos[b]
        L = float(np.linalg.norm(B - A))
        if L < 1e-3:
            return None
        return {"a": int(a), "b": int(b), "L": L, "papel": papel, "papel_trelica": None, "elemento": None, "grupo": "hipotese",
                "marca": None, "perfil": perfil, "ids": [], "sec": sec, "R": _eixos(A, B, 0.0), "soltos": [4, 5, 10, 11],
                "hipotese": True}
    pares_vizinhos = []
    for t1, t2 in zip(trel, trel[1:]):
        if abs(t1["u"] @ t2["u"]) < 0.98:
            continue
        # o nó da outra tesoura na mesma posição ao longo do vão (a até 30 cm)
        s2 = [(float(nos[k][:2] @ t1["u"]), k) for k in t2["nos"]]
        casados = []
        for k in t1["nos"]:
            sk = float(nos[k][:2] @ t1["u"])
            d, k2 = min(((abs(sk - x), kk) for x, kk in s2), default=(1e9, None))
            if k2 is not None and d <= 0.30:
                casados.append((k, k2))
        if len(casados) < 2:
            continue
        pares_vizinhos.append(casados)
        for k, k2 in casados:
            b = barra(k, k2, "terça", sec_t, P["perfil_terca_hipotese"])
            if b:
                novas.append(b)
    # o X nos vãos das pontas (o primeiro e o último par de tesouras), em cada painel entre terças
    if pares_vizinhos:
        for casados in {id(pares_vizinhos[0]): pares_vizinhos[0], id(pares_vizinhos[-1]): pares_vizinhos[-1]}.values():
            for (k1, k2), (m1, m2) in zip(casados, casados[1:]):
                for a, b in ((k1, m2), (m1, k2)):
                    br = barra(a, b, "contraventamento", sec_c, P["perfil_contravento_hipotese"])
                    if br:
                        novas.append(br)
        nt = sum(1 for b in novas if b["papel"] == "terça")
        nc = len(novas) - nt
        avisos.append(("hipótese de travamento (o modelo não tem terças nem contraventamento): %d terças %s ligando os nós do "
                       "banzo superior e %d diagonais %s em X nos vãos das pontas, só na análise — sem elas a tesoura gira em "
                       "torno dos apoios. Modele as terças e o contraventamento reais para o cálculo final")
                      % (nt, P["perfil_terca_hipotese"], nc, P["perfil_contravento_hipotese"]))
    return novas


# ------------------------------------------------------------------ cargas

def _tesouras_e_cobertura(M: dict) -> dict:
    """os nós do banzo superior das treliças com a área de influência de cada trecho: {barra: (Ls, Lh, largura)}"""
    nos, barras = M["nos"], M["barras"]
    sup = [i for i, br in enumerate(barras) if br.get("papel_trelica") == "banzo_sup" or
           (br["papel"] == "banzo" and br.get("elemento") != "trelica" and False)]
    por_trelica: Dict[str, List[int]] = collections.defaultdict(list)
    for i in sup:
        por_trelica[barras[i]["grupo"]].append(i)
    if not por_trelica:
        return {}
    # o plano de cada treliça: a direção horizontal do banzo e a posição na perpendicular
    planos = {}
    for g, bs in por_trelica.items():
        pts = np.array([nos[barras[i][k]] for i in bs for k in ("a", "b")])
        d = pts[:, :2].max(0) - pts[:, :2].min(0)
        dirs = []
        for i in bs:
            v = nos[barras[i]["b"]][:2] - nos[barras[i]["a"]][:2]
            if np.linalg.norm(v) > 1e-6:
                v = _unit(v)
                dirs.append(v if v[0] + v[1] * 1e-3 >= 0 else -v)
        u = _unit(np.mean(dirs, axis=0)) if dirs else np.array([1.0, 0.0])
        n = np.array([-u[1], u[0]])
        c = pts[:, :2].mean(0)
        planos[g] = {"u": u, "n": n, "off": float(c @ n), "c": c, "s0": float((pts[:, :2] @ u).min()), "s1": float((pts[:, :2] @ u).max())}
    # largura: meia distância às treliças vizinhas paralelas (que se sobrepõem no vão)
    gs = list(planos)
    larg = {}
    for g in gs:
        p = planos[g]
        viz = []
        for h in gs:
            if h == g:
                continue
            q = planos[h]
            if abs(p["u"][0] * q["u"][1] - p["u"][1] * q["u"][0]) > 0.1:
                continue
            if min(p["s1"], q["s1"]) - max(p["s0"], q["s0"]) < 0.3 * (p["s1"] - p["s0"]):
                continue
            viz.append(float(q["c"] @ p["n"]) - p["off"])
        mais = [v for v in viz if v > 0.05]
        menos = [-v for v in viz if v < -0.05]
        lados = ([min(mais)] if mais else []) + ([min(menos)] if menos else [])
        larg[g] = sum(lados) / 2.0 if len(lados) == 2 else (lados[0] / 2.0 if lados else 0.0)
    out = {}
    for g, bs in por_trelica.items():
        for i in bs:
            a, b = nos[barras[i]["a"]], nos[barras[i]["b"]]
            Ls = float(np.linalg.norm(b - a))
            Lh = float(np.linalg.norm((b - a)[:2]))
            out[i] = (Ls, Lh, larg[g])
    return {"trechos": out, "planos": planos, "larguras": larg}


def _vento(M: dict, cob: dict, avisos: List[str]) -> Tuple[Dict[str, dict], dict]:
    """os casos de vento da cobertura isolada (NBR 6123:2023, 7.2): {caso: {barra: força nodal por ponta (kN, 3)}}"""
    from nucleo import cargas as C
    P, nos, barras = M["par"], M["nos"], M["barras"]
    if not P.get("vento") or not cob:
        return {}, {}
    trechos, planos = cob["trechos"], cob["planos"]
    pts = np.array([nos[barras[i][k]] for i in trechos for k in ("a", "b")])
    zt = float(pts[:, 2].max())
    # dimensões em planta da cobertura e a maior dimensão (classe)
    u = np.mean([p["u"] for p in planos.values()], axis=0)
    u = _unit(u)
    n = np.array([-u[1], u[0]])
    s = pts[:, :2] @ u
    t = pts[:, :2] @ n
    vao, prof = float(s.max() - s.min()), float(t.max() - t.min())
    maior = max(vao, prof, zt)
    classe = P.get("classe") or ("A" if maior <= 20 else "B" if maior <= 50 else "C")
    S2 = C.fator_s2(P["categoria"], classe, max(zt, 1.0))
    Vk = C.velocidade_caracteristica(float(P["v0"]), float(P["s1"]), S2, float(P["s3"]))
    q = C.pressao_dinamica(Vk)
    # a inclinação equivalente: a flecha da cobertura sobre o meio vão (tg θ), pelos nós do banzo superior
    zb = float(pts[:, 2].min())
    flecha = zt - zb
    tg = flecha / (vao / 2.0) if vao > 0 else 0.0
    h_livre = zb
    info = {"Vk": round(Vk, 2), "S2": round(S2, 3), "q_kN_m2": round(q, 3), "classe": classe, "z": round(zt, 2),
            "vao": round(vao, 2), "profundidade": round(prof, 2), "flecha": round(flecha, 3), "tg": round(tg, 3),
            "h_livre": round(h_livre, 2)}
    if tg < 0.07:
        avisos.append("cobertura quase plana (tg θ = %.3f < 0,07): a Tabela 25 da NBR 6123 começa em 0,07 — usado 0,07" % tg)
        tg = 0.07
    if tg > 0.6:
        avisos.append("tg θ = %.2f acima de 0,6: fora da Tabela 25 da NBR 6123 — usado 0,6" % tg)
        tg = 0.6
    if tg <= 0.4:
        c1 = (2.4 * tg + 0.6, 3.0 * tg - 0.5)
        c2 = (0.6 * tg - 0.74, -1.0)
    else:
        c1 = (min(2.4 * tg + 0.6, 2.0), 0.7)
        c2 = (6.5 * tg - 3.1, 5.0 * tg - 3.0)
    info["carregamento_1"] = {"cpb": round(c1[0], 3), "cps": round(c1[1], 3)}
    info["carregamento_2"] = {"cpb": round(c2[0], 3), "cps": round(c2[1], 3)}
    if h_livre < 0.5 * vao:
        avisos.append(("vento: a altura livre (%.2f m) é menor que 0,5 × a profundidade da cobertura (%.2f m) — a NBR 6123 "
                       "(7.2.1) pede, nesse caso, calcular como edificação fechada com cpi +0,8/−0,3 na zona de obstrução. "
                       "Usada a Tabela 25 (cobertura isolada): conferir com o engenheiro") % (h_livre, 0.5 * vao))
    smid = float((s.max() + s.min()) / 2)
    casos: Dict[str, dict] = {}
    for nome_c, (cpb, cps) in (("1", c1), ("2", c2)):
        for sentido, rot in ((+1, "→"), (-1, "←")):
            f: Dict[int, np.ndarray] = {}
            for i, (Ls, Lh, w) in trechos.items():
                a, b = nos[barras[i]["a"]], nos[barras[i]["b"]]
                m = (a + b) / 2
                barlavento = (float(m[:2] @ u) - smid) * sentido < 0
                cp = cpb if barlavento else cps
                d = _unit(b - a)
                up = np.array([0.0, 0.0, 1.0])
                nn = _unit(up - (up @ d) * d)                 # normal ao trecho, para cima
                F = -cp * q * Ls * w * nn                    # cp positivo empurra para baixo
                f[i] = F / 2.0
            mv = M.get("movel")
            fn: Dict[int, np.ndarray] = {}
            if mv and mv.get("altura_aba_m", 0) > 0:
                # as abas de lona nas bordas (NBR 6123, 7.2.5.1): 1,3·q·Ae a barlavento e 0,6·q·Ae a sotavento, as duas no
                # sentido do vento; cada tesoura recebe a faixa dela (meio passo de cada lado), metade no topo e metade no apoio
                dirv = np.array([u[0] * sentido, u[1] * sentido, 0.0])
                for t_ in mv["tesouras"]:
                    for top, bot in t_["lados"]:
                        pa = nos[bot]
                        barl = (float(pa[:2] @ u) - smid) * sentido < 0
                        Ae = (nos[top][2] - nos[bot][2]) * t_["faixa"]
                        Fa = (1.3 if barl else 0.6) * q * Ae * dirv
                        for no_ in (top, bot):
                            fn[no_] = fn.get(no_, np.zeros(3)) + Fa / 2.0
            casos["V%s%s" % (nome_c, rot)] = {"dist": {}, "nos": fn, "nodal": f, "descricao": "vento perpendicular à geratriz, carregamento %s, %s"
                                              % (nome_c, "de um lado" if sentido > 0 else "do outro lado"),
                                              "cpb": cpb, "cps": cps, "sentido": [float(v) for v in u * sentido]}
    # atrito no sentido da geratriz (7.2.2): F = 0,05 q a b, distribuída pelas áreas
    area_tot = sum(Lh * w for (Ls, Lh, w) in trechos.values()) or 1.0
    Ft = 0.05 * q * vao * prof
    for sentido, rot in ((+1, "↑"), (-1, "↓")):
        f = {}
        for i, (Ls, Lh, w) in trechos.items():
            F = np.zeros(3)
            F[:2] = n * sentido * Ft * (Lh * w) / area_tot
            f[i] = F / 2.0
        casos["Vat%s" % rot] = {"dist": {}, "nodal": f, "descricao": "vento ao longo da geratriz: atrito na cobertura (7.2.2)", "Ft": Ft}
    info["atrito_kN"] = round(Ft, 2)
    return casos, info


def cargas(M: dict) -> Tuple[Dict[str, dict], dict, List[str]]:
    """os casos de carga: {caso: {"dist": {barra: w global (kN/m)}, "nodal": {barra: força por ponta}}}, informações"""
    P, nos, barras = M["par"], M["nos"], M["barras"]
    avisos: List[str] = []
    casos: Dict[str, dict] = {}
    # peso próprio: distribuído na barra
    pp = {i: np.array([0.0, 0.0, -br["sec"]["kg_m"] * float(br.get("pp_fator", 1.0)) * G_GRAV]) for i, br in enumerate(barras)}
    casos["PP"] = {"dist": pp, "nodal": {}, "descricao": "peso próprio da estrutura (pelo perfil)"}
    cob = _tesouras_e_cobertura(M)
    info: dict = {}
    if not cob:
        avisos.append("o modelo não tem banzo superior de treliça: telha, sobrecarga e vento não foram aplicados")
    else:
        g_cob = float(P["telha"]) + float(P.get("carga_extra") or 0.0)
        cp, sc = {}, {}
        for i, (Ls, Lh, w) in cob["trechos"].items():
            cp[i] = np.array([0.0, 0.0, -g_cob * Ls * w / 2.0])
            sc[i] = np.array([0.0, 0.0, -float(P["sobrecarga"]) * Lh * w / 2.0])
        casos["CP"] = {"dist": {}, "nodal": cp, "descricao": "telha e permanentes da cobertura (%.2f kN/m²)" % g_cob}
        if not (M.get("movel") and M["movel"]["configuracao"] != "aberta"):
            casos["SC"] = {"dist": {}, "nodal": sc, "descricao": "sobrecarga de cobertura (%.2f kN/m², projeção horizontal)" % float(P["sobrecarga"])}
        area = sum(Lh * w for (Ls, Lh, w) in cob["trechos"].values())
        info["cobertura"] = {"area_m2": round(area, 1), "larguras_m": sorted({round(v, 3) for v in cob["larguras"].values()}),
                             "trelicas": len(cob["planos"])}
        vc, vi = _vento(M, cob, avisos)
        casos.update(vc)
        if vi:
            info["vento"] = vi
    return casos, info, avisos


def combinacoes(casos: Sequence[str]) -> Dict[str, dict]:
    """as combinações da NBR 8800 (Tabelas 1 e 2): ELU normais e ELS (raras e frequentes)"""
    from nucleo import cargas as C
    gpp = C.GAMA_G["metálica"][0]
    gcp = C.GAMA_G["moldada no local"][0]              # elementos construtivos industrializados (telha, terças)
    gsc, gv = C.GAMA_Q["sobrecarga"][0], C.GAMA_Q["vento"][0]
    psc0, pv0 = C.PSI["cobertura"][0], C.PSI["vento"][0]
    psc1, pv1 = C.PSI["cobertura"][1], C.PSI["vento"][1]
    tem = set(casos)
    ventos = [c for c in casos if c.startswith("V")]
    G = {"PP": gpp, **({"CP": gcp} if "CP" in tem else {})}
    Gf = {"PP": 1.0, **({"CP": 1.0} if "CP" in tem else {})}
    out: Dict[str, dict] = {}
    if "SC" in tem:
        out["ELU1 SC"] = {"tipo": "ELU", "fatores": {**G, "SC": gsc}, "descricao": "permanentes + sobrecarga principal"}
    for v in ventos:
        pressao = not v.startswith("V2")                 # o carregamento 2 é sucção: permanentes favoráveis
        if pressao:
            out["ELU %s" % v] = {"tipo": "ELU", "fatores": {**G, v: gv, **({"SC": gsc * psc0} if "SC" in tem else {})},
                                 "descricao": "permanentes + vento %s principal + sobrecarga" % v}
            if "SC" in tem:
                out["ELU SC+%s" % v] = {"tipo": "ELU", "fatores": {**G, "SC": gsc, v: gv * pv0},
                                        "descricao": "permanentes + sobrecarga principal + vento %s" % v}
        out["ELU %s suc" % v if pressao else "ELU %s" % v] = {"tipo": "ELU", "fatores": {**Gf, v: gv},
                                                             "descricao": "permanentes favoráveis + vento %s (sucção)" % v}
    if not out:
        out["ELU PP"] = {"tipo": "ELU", "fatores": dict(G), "descricao": "permanentes"}
    # serviço
    if "SC" in tem:
        out["ELS SC"] = {"tipo": "ELS", "fatores": {"PP": 1.0, **({"CP": 1.0} if "CP" in tem else {}), "SC": 1.0},
                         "descricao": "rara: permanentes + sobrecarga"}
    for v in ventos:
        out["ELS %s" % v] = {"tipo": "ELS", "fatores": {"PP": 1.0, **({"CP": 1.0} if "CP" in tem else {}), v: 1.0},
                             "descricao": "rara: permanentes + vento %s" % v}
    return out


# ------------------------------------------------------------------ resolver

def resolver(M: dict, casos: Dict[str, dict]) -> dict:
    """resolve todos os casos de uma vez: deslocamentos, reações e esforços nas pontas de cada barra (local)"""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import splu
    nos, barras = M["nos"], M["barras"]
    N = len(nos)
    ndof = 6 * N
    nomes = list(casos)
    F = np.zeros((ndof, len(nomes)))
    rows, cols, vals = [], [], []
    elem = []
    for i, br in enumerate(barras):
        s = br["sec"]
        k = _rigidez_local(br["L"], s["A"], s["Iy"], s["Iz"], s["J"])
        R = br["R"]
        T = np.zeros((12, 12))
        for j in range(4):
            T[3 * j:3 * j + 3, 3 * j:3 * j + 3] = R
        # carga distribuída de cada caso, no local
        w_loc = np.zeros((len(nomes), 3))
        f0 = np.zeros((len(nomes), 12))
        for c, nome in enumerate(nomes):
            wg = casos[nome]["dist"].get(i)
            if wg is not None:
                w_loc[c] = R @ wg
                f0[c] = _engaste_perfeito(br["L"], w_loc[c])
        kc = k
        rec = None
        f0c = f0.copy()
        if br["soltos"]:
            kc, _f, rec = _condensar(k, np.zeros(12), br["soltos"])
            for c in range(len(nomes)):
                _k, f0c[c], _r = _condensar(k, f0[c], br["soltos"])
        kg = T.T @ kc @ T
        dofs = np.r_[6 * br["a"]:6 * br["a"] + 6, 6 * br["b"]:6 * br["b"] + 6]
        rows.append(np.repeat(dofs, 12)); cols.append(np.tile(dofs, 12)); vals.append(kg.ravel())
        for c in range(len(nomes)):
            if np.any(f0c[c]):
                F[dofs, c] -= T.T @ f0c[c]
        elem.append((k, kc, T, dofs, f0, f0c, w_loc, rec))
    # cargas nodais (por barra: a força em cada ponta) e as diretas em nós
    for c, nome in enumerate(nomes):
        for i, Fp in casos[nome]["nodal"].items():
            br = barras[i]
            for no in (br["a"], br["b"]):
                F[6 * no:6 * no + 3, c] += Fp
        for no, Fp in (casos[nome].get("nos") or {}).items():
            F[6 * no:6 * no + 3, c] += Fp
    K = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(ndof, ndof)).tocsr()
    # apoios
    fixos = set()
    for ap in M["apoios"]:
        n = ap["no"]
        fixos.update(range(6 * n, 6 * n + (6 if ap["tipo"] == "engastada" else 3)))
    # graus sem rigidez (nó só de barras rotuladas): presos, com aviso
    diag = K.diagonal()
    escala = float(np.max(np.abs(diag))) if len(diag) else 1.0
    com_barra = {br["a"] for br in barras} | {br["b"] for br in barras}
    soltos = [d for d in range(ndof) if abs(diag[d]) < 1e-9 * escala and d not in fixos]
    soltos_reais = [d for d in soltos if d // 6 in com_barra]
    fixos.update(soltos)
    livres = np.array([d for d in range(ndof) if d not in fixos], int)
    Kff = K[livres][:, livres].tocsc()
    U = np.zeros((ndof, len(nomes)))
    instavel = None
    try:
        lu = splu(Kff)
        U[livres] = lu.solve(F[livres])
    except RuntimeError as e:
        instavel = str(e)
    if instavel is None:
        # mecanismo que o fatoramento não pegou: deslocamento absurdo
        if not np.all(np.isfinite(U)) or float(np.abs(U[0::6].tolist() + U[1::6].tolist() + U[2::6].tolist()).max(initial=0)) > 50.0:
            instavel = "deslocamentos sem limite (mecanismo)"
    R_all = K @ U - F
    reac = {int(ap["no"]): R_all[6 * ap["no"]:6 * ap["no"] + 6] for ap in M["apoios"]}
    # esforços nas pontas (local), por caso: f = kc·u + f0c; os graus soltos recuperados (deram zero de momento)
    pontas = np.zeros((len(barras), len(nomes), 12))
    wloc = np.zeros((len(barras), len(nomes), 3))
    for i, (k, kc, T, dofs, f0, f0c, w_loc, rec) in enumerate(elem):
        ul = (T @ U[dofs]).T                          # (casos, 12)
        if rec is not None:
            r, m, inv, krm = rec
            for c in range(len(nomes)):
                ul[c, r] = -inv @ (krm @ ul[c, m] + f0[c][r])
            pontas[i] = (k @ ul.T).T + f0
        else:
            pontas[i] = (k @ ul.T).T + f0
        wloc[i] = w_loc
    return {"casos": nomes, "U": U, "reacoes": reac, "pontas": pontas, "w": wloc, "instavel": instavel,
            "graus_presos": len(soltos_reais)}


# ------------------------------------------------------------------ esforços ao longo da barra e tensões

def esforcos_em(f_i: np.ndarray, w: np.ndarray, x: np.ndarray) -> np.ndarray:
    """(len(x), 6): N, Vy, Vz, T, My, Mz na seção x da barra (a face positiva; N > 0 tração)"""
    Fx, Fy, Fz, Mx, My, Mz = f_i[:6]
    wx, wy, wz = w
    N = -(Fx + wx * x)
    Vy = -(Fy + wy * x)
    Vz = -(Fz + wz * x)
    T = -Mx + 0 * x
    My_ = -(My + x * Fz + wz * x * x / 2)
    Mz_ = -(Mz - x * Fy - wy * x * x / 2)
    return np.stack([N, Vy, Vz, T, My_, Mz_], axis=1)


ESTACOES = 9


def resultados(M: dict, casos: Dict[str, dict], sol: dict, combs: Dict[str, dict]) -> dict:
    """por barra: as pontas e a carga de cada caso (o diagrama no navegador), e por combinação o pico de cada esforço,
    a tensão máxima e onde; as reações e deslocamentos por combinação; os mais solicitados"""
    nos, barras = M["nos"], M["barras"]
    nomes = sol["casos"]
    idx = {c: k for k, c in enumerate(nomes)}
    fy = float(M["par"].get("fy_mpa") or 345.0)
    xs = [np.linspace(0, br["L"], ESTACOES) for br in barras]
    por_comb: Dict[str, dict] = {}
    for cn, cb in combs.items():
        fat = np.zeros(len(nomes))
        for c, v in cb["fatores"].items():
            if c in idx:
                fat[idx[c]] = v
        U = sol["U"] @ fat
        desl = U.reshape(-1, 6)[:, :3]
        reac = {n: (r @ fat) for n, r in sol["reacoes"].items()}
        bar = []
        for i, br in enumerate(barras):
            f_i = np.tensordot(fat, sol["pontas"][i], axes=1)
            w = fat @ sol["w"][i]
            e = esforcos_em(f_i, w, xs[i])
            s = br["sec"]
            sig = (np.abs(e[:, 0]) / s["A"] + np.abs(e[:, 5]) / s["Wz"] + np.abs(e[:, 4]) / s["Wy"]) / 1000.0   # MPa
            k = int(np.argmax(sig))
            bar.append({
                "N": [round(float(e[:, 0].min()), 2), round(float(e[:, 0].max()), 2)],
                "V": round(float(np.max(np.hypot(e[:, 1], e[:, 2]))), 2),
                "M": round(float(np.max(np.hypot(e[:, 4], e[:, 5]))), 3),
                "sigma": round(float(sig[k]), 1), "x": round(float(xs[i][k] / br["L"]), 2),
                "esf": [round(float(e[k, 0]), 2), round(float(e[k, 5]), 3), round(float(e[k, 4]), 3)],
            })
        por_comb[cn] = {"desl_mm": np.round(desl * 1000, 2), "reacoes": reac, "barras": bar}
    # envoltória e ranking (ELU)
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    env = []
    for i, br in enumerate(barras):
        melhor = max(elu, key=lambda c: por_comb[c]["barras"][i]["sigma"]) if elu else None
        b = por_comb[melhor]["barras"][i] if melhor else {"sigma": 0, "N": [0, 0], "M": 0, "V": 0, "x": 0}
        Nmin = min(por_comb[c]["barras"][i]["N"][0] for c in elu) if elu else 0
        Nmax = max(por_comb[c]["barras"][i]["N"][1] for c in elu) if elu else 0
        Mmax = max(por_comb[c]["barras"][i]["M"] for c in elu) if elu else 0
        env.append({"sigma": b["sigma"], "taxa": round(b["sigma"] / fy, 3), "comb": melhor, "N": [Nmin, Nmax], "M": Mmax,
                    "esf": b.get("esf", [0.0, 0.0, 0.0]),
                    "V": max(por_comb[c]["barras"][i]["V"] for c in elu) if elu else 0})
    return {"por_comb": por_comb, "envoltoria": env}


# ------------------------------------------------------------------ o cálculo inteiro

def calcular(doc, par: Optional[dict] = None) -> dict:
    """a análise; com a cobertura retrátil, as duas situações (aberta e retraída) e a envoltória das reações das duas"""
    P = dict(PARAMETROS_PADRAO, **(par or {}))
    if not P.get("cobertura_movel"):
        r = _calcular_situacao(doc, P)
        r["reacoes_envoltoria"] = envoltoria_das_reacoes({"": r})
        r["grupos_perfis"] = grupos_de_perfis(r)
        return r
    r_a = _calcular_situacao(doc, dict(P, configuracao="aberta"))
    r_r = _calcular_situacao(doc, dict(P, configuracao="retraida"))
    r_a["situacao"] = "aberta"
    r_r["situacao"] = "retraida"
    r_a["outras_situacoes"] = {"retraida": r_r}
    r_a["reacoes_envoltoria"] = envoltoria_das_reacoes({"aberta": r_a, "retraida": r_r})
    r_a["grupos_perfis"] = grupos_de_perfis(r_a, [r_r])
    return r_a


def envoltoria_das_reacoes(sits: Dict[str, dict]) -> List[dict]:
    """por base (a chave x,y): Fz máx e mín, H e M máx nas combinações últimas das situações, com onde cada um acontece"""
    por: Dict[str, dict] = {}
    for nome, r in sits.items():
        elu = [c for c, cb in r["combinacoes"].items() if cb["tipo"] == "ELU"]
        for ap in r["apoios"]:
            k = ap["chave"]
            e = por.setdefault(k, {"chave": k, "tipo": ap["tipo"], "Fz_max": [-1e18, ""], "Fz_min": [1e18, ""], "H_max": [0.0, ""],
                                    "M_max": [0.0, ""], "concomitantes": {}})
            for c in elu:
                rr = r["por_comb"][c]["reacoes"].get(str(ap["no"]))
                if rr is None:
                    continue
                onde = "%s · %s" % (nome, c)
                H, Mm = math.hypot(rr[0], rr[1]), math.hypot(rr[3], rr[4])
                if rr[2] > e["Fz_max"][0]:
                    e["Fz_max"] = [rr[2], onde]; e["concomitantes"]["Fz_max"] = [round(v, 2) for v in rr]
                if rr[2] < e["Fz_min"][0]:
                    e["Fz_min"] = [rr[2], onde]; e["concomitantes"]["Fz_min"] = [round(v, 2) for v in rr]
                if H > e["H_max"][0]:
                    e["H_max"] = [H, onde]; e["concomitantes"]["H_max"] = [round(v, 2) for v in rr]
                if Mm > e["M_max"][0]:
                    e["M_max"] = [Mm, onde]; e["concomitantes"]["M_max"] = [round(v, 2) for v in rr]
    for e in por.values():
        for k in ("Fz_max", "Fz_min", "H_max", "M_max"):
            e[k][0] = round(e[k][0], 2)
    return sorted(por.values(), key=lambda e: tuple(int(v) for v in e["chave"].split(",")))


def _calcular_situacao(doc, par: Optional[dict] = None) -> dict:
    """modelo → cargas → combinações → resolver → resultados, no formato que a tela de análise lê (JSON)"""
    M = montar(doc, par)
    casos, info, av_c = cargas(M)
    combs = combinacoes(list(casos))
    sol = resolver(M, casos)
    avisos = list(M["avisos"]) + av_c
    if sol["instavel"]:
        avisos.insert(0, ("A estrutura está instável (%s): falta travamento — contraventamento, base engastada ou ligação "
                          "viga–pilar rígida. Os resultados não valem.") % sol["instavel"])
    if sol["graus_presos"]:
        avisos.append("%d grau(s) de liberdade sem rigidez foram presos (nós só de barras rotuladas)" % sol["graus_presos"])
    res = resultados(M, casos, sol, combs)
    nos, barras = M["nos"], M["barras"]
    nomes = sol["casos"]
    # equilíbrio de cada caso: soma das cargas + soma das reações
    equil = {}
    for c, nome in enumerate(nomes):
        diretas = list((casos[nome].get("nos") or {}).values())
        Fz = sum(float(v[2]) for v in diretas) + sum(float(v[2]) * 2 for v in casos[nome]["nodal"].values()) + \
            sum(float(w[2]) * barras[i]["L"] for i, w in casos[nome]["dist"].items())
        Fx = sum(float(v[0]) for v in diretas) + sum(float(v[0]) * 2 for v in casos[nome]["nodal"].values()) + \
            sum(float(w[0]) * barras[i]["L"] for i, w in casos[nome]["dist"].items())
        Fy = sum(float(v[1]) for v in diretas) + sum(float(v[1]) * 2 for v in casos[nome]["nodal"].values()) + \
            sum(float(w[1]) * barras[i]["L"] for i, w in casos[nome]["dist"].items())
        Rz = sum(float(r[2, c]) for r in (np.array(sol["reacoes"][n]) for n in sol["reacoes"]))
        Rx = sum(float(r[0, c]) for r in (np.array(sol["reacoes"][n]) for n in sol["reacoes"]))
        Ry = sum(float(r[1, c]) for r in (np.array(sol["reacoes"][n]) for n in sol["reacoes"]))
        equil[nome] = {"cargas_kN": [round(Fx, 2), round(Fy, 2), round(Fz, 2)], "reacoes_kN": [round(Rx, 2), round(Ry, 2), round(Rz, 2)]}
    saida = {
        "versao": 1,
        "parametros": {k: v for k, v in M["par"].items()},
        "resumo_esqueleto": M["resumo_esqueleto"],
        "nos": np.round(nos * 1000, 1).tolist(),
        "apoios": M["apoios"],
        "barras": [{"a": br["a"], "b": br["b"], "papel": br["papel"], "papel_trelica": br["papel_trelica"],
                    "elemento": br["elemento"], "marca": br["marca"], "perfil": br["perfil"], "ids": br["ids"],
                    "L": round(br["L"], 4), "ey": np.round(br["R"][1], 4).tolist(), "ez": np.round(br["R"][2], 4).tolist(),
                    "rotulas": [p for p in ("a", "b") if (4 if p == "a" else 10) in br["soltos"]],
                    "A": br["sec"]["A"], "Wz": br["sec"]["Wz"], "Wy": br["sec"]["Wy"], "hipotese": bool(br.get("hipotese")),
                    **({"duplo": True} if br.get("duplo") else {}),
                    **({"perfil_original": br["perfil_original"]} if br.get("perfil_original") else {})}
                   for br in barras],
        "casos": {nome: {"descricao": casos[nome].get("descricao", nome),
                         "nodal": {str(i): np.round(v, 4).tolist() for i, v in casos[nome]["nodal"].items()},
                         "nos": {str(i): np.round(v, 4).tolist() for i, v in (casos[nome].get("nos") or {}).items()},
                         "dist": {str(i): np.round(v, 4).tolist() for i, v in casos[nome]["dist"].items()}}
                  for nome in nomes},
        # por barra e caso: as forças da ponta a (local) e a carga distribuída local — o diagrama de qualquer combinação
        "pontas": np.round(sol["pontas"][:, :, :6], 3).tolist(),
        "w_local": np.round(sol["w"], 4).tolist(),
        "combinacoes": combinacoes_json(combinacoes(nomes)),
        # por barra, compacto: [N mín, N máx, V, M, σ, posição do σ máx (0–1)]
        "por_comb": {c: {"desl_mm": np.round(v["desl_mm"], 1).tolist(),
                         "reacoes": {str(n): np.round(r, 2).tolist() for n, r in v["reacoes"].items()},
                         "barras": [[b["N"][0], b["N"][1], b["V"], b["M"], b["sigma"], b["x"]] for b in v["barras"]]}
                     for c, v in res["por_comb"].items()},
        "envoltoria": res["envoltoria"],
        "reacoes_casos": {str(n): np.round(np.array(r).T, 3).tolist() for n, r in sol["reacoes"].items()},
        "equilibrio": equil,
        "info": info,
        "avisos": avisos,
        "instavel": sol["instavel"],
        "movel": ({k: v for k, v in M["movel"].items() if k != "tesouras"} if M.get("movel") else None),
    }
    return saida


def combinacoes_json(c: Dict[str, dict]) -> Dict[str, dict]:
    return {k: {"tipo": v["tipo"], "fatores": v["fatores"], "descricao": v["descricao"]} for k, v in c.items()}
