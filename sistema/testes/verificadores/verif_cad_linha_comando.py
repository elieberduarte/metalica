# -*- coding: utf-8 -*-
"""A linha de comando do CAD 2D (usuário, 24/10: "ter esse menu de comandos" + "stretch, array, divide"; DECISÃO: os
atalhos do AutoCAD; o Dividir com marca de ponto), com o teclado e o mouse de verdade (CDP):
  A. "tr" digitado no desenho vai para a caixa, a lista abre com "TR (TRIM)" — Aparar em cima; Enter abre o Aparar;
  B. os atalhos do AutoCAD: O + espaço = Offset, CO = Copiar, RO = Girar, S = Esticar, AR = Matriz, MI = Espelhar;
  C. o nome em português acha o comando ("apar" → Aparar); as setas escolhem outro da lista; o clique na lista executa;
  D. Enter (ou espaço) vazio no desenho repete o último comando; Esc fecha a lista;
  E. a medida continua indo para a ferramenta: Linha, o clique e "500" Enter → a linha de 500;
  F. DIV: a linha de 1000 em 4 → 3 marcas de ponto (cruz na AUXILIAR) a 250, 500 e 750; o clique pega a cruz inteira;
     o círculo em 6 → 6 marcas; Ctrl+Z desfaz o Dividir inteiro;
  G. a dica do botão mostra o atalho do AutoCAD (Offset: O)."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Circulo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_linha_comando_")
PASTA = os.path.join(DADOS, "obra-comandos")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra comandos", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Comandos", escala=10.0)
d.add(Linha(id="l1", a=(0, 0), b=(1000, 0)))
d.add(Circulo(id="c1", centro=(2000, 0), raio=200))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "comandos.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_linha_cmd_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CAPTURA = os.environ.get("VERIF_LINHA_COMANDO_CAPTURA")     # pasta para a imagem da lista (para mostrar ao usuário)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ const c = window.cad; {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.2)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def ev(tipo, x, y, botao="none", botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1)

    def mover(p):
        x, y = tela(p); ev("mouseMoved", x, y); aba.drenar(0.15)

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.3)

    COD = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), " ": (32, "Space"), "ArrowDown": (40, "ArrowDown"), "ArrowUp": (38, "ArrowUp")}

    def tecla(k, mods=0):
        code, nome = COD.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ("Digit" + k if k.isdigit() else k)))
        texto = "\r" if k == "Enter" else k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.08)

    def escrever(t):
        for ch in t: tecla(ch)
        aba.drenar(0.15)

    def comando(t, fim="Enter"):
        escrever(t); tecla(fim); aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape"); aba.drenar(0.1)

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    caixa = lambda: js("return [document.activeElement === c.el.medida, c.el.medida.value];")
    lista = lambda: js("const u = document.querySelector('.lista-comandos'); return u && !u.hidden ? [...u.querySelectorAll('li')].map(li => [li.querySelector('b').textContent, li.querySelector('span').textContent, li.className]) : [];")
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [e for e in (js(f"return c.doc.get('{i}');") for i in ids() - antes) if e]

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-comandos&desenho=comandos", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40), "o CAD abriu o desenho")
    js("c.tela.enquadrar([[-300, -600], [2600, 600]], 0.05); return 1;"); aba.drenar(0.3)
    aba.console.clear()

    # ------------------------------------------------------------------ A. TR
    escrever("tr")
    ok(caixa() == [True, "tr"], f"A. \"tr\" digitado no desenho vai para a caixa ({caixa()})")
    li = lista()
    ok(li and li[0][0] == "TR (TRIM)" and li[0][1].startswith("Aparar") and li[0][2] == "on", f"A. a lista abre com TR (TRIM) — Aparar em cima ({li[:3]})")
    if CAPTURA:
        import base64
        os.makedirs(CAPTURA, exist_ok=True)
        tecla("Escape"); escrever("l")
        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        open(os.path.join(CAPTURA, "linha-comando-L.png"), "wb").write(base64.b64decode(png))
        tecla("Escape"); escrever("tr")
    tecla("Enter"); aba.drenar(0.2)
    ok(ferr() == "aparar" and caixa() == [False, ""] and not lista(), f"A. Enter abre o Aparar e limpa a caixa ({ferr()})")
    esc()

    # ------------------------------------------------------------------ B. os atalhos do AutoCAD
    for t, alvo in [("o", "offset"), ("co", "copiar"), ("ro", "girar"), ("s", "esticar"), ("ar", "matriz"), ("mi", "espelhar"), ("e", "apagar"), ("x", "explodir")]:
        comando(t, " ")
        ok(ferr() == alvo, f"B. {t.upper()} + espaço = {alvo} ({ferr()})")
        esc()

    # ------------------------------------------------------------------ C. português, setas e clique
    comando("apar")
    ok(ferr() == "aparar", f"C. \"apar\" acha o Aparar ({ferr()})")
    esc()
    escrever("d")
    li = lista()
    tecla("ArrowDown")
    segundo = lista()[1][0] if len(lista()) > 1 else None
    tecla("Enter"); aba.drenar(0.2)
    ok(li and li[0][0].startswith("D") and ferr() != "cota" and segundo, f"C. a seta escolhe o 2º da lista ({segundo} → {ferr()})")
    esc()
    escrever("cha")
    js("document.querySelector('.lista-comandos li').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); return 1;"); aba.drenar(0.2)
    ok(ferr() == "chanfro", f"C. o clique na lista executa ({ferr()})")
    esc()

    # ------------------------------------------------------------------ D. repetir e Esc
    comando("o")
    esc()
    tecla("Enter"); aba.drenar(0.2)
    ok(ferr() == "offset", f"D. Enter vazio no desenho repete o último comando ({ferr()})")
    esc()
    escrever("ma")
    ok(len(lista()) >= 1, "D. a lista aberta")
    tecla("Escape"); aba.drenar(0.1)
    ok(not lista() and caixa() == [False, ""], "D. Esc fecha a lista e limpa a caixa")
    esc()

    # ------------------------------------------------------------------ E. a medida continua
    comando("l")
    ok(ferr() == "linha", f"E. L = Linha ({ferr()})")
    antes = ids()
    clique([0, 300]); mover([400, 300])
    comando("500")
    ls = [e for e in novas(antes) if e["tipo"] == "linha"]
    ok(len(ls) == 1 and abs(math.dist(ls[0]["a"], ls[0]["b"]) - 500) < 0.01, f"E. o clique e \"500\" Enter: a linha de 500 ({[round(math.dist(e['a'], e['b']), 1) for e in ls]})")
    esc()

    # ------------------------------------------------------------------ F. DIV
    js("c.selecionar(['l1']); return 1;")
    comando("div")
    ok(ferr() == "dividir", f"F. DIV abre o Dividir ({ferr()})")
    antes = ids()
    comando("4")
    m = novas(antes)
    meios = sorted(round((e["a"][0] + e["b"][0]) / 2) for e in m if abs(e["a"][1] - e["b"][1]) < 1e-9)
    ok(len(m) == 6 and all(e["camada"] == "AUXILIAR" for e in m) and meios == [250, 500, 750], f"F. a linha em 4: 3 marcas a 250, 500, 750 ({len(m)} linhas; {meios})")
    clique([2000 + 200, 0])
    antes = ids()
    comando("6")
    m6 = novas(antes)
    ok(len({(e.get("atributos") or {}).get("simbolo") for e in m6}) == 6, f"F. o círculo em 6: 6 marcas ({len(m6)} linhas)")
    tecla("z", 2)
    ok(not (ids() - antes), "F. Ctrl+Z desfaz o Dividir inteiro")
    esc()
    cruz = next(e for e in m if abs(e["a"][1] - e["b"][1]) < 1e-9 and round((e["a"][0] + e["b"][0]) / 2) == 500)
    js("c.tela.enquadrar([[460, -40], [540, 40]], 0.05); return 1;"); aba.drenar(0.3)
    clique([500, 12])                                     # no braço de cima da cruz (a linha dividida fica embaixo)
    sel = set(js("return [...c.tela.selecao];") or [])
    mesma = {e["id"] for e in m if (e.get("atributos") or {}).get("simbolo") == cruz["atributos"]["simbolo"]}
    ok(len(mesma) == 2 and sel == mesma, f"F. o clique na marca pega a cruz inteira ({len(sel)} de {len(mesma)})")

    # ------------------------------------------------------------------ G. a dica do botão
    titulo = js("return document.querySelector('[data-ferramenta=offset]').title;")
    ok(titulo and titulo.endswith("(O)"), f"G. a dica do botão mostra o atalho do AutoCAD ({titulo!r})")
    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
