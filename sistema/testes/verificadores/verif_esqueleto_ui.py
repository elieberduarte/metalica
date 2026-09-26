# -*- coding: utf-8 -*-
"""Editor 3D: Ver → Esqueleto — o modelo só em linhas (cada peça pelo eixo), o modelo com perfis
escondido, o clique pega o bloco (a treliça inteira, pela peça de origem) e desligar volta tudo."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_esqueleto_")
os.makedirs(os.path.join(DADOS, "compressores"))
# o modelo de exemplo com uma viga solta no ar, longe de tudo: um achado garantido
_m = json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8"))
_ents = _m["entidades"]
_voando = {"id": "viga-voando", "tipo": "barra", "nome": "W 200×19,3", "camada": "Estrutura", "inicio": [0.0, -30000.0, 9000.0],
           "fim": [4000.0, -30000.0, 9000.0], "perfil": "W 200×19,3", "papel": "viga", "rotacao": 0.0, "atributos": {}}
if isinstance(_ents, dict):
    _ents["viga-voando"] = _voando
else:
    _ents.append(_voando)
json.dump(_m, open(os.path.join(DADOS, "compressores", "modelo.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_esqueleto_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.entidades.size > 100"): aba.drenar(0.5)
    n_pecas = aba.avaliar("[...window.editor.documento.entidades.values()].filter(x => x.tipo === 'barra' || x.tipo === 'solido').length") or 0
    aba.avaliar("document.querySelector('[data-acao=esqueleto]').click(); 1")
    aba.drenar(1.0)
    ok(aba.avaliar("window.editor.esqueleto.ativo === true"), "Ver → Esqueleto liga")
    n_seg = aba.avaliar("window.editor.esqueleto._idDoSegmento.length") or 0
    ok(n_seg >= n_pecas > 0, f"{n_seg} trechos de linha para {n_pecas} peças (o eixo de cada uma, na hora)")
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("!!window.editor.esqueleto.analitico"): aba.drenar(0.5)
    res = aba.avaliar("window.editor.esqueleto.analitico && window.editor.esqueleto.analitico.resumo") or {}
    ok(res.get("barras", 0) > 0 and res.get("nos", 0) > 0,
       f"o modelo analítico chega do servidor: {res.get('barras')} barras em {res.get('nos')} nós, {res.get('soltas')} soltas")
    dica = aba.avaliar("(document.querySelector('#dica, .dica, [data-dica]') || {}).textContent || ''") or ""
    ok("analítico" in dica or "Esqueleto" in dica or dica == "", f"a dica diz o resumo: {dica[:90]}")
    ok(aba.avaliar("window.editor.cena.raiz.children.filter(c => c !== window.editor.cena.previa).every(c => !c.visible)"),
       "o modelo com perfis fica escondido")
    # três peças da mesma treliça (peça de origem): o clique no esqueleto pega as três
    ids = aba.avaliar("""(() => { const e = window.editor; const ids = [...e.esqueleto._faixas.keys()].slice(0, 3);
        ids.forEach(i => { const x = e.documento.get(i); x.atributos = x.atributos || {}; x.atributos.origem = { peca: 'TESOURA 9#1' }; });
        e.esqueleto._montar(); return ids; })()""") or []
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("!!window.editor.esqueleto.analitico"): aba.drenar(0.5)
    grupo = aba.avaliar(f"window.editor.esqueleto.grupoDe({ids[0]!r}).length") if ids else 0
    ok(grupo == 3, f"o grupo da treliça tem {grupo} barras (esperado 3)")
    # clique de verdade sobre o meio da primeira barra, em pixels da tela
    xy = aba.avaliar(f"""(() => {{ const e = window.editor; const [v0] = e.esqueleto._faixas.get({ids[0]!r});
        const pos = e.esqueleto.objeto.geometry.getAttribute('position');
        const m = [0, 1, 2].map(k => (pos.array[v0 * 3 + k] + pos.array[(v0 + 1) * 3 + k]) / 2 * 0.001);
        const v = e.camera.ativa.position.clone().set(m[0], m[1], m[2]).project(e.camera.ativa);
        const r = e.el.canvas.getBoundingClientRect(); return [(v.x + 1) / 2 * r.width, (1 - v.y) / 2 * r.height]; }})()""")
    e_id = aba.avaliar(f"(() => {{ const h = window.editor.selecao.sob({xy[0]}, {xy[1]}); return h && h.id; }})()") if xy else None
    ok(e_id is not None, f"o raio acha a linha do esqueleto sob o cursor ({e_id})")
    if e_id:
        aba.avaliar(f"window.editor.selecao.clicar({e_id!r}, {{}}); 1")
        n_sel = aba.avaliar("window.editor.selecao.ids.size") or 0
        ok(n_sel == (3 if e_id in ids else 1), f"o clique seleciona o bloco: {n_sel} barra(s)")
    foto(aba, "_esqueleto.png")
    aba.avaliar("document.querySelector('[data-acao=esqueleto]').click(); 1")
    aba.drenar(0.5)
    ok(aba.avaliar("!window.editor.esqueleto.ativo && !window.editor.esqueleto.objeto && window.editor.cena.raiz.children.every(c => c.visible)"),
       "desligado, volta o modelo com perfis")
    ok(aba.avaliar("window.editor.selecao.grupoDe === null && window.editor.cena.alvosExtras === null"), "e o clique volta a ser por peça")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
