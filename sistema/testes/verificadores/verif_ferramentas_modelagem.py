# -*- coding: utf-8 -*-
"""Modelagem de barra no editor 3D (F6 e F7 do levantamento de 14/10/2026):
  F6 ponto de inserção da Barra — a face de baixo na linha (a terça sobre o banzo) e a face esquerda na linha;
  F7 Estender / aparar até outra barra — até a face do pilar W (a mesa), até o eixo (Shift), com folga, e aparando a
     viga que passava; Dividir — em dois pelo meio e em /3, o corte e o furo indo para o pedaço certo; Unir peças — as
     duas metades voltam a uma barra, com o corte da ponta e o furo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento, Solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_modelagem_")
PASTA = os.path.join(DADOS, "mod")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Modelagem", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
W = "W 250×32,7"                           # d 258, bf 146
doc.add(Barra(nome="pilar", inicio=(3000.0, 0.0, -1000.0), fim=(3000.0, 0.0, 2000.0), perfil=W, rotacao=0.0, papel="pilar"))
doc.add(Barra(nome="viga", inicio=(0.0, 0.0, 0.0), fim=(2500.0, 0.0, 0.0), perfil=W, rotacao=0.0, papel="viga",
              atributos={"marcas": {"posicao": "P7"}}))
doc.add(Barra(nome="longa", inicio=(0.0, 3000.0, 0.0), fim=(4000.0, 3000.0, 0.0), perfil=W, rotacao=0.0, papel="viga",
              cortes_fim=[{"normal": [-0.7071068, 0.7071068, 0.0], "ponto": [0.0, 0.0, 0.0]}]))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_modelagem_")
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
    base = f"http://localhost:{PORTA}"
    aba.navegar(base + "/editor?projeto=mod", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 3 && editor.ferramentas"
                                                    " && editor.ferramentas.get('estender') && editor.ferramentas.get('dividir') && editor.cena.perfil(%s))" % json.dumps(W)):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ID = jsj("const l = [...editor.documento.entidades.values()]; const q = n => (l.find(e => e.nome === n) || {}).id;"
             " return { pilar: q('pilar'), viga: q('viga'), longa: q('longa') };")
    ok(js("!!(document.querySelector('[data-id=\"estender\"]') && document.querySelector('[data-id=\"dividir\"]'))"),
       "Estender e Dividir estão na barra de ferramentas")

    # ---- F6: ponto de inserção
    f6 = jsj("""const ed = editor; ed.ativarFerramenta('barra'); const F = ed.ativa.constructor;
      ed.ativa.perfilAtivo = 'W 250×32,7';
      F.insercao = { altura: 'baixo', largura: 'eixo', da: 0, dl: 0 };
      ed.ativa.criar([0, -2000, 129], [2000, -2000, 129]);
      const b1 = [...ed.documento.entidades.values()].filter(e => e.tipo === 'barra').pop();
      ed.ativa.reiniciar();
      F.insercao = { altura: 'eixo', largura: 'esquerda', da: 0, dl: 0 };
      ed.ativa.criar([0, -4000, 0], [2000, -4000, 0]);
      const b2 = [...ed.documento.entidades.values()].filter(e => e.tipo === 'barra').pop();
      ed.ativa.reiniciar();
      F.insercao = { altura: 'cima', largura: 'eixo', da: 20, dl: 0 };
      ed.ativa.criar([0, -6000, 0], [2000, -6000, 0]);
      const b3 = [...ed.documento.entidades.values()].filter(e => e.tipo === 'barra').pop();
      F.insercao = { altura: 'eixo', largura: 'eixo', da: 0, dl: 0 };
      ed.ativa.reiniciar(); ed.ativarFerramenta('selecionar');
      return [b1.inicio, b2.inicio, b3.inicio];""")
    ok(f6 and abs(f6[0][2] - 258) < 0.01, f"F6: face de baixo na linha (z 129) → eixo a +129 (z 258): {f6 and f6[0]}")
    ok(f6 and abs(f6[1][1] - (-4000 - 73)) < 0.01, f"F6: face esquerda na linha → eixo a 73 para a direita (y −4073): {f6 and f6[1]}")
    ok(f6 and abs(f6[2][2] - (-129 + 20)) < 0.01, f"F6: face de cima na linha com 20 para cima (z −109): {f6 and f6[2]}")

    # ---- F7: Estender até a face do pilar, até o eixo (Shift), com folga; aparar a que passava
    def estender(id_, ponto, alvo, shift=False, folga=0):
        return jsj(f"""const ed = editor; ed.ativarFerramenta('estender'); const f = ed.ativa; f.constructor.folga = {folga};
          const doc = ed.documento;
          f._barraSob = () => ({{ e: doc.get('{id_}'), ponto: {json.dumps(ponto)} }}); f.onPonto({{ tela: [0, 0] }}, {{}});
          f._barraSob = () => ({{ e: doc.get('{alvo}'), ponto: [3000, 0, 0] }}); f.onPonto({{ tela: [0, 0] }}, {{ shiftKey: {str(shift).lower()} }});
          const v = doc.get('{id_}'); f.constructor.folga = 0; return {{ fim: v.fim.map(x => Math.round(x * 10) / 10), conf: !!(v.atributos || {{}}).marca_a_conferir }};""")
    r = estender(ID["viga"], [2400, 0, 0], ID["pilar"])
    ok(r and r["fim"][0] == 2871 and r["conf"], f"F7: a viga foi até a face do pilar (x 3000 − 129 = 2871) e a marca ficou a conferir: {r}")
    r = estender(ID["viga"], [2400, 0, 0], ID["pilar"], shift=True)
    ok(r and r["fim"][0] == 3000, f"F7: com Shift, até o eixo do pilar (x 3000): {r}")
    r = estender(ID["viga"], [2400, 0, 0], ID["pilar"], folga=10)
    ok(r and r["fim"][0] == 2861, f"F7: com folga de 10, para 10 antes da face (x 2861): {r}")
    js(f"editor.documento.alterar('{ID['viga']}', {{ fim: [3500, 0, 0] }}); 1")
    r = estender(ID["viga"], [3400, 0, 0], ID["pilar"])
    ok(r and r["fim"][0] == 2871, f"F7: a viga que passava do pilar foi aparada na face (x 2871): {r}")
    js("editor.ativarFerramenta('selecionar'); 1")

    # ---- F7: Dividir a "longa" (com corte no fim e um furo a 3000) em duas pelo meio; depois /3; Unir
    furo = jsj(f"""const vs = []; for (const z of [139, 120]) for (const [x, y] of [[2990, 3030], [3010, 3030], [3010, 3050], [2990, 3050]]) vs.push([x, y, z]);
      const m = editor.documento.add({{ tipo: 'solido', nome: 'FURO', camada: 'Furos', vertices: vs,
        faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [],
        atributos: {{ tipo_ifc: 'IfcOpeningElement', exportar: false, furo: {{ d: 13.5, ponto: [3000, 3040, 129], eixo: [0, 0, -1], profundidade: 9.1, peca: '{ID['longa']}' }} }} }});
      return m.id;""")
    dv = jsj(f"""const ed = editor; ed.ativarFerramenta('dividir'); const f = ed.ativa; const doc = ed.documento;
      f.dividir(doc.get('{ID['longa']}'), [2000]);
      const bs = [...doc.entidades.values()].filter(e => e.tipo === 'barra' && Math.abs(e.inicio[1] - 3000) < 1);
      const m = doc.get('{furo}');
      return bs.map(b => ({{ id: b.id, i: b.inicio[0], f: b.fim[0], ci: (b.cortes_inicio || []).length, cf: (b.cortes_fim || []).length }}))
               .concat([{{ furoNa: m.atributos.furo.peca }}]);""")
    pedacos = [x for x in dv if "id" in x]
    furo_na = dv[-1]["furoNa"]
    ok(len(pedacos) == 2 and sorted((p["i"], p["f"]) for p in pedacos) == [(0, 2000), (2000, 4000)],
       f"F7: dividida em 2000 + 2000: {[(p['i'], p['f']) for p in pedacos]}")
    seg = next(p for p in pedacos if p["i"] == 2000)
    ok(seg["cf"] == 1 and next(p for p in pedacos if p["i"] == 0)["cf"] == 0 and furo_na == seg["id"],
       f"F7: o corte do fim e o furo (x 3000) ficaram no pedaço de 2000 a 4000: {pedacos} furo em {furo_na}")
    un = jsj(f"""const ed = editor; ed.ativarFerramenta('selecionar'); const doc = ed.documento;
      const ids = [...doc.entidades.values()].filter(e => e.tipo === 'barra' && Math.abs(e.inicio[1] - 3000) < 1).map(e => e.id);
      ed.selecao.definir(ids); ed.juntarSelecao();
      const bs = [...doc.entidades.values()].filter(e => e.tipo === 'barra' && Math.abs(e.inicio[1] - 3000) < 1);
      return {{ n: bs.length, i: bs[0].inicio[0], f: bs[0].fim[0], cf: (bs[0].cortes_fim || []).length, furo: doc.get('{furo}').atributos.furo.peca === bs[0].id }};""")
    ok(un and un["n"] == 1 and un["i"] == 0 and un["f"] == 4000 and un["cf"] == 1 and un["furo"],
       f"F7: Unir devolveu uma barra de 0 a 4000, com o corte do fim e o furo: {un}")
    d3 = jsj("""const ed = editor; ed.ativarFerramenta('dividir'); const f = ed.ativa; const doc = ed.documento;
      const b = [...doc.entidades.values()].find(e => e.tipo === 'barra' && Math.abs(e.inicio[1] - 3000) < 1);
      f.sob = { e: b, ponto: b.inicio }; f.onValor('/3');
      return [...doc.entidades.values()].filter(e => e.tipo === 'barra' && Math.abs(e.inicio[1] - 3000) < 1).map(e => Math.round(Math.hypot(e.fim[0] - e.inicio[0], e.fim[1] - e.inicio[1]))).sort((a, b) => a - b);""")
    ok(d3 == [1333, 1333, 1333], f"F7: /3 divide em três partes iguais: {d3}")
    js("editor.ativarFerramenta('selecionar'); 1")
    erros("F6 e F7")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
