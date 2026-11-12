# -*- coding: utf-8 -*-
"""A cena da obra na prancha (usuário, 11/11: "pode fazer" — etapa 4 da tela das Cenas; amostra-2 aprovada), no CAD 2D
de verdade:
  A. Inserir cena da obra…: a janela lista só as cenas com render; Inserir → a imagem no meio da tela, na proporção do
     render, com o título e o "sem escala" embaixo; a imagem aparece no canvas (o azul do render);
  B. o painel: a largura no papel muda a imagem sem distorcer;
  C. Fixa: a cópia congelada na pasta da obra, a entidade aponta para ela;
  D. gravar: a imagem no desenho; o PDF pela rota do CAD sai com a imagem dentro;
  E. o menu Desenhos › Pranchas tem o Inserir cena da obra…; sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Polilinha
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cena_prancha_")
OBRA = os.path.join(DADOS, "obra")
os.makedirs(os.path.join(OBRA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-11T00:00:00", "alterado": "2026-11-11T00:00:00", "dados": None},
          open(os.path.join(OBRA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Desenho", escala=1.0)
d.add(Polilinha(id="folha", vertices=[(0, 0), (420, 0), (420, 297), (0, 297)], fechada=True))
json.dump(d.dict(), open(os.path.join(OBRA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
for i, nome, render in (("fachada", "Fachada", True), ("lateral", "Lateral", False)):
    os.makedirs(os.path.join(OBRA, "cenas", "dados", i))
    json.dump({"id": i, "tipo": "3d", "nome": nome, "camera": {"posicao": [1, 2, 3], "alvo": [0, 0, 0], "fov": 45},
               "criada": "2026-11-11T08:00:00", "alterada": "2026-11-11T08:00:00"},
              open(os.path.join(OBRA, "cenas", "dados", i, "cena.json"), "w", encoding="utf-8"))
    if render:
        Image.new("RGB", (1600, 900), (40, 90, 210)).save(os.path.join(OBRA, "cenas", "Cena - %s (render).jpg" % nome), "JPEG")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cena_prancha_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(f"http://localhost:{PORTA}/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ const c = window.cad; {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=20.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.2)
        return False

    def imagem():
        return js("return [...c.doc.entidades.values()].find(e => e.tipo === 'imagem') || null;")

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra&desenho=desenho", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 1", 40), "o CAD abriu o desenho (a folha)")
    js("c.tela.enquadrar([[-20, -40], [440, 320]], 0.02); return 1;"); aba.drenar(0.3)
    aba.console.clear()

    print("A — Inserir cena da obra…")
    # pelo item do menu, como a pessoa (o botão data-acao do cabeçalho do CAD, que a barra única aciona — 12/11: o item
    # estava na barra mas não no CAD e test_barra_unica falhou)
    ok(js("const b = document.querySelector('[data-acao=\"inserir-cena\"]'); if (!b) return false; b.click(); return true;") is True,
       "o item Inserir cena da obra… no menu do CAD")
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-corpo input[name=cena-prancha]')"), "a janela abre")
    ids = js("return [...document.querySelectorAll('#dialogo-corpo input[name=cena-prancha]')].map(i => i.value);")
    ok(ids == ["fachada"], f"só as cenas com render ({ids})")
    js("document.getElementById('dialogo-ok').click(); return 1;")
    ok(esperar("[...c.doc.entidades.values()].some(e => e.tipo === 'imagem')", 15), "a imagem entrou no desenho")
    im = imagem() or {}
    ok(im.get("viva") is True and im.get("cena") == "fachada" and abs(im.get("largura", 0) - 250) < 0.01 and abs(im.get("altura", 0) - 250 * 900 / 1600) < 0.01,
       f"viva, 250 mm de largura, na proporção do render ({im.get('largura')} × {im.get('altura')})")
    textos = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'texto').map(e => e.texto);")
    ok(textos == ["PERSPECTIVA — FACHADA", 'sem escala · cena "Fachada" do 3D'], f"o título e o sem escala embaixo ({textos})")
    ok(esperar("c.tela._imagensCarregadas && [...c.tela._imagensCarregadas.values()].some(i => i._pronta)", 15), "a imagem do render carregou na tela")
    js("c.selecionar([]); c.tela._cache = null; c.tela.desenhar(); return 1;"); aba.drenar(0.5)
    cor = js("""const e = [...c.doc.entidades.values()].find(e => e.tipo === 'imagem');
      const t = c.tela.paraTela([e.posicao[0] + e.largura / 2, e.posicao[1] + e.altura / 2]), dpr = window.devicePixelRatio || 1;
      return [...c.el.canvas.getContext('2d').getImageData(Math.round(t[0] * dpr), Math.round(t[1] * dpr), 1, 1).data];""")
    ok(cor and cor[2] > 150 and cor[0] < 100, f"o azul do render no meio da imagem, no canvas ({cor})")

    print("B — a largura no papel")
    js(f"c.selecionar([{json.dumps(im.get('id'))}]); return 1;"); aba.drenar(0.5)
    ok(js("return [...document.querySelectorAll('label')].some(l => l.textContent === 'Largura no papel (mm)');"), "o painel da imagem")
    js("""const l = [...document.querySelectorAll('label')].find(l => l.textContent === 'Largura no papel (mm)');
      const i = l.nextElementSibling; i.value = '100'; i.dispatchEvent(new Event('change')); return 1;""")
    aba.drenar(0.5)
    im = imagem() or {}
    ok(abs(im.get("largura", 0) - 100) < 0.01 and abs(im.get("altura", 0) - 56.25) < 0.01, f"100 mm, sem distorcer ({im.get('largura')} × {im.get('altura')})")
    js("c.desfazer ? c.desfazer() : c.pilha.desfazer(); return 1;"); aba.drenar(0.4)
    ok(abs((imagem() or {}).get("largura", 0) - 250) < 0.01, "Ctrl+Z volta a 250 mm")

    print("C — Fixa")
    js(f"c.selecionar([{json.dumps(im.get('id'))}]); return 1;"); aba.drenar(0.5)
    js("""const s = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.value === 'fixa'));
      s.value = 'fixa'; s.dispatchEvent(new Event('change')); return 1;""")
    ok(esperar("(() => { const e = [...c.doc.entidades.values()].find(e => e.tipo === 'imagem'); return e && e.viva === false && !!e.arquivo; })()", 15),
       "a imagem fica fixa")
    arq = (imagem() or {}).get("arquivo", "")
    ok(arq.startswith("fachada-") and os.path.isfile(os.path.join(OBRA, "cenas", "dados", "prancha", arq)), f"a cópia congelada na pasta da obra ({arq})")

    print("D — gravar e o PDF")
    js("return c.salvar({ avisar: false }), 1;")
    aba.drenar(1.5)
    gravado = json.load(open(os.path.join(OBRA, "desenhos-2d", "desenho.desenho.json"), encoding="utf-8"))
    imgs = [e for e in gravado["entidades"] if e["tipo"] == "imagem"]
    ok(len(imgs) == 1 and imgs[0]["viva"] is False and imgs[0]["arquivo"] == arq, "gravada no desenho")
    req = urllib.request.Request(f"http://localhost:{PORTA}/api/projetos/obra/desenhos/desenho/pdf", data=json.dumps({}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    pdfs = [os.path.join(dp, n) for dp, _, ns in os.walk(OBRA) for n in ns if n.lower().endswith(".pdf")]
    ok(bool(pdfs) and b"/Subtype /Image" in open(pdfs[0], "rb").read(), f"o PDF do CAD com a imagem dentro ({[os.path.basename(p) for p in pdfs]})")

    print("E — o menu e o console")
    menu = open(os.path.join(BASE, "web", "barra_unica.js"), encoding="utf-8").read()
    ok("'Inserir cena da obra…', '2d', 'inserir-cena'" in menu, "Desenhos › Pranchas › Inserir cena da obra…")
    erros = [x for x in aba.console if x[0] in ("excecao", "error")]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
