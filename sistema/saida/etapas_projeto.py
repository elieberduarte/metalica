# -*- coding: utf-8 -*-
"""As telas do projeto para o cabeçalho (web/etapas.js), o mesmo em todas as telas de um projeto.

03/10/2026, primeira versão: seis etapas (Entrada, Modelo 3D, Comercial, Detalhamento, Produção, Obra). No mesmo dia
o usuário achou o topo bagunçado ("3 linhas de informações, modelo 3D aparece 2 vezes"): Entrada, Modelo 3D e
Detalhamento abriam a mesma área de trabalho, só com outra vista. Ficaram quatro telas, uma por setor da empresa:
Engenharia (entrada do projeto, modelo 3D, cálculo e detalhamento: a área de trabalho, com a vista 2D/3D dentro),
Comercial (orçamento, proposta, contrato), Produção (lista de materiais, corte, romaneio) e Obra (etapas e pagamentos).
Cada tela diz onde se vai ao clicar, os atalhos dela (achados pela busca Ctrl+K) e uma situação tirada dos arquivos
do projeto: "feita", "andamento" ou "" (não começou). A situação é uma leitura, não um controle: o usuário marca as
etapas da obra na tela Comercial.
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


def etapas(slug: str, pasta: str, projeto: dict, comercial_ligado: bool = True) -> List[Dict]:
    """As telas do projeto. Sem `comercial_ligado` (o programa instalado: a parte comercial fica só no
    desenvolvimento, pedido de 05/10) saem Comercial e Obra, que moram na tela /comercial."""
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

    entrada = bool(projeto.get("origem_ifc") or projeto.get("projeto_recebido") or tem_modelo or desenhos)
    modelo_feito = tem_modelo and (_tem(pasta, "esforcos.json") or bool(proposta) or "lista-de-materiais.json" in detalh)
    pranchas = any("prancha" in n.lower() for n in desenhos + detalh)
    engenharia = sit(pranchas or marcada("projeto") == "concluida", entrada or modelo_feito or "nomes.json" in detalh)
    com = sit(contrato.get("situacao") == "assinado", bool(proposta) or _tem(pasta, "orcamento", "orcamento.json"))
    producao = sit(marcada("pintura") == "concluida" or marcada("fabricacao") == "concluida",
                   "lista-de-materiais.json" in detalh or marcada("fabricacao") == "andamento")
    obra = sit(marcada("entrega") == "concluida", marcada("montagem") in ("andamento", "concluida"))

    area = "/dividida?projeto=%s" % s
    menu = lambda *caminho: {"menu": list(caminho)}                    # noqa: E731 — um item da barra única
    link = lambda url: {"link": url}                                   # noqa: E731
    telas = [
        {"chave": "engenharia", "nome": "Engenharia", "situacao": engenharia,
         "url": ("/dimensionar?projeto=%s" % s) if galpao else area + "&vista=3d",
         "dica": "projeto recebido, modelo 3D, cálculo e detalhamento",
         "itens": [dict(texto="Abrir o modelo 3D", **link(area + "&vista=3d")),
                   dict(texto="Abrir os desenhos 2D", **link(area + "&vista=2d")),
                   dict(texto="Importar IFC de outro programa…", **menu("Arquivo", "Importar", "IFC de outro programa…")),
                   dict(texto="Importar o arquitetônico do cliente…", **menu("Arquivo", "Importar", "Arquitetônico do cliente (DXF/PDF)…")),
                   dict(texto="Importar o projeto do projetista…", **menu("Arquivo", "Importar", "Projeto do projetista (DXF/PDF)…")),
                   dict(texto="Ler folhas e considerações de cálculo", **menu("Modelo", "Montar pelo projeto recebido", "2. Ler folhas e considerações de cálculo")),
                   dict(texto="Calcular a estrutura", **menu("Modelo", "Calcular a estrutura")),
                   dict(texto="Dimensionar: o perfil mais leve que passa…", **menu("Modelo", "Dimensionar: o perfil mais leve que passa…")),
                   dict(texto="Resultado da análise…", **menu("Modelo", "Resultado da análise…")),
                   dict(texto="Esforços da estrutura…", **menu("Modelo", "Esforços da estrutura…")),
                   dict(texto="Memorial do dimensionamento (PDF)", **menu("Modelo", "Memorial do dimensionamento (PDF)")),
                   dict(texto="Eixos da obra…", **menu("Modelo", "Eixos da obra…")),
                   dict(texto="Detalhar peças e conjuntos…", **menu("Detalhamento", "Detalhar peças e conjuntos…")),
                   dict(texto="Montar pranchas (automático)…", **menu("Detalhamento", "Pranchas", "Montar pranchas (automático)…")),
                   dict(texto="PDF de todas as pranchas…", **menu("Arquivo", "Exportar", "PDF de todas as pranchas…")),
                   dict(texto="Abrir a pasta do projeto", **menu("Arquivo", "Abrir a pasta do projeto"))]},
        {"chave": "comercial", "nome": "Comercial", "situacao": com, "url": "/comercial?projeto=%s#proposta" % s,
         "dica": "orçamento, proposta com as imagens do 3D e contrato",
         "itens": [dict(texto="Orçamento da obra", **link("/comercial?projeto=%s#orcamento" % s)),
                   dict(texto="Proposta comercial", **link("/comercial?projeto=%s#proposta" % s)),
                   dict(texto="Contrato", **link("/comercial?projeto=%s#contrato" % s)),
                   dict(texto="Documentos da obra", **link("/comercial?projeto=%s#documentos" % s))]},
        {"chave": "producao", "nome": "Produção", "situacao": producao, "url": "/materiais?projeto=%s#geral" % s,
         "dica": "lista de materiais, plano de corte e os resumos da fábrica",
         "itens": [dict(texto="Lista de materiais", **link("/materiais?projeto=%s#geral" % s)),
                   dict(texto="Plano de corte", **link("/materiais?projeto=%s#corte" % s)),
                   dict(texto="Romaneio por posição", **link("/materiais?projeto=%s#romaneio" % s)),
                   dict(texto="Resumo da obra e de materiais", **link("/materiais?projeto=%s#resumos" % s))]},
        {"chave": "obra", "nome": "Obra", "situacao": obra, "url": "/comercial?projeto=%s#obra" % s,
         "dica": "etapas, parcelas, aditivos e entrega",
         "itens": [dict(texto="Etapas e pagamentos", **link("/comercial?projeto=%s#obra" % s))]},
    ]
    return telas if comercial_ligado else [t for t in telas if t["chave"] not in ("comercial", "obra")]


def biblioteca(slug: str, comercial_ligado: bool = True) -> List[Dict]:
    """O que vale para todas as obras (no menu do projeto, à esquerda do cabeçalho). A tabela de preços e os dados
    da empresa são da tela Comercial: sem ela, ficam de fora."""
    s = quote(slug)
    itens = [{"texto": "Catálogo de peças e perfis", "link": "/catalogo"},
            {"texto": "Ligações e acessórios", "link": "/ligacoes"},
            {"texto": "Tabela de preços", "link": "/comercial?projeto=%s#orcamento" % s, "dica": "botão \"Trocar a tabela…\" no orçamento"},
            {"texto": "Dados da empresa e logo", "link": "/comercial?projeto=%s#empresa" % s},
            {"texto": "Ajuda do programa", "link": "/ajuda", "nova": True}]
    return itens if comercial_ligado else [i for i in itens if "/comercial" not in i["link"]]
