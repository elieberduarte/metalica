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
    # o número de cada unidade é o dos títulos das pranchas (nomes.numerar_unidades: o mesmo nome numera junto, na ordem
    # natural das marcas — TESOURA 14-1 e 14-2, Posto 12/11), não a ordem da lista por peso
    from nucleo2d.detalhe.nomes import numerar_unidades
    ids_de = numerar_unidades((c.get("marca"), nome, int(c.get("instancias") or 1))
                              for nome, grupo in por_nome.items() for c in grupo)
    # o lugar de cada unidade (nomes.json → "unidades", detalhe/unidades.py, 13/11): o número pela ordem dos eixos e as
    # peças dela no 3D. Vale só quando o Detalhar separou o mesmo número de unidades que a lista tem
    lugar = (nomes or {}).get("unidades") or {}
    for nome, grupo in por_nome.items():
        for c in grupo:
            n = int(c.get("instancias") or 1)
            kg_u = float(c.get("peso_total") or 0.0) / n if n else 0.0
            tipo = tipos_cj.get(c.get("marca")) or _TIPO_CATEGORIA.get(str(c.get("categoria") or "").upper(), "conjunto")
            ids_c = list(ids_de.get(str(c.get("marca")), []))
            un = lugar.get(str(c.get("marca"))) or []
            if len(un) != n or any(not u.get("nome") for u in un):
                un = []
            for k in range(n):
                x = {"id": un[k]["nome"] if un else (ids_c[k] if k < len(ids_c) else "%s-%d" % (nome, k + 1)), "nome": nome,
                     "tipo": tipo, "origem": "conjunto", "refs": [c.get("marca")],
                     "descricao": "%d peças" % int(c.get("pecas_unidade") or 0),
                     "quantidade": 1, "kg_unidade": round(kg_u, 3), "kg": round(kg_u, 3)}
                if un and un[k].get("ids"):
                    x["pecas3d"] = list(un[k]["ids"])      # as peças desta unidade no modelo 3D (controle3d.js)
                saida.append(x)
            for k, q in _total_por_posicao(c).items():
                p = por_marca.get(k)
                if p is not None:
                    usados[id(p)] += q

    # --- as peças que sobram fora dos conjuntos: uma linha por posição, com a quantidade
    ids = {x["id"] for x in saida}
    # as variantes que o 3D não distingue pelo nome (nomes.json → "variantes" {id da peça: [posição, conjunto]}: as chapas
    # "Suporte de terça ST1 (aa)", "(ab)"… do Posto, todas "Suporte de terça ST1" no 3D e sem marca de posição) — com as
    # peças de cada uma, o 3D acende a variante sozinha em vez do grupo todo (13/11)
    pecas_var: Dict[str, List[str]] = {}
    for pid, (vpos, vcj) in ((k, (list(v) + ["", ""])[:2]) for k, v in ((nomes or {}).get("variantes") or {}).items()):
        if vpos and not vcj:
            pecas_var.setdefault(str(vpos), []).append(str(pid))
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
        partes = [m.strip() for m in str(p.get("marca") or "").split(" / ") if m.strip()]
        if partes and all(m in pecas_var for m in partes):
            pv = sorted({i for m in partes for i in pecas_var[m]})
            if len(pv) == resto:                        # só quando fecha com a quantidade da linha
                saida[-1]["pecas3d"] = pv
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


def feito(eventos: List[dict], mapa: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, Counter]:
    """{item: Counter({etapa: quantidade})} dos apontamentos que valem; com `mapa` (resolver), cada apontamento conta no
    item de agora (o que seguiu a peça depois de um Detalhar que renumerou); o sem item de agora fica no nome dele"""
    out: Dict[str, Counter] = {}
    for e in _validos(eventos):
        item = (mapa or {}).get(e.get("id")) or e.get("item")
        out.setdefault(item, Counter())[e.get("etapa")] += int(e.get("quantidade") or 0)
    return out


# ------------------------------------------------------------------ o apontamento segue a peça
#: quantos ids de peças da unidade o apontamento guarda ("ancora"): o bastante para achar a unidade de novo no modelo
ANCORA = 12


def ancora(it: dict) -> List[str]:
    """as peças que identificam a unidade no modelo 3D (as primeiras, em ordem), [] quando o item não tem lugar"""
    return sorted(str(i) for i in (it.get("pecas3d") or []))[:ANCORA]


def resolver(eventos: List[dict], its: List[dict]) -> Dict[str, Optional[str]]:
    """{id do apontamento: item de agora (ou None)} — o apontamento guarda o NOME do item, e o Detalhar pode renumerar
    (13/11: o número pela ordem dos eixos trocou 35 nomes no Posto; a TESOURA 1-1 de antes é a 1-7 de agora). Nunca
    reescreve o arquivo; acha o item de agora, nesta ordem:
      1. pela âncora (as peças da unidade no 3D): a peça física vence o nome — o mesmo nome pode ser outra tesoura agora;
      2. pelo nome, quando ele continua na mesma marca;
      3. pela marca: a peça avulsa da mesma posição; a unidade de conjunto sem lugar, a da marca com menos apontado
         naquela etapa (unidades sem lugar são iguais entre si).
    O que não se acha fica None ("fora da lista", como antes)."""
    por_id = {x["id"]: x for x in its}
    por_peca: Dict[str, str] = {}
    avulso: Dict[str, str] = {}
    unidades: Dict[str, List[str]] = {}
    for x in its:
        for i in x.get("pecas3d") or []:
            por_peca[str(i)] = x["id"]
        refs = [str(r) for r in x.get("refs") or []]
        if x.get("origem") == "pecas":
            for r in refs:
                avulso[r] = x["id"]
                for parte in r.split(" / "):
                    avulso.setdefault(parte.strip(), x["id"])
        elif refs:
            unidades.setdefault(refs[0], []).append(x["id"])
    usado: Dict[tuple, int] = Counter()
    mapa: Dict[str, Optional[str]] = {}
    for e in eventos:
        if e.get("estorno_de"):
            continue
        alvo = None
        anc = [str(i) for i in e.get("ancora") or []]
        if anc:
            votos = Counter(por_peca[i] for i in anc if i in por_peca)
            if votos:
                cand, n = votos.most_common(1)[0]
                if 2 * n >= len(anc):
                    alvo = cand
        refs = [str(r) for r in e.get("refs") or []]
        if alvo is None and e.get("item") in por_id and (not refs or [str(r) for r in por_id[e["item"]].get("refs") or []] == refs):
            alvo = e["item"]
        if alvo is None and refs:
            if refs[0] in avulso:
                alvo = avulso[refs[0]]
            elif refs[0] in unidades:
                etapa = e.get("etapa")
                alvo = min(unidades[refs[0]], key=lambda u: (usado[(u, etapa)], unidades[refs[0]].index(u)))
        if alvo is not None:
            usado[(alvo, e.get("etapa"))] += int(e.get("quantidade") or 0)
        mapa[e.get("id")] = alvo
    for e in eventos:                                   # o estorno vai para onde foi o original
        if e.get("estorno_de"):
            mapa[e.get("id")] = mapa.get(e["estorno_de"])
    return mapa


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
    its = itens(lista, nomes)
    por_id = {x["id"]: x for x in its}
    it = por_id.get(item)
    if it is None:
        raise ErroControle("%s não está na lista de materiais atual" % item)
    dia = _data(data)
    with _TRAVA:
        eventos = ler_eventos(pasta_projeto)
        ja = feito(eventos, resolver(eventos, its)).get(item, Counter())[etapa]
        falta = it["quantidade"] - ja
        if falta <= 0:
            raise ErroControle("%s já está completo na %s" % (item, ETAPAS[etapa].lower()))
        if q > falta:
            raise ErroControle("%s: só falta%s %d na %s (pedido: %d)"
                               % (item, "m" if falta != 1 else "", falta, ETAPAS[etapa].lower(), q))
        ev = _evento(it, etapa, q, quem, dia, obs)
        _gravar(pasta_projeto, ev)
    return ev


def _evento(it: dict, etapa: str, q: int, quem: str, dia: str, obs) -> dict:
    ev = {"id": uuid.uuid4().hex[:12], "quando": _agora(), "data": dia, "quem": quem or "", "etapa": etapa,
          "item": it["id"], "refs": it["refs"], "quantidade": q, "kg": round(q * it["kg_unidade"], 3),
          "estorno_de": None, "obs": str(obs or "")[:300]}
    if ancora(it):
        ev["ancora"] = ancora(it)                       # as peças da unidade: o apontamento segue a peça (resolver)
    return ev


#: o máximo de itens num apontamento de vários (a obra inteira do Posto tem 652)
MAIS_ITENS = 2000


def apontar_varios(pasta_projeto: str, lista: dict, ids: List[str], etapa: str, quem: str,
                   data=None, obs: str = "", nomes: Optional[dict] = None) -> dict:
    """aponta, de uma vez, TUDO o que falta na etapa em cada item escolhido (na lista ou no 3D ao lado; usuário 13/11,
    "apontar vários de uma vez", as 6 MT71). Um evento por item — o ERP, a nuvem e o estorno seguem como no apontar de
    um. Item já completo na etapa é pulado (volta em "pulados"); item fora da lista recusa tudo, sem gravar nada.
    Devolve {"eventos": [...], "pulados": [ids]}."""
    if etapa not in ETAPAS:
        raise ErroControle("etapa desconhecida: %r" % etapa)
    pedidos = list(OrderedDict.fromkeys(str(i) for i in (ids or []) if str(i or "").strip()))
    if not pedidos:
        raise ErroControle("nenhum item escolhido")
    if len(pedidos) > MAIS_ITENS:
        raise ErroControle("escolha até %d itens de uma vez (pedido: %d)" % (MAIS_ITENS, len(pedidos)))
    its = itens(lista, nomes)
    por_id = {x["id"]: x for x in its}
    fora = [i for i in pedidos if i not in por_id]
    if fora:
        raise ErroControle("fora da lista de materiais atual: %s" % ", ".join(fora[:10]) + ("…" if len(fora) > 10 else ""))
    dia = _data(data)
    with _TRAVA:
        eventos = ler_eventos(pasta_projeto)
        ja = feito(eventos, resolver(eventos, its))
        novos, pulados = [], []
        for i in pedidos:
            it = por_id[i]
            falta = it["quantidade"] - ja.get(i, Counter())[etapa]
            if falta <= 0:
                pulados.append(i)
                continue
            novos.append(_evento(it, etapa, falta, quem, dia, obs))
        if not novos:
            raise ErroControle("%s já est%s completo%s na %s" % (
                pulados[0] if len(pulados) == 1 else "os %d itens escolhidos" % len(pulados),
                "á" if len(pulados) == 1 else "ão", "" if len(pulados) == 1 else "s", ETAPAS[etapa].lower()))
        for ev in novos:
            _gravar(pasta_projeto, ev)
    return {"eventos": novos, "pulados": pulados}


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
        if orig.get("ancora"):
            ev["ancora"] = list(orig["ancora"])
        _gravar(pasta_projeto, ev)
    return ev


# ------------------------------------------------------------------ o andamento
def situacao(lista: dict, eventos: List[dict], nomes: Optional[dict] = None, ultimos: int = 30) -> dict:
    """o que a aba Controle mostra: os itens com o feito por etapa, o andamento em kg e %, os últimos eventos e os
    apontamentos de itens que não estão mais na lista"""
    its = itens(lista, nomes)
    mapa = resolver(eventos, its)
    f = feito(eventos, mapa)
    kg_total = round(sum(x["kg"] for x in its), 1)
    andamento = OrderedDict()
    for etapa, titulo in ETAPAS.items():
        kg = sum(min(f.get(x["id"], Counter())[etapa], x["quantidade"]) * x["kg_unidade"] for x in its)
        completos = sum(1 for x in its if f.get(x["id"], Counter())[etapa] >= x["quantidade"])
        andamento[etapa] = {"titulo": titulo, "kg": round(kg, 1), "pct": round(100.0 * kg / kg_total, 1) if kg_total else 0.0,
                            "itens_completos": completos}
    for x in its:
        x["feito"] = {e: int(f.get(x["id"], Counter())[e]) for e in ETAPAS}
        # apontado a mais (duas pessoas no mesmo item ao mesmo tempo, com a obra compartilhada — 13/11): fica à vista para
        # alguém estornar, em vez de sumir no "completo"
        mais = {e: q - x["quantidade"] for e, q in x["feito"].items() if q > x["quantidade"]}
        if mais:
            x["a_mais"] = mais
    fora = sorted({e.get("item") for e in _validos(eventos) if not mapa.get(e.get("id"))})
    # os que seguiram a peça para outro nome (o Detalhar renumerou): a tela avisa "era TESOURA 1-1, agora 1-7"
    seguiram = sorted({(e.get("item"), mapa[e.get("id")]) for e in _validos(eventos)
                       if mapa.get(e.get("id")) and mapa[e.get("id")] != e.get("item")})
    hoje = _hoje().isoformat()
    validos_hoje = [e for e in _validos(eventos) if str(e.get("quando", ""))[:10] == hoje]
    estornados = {e.get("estorno_de") for e in eventos if e.get("estorno_de")}
    recentes = []
    for e in reversed(eventos[-ultimos:] if ultimos else eventos):
        r = dict(e)
        r["estornado"] = e.get("id") in estornados
        if mapa.get(e.get("id")) and mapa[e.get("id")] != e.get("item"):
            r["item_atual"] = mapa[e.get("id")]
        recentes.append(r)
    return {"etapas": [{"chave": k, "titulo": t} for k, t in ETAPAS.items()],
            "total": {"kg": kg_total, "itens": len(its), "unidades_conjunto": sum(1 for x in its if x["origem"] == "conjunto"),
                      "peso_lista": (lista.get("totais") or {}).get("peso")},
            "andamento": andamento, "itens": its, "fora_da_lista": fora,
            "seguiram": [{"era": a, "agora": b} for a, b in seguiram],
            "hoje": {"apontamentos": len(validos_hoje), "kg": round(sum(float(e.get("kg") or 0) for e in validos_hoje), 1)},
            "eventos": recentes, "lista_gerada": lista.get("gerado")}


# ------------------------------------------------------------------ as cores do 3D
# a situação de cada peça no modelo 3D ao lado da lista (usuário, 12/11: "toda a estrutura não feita cinza, produzida azul,
# pintada verde", com a ferramenta para escolher os tons). Valem para todas as obras desta máquina: um arquivo na pasta
# dos projetos (o "_" a tira da lista de projetos).
CORES_PADRAO = OrderedDict([("falta", "#9aa3ad"), ("producao", "#2f6fd6"), ("pintura", "#2e9d57"), ("destaque", "#f2b01e")])
ARQUIVO_CORES = "_producao-cores.json"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def ler_cores(pasta_projetos: str) -> dict:
    """as cores escolhidas, com o padrão no que faltar ou estiver errado"""
    cores = OrderedDict(CORES_PADRAO)
    try:
        with open(os.path.join(pasta_projetos, ARQUIVO_CORES), encoding="utf-8") as f:
            gravadas = json.load(f)
    except (OSError, ValueError):
        gravadas = {}
    for k in cores:
        v = (gravadas or {}).get(k) if isinstance(gravadas, dict) else None
        if isinstance(v, str) and _HEX.match(v):
            cores[k] = v.lower()
    return cores


def gravar_cores(pasta_projetos: str, cores: dict) -> dict:
    """grava as cores (só as quatro conhecidas, em #rrggbb); `cores` vazio volta ao padrão"""
    novas = OrderedDict()
    for k, v in (cores or {}).items():
        if k not in CORES_PADRAO:
            raise ErroControle("cor desconhecida: %r" % k)
        if not (isinstance(v, str) and _HEX.match(v)):
            raise ErroControle("cor inválida para %s: %r (use #rrggbb)" % (k, v))
        novas[k] = v.lower()
    caminho_ = os.path.join(pasta_projetos, ARQUIVO_CORES)
    with _TRAVA:
        if not novas:
            if os.path.exists(caminho_):
                os.remove(caminho_)
        else:
            tmp = caminho_ + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(novas, f, ensure_ascii=False, indent=1)
            os.replace(tmp, caminho_)
    return ler_cores(pasta_projetos)


def para_erp(slug: str, nome: str, lista: dict, eventos: List[dict], nomes: Optional[dict] = None,
             desde: Optional[str] = None) -> dict:
    """o que o ERP lê (só leitura): o andamento já somado, cada item e os eventos (com `desde`, só os de depois)"""
    s = situacao(lista, eventos, nomes, ultimos=0)
    mapa = resolver(eventos, itens(lista, nomes))
    evs = [e for e in eventos if not desde or str(e.get("quando", "")) > str(desde)]
    return {"obra": slug, "nome": nome, "atualizado": _agora(), "lista_gerada": lista.get("gerado"),
            "etapas": list(ETAPAS.keys()),
            "total": {"kg": s["total"]["kg"], "itens": s["total"]["itens"]},
            "andamento": {k: {"kg": v["kg"], "pct": v["pct"]} for k, v in s["andamento"].items()},
            "itens": [OrderedDict([("marca", x["id"]), ("tipo", x["tipo"]), ("quantidade", x["quantidade"]),
                                   ("kg_unidade", x["kg_unidade"])] + [(e, x["feito"][e]) for e in ETAPAS])
                      for x in s["itens"]],
            "eventos": [{"id": e.get("id"), "quando": e.get("quando"), "data": e.get("data"), "quem": e.get("quem"),
                         "etapa": e.get("etapa"), "marca": e.get("item"), "marca_atual": mapa.get(e.get("id")),
                         "quantidade": e.get("quantidade"),
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
