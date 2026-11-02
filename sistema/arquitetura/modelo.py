# -*- coding: utf-8 -*-
"""A arquitetura dentro do modelo 3D (fase 1b, 30/10/2026): a mesma base do metálico e do pré-moldado.

Cada elemento é uma entidade comum do `modelo.json` (um `Solido`), e a **definição** dele fica em `atributos.arq`. O
`regenerar` refaz as malhas pela definição: a parede pelo motor (`paredes.montar`), com as uniões e os vãos. Assim o
elemento aparece no editor, no modo ver, no corte (`nucleo2d/vistas.py`) e no IFC sem mudar o núcleo.

    arq = {"elemento": "parede", "p0": [x, y], "p1": [x, y], "tipo": "EXT20", "base": "Térreo", "topo": "Superior",
           "vaos": [{"tipo": "janela", "u": 750, "largura": 1500, "altura": 1200, "peitoril": 1100}, ...]}
    arq = {"elemento": "laje", "contorno": [[x, y], ...], "furos": [[[x, y], ...]], "nivel": "Superior"}
    arq = {"elemento": "ambiente", "nome": "Sala", "piso": "porcelanato", "nivel": "Térreo", "ret": [x0, x1, y0, y1]}
    arq = {"elemento": "esquadria", "parede": <id>, "codigo": "J1", ...}     (derivada da parede, refeita sempre)
    arq = {"elemento": "lote", "contorno": [[x, y], ...], "permeaveis": [[[x, y], ...], ...], "nivel": "Térreo"}

- **Níveis** (`metadados.arquitetura.niveis`): o nome, a cota do piso acabado e a espessura da laje que tem o topo nele.
- **ARQ-03:** a parede vai da cota do nível da base ao fundo da laje do nível do topo.
- **ARQ-06:** a área do ambiente é contada pelas faces internas das paredes que o cercam.
"""
import math
from typing import Dict, List, Optional, Tuple

from nucleo3d.geometria import extrudar
from nucleo3d.modelo import Camada, Documento, Material, Solido

from .paredes import TIPOS, Esquadria, Parede, montar, prisma, solido_da_parede

CAMADAS = {
    "parede_ext": ("ARQ — Paredes de fachada", "#e9e4da"),
    "parede_int": ("ARQ — Paredes internas", "#f1ede6"),
    "esquadria": ("ARQ — Vidros e esquadrias", "#9fc6e8"),
    "laje": ("ARQ — Pisos e lajes", "#c2bcae"),
    "ambiente": ("ARQ — Ambientes", "#d8cfc0"),
    "telhado": ("ARQ — Telhas", "#cfd6e0"),
    "escada": ("ARQ — Escadas e rampas", "#aaa39a"),
    "lote": ("ARQ — Terreno", "#8fb573"),
}
GRUPO_CAMADAS = "ARQUITETURA"
MATERIAIS = {
    "Alvenaria": dict(cor="#ece7dd", metalico=0.0, rugosidade=0.9),
    "Madeira": dict(cor="#8b5a2b", metalico=0.0, rugosidade=0.7),
    "Granito": dict(cor="#6f6a66", metalico=0.1, rugosidade=0.4),
    "Piso": dict(cor="#d8cfc0", metalico=0.0, rugosidade=0.6),
    "Concreto": dict(cor="#b9b2a6", metalico=0.0, rugosidade=0.9),
    "Telha": dict(cor="#cfd6e0", metalico=0.6, rugosidade=0.45),
    "Vidro": dict(cor="#9fc6e8", opacidade=0.35, metalico=0.1, rugosidade=0.05),
    "Grama": dict(cor="#8fb573", metalico=0.0, rugosidade=1.0),
}
DIVISA = 100            # a linha da divisa do lote no 3D: uma faixa de 10 cm por dentro do contorno
PREFIXO_ID = "arq"
_CODIGOS = {"janela": "J", "portajanela": "PJ", "porta": "P"}


# ------------------------------------------------------------------ níveis

def niveis(doc: Documento) -> Dict[str, dict]:
    lista = ((doc.metadados or {}).get("arquitetura") or {}).get("niveis") or []
    return {n["nome"]: n for n in lista}


def definir_niveis(doc: Documento, lista: List[dict]):
    """[{"nome": "Térreo", "cota": 0, "laje": 100}, ...] — cota do piso acabado e espessura da laje, em mm"""
    doc.metadados.setdefault("arquitetura", {})["niveis"] = [dict(n) for n in lista]


def _cota(nv: Dict[str, dict], nome: str) -> float:
    if nome not in nv:
        raise ValueError(f"nível desconhecido: {nome!r} (níveis: {', '.join(nv) or 'nenhum'})")
    return float(nv[nome]["cota"])


def altura_da_parede(nv: Dict[str, dict], base: str, topo: str) -> Tuple[float, float]:
    """ARQ-03: da cota do piso da base ao fundo da laje do topo"""
    z0 = _cota(nv, base)
    z1 = _cota(nv, topo) - float(nv[topo].get("laje", 0))
    if z1 <= z0:
        raise ValueError(f"parede de {base} a {topo} sem altura ({z0:.0f} → {z1:.0f})")
    return z0, z1


def so_camadas_da_arquitetura(doc: Documento):
    """o projeto de arquitetura não leva as camadas padrão da metálica (Terças, Contraventamento…) enquanto vazias"""
    _preparar(doc)
    usadas = {e.camada for e in doc.entidades.values()}
    for nome in list(doc.camadas):
        if not nome.startswith("ARQ — ") and nome not in usadas:
            del doc.camadas[nome]


# ------------------------------------------------------------------ criar

def _preparar(doc: Documento):
    for chave, (nome, cor) in CAMADAS.items():
        if nome not in doc.camadas:
            doc.camadas[nome] = Camada(nome=nome, cor=cor, grupo=GRUPO_CAMADAS)
    for nome, m in MATERIAIS.items():
        if nome not in doc.materiais:
            doc.materiais[nome] = Material(nome, m["cor"], opacidade=m.get("opacidade", 1.0), metalico=m["metalico"],
                                           rugosidade=m["rugosidade"])


def _novo(doc: Documento, arq: dict, camada: str, nome: str, material: str, id_: Optional[str] = None) -> Solido:
    s = Solido(nome=nome, camada=camada, material=material, atributos={"arq": arq})
    if id_:
        s.id = id_
    doc.add(s)
    return s


def nova_parede(doc, p0, p1, tipo="EXT20", base="Térreo", topo="Superior", vaos=(), nome="", id_=None) -> Solido:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de parede desconhecido: {tipo}")
    _preparar(doc)
    arq = {"elemento": "parede", "p0": list(p0), "p1": list(p1), "tipo": tipo, "base": base, "topo": topo,
           "vaos": [dict(v) for v in vaos]}
    cam = CAMADAS["parede_ext" if tipo.startswith("EXT") else "parede_int"][0]
    return _novo(doc, arq, cam, nome or TIPOS[tipo].nome, "Alvenaria", id_)


def nova_laje(doc, contorno, nivel, furos=(), nome="Laje", id_=None) -> Solido:
    _preparar(doc)
    arq = {"elemento": "laje", "contorno": [list(p) for p in contorno], "furos": [[list(p) for p in f] for f in furos],
           "nivel": nivel}
    return _novo(doc, arq, CAMADAS["laje"][0], nome, "Concreto", id_)


def novo_telhado(doc, aguas, espessura=50, nome="Telhado", id_=None) -> Solido:
    """aguas = [{"ret": [x0, x1, y0, y1], "beiral_y": y, "z_beiral": z, "inclinacao": 0.10}, ...]"""
    _preparar(doc)
    arq = {"elemento": "telhado", "aguas": [dict(a) for a in aguas], "espessura": espessura}
    return _novo(doc, arq, CAMADAS["telhado"][0], nome, "Telha", id_)


def nova_escada(doc, lances, base, topo, patamares=(), piso=280, nome="Escada", id_=None) -> Solido:
    """lances = [{"p0": [x, y], "dir": [dx, dy], "largura": 1000, "espelhos": 10}, ...] (p0 no canto direito do pé do
    lance, a largura para a esquerda de quem sobe); patamares = [{"ret": [x0, x1, y0, y1], "apos": n espelhos}]"""
    _preparar(doc)
    arq = {"elemento": "escada", "lances": [dict(l) for l in lances], "patamares": [dict(p) for p in patamares],
           "base": base, "topo": topo, "piso": piso}
    return _novo(doc, arq, CAMADAS["escada"][0], nome, "Concreto", id_)


def novo_lote(doc, contorno, permeaveis=(), nivel="Térreo", nome="Lote", id_=None) -> Solido:
    """o terreno da estatística (`estatistica.py`): o contorno pelas divisas e as áreas permeáveis (grama, jardim). O que
    não está numa área permeável conta como impermeável"""
    _preparar(doc)
    arq = {"elemento": "lote", "contorno": [list(p) for p in contorno],
           "permeaveis": [[list(p) for p in a] for a in permeaveis], "nivel": nivel}
    return _novo(doc, arq, CAMADAS["lote"][0], nome, "Grama", id_)


def novo_ambiente(doc, nome, ret, nivel, piso="", id_=None) -> Solido:
    _preparar(doc)
    arq = {"elemento": "ambiente", "nome": nome, "ret": list(ret), "nivel": nivel, "piso": piso}
    return _novo(doc, arq, CAMADAS["ambiente"][0], nome, "Piso", id_)


# ------------------------------------------------------------------ regenerar

def _arq(e) -> Optional[dict]:
    a = getattr(e, "atributos", None) or {}
    v = a.get("arq")
    return v if isinstance(v, dict) else None


def _contorno_mundo(pts):
    """o `extrudar` em Z põe o x do contorno em −y e o y em x: entra (−y, x) para sair no lugar"""
    return [(-float(y), float(x)) for x, y in pts]


def regenerar(doc: Documento) -> dict:
    """refaz as malhas de todos os elementos de arquitetura pelas definições; devolve um resumo com os avisos"""
    _preparar(doc)
    nv = niveis(doc)
    avisos: List[str] = []
    for e in list(doc.entidades.values()):           # as esquadrias derivadas saem e voltam
        a = _arq(e)
        if a and a.get("elemento") == "esquadria":
            doc.remover(e.id)

    paredes_ent = [e for e in doc.entidades.values() if (_arq(e) or {}).get("elemento") == "parede"]
    # as paredes se unem por nível de base (as do térreo entre si, as do superior entre si)
    # as uniões valem entre as paredes que nascem no mesmo piso, mesmo com topos diferentes (a platibanda e a casinha
    # das caixas d'água, a mureta e a parede inteira); cada peça sai com a altura da sua parede
    por_base: Dict[float, List[Tuple[Solido, Parede]]] = {}
    esqs: List[Esquadria] = []
    for e in paredes_ent:
        a = _arq(e)
        try:
            z0, z1 = altura_da_parede(nv, a["base"], a["topo"])
        except ValueError as ex:
            avisos.append(f"{e.nome}: {ex}")
            continue
        w = Parede(e.id, tuple(a["p0"]), tuple(a["p1"]), a["tipo"], z0, z1)
        por_base.setdefault(z0, []).append((e, w))
        for i, v in enumerate(a.get("vaos") or []):
            esqs.append(Esquadria(f"{e.id}:{i}", e.id, v.get("tipo", "janela"), float(v["u"]), float(v["largura"]),
                                  float(v["altura"]), float(v.get("peitoril", 0)), v.get("codigo", "")))
    n_esq = 0
    for grupo in por_base.values():
        ws = [w for _, w in grupo]
        m = montar(ws, [q for q in esqs if any(q.parede == w.id for w in ws)])
        avisos += m.avisos
        for e, w in grupo:
            s = solido_da_parede(m.da_parede(w.id))
            e.vertices, e.faces = s.vertices, s.faces
            e.atributos["arq"]["altura"] = [w.z0, w.z1]
        for q in m_esquadrias(ws, esqs):
            n_esq += _nova_esquadria(doc, *q)
    _codigos(doc)

    n_lajes = n_amb = n_tel = n_esc = 0
    for e in list(doc.entidades.values()):
        a = _arq(e)
        if not a:
            continue
        if a.get("elemento") == "lote":
            try:
                e.vertices, e.faces = _malha_lote(a, _cota(nv, a.get("nivel", "Térreo")))
            except ValueError as ex:
                avisos.append(f"{e.nome}: {ex}")
        elif a.get("elemento") == "telhado":
            e.vertices, e.faces = _malha_telhado(a)
            n_tel += 1
        elif a.get("elemento") == "escada":
            try:
                e.vertices, e.faces, av = _malha_escada(a, nv)
            except ValueError as ex:
                avisos.append(f"{e.nome}: {ex}")
                continue
            a["avisos"] = av
            avisos += [f"{e.nome}: {x}" for x in av]
            n_esc += 1
        elif a.get("elemento") == "laje":
            try:
                topo = _cota(nv, a["nivel"])
            except ValueError as ex:
                avisos.append(f"{e.nome}: {ex}")
                continue
            esp = float(nv[a["nivel"]].get("laje", 100)) or 100.0
            s = extrudar((_contorno_mundo(a["contorno"]), [_contorno_mundo(f) for f in a.get("furos") or []]),
                         (0, 0, 1), esp, origem=(0, 0, topo - esp))
            e.vertices, e.faces = s.vertices, s.faces
            n_lajes += 1
        elif a.get("elemento") == "ambiente":
            try:
                z = _cota(nv, a["nivel"])
            except ValueError as ex:
                avisos.append(f"{e.nome}: {ex}")
                continue
            x0, x1, y0, y1 = interior(doc, a["ret"], z)
            a["interno"] = [x0, x1, y0, y1]
            a["area"] = round((x1 - x0) * (y1 - y0) / 1e6, 2)
            v, f = prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z, z + 10)
            e.vertices, e.faces = v, f
            e.nome = f"{a['nome']} — {a['area']:.2f} m²".replace(".", ",")
            n_amb += 1
    r = {"paredes": len(paredes_ent), "esquadrias": n_esq, "lajes": n_lajes, "ambientes": n_amb, "avisos": avisos}
    if n_tel:
        r["telhados"] = n_tel
    if n_esc:
        r["escadas"] = n_esc
    return r


# ------------------------------------------------------------------ lote, telhado e escada

def _malha_lote(a: dict, z: float):
    """a divisa (uma faixa por lado, por dentro do contorno, 2 cm acima do chão) e as áreas permeáveis (1 cm abaixo)"""
    pts = [tuple(map(float, p)) for p in a["contorno"]]
    giro = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    if abs(giro) < 1:
        raise ValueError("lote sem área")
    lado = 1 if giro > 0 else -1                      # anti-horário: o lado de dentro fica à esquerda
    vs, fs = [], []

    def juntar(v, f):
        base = len(vs)
        vs.extend(v)
        fs.extend([[base + i for i in face] for face in f])

    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1:
            continue
        nx, ny = -(y1 - y0) / L * lado * DIVISA, (x1 - x0) / L * lado * DIVISA
        faixa = [(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]
        juntar(*prisma(faixa if lado > 0 else faixa[::-1], z, z + 20))
    for p in a.get("permeaveis") or []:
        s = extrudar((_contorno_mundo(p), []), (0, 0, 1), 10, origem=(0, 0, z - 10))
        juntar(s.vertices, s.faces)
    return vs, fs


def _caixa_inclinada(poly, z_de, esp):
    """prisma de base convexa com o fundo na superfície z_de(x, y) e espessura `esp` medida na vertical"""
    n = len(poly)
    v = [(x, y, z_de(x, y)) for x, y in poly] + [(x, y, z_de(x, y) + esp) for x, y in poly]
    faces = [list(reversed(range(n))), [n + i for i in range(n)]]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    return v, faces


def _malha_telhado(a: dict):
    """cada água é um retângulo com o beiral numa das bordas em y (`beiral_y`) e sobe `inclinacao` por mm até a outra"""
    vs, fs = [], []
    esp = float(a.get("espessura", 50))
    for ag in a["aguas"]:
        x0, x1, y0, y1 = map(float, ag["ret"])
        by, zb, inc = float(ag["beiral_y"]), float(ag["z_beiral"]), float(ag["inclinacao"])
        v, f = _caixa_inclinada([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], lambda x, y: zb + inc * abs(y - by), esp)
        base = len(vs)
        vs += v
        fs += [[base + i for i in face] for face in f]
    return vs, fs


def _malha_escada(a: dict, nv: Dict[str, dict]):
    """escada maciça (cada degrau é um bloco do piso de baixo até a pisada): lances retos e patamares.
    O espelho sai da altura entre os níveis dividida pelo total de espelhos. Confere (proposta ARQ-08, combinada com o
    usuário em 30/10 ao falar da escada da casa): 63 ≤ 2e + p ≤ 64 cm e o patamar com pelo menos a largura do lance."""
    z0 = _cota(nv, a["base"])
    z1 = _cota(nv, a["topo"])
    lances = a["lances"]
    total = sum(int(l["espelhos"]) for l in lances)
    e = (z1 - z0) / total
    p = float(a.get("piso", 280))
    vs, fs, avisos = [], [], []

    def bloco(poly, zt):
        v, f = prisma(poly, z0, zt)
        base = len(vs)
        vs.extend(v)
        fs.extend([[base + i for i in face] for face in f])

    subidos = 0
    for l in lances:
        (px, py), (dx, dy) = l["p0"], l["dir"]
        nrm = math.hypot(dx, dy)
        dx, dy = dx / nrm, dy / nrm
        lx, ly = -dy, dx                         # a largura fica à esquerda do sentido de subida
        w = float(l["largura"])
        for k in range(1, int(l["espelhos"])):
            s0, s1 = (k - 1) * p, k * p
            pts = [(px + dx * s0, py + dy * s0), (px + dx * s1, py + dy * s1),
                   (px + dx * s1 + lx * w, py + dy * s1 + ly * w), (px + dx * s0 + lx * w, py + dy * s0 + ly * w)]
            if (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[1][1] - pts[0][1]) * (pts[2][0] - pts[0][0]) < 0:
                pts.reverse()
            bloco(pts, z0 + (subidos + k) * e)
        subidos += int(l["espelhos"])
    for pt in a.get("patamares") or []:
        x0, x1, y0, y1 = map(float, pt["ret"])
        bloco([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0 + int(pt["apos"]) * e)
        prof = min(x1 - x0, y1 - y0)
        larg = max(float(l["largura"]) for l in lances)
        if prof < larg - 1:
            avisos.append(f"patamar com {prof / 10:.0f} cm, menor que a largura do lance ({larg / 10:.0f} cm)")
    blondel = (2 * e + p) / 10
    if not (63 - 1e-6 <= blondel <= 64 + 1e-6):
        avisos.append(f"2e + p = {blondel:.1f} cm, fora de 63 a 64 (espelho {e / 10:.1f}, piso {p / 10:.1f})")
    a["espelho"] = round(e, 1)
    return vs, fs, avisos


def m_esquadrias(ws: List[Parede], esqs: List[Esquadria]):
    """(parede, esquadria) das esquadrias das paredes deste grupo"""
    por_id = {w.id: w for w in ws}
    return [(por_id[q.parede], q) for q in esqs if q.parede in por_id]


def _nova_esquadria(doc: Documento, w: Parede, q: Esquadria) -> int:
    """o vidro (janela, vidro de correr) ou a folha (porta) no vão acabado, no meio da parede"""
    if q.tipo == "passagem":
        return 0
    d = (w.p1[0] - w.p0[0], w.p1[1] - w.p0[1])
    L = math.hypot(*d)
    d = (d[0] / L, d[1] / L)
    n = (-d[1], d[0])
    if q.tipo == "porta":
        esp, mat, z0, z1 = 35.0, "Madeira", w.z0, w.z0 + q.altura
    else:
        esp, mat = 20.0, "Vidro"
        z0 = w.z0 + (0 if q.tipo == "portajanela" else q.peitoril)
        z1 = z0 + q.altura

    def pt(u, v):
        return (w.p0[0] + d[0] * u + n[0] * v, w.p0[1] + d[1] * u + n[1] * v)
    poly = [pt(q.u, -esp / 2), pt(q.u + q.largura, -esp / 2), pt(q.u + q.largura, esp / 2), pt(q.u, esp / 2)]
    if (poly[1][0] - poly[0][0]) * (poly[2][1] - poly[0][1]) - (poly[1][1] - poly[0][1]) * (poly[2][0] - poly[0][0]) < 0:
        poly.reverse()
    v, f = prisma(poly, z0, z1)
    arq = {"elemento": "esquadria", "parede": w.id, "tipo": q.tipo, "largura": q.largura, "altura": q.altura,
           "peitoril": q.peitoril, "codigo": q.codigo}
    s = Solido(nome=q.tipo, camada=CAMADAS["esquadria"][0], material=mat, vertices=v, faces=f, atributos={"arq": arq})
    s.id = f"{PREFIXO_ID}-esq-{q.id.replace(':', '-')}"
    doc.add(s)
    return 1


def _codigos(doc: Documento):
    """o mesmo tipo e a mesma medida têm o mesmo código (J1, PJ1, P1…), na ordem em que aparecem"""
    vistos: Dict[tuple, str] = {}
    cont: Dict[str, int] = {}
    for e in doc.entidades.values():
        a = _arq(e)
        if not a or a.get("elemento") != "esquadria":
            continue
        if a.get("codigo"):
            continue
        chave = (a["tipo"], round(a["largura"]), round(a["altura"]), round(a.get("peitoril", 0)))
        if chave not in vistos:
            pre = _CODIGOS.get(a["tipo"], "E")
            cont[pre] = cont.get(pre, 0) + 1
            vistos[chave] = f"{pre}{cont[pre]}"
        a["codigo"] = vistos[chave]
        e.nome = f"{a['codigo']} — {a['largura'] / 1000:.2f} × {a['altura'] / 1000:.2f}".replace(".", ",")


def interior(doc: Documento, ret, z: float) -> Tuple[float, float, float, float]:
    """ARQ-06: o retângulo do ambiente (pelos eixos ou pela face de fora) recuado até a face das paredes do lado de
    dentro, só das paredes daquele nível; lado sem parede fica como está"""
    x0, x1, y0, y1 = map(float, ret)
    nv = niveis(doc)
    paredes = []
    for e in doc.entidades.values():
        a = _arq(e)
        if not a or a.get("elemento") != "parede":
            continue
        try:
            zb, zt = altura_da_parede(nv, a["base"], a["topo"])
        except ValueError:
            continue
        if zb < z + 2000 and zt > z:          # a parede cruza a altura do ambiente (a garagem 35 cm abaixo da casa)
            paredes.append(a)

    def face(c, horizontal, sentido, lo, hi):
        """a face da parede que corre sobre a linha `c` (y = c se horizontal), do lado `sentido` (+1 para dentro
        crescente); `lo..hi` é o trecho do lado. Com mais de uma, vale a que corre mais por esse lado"""
        melhor, junto = c, 0.0
        for a in paredes:
            (ax, ay), (bx, by) = a["p0"], a["p1"]
            t = TIPOS[a["tipo"]].espessura / 2
            if horizontal and abs(ay - by) < 1:
                eixo, s0, s1 = ay, min(ax, bx), max(ax, bx)
            elif not horizontal and abs(ax - bx) < 1:
                eixo, s0, s1 = ax, min(ay, by), max(ay, by)
            else:
                continue
            corre = min(s1, hi) - max(s0, lo)
            if corre < 100:                              # não corre por esse lado
                continue
            if eixo - t - 1 <= c <= eixo + t + 1 and corre > junto:
                melhor, junto = eixo + sentido * t, corre
        return melhor
    return (face(x0, False, +1, y0, y1), face(x1, False, -1, y0, y1),
            face(y0, True, +1, x0, x1), face(y1, True, -1, x0, x1))
