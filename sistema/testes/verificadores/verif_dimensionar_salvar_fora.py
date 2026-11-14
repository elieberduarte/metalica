# -*- coding: utf-8 -*-
"""D11 (agente usuario-desastrado, 13/11): o Salvar do Dimensionamento gravava vão 0 e comprimento negativo, dizendo
"Projeto salvo". No navegador de verdade: no projeto com vão 20 e comprimento 40, digita-se vão 0 e comprimento −40 e
clica-se em Salvar — o recado diz quais campos ficaram de fora (o rótulo, o valor digitado, a faixa aceita), os dois
campos continuam com o que foi digitado, marcados, e o projeto.json fica com 20 e 40. Corrigido o vão para 25 e o
comprimento para 50, o Salvar grava e diz "Projeto salvo". E a tela usa a faixa do cálculo (a inclinação 100, que a
tela aceitava e o cálculo não, fica marcada)."""
import json, os, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_dimsalvar_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(f"http://localhost:{PORTA}{rota}", data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))


def gravado(s):
    with open(os.path.join(DADOS, s, "projeto.json"), encoding="utf-8") as f:
        return json.load(f).get("dados") or {}


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_dimsalvar_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    s = post("/api/projetos", {"nome": "Galpão salvar", "tipo": "galpao",
                               "dados": {"nome": "Galpão salvar", "vao": 20, "comprimento": 40, "pe_direito": 6}})["slug"]
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    def esperar(cond, limite=30.0, passo=0.2):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(passo)
        return False

    def digitar(campo, valor):
        aba.avaliar("(() => { const c = document.getElementById('c-%s'); c.value = %s; c.dispatchEvent(new Event('input', {bubbles: true})); })()"
                    % (campo, json.dumps(str(valor))))

    def valor(campo):
        return aba.avaliar("document.getElementById('c-%s').value" % campo)

    def marcado(campo):
        return aba.avaliar("document.getElementById('c-%s').closest('.campo').classList.contains('erro')" % campo)

    recados = "[...document.querySelectorAll('#bandeja .recado')].map(r => r.textContent).join(' || ')"
    limpar = "document.querySelectorAll('#bandeja .recado').forEach(r => r.remove())"

    aba.navegar(f"http://localhost:{PORTA}/dimensionar?projeto={s}", limite=60)
    ok(esperar("!!document.getElementById('c-vao') && document.getElementById('c-vao').value === '20'", 30),
       "o formulário abriu com o vão 20 do projeto")

    print("A — vão 0 e comprimento −40: o Salvar não grava os dois e diz quais")
    digitar("vao", 0); digitar("comprimento", -40); digitar("pe_direito", "6,5")
    ok(marcado("vao") and marcado("comprimento") and not marcado("pe_direito"), "a tela marca os dois campos errados")
    aba.avaliar(limpar)
    aba.avaliar("document.getElementById('btn-salvar').click()")
    ok(esperar("/Salvo, menos 2 campos a corrigir/.test(" + recados + ")", 15), "o recado diz \"Salvo, menos 2 campos a corrigir\"")
    texto = aba.avaliar(recados) or ""
    print("       recado:", texto[:300])
    ok("Vão: valor 0 fora da faixa aceitável (5 a 60 m)" in texto, "com o rótulo, o valor digitado e a faixa do vão")
    ok("Comprimento: valor -40 fora da faixa aceitável (5 a 300 m)" in texto, "e do comprimento")
    ok("Projeto salvo" not in texto, "sem o \"Projeto salvo\" de antes")
    ok(valor("vao") == "0" and valor("comprimento") == "-40", "o que foi digitado continua nos campos")
    ok(marcado("vao") and marcado("comprimento"), "e os dois continuam marcados")
    ok("menos 2 campos" in (aba.avaliar("document.getElementById('estado-salvo').textContent") or ""), "a linha do \"gravado às…\" também diz")
    d = gravado(s)
    print("       projeto.json:", {k: d.get(k) for k in ("vao", "comprimento", "pe_direito")})
    ok(d.get("vao") == 20 and d.get("comprimento") == 40, "no projeto.json ficaram o vão 20 e o comprimento 40 de antes")
    ok(d.get("pe_direito") == 6.5, "e o pé-direito 6,5, válido, foi gravado")

    print("B — corrigidos, o Salvar grava")
    digitar("vao", 25); digitar("comprimento", 50)
    aba.avaliar(limpar)
    aba.avaliar("document.getElementById('btn-salvar').click()")
    ok(esperar("/Projeto salvo/.test(" + recados + ")", 15), "o recado volta a ser \"Projeto salvo\"")
    aba.drenar(0.5)
    d = gravado(s)
    ok(d.get("vao") == 25 and d.get("comprimento") == 50, "o projeto.json ficou com 25 e 50")
    ok("menos" not in (aba.avaliar("document.getElementById('estado-salvo').textContent") or ""), "a linha do \"gravado às…\" sem a ressalva")

    print("C — a tela usa a faixa do cálculo")
    digitar("inclinacao", 100)
    ok(marcado("inclinacao"), "inclinação 100 % fica marcada (a tela aceitava até 100; o cálculo, até 99)")
    digitar("inclinacao", 99)
    ok(not marcado("inclinacao"), "inclinação 99 % passa")
    digitar("flecha_terca", 800)
    ok(not marcado("flecha_terca"), "flecha da terça L/800 passa (a tela recusava acima de 600; o cálculo aceita até 1000)")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
