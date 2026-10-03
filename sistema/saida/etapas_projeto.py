# -*- coding: utf-8 -*-
"""As etapas da obra para a barra do projeto (web/etapas.js), a mesma em todas as telas de um projeto.

Decisão do usuário (03/10/2026): seis etapas, na ordem em que a obra acontece — Entrada, Modelo 3D (com o cálculo
dentro), Comercial (orçamento, proposta e contrato juntos), Detalhamento, Produção, Obra. Cada etapa diz onde se vai
ao clicar, os atalhos dela (o menu que abre) e uma situação tirada dos arquivos do projeto: "feita", "andamento"
ou "" (não começou). A situação é uma leitura, não um controle: o usuário marca as etapas da obra na tela Comercial.
"""
import json
import os
from typing import Dict, List
from urllib.parse import quote


def _ler_json(caminho: str) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _tem(pasta: str, *partes: str) -> bool:
    return os.path.exists(os.path.join(pasta, *partes))


def _arquivos(pasta: str) -> List[str]:
    try:
        return os.listdir(pasta)
    except OSError:
        return []


def etapas(slug: str, pasta: str, projeto: dict) -> List[Dict]:
    s = quote(slug)
    comercial = _ler_json(os.path.join(pasta, "comercial", "comercial.json"))
    proposta, contrato, marcadas = comercial.get("proposta") or {}, comercial.get("contrato") or {}, comercial.get("etapas") or {}
    tem_modelo = _tem(pasta, "modelo.json")
    desenhos = [n for n in _arquivos(os.path.join(pasta, "desenhos-2d")) if not n.startswith(".")]
    detalh = _arquivos(os.path.join(pasta, "detalhamento"))
    galpao = str(projeto.get("tipo") or "") == "galpao"

    def sit(feita: bool, andamento: bool) -> str:
        return "feita" if feita else ("andamento" if andamento else "")

    def marcada(k: str) -> str:
        return str((marcadas.get(k) or {}).get("situacao") or "")

    entrada = sit(bool(projeto.get("origem_ifc") or projeto.get("projeto_recebido") or tem_modelo or desenhos), False)
    modelo = sit(tem_modelo and (_tem(pasta, "esforcos.json") or bool(proposta) or "lista-de-materiais.json" in detalh), tem_modelo)
    com = sit(contrato.get("situacao") == "assinado", bool(proposta) or _tem(pasta, "orcamento", "orcamento.json"))
    pranchas = any("prancha" in n.lower() for n in desenhos + detalh)
    detalhamento = sit(pranchas or marcada("projeto") == "concluida", bool(desenhos) or "nomes.json" in detalh)
    producao = sit(marcada("pintura") == "concluida" or marcada("fabricacao") == "concluida",
                   "lista-de-materiais.json" in detalh or marcada("fabricacao") == "andamento")
    obra = sit(marcada("entrega") == "concluida", marcada("montagem") in ("andamento", "concluida"))

    area = "/dividida?projeto=%s" % s
    menu = lambda *caminho: {"menu": list(caminho)}                    # noqa: E731 — um item da barra única
    link = lambda url: {"link": url}                                   # noqa: E731
    return [
        {"chave": "entrada", "nome": "Entrada", "situacao": entrada, "url": area + "&vista=2d",
         "dica": "o que o cliente e o projetista mandaram: IFC, arquitetônico, projeto, considerações de cálculo",
         "itens": [dict(texto="Importar IFC de outro programa…", **menu("Arquivo", "Importar", "IFC de outro programa…")),
                   dict(texto="Importar o arquitetônico do cliente…", **menu("Arquivo", "Importar", "Arquitetônico do cliente (DXF/PDF)…")),
                   dict(texto="Importar o projeto do projetista…", **menu("Arquivo", "Importar", "Projeto do projetista (DXF/PDF)…")),
                   dict(texto="Ler folhas e considerações de cálculo", **menu("Modelo", "Montar pelo projeto recebido", "2. Ler folhas e considerações de cálculo")),
                   dict(texto="Abrir a pasta do projeto", **menu("Arquivo", "Abrir a pasta do projeto"))]},
        {"chave": "modelo", "nome": "Modelo 3D", "situacao": modelo,
         "url": ("/dimensionar?projeto=%s" % s) if galpao else area + "&vista=3d",
         "dica": "lançar, montar e calcular a estrutura",
         "itens": [dict(texto="Abrir o modelo 3D", **link(area + "&vista=3d")),
                   dict(texto="Calcular a estrutura", **menu("Modelo", "Calcular a estrutura")),
                   dict(texto="Dimensionar: o perfil mais leve que passa…", **menu("Modelo", "Dimensionar: o perfil mais leve que passa…")),
                   dict(texto="Resultado da análise…", **menu("Modelo", "Resultado da análise…")),
                   dict(texto="Esforços da estrutura…", **menu("Modelo", "Esforços da estrutura…")),
                   dict(texto="Memorial do dimensionamento (PDF)", **menu("Modelo", "Memorial do dimensionamento (PDF)")),
                   dict(texto="Eixos da obra…", **menu("Modelo", "Eixos da obra…"))]},
        {"chave": "comercial", "nome": "Comercial", "situacao": com, "url": "/comercial?projeto=%s#proposta" % s,
         "dica": "orçamento, proposta com as imagens do 3D e contrato",
         "itens": [dict(texto="Orçamento da obra", **link("/materiais?projeto=%s#orcamento" % s)),
                   dict(texto="Proposta comercial", **link("/comercial?projeto=%s#proposta" % s)),
                   dict(texto="Contrato", **link("/comercial?projeto=%s#contrato" % s)),
                   dict(texto="Documentos da obra", **link("/comercial?projeto=%s#documentos" % s))]},
        {"chave": "detalhamento", "nome": "Detalhamento", "situacao": detalhamento, "url": area + "&vista=2d",
         "dica": "desenhos de fabricação, conjuntos e pranchas",
         "itens": [dict(texto="Abrir os desenhos", **link(area + "&vista=2d")),
                   dict(texto="Detalhar peças e conjuntos…", **menu("Detalhamento", "Detalhar peças e conjuntos…")),
                   dict(texto="Montar pranchas (automático)…", **menu("Detalhamento", "Pranchas", "Montar pranchas (automático)…")),
                   dict(texto="PDF de todas as pranchas…", **menu("Arquivo", "Exportar", "PDF de todas as pranchas…"))]},
        {"chave": "producao", "nome": "Produção", "situacao": producao, "url": "/materiais?projeto=%s#geral" % s,
         "dica": "lista de materiais, plano de corte e os resumos da fábrica",
         "itens": [dict(texto="Lista de materiais", **link("/materiais?projeto=%s#geral" % s)),
                   dict(texto="Plano de corte", **link("/materiais?projeto=%s#corte" % s)),
                   dict(texto="Romaneio por posição", **link("/materiais?projeto=%s#romaneio" % s)),
                   dict(texto="Resumo da obra e de materiais", **link("/materiais?projeto=%s#resumos" % s))]},
        {"chave": "obra", "nome": "Obra", "situacao": obra, "url": "/comercial?projeto=%s#obra" % s,
         "dica": "etapas, parcelas, aditivos e entrega",
         "itens": [dict(texto="Etapas e pagamentos", **link("/comercial?projeto=%s#obra" % s)),
                   dict(texto="Contrato", **link("/comercial?projeto=%s#contrato" % s))]},
    ]


def biblioteca(slug: str) -> List[Dict]:
    """O que vale para todas as obras (o botão Biblioteca da barra)."""
    s = quote(slug)
    return [{"texto": "Catálogo de peças e perfis", "link": "/catalogo"},
            {"texto": "Ligações e acessórios", "link": "/ligacoes"},
            {"texto": "Tabela de preços", "link": "/materiais?projeto=%s#orcamento" % s, "dica": "botão \"Trocar a tabela…\" no orçamento"},
            {"texto": "Dados da empresa e logo", "link": "/comercial?projeto=%s#empresa" % s},
            {"texto": "Ajuda do programa", "link": "/ajuda", "nova": True}]
