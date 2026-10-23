# -*- coding: utf-8 -*-
"""Rodada de pedidos do CAD 2D (usuário, 23/10), com o teclado e o mouse de verdade (CDP):
  A. "selecionar todos os desenhos do 2D com ctrl + a": em qualquer ferramenta (aqui, no meio da Linha), todos os
     objetos visíveis, menos os das camadas travadas;
  B. "as [cotas] quando são diagonais às vezes apresentam uma dificuldade para medir no plano … uso a seta do teclado e
     travo em um eixo": na Cota, ← → travam a horizontal e ↑ ↓ a vertical, a mesma seta solta e volta ao automático
     (que continua dando a alinhada); no Medir, a seta deixa só o Δ do eixo;
  C. "aumentar um pouco mais o limite de zoom": a roda aproxima até 2000 px por mm (eram 200);
  D. "se dou um ctrl + p nessa tela original ele não deixa imprimir aparece essa mensagem que o projeto não tem
     prancha": no desenho que não é das pranchas, o Ctrl+P abre "Imprimir este desenho" (a vista da tela ou o desenho
     inteiro, numa escala); a folha sai pela Microsoft Print to PDF no tamanho do trecho ÷ a escala; com pranchas no
     projeto, o botão leva ao Imprimir pranchas.

Nunca imprime na impressora padrão da máquina (a plotter da fábrica): só pela Microsoft Print to PDF."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Texto, Camada2D
from saida import impressao

PDF_DO_WINDOWS = "Microsoft Print to PDF"
TEM_PDF = sys.platform == "win32" and any(p["nome"] == PDF_DO_WINDOWS for p in impressao.impressoras()["impressoras"])

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cadrodada_")
PASTA = os.path.join(DADOS, "obra-rodada")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra rodada", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def _gravar(d, nome):
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", nome + ".desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)


# o "Original": um desenho comum (não é das pranchas), em 1:10, com uma camada travada
orig = Desenho(nome="Original", escala=10.0)
orig.camadas["ARQ"] = Camada2D(nome="ARQ", cor="#888888", bloqueada=True)
for i, (a, b) in enumerate([((0, 0), (2000, 0)), ((2000, 0), (2000, 1200)), ((2000, 1200), (0, 1200)), ((0, 1200), (0, 0)),
                            ((300, 300), (1300, 900))]):
    orig.add(Linha(id="l%d" % i, a=a, b=b, camada="VISTA"))
orig.add(Linha(id="arq", a=(0, -300), b=(2000, -300), camada="ARQ"))
orig.add(Texto(id="t", posicao=(100, 1300), texto="ORIGINAL", altura=5))
_gravar(orig, "projeto-recebido-original")
pr = Desenho(nome="Prancha 01", escala=1.0)
pr.add(Linha(a=(25, 7), b=(290, 7))); pr.add(Texto(posicao=(40, 150), texto="FOLHA 1", altura=12))
pr.metadados["prancha"] = {"formato": "A4", "numero": 1, "total": 1, "titulo": "FOLHA 1"}
_gravar(pr, "prancha-01")
SAIDA = os.path.join(PASTA, "pranchas", "impressao-microsoft-print-to-pdf.pdf")

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadrodada_")
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

    def evento(tipo, x, y, botao="none", botoes=0, **k):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1, **k)

    def mover(p):
        x, y = tela(p); evento("mouseMoved", x, y); aba.drenar(0.12)

    def clique(p):
        x, y = tela(p)
        evento("mouseMoved", x, y); evento("mousePressed", x, y, "left", 1); evento("mouseReleased", x, y, "left", 0)
        aba.drenar(0.2)

    TECLAS = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), "ArrowLeft": (37, "ArrowLeft"), "ArrowUp": (38, "ArrowUp"),
              "ArrowRight": (39, "ArrowRight"), "ArrowDown": (40, "ArrowDown")}

    def tecla(k, mods=0):
        code, nome = TECLAS.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ""))
        texto = k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.12)

    def clicar(seletor_js):
        r = js(f"const e = {seletor_js}; if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        evento("mouseMoved", *r); evento("mousePressed", *r, "left", 1); evento("mouseReleased", *r, "left", 0)
        aba.drenar(0.3)
        return True

    def escolher(nome, valor):
        return js(f"const s = document.querySelector('dialog[open] select[name={nome}]'); s.value = {json.dumps(valor)}; s.dispatchEvent(new Event('change', {{bubbles: true}})); return s.value;")

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    sel = lambda: sorted(js("return [...c.tela.selecao];") or [])
    dica = lambda: js("return c.el.dica.textContent;") or ""

    def esc():
        tecla("Escape"); tecla("Escape")

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-rodada&desenho=projeto-recebido-original", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 7", 40), "o CAD abriu o Original")
    aba.console.clear()
    js("c.tela.enquadrar([[-200, -500], [2200, 1500]]); return 1;"); aba.drenar(0.3)

    # ------------------------------------------------------------------ A. Ctrl+A
    tecla("l"); clique([500, 500])
    ok(ferr() == "linha", "A. no meio da Linha (o primeiro ponto dado)")
    tecla("a", 2)
    ok(ferr() == "selecionar" and sel() == sorted(["l0", "l1", "l2", "l3", "l4", "t"]),
       f"A. Ctrl+A: a Linha sai e ficam selecionados os 6 visíveis, sem o da camada travada: {sel()}")
    ok("1 em camadas travadas" in dica(), f"A. a dica diz o que ficou de fora: '{dica()}'")
    ok(js("return c.doc.tamanho;") == 7, "A. nada foi desenhado pela Linha interrompida")
    esc()

    # ------------------------------------------------------------------ B. as setas na Cota e no Medir
    tecla("d")
    clique([300, 300]); clique([1300, 900])
    mover([800, 620])                                     # entre os dois pontos: a alinhada (o automático)
    modo = lambda: js("const p = c.tela.previa || c._previa || []; const e = (Array.isArray(p) ? p : []).find(x => x.tipo === 'cota'); return e ? e.modo : null;")
    ok(modo() == "alinhada", f"B. no automático, a cota diagonal sai alinhada: {modo()}")
    tecla("ArrowRight"); mover([800, 640])
    ok(modo() == "h", f"B. → trava a horizontal: {modo()}")
    tecla("ArrowRight"); mover([800, 620])
    ok(modo() == "alinhada", f"B. → de novo solta: volta ao automático ({modo()})")
    tecla("ArrowDown"); mover([820, 620])
    ok(modo() == "v", f"B. ↓ trava a vertical: {modo()}")
    antes = set(js("return [...c.doc.entidades.keys()];"))
    clique([1500, 620])
    nova = [js(f"return c.doc.get('{i}');") for i in set(js("return [...c.doc.entidades.keys()];")) - antes]
    ok(len(nova) == 1 and nova[0]["modo"] == "v" and abs(abs(nova[0]["p2"][1] - nova[0]["p1"][1]) - 600) < 1e-6,
       f"B. a cota feita na vertical: 600 mm ({nova and nova[0]['modo']})")
    tecla("ArrowDown")                                    # solta para as próximas
    esc()
    tecla("u"); clique([300, 300]); tecla("ArrowLeft"); clique([1300, 900])
    aviso = js("return [...document.querySelectorAll('.aviso, .avisos *')].map(a => a.textContent).reverse().find(t => t.includes('Distância')) || '';") or ""
    ok("Distância: 1000 mm" in aviso and "Δy 0" in aviso, f"B. Medir com ←: só a horizontal ({aviso[:70]})")
    esc()

    # ------------------------------------------------------------------ C. o zoom mais perto
    x, y = tela([1300, 900])
    for _ in range(60):
        aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0, deltaY=-600)
    aba.drenar(0.3)
    z = js("return c.tela.vp.z;")
    ok(abs(z - 2000) < 1e-6, f"C. a roda aproxima até 2000 px/mm (eram 200): {z}")
    ok(js("const p = c.tela.paraMundo(c.tela.paraTela([1300, 900])); return Math.hypot(p[0] - 1300, p[1] - 900) < 1e-6;"),
       "C. no zoom máximo a conta da tela continua exata")
    js("c.tela.enquadrar([[-200, -500], [2200, 1500]]); return 1;"); aba.drenar(0.3)

    # ------------------------------------------------------------------ D. Ctrl+P no Original
    clique([2100, 1400])
    tecla("p", 2)
    ok(esperar("document.querySelector('dialog[open] select[name=area]')", 20), "D. Ctrl+P no Original abre o Imprimir este desenho")
    ok(not js("return [...document.querySelectorAll('.aviso, .avisos *')].some(a => a.textContent.includes('não tem pranchas'));"),
       "D. sem o aviso de que o projeto não tem pranchas")
    if TEM_PDF:
        escolher("impressora", PDF_DO_WINDOWS)
        ok(esperar("(() => { const s = document.querySelector('dialog[open] select[name=papel]'); return s && !s.disabled && s.options.length > 1; })()", 30),
           "D. os papéis da Microsoft Print to PDF carregados")
        escolher("area", "tudo")
        js("const i = document.querySelector('dialog[open] input[name=escala]'); i.value = '10'; i.dispatchEvent(new Event('input')); return 1;")
        resumo = js("return document.querySelector('dialog[open] .resumo').textContent;") or ""
        ok("Folha de 200 × 160 mm (1:10)" in resumo, f"D. o desenho inteiro em 1:10: a folha de 200 × 160 mm ({resumo[:80]})")
        if js("return document.querySelector('dialog[open] select[name=impressora]').value;") != PDF_DO_WINDOWS:
            ok(False, "a impressora escolhida não é a de teste: não imprimo")
            raise SystemExit
        clicar("document.querySelector('dialog[open] .botao-ok')")
        ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => a.textContent.includes('gravada em PDF'))", 120),
           "D. Imprimir: a folha gravada em PDF pela Microsoft Print to PDF")
        import pymupdf
        for _ in range(20):
            if os.path.exists(SAIDA): break
            time.sleep(0.5)
        if os.path.exists(SAIDA):
            doc = pymupdf.open(SAIDA)
            pg = doc[0]
            w, h = pg.rect.width / 72 * 25.4, pg.rect.height / 72 * 25.4
            pix = pg.get_pixmap(dpi=30, colorspace=pymupdf.csGRAY)
            escuros = sum(1 for b in pix.samples if b < 128)
            ok(doc.page_count == 1 and abs(max(w, h) - 297) < 2 and abs(min(w, h) - 210) < 2 and escuros > 50,
               f"D. o arquivo: 1 página A4 (a folha de 200 × 160 cabe no A4, deitada), {w:.0f} × {h:.0f} mm, {escuros} pixels escuros")
        else:
            ok(False, f"D. o arquivo da impressão não foi gravado: {SAIDA}")
    else:
        print("  ok    sem a Microsoft Print to PDF do Windows: a impressão não é conferida")
        clicar("document.querySelector('#dialogo-cancelar')")
    # o botão das pranchas
    tecla("p", 2)
    ok(esperar("document.querySelector('dialog[open] select[name=area]')", 20), "D. Ctrl+P de novo")
    clicar("[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent.startsWith('Imprimir as pranchas'))")
    ok(esperar("document.querySelector('dialog[open] .folhas label')", 20), "D. o botão leva ao Imprimir pranchas, com as folhas do projeto")
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
