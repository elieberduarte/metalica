# -*- coding: utf-8 -*-
"""Treliças lidas: cada elevação do projeto ("TESOURA 16 - 3X") ao lado do que a montagem pela
planta leu dela — o bloco que entrou no modelo — e onde cada cópia foi colocada.

Serve para conferir o "lego" peça a peça, como o projetista desenhou: o desenho original da
elevação (tudo o que está na moldura dela: linhas, arcos, textos, cotas), as barras lidas
(banzos, montantes, diagonais, no mesmo referencial — s ao longo do banzo inferior a partir
da ponta esquerda, h acima do eixo dele), as quantidades (o título × o modelo) e o encaixe de
cada cópia no vão da planta (com os eixos do projeto). A tela /trelicas mostra; o arquivo
`trelicas-lidas.json` do projeto guarda (a montagem pela planta o refaz a cada vez).
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional

__all__ = ["montar_lista", "ENCAIXE_MAX", "JUSTO"]

ENCAIXE_MAX = 200.0     # mm: acima disso o encaixe no vão é apontado (o mesmo limite dos avisos)
JUSTO = 50.0            # mm: até isso a elevação cabe no vão
CELULA = 5000.0         # mm: grade para achar as entidades de cada moldura
_RX_TITULO = re.compile(r"-\s*\d+\s*X\s*$", re.I)


def _ponto(e) -> Optional[tuple]:
    t = e.get("tipo")
    if t == "linha":
        return (e["a"][0], e["a"][1])
    if t == "polilinha" and e.get("vertices"):
        return (e["vertices"][0][0], e["vertices"][0][1])
    if t in ("arco", "circulo"):
        if t == "arco":
            a0, a1 = e["inicio"] % 360.0, e["fim"] % 360.0
            meio = math.radians(a0 + ((a1 - a0) % 360.0) / 2.0)
            return (e["centro"][0] + e["raio"] * math.cos(meio), e["centro"][1] + e["raio"] * math.sin(meio))
        return (e["centro"][0], e["centro"][1])
    if t == "texto":
        return (e["posicao"][0], e["posicao"][1])
    return None


def _no_referencial(e, x0: float, y0: float, escala: float) -> Optional[dict]:
    """a entidade do desenho no referencial da elevação, em mm inteiros e chaves curtas"""
    t = e.get("tipo")

    def P(p):
        return [round(p[0] - x0), round(p[1] - y0)]
    if t == "linha":
        return {"t": "l", "p": P(e["a"]) + P(e["b"])}
    if t == "polilinha":
        return {"t": "p", "v": [P(v) for v in e["vertices"]], "f": bool(e.get("fechada"))}
    if t == "arco":
        return {"t": "a", "c": P(e["centro"]), "r": round(e["raio"]), "i": round(e["inicio"], 2), "f": round(e["fim"], 2)}
    if t == "circulo":
        return {"t": "c", "c": P(e["centro"]), "r": round(e["raio"])}
    if t == "texto":
        txt = str(e.get("texto") or "").strip()
        if not txt:
            return None
        return {"t": "x", "p": P(e["posicao"]), "s": txt[:80], "h": round(float(e.get("altura") or 2.5) * escala),
                "g": round(float(e.get("angulo") or 0.0), 1)}
    return None


def montar_lista(ents: List[dict], elevacoes: Dict[str, object], contagem: Dict[str, int], encaixe: List[dict],
                 eixos_p: Optional[dict], escala: float, bonito) -> List[dict]:
    """uma entrada por elevação lida (as usadas na planta e as que ficaram de fora), na ordem do
    nome; `encaixe` são as cópias colocadas (ponto já no modelo), `eixos_p` os eixos da planta
    no modelo, `bonito` o nome com acento ("TRANSICAO 14" → "TRANSIÇÃO 14")."""
    from nucleo3d import eixos as _eixos
    ex = _eixos.de_dict(eixos_p)
    segs = _eixos.segmentos(ex) if ex else []
    for e in (eixos_p or {}).get("extras") or []:
        segs.append({"nome": e["nome"], "tipo": "extra", "a": list(e["a"]) + [0.0], "b": list(e["b"]) + [0.0]})

    grade: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for e in ents:
        p = _ponto(e)
        if p is not None:
            grade[(int(p[0] // CELULA), int(p[1] // CELULA))].append(e)

    por_nome: Dict[str, List[dict]] = collections.defaultdict(list)
    for c in encaixe:
        por_nome[c["peca"]].append(c)

    out = []
    for nome, el in sorted(elevacoes.items(), key=lambda kv: _ordem(bonito(kv[0]))):
        nb = bonito(nome)
        x0, y0, x1, y1 = el.caixa
        tx, ty = el.titulo_em
        el_titulo = next((e for e in grade.get((int(tx // CELULA), int(ty // CELULA)), [])
                          if e.get("tipo") == "texto" and tuple(e["posicao"][:2]) == (tx, ty)), None)
        # a moldura da elevação: o desenho, a nota dos perfis e o título embaixo (com a escala), as
        # marcas ST e as cotas em cima — sem o título da elevação de cima nem o desenho da de baixo
        cx = (min(x0, tx) - 400.0, min(y0, ty) - 450.0, x1 + 400.0, y1 + 900.0)
        desenho = []
        for gx in range(int(cx[0] // CELULA), int(cx[2] // CELULA) + 1):
            for gy in range(int(cx[1] // CELULA), int(cx[3] // CELULA) + 1):
                for e in grade.get((gx, gy), []):
                    p = _ponto(e)
                    if cx[0] <= p[0] <= cx[2] and cx[1] <= p[1] <= cx[3]:
                        if e.get("tipo") == "texto" and e is not el_titulo and _RX_TITULO.search(str(e.get("texto") or "")):
                            continue            # o título de outra elevação
                        d = _no_referencial(e, el.x_esq, el.y_base, escala)
                        if d:
                            desenho.append(d)
        membros = [[m.papel, round(m.s0), round(m.h0), round(m.s1), round(m.h1), 1 if m.altura_linha > 0 else 0]
                   for m in el.membros]
        hs = [h for m in el.membros for h in (m.h0, m.h1)]
        colocadas = []
        for c in por_nome.get(nb, []):
            onde = _eixos.onde(c["ponto"], segs) if segs else ""
            colocadas.append({"conjunto": c["conjunto"], "vao": c["vao"], "elevacao": c["elevacao"], "dif": c["dif"],
                              "onde": onde, "ponto": c["ponto"], "deitada": bool(c.get("deitada")),
                              "a_conferir": abs(c["dif"]) > ENCAIXE_MAX or not c.get("centrada", True)})
        no_modelo = int(contagem.get(nome, 0))
        pendencias = []
        if no_modelo == 0:
            pendencias.append("não entrou no modelo: o nome não aparece na planta")
        elif no_modelo != el.qtd:
            pendencias.append("o título pede %d, o modelo tem %d" % (el.qtd, no_modelo))
        n_enc = sum(1 for c in colocadas if c["a_conferir"])
        if n_enc:
            pendencias.append("%d cópia(s) com mais de %d cm de diferença entre a elevação e o vão" % (n_enc, ENCAIXE_MAX / 10))
        if not (el.banzo or {}).get("perfil"):
            pendencias.append("sem a nota do perfil do banzo")
        out.append({
            "nome": nb, "familia": nb.split()[0], "qtd_projeto": el.qtd, "no_modelo": no_modelo,
            "comprimento": round(el.comprimento), "altura": round(max(hs) - min(hs)) if hs else 0,
            "banzo": (el.banzo or {}).get("perfil"), "alma": (el.alma or {}).get("perfil"),
            "alma_mult": int((el.alma or {}).get("mult") or 1),
            "membros": membros, "marcas_terca": [round(s) for s in el.marcas_terca],
            "contagem_membros": dict(collections.Counter(m.papel for m in el.membros)),
            "avisos": list(el.avisos), "colocadas": colocadas, "pendencias": pendencias,
            "situacao": "conferir" if pendencias else "ok", "desenho": desenho,
        })
    return out


def _ordem(nome: str):
    """TESOURA 2 antes de TESOURA 10"""
    partes = nome.rsplit(" ", 1)
    if len(partes) == 2 and partes[1].isdigit():
        return (partes[0], int(partes[1]), "")
    return (nome, 0, nome)
