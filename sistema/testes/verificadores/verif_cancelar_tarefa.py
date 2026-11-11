# -*- coding: utf-8 -*-
"""O Cancelar das tarefas em andamento, na tela (DESEMPENHO N.3, 11/11/2026; usuário: "Não consigo cancelar um processo
quando está em andamento, preciso que crie um botão para fazer esse cancelamento").

A. cartão da tela Projetos: um script de obra (outro processo) atualizando o projeto → "Atualizando… · Cancelar";
   o clique pede confirmação; "Continuar a tarefa" não cancela; "Cancelar a tarefa" para o script, o cartão abre e avisa;
B. barra de andamento: "Atualizar pelo modelo 3D" da Lista de materiais (levantamento lento) → a barra tem "Cancelar";
   confirmado, a lista e o romaneio ficam os de antes, a barra sai e o projeto não fica "Atualizando…".

Servidor próprio numa pasta temporária (nunca a 8765/8766), com o levantamento da lista trocado por um lento."""
import json, os, shutil, subprocess, sys, tempfile, textwrap, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cancelar_tarefa_")
# o app de verdade, com o levantamento da lista lento (300 passos de 0,1 s, dizendo o andamento como o de verdade)
LANCADOR = textwrap.dedent('''
    import runpy, sys, time
    sys.path.insert(0, %r)
    import nucleo2d.detalhar as D
    def levantar(doc, avisar=None, **_):
        for i in range(300):
            avisar("%%d peças em 112 posições" %% ((i + 1) * 10))
            time.sleep(0.1)
        return {"posicoes": [], "categorias": {}, "acessorios": {}, "pecas": [], "fora_do_aco": [], "estrutura_a_conferir": []}
    D.levantar = levantar
    sys.argv = ["app.py", "--sem-navegador", "--porta", %r, "--dados", %r]
    runpy.run_path(%r, run_name="__main__")
''') % (BASE, str(PORTA), DADOS, os.path.join(BASE, "app.py"))
srv = subprocess.Popen([sys.executable, "-c", LANCADOR], cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(80):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def clicar(aba, expr_elemento):
    r = aba.avaliar(f"(() => {{ const b = {expr_elemento}; if (!b) return null; b.scrollIntoView({{block: 'center'}}); const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
    if not r:
        raise RuntimeError("não achei " + expr_elemento)
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1, buttons=1 if tipo == "mousePressed" else 0)
    aba.drenar(0.4)


def projeto(nome):
    s = post("/api/projetos", {"nome": nome, "tipo": "desenho"})["slug"]
    post(f"/api/projetos/{urllib.parse.quote(s)}/modelo", {"documento": {"nome": nome, "entidades": [
        {"tipo": "barra", "id": "b1", "nome": "terça", "camada": "Vigas", "perfil": "U150X50X2.28", "inicio": [0, 0, 3000],
         "fim": [0, 6000, 3000]}]}})
    return s


BOTAO_DO_DIALOGO = "[...document.querySelectorAll('dialog.dlg-cancelar-tarefa button')].find(b => b.textContent === %s)"


def a_cartao_cancela_o_script(aba):
    print("A — o cartão da tela Projetos cancela o script de obra")
    s = projeto("Cobertura Filipin")
    script = textwrap.dedent('''
        import sys, time
        sys.path.insert(0, %r)
        import app
        app.PROJETOS = %r
        try:
            for i in range(1200):
                app._progresso(%r, "remontando a marquise (%%d de 1200)" %% i)
                time.sleep(0.1)
            print("INTEIRA")
        except app.TarefaCancelada:
            print("CANCELADA")
    ''') % (BASE, DADOS, s)
    p = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        time.sleep(2.5)
        aba.navegar(base + "/", limite=60)
        cartao = f"document.querySelector('.cartao-atualizando[data-slug=\"{s}\"]')"
        ok(esperar(aba, f"!!{cartao} && !!{cartao}.querySelector('button.cancelar-tarefa')", 30),
           "o cartão mostra Atualizando… com o botão Cancelar")
        clicar(aba, f"{cartao}.querySelector('button.cancelar-tarefa')")
        ok(esperar(aba, "!!document.querySelector('dialog.dlg-cancelar-tarefa[open]')", 10), "o clique pede confirmação")
        texto = aba.avaliar("(document.querySelector('dialog.dlg-cancelar-tarefa') || {}).textContent || ''")
        ok("Cobertura Filipin" in texto and "como estava" in texto, f"a confirmação diz a obra e que o projeto fica como estava ({texto[:120]})")
        foto(aba, "cancelar_1_confirmacao.png")
        clicar(aba, BOTAO_DO_DIALOGO % json.dumps("Continuar a tarefa"))
        time.sleep(1.5)
        ok(p.poll() is None, "Continuar a tarefa não cancela: o script segue")
        clicar(aba, f"{cartao}.querySelector('button.cancelar-tarefa')")
        esperar(aba, "!!document.querySelector('dialog.dlg-cancelar-tarefa[open]')", 10)
        clicar(aba, BOTAO_DO_DIALOGO % json.dumps("Cancelar a tarefa"))
        try:
            saida, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            saida = "(o script não parou)"
        ok(saida.strip() == "CANCELADA", f"o script parou no passo seguinte ({saida.strip()})")
        ok(esperar(aba, f"!{cartao}", 30), "o cartão sai do Atualizando… e o projeto abre")
        ok(esperar(aba, "/Tarefa cancelada/.test(document.body.textContent)", 10), "o aviso diz Tarefa cancelada")
        foto(aba, "cancelar_2_cartao_depois.png")
    finally:
        if p.poll() is None:
            p.kill()


def b_barra_cancela_a_lista(aba):
    print("B — a barra de andamento cancela o Atualizar pelo modelo 3D da lista")
    s = projeto("Lista de ontem")
    q = urllib.parse.quote(s)
    pasta = os.path.join(DADOS, s, "detalhamento")
    os.makedirs(pasta, exist_ok=True)
    antes = {"titulo": "a lista de ontem, 17:40", "posicoes": [], "perfis": [], "chapas": [], "conjuntos": [], "parafusos": []}
    with open(os.path.join(pasta, "lista-de-materiais.json"), "w", encoding="utf-8") as f:
        json.dump(antes, f)
    with open(os.path.join(pasta, "romaneio.csv"), "w", encoding="utf-8") as f:
        f.write("o romaneio de ontem\n")
    aba.navegar(f"{base}/materiais?projeto={q}", limite=60)
    esperar(aba, "!!document.querySelector('#btn-recalcular')", 30)
    aba.drenar(1.0)
    clicar(aba, "document.querySelector('#btn-recalcular')")
    ok(esperar(aba, "!!document.querySelector('.barra-andamento .barra-andamento-cancelar')", 20), "a barra aparece com Cancelar")
    esperar(aba, "/peças em 112/.test((document.querySelector('.barra-andamento') || {}).title || '') || /peças em 112/.test(document.body.textContent)", 10)
    foto(aba, "cancelar_3_barra.png")
    clicar(aba, "document.querySelector('.barra-andamento .barra-andamento-cancelar')")
    ok(esperar(aba, "!!document.querySelector('dialog.dlg-cancelar-tarefa[open]')", 10), "o clique pede confirmação")
    clicar(aba, BOTAO_DO_DIALOGO % json.dumps("Cancelar a tarefa"))
    ok(esperar(aba, "!document.querySelector('.barra-andamento')", 20), "a barra sai")
    ok(esperar(aba, "/cancelada/.test(document.body.textContent)", 10), "a tela diz que foi cancelada")
    with open(os.path.join(pasta, "lista-de-materiais.json"), encoding="utf-8") as f:
        ok(json.load(f) == antes, "a lista ficou a de antes")
    with open(os.path.join(pasta, "romaneio.csv"), encoding="utf-8") as f:
        ok(f.read() == "o romaneio de ontem\n", "o romaneio ficou o de antes")
    pr = _json(f"{base}/api/projetos/{q}/progresso")
    ok(not pr.get("etapa"), f"sem etapa pendurada ({pr})")
    lista = _json(base + "/api/projetos")
    ok(not [p for p in lista if p.get("slug") == s and p.get("atualizando")], "o cartão do projeto não fica Atualizando…")


FOTOS = os.path.dirname(os.path.abspath(__file__))


def foto(aba, nome):
    import base64
    try:
        d = aba.cmd("Page.captureScreenshot", format="png")
        with open(os.path.join(FOTOS, nome), "wb") as f:
            f.write(base64.b64decode(d["data"] if "data" in d else d["result"]["data"]))
    except Exception:                               # noqa: BLE001 — a foto é só para olhar
        pass


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cancelar_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    for passo in (a_cartao_cancela_o_script, b_barra_cancela_a_lista):
        try:
            passo(aba)
        except Exception as exc:                    # noqa: BLE001
            ok(False, f"{passo.__name__}: {exc!r}")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
