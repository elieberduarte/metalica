# -*- coding: utf-8 -*-
"""As rotas do controle de produção (extensão do modo desenvolvimento: app.py `_extensoes_dev`; o programa instalado
não tem nada disto até o usuário aprovar).

* GET  /materiais, /lista-de-materiais      a mesma tela da lista, com o script da aba Controle antes do materiais.js
* GET  /api/producao/controle.js            o script da aba (web/producao/controle.js)
* GET  /api/producao/controle?projeto=      a situação da obra (controle.situacao)
* POST /api/producao/apontar                {projeto, item, etapa, quantidade, data?, obs?}
* POST /api/producao/estornar               {projeto, evento, obs?}
* GET  /api/producao/erp?projeto=&desde=    o que o ERP lê (só leitura; controle.para_erp)

"Quem" é sempre a pessoa da licença desta máquina (decisão do usuário, 12/11: só a engenharia aponta).
"""
import os
import sys
from urllib.parse import parse_qs, urlparse

from producao import controle

_AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(_AQUI), "web")
SCRIPT = os.path.join(WEB, "producao", "controle.js")


def _app():
    return sys.modules.get("app") or sys.modules["__main__"]


def _erro(msg):
    from nucleo.base import ErroDeDados
    return ErroDeDados(msg)


def _pasta(slug: str) -> str:
    if not slug:
        raise _erro("falta o projeto")
    return _app()._gerente()._existente(slug)


def _quem() -> str:
    try:
        import licenca
        return licenca.estado().get("pessoa") or "sem licença"
    except Exception:                                   # noqa: BLE001 — sem a licença o apontamento continua
        return "sem licença"


def _nome_da_obra(slug: str, lista: dict) -> str:
    return ((lista.get("projeto") or {}).get("nome")) or slug


def _consulta(h) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(h.path).query).items()}


def _pagina_da_lista(h):
    html = open(os.path.join(WEB, "materiais.html"), encoding="utf-8").read()
    marca = '<script src="/materiais.js"></script>'
    if marca in html:
        html = html.replace(marca, '<script src="/api/producao/controle.js"></script>\n' + marca, 1)
    corpo = html.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(corpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(corpo)


def _script(h):
    corpo = open(SCRIPT, "rb").read()
    h.send_response(200)
    h.send_header("Content-Type", "text/javascript; charset=utf-8")
    h.send_header("Content-Length", str(len(corpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(corpo)


def rota_get(h, rota: str) -> bool:
    if rota in ("/materiais", "/lista-de-materiais"):
        _pagina_da_lista(h)
        return True
    if rota == "/api/producao/controle.js":
        _script(h)
        return True
    if rota == "/api/producao/controle":
        s = _consulta(h).get("projeto", "")
        pasta = _pasta(s)
        try:
            lista = controle.ler_lista(pasta)
        except controle.ErroControle as e:
            h._json({"sem_lista": True, "erro": str(e)})
            return True
        r = controle.situacao(lista, controle.ler_eventos(pasta), controle.ler_nomes(pasta))
        r["quem"] = _quem()
        h._json(r)
        return True
    if rota == "/api/producao/erp":
        q = _consulta(h)
        s = q.get("projeto", "")
        pasta = _pasta(s)
        try:
            lista = controle.ler_lista(pasta)
        except controle.ErroControle as e:
            raise _erro(str(e))
        h._json(controle.para_erp(s, _nome_da_obra(s, lista), lista, controle.ler_eventos(pasta),
                                  controle.ler_nomes(pasta), desde=q.get("desde")))
        return True
    return False


def rota_post(h, rota: str, corpo: dict) -> bool:
    if rota not in ("/api/producao/apontar", "/api/producao/estornar"):
        return False
    corpo = corpo if isinstance(corpo, dict) else {}
    pasta = _pasta(str(corpo.get("projeto") or ""))
    try:
        if rota == "/api/producao/apontar":
            lista = controle.ler_lista(pasta)
            ev = controle.apontar(pasta, lista, str(corpo.get("item") or ""), str(corpo.get("etapa") or ""),
                                  corpo.get("quantidade"), _quem(), data=corpo.get("data"), obs=corpo.get("obs") or "",
                                  nomes=controle.ler_nomes(pasta))
        else:
            ev = controle.estornar(pasta, str(corpo.get("evento") or ""), _quem(), obs=corpo.get("obs") or "")
    except controle.ErroControle as e:
        raise _erro(str(e))
    h._json({"ok": True, "evento": ev})
    return True
