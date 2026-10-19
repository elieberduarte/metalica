# -*- coding: utf-8 -*-
"""Regressão (19/10, anexo do Mercado Hermes): "não consigo selecionar uma tesoura inteira, ele seleciona todas, e com o alt
pressionado ele seleciona apenas um trechinho". O gerador do Mercado grava a peça de origem só com o tipo ("T.7") e a
instância no conjunto ("T.7#2"); o bloco era pela origem, então o clique pegava as quatro tesouras iguais. Aqui, no navegador
de verdade: duas tesouras iguais assim e uma terceira no jeito dos outros geradores ("TESOURA 1#3"); o clique numa barra
pega só a tesoura dela (as 7 barras), o Alt+clique pega a barra só; sem erros no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_blinst_")
PASTA = os.path.join(DADOS, "blinst")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Blocos", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
U = "U 100×50×3,00 (FF)"


def tesoura(y, peca, conjunto):
    at = {"origem": {"peca": peca}, "conjunto": conjunto}
    pts = [((0, y, 0), (6000, y, 0), "banzo"), ((0, y, 1000), (6000, y, 1000), "banzo"), ((0, y, 0), (0, y, 1000), "montante"),
           ((3000, y, 0), (3000, y, 1000), "montante"), ((6000, y, 0), (6000, y, 1000), "montante"),
           ((0, y, 1000), (3000, y, 0), "diagonal"), ((6000, y, 1000), (3000, y, 0), "diagonal")]
    out = []
    for a, b, papel in pts:
        out.append(doc.add(Barra(nome=papel, inicio=a, fim=b, perfil=U, papel=papel, camada="Tesouras", atributos=json.loads(json.dumps(at)))))
    return out


t1 = tesoura(0, "T.7", "T.7#1")
t2 = tesoura(4000, "T.7", "T.7#2")
t3 = tesoura(8000, "TESOURA 1#3", "")
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_blinst_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=blinst", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 21)"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    aba.console.clear()

    def clicar_na_barra(bid, mod=0):
        """enquadra a barra (ela fica no meio da tela) e clica no meio do canvas, com o evento de verdade"""
        aba.avaliar("editor.selecao.limpar && editor.selecao.limpar(); 1")
        for _ in range(3):
            aba.avaliar(f"editor.camera.zoomSelecao(['{bid}']); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); 1")
            aba.drenar(0.5)
        aba.avaliar("editor.selecao.limpar && editor.selecao.limpar(); 1")
        x, y = json.loads(aba.avaliar("""JSON.stringify((() => { const c = editor.el.canvas || document.querySelector('canvas');
            const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"""))
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, modifiers=mod)
        aba.drenar(0.2)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, modifiers=mod)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, modifiers=mod)
        aba.drenar(0.8)
        return json.loads(aba.avaliar("JSON.stringify(editor.selecao.entidades.map(e => e.id))") or "[]")

    ids1, ids2, ids3 = {b.id for b in t1}, {b.id for b in t2}, {b.id for b in t3}
    sel = set(clicar_na_barra(t1[1].id))                         # o banzo de cima da T.7#1
    ok(sel == ids1, f"o clique na T.7#1 pega só ela ({len(sel)} barras; da T.7#2: {len(sel & ids2)})")
    sel = set(clicar_na_barra(t2[1].id))
    ok(sel == ids2, f"o clique na T.7#2 pega só ela ({len(sel)} barras; da T.7#1: {len(sel & ids1)})")
    sel = set(clicar_na_barra(t3[1].id))
    ok(sel == ids3, f"a tesoura dos outros geradores continua um bloco ({len(sel)} barras)")
    sel = set(clicar_na_barra(t1[1].id, mod=1))                  # Alt
    ok(sel == {t1[1].id}, f"Alt+clique pega a barra só ({len(sel)})")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
