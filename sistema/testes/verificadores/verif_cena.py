# -*- coding: utf-8 -*-
"""A cena (26/10, o usuário: "criar cena… para poder encaixar certinho o 3D na imagem"): a estrutura numa foto do local.

A "foto" é feita aqui por uma câmera conhecida (de pé, a 1,6 m do chão, lente de 70°), com 6 pontos do chão marcados —
como os cantos e o meio das linhas de uma quadra (o caso da Kaefer: os pontos de referência no chão, a estrutura ainda
não existe na foto). Pela tela, com cliques de verdade:
  1. a foto entra como cena nova (a rota do terreno) e a página abre nela;
  2. para cada ponto: "+ Ponto", o clique na foto, a vista vai para o 3D, o clique no mesmo ponto do chão;
  3. no 4º ponto o encaixe sai sozinho; com os 6, a lente volta 70° (±2°) e o erro fica abaixo de 3 px;
  4. Salvar imagem: a foto com o 3D em <projeto>/documentos/, no tamanho da foto;
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

    # 4. a imagem pronta em documentos/
    aba.avaliar("document.getElementById('salvar-imagem').click(); 1")
    ok(esperar(aba, "!!window.ultimaImagemCena", 30), "Salvar imagem responde")
    arq = os.path.join(DADOS, "obra", "documentos", "Cena - foto-teste.png")
    ok(os.path.isfile(arq) and Image.open(arq).size == (W, H), f"a imagem em documentos/, no tamanho da foto ({os.path.isfile(arq) and Image.open(arq).size})")

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
