# -*- coding: utf-8 -*-
"""O tipo e o tamanho da ponta da cota (usuário, 26/10, ME Sooro, na ponta de uma cota da T1: "como faço para trocar o
tipo e tamanho dos arrowheads?" — o DIMBLK e a DIMASZ do AutoCAD), com o mouse e o teclado de verdade, em cada situação
de SITUACOES (perto do zero, em UTM como o SESI, e o desenho em 1:20):
  A. a cota selecionada mostra no painel "Terminador" e "Tamanho da seta (mm)", vazios (= os do desenho);
  B. o tamanho digitado no painel vai para a cota e a ponta desenhada na tela fica desse tamanho (mm de papel);
     o terminador trocado no painel muda a ponta; Ctrl+Z volta o tamanho;
  C. Estilos do desenho › "Tamanho da ponta das cotas", no desenho todo: vira o do desenho (metadados.estilo.seta) e a
     cota sem tamanho próprio segue ele; a que tem o dela fica com o dela;
  D. gravar e abrir de novo: continua."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Cota

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (nome, origem, escala do desenho, tamanho do modelo): as formas de modelo em que a ponta tem de valer (CLAUDE.md)
SITUACOES = [
    ("perto do zero, 1:1", (0.0, 0.0), 1.0, 1.0),
    ("coordenadas UTM (SESI Chapecó), 1:1", (1218181.0, 211836.0), 1.0, 1.0),
    ("desenho 1:20, longe do zero", (50000.0, -30000.0), 20.0, 20.0),
]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ponta_cota_")
PASTA = os.path.join(DADOS, "obra-ponta")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra ponta", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-09T00:00:00", "alterado": "2026-11-09T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
for i, (_, (ox, oy), esc, s) in enumerate(SITUACOES):
    P = lambda x, y: (ox + x * s, oy + y * s)
    d = Desenho(nome=f"Ponta {i}", escala=esc)
    d.add(Cota(id="c1", p1=P(0, 0), p2=P(700, 0), modo="h", deslocamento=-10.0, altura=2.5))
    d.add(Cota(id="c2", p1=P(0, 300), p2=P(700, 300), modo="h", deslocamento=-10.0, altura=2.5))
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", f"ponta{i}.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ponta_cota_")
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

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.2)
        return False

    def ev(tipo, x, y, botao="none", botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1)

    def tecla(k, cod, mods=0, texto=""):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=k, windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.12)

    def clicar_elemento(seletor):
        r = js(f"const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; b.scrollIntoView({{ block: 'center' }}); const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2];")
        if not r: return False
        ev("mouseMoved", *r); ev("mousePressed", *r, "left", 1); ev("mouseReleased", *r, "left", 0)
        aba.drenar(0.3)
        return True

    def digitar_no_campo(seletor, texto):
        """clica no campo, apaga o que tem, digita e sai com Tab (o change do campo)"""
        if not clicar_elemento(seletor): return False
        tecla("a", 65, mods=2)                                    # Ctrl+A
        tecla("Delete", 46)
        aba.cmd("Input.insertText", text=texto); aba.drenar(0.1)
        tecla("Tab", 9)
        aba.drenar(0.3)
        return True

    def gravar():
        for _ in range(20):
            if js("return !c._editado && !c._salvando;"): return True
            js("return c.salvar({ avisar: false }), 1;"); aba.drenar(0.5)
        return False

    def pontas(id_):
        """as pontas que a tela desenha para a cota `id_`, em mm de papel (o tamanho em pixels ÷ pixels por mm ÷ escala)"""
        return js("""const t = c.tela, k = c.doc.escala || 1, reg = [];
            const orig = t._terminador; t._terminador = function (ctx, p, ang, tam, tipo) { reg.push([tam, tipo]); return orig.apply(this, arguments); };
            try { const ctx = t.ctx || t.canvas.getContext('2d'); t._cota(ctx, c.doc.get(%s), k, '#000'); } finally { t._terminador = orig; }
            return reg.map(([tam, tipo]) => [Math.round(tam / t.vp.z / k * 1000) / 1000, tipo]);""" % json.dumps(id_))

    for i, (nome, (ox, oy), esc_d, s) in enumerate(SITUACOES):
        P = lambda x, y: [ox + x * s, oy + y * s]
        print(f"\n== {nome}")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-ponta&desenho=ponta{i}", limite=60)
        ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40), "o CAD abriu o desenho")
        js(f"c.tela.enquadrar([{json.dumps(P(-100, -200))}, {json.dumps(P(800, 400))}], 0.05); return 1;"); aba.drenar(0.3)
        aba.console.clear()

        # ------------------------------------------------------------------ A. o painel
        js("c.selecionar(['c1']); return 1;"); aba.drenar(0.4)
        r = js("""const t = document.querySelector('select[name=terminador]'), s = document.querySelector('input[name=seta]');
            return t && s ? { t: t.value, s: s.value, ph: s.placeholder, op: [...t.options].map(o => o.textContent) } : null;""")
        ok(r is not None and r["t"] == "" and r["s"] == "", f"A. o painel da cota tem Terminador e Tamanho da seta, vazios = os do desenho ({r})")
        ok(pontas("c1") == [[2.5, "traco"], [2.5, "traco"]], f"A. sem escolha, o traço de 2,5 mm de antes ({pontas('c1')})")

        # ------------------------------------------------------------------ B. o tamanho e o tipo pelo painel
        digitar_no_campo("input[name=seta]", "4")
        ok(js("return c.doc.get('c1').seta;") == 4, f"B. o tamanho digitado vai para a cota ({js('return c.doc.get(\"c1\").seta;')})")
        ok(pontas("c1") == [[4, "traco"], [4, "traco"]], f"B. a ponta desenhada fica com 4 mm ({pontas('c1')})")
        ok(js("return c.doc.get('c2').seta;") is None, "B. a outra cota não muda")
        js("c.selecionar(['c1']); return 1;"); aba.drenar(0.3)
        js("const t = document.querySelector('select[name=terminador]'); t.value = 'seta'; t.dispatchEvent(new Event('change', { bubbles: true })); return 1;")
        aba.drenar(0.3)
        ok(js("return c.doc.get('c1').terminador;") == "seta" and pontas("c1") == [[4, "seta"], [4, "seta"]],
           f"B. o terminador trocado no painel muda a ponta ({pontas('c1')})")
        js("c.desfazer(); c.desfazer(); return 1;"); aba.drenar(0.3)
        ok(js("return [c.doc.get('c1').seta ?? null, c.doc.get('c1').terminador ?? null];") == [None, None], "B. Ctrl+Z volta o tipo e o tamanho")

        # ------------------------------------------------------------------ C. Estilos do desenho
        js("c.selecionar(['c2']); return 1;"); aba.drenar(0.3)
        digitar_no_campo("input[name=seta]", "3")               # a c2 com o tamanho dela
        js("c.selecionar([]); c.dialogoEstilos(); return 1;"); aba.drenar(0.5)
        ok(digitar_no_campo("dialog[open] input[name=seta]", "5"), "C. o Estilos do desenho tem o tamanho da ponta")
        clicar_elemento("dialog[open] .botao-ok"); aba.drenar(0.4)
        ok(js("return (c.doc.metadados.estilo || {}).seta;") == 5, "C. vira o tamanho do desenho (estilo.seta = 5)")
        ok(pontas("c1") == [[5, "traco"], [5, "traco"]], f"C. a cota sem tamanho próprio segue o do desenho ({pontas('c1')})")
        # no desenho todo as cotas voltam a seguir o estilo (como a folga): a c2 perde o dela
        ok(js("return c.doc.get('c2').seta ?? null;") is None and pontas("c2") == [[5, "traco"], [5, "traco"]],
           f"C. no desenho todo, as cotas voltam a seguir o do desenho ({pontas('c2')})")
        js("c.selecionar(['c2']); return 1;"); aba.drenar(0.3)
        digitar_no_campo("input[name=seta]", "1,5")
        ok(js("return c.doc.get('c2').seta;") == 1.5 and pontas("c2") == [[1.5, "traco"], [1.5, "traco"]],
           f"C. depois, a cota com o dela fica com o dela ({pontas('c2')})")

        # ------------------------------------------------------------------ D. gravar e abrir de novo
        ok(gravar(), "D. gravado")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-ponta&desenho=ponta{i}", limite=60)
        esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40)
        ok(js("return [(c.doc.metadados.estilo || {}).seta, c.doc.get('c2').seta];") == [5, 1.5], "D. aberto de novo, continua")
        erros = [m for m in aba.console if m[0] in ("error", "excecao") and "beforeunload' confirmation panel" not in m[1]]
        ok(not erros, "sem erro no console" + (": %s" % erros[:3] if erros else ""))
finally:
    for p in (nav, srv):
        try:
            p.kill()
        except Exception:                                         # noqa: BLE001
            pass
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
