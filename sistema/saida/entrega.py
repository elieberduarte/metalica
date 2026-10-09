# -*- coding: utf-8 -*-
"""O nome de entrega dos arquivos do projeto (o usuário, 09/10/2026): "OBRA - Arquivo (dd.mm.aaaa).ext" — o que o
navegador sugere ao salvar um PDF, DXF, planilha ou documento gerado, e o título das páginas que se imprimem. Os
arquivos na pasta do projeto continuam com o nome interno (o programa os acha por ele)."""
import json
import os
import re
import time
from typing import Optional

#: O nome legível dos arquivos que o programa gera (o resto: os hífens viram espaço e a primeira letra maiúscula).
NOMES = {
    "resumo-de-materiais": "Resumo de materiais", "resumo-da-obra": "Resumo da obra",
    "lista-de-materiais": "Lista de materiais", "romaneio": "Romaneio", "plano-de-corte": "Plano de corte",
    "resumo-perfis": "Resumo de perfis", "resumo-chapas": "Resumo de chapas", "conjuntos": "Conjuntos",
    "peso-dobras": "Peso das dobras", "pre-moldados": "Pré-moldados", "pranchas": "Pranchas",
    "pranchas-dxf": "Pranchas DXF", "orcamento": "Orçamento", "resumo-de-orcamento": "Resumo de orçamento",
    "memorial": "Memorial de cálculo", "estrutura_a_conferir": "Estrutura a conferir",
}

#: As extensões entregues com o nome de entrega (as outras — páginas, imagens, o modelo — como sempre).
EXTENSOES = {".pdf", ".dxf", ".dwg", ".csv", ".xlsx", ".xls", ".docx", ".doc", ".zip", ".ifc", ".txt"}

_PROIBIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def data_br(quando: Optional[float] = None) -> str:
    """dd.mm.aaaa (o ponto no lugar da barra: a barra não vale em nome de arquivo)."""
    return time.strftime("%d.%m.%Y", time.localtime(quando if quando is not None else time.time()))


def nome_legivel(base: str) -> str:
    """"resumo-de-materiais" → "Resumo de materiais"."""
    b = re.sub(r"\.(pdf|dxf|csv|html?)$", "", base, flags=re.I)
    if b.lower() in NOMES:
        return NOMES[b.lower()]
    t = re.sub(r"[_]+", " ", b)
    t = re.sub(r"(?<=[A-Za-zÀ-ÿ])-(?=[A-Za-zÀ-ÿ])", " ", t)     # palavras-com-hífen; "2026-001" e "R00-A" ficam
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:1].upper() + t[1:]) if t else base


def nome_de_entrega(obra: str, arquivo: str, extensao: str = "", quando: Optional[float] = None) -> str:
    """"VICENTE RESIDENCE - Resumo de materiais (09.10.2026).pdf". O arquivo que já traz a obra no nome (a proposta
    "Proposta 2026-001 R00 ME SOORO - DEPÓSITO QUÍM") perde a parte da obra, que já vai na frente."""
    obra = re.sub(r"\s+", " ", str(obra or "").strip())
    rotulo = nome_legivel(arquivo)
    if obra:
        chave = obra.upper()[:8]
        i = rotulo.upper().find(chave) if len(chave) >= 6 else -1
        if i > 0:
            rotulo = rotulo[:i].rstrip(" -_")
        elif i == 0:
            rotulo = rotulo[len(obra):].lstrip(" -_") or rotulo
    texto = ("%s - %s (%s)" % (obra, rotulo, data_br(quando))) if obra else "%s (%s)" % (rotulo, data_br(quando))
    return _PROIBIDOS.sub(" ", texto).strip() + (extensao or "")


def obra_do_projeto(pasta_projeto: str) -> str:
    """O nome do projeto (a obra) pelo projeto.json da pasta."""
    try:
        with open(os.path.join(pasta_projeto, "projeto.json"), encoding="utf-8") as f:
            return str(json.load(f).get("nome") or "").strip()
    except (OSError, ValueError):
        return ""


def nome_do_arquivo_servido(caminho: str, raiz_projetos: str) -> Optional[str]:
    """O nome de entrega de um arquivo de dentro da pasta de um projeto (a obra pelo projeto dele, a data pela do
    arquivo); None quando não é entrega (fora de projeto ou extensão de outro tipo)."""
    base, ext = os.path.splitext(os.path.basename(caminho))
    if ext.lower() not in EXTENSOES:
        return None
    rel = os.path.relpath(os.path.abspath(caminho), os.path.abspath(raiz_projetos))
    partes = rel.replace("\\", "/").split("/")
    if len(partes) < 2 or partes[0] in ("..", "") or partes[0].startswith("."):
        return None
    try:
        quando = os.path.getmtime(caminho)
    except OSError:
        quando = None
    return nome_de_entrega(obra_do_projeto(os.path.join(raiz_projetos, partes[0])), base, ext.lower(), quando)
