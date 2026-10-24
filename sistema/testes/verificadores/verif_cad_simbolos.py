# -*- coding: utf-8 -*-
"""Os símbolos à mão do CAD 2D (usuário, 23/10: "pode seguir" a lista das ferramentas que faltam; web/cad/nucleo/simbolos.js),
com o teclado e o mouse de verdade (CDP), num desenho em 1:10:
  A. Solda (S D): "8-150", L L (os dois lados) → 2 triângulos, "8" e "150" dos dois lados, a linha de referência de 22 mm
     de papel (220 no 1:10) para o lado do 2º clique, na camada SOLDA; o 2º símbolo para a esquerda, "6-50-150", F
     (penetração, sem triângulo), O (todo o contorno) e B (campo);
  B. o clique pega o símbolo inteiro; Del apaga tudo; Ctrl+Z volta tudo;
  C. Balão (B M): a marca vem da peça clicada ("V12"); "4x V12" → o círculo, a marca no meio, o "4x" e a seta na peça;
  D. Nível (N V): "5,2" → "+5,20"; R e o ponto de referência "+0,00" → 3,5 m acima sai "+3,50" sozinho;
  E. Chamada de detalhe (C D): o círculo tracejado de raio 300, a bolha "1" / "03" com o traço no meio; a próxima
     sugere "2";
  F. o DXF e o PDF do desenho saem com os textos dos símbolos (nucleo2d/dxf_cad.exportar, pranchas.pdf_da_area)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_simbolos_")
PASTA = os.path.join(DADOS, "obra-simbolos")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra símbolos", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Simbolos", escala=10.0)
d.add(Linha(id="l1", a=(0, 0), b=(1000, 0)))
d.add(Linha(id="peca", a=(3000, 0), b=(3000, 1000), atributos={"posicao": "V12"}))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "simbolos.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_simbolos_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CAPTURA = os.environ.get("VERIF_SIMBOLOS_CAPTURA")          # pasta para a imagem dos símbolos (para mostrar ao usuário)
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

    COD = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), "Delete": (46, "Delete"), ",": (188, "Comma"), "-": (189, "Minus"), "+": (187, "Equal")}

    def tecla(k, mods=0):
        code, nome = COD.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ("Digit" + k if k.isdigit() else k)))
        texto = "\r" if k == "Enter" else k if len(k) == 1 and not (mods & 2) else ""      # o \r: o Enter que envia o formulário
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.1)

    def duas(k1, k2):
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        # a linha de comando (24/10): as letras vão para ela e o espaço executa, como no AutoCAD
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, text=" ", unmodifiedText=" ")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32)
        aba.drenar(0.2)

    def digitar(t):
        for ch in t: tecla(ch)
        tecla("Enter"); aba.drenar(0.2)

    def responder(t):
        """O diálogo de pergunta aberto: devolve o valor sugerido e responde `t` (digitado de verdade, Enter)."""
        if not esperar("document.querySelector('#dialogo').open", 10): return None
        sugerido = js("return document.querySelector('#dialogo-corpo input').value;")
        js("const i = document.querySelector('#dialogo-corpo input'); i.focus(); i.select(); return 1;")
        aba.cmd("Input.insertText", text=t); aba.drenar(0.1)
        tecla("Enter"); aba.drenar(0.3)
        return sugerido

    def esc():
        tecla("Escape"); tecla("Escape")

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [e for e in (js(f"return c.doc.get('{i}');") for i in ids() - antes) if e]
    perto = lambda a, b, tol=0.01: a is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol
    textos = lambda es: sorted(e["texto"] for e in es if e["tipo"] == "texto")

    def vista(caixa):
        esc(); js("c.ativarFerramenta('selecionar'); c.selecionar([]); c.tela.enquadrar(%s, 0.05); return 1;" % json.dumps(caixa)); aba.drenar(0.3)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-simbolos&desenho=simbolos", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 2", 40), "o CAD abriu o desenho")
    aba.console.clear()

    # ------------------------------------------------------------------ A. solda
    vista([[-700, -300], [700, 500]])
    duas("s", "d")
    ok(ferr() == "simbolo_solda", f"A. S D abre o Símbolo de solda ({ferr()})")
    digitar("8-150"); tecla("l"); tecla("l")
    antes = ids()
    clique([0, 0]); mover([300, 200])
    ok(len(js("return c.tela.previa || [];") or []) > 5, "A. a prévia segue o cursor depois do 1º clique")
    clique([300, 200])
    s1 = novas(antes)
    tri = [e for e in s1 if e["tipo"] == "polilinha" and e.get("fechada")]
    horiz = lambda es: [e for e in es if e["tipo"] == "linha" and abs(e["a"][1] - e["b"][1]) < 1e-6 and abs(abs(e["b"][0] - e["a"][0]) - 220) < 1e-6]
    refs = horiz(s1)
    ok(len(tri) == 2 and textos(s1) == ["150", "150", "8", "8"], f"A. os dois lados: 2 triângulos, \"8\" e \"150\" de cada lado ({len(tri)}; {textos(s1)})")
    ok(len(refs) == 1 and abs(refs[0]["b"][0] - refs[0]["a"][0] - 220) < 1e-6, f"A. a linha de referência de 22 mm de papel (220 em 1:10) para a direita ({refs[0]['a'] if refs else None} a {refs[0]['b'] if refs else None})")
    ok(all(e["camada"] == "SOLDA" for e in s1) and len({e["atributos"]["simbolo"] for e in s1}) == 1, "A. tudo na camada SOLDA, num símbolo só")
    digitar("6-50-150"); tecla("f"); tecla("l"); tecla("o"); tecla("b")
    antes = ids()
    clique([0, -100]); clique([-300, 100])
    s2 = novas(antes)
    refs = horiz(s2)
    ok(not [e for e in s2 if e["tipo"] == "polilinha" and e.get("fechada")] and "50-150" in textos(s2) and "6" in textos(s2),
       f"A. penetração (sem triângulo), \"6\" e \"50-150\" ({textos(s2)})")
    ok(len(refs) == 1 and refs[0]["b"][0] < refs[0]["a"][0], "A. o 2º clique à esquerda: a linha de referência vai para a esquerda")
    ok(any(e["tipo"] == "circulo" for e in s2) and sum(1 for e in s2 if e["tipo"] == "polilinha" and not e.get("fechada")) >= 2,
       "A. O e B: o círculo de todo o contorno e a bandeira de campo")

    # ------------------------------------------------------------------ B. o símbolo inteiro
    esc()
    t8 = next(e for e in s1 if e["tipo"] == "texto" and e["texto"] == "150")
    clique(t8["posicao"])
    sel = set(js("return [...c.tela.selecao];") or [])
    ok(sel == {e["id"] for e in s1}, f"B. o clique num texto pega o símbolo inteiro ({len(sel)} de {len(s1)})")
    n0 = js("return c.doc.tamanho;")
    tecla("Delete")
    ok(js("return c.doc.tamanho;") == n0 - len(s1), "B. Del apaga o símbolo inteiro")
    tecla("z", 2)
    ok(js("return c.doc.tamanho;") == n0, "B. Ctrl+Z volta o símbolo inteiro")

    # ------------------------------------------------------------------ C. balão
    vista([[2500, -200], [3800, 1200]])
    duas("b", "m")
    ok(ferr() == "balao_marca", f"C. B M abre o Balão de marca ({ferr()})")
    antes = ids()
    clique([3000, 500]); clique([3400, 800])
    sugerido = responder("4x V12")
    ok(sugerido == "V12", f"C. a marca sugerida vem da peça clicada ({sugerido!r})")
    b = novas(antes)
    circ = [e for e in b if e["tipo"] == "circulo"]
    marca = [e for e in b if e["tipo"] == "texto" and e["texto"] == "V12"]
    ok(len(circ) == 1 and perto(circ[0]["centro"], [3400, 800]) and marca and perto(marca[0]["posicao"], [3400, 800]) and marca[0]["alinhamento"] == "centro",
       f"C. o círculo e a marca no meio ({textos(b)})")
    ok("4x" in textos(b) and any(e["tipo"] == "polilinha" and any(perto(v, [3000, 500]) for v in e["vertices"]) for e in b), "C. o \"4x\" ao lado e a seta na peça")

    # ------------------------------------------------------------------ D. nível
    vista([[800, -500], [2400, 4000]])
    duas("n", "v")
    ok(ferr() == "simbolo_nivel", f"D. N V abre o Nível ({ferr()})")
    digitar("5,2")
    antes = ids(); clique([1000, 0])
    ok(textos(novas(antes)) == ["+5,20"], f"D. \"5,2\" → \"+5,20\" ({textos(novas(antes))})")
    tecla("r")
    antes = ids(); clique([2000, 0]); responder("+0,00")
    ok(textos(novas(antes)) == ["+0,00"], f"D. R: o ponto de referência \"+0,00\" ({textos(novas(antes))})")
    antes = ids(); clique([2000, 3500])
    ok(textos(novas(antes)) == ["+3,50"], f"D. 3,5 m acima da referência sai \"+3,50\" sozinho ({textos(novas(antes))})")

    # ------------------------------------------------------------------ E. chamada de detalhe
    vista([[4500, -500], [6600, 1300]])
    duas("c", "d")
    ok(ferr() == "chamada_detalhe", f"E. C D abre a Chamada de detalhe ({ferr()})")
    antes = ids()
    clique([5000, 0]); clique([5300, 0]); clique([6000, 800])
    sugerido = responder("1/03")
    cd = novas(antes)
    area = [e for e in cd if e["tipo"] == "circulo" and perto(e["centro"], [5000, 0])]
    bolha = [e for e in cd if e["tipo"] == "circulo" and perto(e["centro"], [6000, 800])]
    ok(sugerido == "1" and area and abs(area[0]["raio"] - 300) < 0.01 and area[0].get("tipo_linha") == "DASHED",
       f"E. o círculo tracejado de raio 300 (sugerido {sugerido!r})")
    ok(bolha and textos(cd) == ["03", "1"] and any(e["tipo"] == "linha" and abs(e["a"][1] - 800) < 0.01 and abs(e["b"][1] - 800) < 0.01 for e in cd),
       f"E. a bolha com \"1\" / \"03\" e o traço no meio ({textos(cd)})")
    clique([5000, 600]); clique([5100, 600]); clique([5600, 1100])
    sugerido = responder("2")
    ok(sugerido == "2", f"E. a próxima chamada sugere \"2\" ({sugerido!r})")

    if CAPTURA:
        os.makedirs(CAPTURA, exist_ok=True)
        vista([[-700, -600], [6600, 4000]])
        import base64
        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        open(os.path.join(CAPTURA, "simbolos-tela.png"), "wb").write(base64.b64decode(png))

    # ------------------------------------------------------------------ F. DXF e PDF
    import ezdxf
    from nucleo2d import dxf_cad, pranchas
    dd = Desenho.de_dict(js("return c.doc.paraJSON();"))
    tmp = tempfile.mkdtemp(prefix="simbolos_saida_")
    dxf = dxf_cad.exportar(dd, os.path.join(tmp, "simbolos.dxf"))
    txts = {t.dxf.text for t in ezdxf.readfile(dxf).modelspace().query("TEXT")}
    ok({"50-150", "V12", "4x", "+5,20", "+3,50", "03"} <= txts, f"F. o DXF com os textos dos símbolos ({sorted(txts)[:12]})")
    pdf = pranchas.pdf_da_area(dd, os.path.join(CAPTURA or tmp, "simbolos.pdf"), ((-700, -600), (6600, 4000)), 10)
    ok(os.path.getsize(pdf) > 1000, "F. o PDF sai")
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
