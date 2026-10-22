# -*- coding: utf-8 -*-
"""O vidro transparente no modo ver (e no 3D do celular, o mesmo visor3d.js) como no editor (opacidade 0,35). SESI Chapecó,
22/10: as fachadas de vidro do arquitetônico escondiam os brises metálicos — o visor desenhava tudo opaco.

Um brise vermelho atrás de um pano de vidro, visto de frente:
  1. o vermelho do brise aparece através do vidro (o pixel do vidro sobre o brise é bem mais vermelho que o do vidro
     sobre o fundo), com a opacidade gravada no material do projeto ("Vidro": opacidade 0,35);
  2. o mesmo no projeto sem a opacidade gravada (o pacote de antes de 22/10): o material "Vidro" pelo nome;
  3. o brise sozinho (sem vidro) continua opaco e a escolha da peça pelo clique acha o vidro na frente;
  4. desligar a camada do vidro mostra o brise puro; ligar volta o vidro.
Porta livre, nunca a 8765/8766."""
import base64, io, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _caixa_solido
from PIL import Image

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ver3d_vidro_")


def _peca(id_, x, y, z, a, b, c, material, camada):
    e = _caixa_solido(id_, x, y, z, a=a, b=b, c=c, camada=camada)
    e["material"] = material
    return e


# o pano de vidro na frente (y 0–20) e o brise atrás dele (y 600–900), no meio do pano; um apoio de aço fora do vidro
ents = [_peca("vid0", 0, 0, 0, 4000, 20, 3000, "Vidro", "ARQ — Esquadrias"),
        _peca("bri0", 1400, 600, 1000, 1200, 300, 1000, "Aço", "Fachadas — Brises"),
        _peca("apo0", 4600, 600, 0, 400, 300, 400, "Aço", "Fachadas — Brises")]
camadas = {n: {"nome": n, "cor": "#888888", "visivel": True} for n in ("ARQ — Esquadrias", "Fachadas — Brises")}
mat_com = {"Aço": {"nome": "Aço", "cor": "#d02020"}, "Vidro": {"nome": "Vidro", "cor": "#9fc6e8", "opacidade": 0.35}}
mat_sem = {"Aço": {"nome": "Aço", "cor": "#d02020"}, "Vidro": {"nome": "Vidro", "cor": "#9fc6e8"}}
for nome, mats in (("com", mat_com), ("sem", mat_sem)):
    os.makedirs(os.path.join(DADOS, nome))
    json.dump({"nome": nome, "tipo": "ifc", "alterado": "2026-10-22T01:00:00"}, open(os.path.join(DADOS, nome, "projeto.json"), "w", encoding="utf-8"))
    json.dump({"nome": nome, "unidade": "mm", "entidades": ents, "camadas": camadas, "materiais": mats},
              open(os.path.join(DADOS, nome, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
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


# o ponto do projeto (mm) na tela, em px CSS
NA_TELA = ("(() => { const o = visor.cabecalho.origem, v = visor.camera.position.clone().set(%s - o[0], %s - o[1], %s - o[2]);"
           " v.project(visor.camera); const r = visor.tela.getBoundingClientRect();"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; })()")


def pixel(aba, img, p):
    x, y = aba.avaliar(NA_TELA % tuple(p))
    return img.getpixel((int(round(x)), int(round(y))))[:3]


def foto(aba):
    aba.drenar(1.0)
    dados = aba.cmd("Page.captureScreenshot", format="png")["data"]
    return Image.open(io.BytesIO(base64.b64decode(dados))).convert("RGB")


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ver3d_vidro_")
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
    PRONTO = "!!(window.ver3dPronto && window.visor && visor.fichas)"
    BRISE, VIDRO_SO, APOIO = (2000, 0, 1500), (500, 0, 2700), (4800, 600, 200)   # o vidro sobre o brise, sobre o fundo; o apoio

    for nome, rotulo in (("com", "opacidade no material"), ("sem", "pacote antigo, pelo nome")):
        aba.navegar(base + f"/visor3d/ver3d.html?projeto={nome}", limite=60)
        ok(esperar(aba, PRONTO, 90), f"[{rotulo}] o modo ver abriu ({aba.avaliar('window.visor && visor.nPecas')} peças)")
        aba.avaliar("visor.enquadrar('frente'); 1")
        img = foto(aba)
        sobre, so, apoio = pixel(aba, img, BRISE), pixel(aba, img, VIDRO_SO), pixel(aba, img, APOIO)
        verm = lambda c: c[0] - (c[1] + c[2]) / 2
        ok(verm(sobre) > verm(so) + 40,
           f"[{rotulo}] o brise vermelho aparece através do vidro (vidro sobre o brise {sobre}, vidro sobre o fundo {so})")
        ok(verm(apoio) > 60, f"[{rotulo}] o aço fora do vidro continua opaco e vermelho ({apoio})")
        if nome == "com":
            img.save(os.path.join(os.path.dirname(__file__), "ver3d_vidro.png"))
            # a escolha pelo clique: o vidro na frente é a peça escolhida (o visor escolhe pela placa, e o vidro está lá)
            x, y = aba.avaliar(NA_TELA % BRISE)
            esc = aba.avaliar(f"(() => {{ const r = visor.tela.getBoundingClientRect(); return visor.escolher({x} - r.left, {y} - r.top); }})()")
            ok(esc is not None and esc >= 0 and aba.avaliar(f"visor.fichas[{esc}].id") == "vid0",
               f"o clique no vidro escolhe o vidro ({esc})")
            # desligar a camada do vidro: o brise puro; ligar: o vidro volta
            ID = "visor.cabecalho.camadas.findIndex(c => c.nome === 'ARQ — Esquadrias')"
            aba.avaliar(f"(() => {{ visor.visivelCamada[{ID}] = false; visor._repintar(); return 1; }})()")
            puro = pixel(aba, foto(aba), BRISE)
            aba.avaliar(f"(() => {{ visor.visivelCamada[{ID}] = true; visor._repintar(); return 1; }})()")
            devolta = pixel(aba, foto(aba), BRISE)
            ok(verm(puro) > verm(sobre) + 20, f"sem o vidro, o brise puro é mais vermelho ({puro} > {sobre})")
            ok(max(abs(a - b) for a, b in zip(devolta, sobre)) < 12, f"ligado de novo, o vidro volta ({devolta} ≈ {sobre})")

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
