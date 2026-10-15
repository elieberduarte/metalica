# -*- coding: utf-8 -*-
"""O fluxo de uma obra inteira pelo editor 3D, só pelos menus e diálogos (15/10/2026): pilares nos eixos → bases →
vigas → terças → correntes → mão-francesa → contravento com SC1 → longarinas → chapa de topo (Aplicar ligação) →
Numerar → Conferir antes de detalhar → Exportar IFC → Detalhar peças e conjuntos. Imprime os achados da conferência (as ferramentas não devem
gerar colisão entre si)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo_")
PASTA = os.path.join(DADOS, "fluxo")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=fluxo", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.true)"):
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
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)
    PREVIA = "(() => { const g = editor.cena.previa.getObjectByName('previa-modelagem'); return g ? g.children.filter(x => x.isMesh).length : 0; })()"
    def todas(cond): return jsj(f"return [...editor.documento.entidades.values()].filter(e => {cond}).map(e => e.id);")
    def conta(cond): return len(todas(cond))
    def lancar(acao, rotulo, ids_sel=None, campos=None, espera_previa=True):
        if ids_sel is not None:
            selecionar(*ids_sel)
        n0 = jsj("return editor.documento.entidades.size;")
        menu(acao)
        ok(esperar("editor.el.dialogo.open", 20), f"{rotulo}: o diálogo abriu")
        for rot, val in (campos or {}).items():
            js(f"""(() => {{ const l = [...editor.el.dialogoCorpo.querySelectorAll('label')].find(l => l.textContent.startsWith({json.dumps(rot)}));
                    const i = l.nextElementSibling; i.value = {json.dumps(str(val))}; i.dispatchEvent(new Event('change', {{ bubbles: true }})); return 1; }})()""")
        if espera_previa:
            ok(esperar(f"{PREVIA} > 0", 30), f"{rotulo}: a prévia apareceu ({js(PREVIA)} peças)")
        js("editor.el.dialogoOk.click(); 1")
        ok(esperar(f"editor.documento.entidades.size > {n0}", 40), f"{rotulo}: as peças entraram")
        aba.drenar(0.5)
        erros(rotulo)

    # os eixos da obra (como o lançamento deixa no snap): A e B a 20 m; 1 a 4 a cada 6 m; nível +6,00
    js("""editor.inferencia.referencias = { eixos: [
        { nome: 'A', a: [0, -1000], b: [0, 19000] }, { nome: 'B', a: [20000, -1000], b: [20000, 19000] },
        { nome: '1', a: [-1000, 0], b: [21000, 0] }, { nome: '2', a: [-1000, 6000], b: [21000, 6000] },
        { nome: '3', a: [-1000, 12000], b: [21000, 12000] }, { nome: '4', a: [-1000, 18000], b: [21000, 18000] }],
        niveis: [{ nome: 'Cobertura', z: 6000 }] }; 1""")

    # 1) pilares e bases
    lancar("modelar-pilares", "Pilares nos eixos", campos={"Perfil": "W 250×32,7", "Topo (mm)": 6000})
    pil = todas("e.papel === 'pilar'")
    ok(len(pil) == 8, f"8 pilares: {len(pil)}")
    lancar("modelar-bases", "Bases nos pilares", ids_sel=[])
    ok(conta("e.nome === 'Placa de base'") == 8, "8 placas de base")

    # 2) as vigas de cobertura, uma por eixo numerado (A-n a B-n)
    def pilar(nome): return jsj(f"return [...editor.documento.entidades.values()].find(e => e.nome === 'Pilar {nome}').id;")
    for n in "1234":
        lancar("modelar-viga", f"Viga do eixo {n}", ids_sel=[pilar("A-" + n), pilar("B-" + n)], campos={"Perfil": "W 310×38,7"})
    vigas = todas("e.papel === 'viga'")
    ok(len(vigas) == 4, f"4 vigas de cobertura: {len(vigas)}")

    # 3) terças, correntes, mão-francesa, contravento com SC1
    lancar("modelar-tercas", "Terças", ids_sel=vigas, campos={"Espaçamento máximo (mm)": 2000})
    tercas = todas("e.papel === 'terça'")
    ok(len(tercas) > 0, f"terças: {len(tercas)}")
    lancar("modelar-correntes", "Correntes", ids_sel=tercas)
    lancar("modelar-mao-francesa", "Mão-francesa", ids_sel=tercas)
    lancar("modelar-contravento", "Contravento com SC1", ids_sel=vigas[:2])
    n_sc = conta("e.papel === 'suporte'")
    ok(n_sc == 4, f"4 suportes SC1: {n_sc}")

    # 4) longarinas no eixo A
    lancar("modelar-longarinas", "Longarinas", ids_sel=[pilar("A-" + n) for n in "1234"])

    # 5) a chapa de topo viga × pilar em A-1, pelo Aplicar ligação
    v1 = jsj(f"""const p = editor.documento.get('{pilar("A-1")}');
        return [...editor.documento.entidades.values()].find(e => e.papel === 'viga' && Math.abs(e.inicio[1] - p.inicio[1]) < 1).id;""")
    selecionar(v1, pilar("A-1"))
    menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "Aplicar ligação: o diálogo abriu")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "chapa_topo_joelho", "viga + pilar sugere a chapa de topo")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de topo')", 40), "a chapa de topo entrou")
    erros("Chapa de topo")

    # 6) numerar tudo: toda peça de produção com marca
    selecionar()
    menu("numerar")
    ok(esperar("[...editor.documento.entidades.values()].filter(e => e.papel === 'pilar').every(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao)", 60),
       "Numerar: os pilares ganharam marca")
    aba.drenar(1.0)
    sem = jsj("""return [...editor.documento.entidades.values()].filter(e => (e.tipo === 'barra' || e.tipo === 'chapa')
                 && !(e.atributos && e.atributos.furo) && !((e.atributos || {}).marcas || {}).posicao).map(e => e.nome + ' ' + (e.perfil || ''));""")
    ok(not sem, f"todas as barras e chapas com marca de posição: {sem[:8]}")
    erros("Numerar")
    pos = jsj("return [...new Set([...editor.documento.entidades.values()].map(e => ((e.atributos || {}).marcas || {}).posicao).filter(Boolean))].length;")
    mats = jsj("const m = {}; for (const e of editor.documento.entidades.values()) { const k = e.tipo + ' | ' + (e.material || '(sem)') + ' | ' + (e.papel || e.nome || ''); m[k] = (m[k] || 0) + 1; } return m;")
    for k, n in sorted((mats or {}).items()):
        print(f"          {n:3d}  {k}")
    print(f"        modelo: {jsj('return editor.documento.entidades.size;')} entidades, {pos} posições")

    # 7) conferir antes de detalhar: os achados (colisão, execução, produção)
    r = aba.cmd("Runtime.evaluate", awaitPromise=True, returnByValue=True, expression="""(async () => {
        const resp = await fetch('/api/modelo/conferencia', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ documento: editor.documento.paraJSON() }) });
        const j = await resp.json();
        const nome = (id) => { const e = editor.documento.get(id); return e ? (e.nome + (e.perfil ? ' ' + e.perfil : '')) : id; };
        return JSON.stringify({ chaves: Object.keys(j), achados: (j.achados || []).map(a => [a.regra || a.tipo || '', a.nivel || '', (a.ids || []).map(nome).join(' x '), String(a.texto || a.mensagem || a.descricao || '').slice(0, 160)]) });
    })()""")
    bruto = ((r or {}).get("result") or {}).get("value") or (r or {}).get("value") or "{}"
    dados = json.loads(bruto)
    achados = dados.get("achados") or []
    import collections
    por = collections.Counter((a[0], a[2]) for a in achados)
    print(f"        conferência ({dados.get('chaves')}): {len(achados)} achados")
    for (regra, pecas), n in por.most_common(40):
        exemplo = next(a[3] for a in achados if (a[0], a[2]) == (regra, pecas))
        print(f"          {n:3d}x {regra}: {pecas} | {exemplo}")
    menu("conferir-producao")
    ok(esperar("!!editor._painelConferencia", 120), "Conferir antes de detalhar: o painel abriu")
    erros("Conferência")

    # 8) exportar IFC
    menu("exportar-ifc")
    ok(esperar("[...document.querySelectorAll('a[download]')].some(a => /[.]ifc/i.test(a.getAttribute('href') || a.textContent))", 60), "o IFC exportado tem link para baixar")
    erros("IFC")

    # 9) detalhar peças e conjuntos (sem abrir o CAD: o teste continua nesta página)
    js("""window.__avisos = []; const av = editor.aviso.bind(editor);
          editor.aviso = (c, t, d) => { window.__avisos.push([String(c && c.textContent !== undefined ? c.textContent : c), t]); return av(c, t, d); };
          editor._abrirCAD = () => {};
          const f0 = window.fetch.bind(window);
          window.fetch = async (u, o) => { const r = await f0(u, o);
            if (/\/detalhar$/.test(String(u))) { try { window.__detalhe = await r.clone().json(); } catch (e) {} }
            return r; }; 1""")
    menu("detalhar-pecas")
    ok(esperar("editor.el.dialogo.open", 20), "Detalhar peças: o diálogo abriu")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("window.__avisos.some(a => /^(Detalhamento:|Não foi possível detalhar)/.test(a[0]))", 400), "o detalhamento terminou")
    msg = jsj("return (window.__avisos.find(a => /^(Detalhamento:|Não foi possível detalhar)/.test(a[0])) || [''])[0];")
    print(f"        {msg}")
    for av in (jsj("return (window.__detalhe || {}).avisos || [];") or [])[:12]:
        print(f"          aviso: {str(av)[:200]}")
    ok(msg.startswith("Detalhamento:"), "as peças das ferramentas detalham sem erro")
    erros("Detalhamento")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
