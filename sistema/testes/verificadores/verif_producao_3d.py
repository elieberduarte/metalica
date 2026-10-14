# -*- coding: utf-8 -*-
"""A informação de produção feita à mão no editor 3D (onda 1, 14/10/2026), no navegador de verdade. Num projeto
sintético — dois pilares W com a placa de base (Chapa paramétrica, sem marcas), um banzo com um montante em cima e um
retângulo empurrado (sólido feito à mão) — confere pelos menus e pelo painel:
  1. Editar → Numerar peças dá P e M a tudo; pilares iguais na mesma posição; Ctrl+Z desfaz numa entrada só;
  2. Criar conjunto (pilar + base) duas vezes: a mesma marca M para as duas cópias, o pilar como peça principal;
  3. Soldar (pilar × base): o diálogo acha o encontro, a perna digitada fica gravada nas peças das duas posições;
  4. o painel "Produção" mostra a solda, a peça principal, e grava fase e acabamento;
  5. Converter em chapa: o retângulo empurrado vira Chapa paramétrica de 12,5 mm;
  6. o detalhamento do modelo gravado sai com o conjunto de 2 cópias e a solda definida (perna 8);
  7. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Chapa, Documento, Solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_prod3d_")
PASTA = os.path.join(DADOS, "prod")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Produção", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
W = "W 310×38,7"
doc = Documento()
for i, x in enumerate((0.0, 5000.0)):
    doc.add(Barra(nome="pilar%d" % (i + 1), inicio=(x, 0, 0), fim=(x, 0, 3000), perfil=W, papel="pilar"))
    doc.add(Chapa(nome="base%d" % (i + 1), origem=(x - 200, -200, -25), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                  contorno=[(0, 0), (400, 0), (400, 400), (0, 400)], espessura=25.0, centrada=False))
doc.add(Barra(nome="banzo", inicio=(10000, 0, 0), fim=(13000, 0, 0), perfil=W, papel="banzo"))
doc.add(Barra(nome="montante", inicio=(11500, 0, 155), fim=(11500, 0, 1155), perfil=W, papel="montante"))
vs = [(x, y, z) for z in (0.0, 12.5) for (x, y) in ((20000, 0), (20300, 0), (20300, 200), (20000, 200))]
fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
doc.add(Solido(nome="placa à mão", vertices=vs, faces=fs))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_prod3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=prod", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 7)"):
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
    def confirmar():
        ok(esperar("editor.el.dialogo.open", 20), "o diálogo abriu")
        js("editor.el.dialogoOk.click(); 1"); aba.drenar(0.3)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ids = jsj("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    def marcas(nome): return jsj(f"return (editor.documento.get('{ids[nome]}').atributos || {{}}).marcas || {{}};")
    def atr(nome): return jsj(f"return editor.documento.get('{ids[nome]}').atributos || {{}};")
    def selecionar(*nomes): js(f"editor.selecao.definir({json.dumps([ids[n] for n in nomes])}); 1"); aba.drenar(0.3)

    # 1) Numerar
    menu("numerar")
    ok(esperar(f"!!((editor.documento.get('{ids['base2']}').atributos || {{}}).marcas || {{}}).posicao"), "Numerar deu marca às peças")
    p1, p2, b1, b2 = marcas("pilar1"), marcas("pilar2"), marcas("base1"), marcas("base2")
    ok(p1.get("posicao") and p1["posicao"] == p2.get("posicao") and b1.get("posicao") == b2.get("posicao") != p1["posicao"],
       f"pilares iguais numa posição, bases noutra: {p1.get('posicao')} {p2.get('posicao')} {b1.get('posicao')} {b2.get('posicao')}")
    ok(p1.get("conjunto") and b1.get("conjunto") and p1["conjunto"] != b1["conjunto"], f"cada solta no conjunto da posição: {p1.get('conjunto')} {b1.get('conjunto')}")
    js("editor.desfazer(); 1"); aba.drenar(0.3)
    ok(not marcas("pilar1").get("posicao"), "Ctrl+Z tira a numeração numa entrada só")
    js("editor.refazer(); 1"); aba.drenar(0.3)
    ok(marcas("pilar1").get("posicao") == p1["posicao"], "Refazer volta as marcas")
    erros("Numerar")

    # 2) Criar conjunto duas vezes
    selecionar("pilar1", "base1"); menu("criar-conjunto"); confirmar()
    ok(esperar(f"!!((editor.documento.get('{ids['base1']}').atributos.marcas || {{}}).instancia)"), "o primeiro conjunto foi criado")
    selecionar("pilar2", "base2"); menu("criar-conjunto"); confirmar()
    ok(esperar(f"!!((editor.documento.get('{ids['base2']}').atributos.marcas || {{}}).instancia)"), "o segundo conjunto foi criado")
    aba.drenar(0.5)
    p1, p2, b1, b2 = marcas("pilar1"), marcas("pilar2"), marcas("base1"), marcas("base2")
    ok(p1["conjunto"] == b1["conjunto"] == p2["conjunto"] == b2["conjunto"], f"as duas cópias com a mesma marca: {p1['conjunto']} {p2['conjunto']}")
    ok(p1["instancia"] != p2["instancia"] and p1["instancia"] == b1["instancia"], "uma instância por cópia")
    ok(p1.get("principal") and not b1.get("principal"), "o pilar (a barra mais comprida) é a peça principal")
    erros("Criar conjunto")

    # 3) Soldar pilar × base
    selecionar("pilar1", "base1"); menu("soldar")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo Soldar abriu")
    txt = js("editor.el.dialogoCorpo.textContent") or ""
    ok("perna mínima" in txt and "×" in txt, f"o diálogo lista o encontro: {txt[:140]!r}")
    js("(() => { const i = editor.el.dialogoCorpo.querySelector('input[type=number]'); i.value = '8'; return 1; })()")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar(f"!!editor.documento.get('{ids['pilar2']}').atributos.soldas"), "a solda foi gravada")
    s_p2, s_b1 = atr("pilar2").get("soldas") or {}, atr("base1").get("soldas") or {}
    d = s_p2.get(b1["posicao"]) or {}
    ok(d.get("perna") == 8 and d.get("tipo") == "filete" and d.get("local") == "fabrica", f"a outra cópia do pilar tem a solda com a base: {d}")
    ok(p1["posicao"] in s_b1, "a base tem a solda pela posição do pilar")
    erros("Soldar")

    # 4) Painel Produção
    selecionar("pilar1"); aba.drenar(0.6)
    painel = js("editor.el.props.textContent") or ""
    ok("Produção" in painel and f"Solda × {b1['posicao']}" in painel and "Peça principal" in painel, "o painel mostra produção, solda e peça principal")
    jsj("""const g = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Fase / lote');
          const i = g.nextElementSibling; i.value = 'Lote 2'; i.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.4)
    ok(atr("pilar1").get("fase") == "Lote 2", "a fase digitada no painel fica na peça")
    erros("Painel")

    # 5) Converter em chapa
    selecionar("placa à mão"); menu("converter-chapa")
    ok(esperar(f"editor.documento.get('{ids['placa à mão']}') && editor.documento.get('{ids['placa à mão']}').tipo === 'chapa'"), "o sólido virou chapa")
    c = jsj(f"const c = editor.documento.get('{ids['placa à mão']}'); return {{esp: c.espessura, n: (c.contorno || []).length}};")
    ok(c and c["esp"] == 12.5 and c["n"] == 4, f"chapa de 12,5 com 4 cantos: {c}")
    js("editor.desfazer(); 1"); aba.drenar(0.3)
    ok(js(f"editor.documento.get('{ids['placa à mão']}').tipo") == "solido", "Ctrl+Z volta o sólido")
    js("editor.refazer(); 1"); aba.drenar(0.3)
    erros("Converter")

    # 6) o detalhamento do modelo gravado
    js("editor.salvar(); 1")
    aba.drenar(3.0)
    m = json.load(open(os.path.join(PASTA, "modelo.json"), encoding="utf-8"))
    from nucleo3d.modelo import Documento as _D
    from nucleo2d.detalhar import detalhar
    dg = _D.de_dict(m)
    r = detalhar(dg, regra_tercas=False, converter=False)
    cj = [x for x in r["conjuntos"] if p1["conjunto"] in x.get("marcas", [])]
    ok(cj and cj[0]["instancias"] == 2, f"o detalhamento tem o conjunto {p1['conjunto']} com 2 cópias: {cj and cj[0].get('instancias')}")
    textos = [e.texto for e in r["desenhos"]["conjuntos"].entidades.values() if getattr(e, "camada", "") == "SOLDA" and hasattr(e, "texto")]
    ok("8" in textos and any("conforme os símbolos" in t for t in textos), f"a prancha do conjunto tem a solda de 8 mm: {textos[:4]}")
    erros("Final")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
