# -*- coding: utf-8 -*-
"""A tela das Cenas (usuário, 11/11: "a tela de tratamento, criação, exportação, renderização das cenas"; amostra-4 aprovada
em Projeto/BRIEFINGS/imagens/cenas-3d/): visor3d/cena.html com as cenas do 3D e as da foto. Pela tela, com cliques de verdade:
  A. os cartões: a cena da foto que já existe; "+ Nova cena pela vista" → a caixa do nome → a cena do 3D nova, em destaque,
     com o tratamento à direita e o QUADRO da imagem 16:9 no palco; a miniatura chega ao cartão;
  B. a proporção 4:3: o quadro muda e o servidor guarda; Ctrl+Z volta a 16:9;
  C. o fundo transparente: o render em PNG, 4:3, com os cantos vazados; o céu: o render em JPEG com o céu azul em cima;
  D. girar o 3D marca a vista como mudada; "Atualizar a cena com esta vista" grava a câmera nova; a lente muda o quadro e a
     câmera gravada;
  E. o estilo: cores por camada e sem arestas, no visor e no servidor;
  F. o cartão da foto abre a cena da foto (a foto no palco, sem o quadro); o do 3D volta com o quadro;
  H. a marca d'água: o padrão B (a empresa do projeto), a prévia, o render com a placa no canto e sem ela ("sem"), a faixa C;
  G. botão direito no cartão: Duplicar e Apagar; sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_tela_cenas (para conferir de olho)."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_tela_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_tela_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-11T00:00:00", "alterado": "2026-11-11T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
FOTO_DIR = os.path.join(DADOS, "obra", "cenas", "dados", "quadra")
os.makedirs(FOTO_DIR)
Image.new("RGB", (120, 90), (120, 110, 95)).save(os.path.join(FOTO_DIR, "foto.jpg"), "JPEG")
json.dump({"id": "quadra", "nome": "Quadra", "foto": "foto.jpg", "px": [120, 90], "pares": [], "camera": None, "opacidade": 1.0,
           "criada": "2026-11-01T08:00:00", "alterada": "2026-11-01T08:00:00"},
          open(os.path.join(FOTO_DIR, "cena.json"), "w", encoding="utf-8"))
# a marca d'água: um logo em faixa como o da Hermes (o nome numa ponta, o símbolo na outra), em cor e claro
from PIL import ImageDraw
os.makedirs(os.path.join(DADOS, "fabrica", "marca"))
for nome, cor in (("logo.png", (53, 67, 76, 255)), ("logo_claro.png", (255, 255, 255, 255))):
    im = Image.new("RGBA", (1772, 229), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle((82, 68, 564, 145), fill=cor); d.rectangle((1621, 68, 1690, 145), fill=(195, 215, 115, 255))
    im.save(os.path.join(DADOS, "fabrica", "marca", nome))
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
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button=botao, clickCount=1)
    aba.drenar(0.2)
    return True


def tecla(aba, key, code=None, mod=0, vk=0):
    for tipo in ("rawKeyDown", "keyUp"):
        aba.cmd("Input.dispatchKeyEvent", type=tipo, key=key, code=code or key, modifiers=mod, windowsVirtualKeyCode=vk)
    aba.drenar(0.2)


def foto_tela(aba, nome):
    d = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(os.path.join(SAIDA, nome), "wb").write(base64.b64decode(d))


def servidor():
    return {c["id"]: c for c in json.loads(urllib.request.urlopen(API, timeout=30).read())["cenas"]}


def estado(aba):
    return aba.avaliar("JSON.parse(JSON.stringify(cenaApi.estado(), (k, v) => k === 'cena' ? (v && {id: v.id, tipo: v.tipo, proporcao: v.proporcao, fundo: v.fundo}) : v))")


def arquivos(prefixo):
    return [n for n in os.listdir(PASTA_CENAS) if n.startswith(prefixo)] if os.path.isdir(PASTA_CENAS) else []


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_tela_cenas_")
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

    print("A — os cartões e a cena nova pela vista")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    ok(aba.avaliar("[...document.querySelectorAll('#cartoes .cartao-cena')].map(b => b.dataset.cena)") == ["quadra"], "o cartão da cena da foto")
    ok(aba.avaliar("document.getElementById('titulo-obra').textContent") == "Obra Teste", "o nome da obra no alto")
    ok(clicar_no(aba, "#nova-3d"), "clique em + Nova cena pela vista")
    ok(esperar(aba, "!!document.querySelector('#caixa-cena input') && document.activeElement === document.querySelector('#caixa-cena input')", 5),
       "a caixa do nome abre")
    aba.cmd("Input.insertText", text="Fachada")
    tecla(aba, "Enter", vk=13)
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.tipo === '3d' && document.querySelector('.cartao-cena.ativa') && document.querySelector('.cartao-cena.ativa').dataset.cena === 'fachada'", 15),
       "a cena do 3D nova em destaque")
    ok(aba.avaliar("!document.getElementById('corpo3d').hidden && document.getElementById('corpo').hidden"), "o tratamento da cena do 3D à direita")
    q = estado(aba)["quadro"] or {}
    ok(q and abs(q["w"] / q["h"] - 16 / 9) < 0.02 and aba.avaliar("!document.getElementById('quadro').hidden"), f"o quadro 16:9 no palco ({q})")
    ok(esperar(aba, "(() => { const m = document.querySelector('.cartao-cena[data-cena=fachada] .mini'); return !!(m && m.style.backgroundImage); })()", 20),
       "a miniatura chega ao cartão")
    ok(bool(servidor().get("fachada", {}).get("miniatura")), "e ao servidor")
    aba.drenar(1.0)
    foto_tela(aba, "1-cena-nova.png")

    print("B — a proporção e o desfazer")
    clicar_no(aba, "#proporcao [data-v='4:3']")
    aba.drenar(1.0)
    q = estado(aba)["quadro"] or {}
    ok(abs(q.get("w", 0) / max(q.get("h", 1), 1) - 4 / 3) < 0.02, f"o quadro 4:3 ({q})")
    ok(servidor()["fachada"].get("proporcao") == "4:3", "gravada no servidor")
    aba.avaliar("document.activeElement && document.activeElement.blur(); 1")
    tecla(aba, "z", "KeyZ", mod=2, vk=90)
    aba.drenar(1.2)
    ok(estado(aba)["cena"]["proporcao"] == "16:9" and servidor()["fachada"].get("proporcao") == "16:9", "Ctrl+Z volta a 16:9 (tela e servidor)")
    clicar_no(aba, "#proporcao [data-v='4:3']")
    aba.drenar(0.8)

    print("C — o fundo e o render")
    clicar_no(aba, "#fundo3d [data-v=transparente]")
    aba.drenar(0.8)
    ok(aba.avaliar("document.body.classList.contains('fundo-transparente')"), "o fundo transparente na tela (o xadrez)")
    foto_tela(aba, "2-transparente.png")
    aba.avaliar("document.getElementById('render-tamanho').value = 'L1920'; 1")
    clicar_no(aba, "#renderizar")
    ok(esperar(aba, "/Imagem renderizada/.test(document.getElementById('aviso').textContent)", 240), f"o render terminou ({aba.avaliar('document.getElementById(\"aviso\").textContent')})")
    pngs = arquivos("Cena - Fachada (render).png")
    ok(bool(pngs), f"o render em PNG na pasta cenas ({arquivos('Cena - ')})")
    if pngs:
        with Image.open(os.path.join(PASTA_CENAS, pngs[0])) as im:
            ok(im.size == (1920, 1440), f"1920 × 1440 (4:3): {im.size}")
            ok(im.mode == "RGBA" and im.getpixel((2, 2))[3] == 0, f"o canto vazado ({im.mode}, {im.getpixel((2, 2))})")
    ok(esperar(aba, "/render/.test(document.querySelector('.cartao-cena[data-cena=fachada]').textContent)", 10), "o cartão diz que tem render")
    clicar_no(aba, "#fundo3d [data-v=ceu]")
    clicar_no(aba, "#barra-palco [data-vista=frente]")      # de frente: o céu aparece em cima (de cima, só o chão)
    aba.drenar(0.8)
    clicar_no(aba, "#renderizar")
    ok(esperar(aba, "/render\\).jpg/.test(document.getElementById('aviso').textContent)", 240), "o render do céu terminou")
    jpgs = arquivos("Cena - Fachada (render).jpg")
    if jpgs:
        with Image.open(os.path.join(PASTA_CENAS, jpgs[0])) as im:
            r, g, b = im.convert("RGB").getpixel((10, 10))
            ok(b > r + 20, f"o céu azul em cima ({(r, g, b)})")
    else:
        ok(False, "o render do céu em JPEG")

    print("D — a vista e a lente")
    cam0 = servidor()["fachada"]["camera"]
    r = aba.avaliar("(() => { const q = document.getElementById('palco').getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; })()")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=r[0], y=r[1], button="left", clickCount=1)
    for k in range(1, 10):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0] + 12 * k, y=r[1] + 3 * k, button="left", buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=r[0] + 108, y=r[1] + 27, button="left", clickCount=1)
    aba.drenar(0.5)
    ok(estado(aba)["vistaMudou"] is True and aba.avaliar("document.getElementById('atualizar-vista').classList.contains('pendente')"),
       "girar marca a vista como mudada")
    clicar_no(aba, "#atualizar-vista")
    aba.drenar(1.0)
    cam1 = servidor()["fachada"]["camera"]
    ok(cam1["posicao"] != cam0["posicao"] and estado(aba)["vistaMudou"] is False, "Atualizar grava a câmera nova")
    aba.avaliar("(() => { const l = document.getElementById('lente3d'); l.value = 30; l.dispatchEvent(new Event('input')); })(); 1")
    aba.drenar(1.2)
    ok(abs(estado(aba)["fovCena"] - 30) < 0.01 and abs(servidor()["fachada"]["camera"]["fov"] - 30) < 0.01, "a lente de 30° na tela e no servidor")
    ok("lente 30°" in aba.avaliar("document.getElementById('quadro-rotulo').textContent"), "o quadro diz a lente")

    print("E — o estilo")
    cor0 = aba.avaliar("Array.from(visor.corBase.slice(0, 30)).join()")
    clicar_no(aba, "#pintar3d [data-v=camada]")
    clicar_no(aba, "#arestas3d [data-v='0']")
    aba.drenar(1.0)
    ok(aba.avaliar("Array.from(visor.corBase.slice(0, 30)).join()") != cor0, "cores por camada no visor")
    ok(aba.avaliar("visor.arestasLigadas") is False, "sem arestas no visor")
    s = servidor()["fachada"]
    ok(s.get("pintar") == "camada" and s.get("arestas") is False, f"e no servidor ({s.get('pintar')}, {s.get('arestas')})")
    foto_tela(aba, "3-estilo.png")
    aba.drenar(3.0)                                          # a miniatura refeita depois do estilo
    mini = os.path.join(SAIDA, "miniatura.jpg")
    with open(mini, "wb") as f:
        f.write(urllib.request.urlopen(f"{API}/fachada/miniatura.jpg", timeout=30).read())
    with Image.open(mini) as im:
        from PIL import ImageStat
        desvio = max(ImageStat.Stat(im.convert("RGB")).stddev)
        ok(desvio > 12, f"a miniatura tem a obra (não uma cor só: desvio {desvio:.1f})")

    print("H — a marca d'água (o padrão B: o logo em cor numa placa)")
    ok(aba.avaliar("!document.getElementById('marca-bloco').hidden"), "a seção Marca d'água à direita")
    ok(aba.avaliar("[...document.querySelectorAll('#marca-empresa button')].map(b => b.dataset.v)") == ["principal", "sem"],
       "as empresas do cadastro e 'sem'")
    ok(aba.avaliar("document.querySelector('#marca-jeito .ligado').dataset.v === 'B' && document.querySelector('#marca-empresa .ligado').dataset.v === 'principal'"),
       "o padrão: B, a empresa do projeto")
    ok(esperar(aba, "!document.getElementById('marca-previa').hidden", 10), "a prévia por cima do quadro")
    clicar_no(aba, "#fundo3d [data-v=branco]")
    clicar_no(aba, "#barra-palco [data-vista=topo]")
    aba.drenar(0.8)
    def render_jpg():
        for n in arquivos("Cena - Fachada (render)"):
            os.remove(os.path.join(PASTA_CENAS, n))
        aba.avaliar("document.getElementById('aviso').textContent = ''; 1")
        clicar_no(aba, "#renderizar")
        esperar(aba, "/Imagem renderizada/.test(document.getElementById('aviso').textContent)", 240)
        n = arquivos("Cena - Fachada (render).jpg")
        return Image.open(os.path.join(PASTA_CENAS, n[0])).convert("RGB") if n else None
    com_b = render_jpg()
    clicar_no(aba, "#marca-empresa [data-v=sem]")
    aba.drenar(0.8)
    sem = render_jpg()
    from PIL import ImageChops, ImageStat
    if com_b and sem:
        W, H = com_b.size
        canto = (int(W * 0.7), int(H * 0.85), W, H)
        dif = max(ImageStat.Stat(ImageChops.difference(com_b.crop(canto), sem.crop(canto))).mean)
        resto = max(ImageStat.Stat(ImageChops.difference(com_b.crop((0, 0, W // 2, H // 2)), sem.crop((0, 0, W // 2, H // 2)))).mean)
        ok(dif > 4 and resto < 1, f"o render com a placa no canto de baixo à direita e nada no resto (canto {dif:.1f}, resto {resto:.2f})")
        com_b.save(os.path.join(SAIDA, "render-marca-b.jpg"))
    else:
        ok(False, "os dois renders (com e sem a marca)")
    clicar_no(aba, "#marca-empresa [data-v=principal]")
    clicar_no(aba, "#marca-jeito [data-v=C]")
    aba.drenar(0.8)
    com_c = render_jpg()
    if com_c:
        W, H = com_c.size
        faixa = ImageStat.Stat(com_c.crop((0, int(H * 0.97), W, H)).convert("L")).mean[0]
        ok(faixa < 110, f"a faixa C escura no rodapé (luz {faixa:.0f})")
        com_c.save(os.path.join(SAIDA, "render-marca-c.jpg"))
    m = servidor()["fachada"].get("marca") or {}
    ok(m.get("empresa") == "principal" and m.get("jeito") == "C", f"a marca gravada na cena ({m})")
    clicar_no(aba, "#marca-jeito [data-v=B]")
    aba.drenar(0.6)

    print("F — a cena da foto na mesma tela")
    clicar_no(aba, ".cartao-cena[data-cena=quadra]")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'quadra' && !document.getElementById('foto').hidden", 30), "a cena da foto abre (a foto no palco)")
    ok(aba.avaliar("document.getElementById('quadro').hidden && !document.getElementById('corpo').hidden && document.getElementById('corpo3d').hidden"),
       "sem o quadro, com o painel da foto")
    ok(aba.avaliar("visor.arestasLigadas") is True, "o estilo de sempre de volta (arestas)")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada' && !document.getElementById('quadro').hidden", 30), "e a do 3D volta com o quadro")
    ok(aba.avaliar("visor.arestasLigadas") is False and abs(estado(aba)["fovCena"] - 30) < 0.01, "com o estilo e a lente dela")

    print("G — duplicar e apagar pelo cartão")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]", "right")
    ok(esperar(aba, "!!document.querySelector('#menu-cartao')", 5), "o menu do cartão")
    clicar_no(aba, "#menu-cartao [data-acao='Duplicar']")
    ok(esperar(aba, "document.querySelectorAll('#cartoes .cartao-cena').length === 3", 15), "duplicada (3 cartões)")
    copia = [i for i, c in servidor().items() if c.get("nome") == "Fachada (cópia)"]
    ok(bool(copia) and servidor()[copia[0]].get("proporcao") == "4:3", "a cópia com o enquadramento")
    aba.avaliar("window.confirm = () => true; 1")
    clicar_no(aba, f".cartao-cena[data-cena='{copia[0] if copia else ''}']", "right")
    clicar_no(aba, "#menu-cartao [data-acao='Apagar…']")
    ok(esperar(aba, "document.querySelectorAll('#cartoes .cartao-cena').length === 2", 15), "apagada (2 cartões)")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print(f"\ncapturas em {SAIDA}")
print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
