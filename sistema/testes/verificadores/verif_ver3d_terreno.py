# -*- coding: utf-8 -*-
"""A obra no terreno do cliente no modo ver (web/visor3d/terreno.js + saida/local_obra.py, 20/10): o botão Terreno, a
coordenada colada do Google Maps, a imagem no chão com o meio na obra, o Ajustar (arrastar a imagem por baixo da obra,
sem girar a câmera) e o giro do norte, gravados no projeto e de volta depois do F5. Fonte de imagem de teste (sem
internet: METALICA_TERRENO_FALSO=1). Porta livre, nunca a 8765/8766."""
import base64, json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_terreno_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)
json.dump({"nome": "Obra no terreno", "tipo": "ifc", "alterado": "2026-10-20T09:00:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
# com um subsolo (o Mercado Conceito, 20/10: a imagem no fundo do subsolo deixava a fundação "voando"): uma laje a −3,50 m
MODELO = _modelo()
MODELO["entidades"].append({"id": "sub", "tipo": "solido", "nome": "laje do subsolo", "camada": "Subsolo", "material": "Concreto",
    "vertices": [[0, 0, -3500], [6000, 0, -3500], [6000, 4000, -3500], [0, 4000, -3500],
                 [0, 0, -3300], [6000, 0, -3300], [6000, 4000, -3300], [0, 4000, -3300]],
    "faces": [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]})
json.dump(MODELO, open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
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


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_terreno_")
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

    ok(_json(API)["terreno"] is None, "projeto novo: sem local")
    # a fonte de teste (sem internet) gravada antes, noutro lugar: a busca troca o lugar e mantém a fonte
    post(API, {"lat": -23.5, "lon": -46.6, "ponto": [0, 0], "norte": 0, "fonte": "teste"})

    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.estado)", 90), "o modo ver abre com o terreno carregado")
    ok(esperar(aba, "!document.getElementById('btn-terreno').hidden", 10), "o botão Terreno aparece (dev)")
    aba.avaliar("document.getElementById('btn-terreno').click()")
    ok(esperar(aba, "!!document.getElementById('terreno-q')", 5), "o painel Terreno abre com a busca")
    # a coordenada como o botão direito do Google Maps copia
    aba.avaliar("""(() => { document.getElementById('terreno-q').value = '-24.956206, -53.4556926';
      document.getElementById('terreno-busca').requestSubmit(); return 1; })()""")
    ok(esperar(aba, "document.querySelectorAll('#terreno-resultados [data-i]').length === 1", 15), "a coordenada colada vira um resultado")
    aba.avaliar("document.querySelector('#terreno-resultados [data-i]').click()")
    ok(esperar(aba, "!!window.terreno.malha && window.terreno.imagem && window.terreno.t.lat < -24.9", 60),
       "escolher o resultado baixa a imagem e a põe no chão")
    t = _json(API)
    ok(abs(t["terreno"]["lat"] + 24.956206) < 1e-6 and t["terreno"]["fonte"] == "teste", "a amarração gravada no projeto (com a fonte)")
    ok(os.path.isfile(os.path.join(proj, "terreno", "imagem.jpg")), "a imagem guardada na pasta do projeto")
    # o meio da imagem é o meio da obra (a amarração de saída), na escala da imagem
    m = aba.avaliar("""(() => { const v = window.visor, tr = window.terreno, o = v.cabecalho.origem, c = v._caixaModelo.getCenter(new v.camera.position.constructor());
      return { dx: tr.malha.position.x - (c.x + o[0]), dy: tr.malha.position.y - (c.y + o[1]), lado: tr.malha.scale.x,
               ladoM: tr.imagem.lado_m, giro: tr.malha.rotation.z, zMalha: tr.malha.position.z, zMin: v._caixaModelo.min.z + o[2],
               fonte: (document.getElementById('terreno-fonte') || {}).textContent }; })()""")
    ok(math.hypot(m["dx"], m["dy"]) < 600, f"o meio da imagem no meio da obra ({m['dx']:.0f}, {m['dy']:.0f} mm)")
    ok(abs(m["lado"] / 1000 - m["ladoM"]) / m["ladoM"] < 0.02, f"a imagem na escala ({m['lado'] / 1000:.1f} m × {m['ladoM']} m)")
    ok(abs(m["zMalha"] - m["zMin"]) < 20 and m["zMin"] < -3400, f"no automático, a imagem no pé da obra (o fundo do subsolo, {m['zMalha']:.0f} mm)")
    ok(m["fonte"] == "Imagem de teste", f"a fonte da imagem no canto ({m['fonte']!r})")
    ok(aba.avaliar("document.getElementById('btn-terreno').classList.contains('ligado')"), "o botão Terreno fica aceso")
    foto(aba, "ver3d_terreno_1.png")

    # o Ajustar: arrastar a imagem por baixo da obra, de cima; a câmera não gira nem anda
    aba.avaliar("document.querySelector('[data-vista=topo]').click()")
    aba.drenar(0.6)
    aba.avaliar("document.getElementById('terreno-ajustar').click()")
    ok(esperar(aba, "window.terreno.ajustando && document.getElementById('palco').classList.contains('ajustando-terreno')", 5), "Ajustar ligado")
    antes = aba.avaliar("""(() => { const tr = window.terreno, c = window.visor.camera.position;
      return { x: tr.malha.position.x, y: tr.malha.position.y, lat: tr.t.lat, lon: tr.t.lon, cam: [c.x, c.y, c.z] }; })()""")
    x0, y0 = 700, 430
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1)
    for i in range(1, 11):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + 12 * i, y=y0, button="left", buttons=1)
        aba.drenar(0.03)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x0 + 120, y=y0, button="left", buttons=0, clickCount=1)
    aba.drenar(0.3)
    depois = aba.avaliar("""(() => { const tr = window.terreno, c = window.visor.camera.position;
      return { x: tr.malha.position.x, y: tr.malha.position.y, lat: tr.t.lat, lon: tr.t.lon, cam: [c.x, c.y, c.z] }; })()""")
    dx, dy = depois["x"] - antes["x"], depois["y"] - antes["y"]
    ok(dx > 500 and abs(dy) < 0.1 * dx, f"arrastar para a direita leva a imagem para a direita ({dx:.0f}, {dy:.0f} mm)")
    ok(max(abs(a - b) for a, b in zip(antes["cam"], depois["cam"])) < 1, "a câmera não se mexe no arrasto do Ajustar")
    # a imagem andou para o leste por baixo da obra: a obra agora está num ponto mais a oeste do mundo
    ok(depois["lon"] < antes["lon"] and abs(depois["lat"] - antes["lat"]) < 1e-6, "a obra passa a cair mais a oeste (a amarração anda)")
    time.sleep(1.2)                                                   # a gravação espera 0,5 s parada
    g = _json(API)["terreno"]
    ok(abs(g["lon"] - depois["lon"]) < 1e-7, "o arrasto gravado sozinho no projeto")
    ok(aba.avaliar("window.visor.selecionada === -1 || window.visor.selecionada === undefined || window.visor.selecionada === null"),
       "o arrasto não escolhe peça")

    # o giro do norte
    aba.avaliar("""(() => { const r = document.getElementById('terreno-norte'); r.value = 30; r.dispatchEvent(new Event('input')); return 1; })()""")
    ok(abs(aba.avaliar("window.terreno.malha.rotation.z") - math.radians(30)) < 1e-6, "o Norte gira a imagem (30°)")
    ok(aba.avaliar("document.getElementById('terreno-norte-dd').textContent").startswith("30,00°"), "a ficha mostra o norte novo")
    # o norte fino (usuário, 20/10: "só vai de 0,5 em 0,5"): o número digitado com vírgula e os botões de 0,1°
    aba.avaliar("""(() => { const i = document.getElementById('terreno-norte-num'); i.value = '29,37'; i.dispatchEvent(new Event('input')); return 1; })()""")
    ok(abs(aba.avaliar("window.terreno.malha.rotation.z") - math.radians(29.37)) < 1e-6, "o norte digitado com duas casas (29,37°)")
    aba.avaliar("document.querySelector('[data-passo=\"0.1\"]').click()")
    aba.avaliar("document.querySelector('[data-passo=\"0.1\"]').click()")
    ok(abs(aba.avaliar("window.terreno.t.norte") - 29.57) < 1e-9 and aba.avaliar("document.getElementById('terreno-norte-num').value") == "29,57",
       "+0,1° duas vezes: 29,57°")
    ok(abs(float(aba.avaliar("document.getElementById('terreno-norte').value")) - 29.57) < 1e-9, "a barra acompanha o número")
    aba.avaliar("""(() => { const i = document.getElementById('terreno-norte-num'); i.value = '30'; i.dispatchEvent(new Event('input')); return 1; })()""")
    largos = aba.avaliar("""(() => { const p = document.querySelector('.painel-terreno'), r = p.getBoundingClientRect();
      return [...p.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > r.right + 1 && e.offsetParent)
        .map(e => (e.id || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right - r.right)); })()""")
    ok(not largos, f"o painel sem nada passando da borda: {largos}")
    time.sleep(1.2)
    ok(abs(_json(API)["terreno"]["norte"] - 30) < 1e-6, "o norte gravado no projeto")
    foto(aba, "ver3d_terreno_2_ajustado.png")
    aba.avaliar("document.getElementById('painel-fechar').click()")
    ok(esperar(aba, "!window.terreno.ajustando", 3), "fechar o painel termina o Ajustar")

    # F5: volta igual, pela imagem guardada
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha)", 60), "depois do F5 a imagem volta (guardada no projeto)")
    ok(abs(aba.avaliar("window.terreno.malha.rotation.z") - math.radians(30)) < 1e-6, "com o norte gravado")
    aba.avaliar("document.getElementById('btn-terreno').click()")
    esperar(aba, "!!document.getElementById('terreno-ligado')", 5)
    # a altura da imagem: no 0,00 o subsolo fica embaixo do chão; outra cota digitada; gravada no projeto
    zM = "window.terreno.malha.position.z"
    ok(aba.avaliar("[...document.querySelectorAll('#terreno-cota-sel option')].some(o => o.value === '0')"), "o 0,00 entre as alturas da imagem")
    aba.avaliar("(() => { const s = document.getElementById('terreno-cota-sel'); s.value = '0'; s.dispatchEvent(new Event('change')); return 1; })()")
    ok(abs(aba.avaliar(zM) - (-3)) < 1, f"no nível 0,00 a imagem vai para o 0 ({aba.avaliar(zM):.0f} mm)")
    time.sleep(1.2)
    ok(_json(API)["terreno"].get("cota") == 0, "a altura gravada no projeto (0)")
    aba.avaliar("""(() => { const s = document.getElementById('terreno-cota-sel'); s.value = 'outra'; s.dispatchEvent(new Event('change'));
      const i = document.getElementById('terreno-cota'); i.value = '1,5'; i.dispatchEvent(new Event('input')); return 1; })()""")
    ok(abs(aba.avaliar(zM) - 1497) < 1, f"outra cota digitada (1,5 m → {aba.avaliar(zM):.0f} mm)")
    time.sleep(1.2)
    ok(_json(API)["terreno"].get("cota") == 1500, "a cota digitada gravada (1500)")
    foto(aba, "ver3d_terreno_3_cota.png")
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha)", 60) and abs(aba.avaliar(zM) - 1497) < 1,
       "depois do F5 a imagem continua na cota escolhida")
    aba.avaliar("document.getElementById('btn-terreno').click()")
    esperar(aba, "!!document.getElementById('terreno-cota-sel')", 5)
    ok(aba.avaliar("document.getElementById('terreno-cota-sel').value") == "outra" and not aba.avaliar("document.getElementById('terreno-cota-outra').hidden"),
       "o painel volta mostrando a cota digitada")
    # a transparência (usuário, 20/10: "colocar a imagem com uma certa transparência para ver o subsolo")
    aba.avaliar("(() => { const r = document.getElementById('terreno-transp'); r.value = 40; r.dispatchEvent(new Event('input')); return 1; })()")
    ok(abs(aba.avaliar("window.terreno.malha.material.opacity") - 0.6) < 1e-9, "transparência 40 %: a imagem a 60 %")
    time.sleep(1.2)
    ok(_json(API)["terreno"].get("transparencia") == 0.4, "a transparência gravada no projeto")
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.malha)", 60)
       and abs(aba.avaliar("window.terreno.malha.material.opacity") - 0.6) < 1e-9, "depois do F5 a transparência continua")
    aba.avaliar("document.getElementById('btn-terreno').click()")
    esperar(aba, "!!document.getElementById('terreno-cota-sel')", 5)
    aba.avaliar("(() => { const s = document.getElementById('terreno-cota-sel'); s.value = 'auto'; s.dispatchEvent(new Event('change')); return 1; })()")
    ok(aba.avaliar(zM) < -3400, f"voltar ao automático põe a imagem no pé da obra de novo ({aba.avaliar(zM):.0f} mm)")
    time.sleep(1.2)
    ok("cota" not in _json(API)["terreno"], "o automático tira a cota do projeto")
    aba.avaliar("document.getElementById('terreno-ligado').click()")
    ok(aba.avaliar("window.terreno.grupo.visible === false && !document.getElementById('terreno-fonte')"),
       "desligar a imagem a esconde (e a fonte do canto)")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]   # o 3D aberto direto, sem a área
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
