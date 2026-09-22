# -*- coding: utf-8 -*-
"""Pranchas (folhas de desenho) montadas a partir dos desenhos 2D do projeto.

Uma prancha é um `Desenho` em **milímetro de papel** (escala 1): moldura, quadro,
carimbo e as vistas já reduzidas à escala de cada uma. Assim ela abre no CAD como
qualquer desenho — dá para mover uma vista, acrescentar uma nota, cotar por cima — e
exporta para DXF em papel 1:1, que é o que a plotagem e a produção esperam.

O que entra são **células**: um desenho de detalhamento (`nucleo2d/detalhar.py`) traz
em `metadados.celulas` a caixa de cada posição ou conjunto, e cada célula vira uma
vista independente; um desenho sem células (um corte, uma planta) é uma célula só. As
células são distribuídas em prateleiras na área útil da folha; a que não cabe na
escala do desenho de origem desce para a escala normalizada seguinte, com nota; a que
não cabe na prateleira vai para a prancha seguinte. A numeração sai "01/07".

Ao reduzir para o papel, o que já é "de papel" não muda: altura de texto, setas e
afastamento de cota, espaçamento de hachura. A cota recebe o valor original como texto
fixo, porque a distância entre os seus pontos na prancha é a de papel.
"""
import collections
import copy
import math
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import (Desenho, Entidade2D, Linha, Polilinha, Circulo, Arco, Texto,
                              Cota, Hachura, Chamada, Camada2D, formatar_mm)

__all__ = ["montar_pranchas", "FOLHAS", "CARIMBO", "texto_escala"]

Ponto2 = Tuple[float, float]

#: Formatos ISO 216 em paisagem: (largura, altura) em mm — os mesmos de saida/pranchas.py.
FOLHAS: Dict[str, Tuple[float, float]] = {
    "A0": (1189.0, 841.0), "A1": (841.0, 594.0), "A2": (594.0, 420.0),
    "A3": (420.0, 297.0), "A4": (297.0, 210.0),
}
MARGENS = {"esquerda": 20.0, "direita": 10.0, "superior": 10.0, "inferior": 10.0}
MARGENS_A3 = {"esquerda": 15.0, "direita": 7.0, "superior": 7.0, "inferior": 7.0}
#: Carimbo (largura × altura, mm): 180 mm é a largura da ISO 7200.
CARIMBO = {"A0": (180.0, 70.0), "A1": (180.0, 65.0), "A2": (180.0, 60.0),
           "A3": (180.0, 55.0), "A4": (170.0, 50.0)}
ESCALAS = (1, 2, 2.5, 5, 10, 15, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500)
#: Folga entre células e faixa do rótulo de escala sob cada uma (mm de papel).
FOLGA = 10.0
FAIXA = 7.0
OBS_CARIMBO = ("Desenho gerado automaticamente. Conferir antes da fabricação.")


def texto_escala(escala: float) -> str:
    if escala < 1.0:
        return "%g:1" % (1.0 / escala)
    return "1:%g" % escala


def escala_normalizada(minima: float) -> float:
    for e in ESCALAS:
        if e >= minima - 1e-9:
            return float(e)
    return float(ESCALAS[-1])


# ============================================================ transformação
def _para_papel(e: Entidade2D, k: float, dx: float, dy: float, fonte: str) -> Entidade2D:
    """Cópia da entidade com as coordenadas de modelo divididas por `k` e deslocadas;
    o que é de papel (alturas, afastamentos, espaçamentos) fica como está."""
    n = copy.deepcopy(e)
    n.id = Entidade2D().id
    mv = lambda p: (round(p[0] / k + dx, 3), round(p[1] / k + dy, 3))    # noqa: E731
    if isinstance(n, Linha):
        n.a, n.b = mv(n.a), mv(n.b)
    elif isinstance(n, Polilinha):
        n.vertices = [mv(p) for p in n.vertices]
    elif isinstance(n, (Circulo, Arco)):
        n.centro = mv(n.centro)
        n.raio = round(n.raio / k, 4)
    elif isinstance(n, Texto):
        n.posicao = mv(n.posicao)
    elif isinstance(n, Cota):
        if n.texto is None or n.texto == "":
            n.texto = formatar_mm(n.valor())
        n.p1, n.p2 = mv(n.p1), mv(n.p2)
    elif isinstance(n, Hachura):
        n.contornos = [[mv(p) for p in c] for c in n.contornos]
    elif isinstance(n, Chamada):
        n.alvo, n.posicao = mv(n.alvo), mv(n.posicao)
    n.atributos = dict(n.atributos or {}, fonte=fonte, escala=k)
    return n


def _caixa_de(ents: Sequence[Entidade2D], escala: float = 1.0) -> Optional[Tuple[Ponto2, Ponto2]]:
    """Caixa das entidades; um texto ocupa a largura estimada (0,75 × altura × caracteres,
    em mm de modelo pela escala), senão o título "P12 – 112x" sai da célula na folha."""
    pts = []
    for e in ents:
        if isinstance(e, Texto) and e.angulo == 0.0:
            larg = 0.75 * e.altura * escala * len(e.texto or "")
            x, y = e.posicao
            x0 = x - larg / 2 if e.alinhamento == "centro" else x - larg if e.alinhamento == "direita" else x
            pts += [(x0, y), (x0 + larg, y + e.altura * escala)]
        else:
            pts += e.pontos()
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys)), (max(xs), max(ys))


def celulas_de(desenho: Desenho, nome: str) -> List[dict]:
    """Células de um desenho: as de `metadados.celulas` (detalhamento) ou o desenho inteiro.

    Cada célula: {fonte, titulo, escala, caixa, entidades}. Uma entidade pertence à
    célula que contém todos os seus pontos (com folga), e a que não pertence a nenhuma
    vai para a célula mais próxima."""
    visiveis = [e for e in desenho.entidades.values()
                if not (desenho.camadas.get(e.camada) and not desenho.camadas[e.camada].visivel)]
    caixas = desenho.metadados.get("celulas") or []
    if not caixas or len(caixas) == 1:
        caixa = _caixa_de(visiveis, float(desenho.escala or 1.0))
        if caixa is None:
            return []
        return [{"fonte": nome, "titulo": desenho.nome, "desenho_titulo": desenho.nome,
                 "escala": float(desenho.escala or 1.0), "caixa": caixa, "entidades": visiveis}]
    folga = 0.5 * desenho.escala
    celulas = [{"fonte": nome, "titulo": desenho.nome, "desenho_titulo": desenho.nome,
                "escala": float(desenho.escala or 1.0), "caixa": ((c[0], c[1]), (c[2], c[3])), "entidades": []}
               for c in caixas]

    def dentro(c, pts):
        (x0, y0), (x1, y1) = c["caixa"]
        return all(x0 - folga <= p[0] <= x1 + folga and y0 - folga <= p[1] <= y1 + folga for p in pts)

    def chave_de(e):
        # o detalhamento marca cada entidade com a posição ou o conjunto da célula: é
        # o agrupamento exato; o resto (o que o usuário desenhou depois) vai pela caixa
        a = e.atributos or {}
        if a.get("detalhe") == "posicao" and a.get("posicao"):
            return ("posicao", a["posicao"])
        if a.get("detalhe") == "conjunto" and a.get("conjunto"):
            return ("conjunto", a["conjunto"])
        return None
    por_chave: Dict[tuple, dict] = {}
    for e in visiveis:
        pts = e.pontos()
        if not pts:
            continue
        chave = chave_de(e)
        alvo = por_chave.get(chave) if chave else None
        if alvo is None:
            alvo = next((c for c in celulas if dentro(c, pts)), None)
            if alvo is None:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                alvo = min(celulas, key=lambda c: math.hypot(
                    cx - (c["caixa"][0][0] + c["caixa"][1][0]) / 2, cy - (c["caixa"][0][1] + c["caixa"][1][1]) / 2))
            if chave and chave not in por_chave and alvo.get("chave") in (None, chave):
                alvo["chave"] = chave
                por_chave[chave] = alvo
        alvo["entidades"].append(e)
    celulas = [c for c in celulas if c["entidades"]]
    for c in celulas:                      # a caixa real do que caiu na célula
        c["caixa"] = _caixa_de(c["entidades"], float(desenho.escala or 1.0)) or c["caixa"]
        # título da célula: o texto mais alto dentro dela (o "P12 – 112x")
        textos = [e for e in c["entidades"] if isinstance(e, Texto)]
        if textos:
            c["titulo"] = max(textos, key=lambda t: t.altura).texto
    return celulas


# ============================================================ folha
def _moldura(d: Desenho, formato: str, info: dict, numero: int, total: int, escalas: Sequence[float]):
    larg, alt = FOLHAS[formato]
    m = MARGENS_A3 if formato in ("A3", "A4") else MARGENS
    cam = "PRANCHA"
    d.camadas[cam] = Camada2D(cam, "#111827", espessura=0.5)
    d.camadas["CARIMBO"] = Camada2D("CARIMBO", "#111827", espessura=0.25)
    atr = {"prancha": "moldura"}
    d.add(Polilinha(camada=cam, vertices=[(0, 0), (larg, 0), (larg, alt), (0, alt)], fechada=True, atributos=dict(atr)))
    x0, y0 = m["esquerda"], m["inferior"]
    x1, y1 = larg - m["direita"], alt - m["superior"]
    d.add(Polilinha(camada=cam, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=dict(atr)))
    # carimbo no canto inferior direito do quadro
    lc, ac = CARIMBO[formato]
    cx0, cy0 = x1 - lc, y0
    cy1 = cy0 + ac
    T = lambda x, y, t, h, **kw: d.add(Texto(camada="CARIMBO", posicao=(round(x, 2), round(y, 2)), texto=str(t), altura=h,   # noqa: E731
                                            atributos=dict(atr, campo=kw.get("campo", "")), alinhamento=kw.get("al", "esquerda")))
    L = lambda a, b: d.add(Linha(camada="CARIMBO", a=a, b=b, atributos=dict(atr)))    # noqa: E731
    d.add(Polilinha(camada=cam, vertices=[(cx0, cy0), (x1, cy0), (x1, cy1), (cx0, cy1)], fechada=True, atributos=dict(atr)))
    h_obs, h_rod, h_tit = ac * 0.13, ac * 0.29, ac * 0.25
    y_obs, y_rod, y_tit = cy0 + h_obs, cy0 + h_obs + h_rod, cy0 + h_obs + h_rod + h_tit
    for y in (y_obs, y_rod, y_tit):
        L((cx0, y), (x1, y))
    xc1, xc2 = cx0 + lc * 0.46, cx0 + lc * 0.72
    for x in (xc1, xc2):
        L((x, y_obs), (x, y_rod))
    k = ac / 65.0
    mg = 3.0
    h_top = cy1 - y_tit
    T(cx0 + mg, cy1 - 0.24 * h_top, "OBRA", 1.8 * k, campo="rotulo")
    obra = str(info.get("obra") or "")
    T(cx0 + mg, cy1 - 0.52 * h_top, obra[:60], (3.2 if len(obra) <= 40 else 2.5) * k, campo="obra")
    T(cx0 + mg, cy1 - 0.72 * h_top, "CLIENTE", 1.8 * k, campo="rotulo")
    T(cx0 + mg, cy1 - 0.95 * h_top, str(info.get("cliente") or "")[:58], 2.4 * k, campo="cliente")
    T(cx0 + mg, y_tit - 0.28 * h_tit, "TÍTULO DO DESENHO", 1.8 * k, campo="rotulo")
    T(cx0 + mg, y_tit - 0.62 * h_tit, str(info.get("titulo") or "")[:48], 3.0 * k, campo="titulo")
    if info.get("subtitulo"):
        T(cx0 + mg, y_tit - 0.92 * h_tit, str(info["subtitulo"])[:66], 2.0 * k, campo="subtitulo")
    esc_txt = ", ".join(texto_escala(e) for e in sorted(set(escalas))) or "—"
    if len(set(escalas)) > 1:
        esc_txt = "INDICADA (%s)" % esc_txt
    for x, rotulo, valor, extra, grande, campo in (
            (cx0, "RESPONSÁVEL TÉCNICO", str(info.get("responsavel") or "—")[:38], str(info.get("crea") or "CREA ____________")[:44], False, "responsavel"),
            (xc1, "ESCALA", esc_txt[:24], "DATA  " + str(info.get("data") or date.today().strftime("%d/%m/%Y")), False, "escala"),
            (xc2, "PRANCHA", "%02d/%02d" % (numero, total), "REV. " + str(info.get("revisao") or "00"), True, "prancha")):
        T(x + mg, y_rod - 0.24 * h_rod, rotulo, 1.7 * k, campo="rotulo")
        T(x + mg, y_rod - 0.55 * h_rod, valor, (3.4 if grande else 2.4) * k, campo=campo)
        T(x + mg, y_rod - 0.84 * h_rod, extra, 1.8 * k, campo=campo + "-extra")
    T(cx0 + mg, y_obs - 0.68 * h_obs, OBS_CARIMBO, 1.6 * k, campo="obs")
    return (x0, y0, x1, y1), (cx0, cy0, x1, cy1)


def _tabela_de_posicoes(d: Desenho, cels: Sequence[dict], quadro, carimbo_caixa):
    """Lista das posições da prancha (marca, quantidade, perfil, comprimento, peso) na
    faixa do rodapé, à esquerda do carimbo, em quantas colunas couberem."""
    linhas = []
    for c in cels:
        it = c.get("item")
        if not it or not c.get("marca"):
            continue
        comp = ("%d" % it["comprimento"]) if it.get("comprimento") else ("#%s" % it["espessura"] if it.get("espessura") else "")
        linhas.append((c["marca"], "%dx" % it.get("quantidade", 0), (it.get("perfil") or "")[:26], comp,
                       ("%.1f" % (it["peso"] * it.get("quantidade", 0))) if it.get("peso") else ""))
    if not linhas:
        return
    qx0, qy0, qx1, qy1 = quadro
    cx0, cy0, cx1, cy1 = carimbo_caixa
    x0, y0, x1, y1 = qx0, cy0, cx0, cy1
    h_linha = 3.2
    altura_txt = 1.8
    cabec = ("POS.", "QTD", "PERFIL / CHAPA", "COMPR.", "PESO kg")
    larguras = (14.0, 10.0, 46.0, 14.0, 14.0)
    larg_col = sum(larguras) + 6.0
    n_cols = max(1, int((x1 - x0 - 4.0) // larg_col))
    por_col = max(1, int((y1 - y0 - 4.0) // h_linha) - 1)
    cam = "CARIMBO"
    atr = {"prancha": "tabela"}
    d.add(Polilinha(camada="PRANCHA", vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=dict(atr)))
    total_cabe = n_cols * por_col
    if len(linhas) > total_cabe:
        linhas = linhas[:total_cabe - 1] + [("…", "", "e mais %d posição(ões): ver as células" % (len(linhas) - total_cabe + 1), "", "")]
    for ci in range(n_cols):
        bloco = linhas[ci * por_col:(ci + 1) * por_col]
        if not bloco:
            break
        bx = x0 + 3.0 + ci * larg_col
        y = y1 - 3.0
        for j, (rot, larg) in enumerate(zip(cabec, larguras)):
            xx = bx + sum(larguras[:j])
            d.add(Texto(camada=cam, posicao=(round(xx, 2), round(y - altura_txt, 2)), texto=rot, altura=altura_txt, atributos=dict(atr, campo="cabecalho")))
        d.add(Linha(camada=cam, a=(round(bx, 2), round(y - h_linha + 0.6, 2)), b=(round(bx + sum(larguras), 2), round(y - h_linha + 0.6, 2)), atributos=dict(atr)))
        y -= h_linha
        for linha in bloco:
            for j, (valor, larg) in enumerate(zip(linha, larguras)):
                xx = bx + sum(larguras[:j])
                d.add(Texto(camada=cam, posicao=(round(xx, 2), round(y - altura_txt, 2)), texto=str(valor), altura=altura_txt,
                            atributos=dict(atr, marca=linha[0])))
            y -= h_linha


def montar_pranchas(fontes: Sequence[dict], formato: str = "A1", carimbo: Optional[dict] = None,
                    titulo: str = "Prancha") -> List[Desenho]:
    """Monta as pranchas. `fontes`: [{nome, desenho (Desenho), escala (opcional)}].
    Devolve a lista de desenhos-prancha, já numerados."""
    if formato not in FOLHAS:
        raise ErroDeDados("formato de folha desconhecido: %s" % formato)
    carimbo = dict(carimbo or {})
    celulas = []
    for f in fontes:
        cs = celulas_de(f["desenho"], f["nome"])
        if f.get("chaves"):                      # só as posições/conjuntos pedidos
            pedidas = {str(k) for k in f["chaves"]}
            cs = [c for c in cs if (c.get("chave") and c["chave"][1] in pedidas) or c["titulo"] in pedidas]
        if f.get("escala"):
            for c in cs:
                c["escala"] = float(f["escala"])
        itens = (f["desenho"].metadados.get("detalhamento") or {}).get("itens") or {}
        for c in cs:
            if c.get("chave"):
                c["item"] = itens.get(c["chave"][1])
                c["marca"] = c["chave"][1]
        celulas.extend(cs)
    if not celulas:
        raise ErroDeDados("nenhum desenho com conteúdo para montar a prancha.")
    larg, alt = FOLHAS[formato]
    m = MARGENS_A3 if formato in ("A3", "A4") else MARGENS
    lc, ac = CARIMBO[formato]
    # área útil: o quadro menos a faixa do carimbo (a faixa inteira, para a prateleira
    # de baixo não invadir o carimbo)
    ux0, ux1 = m["esquerda"] + FOLGA, larg - m["direita"] - FOLGA
    uy0, uy1 = m["inferior"] + ac + FOLGA, alt - m["superior"] - FOLGA
    util_l, util_a = ux1 - ux0, uy1 - uy0

    # cada célula na sua escala; a que não cabe desce de escala
    itens = []
    for c in celulas:
        (bx0, by0), (bx1, by1) = c["caixa"]
        w_mod, h_mod = bx1 - bx0, by1 - by0
        k = c["escala"]
        if w_mod / k > util_l or (h_mod / k + FAIXA) > util_a:
            k = escala_normalizada(max(w_mod / util_l, h_mod / (util_a - FAIXA)))
            c["nota"] = "reduzida para %s para caber na folha" % texto_escala(k)
        c["k"] = k
        c["w"], c["h"] = w_mod / k, h_mod / k + FAIXA
        itens.append(c)

    # prateleiras: a ordem de chegada é a dos desenhos (grupo a grupo); dentro de uma
    # prateleira as células ficam alinhadas pelo canto inferior
    pranchas: List[List[dict]] = [[]]
    x, y_topo, alt_linha = ux0, uy1, 0.0
    fonte_atual = None
    for c in itens:
        # cada desenho de origem começa numa prateleira nova, para não misturar chapas
        # e barras na mesma linha
        if (x > ux0 and x + c["w"] > ux1) or (fonte_atual not in (None, c["fonte"]) and x > ux0):
            y_topo -= alt_linha + FOLGA
            x, alt_linha = ux0, 0.0
        if y_topo - c["h"] < uy0 and pranchas[-1]:    # nova prancha
            pranchas.append([])
            x, y_topo, alt_linha = ux0, uy1, 0.0
        c["px"], c["py"] = x, y_topo - c["h"]
        fonte_atual = c["fonte"]
        pranchas[-1].append(c)
        x += c["w"] + FOLGA
        alt_linha = max(alt_linha, c["h"])
    pranchas = [p for p in pranchas if p]
    total = len(pranchas)

    saida = []
    for i, cels in enumerate(pranchas, start=1):
        d = Desenho(nome="%s %02d" % (titulo, i), escala=1.0)
        fontes_da = sorted({c["fonte"] for c in cels})
        info = dict(carimbo)
        info.setdefault("titulo", fontes_titulo(cels))
        quadro, carimbo_caixa = _moldura(d, formato, info, i, total, [c["k"] for c in cels])
        _tabela_de_posicoes(d, cels, quadro, carimbo_caixa)
        for c in cels:
            (bx0, by0), (bx1, by1) = c["caixa"]
            dx = c["px"] - bx0 / c["k"]
            dy = c["py"] + FAIXA - by0 / c["k"]
            for e in c["entidades"]:
                d.add(_para_papel(e, c["k"], dx, dy, c["fonte"]))
            rot = "ESC. " + texto_escala(c["k"]) + ("  (%s)" % c["nota"] if c.get("nota") else "")
            d.add(Texto(camada="TEXTO", posicao=(round(c["px"], 2), round(c["py"] + 1.5, 2)), texto=rot, altura=2.0,
                        atributos={"prancha": "escala", "fonte": c["fonte"], "celula": c["titulo"]}))
        d.metadados["prancha"] = {"formato": formato, "numero": i, "total": total, "fontes": fontes_da,
                                  "quadro": [round(v, 2) for v in quadro], "carimbo": [round(v, 2) for v in carimbo_caixa],
                                  "celulas": [{"titulo": c["titulo"], "fonte": c["fonte"], "escala": c["k"],
                                               "caixa": [round(c["px"], 2), round(c["py"], 2), round(c["px"] + c["w"], 2), round(c["py"] + c["h"], 2)]}
                                              for c in cels]}
        saida.append(d)
    return saida


def fontes_titulo(cels: Sequence[dict]) -> str:
    nomes = []
    for c in cels:
        t = c.get("desenho_titulo") or c["fonte"]
        if t not in nomes:
            nomes.append(t)
    return ", ".join(nomes)[:48]
