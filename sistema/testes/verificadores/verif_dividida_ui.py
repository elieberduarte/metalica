# -*- coding: utf-8 -*-
"""Tela dividida (/dividida): o Desenho 2D e o modelo 3D do projeto lado a lado, e a seleção de um
lado mostrada no outro — 3D → 2D na planta (pelo deslocamento gravado pela montagem) e na elevação
(pela moldura da tela Treliças lidas); 2D → 3D pela elevação (o bloco todo) e pela planta (as peças
da região). Também: a navegação de cada lado some dentro da tela, trocar os lados, o botão Salvar
do 3D. Projeto sintético: duas cópias da TESOURA 1, a planta e a elevação dela."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_divididaui_")
PASTA = os.path.join(DADOS, "posto")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
DX, DY = -100000.0, -50000.0                  # modelo = desenho + (DX, DY)
json.dump({"formato": 1, "nome": "Posto dividido", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-27T00:00:00", "alterado": "2026-09-27T00:00:00", "dados": None,
           "planta_modelo": {"desenho": "desenho", "deslocamento": [DX, DY]}},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
ents = []


def linha(i, a, b, cam="metalica3"):
    ents.append({"id": "l%d" % i, "tipo": "linha", "camada": cam, "a": list(a), "b": list(b)})


k = 0
for y in (50000.0, 56000.0):                  # a planta: as duas tesouras (y 0 e 6000 no modelo)
    for dy in (-50.0, 50.0):
        k += 1; linha(k, (100000.0, y + dy), (108000.0, y + dy))
for x in range(0, 8001, 2000):                # a elevação: banzos, montantes, diagonais, longe da planta
    k += 1; linha(k, (100000.0 + x, 20000.0), (100000.0 + x, 21000.0))
for h in (20000.0, 21000.0):
    k += 1; linha(k, (100000.0, h), (108000.0, h))
ents.append({"id": "t1", "tipo": "texto", "camada": "REG", "posicao": [100000.0, 19500.0], "texto": "TESOURA 1 - 2X",
             "altura": 10.0, "angulo": 0, "alinhamento": "esquerda", "vertical": "base"})
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": ents, "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
CAIXA_EL = [[99600, 19300], [108400, 21900]]
json.dump({"desenho": "desenho", "montado_em": "27/09/2026 10:00",
           "trelicas": [{"nome": "TESOURA 1", "familia": "TESOURA", "qtd_projeto": 2, "no_modelo": 2, "comprimento": 8000, "altura": 1000,
                         "banzo": "U 100×40×2,25 (FF)", "alma": None, "alma_mult": 1, "membros": [["banzo", 0, 0, 8000, 0, 0]],
                         "marcas_terca": [], "contagem_membros": {"banzo": 2}, "avisos": [], "colocadas": [], "pendencias": [],
                         "situacao": "ok", "desenho": [], "caixa_desenho": CAIXA_EL}]},
          open(os.path.join(PASTA, "trelicas-lidas.json"), "w", encoding="utf-8"), ensure_ascii=False)
doc = Documento()
ids_barras = []
for conj, y in (("TESOURA 1#1", 0.0), ("TESOURA 1#2", 6000.0)):
    for z in (6000.0, 7000.0):
        b = Barra(nome="U 100×40×2,25 (FF)", inicio=(0.0, y, z), fim=(8000.0, y, z), perfil="U 100×40×2,25 (FF)", papel="banzo")
        b.atributos = {"origem": {"peca": conj, "planta": "TESOURA 1"}, "marcas": {"posicao": "P%d" % (1 if z < 6500 else 2)}}
        doc.add(b)
        ids_barras.append(b.id)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
# o detalhamento do projeto do IFC (sem ligação pela planta): a célula da posição P2 e a peça no lugar,
# na localização, com a origem dela no 3D — longe da planta e da elevação
d_ = json.load(open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), encoding="utf-8"))
d_["entidades"] += [{"id": "d1", "tipo": "linha", "camada": "VISTA", "a": [300000.0, 0.0], "b": [308000.0, 0.0],
                     "atributos": {"detalhe": "posicao", "posicao": "P2"}},
                    {"id": "d2", "tipo": "linha", "camada": "VISTA-FINA", "a": [300000.0, -9000.0], "b": [308000.0, -9000.0],
                     "atributos": {"detalhe": "localizacao", "origem": ids_barras[-1], "posicao": "P2"}}]
json.dump(d_, open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))

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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_divididaui_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
F2 = "document.querySelector('#f2d').contentWindow"
F3 = "document.querySelector('#f3d').contentWindow"
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/dividida?projeto=posto", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar(f"!!({F2}.cad && {F3}.editor && {F3}.editor.documento && {F3}.editor.documento.entidades.size === 4)"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    ok(aba.avaliar(f"!!{F2}.cad") and aba.avaliar(f"{F3}.editor.documento.entidades.size") == 4, "os dois lados abrem: o desenho e o modelo do projeto")
    ok("Posto dividido" in (aba.avaliar("document.title") or ""), "o nome do projeto no título da janela")
    t0 = time.time()
    while time.time() - t0 < 10 and not aba.avaliar(f"!!{F3}.document.querySelector('.seletor-vista a.ativo')"): aba.drenar(0.3)
    t0 = time.time()
    while time.time() - t0 < 20 and not aba.avaliar("document.querySelectorAll('#menus-unicos .menu-botao').length >= 5"): aba.drenar(0.3)
    menus_u = aba.avaliar("[...document.querySelectorAll('#menus-unicos .menu-botao')].map(b => b.textContent).join(',')") or ""
    ok(aba.avaliar("getComputedStyle(document.querySelector('.area-topo')).display") != "none"
       and aba.avaliar(f"getComputedStyle({F2}.document.querySelector('header.topo')).display") == "none"
       and aba.avaliar(f"getComputedStyle({F3}.document.querySelector('header.topo')).display") == "none"
       and aba.avaliar("document.querySelector('.vistas button.ativo').dataset.vista") == "ambos"
       and menus_u == "Arquivo,Desenhos,Estrutura,Cálculo,Ver",
       f"uma barra só, a de fora: o menu geral do 2D e do 3D ({menus_u}); as barras das telas escondidas; abre no 2D + 3D")
    ok(aba.avaliar(f"getComputedStyle({F2}.document.querySelector('#btn-voltar')).display") == "none"
       and aba.avaliar(f"getComputedStyle({F3}.document.querySelector('#link-projetos')).display") != "none",
       "a navegação de cada lado some dentro da tela dividida")
    # 3D → 2D, planta: a TESOURA 1#2 (y = 6000 no modelo) → y = 56000 no desenho
    aba.avaliar(f"""(() => {{ const e = {F3}.editor; const ids = [...e.documento.entidades.values()].filter(x => x.atributos.origem.peca === 'TESOURA 1#2').map(x => x.id);
        e.selecao.definir(ids); return ids.length; }})()""")
    aba.drenar(1.0)
    reg = aba.avaliar(f"{F2}.cad.tela.regiao") or []
    ok(bool(reg) and reg[0][0] <= 104000 <= reg[1][0] and reg[0][1] <= 56000 <= reg[1][1] and not (reg[0][1] <= 50000 <= reg[1][1] and reg[1][1] - reg[0][1] < 5000),
       f"3D → 2D: a cópia escolhida vira a região na planta do desenho {reg}")
    foto(aba, "_dividida.png")
    # 3D → 2D, elevação
    aba.avaliar(f"{F2}.document.querySelector('.ligacao-vistas [data-c=elevacao]').click(); 1"); aba.drenar(0.3)
    aba.avaliar(f"(() => {{ const e = {F3}.editor; const ids = [...e.selecao.ids]; e.selecao.definir([]); e.selecao.definir(ids); return 1; }})()")
    aba.drenar(1.0)
    reg = aba.avaliar(f"{F2}.cad.tela.regiao")
    ok(reg == CAIXA_EL, f"modo a elevação: o 2D vai para a moldura da elevação da treliça ({reg})")
    # 2D → 3D, elevação: uma linha da elevação seleciona o bloco todo (as duas cópias)
    aba.avaliar(f"{F2}.cad.selecionar(['l6']); 1")
    aba.drenar(1.0)
    n = aba.avaliar(f"{F3}.editor.selecao.ids.size")
    ok(n == 4, f"2D → 3D: uma linha da elevação seleciona a TESOURA 1 inteira no 3D ({n} barras, esperado 4)")
    # 2D → 3D, planta: a linha da planta da primeira cópia
    aba.avaliar(f"{F2}.cad.selecionar(['l1']); 1")
    aba.drenar(1.0)
    pecas = aba.avaliar(f"[...new Set([...{F3}.editor.selecao.ids].map(id => {F3}.editor.documento.get(id).atributos.origem.peca))]") or []
    ok(pecas == ["TESOURA 1#1"], f"2D → 3D: a linha da planta seleciona a cópia que está ali ({pecas})")
    # 2D → 3D pela marca (o projeto do IFC, 29/09): a célula da posição destaca as peças dela; a peça da
    # localização, ela só
    aba.avaliar(f"{F2}.cad.selecionar(['d1']); 1")
    aba.drenar(1.0)
    marcas = aba.avaliar(f"[...{F3}.editor.selecao.ids].map(id => {F3}.editor.documento.get(id).atributos.marcas.posicao).sort()") or []
    ok(marcas == ["P2", "P2"], f"2D → 3D: a célula de uma posição destaca as peças dela no 3D ({marcas})")
    aba.avaliar(f"{F2}.cad.selecionar(['d2']); 1")
    aba.drenar(1.0)
    sel = aba.avaliar(f"[...{F3}.editor.selecao.ids]") or []
    ok(sel == [ids_barras[-1]], f"2D → 3D: a peça da localização destaca ela só, pela origem ({sel})")
    # 3D → 2D pela marca (o projeto do IFC, sem ligação pela planta): o 2D vai à célula da posição
    aba.avaliar(f"{F2}.cad._localizarPelaMarca({{posicoes: ['P2'], conjuntos: [], ids: []}}); 1")
    aba.drenar(0.5)
    reg = aba.avaliar(f"{F2}.cad.tela.regiao") or []
    ok(bool(reg) and reg[0][0] <= 300001 and reg[1][0] >= 307999 and reg[0][1] <= 1 and reg[1][1] >= -1,
       f"3D → 2D pela marca: o 2D enquadra a célula da posição P2 ({reg})")
    aba.avaliar(f"{F2}.cad.selecionar(['l1']); 1")         # de volta à cópia da planta (a próxima conta com ela)
    aba.drenar(1.0)
    # sem seguir, nada passa
    aba.avaliar(f"{F2}.document.querySelector('.ligacao-vistas [data-c=seguir]').click(); 1"); aba.drenar(0.3)
    aba.avaliar(f"{F2}.cad.selecionar(['l3']); 1")
    aba.drenar(0.8)
    pecas2 = aba.avaliar(f"[...new Set([...{F3}.editor.selecao.ids].map(id => {F3}.editor.documento.get(id).atributos.origem.peca))]") or []
    ok(pecas2 == ["TESOURA 1#1"], "com \"seguir a seleção\" desligado, um lado não mexe no outro")
    aba.avaliar(f"{F2}.document.querySelector('.ligacao-vistas [data-c=seguir]').click(); {F2}.document.querySelector('.ligacao-vistas [data-c=trocar]').click(); 1"); aba.drenar(0.3)
    ok(aba.avaliar("document.querySelector('#quadro').classList.contains('trocado')"), "trocar lados põe o 3D à esquerda")
    aba.avaliar(f"{F2}.document.querySelector('.ligacao-vistas [data-c=trocar]').click(); 1"); aba.drenar(0.3)
    # as vistas: trocar só mostra/esconde o quadro — o 3D não é montado de novo
    aba.avaliar(f"{F3}.__marca = 'mesmo'; 1")
    aba.avaliar(f"{F3}.document.querySelector('.seletor-vista a[data-vista-area=\"2d\"]').click(); 1"); aba.drenar(0.5)
    ok(aba.avaliar("getComputedStyle(document.querySelector('#lado-3d')).display") == "none"
       and aba.avaliar("getComputedStyle(document.querySelector('#lado-2d')).display") != "none"
       and "vista=2d" in (aba.avaliar("location.search") or ""), "a vista 2D mostra só o desenho (e a URL diz a vista)")
    aba.avaliar(f"{F2}.document.querySelector('.seletor-vista a[data-vista-area=\"3d\"]').click(); 1"); aba.drenar(0.5)
    ok(aba.avaliar(f"{F3}.__marca") == "mesmo" and aba.avaliar(f"{F3}.editor.documento.entidades.size") == 4,
       "voltar ao 3D não recarrega o modelo (o mesmo 3D, montado uma vez)")
    ok(aba.avaliar(f"{F2}.document.querySelector('.ligacao-vistas').hidden") is True,
       "fora do 2D + 3D, os controles da seleção somem")
    # o pedido de ir ao 3D, vindo do 2D (o "Abrir o modelo 3D" depois de montar pela planta): recarrega o 3D e troca a vista
    aba.avaliar(f"{F3}.document.querySelector('.seletor-vista a[data-vista-area=\"2d\"]').click(); 1"); aba.drenar(0.3)
    aba.avaliar(f"{F2}.metalicaNavegar('/editor?projeto=posto'); 1")
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar(f"!!({F3}.editor && {F3}.editor.documento && {F3}.editor.documento.entidades.size === 4 && !{F3}.__marca)"): aba.drenar(0.5)
    ok("vista=3d" in (aba.avaliar("location.search") or "") and not aba.avaliar(f"{F3}.__marca"),
       "o 2D pede o 3D: a área troca a vista e recarrega o 3D (o modelo pode ter mudado)")
    aba.avaliar(f"{F3}.document.querySelector('.seletor-vista a[data-vista-area=\"ambos\"]').click(); 1"); aba.drenar(0.8)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("!!document.querySelector('#rapidos-3d #btn-salvar')"): aba.drenar(0.5)
    txt = aba.avaliar("(document.querySelector('#rapidos-3d #btn-salvar') || {}).textContent || ''") or ""
    ok(txt.startswith("✓ Salvo") or txt.startswith("● Salvar"), f"o Salvar do 3D (recarregado) está na barra única com o estado da gravação ({txt})")
    # os painéis da direita: a aba na borda de cada lado esconde e mostra
    antes = aba.avaliar(f"{F3}.document.documentElement.classList.contains('sem-paineis')")
    aba.avaliar(f"{F3}.document.querySelector('.aba-paineis').click(); 1"); aba.drenar(0.4)
    depois = aba.avaliar(f"{F3}.document.documentElement.classList.contains('sem-paineis')")
    ok(depois != antes, f"a aba na borda do 3D alterna o painel dele ({antes} → {depois})")
    if not depois:
        aba.avaliar(f"{F3}.document.querySelector('.aba-paineis').click(); 1"); aba.drenar(0.4)
    larg = aba.avaliar(f"{F3}.document.querySelector('#paineis').offsetWidth")
    ok(larg == 0, f"escondido, o painel do 3D some de verdade (largura {larg})")
    # a tela sozinha ganha o seletor de vista, que leva à área de trabalho
    aba.navegar(base + "/cad?projeto=posto&desenho=desenho", limite=60)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("!!window.cad"): aba.drenar(0.3)
    sel = aba.avaliar("[...document.querySelectorAll('.seletor-vista a')].map(a => a.textContent + (a.classList.contains('ativo') ? '*' : '') + '=' + a.getAttribute('href'))") or []
    ok(len(sel) == 3 and sel[0].startswith("2D*") and "/dividida?projeto=posto&vista=3d" in sel[1],
       f"o 2D sozinho tem o seletor 2D | 3D | 2D + 3D ({sel})")
    tinha = aba.avaliar("document.documentElement.classList.contains('sem-paineis')")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="F4", code="F4", windowsVirtualKeyCode=115)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="F4", code="F4", windowsVirtualKeyCode=115)
    aba.drenar(0.3)
    ok(aba.avaliar("document.documentElement.classList.contains('sem-paineis')") != tinha
       and "painéis laterais" in (aba.avaliar("[...document.querySelectorAll('.menu[data-menu=ver] .menu-lista button')].map(b => b.textContent).join('|')") or ""),
       "no 2D sozinho, F4 alterna os painéis e Ver tem o item dos painéis laterais")
    alt = aba.avaliar("[...document.querySelectorAll('header.topo > *')].filter(e => e.offsetParent !== null && e.getBoundingClientRect().height > 46).map(e => e.className || e.id)") or []
    ok(not alt, f"a barra do 2D não quebra linha ({alt})")
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
