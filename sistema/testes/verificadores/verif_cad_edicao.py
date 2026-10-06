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
    ok(js("return c.tela.alcas().filter(a => a.id === 'la').length;") == 3, "a linha selecionada tem as alças das pontas e a do meio")
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
    # F. cota da prancha (célula em 1:25, o número escrito é a medida da peça): mexer na ponta mantém a escala
    js("""c.doc.add({ id: 'cp', tipo: 'cota', camada: 'COTA', modo: 'h', p1: [30000, 30000], p2: [30034.32, 30000], deslocamento: -4, texto: '858', altura: 2.5 });
          c.ativarFerramenta('selecionar'); c.selecionar(['cp']); return 1;""")
    js("const f = c.ferramenta; const a = c.tela.alcas().find(x => x.id === 'cp' && x.parte === 'p2'); f._pegarAlca(a); f.onMover([30038.32, 30000]); f._recemPega = false; f.onPonto([30038.32, 30000], {}); return 1;")
    ok(js("return c.doc.get('cp').texto;") == "958",
       "cota da prancha em 1:25 (858): puxada 4 mm no papel vira %s (era 34 antes da correção)" % js("return c.doc.get('cp').texto;"))
    js("c.desfazer(); c.selecionar([]); return 1;")

    # E. A+ em vários textos: o bloco cresce junto, sem encavalar (01/10: "vai comendo os espaçamentos")
    js("""for (const [i, s] of ['NESTA PRANCHA', 'T.O.1 02x', 'T.O.2 02x'].entries()) c.doc.add({ id: 'tx' + i, tipo: 'texto', camada: 'TEXTO', posicao: [20000, 20000 - i * 3.2 * c.doc.escala], texto: s, altura: 2.0 });
          c.doc.add({ id: 'tx9', tipo: 'texto', camada: 'TEXTO', posicao: [20000 + 40 * c.doc.escala, 20000], texto: 'SIGLAS', altura: 2.0 });
          c.selecionar(['tx0', 'tx1', 'tx2', 'tx9']); return 1;""")
    aba.drenar(0.5)
    for _ in range(2):
        js("[...document.querySelectorAll('button')].find(b => b.textContent === 'A+').click(); return 1;"); aba.drenar(0.3)
    r = json.loads(js("return JSON.stringify(['tx0','tx1','tx2','tx9'].map(i => [c.doc.get(i).altura, ...c.doc.get(i).posicao]));"))
    passo = (r[0][2] - r[1][2]) / js("return c.doc.escala;")
    ok(abs(r[0][0] - 3.13) < 0.02 and abs(passo - 3.2 * 1.5625) < 0.05 and r[0][1:] == [20000, 20000],
       "A+ duas vezes em 4 textos: letra 2,0 → %.2f e as linhas se afastam junto (passo %.2f mm), o canto de cima fica" % (r[0][0], passo))
    ok(abs((r[3][1] - r[0][1]) / js("return c.doc.escala;") - 40 * 1.5625) < 0.1, "e a coluna do lado se afasta na mesma proporção: %s" % r)
    # G. duplo clique num texto edita ali mesmo (01/10)
    js("""c.doc.add({ id: 'tdc', tipo: 'texto', camada: 'TEXTO', posicao: [50000, 50000], texto: 'CB1 + CH9', altura: 3.5 });
          c.tela.enquadrar([[49500, 49500], [52000, 51500]]); c.ativarFerramenta('selecionar'); return 1;""")
    aba.drenar(0.4)
    js("""const cv = c.tela.canvas || document.querySelector('#canvas2d'); const r = cv.getBoundingClientRect();
          const q = c.tela.paraTela([50000 + 300, 50000 + 30]);
          cv.dispatchEvent(new MouseEvent('dblclick', { clientX: r.left + q[0], clientY: r.top + q[1], button: 0, bubbles: true })); return 1;""")
    aba.drenar(0.3)
    ok(js("return !!document.querySelector('.editar-texto-no-lugar') && document.querySelector('.editar-texto-no-lugar').value;") == "CB1 + CH9",
       "duplo clique no texto abre a edição no lugar, com o texto dele")
    js("""const i = document.querySelector('.editar-texto-no-lugar'); i.value = 'CB1 + CH9 (2x)';
          i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1;""")
    aba.drenar(0.3)
    ok(js("return c.doc.get('tdc').texto;") == "CB1 + CH9 (2x)" and not js("return !!document.querySelector('.editar-texto-no-lugar');"),
       "Enter grava o texto novo e fecha a caixa")
    js("c.desfazer(); return 1;")
    ok(js("return c.doc.get('tdc').texto;") == "CB1 + CH9", "Ctrl+Z volta o texto")
    # H. janela de seleção com Ctrl soma ao que já estava selecionado (01/10: com o Ctrl ela trocava a seleção)
    js("""c.doc.add({ id: 'wa', tipo: 'linha', camada: 'VISTA', atributos: {}, a: [70000, 70000], b: [70100, 70000] });
          c.doc.add({ id: 'wb', tipo: 'linha', camada: 'VISTA', atributos: {}, a: [71000, 70000], b: [71100, 70000] });
          c.tela.enquadrar([[69500, 69000], [71600, 71000]]); c.ativarFerramenta('selecionar'); c.selecionar(['wa']); return 1;""")
    aba.drenar(0.4)

    def janela(de, para, mod):
        q = json.loads(js("""const cv = c.tela.canvas || document.querySelector('#canvas2d'); const r = cv.getBoundingClientRect();
                             return JSON.stringify([%s, %s].map(p => { const t = c.tela.paraTela(p); return [r.left + t[0], r.top + t[1]]; }));""" % (de, para)))
        (x0, y0), (x1, y1) = q
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1, modifiers=mod)
        for t in (0.3, 0.6, 1.0):
            aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * t, y=y0 + (y1 - y0) * t, button="left", buttons=1, modifiers=mod)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left", buttons=0, clickCount=1, modifiers=mod)
        aba.drenar(0.3)
        return sorted(json.loads(js("return JSON.stringify([...c.tela.selecao]);")))
    s = janela("[70900, 69900]", "[71200, 70100]", 2)
    ok(s == ["wa", "wb"], f"janela com Ctrl soma à seleção: {s}")
    js("c.selecionar(['wa']); return 1;")
    s = janela("[70900, 69900]", "[71200, 70100]", 0)
    ok(s == ["wb"], f"e sem tecla a janela troca a seleção, como antes: {s}")

    # I. a escala da cota (01/10: "criar alguma opção para escolher a escala da cota"): na prancha, a cota feita numa
    # célula em 1:25 mostra a medida da peça; o painel deixa trocar
    r_i = json.loads(aba.avaliar("""(async () => {
      const c = window.cad, { Tela } = await import('/cad/nucleo/tela.js');
      c.doc.metadados = { ...(c.doc.metadados || {}), prancha: { celulas: [{ titulo: 'CH16', escala: 25, caixa: [90000, 90000, 90200, 90200] }] } };
      c.ativarFerramenta('cota');
      const nova = c.ferramenta._cota([90010, 90010], [90010.56, 90010], null);
      const fora = c.ferramenta._cota([10, 10], [10.56, 10], null);
      c.ativarFerramenta('selecionar');
      c.doc.add({ ...nova, id: 'cesc' });
      c.selecionar(['cesc']);
      await new Promise(r => setTimeout(r, 300));
      const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.textContent === '1:25') && s.closest('#painel-props, .props, aside, body'));
      return JSON.stringify({ escala: nova.escala || null, fora: fora.escala || null, txt: Tela.textoCota(nova, c.doc.escala).txt,
                              painel: sel ? sel.value : null });
    })()"""))
    ok(r_i["escala"] == 25 and r_i["fora"] is None and r_i["txt"] == "14" and r_i["painel"] == "25",
       f"cota nova na célula 1:25 da prancha: escala 25, mostra 14 (0,56 × 25), o painel tem a escala; fora da célula, sem escala ({r_i})")
    # J. a cota horizontal girada não vira "0,6" (01/10: "quando rotaciono … elas desconfiguram inteiras")
    r_j = json.loads(aba.avaliar("""(async () => {
      const { transformar, valorCota } = await import('/cad/nucleo/desenho2d.js');
      const h = { id: 'h1', tipo: 'cota', camada: 'COTA', modo: 'h', p1: [0, 0], p2: [122, 50], deslocamento: -10, texto: null, altura: 2.5, atributos: {} };
      const gira = (g) => { const t = g * Math.PI / 180, cs = Math.cos(t), sn = Math.sin(t); return (p) => [p[0] * cs - p[1] * sn, p[0] * sn + p[1] * cs]; };
      const r30 = transformar(h, gira(30)), r90 = transformar(h, gira(90)), esp = transformar(h, (p) => [p[1], p[0]], (a) => a, 1, true);
      return JSON.stringify([[r30.modo, Math.round(valorCota(r30))], [r90.modo, Math.round(valorCota(r90))], [esp.modo, Math.round(valorCota(esp))]]);
    })()"""))
    ok(r_j == [["alinhada", 122], ["v", 122], ["v", 122]], f"cota de 122 girada 30° e 90° e espelhada na diagonal continua 122 ({r_j})")

    # K. Escala (o SCALE do AutoCAD, 06/10): por fator e por referência (dois pontos de uma medida conhecida e a medida
    # nova digitada); Ctrl+Z desfaz
    r_k = json.loads(js("""
      c.ativarFerramenta('linha'); c.ferramenta.onPonto([90000, 0]); c.ferramenta.onPonto([90050.5, 0]); c.ferramenta.cancelar();
      const ln = [...c.doc.entidades.values()].filter(e => e.tipo === 'linha' && e.a[0] === 90000)[0];
      c.selecionar([ln.id]);
      c.ativarFerramenta('escalar'); c.ferramenta.onPonto([90000, 0], {}); c.ferramenta.onValor('2');
      const L2 = Math.hypot(c.doc.get(ln.id).b[0] - c.doc.get(ln.id).a[0], c.doc.get(ln.id).b[1] - c.doc.get(ln.id).a[1]);
      c.desfazer();
      c.selecionar([ln.id]);
      c.ativarFerramenta('escalar'); c.ferramenta.onPonto([90000, 0], {}); c.ferramenta.onValor('R');
      c.ferramenta.onPonto([90000, 0], {}); c.ferramenta.onPonto([90050.5, 0], {}); c.ferramenta.onValor('505cm');
      const e = c.doc.get(ln.id);
      const Lr = Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1]);
      c.desfazer();
      const e0 = c.doc.get(ln.id);
      // sem clicar o ponto base: o fator direto, em volta do centro da seleção
      c.selecionar([ln.id]); c.ativarFerramenta('escalar'); c.ferramenta.onValor('3');
      const e3 = c.doc.get(ln.id), meio3 = (e3.a[0] + e3.b[0]) / 2, L3 = Math.hypot(e3.b[0] - e3.a[0], e3.b[1] - e3.a[1]);   // antes do Ctrl+Z (ele volta o objeto)
      c.desfazer();
      return JSON.stringify([Math.round(L2 * 10) / 10, Math.round(Lr), Math.round(Math.hypot(e0.b[0] - e0.a[0], e0.b[1] - e0.a[1]) * 10) / 10,
                             Math.round(L3 * 10) / 10, Math.round(meio3 * 10) / 10]);
    """))
    ok(r_k == [101.0, 5050, 50.5, 151.5, 90025.3], f"Escala: fator 2 dobra; por referência 50,5 → 505 cm vira 5050 mm; Ctrl+Z volta; o fator digitado sem ponto base escala em volta do centro ({r_k})")

    # L. a alça do meio do eixo da malha (06/10: "mover só selecionando o meio da malha e ela ajuste as cotas"): o eixo
    # anda atravessado, com a bolinha e o nome; as cotas da malha com ponta nele mudam; o último eixo leva as pontas dos
    # que o cruzam (e as bolinhas deles); digitar a distância move para o lado do cursor; Ctrl+Z volta tudo
    r_l = json.loads(js("""
      const X = 200000, E = (id, tipo, o) => c.doc.add({ id, tipo, camada: tipo === 'cota' ? 'COTA' : 'EIXO', ...o });
      const eixoH = (n, y) => { E('e' + n, 'linha', { atributos: { eixo: n, malha: true }, a: [X - 1500, y], b: [X + 13500, y] });
        E('b' + n, 'circulo', { atributos: { eixo: n, bolinha: true }, centro: [X - 2000, y], raio: 500 });
        E('t' + n, 'texto', { atributos: { eixo: n, nome_eixo: true }, posicao: [X - 2000, y], texto: n, altura: 4, angulo: 0, alinhamento: 'centro', vertical: 'meio' }); };
      const eixoV = (n, x) => { E('e' + n, 'linha', { atributos: { eixo: n, malha: true }, a: [X + x, 33500], b: [X + x, 18500] });
        E('b' + n, 'circulo', { atributos: { eixo: n, bolinha: true }, centro: [X + x, 34000], raio: 500 });
        E('t' + n, 'texto', { atributos: { eixo: n, nome_eixo: true }, posicao: [X + x, 34000], texto: n, altura: 4, angulo: 0, alinhamento: 'centro', vertical: 'meio' }); };
      eixoH('1', 20000); eixoH('2', 26000); eixoH('3', 32000); eixoV('A', 0); eixoV('B', 12000);
      const cota = (id, p1, p2, d) => E(id, 'cota', { atributos: { malha: true }, modo: 'alinhada', p1, p2, deslocamento: d, texto: null, altura: 2.5 });
      cota('c12', [X, 20000], [X, 26000], -6); cota('c23', [X, 26000], [X, 32000], -6); cota('c13', [X, 20000], [X, 32000], -11);
      cota('cAB', [X, 20000], [X + 12000, 20000], 6);
      const val = (id) => { const k = c.doc.get(id); return Math.round(Math.hypot(k.p2[0] - k.p1[0], k.p2[1] - k.p1[1])); };
      const pegar = (id) => { c.ativarFerramenta('selecionar'); c.selecionar([id]); const f = c.ferramenta;
        const a = c.tela.alcas().find(x => x.id === id && x.parte === 'meio'); f._pegarAlca(a); f._recemPega = false; return [f, a]; };
      // o eixo 2 para cima 1000 (o cursor fora do eixo: só a parte atravessada conta)
      let [f, a] = pegar('e2'); f.onMover([a.ponto[0] + 700, a.ponto[1] + 1000]); f.onPonto([a.ponto[0] + 700, a.ponto[1] + 1000], {});
      const r1 = [c.doc.get('e2').a[1], c.doc.get('e2').a[0] - X, c.doc.get('b2').centro[1], c.doc.get('t2').posicao[1], val('c12'), val('c23'), val('c13'), c.doc.get('eA').a[1]];
      c.desfazer();
      const r0 = [c.doc.get('e2').a[1], c.doc.get('b2').centro[1], val('c12')];
      // o eixo 3 (o último) 500 para cima, digitado com o cursor acima: as pontas de A e B e as bolinhas deles sobem junto
      [f, a] = pegar('e3'); c.tela.cursor = [a.ponto[0], a.ponto[1] + 50]; f.onValor('500');
      const r2 = [c.doc.get('e3').a[1], val('c23'), val('c13'), c.doc.get('eA').a[1], c.doc.get('eA').b[1], c.doc.get('bB').centro[1], c.doc.get('tA').posicao[1], c.doc.get('e1').a[1]];
      c.desfazer();
      // o eixo A 1000 para a direita: a cota A–B encolhe e a cadeia vai junto (as pontas estão no eixo A)
      [f, a] = pegar('eA'); f.onPonto([a.ponto[0] + 1000, a.ponto[1]], {});
      const r3 = [val('cAB'), val('c12'), c.doc.get('c12').p1[0] - X, c.doc.get('e1').a[0] - X];
      c.desfazer();
      // as alças das pontas, uma de cada vez (como o usuário fez, 06/10): a bolinha e as cotas vêm junto
      const ponta = (id, parte, q) => { c.ativarFerramenta('selecionar'); c.selecionar([id]); const f = c.ferramenta;
        const a = c.tela.alcas().find(x => x.id === id && x.parte === parte); f._pegarAlca(a); f._recemPega = false; f.onPonto(q, {}); };
      ponta('eA', 'b', [X + 1000, 15000]); ponta('eA', 'a', [X + 1000, 33500]);
      const bA = c.doc.get('bA'), tA = c.doc.get('tA');
      const r4 = [Math.round(bA.centro[0] - X), Math.round(bA.centro[1]), Math.round(tA.posicao[0] - X), val('cAB'), Math.round(c.doc.get('c23').p2[0] - X), val('c23')];
      c.desfazer(); c.desfazer();
      const r5 = [Math.round(c.doc.get('bA').centro[0] - X), val('cAB')];
      return JSON.stringify([r1, r0, r2, r3, r4, r5]);
    """))
    ok(r_l[0] == [27000, -1500, 27000, 27000, 7000, 5000, 12000, 33500], f"eixo 2 movido 1000 atravessado: bolinha e nome junto, cotas 7000/5000, a total e o eixo A ficam ({r_l[0]})")
    ok(r_l[1] == [26000, 26000, 6000], f"Ctrl+Z volta o eixo, a bolinha e a cota ({r_l[1]})")
    ok(r_l[2] == [32500, 6500, 12500, 34000, 18500, 34500, 34500, 20000], f"o último eixo (3) movido 500 digitado: A e B esticam em cima e as bolinhas sobem; o eixo 1 fica ({r_l[2]})")
    ok(r_l[3] == [11000, 6000, 1000, -500], f"eixo A (o último à esquerda) movido 1000: a cota A–B dá 11000, a cadeia dos números vai junto e as pontas dos eixos 1–3 também ({r_l[3]})")

    ok(r_l[4] == [1000, 34000, 1000, 11000, 1000, 6000], f"eixo A esticado pelas pontas até 1000 adiante: a bolinha, o nome e as cotas vêm junto ({r_l[4]})")
    ok(r_l[5] == [0, 12000], f"Ctrl+Z duas vezes volta ({r_l[5]})")
    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
