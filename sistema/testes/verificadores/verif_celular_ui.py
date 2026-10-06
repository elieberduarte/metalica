# -*- coding: utf-8 -*-
"""Acesso pelo celular, de ponta a ponta (app.py --dev): no computador, o botão Celular da tela inicial,
ligar o acesso e o QR code; no celular emulado (390 × 844, toque), sem par nada abre, o QR pareia, a
lista mostra o projeto, o pacote é preparado no computador, o 3D abre e o toque dá a ficha da peça, os
quantitativos, o resumo em PDF no leitor (pdf.js) com zoom, o diagnóstico e a fluidez; no computador,
o aparelho aparece e, removido, perde o acesso; desligado, a porta fecha.

O servidor do celular sobe só no 127.0.0.1 de uma porta livre (no programa de verdade ele escuta na
rede). Porta livre para o programa também: nunca a 8765/8766."""
import base64, json, os, shutil, socket, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

# o celular entra pelas extensões do desenvolvimento do app.py (as mesmas do pré-moldado); a cópia que
# ainda não as tem (a do HEAD, enquanto elas estão só na cópia de trabalho) pula, sem falhar
if "import celular.web" not in open(os.path.join(BASE, "app.py"), encoding="utf-8").read():
    print("  pulado: o app.py desta cópia não carrega o acesso pelo celular (extensões do desenvolvimento)")
    print()
    print("FALHAS: 0")
    sys.exit(0)

PORTA = _porta_livre()
PORTA_CEL = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_celui_")
proj = os.path.join(DADOS, "obra-celular")
os.makedirs(os.path.join(proj, "detalhamento"))
json.dump({"nome": "Obra do celular", "alterado": "2026-10-06T01:00:00", "dados_resumo": {"revisao": "R01"}},
          open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
json.dump({"gerado": "2026-10-06 01:00", "totais": {"peso": 1520.4, "pecas": 67, "posicoes": 2, "conjuntos": 0,
                                                    "categorias": [{"categoria": "BARRAS", "titulo": "Barras", "peso": 1200, "pct": 79}]},
           "posicoes": [{"marca": "P1", "nome": "V1", "categoria": "BARRAS", "perfil": "W 200×22,5", "quantidade": 1, "comprimento": 6000,
                         "peso": 135.0, "peso_total": 135.0}, {"marca": "P2", "categoria": "CHAPAS", "classe": "Chapa", "perfil": "CH 12,5",
                                                               "quantidade": 5, "peso": 8.8, "peso_total": 44.0}],
           "perfis": [{"perfil": "W 200×22,5", "pecas": 1, "comprimento_m": 6, "peso": 135, "barras": {"comprimento": 12000, "quantidade": 1, "aproveitamento": 50}}],
           "chapas": [], "telhas": [], "conjuntos": [], "acessorios": [{"nome": "Parafuso M16", "quantidade": 60}]},
          open(os.path.join(proj, "detalhamento", "lista-de-materiais.json"), "w", encoding="utf-8"))
import pymupdf
doc = pymupdf.open()
for i in range(2):
    pg = doc.new_page(width=842, height=595)
    pg.insert_text((60, 80), "Resumo da obra - folha %d" % (i + 1), fontsize=28)
    pg.draw_rect(pymupdf.Rect(60, 120, 780, 540), color=(0, 0, 0.6), width=2)
doc.save(os.path.join(proj, "detalhamento", "resumo-da-obra.pdf"))
doc.close()

amb = dict(os.environ, METALICA_CELULAR_PORTA=str(PORTA_CEL), METALICA_CELULAR_HOST="127.0.0.1", PYTHONIOENCODING="utf-8")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.4)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def chrome(largura, altura, dpr, celular):
    exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celui_")
    p = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                          "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    a = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): a.cmd(f"{dm}.enable")
    a.cmd("Emulation.setDeviceMetricsOverride", width=largura, height=altura, deviceScaleFactor=dpr, mobile=celular)
    if celular:
        a.cmd("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        a.cmd("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36")
    return p, perfil, a


def tocar(aba, x, y):
    aba.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
    aba.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])


navs = []
try:
    for _ in range(40):
        try:
            _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    p1, perf1, pc = chrome(1400, 860, 1, False); navs.append((p1, perf1))
    cel = f"http://127.0.0.1:{PORTA_CEL}"
    # ------------------------------------------------------------------ computador
    pc.navegar(base + "/", limite=60)
    ok(esperar(pc, "!!document.getElementById('btn-celular')", 20), "a tela inicial do dev ganha o botão Celular")
    if os.path.isfile(os.path.join(BASE, "web", "premoldado", "dev_inicio.js")):      # o script da tela inicial junta os dois
        ok(esperar(pc, "!!document.querySelector('.topo .marca.trocavel')", 10), "a troca de área do pré-moldado continua na tela inicial")
    pc.avaliar("document.getElementById('btn-celular').click()")
    ok(esperar(pc, "location.pathname === '/acesso-celular' && document.getElementById('estado-texto').textContent === 'Desligado'", 20),
       "a tela Acesso pelo celular abre desligada")
    try:
        socket.create_connection(("127.0.0.1", PORTA_CEL), timeout=1).close(); ok(False, "desligado: a porta do celular está fechada")
    except OSError:
        ok(True, "desligado: a porta do celular está fechada")
    pc.avaliar("document.getElementById('interruptor').click()")
    ok(esperar(pc, "!!document.querySelector('#qr svg') && document.getElementById('estado-texto').textContent.indexOf('Ligado') === 0", 20),
       "ligado: o QR code aparece")
    url = pc.avaliar("document.getElementById('endereco').textContent") or ""
    ok("/celular/parear?c=" in url, f"o QR leva ao pareamento: {url[:60]}…")
    codigo = url.split("?c=")[1].split("http")[0].strip() if "?c=" in url else ""
    foto(pc, "celular_1_pc.png")
    # ------------------------------------------------------------------ celular
    p2, perf2, ap = chrome(390, 844, 3, True); navs.append((p2, perf2))
    ap.navegar(cel + "/celular/", limite=30)
    ok(esperar(ap, "document.body && document.body.innerText.indexOf('ainda não está ligado') >= 0", 15), "sem par: o celular só vê o aviso")
    ap.navegar(cel + "/celular/parear?c=" + codigo, limite=30)
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 1", 20), "pareado: a lista mostra o projeto")
    ok(esperar(ap, "document.getElementById('conexao').textContent.indexOf('No PC') === 0", 5), "o selo diz que está ligado ao PC")
    foto(ap, "celular_2_lista.png")
    ap.avaliar("document.querySelector('.projeto').click()")
    t0 = time.time()
    ok(esperar(ap, "window.visor && window.visor.fichas && !document.querySelector('.carregando')", 120),
       "o pacote é preparado no computador e o 3D abre (%.0f s)" % (time.time() - t0))
    alvo = ap.avaliar("""(() => { const v = window.visor; let m = -1, k = 0; v.fichas.forEach((f, i) => { if (v.visivelCamada[f.c] !== false && (f.kg || 0) > k) { k = f.kg; m = i; } });
        const [x, y] = v.paraTela(m); const r = v.tela.getBoundingClientRect(); return [x + r.left, y + r.top, m]; })()""")
    tocar(ap, alvo[0], alvo[1])
    ok(esperar(ap, "!document.getElementById('folha').hidden && !!document.querySelector('.ficha dl')", 10), "tocar a peça abre a ficha")
    foto(ap, "celular_3_3d.png")
    ap.avaliar("document.querySelector('[data-aba=quantitativos]').click()")
    ok(esperar(ap, "document.querySelectorAll('#itens .cartao').length === 2", 15), "quantitativos: as posições em cartões")
    ap.avaliar("document.querySelector('[data-aba=resumos]').click()")
    ok(esperar(ap, "!!document.querySelector('a.documento')", 15), "resumos: o PDF do resumo listado")
    ap.avaliar("document.querySelector('a.documento').click()")
    ok(esperar(ap, "(() => { const c = document.querySelector('#pagina-pdf canvas'); return c && c.width > 300; })()", 40),
       "o leitor (pdf.js) desenha a folha")
    w1 = ap.avaliar("document.querySelector('#pagina-pdf canvas').width")
    ap.avaliar("document.getElementById('zoom-mais').click()")
    ok(esperar(ap, f"document.querySelector('#pagina-pdf canvas').width > {w1} * 1.4", 20), "o zoom redesenha a folha maior e nítida")
    ap.avaliar("document.getElementById('pg-prox').click()")
    ok(esperar(ap, "document.getElementById('pg-num').textContent.indexOf('2 de 2') === 0", 20), "passa para a folha 2")
    foto(ap, "celular_4_leitor.png")
    ap.avaliar("location.hash = '#/diagnostico'")
    ok(esperar(ap, "document.querySelectorAll('.ficha dt').length >= 8", 15), "diagnóstico: os números do aparelho")
    ok(esperar(ap, "!!document.getElementById('medir')", 5), "diagnóstico: o último 3D aberto e o botão de medir")
    ap.avaliar("document.getElementById('medir').click()")
    ok(esperar(ap, "(document.querySelector('#folha .nome') || {}).textContent && document.querySelector('#folha .nome').textContent.indexOf('quadros por segundo') > 0", 60),
       "a medida de fluidez roda e mostra os quadros por segundo")
    foto(ap, "celular_5_fluidez.png")
    # métodos que gravam: recusados também para o aparelho pareado
    st = ap.avaliar("fetch('/celular/dados/projetos.json', {method: 'POST', body: '{}'}).then(r => r.status)")
    ok(st == 405, f"POST pelo celular pareado: {st}")
    # ------------------------------------------------------------------ obra: a cópia guardada, sem o computador
    ok(esperar(ap, "(() => { try { const g = JSON.parse(localStorage.getItem('guardados') || '{}'); return g['obra-celular'] && g['obra-celular'].completo; } catch (e) { return false; } })()", 60),
       "o projeto aberto fica guardado no aparelho (pacote inteiro)")
    pc.avaliar("document.getElementById('interruptor').click()")                # o celular "sai para a obra"
    ok(esperar(pc, "document.getElementById('estado-texto').textContent === 'Desligado'", 10), "obra: o computador some da rede")
    ap.navegar(cel + "/celular/", limite=30)
    r = esperar(ap, "document.querySelectorAll('.projeto').length === 1 && document.getElementById('conexao').textContent.indexOf('Sem rede') === 0", 30)
    ok(r, "sem rede: a lista abre da cópia e o selo diz de quando ela é")
    if not r:
        print("        na tela:", (ap.avaliar("document.getElementById('conexao').textContent + ' | ' + document.body.innerText.slice(0, 300)") or "").replace("\n", " "))
        print("        cópia:", ap.avaliar("Promise.all(['dados/projetos.json', 'api/estado'].map(u => fetch(u).then(r => r.status + ' ' + r.headers.get('X-Metalica-Copia')).catch(e => 'erro ' + e))).then(x => x.join(' | '))"),
              "| controlada:", ap.avaliar("!!navigator.serviceWorker.controller"))
    ok(esperar(ap, "document.body.innerText.indexOf('no aparelho') >= 0", 5), "o projeto aparece como guardado no aparelho")
    ap.avaliar("document.querySelector('.projeto').click()")
    ok(esperar(ap, "window.visor && window.visor.fichas && !document.querySelector('.carregando') && window.visor.nPecas === 67", 60),
       "sem rede: o 3D abre da cópia")
    ap.avaliar("location.hash = '#/leitor/obra-celular/resumo-da-obra.pdf/1'")
    ok(esperar(ap, "(() => { const c = document.querySelector('#pagina-pdf canvas'); return c && c.width > 300; })()", 40),
       "sem rede: o PDF abre da cópia")
    foto(ap, "celular_6_sem_rede.png")
    pc.avaliar("document.getElementById('interruptor').click()")                # de volta ao escritório
    ok(esperar(pc, "document.getElementById('estado-texto').textContent.indexOf('Ligado') === 0", 10), "de volta: o computador na rede")
    ap.navegar(cel + "/celular/", limite=30)
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 1 && document.getElementById('conexao').textContent.indexOf('No PC') === 0", 30),
       "de volta à rede: o selo diz que está no PC de novo, sem parear outra vez")
    # ------------------------------------------------------------------ computador: aparelhos
    ok(esperar(pc, "document.querySelectorAll('[data-remover]').length === 1", 15), "o aparelho aparece na lista do computador")
    nome = pc.avaliar("document.querySelector('.aparelhos td').textContent") or ""
    ok("Android" in nome, f"com o nome do aparelho: {nome!r}")
    pc.avaliar("window.confirm = () => true; document.querySelector('[data-remover]').click()")
    ok(esperar(pc, "document.querySelectorAll('[data-remover]').length === 0", 10), "remover tira o aparelho")
    st = ap.avaliar("fetch('/celular/dados/projetos.json').then(r => r.status)")
    ok(st == 401, f"o aparelho removido perde o acesso na hora: {st}")
    pc.avaliar("document.getElementById('interruptor').click()")
    ok(esperar(pc, "document.getElementById('estado-texto').textContent === 'Desligado'", 10), "desligar")
    time.sleep(0.5)
    try:
        socket.create_connection(("127.0.0.1", PORTA_CEL), timeout=1).close(); ok(False, "desligado de novo: a porta fecha")
    except OSError:
        ok(True, "desligado de novo: a porta fecha")
    for nome_aba, a in (("computador", pc), ("celular", ap)):
        erros = [m for m in a.console if m[0] in ("error", "excecao") and "401" not in str(m) and "405" not in str(m)]
        ok(not erros, f"sem erros no console do {nome_aba}: {erros[:3]}")
finally:
    for p, perf in navs:
        try: p.kill()
        except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    for _p, perf in navs: shutil.rmtree(perf, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
