# -*- coding: utf-8 -*-
"""Identificação para modelagem: o projeto recebido lido do Original, etapa por etapa, até o modelo 3D.

Pedido do usuário (20/10/2026, depois do Hangar Almayer — Projeto/ANALISES/Montagem/Caminho-DXF-para-3D-Hangar-Almayer-
2026-10-20.pdf): "a primeira importação poderia ser somente a leitura, quando o projeto estiver dentro do sistema vamos
começar a parte da identificação para modelagem, e deixar esse projeto importado como original que não é mexido … o
sistema faz uma varredura no desenho e tenta identificar essa planta de locação, nessa o usuário pode fazer os ajustes,
corrigir os eixos e níveis … após isso vai para as tesouras … depois as terças … o usuário pede para montar o modelo 3D".
Escolhas dele: painel de etapas na Montagem; uma varredura só, que preenche todas as etapas como sugestão; o caminho
antigo (ler e já gerar o 3D) sai do menu.

Fase 1 (aqui): o que a importação leu, para a tela mostrar antes de qualquer modelagem — as folhas do projeto e a
unidade em que as cotas estão escritas (no Hangar, cotas em centímetro sobre o desenho em milímetro: a leitura antiga
tomou "495" como 495 mm e as vistas saíram 10 vezes menores).
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional

from nucleo2d.desenho import Cota, Desenho, Texto

_FOLHA = re.compile(r"FOLHA\s*(\d+)\s*/\s*(\d+)", re.I)
_NUMERO = re.compile(r"^\s*[\d.,]+\s*$")
#: a unidade das cotas pela razão medida no desenho (mm) ÷ número escrito
UNIDADES = ((1.0, "mm", "milímetro"), (10.0, "cm", "centímetro"), (1000.0, "m", "metro"))


def _valor(texto: str) -> Optional[float]:
    t = str(texto or "").strip()
    t = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", t)                 # códigos de formatação do MTEXT
    if not _NUMERO.match(t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def _medida(c: Cota) -> float:
    dx, dy = c.p2[0] - c.p1[0], c.p2[1] - c.p1[1]
    if c.modo == "h":
        return abs(dx)
    if c.modo == "v":
        return abs(dy)
    return math.hypot(dx, dy)


def unidade_das_cotas(des: Desenho) -> Optional[dict]:
    """Em que unidade os números das cotas estão escritos, pela medida no desenho (em mm reais) ÷ o número: a mais
    votada entre mm, cm e m. A cota sem texto escrito (o CAD mostra a medida) não conta. None sem cota legível."""
    votos: Dict[str, int] = collections.Counter()
    exemplo: Dict[str, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Cota) or not e.texto:
            continue
        v = _valor(e.texto)
        L = _medida(e)
        if not v or L < 1.0:
            continue
        r = math.log10(L / v)
        fator, sigla, _nome = min(UNIDADES, key=lambda u: abs(math.log10(u[0]) - r))
        if abs(math.log10(fator) - r) > 0.05:                  # mais de 12 % fora: escala própria (detalhe ampliado)
            continue
        votos[sigla] += 1
        if sigla not in exemplo or v > exemplo[sigla]["texto_num"]:
            exemplo[sigla] = {"texto": str(e.texto).strip(), "texto_num": v, "mede_mm": round(L, 1)}
    if not votos:
        return None
    sigla, n = votos.most_common(1)[0]
    fator, _s, nome = next(u for u in UNIDADES if u[1] == sigla)
    ex = dict(exemplo[sigla]); ex.pop("texto_num", None)
    return {"sigla": sigla, "nome": nome, "fator": fator, "votos": dict(votos), "amostras": sum(votos.values()),
            "exemplo": ex}


def folhas(des: Desenho) -> dict:
    """As folhas do projeto pelos carimbos ("FOLHA 12/36 - PLANTA DE LOCAÇÃO"): o número, o título e quantas são."""
    achadas: Dict[int, str] = {}
    total = 0
    for e in des.entidades.values():
        if not isinstance(e, Texto):
            continue
        m = _FOLHA.search(e.texto or "")
        if not m:
            continue
        n, t = int(m.group(1)), int(m.group(2))
        total = max(total, t)
        titulo = re.sub(r"\s+", " ", (e.texto or "")[m.end():]).strip(" -–|")
        if titulo and len(titulo) > len(achadas.get(n, "")):
            achadas[n] = titulo
        else:
            achadas.setdefault(n, titulo)
    return {"total": total, "achadas": len(achadas),
            "lista": [{"folha": n, "titulo": achadas[n]} for n in sorted(achadas)]}


def resumo_da_leitura(des: Desenho) -> dict:
    """O que a importação leu, para a tela "O que o programa leu" (antes de qualquer modelagem)."""
    por_tipo = collections.Counter(e.tipo for e in des.entidades.values())
    return {"folhas": folhas(des), "cotas": unidade_das_cotas(des),
            "textos": por_tipo.get("texto", 0), "n_cotas": por_tipo.get("cota", 0)}
