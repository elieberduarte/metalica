# -*- coding: utf-8 -*-
"""Trocar o tipo da ligação de contravento no editor 3D (FERRAMENTA · LIGAÇÕES, 23/10/2026), no navegador de verdade.
O pedido do usuário: "onde o cliente pediu, eu só clico nas ligações e mudo o tipo (castanha, duas chapas, cantoneira
cortada…)". No nó do print (dois tirantes em V na viga W 310) e num segundo nó de um tirante só, confere:
  1. a viga + os tirantes sugerem a castanha; aplicar dá uma ligação por nó (2), com as castanhas;
  2. clicar numa peça: o painel mostra o tipo como escolha da família; trocar para "duas chapas" refaz no lugar
     (mesmo id, as mesmas barras), e Ctrl+Z volta a castanha;
  3. "Todas iguais a esta" seleciona as duas ligações; o painel "Ligações" troca as duas para a cantoneira cortada
     de uma vez, e um Ctrl+Z só volta as duas;
  4. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ligtroca_")
PASTA = os.path.join(DADOS, "lig")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Ligações", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
Z = 156.5 + 45.0
doc = Documento()
doc.add(Barra(nome="viga", inicio=(0, 0, 0), fim=(7200, 0, 0), perfil="W 310 X 32,7", papel="viga"))
doc.add(Barra(nome="cv1", inicio=(0, -4300, Z), fim=(3600, 0, Z), perfil="FE RED 1/2''", papel="contraventamento"))
doc.add(Barra(nome="cv2", inicio=(7200, -4300, Z), fim=(3600, 0, Z), perfil="FE RED 1/2''", papel="contraventamento"))
doc.add(Barra(nome="cv3", inicio=(1000, -4300, Z), fim=(6500, 0, Z), perfil="FE RED 1/2''", papel="contraventamento"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ligtroca_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=lig", limite=60)
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
    def ent(i): return jsj(f"const e = editor.documento.get('{i}'); return e ? JSON.parse(JSON.stringify(e)) : null;")
    def chapas(): return jsj("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').map(e => JSON.parse(JSON.stringify(e)));")
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)

    def tipos_das_ligacoes():
        return jsj("const r = {}; for (const e of editor.documento.entidades.values()) { const l = e.atributos && e.atributos.ligacao; if (l) r[l.id] = l.tipo; } return r;")

    # 1) aplicar: a castanha, uma ligação por nó
    selecionar(ids["viga"], ids["cv1"], ids["cv2"], ids["cv3"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo Aplicar ligação abriu")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "castanha_contravento", "viga + tirantes sugerem a castanha")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Castanha')"), "as castanhas entraram")
    t = tipos_das_ligacoes()
    ok(len(t) == 2 and set(t.values()) == {"castanha_contravento"}, f"uma ligação por nó: {t}")
    erros("Aplicar castanha")

    # 2) trocar o tipo de uma pelo painel
    no2 = jsj(f"return [...editor.documento.entidades.values()].find(e => e.nome === 'Castanha' && e.atributos.ligacao.pecas.includes('{ids['cv1']}')).id;")
    lid = ent(no2)["atributos"]["ligacao"]["id"]
    selecionar(no2); aba.drenar(0.8)
    opcoes = jsj("""const l = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Tipo');
                    const s = l && l.nextElementSibling; return s && s.tagName === 'SELECT' ? [...s.options].map(o => o.value) : null;""")
    ok(opcoes and set(opcoes) == {"castanha_contravento", "duas_chapas_contravento", "cantoneira_contravento"},
       f"o painel oferece as variantes da família: {opcoes}")
    jsj("""const l = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Tipo');
           const s = l.nextElementSibling; s.value = 'duas_chapas_contravento'; s.dispatchEvent(new Event('change')); return 1;""")
    ok(esperar(f"[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa 80×80' && e.atributos.ligacao.id === '{lid}')"),
       "trocar no painel pôs as duas chapas (mesma ligação)")
    t = tipos_das_ligacoes()
    ok(t.get(lid) == "duas_chapas_contravento" and len(t) == 2, f"a outra ficou castanha: {t}")
    ok(not js(f"[...editor.documento.entidades.values()].some(e => e.nome === 'Castanha' && e.atributos.ligacao.id === '{lid}')"),
       "as castanhas do nó saíram")
    js("editor.desfazer(); 1"); aba.drenar(0.6)
    ok(tipos_das_ligacoes().get(lid) == "castanha_contravento", "Ctrl+Z volta a castanha")
    erros("Trocar uma")

    # 3) todas iguais a esta → trocar as duas de uma vez
    selecionar(no2); aba.drenar(0.8)
    js("[...editor.el.props.querySelectorAll('button')].find(b => b.textContent === 'Todas iguais a esta').click(); 1"); aba.drenar(0.8)
    ok("2 × " in (js("editor.el.props.textContent") or ""), "o painel mostra as 2 ligações selecionadas")
    jsj("""const g = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent === 'Tipo');
           const s = g.nextElementSibling; s.value = 'cantoneira_contravento'; s.dispatchEvent(new Event('change')); return 1;""")
    ok(esperar("Object.values((() => { const r = {}; for (const e of editor.documento.entidades.values()) { const l = e.atributos && e.atributos.ligacao; if (l) r[l.id] = l.tipo; } return r; })()).every(t => t === 'cantoneira_contravento')"),
       "as duas viraram cantoneira cortada")
    ok(not js("[...editor.documento.entidades.values()].some(e => e.nome === 'Castanha')"), "nenhuma castanha ficou")
    js("editor.desfazer(); 1"); aba.drenar(0.6)
    t = tipos_das_ligacoes()
    ok(len(t) == 2 and set(t.values()) == {"castanha_contravento"}, f"um Ctrl+Z só volta as duas: {t}")
    erros("Trocar todas")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
