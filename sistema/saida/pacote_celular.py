# -*- coding: utf-8 -*-
"""O 3D leve do celular: o modelo inteiro num binário pronto para a placa de vídeo.

O celular só consulta (decisão de 05/10): não precisa do documento editável, que no editor
do PC é a maior parte da memória (vértices e faces como objetos). Aqui o modelo sai do PC já
na forma em que a placa desenha, e o visualizador do celular (`web/celular/visor3d.js`) só
aponta os buffers para ela:

* **Blocos.** As peças, ordenadas no espaço, entram em blocos de até 65.535 vértices. Cada
  vértice são 4 inteiros de 16 bits: x, y, z quantizados na caixa do bloco e o número da peça
  dentro do bloco. A malha é indexada (vértices compartilhados pela peça) e a normal não vai
  no arquivo: a placa tira a normal plana da própria face (derivadas da posição), que é o
  sombreado de peça de aço. São 8 bytes por vértice, contra 25 no editor.
* **Formas repetidas** (parafusos, tábuas, chapas iguais): a malha vai uma vez, no espaço
  dela, e cada cópia é uma matriz e o número da peça. Mesmo critério do editor
  (`web/editor3d/nucleo/lote.js`, `_agruparCopias`): mesma malha só movida ou girada, vértice
  a vértice a 0,05 mm.
* **Arestas:** pares de índices nos mesmos vértices (borda de face, ou dobra acima de 24°,
  como `arestas.js`), sem repetir a posição.
* **Fichas** (nome, camada, perfil, peso, posição, conjunto, centro) vão num JSON ao lado,
  na mesma ordem dos números de peça.

Formato do arquivo (`.mcel`, versão `VERSAO_3D`): 4 bytes "MCEL", u32 versão, u32 tamanho
do cabeçalho, cabeçalho JSON (UTF-8, completado com espaços até múltiplo de 4) e os trechos
binários, cada um alinhado em 4 bytes; o cabeçalho diz onde cada trecho começa (a partir do
início do arquivo) e quantos elementos tem. Coordenadas em milímetros, relativas a
`origem` (o centro do modelo), para a precisão de 32 bits da placa não se perder longe da
origem do projeto.
"""
import array
import json
import math
import struct
import time
from typing import Dict, List, Optional, Tuple

VERSAO_3D = 1
MAGICA = b"MCEL"

#: Vértices por bloco (índice de 16 bits).
MAX_VERTS_BLOCO = 65535
#: Forma repetida só vira cópias acima de tantos triângulos economizados (o do editor).
MIN_TRI_COPIAS = 2000
#: Distância máxima (mm) entre um vértice da cópia e o da referência levada até ela.
TOL_COPIA = 0.05
#: Dobra entre duas faces acima deste ângulo é aresta (o do `EdgesGeometry(geom, 24)`).
LIMIAR_ARESTA_GRAUS = 24.0

_RHO_ACO = 7850.0      # kg/m³


# ------------------------------------------------------------------ malha de cada peça

def _malha(reg: dict) -> Optional[Tuple[list, list]]:
    """(vértices, faces) da entidade crua do modelo.json, ou None se não tem geometria."""
    tipo = reg.get("tipo")
    if tipo == "solido":
        vs, fs = reg.get("vertices") or [], reg.get("faces") or []
        if len(vs) < 3 or not fs:
            return None
        if (reg.get("atributos") or {}).get("tipo"):        # cota, linha de construção
            return None
        return vs, fs
    if tipo not in ("barra", "chapa"):
        return None
    from nucleo3d.modelo import Barra, Chapa
    from nucleo3d.geometria import malha
    cls = Barra if tipo == "barra" else Chapa
    campos = set(cls.__dataclass_fields__)
    limpo = {k: v for k, v in reg.items() if k in campos}
    for chave in ("inicio", "fim", "origem", "eixo_x", "eixo_y"):
        if isinstance(limpo.get(chave), list):
            limpo[chave] = tuple(limpo[chave])
    try:
        vs, fs = malha(cls(**limpo))
    except Exception:
        return None
    return [list(v) for v in vs], fs


def _triangulos(vs, f) -> List[Tuple[int, int, int]]:
    """Triângulos da face (índices do sólido). Até 4 lados, leque (como o editor); acima,
    leque se a face é convexa, senão ear clipping no plano dela."""
    n = len(f)
    if n == 3:
        return [(f[0], f[1], f[2])]
    if n == 4:
        return [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
    # normal de Newell e o eixo dominante descartado: o polígono no plano mais aberto
    nx = ny = nz = 0.0
    for k in range(n):
        a, b = vs[f[k]], vs[f[(k + 1) % n]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    ax, ay, az = abs(nx), abs(ny), abs(nz)
    if az >= ax and az >= ay:
        i, j = 0, 1
    elif ay >= ax:
        i, j = 2, 0
    else:
        i, j = 1, 2
    pts = [(vs[k][i], vs[k][j]) for k in f]
    sinal = 0
    convexa = True
    for k in range(n):
        a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) < 1e-9:
            continue
        s = 1 if cr > 0 else -1
        if sinal == 0:
            sinal = s
        elif s != sinal:
            convexa = False
            break
    if convexa:
        return [(f[0], f[k], f[k + 1]) for k in range(1, n - 1)]
    from nucleo3d.geometria import triangular
    try:
        return [(f[a], f[b], f[c]) for a, b, c in triangular(pts)]
    except Exception:
        return [(f[0], f[k], f[k + 1]) for k in range(1, n - 1)]


def _arestas(vs, fs, cos_lim: float) -> List[Tuple[int, int]]:
    """Arestas pelo critério de `arestas.js`: borda de uma face só, ou dobra acima do limiar.
    Vértices na mesma posição (a 1 µm) contam como um só."""
    canon = list(range(len(vs)))
    por_pos: Dict[tuple, int] = {}
    for i, p in enumerate(vs):
        k = (round(p[0] * 1e3), round(p[1] * 1e3), round(p[2] * 1e3))
        j = por_pos.setdefault(k, i)
        if j != i:
            canon[i] = j
    normais = {}
    pares: Dict[tuple, list] = {}
    for fi, f in enumerate(fs):
        n = len(f)
        if n < 3:
            continue
        nx = ny = nz = 0.0
        for k in range(n):
            a, b = vs[f[k]], vs[f[(k + 1) % n]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-12:
            continue
        normais[fi] = (nx / ln, ny / ln, nz / ln)
        for k in range(n):
            a, b = canon[f[k]], canon[f[(k + 1) % n]]
            if a == b:
                continue
            if a > b:
                a, b = b, a
            r = pares.get((a, b))
            if r is None:
                pares[(a, b)] = [fi, -1, 1]
            else:
                if r[1] < 0:
                    r[1] = fi
                r[2] += 1
    saida = []
    for (a, b), (f1, f2, vezes) in pares.items():
        if vezes == 2:
            n1, n2 = normais[f1], normais[f2]
            if n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2] > cos_lim:
                continue
        saida.append((a, b))
    return saida


# ------------------------------------------------------------------ cópias

def _ancoras(vs):
    p0 = vs[0]
    i1, d1 = -1, 0.0
    for i in range(1, len(vs)):
        v = vs[i]
        d = (v[0] - p0[0]) ** 2 + (v[1] - p0[1]) ** 2 + (v[2] - p0[2]) ** 2
        if d > d1:
            d1, i1 = d, i
    if i1 < 0 or d1 < 1e-6:
        return None
    ux, uy, uz = vs[i1][0] - p0[0], vs[i1][1] - p0[1], vs[i1][2] - p0[2]
    i2, c2 = -1, 0.0
    for i in range(1, len(vs)):
        wx, wy, wz = vs[i][0] - p0[0], vs[i][1] - p0[1], vs[i][2] - p0[2]
        c = (uy * wz - uz * wy) ** 2 + (uz * wx - ux * wz) ** 2 + (ux * wy - uy * wx) ** 2
        if c > c2:
            c2, i2 = c, i
    if i2 < 0 or c2 < 1e-6 * d1:
        return None
    return i1, i2


def _quadro(vs, ancoras):
    """Triedro (x, y, z) e origem da peça pelos três vértices fixos."""
    p0, a, b = vs[0], vs[ancoras[0]], vs[ancoras[1]]
    x = (a[0] - p0[0], a[1] - p0[1], a[2] - p0[2])
    w = (b[0] - p0[0], b[1] - p0[1], b[2] - p0[2])
    lx = math.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2)
    if lx < 1e-6:
        return None
    x = (x[0] / lx, x[1] / lx, x[2] / lx)
    z = (x[1] * w[2] - x[2] * w[1], x[2] * w[0] - x[0] * w[2], x[0] * w[1] - x[1] * w[0])
    lz = math.sqrt(z[0] ** 2 + z[1] ** 2 + z[2] ** 2)
    if lz < 1e-6:
        return None
    z = (z[0] / lz, z[1] / lz, z[2] / lz)
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    return x, y, z, (p0[0], p0[1], p0[2])


def _local(vs, q):
    """Vértices no triedro da peça."""
    x, y, z, o = q
    out = []
    for v in vs:
        dx, dy, dz = v[0] - o[0], v[1] - o[1], v[2] - o[2]
        out.append((dx * x[0] + dy * x[1] + dz * x[2],
                    dx * y[0] + dy * y[1] + dz * y[2],
                    dx * z[0] + dy * z[1] + dz * z[2]))
    return out


def _bate(local_ref, vs, q) -> bool:
    x, y, z, o = q
    tol = TOL_COPIA * TOL_COPIA
    for (a, b, c), v in zip(local_ref, vs):
        px = o[0] + a * x[0] + b * y[0] + c * z[0] - v[0]
        py = o[1] + a * x[1] + b * y[1] + c * z[1] - v[1]
        pz = o[2] + a * x[2] + b * y[2] + c * z[2] - v[2]
        if px * px + py * py + pz * pz > tol:
            return False
    return True


def _agrupar_copias(pecas: List[dict]) -> List[dict]:
    """Grupos de peças que são a mesma malha só movida ou girada:
    [{ref, local, itens: [(peca, quadro)]}]."""
    por_chave: Dict[tuple, list] = {}
    for p in pecas:
        vs, fs = p["vs"], p["fs"]
        chave = (len(vs), len(fs), hash(tuple(tuple(f) for f in fs)))
        por_chave.setdefault(chave, []).append(p)
    grupos = []
    for lista in por_chave.values():
        if len(lista) < 2:
            continue
        tri = sum(max(len(f) - 2, 0) for f in lista[0]["fs"])
        resto = lista
        while len(resto) >= 2 and tri * (len(resto) - 1) >= MIN_TRI_COPIAS:
            ref = resto[0]
            anc = _ancoras(ref["vs"])
            q_ref = anc and _quadro(ref["vs"], anc)
            if not q_ref:
                break
            local_ref = _local(ref["vs"], q_ref)
            iguais, outros = [(ref, q_ref)], []
            for p in resto[1:]:
                q = _quadro(p["vs"], anc)
                if q and _bate(local_ref, p["vs"], q):
                    iguais.append((p, q))
                else:
                    outros.append(p)
            if len(iguais) >= 2 and tri * (len(iguais) - 1) >= MIN_TRI_COPIAS:
                grupos.append({"ref": ref, "local": local_ref, "itens": iguais})
            resto = outros
    return grupos


# ------------------------------------------------------------------ montagem do binário

class _Saida:
    """Trechos binários alinhados em 4 bytes, com o deslocamento de cada um."""

    def __init__(self):
        self.partes: List[bytes] = []
        self.tamanho = 0

    def por(self, dados: bytes) -> int:
        ofs = self.tamanho
        self.partes.append(dados)
        self.tamanho += len(dados)
        resto = (-len(dados)) % 4
        if resto:
            self.partes.append(b"\0" * resto)
            self.tamanho += resto
        return ofs


def _caixa(pontos) -> Tuple[List[float], List[float]]:
    mn = [math.inf] * 3
    mx = [-math.inf] * 3
    for p in pontos:
        for i in range(3):
            if p[i] < mn[i]:
                mn[i] = p[i]
            if p[i] > mx[i]:
                mx[i] = p[i]
    return mn, mx


def _quantizar(pontos, mn, esc, w_de, saida: array.array):
    """x, y, z em 16 bits na caixa (mn, esc) e o quarto inteiro `w`."""
    ix, iy, iz = 1.0 / esc[0], 1.0 / esc[1], 1.0 / esc[2]
    for p, w in zip(pontos, w_de):
        saida.append(min(65535, max(0, int((p[0] - mn[0]) * ix + 0.5))))
        saida.append(min(65535, max(0, int((p[1] - mn[1]) * iy + 0.5))))
        saida.append(min(65535, max(0, int((p[2] - mn[2]) * iz + 0.5))))
        saida.append(w)


def _escala(mn, mx) -> List[float]:
    return [max(mx[i] - mn[i], 1e-3) / 65535.0 for i in range(3)]


def _texto_perfil(reg: dict) -> str:
    if reg.get("tipo") == "barra":
        return str(reg.get("perfil") or "")
    if reg.get("tipo") == "chapa":
        return f"CH {reg.get('espessura', '')}"
    m = (reg.get("atributos") or {}).get("marcas") or {}
    return str(m.get("perfil") or "")


def _ficha(reg: dict, camadas_idx: Dict[str, int], centro, volume_mm3: float) -> dict:
    marcas = (reg.get("atributos") or {}).get("marcas") or {}
    material = str(reg.get("material") or "")
    f = {"id": reg.get("id"), "n": reg.get("nome") or "", "c": camadas_idx.get(reg.get("camada") or "", 0),
         "m": material, "p": _texto_perfil(reg),
         "x": [round(centro[0]), round(centro[1]), round(centro[2])]}
    if volume_mm3 > 0 and ("aço" in material.lower() or "aco" in material.lower() or reg.get("tipo") in ("barra", "chapa")):
        f["kg"] = round(volume_mm3 * _RHO_ACO / 1e9, 2)
    for k_ori, k in (("posicao", "pos"), ("conjunto", "cj"), ("marca", "mc")):
        if marcas.get(k_ori):
            f[k] = str(marcas[k_ori])
    return f


def _volume(vs, tris) -> float:
    v = 0.0
    for a, b, c in tris:
        p, q, r = vs[a], vs[b], vs[c]
        v += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0])
              + p[2] * (q[0] * r[1] - q[1] * r[0]))
    return abs(v) / 6.0


def gerar_3d(modelo: dict, progresso=None) -> Tuple[bytes, dict, dict]:
    """(binário .mcel, fichas, números da geração) do modelo cru (o dict do modelo.json)."""
    t0 = time.time()
    cos_lim = math.cos(math.radians(LIMIAR_ARESTA_GRAUS))
    camadas = modelo.get("camadas") or {}
    materiais = modelo.get("materiais") or {}
    nomes_camadas = list(camadas.keys())
    pecas: List[dict] = []
    for reg in modelo.get("entidades") or []:
        m = _malha(reg)
        if not m:
            continue
        cam = reg.get("camada") or ""
        if cam not in camadas and cam not in nomes_camadas:
            nomes_camadas.append(cam)
        pecas.append({"reg": reg, "vs": m[0], "fs": m[1]})
    camadas_idx = {n: i for i, n in enumerate(nomes_camadas)}
    t_malha = time.time()
    if not pecas:
        raise ValueError("o modelo não tem peças com geometria")

    # origem = centro da caixa do modelo
    mn_g = [math.inf] * 3
    mx_g = [-math.inf] * 3
    for p in pecas:
        a, b = _caixa(p["vs"])
        p["centro"] = [(a[i] + b[i]) / 2 for i in range(3)]
        for i in range(3):
            mn_g[i] = min(mn_g[i], a[i])
            mx_g[i] = max(mx_g[i], b[i])
    origem = [(mn_g[i] + mx_g[i]) / 2 for i in range(3)]
    for p in pecas:
        o0, o1, o2 = origem
        p["vs"] = [(v[0] - o0, v[1] - o1, v[2] - o2) for v in p["vs"]]
        p["centro"] = [p["centro"][i] - origem[i] for i in range(3)]

    grupos = _agrupar_copias(pecas)
    em_copia = set()
    for g in grupos:
        for p, _q in g["itens"]:
            em_copia.add(id(p))
    t_copias = time.time()

    # números de peça: as do bloco primeiro (contíguas por bloco), depois as das cópias
    soltas = [p for p in pecas if id(p) not in em_copia]
    soltas.sort(key=lambda p: (p["centro"][0], p["centro"][1]))
    saida = _Saida()
    blocos_cab = []
    fichas: List[dict] = []
    n_tri = n_ar = n_vert = 0
    k = 0
    while k < len(soltas):
        # monta o bloco até o teto de vértices (uma peça grande demais fica sozinha)
        lote = [soltas[k]]
        nv = len(soltas[k]["vs"])
        k += 1
        while k < len(soltas) and nv + len(soltas[k]["vs"]) <= MAX_VERTS_BLOCO:
            lote.append(soltas[k])
            nv += len(soltas[k]["vs"])
            k += 1
        id0 = len(fichas)
        mn = [math.inf] * 3
        mx = [-math.inf] * 3
        for p in lote:
            a, b = _caixa(p["vs"])
            for i in range(3):
                mn[i] = min(mn[i], a[i])
                mx[i] = max(mx[i], b[i])
        esc = _escala(mn, mx)
        vq = array.array("H")
        tipo_idx = "H" if nv <= 65536 else "I"
        idx = array.array(tipo_idx)
        ar = array.array(tipo_idx)
        base = 0
        for li, p in enumerate(lote):
            vs = p["vs"]
            _quantizar(vs, mn, esc, [li] * len(vs) if li < 65536 else [65535] * len(vs), vq)
            tris = []
            for f in p["fs"]:
                if len(f) >= 3:
                    tris.extend(_triangulos(vs, f))
            for a, b, c in tris:
                idx.append(a + base)
                idx.append(b + base)
                idx.append(c + base)
            for a, b in _arestas(vs, p["fs"], cos_lim):
                ar.append(a + base)
                ar.append(b + base)
            fichas.append(_ficha(p["reg"], camadas_idx, p["centro"], _volume(vs, tris)))
            base += len(vs)
            n_tri += len(tris)
        n_vert += nv
        n_ar += len(ar) // 2
        blocos_cab.append({
            "id0": id0, "n": len(lote), "min": mn, "esc": esc,
            "vertices": {"ofs": saida.por(vq.tobytes()), "n": nv},
            "indices": {"ofs": saida.por(idx.tobytes()), "n": len(idx), "tipo": "u16" if tipo_idx == "H" else "u32"},
            "arestas": {"ofs": saida.por(ar.tobytes()), "n": len(ar), "tipo": "u16" if tipo_idx == "H" else "u32"},
        })
        if progresso:
            progresso(k, len(soltas))

    formas_cab = []
    n_copias = 0
    for g in grupos:
        ref = g["ref"]
        local = g["local"]
        mn, mx = _caixa(local)
        esc = _escala(mn, mx)
        vq = array.array("H")
        _quantizar(local, mn, esc, [0] * len(local), vq)
        nv = len(local)
        tipo_idx = "H" if nv <= 65536 else "I"
        idx = array.array(tipo_idx)
        tris = []
        for f in ref["fs"]:
            if len(f) >= 3:
                tris.extend(_triangulos(local, f))
        for t in tris:
            idx.extend(t)
        ar = array.array(tipo_idx)
        for a, b in _arestas(local, ref["fs"], cos_lim):
            ar.append(a)
            ar.append(b)
        vol = _volume(local, tris)
        inst = array.array("f")
        for p, q in g["itens"]:
            x, y, z, o = q
            # matriz da cópia já com a volta da quantização: mundo = o + R·(mn + esc·q)
            tx = o[0] + x[0] * mn[0] + y[0] * mn[1] + z[0] * mn[2]
            ty = o[1] + x[1] * mn[0] + y[1] * mn[1] + z[1] * mn[2]
            tz = o[2] + x[2] * mn[0] + y[2] * mn[1] + z[2] * mn[2]
            inst.extend((x[0] * esc[0], y[0] * esc[1], z[0] * esc[2], tx,
                         x[1] * esc[0], y[1] * esc[1], z[1] * esc[2], ty,
                         x[2] * esc[0], y[2] * esc[1], z[2] * esc[2], tz,
                         float(len(fichas))))
            fichas.append(_ficha(p["reg"], camadas_idx, p["centro"], vol))
        n_copias += len(g["itens"])
        n_tri += len(tris) * len(g["itens"])
        formas_cab.append({
            "n": len(g["itens"]),
            "vertices": {"ofs": saida.por(vq.tobytes()), "n": nv},
            "indices": {"ofs": saida.por(idx.tobytes()), "n": len(idx), "tipo": "u16" if tipo_idx == "H" else "u32"},
            "arestas": {"ofs": saida.por(ar.tobytes()), "n": len(ar), "tipo": "u16" if tipo_idx == "H" else "u32"},
            "copias": {"ofs": saida.por(inst.tobytes()), "n": len(g["itens"])},
        })
    t_fim = time.time()

    # caixa de cada camada: o celular enquadra só o que está ligado
    caixas: Dict[int, list] = {}
    for p in pecas:
        a, b = _caixa(p["vs"])
        ci = camadas_idx.get(p["reg"].get("camada") or "", 0)
        cx = caixas.get(ci)
        if cx is None:
            caixas[ci] = [list(a), list(b)]
        else:
            for i in range(3):
                cx[0][i] = min(cx[0][i], a[i])
                cx[1][i] = max(cx[1][i], b[i])
    cab_camadas = []
    for ci, nome in enumerate(nomes_camadas):
        c = camadas.get(nome) or {}
        cam = {"nome": nome, "cor": c.get("cor") or "#8a94a6", "visivel": c.get("visivel", True) is not False,
               "pecas": sum(1 for f in fichas if f["c"] == ci)}
        if ci in caixas:
            cam["caixa"] = [[round(v, 1) for v in caixas[ci][0]], [round(v, 1) for v in caixas[ci][1]]]
        cab_camadas.append(cam)
    cab_materiais = {n: (m.get("cor") or "") for n, m in materiais.items() if isinstance(m, dict)}
    numeros = {
        "pecas": len(fichas), "blocos": len(blocos_cab), "formas": len(formas_cab), "copias": n_copias,
        "vertices_blocos": n_vert, "triangulos": n_tri, "arestas": n_ar,
        "s_malhas": round(t_malha - t0, 1), "s_copias": round(t_copias - t_malha, 1),
        "s_blocos": round(t_fim - t_copias, 1),
    }
    cab = {
        "versao": VERSAO_3D, "unidade": "mm", "origem": origem,
        "caixa": [[mn_g[i] - origem[i] for i in range(3)], [mx_g[i] - origem[i] for i in range(3)]],
        "camadas": cab_camadas, "materiais": cab_materiais,
        "blocos": blocos_cab, "formas": formas_cab, "numeros": numeros,
    }
    texto = json.dumps(cab, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    texto += b" " * ((-len(texto)) % 4)
    inicio = 12 + len(texto)
    # os deslocamentos foram contados a partir do primeiro trecho: passam a contar do início
    for item in blocos_cab + formas_cab:
        for chave in ("vertices", "indices", "arestas", "copias"):
            if chave in item:
                item[chave]["ofs"] += inicio
    texto = json.dumps(cab, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    texto += b" " * ((-len(texto)) % 4)
    # o cabeçalho pode ter crescido com os números maiores: refaz até estabilizar
    while 12 + len(texto) != inicio:
        delta = 12 + len(texto) - inicio
        inicio += delta
        for item in blocos_cab + formas_cab:
            for chave in ("vertices", "indices", "arestas", "copias"):
                if chave in item:
                    item[chave]["ofs"] += delta
        texto = json.dumps(cab, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        texto += b" " * ((-len(texto)) % 4)
    binario = MAGICA + struct.pack("<II", VERSAO_3D, len(texto)) + texto + b"".join(saida.partes)
    return binario, {"versao": VERSAO_3D, "camadas": cab_camadas, "pecas": fichas}, numeros


def ler_cabecalho(binario: bytes) -> dict:
    """Cabeçalho de um .mcel (para conferência e testes)."""
    if binario[:4] != MAGICA:
        raise ValueError("não é um arquivo do 3D leve")
    versao, n = struct.unpack_from("<II", binario, 4)
    cab = json.loads(binario[12:12 + n].decode("utf-8"))
    cab["_versao_arquivo"] = versao
    return cab


def ler_cabecalho_arquivo(caminho: str) -> dict:
    with open(caminho, "rb") as f:
        inicio = f.read(12)
        n = struct.unpack_from("<I", inicio, 8)[0] if len(inicio) == 12 else 0
        return ler_cabecalho(inicio + f.read(n))


# ====================================================================== o pacote do projeto
# Um formato só para os dois modos (decisão de 05/10): na rede o PC entrega estes arquivos
# na hora; na obra o celular usa a cópia que guardou da última vez. O manifesto diz a versão
# do formato, de quando é o pacote, a revisão do projeto e o resumo (SHA-1) de cada arquivo:
# o celular compara com o que tem e baixa só o que mudou.
#
# Entra só o que está na lista abaixo, nunca uma pasta inteira: a parte comercial (pasta
# comercial/, orçamento, proposta, contrato) não vai para o celular.

FORMATO_PACOTE = 1

#: Resumos prontos do detalhamento: (arquivo, título na tela).
RESUMOS = (("resumo-da-obra.pdf", "Resumo da obra"), ("resumo-de-materiais.pdf", "Resumo de materiais"),
           ("Lista-de-materiais.pdf", "Lista de materiais (PDF)"))

#: Campos da posição que o celular mostra (o resto fica no PC).
_CAMPOS_POSICAO = ("marca", "nome", "categoria", "classe", "perfil", "material", "quantidade", "comprimento",
                   "largura", "espessura", "furos", "parafusos", "peso", "peso_total", "conjuntos")


def _sha1(caminho: str) -> str:
    import hashlib
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _quando(caminho: str) -> Optional[str]:
    import datetime
    import os
    if not os.path.exists(caminho):
        return None
    return datetime.datetime.fromtimestamp(os.path.getmtime(caminho)).isoformat(timespec="seconds")


def _ler(caminho: str):
    import os
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def quantitativos(lista: dict) -> dict:
    """O pedaço da lista de materiais que vai para o celular."""
    def so(d, campos):
        return {k: d[k] for k in campos if k in d and d[k] not in (None, "", [])}
    perfis = []
    for p in lista.get("perfis") or []:
        item = so(p, ("perfil", "material", "categoria", "posicoes", "pecas", "comprimento_m", "peso"))
        b = p.get("barras") or {}
        if b:
            item["barras"] = so(b, ("comprimento", "quantidade", "emendas", "aproveitamento", "sobra_m", "plano"))
        perfis.append(item)
    return {
        "gerado": lista.get("gerado"),
        "totais": lista.get("totais") or {},
        "posicoes": [so(p, _CAMPOS_POSICAO) for p in lista.get("posicoes") or []],
        "perfis": perfis,
        "chapas": lista.get("chapas") or [],
        "telhas": [so(t, ("perfil", "posicoes", "pecas", "comprimento_m", "area_m2", "peso")) for t in lista.get("telhas") or []],
        "conjuntos": [so(c, ("marca", "nome", "categoria", "instancias", "pecas_unidade", "composicao_texto",
                             "peso_unitario", "peso_total")) for c in lista.get("conjuntos") or []],
        "acessorios": lista.get("acessorios") or [],
    }


def _pranchas(pasta_projeto: str, destino: str) -> List[dict]:
    """O PDF das pranchas (refeito do desenho das pranchas do CAD quando ele é mais novo) e uma
    miniatura por folha."""
    import os
    desenho = os.path.join(pasta_projeto, "desenhos-2d", "pranchas.desenho.json")
    if not os.path.exists(desenho):
        return []
    d = _ler(desenho)
    folhas = [f for f in ((d.get("metadados") or {}).get("pranchas") or []) if f.get("formato")]
    if not folhas:
        return []
    pdf = os.path.join(destino, "pranchas.pdf")
    if not os.path.exists(pdf) or os.path.getmtime(pdf) < os.path.getmtime(desenho):
        from nucleo2d.desenho import Desenho
        from nucleo2d.pranchas import pdf_dos_desenhos
        pdf_dos_desenhos([Desenho.de_dict(d)], pdf)
    import pymupdf
    os.makedirs(os.path.join(destino, "folhas"), exist_ok=True)
    saida = []
    with pymupdf.open(pdf) as doc:
        for i, f in enumerate(folhas[:doc.page_count]):
            pg = doc[i]
            zoom = 480.0 / max(pg.rect.width, 1.0)
            nome = "folhas/%02d.png" % (i + 1)
            pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(os.path.join(destino, nome))
            saida.append({"numero": f.get("numero") or i + 1, "titulo": f.get("titulo") or f.get("nome") or "",
                          "formato": f.get("formato"), "pagina": i + 1, "miniatura": nome})
    return saida


def gerar_pacote(pasta_projeto: str, destino: str, slug: str = "", progresso=None) -> dict:
    """Gera (ou refaz o que ficou velho) o pacote do projeto em `destino` e devolve o manifesto."""
    import datetime
    import os
    import shutil
    from versao import VERSAO
    os.makedirs(destino, exist_ok=True)
    projeto = _ler(os.path.join(pasta_projeto, "projeto.json")) or {}
    dados = projeto.get("dados_resumo") or {}
    numeros: Dict[str, object] = {}

    # 3D: só refeito quando o modelo é mais novo que o pacote
    modelo = os.path.join(pasta_projeto, "modelo.json")
    mcel = os.path.join(destino, "modelo3d.mcel")
    if os.path.exists(modelo):
        if not os.path.exists(mcel) or os.path.getmtime(mcel) < os.path.getmtime(modelo):
            with open(modelo, encoding="utf-8") as f:
                m = json.load(f)
            binario, fichas, _num = gerar_3d(m, progresso)
            del m
            with open(os.path.join(destino, "pecas.json"), "w", encoding="utf-8") as f:
                json.dump(fichas, f, ensure_ascii=False, separators=(",", ":"))
            with open(mcel + ".tmp", "wb") as f:
                f.write(binario)
            os.replace(mcel + ".tmp", mcel)
        numeros["pecas"] = ler_cabecalho_arquivo(mcel).get("numeros", {}).get("pecas")

    # quantitativos
    det = os.path.join(pasta_projeto, "detalhamento")
    lista = _ler(os.path.join(det, "lista-de-materiais.json"))
    if lista:
        q = quantitativos(lista)
        with open(os.path.join(destino, "quantitativos.json"), "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, separators=(",", ":"))
        t = q["totais"]
        numeros.update({"peso_kg": t.get("peso"), "posicoes": t.get("posicoes"), "conjuntos": t.get("conjuntos")})

    # resumos
    resumos = []
    rn = _ler(os.path.join(det, "resumo-numeros.json"))
    if rn:
        with open(os.path.join(destino, "resumo-numeros.json"), "w", encoding="utf-8") as f:
            json.dump(rn, f, ensure_ascii=False, separators=(",", ":"))
    for arq, titulo in RESUMOS:
        if os.path.exists(os.path.join(det, arq)):
            shutil.copy2(os.path.join(det, arq), os.path.join(destino, arq))
            resumos.append({"titulo": titulo, "arquivo": arq})

    # pranchas
    pranchas = _pranchas(pasta_projeto, destino)
    numeros["pranchas"] = len(pranchas)

    arquivos = []
    for raiz, _pastas, nomes in os.walk(destino):
        for n in sorted(nomes):
            if n == "manifesto.json" or n.endswith(".tmp"):
                continue
            c = os.path.join(raiz, n)
            rel = os.path.relpath(c, destino).replace("\\", "/")
            arquivos.append({"nome": rel, "bytes": os.path.getsize(c), "sha1": _sha1(c)})
    manifesto = {
        "formato": FORMATO_PACOTE, "versao_3d": VERSAO_3D, "programa": VERSAO,
        "gerado": datetime.datetime.now().isoformat(timespec="seconds"),
        "projeto": {"slug": slug or os.path.basename(os.path.normpath(pasta_projeto)), "nome": projeto.get("nome") or "",
                    "cliente": projeto.get("cliente") or "", "local": projeto.get("local") or "",
                    "responsavel": projeto.get("responsavel") or "", "tipo": projeto.get("tipo") or "",
                    "origem": projeto.get("origem_ifc") or "", "alterado": projeto.get("alterado"),
                    "revisao": dados.get("revisao") or "", "descricao": dados.get("descricao") or ""},
        "fontes": {"modelo": _quando(modelo), "lista": _quando(os.path.join(det, "lista-de-materiais.json")),
                   "pranchas": _quando(os.path.join(pasta_projeto, "desenhos-2d", "pranchas.desenho.json"))},
        "numeros": numeros, "resumos": resumos, "pranchas": pranchas, "arquivos": arquivos,
        "bytes": sum(a["bytes"] for a in arquivos),
    }
    with open(os.path.join(destino, "manifesto.json"), "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1)
    return manifesto
