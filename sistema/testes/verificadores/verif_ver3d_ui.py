# -*- coding: utf-8 -*-
"""O modo "ver" do modelo 3D (web/visor3d/ver3d.html), pelo caminho de sempre (cartão do projeto →
/dividida?…&vista=3d): o 3D abre leve (o 3D leve preparado no servidor, saida/modelo_leve.py), o clique dá a
ficha da peça, Medir mede entre dois pontos das peças, Pintar por perfil e por camada dá a legenda, as
camadas ligam e desligam, a busca acha a peça; Editar carrega o editor no mesmo quadro com a mesma vista e a
peça escolhida; um comando de edição da barra também leva ao editor; /editor direto continua o editor.
Porta livre, nunca a 8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ver3d_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)
json.dump({"nome": "Obra do modo ver", "tipo": "ifc", "alterado": "2026-10-06T09:00:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
F3 = "document.getElementById('f3d').contentWindow"


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.4)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


def clicar(aba, x, y):
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button="left", clickCount=1)
    aba.drenar(0.2)


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ver3d_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)

    aba.navegar(base + "/dividida?projeto=obra&vista=3d", limite=60)
    ok(esperar(aba, F3 + ".ver3dPronto && " + F3 + ".ver3dPronto.pecas === 67", 90), "o cartão do projeto abre o 3D no modo ver (67 peças)")
    ok("/visor3d/ver3d.html" in (aba.avaliar("document.getElementById('f3d').getAttribute('src')") or ""), "o quadro 3D da área é o visor")
    ok(not aba.avaliar("!!" + F3 + ".editor"), "sem o editor carregado")
    foto(aba, "ver3d_1_aberto.png")
    r = aba.avaliar("(() => { const r = document.getElementById('f3d').getBoundingClientRect(); return [r.left, r.top]; })()")

    # o clique na viga dá a ficha
    xy = aba.avaliar(f"(() => {{ const v = {F3}.visor; const i = v.fichas.findIndex(f => f.id === 'b1'); const [x, y] = v.paraTela(i); return [x, y, i]; }})()")
    clicar(aba, r[0] + xy[0], r[1] + xy[1])
    ok(esperar(aba, F3 + ".visor.selecionada === " + str(xy[2]) + " && " + F3 + ".document.getElementById('painel-titulo').textContent === 'viga'", 10),
       "o clique na viga dá a ficha dela")
    ok("W 200×22,5" in (aba.avaliar(F3 + ".document.getElementById('painel-corpo').textContent") or ""), "a ficha mostra o perfil")

    # medir entre a viga e a chapa
    aba.avaliar(F3 + ".document.getElementById('btn-medir').click()")
    pts = aba.avaliar(f"""(() => {{ const v = {F3}.visor; return ['b1', 'h1'].map(id => {{ const i = v.fichas.findIndex(f => f.id === id); const [x, y] = v.paraTela(i); return [x, y]; }}); }})()""")
    for p in pts:
        clicar(aba, r[0] + p[0], r[1] + p[1])
    ok(esperar(aba, F3 + ".ultimaMedida && " + F3 + ".ultimaMedida.mm > 100", 10), "Medir: distância entre dois pontos das peças")
    m = aba.avaliar(F3 + ".ultimaMedida") or {}
    ok(abs(m.get("mm", 0) - (sum(x * x for x in m.get("d", [0])) ** 0.5)) < 0.01, f"a distância é a dos três deltas ({m.get('mm', 0):.1f} mm)")
    foto(aba, "ver3d_2_medir.png")
    aba.avaliar(F3 + ".document.getElementById('btn-medir').click()")

    # pintar
    for modo, minimo in (("perfil", 3), ("camada", 3)):
        aba.avaliar(f"(() => {{ const s = {F3}.document.getElementById('pintar'); s.value = '{modo}'; s.dispatchEvent(new Event('change')); return 1; }})()")
        n = aba.avaliar(F3 + ".document.querySelectorAll('#painel-corpo .linha-lista').length")
        ok(n >= minimo, f"Pintar por {modo}: legenda com {n} grupos")
    foto(aba, "ver3d_3_pintar.png")
    aba.avaliar(f"(() => {{ const s = {F3}.document.getElementById('pintar'); s.value = 'material'; s.dispatchEvent(new Event('change')); return 1; }})()")

    # camadas e busca
    aba.avaliar(F3 + ".document.querySelector('[data-painel=camadas]').click()")
    n = aba.avaliar(F3 + ".document.querySelectorAll('#painel-corpo input[data-c]').length")
    ok(n == 3, f"Camadas: as 3 camadas com peças ({n})")
    aba.avaliar(F3 + ".document.querySelector('#painel-corpo input[data-c]').click()")
    ok(aba.avaliar(F3 + ".visor.visivelCamada.filter(x => x === false).length") >= 1, "desligar uma camada a esconde")
    aba.avaliar(F3 + ".document.querySelector('#painel-corpo input[data-c]').click()")
    aba.avaliar(f"(() => {{ const b = {F3}.document.getElementById('busca'); b.value = 'chapa de base'; b.dispatchEvent(new Event('input')); return 1; }})()")
    ok(esperar(aba, F3 + ".document.querySelectorAll('#painel-corpo .linha-lista').length === 1", 5), "a busca acha a chapa")

    # o vínculo com o 2D ao lado: a peça escolhida aqui vai para a tela de fora ('sel3d') ...
    aba.avaliar("window.__sel3d = []; window.addEventListener('message', e => { if (e.data && e.data.metalica === 'sel3d') window.__sel3d.push(e.data); }); 1")
    clicar(aba, r[0] + xy[0], r[1] + xy[1])
    ok(esperar(aba, "window.__sel3d.length && window.__sel3d[window.__sel3d.length - 1].marcas.ids[0] === 'b1'", 5), "escolher no 3D avisa o 2D (sel3d com a peça)")
    s3 = aba.avaliar("window.__sel3d[window.__sel3d.length - 1]") or {}
    cx = s3.get("caixa") or [[0, 0], [0, 0]]
    ok(abs(cx[0][0] - 0) < 2 and abs(cx[1][0] - 6000) < 120, f"com a caixa da viga em planta ({cx})")
    # ... e a escolhida no 2D chega como 'selecionar3d' e fica em destaque aqui
    aba.avaliar(F3 + ".postMessage({ metalica: 'selecionar3d', destacar: 'ids:h1,c0' }, location.origin); 1")
    ok(esperar(aba, F3 + ".visor.selecaoVarias.size === 2 && " + F3 + ".visor.emDestaque", 5), "escolher no 2D destaca as peças no 3D (o resto esmaecido)")
    aba.avaliar(F3 + ".postMessage({ metalica: 'selecionar3d', caixa: [[-100, 2900], [3000, 3100]], folga: 50 }, location.origin); 1")
    ok(esperar(aba, F3 + ".visor.selecaoVarias.size >= 10", 5), f"uma região escolhida no 2D destaca as peças dela ({aba.avaliar(F3 + '.visor.selecaoVarias.size')})")
    foto(aba, "ver3d_4_do2d.png")
    # o tema da barra troca o fundo do 3D na hora
    escuro0 = aba.avaliar(F3 + ".visor.escuro")
    aba.avaliar("window.barraUnica.executar({ fn: 'tema' }); 1")
    ok(esperar(aba, F3 + ".visor.escuro === " + ("false" if escuro0 else "true") + " && " + F3 + ".document.documentElement.getAttribute('data-tema') === document.documentElement.getAttribute('data-tema')", 5),
       "trocar o tema na barra troca o fundo e o piso do 3D na hora")
    ok(aba.avaliar(F3 + ".visor.piso && " + F3 + ".visor.piso.visible && " + F3 + ".visor.piso.position.z < -100"), "o piso fica sob o modelo")
    aba.avaliar("window.barraUnica.executar({ fn: 'tema' }); 1")

    # Editar: o editor no mesmo quadro, com a mesma vista e a mesma peça
    xy = aba.avaliar(f"(() => {{ const v = {F3}.visor; v.enquadrar('iso'); const i = v.fichas.findIndex(f => f.id === 'b1'); const [x, y] = v.paraTela(i); return [x, y, i]; }})()")
    aba.drenar(0.3)
    clicar(aba, r[0] + xy[0], r[1] + xy[1])
    cam = aba.avaliar(F3 + ".visor.lerCamera()")
    aba.avaliar(F3 + ".document.getElementById('btn-editar').click()")
    ok(esperar(aba, F3 + ".editor && " + F3 + ".editor.documento && " + F3 + ".editor.documento.entidades.size > 60", 90), "Editar carrega o editor no quadro")
    aba.drenar(1.5)
    ed = aba.avaliar(f"(() => {{ const e = {F3}.editor; const p = e.camera.ativa.position, t = e.camera.controles.target; return {{ v: [p.x, p.y, p.z, t.x, t.y, t.z].map(x => x * 1000), sel: [...e.selecao.ids] }}; }})()") or {}
    dif = max(abs(a - b) for a, b in zip(ed.get("v", [1e9] * 6), cam["posicao"] + cam["alvo"]))
    ok(dif < 1.0, f"o editor abre com a mesma vista (diferença {dif:.2f} mm)")
    ok(ed.get("sel") == ["b1"], f"e com a peça escolhida no visor selecionada ({ed.get('sel')})")
    foto(aba, "ver3d_5_editor.png")

    # do editor de volta ao modo ver: o botão Ver, com a mesma vista e a mesma seleção
    ok(aba.avaliar("!!" + F3 + ".document.getElementById('btn-voltar-ver')"), "o editor tem o botão Ver")
    aba.avaliar(f"(() => {{ const e = {F3}.editor; e.camera.irPara(e.camera.ativa.position.clone().multiplyScalar(1.1), e.camera.controles.target.clone(), null, 1); return 1; }})()")
    aba.drenar(0.3)
    camEd = aba.avaliar(f"(() => {{ const e = {F3}.editor; const p = e.camera.ativa.position, t = e.camera.controles.target; return [p.x, p.y, p.z, t.x, t.y, t.z].map(x => x * 1000); }})()")
    aba.avaliar(F3 + ".document.getElementById('btn-voltar-ver').click()")
    ok(esperar(aba, F3 + ".ver3dPronto && " + F3 + ".visor && " + F3 + ".visor.selecaoVarias.size === 1", 60), "Ver volta ao modo ver no mesmo quadro, com a peça selecionada")
    cv = aba.avaliar(F3 + ".visor.lerCamera()") or {}
    dif = max(abs(a - b) for a, b in zip(cv.get("posicao", [1e9] * 3) + cv.get("alvo", [1e9] * 3), camEd))
    ok(dif < 1.0, f"e com a mesma vista do editor (diferença {dif:.2f} mm)")
    ok("/visor3d/ver3d.html" in (aba.avaliar("document.getElementById('f3d').getAttribute('src')") or ""), "o quadro voltou a ser o visor")

    # um comando de edição da barra, com o 3D no modo ver, também leva ao editor
    aba.navegar(base + "/dividida?projeto=obra&vista=3d", limite=60)
    ok(esperar(aba, F3 + ".ver3dPronto", 60), "de volta ao modo ver")
    aba.avaliar("window.barraUnica.executar({ lado: '3d', acao: 'comando-de-teste' })")
    ok(esperar(aba, F3 + ".editor && " + F3 + ".editor.documento && " + F3 + ".editor.documento.entidades.size > 60", 90),
       "um comando de edição da barra carrega o editor")

    # /editor direto continua o editor (outras telas, verificadores)
    aba.navegar(base + "/editor?projeto=obra", limite=60)
    ok(esperar(aba, "location.pathname === '/editor' && window.editor && window.editor.documento && window.editor.documento.entidades.size > 60", 60),
       "/editor?projeto= direto continua abrindo o editor")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "comando não achado" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
