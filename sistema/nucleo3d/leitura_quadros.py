# -*- coding: utf-8 -*-
"""Leitura do projeto recebido por quadros (plano de 01/10, etapas 3 e 4).

O operador copia cada parte do DXF do cliente (a Original) para um quadro tipado da folha
Montagem (web/cad/montagem.js): locação, terças, posição das tesouras, elevações, corte,
uma tesoura por quadro e os detalhes de ligação. Aqui cada quadro é lido de volta:

* as entidades do quadro voltam para milímetros reais, nas coordenadas da Original (a cópia
  guarda em `fonte.caixa` de onde veio) — os quadros de planta tirados do mesmo desenho caem
  uns sobre os outros sem acerto; a locação, desenhada noutro canto, é trazida pelos nomes
  dos pilares (ou pelos balões dos eixos) em comum;
* cada tipo tem o seu leitor, reaproveitando a leitura de elevação e de planta que já existe
  (`de_planta`): a tesoura vira um elemento único (banzos, montantes, diagonais, perfis), a
  locação dá pilares e eixos, as terças as linhas com sigla e a lista, a posição das tesouras
  as marcas T01… em cima das linhas, o corte e as elevações os níveis;
* a pré-análise junta o que está errado (impede o 3D) e o que é aviso (gera, mas confira),
  cada apontamento com o quadro e o ponto no papel para o clique levar até ele.

Nada aqui grava: `ler(desenho_montagem)` devolve a leitura e os apontamentos.
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional, Tuple

from nucleo3d import de_planta as dp

__all__ = ["ler", "entidades_reais", "perfil_escrito", "ler_tesoura", "ler_locacao", "ler_tercas",
           "ler_posicao_tesouras", "ler_niveis", "MARGEM"]

#: o canto do desenho dentro do quadro (o mesmo MARGEM de montagem.js: lado e topo)
MARGEM = {"lado": 8.0, "topo": 20.0, "baixo": 10.0}

#: camadas que nunca são peça (o resto é lido; o operador já limpou o quadro)
_ANOT = re.compile(r"(?i)(cota|dim\b|dimens|texto|folha|hach|defpoints|carimbo|anno|vport|legenda)")
_PECA = re.compile(r"^(?!.*(?:cota|dim\b|dimens|texto|folha|hach|defpoints|carimbo|anno|vport|legenda))", re.I)

PLANTAS = ("locacao", "tercas", "tesouras_pos")
ELEVACOES = ("elev_frontal", "elev_lateral", "elev_fundos", "corte")

ROTULO = {"locacao": "Locação", "tercas": "Posição das terças", "tesouras_pos": "Posição das tesouras",
          "elev_frontal": "Elevação frontal", "elev_lateral": "Elevação lateral", "elev_fundos": "Fundos",
          "corte": "Corte transversal", "tesoura": "Tesoura", "viga": "Viga treliçada",
          "ligacoes": "Detalhes de ligação"}

#: os quadros de peça treliçada com nome (a tesoura e a viga treliçada: viga painel, de transição, pergolado)
COM_NOME = ("tesoura", "viga")


def _rotulo(q: dict) -> str:
    r = ROTULO.get(q.get("tipo"), q.get("tipo") or "quadro")
    return ("%s %s" % (r, q["nome"])).strip() if q.get("tipo") in COM_NOME and q.get("nome") else r


# =====================================================================================
# Do papel para o real
# =====================================================================================

def _transformador(q: dict, envio: Optional[dict] = None):
    """(f, s): f leva um ponto do papel do quadro para o real (coordenadas da Original quando
    a cópia guardou de onde veio); s é a escala. Cada envio guarda a sua volta (o canto do
    desenho em relação ao canto do quadro, a escala, a caixa na Original); sem ele, vale a
    última cópia (`fonte`) no canto padrão"""
    if envio:
        s = float(envio.get("escala") or q.get("escala") or 1.0)
        cx = envio.get("caixa") or [[0.0, 0.0], [0.0, 0.0]]
        ox, oy = float(q["x"]) + float(envio.get("ox", MARGEM["lado"])), float(q["y"]) + float(envio.get("oy", -MARGEM["topo"]))
    else:
        s = float(q.get("escala") or 1.0)
        cx = ((q.get("fonte") or {}).get("caixa")) or [[0.0, 0.0], [0.0, 0.0]]
        ox, oy = float(q["x"]) + MARGEM["lado"], float(q["y"]) - MARGEM["topo"]
    bx0, by1 = float(cx[0][0]), float(cx[1][1])

    def f(p):
        return [bx0 + (p[0] - ox) * s, by1 - (oy - p[1]) * s] + list(p[2:])
    return f, s


def _para_real(e: dict, f, s: float) -> dict:
    n = dict(e)
    t = e.get("tipo")
    if t == "linha":
        n["a"], n["b"] = f(e["a"]), f(e["b"])
    elif t == "polilinha":
        n["vertices"] = [f(v) for v in e.get("vertices") or []]
    elif t in ("circulo", "arco"):
        n["centro"] = f(e["centro"])
        n["raio"] = float(e.get("raio") or 0.0) * s
    elif t == "texto":
        n["posicao"] = f(e["posicao"])
    elif t == "cota":
        n["p1"], n["p2"] = f(e["p1"]), f(e["p2"])
        if e.get("texto_pos"):
            n["texto_pos"] = f(e["texto_pos"])
        n["deslocamento"] = float(e.get("deslocamento") or 0.0) * s
    elif t == "hachura":
        n["contornos"] = [[f(p) for p in c] for c in e.get("contornos") or []]
    elif t == "chamada":
        n["alvo"], n["posicao"] = f(e["alvo"]), f(e["posicao"])
    if e.get("altura") is not None:
        n["altura_papel"] = float(e["altura"])
        n["altura"] = float(e["altura"]) * s            # mm reais (o texto de 2,5 mm em 1:50 tem 125 mm)
    return n


def entidades_reais(desenho: dict) -> Dict[str, List[dict]]:
    """{id do quadro: entidades dele em mm reais}"""
    m = ((desenho.get("metadados") or {}).get("montagem")) or {}
    qs = {q["id"]: q for q in m.get("quadros") or []}
    por_q: Dict[str, List[dict]] = collections.defaultdict(list)
    for e in desenho.get("entidades") or []:
        qid = (e.get("atributos") or {}).get("quadro")
        if qid in qs:
            por_q[qid].append(e)
    out = {}
    for qid, q in qs.items():
        padrao = _transformador(q)
        por_envio = {v.get("id"): _transformador(q, v) for v in q.get("envios") or [] if v.get("id")}
        lst = []
        for e in por_q.get(qid, []):
            f, s = por_envio.get((e.get("atributos") or {}).get("envio")) or padrao
            lst.append(_para_real(e, f, s))
        out[qid] = lst
    return out


def _para_papel(q: dict, p) -> List[float]:
    """o ponto real de volta para o papel do quadro (para o clique do apontamento): pelo envio
    cuja área na Original tem o ponto, senão pela última cópia"""
    env = None
    for v in q.get("envios") or []:
        (x0, y0), (x1, y1) = v.get("caixa") or [[0, 0], [0, 0]]
        if x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 1:
            env = v
    if env:
        s = float(env.get("escala") or 1.0)
        bx0, by1 = float(env["caixa"][0][0]), float(env["caixa"][1][1])
        ox, oy = float(q["x"]) + float(env.get("ox", MARGEM["lado"])), float(q["y"]) + float(env.get("oy", -MARGEM["topo"]))
    else:
        s = float(q.get("escala") or 1.0)
        cx = ((q.get("fonte") or {}).get("caixa")) or [[0.0, 0.0], [0.0, 0.0]]
        bx0, by1 = float(cx[0][0]), float(cx[1][1])
        ox, oy = float(q["x"]) + MARGEM["lado"], float(q["y"]) - MARGEM["topo"]
    return [round(ox + (p[0] - bx0) / s, 2), round(oy - (by1 - p[1]) / s, 2)]


# =====================================================================================
# Perfis escritos
# =====================================================================================

def perfil_escrito(s: str) -> Optional[dict]:
    """o perfil de um texto, também na grafia do Advance Steel: "U100x40#2mm" (a espessura em
    mm depois do #), "L 100x50 E=3.75mm", "Tubo 40x40x1,5" """
    from nucleo2d.reconhecer import perfil_do_texto
    t = str(s or "")
    t = re.sub(r"#\s*(\d+(?:[.,]\d+)?)\s*mm", lambda m: "x" + m.group(1).replace(".", ","), t)
    t = re.sub(r"\s*E\s*=\s*(\d+(?:[.,]\d+)?)\s*mm", lambda m: "x" + m.group(1).replace(".", ","), t)
    return perfil_do_texto(t)


#: um texto com cara de perfil ("U100x40#2", "L25x25", "2U 75x40") — se o catálogo não o reconhece, é erro
_CARA_DE_PERFIL = re.compile(r"(?i)^\s*\d?\s*(U|UE|C|L|W|I|H|TQ|TR|TB|Ø|BR|CH)\s*\d{2,3}\s*[xX×]\s*\d")


def _familia(p: dict) -> str:
    return re.sub(r"[^A-Z]", "", str(p.get("perfil") or "").upper()[:3])[:2]


# =====================================================================================
# Utilidades
# =====================================================================================

def _textos(ents):
    return [e for e in ents if e.get("tipo") == "texto" and str(e.get("texto") or "").strip()]


def _caixa(ents) -> Optional[Tuple[float, float, float, float]]:
    pts = []
    for e in ents:
        t = e.get("tipo")
        if t == "linha":
            pts += [e["a"], e["b"]]
        elif t == "polilinha":
            pts += list(e.get("vertices") or [])
        elif t in ("circulo", "arco"):
            pts.append(e["centro"])
        elif t == "texto":
            pts.append(e["posicao"])
        elif t == "cota":
            pts += [e["p1"], e["p2"]]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _ap(q: dict, nivel: str, msg: str, ponto=None, sugestao: Optional[str] = None, codigo: str = "") -> dict:
    """um apontamento da pré-análise: nivel "erro" (impede o 3D) ou "aviso" (gera, mas confira)"""
    a = {"nivel": nivel, "quadro": q.get("id"), "rotulo": _rotulo(q), "msg": msg, "codigo": codigo}
    if ponto is not None:
        a["real"] = [round(ponto[0], 1), round(ponto[1], 1)]
        a["papel"] = _para_papel(q, ponto)
    if sugestao:
        a["sugestao"] = sugestao
    return a


def _num(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", str(s)) \
            else float(str(s).replace(",", "."))
    except ValueError:
        return None


# =====================================================================================
# Tesoura: um elemento único
# =====================================================================================

_RX_QTD = re.compile(r"(?i)[-–(\s]\s*(\d{1,3})\s*x\s*\)?\s*$")
#: a quantidade no meio do título, seguida de uma nota ("VP1 - 01X - cuidar lado da cantoneira")
_RX_QTD_MEIO = re.compile(r"(?i)[-–(]\s*(\d{1,3})\s*x\s*\)?\s*[-–]")
_RX_NOME_T = re.compile(r"(?i)\b(T|TS|TR|TES|DP|VT|V\.?\s*T|V\.?\s*P)\s*[-.]?\s*(\d{1,3}[A-Z]?)\b")


def _norm_marca(s: str) -> str:
    """"T 05", "T-5", " T05" → "T05"; "V.P 01" → "VP01" """
    s = dp._sem_acento(str(s or "")).upper().strip()
    m = re.match(r"^([A-Z]{1,3})\.?\s*([A-Z]?)\s*[-.]?\s*(\d{1,3})([A-Z]?)$", s.replace(" .", "."))
    if not m:
        return re.sub(r"[\s.\-]", "", s)
    return "%s%s%02d%s" % (m.group(1), m.group(2), int(m.group(3)), m.group(4))


def _limpar_faixa(el) -> int:
    """o que a leitura por linhas traz e não é peça — cotas desenhadas em linha, o contorno de
    outra peça, a chamada que atravessa — sai; a linha dupla que passa da faixa dos banzos é
    cortada nela; o montante de linha dupla da ponta acima do banzo de cima é a moldura. A
    altura fica a partir do fundo da peça. (A regra acertada na portaria, 30/09.)"""
    bz = [m for m in el.membros if m.papel == "banzo"]
    if not bz:
        return 0
    hmin = min(min(m.h0, m.h1) for m in bz)
    hmax = max(max(m.h0, m.h1) for m in bz)
    smin = min(min(m.s0, m.s1) for m in bz)
    smax = max(max(m.s0, m.s1) for m in bz)
    baixo = [m for m in bz if min(m.h0, m.h1) - hmin < 60]
    b_s0 = min(min(m.s0, m.s1) for m in baixo) if baixo else smin
    b_s1 = max(max(m.s0, m.s1) for m in baixo) if baixo else smax
    antes = len(el.membros)
    fica = []
    for m in el.membros:
        m.moldura = False
        if m.papel == "banzo":
            fica.append(m)
            continue
        lo, hi = min(m.h0, m.h1), max(m.h0, m.h1)
        if not (smin - 30 <= min(m.s0, m.s1) and max(m.s0, m.s1) <= smax + 30):
            continue
        if lo >= hmin - 30 and hi <= hmax + 30:
            if m.altura_linha == 0 and m.papel == "montante" and not (b_s0 - 30 <= m.s0 <= b_s1 + 30):
                continue
            if m.altura_linha == 0 and m.papel == "montante" and min(abs(m.s0 - b_s0), abs(m.s0 - b_s1)) < 60                     and (hi - lo) > 0.56 * (hmax - hmin):
                # o montante de ponta desenhado junto do fim do banzo (a outra linha dele é a ponta do banzo):
                # a peça de ponta, no perfil do banzo, a 20 mm do fim
                m.altura_linha = 40.0
                m.s0 = m.s1 = (b_s0 + 20.0) if abs(m.s0 - b_s0) < abs(m.s0 - b_s1) else (b_s1 - 20.0)
            fica.append(m)
            continue
        if m.altura_linha == 0 or m.papel != "montante":
            continue
        if hi > hmax + 30 and lo >= hmin - 30 and (abs(m.s0 - smin) < 80 or abs(m.s0 - smax) < 80) and hi - hmax < 300 \
                and lo > hmax - 120:
            m.moldura = True
            fica.append(m)
            continue
        if lo < hmax - 30 and hi > hmin + 30:
            if m.h0 <= m.h1:
                m.h0, m.h1 = max(m.h0, hmin), min(m.h1, hmax)
            else:
                m.h1, m.h0 = max(m.h1, hmin), min(m.h0, hmax)
            if abs(m.h1 - m.h0) > 100:
                fica.append(m)
    el.membros = fica
    for m in el.membros:
        m.h0 -= hmin
        m.h1 -= hmin
    el.y_base += hmin
    return antes - len(el.membros)


def _segs_da_peca(ents):
    segs = dp._segmentos(ents, _PECA)
    if not segs:
        return []
    comps = dp._componentes(segs, 150.0)
    if not comps:
        return segs
    # o desenho da tesoura: o grupo mais largo e o que encosta nele (a emenda, a continuação)
    princ = max(comps, key=lambda c: c["caixa"][2] - c["caixa"][0])
    x0, y0, x1, y1 = princ["caixa"]
    fica = []
    for c in comps:
        a0, b0, a1, b1 = c["caixa"]
        if a1 >= x0 - 200 and a0 <= x1 + 200 and b1 >= y0 - 200 and b0 <= y1 + 200 and (a1 - a0 > 100 or b1 - b0 > 100):
            fica += c["segs"]
    return fica


def ler_tesoura(q: dict, ents: List[dict]) -> Tuple[dict, list, object]:
    """(leitura, apontamentos, Elevacao) do quadro de uma tesoura"""
    ap: List[dict] = []
    textos = _textos(ents)
    nome = _norm_marca(q.get("nome") or "")
    qtd = None
    titulo = None
    for t in sorted(textos, key=lambda t: -(t.get("altura") or 0)):
        s = t["texto"].strip()
        mq = _RX_QTD.search(s) or _RX_QTD_MEIO.search(s)
        mn = _RX_NOME_T.search(dp._sem_acento(s).upper())
        if mq and (not nome or (mn and _norm_marca(mn.group(0)) == nome) or nome in _norm_marca(s)):
            qtd, titulo = int(mq.group(1)), t
            if not nome and mn:
                nome = _norm_marca(mn.group(0))
            break
    if not nome:
        ap.append(_ap(q, "erro", "tesoura sem nome: digite o nome no título do quadro (T01, T02…)", codigo="tesoura_sem_nome"))
        nome = q.get("id") or "T?"
    # a legenda dos perfis: palavra-chave (BANZO / DIAG / MONT) ou, sem ela, pelo tipo do perfil
    perfis = []
    for t in textos:
        if t is titulo:
            continue
        r = perfil_escrito(t["texto"])
        if r:
            perfis.append((t, r))
        elif _CARA_DE_PERFIL.search(t["texto"]):
            ap.append(_ap(q, "erro", "texto de perfil não reconhecido pelo catálogo: \"%s\"" % t["texto"].strip(), t["posicao"],
                          sugestao="reescreva no padrão do catálogo (ex.: U 100x40x2,00, L 25x25x3)", codigo="perfil_desconhecido"))
    banzo = alma = None
    for t, r in sorted(perfis, key=lambda x: -x[0]["posicao"][1]):
        s = dp._sem_acento(t["texto"]).upper()
        if "BANZO" in s and banzo is None:
            banzo = r
        elif re.search(r"DIAG|MONT|ALMA", s) and alma is None:
            alma = r
    for t, r in sorted(perfis, key=lambda x: -x[0]["posicao"][1]):
        if r is banzo or r is alma:
            continue
        fam = _familia(r)
        if banzo is None and fam[:1] != "L":
            banzo = r
        elif alma is None and fam[:1] == "L":
            alma = r
        elif alma is None and banzo is not None and r.get("perfil") != banzo.get("perfil"):
            alma = r
    if alma is None and banzo is not None and len(perfis) == 1:
        alma = None
    segs = _segs_da_peca(ents)
    el = dp._elevacao_do_grupo("TESOURA " + nome, qtd or 1, segs) if segs else None
    leitura = {"nome": nome, "qtd": qtd, "titulo": titulo["texto"].strip() if titulo else None,
               "banzo": banzo, "alma": alma, "perfis": [r["perfil"] for _t, r in perfis]}
    if el is None or not el.membros:
        ap.append(_ap(q, "erro", "não achei o desenho da tesoura (banzo inferior em linha dupla) no quadro", codigo="tesoura_vazia"))
        leitura.update({"membros": [], "comprimento": 0.0, "altura": 0.0})
        return leitura, ap, el
    el.banzo, el.alma = banzo, alma
    dp._alma_lida_duas_vezes(el)
    if banzo and int(banzo.get("mult") or 1) >= 2 and re.match(r"(?i)^U", str(banzo.get("perfil") or "")):
        dp._banzo_em_caixao(el, segs)
    fora = _limpar_faixa(el)
    # as marcas do suporte de terça em cima do banzo ("ST1") e os suportes desenhados (camada de suporte):
    # onde cada terça apoia — o 3D só põe suporte onde o projeto desenha
    el.marcas_terca = sorted(t["posicao"][0] - el.x_esq for t in textos if re.match(r"^\s*ST\s*\d", t["texto"]))
    x0_, x1_ = el.x_esq - 50.0, el.x_esq + el.comprimento + 50.0
    sup = []
    for e in ents:
        if e.get("tipo") == "polilinha" and re.search(r"(?i)suporte", e.get("camada", "")):
            xs_ = [v[0] for v in e["vertices"]]
            if x0_ <= min(xs_) and max(xs_) <= x1_:
                sup.append(round((min(xs_) + max(xs_)) / 2.0 - el.x_esq, 1))
    el.suportes_des = sorted(sup)
    # as terças desenhadas em corte em cima do banzo: (s, o pé dela acima do eixo do banzo de baixo)
    td = []
    for e in ents:
        if e.get("tipo") == "polilinha" and re.search(r"(?i)ter[çc]a", e.get("camada", "")):
            xs_ = [v[0] for v in e["vertices"]]
            ys_ = [v[1] for v in e["vertices"]]
            if x0_ <= min(xs_) and max(xs_) <= x1_ and max(xs_) - min(xs_) < 400 and max(ys_) - min(ys_) < 400:
                td.append((round((min(xs_) + max(xs_)) / 2.0 - el.x_esq, 1), round(min(ys_) - el.y_base, 1)))
    el.tercas_des = sorted(td)
    cont = collections.Counter(m.papel for m in el.membros)
    bz = [m for m in el.membros if m.papel == "banzo"]
    altura = max((max(m.h0, m.h1) for m in el.membros), default=0.0)
    leitura.update({
        "comprimento": round(el.comprimento, 1), "altura": round(altura, 1),
        "contagem": dict(cont), "fora_da_faixa": fora, "marcas_terca": [round(v, 1) for v in el.marcas_terca],
        "suportes_desenhados": el.suportes_des, "tercas_desenhadas": [list(x) for x in el.tercas_des],
        "membros": [{"s0": round(m.s0, 1), "h0": round(m.h0, 1), "s1": round(m.s1, 1), "h1": round(m.h1, 1),
                     "papel": m.papel, "dupla": round(m.altura_linha, 1), "moldura": bool(getattr(m, "moldura", False))}
                    for m in el.membros]})
    if banzo is None:
        ap.append(_ap(q, "erro", "tesoura sem legenda de perfis (o perfil do banzo não está escrito no quadro)",
                      codigo="sem_legenda"))
    elif alma is None and (cont.get("diagonal") or cont.get("montante")):
        ap.append(_ap(q, "aviso", "sem o perfil da alma na legenda: diagonais e montantes vão no perfil do banzo",
                      codigo="sem_alma"))
    if qtd is None:
        ap.append(_ap(q, "aviso", "sem a quantidade (\"… - 6x\") no título da tesoura; vale a contagem da planta",
                      codigo="sem_qtd"))
    if cont.get("banzo") and not cont.get("diagonal") and el.comprimento > 1200:
        ap.append(_ap(q, "aviso", "nenhuma diagonal lida: confira se as linhas da alma encostam no quadro ou em outro desenho",
                      codigo="sem_diagonal"))
    if len(bz) < 2:
        ap.append(_ap(q, "erro", "só um banzo lido: confira se o banzo de cima está em linha dupla", codigo="um_banzo"))
    # banzo de baixo interrompido: um vão no meio dele
    baixo = sorted(((min(m.s0, m.s1), max(m.s0, m.s1)) for m in bz if min(m.h0, m.h1) < 60.0))
    fim = None
    for a, b in baixo:
        if fim is not None and a - fim > 80.0:
            p = (el.x_esq + (fim + a) / 2, el.y_base)
            ap.append(_ap(q, "erro", "banzo interrompido entre s = %.0f e %.0f mm" % (fim, a), p, codigo="banzo_interrompido"))
        fim = b if fim is None else max(fim, b)
    # barra da alma solta: nenhuma das pontas encosta em outra barra
    for m in el.membros:
        if m.papel == "banzo" or getattr(m, "moldura", False):
            continue
        soltas = 0
        for (ps, ph) in ((m.s0, m.h0), (m.s1, m.h1)):
            if not any(_dist_ponto_membro(ps, ph, n) < 80.0 for n in el.membros if n is not m):
                soltas += 1
        if soltas == 2:
            p = (el.x_esq + (m.s0 + m.s1) / 2, el.y_base + (m.h0 + m.h1) / 2)
            ap.append(_ap(q, "aviso", "%s solta (as duas pontas sem nó) — pode ser cota ou chamada dentro da alma" % m.papel, p,
                          codigo="barra_solta"))
    return leitura, ap, el


def _esticar(a, b, d: float):
    """o segmento a–b com `d` mm a mais em cada ponta (a terça na ponta da tesoura conta como cruzando)"""
    L = math.dist(a, b) or 1.0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    return (a[0] - ux * d, a[1] - uy * d), (b[0] + ux * d, b[1] + uy * d)


def _dist_ponto_membro(s, h, m) -> float:
    ax, ay, bx, by = m.s0, m.h0, m.s1, m.h1
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((s - ax) * dx + (h - ay) * dy) / L2))
    return math.hypot(s - (ax + dx * t), h - (ay + dy * t))


# =====================================================================================
# Plantas
# =====================================================================================

_RX_PILAR = re.compile(r"(?i)^\s*(P[A-Z]{0,2}\s*-?\s*\d{1,3}[A-Z]?)\s*(?:\((.*)\))?\s*$")
_RX_SECAO_CONC = re.compile(r"^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$")


def _marca_pilar(s: str) -> str:
    return re.sub(r"[\s\-]", "", str(s).upper())


def _secoes_pequenas(ents):
    """centros dos contornos pequenos (a seção do pilar desenhada na planta)"""
    out = []
    for e in ents:
        if e.get("tipo") == "polilinha" and len(e.get("vertices") or []) >= 4 and not _ANOT.search(e.get("camada", "")):
            xs = [v[0] for v in e["vertices"]]
            ys = [v[1] for v in e["vertices"]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if 60 <= w <= 1000 and 60 <= h <= 1000:
                out.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, w, h,
                            [[round(v[0], 1), round(v[1], 1)] for v in e["vertices"]]))
        elif e.get("tipo") == "circulo" and 50 <= float(e.get("raio") or 0) <= 500 and not _ANOT.search(e.get("camada", "")):
            out.append((e["centro"][0], e["centro"][1], 2 * e["raio"], 2 * e["raio"], {"raio": round(e["raio"], 1)}))   # pilar redondo
    return out


def _pilares_por_texto(ents) -> List[dict]:
    textos = _textos(ents)
    secoes = _secoes_pequenas(ents)
    out = []
    for t in textos:
        m = _RX_PILAR.match(t["texto"])
        if not m:
            continue
        nome = _marca_pilar(m.group(1))
        x, y = t["posicao"][0], t["posicao"][1]
        alt = float(t.get("altura") or 100.0)
        secao = m.group(2)
        if not secao:
            # a seção escrita logo abaixo do nome ("30/30", "W200x26,6")
            abaixo = [u for u in textos if u is not t and 0 < y - u["posicao"][1] < 2.5 * alt and abs(u["posicao"][0] - x) < 3 * alt]
            if abaixo:
                secao = min(abaixo, key=lambda u: y - u["posicao"][1])["texto"].strip()
        perfil = perfil_escrito(secao) if secao else None
        conc = _RX_SECAO_CONC.match(secao or "")
        redondo = re.match(r"^\s*(?:Ø|%%[cC]|ø|D\s*=?)\s*(\d{2,3})\s*(cm)?\s*$", secao or "")
        if redondo and int(redondo.group(1)) <= 120:
            perfil = None                    # "Ø40" na locação é o pilar redondo de concreto, em cm
        perto = [c for c in secoes if math.hypot(c[0] - x, c[1] - y) < 2000.0]
        pos = None
        contorno = None
        if perto:
            c = min(perto, key=lambda c: math.hypot(c[0] - x, c[1] - y))
            pos = (c[0], c[1])
            contorno = c[4]
        p = {"nome": nome, "texto": (x, y), "secao": secao, "posicao": pos or (x, y), "achou_secao": pos is not None,
             "contorno": contorno}
        if perfil:
            p["perfil"] = perfil["perfil"]
        elif conc:
            p["concreto"] = [int(conc.group(1)) * 10, int(conc.group(2)) * 10]      # cm → mm
        elif redondo and int(redondo.group(1)) <= 120:
            p["concreto"] = [int(redondo.group(1)) * 10]                                 # Ø em cm → mm
        out.append(p)
    return out


def _eixos(ents) -> List[dict]:
    """eixos pelos balões: os de mesma família (números ou letras) enfileirados marcam linhas
    no sentido atravessado"""
    cx = _caixa(ents)
    if not cx:
        return []
    bs = dp.baloes(ents, cx, folga=0.0)
    if len(bs) < 2:
        return []
    raios = {}
    for e in ents:
        if e.get("tipo") == "circulo" and 120 < float(e.get("raio") or 0) < 800:
            raios[(round(e["centro"][0]), round(e["centro"][1]))] = float(e["raio"])
    linhas = [((e["a"][0], e["a"][1]), (e["b"][0], e["b"][1])) for e in ents
              if e.get("tipo") == "linha" and math.dist(e["a"][:2], e["b"][:2]) > 2000.0]
    out = []
    for n, p in bs.items():
        # a linha do eixo: a comprida que começa na borda do balão (a direção vale também na ala girada)
        r = raios.get((round(p[0]), round(p[1])), 300.0)
        melhor = None
        for a, b in linhas:
            for u, v in ((a, b), (b, a)):
                d = math.dist(u, p)
                if d < 2.2 * r and (melhor is None or d < melhor[0]):
                    melhor = (d, u, v)
        if melhor:
            _d, u, v = melhor
            L = math.dist(u, v)
            ux, uy = (v[0] - u[0]) / L, (v[1] - u[1]) / L
            if abs(ux) < 0.02:
                out.append({"nome": n, "x": round(p[0], 1)})
            elif abs(uy) < 0.02:
                out.append({"nome": n, "y": round(p[1], 1)})
            else:
                out.append({"nome": n, "inclinado": True, "balao": [round(p[0], 1), round(p[1], 1)], "dir": [round(ux, 5), round(uy, 5)]})
    feitos = {e["nome"] for e in out}
    for fam in (lambda n: n[:1].isdigit(), lambda n: not n[:1].isdigit()):
        grupo = {n: p for n, p in bs.items() if fam(n)}
        for n, p in grupo.items():
            if n in feitos:
                continue
            # o balão numa fila (vizinhos da mesma família à mesma altura) marca uma linha em pé; numa
            # coluna, uma linha deitada; sozinho, é eixo inclinado (fica sem coordenada)
            fila = sum(1 for o, q in grupo.items() if o != n and abs(q[1] - p[1]) < 300.0)
            coluna = sum(1 for o, q in grupo.items() if o != n and abs(q[0] - p[0]) < 300.0)
            if fila > coluna:
                out.append({"nome": n, "x": round(p[0], 1)})
            elif coluna > fila:
                out.append({"nome": n, "y": round(p[1], 1)})
            else:
                out.append({"nome": n, "inclinado": True, "balao": [round(p[0], 1), round(p[1], 1)], "familia": fam(n)})
    # os inclinados da mesma família em fila (a ala girada): a linha de cada um atravessa a fila
    for f_ in (True, False):
        inc = [e for e in out if e.get("inclinado") and e.get("familia") == f_]
        if len(inc) >= 2:
            a, b = max(((u, v) for u in inc for v in inc), key=lambda uv: math.dist(uv[0]["balao"], uv[1]["balao"]))
            L = math.dist(a["balao"], b["balao"]) or 1.0
            ux, uy = (b["balao"][0] - a["balao"][0]) / L, (b["balao"][1] - a["balao"][1]) / L
            for e in inc:
                e["dir"] = [round(-uy, 5), round(ux, 5)]
    for e in out:
        e.pop("familia", None)
    return out


def _dist_eixo(p, e) -> Optional[float]:
    if "x" in e:
        return abs(p[0] - e["x"])
    if "y" in e:
        return abs(p[1] - e["y"])
    if e.get("dir"):
        bx, by = e["balao"]
        dx, dy = e["dir"]
        return abs(-(p[0] - bx) * dy + (p[1] - by) * dx)          # dir: a direção da linha do eixo
    return None


def ler_locacao(q: dict, ents: List[dict]) -> Tuple[dict, list]:
    ap: List[dict] = []
    pilares = _pilares_por_texto(ents)
    eixos = _eixos(ents)
    if not ents:
        ap.append(_ap(q, "erro", "quadro vazio: mande a planta de locação dos pilares para cá", codigo="vazio"))
        return {"pilares": [], "eixos": []}, ap
    if not pilares:
        ap.append(_ap(q, "erro", "nenhum pilar (P1, P2…) achado na locação", codigo="sem_pilar"))
    vistos = collections.Counter(p["nome"] for p in pilares)
    for n, k in vistos.items():
        if k > 1:
            p = next(p for p in pilares if p["nome"] == n)
            ap.append(_ap(q, "aviso", "%s escrito %d vezes na locação" % (n, k), p["texto"], codigo="pilar_repetido"))
    num = [e for e in eixos if e["nome"][:1].isdigit()]
    let = [e for e in eixos if not e["nome"][:1].isdigit()]
    for p in pilares:
        if not p.get("perfil") and not p.get("concreto"):
            ap.append(_ap(q, "aviso", "%s sem seção escrita (perfil ou 30/30)" % p["nome"], p["texto"], codigo="pilar_sem_secao"))
        if not p["achou_secao"]:
            ap.append(_ap(q, "aviso", "%s: não achei o contorno do pilar perto do nome; ficou no lugar do texto" % p["nome"],
                          p["texto"], codigo="pilar_sem_contorno"))
        d1 = [d for d in (_dist_eixo(p["posicao"], e) for e in num) if d is not None]
        d2 = [d for d in (_dist_eixo(p["posicao"], e) for e in let) if d is not None]
        if d1 and d2 and min(d1) > 150 and min(d2) > 150:
            ap.append(_ap(q, "aviso", "%s fora dos eixos (%.0f mm do eixo de número e %.0f do de letra mais perto)" % (
                p["nome"], min(d1), min(d2)), p["posicao"], codigo="pilar_fora_eixo"))
    if pilares and not eixos:
        ap.append(_ap(q, "aviso", "sem balões de eixo na locação", codigo="sem_eixos"))
    return {"pilares": [dict(p, posicao=[round(v, 1) for v in p["posicao"]], texto=[round(v, 1) for v in p["texto"]])
                        for p in pilares], "eixos": eixos}, ap


def _linhas_longas(ents, lmin=1500.0, camadas=None):
    """linhas de centro das peças compridas da planta: pares (perfil em linha dupla) e simples"""
    segs = dp._segmentos(ents, camadas or _PECA)
    duplas, simples = dp.centros_retos(segs, lmin=lmin, larg=(20.0, 260.0))
    out = [(c.a, c.b, c.largura, c.camada) for c in duplas]
    out += [(a, b, 0.0, cam) for a, b, _ux, _uy, L, cam, _id in simples if L >= lmin]
    return out


def _proj(p, a, b):
    """(t ao longo de a→b em mm, distância ao eixo)"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    t = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
    d = abs(-(p[0] - a[0]) * uy + (p[1] - a[1]) * ux)
    return t, d, L


def _linha_da_marca(p, linhas, dmax=1500.0):
    melhor = None
    for i, (a, b, larg, _c) in enumerate(linhas):
        t, d, L = _proj(p, a, b)
        if -300.0 <= t <= L + 300.0 and d <= dmax:
            nota = d - (0.3 * larg)
            if melhor is None or nota < melhor[0]:
                melhor = (nota, i, t, d)
    return melhor


_RX_MARCA_T = re.compile(r"^\s*T\s*-?\s*\d{1,3}[A-Z]?\s*$", re.I)
_RX_SIGLA_TC = re.compile(r"^\s*(T\.?\s*C\.?|TC)\s*-?\s*(\d{1,3})\s*$", re.I)
_RX_SIGLA_LISTA = re.compile(r"(?i)\b(T\.?\s*C\.?|TC)\s*-?\s*(\d{1,3})\b")
_RX_CV = re.compile(r"(?i)^\s*(CV|C\.V\.?)\s*-?\s*(\d{1,3})\s*$")


def _sigla_tc(n) -> str:
    return "TC%02d" % int(n)


def ler_posicao_tesouras(q: dict, ents: List[dict], nomes=()) -> Tuple[dict, list]:
    """as marcas T01… (e as dos outros quadros de tesoura: V.P 01, V.T 01) em cima das linhas da planta"""
    ap: List[dict] = []
    if not ents:
        ap.append(_ap(q, "erro", "quadro vazio: mande a planta com as marcas T01, T02… para cá", codigo="vazio"))
        return {"marcas": [], "linhas": []}, ap
    # a planta pode ser a mesma das terças: as linhas de terça, contravento e telha não são tesoura
    linhas = _linhas_longas(ents, camadas=re.compile(
        r"^(?!.*(?:cota|dim\b|dimens|texto|folha|hach|defpoints|carimbo|anno|vport|legenda|ter[çc]a|contravent|telha|rufo))", re.I))
    marcas = []
    nomes = set(nomes or ())
    for t in _textos(ents):
        if not (_RX_MARCA_T.match(t["texto"]) or (len(t["texto"].strip()) <= 8 and _norm_marca(t["texto"]) in nomes)):
            continue
        nome = _norm_marca(t["texto"])
        p = (t["posicao"][0], t["posicao"][1])
        m = _linha_da_marca(p, linhas)
        reg = {"nome": nome, "posicao": [round(p[0], 1), round(p[1], 1)]}
        if m is None:
            ap.append(_ap(q, "aviso", "marca %s sem linha de tesoura perto (até 1,5 m)" % nome, p, codigo="marca_sem_linha"))
        else:
            a, b, larg, cam = linhas[m[1]]
            reg.update({"linha": m[1], "t": round(m[2], 1), "dist": round(m[3], 1)})
        marcas.append(reg)
    if not marcas:
        ap.append(_ap(q, "erro", "nenhuma marca de tesoura (T01, T02…) no quadro", codigo="sem_marcas"))
    pilares = _pilares_por_texto(ents)
    return {"marcas": marcas, "contagem": dict(collections.Counter(m["nome"] for m in marcas)),
            "linhas": [{"a": [round(v, 1) for v in a], "b": [round(v, 1) for v in b], "largura": round(larg, 1), "camada": cam}
                       for a, b, larg, cam in linhas],
            "pilares": [{"nome": p["nome"], "posicao": [round(v, 1) for v in p["texto"]]} for p in pilares]}, ap


def _tabela_tercas(textos) -> Dict[str, dict]:
    """a lista das terças: "Terça - TC01 - 4x" / "TC13-U100X40X2,65 - 56X"; o perfil no mesmo
    texto ou logo abaixo"""
    out: Dict[str, dict] = {}
    for t in textos:
        s = t["texto"].strip()
        if _RX_SIGLA_TC.match(s):
            continue                                   # marca solta na planta, não lista
        m = _RX_SIGLA_LISTA.search(s)
        mq = _RX_QTD.search(s)
        if not m or not mq:
            continue
        sig = _sigla_tc(m.group(2))
        item = {"qtd": int(mq.group(1)), "texto": s, "posicao": [round(t["posicao"][0], 1), round(t["posicao"][1], 1)]}
        r = perfil_escrito(s[m.end():mq.start()])
        if not r:
            alt = float(t.get("altura") or 100.0)
            x, y = t["posicao"][0], t["posicao"][1]
            abaixo = sorted((u for u in textos if u is not t and 0 < y - u["posicao"][1] < 2.6 * alt
                             and abs(u["posicao"][0] - x) < 30 * alt), key=lambda u: y - u["posicao"][1])
            for u in abaixo:
                r = perfil_escrito(u["texto"])
                if r:
                    break
        c = re.search(r"(?i)COMP\.?\s*=?\s*(\d+)", s)
        if c:
            item["comp"] = float(c.group(1))
        if r:
            item["perfil"] = r["perfil"]
        out.setdefault(sig, item)
    return out


def ler_tercas(q: dict, ents: List[dict]) -> Tuple[dict, list]:
    ap: List[dict] = []
    if not ents:
        ap.append(_ap(q, "erro", "quadro vazio: mande a planta das terças (com as siglas e a lista) para cá", codigo="vazio"))
        return {"marcas": [], "tabela": {}, "linhas": []}, ap
    textos = _textos(ents)
    tabela = _tabela_tercas(textos)
    # a planta: o que veio no(s) envio(s) com siglas marcadas (a lista mandada ao lado traz o desenho de cada
    # terça, que não é planta)
    env = lambda e: (e.get("atributos") or {}).get("envio")
    com_marca = {env(t) for t in textos if _RX_SIGLA_TC.match(t["texto"])}
    planta = [e for e in ents if env(e) in com_marca] if com_marca else ents
    cam_terca = re.compile(r"(?i)ter[çc]a")
    tem_camada = any(cam_terca.search(e.get("camada", "")) and not _ANOT.search(e.get("camada", "")) for e in planta)
    linhas = _linhas_longas(planta, lmin=1000.0, camadas=re.compile(r"(?i)^(?=.*ter[çc]a)(?!.*(cota|texto|folha))") if tem_camada else None)
    marcas = []
    for t in textos:
        m = _RX_SIGLA_TC.match(t["texto"])
        if not m:
            continue
        sig = _sigla_tc(m.group(2))
        p = (t["posicao"][0], t["posicao"][1])
        reg = {"sigla": sig, "posicao": [round(p[0], 1), round(p[1], 1)]}
        lm = _linha_da_marca(p, linhas, dmax=800.0)
        if lm:
            reg.update({"linha": lm[1], "t": round(lm[2], 1)})
        marcas.append(reg)
    cont = collections.Counter(m["sigla"] for m in marcas)
    if not marcas and not linhas:
        ap.append(_ap(q, "erro", "nenhuma terça (linha ou sigla TC01…) no quadro", codigo="sem_tercas"))
    for sig, k in sorted(cont.items()):
        if sig not in tabela:
            p = next(m["posicao"] for m in marcas if m["sigla"] == sig)
            ap.append(_ap(q, "erro", "%s na planta sem quantidade na lista das terças" % sig, p, codigo="sigla_sem_lista"))
    for sig, it in sorted(tabela.items()):
        if cont.get(sig) and cont[sig] != it["qtd"]:
            ap.append(_ap(q, "aviso", "%s: a lista diz %dx e a planta tem %d marca(s)" % (sig, it["qtd"], cont[sig]), it["posicao"],
                          codigo="sigla_qtd_difere"))
        if "perfil" not in it:
            ap.append(_ap(q, "aviso", "%s na lista sem perfil reconhecido (\"%s\")" % (sig, it["texto"]), it["posicao"],
                          codigo="sigla_sem_perfil"))
        if cont and sig not in cont:
            ap.append(_ap(q, "aviso", "%s na lista e nenhuma marca dela na planta" % sig, it["posicao"], codigo="sigla_sem_marca"))
    # contraventos: a lista ("CV1 (04x) - 400cm") × a linha marcada na planta
    cvs = _contraventos(planta)
    lista_cv = {}
    for t in textos:
        mm = re.search(r"(?i)\b(CV)\s*-?\s*(\d{1,2})\s*\(\s*(\d+)\s*x\s*\)\s*-?\s*(\d+(?:[.,]\d+)?)\s*(cm|mm|m)\b", t["texto"])
        if mm:
            v = float(mm.group(4).replace(",", ".")) * {"cm": 10.0, "mm": 1.0, "m": 1000.0}[mm.group(5).lower()]
            lista_cv["CV%d" % int(mm.group(2))] = {"qtd": int(mm.group(3)), "comp": v, "posicao": [round(t["posicao"][0], 1), round(t["posicao"][1], 1)]}
    marcas_cv = collections.Counter()
    for t in textos:
        mm = _RX_CV.match(t["texto"])
        if not mm or env(t) not in (com_marca or {env(t)}):
            continue
        nome = "CV%d" % int(mm.group(2))
        p = (t["posicao"][0], t["posicao"][1])
        perto = None
        for c in cvs:
            tt, d, L = _proj(p, c["a"], c["b"])
            if -300 <= tt <= L + 300 and d < 1500 and (perto is None or d < perto[0]):
                perto = (d, c)
        if perto:
            perto[1].setdefault("marcas", []).append(nome)
            marcas_cv[nome] += 1
    for c in cvs:
        for nome in set(c.get("marcas") or []):
            it = lista_cv.get(nome)
            L = math.dist(c["a"], c["b"])
            c["nome"] = nome
            if it and abs(L - it["comp"]) > 50.0:
                ap.append(_ap(q, "aviso", "%s: na planta %.0f mm, na lista %.0f mm — o 3D segue a planta" % (nome, L, it["comp"]),
                              ((c["a"][0] + c["b"][0]) / 2, (c["a"][1] + c["b"][1]) / 2), codigo="cv_comprimento"))
    sem_linha = [m for m in marcas if "linha" not in m]
    for m in sem_linha[:20]:
        ap.append(_ap(q, "aviso", "%s sem linha de terça perto" % m["sigla"], m["posicao"], codigo="sigla_sem_linha"))
    return {"marcas": marcas, "contagem": dict(cont), "tabela": tabela,
            "linhas": [{"a": [round(v, 1) for v in a], "b": [round(v, 1) for v in b], "largura": round(larg, 1), "camada": cam}
                       for a, b, larg, cam in linhas],
            "contraventos": cvs, "lista_cv": lista_cv}, ap


def _contraventos(ents) -> List[dict]:
    """as linhas na camada de contravento e as marcas CV1… com a lista ("CV1 (04x) - 400cm")"""
    linhas = []
    for e in ents:
        if e.get("tipo") == "linha" and re.search(r"(?i)contravent", e.get("camada", "")):
            a, b = e["a"], e["b"]
            if math.dist(a[:2], b[:2]) > 800:
                linhas.append({"a": [round(a[0], 1), round(a[1], 1)], "b": [round(b[0], 1), round(b[1], 1)]})
    return linhas


# =====================================================================================
# Corte e elevações: níveis
# =====================================================================================

_RX_NIVEL = re.compile(r"(?i)(?:N[IÍ]VEL|NV\.?|EL\.?|N\.?\s*A\.?|^)\s*([+\-±])\s*(\d{1,3}[,.]\d{2,3})\b")
_RX_NIVEL2 = re.compile(r"(?i)N[IÍ]VEL\s*([+\-]?\s*\d{1,3}[,.]\d{1,3})")
_RX_INCL = re.compile(r"(?i)(\d{1,2}(?:[,.]\d+)?)\s*%")


def ler_niveis(q: dict, ents: List[dict]) -> Tuple[dict, list]:
    ap: List[dict] = []
    niveis = []
    for t in _textos(ents):
        s = t["texto"].strip()
        m = _RX_NIVEL.search(s)
        z = None
        if m:
            sinal = -1.0 if m.group(1) == "-" else 1.0
            z = sinal * float(m.group(2).replace(",", ".")) * 1000.0
        else:
            m2 = _RX_NIVEL2.search(s)
            if m2:
                z = float(m2.group(1).replace(" ", "").replace(",", ".")) * 1000.0
        if z is not None and not any(abs(z - n["z"]) < 5.0 for n in niveis):
            niveis.append({"z": round(z, 1), "texto": s[:60], "y": round(t["posicao"][1], 1)})
    niveis.sort(key=lambda n: n["z"])
    cotas = []
    for e in ents:
        if e.get("tipo") != "cota":
            continue
        dx, dy = e["p2"][0] - e["p1"][0], e["p2"][1] - e["p1"][1]
        v = _num((e.get("atributos") or {}).get("medida_real") or e.get("texto") or "")
        if v is None:
            v = math.hypot(dx, dy)
        cotas.append({"valor": round(v, 1), "vertical": abs(dy) > abs(dx)})
    incl = None
    for t in _textos(ents):
        m = _RX_INCL.search(t["texto"])
        if m and re.search(r"(?i)incl|i\s*=|%", t["texto"]):
            incl = float(m.group(1).replace(",", "."))
            break
    alturas = sorted({c["valor"] for c in cotas if c["vertical"]})
    leitura = {"niveis": niveis, "cotas_verticais": alturas, "inclinacao": incl, "objetos": len(ents)}
    if q.get("tipo") == "corte":
        if not ents:
            ap.append(_ap(q, "aviso", "quadro vazio: sem o corte, a base e o topo dos pilares vêm dos parâmetros", codigo="vazio"))
        elif len(niveis) < 2 and not alturas:
            ap.append(_ap(q, "aviso", "corte sem cotas de nível (+4,00) nem cotas verticais: base e topo dos pilares vêm dos parâmetros",
                          codigo="corte_sem_nivel"))
    return leitura, ap


# =====================================================================================
# Tudo junto
# =====================================================================================

def _alinhamento_locacao(loc: dict, ref_pilares: List[dict], ref_eixos: List[dict]) -> Optional[dict]:
    """o quanto somar à locação para cair sobre a planta de referência: pelos nomes dos pilares
    em comum (mediana), senão pelos balões"""
    ds = []
    por_nome = {p["nome"]: p for p in loc.get("pilares") or []}
    for p in ref_pilares:
        o = por_nome.get(p["nome"])
        if o:
            ds.append((p["posicao"][0] - o["texto"][0], p["posicao"][1] - o["texto"][1]))
    if len(ds) >= 2:
        mx = sorted(d[0] for d in ds)[len(ds) // 2]
        my = sorted(d[1] for d in ds)[len(ds) // 2]
        ok = [d for d in ds if abs(d[0] - mx) < 300 and abs(d[1] - my) < 300]
        if len(ok) >= 2:
            return {"dx": round(sum(d[0] for d in ok) / len(ok), 1), "dy": round(sum(d[1] for d in ok) / len(ok), 1),
                    "por": "pilares", "comuns": len(ok)}
    return None


def _assinaturas(des: dict, caixa) -> collections.Counter:
    """as entidades inteiras dentro da caixa, cada uma pela forma (tipo, camada, pontos ao mm, texto)"""
    (x0, y0), (x1, y1) = caixa
    out = collections.Counter()
    for e in des.get("entidades") or []:
        pts = []
        t_ = e.get("tipo")
        if t_ == "linha":
            pts = [e["a"], e["b"]]
        elif t_ == "polilinha":
            pts = list(e.get("vertices") or [])
        elif t_ in ("circulo", "arco"):
            pts = [e["centro"]]
        elif t_ == "texto":
            pts = [e["posicao"]]
        elif t_ == "cota":
            pts = [e["p1"], e["p2"]]
        if not pts or not all(x0 - 0.5 <= p[0] <= x1 + 0.5 and y0 - 0.5 <= p[1] <= y1 + 0.5 for p in pts):
            continue
        out[(t_, str(e.get("camada", "")), tuple((round(p[0]), round(p[1])) for p in pts),
             str(e.get("texto") or ""), round(float(e.get("raio") or 0.0)))] += 1
    return out


def comparar_revisao(m: dict, abrir) -> List[dict]:
    """cada área mandada para um quadro (o envio) comparada com a revisão atual da Original: o que entrou e
    o que saiu ali. O quadro não muda sozinho (decisão de 01/10): vira apontamento, com o envio para o
    "Atualizar pela revisão" da tela."""
    atual = m.get("original")
    if not atual or not abrir:
        return []
    cache: Dict[str, Optional[dict]] = {}

    def des(nome):
        if nome not in cache:
            try:
                d = abrir(nome)
                ents = d.get("entidades") or []
                if isinstance(ents, dict):
                    d = dict(d, entidades=list(ents.values()))
                cache[nome] = d
            except Exception:                         # noqa: BLE001 — revisão apagada: não compara
                cache[nome] = None
        return cache[nome]
    out = []
    rev = next((r for r in m.get("revisoes") or [] if r.get("nome") == atual), {})
    for q in m.get("quadros") or []:
        envios = list(q.get("envios") or [])
        if not envios and (q.get("fonte") or {}).get("caixa"):
            envios = [dict(q["fonte"], id=None)]
        for env in envios:
            de = env.get("desenho")
            if not de or de == atual or not env.get("caixa"):
                continue
            velho, novo = des(de), des(atual)
            if velho is None or novo is None:
                continue
            a, b = _assinaturas(velho, env["caixa"]), _assinaturas(novo, env["caixa"])
            entrou, saiu = sum((b - a).values()), sum((a - b).values())
            if not entrou and not saiu:
                continue
            (x0, y0), (x1, y1) = env["caixa"]
            ap = _ap(q, "aviso", "a revisão %s mudou a área deste quadro: %d objeto(s) novo(s), %d que saíram" % (
                rev.get("rotulo") or atual, entrou, saiu), ((x0 + x1) / 2, (y0 + y1) / 2),
                sugestao="Atualizar o quadro pela revisão (o que foi previsto não muda sozinho)", codigo="revisao_mudou")
            ap["envio"] = env.get("id")
            ap["revisao"] = atual
            out.append(ap)
    return out


def ler(desenho: dict, parametros: Optional[dict] = None, abrir=None) -> dict:
    """a leitura de todos os quadros da Montagem e a pré-análise. `abrir(nome)` dá um desenho do projeto
    (para comparar as áreas dos quadros com a revisão nova da Original).

    Devolve {quadros: [{id, tipo, nome, escala, objetos, resumo, leitura}], apontamentos: [...],
    erros, avisos, referencia, elevacoes (as Elevacao das tesouras, para gerar o 3D)}."""
    m = ((desenho.get("metadados") or {}).get("montagem")) or {}
    par = dict(m.get("parametros") or {})
    par.update(parametros or {})
    reais = entidades_reais(desenho)
    quadros_out = []
    aps: List[dict] = []
    elevacoes: Dict[str, object] = {}
    por_tipo: Dict[str, List[Tuple[dict, dict]]] = collections.defaultdict(list)
    nomes_t = {_norm_marca(q["nome"]) for q in m.get("quadros") or [] if q.get("tipo") in COM_NOME and q.get("nome")}
    for q in m.get("quadros") or []:
        ents = reais.get(q["id"], [])
        tipo = q.get("tipo")
        item = {"id": q["id"], "tipo": tipo, "nome": q.get("nome") or "", "rotulo": _rotulo(q), "escala": q.get("escala"),
                "objetos": len(ents), "fonte": (q.get("fonte") or {}).get("desenho")}
        if q.get("conferencia") and q["conferencia"].get("cotas") and q["conferencia"].get("batem", 0) < q["conferencia"]["cotas"] / 2:
            c = q["conferencia"]
            aps.append(_ap(q, "aviso", "escala do quadro: só %d de %d cotas batem com a medida%s" % (
                c.get("batem", 0), c["cotas"], " (as cotas parecem estar ×%s)" % c["fator"] if c.get("fator") else ""),
                codigo="escala_nao_confere"))
        if tipo in COM_NOME:
            if not ents:
                aps.append(_ap(q, "aviso", "quadro de tesoura vazio", codigo="vazio"))
                item["resumo"] = "vazio"
                quadros_out.append(item)
                continue
            lt, ap, el = ler_tesoura(q, ents)
            if el is not None and el.membros:
                elevacoes[lt["nome"]] = el
            c = lt.get("contagem") or {}
            item["leitura"] = lt
            item["resumo"] = ("%s: o desenho da tesoura não foi lido" % lt["nome"]) if not lt.get("membros") else                 "%s: %.2f m × %.2f m · %d banzos, %d montantes, %d diagonais · %s / %s%s" % (
                lt["nome"], (lt.get("comprimento") or 0) / 1000.0, (lt.get("altura") or 0) / 1000.0, c.get("banzo", 0),
                c.get("montante", 0), c.get("diagonal", 0), (lt.get("banzo") or {}).get("perfil", "?"),
                (lt.get("alma") or {}).get("perfil", "?"), " · %dx" % lt["qtd"] if lt.get("qtd") else "")
        elif tipo == "locacao":
            lt, ap = ler_locacao(q, ents)
            item["leitura"] = lt
            item["resumo"] = "%d pilares · %d eixos" % (len(lt["pilares"]), len(lt["eixos"]))
        elif tipo == "tercas":
            lt, ap = ler_tercas(q, ents)
            item["leitura"] = lt
            item["resumo"] = "%d linhas de terça · %d siglas marcadas (%s) · lista com %d" % (
                len(lt["linhas"]), len(lt["marcas"]), ", ".join(sorted(lt.get("contagem") or {})) or "—", len(lt["tabela"]))
        elif tipo == "tesouras_pos":
            lt, ap = ler_posicao_tesouras(q, ents, nomes_t)
            item["leitura"] = lt
            item["resumo"] = "%d marcas: %s" % (len(lt["marcas"]), ", ".join("%s ×%d" % kv for kv in sorted((lt.get("contagem") or {}).items())) or "—")
        elif tipo in ELEVACOES:
            lt, ap = ler_niveis(q, ents)
            item["leitura"] = lt
            item["resumo"] = ("níveis: " + ", ".join("%+.2f" % (n["z"] / 1000.0) for n in lt["niveis"]) if lt["niveis"] else "sem níveis escritos") \
                + (" · cotas verticais: %d" % len(lt["cotas_verticais"]) if lt["cotas_verticais"] else "")
        elif tipo == "ligacoes":
            lt, ap = {"escolhas": dict(m.get("ligacoes") or {})}, []
            item["leitura"] = lt
            item["resumo"] = ", ".join("%s: %s" % kv for kv in sorted(lt["escolhas"].items())) or "nenhuma variante escolhida"
        else:
            ap = []
            item["resumo"] = "%d objetos" % len(ents)
        aps += ap
        por_tipo[tipo].append((q, item))
        quadros_out.append(item)
    ref = _cruzar(m, por_tipo, elevacoes, par, aps)
    aps += comparar_revisao(m, abrir)
    erros = sum(1 for a in aps if a["nivel"] == "erro")
    return {"quadros": quadros_out, "apontamentos": aps, "erros": erros, "avisos": len(aps) - erros,
            "referencia": ref, "parametros": par, "elevacoes": elevacoes}


def _cruzar(m: dict, por_tipo, elevacoes, par: dict, aps: List[dict]) -> dict:
    """as conferências entre quadros e a referência comum das plantas"""
    ref: dict = {}
    pos = [it for _q, it in por_tipo.get("tesouras_pos", []) if it.get("leitura")]
    ter = [it for _q, it in por_tipo.get("tercas", []) if it.get("leitura")]
    loc = [it for _q, it in por_tipo.get("locacao", []) if it.get("leitura")]
    q_pos = por_tipo["tesouras_pos"][0][0] if por_tipo.get("tesouras_pos") else {}
    # marcas na planta × quadros de tesoura
    marcas = collections.Counter()
    for it in pos:
        marcas.update(it["leitura"].get("contagem") or {})
    nomes_t = {}
    for q, it in por_tipo.get("tesoura", []) + por_tipo.get("viga", []):
        lt = it.get("leitura") or {}
        if lt.get("nome"):
            nomes_t[lt["nome"]] = (q, lt)
    if pos:
        for nome, k in sorted(marcas.items()):
            if nome not in nomes_t:
                mk = next(mm for it in pos for mm in it["leitura"]["marcas"] if mm["nome"] == nome)
                aps.append(_ap(q_pos, "erro", "marca %s na planta sem quadro de tesoura com esse nome" % nome, mk["posicao"],
                               sugestao="+ corte tesoura e mande a elevação da %s para ele" % nome, codigo="marca_sem_quadro"))
        for nome, (q, lt) in sorted(nomes_t.items()):
            k = marcas.get(nome, 0)
            if k == 0:
                aps.append(_ap(q, "aviso", "tesoura %s sem nenhuma marca na planta da posição das tesouras" % nome, codigo="quadro_sem_marca"))
            elif lt.get("qtd") and lt["qtd"] != k:
                aps.append(_ap(q, "aviso", "título \"%dx\" e a planta com %d marca(s) %s" % (lt["qtd"], k, nome), codigo="qtd_difere"))
    elif nomes_t:
        aps.append({"nivel": "erro", "quadro": None, "rotulo": "Posição das tesouras", "codigo": "sem_posicao",
                    "msg": "sem o quadro da posição das tesouras: não há onde colocar as tesouras"})
    # a referência das plantas: a posição das tesouras (ou as terças); a locação é trazida pelos pilares
    base = pos[0] if pos else (ter[0] if ter else None)
    if loc and base is not None:
        ref_pil = list(base["leitura"].get("pilares") or [])
        if not ref_pil and ter:
            ref_pil = []
        al = _alinhamento_locacao(loc[0]["leitura"], ref_pil, [])
        if al is None and loc[0].get("fonte") and base.get("fonte") == loc[0].get("fonte"):
            # o mesmo desenho, sem pilar em comum: a locação já está no lugar se foi desenhada sobreposta
            al = {"dx": 0.0, "dy": 0.0, "por": "mesma origem", "comuns": 0}
        if al is None:
            q_loc = por_tipo["locacao"][0][0]
            aps.append(_ap(q_loc, "aviso", "a locação não tem pilares com o mesmo nome da planta das tesouras: "
                                           "os pilares ficaram onde a locação está no desenho", codigo="locacao_sem_alinhamento"))
            al = {"dx": 0.0, "dy": 0.0, "por": "nenhum", "comuns": 0}
        ref["locacao"] = al
    # níveis: o corte manda; os parâmetros digitados valem mais
    niveis = []
    for t in ELEVACOES:
        for _q, it in por_tipo.get(t, []):
            niveis += (it.get("leitura") or {}).get("niveis") or []
    zs = sorted({n["z"] for n in niveis})
    base_z = par.get("base")
    topo_z = par.get("topo")
    if base_z in (None, ""):
        base_z = 0.0 if (not zs or 0.0 in zs or min(zs) > 0) else min(zs)
    if topo_z in (None, ""):
        maiores = [z for z in zs if z > float(base_z) + 1500.0]
        topo_z = maiores[0] if maiores else None
    ref["base"] = float(base_z)
    ref["topo"] = float(topo_z) if topo_z is not None else None
    if ref["topo"] is None and (nomes_t or loc):
        aps.append({"nivel": "erro", "quadro": por_tipo["corte"][0][0]["id"] if por_tipo.get("corte") else None,
                    "rotulo": "Corte transversal", "codigo": "sem_topo",
                    "msg": "sem o topo dos pilares (nem no corte nem nos parâmetros): digite o topo no painel da leitura",
                    "sugestao": "Topo dos pilares (mm)"})
    # ligações: a função sem variante escolhida
    lig = dict(m.get("ligacoes") or {})
    precisa = []
    if ter and any(it["leitura"]["linhas"] or it["leitura"]["marcas"] for it in ter):
        precisa.append(("suporte_terca", "suporte de terça"))
    if ter and any(it["leitura"].get("contraventos") for it in ter):
        precisa.append(("suporte_contravento", "suporte de contravento"))
    q_lig = por_tipo["ligacoes"][0][0] if por_tipo.get("ligacoes") else {"id": None, "tipo": "ligacoes"}
    for f, rot in precisa:
        if not lig.get(f):
            aps.append(_ap(q_lig, "erro", "%s sem variante escolhida no banco de detalhes" % rot,
                           sugestao="escolha no quadro Detalhes de ligação", codigo="ligacao_sem_variante:" + f))
    # terça × tesoura: cada linha de terça cruza alguma linha de tesoura?
    if pos and ter:
        lt_lin = [((l["a"][0], l["a"][1]), (l["b"][0], l["b"][1])) for it in pos for l in it["leitura"]["linhas"]]
        q_ter = por_tipo["tercas"][0][0]
        sem = 0
        for l in ter[0]["leitura"]["linhas"]:
            a, b = (l["a"][0], l["a"][1]), (l["b"][0], l["b"][1])
            # a terça de vão em vão para na face da tesoura: as duas esticadas um pouco
            a2, b2 = _esticar(a, b, 150.0)
            if not any(dp._cruzamento(a2, b2, *_esticar(c, d, 300.0)) for c, d in lt_lin):
                sem += 1
                if sem <= 10:
                    aps.append(_ap(q_ter, "aviso", "linha de terça que não cruza nenhuma tesoura", ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                                   codigo="terca_sem_tesoura"))
    return ref
