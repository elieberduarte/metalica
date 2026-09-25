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
#: Folha, carimbo e margens seguem o modelo da fábrica (`nucleo2d/modelo_hermes.py`).
from nucleo2d import modelo_hermes as _modelo    # noqa: E402
MARGENS = MARGENS_A3 = _modelo.MARGENS
CARIMBO = {f: _modelo.carimbo_tamanho(f) for f in FOLHAS}
ESCALAS = (1, 2, 2.5, 5, 10, 15, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500)
#: Folga entre células e faixa do rótulo de escala sob cada uma (mm de papel).
FOLGA = 10.0
FAIXA = 7.0
#: Quadros por categoria: recuo das células dentro do quadro e altura da faixa do título.
QUADRO_MARGEM = 6.0
QUADRO_CABECALHO = 9.0


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


def _eh_moldura_de_origem(e: Entidade2D) -> bool:
    """Título ou moldura de quadro/faixa do desenho de origem: tem `faixa`/`quadro` nos
    atributos e não pertence a nenhuma posição ou conjunto (todas as entidades da faixa
    carregam `faixa`, mas as das células têm `detalhe`)."""
    a = e.atributos or {}
    return bool(a.get("quadro")) or (bool(a.get("faixa")) and not a.get("detalhe"))


def celulas_de(desenho: Desenho, nome: str) -> List[dict]:
    """Células de um desenho: as de `metadados.celulas` (detalhamento) ou o desenho inteiro.

    Cada célula: {fonte, titulo, escala, caixa, entidades}. Uma entidade pertence à
    célula que contém todos os seus pontos (com folga), e a que não pertence a nenhuma
    vai para a célula mais próxima."""
    # as molduras e títulos dos quadros do desenho de origem (faixa/quadro, camada
    # AUXILIAR) ficam de fora: a prancha tem os seus próprios quadros
    visiveis = [e for e in desenho.entidades.values()
                if not (desenho.camadas.get(e.camada) and not desenho.camadas[e.camada].visivel)
                and e.camada != "AUXILIAR" and not _eh_moldura_de_origem(e)]
    caixas = desenho.metadados.get("celulas") or []
    if not caixas or len(caixas) == 1:
        caixa = _caixa_de(visiveis, float(desenho.escala or 1.0))
        if caixa is None:
            return []
        unica = {"fonte": nome, "titulo": desenho.nome, "desenho_titulo": desenho.nome,
                 "escala": float(desenho.escala or 1.0), "caixa": caixa, "entidades": visiveis}
        # desenho de uma célula só (detalhe de uma peça, ou um grupo com uma posição):
        # a chave é a dessa posição/conjunto, para a tabela e o índice a listarem
        meta = desenho.metadados.get("detalhamento") or {}
        dp = desenho.metadados.get("detalhe_posicao") or {}
        posic = list(meta.get("posicoes") or []) or ([dp["marca"]] if dp.get("marca") else [])
        conjs = list(meta.get("conjuntos") or [])
        if len(posic) == 1 and not conjs:
            unica["chave"] = ("posicao", str(posic[0]))
        elif len(conjs) == 1 and not posic:
            unica["chave"] = ("conjunto", str(conjs[0]))
        return [unica]
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
def _moldura(d: Desenho, formato: str, info: dict, numero: int, total: int, escalas: Sequence[float],
             conteudo: Sequence[str] = ()):
    """Borda, quadro, dobras e carimbo do modelo da fábrica. `conteudo`: as linhas da caixa
    CONTEÚDO ("- TESOURAS: T1 (05x)…"). Devolve (quadro, carimbo) como caixas."""
    larg, alt = FOLHAS[formato]
    unicas = sorted(set(escalas))
    esc_txt = "INDICADA" if len(unicas) > 1 else (texto_escala(unicas[0]) if unicas else "-")
    return _modelo.desenhar_folha(d, formato, larg, alt, info, numero, total, esc_txt, conteudo)


def _conteudo_de(cels: Sequence[dict]) -> List[str]:
    """Linhas do CONTEÚDO: por categoria, os nomes com a quantidade — "- TESOURAS: T1 (05x), T2 (02x)";
    vistas e cortes pelo título do desenho."""
    por_cat: Dict[str, List[str]] = collections.OrderedDict()
    for c in cels:
        it = c.get("item") or {}
        cat = (it.get("categoria") or c.get("categoria") or "VISTAS").upper()
        nome = (it.get("nome") or c.get("marca") or c.get("desenho_titulo") or c["titulo"]).replace("Detalhamento – ", "")
        if it.get("quantidade"):
            nome = "%s (%02dx)" % (nome, it["quantidade"])
        por_cat.setdefault(cat, [])
        if nome not in por_cat[cat]:
            por_cat[cat].append(nome)
    return ["- %s: %s" % (cat, ", ".join(nomes)) for cat, nomes in por_cat.items()]


def _quadro(d: Desenho, mq: dict, x0: float, x1: float):
    """Moldura de um quadro de categoria com a faixa do título."""
    y0, y1 = mq["y0"], mq["y1"]
    atr = {"prancha": "quadro", "categoria": mq["categoria"]}
    d.add(Polilinha(camada="PRANCHA", vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=dict(atr)))
    yt = y1 - QUADRO_CABECALHO
    d.add(Linha(camada="PRANCHA", a=(x0, yt), b=(x1, yt), atributos=dict(atr)))
    d.add(Texto(camada="TEXTO", posicao=(round(x0 + 3.0, 2), round(yt + 2.6, 2)), texto=mq["titulo"].upper(), altura=4.0,
                atributos=dict(atr, campo="titulo")))


def montar_pranchas(fontes: Sequence[dict], formato: str = "A1", carimbo: Optional[dict] = None,
                    titulo: str = "Prancha", indice: bool = False) -> List[Desenho]:
    """Monta as pranchas. `fontes`: [{nome, desenho (Desenho), escala (opcional)}].
    Devolve a lista de desenhos-prancha, já numerados. Com `indice`, a prancha 01 é o
    índice: relação das pranchas e tabela de todas as posições/conjuntos com a prancha
    em que cada um está."""
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
    for i_c, c in enumerate(celulas):
        c["_ordem"] = i_c
    larg, alt = FOLHAS[formato]
    m = MARGENS
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
        larg_int = util_l - 2 * QUADRO_MARGEM
        alt_int = util_a - QUADRO_CABECALHO - 2 * FOLGA
        if w_mod / k > larg_int or (h_mod / k + FAIXA) > alt_int:
            k = escala_normalizada(max(w_mod / larg_int, h_mod / (alt_int - FAIXA)))
            c["nota"] = "reduzida para %s para caber na folha" % texto_escala(k)
        c["k"] = k
        c["w"], c["h"] = w_mod / k, h_mod / k + FAIXA
        itens.append(c)

    # quadros por categoria: as células de cada categoria formam prateleiras dentro de
    # um quadro com título; os quadros se empilham na folha e o que não cabe continua
    # na prancha seguinte, com o título "(continuação)"
    from nucleo2d.detalhar import CATEGORIAS
    ordem = {k: i for i, k in enumerate(CATEGORIAS)}
    for c in itens:
        c["categoria"] = (c.get("item") or {}).get("categoria") or ("VISTAS" if not c.get("marca") else "OUTROS")
    itens.sort(key=lambda c: (ordem.get(c["categoria"], 99), c.get("_ordem", 0)))
    qx0, qx1 = ux0 + QUADRO_MARGEM, ux1 - QUADRO_MARGEM
    quadros: List[dict] = []
    for cat in CATEGORIAS:
        cels = [c for c in itens if c["categoria"] == cat]
        if not cels:
            continue
        linhas: List[dict] = []
        x, atual = qx0, None
        for c in cels:
            if atual is None or x + c["w"] > qx1:
                atual = {"celulas": [], "h": 0.0}
                linhas.append(atual)
                x = qx0
            c["px_rel"] = x
            atual["celulas"].append(c)
            atual["h"] = max(atual["h"], c["h"])
            x += c["w"] + FOLGA
        quadros.append({"categoria": cat, "titulo": CATEGORIAS[cat], "linhas": linhas})

    pranchas: List[List[dict]] = [[]]
    molduras: List[List[dict]] = [[]]      # por prancha: {categoria, titulo, y0, y1}
    y_topo = uy1
    for q in quadros:
        continuacao = False
        aberto = None
        for linha in q["linhas"]:
            precisa = linha["h"] + FOLGA + (QUADRO_CABECALHO + FOLGA if aberto is None else 0.0)
            if y_topo - precisa < uy0 and (pranchas[-1] or aberto is not None):
                if aberto is not None:
                    aberto["y0"] = y_topo
                    aberto = None
                pranchas.append([])
                molduras.append([])
                y_topo = uy1
                continuacao = True
            if aberto is None:
                aberto = {"categoria": q["categoria"], "titulo": q["titulo"] + (" (continuação)" if continuacao else ""),
                          "y1": y_topo, "y0": None}
                molduras[-1].append(aberto)
                y_topo -= QUADRO_CABECALHO + FOLGA
            for c in linha["celulas"]:
                c["px"], c["py"] = c["px_rel"], y_topo - linha["h"]
                pranchas[-1].append(c)
            y_topo -= linha["h"] + FOLGA
        if aberto is not None:
            aberto["y0"] = y_topo
        y_topo -= FOLGA
    if not pranchas[-1]:
        pranchas.pop()
        molduras.pop()
    total = len(pranchas) + (1 if indice else 0)

    saida = []
    for i0, cels in enumerate(pranchas, start=1):
        i = i0 + (1 if indice else 0)
        d = Desenho(nome="%s %02d" % (titulo, i), escala=1.0)
        # as camadas dos desenhos de origem (cores por tipo de peça: banzos, diagonais…)
        for f in fontes:
            for k, cam in f["desenho"].camadas.items():
                d.camadas.setdefault(k, copy.deepcopy(cam))
        fontes_da = sorted({c["fonte"] for c in cels})
        info = dict(carimbo)
        info.setdefault("titulo", ", ".join(dict.fromkeys(mq["titulo"].replace(" (continuação)", "") for mq in molduras[i0 - 1]))[:48] or fontes_titulo(cels))
        quadro, carimbo_caixa = _moldura(d, formato, info, i, total, [c["k"] for c in cels], _conteudo_de(cels))
        for mq in molduras[i0 - 1]:
            _quadro(d, mq, ux0, ux1)
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
                                  "titulo": info.get("titulo", ""),
                                  "quadro": [round(v, 2) for v in quadro], "carimbo": [round(v, 2) for v in carimbo_caixa],
                                  "celulas": [{"titulo": c["titulo"], "fonte": c["fonte"], "escala": c["k"],
                                               "marca": c.get("marca"), "item": _item_resumido(c.get("item")),
                                               "caixa": [round(c["px"], 2), round(c["py"], 2), round(c["px"] + c["w"], 2), round(c["py"] + c["h"], 2)]}
                                              for c in cels]}
        saida.append(d)
    if indice:
        saida.insert(0, _prancha_indice(formato, carimbo, titulo, saida, total))
    return saida


def _item_resumido(it: Optional[dict]) -> Optional[dict]:
    if not it:
        return None
    return {k: it.get(k) for k in ("nome", "quantidade", "perfil", "comprimento", "espessura", "peso", "classe", "categoria") if k in it}


def _prancha_indice(formato: str, carimbo: dict, titulo: str, pranchas: Sequence[Desenho], total: int) -> Desenho:
    """Prancha 01: relação das pranchas (número e conteúdo) e a tabela de todas as
    posições e conjuntos — nome, marca, quantidade, perfil, comprimento e a prancha em
    que cada um está desenhado —, em ordem de nome, em quantas colunas couberem."""
    from saida.detalhamento import _ordem_natural
    d = Desenho(nome="%s 01" % titulo, escala=1.0)
    info = dict(carimbo)
    info["titulo"] = "Índice"
    quadro, carimbo_caixa = _moldura(d, formato, info, 1, total, [], ["- ÍNDICE DE PRANCHAS E POSIÇÕES"])
    qx0, qy0, qx1, qy1 = quadro
    cx0, cy0, cx1, cy1 = carimbo_caixa
    cam = "CARIMBO"
    atr = {"prancha": "indice"}
    y = qy1 - 8.0
    d.add(Texto(camada=cam, posicao=(round(qx0 + 6.0, 2), round(y, 2)), texto="ÍNDICE DE PRANCHAS E POSIÇÕES", altura=5.0, atributos=dict(atr, campo="titulo")))
    y -= 9.0
    # relação das pranchas
    for p in pranchas:
        pr = p.metadados.get("prancha") or {}
        d.add(Texto(camada=cam, posicao=(round(qx0 + 6.0, 2), round(y, 2)),
                    texto="Prancha %02d/%02d — %s  (%d vista(s))" % (pr.get("numero", 0), total, pr.get("titulo") or "", len(pr.get("celulas") or [])),
                    altura=2.5, atributos=dict(atr, campo="prancha")))
        y -= 4.2
    y -= 4.0
    # tabela de posições/conjuntos: nome, marca, qtd, perfil, compr., prancha
    linhas = []
    vistos = set()
    for p in pranchas:
        pr = p.metadados.get("prancha") or {}
        for c in pr.get("celulas") or []:
            it, marca = c.get("item"), c.get("marca")
            if not it or not marca or marca in vistos:
                continue
            vistos.add(marca)
            comp = ("%d" % it["comprimento"]) if it.get("comprimento") else ("#%s" % it["espessura"] if it.get("espessura") else "")
            marca_txt = marca if len(marca) <= 14 else marca[:13] + "…"
            linhas.append(((it.get("nome") or marca)[:16], marca_txt, "%dx" % (it.get("quantidade") or 0), (it.get("perfil") or "")[:30], comp, "%02d" % pr.get("numero", 0)))
    linhas.sort(key=lambda r: (_ordem_natural(r[0]), _ordem_natural(r[1])))
    cabec = ("NOME", "MARCA", "QTD", "PERFIL / CHAPA / CONJUNTO", "COMPR.", "PRANCHA")
    larguras = (26.0, 20.0, 10.0, 56.0, 16.0, 16.0)
    h_linha, altura_txt = 3.6, 2.0
    larg_col = sum(larguras) + 8.0
    x0, x1 = qx0 + 6.0, qx1 - 6.0
    y_fundo = max(qy0, cy1) + 6.0
    n_cols = max(1, int((x1 - x0) // larg_col))
    por_col = max(1, int((y - y_fundo) // h_linha) - 1)
    if len(linhas) > n_cols * por_col:
        linhas = linhas[:n_cols * por_col - 1] + [("…", "", "", "e mais %d item(ns): ver as pranchas" % (len(linhas) - n_cols * por_col + 1), "", "")]
    for ci in range(n_cols):
        bloco = linhas[ci * por_col:(ci + 1) * por_col]
        if not bloco:
            break
        bx = x0 + ci * larg_col
        yy = y
        for j, (rot, larg) in enumerate(zip(cabec, larguras)):
            d.add(Texto(camada=cam, posicao=(round(bx + sum(larguras[:j]), 2), round(yy - altura_txt, 2)), texto=rot, altura=altura_txt, atributos=dict(atr, campo="cabecalho")))
        d.add(Linha(camada=cam, a=(round(bx, 2), round(yy - h_linha + 0.6, 2)), b=(round(bx + sum(larguras), 2), round(yy - h_linha + 0.6, 2)), atributos=dict(atr)))
        yy -= h_linha
        for linha in bloco:
            for j, (txt, larg) in enumerate(zip(linha, larguras)):
                if txt:
                    d.add(Texto(camada=cam, posicao=(round(bx + sum(larguras[:j]), 2), round(yy - altura_txt, 2)), texto=str(txt), altura=altura_txt, atributos=dict(atr, campo="linha")))
            yy -= h_linha
    d.metadados["prancha"] = {"formato": formato, "numero": 1, "total": total, "fontes": [], "titulo": "Índice", "indice": True,
                              "quadro": [round(v, 2) for v in quadro], "carimbo": [round(v, 2) for v in carimbo_caixa], "celulas": []}
    return d


def fontes_titulo(cels: Sequence[dict]) -> str:
    nomes = []
    for c in cels:
        t = c.get("desenho_titulo") or c["fonte"]
        if t not in nomes:
            nomes.append(t)
    return ", ".join(nomes)[:48]


# ============================================================ PDF
#: Relação entre a altura de texto do DXF (mm) e o corpo da fonte em pontos no
#: renderizador (`dxf_render` monta o corpo como altura · fator · 2,4). Igual à de
#: saida/pranchas.py.
_FATOR_TEXTO = (2.835 / 0.73) / 2.4


def _preencher_solidas(d: Desenho, ax):
    """Hachuras sólidas (o logo do carimbo) preenchidas de verdade — o DXF de linhas do
    renderizador só tem traços; os contornos internos são furos (regra par-ímpar)."""
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch
    for e in d.entidades.values():
        if not isinstance(e, Hachura) or e.padrao != "solido":
            continue
        cam = d.camadas.get(e.camada)
        cor = cam.cor if cam is not None else "#111827"
        verts, codes = [], []
        for c in e.contornos:
            if len(c) < 3:
                continue
            verts += list(c) + [c[0]]
            codes += [Path.MOVETO] + [Path.LINETO] * (len(c) - 1) + [Path.CLOSEPOLY]
        if verts:
            ax.add_patch(PathPatch(Path(verts, codes), facecolor=cor, edgecolor="none", zorder=5))


def pdf_dos_desenhos(desenhos: Sequence[Desenho], caminho_pdf: str, margem: float = 10.0) -> str:
    """PDF vetorial, uma página por desenho, no tamanho real do papel.

    Prancha (escala 1, `metadados.prancha`) sai na folha do seu formato; qualquer outro
    desenho sai numa página do tamanho do desenho na sua escala mais a margem, e o texto
    com a altura de papel que o CAD mostra. É o `para_dxf` de cada desenho renderizado
    pelo `saida.dxf_render`, o mesmo do memorial, num eixo cujo intervalo de dados é o
    tamanho da página vezes a escala — 1 mm no papel é 1 mm impresso."""
    import os
    import tempfile
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from saida import dxf_render
    os.makedirs(os.path.dirname(os.path.abspath(caminho_pdf)), exist_ok=True)
    with PdfPages(caminho_pdf) as pdf, tempfile.TemporaryDirectory() as tmp:
        for i, d in enumerate(desenhos):
            info = d.metadados.get("prancha")
            if info and info.get("formato") in FOLHAS:
                larg, alt = FOLHAS[info["formato"]]
                k = 1.0
                x0, y0 = 0.0, 0.0
            else:
                k = float(d.escala or 1.0)
                caixa = d.caixa()
                if not caixa:
                    continue
                (bx0, by0), (bx1, by1) = caixa
                larg = (bx1 - bx0) / k + 2 * margem
                alt = (by1 - by0) / k + 2 * margem
                x0, y0 = bx0 - margem * k, by0 - margem * k
            # texto como está no desenho: o PDF não passa pelo ASCII do DXF R12 ("dobra 12,5°",
            # "TERÇAS" e "…" saíam "dobra 12,5 ", "TERCAS" e "?")
            arq = d.para_dxf(k, texto_unicode=True).gravar(os.path.join(tmp, "p%d.dxf" % i))
            fig = plt.figure(figsize=(larg / 25.4, alt / 25.4))
            ax = fig.add_axes((0, 0, 1, 1))
            # as camadas por tipo de peça (banzos, diagonais…) saem na cor delas, como no CAD
            from nucleo2d.detalhe.base import CAMADAS_PECAS
            cores = {n: (d.camadas[n].cor if n in d.camadas else c) for n, (c, _e) in CAMADAS_PECAS.items()}
            dxf_render.desenhar(arq, ax, escala_texto=_FATOR_TEXTO / k, cores=cores)
            _preencher_solidas(d, ax)
            ax.set_xlim(x0, x0 + larg * k)
            ax.set_ylim(y0, y0 + alt * k)
            ax.set_aspect("equal")
            ax.axis("off")
            pdf.savefig(fig)
            plt.close(fig)
    return caminho_pdf
