# -*- coding: utf-8 -*-
"""A informação de produção feita à mão no editor 3D: numerar as peças e achar onde duas peças se encostam (a solda).

Onda 1 da análise de 14/10/2026 (Projeto/ANALISES/Editor-3D/Ferramentas-que-faltam-editor-3D-2026-10-14.pdf): o
detalhamento lê a marca de posição, a de conjunto e a solda de cada peça, e até aqui só os geradores (Lançar
estrutura, montagem pela planta, importação do IFC) escreviam essas marcas. Decisões do usuário (14/10): numerar só
quando ele pede, com a numeração travada depois da emissão; conjunto é comando próprio (o Agrupar só organiza a tela);
solda à mão só onde ele quiser, o resto o detalhamento deduz.

**Numerar.** "Peça igual" é o mesmo critério do detalhamento (`nucleo2d.detalhe.base.fundir_posicoes_iguais`): cada
peça a classificar é analisada sozinha, como se fosse uma posição (perfil, material, furos — inclusive os dos parafusos
que passam por ela —, comprimento, volume, contorno da chapa), e comparada com uma peça de cada posição que já existe.
A peça sem marca recebe a marca da posição igual a ela, ou uma nova (P + o próximo número). A peça com marca só muda
quando a ferramenta que a alterou deixou `atributos.marca_a_conferir` (Empurrar/Puxar, Escalar, Encaixar — combinado com
o chat das ferramentas) e ela deixou de ser igual às outras da posição. As marcas existentes nunca são renumeradas, a
não ser em `compactar` (Renumerar tudo), recusado com a numeração travada.

**Conjunto.** O conjunto feito no editor grava `marcas.instancia` (uma por cópia do conjunto) — o detalhamento já usa a
instância dita pelo modelo em vez de adivinhar pela conta das quantidades (detalhar._instancias_pelo_grupo). Instâncias
com a mesma composição de posições recebem a mesma marca de conjunto (M + número). A peça fora de conjunto é o conjunto
dela mesma: uma marca de conjunto por posição, como no lançamento.

**Solda.** `contatos` mede onde as peças se encostam com as funções do detalhamento (nucleo2d/detalhe/soldas.py): T e
sobreposição chapa × perfil, e o contorno do encontro perfil × perfil (a diagonal no banzo). A solda definida fica
gravada nas duas peças, pela posição da outra (`atributos.soldas = {"P12": {...}}`): as cópias do conjunto levam a solda
junto, e o detalhamento a aplica em todas as instâncias (soldas.definicao).
"""
import collections
import dataclasses
import math
import re
from typing import Dict, List, Optional, Sequence

#: tipos de solda e locais aceitos na definição
TIPOS_SOLDA = ("filete", "penetracao")
LOCAIS_SOLDA = ("fabrica", "obra", "nenhuma")

_RE_P = re.compile(r"^P(\d+)$")
_RE_M = re.compile(r"^M(\d+)$")


# ------------------------------------------------------------------ peças

def pecas_de_producao(doc) -> list:
    """As entidades que viram posição no detalhamento: Barra e Chapa paramétricas e os sólidos de aço com tipo de peça
    (a mesma escolha de nucleo2d.detalhe.base._pecas, sem montar malha nenhuma)."""
    from nucleo3d.modelo import Barra, Chapa, Solido
    from nucleo2d.detalhe.base import TIPOS_PECA, _tipo_ifc
    from nucleo2d.detalhe.fora_do_aco import material_nao_aco
    fora = []
    for e in doc.entidades.values():
        a = e.atributos or {}
        if a.get("tipo") in ("cota", "construcao") or a.get("furo"):
            continue
        if isinstance(e, Barra):
            if (_tipo_ifc(e) or e.tipo_ifc()) in TIPOS_PECA:
                fora.append(e)
        elif isinstance(e, Chapa):
            if (_tipo_ifc(e) or "IfcPlate") in TIPOS_PECA:
                fora.append(e)
        elif isinstance(e, Solido):
            if _tipo_ifc(e) in TIPOS_PECA and material_nao_aco(e) is None and len(e.vertices or []) >= 4:
                fora.append(e)
    return fora


def perfil_de(e) -> str:
    """O perfil como o detalhamento escreve: o da barra, "CH t" na chapa, o das marcas no sólido."""
    from nucleo3d.modelo import Barra, Chapa
    m = (e.atributos or {}).get("marcas") or {}
    if m.get("perfil"):
        return str(m["perfil"])
    if isinstance(e, Barra):
        return str(e.perfil)
    if isinstance(e, Chapa):
        return "CH %s" % ("%g" % round(float(e.espessura), 2)).replace(".", ",")
    return str(e.nome or "")


def _chave_perfil(e) -> str:
    return re.sub(r"\s+", "", perfil_de(e)).upper()


def _proxy(e):
    """O sólido do detalhamento da peça, com os atributos copiados (a marca provisória não toca no modelo)."""
    from nucleo3d.modelo import Barra, Chapa
    from nucleo2d.detalhe.base import _proxy_da_barra, _proxy_da_chapa
    if isinstance(e, Barra):
        s = _proxy_da_barra(e)
    elif isinstance(e, Chapa):
        s = _proxy_da_chapa(e)
    else:
        s = dataclasses.replace(e, atributos=dict(e.atributos or {}))
    s.atributos = dict(s.atributos or {})
    s.atributos["marcas"] = dict(s.atributos.get("marcas") or {})
    return s


def analisar(ents: Sequence, fixadores: Sequence) -> Dict[str, object]:
    """{id: Posicao} — cada peça analisada sozinha (marca provisória "#id"), com os furos dos parafusos que passam por
    ela. Peça que não se monta fica de fora."""
    from nucleo2d.detalhe.base import _posicoes_de
    proxies = []
    for e in ents:
        try:
            s = _proxy(e)
        except Exception:                                 # noqa: BLE001 — peça degenerada não derruba a numeração
            continue
        s.atributos["marcas"]["posicao"] = "#" + e.id
        if not s.atributos["marcas"].get("perfil"):
            s.atributos["marcas"]["perfil"] = perfil_de(e)
        proxies.append(s)
    if not proxies:
        return {}
    posicoes, _ = _posicoes_de(proxies, list(fixadores))
    return {p.marca[1:]: p for p in posicoes}


def mesma_peca(p, q) -> bool:
    """O critério de `fundir_posicoes_iguais`: assinatura, comprimento a 1 mm, volume a 1 %, contorno da chapa."""
    from nucleo2d.detalhe.base import TOLERANCIA_COMPRIMENTO, _assinatura_posicao, _contorno_igual, _volume_igual
    if p is None or q is None or p.classe == "indefinida" or q.classe == "indefinida":
        return False
    if _assinatura_posicao(p) != _assinatura_posicao(q):
        return False
    if abs(float(p.comprimento or 0) - float(q.comprimento or 0)) > TOLERANCIA_COMPRIMENTO:
        return False
    return _volume_igual(p, q) and _contorno_igual(p, q)


def _natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


class _Contador:
    """O próximo número livre de um prefixo (P, M), sem repetir marca nenhuma do modelo."""

    def __init__(self, prefixo: str, regex, usadas: set):
        self.prefixo, self.usadas = prefixo, usadas
        nums = [int(m.group(1)) for m in (regex.match(u) for u in usadas) if m]
        self.n = max(nums) if nums else 0

    def novo(self) -> str:
        while True:
            self.n += 1
            marca = "%s%d" % (self.prefixo, self.n)
            if marca not in self.usadas:
                self.usadas.add(marca)
                return marca


# ------------------------------------------------------------------ numerar

def numerar(doc, compactar: bool = False, conferir_todas: bool = False, avisar=None) -> dict:
    """Dá marca de posição e de conjunto às peças que não têm e separa as que mudaram. Não altera o `doc`: devolve
    {"mudancas": {id: {campo de atributos: valor | None}}, "resumo", "avisos"} para o editor aplicar com desfazer
    (None = apagar o campo). `compactar` renumera tudo de P1/M1 (recusado com a numeração travada)."""
    from nucleo2d.detalhe.base import _fixadores
    avisar = avisar or (lambda *a: None)
    travada = bool(((getattr(doc, "metadados", None) or {}).get("numeracao") or {}).get("travada"))
    if compactar and travada:
        raise ValueError("a numeração está travada (projeto emitido): destrave em Editar → Numeração travada para "
                         "renumerar tudo")
    pecas = pecas_de_producao(doc)
    marcas_ant = {e.id: dict((e.atributos or {}).get("marcas") or {}) for e in pecas}
    pos_ant = {i: str(m.get("posicao") or "") for i, m in marcas_ant.items()}
    a_conferir = {e.id for e in pecas if (e.atributos or {}).get("marca_a_conferir")}
    alvos = [e for e in pecas if conferir_todas or not pos_ant[e.id] or e.id in a_conferir]
    ids_alvo = {e.id for e in alvos}
    membros: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        if pos_ant[e.id]:
            membros[pos_ant[e.id]].append(e)
    # uma peça de cada posição existente que não está em conferência, só dos perfis que interessam
    chaves = {_chave_perfil(e) for e in alvos}
    reps = {}
    for pos, ents in membros.items():
        firmes = [e for e in ents if e.id not in ids_alvo]
        if firmes and _chave_perfil(firmes[0]) in chaves:
            reps[pos] = firmes[0]
    avisos: List[str] = []
    fixadores = _fixadores(doc)
    avisar("analisando %d peça(s)…" % (len(alvos) + len(reps)))
    analise = analisar(alvos + list(reps.values()), fixadores) if alvos else {}
    usadas_p = {p for p in pos_ant.values() if p}
    cont_p = _Contador("P", _RE_P, usadas_p)
    pos_novo = dict(pos_ant)
    novos: List[dict] = []                               # [{"q": Posicao, "ents": [...]}]
    ordem = sorted(alvos, key=lambda e: (_natural(pos_ant[e.id] or "~"), e.id))
    for e in ordem:
        q = analise.get(e.id)
        if q is None or q.classe == "indefinida":
            if not pos_ant[e.id]:
                pos_novo[e.id] = cont_p.novo()
                avisos.append("%s: a geometria não se analisa — recebeu a marca %s sozinha, confira" % (e.nome or e.id, pos_novo[e.id]))
            continue
        velha = pos_ant[e.id]
        if velha in reps and mesma_peca(analise.get(reps[velha].id), q):
            pos_novo[e.id] = velha
            continue
        achada = next((pos for pos in sorted(reps, key=_natural) if mesma_peca(analise.get(reps[pos].id), q)), None)
        if achada:
            pos_novo[e.id] = achada
            continue
        g = next((g for g in novos if mesma_peca(g["q"], q)), None)
        if g is None:
            novos.append({"q": q, "ents": [e]})
        else:
            g["ents"].append(e)
    # cada grupo novo fica com a marca velha que ninguém mais usa (a posição inteira que mudou junta) ou ganha uma nova
    reivindicadas = set(reps)
    for g in sorted(novos, key=lambda g: -len(g["ents"])):
        velhas = collections.Counter(pos_ant[e.id] for e in g["ents"] if pos_ant[e.id])
        marca = next((m for m, _ in velhas.most_common() if m not in reivindicadas), None)
        if marca is None:
            marca = cont_p.novo()
        reivindicadas.add(marca)
        for e in g["ents"]:
            pos_novo[e.id] = marca
    separadas = sorted({(pos_ant[e.id], pos_novo[e.id]) for e in pecas
                        if pos_ant[e.id] and pos_novo[e.id] != pos_ant[e.id]}, key=lambda t: _natural(t[0]))
    for velha, nova in separadas:
        avisos.append("%s → %s: a peça mudou e deixou de ser igual às outras %s" % (velha, nova, velha))
    conj_novo = _conjuntos(pecas, marcas_ant, pos_ant, pos_novo, avisos)
    # os parafusos que levam a marca do conjunto da peça em que foram postos
    mapa_conj: Dict[str, str] = {}
    if compactar:
        pos_novo, conj_novo, mapa_pos, mapa_conj = _compactar(pecas, pos_novo, conj_novo)
    else:
        mapa_pos = {}
    mudancas: Dict[str, dict] = {}
    for e in pecas:
        m = dict(marcas_ant[e.id])
        m["posicao"] = pos_novo[e.id]
        m["conjunto"] = conj_novo[e.id]
        if not m.get("perfil"):
            m["perfil"] = perfil_de(e)
        patch = {}
        if m != marcas_ant[e.id]:
            patch["marcas"] = m
        if e.id in a_conferir:
            patch["marca_a_conferir"] = None
        sold = (e.atributos or {}).get("soldas")
        if mapa_pos and isinstance(sold, dict):
            novo_s = {mapa_pos.get(k, k): v for k, v in sold.items()}
            if novo_s != sold:
                patch["soldas"] = novo_s
        if patch:
            mudancas[e.id] = patch
    if mapa_conj:
        for f in fixadores:
            mf = dict((f.atributos or {}).get("marcas") or {})
            c = str(mf.get("conjunto") or "")
            if c and mapa_conj.get(c, c) != c:
                mf["conjunto"] = mapa_conj[c]
                mudancas[f.id] = {"marcas": mf}
    novas = sorted({pos_novo[e.id] for e in pecas if pos_novo[e.id] and pos_novo[e.id] not in set(pos_ant.values())},
                   key=_natural)
    resumo = {"pecas": len(pecas), "analisadas": len(alvos), "alteradas": len(mudancas),
              "posicoes": len({pos_novo[e.id] for e in pecas}), "conjuntos": len({conj_novo[e.id] for e in pecas}),
              "posicoes_novas": novas, "separadas": [list(t) for t in separadas], "compactada": bool(compactar)}
    return {"mudancas": mudancas, "resumo": resumo, "avisos": avisos}


def _conjuntos(pecas, marcas_ant, pos_ant, pos_novo, avisos) -> Dict[str, str]:
    """A marca de conjunto de cada peça: instâncias iguais (mesma composição de posições) com a mesma marca; peça solta
    no conjunto dela mesma (um por posição); o conjunto dos geradores fica como está."""
    conj_ant = {i: str(m.get("conjunto") or "") for i, m in marcas_ant.items()}
    inst = {i: str(m.get("instancia") or "") for i, m in marcas_ant.items()}
    cont_m = _Contador("M", _RE_M, {c for c in conj_ant.values() if c})
    conj = dict(conj_ant)
    # 1. os conjuntos feitos no editor (com instância)
    grupos: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        if inst[e.id]:
            grupos[inst[e.id]].append(e)
    por_comp: Dict[frozenset, str] = {}
    reivindicadas: Dict[str, frozenset] = {}

    def comp_de(g):
        return frozenset(collections.Counter(pos_novo[e.id] for e in g).items())
    ordem = sorted(grupos.values(), key=lambda g: (0 if any(conj_ant[e.id] for e in g) else 1,
                                                    _natural(min((conj_ant[e.id] for e in g), default=""))))
    for g in ordem:
        c = comp_de(g)
        marca = por_comp.get(c)
        if marca is None:
            atuais = collections.Counter(conj_ant[e.id] for e in g if conj_ant[e.id])
            marca = next((m for m, _ in atuais.most_common() if m not in reivindicadas), None) or cont_m.novo()
            por_comp[c] = marca
            reivindicadas[marca] = c
        for e in g:
            conj[e.id] = marca
    # 2. as soltas: o conjunto "solo" de cada posição (todas as peças dele da mesma posição, sem instância)
    por_conj: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        if conj_ant[e.id] and not inst[e.id]:
            por_conj[conj_ant[e.id]].append(e)
    solo_de_pos: Dict[str, str] = {}
    for c, es in por_conj.items():
        poss = {pos_novo[e.id] for e in es}
        if len(poss) == 1 and c not in reivindicadas and all(pos_ant[e.id] == pos_novo[e.id] for e in es):
            solo_de_pos.setdefault(next(iter(poss)), c)
    for e in sorted(pecas, key=lambda e: _natural(pos_novo[e.id])):
        if inst[e.id]:
            continue
        c = conj_ant[e.id]
        mudou = pos_ant[e.id] and pos_ant[e.id] != pos_novo[e.id]
        if c and c not in reivindicadas:
            solo = {pos_ant[x.id] for x in por_conj.get(c, [])} == {pos_ant[e.id]}
            if not (mudou and solo):
                if mudou:
                    avisos.append("conjunto %s: uma peça mudou de %s para %s — as cópias do conjunto deixaram de ser "
                                  "iguais; se for outra montagem, faça um conjunto à parte (Editar → Criar conjunto)"
                                  % (c, pos_ant[e.id], pos_novo[e.id]))
                continue
        pos = pos_novo[e.id]
        if pos not in solo_de_pos:
            solo_de_pos[pos] = cont_m.novo()
        conj[e.id] = solo_de_pos[pos]
    return conj


def _compactar(pecas, pos_novo, conj_novo):
    """Renumerar tudo: P1… na ordem das posições mais numerosas, M1… na das montagens com mais peças."""
    por_pos = collections.Counter(pos_novo[e.id] for e in pecas)
    perfil = {pos_novo[e.id]: _chave_perfil(e) for e in pecas}
    ordem_p = sorted(por_pos, key=lambda p: (-por_pos[p], perfil.get(p, ""), _natural(p)))
    mapa_pos = {p: "P%d" % (i + 1) for i, p in enumerate(ordem_p)}
    por_conj = collections.Counter(conj_novo[e.id] for e in pecas)
    ordem_m = sorted(por_conj, key=lambda c: (-por_conj[c], _natural(c)))
    mapa_conj = {c: "M%d" % (i + 1) for i, c in enumerate(ordem_m)}
    pos2 = {i: mapa_pos.get(p, p) for i, p in pos_novo.items()}
    conj2 = {i: mapa_conj.get(c, c) for i, c in conj_novo.items()}
    return pos2, conj2, mapa_pos, mapa_conj


# ------------------------------------------------------------------ solda: onde as peças se encostam

def _espessura_peca(s, n) -> float:
    from nucleo2d.detalhe import soldas as _s
    par = getattr(s, "parametrica", None)
    if par is not None and type(par).__name__ == "Chapa":
        return float(par.espessura)
    t = _s._espessura_do_perfil(s, n)
    return t or _s._espessura(s, n)


def _contorno_do_encontro(a, b) -> List[dict]:
    """Perfil × perfil (a diagonal com a ponta no banzo, a viga no pilar): os vértices de uma peça no plano de uma face
    da outra, dentro dela, fecham o encontro; o cordão é o contorno dele (filete em volta)."""
    from nucleo2d.detalhe import soldas as _s
    melhor = None
    for x, y in ((a, b), (b, a)):
        for g in _s.planos(x):
            n, d = g["n"], g["d"]
            pts = [q for q in y.vertices if abs(_s._dot(n, q) - d) <= _s.TOL_PLANO]
            if len(pts) < 3:
                continue
            e1, e2 = _s._base_do_plano(n)
            borda = [((_s._dot(x.vertices[i], e1), _s._dot(x.vertices[i], e2)), (_s._dot(x.vertices[j], e1), _s._dot(x.vertices[j], e2)))
                     for i, j in g["contorno"]]
            p2 = [(_s._dot(q, e1), _s._dot(q, e2), q) for q in pts]
            p2 = [t for t in p2 if _s._dentro(t[:2], borda) or _s._na_borda(t[:2], borda, tol=1.5)]
            if len(p2) < 3:
                continue
            casco = _casco([t[:2] for t in p2])
            if len(casco) < 3:
                continue
            perim = sum(math.dist(casco[i], casco[(i + 1) % len(casco)]) for i in range(len(casco)))
            if perim < _s.MENOR_CORDAO:
                continue
            if melhor is None or perim > melhor[0]:
                i_l = max(range(len(casco)), key=lambda i: math.dist(casco[i], casco[(i + 1) % len(casco)]))
                u0, u1 = casco[i_l], casco[(i_l + 1) % len(casco)]

                def p3(u, n=n, d=d, e1=e1, e2=e2):
                    return tuple(n[k] * d + e1[k] * u[0] + e2[k] * u[1] for k in range(3))
                t_a, t_b = _espessura_peca(x, n), _espessura_peca(y, n)
                melhor = (perim, {"tipo": "contorno", "lados": 1, "comprimento": round(perim, 1),
                                  "perna": _s._perna(t_a, t_b), "p0": p3(u0), "p1": p3(u1)})
    return [melhor[1]] if melhor else []


def _casco(pts):
    """casco convexo 2D (monotone chain)"""
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pts))
    if len(pts) < 3:
        return pts

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo, cima = [], []
    for p in pts:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pts):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


def cordoes_entre(a, b) -> List[dict]:
    """Os cordões possíveis entre duas peças do detalhamento (proxies): chapa × perfil pelo detalhamento; chapa × chapa
    nas duas ordens; perfil × perfil pelo contorno do encontro."""
    from nucleo2d.detalhe.montagens import _eh_chapa
    from nucleo2d.detalhe.soldas import cordoes_chapa_perfil
    ca, cb = _eh_chapa(a), _eh_chapa(b)
    cs: List[dict] = []
    try:
        if ca and not cb:
            cs = cordoes_chapa_perfil(a, b)
        elif cb and not ca:
            cs = cordoes_chapa_perfil(b, a)
        elif ca and cb:
            cs = cordoes_chapa_perfil(a, b) or cordoes_chapa_perfil(b, a)
    except Exception:                                     # noqa: BLE001 — a medida falhou: tenta o contorno
        cs = []
    if not cs:
        cs = _contorno_do_encontro(a, b)
    return [dict(c, p0=[round(v, 2) for v in c["p0"]], p1=[round(v, 2) for v in c["p1"]]) for c in cs]


def contatos(doc, ids: Sequence[str], folga: float = 1.0) -> List[dict]:
    """Os pares das peças `ids` que se encostam, com os cordões possíveis e a perna mínima (NBR 8800, Tabela 11)."""
    from nucleo2d.detalhe.base import _caixa
    ents = [doc.entidades[i] for i in ids if i in doc.entidades]
    prod = {e.id for e in pecas_de_producao(doc)}
    proxies = []
    for e in ents:
        if e.id not in prod:
            continue
        try:
            proxies.append(_proxy(e))
        except Exception:                                 # noqa: BLE001
            continue
    cx = {s.id: _caixa(s) for s in proxies}
    fora = []
    for i in range(len(proxies)):
        for j in range(i + 1, len(proxies)):
            a, b = proxies[i], proxies[j]
            if not all(cx[a.id][k][0] - folga <= cx[b.id][k][1] and cx[b.id][k][0] - folga <= cx[a.id][k][1] for k in range(3)):
                continue
            cs = cordoes_entre(a, b)
            if not cs:
                continue
            fora.append({"a": a.id, "b": b.id, "cordoes": cs,
                         "perna": max(c["perna"] for c in cs),
                         "comprimento": round(sum(c["comprimento"] for c in cs), 1)})
    return fora


def normalizar_definicao(d: dict) -> dict:
    """A definição de solda como o detalhamento lê: tipo, perna, lados, local, intermitente e a forma do encontro."""
    tipo = str(d.get("tipo") or "filete")
    local = str(d.get("local") or "fabrica")
    if tipo not in TIPOS_SOLDA:
        raise ValueError("tipo de solda desconhecido: %s" % tipo)
    if local not in LOCAIS_SOLDA:
        raise ValueError("local da solda desconhecido: %s" % local)
    fora = {"tipo": tipo, "local": local, "perna": round(float(d.get("perna") or 0), 1),
            "lados": 2 if int(d.get("lados") or 1) >= 2 else 1}
    if local != "nenhuma" and fora["perna"] <= 0:
        raise ValueError("a perna da solda precisa ser maior que zero")
    inter = d.get("intermitente")
    if inter:
        l_, p_ = float(inter.get("l") or 0), float(inter.get("passo") or 0)
        if not (0 < l_ < p_):
            raise ValueError("solda intermitente: o trecho precisa ser menor que o passo")
        fora["intermitente"] = {"l": round(l_), "passo": round(p_)}
    for k in ("forma", "comprimento", "p0", "p1", "data"):
        if d.get(k) is not None:
            fora[k] = d[k]
    return fora


# ------------------------------------------------------------------ converter em peça

def converter_em_chapa(doc, ids: Sequence[str]) -> dict:
    """Os sólidos `ids` (o retângulo empurrado, a placa desenhada à mão) viram Chapa paramétrica — contorno, espessura e
    furos medidos da malha, pela mesma conversão das chapas do IFC (celulas.converter_chapas). Não altera o `doc`:
    devolve {"chapas": {id: chapa (dict)}, "recusadas": {id: motivo}}."""
    from nucleo3d.modelo import Solido
    from nucleo2d.detalhe.celulas import converter_chapas
    fora, recusadas = {}, {}
    for i in ids:
        e = doc.entidades.get(i)
        if not isinstance(e, Solido) or len(e.vertices or []) < 4:
            recusadas[i] = "não é sólido com volume"
            continue
        a_orig = dict(e.atributos or {})
        temp = dataclasses.replace(e, atributos=dict(a_orig, tipo_ifc="IfcPlate",
                                                     marcas=dict(a_orig.get("marcas") or {}, posicao="#" + e.id)))
        doc.entidades[e.id] = temp
        try:
            n = converter_chapas(doc, "#" + e.id, referencia=e.id)
            nova = doc.entidades.get(e.id)
        except Exception as exc:                          # noqa: BLE001
            n, nova = 0, None
            recusadas[i] = "a malha não se mede como chapa (%s)" % exc
        finally:
            doc.entidades[e.id] = e
        if not n or nova is None or nova.tipo != "chapa":
            recusadas.setdefault(i, "não é uma chapa plana de espessura constante")
            continue
        d = nova.dict()
        a = dict(a_orig)
        a["tipo_ifc"] = "IfcPlate"
        for k in ("eixos_conferidos", "espelhada"):
            if k in (nova.atributos or {}):
                a[k] = nova.atributos[k]
        if (a.get("marcas") or {}).get("posicao", "").startswith("#"):
            a["marcas"].pop("posicao", None)
        d["atributos"] = a
        fora[i] = d
    return {"chapas": fora, "recusadas": recusadas}
