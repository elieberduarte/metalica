# -*- coding: utf-8 -*-
"""D07 e o recado do D06 na tela de Projetos (agente usuario-desastrado, 13/11), no navegador de verdade:

A. "Novo a partir de IFC…" com um arquivo de 0 bytes: recado "está vazio", e nenhum projeto é criado.
B. Com uma imagem renomeada para .ifc: recado "não é um IFC… O projeto não foi criado.", e a lista continua vazia
   (antes ficava um projeto sem modelo a cada tentativa).
C. Com um IFC cortado no meio: antes de abrir o 3D aparece "O arquivo IFC está incompleto"; cancelando, a tela fica na
   lista e o cartão diz "IFC INCOMPLETO".
D. Projeto novo com o nome de um que já existe: a tela pergunta "Já existe um projeto com este nome"; cancelando, nada
   é criado; confirmando, cria o segundo.
"""
import json, os, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ifcnovo_")
ARQS = tempfile.mkdtemp(prefix="metalica_ifcnovo_arq_")
INTEIRO = open(os.path.join(BASE, "testes", "dados_ifc", "estrutura_mm.ifc"), "rb").read()


def arquivo(nome, bruto):
    caminho = os.path.join(ARQS, nome)
    with open(caminho, "wb") as f:
        f.write(bruto)
    return caminho


VAZIO = arquivo("vazio.ifc", b"")
FOTO = arquivo("foto.ifc", b"\x89PNG\r\n\x1a\n" + bytes(600))
CORTADO = arquivo("cortado.ifc", INTEIRO[:len(INTEIRO) * 2 // 3].rsplit(b"\n", 1)[0] + b"\n#9001=IFCCARTESIANPOINT((0.,0.")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def slugs():
    r = json.loads(urllib.request.urlopen(f"http://localhost:{PORTA}/api/projetos", timeout=30).read().decode("utf-8"))
    return sorted(p["slug"] for p in (r if isinstance(r, list) else r.get("projetos", [])))


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ifcnovo_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    LISTA = f"http://localhost:{PORTA}/"

    def esperar(cond, limite=30.0, passo=0.2):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(passo)
        return False

    def abrir_lista():
        aba.navegar(LISTA, limite=60)
        esperar("!!document.querySelector('[data-acao=\"novo-ifc\"]')", 30)
        aba.drenar(0.8)

    def escolher_ifc(caminho):
        """o botão arma o campo de arquivo (a janela do Windows não abre sem tela); o arquivo entra como ela faria"""
        aba.avaliar("document.querySelector('[data-acao=\"novo-ifc\"]').click()")
        aba.drenar(0.3)
        doc = aba.cmd("DOM.getDocument", depth=-1, pierce=True)
        no = aba.cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="#arquivo-ifc")["nodeId"]
        aba.cmd("DOM.setFileInputFiles", files=[os.path.abspath(caminho)], nodeId=no)
        aba.drenar(0.5)

    dialogo = "(() => { const d = document.getElementById('dlg'); return d.open ? document.getElementById('dlg-titulo').textContent : ''; })()"
    recados = "[...document.querySelectorAll('#bandeja .recado')].map(r => r.textContent).join(' || ')"

    print("A — o arquivo de 0 bytes")
    abrir_lista()
    escolher_ifc(VAZIO)
    ok(esperar("/está vazio \\(0 bytes\\)/.test(" + recados + ")", 10), "o recado diz que o arquivo está vazio")
    ok(not aba.avaliar(dialogo), "o diálogo do projeto novo nem abre")
    ok(slugs() == [], "nenhum projeto criado")

    print("B — a imagem renomeada para .ifc")
    abrir_lista()
    escolher_ifc(FOTO)
    ok(esperar(dialogo + " === 'Novo projeto a partir de IFC'", 10), "o diálogo do projeto novo abre")
    aba.avaliar("document.getElementById('dlg-ok').click()")
    ok(esperar("/não é um IFC/.test(" + recados + ")", 30), "o recado diz que não é um IFC")
    texto = aba.avaliar(recados)
    print("       recado:", texto)
    ok("O projeto não foi criado." in texto and texto.count("O projeto não foi criado.") == 1, "e que o projeto não foi criado (uma vez só)")
    aba.drenar(1.0)
    ok(slugs() == [], "nenhum projeto ficou na lista do servidor")
    ok(aba.avaliar("document.querySelectorAll('.cartao-sub').length") == 0, "nem na tela")

    print("C — o IFC cortado no meio")
    abrir_lista()
    escolher_ifc(CORTADO)
    ok(esperar(dialogo + " === 'Novo projeto a partir de IFC'", 10), "o diálogo do projeto novo abre")
    aba.avaliar("document.getElementById('dlg-ok').click()")
    ok(esperar(dialogo + " === 'O arquivo IFC está incompleto'", 60), "antes de abrir o 3D, o recado do IFC incompleto")
    ok("INCOMPLETO" in (aba.avaliar("document.getElementById('dlg-texto').textContent") or ""), "o texto diz o que houve")
    ok(aba.avaliar("document.getElementById('dlg-ok').textContent") == "Abrir assim mesmo", "o botão é \"Abrir assim mesmo\"")
    ok(aba.avaliar("location.pathname") == "/", "a tela ainda não saiu da lista")
    aba.avaliar("document.getElementById('dlg-cancelar').click()")
    ok(esperar("[...document.querySelectorAll('.cartao-sub')].some(x => /IFC INCOMPLETO/.test(x.textContent))", 15),
       "cancelando, fica na lista e o cartão diz IFC INCOMPLETO")
    ok(slugs() == ["cortado"], "o projeto do IFC cortado ficou (com o aviso)")

    print("D — o nome repetido")
    abrir_lista()
    for vez, confirma in ((1, False), (2, True)):
        aba.avaliar("document.querySelector('[data-acao=\"novo\"]').click()")
        ok(esperar(dialogo + " === 'Novo projeto de galpão'", 10), "o diálogo do galpão abre (vez %d)" % vez)
        aba.avaliar("(() => { const c = document.getElementById('dlg-nome'); c.value = 'CORTADO'; c.dispatchEvent(new Event('input', {bubbles: true})); })()")
        aba.avaliar("document.getElementById('dlg-ok').click()")
        ok(esperar(dialogo + " === 'Já existe um projeto com este nome'", 15), "a tela pergunta do nome repetido")
        ok("cortado" in (aba.avaliar("document.getElementById('dlg-texto').textContent") or "").lower(), "dizendo qual projeto já tem o nome")
        if not confirma:
            aba.avaliar("document.getElementById('dlg-cancelar').click()")
            aba.drenar(1.0)
            ok(slugs() == ["cortado"] and aba.avaliar("location.pathname") == "/", "cancelando, nada é criado")
        else:
            aba.avaliar("document.getElementById('dlg-ok').click()")
            ok(esperar("location.pathname !== '/'", 30), "confirmando, cria e abre o projeto")
            ok(slugs() == ["cortado", "cortado-2"], "o segundo projeto existe")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "400" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
