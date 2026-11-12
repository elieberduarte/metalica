# -*- coding: utf-8 -*-
"""Análise estrutural instável, no navegador de verdade (12/11/2026, Cobertura Filipin — usuário: "estou clicando para
trocar a barra e recalcular e não acontece nada"). A estrutura saía instável (duas linhas de travamento soltas no ar e a
marquise presa só por terças rotuladas) e a tela mostrava o ranking com tensões de matriz singular, o "trocar" recalculava
o mesmo mecanismo e nada mudava à vista. Confere, num pórtico rotulado (mecanismo) com uma viga solta longe de tudo:
- o aviso no alto diz que os números não valem e tem o "Mostrar onde", que leva a câmera até o mecanismo;
- as barras do mecanismo e a solta saem em vermelho (a linha grossa);
- o ranking não tem "trocar" (só o aviso);
- Calcular dá o recado de que calculou (e que segue instável);
- o painel da esquerda não rola para o lado; nenhum erro no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_analitico import barra
from nucleo3d.modelo import Documento
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PAR = {"base": "rotulada", "viga_pilar": "rotulada"}
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_instavel_")
PASTA = os.path.join(DADOS, "instavel")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Instável", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00", "dados": None, "analise_parametros": PAR},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
doc = Documento()
for x in (0.0, 6000.0):
    doc.add(barra((x, 0.0, 0.0), (x, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
doc.add(barra((0.0, 0.0, 3000.0), (6000.0, 0.0, 3000.0), "viga", perfil="W 200×19,3"))
doc.add(barra((20000.0, 0.0, 3000.0), (24000.0, 0.0, 3000.0), "viga", perfil="W 200×19,3"))     # solta no ar
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
from nucleo3d import analise_estrutural as AE                   # a análise gravada (a tela abre com ela, como na Filipin)
json.dump(AE.calcular(doc, PAR), open(os.path.join(PASTA, "analise_estrutural.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_instavel_")
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

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def esperar(cond, limite=60.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if js(cond): return True
            except Exception:
                pass
            aba.drenar(0.3)
        return False
    def clicar(seletor):
        r = jsj(f"const e = document.querySelector({json.dumps(seletor)}); if (!e) return null; e.scrollIntoView({{block: 'center'}}); "
                "const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True

    aba.cmd("Page.navigate", url=f"http://localhost:{PORTA}/analise-estrutural?projeto=instavel")
    ok(esperar("!!document.querySelector('#btn-calcular')"), "a tela da análise abriu")
    ok(esperar("window.ae && window.ae.D && !window.ae.D.vazio && !!window.ae.D.instavel"), "abriu a análise gravada: instável")
    D = jsj("const D = window.ae.D; return {mec: D.mecanismo, soltas: D.soltas, n: D.barras.length};")
    ok(D and len(D["mec"]) == 3, f"o motor aponta as 3 barras do pórtico como mecanismo ({D and D['mec']})")
    ok(D and len(D["soltas"]) == 1, f"e a viga longe de tudo como solta ({D and D['soltas']})")
    txt = js("document.querySelector('#instavel').textContent")
    ok("não valem" in (txt or "") and "Mostrar onde" in (txt or ""), f"o aviso no alto diz que os números não valem e tem o Mostrar onde ({(txt or '')[:120]})")
    # as barras em vermelho: a linha grossa (largura 5) com as 4 barras (3 do mecanismo + a solta)
    n_verm = jsj("""return window.ae.grupo.children.filter(o => o.material && o.material.linewidth === 5)
                    .map(o => o.geometry.attributes.instanceStart.count);""")
    ok(n_verm and sum(n_verm) == 4, f"as 3 barras do mecanismo e a solta em vermelho ({n_verm})")
    ok(not js("[...document.querySelectorAll('#ranking button')].some(b => b.textContent.trim() === 'trocar')"),
       "o ranking não oferece 'trocar' com a estrutura instável")
    ok("instável" in (js("document.querySelector('#ranking').textContent") or ""), "o ranking diz que a estrutura está instável")
    alvo0 = jsj("const t = window.ae.camera.position; return [t.x, t.y, t.z];")
    ok(clicar("#instavel button"), "clicou em Mostrar onde")
    aba.drenar(0.5)
    alvo1 = jsj("const t = window.ae.camera.position; return [t.x, t.y, t.z];")
    ok(alvo0 != alvo1, "a câmera foi até o mecanismo")
    larg = jsj("const p = document.querySelector('#painel'); return [p.scrollWidth, p.clientWidth];")
    ok(larg and larg[0] <= larg[1] + 1, f"o painel da esquerda não rola para o lado ({larg})")
    ok(clicar("#btn-calcular"), "clicou em Calcular (com as premissas da tela)")
    ok(esperar("[...document.querySelectorAll('body > .erro, body > .aviso')].some(e => /Calculado de novo/.test(e.textContent))", 60),
       "o recado de que calculou aparece")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
print("\n%s" % ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
