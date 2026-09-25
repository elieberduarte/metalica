# -*- coding: utf-8 -*-
"""Headless: CAD 2D de ponta a ponta com o IFC do TecnoMETAL."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.parse
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = 8774
DADOS = tempfile.mkdtemp(prefix="metalica_cad_")
# projeto com o modelo já importado (reaproveita o modelo.json recentrado, sem reimportar 80 MB)
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "ME-SOORO.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=300))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cad_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # 1) rota: corte da tesoura em y = 30300 (mesmo do teste anterior), 1,5 m de profundidade
    t0 = time.time()
    r = post("/api/projetos/compressores/vista2d", {"vista": {"origem": [0, 30000, 0], "normal": [0, 1, 0], "profundidade": 1500, "cortar": True, "nome": "Corte tesoura", "tipo": "corte"}, "desenho": "Corte tesoura"})
    ok(r.get("nome") == "corte-tesoura" and r["vista"]["pecas_cortadas"] > 10, "rota vista2d gerou o corte em %.1f s: %s cortadas, %s projetadas" % (time.time() - t0, r["vista"]["pecas_cortadas"], r["vista"]["pecas_projetadas"]))
    lista = json.load(urllib.request.urlopen(base + "/api/projetos/compressores/desenhos"))
    ok(len(lista) == 1 and lista[0]["nome"] == "corte-tesoura", "desenho listado no projeto")

    # 2) abre o CAD nele
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores&desenho=corte-tesoura", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 100"): aba.drenar(0.5)
    n = aba.avaliar("window.cad.doc.tamanho")
    ok(isinstance(n, int) and n > 1000, f"CAD abriu o desenho com {n} objetos")
    ok(aba.avaliar("document.title").startswith("Corte tesoura"), "título da janela é o do desenho")
    aba.drenar(1.0); foto(aba, "cad_1_corte.png")

    # 3) ferramentas via API interna: linha por dois pontos, cota, texto; undo
    antes = n
    aba.avaliar("window.cad.ativarFerramenta('linha'); window.cad.ferramenta.onPonto([0, -500]); window.cad.ferramenta.onPonto([5000, -500]); window.cad.ferramenta.cancelar(); 1")
    aba.avaliar("window.cad.ativarFerramenta('cota'); const f = window.cad.ferramenta; f.onPonto([0, -500]); f.onPonto([5000, -500]); f.onPonto([2500, -900]); 1")
    aba.drenar(0.3)
    ok(aba.avaliar("window.cad.doc.tamanho") == antes + 2, "linha e cota criadas pelas ferramentas")
    cota = aba.avaliar("JSON.stringify([...window.cad.doc.entidades.values()].filter(e => e.tipo === 'cota').map(c => [c.modo, c.deslocamento < 0, Math.round(Math.hypot(c.p2[0]-c.p1[0], c.p2[1]-c.p1[1]))]))")
    ok('["alinhada",true,5000]' in cota, f"cota alinhada de 5000 mm com o deslocamento para baixo: {cota}")
    aba.avaliar("window.cad.desfazer(); 1")
    ok(aba.avaliar("window.cad.doc.tamanho") == antes + 1, "desfazer remove a cota")
    aba.avaliar("window.cad.refazer(); 1")
    ok(aba.avaliar("window.cad.doc.tamanho") == antes + 2, "refazer devolve")
    # entrada numérica: linha de 1200 mm a 90°
    aba.avaliar("window.cad.ativarFerramenta('linha'); window.cad.ferramenta.onPonto([6000, -500]); window.cad.ferramenta.onValor('1200<90'); window.cad.ferramenta.cancelar(); 1")
    l = aba.avaliar("JSON.stringify([...window.cad.doc.entidades.values()].filter(e => e.tipo === 'linha' && e.a[0] === 6000).map(e => e.b))")
    ok('[6000,700]' in l.replace(' ', ''), f"linha por medida digitada 1200<90: {l}")
    # seleção por janela e mover
    aba.avaliar("window.cad.selecionar([...window.cad.doc.entidades.values()].filter(e => e.tipo === 'linha' && e.a[1] === -500).map(e => e.id)); window.cad.ativarFerramenta('mover'); const m = window.cad.ferramenta; m.onPonto([0, -500], {px: [0,0]}); m.onPonto([0, -700], {px: [0,0]}); 1")
    aba.drenar(0.3)
    ok(aba.avaliar("[...window.cad.doc.entidades.values()].some(e => e.tipo === 'linha' && e.a[1] === -700)"), "mover deslocou a seleção 200 mm para baixo")
    # snap: extremidade da linha que criei
    px = aba.avaliar("JSON.stringify(window.cad.tela.paraTela([5000, -700]))")
    s = aba.avaliar(f"JSON.stringify(window.cad.snap.resolver({px}.map(v => v + 3)))")
    ok('"extremidade"' in s, f"snap acha a extremidade: {s[:90]}")
    # selecionar mesma peça (atributos.origem)
    aba.avaliar("const c = [...window.cad.doc.entidades.values()].find(e => e.tipo === 'polilinha' && e.atributos.origem); window.cad.selecionar([c.id]); window.cad.selecionarMesmaPeca(); 1")
    ok(aba.avaliar("window.cad.tela.selecao.size") >= 2, "selecionar tudo da mesma peça 3D")
    aba.avaliar("window.cad.selecionar([]); 1")
    aba.avaliar("window.cad.tela.enquadrar(); 1"); aba.drenar(0.5)
    foto(aba, "cad_2_editado.png")

    # 4) gravação automática e exportação DXF
    t0 = time.time(); arq = os.path.join(DADOS, "compressores", "desenhos-2d", "corte-tesoura.desenho.json"); m0 = os.path.getmtime(arq)
    while time.time() - t0 < 20 and os.path.getmtime(arq) <= m0: aba.drenar(1.0)
    ok(os.path.getmtime(arq) > m0, "gravação automática regravou o desenho")
    d = json.load(open(arq, encoding="utf-8"))
    ok(any(e["tipo"] == "cota" for e in d["entidades"]), "a cota está no arquivo gravado")
    aba.avaliar("window.cad.exportarDXF(); 1")
    # o arquivo aparece antes de a ezdxf terminar de escrevê-lo: espera o aviso da tela
    fim_dxf = "[...document.querySelectorAll('.aviso')].map(a => a.textContent).find(t => /DXF gerado|Não foi possível exportar/.test(t)) || ''"
    t0 = time.time(); dxf = os.path.join(DADOS, "compressores", "desenhos-2d", "corte-tesoura.dxf")
    while time.time() - t0 < 60 and not aba.avaliar(fim_dxf): aba.drenar(1.0)
    ok(os.path.exists(dxf) and "DXF gerado" in aba.avaliar(fim_dxf), "DXF exportado pelo botão: %s" % aba.avaliar(fim_dxf)[:120])
    if os.path.exists(dxf):
        txt = open(dxf, encoding="cp1252", errors="replace").read()
        # DXF R2010 (nucleo2d/dxf_cad.py): as camadas do CAD vão com o nome delas (a peça
        # cortada em CORTE, a vista em VISTA; o ACO era do DXF R12 antigo), a cota vira
        # DIMENSION e a hachura, HATCH
        import re as _re
        camadas = set(_re.findall(r"\n  8\n([A-Za-z][^\n]*)\n", txt))
        tipos = set(_re.findall(r"\n\s*0\n([A-Z_]+)\n", txt))
        ok(txt.rstrip().endswith("EOF") and {"CORTE", "VISTA", "COTA", "HACHURA"} <= camadas and {"DIMENSION", "HATCH"} <= tipos,
           "DXF com camadas CORTE, VISTA, COTA e HACHURA, cota DIMENSION e HATCH (%s)" % sorted(camadas))
        from saida import dxf_render
        dxf_render.para_png(dxf, os.path.join(SCR, "cad_3_dxf.png"), dpi=80, largura=16)

    # 5) inserir vista padrão (planta) no mesmo desenho pela interface
    aba.avaliar("window.cad.inserirVista({padrao: 'topo', rotular: false}, 'Planta'); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("window.cad.doc.vistas.length") < 2: aba.drenar(1.0)
    ok(aba.avaliar("window.cad.doc.vistas.length") == 2, "segunda vista inserida no desenho (%s objetos)" % aba.avaliar("window.cad.doc.tamanho"))
    aba.drenar(1.0); foto(aba, "cad_4_duas_vistas.png")

    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:8]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
