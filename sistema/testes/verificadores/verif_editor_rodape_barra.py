# -*- coding: utf-8 -*-
"""O rodapé do editor 3D com a barra de andamento (D08 do usuario-desastrado, 13/11: na tela dividida 2D + 3D, o
"malhas: locais · lote" do rodapé do 3D quebrava em duas linhas por cima do botão Cancelar da barra do progresso.js).
No navegador de verdade:
  A. o editor sozinho na largura do quadro 3D da tela dividida (800 px) e mais estreito (640 px), com uma barra do
     progresso.js COM o Cancelar (tarefa de projeto) e o indicador das malhas escrito: nada do rodapé se cobre, nada sai
     para fora, o Cancelar não cruza o indicador das malhas, e o indicador volta quando a barra sai;
  B. a tela dividida de verdade (/dividida, vista=ambos, 1600 px): o mesmo no quadro 3D.
Falha sem a correção (editor.css: a barra encolhia abaixo do que mostra e o Cancelar vazava por cima do indicador).
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
DADOS = tempfile.mkdtemp(prefix="metalica_rodape_3d_")
PASTA = os.path.join(DADOS, "obra-rodape")
os.makedirs(PASTA)
v = [[0, 0, 0], [500, 0, 0], [500, 500, 0], [0, 500, 0], [0, 0, 3000], [500, 0, 3000], [500, 500, 3000], [0, 500, 3000]]
f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
json.dump({"nome": "obra-rodape", "unidade": "mm", "camadas": {"Layer0": {"nome": "Layer0", "cor": "#8a94a6", "visivel": True, "bloqueada": False}},
           "materiais": {}, "entidades": [{"id": "P1", "tipo": "solido", "nome": "P1", "camada": "Layer0", "material": "", "vertices": v,
                                          "faces": f, "arestas_vivas": [], "atributos": {}}]},
          open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"formato": 1, "nome": "Obra rodapé", "tipo": "ifc", "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00"},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_rodape_3d_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# `D` = o documento do editor (a página ou o quadro f3d); a barra com o Cancelar (url de projeto) e o indicador das malhas
POR_BARRA = """((D, W) => {
  W.__pararBarra && W.__pararBarra(false);
  D.getElementById('estado-servidor').textContent = 'malhas: locais · lote';
  W.editor.dica('Detalhando peças e conjuntos — gravando os desenhos (3 de 12)');
  W.__pararBarra = W.metalicaProgresso.acompanhar({ url: '/api/projetos/obra-rodape/progresso', tarefa: 'detalhar', rotulo: 'Detalhando',
    onde: D.getElementById('dica'), andamento: () => ({ etapa: 'gravando os desenhos (3 de 12)', fracao: 0.11 }) });
  return 1; })(%s)"""

MEDIR = """((D) => {
  const r = D.querySelector('.rodape');
  const pecas = [...r.children].filter(e => e.offsetParent && e.getBoundingClientRect().width > 0);
  const caixas = pecas.map(e => {
    const b = e.getBoundingClientRect();
    const larg = Math.max(b.width, e.scrollWidth && D.defaultView.getComputedStyle(e).overflow === 'visible' ? e.scrollWidth : 0);
    return { nome: e.id || e.className, esq: b.left, dir: b.left + larg, topo: b.top, base: b.bottom };
  });
  const cobre = [];
  for (let i = 0; i < caixas.length; i++) for (let j = i + 1; j < caixas.length; j++) {
    const a = caixas[i], c = caixas[j];
    if (a.esq < c.dir - 1 && c.esq < a.dir - 1) cobre.push(a.nome + ' × ' + c.nome);
  }
  const rr = r.getBoundingClientRect();
  const fora = caixas.filter(c => c.dir > rr.right + 1 || c.base > rr.bottom + 1 || c.topo < rr.top - 1).map(c => c.nome);
  const can = D.querySelector('.barra-andamento-cancelar'), est = D.getElementById('estado-servidor');
  let cruza = false;
  if (can && est && est.offsetParent) {
    const a = can.getBoundingClientRect(), b = est.getBoundingClientRect();
    cruza = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  }
  return JSON.stringify({ cobre, fora, cruza, cancelar: !!(can && can.offsetParent), estado_visivel: !!(est && est.offsetParent),
                          estado_linhas: est ? Math.round(est.getBoundingClientRect().height / 12) : 0, caixas });
})(%s)"""

try:
    for _ in range(60):
        try: _json(f"http://localhost:{PORTA}/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")

    def esperar(cond, limite=60.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                if aba.avaliar(f"!!({cond})"): return True
            except Exception:
                pass
            aba.drenar(0.3)
        return False

    def conferir(rotulo, D, W):
        aba.avaliar(POR_BARRA % f"{D}, {W}")
        esperar(f"{D}.querySelector('.rodape .barra-andamento')", 10)
        aba.drenar(0.5)
        r = json.loads(aba.avaliar(MEDIR % D))
        ok(r["cancelar"], f"{rotulo} a barra está no rodapé com o Cancelar")
        ok(not r["cobre"] and not r["fora"], f"{rotulo} nada se cobre no rodapé (cobre: {r['cobre']}, fora: {r['fora']})")
        ok(not r["cruza"], f"{rotulo} o Cancelar não cruza o \"malhas: …\"")
        if r["cobre"] or r["fora"] or r["cruza"]: print("       caixas:", r["caixas"])
        aba.avaliar(f"{W}.__pararBarra(false), 1")
        aba.drenar(0.6)
        r = json.loads(aba.avaliar(MEDIR % D))
        ok(r["estado_visivel"] and r["estado_linhas"] <= 1, f"{rotulo} sem a barra, o \"malhas: …\" de volta, numa linha ({r['estado_linhas']})")

    # --- A. o editor sozinho, na largura do quadro 3D
    for largura in (800, 640):
        aba.cmd("Emulation.setDeviceMetricsOverride", width=largura, height=900, deviceScaleFactor=1, mobile=False)
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto=obra-rodape", limite=90)
        ok(esperar("window.editor && editor.documento && editor.documento.entidades.size === 1 && document.body.dataset.pronto === '1' && window.metalicaProgresso", 90),
           f"[A {largura}px] o editor abriu")
        conferir(f"[A {largura}px]", "document", "window")
    # --- B. a tela dividida de verdade
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=obra-rodape&vista=ambos", limite=90)
    F = "document.getElementById('f3d')"
    ok(esperar(f"{F} && {F}.contentWindow.editor && {F}.contentWindow.editor.documento && {F}.contentWindow.document.body.dataset.pronto === '1' && {F}.contentWindow.metalicaProgresso", 120),
       "[B] a tela dividida abriu com o 3D")
    larg = aba.avaliar(f"{F}.getBoundingClientRect().width")
    print(f"     quadro 3D: {larg:.0f} px")
    conferir("[B dividida]", f"{F}.contentDocument", f"{F}.contentWindow")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    print("\nFALHAS: %d" % len(falhas))
    for f_ in falhas: print("  -", f_)
    srv.terminate(); nav.terminate()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)
sys.exit(1 if falhas else 0)
