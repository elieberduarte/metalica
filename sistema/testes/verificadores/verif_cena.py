# -*- coding: utf-8 -*-
"""A cena (26/10, o usuário: "criar cena… para poder encaixar certinho o 3D na imagem"): a estrutura numa foto do local.

A "foto" é feita aqui por uma câmera conhecida (de pé, a 1,6 m do chão, lente de 70°), com 6 pontos do chão marcados —
como os cantos e o meio das linhas de uma quadra (o caso da Kaefer: os pontos de referência no chão, a estrutura ainda
não existe na foto). Pela tela, com cliques de verdade:
  1. a foto entra como cena nova (a rota do terreno) e a página abre nela;
  2. para cada ponto: "+ Ponto", o clique na foto, a vista vai para o 3D, o clique no mesmo ponto do chão;
  3. no 4º ponto o encaixe sai sozinho; com os 6, a lente volta 70° (±2°) e o erro fica abaixo de 3 px;
  4. Salvar imagem: a foto com o 3D em <projeto>/cenas/, no tamanho da foto;
  5. sem erros no console.
Porta livre, nunca a 8765/8766."""
import json, math, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _caixa_solido
from PIL import Image, ImageDraw

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cena_")

# a obra: 5 pilares atrás da quadra (y = 16 m), do chão (z = 0) a 6 m
ents = []
for k in range(5):
    e = _caixa_solido("pil%d" % k, 2000.0 + 5000.0 * k, 16000.0, 0.0, a=300, b=300, c=6000, camada="Pilares")
    e["material"] = "Aço"
    ents.append(e)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"nome": "obra", "tipo": "ifc", "alterado": "2026-10-26T20:00:00"}, open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "obra", "unidade": "mm", "entidades": ents, "camadas": {"Pilares": {"nome": "Pilares", "cor": "#888888", "visivel": True}},
           "materiais": {}}, open(os.path.join(DADOS, "obra", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

# a câmera da "foto" (como a do three.js: olha para −Z, o eixo z do mundo para cima)
W, H, FOV = 1600, 1200, 70.0
OLHO, ALVO = (-6000.0, -14000.0, 1600.0), (11000.0, 8000.0, 1500.0)


def _sub(a, b): return [a[i] - b[i] for i in range(3)]
def _norm(a): n = math.sqrt(sum(x * x for x in a)); return [x / n for x in a]
def _cruz(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _esc(a, b): return sum(a[i] * b[i] for i in range(3))


zc = _norm(_sub(OLHO, ALVO)); xc = _norm(_cruz([0, 0, 1], zc)); yc = _cruz(zc, xc)


def projetar(X):
    d = _sub(X, OLHO)
    p = [_esc(d, xc), _esc(d, yc), _esc(d, zc)]
    t = math.tan(math.radians(FOV / 2))
    x, y = p[0] / -p[2] / (t * W / H), p[1] / -p[2] / t
    return ((x + 1) / 2, (1 - y) / 2)


CHAO = [(0, 0, 0), (20000, 0, 0), (20000, 10000, 0), (0, 10000, 0), (10000, 0, 0), (10000, 10000, 0)]
im = Image.new("RGB", (W, H), (120, 110, 95))
dr = ImageDraw.Draw(im)
uvs = [projetar(X) for X in CHAO]
for (u, v) in uvs:
    dr.ellipse((u * W - 6, v * H - 6, u * W + 6, v * H + 6), fill=(230, 40, 40))
FOTO = os.path.join(DADOS, "foto-teste.jpg")
im.save(FOTO, "JPEG", quality=95)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        aba.ws.settimeout(10)
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        finally: aba.ws.settimeout(120)
        aba.drenar(0.25)
    return False


def clicar(aba, x, y):
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button="left", clickCount=1)


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cena_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
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
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)

    # 1. a foto entra pela rota do terreno (o envio binário, como o botão Nova cena faz)
    req = urllib.request.Request(base + "/api/projetos/obra/terreno/cenas/nova", data=open(FOTO, "rb").read(), method="POST",
                                 headers={"Content-Type": "application/octet-stream", "X-Nome-Arquivo": "foto-teste.jpg"})
    cena = json.loads(urllib.request.urlopen(req, timeout=60).read())
    ok(cena.get("id") == "foto-teste" and cena.get("px") == [W, H], f"a foto virou a cena ({cena.get('id')}, {cena.get('px')})")
    # a entrada pelo botão Cenas do modo ver (26/10: "essas cenas deveriam ter um menu próprio, vamos separar isso do terreno"
    # — a obra aqui nem tem terreno)
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!window.ver3dPronto && !!document.getElementById('btn-cenas')", 90), "o modo ver tem o botão Cenas (sem terreno)")
    aba.avaliar("document.getElementById('btn-cenas').click(); 1")
    ok(esperar(aba, "location.pathname === '/visor3d/cena.html' && !!window.cenaPronta && !document.getElementById('foto').hidden", 90),
       "o botão abre as cenas da obra, na cena que já existe")
    aba.navegar(base + "/visor3d/cena.html?projeto=obra&cena=foto-teste", limite=60)
    ok(esperar(aba, "!!window.cenaPronta && !document.getElementById('foto').hidden", 90), "a página da cena abriu com a foto")

    # 2. os 6 pontos: o clique na foto e o mesmo ponto do chão no 3D
    FOTO_NA_TELA = "(() => { const r = document.getElementById('marcas').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()"
    NO_3D = """(() => { const v = window.visor, o = v.cabecalho.origem, r = v.tela.getBoundingClientRect();
      v.camera.updateMatrixWorld(); const p = v.camera.position.clone().set(%s - o[0], %s - o[1], %s - o[2]).project(v.camera);
      return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; })()"""
    for k, (X, (u, v)) in enumerate(zip(CHAO, uvs)):
        aba.avaliar("document.getElementById('novo-ponto').click(); 1")
        esperar(aba, "cenaApi.estado().marcando && cenaApi.estado().marcando.etapa === 'foto'", 5)
        fx, fy, fw, fh = aba.avaliar(FOTO_NA_TELA)
        clicar(aba, fx + u * fw, fy + v * fh)
        ok(esperar(aba, "cenaApi.estado().modo === '3d' && cenaApi.estado().marcando && cenaApi.estado().marcando.etapa === '3d'", 10),
           f"ponto {k + 1}: o clique na foto leva ao 3D")
        # a vista do 3D de cima, com a quadra inteira (a pessoa gira e aproxima até ver o ponto; o enquadrar de saída
        # mostra só os pilares)
        aba.avaliar("""(() => { const v = window.visor, o = v.cabecalho.origem;
          v.controles.target.set(10000 - o[0], 6000 - o[1], -o[2]); v.camera.position.set(10000 - o[0], -9000 - o[1], 30000 - o[2]);
          v.controles.update(); v.pedirQuadro(); return 1; })()""")
        aba.drenar(0.4)
        x3, y3 = aba.avaliar(NO_3D % X)
        clicar(aba, x3, y3)
        ok(esperar(aba, f"!cenaApi.estado().marcando && cenaApi.estado().cena.pares[{k}].modelo", 15),
           f"ponto {k + 1}: o clique no chão do 3D completa o par")
        m = aba.avaliar(f"cenaApi.estado().cena.pares[{k}].modelo")
        ok(m and math.dist(m, X) < 150, f"ponto {k + 1}: o ponto do chão no 3D cai onde devia ({[round(c) for c in m or []]} × {list(X)})")
        if k == 3:
            ok(esperar(aba, "!!cenaApi.estado().cena.camera && cenaApi.estado().modo === 'foto'", 15), "no 4º ponto o encaixe sai sozinho")
    esperar(aba, "cenaApi.estado().cena.pares.length === 6 && !!cenaApi.estado().cena.camera && cenaApi.estado().modo === 'foto'", 15)
    cam = aba.avaliar("cenaApi.estado().cena.camera") or {}
    ok(abs((cam.get("fov") or 0) - FOV) < 2 and (cam.get("erro_px") or 99) < 3,
       f"com os 6 pontos: a lente de {FOV:.0f}° volta ({cam.get('fov', 0):.1f}°) e o erro é pequeno ({cam.get('erro_px')} px)")
    ok(cam.get("posicao") and math.dist(cam["posicao"], OLHO) < 600, f"e a câmera fica onde a foto foi tirada ({[round(c) for c in cam.get('posicao') or []]} × {list(OLHO)})")
    aba.drenar(1.0)
    dados = aba.cmd("Page.captureScreenshot", format="png")["data"]
    import base64
    open(os.path.join(os.path.dirname(__file__), "cena_encaixada.png"), "wb").write(base64.b64decode(dados))

    # o ajuste fino (26/10: "movimentar esse segundo ponto um pouco para cima ou para o lado"): o ponto 2 escolhido pela
    # lista, Shift+→ três vezes (30 px da tela) — o encaixe acompanha e grava; arrastado de volta com o mouse, o erro volta
    aba.avaliar("document.querySelector('#pares [data-escolher=\"1\"] span').click(); 1")
    ok(esperar(aba, "cenaApi.estado().selecionado === 1 && !!document.querySelector('#marcas .marca.sel')", 5), "clicar na linha escolhe o ponto 2 (a marca acesa)")
    fx, fy, fw, fh = aba.avaliar(FOTO_NA_TELA)
    erro0 = aba.avaliar("cenaApi.estado().cena.camera.erro_px")
    for _ in range(3):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="ArrowRight", code="ArrowRight", windowsVirtualKeyCode=39, modifiers=8)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="ArrowRight", code="ArrowRight", windowsVirtualKeyCode=39, modifiers=8)
    aba.drenar(1.5)
    u2 = aba.avaliar("cenaApi.estado().cena.pares[1].foto[0]")
    ok(u2 and abs((u2 - uvs[1][0]) * fw - 30) < 1.5, f"Shift+→ ×3: o ponto 2 andou 30 px na tela ({(u2 - uvs[1][0]) * fw:.1f} px)")
    erro1 = aba.avaliar("cenaApi.estado().cena.camera.erro_px")
    ok(erro1 > erro0 + 1, f"o encaixe acompanhou o ponto fora do lugar (erro {erro0:.2f} → {erro1:.2f} px)")
    req = urllib.request.urlopen(base + "/api/projetos/obra/terreno/cenas/foto-teste", timeout=30)
    gravado = json.loads(req.read())
    ok(abs(gravado["pares"][1]["foto"][0] - u2) < 1e-9, "e o ponto movido ficou gravado")
    x0, y0 = fx + u2 * fw, fy + uvs[1][1] * fh
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", clickCount=1)
    for k in range(1, 7):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x0 - 30 * k / 6, y=y0, button="left", buttons=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x0 - 30, y=y0, button="left", clickCount=1)
    aba.drenar(1.5)
    u3 = aba.avaliar("cenaApi.estado().cena.pares[1].foto[0]")
    erro2 = aba.avaliar("cenaApi.estado().cena.camera.erro_px")
    ok(u3 and abs((u3 - uvs[1][0]) * fw) < 1.5 and erro2 < 3, f"arrastado de volta: no lugar ({(u3 - uvs[1][0]) * fw:.1f} px) e o erro de novo pequeno ({erro2:.2f} px)")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    ok(esperar(aba, "cenaApi.estado().selecionado === null", 3), "Esc solta o ponto")

    # os pontos depois da cena montada (26/10: "não consigo… excluir/editar os pontos de vínculo da imagem com o 3D"):
    # apagar o 6º, refazer o 5º na foto e no 3D — o encaixe se refaz e continua bom
    aba.avaliar("document.querySelector('#pares [data-acao=apagar][data-i=\"5\"]').click(); 1")
    ok(esperar(aba, "cenaApi.estado().cena.pares.length === 5", 10), "o ✕ apaga o ponto 6")
    aba.avaliar("document.querySelector('#pares [data-acao=foto][data-i=\"4\"]').click(); 1")
    ok(esperar(aba, "cenaApi.estado().marcando && cenaApi.estado().marcando.etapa === 'foto' && cenaApi.estado().marcando.i === 4", 5),
       "\"foto\" no ponto 5: marcar de novo na foto")
    fx, fy, fw, fh = aba.avaliar(FOTO_NA_TELA)
    clicar(aba, fx + uvs[4][0] * fw, fy + uvs[4][1] * fh)
    ok(esperar(aba, "!cenaApi.estado().marcando && cenaApi.estado().modo === 'foto' && document.getElementById('aviso').textContent.includes('Encaixado')", 10),
       "o clique na foto troca o ponto 5, refaz o encaixe e volta à foto")
    aba.avaliar("document.querySelector('#pares [data-acao=\"3d\"][data-i=\"4\"]').click(); 1")
    ok(esperar(aba, "cenaApi.estado().modo === '3d' && cenaApi.estado().marcando && cenaApi.estado().marcando.i === 4", 5),
       "\"3D\" no ponto 5: marcar de novo no 3D (o botão respondia antes só em teoria: data-par-3d)")
    aba.avaliar("""(() => { const v = window.visor, o = v.cabecalho.origem;
      v.controles.target.set(10000 - o[0], 6000 - o[1], -o[2]); v.camera.position.set(10000 - o[0], -9000 - o[1], 30000 - o[2]);
      v.controles.update(); v.pedirQuadro(); return 1; })()""")
    aba.drenar(0.4)
    clicar(aba, *aba.avaliar(NO_3D % CHAO[4]))
    ok(esperar(aba, "!cenaApi.estado().marcando && cenaApi.estado().modo === 'foto'", 15), "o clique no 3D troca o ponto 5")
    cam = aba.avaliar("cenaApi.estado().cena.camera") or {}
    ok(abs((cam.get("fov") or 0) - FOV) < 2 and (cam.get("erro_px") or 99) < 3,
       f"com 5 pontos refeitos o encaixe continua: lente {cam.get('fov', 0):.1f}°, erro {cam.get('erro_px')} px")

    # as camadas (26/10: "interagir com as camadas… colocar e tirar a lona"): desligar Pilares esconde as peças, fica gravado
    # e volta assim depois de recarregar; sem cobertura retrátil, a seção dela não aparece
    ok(aba.avaliar("document.getElementById('cobertura').hidden") is True, "obra sem cobertura retrátil: sem os botões Aberta/Retraída")
    ok(aba.avaliar("!!document.querySelector('#camadas input[data-chave=\"camada:Pilares\"]')"), "a lista de camadas tem Pilares")
    aba.avaliar("document.querySelector('#camadas input[data-chave=\"camada:Pilares\"]').click(); 1")
    ok(esperar(aba, "visor.visivelCamada[visor.cabecalho.camadas.findIndex(c => c.nome === 'Pilares')] === false", 5),
       "desmarcar Pilares esconde os pilares da cena")
    ok(esperar(aba, "(cenaApi.estado().cena.desligadas || []).includes('camada:Pilares')", 5)
       and esperar(aba, "false", 1.2) is False, "e fica gravado na cena")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, "!!window.cenaPronta && !document.querySelector('#camadas input[data-chave=\"camada:Pilares\"]').checked "
                     "&& visor.visivelCamada[visor.cabecalho.camadas.findIndex(c => c.nome === 'Pilares')] === false", 60),
       "recarregada, a cena volta com os pilares desligados")
    aba.avaliar("document.querySelector('#camadas input[data-chave=\"camada:Pilares\"]').click(); 1")
    esperar(aba, "!(cenaApi.estado().cena.desligadas || []).includes('camada:Pilares')", 5)
    aba.drenar(1.0)

    # 4. a imagem pronta na pasta cenas/ da obra
    aba.avaliar("document.getElementById('salvar-imagem').click(); 1")
    ok(esperar(aba, "!!window.ultimaImagemCena", 30), "Salvar imagem responde")
    arq = os.path.join(DADOS, "obra", "cenas", "Cena - foto-teste.png")
    ok(os.path.isfile(arq) and Image.open(arq).size == (W, H), f"a imagem na pasta cenas/ da obra, no tamanho da foto ({os.path.isfile(arq) and Image.open(arq).size})")

    # apagar a cena (26/10: "não consigo apagar uma cena"): sai da lista; a imagem salva na pasta cenas fica
    aba.avaliar("window.confirm = () => true; document.getElementById('apagar').click(); 1")
    ok(esperar(aba, "!cenaApi.estado().cena && document.getElementById('corpo').hidden", 10), "Apagar a cena: a cena sai da tela")
    ok(not os.path.exists(os.path.join(DADOS, "obra", "cenas", "dados", "foto-teste")) and os.path.isfile(arq),
       "e da pasta dela (a imagem salva continua na pasta cenas)")

    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
