# -*- coding: utf-8 -*-
"""A peça em destaque no 3D (a escolhida no 2D, o "Ver no 3D") se acha nos dois temas (pedido do usuário, 30/09):
cor cheia do destaque (não o azul da seleção misturado ao cinza) e um anel de tamanho fixo na tela em volta
de cada grupo de peças, por cima do modelo; Esc tira os anéis. Fotos em _destaque_claro.png e _destaque_escuro.png."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_dq_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c:
        falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_dq_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos:
            break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"):
        aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    for tema in ("claro", "escuro"):
        aba.navegar(base + f"/editor?projeto=compressores&tema={tema}&destacar=posicao:P77", limite=90)
        t0 = time.time()
        while time.time() - t0 < 90 and not aba.avaliar("!!(window.editor && window.editor.cena && window.editor.cena._marcas)"):
            aba.drenar(1.0)
        aba.drenar(3.0)                      # o segundo enquadramento (1,5 s) e as malhas
        info = aba.avaliar("""(() => { const ed = window.editor, c = ed.cena;
            const ids = [...(c.destaque || [])];
            const cor = (id) => { const o = c.objetos.get(id); if (!o) return null;
              if (o.userData.lote && c.lote) { const it = c.lote.itens.get(id); return it ? it.corMalha : null; }
              const m = o.getObjectByName('malha'); return m && m.material && m.material.color ? '#' + m.material.color.getHexString() : null; };
            return { tema: document.documentElement.getAttribute('data-tema'), destaque: ids.length,
                     aneis: c._marcas ? c._marcas.children.length : 0, cores: [...new Set(ids.map(cor))] }; })()""")
        print("      ", info)
        ok(info["tema"] == tema, f"{tema}: tema aplicado")
        ok(info["destaque"] > 0, f"{tema}: P77 em destaque")
        ok(0 < info["aneis"] <= info["destaque"], f"{tema}: um anel por grupo de peças em destaque ({info['aneis']})")
        ok(info["cores"] and all(c and c.lower() == "#ff5a1f" for c in info["cores"]), f"{tema}: as peças em destaque na cor cheia ({info['cores']})")
        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        with open(os.path.join(AQUI, f"_destaque_{tema}.png"), "wb") as f:
            f.write(base64.b64decode(png))
    # Esc limpa a seleção, o destaque e os anéis
    aba.avaliar("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
    aba.avaliar("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
    aba.drenar(1.0)
    fim = aba.avaliar("({ destaque: !!window.editor.cena.destaque, aneis: !!window.editor.cena._marcas })")
    ok(not fim["destaque"] and not fim["aneis"], f"Esc tira o destaque e os anéis ({fim})")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + (": %s" % erros[:3] if erros else ""))
finally:
    for p in (nav, srv):
        try:
            p.kill()
        except Exception:                                     # noqa: BLE001
            pass
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
