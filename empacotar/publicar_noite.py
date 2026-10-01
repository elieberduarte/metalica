# -*- coding: utf-8 -*-
"""A conferência e a publicação da noite (pedido do usuário, 28/09: "deixar isso para rodar em certos
períodos"; às 23h00, e "se a conferência passar pode publicar sozinho").

Durante o dia os ajustes vão para o `main` e aparecem no modo desenvolvimento (8766), com o teste do
ponto mexido; a conferência completa (uns 30 a 60 min) roda uma vez, aqui, sobre tudo o que entrou:

1. nada novo desde a última versão publicada → não faz nada;
2. a versão: se `versao.py` ainda é a publicada, sobe o último número e escreve as notas no LEIAME a
   partir das mensagens dos commits (o que já foi escrito à mão durante o dia fica);
3. uma cópia limpa do repositório nesse commit (git worktree em %TEMP%, com `Projeto/` ligado ao de
   verdade, onde ficam a bateria das obras e o registro da completa): é o que vai no pacote, sem o
   que está fora do Git (o pré-moldado, só do modo desenvolvimento);
4. a conferência completa nessa cópia (`testes/antes_de_publicar.py --completa`), com a barrinha do
   modo desenvolvimento acompanhando;
5. tudo verde e a bateria das obras IGUAL à rodada aceita → instalador, teste do executável, etiqueta,
   push do commit conferido, release no GitHub e atualização do programa instalado (se estiver aberto;
   fechado, ele avisa ao abrir). Diferença na bateria não é erro, mas precisa de alguém olhar: a noite
   não publica e deixa o relatório; de manhã, conferida e aceita (`bateria_obras.py --aceitar-ultima`),
   `--publicar-aprovado` publica sem refazer a conferência.

Relatório: Projeto/conferencia-noite/AAAA-MM-DD.txt e ultima.json.

Uso:  python empacotar/publicar_noite.py                     a rodada da noite
      python empacotar/publicar_noite.py --sem-publicar       só confere
      python empacotar/publicar_noite.py --publicar-aprovado  publica o commit conferido na noite (bateria aceita)
      python empacotar/publicar_noite.py --agendar            agenda às 23h00 no Agendador de Tarefas
"""
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)
SISTEMA = os.path.join(REPO, "sistema")
PROJETO = os.path.join(REPO, "Projeto")
PASTA_LOG = os.path.join(PROJETO, "conferencia-noite")
REGISTRO = os.path.join(PASTA_LOG, "ultima.json")
COPIA = os.path.join(tempfile.gettempdir(), "metalica-noite", "repo")
TRAVA = os.path.join(tempfile.gettempdir(), "metalica-noite", "rodando.lock")
GITHUB = "elieberduarte/metalica"
PORTA_INSTALADO = 8765
HORA = "23:00"
#: o Python de console para os processos filhos (a tarefa roda no pythonw, sem janela)
PY = (os.path.join(os.path.dirname(sys.executable), "python.exe")
      if os.path.exists(os.path.join(os.path.dirname(sys.executable), "python.exe")) else sys.executable)
#: o que não vai no programa: só isso mudou, não há versão para publicar
FORA_DO_PACOTE = ("sistema/testes/", "empacotar/publicar_noite.py", "Projeto/", "manual/")
TAREFA = "Metalica - conferencia da noite"

_log_arq = None


def log(msg=""):
    linha = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(linha, flush=True)
    if _log_arq:
        with open(_log_arq, "a", encoding="utf-8") as f:
            f.write(linha + "\n")


def git(*args, cwd=REPO, check=True) -> str:
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), (r.stderr or r.stdout).strip()[:400]))
    return r.stdout.strip()


def rodar(cmd, cwd, env=None, arquivo=None) -> int:
    """roda e copia a saída para o relatório"""
    log("> " + " ".join(cmd))
    # a saída vai para o relatório (arquivo): em UTF-8, senão a seta "→" do relatório da bateria derruba
    # o processo no cp1252 do Windows
    env = dict(env or os.environ, PYTHONIOENCODING="utf-8")
    with open(arquivo or _log_arq or os.devnull, "a", encoding="utf-8") as f:
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode


def registrar(**campos):
    os.makedirs(PASTA_LOG, exist_ok=True)
    d = {}
    if os.path.exists(REGISTRO):
        try:
            with open(REGISTRO, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
    d.update(campos, atualizado=time.strftime("%Y-%m-%d %H:%M"))
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ versão e notas
def _versao_no_arquivo() -> str:
    with open(os.path.join(SISTEMA, "versao.py"), encoding="utf-8") as f:
        return re.search(r'VERSAO\s*=\s*"([\d.]+)"', f.read()).group(1)


def _proxima(v: str) -> str:
    a, b, c = (int(x) for x in v.split("."))
    return "%d.%d.%d" % (a, b, c + 1)


def _frase(assunto: str) -> str:
    """a primeira frase da mensagem do commit, sem o "(pedido do usuário, …)" e sem o fim longo"""
    t = re.sub(r"\s*\((?:pedidos? do usuário|pedido)[^)]*\)", "", assunto).strip()
    t = re.split(r"(?<=[.;])\s", t)[0].rstrip(".;")
    return t[:220] + ("…" if len(t) > 220 else "")


def subir_versao(etiqueta: str) -> str:
    """versao.py e as notas do LEIAME para a versão nova, num commit só destes dois arquivos"""
    nova = _proxima(etiqueta.lstrip("v"))
    assuntos = [a for a in git("log", "--format=%s", "%s..HEAD" % etiqueta).splitlines()
                if a and not re.match(r"^\d+\.\d+\.\d+:", a)]
    caminho_v = os.path.join(SISTEMA, "versao.py")
    with open(caminho_v, encoding="utf-8", newline="") as f:
        t = f.read()
    t = re.sub(r'VERSAO\s*=\s*"[\d.]+"', 'VERSAO = "%s"' % nova, t, count=1)
    with open(caminho_v, "w", encoding="utf-8", newline="") as f:
        f.write(t)
    caminho_l = os.path.join(SISTEMA, "LEIAME.md")
    with open(caminho_l, encoding="utf-8", newline="") as f:
        s = f.read()
    nl = "\r\n" if "\r\n" in s else "\n"
    if "**%s.**" % nova not in s:
        m = re.search(r"(?m)^\*\*\d+\.\d+\.\d+\.\*\*", s)
        notas = ("**%s.** (versão da noite, %s) " % (nova, time.strftime("%d/%m/%Y"))
                 + "; ".join(_frase(a) for a in reversed(assuntos)) + "." + nl + nl)
        s = s[:m.start()] + notas + s[m.start():] if m else s + nl + notas
        with open(caminho_l, "w", encoding="utf-8", newline="") as f:
            f.write(s)
    git("commit", "-m", "%s: versão da noite (%d mudança(s) desde %s)\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
        % (nova, len(assuntos), etiqueta), "--", "sistema/versao.py", "sistema/LEIAME.md")
    log("versão nova: %s (%d commits desde %s)" % (nova, len(assuntos), etiqueta))
    return nova


def notas_da_versao(v: str) -> str:
    """o bloco "**X.Y.Z.** …" do LEIAME, em texto simples, para a release"""
    with open(os.path.join(SISTEMA, "LEIAME.md"), encoding="utf-8") as f:
        s = f.read().replace("\r\n", "\n")
    m = re.search(r"(?ms)^\*\*%s\.\*\*(.*?)(?=^\*\*\d+\.\d+\.\d+\.\*\*|^#)" % re.escape(v), s)
    texto = (m.group(1) if m else "Versão %s." % v).strip()
    texto = re.sub(r"\*\*", "", texto).replace("`", "")
    return re.sub(r"(?<!\n)\n(?!\n)", " ", texto)


# ------------------------------------------------------------------ cópia limpa e conferência
#: As pastas fora do git que a cópia limpa usa, ligadas por junção às de verdade: os dados (Projeto/) e os
#: modelos de exemplo dos verificadores (grandes demais para o git — sem eles, os verificadores das telas
#: falhavam todos, 29/09).
JUNCOES = (("Projeto",), ("sistema", "projetos", "modelos"))


def _soltar_projeto():
    """desfaz as junções da cópia ANTES de apagar a cópia: apagar a pasta seguindo a junção apagaria os
    dados de verdade (a bateria, os relatórios, os modelos). Se não for junção, não apaga nada."""
    for partes in JUNCOES:
        j = os.path.join(COPIA, *partes)
        if not os.path.lexists(j):
            continue
        if not os.path.isjunction(j):
            if partes == ("Projeto",):
                raise RuntimeError("%s não é a junção esperada: a cópia não foi apagada" % j)
            continue
        os.rmdir(j)                                              # remove só a junção


def apagar_copia():
    if not os.path.exists(COPIA):
        return
    _soltar_projeto()
    git("worktree", "remove", "--force", COPIA, check=False)
    shutil.rmtree(COPIA, ignore_errors=True)
    git("worktree", "prune", check=False)


def copia_limpa(commit: str) -> str:
    """git worktree do commit em %TEMP%, com Projeto/ ligado ao de verdade (junção)"""
    apagar_copia()
    git("worktree", "prune", check=False)
    os.makedirs(os.path.dirname(COPIA), exist_ok=True)
    git("worktree", "add", "--detach", COPIA, commit)
    for partes in JUNCOES:
        destino = os.path.join(COPIA, *partes)
        origem = os.path.join(REPO, *partes)
        if not os.path.isdir(origem):
            continue
        if os.path.isdir(destino) and not os.listdir(destino):
            os.rmdir(destino)                                    # a pasta vazia que o git criou
        if not os.path.lexists(destino):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            subprocess.run(["cmd", "/c", "mklink", "/J", destino, origem], capture_output=True, check=True)
    return COPIA


def bateria_igual(desde: float) -> tuple:
    """(igual, texto) do relatório da bateria desta rodada: cada obra "igual à rodada aceita" (ou a
    primeira rodada dela)"""
    arq = os.path.join(PROJETO, "bateria", "ultima-comparacao.txt")
    if not os.path.exists(arq) or os.path.getmtime(arq) < desde:
        return False, "relatório da bateria não foi gerado nesta rodada"
    with open(arq, encoding="utf-8") as f:
        texto = f.read()
    blocos = [b for b in texto.split("\n== ")[1:]]
    iguais = all(all(l.strip() in ("igual à rodada aceita", "primeira rodada")
                     for l in b.splitlines()[1:] if l.strip()) for b in blocos)
    return iguais, texto


ARQ_CONFERENCIA = os.path.join(SISTEMA, "testes", "_conferencia.json")


def conferir(copia: str) -> bool:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", METALICA_CONFERENCIA_ARQ=ARQ_CONFERENCIA)
    return rodar([PY, "testes/antes_de_publicar.py", "--completa"], os.path.join(copia, "sistema"), env) == 0


def cancelada() -> bool:
    """o botão Cancelar da barrinha (app.cancelar_conferencia) derrubou a conferência e marcou o arquivo dela"""
    try:
        with open(ARQ_CONFERENCIA, encoding="utf-8") as f:
            return bool(json.load(f).get("cancelada"))
    except (OSError, ValueError):
        return False


# ------------------------------------------------------------------ pacote e publicação
def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def testar_executavel(versao: str) -> bool:
    exe = os.path.join(tempfile.gettempdir(), "metalica-build", "dist", "Metalica", "Metalica.exe")
    porta, dados = _porta_livre(), tempfile.mkdtemp(prefix="metalica_noite_exe_")
    p = subprocess.Popen([exe, "--sem-navegador", "--porta", str(porta), "--dados", dados])
    try:
        base = "http://127.0.0.1:%d" % porta
        v = None
        for _ in range(120):
            try:
                v = json.load(urllib.request.urlopen(base + "/api/versao", timeout=2))
                break
            except Exception:                                   # noqa: BLE001 — ainda subindo
                time.sleep(0.5)
        if not v or v.get("versao") != versao:
            log("executável: versão %r (esperada %s)" % (v and v.get("versao"), versao))
            return False
        for rota in ("/", "/cad", "/editor", "/api/projetos"):
            if urllib.request.urlopen(base + rota, timeout=15).status != 200:
                log("executável: %s não abriu" % rota)
                return False
        # os módulos importados dentro de funções (desenhos_vivos…) foram para o pacote: a rota responde
        # com o erro do projeto que não existe (400), não com módulo faltando (500)
        try:
            urllib.request.urlopen(base + "/api/projetos/nao-existe/desenhos-vivos", timeout=15)
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                log("executável: /desenhos-vivos deu %d (módulo fora do pacote?)" % e.code)
                return False
        log("executável %s ok (/, /cad, /editor, /api/projetos, desenhos-vivos)" % versao)
        return True
    finally:
        p.terminate()
        shutil.rmtree(dados, ignore_errors=True)


def _token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, check=True).stdout
    return dict(l.split("=", 1) for l in out.strip().splitlines() if "=" in l)["password"]


def _api(rota, dados=None, metodo=None, tipo="application/json", tok=None, base="https://api.github.com"):
    corpo = None if dados is None else (dados if isinstance(dados, bytes) else json.dumps(dados).encode())
    req = urllib.request.Request(base + rota, data=corpo, method=metodo or ("POST" if corpo is not None else "GET"))
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    if corpo is not None:
        req.add_header("Content-Type", tipo)
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def release(versao: str, exe: str) -> str:
    """cria a release vX (rascunho até o instalador subir: o programa que consulta a "latest" nunca vê
    a versão sem o .exe) e a publica"""
    tag, tok = "v" + versao, _token()
    try:
        rel = _api("/repos/%s/releases/tags/%s" % (GITHUB, tag), tok=tok)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rel = _api("/repos/%s/releases" % GITHUB, {"tag_name": tag, "name": "Metálica " + versao,
                                                   "body": notas_da_versao(versao), "draft": True}, tok=tok)
    nome = "Metalica-%s-instalador.exe" % versao
    if nome not in [a["name"] for a in rel.get("assets", [])]:
        with open(exe, "rb") as f:
            _api("?name=" + nome, f.read(), tipo="application/octet-stream", tok=tok, base=rel["upload_url"].split("{")[0])
    if rel.get("draft"):
        rel = _api("/repos/%s/releases/%d" % (GITHUB, rel["id"]), {"draft": False}, metodo="PATCH", tok=tok)
    return rel["html_url"]


def atualizar_instalado() -> str:
    try:
        urllib.request.urlopen("http://localhost:%d/api/versao" % PORTA_INSTALADO, timeout=3)
    except Exception:                                           # noqa: BLE001
        return "programa instalado fechado: ele avisa da versão nova ao abrir"
    req = urllib.request.Request("http://localhost:%d/api/atualizacao/instalar" % PORTA_INSTALADO, data=b"{}",
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=120).read()
        return "programa instalado atualizando"
    except Exception as e:                                      # noqa: BLE001
        return "não consegui atualizar o programa instalado: %s" % e


def publicar(commit: str, versao: str, copia: str) -> bool:
    if rodar([PY, "empacotar/construir.py"], copia) != 0:
        log("FALHOU: o instalador não foi gerado")
        return False
    exe = os.path.join(copia, "Metalica-instalador.exe")
    if not os.path.exists(exe) or not testar_executavel(versao):
        log("FALHOU: o executável não passou no teste")
        return False
    tag = "v" + versao
    if tag not in git("tag", "--list", tag).splitlines():
        git("tag", tag, commit)
    # só o commit conferido vai para o main do GitHub (o que entrou depois espera a próxima noite)
    git("push", "origin", "%s:refs/heads/main" % commit)
    git("push", "origin", tag)
    url = release(versao, exe)
    shutil.copy2(exe, os.path.join(REPO, "Metalica-instalador.exe"))
    log("release publicada: %s" % url)
    log(atualizar_instalado())
    registrar(publicada=versao, release=url)
    return True


# ------------------------------------------------------------------ agendamento
def agendar() -> int:
    """a tarefa diária no Agendador de Tarefas do Windows (roda com o usuário logado)"""
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else py              # sem janela de console às 23h
    ps = ("$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '\"{script}\"' -WorkingDirectory '{repo}';"
          "$t = New-ScheduledTaskTrigger -Daily -At {hora};"
          "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries;"
          "Register-ScheduledTask -TaskName '{nome}' -Action $a -Trigger $t -Settings $s -Force | Out-Null;"
          "(Get-ScheduledTask -TaskName '{nome}').State").format(
              exe=exe.replace("'", "''"), script=os.path.abspath(__file__).replace("'", "''"),
              repo=REPO.replace("'", "''"), hora=HORA, nome=TAREFA)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())
    return r.returncode


# ------------------------------------------------------------------ a rodada
def _prioridade_baixa() -> None:
    """A conferência ocupa a máquina inteira (pytest, ~50 verificadores com Chrome desenhando o 3D por software e
    a bateria): em prioridade baixa ela cede a vez a quem está usando o computador — os processos que ela abre
    herdam a prioridade (pedido do usuário, 01/10: "fica impossível de usar o sistema, fica muito lento")."""
    if os.name != "nt":
        try:
            os.nice(10)
        except (AttributeError, OSError):
            pass
        return
    try:
        import ctypes
        BELOW_NORMAL = 0x00004000
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    except Exception:                                   # noqa: BLE001 — sem prioridade baixa, roda como antes
        pass


def main(argv) -> int:
    global _log_arq
    if "--agendar" in argv:
        return agendar()
    _prioridade_baixa()
    os.makedirs(PASTA_LOG, exist_ok=True)
    os.makedirs(os.path.dirname(TRAVA), exist_ok=True)
    _log_arq = os.path.join(PASTA_LOG, time.strftime("%Y-%m-%d") + ".txt")
    if os.path.exists(TRAVA) and time.time() - os.path.getmtime(TRAVA) < 6 * 3600:
        log("outra rodada da noite está em andamento (%s): nada feito" % TRAVA)
        return 0
    with open(TRAVA, "w") as f:
        f.write(str(os.getpid()))
    try:
        return _rodada(argv)
    except Exception as e:                                      # noqa: BLE001 — o relatório diz o que foi
        log("ERRO: %s" % e)
        registrar(estado="erro", motivo=str(e)[:400])
        return 2
    finally:
        try:
            os.remove(TRAVA)
        except OSError:
            pass
        try:
            apagar_copia()
        except Exception as e:                                  # noqa: BLE001
            log("cópia não apagada: %s" % e)


def _rodada(argv) -> int:
    t0 = time.time()
    log("==== conferência da noite — %s" % datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    etiqueta = git("describe", "--tags", "--abbrev=0", "--match", "v*")
    if "--publicar-aprovado" in argv:
        reg = {}
        if os.path.exists(REGISTRO):
            with open(REGISTRO, encoding="utf-8") as f:
                reg = json.load(f)
        commit, versao = reg.get("commit"), reg.get("versao")
        if not (reg.get("conferencia_ok") and commit and versao) or reg.get("publicada") == versao:
            log("nada aprovado para publicar (registro: %s)" % reg)
            return 1
        log("publicando %s (commit %s), conferido na noite, bateria aceita" % (versao, commit[:9]))
        return 0 if publicar(commit, versao, copia_limpa(commit)) else 1
    novos = int(git("rev-list", "--count", "%s..HEAD" % etiqueta) or 0)
    mudados = [a for a in git("diff", "--name-only", "%s..HEAD" % etiqueta).splitlines() if a]
    do_pacote = [a for a in mudados if not a.startswith(FORA_DO_PACOTE)]
    if not do_pacote and "--forcar" not in argv:
        log("nada novo no programa desde %s (%d commit(s), só testes/ferramentas)" % (etiqueta, novos))
        registrar(estado="nada novo", versao=etiqueta.lstrip("v"))
        return 0
    versao = _versao_no_arquivo()
    if "v" + versao == etiqueta:
        versao = subir_versao(etiqueta)
    commit = git("rev-parse", "HEAD")
    log("conferindo %s (commit %s, %d commit(s) desde %s)" % (versao, commit[:9], novos, etiqueta))
    registrar(estado="conferindo", versao=versao, commit=commit, conferencia_ok=None, bateria_igual=None,
              relatorio=_log_arq)
    copia = copia_limpa(commit)
    ok = conferir(copia)
    if not ok and cancelada():
        registrar(estado="cancelada", conferencia_ok=False)
        log("cancelada pelo usuário (botão da barrinha) após %.0f min: nada publicado; a cópia limpa é desfeita"
            % ((time.time() - t0) / 60))
        return 1
    igual, _texto = bateria_igual(t0)
    log("conferência: %s · bateria: %s (%.0f min)" % ("ok" if ok else "FALHOU", "igual" if igual else "COM DIFERENÇAS",
                                                        (time.time() - t0) / 60))
    registrar(conferencia_ok=ok, bateria_igual=igual)
    if not ok:
        registrar(estado="falhou")
        log("não publicado: a conferência falhou (detalhes acima)")
        return 1
    if not igual:
        registrar(estado="diferenças para conferir")
        log("não publicado: a bateria das obras mudou — conferir Projeto/bateria/ultima-comparacao.txt, "
            "aceitar (testes/bateria_obras.py --aceitar-ultima) e publicar com --publicar-aprovado")
        return 1
    if "--sem-publicar" in argv:
        registrar(estado="conferido")
        return 0
    if not publicar(commit, versao, copia):
        registrar(estado="falhou ao publicar")
        return 1
    registrar(estado="publicada")
    log("==== pronto em %.0f min" % ((time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
