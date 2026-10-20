# -*- coding: utf-8 -*-
"""Os gestos do 3D no celular (visor3d.js, _toque…), com toques de verdade (CDP) na tela em pé, nos modelos de
formas diferentes do verif_camera_modelos (SITUACOES).

Pedido do usuário (20/10/2026, ME SOORO no celular): "posicionar dois dedos na tela e rotacionar como se o eixo
estivesse no meio dos dois pontos"; "quando o zoom está bem próximo, no giro a sensibilidade não se adapta e o
desenho se movimenta muito"; "bem próximo, os eixos se confundem um pouco". O OrbitControls girava sempre em volta
do alvo da câmera, na mesma velocidade perto ou longe, e a pinça mirava o alvo, não os dedos.

  A. dois dedos sobre a peça, abrindo 2×, torcendo 35° e andando: o ponto entre os dedos fica entre os dedos, a
     câmera chega à metade da distância até ele e gira em volta da vertical (≈ 35° − os 6° de folga)
  B. na planta, a torção gira o modelo no mesmo sentido dos dedos (o ponto sob um dedo acompanha o dedo)
  C. de longe, um dedo de lado gira na velocidade de sempre; de perto (depois da pinça), bem mais devagar
  D. um dedo sobre a peça gira em volta do ponto tocado (ele fica parado na tela)
  E. arrastando de lado com o dedo tremendo um pouco para baixo, a vista não inclina (os eixos não se misturam)
  F. nenhum erro de JavaScript
  (e, no A, o visor em movimento durante o gesto — a imagem leve e a sombra da apresentação parada — e fora dele depois)

Uso:  python testes/verificadores/verif_celular_gestos.py [situação…]
Sai com código 1 se algum passo falhar.
"""
import json, math, os, shutil, subprocess, sys, tempfile, time
AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(AQUI, "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes")); sys.path.insert(0, AQUI)
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from verif_camera_modelos import SITUACOES, preparar_dados, ADAPTADOR

PX_PARADO = 4            # o ponto que deveria ficar parado (ou entre os dedos) na tela
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c:
        falhas.append(m)
    return c


def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# as leituras que o gesto precisa além das do verif_camera_modelos
EXTRA = r"""
(async () => {
  const T = await import('three');
  const v = window.visor;
  v.leveAoGirar = true;              // como no celular (o modo ver do PC deixa a imagem inteira ao girar)
  Object.assign(window.__cam, {
    // o rumo (em volta da vertical) e a inclinação da direção da vista, em radianos
    rumo() { const d = v.camera.getWorldDirection(new T.Vector3()); return Math.atan2(d.y, d.x); },
    inclinacao() { const d = v.camera.getWorldDirection(new T.Vector3()); return Math.asin(Math.max(-1, Math.min(1, d.z))); },
    // o ponto na altura z sob (x, y) da página
    noPlano(x, y, z) { const R = v.tela.getBoundingClientRect(), r = new T.Raycaster();
      v.camera.updateMatrixWorld();
      r.setFromCamera(new T.Vector2((x - R.left) / R.width * 2 - 1, -((y - R.top) / R.height) * 2 + 1), v.camera);
      const p = r.ray.intersectPlane(new T.Plane(new T.Vector3(0, 0, 1), -z), new T.Vector3()); return p ? p.toArray() : null; },
    vista(n) { v.enquadrar(n); return 1; },
  });
  return 1;
})()
"""


class Celular:
    def __init__(self, aba):
        self.aba = aba

    def js(self, expr):
        r = self.aba.avaliar("JSON.stringify(" + expr + ")")
        return json.loads(r) if r is not None else None

    def estado(self): return self.js("window.__cam.estado()")
    def na_tela(self, p): return self.js("window.__cam.naTela(%s)" % json.dumps(p))
    def acerto(self, x, y): return self.js("window.__cam.acerto(%s, %s)" % (x, y))
    def rumo(self): return self.js("window.__cam.rumo()")
    def inclinacao(self): return self.js("window.__cam.inclinacao()")

    def vista(self, nome="iso"):
        self.aba.avaliar("window.__cam.vista(%s)" % json.dumps(nome))
        self.aba.drenar(0.5)

    def dedos(self, caminhos, passos=14):
        """Os dedos descem juntos, seguem cada um o seu caminho (t de 0 a 1 → x, y) e sobem juntos."""
        pts = lambda t: [{"x": c(t)[0], "y": c(t)[1], "id": i} for i, c in enumerate(caminhos)]
        self.aba.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=pts(0))
        self.aba.drenar(0.15)
        for k in range(1, passos + 1):
            self.aba.cmd("Input.dispatchTouchEvent", type="touchMove", touchPoints=pts(k / passos))
            self.aba.drenar(0.04)
            if k == passos // 2:
                self.no_meio = self.js("window.visor._emMovimento === true")
        self.aba.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        self.aba.drenar(0.5)

    def pinca(self, mx, my, r0, r1, a0=0.0, a1=0.0, dx=0.0, dy=0.0, passos=14):
        """Dois dedos em volta de (mx, my): o raio vai de r0 a r1, o ângulo de a0 a a1, o meio anda (dx, dy)."""
        def dedo(lado):
            def c(t):
                r, a = r0 + (r1 - r0) * t, a0 + (a1 - a0) * t
                return (mx + dx * t + lado * r * math.cos(a), my + dy * t + lado * r * math.sin(a))
            return c
        self.dedos([dedo(1), dedo(-1)], passos)

    def arrasto(self, x, y, dx, dy, passos=14):
        self.dedos([lambda t: (x + dx * t, y + dy * t)], passos)

    def pixel_na_peca(self):
        """Um pixel com peça sob ele, o mais perto do meio da tela (com folga para os dois dedos em volta)."""
        L, T_, W, H = self.estado()["tela"]
        cx, cy = L + W / 2, T_ + H / 2
        # a passarela de 354 m na tela em pé é uma linha fina: a busca anda de 7 em 7 px
        for raio in range(0, int(min(W, H) * 0.4), 7):
            for k in range(max(1, raio // 3)):
                ang = 2 * math.pi * k / max(1, raio // 3)
                x, y = round(cx + raio * math.cos(ang)), round(cy + raio * math.sin(ang))
                if self.js("window.__cam.daTela(%d, %d)" % (x, y)) and self.acerto(x, y):
                    return x, y
        return None


def _ang(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def conferir(c, rotulo):
    p = f"[{rotulo}]"
    # A. dois dedos: pinça + torção + arrasto em volta do ponto entre eles
    c.vista("iso")
    px = c.pixel_na_peca()
    if not ok(px is not None, f"{p} achou um pixel com peça"):
        return
    x, y = px
    P = c.acerto(x, y)
    e0, rumo0 = c.estado(), c.rumo()
    d0 = _dist(e0["pos"], P)
    c.pinca(x, y, 50, 100, 0.0, math.radians(35), dx=30, dy=40)
    ok(c.no_meio, f"{p} A. no meio do gesto, o visor está em movimento (imagem leve, sombra parada)")
    ok(c.js("window.visor._emMovimento") is not True, f"{p} A. soltos os dedos, o movimento terminou")
    s = c.na_tela(P)
    erro = math.hypot(s[0] - (x + 30), s[1] - (y + 40))
    ok(erro <= PX_PARADO, f"{p} A. o ponto entre os dedos ficou entre os dedos (a {erro:.1f} px)")
    razao = _dist(c.estado()["pos"], P) / d0
    ok(0.45 <= razao <= 0.55, f"{p} A. abrir os dedos 2× levou a câmera à metade da distância até o ponto (×{razao:.2f})")
    giro = math.degrees(_ang(c.rumo() - rumo0))
    ok(24 <= giro <= 32, f"{p} A. torcer 35° girou a vista {giro:.1f}° em volta da vertical do ponto")

    # B. na planta: o ponto sob um dedo acompanha o dedo na torção
    c.vista("topo")
    px = c.pixel_na_peca()
    if px:
        x, y = px
        z = c.acerto(x, y)[2]
        a = (x + 80, y)
        Pa = c.js("window.__cam.noPlano(%s, %s, %s)" % (a[0], a[1], z))
        c.pinca(x, y, 80, 80, 0.0, math.radians(40))
        s = c.na_tela(Pa)
        ang = math.degrees(math.atan2(s[1] - y, s[0] - x))
        ok(28 <= ang <= 40, f"{p} B. na planta, a torção levou o ponto sob o dedo junto ({ang:.1f}° de 34°)")

    # C. a velocidade do giro de um dedo: de longe a de sempre, de perto bem menor
    c.vista("iso")
    px = c.pixel_na_peca()
    if not px:
        return
    x, y = px
    H = c.estado()["tela"][3]
    cheio = math.degrees(120 * 2 * math.pi / H)          # a velocidade do OrbitControls (rotateSpeed 1)
    r0 = c.rumo()
    c.arrasto(x, y, 120, 0)
    longe = abs(math.degrees(_ang(c.rumo() - r0)))
    ok(0.85 * cheio <= longe <= 1.1 * cheio, f"{p} C. de longe, o dedo girou na velocidade de sempre ({longe:.0f}° de {cheio:.0f}°)")
    c.vista("iso")
    x, y = c.pixel_na_peca()
    for _ in range(3):                                   # chega bem perto da peça pela pinça
        c.pinca(x, y, 30, 150)
        x, y = c.pixel_na_peca() or (x, y)
    P = c.acerto(x, y)
    if not ok(P is not None, f"{p} C. de perto, ainda há peça sob o dedo"):
        return
    perto_d = _dist(c.estado()["pos"], P) / c.estado()["raio"]
    r0 = c.rumo()
    c.arrasto(x, y, 120, 0)
    perto = abs(math.degrees(_ang(c.rumo() - r0)))
    ok(0.25 * cheio <= perto <= 0.6 * cheio,
       f"{p} C. de perto ({perto_d:.2f} raio do modelo), o mesmo dedo girou só {perto:.0f}° (de longe {longe:.0f}°)")
    # D. em volta do ponto tocado
    s = c.na_tela(P)
    ok(math.hypot(s[0] - x, s[1] - y) <= PX_PARADO, f"{p} D. o giro de um dedo foi em volta do ponto tocado (a {math.hypot(s[0] - x, s[1] - y):.1f} px)")
    # E. de lado com o dedo tremendo para baixo: a vista não inclina
    x, y = c.pixel_na_peca() or (x, y)
    i0 = c.inclinacao()
    c.arrasto(x, y, 110, 14)
    di = abs(math.degrees(c.inclinacao() - i0))
    ok(di < 0.5, f"{p} E. arrastando de lado (14 px de tremor), a inclinação da vista ficou ({di:.2f}°)")


def _celular():
    """Um Chrome novo na tela em pé de um celular, com toque. Um por modelo: depois da troca de página no mesmo Chrome,
    os toques do CDP deixavam de chegar à página (nenhum evento; o mesmo modelo sozinho passava)."""
    exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_gestos_")
    nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                            "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            alvos = [a for a in _json(f"http://127.0.0.1:{cdp}/json/list") if a.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=1, mobile=True)
    aba.cmd("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    return nav, perfil, aba


def main(pedidas):
    nomes = [n for n in SITUACOES if not pedidas or n in pedidas]
    dados = preparar_dados(nomes)
    porta = _porta_livre()
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://localhost:{porta}"
    try:
        for _ in range(60):
            try: _json(base + "/api/versao"); break
            except Exception: time.sleep(0.5)
        for nome in nomes:
            print(f"\n== {nome}: {SITUACOES[nome][0]}", flush=True)
            nav, perfil, aba = _celular()
            try:
                aba.navegar(base + f"/visor3d/ver3d.html?projeto={nome}", limite=90)
                t0 = time.time()
                while time.time() - t0 < 90 and not aba.avaliar("!!window.ver3dPronto"):
                    aba.drenar(0.3)
                if not ok(aba.avaliar("!!window.ver3dPronto"), f"[{nome}] abriu"):
                    continue
                aba.drenar(1.5)
                if not ok(aba.avaliar(ADAPTADOR) == 1 and aba.avaliar(EXTRA) == 1, f"[{nome}] leitura da câmera"):
                    continue
                conferir(Celular(aba), nome)
                erros = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
                ok(not erros, f"[{nome}] F. sem erros no console: {erros[:2]}")
            finally:
                try: nav.kill()
                except Exception: pass
                time.sleep(0.5)
                shutil.rmtree(perfil, ignore_errors=True)
    finally:
        srv.kill()
        shutil.rmtree(dados, ignore_errors=True)
    print()
    print("FALHAS:", len(falhas))
    for f in falhas:
        print("  -", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
