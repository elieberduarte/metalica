# -*- coding: utf-8 -*-
"""Lançamento sobre o arquitetônico, pelas telas: projeto novo a partir do arquitetônico,
DXF do cliente na Planta de lançamento (travado, em cinza), malha de eixos, gravar os
eixos, Lançar estrutura no 3D (arquitetônico e eixos no chão), memorial do lançamento.

Sobe o servidor próprio numa pasta temporária (nunca a porta 8765 do programa instalado)
e gera o arquitetônico de teste com a ezdxf: galpão 15 × 30 m em centímetro, com
coordenadas grandes, como um DWG de topografia."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_lanc_")


def arquitetonico_dxf(caminho):
    import ezdxf
    d = ezdxf.new("R2010"); d.header["$INSUNITS"] = 5            # cm
    m = d.modelspace()
    X0, Y0 = 350000.0, 780000.0

    def r(x0, y0, x1, y1, camada):
        m.add_lwpolyline([(X0 + x0, Y0 + y0), (X0 + x1, Y0 + y0), (X0 + x1, Y0 + y1), (X0 + x0, Y0 + y1)], close=True,
                         dxfattribs={"layer": camada})
    r(-15, -15, 3015, 1515, "PAREDE"); r(0, 0, 3000, 1500, "PAREDE")
    for i in range(6):
        x = i * 600
        r(x - 15, -15, x + 15, 15, "PILAR"); r(x - 15, 1485, x + 15, 1515, "PILAR")
    m.add_line((X0 + 1200, Y0 - 15), (X0 + 1600, Y0 - 15), dxfattribs={"layer": "PORTAO"})
    m.add_arc((X0 + 1200, Y0 - 15), 400, 270, 360, dxfattribs={"layer": "PORTAO"})
    m.add_text("DEPÓSITO", dxfattribs={"layer": "TEXTO", "height": 40, "insert": (X0 + 1300, Y0 + 750)})
    d.saveas(caminho)


dxf = os.path.join(DADOS, "arquitetonico.dxf")
arquitetonico_dxf(dxf)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(60):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)


def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c:
        falhas.append(m)


def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr):
                return True
        except Exception:
            pass
        aba.drenar(0.3)
    return False


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_lanc_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos:
            break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"):
        aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)

    # 1) tela inicial: a porta nova
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1")
    aba.navegar(base + "/")
    ok(esperar(aba, "!!document.querySelector('#btn-novo-arquitetonico')", 15), "tela inicial tem 'Novo a partir do arquitetônico…'")
    criado = post("/api/projetos", {"nome": "Depósito lançado", "tipo": "lancamento"})
    s = criado["slug"]
    ok(criado.get("tipo") == "lancamento" or get("/api/projetos/" + urllib.parse.quote(s))["projeto"]["tipo"] == "lancamento",
       "projeto do tipo lançamento criado: %s" % s)

    # 2) CAD pede o arquitetônico e importa o DXF (o seletor de arquivo não abre sem janela:
    #    o arquivo entra pelo mesmo método que o seletor chama)
    aba.console.clear()
    aba.navegar(base + "/cad?projeto=%s&arquitetonico=1" % urllib.parse.quote(s), limite=30)
    ok(esperar(aba, "document.body.dataset.pronto === '1'", 30), "CAD carregou")
    ok(esperar(aba, "document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent.includes('Arquitetônico')", 10),
       "CAD abriu o diálogo pedindo o arquitetônico")
    aba.avaliar("document.querySelector('#dialogo-cancelar').click(); 1")
    b64 = base64.b64encode(open(dxf, "rb").read()).decode()
    aba.avaliar("window.__arq = new File([Uint8Array.from(atob('%s'), c => c.charCodeAt(0))], 'arquitetonico.dxf'); 1" % b64)
    aba.avaliar("window.__imp = cad.importarArquitetonico(window.__arq); 1")
    ok(esperar(aba, "document.querySelector('#dialogo').open", 10), "diálogo de importação aberto")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar(aba, "cad.nomeDesenho === 'planta-de-lançamento' && cad.doc.tamanho > 10", 40),
       "planta de lançamento aberta com o arquitetônico (%s objetos)" % aba.avaliar("cad.doc.tamanho"))
    arq = aba.avaliar("[...cad.doc.camadas.values()].filter(c => c.nome.startsWith('ARQ ')).map(c => [c.nome, c.bloqueada, c.cor])")
    ok(arq and all(c[1] for c in arq), "camadas do arquitetônico travadas e cinza: %s" % arq)
    largura = aba.avaliar("(() => { const c = cad.doc.caixa(); return c ? Math.round(c[1][0] - c[0][0]) : 0; })()")
    ok(29000 < (largura or 0) < 32000, "arquitetônico em milímetro real (largura %s mm; o arquivo estava em cm)" % largura)
    aba.drenar(1.0)
    foto(aba, "lanc_1_arquitetonico.png")

    # 3) malha de eixos pelo diálogo (origem no centro do pilar do canto)
    aba.avaliar("window.__malha = cad.dialogoMalha({x: '150', y: '150', numeros: '5x6000', letras: '15000'}); 1")
    ok(esperar(aba, "document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Malha de eixos'", 10),
       "diálogo Malha de eixos aberto")
    foto(aba, "lanc_2_malha_dialogo.png")
    aba.avaliar("document.querySelector('#dialogo-ok').click(); 1")
    ok(esperar(aba, "[...cad.doc.entidades.values()].filter(e => e.camada === 'EIXO' && e.tipo === 'linha').length === 8", 20),
       "malha desenhada: 8 linhas na camada EIXO")
    cotas = aba.avaliar("[...cad.doc.entidades.values()].filter(e => e.tipo === 'cota' && e.atributos && e.atributos.malha).length")
    ok(cotas == 7, "cotas da malha entre eixos e totais: %s" % cotas)
    aba.avaliar("cad.tela.enquadrar(); 1"); aba.drenar(1.0)
    foto(aba, "lanc_3_malha.png")

    # 4) gravar eixos
    aba.avaliar("window.__g = cad.gravarEixos(); 1")
    ok(esperar(aba, "[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('Eixos gravados'))", 20), "aviso dos eixos gravados")
    L = get("/api/projetos/%s/lancamento" % urllib.parse.quote(s))
    ok(L["geometria"] and abs(L["geometria"]["vao"] - 15000) < 1 and len(L["geometria"]["espacamentos"]) == 5,
       "eixos no projeto: vão %s mm, %s vãos" % (L["geometria"] and L["geometria"]["vao"], L["geometria"] and len(L["geometria"]["espacamentos"])))
    aba.avaliar("cad.gravarConfirmado().then(() => window.__gravado = 1); 1")
    esperar(aba, "window.__gravado === 1", 20)

    # 5) 3D: diálogo Lançar estrutura, lançar, modelo lançado com a referência no chão
    aba.console.clear()
    aba.navegar(base + "/editor?projeto=%s&lancar=1" % urllib.parse.quote(s), limite=40)
    ok(esperar(aba, "document.querySelector('#dialogo') && document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo, .dialogo-titulo, dialog h2') !== null", 30),
       "editor 3D abriu o diálogo Lançar estrutura")
    foto(aba, "lanc_4_dialogo_lancar.png")
    titulo = aba.avaliar("editor.el.dialogoTitulo.textContent")
    ok("Lançar" in (titulo or ""), "título do diálogo: %s" % titulo)
    aba.avaliar("editor.el.dialogoOk.click(); 1")
    ok(esperar(aba, "editor.el.dialogo.open && editor.el.dialogoTitulo.textContent === 'Estrutura lançada'", 90), "estrutura lançada (diálogo do resultado)")
    foto(aba, "lanc_5_lancado.png")
    aba.avaliar("editor.el.dialogoOk.click(); 1")
    ok(esperar(aba, "window.editor && editor.documento && editor.documento.entidades.size > 300", 60),
       "modelo lançado aberto no 3D: %s entidades" % aba.avaliar("window.editor && editor.documento.entidades.size"))
    ok(esperar(aba, "!!(editor._referencia && editor._referencia.children.length >= 2)", 20),
       "arquitetônico e eixos no chão do 3D (%s objetos no grupo)" % aba.avaliar("editor._referencia && editor._referencia.children.length"))
    aba.avaliar("editor.camera.vista('isometrica'); editor.camera.zoomExtensao(); 1"); aba.drenar(2.0)
    foto(aba, "lanc_6_modelo_iso.png")
    aba.avaliar("editor.camera.vista('topo'); editor.camera.zoomExtensao(); 1"); aba.drenar(1.5)
    foto(aba, "lanc_7_modelo_topo.png")
    # o pilar do canto está no cruzamento dos eixos 1 e A (centro do pilar de concreto: 150, 150)
    pil = aba.avaliar("(() => { const b = [...editor.documento.entidades.values()].find(e => e.tipo === 'barra' && e.papel === 'pilar'); return b ? [b.inicio, (b.atributos.marcas || {}).posicao] : null; })()")
    ok(pil and abs(pil[0][0] - 150) < 1 and abs(pil[0][1] - 150) < 1, "primeiro pilar no cruzamento 1-A: %s" % pil)
    aba.avaliar("editor.alternarReferencia(); 1")
    ok(aba.avaliar("editor._referencia.visible === false"), "Ver → Arquitetônico e eixos esconde a referência")
    aba.avaliar("editor.alternarReferencia(); 1")

    # 6) memorial do dimensionamento
    aba.avaliar("window.__m = editor.memorialDoLancamento(); 1")
    ok(esperar(aba, "[...document.querySelectorAll('.aviso')].some(a => a.textContent.includes('Memorial gravado'))", 180), "memorial do lançamento gerado")
    pdf = os.path.join(DADOS, s, "memorial", "lancamento", "Memorial_de_calculo.pdf")
    ok(os.path.exists(pdf) and os.path.getsize(pdf) > 200_000, "PDF do memorial em memorial/lancamento (%s kB)" % (os.path.getsize(pdf) // 1024 if os.path.exists(pdf) else 0))

    # 7) o modelo lançado segue o caminho de sempre: calcular e detalhar
    c = post("/api/projetos/%s/calcular" % urllib.parse.quote(s), {"parametros": {}})
    ok(c["ok"] and c["resumo"]["tesouras"] == 6, "Calcular estrutura no modelo lançado: %s tesouras" % c["resumo"].get("tesouras"))
    d = post("/api/projetos/%s/detalhar" % urllib.parse.quote(s), {})
    nomes = json.load(open(os.path.join(DADOS, s, "detalhamento", "nomes.json"), encoding="utf-8"))
    ok("pilar" in nomes["tipos_conjuntos"].values() and "tesoura" in nomes["tipos_conjuntos"].values(),
       "detalhamento: conjuntos %s" % nomes["conjuntos"])
    ok("chumbador" in nomes["tipos"].values() and "suporte_terca" in nomes["tipos"].values(),
       "ligações geradas no modelo chegam ao detalhamento (suportes de terça e chumbadores)")
    L2 = json.load(open(os.path.join(DADOS, s, "detalhamento", "lista-de-materiais.json"), encoding="utf-8"))
    ok(any("BOLT" in a["nome"] for a in L2.get("acessorios") or []), "parafusos na lista de materiais: %s" % L2.get("acessorios"))

    # 8) biblioteca de ligações
    aba.navegar(base + "/ligacoes?tipo=suporte_terca_cadeirinha", limite=30)
    ok(esperar(aba, "!!document.querySelector('#figura svg') && document.querySelectorAll('#indice button').length >= 20", 20),
       "tela de ligações com %s tipos e o desenho" % aba.avaliar("document.querySelectorAll('#indice button').length"))
    ok(esperar(aba, "document.querySelectorAll('#verif .verif').length >= 3", 20), "verificação da cadeirinha com as contas")
    aba.avaliar("(() => { const i = [...document.querySelectorAll('#esforcos input')][0]; i.value = '60'; i.dispatchEvent(new Event('change')); })(); 1")
    ok(esperar(aba, "document.querySelector('#verif .selo').textContent.includes('não atende')", 20), "esforço maior reprova na tela")
    foto(aba, "lanc_8_ligacoes.png")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erro de JavaScript" + ("" if not erros else ": %s" % erros[:3]))
finally:
    nav.kill(); srv.kill()
print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo certo")
sys.exit(1 if falhas else 0)
