# -*- coding: utf-8 -*-
"""As rotas do controle de produção. No desenvolvimento valem para todas as obras; no programa instalado (13/11, FERRAMENTA ·
OBRA COMPARTILHADA, item 3 da 1a: o Fernando aponta no Posto pelo instalado) só para a obra compartilhada — a obra sem o
obra_id não tem a tela Controle na barra de cima e as rotas recusam; o que o ERP lê fica só no dev. Carregado pelo
`_extensoes_gerais` do app.py (o mesmo no dev e no instalado).

* GET  /controle-producao?projeto=          a tela do controle (web/producao/controle.html); era uma aba da lista de
                                            materiais até 12/11, o usuário pediu no menu Produção do topo
* GET  /api/projetos/<slug>/etapas          a barra de cima, com a Produção abrindo a lista das duas telas (etapas.js)
* GET  /api/producao/controle.js            o script da tela (web/producao/controle.js)
* GET  /api/producao/controle?projeto=      a situação da obra (controle.situacao)
* POST /api/producao/apontar                {projeto, item, etapa, quantidade, data?, obs?}
* POST /api/producao/estornar               {projeto, evento, obs?} — qualquer apontamento, não só os 30 da tela
* GET  /api/producao/historico?projeto=&item=  todos os apontamentos do item, para estornar dali (controle.historico)
* POST /api/producao/apontar-varios         {projeto, itens: [ids], etapa, data?, obs?} — tudo o que falta na etapa em cada
                                            um (escolhidos na lista ou no 3D); devolve {eventos, pulados}
* GET  /api/producao/erp?projeto=&desde=    o que o ERP lê (só leitura; controle.para_erp)
* GET  /api/producao/controle3d.js          o 3D ao lado da lista (web/producao/controle3d.js): clicar destaca, cor = situação
* GET  /api/producao/cores                  as cores do 3D (não feita, produzida, pintada, destaque) e o padrão
* POST /api/producao/cores                  {cores: {...}} grava para todas as obras; {cores: {}} volta ao padrão

"Quem" é sempre a pessoa da licença desta máquina (decisão do usuário, 12/11: só a engenharia aponta).

Obra compartilhada (13/11, FERRAMENTA · OBRA COMPARTILHADA; obra_compartilhada.py): quando o projeto.json tem o obra_id,
o controle sincroniza com a nuvem antes de mostrar e antes de apontar (traz o que os outros apontaram), põe na fila o que
foi apontado ou estornado aqui e sincroniza de novo (sobe). Sem internet tudo segue local e a fila espera. O papel vem da
nuvem: o Leitor não aponta nem estorna (a nuvem recusa de qualquer jeito; aqui a mensagem sai antes).
"""
import os
import sys
from urllib.parse import parse_qs, quote, urlparse

import obra_compartilhada
from producao import controle

_AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(_AQUI), "web")
SCRIPT = os.path.join(WEB, "producao", "controle.js")
SCRIPT_3D = os.path.join(WEB, "producao", "controle3d.js")
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


def _so_compartilhadas() -> bool:
    """o programa instalado: o Controle só para obra compartilhada (o dev, e os testes com o app de mentira, todas)"""
    return not getattr(_app(), "DEV", True)


def _exigir_compartilhada(pasta: str):
    if _so_compartilhadas() and not obra_compartilhada.info(pasta):
        raise _erro("no programa instalado o Controle de produção é só para obra compartilhada")


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


#: o tempo de cada pedido à nuvem na obra compartilhada: sem internet a tela não pode ficar presa
TEMPO_NUVEM = 4.0


def _sincronizar(pasta: str):
    """a obra compartilhada com a nuvem (None se não é compartilhada); nunca levanta erro de rede"""
    try:
        return obra_compartilhada.sincronizar(pasta, timeout=TEMPO_NUVEM, trava=controle._TRAVA)
    except Exception as e:                              # noqa: BLE001 — o controle local continua
        est = obra_compartilhada.estado(pasta)
        if est is not None:
            est["erro"] = "falha ao sincronizar: %s" % e
        return est


def _sem_papel(erro: str) -> str:
    """a recusa do Apontar quando o papel nunca veio da nuvem, em palavras (14/11): o texto do Windows/urllib
    ("[WinError 10061] Nenhuma conexão pôde ser feita…", obra_compartilhada._pedir) vai para o log, não para a tela"""
    e = (erro or "").strip()
    if e:
        sys.stderr.write("[controle] obra compartilhada sem o papel: %s\n" % e)
    inicio = "não deu para saber o seu papel nesta obra compartilhada"
    if not e or e.startswith(("sem conexão com a nuvem", "a nuvem recusou o pedido", "falha ao sincronizar")):
        motivo = ("a nuvem do Metálica não respondeu a tempo" if "timed out" in e
                  else "sem internet" if e.startswith("sem conexão com a nuvem") else "a nuvem do Metálica não respondeu")
        return "%s (%s) — conecte à internet e abra o Controle de novo" % (inicio, motivo)
    # os recados da própria nuvem já vêm em palavras (a licença bloqueada, sem acesso a esta obra, computador desligado…)
    return "%s: %s" % (inicio, e)


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


def _script(h, caminho=SCRIPT):
    _enviar(h, open(caminho, "rb").read(), "text/javascript; charset=utf-8")


def _raiz() -> str:
    """a pasta dos projetos (onde ficam as cores do 3D, comuns a todas as obras)"""
    return _app().PROJETOS


def _cores(h):
    h._json({"cores": controle.ler_cores(_raiz()), "padrao": controle.CORES_PADRAO})


def rota_get(h, rota: str) -> bool:
    if rota == "/controle-producao":
        _pagina(h)
        return True
    if rota.startswith("/api/projetos/") and rota.endswith("/etapas"):
        partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
        if len(partes) == 2:
            if _so_compartilhadas():                    # no instalado, a tela Controle só na obra compartilhada
                try:
                    if not obra_compartilhada.info(_pasta(partes[0])):
                        return False                    # o app responde as etapas de sempre
                except Exception:                       # noqa: BLE001 — projeto que não existe: o app responde o erro
                    return False
            _etapas(h, partes[0])
            return True
    if rota == "/api/producao/controle.js":
        _script(h)
        return True
    if rota == "/api/producao/controle3d.js":
        _script(h, SCRIPT_3D)
        return True
    if rota == "/api/producao/cores":
        _cores(h)
        return True
    if rota == "/api/producao/controle":
        s = _consulta(h).get("projeto", "")
        pasta = _pasta(s)
        _exigir_compartilhada(pasta)
        try:
            lista = controle.ler_lista(pasta)
        except controle.ErroControle as e:
            h._json({"sem_lista": True, "erro": str(e)})
            return True
        nuvem = _sincronizar(pasta)
        r = controle.situacao(lista, controle.ler_eventos(pasta), controle.ler_nomes(pasta))
        r["quem"] = _quem()
        r["nuvem"] = nuvem                              # None: obra só deste computador
        r["obra"] = _nome_da_obra(s, lista)
        r["tem_3d"] = os.path.isfile(os.path.join(pasta, "modelo.json"))      # sem modelo, a tela nem abre o 3D ao lado
        h._json(r)
        return True
    if rota == "/api/producao/historico":
        q = _consulta(h)
        pasta = _pasta(q.get("projeto", ""))
        _exigir_compartilhada(pasta)
        try:
            evs = controle.historico(controle.ler_lista(pasta), controle.ler_eventos(pasta), q.get("item", ""),
                                     controle.ler_nomes(pasta))
        except controle.ErroControle as e:
            raise _erro(str(e))
        h._json({"item": q.get("item", ""), "eventos": evs})
        return True
    if rota == "/api/producao/erp" and not _so_compartilhadas():       # o ERP: só no dev
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
    if rota == "/api/producao/cores":
        try:
            controle.gravar_cores(_raiz(), (corpo if isinstance(corpo, dict) else {}).get("cores") or {})
        except controle.ErroControle as e:
            raise _erro(str(e))
        _cores(h)
        return True
    if rota not in ("/api/producao/apontar", "/api/producao/estornar", "/api/producao/apontar-varios"):
        return False
    corpo = corpo if isinstance(corpo, dict) else {}
    pasta = _pasta(str(corpo.get("projeto") or ""))
    _exigir_compartilhada(pasta)
    nuvem = _sincronizar(pasta)
    if nuvem is not None and nuvem.get("papel") and not nuvem.get("pode_apontar"):
        raise _erro("o seu papel nesta obra compartilhada é %s: só vê, não aponta" % (nuvem.get("papel_nome") or nuvem["papel"]))
    if nuvem is not None and not nuvem.get("papel") and _so_compartilhadas():
        # no instalado, o papel vem da nuvem: sem ele (nunca sincronizou, ou a licença perdeu o acesso) não aponta; depois
        # de uma vez com internet ele fica guardado (nuvem.json) e sem internet o apontamento segue (decisão 9)
        raise _erro(_sem_papel(nuvem.get("erro")))
    try:
        if rota == "/api/producao/apontar":
            lista = controle.ler_lista(pasta)
            ev = controle.apontar(pasta, lista, str(corpo.get("item") or ""), str(corpo.get("etapa") or ""),
                                  corpo.get("quantidade"), _quem(), data=corpo.get("data"), obs=corpo.get("obs") or "",
                                  nomes=controle.ler_nomes(pasta))
        elif rota == "/api/producao/apontar-varios":
            lista = controle.ler_lista(pasta)
            ids = corpo.get("itens")
            r = controle.apontar_varios(pasta, lista, ids if isinstance(ids, list) else [], str(corpo.get("etapa") or ""),
                                        _quem(), data=corpo.get("data"), obs=corpo.get("obs") or "",
                                        nomes=controle.ler_nomes(pasta))
        else:
            ev = controle.estornar(pasta, str(corpo.get("evento") or ""), _quem(), obs=corpo.get("obs") or "")
    except controle.ErroControle as e:
        raise _erro(str(e))
    novos = r["eventos"] if rota == "/api/producao/apontar-varios" else [ev]
    if nuvem is not None:
        # a tesoura montada grava uma linha por parte ("junto"), e o estorno dela desfaz o lote inteiro
        for i in [x["id"] for x in novos] + [j for x in novos for j in x.get("junto") or []]:
            obra_compartilhada.na_fila(pasta, i)
        nuvem = _sincronizar(pasta)
    if rota == "/api/producao/apontar-varios":
        h._json({"ok": True, "eventos": novos, "pulados": r["pulados"], "nuvem": nuvem})
    else:
        h._json({"ok": True, "evento": ev, "nuvem": nuvem})
    return True
