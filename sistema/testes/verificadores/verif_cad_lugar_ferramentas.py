# -*- coding: utf-8 -*-
"""O lugar das ferramentas do CAD 2D (DECISÃO do usuário, 25/10, "Cotas e símbolos em cima": a barra da esquerda passava
da altura da tela), com o mouse de verdade, na área de trabalho (/dividida) e no CAD sozinho, em cada tamanho de TELAS:
  A. nenhuma coluna rola: a da esquerda (Nav, desenho, edição — baixa os botões ou vira duas colunas quando não cabe) e
     a da direita (os elementos, mais Medir, Dividir e os blocos);
  B. cada cota e cada símbolo está num lugar só: na faixa de cima (no espaço livre da barra) ou, quando não cabe, na
     esquerda; em 1920 de largura cabem todos em cima;
  C. o clique em cada botão de cima abre a ferramenta (e o botão acende); os da direita e alguns da esquerda também;
  D. na vista só 3D a faixa de cima some; de volta ao 2D, aparece."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (largura, altura, cabem todas em cima?) — a de 2556 × 983 é a tela do usuário (o print de 25/10)
TELAS = [(1600, 900, None), (1366, 768, None), (1920, 1040, True), (2556, 983, True)]
TOPO = ["cota", "cota_continua", "cota_base", "cota_angular", "cota_raio", "cota_diametro", "cota_ordenada", "cota_rapida", "mover_cota", "chamada", "seta_chamada",
        "simbolo_solda", "balao_marca", "simbolo_nivel", "chamada_detalhe", "nuvem_revisao", "grade_furos"]
DIREITA = ["medir", "dividir", "criar_bloco", "inserir_bloco"]
ESQUERDA = ["linha", "offset", "apagar", "hachura"]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_lugar_")
PASTA = os.path.join(DADOS, "obra-lugar")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra lugar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-25T00:00:00", "alterado": "2026-10-25T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Planta", escala=1.0)
d.add(Linha(id="h", a=(0, 0), b=(1000, 0)))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "planta.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_lugar_")
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

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=40.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.25)
        return False

    def clicar(x, y):
        for tipo, b, n in (("mouseMoved", "none", 0), ("mousePressed", "left", 1), ("mouseReleased", "left", 0)):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=b, buttons=n, clickCount=1)
        aba.drenar(0.2)

    def rodada(rotulo, url, area, w, h, todas_em_cima):
        print(f"\n== {rotulo} {w}×{h}")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        aba.navegar(f"http://localhost:{PORTA}{url}", limite=60)
        # C = o documento do CAD; T = o documento da faixa de cima
        C = "document.getElementById('f2d').contentWindow" if area else "window"
        T = "document" if area else "window.document"
        ok(esperar(f"{C}.cad && {C}.document.body.dataset.pronto === '1' && {T}.getElementById('ferramentas-2d-topo') && "
                   f"{C}.document.querySelector('#barra-disciplina [data-ferramenta=medir]')"), "o CAD abriu, com a faixa de cima e a direita montadas")
        aba.drenar(1.0)
        cols = js(f"""const d = {C}.document; const m = (id) => {{ const b = d.getElementById(id); return [b.clientHeight, b.scrollHeight, b.className]; }};
                     return {{ esq: m('barra-ferramentas'), dir: m('barra-disciplina') }};""")
        ok(cols and cols["esq"][1] <= cols["esq"][0] + 1, f"A. a esquerda não rola ({cols and cols['esq']})")
        ok(cols and cols["dir"][1] <= cols["dir"][0] + 1, f"A. a direita não rola ({cols and cols['dir']})")
        lugar = js(f"""const d = {C}.document, t = {T};
          return {json.dumps(TOPO)}.map(id => {{ const a = t.querySelector('[data-ferramenta-topo="' + id + '"]'), e = d.querySelector('#barra-ferramentas [data-ferramenta="' + id + '"]');
            return [id, !!(a && a.offsetParent), !!(e && e.offsetParent)]; }});""")
        dobrados = [x[0] for x in lugar if x[1] == x[2]]
        em_cima = [x[0] for x in lugar if x[1]]
        ok(not dobrados, f"B. cada cota e símbolo num lugar só ({len(em_cima)} em cima; em nenhum ou nos dois: {dobrados})")
        if todas_em_cima: ok(len(em_cima) == len(TOPO), f"B. cabem todas em cima ({len(em_cima)} de {len(TOPO)})")
        # C. o clique de verdade: em cima (na barra), na direita e na esquerda (no CAD: a posição da moldura soma)
        for id in em_cima:
            js(f"{C}.cad.ativarFerramenta('selecionar'); return 1;")
            p = js(f"const b = {T}.querySelector('[data-ferramenta-topo=\"{id}\"]'); const r = b.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2];")
            clicar(*p)
            r = js(f"return [{C}.cad.ferramenta.constructor.id, {T}.querySelector('[data-ferramenta-topo=\"{id}\"]').getAttribute('aria-pressed')];")
            ok(r == [id, "true"], f"C. em cima: {id} ({r})")
        for id in DIREITA + ESQUERDA:
            js(f"{C}.cad.ativarFerramenta('selecionar'); return 1;")
            p = js(f"""const f = {'document.getElementById("f2d").getBoundingClientRect()' if area else '({left: 0, top: 0})'};
                      const b = {C}.document.querySelector('{'#barra-disciplina' if id in DIREITA else '#barra-ferramentas'} [data-ferramenta="{id}"]');
                      if (!b || !b.offsetParent) return null; const r = b.getBoundingClientRect(); return [f.left + r.left + r.width / 2, f.top + r.top + r.height / 2];""")
            if not p: ok(False, f"C. {id}: o botão não está à vista"); continue
            # o Criar bloco sem seleção e o Inserir bloco sem blocos voltam ao Selecionar na hora: vale a ferramenta pedida
            js(f"const c = {C}.cad; c._pedidas = []; if (!c._ativarOriginal) {{ c._ativarOriginal = c.ativarFerramenta; c.ativarFerramenta = function (i) {{ (this._pedidas || []).push(i); return this._ativarOriginal(i); }}; }} return 1;")
            clicar(*p)
            r = js(f"const c = {C}.cad, d = {C}.document.getElementById('dialogo'); if (d && d.open) d.close(); return (c._pedidas || [])[0] || c.ferramenta.constructor.id;")
            ok(r == id, f"C. {'na direita' if id in DIREITA else 'na esquerda'}: {id} ({r})")
        js(f"{C}.cad.ativarFerramenta('selecionar'); return 1;")
        if area:
            js("document.querySelector('nav.vistas [data-vista=\"3d\"]').click(); return 1;"); aba.drenar(0.6)
            ok(js("return getComputedStyle(document.getElementById('ferramentas-2d-topo')).display;") == "none", "D. na vista só 3D a faixa some")
            js("document.querySelector('nav.vistas [data-vista=\"2d\"]').click(); return 1;"); aba.drenar(0.8)
            ok(js("return [...document.querySelectorAll('#ferramentas-2d-topo [data-ferramenta-topo]')].filter(b => b.offsetParent).length;") == len(em_cima),
               "D. de volta ao 2D, a faixa aparece com as mesmas")
        erros = [x for x in aba.console if x[0] in ("error", "excecao") and "/3d-leve" not in x[1]]     # o 3D da área num projeto sem modelo
        ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
        aba.console.clear()

    for (w, h, todas) in TELAS:
        rodada("área de trabalho", "/dividida?projeto=obra-lugar&vista=2d&desenho=planta", True, w, h, todas)
    rodada("CAD sozinho", "/cad?projeto=obra-lugar&desenho=planta", False, 1600, 900, None)
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
