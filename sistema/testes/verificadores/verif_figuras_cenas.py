# -*- coding: utf-8 -*-
"""As figuras da cena do 3D (usuário, 12/11: "o que sugere criarmos para refinar essa parte de montagem de cenas?" → "pode
começar"; amostra-9 aprovada: "os dois, por cena", árvores do fundo "é assim, com 3 densidades", pôr "como as luzes"). Na tela
das Cenas, com cliques de verdade:
  A. + Pessoa e três cliques no chão: três pessoas no 3D e no servidor (continua pondo até o Esc); o Esc termina;
  B. + Carro: o carro de frente para o prédio (giro num eixo); ↻ gira 45°; 📍 muda de lugar; ✕ tira; ↶ desfaz;
  C. as figuras fazem sombra: na sombra do sol o grupo das figuras fica à vista (o resto do que não é modelo some);
  D. o render: com as figuras a imagem muda onde elas estão;
  E. o estilo: "pelo ambiente" colorido no Dia e maquete branca no Estúdio; "coloridas" no Estúdio volta à cor;
  F. árvores no fundo (Entorno › Grama › médio): muitas árvores, nenhuma do lado da câmera; gravado no servidor;
  G. Copiar ajustes › Pessoas, veículos e árvores para outra cena; Duplicar leva as figuras e o entorno;
  H. sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_figuras_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, base64, io
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image, ImageChops
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_figuras_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_figuras_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
API = f"{base}/api/projetos/obra/terreno/cenas"
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


def clicar_xy(aba, fx, fy):
    q = aba.avaliar("(() => { const r = document.getElementById('palco').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
    x, y = q[0] + q[2] * fx, q[1] + q[3] * fy
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button="left", clickCount=1)
    aba.drenar(0.6)


def esc(aba):
    for t in ("rawKeyDown", "keyUp"):
        aba.cmd("Input.dispatchKeyEvent", type=t, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.3)


def servidor():
    return {c["id"]: c for c in json.loads(urllib.request.urlopen(API, timeout=30).read())["cenas"]}


def itens_do_servidor(aba, cena, n, lim=10):
    t0 = time.time()
    while time.time() - t0 < lim:
        it = (servidor()[cena].get("figuras") or {}).get("itens") or []
        if len(it) == n: return it
        aba.drenar(0.3)
    return (servidor()[cena].get("figuras") or {}).get("itens") or []


def render(aba, nome):
    url = aba.avaliar("cenaApi.imagemDaCena3d(960, 540, 1, null, false).then(c => c.toDataURL('image/png'))")
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
    im.save(os.path.join(SAIDA, nome))
    return im


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_figuras_cenas_")
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
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    aba.avaliar("cenaApi.novaCena3d('Fachada'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada'", 30), "a cena do 3D")
    clicar_no(aba, "#barra-palco [data-vista=frente]")
    clicar_no(aba, "#atualizar-vista")
    aba.drenar(1.0)
    clicar_no(aba, "#ambiente3d [data-v=ceu]"); aba.drenar(0.5)
    im0 = render(aba, "sem-figuras.png")

    print("A — + Pessoa e três cliques no chão")
    ok(aba.avaliar("!!document.getElementById('sec-figuras') && document.querySelectorAll('.bt-figuras button').length === 8"),
       "a seção Pessoas, veículos e árvores com os 8 tipos")
    clicar_no(aba, ".bt-figuras [data-tipo=pessoa]")
    ok(aba.avaliar("document.body.classList.contains('colocando-luz') && !document.getElementById('dica-figura').hidden"),
       "+ Pessoa: espera o clique no chão, com a dica")
    for fx in (0.40, 0.47, 0.54):
        clicar_xy(aba, fx, 0.88)
    it = itens_do_servidor(aba, "fachada", 3)
    ok(len(it) == 3 and all(f["tipo"] == "pessoa" for f in it), f"três pessoas no servidor ({[f['tipo'] for f in it]})")
    ok(len({f["semente"] for f in it}) == 3, "cada uma com a sua semente (saem diferentes)")
    ok(aba.avaliar("document.body.classList.contains('colocando-luz')"), "continua pondo depois do clique")
    esc(aba)
    ok(aba.avaliar("!document.body.classList.contains('colocando-luz')"), "o Esc termina")
    clicar_xy(aba, 0.6, 0.88)
    ok(len(itens_do_servidor(aba, "fachada", 3, lim=2)) == 3, "depois do Esc o clique não põe mais")
    ok(aba.avaliar("visor.extras.children.some(g => g.isGroup && g.children.length === 3)"), "as três no 3D (no grupo extras)")
    ok(aba.avaliar("document.querySelectorAll('#figuras-lista .item-figura').length") == 3, "a lista com as três")
    ok("3 pessoas" in (aba.avaliar("document.getElementById('res-figuras').textContent") or ""), "o resumo da seção: 3 pessoas")

    print("B — + Carro, girar, mover, tirar, desfazer")
    clicar_no(aba, ".bt-figuras [data-tipo=carro]")
    clicar_xy(aba, 0.30, 0.93)
    esc(aba)
    it = itens_do_servidor(aba, "fachada", 4)
    carro = it[-1] if it else {}
    ok(carro.get("tipo") == "carro" and carro.get("giro") in (0, 90, 180, 270), f"o carro de frente para o prédio (giro {carro.get('giro')})")
    clicar_no(aba, "#figuras-lista .item-figura[data-i='3'] [data-r=girar]")
    t0 = time.time()
    while time.time() - t0 < 8 and (itens_do_servidor(aba, "fachada", 4, lim=1) or [{}])[-1].get("giro") == carro.get("giro"): aba.drenar(0.3)
    g1 = itens_do_servidor(aba, "fachada", 4)[-1]["giro"]
    ok(g1 == (carro["giro"] + 45) % 360, f"↻ gira 45° ({carro.get('giro')} → {g1})")
    clicar_no(aba, "#figuras-lista .item-figura[data-i='3'] [data-r=mover]")
    clicar_xy(aba, 0.70, 0.93)
    t0 = time.time()
    while time.time() - t0 < 8 and itens_do_servidor(aba, "fachada", 4, lim=1)[-1]["p"] == carro["p"]: aba.drenar(0.3)
    p2 = itens_do_servidor(aba, "fachada", 4)[-1]["p"]
    ok(p2 != carro["p"] and aba.avaliar("!document.body.classList.contains('colocando-luz')"), f"📍 muda de lugar com um clique ({carro['p']} → {p2})")
    clicar_no(aba, "#figuras-lista .item-figura[data-i='3'] [data-r=tirar]")
    ok(len(itens_do_servidor(aba, "fachada", 3)) == 3, "✕ tira o carro")
    clicar_no(aba, "#btn-desfazer")
    ok(len(itens_do_servidor(aba, "fachada", 4)) == 4, "↶ desfaz: o carro volta")

    print("C — as figuras fazem sombra (no desenho da sombra do sol o grupo delas fica à vista)")
    vis = aba.avaliar("""(() => { const V = visor, r = V.renderer, orig = r.render.bind(r); let viu = null;
        r.render = (cena, cam) => { if (r.getRenderTarget() === V._alvoSombra) viu = V.extras.visible && V.extras.children.length > 0; return orig(cena, cam); };
        try { V._desenharSombra(); } finally { r.render = orig; } return viu; })()""")
    ok(vis is True, f"o grupo das figuras entra na sombra ({vis})")

    print("D — o render com as figuras")
    im1 = render(aba, "com-figuras.png")
    mudou = sum(ImageChops.difference(im0, im1).convert("L").histogram()[31:])
    ok(mudou > 150, f"a imagem muda onde estão as figuras ({mudou} pixels)")

    print("E — o estilo")
    cores = "(() => { const c = []; visor.extras.traverse(o => { if (o.isMesh && o.material.uniforms && o.material.uniforms.uCor) { const v = o.material.uniforms.uCor.value; c.push(Math.max(v.r, v.g, v.b) - Math.min(v.r, v.g, v.b)); } }); return Math.max(...c); })()"
    ok(aba.avaliar(cores) > 0.2, "pelo ambiente, no Dia: coloridas")
    clicar_no(aba, "#ambiente3d [data-v=estudio]"); aba.drenar(0.6)
    ok(aba.avaliar(cores) < 0.08, f"no Estúdio: maquete branca ({aba.avaliar(cores):.3f})")
    clicar_no(aba, "#figuras-estilo [data-v=cor]"); aba.drenar(0.6)
    ok(aba.avaliar(cores) > 0.2, "coloridas escolhidas no Estúdio: a cor volta")
    t0 = time.time()
    while time.time() - t0 < 8 and (servidor()["fachada"].get("figuras") or {}).get("estilo") != "cor": aba.drenar(0.3)
    ok((servidor()["fachada"].get("figuras") or {}).get("estilo") == "cor", "o estilo gravado na cena")
    clicar_no(aba, "#ambiente3d [data-v=ceu]"); aba.drenar(0.5)

    print("F — árvores no fundo")
    ok(aba.avaliar("document.getElementById('arvores-linha').hidden") is False, "a escolha aparece no Entorno")
    n0 = aba.avaliar("visor.extras.children.find(g => g.children.length >= 4).children.length")
    clicar_no(aba, "#entorno3d [data-v=grama]"); aba.drenar(0.4)
    clicar_no(aba, '#arvores3d [data-v="2"]'); aba.drenar(0.8)
    grupo = "visor.extras.children.find(g => g.children.length >= 4)"
    n1 = aba.avaliar(f"{grupo}.children.length")
    ok(n1 - n0 >= 15, f"as árvores do fundo no 3D ({n1 - n0})")
    lado = aba.avaliar(f"""(() => {{ const V = visor, c = V.caixaVisivel().getCenter(V.camera.position.clone()), o = V.cabecalho.origem;
        const cam = cenaApi.estado().cena.camera.posicao, vx = cam[0] - o[0] - c.x, vy = cam[1] - o[1] - c.y, vn = Math.hypot(vx, vy);
        return {grupo}.children.slice({n0}).map(a => ((a.position.x - c.x) * vx + (a.position.y - c.y) * vy) / (Math.hypot(a.position.x - c.x, a.position.y - c.y) * vn)); }})()""")
    ok(lado and max(lado) <= -0.15 + 1e-6, f"nenhuma do lado da câmera (maior cosseno {max(lado or [9]):.2f})")
    t0 = time.time()
    while time.time() - t0 < 8 and (servidor()["fachada"].get("entorno") or {}).get("arvores") != 2: aba.drenar(0.3)
    ok((servidor()["fachada"].get("entorno") or {}).get("arvores") == 2, "gravado no servidor (entorno.arvores = 2)")
    ok("árvores no fundo" in (aba.avaliar("document.getElementById('res-figuras').textContent") or ""), "o resumo diz árvores no fundo")
    render(aba, "arvores-fundo.png")

    print("G — copiar e duplicar")
    aba.avaliar("cenaApi.novaCena3d('Lateral'); 1")
    esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'lateral'", 30)
    corpo = json.dumps({"de": "fachada", "para": ["lateral"], "grupos": ["figuras"]}).encode()
    urllib.request.urlopen(urllib.request.Request(API + "/copiar", data=corpo, headers={"Content-Type": "application/json"}), timeout=30).read()
    lat = servidor()["lateral"]
    ok(len((lat.get("figuras") or {}).get("itens") or []) == 4, "Copiar ajustes › Pessoas, veículos e árvores leva as 4 figuras")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]")
    esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada'", 30)
    aba.avaliar("""(() => { const c = document.querySelector('.cartao-cena[data-cena=fachada]'); c.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, clientX: 100, clientY: 100})); return 1; })()""")
    aba.drenar(0.4)
    feito = clicar_no(aba, "#menu-cartao [data-acao='Duplicar']")
    if feito:
        t0 = time.time()
        while time.time() - t0 < 10 and not any(i.startswith("fachada-copia") for i in servidor()): aba.drenar(0.3)
    dup = next((c for i, c in servidor().items() if i.startswith("fachada-copia")), None)
    ok(dup is not None and len((dup.get("figuras") or {}).get("itens") or []) == 4 and (dup.get("entorno") or {}).get("arvores") == 2,
       f"Duplicar leva as figuras e o entorno ({feito}, {dup and dup.get('figuras', {}).get('estilo')})")

    print("H — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill(); time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print(f"FALHAS: {len(falhas)}")
for f in falhas: print("  -", f)
sys.exit(1 if falhas else 0)
