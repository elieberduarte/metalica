# -*- coding: utf-8 -*-
"""O chão do 3D passa na chapa de base, não na ponta do chumbador (13/11, Posto, vídeo das Cenas: "a sombra está considerando
que o chumbador está acima do chão; na verdade ele está abaixo do solo, ela deveria sair da chapinha"). O galpão de exemplo
com chumbadores (papel "chumbador", camada "Chumbadores") descendo 2,5 m abaixo das bases:
  A. na tela das Cenas: o piso do visor no pé das peças SEM os chumbadores (− 10 mm), acima da ponta deles;
  B. o chão da cena (zDoChao — a sombra no chão da foto, os pontos do chão) no mesmo nível;
  C. no modo ver (o mesmo visor): o piso no mesmo nível;
  D. sem os chumbadores no modelo, o piso no fundo da caixa como sempre.
Falha sem a correção (o piso ia para a ponta dos chumbadores). Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_chao_chumbador_")
modelo = json.load(open(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), encoding="utf-8"))
sem = json.loads(json.dumps(modelo))
modelo["camadas"]["Chumbadores"] = {"nome": "Chumbadores", "cor": "#9aa1ab", "visivel": True, "bloqueada": False}
pilares = [e for e in modelo["entidades"] if e.get("papel") == "pilar"][:4]
for k, p in enumerate(pilares):
    x, y, z = p["inicio"]
    for dx in (-120, 120):
        modelo["entidades"].append({"id": f"chumb-{k}-{dx}", "tipo": "barra", "nome": "CH1", "camada": "Chumbadores", "inicio": [x + dx, y, z - 2500],
                                    "fim": [x + dx, y, z + 60], "perfil": "FE RED 3/4''", "papel": "chumbador", "atributos": {}})
for nome, m in (("obra", modelo), ("sem", sem)):
    os.makedirs(os.path.join(DADOS, nome))
    json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
               "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00", "dados": None},
              open(os.path.join(DADOS, nome, "projeto.json"), "w", encoding="utf-8"))
    json.dump(m, open(os.path.join(DADOS, nome, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


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


# o pé das peças à vista sem os chumbadores e a ponta dos chumbadores, contados aqui pelas fichas (mundo)
NIVEIS = r"""(() => { const F = visor.fichas, n = Math.min(F.length, visor.nPecas), cams = visor.cabecalho.camadas;
  let pe = Infinity, ponta = Infinity, nCh = 0;
  for (let i = 0; i < n; i++) { const f = F[i]; if (!f.b || visor.visivelCamada[f.c || 0] === false) continue;
    const ch = f.pp === 'chumbador' || /chumbador/i.test((cams[f.c || 0] || {}).nome || '');
    if (ch) { nCh++; ponta = Math.min(ponta, f.b[2]); } else pe = Math.min(pe, f.b[2]); }
  return { pe, ponta, nCh, piso: visor.piso.position.z, fundo: visor.caixaVisivel().min.z }; })()"""

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_chao_chumbador_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    print("A/B — a tela das Cenas")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta && !!visor.fichas", 180), "a tela das Cenas abriu")
    aba.drenar(1)
    v = aba.avaliar(NIVEIS)
    ok(v["nCh"] == 2 * len(pilares) and v["ponta"] < v["pe"] - 1000, f"os chumbadores descem abaixo das bases ({v})")
    ok(abs(v["piso"] - (v["pe"] - 10)) < 1, f"o piso no pé sem os chumbadores: {v['piso']:.0f} (pé {v['pe']:.0f}; a ponta do chumbador {v['ponta']:.0f})")
    aba.avaliar("cenaApi.novaCena3d('Iso'); 1")
    esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'iso'", 30)
    z = aba.avaliar("cenaApi.estado && visor.zDoPiso(visor._caixaModelo.clone())")
    ok(abs(z - v["pe"]) < 1, f"o chão da cena (zDoChao) no mesmo nível ({z:.0f})")

    print("C — o modo ver")
    aba.navegar(f"{base}/visor3d/ver3d.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.visor && !!visor.fichas && !!visor.piso", 180), "o modo ver abriu")
    aba.drenar(1)
    v2 = aba.avaliar(NIVEIS)
    ok(abs(v2["piso"] - (v2["pe"] - 10)) < 1, f"o piso do modo ver também no pé sem os chumbadores ({v2['piso']:.0f})")

    print("D — sem chumbadores, como sempre")
    aba.navegar(f"{base}/visor3d/cena.html?projeto=sem&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta && !!visor.fichas", 180), "a obra sem chumbadores")
    aba.drenar(1)
    v3 = aba.avaliar(NIVEIS)
    ok(v3["nCh"] == 0 and abs(v3["piso"] - (v3["fundo"] - 10)) < 1, f"o piso no fundo da caixa ({v3})")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
