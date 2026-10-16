# -*- coding: utf-8 -*-
"""O Painel DEV nas telas (extensão do modo desenvolvimento, como o celular e o pré-moldado: app.py
`_extensoes_dev`; o programa instalado não leva nada disto — empacotar/construir.py).

* GET /painel-dev                      a tela
* GET /api/dev/chats?horas=24          os chats ativos nas últimas horas, os alertas, a linha do tempo e as frentes
* GET /api/dev/chats/mensagens?id=…    as mensagens trocadas por um chat com os outros, inteiras
"""
import os
from urllib.parse import parse_qs, urlparse

from painel_dev import chats

WEB = os.path.join(chats.SISTEMA, "web")


def _consulta(h) -> dict:
    return {k: v[-1] for k, v in parse_qs(urlparse(h.path).query).items()}


def rota_get(h, rota: str) -> bool:
    if rota == "/painel-dev":
        h._arquivo(os.path.join(WEB, "painel_dev", "painel.html"), WEB)
        return True
    if rota == "/api/dev/chats":
        try:
            horas = min(max(float(_consulta(h).get("horas") or 24), 1.0), 24 * 14)
        except ValueError:
            horas = 24.0
        h._json(chats.painel(horas))
        return True
    if rota == "/api/dev/chats/mensagens":
        sid = _consulta(h).get("id") or ""
        s = next((x for x in chats._SESSOES.values() if x.id == sid), None)
        if s is None:
            h._json({"enviadas": [], "recebidas": [], "agentes": []})
        else:
            h._json({"enviadas": s.enviadas[-60:], "recebidas": s.recebidas[-60:],
                     "agentes": sorted(s.agentes.values(), key=lambda a: -(a.get("inicio") or 0))})
        return True
    return False


def rota_post(h, rota: str, corpo: dict) -> bool:
    return False
