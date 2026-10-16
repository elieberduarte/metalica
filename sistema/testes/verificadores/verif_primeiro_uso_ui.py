# -*- coding: utf-8 -*-
"""Achados de tela dos testes de primeiro uso (16/10/2026, Projeto/BRIEFINGS/Briefing-primeiro-uso*.md): cada bloco
refaz, com eventos de verdade, o que o engenheiro novo fez e confere que não volta a acontecer. Servidor próprio numa
pasta temporária (nunca a 8765/8766). Ver sistema/testes/REGRESSOES.md, seção "Primeiro uso"."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_primeiro_uso_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(80):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def projeto(nome, tipo="lancamento"):
    return urllib.parse.quote(post("/api/projetos", {"nome": nome, "tipo": tipo})["slug"])


def p02_p13_recebido(aba):
    """P02: na tela inicial não havia "Recebi o projeto estrutural"; o engenheiro com o DXF do projetista importava como
    arquitetônico. P13: o Projeto recebido abria o seletor do Windows sem explicar nada antes."""
    print("P02/P13 — Novo pelo CAD 2D com o projeto estrutural recebido")
    aba.navegar(base + "/", limite=60)
    esperar(aba, "document.querySelector('#btn-novo-cad') && document.querySelector('#contagem') && !/carregando/.test(document.querySelector('#contagem').textContent)")
    # P20: os botões Novo… da pasta vazia e da barra com o mesmo nome e com dica
    pares = aba.avaliar("""[['novo', 'btn-novo'], ['novo-ifc', 'btn-novo-ifc'], ['novo-cad', 'btn-novo-cad']].map(([a, b]) => {
        const x = document.querySelector(`[data-acao="${a}"]`), y = document.getElementById(b);
        return [x.textContent.trim(), y.textContent.trim(), !!x.title, !!y.title]; })""") or []
    ok(pares and all(p[0] == p[1] and p[2] and p[3] for p in pares), f"P20: botões Novo… iguais nos dois lugares e com dica: {pares}")
    sel = "#btn-novo-cad" if aba.avaliar("document.querySelector('#btn-novo-cad').offsetParent !== null") else '[data-acao="novo-cad"]'
    clicar(aba, sel)
    esperar(aba, "document.querySelector('#dlg').open")
    marcado = aba.avaliar("(document.querySelector('input[name=dlg-comeco]:checked') || {}).value")
    ok(marcado == "recebido", f"a opção do projeto recebido existe e vem marcada ({marcado})")
    aba.cmd("Input.insertText", text="Portaria recebida")
    clicar(aba, "#dlg-ok")
    esperar(aba, "location.pathname === '/cad' && window.cad && document.body.dataset.pronto === '1'", 60)
    esperar(aba, "window.cad.el && document.querySelector('dialog[open]')", 10)
    titulo = aba.avaliar("(document.querySelector('dialog[open] h3, dialog[open] .titulo, dialog[open] header') || {}).textContent || document.querySelector('dialog[open]') && document.querySelector('dialog[open]').textContent.slice(0, 60)") or ""
    ok(aba.avaliar("location.pathname") == "/cad" and "Projeto recebido" in titulo, f"o CAD abre explicando o Projeto recebido antes do arquivo («{titulo.strip()[:50]}»)")
    s = aba.avaliar("new URL(location.href).searchParams.get('projeto')")
    tipo = json.load(urllib.request.urlopen(f"{base}/api/projetos/{urllib.parse.quote(s)}", timeout=30)).get("projeto", {}).get("tipo")
    ok(tipo == "recebido", f"o projeto nasce com o tipo recebido ({tipo})")
    aba.avaliar("document.querySelector('dialog[open]') && document.querySelector('dialog[open]').close('cancelar'); 1")


def p06_vao_pequeno(aba):
    """P06: eixos com 4 m de vão — o Lançar estrutura nos eixos avisa antes (5 a 60 m) e oferece Pilares nos eixos,
    em vez de aceitar e voltar com "Vão: valor 4.0 fora da faixa" depois do clique."""
    print("P06 — vão de 4 m no Lançar estrutura nos eixos")
    s = projeto("Portaria vão pequeno")
    post(f"/api/projetos/{s}/eixos", {"eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
                                                "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 4000.0}],
                                                "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto")
    aba.avaliar("window.editor.dialogoLancar(); 1")
    esperar(aba, "window.editor.el.dialogo.open")
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent") or ""
    botao = aba.avaliar("window.editor.el.dialogoOk.hidden ? '' : window.editor.el.dialogoOk.textContent") or ""
    ok("5 a 60 m" in txt and "4,00" in txt, f"o diálogo avisa a faixa antes: {txt[:110]}")
    ok(botao != "Lançar", f"sem o botão Lançar (botão: «{botao}»)")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")


def clicar(aba, seletor):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
    if not r:
        raise RuntimeError("não achei " + seletor)
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    aba.drenar(0.3)


def tecla_esc(aba):
    for tipo in ("rawKeyDown", "keyUp"):
        aba.cmd("Input.dispatchKeyEvent", type=tipo, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.3)


def p11_p12_cad(aba):
    """P12: Esc não fechava o menu aberto do CAD (ficava por cima do desenho). P11: o mesmo aviso de erro fixo
    se repetia na pilha, e os fixos seguiam ao trocar de desenho."""
    print("P11/P12 — menus e avisos do CAD")
    s = projeto("Portaria CAD", tipo="desenho")
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    clicar(aba, '.menu[data-menu="lancamento"] > button')
    ok(bool(aba.avaliar("!!document.querySelector('.menu.aberto')")), "o menu Lançamento abriu com o clique")
    tecla_esc(aba)
    ok(not aba.avaliar("!!document.querySelector('.menu.aberto')"), "Esc fecha o menu aberto")
    clicar(aba, '.menu[data-menu="desenho"] > button')
    clicar(aba, '[data-acao="projeto-2d"]')
    t = aba.avaliar("(document.querySelector('dialog[open]') || {}).textContent || ''") or ""
    ok("Projeto recebido" in t and "Escolher o arquivo" in t, "Desenho → Projeto recebido explica antes de abrir o seletor de arquivo")
    aba.avaliar("document.querySelector('dialog[open]') && document.querySelector('dialog[open]').close('cancelar'); 1")
    aba.avaliar("window.cad.aviso('Não foi possível montar: teste', 'erro', 0); window.cad.aviso('Não foi possível montar: teste', 'erro', 0); 1")
    n = aba.avaliar("[...document.querySelectorAll('#avisos .aviso')].filter(c => c.textContent.includes('montar: teste')).length")
    ok(n == 1, f"o mesmo aviso repetido fica um só ({n})")
    for i in range(7):
        aba.avaliar(f"window.cad.aviso('aviso {i}', 'info', 60000); 1")
    n = aba.avaliar("document.querySelectorAll('#avisos .aviso').length")
    ok(n <= 4, f"a pilha de avisos não passa de 4 ({n})")
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.el && window.editor.el.avisos")
    aba.avaliar("window.editor.aviso('Falhou: teste', 'erro'); window.editor.aviso('Falhou: teste', 'erro'); 1")
    n = aba.avaliar("[...window.editor.el.avisos.children].filter(c => c.textContent.includes('Falhou: teste')).length")
    ok(n == 1, f"no 3D, o mesmo aviso repetido fica um só ({n})")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_primeiro_uso_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    for bloco in (p02_p13_recebido, p06_vao_pequeno, p11_p12_cad):
        try:
            bloco(aba)
        except Exception as e:                       # noqa: BLE001
            ok(False, f"{bloco.__name__}: {e}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
