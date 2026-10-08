# -*- coding: utf-8 -*-
"""A identidade visual dos documentos da empresa (08/10): as cores, o logo e as peças de
página da proposta comercial (saida/proposta_html.py), para os documentos internos — resumo
da obra e resumo de materiais — saírem com a mesma cara.

Lê ``<dados>/fabrica/empresa.json`` e ``<dados>/fabrica/marca/`` direto, sem importar
``saida.comercial``: o comercial fica só no dev (empacotar/construir.py, MODULOS_SO_DEV) e
os resumos vão no programa instalado. Sem empresa cadastrada, as cores padrão e sem logo.

O logo vai embutido (data URI): a prévia dos resumos abre o HTML por http no iframe da tela
de materiais, e ali um ``file:///`` não carrega."""
import base64
import html
import json
import os

#: As cores da proposta: primária (grafite), escura (o fundo da capa) e destaque (verde-limão).
CORES_PADRAO = {"primaria": "#35434C", "escura": "#1f2a31", "destaque": "#C3D773"}


def ler_marca(dados: str) -> dict:
    """{nome, slogan, site, cores{primaria, escura, destaque}, logo, logo_claro} — os logos como data URI ("" sem arquivo)."""
    emp = {}
    try:
        with open(os.path.join(dados, "fabrica", "empresa.json"), encoding="utf-8") as f:
            emp = json.load(f) or {}
    except (OSError, ValueError, TypeError):
        emp = {}
    cores = dict(CORES_PADRAO)
    cores.update({k: v for k, v in (emp.get("cores") or {}).items() if k in cores and v})
    marca = os.path.join(dados or "", "fabrica", "marca")
    logo = _data_uri(_primeiro(marca, "logo.png", "logo.jpg"))
    logo_claro = _data_uri(_primeiro(marca, "logo_claro.png")) or logo
    return {"nome": emp.get("nome_comercial") or emp.get("razao_social") or "", "slogan": emp.get("slogan") or "",
            "site": emp.get("site") or "", "cores": cores, "logo": logo, "logo_claro": logo_claro}


def _primeiro(pasta: str, *nomes) -> str:
    return next((os.path.join(pasta, n) for n in nomes if os.path.exists(os.path.join(pasta, n))), "")


def _data_uri(caminho: str) -> str:
    if not caminho:
        return ""
    try:
        with open(caminho, "rb") as f:
            b = f.read()
    except OSError:
        return ""
    if len(b) > 600_000:                       # logo grande demais para ir em cada documento
        return ""
    tipo = "image/png" if caminho.lower().endswith(".png") else "image/jpeg"
    return "data:%s;base64,%s" % (tipo, base64.b64encode(b).decode("ascii"))


def logo_ou_nome(marca: dict, claro: bool = False) -> str:
    """O <img> do logo, ou o nome da empresa em texto quando não há logo."""
    src = (marca or {}).get("logo_claro" if claro else "logo") or ""
    if src:
        return '<img class="logo" src="%s" alt="">' % src
    nome = (marca or {}).get("nome") or ""
    return ('<b class="logo-texto">%s</b>' % html.escape(nome)) if nome else ""


def variaveis_css(marca: dict) -> str:
    """O :root com as cores da marca e os tons neutros da proposta."""
    c = dict(CORES_PADRAO)
    c.update((marca or {}).get("cores") or {})
    return (":root { --pri: %s; --pri2: %s; --dest: %s; --fundo: #f3f5f6; --linha: #dde3e7; --texto: #26323a; --mudo: #6b7780; }\n"
            % (c["primaria"], c["escura"], c["destaque"]))
