# -*- coding: utf-8 -*-
"""O modo ver não esconde peça sem aviso (Residencial Madrid, 11/11, pelo chat da obra: o modelo com 994 peças e o modo
ver com 811 — as 183 ripas e testeiras em cartola "Cr 50×60×15×0,95…", fora do catálogo, não apareciam e o usuário achou
que tinham sido retiradas do modelo).

Um projeto longe da origem (como o da obra) com duas ripas cartola fora do catálogo e uma barra de perfil inventado:
  A. as cartolas aparecem (o 3D leve tem 2 peças, desenhadas pelo nome "Cr h×B×C×t");
  B. o rodapé avisa a peça que ficou sem desenho, com o perfil: "⚠ 1 peça sem desenho (PERFIL INVENTADO 99: 1)";
  C. sem erros no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_sem_desenho_")
X0, Y0, Z0 = 137526.0, 72917.0, 6427.0


def barra(id_, perfil, dy):
    return {"id": id_, "tipo": "barra", "inicio": [X0, Y0 + dy, Z0], "fim": [X0 + 3000.0, Y0 + dy, Z0], "perfil": perfil,
            "rotacao": 0.0, "camada": "Ripas", "material": ""}


pasta = os.path.join(DADOS, "madrid")
os.makedirs(pasta)
json.dump({"nome": "madrid", "tipo": "3d", "alterado": "2026-11-11T10:00:00"}, open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "madrid", "unidade": "mm", "camadas": {"Ripas": {"nome": "Ripas", "cor": "#888888", "visivel": True}}, "materiais": {},
           "entidades": [barra("r1", "Cr 50×60×15×0,95", 0.0), barra("r2", "Cr 50×80×15×1,95", 320.0),
                         barra("x1", "PERFIL INVENTADO 99", 640.0)]},
          open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base_url = f"http://localhost:{PORTA}"
falhas = []


def ok(c, msg):
    print(("  ok    " if c else "  FALHA ") + msg, flush=True)
    if not c: falhas.append(msg)


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_sem_desenho_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base_url + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=90):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                v = aba.avaliar(expr)
                if v: return v
            except Exception: pass
            aba.drenar(0.3)
        return None

    aba.navegar(base_url + "/visor3d/ver3d.html?projeto=madrid", limite=60)
    ok(bool(esperar("!!(window.ver3dPronto && window.visor && visor.fichas)", 180)), "o modo ver abriu")
    n = aba.avaliar("visor.nPecas")
    ok(n == 2, f"[A] as duas ripas cartola fora do catálogo aparecem ({n} peças no 3D leve)")
    rod = esperar("(() => { const t = document.querySelector('#situacao').textContent; return t.includes('sem desenho') ? t : null; })()", 30) or \
        aba.avaliar("document.querySelector('#situacao').textContent")
    print("     rodapé:", rod)
    ok("⚠ 1 peça sem desenho (PERFIL INVENTADO 99: 1)" in (rod or ""), "[B] o rodapé avisa a peça sem desenho, com o perfil")
    ok("2 peças" in (rod or ""), "[B] e conta as peças desenhadas")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"[C] sem erros no console: {erros[:3]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
