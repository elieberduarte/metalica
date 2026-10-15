# -*- coding: utf-8 -*-
"""Os comandos do 3D na barra única (a tela dividida, que o usuário usa — 15/10/2026): o menu de cima é o MAPA do
web/barra_unica.js e os menus do editor.html ficam escondidos; a modelagem pela seleção, a produção, as ligações e o
lado BIM não estavam lá. Confere:
  1. Modelo › Modelar pela seleção (3D) tem os 10 comandos; Detalhamento tem a produção; Ver tem o modelo BIM;
  2. Modelo › Modelar pela seleção › Pilares nos eixos… abre o diálogo no 3D;
  3. Detalhamento › Numerar peças dá as marcas no 3D;
  4. Ver › Tabela de peças abre a tabela no 3D;
  5. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_bu_")
PASTA = os.path.join(DADOS, "bu")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Barra única", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
doc.add(Barra(nome="P1", inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 250×32,7", papel="pilar"))
doc.add(Barra(nome="P2", inicio=(8000, 0, 0), fim=(8000, 0, 6000), perfil="W 250×32,7", papel="pilar"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_bu_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=bu", limite=90)
    ED = "([...document.querySelectorAll('iframe')].map(f => { try { return f.contentWindow.editor ? f.contentWindow : null; } catch (e) { return null; } }).find(Boolean))"

    def esperar(cond, limite=60.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(0.4)
        return False
    # o 3D da tela dividida abre leve (o modo ver); o editor sobe quando um comando dele é pedido
    ok(esperar("!!document.querySelector('#menus-unicos .menu[data-nome=\"Modelo\"]') && document.querySelectorAll('iframe').length > 0", 120),
       "a tela dividida abriu com a barra única")
    aba.drenar(3.0)
    aba.console.clear()

    def itens_do_menu(nome):
        """abre o menu de cima e devolve os textos dos itens (com os dos submenus)"""
        return json.loads(aba.avaliar(f"""JSON.stringify((() => {{
            const b = document.querySelector('#menus-unicos .menu[data-nome="{nome}"] .menu-botao'); if (b) b.click();
            const m = document.querySelector('#menus-unicos .menu[data-nome="{nome}"]');
            const t = m ? [...m.querySelectorAll('button, a, li, div')].filter(e => e.children.length <= 3).map(e => (e.textContent || '').trim()) : [];
            if (b) b.click();
            return [...new Set(t)]; }})())"""))

    def clicar_item(menu, texto, sub=None):
        return aba.avaliar(f"""(() => {{
            const b = document.querySelector('#menus-unicos .menu[data-nome="{menu}"] .menu-botao'); if (b) b.click();
            const m = document.querySelector('#menus-unicos .menu[data-nome="{menu}"]');
            const achar = (re) => [...m.querySelectorAll('button, a, li, div')].find(e => e.children.length <= 3 && re.test((e.textContent || '').trim()));
            {f"const s = achar(/^{sub}/); if (s) {{ s.dispatchEvent(new MouseEvent('mouseenter', {{ bubbles: true }})); s.click(); }}" if sub else ""}
            const it = achar(/^{texto}/); if (!it) return 'sem item';
            it.click(); return 'ok'; }})()""")

    modelo = " | ".join(itens_do_menu("Modelo"))
    nomes = ["Pilares nos eixos", "Bases nos pilares dos eixos", "Viga entre pilares", "Treliça entre banzos", "Terças por espaçamento",
             "Correntes entre terças", "Mão-francesa", "Contraventamento em X", "Longarinas de fechamento", "Copiar para os eixos",
             "Aplicar ligação", "Salvar como detalhe", "Aplicar detalhe"]
    faltam = [n for n in nomes if n not in modelo]
    ok(not faltam and "Modelar pela seleção (3D)" in modelo, f"Modelo: a modelagem pela seleção, a ligação e os detalhes (faltam {faltam})")
    det = " | ".join(itens_do_menu("Detalhamento"))
    faltam = [n for n in ("Numerar peças", "Criar conjunto", "Soldar", "Converter em chapa", "Renumerar tudo", "Numeração travada",
                          "Conferir antes de detalhar") if n not in det]
    ok(not faltam, f"Detalhamento: a produção (faltam {faltam})")
    ver = " | ".join(itens_do_menu("Ver"))
    faltam = [n for n in ("Tabela de peças", "Sequência de montagem", "Etiquetas das marcas", "Salvar vista") if n not in ver]
    ok(not faltam, f"Ver: o modelo BIM (faltam {faltam})")

    # 2) Numerar peças pelo menu
    r = clicar_item("Detalhamento", "Numerar peças")
    ok(r == "ok" and esperar(f"[...{ED}.editor.documento.entidades.values()].every(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao)", 40),
       f"Detalhamento › Numerar peças deu as marcas no 3D ({r})")
    aba.drenar(1.0)
    # 3) Pilares nos eixos… pelo menu: o diálogo abre no 3D (com os eixos que o lançamento deixa no snap)
    aba.avaliar(f"""(() => {{ const w = {ED}; w.editor.inferencia.referencias = {{ eixos: [
        {{ nome: 'A', a: [0, -1000], b: [0, 9000] }}, {{ nome: 'B', a: [8000, -1000], b: [8000, 9000] }},
        {{ nome: '1', a: [-1000, 0], b: [9000, 0] }}, {{ nome: '2', a: [-1000, 8000], b: [9000, 8000] }}], niveis: [] }}; return 1; }})()""")
    r = clicar_item("Modelo", "Pilares nos eixos", sub="Modelar pela seleção")
    ok(r == "ok" and esperar(f"{ED}.editor.el.dialogo.open && {ED}.editor.el.dialogoTitulo.textContent === 'Pilares nos eixos'", 30),
       f"Modelo › Modelar pela seleção › Pilares nos eixos… abre o diálogo no 3D ({r})")
    aba.avaliar(f"{ED}.editor.el.dialogoCancelar.click(); 1"); aba.drenar(0.5)
    # 4) Tabela de peças pelo menu
    r = clicar_item("Ver", "Tabela de peças")
    ok(r == "ok" and esperar(f"!!{ED}.document.querySelector('.tabela-pecas')", 20), f"Ver › Tabela de peças abre a tabela no 3D ({r})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao") and "3d-leve" not in m[1]]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
