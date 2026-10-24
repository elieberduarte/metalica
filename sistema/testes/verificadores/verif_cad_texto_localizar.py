# -*- coding: utf-8 -*-
"""O texto de várias linhas e o localizar e substituir do CAD 2D (24/10, a lista das ferramentas que faltam), com o
teclado e o mouse de verdade:
  A. MT (MTEXT): o clique e o texto de 3 linhas na caixa (Ctrl+Enter grava) → um texto só, com as linhas;
  B. o clique na 3ª linha pega o texto (a caixa de clique cobre as linhas);
  C. o duplo clique edita numa caixa de várias linhas: Enter quebra a linha, Ctrl+Enter grava;
  D. o DXF sai com MTEXT (as linhas pelo \\P) e o PDF sai;
  E. Ctrl+H: "T1" com palavra inteira acha o texto, a chamada e a cota escrita (não o "T10"); o clique na lista
     seleciona; "Substituir todos" por "T2" troca, a camada travada fica, e um Ctrl+Z volta tudo;
  F. maiúsculas e minúsculas: "t1" acha sem a opção e não acha com ela."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Texto, Chamada, Cota, Camada2D

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_texto_")
PASTA = os.path.join(DADOS, "obra-texto")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra texto", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Texto", escala=1.0)
d.camadas["ARQ"] = Camada2D("ARQ", "#888888", bloqueada=True)
d.add(Texto(id="t1", camada="TEXTO", posicao=(0, 300), texto="T1", altura=2.5))
d.add(Texto(id="t1b", camada="TEXTO", posicao=(0, 320), texto="T1 - TESOURA", altura=2.5))
d.add(Texto(id="t10", camada="TEXTO", posicao=(0, 340), texto="T10", altura=2.5))
d.add(Texto(id="tarq", camada="ARQ", posicao=(0, 360), texto="T1", altura=2.5))
d.add(Chamada(id="ch", camada="TEXTO", alvo=(50, 250), posicao=(80, 270), texto="VER T1", altura=2.5))
d.add(Cota(id="ct", camada="COTA", p1=(0, 200), p2=(100, 200), texto="T1", altura=2.5))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "texto.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_texto_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def esperar(cond, limite=20.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.2)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def ev(tipo, x, y, botao="none", botoes=0, n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=n)

    def clique(p, n=1):
        x, y = tela(p)
        ev("mouseMoved", x, y)
        for i in range(1, n + 1):
            ev("mousePressed", x, y, "left", 1, i); ev("mouseReleased", x, y, "left", 0, i)
        aba.drenar(0.3)

    def tecla(k, mods=0):
        cod = {"Enter": 13, "Escape": 27}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" and not mods else (k if len(k) == 1 and not mods else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 else k, windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.12)

    def esc():
        tecla("Escape"); tecla("Escape")

    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [e for e in (js(f"return c.doc.get('{i}');") for i in ids() - antes) if e]
    texto_de = lambda i: js(f"return c.doc.get('{i}').texto;")

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-texto&desenho=texto", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 6", 40), "o CAD abriu o desenho")
    js("c.tela.enquadrar([[-20, -40], [200, 120]], 0.02); return 1;"); aba.drenar(0.3)
    aba.console.clear()

    # ------------------------------------------------------------------ A. MT
    comando(aba, "mt")
    ok(js("return c.ferramenta.constructor.id;") == "texto_mt", "A. MT abre o Texto de várias linhas")
    antes = ids()
    clique([10, 100])
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo textarea')"), "A. a caixa de várias linhas abre")
    js("document.querySelector('#dialogo-corpo textarea').focus(); return 1;")
    aba.cmd("Input.insertText", text="LINHA 1")
    tecla("Enter")
    aba.cmd("Input.insertText", text="LINHA 2")
    tecla("Enter")
    aba.cmd("Input.insertText", text="LINHA 3 MAIS COMPRIDA")
    ok(js("return document.querySelector('#dialogo').open;"), "A. Enter na caixa quebra a linha (não grava)")
    tecla("Enter", 2)
    aba.drenar(0.3)
    nv = [e for e in novas(antes) if e["tipo"] == "texto"]
    ok(len(nv) == 1 and nv[0]["texto"] == "LINHA 1\nLINHA 2\nLINHA 3 MAIS COMPRIDA" and nv[0]["vertical"] == "topo",
       f"A. Ctrl+Enter grava um texto só com as 3 linhas ({[e['texto'] for e in nv]})")
    mt = nv[0]["id"] if nv else None
    esc()

    # ------------------------------------------------------------------ B. o clique na 3ª linha
    h = 2.5
    clique([14, 100 - 2 * 1.6 * h - h / 2])
    ok(js("return [...c.tela.selecao];") == [mt], f"B. o clique na 3ª linha pega o texto ({js('return [...c.tela.selecao];')})")

    # ------------------------------------------------------------------ C. a edição no lugar
    clique([14, 100 - h / 2], 2)
    ok(esperar("document.querySelector('.editar-texto-no-lugar') && document.querySelector('.editar-texto-no-lugar').tagName === 'TEXTAREA'", 5),
       "C. o duplo clique abre a caixa de várias linhas")
    js("const t = document.querySelector('.editar-texto-no-lugar'); t.focus(); t.selectionStart = t.selectionEnd = t.value.length; return 1;")
    tecla("Enter")
    aba.cmd("Input.insertText", text="LINHA 4")
    ok(js("return !!document.querySelector('.editar-texto-no-lugar');"), "C. Enter quebra a linha (a caixa continua)")
    tecla("Enter", 2)
    aba.drenar(0.2)
    ok(texto_de(mt) == "LINHA 1\nLINHA 2\nLINHA 3 MAIS COMPRIDA\nLINHA 4", f"C. Ctrl+Enter grava a 4ª linha ({texto_de(mt)!r})")
    esc()

    # ------------------------------------------------------------------ D. DXF e PDF
    import ezdxf
    from nucleo2d import dxf_cad, pranchas
    dd = Desenho.de_dict(js("return c.doc.paraJSON();"))
    tmp = tempfile.mkdtemp(prefix="texto_saida_")
    doc = ezdxf.readfile(dxf_cad.exportar(dd, os.path.join(tmp, "t.dxf")))
    mts = [m.text for m in doc.modelspace().query("MTEXT")]
    ok(any("LINHA 1\\PLINHA 2" in t for t in mts), f"D. o DXF com o MTEXT ({mts})")
    pdf = pranchas.pdf_da_area(dd, os.path.join(tmp, "t.pdf"), ((-20, -40), (200, 400)), 1)
    ok(os.path.getsize(pdf) > 1000, "D. o PDF sai")

    # ------------------------------------------------------------------ E. localizar e substituir
    tecla("h", 2)
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo [data-campo=busca]')"), "E. Ctrl+H abre o Localizar e substituir")
    js("const b = document.querySelector('#dialogo-corpo [data-campo=busca]'); b.focus(); b.select(); return 1;")
    aba.cmd("Input.insertText", text="T1")
    js("const p = document.querySelector('#dialogo-corpo [data-campo=palavra]'); p.click(); return 1;")
    achou = set(js("return [...document.querySelectorAll('#dialogo-corpo [data-campo=resultados] [data-id]')].map(b => b.dataset.id);") or [])
    ok(achou == {"t1", "t1b", "tarq", "ch", "ct"}, f"E. palavra inteira: o texto, a chamada e a cota escrita, não o T10 ({sorted(achou)})")
    js("document.querySelector('#dialogo-corpo [data-id=ch]').click(); return 1;")
    ok(js("return [...c.tela.selecao];") == ["ch"], "E. o clique na lista seleciona")
    js("const t = document.querySelector('#dialogo-corpo [data-campo=troca]'); t.focus(); return 1;")
    aba.cmd("Input.insertText", text="T2")
    tecla("Enter")
    aba.drenar(0.3)
    textos = {i: texto_de(i) for i in ("t1", "t1b", "t10", "tarq", "ch", "ct")}
    ok(textos == {"t1": "T2", "t1b": "T2 - TESOURA", "t10": "T10", "tarq": "T1", "ch": "VER T2", "ct": "T2"},
       f"E. Substituir todos: troca, o T10 e a camada travada ficam ({textos})")
    ok(esperar("[...document.querySelectorAll('#avisos .aviso')].some(a => /camada travada/.test(a.textContent))", 5), "E. o aviso diz o que ficou na camada travada")
    tecla("z", 2)
    ok({i: texto_de(i) for i in ("t1", "t1b", "ch", "ct")} == {"t1": "T1", "t1b": "T1 - TESOURA", "ch": "VER T1", "ct": "T1"}, "E. um Ctrl+Z volta tudo")

    # ------------------------------------------------------------------ F. maiúsculas
    js("return c.dialogoLocalizar(), 1;")
    esperar("document.querySelector('#dialogo').open")
    js("const b = document.querySelector('#dialogo-corpo [data-campo=busca]'); b.value = 't1'; b.dispatchEvent(new Event('input')); return 1;")
    n1 = js("return document.querySelectorAll('#dialogo-corpo [data-campo=resultados] [data-id]').length;")
    js("document.querySelector('#dialogo-corpo [data-campo=maiusculas]').click(); return 1;")
    n2 = js("return document.querySelectorAll('#dialogo-corpo [data-campo=resultados] [data-id]').length;")
    ok(n1 >= 5 and n2 == 0, f"F. \"t1\": acha sem a opção ({n1}) e não acha com ela ({n2})")
    tecla("Escape")
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
