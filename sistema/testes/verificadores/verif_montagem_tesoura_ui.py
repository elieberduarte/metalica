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
