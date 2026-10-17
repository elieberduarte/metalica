# -*- coding: utf-8 -*-
"""Corrigir pelas regras (17/10/2026), no navegador de verdade: um modelo antigo (a tesoura com os U e as cantoneiras fora da
posição, longe da origem e com uma peça de `origem` em texto, como o PRATI) acusa no Verificar apoios; o botão Corrigir
pelas regras do painel gira e encaixa tudo numa entrada de desfazer, o painel confere de novo sem a acusação, e o Ctrl+Z
volta; nenhum erro no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_corrigir_pelas_regras import _doc
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_regras_")
PASTA = os.path.join(DADOS, "antigo")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Antigo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-17T00:00:00", "alterado": "2026-10-17T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = _doc(-40000.0, 85000.0, True)
N0 = len(doc.entidades)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_regras_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=antigo", limite=60)
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

    def posicao(): return jsj("return [...document.querySelectorAll('.painel-apoios summary')].filter(s => s.textContent.startsWith('Peça da treliça fora')).map(s => s.textContent);")
    def rotacoes(): return jsj("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => e.rotacao).join(',');")
    rot0 = rotacoes()
    js("document.querySelector('[data-acao=\"verificar-apoios\"]').click(); 1")
    ok(esperar("!!document.querySelector('.painel-apoios')", 60), "o painel do Verificar apoios abriu")
    ok(bool(posicao()), f"o modelo antigo acusa peças fora da posição: {posicao()}")
    ok(js("!!document.querySelector('.painel-apoios .corrigir-regras')"), "o painel tem o botão Corrigir pelas regras")
    js("document.querySelector('.painel-apoios .corrigir-regras').click(); 1")
    ok(esperar(f"[...editor.documento.entidades.values()].filter(e => e.tipo === 'barra').map(e => e.rotacao).join(',') !== {json.dumps(rot0)}", 60),
       "as peças foram giradas")
    ok(esperar("!!document.querySelector('.painel-apoios') && ![...document.querySelectorAll('.painel-apoios summary')].some(s => s.textContent.startsWith('Peça da treliça fora'))", 60),
       f"o painel conferiu de novo sem peças fora da posição: {posicao()}")
    ok(not js("!!document.querySelector('.painel-apoios .corrigir-regras')"), "o botão some quando não há o que corrigir")
    erros("Corrigir")
    js("editor.desfazer(); 1"); aba.drenar(0.5)
    ok(rotacoes() == rot0, "Ctrl+Z volta o modelo de uma vez")
    ok(jsj("return editor.documento.entidades.size;") == N0, "o mesmo número de peças")
    erros("Desfazer")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
