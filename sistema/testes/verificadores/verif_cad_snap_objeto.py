# -*- coding: utf-8 -*-
"""O snap de objeto como no AutoCAD (usuário, 25/10, desenhando uma polilinha no SESI Chapecó: "ela não reconhece os nós
para se ligar, no autocad tem a ferramenta snap (F3) que pode habilitar e desabilitar isso, e configurar quais pontos de
snap o sistema quer buscar"), com o mouse e o teclado de verdade, em cada situação de SITUACOES (o desenho perto do zero e
o do SESI, em coordenadas UTM: x ≈ 1.218.181, y ≈ 211.836):
  A. a Polilinha em andamento: o cursor gruda no 1º vértice já marcado (extremidade) e no meio do 1º trecho; o clique
     fecha exatamente no vértice — o defeito: o snap só via o que já estava gravado no desenho;
  B. a Nuvem de revisão pelo contorno (P): o mesmo, no 1º ponto;
  C. F3 desliga o snap de objeto (a ponta da linha não gruda) e liga de novo; o botão SNAP do rodapé faz o mesmo;
  D. Quadrante: o ponto a 0° do círculo; desmarcado no menu do botão SNAP, deixa de valer;
  E. Centro geométrico: o centroide da área do triângulo fechado (não o centro da caixa);
  F. Nó: o centro da marca de ponto do Dividir; desligado, a cruz não dá interseção;
  G. Inserção: o ponto de inserção do texto;
  H. a escolha fica gravada: o F3 desligado continua desligado depois de abrir o desenho de novo."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Linha, Circulo, Polilinha, Texto

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# as formas de modelo em que o snap tem de valer (CLAUDE.md): perto do zero e longe dele (o SESI vem do PDF em UTM)
SITUACOES = [
    ("perto do zero", (0.0, 0.0)),
    ("coordenadas UTM (SESI Chapecó)", (1218181.0, 211836.0)),
]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_snap_objeto_")
PASTA = os.path.join(DADOS, "obra-snap")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra snap", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-25T00:00:00", "alterado": "2026-10-25T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
for i, (_, (ox, oy)) in enumerate(SITUACOES):
    P = lambda x, y: (ox + x, oy + y)
    d = Desenho(nome=f"Snap {i}", escala=1.0)
    d.add(Linha(id="h", a=P(0, 0), b=P(1000, 0)))
    d.add(Circulo(id="c", centro=P(2000, 0), raio=200))
    d.add(Polilinha(id="tri", vertices=[P(3000, 0), P(3900, 0), P(3000, 900)], fechada=True))
    pt = {"simbolo": "pt1", "simbolo_tipo": "ponto", "params": {}}
    d.add(Linha(id="no1", camada="AUXILIAR", a=P(4498.5, 0), b=P(4501.5, 0), atributos=dict(pt)))
    d.add(Linha(id="no2", camada="AUXILIAR", a=P(4500, -1.5), b=P(4500, 1.5), atributos=dict(pt)))
    d.add(Texto(id="tx", posicao=P(5000, 0), texto="ABC", altura=2.5))
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", f"snap{i}.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_snap_objeto_")
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

    def tecla(k):
        cod = {"Enter": 13, "Escape": 27, "F3": 114, "F9": 120}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" else (k if len(k) == 1 else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=k if k.startswith("F") and len(k) > 1 else ("Key" + k.upper() if len(k) == 1 else k),
                windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod)
        aba.drenar(0.1)

    def esc():
        tecla("Escape"); tecla("Escape")

    def clicar_elemento(seletor):
        r = js(f"const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2];")
        if not r: return False
        ev("mouseMoved", *r); ev("mousePressed", *r, "left", 1); ev("mouseReleased", *r, "left", 0)
        aba.drenar(0.25)
        return True

    snap = lambda: js("return c.tela.snap ? { tipo: c.tela.snap.tipo, ponto: c.tela.snap.ponto, rotulo: c.tela.snap.rotulo } : null;")
    perto = lambda a, b, tol=1e-6: a is not None and b is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol
    botao_on = lambda: js("const b = document.querySelector('#barra-snap button'); return b ? b.classList.contains('on') : null;")

    for i, (nome, (ox, oy)) in enumerate(SITUACOES):
        P = lambda x, y: [ox + x, oy + y]
        print(f"\n== {nome}")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-snap&desenho=snap{i}", limite=60)
        ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 6", 40), "o CAD abriu o desenho")
        js(f"c.tela.enquadrar([[{ox - 300}, {oy - 900}], [{ox + 5500}, {oy + 6000}]], 0.02); return 1;"); aba.drenar(0.3)
        mm_px = js("return c.tela.mmPorPixel;")
        aba.console.clear()

        def tela(p):
            return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

        def mover(p, dx=2, dy=1, pausa=0.15):
            x, y = tela(p); ev("mouseMoved", x + dx, y + dy); aba.drenar(pausa)

        def clique(p, dx=0, dy=0):
            x, y = tela(p); x += dx; y += dy
            ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
            aba.drenar(0.25)

        # ------------------------------------------------------------------ A. a polilinha em andamento
        comando(aba, "pl")
        for q in (P(0, 3000), P(800, 3000), P(800, 3600)): clique(q)
        v0, v1 = js("return c.ferramenta.pontos.slice(0, 2);")         # o clique no vazio grava o ponto do pixel
        mover(P(0, 3000), 3, 2)
        s = snap()
        ok(s and s["tipo"] == "extremidade" and perto(s["ponto"], v0), f"A. o cursor gruda no 1º vértice da polilinha em andamento ({s}, vértice {v0})")
        clique(P(0, 3000), 3, 2)
        mover(P(400, 3000), 3, 3)
        s = snap()
        meio = [(v0[0] + v1[0]) / 2, (v0[1] + v1[1]) / 2]
        ok(s and s["tipo"] == "meio" and perto(s["ponto"], meio), f"A. e no meio do 1º trecho ({s})")
        tecla("Enter"); aba.drenar(0.3)
        pl = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && e.vertices.length === 4).map(e => e.vertices);")
        ok(pl and len(pl) == 1 and perto(pl[0][3], v0, 1e-9), f"A. a polilinha fecha exatamente no 1º vértice ({pl and pl[0][3]})")
        esc()

        # ------------------------------------------------------------------ B. a nuvem pelo contorno
        comando(aba, "nr"); tecla("p")
        for q in (P(0, 5000), P(600, 5000), P(600, 5500)): clique(q)
        n0 = js("return c.ferramenta.pts[0];")
        mover(P(0, 5000), 3, 2)
        s = snap()
        ok(s and s["tipo"] == "extremidade" and perto(s["ponto"], n0), f"B. a nuvem pelo contorno: o 1º ponto ({s})")
        esc()

        # ------------------------------------------------------------------ C. F3 e o botão SNAP
        comando(aba, "l")
        mover(P(1000, 0))
        s = snap()
        ok(s and s["tipo"] == "extremidade" and perto(s["ponto"], P(1000, 0)), f"C. com o snap ligado, a ponta da linha ({s})")
        tecla("F3"); mover(P(1000, 0), 2, 2)
        s = snap()
        ok(js("return c.snap.objeto;") is False and botao_on() is False and not (s and perto(s["ponto"], P(1000, 0))), f"C. F3 desliga: a ponta não gruda ({s})")
        tecla("F3"); mover(P(1000, 0))
        s = snap()
        ok(js("return c.snap.objeto;") is True and botao_on() is True and s and s["tipo"] == "extremidade", f"C. F3 liga de novo ({s})")
        ok(clicar_elemento("#barra-snap button") and js("return c.snap.objeto;") is False, "C. o botão SNAP do rodapé desliga")
        ok(clicar_elemento("#barra-snap button") and js("return c.snap.objeto;") is True, "C. e liga")
        esc()

        # ------------------------------------------------------------------ D. quadrante (e o menu do botão)
        comando(aba, "l")
        mover(P(2200, 0), 3, -2)
        s = snap()
        ok(s and s["tipo"] == "quadrante" and perto(s["ponto"], P(2200, 0)), f"D. o quadrante a 0° do círculo ({s})")
        ok(clicar_elemento("#barra-snap button.seta") and js("return !document.querySelector('#barra-snap .menu-snap').hidden;"), "D. a setinha abre a lista dos pontos")
        ok(clicar_elemento("#barra-snap input[data-snap=quadrante]") and js("return c.snap.ativos.quadrante;") is False, "D. desmarcar o Quadrante no menu")
        mover(P(2200, 0), 3, -2)
        s = snap()
        ok(not (s and s["tipo"] == "quadrante"), f"D. desmarcado, o quadrante não vale ({s and s['tipo']})")
        clicar_elemento("#barra-snap input[data-snap=quadrante]")
        ok(js("return c.snap.ativos.quadrante;") is True, "D. marcado de novo")
        clique(P(2500, -700))                                   # fora: o menu fecha
        ok(js("return document.querySelector('#barra-snap .menu-snap').hidden;"), "D. o clique fora fecha o menu")
        esc()

        # ------------------------------------------------------------------ E. centro geométrico
        comando(aba, "l")
        mover(P(3300, 300), 3, 2)
        s = snap()
        ok(s and s["tipo"] == "centro_geometrico" and perto(s["ponto"], P(3300, 300), 1e-3), f"E. o centroide do triângulo, não o centro da caixa ({s})")
        esc()

        # ------------------------------------------------------------------ F. nó
        comando(aba, "l")
        mover(P(4500, 0), 3, 2)
        s = snap()
        ok(s and s["tipo"] == "no" and perto(s["ponto"], P(4500, 0)), f"F. o nó da marca de ponto ({s})")
        js("c.definirSnap({ ativos: { no: false } }); return 1;")
        mover(P(4500, 0), 2, 3)
        s = snap()
        ok(not (s and s["tipo"] in ("no", "interseccao", "extremidade")), f"F. com o Nó desligado a cruz não dá ponto ({s and s['tipo']})")
        js("c.definirSnap({ ativos: { no: true } }); return 1;")
        esc()

        # ------------------------------------------------------------------ G. inserção do texto
        comando(aba, "l")
        mover(P(5000, 0), 3, 2)
        s = snap()
        ok(s and s["tipo"] == "insercao" and perto(s["ponto"], P(5000, 0)), f"G. a inserção do texto ({s})")
        esc()

        # ------------------------------------------------------------------ H. fica gravado
        tecla("F3")
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-snap&desenho=snap{i}", limite=60)
        esperar("document.body.dataset.pronto === '1' && window.cad", 40)
        ok(js("return c.snap.objeto;") is False and botao_on() is False, "H. o F3 desligado continua desligado ao abrir de novo")
        tecla("F3")
        ok(js("return c.snap.objeto;") is True, "H. ligado de novo")

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
