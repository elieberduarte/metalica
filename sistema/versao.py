# -*- coding: utf-8 -*-
"""Versão do programa e impressão digital do núcleo de cálculo.

O memorial imprime as duas. A versão diz de qual edição do programa o documento saiu; a
impressão digital diz se o núcleo de cálculo daquela cópia é o original. É a defesa do
responsável técnico: um resultado contestado confere-se em segundos contra a impressão
da versão publicada, e um memorial gerado por cópia adulterada não fecha.

A impressão é o SHA-256 dos arquivos de `nucleo/`, em ordem de nome e com as quebras de
linha normalizadas (para não mudar entre Windows e Linux). No desenvolvimento ela é
calculada na hora, direto dos fontes. No programa instalado os fontes não existem — o
PyInstaller guarda só o bytecode —, então o empacotamento calcula a impressão e a grava
em `impressao_nucleo.txt`, que viaja junto com o executável.
"""
import hashlib
import os
import sys

NOME = "Metálica"
VERSAO = "0.7.1"

_AQUI = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_IMPRESSAO = "impressao_nucleo.txt"

#: True dentro do executável gerado pelo PyInstaller.
CONGELADO = bool(getattr(sys, "frozen", False))


def calcular_impressao(pasta_nucleo: str = None) -> str:
    """SHA-256 dos fontes de `nucleo/` (12 primeiros caracteres são os que se imprimem)."""
    pasta = pasta_nucleo or os.path.join(_AQUI, "nucleo")
    h = hashlib.sha256()
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith(".py"):
            continue
        with open(os.path.join(pasta, nome), "rb") as f:
            dados = f.read().replace(b"\r\n", b"\n")
        h.update(nome.encode("utf-8") + b"\0" + dados + b"\0")
    return h.hexdigest()


def impressao_do_nucleo() -> str:
    """A impressão gravada no empacotamento, ou a calculada dos fontes."""
    gravada = os.path.join(_AQUI, ARQUIVO_IMPRESSAO)
    if os.path.exists(gravada):
        with open(gravada, encoding="utf-8") as f:
            valor = f.read().strip()
        if valor:
            return valor
    try:
        return calcular_impressao()
    except OSError:
        return "indisponivel"


def identificacao() -> str:
    """Linha que vai no memorial: 'Metálica 0.1.0 · núcleo 3f9a1c0b7e2d'."""
    return f"{NOME} {VERSAO} · núcleo {impressao_do_nucleo()[:12]}"
