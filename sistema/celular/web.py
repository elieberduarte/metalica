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
* GET  /api/dev/extensoes.js      o script da tela inicial: o do pré-moldado (se houver) e o botão do celular
"""
import os
import sys
import threading

from celular.servidor import Celular, pasta_de_trabalho, WEB

_UNICO = None
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


def iniciar():
    """Na subida do programa: se o acesso ficou ligado da última vez, liga de novo."""
    try:
        c = celular()
        if c.configuracao().get("ligado"):
            c.ligar()
    except Exception:                    # noqa: BLE001 — porta ocupada etc.: a tela mostra ao abrir
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
    if rota == "/api/dev/extensoes.js":
        partes = []
        pm = os.path.join(WEB, "premoldado", "dev_inicio.js")
        if os.path.isfile(pm):
            with open(pm, encoding="utf-8") as f:
                partes.append(f.read())
        with open(os.path.join(WEB, "acesso-celular-inicio.js"), encoding="utf-8") as f:
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
    if acao == "renomear":
        h._json(c.renomear(str(corpo.get("id") or ""), str(corpo.get("nome") or "")))
        return True
    return False


iniciar()
