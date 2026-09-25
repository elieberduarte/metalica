# -*- coding: utf-8 -*-
"""Edição no CAD (0.8.17): alça na ponta da linha leva até outro ponto; Esticar anda no eixo
da própria barra mesmo com a barra de outra peça chegando no nó; duas cópias da mesma peça
separadas são selecionadas uma de cada vez; Explodir vira linhas soltas e Juntar devolve a
polilinha com o vínculo da peça."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8803
DADOS = tempfile.mkdtemp(prefix="metalica_cadedit_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def L(id_, a, b, **atr):
    return {"id": id_, "tipo": "linha", "camada": "VISTA", "atributos": atr, "a": a, "b": b}


def PL(id_, vs, fechada=False, **atr):
    return {"id": id_, "tipo": "polilinha", "camada": "VISTA", "atributos": atr, "vertices": vs, "fechada": fechada}


ents = [
    # A. alça: linha horizontal e uma vertical adiante
    L("la", [0, 0], [1000, 0]), L("lv", [1500, -500], [1500, 500]),
    # B. barra da peça "A" com a ponta cortada inclinada e a barra da peça "B" saindo do mesmo nó
    PL("bs", [[0, 3100], [1050, 3100]], origem="A"), PL("bi", [[0, 3000], [1000, 3000]], origem="A"),
    L("bc", [1000, 3000], [1050, 3100], origem="A"),
    L("bo", [1000, 3000], [1400, 2600], origem="B"),
    # C. duas cópias (mesmo grupo) da mesma peça, afastadas
    PL("c1", [[0, 6000], [800, 6000], [800, 6050], [0, 6050]], True, origem="C", grupo_copia="g"),
    PL("c2", [[0, 6400], [800, 6400], [800, 6450], [0, 6450]], True, origem="C", grupo_copia="g"),
    # D. polilinha de peça para explodir e juntar
    PL("dp", [[0, 9000], [600, 9000], [600, 9200]], origem="D"),
]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadedit_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Edicao", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/edicao", {"desenho": {"nome": "Edicao", "escala": 25, "entidades": ents}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + f"/cad?projeto={slug}&desenho=edicao", limite=30)
    ok(esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho === 9"), "desenho aberto")
    js = lambda s: aba.avaliar("(() => { const c = window.cad; " + s + " })()")

    # A. alça na ponta da linha
    js("c.tela.enquadrar(); c.ativarFerramenta('selecionar'); c.selecionar(['la']); return 1;")
    ok(js("return c.tela.alcas().filter(a => a.id === 'la').length;") == 2, "a linha selecionada tem as duas alças")
    js("const f = c.ferramenta; const a = c.tela.alcas().find(x => x.id === 'la' && x.parte === 'b'); f._pegarAlca(a); f.onMover([1500, 0]); f._recemPega = false; f.onPonto([1500, 0], {}); return 1;")
    ok(js("return JSON.stringify(c.doc.get('la').b);") == "[1500,0]", "a alça levou a ponta até a outra linha")
    js("c.desfazer(); return 1;")
    ok(js("return JSON.stringify(c.doc.get('la').b);") == "[1000,0]", "desfazer volta a ponta")
    js("c.selecionar(['la']); const f = c.ferramenta; const a = c.tela.alcas().find(x => x.id === 'la' && x.parte === 'b'); f._pegarAlca(a); return 1;")
    ok(js("return JSON.stringify(c.snap.direcoes);") == "[[1,0]]", "a alça segue a continuação da linha")
    js("c.ferramenta.onValor('1250'); return 1;")
    ok(abs(js("return c.doc.get('la').b[0];") - 1250) < 0.01, "comprimento digitado na alça (1250)")
    js("c.desfazer(); c.selecionar([]); return 1;")

    # B. Esticar no eixo da barra
    js("c.ativarFerramenta('esticar'); const f = c.ferramenta; const p = [1025, 3050]; f.onPonto(p, { px: c.tela.paraTela(p) }); f.onPonto([1325, 2950], {}); return 1;")   # pegar a aresta já fixa a base
    ok(js("return JSON.stringify([c.doc.get('bs').vertices[1], c.doc.get('bi').vertices[1]]);") == "[[1350,3100],[1300,3000]]",
       "Esticar andou só no eixo da barra: %s" % js("return JSON.stringify([c.doc.get('bs').vertices[1], c.doc.get('bi').vertices[1]]);"))
    js("c.desfazer(); c.ativarFerramenta('selecionar'); return 1;")

    # C. cópias separadas da mesma peça
    ok(js("return JSON.stringify(c.pecaDe('c1'));") == '["c1"]', "a cópia afastada não vem junto na seleção da peça")

    # D. Explodir e Juntar
    js("c.selecionar(['dp']); c.ativarFerramenta('explodir'); return 1;")
    soltas = js("return [...c.doc.entidades.values()].filter(e => (e.atributos || {}).origem_explodida === 'D').length;")
    ok(soltas == 2 and not js("return !!c.doc.get('dp');"), f"Explodir: a polilinha virou {soltas} linhas soltas")
    ok(js("return [...c.doc.entidades.values()].filter(e => (e.atributos || {}).origem_explodida === 'D').every(e => !e.atributos.origem);"),
       "as linhas soltas não são mais a peça")
    js("const ids = [...c.doc.entidades.values()].filter(e => (e.atributos || {}).origem_explodida === 'D').map(e => e.id); c.selecionar(ids); c.ativarFerramenta('juntar'); return 1;")
    pl = js("const p = [...c.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && (e.atributos || {}).origem === 'D'); return p.length ? JSON.stringify(p[0].vertices) : '';")
    ok(pl == "[[0,9000],[600,9000],[600,9200]]", f"Juntar devolveu a polilinha da peça: {pl}")
    ok(js("return c.ferramenta.constructor.id;") == "selecionar", "voltou para Selecionar")
    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
