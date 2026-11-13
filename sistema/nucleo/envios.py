# -*- coding: utf-8 -*-
"""O arquivo enviado como ele é (o envio binário do servidor, app._corpo_binario) — onde ele fica e quem pode usá-lo.

O servidor grava o arquivo recebido em <pasta de dados>/.envios e passa à rota {"arquivo_local": <caminho>, "nome"}. As
rotas movem, leem e apagam esse arquivo. O caminho só pode ser um arquivo dessa pasta: até 13/11 o campo vindo num JSON
comum também valia, e a rota do vídeo das Cenas apagava qualquer arquivo do disco cujo caminho viesse nele (D12, agente
usuario-desastrado; o mesmo para mover para dentro da obra nas fotos, PDF, imagem do terreno e IFC)."""
import os

from nucleo.base import ErroDeDados

PASTA = ".envios"
CAMPO = "arquivo_local"


def pasta(raiz: str) -> str:
    """A pasta dos envios dentro da pasta de dados."""
    return os.path.join(raiz, PASTA)


def dentro(raiz: str, caminho: str) -> bool:
    """O caminho é um arquivo da pasta de envios de `raiz` (resolvendo `..`, atalhos e maiúsculas do Windows)."""
    if not caminho or not raiz:
        return False
    base = os.path.normcase(os.path.realpath(pasta(raiz)))
    alvo = os.path.normcase(os.path.realpath(str(caminho)))
    try:
        return os.path.commonpath([base, alvo]) == base and alvo != base
    except ValueError:                                   # outro disco no Windows
        return False


def arquivo(raiz: str, corpo: dict, erro=ErroDeDados):
    """O caminho do arquivo enviado, ou None quando o pedido não trouxe arquivo. Caminho fora da pasta de envios: `erro`,
    sem tocar no arquivo (nem ler, nem mover, nem apagar)."""
    caminho = (corpo or {}).get(CAMPO)
    if not caminho:
        return None
    if not dentro(raiz, caminho):
        raise erro("o arquivo recebido não veio pelo envio do programa; nada foi lido nem apagado.")
    return str(caminho)
