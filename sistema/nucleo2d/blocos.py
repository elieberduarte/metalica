# -*- coding: utf-8 -*-
"""A biblioteca de blocos da empresa (usuário, 24/10: "Biblioteca da empresa" — os blocos para todas as obras: detalhe
típico, símbolo, nota padrão; e "Como no AutoCAD" — a inserção é um objeto só, editar o bloco muda todas, X explode,
o DXF sai com BLOCK/INSERT).

Um arquivo do programa, na pasta de dados (como as penas de impressão): {"blocos": {nome: definicao}}. A definição é
{"entidades": [...], "alterado", "origem", "escala_desenho"}: as entidades do CAD no referencial do bloco, com o ponto
de base na origem. Cada desenho guarda também as que usa (`metadados.blocos`), para abrir em outro computador e para
o DXF; a inserção é a entidade `Bloco` (nucleo2d/desenho.py)."""
import datetime
import json
import os
from typing import Optional

from nucleo.base import ErroDeDados
from nucleo2d.desenho import TIPOS

ARQUIVO = "blocos-da-biblioteca.json"


def _ler_arquivo(caminho: str) -> dict:
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f) or {}
    except (OSError, ValueError):
        return {}
    blocos = dados.get("blocos") if isinstance(dados, dict) else None
    return blocos if isinstance(blocos, dict) else {}


def ler(caminho: str) -> dict:
    """Os blocos da biblioteca: {nome: definicao}."""
    return _ler_arquivo(caminho)


def definicao_valida(definicao) -> dict:
    """A definição limpa (as entidades de tipo conhecido); ErroDeDados se não há nenhuma."""
    if not isinstance(definicao, dict):
        raise ErroDeDados("definição de bloco inválida.")
    ents = [e for e in definicao.get("entidades") or [] if isinstance(e, dict) and e.get("tipo") in TIPOS]
    if not ents:
        raise ErroDeDados("o bloco não tem nada desenhado.")
    out = {"entidades": ents}
    for k in ("origem", "escala_desenho", "descricao"):
        if definicao.get(k) not in (None, ""):
            out[k] = definicao[k]
    return out


def _gravar(caminho: str, blocos: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"blocos": blocos}, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def gravar(caminho: str, nome: str, definicao: dict) -> dict:
    """Grava (ou redefine) o bloco `nome` na biblioteca. Devolve a definição gravada."""
    nome = str(nome or "").strip()
    if not nome:
        raise ErroDeDados("dê um nome ao bloco.")
    d = definicao_valida(definicao)
    d["alterado"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    blocos = _ler_arquivo(caminho)
    blocos[nome] = d
    _gravar(caminho, blocos)
    return d


def excluir(caminho: str, nome: str) -> bool:
    """Tira o bloco da biblioteca (os desenhos que já o usam continuam com a cópia deles)."""
    blocos = _ler_arquivo(caminho)
    if nome not in blocos:
        return False
    del blocos[nome]
    _gravar(caminho, blocos)
    return True


def rota(caminho: str, corpo: Optional[dict]) -> dict:
    """GET (corpo None) → {blocos}; POST {acao: "gravar", nome, definicao} ou {acao: "excluir", nome} → {blocos}."""
    if corpo is not None:
        acao = corpo.get("acao")
        if acao == "gravar":
            gravar(caminho, corpo.get("nome"), corpo.get("definicao"))
        elif acao == "excluir":
            excluir(caminho, str(corpo.get("nome") or ""))
        else:
            raise ErroDeDados("ação de blocos inválida: %s" % acao)
    return {"blocos": ler(caminho)}
