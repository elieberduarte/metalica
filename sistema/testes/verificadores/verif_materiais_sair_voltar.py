# -*- coding: utf-8 -*-
"""Lista de materiais: "Atualizar pelo modelo 3D", sair da tela e voltar (SESI, 27/10: "cliquei para atualizar a lista
de materiais pelo 3D, porém se saio dessa tela ele interrompe a atualização"). O servidor seguia até o fim, mas quem
voltava via a lista antiga com "o modelo 3D foi alterado…", sem nada dizer que ela estava sendo refeita.

Agora: o clique diz que pode sair; ao voltar no meio, a tela diz desde quando está sendo atualizada, mostra a barra,
desliga o botão (sem segunda conta) e, quando acaba, mostra a lista nova sozinha. Modelo de verdade (compressores-ar,
o levantamento leva uns segundos)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_mat_voltar_")
dst = os.path.join(DADOS, "sala")
os.makedirs(os.path.join(dst, "detalhamento"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(dst, "modelo.json"))
json.dump({"formato": 1, "nome": "Sala", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "", "criado": "2026-10-27T00:00:00",
           "alterado": "2026-10-27T00:00:00", "dados": None}, open(os.path.join(dst, "projeto.json"), "w", encoding="utf-8"))
# a lista de antes (de antes da mudança do modelo): a tela mostra "o modelo 3D foi alterado…"
json.dump({"gerado": "2026-10-27 15:13", "itens": []}, open(os.path.join(dst, "detalhamento", "lista-de-materiais.json"), "w", encoding="utf-8"))
os.utime(os.path.join(dst, "detalhamento", "lista-de-materiais.json"), (time.time() - 7200, time.time() - 7200))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


AVISO = "(document.querySelector('#aviso')?.textContent || '')"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mat_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/materiais?projeto=sala", limite=60)
    ok(esperar(aba, f"/foi alterado/.test({AVISO})", 30), "a lista de antes, com o aviso do modelo alterado")
    # o clique de verdade no botão
    r = aba.avaliar("(() => { const b = document.querySelector('#btn-recalcular'); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; })()")
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    ok(esperar(aba, f"/pode sair desta tela/.test({AVISO})", 5), f"o clique diz que pode sair ({aba.avaliar(AVISO)[:90]!r})")
    aba.drenar(1.5)
    # sai da tela no meio (a tela inicial) e volta
    aba.navegar(f"{base}/", limite=60)
    aba.drenar(1.0)
    aba.navegar(f"{base}/materiais?projeto=sala", limite=60)
    em = esperar(aba, f"/sendo atualizada pelo modelo 3D \\(começou às \\d\\d:\\d\\d\\)/.test({AVISO})", 20)
    ok(em, f"de volta no meio: a tela diz que está sendo atualizada e desde quando ({aba.avaliar(AVISO)[:120]!r})")
    ok(aba.avaliar("document.querySelector('#btn-recalcular').disabled"), "o botão fica desligado (sem segunda conta)")
    ok(esperar(aba, "!!document.querySelector('.barra-andamento')", 10), "com a barra de andamento")
    fim = esperar(aba, f"/Lista atualizada pelo modelo 3D/.test({AVISO})", 180)
    ok(fim, f"quando acaba, a lista nova aparece sozinha ({aba.avaliar(AVISO)[:120]!r})")
    ok(not aba.avaliar("document.querySelector('#btn-recalcular').disabled"), "e o botão volta")
    g = _json(base + "/api/projetos/sala/materiais")
    ok(g.get("gerado") != "2026-10-27 15:13" and not g.get("atualizando"), f"a lista gravada é a nova ({g.get('gerado')})")
    ok(esperar(aba, "!document.querySelector('.barra-andamento')", 10), "a barra sai")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
