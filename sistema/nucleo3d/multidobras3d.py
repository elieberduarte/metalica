# -*- coding: utf-8 -*-
"""Multidobra no 3D: a telha que dobra do telhado para a parede (o beiral arredondado) como a
fábrica dobra — raio interno comercial (R450 na TP40), girando no vértice das duas retas —,
reescrita no próprio modelo 3D (pedido do usuário, 13/10: "gostaria de ter no 3D a configuração
nova da telha, para conferir se não interfere com os banzos e terças").

O TecnoMETAL exporta a multidobra como uma fileira de peças: a reta da água, N facetas do arco
(R800) e a reta da parede, cada uma um prisma do perfil da onda. O detalhamento
(`nucleo2d.detalhe.telhas`) já lê essa fileira e recalcula a dobra com o raio comercial: as
pontas livres e o vértice I das duas retas ficam os do modelo, as tangências recuam para
R·tan(θ/2) do vértice. Aqui a mesma conta vai para as malhas:

* cada reta é esticada da ponta livre até a tangência nova (a ponta livre não se move);
* cada faceta vira uma corda do arco novo (centro no bissetor, a R/cos(θ/2) do vértice), com
  o perfil da onda girado junto — a malha é só transformada, as faces ficam como eram.

Os vértices de antes ficam guardados na peça (`atributos.multidobra_3d.original`) para
"Voltar ao original". As quantidades não mudam: o detalhamento parte das pontas livres e do
vértice, que são os mesmos.
"""
import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido

Ponto = Tuple[float, float, float]

#: Chave dos atributos da peça ajustada.
CHAVE = "multidobra_3d"


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _telhas(doc: Documento) -> List[Solido]:
    from nucleo2d.detalhe.base import _marcas
    from nucleo2d.detalhe.telhas import _eh_telha
    saida = []
    for e in doc.entidades.values():
        if not isinstance(e, Solido) or len(e.vertices or []) < 8:
            continue
        m = _marcas(e)
        if _eh_telha(str(m.get("perfil") or e.nome or "")):
            saida.append(e)
    return saida


def instancias(doc: Documento) -> List[dict]:
    """As multidobras do modelo, uma entrada por instância: {conjunto, pecas: [Solido na ordem da
    fileira], perfil: o dict de `_analisar_instancia`} — o mesmo reconhecimento do detalhamento,
    instância por instância (o detalhamento analisa só a primeira de cada conjunto)."""
    from nucleo2d.detalhe.base import _marcas
    from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto
    from nucleo2d.detalhe.telhas import _analisar_instancia, _posicao
    por_conj: Dict[str, list] = collections.defaultdict(list)
    for e in _telhas(doc):
        conj = str(_marcas(e).get("conjunto") or "")
        if conj:
            por_conj[conj].append(e)
    saida = []
    for conj, lista in por_conj.items():
        if len(lista) < 4:
            continue
        total = collections.Counter(_posicao(e) for e in lista)
        g = 0
        for q in total.values():
            g = math.gcd(g, q)
        unidade = collections.Counter({k: q // max(g, 1) for k, q in total.items()})
        if sum(unidade.values()) < 4:
            continue
        for inst in _instancias_do_conjunto(lista, unidade):
            if collections.Counter(_posicao(e) for e in inst) != unidade:
                continue
            perfil = _analisar_instancia(inst, ())
            if perfil is None:
                continue
            por_id = {e.id: e for e in inst}
            saida.append({"conjunto": conj, "pecas": [por_id[i] for i in perfil["cadeia_ids"]], "perfil": perfil})
    return saida


def analisar_modelo(doc: Documento) -> List[dict]:
    """Uma linha por conjunto, para o diálogo: conjunto, perfil da telha, instâncias, facetas, raio do
    modelo, raio alvo (interno comercial), ângulo, e quantas instâncias já estão ajustadas."""
    por_conj: Dict[str, dict] = collections.OrderedDict()
    for it in instancias(doc):
        p = it["perfil"]
        r = por_conj.setdefault(it["conjunto"], {
            "conjunto": it["conjunto"], "perfil": p.get("perfil", ""), "instancias": 0, "ajustadas": 0,
            "facetas": p.get("facetas", 0), "raio_modelo": p.get("raio_modelo"), "raio_int": p.get("raio_int"),
            "raio_ext": p.get("raio_ext"), "angulo": p.get("angulo"), "reta1": p.get("reta1"), "reta2": p.get("reta2")})
        r["instancias"] += 1
        if all((e.atributos or {}).get(CHAVE) for e in it["pecas"]):
            r["ajustadas"] += 1
    return list(por_conj.values())


def _ajustar_instancia(it: dict, raio_int: float) -> Optional[dict]:
    """Reescreve os vértices das peças de uma instância. Devolve {raio_modelo, raio_novo} ou None."""
    from nucleo2d.detalhe.telhas import _medidas
    p = it["perfil"]
    pecas = it["pecas"]
    a, b, w = p["eixos_perfil"]
    d1, d2, I = p["d1"], p["d2"], p["I"]
    theta = math.radians(p["angulo"])
    R = raio_int + p["altura_onda"] / 2.0                # linha média da telha
    T = R * math.tan(theta / 2.0)
    t1 = (I[0] - d1[0] * T, I[1] - d1[1] * T)
    t2 = (I[0] + d2[0] * T, I[1] + d2[1] * T)
    bis = (d2[0] - d1[0], d2[1] - d1[1])
    nb = math.hypot(*bis)
    if nb < 1e-9:
        return None
    bis = (bis[0] / nb, bis[1] / nb)
    C = (I[0] + bis[0] * R / math.cos(theta / 2.0), I[1] + bis[1] * R / math.cos(theta / 2.0))
    r0 = (t1[0] - C[0], t1[1] - C[1])
    r1 = (t2[0] - C[0], t2[1] - C[1])
    sentido = 1.0 if r0[0] * r1[1] - r0[1] * r1[0] >= 0 else -1.0

    def no_arco(f):
        ang = sentido * theta * f
        return (C[0] + r0[0] * math.cos(ang) - r0[1] * math.sin(ang), C[1] + r0[0] * math.sin(ang) + r0[1] * math.cos(ang))

    def em_2d(v):
        return (_dot(v, a), _dot(v, b))

    def em_3d(x, y, wv):
        return (a[0] * x + b[0] * y + w[0] * wv, a[1] * x + b[1] * y + w[1] * wv, a[2] * x + b[2] * y + w[2] * wv)

    def eixo_da_peca(e):
        c, eixos, ext = _medidas(e)
        outros = [(ax, x) for ax, x in zip(eixos, ext) if abs(_dot(ax, w)) < 0.9]
        (ax_l, comp), _ = sorted(outros, key=lambda t: -t[1])[:2]
        u = em_2d(ax_l)
        n = math.hypot(*u) or 1.0
        return em_2d(c), (u[0] / n, u[1] / n), comp

    def transformar(e, origem, u_old, s, destino, u_new):
        """v' = destino + (x·s)·u_new + y·n_new, com (x, y) as coordenadas de v em (u_old, n_old) a partir de `origem`."""
        n_old = (-u_old[1], u_old[0])
        n_new = (-u_new[1], u_new[0])
        novos = []
        for v in e.vertices:
            v2 = em_2d(v)
            dx, dy = v2[0] - origem[0], v2[1] - origem[1]
            x, y = dx * u_old[0] + dy * u_old[1], dx * n_old[0] + dy * n_old[1]
            x2 = destino[0] + x * s * u_new[0] + y * n_new[0]
            y2 = destino[1] + x * s * u_new[1] + y * n_new[1]
            novos.append(em_3d(x2, y2, _dot(v, w)))
        return novos

    reta1, reta2, meio = pecas[0], pecas[-1], pecas[1:-1]
    n = len(meio)
    if n < 1:
        return None
    novos: Dict[str, list] = {}
    # as retas: a ponta livre fica, a ponta da dobra vai para a tangência nova
    for e, p_livre, d, t_old, t_new in ((reta1, p["p1"], d1, p["t1_modelo"], t1),
                                        (reta2, p["p2"], (-d2[0], -d2[1]), p["t2_modelo"], t2)):
        L_old = math.dist(p_livre, t_old)
        L_new = math.dist(p_livre, t_new)
        if L_old < 1e-6 or L_new <= 0:
            return None
        novos[e.id] = transformar(e, p_livre, d, L_new / L_old, p_livre, d)
    # as facetas: cada uma vira a corda k do arco novo, com o perfil girado junto
    centros = [eixo_da_peca(e) for e in meio]
    for k, e in enumerate(meio):
        c, u, L_old = centros[k]
        antes = centros[k - 1][0] if k > 0 else em_2d(_medidas(reta1)[0])
        depois = centros[k + 1][0] if k + 1 < n else em_2d(_medidas(reta2)[0])
        if u[0] * (depois[0] - antes[0]) + u[1] * (depois[1] - antes[1]) < 0:
            u = (-u[0], -u[1])
        A, B = no_arco(k / n), no_arco((k + 1) / n)
        M = ((A[0] + B[0]) / 2.0, (A[1] + B[1]) / 2.0)
        L_new = math.dist(A, B)
        u_new = ((B[0] - A[0]) / L_new, (B[1] - A[1]) / L_new)
        if L_old < 1e-6:
            return None
        novos[e.id] = transformar(e, c, u, L_new / L_old, M, u_new)
    for e in pecas:
        at = dict(e.atributos or {})
        guardado = at.get(CHAVE) or {}
        original = guardado.get("original") or {"vertices": [list(v) for v in e.vertices]}
        e.vertices = [tuple(v) for v in novos[e.id]]
        at[CHAVE] = {"raio_int": raio_int, "raio_modelo": p.get("raio_modelo"), "original": original}
        e.atributos = at
    return {"raio_modelo": p.get("raio_modelo"), "raio_novo": round(R, 1)}


def ajustar_modelo(doc: Documento, raio_int: Optional[float] = None, conjuntos: Optional[Sequence[str]] = None) -> dict:
    """Reescreve todas as multidobras (ou só os `conjuntos` pedidos) com o raio interno `raio_int` (o
    comercial por padrão). A instância já ajustada parte dos vértices originais guardados, então
    aplicar de novo com outro raio funciona. Devolve {"instancias", "pecas", "conjuntos", "falhas"}."""
    from nucleo2d.detalhe.telhas import RAIO_INTERNO_COMERCIAL
    raio_int = float(raio_int or RAIO_INTERNO_COMERCIAL)
    quer = set(conjuntos) if conjuntos else None
    saida = {"instancias": 0, "pecas": 0, "conjuntos": [], "falhas": [], "raio_int": raio_int}
    _restaurar(doc, quer, limpar=False)                      # parte sempre do original
    for it in instancias(doc):
        if quer is not None and it["conjunto"] not in quer:
            continue
        r = _ajustar_instancia(it, raio_int)
        if r is None:
            saida["falhas"].append("%s: uma instância sem dobra reconhecível ficou como estava" % it["conjunto"])
            continue
        saida["instancias"] += 1
        saida["pecas"] += len(it["pecas"])
        if it["conjunto"] not in saida["conjuntos"]:
            saida["conjuntos"].append(it["conjunto"])
    return saida


def _restaurar(doc: Documento, quer, limpar: bool) -> int:
    n = 0
    for e in doc.entidades.values():
        if not isinstance(e, Solido):
            continue
        g = (e.atributos or {}).get(CHAVE)
        if not g:
            continue
        from nucleo2d.detalhe.base import _marcas
        if quer is not None and str(_marcas(e).get("conjunto") or "") not in quer:
            continue
        orig = (g.get("original") or {}).get("vertices")
        if orig:
            e.vertices = [tuple(v) for v in orig]
            n += 1
        if limpar:
            e.atributos = {k: v for k, v in (e.atributos or {}).items() if k != CHAVE}
    return n


def desfazer_modelo(doc: Documento, conjuntos: Optional[Sequence[str]] = None) -> dict:
    """Voltar ao original: os vértices guardados voltam e a marca sai. Devolve {"pecas"}."""
    quer = set(conjuntos) if conjuntos else None
    return {"pecas": _restaurar(doc, quer, limpar=True)}
