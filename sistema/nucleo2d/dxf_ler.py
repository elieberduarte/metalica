# -*- coding: utf-8 -*-
"""Leitura de DXF (R12 a R2018, texto) para o desenho 2D do CAD.

Serve para trazer um detalhe já desenhado noutro programa (o DWG de exemplo da
fábrica, convertido para DXF) para dentro de um desenho do projeto. Lê:

* LINE, CIRCLE, ARC, LWPOLYLINE (com bulge, virado em arcos aproximados), POLYLINE/VERTEX,
  SOLID, ELLIPSE (aproximada), LEADER, POINT (ignorado);
* TEXT, MTEXT (códigos de formatação removidos) e ATTRIB dos blocos;
* INSERT, com blocos aninhados, escala, rotação e ponto-base;
* DIMENSION pelo bloco anônimo que a acompanha (linhas e textos, como o CAD de origem
  desenhou) — não vira cota editável, porque o DXF não traz os pontos de definição de
  forma confiável em todos os exportadores;
* HATCH fica de fora (só o contorno quando é polilinha).

Unidades: `$INSUNITS` do cabeçalho (4 = mm, 5 = cm, 6 = m) dá o fator para milímetro;
sem ele, o chamador informa. O texto do DXF tem altura em unidades de modelo; no CAD a
altura é de papel, então ela é dividida pela escala do desenho de destino.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Camada2D

__all__ = ["ler_dxf", "para_desenho", "FATOR_UNIDADE"]

Ponto2 = Tuple[float, float]

TIPOS = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "VERTEX", "SEQEND", "TEXT", "MTEXT",
         "INSERT", "ATTRIB", "DIMENSION", "HATCH", "LEADER", "POINT", "ELLIPSE", "SOLID", "SPLINE",
         "WIPEOUT", "MULTILEADER", "VIEWPORT", "ATTDEF", "3DFACE", "TRACE", "IMAGE", "XLINE", "RAY"}

#: $INSUNITS → mm por unidade.
FATOR_UNIDADE = {0: None, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 0.0254, 9: 0.0254e3 / 1000.0}

#: Cores ACI mais usadas → hex (7 é preto/branco conforme o fundo: fica o tom do CAD).
CORES_ACI = {1: "#c0392b", 2: "#b7950b", 3: "#1c7a43", 4: "#17a2b8", 5: "#1f5fbf", 6: "#8e44ad",
             7: "#16202e", 8: "#7d8a9e", 9: "#aab7cc", 30: "#e08a1e", 40: "#c99526", 250: "#333b47",
             251: "#4b5563", 252: "#6b7280", 253: "#8a94a6", 254: "#aab7cc"}


def _pares(texto: str):
    linhas = texto.split("\n")
    out = []
    for i in range(0, len(linhas) - 1, 2):
        c = linhas[i].strip()
        if c.lstrip("-").isdigit():
            out.append((int(c), linhas[i + 1].rstrip("\r")))
    return out


def ler_dxf(texto: str) -> dict:
    """Estrutura crua: {cabecalho, camadas, blocos, entidades}."""
    pares = _pares(texto)
    secao = None
    cabecalho: Dict[str, object] = {}
    camadas: Dict[str, dict] = {}
    blocos: Dict[str, dict] = {}
    modelo: List[dict] = []
    bloco = None
    ent = None
    alvo = None
    var = None
    tabela = None

    def fechar():
        nonlocal ent
        if ent is not None and alvo is not None and ent.get("tipo") not in ("BLOCKDEF", "LAYER"):
            alvo.append(ent)
        if ent is not None and ent.get("tipo") == "LAYER" and ent.get("nome") is not None:
            camadas[ent["nome"]] = ent
        ent = None

    for cod, val in pares:
        if secao == "HEADER":
            if cod == 9:
                var = val
            elif var == "$INSUNITS" and cod == 70:
                cabecalho["insunits"] = int(float(val))
            elif cod == 0 and val == "ENDSEC":
                secao = None
            continue
        if cod == 0:
            fechar()
            if val == "SECTION":
                secao = "?"
                continue
            if val == "ENDSEC":
                secao = None
                bloco = None
                alvo = None
                continue
            if secao == "TABLES":
                if val == "TABLE":
                    tabela = None
                elif val == "LAYER" and tabela == "LAYER":
                    ent = {"tipo": "LAYER", "nome": None, "cor": 7, "tipo_linha": "CONTINUOUS", "_g": collections.defaultdict(list)}
                    alvo = []
                elif val in ("ENDTAB",):
                    tabela = None
                continue
            if secao == "BLOCKS":
                if val == "BLOCK":
                    bloco = {"nome": None, "base": [0.0, 0.0], "ents": []}
                    ent = {"tipo": "BLOCKDEF", "_b": bloco, "_g": collections.defaultdict(list)}
                    alvo = None
                    continue
                if val == "ENDBLK":
                    if bloco and bloco["nome"] is not None:
                        blocos[bloco["nome"]] = bloco
                    bloco = None
                    alvo = None
                    continue
                if bloco is not None and val in TIPOS:
                    ent = {"tipo": val, "_g": collections.defaultdict(list)}
                    alvo = bloco["ents"]
                continue
            if secao == "ENTITIES" and val in TIPOS:
                ent = {"tipo": val, "_g": collections.defaultdict(list)}
                alvo = modelo
            continue
        if cod == 2 and secao == "?":
            secao = val
            continue
        if secao == "TABLES" and cod == 2 and ent is None:
            tabela = val
            continue
        if ent is None:
            continue
        if ent["tipo"] == "BLOCKDEF":
            if cod == 2:
                ent["_b"]["nome"] = val
            elif cod == 10:
                ent["_b"]["base"][0] = float(val)
            elif cod == 20:
                ent["_b"]["base"][1] = float(val)
            continue
        if ent["tipo"] == "LAYER":
            if cod == 2:
                ent["nome"] = val
            elif cod == 62:
                try:
                    ent["cor"] = abs(int(val))
                except ValueError:
                    pass
            elif cod == 6:
                ent["tipo_linha"] = val
            continue
        ent["_g"][cod].append(val)
    fechar()

    for b in blocos.values():
        b["ents"] = _preparar(b["ents"])
    return {"cabecalho": cabecalho, "camadas": camadas, "blocos": blocos, "entidades": _preparar(modelo)}


def _num(e, c, d=0.0):
    v = e["_g"].get(c)
    try:
        return float(v[0]) if v else d
    except ValueError:
        return d


def _preparar(lista):
    out = []
    pend = None
    for e in lista:
        g = e["_g"]
        e["camada"] = g.get(8, ["0"])[0]
        e["papel"] = int(_num(e, 67, 0)) == 1
        t = e["tipo"]
        if t == "LINE":
            e["a"] = (_num(e, 10), _num(e, 20))
            e["b"] = (_num(e, 11), _num(e, 21))
        elif t in ("ARC", "CIRCLE"):
            e["c"] = (_num(e, 10), _num(e, 20))
            e["r"] = _num(e, 40)
            e["a0"] = _num(e, 50)
            e["a1"] = _num(e, 51, 360)
        elif t == "LWPOLYLINE":
            xs, ys = g.get(10, []), g.get(20, [])
            e["pts"] = [(float(x), float(y)) for x, y in zip(xs, ys)]
            # bulge só existe quando não é zero em alguns exportadores: alinha por índice
            bul = g.get(42, [])
            e["bulge"] = [float(b) for b in bul] if len(bul) == len(e["pts"]) else ([float(b) for b in bul] + [0.0] * len(e["pts"]))[:len(e["pts"])]
            e["fechada"] = bool(int(_num(e, 70, 0)) & 1)
        elif t == "POLYLINE":
            e["pts"] = []
            e["bulge"] = []
            e["fechada"] = bool(int(_num(e, 70, 0)) & 1)
            pend = e
        elif t == "VERTEX":
            if pend is not None:
                pend["pts"].append((_num(e, 10), _num(e, 20)))
                pend["bulge"].append(_num(e, 42, 0.0))
            continue
        elif t == "SEQEND":
            pend = None
            continue
        elif t in ("TEXT", "ATTRIB", "ATTDEF"):
            e["p"] = (_num(e, 10), _num(e, 20))
            e["h"] = _num(e, 40)
            e["rot"] = _num(e, 50)
            e["texto"] = g.get(1, [""])[0]
            e["ha"] = int(_num(e, 72, 0))
            e["va"] = int(_num(e, 73, 0))
            e["p2"] = (_num(e, 11), _num(e, 21))
            if t == "ATTRIB" and pend is not None and pend["tipo"] == "INSERT":
                pend.setdefault("attribs", []).append(e)
                continue
            if t == "ATTDEF":
                continue
        elif t == "MTEXT":
            e["p"] = (_num(e, 10), _num(e, 20))
            e["h"] = _num(e, 40)
            e["texto"] = "".join(g.get(3, [])) + g.get(1, [""])[0]
            rot = g.get(50)
            if rot:
                e["rot"] = float(rot[0])
            elif 11 in g:
                e["rot"] = math.degrees(math.atan2(_num(e, 21), _num(e, 11)))
            else:
                e["rot"] = 0.0
            e["anexo"] = int(_num(e, 71, 1))
        elif t == "INSERT":
            e["nome"] = g.get(2, [""])[0]
            e["p"] = (_num(e, 10), _num(e, 20))
            e["sx"] = _num(e, 41, 1) or 1
            e["sy"] = _num(e, 42, 1) or 1
            e["rot"] = _num(e, 50)
            if int(_num(e, 66, 0)) == 1:
                pend = e
        elif t == "DIMENSION":
            e["bloco"] = g.get(2, [""])[0]
        elif t == "LEADER":
            e["pts"] = [(float(x), float(y)) for x, y in zip(g.get(10, []), g.get(20, []))]
        elif t == "ELLIPSE":
            e["c"] = (_num(e, 10), _num(e, 20))
            e["maj"] = (_num(e, 11), _num(e, 21))
            e["ratio"] = _num(e, 40, 1)
            e["t0"] = _num(e, 41, 0)
            e["t1"] = _num(e, 42, 2 * math.pi)
        elif t in ("SOLID", "TRACE", "3DFACE"):
            e["pts"] = [(_num(e, 10), _num(e, 20)), (_num(e, 11), _num(e, 21)),
                        (_num(e, 12), _num(e, 22)), (_num(e, 13), _num(e, 23))]
        del e["_g"]
        out.append(e)
    return out


def mtext_limpo(t: str) -> str:
    t = re.sub(r"\\[Pp]", "\n", t)
    t = re.sub(r"\\[A-Za-z][^;]*;", "", t)
    t = re.sub(r"[{}]", "", t)
    return (t.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%D", "°")
             .replace("%%p", "±").replace("%%P", "±").strip())


# ------------------------------------------------------------ geometria
def texto_de_bytes(dados: bytes) -> str:
    """Bytes do arquivo → texto. DXF de 2007 em diante é UTF-8; os anteriores são da
    página de código do Windows ($DWGCODEPAGE, quase sempre ANSI_1252)."""
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        cab = dados[:6000].decode("latin-1", errors="replace")
        m = re.search(r"\$DWGCODEPAGE\s*\n\s*3\s*\n\s*ANSI_(\d+)", cab)
        pagina = "cp" + (m.group(1) if m else "1252")
        try:
            return dados.decode(pagina, errors="replace")
        except LookupError:
            return dados.decode("cp1252", errors="replace")


def codigos_de_texto(t: str) -> str:
    """Códigos de controle do TEXT: %%c Ø, %%d °, %%p ±, %%nnn caractere; %%u e %%o
    (sublinhado e sobrelinha) somem — "%%UCORTE 1" é o título "CORTE 1" sublinhado."""
    t = re.sub(r"%%(\d{3})", lambda m: chr(int(m.group(1))), t)
    t = re.sub(r"(?i)%%[uok]", "", t)
    for a, b in (("%%c", "Ø"), ("%%C", "Ø"), ("%%d", "°"), ("%%D", "°"), ("%%p", "±"), ("%%P", "±"), ("%%%", "%")):
        t = t.replace(a, b)
    return t


def _arco_pts(c, r, a0, a1, passo_graus=6.0):
    if a1 < a0:
        a1 += 360
    n = max(4, int((a1 - a0) / passo_graus))
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _bulge_pts(p, q, b):
    if abs(b) < 1e-9:
        return [p, q]
    ang = 4 * math.atan(b)
    d = math.hypot(q[0] - p[0], q[1] - p[1])
    if d < 1e-9:
        return [p, q]
    r = d / (2 * math.sin(abs(ang) / 2))
    m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    h = math.sqrt(max(r * r - (d / 2) ** 2, 0))
    nx, ny = -(q[1] - p[1]) / d, (q[0] - p[0]) / d
    s = (1 if b > 0 else -1) * (1 if abs(ang) <= math.pi else -1)
    c = (m[0] + s * h * nx, m[1] + s * h * ny)
    a0 = math.atan2(p[1] - c[1], p[0] - c[0])
    a1 = math.atan2(q[1] - c[1], q[0] - c[0])
    if b > 0 and a1 < a0:
        a1 += 2 * math.pi
    if b < 0 and a1 > a0:
        a1 -= 2 * math.pi
    n = max(3, int(abs(a1 - a0) / 0.2))
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


class _T:
    """Transformação afim 2D acumulada (inserção de blocos)."""
    def __init__(self, fn=None, rot=0.0, esc=1.0):
        self.fn = fn or (lambda p: p)
        self.rot = rot
        self.esc = esc

    def ap(self, p):
        return self.fn(p)

    def compor(self, ins_p, sx, sy, rot, base):
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        pai = self.fn

        def fn(p):
            x, y = (p[0] - base[0]) * sx, (p[1] - base[1]) * sy
            return pai((x * c - y * s + ins_p[0], x * s + y * c + ins_p[1]))
        return _T(fn, self.rot + rot, self.esc * abs(sx))


def _achatar(dxf: dict, so_modelo: bool = True):
    blocos = dxf["blocos"]

    def rec(ents, T, prof, camada_pai=None):
        for e in ents:
            if so_modelo and prof == 0 and e.get("papel"):
                continue
            # objeto do bloco na camada 0 fica na camada de quem insere o bloco (como no
            # AutoCAD): a linha da cota vai para a camada da cota, não para a 0
            if camada_pai and (e.get("camada") or "0") == "0":
                e = dict(e, camada=camada_pai)
            t = e["tipo"]
            if t == "INSERT":
                b = blocos.get(e["nome"])
                if b and prof < 10:
                    T2 = T.compor(e["p"], e["sx"], e["sy"], e["rot"], b["base"])
                    yield from rec(b["ents"], T2, prof + 1, e.get("camada") or camada_pai)
                for a in e.get("attribs", []):
                    yield a, T
            elif t == "DIMENSION":
                b = blocos.get(e.get("bloco") or "")
                if b:
                    yield from rec(b["ents"], T, prof + 1, e.get("camada") or camada_pai)
            else:
                yield e, T
    yield from rec(dxf["entidades"], _T(), 0)


# ------------------------------------------------------------ desenho do CAD
def para_desenho(texto: str, escala: float = 1.0, fator: Optional[float] = None,
                 destino: Optional[Desenho] = None, deslocamento: Ponto2 = (0.0, 0.0),
                 prefixo_camada: str = "") -> Tuple[Desenho, dict]:
    """Converte o DXF em entidades do CAD, acrescentando a `destino` (ou a um desenho novo).

    `fator` é mm por unidade do arquivo (None: pelo $INSUNITS, senão 1). `escala` é a do
    desenho de destino, para a altura de texto virar mm de papel. Devolve (desenho,
    resumo)."""
    if not texto or "SECTION" not in texto[:20000]:
        raise ErroDeDados("o arquivo não parece um DXF em texto (DXF binário e DWG não são lidos).")
    dxf = ler_dxf(texto)
    if fator is None:
        fator = FATOR_UNIDADE.get(dxf["cabecalho"].get("insunits", 0)) or 1.0
    des = destino if destino is not None else Desenho(nome="DXF importado", escala=escala)
    k = float(escala or 1.0)
    dx, dy = deslocamento
    contagem = collections.Counter()
    camadas_novas = set()
    ids = []
    cam_info = dxf["camadas"]

    def camada(e):
        nome = (prefixo_camada + (e.get("camada") or "0")).strip() or "0"
        if nome not in des.camadas:
            info = cam_info.get(e.get("camada") or "0") or {}
            cor = CORES_ACI.get(int(info.get("cor", 7) or 7), "#4b5563")
            tl = str(info.get("tipo_linha") or "CONTINUOUS").upper()
            des.camadas[nome] = Camada2D(nome, cor, tipo_linha="HIDDEN" if "HIDDEN" in tl or "DASH" in tl else ("CENTER" if "CENTER" in tl else "CONTINUOUS"))
            camadas_novas.add(nome)
        return nome

    def P(T, p):
        q = T.ap(p)
        return (round(q[0] * fator + dx, 3), round(q[1] * fator + dy, 3))

    def add(ent):
        des.add(ent)
        ids.append(ent.id)
        contagem[ent.tipo] += 1

    atr = {"origem": "dxf"}
    for e, T in _achatar(dxf):
        t = e["tipo"]
        cam = camada(e)
        if t == "LINE":
            add(Linha(camada=cam, a=P(T, e["a"]), b=P(T, e["b"]), atributos=dict(atr)))
        elif t == "CIRCLE":
            if abs(T.rot) < 1e-9 or True:
                add(Circulo(camada=cam, centro=P(T, e["c"]), raio=round(e["r"] * T.esc * fator, 4), atributos=dict(atr)))
        elif t == "ARC":
            add(Arco(camada=cam, centro=P(T, e["c"]), raio=round(e["r"] * T.esc * fator, 4),
                     inicio=(e["a0"] + T.rot) % 360, fim=(e["a1"] + T.rot) % 360, atributos=dict(atr)))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts = e["pts"]
            if len(pts) < 2:
                continue
            bul = e.get("bulge") or []
            seq: List[Ponto2] = []
            n = len(pts)
            for i in range(n - (0 if e.get("fechada") else 1)):
                p, q = pts[i], pts[(i + 1) % n]
                seg = _bulge_pts(p, q, bul[i] if i < len(bul) else 0.0)
                seq.extend(seg if not seq else seg[1:])
            vs = [P(T, p) for p in seq]
            if e.get("fechada") and len(vs) > 2 and math.hypot(vs[0][0] - vs[-1][0], vs[0][1] - vs[-1][1]) < 1e-6:
                vs = vs[:-1]
            if len(vs) == 2:
                add(Linha(camada=cam, a=vs[0], b=vs[1], atributos=dict(atr)))
            elif len(vs) > 2:
                add(Polilinha(camada=cam, vertices=vs, fechada=bool(e.get("fechada")), atributos=dict(atr)))
        elif t in ("TEXT", "ATTRIB", "MTEXT"):
            txt = mtext_limpo(e["texto"]) if t == "MTEXT" else codigos_de_texto(e["texto"])
            if not txt.strip():
                continue
            h = e["h"] * T.esc * fator / k
            if t == "MTEXT":
                al = "esquerda"
                if e.get("anexo") in (2, 5, 8):
                    al = "centro"
                elif e.get("anexo") in (3, 6, 9):
                    al = "direita"
                vert = "topo" if e.get("anexo", 1) in (1, 2, 3) else ("meio" if e.get("anexo") in (4, 5, 6) else "base")
                pos = P(T, e["p"])
            else:
                ha, va = e.get("ha", 0), e.get("va", 0)
                al = {0: "esquerda", 1: "centro", 2: "direita", 4: "centro"}.get(ha, "esquerda")
                vert = {0: "base", 1: "base", 2: "meio", 3: "topo"}.get(va, "base")
                pos = P(T, e["p2"] if (ha or va) else e["p"])
            for i, linha in enumerate(txt.split("\n")):
                if not linha.strip():
                    continue
                py = pos[1] - i * 1.6 * h * k
                add(Texto(camada=cam, posicao=(pos[0], round(py, 3)), texto=linha, altura=round(max(h, 1e-4), 4),
                          angulo=(e.get("rot", 0.0) + T.rot) % 360, alinhamento=al, vertical=vert, atributos=dict(atr)))
        elif t == "LEADER":
            vs = [P(T, p) for p in e["pts"]]
            if len(vs) >= 2:
                add(Polilinha(camada=cam, vertices=vs, fechada=False, atributos=dict(atr)))
        elif t in ("SOLID", "TRACE", "3DFACE"):
            vs = [P(T, p) for p in e["pts"]]
            if len(vs) >= 3:
                add(Polilinha(camada=cam, vertices=vs[:3] + ([vs[3]] if vs[3] != vs[2] else []), fechada=True, atributos=dict(atr)))
        elif t == "ELLIPSE":
            cx, cy = e["c"]
            mx, my = e["maj"]
            a = math.hypot(mx, my)
            b = a * e["ratio"]
            ang = math.atan2(my, mx)
            vs = []
            for i in range(37):
                tt = e["t0"] + (e["t1"] - e["t0"]) * i / 36
                x, y = a * math.cos(tt), b * math.sin(tt)
                vs.append(P(T, (cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang))))
            add(Polilinha(camada=cam, vertices=vs, fechada=abs(e["t1"] - e["t0"] - 2 * math.pi) < 1e-6, atributos=dict(atr)))
        else:
            contagem["ignorado:" + t] += 1
    resumo = {"entidades": len(ids), "ids": ids, "por_tipo": dict(contagem), "camadas_novas": sorted(camadas_novas),
              "fator": fator, "insunits": dxf["cabecalho"].get("insunits"), "blocos": len(dxf["blocos"])}
    return des, resumo
