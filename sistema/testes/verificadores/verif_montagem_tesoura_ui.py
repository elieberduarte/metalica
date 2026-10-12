# -*- coding: utf-8 -*-
"""A tesoura do desenho do cliente na Montagem por eixos (11/10/2026, web/cad/implantacao.js, etapa 2).
Confere o caminho que o operador faz: os eixos e os níveis na Implantação; na Original (camadas do cliente travadas),
"Copiar" por área e os dois pontos de referência (os apoios); na Elevação do eixo 2, Ctrl+V pelos dois pontos — a
escala sai dos pontos e a medida é conferida com os eixos; "Tesoura…" lança o tipo T1 nos eixos marcados, no nível em
que foi colada; a tesoura aparece na elevação dos outros eixos e no 3D na medida real; o duplo clique nela abre a
elevação do eixo dela; colar com a medida errada avisa; lançar só num eixo com a marca de outros vira o tipo T1A."""
import json, os, shutil, subprocess, sys, tempfile, time, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_tesoura_")
PASTA = os.path.join(DADOS, "galpao")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Galpão", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-11T00:00:00", "alterado": "2026-10-11T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
# o desenho do cliente: a tesoura de duas águas de 20 m (banzo inferior reto, superior 600 → 1600 → 600, montantes a cada
# 2,5 m e diagonais), longe da origem, nas camadas ARQ travadas — como o arquitetônico entra
X0, Y0 = 100000.0, 50000.0
ents, n = [], 0


def lin(a, b, cam="ARQ TESOURA"):
    global n
    n += 1
    ents.append({"id": "t%d" % n, "tipo": "linha", "camada": cam, "a": [X0 + a[0], Y0 + a[1]], "b": [X0 + b[0], Y0 + b[1]]})


def topo(x):
    return 600 + 1000 * (1 - abs(x - 10000) / 10000)


lin((0, 0), (20000, 0))
lin((0, 600), (10000, 1600)); lin((10000, 1600), (20000, 600))
xs = [i * 2500 for i in range(9)]
for x in xs:
    lin((x, 0), (x, topo(x)))
for i in range(8):
    a, b = xs[i], xs[i + 1]
    lin((a, 0), (b, topo(b))) if i < 4 else lin((a, topo(a)), (b, 0))
N_TESOURA = len(ents)
cam = {"ARQ TESOURA": {"nome": "ARQ TESOURA", "cor": "#888888", "visivel": True, "bloqueada": True}}
json.dump({"nome": "Planta de lançamento", "unidade": "mm", "escala": 100, "camadas": cam, "entidades": ents, "vistas": [],
           "metadados": {"arquitetonico": {"deslocamento": [0.0, 0.0]}}},
          open(os.path.join(PASTA, "desenhos-2d", "planta-de-lançamento.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_tes_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


def foto(aba, nome):
    open(os.path.join(os.path.dirname(__file__), nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def avisos(aba):
    return aba.avaliar("document.querySelector('#avisos').textContent") or ""


def limpar_avisos(aba):
    aba.avaliar("document.querySelectorAll('#avisos .aviso').forEach(a => a.remove()); 1")


def ir(aba, qual):
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=%s]').click(); 1" % qual)
    esperar(aba, "cad.nomeDesenho === '%s'" % ("montagem" if qual == "montagem" else "planta-de-lançamento"), 20)
    aba.drenar(0.8)


try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/cad?projeto=galpao&desenho=" + "planta-de-lan%C3%A7amento", limite=60)
    esperar(aba, "!!(window.montagem && !document.querySelector('#abas-projeto').hidden)")
    ir(aba, "montagem")
    esperar(aba, "!!window.montagem._quadroImplantacao() && !!window.montagem._quadroImplantacao().mapa", 20)
    # os níveis e os eixos: 4 numerados a cada 6 m, 3 com letra a cada 10 m (o vão de 20 m da tesoura)
    aba.avaliar("""(async () => { await fetch('/api/projetos/galpao/niveis', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ niveis: [{ nome: 'Piso', z: 0 }, { nome: 'Apoio', z: 6000 }] }) });
      window.montagem._renovarCaixasNiveis();
      await window.montagem.gravarEixos({ eixo_g: [1, 0], numeros: [0, 6000, 12000, 18000].map((p, i) => ({ nome: String(i + 1), pos: p })),
        letras: ['A', 'B', 'C'].map((n, i) => ({ nome: n, pos: -i * 10000 })) });
      await window.montagem.abrirElevacao('2', 'numero'); window.__pronto = 1; })(); 1""")
    ok(esperar(aba, "window.__pronto === 1", 30), "eixos, níveis e a Elevação 2 prontos")
    aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('.quadro-titulo[data-tipo=elevacao] .quadro-botao')"), "a elevação tem \"Colar\" e \"Tesoura…\" no título")

    # na Original: Copiar por área (as camadas do cliente são travadas) e os dois apoios
    aba.avaliar("cad._salvando || !cad._editado ? 1 : cad.salvar({ avisar: false }); 1"); aba.drenar(1.0)
    ir(aba, "original")
    ok(not aba.avaliar("document.querySelector('#btn-copiar-tesoura').hidden"), "na Original aparece \"Copiar (Ctrl+C)\"")
    aba.avaliar("document.querySelector('#btn-copiar-tesoura').click(); 1"); aba.drenar(0.3)
    ok(aba.avaliar("cad.ferramenta.constructor.id") == "copiar-base" and aba.avaliar("cad.ferramenta.modoArea"),
       "sem nada selecionado, o Copiar pede a área")
    aba.avaliar("(() => { const f = cad.ferramenta; f.onPonto([%s, %s]); f.onPonto([%s, %s]); return 1; })()" % (X0 - 500, Y0 - 500, X0 + 20500, Y0 + 2500))
    ok(aba.avaliar("window.montagem._copiaPendente && window.montagem._copiaPendente.ents.length") == N_TESOURA,
       "a área pega a tesoura inteira, das camadas travadas: %s objetos" % aba.avaliar("window.montagem._copiaPendente && window.montagem._copiaPendente.ents.length"))
    aba.avaliar("(() => { const f = cad.ferramenta; f.onPonto([%s, %s]); f.onPonto([%s, %s]); return 1; })()" % (X0, Y0, X0 + 20000, Y0))
    ok(aba.avaliar("window.montagem._copia && window.montagem._copia.refs.length") == 2, "copiado com os dois pontos de referência (os apoios)")

    # na Montagem: Ctrl+V na Elevação 2, os apoios nos eixos A e C, na linha do Apoio (6 m)
    ir(aba, "montagem")
    q2 = json.loads(aba.avaliar("JSON.stringify(window.montagem._elevacoes().find(q => q.eixo === '2'))"))
    a1 = json.loads(aba.avaliar("JSON.stringify(window.montagem._paraPapel(window.montagem._elevacoes().find(q => q.eixo === '2'), [0, 6000]))"))
    a2 = json.loads(aba.avaliar("JSON.stringify(window.montagem._paraPapel(window.montagem._elevacoes().find(q => q.eixo === '2'), [20000, 6000]))"))
    limpar_avisos(aba)
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="v", code="KeyV", modifiers=2, windowsVirtualKeyCode=86)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="v", code="KeyV", modifiers=2, windowsVirtualKeyCode=86)
    aba.drenar(0.3)
    ok(aba.avaliar("cad.ferramenta.constructor.id") == "colar-base", "Ctrl+V na Montagem liga o Colar")
    aba.avaliar("(() => { const f = cad.ferramenta; f.onPonto(%s); f.onPonto(%s); return 1; })()" % (json.dumps(a1), json.dumps(a2)))
    aba.drenar(0.8)
    colados = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).colado && e.atributos.quadro === '%s'))" % q2["id"]))
    ok(len(colados) == N_TESOURA, "colados %d objetos dentro da Elevação 2" % len(colados))
    reais = json.loads(aba.avaliar("""JSON.stringify((() => { const m = window.montagem, q = m._elevacoes().find(q => q.eixo === '2');
      const ls = [...cad.doc.entidades.values()].filter(e => (e.atributos || {}).colado && e.tipo === 'linha');
      const pts = ls.flatMap(e => [m._paraReal(q, e.a), m._paraReal(q, e.b)]);
      return [Math.min(...pts.map(p => p[0])), Math.max(...pts.map(p => p[0])), Math.min(...pts.map(p => p[1])), Math.max(...pts.map(p => p[1]))]; })())"""))
    ok(abs(reais[0]) < 1 and abs(reais[1] - 20000) < 1 and abs(reais[2] - 6000) < 1 and abs(reais[3] - 7600) < 1,
       "na medida real da elevação: de u 0 a 20 m e de 6,00 a 7,60 m: %s" % [round(v) for v in reais])
    ok("Medida conferida" in avisos(aba), "o aviso confere a medida entre os pontos com a da elevação")
    foto(aba, "_tesoura_colada.png")

    # "Tesoura…": o desenho colado (selecionado) vira o tipo T1, nos 4 eixos
    aba.avaliar("(() => { const q = window.montagem._elevacoes().find(q => q.eixo === '2'); window.montagem.tesouraDaElevacao(q); return 1; })()")
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelectorAll('#dialogo input[type=checkbox]').length >= 4", 15)
    info = aba.avaliar("document.querySelector('#dialogo .explica').textContent") or ""
    ok("20,000 m" in info and "nível Apoio" in info, "o diálogo diz o comprimento e o nível do apoio: %s" % info[:160])
    aba.avaliar("""(() => { document.querySelectorAll('#dialogo input[type=checkbox]').forEach(c => { c.checked = true; }); document.querySelector('#dialogo-ok').click(); return 1; })()""")
    esperar(aba, "[...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').length === 4", 20)
    trels = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica'))"))
    ok(len(trels) == 4 and all(t["atributos"]["marca"] == "T1" and t["atributos"]["nivel_base"] == "Apoio" for t in trels),
       "a T1 lançada nos 4 eixos, no nível Apoio: %s" % sorted((t["atributos"]["eixo"], t["atributos"]["marca"], t["atributos"]["nivel_base"]) for t in trels))
    aba.drenar(1.0)
    n_el3 = aba.avaliar("""(() => { const m = window.montagem; return m.abrirElevacao('3', 'numero').then(q => [...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento_ref && e.atributos.quadro === q.id && e.tipo === 'linha').length); })()""")
    aba.drenar(1.0)
    n_el3 = aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(q => q.eixo === '3'); return [...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento_ref && e.atributos.quadro === q.id && e.tipo === 'linha').length; })()""")
    ok(n_el3 == N_TESOURA, "a Elevação 3 mostra a T1 lançada nela (%s barras)" % n_el3)

    # o 3D: as barras nos eixos (x 0, 6, 12, 18 m), do eixo A ao C (y 0 a −20 m), no Apoio (z ≥ 6 m)
    def _barras():
        mod = json.loads(aba.avaliar("(async () => JSON.stringify(await (await fetch('/api/projetos/galpao/modelo')).json()))()") or "{}")
        es = (mod.get("documento") or {}).get("entidades") or []
        return [e for e in es if (e.get("atributos") or {}).get("planta") == "montagem"]
    t0 = time.time()
    while time.time() - t0 < 40 and len(_barras()) < 4 * N_TESOURA:
        aba.drenar(0.6)
    bs = _barras()
    xs3 = sorted({round(c) for b in bs for c in (b["inicio"][0], b["fim"][0])})
    ys3 = [c for b in bs for c in (b["inicio"][1], b["fim"][1])]
    zs3 = [c for b in bs for c in (b["inicio"][2], b["fim"][2])]
    ok(len(bs) == 4 * N_TESOURA and xs3 == [0, 6000, 12000, 18000], "o 3D tem as 4 tesouras nos eixos: %d barras, x %s" % (len(bs), xs3))
    ok(bs and abs(max(ys3)) < 1 and abs(min(ys3) + 20000) < 1 and abs(min(zs3) - 6000) < 1 and abs(max(zs3) - 7600) < 1,
       "do eixo A ao C e de 6,00 a 7,60 m, como colada: y %s…%s, z %s…%s" % (round(min(ys3)) if ys3 else '-', round(max(ys3)) if ys3 else '-', round(min(zs3)) if zs3 else '-', round(max(zs3)) if zs3 else '-'))

    # o duplo clique na tesoura do eixo 4 (na implantação) abre a elevação dele
    impl = json.loads(aba.avaliar("JSON.stringify(window.montagem._quadroImplantacao())"))
    t4 = next(t for t in trels if t["atributos"]["eixo"] == "4")
    aba.avaliar("cad.tela.enquadrar([[%s, %s], [%s, %s]]); 1" % (impl["x"], impl["y"] - impl["h"], impl["x"] + impl["w"], impl["y"])); aba.drenar(0.4)
    meio = [(t4["a"][0] + t4["b"][0]) / 2, (t4["a"][1] * 0.3 + t4["b"][1] * 0.7)]
    pt = json.loads(aba.avaliar("""JSON.stringify((() => { const p = cad.tela.paraTela(%s); const r = cad.el.canvas.getBoundingClientRect(); return [p[0] + r.left, p[1] + r.top]; })())""" % json.dumps(meio)))
    for k in (1, 2):
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=pt[0], y=pt[1], button="left", clickCount=k)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=pt[0], y=pt[1], button="left", clickCount=k)
    ok(esperar(aba, "window.montagem._elevacoes().some(q => q.eixo === '4')", 15), "o duplo clique na tesoura do eixo 4 abre a elevação dele")
    aba.drenar(0.8)
    foto(aba, "_tesoura_elevacao4.png")

    # colar com a medida errada (o 2º apoio 1 m antes do eixo C) avisa
    limpar_avisos(aba)
    a2e = json.loads(aba.avaliar("JSON.stringify(window.montagem._paraPapel(window.montagem._elevacoes().find(q => q.eixo === '2'), [19000, 6000]))"))
    aba.avaliar("window.montagem.colar(); (() => { const f = cad.ferramenta; f.onPonto(%s); f.onPonto(%s); return 1; })()" % (json.dumps(a1), json.dumps(a2e)))
    aba.drenar(0.6)
    ok("ATENÇÃO" in avisos(aba) and "1000 mm" in avisos(aba), "colar com a medida diferente dos eixos avisa a diferença: %s" % avisos(aba)[:200])
    aba.avaliar("cad.desfazer(); 1"); aba.drenar(0.4)

    # lançar de novo só no eixo 2 com a marca T1 (que está nos outros): "só estas" vira o tipo T1A
    aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(q => q.eixo === '2');
      cad.selecionar([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).colado && e.atributos.quadro === q.id).map(e => e.id));
      window.montagem.tesouraDaElevacao(q); return 1; })()""")
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelectorAll('#dialogo input[type=checkbox]').length >= 4", 15)
    aba.avaliar("""(() => { document.querySelectorAll('#dialogo input[type=checkbox]').forEach(c => { c.checked = c.value === '2'; });
      const m = [...document.querySelectorAll('#dialogo input[type=text]')][0]; m.value = 'T1'; document.querySelector('#dialogo-ok').click(); return 1; })()""")
    esperar(aba, "document.querySelector('#dialogo').open && !!document.querySelector('#dialogo input[type=radio]')", 10)
    aba.avaliar("(() => { document.querySelector('#dialogo input[type=radio][value=so]').checked = true; document.querySelector('#dialogo-ok').click(); return 1; })()")
    esperar(aba, "[...cad.doc.entidades.values()].some(e => (e.atributos || {}).marca === 'T1A')", 15)
    marcas = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e => [e.atributos.eixo, e.atributos.marca]).sort())"))
    ok(marcas == [["1", "T1"], ["2", "T1A"], ["3", "T1"], ["4", "T1"]], "só o eixo 2 vira o tipo T1A; os outros continuam T1: %s" % marcas)
    # nas propriedades da T1 do eixo 3: o banzo superior novo para todas as T1 (a T1A fica)
    aba.avaliar("""(() => { const t = [...cad.doc.entidades.values()].find(e => (e.atributos || {}).elemento === 'trelica' && e.atributos.eixo === '3');
      cad.selecionar([t.id]); return 1; })()""")
    esperar(aba, "[...document.querySelectorAll('#paineis label')].some(l => l.textContent === 'Banzo superior')", 10)
    aba.avaliar("""(() => { const l = [...document.querySelectorAll('#paineis label')].find(l => l.textContent === 'Banzo superior');
      const i = l.nextElementSibling; i.value = 'U 200×75×3,0'; i.dispatchEvent(new Event('change')); return 1; })()""")
    esperar(aba, "document.querySelector('#dialogo').open && !!document.querySelector('#dialogo input[type=radio]')", 10)
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1"); aba.drenar(0.6)
    bs_ = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e => [e.atributos.eixo, e.atributos.marca, e.atributos.perfis.banzo_sup]).sort())"))
    ok([b for b in bs_ if b[1] == "T1"] and all(b[2] == "U 200×75×3,0" for b in bs_ if b[1] == "T1") and all(b[2] != "U 200×75×3,0" for b in bs_ if b[1] == "T1A"),
       "mudar o banzo de uma T1 nas propriedades muda todas as T1 (a T1A fica): %s" % bs_)

    # "Perfis…" (11/10): na Elevação 3, o banzo de baixo vira composto de U 150 com vão 150 e a boca virada em todas as
    # T1; depois as diagonais só deste eixo viram L 50,8 — e a tesoura do eixo 3 vira outro tipo (T1B: a T1A já existe)
    ok(aba.avaliar("[...document.querySelectorAll('.quadro-botao')].some(b => b.textContent === 'Perfis…')"), "a elevação tem \"Perfis…\" no título")
    aba.avaliar("(() => { const m = window.montagem; m.abrirPerfis(m._elevacoes().find(q => q.eixo === '3')); return 1; })()")
    ok(esperar(aba, "!!document.querySelector('#painel-perfis:not([hidden]) #perfis-arranjo')", 10) and aba.avaliar("cad.ferramenta.constructor.id") == "perfis-sel",
       "o painel abre com a seleção de barras ligada")
    aba.avaliar("document.querySelector('#painel-perfis [data-funcao=banzo_inf]').click(); 1"); aba.drenar(0.4)
    n_inf = aba.avaliar("window.montagem._pf.sel.size")
    ok(n_inf and "barra(s) selecionada(s)" in (aba.avaliar("document.querySelector('#perfis-sel').textContent") or ""), "\"banzo de baixo\" seleciona %s barra(s)" % n_inf)
    # o clique numa barra (a do meio da diagonal desenhada) pega só ela; Shift soma
    um = aba.avaliar("""(() => { const m = window.montagem, l = m._linhasDasBarras().find(l => { const e = cad.doc.get(l.ref); return e.atributos.desenho.barras[l.i][4] === 'diagonal'; });
      cad.ferramenta.onPonto([(l.a[0] + l.b[0]) / 2, (l.a[1] + l.b[1]) / 2], {}); return m._pf.sel.size; })()""")
    ok(um == 1, "o clique numa barra seleciona só ela (%s)" % um)
    aba.avaliar("document.querySelector('#painel-perfis [data-funcao=banzo_inf]').click(); 1"); aba.drenar(0.4)
    aba.avaliar("""(() => { const P = document.querySelector('#painel-perfis'); P.querySelector('#perfis-perfil').value = 'U 150×50×3,0';
      const a = P.querySelector('#perfis-arranjo'); a.value = 'composto'; a.dispatchEvent(new Event('change'));
      const v = P.querySelector('#perfis-vao'); v.value = '150'; v.dispatchEvent(new Event('input')); P.querySelector('#perfis-boca').value = '1'; return 1; })()""")
    ok(aba.avaliar("!!document.querySelector('#painel-perfis .perfis-croqui svg polyline')") and "150" in (aba.avaliar("document.querySelector('#painel-perfis .perfis-croqui').textContent") or ""),
       "o croqui do composto aparece com o vão (150)")
    aba.avaliar("document.querySelector('#perfis-aplicar-todas').click(); 1")
    esperar(aba, "!cad._salvando && [...cad.doc.entidades.values()].some(e => (e.atributos || {}).elemento === 'trelica' && e.atributos.desenho.barras.some(b => b[5] === 'U 150×50×3,0'))", 15)
    inf = json.loads(aba.avaliar("""JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e =>
      [e.atributos.eixo, e.atributos.marca, e.atributos.desenho.barras.filter(b => b[4] === 'banzo_inf').map(b => [b[5], b[6], b[7], b[8]])]).sort())"""))
    ok(all(all(b == ["U 150×50×3,0", "composto", 150, 1] for b in t[2]) for t in inf if t[1] == "T1")
       and all(all(b[0] != "U 150×50×3,0" for b in t[2]) for t in inf if t[1] == "T1A"),
       "\"Aplicar a todas\": o banzo de baixo de todas as T1 vira composto U 150, vão 150, boca virada; a T1A fica: %s" % [(t[0], t[1], t[2][:1]) for t in inf])
    aba.avaliar("document.querySelector('#painel-perfis [data-funcao=diagonal]').click(); 1"); aba.drenar(0.4)
    aba.avaliar("""(() => { const P = document.querySelector('#painel-perfis'); P.querySelector('#perfis-perfil').value = 'L 50,8×4,76'; return 1; })()""")
    aba.avaliar("document.querySelector('#perfis-aplicar-so').click(); 1")
    esperar(aba, "[...cad.doc.entidades.values()].some(e => (e.atributos || {}).marca === 'T1B')", 15)
    marcas = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e => [e.atributos.eixo, e.atributos.marca, e.atributos.desenho.barras.filter(b => b[4] === 'diagonal').every(b => b[5] === 'L 50,8×4,76')]).sort())"))
    ok(marcas == [["1", "T1", False], ["2", "T1A", False], ["3", "T1B", True], ["4", "T1", False]],
       "\"Só neste eixo\": as diagonais do eixo 3 mudam e ele vira T1B; os outros ficam: %s" % marcas)
    ok(aba.avaliar("[...cad.doc.entidades.values()].some(e => (e.atributos || {}).rotulo_de && e.texto === 'T1B')"), "o rótulo da implantação mostra T1B")
    t0 = time.time()
    while time.time() - t0 < 40 and not any(b.get("perfil") == "U 150×50×3,0" for b in _barras()):
        aba.drenar(0.6)
    bs = _barras()
    duplas = [b for b in bs if b.get("perfil") == "U 150×50×3,0" and (b.get("atributos") or {}).get("secao_dupla") == "composto"]
    ok(duplas and len(duplas) % 2 == 0, "o 3D acompanha: %d barras de U 150 em composto" % len(duplas))
    # etapa 2: a legenda pinta cada perfil com uma cor, clicar nela seleciona as barras dele; a tabela dá kg por tesoura
    leg = json.loads(aba.avaliar("JSON.stringify([...document.querySelectorAll('#perfis-legenda li')].map(l => [l.dataset.chave, +l.querySelector('.perfis-n').textContent]))") or "[]")
    ok(any(k.startswith("U 150×50×3,0|composto") for k, _n in leg) and any(k.startswith("L 50,8×4,76|") for k, _n in leg),
       "a legenda tem o composto U 150 e a L 50,8 aplicados: %s" % leg)
    k150 = next((k for k, _n in leg if k.startswith("U 150×50×3,0|composto")), "")
    n150 = next((n for k, n in leg if k == k150), 0)
    aba.avaliar("document.querySelector('#perfis-legenda li[data-chave=\"%s\"]').click(); 1" % k150); aba.drenar(0.4)
    ok(aba.avaliar("window.montagem._pf.sel.size") == n150, "clicar no perfil da legenda seleciona as %s barra(s) dele" % n150)
    resumo = aba.avaliar("[...document.querySelectorAll('.perfis-tabela summary')].map(s => s.textContent).join(' | ')") or ""
    ok("kg por tesoura" in resumo and "na obra" in resumo, "a tabela da tesoura dá o peso: %s" % resumo)
    aba.avaliar("(() => { const c = document.querySelector('#perfis-pintar'); c.checked = false; c.dispatchEvent(new Event('change')); return 1; })()"); aba.drenar(0.2)
    ok(aba.avaliar("window.montagem._pf.pintar === false"), "\"Pintar por perfil\" desliga")
    aba.avaliar("(() => { const c = document.querySelector('#perfis-pintar'); c.checked = true; c.dispatchEvent(new Event('change')); return 1; })()"); aba.drenar(0.2)
    foto(aba, "_tesoura_perfis.png")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.3)
    ok(aba.avaliar("document.querySelector('#painel-perfis').hidden && !window.montagem._pf"), "Esc fecha o painel")

    # etapa 3: a legenda de cores colada na Elevação 3 (como a folha "PERFIS" do projeto) sugere: o banzo de baixo em
    # vermelho = "PERFIL COMPOSTO UE100…", as diagonais em verde = "PERFIL SIMPLES UE127…"; o painel mostra as diferentes,
    # preenche os campos ao selecionar e "Aceitar" grava em todas as T1B
    aba.avaliar("""(async () => {
      const d = await import('/cad/nucleo/desenho2d.js'), c = await import('/cad/nucleo/comandos.js'), m = window.montagem;
      const q = m._elevacoes().find(q => q.eixo === '3');
      m._pf = { q, sel: new Set() };
      const at = (cor) => ({ quadro: q.id, colado: 'legenda-teste', cor });
      const P = (u, z) => m._paraPapel(q, [u, z]);
      const novos = [];
      for (const l of m._linhasDasBarras()) {
        const papel = cad.doc.get(l.ref).atributos.desenho.barras[l.i][4];
        const cor = papel === 'banzo_inf' ? '#ff0000' : papel === 'diagonal' ? '#00ff00' : null;
        if (cor) novos.push(d.criar({ tipo: 'linha', camada: '0', a: [...l.a], b: [...l.b], atributos: at(cor) }));
      }
      const T = (u, z, texto, cor) => d.criar({ tipo: 'texto', camada: '0', posicao: P(u, z), texto, altura: 2.5, atributos: cor ? at(cor) : { quadro: q.id, colado: 'legenda-teste' } });
      novos.push(T(2000, 9400, 'BANZOS'), T(2000, 9000, 'PERFIL COMPOSTO UE100x50x17x2.25mm', '#ff0000'),
        T(12000, 9400, 'MONTANTES E DIAGONAIS'), T(12000, 9000, 'PERFIL SIMPLES UE127x50x17x2.00mm', '#00ff00'));
      m._pf = null;
      cad.executar(new c.ComandoAdicionar(novos, 'legenda de teste'));
      await m.abrirPerfis(q); window.__leg = novos.length; })(); 1""")
    esperar(aba, "!!window.__leg && !!document.querySelector('#perfis-ler-legenda')", 15)
    aba.avaliar("document.querySelector('#perfis-ler-legenda').click(); 1"); aba.drenar(0.6)
    dif = json.loads(aba.avaliar("JSON.stringify(window.montagem._diferentesDaSugestao().map(d => [d.b[4], d.sug.perfil, d.sug.arranjo]))") or "[]")
    ok(dif and all((f == "banzo_inf" and p_ == "Ue 100×50×17×2,25" and a_ == "composto") or (f == "diagonal" and p_ == "Ue 127×50×17×2,00" and a_ == "") for f, p_, a_ in dif)
       and {f for f, _p, _a in dif} == {"banzo_inf", "diagonal"},
       "a legenda colada sugere Ue 100 composto no banzo de baixo e Ue 127 nas diagonais: %s" % dif[:4])
    ok("diferente(s)" in (aba.avaliar("document.querySelector('#perfis-sugestao').textContent") or ""), "o painel diz quantas a legenda muda")
    aba.avaliar("document.querySelector('#painel-perfis [data-funcao=banzo_inf]').click(); 1"); aba.drenar(0.5)
    ok(aba.avaliar("document.querySelector('#perfis-perfil').value") == "Ue 100×50×17×2,25" and aba.avaliar("document.querySelector('#perfis-arranjo').value") == "composto"
       and aba.avaliar("!!document.querySelector('#perfis-sugerido')"), "ao selecionar o banzo de baixo, o painel vem preenchido pela legenda")
    aba.avaliar("document.querySelector('#perfis-aceitar-legenda').click(); 1")
    esperar(aba, "window.montagem._pf && window.montagem._pf.sugestao && window.montagem._diferentesDaSugestao().length === 0", 15)
    t1b = json.loads(aba.avaliar("""JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && e.atributos.marca === 'T1B')
      .flatMap(e => e.atributos.desenho.barras.filter(b => b[4] === 'banzo_inf' || b[4] === 'diagonal').map(b => [b[4], b[5], b[6] || ''])))"""))
    ok(t1b and all(b[1:] == (["Ue 100×50×17×2,25", "composto"] if b[0] == "banzo_inf" else ["Ue 127×50×17×2,00", ""]) for b in t1b),
       "\"Aceitar\" grava a legenda na T1B e não sobra diferença: %s" % t1b[:3])
    foto(aba, "_tesoura_legenda.png")
    aba.avaliar("window.montagem.enquadrar(); 1"); aba.drenar(0.8)
    foto(aba, "_tesoura_folha.png")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + ("" if not erros else ": " + str(erros[:2])))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
