# -*- coding: utf-8 -*-
"""Banco de detalhes de ligação da empresa (plano de 01/10, etapa 5).

Cada detalhe é uma VARIANTE com nome (ST1, SC1, CASTANHA 16…): um tipo da biblioteca de ligações
(`nucleo/acessorios.py`, tela /ligacoes) com as medidas fixadas e a regra de colocação no 3D. No
quadro "Detalhes de ligação" da Montagem o operador só escolhe, para cada função (suporte de terça,
suporte de contravento, base, emenda), a variante — o programa não interpreta o desenho do detalhe do
cliente, que fica no quadro como referência.

As variantes padrão saem daqui (as acertadas na portaria do Projeto Hermes, 30/09); as que o
operador cadastra ficam no arquivo `banco-detalhes.json` da pasta de dados e valem para as próximas
obras. A regra de furação da fábrica sempre vale (50×60 abaixo de 200 mm, 100×60 acima; oblongos
25×13 na terça; 30 mm das pontas).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional

__all__ = ["FUNCOES", "PADRAO", "lista", "variante", "salvar", "excluir", "ARQUIVO"]

ARQUIVO = "banco-detalhes.json"

#: as funções que a montagem precisa decidir, na ordem do quadro
FUNCOES = [
    {"id": "suporte_terca", "nome": "Suporte de terça"},
    {"id": "suporte_contravento", "nome": "Suporte de contravento"},
    {"id": "base_pilar", "nome": "Base do pilar"},
    {"id": "emenda_terca", "nome": "Emenda de terça"},
]

#: as variantes da casa (não se apagam; uma cadastrada com o mesmo id vale por cima)
PADRAO: List[dict] = [
    {"id": "ST1", "nome": "ST1 — cantoneira L 100×50×3,75 de 120 mm, 4 M12", "funcao": "suporte_terca",
     "tipo": "suporte_terca_cantoneira",
     "parametros": {"cantoneira": "L 100×50×3,75", "comprimento": 120, "n_parafusos": 4, "parafuso": "M12",
                    "classe": "ASTM A307", "gabarito": 60},
     "colocacao": {"peca": "L 100×50×3,75", "comprimento": 120.0, "aba_em_pe": "alma da terça",
                   "pe": "topo do banzo", "furos": [[30.0, 25.0], [90.0, 25.0], [30.0, 75.0], [90.0, 75.0]],
                   "furo_d": 13.5, "parafuso": "M12", "oblongo_terca": [25.0, 13.0]},
     "origem": "portaria Projeto Hermes (30/09): ST1 de 110 do projeto → 120 pelo padrão de furação",
     "padrao": True},
    {"id": "SC1", "nome": "SC1 — L 2\"×3/16\" de 90 mm em pé, furo Ø16", "funcao": "suporte_contravento",
     "tipo": "contravento_tirante",
     "parametros": {},
     "colocacao": {"peca": "L 2\"×3/16\"", "altura": 90.0, "furo_z": 45.0, "furo_d": 16.0, "centrada_no_banzo": True,
                   "gira_com_o_tirante": True, "porcas": 2, "barra": "Ø1/2\"", "passa": 40.0, "separa": 150.0},
     "origem": "portaria Projeto Hermes (30/09): detalhe CONTRAVENTAMENTO Cobertura, no banzo de cima",
     "padrao": True},
    {"id": "CASTANHA16", "nome": "Castanha 16 — bloco 40×40 chanfrado na face do banzo", "funcao": "suporte_contravento",
     "tipo": "contravento_tirante",
     "parametros": {},
     "colocacao": {"peca": "castanha", "lado": 40.0, "t_min": 4.0, "furo_d": 16.0, "porcas": 1, "barra": "Ø1/2\"",
                   "sobra": 10.0},
     "origem": "portaria Projeto Hermes (30/09): CASTANHA 16 do detalhe do projeto",
     "padrao": True},
    {"id": "APOIO-CONCRETO", "nome": "Pilar de concreto de outros — só apoio", "funcao": "base_pilar",
     "tipo": "apoio_tesoura_concreto", "parametros": {},
     "colocacao": {"concreto": True, "calcular": False},
     "origem": "portaria Projeto Hermes (30/09): pilares de concreto só de apoio", "padrao": True},
    {"id": "EMENDA-TRANSPASSE", "nome": "Emenda de terça por transpasse no apoio", "funcao": "emenda_terca",
     "tipo": "emenda_terca", "parametros": {},
     "colocacao": {"no_apoio": True}, "origem": "biblioteca de ligações", "padrao": True},
]


def _arquivo(pasta: str) -> str:
    return os.path.join(pasta, ARQUIVO)


def _ler(pasta: str) -> List[dict]:
    try:
        with open(_arquivo(pasta), encoding="utf-8") as f:
            d = json.load(f)
        return [v for v in d.get("variantes") or [] if isinstance(v, dict) and v.get("id")]
    except (OSError, ValueError):
        return []


def lista(pasta: Optional[str] = None) -> Dict[str, object]:
    """{funcoes, variantes}: as da casa e as cadastradas (estas por cima, mesmo id)"""
    por_id = {v["id"]: dict(v) for v in PADRAO}
    for v in _ler(pasta) if pasta else []:
        por_id[v["id"]] = dict(v, padrao=False)
    return {"funcoes": FUNCOES, "variantes": list(por_id.values())}


def variante(vid: str, pasta: Optional[str] = None) -> Optional[dict]:
    return next((v for v in lista(pasta)["variantes"] if v["id"] == vid), None)


def _limpo(v: dict) -> dict:
    vid = re.sub(r"[^A-Z0-9.\-]", "", str(v.get("id") or "").upper().replace(" ", ""))
    if not vid:
        raise ValueError("a variante precisa de um nome curto (ST2, SC2…)")
    funcao = str(v.get("funcao") or "")
    if funcao not in {f["id"] for f in FUNCOES}:
        raise ValueError("função desconhecida: %s" % funcao)
    out = {"id": vid, "nome": str(v.get("nome") or vid)[:120], "funcao": funcao, "tipo": str(v.get("tipo") or ""),
           "parametros": dict(v.get("parametros") or {}), "colocacao": dict(v.get("colocacao") or {}),
           "origem": str(v.get("origem") or "")[:300], "cadastrada": time.strftime("%Y-%m-%dT%H:%M")}
    for k in ("comprimento", "altura", "furo_d", "furo_z"):
        if k in out["colocacao"]:
            try:
                out["colocacao"][k] = float(str(out["colocacao"][k]).replace(",", "."))
            except ValueError:
                raise ValueError("%s: número inválido" % k)
    return out


def salvar(pasta: str, v: dict) -> dict:
    """cadastra (ou troca) uma variante da empresa"""
    novo = _limpo(v)
    vs = [x for x in _ler(pasta) if x.get("id") != novo["id"]]
    vs.append(novo)
    os.makedirs(pasta, exist_ok=True)
    tmp = _arquivo(pasta) + ".parcial"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"formato": 1, "variantes": vs}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _arquivo(pasta))
    return novo


def excluir(pasta: str, vid: str) -> bool:
    vs = _ler(pasta)
    fica = [x for x in vs if x.get("id") != vid]
    if len(fica) == len(vs):
        return False
    with open(_arquivo(pasta), "w", encoding="utf-8") as f:
        json.dump({"formato": 1, "variantes": fica}, f, ensure_ascii=False, indent=1)
    return True
