# -*- coding: utf-8 -*-
"""Leitura de DXF (R12 a R2018, texto) para o desenho 2D do CAD.

Serve para trazer um detalhe já desenhado noutro programa (o DWG de exemplo da
fábrica, convertido para DXF) para dentro de um desenho do projeto. Lê:

* LINE, CIRCLE, ARC, LWPOLYLINE (com o bulge de cada vértice, virado em arcos aproximados),
  POLYLINE/VERTEX, ELLIPSE e SPLINE (aproximadas), POINT (ignorado: são os pontos de
  definição das cotas, que o AutoCAD também não mostra);
* SOLID/TRACE e HATCH viram hachura do CAD (sólida, ou de linhas pelo padrão do arquivo);
* LEADER com a seta (tamanho pelo estilo de cota) e MULTILEADER (linha, seta e texto);
* TEXT, MTEXT (formatação do AutoCAD lida: parágrafos, altura relativa e cor por linha,
  frações empilhadas) e ATTRIB dos blocos;
* INSERT, com blocos aninhados, escala, rotação, espelhamento e ponto-base;
* DIMENSION pelo bloco anônimo que a acompanha (linhas e textos, como o CAD de origem
  desenhou) — não vira cota editável, porque o DXF não traz os pontos de definição de
  forma confiável em todos os exportadores;
* objetos com a normal para baixo (extrusão 0,0,−1: o "espelhado" do AutoCAD) voltam ao lado
  certo.

Unidades: `$INSUNITS` do cabeçalho (4 = mm, 5 = cm, 6 = m) dá o fator para milímetro;
sem ele, o chamador informa. O texto do DXF tem altura em unidades de modelo; no CAD a
altura é de papel, então ela é dividida pela escala do desenho de destino.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Hachura, Camada2D

__all__ = ["ler_dxf", "para_desenho", "mtext_linhas", "mtext_limpo", "FATOR_UNIDADE"]

Ponto2 = Tuple[float, float]

TIPOS = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "VERTEX", "SEQEND", "TEXT", "MTEXT",
         "INSERT", "ATTRIB", "DIMENSION", "HATCH", "LEADER", "POINT", "ELLIPSE", "SOLID", "SPLINE",
         "WIPEOUT", "MULTILEADER", "VIEWPORT", "ATTDEF", "3DFACE", "TRACE", "IMAGE", "XLINE", "RAY"}

#: os que precisam da ordem dos códigos (o bulge e a largura são de cada vértice; a hachura, o spline, o multileader
#: e o leader com as sobreposições do estilo de cota têm seções)
EM_ORDEM = {"LWPOLYLINE", "HATCH", "SPLINE", "MULTILEADER", "LEADER"}

#: $INSUNITS → mm por unidade.
FATOR_UNIDADE = {0: None, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 0.0254, 9: 0.0254e3 / 1000.0}

#: Cores ACI mais usadas → hex (7 é preto/branco conforme o fundo: fica o tom do CAD). As de 1 a 6 em tons que se
#: leem no fundo claro; as outras pela paleta do AutoCAD (cor_aci).
CORES_ACI = {1: "#c0392b", 2: "#b7950b", 3: "#1c7a43", 4: "#17a2b8", 5: "#1f5fbf", 6: "#8e44ad",
             7: "#16202e", 8: "#7d8a9e", 9: "#aab7cc", 30: "#e08a1e", 40: "#c99526", 250: "#333b47",
             251: "#4b5563", 252: "#6b7280", 253: "#8a94a6", 254: "#aab7cc"}

_PALETA = None


def cor_aci(indice) -> Optional[str]:
    """"#rrggbb" do índice ACI (1–255); None para BYBLOCK (0), BYLAYER (256) ou inválido. Antes só os da tabela acima
    tinham cor e o resto ficava cinza (usuário, 08/10: o DXF importado vinha sem as cores)."""
    global _PALETA
    try:
        i = abs(int(indice))
    except (TypeError, ValueError):
        return None
    if not 1 <= i <= 255:
        return None
    if i in CORES_ACI:
        return CORES_ACI[i]
    if _PALETA is None:
        from saida.dxf import _paleta_aci                 # a mesma paleta da exportação: o DXF vai e volta igual
        _PALETA = _paleta_aci()
        _PALETA.update({250: (51, 51, 51), 251: (80, 80, 80), 252: (105, 105, 105), 253: (130, 130, 130),
                        254: (190, 190, 190), 255: (255, 255, 255)})
    r, g, b = _PALETA.get(i, (75, 85, 99))
    return "#%02x%02x%02x" % (r, g, b)


def _cor_do_objeto(e) -> Optional[tuple]:
    """a cor própria do objeto: ("rgb", "#rrggbb") pela cor verdadeira (420), ("aci", n) pelo índice (62; 0 = BYBLOCK),
    None se é a da camada (BYLAYER, 256, ou sem código)"""
    g = e.get("_g") or {}
    if g.get(420):
        try:
            return ("rgb", "#%06x" % (int(g[420][0]) & 0xFFFFFF))
        except ValueError:
            pass
    if g.get(62):
        try:
            n = int(g[62][0])
        except ValueError:
            return None
        if n == 256:
            return None
        return ("aci", abs(n))
    return None


def _pares(texto: str):
    linhas = texto.split("\n")
    out = []
    for i in range(0, len(linhas) - 1, 2):
        c = linhas[i].strip()
        if c.lstrip("-").isdigit():
            out.append((int(c), linhas[i + 1].rstrip("\r")))
    return out


def ler_dxf(texto: str) -> dict:
    """Estrutura crua: {cabecalho, camadas, estilos_cota, blocos, entidades}."""
    pares = _pares(texto)
    secao = None
    cabecalho: Dict[str, object] = {}
    camadas: Dict[str, dict] = {}
    estilos_cota: Dict[str, dict] = {}
    blocos: Dict[str, dict] = {}
    modelo: List[dict] = []
    bloco = None
    ent = None
    alvo = None
    var = None
    tabela = None

    def nova(tipo):
        e = {"tipo": tipo, "_g": collections.defaultdict(list)}
        if tipo in EM_ORDEM:
            e["_seq"] = []
        return e

    def fechar():
        nonlocal ent
        if ent is not None and alvo is not None and ent.get("tipo") not in ("BLOCKDEF", "LAYER", "DIMSTYLE"):
            alvo.append(ent)
        if ent is not None and ent.get("tipo") == "LAYER" and ent.get("nome") is not None:
            camadas[ent["nome"]] = ent
        if ent is not None and ent.get("tipo") == "DIMSTYLE" and ent.get("nome") is not None:
            estilos_cota[ent["nome"]] = ent
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
                elif val == "DIMSTYLE" and tabela == "DIMSTYLE":
                    # a seta do LEADER tem o tamanho do estilo de cota: DIMASZ × DIMSCALE
                    ent = {"tipo": "DIMSTYLE", "nome": None, "asz": 2.5, "escala": 1.0, "_g": collections.defaultdict(list)}
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
                    ent = nova(val)
                    alvo = bloco["ents"]
                continue
            if secao == "ENTITIES" and val in TIPOS:
                ent = nova(val)
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
        if ent["tipo"] == "DIMSTYLE":
            try:
                if cod == 2:
                    ent["nome"] = val
                elif cod == 41:
                    ent["asz"] = float(val)
                elif cod == 40:
                    ent["escala"] = float(val) or 1.0
            except ValueError:
                pass
            continue
        ent["_g"][cod].append(val)
        if "_seq" in ent:
            ent["_seq"].append((cod, val))
    fechar()

    for b in blocos.values():
        b["ents"] = _preparar(b["ents"], estilos_cota)
    return {"cabecalho": cabecalho, "camadas": camadas, "estilos_cota": estilos_cota, "blocos": blocos,
            "entidades": _preparar(modelo, estilos_cota)}


def _num(e, c, d=0.0):
    v = e["_g"].get(c)
    try:
        return float(v[0]) if v else d
    except ValueError:
        return d


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _lwpolyline(e, inv):
    """vértices, bulges e larguras na ordem do arquivo: o 42 (bulge) só aparece no vértice que tem arco, então
    juntar todos os 42 numa lista e alinhar pelo índice punha o arco no trecho errado (o carimbo do Vicente, 08/10,
    com balões no lugar dos cantos arredondados)"""
    pts, bul = [], []
    for cod, val in e["_seq"]:
        if cod == 10:
            pts.append([_f(val), 0.0])
            bul.append(0.0)
        elif cod == 20 and pts:
            pts[-1][1] = _f(val)
        elif cod == 42 and pts:
            bul[-1] = _f(val)
    if inv:                               # normal (0,0,−1): x do sistema do objeto é −x, e o arco vira de sentido
        pts = [[-x, y] for x, y in pts]
        bul = [-b for b in bul]
    e["pts"] = [tuple(p) for p in pts]
    e["bulge"] = bul


def _hatch(e, inv):
    """contornos (listas de pontos no sistema do objeto), padrão, escala e ângulo do HATCH"""
    seq = e["_seq"]
    n = len(seq)
    i = 0
    contornos: List[List[Ponto2]] = []
    e["padrao"], e["solida"], e["escala_padrao"], e["angulo_padrao"] = "", False, 1.0, 0.0

    def val(k):
        return _f(seq[k][1]) if k < n else 0.0

    while i < n:
        cod, v = seq[i]
        if cod == 2:
            e["padrao"] = v.strip().upper()
        elif cod == 70:
            e["solida"] = bool(int(_f(v)) & 1)
        elif cod == 91:
            npaths = int(_f(v))
            i += 1
            for _ in range(npaths):
                # cada contorno: 92 (tipo), depois polilinha (72 bulge?, 73 fechada, 93 n, 10/20/42) ou arestas (93 n, 72 tipo)
                while i < n and seq[i][0] != 92:
                    i += 1
                if i >= n:
                    break
                flags = int(_f(seq[i][1]))
                i += 1
                pts: List[Ponto2] = []
                if flags & 2:
                    tem_bulge = fechada = 0
                    nv = 0
                    while i < n and seq[i][0] in (72, 73, 93):
                        if seq[i][0] == 72:
                            tem_bulge = int(_f(seq[i][1]))
                        elif seq[i][0] == 93:
                            nv = int(_f(seq[i][1]))
                        i += 1
                    vs, bs = [], []
                    while i < n and len(vs) < nv and seq[i][0] in (10, 20, 42):
                        if seq[i][0] == 10:
                            vs.append((val(i), val(i + 1)))
                            bs.append(0.0)
                            i += 2
                            continue
                        if seq[i][0] == 42:
                            bs[-1] = val(i)
                        i += 1
                    if i < n and seq[i][0] == 42 and bs:     # o bulge do último vértice
                        bs[-1] = val(i)
                        i += 1
                    for k in range(len(vs)):
                        seg = _bulge_pts(vs[k], vs[(k + 1) % len(vs)], bs[k] if tem_bulge else 0.0)
                        pts.extend(seg[:-1])
                else:
                    while i < n and seq[i][0] != 93:
                        i += 1
                    nar = int(val(i))
                    i += 1
                    for _ in range(nar):
                        while i < n and seq[i][0] != 72:
                            i += 1
                        if i >= n:
                            break
                        tipo = int(val(i))
                        i += 1
                        d: Dict[int, List[float]] = collections.defaultdict(list)
                        # até o próximo 72 (outra aresta), 97 (fim do contorno) ou 92/75; no spline, o 97 seguido de
                        # 11 é a quantidade de pontos de ajuste, não o fim
                        while i < n and (seq[i][0] not in (72, 97, 92, 75) or
                                         (tipo == 4 and seq[i][0] == 97 and i + 1 < n and seq[i + 1][0] == 11)):
                            d[seq[i][0]].append(_f(seq[i][1]))
                            i += 1
                        horario = bool(d[73]) and not d[73][0]
                        if tipo == 1 and d[10] and d[11]:
                            seg = [(d[10][0], d[20][0]), (d[11][0], d[21][0])]
                        elif tipo in (2, 3) and d[10]:
                            # arco (2) ou elipse (3); horário: os ângulos vêm medidos ao contrário e o
                            # percurso vai do início ao fim no sentido horário
                            a0, a1 = (d[50] or [0.0])[0], (d[51] or [360.0])[0]
                            if horario:
                                a0, a1 = -a1, -a0
                            if a1 < a0:
                                a1 += 360.0
                            m = max(2, int((a1 - a0) / 10))
                            angs = [math.radians(a0 + (a1 - a0) * j / m) for j in range(m + 1)]
                            cx, cy = d[10][0], d[20][0]
                            if tipo == 2:
                                r = (d[40] or [0.0])[0]
                                seg = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angs]
                            else:
                                mx, my, ra = d[11][0], d[21][0], (d[40] or [1.0])[0]
                                seg = [(cx + math.cos(a) * mx - ra * math.sin(a) * my,
                                        cy + math.cos(a) * my + ra * math.sin(a) * mx) for a in angs]
                            if horario:
                                seg.reverse()
                        elif tipo == 4:
                            seg = _spline_pts(int((d[94] or [3])[0]), d[40], list(zip(d[10], d[20])), d[42],
                                              list(zip(d[11], d[21])))
                        else:
                            seg = []
                        if seg:
                            if pts and math.hypot(pts[-1][0] - seg[0][0], pts[-1][1] - seg[0][1]) < 1e-9:
                                seg = seg[1:]
                            pts.extend(seg)
                # 97: objetos de origem (330 cada) — pular
                while i < n and seq[i][0] in (97, 330):
                    i += 1
                if len(pts) > 3 and math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1e-9:
                    pts.pop()                      # a última aresta volta ao começo: o contorno já é fechado
                if len(pts) >= 3:
                    contornos.append([(-x, y) if inv else (x, y) for x, y in pts])
            continue
        elif cod == 52:
            e["angulo_padrao"] = _f(v)
        elif cod == 41:
            e["escala_padrao"] = _f(v, 1.0) or 1.0
        elif cod == 78:
            break                          # as linhas da definição do padrão não interessam
        i += 1
    if inv:
        e["angulo_padrao"] = 180.0 - e["angulo_padrao"]
    e["contornos"] = contornos


def _spline_pts(grau, nos, ctrl, pesos, ajuste, n_seg=None):
    """pontos de um B-spline (NURBS) pelo algoritmo de De Boor; sem pontos de controle, os de ajuste"""
    if len(ctrl) < 2:
        return list(ajuste)
    p = max(1, int(grau))
    if len(nos) != len(ctrl) + p + 1:            # nó faltando: uniforme fixado nas pontas
        m = len(ctrl) - p
        nos = [0.0] * (p + 1) + [k / m for k in range(1, m)] + [1.0] * (p + 1)
    w = pesos if len(pesos) == len(ctrl) else [1.0] * len(ctrl)
    t0, t1 = nos[p], nos[len(ctrl)]
    n_seg = n_seg or max(8, 4 * len(ctrl))
    out = []
    for j in range(n_seg + 1):
        t = t0 + (t1 - t0) * j / n_seg
        k = p
        while k < len(ctrl) - 1 and t >= nos[k + 1]:
            k += 1
        d = [(ctrl[k - p + r][0] * w[k - p + r], ctrl[k - p + r][1] * w[k - p + r], w[k - p + r]) for r in range(p + 1)]
        for r in range(1, p + 1):
            for s in range(p, r - 1, -1):
                i = k - p + s
                den = nos[i + p - r + 1] - nos[i]
                a = 0.0 if den == 0 else (t - nos[i]) / den
                d[s] = tuple((1 - a) * d[s - 1][q] + a * d[s][q] for q in range(3))
        x, y, ww = d[p]
        out.append((x / ww, y / ww) if ww else (x, y))
    return out


def _multileader(e):
    """linhas da chamada (com o ponto de ligação e o patamar), a seta e o texto do MULTILEADER"""
    e["linhas"], e["patamares"], e["texto"], e["p"], e["h"], e["anexo"], e["seta"] = [], [], "", (0.0, 0.0), 0.0, 1, 0.0
    pilha = []
    lider = None
    for cod, val in e["_seq"]:
        if cod in (300, 302, 304, 305) and val.strip().endswith("{"):
            pilha.append(val.strip())
            if val.strip() == "LEADER{":
                lider = {"liga": None, "dir": (1.0, 0.0), "patamar": 0.0}
            elif val.strip() == "LEADER_LINE{":
                e["linhas"].append([])
            continue
        if val.strip() == "}" and cod in (301, 303, 305):
            topo = pilha.pop() if pilha else ""
            if topo == "LEADER{" and lider and lider["liga"]:
                for ln in e["linhas"][lider.get("de", 0):]:
                    ln.append(lider["liga"])
                if lider["patamar"]:
                    lx, ly = lider["liga"]
                    e["patamares"].append([(lx, ly), (lx + lider["dir"][0] * lider["patamar"],
                                                      ly + lider["dir"][1] * lider["patamar"])])
            continue
        topo = pilha[-1] if pilha else ""
        if topo == "CONTEXT_DATA{":
            if cod == 41:
                e["h"] = _f(val)
            elif cod == 140:
                e["seta"] = _f(val)
            elif cod == 304:
                e["texto"] = val
            elif cod == 12:
                e["p"] = (_f(val), e["p"][1])
            elif cod == 22:
                e["p"] = (e["p"][0], _f(val))
            elif cod == 171:
                e["anexo"] = int(_f(val, 1)) or 1
        elif topo == "LEADER{" and lider is not None:
            if cod == 10:
                lider["liga"] = (_f(val), 0.0)
                lider["de"] = len(e["linhas"])
            elif cod == 20 and lider["liga"]:
                lider["liga"] = (lider["liga"][0], _f(val))
            elif cod == 11:
                lider["dir"] = (_f(val), lider["dir"][1])
            elif cod == 21:
                lider["dir"] = (lider["dir"][0], _f(val))
            elif cod == 40:
                lider["patamar"] = _f(val)
        elif topo == "LEADER_LINE{" and e["linhas"]:
            if cod == 10:
                e["linhas"][-1].append((_f(val), 0.0))
            elif cod == 20 and e["linhas"][-1]:
                e["linhas"][-1][-1] = (e["linhas"][-1][-1][0], _f(val))
    # a seta vai na ponta de cada linha da chamada (o primeiro vértice), apontando do segundo para ele
    e["setas"] = [(ln[0], ln[1]) for ln in e["linhas"] if len(ln) >= 2 and ln[0] != ln[1]]
    e["linhas"] += e["patamares"]


def _leader(e, estilos):
    """a seta do LEADER: tamanho = DIMASZ × DIMSCALE do estilo, com as sobreposições do próprio leader (XDATA DSTYLE)"""
    est = estilos.get(e["_g"].get(3, [""])[0]) or {}
    asz, esc = est.get("asz", 2.5), est.get("escala", 1.0) or 1.0
    seq = e["_seq"]
    for k, (cod, val) in enumerate(seq):
        if cod == 1070 and k + 1 < len(seq) and seq[k + 1][0] == 1040:
            if int(_f(val)) == 41:
                asz = _f(seq[k + 1][1], asz)
            elif int(_f(val)) == 40:
                esc = _f(seq[k + 1][1], esc) or esc
    e["seta"] = asz * esc if int(_num(e, 71, 1)) else 0.0


def _preparar(lista, estilos_cota=None):
    out = []
    pend = None
    estilos_cota = estilos_cota or {}
    for e in lista:
        g = e["_g"]
        e["camada"] = g.get(8, ["0"])[0]
        e["cor"] = _cor_do_objeto(e)
        e["papel"] = int(_num(e, 67, 0)) == 1
        inv = _num(e, 230, 1.0) < 0             # normal (0,0,−1): o sistema do objeto tem o x invertido
        t = e["tipo"]
        if t == "LINE":
            e["a"] = (_num(e, 10), _num(e, 20))
            e["b"] = (_num(e, 11), _num(e, 21))
        elif t in ("ARC", "CIRCLE"):
            e["c"] = (_num(e, 10), _num(e, 20))
            e["r"] = _num(e, 40)
            e["a0"] = _num(e, 50)
            e["a1"] = _num(e, 51, 360)
            if inv:
                e["c"] = (-e["c"][0], e["c"][1])
                e["a0"], e["a1"] = 180.0 - e["a1"], 180.0 - e["a0"]
        elif t == "LWPOLYLINE":
            _lwpolyline(e, inv)
            e["fechada"] = bool(int(_num(e, 70, 0)) & 1)
        elif t == "HATCH":
            _hatch(e, inv)
        elif t == "SPLINE":
            d: Dict[int, List[float]] = collections.defaultdict(list)
            for cod, val in e["_seq"]:
                d[cod].append(_f(val))
            e["pts"] = _spline_pts(int((d[71] or [3])[0]), d[40], list(zip(d[10], d[20])), d[41], list(zip(d[11], d[21])))
            e["fechada"] = bool(int((d[70] or [0])[0]) & 1)
            if inv:
                e["pts"] = [(-x, y) for x, y in e["pts"]]
        elif t == "MULTILEADER":
            _multileader(e)
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
            e["largura"] = _num(e, 41, 0.0)
        elif t == "INSERT":
            e["nome"] = g.get(2, [""])[0]
            e["p"] = (_num(e, 10), _num(e, 20))
            e["sx"] = _num(e, 41, 1) or 1
            e["sy"] = _num(e, 42, 1) or 1
            e["rot"] = _num(e, 50)
            if inv:                        # bloco espelhado pela normal: o mesmo que escala x negativa e giro ao contrário
                e["p"] = (-e["p"][0], e["p"][1])
                e["sx"], e["rot"] = -e["sx"], -e["rot"]
            if int(_num(e, 66, 0)) == 1:
                pend = e
        elif t == "DIMENSION":
            e["bloco"] = g.get(2, [""])[0]
        elif t == "LEADER":
            e["pts"] = [(float(x), float(y)) for x, y in zip(g.get(10, []), g.get(20, []))]
            _leader(e, estilos_cota)
        elif t == "ELLIPSE":
            # o centro e o eixo maior já vêm no sistema do mundo, mas com a normal para baixo o eixo menor fica do
            # outro lado: o arco parcial saía espelhado (as 1.336 roscas do Vicente, 08/10)
            e["inv"] = inv
            e["c"] = (_num(e, 10), _num(e, 20))
            e["maj"] = (_num(e, 11), _num(e, 21))
            e["ratio"] = _num(e, 40, 1)
            e["t0"] = _num(e, 41, 0)
            e["t1"] = _num(e, 42, 2 * math.pi)
        elif t in ("SOLID", "TRACE", "3DFACE"):
            p = [(_num(e, 10), _num(e, 20)), (_num(e, 11), _num(e, 21)),
                 (_num(e, 12), _num(e, 22)), (_num(e, 13), _num(e, 23))]
            # o SOLID e o TRACE se fecham na ordem 1-2-4-3 (o 3DFACE em 1-2-3-4)
            e["pts"] = p if t == "3DFACE" else [p[0], p[1], p[3], p[2]]
            if inv and t != "3DFACE":
                e["pts"] = [(-x, y) for x, y in e["pts"]]
        del e["_g"]
        e.pop("_seq", None)
        out.append(e)
    return out


def mtext_linhas(t: str, altura: float = 1.0) -> List[Tuple[str, float, Optional[int]]]:
    """O texto do MTEXT em linhas, cada uma com o fator de altura (sobre `altura`, a do MTEXT) e a cor (ACI) com
    que começa.

    Lê os códigos do AutoCAD um a um: \\P e \\N quebram a linha; \\L \\l \\O \\o \\K \\k (sublinhado, sobrelinha,
    riscado) não têm argumento; \\H…; muda a altura (com x, relativa); \\C…; a cor; \\S a^b; ou a/b; é a fração
    empilhada; \\U+XXXX é o caractere; \\p…; \\f…; \\A…; \\Q…; \\W…; \\T…; são formatação que some; {} agrupam;
    ^J quebra a linha. Antes, uma expressão só tirava "de \\ até o ;" e engolia o título sublinhado inteiro:
    "{\\LCORTE A-A\\P\\H0.5x;\\l\\C1;ESC.: 1:50}" virava só "ESC.: 1:50" (Vicente, 08/10)."""
    linhas: List[list] = []
    atual: List[str] = []
    fator, cor = 1.0, None
    pilha: List[tuple] = []
    inicio = [1.0, None, False]           # fator e cor do primeiro caractere visível da linha

    def por(ch):
        if not inicio[2] and ch.strip():
            inicio[0], inicio[1], inicio[2] = fator, cor, True
        atual.append(ch)

    def quebra():
        linhas.append(["".join(atual), inicio[0] if inicio[2] else fator, inicio[1] if inicio[2] else cor])
        atual.clear()
        inicio[2] = False

    def argumento(k):
        f = t.find(";", k)
        if f < 0:
            return t[k:], len(t)
        return t[k:f], f + 1

    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        if ch == "\\" and i + 1 < n:
            c = t[i + 1]
            i += 2
            if c in "PN":
                quebra()
            elif c in "LlOoKk":
                pass
            elif c == "~":
                por(" ")
            elif c in "\\{}":
                por(c)
            elif c == "U" and t[i:i + 1] == "+" and re.match(r"[0-9A-Fa-f]{4}", t[i + 1:i + 5]):
                por(chr(int(t[i + 1:i + 5], 16)))
                i += 5
            elif c == "S":
                a, i = argumento(i)
                partes = re.split(r"[\^/#]", a, maxsplit=1)
                frac = "/".join(p.strip() for p in partes if p.strip())
                if frac[:1].isdigit() and atual and atual[-1][-1:].isdigit():
                    por(" ")                        # 2\S1/2; → "2 1/2" — colado, "21/2" (auditoria D7, 11/10)
                por(frac)
            elif c == "H":
                a, i = argumento(i)
                try:
                    fator = fator * float(a[:-1]) if a.lower().endswith("x") else float(a) / (altura or 1.0)
                except ValueError:
                    pass
            elif c == "C":
                a, i = argumento(i)
                try:
                    cor = int(float(a)) or None
                except ValueError:
                    pass
            elif c.isalpha():
                _, i = argumento(i)
            else:
                por(c)
            continue
        if ch == "{":
            pilha.append((fator, cor))
        elif ch == "}":
            if pilha:
                fator, cor = pilha.pop()
        elif ch == "^" and i + 1 < n:
            c = t[i + 1]
            i += 2
            if c in "JM":
                quebra()
            elif c == "I":
                por(" ")
            elif c == " ":
                por("^")
            elif not ("@" <= c <= "_"):
                por("^" + c)
            continue
        else:
            por(ch)
        i += 1
    quebra()
    out = []
    for txt, f, c in linhas:
        txt = (txt.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%D", "°")
                  .replace("%%p", "±").replace("%%P", "±"))
        out.append((txt.rstrip(), f, c))
    while out and not out[-1][0].strip():
        out.pop()
    while out and not out[0][0].strip():
        out.pop(0)
    return out


def mtext_limpo(t: str) -> str:
    return "\n".join(l for l, _, _ in mtext_linhas(t)).strip()


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
    """Transformação afim 2D acumulada (inserção de blocos): p' = M·p + t, com M = [[a, b], [c, d]].

    Antes guardava só o giro e a escala x, e o arco de um bloco espelhado ou com escala diferente em x e y saía no
    lugar errado; agora o arco e o círculo viram polilinha quando a transformação não é uma semelhança."""
    def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, tx=0.0, ty=0.0):
        self.a, self.b, self.c, self.d, self.tx, self.ty = a, b, c, d, tx, ty
        det = a * d - b * c
        self.espelhada = det < 0
        self.esc = math.sqrt(abs(det)) or 1.0
        self.rot = math.degrees(math.atan2(c, a))
        # semelhança: as colunas com o mesmo tamanho e perpendiculares
        n1, n2 = math.hypot(a, c), math.hypot(b, d)
        self.semelhanca = abs(n1 - n2) <= 1e-6 * max(n1, n2, 1e-12) and abs(a * b + c * d) <= 1e-6 * max(n1 * n2, 1e-12)
        self.esc_y = n2 or 1.0               # o que a altura do texto (na direção y do objeto) cresce

    def ap(self, p):
        return (self.a * p[0] + self.b * p[1] + self.tx, self.c * p[0] + self.d * p[1] + self.ty)

    def angulo(self, graus):
        """ângulo de uma direção do objeto depois da transformação"""
        r = math.radians(graus)
        x, y = math.cos(r), math.sin(r)
        return math.degrees(math.atan2(self.c * x + self.d * y, self.a * x + self.b * y))

    def compor(self, ins_p, sx, sy, rot, base):
        cs, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        # local: q = R(rot)·S(sx, sy)·(p − base) + ins_p
        la, lb, lc, ld = cs * sx, -sn * sy, sn * sx, cs * sy
        ltx = ins_p[0] - (la * base[0] + lb * base[1])
        lty = ins_p[1] - (lc * base[0] + ld * base[1])
        return _T(self.a * la + self.b * lc, self.a * lb + self.b * ld,
                  self.c * la + self.d * lc, self.c * lb + self.d * ld,
                  self.a * ltx + self.b * lty + self.tx, self.c * ltx + self.d * lty + self.ty)


def _achatar(dxf: dict, so_modelo: bool = True):
    blocos = dxf["blocos"]

    def rec(ents, T, prof, camada_pai=None, cor_pai=None):
        for e in ents:
            if so_modelo and prof == 0 and e.get("papel"):
                continue
            # objeto do bloco na camada 0 fica na camada de quem insere o bloco (como no
            # AutoCAD): a linha da cota vai para a camada da cota, não para a 0
            if camada_pai and (e.get("camada") or "0") == "0":
                e = dict(e, camada=camada_pai)
            # a cor BYBLOCK (0) é a de quem insere o bloco: a própria dele, se tem (senão fica a da camada)
            if e.get("cor") == ("aci", 0):
                e = dict(e, cor=cor_pai)
            t = e["tipo"]
            if t == "INSERT":
                b = blocos.get(e["nome"])
                if b and prof < 10:
                    T2 = T.compor(e["p"], e["sx"], e["sy"], e["rot"], b["base"])
                    yield from rec(b["ents"], T2, prof + 1, e.get("camada") or camada_pai, e.get("cor") or cor_pai)
                for a in e.get("attribs", []):
                    yield a, T
            elif t == "DIMENSION":
                b = blocos.get(e.get("bloco") or "")
                if b:
                    yield from rec(b["ents"], T, prof + 1, e.get("camada") or camada_pai, e.get("cor") or cor_pai)
            else:
                yield e, T
    yield from rec(dxf["entidades"], _T(), 0)


def _pontos_do_arco(c, r, a0, a1, passo=5.0):
    if a1 <= a0:
        a1 += 360.0
    m = max(4, int((a1 - a0) / passo))
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / m)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / m))) for i in range(m + 1)]


def _seta(ponta, de, tamanho):
    """triângulo da seta fechada do AutoCAD: comprimento = tamanho, largura = tamanho/3"""
    dx, dy = ponta[0] - de[0], ponta[1] - de[1]
    L = math.hypot(dx, dy)
    if L < 1e-9 or tamanho <= 0:
        return None
    ux, uy = dx / L, dy / L
    bx, by = ponta[0] - ux * tamanho, ponta[1] - uy * tamanho
    w = tamanho / 6.0
    return [ponta, (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)]


#: padrões de hachura do AutoCAD → padrão do CAD (o de linhas, "aco", é o ANSI31: linhas a 45°)
PADROES_CONCRETO = ("AR-CONC", "CONC", "ANSI33", "AR-SAND", "GRAVEL", "EARTH")
#: espaçamento das linhas do ANSI31 na escala 1 (1/8")
ESPACO_ANSI31 = 3.175


def tipo_de_linha(nome: str) -> str:
    """o tipo de linha do AutoCAD no traço mais parecido do CAD (HIDDEN, CENTER = traço-ponto, DASHED, DOT): antes
    o DASHDOT virava tracejado e o PHANTOM e o DIVIDE contínuos (a grade da laje do Vicente, 08/10)"""
    n = str(nome or "").upper()
    if "HIDDEN" in n:
        return "HIDDEN"
    if any(x in n for x in ("DASHDOT", "CENTER", "PHANTOM", "DIVIDE")):
        return "CENTER"
    if "DASH" in n:
        return "DASHED"
    if "DOT" in n:
        return "DOT"
    return "CONTINUOUS"


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
            cor = cor_aci(info.get("cor", 7) or 7) or "#4b5563"
            tl = str(info.get("tipo_linha") or "CONTINUOUS").upper()
            des.camadas[nome] = Camada2D(nome, cor, tipo_linha=tipo_de_linha(tl))
            camadas_novas.add(nome)
        return nome

    def P(T, p):
        q = T.ap(p)
        return (round(q[0] * fator + dx, 3), round(q[1] * fator + dy, 3))

    def add(ent):
        des.add(ent)
        ids.append(ent.id)
        contagem[ent.tipo] += 1

    def linha_ou_poli(cam, vs, fechada, atr):
        if fechada and len(vs) > 2 and math.hypot(vs[0][0] - vs[-1][0], vs[0][1] - vs[-1][1]) < 1e-6:
            vs = vs[:-1]
        if len(vs) == 2:
            add(Linha(camada=cam, a=vs[0], b=vs[1], atributos=dict(atr)))
        elif len(vs) > 2:
            add(Polilinha(camada=cam, vertices=vs, fechada=bool(fechada), atributos=dict(atr)))

    def solida(cam, vs, atr):
        if len(vs) >= 3:
            add(Hachura(camada=cam, contornos=[vs], padrao="solido", angulo=0.0, espacamento=1.0, atributos=dict(atr)))

    def textos(cam, T, linhas, h0, pos, rot, al, vert, atr):
        """as linhas do texto, uma embaixo da outra (5/3 da altura de cada uma), com a altura e a cor de cada"""
        desce = 0.0
        for txt, f, cor in linhas:
            h = h0 * f
            if txt.strip():
                a = dict(atr)
                if cor:
                    a["cor"] = cor_aci(cor) or a.get("cor")
                r = math.radians(rot)
                px, py = pos[0] + math.sin(r) * desce, pos[1] - math.cos(r) * desce
                add(Texto(camada=cam, posicao=(round(px, 3), round(py, 3)), texto=txt, altura=round(max(h, 1e-4), 4),
                          angulo=rot % 360, alinhamento=al, vertical=vert, atributos=a))
            desce += 5.0 / 3.0 * h * k

    base_atr = {"origem": "dxf"}
    for e, T in _achatar(dxf):
        t = e["tipo"]
        if t in ("POINT", "ATTDEF"):
            continue                       # pontos de definição das cotas: o AutoCAD também não mostra
        cam = camada(e)
        # a cor própria do objeto (por cima da da camada), como no CAD de origem
        c = e.get("cor")
        hexa = c[1] if c and c[0] == "rgb" else (cor_aci(c[1]) if c else None)
        atr = dict(base_atr, cor=hexa) if hexa else base_atr
        if t == "LINE":
            add(Linha(camada=cam, a=P(T, e["a"]), b=P(T, e["b"]), atributos=dict(atr)))
        elif t in ("CIRCLE", "ARC"):
            r = e["r"]
            if T.semelhanca and t == "CIRCLE":
                add(Circulo(camada=cam, centro=P(T, e["c"]), raio=round(r * T.esc * fator, 4), atributos=dict(atr)))
            elif T.semelhanca:
                # espelhado: o arco anda ao contrário, então o início e o fim trocam
                a0, a1 = (T.angulo(e["a1"]), T.angulo(e["a0"])) if T.espelhada else (T.angulo(e["a0"]), T.angulo(e["a1"]))
                add(Arco(camada=cam, centro=P(T, e["c"]), raio=round(r * T.esc * fator, 4),
                         inicio=round(a0 % 360, 6), fim=round(a1 % 360, 6), atributos=dict(atr)))
            else:
                a0, a1 = (0.0, 360.0) if t == "CIRCLE" else (e["a0"], e["a1"])
                linha_ou_poli(cam, [P(T, p) for p in _pontos_do_arco(e["c"], r, a0, a1)], t == "CIRCLE", atr)
        elif t in ("LWPOLYLINE", "POLYLINE", "SPLINE"):
            pts = e["pts"]
            if len(pts) < 2:
                continue
            if t == "SPLINE":
                seq = list(pts)
            else:
                bul = e.get("bulge") or []
                seq: List[Ponto2] = []
                n = len(pts)
                for i in range(n - (0 if e.get("fechada") else 1)):
                    p, q = pts[i], pts[(i + 1) % n]
                    seg = _bulge_pts(p, q, bul[i] if i < len(bul) else 0.0)
                    seq.extend(seg if not seq else seg[1:])
            linha_ou_poli(cam, [P(T, p) for p in seq], e.get("fechada"), atr)
        elif t in ("TEXT", "ATTRIB"):
            txt = codigos_de_texto(e["texto"])
            if not txt.strip():
                continue
            h = e["h"] * T.esc_y * fator / k
            ha, va = e.get("ha", 0), e.get("va", 0)
            al = {0: "esquerda", 1: "centro", 2: "direita", 4: "centro"}.get(ha, "esquerda")
            vert = {0: "base", 1: "base", 2: "meio", 3: "topo"}.get(va, "base")
            if ha == 4:
                vert = "meio"
            pos = P(T, e["p2"] if (ha or va) else e["p"])
            textos(cam, T, [(l, 1.0, None) for l in txt.split("\n")], h, pos, T.angulo(e.get("rot", 0.0)), al, vert, atr)
        elif t == "MTEXT":
            linhas = mtext_linhas(e["texto"], e["h"])
            if not any(l.strip() for l, _, _ in linhas):
                continue
            h = e["h"] * T.esc_y * fator / k
            anexo = e.get("anexo") or 1
            al = "centro" if anexo in (2, 5, 8) else ("direita" if anexo in (3, 6, 9) else "esquerda")
            vert = "topo" if anexo in (1, 2, 3) else ("meio" if anexo in (4, 5, 6) else "base")
            base = e["p"]
            # parágrafo alinhado (\pxql; \pxqc; \pxqr;) dentro da caixa da largura do MTEXT: as linhas encostam na
            # borda da caixa, não no ponto de inserção (o carimbo do Vicente vinha centrado, e é à esquerda)
            q = re.search(r"\\p[^;]*?q([lcr])", e["texto"])
            w = e.get("largura") or 0.0
            if q and w > 0:
                col = {"esquerda": 0.0, "centro": 0.5, "direita": 1.0}
                desl = ({"l": 0.0, "c": 0.5, "r": 1.0}[q.group(1)] - col[al]) * w
                r = math.radians(e.get("rot", 0.0))
                base = (base[0] + math.cos(r) * desl, base[1] + math.sin(r) * desl)
                al = {"l": "esquerda", "c": "centro", "r": "direita"}[q.group(1)]
            textos(cam, T, linhas, h, P(T, base), T.angulo(e.get("rot", 0.0)), al, vert, atr)
        elif t == "LEADER":
            vs = [P(T, p) for p in e["pts"]]
            linha_ou_poli(cam, vs, False, atr)
            if len(vs) >= 2 and e.get("seta"):
                solida(cam, _seta(vs[0], vs[1], e["seta"] * T.esc * fator) or [], atr)
        elif t == "MULTILEADER":
            for ln in e["linhas"]:
                linha_ou_poli(cam, [P(T, p) for p in ln], False, atr)
            for ponta, de in e["setas"]:
                solida(cam, _seta(P(T, ponta), P(T, de), e["seta"] * T.esc * fator) or [], atr)
            linhas = mtext_linhas(e["texto"], e["h"])
            if any(l.strip() for l, _, _ in linhas) and e["h"] > 0:
                anexo = e.get("anexo") or 1
                al = "centro" if anexo in (2, 5, 8) else ("direita" if anexo in (3, 6, 9) else "esquerda")
                vert = "topo" if anexo in (1, 2, 3) else ("meio" if anexo in (4, 5, 6) else "base")
                textos(cam, T, linhas, e["h"] * T.esc_y * fator / k, P(T, e["p"]), T.angulo(0.0), al, vert, atr)
        elif t in ("SOLID", "TRACE"):
            vs = [P(T, p) for p in e["pts"]]
            if vs[3] == vs[2]:
                vs = vs[:3]
            # a marca "dxf": "SOLID" deixa o reconhecimento usar o contorno como antes (a ponta de seta da cota)
            solida(cam, vs, dict(atr, dxf="SOLID"))
        elif t == "3DFACE":
            vs = [P(T, p) for p in e["pts"]]
            linha_ou_poli(cam, vs[:3] + ([vs[3]] if vs[3] != vs[2] else []), True, atr)
        elif t == "HATCH":
            contornos = [[P(T, p) for p in ct] for ct in e.get("contornos") or []]
            contornos = [ct for ct in contornos if len(ct) >= 3]
            if not contornos:
                contagem["vazia:HATCH"] += 1
                continue
            nome = e.get("padrao") or ""
            if e.get("solida") or nome == "SOLID":
                add(Hachura(camada=cam, contornos=contornos, padrao="solido", angulo=0.0, espacamento=1.0,
                            atributos=dict(atr)))
            else:
                # ANSI31: linhas a 45° (+ o giro do padrão) com 1/8" × a escala do padrão, em mm de papel
                ang = (45.0 + T.angulo(e.get("angulo_padrao", 0.0))) % 180 or 180.0     # 0 o CAD lê como "sem ângulo" (45°)
                esp = ESPACO_ANSI31 * e.get("escala_padrao", 1.0) * T.esc * fator / k
                add(Hachura(camada=cam, contornos=contornos, padrao="concreto" if nome in PADROES_CONCRETO else "aco",
                            angulo=round(ang, 3), espacamento=round(max(esp, 1e-3), 4),
                            atributos=dict(atr, padrao_dxf=nome)))
        elif t == "ELLIPSE":
            cx, cy = e["c"]
            mx, my = e["maj"]
            a = math.hypot(mx, my)
            b = a * e["ratio"] * (-1.0 if e.get("inv") else 1.0)
            ang = math.atan2(my, mx)
            t0, t1 = e["t0"], e["t1"]
            if t1 <= t0:
                t1 += 2 * math.pi
            inteira = abs(t1 - t0 - 2 * math.pi) < 1e-6
            m = max(8, int(36 * (t1 - t0) / (2 * math.pi)))
            vs = []
            for i in range(m + 1):
                tt = t0 + (t1 - t0) * i / m
                x, y = a * math.cos(tt), b * math.sin(tt)
                vs.append(P(T, (cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang))))
            linha_ou_poli(cam, vs, inteira, atr)
        else:
            contagem["ignorado:" + t] += 1
    resumo = {"entidades": len(ids), "ids": ids, "por_tipo": dict(contagem), "camadas_novas": sorted(camadas_novas),
              "fator": fator, "insunits": dxf["cabecalho"].get("insunits"), "blocos": len(dxf["blocos"])}
    return des, resumo
