# -*- coding: utf-8 -*-
"""Uma obra para outro usuário, por dentro do Metálica (21/10/2026, o usuário: "estou trabalhando no projeto da PRATI CD,
aparece somente para mim; ter uma opção de enviar o projeto para outro usuário por dentro do sistema sem precisar exportar
o pacote da obra e enviar para ele abrir").

O cartão do projeto › Enviar para… escolhe a pessoa (as licenças ativas); o programa monta o pacote da obra (o mesmo do
Exportar: projetos.exportar) e o sobe para a nuvem (o Worker metalica-celular, servicos/celular: o R2 e o banco das
licenças) em partes de até 40 MB; o Metálica da pessoa mostra "recebido de …" na tela inicial e, em Abrir, baixa as
partes, confere o SHA-1, importa como um projeto novo (importar_pacote: nunca por cima de outro) e marca recebido — a
nuvem apaga o pacote. Enviar é uma cópia: cada um segue com a sua. A pessoa é escolhida por um identificador opaco, nunca
pela chave da licença; o computador prova quem é com a licença assinada (licenca.token()).
"""
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from typing import Callable, Optional

import licenca
import versao
from nucleo.base import ErroDeDados

SERVICO = "https://metalica-celular.elieber-lucas.workers.dev"
PARTE = 40 * 1024 * 1024                    # o corpo de um pedido ao Worker tem limite (o Worker aceita até 45 MB)


class ErroCompartilhar(ErroDeDados):
    pass


def _servico() -> str:
    if not versao.CONGELADO and os.environ.get("METALICA_COMPARTILHAR"):
        return os.environ["METALICA_COMPARTILHAR"].rstrip("/")
    return SERVICO


def _pedir(metodo: str, rota: str, corpo=None, tipo: str = "application/json", timeout: float = 60.0, bruto: bool = False):
    tok = licenca.token()
    if not tok:
        raise ErroCompartilhar("este computador não tem licença do Metálica ativada — o envio de obras usa a licença")
    cab = {"Authorization": "Licenca " + tok, "User-Agent": "Metalica/" + versao.VERSAO}
    dados = None
    if corpo is not None:
        dados = corpo if isinstance(corpo, (bytes, bytearray)) else json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = tipo
    req = urllib.request.Request(_servico() + rota, data=dados, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("erro")
        except Exception:                                    # noqa: BLE001
            msg = None
        raise ErroCompartilhar(msg or "a nuvem recusou o pedido (%s)" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ErroCompartilhar("sem conexão com a nuvem do Metálica (%s) — confira a internet" % str(getattr(e, "reason", e))[:80])
    return b if bruto else json.loads(b.decode("utf-8") or "{}")


def pessoas() -> list:
    """[{id, pessoa, eu}] — as licenças ativas, para escolher a quem enviar ("eu": os meus outros computadores)."""
    return _pedir("GET", "/pc/pessoas").get("pessoas") or []


def _partes(caminho: str):
    """[(sha1, bytes, início)] do arquivo em partes de PARTE, e o SHA-1 do arquivo inteiro"""
    total, saida, ini = hashlib.sha1(), [], 0
    with open(caminho, "rb") as f:
        while True:
            b = f.read(PARTE)
            if not b:
                break
            total.update(b)
            saida.append((hashlib.sha1(b).hexdigest(), len(b), ini))
            ini += len(b)
    return saida, total.hexdigest()


def enviar(g, s: str, para: str, progresso: Callable = lambda *a, **k: None) -> dict:
    """Sobe o pacote da obra `s` e registra o envio para a pessoa `para` (o id de pessoas())."""
    if not para:
        raise ErroCompartilhar("escolha para quem enviar")
    progresso("empacotando a obra…", 0.02)
    r = g.exportar(s)
    pasta = os.path.dirname(r["caminho"])
    try:
        partes, sha1 = _partes(r["caminho"])
        faltam = set(_pedir("POST", "/pc/envio/faltam", {"sha1s": [p[0] for p in partes]}).get("faltam") or [])
        total = sum(p[1] for p in partes) or 1
        feito = 0
        with open(r["caminho"], "rb") as f:
            for i, (h, n, ini) in enumerate(partes, 1):
                if h in faltam:
                    progresso("enviando a obra (%d de %d)" % (i, len(partes)), 0.05 + 0.9 * feito / total)
                    f.seek(ini)
                    _pedir("PUT", "/pc/envio/parte/" + h, f.read(n), tipo="application/octet-stream", timeout=900)
                feito += n
        progresso("avisando a pessoa…", 0.97)
        p = g.ler(s)
        e = _pedir("POST", "/pc/envios", {"para": para, "nome": p.get("nome") or s, "slug": s, "sha1": sha1,
                                           "partes": [{"sha1": h, "bytes": n} for h, n, _i in partes]})
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return {"id": e.get("id"), "para": e.get("para"), "eu": e.get("eu"), "mb": round(sum(p[1] for p in partes) / 1048576, 1)}


def recebidos(incluir_deste: bool = False) -> list:
    """os envios pendentes para esta licença (os de outros computadores; `incluir_deste`: também os deste, nos testes)"""
    return _pedir("GET", "/pc/recebidos" + ("?incluir_deste=1" if incluir_deste else "")).get("recebidos") or []


def abrir(g, envio_id: int, progresso: Callable = lambda *a, **k: None, incluir_deste: bool = False) -> dict:
    """Baixa as partes do envio, confere, importa como projeto novo e marca recebido; devolve o resumo do projeto."""
    e = next((x for x in recebidos(incluir_deste) if int(x["id"]) == int(envio_id)), None)
    if not e:
        raise ErroCompartilhar("este envio não está mais na nuvem (já foi aberto em outro computador, recusado ou venceu)")
    pasta = tempfile.mkdtemp(prefix="metalica-recebido-")
    try:
        caminho = os.path.join(pasta, "obra.metalica.zip")
        total = sum(int(p["bytes"]) for p in e["partes"]) or 1
        feito, inteiro = 0, hashlib.sha1()
        with open(caminho, "wb") as f:
            for i, p in enumerate(e["partes"], 1):
                progresso("baixando a obra (%d de %d)" % (i, len(e["partes"])), 0.05 + 0.85 * feito / total)
                b = _pedir("GET", "/pc/recebidos/%d/parte/%s" % (int(e["id"]), p["sha1"]), timeout=900, bruto=True)
                if hashlib.sha1(b).hexdigest() != p["sha1"]:
                    raise ErroCompartilhar("uma parte da obra chegou diferente do que foi enviado — tente abrir de novo")
                f.write(b)
                inteiro.update(b)
                feito += len(b)
        if e.get("sha1") and inteiro.hexdigest() != e["sha1"]:
            raise ErroCompartilhar("o pacote da obra chegou incompleto — tente abrir de novo")
        progresso("abrindo a obra…", 0.93)
        resumo = g.importar_pacote(caminho, e.get("nome") or None)
        try:                                                  # o projeto já está aqui: marcar recebido limpa a nuvem
            _pedir("POST", "/pc/recebidos/%d/recebido" % int(e["id"]), {})
        except ErroCompartilhar:
            pass
        return dict(resumo, recebido_de=e.get("de"))
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def recusar(envio_id: int) -> dict:
    return _pedir("POST", "/pc/recebidos/%d/recusar" % int(envio_id), {})
