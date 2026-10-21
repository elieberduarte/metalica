# -*- coding: utf-8 -*-
"""O cartão do projeto que está sendo atualizado (21/10/2026, web/inicio.js): com atualizando.json gravado por outro
processo, a tela inicial mostra "Atualizando…" com a etapa e a barra, o cartão e o botão Abrir não abrem o projeto (um
recado explica), o servidor recusa o POST (409) e, quando a marca some, o cartão volta ao normal sozinho."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
import platform

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_atualizando_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Obra em atualização", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"formato": 1, "nome": "Obra livre", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None},
          open(os.path.join(os.makedirs(os.path.join(DADOS, "livre")) or os.path.join(DADOS, "livre"), "projeto.json"), "w", encoding="utf-8"), ensure_ascii=False)
MARCA = os.path.join(PASTA, "atualizando.json")


def marcar(etapa, fracao=None):
    # este verificador é "o outro processo": vivo, desta máquina, e não é o servidor
    json.dump({"etapa": etapa, "fracao": fracao, "quando": time.time(), "inicio": time.time() - 12, "quem": "script",
               "pid": os.getpid(), "maquina": platform.node()}, open(MARCA, "w", encoding="utf-8"))


marcar("montando as treliças…", 0.4)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_atu_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "document.querySelectorAll('.cartao').length === 2", 30), "a tela inicial lista os 2 projetos")

    # 1. o cartão em atualização: classe, "Atualizando…", a etapa, a barra com a fração, o botão Abrir desligado
    sel = ".cartao[data-slug='obra']"
    ok(aba.avaliar(f"document.querySelector(\"{sel}\").classList.contains('atualizando')"), "o cartão tem a classe atualizando")
    txt = aba.avaliar(f"document.querySelector(\"{sel} .cartao-atualizando\")?.textContent || ''")
    ok("Atualizando…" in txt and "montando as treliças" in txt, f"o cartão diz Atualizando… com a etapa ({txt!r})")
    larg = aba.avaliar(f"document.querySelector(\"{sel} .cartao-atualizando .cheio\")?.style.width")
    ok(larg == "40%", f"a barra mostra a fração do servidor ({larg})")
    btn = aba.avaliar(f"(() => {{ const b = document.querySelector(\"{sel} .cartao-botoes .principal\"); return [b.disabled, b.textContent]; }})()")
    ok(btn == [True, "Atualizando…"], f"o botão Abrir vira 'Atualizando…' desligado ({btn})")
    ok(not aba.avaliar("document.querySelector(\".cartao[data-slug='livre']\").classList.contains('atualizando')"), "o outro projeto segue normal")

    # 2. clicar no cartão (e Enter) não abre: a página continua a inicial, com o recado
    aba.avaliar(f"document.querySelector(\"{sel}\").click(); 1")
    aba.drenar(1.0)
    ok(aba.avaliar("location.pathname") == "/", "o clique no cartão não sai da tela inicial")
    rec = aba.avaliar("[...document.querySelectorAll('#bandeja .recado')].map(r => r.textContent).join(' | ')")
    ok("sendo atualizado" in rec and "espere terminar" in rec, f"o recado explica ({rec[:80]!r})")
    aba.avaliar(f"document.querySelector(\"{sel}\").dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }})); 1")
    aba.drenar(0.5)
    ok(aba.avaliar("location.pathname") == "/", "Enter no cartão também não abre")

    # 3. o servidor recusa o POST de quem não é o processo que atualiza
    st = aba.avaliar("(async () => { const r = await fetch('/api/projetos/obra/renomear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{\"nome\":\"x\"}' }); return [r.status, (await r.json()).erro || '']; })()")
    ok(st and st[0] == 409 and "sendo atualizado" in st[1], f"POST no projeto em atualização: 409 com o motivo ({st})")
    pr = _json(base + "/api/projetos/obra/progresso")
    ok(pr.get("etapa") == "montando as treliças…" and pr.get("externo") and pr.get("fracao") == 0.4, f"GET progresso mostra a etapa do outro processo ({pr})")

    # 4. a etapa muda no servidor → o cartão acompanha
    marcar("gravando o modelo…", 0.9)
    ok(esperar(aba, f"(document.querySelector(\"{sel} .cartao-atualizando .etapa\")?.textContent || '') === 'gravando o modelo…'", 8), "a etapa nova aparece no cartão sem recarregar")
    ok(aba.avaliar(f"document.querySelector(\"{sel} .cartao-atualizando .cheio\")?.style.width") == "90%", "a barra anda com a fração nova")

    # 5. a marca some → o cartão volta ao normal sozinho e abre
    os.remove(MARCA)
    ok(esperar(aba, f"!document.querySelector(\"{sel}\").classList.contains('atualizando')", 10), "sem a marca, o cartão volta ao normal sozinho")
    btn = aba.avaliar(f"(() => {{ const b = document.querySelector(\"{sel} .cartao-botoes .principal\"); return [b.disabled, b.textContent]; }})()")
    ok(btn == [False, "Abrir"], f"o botão Abrir volta ({btn})")
    st = aba.avaliar("(async () => { const r = await fetch('/api/projetos/obra/renomear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{\"nome\":\"Obra em atualização\"}' }); return r.status; })()")
    ok(st == 200, f"o POST volta a ser aceito ({st})")
    aba.avaliar(f"document.querySelector(\"{sel}\").click(); 1")
    ok(esperar(aba, "location.pathname !== '/'", 15), f"o clique abre o projeto ({aba.avaliar('location.pathname')})")

    # o 409 do passo 3 é o esperado (o navegador registra toda resposta de erro no console)
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "409" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    import shutil
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
