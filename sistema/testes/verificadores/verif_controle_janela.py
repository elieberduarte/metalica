# -*- coding: utf-8 -*-
"""A janela Apontar do Controle de produção não pula (14/11/2026, GESTÃO · CHATS N.10 pela medição do CONTROLE N.2).

Medido na cópia do Posto (Projeto/ANALISES/Controle-de-producao/_interno/medir_janela.py, 09h48): a janela abria centrada e
sem largura fixa; 12–66 ms depois chegava a lista dos apontamentos do item (/api/producao/historico), a janela alargava e se
recentrava, e a opção Pintura andava 129–148 px — um clique dado nesse meio cairia fora dela (a mesma família da "barra do modo
ver que pula", EDITOR 3D 623bad8). Aqui, com eventos de verdade, em 5 itens com apontamentos:
  1. a posição da opção Pintura (e do botão Apontar) a cada quadro, por 2,5 s depois do clique que abre a janela, não muda
     mais de 2 px — e a lista dos apontamentos chegou nesse tempo (senão a conta não prova nada);
  2. sem erro no console.
Servidor de teste numa pasta temporária; porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_producao_controle import _lista, NOMES
from producao import controle as C

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_controle_janela_")
OBRA = os.path.join(DADOS, "obra-janela")
os.makedirs(os.path.join(OBRA, "detalhamento"))
LISTA = _lista()
json.dump({"formato": 1, "nome": "OBRA DA JANELA", "tipo": "ifc", "alterado": "2026-11-14T10:00:00"},
          open(os.path.join(OBRA, "projeto.json"), "w", encoding="utf-8"))
json.dump(LISTA, open(os.path.join(OBRA, "detalhamento", "lista-de-materiais.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(NOMES, open(os.path.join(OBRA, "detalhamento", "nomes.json"), "w", encoding="utf-8"), ensure_ascii=False)
# 5 itens com apontamento na produção (a lista dos apontamentos chega com linhas; a Pintura fica liberada)
ITENS = [("T38-1", 1, ""), ("T38-2", 1, "refeita a solda do banzo depois da inspeção do encarregado"), ("T74", 1, ""),
         ("MT71-1", 1, ""), ("T.C.1", 10, "")]
for it, q, obs in ITENS:
    C.apontar(OBRA, LISTA, it, "producao", q, "Fernando (teste)", obs=obs, nomes=NOMES)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


def clicar(aba, seletor):
    r = aba.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor, ensure_ascii=False)}); if (!e) return null;"
                    f" e.scrollIntoView({{block: 'center'}}); const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }})()")
    if not r: return False
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=r[0], y=r[1], button="left", clickCount=1)
    return True


# grava, a cada quadro, a posição da opção Pintura e do botão Apontar da janela aberta, e se a lista dos apontamentos já chegou
GRAVAR = """(() => {
  window._pos = []; const t0 = performance.now();
  const passo = () => {
    const d = document.querySelector('#ctl-dialogo[open]');
    const r = d && d.querySelector('input[name=ctl-etapa][value=pintura]'), b = d && d.querySelector('#ctl-confirmar');
    if (r && b) { const a = r.getBoundingClientRect(), c = b.getBoundingClientRect();
      window._pos.push([Math.round(performance.now() - t0), a.left, a.top, c.left, c.top, !!d.querySelector('.ctl-historico table')]); }
    if (performance.now() - t0 < 2500) requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
})()"""

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_controle_janela_")
nav = subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/controle-producao?projeto=obra-janela", limite=40)
    ok(esperar(aba, "!!document.querySelector('#ctl-cartoes') && !!document.querySelector('#controle-corpo button[data-item]')", 40),
       "o Controle abre com a lista")

    for it, _, _ in ITENS:
        aba.avaliar("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
        aba.drenar(0.3)
        aba.avaliar(GRAVAR)
        clicar(aba, f"#controle-corpo button[data-item={json.dumps(it, ensure_ascii=False)}]")
        aba.drenar(2.7)
        pos = aba.avaliar("window._pos") or []
        if not pos:
            ok(False, f"{it}: a janela Apontar abriu")
            continue
        chegou = next((p[0] for p in pos if p[5]), None)
        mov = max(max(abs(p[1] - pos[0][1]), abs(p[2] - pos[0][2]), abs(p[3] - pos[0][3]), abs(p[4] - pos[0][4])) for p in pos)
        ok(chegou is not None, f"{it}: a lista dos apontamentos chegou com a janela aberta ({chegou} ms)")
        ok(mov <= 2, f"{it}: a opção Pintura e o botão Apontar não mudam de lugar quando a lista chega (andaram {mov:.0f} px)")
    aba.avaliar("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    for p in (nav, srv):
        try: subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        except Exception: pass
    shutil.rmtree(perfil, ignore_errors=True)
    shutil.rmtree(DADOS, ignore_errors=True)

print("\ntudo ok" if not falhas else f"\n{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
