# -*- coding: utf-8 -*-
"""Reconhecimento pela geometria: o projeto recebido sem perfil escrito (o DXF exportado
de um modelo 3D, o desenho só com linhas e cotas, sem título nem eixos).

Sem texto, o que sobra é a forma. Este módulo classifica as vistas e dá o papel a cada
barra como um detalhista faria olhando o desenho — e deixa o perfil para ser escolhido
por papel na hora de gerar o 3D (`PERFIS_PADRAO` é a sugestão inicial).

* **Pórtico / tesoura**: a vista com o reticulado da treliça (muitas diagonais curtas,
  espalhadas pela largura). Com pilares (linhas em pé compridas ou retângulos finos
  fechados, que é como o pilar treliçado vem desenhado) é o pórtico; sem eles, a
  tesoura. O vão W e a altura do pilar H saem daqui. O pórtico com mais pilares que o
  de menos (o oitão, com o pilar do meio) vai só para os eixos das pontas.
* **Planta**: a vista cuja largura (ou altura) é o vão W e que não é uma fachada. As
  linhas que atravessam o vão inteiro viram os eixos das tesouras (1, 2, 3…) e os dois
  beirais os eixos A e B; as linhas no sentido do comprimento são terças, as inclinadas
  contraventamento e os trechos curtos entre terças, correntes.
* **Fachada lateral**: pilares em pé na altura H e as longarinas entre eles; a linha do
  beiral e a do chão não são peças.
* **Repetição**: vista com o mesmo tipo, o mesmo tamanho e a mesma quantidade de linhas
  de outra já lida entra como repetida, sem peças. Retângulo fino fechado vira uma barra
  no eixo (e o que está dentro dele, a hachura ou o reticulado, é consumido); retângulo
  pequeno fechado é marca de seção, não é peça.
* **Unidade**: com o pórtico menor que 6 m (ou, sem pórtico, tudo menor que 8 m), o DXF
  está em centímetros — a escala vira 10 mm por unidade, com aviso.

As barras saem com `perfil` vazio, `fonte` "geometria" e o papel; `resumo["sem_perfil"]`
conta quantas por papel, e o "Gerar modelo 3D" pede o perfil de cada papel.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["PERFIS_PADRAO", "classificar", "unidade_em_cm", "barras_da_vista", "e_quadro"]

#: perfil sugerido para cada papel quando o desenho não diz (o usuário troca ao gerar o 3D)
PERFIS_PADRAO: Dict[str, str] = {
    "pilar": "W 250 x 32,7", "viga": "W 200 x 26,6", "banzo": "U 100x50x3,00",
    "diagonal": 'L 2"x1/8"', "montante": 'L 2"x1/8"', "terça": "Ue 150x60x20x2,00",
    "longarina": "Ue 150x60x20x2,00", "contraventamento": 'Barra redonda 1/2"',
    "tirante": 'Barra redonda 1/2"', "corrente": 'Barra redonda 1/2"', "barra": "U 100x50x3,00",
}

VAO_MINIMO_MM = 6000.0      # pórtico mais estreito que isto: o desenho está em cm
TUDO_MINIMO_MM = 8000.0     # sem pórtico: a maior vista menor que isto
MINIMO_DE_LINHAS = 6        # vista com menos linhas de peça que isto não é estrutura


def _vertical(ang: float) -> bool:
    return abs(ang - 90.0) < 4.0


def _horizontal(ang: float) -> bool:
    return ang < 4.0 or ang > 176.0


def _inclinada(ang: float) -> bool:
    return 8.0 < ang < 82.0 or 98.0 < ang < 172.0


# ------------------------------------------------------------------------------------
# Análise de uma vista (independe da escala)
# ------------------------------------------------------------------------------------

def analisar(v: dict, fechadas: Dict[str, object]) -> dict:
    """Estatísticas da vista: linhas de peça ativas, retângulos finos (barras de linha
    dupla), reticulado, pilares candidatos. `fechadas`: id → Polilinha fechada."""
    g = [s for s in v["segs"] if not s.anotacao and not s.consumido and s.peca is None]
    (x0, y0), (x1, y1) = v["caixa"]
    W, H = x1 - x0, y1 - y0
    D = max(W, H, 1e-9)
    por_ent: Dict[str, list] = collections.defaultdict(list)
    for s in g:
        por_ent[s.ent].append(s)
    finos: List[dict] = []          # {"a", "b", "ang", "L", "larg"}
    marcas: List[Tuple[float, float]] = []   # centro dos retângulos pequenos (seção de pilar na planta)
    consumir = set()
    tol = 0.005 * D
    for ent_id, lista in por_ent.items():
        e = fechadas.get(ent_id)
        if e is None:
            continue
        vs = [tuple(p) for p in (e.vertices or [])]
        if len(vs) == 5 and math.dist(vs[0], vs[-1]) <= tol:
            vs = vs[:-1]
        if len(vs) != 4:
            continue
        bx0, bx1 = min(p[0] for p in vs), max(p[0] for p in vs)
        by0, by1 = min(p[1] for p in vs), max(p[1] for p in vs)
        w, h = bx1 - bx0, by1 - by0
        # só retângulos alinhados com os eixos (o pilar em pé, a viga deitada)
        alinhado = all(abs(p[0] - bx0) <= tol or abs(p[0] - bx1) <= tol for p in vs) and \
            all(abs(p[1] - by0) <= tol or abs(p[1] - by1) <= tol for p in vs)
        if not alinhado:
            continue
        maior, menor = max(w, h), min(w, h)
        if menor <= 0.04 * D and maior >= 5.0 * menor and maior >= 0.05 * D:
            if h > w:
                a, b = ((bx0 + bx1) / 2, by0), ((bx0 + bx1) / 2, by1)
            else:
                a, b = (bx0, (by0 + by1) / 2), (bx1, (by0 + by1) / 2)
            finos.append({"a": a, "b": b, "ang": 90.0 if h > w else 0.0, "L": maior, "larg": menor,
                          "caixa": (bx0, by0, bx1, by1), "ent": ent_id})
            consumir.update(s.i for s in lista)
            # o que está dentro (a hachura, o reticulado do pilar treliçado, a outra face)
            # não é peça — a hachura costuma ser mais larga que o retângulo (a alma do
            # pilar treliçado é o retângulo; o reticulado vai de mesa a mesa)
            folga = 2.5 * menor
            if h > w:
                cx0, cx1, cy0, cy1 = bx0 - folga, bx1 + folga, by0 - tol, by1 + tol
            else:
                cx0, cx1, cy0, cy1 = bx0 - tol, bx1 + tol, by0 - folga, by1 + folga
            for s in g:
                if s.i in consumir:
                    continue
                if all(cx0 <= p[0] <= cx1 and cy0 <= p[1] <= cy1 for p in (s.a, s.b)):
                    consumir.add(s.i)
        elif maior <= 0.05 * D:
            consumir.update(s.i for s in lista)          # marca de seção
            marcas.append(((bx0 + bx1) / 2, (by0 + by1) / 2))
    ativos = [s for s in g if s.i not in consumir and s.L >= 0.006 * D]
    reticulado = [s for s in ativos if _inclinada(s.ang) and s.L < 0.12 * D]
    if reticulado:
        rx = [p[0] for s in reticulado for p in (s.a, s.b)]
        espalha = (max(rx) - min(rx)) / max(W, 1e-9)
    else:
        espalha = 0.0
    em_pe = [(s.a, s.b, s.L) for s in ativos if _vertical(s.ang)] + \
            [(f["a"], f["b"], f["L"]) for f in finos if f["ang"] == 90.0]
    pilares = [p for p in em_pe if p[2] >= 0.35 * H]
    n = len(ativos) + len(finos)
    quadro = len(reticulado) >= 8 and espalha >= 0.5 and W >= 0.8 * H and n >= MINIMO_DE_LINHAS
    # assinatura da vista (ângulo × comprimento das linhas), para achar as repetidas
    assinatura = collections.Counter((int(round(s.ang / 5.0)), int(round(s.L / (0.02 * D)))) for s in ativos)
    return {"ativos": ativos, "finos": finos, "consumidos": consumir, "reticulado": reticulado,
            "espalha": espalha, "pilares": pilares, "n": n, "W": W, "H": H, "D": D, "marcas": marcas,
            "caixa": (x0, y0, x1, y1), "quadro": quadro, "assinatura": assinatura,
            "tipo_geo": ("elevacao" if pilares else "trelica") if quadro else ""}


def _parecidas(a: dict, b: dict) -> bool:
    """As duas vistas têm as mesmas linhas (a mesma vista desenhada duas vezes)?"""
    tol = 0.01 * max(a["D"], b["D"])
    if abs(a["W"] - b["W"]) > tol or abs(a["H"] - b["H"]) > tol:
        return False
    if abs(a["n"] - b["n"]) > 0.1 * max(a["n"], b["n"]):
        return False
    comum = sum((a["assinatura"] & b["assinatura"]).values())
    return comum >= 0.9 * max(sum(a["assinatura"].values()), sum(b["assinatura"].values()), 1)


def e_quadro(a: dict) -> bool:
    return bool(a.get("quadro"))


# ------------------------------------------------------------------------------------
# Tipo de cada vista pela forma, referência de vão e altura, repetições
# ------------------------------------------------------------------------------------

def classificar(vistas: Sequence[dict], analises: Dict[int, dict]) -> dict:
    """Dá `tipo` às vistas sem título (planta, elevacao, trelica, lateral, detalhe) e
    marca as repetidas (`repetida` = id da primeira). Devolve {W, H} de referência (em
    unidades do desenho) — None quando não há pórtico."""
    quadros = [v for v in vistas if analises[v["id"]]["quadro"] or v.get("tipo") in ("trelica", "elevacao")]
    for v in quadros:
        if not v.get("tipo"):
            v["tipo"] = analises[v["id"]]["tipo_geo"]
    com_pilar = [v for v in quadros if analises[v["id"]]["pilares"]]
    W_ref = H_ref = None
    if quadros:
        ws = sorted(analises[v["id"]]["W"] for v in quadros)
        W_ref = ws[len(ws) // 2]
    if com_pilar:
        alturas = sorted(max(p[2] for p in analises[v["id"]]["pilares"]) for v in com_pilar)
        H_ref = alturas[len(alturas) // 2]
        # "elevação" com pilares muito mais baixos que os do pórtico (os montantes de uma
        # tesoura desenhada de lado, a axonometria): é só a treliça
        for v in com_pilar:
            if max(p[2] for p in analises[v["id"]]["pilares"]) < 0.5 * H_ref and v.get("tipo") == "elevacao":
                v["tipo"] = "trelica"
        com_pilar = [v for v in quadros if v.get("tipo") == "elevacao"]
    for v in vistas:
        a = analises[v["id"]]
        if v.get("tipo") or a["n"] < MINIMO_DE_LINHAS:
            continue
        W, H = a["W"], a["H"]
        vao_x = W_ref is not None and abs(W - W_ref) <= 0.06 * W_ref
        vao_y = W_ref is not None and abs(H - W_ref) <= 0.06 * W_ref
        # fachada: pilares na altura do pórtico e a largura é o comprimento (não o vão);
        # planta: uma das medidas é o vão
        fachada = H_ref is not None and len(a["pilares"]) >= 2 and 0.5 * H_ref <= H <= 1.8 * H_ref and W >= H
        if fachada and not vao_x:
            v["tipo"] = "lateral"
        elif (vao_x or vao_y) and _tem_grade(a):
            v["tipo"] = "planta"
        elif W_ref is None and _parece_planta(a):
            v["tipo"] = "planta"
        elif W_ref is None and len(a["pilares"]) >= 2 and W > 2.0 * H:
            v["tipo"] = "lateral"
        elif len(a["reticulado"]) >= 8 and a["espalha"] >= 0.5 and W >= 0.8 * H:
            v["tipo"] = "trelica"
        else:
            v["tipo"] = "detalhe"
    # repetições: mesmo tipo, mesmo tamanho, as mesmas linhas
    vistas_ok = []
    for v in vistas:
        a = analises[v["id"]]
        if a["n"] < MINIMO_DE_LINHAS:
            continue
        for u in vistas_ok:
            if u["tipo"] == v["tipo"] and _parecidas(a, analises[u["id"]]):
                v["repetida"] = u["id"]
                break
        else:
            vistas_ok.append(v)
    # a treliça solta com o vão do pórtico (a mesma tesoura desenhada de novo, a
    # axonometria dela) não entra: o pórtico já a tem
    if com_pilar and W_ref is not None:
        for v in vistas:
            if v.get("tipo") == "trelica" and v.get("repetida") is None \
                    and abs(analises[v["id"]]["W"] - W_ref) <= 0.06 * W_ref:
                v["repetida"] = com_pilar[0]["id"]
    return {"W": W_ref, "H": H_ref}


def _tem_grade(a: dict) -> bool:
    """Pelo menos três linhas atravessando a vista numa direção (terças ou tesouras)."""
    W, H = a["W"], a["H"]
    hor = sum(1 for s in a["ativos"] if _horizontal(s.ang) and s.L >= 0.6 * W)
    ver = sum(1 for s in a["ativos"] if _vertical(s.ang) and s.L >= 0.6 * H)
    return hor >= 3 or ver >= 3


def _parece_planta(a: dict) -> bool:
    W, H = a["W"], a["H"]
    hor = sum(1 for s in a["ativos"] if _horizontal(s.ang) and s.L >= 0.6 * W)
    ver = sum(1 for s in a["ativos"] if _vertical(s.ang) and s.L >= 0.6 * H)
    return hor >= 3 and ver >= 3 and 0.33 <= W / max(H, 1e-9) <= 3.0 and not a["reticulado"]


def unidade_em_cm(vistas: Sequence[dict], analises: Dict[int, dict]) -> bool:
    """O DXF sem unidade parece estar em centímetros? (pórtico com menos de 6 m de vão,
    ou, sem pórtico, a maior vista com menos de 8 m)."""
    quadros = [v for v in vistas if v.get("tipo") in ("elevacao", "trelica")]
    if quadros:
        maior = max(analises[v["id"]]["W"] * float(v.get("fator") or 1.0) for v in quadros)
        return maior < VAO_MINIMO_MM
    estr = [v for v in vistas if analises[v["id"]]["n"] >= MINIMO_DE_LINHAS]
    if not estr:
        return False
    maior = max(analises[v["id"]]["D"] * float(v.get("fator") or 1.0) for v in estr)
    return maior < TUDO_MINIMO_MM


# ------------------------------------------------------------------------------------
# Barras de cada vista
# ------------------------------------------------------------------------------------

def barras_da_vista(v: dict, a: dict, ref: dict) -> Tuple[List[dict], List[dict]]:
    """Barras (sem perfil, com papel) e eixos sintetizados da vista, pelo tipo dela."""
    tipo = v.get("tipo") or ""
    if v.get("repetida") is not None or a["n"] < MINIMO_DE_LINHAS:
        return [], []
    # o que o reconhecimento pelos textos consumiu depois da análise (a linha do eixo com balão)
    a = dict(a, ativos=[s for s in a["ativos"] if not s.consumido and s.peca is None])
    if tipo in ("elevacao", "trelica"):
        brutas, eixos = _portico(v, a), []
    elif tipo == "planta":
        brutas, eixos = _planta(v, a, ref)
    elif tipo == "lateral":
        brutas, eixos = _lateral(v, a), []
    else:
        return [], []
    tol = 0.004 * a["D"]
    fundidas = _emendar(brutas, tol)
    saida = []
    for b in fundidas:
        b.pop("caixa", None)
        b.pop("fixa", None)
        saida.append({"a": [round(b["a"][0], 3), round(b["a"][1], 3)], "b": [round(b["b"][0], 3), round(b["b"][1], 3)],
                      "perfil": "", "papel": b["papel"], "mult": 1, "vista": v["id"], "fonte": "geometria",
                      "texto": "", "dupla": bool(b.get("dupla")), "conferir": False})
    return saida, eixos


def _barra(a, b, papel, dupla=False) -> dict:
    return {"a": tuple(a), "b": tuple(b), "papel": papel, "dupla": dupla}


def _fundir_paralelas(lista: List[dict], perp: float) -> List[dict]:
    """Duas linhas paralelas, muito perto e sobrepostas (as duas faces do pilar) viram
    uma no eixo."""
    saida: List[dict] = []
    for b in sorted(lista, key=lambda b: -math.dist(b["a"], b["b"])):
        ang = math.degrees(math.atan2(b["b"][1] - b["a"][1], b["b"][0] - b["a"][0])) % 180
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        nx, ny = -uy, ux
        alvo = None
        for o in saida:
            if abs(((o["ang"] - ang) + 90) % 180 - 90) > 2.0:
                continue
            off = (b["a"][0] - o["a"][0]) * nx + (b["a"][1] - o["a"][1]) * ny
            if abs(off) > perp:
                continue
            t0 = (o["a"][0] - b["a"][0]) * ux + (o["a"][1] - b["a"][1]) * uy
            t1 = (o["b"][0] - b["a"][0]) * ux + (o["b"][1] - b["a"][1]) * uy
            tb = (b["b"][0] - b["a"][0]) * ux + (b["b"][1] - b["a"][1]) * uy
            Lb = abs(tb)
            sobre = min(max(t0, t1), max(0.0, tb)) - max(min(t0, t1), min(0.0, tb))
            if sobre >= 0.5 * min(Lb, abs(t1 - t0)):
                alvo = o
                break
        if alvo is None:
            saida.append(dict(b, ang=ang, faces=[b]))
        else:
            alvo["faces"].append(b)
    out = []
    for o in saida:
        faces = o["faces"]
        if len(faces) == 1:
            out.append(_barra(o["a"], o["b"], o["papel"], o.get("dupla", False)))
            continue
        ang = o["ang"]
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        nx, ny = -uy, ux
        offs = [((f["a"][0] - o["a"][0]) * nx + (f["a"][1] - o["a"][1]) * ny) for f in faces]
        om = (min(offs) + max(offs)) / 2
        ts = [((p[0] - o["a"][0]) * ux + (p[1] - o["a"][1]) * uy) for f in faces for p in (f["a"], f["b"])]
        t0, t1 = min(ts), max(ts)
        a = (o["a"][0] + ux * t0 + nx * om, o["a"][1] + uy * t0 + ny * om)
        b = (o["a"][0] + ux * t1 + nx * om, o["a"][1] + uy * t1 + ny * om)
        bar = _barra(a, b, o["papel"], True)
        larg = max(offs) - min(offs)
        xs = [p[0] for f in faces for p in (f["a"], f["b"])]
        ys = [p[1] for f in faces for p in (f["a"], f["b"])]
        bar["caixa"] = (min(xs) - 0.3 * larg, min(ys), max(xs) + 0.3 * larg, max(ys))
        out.append(bar)
    return out


def _dentro_de_dupla(s, duplas: List[dict]) -> bool:
    """A linha está entre as duas faces de uma barra de linha dupla (o reticulado ou a
    hachura do pilar treliçado)?"""
    for d in duplas:
        c = d.get("caixa")
        if c and all(c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3] for p in (s.a, s.b)):
            return True
    return False


def _emendar(brutas: List[dict], tol: float) -> List[dict]:
    """Trechos colineares, encostados e com o mesmo papel viram uma barra só."""
    feitas: List[Optional[dict]] = list(brutas)
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(feitas)):
            bi = feitas[i]
            if bi is None:
                continue
            if bi.get("fixa"):
                continue
            for j in range(i + 1, len(feitas)):
                bj = feitas[j]
                if bj is None or bj["papel"] != bi["papel"] or bj.get("fixa"):
                    continue
                ai = math.degrees(math.atan2(bi["b"][1] - bi["a"][1], bi["b"][0] - bi["a"][0])) % 180
                aj = math.degrees(math.atan2(bj["b"][1] - bj["a"][1], bj["b"][0] - bj["a"][0])) % 180
                if abs((ai - aj + 90) % 180 - 90) > 1.0:
                    continue
                pares = [(p, q) for p in (bi["a"], bi["b"]) for q in (bj["a"], bj["b"])]
                if min(math.dist(p, q) for p, q in pares) > tol:
                    continue
                ux, uy = math.cos(math.radians(ai)), math.sin(math.radians(ai))
                # colineares mesmo (não só paralelas encostadas na ponta)
                if abs((bj["a"][0] - bi["a"][0]) * -uy + (bj["a"][1] - bi["a"][1]) * ux) > tol:
                    continue
                pts = [bi["a"], bi["b"], bj["a"], bj["b"]]
                pts.sort(key=lambda p: p[0] * ux + p[1] * uy)
                bi = dict(bi, a=pts[0], b=pts[-1], dupla=bi.get("dupla") or bj.get("dupla"))
                feitas[i] = bi
                feitas[j] = None
                mudou = True
    return [b for b in feitas if b is not None]


def _nos_de(segs: Sequence[object], tol: float) -> Dict[Tuple[int, int], List[object]]:
    nos: Dict[Tuple[int, int], List[object]] = collections.defaultdict(list)
    for s in segs:
        for p in (s.a, s.b):
            nos[(int(round(p[0] / tol)), int(round(p[1] / tol)))].append(s)
    return nos


def _vizinhos(no_map: Dict[Tuple[int, int], List[object]], p, tol: float) -> List[object]:
    k = (int(round(p[0] / tol)), int(round(p[1] / tol)))
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            out.extend(no_map.get((k[0] + dx, k[1] + dy), ()))
    return out


def _nos_interiores(s, ativos: Sequence[object], tol: float) -> int:
    """Quantas outras linhas chegam a esta linha, ou a cruzam, fora das pontas dela (a
    barra de verdade tem nós ao longo — a diagonal que chega, o montante que cruza; a
    linha de cota só tem as linhas de chamada nas pontas)."""
    n = 0
    r = (s.b[0] - s.a[0], s.b[1] - s.a[1])
    for o in ativos:
        if o is s:
            continue
        achou = False
        for p in (o.a, o.b):
            if s.dist_linha(p) <= tol and 0.04 < s.param(p) < 0.96:
                achou = True
                break
        if not achou:
            q = (o.b[0] - o.a[0], o.b[1] - o.a[1])
            den = r[0] * q[1] - r[1] * q[0]
            if abs(den) > 1e-12:
                t = ((o.a[0] - s.a[0]) * q[1] - (o.a[1] - s.a[1]) * q[0]) / den
                u = ((o.a[0] - s.a[0]) * r[1] - (o.a[1] - s.a[1]) * r[0]) / den
                achou = 0.04 < t < 0.96 and 0.0 <= u <= 1.0
        if achou:
            n += 1
    return n


def _portico(v: dict, a: dict) -> List[dict]:
    """Pórtico ou tesoura: pilar (em pé, comprido), banzo (contorno de cima e de baixo
    do reticulado), montante (em pé, dentro da treliça), diagonal; abaixo da treliça, a
    linha inclinada é contraventamento e a deitada, longarina (do oitão). A linha do
    chão, a linha comprida sem nó no meio (cota desenhada como linha) e o que está acima
    da treliça não são peças."""
    x0, y0, x1, y1 = a["caixa"]
    W, H, D = a["W"], a["H"], a["D"]
    if H < 0.03 * W:
        return []                                        # uma tira: fila de cotas, não é treliça
    tol = 0.005 * D
    ret = a["reticulado"]
    # a faixa da treliça sai do reticulado ligado (diagonal encostada em outras duas
    # linhas do reticulado); o traço da seta de cota, solto, fica de fora
    nos_ret = _nos_de(ret, tol)
    ligados = []
    for s in ret:
        outros = {id(o) for p in (s.a, s.b) for o in _vizinhos(nos_ret, p, tol) if o is not s}
        if len(outros) >= 2:
            ligados.append(s)
    base_faixa = ligados if len(ligados) >= 4 else ret
    if base_faixa:
        ys = [p[1] for s in base_faixa for p in (s.a, s.b)]
        alt = max(ys) - min(ys)
        faixa = (min(ys) - 0.2 * alt, max(ys) + 0.2 * alt)
    else:
        faixa = (y0 + 0.5 * H, y1)
    L_pilar = 0.35 * H
    pilares: List[dict] = []
    vigas_finas = [_barra(f["a"], f["b"], "viga", True) for f in a["finos"] if f["ang"] == 0.0]
    brutas: List[dict] = []
    membros: List[dict] = []
    for f in a["finos"]:
        if f["ang"] != 90.0:
            continue
        # o retângulo fino em pé: pilar (comprido, ou abaixo da treliça — a base dele), senão montante
        if f["L"] >= L_pilar or (f["a"][1] + f["b"][1]) / 2 < faixa[0]:
            pilares.append(_barra(f["a"], f["b"], "pilar", True))
        else:
            membros.append(_barra(f["a"], f["b"], "montante", True))
    # pilar: em pé, do pé do pórtico até a treliça (o montante da treliça não parte do
    # pé; a linha em pé debaixo da vista, o fechamento desenhado abaixo do chão, não
    # chega à treliça)
    pe0 = min([min(f["a"][1], f["b"][1]) for f in a["finos"] if f["ang"] == 90.0] +
              [min(s.a[1], s.b[1]) for s in a["ativos"] if _vertical(s.ang) and s.L >= L_pilar] + [y0])

    def e_pilar(s):
        return _vertical(s.ang) and s.L >= 0.2 * H and max(s.a[1], s.b[1]) >= faixa[0] - 0.05 * H \
            and min(s.a[1], s.b[1]) <= pe0 + 0.05 * H

    for s in a["ativos"]:
        if e_pilar(s):
            pilares.append(_barra(s.a, s.b, "pilar"))
    pilares = _fundir_paralelas(pilares, 0.03 * W)
    duplas = [p for p in pilares if p.get("caixa")]
    ativos = [s for s in a["ativos"] if not e_pilar(s) and not _dentro_de_dupla(s, duplas)]
    pe = min([min(p["a"][1], p["b"][1]) for p in pilares] + [y0])
    for s in ativos:
        ym = (s.a[1] + s.b[1]) / 2
        na_faixa = faixa[0] <= ym <= faixa[1]
        if _vertical(s.ang):
            if na_faixa:
                membros.append(_barra(s.a, s.b, "montante"))
            # em pé, curta, fora da treliça: linha de chamada da cota, detalhe — não é peça
            continue
        if _horizontal(s.ang) and s.L >= 0.5 * W and abs(ym - pe) <= 0.05 * H:
            continue                                     # linha do chão
        if s.L >= 0.15 * W and _nos_interiores(s, ativos, tol) < 2:
            continue                                     # comprida e sem nó no meio: cota
        if na_faixa:
            membros.append(_barra(s.a, s.b, "?"))
        elif ym < faixa[0]:
            membros.append(_barra(s.a, s.b, "contraventamento" if _inclinada(s.ang) else "longarina"))
        # acima da treliça: cota, beiral desenhado — não é peça
    # banzo: o que está no contorno de cima ou de baixo da treliça (entre os membros da faixa)
    faixa_m = [m for m in membros if m["papel"] == "?"]
    tol_c = 0.01 * D
    for m in faixa_m:
        xm = (m["a"][0] + m["b"][0]) / 2
        ym = _y_em(m, xm)
        ys = [y for o in faixa_m if o is not m for y in [_y_em(o, xm)] if y is not None]
        if ym is None:
            m["papel"] = "diagonal"
        elif not ys or ym >= max(ys) - tol_c or ym <= min(ys) + tol_c:
            m["papel"] = "banzo"
        else:
            m["papel"] = "diagonal"
    brutas.extend(pilares)
    brutas.extend(vigas_finas)
    brutas.extend(membros)
    return brutas


def _y_em(b: dict, x: float) -> Optional[float]:
    (x0, y0), (x1, y1) = b["a"], b["b"]
    if abs(x1 - x0) < 1e-9:
        return None
    t = (x - x0) / (x1 - x0)
    if t < -1e-6 or t > 1 + 1e-6:
        return None
    return y0 + (y1 - y0) * t


def _planta(v: dict, a: dict, ref: dict) -> Tuple[List[dict], List[dict]]:
    """Planta: as linhas que atravessam o vão são os eixos das tesouras (não são peça);
    no sentido do comprimento, terça; inclinada, contraventamento; trecho curto entre
    terças, corrente."""
    x0, y0, x1, y1 = a["caixa"]
    W, H = a["W"], a["H"]
    W_ref = ref.get("W")
    # o vão está no X da planta (as tesouras são linhas deitadas) ou no Y?
    if W_ref is not None and abs(H - W_ref) <= 0.06 * W_ref and not abs(W - W_ref) <= 0.06 * W_ref:
        vao_em_x = False
    elif W_ref is not None:
        vao_em_x = True
    else:
        # sem pórtico: as tesouras são a família com menos linhas compridas
        hor = sum(1 for s in a["ativos"] if _horizontal(s.ang) and s.L >= 0.8 * W)
        ver = sum(1 for s in a["ativos"] if _vertical(s.ang) and s.L >= 0.8 * H)
        vao_em_x = hor <= ver
    brutas: List[dict] = []
    tesouras: List[float] = []      # posição perpendicular de cada linha que atravessa o vão
    atravessam: List[object] = []
    beirais: List[float] = []
    tercas_pos: List[float] = []
    tol = 0.01 * a["D"]
    for s in a["ativos"]:
        if _inclinada(s.ang):
            brutas.append(_barra(s.a, s.b, "contraventamento"))
            continue
        ao_longo_do_vao = _horizontal(s.ang) if vao_em_x else _vertical(s.ang)
        if ao_longo_do_vao:
            vao = W if vao_em_x else H
            if s.L >= 0.8 * vao:
                tesouras.append((s.a[1] + s.b[1]) / 2 if vao_em_x else (s.a[0] + s.b[0]) / 2)
                atravessam.append(s)
            else:
                brutas.append(_barra(s.a, s.b, "corrente"))
        elif _horizontal(s.ang) or _vertical(s.ang):
            comp = H if vao_em_x else W
            brutas.append(_barra(s.a, s.b, "terça"))
            tercas_pos.append((s.a[0] + s.b[0]) / 2 if vao_em_x else (s.a[1] + s.b[1]) / 2)
            if s.L >= 0.8 * comp:
                beirais.append((s.a[0] + s.b[0]) / 2 if vao_em_x else (s.a[1] + s.b[1]) / 2)
    for f in a["finos"]:
        brutas.append(_barra(f["a"], f["b"], "viga", True))
    eixos: List[dict] = []
    # os eixos das tesouras: pelas marcas de pilar (a seção do pilar na planta, duas ou
    # mais na mesma linha); senão pelas linhas que atravessam o vão; senão as pontas
    marcas = a["marcas"]
    grupos = _agrupar([m[1] if vao_em_x else m[0] for m in marcas], tol)
    pos_t = [p for p, n in grupos if n >= 2]
    pos_marcas = pos_t
    # a marca diz qual linha é a tesoura; a posição exata é a da linha
    linhas_t = _unicas(sorted(tesouras), tol)
    pos_t = [min(linhas_t, key=lambda q: abs(q - p)) if linhas_t and min(abs(q - p) for q in linhas_t) <= 3 * tol else p
             for p in pos_t]
    pos_t = _unicas(sorted(pos_t), tol)
    if len(pos_t) < 2:
        pos_t = _unicas(sorted(tesouras), tol)
    if len(pos_t) < 2:
        pos_t = [y0, y1] if vao_em_x else [x0, x1]
    # a linha que atravessa o vão fora de um eixo de tesoura é corrente (entre as terças)
    cortes = sorted(_unicas(sorted(tercas_pos), tol))
    for s in atravessam:
        p = (s.a[1] + s.b[1]) / 2 if vao_em_x else (s.a[0] + s.b[0]) / 2
        if any(abs(p - q) <= 2 * tol for q in pos_t):
            continue
        pontos = [s.a] + [((c, p) if vao_em_x else (p, c)) for c in cortes
                          if min(s.a[0 if vao_em_x else 1], s.b[0 if vao_em_x else 1]) + tol < c
                          < max(s.a[0 if vao_em_x else 1], s.b[0 if vao_em_x else 1]) - tol] + [s.b]
        pontos.sort(key=lambda q: q[0 if vao_em_x else 1])
        for q1, q2 in zip(pontos, pontos[1:]):
            brutas.append(dict(_barra(q1, q2, "corrente"), fixa=True))     # já partida: não emendar
    for k, p in enumerate(pos_t):
        if vao_em_x:
            eixos.append({"rotulo": str(k + 1), "ponto": [round(x0, 3), round(p, 3)], "ang": 0.0, "dir": [1.0, 0.0],
                          "pos": round(p, 3), "a": [round(x0, 3), round(p, 3)], "b": [round(x1, 3), round(p, 3)]})
        else:
            eixos.append({"rotulo": str(k + 1), "ponto": [round(p, 3), round(y0, 3)], "ang": 90.0, "dir": [0.0, 1.0],
                          "pos": round(p, 3), "a": [round(p, 3), round(y0, 3)], "b": [round(p, 3), round(y1, 3)]})
    # a outra família: as filas de pilares pelas marcas (as duas dos beirais e as do meio,
    # com marca na maioria das tesouras); senão os beirais desenhados; senão as pontas
    grupos_o = _agrupar([m[0] if vao_em_x else m[1] for m in marcas], tol)
    pos_b = [p for p, n in grupos_o if n >= max(2, 0.5 * len(pos_marcas))] if len(pos_marcas) >= 2 else []
    if len(pos_b) < 2:
        pos_b = _unicas(sorted(beirais), tol)
        pos_b = [pos_b[0], pos_b[-1]] if len(pos_b) >= 2 else ([x0, x1] if vao_em_x else [y0, y1])
    for k, p in enumerate(pos_b):
        rot = chr(ord("A") + k)
        if vao_em_x:
            eixos.append({"rotulo": rot, "ponto": [round(p, 3), round(y0, 3)], "ang": 90.0, "dir": [0.0, 1.0],
                          "pos": round(p, 3), "a": [round(p, 3), round(y0, 3)], "b": [round(p, 3), round(y1, 3)]})
        else:
            eixos.append({"rotulo": rot, "ponto": [round(x0, 3), round(p, 3)], "ang": 0.0, "dir": [1.0, 0.0],
                          "pos": round(p, 3), "a": [round(x0, 3), round(p, 3)], "b": [round(x1, 3), round(p, 3)]})
    return brutas, eixos


def _agrupar(valores: List[float], tol: float) -> List[Tuple[float, int]]:
    """Valores próximos (a menos de tol) agrupados: [(média, quantos)], em ordem."""
    out: List[Tuple[float, int]] = []
    for x in sorted(valores):
        if out and abs(x - out[-1][0]) <= tol:
            m, n = out[-1]
            out[-1] = ((m * n + x) / (n + 1), n + 1)
        else:
            out.append((x, 1))
    return out


def _unicas(valores: List[float], tol: float) -> List[float]:
    out: List[float] = []
    for x in valores:
        if out and abs(x - out[-1]) <= tol:
            continue
        out.append(x)
    return out


def _lateral(v: dict, a: dict) -> List[dict]:
    """Fachada lateral: pilar em pé comprido, longarina deitada comprida (menos a linha
    do beiral e a do chão), inclinada contraventamento, em pé curta montante."""
    x0, y0, x1, y1 = a["caixa"]
    W, H = a["W"], a["H"]
    L_pilar = 0.35 * H
    pilares = [_barra(f["a"], f["b"], "pilar", True) for f in a["finos"] if f["ang"] == 90.0 and f["L"] >= L_pilar]
    for s in a["ativos"]:
        if _vertical(s.ang) and s.L >= L_pilar:
            pilares.append(_barra(s.a, s.b, "pilar"))
    pilares = _fundir_paralelas(pilares, 0.03 * W)
    duplas = [p for p in pilares if p.get("caixa")]
    outras: List[dict] = []
    for s in a["ativos"]:
        if (_vertical(s.ang) and s.L >= L_pilar) or _dentro_de_dupla(s, duplas):
            continue
        ym = (s.a[1] + s.b[1]) / 2
        if _vertical(s.ang):
            outras.append(_barra(s.a, s.b, "montante"))
        elif _horizontal(s.ang):
            if s.L >= 0.5 * W and (abs(ym - y0) <= 0.03 * H or abs(ym - y1) <= 0.03 * H):
                continue                                 # beiral e chão
            outras.append(_barra(s.a, s.b, "longarina"))
        else:
            outras.append(_barra(s.a, s.b, "contraventamento"))
    for f in a["finos"]:
        if f["ang"] == 0.0:
            outras.append(_barra(f["a"], f["b"], "longarina", True))
    return pilares + outras



def conferir_pilares(vistas: Sequence[dict], barras: List[dict], analises: Dict[int, dict]) -> int:
    """Nas elevações, o "pilar" que não está numa fila de pilares da planta (as marcas de
    seção) não é pilar — é a linha de cota em pé, o eixo desenhado. Devolve quantos saíram."""
    plantas = [v for v in vistas if v.get("tipo") == "planta" and analises[v["id"]]["marcas"]
               and v.get("repetida") is None]
    if not plantas:
        return 0
    planta = max(plantas, key=lambda v: len(analises[v["id"]]["marcas"]))
    a = analises[planta["id"]]
    vao_em_x = any(e["ang"] == 0.0 and e["rotulo"].isdigit() for e in planta.get("eixos") or [])
    tol = 0.01 * a["D"]
    filas = [p for p, _n in _agrupar([m[0] if vao_em_x else m[1] for m in a["marcas"]], tol)]
    if len(filas) < 2:
        return 0
    ref = min(filas)
    offs = [p - ref for p in filas]
    larg = max(offs)
    saiu = 0
    for v in vistas:
        if v.get("tipo") not in ("elevacao",):
            continue
        pil = [b for b in barras if b["vista"] == v["id"] and b["papel"] == "pilar"]
        if len(pil) < 2:
            continue
        x_min = min(min(b["a"][0], b["b"][0]) for b in pil)
        for b in pil:
            dx = (b["a"][0] + b["b"][0]) / 2 - x_min
            if not any(abs(dx - o) <= 2 * tol or abs((larg - dx) - o) <= 2 * tol for o in offs):
                barras.remove(b)
                saiu += 1
    return saiu
