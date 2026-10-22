# -*- coding: utf-8 -*-
"""O cartão da conferência no canto do modo desenvolvimento (web/versao.js). 22/10, a conferência da 0.9.1 cancelada
pelo botão: o cartão ficou parado na tela ("Conferência cancelada · nada publicado · parada em bateria das obras após
1…"), sem botão para fechar e sem sumir. Agora: rodando, o Cancelar (sem o ×); terminada, o × fecha na hora e o
cartão não volta para a mesma rodada (a rodada seguinte aparece de novo); a frase inteira, com a etapa em que parou.
A resposta do servidor é simulada no navegador (o fetch de /api/versao com dev e a conferência). Porta livre, nunca a
8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_conferencia_cartao_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
# window.__conf é o que o servidor responderia em "conferencia"; o verificador troca durante o teste
SIMULA = """(() => {
  window.__conf = { inicio: 1000, pct: 28, etapa: 'verificadores das telas', n_etapa: 2, etapas: 3, feito: 30, total: 141,
                    texto: 'verif_cad', resta_s: 4600, decorrido_s: 10000, fim: false, ok: null, parada: false,
                    cancelada: false, falhas: [] };
  const original = window.fetch.bind(window);
  window.fetch = (u, o) => {
    const url = typeof u === 'string' ? u : (u && u.url) || '';
    if (url.includes('/api/versao'))
      return original(u, o).then(r => r.json()).then(v => new Response(JSON.stringify(Object.assign(v,
        { dev: true, conferencia: window.__conf, ritmo: 'calmo' })), { headers: { 'Content-Type': 'application/json' } }));
    return original(u, o);
  };
})();"""
CANCELADA = {"inicio": 1000, "pct": 100.0, "etapa": "verificadores das telas", "n_etapa": 2, "etapas": 3, "feito": 30,
             "total": 141, "texto": "cancelada", "resta_s": 0, "decorrido_s": 10080, "fim": True, "ok": False,
             "parada": False, "cancelada": True, "falhas": ["testes automáticos", "verificadores das telas"]}


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.5)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


CARTAO = "document.getElementById('conferencia-dev')"
exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_conf_cartao_")
nav = subprocess.Popen([exe, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1300, height=820, deviceScaleFactor=1, mobile=False)
    aba.cmd("Page.addScriptToEvaluateOnNewDocument", source=SIMULA)
    aba.navegar(base + "/", limite=60)
    # rodando
    ok(esperar(aba, f"!!{CARTAO}"), "rodando: o cartão da conferência aparece")
    vis = aba.avaliar(f"(() => {{ const c = {CARTAO}; const f = c.querySelector('[data-fechar]'); "
                      "return [!c.querySelector('[data-cancelar]').hidden, !!f && !f.hidden]; })()") or [False, True]
    ok(vis == [True, False], f"rodando: o Cancelar à vista e sem o × ({vis})")
    # cancelada
    aba.avaliar("window.__conf = %s; 1" % json.dumps(CANCELADA))
    ok(esperar(aba, f"({CARTAO}.textContent || '').includes('Conferência cancelada')", 15), "cancelada: o cartão diz")
    l2 = aba.avaliar(f"{CARTAO}.querySelector('[data-l2]').textContent") or ""
    ok("parou em verificadores das telas (30 de 141)" in l2, f"cancelada: a etapa em que parou, com a contagem ({l2!r})")
    cabe = aba.avaliar(f"(() => {{ const e = {CARTAO}.querySelector('[data-l2]'); return e.scrollWidth <= e.clientWidth + 1; }})()")
    ok(cabe and "após 168 min" in l2, "cancelada: a frase inteira, sem cortar no \"após 1…\"")
    vis = aba.avaliar(f"(() => {{ const c = {CARTAO}; const f = c.querySelector('[data-fechar]'); "
                      "return [!c.querySelector('[data-cancelar]').hidden, !!f && !f.hidden]; })()") or [True, False]
    ok(vis == [False, True], f"terminada: sem o Cancelar e com o × para fechar ({vis})")
    foto(aba, "conferencia_cartao_1_cancelada.png")
    # o × fecha e o cartão não volta para a mesma rodada
    aba.avaliar(f"{CARTAO}.querySelector('[data-fechar]').click(); 1")
    ok(not aba.avaliar(f"!!{CARTAO}"), "o × fecha o cartão")
    aba.drenar(9)                                   # duas perguntas ao servidor (de 4 em 4 s no desenvolvimento)
    ok(not aba.avaliar(f"!!{CARTAO}"), "e ele não volta para a mesma rodada")
    # a rodada seguinte aparece
    aba.avaliar("window.__conf = Object.assign({}, window.__conf, { inicio: 2000, fim: false, cancelada: false, pct: 5, "
                "etapa: 'testes automáticos', n_etapa: 1, feito: null, total: null }); 1")
    ok(esperar(aba, f"!!{CARTAO}", 15), "a rodada seguinte aparece de novo")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
