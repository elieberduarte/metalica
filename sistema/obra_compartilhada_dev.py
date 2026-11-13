# -*- coding: utf-8 -*-
"""As obras compartilhadas vistas pelo dono, no Metálica de desenvolvimento (13/11/2026, FERRAMENTA · OBRA COMPARTILHADA).

Decisões do usuário (13/11): só ele dá acesso (tela no dev, junto das Licenças); papéis Dono, Editor, Apontador e
Leitor por obra e por pessoa (pessoa = licença); piloto só o Posto. A seção "Obras compartilhadas" da tela Licenças
lê e grava as tabelas `obras` e `obra_acessos` direto no D1 (licencas_dev._sql, o login do wrangler desta máquina) —
o Worker não tem rota para dar acesso: quem garante é a nuvem, e só o dono mexe nela.

Extensão do desenvolvimento (app.py `_extensoes_dev`); o instalado não leva este módulo (empacotar/construir.py,
MODULOS_SO_DEV). Rotas:

* GET  /api/dev/compartilhadas              as obras compartilhadas, quem tem acesso, as pessoas e as obras deste dev
* GET  /api/dev/compartilhadas.js           o script da seção (web/compartilhadas_dev.js)
* POST /api/dev/compartilhadas/compartilhar {slug}                 a obra vira compartilhada (o obra_id fixo)
* POST /api/dev/compartilhadas/acesso       {obra_id, chave, papel} dá ou muda o papel; papel "" tira o acesso
"""
import datetime
import os
import sys

import obra_compartilhada as OC

_AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(_AQUI, "web", "compartilhadas_dev.js")


def _app():
    return sys.modules.get("app") or sys.modules["__main__"]


def _sql(sql, params=None):
    import licencas_dev
    return licencas_dev._sql(sql, params)


def _agora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _minha_chave() -> str:
    import licenca
    e = licenca.estado()
    if not e.get("chave"):
        raise ValueError("este computador não tem licença ativada — o dono da obra compartilhada é a licença do dev")
    return e["chave"]


def painel(gerente) -> dict:
    """{obras: [{obra_id, nome, criada, apontamentos, ultimo, acessos: [{chave, pessoa, papel, desde, ultima_vez}],
    slug}], pessoas: [{chave, pessoa}], locais: [{slug, nome, obra_id}], sem_tabelas}"""
    import licencas_dev
    try:
        obras = _sql("SELECT * FROM obras WHERE ativa = 1 ORDER BY nome")
    except licencas_dev.ErroLicencas as e:
        if "no such table" in str(e):
            return {"sem_tabelas": True, "obras": [], "pessoas": [], "locais": []}
        raise
    acessos = _sql("SELECT a.*, l.pessoa FROM obra_acessos a LEFT JOIN licencas l ON l.chave = a.chave ORDER BY a.desde")
    contas = {c["obra_id"]: c for c in _sql("SELECT obra_id, COUNT(*) AS n, MAX(recebido) AS ultimo FROM apontamentos GROUP BY obra_id")}
    pessoas = _sql("SELECT chave, pessoa FROM licencas WHERE ativa = 1 ORDER BY pessoa")
    locais = []
    for p in gerente.listar():
        slug = p.get("slug") or p.get("id")
        if not slug:
            continue
        try:
            c = OC.info(gerente._existente(slug))
        except Exception:                                   # noqa: BLE001
            c = None
        locais.append({"slug": slug, "nome": p.get("nome") or slug, "obra_id": (c or {}).get("obra_id")})
    por_id = {x["obra_id"]: x["slug"] for x in locais if x["obra_id"]}
    for o in obras:
        o["acessos"] = [a for a in acessos if a["obra_id"] == o["obra_id"]]
        o["apontamentos"] = (contas.get(o["obra_id"]) or {}).get("n") or 0
        o["ultimo"] = (contas.get(o["obra_id"]) or {}).get("ultimo") or ""
        o["slug"] = por_id.get(o["obra_id"])
    return {"obras": obras, "pessoas": pessoas, "locais": locais}


def compartilhar(gerente, slug: str) -> dict:
    """a obra deste dev vira compartilhada: o obra_id fixo no projeto.json, a obra e o dono na nuvem, e os
    apontamentos que já existem entram na fila para subir"""
    pasta = gerente._existente(slug)
    p = gerente.ler(slug)
    c = OC.info(pasta)
    chave = _minha_chave()
    if not c:
        c = {"obra_id": OC.novo_obra_id(), "nome": p.get("nome") or slug, "desde": _agora()}
        gerente._atualizar(slug, compartilhada=c)
    t = _agora()
    _sql("INSERT OR IGNORE INTO obras (obra_id, nome, dono_chave, criada, ativa) VALUES (?, ?, ?, ?, 1)",
         [c["obra_id"], c.get("nome") or slug, chave, t])
    _sql("UPDATE obras SET ativa = 1 WHERE obra_id = ?", [c["obra_id"]])
    _sql("INSERT OR IGNORE INTO obra_acessos (obra_id, chave, papel, desde) VALUES (?, ?, 'dono', ?)", [c["obra_id"], chave, t])
    _sql("INSERT INTO eventos (quando, chave, maquina, tipo, detalhe, pais) VALUES (?, ?, '', 'obra compartilhada', ?, '')",
         [t, chave, "%s (%s)" % (c.get("nome") or slug, c["obra_id"][:8])])
    OC.iniciar(pasta)
    r = OC.sincronizar(pasta)
    return {"ok": True, "obra_id": c["obra_id"], "sincronizar": r}


def acesso(obra_id: str, chave: str, papel: str) -> dict:
    """dá ou muda o papel de uma pessoa; papel vazio tira o acesso. O dono não muda por aqui."""
    if not OC._OBRA_ID.match(str(obra_id or "")):
        raise ValueError("obra inválida")
    papel = str(papel or "")
    if papel and papel not in ("editor", "apontador", "leitor"):
        raise ValueError("papel inválido: %r (editor, apontador ou leitor)" % papel)
    o = _sql("SELECT dono_chave FROM obras WHERE obra_id = ?", [obra_id])
    if not o:
        raise ValueError("obra compartilhada não encontrada")
    if o[0]["dono_chave"] == chave:
        raise ValueError("o dono da obra não muda de papel")
    if not _sql("SELECT chave FROM licencas WHERE chave = ?", [chave]):
        raise ValueError("licença não encontrada")
    t = _agora()
    if papel:
        _sql("INSERT INTO obra_acessos (obra_id, chave, papel, desde) VALUES (?, ?, ?, ?) "
             "ON CONFLICT(obra_id, chave) DO UPDATE SET papel = excluded.papel", [obra_id, chave, papel, t])
    else:
        _sql("DELETE FROM obra_acessos WHERE obra_id = ? AND chave = ?", [obra_id, chave])
    _sql("INSERT INTO eventos (quando, chave, maquina, tipo, detalhe, pais) VALUES (?, ?, '', 'acesso à obra', ?, '')",
         [t, chave, "%s → %s" % (obra_id[:8], papel or "sem acesso")])
    return {"ok": True}


# ------------------------------------------------------------------ as rotas (extensão do dev)
def _responder(h, fazer):
    import licencas_dev
    try:
        h._json(fazer())
    except (licencas_dev.ErroLicencas, OC.ErroObra, ValueError) as e:
        h._json({"erro": str(e)}, 502 if isinstance(e, licencas_dev.ErroLicencas) else 400)


def rota_get(h, rota: str) -> bool:
    if rota == "/api/dev/compartilhadas":
        _responder(h, lambda: painel(_app()._gerente()))
        return True
    if rota == "/api/dev/compartilhadas.js":
        corpo = open(SCRIPT, "rb").read()
        h.send_response(200)
        h.send_header("Content-Type", "text/javascript; charset=utf-8")
        h.send_header("Content-Length", str(len(corpo)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(corpo)
        return True
    return False


def rota_post(h, rota: str, corpo) -> bool:
    corpo = corpo if isinstance(corpo, dict) else {}
    if rota == "/api/dev/compartilhadas/compartilhar":
        _responder(h, lambda: compartilhar(_app()._gerente(), str(corpo.get("slug") or "")))
        return True
    if rota == "/api/dev/compartilhadas/acesso":
        _responder(h, lambda: acesso(str(corpo.get("obra_id") or ""), str(corpo.get("chave") or ""), str(corpo.get("papel") or "")))
        return True
    return False
