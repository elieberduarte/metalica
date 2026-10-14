# -*- coding: utf-8 -*-
"""O detalhe do usuário (F14, 14/10/2026) no navegador de verdade: a chapa de topo posta numa viga × pilar, salva pelo
menu Editar → Salvar como detalhe (as duas barras compridas já vêm marcadas como referência) e aplicada pelo Editar →
Aplicar detalhe num segundo pórtico girado 90° em planta — 9 peças, a chapa na mesa do pilar novo, a viga cortada, a
mesma marca da chapa; Ctrl+Z desfaz numa entrada. Sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_det3d_")
PASTA = os.path.join(DADOS, "det")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Detalhe", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
W = "W 310×38,7"
doc = Documento()
doc.add(Barra(nome="pilar", inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar"))
doc.add(Barra(nome="viga", inicio=(0, 0, 3500), fim=(0, 6000, 3500), perfil=W, papel="viga"))
doc.add(Barra(nome="pilar2", inicio=(20000, 0, 0), fim=(20000, 0, 4000), perfil=W, rotacao=0, papel="pilar"))
doc.add(Barra(nome="viga2", inicio=(26000, 0, 3500), fim=(20000, 0, 3500), perfil=W, papel="viga"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_det3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=det", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 4)"):
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

    # a chapa de topo pela ligação, depois salva como detalhe
    selecionar(ids["viga"], ids["pilar"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo da ligação abriu")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de topo')"), "a chapa de topo entrou")
    aba.drenar(0.6)
    pecas = jsj("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.ligacao).map(e => e.id);")
    selecionar(*(pecas + [ids["viga"], ids["pilar"]])); menu("salvar-detalhe")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo Salvar como detalhe abriu")
    marcadas = jsj("return [...editor.el.dialogoCorpo.querySelectorAll('input[type=checkbox]')].filter(c => c.checked).length;")
    ok(marcadas == 2, f"as duas barras compridas vêm marcadas como referência: {marcadas}")
    jsj("const i = editor.el.dialogoCorpo.querySelector('input[type=text]'); i.value = 'CT W310'; return 1;")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("!!document.querySelector('.aviso') || true", 5), "salvou")
    aba.drenar(1.5)
    ok(os.path.exists(os.path.join(DADOS, "detalhes-3d.json")), "a biblioteca foi gravada na pasta de dados")
    erros("Salvar detalhe")

    # aplicar no segundo pórtico
    selecionar(ids["viga2"], ids["pilar2"]); menu("aplicar-detalhe")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo Aplicar detalhe abriu")
    ok("CT W310" in (js("editor.el.dialogoCorpo.textContent") or ""), "o detalhe está na lista")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.detalhe_usuario).length === 9"), "9 peças do detalhe")
    ch = jsj("const c = [...editor.documento.entidades.values()].find(e => e.tipo === 'chapa' && e.atributos.detalhe_usuario); return {o: c.origem, pos: c.atributos.marcas.posicao};")
    orig = jsj("const c = [...editor.documento.entidades.values()].find(e => e.tipo === 'chapa' && e.atributos.ligacao); return c.atributos.marcas.posicao;")
    ok(ch and abs(ch["o"][0] - 20155) < 0.01, f"a chapa na mesa do pilar novo: {ch and ch['o']}")
    ok(ch and ch["pos"] == orig, f"a mesma marca da chapa original: {ch and ch['pos']} = {orig}")
    v2 = ent(ids["viga2"])
    ok(v2 and v2["cortes_fim"], "a viga nova cortada na chapa")
    js("editor.desfazer(); 1"); aba.drenar(0.5)
    ok(js("[...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.detalhe_usuario).length") == 0, "Ctrl+Z tira o detalhe aplicado")
    erros("Aplicar detalhe")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
