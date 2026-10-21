# -*- coding: utf-8 -*-
"""A Montagem ligada ao 3D na tela 2D + 3D (21/10/2026, Posto V2 — o usuário: "o 3D só vincula ao trecho; tem como
aparecer o trecho e também o corte?" e "quando clico nela na tela de montagem aparece um quadro em branco").

Com a Montagem aberta no lado 2D: escolher a TESOURA 1 no 3D mostra o quadrinho com o trecho na Implantação e o corte
na Elevação 2 (onde ela está), abre no corte com as linhas dela marcadas e a região laranja em cima delas (antes: a
caixa da planta do cliente, um lugar vazio); "Trecho na implantação" enquadra o trecho no quadro da Implantação; limpar
a seleção do 3D tira o quadrinho. Do 2D para o 3D: a linha do corte seleciona a peça dela no 3D (pelo id) e a caixa na
Implantação seleciona as peças em planta. E o desempenho: com zoom num quadro, os títulos dos quadros fora da vista
ficam escondidos (não são reposicionados a cada quadro de tela — no Posto V2, 56–75 ms por quadro)."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_montagem_3d_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra", "tipo": "recebido", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None,
           "niveis": [{"nome": "BASE", "z": 0.0}, {"nome": "BANZO INFERIOR", "z": 6000.0}],
           "eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6000.0}, {"nome": "3", "pos": 12000.0}],
                     "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 10000.0}], "extras": [], "z_base": 0.0, "origem": "usuario"}},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"), ensure_ascii=False)
ents, n = [], 0


def barra(a, b, papel, peca="", planta="", perfil="U 100×40×2,25 (FF)", camada="Treliças"):
    global n
    n += 1
    o = {"peca": peca, "planta": planta} if peca else {}
    ents.append({"id": "b%d" % n, "tipo": "barra", "nome": perfil, "camada": camada, "perfil": perfil, "papel": papel, "rotacao": 0.0,
                 "inicio": list(a), "fim": list(b), "atributos": {"origem": o}})


# a TESOURA 1 no eixo 2 (x = 6 m), a TESOURA 2 no eixo 3, os pilares
for x, peca, planta in ((6000.0, "TESOURA 1#1", "TESOURA 1"), (12000.0, "TESOURA 2#2", "TESOURA 2")):
    barra((x, 0, 6000), (x, 10000, 6000), "banzo", peca, planta)
    barra((x, 0, 7000), (x, 10000, 7000), "banzo", peca, planta)
    for y in (0.0, 5000.0, 10000.0):
        barra((x, y, 6000), (x, y, 7000), "montante", peca, planta, perfil='L 1"×1/8"')
for p in ((0.0, 0.0), (6000.0, 0.0), (12000.0, 0.0), (6000.0, 10000.0), (12000.0, 10000.0)):
    barra((p[0], p[1], 0), (p[0], p[1], 6000), "pilar", perfil="Ue 200×70×20×2,65", camada="Pilares")
json.dump({"nome": "Modelo", "unidade": "mm", "entidades": ents, "camadas": [], "materiais": [], "metadados": {}},
          open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"nome": "Planta de lançamento", "unidade": "mm", "escala": 100,
           "camadas": {"ARQ": {"nome": "ARQ", "cor": "#888888", "visivel": True, "bloqueada": True}},
           "entidades": [{"id": "a1", "tipo": "linha", "camada": "ARQ", "a": [0, 0], "b": [12000, 0]}],
           "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "planta-de-lançamento.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mont3d_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


F2 = "document.getElementById('f2d').contentWindow"
F3 = "document.getElementById('f3d').contentWindow"
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    # 1. a Montagem com as elevações do 3D (como no Posto), gravada
    aba.navegar(base + "/cad?projeto=obra&desenho=planta-de-lançamento", limite=60)
    esperar(aba, "document.body.dataset.pronto === '1' && !!window.montagem", 40)
    aba.avaliar("(async () => { await window.montagem.ir('montagem'); return 1; })()")
    esperar(aba, "window.cad.nomeDesenho === 'montagem'", 20)
    aba.avaliar("(async () => { await window.montagem.garantirImplantacao(); await window.montagem.todasAsElevacoes(); return 1; })()")
    aba.avaliar("(async () => { await window.montagem._gravarJa(); await window.cad.salvar({ avisar: false }); return 1; })()")
    esperar(aba, "!window.montagem._timer && !window.cad._editado", 15)
    nq = aba.avaliar("window.montagem._elevacoes().length")
    ok(nq == 5, f"a Montagem com as 5 elevações do 3D ({nq})")

    # 2. a tela 2D + 3D com a Montagem no lado 2D
    aba.navegar(base + "/dividida?projeto=obra&vista=ambos&desenho=montagem", limite=60)
    ok(esperar(aba, f"(() => {{ try {{ const w = {F2}; return w.document.body.dataset.pronto === '1' && w.cad && w.cad.nomeDesenho === 'montagem' && !!w.montagem.m; }} catch (e) {{ return false; }} }})()", 60),
       "o 2D abre na Montagem")
    ok(esperar(aba, f"(() => {{ try {{ const w = {F3}; return !!(w.visor && w.visor.fichas); }} catch (e) {{ return false; }} }})()", 120), "o 3D (modo ver) abre")
    aba.drenar(1.0)

    # 3. o 3D escolhe a TESOURA 1 (como o visor avisa: ids e caixa em planta)
    aba.avaliar(f"""(() => {{ const w = {F3}; const v = w.visor; const o = v.cabecalho.origem; const idx = [];
        v.fichas.forEach((f, i) => {{ if (f.pc && f.pc.startsWith('TESOURA 1#')) idx.push(i); }});
        v.selecionarVarias(idx, true); return idx.length; }})()""")
    # o visor avisa a seleção do clique; aqui a mensagem dele, como ele a monta
    aba.avaliar(f"""(() => {{ const w = {F3}; const v = w.visor; const o = v.cabecalho.origem; const ids = []; let x0=1e18,y0=1e18,x1=-1e18,y1=-1e18;
        v.fichas.forEach((f) => {{ if (f.pc && f.pc.startsWith('TESOURA 1#')) {{ ids.push(f.id); const b = f.b || [f.x[0],f.x[1],f.x[2],f.x[0],f.x[1],f.x[2]];
          x0=Math.min(x0,b[0]+o[0]); y0=Math.min(y0,b[1]+o[1]); x1=Math.max(x1,b[3]+o[0]); y1=Math.max(y1,b[4]+o[1]); }} }});
        w.__msg = {{ metalica: 'sel3d', n: ids.length, caixa: [[x0,y0],[x1,y1]], nomes: ['TESOURA 1'], pecas: ['TESOURA 1#1'],
          marcas: {{ ids, posicoes: [], conjuntos: [], origem2d: [], pm: [] }} }};
        w.eval('parent.postMessage(window.__msg, location.origin)'); return ids.length; }})()""")
    ok(esperar(aba, f"!!{F2}.document.getElementById('ligacao-3d')", 10), "o quadrinho da ligação aparece no 2D")
    chip = aba.avaliar(f"{F2}.document.getElementById('ligacao-3d').textContent")
    ok("TESOURA 1" in (chip or "") and "Trecho na implantação" in chip and "Corte: Elevação 2" in chip, f"o quadrinho: o nome, o trecho e o corte da Elevação 2 ({chip!r})")
    ativo = aba.avaliar(f"{F2}.document.querySelector('#ligacao-3d button.on')?.textContent")
    ok(ativo == "Corte: Elevação 2", f"abre no corte ({ativo})")
    # a região laranja e a seleção caem em cima das linhas do corte da TESOURA 1, dentro do quadro da Elevação 2
    r = aba.avaliar(f"""(() => {{ const w = {F2}; const M = w.montagem, t = w.cad.tela; const q = M._elevacoes().find(x => x.eixo === '2');
        const c = t.regiao; if (!c) return null; const dentro = w.cad.doc.naRegiao(c).filter(e => (e.atributos||{{}}).quadro === q.id && (e.atributos||{{}}).peca === 'TESOURA 1');
        const sel = [...t.selecao].map(id => w.cad.doc.get(id)).filter(Boolean);
        return [dentro.length, sel.length, sel.every(e => (e.atributos||{{}}).quadro === q.id && (e.atributos||{{}}).id3d)]; }})()""")
    ok(r and r[0] >= 3 and r[1] >= 3 and r[2], f"a região e a seleção nas linhas da TESOURA 1 no corte ({r})")
    vis = aba.avaliar(f"""(() => {{ const w = {F2}; const t = w.cad.tela; const c = t.regiao; const a = t.paraTela(c[0]), b = t.paraTela(c[1]);
        return [Math.min(a[0], b[0]) >= -2, Math.max(a[0], b[0]) <= t.largura + 2, Math.min(a[1], b[1]) >= -2, Math.max(a[1], b[1]) <= t.altura + 2]; }})()""")
    ok(vis and all(vis), f"o corte enquadrado à vista ({vis})")

    # 4. "Trecho na implantação": a região no quadro da Implantação, no lugar da TESOURA 1 (x = 6 m)
    aba.avaliar(f"(() => {{ const b = [...{F2}.document.querySelectorAll('#ligacao-3d button')].find(x => x.textContent === 'Trecho na implantação'); b.click(); return 1; }})()")
    r = aba.avaliar(f"""(() => {{ const w = {F2}; const M = w.montagem, t = w.cad.tela; const qi = M._quadroImplantacao(); const c = t.regiao; if (!c) return null;
        const meio = [(c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2]; const real = M._paraReal(qi, meio);
        const dentro = meio[0] >= qi.x && meio[0] <= qi.x + qi.w && meio[1] <= qi.y && meio[1] >= qi.y - qi.h;
        return [dentro, Math.round(real[0]), Math.round(real[1])]; }})()""")
    ok(r and r[0] and abs(r[1] - 6000) < 300 and abs(r[2] - 5000) < 800, f"o trecho na Implantação, em x = 6 m ({r})")
    # a peça desenhada em planta no trecho (não só a caixa vazia): as barras da TESOURA 1, em laranja
    des = esperar(aba, f"(() => {{ const w = {F2}; w.cad.tela.desenhar(); return (w.montagem._ligacao3d || {{}}).desenhadas || 0; }})()", 10)
    ok(des and des >= 5, f"a TESOURA 1 desenhada em planta no trecho da Implantação ({des} peça(s))")

    # 5. do 2D para o 3D: uma linha do corte da TESOURA 2 seleciona a peça dela no 3D
    aba.avaliar(f"""(() => {{ const w = {F2}; const e = [...w.cad.doc.entidades.values()].find(x => (x.atributos||{{}}).peca === 'TESOURA 2' && (x.atributos||{{}}).id3d && x.tipo === 'linha');
        w.cad.selecionar([e.id]); return e.atributos.id3d; }})()""")
    sel3 = esperar(aba, f"(() => {{ const w = {F3}; const v = w.visor; return [...v.selecaoVarias].map(i => v.fichas[i].pc).filter(Boolean).join(','); }})()", 10)
    ok(sel3 and all(s.startswith("TESOURA 2#") for s in sel3.split(",")), f"a linha do corte seleciona a peça dela no 3D ({sel3})")
    # e uma caixa na Implantação em volta do eixo 3 seleciona as peças dele, em planta
    aba.avaliar(f"""(() => {{ const w = {F2}; const M = w.montagem; const qi = M._quadroImplantacao(); const a = M._paraPapel(qi, [11500, 2000]), b = M._paraPapel(qi, [12500, 8000]);
        const e = [...w.cad.doc.entidades.values()].find(x => (x.atributos||{{}}).quadro === qi.id && (x.atributos||{{}}).eixo === '3' && x.tipo === 'linha');
        w.cad.selecionar([e.id]); return 1; }})()""")
    sel3b = esperar(aba, f"(() => {{ const w = {F3}; const v = w.visor; const pcs = [...v.selecaoVarias].map(i => v.fichas[i].pc || 'pilar'); return pcs.length && pcs.some(p => p.startsWith('TESOURA 2#')) ? pcs.length : 0; }})()", 10)
    ok(sel3b, f"a linha do eixo 3 na Implantação seleciona no 3D as peças em planta dela ({sel3b})")

    # 6. limpar a seleção do 3D tira o quadrinho
    aba.avaliar(f"(() => {{ const w = {F3}; w.eval(\"parent.postMessage({{ metalica: 'sel3d', n: 0, caixa: null, nomes: [], pecas: [], marcas: {{}} }}, location.origin)\"); return 1; }})()")
    ok(esperar(aba, f"!{F2}.document.getElementById('ligacao-3d') && !{F2}.cad.tela.regiao", 8), "sem seleção no 3D, o quadrinho e a região saem")

    # 7. o desempenho: com zoom numa elevação, os títulos dos quadros fora da vista ficam escondidos
    r = aba.avaliar(f"""(() => {{ const w = {F2}; const M = w.montagem; const q = M._elevacoes().find(x => x.eixo === '2');
        w.cad.tela.enquadrar([[q.x, q.y - q.h * 0.3], [q.x + q.w * 0.3, q.y]]); w.cad.tela.desenhar();
        const W = w.cad.tela.largura, H = w.cad.tela.altura; let fora = 0, mostrando = 0;
        for (const x of M.m.quadros) {{ const a = w.cad.tela.paraTela([x.x, x.y]), b = w.cad.tela.paraTela([x.x + x.w, x.y - x.h]);
          if (a[0] > W + 40 || a[1] > H + 40 || b[0] < -40 || b[1] < -40) {{ fora++; const c = M.camada.querySelector(`[data-quadro="${{x.id}}"]`);
            if (c && w.getComputedStyle(c).display !== 'none') mostrando++; }} }}
        return [fora, mostrando]; }})()""")
    ok(r and r[0] >= 3 and r[1] == 0, f"com zoom, os títulos dos quadros fora da vista somem da tela (display none: o display do título vencia o hidden e eles ficavam parados na frente do desenho) ({r})")

    erros = [c for c in aba.console if c[0] in ("excecao", "error")]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
