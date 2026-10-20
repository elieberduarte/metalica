# -*- coding: utf-8 -*-
"""Os grupos de camadas no navegador de verdade (19/10/2026, o usuário no Mercado: "criar uma layer com as telhas, calhas e
rufos agrupadas no mesmo elemento e também criar uma ferramenta para agrupar layers onde seja possível desabilitar a layer
de um grupo todo de uma vez").

No editor: o grupo aparece com um cabeçalho; o clique no olho do grupo oculta as duas camadas dele de uma vez e um Ctrl+Z
as traz de volta; a seta recolhe o grupo; "Agrupar camadas" põe outra camada no grupo. No modo ver: a caixinha do grupo
desliga as camadas dele. Cliques com o mouse (CDP), sem erros no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Camada, Documento
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_grcam_")
PASTA = os.path.join(DADOS, "grcam")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Grupo de camadas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
G = "Cobertura — telhas, calhas e rufos"
doc = Documento()
doc.camadas["Telhas"] = Camada(nome="Telhas", cor="#b07a3a", grupo=G)
doc.camadas["Calhas"] = Camada(nome="Calhas", cor="#1971c2", grupo=G)
doc.camadas["Pilares"] = Camada(nome="Pilares", cor="#495057")
for i, cam in enumerate(("Telhas", "Calhas", "Pilares") * 4):
    doc.add(Barra(nome=cam, inicio=(i * 1000.0, 0, 0), fim=(i * 1000.0, 0, 3000), perfil="U 100×50×3,00 (FF)",
                  papel="pilar", camada=cam))
for i in range(4):                                       # a estrutura fora do grupo (o sistema Metálica)
    doc.add(Barra(nome="Viga", inicio=(i * 1000.0, 5000, 3000), fim=(i * 1000.0, 9000, 3000), perfil="U 100×50×3,00 (FF)",
                  papel="viga", camada="Vigas", aco="ASTM A36"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_grcam_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)

    def clicar(js_elemento, rotulo):
        r = aba.avaliar("JSON.stringify((() => { const e = %s; if (!e) return null; e.scrollIntoView({block: 'center'});"
                        " const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())" % js_elemento)
        pos = json.loads(r or "null")
        if not pos:
            ok(False, "achar " + rotulo)
            return
        x, y = pos
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
        aba.drenar(0.6)

    def vis():
        return json.loads(aba.avaliar("JSON.stringify(Object.fromEntries([...editor.documento.camadas].map(([n, c]) => [n, c.visivel !== false])))"))

    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=grcam", limite=90)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 16)"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    aba.console.clear()
    aba.avaliar("(() => { const p = document.querySelector('.painel[data-painel=\"camadas\"]'); if (p) p.removeAttribute('data-fechado'); return 1; })()")
    aba.drenar(0.5)
    cab = "document.querySelector('#painel-camadas .grupo-camadas[data-grupo=\"%s\"]')" % G
    ok(aba.avaliar("!!" + cab), "o grupo aparece no painel de camadas com o cabeçalho")
    membros = aba.avaliar("[...document.querySelectorAll('#painel-camadas .linha[data-no-grupo] .nome')].map(e => e.textContent).join(',')")
    ok(membros == "Telhas,Calhas", f"as camadas do grupo logo abaixo, recuadas ({membros})")
    # o olho do grupo: as duas camadas de uma vez
    clicar(cab + ".querySelectorAll('button')[1]", "o olho do grupo")
    v = vis()
    ok(v["Telhas"] is False and v["Calhas"] is False and v["Pilares"] is True, f"o olho do grupo oculta as camadas dele ({v})")
    ocultas = aba.avaliar("[...editor.documento.entidades.values()].filter(e => e.camada === 'Telhas' || e.camada === 'Calhas')"
                          ".every(e => !editor.documento.aparece(e))")
    ok(ocultas is True, "as peças das camadas do grupo saem da vista")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="z", code="KeyZ", modifiers=2, windowsVirtualKeyCode=90)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="z", code="KeyZ", modifiers=2, windowsVirtualKeyCode=90)
    aba.drenar(0.8)
    v = vis()
    ok(v["Telhas"] is True and v["Calhas"] is True, f"um Ctrl+Z traz o grupo todo de volta ({v})")
    # a seta recolhe
    clicar(cab + ".querySelector('.seta-grupo')", "a seta do grupo")
    n = aba.avaliar("document.querySelectorAll('#painel-camadas .linha[data-no-grupo]').length")
    ok(n == 0, f"a seta recolhe o grupo ({n} camadas à mostra)")
    clicar(cab + ".querySelector('.seta-grupo')", "a seta do grupo")
    # Agrupar camadas: os Pilares entram no grupo
    clicar("[...document.querySelectorAll('#painel-camadas .acoes-painel button')].find(b => b.textContent.includes('Agrupar'))",
           "o botão Agrupar camadas")
    ok(aba.avaliar("editor.el.dialogo.open"), "o diálogo Agrupar camadas abre")
    aba.avaliar("(() => { const i = editor.el.dialogoCorpo.querySelector('input[list]'); i.value = %s;"
                " i.dispatchEvent(new Event('input')); return 1; })()" % json.dumps(G))
    aba.drenar(0.3)
    marcadas = aba.avaliar("[...editor.el.dialogoCorpo.querySelectorAll('input[type=checkbox]')].filter(c => c.checked).map(c => c.dataset.camada).join(',')")
    ok(marcadas == "Telhas,Calhas", f"o nome de um grupo que existe marca as camadas dele ({marcadas})")
    clicar("editor.el.dialogoCorpo.querySelector('input[data-camada=\"Pilares\"]')", "a caixinha Pilares")
    clicar("editor.el.dialogoOk", "o botão Agrupar")
    aba.drenar(0.6)
    gr = aba.avaliar("editor.documento.camadas.get('Pilares').grupo || ''")
    ok(gr == G, f"Agrupar camadas pôs os Pilares no grupo ({gr!r})")
    # gravar e abrir o modo ver
    aba.avaliar("editor.salvar ? (editor.salvar(), 1) : 1")
    aba.drenar(3.0)
    d = json.load(open(os.path.join(PASTA, "modelo.json"), encoding="utf-8"))
    ok((d["camadas"].get("Pilares") or {}).get("grupo") == G, "o grupo vai para o modelo gravado")
    aba.navegar(f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto=grcam", limite=120)
    t0 = time.time()
    while time.time() - t0 < 120 and not aba.avaliar("!!window.ver3dPronto"):
        aba.drenar(0.5)
    aba.console.clear()
    aba.avaliar("(() => { const b = [...document.querySelectorAll('button')].find(x => /Camadas/.test(x.textContent)); if (b) b.click(); return !!b; })()")
    aba.drenar(0.8)
    caixa = "document.querySelector('#painel-corpo input[data-g]')"
    ok(aba.avaliar("!!" + caixa), "o modo ver mostra o grupo com uma caixinha")
    clicar(caixa, "a caixinha do grupo no modo ver")
    vv = json.loads(aba.avaliar("JSON.stringify(visor.cabecalho.camadas.map((c, i) => [c.nome, visor.visivelCamada[i] !== false]))"))
    dele = {n: v for n, v in vv if n in ("Telhas", "Calhas", "Pilares")}
    ok(dele and not any(dele.values()), f"a caixinha do grupo desliga todas as camadas dele ({dele})")
    # 19/10 (usuário, no modo ver do Mercado: "não foi criado o grupo com as telhas, calhas e rufos"): no Pintar por
    # sistema a cobertura é um sistema só — as telhas caíam em Outros e as calhas/rufos de chapa galvanizada em Metálica
    clicar(caixa, "a caixinha do grupo no modo ver")                       # liga de novo
    aba.avaliar("(() => { const s = document.getElementById('pintar'); s.value = 'sistema';"
                " s.dispatchEvent(new Event('change')); return 1; })()")
    aba.drenar(1.0)
    leg = aba.avaliar("(document.getElementById('painel-corpo') || {}).textContent || ''")
    ok("Cobertura — telhas, calhas e rufos" in leg, "no Pintar por sistema a cobertura é um sistema só")
    ok("Outros" not in leg, "as telhas e as calhas não caem mais em Outros")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
