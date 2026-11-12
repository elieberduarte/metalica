# -*- coding: utf-8 -*-
"""O que o Imprimir pranchas… mostra de cada folha e o que ele guarda (usuário, 12/11, no Vicente Residence: "precisamos
melhorar a ferramenta de gestão das impressões"; a tela A aprovada, Projeto/ANALISES/Interface/
Impressao-gerenciador-proposta-2026-11-12.pdf):

* a escala de cada folha (a das células dela: "1:25", "1:25 / 1:10", "várias") e a revisão (a última do carimbo,
  `carimbo_pranchas.revisoes` do projeto);
* a situação: nunca impressa, impressa (quando e onde), ou mudou depois da última impressão — pela assinatura do que está
  dentro da moldura da folha, gravada a cada impressão;
* os conjuntos de folhas guardados por obra ("Fabricação", "Montagem"…).

Tudo fica no projeto, em `impressoes.json`: {"historico": [{quando, impressora, folhas: [{chave, desenho, numero, titulo,
revisao, assinatura}]}], "conjuntos": {nome: [chave, …]}}. A chave da folha é "<desenho>|<número>": a folha 03 continua
a 03 quando as pranchas são montadas de novo."""
import collections
import datetime
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Sequence

ARQUIVO = "impressoes.json"
#: o histórico guarda as últimas tantas impressões
HISTORICO_MAX = 200


def chave(desenho: str, numero, indice: int = 0) -> str:
    return "%s|%s" % (desenho, numero if numero not in (None, "") else "i%d" % indice)


# ------------------------------------------------------------------ escala e revisão
def escala_da_folha(info: dict) -> str:
    """As escalas das células da folha, a mais usada primeiro: "1:25", "1:25 / 1:10"; mais de duas, "várias"."""
    conta = collections.Counter()
    for c in info.get("celulas") or []:
        try:
            k = float(c.get("escala") or 0)
        except (TypeError, ValueError):
            continue
        if k > 0:
            conta[int(round(k)) if abs(k - round(k)) < 1e-6 else round(k, 2)] += 1
    if not conta and info.get("escala"):
        try:
            conta[int(round(float(info["escala"])))] += 1
        except (TypeError, ValueError):
            pass
    if not conta:
        return ""
    ordem = [k for k, _ in sorted(conta.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(ordem) > 2:
        return "várias"
    return " / ".join("1:%s" % ("%g" % k).replace(".", ",") for k in ordem)


def revisao_da_folha(revisoes: dict, numero) -> str:
    """A última revisão da prancha `numero` no carimbo do projeto ("" sem revisão lançada)."""
    from nucleo2d.revisoes import ultima_revisao
    if numero in (None, ""):
        return ""
    return ultima_revisao((revisoes or {}).get(str(numero)) or [])


# ------------------------------------------------------------------ assinatura do que está na folha
def _ponto(e: dict):
    for k in ("a", "posicao", "p1", "centro", "alvo"):
        v = e.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return float(v[0]), float(v[1])
    for k in ("vertices",):
        v = e.get(k)
        if v:
            return float(v[0][0]), float(v[0][1])
    cs = e.get("contornos")
    if cs and cs[0]:
        return float(cs[0][0][0]), float(cs[0][0][1])
    return None


_ID = re.compile(r'"id":\s*"[^"]*",?\s*')


def assinaturas(entidades, folhas: Sequence[dict]) -> List[str]:
    """Para cada folha ({origem, tamanho}), a assinatura do que tem o ponto de referência dentro da moldura dela (o id
    não conta: montar de novo o mesmo desenho não muda a assinatura). A folha sem origem (o desenho de uma folha só)
    leva tudo. Cada folha é serializada de uma vez (as 34 mil entidades do Vicente em ~1,3 s; uma a uma eram 2,9 s)."""
    caixas = []
    for f in folhas:
        o, t = f.get("origem"), f.get("tamanho")
        caixas.append((float(o[0]), float(o[1]), float(o[0]) + float(t[0]), float(o[1]) + float(t[1])) if o and t else None)
    grupos: List[list] = [[] for _ in folhas]
    for e in (entidades.values() if isinstance(entidades, dict) else entidades or []):
        if not isinstance(e, dict):
            continue
        p = _ponto(e)
        for i, c in enumerate(caixas):
            if c is None or (p is not None and c[0] - 1e-6 <= p[0] <= c[2] + 1e-6 and c[1] - 1e-6 <= p[1] <= c[3] + 1e-6):
                grupos[i].append(e)
                break
    return [hashlib.md5(_ID.sub("", json.dumps(g, default=str)).encode("ascii")).hexdigest()[:16] for g in grupos]


# ------------------------------------------------------------------ o arquivo do projeto
def ler(pasta_projeto: str) -> dict:
    try:
        with open(os.path.join(pasta_projeto, ARQUIVO), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("historico", [])
    d.setdefault("conjuntos", {})
    return d


def gravar(pasta_projeto: str, dados: dict) -> None:
    caminho = os.path.join(pasta_projeto, ARQUIVO)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def conjuntos_validos(conjuntos) -> Dict[str, List[str]]:
    out = {}
    for nome, chaves in (conjuntos or {}).items() if isinstance(conjuntos, dict) else []:
        nome = str(nome or "").strip()[:60]
        if nome and isinstance(chaves, list):
            out[nome] = [str(c) for c in chaves if isinstance(c, (str, int))][:500]
    return out


def registrar(pasta_projeto: str, impressora: str, folhas: Sequence[dict], quando: Optional[str] = None) -> dict:
    """Uma impressão no histórico: as folhas impressas (com a chave, a revisão e a assinatura de agora)."""
    d = ler(pasta_projeto)
    item = {"quando": quando or datetime.datetime.now().isoformat(timespec="seconds"), "impressora": str(impressora),
            "folhas": [{k: f.get(k) for k in ("chave", "desenho", "numero", "titulo", "revisao", "assinatura")} for f in folhas]}
    d["historico"] = (d["historico"] + [item])[-HISTORICO_MAX:]
    gravar(pasta_projeto, d)
    return item


def _curto(impressora: str) -> str:
    """O nome da impressora para a lista: a plotter vira "plotter"; o caminho de rede some."""
    n = str(impressora or "")
    if ehPlotter(n):
        return "plotter"
    return n.split("\\")[-1].strip() or n


def ehPlotter(nome: str) -> bool:
    n = str(nome or "").lower()
    return "designjet" in n or "t120" in n or "plotter" in n


def situacao(historico: Sequence[dict], ch: str, assinatura: str) -> dict:
    """{estado: nunca | impressa | mudou, quando (dd/mm), onde}: a última impressão da folha e se ela mudou depois."""
    for item in reversed(list(historico or [])):
        for f in item.get("folhas") or []:
            if f.get("chave") == ch:
                q = str(item.get("quando") or "")
                dm = "%s/%s" % (q[8:10], q[5:7]) if len(q) >= 10 else q
                return {"estado": "impressa" if f.get("assinatura") == assinatura else "mudou", "quando": dm,
                        "onde": _curto(item.get("impressora")), "revisao": f.get("revisao") or ""}
    return {"estado": "nunca"}
