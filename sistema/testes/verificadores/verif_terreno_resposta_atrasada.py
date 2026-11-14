# -*- coding: utf-8 -*-
"""A resposta atrasada da gravação do terreno não apaga o que a tela mudou com o pedido no ar (14/11, conferência da
0.9.4: o verif_ver3d_chao_sem_imagem caía com a máquina carregada — dois cliques no +5 cm davam 5 cm; a volta da gravação
de antes trocava o chão da tela pelo que tinha ido, e o clique seguinte somava em cima dele). web/visor3d/terreno.js,
_agendarGravacao/_mandar.

No modo ver, com cliques de verdade e a resposta do servidor ATRASADA 1,5 s (embrulho do fetch antes da página abrir):
  A. sem local: Outra cota −0,50; o pedido sai; 1º clique no +5 com ele no ar; a resposta volta; 2º clique → 10 cm:
     a frase, o chão liso, a sombra, o gravado ({cota −500, ajuste 100}) e depois do F5;
  B. com o local (a imagem de teste): o mesmo, pela gravação do local (o ajuste e a imagem em −0,40);
  C. fechar a página logo depois de mexer (antes do meio segundo): o que mudou chega ao projeto (pagehide).
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_terreno_atrasado_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)
json.dump({"nome": "Obra resposta atrasada", "tipo": "ifc", "alterado": "2026-11-14T09:00:00"},
          open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
amb = dict(os.environ, METALICA_TERRENO="1", METALICA_TERRENO_FALSO="1")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
API = base + "/api/projetos/obra/terreno"
falhas = []

# a resposta das gravações do terreno (o local e o chão) chega 1,5 s depois; o pedido chega ao servidor na hora
ATRASO = r"""(() => {
  const orig = window.fetch.bind(window);
  window.__gravacoes = 0;
  window.fetch = async (url, op) => {
    const u = String(url && url.url || url), post = op && String(op.method || '').toUpperCase() === 'POST';
    const r = await orig(url, op);
    if (post && !(op && op.keepalive) && /\/api\/projetos\/[^/]+\/terreno(\/chao)?$/.test(u.split('?')[0])) {
      window.__gravacoes++;
      await new Promise(ok => setTimeout(ok, 1500));
    }
    return r;
  };
})();"""


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def post(rota, corpo):
    pedido = urllib.request.Request(API + rota, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return json.loads(r.read().decode())


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


def clicar_no(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    return True


def digitar(aba, sel, texto):
    aba.avaliar(f"(i => {{ i.focus(); i.select(); return 1; }})(document.querySelector({json.dumps(sel)}))")
    aba.cmd("Input.insertText", text=texto)


PISO = "(v => v.piso.position.z + v.cabecalho.origem[2] + 10)(window.visor)"
SOMBRA = "(window.visor.zDoChao() + window.visor.cabecalho.origem[2])"
FRASE = "document.getElementById('terreno-cota-final').textContent"


def abrir(aba, pronto):
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, f"!!(window.ver3dPronto && window.terreno && window.terreno.estado{pronto})", 90), "o modo ver abre com o terreno")
    if not aba.avaliar("!!document.getElementById('terreno-q')"):
        aba.avaliar("document.getElementById('btn-terreno').click()")
    return esperar(aba, "!!document.getElementById('terreno-ajuste')", 10)


def dois_cliques_com_o_pedido_no_ar(aba, quem="Chão"):
    """Outra cota −0,50 → o pedido sai (0,5 s) → 1º +5 com ele no ar → a resposta volta (1,5 s) → 2º +5."""
    g0 = aba.avaliar("window.__gravacoes")
    aba.avaliar("(s => { s.value = 'outra'; s.dispatchEvent(new Event('change')); return 1; })(document.getElementById('terreno-cota-sel'))")
    digitar(aba, "#terreno-cota", "-0,50")
    ok(esperar(aba, f"window.__gravacoes > {g0}", 5), "a gravação da cota saiu (a resposta vem 1,5 s depois)")
    clicar_no(aba, "[data-ajuste='50']")                # o 1º clique, com o pedido no ar
    aba.drenar(1.9)                                     # a resposta do 1º pedido já voltou (e a do 1º clique está no ar)
    clicar_no(aba, "[data-ajuste='50']")                # o 2º clique
    aba.drenar(0.1)
    frase = aba.avaliar(FRASE)
    ok(frase == f"{quem} em −0,40 (cota −0,50 + 10 cm).", f"a frase logo depois do 2º clique: 10 cm ({frase!r})")
    ok(esperar(aba, f"Math.abs({PISO} + 400) < 1", 2), f"o chão liso em −0,40 ({aba.avaliar(PISO):.0f} mm)")
    aba.drenar(4.5)                                     # as respostas atrasadas todas de volta
    frase = aba.avaliar(FRASE)
    ok(frase == f"{quem} em −0,40 (cota −0,50 + 10 cm).", f"depois de todas as respostas, a frase segue em 10 cm ({frase!r})")
    ok(abs(aba.avaliar(PISO) + 400) < 1, f"e o chão liso em −0,40 ({aba.avaliar(PISO):.0f} mm)")
    ok(abs(aba.avaliar(SOMBRA) + 400) < 1, f"e a sombra em −0,40 ({aba.avaliar(SOMBRA):.0f} mm)")
    ok(aba.avaliar("document.getElementById('terreno-ajuste').value") == "10", "o campo do ajuste em 10")


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_terreno_atrasado_")
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
    aba.cmd("Page.addScriptToEvaluateOnNewDocument", source=ATRASO)
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)

    print("A — sem local: dois cliques no +5 com a gravação no ar")
    ok(abrir(aba, ""), "o painel Terreno abre com o Ajuste")
    ok(_json(API)["terreno"] is None, "projeto sem local")
    dois_cliques_com_o_pedido_no_ar(aba)
    e = _json(API)
    ok(e["terreno"] is None and e.get("chao") == {"cota": -500.0, "ajuste": 100.0}, f"gravado no projeto: {e.get('chao')}")
    ok(abrir(aba, ""), "F5")
    ok(esperar(aba, f"Math.abs({PISO} + 400) < 1", 10), f"depois do F5, o chão em −0,40 ({aba.avaliar(PISO):.0f} mm)")
    ok(aba.avaliar("document.getElementById('terreno-ajuste').value") == "10", "depois do F5, o ajuste em 10")

    print("B — com o local: o mesmo pela gravação do local")
    post("", {"lat": -24.956, "lon": -53.456, "ponto": [0, 0], "norte": 0, "fonte": "teste"})
    post("/chao", {})
    post("/baixar-imagem", {"caixa": [-5000, -5000, 5000, 5000]})
    ok(abrir(aba, " && window.terreno.malha"), "o painel abre com a imagem")
    dois_cliques_com_o_pedido_no_ar(aba, "Imagem")                # com o local, a frase fala da imagem
    z = aba.avaliar("window.terreno.zChao")
    ok(abs(z - (-500 - 3 + 100)) < 1, f"a imagem em −0,40 ({z:.0f} mm)")
    t = _json(API)["terreno"]
    ok(t.get("cota") == -500.0 and t.get("ajuste") == 100.0, f"gravado no local: cota {t.get('cota')}, ajuste {t.get('ajuste')}")
    ok(abrir(aba, " && window.terreno.malha"), "F5")
    ok(esperar(aba, "Math.abs(window.terreno.zChao + 403) < 1", 10), f"depois do F5, a imagem em −0,40 ({aba.avaliar('window.terreno.zChao'):.0f} mm)")

    print("C — fechar a página logo depois de mexer")
    clicar_no(aba, "[data-ajuste='50']")                # 15 cm, e sai antes do meio segundo da espera
    aba.drenar(0.05)
    aba.navegar("about:blank", limite=20)
    t0, aj = time.time(), None
    while time.time() - t0 < 10:
        aj = (_json(API)["terreno"] or {}).get("ajuste")
        if aj == 150.0: break
        time.sleep(0.3)
    ok(aj == 150.0, f"o clique de antes de fechar chegou ao projeto (ajuste {aj})")
finally:
    for p in (nav, srv):
        try: p.kill()
        except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("FALHAS:", len(falhas))
for f in falhas: print("  -", f)
sys.exit(1 if falhas else 0)
