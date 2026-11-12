# -*- coding: utf-8 -*-
"""As rotas do controle de produção (extensão do modo desenvolvimento: app.py `_extensoes_dev`; o programa instalado
não tem nada disto até o usuário aprovar).

* GET  /controle-producao?projeto=          a tela do controle (web/producao/controle.html); era uma aba da lista de
                                            materiais até 12/11, o usuário pediu no menu Produção do topo
* GET  /api/projetos/<slug>/etapas          a barra de cima, com a Produção abrindo a lista das duas telas (etapas.js)
* GET  /api/producao/controle.js            o script da tela (web/producao/controle.js)
* GET  /api/producao/controle?projeto=      a situação da obra (controle.situacao)
* POST /api/producao/apontar                {projeto, item, etapa, quantidade, data?, obs?}
* POST /api/producao/estornar               {projeto, evento, obs?}
* GET  /api/producao/erp?projeto=&desde=    o que o ERP lê (só leitura; controle.para_erp)

"Quem" é sempre a pessoa da licença desta máquina (decisão do usuário, 12/11: só a engenharia aponta).
"""
import os
import sys
from urllib.parse import parse_qs, quote, urlparse

from producao import controle

_AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(_AQUI), "web")
SCRIPT = os.path.join(WEB, "producao", "controle.js")
PAGINA = os.path.join(WEB, "producao", "controle.html")


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
    """o nome do projeto (projeto.json) — a lista guarda o nome do dia em que foi levantada: 12/11 o usuário trocou o
    nome do Posto e o Controle seguia com o "- V2" da lista de 09/11. Sem nome no projeto, o da lista; sem os dois, o slug."""
    try:
        nome = (_app()._gerente().ler(slug) or {}).get("nome")
    except Exception:                                   # noqa: BLE001 — sem o projeto, o da lista
        nome = None
    return nome or (lista.get("projeto") or {}).get("nome") or slug


def _consulta(h) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(h.path).query).items()}


def _enviar(h, corpo: bytes, tipo: str):
    h.send_response(200)
    h.send_header("Content-Type", tipo)
    h.send_header("Content-Length", str(len(corpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(corpo)


def _pagina(h):
    _enviar(h, open(PAGINA, "rb").read(), "text/html; charset=utf-8")


def telas_da_producao(slug: str) -> list:
    """as páginas da Produção na barra de cima (o clique na Produção abre esta lista)"""
    s = quote(slug)
    return [{"texto": "Lista de materiais", "url": "/materiais?projeto=%s#geral" % s,
             "dica": "peças, perfis, plano de corte, romaneio e resumos"},
            {"texto": "Controle de produção", "url": "/controle-producao?projeto=%s" % s,
             "dica": "apontar o que a fábrica fez: produção e pintura"}]


def _etapas(h, slug: str):
    r = _app().etapas_do_projeto(slug)
    for e in r.get("etapas") or []:
        if e.get("chave") == "producao":
            e["telas"] = telas_da_producao(slug)
            e["itens"] = list(e.get("itens") or []) + [{"texto": "Controle de produção", "link": e["telas"][1]["url"]}]
    h._json(r)


def _script(h):
    _enviar(h, open(SCRIPT, "rb").read(), "text/javascript; charset=utf-8")


def rota_get(h, rota: str) -> bool:
    if rota == "/controle-producao":
        _pagina(h)
        return True
    if rota.startswith("/api/projetos/") and rota.endswith("/etapas"):
        partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
        if len(partes) == 2:
            _etapas(h, partes[0])
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
        r["obra"] = _nome_da_obra(s, lista)
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
