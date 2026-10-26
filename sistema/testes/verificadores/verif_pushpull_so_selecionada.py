# -*- coding: utf-8 -*-
"""Empurrar/Puxar com peça selecionada só enxerga ela (usuário, 26/10/2026, no OrtoBio: "a ferramenta puxar está
interagindo com outras peças diferentes da que está selecionada, preciso que quando uma peça estiver selecionada ele
interaja apenas com ela" — a VIGA RETANGULAR de concreto selecionada; parado sobre ela, o destaque era o da barra L do
lado, e no arrasto o snap "Sobre aresta" grudava na peça vizinha).

Mouse e teclado de verdade (Chrome sem janela), vista iso: a viga (sólido) selecionada, uma barra U passando por cima
dela (na frente, na tela) e uma peça vizinha mais alta ao lado.
  A. com a viga selecionada, o cursor sobre a barra que passa na frente: o destaque e o clique são da viga;
  B. no arrasto, o cursor no canto da vizinha: o snap não gruda nela;
  C. o clique na vizinha (fora da seleção) não começa nada;
  D. sem seleção, tudo como antes: a barra da frente estica;
  E. trocando de ferramenta, o snap volta a enxergar tudo;
  F. depois de cancelar (Esc, Esc), o clique seleciona a viga de novo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_pp_sel_")
PASTA = os.path.join(DADOS, "ps")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Puxar seleção", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-26T00:00:00", "alterado": "2026-10-26T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
json.dump(Documento().dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pp_sel_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ps", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('pushpull'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    ids = json.loads(aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento, cena = ed.cena;
      const caixa = (nome, x0, x1, z1) => {
        const V = [[x0,0,0],[x1,0,0],[x1,7000,0],[x0,7000,0],[x0,0,z1],[x1,0,z1],[x1,7000,z1],[x0,7000,z1]];
        const F = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
        return doc.add({ tipo: 'solido', nome, camada: 'Estrutura', vertices: V, faces: F, arestas_vivas: [], atributos: {} });
      };
      const viga = caixa('VIGA RETANGULAR', 0, 500, 500), viz = caixa('VIZINHA', 900, 1400, 900);
      const barra = doc.add({ tipo: 'barra', nome: 'U-frente', perfil: 'U 127×50×3,75', inicio: [-1500, 3500, 650], fim: [2400, 3500, 650],
                              rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      for (let i = 0; i < 40 && ![viga, viz, barra].every(e => cena.objetos.has(e.id)); i++) await new Promise(r => setTimeout(r, 100));
      ed.ativarFerramenta('selecionar');
      ed.camera.vista('iso'); ed.camera.concluirAnimacao();
      ed.camera.enquadrar([[-600, 1500, -100], [2000, 5500, 1000]]); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      for (let i = 0; i < 50 && (cena._refinando || cena._pedidoAgendado); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 600));
      return JSON.stringify({ viga: viga.id, viz: viz.id, barra: barra.id }); })()"""))
    nome = {v: k for k, v in ids.items()}

    def tela(p):
        return jsj("const ed = editor, r = ed.el.canvas.getBoundingClientRect(); const t = ed.camera.paraTela(%s);"
                   " return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];" % json.dumps(p))

    def sob(pt):   # sem filtro: o que está na frente
        return nome.get(jsj("const r = editor.el.canvas.getBoundingClientRect(); const s = editor.selecao.sob(%d - r.left, %d - r.top); return s && s.id;" % tuple(pt)))

    def evento(tipo, x, y, botao="none", botoes=0, n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=n)

    def mover(p): evento("mouseMoved", p[0], p[1]); aba.drenar(0.15)

    def clique(p):
        mover(p)
        evento("mousePressed", p[0], p[1], "left", 1); evento("mouseReleased", p[0], p[1], "left", 0)
        aba.drenar(0.3)

    def tecla(k, code, vk):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=code, windowsVirtualKeyCode=vk)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=code, windowsVirtualKeyCode=vk)
        aba.drenar(0.25)

    sel = lambda: sorted(nome.get(i, i) for i in jsj("return [...editor.selecao.ids];"))
    medida = lambda: jsj("return editor._textoMedida || '';") or ""
    alvo = lambda: nome.get((jsj("const a = editor.ativa && editor.ativa.alvo; return a && a.id;") or ""), None)
    snap = lambda: jsj("const u = editor.inferencia.ultimo; return u && { e: u.entidade, t: u.tipoSnap };") or {}

    # o ponto da barra que passa por cima da viga, na frente dela na tela; o canto de cima da vizinha
    p_barra = next((q for q in (tela([x, 3500, 650]) for x in (250, 200, 300, 150, 350)) if sob(q) == "barra"), None)
    p_viz = tela([900, 5000, 900])
    p_viga = next((q for q in (tela([250, y, 500]) for y in (2000, 2500, 5000, 1500)) if sob(q) == "viga"), None)
    ok(p_barra is not None and p_viga is not None, f"preparo: a barra na frente da viga num pixel ({p_barra}) e a viga sozinha noutro ({p_viga})")

    # A. a viga selecionada; o cursor sobre a barra da frente
    clique(p_viga)
    ok(sel() == ["viga"], f"A. a viga selecionada: {sel()}")
    tecla("p", "KeyP", 80)
    ok(jsj("return editor.idAtiva;") == "pushpull", "A. P liga o Empurrar/Puxar")
    mover(p_barra)
    m = medida()
    ok("U 127" not in m, f"A. parado sobre a barra da frente, o destaque não é dela: {m!r}")
    clique(p_barra)
    ok(alvo() == "viga", f"A. o clique ali começa na viga selecionada (atravessa a barra): {alvo()}")

    # B. no arrasto, o canto da vizinha não pega
    mover([p_viz[0] - 20, p_viz[1] + 10]); mover(p_viz)
    s = snap()
    ok(nome.get(s.get("e")) != "viz", f"B. no arrasto o snap não gruda na vizinha: {nome.get(s.get('e'), s.get('e'))} {s.get('t')}")
    tecla("Escape", "Escape", 27)
    ok(alvo() is None, "B. Esc cancela o puxão")

    # C. o clique na vizinha (fora da seleção) não começa nada
    # um pixel da vizinha cujo raio não chega na viga (se chegasse, valeria a viga, como no A)
    p_viz_meio = next((q for q in (tela([x, y, 900]) for x in (1350, 1150, 950) for y in (6500, 5000, 2500, 1000))
                       if sob(q) == "viz" and not jsj("const r = editor.el.canvas.getBoundingClientRect(); return editor.selecao.sob(%d - r.left, %d - r.top, id => id === '%s');" % (q[0], q[1], ids["viga"]))), None)
    ok(p_viz_meio is not None, f"C. preparo: um pixel só da vizinha ({p_viz_meio})")
    if p_viz_meio:
        clique(p_viz_meio)
        ok(alvo() is None, f"C. o clique na vizinha, fora da seleção, não começa: {alvo()}")
        ok("selecionada" in (jsj("return editor.el.dica.textContent;") or ""), "C. a dica diz para apontar a peça selecionada")

    # D. sem seleção, como antes: a barra da frente
    tecla("Escape", "Escape", 27)                     # volta para a Seleção
    jsj("editor.selecao.limpar(); return 1;")
    tecla("p", "KeyP", 80)
    mover(p_barra)
    ok("U 127" in medida(), f"D. sem seleção, o destaque é da barra da frente: {medida()!r}")
    clique(p_barra)
    ok(alvo() == "barra", f"D. sem seleção, o clique começa na barra da frente: {alvo()}")
    tecla("Escape", "Escape", 27)

    # E. trocando de ferramenta, o snap enxerga tudo de novo
    jsj("editor.selecao.definir(['%s']); return 1;" % ids["viga"])
    tecla("Escape", "Escape", 27)
    ok(jsj("return editor.idAtiva;") == "selecionar" and jsj("return editor.inferencia.restricao === null;"),
       "E. na Seleção o snap volta sem filtro")
    tecla("l", "KeyL", 76)                          # Linha: o snap pega a vizinha
    mover(p_viz)
    ok(nome.get(snap().get("e")) == "viz", f"E. com a Linha, o canto da vizinha pega: {snap()}")
    tecla("Escape", "Escape", 27); tecla("Escape", "Escape", 27)

    # F. cancelar e selecionar a viga de novo
    jsj("editor.ativarFerramenta('selecionar'); editor.selecao.limpar(); return 1;")
    clique(p_viga); tecla("p", "KeyP", 80); clique(p_viga)
    mover([p_viga[0] + 30, p_viga[1] - 80])
    tecla("Escape", "Escape", 27); tecla("Escape", "Escape", 27)
    clique(p_viga)
    ok(sel() == ["viga"], f"F. depois de cancelar, o clique na viga seleciona: {sel()}")
    # o caminho do usuário: clique no vazio (abre a janela) e depois na viga — a janela vazia vale a viga (26/10)
    clique([150, 150]); clique(p_viga)
    ok(sel() == ["viga"], f"F. clique no vazio e depois na viga: a viga selecionada: {sel()}")

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
