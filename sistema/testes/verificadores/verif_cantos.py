# -*- coding: utf-8 -*-
"""Editor 3D: Cantos redondos — a análise do projeto lista o joelho P15 com raio e opções,
o diálogo mostra a tabela, a quebra vai para o modelo (14 instâncias) e o modelo recarregado
tem as peças com `quebras`."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8785
DADOS = tempfile.mkdtemp(prefix="metalica_cantos_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cantos_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    # a análise pela API
    r = json.loads(aba.avaliar("""(async () => { const d = await window.editor.api.cantosDoProjeto('compressores'); return JSON.stringify(d.pecas.map(p => [p.marca, p.perfil, p.instancias, Math.round(p.raio), Math.round(p.angulo), p.opcoes.length])); })()"""))
    print("     peças:", r)
    p15 = next((x for x in r if x[0] == "P15"), None)
    ok(p15 is not None and p15[2] == 14 and 500 < p15[3] < 700 and 70 < p15[4] < 85 and p15[5] == 4, f"P15 reconhecido: {p15}")
    ok(not any("FE RED" in x[1] for x in r), "barras redondas fora da lista")
    # o diálogo: abre com a tabela e fecha sem aplicar
    aba.avaliar("window.editor.dialogoCantosRedondos(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor.el.dialogo.open && window.editor.el.dialogoCorpo.querySelectorAll('select').length > 0"): aba.drenar(0.5)
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent")
    n_sel = aba.avaliar("window.editor.el.dialogoCorpo.querySelectorAll('select').length")
    ok("P15" in txt and "Quebrar em" in txt and n_sel >= 1, f"diálogo com a tabela ({n_sel} seletores): " + txt[:120])
    foto(aba, "_cantos.png")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")
    aba.drenar(0.5)
    # a quebra pela API e o modelo recarregado
    r = json.loads(aba.avaliar("""(async () => { const r = await window.editor.api.quebrarCantos('compressores', { P15: 1 }); await window.editor._abrirProjeto();
      const ents = [...window.editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.quebras);
      return JSON.stringify([r.pecas, r.posicoes, ents.length, ents[0] ? ents[0].atributos.quebras.n : null, ents[0] ? ents[0].vertices.length : 0]); })()"""))
    # o joelho encosta no banzo: termina no nó (perna: 2 anéis + 2 nós = 32 vértices)
    ok(r[0] == 14 and r[1] == ["P15"] and r[2] == 14 and r[3] == 1 and r[4] == 32, f"quebra aplicada e recarregada: {r}")
    r2 = json.loads(aba.avaliar("""(async () => { const d = await window.editor.api.cantosDoProjeto('compressores'); return JSON.stringify(d.pecas.map(p => p.marca)); })()"""))
    ok("P15" not in r2, f"P15 já não aparece como canto redondo: {r2}")
    # as quebradas aparecem no diálogo com a opção de voltar
    q = json.loads(aba.avaliar("""(async () => { const d = await window.editor.api.cantosDoProjeto('compressores'); return JSON.stringify((d.quebradas || []).map(p => [p.marca, p.n, p.instancias, p.original])); })()"""))
    ok(q == [["P15", 1, 14, True]], f"quebradas listadas com a malha original guardada: {q}")
    aba.avaliar("window.editor.dialogoCantosRedondos(); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor.el.dialogo.open && window.editor.el.dialogoCorpo.querySelectorAll('input[type=checkbox]').length > 0"): aba.drenar(0.5)
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent")
    ok("Voltar ao canto redondo" in txt and "P15" in txt, "diálogo com a tabela das já quebradas: " + txt[:120])
    foto(aba, "_cantos_voltar.png")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")
    aba.drenar(0.5)
    # volta ao canto redondo pela API: joelho com a malha original (216 vértices), banzo e diagonais como eram
    r3 = json.loads(aba.avaliar("""(async () => { const r = await window.editor.api.desfazerCantos('compressores', ['P15']); await window.editor._abrirProjeto();
      const ents = [...window.editor.documento.entidades.values()];
      const quebradas = ents.filter(e => e.atributos && e.atributos.quebras).length;
      const esticadas = ents.filter(e => e.atributos && e.atributos.estendida_ate_no).length;
      const refeitas = ents.filter(e => e.atributos && e.atributos.diagonal_da_quebra).length;
      const p15 = ents.filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao === 'P15');
      return JSON.stringify([r.pecas, r.posicoes, (r.falhas || []).length, quebradas, esticadas, refeitas, p15.length, p15[0] ? p15[0].vertices.length : 0]); })()"""))
    ok(r3[0] == 14 and r3[1] == ["P15"] and r3[2] == 0 and r3[3] == 0 and r3[4] == 0 and r3[5] == 0 and r3[6] == 14 and r3[7] == 216, f"voltou ao canto redondo: {r3}")
    r4 = json.loads(aba.avaliar("""(async () => { const d = await window.editor.api.cantosDoProjeto('compressores'); return JSON.stringify([d.pecas.map(p => p.marca), (d.quebradas || []).length]); })()"""))
    ok("P15" in r4[0] and r4[1] == 0, f"P15 volta à lista de cantos redondos: {r4}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
