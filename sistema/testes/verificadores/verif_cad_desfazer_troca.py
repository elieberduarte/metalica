# -*- coding: utf-8 -*-
"""D10 do usuario-desastrado (13/11): no CAD, depois de trocar de desenho e voltar, o Ctrl+Z não desfazia o que foi feito
antes da troca, e nada aparecia — o usuário achava que tinha desfeito e mandava a prancha com a linha. Agora o Desfazer de
cada desenho fica guardado enquanto a janela está aberta, e sem nada para desfazer vem o recado.

  A. desenhar uma linha em "a" (L, dois cliques, Esc), trocar para "b" e voltar: o Ctrl+Z desfaz a linha ("Desfeito");
  B. sem mais nada para desfazer, o Ctrl+Z dá o recado "Nada para desfazer…" (antes: silêncio);
  C. o desenho que mudou por fora enquanto se estava no outro (gravado por outra tela): a pilha velha não é aplicada nele,
     e o Ctrl+Z diz que o desenho mudou.

Toda entrada de desenho é Input.dispatchMouseEvent / Input.dispatchKeyEvent; a troca de desenho é a do menu (abrirDesenho).
Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_desfazer_troca.py"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import atalho_na_linha

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_desfazer_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def ents(prefixo):
    return [{"id": f"{prefixo}{i}", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 1000 * i], "b": [3000, 1000 * i]}
            for i in range(3)]


N0 = 3
TECLAS = {"Enter": 13, "Escape": 27}
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_desfazer_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Desfazer troca", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/a", {"desenho": {"nome": "A", "escala": 20, "entidades": ents("a")}})
    post(f"/api/projetos/{slug}/desenhos/b", {"desenho": {"nome": "B", "escala": 20, "entidades": ents("b")}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + f"/cad?projeto={slug}&desenho=a", limite=60)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.3)
        return False

    def tela(p):
        return js(f"const t = c.tela.paraTela({json.dumps(p)}), r = c.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")

    def clicar_mm(p):
        x, y = tela(p)
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=0); aba.drenar(0.06)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.2)

    def tecla(k, mods=0):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = k if len(k) == 1 and not mods else ("\r" if k == "Enter" else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 and k.isalpha() else "",
                windowsVirtualKeyCode=code, text=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        if not mods: atalho_na_linha(aba, k)
        aba.drenar(0.15)

    def trocar(nome):
        js(f"window.__trocou = false; c.abrirDesenho({json.dumps(nome)}).then(() => window.__trocou = true); return 1;")
        return esperar(f"window.__trocou && c.nomeDesenho === {json.dumps(nome)}", 30)

    def avisos():
        return js("return [...document.querySelectorAll('.aviso, .avisos *')].map(a => a.textContent).join(' | ');") or ""

    def desenhar_linha():
        js("c.tela.enquadrar([[-1000, -1000], [5000, 4000]]); return 1;")
        aba.drenar(0.3)
        tecla("l")
        clicar_mm([500, 3500])
        clicar_mm([2500, 3500])
        tecla("Escape"); tecla("Escape")

    ok(esperar(f"document.body.dataset.pronto === '1' && c && c.nomeDesenho === 'a' && c.doc.tamanho === {N0}", 60), "o CAD abriu o desenho a")

    # ------------------------------------------------------------------ A. desenhar, trocar, voltar, Ctrl+Z
    desenhar_linha()
    ok(js("return c.doc.tamanho;") == N0 + 1, f"A. a linha desenhada em a ({js('return c.doc.tamanho;')} objetos)")
    ok(trocar("b") and js("return c.doc.tamanho;") == N0, "A. trocou para b")
    ok(trocar("a") and js("return c.doc.tamanho;") == N0 + 1, "A. voltou para a (com a linha, gravada na troca)")
    tecla("z", 2)
    ok(js("return c.doc.tamanho;") == N0, f"A. o Ctrl+Z depois de voltar desfaz a linha ({js('return c.doc.tamanho;')} objetos; antes ficava {N0 + 1}, calado)")
    ok("Desfeito" in (js("return document.querySelector('#dica, .dica') ? document.querySelector('#dica, .dica').textContent : '';") or "")
       or esperar("[...document.querySelectorAll('*')].some(e => e.children.length === 0 && /Desfeito: /.test(e.textContent))", 3),
       "A. a dica \"Desfeito: …\"")

    # ------------------------------------------------------------------ B. nada mais para desfazer: o recado
    tecla("z", 2)
    ok(js("return c.doc.tamanho;") == N0, "B. o segundo Ctrl+Z não desfaz o que veio do arquivo")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /Nada para desfazer/.test(a.textContent))", 5),
       f"B. o recado \"Nada para desfazer…\" ({avisos()[:160]})")

    # ------------------------------------------------------------------ C. o desenho mudou por fora enquanto se estava no outro
    desenhar_linha()
    ok(js("return c.doc.tamanho;") == N0 + 1, "C. outra linha em a")
    ok(trocar("b"), "C. trocou para b")
    # outra tela grava o "a" com um objeto a mais
    post(f"/api/projetos/{slug}/desenhos/a", {"desenho": {"nome": "A", "escala": 20, "entidades": ents("a") + ents("x")}})
    ok(trocar("a") and js("return c.doc.tamanho;") == 2 * N0, f"C. voltou para a, com o que a outra tela gravou ({js('return c.doc.tamanho;')})")
    tecla("z", 2)
    ok(js("return c.doc.tamanho;") == 2 * N0, "C. a pilha velha não é aplicada no desenho que mudou")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => /Nada para desfazer: este desenho mudou/.test(a.textContent))", 5),
       f"C. o recado diz que o desenho mudou ({avisos()[:160]})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
