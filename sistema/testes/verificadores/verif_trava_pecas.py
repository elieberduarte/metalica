# -*- coding: utf-8 -*-
"""Trava da peça gerada (regra R5, combinada com o usuário em 02/10): no desenho gerado do 3D a geometria da peça não
se edita — apagar um furo ou esticar uma linha dela é recusado, com o caminho ("Editar isolada/no local"); mover ou
apagar a célula inteira (arrumar a prancha) passa; no ambiente de edição (faixa EDITANDO) a peça é livre e a camada
REFERENCIA continua travada para tudo."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_tr_")
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


def esperar(aba, cond, limite=90):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(cond):
        aba.drenar(0.5)
    return aba.avaliar(cond)


JS_CMD = "const C = await import('/cad/nucleo/comandos.js');"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_tr_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    post("/api/projetos/compressores/detalhar", {"grupos": ["chaparias"]})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos:
            break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"):
        aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/cad?projeto=compressores&desenho=detalhamento-chaparias", limite=90)
    esperar(aba, "document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 50")
    # 1) um furo da peça: apagar é recusado
    r = aba.avaliar("""(async () => { const cad = window.cad;
        const f = [...cad.doc.entidades.values()].find(e => e.camada === 'FURO' && (e.atributos || {}).posicao && (e.atributos || {}).detalhe);
        if (!f) return null;
        cad.tela.selecao.clear(); cad.tela.selecao.add(f.id); cad.apagarSelecao();
        return { existe: !!cad.doc.get(f.id), aviso: [...document.querySelectorAll('.aviso')].map(x => x.textContent).join(' | '), pos: f.atributos.posicao }; })()""")
    ok(r and r["existe"], f"apagar um furo da peça gerada é recusado ({(r or {}).get('pos')})")
    ok(r and "Editar" in r["aviso"], "o aviso mostra o caminho (Editar isolada / no local)")
    # 2) a célula inteira: mover passa; mexer numa linha só, não
    r = aba.avaliar("""(async () => { %s const cad = window.cad;
        const f = [...cad.doc.entidades.values()].find(e => e.camada === 'FURO' && (e.atributos || {}).posicao && (e.atributos || {}).detalhe);
        const k = cad._celulaDaPeca(f);
        const cel = [...cad.doc.entidades.values()].filter(e => cad._pecaTravada(e) && cad._celulaDaPeca(e) === k);
        const mover = (es) => es.map(e => { const n = JSON.parse(JSON.stringify(e));
            if (n.vertices) n.vertices = n.vertices.map(p => [p[0] + 50, p[1]]);
            if (n.centro) n.centro = [n.centro[0] + 50, n.centro[1]];
            if (n.a) n.a = [n.a[0] + 50, n.a[1]]; if (n.b) n.b = [n.b[0] + 50, n.b[1]]; return n; });
        const uma = cad.executar(new C.ComandoSubstituir(mover([cel[0]]), 'teste uma'));
        const toda = cad.executar(new C.ComandoSubstituir(mover(cel), 'teste célula'));
        return { uma: !!uma, toda: !!toda, n: cel.length }; })()""" % JS_CMD)
    ok(r and not r["uma"], "mover uma linha só da peça é recusado")
    ok(r and r["toda"], f"mover a célula inteira passa ({(r or {}).get('n')} objetos)")
    # 3) cota e texto continuam livres
    r = aba.avaliar("""(async () => { %s const cad = window.cad;
        const c = [...cad.doc.entidades.values()].find(e => e.tipo === 'cota');
        if (!c) return null;
        return !!cad.executar(new C.ComandoRemover([c.id], 'apagar cota')); })()""" % JS_CMD)
    ok(r is True, "apagar uma cota gerada (apresentação) passa")
    # 4) no ambiente de edição a peça é livre; a REFERENCIA travada não
    e = post("/api/projetos/compressores/detalhar-posicao", {"marca": "P77", "edicao": True, "modo": "local"})
    aba.navegar(base + f"/cad?projeto=compressores&desenho={e['nome']}", limite=90)
    esperar(aba, "document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 5")
    r = aba.avaliar("""(async () => { %s const cad = window.cad; const ents = [...cad.doc.entidades.values()];
        const f = ents.find(e => e.camada === 'FURO' && (e.atributos || {}).furo != null);
        const ref = ents.filter(e => e.camada === 'REFERENCIA');
        const furo = !!cad.executar(new C.ComandoRemover([f.id], 'apagar furo'));
        const tudo = !!cad.executar(new C.ComandoRemover(ents.filter(e => cad.doc.get(e.id)).map(e => e.id), 'Ctrl+A apagar'));
        return { furo, tudo, ref: ref.length, ref_ainda: ref.filter(e => cad.doc.get(e.id)).length }; })()""" % JS_CMD)
    ok(r and r["furo"], "no ambiente de edição o furo da peça se apaga")
    ok(r and r["tudo"] and r["ref"] > 0 and r["ref_ainda"] == r["ref"], f"tudo selecionado e apagado: sai a peça, a REFERENCIA travada fica ({r})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
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
