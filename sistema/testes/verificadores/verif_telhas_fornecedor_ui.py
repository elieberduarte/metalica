# -*- coding: utf-8 -*-
"""Telhas para o fornecedor (o padrão do Fábio; usuário, 13/11, "é assim?" aprovado em 14/11), com o mouse e o teclado de
verdade (CDP), no menu Desenho › Telhas para o fornecedor (DXF + Word)…:

  A. sem o Detalhar das telhas, o menu diz o que fazer (não abre o diálogo vazio);
  B. com o desenho do fornecedor no projeto: o diálogo mostra o tipo de telha com o campo da cor, a obra, o local em
     branco e a revisão R00; o Enter no campo não gera;
  C. Gerar: o DXF (R2018, com DIMENSION de verdade) e o Word (com a cor) na pasta da obra 04-EXECUCAO, em R00; a cor fica
     guardada na obra; o aviso da cidade em branco;
  D. de novo, com o Word da R00 aberto (preso, como no Word): sai a R01, a cor vem preenchida, o DXF da R00 vai para o
     Obsoleto e o aviso diz que o Word aberto não foi.

O desenho do fornecedor é o do Detalhar das telhas do recorte do Depósito Químico (testes/dados_telhas). Não imprime nada.
Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_telhas_fornecedor_ui.py"""
import gzip, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fornecedor_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def desenho_do_fornecedor():
    from nucleo3d.modelo import Documento
    from nucleo2d import detalhar as det
    with gzip.open(os.path.join(BASE, "testes", "dados_telhas", "deposito_quimico_cumeeira.json.gz"), "rt", encoding="utf-8") as f:
        doc = Documento.de_dict(json.load(f))
    return det.detalhar(doc, grupos=["telhas"])["desenhos"]["telhas_fornecedor"]


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fornecedor_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
preso = None
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Depósito teste", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    PASTA = os.path.join(DADOS, slug)
    post(f"/api/projetos/{slug}/desenhos/planta", {"desenho": {"nome": "Planta", "escala": 50, "entidades": [
        {"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 0], "b": [5000, 0]}]}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + f"/cad?projeto={slug}&desenho=planta", limite=60)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.3)
        return False

    def clicar(seletor_js):
        r = js(f"const e = {seletor_js}; if (!e) return null; e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True

    def avisos():
        return js("return [...document.querySelectorAll('.aviso, .avisos *')].map(a => a.textContent).join(' | ');") or ""

    def pelo_menu():
        clicar("document.querySelector('.menu[data-menu=desenho] .menu-botao')")
        return clicar("document.querySelector('.menu[data-menu=desenho] button[data-acao=telhas-fornecedor]')")

    ok(esperar("document.body.dataset.pronto === '1' && c && c.nomeDesenho === 'planta'", 60), "o CAD abriu")

    # ------------------------------------------------------------------ A. sem o Detalhar das telhas
    ok(pelo_menu(), "A. o item Desenho › Telhas para o fornecedor (DXF + Word)…")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /detalhe as telhas/i.test(a.textContent))", 15)
       and not js("return !!document.querySelector('dialog[open]');"), f"A. sem o desenho do fornecedor: o que fazer, sem diálogo ({avisos()[:160]})")

    # ------------------------------------------------------------------ B. o diálogo
    d = desenho_do_fornecedor()
    post(f"/api/projetos/{slug}/desenhos/telhas-para-o-fornecedor", {"desenho": d.dict()})
    ok(pelo_menu() and esperar("document.querySelector('dialog[open] input[name=acabamento]')", 20), "B. o diálogo abre")
    info = js("""const d = document.querySelector('dialog[open]');
        return { campos: [...d.querySelectorAll('input[name=acabamento]')].map(i => [i.dataset.perfil, i.value]),
                 revisao: d.querySelector('input[name=revisao]').value, texto: d.textContent };""") or {}
    ok(len(info.get("campos") or []) == 1 and info["campos"][0][1] == "", f"B. um tipo de telha, com o campo da cor vazio: {info.get('campos')}")
    ok(info.get("revisao") == "R00" and "em branco" in (info.get("texto") or ""), f"B. a revisão R00 e o local em branco dito: {info.get('revisao')}")
    clicar("document.querySelector('dialog[open] input[name=acabamento]')")
    aba.cmd("Input.insertText", text="pré-pintada CINZA RAL 7035")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    aba.drenar(1.0)
    pasta = os.path.join(PASTA, "04-EXECUCAO")
    ok(js("return !!document.querySelector('dialog[open]');") and not os.path.isdir(pasta), "B. o Enter no campo não gera")

    # ------------------------------------------------------------------ C. Gerar
    clicar("document.querySelector('dialog[open] .botao-ok')")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /Telhas para o fornecedor R00/.test(a.textContent))", 60),
       f"C. o aviso de gerado ({avisos()[:200]})")
    arqs = sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []
    ok([a.rsplit(".", 1)[-1] for a in arqs if "." in a] == ["docx", "dxf"] and all("-R00." in a for a in arqs if "." in a),
       f"C. o DXF e o Word na pasta da obra, em R00: {arqs}")
    import ezdxf, docx
    dx = next((os.path.join(pasta, a) for a in arqs if a.endswith(".dxf")), None)
    dw = next((os.path.join(pasta, a) for a in arqs if a.endswith(".docx")), None)
    if dx and dw:
        doc = ezdxf.readfile(dx)
        dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]
        ok(doc.dxfversion == "AC1032" and dims and all(e.dxf.text in ("", "<>") for e in dims), f"C. o DXF R2018 com {len(dims)} cotas de verdade")
        texto = "\n".join(p.text for p in docx.Document(dw).paragraphs)
        ok("pré-pintada CINZA RAL 7035" in texto and "RELAÇÃO DE TELHAS" in texto, "C. o Word com a cor")
    proj = json.load(open(os.path.join(PASTA, "projeto.json"), encoding="utf-8"))
    ok(list(((proj.get("opcoes_detalhamento") or {}).get("acabamentos_telhas") or {}).values()) == ["pré-pintada CINZA RAL 7035"],
       "C. a cor guardada na obra")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /sem a cidade/.test(a.textContent))", 5), "C. o aviso da cidade em branco")

    # ------------------------------------------------------------------ D. de novo, com o Word da R00 aberto
    preso = open(dw, "rb")                             # como o Word: o arquivo aberto não se move
    ok(pelo_menu() and esperar("document.querySelector('dialog[open] input[name=revisao]')", 20), "D. o diálogo de novo")
    info = js("""const d = document.querySelector('dialog[open]');
        return { cor: d.querySelector('input[name=acabamento]').value, revisao: d.querySelector('input[name=revisao]').value };""") or {}
    ok(info == {"cor": "pré-pintada CINZA RAL 7035", "revisao": "R01"}, f"D. a cor preenchida e a revisão R01: {info}")
    clicar("document.querySelector('dialog[open] .botao-ok')")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /Telhas para o fornecedor R01/.test(a.textContent))", 60), "D. gerada a R01")
    obs = sorted(os.listdir(os.path.join(pasta, "Obsoleto"))) if os.path.isdir(os.path.join(pasta, "Obsoleto")) else []
    ok(any(a.endswith("-R00.dxf") for a in obs) and not any(a.endswith("-R00.docx") for a in obs), f"D. o DXF da R00 no Obsoleto, o Word aberto não: {obs}")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /abertos/.test(a.textContent) && /Obsoleto/.test(a.textContent))", 5),
       f"D. o aviso do Word aberto ({avisos()[:200]})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    if preso:
        preso.close()
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
