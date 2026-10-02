# -*- coding: utf-8 -*-
"""A ida e volta 2D ↔ 3D no detalhamento (pedido do usuário, 30/09):
(1) a peça escolhida no 3D, no Detalhamento – completo, enquadra o detalhe dela — não a caixa de todos os lugares em
que a marca aparece (a chapa desenhada em cada tesoura: 905 traços, o desenho inteiro);
(2) a chapa das CHAPAS PARA CORTE do chumbamento montado acha a peça no 3D (antes: "essa seleção não é de uma peça
do modelo")."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_l2d_")
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


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                                                                   headers={"Content-Type": "application/json"}), timeout=900))


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_l2d_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos/compressores/detalhar", {})
    completo = [d["nome"] for d in r["desenhos"] if d["grupo"] == "completo"][0]
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos:
            break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"):
        aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + f"/cad?projeto=compressores&desenho={completo}", limite=90)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 1000"):
        aba.drenar(0.5)
    # (1) uma chapa que está no detalhe próprio e dentro dos conjuntos
    res = aba.avaliar("""(() => { const cad = window.cad, ents = [...cad.doc.entidades.values()];
        const por = new Map();
        for (const e of ents) { const a = e.atributos || {}; if (!a.posicao || a.detalhe === 'localizacao') continue;
          for (const p of String(a.posicao).split(/\\s*\\/\\s*/)) { if (!por.has(p)) por.set(p, new Set()); por.get(p).add(a.detalhe); } }
        const p = [...por.entries()].find(([k, s]) => s.has('posicao') && s.has('conjunto'));
        if (!p) return { erro: 'nenhuma posição no detalhe próprio e num conjunto' };
        const todas = ents.filter(e => String((e.atributos || {}).posicao || '').split(/\\s*\\/\\s*/).includes(p[0])
                                        && (e.atributos || {}).detalhe !== 'localizacao');
        const cT = cad.doc.caixa(new Set(todas.map(e => e.id)));
        cad._localizarPelaMarca({ posicoes: [p[0]], conjuntos: [], ids: [] });
        const r = cad.tela.regiao;
        const area = (c) => (c[1][0] - c[0][0]) * (c[1][1] - c[0][1]);
        const dentro = ents.filter(e => { const a = e.atributos || {}; if (a.detalhe !== 'posicao') return false;
          if (!String(a.posicao || '').split(/\\s*\\/\\s*/).includes(p[0])) return false;
          const c = cad.doc.caixa(new Set([e.id])); return c && c[0][0] >= r[0][0] - 1 && c[1][0] <= r[1][0] + 1 && c[0][1] >= r[0][1] - 1 && c[1][1] <= r[1][1] + 1; });
        return { posicao: p[0], todas: todas.length, area_todas: area(cT), area_regiao: area(r), proprias_dentro: dentro.length }; })()""")
    print("      ", res)
    ok("erro" not in res, "achou uma chapa no detalhe próprio e dentro dos conjuntos")
    if "erro" not in res:
        ok(res["area_regiao"] < 0.05 * res["area_todas"], "3D → 2D enquadra o detalhe da peça, não todos os lugares da marca "
           "(%.0f%% da caixa de todos)" % (100.0 * res["area_regiao"] / max(res["area_todas"], 1)))
        ok(res["proprias_dentro"] > 0, "o detalhe próprio da peça está dentro da região enquadrada")
    # (2) a chapa das CHAPAS PARA CORTE acha a peça no 3D
    alvo = aba.avaliar("""(() => { const cad = window.cad;
        const e = [...cad.doc.entidades.values()].find(e => (e.atributos || {}).chapa_de_corte && e.tipo === 'polilinha');
        if (!e) return 'sem chapa de corte no desenho';
        return cad._alvoNo3D([e], true); })()""")
    print("       alvo da chapa de corte:", alvo)
    ok(isinstance(alvo, str) and alvo.startswith("posicao:"), "a chapa para corte do chumbamento acha a peça no 3D (%s)" % alvo)
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
