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
        if n.texto_pos:                               # o número posto fora (cadeia curta): junto
            n.texto_pos = mv(n.texto_pos)             # (sem isto ia parar longe da folha, 28/09)
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
    # as chapas da cumeeira desenhadas debaixo da tesoura (detalhe_cumeeira) viram células próprias: na
    # prancha elas vão para os DETALHES, e a tesoura fica só com ela (pedido do usuário, 28/09)
    extra = []
    for c in celulas:
        cume = [e for e in c["entidades"] if (e.atributos or {}).get("detalhe_cumeeira")]
        if not cume:
            continue
        c["entidades"] = [e for e in c["entidades"] if not (e.atributos or {}).get("detalhe_cumeeira")]
        por = collections.OrderedDict()
        for e in cume:
            por.setdefault(str((e.atributos or {}).get("posicao") or ""), []).append(e)
        for mk, ents in por.items():
            extra.append({"fonte": nome, "titulo": desenho.nome, "desenho_titulo": desenho.nome,
                          "escala": c["escala"], "caixa": c["caixa"], "entidades": ents,
                          **({"chave": ("posicao", mk)} if mk else {})})
    # os detalhes de furos das barras (DETALHE A – FUROS DE B.28), desenhados debaixo da tesoura, também:
    # na prancha eles vão para os DETALHES da tesoura (pedido do usuário, 28/09) — `pai` é a célula dela
    for c in celulas:
        fur = [e for e in c["entidades"] if (e.atributos or {}).get("detalhe_furos")]
        if not fur:
            continue
        c["entidades"] = [e for e in c["entidades"] if not (e.atributos or {}).get("detalhe_furos")]
        por = collections.OrderedDict()
        for e in fur:
            por.setdefault(str(e.atributos["detalhe_furos"]), []).append(e)
        for letra, ents in por.items():
            extra.append({"fonte": nome, "titulo": desenho.nome, "desenho_titulo": desenho.nome,
                          "escala": c["escala"], "caixa": c["caixa"], "entidades": ents, "pai": c, "letra": letra})
    celulas = [c for c in celulas + extra if c["entidades"]]
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
        if c.get("pai") is not None:
            continue                                  # o detalhe de furos é da tesoura, que já está na lista
        it = c.get("item") or {}
        cat = (it.get("categoria") or c.get("categoria") or "VISTAS").upper()
        nome = (it.get("nome") or c.get("montagem") or c.get("marca") or c.get("desenho_titulo") or c["titulo"]).replace("Detalhamento – ", "")
        q = _quantidade_da_celula(c) if (it or c.get("montagem")) else 0
        if q:
            nome = "%s (%02dx)" % (nome, q)
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
    Devolve a lista de desenhos-prancha, já numerados. `indice` fica pela compatibilidade: a relação das
    pranchas saiu da legenda (pedido do usuário, 28/09: "as legendas devem ser só dos elementos que estão
    nessa prancha"); ela está no CONTEÚDO do carimbo de cada uma."""
    if formato not in FOLHAS:
        raise ErroDeDados("formato de folha desconhecido: %s" % formato)
    carimbo = dict(carimbo or {})
    celulas = []
    for f in fontes:
        cs = celulas_de(f["desenho"], f["nome"])
        if f.get("chaves"):                      # só as posições/conjuntos pedidos
            pedidas = {str(k) for k in f["chaves"]}
            cs = [c for c in cs if (c.get("chave") and c["chave"][1] in pedidas) or c["titulo"] in pedidas]
            for c in cs:
                c["selecionada"] = True               # escolhida à mão: é a que fica, se repetir
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
    # as células de montagem (o chumbamento "CB1 + CH9": o chumbador com a chapa de apoio) pelo nome dela
    for c in celulas:
        if c.get("chave"):
            continue
        conta = collections.Counter(str((e.atributos or {}).get("montagem") or "") for e in c["entidades"])
        nome_m, n_m = conta.most_common(1)[0] if conta else ("", 0)
        if nome_m and n_m >= 0.8 * len(c["entidades"]):
            c["montagem"] = nome_m
            c["chave"] = ("montagem", nome_m)
    # a mesma posição desenhada em dois desenhos (a chapa na tesoura, nas terças e nas chaparias, que é
    # o desenho para o corte): uma célula só, a do desenho da família, com o item de quem o tiver
    unicas, vistas = [], {}
    for c in celulas:
        ch = c.get("chave")
        if ch and ch[0] in ("posicao", "montagem") and ch in vistas:
            j = vistas[ch]
            antes = unicas[j]
            if (c.get("selecionada") and not antes.get("selecionada")) or (
                    not antes.get("selecionada") and "chaparia" in str(antes["fonte"]) and "chaparia" not in str(c["fonte"])):
                c.setdefault("item", antes.get("item"))
                if not c.get("item"):
                    c["item"] = antes.get("item")
                c.setdefault("marca", antes.get("marca"))
                unicas[j] = c
            elif not antes.get("item") and c.get("item"):
                antes["item"] = c["item"]
            continue
        if ch and ch[0] in ("posicao", "montagem"):
            vistas[ch] = len(unicas)
        unicas.append(c)
    celulas = unicas
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
        c["categoria"] = (c.get("item") or {}).get("categoria") or (
            "CHAPAS" if c.get("montagem") else "VISTAS" if not c.get("marca") else "OUTROS")
    qx0, qx1 = ux0 + QUADRO_MARGEM, ux1 - QUADRO_MARGEM
    # os detalhes de furos: os da tesoura vão para a faixa da prancha dela (na categoria dela, se não
    # couberem); os de um conjunto menor voltam para a célula dele, como antes
    for c in [c for c in itens if c.get("pai") is not None]:
        pai = c["pai"]
        if not any(pai is x for x in itens):
            continue
        if _empilhavel(pai, qx1 - qx0):
            c["categoria"] = pai["categoria"]
            c["_ordem"] = pai.get("_ordem", 0) + 0.5
            continue
        pai["entidades"] = list(pai["entidades"]) + list(c["entidades"])
        pai["caixa"] = _caixa_de(pai["entidades"], pai["escala"]) or pai["caixa"]
        (bx0, by0), (bx1, by1) = pai["caixa"]
        pai["w"], pai["h"] = (bx1 - bx0) / pai["k"], (by1 - by0) / pai["k"] + FAIXA
        itens = [x for x in itens if x is not c]
    itens.sort(key=lambda c: (ordem.get(c["categoria"], 99), c.get("_ordem", 0)))
    # a faixa ao lado do carimbo, embaixo (pedido do usuário, 28/09): DETALHES à esquerda — as chapas dos
    # conjuntos desenhados na prancha (a composição deles), ou, sem conjunto, mais células das mesmas
    # categorias — e LEGENDA junto do carimbo — as peças da prancha, as siglas e, na primeira, a relação das
    # pranchas. O último quadro de cima desce até a faixa.
    fx0, fx1 = ux0, larg - m["direita"] - lc - FOLGA
    fy0, fy1 = m["inferior"] + 3.0, m["inferior"] + ac
    alt_faixa = fy1 - fy0 - QUADRO_CABECALHO - FOLGA

    def distribuir(n_rel):
        for c_ in itens:
            c_.pop("empilhada", None)
        fila = list(itens)
        pranchas: List[List[dict]] = []
        molduras: List[List[dict]] = []        # por prancha: {categoria, titulo, y0, y1[, x0, x1]}
        legendas: List[dict] = []
        iniciadas = set()

        def prateleira(cat, x_ini, x_fim):
            """as próximas células da fila, da categoria, que cabem lado a lado entre x_ini e x_fim"""
            linha, x = [], x_ini
            for c in fila:
                if c["categoria"] != cat:
                    break
                if linha and x + c["w"] > x_fim:
                    break
                linha.append(c)
                x += c["w"] + FOLGA
            return linha

        while fila:
            cels_p, mold_p = [], []
            y_topo = uy1
            cheia = False
            sobra_v = 0.0                      # a altura que a tesoura deixa livre no quadro dela
            # as tesouras (conjunto largo com o bloco do título): uma ou duas por prancha, empilhadas pela
            # altura real delas com o bloco embaixo (o usuário montou assim a Sala, 28/09)
            if fila and _empilhavel(fila[0], qx1 - qx0):
                util = (uy1 - QUADRO_CABECALHO - 3.0) - (uy0 - FOLGA * 0.5 + 3.0)
                grupo = [fila[0]]
                seg = [c_ for c_ in fila[1:] if c_.get("pai") is None][:1]
                sep_ = None
                if seg and _empilhavel(seg[0], qx1 - qx0) and seg[0]["categoria"] == fila[0]["categoria"]:
                    mq_ = {"y1": uy1, "y0": uy0 - FOLGA * 0.5}
                    sep_ = _separacao(fila[0], seg[0], mq_, qx0, qx1)
                    if sep_ + _altura_empilhada(seg[0]) <= util:
                        grupo.append(seg[0])
                usado = (sep_ + _altura_empilhada(grupo[1])) if len(grupo) == 2 else _altura_empilhada(grupo[0])
                sobra_v = max(0.0, util - usado - 4.0)
                cat = fila[0]["categoria"]
                mold_p.append({"categoria": cat, "titulo": CATEGORIAS.get(cat, cat) + (" (continuação)" if cat in iniciadas else ""),
                               "y1": uy1, "y0": uy0 - FOLGA * 0.5})
                iniciadas.add(cat)
                for c in grupo:
                    c["empilhada"] = True
                    c["px"], c["py"] = qx0, uy0              # a posição real sai no desenho
                    cels_p.append(c)
                    fila.remove(c)
                cheia = True
            while fila and not cheia:
                cat = fila[0]["categoria"]
                linha = prateleira(cat, qx0, qx1)
                alt = max(c["h"] for c in linha)
                if y_topo - (QUADRO_CABECALHO + FOLGA + alt + FOLGA) < uy0 and cels_p:
                    break
                aberto = {"categoria": cat, "titulo": CATEGORIAS.get(cat, cat) + (" (continuação)" if cat in iniciadas else ""),
                          "y1": y_topo, "y0": None}
                mold_p.append(aberto)
                iniciadas.add(cat)
                y_topo -= QUADRO_CABECALHO + FOLGA
                while fila and fila[0]["categoria"] == cat:
                    linha = prateleira(cat, qx0, qx1)
                    alt = max(c["h"] for c in linha)
                    if y_topo - (alt + FOLGA) < uy0 and cels_p:
                        cheia = True
                        break
                    x = qx0
                    for c in linha:
                        # alinhadas pelo topo: os títulos numa linha só
                        c["px"], c["py"] = x, y_topo - c["h"]
                        x += c["w"] + FOLGA
                        cels_p.append(c)
                        fila.remove(c)
                    y_topo -= alt + FOLGA
                aberto["y0"] = y_topo
                y_topo -= FOLGA
            if mold_p:
                mold_p[-1]["y0"] = uy0 - FOLGA * 0.5            # o último quadro desce até a faixa
            # os detalhes: as chapas dos conjuntos da prancha; sem conjunto, as das mesmas categorias
            comp_p = [x for c in cels_p for x in ((c.get("item") or {}).get("composicao") or [])
                      if str(x.get("classe") or "").startswith("chapa")]
            alvo = {x["marca"] for x in comp_p}
            cats_p = {c["categoria"] for c in cels_p}
            nomes_alvo = {x["nome"] for x in comp_p}
            if alvo:
                # as chapas das tesouras e os chumbamentos delas ("CB1 + CH9"), cada uma com quantas estão
                # desenhadas na prancha (pedido do usuário, 28/09: "a quantidade total vai na prancha da
                # chaparia, aqui é quantas tem nessa prancha"): uma cópia do detalhe, e o de antes segue na fila
                # para a prancha das chapas
                por_marca, por_nome = collections.Counter(), collections.Counter()
                for x in comp_p:
                    por_marca[x["marca"]] += int(x.get("qtd") or 0)
                    por_nome[x["nome"]] += int(x.get("qtd") or 0)
                candidatas, vistas_ch = [], set()
                for c in itens:
                    if any(c is x for x in cels_p) or c.get("empilhada") or c.get("pai") is not None:
                        continue
                    marcas_c = [c.get("marca")] + list((c.get("item") or {}).get("marcas") or [])
                    if c.get("montagem"):
                        partes = [pt for pt in c["montagem"].split(" + ") if pt in nomes_alvo]
                        n_loc = max((por_nome[pt] for pt in partes), default=0)
                    elif any(mk in alvo for mk in marcas_c if mk):
                        n_loc = sum(por_marca[mk] for mk in dict.fromkeys(marcas_c) if mk in por_marca)
                    else:
                        continue
                    ch_ = c.get("chave") or ("id", id(c))
                    if n_loc <= 0 or ch_ in vistas_ch:
                        continue
                    vistas_ch.add(ch_)
                    candidatas.append(_copia_local(c, n_loc))
                # o chumbamento primeiro (é o que a obra procura junto da tesoura), depois as chapas
                candidatas.sort(key=lambda c: 0 if _eh_chumbamento(c.get("montagem")) else 1)
            else:
                candidatas = [c for c in fila if c["categoria"] in cats_p and c.get("pai") is None]
            furos_p = [c for c in fila if c.get("pai") is not None and any(c["pai"] is x for x in cels_p)]
            # a legenda: só o que está na prancha — nome e quantidade — e as siglas (pedido do usuário, 28/09:
            # "precisa reduzir bastante o tamanho"); a largura sai do conteúdo com todos os detalhes possíveis
            leg = {"blocos": _blocos_da_legenda(cels_p, candidatas if alvo else ()), "relacao": False, "n_rel": n_rel}
            tem_legenda = bool(leg["blocos"])
            larg_leg = min(_legenda(None, leg, 0.0, fy0, fy1, [], {}), 0.6 * (fx1 - fx0)) if tem_legenda else 0.0
            leg["x0"] = fx1 - larg_leg
            dx1 = leg["x0"] - FOLGA if tem_legenda else fx1

            def empacotar(y_top):
                """em colunas: cada detalhe embaixo do último da coluna em que cabe (os pequenos se empilham
                debaixo dos outros), ou numa coluna nova à direita; o detalhe da fileira de baixo pode ser
                mais largo que o de cima se a coluna seguinte ainda não existe. Devolve [(célula, px, py)]."""
                topo_cel = y_top - QUADRO_CABECALHO - FOLGA * 0.5
                alt_f = y_top - fy0 - QUADRO_CABECALHO - FOLGA
                colunas, x_prox, postos = [], fx0 + QUADRO_MARGEM, []
                vao = FOLGA * 0.6                              # entre os detalhes (cada um já tem a margem dele)
                base_faixa = fy0 + FOLGA * 0.5
                for c in candidatas:
                    if c["h"] > alt_f or c["w"] > dx1 - fx0 - 2 * QUADRO_MARGEM:
                        continue
                    col = next((k_ for k_ in colunas if k_["y"] - FOLGA - c["h"] >= base_faixa and (
                        c["w"] <= k_["w"] + 0.5 or (k_ is colunas[-1] and k_["x"] + c["w"] <= dx1 - QUADRO_MARGEM))), None)
                    if col is not None:
                        py_ = col["y"] - FOLGA - c["h"]
                        postos.append((c, col["x"], py_))
                        col["y"] = py_
                        if c["w"] > col["w"]:
                            col["w"] = c["w"]
                            x_prox = col["x"] + c["w"] + vao
                    elif x_prox + c["w"] <= dx1 - QUADRO_MARGEM and topo_cel - c["h"] >= base_faixa:
                        postos.append((c, x_prox, topo_cel - c["h"]))
                        colunas.append({"x": x_prox, "w": c["w"], "y": topo_cel - c["h"]})
                        x_prox += c["w"] + vao
                return postos
            fy1_p = fy1
            postos = empacotar(fy1)
            if len(postos) < len(candidatas) and sobra_v > 5.0:
                alto = fy1 + min(sobra_v, alt_faixa + FOLGA)
                postos_alto = empacotar(alto)
                if len(postos_alto) > len(postos):
                    # a faixa só tão alta quanto os detalhes pedem: o que sobra embaixo sai
                    folga_b = min(py_ for _c, _x, py_ in postos_alto) - (fy0 + FOLGA * 0.5)
                    folga_b = max(0.0, min(folga_b, alto - fy1))
                    postos = [(c_, x_, py_ - folga_b) for c_, x_, py_ in postos_alto]
                    fy1_p = alto - folga_b
            na_faixa = []
            for c, px_, py_ in postos:
                c["px"], c["py"] = px_, py_
                na_faixa.append(c)
                if not c.get("local"):
                    fila.remove(c)
            if fy1_p > fy1 and mold_p:
                mold_p[-1]["y0"] = fy1_p + FOLGA * 0.5            # o quadro de cima sobe junto com a faixa
            leg["y1"] = fy1_p
            # no quadro das tesouras: os detalhes de furos logo abaixo da cota de baixo da tesoura deles, à
            # direita do bloco do título, com a linha de chamada até a marca dos furos (pedido do usuário,
            # 28/09); depois, o que não coube na faixa, no canto livre embaixo da última tesoura
            emp_p = [c for c in cels_p if c.get("empilhada")]
            sobras = [c for c in candidatas if not any(c is x_ for x_ in na_faixa)
                      and (c.get("local") or any(c is x_ for x_ in fila))]
            no_canto = []
            if emp_p and mold_p and (furos_p or sobras):
                mq_t = mold_p[0]
                ocup, info_t = _layout_das_tesouras(emp_p, mq_t, qx0, qx1)
                y_min = mq_t["y0"] + 1.5
                for c in furos_p:
                    t_ = next(i_ for i_, x_ in enumerate(emp_p) if c["pai"] is x_)
                    it_ = info_t[t_]
                    pos = (_encaixar(ocup, c["w"], c["h"], it_["x_bloco"] + FOLGA, it_["y_cotas"] - 2.0, qx1, y_min, descer=40.0)
                           or _encaixar(ocup, c["w"], c["h"], qx0, it_["y_cotas"] - 2.0, qx1, y_min))
                    if pos is None:
                        continue
                    c["px"], c["py"] = pos
                    c["alvo_furos"] = it_["marcas"].get(str(c.get("letra")))
                    no_canto.append(c)
                    fila.remove(c)
                it_ = info_t[-1]
                for c in sobras:
                    pos = _encaixar(ocup, c["w"], c["h"], it_["x_bloco"] + FOLGA, it_["y_cotas"] - FOLGA * 0.5, qx1, y_min)
                    if pos is None:
                        continue
                    c["px"], c["py"] = pos
                    no_canto.append(c)
                    if not c.get("local"):
                        fila.remove(c)
            # a legenda com o que ficou de fato na prancha (os detalhes que couberam), e os DETALHES até ela
            leg["blocos"] = _blocos_da_legenda(cels_p, na_faixa + no_canto)
            if leg["blocos"]:
                leg["x0"] = fx1 - min(_legenda(None, leg, 0.0, fy0, fy1, [], {}), 0.6 * (fx1 - fx0))
                dx1 = leg["x0"] - FOLGA
            tem_legenda = bool(leg["blocos"])
            if na_faixa:
                # "ACESSÓRIOS/DISPOSITIVOS": as chapas e os acessórios das peças da prancha (pedido do usuário, 28/09)
                mold_p.append({"categoria": "DETALHES", "titulo": "ACESSÓRIOS/DISPOSITIVOS", "y1": fy1_p, "y0": fy0, "x0": fx0, "x1": dx1})
                iniciadas.update(c["categoria"] for c in na_faixa)
            if tem_legenda:
                mold_p.append({"categoria": "LEGENDA", "titulo": "LEGENDA", "y1": fy1_p, "y0": fy0, "x0": leg["x0"], "x1": fx1})
            pranchas.append(cels_p + na_faixa + no_canto)
            molduras.append(mold_p)
            legendas.append(leg)
        return pranchas, molduras, legendas

    pranchas, molduras, legendas = distribuir(1)
    total = len(pranchas)
    # em que prancha cada posição está detalhada (a coluna PR. da legenda) e a relação das pranchas
    onde: Dict[str, int] = {}
    for i_p, cels in enumerate(pranchas, start=1):
        for c in cels:
            if c.get("local"):
                continue                     # a cópia na prancha da tesoura: as outras apontam o total
            for mk in [c.get("marca")] + list((c.get("item") or {}).get("marcas") or []):
                if mk:
                    onde.setdefault(str(mk), i_p)
            if c.get("montagem"):
                onde.setdefault("montagem:" + c["montagem"], i_p)
    # a montagem de cada chapa ("CH9" -> "CB1 + CH9"): as chamadas apontam os chumbamentos nos apoios
    montagem_de = {pt: c["montagem"] for cels in pranchas for c in cels if _eh_chumbamento(c.get("montagem"))
                   for pt in c["montagem"].split(" + ")}

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
        info.setdefault("titulo", ", ".join(dict.fromkeys(mq["titulo"].replace(" (continuação)", "") for mq in molduras[i0 - 1]
                                                          if mq["categoria"] not in ("DETALHES", "LEGENDA")))[:48] or fontes_titulo(cels))
        quadro, carimbo_caixa = _moldura(d, formato, info, i, total, [c["k"] for c in cels], _conteudo_de(cels))
        for mq in molduras[i0 - 1]:
            _quadro(d, mq, mq.get("x0", ux0), mq.get("x1", ux1))
        # um conjunto sozinho na área de cima (a tesoura): centralizado no quadro, que desce até a faixa, e
        # o bloco do título dele (nome, perfis, parafusos, peso) embaixo, maior (pedido do usuário, 28/09)
        # o que está detalhado nesta prancha (as cópias locais das chapas): a chamada não leva "– PR.xx"
        onde_i = dict(onde)
        for c in cels:
            for mk in [c.get("marca")] + list((c.get("item") or {}).get("marcas") or []):
                if mk:
                    onde_i[str(mk)] = i
            if c.get("montagem"):
                onde_i["montagem:" + c["montagem"]] = i
        empilhadas = [c for c in cels if c.get("empilhada")]
        if empilhadas:
            mq = molduras[i0 - 1][0]
            for c, topo_c in zip(empilhadas, _topos_empilhadas(empilhadas, mq, qx0, qx1)):
                _conjunto_centralizado(d, c, mq, qx0, qx1, onde_i, i, montagem_de, topo=topo_c)
        for c in cels:
            if c.get("empilhada"):
                continue
            (bx0, by0), (bx1, by1) = c["caixa"]
            dx = c["px"] - bx0 / c["k"]
            dy = c["py"] + FAIXA - by0 / c["k"]
            for e in c["entidades"]:
                d.add(_para_papel(e, c["k"], dx, dy, c["fonte"]))
            if c.get("alvo_furos"):
                (mx, my), mr = c["alvo_furos"]
                # do canto de cima da caixa do detalhe mais perto da marca até a borda do círculo
                ax_ = min(max(mx, c["px"]), c["px"] + c["w"])
                ay_ = c["py"] + c["h"]
                dl = math.hypot(mx - ax_, my - ay_)
                if dl > mr + 1.0:
                    bx_, by_ = mx - (mx - ax_) / dl * mr, my - (my - ay_) / dl * mr
                    d.add(Linha(camada="COTA", a=(round(ax_, 2), round(ay_, 2)), b=(round(bx_, 2), round(by_, 2)),
                                atributos={"prancha": "chamada_furos", "fonte": c["fonte"], "letra": c.get("letra")}))
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
        leg = legendas[i0 - 1]
        if leg["blocos"]:
            _legenda(d, leg, leg["x0"], fy0, leg.get("y1", fy1), [], onde, largura=fx1 - leg["x0"])
        d.metadados["prancha"]["relacao"] = leg["relacao"]
        d.metadados["prancha"]["siglas"] = [x[0] for b in leg["blocos"] if b[0] == "SIGLAS" for x in b[1]]
        saida.append(d)
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
            txt = "Tesoura"
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


#: O bloco do título da tesoura na prancha: o nome, as linhas, o espaço entre elas e o vão da cota mais
#: baixa até ele (mm de papel; 8 mm além da faixa do número da cota = os 13,5 mm que o usuário usou).
BLOCO_TITULO, BLOCO_LINHA, BLOCO_ESPACO, BLOCO_VAO = 6.0, 4.2, 1.8, 8.0


def _partes_do_conjunto(c: dict):
    """(linhas do bloco do título em ordem, o resto das entidades, caixa do resto em mm do modelo)"""
    leg = sorted((e for e in c["entidades"] if isinstance(e, Texto) and "legenda_conjunto" in (e.atributos or {})),
                 key=lambda e: e.atributos["legenda_conjunto"])
    ids_leg = {id(e) for e in leg}
    resto = [e for e in c["entidades"] if id(e) not in ids_leg]
    return leg, resto, (_caixa_de(resto, c["k"]) or c["caixa"])


def _altura_empilhada(c: dict) -> float:
    """A altura de papel do conjunto com o bloco embaixo (a tesoura como na prancha)."""
    leg, _resto, ((_x0, y0), (_x1, y1)) = _partes_do_conjunto(c)
    alt_leg = BLOCO_TITULO + max(0, len(leg) - 1) * (BLOCO_LINHA + BLOCO_ESPACO) + BLOCO_ESPACO
    return (y1 - y0) / c["k"] + BLOCO_VAO + alt_leg + 6.0


def _conjunto_centralizado(d: Desenho, c: dict, mq: dict, qx0: float, qx1: float, onde: Dict[str, int] = None,
                           numero: int = 0, montagem_de: Dict[str, str] = None, topo: Optional[float] = None,
                           coletor=None):
    """O conjunto (a tesoura) no meio do quadro dele, com o bloco do título — as linhas marcadas com
    `legenda_conjunto` no detalhamento — embaixo, à esquerda, alinhado pela borda da tesoura (sem as
    cotas), em letra maior: 6 mm o nome, 4,2 mm o resto (pedido do usuário, 28/09; a posição como ele a
    ajustou na Sala). Uma chamada por tipo de chapa da composição aponta onde ela fica na tesoura, com o
    nome e, detalhada noutra prancha, qual. Atualiza a posição da célula (px, py, w, h) para os metadados."""
    saida = coletor if coletor is not None else d
    k = c["k"]
    leg, resto, ((bx0, by0), (bx1, by1)) = _partes_do_conjunto(c)
    w, h = (bx1 - bx0) / k, (by1 - by0) / k
    h_tit, h_lin, esp, vao = BLOCO_TITULO, BLOCO_LINHA, BLOCO_ESPACO, BLOCO_VAO
    if topo is None:
        topo_area = mq["y1"] - QUADRO_CABECALHO - FOLGA
        base_area = mq["y0"] + FOLGA
        topo = topo_area - max(0.0, (topo_area - base_area - _altura_empilhada(c)) / 2.0)
    xc = (qx0 + qx1) / 2.0
    dx, dy = xc - w / 2.0 - bx0 / k, (topo - h) - by0 / k
    for e in resto:
        saida.add(_para_papel(e, k, dx, dy, c["fonte"]))
    y = topo - h - vao - h_tit
    geo = [e for e in resto if not isinstance(e, (Cota, Texto, Chamada))]
    g0 = (_caixa_de(geo, k) or ((bx0, by0), (bx1, by1)))[0][0]
    x_bloco = g0 / k + dx + 5.5                                # a borda da tesoura, sem as cotas da esquerda
    _chamadas_das_chapas(saida, c, geo, k, dx, dy, onde or {}, numero, montagem_de or {})
    for i, e in enumerate(leg):
        alt = h_tit if i == 0 else h_lin
        saida.add(Texto(camada=e.camada, posicao=(round(x_bloco, 2), round(y, 2)), texto=e.texto, altura=alt,
                    atributos=dict(e.atributos or {}, fonte=c["fonte"], escala=k)))
        y -= (h_lin + esp)
    saida.add(Texto(camada="TEXTO", posicao=(round(x_bloco, 2), round(y - 1.0, 2)), texto="ESC. " + texto_escala(k), altura=2.5,
                atributos={"prancha": "escala", "fonte": c["fonte"], "celula": c["titulo"]}))
    c["px"], c["py"], c["w"], c["h"] = xc - w / 2.0, y - 2.0, w, topo - (y - 2.0)


class _Coletor(list):
    """as entidades de um conjunto antes de irem para a prancha"""
    def add(self, e):
        self.append(e)


def _perfil(ents: Sequence, passo: float = 5.0):
    """O perfil de cima e o de baixo das entidades (mm de papel), em faixas de `passo` na horizontal:
    ({faixa: y mais alto}, {faixa: y mais baixo}). Linhas, cotas (a linha e as chamadas dela, o número),
    textos e chamadas pelos pontos ao longo deles."""
    cima, baixo = {}, {}

    def ponto(x, y):
        i = int(math.floor(x / passo))
        if y > cima.get(i, -1e18):
            cima[i] = y
        if y < baixo.get(i, 1e18):
            baixo[i] = y

    def seg(a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / passo) + 1)
        for j in range(n + 1):
            t = j / n
            ponto(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    for e in ents:
        if isinstance(e, Cota):
            pc = _pontos_da_cota(e, 1.0)
            if len(pc) >= 4:
                seg(pc[0], pc[1])
                seg(pc[2], pc[3])
                seg(e.p1, pc[0])
                seg(e.p2, pc[1])
        elif isinstance(e, Texto):
            larg = LARGURA_LETRA * e.altura * len(e.texto or "")
            x0 = e.posicao[0] - (larg / 2 if e.alinhamento == "centro" else larg if e.alinhamento == "direita" else 0.0)
            seg((x0, e.posicao[1]), (x0 + larg, e.posicao[1]))
            seg((x0, e.posicao[1] + e.altura), (x0 + larg, e.posicao[1] + e.altura))
        elif isinstance(e, Chamada):
            seg(e.alvo, e.posicao)
            larg = LARGURA_LETRA * e.altura * len(e.texto or "") + 10.0
            sx = 1.0 if e.posicao[0] >= e.alvo[0] else -1.0
            seg(e.posicao, (e.posicao[0] + sx * larg, e.posicao[1] + e.altura))
        else:
            pts = e.pontos()
            for a, b in zip(pts, pts[1:]):
                seg(a, b)
            if len(pts) == 1:
                ponto(*pts[0])
    return cima, baixo


def _separacao(c1: dict, c2: dict, mq: dict, qx0: float, qx1: float, folga: float = 5.0) -> float:
    """Quanto o topo da segunda tesoura fica abaixo do da primeira, encaixada nela (pedido do usuário,
    28/09: o bloco da de cima, embaixo à esquerda, entra no canto vazio de cima da de baixo): o menor
    que deixa `folga` mm entre o perfil de baixo da primeira e o de cima da segunda."""
    e1, e2 = _Coletor(), _Coletor()
    _conjunto_centralizado(None, c1, mq, qx0, qx1, {}, 0, {}, topo=0.0, coletor=e1)
    _conjunto_centralizado(None, c2, mq, qx0, qx1, {}, 0, {}, topo=0.0, coletor=e2)
    _c1, baixo1 = _perfil(e1)
    cima2, _b2 = _perfil(e2)
    comuns = set(baixo1) & set(cima2)
    if not comuns:
        return max(cima2.values()) - min(baixo1.values()) + folga
    return max(cima2[i] - baixo1[i] for i in comuns) + folga


def _topos_empilhadas(emp: Sequence[dict], mq: dict, qx0: float, qx1: float) -> List[Optional[float]]:
    """O topo de cada tesoura no quadro: o par encaixado e centrado na altura; uma só, None (centrada)."""
    topo_a, base_a = mq["y1"] - QUADRO_CABECALHO - 3.0, mq["y0"] + 3.0
    if len(emp) == 2:
        sep = _separacao(emp[0], emp[1], mq, qx0, qx1)
        y_ = topo_a - max(0.0, (topo_a - base_a - (sep + _altura_empilhada(emp[1]))) / 2.0)
        return [y_, y_ - sep]
    return [None] * len(emp)


#: A malha (mm de papel) com que se marca o que já está desenhado no quadro das tesouras.
PASSO_OCUPACAO = 4.0


def _ocupacao(ents: Sequence, passo: float = PASSO_OCUPACAO) -> set:
    """As casas da malha que as entidades (em mm de papel) ocupam: linhas e cotas pelos pontos ao longo
    delas (a cota com a faixa do número), textos e círculos pela caixa."""
    occ = set()

    def ret(x0, y0, x1, y1):
        for i in range(int(math.floor(x0 / passo)), int(math.floor(x1 / passo)) + 1):
            for j in range(int(math.floor(y0 / passo)), int(math.floor(y1 / passo)) + 1):
                occ.add((i, j))

    def seg(a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / (passo * 0.5)) + 1)
        for k_ in range(n + 1):
            t = k_ / n
            occ.add((int(math.floor((a[0] + (b[0] - a[0]) * t) / passo)), int(math.floor((a[1] + (b[1] - a[1]) * t) / passo))))

    for e in ents:
        if isinstance(e, Cota):
            pc = _pontos_da_cota(e, 1.0)
            if len(pc) >= 4:
                seg(pc[0], pc[1])
                seg(pc[2], pc[3])
                seg(((pc[0][0] + pc[2][0]) / 2, (pc[0][1] + pc[2][1]) / 2), ((pc[1][0] + pc[3][0]) / 2, (pc[1][1] + pc[3][1]) / 2))
                seg(e.p1, pc[0])
                seg(e.p2, pc[1])
            if e.texto_pos:
                ret(e.texto_pos[0] - 4.0, e.texto_pos[1] - 2.0, e.texto_pos[0] + 4.0, e.texto_pos[1] + 2.0)
        elif isinstance(e, Texto):
            larg = LARGURA_LETRA * e.altura * len(e.texto or "")
            if abs(e.angulo or 0.0) < 1e-6:
                x0 = e.posicao[0] - (larg / 2 if e.alinhamento == "centro" else larg if e.alinhamento == "direita" else 0.0)
                ret(x0, e.posicao[1], x0 + larg, e.posicao[1] + e.altura)
            else:
                a_ = math.radians(e.angulo)
                seg(e.posicao, (e.posicao[0] + larg * math.cos(a_), e.posicao[1] + larg * math.sin(a_)))
        elif isinstance(e, Chamada):
            seg(e.alvo, e.posicao)
            larg = LARGURA_LETRA * e.altura * len(e.texto or "") + 10.0
            x0 = e.posicao[0] if e.posicao[0] >= e.alvo[0] else e.posicao[0] - larg
            ret(x0, e.posicao[1], x0 + larg, e.posicao[1] + e.altura)
        elif isinstance(e, Circulo):
            ret(e.centro[0] - e.raio, e.centro[1] - e.raio, e.centro[0] + e.raio, e.centro[1] + e.raio)
        else:
            pts = e.pontos()
            for a, b in zip(pts, pts[1:]):
                seg(a, b)
    return occ


def _encaixar(occ: set, w: float, h: float, x_ini: float, y_top: float, x_max: float, y_min: float,
              descer: float = 1e9, passo: float = PASSO_OCUPACAO) -> Optional[Tuple[float, float]]:
    """O primeiro lugar livre para uma caixa w × h: o mais alto (a partir de y_top, descendo até `descer`
    mm), e nele o mais à esquerda a partir de x_ini. Marca a caixa como ocupada e devolve (px, py)."""
    def livre(x0, y0, x1, y1):
        return not any((i, j) in occ for i in range(int(math.floor(x0 / passo)), int(math.floor(x1 / passo)) + 1)
                       for j in range(int(math.floor(y0 / passo)), int(math.floor(y1 / passo)) + 1))
    y = y_top
    while y - h >= y_min and y_top - y <= descer:
        x = x_ini
        while x + w <= x_max:
            if livre(x, y - h, x + w, y):
                for i in range(int(math.floor(x / passo)), int(math.floor((x + w) / passo)) + 1):
                    for j in range(int(math.floor((y - h) / passo)), int(math.floor(y / passo)) + 1):
                        occ.add((i, j))
                return x, y - h
            x += passo
        y -= passo
    return None


def _layout_das_tesouras(emp: Sequence[dict], mq: dict, qx0: float, qx1: float):
    """As tesouras como vão sair no quadro: (ocupação, [por tesoura: a borda direita do bloco do título,
    o fundo das cotas de baixo e as marcas dos detalhes de furos {letra: (centro, raio)}])."""
    todas, info = [], []
    for c, topo_c in zip(emp, _topos_empilhadas(emp, mq, qx0, qx1)):
        col = _Coletor()
        _conjunto_centralizado(None, c, mq, qx0, qx1, {}, 0, {}, topo=topo_c, coletor=col)
        bloco = [e for e in col if isinstance(e, Texto) and (
            "legenda_conjunto" in (e.atributos or {}) or (e.atributos or {}).get("prancha") == "escala")]
        resto = [e for e in col if not any(e is b for b in bloco)]
        caixa_r = _caixa_de(resto, 1.0)
        marcas = {}
        for e in col:
            mf = (e.atributos or {}).get("marca_furos")
            if mf and isinstance(e, Circulo):
                marcas[str(mf)] = (e.centro, e.raio)
        info.append({"x_bloco": (max(b.posicao[0] + LARGURA_LETRA * b.altura * len(b.texto or "") for b in bloco)
                                 if bloco else qx0),
                     "y_cotas": caixa_r[0][1] if caixa_r else mq["y0"], "marcas": marcas})
        todas += col
    return _ocupacao(todas), info


def _empilhavel(c: dict, largura_util: float) -> bool:
    """a tesoura: conjunto com o bloco do título e largo (mais de 60% do quadro) — os conjuntos menores,
    também com bloco, seguem nas prateleiras"""
    return c["w"] > 0.6 * largura_util and any(
        isinstance(e, Texto) and "legenda_conjunto" in (e.atributos or {}) for e in c["entidades"])


def _eh_chumbamento(montagem) -> bool:
    """montagem com chumbador ("CB1 + CH9"), não as chapas soldadas entre si ("CH1 + CH2")"""
    import re as _re
    return bool(montagem) and any(_re.match(r"CB\d", pt.strip()) for pt in str(montagem).split(" + "))


def _chamadas_das_chapas(d: Desenho, c: dict, geo: Sequence, k: float, dx: float, dy: float,
                         onde: Dict[str, int], numero: int, montagem_de: Dict[str, str] = None):
    """Uma chamada por tipo de chapa da composição do conjunto, do centro de uma instância dela no desenho
    ao nome ("CH4"; detalhada noutra prancha, "CH3 – PR.02"). A instância é a mais longe das já apontadas,
    para as chamadas se espalharem; o texto sai para fora do desenho (para cima na metade de cima)."""
    comp = [x for x in ((c.get("item") or {}).get("composicao") or []) if str(x.get("classe") or "").startswith("chapa")]
    if not comp:
        return
    pts_geo = [p for e in geo for p in e.pontos()]
    if not pts_geo:
        return
    cx_m = (min(p[0] for p in pts_geo) + max(p[0] for p in pts_geo)) / 2.0
    cy_m = (min(p[1] for p in pts_geo) + max(p[1] for p in pts_geo)) / 2.0
    apontados: List[Ponto2] = []
    for x in comp:
        marcas = set(str(x["marca"]).split(" / "))
        por_inst = collections.defaultdict(list)
        for e in geo:
            a = e.atributos or {}
            if e.camada == "CHAPAS" and str(a.get("posicao") or "") in marcas:
                por_inst[a.get("origem") or id(e)] += e.pontos()
        if not por_inst:
            continue
        centros = [(sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for ps in por_inst.values()]
        mont = (montagem_de or {}).get(x["nome"])
        if mont:
            # a chapa do chumbamento: os apoios, um de cada lado (pedido do usuário, 28/09), com o nome da
            # montagem — "CB1 + CH9"; a meia tesoura com outro apoio do outro lado leva o dela
            alvos = [min(centros, key=lambda q: q[0]), max(centros, key=lambda q: q[0])] if len(centros) >= 2 else centros
            pr = onde.get("montagem:" + mont)
            txt = mont + (" – PR.%02d" % pr if pr and pr != numero else "")
        else:
            alvos = [max(centros, key=lambda q: min((math.hypot(q[0] - a_[0], q[1] - a_[1]) for a_ in apontados), default=0.0)
                         - 1e-6 * q[0])]
            pr = onde.get(str(x["marca"])) or next((onde[m] for m in marcas if m in onde), None)
            txt = x["nome"] + (" – PR.%02d" % pr if pr and pr != numero else "")
        for alvo_m in alvos:
            apontados.append(alvo_m)
            ax, ay = alvo_m[0] / k + dx, alvo_m[1] / k + dy
            sx = -1.0 if alvo_m[0] < cx_m else 1.0
            sy = 1.0 if alvo_m[1] >= cy_m else -1.0
            d.add(Chamada(camada="TEXTO", alvo=(round(ax, 2), round(ay, 2)), posicao=(round(ax + 10.0 * sx, 2), round(ay + 12.0 * sy, 2)),
                          texto=txt, altura=2.5, atributos={"prancha": "chamada_chapa", "fonte": c["fonte"], "marca": x["marca"]}))


def _quantidade_da_celula(c: dict) -> int:
    """a quantidade do item da célula, ou a do título ("CB1 + CH9 – 11x")"""
    if c.get("qtd_local"):
        return int(c["qtd_local"])
    it = c.get("item") or {}
    if it.get("quantidade"):
        return int(it["quantidade"])
    m_q = re.search(r"–\s*(\d+)x\s*$", str(c.get("titulo") or ""))
    return int(m_q.group(1)) if m_q else 0


def _blocos_da_legenda(cels: Sequence[dict], detalhes: Sequence[dict] = ()) -> List[tuple]:
    """Os blocos da legenda da prancha: [(título, linhas)] — o que está NESTA PRANCHA (nome e
    quantidade: as tesouras, as peças e os detalhes da faixa, com a quantidade desta prancha) e as
    SIGLAS que aparecem nela (as dos nomes, das peças das tesouras e dos detalhes). Pedido do usuário,
    28/09: "as legendas devem ser só dos elementos que estão nessa prancha, precisa reduzir bastante"."""
    linhas, nomes = [], []
    for c in list(cels) + list(detalhes):
        it = c.get("item") or {}
        nome = str(it.get("nome") or c.get("montagem") or c.get("marca") or "")
        if not nome:
            continue                                  # vistas e cortes: o título deles basta
        q = _quantidade_da_celula(c)
        linha = (nome, "%02dx" % q if q else "")
        if linha not in linhas:
            linhas.append(linha)
        nomes.append(nome)
        nomes += [x["nome"] for x in (it.get("composicao") or [])]
    blocos = [("NESTA PRANCHA", linhas)] if linhas else []
    siglas = siglas_usadas(nomes)
    if siglas:
        blocos.append(("SIGLAS", siglas))
    return blocos


def _copia_local(c: dict, n: int) -> dict:
    """O detalhe de uma chapa (ou chumbamento) para a faixa da prancha da tesoura, com a quantidade
    desenhada nela: o título ("CH13 – 02x") e o peso total ("8,88 kg/pç  total 17,8 kg") pela
    quantidade local; o original segue para a prancha das chapas, com o total da obra."""
    textos = [e for e in c["entidades"] if isinstance(e, Texto)]
    titulo = max(textos, key=lambda t: t.altura) if textos else None
    ents = []
    for e in c["entidades"]:
        if isinstance(e, Texto):
            txt = e.texto
            if e is titulo:
                txt = re.sub(r"\s*–\s*\d+x\s*$", "", txt) + " – %02dx" % n
            m_kg = re.search(r"([\d.]+(?:,\d+)?)\s*kg/pç(\s+)total\s+[\d.,]+\s*kg", txt)
            if m_kg:
                kg = float(m_kg.group(1).replace(".", "").replace(",", "."))
                txt = txt[:m_kg.start()] + "%s kg/pç%stotal %s kg" % (m_kg.group(1), m_kg.group(2),
                                                                     ("%.1f" % (kg * n)).replace(".", ",")) + txt[m_kg.end():]
            if txt != e.texto:
                e = copy.copy(e)
                e.texto = txt
        ents.append(e)
    cc = dict(c, entidades=ents, local=True, qtd_local=n)
    if titulo is not None:
        cc["titulo"] = re.sub(r"\s*–\s*\d+x\s*$", "", titulo.texto) + " – %02dx" % n
    if c.get("item"):
        cc["item"] = dict(c["item"], quantidade=n)
    return cc


def _tabela(d, x0: float, y1: float, y0: float, titulo: str, linhas: Sequence[tuple], h: float = 2.0,
            passo: float = 3.2, cabecalho: Optional[tuple] = None, max_larg: Optional[float] = None) -> float:
    """Uma tabela de texto com título, as linhas correndo em colunas de cima para baixo e da esquerda
    para a direita entre y1 e y0. Com `d` None só mede. `max_larg`: o que não cabe nela é cortado, com
    "… +N" na última linha. Devolve a largura usada (mm)."""
    if not linhas:
        return 0.0
    linhas = list(linhas)
    h_tit = 2.5
    n_campos = max(len(l) for l in linhas)
    todas = ([cabecalho] if cabecalho else []) + list(linhas)
    # as letras da tabela (maiúsculas e números, "C127X50X17X#14") são mais largas que a média do texto
    larg_campo = [max(len(str(l[i])) if i < len(l) else 0 for l in todas) * 0.85 * h + (4.0 if i < n_campos - 1 else 0.0)
                  for i in range(n_campos)]
    larg_col = sum(larg_campo) + 6.0
    y_ini = y1 - h_tit - 2.5 - (passo if cabecalho else 0.0)
    por_col = max(1, int((y_ini - y0) // passo))
    n_col = -(-len(linhas) // por_col)
    if max_larg is not None and n_col * larg_col > max_larg + 0.01:
        n_col = max(1, int(max_larg // larg_col))
        cabe = n_col * por_col
        if len(linhas) > cabe:
            resto = len(linhas) - cabe + 1
            linhas = linhas[:cabe - 1] + [("…", "+%d" % resto)]
    if d is not None:
        atr = {"prancha": "legenda"}
        d.add(Texto(camada="TEXTO", posicao=(round(x0, 2), round(y1 - h_tit, 2)), texto=titulo, altura=h_tit,
                    atributos=dict(atr, campo="titulo_bloco")))
        for col in range(n_col):
            xc = x0 + col * larg_col
            if cabecalho:
                xx = xc
                for i, txt in enumerate(cabecalho):
                    d.add(Texto(camada="TEXTO", posicao=(round(xx, 2), round(y_ini + passo - h - 0.4, 2)), texto=str(txt),
                                altura=h * 0.9, atributos=dict(atr, campo="cabecalho")))
                    xx += larg_campo[i]
            for lin, linha in enumerate(linhas[col * por_col:(col + 1) * por_col]):
                xx = xc
                for i, txt in enumerate(linha):
                    if txt:
                        d.add(Texto(camada="TEXTO", posicao=(round(xx, 2), round(y_ini - (lin + 1) * passo + (passo - h), 2)),
                                    texto=str(txt), altura=h, atributos=dict(atr, campo="linha")))
                    xx += larg_campo[i]
    return max(n_col * larg_col, LARGURA_LETRA * h_tit * len(titulo) + 4.0)


def _legenda(d, leg: dict, x0: float, y0: float, y1: float, relacao: Sequence[tuple], onde: Dict[str, int],
             largura: Optional[float] = None) -> float:
    """A legenda da prancha, da esquerda para a direita a partir de x0: a relação das pranchas (na
    primeira), as peças (com a prancha em que cada uma está detalhada) e as siglas. Com `d` None só mede
    (a relação ainda desconhecida conta `n_rel` linhas). Com `largura`, nunca passa dela: as siglas ficam
    inteiras, e a relação e as peças, nessa ordem, perdem colunas (o que não cabe vira "… +N"). Devolve
    a largura (mm)."""
    topo = y1 - QUADRO_CABECALHO - 1.5
    base = y0 + 2.0
    blocos = []
    if leg.get("relacao"):
        rel = relacao or [("00/00", "X" * 40)] * max(1, int(leg.get("n_rel") or 1))
        rel = [(a, b if len(b) <= 48 else b[:47] + "…") for a, b in rel]
        blocos.append(["RELAÇÃO DAS PRANCHAS", rel, None])
    for titulo, linhas in leg["blocos"]:
        blocos.append([titulo, linhas, None])
    folga = 4.0
    # os blocos um embaixo do outro quando cabem na altura (a legenda fica estreita e sobra largura para
    # os DETALHES — pedido do usuário, 28/09: "reduzir bastante o tamanho")
    passo_t, gap_v = 3.2, 3.0
    alturas = [2.5 + 2.5 + len(l) * passo_t + (passo_t if c else 0.0) for t, l, c in blocos]
    if len(blocos) > 1 and sum(alturas) + gap_v * (len(blocos) - 1) <= topo - base:
        x = x0 + QUADRO_MARGEM
        y_ = topo
        larg_max = 0.0
        for (t, l, c), a_ in zip(blocos, alturas):
            larg_max = max(larg_max, _tabela(d, x, y_, y_ - a_ - 0.5, t, l, cabecalho=c, passo=passo_t))
            y_ -= a_ + gap_v
        return larg_max + 2 * QUADRO_MARGEM
    naturais = [_tabela(None, 0.0, topo, base, t, l, cabecalho=c) for t, l, c in blocos]
    limites = [None] * len(blocos)
    if largura is not None:
        disponivel = largura - 2 * QUADRO_MARGEM - folga * max(0, len(blocos) - 1)
        usadas = list(naturais)
        # quem encolhe: a relação primeiro, depois as peças (as siglas ficam inteiras)
        for i in [i for i, b in enumerate(blocos) if b[0] == "RELAÇÃO DAS PRANCHAS"] + \
                 [i for i, b in enumerate(blocos) if b[0] not in ("RELAÇÃO DAS PRANCHAS", "SIGLAS")]:
            sobra = disponivel - (sum(usadas) - usadas[i])
            if usadas[i] > sobra:
                limites[i] = max(sobra, 1.0)
                usadas[i] = _tabela(None, 0.0, topo, base, blocos[i][0], blocos[i][1], cabecalho=blocos[i][2],
                                    max_larg=limites[i])
    x = x0 + QUADRO_MARGEM
    for (t, l, c), lim in zip(blocos, limites):
        x += _tabela(d, x, topo, base, t, l, cabecalho=c, max_larg=lim) + folga
    return x - x0 + QUADRO_MARGEM - folga


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
            # e as camadas do desenho que não são as da tabela do DXF — um perfil por camada ("BANZOS
            # U100X50X#9", 28/09), as telhas por tipo —, na cor do CAD
            from saida.dxf import CAMADAS as _CAMADAS_DXF
            fixas = {n for n, _c, _t in _CAMADAS_DXF}
            cores.update({n: cam.cor for n, cam in d.camadas.items() if n not in fixas and n not in cores and getattr(cam, "cor", None)})
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
