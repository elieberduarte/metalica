# -*- coding: utf-8 -*-
"""Regressão da câmera do 3D em modelos de formas diferentes — editor e modo ver.

Os defeitos da navegação já corrigidos (testes/REGRESSOES.md, seção Câmera) voltavam quando
chegava um modelo novo (usuário, 16/10/2026): os verificadores da câmera rodavam só no modelo
dos compressores, perto do z = 0, e o que depende da forma do modelo — o piso a +637 m da
Bellacasa (a cota do terreno no IFC), as fundações a −7,35 m do Mercado Conceito, os 354 m da
Passarela, os 134 m de altura do Vicente, uma peça pequena sozinha — nunca era conferido.

Aqui cada situação vira um modelo de teste (barras de verdade, com vãos entre as terças) e,
no editor e no modo ver, com eventos de mouse de verdade (CDP):

  A. abre com o modelo inteiro na tela, nada cortado pelos planos de perto/longe
  B. a roda sobre a peça aproxima 30 cliques: o ponto fica parado sob o cursor e a câmera
     não atravessa a peça (587e5a0: "o BRAMAIS bugava inteiro ao dar zoom")
  C. depois de aproximar, a órbita sobre a peça gira em volta do ponto dela (o ponto fica
     parado; 48d337c, ade2f56, 477583d)
  D. o pan do botão direito sobre a peça: o ponto agarrado acompanha o mouse (e93355d)
  E. a roda no vazio mira perto do modelo, nunca a quilômetros (631d6f7, cda3ed2, 05f0810),
     e a câmera não se afasta do modelo ao aproximar
  F. o pan no vazio desloca o modelo na tela como o mouse (nem parado, nem disparado)
  G. a órbita no vazio mantém o modelo na tela
  H. nenhum erro de JavaScript

Uso:  python testes/verificadores/verif_camera_modelos.py [situação…]
Sai com código 1 se algum passo falhar.
"""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PILAR, VIGA, TERCA = "W 250×32,7", "W 250×32,7", "U 127×50×2,00 (FF)"


def galpao(largura, comprimento, altura, z0=0.0, base=None, passo=6000.0, passo_terca=1500.0):
    """Pórticos a cada `passo`, terças por vão (os vãos entre elas são parte do teste)."""
    doc = Documento()
    nx = max(1, round(comprimento / passo))
    zb, zt = (z0 if base is None else base), z0 + altura
    for i in range(nx + 1):
        x = i * passo
        for y in (0.0, largura):
            doc.add(Barra(nome=f"P{i}-{y:.0f}", inicio=(x, y, zb), fim=(x, y, zt), perfil=PILAR, rotacao=0.0, papel="pilar"))
        doc.add(Barra(nome=f"V{i}", inicio=(x, 0.0, zt), fim=(x, largura, zt), perfil=VIGA, rotacao=0.0, papel="viga"))
    for i in range(nx):
        for j in range(int(largura // passo_terca) + 1):
            y = j * passo_terca
            doc.add(Barra(nome=f"T{i}-{j}", inicio=(i * passo, y, zt + 250), fim=((i + 1) * passo, y, zt + 250),
                          perfil=TERCA, rotacao=0.0, papel="terca"))
    return doc


def torre(lado, altura, passo=3000.0):
    doc = Documento()
    cantos = [(0.0, 0.0), (lado, 0.0), (lado, lado), (0.0, lado)]
    for k, (x, y) in enumerate(cantos):
        doc.add(Barra(nome=f"P{k}", inicio=(x, y, 0.0), fim=(x, y, altura), perfil=PILAR, rotacao=0.0, papel="pilar"))
    for n in range(1, int(altura // passo) + 1):
        for k in range(4):
            a, b = cantos[k], cantos[(k + 1) % 4]
            doc.add(Barra(nome=f"V{n}-{k}", inicio=(a[0], a[1], n * passo), fim=(b[0], b[1], n * passo), perfil=VIGA, rotacao=0.0, papel="viga"))
    return doc


def pequeno():
    doc = Documento()
    doc.add(Barra(nome="a", inicio=(0.0, 0.0, 0.0), fim=(500.0, 0.0, 0.0), perfil=VIGA, rotacao=0.0, papel="viga"))
    doc.add(Barra(nome="b", inicio=(0.0, 300.0, 0.0), fim=(500.0, 300.0, 0.0), perfil=VIGA, rotacao=0.0, papel="viga"))
    doc.add(Barra(nome="c", inicio=(250.0, 0.0, 0.0), fim=(250.0, 300.0, 0.0), perfil=TERCA, rotacao=0.0, papel="viga"))
    return doc


#: nome → (o que imita, o modelo)
SITUACOES = {
    "origem":      ("galpão perto do z = 0 (como o dos compressores)", lambda: galpao(20000, 30000, 6000)),
    "piso-alto":   ("piso a +637 m, a cota do terreno no IFC (Bellacasa)", lambda: galpao(20000, 30000, 6000, z0=637000.0)),
    "fundacao":    ("pilares até −7,35 m, as fundações (Mercado Conceito)", lambda: galpao(20000, 30000, 7300, base=-7350.0)),
    "comprido":    ("354 m de comprimento (Passarela Mirante)", lambda: galpao(4000, 354000, 3000)),
    "alto":        ("134 m de altura (Vicente Residence)", lambda: torre(10000, 134000)),
    "pequeno":     ("três barras de meio metro (uma peça sozinha)", pequeno),
}

#: Tolerâncias (pixels; razões)
PX_PARADO = 4            # o ponto que deveria ficar parado na tela
PX_PAN = 8               # o ponto agarrado pelo pan (o OrbitControls amortece no editor)
PAN_RAZAO = (0.3, 3.0)   # quanto o modelo anda na tela pelo quanto o mouse andou, no vazio

# O adaptador: o mesmo jeito de ler a câmera nas duas telas (o editor em metros, o modo ver em mm locais)
ADAPTADOR = r"""
(async () => {
  const T = await import('three');
  const ed = window.editor;
  let A;
  if (ed) {
    const c = ed.camera, E = 0.001;
    A = { tela: ed.el.canvas, cam: () => c.ativa, alvo: () => c.controles.target,
      caixa: () => { const b = ed.documento.caixa(); return new T.Box3(new T.Vector3(...b[0].map(v => v * E)), new T.Vector3(...b[1].map(v => v * E))); },
      acerto: (x, y) => { const p = c._pecaPertoDoCursor(c._ndcDoEvento({ clientX: x, clientY: y }), []); return p ? p.clone() : null; },
      enquadrar: () => { c.concluirAnimacao(); c.enquadrar(ed.documento.caixa()); } };
  } else {
    const v = window.visor;
    A = { tela: v.tela, cam: () => v.camera, alvo: () => v.controles.target, caixa: () => v._caixaModelo.clone(),
      acerto: (x, y) => { const R = v.tela.getBoundingClientRect(); const lx = x - R.left, ly = y - R.top;
                          return v.escolher(lx, ly) >= 0 ? v._focoSeguro(lx, ly) : null; },
      enquadrar: () => v.enquadrar('iso') };
  }
  const R = () => A.tela.getBoundingClientRect();
  const naTela = (p) => { const cam = A.cam(); cam.updateMatrixWorld(); const q = new T.Vector3(...p).project(cam), r = R();
                          return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height, q.z]; };
  window.__cam = {
    estado() {
      const cam = A.cam(), cx = A.caixa(), esf = cx.getBoundingSphere(new T.Sphere()), r = R();
      return { pos: cam.position.toArray(), alvo: A.alvo().toArray(), near: cam.near, far: cam.far,
               centro: esf.center.toArray(), raio: esf.radius, ate_caixa: cx.distanceToPoint(cam.position),
               tela: [r.left, r.top, r.width, r.height],
               dir: cam.getWorldDirection(new T.Vector3()).toArray() };
    },
    naTela,
    cantos() { const cx = A.caixa(), out = [];
      for (let k = 0; k < 8; k++) out.push(naTela([k & 1 ? cx.max.x : cx.min.x, k & 2 ? cx.max.y : cx.min.y, k & 4 ? cx.max.z : cx.min.z]));
      return out; },
    acerto(x, y) { const p = A.acerto(x, y); return p ? p.toArray() : null; },
    daTela(x, y) { return document.elementFromPoint(x, y) === A.tela; },
    enquadrar() { A.enquadrar(); return 1; },
  };
  return 1;
})()
"""


def preparar_dados(nomes):
    dados = tempfile.mkdtemp(prefix="metalica_camera_")
    for nome in nomes:
        pasta = os.path.join(dados, nome)
        os.makedirs(pasta)
        json.dump({"formato": 1, "nome": nome, "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
                   "criado": "2026-10-16T00:00:00", "alterado": "2026-10-16T00:00:00", "dados": None},
                  open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
        json.dump(SITUACOES[nome][1]().dict(), open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return dados


falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c:
        falhas.append(m)
    return c


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _norma(a): return math.sqrt(sum(x * x for x in a))
def _dist(a, b): return _norma(_sub(a, b))
def _dot(a, b): return sum(x * y for x, y in zip(a, b))


class Tela:
    """Uma das duas telas aberta num projeto: os gestos e as leituras."""

    def __init__(self, aba, nome):
        self.aba, self.nome = aba, nome

    def js(self, expr):
        v = self.aba.avaliar("JSON.stringify(" + expr + ")")
        return json.loads(v) if v is not None else None

    def estado(self): return self.js("window.__cam.estado()")
    def na_tela(self, p): return self.js("window.__cam.naTela(%s)" % json.dumps(p))
    def acerto(self, x, y): return self.js("window.__cam.acerto(%s, %s)" % (x, y))

    def enquadrar(self):
        self.aba.avaliar("window.__cam.enquadrar()")
        self.aba.drenar(0.6)

    def roda(self, x, y, dy, vezes=1):
        for _ in range(vezes):
            self.aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0, deltaY=dy)
            self.aba.drenar(0.05)
        self.aba.drenar(0.3)

    def arrastar(self, x, y, dx, dy, botao, passos=8):
        botoes = {"middle": 4, "right": 2}[botao]
        self.aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none", buttons=0)
        self.aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=botao, buttons=botoes, clickCount=1)
        self.aba.drenar(0.15)
        for k in range(1, passos + 1):
            self.aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x + dx * k / passos, y=y + dy * k / passos,
                         button=botao, buttons=botoes)
            self.aba.drenar(0.04)
        self.aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x + dx, y=y + dy, button=botao, buttons=0, clickCount=1)
        self.aba.drenar(1.0)            # o amortecimento do OrbitControls (editor) assenta
        # … e, com a máquina carregada (a conferência, 20/10: erro do pan 12–14 px; sozinho 3–4 px), o desenho por
        # software leva mais que 1 s para assentar: espera a câmera parar de andar (até 6 s a mais)
        antes, t0 = self.estado()["pos"], time.time()
        while time.time() - t0 < 6:
            self.aba.drenar(0.3)
            agora = self.estado()["pos"]
            if _dist(antes, agora) <= 1e-9 * max(1.0, max(abs(v) for v in agora)):
                break
            antes = agora

    def pixel_na_peca(self):
        """Um pixel com peça direto sob ele, o mais perto do meio da tela."""
        e = self.estado()
        L, T_, W, H = e["tela"]
        cx, cy = L + W / 2, T_ + H / 2
        for raio in range(0, int(min(W, H) * 0.45), 18):
            for k in range(max(1, raio // 6)):
                ang = 2 * math.pi * k / max(1, raio // 6)
                x, y = round(cx + raio * math.cos(ang)), round(cy + raio * math.sin(ang))
                if self.js("window.__cam.daTela(%d, %d)" % (x, y)) and self.acerto(x, y):
                    return x, y
        return None

    def pixel_no_vazio(self):
        """Um pixel sem peça, o mais longe possível do modelo na tela (um dos cantos ou meios das bordas)."""
        e = self.estado()
        L, T_, W, H = e["tela"]
        c = self.na_tela(e["centro"])
        cands = [(L + fx * W, T_ + fy * H) for fx, fy in ((0.06, 0.5), (0.94, 0.5), (0.5, 0.94), (0.06, 0.9), (0.94, 0.9), (0.5, 0.08))]
        cands.sort(key=lambda p: -math.hypot(p[0] - c[0], p[1] - c[1]))
        for x, y in cands:
            x, y = round(x), round(y)
            if self.js("window.__cam.daTela(%d, %d)" % (x, y)) and not self.acerto(x, y):
                return x, y
        return None


def foco_do_zoom(antes, depois):
    """O ponto em volta do qual câmera e alvo foram escalados (o apoio da roda), pelo antes e o depois."""
    f = _dist(depois["pos"], depois["alvo"]) / max(_dist(antes["pos"], antes["alvo"]), 1e-12)
    if abs(1 - f) < 1e-6:
        return None
    return [(pd - f * pa) / (1 - f) for pa, pd in zip(antes["pos"], depois["pos"])]


def no_quadro(t, p, margem=0.0):
    L, T_, W, H = t.estado()["tela"]
    x, y, z = t.na_tela(p)
    return -1 < z < 1 and L - margem * W <= x <= L + W * (1 + margem) and T_ - margem * H <= y <= T_ + H * (1 + margem)


def conferir(t, rotulo):
    p = f"[{rotulo} · {t.nome}]"
    t.enquadrar()
    e0 = t.estado()
    # A. abertura
    L, T_, W, H = e0["tela"]
    cantos = t.js("window.__cam.cantos()")
    fora = [c for c in cantos if not (-1 < c[2] < 1 and L - 2 <= c[0] <= L + W + 2 and T_ - 2 <= c[1] <= T_ + H + 2)]
    ok(all(math.isfinite(v) for v in e0["pos"] + e0["alvo"]) and not fora,
       f"{p} A. enquadrado: os 8 cantos do modelo na tela e entre os planos de perto e de longe ({len(fora)} fora)")

    # B. roda sobre a peça, aproximando
    px = t.pixel_na_peca()
    if not ok(px is not None, f"{p} achou um pixel com peça"):
        return
    x, y = px
    P = t.acerto(x, y)
    pior, atravessou, cortou = 0.0, False, False
    d0 = _dist(e0["pos"], P)
    for _ in range(30):
        t.roda(x, y, -100)
        e = t.estado()
        s = t.na_tela(P)
        pior = max(pior, math.hypot(s[0] - x, s[1] - y))
        prof = _dot(_sub(P, e["pos"]), e["dir"])
        atravessou |= prof <= 0
        cortou |= prof < e["near"]
    d1 = _dist(t.estado()["pos"], P)
    ok(d1 < d0 / 4, f"{p} B. a roda sobre a peça aproximou ({d0:.4g} → {d1:.4g})")
    ok(pior <= PX_PARADO, f"{p} B. o ponto sob o cursor ficou parado na tela ao aproximar (desvio máx {pior:.1f} px)")
    ok(not atravessou and not cortou, f"{p} B. a câmera não atravessou a peça nem o plano de perto a cortou")

    # C. a órbita sobre a peça depois de aproximar: o ponto fica parado
    P2 = t.acerto(x, y)
    if ok(P2 is not None, f"{p} C. a peça continua sob o cursor depois de aproximar"):
        antes = t.estado()
        t.arrastar(x, y, 70, 25, "middle")
        s = t.na_tela(P2)
        andou = _dist(antes["pos"], t.estado()["pos"])
        ok(andou > 0, f"{p} C. a órbita sobre a peça girou a câmera")
        ok(math.hypot(s[0] - x, s[1] - y) <= PX_PARADO,
           f"{p} C. a órbita girou em volta do ponto da peça (ficou a {math.hypot(s[0] - x, s[1] - y):.1f} px do cursor)")

    # D. o pan sobre a peça: o ponto agarrado acompanha o mouse
    t.enquadrar()
    px = t.pixel_na_peca()
    if px:
        x, y = px
        P = t.acerto(x, y)
        t.arrastar(x, y, 90, 40, "right")
        s = t.na_tela(P)
        erro = math.hypot(s[0] - (x + 90), s[1] - (y + 40))
        ok(erro <= PX_PAN, f"{p} D. o pan sobre a peça levou o ponto junto com o mouse (erro {erro:.1f} px)")

    # E. a roda no vazio mira perto do modelo
    t.enquadrar()
    vz = t.pixel_no_vazio()
    if not ok(vz is not None, f"{p} achou um pixel no vazio"):
        return
    vx, vy = vz
    longe_max = e0["raio"] * 1.5 + 2 * (1 if t.nome == "editor" else 1000)
    pior_foco, afastou = 0.0, False
    for _ in range(6):
        antes = t.estado()
        t.roda(vx, vy, -100)
        depois = t.estado()
        F = foco_do_zoom(antes, depois)
        if F is not None:
            pior_foco = max(pior_foco, _dist(F, e0["centro"]))
        afastou |= depois["ate_caixa"] > antes["ate_caixa"] * 1.02 + 1e-9
    ok(pior_foco <= longe_max, f"{p} E. a roda no vazio mirou perto do modelo (o apoio mais longe a {pior_foco / e0['raio']:.2f} raios do centro)")
    ok(not afastou, f"{p} E. aproximando no vazio, a câmera não se afastou do modelo")
    t.roda(vx, vy, 100, vezes=6)
    ok(no_quadro(t, e0["centro"], 0.25), f"{p} E. afastando no vazio, o modelo continua na tela")

    # F. o pan no vazio anda como o mouse
    t.enquadrar()
    c0 = t.na_tela(e0["centro"])
    t.arrastar(vx, vy, 80, -30, "right")
    c1 = t.na_tela(e0["centro"])
    razao = math.hypot(c1[0] - c0[0], c1[1] - c0[1]) / math.hypot(80, 30)
    ok(PAN_RAZAO[0] <= razao <= PAN_RAZAO[1],
       f"{p} F. o pan no vazio deslocou o modelo como o mouse (o modelo andou {razao:.2f}× o que o mouse andou)")

    # G. a órbita no vazio mantém o modelo na tela
    t.enquadrar()
    d_antes = _dist(t.estado()["pos"], e0["centro"])
    t.arrastar(vx, vy, 60, 20, "middle")
    d_depois = _dist(t.estado()["pos"], e0["centro"])
    ok(no_quadro(t, e0["centro"], 0.1) and 0.66 < d_depois / d_antes < 1.5,
       f"{p} G. a órbita no vazio manteve o modelo na tela (distância ×{d_depois / d_antes:.2f})")


def main(pedidas):
    nomes = [n for n in SITUACOES if not pedidas or n in pedidas]
    dados = preparar_dados(nomes)
    porta = _porta_livre()
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://localhost:{porta}"
    chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_camera_")
    nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                            "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: _json(base + "/api/versao"); break
            except Exception: time.sleep(0.5)
        for _ in range(60):
            alvos = [a for a in _json(f"http://127.0.0.1:{cdp}/json/list") if a.get("type") == "page"]
            if alvos: break
            time.sleep(0.5)
        aba = Aba(alvos[0]["webSocketDebuggerUrl"])
        for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)
        aba.navegar(base + "/", limite=60)

        def esperar(expr, limite=90):
            t0 = time.time()
            while time.time() - t0 < limite:
                try:
                    if aba.avaliar(expr): return True
                except Exception: pass
                aba.drenar(0.3)
            return False

        for nome in nomes:
            print(f"\n== {nome}: {SITUACOES[nome][0]}", flush=True)
            for tela, url, pronto in (("editor", f"/editor?projeto={nome}", "window.editor && window.editor.documento && window.editor.documento.entidades.size > 0"),
                                      ("modo ver", f"/visor3d/ver3d.html?projeto={nome}", "!!window.ver3dPronto")):
                aba.console.clear()
                aba.navegar(base + url, limite=90)
                if not ok(esperar(pronto), f"[{nome} · {tela}] abriu"):
                    continue
                aba.drenar(1.5)
                if not ok(aba.avaliar(ADAPTADOR) == 1, f"[{nome} · {tela}] leitura da câmera"):
                    continue
                conferir(Tela(aba, tela), nome)
                erros = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
                ok(not erros, f"[{nome} · {tela}] H. sem erros no console: {erros[:2]}")
    finally:
        try: nav.kill()
        except Exception: pass
        srv.kill()
        shutil.rmtree(dados, ignore_errors=True)
        shutil.rmtree(perfil, ignore_errors=True)
    print()
    print("FALHAS:", len(falhas))
    for f in falhas:
        print("  -", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
