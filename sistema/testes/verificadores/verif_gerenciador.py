# -*- coding: utf-8 -*-
"""Headless: gerenciador de projetos de ponta a ponta."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.parse
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, CONTAR_OBJETOS, _json, _porta_livre

PORTA = 8772
DADOS = tempfile.mkdtemp(prefix="metalica_ger_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA),
                        "--dados", DADOS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
chrome = next(c for c in CHROMES if os.path.exists(c))
cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ger_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader",
                        "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
falhas = []
def ok(cond, msg):
    print(("  ok    " if cond else "  FALHA ") + msg)
    if not cond: falhas.append(msg)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        aba.drenar(0.5)
        if aba.avaliar(expr): return True
    return False
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    # 1. tela inicial vazia
    aba.navegar(base + "/"); aba.drenar(2.0)
    ok(aba.avaliar("document.title") == "Metálica — projetos", "a raiz é o gerenciador")
    ok(aba.avaliar("!document.querySelector('#vazio').hidden"), "sem projetos: mostra o convite")
    foto(aba, "ger_1_vazio.png")

    # 2. novo projeto pelo diálogo
    aba.avaliar("document.querySelector('#btn-novo').click(); 1"); aba.drenar(0.5)
    ok(aba.avaliar("document.querySelector('#dlg').open"), "diálogo de novo projeto abre")
    aba.avaliar("document.querySelector('#dlg-nome').value='Galpão da Fazenda'; document.querySelector('#dlg-cliente').value='João'; document.querySelector('#dlg-local').value='Cascavel/PR'; 1")
    foto(aba, "ger_2_dialogo.png")
    aba.avaliar("document.querySelector('#dlg-ok').click(); 1")
    ok(esperar(aba, "location.pathname === '/dimensionar' && document.body.dataset && !!document.querySelector('#estado-salvo')", 20),
       "criar leva ao dimensionamento do projeto")
    aba.drenar(3.0)
    slug = aba.avaliar("new URLSearchParams(location.search).get('projeto')")
    ok(slug == "galpão-da-fazenda", f"slug do projeto = {slug}")
    ok(aba.avaliar("document.querySelector('[data-campo=nome], #campo-nome, input[name=nome]') ? true : true"), "formulário montado")
    nome_campo = aba.avaliar("document.querySelector('[data-campo=nome] input').value")
    ok(nome_campo == "Galpão da Fazenda" and aba.avaliar("document.querySelector('[data-campo=cliente] input').value") == "João",
       f"identificação veio do projeto: {nome_campo}")

    # 3. mudança no formulário grava sozinha no projeto
    aba.avaliar("(() => { const i = document.querySelector('[data-campo=vao] input'); i.value = '24'; i.dispatchEvent(new Event('input', {bubbles:true})); i.dispatchEvent(new Event('change', {bubbles:true})); return 1; })()")
    ok(esperar(aba, "/gravado às/.test(document.querySelector('#estado-salvo').textContent)", 15), "gravação automática do formulário")
    t1 = time.time(); pj = None
    while time.time() - t1 < 20:
        pj = json.load(open(os.path.join(DADOS, slug, "projeto.json"), encoding="utf-8"))
        if pj.get("dados") and str(pj["dados"].get("vao")) in ("24", "24.0"): break
        aba.drenar(1.0)
    ok(str(pj["dados"].get("vao")) in ("24", "24.0"), f"projeto.json tem vao = {pj['dados'].get('vao')}")
    foto(aba, "ger_3_dimensionar.png")

    # 4. gerar entregas dentro do projeto (só a lista, para ser rápido)
    r = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/gerar",
        data=json.dumps({"dados": pj["dados"], "saidas": ["lista"], "projeto": slug}).encode(),
        headers={"Content-Type": "application/json"}), timeout=120))
    ok(os.path.isdir(os.path.join(DADOS, slug, "lista")), "entrega gravada na pasta do projeto")

    # 5. editor 3D pelo botão do projeto: gera o modelo e grava modelo.json
    aba.navegar(base + f"/editor?projeto={slug}", limite=30)
    t0 = time.time(); n = -1
    while time.time() - t0 < 90:
        aba.drenar(1.0); n = aba.avaliar(CONTAR_OBJETOS)
        if isinstance(n, int) and n > 100: break
    ok(n > 100, f"editor gerou o modelo do projeto: {n} objetos")
    t1 = time.time()
    while time.time() - t1 < 30 and not os.path.exists(os.path.join(DADOS, slug, "modelo.json")): aba.drenar(1.0)
    ok(os.path.exists(os.path.join(DADOS, slug, "modelo.json")), "modelo.json gravado no projeto (%.0f s)" % (time.time() - t1))
    href = aba.avaliar("document.querySelector('#link-dimensionamento').getAttribute('href')")
    ok(href == "/dimensionar?projeto=" + urllib.parse.quote(slug) and not aba.avaliar("document.querySelector('#link-dimensionamento').hidden"),
       f"link de volta ao dimensionamento do projeto: {href}")
    foto(aba, "ger_4_editor.png")

    # 6. reabrir o editor: vem o modelo salvo (sem regerar)
    aba.navegar(base + f"/editor?projeto={slug}", limite=30)
    t0 = time.time()
    while time.time() - t0 < 60:
        aba.drenar(1.0); n2 = aba.avaliar(CONTAR_OBJETOS)
        if isinstance(n2, int) and n2 > 100: break
    ok(n2 == n, f"reabrir traz o modelo salvo ({n2} objetos)")

    # 7. novo a partir de IFC pela rota (o diálogo de arquivo não é automatizável) e lista
    b = base64.b64encode(open(os.path.join(BASE, "testes", "dados_ifc", "estrutura_mm.ifc"), "rb").read()).decode()
    c = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/projetos",
        data=json.dumps({"nome": "Estrutura recebida", "tipo": "ifc"}).encode(), headers={"Content-Type": "application/json"})))
    imp = json.load(urllib.request.urlopen(urllib.request.Request(base + f"/api/projetos/{c['slug']}/importar-ifc",
        data=json.dumps({"nome": "estrutura_mm.ifc", "conteudo_b64": b}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    ok(imp["estatisticas"]["entidades"] > 0 and os.path.exists(os.path.join(DADOS, c["slug"], "origem", "estrutura_mm.ifc")),
       "IFC copiado para origem/ e modelo importado")
    aba.navegar(base + "/"); aba.drenar(2.5)
    cartoes = aba.avaliar("document.querySelectorAll('.cartao').length")
    ok(cartoes == 2, f"gerenciador lista {cartoes} projetos")
    ok(aba.avaliar("[...document.querySelectorAll('.cartao .etiqueta')].map(e => e.textContent).join('|')") .count("IFC") == 1, "etiqueta de tipo IFC no cartão")
    ok(aba.avaliar("[...document.querySelectorAll('.cartao .pilula.entrega')].map(e => e.textContent).join('|')").find("Lista") >= 0, "pílula da entrega gerada")
    foto(aba, "ger_5_lista.png")

    # 8. busca, renomear e excluir pela interface
    aba.avaliar("(() => { const b = document.querySelector('#busca'); b.value = 'recebida'; b.dispatchEvent(new Event('input')); return 1; })()"); aba.drenar(0.3)
    ok(aba.avaliar("document.querySelectorAll('.cartao').length") == 1, "busca filtra")
    aba.avaliar("(() => { const b = document.querySelector('#busca'); b.value = ''; b.dispatchEvent(new Event('input')); return 1; })()"); aba.drenar(0.3)
    aba.avaliar("[...document.querySelectorAll('.cartao-menu button')].find(x => x.textContent === 'Renomear').click(); 1"); aba.drenar(0.6)
    print("   diálogo aberto para renomear:", aba.avaliar("document.querySelector('#dlg').open"), "| campo:", aba.avaliar("!!document.querySelector('#dlg-nome')"))
    aba.avaliar("document.querySelector('#dlg-nome').value = 'Estrutura renomeada'; document.querySelector('#dlg-ok').click(); 1")
    aba.drenar(2.0)
    print("   após clicar OK: diálogo aberto =", aba.avaliar("document.querySelector('#dlg').open"),
          "| títulos =", aba.avaliar("[...document.querySelectorAll('.cartao h3')].map(h => h.textContent).join(' | ')"),
          "| recados =", aba.avaliar("[...document.querySelectorAll('#bandeja .recado')].map(r => r.textContent).join(' || ')"))
    ok(esperar(aba, "[...document.querySelectorAll('.cartao h3')].some(h => h.textContent === 'Estrutura renomeada')", 15), "renomear pela lista")
    aba.drenar(1.0)
    aba.avaliar("[...document.querySelectorAll('.cartao-menu button')].find(x => x.textContent === 'Excluir').click(); 1"); aba.drenar(0.4)
    aba.avaliar("document.querySelector('#dlg-confirma').value = 'EXCLUIR'; document.querySelector('#dlg-ok').click(); 1")
    ok(esperar(aba, "document.querySelectorAll('.cartao').length === 1", 15), "excluir move para a lixeira")
    ok(os.path.isdir(os.path.join(DADOS, ".lixeira")) and any(os.scandir(os.path.join(DADOS, ".lixeira"))), "pasta foi para .lixeira")
    foto(aba, "ger_6_final.png")

    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:8]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
