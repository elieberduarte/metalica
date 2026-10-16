# -*- coding: utf-8 -*-
"""Painel DEV (painel_dev/chats.py): a leitura de uma conversa do Claude Code como ela fica gravada — título,
pedido, resposta, arquivos editados, commit, agente lançado e terminado, mensagens entre chats (as que chegam
no meio do trabalho ficam na fila: queue-operation) — e o estado (trabalhando / sua vez / parado)."""
import json
import os
import tempfile
import time

from painel_dev import chats


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def conversa(linhas) -> chats.Sessao:
    pasta = tempfile.mkdtemp(prefix="painel_dev_")
    arq = os.path.join(pasta, "sessao-teste.jsonl")
    with open(arq, "w", encoding="utf-8") as f:
        for d in linhas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    s = chats.Sessao(arq)
    s.atualizar()
    return s


def test_le_a_conversa():
    t = time.time() - 60
    s = conversa([
        {"type": "ai-title", "aiTitle": "Correções do IFC"},
        {"type": "user", "timestamp": _iso(t), "message": {"content": "<pasted_content id=\"x\">Frente: correções</pasted_content>"}},
        {"type": "assistant", "timestamp": _iso(t + 1), "message": {"stop_reason": "tool_use", "content": [
            {"type": "text", "text": "Começo pelo Q04."},
            {"type": "tool_use", "id": "u1", "name": "Edit", "input": {"file_path": os.path.join(chats.REPO, "sistema", "app.py")}},
            {"type": "tool_use", "id": "u2", "name": "Bash", "input": {"command": 'git commit -q -m "Q04: cópia local certa\n\nCo-Authored-By: x"'}},
            {"type": "tool_use", "id": "u3", "name": "Agent", "input": {"description": "Auditor de números", "model": "opus"}},
            {"type": "tool_use", "id": "u4", "name": "SendMessage", "input": {"to": "met-lica-56", "summary": "aviso", "message": "met-lica-69: commitei o Q04"}}]}},
        {"type": "user", "timestamp": _iso(t + 2), "message": {"content": [
            {"type": "tool_result", "tool_use_id": "u3", "content": "Async agent launched successfully.\nagentId: abc123 (internal ID)"}]}},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": _iso(t + 3),
         "content": '<cross-session-message from="uds:pipe-1" hop-chain="h" from-name="met-lica-56" from-mode="prompting">\nok, recebido\n</cross-session-message>'},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": _iso(t + 4),
         "content": '<agent-message from="abc123">\n[Subagent hand-back] The report follows:\n  Terminei.\n</agent-message>'},
        {"type": "assistant", "timestamp": _iso(t + 5), "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Pronto, Q04 feito."}]}},
    ])
    assert s.titulo == "Correções do IFC"
    assert s.ultimo_pedido.startswith("[colado] Frente")
    assert s.ultima_resposta == "Pronto, Q04 feito."
    assert list(s.arquivos) == ["sistema/app.py"]
    assert [c["texto"] for c in s.commits] == ["Q04: cópia local certa"]
    assert s.agentes["abc123"]["descricao"] == "Auditor de números" and s.agentes["abc123"]["estado"] == "terminou"
    assert s.enviadas[0]["para"] == "met-lica-56"
    assert [(r["de"], r["texto"]) for r in s.recebidas] == [("met-lica-56", "ok, recebido")]
    assert s.estado(time.time()) == "sua_vez"


def test_estado_trabalhando_e_parado():
    agora = time.time()
    s = conversa([{"type": "user", "timestamp": _iso(agora - 30), "message": {"content": "faça"}},
                  {"type": "assistant", "timestamp": _iso(agora - 20), "message": {"stop_reason": "tool_use", "content": []}}])
    assert s.estado(agora) == "trabalhando"
    assert s.estado(agora + 600) == "parado"          # não terminou a vez e não mexe há 10 min


def test_leitura_continua_de_onde_parou():
    s = conversa([{"type": "ai-title", "aiTitle": "A"}])
    with open(s.arquivo, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "ai-title", "aiTitle": "B"}) + "\n")
        f.write('{"type": "ai-title", "aiTi')                # linha ainda sendo escrita: espera a próxima leitura
    s.atualizar()
    assert s.titulo == "B"
    with open(s.arquivo, "a", encoding="utf-8") as f:
        f.write('tle": "C"}\n')
    s.atualizar()
    assert s.titulo == "C"


def test_chamada_de_agente_com_erro_nao_conta():
    s = conversa([
        {"type": "assistant", "timestamp": _iso(time.time()), "message": {"stop_reason": "tool_use", "content": [
            {"type": "tool_use", "id": "u9", "name": "Agent", "input": {"description": "tipo errado"}}]}},
        {"type": "user", "timestamp": _iso(time.time()), "message": {"content": [
            {"type": "tool_result", "tool_use_id": "u9", "is_error": True, "content": "Agent type 'x' not found"}]}}])
    assert s.agentes == {}


# ------------------------------------------------------------------ ganchos (responder pelo painel)
import io
import sys
import threading

from painel_dev import ganchos


def _caixa(monkeypatch):
    base = tempfile.mkdtemp(prefix="caixa_")
    for nome in ("PENDENTES", "RESPOSTAS", "AVISOS"):
        monkeypatch.setattr(ganchos, nome, os.path.join(base, nome.lower()))
    monkeypatch.setattr(ganchos, "PASSO", 0.05)
    return base


def _rodar(fn, d, saida):
    class _Std:
        def __init__(self):
            self.buffer = io.BytesIO()

        def flush(self):
            pass
    err, out = _Std(), _Std()
    velho = sys.stderr, sys.stdout
    sys.stderr, sys.stdout = err, out
    try:
        saida["rc"] = fn(d)
    finally:
        sys.stderr, sys.stdout = velho
    saida["err"] = err.buffer.getvalue().decode("utf-8")
    saida["out"] = out.buffer.getvalue().decode("utf-8")


def _esperar_pendente(sid):
    for _ in range(100):
        p = ganchos._ler(ganchos._arq(ganchos.PENDENTES, sid))
        if p:
            return p
        time.sleep(0.02)
    raise AssertionError("o gancho não registrou a pendência")


def test_parada_acorda_o_chat_com_a_resposta_do_painel(monkeypatch):
    _caixa(monkeypatch)
    tr = os.path.join(tempfile.mkdtemp(), "t.jsonl")
    open(tr, "w").close()
    saida = {}
    th = threading.Thread(target=_rodar, args=(ganchos.parada, {"session_id": "s1", "last_assistant_message": "TM1 ou T1A?",
                                                                "transcript_path": tr}, saida))
    th.start()
    p = _esperar_pendente("s1")
    assert p["tipo"] == "vez" and p["texto"] == "TM1 ou T1A?"
    ganchos.gravar(ganchos._arq(ganchos.RESPOSTAS, "s1"), {"token": "outro", "texto": "não vale"})   # token velho: ignora
    time.sleep(0.2)
    assert th.is_alive()
    ganchos.gravar(ganchos._arq(ganchos.RESPOSTAS, "s1"), {"token": p["token"], "texto": "Use T1A + T1B."})
    th.join(5)
    assert saida["rc"] == 2 and "Use T1A + T1B." in saida["err"]
    assert not os.path.exists(ganchos._arq(ganchos.PENDENTES, "s1"))


def test_parada_sai_calada_quando_o_usuario_responde_no_vs_code(monkeypatch):
    _caixa(monkeypatch)
    tr = os.path.join(tempfile.mkdtemp(), "t.jsonl")
    with open(tr, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "timestamp": _iso(time.time() - 30), "message": {"content": "pedido antigo"}}) + "\n")
    saida = {}
    th = threading.Thread(target=_rodar, args=(ganchos.parada, {"session_id": "s2", "last_assistant_message": "pronto",
                                                                "transcript_path": tr}, saida))
    th.start()
    _esperar_pendente("s2")
    time.sleep(0.2)
    assert th.is_alive()                     # o pedido antigo, de antes de parar, não conta
    with open(tr, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "timestamp": _iso(time.time() + 1), "message": {"content": "agora o P07"}}) + "\n")
    th.join(5)
    assert saida["rc"] == 0 and saida["err"] == ""
    assert not os.path.exists(ganchos._arq(ganchos.PENDENTES, "s2"))


def test_pergunta_com_opcoes_respondida_no_painel(monkeypatch):
    _caixa(monkeypatch)
    entrada = {"questions": [{"question": "Qual nome?", "header": "Nome", "multiSelect": False,
                              "options": [{"label": "TM1", "description": ""}, {"label": "T1A + T1B", "description": ""}]}]}
    saida = {}
    th = threading.Thread(target=_rodar, args=(ganchos.pergunta, {"session_id": "s3", "tool_input": entrada}, saida))
    th.start()
    p = _esperar_pendente("s3")
    assert p["tipo"] == "pergunta" and p["perguntas"][0]["question"] == "Qual nome?"
    ganchos.gravar(ganchos._arq(ganchos.RESPOSTAS, "s3"), {"token": p["token"], "respostas": {"Qual nome?": "T1A + T1B"}})
    th.join(5)
    out = json.loads(saida["out"])["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow"
    assert out["updatedInput"]["answers"] == {"Qual nome?": "T1A + T1B"}
    assert out["updatedInput"]["questions"] == entrada["questions"]


def test_aviso_de_permissao_vai_para_a_caixa(monkeypatch):
    _caixa(monkeypatch)
    ganchos.aviso({"session_id": "s4", "notification_type": "permission_prompt", "message": "Claude needs your permission to use Bash"})
    assert ganchos._ler(ganchos._arq(ganchos.AVISOS, "s4"))["texto"].startswith("Claude needs")
