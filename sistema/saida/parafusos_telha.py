# -*- coding: utf-8 -*-
"""Parafusos de telha pela contagem do 3D (regra COM-05, usuário 09/11/2026).

- OA (onda alta, telha × terça pela crista): 2.3/8" na cobertura em telha simples; sanduíche PIR 30 → 4", PIR 50 → 5",
  isopainel → 2". OB (onda baixa) 3/4" no fechamento em telha simples, na TP25 e no forro. Fechamento em sanduíche: pendência
  (perguntar ao usuário), sem comprimento chutado.
- Quantidade pela contagem do 3D, cada telha × cada apoio (terça ou longarina em que ela encosta), com as fixações por telha
  decididas pelo usuário em 09/11 (critério C do "é assim?" da FÁBRICA, para todas as obras; o caso B da Sooro — 5 nas
  pontas, 2,5 no meio — ficou de fora): 3 por telha em cada apoio, na cobertura (OA, terça) e no fechamento e no forro (OB,
  longarina). O recorte sem apoio conta 1 apoio; a telha estreita, proporcional à largura útil (TP40: 5 cristas, passo 196,
  útil 0,98). Na emenda de duas telhas sobre a mesma terça, cada telha conta a dela.
- Costura 7/8" = (OA + OB) ÷ 4 por cor, sem o isopainel. Arredonda: OA e OB para cima no múltiplo de 50; costura no de 5.
- Cabeça sempre na cor da telha (galvalume/natural → natural). Um lote de OA/OB/costura por cor.
- Conferência (aviso, sem trava): nas linhas com ≥ 1.000 ml, OA fora de ±30 % de 2,4 pç/ml (simples) ou 2,0 (PIR) e OB fora
  de ±30 % de 3,0 pç/ml.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

#: Fixações por telha em cada apoio (usuário, 09/11, critério C para todas as obras): 3 em toda terça — a do beiral, a da
#: cumeeira e as do meio — e 3 em toda longarina do fechamento e do forro.
FIX_PONTA = 3.0
FIX_MEIO = 3.0
FIX_FECHAMENTO = 3.0
#: Pedaços da mesma faixa de telha (o beiral curvo R450 que o IFC parte em facetas, a telha cortada): a mesma posição na
#: largura (até isto, mm) e encostados ponta com ponta (até FOLGA_FAIXA mm).
MESMA_FAIXA = 100.0
FOLGA_FAIXA = 30.0
#: Só a faceta e a ponta da cumeeira (menos de 0,5 m) se juntam à vizinha: duas telhas que se encostam (o forro de 0,96 m ao
#: lado do outro ou do oitão, a cumeeira, a emenda) são duas telhas. A saia em pé do beiral curvo chega à faixa pelas facetas.
PEDACO_ML = 0.5
#: A largura útil da telha (TP40: 5 cristas de 196 mm): a telha mais estreita (recorte) leva a parte proporcional.
LARGURA_UTIL = 980.0
#: A costura é ¼ da fixação (53 de 75 casos da Hermes).
COSTURA_FRACAO = 0.25
ARRED_FIXACAO = 50
ARRED_COSTURA = 5
#: Mediana Hermes (obras ≥ 1.000 ml) para o aviso, por (tipo, comprimento).
MEDIANA_HERMES = {("OA", '2.3/8"'): 2.4, ("OA", '4"'): 2.0, ("OA", '5"'): 2.0, ("OB", '3/4"'): 3.0}
MARGEM_AVISO = 0.30
ML_AVISO = 1000.0
#: O apoio encosta na telha: a face da peça a até isto (mm) do plano do meio da telha; o eixo dela a até 260 mm (meia W250 +
#: a onda) — o critério do contar_apoios_telhas.py da Sooro (aprovado nas duas obras, 09/11).
TOL_CONTATO = 80.0
TOL_EIXO = 260.0
#: Duas peças que cruzam a telha a menos disto (mm) ao longo dela são o mesmo apoio (terça emendada ou transpassada).
MESMO_APOIO = 120.0

_RE_TELHA = re.compile(r"\bTELHA\b|^\s*T[PR]\s*-?\s*\d{2}\b|ISOPAINEL|ISOTELHA|SANDU[IÍ]CHE", re.I)
_RE_NAO_APOIO = re.compile(r"corrente|tirante|contravent|chumbador|parafuso|barra_roscada|gancho|\bRufos?\b|\bCalhas?\b", re.I)
#: Barra redonda (tirante, corrente) não é apoio de telha. A cantoneira é (a L 50×50 que segura o forro do beiral da Sala de
#: Compressores); a que não encosta na telha fica de fora pelo contato.
_RE_PERFIL_NAO_APOIO = re.compile(r"^\s*(BR\b|BR\d|FE\b|FE\s|Barra redonda)", re.I)


def arredondar(n: float, passo: int) -> int:
    return int(math.ceil(float(n) / passo - 1e-9)) * passo if n > 0 else 0


def costura(oa: int, ob: int) -> int:
    """Costura 7/8" = (OA + OB) ÷ 4, para cima no múltiplo de 5 (Sooro Depósito Químico: (1.725 + 980) ÷ 4 = 676,25 → 680)."""
    return arredondar((int(oa) + int(ob)) * COSTURA_FRACAO, ARRED_COSTURA)


def eh_telha(e) -> bool:
    at = getattr(e, "atributos", None) or {}
    if getattr(e, "tipo", "") not in ("solido",):
        return False
    if at.get("telha_lancada") or re.search(r"telha", str(getattr(e, "camada", "") or ""), re.I):
        return True
    return bool(_RE_TELHA.search(str(getattr(e, "nome", "") or "")))


def tipo_da_telha(texto: str) -> str:
    """"pir30", "pir50", "isopainel", "sanduiche" (outra), "tp25", "simples"."""
    t = texto or ""
    if re.search(r"ISOPAINEL|\bEPS\b", t, re.I):
        return "isopainel"
    if re.search(r"PIR\s*-?\s*50", t, re.I):
        return "pir50"
    if re.search(r"PIR\s*-?\s*30", t, re.I):
        return "pir30"
    if re.search(r"PIR|PUR|SANDU[IÍ]CHE|TERMOAC|ISOTELHA", t, re.I):
        return "sanduiche"
    if re.search(r"T[PR]\s*-?\s*25\b", t, re.I):
        return "tp25"
    return "simples"


_CORES = (("branc", "branca"), ("bege", "bege"), ("cinza", "cinza"), ("pret", "preta"), ("azul", "azul"), ("verde", "verde"),
          ("vermelh", "vermelha"), ("marrom", "marrom"), ("cer[aâ]mic", "cerâmica"), ("areia", "areia"))


def cor_da_telha(texto: str) -> str:
    """A cor da cabeça do parafuso = a da telha (na sanduíche, a da face de cima — a primeira cor escrita). Galvalume, aluzinc,
    "aço nat." → natural. Sem cor no nome: "" (vira pendência)."""
    t = texto or ""
    ral = re.search(r"RAL\s*(\d{4})", t, re.I)
    nome = next((c for r, c in _CORES if re.search(r, t, re.I)), "")
    if ral:
        return ("%s RAL %s" % (nome, ral.group(1))).strip()
    if nome:
        return nome
    if re.search(r"GALVALUME|ALUZINC|ZINCALUME|NATURAL|NAT\.|A[CÇ]O\s+NAT|GALVANIZAD", t, re.I):
        return "natural"
    return ""


def _quadro(V: np.ndarray, telha: bool = False):
    c = V.mean(0)
    _u, _s, W = np.linalg.svd(V - c, full_matrices=False)
    ax_l, ax_w, nrm = W[0], W[1], W[2]
    if nrm[2] < 0:
        nrm = -nrm
    if not telha:
        return c, ax_l, ax_w, nrm
    # a largura da telha é o eixo do plano com a medida perto da largura da telha (~1 m): a faceta do beiral curvo tem 1.000 ×
    # 150 e a telha inteira 1.000 × 6.000. Quando os dois lados ficam perto de 1 m (recorte, oitão), o comprimento é o sentido
    # das ondas: o eixo que sobe; na telha plana, o mais comprido
    e_l = float(np.ptp((V - c) @ ax_l))
    e_w = float(np.ptp((V - c) @ ax_w))
    perto = lambda e: 700.0 <= e <= 1300.0                     # noqa: E731
    if perto(e_l) and not perto(e_w) and e_w < e_l:
        ax_l, ax_w = ax_w, ax_l
    elif perto(e_l) == perto(e_w) and abs(ax_w[2]) > abs(ax_l[2]) + 0.05:
        ax_l, ax_w = ax_w, ax_l
    return c, ax_l, ax_w, nrm


def _malha(e):
    from nucleo3d import geometria as G
    try:
        vs, _f = G.malha(e)
    except Exception:                                        # noqa: BLE001 — entidade sem malha
        vs = getattr(e, "vertices", None) or []
    return np.asarray(vs, dtype=float).reshape(-1, 3) if len(vs) else None


def apoios_por_telha(doc) -> List[dict]:
    """Cada telha do modelo com os apoios em que ela encosta: [{id, nome, camada, texto, uso, ml, apoios}].

    Apoio = peça linear (barra ou sólido comprido) que cruza a telha de lado (perpendicular ao comprimento dela, no plano dela)
    com a face de cima encostada na face de baixo da telha (fechamento: em uma das duas faces). Corrente, tirante,
    contraventamento e parafuso não são apoio. Duas peças a menos de 150 mm ao longo da telha contam um apoio só."""
    ents = list(doc.entidades.values()) if hasattr(doc.entidades, "values") else list(doc.entidades)
    telhas = [e for e in ents if eh_telha(e)]
    if not telhas:
        return []
    cand = []
    for e in ents:
        if eh_telha(e) or getattr(e, "tipo", "") not in ("barra", "solido"):
            continue
        at = getattr(e, "atributos", None) or {}
        txt = " ".join(str(x or "") for x in (getattr(e, "papel", ""), getattr(e, "camada", ""), getattr(e, "nome", ""),
                                               at.get("tipo_ifc")))
        if _RE_NAO_APOIO.search(txt) or re.search(r"MechanicalFastener|BuildingElementProxy|IfcPlate|IfcCovering", txt, re.I):
            continue
        perfil = str(getattr(e, "perfil", "") or (at.get("marcas") or {}).get("perfil") or getattr(e, "nome", "") or "")
        if _RE_PERFIL_NAO_APOIO.search(perfil) and not re.search(r"ter[cç]a|longarina", str(getattr(e, "papel", "") or ""), re.I):
            continue
        cand.append(e)
    # caixas das telhas para pré-filtrar as peças
    tq = []
    for t in telhas:
        V = _malha(t)
        if V is None or len(V) < 4:
            continue
        tq.append((t, V))
    if not tq:
        return []
    tlo = np.array([V.min(0) for _t, V in tq]) - 400.0
    thi = np.array([V.max(0) for _t, V in tq]) + 400.0
    glo, ghi = tlo.min(0), thi.max(0)
    pecas = []
    for e in cand:
        if getattr(e, "tipo", "") == "barra" and getattr(e, "inicio", None) and getattr(e, "fim", None):
            a, b = np.asarray(e.inicio, float), np.asarray(e.fim, float)
            lo, hi = np.minimum(a, b) - 300.0, np.maximum(a, b) + 300.0
            if np.any(hi < glo) or np.any(lo > ghi):
                continue
        V = _malha(e)
        if V is None or len(V) < 4:
            continue
        c, ax, _w, _n = _quadro(V)
        s = (V - c) @ ax
        if s.max() - s.min() < 300.0:
            continue                                        # não é linear (chapa, peça curta)
        pecas.append((e, V, c, ax, V.min(0), V.max(0)))
    if not pecas:
        return _faixas([_linha(t, V, []) for t, V in tq])
    plo = np.array([p[4] for p in pecas])
    phi = np.array([p[5] for p in pecas])
    saida = []
    for k, (t, V) in enumerate(tq):
        c, ax_l, ax_w, nrm = _quadro(V, telha=True)
        pl, pw = (V - c) @ ax_l, (V - c) @ ax_w
        larg = float(pw.max() - pw.min())
        idx = np.where(np.all(phi >= tlo[k], 1) & np.all(plo <= thi[k], 1))[0]
        posicoes = []
        for i in idx:
            e, P, pc, pax, _lo, _hi = pecas[i]
            if abs(pax @ ax_l) > 0.35 or abs(pax @ nrm) > 0.3:
                continue                                    # paralela à telha, ou fora do plano dela (montante, diagonal)
            # a barra extrudada só tem vértices nas pontas: o cruzamento pelo eixo, e a faixa da peça na normal da telha pela
            # seção (o afastamento dos vértices ao eixo), aplicada no ponto do cruzamento
            sv = (P - pc) @ pax
            s_ = np.linspace(sv.min(), sv.max(), max(2, int((sv.max() - sv.min()) / 40.0)))
            eixo = (pc - c)[None, :] + np.outer(s_, pax)
            ql, qw = eixo @ ax_l, eixo @ ax_w
            dentro = (ql > pl.min() - 40) & (ql < pl.max() + 40) & (qw > pw.min()) & (qw < pw.max())
            if not dentro.any():
                continue
            if qw[dentro].max() - qw[dentro].min() < min(150.0, 0.5 * larg):
                continue                                    # mal encosta na largura da telha
            n0 = float((pc - c) @ nrm)
            desl = (P - c) @ nrm - (n0 + sv * float(pax @ nrm))
            n_x = n0 + float(s_[dentro].mean()) * float(pax @ nrm)
            if abs(n_x) > TOL_EIXO:
                continue
            lo_, hi_ = n_x + desl.min(), n_x + desl.max()
            dist = 0.0 if lo_ <= 0.0 <= hi_ else min(abs(lo_), abs(hi_))
            if dist <= TOL_CONTATO:
                posicoes.append((float(ql[dentro].mean()), n_x > 0))
        posicoes.sort()
        apoios, acima = [], 0
        for qv, em_cima in posicoes:
            if not apoios or qv - apoios[-1] >= MESMO_APOIO:
                apoios.append(qv)
                acima += int(em_cima)
        lin = _linha(t, V, [c + qv * ax_l for qv in apoios])
        # o forro (do beiral, interno): telha deitada presa por baixo da estrutura — os apoios encostam na face de cima dela
        if lin["uso"] == "cobertura" and apoios and acima == len(apoios):
            lin["uso"] = "forro"
        saida.append(lin)
    return _faixas(saida)


def _faixas(pecas: List[dict]) -> List[dict]:
    """Junta os pedaços de telha da mesma faixa (a mesma telha, mesma direção da largura, a mesma posição na largura, e
    encostados ponta com ponta) numa telha só: os apoios são a união (o mesmo apoio a menos de 120 mm conta uma vez) e as
    pontas, o primeiro e o último apoio da faixa — a terça do beiral e a da cumeeira (Sooro Sala de Compressores: o beiral
    curvo R450 vem do IFC em facetas; 64 faixas × 8 apoios, 2 de ponta)."""
    # o recorte deitado sem apoio que encosta no forro é do forro (as pontas do forro do beiral da Sala de Compressores)
    forros = [t for t in pecas if t["uso"] == "forro"]
    for t in pecas:
        if t["uso"] == "cobertura" and not t["_apoios"] and t["_sobe"] is None and any(
                np.all(t["_lo"] <= f["_hi"] + FOLGA_FAIXA) and np.all(f["_lo"] <= t["_hi"] + FOLGA_FAIXA) for f in forros):
            t["uso"] = "forro"
    grupos = collections.defaultdict(list)
    for k, t in enumerate(pecas):
        w = t["_w"]
        if w[int(np.argmax(np.abs(w)))] < 0:
            w = -w
            t["_pw"] = -t["_pw"]                                     # a posição na largura no mesmo sentido da chave
        grupos[(t["texto"], tuple(np.round(w, 1)))].append(k)        # o uso não: a faceta em pé do beiral curvo é da faixa
    pai = list(range(len(pecas)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for ids in grupos.values():
        ids.sort(key=lambda i: pecas[i]["_pw"])
        for a_ in range(len(ids)):
            i = ids[a_]
            for b_ in range(a_ + 1, len(ids)):
                j = ids[b_]
                if pecas[j]["_pw"] - pecas[i]["_pw"] > MESMA_FAIXA:
                    break
                if pecas[i]["ml"] >= PEDACO_ML and pecas[j]["ml"] >= PEDACO_ML:
                    continue                    # duas telhas inteiras (a cumeeira, a emenda, o forro × o oitão): cada uma a sua
                ui, uj = pecas[i]["_sobe"], pecas[j]["_sobe"]
                if ui is not None and uj is not None and float(ui @ uj) < 0:
                    continue                    # sobem uma contra a outra: os dois lados da cumeeira
                if np.all(pecas[i]["_lo"] <= pecas[j]["_hi"] + FOLGA_FAIXA) and np.all(pecas[j]["_lo"] <= pecas[i]["_hi"] + FOLGA_FAIXA):
                    pai[raiz(j)] = raiz(i)
    juntas = collections.OrderedDict()
    for i in range(len(pecas)):
        juntas.setdefault(raiz(i), []).append(pecas[i])
    saida = []
    for membros in juntas.values():
        base = max(membros, key=lambda t: t["ml"])
        pts = []
        for t in membros:
            for q in t["_apoios"]:
                if all(np.linalg.norm(q - r) >= MESMO_APOIO for r in pts):
                    pts.append(q)
        n = len(pts)
        saida.append({"id": base["id"], "ids": [t["id"] for t in membros], "nome": base["nome"], "camada": base["camada"],
                      "texto": base["texto"], "uso": base["uso"], "ml": sum(t["ml"] for t in membros),
                      "largura": max(t["largura"] for t in membros), "apoios": n, "pontas": min(2, n), "pedacos": len(membros)})
    return saida


def _linha(t, V, apoios: list) -> dict:
    at = getattr(t, "atributos", None) or {}
    c, ax_l, ax_w, nrm = _quadro(V, telha=True)
    pl, pw = (V - c) @ ax_l, (V - c) @ ax_w
    texto = " ".join(str(x or "") for x in (getattr(t, "nome", ""), at.get("telha"), getattr(t, "material", ""),
                                             (at.get("propriedades") or {}).get("Steel & Graphics Common", {}).get("Profile")
                                             if isinstance(at.get("propriedades"), dict) else ""))
    cam = str(getattr(t, "camada", "") or "")
    fech = bool(at.get("fechamento")) or abs(nrm[2]) < 0.5 or bool(re.search(r"fechamento|lateral|oit[aã]o|platibanda", cam, re.I))
    forro = bool(re.search(r"forro", cam + " " + texto, re.I))
    return {"id": t.id, "nome": str(getattr(t, "nome", "") or ""), "camada": cam, "texto": texto,
            "uso": "forro" if forro else ("fechamento" if fech else "cobertura"),
            "ml": float(pl.max() - pl.min()) / 1000.0, "largura": float(pw.max() - pw.min()),
            "_apoios": list(apoios), "_w": ax_w, "_pw": float(c @ ax_w), "_lo": V.min(0), "_hi": V.max(0), "_sobe": _sobe(nrm)}


def _sobe(nrm):
    """Para onde a telha sobe, em planta (None na telha deitada sem caimento e na telha em pé)."""
    g = np.array([0.0, 0.0, 1.0]) - nrm[2] * nrm
    h = np.array([g[0], g[1], 0.0])
    if np.linalg.norm(g) < 1e-6 or np.linalg.norm(h) < 0.05 or abs(nrm[2]) > 0.999:
        return None
    return h / np.linalg.norm(h)


def fixacoes_da_telha(t: dict, tipo_parafuso: str) -> float:
    """As fixações de uma faixa de telha (critério C, usuário 09/11): 3 por apoio (OA: FIX_PONTA no primeiro e no último,
    FIX_MEIO nos do meio — hoje os dois 3; OB: FIX_FECHAMENTO = 3); o recorte sem apoio conta 1 apoio; a telha mais estreita
    que a útil, proporcional."""
    n = int(t.get("apoios") or 0)
    f = min(1.0, float(t.get("largura") or LARGURA_UTIL) / LARGURA_UTIL)
    if tipo_parafuso == "OA":
        p = min(int(t.get("pontas") or 0), n) if n else 1
        n = max(n, 1)
        return f * (FIX_PONTA * p + FIX_MEIO * (n - p))
    return f * FIX_FECHAMENTO * max(n, 1)


def parafuso_da_telha(uso: str, tipo: str) -> Tuple[Optional[str], Optional[str], str]:
    """(tipo OA/OB, comprimento, pendência) pela regra COM-05."""
    if uso == "cobertura":
        comp = {"simples": '2.3/8"', "pir30": '4"', "pir50": '5"', "isopainel": '2"'}.get(tipo)
        if tipo == "tp25":
            return "OB", '3/4"', ""
        if comp:
            return "OA", comp, ""
        return None, None, "cobertura em telha sanduíche sem a espessura do miolo (PIR 30 = 4\", PIR 50 = 5\"): perguntar ao usuário"
    if tipo in ("simples", "tp25"):
        return "OB", '3/4"', ""
    return None, None, "fechamento em telha sanduíche: o comprimento do parafuso está EM ABERTO na regra (a Hermes usou 2.3/8\", 3\" e 4\") — perguntar ao usuário"


def parafusos_de_telha(doc, telhas: Optional[List[dict]] = None, telha_dos_dados: str = "") -> dict:
    """{"linhas": [{item, tipo, comprimento, cor, descricao, qtd, apoios, telhas, ml, pc_ml}], "avisos": [...]}.

    `telhas` (opcional) = a saída de `apoios_por_telha` (para o teste e para reaproveitar a conta). `telha_dos_dados` = a
    descrição da telha nos dados do resumo ("TP40 0,50 bege RAL 1015"): a cor dela vale quando a telha do 3D não tem cor (o
    IFC da Sooro: "TELHA TP40 ESP.0.50")."""
    telhas = apoios_por_telha(doc) if telhas is None else telhas
    grupos: Dict[tuple, dict] = collections.OrderedDict()
    avisos, pend = [], collections.Counter()
    sem_apoio = collections.Counter()
    for t in telhas:
        tipo = tipo_da_telha(t["texto"])
        pf, comp, p = parafuso_da_telha(t["uso"], tipo)
        if p:
            pend[p] += 1
            continue
        cor = cor_da_telha(t["texto"]) or cor_da_telha(telha_dos_dados)
        if not t["apoios"]:
            sem_apoio[t["nome"][:60]] += 1
        g = grupos.setdefault((pf, comp, cor), {"tipo": pf, "comprimento": comp, "cor": cor, "bruto": 0, "apoios": 0, "telhas": 0,
                                                "ml": 0.0, "isopainel": tipo == "isopainel", "pir": tipo in ("pir30", "pir50")})
        g["bruto"] += fixacoes_da_telha(t, pf)
        g["apoios"] += t["apoios"]
        g["telhas"] += 1
        g["ml"] += t["ml"]
    linhas = []
    for (pf, comp, cor), g in grupos.items():
        qtd = arredondar(g["bruto"], ARRED_FIXACAO)
        cor_txt = cor or "na cor da telha (cor não informada no 3D)"
        linhas.append({"item": "%s %s" % (pf, comp), "tipo": pf, "comprimento": comp, "cor": cor,
                       "descricao": "Parafuso autobrocante %s %s – %s (com arruela de vedação)" % (pf, comp, cor_txt),
                       "qtd": qtd, "apoios": g["apoios"], "telhas": g["telhas"], "ml": g["ml"],
                       "pc_ml": g["bruto"] / g["ml"] if g["ml"] else 0.0, "isopainel": g["isopainel"]})
        med = MEDIANA_HERMES.get((pf, comp))
        if med and g["ml"] >= ML_AVISO and abs(g["bruto"] / g["ml"] / med - 1.0) > MARGEM_AVISO:
            avisos.append("COM-05: %s %s %s dá %s pç/ml (%d telhas, %s ml); a mediana Hermes é %s pç/ml (±30 %%) — conferir os "
                          "apoios das telhas" % (pf, comp, cor_txt, _n(g["bruto"] / g["ml"]), g["telhas"], _n(g["ml"], 0), _n(med, 1)))
        if not cor:
            avisos.append("COM-05: %s %s — a telha não tem a cor no 3D; o parafuso vai na cor da telha: conferir" % (pf, comp))
    # a costura por cor, sem o isopainel
    por_cor = collections.OrderedDict()
    for li in linhas:
        if not li["isopainel"]:
            por_cor[li["cor"]] = por_cor.get(li["cor"], 0) + li["qtd"]
    for cor, soma in por_cor.items():
        cor_txt = cor or "na cor da telha (cor não informada no 3D)"
        linhas.append({"item": 'Costura 7/8"', "tipo": "C", "comprimento": '7/8"', "cor": cor,
                       "descricao": "Parafuso autobrocante de costura 7/8\" – %s ((OA + OB) ÷ 4)" % cor_txt,
                       "qtd": arredondar(soma * COSTURA_FRACAO, ARRED_COSTURA), "apoios": 0, "telhas": 0, "ml": 0.0, "pc_ml": 0.0,
                       "isopainel": False})
    for p, n in pend.items():
        avisos.append("COM-05: %d telha(s) — %s" % (n, p))
    if sem_apoio:
        avisos.append("COM-05: %d telha(s) sem apoio achado no 3D (contadas como recorte, 1 apoio): %s — conferir se encostam na terça"
                      % (sum(sem_apoio.values()), ", ".join("%s (%d)" % kv for kv in sem_apoio.most_common(3))))
    return {"linhas": linhas, "avisos": avisos}


def _n(v, casas=2) -> str:
    return ("%%.%df" % casas % float(v)).replace(".", ",")
