# -*- coding: utf-8 -*-
"""Gerar cenas (roteiro de refino, item 3; usuário, 12/11: "ter uma opção para gerar algumas cenas como essas pré-programadas,
sem eu precisar ir tirando cena por cena"; amostra-16 aprovada no SESI: os 4 cantos a 30°). Na tela das Cenas, com o galpão
de exemplo e cliques de verdade:
  A. ✨ Gerar cenas… abre a janela; Gerar cria as 4 aéreas (sudoeste, sudeste, nordeste, noroeste) no servidor;
  B. cada uma: a câmera no canto certo (azimute 225/315/45/135° ± 1°), a 30° de altura, lente 40°, quadro 16:9; o sol de trás
     de quem olha (azimute + 40°, 45°);
  C. o prédio inteiro no quadro e grande: os cantos de todas as camadas ligadas dentro da imagem, e pelo menos um lado
     ocupando ≥ 85 % (antes, pela caixa da obra inteira, o prédio ficava pequeno);
  D. de novo: os nomes repetidos ganham número (Aérea sudoeste 2…), nenhuma cena some;
  E. a camada desligada fica desligada nas aéreas e não conta no enquadramento;
  F. o menu Cenas › Gerar cenas aéreas… (?gerar=1) abre a janela direto;
  G. o render de uma aérea sai (com a sombra nos cantos) e sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, math
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_gerar_cenas_")
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
AZ = {"Aérea sudoeste": 225, "Aérea sudeste": 315, "Aérea nordeste": 45, "Aérea noroeste": 135}


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


def servidor():
    return json.loads(urllib.request.urlopen(API, timeout=30).read())["cenas"]


# quanto da imagem 16:9 os cantos das camadas ligadas ocupam, pela câmera gravada da cena (mm do projeto): [max |x|, max |y|]
OCUPA = r"""((cam) => {
  const T = visor.camera.position.constructor, o = visor.cabecalho.origem;
  const pos = new T(cam.posicao[0] - o[0], cam.posicao[1] - o[1], cam.posicao[2] - o[2]);
  const alv = new T(cam.alvo[0] - o[0], cam.alvo[1] - o[1], cam.alvo[2] - o[2]);
  const fr = alv.clone().sub(pos).normalize(), r = new T().crossVectors(fr, new T(0, 0, 1)).normalize(), u = new T().crossVectors(r, fr);
  const tv = Math.tan(cam.fov * Math.PI / 360), th = tv * 16 / 9;
  let mx = 0, my = 0;
  visor.cabecalho.camadas.forEach((cm, i) => { if (visor.visivelCamada[i] === false || !cm.caixa) return;
    for (let k = 0; k < 8; k++) { const p = new T(cm.caixa[k & 1 ? 1 : 0][0], cm.caixa[k & 2 ? 1 : 0][1], cm.caixa[k & 4 ? 1 : 0][2]).sub(pos);
      const d = p.dot(fr); mx = Math.max(mx, Math.abs(p.dot(r)) / (d * th)); my = Math.max(my, Math.abs(p.dot(u)) / (d * tv)); } });
  return [mx, my];
})"""


def conferir(aba, cenas, rotulo):
    for c in cenas:
        nome = c["nome"].rstrip(" 0123456789")
        az = AZ.get(nome)
        cam = c.get("camera") or {}
        p, a = cam.get("posicao"), cam.get("alvo")
        if not (az is not None and p and a):
            ok(False, f"{rotulo} {c['nome']}: câmera ({cam})"); continue
        dx, dy, dz = (p[i] - a[i] for i in range(3))
        azc = math.degrees(math.atan2(dy, dx)) % 360
        el = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        dif = min(abs(azc - az), 360 - abs(azc - az))
        ok(dif < 1 and abs(el - 30) < 1 and abs(cam.get("fov", 0) - 40) < 0.01 and c.get("proporcao") == "16:9",
           f"{rotulo} {c['nome']}: no canto (azimute {azc:.1f}°), a 30° ({el:.1f}°), lente 40, 16:9")
        sol = c.get("sol") or {}
        ok(abs(sol.get("direcao", -99) - (az + 40) % 360) < 0.2 and sol.get("altura") == 45, f"{rotulo} {c['nome']}: o sol de trás de quem olha ({sol})")
        mx, my = aba.avaliar(f"{OCUPA}({json.dumps(cam)})")
        ok(mx <= 1.0 and my <= 1.0 and max(mx, my) >= 0.85, f"{rotulo} {c['nome']}: o prédio inteiro e grande no quadro (x {mx:.2f}, y {my:.2f})")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_gerar_cenas_")
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

    print("A — Gerar as aéreas")
    ok(clicar_no(aba, "#gerar-cenas-bt") and esperar(aba, "!!document.getElementById('gerar-cenas')", 5), "✨ Gerar cenas… abre a janela")
    ok(aba.avaliar("document.getElementById('gerar-aereas').checked"), "Aéreas dos 4 cantos já marcada")
    clicar_no(aba, "#gerar-ok")
    ok(esperar(aba, "!!window.cenasGeradas && !document.getElementById('gerar-cenas')", 60), "Gerar: a janela fecha")
    cenas = servidor()
    nomes = [c["nome"] for c in cenas]
    ok(sorted(nomes) == sorted(AZ), f"as 4 aéreas no servidor ({nomes})")
    ok(esperar(aba, "document.querySelectorAll('.cartao-cena').length === 4", 10), "os 4 cartões na lista")

    print("B/C — o canto, a altura, o sol e o enquadramento")
    conferir(aba, cenas, "1ª")

    print("D — de novo: os nomes ganham número")
    clicar_no(aba, "#gerar-cenas-bt"); esperar(aba, "!!document.getElementById('gerar-cenas')", 5)
    aba.avaliar("window.cenasGeradas = null; 1")
    clicar_no(aba, "#gerar-ok")
    esperar(aba, "!!window.cenasGeradas", 60)
    nomes2 = sorted(c["nome"] for c in servidor())
    ok(len(nomes2) == 8 and "Aérea sudoeste 2" in nomes2 and "Aérea noroeste 2" in nomes2, f"8 cenas, as novas com o 2 ({nomes2})")

    print("E — a camada desligada")
    camadas = aba.avaliar("visor.cabecalho.camadas.map(c => c.nome)")
    alvo = next((n for n in camadas if "fecham" in n.lower() or "telha" in n.lower() or "cobert" in n.lower()), camadas[-1] if camadas else None)
    i = camadas.index(alvo) if alvo else -1
    ok(i >= 0, f"uma camada para desligar ({alvo} de {camadas})")
    if i >= 0:
        # desliga pela própria tela (a lista de camadas do painel), como o usuário
        aba.avaliar(f"(() => {{ const cb = [...document.querySelectorAll('#camadas-caixa input[type=checkbox]')].find(c => (c.closest('label') || c.parentElement).textContent.includes({json.dumps(alvo)})); if (cb) cb.click(); return !!cb; }})()")
        aba.drenar(1.0)
        aba.avaliar("window.cenasGeradas = null; cenaApi.gerarAereas().then(ids => window.cenasGeradas = ids); 1")
        esperar(aba, "!!window.cenasGeradas", 60)
        ids = aba.avaliar("window.cenasGeradas")
        novas = [c for c in servidor() if c["id"] in ids]
        ok(len(novas) == 4 and all(("camada:" + alvo) in (c.get("desligadas") or []) for c in novas),
           f"as aéreas novas com \"{alvo}\" desligada ({[c.get('desligadas') for c in novas][:1]})")
        conferir(aba, novas, "sem a camada")

    print("F — o menu Cenas › Gerar cenas aéreas… (?gerar=1)")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro&gerar=1", limite=90)
    ok(esperar(aba, "!!window.cenaPronta && !!document.getElementById('gerar-cenas')", 180), "a janela abre direto")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    ok(esperar(aba, "!document.getElementById('gerar-cenas')", 5) or clicar_no(aba, "#gerar-nao"), "Esc / Cancelar fecha sem gerar")
    ok(len(servidor()) == 12, "nada gerado ao fechar")

    print("G — o render de uma aérea")
    cid = next(c["id"] for c in servidor() if c["nome"] == "Aérea sudeste")
    aba.avaliar(f"window.aberta = false; cenaApi.abrirCena('{cid}', {{ recarregar: false }}).then(() => window.aberta = true); 1")
    esperar(aba, "window.aberta", 60)
    aba.avaliar("window.img = null; cenaApi.imagemDaCena3d(960, 540, 1, null, false, null, { cantos: true }).then(c => window.img = c.width + 'x' + c.height, e => window.img = 'erro ' + e.message); 1")
    ok(esperar(aba, "!!window.img", 300) and aba.avaliar("window.img") == "960x540", f"o render sai ({aba.avaliar('window.img')})")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
