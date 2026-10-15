# -*- coding: utf-8 -*-
"""Menu do botão direito (14/10/2026), com o mouse de verdade (CDP): o clique direito sem arrastar abre o menu no
cursor e seleciona a peça; arrastado não abre (é o pan); "Ocultar" tira a peça só da vista (o modelo continua com ela
visível); no vazio, "Mostrar ocultas" traz de volta; Esc fecha."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_menu_")
PASTA = os.path.join(DADOS, "mc")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Menu", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-14T00:00:00", "alterado": "2026-10-14T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
json.dump(Documento().dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_menu_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=mc", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('linha'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    def mouse(tipo, x, y, botao="right", n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, clickCount=n, buttons=2 if botao == "right" and tipo != "mouseReleased" else 0)

    pos = json.loads(aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento;
      const v = doc.add({ tipo: 'barra', nome: 'viga', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [4000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      for (let i = 0; i < 40 && !ed.cena.objetos.has(v.id); i++) await new Promise(r => setTimeout(r, 100));
      ed.camera.enquadrar([[-500, -2500, -500], [4500, 2500, 800]]); ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 400));
      const t = ed.camera.paraTela([2000, 0, 125]), r = ed.el.canvas.getBoundingClientRect();
      // um ponto do 3D sem nada em cima (nem barra sobreposta, nem peça)
      let vx = null, vy = null;
      for (let fy = 0.15; fy < 0.9 && vx === null; fy += 0.05) for (let fx = 0.1; fx < 0.9; fx += 0.05) {
        const px = r.left + r.width * fx, py = r.top + r.height * fy;
        if (document.elementFromPoint(px, py) === ed.el.canvas && !ed.selecao.sob(px - r.left, py - r.top)) { vx = px; vy = py; break; }
      }
      return JSON.stringify({ id: v.id, x: r.left + t[0], y: r.top + t[1], vx, vy }); })()"""))
    x, y = round(pos["x"]), round(pos["y"])
    # arrastado com o direito: é o pan, sem menu
    mouse("mousePressed", x, y); mouse("mouseMoved", x + 40, y + 10); mouse("mouseReleased", x + 40, y + 10)
    aba.drenar(0.3)
    arrastado = aba.avaliar("!!document.querySelector('.menu-contexto')")
    # clique direito parado na viga
    mouse("mousePressed", x, y); mouse("mouseReleased", x, y)
    aba.drenar(0.3)
    r = json.loads(aba.avaliar("""JSON.stringify({ aberto: !!document.querySelector('.menu-contexto'),
      itens: [...document.querySelectorAll('.menu-contexto button span')].map(s => s.textContent),
      sel: [...editor.selecao.ids] })"""))
    print("     ", arrastado, r)
    ok(not arrastado, "o direito arrastado (pan) não abre o menu")
    ok(r["aberto"] and r["sel"] == [pos["id"]] and "Ocultar" in r["itens"] and "Virar perfil" in r["itens"] and "Mover" in r["itens"],
       f"o clique direito na viga abre o menu e a seleciona: {r}")
    # Ocultar
    r = json.loads(aba.avaliar("""(() => { const b = [...document.querySelectorAll('.menu-contexto button')].find(b => b.textContent.startsWith('Ocultar')); b.click();
      const doc = editor.documento, e = doc.get('%s');
      return JSON.stringify({ fechado: !document.querySelector('.menu-contexto'), aparece: doc.aparece(e), visivel: e.visivel !== false,
                              gravado: JSON.stringify(doc.dict ? doc.dict() : {}).includes('"visivel":false') }); })()""" % pos["id"]))
    ok(r["fechado"] and not r["aparece"] and r["visivel"] and not r["gravado"], f"Ocultar tira a viga só da vista (o modelo continua com ela visível): {r}")
    # no vazio: Mostrar ocultas
    mouse("mousePressed", round(pos["vx"]), round(pos["vy"])); mouse("mouseReleased", round(pos["vx"]), round(pos["vy"]))
    aba.drenar(0.3)
    r = json.loads(aba.avaliar("""(() => { const bs = [...document.querySelectorAll('.menu-contexto button')]; const t = bs.map(b => b.textContent);
      const m = bs.find(b => b.textContent.startsWith('Mostrar ocultas')); if (m) m.click();
      return JSON.stringify({ t, aparece: editor.documento.aparece(editor.documento.get('%s')) }); })()""" % pos["id"]))
    ok(any(t.startswith("Mostrar ocultas (1)") for t in r["t"]) and r["aparece"], f"no vazio, 'Mostrar ocultas (1)' traz a viga de volta: {r}")
    # Esc fecha
    mouse("mousePressed", x, y); mouse("mouseReleased", x, y); aba.drenar(0.2)
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.drenar(0.2)
    ok(not aba.avaliar("!!document.querySelector('.menu-contexto')"), "Esc fecha o menu")
    # teclado: Alt+H oculta a seleção, Alt+Shift+H mostra, Alt+I isola (na ferramenta Selecionar)
    def tecla(k, mods):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), modifiers=mods)
        aba.drenar(0.2)
    aba.avaliar(f"editor.ativarFerramenta('selecionar'); editor.selecao.definir(['{pos['id']}'])")
    tecla("h", 1)
    oc = aba.avaliar(f"!editor.documento.aparece(editor.documento.get('{pos['id']}'))")
    tecla("H", 1 | 8)
    volta = aba.avaliar(f"editor.documento.aparece(editor.documento.get('{pos['id']}'))")
    aba.avaliar(f"editor.selecao.definir(['{pos['id']}'])")
    tecla("i", 1); iso = aba.avaliar("!!editor._isolamento")
    tecla("i", 1); saiu = aba.avaliar("!editor._isolamento")
    ok(oc and volta, f"Alt+H oculta a seleção e Alt+Shift+H mostra de volta: {(oc, volta)}")
    ok(iso and saiu, f"Alt+I isola a seleção e de novo volta ao modelo: {(iso, saiu)}")
    # a chapa: "Editar chapa no 2D" (a tela auxiliar, 15/10) e "Alças da chapa no 3D", que abre a ferramenta já nela
    r = json.loads(aba.avaliar("""(async () => { const mc = await import('/editor3d/modulos/menu_contexto.js'); const ed = editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [0, 3000, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 200], [0, 200]], espessura: 10, centrada: true, furos: [], atributos: {} });
      ed.selecao.definir([ch.id]);
      const itens = mc.itensDoMenu(ed, -1000, -1000).filter(i => i && i.rotulo);
      const no2d = itens.map(i => i.rotulo).filter(r => r.startsWith('Editar chapa no 2D'));
      const it = itens.find(i => i.rotulo.startsWith('Alças da chapa'));
      if (it) it.fazer();
      return JSON.stringify({ tem: !!it, no2d, ativa: ed.idAtiva, chapa: !!ed.ativa && ed.ativa.chapa === ch.id }); })()"""))
    ok(r["no2d"] == ["Editar chapa no 2D", "Editar chapa no 2D, no local"], f"na chapa, o menu oferece a edição no 2D: {r['no2d']}")
    ok(r["tem"] and r["ativa"] == "editar_chapa" and r["chapa"], f"na chapa, 'Alças da chapa no 3D' abre a ferramenta já nela: {r}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
