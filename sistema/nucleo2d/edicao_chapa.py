# -*- coding: utf-8 -*-
"""Edição de chapa (pedido do usuário, 02/10): "selecionar a chapa no 2D ou 3D e ter um menu de edição, com as opções
de editar no local — vendo como a peça interage com os elementos ao redor para pegar alguma referência — e o ambiente
de edição, só a peça, para mudar furos, tamanhos, recortes; quando terminar, o 3D e o 2D ficam exatamente iguais".

O ambiente é o desenho "Detalhe – <marca>" (a chapa paramétrica com os furos editáveis, que o "Aplicar furos e tamanho
ao modelo 3D" leva a todas as chapas da posição). Este módulo acrescenta a ele:

* `referencias_no_plano`: no modo "no local", as peças em volta da chapa cortadas no plano dela (uma fatia de cada lado),
  com o nome de produção, e os parafusos que a atravessam — na camada REFERENCIA, travada, no mesmo sistema do desenho
  da chapa (os eixos dela e o giro da posição montada). Servem para medir e encaixar; nada delas vai ao modelo.
* `marcar_edicao`: os metadados do modo (marca, nome, quantas peças no modelo, modo) que o CAD usa para a faixa
  "EDITANDO … · Concluir · Cancelar".
"""
import math
from typing import Dict, List, Optional

from nucleo2d.desenho import Camada2D, Circulo, Desenho, Polilinha, Texto

#: Camada das peças de referência no modo "no local".
CAMADA_REFERENCIA = "REFERENCIA"
#: Até onde em volta da chapa (mm) as peças entram como referência, e a fatia (mm) de cada lado do plano dela.
RAIO_REFERENCIA = 350.0
FATIA_REFERENCIA = 150.0


def _sistema_da_chapa(pos):
    """(c, e1, e2, e3, u0, v0, giro) que leva um ponto do mundo ao desenho da chapa: o mesmo sistema do contorno da
    posição (analisar) e o giro da posição montada (_giro_montado), como desenho_da_posicao desenha."""
    from saida.detalhamento import _autovetores
    from nucleo2d.detalhe.base import _dot, _sub
    from nucleo2d.detalhe.celulas import _giro_montado
    if not pos.eixos or not pos.vertices:
        return None
    e1, e2, e3 = pos.eixos
    c, _ = _autovetores(pos.vertices)
    us = [_dot(_sub(v, c), e1) for v in pos.vertices]
    vs = [_dot(_sub(v, c), e2) for v in pos.vertices]
    return c, e1, e2, e3, min(us), min(vs), _giro_montado(pos)


def _no_desenho(sis, p):
    from nucleo2d.detalhe.base import _dot, _sub
    c, e1, e2, _e3, u0, v0, giro = sis
    x, y = _dot(_sub(p, c), e1) - u0, _dot(_sub(p, c), e2) - v0
    if giro:
        phi, tx, ty = giro
        cs, sn = math.cos(phi), math.sin(phi)
        x, y = x * cs - y * sn + tx, x * sn + y * cs + ty
    return (round(x, 2), round(y, 2))


def _recortar_na_janela(poli, janela):
    """O polígono recortado no retângulo (x0, y0, x1, y1), pelos quatro lados (Sutherland–Hodgman)."""
    x0, y0, x1, y1 = janela
    for dentro, cruza in ((lambda q: q[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
                          (lambda q: q[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
                          (lambda q: q[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
                          (lambda q: q[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))):
        saida = []
        for i in range(len(poli)):
            a, b = poli[i], poli[(i + 1) % len(poli)]
            if dentro(a):
                saida.append(a)
            if dentro(a) != dentro(b):
                saida.append(cruza(a, b))
        poli = saida
        if not poli:
            return []
    return [(round(q[0], 2), round(q[1], 2)) for q in poli]


def referencias_no_plano(doc, pos, nomes: Optional[Dict[str, str]] = None, raio: float = RAIO_REFERENCIA,
                         fatia: float = FATIA_REFERENCIA) -> List[dict]:
    """As peças em volta da instância de `pos` (a da referência do detalhe) cortadas na fatia do plano da chapa, no
    sistema do desenho dela: [{"tipo": "contorno", "pontos", "nome"} | {"tipo": "parafuso", "centro", "raio"}]."""
    from nucleo2d.detalhe.base import _pecas, _fixadores, _marcas, _dot, _sub, _caixa
    from nucleo2d.detalhe.conjuntos import _cortar_na_fatia, _casco
    from saida.detalhamento import _autovetores
    sis = _sistema_da_chapa(pos)
    if sis is None:
        return []
    c, e1, e2, e3, *_ = sis
    ws = [_dot(_sub(v, c), e3) for v in pos.vertices]
    w0, w1 = min(ws) - fatia, max(ws) + fatia
    xs = [v[0] for v in pos.vertices]
    ys = [v[1] for v in pos.vertices]
    zs = [v[2] for v in pos.vertices]
    caixa = ((min(xs) - raio, max(xs) + raio), (min(ys) - raio, max(ys) + raio), (min(zs) - raio, max(zs) + raio))
    pecas, _ = _pecas(doc)
    fixadores = _fixadores(doc)
    proprias = {tuple(round(q, 1) for q in v) for v in pos.vertices[:8]}
    fora: List[dict] = []
    # a janela no plano da chapa: a peça comprida (a terça de 6 m na fatia) só até `raio` em volta dela
    pp = [_no_desenho(sis, v) for v in pos.vertices]
    janela = (min(q[0] for q in pp) - raio, min(q[1] for q in pp) - raio, max(q[0] for q in pp) + raio, max(q[1] for q in pp) + raio)
    # o plano do corte em w: a peça cortada na fatia (contada no sistema da chapa: w = e3·(p − c))
    w_dir = tuple(e3)
    base_w = _dot(c, w_dir)
    for e in pecas:
        cx = _caixa(e)
        if any(cx[i][1] < caixa[i][0] or cx[i][0] > caixa[i][1] for i in range(3)):
            continue
        if {tuple(round(q, 1) for q in v) for v in e.vertices[:8]} == proprias:
            continue                                  # a própria chapa
        pts = _cortar_na_fatia(e, w_dir, base_w + w0, base_w + w1)
        if len(pts) < 3:
            continue
        casco = _recortar_na_janela(_casco([_no_desenho(sis, q) for q in pts]), janela)
        if len(casco) < 3:
            continue
        m = str(_marcas(e).get("posicao") or e.nome or "")
        fora.append({"tipo": "contorno", "pontos": casco, "nome": (nomes or {}).get(m) or m})
    # os parafusos que atravessam a chapa (o eixo perpendicular a ela): o círculo onde cruzam o plano
    for f in fixadores:
        if len(f.vertices or []) < 4:
            continue
        cf = tuple(sum(v[i] for v in f.vertices) / len(f.vertices) for i in range(3))
        if any(not (caixa[i][0] <= cf[i] <= caixa[i][1]) for i in range(3)):
            continue
        cc, pca = _autovetores(f.vertices)
        ext = [max(_dot(_sub(v, cc), a) for v in f.vertices) - min(_dot(_sub(v, cc), a) for v in f.vertices) for a in pca]
        if ext[0] <= 1.5 * ext[1]:
            continue                                  # só o parafuso comprido tem eixo pela forma
        eixo = pca[0]
        den = _dot(eixo, e3)
        if abs(den) < 0.9:
            continue
        t = _dot(_sub(c, cc), e3) / den
        if abs(t) > ext[0] / 2.0 + fatia:
            continue
        p = tuple(cc[i] + eixo[i] * t for i in range(3))
        fora.append({"tipo": "parafuso", "centro": _no_desenho(sis, p), "raio": round(min(ext[1], ext[2]) / 2.0, 1)})
    return fora


def acrescentar_referencias(d: Desenho, refs: List[dict], chapa=None) -> int:
    """As referências no desenho, na camada REFERENCIA travada (cinza): contornos fechados com o nome no meio, e os
    parafusos em círculo. Devolve quantas entraram."""
    if CAMADA_REFERENCIA not in d.camadas:
        d.camadas[CAMADA_REFERENCIA] = Camada2D(CAMADA_REFERENCIA, "#7a8496", espessura=0.18)
    d.camadas[CAMADA_REFERENCIA].bloqueada = True
    atr = {"referencia": True}
    h = 2.0 * float(d.escala or 1.0)
    n = 0
    vistos = set()
    for r in refs:
        if r["tipo"] == "contorno":
            d.add(Polilinha(camada=CAMADA_REFERENCIA, vertices=[tuple(q) for q in r["pontos"]], fechada=True,
                            atributos=dict(atr, nome=r.get("nome") or "")))
            nome = r.get("nome") or ""
            if nome and nome not in vistos:
                vistos.add(nome)
                cx = sum(q[0] for q in r["pontos"]) / len(r["pontos"])
                cy = sum(q[1] for q in r["pontos"]) / len(r["pontos"])
                if chapa:
                    # o nome no lado da peça mais longe da chapa (no meio, caía em cima do título dela)
                    lx, ly = chapa
                    lon = max(r["pontos"], key=lambda q: math.hypot(q[0] - lx, q[1] - ly))
                    cx, cy = (cx + 2.0 * lon[0]) / 3.0, (cy + 2.0 * lon[1]) / 3.0
                d.add(Texto(camada=CAMADA_REFERENCIA, posicao=(round(cx, 2), round(cy, 2)), texto=nome, altura=round(h / d.escala, 2),
                            alinhamento="centro", atributos=dict(atr)))
        else:
            d.add(Circulo(camada=CAMADA_REFERENCIA, centro=tuple(r["centro"]), raio=float(r["raio"]), atributos=dict(atr, parafuso=True)))
        n += 1
    return n


def marcar_edicao(d: Desenho, marca: str, nome: str, quantidade: int, modo: str) -> None:
    """Os metadados do modo de edição que o CAD lê para a faixa e para o Concluir."""
    d.metadados["edicao"] = {"marca": marca, "nome": nome or marca, "quantidade": int(quantidade or 0),
                             "modo": "local" if modo == "local" else "isolada"}
