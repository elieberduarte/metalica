# -*- coding: utf-8 -*-
"""Estender / recuar telha (20/10/2026, o usuário no Mercado: "criar uma ferramenta para extender ou recuar as telhas — no
editar elas viram todas pedaços individuais em trechos, e as ferramentas que criamos não funcionam para as telhas"), com o
mouse e o teclado de verdade (CDP), nas telhas no formato do lançamento (telhas_cobertura._solido_da_chapa):
  · a fiada de cima do fechamento (3 pedaços em pé, selecionados com Shift+clique) sobe 300 digitando, só a ponta de cima,
    a fiada de baixo fica; logo depois "500" corrige; Ctrl+Z volta;
  · com o cursor na ponta de um pilar (snap), as pontas vão até a altura dela;
  · a telha da cobertura (3 terças, inclinada) recua 2000 pela ponta de baixo: passa da primeira terça, a seção dela sai,
    a ponta fica na reta da telha, e o comprimento do atributo acompanha."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
from nucleo3d.telhas_cobertura import TELHA_PADRAO, _solido_da_chapa

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_estender_telha_")
PASTA = os.path.join(DADOS, "et")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Estender telha", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-20T00:00:00", "alterado": "2026-10-20T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
W = 1020.0


def telha(secoes, nome, normal=(0.0, 0.0, 1.0), **at):
    so = _solido_da_chapa({"secoes": secoes, "a": 0.0, "b": W, "origem": 0.0}, TELHA_PADRAO, "Telhas", normal=normal)
    so.nome = nome
    so.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": "TP40", **at}
    return so


# o fechamento: duas fiadas em pé (como o lançamento deixa, um pedaço entre longarinas), a onda para fora (−y)
for fiada, (z0, z1) in (("baixo", (6456.0, 7248.0)), ("cima", (7248.0, 8040.0))):
    for i in range(3):
        x = i * W
        doc.add(telha([((x, 0.0, z0), (x + W, 0.0, z0)), ((x, 0.0, z1), (x + W, 0.0, z1))], f"F{fiada}{i}",
                      normal=(0.0, -1.0, 0.0), fechamento=True))
doc.add(Barra(nome="pilar", inicio=(3600.0, -300.0, 6000.0), fim=(3600.0, -300.0, 9000.0), perfil="W 250×32,7", rotacao=0.0, papel="pilar"))
# a cobertura: três terças a 1500 em planta, 5 % de caída (sobe para +x)
secs = [((x, 3000.0, 9500.0 + 0.05 * (x - 20000.0)), (x, 3000.0 + W, 9500.0 + 0.05 * (x - 20000.0))) for x in (20000.0, 21500.0, 23000.0)]
# a seção da telha corre ao longo da terça (y) e a telha desce/sobe em x: A e B são as bordas na terça
cob = telha(secs, "cobertura", comprimento=3004)
doc.add(cob)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_estender_telha_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=et", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 8"
                                                    " && editor.ferramentas && editor.ferramentas.get('estender_telha'))"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    aba.console.clear()

    def js(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ try {{ {e} }} catch (err) {{ return {{ erro: String(err && err.stack || err) }}; }} }})())")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def tela(p):
        return js(f"const t = editor.camera.paraTela({json.dumps(p)}), r = editor.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")

    def mover(p):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=p[0], y=p[1], buttons=0); aba.drenar(0.12)

    def clicar(p, mods=0):
        mover(p)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=p[0], y=p[1], button="left", clickCount=1, buttons=1, modifiers=mods)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=p[0], y=p[1], button="left", clickCount=1, buttons=0, modifiers=mods)
        aba.drenar(0.3)

    TECLAS = {"Enter": 13, "Escape": 27, "Control": 17, "Shift": 16}

    def tecla(k, mods=0):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, windowsVirtualKeyCode=code, text=k if len(k) == 1 and not mods else "", modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.15)

    def digitar(t):
        tecla(t[0])
        if len(t) > 1: aba.cmd("Input.insertText", text=t[1:])
        aba.drenar(0.05)
        tecla("Enter")
        aba.drenar(0.4)

    def shift_t():
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Shift", windowsVirtualKeyCode=16, modifiers=8)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="T", windowsVirtualKeyCode=84, text="T", modifiers=8)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="T", windowsVirtualKeyCode=84, modifiers=8)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Shift", windowsVirtualKeyCode=16, modifiers=0)
        aba.drenar(0.3)

    def ctrl_z():
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Control", windowsVirtualKeyCode=17, modifiers=2)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Control", windowsVirtualKeyCode=17, modifiers=0)
        aba.drenar(0.4)

    def vista(nome, lo, hi):
        for _ in range(5):
            js(f"editor.camera.vista('{nome}', [{json.dumps(lo)}, {json.dumps(hi)}]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); return 1;")
            a_ = js("const c = editor.camera.ativa.position; return [c.x, c.y, c.z].map(v => Math.round(v * 1000));"); aba.drenar(0.6)
            if js("const c = editor.camera.ativa.position; return [c.x, c.y, c.z].map(v => Math.round(v * 1000));") == a_: break

    ID = js("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    # o z de cima e de baixo de cada pedaço do fechamento (todos os vértices)
    def zs(nome):
        return js(f"const v = editor.documento.get('{ID[nome]}').vertices.map(p => p[2]); return [Math.round(Math.min(...v)), Math.round(Math.max(...v))];")

    ok(js("return !!document.querySelector('[data-id=\"estender_telha\"]');"), "Estender telha está na barra de ferramentas")
    vista("frente", [-300, -500, 6200], [3800, 300, 9200])
    alvo_sel = lambda i, z: tela([i * W + W / 2 - 60, -6.0, z])
    js("editor.ativarFerramenta('selecionar'); editor.selecao.limpar(); return 1;")
    clicar(alvo_sel(0, 7700)); clicar(alvo_sel(1, 7700), mods=8); clicar(alvo_sel(2, 7700), mods=8)
    sel = js("return [...editor.selecao.ids].length;")
    ok(sel == 3, f"Shift+clique seleciona a fiada de cima (3 pedaços): {sel}")
    shift_t()
    ok(js("return editor.idAtiva;") == "estender_telha", "Shift+T abre o Estender telha")
    clicar(alvo_sel(1, 7950))
    dica = js("return editor.el.dica ? editor.el.dica.textContent : '';") or ""
    ok("3 telha" in dica, f"o clique perto da ponta de cima pega as 3 da seleção: {dica[:90]}")
    digitar("300")
    r = [zs(f"Fcima{i}") for i in range(3)]
    ok(all(x == [7248, 8340] for x in r), f"as 3 sobem 300 só pela ponta de cima (7248 a 8340): {r}")
    rb = [zs(f"Fbaixo{i}") for i in range(3)]
    ok(all(x == [6456, 7248] for x in rb), f"a fiada de baixo não mexe: {rb}")
    digitar("500")
    r = [zs(f"Fcima{i}") for i in range(3)]
    ok(all(x == [7248, 8540] for x in r), f"logo depois, \"500\" corrige (8540): {r}")
    ctrl_z()
    r = [zs(f"Fcima{i}") for i in range(3)]
    ok(all(x == [7248, 8040] for x in r), f"Ctrl+Z volta a fiada (8040): {r}")

    # até a ponta do pilar (snap na extremidade, z 9000)
    js("editor.selecao.definir(%s); return 1;" % json.dumps([ID[f"Fcima{i}"] for i in range(3)]))
    clicar(alvo_sel(0, 7950))
    topo = tela([3600.0, -300.0, 9000.0])
    mover([topo[0] + 3, topo[1] + 2]); mover(topo)
    snap = js("const p = editor.ultimoPonto || editor._ultimoPonto || null; return p ? p.tipoSnap : (editor.inferencia && editor.inferencia.ultimo ? editor.inferencia.ultimo.tipoSnap : '');")
    clicar(topo)
    r = [zs(f"Fcima{i}") for i in range(3)]
    ok(all(x == [7248, 9000] for x in r), f"no ponto do pilar, as pontas vão até a altura dele (9000; snap {snap!r}): {r}")
    ctrl_z()

    # a cobertura: recua 2000 pela ponta de baixo (x 20000) — passa da terça do meio (1501,9 de cada trecho)
    js("editor.ativarFerramenta('selecionar'); editor.selecao.limpar(); return 1;")
    vista("topo", [19500, 2500, 9000], [23500, 4500, 10000])
    shift_t()
    clicar(tela([20250.0, 3000.0 + W / 2 - 60, 9600.0]))
    digitar("-2000")
    c = js(f"const e = editor.documento.get('{ID['cobertura']}'); const v = e.vertices; const xs = v.map(p => p[0]);"
           " return { n: v.length, xmin: Math.min(...xs), xmax: Math.max(...xs), faces: e.faces.length, comp: e.atributos.comprimento,"
           "          zmin: Math.min(...v.filter(p => p[0] < Math.min(...xs) + 1).map(p => p[2])) };")
    L = math.hypot(1500, 75)                                    # cada trecho na caída de 5 %
    x_novo = 20000 + 1500 * (2000 / L)
    z_novo = 9500 + 0.05 * (x_novo - 20000)
    m_sec = len(cob.vertices) // 3
    ok(c and c["n"] == 2 * m_sec and c["faces"] == len(cob.faces) // 2,
       f"recuando 2000 a telha passa da terça do meio: fica com 2 seções (de 3): {c and (c['n'], c['faces'])}")
    ok(c and abs(c["xmin"] - x_novo) < 1.0 and abs(c["xmax"] - 23000) < 1.0, f"a ponta de baixo em x {x_novo:.0f} e a de cima parada: {c}")
    ok(c and abs(c["zmin"] - z_novo) < 1.0, f"a ponta nova na reta da telha (z {z_novo:.0f}): {c and c['zmin']}")
    ok(c and c["comp"] == 3004 - 2000, f"o comprimento do atributo acompanha (1004): {c and c['comp']}")
    ctrl_z()
    n_volta = js(f"return editor.documento.get('{ID['cobertura']}').vertices.length;")
    ok(n_volta == len(cob.vertices), f"Ctrl+Z devolve a seção tirada: {n_volta}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
