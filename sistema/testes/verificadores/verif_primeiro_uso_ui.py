# -*- coding: utf-8 -*-
"""Achados de tela dos testes de primeiro uso (16/10/2026, Projeto/BRIEFINGS/Briefing-primeiro-uso*.md): cada bloco
refaz, com eventos de verdade, o que o engenheiro novo fez e confere que não volta a acontecer. Servidor próprio numa
pasta temporária (nunca a 8765/8766). Ver sistema/testes/REGRESSOES.md, seção "Primeiro uso"."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_primeiro_uso_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(80):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def projeto(nome, tipo="lancamento"):
    return urllib.parse.quote(post("/api/projetos", {"nome": nome, "tipo": tipo})["slug"])


def p02_p13_recebido(aba):
    """P02: na tela inicial não havia "Recebi o projeto estrutural"; o engenheiro com o DXF do projetista importava como
    arquitetônico. P13: o Projeto recebido abria o seletor do Windows sem explicar nada antes."""
    print("P02/P13 — Novo pelo CAD 2D com o projeto estrutural recebido")
    aba.navegar(base + "/", limite=60)
    esperar(aba, "document.querySelector('#btn-novo-cad') && document.querySelector('#contagem') && !/carregando/.test(document.querySelector('#contagem').textContent)")
    # P20: os botões Novo… da pasta vazia e da barra com o mesmo nome e com dica
    pares = aba.avaliar("""[['novo', 'btn-novo'], ['novo-ifc', 'btn-novo-ifc'], ['novo-cad', 'btn-novo-cad']].map(([a, b]) => {
        const x = document.querySelector(`[data-acao="${a}"]`), y = document.getElementById(b);
        return [x.textContent.trim(), y.textContent.trim(), !!x.title, !!y.title]; })""") or []
    ok(pares and all(p[0] == p[1] and p[2] and p[3] for p in pares), f"P20: botões Novo… iguais nos dois lugares e com dica: {pares}")
    sel = "#btn-novo-cad" if aba.avaliar("document.querySelector('#btn-novo-cad').offsetParent !== null") else '[data-acao="novo-cad"]'
    clicar(aba, sel)
    esperar(aba, "document.querySelector('#dlg').open")
    marcado = aba.avaliar("(document.querySelector('input[name=dlg-comeco]:checked') || {}).value")
    ok(marcado == "recebido", f"a opção do projeto recebido existe e vem marcada ({marcado})")
    aba.cmd("Input.insertText", text="Portaria recebida")
    clicar(aba, "#dlg-ok")
    esperar(aba, "location.pathname === '/cad' && window.cad && document.body.dataset.pronto === '1'", 60)
    esperar(aba, "window.cad.el && document.querySelector('dialog[open]')", 10)
    titulo = aba.avaliar("(document.querySelector('dialog[open] h3, dialog[open] .titulo, dialog[open] header') || {}).textContent || document.querySelector('dialog[open]') && document.querySelector('dialog[open]').textContent.slice(0, 60)") or ""
    ok(aba.avaliar("location.pathname") == "/cad" and "Projeto recebido" in titulo, f"o CAD abre explicando o Projeto recebido antes do arquivo («{titulo.strip()[:50]}»)")
    s = aba.avaliar("new URL(location.href).searchParams.get('projeto')")
    tipo = json.load(urllib.request.urlopen(f"{base}/api/projetos/{urllib.parse.quote(s)}", timeout=30)).get("projeto", {}).get("tipo")
    ok(tipo == "recebido", f"o projeto nasce com o tipo recebido ({tipo})")
    aba.avaliar("document.querySelector('dialog[open]') && document.querySelector('dialog[open]').close('cancelar'); 1")


def p06_vao_pequeno(aba):
    """P06: eixos com 4 m de vão — o Lançar estrutura nos eixos avisa antes (5 a 60 m) e oferece Pilares nos eixos,
    em vez de aceitar e voltar com "Vão: valor 4.0 fora da faixa" depois do clique."""
    print("P06 — vão de 4 m no Lançar estrutura nos eixos")
    s = projeto("Portaria vão pequeno")
    post(f"/api/projetos/{s}/eixos", {"eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
                                                "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 4000.0}],
                                                "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto")
    # P27: a árvore do modelo vazio traz os botões, em vez de citar "Arquivo → Gerar do galpão" (outro nome na tela do projeto)
    bts = aba.avaliar("[...window.editor.el.arvore.querySelectorAll('button')].map(b => b.textContent)") or []
    ok("Gerar do galpão dimensionado…" in bts and "Modelo de exemplo" in bts, f"P27: árvore vazia com os botões {bts}")
    aba.avaliar("window.editor.dialogoLancar(); 1")
    esperar(aba, "window.editor.el.dialogo.open")
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent") or ""
    botao = aba.avaliar("window.editor.el.dialogoOk.hidden ? '' : window.editor.el.dialogoOk.textContent") or ""
    ok("5 a 60 m" in txt and "4,00" in txt, f"o diálogo avisa a faixa antes: {txt[:110]}")
    ok(botao != "Lançar", f"sem o botão Lançar (botão: «{botao}»)")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")


def clicar(aba, seletor):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
    if not r:
        raise RuntimeError("não achei " + seletor)
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    aba.drenar(0.3)


def tecla_esc(aba):
    for tipo in ("rawKeyDown", "keyUp"):
        aba.cmd("Input.dispatchKeyEvent", type=tipo, key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.3)


def p11_p12_cad(aba):
    """P12: Esc não fechava o menu aberto do CAD (ficava por cima do desenho). P11: o mesmo aviso de erro fixo
    se repetia na pilha, e os fixos seguiam ao trocar de desenho."""
    print("P11/P12 — menus e avisos do CAD")
    s = projeto("Portaria CAD", tipo="desenho")
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    clicar(aba, '.menu[data-menu="lancamento"] > button')
    ok(bool(aba.avaliar("!!document.querySelector('.menu.aberto')")), "o menu Lançamento abriu com o clique")
    tecla_esc(aba)
    ok(not aba.avaliar("!!document.querySelector('.menu.aberto')"), "Esc fecha o menu aberto")
    clicar(aba, '.menu[data-menu="desenho"] > button')
    clicar(aba, '[data-acao="projeto-2d"]')
    t = aba.avaliar("(document.querySelector('dialog[open]') || {}).textContent || ''") or ""
    ok("Projeto recebido" in t and "Escolher o arquivo" in t, "Desenho → Projeto recebido explica antes de abrir o seletor de arquivo")
    aba.avaliar("document.querySelector('dialog[open]') && document.querySelector('dialog[open]').close('cancelar'); 1")
    aba.avaliar("window.cad.aviso('Não foi possível montar: teste', 'erro', 0); window.cad.aviso('Não foi possível montar: teste', 'erro', 0); 1")
    n = aba.avaliar("[...document.querySelectorAll('#avisos .aviso')].filter(c => c.textContent.includes('montar: teste')).length")
    ok(n == 1, f"o mesmo aviso repetido fica um só ({n})")
    for i in range(7):
        aba.avaliar(f"window.cad.aviso('aviso {i}', 'info', 60000); 1")
    n = aba.avaliar("document.querySelectorAll('#avisos .aviso').length")
    ok(n <= 4, f"a pilha de avisos não passa de 4 ({n})")
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.el && window.editor.el.avisos")
    aba.avaliar("window.editor.aviso('Falhou: teste', 'erro'); window.editor.aviso('Falhou: teste', 'erro'); 1")
    n = aba.avaliar("[...window.editor.el.avisos.children].filter(c => c.textContent.includes('Falhou: teste')).length")
    ok(n == 1, f"no 3D, o mesmo aviso repetido fica um só ({n})")


def _lancado_nos_eixos(aba, nome):
    """o caminho do engenheiro: eixos A–B × 1–2 (5 × 6,2 m) e "Lançar a estrutura nos eixos" no 3D; devolve o projeto"""
    s = projeto(nome)
    post(f"/api/projetos/{s}/eixos", {"eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
                                                "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 5000.0}],
                                                "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && document.body.dataset.pronto === '1'")
    aba.avaliar("window.editor.dialogoLancar(); 1")
    esperar(aba, "window.editor.el.dialogo.open && !window.editor.el.dialogoOk.hidden && window.editor.el.dialogoOk.textContent === 'Lançar'", 30)
    aba.avaliar("window.editor.el.dialogoOk.click(); 1")
    # o "Estrutura lançada", com o botão Abrir o modelo lançado
    esperar(aba, "window.editor.el.dialogo.open && window.editor.el.dialogoOk.textContent === 'Abrir o modelo lançado'", 120)
    aba.avaliar("window.editor.el.dialogoOk.click(); 1")
    esperar(aba, "window.editor.documento && window.editor.documento.barras.length > 0 && document.body.dataset.pronto === '1'", 120)
    aba.drenar(1.0)
    return s


def p22_nome_e_posicao(aba):
    """P22: o pilar lançado mostrava título "P11 – 04x", "Nome P1" (o campo livre) e "Posição P11" — qual é a marca?"""
    print("P22 — Nome livre × Posição no pilar lançado")
    _lancado_nos_eixos(aba, "Portaria nome")
    pid = aba.avaliar("(window.editor.documento.barras.find(b => b.papel === 'pilar' && b.atributos && b.atributos.marcas && b.atributos.marcas.posicao) || {}).id")
    ok(bool(pid), f"um pilar com a marca de posição ({pid})")
    aba.avaliar(f"window.editor.selecao.definir([{json.dumps(pid)}]); 1")
    aba.drenar(1.0)
    rotulos = aba.avaliar("[...document.querySelectorAll('.campos > label')].map(l => l.textContent)") or []
    grupos = aba.avaliar("[...document.querySelectorAll('.grupo-campos, .grupo')].map(g => (g.querySelector('h3, h4, summary, .titulo') || g).textContent.trim().slice(0, 40))") or []
    ok("Nome no modelo (livre)" in rotulos and "Posição" in rotulos, f"o campo livre não se chama só Nome: {rotulos[:6]}")
    ok(any("marcas de fabricação" in g for g in grupos) and not any("Peça (IFC)" in g for g in grupos), f"o grupo da marca não fala em IFC: {grupos[:6]}")


def p23_lista_sob_medida(aba):
    """P23: na lista de materiais da portaria lançada, "Ue 250… 354 kg · 0 barras" parecia nada (são peças sob medida)."""
    print("P23 — perfis sob medida na lista de materiais")
    s = _lancado_nos_eixos(aba, "Portaria lista")
    aba.navegar(f"{base}/materiais?projeto={s}", limite=120)
    esperar(aba, "document.querySelectorAll('.barras-peso .kg').length > 3", 120)
    kgs = aba.avaliar("[...document.querySelectorAll('.barras-peso .kg')].map(k => k.textContent)") or []
    ok(kgs and not [k for k in kgs if "· 0 barras" in k] and any("sob medida" in k for k in kgs), f"sem «0 barras», com «sob medida»: {kgs[:8]}")


def p15_zoom_da_roda(aba):
    """P15: no CAD, cada evento da roda dava 1,15×, forte ou fraco (16 roladas da folha até ler os textos), e o x/y do
    rodapé ficava parado durante o zoom."""
    print("P15 — zoom da roda no CAD")
    s = projeto("Portaria zoom", tipo="desenho")
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    r = aba.avaliar("(() => { const q = document.querySelector('#tela, canvas').getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; })()")

    def rolar(dy, x, y):
        z0 = aba.avaliar("window.cad.tela.vp.z")
        aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0, deltaY=dy)
        aba.drenar(0.3)
        return aba.avaliar("window.cad.tela.vp.z") / z0

    fraco = rolar(-100, r[0], r[1])
    forte = rolar(-500, r[0], r[1])
    ok(fraco > 1.1 and forte > fraco * 1.5, f"a rolagem forte aproxima mais que a fraca ({fraco:.2f}× × {forte:.2f}×)")
    c0 = aba.avaliar("window.cad.el.coord.textContent")
    rolar(100, r[0] - 200, r[1] - 120)
    c1 = aba.avaliar("window.cad.el.coord.textContent")
    ok(c1 != c0 and "x" in c1, f"o x/y do rodapé acompanha o zoom («{c0}» → «{c1}»)")


def p18_uma_barra_de_ferramentas(aba):
    """P18 (guarda): o engenheiro viu as mesmas ferramentas na faixa de cima e na coluna da esquerda da tela do projeto.
    Não reproduziu em 16/10 (nem pelo modo ver → editor); o bloco segura as duas escolhas de Ver › Tela."""
    print("P18 — uma barra de ferramentas só na tela do projeto")
    s = projeto("Portaria ferramentas")
    for modo in ("", "faixa", "colunas"):
        aba.navegar(f"{base}/", limite=30)
        aba.avaliar(f"(() => {{ try {{ {'localStorage.removeItem' if not modo else 'localStorage.setItem'}('metalica.ferramentas'{', ' + json.dumps(modo) if modo else ''}); }} catch (e) {{}} return 1; }})()")
        aba.navegar(f"{base}/dividida?projeto={s}&vista=3d", limite=60)
        esperar(aba, "(() => { try { return !!document.querySelector('#f3d').contentWindow.visorLeve; } catch (e) { return false; } })()")
        aba.avaliar("document.querySelector('#f3d').contentWindow.visorLeve.editar(); 1")
        esperar(aba, "(() => { try { const d = document.querySelector('#f3d').contentWindow.document; return d.location.pathname === '/editor' && d.body.dataset.pronto === '1'; } catch (e) { return false; } })()", 60)
        aba.drenar(1.0)
        vis = aba.avaliar("""(() => { const d = document.querySelector('#f3d').contentWindow.document, col = d.querySelector('#barra-ferramentas'),
            fx = document.querySelector('#faixa-ferramentas');
            const ve = (e) => !!e && getComputedStyle(e).display !== 'none' && !e.hidden && e.getBoundingClientRect().width > 0;
            return [ve(col), ve(fx) && fx.children.length > 0]; })()""") or [None, None]
        ok(vis.count(True) == 1, f"«{modo or 'sem escolha'}»: uma barra só (coluna, faixa) = {vis}")
    aba.avaliar("(() => { try { localStorage.removeItem('metalica.ferramentas'); } catch (e) {} return 1; })()")


def p17_busca_acha_desenho(aba):
    """P17: Ctrl+K "projeto recebido" só achava comandos, e o Trocar de desenho morava só em Detalhamento (~6 ações)."""
    print("P17 — Ctrl+K acha os desenhos do projeto")
    if not os.path.exists(PORTARIA):
        ok(False, "sem o DXF da Portaria em Projeto/OBRAS/Portaria-Hermes"); return
    s = _projeto_com_a_portaria("Portaria desenhos")
    post(f"/api/projetos/{s}/desenhos/{urllib.parse.quote('Rascunho')}", {"desenho": {"nome": "Rascunho", "unidade": "mm", "escala": 1, "camadas": {}, "vistas": [], "metadados": {}, "entidades": []}})
    aba.navegar(f"{base}/dividida?projeto={s}&vista=2d&desenho=Rascunho", limite=60)
    esperar(aba, "window.etapasProjeto && document.querySelector('#desenho') && document.querySelector('#desenho').options.length >= 2", 30)
    ok(bool(aba.avaliar(_item_da_barra("Trocar de desenho") + " && " + "window.barraUnica.mapa[0].itens.some(i => i && i.texto === 'Trocar de desenho')")), "Arquivo › Trocar de desenho existe")
    aba.avaliar("window.etapasProjeto.abrirBusca(); 1")
    esperar(aba, "document.querySelector('.be-fundo.on input') === document.activeElement", 10)
    aba.cmd("Input.insertText", text="recebido")
    esperar(aba, "[...document.querySelectorAll('.be-r .be-tipo')].some(t => t.textContent === 'desenho')", 10)
    achados = aba.avaliar("[...document.querySelectorAll('.be-r')].map(r => r.textContent)") or []
    ok(any(a.startswith("desenho") and "Projeto recebido" in a for a in achados), f"aparece o DESENHO Projeto recebido: {achados[:3]}")
    aba.avaliar("[...document.querySelectorAll('.be-r')].find(r => r.querySelector('.be-tipo').textContent === 'desenho').click(); 1")
    foi = esperar(aba, "(() => { const s = document.querySelector('#desenho'), o = s.selectedOptions[0]; return !!o && o.textContent.startsWith('Projeto recebido') && decodeURIComponent(document.querySelector('#f2d').src).includes('desenho=' + o.value); })()", 20)
    ok(foi, f"o clique abre o desenho no 2D ({aba.avaliar('document.querySelector(\'#desenho\').value')})")


def p16_camadas_do_arquivo(aba):
    """P16: depois de importar o DXF da Portaria, o painel de camadas punha CORTE…AUXILIAR com 0 no topo e misturava
    as camadas do arquivo ("0, 1, 6, 20, 画層 50, MOB…") com as do Metálica."""
    print("P16 — camadas do arquivo × do Metálica")
    if not os.path.exists(PORTARIA):
        ok(False, "sem o DXF da Portaria em Projeto/OBRAS/Portaria-Hermes"); return
    s = _projeto_com_a_portaria("Portaria camadas")
    nome = "Projeto recebido – " + os.path.splitext(os.path.basename(PORTARIA))[0]
    aba.navegar(f"{base}/cad?projeto={s}&desenho={urllib.parse.quote(nome)}", limite=90)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1' && document.querySelector('.lista-linhas .linha')", 90)
    filhos = aba.avaliar("""[...document.querySelector('.lista-linhas').children].map(c => c.classList.contains('grupo-camadas') ? 'G:' + c.textContent
        : c.tagName === 'DETAILS' ? 'V:' + [...c.querySelectorAll('.linha .nome')].map(n => n.textContent).join(',')
        : c.querySelector('.nome').textContent + '=' + c.querySelector('.contagem').textContent)""") or []
    ok(filhos and filhos[0].startswith("G:Do arquivo") and "Portaria" in filhos[0], f"o grupo do arquivo vem primeiro, com o nome do DXF: {filhos[:2]}")
    meu = next((i for i, f in enumerate(filhos) if f.startswith("G:Do Metálica")), None)
    vazias = next((f for f in filhos if f.startswith("V:")), "")
    ok(meu is not None and not [f for f in filhos[:meu] if f.endswith("=0")], f"nenhuma camada vazia antes do grupo do Metálica: {filhos[:meu][:6] if meu else filhos[:6]}")
    ok("CORTE" in vazias and "AUXILIAR" in vazias, f"as vazias do Metálica recolhidas: {vazias[:80]}")


def _item_da_barra(texto):
    return f"""(() => {{ let a = null; (function andar(l) {{ for (const it of (Array.isArray(l) ? l : [])) {{ if (a) return; if (it && it.texto === {json.dumps(texto)}) a = it; else if (it && (it.sub || it.itens)) andar(it.sub || it.itens); }} }})(window.barraUnica.mapa); return a; }})()"""


def p07_menu_antes_do_editor(aba):
    """P07: com o 3D no modo "ver", o comando do menu da tela do projeto carregava o editor e clicava logo que o
    window.editor nascia, antes de o projeto chegar: "Abra um projeto: as treliças lidas vêm…" com o projeto aberto, e o
    Detalhar não abria."""
    print("P07 — comando do menu com o 3D no modo ver")
    s = projeto("Portaria menu")
    for texto, conferir, rotulo in (("Detalhar peças e conjuntos…", "(() => { try { const d = document.querySelector('#f3d').contentWindow.document.querySelector('dialog[open]'); return !!d && d.textContent.includes('Tesouras (com as barras'); } catch (e) { return false; } })()", "o diálogo Detalhar peças e conjuntos abre"),
                                    ("5. Conferir as treliças lidas…", "location.pathname === '/trelicas'", "Conferir as treliças lidas vai para /trelicas")):
        aba.navegar(f"{base}/dividida?projeto={s}&vista=3d", limite=60)
        esperar(aba, "window.barraUnica && (() => { try { return !!document.querySelector('#f3d').contentWindow.visorLeve; } catch (e) { return false; } })()")
        ok(aba.avaliar(f"!!{_item_da_barra(texto)}"), f"o item «{texto}» existe no menu")
        aba.avaliar(f"window.barraUnica.executar({_item_da_barra(texto)}); 1")
        foi = esperar(aba, conferir, 60)
        aviso = aba.avaliar("(() => { try { return [...document.querySelector('#f3d').contentWindow.document.querySelectorAll('.aviso, #avisos > *')].map(a => a.textContent).join(' | '); } catch (e) { return ''; } })()") or ""
        ok(foi and "Abra" not in aviso, f"{rotulo} (avisos: «{aviso[:80]}»)")


def p07_menu_com_o_2d_a_mostra(aba):
    """P07, rodada 2: com o 2D à mostra, Modelo › Eixos da obra… trocava para o 3D no modo ver e não abria nada — o quadro
    do 3D ainda nem tinha o modo ver quando o comando pediu o editor, e o pedido (único) se perdia."""
    print("P07 (rodada 2) — comando do 3D com o 2D à mostra")
    s = projeto("Portaria eixos")
    post(f"/api/projetos/{s}/eixos", {"eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "z_base": 0.0,
                                                "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 5000.0}],
                                                "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6200.0}]}})
    aba.navegar(f"{base}/dividida?projeto={s}&vista=2d", limite=60)
    esperar(aba, "window.barraUnica && (() => { try { return !!document.querySelector('#f2d').contentWindow.cad; } catch (e) { return false; } })()")
    ok(aba.avaliar(f"!!{_item_da_barra('Eixos da obra…')}"), "o item «Eixos da obra…» existe no menu")
    aba.avaliar(f"window.barraUnica.executar({_item_da_barra('Eixos da obra…')}); 1")
    foi = esperar(aba, "(() => { try { const w = document.querySelector('#f3d').contentWindow; return !!(w.editor && w.editor.el.dialogo.open && /Eixos/.test(w.editor.el.dialogoTitulo.textContent)); } catch (e) { return false; } })()", 60)
    ok(foi, "o diálogo Eixos da obra abre (o editor é pedido quando o modo ver fica pronto)")


def p08_folhas_sem_pedir_o_arquivo(aba):
    """P08: o passo "2. Ler folhas e considerações de cálculo" abria direto a janela do Windows pedindo o DXF de novo (o
    passo 1 já o tinha importado). Agora pergunta antes e lê o DXF guardado no projeto."""
    print("P08 — passo 2 do projeto recebido lê o DXF do passo 1")
    import base64
    from test_folhas_recebidas import _dxf
    s = projeto("Portaria folhas")
    post(f"/api/projetos/{s}/projeto-2d", {"arquivo": "portaria.dxf", "ifc": False, "conteudo_b64": base64.b64encode(_dxf().encode()).decode()})
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    aba.avaliar("window.__seletores = 0; const c0 = HTMLInputElement.prototype.click; HTMLInputElement.prototype.click = function () { if (this.type === 'file') window.__seletores++; return c0.apply(this, arguments); }; 1")
    clicar(aba, '.menu[data-menu="vistas"] > button')
    clicar(aba, '[data-acao="folhas-recebidas"]')
    esperar(aba, "document.querySelector('#dialogo').open", 15)
    t = aba.avaliar("document.querySelector('#dialogo').textContent") or ""
    ok("portaria.dxf" in t and "passo 1" in t and "Escolher outro arquivo" in t, f"pergunta antes, com o DXF do passo 1: «{t.strip()[:90]}»")
    clicar(aba, "#dialogo-ok")
    esperar(aba, "document.querySelector('#dialogo').open && /3 folha/.test(document.querySelector('#dialogo').textContent)", 30)
    t = aba.avaliar("document.querySelector('#dialogo').textContent") or ""
    ok("3 folha" in t and "CONSTRUTORA ROSA DOS VENTOS" in t, f"lê as folhas do DXF guardado: «{t.strip()[:90]}»")
    ok(aba.avaliar("window.__seletores") == 0, f"sem abrir a janela de arquivo ({aba.avaliar('window.__seletores')})")
    aba.avaliar("document.querySelector('#dialogo').close(); 1")


PORTARIA = os.path.join(BASE, "..", "Projeto", "OBRAS", "Portaria-Hermes", "Portaria projeto Hermes 30.09.dxf")


def escolher_arquivo(aba, seletor, caminho):
    """o arquivo no campo, como a janela do Windows faria (DOM.setFileInputFiles dispara o change)"""
    doc = aba.cmd("DOM.getDocument", depth=-1, pierce=True)
    no = aba.cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=seletor)["nodeId"]
    aba.cmd("DOM.setFileInputFiles", files=[os.path.abspath(caminho)], nodeId=no)
    aba.drenar(0.5)


def p19_resultado_do_recebido(aba):
    """P19: o resultado do Projeto recebido da Portaria era um paredão — 15 vistas, 8 "sem título" repetindo "escala não
    encontrada… usei mm" e o aviso que importava (a planta sem eixos: as vistas não montam) no fim."""
    print("P19 — resultado do Projeto recebido (DXF da Portaria)")
    if not os.path.exists(PORTARIA):
        ok(False, "sem o DXF da Portaria em Projeto/OBRAS/Portaria-Hermes"); return
    s = projeto("Portaria resultado", tipo="recebido")
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    escolher_arquivo(aba, "#arquivo-projeto-2d", PORTARIA)
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelector('#dialogo-ok').textContent === 'Ler o projeto'", 30)
    clicar(aba, "#dialogo-ok")
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Projeto recebido'", 240)
    blocos = aba.avaliar("[...document.querySelectorAll('#dialogo-corpo .resultado-recebido > *')].map(e => (e.querySelector('h4, summary') || e).textContent.trim().slice(0, 60))") or []
    ok(blocos and blocos[0].startswith("Não deu"), f"o primeiro bloco é o que não deu: {blocos[:5]}")
    primeiro = aba.avaliar("(document.querySelector('#dialogo-corpo .bloco-resultado.erro') || {}).textContent || ''") or ""
    ok("eixos" in primeiro, f"o aviso de posicionamento está no bloco Não deu: «{primeiro[:120]}»")
    corpo = aba.avaliar("document.querySelector('#dialogo-corpo').textContent") or ""
    n = corpo.count("escala não encontrada") + corpo.count("sem escala pelas cotas")
    ok(n == 1 and "8 vistas sem escala" in corpo, f"a escala não encontrada aparece uma vez, com a contagem ({n})")
    ok("Próximos passos" in corpo, "tem Próximos passos")
    aba.avaliar("document.querySelector('#dialogo').close(); 1")


def _dxf_simples():
    import io
    import ezdxf
    d = ezdxf.new("R2010")
    for a, b in (((0, 0), (12000, 0)), ((12000, 0), (12000, 8000)), ((12000, 8000), (0, 8000)), ((0, 8000), (0, 0))):
        d.modelspace().add_line(a, b)
    buf = io.StringIO(); d.write(buf)
    return buf.getvalue()


def p14_quadros_vazios(aba):
    """P14: a aba Montagem só dizia "ponha em cada quadro a parte do projeto que ele pede" no rodapé; o "Enviar para
    quadro" só aparece na Original e nada ligava uma à outra."""
    print("P14 — quadros vazios da Montagem")
    import base64
    s = projeto("Portaria montagem")
    post(f"/api/projetos/{s}/arquitetonico", {"arquivo": "planta.dxf", "conteudo_b64": base64.b64encode(_dxf_simples().encode()).decode()})
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1' && document.querySelector('[data-aba=montagem]') && !document.querySelector('[data-aba=montagem]').hidden", 30)
    clicar(aba, "[data-aba=montagem]")
    esperar(aba, "window.cad.nomeDesenho === 'montagem' && document.querySelectorAll('.quadro-titulo').length > 5", 30)
    aba.drenar(1.0)
    vazios = aba.avaliar("[...document.querySelectorAll('.quadro-vazio')].map(v => [v.textContent, v.hidden])") or []
    ok(len(vazios) >= 8 and all("Vazio" in t and "Enviar para quadro" in t and "Ir ao Original" in t for t, _ in vazios),
       f"cada quadro vazio diz o que pôr e tem Ir ao Original ({len(vazios)}: {vazios[:1]})")
    ok(any(not h for _, h in vazios), "algum aparece na tela inteira")
    aba.avaliar("[...document.querySelectorAll('.quadro-vazio')].find(v => !v.hidden).querySelector('button').setAttribute('data-teste', '1'); 1")
    clicar(aba, "[data-teste='1']")
    ok(esperar(aba, "window.cad.nomeDesenho && window.cad.nomeDesenho !== 'montagem'", 20), f"Ir ao Original abre a Original ({aba.avaliar('window.cad.nomeDesenho')})")
    esperar(aba, "document.body.textContent.includes('Para o quadro')", 10)
    ok(aba.avaliar("document.body.textContent.includes('Para o quadro') && document.querySelector('#btn-enviar-quadro').classList.contains('chama') && !document.querySelector('#btn-enviar-quadro').hidden"),
       "na Original, o rodapé diz o que mandar e o Enviar para quadro chama a atenção")


def p26_padroes_da_planta(aba):
    """P26: o diálogo "Montar o 3D pela planta" mostrava banzo 6,00 m e ASTM A36 como se fossem lidos do desenho; eram o
    padrão do programa. A planta da Portaria ("PLANTA NO NÍVEL DO FORRO") não traz o nível."""
    print("P26 — de onde vêm o nível e o aço do Montar o 3D pela planta")
    s = projeto("Portaria planta")
    nome = "Projeto recebido – portaria"
    post(f"/api/projetos/{s}/desenhos/{urllib.parse.quote(nome)}", {"desenho": {"nome": nome, "unidade": "mm", "escala": 1, "camadas": {}, "vistas": [], "metadados": {},
         "entidades": [{"id": "t1", "tipo": "texto", "camada": "TEXTO", "posicao": [0, 0], "texto": "PLANTA NO NÍVEL DO FORRO"},
                       {"id": "t2", "tipo": "texto", "camada": "TEXTO", "posicao": [0, 9000], "texto": "PLANTA NO NÍVEL 4,25"}]}})
    aba.navegar(f"{base}/cad?projeto={s}&desenho={urllib.parse.quote(nome)}", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'")
    clicar(aba, '.menu[data-menu="vistas"] > button')
    clicar(aba, '[data-acao="montar-planta"]')
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent.includes('pela planta')", 20)
    corpo = lambda: aba.avaliar("document.querySelector('#dialogo-corpo').textContent") or ""
    sel = aba.avaliar("document.querySelector('#dialogo-corpo select').value")
    if sel != "PLANTA NO NÍVEL DO FORRO":
        aba.avaliar("(() => { const s = document.querySelector('#dialogo-corpo select'); s.value = 'PLANTA NO NÍVEL DO FORRO'; s.dispatchEvent(new Event('change')); return 1; })()")
    t = corpo()
    ok("é o padrão" in t and "confira na elevação" in t, f"o banzo sem nível no título é dito padrão: «{t[t.find('Banzo inferior:'):][:90]}»")
    ok("padrão do programa" in t, "o aço é dito padrão do programa (o projeto não teve as folhas lidas)")
    aba.avaliar("(() => { const s = document.querySelector('#dialogo-corpo select'); s.value = 'PLANTA NO NÍVEL 4,25'; s.dispatchEvent(new Event('change')); return 1; })()")
    t = corpo()
    v = aba.avaliar("[...document.querySelectorAll('#dialogo-corpo input[type=text]')][0].value")
    ok(v == "4,25" and "lido do título" in t, f"com o nível no título, o banzo vem dele ({v})")
    aba.avaliar("document.querySelector('#dialogo').close(); 1")


def _projeto_com_a_portaria(nome):
    """um projeto com o modelo do Projeto recebido da Portaria (608 barras, 4,2 t)"""
    import base64
    s = projeto(nome, tipo="recebido")
    with open(PORTARIA, "rb") as f:
        post(f"/api/projetos/{s}/projeto-2d", {"arquivo": os.path.basename(PORTARIA), "ifc": False, "conteudo_b64": base64.b64encode(f.read()).decode()})
    return s


ACO_DO_PAINEL = "[...document.querySelectorAll('label')].filter(l => l.textContent === 'Aço' && l.nextElementSibling && l.nextElementSibling.classList.contains('valor')).map(l => l.nextElementSibling.textContent).join('|')"


def p21_peso_do_modelo_vazio(aba):
    """P21: depois de Novo modelo › Em branco, o painel do modelo mostrava 0 objetos e "Aço 4,3 t" (o peso do modelo
    anterior, que vem do modelo gravado no servidor)."""
    print("P21 — peso do modelo em branco")
    if not os.path.exists(PORTARIA):
        ok(False, "sem o DXF da Portaria em Projeto/OBRAS/Portaria-Hermes"); return
    s = _projeto_com_a_portaria("Portaria peso")
    aba.navegar(f"{base}/editor?projeto={s}", limite=90)
    esperar(aba, "window.editor && document.body.dataset.pronto === '1'", 90)
    esperar(aba, f"/ t/.test({ACO_DO_PAINEL})", 30)
    antes = aba.avaliar(ACO_DO_PAINEL)
    ok(" t" in (antes or ""), f"com a Portaria, o painel mostra o aço ({antes})")
    aba.avaliar("window.editor.novo(); 1")
    esperar(aba, "window.editor.el.dialogo.open", 10)
    aba.avaliar("window.editor.el.dialogoOk.click(); 1")
    esperar(aba, "window.editor.documento.tamanho === 0", 10)
    aba.drenar(1.5)
    depois = aba.avaliar(ACO_DO_PAINEL)
    ok(aba.avaliar("window.editor.documento.tamanho") == 0 and depois == "—", f"no modelo em branco, Aço é «—» ({depois})")


# ---------------------------------------------------------------- IFC → pranchas (Eng. Camila, achados Q)

def _pasta_do_projeto(slug):
    for raiz, dirs, _ in os.walk(DADOS):
        if os.path.basename(raiz) == slug and os.path.exists(os.path.join(raiz, "projeto.json")):
            return raiz
    raise RuntimeError("pasta do projeto %s não achada" % slug)


def q01_pdf_recusado_ver_no_3d(aba):
    """Q01: o PDF das pranchas recusado por terças fora do passo da máquina ("T.O.6: furos a 60 mm…") e nada levava à
    peça. O aviso amarelo e o erro vermelho trazem cada terça com "Ver no 3D", que abre o editor com as peças (e a barra
    em que a terça se liga) em destaque."""
    print("Q01 — PDF recusado: cada terça com Ver no 3D")
    s = projeto("Sooro pranchas", tipo="desenho")
    # 3 barras no 3D: as duas cópias da terça T.O.6 e o banzo em que ela se liga
    post(f"/api/projetos/{s}/modelo", {"documento": {"nome": "Sooro", "entidades": [
        {"tipo": "barra", "id": i, "nome": n, "camada": "Vigas", "perfil": "U150X50X2.28", "inicio": [x, 0, 3000], "fim": [x, 6000, 3000],
         "atributos": {"marcas": {"posicao": "M92", "nome": "T.O.6"} if n != "banzo" else {"posicao": "M1"}}}
        for i, n, x in (("b1", "T.O.6", 0), ("b2", "T.O.6", 2000), ("b3", "banzo", 4000))]}})
    post(f"/api/projetos/{s}/desenhos/pranchas", {"desenho": {"nome": "pranchas", "entidades": [
        {"tipo": "linha", "id": "l1", "camada": "0", "a": [0, 0], "b": [100, 100]}],
        "metadados": {"pranchas": [{"numero": 1, "celulas": []}]}}})
    texto = "T.O.6: furos a 60 mm na altura (máquina: 50)"
    det = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "detalhamento")
    os.makedirs(det, exist_ok=True)
    with open(os.path.join(det, "carimbo.json"), "w", encoding="utf-8") as f:
        json.dump({"desenhos": {}, "fora_da_maquina": [texto],
                   "fora_da_maquina_pecas": [{"nome": "T.O.6", "marca": "M92", "texto": texto, "ids": ["b1", "b2"], "ligadas": ["b3"]}]}, f)
    aba.navegar(f"{base}/cad?projeto={s}&desenho=pranchas", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'", 60)
    amarelo = esperar(aba, "[...document.querySelectorAll('.aviso[data-tipo=atencao] button.ver-no-3d')].length === 1", 30)
    ok(amarelo, "o aviso amarelo traz a T.O.6 com Ver no 3D")
    aba.avaliar("window.cad.pdfDasPranchas(); 1")
    vermelho = esperar(aba, "[...document.querySelectorAll('.aviso[data-tipo=erro]')].some(a => /T.O.6/.test(a.textContent) && a.querySelector('button.ver-no-3d'))", 60)
    ok(vermelho, "o erro do PDF traz a T.O.6 com Ver no 3D")
    txt = aba.avaliar("[...document.querySelectorAll('.aviso[data-tipo=erro]')].map(a => a.textContent).join(' ')") or ""
    ok("chapa de ligação" in txt, f"o erro diz o que fazer: {txt[:160]}")
    clicar(aba, ".aviso[data-tipo=erro] button.ver-no-3d")
    no3d = esperar(aba, "location.pathname === '/editor' && window.editor && window.editor.selecao && window.editor.selecao.ids.size === 3", 60)
    ok(no3d, "Ver no 3D abre o editor com as 2 cópias da terça e o banzo selecionados (%s)"
       % aba.avaliar("location.pathname + ' ' + (window.editor && window.editor.selecao ? window.editor.selecao.ids.size : '-')"))
    # o 400 do PDF recusado é o caso testado, não erro da tela
    aba.console[:] = [m for m in aba.console if not ("400" in m[1] and "/pranchas/pdf" in m[1])]


def q02_q03_dialogo_detalhar(aba):
    """Q03: as opções do Detalhar se perdiam (o diálogo voltava ao padrão e a atualização automática também). Q02
    (decisão do usuário: o padrão da máquina vence): a caixa diz o que faz, e o fim do Detalhar mostra o que mudou no 3D
    com Desfazer."""
    print("Q02/Q03 — diálogo Detalhar com as opções do projeto e o que mudou no 3D")
    s = projeto("Sooro opções", tipo="ifc")
    post(f"/api/projetos/{s}/modelo", {"documento": {"nome": "Sooro", "entidades": [
        {"tipo": "barra", "id": "b1", "camada": "Vigas", "perfil": "U150X50X2.28", "inicio": [0, 0, 3000], "fim": [0, 6000, 3000],
         "atributos": {"marcas": {"posicao": "M92"}}}]}})
    arq = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "projeto.json")
    with open(arq, encoding="utf-8") as f:
        pj = json.load(f)
    pj["opcoes_detalhamento"] = {"regra_tercas": False, "rotular": True, "parafuso_compra": "metrico"}
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(pj, f)
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto && document.body.dataset.pronto === '1'", 60)
    aba.avaliar("window.editor.dialogoDetalharPecas(); 1")
    esperar(aba, "window.editor.el.dialogo.open && /Detalhar peças/.test(window.editor.el.dialogoTitulo.textContent)", 30)
    estado = aba.avaliar("""(() => { const ls = [...window.editor.el.dialogoCorpo.querySelectorAll('label')];
        const caixa = (t) => { const l = ls.find(x => x.textContent.startsWith(t)); return l && l.nextElementSibling ? l.nextElementSibling.checked : null; };
        return { regra: caixa('Chapas de ligação das terças no passo da máquina'), rotular: caixa('Rotular posições'),
                 antigo: ls.some(x => x.textContent === 'Furação das terças no padrão da fábrica'),
                 explica: /vai para o 3D sempre/.test(window.editor.el.dialogoCorpo.textContent) }; })()""") or {}
    ok(estado.get("regra") is False and estado.get("rotular") is True, f"Q03: o diálogo abre com as opções do projeto {estado}")
    ok(estado.get("antigo") is False and estado.get("explica"), "Q02: a caixa com o nome do que faz e o padrão de fábrica explicado")
    # N04 (decisão do usuário 16/10): o parafuso da compra é opção do projeto
    compra = aba.avaliar("(window.editor.el.dialogoCorpo.querySelector('select.parafuso-compra') || {}).value")
    ok(compra == "metrico", f"N04: Parafusos na compra abre com a opção do projeto ({compra})")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")
    aba.drenar(0.5)
    # o fim do Detalhar: o que mudou no 3D, e o Desfazer pede a versão de antes
    aba.avaliar("""window.__pedidos = []; const f0 = window.fetch; window.fetch = (u, o) => { if (String(u).includes('desfazer-detalhar')) {
        window.__pedidos.push([String(u), o && o.body]); return Promise.resolve(new Response(JSON.stringify({ erro: 'teste' }), { status: 400 })); } return f0(u, o); };
        window.editor._mudancasDoDetalhar({ posicoes: ['T.O.6 (M92)'], etapas: ['4 furo(s) de terças e das chapas parafusadas nelas viraram oblongos 25×13'],
                                            convertidas: 0, desfazer: 'modelo-20261016-120703-marco.json.gz' }); 1""")
    abriu = esperar(aba, "window.editor.el.dialogo.open && /mudou no 3D/.test(window.editor.el.dialogoTitulo.textContent) && !!window.editor.el.dialogoCorpo.querySelector('button.desfazer-detalhar')", 20)
    ok(abriu, "o quadro O que o detalhamento mudou no 3D, com as etapas e o Desfazer")
    if abriu:
        clicar(aba, "button.desfazer-detalhar")
        pedido = esperar(aba, "window.__pedidos.length === 1", 10)
        corpo = aba.avaliar("window.__pedidos[0] && window.__pedidos[0][1]") or ""
        ok(pedido and "modelo-20261016-120703-marco.json.gz" in corpo, f"Desfazer pede a versão de antes: {corpo}")
    aba.console[:] = [m for m in aba.console if "desfazer-detalhar" not in m[1] and "400" not in m[1]]


def q12_busca_pelo_nome_de_producao(aba):
    """Q12: o aviso e o erro do PDF diziam "T.O.6" e a busca (Ctrl+K, a do 3D) respondia "Nada com esse nome": o editor
    aberto antes do Detalhar não tinha os nomes de produção. A busca lê os nomes do servidor."""
    print("Q12 — a busca acha a peça pelo nome de produção")
    s = projeto("Sooro busca", tipo="ifc")
    post(f"/api/projetos/{s}/modelo", {"documento": {"nome": "Sooro", "entidades": [
        {"tipo": "barra", "id": i, "camada": "Vigas", "perfil": "U150X50X2.28", "inicio": [x, 0, 3000], "fim": [x, 6000, 3000],
         "atributos": {"marcas": {"posicao": "M92"}}} for i, x in (("b1", 0), ("b2", 2000))]}})
    det = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "detalhamento")
    os.makedirs(det, exist_ok=True)
    with open(os.path.join(det, "nomes.json"), "w", encoding="utf-8") as f:
        json.dump({"posicoes": {"M92": "T.O.6"}, "ifc": {"M92": "T.O.6"}}, f)
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto && document.body.dataset.pronto === '1'", 60)
    aba.avaliar("window.editor.pesquisarPecas('T.O.6'); 1")            # a 1ª pede os nomes ao servidor
    achou = esperar(aba, "window.editor.pesquisarPecas('T.O.6').total === 2", 10)
    rot = aba.avaliar("(window.editor.pesquisarPecas('T.O.6').grupos[0] || {}).chave") or ""
    ok(achou and rot == "T.O.6 (M92)", f"a busca acha as 2 cópias da T.O.6 pelo nome de produção ({rot})")



def q11_detalhar_ifc_avulso(aba):
    """Q11: "Detalhar as peças de um IFC…" não fazia nada — pelo menu da tela do projeto o editor carregava e clicava no
    campo de arquivo sem o gesto do usuário (o navegador bloqueava calado). Agora um diálogo explica e tem o botão."""
    print("Q11 — Detalhar um IFC avulso abre um diálogo visível")
    s = projeto("Sooro avulso", tipo="ifc")
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto && document.body.dataset.pronto === '1'", 60)
    aba.avaliar("document.querySelector('[data-acao=\"detalhar-ifc\"]').click(); 1")
    abriu = esperar(aba, "window.editor.el.dialogo.open && !!window.editor.el.dialogoCorpo.querySelector('button.escolher-ifc')", 10)
    txt = aba.avaliar("window.editor.el.dialogoCorpo.textContent") or ""
    ok(abriu and "Detalhar peças e conjuntos" in txt, f"o diálogo explica e tem o botão Escolher o arquivo ({txt[:80]})")
    aba.avaliar("window.editor.el.dialogo.close('cancelar'); 1")


def q18_avisos_e_contagem_do_pdf(aba):
    """Q18: os avisos do Detalhar de antes seguiam na tela depois do novo, e a dica do PDF contava os desenhos
    ("Gerando o PDF de 1 prancha(s)…" para 13 folhas)."""
    print("Q18 — o aviso velho sai e a dica do PDF conta as folhas")
    s = projeto("Sooro folhas", tipo="desenho")
    # acima de 4 MB a lista de desenhos lê só as pontas do arquivo e dá "pranchas: 1" (R20 da 2ª rodada: "Gerando o PDF de
    # 1 folha(s)" para 14 folhas) — o desenho daqui passa disso
    post(f"/api/projetos/{s}/desenhos/pranchas", {"desenho": {"nome": "pranchas", "entidades": [
        {"tipo": "linha", "id": "l%d" % k, "camada": "0", "a": [k % 900, k // 900], "b": [k % 900 + 5, k // 900]} for k in range(90000)],
        "metadados": {"pranchas": [{"numero": i, "celulas": []} for i in (1, 2, 3)]}}})
    texto = "T.O.6: furos a 60 mm na altura (máquina: 50)"
    det = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "detalhamento")
    os.makedirs(det, exist_ok=True)
    with open(os.path.join(det, "carimbo.json"), "w", encoding="utf-8") as f:
        json.dump({"desenhos": {}, "fora_da_maquina": [texto],
                   "fora_da_maquina_pecas": [{"nome": "T.O.6", "marca": "M92", "texto": texto, "ids": ["b1"]}]}, f)
    aba.navegar(f"{base}/cad?projeto={s}&desenho=pranchas", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1' && window.cad.doc.tamanho > 80000", 180)
    esperar(aba, "!!document.querySelector('.aviso[data-tipo=atencao] button.ver-no-3d')", 30)
    aba.avaliar("window.__dicas = []; const d0 = window.cad.dica.bind(window.cad); window.cad.dica = (t) => { window.__dicas.push(String(t)); return d0(t); }; window.cad.pdfDasPranchas(); 1")
    contou = esperar(aba, "window.__dicas.some(t => /Gerando o PDF de 3 folha/.test(t))", 20)
    ok(contou, "a dica do PDF conta as 3 folhas (%s)" % (aba.avaliar("window.__dicas.join(' | ')") or "")[:120])
    aba.avaliar("window.cad._avisarPendencias({ pendente_3d: {}, fora_da_maquina: [], pranchas_descartadas: [] }); 1")
    saiu = esperar(aba, "!document.querySelector('.aviso[data-tipo=atencao] button.ver-no-3d')", 5)
    ok(saiu, "o aviso amarelo das terças sai quando as pendências acabam")
    aba.console[:] = [m for m in aba.console if not ("400" in m[1] and "/pranchas/pdf" in m[1])]


LISTA_SOORO = os.path.join(BASE, "..", "Projeto", "OBRAS", "ME-Sooro", "teste-primeiro-uso", "lista-de-materiais.json")


def q19_dxf_de_corte_na_aba_chapas(aba):
    """Q19: não havia DXF de corte das chapas. A aba Chapas da lista de materiais tem "DXF de corte (1:1)…", que pede o
    ZIP ao servidor e baixa."""
    print("Q19 — DXF de corte na aba Chapas")
    if not os.path.exists(LISTA_SOORO):
        print("  (sem a lista da ME-Sooro do teste: pulado)")
        return
    s = projeto("Sooro corte", tipo="ifc")
    det = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "detalhamento")
    os.makedirs(det, exist_ok=True)
    shutil.copy(LISTA_SOORO, os.path.join(det, "lista-de-materiais.json"))
    aba.navegar(f"{base}/materiais?projeto={s}#chapas", limite=60)
    tem = esperar(aba, "!!document.querySelector('button.corte-chapas')", 30)
    ok(tem, "a aba Chapas tem o botão DXF de corte (1:1)…")
    if not tem:
        return
    aba.avaliar("""window.__corte = 0; const f0 = window.fetch; window.fetch = (u, o) => { if (String(u).includes('/corte-chapas')) {
        window.__corte++; return Promise.resolve(new Response(JSON.stringify({ chapas: 17, nomes: ['CH2_6,35mm_56x.dxf'],
        arquivo: { nome: 'corte-chapas.zip', url: '#' } }), { status: 200 })); } return f0(u, o); }; 1""")
    clicar(aba, "button.corte-chapas")
    feito = esperar(aba, "window.__corte === 1 && /17 chapa/.test(document.querySelector('#aviso').textContent)", 10)
    ok(feito, "o botão pede o ZIP e diz quantas chapas (%s)" % (aba.avaliar("document.querySelector('#aviso').textContent") or "")[:80])


def q20_dialogo_das_pranchas_lembra(aba):
    """Q20: o diálogo Montar pranchas voltava ao padrão (o Projetista e a revisão redigitados a cada vez)."""
    print("Q20 — Montar pranchas abre com o que foi digitado da última vez")
    s = projeto("Sooro carimbo", tipo="desenho")
    arq = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "projeto.json")
    with open(arq, encoding="utf-8") as f:
        pj = json.load(f)
    pj.update(responsavel="Eng. Camila", carimbo_pranchas={"obra": "Sooro – galpão", "revisao": "02"})
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(pj, f)
    post(f"/api/projetos/{s}/desenhos/rascunho", {"desenho": {"nome": "rascunho", "entidades": [
        {"tipo": "linha", "id": "l1", "camada": "0", "a": [0, 0], "b": [100, 100]}]}})
    aba.navegar(f"{base}/cad?projeto={s}&desenho=rascunho", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'", 60)
    aba.avaliar("window.cad.dialogoPranchas(); 1")
    esperar(aba, "!!document.querySelector('dialog[open]') && /Montar pranchas/.test(document.querySelector('dialog[open]').textContent)", 15)
    vals = aba.avaliar("[...document.querySelectorAll('dialog[open] label')].filter(l => ['Obra', 'Projetista', 'Revisão'].includes(l.firstChild && l.firstChild.textContent)).map(l => l.querySelector('input').value)") or []
    ok(vals == ["Sooro – galpão", "Eng. Camila", "02"], f"o diálogo abre com a obra, o projetista e a revisão gravados: {vals}")
    aba.avaliar("document.querySelector('dialog[open]').close('cancelar'); 1")


def q21_cartao_importado(aba):
    """Q21: depois de importar o IFC o 3D abria sem dizer o que veio; agora o cartão "Importado" com as contagens e o
    próximo passo, uma vez."""
    print("Q21 — cartão Importado no 3D")
    s = projeto("Sooro importado", tipo="ifc")
    arq = os.path.join(_pasta_do_projeto(urllib.parse.unquote(s)), "projeto.json")
    with open(arq, encoding="utf-8") as f:
        pj = json.load(f)
    pj["importacao_resumo"] = {"pecas": 4047, "barras": 1085, "chapas": 652, "fixadores": 1342, "telhas": 968, "outras": 0,
                               "perfis_fora": [], "n_perfis_fora": 0, "marcas": {"pecas": 162, "conjuntos": 125, "exemplo": "M1, P106"}}
    pj["origem_ifc"] = "teste.ifc"
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(pj, f)
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto && document.body.dataset.pronto === '1'", 60)
    tem = esperar(aba, "!!document.querySelector('.cartao-importado')", 15)
    txt = aba.avaliar("(document.querySelector('.cartao-importado') || {}).textContent || ''") or ""
    ok(tem and "4.047" in txt and "652 chapas" in txt and "Próximo: Detalhar" in txt, f"o cartão Importado: {txt[:120]}")


def q24_padroes_recolhidos(aba):
    """Q24: com nada selecionado, o painel Propriedades mostrava "Perfil W310×38,7 / Aço / Papel viga / Camada Chapas" —
    os padrões de desenho pareciam propriedades. Agora o resumo do modelo, e os padrões num bloco recolhido com o nome."""
    print("Q24 — os padrões de desenho recolhidos no painel sem seleção")
    s = projeto("Sooro painel", tipo="ifc")
    aba.navegar(f"{base}/editor?projeto={s}", limite=60)
    esperar(aba, "window.editor && window.editor.projeto && document.body.dataset.pronto === '1'", 60)
    aba.avaliar("window.editor.selecao.definir([]); window.editor._agendarPaineis('props'); 1")
    tem = esperar(aba, "!!window.editor.el.props.querySelector('details.padroes-de-desenho')", 10)
    estado = aba.avaliar("(() => { const d = window.editor.el.props.querySelector('details.padroes-de-desenho'); return d ? [d.open, d.querySelector('summary').textContent] : null; })()")
    ok(tem and estado and estado[0] is False and "Padrões para desenhar novas peças" in estado[1], f"padrões recolhidos e com nome: {estado}")


#: os blocos dos achados Q (IFC → pranchas), rodados depois dos P
BLOCOS_Q = (q01_pdf_recusado_ver_no_3d, q02_q03_dialogo_detalhar, q12_busca_pelo_nome_de_producao, q11_detalhar_ifc_avulso, q18_avisos_e_contagem_do_pdf, q19_dxf_de_corte_na_aba_chapas, q20_dialogo_das_pranchas_lembra, q21_cartao_importado, q24_padroes_recolhidos)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_primeiro_uso_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
    # python verif_primeiro_uso_ui.py p07 → só os blocos cujo nome começa assim
    for bloco in [b for b in (p02_p13_recebido, p06_vao_pequeno, p11_p12_cad, p07_menu_antes_do_editor, p07_menu_com_o_2d_a_mostra,
                                p08_folhas_sem_pedir_o_arquivo, p19_resultado_do_recebido,
                                p14_quadros_vazios, p26_padroes_da_planta, p21_peso_do_modelo_vazio,
                                p22_nome_e_posicao, p23_lista_sob_medida, p15_zoom_da_roda,
                                p18_uma_barra_de_ferramentas, p17_busca_acha_desenho, p16_camadas_do_arquivo) + BLOCOS_Q
                  if not sys.argv[1:] or any(b.__name__.startswith(a) for a in sys.argv[1:])]:
        try:
            bloco(aba)
        except Exception as e:                       # noqa: BLE001
            ok(False, f"{bloco.__name__}: {e}")
    # o 3D leve de um projeto sem modelo responde 404 (o visor mostra "sem modelo"): não é erro da tela
    # e o "sair sem salvar?" do editor com o modelo em branco não gravado (P21), que o Chrome sem janela bloqueia
    erros = [m for m in aba.console if m[0] in ("error", "excecao") and not ("404" in m[1] and "/3d-leve" in m[1])
             and "Blocked attempt to show a 'beforeunload'" not in m[1]]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
