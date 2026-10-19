# -*- coding: utf-8 -*-
"""Reanalisar estrutura (19/10/2026), no navegador de verdade: o modelo antigo (a tesoura do test_reanalise longe da origem,
nas coordenadas do CD Bom Dia, com um toco solto, uma diagonal pendurada, uma passando do banzo, uma repetida…) abre no
modo ver; o botão ⟳ Reanalisar estrutura carrega o editor já com a prévia; clicar num achado seleciona a peça; Aplicar
tira as sobras numa entrada só de desfazer e grava o carimbo da versão das regras; o Ctrl+Z volta tudo; o menu Modelo da
barra única tem o item em destaque; nenhum erro no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_reanalise import _tesoura
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_reanalisar_")
PASTA = os.path.join(DADOS, "antigo")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Antigo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc, D = _tesoura(222913.0, 251770.0, 12000.0, False)
N0 = len(doc.entidades)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_reanalisar_")
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
    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if js(cond): return True
            except Exception:
                pass                                       # a página trocando (modo ver → editor)
            aba.drenar(0.3)
        return False
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    def clicar(seletor):
        """o clique de verdade (mouse do navegador) no meio do elemento"""
        r = jsj(f"const e = document.querySelector({json.dumps(seletor)}); if (!e) return null; e.scrollIntoView({{block: 'center'}}); "
                "const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True
    def n_pecas(): return jsj("return editor.documento.entidades.size;")

    # 0) a barra única (área de trabalho): Modelo › Reanalisar estrutura… em destaque, no alto
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=antigo", limite=60)
    ok(esperar("!!document.querySelector('.menu[data-nome=\"Modelo\"] .menu-botao')", 30), "a área de trabalho abriu com a barra única")
    clicar('.menu[data-nome="Modelo"] .menu-botao')
    ok(esperar("!!document.querySelector('.menu[data-nome=\"Modelo\"] .menu-lista button')", 10), "o menu Modelo abriu")
    primeiro = js("(document.querySelector('.menu[data-nome=\"Modelo\"] .menu-lista > button, .menu[data-nome=\"Modelo\"] .menu-lista > .item-sub') || {}).textContent || ''")
    ok(str(primeiro).startswith("Reanalisar estrutura"), f"o primeiro item do menu Modelo é o Reanalisar estrutura: {primeiro[:60]!r}")
    ok(js("!!document.querySelector('.menu[data-nome=\"Modelo\"] .menu-lista > button.destaque')"), "e está em destaque")
    erros("Barra única")

    # 1) o modo ver: o botão em destaque ao lado do Editar abre o editor já com a prévia
    aba.navegar(f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto=antigo", limite=60)
    ok(esperar("!!window.ver3dPronto", 60), "o modo ver abriu")
    ok(js("!!document.querySelector('#btn-reanalisar.forte')"), "o modo ver tem o botão ⟳ Reanalisar estrutura em destaque")
    aba.console.clear()
    clicar("#btn-reanalisar")
    ok(esperar(f"location.pathname === '/editor' && !!(window.editor && editor.documento && editor.documento.entidades.size >= {N0})", 60),
       "o botão carregou o editor com o modelo")
    ok(esperar("!!document.querySelector('.painel-reanalise .aplicar-reanalise')", 90), "a prévia abriu sozinha, com o botão Aplicar")
    ok(js("!new URL(location.href).searchParams.has('reanalisar')"), "o pedido sai da URL (F5 não reabre a prévia)")
    ok(n_pecas() == N0, "a prévia não mudou o modelo")
    resumo = jsj("return [...document.querySelectorAll('.painel-reanalise summary')].map(s => s.textContent.trim());")
    print("    prévia:", resumo)
    ok(any(s.startswith("Tocos de alma soltos (2)") for s in resumo), "os 2 tocos soltos (o bloqueado fica de fora)")
    ok(any(s.startswith("Alma com a ponta solta (3)") for s in resumo), "as 3 almas com a ponta solta (pendurada, passando do banzo, saindo do nó)")
    ok(any(s.startswith("Peças repetidas no mesmo lugar (1)") for s in resumo), "a repetida")
    ok(any(s.startswith("Alma com a ponta solta (a conferir)") for s in resumo), "o montante da ponta fica para conferir")
    erros("Prévia")

    # 2) clicar num achado seleciona a peça
    clicar(".painel-reanalise details summary")
    ok(esperar("!!document.querySelector('.painel-reanalise details[open] li')", 5), "o grupo abre com os achados")
    clicar(".painel-reanalise details[open] li")
    ok(esperar("editor.selecao.ids.size > 0", 5), "clicar no achado seleciona a peça")

    # 3) aplicar
    texto = js("document.querySelector('.painel-reanalise .aplicar-reanalise').textContent")
    ok(texto.startswith("Aplicar as marcadas"), f"o botão diz o que aplica: {texto}")
    clicar(".painel-reanalise .aplicar-reanalise")
    ok(esperar(f"editor.documento.entidades.size === {N0 - 5}", 60), f"saíram as 5 sobras ({N0} → {n_pecas()})")
    ok(not jsj(f"return editor.documento.entidades.has({json.dumps(D['toco'].id)});"), "o toco saiu")
    ok(jsj(f"return editor.documento.entidades.has({json.dumps(D['bloqueada'].id)});"), "o toco bloqueado ficou")
    ok(jsj(f"return editor.documento.entidades.has({json.dumps(D['ponta'].id)});"), "o montante da ponta ficou")
    ok(jsj("return (editor.documento.metadados.reanalise || {}).versao;") == 1, "o carimbo da versão das regras no modelo")
    ok(esperar("!document.querySelector('.painel-reanalise .aplicar-reanalise') && !!document.querySelector('.painel-reanalise')", 10),
       "o painel fica só com o que é para conferir")
    erros("Aplicar")

    # 4) o Ctrl+Z de verdade volta tudo de uma vez
    js("document.activeElement && document.activeElement.blur(); 1")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Control", windowsVirtualKeyCode=17, modifiers=2)
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Control", windowsVirtualKeyCode=17, modifiers=0)
    ok(esperar(f"editor.documento.entidades.size === {N0}", 10), f"Ctrl+Z volta as {N0} peças de uma vez")
    erros("Desfazer")

    # 5) a conexão cai no meio (o servidor do modo dev reinicia a cada .py salvo — CD Bom Dia, 19/10: "Failed to fetch"):
    #    a tela espera o servidor voltar e refaz a reanálise sozinha, sem o aviso de erro
    js("""(() => { const orig = window.fetch; let caiu = false;
          window.fetch = function (u, o) {
            if (!caiu && String(u).includes('/reanalisar')) { caiu = true; return Promise.reject(new TypeError('Failed to fetch')); }
            return orig.apply(this, arguments); };
          return 1; })()""")
    clicar(".painel-reanalise .painel-apoios-titulo button")      # Analisar de novo
    ok(esperar("!!document.querySelector('.painel-reanalise .aplicar-reanalise')", 60),
       "com a conexão caindo no meio, a prévia abriu mesmo assim (refeita depois que o servidor respondeu)")
    ok(not js("document.body.textContent.includes('o servidor não respondeu')"), "sem o aviso de erro")
    erros("Conexão caindo")

finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
