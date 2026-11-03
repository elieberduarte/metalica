# -*- coding: utf-8 -*-
"""As ligações do pré-moldado calculadas avulsas (a tela /premoldado/ligacoes): cálice, consolo e aparelho
de apoio de elastômero — as mesmas rotinas da NBR 9062 que o galpão usa (nbr9062.py). As entradas vêm como
a tela mostra (kN, kN·m, cm) e voltam o resultado com a memória e os dados para o desenho."""
from __future__ import annotations

from typing import Any, Dict

from nucleo.base import ErroDeDados
from nucleo.verificar import serializar_resultado

from . import nbr9062 as N9062
from .concreto import Concreto, aco as aco_armadura

TIPOS = {
    "calice": "Cálice de fundação",
    "consolo": "Consolo",
    "elastomero": "Aparelho de apoio de elastômero",
}


def _num(p: Dict[str, Any], k: str, padrao=None) -> float:
    v = p.get(k, padrao)
    if v in (None, ""):
        if padrao is None:
            raise ErroDeDados("informe %s" % k)
        v = padrao
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        raise ErroDeDados("%s: número inválido (%s)" % (k, v))


def _bool(p: Dict[str, Any], k: str) -> bool:
    v = p.get(k)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "sim", "on")


def _materiais(p):
    pf = _bool(p, "pre_fabricado")
    gc, gs = N9062.coeficientes(pf)
    conc = Concreto(_num(p, "fck", 35), p.get("agregado") or "granito", gama_c=gc)
    a0 = aco_armadura(p.get("aco") or "CA-50")
    a = type(a0)(a0.nome, a0.fyk_MPa, a0.Es_MPa, gama_s=gs)
    return conc, a, pf


def _json(v):
    if isinstance(v, dict):
        return {str(k): _json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, float):
        return round(v, 4)
    return v if isinstance(v, (int, str, bool)) or v is None else str(v)


def calcular(tipo: str, p: Dict[str, Any]) -> Dict[str, Any]:
    if tipo not in TIPOS:
        raise ErroDeDados("ligação desconhecida: %s (use %s)" % (tipo, ", ".join(TIPOS)))
    if tipo == "calice":
        conc, a, _pf = _materiais(p)
        r = N9062.calice(_num(p, "b"), _num(p, "h"), _num(p, "Nd"), _num(p, "Md") * 100.0, _num(p, "Vd", 0),
                         conc, a, _num(p, "bitola_pilar", 16), interface=p.get("interface") or "rugosa",
                         parede=_num(p, "parede", 20), folga=_num(p, "folga", 5), elemento="Cálice")
    elif tipo == "consolo":
        conc, a, pf = _materiais(p)
        Hd = p.get("Hd")
        r = N9062.consolo(_num(p, "b"), _num(p, "h"), _num(p, "a"), _num(p, "Fd"), conc, a,
                          apoio=p.get("apoio") or "elastômero",
                          Hd=None if Hd in (None, "") else _num(p, "Hd"),
                          carga_direta=not _bool(p, "carga_indireta"), pre_fabricado=pf,
                          permanente_preponderante=_bool(p, "permanente_preponderante"),
                          interface=p.get("interface") or "monolítico",
                          bitola_tirante=_num(p, "bitola_tirante", 12.5), elemento="Consolo")
    else:
        r = N9062.elastomero_simples(_num(p, "a"), _num(p, "b"), _num(p, "h"), _num(p, "Ngk"), _num(p, "Nqk", 0),
                                     _num(p, "Hk", 0), shore=int(_num(p, "shore", 60)),
                                     rotacao_g=_num(p, "rotacao_g", 0), rotacao_q=_num(p, "rotacao_q", 0),
                                     elemento="Aparelho de apoio")
    out = serializar_resultado(r)
    out["dados"] = _json(r.dados)
    out["tipo"] = tipo
    out["entrada"] = _json(p)
    return out


def opcoes() -> Dict[str, Any]:
    """as listas que a tela oferece"""
    return {"tipos": TIPOS, "apoios": list(N9062.HD_FD), "shore": sorted(N9062.SHORE_G)}
