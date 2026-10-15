# -*- coding: utf-8 -*-
"""As ferramentas de modelagem pela seleção do editor 3D (14/10/2026), no navegador de verdade: Terças por espaçamento,
Treliça entre banzos, Pilares nos eixos, Viga entre pilares e Contraventamento em X — pelo menu Lançamento, com o
diálogo, o desfazer e sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_mod3d_")
PASTA = os.path.join(DADOS, "mod")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Modelagem", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
doc.add(Barra(nome="T1", inicio=(0, 0, 5000), fim=(6000, 0, 5600), perfil="W 150×13", papel="banzo"))
doc.add(Barra(nome="T2", inicio=(0, 5000, 5000), fim=(6000, 5000, 5600), perfil="W 150×13", papel="banzo"))
doc.add(Barra(nome="BS", inicio=(0, 20000, 1000), fim=(6000, 20000, 1000), perfil="U 100×40×2,65", papel="banzo"))
doc.add(Barra(nome="BI", inicio=(0, 20000, 0), fim=(6000, 20000, 0), perfil="U 100×40×2,65", papel="banzo"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mod3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=mod", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 4)"):
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
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)
    def conta(papel): return jsj(f"return [...editor.documento.entidades.values()].filter(e => e.papel === '{papel}').length;")
    def dialogo(acao):
        menu(acao)
        return esperar("editor.el.dialogo.open", 20)
    def ok_dialogo(): js("editor.el.dialogoOk.click(); 1")
    PREVIA = "(() => { const g = editor.cena.previa.getObjectByName('previa-modelagem'); return g ? g.children.filter(x => x.isMesh).length : 0; })()"
    def campo(rotulo, valor):
        js(f"""(() => {{ const l = [...editor.el.dialogoCorpo.querySelectorAll('label')].find(l => l.textContent.startsWith({json.dumps(rotulo)}));
                const i = l.nextElementSibling; i.value = {json.dumps(str(valor))}; i.dispatchEvent(new Event('input', {{ bubbles: true }})); return 1; }})()""")

    # 1) terças nas duas tesouras
    selecionar(ids["T1"], ids["T2"])
    ok(dialogo("modelar-tercas"), "o diálogo Terças abriu")
    ok(esperar(f"{PREVIA} === 5", 20), f"a prévia mostra as 5 terças antes do OK: {js(PREVIA)}")
    ok(js("editor.el.dialogo.classList.contains('com-previa')"), "o diálogo vai para o canto durante a prévia")
    ok("5 peças" in (js("editor.el.dialogoCorpo.querySelector('.estado-previa').textContent") or ""), "o diálogo diz o que vai sair")
    ok(conta("terça") == 0, "a prévia não entra no modelo")
    campo("Espaçamento máximo", 1000)
    ok(esperar(f"{PREVIA} === 7", 20), f"espaçamento 1000: a prévia refaz com 7 terças: {js(PREVIA)}")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'terça')"), "as terças entraram")
    ok(esperar(f"{PREVIA} === 0", 5), "a prévia sai quando o diálogo fecha")
    n = conta("terça")
    ok(n == 7, f"7 linhas de terças em 6,03 m (beiral 200, cumeeira 250, máx. 1000): {n}")
    ok(jsj("return editor.selecao.entidades.length;") == n, "as terças novas ficam selecionadas")
    js("editor.desfazer(); 1"); aba.drenar(0.4)
    ok(conta("terça") == 0, "Ctrl+Z tira as terças de uma vez")
    erros("Terças")

    # 2) treliça Pratt entre os banzos
    selecionar(ids["BS"], ids["BI"])
    ok(dialogo("modelar-trelica"), "o diálogo Treliça abriu")
    ok(esperar(f"{PREVIA} === 9", 20), f"a prévia mostra os 5 montantes e as 4 diagonais: {js(PREVIA)}")
    js("editor.el.dialogoCancelar.click(); 1"); aba.drenar(0.5)
    ok(js(PREVIA) == 0 and conta("montante") == 0, "Cancelar tira a prévia e não lança nada")
    ok(dialogo("modelar-trelica"), "o diálogo Treliça abriu de novo")
    ok(esperar(f"{PREVIA} === 9", 20), "a prévia de novo")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'montante')"), "a treliça entrou")
    ok(conta("montante") == 5 and conta("diagonal") == 4, f"Pratt de 4 painéis: {conta('montante')} montantes, {conta('diagonal')} diagonais")
    pecas = jsj("return [...new Set([...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.origem).map(e => e.atributos.origem.peca))];")
    ok(pecas == ["TRELIÇA"], f"banzos e almas no mesmo bloco: {pecas}")
    erros("Treliça")

    # 3) pilares nos eixos (os eixos gravados da obra, como o lançamento deixa no snap)
    js("""editor.inferencia.referencias = { eixos: [
        { nome: 'A', a: [30000, -1000], b: [30000, 11000] }, { nome: 'B', a: [38000, -1000], b: [38000, 11000] },
        { nome: '1', a: [29000, 0], b: [39000, 0] }, { nome: '2', a: [29000, 10000], b: [39000, 10000] }],
        niveis: [{ nome: 'Topo', z: 7000 }] }; 1""")
    ok(dialogo("modelar-pilares"), "o diálogo Pilares nos eixos abriu")
    n_cx = jsj("return editor.el.dialogoCorpo.querySelectorAll('input[type=checkbox]').length;")
    ok(n_cx == 4, f"4 cruzamentos para escolher: {n_cx}")
    ok(esperar(f"{PREVIA} === 4", 20), f"a prévia com os 4 pilares: {js(PREVIA)}")
    js("[...editor.el.dialogoCorpo.querySelectorAll('input[type=checkbox]')].slice(2).forEach(c => { c.checked = false; c.dispatchEvent(new Event('change', { bubbles: true })); }); 1")
    ok(esperar(f"{PREVIA} === 2", 20), f"desmarcar 2 cruzamentos tira 2 pilares da prévia: {js(PREVIA)}")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'pilar')"), "os pilares entraram")
    pil = jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'pilar').map(e => [e.inicio, e.fim, e.nome]);")
    ok(len(pil) == 2 and all(p[1][2] == 7000 for p in pil), f"2 pilares (A-1, A-2) até o nível +7,00: {pil}")
    erros("Pilares")

    # 4) viga entre os pilares
    selecionar(*jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'pilar').map(e => e.id);"))
    ok(dialogo("modelar-viga"), "o diálogo Viga entre pilares abriu")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'viga')"), "a viga entrou")
    vg = jsj("const v = [...editor.documento.entidades.values()].find(e => e.papel === 'viga'); return [v.inicio, v.fim];")
    ok(vg and abs(vg[0][2] - (7000 - 155)) < 1 and {round(vg[0][1]), round(vg[1][1])} == {0, 10000}, f"viga de A-1 a A-2 com o topo em +7,00: {vg}")
    erros("Viga")

    # 5) contraventamento em X entre os dois pilares
    selecionar(*jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'pilar').map(e => e.id);"))
    ok(dialogo("modelar-contravento"), "o diálogo Contraventamento abriu")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'contraventamento')"), "o contraventamento entrou")
    ok(conta("contraventamento") == 4, f"2 painéis × 2 diagonais: {conta('contraventamento')}")
    erros("Contraventamento")

    # 5b) longarinas nos dois pilares do eixo A (a parede ao longo de y; o resto do modelo fica em x < 30000)
    selecionar(*jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'pilar').map(e => e.id);"))
    ok(dialogo("modelar-longarinas"), "o diálogo Longarinas abriu")
    ok(esperar(f"{PREVIA} > 0", 20), f"a prévia das longarinas: {js(PREVIA)}")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'longarina')"), "as longarinas entraram")
    lg = jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'longarina').map(e => [e.inicio, e.fim]);")
    zs = sorted({round(x[0][2]) for x in lg})
    ok(zs and zs[0] == 1900 and zs[-1] == 6700 and len(lg) == len(zs), f"fiadas de 1,90 a 6,70 m, uma por vão: {zs}")
    ok(all(x[0][0] > 30000 for x in lg), f"na face de fora (x > 30000, longe do resto do modelo): {lg[0] if lg else None}")
    erros("Longarinas")

    # 5c) terças nas tesouras de novo e as correntes entre elas
    selecionar(ids["T1"], ids["T2"]); dialogo("modelar-tercas"); esperar(f"{PREVIA} === 5", 20); ok_dialogo()
    esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'terça')")
    selecionar(*jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'terça').map(e => e.id);"))
    ok(dialogo("modelar-correntes"), "o diálogo Correntes abriu")
    ok(esperar(f"{PREVIA} === 4", 20), f"a prévia: 4 correntes entre as 5 linhas: {js(PREVIA)}")
    ok_dialogo()
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.papel === 'corrente')"), "as correntes entraram")
    cr = jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'corrente').map(e => [e.inicio, e.fim]);")
    ok(len(cr) == 4 and all(abs(c[0][1] - 2500) < 1 and abs(c[1][1] - 2500) < 1 for c in cr), f"no meio do vão (y 2500): {cr[:1]}")
    erros("Correntes")

    # 5d) copiar a treliça (y 20000, paralela aos eixos 1 e 2) do eixo 2 para o eixo 1: 10 m para trás
    trel = jsj("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.origem && e.atributos.origem.peca === 'TRELIÇA').map(e => e.id);")
    selecionar(*trel)
    ok(dialogo("copiar-para-eixos"), "o diálogo Copiar para os eixos abriu")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "2", "o eixo de origem sugerido é o mais perto da seleção (2)")
    nomes = jsj("return [...editor.el.dialogoCorpo.querySelectorAll('label')].filter(l => l.querySelector('input[type=checkbox]')).map(l => l.textContent.trim());")
    ok(nomes == ["1"], f"só os eixos paralelos ao de origem: {nomes}")
    js("const c = editor.el.dialogoCorpo.querySelector('input[type=checkbox]'); c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); 1")
    ok(esperar("editor.cena.previa.children.length > 0", 5), "a prévia (o fantasma) aparece no eixo 1")
    n0 = jsj("return editor.documento.entidades.size;")
    ok_dialogo()
    ok(esperar(f"editor.documento.entidades.size === {n0 + len(trel)}"), f"{len(trel)} peças copiadas")
    ys = jsj("return [...new Set(editor.selecao.entidades.map(e => Math.round((e.inicio || e.origem || [0, 0])[1])))];")
    ok(ys == [10000], f"as cópias no eixo 1 (y 20000 − 10000): {ys}")
    ok(js("editor.cena.previa.children.length") == 0, "a prévia sai ao fechar")
    js("editor.desfazer(); 1"); aba.drenar(0.4)
    ok(jsj("return editor.documento.entidades.size;") == n0, "Ctrl+Z tira as cópias de uma vez")
    erros("Copiar para os eixos")

    # 6) sem seleção: a dica, sem diálogo
    selecionar()
    menu("modelar-tercas"); aba.drenar(0.4)
    ok(not js("editor.el.dialogo.open"), "Terças sem seleção não abre diálogo (só a dica)")
    erros("Sem seleção")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
