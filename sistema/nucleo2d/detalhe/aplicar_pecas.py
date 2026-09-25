# -*- coding: utf-8 -*-
"""O que se corrige à mão na elevação de um conjunto volta para o modelo 3D.

O detalhamento projeta a tesoura numa vista (`desenho.vistas`: origem, normal, eixos, as
peças e o canto da célula). Quem corrige a diagonal da ponta no CAD — move, espelha,
copia, apaga — muda o desenho, e o próximo Detalhar refaz a elevação do 3D e desfaz a
correção. Aqui a correção sobe.

Cada linha de peça do desenho leva a `origem` (id da peça no 3D). O desenho do usuário é
comparado com um **gerado agora** pelo mesmo código (as duas elevações têm os mesmos
artifícios — chanfro do canto, banzo prolongado até o nó —, então só a mudança feita à
mão sobra), peça a peça, pelo segmento do eixo de cada uma:

* peça cujas linhas **saíram** → apagada no 3D;
* peça cujo segmento **andou ou virou** → a malha 3D recebe a mesma rotação e translação
  no plano da vista (a profundidade fica; o espelho no plano é uma rotação);
* linhas com `grupo_copia` (Copiar/Espelhar) → **peça nova**: cópia da original levada
  para onde a cópia está, na célula em que ela caiu (pode ser outra tesoura).

A mesma mudança vale para todas as instâncias do mesmo tipo de conjunto (a tesoura T1
repetida 8 vezes): cada instância é deslocada da referência, e a transformação é
aplicada no sistema dela.
"""
import collections
import copy as _copy
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Barra, Chapa, novo_id
from nucleo3d import geometria as _geo
from nucleo2d.desenho import Desenho, Linha, Polilinha
from nucleo2d.vistas import Vista

Ponto = Tuple[float, float, float]
Ponto2 = Tuple[float, float]

#: Segmento do eixo que difere menos que isto (mm) do gerado não mudou; giro menor que
#: ANGULO_MINIMO (graus) com o centro parado também não (ruído de geração).
TOLERANCIA = 5.0
ANGULO_MINIMO = 1.0


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vertices(ent) -> List[Ponto]:
    """Vértices da malha de qualquer peça (barra e chapa paramétricas, sólido)."""
    try:
        return list(_geo.malha(ent)[0])
    except Exception:                                   # noqa: BLE001 — peça sem geometria
        return []


def _proj(p: Ponto, origem: Ponto, u, v, w) -> Ponto:
    d = (p[0] - origem[0], p[1] - origem[1], p[2] - origem[2])
    return (_dot(d, u), _dot(d, v), _dot(d, w))


# ------------------------------------------------------------------ segmentos 2D
def _segmento(pontos: Sequence[Ponto2]) -> Optional[Tuple[Ponto2, Ponto2]]:
    """O eixo (ponta a ponta) da nuvem de pontos 2D de uma barra, como segmento."""
    if len(pontos) < 2:
        return None
    n = float(len(pontos))
    cx = sum(p[0] for p in pontos) / n
    cy = sum(p[1] for p in pontos) / n
    sxx = sum((p[0] - cx) ** 2 for p in pontos)
    syy = sum((p[1] - cy) ** 2 for p in pontos)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pontos)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    d = (math.cos(ang), math.sin(ang))
    ts = [(p[0] - cx) * d[0] + (p[1] - cy) * d[1] for p in pontos]
    t0, t1 = min(ts), max(ts)
    return (cx + d[0] * t0, cy + d[1] * t0), (cx + d[0] * t1, cy + d[1] * t1)


def _pontos_das_linhas(ents) -> List[Ponto2]:
    pts: List[Ponto2] = []
    for e in ents:
        if isinstance(e, Linha):
            pts += [tuple(e.a), tuple(e.b)]
        elif isinstance(e, Polilinha):
            pts += [tuple(p) for p in e.vertices]
    return pts


def _d2(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _mesmo_segmento(s1, s2, tol: float) -> bool:
    (a1, b1), (a2, b2) = s1, s2
    return (_d2(a1, a2) <= tol and _d2(b1, b2) <= tol) or (_d2(a1, b2) <= tol and _d2(b1, a2) <= tol)


def _transformacao_2d(de, para):
    """(ângulo, centro_de, centro_para): rotação no plano + translação que leva o
    segmento `de` ao `para`. Segmento não tem sentido: a rotação é a menor (±90°)."""
    (a, b), (c, d) = de, para
    ang = math.atan2(d[1] - c[1], d[0] - c[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
    while ang > math.pi / 2:
        ang -= math.pi
    while ang < -math.pi / 2:
        ang += math.pi
    return ang, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)


def _esticamento(s3, s2, tol: float):
    """Segmento que ficou na mesma reta com uma ponta parada e a outra andando ao longo
    do eixo (o Esticar do CAD): (ponta_fixa, ponta_de, ponta_para) em 2D, ou None."""
    (a, b) = s3
    L = _d2(a, b)
    if L < 1e-6:
        return None
    d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    for fixa, movel in ((a, b), (b, a)):
        # qual ponta do desenho está parada
        outra = [q for q in s2 if _d2(q, fixa) <= tol]
        if not outra:
            continue
        nova = [q for q in s2 if _d2(q, fixa) > tol]
        if not nova:
            return None
        q = nova[0]
        # a ponta nova na reta do eixo
        t = (q[0] - fixa[0]) * d[0] + (q[1] - fixa[1]) * d[1]
        pe = (fixa[0] + d[0] * t, fixa[1] + d[1] * t)
        if _d2(pe, q) > tol:
            return None
        return fixa, movel, q
    return None


# ------------------------------------------------------------------ células e vistas
def _conjunto_da_vista(vd: dict) -> str:
    nome = str(vd.get("nome") or "")
    return nome[len("Conjunto "):] if nome.startswith("Conjunto ") else ""


def _celulas(desenho: Desenho) -> List[dict]:
    return [v for v in (desenho.vistas or []) if v.get("tipo") == "conjunto" and _conjunto_da_vista(v)]


def _celula_de(p: Ponto2, celulas: Sequence[dict], folga: float = 300.0) -> Optional[dict]:
    """A célula cuja caixa (canto + largura × altura) contém o ponto; a mais próxima
    se nenhuma contém dentro da folga."""
    melhor, dm = None, float("inf")
    for vd in celulas:
        x0, y0 = vd.get("canto") or (0.0, 0.0)
        x1, y1 = x0 + float(vd.get("largura") or 0.0), y0 + float(vd.get("altura") or 0.0)
        dx = max(x0 - p[0], 0.0, p[0] - x1)
        dy = max(y0 - p[1], 0.0, p[1] - y1)
        d = math.hypot(dx, dy)
        if d < dm:
            dm, melhor = d, vd
    return melhor if dm <= folga else None


class _Quadro:
    """A vista de uma célula com o que é preciso para ir do desenho ao 3D e voltar."""

    def __init__(self, doc: Documento, vd: dict):
        self.conjunto = _conjunto_da_vista(vd)
        self.vista = Vista.de_dict(vd)
        self.u, self.v, self.w = self.vista.eixos()
        self.origem = tuple(float(x) for x in self.vista.origem)
        self.canto = tuple(float(x) for x in (vd.get("canto") or (0.0, 0.0)))
        self.ids = [i for i in (vd.get("entidades") or []) if i in doc.entidades]
        xs, ys, ws = [], [], []
        for pid in self.ids:
            for p in _vertices(doc.entidades[pid]):
                q = _proj(p, self.origem, self.u, self.v, self.w)
                xs.append(q[0])
                ys.append(q[1])
                ws.append(q[2])
        if not xs:
            raise ErroDeDados("nenhuma peça da vista de %s está no modelo." % self.conjunto)
        # a projeção do 3D como o desenho a recebeu: o canto é o mínimo do que foi projetado
        self.dxy = (self.canto[0] - min(xs), self.canto[1] - min(ys))
        self.w_medio = sum(ws) / len(ws)

    def para_2d(self, p: Ponto) -> Ponto2:
        q = _proj(p, self.origem, self.u, self.v, self.w)
        return (q[0] + self.dxy[0], q[1] + self.dxy[1])

    def segmento_3d(self, ent) -> Optional[Tuple[Ponto2, Ponto2]]:
        return _segmento([self.para_2d(p) for p in _vertices(ent)])


# ------------------------------------------------------------------ comparação
def _segmentos_das_linhas(desenho: Desenho):
    """{conjunto: {origem: segmento}} das linhas de peça (sem as cópias) e as cópias
    [(origem, grupo, segmento, centro)]."""
    por: Dict[str, Dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
    copias: Dict[Tuple[str, str], list] = collections.defaultdict(list)
    for e in desenho.entidades.values():
        if not isinstance(e, (Linha, Polilinha)):
            continue
        a = e.atributos or {}
        if not a.get("origem") or not a.get("conjunto"):
            continue
        if a.get("grupo_copia"):
            copias[(str(a["origem"]), str(a["grupo_copia"]))].append(e)
        else:
            por[str(a["conjunto"])][str(a["origem"])].append(e)
    segs = {c: {o: _segmento(_pontos_das_linhas(ents)) for o, ents in d.items()} for c, d in por.items()}
    lista = []
    for (origem, grupo), ents in copias.items():
        s = _segmento(_pontos_das_linhas(ents))
        if s:
            lista.append((origem, grupo, s, ((s[0][0] + s[1][0]) / 2, (s[0][1] + s[1][1]) / 2)))
    return segs, lista


def mudancas_do_desenho(doc: Documento, desenho: Desenho, gerado: Sequence[Desenho], tol: float = TOLERANCIA) -> dict:
    """Compara o desenho do usuário com os desenhos `gerado` (do mesmo modelo, agora):
    {"celulas": {conjunto: {"apagadas": [ids], "movidas": {id: (ang, c_de, c_para)},
     "copias": [(id_original, ang, c_de, c_para, dw)], "quadro": _Quadro}}, "avisos": [...]}."""
    celulas = _celulas(desenho)
    if not celulas:
        raise ErroDeDados("o desenho não tem elevações de conjunto (vistas): gere o detalhamento de novo.")
    vistas_geradas = {}
    for g in gerado:
        for vd in _celulas(g):
            vistas_geradas.setdefault(_conjunto_da_vista(vd), (g, vd))
    segs_u, copias = _segmentos_das_linhas(desenho)
    saida: Dict[str, dict] = {}
    avisos: List[str] = []
    for vd in celulas:
        conj = _conjunto_da_vista(vd)
        if conj not in vistas_geradas:
            avisos.append("%s: a elevação não existe mais no detalhamento atual" % conj)
            continue
        g, vg = vistas_geradas[conj]
        try:
            quadro = _Quadro(doc, vd)
        except ErroDeDados as exc:
            avisos.append(str(exc))
            continue
        segs_g, _ = _segmentos_das_linhas(g)
        cg = vg.get("canto") or (0.0, 0.0)
        desl = (quadro.canto[0] - float(cg[0]), quadro.canto[1] - float(cg[1]))
        gerados = {}
        for o, s in (segs_g.get(conj) or {}).items():
            if s:
                gerados[o] = ((s[0][0] + desl[0], s[0][1] + desl[1]), (s[1][0] + desl[0], s[1][1] + desl[1]))
        usuario = segs_u.get(conj) or {}
        apagadas, movidas, esticadas = [], {}, {}
        for o, s3 in gerados.items():
            s2 = usuario.get(o)
            if s2 is None:
                apagadas.append(o)
                continue
            if _mesmo_segmento(s2, s3, tol):
                continue
            ang, c_de, c_para = _transformacao_2d(s3, s2)
            if abs(math.degrees(ang)) < ANGULO_MINIMO and _d2(c_de, c_para) <= tol:
                continue
            est = _esticamento(s3, s2, tol)
            if est is not None:
                esticadas[o] = est                     # a ponta andou ao longo do eixo (Esticar)
                continue
            movidas[o] = (ang, c_de, c_para)
        saida[conj] = {"apagadas": apagadas, "movidas": movidas, "esticadas": esticadas, "copias": [],
                       "quadro": quadro, "gerados": gerados}
    # cópias: na célula em que caíram (pode ser outra tesoura)
    for origem, grupo, s2, centro in copias:
        vd = _celula_de(centro, celulas)
        if vd is None or _conjunto_da_vista(vd) not in saida:
            avisos.append("cópia de %s fora de qualquer elevação: ignorada" % origem)
            continue
        reg = saida[_conjunto_da_vista(vd)]
        ent = doc.entidades.get(origem)
        if ent is None:
            continue
        q: _Quadro = reg["quadro"]
        s3 = reg["gerados"].get(origem) or q.segmento_3d(ent)
        if s3 is None:
            continue
        ang, c_de, c_para = _transformacao_2d(s3, s2)
        # profundidade: a da instância desta célula (a original pode ser de outra)
        vs = _vertices(ent)
        w_orig = sum(_proj(p, q.origem, q.u, q.v, q.w)[2] for p in vs) / max(1, len(vs))
        dw = q.w_medio - w_orig if origem not in q.ids else 0.0
        reg["copias"].append((origem, ang, c_de, c_para, dw))
    return {"celulas": saida, "avisos": avisos}


# ------------------------------------------------------------------ aplicar no 3D
def _girar_no_plano(p: Ponto, centro3: Ponto, u, v, w, ang: float, desloc2: Ponto2, dw: float = 0.0) -> Ponto:
    d = (p[0] - centro3[0], p[1] - centro3[1], p[2] - centro3[2])
    x, y, z = _dot(d, u), _dot(d, v), _dot(d, w)
    c, s = math.cos(ang), math.sin(ang)
    x2, y2, z2 = x * c - y * s + desloc2[0], x * s + y * c + desloc2[1], z + dw
    return tuple(centro3[i] + x2 * u[i] + y2 * v[i] + z2 * w[i] for i in range(3))


def _mover_peca(ent, quadro: _Quadro, ang, c_de, c_para, dw: float = 0.0, origem3: Optional[Ponto] = None) -> None:
    """Rotação `ang` em torno de `c_de` e translação até `c_para`, no plano da vista do
    `quadro` (com `origem3` no lugar da origem do quadro, para outra instância)."""
    vs = _vertices(ent)
    if not vs:
        return
    o = origem3 if origem3 is not None else quadro.origem
    u, v, w = quadro.u, quadro.v, quadro.w
    wm = sum(_proj(p, o, u, v, w)[2] for p in vs) / float(len(vs))
    cx, cy = c_de[0] - quadro.dxy[0], c_de[1] - quadro.dxy[1]
    centro3 = tuple(o[i] + cx * u[i] + cy * v[i] + wm * w[i] for i in range(3))
    desloc = (c_para[0] - c_de[0], c_para[1] - c_de[1])
    mover = lambda p: _girar_no_plano(p, centro3, u, v, w, ang, desloc, dw)                    # noqa: E731
    girar = lambda d: _girar_no_plano(d, (0.0, 0.0, 0.0), u, v, w, ang, (0.0, 0.0), 0.0)     # noqa: E731
    if isinstance(ent, Barra):
        ent.inicio = mover(tuple(ent.inicio))
        ent.fim = mover(tuple(ent.fim))
    elif isinstance(ent, Chapa):
        ent.origem = mover(tuple(ent.origem))
        ent.eixo_x = girar(tuple(ent.eixo_x))
        ent.eixo_y = girar(tuple(ent.eixo_y))
    else:
        ent.vertices = [mover(p) for p in ent.vertices]


def _esticar_peca(ent, quadro: _Quadro, fixa: Ponto2, de: Ponto2, para: Ponto2, origem3: Optional[Ponto] = None) -> None:
    """A ponta `de` da peça vai para `para` (as duas na reta do eixo, `fixa` parada): na
    barra paramétrica anda a ponta; no sólido andam os vértices da metade daquela ponta."""
    o = origem3 if origem3 is not None else quadro.origem
    u, v, w = quadro.u, quadro.v, quadro.w
    delta2 = (para[0] - de[0], para[1] - de[1])
    delta3 = tuple(delta2[0] * u[i] + delta2[1] * v[i] for i in range(3))
    # eixo 2D da peça e a coordenada axial que separa a metade que anda
    L = _d2(fixa, de)
    if L < 1e-6:
        return
    d = ((de[0] - fixa[0]) / L, (de[1] - fixa[1]) / L)
    meio = L / 2.0

    def axial(p):
        q = _proj(p, o, u, v, w)
        q2 = (q[0] + quadro.dxy[0], q[1] + quadro.dxy[1])
        return (q2[0] - fixa[0]) * d[0] + (q2[1] - fixa[1]) * d[1]
    if isinstance(ent, Barra):
        if axial(tuple(ent.fim)) > axial(tuple(ent.inicio)):
            ent.fim = tuple(ent.fim[i] + delta3[i] for i in range(3))
        else:
            ent.inicio = tuple(ent.inicio[i] + delta3[i] for i in range(3))
    elif isinstance(ent, Chapa):
        return
    else:
        ent.vertices = [tuple(p[i] + delta3[i] for i in range(3)) if axial(p) > meio else tuple(p) for p in ent.vertices]


def _transladar(ent, desl: Ponto) -> None:
    if isinstance(ent, Barra):
        ent.inicio = tuple(ent.inicio[i] + desl[i] for i in range(3))
        ent.fim = tuple(ent.fim[i] + desl[i] for i in range(3))
    elif isinstance(ent, Chapa):
        ent.origem = tuple(ent.origem[i] + desl[i] for i in range(3))
    elif getattr(ent, "vertices", None):
        ent.vertices = [tuple(p[i] + desl[i] for i in range(3)) for p in ent.vertices]


def _centro(doc: Documento, ids: Sequence[str]) -> Ponto:
    pts = [p for i in ids if i in doc.entidades for p in _vertices(doc.entidades[i])]
    n = float(len(pts)) or 1.0
    return tuple(sum(p[i] for p in pts) / n for i in range(3))


def _instancias_iguais(doc: Documento, conjunto: str, ids_ref: Sequence[str]) -> List[Dict[str, str]]:
    """As outras instâncias do mesmo tipo de conjunto, cada uma como {id da peça na
    referência: id da peça correspondente} (mesma posição e mesmo lugar relativo)."""
    from nucleo2d.detalhe.base import _marcas, _pecas
    from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto
    marcas_conj = set()
    for r in conjunto.split("+"):
        marcas_conj.update(m.strip() for m in r.split("/"))
    pecas, _ = _pecas(doc)
    lista = [e for e in pecas if str(_marcas(e).get("conjunto") or "") in marcas_conj]
    ref = [doc.entidades[i] for i in ids_ref if i in doc.entidades]
    unidade = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in ref)
    if not unidade:
        return []
    inst = _instancias_do_conjunto(lista, unidade)
    ref_ids = set(ids_ref)
    c_ref = _centro(doc, ids_ref)
    centros = {e.id: _centro(doc, [e.id]) for e in lista}
    rel_ref = {e.id: tuple(centros[e.id][i] - c_ref[i] for i in range(3)) for e in ref if e.id in centros}
    saida = []
    for g in inst:
        gids = [e.id for e in g]
        if set(gids) & ref_ids:
            continue                                   # a própria referência
        # só a instância com a mesma composição: a tesoura M2 + M2 não é uma M2 + M7,
        # ainda que as duas tenham as peças de M2
        if collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in g) != unidade:
            continue
        cg = _centro(doc, gids)
        por_pos = collections.defaultdict(list)
        for e in g:
            por_pos[str(_marcas(e).get("posicao") or e.nome)].append(e.id)
        mapa = {}
        for e in ref:
            cands = por_pos.get(str(_marcas(e).get("posicao") or e.nome)) or []
            r = rel_ref.get(e.id)
            if not cands or r is None:
                continue
            mapa[e.id] = min(cands, key=lambda x: sum((centros[x][i] - cg[i] - r[i]) ** 2 for i in range(3)))
        if mapa:
            saida.append(mapa)
    return saida


def aplicar_desenho_ao_modelo(doc: Documento, desenho: Desenho, gerado: Sequence[Desenho],
                              todas_instancias: bool = True) -> dict:
    """Leva as mudanças de todas as elevações do desenho para o 3D. Devolve
    {"celulas": {conjunto: {"apagadas", "movidas", "copiadas", "instancias"}}, "avisos", "total"}."""
    m = mudancas_do_desenho(doc, desenho, gerado)
    saida = {"celulas": {}, "avisos": list(m["avisos"]), "total": {"apagadas": 0, "movidas": 0, "copiadas": 0, "esticadas": 0}}
    for conj, reg in m["celulas"].items():
        if not (reg["apagadas"] or reg["movidas"] or reg["copias"] or reg["esticadas"]):
            continue
        quadro: _Quadro = reg["quadro"]
        instancias = [{i: i for i in quadro.ids}]
        if todas_instancias:
            instancias += _instancias_iguais(doc, conj, quadro.ids)
        c0 = _centro(doc, quadro.ids)
        # cópias: a original vem de onde estiver, antes de qualquer mudança
        fontes = {o: _copy.deepcopy(doc.entidades[o]) for o, *_ in reg["copias"] if o in doc.entidades}
        n_ap = n_mov = n_cop = n_est = 0
        for k, mapa in enumerate(instancias):
            if k == 0:
                origem_k, desl = quadro.origem, (0.0, 0.0, 0.0)
            else:
                c1 = _centro(doc, list(mapa.values()))
                desl = tuple(c1[i] - c0[i] for i in range(3))
                origem_k = tuple(quadro.origem[i] + desl[i] for i in range(3))
            for o in reg["apagadas"]:
                alvo = mapa.get(o)
                if alvo and alvo in doc.entidades:
                    doc.remover(alvo)
                    n_ap += 1
            for o, (ang, c_de, c_para) in reg["movidas"].items():
                alvo = mapa.get(o)
                ent = doc.entidades.get(alvo) if alvo else None
                if ent is not None:
                    _mover_peca(ent, quadro, ang, c_de, c_para, 0.0, origem_k)
                    n_mov += 1
            for o, (fixa, de, para) in reg["esticadas"].items():
                alvo = mapa.get(o)
                ent = doc.entidades.get(alvo) if alvo else None
                if ent is not None:
                    _esticar_peca(ent, quadro, fixa, de, para, origem_k)
                    n_est += 1
            for o, ang, c_de, c_para, dw in reg["copias"]:
                fonte = fontes.get(o)
                if fonte is None:
                    continue
                nova = _copy.deepcopy(fonte)
                nova.id = novo_id()
                if hasattr(nova, "origem_ifc"):
                    nova.origem_ifc = ""
                nova.atributos = dict(nova.atributos or {}, copiada_de=o)
                if k > 0:
                    _transladar(nova, desl)             # a original está na referência
                _mover_peca(nova, quadro, ang, c_de, c_para, dw, origem_k)
                doc.add(nova)
                n_cop += 1
        saida["celulas"][conj] = {"apagadas": n_ap, "movidas": n_mov, "copiadas": n_cop, "esticadas": n_est,
                                  "instancias": len(instancias)}
        for chave in ("apagadas", "movidas", "copiadas", "esticadas"):
            saida["total"][chave] += saida["celulas"][conj][chave]
    return saida
