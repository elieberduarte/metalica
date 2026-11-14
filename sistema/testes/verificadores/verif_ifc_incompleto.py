# -*- coding: utf-8 -*-
"""D06 (agente usuario-desastrado, 13/11): o IFC que chegou cortado entrava calado — 176 peças de 434, o 3D abria no modo
ver sem aviso nenhum. No navegador de verdade: um IFC cortado no meio é importado num projeto; o cartão da lista diz
"IFC INCOMPLETO", o modo ver mostra a faixa no alto e o editor mostra o aviso em toda abertura (não só na primeira). O
projeto com o IFC inteiro não mostra nada disso, e o que não é IFC (uma imagem renomeada) é recusado pela rota."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ifcinc_")
INTEIRO = open(os.path.join(BASE, "testes", "dados_ifc", "estrutura_mm.ifc"), "rb").read()
CORTADO = INTEIRO[:len(INTEIRO) * 2 // 3].rsplit(b"\n", 1)[0] + b"\n#9001=IFCCARTESIANPOINT((0.,0."
PNG = b"\x89PNG\r\n\x1a\n" + bytes(600)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def postar(rota, corpo):
    """(status, resposta) — o erro da rota vem como 400 com {"erro"}"""
    req = urllib.request.Request(f"http://localhost:{PORTA}{rota}", data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def importar(nome, arquivo, bruto):
    _, criado = postar("/api/projetos", {"nome": nome, "tipo": "ifc"})
    s = criado["slug"]
    st, r = postar(f"/api/projetos/{s}/importar-ifc", {"nome": arquivo, "conteudo_b64": base64.b64encode(bruto).decode("ascii")})
    return s, st, r


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ifcinc_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    cortado, st, r = importar("Obra cortada", "cortado.ifc", CORTADO)
    ok(st == 200 and r.get("avisos") and "INCOMPLETO" in r["avisos"][0], "a rota importa o IFC cortado e devolve o aviso")
    pecas = (r.get("resumo") or {}).get("pecas")
    print("       peças lidas:", pecas, "| aviso:", (r.get("avisos") or [""])[0][:110])
    ok(bool(pecas), "o corte deixou peças (o caso do defeito: parte do modelo)")
    inteiro, st, r = importar("Obra inteira", "inteiro.ifc", INTEIRO)
    ok(st == 200 and r.get("avisos") == [], "o IFC inteiro entra sem aviso")
    _, st, r = importar("Obra foto", "foto.ifc", PNG)
    ok(st == 400 and "não é um IFC" in (r.get("erro") or ""), "a imagem renomeada para .ifc é recusada (400, \"não é um IFC\")")

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    def esperar(cond, limite=60.0, passo=0.3):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(passo)
        return False

    # a lista de projetos: só o cartão da obra cortada diz
    aba.navegar(f"http://localhost:{PORTA}/", limite=60)
    ok(esperar("document.querySelectorAll('.cartao-sub').length >= 3"), "a lista abriu com os cartões")
    subs = aba.avaliar("[...document.querySelectorAll('.cartao-sub')].map(x => x.textContent)")
    print("       cartões:", subs)
    ok(sum("IFC INCOMPLETO" in t for t in subs) == 1 and any("cortado.ifc" in t and "IFC INCOMPLETO" in t for t in subs),
       "só o cartão da obra cortada diz \"IFC INCOMPLETO\"")

    # o modo ver: a faixa no alto, visível, sem cobrir os botões
    aba.navegar(f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto={cortado}", limite=120)
    ok(esperar("!!window.ver3dPronto", 120), "o modo ver abriu a obra cortada")
    ok(esperar("!!document.getElementById('aviso-ifc')", 15), "o modo ver mostra a faixa do IFC incompleto")
    faixa = aba.avaliar("""(() => { const f = document.getElementById('aviso-ifc'); if (!f) return null;
        const r = f.getBoundingClientRect();
        const bot = [...document.querySelectorAll('#ferramentas button')].filter(x => x.offsetParent).map(x => x.getBoundingClientRect());
        return {texto: f.textContent, topo: r.top, base: r.bottom, larg: r.width, visivel: r.width > 100 && r.height > 10,
                cobre: bot.some(b => r.left < b.right && r.right > b.left && r.top < b.bottom && r.bottom > b.top)}; })()""")
    print("       faixa:", faixa)
    ok(bool(faixa) and "INCOMPLETO" in faixa["texto"] and faixa["visivel"], "a faixa diz INCOMPLETO e está à vista")
    ok(bool(faixa) and not faixa["cobre"], "a faixa não cobre os botões do alto")
    aba.avaliar("document.querySelector('#aviso-ifc button').click()")
    ok(aba.avaliar("!document.getElementById('aviso-ifc')"), "o × fecha a faixa")
    aba.navegar(f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto={inteiro}", limite=120)
    ok(esperar("!!window.ver3dPronto", 120) and aba.avaliar("!document.getElementById('aviso-ifc')"),
       "a obra com o IFC inteiro abre sem a faixa")

    # o editor: o aviso em toda abertura (o cartão "Importado" é que aparece uma vez só)
    for vez in (1, 2):
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto={cortado}", limite=120)
        esperar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 1)", 90)
        ok(esperar("[...document.querySelectorAll('.aviso[data-tipo=\"atencao\"]')].some(a => /INCOMPLETO/.test(a.textContent))", 20),
           "o editor mostra o aviso do IFC incompleto (abertura %d)" % vez)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto={inteiro}", limite=120)
    esperar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 1)", 90)
    aba.drenar(3)
    ok(aba.avaliar("![...document.querySelectorAll('.aviso')].some(a => /INCOMPLETO/.test(a.textContent))"),
       "o editor da obra com o IFC inteiro não mostra o aviso")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
