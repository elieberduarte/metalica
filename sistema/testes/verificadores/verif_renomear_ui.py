# -*- coding: utf-8 -*-
"""Renomear o projeto não perde o que a tela guarda dele (21/10, o usuário, Mercado Conceito → Mercado Super Maria Luiza:
"perde a ref. de todas as layers que estavam ocultas"): a pasta troca de nome, e as camadas ocultas do modo ver
(ver3d:<projeto>), a vista e as cores do editor (vista3d:), os grupos recolhidos e a duração das tarefas iam pelo nome
antigo. Pelo cartão da tela inicial, com o Renomear de verdade; o projeto de nome parecido (mercado-conceito-2) fica como
está. Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_renomear_")
for slug, nome, antes in (("mercado-conceito", "MERCADO CONCEITO", []), ("mercado-conceito-2", "MERCADO CONCEITO 2", []),
                          # renomeado antes da correção (ou noutro navegador): o nome antigo gravado no projeto
                          ("galpao-novo", "GALPÃO NOVO", ["galpao-antigo"])):
    os.makedirs(os.path.join(DADOS, slug))
    json.dump({"nome": nome, "tipo": "ifc", "alterado": "2026-10-21T09:00:00", "slugs_anteriores": antes},
              open(os.path.join(DADOS, slug, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
GUARDADO = {
    "ver3d:mercado-conceito": json.dumps({"camadas": {"Telhas": False, "Concreto": False}}),
    "vista3d:mercado-conceito": json.dumps({"ids_ocultos": ["a1", "b2"]}),
    "camadas-recolhidas:mercado-conceito": json.dumps(["Pré-moldado"]),
    "metalica.duracao.mercado-conceito|POST /api/projetos/x/detalhar": "42",
    "ver3d:mercado-conceito-2": json.dumps({"camadas": {"Outra": False}}),
    "ver3d:galpao-antigo": json.dumps({"camadas": {"Telhas": False}}),
}


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_renomear_")
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
    aba.navegar(base + "/", limite=60)
    aba.avaliar("(() => { const g = %s; for (const k in g) localStorage.setItem(k, g[k]); return 1; })()" % json.dumps(GUARDADO))
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "[...document.querySelectorAll('button')].some(b => b.textContent === 'Renomear')"), "o cartão com o Renomear")
    ok(aba.avaliar("localStorage.getItem('ver3d:galpao-novo')") == GUARDADO["ver3d:galpao-antigo"]
       and aba.avaliar("localStorage.getItem('ver3d:galpao-antigo')") is None,
       "o projeto renomeado antes: ao abrir a tela inicial, o guardado pelo nome antigo foi para o atual")
    # o Renomear do cartão do MERCADO CONCEITO (não o do 2)
    aba.avaliar("""(() => {
      const cartoes = [...document.querySelectorAll('button')].filter(b => b.textContent === 'Renomear');
      const b = cartoes.find(x => { let c = x; while (c && !/MERCADO CONCEITO(?! 2)/.test(c.textContent || '')) c = c.parentElement;
                                   return c && !/MERCADO CONCEITO 2/.test(c.textContent); }) ||
                cartoes.find(x => (x.closest('[class*=cart]') || x.parentElement.parentElement).textContent.includes('MERCADO CONCEITO') &&
                                  !(x.closest('[class*=cart]') || x.parentElement.parentElement).textContent.includes('CONCEITO 2'));
      b.click(); return 1; })()""")
    ok(esperar(aba, "document.getElementById('dlg').open"), "o diálogo de renomear abre")
    aba.avaliar("(() => { const e = document.getElementById('dlg-nome'); e.value = 'Mercado Super Maria Luiza'; "
                "e.dispatchEvent(new Event('input', {bubbles: true})); document.getElementById('dlg-ok').click(); return 1; })()")
    ok(esperar(aba, "[...document.querySelectorAll('*')].some(e => e.children.length === 0 && e.textContent === 'Projeto renomeado')"),
       "renomeado")
    ok(os.path.isdir(os.path.join(DADOS, "mercado-super-maria-luiza")), "a pasta trocou de nome (o projeto mudou de endereço)")
    ls = aba.avaliar("(() => { const o = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); o[k] = localStorage.getItem(k); } return o; })()") or {}
    ok(ls.get("ver3d:mercado-super-maria-luiza") == GUARDADO["ver3d:mercado-conceito"], "as camadas ocultas do modo ver foram junto")
    ok(ls.get("vista3d:mercado-super-maria-luiza") == GUARDADO["vista3d:mercado-conceito"], "as peças ocultas e a vista do editor foram junto")
    ok(ls.get("camadas-recolhidas:mercado-super-maria-luiza") == GUARDADO["camadas-recolhidas:mercado-conceito"], "os grupos recolhidos foram junto")
    ok(ls.get("metalica.duracao.mercado-super-maria-luiza|POST /api/projetos/x/detalhar") == "42", "a duração das tarefas foi junto")
    ok(not any(k.endswith(":mercado-conceito") or ".mercado-conceito|" in k for k in ls), "nada ficou no nome antigo")
    ok(ls.get("ver3d:mercado-conceito-2") == GUARDADO["ver3d:mercado-conceito-2"], "o projeto de nome parecido ficou como estava")
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
