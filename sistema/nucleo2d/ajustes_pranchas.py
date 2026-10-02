# -*- coding: utf-8 -*-
"""Os ajustes que o usuário faz nas pranchas geradas voltam na próxima geração (pedido do usuário, 29/09:
"criar uma função para que os ajustes que eu fizer na prancha vc aprenda … para que a próxima vez que for
gerado ele venha com os ajustes que eu fiz").

Como funciona:

* `marcar(junto)` — depois de montar as pranchas: cada entidade de uma célula já traz `cel` (a identidade
  da célula, estável entre gerações — a posição, o conjunto ou a montagem, não o título com a
  quantidade); aqui ela ganha `g`, a impressão do que foi gerado: a assinatura (a forma e o lugar dentro
  da célula) e o ponto de referência gerado. Os metadados guardam, por célula, a origem e todas as
  assinaturas (para saber o que foi apagado).
* `aprender(antigo, ajustes)` — antes de gravar as pranchas novas, o desenho gravado (com o que o
  usuário mexeu) é comparado com as impressões: célula movida ou escalada (o ajuste de toda a célula,
  pelo que a maioria das entidades dela andou), entidade movida dentro da célula (o texto, a chamada, o
  número da cota arrastado), o que foi apagado, e o que foi desenhado à mão. Vira
  `detalhamento/ajustes-pranchas.json`, com um diário.
* `aplicar(junto, ajustes)` — nas pranchas novas, cada ajuste vai para a mesma célula e a mesma entidade
  (pela assinatura); o que não se acha mais (a peça mudou) fica de fora e é contado.

As impressões ficam sempre as do gerado puro: a próxima comparação mede o ajuste inteiro, não só o novo.
"""
import collections
import copy
import hashlib
import json
import math
import os
import time
from typing import Dict, List, Optional, Tuple

from nucleo2d.desenho import Arco, Chamada, Circulo, Cota, Desenho, Hachura, Linha, Polilinha, Texto

#: Abaixo disto (mm de papel) não é ajuste — o arredondamento das coordenadas gravadas.
TOLERANCIA = 0.3
#: A escala só conta a partir de 0,5 % de diferença.
TOLERANCIA_ESCALA = 0.005
#: Quantas entradas o diário guarda.
DIARIO_MAX = 500
#: A repetição de uma entidade gerada a menos disto (mm de papel) da original é do gerador, não cópia à mão.
MESMO_LUGAR = 0.5
#: Tantas entidades quanto isto (e esta fração das da célula) "movidas dentro dela" não é ajuste do usuário:
#: a célula foi montada de outro jeito entre as gerações, e nada se aprende dela.
FORA_DO_LUGAR_MIN = 3
FORA_DO_LUGAR_FRACAO = 0.5
#: A célula gerada agora com menos disto das entidades da geração em que o ajuste foi aprendido (as mesmas
#: assinaturas): o gerador mudou a célula (uma regra nova arrumou o desenho dela), e o ajuste não vale mais —
#: reaplicado, deslocava de novo o que a regra já tinha posto no lugar (as telhas e os S.T. da Sala, 01/10).
SEMELHANCA_MINIMA = 0.9
#: Sem as assinaturas da geração antiga, a célula mudou se a caixa dela mudou mais que isto (mm de papel).
TOLERANCIA_CAIXA = 1.0
ARQUIVO = "ajustes-pranchas.json"


# ------------------------------------------------------------------ geometria
def _pontos(e) -> List[Tuple[float, float]]:
    if isinstance(e, Linha):
        return [tuple(e.a), tuple(e.b)]
    if isinstance(e, Polilinha):
        return [tuple(q) for q in e.vertices]
    if isinstance(e, (Circulo, Arco)):
        return [tuple(e.centro)]
    if isinstance(e, Texto):
        return [tuple(e.posicao)]
    if isinstance(e, Cota):
        return [tuple(e.p1), tuple(e.p2)]
    if isinstance(e, Hachura):
        return [tuple(q) for c in e.contornos for q in c]
    if isinstance(e, Chamada):
        return [tuple(e.alvo)]
    return []


def _ref(e) -> Optional[Tuple[float, float]]:
    pts = _pontos(e)
    return pts[0] if pts else None


def _forma(e) -> tuple:
    """O que identifica a entidade além do lugar: tipo, camada, texto e o desenho dela em volta do ponto
    de referência (arredondado a 0,5 mm)."""
    pts = _pontos(e)
    if not pts:
        return (type(e).__name__,)
    r = pts[0]
    rel = tuple((round((q[0] - r[0]) * 2), round((q[1] - r[1]) * 2)) for q in pts[1:40])
    extra = ()
    if isinstance(e, (Circulo, Arco)):
        extra = (round(e.raio * 2),)
    if isinstance(e, Texto):
        extra = (e.texto, round(e.altura, 2), round(e.angulo or 0.0, 1))
    if isinstance(e, Cota):
        extra = (e.modo, e.texto)
    if isinstance(e, Chamada):
        extra = (e.texto,)
    return (type(e).__name__, e.camada) + extra + rel


def assinatura(e, origem: Tuple[float, float]) -> str:
    """A forma e o lugar dentro da célula (a 0,5 mm): a mesma entidade na próxima geração."""
    r = _ref(e) or (0.0, 0.0)
    chave = (_forma(e), round((r[0] - origem[0]) * 2), round((r[1] - origem[1]) * 2))
    return hashlib.md5(repr(chave).encode("utf-8")).hexdigest()[:16]


def _transformar(e, f, s: float = 1.0):
    """A entidade com cada ponto levado por `f` (e os tamanhos pela escala `s`), no lugar."""
    if isinstance(e, Linha):
        e.a, e.b = f(e.a), f(e.b)
    elif isinstance(e, Polilinha):
        e.vertices = [f(q) for q in e.vertices]
    elif isinstance(e, (Circulo, Arco)):
        e.centro = f(e.centro)
        e.raio = e.raio * s
    elif isinstance(e, Texto):
        e.posicao = f(e.posicao)
        e.altura = round(e.altura * s, 3)
    elif isinstance(e, Cota):
        e.p1, e.p2 = f(e.p1), f(e.p2)
        if e.texto_pos:
            e.texto_pos = f(e.texto_pos)
        e.altura = round(e.altura * s, 3)
    elif isinstance(e, Hachura):
        e.contornos = [[f(q) for q in c] for c in e.contornos]
    elif isinstance(e, Chamada):
        e.alvo, e.posicao = f(e.alvo), f(e.posicao)
        e.altura = round(e.altura * s, 3)


def _mediana(vs: List[float]) -> float:
    vs = sorted(vs)
    n = len(vs)
    return 0.0 if not n else (vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2.0)


# ------------------------------------------------------------------ gerado
def _origens(junto: Desenho) -> Dict[str, Tuple[float, float]]:
    o = {}
    for info in junto.metadados.get("pranchas") or []:
        for c in info.get("celulas") or []:
            if c.get("id") and c.get("caixa"):
                o.setdefault(c["id"], (float(c["caixa"][0]), float(c["caixa"][1])))
    return o


def _tamanhos(junto: Desenho) -> Dict[str, List[float]]:
    """largura e altura da caixa de cada célula (mm de papel)"""
    t = {}
    for info in junto.metadados.get("pranchas") or []:
        for c in info.get("celulas") or []:
            cx = c.get("caixa")
            if c.get("id") and cx and len(cx) == 4:
                t.setdefault(c["id"], [round(float(cx[2]) - float(cx[0]), 2), round(float(cx[3]) - float(cx[1]), 2)])
    return t


#: Folga em volta da célula (mm de papel) para o desenho à mão contar como dela.
ANCORA_FOLGA = 15.0


def marcar(junto: Desenho) -> dict:
    """A impressão do gerado em cada entidade das células (`g`). Nos metadados do desenho fica só a origem de
    cada célula (`ajustaveis`); a lista de assinaturas por célula — grande (560 KB no depósito), e no desenho
    empurrava a chave `pranchas` para fora da janela que a listagem lê — volta ao chamador, que a guarda no
    arquivo de ajustes pela geração (`impressoes`)."""
    origens = _origens(junto)
    lista: Dict[str, list] = collections.defaultdict(list)
    n = 0
    for e in junto.entidades.values():
        a = e.atributos or {}
        cel = a.get("cel")
        if not cel or cel not in origens:
            continue
        s = assinatura(e, origens[cel])
        r = _ref(e)
        g = {"s": s, "r": [round(r[0], 3), round(r[1], 3)]}
        if isinstance(e, Cota) and e.texto_pos:
            g["t"] = [round(e.texto_pos[0], 3), round(e.texto_pos[1], 3)]
        if isinstance(e, Chamada):
            g["p"] = [round(e.posicao[0], 3), round(e.posicao[1], 3)]
        if isinstance(e, (Texto, Cota)):
            g["x"] = e.texto or ""          # o texto gerado: o trocado à mão é aprendido (B7, 02/10)
        e.atributos = dict(a, g=g)
        lista[cel].append(s)
        n += 1
    tam = _tamanhos(junto)
    junto.metadados["ajustaveis"] = {c: {"o": [round(origens[c][0], 3), round(origens[c][1], 3)], "cx": tam.get(c)}
                                     for c in lista}
    return {c: {"o": [round(origens[c][0], 3), round(origens[c][1], 3)], "cx": tam.get(c), "s": ss}
            for c, ss in lista.items()}


# ------------------------------------------------------------------ aprender
def _peca_solta(a: dict, e=None) -> bool:
    """geometria de peça gerada (furo, contorno, vista de uma posição) que perdeu a célula: não é desenho à mão — a
    peça é do 3D e só o gerador a desenha. Guardada como à mão, voltava em toda geração no lugar de antes, por cima
    de outra peça (os 2 furos da M117 (b) em cima da P27 (b) do depósito, 02/10). A anotação (cota, texto, chamada)
    copiada continua sendo do usuário."""
    if e is not None and (isinstance(e, (Texto, Cota, Chamada)) or str(getattr(e, "camada", "")).upper() in ("COTA", "TEXTO")):
        return False
    return bool(a.get("detalhe") and (a.get("posicao") or a.get("conjunto")))


def _a_mao(a: dict, e=None) -> bool:
    """desenhado à mão: o que o gerador não marcou (nem célula, nem quadro, nem folha), ou já guardado assim; nunca
    a peça gerada solta (_peca_solta)"""
    if _peca_solta(a, e):
        return False
    return bool(a.get("a_mao")) or not any(k in a for k in ("prancha", "cel", "fonte", "folha", "g", "prancha_numero"))


def aprender(antigo: Desenho, ajustes: dict) -> dict:
    """Os ajustes do desenho gravado (o que o usuário mexeu) em relação ao que foi gerado, por célula;
    substituem os guardados das células que estavam nele (as outras ficam). O desenhado à mão vai
    em `a_mao`. Devolve os ajustes atualizados."""
    ajustes = dict(ajustes or {})
    celulas = dict(ajustes.get("celulas") or {})
    diario = list(ajustes.get("diario") or [])
    # as impressões do gerado: no arquivo de ajustes pela geração do desenho; senão as do próprio desenho (o
    # formato de antes, com as assinaturas), senão só as origens (sem saber o que foi apagado)
    ajv = ((ajustes.get("impressoes") or {}).get(str(antigo.metadados.get("geracao") or ""))
           or antigo.metadados.get("ajustaveis") or {})
    quando = time.strftime("%Y-%m-%d %H:%M")
    if not ajv:
        return ajustes
    cx_antigo = _tamanhos(antigo)
    por_cel: Dict[str, list] = collections.defaultdict(list)
    a_mao = []
    for e in antigo.entidades.values():
        a = e.atributos or {}
        if a.get("cel") and a.get("g"):
            por_cel[a["cel"]].append(e)
        elif _a_mao(a, e):
            a_mao.append(e)
    for cel, info in ajv.items():
        o = tuple(info.get("o") or (0.0, 0.0))
        gerados = list(info.get("s") or [])
        ents = por_cel.get(cel, [])
        novo: dict = {}
        if not ents:
            novo = {"apagada": True}
            diario.append({"quando": quando, "celula": cel, "ajuste": "célula apagada"})
        else:
            # a mesma impressão mais vezes do que foi gerada (o gerado já repete linhas sobrepostas): as mais
            # perto do gerado são as originais, as a mais são cópias feitas à mão
            por_s: Dict[str, list] = collections.defaultdict(list)
            for e in ents:
                por_s[e.atributos["g"]["s"]].append(e)
            n_gerado = collections.Counter(gerados)
            originais = []
            for s_, es in por_s.items():
                g0 = es[0].atributos["g"]["r"]
                es.sort(key=lambda e: math.dist(_ref(e) or g0, g0))
                n_ = max(1, n_gerado.get(s_, 1))
                originais += es[:n_]
                for c_ in es[n_:]:
                    r_c = _ref(c_)
                    if r_c is not None and any(math.dist(r_c, _ref(o_) or g0) < MESMO_LUGAR for o_ in es[:n_]):
                        # em cima da original: é o gerado repetindo a peça (as tesouras projetadas umas sobre as
                        # outras), não uma cópia do usuário — guardada, voltava em toda geração por cima do
                        # desenho novo (9366 entidades no depósito desde 29/09, 30/09)
                        continue
                    a_mao.append(c_)
            G = [tuple(e.atributos["g"]["r"]) for e in originais]
            C = [_ref(e) for e in originais]
            # a escala: a distância de cada ponto ao centro, agora e no gerado
            gx, gy = sum(p[0] for p in G) / len(G), sum(p[1] for p in G) / len(G)
            cx, cy = sum(p[0] for p in C) / len(C), sum(p[1] for p in C) / len(C)
            razoes = [math.dist(c, (cx, cy)) / math.dist(g, (gx, gy)) for g, c in zip(G, C) if math.dist(g, (gx, gy)) > 5.0]
            s = _mediana(razoes) if len(razoes) >= 3 else 1.0
            if abs(s - 1.0) < TOLERANCIA_ESCALA:
                s = 1.0
            # o deslocamento da célula: p' = o + s (p − o) + d, pela mediana
            dx = _mediana([c[0] - (o[0] + s * (g[0] - o[0])) for g, c in zip(G, C)])
            dy = _mediana([c[1] - (o[1] + s * (g[1] - o[1])) for g, c in zip(G, C)])
            if abs(dx) < TOLERANCIA:
                dx = 0.0
            if abs(dy) < TOLERANCIA:
                dy = 0.0
            if s != 1.0 or dx or dy:
                novo["d"] = [round(dx, 3), round(dy, 3)]
                novo["s"] = round(s, 5)
                diario.append({"quando": quando, "celula": cel,
                               "ajuste": "célula movida %.1f, %.1f mm%s" % (dx, dy, "" if s == 1.0 else ", escala × %.3f" % s)})

            def leva(p):
                return (o[0] + s * (p[0] - o[0]) + dx, o[1] + s * (p[1] - o[1]) + dy)
            ents_aj = {}
            for e in originais:
                g = e.atributos["g"]
                esperado = leva(g["r"])
                r = _ref(e)
                aj = {}
                if math.dist(r, esperado) > TOLERANCIA:
                    aj["d"] = [round(r[0] - esperado[0], 3), round(r[1] - esperado[1], 3)]
                if isinstance(e, Cota) and e.texto_pos and g.get("t"):
                    esp_t = leva(g["t"])
                    esp_t = (esp_t[0] + aj.get("d", [0, 0])[0], esp_t[1] + aj.get("d", [0, 0])[1])
                    if math.dist(e.texto_pos, esp_t) > TOLERANCIA:
                        aj["t"] = [round(e.texto_pos[0] - esp_t[0], 3), round(e.texto_pos[1] - esp_t[1], 3)]
                if isinstance(e, Cota) and e.texto_pos and not g.get("t"):
                    aj["t_abs"] = [round(e.texto_pos[0] - r[0], 3), round(e.texto_pos[1] - r[1], 3)]
                if isinstance(e, (Texto, Cota)) and "x" in g and (e.texto or "") != (g["x"] or ""):
                    aj["x"] = e.texto or ""      # o texto (o título, a nota, o número da cota) trocado à mão
                if isinstance(e, Chamada) and g.get("p"):
                    esp_p = leva(g["p"])
                    esp_p = (esp_p[0] + aj.get("d", [0, 0])[0], esp_p[1] + aj.get("d", [0, 0])[1])
                    if math.dist(e.posicao, esp_p) > TOLERANCIA:
                        aj["p"] = [round(e.posicao[0] - esp_p[0], 3), round(e.posicao[1] - esp_p[1], 3)]
                if aj:
                    ents_aj[g["s"]] = aj
            if len(ents_aj) >= max(FORA_DO_LUGAR_MIN, FORA_DO_LUGAR_FRACAO * len(originais)):
                # quase tudo "movido dentro da célula": não foi o usuário — a célula foi montada de outro jeito
                # entre as duas gerações (outra escala, outro arranjo) e a comparação não fecha. Nada é
                # aprendido dela: o S.TI.2 do depósito ganhou "escala × 1,088 + 21 entidades movidas" e ficou
                # com as cotas fora da chapa (29/09)
                novo = {}
                ents_aj = {}
                diario.append({"quando": quando, "celula": cel,
                               "ajuste": "célula montada de outro jeito nesta geração: nada aprendido dela"})
            if ents_aj:
                novo["ents"] = ents_aj
                diario.append({"quando": quando, "celula": cel, "ajuste": "%d entidade(s) movida(s) dentro dela" % len(ents_aj)})
            presentes = set(por_s)
            apagadas = [s_ for s_ in gerados if s_ not in presentes]
            if apagadas:
                novo["apagadas"] = sorted(set(apagadas))
                diario.append({"quando": quando, "celula": cel, "ajuste": "%d entidade(s) apagada(s)" % len(set(apagadas))})
        if novo:
            # a geração e a caixa da célula gerada de que o ajuste foi tirado: se o gerador mudar a célula, ele não
            # volta (aplicar)
            novo["base"] = {"g": str(antigo.metadados.get("geracao") or ""), "cx": info.get("cx") or cx_antigo.get(cel),
                            "o": [round(o[0], 3), round(o[1], 3)]}
            celulas[cel] = novo
        else:
            celulas.pop(cel, None)
    ajustes["celulas"] = celulas
    # a caixa de cada célula como está no desenho gravado (a gerada, levada pelo ajuste aprendido agora): o desenho à
    # mão dentro de uma célula fica preso a ela e anda com ela na próxima geração (B7, 02/10) — antes ficava no lugar
    # da folha e a célula, refeita noutro canto, o deixava para trás
    caixas = {}
    for cel, info in ajv.items():
        o_, cx_ = info.get("o"), info.get("cx") or cx_antigo.get(cel)
        if not o_ or not cx_:
            continue
        aj_ = celulas.get(cel) or {}
        d_, s_ = aj_.get("d") or [0.0, 0.0], float(aj_.get("s") or 1.0)
        x0, y0 = float(o_[0]) + d_[0], float(o_[1]) + d_[1]
        caixas[cel] = (x0, y0, x0 + float(cx_[0]) * s_, y0 + float(cx_[1]) * s_)

    def ancora(e):
        r = _ref(e)
        if r is None:
            return None
        dentro = [(c[2] - c[0]) * (c[3] - c[1]) for c in caixas.values()]
        melhor = None
        for (cel, c), area in zip(caixas.items(), dentro):
            if c[0] - ANCORA_FOLGA <= r[0] <= c[2] + ANCORA_FOLGA and c[1] - ANCORA_FOLGA <= r[1] <= c[3] + ANCORA_FOLGA:
                if melhor is None or area < melhor[1]:
                    melhor = (cel, area)
        return {"cel": melhor[0], "o": [round(caixas[melhor[0]][0], 3), round(caixas[melhor[0]][1], 3)]} if melhor else None
    guardado = Desenho(nome="a_mao", escala=1.0)
    for e in a_mao:
        n = copy.deepcopy(e)
        # a cópia de uma peça gerada vira desenho à mão: sem as marcas do gerado, que a apagariam depois
        a = {k: v for k, v in (n.atributos or {}).items() if k not in ("cel", "g", "fonte", "prancha_numero")}
        a["a_mao"] = True
        anc = ancora(e)
        if anc:
            a["ancora"] = anc
        else:
            a.pop("ancora", None)
        n.atributos = a
        guardado.add(n)
    ajustes["a_mao"] = guardado.dict() if a_mao else None
    if a_mao:
        diario.append({"quando": quando, "celula": "", "ajuste": "%d entidade(s) desenhada(s) à mão guardadas" % len(a_mao)})
    ajustes["diario"] = diario[-DIARIO_MAX:]
    return ajustes


# ------------------------------------------------------------------ aplicar
def aplicar(junto: Desenho, ajustes: dict) -> dict:
    """Os ajustes nas pranchas novas (já marcadas): cada célula e cada entidade pela assinatura; o
    desenhado à mão entra como estava. Devolve a contagem."""
    rel = {"celulas": 0, "entidades": 0, "apagadas": 0, "a_mao": 0, "sem_alvo": 0, "descartadas": 0}
    celulas = (ajustes or {}).get("celulas") or {}
    origens = {c: tuple(v["o"]) for c, v in (junto.metadados.get("ajustaveis") or {}).items()}
    por_cel: Dict[str, list] = collections.defaultdict(list)
    for e in junto.entidades.values():
        cel = (e.atributos or {}).get("cel")
        if cel:
            por_cel[cel].append(e)
    # o gerador mudou a célula desde que o ajuste foi aprendido: ele sai (e vai para o diário), em vez de deslocar
    # de novo o que a regra nova já arrumou
    tam = _tamanhos(junto)
    descartar = [cel for cel in celulas if por_cel.get(cel) and cel in origens
                 and _gerador_mudou(cel, celulas[cel], ajustes, por_cel[cel], tam.get(cel))]
    if descartar:
        quando = time.strftime("%Y-%m-%d %H:%M")
        diario = list(ajustes.get("diario") or [])
        for cel in descartar:
            celulas.pop(cel, None)
            diario.append({"quando": quando, "celula": cel, "ajuste": "descartado: o gerador mudou a célula"})
        ajustes["diario"] = diario[-DIARIO_MAX:]
        rel["descartadas"] = len(descartar)
        rel["descartadas_celulas"] = list(descartar)      # o CAD avisa quais (antes só no diário)
    # a célula igual, mas posta em outro lugar da folha (outra prancha, outro canto): o movimento dela, medido do lugar
    # antigo, a jogaria em cima de outra; ficam a escala e o que foi mexido dentro dela
    for cel in list(celulas):
        aj = celulas[cel]
        o_velho = _origem_base(cel, aj, ajustes)
        if not aj.get("d") or cel not in origens or o_velho is None:
            continue
        if math.dist(o_velho, origens[cel]) <= TOLERANCIA_CAIXA:
            continue
        aj = {k: v for k, v in aj.items() if k != "d"}
        if float(aj.get("s") or 1.0) == 1.0:
            aj.pop("s", None)
        if any(k in aj for k in ("s", "ents", "apagadas", "apagada")):
            celulas[cel] = aj
        else:
            celulas.pop(cel)
        diario = list(ajustes.get("diario") or [])
        diario.append({"quando": time.strftime("%Y-%m-%d %H:%M"), "celula": cel,
                       "ajuste": "movimento descartado: o gerador pôs a célula em outro lugar"})
        ajustes["diario"] = diario[-DIARIO_MAX:]
        rel["descartadas"] += 1
        rel.setdefault("descartadas_celulas", []).append(cel)
    tirar = []
    lugar = {cel: tuple(o) for cel, o in origens.items()}       # onde cada célula ficou (o desenho à mão a segue)
    for cel, aj in celulas.items():
        ents = por_cel.get(cel)
        if not ents or cel not in origens:
            rel["sem_alvo"] += 1
            continue
        if aj.get("apagada"):
            tirar += [e.id for e in ents]
            rel["apagadas"] += len(ents)
            continue
        o = origens[cel]
        s = float(aj.get("s") or 1.0)
        dx, dy = (aj.get("d") or [0.0, 0.0])
        apagadas = set(aj.get("apagadas") or [])
        ents_aj = aj.get("ents") or {}
        achadas = set()
        if dx or dy or s != 1.0:
            rel["celulas"] += 1
        for e in ents:
            sg = (e.atributos.get("g") or {}).get("s")
            if sg in apagadas:
                tirar.append(e.id)
                rel["apagadas"] += 1
                continue
            ex = ents_aj.get(sg) or {}
            ed = ex.get("d") or [0.0, 0.0]
            f = (lambda p, ed=ed: (round(o[0] + s * (p[0] - o[0]) + dx + ed[0], 3),
                                   round(o[1] + s * (p[1] - o[1]) + dy + ed[1], 3)))
            if dx or dy or s != 1.0 or ex:
                _transformar(e, f, s)
            if ex:
                achadas.add(sg)
                if isinstance(e, Cota):
                    if ex.get("t") and e.texto_pos:
                        e.texto_pos = (round(e.texto_pos[0] + ex["t"][0], 3), round(e.texto_pos[1] + ex["t"][1], 3))
                    elif ex.get("t_abs"):
                        e.texto_pos = (round(e.p1[0] + ex["t_abs"][0], 3), round(e.p1[1] + ex["t_abs"][1], 3))
                if isinstance(e, Chamada) and ex.get("p"):
                    e.posicao = (round(e.posicao[0] + ex["p"][0], 3), round(e.posicao[1] + ex["p"][1], 3))
                if "x" in ex and isinstance(e, (Texto, Cota)):
                    e.texto = ex["x"] or (None if isinstance(e, Cota) else "")
        lugar[cel] = (o[0] + dx, o[1] + dy)
        rel["entidades"] += len(achadas)
        rel["sem_alvo"] += len(set(ents_aj) - achadas)
    for i in tirar:
        junto.entidades.pop(i, None)
    bruto = (ajustes or {}).get("a_mao")
    if bruto:
        tmp = Desenho.de_dict(bruto)
        for nome_c, cam in tmp.camadas.items():
            junto.camadas.setdefault(nome_c, cam)
        for e in tmp.entidades.values():
            if _peca_solta(e.atributos or {}, e):
                rel["pecas_soltas"] = rel.get("pecas_soltas", 0) + 1     # guardada antes da regra: não volta
                continue
            anc = (e.atributos or {}).get("ancora")
            if anc and anc.get("cel") in lugar and anc.get("o"):
                nx, ny = lugar[anc["cel"]]
                ddx, ddy = nx - float(anc["o"][0]), ny - float(anc["o"][1])
                if abs(ddx) > TOLERANCIA or abs(ddy) > TOLERANCIA:
                    _transformar(e, lambda p, ddx=ddx, ddy=ddy: (round(p[0] + ddx, 3), round(p[1] + ddy, 3)), 1.0)
                    rel["a_mao_movidas"] = rel.get("a_mao_movidas", 0) + 1
            junto.add(e)
            rel["a_mao"] += 1
    return rel


def _origem_base(cel: str, aj: dict, ajustes: dict) -> Optional[Tuple[float, float]]:
    """a origem da célula gerada de que o ajuste foi tirado (a base dele, ou a impressão guardada)"""
    base = aj.get("base") or {}
    if base.get("o"):
        return tuple(base["o"])
    imps = ajustes.get("impressoes") or {}
    v = (imps.get(base.get("g")) or {}).get(cel) if base.get("g") else None
    v = v or next((x.get(cel) for x in imps.values() if (x.get(cel) or {}).get("o")), None)
    return tuple(v["o"]) if v and v.get("o") else None


def _gerador_mudou(cel: str, aj: dict, ajustes: dict, ents_novas: Sequence, cx_novo: Optional[List[float]]) -> bool:
    """A célula gerada agora é outra que a do ajuste? Pelas assinaturas da geração em que ele foi aprendido (a
    fração das entidades iguais, SEMELHANCA_MINIMA); sem elas, pelo tamanho da caixa gerada (TOLERANCIA_CAIXA);
    sem nenhum dos dois (o ajuste do formato antigo), ele vale como antes."""
    base = aj.get("base") or {}
    imps = ajustes.get("impressoes") or {}
    velhas = None
    if base.get("g") and base["g"] in imps:
        velhas = (imps[base["g"]].get(cel) or {}).get("s")
    elif not base:
        velhas = next(((v.get(cel) or {}).get("s") for v in imps.values() if (v.get(cel) or {}).get("s")), None)
    if velhas:
        a = collections.Counter(velhas)
        b = collections.Counter(((e.atributos or {}).get("g") or {}).get("s") for e in ents_novas)
        iguais = sum((a & b).values())
        return iguais < SEMELHANCA_MINIMA * max(sum(a.values()), sum(b.values()), 1)
    cx_velho = base.get("cx") or next(((v.get(cel) or {}).get("cx") for v in imps.values() if (v.get(cel) or {}).get("cx")), None)
    if cx_velho and cx_novo:
        return abs(cx_velho[0] - cx_novo[0]) > TOLERANCIA_CAIXA or abs(cx_velho[1] - cx_novo[1]) > TOLERANCIA_CAIXA
    return False


# ------------------------------------------------------------------ arquivo
def ler(caminho: str) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gravar(caminho: str, ajustes: dict) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ajustes, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)
