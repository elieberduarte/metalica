# -*- coding: utf-8 -*-
"""Ganchos (hooks) do Claude Code que ligam os chats ao Painel DEV (16/10/2026, pedido do usuário: "responder por
essa tela — um escritório onde os agentes trabalham e vêm com as perguntas e dúvidas"). Configurados em
.claude/settings.local.json; cada chat deste projeto os roda:

  parada    Stop, em segundo plano (asyncRewake): o chat terminou a vez. Registra o que ele disse na caixa do painel
            e fica esperando: a resposta digitada no painel acorda o chat (sai com 2 e a resposta vai para ele); se
            o usuário responder no próprio VS Code, ou chegar outra coisa, sai calado.
  pergunta  PreToolUse do AskUserQuestion: a pergunta com opções vai para o painel; a escolha feita lá volta como a
            resposta da ferramenta. Sem resposta em 10 min, a pergunta aparece no VS Code, como sempre.
  aviso     Notification de permissão: o painel mostra que o chat está pedindo permissão (aprovar continua no VS Code).

A caixa fica em %LOCALAPPDATA%\\Metalica\\painel_dev (fora do OneDrive e do git): pendentes/<sessão>.json (o que espera
o usuário, com um token), respostas/<sessão>.json (o painel grava; vale só com o mesmo token), avisos/<sessão>.json.
Nada sai da máquina.
"""
import json
import os
import sys
import tempfile
import time
import uuid

#: METALICA_PAINEL_CAIXA troca a pasta (testes: mudar o LOCALAPPDATA esconderia as bibliotecas do Python)
CAIXA = os.environ.get("METALICA_PAINEL_CAIXA") or os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                                                                  "Metalica", "painel_dev")
PENDENTES = os.path.join(CAIXA, "pendentes")
RESPOSTAS = os.path.join(CAIXA, "respostas")
AVISOS = os.path.join(CAIXA, "avisos")

#: quanto a parada espera a resposta do painel (o timeout do gancho é um pouco maior) e a pergunta com opções
ESPERA_PARADA = 3 * 3600
ESPERA_PERGUNTA = 600
PASSO = 1.5


def _ler(arq):
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gravar(arq, dados):
    """grava inteiro de uma vez (arquivo temporário + troca): quem lê nunca pega pela metade"""
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    tmp = arq + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, arq)


def _apagar(arq, token=None):
    """apaga, mas só se ainda for o do token (outro gancho pode ter gravado por cima)"""
    if token is not None:
        d = _ler(arq)
        if not d or d.get("token") != token:
            return
    try:
        os.remove(arq)
    except OSError:
        pass


def _arq(pasta, sid):
    return os.path.join(pasta, "".join(c for c in str(sid) if c.isalnum() or c in "-_") + ".json")


def _ts(s):
    import datetime as _dt
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _usuario_voltou(transcricao, desde, t0) -> bool:
    """o chat recebeu outra entrada depois que parou (o usuário digitou no VS Code, chegou mensagem de outro chat…):
    uma linha do usuário, com texto, de depois que o gancho começou"""
    try:
        if not transcricao or os.path.getsize(transcricao) <= desde:
            return False
        with open(transcricao, "rb") as f:
            f.seek(desde)
            novo = f.read()
    except OSError:
        return False
    for linha in novo.split(b"\n"):
        if b'"type":"user"' not in linha and b'"type": "user"' not in linha:
            continue
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        ts = _ts(d.get("timestamp"))
        if ts is None or ts < t0 - 0.5:
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, str) or any(isinstance(i, dict) and i.get("type") == "text" for i in (c or [])):
            return True
    return False


def parada(d: dict) -> int:
    sid = d.get("session_id")
    if not sid:
        return 0
    token = uuid.uuid4().hex
    pend = _arq(PENDENTES, sid)
    transcricao = d.get("transcript_path") or ""
    gravar(pend, {"tipo": "vez", "sessao": sid, "token": token, "t": time.time(), "pid": os.getpid(),
                  "texto": str(d.get("last_assistant_message") or "")[:8000], "transcricao": transcricao})
    _apagar(_arq(AVISOS, sid))
    t0 = time.time()
    try:
        desde = max(0, os.path.getsize(transcricao) - 65536) if transcricao else 0   # olha um pouco para trás: pela hora
    except OSError:
        desde = 0
    fim = t0 + ESPERA_PARADA
    resp = _arq(RESPOSTAS, sid)
    while time.time() < fim:
        time.sleep(PASSO)
        p = _ler(pend)
        if not p or p.get("token") != token:
            return 0                                   # outro gancho do mesmo chat tomou o lugar
        r = _ler(resp)
        if r and r.get("token") == token and str(r.get("texto") or "").strip():
            _apagar(resp)
            _apagar(pend, token)
            msg = ("Resposta do usuário pelo Painel DEV (ele leu a sua última mensagem no painel e respondeu por lá, "
                   "em vez de no chat):\n\n" + str(r["texto"]).strip() + "\n")
            sys.stderr.buffer.write(msg.encode("utf-8"))
            sys.stderr.flush()
            return 2                                   # acorda o chat com a resposta
        if _usuario_voltou(transcricao, desde, t0):
            _apagar(pend, token)
            return 0
    _apagar(pend, token)
    return 0


def pergunta(d: dict) -> int:
    sid = d.get("session_id")
    entrada = d.get("tool_input") or {}
    perguntas = entrada.get("questions") or []
    if not sid or not perguntas:
        return 0
    token = uuid.uuid4().hex
    pend = _arq(PENDENTES, sid)
    gravar(pend, {"tipo": "pergunta", "sessao": sid, "token": token, "t": time.time(), "pid": os.getpid(),
                  "perguntas": perguntas, "texto": "\n".join(str(q.get("question") or "") for q in perguntas),
                  "transcricao": d.get("transcript_path") or "", "prazo": time.time() + ESPERA_PERGUNTA})
    resp = _arq(RESPOSTAS, sid)
    fim = time.time() + ESPERA_PERGUNTA
    while time.time() < fim:
        time.sleep(PASSO)
        p = _ler(pend)
        if not p or p.get("token") != token:
            return 0
        r = _ler(resp)
        if r and r.get("token") == token and isinstance(r.get("respostas"), dict):
            _apagar(resp)
            _apagar(pend, token)
            respostas = {str(k): str(v) for k, v in r["respostas"].items()}
            saida = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                            "updatedInput": dict(entrada, answers=respostas)}}
            sys.stdout.buffer.write(json.dumps(saida, ensure_ascii=False).encode("utf-8"))
            sys.stdout.flush()
            return 0
    _apagar(pend, token)                               # sem resposta: a pergunta segue para o VS Code
    return 0


def aviso(d: dict) -> int:
    sid = d.get("session_id")
    if sid and d.get("notification_type") in (None, "permission_prompt", "elicitation_dialog", "agent_needs_input"):
        gravar(_arq(AVISOS, sid), {"sessao": sid, "t": time.time(), "tipo": d.get("notification_type") or "",
                                   "texto": str(d.get("message") or "")[:1000]})
    return 0


def main(argv) -> int:
    try:
        d = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return 0
    acao = argv[0] if argv else ""
    try:
        return {"parada": parada, "pergunta": pergunta, "aviso": aviso}.get(acao, lambda _d: 0)(d)
    except Exception:                                  # noqa: BLE001 — um gancho com defeito não pode travar o chat
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
