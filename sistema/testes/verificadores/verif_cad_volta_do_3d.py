# -*- coding: utf-8 -*-
"""A volta do 3D refeita pela planta de antes (BUGS N.3 pelo GESTÃO N.9, 14/11, na cópia do Hangar do verif_identificacao_ui):
o "Atualizar a planta pelo 3D" gravava a planta antes de pedir a volta, e essa gravação disparava a sincronia do 3D sem
esperar — a sincronia lia a planta de ANTES da volta e terminava depois dela: o 3D refeito com a terça de volta ao lugar
antigo, a planta com ela 300 mm adiante, e um 2º clique levava a terça de volta também na planta (o que o usuário fez no
3D se perdia). As duas gravavam o modelo.json ao mesmo tempo (o "arquivo danificado" / 500 da /estrutura/3d).

  A. a planta com duas terças e o 3D gerado por ela; no 3D, a terça T1 anda 300 mm ao longo dela; a planta aberta de novo
     (a primeira gravação dela sincronizava); clique de verdade em Estrutura › Atualizar a planta pelo 3D;
  B. depois de tudo terminar: a planta com a T1 300 mm adiante E o 3D com ela 300 mm adiante (a mesma barra, o mesmo id);
  C. o 2º clique: "Nada mudou no 3D em relação a esta planta", e a planta e o 3D continuam com a T1 movida;
  D. uma terça nova na planta (T3) e o clique logo em seguida, antes do autosave: a mudança da planta vai ao 3D antes da
     volta (a T3 no 3D, sem "Sem peça no 3D") e a volta diz isso numa linha; a T1 continua movida nos dois. Nos cliques A e C
     (nada mudado na planta), essa linha não aparece.

Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_volta_do_3d.py"""
import json, math, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_volta_3d_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
PERFIL = "U 127×50×2,25 (FF)"


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def terca(i, y):
    return {"id": f"t{i}", "tipo": "linha", "camada": "ESTRUTURA", "a": [0.0, y], "b": [5460.0, y],
            "atributos": {"elemento": "viga", "material": "aco", "papel": "terça", "marca": f"T{i}",
                          "secao": {"perfil": PERFIL, "aco": "ASTM A36"}, "nivel_topo": 6454.5, "alinhamento": "base"}}


def modelo(pasta):
    m = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
    return m, (m["entidades"] if isinstance(m["entidades"], list) else list(m["entidades"].values()))


def barras(pasta):
    return {e["atributos"]["origem_2d"]: e for e in modelo(pasta)[1] if (e.get("atributos") or {}).get("origem_2d") in ("t1", "t2")}


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_volta_3d_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Volta do 3D", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    pasta = os.path.join(DADOS, slug)
    post(f"/api/projetos/{slug}/desenhos/planta", {"desenho": {"nome": "Planta", "escala": 100, "entidades": [terca(1, 0.0), terca(2, 2000.0)]}})
    g = post(f"/api/projetos/{slug}/estrutura/3d", {"desenho": "planta"})
    b0 = barras(pasta)
    ok(set(b0) == {"t1", "t2"}, f"o 3D gerado pela planta: as duas terças ({sorted(b0)}; {str(g)[:120]})")

    # no 3D, a T1 anda 300 mm ao longo dela (gravado inteiro, de uma vez)
    m, lista = modelo(pasta)
    t1 = next(e for e in lista if (e.get("atributos") or {}).get("origem_2d") == "t1")
    id_t1 = t1["id"]
    L = math.dist(t1["inicio"], t1["fim"]); d = [(t1["fim"][i] - t1["inicio"][i]) / L for i in range(3)]
    t1["inicio"] = [t1["inicio"][i] + 300 * d[i] for i in range(3)]
    t1["fim"] = [t1["fim"][i] + 300 * d[i] for i in range(3)]
    movida = list(t1["inicio"])
    tmp = os.path.join(pasta, "modelo.json.tmp")
    json.dump(m, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, os.path.join(pasta, "modelo.json"))

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    # conta os pedidos às rotas da estrutura em curso, para esperar tudo terminar (a sincronia que corria depois da volta)
    aba.cmd("Page.addScriptToEvaluateOnNewDocument", source="""(() => { const o = window.fetch.bind(window); window.__estr = 0; window.__rotas = [];
      window.fetch = async (u, op) => { const t = String(u && u.url || u); const e = /\\/estrutura\\//.test(t);
        if (e) { window.__estr++; window.__rotas.push(t.split('/').pop()); }
        try { const r = await o(u, op); if (e && !r.ok) window.__rotas.push('ERRO ' + r.status); return r; } finally { if (e) window.__estr--; } }; })();""")
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
            aba.drenar(0.2)
        return False

    def clicar(seletor_js):
        r = js(f"const e = {seletor_js}; if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True

    def volta(texto):
        js("document.querySelectorAll('#avisos .aviso').forEach(a => a.remove()); return 1;")
        clicar("document.querySelector('[data-menu=\"estrutura\"] .menu-botao')")
        esperar("(() => { const b = document.querySelector('[data-acao=\"estr-do-3d\"]'); return b && b.getBoundingClientRect().height > 0; })()", 5)
        clicar("document.querySelector('[data-acao=\"estr-do-3d\"]')")
        achou = esperar(f"[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes({json.dumps(texto)}))", 30)
        # tudo terminar: nenhum pedido da estrutura em curso por 2 s seguidos (a sincronia de antes corria depois da volta)
        t0 = time.time(); quieto = None
        while time.time() - t0 < 60:
            if js("return window.__estr;") == 0 and not js("return c._salvando;"):
                quieto = quieto or time.time()
                if time.time() - quieto > 2: break
            else:
                quieto = None
            aba.drenar(0.2)
        return achou

    def t1_na_planta():
        return js("const e = c.doc.get('t1'); return e ? e.a : null;")

    ok(esperar("document.body.dataset.pronto === '1' && c && c.nomeDesenho === 'planta' && c.doc.tamanho === 2", 60), "o CAD abriu a planta com as duas terças")

    # ------------------------------------------------------------------ A/B. o 1º clique
    ok(volta("Planta atualizada pelo 3D"), "A. Atualizar a planta pelo 3D: \"Planta atualizada pelo 3D\"")
    a = t1_na_planta()
    ok(a and abs(math.dist(a, [0.0, 0.0]) - 300) < 2, f"B. a T1 andou 300 mm na planta ({a})")
    b1 = barras(pasta)
    t1b = b1.get("t1") or {}
    ok(t1b and math.dist(t1b["inicio"], movida) < 2, f"B. o 3D continua com a T1 300 mm adiante ({t1b.get('inicio')} × {movida}; antes voltava ao lugar antigo)")
    ok(t1b.get("id") == id_t1 and (b1.get("t2") or {}).get("id") == b0["t2"]["id"], "B. as mesmas barras no 3D (o 3D não foi refeito pela planta de antes)")
    print("     rotas:", js("return window.__rotas;"))
    def levou():
        return js("return [...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('ainda não levadas ao 3D'));")
    ok(not levou(), "A. sem mudança na planta, a volta não diz que levou algo antes")

    # ------------------------------------------------------------------ C. o 2º clique
    ok(volta("Nada mudou no 3D"), f"C. o 2º clique: \"Nada mudou no 3D em relação a esta planta\" ({js('return [...document.querySelectorAll(\"#avisos .aviso\")].map(a => a.textContent.slice(0, 80));')})")
    ok(not levou(), "C. sem mudança na planta, a volta não diz que levou algo antes")
    a2 = t1_na_planta()
    t1c = barras(pasta).get("t1") or {}
    ok(a2 and abs(math.dist(a2, [0.0, 0.0]) - 300) < 2 and t1c and math.dist(t1c["inicio"], movida) < 2,
       f"C. a T1 continua movida na planta ({a2}) e no 3D ({t1c.get('inicio')})")

    # ------------------------------------------------------------------ D. a planta mudada e o clique antes do autosave
    js(f"""window.__t3 = false; import('/cad/nucleo/desenho2d.js').then(d => import('/cad/nucleo/comandos.js').then(k => {{
      c.executar(new k.ComandoAdicionar([d.criar({json.dumps(terca(3, 4000.0))})], 'T3')); window.__t3 = true; }})); return 1;""")
    ok(esperar("window.__t3 && c.doc.get('t3')", 10), "D. a T3 desenhada na planta")
    ok(volta("Nada mudou no 3D"), f"D. o clique logo depois: \"Nada mudou\" ({js('return [...document.querySelectorAll(\"#avisos .aviso\")].map(a => a.textContent.slice(0, 80));')})")
    b3 = barras(pasta)
    t3 = [e for e in modelo(pasta)[1] if (e.get("atributos") or {}).get("origem_2d") == "t3"]
    ok(len(t3) == 1, f"D. a T3 foi ao 3D antes da volta ({len(t3)})")
    ok(not js("return [...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('Sem peça no 3D'));"), "D. sem \"Sem peça no 3D\"")
    ok(levou(), "D. a volta diz que a planta tinha mudanças ainda não levadas ao 3D e que foram levadas antes")
    a3 = t1_na_planta()
    ok(a3 and abs(math.dist(a3, [0.0, 0.0]) - 300) < 2 and math.dist((b3.get("t1") or {}).get("inicio", [0, 0, 0]), movida) < 2,
       f"D. a T1 continua movida na planta ({a3}) e no 3D ({(b3.get('t1') or {}).get('inicio')})")
    ok("ERRO" not in " ".join(js("return window.__rotas;") or []), f"sem erro nas rotas da estrutura ({js('return window.__rotas;')})")
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
