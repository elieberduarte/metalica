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
import re
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import (Desenho, Entidade2D, Linha, Polilinha, Circulo, Arco, Texto,
                              Cota, Hachura, Chamada, Camada2D, formatar_mm, transladar, novo_id)

__all__ = ["montar_pranchas", "juntar_pranchas", "FOLHAS", "CARIMBO", "texto_escala"]

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
#: Folga entre as folhas postas lado a lado no desenho único das pranchas (mm de papel).
FOLGA_ENTRE_FOLHAS = 40.0


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
            n.texto = formatar_mm(n.valor(), n.casas)
        n.p1, n.p2 = mv(n.p1), mv(n.p2)
    elif isinstance(n, Hachura):
        n.contornos = [[mv(p) for p in c] for c in n.contornos]
    elif isinstance(n, Chamada):
        n.alvo, n.posicao = mv(n.alvo), mv(n.posicao)
    n.atributos = dict(n.atributos or {}, fonte=fonte, escala=k)
    return n


def _pontos_da_cota(c: Cota, k: float) -> List[Ponto2]:
    """A linha de cota (deslocada dos pontos medidos por `deslocamento` mm de papel) e a faixa
    do número acima dela: o que a cota ocupa de verdade no desenho. Só com os pontos medidos, a
    cadeia de cotas sob a terça saía da caixa da célula e invadia o título da linha de baixo da
    prancha (revisão de 28/09)."""
    x1, y1 = c.p1
    x2, y2 = c.p2
    if c.modo == "h":
        y2 = y1
    elif c.modo == "v":
        x2 = x1
    dx, dy = x2 - x1, y2 - y1
    comp = math.hypot(dx, dy)
    if comp < 1e-9:
        return [c.p1, c.p2]
    nx, ny = -dy / comp, dx / comp
    desl = c.deslocamento * k
    sg = 1.0 if desl >= 0 else -1.0
    alem = desl + sg * (2.0 + c.altura + 1.0) * k          # a linha passa 2 mm; o número fica em cima
    pts = [(x1 + nx * desl, y1 + ny * desl), (x2 + nx * desl, y2 + ny * desl),
           (x1 + nx * alem, y1 + ny * alem), (x2 + nx * alem, y2 + ny * alem)]
    if c.texto_pos:
        pts.append(c.texto_pos)
    return pts


def _caixa_de(ents: Sequence[Entidade2D], escala: float = 1.0) -> Optional[Tuple[Ponto2, Ponto2]]:
    """Caixa das entidades; um texto ocupa a largura estimada (0,75 × altura × caracteres,
    em mm de modelo pela escala), senão o título "P12 – 112x" sai da célula na folha; a cota,
    a linha de cota e o número dela."""
    pts = []
    for e in ents:
        if isinstance(e, Cota):
            pts += e.pontos() + _pontos_da_cota(e, escala)
        elif isinstance(e, Texto) and e.angulo == 0.0:
            larg = 0.75 * e.altura * escala * len(e.texto or "")
            x, y = e.posicao
            x0 = x - larg / 2 if e.alinhamento == "centro" else x - larg if e.alinhamento == "direita" else x
            pts += [(x0, y), (x0 + larg, y + e.altura * escala)]
        elif type(e).__name__ == "Chamada":
            # a chamada vai da seta até o fim do texto (o texto sai do lado de fora do alvo):
            # sem a largura dele, a célula vizinha era posta em cima das chamadas de parafuso
            larg = 0.75 * e.altura * escala * len(e.texto or "") + 10.0 * escala
            (xa, ya), (xt, yt) = e.alvo, e.posicao
            xf = xt + larg if xt >= xa else xt - larg
            pts += [e.alvo, e.posicao, (xf, yt + e.altura * escala)]
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
                    # o quadro já começou numa prancha anterior: o da próxima é "(continuação)" — o
                    # que só não cabe na prancha de antes e abre a próxima não é (revisão de 28/09)
                    aberto["y0"] = y_topo
                    aberto = None
                    continuacao = True
                pranchas.append([])
                molduras.append([])
                y_topo = uy1
            if aberto is None:
                aberto = {"categoria": q["categoria"], "titulo": q["titulo"] + (" (continuação)" if continuacao else ""),
                          "y1": y_topo, "y0": None}
                molduras[-1].append(aberto)
                y_topo -= QUADRO_CABECALHO + FOLGA
            for c in linha["celulas"]:
                # as células da prateleira alinhadas pelo topo: os títulos numa linha só (a de baixo
                # deixava a peça de célula mais alta flutuando acima das vizinhas — revisão de 28/09)
                c["px"], c["py"] = c["px_rel"], y_topo - c["h"]
                pranchas[-1].append(c)
            y_topo -= linha["h"] + FOLGA
        if aberto is not None:
            aberto["y0"] = y_topo
        y_topo -= FOLGA
    if not pranchas[-1]:
        pranchas.pop()
        molduras.pop()
    total = len(pranchas)

    saida = []
    for i0, cels in enumerate(pranchas, start=1):
        i = i0
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
        d.metadados["prancha"]["conteudo"] = _conteudo_de(cels)
        saida.append(d)
    if indice and saida:
        _relacao_na_faixa(saida[0], formato, saida)
    return saida


def juntar_pranchas(pranchas: Sequence[Desenho], nome: str = "Pranchas", folga: float = FOLGA_ENTRE_FOLHAS) -> Desenho:
    """Um desenho só com todas as pranchas lado a lado, em papel 1:1 (pedido do usuário, 28/09:
    as pranchas "uma do lado da outra no mesmo ambiente, sem abas separadas"). Cada folha fica em
    `metadados.pranchas` com a origem dela (o canto de baixo à esquerda) e o que a prancha solta
    tinha em `metadados.prancha`; a moldura e o carimbo levam `folha` (o clique na borda pega a
    folha inteira, e o carimbo edita como na folha do desenho de trabalho) e todas as entidades
    levam `prancha_numero`. O PDF sai uma página por folha (`pdf_dos_desenhos`)."""
    out = Desenho(nome=nome, escala=1.0)
    lista = []
    x = 0.0
    for p in pranchas:
        info = dict(p.metadados.get("prancha") or {})
        formato = info.get("formato") if info.get("formato") in FOLHAS else "A1"
        larg, alt = FOLHAS[formato]
        for k, cam in p.camadas.items():
            out.camadas.setdefault(k, copy.deepcopy(cam))
        ident = "folha-" + Entidade2D().id
        numero = int(info.get("numero") or len(lista) + 1)
        for e in p.entidades.values():
            n = transladar(e, x, 0.0)
            n.id = Entidade2D().id
            a = dict(n.atributos or {}, prancha_numero=numero)
            if a.get("prancha") == "moldura":
                a.update(folha=ident, formato=formato, escala=1.0, titulo=str(info.get("titulo") or ""))
            n.atributos = a
            out.add(n)
        for chave in ("quadro", "carimbo"):
            if info.get(chave):
                info[chave] = [round(v + (x if i % 2 == 0 else 0.0), 2) for i, v in enumerate(info[chave])]
        for c in info.get("celulas") or []:
            if c.get("caixa"):
                c["caixa"] = [round(v + (x if i % 2 == 0 else 0.0), 2) for i, v in enumerate(c["caixa"])]
        info.update(numero=numero, folha=ident, origem=[round(x, 2), 0.0], tamanho=[larg, alt], nome=p.nome)
        lista.append(info)
        x += larg + folga
    out.metadados["pranchas"] = lista
    out.metadados["formato"] = lista[0]["formato"] if lista else "A1"
    return out


def paginas_de(d: Desenho, margem: float = 10.0) -> List[tuple]:
    """As páginas de um desenho no PDF: (largura, altura, k, x0, y0) em mm de papel e mm do desenho.
    O desenho único das pranchas dá uma página por folha; a prancha solta, a folha do formato; o
    desenho comum, uma página do tamanho dele na sua escala mais a margem."""
    folhas = d.metadados.get("pranchas")
    if folhas:
        out = []
        for f in folhas:
            if f.get("formato") in FOLHAS:
                larg, alt = FOLHAS[f["formato"]]
                o = f.get("origem") or [0.0, 0.0]
                out.append((larg, alt, 1.0, float(o[0]), float(o[1])))
        return out
    info = d.metadados.get("prancha")
    if info and info.get("formato") in FOLHAS:
        larg, alt = FOLHAS[info["formato"]]
        return [(larg, alt, 1.0, 0.0, 0.0)]
    k = float(d.escala or 1.0)
    caixa = d.caixa()
    if not caixa:
        return []
    (bx0, by0), (bx1, by1) = caixa
    return [((bx1 - bx0) / k + 2 * margem, (by1 - by0) / k + 2 * margem, k, bx0 - margem * k, by0 - margem * k)]


def _por_folha(d: Desenho) -> List[Desenho]:
    """O desenho das pranchas lado a lado repartido por folha, na ordem de `metadados.pranchas`:
    pelo `prancha_numero` das entidades; o que não tem (acrescentado à mão no CAD) vai pela folha
    em que o centro dele cai."""
    folhas = [f for f in d.metadados.get("pranchas") or [] if f.get("formato") in FOLHAS]
    partes, caixas = [], []
    for f in folhas:
        p = Desenho(nome=d.nome, escala=d.escala)
        p.camadas.update(copy.deepcopy(d.camadas))
        partes.append(p)
        larg, alt = FOLHAS[f["formato"]]
        o = f.get("origem") or [0.0, 0.0]
        caixas.append((float(o[0]), float(o[1]), float(o[0]) + larg, float(o[1]) + alt))
    por_num = {int(f.get("numero") or 0): i for i, f in enumerate(folhas)}
    for e in d.entidades.values():
        n = (e.atributos or {}).get("prancha_numero")
        i = por_num.get(int(n)) if n is not None else None
        if i is None:
            pts = e.pontos()
            if not pts:
                continue
            cx = sum(q[0] for q in pts) / len(pts)
            cy = sum(q[1] for q in pts) / len(pts)
            i = next((j for j, (x0, y0, x1, y1) in enumerate(caixas)
                      if x0 - 1e-6 <= cx <= x1 + 1e-6 and y0 - 1e-6 <= cy <= y1 + 1e-6), None)
            if i is None:
                continue
        partes[i].add(e)
    return partes


def _item_resumido(it: Optional[dict]) -> Optional[dict]:
    if not it:
        return None
    return {k: it.get(k) for k in ("nome", "quantidade", "perfil", "comprimento", "espessura", "peso", "classe", "categoria") if k in it}


#: Largura média de uma letra em relação à altura (a mesma estimativa da caixa das células).
LARGURA_LETRA = 0.75
#: Siglas das telhas (os nomes vêm do código da telha no modelo, não do tipo de peça).
SIGLAS_TELHA = [("TMD", "Telha multi-dobra"), ("MD", "Telha multi-dobra"), ("CM", "Cumeeira"), ("CU", "Cumeeira"),
                ("TL", "Telha")]


def siglas_da_fabrica() -> List[Tuple[str, str]]:
    """(sigla, o que é) da nomenclatura da fábrica (base.PREFIXO_NOME): uma linha por sigla; as chapas
    (suporte de terça, de agulhamento, de contraventamento, castanha) numa só."""
    from nucleo2d.detalhe.base import PREFIXO_NOME, TIPOS_NOME
    por = collections.OrderedDict()
    for tipo, sigla in PREFIXO_NOME.items():
        if not sigla:
            continue
        por.setdefault(sigla, []).append(TIPOS_NOME.get(tipo, tipo))
    fora = []
    for sigla, nomes in por.items():
        if sigla == "CH":
            txt = "Chapa (suportes e castanhas)"
        elif sigla == "DP.":
            txt = "Dispositivo (conjunto menor)"
        elif sigla == "T":
            txt = "Tesoura (T1 + T1: as duas metades)"
        else:
            txt = nomes[0]
        fora.append((sigla, txt))
    return fora + [x for x in SIGLAS_TELHA if x[0] not in por]


def siglas_usadas(nomes: Sequence[str]) -> List[Tuple[str, str]]:
    """As siglas que aparecem nos nomes ("A.D.1 / A.D.2", "T1 + T1", "CH4", "TMD.1"…), na ordem da tabela:
    a sigla mais longa que começa o nome e é seguida de número (T.C.1 é terça de cobertura, não tesoura)."""
    tabela = siglas_da_fabrica()
    ordem = sorted(tabela, key=lambda x: -len(x[0]))
    achadas = set()
    for nome in nomes:
        for parte in re.split(r"\s*(?:/|\+)\s*", str(nome or "")):
            parte = parte.strip()
            for sigla, _t in ordem:
                if parte.startswith(sigla) and re.match(r"\.?\d", parte[len(sigla):len(sigla) + 2] or ""):
                    achadas.add(sigla)
                    break
    return [x for x in tabela if x[0] in achadas]


def _relacao_na_faixa(d: Desenho, formato: str, pranchas: Sequence[Desenho]):
    """A relação das pranchas na faixa livre ao lado do carimbo da primeira prancha (pedido do usuário,
    28/09: "tem esse espaço inutilizado em baixo das pranchas … usaria ele para trazer o índice na
    primeira prancha"), no lugar da folha de índice separada: número/total, o título e o conteúdo de
    cada uma, em quantas colunas precisar. A tabela das posições fica na lista de materiais."""
    larg, alt = FOLHAS[formato]
    m = MARGENS
    lc, ac = CARIMBO[formato]
    x0, x1 = m["esquerda"] + FOLGA, larg - m["direita"] - lc - FOLGA
    y_topo, y_fundo = m["inferior"] + ac - 3.0, m["inferior"] + FOLGA * 0.6
    atr = {"prancha": "relacao"}
    h_tit, h, passo = 3.5, 2.2, 3.8
    # as siglas que aparecem nas pranchas, num bloco à direita da relação (pedido do usuário, 28/09:
    # "no índice deveria ter um campo onde explique o que significa cada uma das siglas")
    nomes = []
    for p in pranchas:
        for c in (p.metadados.get("prancha") or {}).get("celulas") or []:
            nomes += [c.get("titulo") or "", ((c.get("item") or {}).get("nome") or "")]
    siglas = siglas_usadas(nomes)
    if siglas:
        por_col_s = max(1, int((y_topo - h_tit - 3.0 - y_fundo) // passo))
        n_col_s = -(-len(siglas) // por_col_s)
        larg_col_s = LARGURA_LETRA * h * (max(len(x[0]) for x in siglas) + max(len(x[1]) for x in siglas)) + 9.0
        larg_s = min(n_col_s * larg_col_s, 0.45 * (x1 - x0))
        larg_col_s = larg_s / n_col_s
        xs = x1 - larg_s
        d.add(Texto(camada="TEXTO", posicao=(round(xs, 2), round(y_topo - h_tit, 2)), texto="SIGLAS",
                    altura=h_tit, atributos=dict(atr, campo="titulo_siglas")))
        # a sigla numa coluna e o que ela é noutra, alinhada (lê como tabela)
        larg_sig = LARGURA_LETRA * h * max(len(x[0]) for x in siglas) + 3.0
        cabe_s = max(8, int((larg_col_s - larg_sig - 3.0) / (LARGURA_LETRA * h)))
        for i, (sigla, txt) in enumerate(siglas):
            col, lin = divmod(i, por_col_s)
            if len(txt) > cabe_s:
                txt = txt[:cabe_s - 1].rstrip(" ,;(") + "…"
            y_ = round(y_topo - h_tit - 3.0 - (lin + 1) * passo + (passo - h), 2)
            x_ = xs + col * larg_col_s
            d.add(Texto(camada="TEXTO", posicao=(round(x_, 2), y_), texto=sigla, altura=h, atributos=dict(atr, campo="sigla")))
            d.add(Texto(camada="TEXTO", posicao=(round(x_ + larg_sig, 2), y_), texto=txt, altura=h,
                        atributos=dict(atr, campo="sigla_texto")))
        x1 = xs - 8.0                                              # a relação fica à esquerda
    d.add(Texto(camada="TEXTO", posicao=(round(x0, 2), round(y_topo - h_tit, 2)), texto="RELAÇÃO DAS PRANCHAS",
                altura=h_tit, atributos=dict(atr, campo="titulo")))
    linhas = []
    for p in pranchas:
        pr = p.metadados.get("prancha") or {}
        conteudo = "; ".join(t.lstrip("- ") for t in pr.get("conteudo") or []) or str(pr.get("titulo") or "")
        linhas.append("%02d/%02d  %s" % (pr.get("numero", 0), pr.get("total", len(pranchas)), conteudo))
    y_ini = y_topo - h_tit - 3.0
    por_col = max(1, int((y_ini - y_fundo) // passo))
    n_col = max(1, -(-len(linhas) // por_col))
    larg_col = (x1 - x0) / n_col
    cabe = max(12, int((larg_col - 4.0) / (LARGURA_LETRA * h)))           # caracteres que cabem na coluna
    for i, txt in enumerate(linhas):
        col, lin = divmod(i, por_col)
        if len(txt) > cabe:
            txt = txt[:cabe - 1].rstrip(" ,;") + "…"
        d.add(Texto(camada="TEXTO", posicao=(round(x0 + col * larg_col, 2), round(y_ini - (lin + 1) * passo + (passo - h), 2)),
                    texto=txt, altura=h, atributos=dict(atr, campo="prancha")))
    d.metadados["prancha"]["relacao"] = True
    d.metadados["prancha"]["siglas"] = [x[0] for x in siglas]


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
    from nucleo2d.detalhe.base import CAMADAS_PECAS
    with PdfPages(caminho_pdf) as pdf, tempfile.TemporaryDirectory() as tmp:
        for i, d in enumerate(desenhos):
            paginas = paginas_de(d, margem)
            if not paginas:
                continue
            # as camadas por tipo de peça (banzos, diagonais…) saem na cor delas, como no CAD
            cores = {n: (d.camadas[n].cor if n in d.camadas else c) for n, (c, _e) in CAMADAS_PECAS.items()}
            # o desenho das pranchas lado a lado: uma página por folha, cada uma renderizando só o que
            # é dela (as 12 folhas da Sala inteiras, 12 vezes, levavam 5 min)
            partes = _por_folha(d) if d.metadados.get("pranchas") else [d]
            for j, ((larg, alt, k, x0, y0), parte) in enumerate(zip(paginas, partes)):
                # texto como está no desenho: o PDF não passa pelo ASCII do DXF R12 ("dobra 12,5°",
                # "TERÇAS" e "…" saíam "dobra 12,5 ", "TERCAS" e "?")
                arq = parte.para_dxf(k, texto_unicode=True).gravar(os.path.join(tmp, "p%d_%d.dxf" % (i, j)))
                fig = plt.figure(figsize=(larg / 25.4, alt / 25.4))
                ax = fig.add_axes((0, 0, 1, 1))
                dxf_render.desenhar(arq, ax, escala_texto=_FATOR_TEXTO / k, cores=cores)
                _preencher_solidas(parte, ax)
                ax.set_xlim(x0, x0 + larg * k)
                ax.set_ylim(y0, y0 + alt * k)
                ax.set_aspect("equal")
                ax.axis("off")
                pdf.savefig(fig)
                plt.close(fig)
    return caminho_pdf


# ============================================================ folhas no desenho de trabalho
# O caminho manual: a folha (borda, quadro, dobras e carimbo) entra no próprio desenho de
# detalhamento, ampliada pela escala dele; o usuário move ou copia os detalhes para dentro
# dela com as ferramentas do CAD, e cada folha posicionada vira depois uma prancha em papel.

def _do_papel(e: Entidade2D, k: float, ox: float, oy: float, atr: dict) -> Entidade2D:
    """o inverso de `_para_papel`: do mm de papel para o mm do desenho (× k, a partir de ox, oy);
    o que é de papel (altura de texto, afastamentos) fica como está"""
    n = copy.deepcopy(e)
    n.id = Entidade2D().id
    mv = lambda p: (round(p[0] * k + ox, 3), round(p[1] * k + oy, 3))    # noqa: E731
    if isinstance(n, Linha):
        n.a, n.b = mv(n.a), mv(n.b)
    elif isinstance(n, Polilinha):
        n.vertices = [mv(p) for p in n.vertices]
    elif isinstance(n, (Circulo, Arco)):
        n.centro = mv(n.centro)
        n.raio = round(n.raio * k, 4)
    elif isinstance(n, Texto):
        n.posicao = mv(n.posicao)
    elif isinstance(n, Hachura):
        n.contornos = [[mv(p) for p in c] for c in n.contornos]
    n.atributos = dict(n.atributos or {}, **atr)
    return n


def folha_no_desenho(formato: str, escala: float, origem: Ponto2, carimbo: Optional[dict] = None,
                     titulo: str = "", numero: int = 1, total: int = 1) -> Desenho:
    """A folha para o desenho de trabalho, com o canto de baixo à esquerda em `origem` (mm do
    desenho) e ampliada pela `escala` dele. Todas as linhas levam `folha` (o id: o clique pega a
    folha inteira), o formato e a escala. Devolve um Desenho só com ela."""
    if formato not in FOLHAS:
        raise ErroDeDados("formato de folha desconhecido: %s" % formato)
    k = float(escala or 1.0)
    larg, alt = FOLHAS[formato]
    papel = Desenho(nome="folha", escala=1.0)
    info = dict(carimbo or {})
    if titulo:
        info["titulo"] = titulo
    quadro, carimbo_cx = _modelo.desenhar_folha(papel, formato, larg, alt, info, numero, total, texto_escala(k), [])
    ident = "folha-" + Entidade2D().id
    atr = {"folha": ident, "formato": formato, "escala": k, "titulo": titulo}
    out = Desenho(nome="folha", escala=k)
    out.camadas.update(copy.deepcopy(papel.camadas))
    for e in papel.entidades.values():
        out.add(_do_papel(e, k, origem[0], origem[1], atr))
    out.metadados["folha"] = {"id": ident, "formato": formato, "escala": k, "origem": [origem[0], origem[1]],
                              "tamanho": [larg * k, alt * k],
                              "quadro": [round(v * k + (origem[0] if i % 2 == 0 else origem[1]), 1) for i, v in enumerate(quadro)]}
    return out


def _folhas_do(desenho: Desenho) -> List[dict]:
    """as folhas posicionadas no desenho: {id, formato, escala, titulo, caixa (mm do desenho)}"""
    por = collections.OrderedDict()
    for e in desenho.entidades.values():
        a = e.atributos or {}
        if a.get("folha"):
            # a folha copiada (Copiar do CAD) tem o mesmo id e outro grupo de cópia: é outra folha
            por.setdefault("%s|%s" % (a["folha"], a.get("grupo_copia") or ""), []).append(e)
    out = []
    for ident, ents in por.items():
        a = ents[0].atributos
        formato = a.get("formato") if a.get("formato") in FOLHAS else "A1"
        k = float(a.get("escala") or desenho.escala or 1.0)
        # o canto da folha: a borda externa (a polilinha de moldura com o maior contorno)
        pts = [p for e in ents if isinstance(e, Polilinha) for p in e.vertices]
        if not pts:
            continue
        x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
        larg, alt = FOLHAS[formato]
        out.append({"id": ident, "formato": formato, "escala": k, "titulo": a.get("titulo") or "",
                    "caixa": (x0, y0, x0 + larg * k, y0 + alt * k), "entidades": ents})
    # a ordem de leitura: de cima para baixo, da esquerda para a direita
    out.sort(key=lambda f: (-round(f["caixa"][3] / 1000.0), f["caixa"][0]))
    return out


def pranchas_das_folhas(desenho: Desenho, fonte: str, carimbo: Optional[dict] = None, titulo: str = "Prancha",
                        primeira: int = 1, total: Optional[int] = None) -> List[Desenho]:
    """Cada folha posicionada no desenho vira uma prancha em papel 1:1: a folha redesenhada (o número
    e o total da vez) e tudo o que está inteiro dentro da borda dela, reduzido pela escala."""
    folhas = _folhas_do(desenho)
    if not folhas:
        raise ErroDeDados("o desenho não tem folhas: use Desenho → Inserir folha (prancha)… e ponha os detalhes dentro dela.")
    total = total or (primeira - 1 + len(folhas))
    carimbo = dict(carimbo or {})
    de_folha = {e.id for f in folhas for e in f["entidades"]}
    soltas = [e for e in desenho.entidades.values() if e.id not in de_folha]
    saida = []
    for i, f in enumerate(folhas):
        n = primeira + i
        x0, y0, x1, y1 = f["caixa"]
        k = f["escala"]
        d = Desenho(nome="%s %02d" % (titulo, n), escala=1.0)
        for nome_c, cam in desenho.camadas.items():
            d.camadas.setdefault(nome_c, copy.deepcopy(cam))
        info = dict(carimbo)
        if f["titulo"]:
            info["titulo"] = f["titulo"]
        info.setdefault("titulo", desenho.nome.replace("Detalhamento – ", "")[:48])
        # o carimbo como está na folha do desenho (editado à mão no CAD — pedido do usuário, 28/09):
        # obra, projetista, data, escala, revisão e as linhas do conteúdo
        tx = [e for e in f["entidades"] if isinstance(e, Texto)]
        por_campo = collections.defaultdict(list)
        for e in tx:
            por_campo[(e.atributos or {}).get("campo")].append(e)
        for c in ("obra", "projetista", "data"):
            if por_campo.get(c):
                info[c] = por_campo[c][0].texto
                if c == "obra":
                    info["cliente"] = ""                 # o texto da obra já vem inteiro
        escala_txt = por_campo["escala"][0].texto if por_campo.get("escala") else texto_escala(k)
        conteudo = [e.texto for e in sorted(por_campo.get("conteudo", []), key=lambda e: -e.posicao[1]) if e.texto.strip() not in ("", "-")]
        if por_campo.get("prancha"):
            m_rev = re.search(r"REV\.\s*(\S+)", por_campo["prancha"][0].texto)
            if m_rev:
                info["revisao"] = m_rev.group(1)
        larg, alt = FOLHAS[f["formato"]]
        quadro, carimbo_cx = _modelo.desenhar_folha(d, f["formato"], larg, alt, info, n, total, escala_txt, conteudo)
        dentro = 0
        for e in soltas:
            cx = _caixa_de([e], k)
            if cx is None:
                continue
            (ex0, ey0), (ex1, ey1) = cx
            if ex0 >= x0 - 1e-6 and ey0 >= y0 - 1e-6 and ex1 <= x1 + 1e-6 and ey1 <= y1 + 1e-6:
                d.add(_para_papel(e, k, -x0 / k, -y0 / k, fonte))
                dentro += 1
        d.metadados["prancha"] = {"formato": f["formato"], "numero": n, "total": total, "fontes": [fonte],
                                  "titulo": info.get("titulo", ""), "folha": f["id"], "escala": k,
                                  "quadro": [round(v, 2) for v in quadro], "carimbo": [round(v, 2) for v in carimbo_cx],
                                  "celulas": [], "entidades_do_desenho": dentro}
        d.metadados["gerado_por"] = "folhas"
        saida.append(d)
    return saida


def _chave_da_celula(a: dict):
    """A célula do detalhamento a que a entidade pertence: (tipo do detalhe, campo, valor) — o
    conjunto, a montagem ou a posição. None para o que não é de célula (a faixa, o desenhado à mão)."""
    d = a.get("detalhe")
    if not d:
        return None
    for k in ("conjunto", "montagem", "posicao"):
        if a.get(k):
            return (str(d), k, str(a[k]))
    return None


def _assinatura(e: Entidade2D, k: float):
    """O que não muda quando a entidade é só deslocada — para achar a mesma entidade no desenho novo:
    (tipo, camada, forma) e o ponto de referência dela."""
    if isinstance(e, Linha):
        a, b = (e.a, e.b) if (e.a[0], e.a[1]) <= (e.b[0], e.b[1]) else (e.b, e.a)
        return ("L", e.camada, round(b[0] - a[0]), round(b[1] - a[1])), a
    if isinstance(e, Texto):
        return ("T", e.camada, e.texto, round(e.altura, 2), round(e.angulo, 1)), e.posicao
    if isinstance(e, Circulo):
        return ("C", e.camada, round(e.raio, 1)), e.centro
    if isinstance(e, Cota):
        return ("D", e.camada, round(e.p2[0] - e.p1[0]), round(e.p2[1] - e.p1[1]), e.modo), e.p1
    return None, None


def manter_montagem(antigo: Desenho, novo: Desenho) -> dict:
    """Gerar o detalhamento de novo sem perder a montagem das pranchas (pergunta do usuário, 28/09).

    Do desenho de antes vão para o novo: as folhas (com o carimbo), o que foi desenhado à mão e, para
    cada pedaço de detalhe posto dentro de uma folha (a elevação, o bloco de texto, uma peça — movido
    ou copiado para lá), o mesmo pedaço do desenho **novo** no mesmo lugar. O pedaço se acha pelas
    entidades que não mudaram (linhas, textos e cotas iguais, só deslocados): o deslocamento mais
    votado leva do desenho novo à folha, e entram as entidades novas do mesmo detalhe que caem na
    área dele. O pedaço movido sai do lugar padrão do desenho novo; o copiado fica nos dois. O que
    não se acha no desenho novo (a peça saiu do modelo) fica como estava, contado em `sem_modelo`."""
    folhas = _folhas_do(antigo)
    k = float(antigo.escala or 1.0)
    rel = {"folhas": len(folhas), "atualizadas": 0, "sem_modelo": [], "a_mao": 0}

    def caixa(ents):
        cx = _caixa_de(ents, k)
        return None if cx is None else (cx[0][0], cx[0][1], cx[1][0], cx[1][1])

    def na_folha(e):
        cx = caixa([e])
        if cx is None:
            return False
        mx, my = (cx[0] + cx[2]) / 2.0, (cx[1] + cx[3]) / 2.0
        return any(f["caixa"][0] <= mx <= f["caixa"][2] and f["caixa"][1] <= my <= f["caixa"][3] for f in folhas)

    postos: Dict[tuple, list] = collections.OrderedDict()   # (grupo de cópia ou chave) → entidades na folha
    a_mao, de_folha = [], []
    for e in antigo.entidades.values():
        a = e.atributos or {}
        if a.get("folha"):
            de_folha.append(e)
            continue
        ch = _chave_da_celula(a)
        if ch is None:
            if not a.get("faixa") and not a.get("quadro"):
                a_mao.append(e)                     # o que o gerador não põe: foi desenhado à mão
            continue
        if folhas and na_folha(e):
            g = a.get("grupo_copia") or ""
            # a cópia é um grupo só (uma operação de Copiar); o movido, pela célula
            postos.setdefault(("c", g) if g else ("m", ch), []).append(e)
    if not folhas and not a_mao:
        return rel
    for nome_c, cam in antigo.camadas.items():
        novo.camadas.setdefault(nome_c, copy.deepcopy(cam))
    # o desenho novo pela assinatura, só as entidades de detalhe (sem as cópias)
    por_assin: Dict[tuple, list] = collections.defaultdict(list)
    por_chave: Dict[tuple, list] = collections.defaultdict(list)
    for e in novo.entidades.values():
        a = e.atributos or {}
        ch = _chave_da_celula(a)
        if ch is None or a.get("grupo_copia"):
            continue
        por_chave[ch].append(e)
        sg, ref = _assinatura(e, k)
        if sg is not None:
            por_assin[(ch, sg)].append((e, ref))
    tirar = set()
    for (modo, _g), ents in postos.items():
        chaves = {_chave_da_celula(e.atributos or {}) for e in ents}
        votos = collections.Counter()
        for e in ents:
            sg, ref = _assinatura(e, k)
            if sg is None:
                continue
            ch = _chave_da_celula(e.atributos or {})
            for n, rn in por_assin.get((ch, sg), [])[:200]:
                votos[(round(ref[0] - rn[0]), round(ref[1] - rn[1]))] += 1
        melhor = votos.most_common(1)
        if not melhor or melhor[0][1] < (1 if len(ents) == 1 else 2):
            for e in ents:                          # não se acha no desenho novo: fica o de antes
                novo.add(transladar(e, 0.0, 0.0))
            rel["sem_modelo"].extend(sorted({c[2] for c in chaves if c}))
            continue
        dx, dy = melhor[0][0]
        x0, y0, x1, y1 = caixa(ents)
        folga = 0.02 * max(x1 - x0, y1 - y0) + 5.0 * k       # o que cresceu no desenho novo, sem pegar a célula vizinha
        pedaco = []
        for ch in chaves:
            for n in por_chave.get(ch, []):
                cn = caixa([n])
                if cn is None:
                    continue
                mx, my = (cn[0] + cn[2]) / 2.0 + dx, (cn[1] + cn[3]) / 2.0 + dy
                if x0 - folga <= mx <= x1 + folga and y0 - folga <= my <= y1 + folga:
                    pedaco.append(n)
        grupo = _g if modo == "c" else ""
        for n in pedaco:
            c = transladar(n, dx, dy)
            c.id = novo_id()
            if grupo:
                c.atributos = dict(c.atributos or {}, grupo_copia=grupo)
            novo.add(c)
        if modo == "m":
            tirar.update(n.id for n in pedaco)      # foi movido (não copiado): sai do lugar padrão
        rel["atualizadas"] += 1
    for i in tirar:
        novo.remover(i)
    for e in de_folha + a_mao:
        novo.add(transladar(e, 0.0, 0.0))
    rel["a_mao"] = len(a_mao)
    return rel
