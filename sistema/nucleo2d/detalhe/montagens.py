# -*- coding: utf-8 -*-
"""Peças montadas: o que a fábrica solda ou a obra junta antes de pôr no lugar, desenhado
junto — a vista de frente, a lateral e uma isométrica, para ficar claro como fica.

Dois tipos, achados pela geometria do modelo:

* **chapas soldadas**: chapas pequenas do mesmo conjunto que se encostam (o suporte de
  terça é a chapa furada mais a nervura triangular soldada nela);
* **chumbamento**: a chapa de base com os chumbadores (barra redonda) que passam nos furos
  dela, e as porcas. No TecnoMETAL o chumbador vem como conjunto próprio (M1), então ele
  não aparecia junto da chapa.

Cada combinação diferente de peças vira uma célula, com a quantidade de vezes que ela
aparece no modelo. As peças continuam detalhadas uma a uma nas células delas; aqui é só a
montagem.
"""
import collections
import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido
from nucleo2d import vistas as _vistas
from nucleo2d.desenho import Desenho
from saida.detalhamento import _autovetores, _ordem_natural
from nucleo2d.detalhe.base import (_marcas, _dot, _sub, _norm, _cruz, _caixa, _eh_redonda_perfil, _Papel,
                                   _registrar_camadas_de_pecas)

#: Chapa maior que isto (mm) não entra em montagem soldada: é chapa de nó, não peça miúda.
MAIOR_CHAPA_MONTAGEM = 600.0
#: Folga (mm) para duas peças "se encostarem" (caixas que se tocam).
FOLGA_CONTATO = 1.0
#: Mais peças que isto num grupo: não é peça miúda, é um pedaço do conjunto.
MAIS_PECAS = 8


def _perfil(e) -> str:
    return str(_marcas(e).get("perfil") or e.nome or "")


def _eh_chapa(e) -> bool:
    return getattr(e, "parametrica", None) is not None or "PLATE" in _perfil(e).upper() \
        or str((e.atributos or {}).get("tipo_ifc") or "") == "IfcPlate"


def _extensao(e) -> float:
    cx = _caixa(e)
    return max(cx[i][1] - cx[i][0] for i in range(3))


def _tocam(a, b, folga: float) -> bool:
    return all(a[i][0] - folga <= b[i][1] and b[i][0] - folga <= a[i][1] for i in range(3))


def grupos_montados(pecas: Sequence[Solido], fixadores: Sequence[Solido], nome_de: Callable[[str], str]) -> List[dict]:
    """[{"tipo": "soldadas"|"chumbamento", "chave": (nomes...), "composicao": {nome: n},
    "instancias": n, "exemplo": [ids], "pecas": [ids da 1ª instância sem fixadores]}]."""
    chapas = [e for e in pecas if _eh_chapa(e) and len(e.vertices or []) >= 4]
    barras = [e for e in pecas if not _eh_chapa(e) and _eh_redonda_perfil(_perfil(e)) and len(e.vertices or []) >= 4]
    cx = {e.id: _caixa(e) for e in chapas + barras}
    pai: Dict[str, str] = {e.id: e.id for e in chapas + barras}

    def raiz(i):
        while pai.get(i, i) != i:
            pai[i] = pai.get(pai[i], pai[i])
            i = pai[i]
        return i

    def unir(a, b):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[ra] = rb
    # chapas miúdas do mesmo conjunto que se encostam: soldadas
    miudas = [e for e in chapas if _extensao(e) <= MAIOR_CHAPA_MONTAGEM]
    por_conj: Dict[str, list] = collections.defaultdict(list)
    for e in miudas:
        por_conj[str(_marcas(e).get("conjunto") or "")].append(e)
    for conj, lista in por_conj.items():
        if not conj:
            continue
        lista.sort(key=lambda e: cx[e.id][0][0])
        for i, a in enumerate(lista):
            for b in lista[i + 1:]:
                if cx[b.id][0][0] > cx[a.id][0][1] + FOLGA_CONTATO:
                    break                             # varredura em x
                if _tocam(cx[a.id], cx[b.id], FOLGA_CONTATO):
                    unir(a.id, b.id)
    # chumbador: barra redonda em pé que atravessa a chapa deitada (de base) — as caixas se
    # cruzam de verdade (2 mm), não só encostam; tirante inclinado passando numa castanha não conta
    def eixo_principal(e):
        return _norm(tuple(_autovetores(e.vertices)[1][0]))
    base = [e for e in chapas if _extensao(e) <= 2 * MAIOR_CHAPA_MONTAGEM
            and abs(_norm(tuple(_autovetores(e.vertices)[1][2]))[2]) > 0.8]
    for b in barras:
        if abs(eixo_principal(b)[2]) < 0.8:
            continue
        for c in base:
            if _tocam(cx[b.id], cx[c.id], -2.0):
                unir(b.id, c.id)
    comps: Dict[str, list] = collections.defaultdict(list)
    por_id = {e.id: e for e in chapas + barras}
    for i in por_id:
        comps[raiz(i)].append(por_id[i])
    grupos: Dict[tuple, dict] = {}
    for membros in comps.values():
        if len(membros) < 2 or len(membros) > MAIS_PECAS:
            continue
        tem_barra = any(not _eh_chapa(e) for e in membros)
        if tem_barra and not any(_eh_chapa(e) for e in membros):
            continue
        if len({str(_marcas(e).get("posicao") or e.nome) for e in membros}) < 2:
            continue                                  # duas chapas iguais encostadas: não é peça montada
        nomes = [nome_de(str(_marcas(e).get("posicao") or e.nome or e.id)) for e in membros]
        chave = tuple(sorted(nomes, key=_ordem_natural))
        g = grupos.get(chave)
        if g is None:
            ids = [e.id for e in membros]
            if tem_barra:
                # as porcas e arruelas dos chumbadores entram no desenho
                cx_g = [cx[e.id] for e in membros]
                caixa = tuple((min(c[i][0] for c in cx_g) - 30.0, max(c[i][1] for c in cx_g) + 30.0) for i in range(3))
                for f in fixadores:
                    if _tocam(_caixa(f), caixa, 0.0):
                        ids.append(f.id)
            g = grupos[chave] = {"tipo": "chumbamento" if tem_barra else "soldadas", "chave": chave,
                                 "composicao": dict(collections.Counter(nomes)), "instancias": 0,
                                 "exemplo": ids, "pecas": [e.id for e in membros],
                                 "marcas": sorted({str(_marcas(e).get("posicao") or e.nome) for e in membros}),
                                 "_nomes": {e.id: n for e, n in zip(membros, nomes)}}
        g["instancias"] += 1
    return sorted(grupos.values(), key=lambda g: (g["tipo"] != "soldadas", [_ordem_natural(n) for n in g["chave"]]))


def _eixos_da_chapa(e):
    c, pca = _autovetores(e.vertices)
    return c, [_norm(tuple(a)) for a in pca]


def desenho_de_montagem(doc: Documento, grupo: dict, desenho: Desenho, dx: float, dy: float,
                        titulo: str = "", pecas_por_id: Optional[dict] = None) -> Tuple[float, float, float, float]:
    """Célula da peça montada: vista de frente e lateral com as cotas gerais e o nome de
    cada peça, e a isométrica ao lado."""
    ids = [i for i in grupo["exemplo"] if i in doc.entidades]
    pecas_por_id = pecas_por_id or {}
    ents = [pecas_por_id.get(i) or doc.entidades[i] for i in ids]
    solidos = [e for e in ents if getattr(e, "vertices", None)]
    chapas = [e for e in solidos if e.id in grupo["pecas"] and _eh_chapa(e)]
    ref = max(chapas, key=lambda e: sorted((c[1] - c[0] for c in _caixa(e)))[-1] * sorted((c[1] - c[0] for c in _caixa(e)))[-2])
    c_ref, (e1, e2, n) = _eixos_da_chapa(ref)
    z = (0.0, 0.0, 1.0)
    if abs(_dot(n, z)) < 0.7:
        # chapa em pé (suporte): de frente para a chapa e de lado
        w1 = n
        w2 = _norm(_cruz(z, n))
    else:
        # chapa deitada (base): de frente e de lado, olhando na horizontal — os chumbadores em pé
        h1 = _norm(_sub(e2, tuple(z[i] * _dot(e2, z) for i in range(3))))
        w1 = h1
        w2 = _norm(_cruz(z, h1))
    # isométrica: de cima, pela diagonal das duas vistas (o observador fica em −w)
    w3 = _norm(tuple(w1[i] + w2[i] - z[i] * 1.2 for i in range(3)))
    esc = desenho.escala
    _registrar_camadas_de_pecas(desenho)
    atr = {"detalhe": "montagem", "montagem": " + ".join(grupo["chave"])}
    camada_de = {}
    for e in solidos:
        if e.id in grupo["pecas"]:
            camada_de[e.id] = "CHAPAS" if _eh_chapa(e) else "TIRANTES"
    nome_peca = {}
    for e in solidos:
        if e.id in grupo["pecas"]:
            nome_peca[e.id] = e
    x = dx
    caixas = []
    p_txt = _Papel(desenho, atr, 0.0, 0.0)
    for k, (w, rot) in enumerate(((w1, "FRENTE"), (w2, "LATERAL"), (w3, "ISOMÉTRICA"))):
        pts = [q for e in solidos for q in e.vertices]
        ws = [_dot(q, w) for q in pts]
        origem = tuple(c_ref[i] + w[i] * (min(ws) - _dot(c_ref, w) - 10.0) for i in range(3))
        vista = _vistas.Vista(origem=origem, normal=w, acima=z, profundidade=None, cortar=False,
                              entidades=ids, rotular=False, nome="Montagem %s – %s" % (atr["montagem"], rot.lower()),
                              tipo="montagem")
        u, v, _ = vista.eixos()
        antes = set(desenho.entidades)
        _vistas.gerar(doc, vista, desenho, (x, dy))
        info = desenho.vistas[-1]
        larg, alt = info["largura"], info["altura"]
        for ent in (desenho.entidades[i] for i in desenho.entidades if i not in antes):
            ent.atributos.update(atr)
            if getattr(ent, "camada", "") in ("VISTA", "CORTE") and ent.atributos.get("origem") in camada_de:
                ent.camada = camada_de[ent.atributos["origem"]]
        us = [_dot(_sub(q, origem), u) for q in pts]
        vs = [_dot(_sub(q, origem), v) for q in pts]
        u0, v0 = min(us), min(vs)
        p = _Papel(desenho, atr, x, dy)
        if k < 2:
            p.cota_h(0, larg, 0, -8.0)
            p.cota_v(0, alt, larg, 8.0)
            if k == 0:
                # o nome de cada peça numa coluna à esquerda, com a chamada até o centro dela
                # (no centro, as peças encostadas empilhavam os nomes)
                h = 1.8 * esc
                alvos, vistos = [], set()
                for i, e in nome_peca.items():
                    nome = grupo["_nomes"].get(i, "")
                    if not nome or nome in vistos:
                        continue
                    vistos.add(nome)
                    cc = tuple(sum(q[j] for q in e.vertices) / len(e.vertices) for j in range(3))
                    alvos.append((nome, _dot(_sub(cc, origem), u) - u0, _dot(_sub(cc, origem), v) - v0))
                alvos.sort(key=lambda a: -a[2])
                y_ant = None
                for nome, ax, ay in alvos:
                    y_t = ay if y_ant is None else min(ay, y_ant - 2.2 * h)
                    y_ant = y_t
                    x_t = -6.0 * esc
                    p.texto(x_t, y_t - h / 2, nome, h, "TEXTO", alinhamento="direita")
                    p.linha(x_t + 1.0 * esc, y_t, ax, ay, "COTA")
        p.texto(larg / 2, -(16.0 if k < 2 else 4.0) * esc, rot, 2.2 * esc, "TEXTO", alinhamento="centro")
        caixas.append(p.extremos)
        caixas.append((x, dy, x + larg, dy + alt))
        x += larg + (22.0 if k < 2 else 10.0) * esc
    topo = max(c[3] for c in caixas)
    tit = titulo or ("CHAPA DE BASE COM CHUMBADORES" if grupo["tipo"] == "chumbamento" else "PEÇAS SOLDADAS")
    comp = ", ".join("%s x%d" % (k, q) for k, q in sorted(grupo["composicao"].items(), key=lambda kv: _ordem_natural(kv[0])))
    linhas = [tit + " – MONTADO", "%s – %02dx" % (" + ".join(dict.fromkeys(grupo["chave"])), grupo["instancias"]),
              "por unidade: " + comp,
              "vistas de frente e lateral na escala do desenho; isométrica só para visualizar"]
    if grupo["tipo"] == "chumbamento":
        linhas.insert(3, "chumbadores, porcas e arruelas como no modelo; o comprimento de corte do chumbador está no detalhe dele")
    y = topo + 4.0 * esc
    for i, txt in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.2
        p_txt.texto(dx, y, txt, alt_t * esc, "TEXTO")
        y += (alt_t + 1.2) * esc
    caixas.append(p_txt.extremos)
    return (min(c[0] for c in caixas), min(c[1] for c in caixas), max(c[2] for c in caixas), max(c[3] for c in caixas))
