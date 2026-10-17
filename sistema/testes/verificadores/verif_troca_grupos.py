# -*- coding: utf-8 -*-
"""Trocar perfis por grupo (16/10/2026, a ferramenta dos estudos), no navegador de verdade: pelo menu Lançamento, a
tabela dos grupos do modelo, a prévia (peças e peso), terças em cartola e diagonais em cantoneira dupla no OK, as peças
numeradas, o Ctrl+Z que volta tudo de uma vez e nenhum erro no console. O modelo é o do test_troca_por_grupo (duas
tesouras com terças), longe da origem (o piso longe do z = 0)."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_troca_por_grupo import CR_T, L_AL, _modelo
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_trocagr_")
PASTA = os.path.join(DADOS, "estudo")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Estudo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-16T00:00:00", "alterado": "2026-10-16T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = _modelo(z=85000.0, x=-40000.0)
N0 = len(doc.entidades)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_trocagr_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=estudo", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar(f"!!(window.editor && editor.documento && editor.documento.entidades.size >= {N0})"):
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
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    def linha(grupo, campo, valor):
        js(f"""(() => {{ const tr = editor.el.dialogoCorpo.querySelector('tr[data-grupo="{grupo}"]');
                const i = tr.querySelector({json.dumps('select' if campo == 'forma' else 'input')});
                i.value = {json.dumps(valor)}; i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                i.dispatchEvent(new Event('change', {{ bubbles: true }})); return 1; }})()""")
    def barras(cond): return jsj(f"return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra' && ({cond})).length;")

    ok(js("!!document.querySelector('[data-acao=\"trocar-grupos\"]')"), "o menu Lançamento tem Trocar perfis por grupo")
    js("document.querySelector('[data-acao=\"trocar-grupos\"]').click(); 1")
    ok(esperar("editor.el.dialogo.open && editor.el.dialogoCorpo.querySelectorAll('tr[data-grupo]').length > 0", 30), "o diálogo abriu com a tabela")
    gs = jsj("return [...new Set([...editor.el.dialogoCorpo.querySelectorAll('tr[data-grupo]')].map(tr => tr.dataset.grupo))];")
    ok(all(g in gs for g in ("tercas", "banzo_sup", "banzo_inf", "montantes", "diagonais")), f"os grupos do modelo: {gs}")
    ok(jsj("return !!editor.el.dialogoCorpo.querySelector('tr[data-grupo=\"diagonais\"] select');"), "a alma tem a escolha da forma")
    ok(not jsj("return !!editor.el.dialogoCorpo.querySelector('tr[data-grupo=\"tercas\"] select');"), "a terça não tem cantoneira dupla")
    linha("tercas", "perfil", CR_T)
    linha("diagonais", "perfil", L_AL)
    linha("diagonais", "forma", "dupla")
    js("[...editor.el.dialogoCorpo.querySelectorAll('button')].find(b => b.textContent.startsWith('Prévia')).click(); 1")
    ok(esperar("/peça\\(s\\) trocada/.test(editor.el.dialogoCorpo.querySelector('.estado-previa').textContent)", 60),
       "a prévia diz quantas peças e o peso: " + str(js("editor.el.dialogoCorpo.querySelector('.estado-previa').textContent")))
    ok(barras("e.perfil === " + json.dumps(CR_T)) == 0, "a prévia não entra no modelo")
    js("editor.el.dialogoOk.click(); 1")
    ok(esperar(f"[...editor.documento.entidades.values()].some(e => e.perfil === {json.dumps(CR_T)})", 60), "as terças viraram cartola")
    ok(barras("e.papel === 'terça' && e.perfil === " + json.dumps(CR_T)) == 3, "as 3 terças em cartola")
    npar = barras("e.atributos && e.atributos.cantoneira_dupla")
    ok(npar == 16, f"as 8 diagonais viraram 8 pares de cantoneiras: {npar}")
    ok(barras("e.papel === 'presilha'") >= 16, "as presilhas entre as cantoneiras")
    ok(barras("e.papel === 'diagonal' && /^U/.test(e.perfil)") == 0, "nenhuma diagonal em U ficou")
    sem = barras("e.atributos && e.atributos.cantoneira_dupla && !((e.atributos.marcas || {}).posicao)")
    ok(sem == 0, f"as cantoneiras novas saem numeradas: {sem} sem posição")
    conf = barras("e.atributos && e.atributos.marca_a_conferir")
    ok(conf == 0, f"as terças trocadas foram conferidas pelo Numerar: {conf} ainda a conferir")
    erros("Trocar")
    js("editor.desfazer(); 1"); aba.drenar(0.5)
    ok(barras("e.perfil === " + json.dumps(CR_T)) == 0 and barras("e.atributos && e.atributos.cantoneira_dupla") == 0,
       "Ctrl+Z volta as terças e as diagonais de uma vez")
    ok(jsj("return editor.documento.entidades.size;") == N0, "o modelo volta ao mesmo número de peças")
    erros("Desfazer")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
