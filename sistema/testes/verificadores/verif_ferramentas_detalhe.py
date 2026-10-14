# -*- coding: utf-8 -*-
"""As ferramentas de detalhamento manual do editor 3D com o mouse e o teclado de verdade (revisão de 14/10/2026, "estão
bem desfuncionais"). Num projeto sintético — uma viga W 250 (barra do catálogo) com uma chapa de 10 mm em cima (malha)
— confere:
  1. Shift numa aresta inclinada (travar paralelo) não quebra mais a inferência: antes a direção ia para a tabela de
     eixos do módulo e todo movimento do mouse, em todas as ferramentas, dava erro até recarregar a página;
  2. Parafuso: digitar "M16x45" sem clicar na caixa não troca de ferramenta (o M ativava o Mover e o x a Seção); o
     comprimento sai da pega (chapa de 10 + mesa da W) pela tabela do AISC; o padrão 2 × 2 lança 4 de uma vez; no meio
     da mesa (em cima da alma) não lança nada — antes saía um M12x290 atravessando a viga;
  3. Furo na barra do catálogo: a parede é a mesa do perfil (antes 10 mm fixos); em cima da alma, recusa;
  4. Chapa: na face, o retângulo "200;100" sai alinhado com a viga e EM CIMA da face (antes centrada, metade
     enterrada); "40;30" fura pelo canto com o furo da norma; um número troca a espessura;
  5. Virar, Encaixar e Chapa soltam com o Esc; a Barra lança com a rotação do painel;
  6. Sem erros no console."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento, Solido

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ferrdet_")
PASTA = os.path.join(DADOS, "ferr")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Ferramentas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
W = "W 250×32,7"                      # d 258, bf 146, tf 9,1
viga = Barra(nome="viga", inicio=(0.0, 0.0, 0.0), fim=(4000.0, 0.0, 0.0), perfil=W, rotacao=0.0, papel="viga")
diag = Barra(nome="diagonal", inicio=(0.0, 1500.0, 0.0), fim=(3000.0, 1500.0, 1500.0), perfil=W, rotacao=0.0, papel="viga")
doc.add(viga); doc.add(diag)
# a chapa de 10 mm em cima da mesa, de x 2800 a 3200 (malha, como a do IFC)
z0, z1 = 129.0, 139.0
vs = [(x, y, z) for z in (z0, z1) for (x, y) in ((2800.0, -73.0), (3200.0, -73.0), (3200.0, 73.0), (2800.0, 73.0))]
fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
doc.add(Solido(nome="CHAPA DE TESTE", camada="Chapas", vertices=vs, faces=fs, atributos={"marcas": {"nome": "CH1"}}))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ferrdet_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ferr", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 3 && editor.ferramentas"
                                                    " && editor.ferramentas.get('parafuso') && editor.cena.perfil(%s))" % json.dumps(W)):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def mods(shift=False, ctrl=False): return (2 if ctrl else 0) | (8 if shift else 0)
    def mover(x, y, **m):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, modifiers=mods(**m), buttons=0); aba.drenar(0.05)
    def clicar(x, y, **m):
        mover(x, y, **m)
        for t, bt in (("mousePressed", 1), ("mouseReleased", 0)):
            aba.cmd("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1, modifiers=mods(**m), buttons=bt)
        aba.drenar(0.15)
    def tecla(k):
        kc = {"Escape": 27, "Enter": 13}.get(k, ord(k.upper()) if len(k) == 1 else 0)
        p = dict(key=k, code=k, windowsVirtualKeyCode=kc)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", **p, **({"text": k} if len(k) == 1 else {}))
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", **p)
        aba.drenar(0.08)
    def digitar(t):
        for ch in t: tecla(ch)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    def enquadrar(lo, hi):
        js(f"editor.camera.enquadrar([{json.dumps(lo)}, {json.dumps(hi)}]); editor.camera.concluirAnimacao(); 1"); aba.drenar(0.6)
    def na_face(eid, p3, n, raio=120):
        """Um pixel em volta da projeção de p3 em que o raio pega a peça `eid` com a normal `n`: [x, y, ponto]."""
        return jsj(f"""const ed = editor, r = ed.el.canvas.getBoundingClientRect(); const t = ed.camera.paraTela({json.dumps(p3)});
          for (let rr = 0; rr <= {raio}; rr += 2) for (let k = 0; k < (rr ? 16 : 1); k++) {{
            const a = 2 * Math.PI * k / 16, sx = t[0] + rr * Math.cos(a), sy = t[1] + rr * Math.sin(a);
            const s = ed.selecao.sob(sx, sy); const n = {json.dumps(n)};
            if (s && s.id === {json.dumps(eid)} && s.normal[0]*n[0] + s.normal[1]*n[1] + s.normal[2]*n[2] > 0.9) return [sx + r.left, sy + r.top, s.ponto];
          }} return null;""")
    ids = jsj("const l = [...editor.documento.entidades.values()]; return { viga: l.find(e => e.nome === 'viga').id, diag: l.find(e => e.nome === 'diagonal').id, chapa: l.find(e => e.nome === 'CHAPA DE TESTE').id };")

    # 1) Shift numa aresta inclinada (a diagonal) com o Mover: depois disso, nenhuma ferramenta pode dar erro
    enquadrar([0, 1300, -200], [3000, 1700, 1700])
    p = na_face(ids["diag"], [1500, 1500, 750 + 129], [-0.447, 0, 0.894], raio=200) or na_face(ids["diag"], [1500, 1500, 750], [0, -1, 0], raio=200)
    ok(p is not None, f"achou a diagonal na tela: {p and p[:2]}")
    js(f"editor.ativarFerramenta('mover'); editor.selecao.definir(['{ids['diag']}']); 1")
    clicar(p[0], p[1])
    js(f"editor.inferencia.ultimo = {{ tipoSnap: 'sobre_aresta', aresta: [[0, 1500, 129], [3000, 1500, 1629]] }}; 1")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Shift", code="ShiftLeft", windowsVirtualKeyCode=16, modifiers=8)
    ok(js("editor.inferencia.travado") == "aresta", "Shift trava paralelo à aresta da diagonal")
    for k in range(4): mover(p[0] + 30 + 5 * k, p[1] - 10, shift=True)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Shift", code="ShiftLeft", windowsVirtualKeyCode=16, modifiers=0)
    for k in range(4): mover(p[0] + 60 + 5 * k, p[1] + 20)
    tecla("Escape"); tecla("Escape")
    # depois do Shift solto, as outras ferramentas: o movimento do mouse com a âncora não pode dar erro
    js("editor.selecao.limpar(); editor.ativarFerramenta('linha'); 1")
    clicar(p[0], p[1])
    for k in range(4): mover(p[0] + 40 + 5 * k, p[1] + 15)
    tecla("Escape"); tecla("Escape")
    erros("Mover + Shift na aresta e depois")

    # 2) Parafuso: digitar o tamanho, comprimento pela pega, padrão
    enquadrar([2700, -300, -100], [3300, 300, 300])
    tecla("u")
    digitar("M16x45"); tecla("Enter")
    t = jsj("return editor.ativa && editor.ativa.tamanho;")
    ok(js("editor.idAtiva") == "parafuso" and t and t["d"] == 16 and t["L"] == 45, f"digitar M16x45 fica no Parafuso com o tamanho: {js('editor.idAtiva')} {t}")
    digitar("12"); tecla("Enter")
    pc = na_face(ids["chapa"], [3000, 40, z1], [0, 0, 1])
    ok(pc is not None, "achou a chapa de cima na tela")
    for k in range(4): mover(pc[0] + k, pc[1])
    clicar(pc[0], pc[1])
    pf = jsj("const e = [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.parafuso).pop(); return e ? [e.nome, e.atributos.parafuso] : null;")
    # pega = chapa 10 + mesa 9,1 = 19,1; M12: + 17,5 = 36,6 → 40
    ok(pf and abs((pf[1].get("pega") or 0) - 19.1) < 0.6 and pf[1]["L"] == 40 and pf[0] == "BOLT (A325) 12x40",
       f"comprimento pela pega (chapa 10 + mesa 9,1): {pf and (pf[0], pf[1].get('pega'), pf[1]['L'])}")
    furos = jsj(f"const c = editor.documento.get('{ids['chapa']}'); return (c.atributos.furos_editor || []).length;")
    marc = jsj(f"return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.furo && e.atributos.furo.peca === '{ids['viga']}').length;")
    ok(furos == 1 and marc == 1, f"o parafuso furou a chapa (malha) e a mesa da viga (marcador): {furos} {marc}")
    js("editor.ativa.constructor.padrao = { linhas: 2, g: 60, colunas: 2, p: 80 }; 1")
    n0 = js("editor.documento.entidades.size")
    pc2 = na_face(ids["chapa"], [2880, 0, z1], [0, 0, 1])
    js("editor.ativa.constructor.padrao = { linhas: 2, g: 80, colunas: 2, p: 80 }; 1")
    mover(pc2[0], pc2[1]); clicar(pc2[0], pc2[1])
    novos = jsj(f"return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.parafuso).length;")
    ok(novos == 5, f"padrão 2 × 2 no gabarito de 80: 4 parafusos de uma vez (5 no total): {novos}")
    # no meio da mesa da viga (sem a chapa), o eixo corre em cima da alma: nada é lançado
    js("editor.ativa.constructor.padrao = { linhas: 1, g: 60, colunas: 1, p: 60 }; editor.ativa.constructor.eixos = true; 1")
    enquadrar([2000, -300, -100], [2600, 300, 300])
    pm = na_face(ids["viga"], [2300, 0, 129], [0, 0, 1])
    n1 = js("editor.documento.entidades.size")
    mover(pm[0], pm[1]); clicar(pm[0], pm[1])
    ok(js("editor.documento.entidades.size") == n1 and "alma" in (js("editor.el.dica.textContent") or ""),
       f"em cima da alma não lança e avisa: {js('editor.documento.entidades.size') - n1} · {(js('editor.el.dica.textContent') or '')[:90]}")
    js("editor.ativa.constructor.padrao = { linhas: 1, g: 60, colunas: 1, p: 60 }; 1")
    aba.cmd("Page.captureScreenshot", format="png")
    open(os.path.join(SCR, "_ferr_parafuso.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    tecla("Escape")
    ok(js("editor.idAtiva") == "selecionar", "Esc solta o Parafuso")
    erros("Parafuso")

    # 3) Furo na mesa da viga (barra do catálogo): a parede é a mesa
    enquadrar([1200, -300, -100], [1800, 300, 300])
    tecla("f"); digitar("M16"); tecla("Enter")
    ok(abs((js("editor.ativa.diametro") or 0) - 17.5) < 0.01, f"furo M16 = Ø17,5 (d + 1,5): {js('editor.ativa.diametro')}")
    pv = na_face(ids["viga"], [1500, 0, 129], [0, 0, 1])
    n1 = js("editor.documento.entidades.size")
    clicar(pv[0], pv[1])
    ok(js("editor.documento.entidades.size") == n1, "furo no meio da mesa (em cima da alma): recusado")
    pv = na_face(ids["viga"], [1500, 45, 129], [0, 0, 1])
    clicar(pv[0], pv[1])
    fu = jsj("const e = [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.furo && Math.abs(e.atributos.furo.d - 17.5) < 0.01).pop(); return e ? e.atributos.furo : null;")
    ok(fu and abs(fu["profundidade"] - 9.1) < 0.6, f"furo na mesa da W com a espessura da mesa (9,1): {fu and fu['profundidade']}")
    tecla("Escape")
    erros("Furo")

    # 4) Chapa na mesa: "200;100", em cima da face, alinhada com a viga; "40;30" fura; "8" troca a espessura
    tecla("h")
    pv = na_face(ids["viga"], [1450, -40, 129], [0, 0, 1])
    clicar(pv[0], pv[1]); mover(pv[0] + 40, pv[1] + 10)
    digitar("200;100"); tecla("Enter")
    ch = jsj("const c = [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').pop(); return c ? {id: c.id, origem: c.origem, ex: c.eixo_x, centrada: c.centrada, contorno: c.contorno, esp: c.espessura} : null;")
    if ch:
        xs = [q[0] for q in ch["contorno"]]; ys = [q[1] for q in ch["contorno"]]
        ok(round(max(xs) - min(xs)) == 200 and round(max(ys) - min(ys)) == 100, f"chapa 200 × 100: {max(xs)-min(xs):.1f} × {max(ys)-min(ys):.1f}")
        ok(ch["centrada"] is False and abs(ch["origem"][2] - 129) < 0.6, f"chapa em cima da mesa (cresce para fora): centrada {ch['centrada']}, z {ch['origem'][2]:.1f}")
        ok(abs(abs(ch["ex"][0]) - 1) < 1e-6, f"o X da chapa segue a viga: {ch['ex']}")
    else:
        ok(False, "a chapa foi criada")
    digitar("40;30"); tecla("Enter")
    digitar("8"); tecla("Enter")
    c2 = jsj(f"const c = editor.documento.get('{ch['id']}'); return {{esp: c.espessura, furos: c.furos}};") if ch else None
    ok(c2 and c2["esp"] == 8 and len(c2["furos"]) == 1 and abs(c2["furos"][0]["diametro"] - 13.5) < 0.01
       and abs(c2["furos"][0]["x"] - min(xs) - 40) < 0.01, f"furo a 40;30 do canto (Ø13,5) e espessura 8: {c2}")
    tecla("Enter"); tecla("Escape")
    ok(js("editor.idAtiva") == "selecionar", "Esc solta a Chapa")
    erros("Chapa")

    # 5) Virar e Encaixar soltam com o Esc; a Barra lança com a rotação do painel
    tecla("v")
    pv = na_face(ids["viga"], [1000, 0, 129], [0, 0, 1])
    clicar(pv[0], pv[1])
    ok((js(f"editor.documento.get('{ids['viga']}').rotacao") or 0) == 90, "Virar girou a viga 90°")
    js("editor.desfazer(); 1")
    tecla("Escape")
    ok(js("editor.idAtiva") == "selecionar", "Esc solta o Virar")
    js("editor.ativarFerramenta('encaixar')"); tecla("Escape")
    ok(js("editor.idAtiva") == "selecionar", "Esc solta o Encaixar")
    tecla("b"); aba.drenar(0.5)
    ok("Barra a lançar" in (js("editor.el.props.textContent") or ""), "a Barra tem o painel com perfil, papel e rotação")
    js("editor.ativa.constructor.rotacao = 90; 1")
    clicar(500, 300); mover(700, 300); clicar(700, 300)
    nb = jsj("const e = [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').pop(); return [e.nome, e.rotacao];")
    ok(nb and nb[1] == 90, f"barra lançada com a rotação do painel: {nb}")
    js("editor.ativa.constructor.rotacao = 0; 1")
    tecla("Escape"); tecla("Escape")
    erros("Virar, Encaixar e Barra")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
