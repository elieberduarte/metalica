# -*- coding: utf-8 -*-
"""A janela Renderizar e exportar da tela das Cenas (usuário, 11/11: "a tela de tratamento, criação, exportação, renderização
das cenas"; amostra-5 aprovada em Projeto/BRIEFINGS/imagens/cenas-3d/). Pela tela, com cliques de verdade:
  A. Exportar… abre a janela com a prévia (a cena como vai sair) e o tamanho; Esta cena, Full HD, JPG, gravar → o render
     1920 × 1080 na pasta cenas/ da obra, com o céu;
  B. Todas as cenas, rápida, PDF → um PDF com uma página por cena do 3D na proporção dela; a cena da foto sem encaixe fica de
     fora, dito no fim; a tela volta à cena de antes;
  C. Várias (as duas do 3D), PNG, só baixar → um ZIP com os dois PNG (1920 × 1080 e 1920 × 1440), nada novo na pasta;
  D. Cancelar no meio do render: para no bloco, diz "Cancelado", a tela volta a renderizar;
  E. sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_exportar_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, base64, zipfile, io, re
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_exportar_cenas_")
BAIXADOS = tempfile.mkdtemp(prefix="metalica_exportar_baixados_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_exportar_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-11T00:00:00", "alterado": "2026-11-11T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
FOTO_DIR = os.path.join(DADOS, "obra", "cenas", "dados", "quadra")      # uma cena da foto ainda sem encaixe
os.makedirs(FOTO_DIR)
Image.new("RGB", (120, 90), (120, 110, 95)).save(os.path.join(FOTO_DIR, "foto.jpg"), "JPEG")
json.dump({"id": "quadra", "nome": "Quadra", "foto": "foto.jpg", "px": [120, 90], "pares": [], "camera": None, "opacidade": 1.0,
           "criada": "2026-11-01T08:00:00", "alterada": "2026-11-01T08:00:00"},
          open(os.path.join(FOTO_DIR, "cena.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
API = f"{base}/api/projetos/obra/terreno/cenas"
PASTA_CENAS = os.path.join(DADOS, "obra", "cenas")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def clicar_no(aba, sel, botao="left"):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button=botao, clickCount=1)
    aba.drenar(0.2)
    return True


def marcar(aba, sel, ligado=True):
    """Liga/desliga a caixa (ou escolhe o rádio) pelo clique, só se precisar."""
    if aba.avaliar(f"document.querySelector({json.dumps(sel)}).checked") != ligado:
        clicar_no(aba, sel)


def foto_tela(aba, nome):
    d = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(os.path.join(SAIDA, nome), "wb").write(base64.b64decode(d))


def na_pasta():
    return sorted(n for n in os.listdir(PASTA_CENAS) if n != "dados") if os.path.isdir(PASTA_CENAS) else []


def lote(aba, limite=300):
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    clicar_no(aba, "#exportar-ir")
    esperar(aba, "!!window.ultimoLoteCenas", limite)
    return aba.avaliar("window.ultimoLoteCenas")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_exportar_cenas_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=900, deviceScaleFactor=1, mobile=False)
    aba.cmd("Page.setDownloadBehavior", behavior="allow", downloadPath=BAIXADOS)

    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    # duas cenas do 3D: Fachada (16:9, céu, de frente) e Lateral (4:3)
    aba.avaliar("cenaApi.novaCena3d('Fachada'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada'", 30), "a cena Fachada")
    clicar_no(aba, "#barra-palco [data-vista=frente]")
    clicar_no(aba, "#atualizar-vista")
    aba.drenar(1.0)
    aba.avaliar("cenaApi.novaCena3d('Lateral'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'lateral'", 30), "a cena Lateral")
    clicar_no(aba, "#proporcao [data-v='4:3']")
    aba.drenar(1.0)
    clicar_no(aba, ".cartao-cena[data-cena=fachada]")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada' && !!cenaApi.estado().quadro", 30), "de volta à Fachada")
    aba.drenar(1.0)

    print("A — a janela, a prévia e esta cena em JPG")
    ok(clicar_no(aba, "#exportar"), "clique em Exportar…")
    ok(esperar(aba, "!!document.getElementById('exportar-caixa')", 5), "a janela Renderizar e exportar abre")
    ok(esperar(aba, "/url\\(/.test(document.getElementById('exportar-previa').style.backgroundImage)", 30), "a prévia da cena como vai sair")
    marcar(aba, "#exportar-caixa input[name=quais][value=esta]")
    marcar(aba, "#exportar-caixa input[name=lado][value='1920']")
    marcar(aba, "#exportar-caixa input[name=qualidade][value=refinada]")
    marcar(aba, "#exportar-caixa input[name=formato][value=jpg]")
    marcar(aba, "#exportar-gravar", True); marcar(aba, "#exportar-baixar", False); marcar(aba, "#exportar-abrir", False)
    ok(aba.avaliar("document.getElementById('exportar-varias').offsetHeight === 0"), "com Esta cena, a lista das várias escondida")
    ok(aba.avaliar("(() => { const c = document.getElementById('exportar-caixa'), h = c.querySelector('header');"
                   " return c.scrollTop === 0 && h.getBoundingClientRect().top >= c.getBoundingClientRect().top; })()"),
       "o título da janela à vista (a caixa não rola com os cliques)")
    info = aba.avaliar("document.getElementById('exportar-info').textContent")
    ok("Fachada" in info and "1.920 × 1.080" in info and "JPG" in info, f"o resumo: a cena, o tamanho e o formato ({info})")
    marca = aba.avaliar("document.getElementById('exportar-marca').textContent")
    ok(bool(marca.strip()), f"a marca d'água da cena dita na janela ({marca})")
    foto_tela(aba, "1-janela.png")
    r = lote(aba)
    ok(r and not r["erro"] and r["gravados"] == ["Cena - Fachada (render).jpg"], f"o render gravado ({r})")
    arq = os.path.join(PASTA_CENAS, "Cena - Fachada (render).jpg")
    if os.path.isfile(arq):
        im = Image.open(arq).convert("RGB")
        ok(im.size == (1920, 1080), f"1920 × 1080 ({im.size})")
        rr, gg, bb = im.getpixel((960, 8))
        ok(bb > rr + 25, f"o céu azul em cima ({rr}, {gg}, {bb})")
    else:
        ok(False, "o arquivo do render na pasta cenas")
    ok(esperar(aba, "/Pronto: 1 cena/.test(document.getElementById('exportar-situacao').textContent)", 5),
       f"o fim dito na janela ({aba.avaliar('document.getElementById(\"exportar-situacao\").textContent')})")

    print("B — todas as cenas num PDF (a da foto sem encaixe fica de fora)")
    marcar(aba, "#exportar-caixa input[name=quais][value=todas]")
    marcar(aba, "#exportar-caixa input[name=qualidade][value=rapida]")
    marcar(aba, "#exportar-caixa input[name=formato][value=pdf]")
    ok(aba.avaliar("document.getElementById('exportar-ir').textContent") == "Renderizar 3 cenas", "o botão diz quantas")
    r = lote(aba)
    ok(r and not r["erro"] and r["paginas"] == 2 and r["gravados"] == ["Cenas - Obra Teste (render).pdf"], f"o PDF gravado com 2 páginas ({r})")
    ok(r and len(r["pulados"]) == 1 and r["pulados"][0].startswith("Quadra"), "a cena da foto sem encaixe ficou de fora")
    ok("Ficaram de fora: Quadra" in aba.avaliar("document.getElementById('exportar-situacao').textContent"), "e isso é dito na janela")
    pdf = os.path.join(PASTA_CENAS, "Cenas - Obra Teste (render).pdf")
    if os.path.isfile(pdf):
        b = open(pdf, "rb").read()
        caixas = re.findall(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", b)
        prop = [round(float(w) / float(h), 2) for w, h in caixas]
        ok(b.startswith(b"%PDF-") and b.rstrip().endswith(b"%%EOF") and prop == [1.78, 1.33], f"uma página por cena, na proporção dela ({prop})")
        try:
            from pypdf import PdfReader
            ok(len(PdfReader(pdf).pages) == 2, "o PDF abre num leitor de PDF (pypdf)")
        except ImportError:
            pass
        shutil.copy(pdf, os.path.join(SAIDA, "cenas.pdf"))
    else:
        ok(False, "o PDF na pasta cenas")
    ok(aba.avaliar("cenaApi.estado().cena.id") == "fachada", "a tela volta à cena de antes")

    print("C — várias cenas em PNG, só baixar: o ZIP")
    antes = na_pasta()
    marcar(aba, "#exportar-caixa input[name=quais][value=varias]")
    for i in ("fachada", "lateral"): marcar(aba, f"#exportar-varias input[value={i}]", True)
    marcar(aba, "#exportar-varias input[value=quadra]", False)
    marcar(aba, "#exportar-caixa input[name=formato][value=png]")
    marcar(aba, "#exportar-gravar", False); marcar(aba, "#exportar-baixar", True)
    r = lote(aba)
    ok(r and not r["erro"] and r["baixados"] == ["Cena - Fachada (render).png", "Cena - Lateral (render).png"], f"os dois PNG ({r})")
    zipado = os.path.join(BAIXADOS, "Cenas - Obra Teste (render).zip")
    t0 = time.time()
    while not os.path.isfile(zipado) and time.time() - t0 < 20: time.sleep(0.3)
    if os.path.isfile(zipado):
        with zipfile.ZipFile(zipado) as z:
            ok(z.testzip() is None, "o ZIP abre e confere (CRC)")
            tam = {n: Image.open(io.BytesIO(z.read(n))).size for n in z.namelist()}
        ok(tam == {"Cena - Fachada (render).png": (1920, 1080), "Cena - Lateral (render).png": (1920, 1440)}, f"cada uma no tamanho dela ({tam})")
    else:
        ok(False, f"o ZIP baixado ({os.listdir(BAIXADOS)})")
    ok(na_pasta() == antes, "nada novo na pasta da obra")

    print("D — Cancelar no meio")
    marcar(aba, "#exportar-caixa input[name=quais][value=todas]")
    marcar(aba, "#exportar-caixa input[name=lado][value='4961']")
    marcar(aba, "#exportar-caixa input[name=qualidade][value=refinada]")
    marcar(aba, "#exportar-caixa input[name=formato][value=jpg]")
    marcar(aba, "#exportar-gravar", True); marcar(aba, "#exportar-baixar", False)
    antes = na_pasta()
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    clicar_no(aba, "#exportar-ir")
    ok(esperar(aba, "/bloco \\d+ de \\d+/.test(document.getElementById('exportar-situacao').textContent)", 60),
       f"a barra diz a cena e o bloco ({aba.avaliar('document.getElementById(\"exportar-situacao\").textContent')})")
    foto_tela(aba, "2-renderizando.png")
    ok(aba.avaliar("document.getElementById('exportar-cancelar').textContent") == "Cancelar", "o botão vira Cancelar")
    clicar_no(aba, "#exportar-cancelar")
    ok(esperar(aba, "!!window.ultimoLoteCenas", 60) and aba.avaliar("window.ultimoLoteCenas.erro") == "cancelado", "cancelado")
    ok(aba.avaliar("/^Cancelado/.test(document.getElementById('exportar-situacao').textContent)"), "a janela diz Cancelado")
    ok(na_pasta() == antes, "nada gravado")
    ok(aba.avaliar("!document.getElementById('renderizar').disabled && !cenaApi.estado().cena.__x"), "a tela volta a renderizar")
    clicar_no(aba, "#exportar-cancelar")
    ok(esperar(aba, "!document.getElementById('exportar-caixa')", 5), "Fechar fecha a janela")

    print("F — o acesso rápido à pasta (11/11: \"um acesso rápido a pasta para encontrar o arquivo\")")
    # o pedido de abrir o Explorador é guardado aqui, sem abrir janela nenhuma na máquina
    aba.avaliar("""window.pedidosMostrar = []; const f0 = window.fetch;
      window.fetch = (u, o) => { if (String(u).endsWith('/cenas/mostrar')) { window.pedidosMostrar.push(JSON.parse(o.body).nome);
        return Promise.resolve(new Response('{"pasta": "x"}', { headers: { 'Content-Type': 'application/json' } })); } return f0(u, o); }; 1""")
    ultimo = lambda: aba.avaliar("window.pedidosMostrar[window.pedidosMostrar.length - 1]")
    clicar_no(aba, "#exportar")
    esperar(aba, "!!document.getElementById('exportar-caixa')", 5)
    ok(aba.avaliar("document.getElementById('exportar-pasta').offsetHeight === 0"), "antes do lote, sem o botão da pasta")
    marcar(aba, "#exportar-caixa input[name=quais][value=esta]")
    marcar(aba, "#exportar-caixa input[name=lado][value=tela]")
    marcar(aba, "#exportar-caixa input[name=qualidade][value=rapida]")
    marcar(aba, "#exportar-caixa input[name=formato][value=jpg]")
    marcar(aba, "#exportar-gravar", True); marcar(aba, "#exportar-baixar", False); marcar(aba, "#exportar-abrir", True)
    r = lote(aba)
    ok(r and r["gravados"] == ["Cena - Fachada (render).jpg"] and ultimo() == "Cena - Fachada (render).jpg",
       f"abrir a pasta quando terminar: com o render selecionado ({aba.avaliar('window.pedidosMostrar')})")
    ok(clicar_no(aba, "#exportar-pasta") and esperar(aba, "window.pedidosMostrar.length === 2", 5) and ultimo() == "Cena - Fachada (render).jpg",
       "📁 Mostrar na pasta no fim do lote")
    clicar_no(aba, "#exportar-cancelar")
    esperar(aba, "!document.getElementById('exportar-caixa')", 5)
    aba.avaliar("document.getElementById('render-tamanho').value = 'L1920'; document.getElementById('aviso').textContent = ''; 1")
    clicar_no(aba, "#renderizar")
    ok(esperar(aba, "!!document.querySelector('#aviso .mostrar-pasta')", 240), "depois do Renderizar, o botão Mostrar na pasta no aviso")
    n = len(aba.avaliar("window.pedidosMostrar"))
    clicar_no(aba, "#aviso .mostrar-pasta")
    ok(esperar(aba, f"window.pedidosMostrar.length === {n + 1}", 5) and ultimo() == "Cena - Fachada (render).jpg", "e ele seleciona o render")
    clicar_no(aba, "#pasta-cenas")
    ok(esperar(aba, f"window.pedidosMostrar.length === {n + 2}", 5) and ultimo() == "", "📁 Pasta no alto abre a pasta cenas")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]", "right")
    ok(clicar_no(aba, "#menu-cartao [data-acao='Mostrar o render na pasta']") and esperar(aba, f"window.pedidosMostrar.length === {n + 3}", 5)
       and ultimo() == "Cena - Fachada (render).jpg", "no cartão: Mostrar o render na pasta")
    clicar_no(aba, ".cartao-cena[data-cena=lateral]", "right")
    ok(aba.avaliar("!document.querySelector(\"#menu-cartao [data-acao='Mostrar o render na pasta']\")"), "a cena sem render não tem o item")

    aba.avaliar("document.getElementById('menu-cartao') && document.getElementById('menu-cartao').remove(); 1")

    print("E — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True); shutil.rmtree(BAIXADOS, ignore_errors=True)

print(f"\ncapturas em {SAIDA}")
print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
