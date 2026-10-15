# -*- coding: utf-8 -*-
"""O lado BIM do editor 3D (14/10/2026: "cheia de informações como um Revit"), no navegador de verdade, num projeto
sintético com peças numeradas e com fase: a ficha ao parar o mouse sobre a viga (marca, comprimento, peso), Colorir por
fase (dois grupos na legenda), a Tabela de peças (linhas, total e clique selecionando), as Etiquetas das marcas no 3D e
uma vista salva que volta o enquadramento. Sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_bim3d_")
PASTA = os.path.join(DADOS, "bim")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "BIM", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
W = "W 310×38,7"
doc = Documento()
for i, x in enumerate((0, 6000)):
    doc.add(Barra(nome="pilar%d" % i, inicio=(x, 0, 0), fim=(x, 0, 4000), perfil=W, rotacao=90, papel="pilar",
                  atributos={"marcas": {"posicao": "P1", "conjunto": "M1", "perfil": W}, "fase": "Lote 1"}))
doc.add(Barra(nome="viga", inicio=(0, 0, 4000), fim=(6000, 0, 4000), perfil=W, papel="viga",
              atributos={"marcas": {"posicao": "P2", "conjunto": "M2", "perfil": W}, "fase": "Lote 2"}))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_bim3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=bim", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 3)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            if js(cond): return True
            aba.drenar(0.3)
        return False
    def menu(acao):
        js(f"document.querySelector('[data-acao=\"{acao}\"]').click(); 1"); aba.drenar(0.3)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ids = jsj("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    def ent(i): return jsj(f"const e = editor.documento.get('{i}'); return e ? JSON.parse(JSON.stringify(e)) : null;")
    def chapas(): return jsj("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').map(e => JSON.parse(JSON.stringify(e)));")
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)

    js("editor.camera.zoomExtensao(); editor.camera.concluirAnimacao(); 1"); aba.drenar(0.8)
    # 1) a ficha ao parar o mouse sobre a viga
    p = jsj(f"""const r = editor.el.canvas.getBoundingClientRect(); const t = editor.camera.paraTela([3000, 0, 4000]);
              for (let d = 0; d < 60; d += 3) for (const s of [1, -1]) {{ const h = editor.selecao.sob(t[0], t[1] + s * d);
                if (h && h.id === '{ids['viga']}') return [t[0] + r.left, t[1] + s * d + r.top]; }} return null;""")
    ok(p is not None, "achou a viga na tela")
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=p[0], y=p[1], buttons=0); aba.drenar(0.9)
    ficha = js("(() => { const f = document.querySelector('.ficha-peca'); return f && !f.hidden ? f.textContent : ''; })()") or ""
    ok("P2" in ficha and "Comprimento" in ficha and "Peso" in ficha and "Lote 2" in ficha, f"a ficha mostra marca, comprimento, peso e fase: {ficha[:120]!r}")
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=5, buttons=0); aba.drenar(0.2)
    # 2) colorir por fase
    jsj("""const s = [...editor.el.camadas.querySelectorAll('select')].find(x => [...x.options].some(o => o.value === 'fase'));
           s.value = 'fase'; s.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.6)
    n = js("editor.el.camadas.querySelectorAll('.legenda-grupos .linha').length")
    ok(n == 2, f"Colorir por fase: dois grupos na legenda ({n})")
    # 3) a tabela de peças
    menu("tabela-pecas")
    ok(esperar("!!document.querySelector('.painel-tabela table')", 10), "a tabela de peças abriu")
    linhas = js("document.querySelectorAll('.painel-tabela tr').length")
    ok(linhas == 4, f"cabeçalho, P1, P2 e o total: {linhas}")
    js("document.querySelectorAll('.painel-tabela tr')[1].click(); 1"); aba.drenar(0.3)
    sel = set(jsj("return [...editor.selecao.ids];") or [])
    ok(sel == {ids["pilar0"], ids["pilar1"]}, "clicar em P1 seleciona os dois pilares")
    menu("tabela-pecas")
    # 4) etiquetas
    js("editor.selecao.limpar(); 1")
    menu("etiquetas"); aba.drenar(0.6)
    et = js("[...document.querySelectorAll('.camada-etiquetas span')].map(s => s.textContent).sort().join(',')")
    ok(et == "P1,P1,P2", f"etiquetas das marcas: {et}")
    menu("etiquetas")
    # 5) a vista salva volta o enquadramento
    alvo0 = jsj("return editor.camera.controles.target.toArray();")
    menu("salvar-vista")
    ok(esperar("editor.el.dialogo.open", 10), "o diálogo Salvar vista abriu")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("!!document.querySelector('.barra-vistas button')", 10), "a aba da vista apareceu embaixo")
    js(f"editor.camera.zoomSelecao(['{ids['pilar1']}']); editor.camera.concluirAnimacao(); 1"); aba.drenar(0.6)
    meio_ = jsj("return editor.camera.controles.target.toArray();")
    ok(meio_ and any(abs(a - b) > 0.5 for a, b in zip(alvo0, meio_)), f"a câmera saiu do lugar antes de voltar: {meio_}")
    js("document.querySelector('.barra-vistas button').click(); 1"); aba.drenar(1.0)
    js("editor.camera.concluirAnimacao(); 1")
    alvo1 = jsj("return editor.camera.controles.target.toArray();")
    ok(alvo1 and all(abs(a - b) < 1e-3 for a, b in zip(alvo0, alvo1)), f"a vista voltou o alvo da câmera: {alvo0} = {alvo1}")
    ok(len(jsj("return editor.documento.metadados.vistas || [];")) == 1, "a vista ficou gravada no modelo")
    # 6) a árvore por conjunto → posição e o escopo tipo × instância no painel
    jsj("""const s = [...editor.el.arvore.querySelectorAll('select')][0]; s.value = 'conjunto'; s.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.6)
    ramos = js("[...editor.el.arvore.querySelectorAll('.ramo > .titulo')].map(b => b.textContent).join('|')") or ""
    ok("M1" in ramos and "M2" in ramos, f"a árvore organizada por conjunto: {ramos}")
    selecionar(ids["pilar0"]); aba.drenar(0.6)
    jsj("""const l = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Aplicar a');
           const s = l.nextElementSibling; s.value = 'posicao'; s.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.6)
    jsj("""const l = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Acabamento');
           const s = l.nextElementSibling; s.value = 'pintura'; s.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.5)
    acab = jsj(f"return ['{ids['pilar0']}', '{ids['pilar1']}', '{ids['viga']}'].map(i => editor.documento.get(i).atributos.acabamento || '');")
    ok(acab == ["pintura", "pintura", ""], f"o acabamento foi para a posição inteira (os dois pilares), não para a viga: {acab}")
    # 6b) uma propriedade do usuário (a posição inteira, pelo "Aplicar a" que ficou em "todas da mesma posição")
    selecionar(ids["pilar0"]); aba.drenar(0.6)
    js("[...editor.el.props.querySelectorAll('button')].find(b => b.textContent === '+ propriedade').click(); 1")
    ok(esperar("editor.el.dialogo.open", 10), "o diálogo da propriedade abriu")
    jsj("""const i = editor.el.dialogoCorpo.querySelectorAll('input'); i[0].value = 'Fornecedor'; i[1].value = 'Gerdau'; return 1;""")
    js("editor.el.dialogoOk.click(); 1"); aba.drenar(0.6)
    pu = jsj(f"return ['{ids['pilar0']}', '{ids['pilar1']}', '{ids['viga']}'].map(i => (editor.documento.get(i).atributos.props_usuario || {{}}).Fornecedor || '');")
    ok(pu == ["Gerdau", "Gerdau", ""], f"a propriedade foi para os dois pilares da posição: {pu}")
    ok("Fornecedor" in (js("editor.el.props.textContent") or ""), "o painel mostra a propriedade")
    ok(bool(js("[...editor.el.camadas.querySelectorAll('select option')].some(o => o.value === 'u:Fornecedor')")), "o Colorir por oferece a propriedade")

    # 6c) a sequência de montagem: até o Lote 1 a viga (Lote 2) some; fechando, volta
    js("editor.selecao.limpar(); 1")
    menu("sequencia-montagem")
    ok(esperar("!!document.querySelector('.painel-sequencia ul li')", 10), "o painel da sequência abriu com as fases")
    js("document.querySelectorAll('.painel-sequencia ul li')[0].click(); 1"); aba.drenar(0.4)
    oc = jsj("return editor.documento.ocultosNaVista ? [...editor.documento.ocultosNaVista] : [];")
    ok(oc == [ids["viga"]], f"até o Lote 1: só a viga (Lote 2) escondida: {oc}")
    js("[...document.querySelectorAll('.painel-sequencia button')].find(b => b.textContent === '×').click(); 1"); aba.drenar(0.4)
    ok(not js("editor.documento.ocultosNaVista && editor.documento.ocultosNaVista.size"), "fechar a sequência mostra tudo de novo")

    # 7) o perfil soldado digitado no campo de perfil
    selecionar(ids["viga"]); aba.drenar(0.6)
    jsj("""const i = [...editor.el.props.querySelectorAll('.busca-perfil input')][0]; i.focus(); i.value = 'VS 500x250x9,5x6,3';
           i.dispatchEvent(new Event('input')); return 1;""")
    aba.drenar(0.3)
    item = js("(() => { const b = document.querySelector('.lista-perfis button'); return b ? b.textContent : ''; })()") or ""
    ok("VS 500x250x9,5x6,3" in item, f"a lista oferece o perfil soldado: {item[:60]!r}")
    js("document.querySelector('.lista-perfis button').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); 1")
    ok(esperar(f"editor.documento.get('{ids['viga']}').perfil === 'VS 500x250x9,5x6,3'", 15), "a viga ficou com o perfil soldado")
    ok(esperar("!!editor.cena.perfil('VS 500x250x9,5x6,3')", 10), "o editor conhece a seção do perfil soldado")
    erros("BIM")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
