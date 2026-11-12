# -*- coding: utf-8 -*-
"""O controle de produção de uma obra: o que se controla, os apontamentos e o andamento.

Decisões do usuário (11–12/11/2026, FERRAMENTA · CONTROLE DE PRODUÇÃO):

* O apontamento mora no projeto da obra: `<projeto>/producao/apontamentos.jsonl`, um evento por linha, nunca
  reescrito. Apontamento errado vira estorno (outro evento), nada se apaga.
* Etapas agora: PRODUÇÃO e PINTURA (internas da fábrica); expedição e montagem entram depois sem mexer no que já foi
  apontado (é só mais uma chave em ETAPAS).
* O que se controla (os "itens"), tirado da lista de materiais (`detalhamento/lista-de-materiais.json`):
  - cada **unidade** de conjunto de várias peças (tesoura, viga de rigidez, MT, DP…) é um item; quando há mais de uma
    com o mesmo nome, ganha o número na frente: T38-1, T38-2 (a T74, única, fica T74);
  - as peças iguais que sobram fora desses conjuntos (terças, contraventos, chapas avulsas…) são **um item por
    posição**, apontado com a quantidade ("T.C.1: 30 de 46").
  A soma dos itens fecha com o peso da lista (o Posto V2: 32.114,5 kg em 233 unidades + 33.237,9 kg em peças).
* Quem aponta: a engenharia, pela licença da máquina (licenca.estado()["pessoa"]).
* O ERP só lê (`para_erp`).

Nada aqui recalcula a lista: se o detalhamento for refeito e um item sumir, os apontamentos dele aparecem como
"fora da lista atual" em vez de serem remarcados.
"""
import datetime
import json
import os
import re
import threading
import uuid
from collections import Counter, OrderedDict
from typing import Dict, List, Optional

ETAPAS = OrderedDict([("producao", "Produção"), ("pintura", "Pintura")])
PASTA = "producao"
ARQUIVO = "apontamentos.jsonl"
LISTA = os.path.join("detalhamento", "lista-de-materiais.json")

_TRAVA = threading.Lock()
_DIFERE = re.compile(r"^(.+?) \((\d+) em vez de (\d+)\)$")

# o tipo das peças avulsas, pela categoria da lista
_TIPO_CATEGORIA = {"TERÇAS": "terça", "BARRAS": "barra", "CHAPAS": "chapa", "TIRANTES": "tirante",
                   "TELHAS": "telha", "RUFOS": "rufo", "TESOURAS": "tesoura", "CONJUNTOS": "conjunto"}


class ErroControle(ValueError):
    """pedido que não se pode atender (quantidade a mais, item que não existe…): a mensagem vai para a tela"""


# ------------------------------------------------------------------ os itens
def _tipo_peca(p: dict) -> str:
    nome = str(p.get("nome") or "")
    if nome.startswith("CV."):
        return "contravento"
    return _TIPO_CATEGORIA.get(str(p.get("categoria") or "").upper(), str(p.get("categoria") or "peça").lower())


def _total_por_posicao(c: dict) -> Dict[str, int]:
    """as peças de TODAS as unidades do conjunto, por posição: a composição × instâncias, corrigida pelo `difere`
    da lista ("P1290 (1 em vez de 0)": uma das unidades leva uma peça a mais)"""
    n = int(c.get("instancias") or 1)
    tot = {k: int(q) * n for k, q in (c.get("composicao") or {}).items()}
    for s in c.get("difere") or []:
        m = _DIFERE.match(str(s))
        if m:
            tot[m.group(1)] = int(m.group(2))
    return tot


def itens(lista: dict, nomes: Optional[dict] = None) -> List[dict]:
    """[{id, tipo, origem: conjunto|pecas, refs, descricao, quantidade, kg_unidade, kg}] na ordem da tela: os conjuntos
    (pelo nome, numerados) e depois as peças avulsas (pela posição)."""
    tipos_cj = (nomes or {}).get("tipos_conjuntos") or {}
    posicoes = lista.get("posicoes") or []
    conjuntos = lista.get("conjuntos") or []
    por_marca = {}
    for p in posicoes:
        for m in str(p.get("marca") or "").split(" / "):
            if m.strip():
                por_marca[m.strip()] = p

    # --- conjuntos de várias peças: uma linha por unidade; o mesmo nome em marcas diferentes (MT71 = M102, M103,
    # M104) numera junto
    por_nome: Dict[str, list] = OrderedDict()
    for c in conjuntos:
        por_nome.setdefault(str(c.get("nome") or c.get("marca")), []).append(c)
    usados: Counter = Counter()
    saida = []
    for nome, grupo in por_nome.items():
        total = sum(int(c.get("instancias") or 1) for c in grupo)
        i = 0
        for c in grupo:
            n = int(c.get("instancias") or 1)
            kg_u = float(c.get("peso_total") or 0.0) / n if n else 0.0
            tipo = tipos_cj.get(c.get("marca")) or _TIPO_CATEGORIA.get(str(c.get("categoria") or "").upper(), "conjunto")
            for _ in range(n):
                i += 1
                saida.append({"id": "%s-%d" % (nome, i) if total > 1 else nome, "nome": nome, "tipo": tipo,
                              "origem": "conjunto", "refs": [c.get("marca")],
                              "descricao": "%d peças" % int(c.get("pecas_unidade") or 0),
                              "quantidade": 1, "kg_unidade": round(kg_u, 3), "kg": round(kg_u, 3)})
            for k, q in _total_por_posicao(c).items():
                p = por_marca.get(k)
                if p is not None:
                    usados[id(p)] += q

    # --- as peças que sobram fora dos conjuntos: uma linha por posição, com a quantidade
    ids = {x["id"] for x in saida}
    for p in posicoes:
        resto = int(p.get("quantidade") or 0) - usados[id(p)]
        if resto <= 0:
            continue
        nome = str(p.get("nome") or p.get("marca"))
        ident = nome if nome not in ids else "%s (%s)" % (nome, p.get("marca"))
        ids.add(ident)
        dim = [str(p.get("perfil") or "")]
        if p.get("comprimento"):
            dim.append("× %s" % _mm(p.get("comprimento")))
        saida.append({"id": ident, "nome": nome, "tipo": _tipo_peca(p), "origem": "pecas", "refs": [p.get("marca")],
                      "descricao": " ".join(x for x in dim if x), "quantidade": resto,
                      "kg_unidade": round(float(p.get("peso") or 0.0), 3),
                      "kg": round(resto * float(p.get("peso") or 0.0), 3)})
    return saida


def _mm(v) -> str:
    try:
        return ("%.0f" % float(v)).replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


# ------------------------------------------------------------------ os eventos
def caminho(pasta_projeto: str) -> str:
    return os.path.join(pasta_projeto, PASTA, ARQUIVO)


def ler_eventos(pasta_projeto: str) -> List[dict]:
    cam = caminho(pasta_projeto)
    if not os.path.exists(cam):
        return []
    out = []
    with open(cam, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                out.append(json.loads(linha))
            except ValueError:                      # linha cortada (queda de energia no meio da gravação): pula
                continue
    return out


def _gravar(pasta_projeto: str, ev: dict):
    cam = caminho(pasta_projeto)
    os.makedirs(os.path.dirname(cam), exist_ok=True)
    with open(cam, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _validos(eventos: List[dict]) -> List[dict]:
    """os apontamentos que valem: sem os estornados e sem os próprios estornos"""
    estornados = {e.get("estorno_de") for e in eventos if e.get("estorno_de")}
    return [e for e in eventos if not e.get("estorno_de") and e.get("id") not in estornados]


def feito(eventos: List[dict]) -> Dict[str, Counter]:
    """{item: Counter({etapa: quantidade})} dos apontamentos que valem"""
    out: Dict[str, Counter] = {}
    for e in _validos(eventos):
        out.setdefault(e.get("item"), Counter())[e.get("etapa")] += int(e.get("quantidade") or 0)
    return out


def _hoje() -> datetime.date:
    return datetime.date.today()


def _agora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _data(valor) -> str:
    if not valor:
        return _hoje().isoformat()
    try:
        d = datetime.date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ErroControle("data inválida: %r (use AAAA-MM-DD)" % valor)
    if d > _hoje():
        raise ErroControle("a data do apontamento (%s) é depois de hoje" % d.strftime("%d/%m/%Y"))
    return d.isoformat()


def apontar(pasta_projeto: str, lista: dict, item: str, etapa: str, quantidade, quem: str,
            data=None, obs: str = "", nomes: Optional[dict] = None) -> dict:
    """grava um apontamento e devolve o evento. Recusa etapa desconhecida, item fora da lista e quantidade maior
    que o que falta naquela etapa."""
    if etapa not in ETAPAS:
        raise ErroControle("etapa desconhecida: %r" % etapa)
    try:
        q = int(quantidade)
    except (TypeError, ValueError):
        raise ErroControle("quantidade inválida: %r" % quantidade)
    if q < 1:
        raise ErroControle("a quantidade precisa ser 1 ou mais")
    por_id = {x["id"]: x for x in itens(lista, nomes)}
    it = por_id.get(item)
    if it is None:
        raise ErroControle("%s não está na lista de materiais atual" % item)
    dia = _data(data)
    with _TRAVA:
        ja = feito(ler_eventos(pasta_projeto)).get(item, Counter())[etapa]
        falta = it["quantidade"] - ja
        if falta <= 0:
            raise ErroControle("%s já está completo na %s" % (item, ETAPAS[etapa].lower()))
        if q > falta:
            raise ErroControle("%s: só falta%s %d na %s (pedido: %d)"
                               % (item, "m" if falta != 1 else "", falta, ETAPAS[etapa].lower(), q))
        ev = {"id": uuid.uuid4().hex[:12], "quando": _agora(), "data": dia, "quem": quem or "", "etapa": etapa,
              "item": item, "refs": it["refs"], "quantidade": q, "kg": round(q * it["kg_unidade"], 3),
              "estorno_de": None, "obs": str(obs or "")[:300]}
        _gravar(pasta_projeto, ev)
    return ev


def estornar(pasta_projeto: str, evento: str, quem: str, obs: str = "") -> dict:
    """desfaz um apontamento com um evento de estorno (o original fica no arquivo)"""
    with _TRAVA:
        eventos = ler_eventos(pasta_projeto)
        orig = next((e for e in eventos if e.get("id") == evento), None)
        if orig is None:
            raise ErroControle("apontamento não encontrado: %r" % evento)
        if orig.get("estorno_de"):
            raise ErroControle("isto já é um estorno")
        if any(e.get("estorno_de") == evento for e in eventos):
            raise ErroControle("este apontamento já foi estornado")
        ev = {"id": uuid.uuid4().hex[:12], "quando": _agora(), "data": _hoje().isoformat(), "quem": quem or "",
              "etapa": orig.get("etapa"), "item": orig.get("item"), "refs": orig.get("refs") or [],
              "quantidade": int(orig.get("quantidade") or 0), "kg": orig.get("kg") or 0, "estorno_de": evento,
              "obs": str(obs or "")[:300]}
        _gravar(pasta_projeto, ev)
    return ev


# ------------------------------------------------------------------ o andamento
def situacao(lista: dict, eventos: List[dict], nomes: Optional[dict] = None, ultimos: int = 30) -> dict:
    """o que a aba Controle mostra: os itens com o feito por etapa, o andamento em kg e %, os últimos eventos e os
    apontamentos de itens que não estão mais na lista"""
    its = itens(lista, nomes)
    f = feito(eventos)
    kg_total = round(sum(x["kg"] for x in its), 1)
    andamento = OrderedDict()
    for etapa, titulo in ETAPAS.items():
        kg = sum(min(f.get(x["id"], Counter())[etapa], x["quantidade"]) * x["kg_unidade"] for x in its)
        completos = sum(1 for x in its if f.get(x["id"], Counter())[etapa] >= x["quantidade"])
        andamento[etapa] = {"titulo": titulo, "kg": round(kg, 1), "pct": round(100.0 * kg / kg_total, 1) if kg_total else 0.0,
                            "itens_completos": completos}
    for x in its:
        x["feito"] = {e: int(f.get(x["id"], Counter())[e]) for e in ETAPAS}
    ids = {x["id"] for x in its}
    fora = sorted({e.get("item") for e in _validos(eventos) if e.get("item") not in ids})
    hoje = _hoje().isoformat()
    validos_hoje = [e for e in _validos(eventos) if str(e.get("quando", ""))[:10] == hoje]
    estornados = {e.get("estorno_de") for e in eventos if e.get("estorno_de")}
    recentes = []
    for e in reversed(eventos[-ultimos:] if ultimos else eventos):
        r = dict(e)
        r["estornado"] = e.get("id") in estornados
        recentes.append(r)
    return {"etapas": [{"chave": k, "titulo": t} for k, t in ETAPAS.items()],
            "total": {"kg": kg_total, "itens": len(its), "unidades_conjunto": sum(1 for x in its if x["origem"] == "conjunto"),
                      "peso_lista": (lista.get("totais") or {}).get("peso")},
            "andamento": andamento, "itens": its, "fora_da_lista": fora,
            "hoje": {"apontamentos": len(validos_hoje), "kg": round(sum(float(e.get("kg") or 0) for e in validos_hoje), 1)},
            "eventos": recentes, "lista_gerada": lista.get("gerado")}


def para_erp(slug: str, nome: str, lista: dict, eventos: List[dict], nomes: Optional[dict] = None,
             desde: Optional[str] = None) -> dict:
    """o que o ERP lê (só leitura): o andamento já somado, cada item e os eventos (com `desde`, só os de depois)"""
    s = situacao(lista, eventos, nomes, ultimos=0)
    evs = [e for e in eventos if not desde or str(e.get("quando", "")) > str(desde)]
    return {"obra": slug, "nome": nome, "atualizado": _agora(), "lista_gerada": lista.get("gerado"),
            "etapas": list(ETAPAS.keys()),
            "total": {"kg": s["total"]["kg"], "itens": s["total"]["itens"]},
            "andamento": {k: {"kg": v["kg"], "pct": v["pct"]} for k, v in s["andamento"].items()},
            "itens": [OrderedDict([("marca", x["id"]), ("tipo", x["tipo"]), ("quantidade", x["quantidade"]),
                                   ("kg_unidade", x["kg_unidade"])] + [(e, x["feito"][e]) for e in ETAPAS])
                      for x in s["itens"]],
            "eventos": [{"id": e.get("id"), "quando": e.get("quando"), "data": e.get("data"), "quem": e.get("quem"),
                         "etapa": e.get("etapa"), "marca": e.get("item"), "quantidade": e.get("quantidade"),
                         "kg": e.get("kg"), "estorno_de": e.get("estorno_de")} for e in evs]}


def ler_lista(pasta_projeto: str) -> dict:
    cam = os.path.join(pasta_projeto, LISTA)
    if not os.path.exists(cam):
        raise ErroControle("esta obra ainda não tem a lista de materiais: detalhe a obra (Produção › Lista de materiais) primeiro")
    with open(cam, encoding="utf-8") as f:
        return json.load(f)


def ler_nomes(pasta_projeto: str) -> dict:
    cam = os.path.join(pasta_projeto, "detalhamento", "nomes.json")
    try:
        with open(cam, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
