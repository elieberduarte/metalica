# -*- coding: utf-8 -*-
"""As revisões das pranchas no CAD 2D (usuário, 24/10: a opção A — a tabela inteira em cima do carimbo; "nuvem +
triângulo"; o diálogo "Revisões das pranchas…" marca as pranchas que mudaram), com o mouse e o teclado de verdade:
  A. NR (REVCLOUD) + espaço: o retângulo por dois cantos na prancha 02 e o clique do triângulo → a nuvem (arcos) e o
     △ "1" (a prancha está na REV. 00) num símbolo só; o clique pega tudo e Del apaga tudo;
  B. Arquivo › Revisões das pranchas…: a descrição, a prancha 02 marcada, Gravar → o desenho aberto recarrega com a
     tabela em cima do carimbo da 02 (00 EMISSÃO INICIAL, 01 a nova) e "PRANCHA 02/02   REV. 01"; a 01 não muda;
     o projeto guarda as revisões;
  C. a nuvem seguinte na prancha 02 já sugere o △ "1"… e depois da revisão 02, o "2";
  D. o diálogo de novo mostra as já lançadas; a data da emissão corrigida ali fica gravada e aparece na tabela;
  E. a tabela que cai em cima de um detalhe é avisada."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import comando
from nucleo2d.desenho import Desenho, Linha
from nucleo2d import modelo_hermes as M
from nucleo2d.pranchas import FOLHAS, juntar_pranchas

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_revisoes_")
PASTA = os.path.join(DADOS, "obra-revisoes")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra revisões", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "E.D.",
           "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def prancha(n, detalhe_acima_do_carimbo=False):
    d = Desenho(nome="Prancha %02d" % n, escala=1.0)
    quadro, carimbo = M.desenhar_folha(d, "A1", 841, 594, {"obra": "OBRA REVISÕES", "revisao": "00"}, n, 2, "1:25", ["- TESOURAS"])
    d.add(Linha(camada="VISTA", a=(100.0, 300.0), b=(400.0, 300.0), atributos={"cel": "c%d" % n}))
    if detalhe_acima_do_carimbo:
        d.add(Linha(camada="VISTA", a=(700.0, 125.0), b=(780.0, 125.0), atributos={"cel": "d%d" % n}))
    d.metadados["prancha"] = {"formato": "A1", "numero": n, "total": 2, "titulo": "TESOURAS %d" % n,
                              "quadro": list(quadro), "carimbo": list(carimbo), "celulas": []}
    return d


junto = juntar_pranchas([prancha(1, detalhe_acima_do_carimbo=True), prancha(2)], nome="Pranchas")
junto.metadados["gerado_por"] = "pranchas"
json.dump(junto.dict(), open(os.path.join(PASTA, "desenhos-2d", "pranchas.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
O2 = junto.metadados["pranchas"][1]["origem"]
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_revisoes_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CAPTURA = os.environ.get("VERIF_REVISOES_CAPTURA")
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

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.3)

    def tecla(k, mods=0):
        cod = {"Enter": 13, "Escape": 27, "Delete": 46, " ": 32}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = "\r" if k == "Enter" else (k if len(k) == 1 and not mods else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, windowsVirtualKeyCode=cod, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=cod, modifiers=mods)
        aba.drenar(0.12)

    def esc():
        tecla("Escape"); tecla("Escape")

    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))
    novas = lambda antes: [e for e in (js(f"return c.doc.get('{i}');") for i in ids() - antes) if e]
    tabela = lambda n: js(f"return [...c.doc.entidades.values()].filter(e => (e.atributos||{{}}).campo === 'revisoes' && (e.atributos||{{}}).prancha_numero === {n}).map(e => e.tipo === 'texto' ? e.texto : '');")
    rev_txt = lambda n: js(f"return [...c.doc.entidades.values()].filter(e => e.tipo === 'texto' && (e.atributos||{{}}).campo === 'prancha' && (e.atributos||{{}}).prancha_numero === {n}).map(e => e.texto);")
    projeto = lambda: json.load(open(os.path.join(PASTA, "projeto.json"), encoding="utf-8"))

    def nuvem_em(p0, p1, tri):
        comando(aba, "nr")
        antes = ids()
        clique(p0); clique(p1); clique(tri)
        aba.drenar(0.2)
        return novas(antes)

    def abrir_revisoes():
        js("document.querySelector('[data-acao=revisoes]').click(); return 1;")
        return esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo [data-campo=descricao]')", 15)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-revisoes&desenho=pranchas", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && (window.cad.doc.metadados.pranchas || []).length === 2", 40), "o CAD abriu as pranchas")
    js("c.tela.enquadrar([[%f, 0], [%f, 594]], 0.02); return 1;" % (O2[0], O2[0] + 841)); aba.drenar(0.4)
    aba.console.clear()

    # ------------------------------------------------------------------ A. nuvem com o △
    s1 = nuvem_em([O2[0] + 150, 280], [O2[0] + 260, 330], [O2[0] + 275, 340])
    arcos = [e for e in s1 if e["tipo"] == "arco"]
    tri = [e for e in s1 if e["tipo"] == "texto"]
    ok(js("return c.ferramenta.constructor.id;") == "nuvem_revisao" and len(arcos) >= 20, f"A. NR: a nuvem pelos dois cantos ({len(arcos)} arcos)")
    ok([t["texto"] for t in tri] == ["1"] and len({(e.get("atributos") or {}).get("simbolo") for e in s1}) == 1,
       f"A. o △ \"1\" (a prancha na REV. 00) e a nuvem num símbolo só ({[t['texto'] for t in tri]})")
    fora = all(min(abs(e["centro"][0] - x) for x in (O2[0] + 150, O2[0] + 260)) < 0.5 or min(abs(e["centro"][1] - y) for y in (280, 330)) < 0.5 for e in arcos)
    ok(fora, "A. os arcos ficam sobre o contorno do retângulo")
    esc()
    clique(tri[0]["posicao"])
    sel = set(js("return [...c.tela.selecao];") or [])
    ok(sel == {e["id"] for e in s1}, f"A. o clique no △ pega a nuvem inteira ({len(sel)} de {len(s1)})")
    tecla("Delete")
    ok(not (ids() & {e["id"] for e in s1}), "A. Del apaga a nuvem e o △")

    # ------------------------------------------------------------------ B. a revisão nova pelo diálogo
    ok(abrir_revisoes(), "B. Arquivo › Revisões das pranchas… abre o diálogo")
    js("const c2 = document.querySelector('#dialogo-corpo [data-prancha=\"2\"]'); c2.checked = true; return 1;")
    js("const i = document.querySelector('#dialogo-corpo [data-campo=descricao]'); i.focus(); return 1;")
    aba.cmd("Input.insertText", text="terças Ue 200 no lugar das Ue 150")
    js("document.querySelector('#dialogo-corpo [data-campo=data]').value = '24/10/2026'; return 1;")
    tecla("Enter")
    ok(esperar("(cad.doc.entidades && [...cad.doc.entidades.values()].some(e => (e.atributos||{}).campo === 'revisoes'))", 20), "B. o desenho recarrega com a tabela")
    t2 = tabela(2)
    ok("EMISSÃO INICIAL" in t2 and "TERÇAS UE 200 NO LUGAR DAS UE 150" in t2 and "REV." in t2 and "01" in t2, f"B. a tabela da 02: {[t for t in t2 if t][:12]}")
    ok(rev_txt(2) == ["PRANCHA 02/02   REV. 01"] and rev_txt(1) == ["PRANCHA 01/02   REV. 00"] and not [t for t in tabela(1) if t],
       f"B. o REV. da 02 acompanha; a 01 não muda ({rev_txt(2)}, {rev_txt(1)})")
    rv = (projeto().get("carimbo_pranchas") or {}).get("revisoes") or {}
    ok([ln["rev"] for ln in rv.get("2", [])] == ["00", "01"] and rv["2"][1]["por"] == "E.D." and rv["2"][1]["data"] == "24/10/2026",
       f"B. o projeto guarda as revisões da 02 ({rv})")

    # ------------------------------------------------------------------ C. o △ sugere a revisão da prancha
    s2 = nuvem_em([O2[0] + 150, 400], [O2[0] + 260, 450], [O2[0] + 275, 460])
    ok([e["texto"] for e in s2 if e["tipo"] == "texto"] == ["1"], "C. depois da REV. 01, o △ \"1\"")
    esc()

    # ------------------------------------------------------------------ D. editar as já lançadas + a revisão 02
    ok(abrir_revisoes(), "D. o diálogo de novo")
    n_ent = js("return document.querySelectorAll('#dialogo-corpo input[type=text]').length;")
    js("""const ins = [...document.querySelectorAll('#dialogo-corpo input[type=text]')].filter(i => i.value === '');
          const d0 = ins.find(i => !i.dataset.campo); d0.value = '10/10/2026'; d0.dispatchEvent(new Event('input')); return 1;""")
    js("document.querySelector('#dialogo-corpo [data-prancha=\"2\"]').checked = true; const i = document.querySelector('#dialogo-corpo [data-campo=descricao]'); i.focus(); return 1;")
    aba.cmd("Input.insertText", text="detalhe 4 revisado")
    tecla("Enter")
    ok(esperar("[...cad.doc.entidades.values()].some(e => e.tipo === 'texto' && e.texto === 'DETALHE 4 REVISADO')", 20), "D. a revisão 02 entra na tabela")
    rv = (projeto().get("carimbo_pranchas") or {}).get("revisoes") or {}
    ok([ln["rev"] for ln in rv.get("2", [])] == ["00", "01", "02"] and rv["2"][0]["data"] == "10/10/2026" and "10/10/2026" in tabela(2),
       f"D. a data da emissão corrigida no diálogo fica gravada e aparece ({rv.get('2', [{}])[0]})")
    ok(rev_txt(2) == ["PRANCHA 02/02   REV. 02"], f"D. REV. 02 no carimbo ({rev_txt(2)})")
    s3 = nuvem_em([O2[0] + 450, 400], [O2[0] + 560, 450], [O2[0] + 575, 460])
    ok([e["texto"] for e in s3 if e["tipo"] == "texto"] == ["2"], "D. o △ sugere o \"2\"")
    esc()

    # ------------------------------------------------------------------ E. a tabela em cima de um detalhe
    ok(abrir_revisoes(), "E. o diálogo de novo")
    js("document.querySelector('#dialogo-corpo [data-prancha=\"1\"]').checked = true; const i = document.querySelector('#dialogo-corpo [data-campo=descricao]'); i.focus(); return 1;")
    aba.cmd("Input.insertText", text="chapas")
    tecla("Enter")
    ok(esperar("[...document.querySelectorAll('#avisos .aviso')].some(a => /encosta num detalhe/.test(a.textContent))", 20),
       "E. a tabela da 01 cai em cima do detalhe: o aviso diz para arrastar")
    if CAPTURA:
        import base64
        os.makedirs(CAPTURA, exist_ok=True)
        js("c.tela.enquadrar([[%f, 0], [%f, 594]], 0.02); return 1;" % (O2[0] + 500, O2[0] + 841)); aba.drenar(0.5)
        open(os.path.join(CAPTURA, "revisoes-tela.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
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
