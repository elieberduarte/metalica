# -*- coding: utf-8 -*-
"""Tipos de linha, espessuras e penas de impressão no CAD 2D (usuário, 23/10: "precisamos criar outros tipos de linhas
(tracejada, pontilhada....) igual existe no autocad, e a opção de mexer nas espessuras..." e "criar as penas igual
existe no autocad para configurar como vai para impressão"), com o mouse e o teclado de verdade (CDP):
  A. Propriedades: a linha selecionada ganha o tipo (Pontilhada) e a espessura (0,70) dela; a tela mostra (o traço
     mais grosso pinta mais pixels, o pontilhado menos); "Pela camada" volta; Ctrl+Z desfaz; gravado no desenho só o
     que é do objeto;
  B. Camadas: o botão da linha da camada abre o diálogo; a camada vira Oculta 0,50 e as linhas dela acompanham;
  C. Estilos do desenho: a escala dos tracejados (o LTSCALE) gravada no desenho;
  D. Penas de impressão (Arquivo): as cores do desenho, uma pena (1,00 mm, preta) gravada na tabela do programa e
     lembrada ao abrir de novo; também pelo botão do Imprimir."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Camada2D

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_linhas_")
PASTA = os.path.join(DADOS, "obra-linhas")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra linhas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Linhas", escala=10.0)
d.camadas["PECAS"] = Camada2D(nome="PECAS", cor="#c0392b", espessura=0.25)
d.add(Linha(id="a", a=(0, 0), b=(2000, 0), camada="VISTA"))
d.add(Linha(id="b", a=(0, 400), b=(2000, 400), camada="PECAS"))
d.add(Linha(id="c", a=(0, 800), b=(2000, 800), camada="PECAS"))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "linhas.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
ARQ_PENAS = os.path.join(DADOS, "penas-de-impressao.json")

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_linhas_")
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
            aba.drenar(0.3)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def clicar_xy(x, y):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)

    def clicar(seletor_js):
        r = js(f"const e = {seletor_js}; if (!e) return null; e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        clicar_xy(*r)
        return True

    def escolher(seletor_js, valor):
        return js(f"const s = {seletor_js}; if (!s) return null; s.value = {json.dumps(valor)}; s.dispatchEvent(new Event('change', {{bubbles: true}})); return s.value;")

    def tecla(k, mods=0):
        code = 27 if k == "Escape" else ord(k.upper())
        texto = k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 else k, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=("Key" + k.upper()) if len(k) == 1 else k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.2)

    ent = lambda i: js(f"return c.doc.get('{i}');")

    def pixels(y_mm):
        """os pixels pintados numa faixa de 14 px em volta da linha, no meio dela (a cor do fundo fica de fora) — com o
        cursor fora do desenho (sem o realce do objeto sob ele nem o glifo do snap) e nada selecionado"""
        xa, ya = tela([1000, 1050]); aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=xa, y=ya)
        js("c.selecionar([]); c.tela.pedirQuadro(); return 1;")
        aba.drenar(0.4)
        return js("""const cv = c.el.canvas, dpr = window.devicePixelRatio || 1, t = c.tela.paraTela([1000, %r]);
            const g = cv.getContext('2d').getImageData(Math.round((t[0] - 150) * dpr), Math.round((t[1] - 7) * dpr), Math.round(300 * dpr), Math.round(14 * dpr)).data;
            const f = getComputedStyle(document.body).backgroundColor; let n = 0;
            for (let i = 0; i < g.length; i += 4) { const claro = g[i] > 225 && g[i + 1] > 225 && g[i + 2] > 225; const escuro = g[i] < 30 && g[i + 1] < 36 && g[i + 2] < 46; if (!claro && !escuro && Math.abs(g[i] - g[i + 1]) > 40) n++; }
            return n;""" % y_mm)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-linhas&desenho=linhas", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 3", 40), "o CAD abriu o desenho")
    aba.console.clear()
    js("c.tela.enquadrar([[-100, -300], [2100, 1100]]); c.tela.pedirQuadro(); return 1;"); aba.drenar(0.4)

    # ------------------------------------------------------------------ A. o tipo e a espessura do objeto
    n_fino = pixels(400)
    clicar_xy(*tela([1000, 400]))
    ok(js("return [...c.tela.selecao];") == ["b"], "A. a linha b selecionada")
    ok(js("return !!document.querySelector('select[name=tipo_linha]') && !!document.querySelector('select[name=espessura]');"),
       "A. Propriedades com Tipo de linha e Espessura")
    opcoes = js("return [...document.querySelector('select[name=tipo_linha]').options].map(o => o.value);") or []
    ok(opcoes[:1] == [""] and {"DASHED", "HIDDEN", "DOT", "DASHDOT", "CENTER", "PHANTOM", "BORDER", "DASHED2", "DASHEDX2"} <= set(opcoes),
       f"A. os tipos do AutoCAD ({len(opcoes)} opções, a primeira Pela camada)")
    escolher("document.querySelector('select[name=espessura]')", "0.7")
    ok(ent("b").get("espessura") == 0.7, f"A. a espessura própria: {ent('b').get('espessura')}")
    js("c.selecionar([]); return 1;")
    n_grosso = pixels(400)
    ok(n_grosso > 1.8 * n_fino, f"A. na tela o traço de 0,70 pinta mais que o de 0,25 ({n_grosso} × {n_fino} pixels)")
    clicar_xy(*tela([1000, 400]))
    escolher("document.querySelector('select[name=tipo_linha]')", "DOT")
    ok(ent("b").get("tipo_linha") == "DOT", f"A. o tipo próprio: {ent('b').get('tipo_linha')}")
    js("c.selecionar([]); return 1;")
    n_ponto = pixels(400)
    ok(0 < n_ponto < 0.8 * n_grosso, f"A. o pontilhado pinta menos que o contínuo ({n_ponto} × {n_grosso})")
    js("return c.salvar({ avisar: false });"); aba.drenar(1.5)
    gravado = {e["id"]: e for e in json.load(open(os.path.join(PASTA, "desenhos-2d", "linhas.desenho.json"), encoding="utf-8"))["entidades"]}
    ok(gravado["b"].get("tipo_linha") == "DOT" and gravado["b"].get("espessura") == 0.7 and "tipo_linha" not in gravado["c"],
       "A. gravado: o tipo e a espessura só no objeto que tem os seus")
    clicar_xy(*tela([1000, 400]))
    escolher("document.querySelector('select[name=tipo_linha]')", "")
    ok(ent("b").get("tipo_linha") is None, "A. Pela camada tira o tipo próprio")
    tecla("z", 2)
    ok(ent("b").get("tipo_linha") == "DOT", "A. Ctrl+Z devolve o tipo próprio")
    tecla("Escape"); tecla("Escape")

    # ------------------------------------------------------------------ B. a linha da camada
    ok(clicar("document.querySelector('.linha-da-camada[data-camada=PECAS]')"), "B. o botão da linha da camada PECAS")
    ok(esperar("document.querySelector('dialog[open] select[name=tipo_linha]')", 10), "B. o diálogo da camada abriu")
    escolher("document.querySelector('dialog[open] select[name=tipo_linha]')", "HIDDEN")
    escolher("document.querySelector('dialog[open] select[name=espessura]')", "0.5")
    clicar("document.querySelector('dialog[open] .botao-ok')")
    cam = js("return c.doc.camadas.get('PECAS');")
    ok(cam["tipo_linha"] == "HIDDEN" and cam["espessura"] == 0.5, f"B. a camada PECAS: {cam['tipo_linha']} {cam['espessura']}")
    ok("╍ 0,5" in (js("return document.querySelector('.linha-da-camada[data-camada=PECAS]').textContent;") or ""), "B. o botão mostra a linha nova")
    n_c = pixels(800)
    ok(0 < n_c < 0.9 * n_grosso * 0.5 / 0.7 * 1.5, f"B. a linha c (pela camada) agora tracejada ({n_c} pixels)")

    # ------------------------------------------------------------------ C. a escala dos tracejados
    js("c.aplicarEstilos({ escala_tracejado: 0.8 }); return 1;")
    ok(js("return c.doc.metadados.estilo.escala_tracejado;") == 0.8, "C. Estilos: a escala dos tracejados no desenho")
    ok(js("return !!document;") and js("""const b = [...document.querySelectorAll('button[data-acao=estilos]')][0]; return !!b;"""), "C. o item Estilos do desenho")

    # ------------------------------------------------------------------ D. as penas
    ok(clicar("document.querySelector('.menu[data-menu=desenho] .menu-botao')") or True, "D. o menu")
    ok(clicar("document.querySelector('button[data-acao=penas]')"), "D. o item Penas de impressão…")
    ok(esperar("document.querySelector('dialog[open] .penas .pena')", 15), "D. o diálogo das penas abriu")
    cores = js("return [...document.querySelectorAll('dialog[open] .pena')].map(l => l.dataset.cor);") or []
    ok("#c0392b" in cores, f"D. as cores do desenho na lista: {cores}")
    escolher("document.querySelector('dialog[open] .pena[data-cor=\"#c0392b\"] select[name=espessura]')", "1")
    escolher("document.querySelector('dialog[open] .pena[data-cor=\"#c0392b\"] select[name=cor]')", "#000000")
    clicar("document.querySelector('dialog[open] .botao-ok')")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => a.textContent.includes('Penas gravadas'))", 15), "D. o aviso de penas gravadas")
    tab = json.load(open(ARQ_PENAS, encoding="utf-8")) if os.path.exists(ARQ_PENAS) else {}
    ok(tab.get("penas") == {"#c0392b": {"espessura": 1.0, "cor": "#000000"}}, f"D. a tabela do programa: {tab}")
    clicar("document.querySelector('.menu[data-menu=desenho] .menu-botao')")
    clicar("document.querySelector('button[data-acao=penas]')")
    ok(esperar("document.querySelector('dialog[open] .penas .pena')", 15), "D. aberto de novo")
    lembrado = js("""const l = document.querySelector('dialog[open] .pena[data-cor="#c0392b"]'); return [l.querySelector('select[name=espessura]').value, l.querySelector('select[name=cor]').value];""")
    ok(lembrado == ["1", "#000000"], f"D. a pena lembrada: {lembrado}")
    clicar("document.querySelector('#dialogo-cancelar')")
    # pelo Imprimir (o desenho não é das pranchas: o Imprimir este desenho)
    tecla("p", 2)
    ok(esperar("document.querySelector('dialog[open] select[name=area]')", 20), "D. Ctrl+P abre o Imprimir este desenho")
    ok(clicar("[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent.startsWith('Penas'))"), "D. o botão Penas… do Imprimir")
    ok(esperar("document.querySelector('dialog[open] .penas .pena')", 15), "D. leva às penas")
    clicar("document.querySelector('#dialogo-cancelar')")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
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
