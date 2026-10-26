# -*- coding: utf-8 -*-
"""A seta a mais na chamada (usuário, 26/10, ME Sooro, na chamada "CH3": "criar essa opção de puxar mais de uma seta da
mesma linha de chamada" — o MLEADEREDIT › Adicionar do AutoCAD), com o mouse e o teclado de verdade, em cada situação de
SITUACOES (perto do zero, em UTM como o SESI, e o desenho em 1:20):
  A. MLE + espaço abre a ferramenta; o clique fora de chamada não faz nada;
  B. o clique na linha da chamada marca de onde a seta sai (o meio da linha → de ≈ 0,5); o clique seguinte põe a seta
     com a ponta ali; o outro clique põe mais uma, do mesmo ponto; Enter termina;
  C. Ctrl+Z tira a última seta posta;
  D. o clique na seta a mais seleciona a chamada; a alça da ponta dela leva a ponta (o ponto de onde sai não muda);
  E. Mover (M) leva a chamada com as setas a mais;
  F. o painel: "− última" e "só uma" tiram as setas a mais; "+ seta" abre a ferramenta;
  G. gravar e abrir de novo: as setas a mais continuam."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Chamada, Linha

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (nome, origem, escala do desenho, tamanho do modelo): as formas de modelo em que a seta tem de valer (CLAUDE.md)
SITUACOES = [
    ("perto do zero, 1:1", (0.0, 0.0), 1.0, 1.0),
    ("coordenadas UTM (SESI Chapecó), 1:1", (1218181.0, 211836.0), 1.0, 1.0),
    ("desenho 1:20, longe do zero", (50000.0, -30000.0), 20.0, 20.0),
]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_seta_chamada_")
PASTA = os.path.join(DADOS, "obra-seta")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra seta", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-26T00:00:00", "alterado": "2026-10-26T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
for i, (_, (ox, oy), esc, s) in enumerate(SITUACOES):
    P = lambda x, y: (ox + x * s, oy + y * s)
    d = Desenho(nome=f"Seta {i}", escala=esc)
    d.add(Chamada(id="ch3", alvo=P(1000, 0), posicao=P(0, 1000), texto="CH3", altura=2.5))
    d.add(Linha(id="banzo", a=P(-500, -600), b=P(2500, -600)))
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", f"seta{i}.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_seta_chamada_")
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

    def tecla(k, mods=0):
        cod = {"Enter": 13, "Escape": 27}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" and not mods else (k if len(k) == 1 and not mods else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 and k.isalpha() else k,
                windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.12)

    def esc():
        tecla("Escape"); tecla("Escape")

    def clicar_elemento(seletor):
        r = js(f"const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2];")
        if not r: return False
        ev("mouseMoved", *r); ev("mousePressed", *r, "left", 1); ev("mouseReleased", *r, "left", 0)
        aba.drenar(0.3)
        return True

    def gravar():
        """grava até não sobrar edição (a gravação automática pode estar no meio)"""
        for _ in range(20):
            if js("return !c._editado && !c._salvando;"): return True
            js("return c.salvar({ avisar: false }), 1;"); aba.drenar(0.5)
        return False

    ramos = lambda: js("const e = c.doc.get('ch3'); return e ? (e.ramos || []) : null;")
    perto = lambda a, b, tol: a is not None and b is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    for i, (nome, (ox, oy), esc_d, s) in enumerate(SITUACOES):
        P = lambda x, y: [ox + x * s, oy + y * s]
        print(f"\n== {nome}")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-seta&desenho=seta{i}", limite=60)
        ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40), "o CAD abriu o desenho")
        lo, hi = P(-800, -1200), P(2800, 1600)
        js(f"c.tela.enquadrar([{json.dumps(lo)}, {json.dumps(hi)}], 0.02); return 1;"); aba.drenar(0.3)
        tol = 3 * js("return c.tela.mmPorPixel;")        # o clique no vazio grava o ponto do pixel
        aba.console.clear()

        def tela(p):
            return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

        def clique(p):
            x, y = tela(p)
            ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
            aba.drenar(0.25)

        # ------------------------------------------------------------------ A. abrir
        esc()
        comando(aba, "mle")
        ok(js("return c.ferramenta.constructor.id;") == "seta_chamada", "A. MLE abre a Seta a mais na chamada")
        clique(P(2000, 1200))
        ok(ramos() == [] and js("return c.ferramenta.chamada;") is None, "A. o clique longe da chamada não marca nada")

        # ------------------------------------------------------------------ B. duas setas do mesmo ponto
        clique(P(500, 500))
        de = js("return c.ferramenta.de;")
        ok(js("return c.ferramenta.chamada;") == "ch3" and de is not None and abs(de - 0.5) < 0.02, f"B. o clique na linha marca a chamada e o ponto de onde sai (de = {de})")
        clique(P(900, -300))
        r = ramos()
        ok(len(r) == 1 and perto(r[0]["alvo"], P(900, -300), tol) and abs(r[0]["de"] - de) < 1e-9, f"B. a seta nova com a ponta no clique ({r})")
        clique(P(300, -300))
        r = ramos()
        ok(len(r) == 2 and perto(r[1]["alvo"], P(300, -300), tol) and r[1]["de"] == r[0]["de"], f"B. outra seta do mesmo ponto ({len(r)} setas a mais)")
        tecla("Enter")
        ok(js("return c.ferramenta.chamada;") is None, "B. Enter termina (a ferramenta volta a pedir a chamada)")

        # ------------------------------------------------------------------ C. Ctrl+Z
        tecla("z", 2)
        ok(len(ramos()) == 1, f"C. Ctrl+Z tira a última seta posta ({len(ramos())} ficou)")

        # ------------------------------------------------------------------ D. a seta a mais seleciona e a alça leva a ponta
        esc(); js("c.selecionar([]); return 1;")
        clique(P(700, 100))          # no meio da seta a mais: de (500, 500) a (900, -300)
        ok(js("return [...c.tela.selecao];") == ["ch3"], f"D. o clique na seta a mais seleciona a chamada ({js('return [...c.tela.selecao];')})")
        clique(P(900, -300))         # a alça da ponta (pega)
        clique(P(1100, -400))        # e solta
        r = ramos()
        ok(len(r) == 1 and perto(r[0]["alvo"], P(1100, -400), tol) and abs(r[0]["de"] - de) < 1e-9, f"D. a alça leva a ponta da seta a mais ({r})")

        # ------------------------------------------------------------------ E. Mover leva junto
        esc(); js("c.selecionar(['ch3']); return 1;")
        antes = ramos()[0]["alvo"]
        comando(aba, "m")
        clique(P(0, 0)); clique(P(200, 100))
        esc()
        depois = ramos()[0]["alvo"]
        ok(perto([depois[0] - antes[0], depois[1] - antes[1]], [200 * s, 100 * s], 2 * tol), f"E. o Mover leva a seta a mais junto ({antes} → {depois})")

        # ------------------------------------------------------------------ F. o painel
        js("c.selecionar(['ch3']); return 1;"); aba.drenar(0.3)
        ok(clicar_elemento(".setas-chamada button:nth-of-type(1)") and js("return c.ferramenta.constructor.id;") == "seta_chamada", "F. \"+ seta\" abre a ferramenta")
        # mais uma, saindo de outro ponto: a linha agora vai de (1200, 100) a (200, 1100) — (900, 400) é o de ≈ 0,3
        clique(P(900, 400)); clique(P(-300, 300)); tecla("Enter")
        r = ramos()
        ok(len(r) == 2 and abs(r[1]["de"] - 0.3) < 0.02, f"F. mais uma seta pelo painel, de outro ponto da linha ({r[-1:]})")
        esc(); js("c.selecionar(['ch3']); return 1;"); aba.drenar(0.3)
        ok(clicar_elemento(".setas-chamada button:nth-of-type(2)") and len(ramos()) == 1, "F. \"− última\" tira a última")

        # ------------------------------------------------------------------ G. gravar e abrir de novo
        esc()
        gravadas = ramos()
        ok(gravar(), f"G. gravado ({js('return c.el.estadoSalvo.textContent;')})")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-seta&desenho=seta{i}", limite=60)
        ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40), "G. abriu de novo")
        ok(ramos() == gravadas and len(gravadas) == 1, f"G. a seta a mais continua depois de gravar ({ramos()})")
        js("c.selecionar(['ch3']); return 1;"); aba.drenar(0.3)
        ok(clicar_elemento(".setas-chamada button:nth-of-type(3)") and ramos() == [], "F. \"só uma\" deixa só a seta principal")
        gravar()                     # sem edição pendente: o "sair sem gravar?" travava a próxima situação

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
