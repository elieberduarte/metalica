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
    for bloco in [b for b in (p02_p13_recebido, p06_vao_pequeno, p11_p12_cad, p07_menu_antes_do_editor,
                                p08_folhas_sem_pedir_o_arquivo, p19_resultado_do_recebido,
                                p14_quadros_vazios, p26_padroes_da_planta)
                  if not sys.argv[1:] or any(b.__name__.startswith(a) for a in sys.argv[1:])]:
        try:
            bloco(aba)
        except Exception as e:                       # noqa: BLE001
            ok(False, f"{bloco.__name__}: {e}")
    # o 3D leve de um projeto sem modelo responde 404 (o visor mostra "sem modelo"): não é erro da tela
    erros = [m for m in aba.console if m[0] in ("error", "excecao") and not ("404" in m[1] and "/3d-leve" in m[1])]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
