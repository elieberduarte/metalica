# -*- coding: utf-8 -*-
"""Gravar com outra gravação em curso (14/11, achado ao conferir o verif_identificacao_ui para o GESTÃO N.9): no CAD, o
salvar() chamado enquanto o autosave ainda gravava voltava na hora, sem gravar — e quem faz "await salvar()" e depois
pede ao servidor que leia o desenho (Lançar os apoios, Trazer do 3D o que mudou, Gerar o 3D da planta…) recebia o desenho
de antes: o "Lançar os apoios" leu a Implantação sem os 16 pilares recém-lançados, "Nenhum apoio lido". Agora o salvar
espera a gravação em curso e grava de novo.

  A. a gravação do desenho fica lenta (1,5 s, só a resposta trocada); desenha uma linha (L, dois cliques, Esc) e o
     autosave começa a gravar; desenha outra; "await salvar()": quando ele volta, o servidor já tem as duas linhas;
  B. a tela diz "gravado às …" e nada fica para gravar;
  C. a planta ligada ao 3D (estrutura.js embrulha o salvar): cada gravação chama a sincronia do 3D — o
     embrulho pulava a da gravação que chegava com outra em curso, e com o salvar que espera ela não viria mais.

Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_salvar_em_curso.py"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from linha_comando_teste import atalho_na_linha

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_salvar_em_curso_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def no_servidor(slug, nome):
    j = json.load(urllib.request.urlopen(base + urllib.parse.quote(f"/api/projetos/{slug}/desenhos/{nome}"), timeout=30))
    d = j.get("desenho", j)
    ents = d.get("entidades") or []
    return len(ents if isinstance(ents, list) else list(ents.values()))


N0 = 3
TECLAS = {"Enter": 13, "Escape": 27}
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_salvar_em_curso_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Salvar em curso", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/a", {"desenho": {"nome": "A", "escala": 20, "entidades": [
        {"id": f"a{i}", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 1000 * i], "b": [3000, 1000 * i]} for i in range(N0)]}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + f"/cad?projeto={slug}&desenho=a", limite=60)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.1)
        return False

    def clicar_mm(p):
        x, y = js(f"const t = c.tela.paraTela({json.dumps(p)}), r = c.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=0); aba.drenar(0.06)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.15)

    def tecla(k):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 and k.isalpha() else "",
                windowsVirtualKeyCode=code, text=k if len(k) == 1 else "")
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code)
        atalho_na_linha(aba, k)
        aba.drenar(0.1)

    def desenhar_linha(y):
        tecla("l"); clicar_mm([500, y]); clicar_mm([2500, y]); tecla("Escape"); tecla("Escape")

    ok(esperar(f"document.body.dataset.pronto === '1' && c && c.nomeDesenho === 'a' && c.doc.tamanho === {N0}", 60), "o CAD abriu o desenho a")
    js("c.tela.enquadrar([[-1000, -1000], [5000, 5000]]); return 1;")
    aba.drenar(0.3)
    # a gravação do desenho lenta: 1,5 s antes de ir ao servidor
    js("""const o = window.fetch.bind(window); window.__gravacoes = 0;
      window.fetch = async (u, op) => { const t = String(u && u.url || u);
        if (op && op.method === 'POST' && /\\/desenhos\\/a$/.test(t)) { window.__gravacoes++; await new Promise(r => setTimeout(r, 1500)); }
        return o(u, op); };
      return 1;""")
    # a sincronia do 3D espionada (só conta; a de verdade segue)
    js("const o = c._sincronizar3D.bind(c); window.__sinc = 0; c._sincronizar3D = (...a) => { window.__sinc++; return o(...a); }; return 1;")

    # ------------------------------------------------------------------ A. salvar com a gravação do autosave em curso
    desenhar_linha(3500)
    js("c.salvar({ avisar: false }); return 1;")          # o autosave: começa a gravar e fica 1,5 s no caminho
    ok(esperar("c._salvando", 3), "A. a primeira gravação está em curso")
    desenhar_linha(4200)
    ok(js("return c.doc.tamanho;") == N0 + 2, f"A. duas linhas novas na tela ({js('return c.doc.tamanho;')})")
    js("window.__voltou = false; c.salvar({ avisar: false }).then(() => window.__voltou = true); return 1;")
    ok(esperar("window.__voltou", 15), "A. o await salvar() voltou")
    n = no_servidor(slug, "a")
    ok(n == N0 + 2, f"A. quando o await salvar() volta, o servidor tem as duas linhas ({n}; antes voltava na hora, com {N0} ou {N0 + 1})")

    # ------------------------------------------------------------------ B. o estado da tela
    ok(esperar("!c._salvando && /gravado às/.test(c.el.estadoSalvo.textContent)", 10), f"B. a tela diz \"gravado às …\" ({js('return c.el.estadoSalvo.textContent;')})")
    ok(js("return !c._editado;"), "B. nada ficou para gravar")

    # ------------------------------------------------------------------ C. a sincronia do 3D nas duas gravações
    g, sc = js("return window.__gravacoes;"), js("return window.__sinc;")
    ok(g >= 2 and sc == g, f"C. uma sincronia do 3D por gravação, também a que esperou a outra ({g} gravações, {sc} sincronias; antes faltava a dela)")
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
