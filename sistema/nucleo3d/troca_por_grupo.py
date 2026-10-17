# -*- coding: utf-8 -*-
"""Trocar perfis por grupo — a ferramenta dos estudos (pedido do usuário na revisão das regras das tesouras, 16/10/2026:
"se o cliente pede para ver uma opção diferente o ajuste é rápido"). De uma vez, todas as peças de um grupo do modelo:

* **terças** — outro Ue (maior, menor) ou a **cartola**: a terça continua sentada nos apoios (a face de baixo não sai do
  lugar; o eixo sobe ou desce a diferença) e a cartola fica com o chapéu para cima;
* **banzo superior / banzo inferior** — outro perfil; as pontas seguem o banzo (regra 1.4) e as almas são encaixadas de
  novo na face nova (regra 3.1a);
* **montantes / diagonais** — outro perfil, ou **cantoneira dupla** no lugar do U (uma em cada aba do banzo, abas de pé
  para o centro, presilhas pela norma 5.3.6.1 — regra 2.5), ou o contrário: o par volta a ser um U só;
* **os outros papéis** (contraventamento, escora, apoio de terça, pilar, viga…) — só o perfil.

Depois da troca, as treliças tocadas passam pelas regras de montagem (nucleo3d/regras_trelica.aplicar: classificar,
orientar, recuar da platibanda, encaixar); o peso de cada peça é refeito; as peças trocadas ficam com a marca "a conferir"
(o Numerar decide se a posição inteira mudou junta e fica com a marca velha, ou se separou) e as peças novas (o par de
cantoneiras, as presilhas) saem sem posição, com o conjunto da tesoura.

Nada altera o documento recebido: `aplicar` devolve {"novas", "alterar", "remover", "resumo", "avisos"} para o editor
aplicar numa entrada de desfazer — como as ferramentas de nucleo3d/modelagem.py.
"""
from __future__ import annotations

import collections
import copy
import math
import re
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados

# os grupos com regra própria, na ordem da tela; os outros papéis entram depois, pelo nome do papel
GRUPOS = (
    ("tercas", "Terças"),
    ("banzo_sup", "Banzo superior"),
    ("banzo_inf", "Banzo inferior"),
    ("montantes", "Montantes"),
    ("diagonais", "Diagonais"),
)
ALMA = ("montantes", "diagonais")
_FORA = {"presilha", "extremidade"}              # a presilha vai com o par; a ponta segue o banzo (1.4)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _r(p):
    return tuple(round(float(x), 3) for x in p)


# ------------------------------------------------------------------ os grupos
def grupo_da_barra(b) -> Optional[str]:
    """o grupo da troca: 'tercas', 'banzo_sup', 'banzo_inf', 'montantes', 'diagonais', 'papel:<papel>' ou None (a
    presilha e a ponta da treliça, que seguem as outras)"""
    a = getattr(b, "atributos", None) or {}
    pt = str(a.get("papel_trelica") or "")
    papel = str(getattr(b, "papel", "") or "")
    if pt in _FORA or papel in _FORA:
        return None
    if papel.lower() in ("terça", "terca"):
        return "tercas"
    if pt in ("banzo_sup", "banzo_inf"):
        return pt
    if a.get("um_lado_so") or pt == "secundaria":
        return "papel:" + (papel or "barra")       # a barra "um lado só" (o suporte de terça do Docas): só o perfil
    if pt == "montante" or (not pt and papel == "montante"):
        return "montantes"
    if pt == "diagonal" or (not pt and papel == "diagonal"):
        return "diagonais"
    return "papel:" + (papel or "barra")


def rotulo_do_grupo(g: str) -> str:
    for k, r in GRUPOS:
        if k == g:
            return r
    p = g.partition(":")[2]
    return (p[:1].upper() + p[1:]) if p else "Barras"


# o tipo da treliça pela marca do conjunto (os nomes decididos em 16/10: T.n, MT.n, P.n, VT.n, VL.n) — no Mercado o banzo
# superior em U 100×50 é das tesouras e das platibandas, e o estudo troca um sem o outro
TIPOS = {"T": "tesouras", "MT": "meias-tesouras", "P": "platibandas e fechamentos", "VT": "vigas de transição",
         "VL": "vigas laterais"}


def tipo_da_trelica(b) -> str:
    """'T', 'MT', 'P', 'VT', 'VL'… pela marca do conjunto da peça; '' sem conjunto com nome"""
    m = ((getattr(b, "atributos", None) or {}).get("marcas") or {})
    c = str(m.get("conjunto") or "") if isinstance(m, dict) else ""
    r = re.match(r"^([A-Za-z]+(?:\.[A-Za-z]+)*)\.?\d", c.strip())
    return r.group(1).upper() if r else ""


def _dupla(b) -> bool:
    return bool((getattr(b, "atributos", None) or {}).get("cantoneira_dupla"))


_MASSAS: Dict[str, float] = {}


def _peso(b) -> float:
    """o peso pelo eixo (kg/m × comprimento) — o dos totais da tela; o exato, pela peça cortada (geometria.peso_barra),
    fica só no `peso_kg` das peças trocadas: no Mercado a malha de 11 mil barras levava 18 s"""
    k = str(b.perfil or "")
    if k not in _MASSAS:
        try:
            from nucleo3d.geometria import resolver_perfil
            _MASSAS[k] = float(resolver_perfil(k).massa or 0.0)
        except Exception:                                # noqa: BLE001 — perfil sem massa conhecida
            _MASSAS[k] = 0.0
    return _MASSAS[k] * math.dist(b.inicio, b.fim) / 1000.0


def _peso_exato(b) -> float:
    try:
        from nucleo3d.geometria import peso_barra
        return float(peso_barra(b))
    except Exception:                                    # noqa: BLE001
        return _peso(b)


def grupos(doc) -> List[dict]:
    """os grupos do modelo, por perfil: [{grupo, rotulo, perfis: [{perfil, forma, pecas, metros, kg}], pecas, kg}].
    `forma` = 'dupla' no par de cantoneiras (as duas contam como peças)"""
    from nucleo3d.modelo import Barra
    por = collections.defaultdict(lambda: collections.defaultdict(lambda: {"pecas": 0, "metros": 0.0, "kg": 0.0}))
    for e in doc.entidades.values():
        if not isinstance(e, Barra):
            continue
        g = grupo_da_barra(e)
        if g is None:
            continue
        tipo = tipo_da_trelica(e) if g in ("banzo_sup", "banzo_inf") + ALMA else ""
        r = por[g][(tipo, str(e.perfil), "dupla" if _dupla(e) else "simples")]
        r["pecas"] += 1
        r["metros"] += math.dist(e.inicio, e.fim) / 1000.0
        r["kg"] += _peso(e)
    ordem = [k for k, _ in GRUPOS] + sorted(k for k in por if k not in dict(GRUPOS))
    out = []
    for g in ordem:
        if g not in por:
            continue
        perfis = [{"perfil": p, "forma": f, "tipo": tp, "tipo_rotulo": TIPOS.get(tp, tp), "pecas": v["pecas"],
                   "metros": round(v["metros"], 2), "kg": round(v["kg"], 1)}
                  for (tp, p, f), v in sorted(por[g].items(), key=lambda kv: (kv[0][0], -kv[1]["kg"]))]
        out.append({"grupo": g, "rotulo": rotulo_do_grupo(g), "perfis": perfis,
                    "pecas": sum(p["pecas"] for p in perfis), "kg": round(sum(p["kg"] for p in perfis), 1)})
    return out


# ------------------------------------------------------------------ a seção
def _resolver(nome: str):
    from nucleo3d.geometria import resolver_perfil
    try:
        return resolver_perfil(nome)
    except Exception as exc:                              # noqa: BLE001
        raise ErroDeDados("perfil %s fora do catálogo: %s" % (nome, exc))


def familia(perfil: str) -> str:
    """'L', 'U' (U e Ue), 'Cr' (cartola) ou '' — pelo nome"""
    p = str(perfil or "").strip()
    if re.match(r"(?i)^cr\s", p):
        return "Cr"
    if re.match(r"(?i)^ue?\s", p):
        return "U"
    if re.match(r"(?i)^l\s", p):
        return "L"
    return ""


def _extensao(perfil: str, rotacao: float, w, direcao) -> float:
    """quanto o material da seção (girada) vai do eixo da barra na direção dada, em mm"""
    from nucleo3d.geometria import base_local, secao
    pts = secao(_resolver(perfil))
    u, v, _w = base_local(w, rotacao)
    return max(_dot(_add(_mul(u, x), _mul(v, y)), direcao) for x, y in pts)


def _trocar(b, perfil: str):
    """o perfil novo com o peso refeito e a marca do perfil; a posição fica para o Numerar conferir"""
    from nucleo3d.regras_trelica import _trocar_perfil
    _trocar_perfil(b, perfil)
    a = b.atributos if isinstance(b.atributos, dict) else {}
    b.atributos = a
    if isinstance(a.get("marcas"), dict) and a["marcas"].get("posicao"):
        a["marca_a_conferir"] = True


# ------------------------------------------------------------------ terças
def _trocar_terca(b, novo: str):
    """a terça com o perfil novo, sentada no mesmo lugar: a face de baixo (a que encosta no apoio) fica; a cartola com o
    chapéu para cima (o eixo v da seção para o lado de cima da água)"""
    from nucleo3d.geometria import base_local
    from nucleo3d.modelagem import _rotacao_para_v
    w = _unit(_sub(b.fim, b.inicio))
    rot0 = float(b.rotacao or 0.0)
    u, v, _ = base_local(w, rot0)
    cima = u if abs(u[2]) > abs(v[2]) else v              # o eixo da seção mais perto da vertical: o "para cima" da água
    if cima[2] < 0:
        cima = _mul(cima, -1.0)
    baixo = _mul(cima, -1.0)
    rot1 = rot0
    if familia(novo) == "Cr":
        rot1 = _rotacao_para_v(w, cima)                   # o chapéu (v da seção) para cima
    elif familia(str(b.perfil)) == "Cr" and familia(novo) == "U":
        rot1 = _rotacao_para_v(w, cima)                   # o Ue volta com a alma perpendicular à água
    try:
        e0 = _extensao(str(b.perfil), rot0, w, baixo)
        e1 = _extensao(novo, rot1, w, baixo)
    except ErroDeDados:
        e0 = e1 = 0.0
    d = e1 - e0                                           # o eixo sobe o quanto a seção nova desce mais
    if abs(d) > 0.01:
        b.inicio = _r(_add(b.inicio, _mul(cima, d)))
        b.fim = _r(_add(b.fim, _mul(cima, d)))
    b.rotacao = round(rot1 % 360.0, 3)
    _trocar(b, novo)


# ------------------------------------------------------------------ o par de cantoneiras
def _afastamento(perfil_banzo: Optional[str], perfil_l: str) -> Tuple[float, float]:
    """(afastamento de cada cantoneira do plano, largura da presilha): encostadas na face de dentro das abas do banzo em
    U — a mesma conta do gerador pela planta (de_planta_estrutura, cantoneira dupla)"""
    try:
        pl = _resolver(perfil_l)
        bf = float(pl.bf or 0.0)
    except ErroDeDados:
        bf = 25.0
    afast = 0.0
    if perfil_banzo:
        try:
            pu = _resolver(perfil_banzo)
            afast = max(float(pu.d or 0.0) / 2.0 - float(pu.tf or pu.tw or 0.0) - bf / 2.0, 0.0)
        except ErroDeDados:
            afast = 0.0
    return afast, 2.0 * afast + bf


def _atributos_novos(a: dict, perfil: str, **extra) -> dict:
    """os atributos da peça nova a partir da que sai: o bloco, a tesoura e o conjunto ficam; a posição sai (o Numerar dá)"""
    at = copy.deepcopy(a or {})
    for k in ("cantoneira_dupla", "presilha_de", "marca_a_conferir", "peso_kg"):
        at.pop(k, None)
    m = at.get("marcas")
    if isinstance(m, dict):
        at["marcas"] = {k: v for k, v in m.items() if k not in ("posicao", "perfil")}
        at["marcas"]["perfil"] = perfil
    at.update(extra)
    return at


def _fazer_par(A, B, perfil: str, n, perfil_banzo, modelo) -> list:
    """as duas cantoneiras (uma em cada aba do banzo) e as presilhas entre elas, no eixo A–B da alma; `modelo` é a
    barra que sai (papel, aço, camada, nome e atributos)"""
    from nucleo3d.de_planta import _presilhas_pela_norma
    from nucleo3d.modelo import Barra
    afast, larg = _afastamento(perfil_banzo, perfil)
    nome0 = re.sub(r"\s*\((a|b)\)\s*$", "", str(modelo.nome or ""))
    out = []
    for lado in (-1.0, 1.0):
        dl = _mul(n, lado * afast)
        out.append(Barra(inicio=_r(_add(A, dl)), fim=_r(_add(B, dl)), perfil=perfil, papel=modelo.papel, aco=modelo.aco,
                         camada=modelo.camada, material=modelo.material, nome=nome0 + (" (a)" if lado < 0 else " (b)"),
                         rotacao=0.0, grupo=modelo.grupo,
                         atributos=_atributos_novos(modelo.atributos, perfil, cantoneira_dupla="a" if lado < 0 else "b")))
    n_p = _presilhas_pela_norma(perfil)
    for k in range(1, n_p + 1):
        f = k / (n_p + 1.0)
        c = tuple(A[i] + (B[i] - A[i]) * f for i in range(3))
        out.append(Barra(inicio=_r(_add(c, _mul(n, -larg / 2.0))), fim=_r(_add(c, _mul(n, larg / 2.0))), perfil=perfil,
                         papel="presilha", aco=modelo.aco, camada=modelo.camada, material=modelo.material,
                         nome="%s presilha %d" % (nome0, k), rotacao=0.0, grupo=modelo.grupo,
                         atributos=_atributos_novos(modelo.atributos, perfil, presilha_de=perfil, papel_trelica="presilha")))
    return out


def _parceira_e_presilhas(b, todas) -> Tuple[Optional[object], list]:
    """a outra cantoneira do par de `b` (mesmo perfil, paralela, lado a lado) e as presilhas entre as duas"""
    w = _unit(_sub(b.fim, b.inicio))
    L = math.dist(b.inicio, b.fim)
    mb = _mul(_add(b.inicio, b.fim), 0.5)
    melhor, dmin = None, 1e9
    for o in todas:
        if o is b or not _dupla(o) or str(o.perfil) != str(b.perfil):
            continue
        if (o.atributos or {}).get("cantoneira_dupla") == (b.atributos or {}).get("cantoneira_dupla"):
            continue
        wo = _unit(_sub(o.fim, o.inicio))
        if abs(_dot(w, wo)) < 0.995 or abs(math.dist(o.inicio, o.fim) - L) > 0.25 * L:
            continue
        d = math.dist(_mul(_add(o.inicio, o.fim), 0.5), mb)
        if d < 300.0 and d < dmin:
            melhor, dmin = o, d
    pres = []
    if melhor is not None:
        from nucleo3d.regras_trelica import _dist_pt_seg
        A, B = _eixo_do_par(b, melhor)
        for o in todas:
            eh = str((o.atributos or {}).get("papel_trelica") or "") == "presilha" or str(o.papel) == "presilha"
            if not eh or str((o.atributos or {}).get("presilha_de") or o.perfil) != str(b.perfil):
                continue
            # o meio da presilha no eixo do par (ela atravessa as duas cantoneiras)
            if _dist_pt_seg(_mul(_add(o.inicio, o.fim), 0.5), A, B) < 60.0:
                pres.append(o)
    return melhor, pres


def _eixo_do_par(a, b) -> Tuple[tuple, tuple]:
    """o eixo da alma do par: o meio das pontas correspondentes"""
    if math.dist(a.inicio, b.inicio) <= math.dist(a.inicio, b.fim):
        p, q = b.inicio, b.fim
    else:
        p, q = b.fim, b.inicio
    return _r(_mul(_add(a.inicio, p), 0.5)), _r(_mul(_add(a.fim, q), 0.5))


# ------------------------------------------------------------------ aplicar
def _normais(doc) -> Dict[int, tuple]:
    """{id(barra): (n do plano da treliça, perfil do banzo superior)} para as peças das treliças do modelo"""
    from nucleo3d import regras_trelica as RT
    out = {}
    for t in RT.trelicas(list(doc.entidades.values())):
        pb = RT.perfil_do_banzo(t)
        for b, _p in t["barras"]:
            out[id(b)] = (t["n"], pb)
    return out


def _normal_de_reserva(b) -> tuple:
    """sem a treliça reconhecida: a horizontal perpendicular à peça"""
    w = _unit(_sub(b.fim, b.inicio))
    n = _unit((-w[1], w[0], 0.0)) if abs(w[2]) < 0.99 else (1.0, 0.0, 0.0)
    return n if n != (0.0, 0.0, 0.0) else (1.0, 0.0, 0.0)


def aplicar(doc, trocas: List[dict]) -> dict:
    """as trocas [{grupo, de ('' = todos os perfis do grupo), tipo (o tipo da treliça, T/P/VT…; ausente = todos), para
    ('' = o mesmo perfil), forma ('simples' | 'dupla' | '' = a mesma)}] no modelo. Devolve {"novas", "alterar", "remover", "resumo": {grupos: [...], kg_antes, kg_depois,
    pecas, regras}, "avisos"} — o documento recebido também muda (é uma cópia do editor)"""
    from nucleo3d import regras_trelica as RT
    from nucleo3d.modelo import Barra
    trocas = [t for t in (trocas or []) if t and t.get("grupo") and (t.get("para") or t.get("forma"))]
    if not trocas:
        raise ErroDeDados("nada a trocar: escolha o perfil novo (ou a forma) de algum grupo.")
    for t in trocas:
        if t.get("para"):
            _resolver(str(t["para"]))
        if t.get("forma") == "dupla" and t.get("grupo") not in ALMA:
            raise ErroDeDados("a cantoneira dupla é só para os montantes e as diagonais.")
        if t.get("forma") == "dupla" and familia(t.get("para") or "") != "L":
            raise ErroDeDados("cantoneira dupla: escolha o perfil da cantoneira (L …).")
        if t.get("forma") == "simples" and t.get("grupo") in ALMA and not t.get("para"):
            raise ErroDeDados("o par de cantoneiras volta a ser uma peça só: escolha o perfil dela (U …).")
    barras = [e for e in doc.entidades.values() if isinstance(e, Barra)]
    antes = {e.id: e.dict() for e in barras}
    kg_antes = sum(_peso(e) for e in barras)
    normais = _normais(doc)
    avisos: List[str] = []
    novas_ents, removidas = [], set()
    tocadas = set()                                       # ids das barras trocadas (as treliças delas passam pelas regras)
    por_grupo = collections.Counter()

    def casa(e, t) -> bool:
        return (grupo_da_barra(e) == t["grupo"] and (not t.get("de") or str(e.perfil) == str(t["de"]))
                and (t.get("tipo") is None or tipo_da_trelica(e) == str(t["tipo"])))

    for t in trocas:
        para = str(t.get("para") or "")
        forma = str(t.get("forma") or "")
        alvo = [e for e in barras if e.id not in removidas and casa(e, t)]
        feitos = set()
        for e in alvo:
            if e.id in feitos or e.id in removidas:
                continue
            n, pb = normais.get(id(e)) or (_normal_de_reserva(e), None)
            if t["grupo"] in ALMA and _dupla(e):
                par, pres = _parceira_e_presilhas(e, barras)
                if par is None:
                    avisos.append("%s: a outra cantoneira do par não foi achada; trocada sozinha" % (e.nome or e.id))
                    if para:
                        _trocar(e, para)
                        tocadas.add(e.id)
                        por_grupo[t["grupo"]] += 1
                    feitos.add(e.id)
                    continue
                A, B = _eixo_do_par(e, par)
                for x in [e, par] + pres:
                    removidas.add(x.id)
                    feitos.add(x.id)
                if forma == "simples":                    # o par volta a ser um U só, no eixo da alma
                    nova = Barra(inicio=A, fim=B, perfil=para, papel=e.papel, aco=e.aco, camada=e.camada,
                                 material=e.material, nome=re.sub(r"\s*\((a|b)\)\s*$", "", str(e.nome or "")),
                                 rotacao=0.0, grupo=e.grupo, atributos=_atributos_novos(e.atributos, para))
                    novas_ents.append(nova)
                else:                                     # outro par (outra cantoneira): refeito pelo banzo
                    novas_ents.extend(_fazer_par(A, B, para or str(e.perfil), n, pb, e))
                por_grupo[t["grupo"]] += 1
                continue
            if t["grupo"] in ALMA and forma == "dupla":   # o U vira o par de cantoneiras
                removidas.add(e.id)
                feitos.add(e.id)
                novas_ents.extend(_fazer_par(tuple(e.inicio), tuple(e.fim), para, n, pb, e))
                por_grupo[t["grupo"]] += 1
                continue
            if not para or para == str(e.perfil):
                continue
            if t["grupo"] == "tercas":
                _trocar_terca(e, para)
            else:
                _trocar(e, para)
            tocadas.add(e.id)
            feitos.add(e.id)
            por_grupo[t["grupo"]] += 1

    for i in removidas:
        doc.entidades.pop(i, None)
    for e in novas_ents:
        doc.add(e)

    # as treliças tocadas passam pelas regras de montagem (1.2/1.4, 2.x, 4.8 e o encaixe 3.1a): só as peças do mesmo
    # bloco/conjunto das trocadas — o resto do modelo não se mexe
    chaves = set()
    for e in list(novas_ents) + [doc.entidades[i] for i in tocadas if i in doc.entidades]:
        if grupo_da_barra(e) in ("tercas",) or str(getattr(e, "papel", "")).lower() in ("terça", "terca"):
            continue
        chaves.add(RT._chave_grupo(e))
        peca = ((e.atributos or {}).get("origem") or {}).get("peca") if isinstance((e.atributos or {}).get("origem"), dict) else None
        if peca:
            chaves.add(("peca", str(peca)))
    regras = (0, 0, 0, 0)
    if chaves:
        lista = []
        for e in doc.entidades.values():
            if not isinstance(e, Barra):
                continue
            a = e.atributos or {}
            o = a.get("origem") if isinstance(a.get("origem"), dict) else {}
            if RT._chave_grupo(e) in chaves or (o.get("peca") and ("peca", str(o["peca"])) in chaves):
                lista.append(e)
        regras = RT.aplicar(lista)
    # o peso de cada peça que mudou e a marca a conferir das que a regra trocou (a ponta seguiu o banzo)
    depois = [e for e in doc.entidades.values() if isinstance(e, Barra)]
    novas_ids = {e.id for e in novas_ents}
    alterar = {}
    for e in depois:
        if e.id in novas_ids or e.id not in antes:
            continue
        d1 = e.dict()
        d0 = antes[e.id]
        if d1.get("perfil") != d0.get("perfil"):
            a = d1.get("atributos") or {}
            if isinstance(a.get("marcas"), dict) and a["marcas"].get("posicao"):
                a["marca_a_conferir"] = True
                a["marcas"]["perfil"] = d1["perfil"]
            if "peso_kg" in a:
                a["peso_kg"] = round(_peso_exato(e), 2)
            a["trocas_de_perfil"] = list(a.get("trocas_de_perfil") or []) + [
                {"de": d0.get("perfil"), "para": d1.get("perfil"), "como": "trocar perfis por grupo"}]
            d1["atributos"] = a
        mud = {k: v for k, v in d1.items() if k != "id" and d0.get(k) != v}
        if mud:
            alterar[e.id] = mud
    kg_depois = sum(_peso(e) for e in depois)
    g_depois = {g["grupo"]: g for g in grupos(doc)}
    linhas = []
    for t in trocas:
        g = t["grupo"]
        linhas.append({"grupo": g, "rotulo": rotulo_do_grupo(g), "de": t.get("de") or "todos",
                       "para": t.get("para") or "", "forma": t.get("forma") or "", "pecas": por_grupo.get(g, 0),
                       "kg_depois": (g_depois.get(g) or {}).get("kg", 0.0)})
        if not por_grupo.get(g):
            avisos.append("%s%s: nenhuma peça mudou" % (rotulo_do_grupo(g), (" " + t["de"]) if t.get("de") else ""))
    return {"novas": [e.dict() for e in novas_ents], "alterar": alterar, "remover": sorted(removidas),
            "resumo": {"grupos": linhas, "kg_antes": round(kg_antes, 1), "kg_depois": round(kg_depois, 1),
                       "pecas": sum(por_grupo.values()), "regras": {"reclassificadas": regras[0], "giradas": regras[1],
                                                                    "recuadas": regras[2], "encaixadas": regras[3]}},
            "avisos": avisos}
