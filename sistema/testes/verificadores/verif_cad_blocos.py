# -*- coding: utf-8 -*-
"""Os blocos do CAD 2D (24/10; usuário: "Biblioteca da empresa" e "Como no AutoCAD"), com o mouse e o teclado de verdade:
  A. B (BLOCK) com a seleção: o ponto de base e o nome → a seleção vira uma inserção só; a definição no desenho e na
     biblioteca da empresa (o arquivo do programa);
  B. I (INSERT): a lista, o bloco preso ao cursor, "90" gira, R gira mais 90°, E espelha; o clique insere;
  C. o snap pega as pontas de dentro do bloco (giradas) e o ponto de inserção; o clique seleciona a inserção inteira;
  D. o duplo clique (BEDIT) solta as entidades; uma linha a mais; Concluir → todas as inserções mudam, e a biblioteca;
  E. X explode uma inserção em entidades soltas;
  F. Ctrl+C leva a definição junto; gravar e reabrir mantém os blocos;
  G. em outra obra, I mostra o bloco da biblioteca e o insere (a definição vem para o desenho);
  H. o DXF do desenho sai com BLOCK/INSERT e o PDF sai."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Linha, Circulo, Texto

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_blocos_")
for nome_p, ents in (("obra-a", True), ("obra-b", False)):
    pasta = os.path.join(DADOS, nome_p)
    os.makedirs(os.path.join(pasta, "desenhos-2d"))
    json.dump({"formato": 1, "nome": nome_p, "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
               "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
    d = Desenho(nome="Desenho", escala=1.0)
    if ents:
        d.add(Linha(id="l1", a=(0, 0), b=(100, 0))); d.add(Linha(id="l2", a=(100, 0), b=(100, 50)))
        d.add(Circulo(id="c1", centro=(50, 25), raio=9)); d.add(Texto(id="t1", posicao=(0, 60), texto="PLACA", altura=2.5))
    else:
        d.add(Linha(id="x", a=(-500, -500), b=(-490, -500)))
    json.dump(d.dict(), open(os.path.join(pasta, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_blocos_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CAPTURA = os.environ.get("VERIF_BLOCOS_CAPTURA")
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

    def mover(p, pausa=0.15):
        x, y = tela(p); ev("mouseMoved", x, y); aba.drenar(pausa)

    def clique(p, n=1):
        x, y = tela(p)
        ev("mouseMoved", x, y)
        for i in range(1, n + 1):
            ev("mousePressed", x, y, "left", 1, i); ev("mouseReleased", x, y, "left", 0, i)
        aba.drenar(0.3)

    def tecla(k, mods=0):
        cod = {"Enter": 13, "Escape": 27}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" and not mods else (k if len(k) == 1 and not mods else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 and k.isalpha() else k, windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.12)

    def digitar(t):
        tecla(t[0])
        if len(t) > 1: aba.cmd("Input.insertText", text=t[1:])
        tecla("Enter"); aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape")

    blocos = lambda: [e for e in js("return [...c.doc.entidades.values()];") if e["tipo"] == "bloco"]
    biblioteca = lambda: json.load(open(os.path.join(DADOS, "blocos-da-biblioteca.json"), encoding="utf-8"))["blocos"] if os.path.exists(os.path.join(DADOS, "blocos-da-biblioteca.json")) else {}
    perto = lambda a, b, tol=0.05: a is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-a&desenho=desenho", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 4", 40), "o CAD abriu o desenho")
    js("c.tela.enquadrar([[-200, -300], [1300, 300]], 0.02); return 1;"); aba.drenar(0.3)
    aba.console.clear()

    # ------------------------------------------------------------------ A. B
    js("c.selecionar(['l1', 'l2', 'c1', 't1']); return 1;")
    comando(aba, "b")
    ok(js("return c.ferramenta.constructor.id;") == "criar_bloco", "A. B (com a seleção) pede o ponto de base")
    clique([0, 0])
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo [data-campo=nome]')"), "A. o diálogo do nome")
    js("const n = document.querySelector('#dialogo-corpo [data-campo=nome]'); n.focus(); n.select(); return 1;")
    aba.cmd("Input.insertText", text="PLACA-1")
    tecla("Enter"); aba.drenar(0.6)
    bs = blocos()
    ok(len(bs) == 1 and bs[0]["nome"] == "PLACA-1" and js("return c.doc.tamanho;") == 1, f"A. a seleção vira uma inserção só ({js('return c.doc.tamanho;')} objeto(s))")
    d0 = js("return c.doc.metadados.blocos['PLACA-1'];")
    ok(d0 and len(d0["entidades"]) == 4, "A. a definição no desenho, com as 4 entidades")
    ok(esperar("true", 1) and "PLACA-1" in biblioteca() and len(biblioteca()["PLACA-1"]["entidades"]) == 4, "A. e na biblioteca da empresa")
    ins1 = bs[0]["id"]

    # ------------------------------------------------------------------ B. I
    comando(aba, "i")
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo [data-bloco=\"PLACA-1\"]')"), "B. I abre a lista com o PLACA-1")
    tecla("Enter"); aba.drenar(0.3)
    ok(js("return c.ferramenta.constructor.id;") == "inserir_bloco" and js("return c.ferramenta.nome;") == "PLACA-1", "B. o bloco preso ao cursor")
    digitar("90")
    clique([500, 0])
    tecla("r"); tecla("e")
    clique([900, 0])
    esc()
    bs = sorted(blocos(), key=lambda b: b["posicao"][0])
    ok(len(bs) == 3 and bs[1]["angulo"] == 90 and perto(bs[1]["posicao"], [500, 0]), f"B. a 2ª inserção girada 90° ({bs[1] if len(bs) > 1 else None})")
    ok(len(bs) == 3 and bs[2]["angulo"] == 180 and bs[2]["escala"][0] == -1, f"B. R gira mais 90° e E espelha ({bs[2] if len(bs) > 2 else None})")
    ins2, ins3 = bs[1]["id"], bs[2]["id"]

    # ------------------------------------------------------------------ C. snap e seleção
    comando(aba, "l")
    mover([500 + 2, 100 - 1])                               # a ponta (100, 0) girada 90° → (500, 100)
    s = js("return c.tela.snap && { tipo: c.tela.snap.tipo, ponto: c.tela.snap.ponto };")
    ok(s and s["tipo"] == "extremidade" and perto(s["ponto"], [500, 100]), f"C. o snap pega a ponta de dentro do bloco, girada ({s})")
    mover([500 + 1, 1])
    s = js("return c.tela.snap && { tipo: c.tela.snap.tipo, ponto: c.tela.snap.ponto, rotulo: c.tela.snap.rotulo };")
    ok(s and perto(s["ponto"], [500, 0]), f"C. e o ponto de inserção ({s})")
    esc()
    clique([500, 50])
    ok(js("return [...c.tela.selecao];") == [ins2], "C. o clique seleciona a inserção inteira")

    # ------------------------------------------------------------------ D. BEDIT
    esc()
    clique([100, 25], 2)                                    # o duplo clique na 1ª inserção (na linha em pé, x = 100)
    ok(js("return !!c._edicaoDoBloco;") and len([e for e in js("return [...c.doc.entidades.values()];") if (e.get("atributos") or {}).get("bloco_edicao") == "PLACA-1"]) == 4,
       "D. o duplo clique solta as 4 entidades do bloco para editar")
    comando(aba, "l")
    clique([0, 0]); clique([0, 50]); esc()
    js("document.querySelector('[data-acao-bloco=concluir]').click(); return 1;")
    aba.drenar(0.8)
    d1 = js("return c.doc.metadados.blocos['PLACA-1'];")
    bs = blocos()
    ok(not js("return !!c._edicaoDoBloco;") and len(bs) == 3 and d1 and len(d1["entidades"]) == 5, f"D. Concluir: o bloco com 5 entidades, as 3 inserções de volta ({len(bs)})")
    comando(aba, "l")
    mover([500 - 50 + 1, 0 + 1])                            # a linha nova (0,0)-(0,50) girada 90° vai a (500,0)-(450,0): a ponta (450, 0)
    s = js("return c.tela.snap && { tipo: c.tela.snap.tipo, ponto: c.tela.snap.ponto };")
    ok(s and s["tipo"] == "extremidade" and perto(s["ponto"], [450, 0]), f"D. a outra inserção mudou junto (a linha nova nela: {s})")
    esc()
    ok(len(biblioteca()["PLACA-1"]["entidades"]) == 5, "D. a biblioteca também mudou")

    # ------------------------------------------------------------------ E. X
    js(f"c.selecionar([{json.dumps(ins3)}]); return 1;")
    comando(aba, "x")
    aba.drenar(0.3)
    ok(len(blocos()) == 2 and js("return c.doc.tamanho;") == 2 + 5, f"E. X explode a inserção em 5 entidades soltas ({js('return c.doc.tamanho;')})")
    esc()

    # ------------------------------------------------------------------ F. Ctrl+C e gravar
    js(f"c.selecionar([{json.dumps(ins1)}]); return 1;")
    tecla("c", 2)
    copia = json.loads(js("return localStorage.getItem('cad.copia');") or "{}")
    ok("PLACA-1" in (copia.get("blocos") or {}), "F. o Ctrl+C leva a definição do bloco junto")
    js("return c.salvar({ avisar: false }), 1;")
    aba.drenar(1.0)
    gravado = json.load(open(os.path.join(DADOS, "obra-a", "desenhos-2d", "desenho.desenho.json"), encoding="utf-8"))
    ok(sum(1 for e in gravado["entidades"] if e["tipo"] == "bloco") == 2 and "PLACA-1" in gravado["metadados"].get("blocos", {}), "F. gravado com as inserções e a definição")
    if CAPTURA:
        import base64
        os.makedirs(CAPTURA, exist_ok=True)
        open(os.path.join(CAPTURA, "blocos-tela.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    # ------------------------------------------------------------------ H. DXF e PDF
    import ezdxf
    from nucleo2d import dxf_cad, pranchas
    dd = Desenho.de_dict(gravado)
    tmp = tempfile.mkdtemp(prefix="blocos_saida_")
    doc = ezdxf.readfile(dxf_cad.exportar(dd, os.path.join(tmp, "b.dxf")))
    ok(len(doc.modelspace().query("INSERT")) == 2 and "PLACA-1" in doc.blocks, "H. o DXF com 2 INSERT e o BLOCK")
    pdf = pranchas.pdf_da_area(dd, os.path.join(tmp, "b.pdf"), ((-200, -300), (1300, 300)), 5)
    ok(os.path.getsize(pdf) > 1000, "H. o PDF sai")

    # ------------------------------------------------------------------ G. outra obra
    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-b&desenho=desenho", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 1", 40), "G. a outra obra abriu")
    js("c.tela.enquadrar([[-200, -300], [1300, 300]], 0.02); return 1;"); aba.drenar(0.3)
    comando(aba, "i")
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo [data-bloco=\"PLACA-1\"]')"), "G. I na outra obra lista o PLACA-1 da biblioteca")
    tecla("Enter"); aba.drenar(0.3)
    clique([300, 0]); esc()
    ok(len(blocos()) == 1 and len((js("return c.doc.metadados.blocos || {};") or {}).get("PLACA-1", {}).get("entidades", [])) == 5,
       "G. inserido, com a definição trazida da biblioteca")
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
