# -*- coding: utf-8 -*-
"""Os chats do Claude Code deste projeto, lidos das conversas que o próprio Claude Code grava na máquina
(%USERPROFILE%\\.claude\\projects\\<pasta do projeto>\\<sessão>.jsonl) — 16/10/2026, pedido do usuário: "essas
interações entre vários chats e agentes estão confusas, já me perdi do que cada um está fazendo".

Só leitura e só local: nada sai da máquina, nada é escrito nas conversas. Cada arquivo é lido do ponto onde parou
na última vez (eles só crescem), então a tela pode atualizar a cada poucos segundos mesmo com conversas de 30 MB.

Por chat: título, nome curto ("met-lica-69", descoberto pelas mensagens que os outros chats receberam dele), estado
(trabalhando / sua vez / parado), o último pedido do usuário e a última resposta, os arquivos que editou, os commits,
os agentes que lançou e as mensagens trocadas com outros chats. Mais: os arquivos que dois chats editaram e ainda
estão sem commit, a linha do tempo do dia e as frentes (briefings).
"""
import collections
import datetime as _dt
import glob
import json
import os
import re
import subprocess
import threading
import time
from typing import Dict, List, Optional

SISTEMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(SISTEMA)
BRIEFINGS = os.path.join(REPO, "Projeto", "BRIEFINGS")
_TRAVA = threading.Lock()

#: sem atividade há mais que isto, o chat que não terminou a vez está "parado" (talvez esperando uma permissão)
TRABALHANDO_S = 180
TEXTO = 420                      # caracteres guardados de pedido/resposta


def pastas_das_conversas() -> List[str]:
    """As pastas do Claude Code para este projeto (a raiz e as subpastas, ex.: sistema/)."""
    base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(base):
        return []
    slug = re.sub(r"[^A-Za-z0-9]", "-", REPO).lower()
    return [os.path.join(base, d) for d in sorted(os.listdir(base))
            if d.lower() == slug or d.lower().startswith(slug + "-")]


def _ts(s) -> Optional[float]:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _limpo(t: str, n: int = TEXTO) -> str:
    t = re.sub(r"<(ide_selection|ide_opened_file|system-reminder)>.*?</\1>", " ", str(t or ""), flags=re.S)
    t = re.sub(r"<pasted_content[^>]*>", "[colado] ", t).replace("</pasted_content>", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n] + ("…" if len(t) > n else "")


def _rel(caminho: str) -> str:
    c = str(caminho or "").replace("\\", "/")
    r = REPO.replace("\\", "/")
    if c.lower().startswith(r.lower() + "/"):
        c = c[len(r) + 1:]
    return c


#: as linhas que interessam (as enormes, de pedido à API, ficam de fora sem passar pelo json)
_INTERESSA = tuple(f'"type":{e}"{t}"'.encode() for t in ("user", "assistant", "ai-title") for e in ("", " "))


class Sessao:
    def __init__(self, arquivo: str):
        self.arquivo = arquivo
        self.id = os.path.splitext(os.path.basename(arquivo))[0]
        self.offset = 0
        self.titulo = ""
        self.inicio: Optional[float] = None
        self.ultimo: Optional[float] = None
        self.ultimo_pedido = ""
        self.t_pedido: Optional[float] = None
        self.ultima_resposta = ""
        self.t_resposta: Optional[float] = None
        self.fim_de_vez = False          # a última coisa foi o Claude terminar a vez (end_turn)
        self.arquivos: Dict[str, float] = {}
        self.commits: List[dict] = []
        self.agentes: Dict[str, dict] = {}
        self._agente_pedido: Dict[str, dict] = {}     # tool_use_id → {descricao, t}
        self.enviadas: List[dict] = []                 # mensagens para outros chats
        self.recebidas: List[dict] = []
        self.ferramenta_atual = ""

    # ------------------------------------------------------------------ leitura incremental
    def atualizar(self):
        try:
            tam = os.path.getsize(self.arquivo)
        except OSError:
            return
        if tam < self.offset:            # arquivo trocado: lê de novo
            self.__init__(self.arquivo)
        if tam == self.offset:
            return
        with open(self.arquivo, "rb") as f:
            f.seek(self.offset)
            bruto = f.read()
        fim = bruto.rfind(b"\n")
        if fim < 0:
            return
        self.offset += fim + 1
        for linha in bruto[:fim].split(b"\n"):
            # as linhas enormes de pedido à API não interessam: só as que podem ser mensagem, título ou pedido
            if not linha or not (any(x in linha for x in _INTERESSA) or (b'"queue-operation"' in linha and b'"enqueue"' in linha)):
                continue
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            self._linha(d)

    def _linha(self, d: dict):
        t = d.get("type")
        if t == "ai-title":
            self.titulo = str(d.get("aiTitle") or self.titulo)
            return
        if t == "queue-operation":
            # mensagem que chegou no meio de um trabalho (fica na fila até a próxima rodada de ferramentas)
            c = str(d.get("content") or "")
            if "<cross-session-message" in c or "<agent-message" in c or "<task-notification>" in c:
                self._texto_do_usuario(c, _ts(d.get("timestamp")), True)
            return
        if d.get("isSidechain"):
            return
        ts = _ts(d.get("timestamp"))
        if ts:
            self.inicio = self.inicio or ts
            self.ultimo = max(self.ultimo or 0, ts)
        msg = d.get("message") or {}
        cont = msg.get("content")
        if t == "user":
            itens = [{"type": "text", "text": cont}] if isinstance(cont, str) else (cont or [])
            for it in itens:
                if not isinstance(it, dict):
                    continue
                if it.get("type") == "tool_result":
                    self._resultado(it)
                elif it.get("type") == "text":
                    self._texto_do_usuario(str(it.get("text") or ""), ts, bool(d.get("isMeta")))
        elif t == "assistant":
            self.fim_de_vez = msg.get("stop_reason") == "end_turn"
            for it in cont or []:
                if not isinstance(it, dict):
                    continue
                if it.get("type") == "text" and str(it.get("text") or "").strip():
                    self.ultima_resposta = _limpo(it["text"])
                    self.t_resposta = ts
                elif it.get("type") == "tool_use":
                    self._ferramenta(it, ts)

    def _texto_do_usuario(self, texto: str, ts, meta: bool):
        s = texto.lstrip()
        m = re.search(r'<cross-session-message([^>]*)>(.*?)(?:</cross-session-message>|$)', s, re.S)
        if m:
            atr = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
            texto = _limpo(m.group(2), 600)
            # a mesma mensagem vem na fila (queue-operation) e depois entregue: uma vez só
            if not any(r["texto"][:80] == texto[:80] and r["de"] == (atr.get("from-name") or atr.get("from")) for r in self.recebidas[-30:]):
                self.recebidas.append({"t": ts, "de": atr.get("from-name") or atr.get("from", ""), "endereco": atr.get("from", ""),
                                       "texto": texto})
            return
        m = re.search(r'<agent-message from="([^"]+)">', s)
        if m:
            ag = self.agentes.setdefault(m.group(1), {"id": m.group(1)})
            ag["estado"], ag["fim"] = "terminou", ts
            corpo = re.sub(r"^.*?The report follows:", "", s, flags=re.S)
            ag["relatorio"] = _limpo(corpo, 600)
            return
        for tid, st in re.findall(r"<task-id>([^<]+)</task-id>.*?<status>([^<]+)</status>", s, re.S):
            ag = self.agentes.get(tid)
            if ag is not None:
                ag["estado"] = "terminou" if st == "completed" else st
                ag["fim"] = ts
        if "<task-notification>" in s or s.startswith(("<system-reminder>", "<command-", "Caveat:", "[Request interrupted")) or meta:
            return
        limpo = _limpo(s)
        if limpo:
            self.ultimo_pedido, self.t_pedido = limpo, ts
            self.fim_de_vez = False

    def _ferramenta(self, it: dict, ts):
        nome = str(it.get("name") or "")
        ent = it.get("input") or {}
        self.ferramenta_atual = nome
        if nome in ("Edit", "Write", "NotebookEdit", "MultiEdit") and ent.get("file_path"):
            self.arquivos[_rel(ent["file_path"])] = ts or 0
        elif nome in ("Bash", "PowerShell"):
            cmd = str(ent.get("command") or "")
            for m in re.finditer(r"git commit[^\n]*?-m\s+([\"'])(.+?)(?:\1|\n)", cmd, re.S):
                self.commits.append({"t": ts, "texto": _limpo(m.group(2).split("\n")[0], 220)})
        elif nome == "SendMessage":
            self.enviadas.append({"t": ts, "para": str(ent.get("to") or ""), "resumo": _limpo(ent.get("summary") or "", 120),
                                  "texto": _limpo(ent.get("message") or "", 600)})
        elif nome in ("Agent", "Task"):
            self._agente_pedido[str(it.get("id"))] = {"descricao": _limpo(ent.get("description") or "", 80), "t": ts,
                                                       "modelo": ent.get("model") or ""}

    def _resultado(self, it: dict):
        pedido = self._agente_pedido.pop(str(it.get("tool_use_id")), None)
        if not pedido or it.get("is_error"):
            return                          # a chamada que deu erro não lançou agente nenhum
        txt = it.get("content")
        txt = " ".join(x.get("text", "") for x in txt if isinstance(x, dict)) if isinstance(txt, list) else str(txt or "")
        m = re.search(r"agentId:\s*([A-Za-z0-9_-]+)", txt)
        aid = m.group(1) if m else "?" + str(it.get("tool_use_id"))[-6:]
        ag = self.agentes.setdefault(aid, {"id": aid})
        ag.update({"descricao": pedido["descricao"], "inicio": pedido["t"], "modelo": pedido["modelo"]})
        ag.setdefault("estado", "rodando" if "background" in txt.lower() or m else "terminou")

    # ------------------------------------------------------------------ para a tela
    def estado(self, agora: float) -> str:
        if self.ultimo is None:
            return "inativo"
        parado = agora - self.ultimo
        if self.fim_de_vez:
            return "sua_vez" if parado < 12 * 3600 else "inativo"
        if parado < TRABALHANDO_S:
            return "trabalhando"
        return "parado" if parado < 12 * 3600 else "inativo"


_SESSOES: Dict[str, Sessao] = {}


def _agentes_em_disco(s: Sessao, agora: float):
    """Os agentes da sessão pela pasta subagents/ (descrição e a última atividade)."""
    pasta = os.path.join(os.path.dirname(s.arquivo), s.id, "subagents")
    for meta in glob.glob(os.path.join(pasta, "agent-*.meta.json")):
        aid = os.path.basename(meta)[len("agent-"):-len(".meta.json")]
        ag = s.agentes.setdefault(aid, {"id": aid, "estado": "rodando"})
        try:
            with open(meta, encoding="utf-8") as f:
                m = json.load(f)
            ag.setdefault("descricao", m.get("description") or "")
            ag.setdefault("modelo", m.get("model") or "")
        except (OSError, ValueError):
            pass
        jl = meta.replace(".meta.json", ".jsonl")
        if os.path.exists(jl):
            ag["ultimo"] = os.path.getmtime(jl)
            ag.setdefault("inicio", os.path.getctime(jl))
            if ag.get("estado") == "rodando" and agora - ag["ultimo"] > 1800:
                ag["estado"] = "sem notícia"


def _git(args: List[str]) -> str:
    try:
        return subprocess.run(["git"] + args, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20).stdout
    except Exception:                                      # noqa: BLE001
        return ""


_GIT = {"t": 0.0, "mexidos": set(), "log": []}


def _estado_git():
    if time.time() - _GIT["t"] < 15:
        return _GIT
    mexidos = set()
    for ln in _git(["status", "--porcelain", "-uall"]).splitlines():
        if len(ln) > 3:
            mexidos.add(ln[3:].strip().strip('"').split(" -> ")[-1])
    log = []
    for ln in _git(["log", "--since=36 hours ago", "--date=iso-strict", "--format=%h\t%ad\t%s"]).splitlines():
        p = ln.split("\t", 2)
        if len(p) == 3:
            log.append({"hash": p[0], "t": _ts(p[1]), "texto": _limpo(p[2], 220)})
    _GIT.update(t=time.time(), mexidos=mexidos, log=log)
    return _GIT


def _frentes(ids_em_commits: set) -> List[dict]:
    out = []
    for arq in sorted(glob.glob(os.path.join(BRIEFINGS, "*.md")), key=os.path.getmtime, reverse=True)[:12]:
        mt = os.path.getmtime(arq)
        if time.time() - mt > 7 * 86400:
            continue
        try:
            with open(arq, encoding="utf-8") as f:
                txt = f.read()
        except OSError:
            continue
        itens = re.findall(r"^###\s+([A-Z]\d{2})\b\s*[—-]\s*(.+)$", txt, re.M)
        estado = re.search(r"^>\s*\*\*ESTADO[^*]*\*\*:?\s*(.+?)(?:\n(?!>)|\Z)", txt, re.M | re.S)
        decisao = [ _limpo(l, 200) for l in txt.splitlines() if re.search(r"DECIS[ÃA]O|decisão do usuário antes|precisa da decisão", l, re.I)][:3]
        out.append({"arquivo": os.path.basename(arq), "alterado": mt, "itens": len(itens),
                    "citados": sum(1 for i, _t in itens if i in ids_em_commits),
                    "estado": _limpo(re.sub(r"\n>\s*", " ", estado.group(1)), 500) if estado else "",
                    "decisoes": decisao})
    return out


def painel(horas: float = 24.0) -> dict:
    agora = time.time()
    with _TRAVA:
        ativos = []
        for pasta in pastas_das_conversas():
            for arq in glob.glob(os.path.join(pasta, "*.jsonl")):
                try:
                    if agora - os.path.getmtime(arq) > horas * 3600:
                        continue
                except OSError:
                    continue
                s = _SESSOES.get(arq) or _SESSOES.setdefault(arq, Sessao(arq))
                s.atualizar()
                _agentes_em_disco(s, agora)
                ativos.append(s)
        # nomes curtos: o texto que uma sessão mandou é o que outra recebeu "from-name=…"
        nome_de, endereco_nome = {}, {}
        recebidas = [(r, s) for s in ativos for r in s.recebidas]
        for r, _s in recebidas:
            if r.get("endereco") and r.get("de"):
                endereco_nome[r["endereco"]] = r["de"]
        conhecidos = {r["de"] for r, _s in recebidas if r.get("de")} | {e["para"] for s in ativos for e in s.enviadas
                                                                        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{2}", e["para"])}
        for s in ativos:
            # 1) o texto que ela mandou chegou num outro chat com from-name
            # o nome muda quando o chat é reaberto (o "Comprimento da peça" foi met-lica-80 e depois e9): vale a mais recente
            for e in reversed(s.enviadas):
                chave = e["texto"][:60]
                r = next((r for r, s_r in recebidas if s_r is not s and chave and r["texto"].startswith(chave)), None)
                if r:
                    nome_de[s.id] = r["de"]
                    break
            if s.id in nome_de:
                continue
            # 2) a assinatura no começo das mensagens dela ("met-lica-56: …", "met-lica-56 aqui"), de um nome conhecido
            #    que ela nunca usou como destino
            assin = collections.Counter(m.group(1) for e in s.enviadas[-6:]
                                        for m in [re.match(r"\s*([a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{2})\b[:\s]", e["texto"])] if m)
            destinos = {e["para"] for e in s.enviadas}
            for nome, _n in assin.most_common():
                if nome in conhecidos and nome not in destinos:
                    nome_de[s.id] = nome
                    break
        g = _estado_git()
        # arquivos editados por mais de um chat e ainda sem commit
        quem_mexeu = collections.defaultdict(set)
        for s in ativos:
            for a, t in s.arquivos.items():
                if t and agora - t < horas * 3600:
                    quem_mexeu[a].add(s.id)
        conflitos = []
        for a, ss in sorted(quem_mexeu.items()):
            if len(ss) > 1 and any(m == a or a.endswith("/" + m) or m.endswith(a) for m in g["mexidos"]):
                conflitos.append({"arquivo": a, "chats": sorted(ss)})

        def rotulo(sid):
            s = next((x for x in ativos if x.id == sid), None)
            return nome_de.get(sid) or (s.titulo if s and s.titulo else sid[:8])

        chats, linha = [], []
        ids = set()
        for s in sorted(ativos, key=lambda x: -(x.ultimo or 0)):
            est = s.estado(agora)
            agentes = sorted(s.agentes.values(), key=lambda a: -(a.get("inicio") or 0))
            sem_commit = sorted(a for a in s.arquivos if any(m == a or m.endswith(a) or a.endswith(m) for m in g["mexidos"]))
            chats.append({
                "id": s.id, "nome": nome_de.get(s.id) or "", "titulo": s.titulo or "(sem título)", "estado": est,
                "ultimo": s.ultimo, "inicio": s.inicio, "parado_s": (agora - s.ultimo) if s.ultimo else None,
                "ultimo_pedido": s.ultimo_pedido, "t_pedido": s.t_pedido,
                "ultima_resposta": s.ultima_resposta, "t_resposta": s.t_resposta, "ferramenta": s.ferramenta_atual,
                "arquivos": sorted(s.arquivos, key=lambda a: -(s.arquivos[a] or 0))[:40], "sem_commit": sem_commit[:40],
                "commits": s.commits[-15:][::-1],
                "agentes": [{k: a.get(k) for k in ("id", "descricao", "estado", "inicio", "fim", "ultimo", "modelo", "relatorio")}
                            for a in agentes[:15]],
                "enviadas": len(s.enviadas), "recebidas": len(s.recebidas),
            })
            for c in s.commits:
                linha.append({"t": c["t"], "tipo": "commit", "chat": rotulo(s.id), "texto": c["texto"]})
                ids.update(re.findall(r"\b([A-Z]\d{2})\b", c["texto"]))
            for e in s.enviadas:
                para = endereco_nome.get(e["para"]) or next((a.get("descricao") for a in s.agentes.values() if a.get("id") == e["para"]), "") or e["para"][-12:]
                linha.append({"t": e["t"], "tipo": "mensagem", "chat": rotulo(s.id), "para": para,
                              "texto": e["resumo"] or e["texto"][:160], "completo": e["texto"]})
            for a in s.agentes.values():
                if a.get("inicio"):
                    linha.append({"t": a["inicio"], "tipo": "agente", "chat": rotulo(s.id), "texto": "lançou o agente: " + (a.get("descricao") or a["id"])})
                if a.get("fim") and a.get("estado") == "terminou":
                    linha.append({"t": a["fim"], "tipo": "agente", "chat": rotulo(s.id), "texto": "agente terminou: " + (a.get("descricao") or a["id"])})
        for c in g["log"]:
            ids.update(re.findall(r"\b([A-Z]\d{2})\b", c["texto"]))
        linha = sorted((x for x in linha if x.get("t") and agora - x["t"] < horas * 3600), key=lambda x: -x["t"])[:250]
        alertas = []
        for c in chats:
            if c["estado"] == "sua_vez":
                alertas.append({"tipo": "sua_vez", "chat": c["nome"] or c["titulo"], "id": c["id"],
                                "texto": f"esperando você há {int((c['parado_s'] or 0) // 60)} min"})
            elif c["estado"] == "parado":
                alertas.append({"tipo": "parado", "chat": c["nome"] or c["titulo"], "id": c["id"],
                                "texto": f"sem atividade há {int((c['parado_s'] or 0) // 60)} min sem terminar a vez — pode estar esperando uma permissão"})
        for k in conflitos:
            alertas.append({"tipo": "conflito", "chat": ", ".join(rotulo(x) for x in k["chats"]),
                            "texto": f"{len(k['chats'])} chats editaram {k['arquivo']} e ele está sem commit"})
        return {"agora": agora, "horas": horas, "chats": chats, "alertas": alertas, "linha": linha,
                "frentes": _frentes(ids), "commits_git": g["log"][:40], "pastas": pastas_das_conversas()}
