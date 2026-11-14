# -*- coding: utf-8 -*-
"""O clique duplo não atravessa o diálogo (D09 do usuario-desastrado, 13/11: A) na lista, clique duplo em "Cancelar a
tarefa" abriu o projeto do cartão de baixo; B) no 3D, clique duplo em "Detalhar e abrir" começou uma seleção por janela).
Cliques de verdade (Input.dispatchMouseEvent, clickCount 1 e depois 2, no mesmo ponto):
  A. a tela Projetos: o diálogo do Cancelar da tarefa (progresso.pedirCancelar), clique duplo no "Continuar a tarefa":
     o diálogo fecha, a página continua a mesma e nada atrás recebe o 2º clique;
  B. o editor 3D: o diálogo do editor com "Detalhar e abrir", clique duplo no botão: fecha com "ok", nenhuma seleção
     nova, nenhuma janela de seleção começada, nada atrás recebe o 2º clique;
  C. o clique legítimo noutro ponto logo depois (100 ms) passa;
  D. sem erros no console.
Falha sem a correção. Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_clique_duplo_")
for nome in ("obra-a", "obra-b", "obra-c"):
    pasta = os.path.join(DADOS, nome)
    os.makedirs(pasta)
    v = [[0, 0, 0], [500, 0, 0], [500, 500, 0], [0, 500, 0], [0, 0, 3000], [500, 0, 3000], [500, 500, 3000], [0, 500, 3000]]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    json.dump({"nome": nome, "unidade": "mm", "camadas": {"Layer0": {"nome": "Layer0", "cor": "#8a94a6", "visivel": True, "bloqueada": False}},
               "materiais": {}, "entidades": [{"id": "P%d" % i, "tipo": "solido", "nome": "P%d" % i, "camada": "Layer0", "material": "",
                                              "vertices": [[x + i * 2000, y, z] for x, y, z in v], "faces": f, "arestas_vivas": [], "atributos": {}}
                                             for i in range(4)]},
              open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"formato": 1, "nome": nome, "tipo": "ifc", "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00"},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_clique_duplo_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# quem está atrás conta os cliques que recebe (na fase de bolha do body: o que o diálogo segura não chega)
CONTADOR = """(() => { window.__atras = 0; window.__atrasTipos = [];
  for (const t of ['pointerdown', 'mousedown', 'click', 'dblclick'])
    document.body.addEventListener(t, (ev) => { if (!ev.target.closest('dialog')) { window.__atras++; window.__atrasTipos.push(t); } });
  return 1; })()"""

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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=60):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                v = aba.avaliar(expr)
                if v: return v
            except Exception: pass
            aba.drenar(0.3)
        return None

    def centro(seletor):
        return aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return q.width ? [q.left + q.width / 2, q.top + q.height / 2] : null; }})()")

    def clique_duplo(x, y):
        """como o mouse de verdade: o 1º clique (clickCount 1) e o 2º (clickCount 2), ~120 ms depois, no mesmo ponto"""
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        for n in (1, 2):
            aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=n)
            aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=n)
            if n == 1: time.sleep(0.12)
        aba.drenar(0.6)

    # --- A. a tela Projetos: o Cancelar da tarefa
    aba.navegar(base + "/", limite=60)
    ok(bool(esperar("document.readyState === 'complete' && window.metalicaProgresso", 40)), "[A] a tela Projetos abriu")
    url0 = aba.avaliar("location.href")
    aba.avaliar(CONTADOR)
    aba.avaliar("window.__resp = 'esperando'; window.metalicaProgresso.pedirCancelar('obra-b', { rotulo: 'Detalhando' }).then(r => { window.__resp = r; }); 1")
    ok(bool(esperar("!!document.querySelector('dialog.dlg-cancelar-tarefa[open]')", 10)), "[A] o diálogo \"Cancelar a tarefa?\" abriu")
    c = centro("dialog.dlg-cancelar-tarefa .bts button:not(.perigo)")
    clique_duplo(*c)
    ok(aba.avaliar("!document.querySelector('dialog.dlg-cancelar-tarefa')") is True, "[A] o diálogo fechou no 1º clique")
    ok(aba.avaliar("window.__resp") is None, "[A] \"Continuar a tarefa\": nada foi cancelado")
    atras = aba.avaliar("[window.__atras, window.__atrasTipos]")
    ok(atras[0] == 0, f"[A] o 2º clique não chegou atrás ({atras})")
    ok(aba.avaliar("location.href") == url0, "[A] a página continua a mesma (nenhum projeto aberto)")
    # --- C. o clique legítimo noutro ponto, logo depois, passa
    aba.avaliar("window.__atras = 0; window.__atrasTipos = []; 1")
    aba.avaliar("window.metalicaProgresso.pedirCancelar('obra-b', {}); 1")
    esperar("!!document.querySelector('dialog.dlg-cancelar-tarefa[open]')", 10)
    c = centro("dialog.dlg-cancelar-tarefa .bts button:not(.perigo)")
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=c[0], y=c[1], button="left", clickCount=1)
    time.sleep(0.1)
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=20, y=880, button="left", clickCount=1)
    aba.drenar(0.4)
    ok(aba.avaliar("window.__atras") >= 1, "[C] o clique noutro ponto, 100 ms depois, passa")

    # --- B. o editor 3D: "Detalhar e abrir"
    aba.navegar(base + "/editor?projeto=obra-a", limite=90)
    ok(bool(esperar("window.editor && editor.documento && editor.documento.entidades.size === 4 && document.body.dataset.pronto === '1'", 90)),
       "[B] o editor abriu")
    aba.avaliar("editor.camera.zoomExtensao && editor.camera.zoomExtensao(); editor.selecao.limpar(); 1")
    aba.avaliar(CONTADOR)
    aba.avaliar("window.__resp = 'esperando'; editor.dialogo({ titulo: 'Detalhar peças e conjuntos', corpo: null, ok: 'Detalhar e abrir' }).then(r => { window.__resp = r; }); 1")
    ok(bool(esperar("document.querySelector('#dialogo').open", 10)), "[B] o diálogo do Detalhar abriu")
    c = centro("#dialogo-ok")
    clique_duplo(*c)
    ok(aba.avaliar("window.__resp") == "ok", f"[B] fechou com \"Detalhar e abrir\" ({aba.avaliar('window.__resp')!r})")
    r = json.loads(aba.avaliar("JSON.stringify({ sel: editor.selecao.ids.size, baixo: !!editor._baixo, atras: window.__atras, tipos: window.__atrasTipos })"))
    ok(r["sel"] == 0 and not r["baixo"], f"[B] nenhuma seleção nova nem janela começada no 3D ({r})")
    ok(r["atras"] == 0, f"[B] o 2º clique não chegou ao 3D atrás ({r})")

    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"[D] sem erros no console: {erros[:3]}")
finally:
    print("\nFALHAS: %d" % len(falhas))
    for f_ in falhas: print("  -", f_)
    srv.terminate(); nav.terminate()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)
sys.exit(1 if falhas else 0)
