# -*- coding: utf-8 -*-
"""O chão em mais de um nível no modo ver (03/11, o usuário pelo SESI Chapecó: "uma limitação legal da nossa representação
do terreno, quando temos níveis diferentes"; caso (b) aprovado — Projeto/ESTUDOS/Terreno-niveis): web/visor3d/terreno.js +
chao.js. A situação do SESI em miniatura — um prédio de 20 × 10 m (eixos 1–3 × A–B), a frente sul no térreo (−0,50), o
pátio norte do subsolo (−4,00), a rua norte acima (−1,50) e um muro (−4,00 → −0,50 em 1,5 m) — e a obra plana (sem pontos:
o plano de sempre). Confere: a imagem passa pelos pontos, encosta na face norte na cota do pátio, o muro sai em cor neutra,
o "+ Ponto de nível" marca com um clique de verdade no chão e a cota digitada grava no projeto, o ✕ e o "Tirar todos"
voltam ao plano, e tudo continua depois do F5. Fonte de imagem de teste (sem internet). Porta livre, nunca a 8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_niveis_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)


def caixa(i, nome, x0, y0, z0, x1, y1, z1, camada="Concreto"):
    v = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    return {"id": i, "tipo": "solido", "nome": nome, "camada": camada, "material": "Concreto", "vertices": v,
            "faces": [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]}


MODELO = {"nome": "níveis", "unidade": "mm", "materiais": {"Concreto": {"nome": "Concreto", "cor": "#b8b2a6"}},
          "camadas": {"Concreto": {"nome": "Concreto", "cor": "#b8b2a6", "visivel": True}},
          "entidades": [caixa("sub", "laje do subsolo", 0, 0, -4200, 20000, 10000, -4000),
                        caixa("ter", "laje do térreo", 0, 0, -200, 20000, 10000, 0),
                        caixa("cob", "laje de cima", 0, 0, 3800, 20000, 10000, 4000)]
                       + [caixa("p%d" % k, "pilar", x - 150, y - 150, -4000, x + 150, y + 150, 3800)
                          for k, (x, y) in enumerate((x, y) for x in (0, 10000, 20000) for y in (0, 10000))]}
json.dump(MODELO, open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
json.dump({"nome": "Obra em níveis", "tipo": "ifc", "alterado": "2026-11-03T09:00:00",
           "eixos": {"eixo_g": [1.0, 0.0], "numeros": [{"nome": "1", "pos": 0}, {"nome": "2", "pos": 10000}, {"nome": "3", "pos": 20000}],
                     "letras": [{"nome": "A", "pos": 0}, {"nome": "B", "pos": 10000}], "origem": "usuario"}},
          open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
# os pontos da implantação, como o script da obra (ou o painel) os grava
NIVEIS = [{"x": 0, "y": -6000, "z": -500}, {"x": 10000, "y": -6000, "z": -500}, {"x": 20000, "y": -6000, "z": -500},
          {"x": 3000, "y": 13000, "z": -4000}, {"x": 10000, "y": 13000, "z": -4000}, {"x": 17000, "y": 13000, "z": -4000},
          {"x": 3000, "y": 21000, "z": -1500}, {"x": 17000, "y": 21000, "z": -1500},
          {"x": 26000, "y": 13000, "z": -4000}, {"x": 26000, "y": 14500, "z": -500}]
amb = dict(os.environ, METALICA_TERRENO="1", METALICA_TERRENO_FALSO="1")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
API = base + "/api/projetos/obra/terreno"
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
        aba.drenar(0.25)
    return False


def post(url, corpo):
    import urllib.request
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return json.loads(r.read().decode())


# a cota da imagem (mm do projeto) num ponto da obra: o vértice da malha mais perto, na posição do mundo dele
COTA_DA_MALHA = """((X, Y) => { const tr = window.terreno, m = tr.malha, pos = m.geometry.attributes.position;
  const c = Math.cos(m.rotation.z), s = Math.sin(m.rotation.z); let melhor = null, d0 = Infinity;
  for (let v = 0; v < pos.count; v++) {
    const u = pos.getX(v) * m.scale.x, w = pos.getY(v) * m.scale.y;
    const x = m.position.x + c * u - s * w, y = m.position.y + s * u + c * w, d = Math.hypot(x - X, y - Y);
    if (d < d0) { d0 = d; melhor = { z: m.position.z + pos.getZ(v), d, parede: m.geometry.attributes.parede ? m.geometry.attributes.parede.getX(v) : 0 }; }
  }
  return melhor; })"""

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_niveis_")
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

    # a obra no lugar, a imagem baixada (a fonte de teste), a altura no 0,00 — e ainda sem pontos: a obra plana
    T0 = {"lat": -27.09, "lon": -52.63, "ponto": [10000, 5000], "norte": -53.1, "fonte": "teste", "cota": 0}
    post(API, T0)
    post(API + "/baixar-imagem", {"caixa": [0, 0, 20000, 10000]})
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha)", 90), "o modo ver abre com a imagem do terreno")
    plano = aba.avaliar("""(() => { const m = window.terreno.malha, g = m.geometry, p = g.attributes.position;
      let z = 0; for (let v = 0; v < p.count; v++) z = Math.max(z, Math.abs(p.getZ(v)));
      return { seg: g.parameters.widthSegments, n: p.count, z, zm: m.position.z, cota: window.terreno.cotaEm(5000, 20000) }; })()""")
    ok(plano["seg"] == 1 and plano["n"] == 4 and plano["z"] == 0 and plano["zm"] == -3,
       f"obra plana (sem pontos): o plano de sempre, 4 vértices na cota −3 mm ({plano})")
    ok(plano["cota"] == -3, "obra plana: a cota do chão é a do plano em qualquer lugar")

    # os pontos de nível gravados (como o script da obra faz) → F5
    post(API, dict(T0, niveis=NIVEIS))
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha && window.terreno._sup)", 90), "com os pontos: o chão em níveis")
    ok(esperar(aba, "window.terreno._referenciaUsada === window.visor._dadosReferencia && !!window.visor._dadosReferencia", 20),
       "a face do prédio pelos eixos (a referência chegou e o chão foi refeito)")
    aba.drenar(0.5)
    seg = aba.avaliar("window.terreno.malha.geometry.parameters.widthSegments")
    ok(seg and seg >= 64, f"a imagem vira uma malha subdividida ({seg} × {seg})")
    for nome, (x, y, z) in {"frente sul (−0,50)": (10000, -6000, -503), "pátio norte (−4,00)": (10000, 13000, -4003),
                            "rua norte (−1,50)": (10000, 21000, -1503), "face norte, por fora (o pátio)": (10000, 11500, -4003),
                            }.items():
        r = aba.avaliar(COTA_DA_MALHA + f"({x}, {y})")
        ok(r and abs(r["z"] - z) < 150 and r["d"] < 1500, f"{nome}: a imagem em {r and round(r['z'])} mm (esperado {z})")
    longe = aba.avaliar("[window.terreno.cotaEm(10000, -2000000), window.terreno.cotaEm(10000, -100000)]")
    ok(abs(longe[0] + 3) < 1 and -503 < longe[1] < -3,
       f"longe da obra, o plano de antes (−3 mm no anel; {round(longe[1])} mm a 100 m: volta aos poucos)")
    r = aba.avaliar(COTA_DA_MALHA + "(26000, 13750)")
    ok(r and r["parede"] > 0.5, f"o muro (−4,00 → −0,50 em 1,5 m) sai como parede, cor neutra ({r and round(r['parede'], 2)})")
    r = aba.avaliar(COTA_DA_MALHA + "(10000, -4000)")
    ok(r and r["parede"] == 0, "o chão plano da frente não é parede")
    err = [c for c in aba.console if (c[0] in ("excecao", "error") or "Shader" in c[1]) and "favicon" not in c[1]]
    ok(not err, f"sem erro no console (o sombreador da parede compila) {err[:3]}")
    aba.avaliar("""(() => { const v = window.visor, o = v.cabecalho.origem || [0, 0, 0];
      v.camera.position.set(34000 - o[0], 36000 - o[1], 9000 - o[2]); v.controles.target.set(10000 - o[0], 8000 - o[1], -2500 - o[2]);
      v.controles.update(); v.pedirQuadro(); return 1; })()""")
    foto(aba, "ver3d_terreno_niveis_1.png")

    # o painel: a lista dos pontos e os pinos no 3D só com o painel aberto
    ok(not aba.avaliar("!!(window.terreno.pinos && window.terreno.pinos.visible)"), "os pinos dos pontos escondidos com o painel fechado")
    aba.avaliar("document.getElementById('btn-terreno').click()")
    ok(esperar(aba, "document.querySelectorAll('.terreno-nivel').length === %d" % len(NIVEIS), 5),
       f"o painel Terreno lista os {len(NIVEIS)} pontos de nível")
    aba.avaliar("document.getElementById('terreno-niveis-ver').click()")
    ok(esperar(aba, "window.terreno.pinos && window.terreno.pinos.visible", 5), "Mostrar os pontos: os pinos aparecem no 3D")

    # + Ponto de nível: um clique de verdade no chão (na vista de cima, no pátio norte)
    aba.avaliar("""(() => { const v = window.visor, o = v.cabecalho.origem || [0, 0, 0];
      v.camera.position.set(6500 - o[0], 13000 - o[1] - 1, 60000 - o[2]); v.controles.target.set(6500 - o[0], 13000 - o[1], -4000 - o[2]);
      v.controles.update(); v.pedirQuadro(); return 1; })()""")
    aba.drenar(0.6)
    aba.avaliar("document.getElementById('terreno-nivel-marcar').click()")
    ok(esperar(aba, "window.terreno.marcandoNivel && document.getElementById('palco').classList.contains('marcando-nivel')", 5),
       "+ Ponto de nível: marcando (cursor em cruz)")
    tela = aba.avaliar("(() => { const r = window.visor.renderer.domElement.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    cx, cy = tela
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy, button="none")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", buttons=1, clickCount=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", buttons=0, clickCount=1)
    ok(esperar(aba, "window.terreno.t.niveis.length === %d" % (len(NIVEIS) + 1), 5), "o clique no chão põe um ponto")
    novo = aba.avaliar("window.terreno.t.niveis[window.terreno.t.niveis.length - 1]")
    ok(novo and abs(novo["x"] - 6500) < 800 and abs(novo["y"] - 13000) < 800 and abs(novo["z"] + 4000) < 150,
       f"o ponto cai onde se clicou, com a cota que o chão tem ali ({novo})")
    ok(esperar(aba, "document.activeElement && document.activeElement.dataset.cota === '%d'" % len(NIVEIS), 5),
       "a cota do ponto novo fica pronta para digitar")
    aba.avaliar("document.execCommand('selectAll'); 1")
    aba.cmd("Input.insertText", text="-3,20")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    ok(esperar(aba, "window.terreno.t.niveis[%d].z === -3200" % len(NIVEIS), 5), "a cota digitada (−3,20) vale para o ponto")
    ok(esperar(aba, "Math.abs(window.terreno.cotaEm(%d, %d) + 3203) < 2" % (novo["x"], novo["y"]), 5), "e a imagem passa a passar por ela")
    aba.drenar(1.2)
    t = _json(API)["terreno"]
    ok(len(t.get("niveis") or []) == len(NIVEIS) + 1 and t["niveis"][-1]["z"] == -3200, "o ponto novo gravado no projeto")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    ok(esperar(aba, "!window.terreno.marcandoNivel", 3), "Esc termina de marcar")

    # o ✕ tira um ponto; "Tirar todos" volta ao plano
    aba.avaliar("document.querySelector('[data-tirar=\"%d\"]').click()" % len(NIVEIS))
    aba.drenar(1.2)
    ok(len(_json(API)["terreno"].get("niveis") or []) == len(NIVEIS), "o ✕ tira o ponto (no projeto também)")
    aba.avaliar("window.confirm = () => true; document.getElementById('terreno-niveis-tirar').click(); 1")
    aba.drenar(1.2)
    ok("niveis" not in _json(API)["terreno"], "Tirar todos os pontos: o projeto fica sem níveis")
    ok(aba.avaliar("window.terreno.malha.geometry.parameters.widthSegments === 1 && !window.terreno._sup"), "e a imagem volta ao plano")
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha)", 90)
       and aba.avaliar("window.terreno.malha.geometry.parameters.widthSegments === 1"), "depois do F5, continua plana")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%s" % ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
