# -*- coding: utf-8 -*-
"""Ver → Conferir antes de detalhar (onda 4, 14/10/2026), no navegador de verdade: num projeto sintético com duas vigas
se atravessando, uma barra apoiada em cima (encostada) e uma chapa com um parafuso perto da borda, o painel lista a
colisão (só o par que se atravessa), o furo perto da borda e as peças sem marca; clicar no achado seleciona as peças.
Sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Chapa, Documento
from nucleo3d.lancamento import _parafuso_solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_conf3d_")
PASTA = os.path.join(DADOS, "conf")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Conferência", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
W = "W 250×32,7"
doc = Documento()
doc.add(Barra(nome="viga1", inicio=(0, 0, 0), fim=(4000, 0, 0), perfil=W))
doc.add(Barra(nome="viga2", inicio=(2000, -2000, 0), fim=(2000, 2000, 0), perfil=W))
doc.add(Barra(nome="em cima", inicio=(1000, -2000, 258), fim=(1000, 2000, 258), perfil=W))
doc.add(Chapa(nome="chapa", origem=(6000, 0, 0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0), contorno=[(0, 0), (200, 0), (200, 150), (0, 150)],
              espessura=12.5, centrada=False, furos=[{"x": 15, "y": 75, "diametro": 17.5}]))
b = _parafuso_solido((6015, 75, 6), (0, 0, 1), 16, 40, "ASTM A325")
b.atributos["parafuso"].update(ponto=[6015, 75, 6], eixo=[0, 0, 1])
doc.add(b)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_conf3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=conf", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 5)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            if js(cond): return True
            aba.drenar(0.3)
        return False
    def menu(acao):
        js(f"document.querySelector('[data-acao=\"{acao}\"]').click(); 1"); aba.drenar(0.3)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ids = jsj("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    def ent(i): return jsj(f"const e = editor.documento.get('{i}'); return e ? JSON.parse(JSON.stringify(e)) : null;")
    def chapas(): return jsj("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').map(e => JSON.parse(JSON.stringify(e)));")
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)

    menu("conferir-producao")
    ok(esperar("!!document.querySelector('.painel-conferencia')", 90), "o painel da conferência abriu")
    txt = js("document.querySelector('.painel-conferencia').textContent") or ""
    ok("atravessando" in txt, "lista as peças se atravessando")
    ok("borda" in txt, "lista o furo perto da borda")
    ok("sem marca" in txt, "lista as peças sem marca")
    n_col = jsj("return [...document.querySelectorAll('.painel-conferencia details')].filter(d => d.querySelector('summary').textContent.includes('atravessando')).map(d => d.querySelectorAll('li').length).reduce((a, b) => a + b, 0);")
    ok(n_col == 1, f"só o par que se atravessa (não a viga encostada em cima): {n_col}")
    js("[...document.querySelectorAll('.painel-conferencia details')].find(d => d.querySelector('summary').textContent.includes('atravessando')).querySelector('li').click(); 1")
    aba.drenar(0.5)
    sel = set(jsj("return [...editor.selecao.ids];") or [])
    ok(sel == {ids["viga1"], ids["viga2"]}, "clicar no achado seleciona as duas vigas")
    erros("Conferência")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
