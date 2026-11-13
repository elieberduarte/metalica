# -*- coding: utf-8 -*-
"""As unidades de cada conjunto e o número delas pela ordem dos eixos da obra.

Pedido do usuário (Posto, 12/11/2026), aprovado: "o número da unidade segue a ordem dos eixos — TESOURA 1-1 é a do
primeiro eixo, a 1-2 a do seguinte". Até aqui o número era só uma contagem pela ordem das marcas (M25 → 1, M27 → 2,
M103 → 3 e 4…): nenhuma unidade era uma peça num lugar, e o Controle de produção com o 3D ao lado acendia as 7
TESOURA 1 juntas. Agora:

* **as unidades de uma marca** se separam pelo que o modelo diz — `marcas.instancia` (o conjunto do IFC, o do editor), a
  cópia da elevação de onde as barras vieram (`origem.peca`, "PAINEL 3#173", gravada pela montagem pela planta) — e, sem
  isso, pelas peças que se tocam (como o Detalhar acha as instâncias). A peça sem chave (a chapa soldada) vai para a
  unidade em que encosta. Por último, como o Detalhar acha as instâncias: pela composição da unidade (a T1 do Posto,
  duas meias-tesouras em L que não se tocam). Só vale quando dá o número de unidades da marca; senão a marca fica sem
  lugar e o nome todo numera como antes;
* **a ordem**: pelo meio de cada unidade em planta, primeiro ao longo dos eixos de número (do eixo 1 em diante),
  depois ao longo dos de letra (do A em diante), depois a altura. Sem eixos no projeto, x, y e z;
* **o nome**: as unidades do mesmo nome (em todas as marcas) numeram juntas — "TESOURA 1-1"…; o nome com uma unidade só
  fica sem número (a mesma regra de `nomes.numerar_unidades`).

`numerar` devolve os nomes por marca (o que os títulos das pranchas usam) e as peças de cada unidade (os ids das peças
no modelo 3D: o Controle de produção acende e pinta a unidade certa).
"""
import collections
import math
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

#: duas unidades com o meio a menos disto (mm) na mesma direção estão "no mesmo eixo": decide a direção seguinte
MESMO_EIXO = 300.0
#: a peça sem chave encosta na unidade a até isto (mm), em cadeia (a chapa soldada na chapa soldada no banzo)
ENCOSTA = 8.0
#: unidades iguais têm quase o mesmo número de peças: a separação com uma unidade fora disto (da média) não vale —
#: no Posto, as 6 T1 (16 peças) pela origem das barras davam 4 de 8 e 2 de 32
DESVIO_PECAS = 0.4


def _marcas(e) -> dict:
    m = (getattr(e, "atributos", None) or {}).get("marcas")
    return m if isinstance(m, dict) else {}


def _caixa(e):
    vs = getattr(e, "vertices", None) or []
    if not vs:
        return None
    xs, ys, zs = zip(*vs)
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def _chave_da_peca(e) -> str:
    """a unidade que o modelo diz: a instância do conjunto ou a cópia da elevação"""
    m = _marcas(e)
    if m.get("instancia"):
        return "i:" + str(m["instancia"])
    o = (getattr(e, "atributos", None) or {}).get("origem") or {}
    if isinstance(o, dict) and o.get("peca"):
        return "o:" + str(o["peca"])
    return ""


def _separacao(e, caixa) -> float:
    """a folga entre duas caixas (negativa quando se cruzam)"""
    return max(max(e[k][0] - caixa[k][1], caixa[k][0] - e[k][1]) for k in range(3))


def _pelas_chaves(pecas) -> Optional[List[list]]:
    """grupos pela chave das peças; as sem chave vão para o grupo em que encostam. None quando a maioria não tem chave
    ou sobra peça sem grupo"""
    grupos: Dict[str, list] = collections.OrderedDict()
    sem = []
    for e in pecas:
        k = _chave_da_peca(e)
        if k:
            grupos.setdefault(k, []).append(e)
        else:
            sem.append(e)
    if not grupos or 2 * sum(len(g) for g in grupos.values()) < len(pecas):
        return None
    if sem:
        caixas = {id(e): _caixa(e) for e in pecas}
        if any(c is None for c in caixas.values()):
            return None
        dono = {id(e): k for k, g in grupos.items() for e in g}
        while sem:
            resolvidas = []
            for e in sem:
                perto = [(_separacao(caixas[id(e)], caixas[i]), k) for i, k in dono.items()]
                perto = [p for p in perto if p[0] <= ENCOSTA]
                if perto:
                    resolvidas.append((e, min(perto, key=lambda p: p[0])[1]))
            if not resolvidas:
                return None
            for e, k in resolvidas:
                grupos[k].append(e)
                dono[id(e)] = k
            ids = {id(e) for e, _k in resolvidas}
            sem = [e for e in sem if id(e) not in ids]
    return list(grupos.values())


def _pelo_contato(pecas) -> Optional[List[list]]:
    if not all(getattr(e, "vertices", None) for e in pecas):
        return None
    from nucleo2d.detalhe.conjuntos import _instancias
    return _instancias(list(pecas), folga=ENCOSTA)


def _pela_composicao(pecas, n: int) -> Optional[List[list]]:
    """as unidades como o Detalhar acha as instâncias (conjuntos._instancias_do_conjunto, pela composição da unidade): a
    T1 do Posto (16 peças) é uma meia-tesoura em X (P257) e uma em Y (P259) na cabeça do pilar PM6, que não se tocam
    (95 mm) — pelo contato saíam 12 metades, pela cópia da elevação 3 pares; a lista diz 1× P257 + 1× P259 por unidade"""
    from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto, posicao_base
    if not all(getattr(e, "vertices", None) for e in pecas):
        return None
    total = collections.Counter(posicao_base(e) for e in pecas)
    if not total or any(q % n for q in total.values()):
        return None
    unidade = collections.Counter({k: q // n for k, q in total.items()})
    grupos = _instancias_do_conjunto(list(pecas), unidade)
    if len(grupos) == n and all(collections.Counter(posicao_base(e) for e in g) == unidade for g in grupos):
        return grupos
    return None


def _meio(g) -> Tuple[float, float, float]:
    pts = [v for e in g for v in (getattr(e, "vertices", None) or [])]
    if not pts:
        return (0.0, 0.0, 0.0)
    return tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))


def _juntar_pedacos(grupos: List[list], n: int) -> Optional[List[list]]:
    """mais grupos que unidades: os n maiores (parecidos entre si) ficam, os pedaços vão para o mais perto"""
    grupos = sorted(grupos, key=len, reverse=True)
    grandes = [list(g) for g in grupos[:n]]
    if len(grandes[-1]) < 0.5 * len(grandes[0]):
        return None
    meios = [_meio(g) for g in grandes]
    for g in grupos[n:]:
        c = _meio(g)
        k = min(range(n), key=lambda t: math.dist(meios[t], c))
        grandes[k].extend(g)
    return grandes


def _parecidas(grupos: List[list], total: int) -> bool:
    media = total / float(len(grupos))
    return all(abs(len(g) - media) <= DESVIO_PECAS * media for g in grupos)


def separar(pecas: Sequence, n: int) -> Optional[List[list]]:
    """as `n` unidades de uma marca (listas de peças) ou None quando o modelo não as separa em `n` unidades parecidas"""
    pecas = list(pecas)
    if n <= 1:
        return [pecas] if pecas else None
    if len(pecas) < n:
        return None
    for jeito in (_pelas_chaves, _pelo_contato, _pela_composicao):
        grupos = jeito(pecas, n) if jeito is _pela_composicao else jeito(pecas)
        if not grupos:
            continue
        if len(grupos) > n and jeito is _pelo_contato:
            grupos = _juntar_pedacos(grupos, n) or grupos
        if len(grupos) == n and _parecidas(grupos, len(pecas)):
            return grupos
    return None


# ------------------------------------------------------------------ a ordem pelos eixos

def _sentido(lista: Sequence[dict], letra: bool) -> float:
    """+1 quando o primeiro eixo (1, A) está no começo da coordenada; -1 quando está no fim (o Posto: L … A)"""
    if len(lista) < 2:
        return 1.0
    def ordem(nome):
        nome = str(nome).strip().upper()
        if letra:
            return [ord(c) for c in nome]
        m = re.match(r"^(\d+)", nome)
        return [int(m.group(1))] if m else [ord(c) for c in nome]
    primeiro = min(lista, key=lambda e: ordem(e["nome"]))
    ultimo = max(lista, key=lambda e: ordem(e["nome"]))
    return 1.0 if float(primeiro["pos"]) <= float(ultimo["pos"]) else -1.0


def chave_pelos_eixos(eixos: Optional[dict]):
    """f(meio) → (ao longo dos eixos de número, ao longo dos de letra, altura), cada um no sentido do eixo 1 / do A"""
    from nucleo3d import eixos as _eixos
    ex = _eixos.de_dict(eixos) if eixos else None
    if not ex:
        return lambda c: (c[0], c[1], c[2])
    g, p = ex["eixo_g"], ex["perp_g"]
    sg, sp = _sentido(ex["numeros"], False), _sentido(ex["letras"], True)
    return lambda c: (sg * (c[0] * g[0] + c[1] * g[1]), sp * (c[0] * p[0] + c[1] * p[1]), c[2])


def ordenar(meios: Sequence[Sequence[float]], eixos: Optional[dict] = None) -> List[int]:
    """os índices dos meios na ordem da obra: as unidades a menos de MESMO_EIXO uma da outra ao longo dos eixos de
    número estão no mesmo eixo (em cadeia, não por faixa fixa: duas tesouras a 2 mm não caem em faixas diferentes) e
    vão pela letra; depois a altura"""
    chave = chave_pelos_eixos(eixos)
    ks = [chave(m) for m in meios]
    ordem_g = sorted(range(len(ks)), key=lambda i: ks[i][0])
    faixa, f, ant = {}, 0, None
    for i in ordem_g:
        if ant is not None and ks[i][0] - ant > MESMO_EIXO:
            f += 1
        faixa[i] = f
        ant = ks[i][0]
    return sorted(range(len(ks)), key=lambda i: (faixa[i], ks[i][1], ks[i][2]))


def _ordem_natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def numerar(conjuntos: Iterable[Tuple[str, str, int]], pecas: Sequence, eixos: Optional[dict] = None):
    """`conjuntos`: (marca, nome, unidades). Devolve (nomes, detalhe):

    * nomes = {marca: [nome de cada unidade]} — como `nomes.numerar_unidades`, mas na ordem dos eixos quando todas as
      unidades do nome se separam no modelo (senão, a ordem das marcas, como sempre);
    * detalhe = {marca: [{"nome", "ids": [ids das peças], "meio": [x, y, z]}]} das marcas separadas, só para os nomes
      com mais de uma unidade (os únicos que precisam de lugar)."""
    por_marca: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        c = str(_marcas(e).get("conjunto") or "")
        if c:
            por_marca[c].append(e)
    por_nome: Dict[str, list] = collections.OrderedDict()
    for marca, nome, n in conjuntos:
        por_nome.setdefault(str(nome or marca), []).append((str(marca), max(int(n or 1), 1)))
    nomes: Dict[str, List[str]] = {}
    detalhe: Dict[str, List[dict]] = {}
    for nome, grupo in por_nome.items():
        grupo.sort(key=lambda g: _ordem_natural(g[0]))
        total = sum(n for _m, n in grupo)
        if total == 1:
            nomes.setdefault(grupo[0][0], []).append(nome)
            continue
        unidades = []                                     # (marca, peças da unidade)
        for marca, n in grupo:
            sep = separar(por_marca.get(marca) or [], n)
            if sep is None:
                unidades = None
                break
            unidades.extend((marca, g) for g in sep)
        if unidades is None:
            # alguma marca não se separa no modelo: o nome todo pela ordem das marcas (o de antes)
            i = 0
            for marca, n in grupo:
                for _ in range(n):
                    i += 1
                    nomes.setdefault(marca, []).append("%s-%d" % (nome, i))
            continue
        com_meio = [(marca, g, _meio(g)) for marca, g in unidades]
        com_meio = [com_meio[i] for i in ordenar([u[2] for u in com_meio], eixos)]
        for i, (marca, g, meio) in enumerate(com_meio, 1):
            un = "%s-%d" % (nome, i)
            nomes.setdefault(marca, []).append(un)
            detalhe.setdefault(marca, []).append({"nome": un, "ids": sorted(str(e.id) for e in g),
                                                  "meio": [round(v) for v in meio]})
    for m in nomes:
        nomes[m].sort(key=_ordem_natural)
    for m in detalhe:
        detalhe[m].sort(key=lambda u: _ordem_natural(u["nome"]))
    return nomes, detalhe
