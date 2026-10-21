# -*- coding: utf-8 -*-
"""Imprimir pranchas (21/10, pedido do usuário: "criar a ferramenta de impressão das pranchas diretamente do
sistema"), com o teclado e o mouse de verdade (CDP): Ctrl+P no desenho das pranchas lado a lado abre o diálogo com
as folhas do projeto (as pranchas soltas e as do desenho lado a lado, na ordem do PDF), todas marcadas; "Só a da tela"
deixa só a folha que está no meio da tela, e "Nenhuma" + o clique numa folha, só ela; a impressora troca os papéis
(a série A primeiro, o "ISOA1" do driver como A1); A4 num A3 ajustado avisa que amplia; Imprimir manda pela
"Microsoft Print to PDF" (que grava em pranchas/ do projeto, sem a janela do Windows) só a folha marcada, no papel
A3; o menu Desenho › Imprimir pranchas… abre de novo com a última escolha lembrada.

Nunca imprime na impressora padrão da máquina (a plotter da fábrica): antes do clique em Imprimir confere que a
escolhida é a Microsoft Print to PDF, e sem ela o verificador para."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Texto
from nucleo2d import pranchas
from saida import impressao

PDF_DO_WINDOWS = "Microsoft Print to PDF"
if sys.platform != "win32" or not any(p["nome"] == PDF_DO_WINDOWS for p in impressao.impressoras()["impressoras"]):
    print("  ok    sem a Microsoft Print to PDF do Windows: nada a verificar")
    sys.exit(0)

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_impressao_")
PASTA = os.path.join(DADOS, "obra-impressao")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra impressão", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
def _a4(titulo, i, n):
    d = Desenho(nome="Prancha %02d" % i, escala=1.0)
    d.add(Linha(a=(25, 7), b=(290, 7))); d.add(Linha(a=(290, 7), b=(290, 203)))
    d.add(Linha(a=(290, 203), b=(25, 203))); d.add(Linha(a=(25, 203), b=(25, 7)))
    d.add(Texto(posicao=(40, 150), texto=titulo, altura=12))
    d.metadados["prancha"] = {"formato": "A4", "numero": i, "total": n, "titulo": titulo}
    return d


def _gravar(d, nome):
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", nome + ".desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)


for i in range(1, 4):
    _gravar(_a4("FOLHA %d" % i, i, 3), "prancha-%02d" % i)
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

    def escolher(nome, valor):
        """O <select> do diálogo (a lista nativa não abre no Chrome sem janela): o valor e o change, como a escolha."""
        return js(f"const s = document.querySelector('dialog[open] select[name={nome}]'); s.value = {json.dumps(valor)}; s.dispatchEvent(new Event('change', {{bubbles: true}})); return s.value;")

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-impressao&desenho=pranchas", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 0", 40), "o CAD abriu o desenho das pranchas")
    aba.console.clear()
    # a vista na segunda folha do desenho lado a lado
    js("const f = cad.doc.metadados.pranchas[1]; cad.tela.enquadrar([f.origem, [f.origem[0] + f.tamanho[0], f.origem[1] + f.tamanho[1]]]); return 1;")
    aba.drenar(0.5)

    # Ctrl+P no desenho
    clicar("document.querySelector('canvas')")
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="p", code="KeyP", windowsVirtualKeyCode=80, modifiers=2)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="p", code="KeyP", windowsVirtualKeyCode=80, modifiers=2)
    ok(esperar("document.querySelector('dialog[open] .impressao')", 20), "Ctrl+P abre o Imprimir pranchas")
    folhas = js("return [...document.querySelectorAll('dialog[open] .folhas label')].map(l => [l.querySelector('input').checked, l.textContent]);") or []
    ok(len(folhas) == 5 and all(f[0] for f in folhas) and "FOLHA 2" in folhas[1][1] and "A4" in folhas[1][1]
       and "LADO A LADO 2" in folhas[4][1], f"as 5 folhas do projeto, na ordem do PDF, todas marcadas: {folhas}")
    clicar("[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent === 'Só a da tela')")
    marcadas = js("return [...document.querySelectorAll('dialog[open] .folhas input')].map(c => c.checked);")
    ok(marcadas == [False, False, False, False, True], f"Só a da tela: a folha 2 do desenho lado a lado, que está na tela: {marcadas}")
    imps = js("return [...document.querySelectorAll('dialog[open] select[name=impressora] option')].map(o => o.value);") or []
    ok(PDF_DO_WINDOWS in imps, f"as impressoras do Windows na lista ({len(imps)})")

    # a impressora de teste e os papéis dela
    escolher("impressora", PDF_DO_WINDOWS)
    ok(esperar("(() => { const s = document.querySelector('dialog[open] select[name=papel]'); return !s.disabled && [...s.options].some(o => o.value === '8'); })()", 30),
       "os papéis da Microsoft Print to PDF carregados (o A3 entre eles)")
    primeiro = js("return [...document.querySelectorAll('dialog[open] select[name=papel] option')].slice(0, 4).map(o => o.textContent);")
    ok(primeiro and primeiro[0].startswith("Automático") and [o.split(" ")[0] for o in primeiro[1:]] == ["A0", "A1", "A2"],
       f"o automático e a série A primeiro, o ISOA1 do driver como A1: {primeiro}")

    # só a folha 2
    clicar("[...document.querySelectorAll('dialog[open] .botoes-folhas button')].find(b => b.textContent === 'Nenhuma')")
    clicar("document.querySelectorAll('dialog[open] .folhas label')[1]")
    conta = js("return document.querySelector('dialog[open] .botoes-folhas .conta').textContent;")
    ok(conta == "1 de 5 folha(s)", f"Nenhuma + o clique na folha 2: {conta}")

    escolher("papel", "8"); escolher("ajuste", "ajustar")
    resumo = js("return document.querySelector('dialog[open] .resumo').textContent;") or ""
    ok("A4 no A3" in resumo and "ampliada" in resumo, f"o aviso da escala: {resumo}")

    # a guarda: só imprime na impressora que grava em arquivo
    escolhida = js("return document.querySelector('dialog[open] select[name=impressora]').value;")
    if escolhida != PDF_DO_WINDOWS:
        ok(False, f"a impressora escolhida não é a de teste ({escolhida}): não imprimo")
        raise SystemExit
    clicar("document.querySelector('dialog[open] .botao-ok')")
    ok(esperar("[...document.querySelectorAll('.aviso, .avisos *')].some(a => a.textContent.includes('gravada(s) em PDF'))", 120),
       "Imprimir: o aviso de gravada em PDF pela Microsoft Print to PDF")
    aviso = js("return [...document.querySelectorAll('.aviso, .avisos *')].map(a => a.textContent).find(t => t.includes('gravada(s) em PDF')) || '';")
    ok("1 folha(s)" in (aviso or "") and "A3" in (aviso or ""), f"uma folha, no A3: {aviso}")
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
           f"o arquivo: {doc.page_count} página, {w:.0f} × {h:.0f} mm, {escuros} pixels escuros (a folha desenhada)")
    else:
        ok(False, f"o arquivo da impressão não foi gravado: {SAIDA}")

    # pelo menu, com a última escolha lembrada
    clicar("document.querySelector('.menu[data-menu=desenho] .menu-botao')")
    ok(clicar("document.querySelector('.menu[data-menu=desenho] button[data-acao=imprimir]')"), "o item Desenho › Imprimir pranchas…")
    ok(esperar("(() => { const s = document.querySelector('dialog[open] select[name=papel]'); return s && !s.disabled && s.options.length > 1; })()", 30),
       "o diálogo abriu de novo pelo menu")
    lembrado = js("const q = (n) => document.querySelector(`dialog[open] select[name=${n}]`).value; return [q('impressora'), q('papel'), q('ajuste'), q('cor')];")
    ok(lembrado == [PDF_DO_WINDOWS, "8", "ajustar", "preto"], f"a última escolha lembrada: {lembrado}")
    clicar("document.querySelector('#dialogo-cancelar')")
    ok(js("return !document.querySelector('dialog[open]');"), "Cancelar fecha sem imprimir")
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
