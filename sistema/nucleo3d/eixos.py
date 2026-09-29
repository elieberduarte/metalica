# -*- coding: utf-8 -*-
"""Eixos da obra: as linhas numeradas (as tesouras, atravessadas ao galpão) e as linhas
com letra (os apoios — chumbadores ou chapas de base — ao longo do galpão), identificadas
do próprio modelo e gravadas no projeto para o usuário renomear, mover e acrescentar.

O IFC de fábrica não traz os pilares de concreto nem a malha de eixos: o que há são as
tesouras e os chumbadores. As tesouras dão o eixo do galpão (PCA em planta dos centroides
das peças delas: com várias tesouras o maior espalhamento é o eixo; com uma só, o menor) e
cada agrupamento de peças ao longo dele é um eixo numerado (1, 2, 3…). Os chumbadores
(ou, sem eles, as chapas horizontais mais baixas) agrupados na direção atravessada são os
eixos com letra (A, B, C…). Coordenadas: `g` ao longo do galpão, `p` atravessado, no plano.

`segmentos` dá as linhas em 3D para as plantas desenharem (com as bolinhas e as cotas
entre eixos em `nucleo2d.detalhe.conjuntos._desenhar_eixos`), e `de_dict` valida o que o
usuário gravou no projeto (`projeto.json` → `eixos`).
"""
import math
import re
import string
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido, Barra, Chapa

Ponto = Tuple[float, float, float]

#: Peças a menos disto (mm) na mesma linha são o mesmo eixo.
GAP_EIXO = 600.0
#: Quanto a linha do eixo passa além do último eixo atravessado (mm).
FOLGA_EIXO = 1500.0
#: A treliça pela geometria: as peças de um conjunto num plano vertical — finas atravessado ao
#: plano (mm), compridas ao longo do vão e com altura (a do depósito químico, 29/09, veio sem a
#: categoria TESOURAS no IFC e os eixos eram adivinhados pelas peças altas).
ESPESSURA_TRELICA = 600.0
VAO_MINIMO_TRELICA = 2000.0
ALTURA_MINIMA_TRELICA = 300.0
#: Tipos de peça (nomes.json) que não são de treliça.
_NAO_TRELICA = ("terca", "agulhamento", "contraventamento", "telha", "rufo", "calha", "chumbador", "corrente",
                "suporte", "castanha", "cantoneira_forro", "perfil_fechamento")
#: Tipos de conjunto que não são treliça.
_CONJ_NAO_TRELICA = ("contraventamento", "agulhamento", "suporte_terca", "chumbador", "terca")


def _centroide(vs: Sequence[Ponto]) -> Ponto:
    n = len(vs)
    return (sum(v[0] for v in vs) / n, sum(v[1] for v in vs) / n, sum(v[2] for v in vs) / n)


def _pca_2d(pts: Sequence[Tuple[float, float]]):
    """(eixo maior, eixo menor) unitários e os desvios ao longo deles, em planta."""
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    maior = (math.cos(ang), math.sin(ang))
    menor = (-maior[1], maior[0])
    var_maior = sxx * maior[0] ** 2 + 2 * sxy * maior[0] * maior[1] + syy * maior[1] ** 2
    var_menor = sxx * menor[0] ** 2 + 2 * sxy * menor[0] * menor[1] + syy * menor[1] ** 2
    if var_menor > var_maior:
        maior, menor, var_maior, var_menor = menor, maior, var_menor, var_maior
    return maior, menor, math.sqrt(max(var_maior, 0.0)), math.sqrt(max(var_menor, 0.0))


def _agrupar(valores: Sequence[float], gap: float = GAP_EIXO) -> List[float]:
    """Valores em 1D agrupados por proximidade; a posição de cada grupo é a média."""
    vs = sorted(valores)
    grupos: List[List[float]] = []
    for v in vs:
        if grupos and v - grupos[-1][-1] <= gap:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    return [sum(g) / len(g) for g in grupos]


def _letra(i: int) -> str:
    letras = string.ascii_uppercase
    return letras[i] if i < 26 else letras[i // 26 - 1] + letras[i % 26]


def _marcas(e) -> dict:
    return (getattr(e, "atributos", None) or {}).get("marcas") or {}


def _vertices(e) -> List[Ponto]:
    if isinstance(e, Solido):
        return list(e.vertices)
    if isinstance(e, Barra):
        return [tuple(e.inicio), tuple(e.fim)]
    if isinstance(e, Chapa):
        try:
            from nucleo3d import geometria as _geo
            return [tuple(v) for v in _geo.malha(e)[0]]          # chapa paramétrica
        except Exception:                                       # noqa: BLE001
            return [tuple(e.origem)]
    return []


def _eixo_em_planta(e):
    """(direção unitária, comprimento) da peça em planta: a barra de ponta a ponta; o sólido e a
    chapa pelo maior espalhamento dos vértices."""
    if isinstance(e, Barra):
        dx, dy = e.fim[0] - e.inicio[0], e.fim[1] - e.inicio[1]
        L = math.hypot(dx, dy)
        return ((dx / L, dy / L), L) if L > 1e-9 else (None, 0.0)
    pts = [(v[0], v[1]) for v in _vertices(e)]
    if len(pts) < 2:
        return None, 0.0
    d = _pca_2d(pts)[0]
    q = [x * d[0] + y * d[1] for x, y in pts]
    return d, max(q) - min(q)


def _em_pe(e) -> bool:
    """A peça mais alta que comprida em planta: o chumbador do pilar. O de parede (deitado, preso
    na chapa em pé na face do concreto) não marca eixo — a posição dele ao longo da barra é a
    parede, não o centro de um apoio."""
    vs = _vertices(e)
    if not vs:
        return False
    zs = [v[2] for v in vs]
    return max(zs) - min(zs) >= _eixo_em_planta(e)[1]


def _limpo(d: Tuple[float, float]) -> Tuple[float, float]:
    """A direção sem o resíduo numérico: a quase alinhada ao x ou ao y fica alinhada."""
    x, y = d
    if abs(x) < 2e-4:
        x = 0.0
    if abs(y) < 2e-4:
        y = 0.0
    L = math.hypot(x, y)
    return (x / L, y / L)


def _direcao_dominante(pecas, simetria: int) -> Optional[Tuple[float, float]]:
    """A direção em planta que mais se repete nas peças compridas (média do ângulo × `simetria`,
    pesada pelo comprimento ao quadrado): 2 dá uma direção (o vão das treliças — banzos e
    diagonais caem todos nele em planta), 4 dá o par ortogonal da malha."""
    c = sn = 0.0
    for e in pecas:
        d, L = _eixo_em_planta(e)
        if d is None or L < 300.0:
            continue
        a = math.atan2(d[1], d[0]) * simetria
        c += L * L * math.cos(a)
        sn += L * L * math.sin(a)
    if math.hypot(c, sn) < 1e-9:
        return None
    a = math.atan2(sn, c) / simetria
    return _limpo((math.cos(a), math.sin(a)))


def _altura_fora_do_caimento(ss: Sequence[float], zs: Sequence[float]) -> float:
    """A altura do grupo descontado o caimento (reta z = a·s + b pelos vértices): a treliça tem
    banzo de cima e de baixo; a peça deitada no plano inclinado da cobertura só a do perfil."""
    n = len(ss)
    ms, mz = sum(ss) / n, sum(zs) / n
    sss = sum((s - ms) ** 2 for s in ss)
    a = sum((s - ms) * (z - mz) for s, z in zip(ss, zs)) / sss if sss > 1e-9 else 0.0
    r = [z - mz - a * (s - ms) for s, z in zip(ss, zs)]
    return max(r) - min(r)


def _trelicas(pecas, vao: Tuple[float, float], serve) -> List[Tuple[float, int]]:
    """As treliças com o vão na direção `vao`: por conjunto (os que `serve` aceita), as peças
    agrupadas atravessado ao vão; o grupo fino, comprido e com altura, de 3 peças ou mais, é uma
    treliça. Devolve (posição atravessada, peças) de cada uma."""
    g = (vao[1], -vao[0])
    por: Dict[str, list] = {}
    for e in pecas:
        m = str(_marcas(e).get("conjunto") or "")
        if not m or not serve(m, e):
            continue
        vs = _vertices(e)
        if vs:
            c = _centroide(vs)
            por.setdefault(m, []).append((c[0] * g[0] + c[1] * g[1], vs))
    saida = []
    for lst in por.values():
        lst.sort(key=lambda t: t[0])
        grupos: List[list] = []
        for t in lst:
            if grupos and t[0] - grupos[-1][-1][0] <= GAP_EIXO:
                grupos[-1].append(t)
            else:
                grupos.append([t])
        for gr in grupos:
            if len(gr) < 3:
                continue
            vs = [v for _q, vv in gr for v in vv]
            gg = [v[0] * g[0] + v[1] * g[1] for v in vs]
            ss = [v[0] * vao[0] + v[1] * vao[1] for v in vs]
            if (max(gg) - min(gg) <= ESPESSURA_TRELICA and max(ss) - min(ss) >= VAO_MINIMO_TRELICA
                    and _altura_fora_do_caimento(ss, [v[2] for v in vs]) >= ALTURA_MINIMA_TRELICA):
                saida.append((sum(q for q, _vv in gr) / len(gr), len(gr)))
    return saida


def _agrupar_pesado(valores: Sequence[Tuple[float, int]], gap: float = GAP_EIXO) -> List[float]:
    """(posição, peso) agrupados por proximidade; a posição de cada grupo é a média pesada."""
    grupos: List[list] = []
    for v, w in sorted(valores):
        if grupos and v - grupos[-1][-1][0] <= gap:
            grupos[-1].append((v, w))
        else:
            grupos.append([(v, w)])
    return [sum(v * w for v, w in gr) / sum(w for _v, w in gr) for gr in grupos]


def _chapas_de_apoio(pecas, tipos: dict, z_teto: float) -> list:
    """As chapas deitadas do nível mais baixo (até `z_teto`): onde a estrutura se apoia quando o
    modelo não tem chumbadores. Só o nível de baixo — as chapas deitadas dos nós das treliças,
    mais acima, davam uma letra cada (o depósito químico saiu com 10)."""
    cand = []
    for e in pecas:
        if not isinstance(e, (Solido, Chapa)):
            continue
        t = str(tipos.get(str(_marcas(e).get("posicao") or "")) or "")
        if t and t not in ("chapa", "parte"):
            continue
        vs = _vertices(e)
        if len(vs) < 4:
            continue
        zs = [v[2] for v in vs]
        xs = [v[0] for v in vs]
        ys = [v[1] for v in vs]
        if max(zs) - min(zs) <= 25.0 and max(max(xs) - min(xs), max(ys) - min(ys)) >= 80.0 and max(zs) <= z_teto:
            cand.append((min(zs), e))
    for z0 in sorted({round(z) for z, _e in cand}):
        nivel = [e for z, e in cand if z0 - 1.0 <= z <= z0 + 100.0]
        if len(nivel) >= 2:
            return nivel
    return []


def identificar_eixos(doc: Documento, nomes: Optional[dict] = None) -> dict:
    """Os eixos pelo modelo. `nomes`: o nomes.json do detalhamento (tipos por marca e por
    conjunto). Os eixos numerados são as treliças — as tesouras do nomes.json ou, sem elas, os
    conjuntos que a geometria mostra que são treliça (planos verticais); os com letra, os apoios
    (chumbadores ou as chapas deitadas do nível mais baixo), e cada apoio cai num cruzamento.
    Sem treliça nenhuma, as tesouras são adivinhadas pelas peças mais altas."""
    nomes = nomes or {}
    tipos = nomes.get("tipos") or {}
    tipos_conj = nomes.get("tipos_conjuntos") or {}
    conj_tes = {m for m, t in tipos_conj.items() if t == "tesoura"}
    pecas = [e for e in doc.entidades.values() if isinstance(e, (Solido, Barra, Chapa)) and getattr(e, "visivel", True)]
    if not pecas:
        raise ValueError("o modelo não tem peças.")
    todos_v = [v for e in pecas for v in _vertices(e)]
    z_min, z_max = min(v[2] for v in todos_v), max(v[2] for v in todos_v)

    def marca_conj(e) -> str:
        return str(_marcas(e).get("conjunto") or "")

    def peca_de_trelica(e) -> bool:
        t = str(tipos.get(str(_marcas(e).get("posicao") or "")) or "")
        return not any(t.startswith(n) for n in _NAO_TRELICA)

    def serve_tesoura(m, e) -> bool:
        return m in conj_tes

    def serve_conjunto(m, e) -> bool:
        t = str(tipos_conj.get(m) or "")
        return not any(t.startswith(n) for n in _CONJ_NAO_TRELICA) and peca_de_trelica(e)

    # as treliças: as tesouras do nomes.json; sem elas, os conjuntos em plano vertical, com o vão na
    # direção (das duas da malha) que der mais treliça
    tes = [e for e in pecas if marca_conj(e) in conj_tes] if conj_tes else []
    trel: List[Tuple[float, int]] = []
    vao = None
    if tes:
        vao = _direcao_dominante(tes, 2)
        if vao:
            trel = _trelicas(tes, vao, serve_tesoura)
    if not trel:
        malha = _direcao_dominante([e for e in pecas if marca_conj(e)], 4)
        melhor: List[Tuple[float, int]] = []
        for d in ((malha, (-malha[1], malha[0])) if malha else ()):
            achadas = _trelicas(pecas, d, serve_conjunto)
            if sum(n for _q, n in achadas) > sum(n for _q, n in melhor):
                melhor, vao = achadas, d
        trel = melhor
        if trel:
            tes = [e for e in pecas if marca_conj(e) and serve_conjunto(marca_conj(e), e)]
    if trel:
        g = (vao[1], -vao[0])
        if g[0] < 0 or (abs(g[0]) < 1e-9 and g[1] < 0):
            g = (-g[0], -g[1])
            trel = [(-q, n) for q, n in trel]
        gs_n = _agrupar_pesado(trel)
    else:
        # sem treliça reconhecida: as peças da metade de cima do modelo desenham as tesouras
        tes = tes or [e for e in pecas if _centroide(_vertices(e))[2] >= z_min + 0.5 * (z_max - z_min)] or pecas
        cs = [_centroide(_vertices(e)) for e in tes if _vertices(e)]
        maior, menor, d_maior, d_menor = _pca_2d([(c[0], c[1]) for c in cs])
        # várias tesouras: o maior espalhamento é o eixo do galpão; uma só: o menor
        varias = d_maior > 500.0 and d_menor > 500.0 and d_maior / max(d_menor, 1.0) < 8.0
        g = maior if (varias or d_maior > 4.0 * d_menor and len(_agrupar([c[0] * maior[0] + c[1] * maior[1] for c in cs])) >= 2) else menor
        if d_maior < 500.0:
            g = menor
        if g[0] < 0 or (abs(g[0]) < 1e-9 and g[1] < 0):
            g = (-g[0], -g[1])
        gs_n = _agrupar([c[0] * g[0] + c[1] * g[1] for c in cs])
    p = (-g[1], g[0])
    # apoios: chumbadores; senão as chapas deitadas do nível mais baixo, junto do pé das tesouras
    chumb = [e for e in pecas if tipos.get(str(_marcas(e).get("posicao") or "")) == "chumbador" and _em_pe(e)]
    origem_letras = "chumbadores"
    if not chumb:
        z_tes = min(v[2] for e in tes for v in _vertices(e))
        chumb = _chapas_de_apoio(pecas, tipos, z_tes + 800.0)
        origem_letras = "chapas de base" if chumb else "extremos das tesouras"
    if chumb:
        cc = [_centroide(_vertices(e)) for e in chumb]
        ps = [c[0] * p[0] + c[1] * p[1] for c in cc]
        z_base = min(v[2] for e in chumb for v in _vertices(e))
        if trel:
            # cada apoio num cruzamento: o eixo numerado vai ao centro dos apoios dele, e a linha de
            # apoios sem treliça em cima ganha o seu
            for q in _agrupar([c[0] * g[0] + c[1] * g[1] for c in cc]):
                i = min(range(len(gs_n)), key=lambda k: abs(gs_n[k] - q))
                if abs(gs_n[i] - q) <= GAP_EIXO:
                    gs_n[i] = q
                else:
                    gs_n.append(q)
            gs_n.sort()
    else:
        vs_t = [v for e in tes for v in _vertices(e)]
        ps = [min(v[0] * p[0] + v[1] * p[1] for v in vs_t), max(v[0] * p[0] + v[1] * p[1] for v in vs_t)]
        z_base = min(v[2] for v in vs_t)
    numeros = [{"nome": str(i + 1), "pos": round(v, 1)} for i, v in enumerate(gs_n)]
    letras = [{"nome": _letra(i), "pos": round(v, 1)} for i, v in enumerate(_agrupar(ps))]
    return {"eixo_g": [round(g[0], 6), round(g[1], 6)], "perp_g": [round(p[0], 6), round(p[1], 6)],
            "numeros": numeros, "letras": letras, "z_base": round(z_base, 1),
            "origem": "auto", "fonte_letras": origem_letras}


def de_dict(d: Optional[dict]) -> Optional[dict]:
    """O que veio do projeto (ou do usuário), validado; None quando não serve."""
    if not isinstance(d, dict):
        return None
    try:
        g = [float(d["eixo_g"][0]), float(d["eixo_g"][1])]
        L = math.hypot(g[0], g[1])
        if L < 1e-9:
            return None
        g = [g[0] / L, g[1] / L]
        p = [-g[1], g[0]]
        def lista(chave):
            saida = []
            for item in d.get(chave) or []:
                nome = str(item.get("nome") or "").strip()
                if not nome:
                    continue
                saida.append({"nome": nome[:6], "pos": round(float(item.get("pos")), 1)})
            return sorted(saida, key=lambda x: x["pos"])
        numeros, letras = lista("numeros"), lista("letras")
        if not numeros and not letras:
            return None
        return {"eixo_g": g, "perp_g": p, "numeros": numeros, "letras": letras,
                "z_base": float(d.get("z_base") or 0.0), "origem": str(d.get("origem") or "usuario"),
                "fonte_letras": str(d.get("fonte_letras") or "")}
    except (KeyError, TypeError, ValueError):
        return None


def segmentos(eixos: dict, folga: float = FOLGA_EIXO) -> List[dict]:
    """As linhas dos eixos em 3D (z = z_base): {"nome", "tipo": "numero"|"letra", "a", "b"}.
    O eixo numerado corre atravessado, do primeiro ao último eixo com letra (mais a folga);
    o eixo com letra corre ao longo do galpão, do primeiro ao último numerado."""
    g, p = eixos["eixo_g"], eixos["perp_g"]
    z = float(eixos.get("z_base") or 0.0)
    gs = [e["pos"] for e in eixos["numeros"]] or [0.0]
    ps = [e["pos"] for e in eixos["letras"]] or [0.0]
    g0, g1 = min(gs) - folga, max(gs) + folga
    p0, p1 = min(ps) - folga, max(ps) + folga
    saida = []
    for e in eixos["numeros"]:
        a = (g[0] * e["pos"] + p[0] * p0, g[1] * e["pos"] + p[1] * p0, z)
        b = (g[0] * e["pos"] + p[0] * p1, g[1] * e["pos"] + p[1] * p1, z)
        saida.append({"nome": e["nome"], "tipo": "numero", "a": a, "b": b})
    for e in eixos["letras"]:
        a = (g[0] * g0 + p[0] * e["pos"], g[1] * g0 + p[1] * e["pos"], z)
        b = (g[0] * g1 + p[0] * e["pos"], g[1] * g1 + p[1] * e["pos"], z)
        saida.append({"nome": e["nome"], "tipo": "letra", "a": a, "b": b})
    return saida


def _ordem_do_nome(nome: str):
    """1 < 2 < 10; A < B < AA"""
    m = re.match(r"^(\d+)(.*)$", nome)
    return (0, int(m.group(1)), m.group(2)) if m else (1, len(nome), nome)


def fora_do_eixo(ponto, segs: Sequence[dict], perto: float = 600.0) -> List[Tuple[str, float]]:
    """o eixo mais perto do ponto em cada direção (nome, distância em mm), quando a menos de
    `perto`. Serve para o pilar que a locação põe fora do eixo."""
    out = {}
    for s in segs:
        a, b = s["a"], s["b"]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        d = abs((ponto[0] - a[0]) * dy - (ponto[1] - a[1]) * dx) / L
        tipo = s.get("tipo") or s["nome"]
        if d < perto and (tipo not in out or d < out[tipo][1]):
            out[tipo] = (s["nome"], d)
    return list(out.values())


def onde(ponto, segs: Sequence[dict], perto: float = 600.0) -> str:
    """Onde fica um ponto (x, y) na malha de eixos, como no projeto: "eixos 4 / C",
    "eixo 4 / entre B e C", "entre 3 e 4 / C". `segs` são as linhas de `segmentos` (e as
    inclinadas, tipo "extra"); a menos de `perto` mm o ponto está no eixo."""
    partes = []
    for tipo in ("numero", "letra"):
        fam = [s for s in segs if s.get("tipo") == tipo]
        if not fam:
            continue
        a, b = fam[0]["a"], fam[0]["b"]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        n = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
        pos = sorted((s["a"][0] * n[0] + s["a"][1] * n[1], s["nome"]) for s in fam)
        v = ponto[0] * n[0] + ponto[1] * n[1]
        q, nome = min(pos, key=lambda x: abs(x[0] - v))
        if abs(q - v) < perto:
            partes.append((True, nome))
            continue
        antes = [x for x in pos if x[0] < v]
        depois = [x for x in pos if x[0] > v]
        if antes and depois:
            par = sorted((antes[-1][1], depois[0][1]), key=_ordem_do_nome)
            partes.append((False, "entre %s e %s" % tuple(par)))
        else:
            partes.append((False, "fora do %s" % nome))
    for s in segs:
        if s.get("tipo") != "extra":
            continue
        a, b = s["a"], s["b"]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-9 else min(max(((ponto[0] - a[0]) * dx + (ponto[1] - a[1]) * dy) / L2, 0.0), 1.0)
        if math.hypot(ponto[0] - a[0] - dx * t, ponto[1] - a[1] - dy * t) < perto:
            partes.append((True, s["nome"]))
    if not partes:
        return ""
    if len(partes) > 1 and all(e for e, _n in partes):
        return "eixos " + " / ".join(n for _e, n in partes)
    return " / ".join(("eixo " + n) if e else n for e, n in partes)
