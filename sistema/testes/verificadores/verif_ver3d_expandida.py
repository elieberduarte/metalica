# -*- coding: utf-8 -*-
"""A chapa expandida vazada no modo ver (e no 3D do celular, o mesmo visor3d.js). SESI Chapecó, 30/10 (usuário: "é uma
chapa toda furadinha, e a que foi renderizada no projeto é uma chapa sólida, pode detalhar no modelo a chapa real" —
"tamanho real"): a chapa de 960 dos brises saía cheia e escondia o que está atrás.

Uma chapa expandida 12x25 (azul) na frente de um bloco vermelho e, ao lado, uma chapa comum na frente de outro:
  1. a ficha da expandida leva a malha (vz = LD 25, CD 12, cordão 1,5, pelo "12x25" do nome); a comum não;
  2. vista de frente (o losango com 2–3 pixels), o vermelho aparece através da expandida, esmaecido e por igual — sem
     pixels soltos (30/10, usuário: o furo sim/não de pixel em pixel "ficou parecendo um monte de pixels") — e não através
     da comum;
  3. a meia distância (o losango com ~8 pixels), a malha sem pixels soltos; de perto (dezenas de pixels), o cordão azul e
     o vermelho pelos furos;
  4. o clique num furo da expandida escolhe a chapa (a escolha não tem furo);
  5. o vidro continua translúcido e por trás das vazadas (a faixa do alfa de cada um).
Porta livre, nunca a 8765/8766."""
import base64, io, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _caixa_solido
from PIL import Image

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ver3d_expandida_")


def _bloco(id_, x, y, z, a, b, c, material, camada):
    e = _caixa_solido(id_, x, y, z, a=a, b=b, c=c, camada=camada)
    e["material"] = material
    return e


def _chapa(id_, nome, x0):
    # em pé no plano y = 0..2, de x0 a x0 + 3000 e de z 0 a 3000
    return {"id": id_, "tipo": "chapa", "nome": nome, "camada": "Fachadas — Brises", "material": "Aço galv.",
            "origem": [x0, 0.0, 0.0], "eixo_x": [1.0, 0.0, 0.0], "eixo_y": [0.0, 0.0, 1.0],
            "contorno": [[0, 0], [3000, 0], [3000, 3000], [0, 3000]], "espessura": 2.0, "centrada": False, "furos": [],
            "atributos": {}}


ents = [_chapa("exp0", "Chapa expandida 12x25", 0.0), _chapa("che0", "Chapa #2", 4000.0),
        _bloco("bl0", 500, 600, 500, 2000, 300, 2000, "Aço", "Fachadas — Brises"),
        _bloco("bl1", 4500, 600, 500, 2000, 300, 2000, "Aço", "Fachadas — Brises"),
        _bloco("vid0", 8000, 0, 0, 2000, 20, 3000, "Vidro", "ARQ — Esquadrias"),
        _bloco("bl2", 8500, 600, 500, 1000, 300, 2000, "Aço", "Fachadas — Brises"),
        _bloco("bl3", 11000, 600, 500, 1000, 300, 2000, "Aço", "Fachadas — Brises"),      # o vermelho puro, descoberto
        _bloco("laj0", -20000, 3000, 6000, 50000, 60000, 200, "Concreto", "ARQ — Lajes")]  # a laje vista de baixo, de lado
camadas = {n: {"nome": n, "cor": "#888888", "visivel": True} for n in ("Fachadas — Brises", "ARQ — Esquadrias", "ARQ — Lajes")}
mats = {"Aço": {"nome": "Aço", "cor": "#d02020"}, "Aço galv.": {"nome": "Aço galv.", "cor": "#2050f0"},
        "Vidro": {"nome": "Vidro", "cor": "#9fc6e8", "opacidade": 0.35}, "Concreto": {"nome": "Concreto", "cor": "#9a9a9a"}}
os.makedirs(os.path.join(DADOS, "exp"))
json.dump({"nome": "exp", "tipo": "ifc", "alterado": "2026-10-30T01:00:00"}, open(os.path.join(DADOS, "exp", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "exp", "unidade": "mm", "entidades": ents, "camadas": camadas, "materiais": mats},
          open(os.path.join(DADOS, "exp", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
# o recorte do SESI (gravado 30/10): as lajes, pilares e vigas do arquitetônico atrás da fachada A — de baixo, quase de
# lado, saíam salpicadas de claro e escuro pelos brises vazados
ARQ_REC = os.path.join(BASE, "..", "Projeto", "bateria", "entradas", "sesi-modo-ver", "arq-fachada-a.json")   # fora do git
if os.path.exists(ARQ_REC):
    REC = json.load(open(ARQ_REC, encoding="utf-8"))
    os.makedirs(os.path.join(DADOS, "sesi"))
    json.dump({"nome": "sesi", "tipo": "ifc", "alterado": "2026-10-30T01:00:00"}, open(os.path.join(DADOS, "sesi", "projeto.json"), "w", encoding="utf-8"))
    json.dump({"nome": "sesi", "unidade": "mm", "entidades": REC["entidades"], "camadas": REC["camadas"], "materiais": REC["materiais"]},
              open(os.path.join(DADOS, "sesi", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
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
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


NA_TELA = ("(() => { const o = visor.cabecalho.origem, v = visor.camera.position.clone().set(%s - o[0], %s - o[1], %s - o[2]);"
           " v.project(visor.camera); const r = visor.tela.getBoundingClientRect();"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; })()")


def foto(aba):
    aba.drenar(1.0)
    dados = aba.cmd("Page.captureScreenshot", format="png")["data"]
    return Image.open(io.BytesIO(base64.b64decode(dados))).convert("RGB")


verm = lambda c: c[0] - (c[1] + c[2]) / 2 > 60
azul = lambda c: c[2] - c[0] > 60


def fracoes(aba, img, a, b, n=25):
    """(fração vermelha, fração azul) numa grade de n × n pixels entre os pontos a e b do projeto (na tela)."""
    xa, ya = aba.avaliar(NA_TELA % tuple(a))
    xb, yb = aba.avaliar(NA_TELA % tuple(b))
    px = [img.getpixel((int(xa + (xb - xa) * i / (n - 1)), int(ya + (yb - ya) * j / (n - 1))))[:3]
          for i in range(n) for j in range(n)]
    return sum(map(verm, px)) / len(px), sum(map(azul, px)) / len(px)


def regiao(aba, img, a, b):
    """os pixels (r, g, b) do retângulo entre os pontos a e b do projeto, na tela"""
    xa, ya = aba.avaliar(NA_TELA % tuple(a))
    xb, yb = aba.avaliar(NA_TELA % tuple(b))
    x0, x1, y0, y1 = int(min(xa, xb)), int(max(xa, xb)), int(min(ya, yb)), int(max(ya, yb))
    return [[img.getpixel((x, y))[:3] for x in range(x0, x1)] for y in range(y0, y1)]


def soltos(px, limiar=60):
    """a fração de pixels que destoam dos 4 vizinhos (> limiar no vermelho, para o mesmo lado): o pontilhado"""
    n = s = 0
    for y in range(1, len(px) - 1):
        for x in range(1, len(px[0]) - 1):
            r = px[y][x][0]
            d = [r - px[y + dy][x + dx][0] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            n += 1
            s += all(v > limiar for v in d) or all(v < -limiar for v in d)
    return s / max(n, 1)


def aspereza(img, y0, y1, limiar=25):
    """a fração de pares de pixels vizinhos (lado a lado) que diferem mais que o limiar no vermelho: numa superfície lisa,
    só as bordas das peças (poucos %); salpicada de claro e escuro, dezenas de %"""
    n = s = 0
    for y in range(y0, y1):
        for x in range(0, img.width - 1):
            n += 1
            s += abs(img.getpixel((x, y))[0] - img.getpixel((x + 1, y))[0]) > limiar
    return s / max(n, 1)


def media(px):
    v = [c for linha in px for c in linha]
    return tuple(sum(c[i] for c in v) / len(v) for i in range(3))


def camera(aba, x, y, z, dist):
    aba.avaliar("(() => { const o = visor.cabecalho.origem; visor.controles.target.set(%s - o[0], %s - o[1], %s - o[2]);"
                " visor.camera.position.set(%s - o[0], %s - o[1], %s - o[2]); visor.controles.update(); visor.pedirQuadro();"
                " return 1; })()" % (x, y, z, x, y - dist, z))


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ver3d_exp_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1200, height=800, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/visor3d/ver3d.html?projeto=exp", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.visor && visor.fichas)", 90), "o modo ver abriu")

    # 1. a ficha
    vz = aba.avaliar("JSON.stringify(visor.fichas.map(f => [f.id, f.vz || null]))")
    vz = dict(json.loads(vz))
    ok(vz.get("exp0") == [25, 12, 1.5], f"a ficha da expandida leva a malha 25 × 12 × 1,5 pelo nome: {vz.get('exp0')}")
    ok(vz.get("che0") is None, f"a chapa comum não: {vz.get('che0')}")

    # 2. de frente, o modelo inteiro
    aba.avaliar("visor.enquadrar('frente'); 1")
    img = foto(aba)
    img.save(os.path.join(os.path.dirname(__file__), "ver3d_expandida.png"))
    vermelho = lambda c: c[0] - (c[1] + c[2]) / 2
    pe = regiao(aba, img, (800, 0, 2200), (2200, 0, 800))
    me, mc, mp = media(pe), media(regiao(aba, img, (4800, 0, 2200), (6200, 0, 800))), media(regiao(aba, img, (11200, 600, 2200), (11800, 600, 800)))
    ok(vermelho(me) > vermelho(mc) + 40 and vermelho(me) < vermelho(mp) - 15,
       f"de frente, o bloco vermelho aparece pela expandida, esmaecido (expandida {tuple(map(round, me))}, comum {tuple(map(round, mc))}, puro {tuple(map(round, mp))})")
    ok(vermelho(mc) < 0, f"e não pela chapa comum ({tuple(map(round, mc))})")
    sf = soltos(pe)
    ok(sf < 0.01, f"de frente, a expandida por igual, sem pixels soltos ({sf:.1%})")
    px = lambda p: img.getpixel(tuple(int(t) for t in aba.avaliar(NA_TELA % p)))[:3]
    sobre, so = px((9000, 0, 1500)), px((8200, 0, 2800))      # o vidro sobre o bloco e sobre o fundo
    vermelho = lambda c: c[0] - (c[1] + c[2]) / 2
    ok(vermelho(sobre) > vermelho(so) + 20 and not verm(sobre),
       f"o vidro continua translúcido: o vermelho por trás dele, esmaecido ({sobre} × {so} sobre o fundo)")

    # 3. a meia distância (2,5 m: o losango com ~8 pixels) e de perto (400 mm: dezenas de pixels)
    camera(aba, 1500, 0, 1500, 2500)
    img = foto(aba)
    img.save(os.path.join(os.path.dirname(__file__), "ver3d_expandida_meio.png"))
    sm = soltos(regiao(aba, img, (1000, 0, 2000), (2000, 0, 1000)))
    ok(sm < 0.01, f"a meia distância, a malha sem pixels soltos ({sm:.1%})")
    # de lado (rasante, de baixo, como olhando o brise de dentro do prédio): a tela por igual, sem chuvisco
    aba.avaliar("(() => { const o = visor.cabecalho.origem; visor.controles.target.set(1500 - o[0], 0 - o[1], 2500 - o[2]);"
                " visor.camera.position.set(1500 - o[0], -350 - o[1], -1500 - o[2]); visor.controles.update(); visor.pedirQuadro(); return 1; })()")
    img = foto(aba)
    img.save(os.path.join(os.path.dirname(__file__), "ver3d_expandida_lado.png"))
    r = aba.avaliar("(() => { const r = visor.tela.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
    cx, cy = int(r[0] + r[2] / 2), int(r[1] + r[3] / 2)
    pl = [[img.getpixel((x, y))[:3] for x in range(cx - 150, cx + 150)] for y in range(cy - 120, cy + 120)]
    sl = soltos(pl)
    ok(sl < 0.01, f"de lado (rasante), a expandida sem chuvisco ({sl:.1%})")
    # 4. a laje vista de baixo quase de lado (o que se vê pelos brises vazados de dentro do prédio): lisa — a face virada
    #    para o olho era decidida pelo eixo da câmera e virava de pixel em pixel, claro e escuro (30/10, SESI)
    aba.avaliar("(() => { const o = visor.cabecalho.origem; visor.controles.target.set(5000 - o[0], 40000 - o[1], 5600 - o[2]);"
                " visor.camera.position.set(5000 - o[0], 4000 - o[1], 5600 - o[2]); visor.controles.update(); visor.pedirQuadro(); return 1; })()")
    img = foto(aba)
    img.save(os.path.join(os.path.dirname(__file__), "ver3d_laje_de_lado.png"))
    pj = [[img.getpixel((x, y))[:3] for x in range(cx - 300, cx + 300)] for y in range(cy - 330, cy - 40)]
    sj = soltos(pj, limiar=25)
    ok(sj < 0.01, f"a laje vista de baixo, quase de lado, lisa ({sj:.1%} de pixels soltos)")
    camera(aba, 1500, 0, 1500, 400)
    img = foto(aba)
    img.save(os.path.join(os.path.dirname(__file__), "ver3d_expandida_perto.png"))
    ve, ae = fracoes(aba, img, (1440, 0, 1540), (1560, 0, 1460))
    ok(0.45 <= ve <= 0.92 and ae >= 0.05, f"de perto, o cordão azul e o vermelho pelos furos ({ve:.0%} vermelho, {ae:.0%} azul)")

    # 4. o clique num furo escolhe a chapa: o ponto vermelho mais perto do meio
    r = aba.avaliar("(() => { const r = visor.tela.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
    alvo = None
    for d in range(0, 60):
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            x, y = int(r[0] + r[2] / 2 + dx), int(r[1] + r[3] / 2 + dy)
            if verm(img.getpixel((x, y))[:3]):
                alvo = (x, y); break
        if alvo: break
    esc = aba.avaliar(f"(() => {{ const r = visor.tela.getBoundingClientRect(); return visor.escolher({alvo[0]} - r.left, {alvo[1]} - r.top); }})()") if alvo else None
    ok(alvo is not None and esc is not None and esc >= 0 and aba.avaliar(f"visor.fichas[{esc}].id") == "exp0",
       f"o clique num furo escolhe a chapa expandida ({alvo}, {esc})")

    # 5. o recorte do SESI: a laje do 3º Pav. vista de baixo pela fachada A (a vista do usuário, 30/10), lisa
    if not os.path.exists(ARQ_REC):
        print("  ---   o recorte do SESI (Projeto/bateria/entradas/sesi-modo-ver) não está nesta máquina: item pulado")
    else:
        aba.navegar(base + "/visor3d/ver3d.html?projeto=sesi", limite=60)
        ok(esperar(aba, "!!(window.ver3dPronto && window.visor && visor.fichas)", 90), "o recorte do SESI abriu")
        aba.avaliar("(() => { visor.enquadrar('frente'); const o = visor.cabecalho.origem; visor.controles.target.set(20000 - o[0], -1400 - o[1], 9000 - o[2]);"
                    " visor.camera.position.set(20000 - o[0], -9000 - o[1], 9000 - o[2]); visor.controles.update(); visor.pedirQuadro(); return 1; })()")
        img = foto(aba)
        img.save(os.path.join(os.path.dirname(__file__), "ver3d_sesi_lajes.png"))
        asp = aspereza(img, 100, img.height - 30)
        ok(asp < 0.03, f"SESI: as lajes e vigas vistas de baixo pela fachada A, lisas ({asp:.1%} de vizinhos destoando)")

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
