# -*- coding: utf-8 -*-
r"""Editor 3D: Editar → Explodir com critério (usuário, 12/11: "explodir os elementos — não todos peçinha por peçinha, mas com
um critério: o que está junto por um motivo fica junto; a tesoura pode ser UM elemento"; "pode seguir, preciso explodir o
galpão viena").

Um projeto com UM sólido com tudo dentro (como o IFC do SketchUp do Galpão Viena), longe da origem: a treliça de 6 m (2
banzos U, 6 diagonais, 4 presilhas), um pilar PS, um contravento Ø16, uma viga dupla numa malha só e uma chapa
(testes/test_explodir_criterio._modelo). Cliques de verdade no menu:
  A. Explodir com critério → o resumo (1 treliça, as peças) → Desfazer: o modelo volta a ter o sólido só;
  B. de novo → Manter: 17 peças + 1 grupo (a treliça, com as 12 peças dentro), as camadas novas com cor, o clique numa peça da
     treliça pega a treliça inteira (o grupo), os perfis lidos (PS 500×300×8×12,5, Barra redonda Ø16, a viga dupla em 2);
  C. Ctrl+Z: o sólido de volta;
  D. sem erros no console;
  F. pela barra única da área de trabalho (a tela do usuário): Modelo › Explodir com critério… explode no quadro do 3D;
  G. pelo menu do botão direito no sólido (clique direito de verdade);
  E. o Galpão Viena de verdade (C:\Metálica\dados\galpão-viena, quando existe nesta máquina; uma CÓPIA na pasta do teste):
     1.903 pedaços → as treliças e as peças em menos de 60 s, a da frente com as 1.014 presilhas dentro.
Porta livre, nunca a 8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_explodir_criterio import _modelo
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_explodir_criterio_")
V, F = _modelo()
pasta = os.path.join(DADOS, "viena")
os.makedirs(pasta)
json.dump({"nome": "viena", "unidade": "mm", "camadas": {"Layer0": {"nome": "Layer0", "cor": "#8a94a6", "visivel": True, "bloqueada": False}},
           "materiais": {}, "entidades": [{"id": "tudo", "tipo": "solido", "nome": "Galpão Logistico.dxf#1", "camada": "Layer0",
                                          "material": "", "vertices": V, "faces": F, "arestas_vivas": [],
                                          "atributos": {"tipo_ifc": "IfcBuildingElementProxy"}}]},
          open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
VIENA = r"C:\Metálica\dados\galpão-viena\modelo.json"
if os.path.isfile(VIENA):
    os.makedirs(os.path.join(DADOS, "viena-real"))
    shutil.copyfile(VIENA, os.path.join(DADOS, "viena-real", "modelo.json"))
    json.dump({"formato": 1, "nome": "viena-real", "tipo": "ifc", "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00"},
              open(os.path.join(DADOS, "viena-real", "projeto.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "viena", "tipo": "ifc", "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00"},
          open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_explodir_criterio_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=60):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                v = aba.avaliar(expr)
                if v: return v
            except Exception: pass
            aba.drenar(0.3)
        return None

    def clicar(seletor):
        r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return q.width ? [q.left + q.width / 2, q.top + q.height / 2] : null; }})()")
        if not r: return False
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
        aba.drenar(0.3)
        return True

    def explodir_pelo_menu():
        ok(clicar('.menu[data-menu="editar"] .menu-botao'), "abre o menu Editar")
        ok(clicar('[data-acao="explodir-criterio"]'), "clique em Explodir com critério")
        return esperar("(() => { const d = document.querySelector('#dialogo'); return d && d.open && /Explodir com crit/.test(d.textContent) ? d.textContent : null; })()", 60)

    aba.navegar(base + "/editor?projeto=viena", limite=90)
    ok(bool(esperar("!!(window.editor && editor.documento && editor.documento.entidades.size === 1 && document.body.dataset.pronto === '1')", 120)),
       "o editor abriu com o sólido só")
    N = "editor.documento.lista.filter(e => e.tipo === 'solido').length"
    # --- A. Desfazer pelo resumo
    txt = explodir_pelo_menu() or ""
    print("     resumo:", " ".join(txt.split())[:300])
    ok("1 treliça inteira" in txt and "17 pedaços" in txt, "[A] o resumo: 17 pedaços → 1 treliça")
    clicar("#dialogo-cancelar")
    ok(esperar(f"{N} === 1 && editor.documento.lista.every(e => e.tipo !== 'grupo')", 10) is True, "[A] Desfazer: o sólido só de volta")
    # --- B. Manter
    explodir_pelo_menu()
    clicar("#dialogo-ok")
    esperar("!document.querySelector('#dialogo').open", 10)
    r = json.loads(aba.avaliar("""JSON.stringify((() => {
      const L = editor.documento.lista, g = L.filter(e => e.tipo === 'grupo');
      const s = L.filter(e => e.tipo === 'solido');
      const membro = g.length ? g[0].filhos[0] : null;
      const cams = ['Treliças', 'Pilares', 'Vigas', 'Contraventos', 'Chapas'].map(c => [c, (editor.documento.camadas.get(c) || {}).cor || null]);
      return { solidos: s.length, grupos: g.length, filhos: g.length ? g[0].filhos.length : 0, nome: g.length ? g[0].nome : '',
               bloco: membro ? editor.blocoDe(membro).length : 0, nomes: s.map(e => e.nome), cams,
               original: s.some(e => e.id === 'tudo') };
    })())"""))
    print("     depois:", {k: v for k, v in r.items() if k != "nomes"})
    ok(r["solidos"] == 17 and not r["original"], f"[B] 17 peças no lugar do sólido ({r['solidos']})")
    ok(r["grupos"] == 1 and r["filhos"] == 12 and r["nome"].startswith("TR1"), f"[B] a treliça é UM grupo com as 12 peças ({r['grupos']}, {r['filhos']}, {r['nome']})")
    ok(r["bloco"] == 12, f"[B] a peça da treliça pega a treliça inteira ({r['bloco']})")
    ok(all(c for _, c in r["cams"]) and dict(r["cams"])["Treliças"] == "#c0392b", f"[B] as camadas novas com cor ({r['cams']})")
    ok("PS 500×300×8×12,5" in r["nomes"] and "Barra redonda Ø16" in r["nomes"] and r["nomes"].count("PS 400×200×8×12,5") == 2,
       "[B] os perfis lidos: o pilar PS, o contravento Ø16, a viga dupla em dois")
    open(os.path.join(SCR, "explodir_criterio.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    # --- C. Ctrl+Z
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="z", code="KeyZ", windowsVirtualKeyCode=90, modifiers=2)
    ok(esperar(f"{N} === 1 && editor.documento.get('tudo') && editor.documento.lista.every(e => e.tipo !== 'grupo')", 10) is True,
       "[C] Ctrl+Z: o sólido de volta, sem grupo")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"[D] sem erros no console: {erros[:3]}")
    # --- G. o botão direito no sólido (usuário, 12/11: "Pode deixar a opção nesse menu do botão direito")
    aba.avaliar("editor.camera.zoomExtensao(); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); 1")
    aba.drenar(0.8)
    pt = json.loads(aba.avaliar("""JSON.stringify((() => { const r = editor.el.canvas.getBoundingClientRect();
      for (let fy = 0.2; fy < 0.9; fy += 0.02) for (let fx = 0.1; fx < 0.9; fx += 0.01) {
        const x = r.width * fx, y = r.height * fy, s = editor.selecao.sob(x, y);
        if (s && s.id === 'tudo' && document.elementFromPoint(r.left + x, r.top + y) === editor.el.canvas) return [r.left + x, r.top + y];
      } return null; })())"""))
    ok(bool(pt), f"[G] um ponto da tela sobre o sólido ({pt})")
    if pt:
        # como no print do usuário: o sólido selecionado (clique), depois o botão direito nele
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=pt[0], y=pt[1], button="left", clickCount=1)
        aba.drenar(0.4)
        if not aba.avaliar("editor.selecao.ids.has('tudo')"):
            aba.avaliar("editor.selecao.definir(['tudo']); 1")
        for tipo in ("mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=pt[0], y=pt[1], button="right", clickCount=1)
        aba.drenar(0.4)
        itens = aba.avaliar("[...document.querySelectorAll('.menu-contexto button')].map(b => b.textContent).join(' | ')") or ""
        ok("Explodir com critério" in itens, f"[G] o menu do botão direito tem o Explodir com critério ({itens[:160]})")
        aba.avaliar("""(() => { const b = [...document.querySelectorAll('.menu-contexto button')].find(x => /Explodir com crit/.test(x.textContent));
          if (b) b.dataset.verif = 'explodir-ctx'; return 1; })()""")
        clicar('[data-verif="explodir-ctx"]')
        txt = esperar("(() => { const d = document.querySelector('#dialogo'); return d && d.open && /Explodir com crit/.test(d.textContent) ? d.textContent : null; })()", 60) or ""
        ok("1 treliça inteira" in txt, "[G] e o clique explode (o resumo abre)")
        clicar("#dialogo-cancelar")
        ok(esperar(f"{N} === 1", 10) is True, "[G] Desfazer: o sólido de volta")
    # --- F. pela barra única da área de trabalho, a tela que o usuário usa (12/11: "Onde está a ferramenta de explodir?" —
    # o item tinha entrado só no menu Editar do editor, que a barra esconde): Modelo › Explodir com critério…
    esperar("!editor._autosalvando && !editor._autosavePendente", 120)
    aba.navegar(base + "/dividida?projeto=viena", limite=90)
    ok(bool(esperar("!!document.querySelector('.menu[data-nome=\"Modelo\"] .menu-botao')", 30)), "[F] a área de trabalho abriu com a barra única")
    esperar("(() => { const f = document.getElementById('f3d'); const w = f && f.contentWindow; return !!(w && (w.ver3dPronto || (w.editor && w.editor.documento))); })()", 120)
    aba.drenar(1.0)
    item = None
    for _ in range(10):
        clicar('.menu[data-nome="Modelo"] .menu-botao')
        item = esperar("""(() => { const b = [...document.querySelectorAll('.menu[data-nome="Modelo"] .menu-lista button')]
          .find(x => /Explodir com crit/.test(x.textContent)); if (!b) return null; b.dataset.verif = 'explodir'; return b.textContent; })()""", 2)
        if item: break
    ok(bool(item), f"[F] o menu Modelo da barra tem o Explodir com critério ({item!r})")
    clicar('[data-verif="explodir"]')
    DLG = "(() => { const d = document.getElementById('f3d').contentDocument; const g = d && d.querySelector('#dialogo'); return g && g.open && /Explodir com crit/.test(g.textContent) ? g.textContent : null; })()"
    txt = esperar(DLG, 120) or ""
    ok("1 treliça inteira" in txt, "[F] o clique na barra explode no editor do quadro 3D: " + " ".join(txt.split())[:120])
    aba.avaliar("document.getElementById('f3d').contentDocument.querySelector('#dialogo-cancelar').click(); 1")
    ok(esperar("(() => { const w = document.getElementById('f3d').contentWindow; return w.editor.documento.lista.filter(e => e.tipo === 'solido').length === 1; })()", 20) is True,
       "[F] e o Desfazer do resumo volta o sólido")
    esperar("(() => { const w = document.getElementById('f3d').contentWindow; return !w.editor._autosalvando && !w.editor._autosavePendente; })()", 120)
    # --- E. o Galpão Viena de verdade
    if os.path.isdir(os.path.join(DADOS, "viena-real")):
        # sair com a gravação automática em curso dispara o aviso de edição por gravar (beforeunload): espera ela terminar
        esperar("!editor._autosalvando && !editor._autosavePendente", 120)
        aba.navegar(base + "/editor?projeto=viena-real", limite=120)
        ok(bool(esperar("!!(window.editor && editor.documento && editor.documento.entidades.size === 1 && document.body.dataset.pronto === '1')", 180)),
           "[E] o editor abriu o Galpão Viena (1 sólido)")
        t0 = time.time()
        txt = explodir_pelo_menu() or ""
        dt = time.time() - t0
        print("     Viena:", " ".join(txt.split())[:260], f"({dt:.1f} s)")
        ok("1.907 pedaços" in txt and dt < 60, f"[E] 1.907 pedaços (1.903 + as 4 vigas duplas em dois) explodidos em {dt:.1f} s")
        clicar("#dialogo-ok")
        esperar("!document.querySelector('#dialogo').open", 20)
        e = json.loads(aba.avaliar("""JSON.stringify((() => { const L = editor.documento.lista, g = L.filter(x => x.tipo === 'grupo');
          const f = g.reduce((a, b) => (a.filhos.length > b.filhos.length ? a : b), { filhos: [] });
          return { grupos: g.length, maior: f.filhos.length, nomeMaior: f.nome || '', solidos: L.filter(x => x.tipo === 'solido').length }; })())"""))
        print("     Viena depois:", e)
        ok(e["grupos"] >= 11 and e["maior"] == 4 + 253 + 1014 and "135 m" in e["nomeMaior"],
           f"[E] as treliças inteiras; a da frente (135 m) com banzos, alma e as 1.014 presilhas ({e})")
        open(os.path.join(SCR, "explodir_criterio_viena.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
        erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
        ok(not erros, f"[E] sem erros no console: {erros[:3]}")
    else:
        print("  (E pulado: o Galpão Viena não existe nesta máquina)")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
