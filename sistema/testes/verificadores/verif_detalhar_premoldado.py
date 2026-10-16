# -*- coding: utf-8 -*-
"""Detalhar pré-moldado (usuário, 16/10/2026: "todo o sistema foi montado para detalhar a metálica; preciso detalhar o
pré-moldado apenas"). Num modelo sintético com o concreto como o IFC do Tekla traz (sólidos com material
CONCRETE/Fck-40, o console separado do pilar, um inserto de aço na mesma camada), confere com o navegador:
  1. a tela abre pelo editor com as famílias e as peças de cada uma, e o "Marcar / desmarcar todos" fica meio marcado;
  2. detalhar grava um desenho por família, com as peças iguais contadas (2 vigas iguais = 1 célula "2x"), o console
     dentro do pilar e o inserto de aço fora;
  3. refazer substitui (não empilha o desenho de antes)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento, Solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_pm_det_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra PM", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-16T00:00:00", "alterado": "2026-10-16T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def caixa(nome, x0, y0, z0, x1, y1, z1, ref="", material="CONCRETE/Fck-40", tipo="IfcBeam"):
    vs = [(x, y, z) for z in (z0, z1) for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    props = {"Pset_BeamCommon": {"Reference": ref}} if ref else {}
    return Solido(nome=nome, camada="200 Pré-Fabricado", material=material, vertices=vs, faces=fs,
                  atributos={"tipo_ifc": tipo, "propriedades": props, "marcas": {"perfil": nome}})


doc = Documento()
doc.add(caixa("Pilar", 0, 0, 0, 400, 400, 6000, "P1", tipo="IfcColumn"))
doc.add(caixa("Console", 400, 100, 4000, 700, 300, 4400, "C1", tipo="IfcSlab"))          # encosta no pilar
doc.add(caixa("Viga L", 400, 0, 4400, 6400, 300, 5000, "VL1"))
doc.add(caixa("Viga L", 400, 3000, 4400, 6400, 3300, 5000, "VL1"))                      # igual à de cima
doc.add(caixa("Laje Alveolar", 0, 6000, 5000, 5000, 7250, 5200, "LA1"))
doc.add(caixa("Bloco", -500, -500, -800, 900, 900, 0, "B1", material="CONCRETE/Fck-25", tipo="IfcColumn"))
doc.add(caixa("A 100x100x3/8", 0, 0, 6000, 100, 100, 6010, "ACH1", material="STEEL/A36", tipo="IfcPlate"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pm_det_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=obra", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 7)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    ok(bool(aba.avaliar("!!document.querySelector('[data-acao=\"detalhar-premoldado\"]')")), "o editor tem o botão Detalhar pré-moldado")
    # o CAD abriria noutra tela: aqui só anota o pedido
    aba.avaliar("window.__abriu = null; editor._abrirCAD = (n) => { window.__abriu = n; }; editor.dialogoDetalharPremoldado(); 1")
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("!![...document.querySelectorAll('dialog[open], .dialogo')].some(d => /Detalhar pré-moldado/.test(d.textContent))"):
        aba.drenar(0.3)
    tela = jsj("const d = [...document.querySelectorAll('dialog[open], .dialogo')].find(d => /Detalhar pré-moldado/.test(d.textContent));"
               " if (!d) return null; const labels = [...d.querySelectorAll('label')].map(l => l.textContent);"
               " const cb = [...d.querySelectorAll('input[type=checkbox]')]; return {labels, n: cb.length};")
    ok(tela is not None, "a tela Detalhar pré-moldado abriu")
    if tela:
        fams = [l for l in tela["labels"] if "peças" in l]
        print("  famílias:", fams)
        ok(any(l.startswith("Pilares e vigas (3") for l in fams), "pilares e vigas: 3 peças (o console não conta à parte)")
        ok(any(l.startswith("Fundações (1") for l in fams) and any(l.startswith("Lajes") for l in fams), "fundações e lajes na lista")
        ok(not any("Outras" in l for l in fams), "o inserto de aço não vira 'outras peças de concreto'")
        meio = jsj("const d = [...document.querySelectorAll('dialog[open], .dialogo')].find(d => /Detalhar pré-moldado/.test(d.textContent));"
                   " const cb = [...d.querySelectorAll('input[type=checkbox]')]; cb[1].click();"
                   " const r = cb[0].indeterminate; cb[0].click(); return {meio: r, todos: cb.slice(1, cb.length - 1).every(c => c.checked)};")
        ok(meio and meio["meio"] and meio["todos"], f"Marcar todos: meio marcado com uma a menos e marca todas de volta ({meio})")
        aba.avaliar("const d = [...document.querySelectorAll('dialog[open], .dialogo')].find(d => /Detalhar pré-moldado/.test(d.textContent));"
                    " [...d.querySelectorAll('button')].find(b => /Detalhar e abrir/.test(b.textContent)).click(); 1")
        t0 = time.time()
        while time.time() - t0 < 120 and not aba.avaliar("!!window.__abriu"):
            aba.drenar(0.5)
        ok(bool(aba.avaliar("!!window.__abriu")), f"detalhou e pediu para abrir o CAD em {aba.avaliar('window.__abriu')}")
        arqs = sorted(os.listdir(os.path.join(PASTA, "desenhos-2d")))
        print("  desenhos:", arqs)
        pv = next((a for a in arqs if "pilares" in a), None)
        ok(pv is not None and any("fundações" in a for a in arqs) and any("lajes" in a for a in arqs), "um desenho por família")
        if pv:
            d = json.load(open(os.path.join(PASTA, "desenhos-2d", pv), encoding="utf-8"))
            ents = d["entidades"].values() if isinstance(d["entidades"], dict) else d["entidades"]
            titulos = sorted(e.get("texto") for e in ents if e.get("tipo") == "texto" and " – " in str(e.get("texto")) and "x" in str(e.get("texto")))
            print("  títulos:", titulos)
            ok("VL1 – 2x" in titulos, "as duas vigas iguais: uma célula VL1 – 2x")
            ok("P1 – 1x" in titulos and any("com 1 console" in str(e.get("texto")) for e in ents), "o pilar P1 com o console dentro")
            ok(not any("ACH1" in str(e.get("texto")) for e in ents), "o inserto de aço fora")
            n1 = len(d["entidades"])
            aba.avaliar("window.__abriu = null; 1")
            r = jsj("return null;")
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{PORTA}/api/projetos/obra/detalhar-premoldado",
                                         data=json.dumps({"familias": ["pilares_vigas"]}).encode(), headers={"Content-Type": "application/json"})
            json.load(urllib.request.urlopen(req, timeout=120))
            d2 = json.load(open(os.path.join(PASTA, "desenhos-2d", pv), encoding="utf-8"))
            ok(len(d2["entidades"]) == n1, f"refazer substitui, não empilha ({n1} → {len(d2['entidades'])})")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:3]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
