# -*- coding: utf-8 -*-
"""As licenças vistas de dentro do Metálica de desenvolvimento (11/10/2026, pedido do usuário: "uma tela de acesso rápido
às licenças dentro da versão dev").

A mesma coisa que a tela das licenças na Cloudflare (servicos/licencas/src/admin.js): quem tem licença, os computadores
de cada uma com a versão e o último contato, criar chave, bloquear, liberar a vaga — lendo e gravando direto no banco D1
`metalica-licencas` pela API da Cloudflare, com o login do wrangler desta máquina (o token OAuth dele vale 1 h; vencido, o
próprio wrangler o renova). Só no desenvolvimento: o instalado não leva este módulo (empacotar/construir.py,
MODULOS_SO_DEV) nem responde às rotas (app.py, LICENCAS_DEV).
"""
import datetime
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request

CONTA = "97e42554f601fee34702ba83e8b2dd7d"
BANCO = "cb870249-814d-4c2a-a610-490539a21e65"
TELA = "https://metalica-licencas-admin.elieber-lucas.workers.dev"
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ErroLicencas(Exception):
    pass


def _ferramentas() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Metalica-ferramentas", "cloudflare")


def _config_wrangler() -> str:
    return os.path.join(os.environ.get("APPDATA", ""), "xdg.config", ".wrangler", "config", "default.toml")


def _ler_token() -> dict:
    import tomllib
    try:
        with open(_config_wrangler(), "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return {}


def _token() -> str:
    """o token OAuth do wrangler; vencido (ou a 2 min de vencer), o wrangler renova e grava o novo"""
    c = _ler_token()
    fim = c.get("expiration_time") or ""
    try:
        vence = datetime.datetime.fromisoformat(str(fim).replace("Z", "+00:00")).timestamp()
    except ValueError:
        vence = 0
    if not c.get("oauth_token") or vence - time.time() < 120:
        w = os.path.join(_ferramentas(), "node_modules", ".bin", "wrangler.cmd")
        if not os.path.exists(w):
            raise ErroLicencas("o wrangler não está em %s — instale-o (servicos/licencas/LEIAME.md)" % _ferramentas())
        subprocess.run([w, "whoami"], cwd=_ferramentas(), capture_output=True, timeout=90,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        c = _ler_token()
    if not c.get("oauth_token"):
        raise ErroLicencas("o wrangler desta máquina não está com login — rode `wrangler login` (servicos/licencas/LEIAME.md)")
    return c["oauth_token"]


def _sql(sql: str, params=None) -> list:
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/%s/d1/database/%s/query" % (CONTA, BANCO),
        data=json.dumps({"sql": sql, "params": list(params or [])}).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json", "User-Agent": "Metalica-dev"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8"))
        except ValueError:
            d = {}
        msg = "; ".join(str(x.get("message")) for x in d.get("errors") or []) or str(e)
        raise ErroLicencas("o banco das licenças recusou: " + msg)
    except OSError as e:
        raise ErroLicencas("sem conexão com a Cloudflare: %s" % e)
    if not d.get("success"):
        raise ErroLicencas("o banco das licenças recusou: %s" % d.get("errors"))
    res = d.get("result") or [{}]
    return res[-1].get("results") or []


def _agora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evento(chave: str, tipo: str, detalhe: str, maquina: str = ""):
    _sql("INSERT INTO eventos (quando, chave, maquina, tipo, detalhe, pais) VALUES (?, ?, ?, ?, ?, '')",
         [_agora(), chave, maquina, tipo, detalhe[:500]])


def _quem() -> str:
    import getpass
    import platform
    try:
        return "%s (dev, %s)" % (getpass.getuser(), platform.node())
    except Exception:                                   # noqa: BLE001
        return "dev"


def painel() -> dict:
    lics = _sql("SELECT * FROM licencas ORDER BY ativa DESC, pessoa")
    maqs = _sql("SELECT * FROM maquinas ORDER BY ultima_vez DESC")
    evs = _sql("SELECT * FROM eventos ORDER BY id DESC LIMIT 150")
    for l in lics:
        l["maquinas"] = [m for m in maqs if m["chave"] == l["chave"]]
    return {"licencas": lics, "eventos": evs, "agora": _agora(), "tela": TELA}


def _nova_chave() -> str:
    c = "".join(secrets.choice(ALFABETO) for _ in range(12))
    return "MTL-%s-%s-%s" % (c[:4], c[4:8], c[8:])


def criar(corpo: dict) -> dict:
    pessoa = str(corpo.get("pessoa") or "").strip()[:80]
    if not pessoa:
        raise ErroLicencas("informe o nome da pessoa")
    try:
        maximo = max(1, min(10, int(corpo.get("maquinas_max") or 2)))
    except (TypeError, ValueError):
        maximo = 2
    chave = _nova_chave()
    while _sql("SELECT 1 AS x FROM licencas WHERE chave = ?", [chave]):
        chave = _nova_chave()
    _sql("INSERT INTO licencas (chave, pessoa, email, obs, maquinas_max, ativa, criada) VALUES (?, ?, ?, ?, ?, 1, ?)",
         [chave, pessoa, str(corpo.get("email") or "").strip()[:120], str(corpo.get("obs") or "").strip()[:300], maximo, _agora()])
    _evento(chave, "criada", "%s · por %s" % (pessoa, _quem()))
    return {"chave": chave}


def bloquear(chave: str, ativa: bool) -> dict:
    if not _sql("SELECT 1 AS x FROM licencas WHERE chave = ?", [chave]):
        raise ErroLicencas("licença não encontrada")
    _sql("UPDATE licencas SET ativa = ?, bloqueada_em = ? WHERE chave = ?", [1 if ativa else 0, None if ativa else _agora(), chave])
    _evento(chave, "desbloqueada" if ativa else "bloqueada", "por " + _quem())
    return {"ok": True}


def liberar(maquina_id: int) -> dict:
    m = _sql("SELECT * FROM maquinas WHERE id = ?", [int(maquina_id)])
    if not m:
        raise ErroLicencas("computador não encontrado")
    _sql("UPDATE maquinas SET liberada = 1 WHERE id = ?", [int(maquina_id)])
    _evento(m[0]["chave"], "liberada", "%s · por %s" % (m[0].get("nome_pc", ""), _quem()), m[0]["maquina"])
    return {"ok": True}
