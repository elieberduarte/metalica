# -*- coding: utf-8 -*-
"""A obra compartilhada, do lado do PC (13/11/2026, FERRAMENTA · OBRA COMPARTILHADA, passo 1a).

O usuário: "todos os usuários terem acesso ao mesmo projeto … e outros usuários, conforme forem acessando, com
permissões diferentes: leitura, apontamento…" — piloto o Posto, com o Fernando Editor.

A obra compartilhada tem um `obra_id` fixo no projeto.json (`"compartilhada": {"obra_id": <hex 32>, "nome": …}`),
nunca o slug nem o nome (o Posto renomeado já quebrou o Controle uma vez). Aqui ficam os registros leves — os
apontamentos de produção —, que todos gravam ao mesmo tempo, mesmo sem a vez de editar:

* o Controle grava o evento no `<projeto>/producao/apontamentos.jsonl` como sempre (o formato não muda) e põe o id
  na fila (`na_fila`); `sincronizar` sobe a fila para a nuvem (Worker metalica-celular, rotas /pc/compartilhada/…)
  e traz os eventos que os outros gravaram, acrescentando ao apontamentos.jsonl os que ainda não estão lá (pelo id;
  nenhuma linha é reescrita);
* sem internet nada para: o evento fica no arquivo e na fila e sobe na próxima vez ("N esperando a internet");
* quem garante é a nuvem: ela recusa o apontamento de quem não tem papel para apontar (Leitor) e grava a pessoa da
  licença que assinou o pedido.

O estado fica em `<projeto>/producao/nuvem.json`: o último evento recebido (`ultimo`, a ordem de chegada na nuvem), os
ids que a nuvem já tem, a fila deste computador, o papel e o último erro. O estado é deste computador: se o projeto
chegou de outro PC (pacote, "Enviar para…"), começa do zero — os eventos que vieram no pacote não sobem em nome de
quem recebeu, e a nuvem manda de novo o que falta.
"""
import datetime
import json
import os
import re
import time
import threading
import urllib.error
import urllib.request
import uuid
from typing import Optional

import licenca
import versao

PASTA = "producao"
EVENTOS = "apontamentos.jsonl"
ESTADO = "nuvem.json"
PAPEIS = ("dono", "editor", "apontador", "leitor")
APONTAM = ("dono", "editor", "apontador")
NOME_PAPEL = {"dono": "Dono", "editor": "Editor", "apontador": "Apontador", "leitor": "Leitor"}
#: eventos por POST. A nuvem aceita até 500, mas cada evento é uma consulta no D1 e o plano gratuito da Cloudflare
#: permite 50 por chamada (mais as ~4 da licença e do acesso): 40 cabe em qualquer plano (13/11, o "apontar vários" do
#: Controle manda até 2.000 de uma vez)
POR_PEDIDO = 40
#: segundos, no máximo, subindo lotes numa sincronização (um pedido leva ~0,3 s: centenas de eventos): o resto fica na
#: fila e sobe na próxima (a tela relê a cada 60 s) — o apontar não espera minutos
PRAZO_ENVIO = 8.0
_OBRA_ID = re.compile(r"^[0-9a-f]{32}$")
_CAMPOS = ("id", "quando", "data", "quem", "etapa", "item", "refs", "quantidade", "kg", "estorno_de", "obs")

_TRAVA = threading.RLock()


class ErroObra(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ a obra
def novo_obra_id() -> str:
    return uuid.uuid4().hex


def info(pasta_projeto: str) -> Optional[dict]:
    """o "compartilhada" do projeto.json, ou None (obra que não é compartilhada)"""
    try:
        with open(os.path.join(pasta_projeto, "projeto.json"), encoding="utf-8") as f:
            c = (json.load(f) or {}).get("compartilhada")
    except (OSError, ValueError):
        return None
    if isinstance(c, dict) and _OBRA_ID.match(str(c.get("obra_id") or "")):
        return c
    return None


def pode_apontar(papel: Optional[str]) -> bool:
    return papel in APONTAM


# ------------------------------------------------------------------ o estado deste computador
def _maquina() -> str:
    try:
        return licenca.impressao_da_maquina()
    except Exception:                                   # noqa: BLE001
        return ""


def _cam(pasta_projeto: str, nome: str) -> str:
    return os.path.join(pasta_projeto, PASTA, nome)


def _ler_estado(pasta_projeto: str, obra_id: str) -> dict:
    try:
        with open(_cam(pasta_projeto, ESTADO), encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        e = {}
    if not isinstance(e, dict) or e.get("obra_id") != obra_id or e.get("maquina") != _maquina():
        # outra obra ou outro computador (o projeto veio num pacote): começa do zero
        e = {"obra_id": obra_id, "maquina": _maquina(), "ultimo": 0, "conhecidos": [], "fila": []}
    e.setdefault("ultimo", 0)
    e.setdefault("conhecidos", [])
    e.setdefault("fila", [])
    return e


def _gravar_estado(pasta_projeto: str, e: dict):
    cam = _cam(pasta_projeto, ESTADO)
    os.makedirs(os.path.dirname(cam), exist_ok=True)
    tmp = cam + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, cam)


def _ler_eventos(pasta_projeto: str) -> list:
    out = []
    try:
        with open(_cam(pasta_projeto, EVENTOS), encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        out.append(json.loads(linha))
                    except ValueError:              # linha cortada: o Controle também pula
                        continue
    except OSError:
        pass
    return out


def _acrescentar(pasta_projeto: str, eventos: list):
    cam = _cam(pasta_projeto, EVENTOS)
    os.makedirs(os.path.dirname(cam), exist_ok=True)
    with open(cam, "a", encoding="utf-8", newline="\n") as f:
        for ev in eventos:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def na_fila(pasta_projeto: str, evento_id: str):
    """o Controle gravou um evento neste computador: ele sobe na próxima sincronização"""
    c = info(pasta_projeto)
    if not c or not evento_id:
        return
    with _TRAVA:
        e = _ler_estado(pasta_projeto, c["obra_id"])
        if evento_id not in e["fila"] and evento_id not in e["conhecidos"]:
            e["fila"].append(evento_id)
            _gravar_estado(pasta_projeto, e)


def iniciar(pasta_projeto: str):
    """a obra acabou de virar compartilhada neste computador: todo apontamento que já existe aqui entra na fila"""
    c = info(pasta_projeto)
    if not c:
        raise ErroObra("a obra não é compartilhada (sem obra_id no projeto.json)")
    with _TRAVA:
        e = _ler_estado(pasta_projeto, c["obra_id"])
        for ev in _ler_eventos(pasta_projeto):
            i = ev.get("id")
            if i and i not in e["fila"] and i not in e["conhecidos"]:
                e["fila"].append(i)
        _gravar_estado(pasta_projeto, e)


def estado(pasta_projeto: str) -> Optional[dict]:
    """o que a tela mostra sem ir à nuvem: {obra_id, nome, papel, pendentes, erro, quando} — None se não é compartilhada"""
    c = info(pasta_projeto)
    if not c:
        return None
    with _TRAVA:
        e = _ler_estado(pasta_projeto, c["obra_id"])
    return {"obra_id": c["obra_id"], "nome": c.get("nome") or "", "papel": e.get("papel"),
            "papel_nome": NOME_PAPEL.get(e.get("papel") or "", ""), "pessoa": e.get("pessoa") or "",
            "pendentes": len(e["fila"]), "erro": e.get("erro") or "", "quando": e.get("quando") or "",
            "pode_apontar": pode_apontar(e.get("papel")) if e.get("papel") else True}


# ------------------------------------------------------------------ a nuvem
def _servico() -> str:
    if not versao.CONGELADO and os.environ.get("METALICA_COMPARTILHAR"):
        return os.environ["METALICA_COMPARTILHAR"].rstrip("/")
    import compartilhar
    return compartilhar.SERVICO


def _pedir(metodo: str, rota: str, corpo=None, timeout: float = 6.0) -> dict:
    tok = licenca.token()
    if not tok:
        raise ErroObra("este computador não tem licença do Metálica ativada")
    cab = {"Authorization": "Licenca " + tok, "User-Agent": "Metalica/" + versao.VERSAO}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(_servico() + rota, data=dados, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("erro")
        except Exception:                                   # noqa: BLE001
            msg = None
        raise ErroObra(msg or "a nuvem recusou o pedido (%s)" % e.code, e.code)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErroObra("sem conexão com a nuvem do Metálica (%s)" % str(getattr(e, "reason", e))[:80])


def compartilhadas() -> list:
    """[{obra_id, nome, papel, dono}] — as obras compartilhadas com a licença deste computador"""
    return _pedir("GET", "/pc/compartilhadas").get("obras") or []


def _agora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _do_formato_local(ev: dict) -> dict:
    """o evento da nuvem no formato do apontamentos.jsonl (o do Controle: os mesmos campos, na mesma ordem). A "ancora"
    (13/11, os ids das peças do 3D da unidade: o apontamento segue a peça quando o nome do item muda) vai no fim e só
    quando existe, como o Controle grava; depois dela, também só quando existem, a "montada" e o "lote" da tesoura montada
    (13/11, 283c7e8: as partes apontadas juntas; o estorno de uma desfaz o lote inteiro, também no outro computador)"""
    out = {k: ev.get(k) for k in _CAMPOS}
    if ev.get("ancora"):
        out["ancora"] = [str(x) for x in ev["ancora"]]
    for k in ("montada", "lote"):
        if ev.get(k):
            out[k] = str(ev[k])
    return out


def _receber(pasta_projeto: str, oid: str, e: dict, timeout: float, trava) -> int:
    """traz da nuvem os eventos depois de e["ultimo"] e acrescenta ao arquivo os que faltam; atualiza o papel"""
    recebidos = 0
    while True:
        r = _pedir("GET", "/pc/compartilhada/%s/eventos?depois=%d" % (oid, int(e["ultimo"])), timeout=timeout)
        e["papel"] = r.get("papel")
        e["pessoa"] = r.get("pessoa") or ""
        evs = r.get("eventos") or []
        if evs:
            ja = {ev.get("id") for ev in _ler_eventos(pasta_projeto)}
            novos = [_do_formato_local(ev) for ev in evs if ev.get("id") not in ja]
            if novos:
                if trava is not None:
                    with trava:
                        _acrescentar(pasta_projeto, novos)
                else:
                    _acrescentar(pasta_projeto, novos)
                recebidos += len(novos)
            conhecidos = set(e["conhecidos"])
            conhecidos.update(ev.get("id") for ev in evs)
            e["conhecidos"] = sorted(conhecidos)
            e["fila"] = [i for i in e["fila"] if i not in conhecidos]
            e["ultimo"] = max(int(e["ultimo"]), int(r.get("ultimo") or 0))
        if not r.get("mais"):
            return recebidos


def sincronizar(pasta_projeto: str, timeout: float = 6.0, trava=None) -> Optional[dict]:
    """sobe a fila deste computador e traz o que os outros apontaram. Nunca levanta erro de rede: devolve o estado
    com `erro` e a fila guardada. `trava`: a do Controle (para não acrescentar no meio de um apontar).
    None se a obra não é compartilhada."""
    c = info(pasta_projeto)
    if not c:
        return None
    oid = c["obra_id"]
    with _TRAVA:
        e = _ler_estado(pasta_projeto, oid)
        enviados = recebidos = 0
        try:
            # 1. o que os outros apontaram (antes: o papel e o "só falta N" ficam em dia)
            recebidos = _receber(pasta_projeto, oid, e, timeout, trava)
            # 2. a fila deste computador
            if e["fila"]:
                locais = {ev.get("id"): ev for ev in _ler_eventos(pasta_projeto)}
                fila = [i for i in e["fila"] if i in locais]
                inicio = time.monotonic()
                for k in range(0, len(fila), POR_PEDIDO):
                    if k and time.monotonic() - inicio > PRAZO_ENVIO:
                        break                                   # o resto sobe na próxima sincronização
                    lote = fila[k:k + POR_PEDIDO]
                    r = _pedir("POST", "/pc/compartilhada/%s/eventos" % oid,
                               {"eventos": [locais[i] for i in lote]}, timeout=timeout)
                    aceitos = set(r.get("aceitos") or [])
                    conhecidos = set(e["conhecidos"])
                    conhecidos.update(aceitos)
                    e["conhecidos"] = sorted(conhecidos)
                    enviados += len(aceitos)
                    # o recusado por ser inválido não volta a subir (fica só neste computador, com o aviso)
                    ruins = {x.get("id") for x in r.get("recusados") or []}
                    if ruins:
                        e["recusados"] = sorted(set(e.get("recusados") or []) | ruins)
                    e["fila"] = [i for i in e["fila"] if i not in aceitos and i not in ruins]
                e["fila"] = [i for i in e["fila"] if i in locais]       # o que sumiu do arquivo não tem o que subir
            e["erro"] = ""
            e["quando"] = _agora()
        except ErroObra as x:
            e["erro"] = str(x)
            if x.status == 403:
                e["papel"] = None if "acesso" in str(x) else e.get("papel")
        _gravar_estado(pasta_projeto, e)
    r = estado(pasta_projeto) or {}
    r.update(enviados=enviados, recebidos=recebidos)
    return r
