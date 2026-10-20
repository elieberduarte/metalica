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
import re
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
    # a tesoura chumbada no pilar de concreto (pré-moldado, fora da análise): os nós dela encostados na face do pilar são
    # os apoios — engastada (as chapas chumbadas) ou articulada. Docas, 08/10: a marquise em balanço, os dois banzos
    # chumbados no pilar e nenhum outro apoio
    "chumbada_no_pilar": "engastada",
    # as terças (calibração com o Tekla, 08/10): a peça rotulada onde termina sobre a tesoura (o clip aparafusado; a terça
    # contínua sobre várias tesouras continua contínua por dentro) — antes ficava engastada, com wL²/24 no meio do vão em
    # vez de wL²/8 e momento passando para o banzo
    "terca_rotulada": True,
    # telha, sobrecarga e vento chegam às terças (carga distribuída na faixa de influência de cada uma) e às tesouras pelas
    # reações delas — antes iam direto aos nós do banzo e a terça só via o peso próprio. Sem terças, como antes
    "cargas_pelas_tercas": True,
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
    # o modelo do vento (M4, 14/10): auto | isolada (cobertura isolada, 7.2, Tabelas 24 e 25) | fechado (galpão fechado:
    # Tabelas 6 e 7 + C_pi). No auto o fechado liga sozinho quando o modelo tem longarinas (ou terças de parede) ou telha de
    # parede descendo até a metade de baixo do pé-direito (decisão do usuário); o adotado e o motivo ficam em info.vento
    "modelo_vento": "auto",
    "vento_nas_barras": True,           # o arrasto nos pilares, vigas e X entre pilares (8.1, Tabelas 26 a 28)
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
    # giro do pilar só na análise (graus somados ao giro da peça), pela base em planta: {"x,y" (mm): 90} — para testar a
    # inércia no outro sentido; o definitivo é girar o pilar na planta
    "giro_pilares": {},
    # aço
    "fy_mpa": 345.0,                    # para o mapa de tensões (ASTM A572 Gr.50; o tubo leve pode ser outro)
    "aco_tubos": "",                    # o aço dos tubos (TQ, TR, TC) na verificação; vazio = o aço de cada peça no modelo
    # etapa 4 (07/10): a 2ª ordem da NBR 8800:2024 (4.10.7) nas ELU e a verificação de cada peça pela norma
    "segunda_ordem": True,
    # o tirante (barra redonda) só trabalha à tração: na 2ª ordem a diagonal comprimida do X sai da rigidez (15/10, a
    # Kaefer do engenheiro: os X de Ø8 comprimidos entravam com o P-Δ e a iteração divergia)
    "tirantes_so_tracao": True,
    # etapa 5 (07/10): as bases pela NBR 8800:2024, 6.7, com as reações concomitantes
    "base_fck_mpa": 25.0,               # o concreto do bloco de fundação
    "base_aco_placa": "ASTM A36",       # a placa de base (os chumbadores da 6.7 são ASTM A36)
    # a análise global do pré-moldado (09/10, nucleo3d/analise_premoldado.py)
    "modelo_analise": "auto",           # auto (pelo modelo) | aco | premoldado
    "piso_revestimento": 1.0,           # kN/m² nas lajes
    "piso_sobrecarga": 3.0,             # kN/m² nas lajes (NBR 6120, a confirmar com o uso)
    "base_coluna_aco": "rotulada",      # a base das colunas de aço chumbadas no bloco
    # a permeabilidade do prédio fechado (C_pi, NBR 6123:2023, 6.3.2.1): o pré-moldado e o galpão fechado do aço. O padrão
    # é a hipótese da norma para o caso corrente — duas faces opostas igualmente permeáveis (+0,2 e −0,3)
    "aberturas": "duas faces opostas",
    # o fechamento lateral que não desce até o chão (15/10, a Kaefer do engenheiro: lona nos 4 lados até 2,00 m acima do
    # piso, a faixa de baixo aberta para o vento passar): a cota (m, acima das bases) onde a parede começa
    "parede_z_inferior": 0.0,
    # a viga no alinhamento da parede (a do topo dos pilares) recebe a faixa de cima da parede como uma fiada de
    # longarina; sem isso a faixa toda vai para as longarinas abaixo dela
    "parede_nas_vigas": False,
}

ALMA = ("montante", "diagonal")


# ------------------------------------------------------------------ geometria e seção

def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


_SECOES: Dict[str, Optional[dict]] = {}       # as seções do catálogo já lidas (entre um cálculo e outro)


def _secao(nome: str, duplo: bool, cache: dict) -> Optional[dict]:
    """A, Iz (forte), Iy (fraca), J em m; Wz, Wy em m³; kg/m — pelo catálogo"""
    if nome not in cache and nome in _SECOES:
        cache[nome] = _SECOES[nome]
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
                 "kg_m": p.massa or A * 7850.0, "tipo": getattr(p, "tipo", ""),
                 "redonda": (getattr(p, "dados", None) or {}).get("tipo") == "redonda" and getattr(p, "tipo", "") == "barra"}
        cache[nome] = _SECOES[nome] = s
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


def _folga_no_topo(nos: np.ndarray, barras: List[dict]) -> None:
    """O topo em furo oblongo vertical (o pilar de oitão com o topo solto, galpão gerado 20/10): o último
    trecho da peça, até o topo, fica sem rigidez axial — passa força horizontal (o vento do oitão) e não
    passa peso da cobertura."""
    topo: Dict[str, int] = {}
    for i, br in enumerate(barras):
        if not br.get("topo_oblongo") or not br["ids"]:
            continue
        z = max(float(nos[br["a"]][2]), float(nos[br["b"]][2]))
        j = topo.get(br["ids"][0])
        if j is None or z > max(float(nos[barras[j]["a"]][2]), float(nos[barras[j]["b"]][2])):
            topo[br["ids"][0]] = i
    for i in topo.values():
        barras[i]["sec"] = dict(barras[i]["sec"], A=barras[i]["sec"]["A"] * 1e-4)


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


# ------------------------------------------------------------------ o modelo

#: A face do pilar de concreto a até esta distância (m) do nó da tesoura: o nó está chumbado nele (o eixo da ponta em U
#: fica a meia aba da face; a chapa e o chumbador, mais uns centímetros).
CHUMBADA_ATE = 0.10


def _pilares_de_concreto(ents) -> Dict[str, dict]:
    """{id: {marca, caixa (m: x0, x1, y0, y1, z0, z1)}} dos pilares de concreto do modelo (os da planta de lançamento,
    pré-moldados): sólidos, fora da análise de aço — só a caixa deles, para achar as tesouras chumbadas"""
    out: Dict[str, dict] = {}
    for e in ents.values():
        at = getattr(e, "atributos", None) or {}
        if at.get("elemento") != "pilar" or not (at.get("pre_moldado") or str(getattr(e, "material", "")).lower().startswith("concreto")):
            continue
        vs = getattr(e, "vertices", None) or []
        if len(vs) < 4:
            continue
        xs, ys, zs = [v[0] / 1000.0 for v in vs], [v[1] / 1000.0 for v in vs], [v[2] / 1000.0 for v in vs]
        out[e.id] = {"marca": at.get("marca") or at.get("peca") or e.id,
                     "caixa": (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))}
    return out


def _chumbadas_no_concreto(nos: np.ndarray, barras: List[dict], concreto: Dict[str, dict]) -> Dict[int, str]:
    """{nó: marca do pilar}: os nós das tesouras encostados na face de um pilar de concreto (a marquise chumbada no
    pilar, Docas 08/10) — dentro da altura dele e a até CHUMBADA_ATE da face, por fora. A normal da face (para fora do
    pilar, para o lado da tesoura) fica em _NORMAL_CHUMBADA[nó], para a ancoragem"""
    if not concreto:
        return {}
    nos_trel = sorted({n for br in barras if br["elemento"] == "trelica" for n in (br["a"], br["b"])})
    out: Dict[int, str] = {}
    for n in nos_trel:
        x, y, z = (float(c) for c in nos[n])
        for pc in concreto.values():
            x0, x1, y0, y1, z0, z1 = pc["caixa"]
            if not (z0 - 0.05 <= z <= z1 + 0.05):
                continue
            dx = max(x0 - x, 0.0, x - x1)
            dy = max(y0 - y, 0.0, y - y1)
            if math.hypot(dx, dy) <= CHUMBADA_ATE:
                out[n] = pc["marca"]
                # a direção da ancoragem: a da tesoura saindo do pilar (o banzo que chega no nó, na horizontal) — a face pela
                # posição do nó errava quando a tesoura passa um pouco da largura do pilar lançado (a da junta do Docas)
                dirs = []
                for br in barras:
                    if br["elemento"] == "trelica" and br["papel"] == "banzo" and n in (br["a"], br["b"]):
                        o = nos[br["b"] if br["a"] == n else br["a"]] - nos[n]
                        dirs.append(o[:2])           # pelo comprimento em planta: a ponta em pé (quase vertical) não conta
                if dirs:
                    d_ = np.mean(dirs, axis=0)
                    sx, sy = (float(d_[0]), float(d_[1])) if np.linalg.norm(d_) > 1e-6 else (0.0, 0.0)
                    nn = math.hypot(sx, sy) or 1.0
                    sx, sy = sx / nn, sy / nn
                else:
                    cx_, cy_ = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                    sx, sy = x - cx_, y - cy_
                    nn = math.hypot(sx, sy) or 1.0
                    sx, sy = sx / nn, sy / nn
                _NORMAL_CHUMBADA[n] = (sx, sy, 0.0)
                break
    return out


_NORMAL_CHUMBADA: Dict[int, Tuple[float, float, float]] = {}

#: Bases na mesma cota: até esta diferença (m) os pés dos pilares são da mesma cota (o agrupamento das bases e o aviso de
#: cotas diferentes). É tolerância de modelagem (o pé desenhado uns milímetros acima ou abaixo), não critério de norma.
COTA_BASE_TOL = 0.05


def _pes_dos_pilares(nos: np.ndarray, barras: List[dict], no_barras: Dict[int, List[int]]) -> List[int]:
    """os nós de apoio no pé dos pilares (M3, 14/10/2026). Antes só valia o pé na cota do pé mais baixo de todos (±5 cm): o
    pilar com o pé 30 cm acima ficava pendurado na estrutura, sem apoio e sem aviso. Agora:

    * o nó de baixo de cada trecho de pilar na cota mais baixa dos pilares é base (como antes — os modelos com todos os
      pés na mesma cota não mudam);
    * acima dela, o nó de baixo do pilar é base quando nenhuma outra barra o sustenta: nenhuma chega nele vindo de baixo
      ou de lado (viga, outro pilar, diagonal que desce). A barra que só sobe dali (o X de contraventamento que nasce no
      pé) não sustenta. O pilarete apoiado numa viga (o nó tem viga) e o trecho de cima de um pilar partido não viram
      base."""
    zp = [min(nos[br["a"]][2], nos[br["b"]][2]) for br in barras if br["papel"] == "pilar"]
    if not zp:
        return []
    z0 = min(zp)
    pes: List[int] = []
    for i, br in enumerate(barras):
        if br["papel"] != "pilar":
            continue
        n = br["a"] if nos[br["a"]][2] <= nos[br["b"]][2] else br["b"]
        if n in pes:
            continue
        zn = float(nos[n][2])
        if abs(zn - z0) <= COTA_BASE_TOL:
            pes.append(n)
            continue
        sustenta = False
        for j in no_barras.get(n, ()):
            if j == i:
                continue
            o = barras[j]
            outro = o["b"] if o["a"] == n else o["a"]
            if float(nos[outro][2]) <= zn + COTA_BASE_TOL:          # chega de baixo ou de lado
                sustenta = True
                break
        if not sustenta:
            pes.append(n)
    return pes


def _cotas_das_bases(nos: np.ndarray, pes: Sequence[int]) -> List[Tuple[float, int]]:
    """[(cota m, nº de pés)] dos pés agrupados pela cota (COTA_BASE_TOL), da mais baixa para a mais alta"""
    grupos: List[List[float]] = []
    for z in sorted(float(nos[n][2]) for n in pes):
        if grupos and z - grupos[-1][0] <= COTA_BASE_TOL:
            grupos[-1].append(z)
        else:
            grupos.append([z])
    return [(round(sum(g) / len(g), 3), len(g)) for g in grupos]



# ------------------------------------------------------------------ o fechamento lateral (M4, 14/10)

#: Telha pelo nome do perfil, do elemento, da camada ou do material (o mesmo reconhecimento do detalhamento,
#: saida/detalhamento._eh_telha, mais o fechamento gerado pelo galpão e o isopainel).
_TELHA_RX = re.compile(r"TELHA|TP\s*\d{2}|TRAPEZ|ONDUL|ISOPAINEL|ISOTELHA|FECHAMENTO", re.I)
#: A telha é "de parede" quando o plano dela é vertical: a normal (a direção de menor espalhamento dos vértices) quase
#: horizontal — |n_z| abaixo de sen 17,5° (a telha a menos de 17,5° da vertical). Abaixo disso é água de telhado.
TELHA_PAREDE_NZ = 0.3
#: …e quando ela desce até a metade de baixo do pé-direito (da cota das bases ao beiral): a testeira e a dobra do beiral
#: (a multidobra do Posto CB, 1,7 m de telha vertical a 6 m do chão) são verticais mas não fecham a parede.
TELHA_PAREDE_ALTURA = 0.5


def _e_telha(e) -> bool:
    at = getattr(e, "atributos", None) or {}
    if at.get("calha_lancada") or at.get("cumeeira_lancada") or at.get("furo") or at.get("parafuso"):
        return False
    if at.get("telha_lancada"):
        return True
    m = at.get("marcas") or {}
    txt = " ".join(str(x) for x in (m.get("perfil"), getattr(e, "nome", ""), at.get("elemento"), getattr(e, "camada", ""),
                                     getattr(e, "material", "")) if x)
    return bool(_TELHA_RX.search(txt))


def _fechamento_do_modelo(doc, nos: np.ndarray, barras: List[dict], no_barras: Dict[int, List[int]],
                          pes: Sequence[int]) -> dict:
    """o que o modelo tem de fechamento lateral, para o modo do vento (M4, decisão do usuário de 14/10: "galpão fechado
    liga sozinho quando o modelo tem longarinas ou telha de parede"):

    * longarinas: as barras com o papel "longarina" (na peça ou em atributos.papel) e as terças de parede — a terça
      presa só em pilares, na lateral deles (o pilar continua acima do nó; nenhum banzo, viga ou alma de treliça nos
      nós dela). A terça no topo do pilar é do telhado;
    * telhas de parede: as telhas de plano vertical (TELHA_PAREDE_NZ) que descem até a metade de baixo do pé-direito
      (TELHA_PAREDE_ALTURA); as verticais mais altas (testeira, beiral dobrado) ficam contadas à parte.

    {longarinas, tercas_parede, telhas_parede, telhas_altas, barras_longarina (índices das barras de análise), z_base,
    z_beiral}"""
    zp = [float(nos[n][2]) for n in pes]
    z_base = min(zp) if zp else (min((min(nos[br["a"]][2], nos[br["b"]][2]) for br in barras if br["papel"] == "pilar"),
                                     default=float(nos[:, 2].min()) if len(nos) else 0.0))
    sup = [float(nos[br[k]][2]) for br in barras if br.get("papel_trelica") == "banzo_sup" for k in ("a", "b")]
    topo_pil = [max(nos[br["a"]][2], nos[br["b"]][2]) for br in barras if br["papel"] == "pilar"]
    z_beiral = min(sup) if sup else (float(np.median(topo_pil)) if topo_pil else z_base)
    # longarinas
    ids_long = {e.id for e in getattr(doc, "barras", []) if (getattr(e, "papel", "") == "longarina" or
                                                               (getattr(e, "atributos", None) or {}).get("papel") == "longarina")}
    idx_long = [i for i, br in enumerate(barras) if not br.get("hipotese") and
                (br["papel"] == "longarina" or (br["ids"] and br["ids"][0] in ids_long))]
    # terças de parede: a peça só presa em pilares
    trel = {"banzo", "viga", "montante", "diagonal", "apoio_terca"}
    por_peca: Dict[str, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        if br["papel"] == "terça" and not br.get("hipotese") and br["ids"]:
            por_peca[br["ids"][0]].append(i)
    tercas_parede = 0
    for pid, bs in por_peca.items():
        meus = set(bs)
        nos_t = {barras[i][k] for i in bs for k in ("a", "b")}
        papeis = {barras[j]["papel"] for n in nos_t for j in no_barras.get(n, ()) if j not in meus}
        na_lateral = any(barras[j]["papel"] == "pilar" and
                         max(nos[barras[j]["a"]][2], nos[barras[j]["b"]][2]) > nos[n][2] + COTA_BASE_TOL
                         for n in nos_t for j in no_barras.get(n, ()) if j not in meus)
        if na_lateral and not papeis & trel:
            tercas_parede += 1
            idx_long += bs
    # telhas de parede
    lim = z_base + TELHA_PAREDE_ALTURA * max(z_beiral - z_base, 0.0)
    parede = altas = 0
    for e in getattr(doc, "solidos", []):
        vs = getattr(e, "vertices", None) or []
        if len(vs) < 4 or not _e_telha(e):
            continue
        v = np.asarray(vs, float) / 1000.0
        c = v - v.mean(axis=0)
        try:
            _w, V = np.linalg.eigh(c.T @ c)
        except np.linalg.LinAlgError:
            continue
        if abs(float(V[2, 0])) >= TELHA_PAREDE_NZ:
            continue                                       # água de telhado
        if float(v[:, 2].min()) <= lim + 1e-6:
            parede += 1
        else:
            altas += 1
    n_long = len(ids_long | {barras[i]["ids"][0] for i in idx_long if barras[i]["papel"] == "longarina" and barras[i]["ids"]})
    return {"longarinas": n_long, "tercas_parede": tercas_parede, "telhas_parede": parede, "telhas_altas": altas,
            "barras_longarina": sorted(set(idx_long)), "z_base": round(float(z_base), 4), "z_beiral": round(float(z_beiral), 4)}


def _furos_das_pecas(doc) -> Dict[str, dict]:
    """os furos marcados no 3D em cada barra (N1, 14/10 — para o C_t da tração pela ligação): {id da barra: {"L": m,
    "furos": [{x (m ao longo da barra, do início), d (mm, o parafuso), parafuso (id ou None), ponto (m), eixo, d_furo
    (mm)}]}}. Os marcadores são os da ferramenta Furo e os que o Parafuso abre (atributos.furo com "peca" = a barra); o
    diâmetro do parafuso vem do parafuso ligado ao furo, senão do furo-padrão (fabrica.parafuso_do_furo)"""
    out: Dict[str, dict] = {}
    ents = getattr(doc, "entidades", {}) or {}
    for e in ents.values():
        fu = (getattr(e, "atributos", None) or {}).get("furo")
        if not isinstance(fu, dict) or not fu.get("peca"):
            continue
        b = ents.get(fu["peca"])
        if b is None or not hasattr(b, "inicio") or not hasattr(b, "fim"):
            continue
        try:
            p0, p1 = np.array(b.inicio, float), np.array(b.fim, float)
            pt, eixo = np.array(fu["ponto"], float), np.array(fu.get("eixo") or (0.0, 0.0, 1.0), float)
            d_furo = float(fu.get("d") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        L = float(np.linalg.norm(p1 - p0))
        if L < 1e-6 or d_furo <= 0:
            continue
        d = None
        par = ents.get(fu.get("parafuso")) if fu.get("parafuso") else None
        reg = (getattr(par, "atributos", None) or {}).get("parafuso") if par is not None else None
        if isinstance(reg, dict) and reg.get("d"):
            d = float(reg["d"])
        if d is None:
            try:
                import fabrica
                d = float(fabrica.parafuso_do_furo(d_furo))
            except Exception:                                    # noqa: BLE001 — sem a tabela: o furo-padrão d + 1,5
                d = d_furo - 1.5
        reg_b = out.setdefault(b.id, {"L": L / 1000.0, "furos": []})
        reg_b["furos"].append({"x": float((pt - p0) @ (p1 - p0)) / L / 1000.0, "d": d, "parafuso": fu.get("parafuso"),
                               "ponto": (pt / 1000.0).tolist(), "eixo": _unit(eixo).tolist(), "d_furo": d_furo})
    return out

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
    concreto = _pilares_de_concreto(ents)
    for br in an["barras"]:
        ent = ents.get(br["ids"][0]) if br.get("ids") else None
        if ent is not None and getattr(ent, "id", None) in concreto:
            continue                                   # o pilar de concreto não é barra de aço: entra como apoio da tesoura
        a, b = nos[br["a"]], nos[br["b"]]
        L = float(np.linalg.norm(b - a))
        if L < 1e-4:
            continue
        at = (getattr(ent, "atributos", None) or {}) if ent is not None else {}
        # a seção composta que trabalha como uma só (os 2 U soldados boca com boca da Kaefer = tubo 127×100×2, 15/10):
        # a peça diz o perfil de cálculo; o modelado continua no 3D e nas listas
        perfil, duplo = (str(at["perfil_calculo"]), False) if at.get("perfil_calculo") else (br.get("perfil") or "", bool(br.get("duplo")))
        sec = _secao(perfil, duplo, cache)
        if sec is None:
            sem_secao[perfil or "?"] += 1
            continue
        barras.append({
            "a": int(br["a"]), "b": int(br["b"]), "L": L, "papel": br.get("papel") or "barra",
            "papel_trelica": at.get("papel_trelica"),
            # a tesoura do galpão gerado (de_projeto) guarda o nome do elemento do cálculo ("Banzo superior da tesoura",
            # que o editor pinta) e marca a treliça pelo papel_trelica
            "elemento": "trelica" if at.get("papel_trelica") in ("banzo_sup", "banzo_inf", "diagonal", "montante") and
            at.get("origem_2d") else at.get("elemento"), "grupo": at.get("origem_2d") or br.get("grupo"),
            "viga_cobertura": bool(at.get("viga_de_cobertura")), "misula": at.get("misula"),
            "topo_oblongo": bool(at.get("topo_oblongo")),
            "marca": at.get("marca") or at.get("peca"), "perfil": perfil, "ids": list(br.get("ids") or []),
            **({"perfil_modelo": br.get("perfil")} if at.get("perfil_calculo") else {}),
            "aco": (getattr(ent, "aco", "") or "") if ent is not None else "",
            "sec": sec, "duplo": duplo, "rot": float(getattr(ent, "rotacao", 0.0) or 0.0) if ent is not None else 0.0,
            "R": _eixos(a, b, float(getattr(ent, "rotacao", 0.0) or 0.0) if ent is not None else 0.0),
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
    _folga_no_topo(nos, barras)
    _girar_pilares(nos, barras, P, avisos)
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
    # o nó só de duas barras de alma (nem banzo, nem outra barra): a dobra de uma peça quebrada no meio da tesoura — a
    # cantoneira soldada contínua. Rotulada nas duas, o joelho girava solto (mecanismo; Docas, 08/10: a barra que
    # atravessa a T1 em três trechos, com duas dobras fora dos banzos)
    dobra = {n for n, bs in no_barras.items() if len(bs) == 2 and all(barras[i]["papel"] in ALMA for i in bs)}
    # rótulas
    for br in barras:
        for ponta, no in (("a", br["a"]), ("b", br["b"])):
            if br["ids"] and trechos_no[(br["ids"][0], no)] >= 2:
                continue                                      # meio da peça: contínua
            if no in dobra:
                continue                                      # a dobra da alma quebrada: contínua
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
            elif P.get("terca_rotulada", True) and br["papel"] == "terça" and not br.get("hipotese"):
                soltar = True
            elif P["viga_pilar"] == "rotulada" and br["papel"] == "viga" and "pilar" in papeis_no[no]:
                soltar = True
            if soltar:
                base = 0 if ponta == "a" else 6
                br["soltos"] += [base + 4, base + 5]          # ry, rz da ponta (a torção fica)
    # apoios: o pé dos pilares — na cota mais baixa e também acima dela, quando nada sustenta o pé (M3, 14/10)
    pes = _pes_dos_pilares(nos, barras, no_barras)
    cotas = _cotas_das_bases(nos, pes)
    if len(cotas) > 1:
        avisos.append("bases dos pilares em %d cotas diferentes: %s — cada pilar sem outra barra que o sustente no pé (viga, "
                      "outro pilar, diagonal) é apoiado na cota dele; confira com o projeto das fundações" % (
                          len(cotas), "; ".join("%s m (%d pilar%s)" % (("%+.2f" % z).replace(".", ","), k, "es" if k > 1 else "")
                                                for z, k in cotas)))
    chumbadas = _chumbadas_no_concreto(nos, barras, concreto)
    if not pes and not chumbadas:
        # sem pilar: os nós mais baixos
        pes = [int(i) for i in np.where(np.abs(nos[:, 2] - nos[:, 2].min()) < 0.05)[0]]
        avisos.append("o modelo não tem pilares: os apoios foram os nós mais baixos")
    apoios = []
    for n in pes:
        chave = "%d,%d" % (round(nos[n][0] * 1000), round(nos[n][1] * 1000))
        tipo = (P.get("bases") or {}).get(chave) or P["base"]
        apoios.append({"no": int(n), "tipo": tipo, "chave": chave})
    for n, marca in chumbadas.items():
        if n in pes:
            continue
        chave = "%d,%d,%d" % (round(nos[n][0] * 1000), round(nos[n][1] * 1000), round(nos[n][2] * 1000))
        apoios.append({"no": int(n), "tipo": P.get("chumbada_no_pilar") or "engastada", "chave": chave, "chumbada": marca,
                       "normal": list(_NORMAL_CHUMBADA.get(n, (0.0, 0.0, 0.0))), "z": round(float(nos[n][2]), 3)})
    if chumbadas:
        avisos.append("%d nó(s) de tesoura chumbados em %d pilar(es) de concreto (%s): são os apoios dela" % (
            len(chumbadas), len(set(chumbadas.values())), P.get("chumbada_no_pilar") or "engastada"))
    return {"nos": nos, "barras": barras, "apoios": apoios, "avisos": avisos, "par": P, "resumo_esqueleto": an["resumo"],
            "movel": movel, "fechamento": _fechamento_do_modelo(doc, nos, barras, no_barras, pes),
            "furos_por_peca": _furos_das_pecas(doc)}


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


def chave_do_pilar(nos: np.ndarray, br: dict) -> str:
    """o pilar pela base em planta (mm): a mesma chave de todos os trechos dele e das bases da análise"""
    n = br["a"] if nos[br["a"]][2] <= nos[br["b"]][2] else br["b"]
    return "%d,%d" % (round(nos[n][0] * 1000), round(nos[n][1] * 1000))


def _girar_pilares(nos: np.ndarray, barras: List[dict], P: dict, avisos: List[str]) -> None:
    """o giro de teste dos pilares (só na análise): a seção gira em torno do eixo do pilar"""
    giros = P.get("giro_pilares") or {}
    if not giros:
        return
    feitos = collections.Counter()
    for br in barras:
        if br["papel"] != "pilar":
            continue
        k = chave_do_pilar(nos, br)
        g = float(giros.get(k) or 0.0)
        if g:
            br["giro"] = g
            br["R"] = _eixos(nos[br["a"]], nos[br["b"]], br.get("rot", 0.0) + g)
            feitos[k] += 1
    if feitos:
        avisos.append("pilar girado só na análise (o modelo 3D não muda): %s" % ", ".join(
            "%s (%+.0f°)" % (k, float(giros[k])) for k in sorted(feitos)))


def _secao_desenho(nome: str, cache: dict) -> Optional[list]:
    """o contorno da seção (mm, x = largura da mesa, y = altura), para desenhar o pilar na base"""
    if nome not in cache:
        try:
            from nucleo3d import geometria
            from nucleo3d.calculo_ifc import _perfil_de
            p = _perfil_de(nome, "", {}, {})
            cache[nome] = [[round(x, 1), round(y, 1)] for x, y in geometria.secao(p)] if p is not None else None
        except Exception:                                    # noqa: BLE001 — sem contorno: o desenho só não aparece
            cache[nome] = None
    return cache[nome]


def grupos_de_perfis(r: dict, outras: Sequence[dict] = (), limite: int = 20) -> List[dict]:
    """os grupos (função + perfil original) do resultado, com as alternativas do catálogo (mesma família) e, em cada uma,
    o uso ESTIMADO com os esforços da combinação que governa cada barra do grupo (N, Mz, My, nas situações todas):

    * σ elástica = |N|/A + |Mz|/Wz + |My|/Wy (o mesmo mapa da tela), em MPa;
    * uso = a interação da norma com as MESMAS resistências da verificação (nucleo3d/verificacao_pecas.py): a peça de
      cada barra dá os comprimentos de flambagem pelos travamentos (Lx, Ly; Lb = Ly para a FLT) e o aço; compressão com
      χ e Q, flexão com FLA, FLM e FLT, U e Ue pela NBR 14762 — tira da lista o perfil que passa na tensão e flamba ou
      tomba muito antes.

    É estimativa: com o perfil novo os esforços se redistribuem (o recalcular confirma) e o B1 do P-δ não entra.
    Cada alternativa: [nome, kg/m, σ estimada MPa, uso estimado (1 = 100%)]; a lista: as mais pesadas das que não passam
    logo abaixo da mais leve que passa (a referência) e as que passam, da mais leve para cima."""
    from nucleo import catalogo, materiais as mat
    from nucleo3d import verificacao_pecas as VP
    grupos: Dict[str, dict] = {}
    for res in (r, *outras):
        ver = res.get("verificacao") or {}
        pecas, pk = ver.get("pecas") or [], ver.get("peca_da_barra") or []
        for i, b in enumerate(res["barras"]):
            if b.get("hipotese") or b.get("concreto"):
                continue                                  # o concreto do pré-moldado não tem perfil de aço para trocar
            k = chave_do_grupo(b)
            g = grupos.setdefault(k, {"chave": k, "funcao": k.split("|", 1)[0], "perfil": k.split("|", 1)[1], "atual": b["perfil"],
                                      "barras": 0, "duplo": bool(b.get("duplo")), "_esf": [], "_aco": None})
            if res is r:
                g["barras"] += 1
            N, Mz, My = res["envoltoria"][i].get("esf") or [0.0, 0.0, 0.0]
            pc = pecas[pk[i]] if i < len(pk) and 0 <= pk[i] < len(pecas) else {}
            Lx, Ly = float(pc.get("Lx") or b["L"]), float(pc.get("Ly") or b["L"])
            g["_esf"].append((float(N), abs(float(Mz)), abs(float(My)), Lx, Ly, float(pc.get("L") or b["L"])))
            g["_aco"] = g["_aco"] or pc.get("aco")
        # e o ponto que governa a verificação de cada peça (a combinação da flambagem nem sempre é a da maior tensão)
        for pc in pecas:
            e = pc.get("esf")
            if not e or pc.get("hipotese") or pc.get("b0") is None or pc["b0"] >= len(res["barras"]):
                continue
            g = grupos.get(chave_do_grupo(res["barras"][pc["b0"]]))
            if g is not None:
                g["_esf"].append((float(e["N"]), abs(float(e["Mz"])), abs(float(e["My"])), float(pc["Lx"]), float(pc["Ly"]), float(pc["L"])))
    secoes: Dict[str, Optional[dict]] = {}

    def secao(nome, duplo):
        return _secao(nome, duplo, secoes)

    def criticas(g):
        """as barras que podem governar: maior σ, maior compressão e maior compressão × L² (a flambagem), sem repetir os
        mesmos comprimentos e esforços"""
        s0 = secao(g["atual"], g["duplo"])
        E = g["_esf"]
        if s0 is None:
            return E[:12]
        sig = lambda e: abs(e[0]) / s0["A"] + e[1] / s0["Wz"] + e[2] / s0["Wy"]
        esc = set()
        for f in (sig, lambda e: max(0.0, -e[0]), lambda e: max(0.0, -e[0]) * max(e[3], e[4]) ** 2,
                  lambda e: e[1] * e[4]):
            esc.update(sorted(range(len(E)), key=lambda j: -f(E[j]))[:4])
        return [E[j] for j in esc]

    def uso_de(nome, aco, g, crit):
        """a interação da norma (a mesma da verificação, sem o B1) com as resistências da peça de cada barra"""
        n = 2.0 if g["duplo"] else 1.0
        uso = 0.0
        for N, Mz, My, Lx, Ly, L in crit:
            rs = VP.resistencias(nome, aco, round(Lx * 20) / 20, round(Ly * 20) / 20, L, VP.CACHE)
            if rs.get("erro"):
                return None
            n_rd = n * float(rs["Nc"] if N < 0 and not rs["redonda"] else rs["Nt"])
            rn = abs(N) / n_rd if n_rd > 0 else (0.0 if abs(N) < 1e-6 else 99.0)
            if rs["redonda"]:
                uso = max(uso, rn)
                continue
            rm = (Mz / (n * rs["Mz"]) if rs.get("Mz") else 0.0) + (My / (n * rs["My"]) if rs.get("My") else 0.0)
            uso = max(uso, rn + rm if rs["linear"] else (rn + 8.0 / 9.0 * rm if rn >= 0.2 else rn / 2.0 + rm))
        return uso

    def sigma_de(nome, g):
        sec = secao(nome, g["duplo"])
        if sec is None:
            return None
        E = g["_arr"]
        return float(np.max(np.abs(E[:, 0]) / sec["A"] + E[:, 1] / sec["Wz"] + E[:, 2] / sec["Wy"])) / 1000.0
    for g in grupos.values():
        g["_arr"] = np.array(g["_esf"], float).reshape(-1, 6)
        aco = g.pop("_aco") or mat.ACO_PADRAO
        fy = mat.aco(aco).fy * 10.0 if aco in mat.ACOS else 345.0
        crit = criticas(g)
        try:
            alts = catalogo.alternativas(g["perfil"], modo="todos", limite=5000)
        except Exception:                                       # noqa: BLE001 — fora do catálogo: só o campo livre
            alts = []
        cand = []
        for a in alts:
            if 0 < float(a.get("espessura") or 99.0) < ESPESSURA_MIN_SUGESTAO:
                continue                                         # parede fina demais para solda de treliça (prática)
            s = sigma_de(a["nome"], g)
            if s is not None:
                cand.append([a["nome"], round(float(a.get("massa") or 0.0), 2), s])
        # o perfil de hoje também concorre (o catálogo não o devolve como alternativa dele mesmo): se ele passa e é o mais
        # leve, a sugestão é ficar com ele
        s_at, sec_at = sigma_de(g["atual"], g), secao(g["atual"], False)
        if s_at is not None and sec_at is not None and all(a[0] != g["atual"] for a in cand):
            cand.append([g["atual"], round(float(sec_at["kg_m"]), 2), s_at])
        cand.sort(key=lambda a: (a[1], a[2]))
        passam, nao = [], []
        for a in cand:
            if a[2] > 1.5 * fy:
                # longe demais: a resistência plástica (Z·fy) e o ramo N/2 da interação deixam passar até ~1,3·fy de σ
                # elástica, não 1,5 — nem precisa da flambagem
                nao.append(a + [None])
                continue
            uso = uso_de(a[0], aco, g, crit)
            if uso is None:
                continue
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
        s0, u0 = sigma_de(g["atual"], g), uso_de(g["atual"], aco, g, crit)
        g["estimativa_atual"] = [round(s0, 1), round(u0, 3)] if s0 is not None and u0 is not None else None
        g["mais_leve_que_passa"] = passam[0][0] if passam else None
        g["aco"] = aco
        del g["_esf"], g["_arr"]
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
                                         "ids": [], "sec": sec_s, "R": _eixos(A, B, 0.0), "soltos": [4, 5, 10, 11],
                                         "aco": barras[molde[0]].get("aco") or ""})
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
                "hipotese": True, "aco": "ZAR-345" if papel == "terça" else "ASTM A36"}
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
    # e a viga de alma cheia que recebe a cobertura (o pórtico do galpão gerado, 20/10)
    sup = [i for i, br in enumerate(barras) if br.get("papel_trelica") == "banzo_sup" or br.get("viga_cobertura")]
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
        planos[g] = {"u": u, "n": n, "off": float(c @ n), "c": c, "s0": float((pts[:, :2] @ u).min()), "s1": float((pts[:, :2] @ u).max()),
                     "z0": float(pts[:, 2].min()), "z1": float(pts[:, 2].max())}
    # as coberturas independentes: as treliças cujos banzos de cima se sobrepõem em altura são da mesma cobertura (o Docas,
    # 08/10: duas marquises em níveis diferentes, 2 m uma da outra, que se cruzam na junta)
    gs = list(planos)
    grupo = {g: i for i, g in enumerate(gs)}

    def raiz(g):
        while grupo[g] != grupo[gs[grupo[g]]]:
            grupo[g] = grupo[gs[grupo[g]]]
        return grupo[g]
    for i, g in enumerate(gs):
        for h in gs[i + 1:]:
            if min(planos[g]["z1"], planos[h]["z1"]) - max(planos[g]["z0"], planos[h]["z0"]) > -0.05:
                ra, rb = raiz(g), raiz(h)
                for k in gs:
                    if grupo[k] == rb:
                        grupo[k] = ra
    rotulos = {r: k for k, r in enumerate(sorted({raiz(g) for g in gs}))}
    cobertura = {g: rotulos[raiz(g)] for g in gs}
    # largura: meia distância às treliças vizinhas paralelas (que se sobrepõem no vão), da mesma cobertura
    larg = {}
    for g in gs:
        p = planos[g]
        viz = []
        for h in gs:
            if h == g or cobertura[h] != cobertura[g]:
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
    return {"trechos": out, "planos": planos, "larguras": larg, "coberturas": cobertura}


AMOSTRAS_FAIXA = 24        # pontos de integração da faixa de cada terça (inclinação e cp ao longo do telhado)


def _tercas_da_cobertura(M: dict, cob: dict, avisos: List[str]) -> dict:
    """as terças que recebem a cobertura (calibração com o Tekla, 08/10): por cobertura independente, cada terça com a
    faixa de influência — meia distância às terças vizinhas (as que se sobrepõem ao longo da geratriz), até a borda do
    banzo de cima nas da ponta —, a inclinação e a normal do telhado ali. {"por_cobertura": {c: [terça]}, "trechos": set
    dos trechos de banzo que deixam de receber a carga direta}. A cobertura cuja área pelas terças não bate (10 %) com a
    das faixas das tesouras fica como antes, com aviso"""
    nos, barras = M["nos"], M["barras"]
    if not cob:
        return {}
    no_cob: Dict[int, int] = {}
    for br in barras:
        if (br.get("elemento") == "trelica" or br.get("viga_cobertura")) and br["grupo"] in cob["coberturas"]:
            no_cob[br["a"]] = no_cob[br["b"]] = cob["coberturas"][br["grupo"]]
    pecas: Dict[str, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        if br["papel"] == "terça" and not br.get("hipotese"):
            pecas[br["ids"][0] if br["ids"] else "b%d" % i].append(i)
    if not pecas:
        return {}
    por: Dict[int, List[dict]] = collections.defaultdict(list)
    for pid, bs in pecas.items():
        ns = {barras[i][k] for i in bs for k in ("a", "b")}
        cs = [no_cob[n] for n in ns if n in no_cob]
        if not cs:
            continue
        c = collections.Counter(cs).most_common(1)[0][0]
        por[c].append({"barras": bs, "nos": ns})
    saida: Dict[int, List[dict]] = {}
    trechos = set()
    for c, ts in por.items():
        P_ = [p for g, p in cob["planos"].items() if cob["coberturas"][g] == c]
        u = _unit(np.mean([p["u"] for p in P_], axis=0))
        n = np.array([-u[1], u[0]])
        s0, s1 = min(p["s0"] for p in P_), max(p["s1"] for p in P_)
        # a inclinação do telhado sob cada terça é a do trecho de banzo de cima ali (o mesmo do cálculo pelos trechos): pela
        # vizinha, a terça do beiral no pé da ponta inclinada (Docas: 761 mm abaixo, a 0,5 m) dava 57° e o vento virava
        # quase horizontal
        incl_c = []
        for i, (Ls, Lh, w) in cob["trechos"].items():
            if cob["coberturas"].get(barras[i]["grupo"]) != c or Lh < 1e-3:
                continue
            pa, pb = nos[barras[i]["a"]], nos[barras[i]["b"]]
            sa, sb = float(pa[:2] @ u), float(pb[:2] @ u)
            if abs(sb - sa) > 1e-6:
                incl_c.append((min(sa, sb), max(sa, sb), (float(pb[2]) - float(pa[2])) / (sb - sa)))

        def tg_em(s_):
            dentro = [g_ for a_, b_, g_ in incl_c if a_ - 1e-3 <= s_ <= b_ + 1e-3]
            if dentro:
                return float(np.mean(dentro))
            return min(incl_c, key=lambda x: min(abs(s_ - x[0]), abs(s_ - x[1])))[2] if incl_c else 0.0
        for tc in ts:
            pts = np.array([nos[k] for k in tc["nos"]])
            tc.update(s=float(np.mean(pts[:, :2] @ u)), z=float(np.mean(pts[:, 2])), t0=float((pts[:, :2] @ n).min()),
                      t1=float((pts[:, :2] @ n).max()), L=sum(barras[i]["L"] for i in tc["barras"]))
        for tc in ts:
            viz = [o for o in ts if o is not tc and min(o["t1"], tc["t1"]) - max(o["t0"], tc["t0"]) > 0.3]
            mais = [o for o in viz if o["s"] - tc["s"] > 0.05]
            menos = [o for o in viz if tc["s"] - o["s"] > 0.05]
            prox = min(mais, key=lambda o: o["s"]) if mais else None
            ant = max(menos, key=lambda o: o["s"]) if menos else None
            # a faixa da terça, de meio caminho até a vizinha de baixo a meio caminho até a de cima (ou até a borda), integrada
            # ao longo do telhado com a inclinação do banzo de cima em cada ponto — a mesma geometria do cálculo pelos trechos:
            # a terça na quina da ponta inclinada do beiral (Docas) tem parte da faixa a 44° e parte quase plana. As amostras
            # (s, ds × √(1 + tg²) × normal) servem ao vento, que integra o cp ponto a ponto
            s_lo = (tc["s"] + ant["s"]) / 2.0 if ant else min(s0, tc["s"])
            s_hi = (tc["s"] + prox["s"]) / 2.0 if prox else max(s1, tc["s"])
            up = np.array([0.0, 0.0, 1.0])
            amostras = []
            ns_ = AMOSTRAS_FAIXA
            ds = (s_hi - s_lo) / ns_
            for k in range(ns_):
                s_k = s_lo + (k + 0.5) * ds
                tg_ = tg_em(s_k)
                d = _unit(np.array([u[0], u[1], tg_]))
                amostras.append((s_k, ds * math.sqrt(1.0 + tg_ * tg_) * _unit(up - (up @ d) * d), ds * math.sqrt(1.0 + tg_ * tg_)))
            tc["w"] = max(s_hi - s_lo, 0.0)
            tc["w_inclinada"] = sum(a_[2] for a_ in amostras)
            tc["normal_area"] = sum((a_[1] for a_ in amostras), np.zeros(3))
            tc["amostras"] = amostras
            tc["tg"] = tg_em(tc["s"])
        area_t = sum(tc["w"] * tc["L"] for tc in ts)
        tr_c = [i for i, br in enumerate(barras) if i in cob["trechos"] and cob["coberturas"].get(br["grupo"]) == c]
        area_b = sum(cob["trechos"][i][1] * cob["trechos"][i][2] for i in tr_c)
        if area_b <= 0 or abs(area_t - area_b) > 0.10 * area_b:
            avisos.append("cobertura %d: a área pelas terças (%.1f m²) não bate com a das faixas das tesouras (%.1f m²) — a carga "
                          "do telhado ficou nos nós do banzo, como antes" % (c + 1, area_t, area_b))
            continue
        saida[c] = ts
        trechos.update(tr_c)
    return {"por_cobertura": saida, "trechos": trechos}


# NBR 6123:2023, 8.1 — o vento nas barras expostas abaixo da cobertura (pilares, vigas, contraventamento entre pilares).
# A Tabela 25 só cobre a cobertura; sem isto o pilar recebia o vento só pelo que a cobertura passava a ele (07/10, conversa
# com o engenheiro: o pilar circular da Kaefer saía quase sem momento)
K_ELL = (2, 5, 10, 20, 40, 50, 100)                          # Tabela 28: ℓ/c (ou ℓ/d); acima de 100, K = 1,0 (∞)
K_TABELA = {"subcritico": (0.58, 0.62, 0.68, 0.74, 0.82, 0.87, 0.98),
            "acima": (0.80, 0.80, 0.82, 0.90, 0.98, 0.99, 1.0),
            "planas": (0.62, 0.66, 0.69, 0.81, 0.87, 0.90, 0.95)}
CF_FACES_PLANAS = 2.0      # Tabela 26: perfis I/H, U, cantoneiras e tubos retangulares ficam entre 1,6 e 2,1 (pela dimensão c);
                           # 2,0 sobre a largura projetada cobre o perfil I nos dois sentidos (1,6 e 1,9) e o tubo quadrado


def _fator_k(ell_c: float, linha: str) -> float:
    """o fator de redução K da Tabela 28 (interpolado; abaixo de 2, o de 2; acima de 100, 1,0)"""
    if ell_c > K_ELL[-1]:
        return 1.0
    return float(np.interp(ell_c, K_ELL, K_TABELA[linha]))


def _ca_cilindro(Vk: float, d: float, ell_d: float) -> Tuple[float, float, str]:
    """(Ca, K, regime) da barra circular (Tabelas 27 e 28). Acima do crítico a norma (8.1.3) lembra que a força com
    vento menor, ainda no regime subcrítico, pode ser maior: fica o maior dos dois, já referido ao q de Vk"""
    Re = 70000.0 * Vk * d
    if Re < 4.2e5:
        return 1.2, _fator_k(ell_d, "subcritico"), "subcrítico"
    Ca = 0.6 if Re < 8.4e5 else 0.7 if Re < 2.3e6 else 0.8
    K = _fator_k(ell_d, "acima")
    Vc = 4.2e5 / (70000.0 * d)                                # o vento no limite do subcrítico
    sub = 1.2 * _fator_k(ell_d, "subcritico") * (Vc / Vk) ** 2
    if sub > Ca * K:
        return sub, 1.0, "acima do crítico (governa o subcrítico, V = %.1f m/s)" % Vc
    return Ca, K, "acima do crítico"


def _barra_exposta(br: dict) -> bool:
    if br.get("hipotese") or br.get("elemento") in ("trelica", "sanfona"):
        return False
    if br["papel"] in ("pilar", "viga"):
        return True
    return br["papel"] == "contraventamento" and abs(float(br["R"][0][2])) > 0.3    # o X vertical entre pilares


def _vento_nas_barras(M: dict, Vk: float, q: float, sentido) -> Tuple[Dict[int, np.ndarray], List[dict]]:
    """a força de arrasto nas barras expostas (NBR 6123:2023, 8.1.1 e 8.1.2), para o vento horizontal no `sentido` (x, y):
    {barra: w global (kN/m)} e o resumo por papel e perfil. F = C·q·K·c por metro, na componente do vento perpendicular à
    barra (sen² do ângulo, como em 8.2); c = a largura da seção projetada perpendicular ao vento (Tabela 26, Nota 2)"""
    nos, barras = M["nos"], M["barras"]
    wv = _unit(np.array([float(sentido[0]), float(sentido[1]), 0.0]))
    contornos = M.setdefault("_contornos", {})
    # o comprimento da peça inteira (o esqueleto parte a peça nos nós): é o ℓ da Tabela 28
    ell: Dict[str, float] = collections.Counter()
    for br in barras:
        if br["ids"] and _barra_exposta(br):
            ell[br["ids"][0]] += br["L"]
    dist: Dict[int, np.ndarray] = {}
    resumo: Dict[Tuple[str, str], dict] = {}
    for i, br in enumerate(barras):
        if not _barra_exposta(br):
            continue
        ex, ey, ez = br["R"]
        wp = wv - float(wv @ ex) * ex
        s2 = float(wp @ wp)                                   # sen² do ângulo entre o vento e a barra
        if s2 < 1e-4:
            continue
        cont = _secao_desenho(br["perfil"], contornos)
        if not cont:
            continue
        xy = np.array(cont, float) / 1000.0                   # x = a largura da mesa (ez), y = a altura (ey)
        perp = _unit(np.cross(ex, wp))
        proj = xy[:, 0] * float(ez @ perp) + xy[:, 1] * float(ey @ perp)
        c = float(proj.max() - proj.min())
        if c <= 1e-4:
            continue
        L = ell.get(br["ids"][0], br["L"]) if br["ids"] else br["L"]
        dobra = 2.0 if br["papel"] == "pilar" else 1.0         # 8.1.3: o pé no chão impede o escoamento naquela ponta
        if br["perfil"].upper().startswith(("TC", "Ø", "TUBO CIRC")):        # tubo circular e barra redonda
            C, K, regime = _ca_cilindro(Vk, c, dobra * L / c)
        else:
            C, K, regime = CF_FACES_PLANAS, _fator_k(dobra * L / c, "planas"), "faces planas"
        w = C * K * q * c * s2
        dist[i] = w * _unit(wp)
        chave = (br["papel"], br["perfil"])
        r = resumo.get(chave)
        if r is None or w > r["w_kN_m"]:
            resumo[chave] = {"papel": br["papel"], "perfil": br["perfil"], "C": round(C, 3), "K": round(K, 3), "c_mm": round(c * 1000),
                             "regime": regime, "w_kN_m": round(w, 4), "barras": (r or {}).get("barras", 0)}
        resumo[chave]["barras"] += 1
    return dist, sorted(resumo.values(), key=lambda r: (r["papel"], r["perfil"]))


MODOS_VENTO = ("auto", "isolada", "fechado")


def _modo_do_vento(M: dict) -> Tuple[str, str, str]:
    """(modo adotado, motivo, modo pedido) — M4, 14/10. O pedido vem das premissas (`modelo_vento`): "isolada" (cobertura
    isolada, 7.2), "fechado" (galpão fechado: Tabelas 6 e 7 + C_pi) ou "auto" — o fechado liga sozinho quando o modelo tem
    longarinas (ou terças de parede) ou telha de parede descendo até a metade de baixo do pé-direito (decisão do usuário)"""
    from nucleo.base import ErroDeDados
    P = M["par"]
    pedido = str(P.get("modelo_vento") or "auto").strip().lower()
    if pedido not in MODOS_VENTO:
        raise ErroDeDados("modelo do vento \"%s\" desconhecido: use auto, isolada ou fechado" % pedido)
    tem_pilar = any(br["papel"] == "pilar" for br in M["barras"])
    if pedido == "isolada":
        return "isolada", "escolhido nas premissas", pedido
    if pedido == "fechado":
        if not tem_pilar:
            raise ErroDeDados("galpão fechado: o modelo não tem pilares de aço para receber a pressão das paredes — use a "
                              "cobertura isolada")
        return "fechado", "escolhido nas premissas", pedido
    f = M.get("fechamento") or {}
    if M.get("movel"):
        return "isolada", "cobertura retrátil (lona, aberta nas laterais)", pedido
    if not tem_pilar:
        return "isolada", "o modelo não tem pilares de aço (a parede não teria onde se apoiar)", pedido
    if f.get("longarinas") or f.get("tercas_parede"):
        partes = []
        if f.get("longarinas"):
            partes.append("%d longarina(s)" % f["longarinas"])
        if f.get("tercas_parede"):
            partes.append("%d terça(s) de parede (presas só em pilares)" % f["tercas_parede"])
        return "fechado", "o modelo tem %s de fechamento lateral" % " e ".join(partes), pedido
    if f.get("telhas_parede"):
        return "fechado", ("o modelo tem %d telha(s) de parede (verticais, descendo até a metade de baixo do pé-direito)"
                           % f["telhas_parede"]), pedido
    motivo = "o modelo não tem longarinas nem telha de parede"
    if f.get("telhas_altas"):
        motivo += ("; as %d telha(s) verticais do modelo ficam acima da metade do pé-direito (testeira, beiral dobrado) e "
                   "não fecham a parede" % f["telhas_altas"])
    return "isolada", motivo, pedido


def _vento(M: dict, cob: dict, avisos: List[str]) -> Tuple[Dict[str, dict], dict]:
    """os casos de vento pelo modo adotado (M4, 14/10): cobertura isolada (7.2) ou galpão fechado (Tabelas 6 e 7 + C_pi).
    O modo, o motivo da escolha e o pedido ficam no info (para a tela e o memorial). No "auto", o fechado que não fecha a
    conta (fora das Tabelas 6 e 7) volta à cobertura isolada, com aviso; pedido nas premissas, o erro sobe"""
    from nucleo.base import ErroDeDados
    P = M["par"]
    if not P.get("vento") or not cob:
        return {}, {}
    modo, motivo, pedido = _modo_do_vento(M)
    casos, info = {}, {}
    if modo == "fechado":
        try:
            casos, info = _vento_fechado(M, cob, avisos)
        except ErroDeDados as e:
            if pedido == "fechado":
                raise
            avisos.insert(0, "vento: o galpão fechado (%s) não deu para calcular — %s. Usada a cobertura isolada" % (motivo, e))
            modo, motivo = "isolada", "o galpão fechado não fechou a conta (%s)" % e
    if modo == "isolada":
        casos, info = _vento_isolada(M, cob, avisos)
    if info:
        info.update(modo=modo, motivo=motivo, modo_pedido=pedido)
    if modo == "fechado" and casos:
        avisos.append("vento como galpão fechado (NBR 6123:2023, Tabelas 6 e 7 + C_pi %s): %s — troque em \"Modelo do vento\" "
                      "nas premissas" % (" e ".join(("%+.1f" % c).replace(".", ",") for c in info.get("cpi") or []), motivo))
    return casos, info


#: Os pilares de uma fila (a mesma coordenada transversal ao vento, como na análise global do pré-moldado): até esta
#: distância (m) entre eles. Tolerância de modelagem, não critério de norma.
FILA_TOL = 0.5


def _agrupar(valores: Dict, tol: float) -> Dict[float, list]:
    """{coordenada média: [chaves]} — as chaves agrupadas pela coordenada (diferença até tol da anterior)"""
    out: List[Tuple[List[float], list]] = []
    for k, v in sorted(valores.items(), key=lambda kv: kv[1]):
        if out and v - out[-1][0][-1] <= tol:
            out[-1][0].append(v)
            out[-1][1].append(k)
        else:
            out.append(([v], [k]))
    return {sum(vs) / len(vs): ks for vs, ks in out}


def _larguras(coords: Sequence[float]) -> Dict[float, float]:
    """a largura de influência de cada fila: meia distância às vizinhas (as das pontas, só para dentro)"""
    cs = sorted(coords)
    return {c: ((c - cs[k - 1]) / 2.0 if k > 0 else 0.0) + ((cs[k + 1] - c) / 2.0 if k + 1 < len(cs) else 0.0)
            for k, c in enumerate(cs)}


def _ligadas_aos_apoios(M: dict) -> set:
    """as barras ligadas (pelos nós) a algum apoio: a longarina solta no esqueleto não leva carga a lugar nenhum"""
    barras = M["barras"]
    por_no: Dict[int, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        por_no[br["a"]].append(i)
        por_no[br["b"]].append(i)
    vistos = {int(ap["no"]) for ap in M["apoios"]}
    pilha = list(vistos)
    ok = set()
    while pilha:
        no = pilha.pop()
        for i in por_no.get(no, ()):
            if i in ok:
                continue
            ok.add(i)
            for k in (barras[i]["a"], barras[i]["b"]):
                if k not in vistos:
                    vistos.add(k)
                    pilha.append(k)
    return ok


def _nome_cpi(v: float) -> str:
    return ("cpi%+.1f" % v).replace(".", ",").replace("-", "−")


def _vento_fechado(M: dict, cob: dict, avisos: List[str]) -> Tuple[Dict[str, dict], dict]:
    """o vento do galpão fechado (M4, 14/10/2026), NBR 6123:2023: q pela 4.2 (S2 na altura do topo acima das bases); C_e
    das paredes pela Tabela 6 e do telhado pela Tabela 7 (nucleo.cargas.coeficientes_pressao_galpao, os mesmos da análise
    global do pré-moldado); C_pi pela 6.3.2.1 (nucleo.cargas.coeficiente_pressao_interna, pela permeabilidade das
    premissas — por padrão "duas faces opostas igualmente permeáveis": +0,2 e −0,3, os dois em todas as direções). Pressão
    efetiva p = (C_e − C_pi)·q (6.1), positiva empurrando a face para dentro.

    Quatro direções (±u, perpendicular à geratriz; ±n, ao longo dela) × os casos de C_pi:

    * paredes: as faces são as linhas dos pilares das bordas — em cada fila de pilares na direção do vento o primeiro é a
      parede de barlavento e o último a de sotavento; em cada fila ao longo do vento, o primeiro e o último na transversal
      são as paredes laterais (zona 1 até z1 da borda de barlavento, zona 2 depois). A face com longarinas ligadas à
      estrutura recebe a pressão nas longarinas (a faixa de altura de cada fiada: meio caminho até as vizinhas, da cota
      das bases ao topo da parede); sem elas, nos pilares da borda pela largura de influência (meia distância aos
      vizinhos da face), na altura toda do pilar: w = (C_e − C_pi)·q·largura (kN/m). A parede que não desce até o chão
      (`parede_z_inferior`, a lona da Kaefer a 2,00 m do piso) começa ali; com `parede_nas_vigas` a viga do alinhamento
      da face (a do topo dos pilares) é a fiada de cima;
    * telhado: pelas terças (a faixa de cada uma) ou pelos trechos do banzo de cima, como o caminho da cobertura isolada —
      EF/GH na água de barlavento/sotavento com o vento perpendicular à cumeeira; EG, FH e IJ pela distância ao oitão de
      barlavento (b/2, b e o resto, NOTA 3 da Tabela 7) com o vento ao longo dela.

    Os pilares, vigas e contraventamentos ficam dentro do fechamento: sem o arrasto da 8.1."""
    from nucleo import cargas as C
    from nucleo.base import ErroDeDados
    P, nos, barras = M["par"], M["nos"], M["barras"]
    f_ = M.get("fechamento") or {}
    g = _geometria_da_cobertura(M, cob)
    u2, n2 = np.asarray(g["u"], float), np.asarray(g["n"], float)
    U3, N3 = np.array([u2[0], u2[1], 0.0]), np.array([n2[0], n2[1], 0.0])
    # os pilares por pé em planta: as barras de cada um e a posição
    pil: Dict[str, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        if br["papel"] == "pilar":
            pil[chave_do_pilar(nos, br)].append(i)
    if not pil:
        raise ErroDeDados("o modelo não tem pilares de aço")
    xy = {k: np.array([float(v) for v in k.split(",")]) / 1000.0 for k in pil}
    sp = {k: float(p_ @ u2) for k, p_ in xy.items()}
    tp = {k: float(p_ @ n2) for k, p_ in xy.items()}
    s0, s1, t0, t1 = min(sp.values()), max(sp.values()), min(tp.values()), max(tp.values())
    Ls, Lt = s1 - s0, t1 - t0
    if Ls < 1e-3 or Lt < 1e-3:
        raise ErroDeDados("os pilares estão numa linha só (sem planta para as paredes)")
    z_base = float(f_.get("z_base", 0.0))
    z_bei, z_top = float(g["zb"]), float(g["zt"])
    h = z_bei - z_base
    if h <= 0:
        raise ErroDeDados("o beiral (%.2f m) não está acima das bases (%.2f m)" % (z_bei, z_base))
    b_dim, a_dim = min(Ls, Lt), max(Ls, Lt)
    tg = float(g["tg"])
    teta = math.degrees(math.atan(tg))
    z_ref = max(z_top - z_base, 1.0)
    classe = P.get("classe") or C.classe_por_dimensao(max(a_dim, b_dim, z_ref))
    S2 = C.fator_s2(P["categoria"], classe, z_ref)
    Vk = C.velocidade_caracteristica(float(P["v0"]), float(P["s1"]), S2, float(P["s3"]))
    q = C.pressao_dinamica(Vk)
    coefs = C.coeficientes_pressao_galpao(b_dim, a_dim, h, teta)
    ce = {(c.direcao, c.letra): c.Ce for c in coefs.coeficientes if not c.local}
    aberturas = P.get("aberturas") or "duas faces opostas"
    cpis = C.coeficiente_pressao_interna(aberturas)
    # a geratriz (n) é a cumeeira; a Tabela 7 a supõe ao longo da maior dimensão (a)
    cumeeira_na_maior = Lt >= Ls - 1e-6
    if not cumeeira_na_maior:
        avisos.append("vento (galpão fechado): a cumeeira está na menor dimensão em planta (%.1f m × %.1f m) — a Tabela 7 da "
                      "NBR 6123 supõe a cumeeira ao longo da maior; os coeficientes do telhado foram aplicados como "
                      "aproximação" % (Lt, Ls))
    if g["uma_agua"]:
        avisos.append("vento (galpão fechado): telhado de uma água — usados os C_e da Tabela 7 (duas águas): a água inteira "
                      "como de barlavento (EF) com o vento do lado baixo e de sotavento (GH) com o do lado alto; a tabela de "
                      "telhados de uma água da NBR 6123 ainda não está no sistema")
    n_cob = len(set((cob.get("coberturas") or {}).values()))
    if n_cob > 1:
        avisos.append("vento (galpão fechado): as %d coberturas do modelo entraram como um telhado só (Tabela 7)" % n_cob)
    if a_dim / h > 4.0 or a_dim / b_dim > 4.0:
        avisos.append("vento (galpão fechado): a/h ou a/b > 4 — a NBR 6123:2023 (6.1.5) pede a força de atrito nas paredes "
                      "e no telhado, que ainda não entra neste modo: confira")
    # a face de cada longarina: a paralela a n fica numa face s (s0 ou s1), a paralela a u numa face t (t0 ou t1); só as
    # ligadas à estrutura (a solta no esqueleto não leva a carga a nada)
    ligadas = _ligadas_aos_apoios(M)
    faces_long: Dict[Tuple[int, int], List[int]] = collections.defaultdict(list)
    soltas = 0
    for i in f_.get("barras_longarina") or []:
        br = barras[i]
        d = br["R"][0][:2]
        m = (nos[br["a"]] + nos[br["b"]])[:2] / 2.0
        if abs(float(d @ n2)) >= abs(float(d @ u2)):
            face = (0, 0 if abs(float(m @ u2) - s0) <= abs(float(m @ u2) - s1) else 1)
        else:
            face = (1, 0 if abs(float(m @ n2) - t0) <= abs(float(m @ n2) - t1) else 1)
        if i in ligadas:
            faces_long[face].append(i)
        else:
            soltas += 1
    if soltas:
        avisos.append("vento (galpão fechado): %d trecho(s) de longarina sem ligação com os apoios no esqueleto — a pressão "
                      "daquelas paredes foi para os pilares da borda" % soltas)
    # a viga no alinhamento de uma face que já tem longarinas (a do topo dos pilares) vira a fiada de cima dela
    vigas_parede = 0
    if P.get("parede_nas_vigas") and faces_long:
        for i, br in enumerate(barras):
            if br["papel"] != "viga" or br.get("hipotese") or i not in ligadas:
                continue
            a_, b_ = nos[br["a"]], nos[br["b"]]
            if abs(float(b_[2] - a_[2])) > 0.05 * br["L"]:
                continue                                  # inclinada: não é a viga do topo da parede
            d = br["R"][0][:2]
            m = (a_ + b_)[:2] / 2.0
            if abs(float(d @ n2)) >= abs(float(d @ u2)):
                cand = [((0, 0), abs(float(m @ u2) - s0)), ((0, 1), abs(float(m @ u2) - s1))]
            else:
                cand = [((1, 0), abs(float(m @ n2) - t0)), ((1, 1), abs(float(m @ n2) - t1))]
            face, dist_face = min(cand, key=lambda c: c[1])
            if dist_face <= FILA_TOL and face in faces_long:
                faces_long[face].append(i)
                vigas_parede += 1
    # a parede começa em z_par (a lona da Kaefer para a 2,00 m do piso); o topo: o beiral nas faces ao longo da cumeeira
    # (as faces s); a altura média do oitão nas outras
    z_par = z_base + max(0.0, float(P.get("parede_z_inferior") or 0.0))
    topo_face = {0: z_bei, 1: (z_bei + z_top) / 2.0}
    alt_faixa: Dict[Tuple[int, int], Dict[int, float]] = {}
    for face, bs in faces_long.items():
        zs = {i: float((nos[barras[i]["a"]][2] + nos[barras[i]["b"]][2]) / 2.0) for i in bs}
        fiadas = sorted(_agrupar(zs, COTA_BASE_TOL).items())
        alt_faixa[face] = {}
        for k, (z, ks) in enumerate(fiadas):
            lo = max((z + fiadas[k - 1][0]) / 2.0 if k > 0 else z_par, z_par)
            hi = (z + fiadas[k + 1][0]) / 2.0 if k + 1 < len(fiadas) else max(topo_face[face[0]], z)
            for i in ks:
                alt_faixa[face][i] = max(hi - lo, 0.0)

    def acima(i):
        """a fração do trecho de pilar acima de onde a parede começa"""
        za, zb = sorted((float(nos[barras[i]["a"]][2]), float(nos[barras[i]["b"]][2])))
        if zb - za < 1e-6:
            return 1.0 if za >= z_par else 0.0
        return min(1.0, max(0.0, (zb - max(za, z_par)) / (zb - za)))

    def somar(dist, i, v):
        dist[i] = dist.get(i, np.zeros(3)) + v

    # o telhado: as terças e os trechos do banzo de cima
    trechos = cob["trechos"]
    ter = cob.get("tercas") or {}
    tercas = [tc for ts in (ter.get("por_cobertura") or {}).values() for tc in ts]
    fora = (ter.get("trechos") or set()) & set(trechos)
    s_c = float(g["s_alto"])                              # a cumeeira (na de uma água, a borda alta)

    def ce_telhado(eixo: int, sg: float, s_m: float, t_m: float) -> float:
        """C_e da Tabela 7 no ponto (s, t) do telhado; positivo empurra para baixo"""
        if eixo == 0:                                     # perpendicular à cumeeira: EF na água de barlavento
            if g["uma_agua"]:
                do_baixo = (g["s_baixo"] - g["s_alto"]) * sg < 0
                return ce[(C.TRANSVERSAL, "EF" if do_baixo else "GH")]
            return ce[(C.TRANSVERSAL, "EF" if (s_m - s_c) * sg < 0 else "GH")]
        d = (t_m - t0) if sg > 0 else (t1 - t_m)          # ao longo da cumeeira: a distância ao oitão de barlavento
        return ce[(C.LONGITUDINAL, "EG" if d <= b_dim / 2.0 else "FH" if d <= b_dim else "IJ")]

    casos: Dict[str, dict] = {}
    up = np.array([0.0, 0.0, 1.0])
    exemplo = None
    for rot, eixo, sg in (("→", 0, 1.0), ("←", 0, -1.0), ("↑", 1, 1.0), ("↓", 1, -1.0)):
        e_al = u2 if eixo == 0 else n2
        c_al, c_tr = (sp, tp) if eixo == 0 else (tp, sp)
        lo_al, hi_al = (s0, s1) if eixo == 0 else (t0, t1)
        dv3 = (U3 if eixo == 0 else N3) * sg              # o sentido do vento
        tr3 = N3 if eixo == 0 else U3
        # Tabela 6: transversal = o vento perpendicular à face maior (a face que ele pega tem o comprimento da outra
        # dimensão em planta)
        face_len, outro = (Lt, Ls) if eixo == 0 else (Ls, Lt)
        dirn = C.TRANSVERSAL if face_len >= outro - 1e-6 else C.LONGITUDINAL
        L_b, L_so, L_l1, L_l2 = ("A", "B", "C1/D1", "C2/D2") if dirn == C.TRANSVERSAL else ("C", "D", "A1/B1", "A2/B2")
        z1 = min(2.0 * h, b_dim / 2.0) if dirn == C.TRANSVERSAL else min(max(b_dim / 3.0, a_dim / 4.0), 2.0 * h)
        borda_barl = lo_al if sg > 0 else hi_al
        face_barl, face_sota = (eixo, 0 if sg > 0 else 1), (eixo, 1 if sg > 0 else 0)
        filas = _agrupar(c_tr, FILA_TOL)
        larg = _larguras(list(filas))
        filas2 = _agrupar(c_al, FILA_TOL)
        larg2 = _larguras(list(filas2))
        for cpi in cpis:
            v = float(cpi.valor)
            dist: Dict[int, np.ndarray] = {}
            # paredes de barlavento e de sotavento: o primeiro e o último pilar de cada fila na direção do vento
            for c_, ks in filas.items():
                ordem = sorted(ks, key=lambda k: c_al[k] * sg)
                papeis = [(ordem[0], L_b, 1.0, face_barl)] + ([(ordem[-1], L_so, -1.0, face_sota)] if len(ordem) > 1 else [])
                for k, letra, sinal, face in papeis:
                    if face in faces_long:
                        continue
                    pnet = (ce[(dirn, letra)] - v) * q                    # + empurra a face para dentro
                    for i in pil[k]:
                        somar(dist, i, pnet * larg[c_] * sinal * acima(i) * dv3)  # para dentro: a favor do vento a barlavento
                    if exemplo is None and letra == L_b and larg[c_] > 0:
                        exemplo = {"caso": "V%s %s" % (rot, _nome_cpi(v)), "pilar": k, "face": letra, "Ce": ce[(dirn, letra)],
                                   "Cpi": v, "q_kN_m2": round(q, 4), "largura_m": round(larg[c_], 3),
                                   "w_kN_m": round(pnet * larg[c_], 4)}
            # paredes laterais (paralelas ao vento): o primeiro e o último na transversal de cada fila ao longo do vento
            for c_, ks in filas2.items():
                ordem = sorted(ks, key=lambda k: c_tr[k])
                if len(ordem) < 2:
                    continue
                letra = L_l1 if abs(c_ - borda_barl) <= z1 else L_l2
                for k, sinal, face in ((ordem[0], 1.0, (1 - eixo, 0)), (ordem[-1], -1.0, (1 - eixo, 1))):
                    if face in faces_long:
                        continue
                    pnet = (ce[(dirn, letra)] - v) * q
                    for i in pil[k]:
                        somar(dist, i, pnet * larg2[c_] * sinal * acima(i) * tr3)
            # as faces com longarinas: a faixa de altura de cada fiada
            for face, alts in alt_faixa.items():
                eixo_f, lado = face
                normal_in = (U3 if eixo_f == 0 else N3) * (1.0 if lado == 0 else -1.0)
                for i, hf in alts.items():
                    if eixo_f == eixo:
                        letra = L_b if face == face_barl else L_so
                    else:
                        m = (nos[barras[i]["a"]] + nos[barras[i]["b"]])[:2] / 2.0
                        letra = L_l1 if abs(float(m @ e_al) - borda_barl) <= z1 else L_l2
                    somar(dist, i, (ce[(dirn, letra)] - v) * q * hf * normal_in)
            # o telhado: p = (C_e − C_pi)·q, positivo empurra para baixo
            nodal: Dict[int, np.ndarray] = {}
            for tc in tercas:
                for i in tc["barras"]:
                    t_i = float(((nos[barras[i]["a"]] + nos[barras[i]["b"]])[:2] / 2.0) @ n2)
                    w_t = np.zeros(3)
                    for s_k, an_k, _ in tc["amostras"]:
                        w_t += -(ce_telhado(eixo, sg, s_k, t_i) - v) * q * an_k
                    somar(dist, i, w_t)
            for i, (Ls_, Lh, w) in trechos.items():
                if i in fora:
                    continue
                a, b = nos[barras[i]["a"]], nos[barras[i]["b"]]
                m = (a + b) / 2.0
                cp = ce_telhado(eixo, sg, float(m[:2] @ u2), float(m[:2] @ n2)) - v
                d = _unit(b - a)
                nn = _unit(up - (up @ d) * d)
                nodal[i] = -cp * q * Ls_ * w * nn / 2.0
            casos["V%s %s" % (rot, _nome_cpi(v))] = {
                "dist": dist, "nodal": nodal, "nos": {}, "cpi": v, "direcao": dirn, "fechado": True,
                "sentido": [float(x) for x in dv3[:2]],
                "descricao": "galpão fechado: vento %s (%s na Tabela 6), C_pi = %s (NBR 6123:2023, Tabelas 6 e 7; 6.3.2.1)"
                % ("perpendicular à geratriz" if eixo == 0 else "ao longo da geratriz", dirn, ("%+.1f" % v).replace(".", ","))}
    info = {"tabela": "Tabelas 6 e 7 + C_pi (galpão fechado)", "Vk": round(Vk, 2), "S2": round(S2, 3), "q_kN_m2": round(q, 3),
            "classe": classe, "z": round(z_ref, 2), "b": round(b_dim, 2), "a": round(a_dim, 2), "h": round(h, 2),
            "teta": round(teta, 2), "tg": round(tg, 3), "aguas": 1 if g["uma_agua"] else 2, "vao": round(g["vao"], 2),
            "profundidade": round(g["prof"], 2), "aberturas": aberturas, "cpi": [float(c.valor) for c in cpis],
            "cpi_descricao": [c.descricao for c in cpis],
            "cpi_hipotese": ("permeabilidade \"%s\" (premissas; o padrão é o da NBR 6123:2023, 6.3.2.1-a: duas faces opostas "
                             "igualmente permeáveis, as outras impermeáveis) — cada C_pi em todas as direções" % aberturas),
            "coeficientes": {"%s %s" % k: round(v_, 3) for k, v_ in sorted(ce.items())},
            "paredes": {"caminho": ("longarinas em %d face(s); pilares da borda nas outras" % len(faces_long)) if faces_long
                        else "pilares da borda (largura de influência, altura toda)",
                        "longarinas_soltas": soltas, "z_inferior": round(z_par - z_base, 3), "vigas_na_parede": vigas_parede},
            "exemplo_parede": exemplo, "observacoes": list(coefs.observacoes)}
    return casos, info


def _vento_isolada(M: dict, cob: dict, avisos: List[str]) -> Tuple[Dict[str, dict], dict]:
    """os casos de vento da cobertura isolada (NBR 6123:2023, 7.2), em cada cobertura independente — as que estão em níveis
    diferentes (o Docas, 08/10) eram uma só: a "flecha" ia do banzo de uma ao da outra (tg θ 1,29 numa marquise de 9°).
    O vento nas barras (pilares, vigas) entra uma vez, com a primeira"""
    grupos = sorted(set((cob.get("coberturas") or {}).values()))
    if len(grupos) <= 1:
        return _vento_uma(M, cob, avisos)
    barras = M["barras"]
    casos: Dict[str, dict] = {}
    infos = []
    for k in grupos:
        planos = {g: p_ for g, p_ in cob["planos"].items() if cob["coberturas"][g] == k}
        trechos = {i: v for i, v in cob["trechos"].items() if barras[i]["grupo"] in planos}
        sub = dict(cob, planos=planos, trechos=trechos)
        c_k, i_k = _vento_uma(M, sub, avisos, com_barras=not infos)
        infos.append(i_k)
        for nome, caso in c_k.items():
            if nome not in casos:
                casos[nome] = dict(caso, nodal=dict(caso["nodal"]), nos=dict(caso.get("nos") or {}), dist=dict(caso.get("dist") or {}))
                continue
            casos[nome]["nodal"].update(caso["nodal"])
            casos[nome]["dist"].update(caso.get("dist") or {})          # as terças da outra cobertura
            for no_, F in (caso.get("nos") or {}).items():
                casos[nome]["nos"][no_] = casos[nome]["nos"].get(no_, np.zeros(3)) + F
            if "Ft" in caso:
                casos[nome]["Ft"] = casos[nome].get("Ft", 0.0) + caso["Ft"]
    info = dict(infos[0], coberturas=infos)
    return casos, info


def _geometria_da_cobertura(M: dict, cob: dict) -> dict:
    """a geometria da cobertura pelos trechos do banzo de cima: o triedro em planta (u = o vão, perpendicular à geratriz;
    n = a geratriz), as coordenadas s (ao longo de u) e t (ao longo de n) dos nós, o vão, a profundidade, as cotas, a
    inclinação (tg θ) e se é de uma água (com as bordas alta e baixa)"""
    nos, barras = M["nos"], M["barras"]
    trechos, planos = cob["trechos"], cob["planos"]
    pts = np.array([nos[barras[i][k]] for i in trechos for k in ("a", "b")])
    zt = float(pts[:, 2].max())
    # dimensões em planta da cobertura
    u = np.mean([p["u"] for p in planos.values()], axis=0)
    u = _unit(u)
    n = np.array([-u[1], u[0]])
    s = pts[:, :2] @ u
    t = pts[:, :2] @ n
    vao, prof = float(s.max() - s.min()), float(t.max() - t.min())
    # a inclinação equivalente: a flecha da cobertura sobre o meio vão (tg θ), pelos nós do banzo superior
    zb = float(pts[:, 2].min())
    flecha = zt - zb
    tg = flecha / (vao / 2.0) if vao > 0 else 0.0
    h_livre = zb
    # uma água (Tabela 24) ou duas (Tabela 25): na de uma água o ponto mais alto do banzo de cima está numa das bordas (a
    # marquise do Docas, 08/10; antes toda cobertura ia pela Tabela 25, com a "flecha" sobre meio vão e a ponta inclinada do
    # beiral junto: tg θ 0,443 numa água de 0,159). A inclinação é a do banzo de cima, a mediana pelo comprimento em planta
    # (a ponta inclinada, curta, não manda)
    # entre os pontos no topo (até 1 cm; na plana, todos) vale o mais perto de uma borda: a plana é uma água de tg θ 0
    no_topo = s[pts[:, 2] >= zt - 0.01]
    s_alto = float(min(no_topo, key=lambda v: min(v - s.min(), s.max() - v)))
    uma_agua = vao > 0 and min(abs(s_alto - s.min()), abs(s_alto - s.max())) < 0.15 * vao
    s_baixo = float(s.min() if abs(s_alto - s.max()) < abs(s_alto - s.min()) else s.max())
    if uma_agua:
        incl = []
        for i, (Ls, Lh, w) in trechos.items():
            a_, b_ = nos[barras[i]["a"]], nos[barras[i]["b"]]
            if Lh > 1e-3:
                incl.append((abs(float(b_[2] - a_[2])) / Lh, Lh))
        incl.sort()
        meio, acum = sum(L_ for _, L_ in incl) / 2.0, 0.0
        for tg_i, L_ in incl:
            acum += L_
            if acum >= meio:
                tg = tg_i
                break
    return {"pts": pts, "zt": zt, "u": u, "n": n, "s": s, "t": t, "vao": vao, "prof": prof, "zb": zb, "flecha": flecha,
            "tg": tg, "h_livre": h_livre, "uma_agua": uma_agua, "s_alto": s_alto, "s_baixo": s_baixo}


def _vento_uma(M: dict, cob: dict, avisos: List[str], com_barras: bool = True) -> Tuple[Dict[str, dict], dict]:
    """o vento de uma cobertura isolada (NBR 6123:2023, 7.2): {caso: {barra: força nodal por ponta (kN, 3)}}"""
    from nucleo import cargas as C
    P, nos, barras = M["par"], M["nos"], M["barras"]
    if not P.get("vento") or not cob:
        return {}, {}
    trechos, planos = cob["trechos"], cob["planos"]
    g = _geometria_da_cobertura(M, cob)
    pts, zt, u, n, s, t = g["pts"], g["zt"], g["u"], g["n"], g["s"], g["t"]
    vao, prof, zb, flecha, tg, h_livre = g["vao"], g["prof"], g["zb"], g["flecha"], g["tg"], g["h_livre"]
    uma_agua, s_alto, s_baixo = g["uma_agua"], g["s_alto"], g["s_baixo"]
    maior = max(vao, prof, zt)
    classe = P.get("classe") or ("A" if maior <= 20 else "B" if maior <= 50 else "C")
    S2 = C.fator_s2(P["categoria"], classe, max(zt, 1.0))
    Vk = C.velocidade_caracteristica(float(P["v0"]), float(P["s1"]), S2, float(P["s3"]))
    q = C.pressao_dinamica(Vk)
    info = {"Vk": round(Vk, 2), "S2": round(S2, 3), "q_kN_m2": round(q, 3), "classe": classe, "z": round(zt, 2),
            "vao": round(vao, 2), "profundidade": round(prof, 2), "flecha": round(flecha, 3), "tg": round(tg, 3),
            "h_livre": round(h_livre, 2), "aguas": 1 if uma_agua else 2,
            "tabela": "Tabela 24 (uma água)" if uma_agua else "Tabela 25 (duas águas)"}
    if uma_agua and tg > 0.7:
        avisos.append("tg θ = %.2f acima de 0,7: fora da Tabela 24 da NBR 6123 — usado 0,7" % tg)
        tg = 0.7
    if uma_agua:
        pass
    elif tg < 0.07:
        avisos.append("cobertura quase plana (tg θ = %.3f < 0,07): a Tabela 25 da NBR 6123 começa em 0,07 — usado 0,07" % tg)
        tg = 0.07
    if tg > 0.6 and not uma_agua:
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

    def cp_uma_agua(carregamento: str, do_alto: bool, s_m: float) -> Optional[float]:
        """Tabela 24 (cobertura isolada a uma água plana): o cp no ponto s_m, positivo para baixo. t = 0 na borda alta e 1 na
        baixa. Carregamento 1 (tg θ ≤ 0,7): com o vento vindo do lado alto, para cima de 2,0 (borda alta) a tg θ (baixa);
        do lado baixo, para baixo de 2,0 (borda baixa) a tg θ (alta). Carregamento 2 (só até tg θ = 0,3), ao contrário — de
        0,2 a 0,3 as pontas são 6 − 20 tg θ (a de barlavento) e 0,6 − 2 tg θ."""
        tt = min(1.0, max(0.0, (s_m - s_alto) / (s_baixo - s_alto))) if s_baixo != s_alto else 0.5
        if carregamento == "1":
            return -(2.0 + (tg - 2.0) * tt) if do_alto else (tg + (2.0 - tg) * tt)
        if tg > 0.3:
            return None
        bar, sot = (2.0, tg) if tg <= 0.2 else (6.0 - 20.0 * tg, 0.6 - 2.0 * tg)
        return (bar + (sot - bar) * tt) if do_alto else -(sot + (bar - sot) * tt)
    if uma_agua:
        info["carregamento_1"] = {"tabela_24": "vento do lado alto: −2,0 → −%s (para cima); do lado baixo: +2,0 → +%s (para baixo)" % ((("%.3f" % tg).replace(".", ","),) * 2)}
        info["carregamento_2"] = ({"tabela_24": "só até tg θ = 0,3"} if tg > 0.3 else
                                  {"tabela_24": "vento do lado alto: para baixo; do lado baixo: para cima (%s)" % ("2,0 → tg θ" if tg <= 0.2 else "6 − 20 tg θ → 0,6 − 2 tg θ")})
    if h_livre < 0.5 * vao:
        avisos.append(("vento: a altura livre (%.2f m) é menor que 0,5 × a profundidade da cobertura (%.2f m) — a NBR 6123 "
                       "(7.2.1) pede, nesse caso, calcular como edificação fechada com cpi +0,8/−0,3 na zona de obstrução. "
                       "Usada a %s (cobertura isolada): conferir com o engenheiro (o modo \"galpão fechado\" das premissas "
                       "aplica as Tabelas 6 e 7)") % (h_livre, 0.5 * vao, info["tabela"]))
    smid = float((s.max() + s.min()) / 2)
    # as terças desta cobertura (as que recebem o telhado no lugar dos trechos do banzo)
    ter = cob.get("tercas") or {}
    minhas = {cob["coberturas"][g] for g in planos}
    tercas = [tc for c_, ts in (ter.get("por_cobertura") or {}).items() if c_ in minhas for tc in ts]
    fora = (ter.get("trechos") or set()) & set(trechos)
    casos: Dict[str, dict] = {}
    for nome_c, (cpb, cps) in (("1", c1), ("2", c2)):
        if uma_agua and tg > 0.3 and nome_c == "2":
            continue                                          # a Tabela 24 só tem o carregamento 2 até tg θ = 0,3
        for sentido, rot in ((+1, "→"), (-1, "←")):
            f: Dict[int, np.ndarray] = {}
            # o vento no sentido +u vem do lado de s menor: do lado alto se a borda alta tem s menor
            do_alto = (s_alto < s_baixo) if sentido > 0 else (s_alto > s_baixo)
            dt: Dict[int, np.ndarray] = {}
            for tc in tercas:
                # o cp ponto a ponto na faixa da terça (na Tabela 24 ele varia de uma borda à outra)
                w_t = np.zeros(3)
                for s_k, an_k, _ in tc["amostras"]:
                    if uma_agua:
                        cp_k = cp_uma_agua(nome_c, do_alto, s_k)
                    else:
                        cp_k = cpb if (s_k - smid) * sentido < 0 else cps
                    w_t += -cp_k * q * an_k                                # cp positivo empurra para baixo
                for i in tc["barras"]:
                    dt[i] = w_t
            for i, (Ls, Lh, w) in trechos.items():
                if i in fora:
                    continue
                a, b = nos[barras[i]["a"]], nos[barras[i]["b"]]
                m = (a + b) / 2
                if uma_agua:
                    cp = cp_uma_agua(nome_c, do_alto, float(m[:2] @ u))
                else:
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
                # as abas de lona nas bordas (NBR 6123, 7.2.5.1): 1,3·q·Ae a barlavento e 0,8·q·Ae a sotavento, as duas no
                # sentido do vento; cada tesoura recebe a faixa dela (meio passo de cada lado), metade no topo e metade no apoio
                dirv = np.array([u[0] * sentido, u[1] * sentido, 0.0])
                for t_ in mv["tesouras"]:
                    for top, bot in t_["lados"]:
                        pa = nos[bot]
                        barl = (float(pa[:2] @ u) - smid) * sentido < 0
                        Ae = (nos[top][2] - nos[bot][2]) * t_["faixa"]
                        Fa = (1.3 if barl else 0.8) * q * Ae * dirv
                        for no_ in (top, bot):
                            fn[no_] = fn.get(no_, np.zeros(3)) + Fa / 2.0
            db = {}
            if com_barras and P.get("vento_nas_barras", True):
                db, res = _vento_nas_barras(M, Vk, q, u * sentido)
                info.setdefault("barras_transversal", res)
            casos["V%s%s" % (nome_c, rot)] = {"dist": {**db, **dt}, "nos": fn, "nodal": f, "descricao": "vento perpendicular à geratriz, carregamento %s, %s%s"
                                              % (nome_c, "de um lado" if sentido > 0 else "do outro lado",
                                                 "; arrasto nos pilares e vigas (8.1)" if db else ""),
                                              "cpb": cpb, "cps": cps, "sentido": [float(v) for v in u * sentido]}
            if uma_agua:                                  # Tabela 24: o cp na borda de barlavento e na de sotavento
                s_b, s_s = (s_alto, s_baixo) if do_alto else (s_baixo, s_alto)
                casos["V%s%s" % (nome_c, rot)].update(cpb=round(cp_uma_agua(nome_c, do_alto, s_b), 3),
                                                       cps=round(cp_uma_agua(nome_c, do_alto, s_s), 3),
                                                       vem_do="lado alto" if do_alto else "lado baixo")
    # atrito no sentido da geratriz (7.2.2): F = 0,05 q a b, distribuída pelas áreas
    area_tot = sum(Lh * w for (Ls, Lh, w) in trechos.values()) or 1.0
    Ft = 0.05 * q * vao * prof
    for sentido, rot in ((+1, "↑"), (-1, "↓")):
        f = {}
        for i, (Ls, Lh, w) in trechos.items():
            if i in fora:
                continue
            F = np.zeros(3)
            F[:2] = n * sentido * Ft * (Lh * w) / area_tot
            f[i] = F / 2.0
        dt = {}
        for tc in tercas:                                         # ao longo da terça (a geratriz), pela área dela
            for i in tc["barras"]:
                dt[i] = np.array([n[0], n[1], 0.0]) * sentido * Ft * tc["w"] / area_tot
        db = {}
        if com_barras and P.get("vento_nas_barras", True):
            db, res = _vento_nas_barras(M, Vk, q, n * sentido)
            info.setdefault("barras_longitudinal", res)
        casos["Vat%s" % rot] = {"dist": {**db, **dt}, "nodal": f, "Ft": Ft,
                                "descricao": "vento ao longo da geratriz: atrito na cobertura (7.2.2)%s"
                                % ("; arrasto nos pilares e vigas (8.1)" if db else "")}
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
        ter = _tercas_da_cobertura(M, cob, avisos) if P.get("cargas_pelas_tercas", True) else {}
        cob["tercas"] = ter
        fora = (ter or {}).get("trechos") or set()
        cp, sc, cp_d, sc_d = {}, {}, {}, {}
        for i, (Ls, Lh, w) in cob["trechos"].items():
            if i in fora:
                continue
            cp[i] = np.array([0.0, 0.0, -g_cob * Ls * w / 2.0])
            sc[i] = np.array([0.0, 0.0, -float(P["sobrecarga"]) * Lh * w / 2.0])
        # pelas terças: a faixa na inclinação para a telha (por área de telhado) e na projeção para a sobrecarga
        for ts in ((ter or {}).get("por_cobertura") or {}).values():
            for tc in ts:
                for i in tc["barras"]:
                    cp_d[i] = np.array([0.0, 0.0, -g_cob * tc["w_inclinada"]])
                    sc_d[i] = np.array([0.0, 0.0, -float(P["sobrecarga"]) * tc["w"]])
        casos["CP"] = {"dist": cp_d, "nodal": cp, "descricao": "telha e permanentes da cobertura (%.2f kN/m²)%s"
                       % (g_cob, "; pelas terças" if cp_d else "")}
        if not (M.get("movel") and M["movel"]["configuracao"] != "aberta"):
            casos["SC"] = {"dist": sc_d, "nodal": sc, "descricao": "sobrecarga de cobertura (%.2f kN/m², projeção horizontal)%s"
                           % (float(P["sobrecarga"]), "; pelas terças" if sc_d else "")}
        area = sum(Lh * w for (Ls, Lh, w) in cob["trechos"].values())
        info["cobertura"] = {"area_m2": round(area, 1), "larguras_m": sorted({round(v, 3) for v in cob["larguras"].values()}),
                             "trelicas": len(cob["planos"]),
                             "tercas": sum(len(ts) for ts in ((ter or {}).get("por_cobertura") or {}).values())}
        vc, vi = _vento(M, cob, avisos)
        casos.update(vc)
        if vi:
            info["vento"] = vi
    for nome, caso in casos.items():
        if nome.startswith("V"):
            caso["sentido_vertical"], caso["Fz_kN"] = _sentido_vertical(caso, barras)
    return casos, info, avisos


def _sentido_vertical(caso: dict, barras: List[dict]) -> Tuple[str, float]:
    """("pressao" | "succao" | "horizontal", ΣFz kN) do caso: pelo sinal da soma das forças verticais (as nodais nas duas
    pontas, as distribuídas no comprimento, as dos nós). M5, 14/10: antes era pelo nome — "V2" sempre sucção —, e o
    carregamento 2 da Tabela 24 com o vento do lado alto, que empurra para BAIXO, ficava sem a combinação com a sobrecarga"""
    Fz = sum(2.0 * float(F[2]) for F in caso.get("nodal", {}).values()) +         sum(float(w[2]) * barras[i]["L"] for i, w in caso.get("dist", {}).items()) +         sum(float(F[2]) for F in (caso.get("nos") or {}).values())
    escala = sum(2.0 * float(np.abs(F).sum()) for F in caso.get("nodal", {}).values()) +         sum(float(np.abs(w).sum()) * barras[i]["L"] for i, w in caso.get("dist", {}).items()) +         sum(float(np.abs(F).sum()) for F in (caso.get("nos") or {}).values())
    if abs(Fz) <= 1e-6 * max(escala, 1.0):
        return "horizontal", round(Fz, 4)
    return ("pressao" if Fz < 0 else "succao"), round(Fz, 4)


def combinacoes(casos) -> Dict[str, dict]:
    """as combinações da NBR 8800 (Tabelas 1 e 2): ELU normais e ELS (raras e frequentes). `casos`: o dict dos casos (de
    `cargas`) ou só os nomes. O vento que empurra a cobertura para baixo (pressão) ou só de lado entra com os permanentes
    desfavoráveis e a sobrecarga (o vento principal e a sobrecarga principal) e também com os permanentes favoráveis; o que
    levanta (sucção) só com os permanentes favoráveis. M5, 14/10: a pressão/sucção vem do sinal efetivo do caso
    (`sentido_vertical`, gravado por `cargas`); com só os nomes, a regra antiga (o carregamento "V2" é sucção)"""
    from nucleo import cargas as C
    gpp = C.GAMA_G["metálica"][0]
    gcp = C.GAMA_G["moldada no local"][0]              # elementos construtivos industrializados (telha, terças)
    gsc, gv = C.GAMA_Q["sobrecarga"][0], C.GAMA_Q["vento"][0]
    psc0, pv0 = C.PSI["cobertura"][0], C.PSI["vento"][0]
    psc1, pv1 = C.PSI["cobertura"][1], C.PSI["vento"][1]
    tem = set(casos)
    ventos = [c for c in casos if c.startswith("V")]
    sentido = {c: (casos[c].get("sentido_vertical") if isinstance(casos, dict) and isinstance(casos[c], dict) else None)
               for c in ventos}
    G = {"PP": gpp, **({"CP": gcp} if "CP" in tem else {})}
    Gf = {"PP": 1.0, **({"CP": 1.0} if "CP" in tem else {})}
    out: Dict[str, dict] = {}
    if "SC" in tem:
        out["ELU1 SC"] = {"tipo": "ELU", "fatores": {**G, "SC": gsc}, "descricao": "permanentes + sobrecarga principal"}
    for v in ventos:
        pressao = (sentido[v] != "succao") if sentido[v] else not v.startswith("V2")
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

# Todas as barras de uma vez (numpy, em lote): a rigidez local, a condensação das rótulas (por padrão de graus soltos),
# a passagem para o global e a montagem esparsa com a estrutura da matriz calculada uma vez só — a 2ª ordem
# (nucleo3d/segunda_ordem.py) monta e resolve a mesma estrutura várias vezes por combinação.

def _lote(M: dict) -> dict:
    """as barras em arrays: L, seção, eixos (n, 3, 3), graus (n, 12) e os grupos de barras com o mesmo padrão de rótula"""
    barras = M["barras"]
    n = len(barras)
    sec = lambda k: np.array([br["sec"][k] for br in barras], float)
    a = np.array([br["a"] for br in barras], int)
    b = np.array([br["b"] for br in barras], int)
    dofs = np.concatenate([6 * a[:, None] + np.arange(6), 6 * b[:, None] + np.arange(6)], axis=1) if n else np.zeros((0, 12), int)
    pads: Dict[tuple, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        pads[tuple(sorted(set(br["soltos"])))].append(i)
    # o módulo de cada barra: o aço por padrão; a peça de concreto (análise global do pré-moldado, 09/10) leva o dela
    E = np.array([float(br["sec"].get("E") or E_ACO) for br in barras], float)
    G = np.array([float(br["sec"].get("G") or G_ACO) for br in barras], float)
    # o concreto já entra com a rigidez reduzida da NBR 6118 (15.7.3): a redução de 0,8 da 2ª ordem da NBR 8800 é do aço
    conc = np.array([bool(br["sec"].get("concreto")) for br in barras], bool)
    return {"conc": conc, "n": n, "L": np.array([br["L"] for br in barras], float), "A": sec("A"), "Iy": sec("Iy"), "Iz": sec("Iz"),
            "J": sec("J"), "E": E, "G": G, "R": np.array([br["R"] for br in barras], float).reshape(n, 3, 3), "dofs": dofs,
            "padroes": [(p, np.array(ix, int)) for p, ix in pads.items()]}


def _k_local_lote(lt: dict, fator: float = 1.0) -> np.ndarray:
    """(n, 12, 12): a rigidez elástica local de cada barra (a mesma de _rigidez_local); `fator` multiplica E e G (0,8 na
    2ª ordem da NBR 8800:2024, 4.10.7.1.2)"""
    L, n = lt["L"], lt["n"]
    k = np.zeros((n, 12, 12))
    E_, G_ = lt.get("E", E_ACO), lt.get("G", G_ACO)
    if fator != 1.0 and "conc" in lt:
        fator = np.where(lt["conc"], 1.0, fator)
    EA, GJ = fator * E_ * lt["A"] / L, fator * G_ * lt["J"] / L

    def por(i, j, v):
        k[:, i, j] = v
        k[:, j, i] = v
    for i, j, v in ((0, 0, EA), (6, 6, EA), (0, 6, -EA), (3, 3, GJ), (9, 9, GJ), (3, 9, -GJ)):
        por(i, j, v)
    for (v1, r1, v2, r2), I, s in (((1, 5, 7, 11), lt["Iz"], 1.0), ((2, 4, 8, 10), lt["Iy"], -1.0)):
        EI = fator * E_ * I
        a, b, c, d = 12 * EI / L ** 3, 6 * EI / L ** 2, 4 * EI / L, 2 * EI / L
        por(v1, v1, a); por(v2, v2, a); por(v1, v2, -a)
        por(v1, r1, s * b); por(v1, r2, s * b); por(v2, r1, -s * b); por(v2, r2, -s * b)
        por(r1, r1, c); por(r2, r2, c); por(r1, r2, d)
    return k


def _kg_local_lote(lt: dict, N: np.ndarray) -> np.ndarray:
    """(n, 12, 12): a rigidez geométrica consistente (N > 0 tração) nos dois planos de flexão — o P-Δ da 2ª ordem"""
    L, n = lt["L"], lt["n"]
    g = np.zeros((n, 12, 12))
    c = N / (30.0 * L)

    def por(i, j, v):
        g[:, i, j] = v
        g[:, j, i] = v
    for (v1, r1, v2, r2), s in (((1, 5, 7, 11), 1.0), ((2, 4, 8, 10), -1.0)):
        por(v1, v1, 36 * c); por(v2, v2, 36 * c); por(v1, v2, -36 * c)
        por(v1, r1, s * 3 * L * c); por(v1, r2, s * 3 * L * c); por(v2, r1, -s * 3 * L * c); por(v2, r2, -s * 3 * L * c)
        por(r1, r1, 4 * L * L * c); por(r2, r2, 4 * L * L * c); por(r1, r2, -L * L * c)
    return g


def _engaste_lote(L: np.ndarray, w: np.ndarray) -> np.ndarray:
    """(n, c, 12): o engaste perfeito (_engaste_perfeito) de cada barra e caso, w = (n, c, 3) local"""
    Lc = L[:, None]
    wx, wy, wz = w[..., 0], w[..., 1], w[..., 2]
    f = np.zeros(w.shape[:2] + (12,))
    f[..., 0] = f[..., 6] = -wx * Lc / 2
    f[..., 1] = f[..., 7] = -wy * Lc / 2
    f[..., 5], f[..., 11] = -wy * Lc * Lc / 12, wy * Lc * Lc / 12
    f[..., 2] = f[..., 8] = -wz * Lc / 2
    f[..., 4], f[..., 10] = wz * Lc * Lc / 12, -wz * Lc * Lc / 12
    return f


def _inv_lote(m: np.ndarray) -> np.ndarray:
    try:
        return np.linalg.inv(m)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(m)


def _condensar_lote(lt: dict, k: np.ndarray, f0: Optional[np.ndarray] = None):
    """a rigidez e o engaste perfeito com os graus soltos liberados, em lote por padrão de rótula: (kc, f0c, rec) — rec
    guarda o que recupera os giros soltos depois de resolver"""
    kc = k.copy()
    f0c = None if f0 is None else f0.copy()
    rec = []
    for pat, idx in lt["padroes"]:
        if not pat:
            continue
        r = np.array(pat, int)
        m = np.setdiff1d(np.arange(12), r)
        kk = k[idx]
        inv = _inv_lote(kk[:, r[:, None], r])
        kmr = kk[:, m[:, None], r]
        krm = kk[:, r[:, None], m]
        kn = np.zeros_like(kk)
        kn[:, m[:, None], m] = kk[:, m[:, None], m] - kmr @ inv @ krm
        kc[idx] = kn
        if f0 is not None:
            ff = f0[idx]
            fn = np.zeros_like(ff)
            fn[:, :, m] = ff[:, :, m] - np.einsum("gij,gcj->gci", kmr @ inv, ff[:, :, r])
            f0c[idx] = fn
        rec.append((idx, r, m, inv, krm))
    return kc, f0c, rec


def _para_global(lt: dict, kl: np.ndarray) -> np.ndarray:
    """(n, 12, 12): Tᵀ·k·T de cada barra (T = os eixos locais nos quatro blocos 3×3)"""
    n, R = lt["n"], lt["R"]
    G = np.einsum("nji,najbk,nkl->naibl", R, kl.reshape(n, 4, 3, 4, 3), R, optimize=True)
    return G.reshape(n, 12, 12)


def _forcas_para_global(lt: dict, f: np.ndarray) -> np.ndarray:
    """(n, c, 12) local → global (Tᵀ·f)"""
    n, R = lt["n"], lt["R"]
    return np.einsum("nji,ncaj->ncai", R, f.reshape(n, f.shape[1], 4, 3)).reshape(n, f.shape[1], 12)


def _somar_nos_graus(lt: dict, ndof: int, fg: np.ndarray) -> np.ndarray:
    """(ndof, c): as forças das pontas (n, c, 12, global) somadas nos graus dos nós"""
    n, c = fg.shape[0], fg.shape[1]
    out = np.zeros((ndof, c))
    np.add.at(out, lt["dofs"].reshape(-1), fg.transpose(0, 2, 1).reshape(n * 12, c))
    return out


def _deslocamentos_locais(lt: dict, U: np.ndarray) -> np.ndarray:
    """(n, 12, c): os deslocamentos das pontas de cada barra nos eixos locais"""
    n = lt["n"]
    ue = U[lt["dofs"]]                                            # (n, 12, c)
    return np.einsum("nij,najc->naic", lt["R"], ue.reshape(n, 4, 3, -1)).reshape(n, 12, -1)


def _recuperar_soltos(ul: np.ndarray, f0: np.ndarray, rec) -> None:
    """os giros soltos (rótula) que zeram o momento da ponta: ul (n, 12, c) e f0 (n, c, 12), no lugar"""
    for idx, r, m, inv, krm in rec:
        u = ul[idx]
        u[:, r, :] = -inv @ (krm @ u[:, m, :] + f0[idx][:, :, r].transpose(0, 2, 1))
        ul[idx] = u


class _Montador:
    """a matriz dos graus livres montada das matrizes das barras (n, 12, 12): a estrutura esparsa (CSC) sai uma vez; cada
    montagem é um bincount"""

    def __init__(self, dofs: np.ndarray, ndof: int, livres: np.ndarray):
        from scipy.sparse import csc_matrix  # noqa: F401 — falha cedo se faltar o scipy
        mapa = -np.ones(ndof, np.int64)
        mapa[livres] = np.arange(len(livres))
        nl = len(livres)
        rr = mapa[np.repeat(dofs, 12, axis=1)].reshape(-1)
        cc = mapa[np.tile(dofs, (1, 12))].reshape(-1)
        self.ok = (rr >= 0) & (cc >= 0)
        chave = cc[self.ok] * nl + rr[self.ok]
        uniq, self.inv = np.unique(chave, return_inverse=True)
        self.indices = (uniq % nl).astype(np.int32)
        self.indptr = np.searchsorted(uniq // nl, np.arange(nl + 1)).astype(np.int32)
        self.nu, self.nl = len(uniq), nl

    def matriz(self, Kg: np.ndarray):
        from scipy.sparse import csc_matrix
        dados = np.bincount(self.inv, weights=Kg.reshape(-1)[self.ok], minlength=self.nu)
        return csc_matrix((dados, self.indices, self.indptr), shape=(self.nl, self.nl))


def _sem_limite(U: np.ndarray) -> bool:
    """deslocamento absurdo ou não finito: o mecanismo que o fatoramento não pegou"""
    if not np.all(np.isfinite(U)):
        return True
    tr = U.reshape(-1, 6, U.shape[1])[:, :3, :] if U.ndim == 2 else U.reshape(-1, 6)[:, :3]
    return float(np.abs(tr).max(initial=0.0)) > 50.0


def resolver(M: dict, casos: Dict[str, dict]) -> dict:
    """resolve todos os casos de uma vez: deslocamentos, reações e esforços nas pontas de cada barra (local)"""
    from scipy.sparse.linalg import splu
    nos, barras = M["nos"], M["barras"]
    ndof = 6 * len(nos)
    nomes = list(casos)
    nc = len(nomes)
    lt = _lote(M)
    n = lt["n"]
    k = _k_local_lote(lt)
    # carga distribuída de cada caso, no local, e o engaste perfeito
    w_loc = np.zeros((n, nc, 3))
    for c, nome in enumerate(nomes):
        for i, wg in casos[nome]["dist"].items():
            w_loc[i, c] = lt["R"][i] @ wg
    f0 = _engaste_lote(lt["L"], w_loc)
    kc, f0c, rec = _condensar_lote(lt, k, f0)
    Kg = _para_global(lt, kc)
    # cargas nodais (por barra: a força em cada ponta) e as diretas em nós
    Fn = np.zeros((ndof, nc))
    for c, nome in enumerate(nomes):
        for i, Fp in casos[nome]["nodal"].items():
            br = barras[i]
            for no in (br["a"], br["b"]):
                Fn[6 * no:6 * no + 3, c] += Fp
        for no, Fp in (casos[nome].get("nos") or {}).items():
            Fn[6 * no:6 * no + 3, c] += Fp
    F = Fn - _somar_nos_graus(lt, ndof, _forcas_para_global(lt, f0c))
    # apoios
    fixos = set()
    for ap in M["apoios"]:
        no = ap["no"]
        fixos.update(range(6 * no, 6 * no + (6 if ap["tipo"] == "engastada" else 3)))
    # graus sem rigidez (nó só de barras rotuladas): presos, com aviso
    diag = np.zeros(ndof)
    np.add.at(diag, lt["dofs"].reshape(-1), np.einsum("nii->ni", Kg).reshape(-1))
    escala = float(np.max(np.abs(diag))) if len(diag) else 1.0
    com_barra = {br["a"] for br in barras} | {br["b"] for br in barras}
    soltos = [d for d in np.where(np.abs(diag) < 1e-9 * escala)[0].tolist() if d not in fixos]
    soltos_reais = [d for d in soltos if d // 6 in com_barra]
    fixos.update(soltos)
    mascara = np.ones(ndof, bool)
    mascara[list(fixos)] = False
    livres = np.where(mascara)[0]
    mont = _Montador(lt["dofs"], ndof, livres)
    U = np.zeros((ndof, nc))
    instavel = None
    try:
        lu = splu(mont.matriz(Kg))
        U[livres] = lu.solve(F[livres])
    except RuntimeError as e:
        instavel = str(e)
    if instavel is None and _sem_limite(U):
        instavel = "deslocamentos sem limite (mecanismo)"
    # esforços nas pontas (local), por caso: f = k·u + f0, com os giros soltos recuperados (dão momento zero)
    ul = _deslocamentos_locais(lt, U)
    _recuperar_soltos(ul, f0, rec)
    pontas = np.einsum("nij,njc->nci", k, ul) + f0
    R_all = _somar_nos_graus(lt, ndof, _forcas_para_global(lt, pontas)) - Fn
    reac = {int(ap["no"]): R_all[6 * ap["no"]:6 * ap["no"] + 6] for ap in M["apoios"]}
    ctx = {"lote": lt, "k": k, "f0": f0, "w_loc": w_loc, "Fn": Fn, "livres": livres, "montador": mont, "ndof": ndof}
    return {"casos": nomes, "U": U, "reacoes": reac, "pontas": pontas, "w": w_loc, "instavel": instavel,
            "graus_presos": len(soltos_reais), "_ctx": ctx}


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


def esforcos_lote(f: np.ndarray, w: np.ndarray, X: np.ndarray) -> np.ndarray:
    """(n, S, 6): N, Vy, Vz, T, My, Mz de todas as barras nas seções X (n, S) — o esforcos_em em lote; f = as forças da
    ponta a (n, ≥6, local) e w = a carga distribuída local (n, 3)"""
    Fx, Fy, Fz, Mx, My, Mz = (f[:, k, None] for k in range(6))
    wx, wy, wz = (w[:, k, None] for k in range(3))
    return np.stack([-(Fx + wx * X), -(Fy + wy * X), -(Fz + wz * X), -Mx + 0 * X,
                     -(My + X * Fz + wz * X * X / 2), -(Mz - X * Fy - wy * X * X / 2)], axis=2)


def fatores_da(comb: dict, nomes: Sequence[str]) -> np.ndarray:
    idx = {c: k for k, c in enumerate(nomes)}
    fat = np.zeros(len(nomes))
    for c, v in comb["fatores"].items():
        if c in idx:
            fat[idx[c]] = v
    return fat


def estacoes(M: dict) -> np.ndarray:
    """(n, S): as seções de cálculo ao longo de cada barra (m)"""
    return np.array([br["L"] for br in M["barras"]], float)[:, None] * np.linspace(0.0, 1.0, ESTACOES)[None, :]


def esforcos_da_combinacao(M: dict, sol: dict, comb_nome: str, comb: dict, so2: Optional[dict] = None):
    """as forças da ponta a (n, 12) e a carga local (n, 3) de uma combinação: as da 2ª ordem quando houver (ELU), senão
    a superposição dos casos"""
    fat = fatores_da(comb, sol["casos"])
    w = np.einsum("c,ncj->nj", fat, sol["w"])
    s2 = (so2 or {}).get(comb_nome) or {}
    if s2.get("pontas") is not None:
        return s2["pontas"], w
    return np.einsum("c,ncj->nj", fat, sol["pontas"]), w


def resultados(M: dict, casos: Dict[str, dict], sol: dict, combs: Dict[str, dict], so2: Optional[dict] = None) -> dict:
    """por combinação: o pico de cada esforço por barra, a tensão máxima e onde, as reações e os deslocamentos — nas ELU
    com a 2ª ordem (`so2`, nucleo3d/segunda_ordem.py) quando ela foi feita; e a envoltória ELU por barra"""
    barras = M["barras"]
    n = len(barras)
    fy = float(M["par"].get("fy_mpa") or 345.0)
    X = estacoes(M)
    L = X[:, -1]
    A = np.array([br["sec"]["A"] for br in barras])[:, None]
    Wz = np.array([br["sec"]["Wz"] for br in barras])[:, None]
    Wy = np.array([br["sec"]["Wy"] for br in barras])[:, None]
    lin = np.arange(n)
    por_comb: Dict[str, dict] = {}
    for cn, cb in combs.items():
        fat = fatores_da(cb, sol["casos"])
        s2 = (so2 or {}).get(cn) or {}
        f, w = esforcos_da_combinacao(M, sol, cn, cb, so2)
        if s2.get("pontas") is not None:
            U, reac = s2["U"], s2["reacoes"]
        else:
            U, reac = sol["U"] @ fat, {no: (r @ fat) for no, r in sol["reacoes"].items()}
        e = esforcos_lote(f, w, X)
        sig = (np.abs(e[..., 0]) / A + np.abs(e[..., 5]) / Wz + np.abs(e[..., 4]) / Wy) / 1000.0     # MPa
        k = np.argmax(sig, axis=1) if n else np.zeros(0, int)
        arr = np.column_stack([np.round(e[..., 0].min(1), 2), np.round(e[..., 0].max(1), 2),
                               np.round(np.hypot(e[..., 1], e[..., 2]).max(1), 2), np.round(np.hypot(e[..., 4], e[..., 5]).max(1), 3),
                               np.round(sig[lin, k], 1), np.round(X[lin, k] / L, 2)]) if n else np.zeros((0, 6))
        esf = np.column_stack([np.round(e[lin, k, 0], 2), np.round(e[lin, k, 5], 3), np.round(e[lin, k, 4], 3)]) if n else np.zeros((0, 3))
        por_comb[cn] = {"desl_mm": np.round(U.reshape(-1, 6)[:, :3] * 1000, 2), "reacoes": reac, "barras": arr, "esf": esf,
                        "segunda_ordem": s2.get("pontas") is not None}
    # envoltória e ranking (ELU)
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    env = []
    if elu and n:
        S = np.stack([por_comb[c]["barras"][:, 4] for c in elu])                 # (ne, n)
        melhor = np.argmax(S, axis=0)
        Nmin = np.min(np.stack([por_comb[c]["barras"][:, 0] for c in elu]), axis=0)
        Nmax = np.max(np.stack([por_comb[c]["barras"][:, 1] for c in elu]), axis=0)
        Vmax = np.max(np.stack([por_comb[c]["barras"][:, 2] for c in elu]), axis=0)
        Mmax = np.max(np.stack([por_comb[c]["barras"][:, 3] for c in elu]), axis=0)
        for i in range(n):
            c = elu[int(melhor[i])]
            s = float(por_comb[c]["barras"][i, 4])
            env.append({"sigma": s, "taxa": round(s / fy, 3), "comb": c, "N": [float(Nmin[i]), float(Nmax[i])], "M": float(Mmax[i]),
                        "esf": [float(v) for v in por_comb[c]["esf"][i]], "V": float(Vmax[i])})
    else:
        env = [{"sigma": 0.0, "taxa": 0.0, "comb": None, "N": [0.0, 0.0], "M": 0.0, "esf": [0.0, 0.0, 0.0], "V": 0.0} for _ in range(n)]
    return {"por_comb": por_comb, "envoltoria": env}


# ------------------------------------------------------------------ o cálculo inteiro

def calcular(doc, par: Optional[dict] = None) -> dict:
    """a análise; com a cobertura retrátil, as duas situações (aberta e retraída) e a envoltória das reações das duas"""
    P = dict(PARAMETROS_PADRAO, **(par or {}))
    # o modelo de concreto (o IFC do pré-moldado): a análise global dele
    from nucleo3d import analise_premoldado as AP
    if P.get("modelo_analise") == "premoldado" or (P.get("modelo_analise", "auto") == "auto" and AP.e_premoldado(doc)):
        return AP.calcular(doc, P)
    if not P.get("cobertura_movel"):
        r = _calcular_situacao(doc, P)
        r["reacoes_envoltoria"] = envoltoria_das_reacoes({"": r})
        r["ancoragens"] = ancoragens({"": r})
        r["grupos_perfis"] = grupos_de_perfis(r)
        r["bases"] = _bases({"": r}, P)
        r["ligacoes_topo"] = _ligacoes_topo({"": r}, P)
        return r
    r_a = _calcular_situacao(doc, dict(P, configuracao="aberta"))
    r_r = _calcular_situacao(doc, dict(P, configuracao="retraida"))
    r_a["situacao"] = "aberta"
    r_r["situacao"] = "retraida"
    r_a["outras_situacoes"] = {"retraida": r_r}
    r_a["reacoes_envoltoria"] = envoltoria_das_reacoes({"aberta": r_a, "retraida": r_r})
    r_a["ancoragens"] = ancoragens({"aberta": r_a, "retraida": r_r})
    r_a["grupos_perfis"] = grupos_de_perfis(r_a, [r_r])
    r_a["bases"] = _bases({"aberta": r_a, "retraida": r_r}, P)
    r_a["ligacoes_topo"] = _ligacoes_topo({"aberta": r_a, "retraida": r_r}, P)
    return r_a


def _ligacoes_topo(sits: Dict[str, dict], P: dict) -> Optional[List[dict]]:
    """a viga apoiada no topo do pilar por duas chapas parafusadas (nucleo/ligacao_topo_pilar.py)"""
    if any(r.get("instavel") for r in sits.values()):
        return None
    from nucleo3d import bases_analise as BA
    return BA.ligacoes_no_topo(sits, P)


def _bases(sits: Dict[str, dict], P: dict) -> Optional[List[dict]]:
    """as bases dos pilares pela NBR 8800:2024, 6.7, com as reações concomitantes (nucleo3d/bases_analise.py)"""
    if any(r.get("instavel") for r in sits.values()):
        return None
    from nucleo3d import bases_analise as BA
    return BA.dimensionar_bases(sits, P)


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


def ancoragens(sits: Dict[str, dict]) -> List[dict]:
    """O que a estrutura aplica em cada ponto chumbado num pilar de concreto (Docas, 08/10), nas combinações últimas: a
    força sobre o pilar (o contrário da reação) na face dele — T, o arrancamento (puxa a ancoragem para fora da face;
    negativo empurra contra ela), Vz o cisalhamento vertical (para baixo positivo), Vh o horizontal ao longo da face, V a
    resultante dos dois e M o momento (o nó engastado). Cada extremo com a combinação e os concomitantes [T, Vz, Vh, M]."""
    por: Dict[str, dict] = {}
    for nome, r in sits.items():
        elu = [c for c, cb in r["combinacoes"].items() if cb["tipo"] == "ELU"]
        for ap in r["apoios"]:
            if not ap.get("chumbada"):
                continue
            n = np.array(ap.get("normal") or (0.0, 0.0, 0.0), float)
            if np.linalg.norm(n) < 0.5:
                continue
            th = np.array([-n[1], n[0], 0.0])
            k = ap["chave"]
            e = por.setdefault(k, {"chave": k, "pilar": ap["chumbada"], "z": ap.get("z"), "no": ap["no"], "tipo": ap["tipo"],
                                    "T_max": [-1e18, ""], "C_max": [0.0, ""], "V_max": [0.0, ""], "M_max": [0.0, ""],
                                    "concomitantes": {}})
            for c in elu:
                rr = r["por_comb"][c]["reacoes"].get(str(ap["no"]))
                if rr is None:
                    continue
                F = -np.array(rr[:3], float)                 # o que a estrutura faz no pilar
                Mm = float(np.linalg.norm(np.array(rr[3:6], float)))
                T, Vz, Vh = float(F @ n), float(-F[2]), float(F @ th)
                V = math.hypot(Vz, Vh)
                onde = ("%s · %s" % (nome, c)) if nome else c
                conc = [round(T, 2), round(Vz, 2), round(Vh, 2), round(Mm, 2)]
                for chave, val in (("T_max", T), ("C_max", -T), ("V_max", V), ("M_max", Mm)):
                    if val > e[chave][0]:
                        e[chave] = [val, onde]
                        e["concomitantes"][chave] = conc
    for e in por.values():
        for k in ("T_max", "C_max", "V_max", "M_max"):
            e[k][0] = round(e[k][0], 2)
    return sorted(por.values(), key=lambda e: (e["pilar"], -(e["z"] or 0.0)))


def apoios_das_tesouras(M: dict, sol: dict, combs: Dict[str, dict], so2: Optional[dict] = None) -> Optional[dict]:
    """o que cada tesoura entrega onde apoia (na viga-trilho, pelo carrinho, ou no pilar): a soma das forças das barras da
    tesoura no nó de apoio, no eixo global, por combinação última — vertical (compressão no apoio positiva, arrancamento
    negativa), horizontal transversal (no vão da tesoura) e longitudinal (ao longo do trilho). É o que se pede ao
    fabricante do carrinho: ele segura o arrancamento e as forças horizontais? (etapa 5, 07/10)"""
    nos, barras = M["nos"], M["barras"]
    no_bar: Dict[int, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        no_bar[br["a"]].append(i)
        no_bar[br["b"]].append(i)
    apoios = []
    for no, bs in no_bar.items():
        # o conjunto que apoia: a tesoura e o que vai junto com ela (a sanfona da cobertura retrátil) — tudo o que chega no
        # nó e não é a viga ou o pilar
        trel = [i for i in bs if barras[i].get("elemento") == "trelica"]
        if trel and any(barras[i]["papel"] in ("viga", "pilar") for i in bs):
            junto = [i for i in bs if barras[i]["papel"] not in ("viga", "pilar")]
            apoios.append((no, barras[trel[0]].get("grupo") or "", junto))
    if not apoios:
        return None
    mv = M.get("movel")
    if mv:
        u = np.array(list(mv["u"]) + [0.0])
        nd = np.array(list(mv["n_dir"]) + [0.0])
    else:
        dirs = [_unit((nos[barras[i]["b"]] - nos[barras[i]["a"]]) * np.array([1, 1, 0])) for i, br in enumerate(barras)
                if br.get("papel_trelica") in ("banzo_inf", "banzo_sup")]
        u = _unit(np.mean([d if d[0] + 1e-3 * d[1] >= 0 else -d for d in dirs], axis=0)) if dirs else np.array([1.0, 0, 0])
        nd = np.array([-u[1], u[0], 0.0])
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    R = np.array([br["R"] for br in barras])
    lista = []
    for no, g, tr_ in apoios:
        reg = {"grupo": g, "no": int(no), "xy": [round(float(nos[no][0]), 3), round(float(nos[no][1]), 3)],
               "Fv_max": [-1e18, ""], "Fv_min": [1e18, ""], "Ht_max": [0.0, ""], "Hl_max": [0.0, ""]}
        for c in elu:
            s2 = (so2 or {}).get(c) or {}
            if s2.get("pontas_nos") is not None:
                P = s2["pontas_nos"]
            else:
                P = np.einsum("c,ncj->nj", fatores_da(combs[c], sol["casos"]), sol["pontas"])
            F = np.zeros(3)
            for i in tr_:
                f = P[i][0:3] if barras[i]["a"] == no else P[i][6:9]
                F -= R[i].T @ f                        # a força da barra sobre o nó (global)
            Fv, Ht, Hl = -float(F[2]), float(F @ u), float(F @ nd)
            if Fv > reg["Fv_max"][0]:
                reg["Fv_max"] = [Fv, c]
            if Fv < reg["Fv_min"][0]:
                reg["Fv_min"] = [Fv, c]
            if abs(Ht) > abs(reg["Ht_max"][0]):
                reg["Ht_max"] = [Ht, c]
            if abs(Hl) > abs(reg["Hl_max"][0]):
                reg["Hl_max"] = [Hl, c]
        for k in ("Fv_max", "Fv_min", "Ht_max", "Hl_max"):
            reg[k][0] = round(reg[k][0], 2)
        lista.append(reg)
    env = {k: max(lista, key=(lambda r, k=k: r[k][0] if k != "Fv_min" else -r[k][0]) if k in ("Fv_max", "Fv_min")
                  else (lambda r, k=k: abs(r[k][0])))
           for k in ("Fv_max", "Fv_min", "Ht_max", "Hl_max")}
    return {"apoios": lista, "pior": {k: {"valor": v[k][0], "comb": v[k][1], "grupo": v["grupo"], "xy": v["xy"]} for k, v in env.items()},
            "n": len(lista)}


def ligacoes_viga_pilar(M: dict, sol: dict, combs: Dict[str, dict], so2: Optional[dict] = None) -> Optional[List[dict]]:
    """os esforços de cálculo nas pontas das vigas que chegam em pilares — o que a ligação viga–pilar transmite, nas
    combinações últimas (2ª ordem): por ligação, o maior momento (eixo forte e fraco), o maior cortante e a maior normal
    de tração e de compressão, cada um com os outros esforços da MESMA combinação (concomitantes). O detalhe da ligação
    (soldada, chapa de topo, cantoneiras) depende do projeto; com ele, a conta é a de nucleo/ligacoes.py (etapa 5, 07/10)"""
    nos, barras = M["nos"], M["barras"]
    pil = collections.defaultdict(list)
    for i, br in enumerate(barras):
        if br["papel"] == "pilar":
            pil[br["a"]].append(i)
            pil[br["b"]].append(i)
    pontas = [(i, k, no) for i, br in enumerate(barras) if br["papel"] == "viga" for k, no in ((0, br["a"]), (1, br["b"])) if no in pil]
    if not pontas:
        return None
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    idx = np.array([i for i, _k, _n in pontas], int)
    L = np.array([barras[i]["L"] for i in idx])
    lig: Dict[tuple, dict] = {}
    for c in elu:
        f, w = esforcos_da_combinacao(M, sol, c, combs[c], so2)
        X = np.stack([np.zeros(len(idx)), L], axis=1)
        e = esforcos_lote(f[idx], w[idx], X)                     # (n, 2, 6)
        for j, (i, k, no) in enumerate(pontas):
            N, Vy, Vz, T, My, Mz = (float(v) for v in e[j, k])
            reg = lig.setdefault((i, no), {"viga": i, "no": int(no), "perfil_viga": barras[i]["perfil"], "marca": barras[i].get("marca"),
                                           "perfil_pilar": barras[pil[no][0]]["perfil"],
                                           "xyz": [round(float(v), 3) for v in nos[no]], "max": {}})
            conc = {"comb": c, "N": round(N, 2), "V": round(math.hypot(Vy, Vz), 2), "Mz": round(Mz, 3), "My": round(My, 3), "T": round(T, 3)}
            for chave, val in (("Mz", abs(Mz)), ("My", abs(My)), ("V", math.hypot(Vy, Vz)), ("Nt", max(N, 0.0)), ("Nc", max(-N, 0.0))):
                if val > reg["max"].get(chave, [-1.0])[0]:
                    reg["max"][chave] = [round(val, 3), conc]
    return sorted(lig.values(), key=lambda r: -r["max"].get("Mz", [0.0])[0])


def topos_dos_pilares(M: dict, sol: dict, combs: Dict[str, dict], so2: Optional[dict] = None) -> List[dict]:
    """os topos de pilar onde chega viga: por combinação última, o que o pilar entrega à ligação (os esforços internos no
    topo, concomitantes: N > 0 compressão, Mz no eixo forte, My no fraco, V, T), a viga que apoia, se ela é contínua
    sobre o pilar e em que direção da seção do pilar ela corre (x = a altura da seção, y = a largura)"""
    nos, barras = M["nos"], M["barras"]
    no_bar: Dict[int, List[int]] = collections.defaultdict(list)
    for i, br in enumerate(barras):
        no_bar[br["a"]].append(i)
        no_bar[br["b"]].append(i)
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    pares = []
    for no, bs in no_bar.items():
        vigas = [i for i in bs if barras[i]["papel"] == "viga"]
        pil = [i for i in bs if barras[i]["papel"] == "pilar" and max(nos[barras[i]["a"]][2], nos[barras[i]["b"]][2]) <= nos[no][2] + 1e-6]
        if vigas and pil:
            pares.append((no, pil[0], vigas))
    if not pares:
        return []
    forcas = {c: esforcos_da_combinacao(M, sol, c, combs[c], so2) for c in elu}
    saida = []
    for no, ip, vigas in pares:
        bp = barras[ip]
        x = bp["L"] if bp["b"] == no else 0.0
        ey = bp["R"][1]
        v0 = barras[vigas[0]]
        dv = nos[v0["b"]] - nos[v0["a"]]
        ids = [barras[i]["ids"][0] if barras[i].get("ids") else None for i in vigas]
        continua = len(vigas) >= 2 and ids[0] is not None and ids.count(ids[0]) >= 2
        reg = {"no": int(no), "xyz": [round(float(v), 3) for v in nos[no]], "pilar": bp["perfil"], "viga": v0["perfil"],
               "viga_continua": bool(continua), "viga_ao_longo": "x" if abs(float(_unit(dv) @ ey)) >= 0.7 else "y",
               "pilar_chave": chave_do_pilar(nos, bp), "combinacoes": []}
        for c in elu:
            f, w = forcas[c]
            e = esforcos_lote(f[ip:ip + 1], w[ip:ip + 1], np.array([[x]]))[0, 0]
            reg["combinacoes"].append({"comb": c, "N": round(-float(e[0]), 2), "V": round(float(math.hypot(e[1], e[2])), 2),
                                       "T": round(float(e[3]), 3), "My": round(float(e[4]), 3), "Mz": round(float(e[5]), 3)})
        # as pontas de viga que terminam no nó (a viga emendada sobre o pilar): o que cada uma entrega à ligação, nos eixos
        # dela — N > 0 comprimindo os parafusos (a reação vertical), M_forte (o vetor de través: binário ao longo da viga),
        # M_tor (o vetor ao longo: binário de través), T (vertical: torção do grupo) e V (horizontal)
        if not continua:
            reg["pontas_viga"] = []
            z = np.array([0.0, 0.0, 1.0])
            for iv in vigas:
                bv = barras[iv]
                lado = slice(0, 6) if bv["a"] == no else slice(6, 12)
                outro = bv["b"] if bv["a"] == no else bv["a"]
                el = _unit((nos[outro] - nos[no]) * np.array([1.0, 1.0, 0.0]))
                et = np.cross(z, el)
                pv = {"viga": bv["perfil"], "combinacoes": []}
                for c in elu:
                    s2 = (so2 or {}).get(c) or {}
                    P = s2["pontas_nos"] if s2.get("pontas_nos") is not None else np.einsum("c,ncj->nj", fatores_da(combs[c], sol["casos"]), sol["pontas"])
                    fl = P[iv][lado]
                    F = -(bv["R"].T @ fl[:3])          # a força da viga sobre o nó (global)
                    Mv = -(bv["R"].T @ fl[3:6])
                    pv["combinacoes"].append({"comb": c, "N": round(-float(F @ z), 2), "Mz": round(float(Mv @ et), 3),
                                              "My": round(float(Mv @ el), 3), "T": round(float(Mv @ z), 3),
                                              "V": round(float(math.hypot(F @ el, F @ et)), 2)})
                reg["pontas_viga"].append(pv)
        saida.append(reg)
    return saida


def _calcular_situacao(doc, par: Optional[dict] = None, montador=None, carregador=None, combinador=None) -> dict:
    """modelo → cargas → combinações → resolver → resultados, no formato que a tela de análise lê (JSON). O montador, as
    cargas e as combinações podem vir de fora (a análise global do pré-moldado, nucleo3d/analise_premoldado.py)"""
    M = (montador or montar)(doc, par)
    casos, info, av_c = (carregador or cargas)(M)
    combs = combinador(list(casos)) if combinador else combinacoes(casos)
    sol = resolver(M, casos)
    avisos = list(M["avisos"]) + av_c
    if sol["instavel"]:
        avisos.insert(0, ("A estrutura está instável (%s): falta travamento — contraventamento, base engastada ou ligação "
                          "viga–pilar rígida. Os resultados não valem.") % sol["instavel"])
    if sol["graus_presos"]:
        avisos.append("%d grau(s) de liberdade sem rigidez foram presos (nós só de barras rotuladas)" % sol["graus_presos"])
    so2: Dict[str, dict] = {}
    if M["par"].get("segunda_ordem", True) and not sol["instavel"]:
        from nucleo3d import segunda_ordem as SO
        so2 = SO.analisar(M, sol, combs)
        rs = SO.resumo(so2)
        if rs and rs["classe"] == "grande":
            # grande deslocabilidade pelo procedimento simplificado: as imperfeições também nas de vento (4.10.7.2)
            so2 = SO.analisar(M, sol, combs, nocionais_no_vento=True)
            avisos.insert(0, "2ª ordem: grande deslocabilidade — as forças nocionais entraram também nas combinações com vento "
                             "(NBR 8800:2024, 4.10.7.2, procedimento simplificado)")
        combs = SO.combinacoes_da_analise(combs, so2)
        inst = [c for c, r in so2.items() if r.get("instavel")]
        if inst:
            avisos.insert(0, ("2ª ordem: instabilidade global em %d combinação(ões) — %s (%s). Nelas valem só os esforços de "
                              "1ª ordem, que não bastam: falta rigidez lateral (contraventamento) ou a carga passou da crítica")
                          % (len(inst), ", ".join(inst), so2[inst[0]]["instavel"]))
        rs = SO.resumo(so2)
        if rs and rs["classe"] == "grande":
            avisos.insert(0, ("2ª ordem: deslocabilidade GRANDE (Δ2/Δ1 até %.2f em %s; NBR 8800:2024, 4.10.4: acima de 1,40) — a "
                              "norma pede análise rigorosa com as não linearidades ou, a critério do responsável, o "
                              "procedimento simplificado com as imperfeições somadas ao vento (4.10.7.2, feito aqui). A "
                              "estrutura precisa de mais rigidez lateral") % (rs["razao_max"], rs["comb_razao_max"]))
    res = resultados(M, casos, sol, combs, so2)
    nos, barras = M["nos"], M["barras"]
    ver = None
    if not sol["instavel"]:
        from nucleo3d import verificacao_pecas as VP
        ver = VP.verificar(M, sol, combs, so2)
        ver["grupos"] = VP.por_grupo(ver, barras)
        avisos.extend(ver.get("avisos") or [])
        nao = [pc for pc in ver["pecas"] if (pc.get("uso") or 0) > 1.0 and not pc.get("hipotese")]
        if nao:
            pior = max(nao, key=lambda p: p["uso"])
            avisos.insert(0, ("verificação pela norma: %d peça(s) acima de 100%% da resistência de cálculo — a pior: %s %s com %.0f%% "
                              "(%s, %s)") % (len(nao), pior["papel"], pior["perfil"], pior["uso"] * 100, pior.get("verif"),
                                             pior.get("comb") or "—"))
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
    contornos: Dict[str, Optional[list]] = {}
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
                    **({"concreto": True} if br["sec"].get("concreto") else {}),
                    **({"pilar": chave_do_pilar(nos, br), "secao": _secao_desenho(br["perfil"], contornos), "giro": br.get("giro", 0.0)}
                       if br["papel"] == "pilar" else {}),
                    **({"perfil_original": br["perfil_original"]} if br.get("perfil_original") else {})}
                   for br in barras],
        "casos": {nome: {"descricao": casos[nome].get("descricao", nome),
                         **({"sentido_vertical": casos[nome]["sentido_vertical"], "Fz_kN": casos[nome].get("Fz_kN")}
                            if casos[nome].get("sentido_vertical") else {}),
                         "nodal": {str(i): np.round(v, 4).tolist() for i, v in casos[nome]["nodal"].items()},
                         "nos": {str(i): np.round(v, 4).tolist() for i, v in (casos[nome].get("nos") or {}).items()},
                         "dist": {str(i): np.round(v, 4).tolist() for i, v in casos[nome]["dist"].items()}}
                  for nome in nomes},
        # por barra e caso: as forças da ponta a (local) e a carga distribuída local — o diagrama de qualquer combinação
        "pontas": np.round(sol["pontas"][:, :, :6], 3).tolist(),
        "w_local": np.round(sol["w"], 4).tolist(),
        # as combinações últimas com a 2ª ordem: as forças da ponta a (local) de cada barra — o diagrama usa estas
        "pontas2": {c: np.round(r["pontas"][:, :6], 3).tolist() for c, r in so2.items() if r.get("pontas") is not None},
        "segunda_ordem": ({"combinacoes": SO.para_json(so2), "resumo": SO.resumo(so2)} if so2 else None),
        "verificacao": ver,
        "apoios_tesouras": apoios_das_tesouras(M, sol, combs, so2) if not sol["instavel"] else None,
        "ligacoes": ligacoes_viga_pilar(M, sol, combs, so2) if not sol["instavel"] else None,
        "topos_pilares": topos_dos_pilares(M, sol, combs, so2) if not sol["instavel"] else None,
        "combinacoes": combinacoes_json(combs),
        # por combinação: os deslocamentos, as reações e a tensão máxima de cada barra (o mapa)
        "por_comb": {c: {"desl_mm": np.round(v["desl_mm"], 1).tolist(),
                         "reacoes": {str(n): np.round(r, 2).tolist() for n, r in v["reacoes"].items()},
                         "sigma": v["barras"][:, 4].tolist(), **({"segunda_ordem": True} if v.get("segunda_ordem") else {})}
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
