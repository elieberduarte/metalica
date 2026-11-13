# -*- coding: utf-8 -*-
"""Imprimir pranchas (21/10, pedido do usuário: "criar a ferramenta de impressão das pranchas diretamente do
sistema"; 12/11, a tela A do "precisamos melhorar a ferramenta de gestão das impressões" —
Projeto/ANALISES/Interface/Impressao-gerenciador-proposta-2026-11-12.pdf), com o teclado e o mouse de verdade (CDP):
  A. Ctrl+P no desenho das pranchas lado a lado abre o diálogo LARGO, sem rolagem de lado, com as folhas do projeto
     (as soltas e as do desenho lado a lado, na ordem do PDF), todas marcadas, o título inteiro, o formato, a escala
     (a das células), a revisão (a do carimbo) e a situação ("nunca impressa");
  B. a plotter da fábrica vem marcada quando existe (DECISÃO 12/11), mesmo com outra padrão no Windows;
  C. "Só a da tela" deixa a folha do meio da tela, e ela é a da pré-visualização; "Nenhuma" + o clique numa folha, só
     ela; a folha de outro desenho não tem pré-visualização e diz por quê;
  D. a impressora troca os papéis de cada folha (o da folha primeiro, depois a série A, o "ISOA1" do driver como A1);
     o papel escolhido numa folha diz se ela vai em tamanho real ou ajustada;
  E. Imprimir manda pela "Microsoft Print to PDF" (que grava em pranchas/ do projeto) só a folha marcada, no A3;
  F. aberto de novo: a folha impressa diz "impressa dd/mm"; mudada no disco, "mudou depois da impressão" e "Só as que
     mudaram (1)" marca só ela;
  G. "Salvar a seleção como…" guarda um conjunto da obra, que marca as folhas dele e continua lá ao abrir de novo; o ×
     apaga;
  H. pelo menu Desenho › Imprimir pranchas…, a cor lembrada; Cancelar fecha sem imprimir;
  I. o Enter no campo Cópias não imprime (D04 do usuario-desastrado, 13/11: imprimia na hora, com a plotter marcada).

Nunca imprime na impressora padrão da máquina nem na plotter: antes do clique em Imprimir confere que a escolhida é a
Microsoft Print to PDF, e sem ela o verificador para."""
import datetime, json, os, re, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Texto
from nucleo2d import pranchas
from saida import impressao

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PDF_DO_WINDOWS = "Microsoft Print to PDF"
IMPRESSORAS = impressao.impressoras()["impressoras"] if sys.platform == "win32" else []
if not any(p["nome"] == PDF_DO_WINDOWS for p in IMPRESSORAS):
    print("  ok    sem a Microsoft Print to PDF do Windows: nada a verificar")
    sys.exit(0)
PLOTTER = next((p["nome"] for p in IMPRESSORAS if re.search(r"designjet|t120|plotter", p["nome"] + " " + p["driver"].replace("Microsoft IPP Class Driver", ""), re.I)), None)
TITULO_LONGO = "PLANTA DE LOCAÇÃO DOS CHUMBADORES, CHUMBAMENTO – PILARES, BASES E NIVELAMENTO DAS PLACAS DE BASE"

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_impressao_")
PASTA = os.path.join(DADOS, "obra-impressao")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
# a revisão 01 lançada na prancha 2 (o carimbo do projeto)
json.dump({"formato": 1, "nome": "Obra impressão", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None,
           "carimbo_pranchas": {"revisoes": {"2": [{"rev": "00", "data": "01/11/2026", "descricao": "EMISSÃO INICIAL", "por": ""},
                                                   {"rev": "01", "data": "10/11/2026", "descricao": "chumbação revisada", "por": ""}]}}},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def _a4(titulo, i, n, escalas=()):
    d = Desenho(nome="Prancha %02d" % i, escala=1.0)
    d.add(Linha(a=(25, 7), b=(290, 7))); d.add(Linha(a=(290, 7), b=(290, 203)))
    d.add(Linha(a=(290, 203), b=(25, 203))); d.add(Linha(a=(25, 203), b=(25, 7)))
    d.add(Texto(posicao=(40, 150), texto=titulo[:20], altura=12))
    d.metadados["prancha"] = {"formato": "A4", "numero": i, "total": n, "titulo": titulo,
                              "celulas": [{"titulo": "c%d" % k, "escala": e} for k, e in enumerate(escalas)]}
    return d


def _gravar(d, nome):
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", nome + ".desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)


_gravar(_a4("FOLHA 1", 1, 3, (25, 25, 10)), "prancha-01")
_gravar(_a4("FOLHA 2", 2, 3, (50,)), "prancha-02")
_gravar(_a4(TITULO_LONGO, 3, 3, (25, 10, 100)), "prancha-03")
# o desenho das pranchas lado a lado (o de Montar pranchas): as folhas 4 e 5 do PDF
_gravar(pranchas.juntar_pranchas([_a4("LADO A LADO 1", 1, 2), _a4("LADO A LADO 2", 2, 2)], nome="Pranchas"), "pranchas")
SAIDA = os.path.join(PASTA, "pranchas", "impressao-microsoft-print-to-pdf.pdf")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_impressao_")
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

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.3)
        return False

    def clicar(seletor_js):
        """Clique de verdade no meio do elemento (a expressão JS que o acha)."""
        r = js(f"const e = {seletor_js}; if (!e) return null; e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True

    def escolher(seletor, valor):
        """O <select> do diálogo (a lista nativa não abre no Chrome sem janela): o valor e o change, como a escolha."""
        return js(f"const s = document.querySelector({json.dumps(seletor)}); s.value = {json.dumps(valor)}; s.dispatchEvent(new Event('change', {{bubbles: true}})); return s.value;")

    def botao(texto):
        return f"[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent.startsWith({json.dumps(texto)}))"

    def linhas():
        return js("""return [...document.querySelectorAll('dialog[open] .folhas tbody tr')].map(tr => {
            const td = [...tr.children]; return { marcada: td[0].querySelector('input').checked, num: td[1].textContent, titulo: td[2].textContent,
              formato: td[3].textContent, escala: td[4].textContent, rev: td[5].textContent, situacao: td[6].textContent, estado: td[6].dataset.estado }; });""") or []

    def abrir_pelo_teclado():
        clicar("document.querySelector('canvas')")
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="p", code="KeyP", windowsVirtualKeyCode=80, modifiers=2)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="p", code="KeyP", windowsVirtualKeyCode=80, modifiers=2)
        return esperar("document.querySelector('dialog[open] .impressao-folhas') && document.querySelectorAll('dialog[open] .folhas tbody tr').length === 5", 30)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-impressao&desenho=pranchas", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 0", 40), "o CAD abriu o desenho das pranchas")
    aba.console.clear()
    # a vista na segunda folha do desenho lado a lado
    js("const f = cad.doc.metadados.pranchas[1]; cad.tela.enquadrar([f.origem, [f.origem[0] + f.tamanho[0], f.origem[1] + f.tamanho[1]]]); return 1;")
    aba.drenar(0.5)

    # ------------------------------------------------------------------ A. o diálogo largo e as colunas
    ok(abrir_pelo_teclado(), "A. Ctrl+P abre o Imprimir pranchas")
    L = linhas()
    ok(len(L) == 5 and all(x["marcada"] for x in L) and "FOLHA 2" in L[1]["titulo"] and "LADO A LADO 2" in L[4]["titulo"],
       f"A. as 5 folhas do projeto, na ordem do PDF, todas marcadas: {[x['titulo'][:20] for x in L]}")
    ok(L and L[2]["titulo"] == TITULO_LONGO, f"A. o título inteiro, sem corte: {L[2]['titulo'] if L else None!r}")
    medidas = js("""const d = document.querySelector('dialog[open]'), t = d.querySelector('.folhas'), f = d.querySelector('form') || d;
        return { dialogo: d.getBoundingClientRect().width, tabela: [t.scrollWidth, t.clientWidth], corpo: [f.scrollWidth, f.clientWidth] };""") or {}
    ok(medidas.get("dialogo", 0) >= 1000 and medidas["tabela"][0] <= medidas["tabela"][1] + 1 and medidas["corpo"][0] <= medidas["corpo"][1] + 1,
       f"A. o diálogo largo, sem rolagem de lado (era 440 px com a barra de rolagem): {medidas}")
    ok([x["formato"] for x in L] == ["A4"] * 5, f"A. o formato: {[x['formato'] for x in L]}")
    ok([x["escala"] for x in L[:3]] == ["1:25 / 1:10", "1:50", "várias"], f"A. a escala das células: {[x['escala'] for x in L]}")
    ok(L[1]["rev"] == "01" and L[0]["rev"] == "—", f"A. a revisão do carimbo (a prancha 2 na 01): {[x['rev'] for x in L]}")
    ok(all(x["estado"] == "nunca" and "nunca impressa" in x["situacao"] for x in L), f"A. a situação: {[x['situacao'] for x in L]}")

    # ------------------------------------------------------------------ B. a plotter marcada
    escolhida = js("return document.querySelector('dialog[open] select[name=impressora]').value;")
    if PLOTTER:
        ok(escolhida == PLOTTER, f"B. a plotter da fábrica vem marcada ({escolhida!r}; a padrão do Windows é outra ou a mesma)")
    else:
        ok(escolhida == impressao.impressoras()["padrao"], f"B. sem plotter instalada, a padrão do Windows ({escolhida!r})")

    # ------------------------------------------------------------------ C. só a da tela, a pré-visualização, uma folha
    clicar(botao("Só a da tela"))
    marcadas = [x["marcada"] for x in linhas()]
    ok(marcadas == [False, False, False, False, True], f"C. Só a da tela: a folha 2 do desenho lado a lado, que está na tela: {marcadas}")
    ok(esperar("(() => { const t = cad._previaImpressao && cad._previaImpressao(); const c = document.querySelector('dialog[open] canvas.previa-folha');"
               " return t && c && !c.hidden && c.width > 50 && document.querySelector('dialog[open] tr.foco') === document.querySelectorAll('dialog[open] .folhas tbody tr')[4]; })()", 10),
       "C. a pré-visualização mostra a folha da tela (desenhada pela tela do CAD)")
    clicar("document.querySelectorAll('dialog[open] .folhas tbody tr td.titulo')[0]")
    leg = js("return [document.querySelector('dialog[open] canvas.previa-folha').hidden, document.querySelector('dialog[open] .previa .leg').textContent];") or [None, ""]
    ok(leg[0] is True and "desenho aberto" in leg[1], f"C. a folha de outro desenho: sem pré-visualização, dizendo por quê: {leg}")
    clicar(botao("Nenhuma"))
    clicar("document.querySelectorAll('dialog[open] .folhas tbody tr input')[1]")
    conta = js("return document.querySelector('dialog[open] .rodape-impressao .conta').textContent;")
    ok(conta == "1 de 5 folha(s)", f"C. Nenhuma + o clique na folha 2: {conta}")

    # ------------------------------------------------------------------ D. a impressora de teste e o papel da folha
    escolher("dialog[open] select[name=impressora]", PDF_DO_WINDOWS)
    ok(esperar("(() => { const s = document.querySelectorAll('dialog[open] select.papel-folha')[1]; return !s.disabled && [...s.options].some(o => o.value === '8'); })()", 30),
       "D. os papéis da Microsoft Print to PDF carregados em cada folha (o A3 entre eles)")
    primeiro = js("return [...document.querySelectorAll('dialog[open] select.papel-folha')[1].options].slice(0, 4).map(o => o.textContent);")
    ok(primeiro and primeiro[0] == "o da folha" and [o.split(" ")[0] for o in primeiro[1:]] == ["A0", "A1", "A2"],
       f"D. o da folha e a série A primeiro, o ISOA1 do driver como A1: {primeiro}")
    escolher("dialog[open] .folhas tbody tr:nth-child(2) select.papel-folha", "8")
    texto_a3 = js("const s = document.querySelectorAll('dialog[open] select.papel-folha')[1]; return s.options[s.selectedIndex].textContent;")
    ok(texto_a3 and texto_a3.startswith("A3") and "tamanho real" in texto_a3, f"D. a A4 no A3: em tamanho real ({texto_a3})")
    a4 = js("const s = document.querySelectorAll('dialog[open] select.papel-folha')[1]; return [...s.options].map(o => o.textContent).find(t => t.startsWith('A5')) || '';")
    ok("ajustada" in (a4 or ""), f"D. num papel menor, ajustada: {a4}")
    resumo = js("return document.querySelector('dialog[open] .resumo').textContent;") or ""
    ok("1 folha(s)" in resumo and "A3" in resumo and "revisão 01" in resumo, f"D. o resumo: {resumo}")

    # ------------------------------------------------------------------ E. imprimir (só na impressora que grava em arquivo)
    escolhida = js("return document.querySelector('dialog[open] select[name=impressora]').value;")
    if escolhida != PDF_DO_WINDOWS:
        ok(False, f"a impressora escolhida não é a de teste ({escolhida}): não imprimo")
        raise SystemExit
    clicar("document.querySelector('dialog[open] .botao-ok')")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => a.textContent.includes('gravada(s) em PDF'))", 120),
       "E. Imprimir: o aviso de gravada em PDF pela Microsoft Print to PDF")
    aviso = js("return [...document.querySelectorAll('.aviso, .avisos *')].map(a => a.textContent).find(t => t.includes('gravada(s) em PDF')) || '';")
    ok("1 folha(s)" in (aviso or "") and "A3" in (aviso or ""), f"E. uma folha, no A3: {aviso}")
    import pymupdf
    for _ in range(20):
        if os.path.exists(SAIDA): break
        time.sleep(0.5)
    if os.path.exists(SAIDA):
        doc = pymupdf.open(SAIDA)
        pg = doc[0]
        w, h = pg.rect.width / 72 * 25.4, pg.rect.height / 72 * 25.4
        pix = pg.get_pixmap(dpi=20, colorspace=pymupdf.csGRAY)
        escuros = sum(1 for b in pix.samples if b < 128)
        ok(doc.page_count == 1 and abs(w - 420) < 2 and abs(h - 297) < 2 and escuros > 20,
           f"E. o arquivo: {doc.page_count} página, {w:.0f} × {h:.0f} mm, {escuros} pixels escuros (a folha desenhada)")
        doc.close()
    else:
        ok(False, f"E. o arquivo da impressão não foi gravado: {SAIDA}")
    hist = json.load(open(os.path.join(PASTA, "impressoes.json"), encoding="utf-8"))["historico"]
    ok(len(hist) == 1 and [f["chave"] for f in hist[0]["folhas"]] == ["prancha-02|2"] and hist[0]["folhas"][0]["revisao"] == "01",
       f"E. o histórico no projeto: a folha 2, revisão 01 ({hist})")

    # ------------------------------------------------------------------ F. impressa; mudada, "mudou depois"
    hoje = datetime.date.today().strftime("%d/%m")
    ok(abrir_pelo_teclado(), "F. aberto de novo")
    L = linhas()
    ok(L[1]["estado"] == "impressa" and hoje in L[1]["situacao"] and all(x["estado"] == "nunca" for i, x in enumerate(L) if i != 1),
       f"F. a folha 2 impressa hoje, as outras nunca: {[x['situacao'] for x in L]}")
    clicar("document.querySelector('#dialogo-cancelar')")
    caminho = os.path.join(PASTA, "desenhos-2d", "prancha-02.desenho.json")
    d2 = Desenho.de_dict(json.load(open(caminho, encoding="utf-8")))
    d2.add(Texto(posicao=(60, 60), texto="NOTA NOVA", altura=5))
    _gravar(d2, "prancha-02")
    ok(abrir_pelo_teclado(), "F. aberto depois de mudar a folha 2")
    L = linhas()
    ok(L[1]["estado"] == "mudou" and "mudou depois da impressão" in L[1]["situacao"], f"F. a folha 2 mudou depois da impressão: {L[1]['situacao']}")
    clicar(botao("Só as que mudaram"))
    ok([x["marcada"] for x in linhas()] == [False, True, False, False, False], f"F. Só as que mudaram (1): só a folha 2 ({[x['marcada'] for x in linhas()]})")

    # ------------------------------------------------------------------ G. os conjuntos
    clicar(botao("Nenhuma"))
    clicar("document.querySelectorAll('dialog[open] .folhas tbody tr input')[0]")
    clicar("document.querySelectorAll('dialog[open] .folhas tbody tr input')[2]")
    clicar(botao("Salvar a seleção como"))
    clicar("document.querySelector('dialog[open] input[name=nome-conjunto]')")
    aba.cmd("Input.insertText", text="Fabricação")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    ok(esperar("[...document.querySelectorAll('dialog[open] select[name=conjunto] option')].some(o => o.value === 'Fabricação')", 10)
       and js("return !!document.querySelector('dialog[open]');"), "G. o conjunto guardado, sem fechar o diálogo (o Enter no nome)")
    clicar(botao("Todas"))
    escolher("dialog[open] select[name=conjunto]", "Fabricação")
    ok([x["marcada"] for x in linhas()] == [True, False, True, False, False], f"G. o conjunto marca as folhas dele: {[x['marcada'] for x in linhas()]}")
    clicar("document.querySelector('#dialogo-cancelar')")
    ok(abrir_pelo_teclado(), "G. aberto de novo")
    ok("Fabricação" in (js("return [...document.querySelectorAll('dialog[open] select[name=conjunto] option')].map(o => o.value);") or []),
       "G. o conjunto continua na obra")
    escolher("dialog[open] select[name=conjunto]", "Fabricação")
    clicar("[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent === '×')")
    ok(esperar("![...document.querySelectorAll('dialog[open] select[name=conjunto] option')].some(o => o.value === 'Fabricação')", 10)
       and not json.load(open(os.path.join(PASTA, "impressoes.json"), encoding="utf-8"))["conjuntos"], "G. o × apaga o conjunto")
    clicar("document.querySelector('#dialogo-cancelar')")

    # ------------------------------------------------------------------ H. pelo menu
    clicar("document.querySelector('.menu[data-menu=desenho] .menu-botao')")
    ok(clicar("document.querySelector('.menu[data-menu=desenho] button[data-acao=imprimir]')"), "H. o item Desenho › Imprimir pranchas…")
    ok(esperar("document.querySelectorAll('dialog[open] .folhas tbody tr').length === 5", 30), "H. o diálogo abriu de novo pelo menu")
    lembrado = js("const q = (n) => document.querySelector(`dialog[open] select[name=${n}]`).value; return [q('impressora'), q('cor')];")
    ok(lembrado == [PLOTTER or impressao.impressoras()["padrao"], "preto"], f"H. a plotter de novo (não a última usada) e a cor lembrada: {lembrado}")
    clicar("document.querySelector('#dialogo-cancelar')")
    ok(js("return !document.querySelector('dialog[open]');"), "H. Cancelar fecha sem imprimir")

    # ------------------------------------------------------------------ I. o Enter em Cópias não imprime (D04, 13/11)
    # antes, a Microsoft Print to PDF marcada (se o Enter imprimir, sai no arquivo) e o pedido de imprimir interceptado
    ok(abrir_pelo_teclado(), "I. aberto de novo")
    escolher("dialog[open] select[name=impressora]", PDF_DO_WINDOWS)
    js("""window.__imprimiu = 0; const f0 = window.fetch;
        window.fetch = (u, o) => { if (String(u).includes('/impressao/imprimir')) { window.__imprimiu++; return Promise.resolve(new Response('{}')); }
                                   return f0(u, o); }; return 1;""")
    clicar("document.querySelector('dialog[open] input[name=copias]')")
    js("const c = document.querySelector('dialog[open] input[name=copias]'); c.select(); return 1;")
    aba.cmd("Input.insertText", text="2")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
    aba.drenar(1.5)
    estado = js("return [!!document.querySelector('dialog[open] .impressao-folhas'), window.__imprimiu, (document.querySelector('dialog[open] input[name=copias]') || {}).value];")
    ok(estado == [True, 0, "2"], f"I. o Enter em Cópias não imprime: o diálogo aberto, nenhum pedido de imprimir, as 2 cópias no campo ({estado})")
    clicar("document.querySelector('#dialogo-cancelar')")
    ok(js("return !document.querySelector('dialog[open]') && window.__imprimiu === 0;"), "I. Cancelar fecha sem imprimir")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
