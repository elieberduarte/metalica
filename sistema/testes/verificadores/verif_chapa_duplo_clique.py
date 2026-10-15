# -*- coding: utf-8 -*-
"""Dois cliques na chapa abrem a tela de edição dela no 2D (pedido do usuário, 15/10/2026), com o mouse de verdade:
  1. Shift + dois cliques continua selecionando as semelhantes (sem sair do 3D);
  2. dois cliques na chapa desenhada à mão (sem marca de posição): ela recebe a marca, o modelo é gravado e o CAD abre
     no ambiente de edição dela (a faixa EDITANDO P…);
  3. Cancelar volta ao 3D;
  4. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Chapa, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_dc_")
PASTA = os.path.join(DADOS, "dc")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Duplo clique", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
doc.add(Barra(nome="viga", inicio=(0, 0, 0), fim=(3000, 0, 0), perfil="W 310×38,7", papel="viga"))
ch = Chapa(nome="CH 200×160×9,5", origem=(3000, -100, -80), eixo_x=(0, 1, 0), eixo_y=(0, 0, 1),
           contorno=[(0, 0), (200, 0), (200, 160), (0, 160)], espessura=9.5, centrada=False, camada="Chapas")
doc.add(ch)
ch2 = Chapa(nome="CH igual", origem=(0, -100, -80), eixo_x=(0, 1, 0), eixo_y=(0, 0, 1),
            contorno=[(0, 0), (200, 0), (200, 160), (0, 160)], espessura=9.5, centrada=False, camada="Chapas")
doc.add(ch2)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_dc_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=dc", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 3)"):
        aba.drenar(0.5)
    aba.drenar(1.5)
    aba.console.clear()

    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(0.3)
        return False

    def tela_da_chapa():
        """o centro da chapa na tela, com a câmera assentada (o enquadrar repetido até parar)"""
        for _ in range(4):
            aba.avaliar(f"editor.camera.zoomSelecao(['{ch.id}']); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); 1")
            aba.drenar(0.6)
        return json.loads(aba.avaliar(f"""JSON.stringify((() => {{
            const V = editor.camera.ativa.position.constructor; const p = new V((3000 + 4.75) * 0.001, 0, 0).project(editor.camera.ativa);
            const r = editor.el.canvas ? editor.el.canvas.getBoundingClientRect() : document.querySelector('canvas').getBoundingClientRect();
            return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }})())"""))

    def duplo(x, y, mod=0):
        for n in (1, 2):
            aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=n, modifiers=mod)
            aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=n, modifiers=mod)
        aba.drenar(0.8)

    x, y = tela_da_chapa()
    # 1) Shift + dois cliques: as semelhantes, sem sair do 3D
    duplo(x, y, mod=8)
    sel = aba.avaliar("editor.selecao.ids.size")
    ok(sel == 2 and "/editor" in aba.avaliar("location.pathname"), f"Shift + dois cliques seleciona as 2 chapas iguais e fica no 3D ({sel})")
    aba.avaliar("editor.selecao.definir([]); 1")
    aba.console.clear()
    # 2) dois cliques: marca, grava e abre o CAD na edição da chapa
    duplo(x, y)
    ok(esperar("location.pathname === '/cad'", 40), f"dois cliques abriram o CAD ({aba.avaliar('location.href')})")
    ok(esperar("document.body.dataset.pronto === '1' && !!document.querySelector('.faixa-edicao')", 60), "o CAD abriu no ambiente de edição")
    faixa = aba.avaliar("(document.querySelector('.faixa-edicao') || {}).textContent || ''") or ""
    ok("EDITANDO" in faixa and "P" in faixa and "isolada" in faixa, f"a faixa da edição: {faixa[:80]!r}")
    salvo = json.load(open(os.path.join(PASTA, "modelo.json"), encoding="utf-8"))
    m = next((e.get("atributos") or {}).get("marcas") or {} for e in salvo["entidades"] if e["id"] == ch.id)
    ok(bool(m.get("posicao")), f"a chapa recebeu a marca e o modelo foi gravado: {m.get('posicao')}")
    # 3) Cancelar volta ao 3D
    aba.avaliar("window.cad._editado = false; window.cad.cancelarEdicaoChapa(); 1")
    ok(esperar("location.pathname === '/editor'", 40), "Cancelar voltou ao 3D")
    erros = [e for e in aba.console if e[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + (": %s" % [x[1][:160] for x in erros[:3]] if erros else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
