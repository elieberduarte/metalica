# -*- coding: utf-8 -*-
"""Dimensionar pelo editor 3D: projeto recebido sem perfil escrito (galpão só de linhas),
"Dimensionar: o perfil mais leve que passa…" com o travamento do banzo inferior informado,
resultado com as trocas, modelo reaberto com os perfis novos e o cálculo gravado."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
import projeto_2d_sem_texto as ex
PORTA = 8795
DADOS = tempfile.mkdtemp(prefix="metalica_dim_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def pedir(rota):
    return json.load(urllib.request.urlopen(base + urllib.parse.quote(rota), timeout=60))


def post(rota, corpo, limite=300):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=limite))
    except urllib.error.HTTPError as e:
        return json.load(e)


def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar_dialogo(aba, titulo, limite=90):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar("(() => { const d = document.querySelector('dialog[open]'); return !!d && d.querySelector('#dialogo-titulo').textContent === %s; })()" % json.dumps(titulo)):
            return True
        aba.drenar(0.5)
    return False


def barras(slug):
    doc = (pedir(f"/api/projetos/{slug}/modelo").get("documento") or {})
    return [e for e in doc.get("entidades") or [] if e.get("tipo") == "barra"]


tmp = tempfile.mkdtemp(prefix="dim_arq_")
dxf = ex.dxf(os.path.join(tmp, "galpao_sem_texto.dxf"))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_dim_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Galpão dimensionar", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    r = post(f"/api/projetos/{slug}/projeto-2d", {"arquivo": "galpao.dxf", "ifc": False,
                                                  "conteudo_b64": base64.b64encode(open(dxf, "rb").read()).decode()})
    ok(bool(r.get("gerado", {}).get("barras")), "modelo 3D gerado do DXF sem texto: %s barras" % r.get("gerado", {}).get("barras"))
    antes = {e["id"]: e.get("perfil") for e in barras(slug)}
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=" + urllib.parse.quote(slug), limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!window.editor && window.editor.projeto === %s && window.editor.documento && window.editor.documento.tamanho > 10" % json.dumps(slug)):
        aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"dimensionar\"]')"), "menu tem 'Dimensionar'")
    aba.avaliar("document.querySelector('[data-acao=\"dimensionar\"]').click(); 1")
    ok(esperar_dialogo(aba, "Dimensionar a estrutura", 30), "diálogo dos parâmetros do dimensionamento")
    ok(aba.avaliar("[...document.querySelectorAll('dialog[open] label')].some(l => l.textContent.startsWith('Correntes por vão de longarina'))"),
       "campo das correntes da longarina")
    aba.avaliar("(() => { const l = [...document.querySelectorAll('dialog[open] label')].find(x => x.textContent.startsWith('Travamento do banzo inferior'));"
                " l.nextElementSibling.value = '3'; return 1; })()")
    foto(aba, "_dimensionar_parametros.png")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar_dialogo(aba, "Dimensionamento", 300), "resultado do dimensionamento")
    txt = aba.avaliar("document.querySelector('dialog[open] #dialogo-corpo').textContent")
    ok("trocaram de perfil" in txt and "kg" in txt, "resumo: " + txt[:180])
    ok(aba.avaliar("document.querySelectorAll('dialog[open] .lista-linhas .linha').length") > 5, "lista das trocas")
    foto(aba, "_dimensionar_resultado.png")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    t0 = time.time()
    # espera o editor reaberto já com as barras trocadas (a máquina pode estar ocupada)
    while time.time() - t0 < 180 and not aba.avaliar(
            "!!window.editor && !!window.editor.documento && !document.querySelector('dialog[open]') && "
            "[...window.editor.documento.entidades.values()].some(e => e.tipo === 'barra' && e.atributos && e.atributos.trocas_de_perfil)"):
        aba.drenar(1.0)
    aba.drenar(3)
    depois = {e["id"]: e for e in barras(slug)}
    trocadas = [e for e in depois.values() if (e.get("atributos") or {}).get("trocas_de_perfil")]
    ok(len(trocadas) > 20, "%d barras trocaram de perfil no modelo do projeto" % len(trocadas))
    ok(all(antes.get(e["id"]) != e.get("perfil") for e in trocadas), "o perfil gravado é o novo")
    doc_tela = aba.avaliar("[...window.editor.documento.entidades.values()].filter(e => e.tipo === 'barra' && e.atributos && e.atributos.trocas_de_perfil).length")
    ok(doc_tela == len(trocadas), "o editor reabriu com os perfis novos (%s)" % doc_tela)
    calc = pedir(f"/api/projetos/{slug}/calculo")
    ok(bool(calc.get("calculo")) and calc["parametros"].get("trava_inferior") == 3.0, "cálculo do modelo novo gravado com os parâmetros")
    aba.avaliar("window.editor.alternarAnalise(); 1"); aba.drenar(3)
    ok(aba.avaliar("!!document.querySelector('.acoes-linha button')"), "painel do cálculo tem o botão Dimensionar")
    foto(aba, "_dimensionar_painel.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
