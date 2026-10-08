# -*- coding: utf-8 -*-
"""Os pedidos da tela Comercial (/comercial?projeto=…): app.py só passa o contexto (pasta do projeto,
pasta de dados, leitores da lista e do orçamento, a porta do servidor para as imagens 3D)."""
import base64
import json
import os
import re
from datetime import date, datetime
from typing import Callable, Optional

from saida import comercial as C


class Contexto:
    def __init__(self, slug: str, pasta: str, dados: str, projeto: dict, lista: Callable[[], dict],
                 orcamento: Callable[[], dict], descrever: Callable[[str], dict], porta: int = 0):
        self.slug, self.pasta, self.dados, self.projeto = slug, pasta, dados, projeto
        self._lista, self._orc, self.descrever, self.porta = lista, orcamento, descrever, porta
        self._cache = {}

    def lista(self) -> dict:
        if "lista" not in self._cache:
            try:
                self._cache["lista"] = self._lista() or {}
            except Exception:                                # noqa: BLE001 — projeto sem modelo: proposta sem a lista
                self._cache["lista"] = {}
        return self._cache["lista"]

    def orcamento(self) -> dict:
        if "orc" not in self._cache:
            try:
                self._cache["orc"] = self._orc() or {}
            except Exception:                                # noqa: BLE001
                self._cache["orc"] = {}
        return self._cache["orc"]

    def numeros(self) -> Optional[dict]:
        try:
            with open(os.path.join(self.pasta, "detalhamento", "resumo-numeros.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


def _pasta_docs(ctx: Contexto) -> str:
    return os.path.join(ctx.pasta, C.PASTA)


def _nome_arquivo(texto: str, maximo: int = 24) -> str:
    return re.sub(r"[^\w\-]+", "_", str(texto or "obra"), flags=re.UNICODE).strip("_")[:maximo].strip("_") or "obra"


def _imagens_existentes(ctx: Contexto):
    pasta = os.path.join(_pasta_docs(ctx), "imagens")
    try:
        return sorted(os.path.join(pasta, n) for n in os.listdir(pasta) if n.lower().endswith((".jpg", ".png")))
    except OSError:
        return []


LEGENDAS = {"capa": "", "aerea_frente": "Estrutura — vista aérea", "aerea_frente_telhas": "Vista aérea com a cobertura",
            "aerea_tras": "Vista posterior", "perspectiva": "Perspectiva lateral", "lateral": "Vista frontal", "topo": "Vista superior"}


def estado(ctx: Contexto) -> dict:
    """O estado completo para a tela (cria a proposta inicial na primeira vez, sem gravar)."""
    est = C.ler(ctx.pasta)
    empresa = C.ler_empresa(ctx.dados)
    P = est["proposta"]
    novo = not P
    if novo:
        P = C.proposta_inicial(ctx.projeto, ctx.lista(), ctx.orcamento(), ctx.numeros(), empresa)
        P["imagens"] = [{"arquivo": a, "legenda": LEGENDAS.get(os.path.splitext(os.path.basename(a))[0], ""), "usar": True}
                        for a in _imagens_existentes(ctx)]
    Cn = est["contrato"]
    orc = ctx.orcamento()
    tot = (orc or {}).get("totais") or {}
    pasta = _pasta_docs(ctx)
    arquivos = []
    if os.path.isdir(pasta):
        for n in sorted(os.listdir(pasta)):
            cam = os.path.join(pasta, n)
            if os.path.isfile(cam) and n.lower().endswith((".pdf", ".docx")):
                arquivos.append(ctx.descrever(cam))
    imagens = [dict(i, url=ctx.descrever(i["arquivo"])["url"]) for i in P.get("imagens") or [] if i.get("arquivo") and os.path.exists(i["arquivo"])]
    for k in ("logo", "logo_claro"):
        if empresa.get(k):
            empresa[k + "_url"] = ctx.descrever(empresa[k])["url"]
    return {
        "proposta": dict(P, imagens=imagens), "proposta_nova": novo, "contrato": Cn, "tem_contrato": bool(Cn),
        "etapas": C.etapas(est, ctx.pasta), "financeiro": C.resumo_financeiro(Cn) if Cn else None,
        "historico": list(reversed(est.get("historico") or []))[:40],
        "empresa": empresa, "empresa_incompleta": not (empresa.get("razao_social") and empresa.get("cnpj")),
        "avisos_proposta": C.avisos_proposta(P), "avisos_contrato": C.avisos_contrato(P, Cn) if Cn else [],
        "exclusoes_opcionais": C.EXCLUSOES_OPCIONAIS, "situacoes": list(C.SITUACOES),
        "orcamento": {"tabela": tot.get("tabela"), "fechamento": tot.get("fechamento"), "aco_kg": tot.get("aco_kg")},
        "arquivos": arquivos, "projeto": {k: ctx.projeto.get(k, "") for k in ("nome", "cliente", "local", "tipo")},
        "correcoes": C.CORRECOES,
    }


def _limpar_imagens(P: dict) -> dict:
    P = dict(P)
    P["imagens"] = [{"arquivo": i.get("arquivo"), "legenda": i.get("legenda", ""), "usar": i.get("usar", True)}
                    for i in P.get("imagens") or [] if i.get("arquivo")]
    return P


def gravar(ctx: Contexto, corpo: dict) -> dict:
    est = C.ler(ctx.pasta)
    if "proposta" in corpo:
        P = _limpar_imagens(corpo["proposta"] or {})
        if not P.get("numero"):
            P["numero"] = C.proximo_numero(ctx.dados)
            C.registrar(est, "proposta nº %s criada" % P["numero"])
        est["proposta"] = P
    if "contrato" in corpo:
        antes = est.get("contrato") or {}
        est["contrato"] = corpo["contrato"] or {}
        if est["contrato"].get("situacao") == "assinado" and antes.get("situacao") != "assinado":
            C.registrar(est, "contrato marcado como assinado")
        pagas_antes = sum(1 for p in antes.get("parcelas") or [] if p.get("paga"))
        pagas = sum(1 for p in est["contrato"].get("parcelas") or [] if p.get("paga"))
        if pagas != pagas_antes:
            C.registrar(est, "parcelas pagas: %d de %d" % (pagas, len(est["contrato"].get("parcelas") or [])))
    if "etapas" in corpo:
        novas = {}
        for e in corpo["etapas"] or []:
            k = e.get("chave")
            if not k:
                continue
            g = {x: e.get(x, "") for x in ("previsto", "realizado", "responsavel", "obs")}
            if not e.get("automatica"):
                g["situacao"] = e.get("situacao") or "pendente"
            antes = (est.get("etapas") or {}).get(k) or {}
            if g.get("situacao") == "concluida" and antes.get("situacao") != "concluida":
                C.registrar(est, "etapa concluída: %s" % e.get("nome", k))
                if not g.get("realizado"):
                    g["realizado"] = date.today().strftime("%d/%m/%Y")
            novas[k] = g
        est["etapas"] = novas
    C.gravar(ctx.pasta, est)
    return estado(ctx)


def iniciar_contrato(ctx: Contexto) -> dict:
    est = C.ler(ctx.pasta)
    if not est.get("proposta"):
        raise ValueError("grave a proposta antes de abrir o contrato")
    if not est.get("contrato"):
        est["contrato"] = C.contrato_inicial(est["proposta"], C.ler_empresa(ctx.dados))
        C.registrar(est, "contrato aberto a partir da proposta %s %s" % (est["proposta"].get("numero"), est["proposta"].get("revisao")))
        C.gravar(ctx.pasta, est)
    return estado(ctx)


def proposta_pdf(ctx: Contexto, corpo: dict) -> dict:
    if corpo.get("proposta"):
        gravar(ctx, {"proposta": corpo["proposta"]})
    from saida import proposta_html
    est = C.ler(ctx.pasta)
    P = dict(est["proposta"])
    P["imagens"] = [i for i in P.get("imagens") or [] if i.get("usar", True)]
    empresa = C.ler_empresa(ctx.dados)
    nome = "Proposta_%s_%s_%s" % (_nome_arquivo(P.get("numero")), P.get("revisao") or "R00", _nome_arquivo((P.get("obra") or {}).get("nome")))
    r = proposta_html.gerar_pdf(P, empresa, _pasta_docs(ctx), nome, ctx.numeros(), ctx.orcamento())
    try:
        os.remove(r.get("html", ""))                       # o HTML usa caminhos locais; o documento é o PDF
    except OSError:
        pass
    if r.get("pdf"):
        revs = [x for x in est["proposta"].get("revisoes") or [] if x.get("revisao") != P.get("revisao")]
        revs.append({"revisao": P.get("revisao"), "data": P.get("data"), "valor": (P.get("investimento") or {}).get("valor"),
                     "arquivo": os.path.basename(r["pdf"]), "gerado": datetime.now().strftime("%Y-%m-%d %H:%M")})
        est["proposta"]["revisoes"] = revs
        C.registrar(est, "proposta %s %s gerada (%s)" % (P.get("numero"), P.get("revisao"), C.reais((P.get("investimento") or {}).get("valor"))))
        C.gravar(ctx.pasta, est)
    s = estado(ctx)
    s["gerado"] = {k: ctx.descrever(v) for k, v in r.items() if k == "pdf"}
    if r.get("erro_pdf"):
        s["erro_pdf"] = r["erro_pdf"]
    return s


def nova_revisao(ctx: Contexto) -> dict:
    est = C.ler(ctx.pasta)
    P = est.get("proposta") or {}
    m = re.match(r"R(\d+)", str(P.get("revisao") or "R00"))
    P["revisao"] = "R%02d" % ((int(m.group(1)) + 1) if m else 1)
    P["data"] = date.today().strftime("%d/%m/%Y")
    est["proposta"] = P
    C.registrar(est, "nova revisão da proposta: %s" % P["revisao"])
    C.gravar(ctx.pasta, est)
    return estado(ctx)


def imagens(ctx: Contexto, avisar=None) -> dict:
    from saida import imagens3d
    if not ctx.porta:
        raise ValueError("o servidor não informou a porta para abrir o modelo 3D")
    pasta = os.path.join(_pasta_docs(ctx), "imagens")
    angulos = ["aerea_frente", "aerea_tras", "perspectiva", "lateral"]
    lista = ctx.lista()
    if any(str(p.get("categoria") or "") == "TELHAS" for p in lista.get("posicoes") or []):
        angulos.insert(1, "aerea_frente+telhas")
    feitas = imagens3d.fotografar(ctx.porta, ctx.slug, pasta, angulos, avisar=avisar)
    est = C.ler(ctx.pasta)
    P = est.get("proposta") or {}
    if P:
        antigas = {i.get("arquivo"): i for i in P.get("imagens") or []}
        P["imagens"] = [{"arquivo": a, "legenda": (antigas.get(a) or {}).get("legenda") or LEGENDAS.get(n, ""),
                         "usar": (antigas.get(a) or {}).get("usar", True)} for n, a in feitas.items()]
        est["proposta"] = P
        C.registrar(est, "imagens do modelo 3D geradas (%d)" % len(feitas))
        C.gravar(ctx.pasta, est)
    s = estado(ctx)
    if not P:
        s["proposta"]["imagens"] = [{"arquivo": a, "legenda": LEGENDAS.get(n, ""), "usar": True, "url": ctx.descrever(a)["url"]}
                                    for n, a in feitas.items()]
    return s


def contrato_docs(ctx: Contexto, corpo: dict) -> dict:
    if corpo.get("contrato"):
        gravar(ctx, {"contrato": corpo["contrato"]})
    from saida import contrato_docs as CD
    est = C.ler(ctx.pasta)
    P, Cn = est.get("proposta") or {}, est.get("contrato") or {}
    if not Cn:
        raise ValueError("abra o contrato antes de gerar os documentos")
    empresa = C.ler_empresa(ctx.dados)
    ct = (Cn.get("contratante") or {}).get("razao_social") or (P.get("cliente") or {}).get("nome")
    nome = "Contrato_%s_%s" % (_nome_arquivo(ct), Cn.get("revisao") or "R00")
    pasta = _pasta_docs(ctx)
    docx = CD.contrato_docx(P, Cn, empresa, os.path.join(pasta, nome + ".docx"))
    corpo_html, css = CD.contrato_html(P, Cn, empresa)
    r = CD.imprimir(corpo_html, css, "Contrato", pasta, nome)
    try:
        os.remove(r.get("html", ""))
    except OSError:
        pass
    C.registrar(est, "contrato %s gerado (Word e PDF)" % (Cn.get("revisao") or "R00"))
    C.gravar(ctx.pasta, est)
    s = estado(ctx)
    s["gerado"] = {"docx": ctx.descrever(docx)}
    if r.get("pdf"):
        s["gerado"]["pdf"] = ctx.descrever(r["pdf"])
    if r.get("erro_pdf"):
        s["erro_pdf"] = r["erro_pdf"]
    return s


def termo_aceite(ctx: Contexto, corpo: dict) -> dict:
    from saida import contrato_docs as CD
    est = C.ler(ctx.pasta)
    P, Cn = est.get("proposta") or {}, est.get("contrato") or {}
    dados = {"data": corpo.get("data") or date.today().strftime("%d/%m/%Y"), "data_vistoria": corpo.get("data_vistoria") or "",
             "pendencias": [x.strip() for x in str(corpo.get("pendencias") or "").splitlines() if x.strip()]}
    corpo_html, css = CD.termo_aceite_html(P, Cn, C.ler_empresa(ctx.dados), dados)
    r = CD.imprimir(corpo_html, css, "Termo de aceite", _pasta_docs(ctx), "Termo_de_Aceite_%s" % _nome_arquivo((P.get("obra") or {}).get("nome")))
    try:
        os.remove(r.get("html", ""))
    except OSError:
        pass
    C.registrar(est, "termo de aceite gerado")
    C.gravar(ctx.pasta, est)
    s = estado(ctx)
    if r.get("pdf"):
        s["gerado"] = {"pdf": ctx.descrever(r["pdf"])}
    if r.get("erro_pdf"):
        s["erro_pdf"] = r["erro_pdf"]
    return s


def aditivo(ctx: Contexto, corpo: dict) -> dict:
    from saida import contrato_docs as CD
    est = C.ler(ctx.pasta)
    P, Cn = est.get("proposta") or {}, est.get("contrato") or {}
    adits = Cn.get("aditivos") or []
    i = int(corpo.get("indice") or 0)
    if not (0 <= i < len(adits)):
        raise ValueError("aditivo inexistente")
    corpo_html, css = CD.aditivo_html(P, Cn, C.ler_empresa(ctx.dados), adits[i], i + 1)
    r = CD.imprimir(corpo_html, css, "Termo aditivo", _pasta_docs(ctx), "Termo_Aditivo_%02d" % (i + 1))
    try:
        os.remove(r.get("html", ""))
    except OSError:
        pass
    C.registrar(est, "termo aditivo nº %d gerado" % (i + 1))
    C.gravar(ctx.pasta, est)
    s = estado(ctx)
    if r.get("pdf"):
        s["gerado"] = {"pdf": ctx.descrever(r["pdf"])}
    return s


def empresa(ctx: Contexto, corpo: dict) -> dict:
    e = corpo.get("empresa") or {}
    C.gravar_empresa(ctx.dados, e)
    marca = C.pasta_marca(ctx.dados)
    for chave, nome in (("logo", "logo.png"), ("logo_claro", "logo_claro.png")):
        b64 = corpo.get(chave + "_base64")
        if b64:
            os.makedirs(marca, exist_ok=True)
            dados = base64.b64decode(str(b64).split(",", 1)[-1])
            if dados[1:4] != b"PNG" and dados[:2] != b"\xff\xd8":
                raise ValueError("o logo tem de ser PNG ou JPEG")
            with open(os.path.join(marca, nome), "wb") as f:
                f.write(dados)
    return estado(ctx)


def parcelas(corpo: dict) -> dict:
    primeira = C.ler_data(corpo.get("primeira")) or date.today()
    return {"parcelas": C.gerar_parcelas(C._f(corpo.get("valor")) or 0, C._f(corpo.get("entrada_pct")) or 0,
                                         int(C._f(corpo.get("n")) or 0), primeira, int(C._f(corpo.get("dia")) or 0) or None)}


def tratar(ctx: Contexto, acao: str, corpo: Optional[dict], avisar=None) -> dict:
    if corpo is None:
        return estado(ctx)
    acoes = {"": lambda: gravar(ctx, corpo), "proposta-pdf": lambda: proposta_pdf(ctx, corpo),
             "nova-revisao": lambda: nova_revisao(ctx), "imagens": lambda: imagens(ctx, avisar),
             "contrato": lambda: iniciar_contrato(ctx), "contrato-docs": lambda: contrato_docs(ctx, corpo),
             "termo-aceite": lambda: termo_aceite(ctx, corpo), "aditivo": lambda: aditivo(ctx, corpo),
             "empresa": lambda: empresa(ctx, corpo), "parcelas": lambda: parcelas(corpo)}
    if acao not in acoes:
        raise ValueError("ação desconhecida: %s" % acao)
    return acoes[acao]()
