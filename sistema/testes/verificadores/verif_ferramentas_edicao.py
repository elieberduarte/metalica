# -*- coding: utf-8 -*-
"""As ferramentas de edição do editor 3D (Mover, Copiar, Girar, Escalar, Empurrar/Puxar, Seção) e os defeitos D1–D8
do levantamento "Ferramentas-que-faltam-editor-3D" (14/10/2026), com o teclado de verdade e as ferramentas no editor:
  D1 Girar gira os cortes das pontas da barra junto;
  D2 Escalar e Empurrar/Puxar deixam a peça marcada com `marca_a_conferir` (a cópia idêntica mantém a marca);
  D3 Mover/Girar/Copiar levam o marcador de furo da barra e os pontos gravados do parafuso e da cota;
  D4 a peça em camada bloqueada não anda (Mover) e o aviso diz isso;
  D5 → trava X e ← trava Y, na ferramenta e no núcleo;
  D8 o snap perpendicular é gerado; a cota escalada refaz o texto; a área da chapa desconta o oblongo."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento, Solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ferredit_")
PASTA = os.path.join(DADOS, "edic")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Edição", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
W = "W 250×32,7"
# a viga com corte no ângulo na ponta do fim (plano de normal +x inclinado 45° em xy) e marca de produção
viga = Barra(nome="viga", inicio=(0.0, 0.0, 0.0), fim=(4000.0, 0.0, 0.0), perfil=W, rotacao=0.0, papel="viga",
             cortes_fim=[{"normal": [-0.7071068, 0.7071068, 0.0], "ponto": [0.0, 0.0, 0.0]}],
             atributos={"marcas": {"posicao": "P1", "conjunto": "V1"}})
doc.add(viga)
# o marcador de furo da viga, na mesa de cima
vf = [(x, y, z) for z in (139.0, 120.0) for (x, y) in ((1990.0, 30.0), (2010.0, 30.0), (2010.0, 50.0), (1990.0, 50.0))]
ff = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
doc.add(Solido(nome="FURO Ø13,5", camada="Furos", vertices=vf, faces=ff,
               atributos={"tipo_ifc": "IfcOpeningElement", "exportar": False,
                          "furo": {"d": 13.5, "ponto": [2000.0, 40.0, 129.0], "eixo": [0.0, 0.0, -1.0], "profundidade": 9.1, "peca": viga.id}}))
# um parafuso (com o registro de onde está) e uma cota
doc.add(Solido(nome="BOLT (A325) 12x30", camada="Parafusos", vertices=vf, faces=ff,
               atributos={"tipo_ifc": "IfcMechanicalFastener", "parafuso": {"d": 12, "L": 30, "ponto": [1000.0, 40.0, 129.0], "eixo": [0.0, 0.0, -1.0]}}))
cv = [(0.0, -300.0, 0.0), (1000.0, -300.0, 0.0), (0.0, -400.0, 0.0), (1000.0, -400.0, 0.0)]
doc.add(Solido(nome="1000 mm", camada="Referência", vertices=cv, faces=[], arestas_vivas=[[0, 2], [1, 3], [2, 3]],
               atributos={"tipo": "cota", "exportar": False,
                          "cota": {"a": [0.0, -300.0, 0.0], "b": [1000.0, -300.0, 0.0], "deslocamento": -100.0, "texto": "1.000 mm",
                                   "normal": [0.0, 0.0, 1.0], "lado": [0.0, -1.0, 0.0]}}))
# a chapa na camada bloqueada
doc.add(Solido(nome="CHAPA TRAVADA", camada="Travada", vertices=[(x + 3000, y + 1000, z) for (x, y, z) in vf], faces=ff,
               atributos={"tipo_ifc": "IfcPlate"}))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ferredit_")
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
    aba.navegar(base + "/editor?projeto=edic", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 5 && editor.ferramentas"
                                                    " && editor.ferramentas.get('mover') && editor.cena.perfil(%s))" % json.dumps(W)):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def tecla(k, mods=0):
        kc = {"Escape": 27, "Enter": 13, "ArrowLeft": 37, "ArrowRight": 39, "ArrowUp": 38, "ArrowDown": 40, "Control": 17}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        p = dict(key=k, code=k, windowsVirtualKeyCode=kc, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", **p, **({"text": k} if len(k) == 1 else {}))
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", **p)
        aba.drenar(0.08)
    def digitar(t):
        for ch in t: tecla(ch)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ID = jsj("const l = [...editor.documento.entidades.values()]; const q = n => (l.find(e => e.nome === n) || {}).id;"
             " return { viga: q('viga'), furo: q('FURO Ø13,5'), paraf: q('BOLT (A325) 12x30'), cota: q('1000 mm'), trav: q('CHAPA TRAVADA') };")
    js("editor.documento.camadas.set('Travada', { nome: 'Travada', cor: '#8a94a6', visivel: true, bloqueada: true }); 1")
    PEGA = "const e = editor.documento.get(%s); return e;"
    def ent(k): return jsj(PEGA % json.dumps(ID[k]))
    # o primeiro clique da ferramenta (o ponto-base) sem depender de onde a peça cai na tela
    def base_em(p): js(f"editor._confirmarPonto({{ ponto: {json.dumps(p)}, tela: [0, 0], tipoSnap: 'extremidade' }}, {{}}); 1")

    # ---- Mover a viga 1000 em x (digitado): leva o marcador de furo (D3), os cortes ficam no mesmo nó relativo
    js(f"editor.selecao.definir(['{ID['viga']}']); 1")
    tecla("m"); base_em([0, 0, 0]); digitar("1000;0;0"); tecla("Enter")
    v, f = ent("viga"), ent("furo")
    ok(v["inicio"][0] == 1000 and v["fim"][0] == 5000, f"Mover: a viga andou 1000 em x: {v['inicio']} {v['fim']}")
    ok(abs(f["atributos"]["furo"]["ponto"][0] - 3000) < 1e-6 and abs(f["vertices"][0][0] - 2990) < 1e-6,
       f"D3: o marcador de furo da viga foi junto (ponto e malha): {f['atributos']['furo']['ponto']}")
    ok([round(x, 5) for x in v["cortes_fim"][0]["normal"]] == [-0.70711, 0.70711, 0.0] and not (v["atributos"] or {}).get("marca_a_conferir"),
       f"Mover não mexe no corte nem na marca: {v['cortes_fim']}")
    tecla("Escape"); tecla("Escape")

    # ---- Mover o parafuso e a cota: o registro de onde estão acompanha (D3)
    js(f"editor.selecao.definir(['{ID['paraf']}', '{ID['cota']}']); 1")
    tecla("m"); base_em([0, 0, 0]); digitar("0;500;0"); tecla("Enter")
    pf, ct = ent("paraf"), ent("cota")
    ok(pf["atributos"]["parafuso"]["ponto"] == [1000, 540, 129], f"D3: o ponto gravado do parafuso acompanha: {pf['atributos']['parafuso']['ponto']}")
    ok(ct["atributos"]["cota"]["a"] == [0, 200, 0] and ct["atributos"]["cota"]["texto"] == "1.000 mm", f"D3: a cota leva as pontas: {ct['atributos']['cota']['a']}")
    tecla("Escape"); tecla("Escape")

    # ---- Copiar (Mover com Ctrl): a cópia idêntica mantém a marca e leva um marcador de furo novo, ligado a ela
    js(f"editor.selecao.definir(['{ID['viga']}']); 1")
    tecla("m"); base_em([0, 0, 0]); tecla("Control"); digitar("0;3000;0"); tecla("Enter")
    cop = jsj(f"const l = [...editor.documento.entidades.values()]; const c = l.filter(e => e.tipo === 'barra' && e.id !== '{ID['viga']}' && e.nome === 'viga')[0];"
              " if (!c) return null; const m = l.filter(e => e.atributos && e.atributos.furo && e.atributos.furo.peca === c.id);"
              " return { y: c.inicio[1], marca: c.atributos.marcas.posicao, conf: !!c.atributos.marca_a_conferir, marcadores: m.length, my: m.length ? m[0].atributos.furo.ponto[1] : null };")
    ok(cop and cop["y"] == 3000 and cop["marca"] == "P1" and not cop["conf"], f"Copiar: cópia idêntica com a mesma marca: {cop}")
    ok(cop and cop["marcadores"] == 1 and abs(cop["my"] - 3040) < 1e-6, f"D3: a cópia levou o próprio marcador de furo: {cop}")
    tecla("Escape"); tecla("Escape")

    # ---- Girar a viga 90° em volta de z (pelo nó do início): o corte da ponta gira junto (D1)
    js(f"editor.selecao.definir(['{ID['viga']}']); 1")
    js(f"editor.ativarFerramenta('girar'); 1")
    gi = jsj(f"""const f = editor.ativa; f.ids = ['{ID['viga']}'];
      f.plano = {{ normal: [0, 0, 1] }}; f.centro = [1000, 0, 0];
      editor.executar(editor.ativa.constructor && f.comandosPara(90, 0, 'Girar').cmds.length > 1
        ? {{ rotulo: 'g', itens: f.comandosPara(90, 0, 'Girar').cmds, aplicar(d) {{ for (const c of this.itens) c.aplicar(d); }}, desfazer(d) {{}}, ids() {{ return []; }}, selecao() {{ return []; }} }}
        : f.comandosPara(90, 0, 'Girar').cmds[0]); const v = editor.documento.get('{ID['viga']}'); const m = editor.documento.get('{ID['furo']}');
      return {{ fim: v.fim.map(x => Math.round(x)), n: v.cortes_fim[0].normal.map(x => Math.round(x * 1e4) / 1e4), rot: v.rotacao || 0,
               furo: m.atributos.furo.ponto.map(x => Math.round(x)) }};""")
    ok(gi and gi["fim"] == [1000, 4000, 0] and gi["n"] == [-0.7071, -0.7071, 0.0],
       f"D1: o corte da ponta girou com a viga (normal (-0,71; 0,71) → (-0,71; -0,71)): {gi}")
    ok(gi and gi["furo"] == [960, 2000, 129] and gi["rot"] == 0, f"D3: o marcador girou junto; viga horizontal girada em z não muda a rotação da seção: {gi}")
    tecla("Escape"); tecla("Escape")
    # girar em volta do próprio eixo (90° em x numa viga ao longo de x): a seção gira, e o `rotacao` acompanha
    gx = jsj(f"""const id = '{ID['viga']}'; editor.documento.alterar(id, {{ inicio: [0, 0, 0], fim: [4000, 0, 0], rotacao: 0 }});
      editor.ativarFerramenta('girar');
      const f = editor.ativa; f.ids = [id]; f.plano = {{ normal: [1, 0, 0] }}; f.centro = [0, 0, 0];
      const r = f.comandosPara(90, 0, 'Girar'); editor.executar(r.cmds[0]);
      const v = editor.documento.get(id); return [v.rotacao === undefined ? 'indef' : v.rotacao, v.inicio, v.fim, r.cmds.length];""")
    rx = gx[0] if gx and isinstance(gx[0], (int, float)) else None
    ok(rx is not None and (abs(rx % 360 - 90) < 1e-6 or abs(rx % 360 - 270) < 1e-6),
       f"girar em volta do próprio eixo muda a rotação da seção: {gx}")
    erros("Mover, Copiar e Girar")

    # ---- Escalar a viga 2× em x e a cota: a viga fica com a marca a conferir (D2); a cota refaz o texto (D8)
    js(f"editor.selecao.definir(['{ID['viga']}', '{ID['cota']}']); editor.ativarFerramenta('escalar'); 1")
    es = jsj(f"""const f = editor.ativa; f.ids = ['{ID['viga']}', '{ID['cota']}']; f.ancora = [0, 0, 0]; f.aplicar([2, 1, 1]);
      const v = editor.documento.get('{ID['viga']}'), c = editor.documento.get('{ID['cota']}');
      return {{ fim: v.fim, conf: !!v.atributos.marca_a_conferir, marca: v.atributos.marcas.posicao, texto: c.atributos.cota.texto, nome: c.nome }};""")
    ok(es and es["fim"][0] == 8000 and es["conf"] and es["marca"] == "P1", f"D2: a viga esticada fica com a marca a conferir (a marca não muda): {es}")
    ok(es and es["texto"] == "2,00 m" and es["nome"] == "2,00 m", f"D8: a cota escalada refaz o texto: {es and (es['texto'], es['nome'])}")
    tecla("Escape")

    # ---- Camada bloqueada: a chapa travada não anda e o aviso diz (D4)
    antes = ent("trav")["vertices"][0]
    js(f"editor.selecao.definir(['{ID['trav']}']); 1")
    tecla("m"); base_em([0, 0, 0]); digitar("500;0;0"); tecla("Enter")
    depois = ent("trav")["vertices"][0]
    avisos = js("[...document.querySelectorAll('.aviso, .avisos *, [role=alert]')].map(e => e.textContent).join(' | ')") or ""
    ok(antes == depois, f"D4: a peça em camada bloqueada não andou: {antes} → {depois}")
    ok("bloqueada" in avisos, f"D4: o aviso diz que ficou parada: {avisos[:160]}")
    tecla("Escape"); tecla("Escape")
    js("editor.selecao.limpar(); 1")

    # ---- Setas: → X e ← Y na ferramenta e no núcleo (D5)
    tecla("l"); base_em([0, -1000, 0])
    tecla("ArrowRight")
    s1 = jsj("return [editor.ativa.eixo || null, editor.inferencia.travado];")
    tecla("ArrowRight"); tecla("ArrowLeft")
    s2 = jsj("return [editor.ativa.eixo || null, editor.inferencia.travado];")
    ok(s1 == ["x", "x"] and s2 == ["y", "y"], f"D5: → trava X e ← trava Y, iguais na ferramenta e no núcleo: {s1} {s2}")
    tecla("Escape"); tecla("Escape")

    # ---- Snap perpendicular: da âncora até a aresta de cima da viga (D8)
    js(f"editor.documento.alterar('{ID['viga']}', {{ inicio: [0, 0, 0], fim: [4000, 0, 0], rotacao: 0 }}); editor.ativarFerramenta('linha'); 1")
    js("editor.camera.enquadrar([[1500, -300, -200], [2500, 900, 400]]); editor.camera.concluirAnimacao(); 1"); aba.drenar(0.5)
    pp = jsj("""const ed = editor, inf = ed.inferencia; inf.definirAncora([1500, 700, 129]);
      const alvo = [1500, 73, 129]; const t = ed.camera.paraTela(alvo);
      const r = inf.resolver(t[0] + 2, t[1] + 1, {});
      return { tipo: r.tipoSnap, p: r.ponto.map(x => Math.round(x)) };""")
    ok(pp and pp["tipo"] == "perpendicular" and pp["p"][0] == 1500, f"D8: snap perpendicular na aresta de cima da viga: {pp}")
    tecla("Escape"); tecla("Escape")

    # ---- Área da chapa com furo oblongo (D8)
    ar = jsj("""return import('/editor3d/nucleo/documento.js').then(m => m.areaDaChapa({ contorno: [[0, 0], [200, 0], [200, 100], [0, 100]],
               furos: [{ x: 50, y: 50, largura: 33, altura: 13 }, { x: 150, y: 50, diametro: 13 }] }));""") if False else None
    ar = js("""(async () => { const m = await import('/editor3d/nucleo/documento.js');
               return m.areaDaChapa({ contorno: [[0, 0], [200, 0], [200, 100], [0, 100]], furos: [{ x: 50, y: 50, largura: 33, altura: 13 }] }); })()""")
    esperado = 20000 - ((33 - 13) * 13 + 3.141592653589793 * 13 * 13 / 4)
    ok(ar is not None and abs(ar - esperado) < 0.01, f"D8: a área da chapa desconta o oblongo: {ar} (esperado {esperado:.1f})")

    # ---- Seção e Deslocamento abrem e soltam sem erro
    tecla("x"); tecla("z"); aba.drenar(0.3); tecla("Escape"); tecla("Escape")
    tecla("o"); tecla("Escape")
    ok(js("editor.idAtiva") == "selecionar", "Seção e Deslocamento soltam com o Esc")
    erros("Escalar, bloqueio, setas, perpendicular, Seção e Deslocamento")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
