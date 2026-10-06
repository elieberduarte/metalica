# -*- coding: utf-8 -*-
"""Editor 3D, painel de camadas (06/10): a camada vazia se exclui (× na linha, Ctrl+Z traz de volta), a camada
com peças não (aviso para movê-las antes); na legenda do "Colorir por" (perfil) o olho de cada grupo esconde as
peças dele só na vista — o modelo gravado não muda — e "Mostrar todas" traz de volta. Porta livre."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_camgr_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)
json.dump({"nome": "Obra das camadas", "tipo": "ifc"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
m = _modelo()
m["camadas"]["Vazia"] = {"nome": "Vazia", "cor": "#ff8800", "visivel": True}
json.dump(m, open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
falhas = []


def ok(c, msg):
    print(("  ok    " if c else "  FALHA ") + msg, flush=True)
    if not c: falhas.append(msg)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_camgr_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=obra", limite=60)
    ok(esperar(aba, "window.editor && editor.documento && editor.documento.entidades.size > 60", 60), "o editor abre o projeto")
    E = "editor"
    linha = "[...document.querySelectorAll('#painel-camadas .lista-linhas .linha')].find(l => l.querySelector('.nome') && l.querySelector('.nome').textContent === '%s')"
    ok(esperar(aba, "!!(" + linha % "Vazia" + ")", 10), "a camada vazia está no painel")
    aba.avaliar("(" + linha % "Vazia" + ").querySelector('.excluir-camada').click(); 1")
    ok(esperar(aba, "!editor.documento.camadas.has('Vazia') && !(" + linha % "Vazia" + ")", 10), "o × exclui a camada vazia")
    aba.avaliar("editor.desfazer(); 1")
    ok(esperar(aba, "editor.documento.camadas.has('Vazia')", 10), "Ctrl+Z traz a camada de volta")
    aba.avaliar("(" + linha % "Vigas" + ").querySelector('.excluir-camada').click(); 1")
    ok(aba.avaliar("editor.documento.camadas.has('Vigas')"), "a camada com peças não se exclui (aviso para movê-las antes)")

    # Colorir por perfil: o olho de um grupo esconde as peças dele só na vista
    aba.avaliar("(() => { const s = document.querySelector('#painel-camadas .cor-por select'); s.value = 'perfil'; s.dispatchEvent(new Event('change')); return 1; })()")
    ok(esperar(aba, "document.querySelectorAll('#painel-camadas .legenda-grupos .linha button.alternador').length >= 2", 10), "a legenda por perfil tem o olho de cada grupo")
    nome = aba.avaliar("(() => { const l = [...document.querySelectorAll('#painel-camadas .legenda-grupos .linha')].find(x => x.querySelector('.nome').textContent === 'PL'); l.querySelector('button.alternador').click(); return 'PL'; })()")
    ok(esperar(aba, "editor.documento.ocultosNaVista && editor.documento.ocultosNaVista.size === 5", 10), "o olho do perfil PL esconde as 5 peças dele")
    ok(aba.avaliar("!editor.documento.aparece(editor.documento.entidades.get('c0')) && editor.documento.aparece(editor.documento.entidades.get('b1'))"),
       "as do grupo somem e as outras ficam")
    ok(aba.avaliar("(() => { const o = editor.cena.objetos.get('c0'); return !o || o.visible === false; })()"), "e somem do desenho 3D")
    ok(aba.avaliar("editor.documento.entidades.get('c0').visivel !== false && !JSON.stringify(editor.documento.paraJSON()).includes('ocultosNaVista')"),
       "só na vista: o modelo gravado não muda")
    aba.avaliar("[...document.querySelectorAll('#painel-camadas .acoes-painel button')].find(b => b.textContent === 'Mostrar todas').click(); 1")
    ok(esperar(aba, "!editor.documento.ocultosNaVista && editor.documento.aparece(editor.documento.entidades.get('c0'))", 10), "Mostrar todas traz o grupo de volta")
    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
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
