# -*- coding: utf-8 -*-
"""As trocas de perfil da análise levadas ao modelo 3D e à planta de lançamento (etapa 6, 11/10/2026).

Na tela da análise a troca é um "e se" (`trocas_perfil` nas premissas: {"função|perfil original": "perfil novo"}, a função é
o papel na treliça — banzo_sup, banzo_inf, montante, diagonal — ou o papel da peça — pilar, viga…; nucleo3d/
analise_estrutural.py, chave_do_grupo). Aplicar faz a troca de verdade, com a mesma chave:

* no modelo 3D: cada barra do grupo ganha o perfil novo; a viga de aço lançada pela face de cima (ou de baixo) desce
  (sobe) a metade da diferença das alturas, para a face continuar no nível — como a planta a geraria de novo;
* na planta de lançamento: o pilar e a viga de aço (`secao.perfil`) e a tesoura de aço pelo desenho (`perfis[papel]`). O
  montante sem perfil próprio usa o da diagonal (de_planta_estrutura._trelica): trocar a diagonal grava antes o montante
  com o perfil que ele tinha, para ele não mudar junto;
* nas premissas: a sanfona da cobertura retrátil (`perfil_sanfona`), que a análise monta a partir delas.

A troca aplicada sai de `trocas_perfil` (o modelo já tem o perfil); a que não achou nada (a terça de hipótese, que só existe
na análise) fica.
"""
from __future__ import annotations

import collections
from typing import Dict, List, Optional, Tuple


def chave_da_barra(ent) -> str:
    """a mesma chave da análise (chave_do_grupo): a função e o perfil atual da barra do modelo"""
    at = getattr(ent, "atributos", None) or {}
    return "%s|%s" % (at.get("papel_trelica") or getattr(ent, "papel", "") or "barra", getattr(ent, "perfil", "") or "")


def _altura(perfil: str) -> float:
    """a altura d (mm) pelo catálogo do 3D (o mesmo da análise: acha também os W que o nucleo.perfis não tem)"""
    try:
        from nucleo3d.geometria import resolver_perfil
        return float(getattr(resolver_perfil(perfil), "d", 0.0) or 0.0)
    except Exception:                                    # noqa: BLE001 — perfil fora do catálogo: sem ajuste de nível
        return 0.0


def aplicar_no_modelo(doc, trocas: Dict[str, str], alinhamentos: Optional[Dict[str, str]] = None) -> collections.Counter:
    """troca o perfil das barras do modelo; `alinhamentos` = {id do elemento da planta: "topo" | "base" | "eixo"} das vigas
    de aço. Devolve {chave: barras trocadas}"""
    from nucleo3d.modelo import Barra
    feitas = collections.Counter()
    alinhamentos = alinhamentos or {}
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Barra):
            continue
        k = chave_da_barra(ent)
        novo = trocas.get(k)
        if not novo or novo == ent.perfil:
            continue
        antigo = ent.perfil
        ent.perfil = novo
        at = ent.atributos or {}
        if ent.papel == "viga" and abs(ent.inicio[2] - ent.fim[2]) < 1.0:
            alin = alinhamentos.get(str(at.get("origem_2d") or ""), "")
            dz = (_altura(novo) - _altura(antigo)) / 2.0
            if alin in ("topo", "base") and dz:
                s = -1.0 if alin == "topo" else 1.0
                ent.inicio = (ent.inicio[0], ent.inicio[1], ent.inicio[2] + s * dz)
                ent.fim = (ent.fim[0], ent.fim[1], ent.fim[2] + s * dz)
        feitas[k] += 1
    return feitas


def aplicar_na_planta(desenho: dict, trocas: Dict[str, str]) -> Tuple[collections.Counter, Dict[str, str]]:
    """troca o perfil dos elementos de aço da planta (o desenho em dicionário, como gravado). Devolve {chave: elementos
    trocados} e os alinhamentos das vigas de aço ({id: alinhamento}) para o ajuste de nível no modelo"""
    feitas = collections.Counter()
    alinhamentos = {}
    for e in desenho.get("entidades") or []:
        a = e.get("atributos") or {}
        tipo = a.get("elemento")
        if a.get("material") != "aco":
            continue
        if tipo in ("pilar", "viga"):
            s = a.get("secao") or {}
            if tipo == "viga":
                alinhamentos[str(e.get("id"))] = a.get("alinhamento") or "eixo"
            novo = trocas.get("%s|%s" % (tipo, s.get("perfil") or ""))
            if novo and novo != s.get("perfil"):
                a["secao"] = dict(s, perfil=novo)
                feitas["%s|%s" % (tipo, s.get("perfil"))] += 1
        elif tipo == "trelica":
            perfis = dict(a.get("perfis") or {})
            # o perfil de cada função antes da troca (o montante sem perfil próprio é o da diagonal)
            efetivo = {p: perfis.get(p) or (perfis.get("diagonal") if p == "montante" else None)
                       for p in ("banzo_sup", "banzo_inf", "diagonal", "montante")}
            novos = dict(perfis)
            for papel, atual in efetivo.items():
                novo = trocas.get("%s|%s" % (papel, atual)) if atual else None
                if novo and novo != atual:
                    novos[papel] = novo
                    feitas["%s|%s" % (papel, atual)] += 1
            if novos != perfis:
                if "montante" not in perfis and efetivo["montante"]:
                    novos.setdefault("montante", efetivo["montante"])      # trocar a diagonal não leva o montante junto
                a["perfis"] = novos
    return feitas, alinhamentos


def aplicar_nos_parametros(par: dict, trocas: Dict[str, str]) -> collections.Counter:
    """a sanfona da cobertura retrátil sai das premissas (`perfil_sanfona`)"""
    feitas = collections.Counter()
    if par.get("cobertura_movel") in (True, "true"):
        k = "contraventamento|%s" % (par.get("perfil_sanfona") or "")
        if trocas.get(k):
            par["perfil_sanfona"] = trocas[k]
            feitas[k] += 1
    return feitas


def resumo(feitas_modelo, feitas_planta, feitas_par, trocas: Dict[str, str]) -> Tuple[List[str], Dict[str, str]]:
    """o texto do que foi feito e as trocas que ficam (as que não acharam nada fora da análise)"""
    linhas, ficam = [], {}
    for k, novo in trocas.items():
        f, _, p0 = k.partition("|")
        n3, n2, np_ = feitas_modelo.get(k, 0), feitas_planta.get(k, 0), feitas_par.get(k, 0)
        if not (n3 or n2 or np_):
            ficam[k] = novo
            linhas.append("%s %s → %s: nada no modelo nem na planta com esse perfil (fica só na análise)" % (f, p0, novo))
            continue
        partes = []
        if n3:
            partes.append("%d barra(s) no 3D" % n3)
        if n2:
            partes.append("%d elemento(s) na planta" % n2)
        if np_:
            partes.append("a premissa da sanfona")
        linhas.append("%s %s → %s: %s" % (f, p0, novo, ", ".join(partes)))
    return linhas, ficam
