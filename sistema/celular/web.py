# -*- coding: utf-8 -*-
"""O acesso pelo celular nas telas do computador (extensão do modo desenvolvimento, como o
pré-moldado: app.py `_extensoes_dev`). Enquanto a Fase 1 não fecha, o programa instalado não tem
nada disto (empacotar/construir.py deixa de fora).

Rotas, todas no servidor do programa (só o próprio computador, com a proteção de sempre):

* GET  /acesso-celular            a tela: ligar/desligar, QR code, aparelhos pareados
* GET  /api/celular/estado        ligado, endereços, aparelhos, pacotes em preparo
* POST /api/celular/ligar         {"ligado": true|false}
* POST /api/celular/codigo        um código novo para o QR (5 minutos, uso único)
* POST /api/celular/remover       {"id": ...}  o aparelho deixa de entrar na hora
* POST /api/celular/renomear      {"id": ..., "nome": ...}
* GET  /api/celular/obras         as obras que podem ir para o celular e se cada uma está ligada (o botão do cartão)
* POST /api/celular/obra          {"slug": ..., "celular": true|false}  liga ou desliga a obra no celular
* POST /api/celular/https         {"nome": "metalica.dominio.com.br", "token": "..."}  HTTPS (cópia para a obra)
* POST /api/celular/https/remover volta ao http
* GET  /api/celular/nuvem         de qualquer lugar: o envio para a nuvem (celular/nuvem.py) — ligado, último envio, andamento
* GET  /api/celular/nuvem/aparelhos  os celulares da licença deste PC, lidos da nuvem
* POST /api/celular/nuvem/ligar   {"ligada": true|false}
* POST /api/celular/nuvem/enviar  envia agora (em segundo plano)
* POST /api/celular/nuvem/codigo  o QR code da nuvem (o celular fica na licença deste PC)
* GET  /api/dev/extensoes.js      o script da tela inicial: o do pré-moldado (se houver) e o botão do celular
"""
import os
import sys
import threading

from celular.servidor import Celular, pasta_de_trabalho, WEB
from celular.nuvem import Nuvem, ErroNuvem

_UNICO = None
_NUVEM = None
_TRAVA = threading.Lock()


def _app():
    return sys.modules.get("app") or sys.modules["__main__"]


def celular() -> Celular:
    global _UNICO
    with _TRAVA:
        if _UNICO is None:
            app = _app()
            teste = "--dados" in sys.argv or bool(os.environ.get("METALICA_DADOS"))
            _UNICO = Celular(app.PROJETOS, pasta_de_trabalho(app.PROJETOS, teste))
        return _UNICO


def nuvem() -> Nuvem:
    global _NUVEM
    c = celular()
    with _TRAVA:
        if _NUVEM is None:
            _NUVEM = Nuvem(c)
        return _NUVEM


def iniciar():
    """Na subida do programa: se o acesso ficou ligado da última vez, liga de novo; o envio para a nuvem também."""
    try:
        c = celular()
        if c.configuracao().get("ligado"):
            c.ligar()
    except Exception:                    # noqa: BLE001 — porta ocupada etc.: a tela mostra ao abrir
        pass
    try:
        if nuvem().ligada:
            nuvem().iniciar()
    except Exception:                    # noqa: BLE001
        pass


def _erro_de_dados(msg):
    from nucleo.base import ErroDeDados
    return ErroDeDados(msg)


def rota_get(h, rota: str) -> bool:
    if rota == "/acesso-celular":
        h._arquivo(os.path.join(WEB, "acesso-celular.html"), WEB)
        return True
    if rota == "/api/celular/estado":
        h._json(celular().estado())
        return True
    if rota == "/api/celular/nuvem":
        h._json(nuvem().estado())
        return True
    if rota == "/api/celular/nuvem/aparelhos":
        try:
            h._json(nuvem().na_nuvem())
        except ErroNuvem as e:
            raise _erro_de_dados(str(e))
        return True
    if rota == "/api/celular/obras":
        h._json({"obras": celular().obras()})
        return True
    if rota == "/api/dev/extensoes.js":
        partes = []
        pm = os.path.join(WEB, "premoldado", "dev_inicio.js")
        if os.path.isfile(pm):
            with open(pm, encoding="utf-8") as f:
                partes.append(f.read())
        with open(os.path.join(WEB, "acesso-celular-inicio.js"), encoding="utf-8") as f:
            partes.append(f.read())
        pd = os.path.join(WEB, "painel_dev", "inicio.js")          # o botão do Painel DEV (painel_dev/web.py)
        if os.path.isfile(pd):
            with open(pd, encoding="utf-8") as f:
                partes.append(f.read())
        corpo = "\n;\n".join(partes).encode("utf-8")
        h.send_response(200)
        h.send_header("Content-Type", "text/javascript; charset=utf-8")
        h.send_header("Content-Length", str(len(corpo)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(corpo)
        return True
    return False


def rota_post(h, rota: str, corpo: dict) -> bool:
    if not rota.startswith("/api/celular/"):
        return False
    c = celular()
    acao = rota[len("/api/celular/"):]
    corpo = corpo if isinstance(corpo, dict) else {}
    if acao == "ligar":
        if corpo.get("ligado"):
            try:
                h._json(c.ligar())
            except OSError as e:
                raise _erro_de_dados("não foi possível abrir a porta %d na rede (%s): outro programa a usa?" % (c.porta, e))
        else:
            h._json(c.desligar())
        return True
    if acao == "codigo":
        if not c.ligado:
            raise _erro_de_dados("ligue o acesso pelo celular primeiro")
        h._json(c.novo_codigo())
        return True
    if acao == "remover":
        h._json(c.remover(str(corpo.get("id") or "")))
        return True
    if acao == "https":
        try:
            h._json(c.configurar_https(str(corpo.get("nome") or ""), str(corpo.get("token") or "")))
        except ValueError as e:
            raise _erro_de_dados(str(e))
        return True
    if acao == "https/remover":
        h._json(c.remover_https())
        return True
    if acao.startswith("nuvem/"):
        n = nuvem()
        if acao == "nuvem/ligar":
            h._json(n.ligar(bool(corpo.get("ligada"))))
        elif acao == "nuvem/enviar":
            h._json(n.enviar_ja())
        elif acao == "nuvem/codigo":
            try:
                h._json(n.novo_codigo())
            except ErroNuvem as e:
                raise _erro_de_dados(str(e))
        else:
            return False
        return True
    if acao == "obra":
        try:
            h._json(c.mostrar(str(corpo.get("slug") or ""), bool(corpo.get("celular"))))
        except ValueError as e:
            raise _erro_de_dados(str(e))
        return True
    if acao == "renomear":
        h._json(c.renomear(str(corpo.get("id") or ""), str(corpo.get("nome") or "")))
        return True
    return False


iniciar()
