# -*- coding: utf-8 -*-
"""As ligações da biblioteca aplicadas no editor 3D (F13, 14/10/2026), no navegador de verdade. Num projeto sintético —
um pilar W 310 em pé e uma viga W 310 chegando na mesa dele — confere pelo menu e pelo painel:
  1. Editar → Aplicar ligação no pilar: a placa de base rotulada sai no pé, com 2 chumbadores; o pilar fica mais curto;
  2. Aplicar ligação na viga + pilar: o diálogo já sugere a chapa de topo; 8 parafusos, a viga cortada na chapa;
  3. o painel da chapa mostra o grupo "Ligação"; trocar a espessura no painel refaz a chapa (o id da ligação fica);
  4. mover o pilar abre a faixa "ligação com barra que mudou"; "Refazer as ligações" põe a placa no pé novo;
  5. "Apagar ligação" tira a chapa de topo e devolve a viga sem corte; Ctrl+Z volta tudo;
  6. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_lig3d_")
PASTA = os.path.join(DADOS, "lig")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Ligações", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
W = "W 310×38,7"
doc = Documento()
doc.add(Barra(nome="pilar", inicio=(0, 0, 0), fim=(0, 0, 4000), perfil=W, rotacao=90, papel="pilar"))
doc.add(Barra(nome="viga", inicio=(0, 0, 3500), fim=(0, 6000, 3500), perfil=W, papel="viga"))
doc.add(Barra(nome="banzo", inicio=(10000, -3000, 0), fim=(10000, 3000, 0), perfil="W 250×32,7", papel="banzo"))
doc.add(Barra(nome="diag", inicio=(0, 0, 3000), fim=(0, 5000, 0), perfil="L 2 1/2'' X 1/4''", papel="contraventamento"))
doc.add(Barra(nome="terca", inicio=(7000, 0, 222), fim=(13000, 0, 222), perfil="Ue 150×60×20×2,25", papel="terça"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_lig3d_")
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
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 5)"):
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

    # 1) placa de base no pilar
    selecionar(ids["pilar"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo Aplicar ligação abriu")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "placa_base_rotulada", "um pilar sugere a placa de base")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.tipo === 'chapa')"), "a placa de base entrou no modelo")
    cs = chapas()
    placa = cs[0] if cs else {}
    ok(placa and abs(placa["origem"][2]) < 0.01 and len(placa["furos"]) == 2, f"placa no pé com 2 furos: {placa.get('origem')}")
    ok(jsj("return [...editor.documento.entidades.values()].filter(e => e.papel === 'chumbador').length;") == 2, "2 chumbadores")
    ok(abs((ent(ids["pilar"]) or {}).get("recorte_inicio", 0) - 25.4) < 0.01, "o pilar começa em cima da placa")
    erros("Placa de base")

    # 2) chapa de topo viga × pilar
    selecionar(ids["viga"], ids["pilar"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo abriu de novo")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "chapa_topo_joelho", "viga + pilar sugere a chapa de topo")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de topo')"), "a chapa de topo entrou")
    topo = next((c for c in chapas() if c["nome"] == "Chapa de topo"), None)
    ok(topo and abs(topo["origem"][1] - 155) < 0.01 and len(topo["furos"]) == 8, "chapa de topo na mesa do pilar com 8 furos")
    viga = ent(ids["viga"])
    ok(viga and viga["cortes_inicio"] and abs(viga["cortes_inicio"][0]["ponto"][1] - 180.4) < 0.01, "a viga cortada na face da chapa")
    ok(jsj("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.parafuso).length;") == 8, "8 parafusos")
    erros("Chapa de topo")

    # 2b) a cadeirinha da terça no banzo
    selecionar(ids["terca"], ids["banzo"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo abriu para a terça")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "suporte_terca_cadeirinha", "terça + banzo sugere a cadeirinha")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Suporte de terça (base)')"), "a cadeirinha entrou")
    n_par = jsj("return [...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.parafuso).length;")
    ok(n_par == 12, f"4 parafusos da cadeirinha além dos 8 da chapa de topo: {n_par}")
    erros("Cadeirinha")

    # 2c) a chapa de nó do contravento
    selecionar(ids["diag"], ids["pilar"]); menu("aplicar-ligacao")
    ok(esperar("editor.el.dialogo.open", 20), "o diálogo abriu para a diagonal")
    ok(js("editor.el.dialogoCorpo.querySelector('select').value") == "gusset_contravento", "diagonal + pilar sugere a chapa de nó")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar("[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de nó (gusset)')"), "a chapa de nó entrou")
    erros("Gusset")

    # 3) painel da ligação: trocar a espessura refaz
    lid = topo["atributos"]["ligacao"]["id"]
    selecionar(topo["id"]); aba.drenar(0.8)
    ok("Ligação" in (js("editor.el.props.textContent") or ""), "o painel mostra o grupo Ligação")
    jsj("""const l = [...editor.el.props.querySelectorAll('label')].find(l => l.textContent.startsWith('Espessura da chapa'));
           const s = l.nextElementSibling; s.value = '19'; s.dispatchEvent(new Event('change')); return 1;""")
    ok(esperar(f"[...editor.documento.entidades.values()].some(e => e.tipo === 'chapa' && e.espessura === 19 && e.atributos.ligacao.id === '{lid}')"),
       "trocar a espessura no painel refez a chapa (mesma ligação)")
    ok(abs(ent(ids["viga"])["cortes_inicio"][0]["ponto"][1] - 174.0) < 0.01, "a viga cortada na chapa nova")
    erros("Painel da ligação")

    # 4) mover o pilar: a faixa aparece e refaz
    js(f"editor.alterarEntidades(['{ids['pilar']}'], {{ inicio: [0, 0, -500], fim: [0, 0, 4000] }}, 'baixar o pé'); 1")
    ok(esperar("!!document.querySelector('.faixa-ligacoes')", 10), "a faixa das ligações desatualizadas apareceu")
    js("document.querySelector('.faixa-ligacoes button').click(); 1")
    ok(esperar("!document.querySelector('.faixa-ligacoes')", 30), "Refazer as ligações apagou a faixa")
    placa = next((c for c in chapas() if c["nome"] == "Placa de base"), None)
    ok(placa and abs(placa["origem"][2] + 500) < 0.01, f"a placa foi para o pé novo: {placa and placa['origem']}")
    erros("Ligações desatualizadas")

    # 5) apagar a chapa de topo; Ctrl+Z
    topo = next((c for c in chapas() if c["nome"] == "Chapa de topo"), None)
    selecionar(topo["id"]); aba.drenar(0.6)
    js("[...editor.el.props.querySelectorAll('button')].find(b => b.textContent === 'Apagar ligação').click(); 1")
    ok(esperar("![...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de topo')"), "Apagar ligação tirou a chapa de topo")
    v = ent(ids["viga"])
    ok(v and not v["cortes_inicio"] and not (v["atributos"] or {}).get("soldas"), "a viga voltou sem corte e sem solda")
    js("editor.desfazer(); 1"); aba.drenar(0.5)
    ok(js("[...editor.documento.entidades.values()].some(e => e.nome === 'Chapa de topo')"), "Ctrl+Z volta a chapa de topo")
    erros("Apagar")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
