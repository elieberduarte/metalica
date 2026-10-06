# -*- coding: utf-8 -*-
"""A ferramenta Encaixar ponta do editor 3D (web/editor3d/ferramentas/encaixar.js; pedido de 30/09/2026: "uma
ferramenta para, nos que passam pelo filtro, eu poder ajustar manualmente"). Confere: o botão está na coluna do
editor e na faixa da área de trabalho; clicar na barra e na face do banzo corta (ou estica) a ponta mais perto no
plano da face (a malha do editor deita nela); Shift + outra face soma o plano (o bico, com a peça fora do montante);
Del tira os cortes; Ctrl+Z volta; o modelo gravado leva os cortes."""
import json, os, shutil, subprocess, sys, tempfile, time, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_encaixar_")
PASTA = os.path.join(DADOS, "encx")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Encaixar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-30T00:00:00", "alterado": "2026-09-30T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
BZ = "U 100×40×2,25 (FF)"
banzo = Barra(nome="banzo", inicio=(0.0, 0.0, 0.0), fim=(4000.0, 0.0, 0.0), perfil=BZ, rotacao=90.0, papel="banzo")
mont = Barra(nome="montante", inicio=(1000.0, 0.0, 30.1), fim=(1000.0, 0.0, 1500.0), perfil=BZ, rotacao=90.0, papel="montante")
# a diagonal que o desenho deixou curta: começa 200 mm acima do banzo
diag = Barra(nome="diagonal", inicio=(1200.0, 0.0, 200.0), fim=(2500.0, 0.0, 1500.0), perfil=BZ, rotacao=90.0, papel="diagonal")
# o tubo quadrado do catálogo completo: no modo leve o editor monta a seção sozinho (portaria, 30/09: voltou redondo)
tubo = Barra(nome="forro", inicio=(0.0, 800.0, 0.0), fim=(4000.0, 800.0, 0.0), perfil="TQ 40×40×1,5", papel="barra")
for e in (banzo, mont, diag, tubo):
    doc.add(e)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_encx_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# a malha que o editor desenha para a barra, no mundo: [min x, min z]
MALHA = """(() => { const b = editor.documento.get('%s'); const r = editor.cena._geometriaBarra(b);
  const p = r.geom.getAttribute('position'); const v = new r.matriz.constructor(); let mx = 1e9, mz = 1e9, Mz = -1e9;
  const q = { x: 0, y: 0, z: 0 };
  for (let i = 0; i < p.count; i++) { const e = r.matriz.elements, x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const wx = e[0]*x + e[4]*y + e[8]*z + e[12], wz = e[2]*x + e[6]*y + e[10]*z + e[14];
    mx = Math.min(mx, wx); mz = Math.min(mz, wz); }
  return [mx, mz]; })()"""
# o clique da ferramenta com o alvo dado (a face sob o cursor)
CLIQUE = """(() => { const f = editor.ativa; f._sob = () => (%s); f.onPonto({ tela: [0, 0] }, { shiftKey: %s }); return 1; })()"""

try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/editor?projeto=encx", limite=60)
    t0 = time.time()
    # os perfis dobrados (o U FF, o TQ) chegam depois do banco básico (acrescentarPerfis): antes disso a barra tem a
    # seção provisória 100×200 e a malha medida não é a da peça (a falha intermitente da conferência de 03/10)
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 4 && editor.ferramentas && editor.ferramentas.get('encaixar')"
                                                    " && editor.cena.perfil(%s) && editor.cena.perfil('TQ 40×40×1,5'))" % json.dumps(BZ)):
        aba.drenar(0.5)
    aba.drenar(1.0)
    ok(aba.avaliar("!!document.querySelector('#barra-ferramentas [data-id=\"encaixar\"]')"), "o botão Encaixar ponta está na coluna do editor")

    tq = aba.avaliar("""(() => { const f = editor.cena._secaoDoPerfil('TQ 40×40×1,5'); const e = f.extractPoints(8);
      const xs = e.shape.map(q => q.x), ys = e.shape.map(q => q.y);
      return [e.holes.length, Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), e.shape.length]; })()""")
    ok(tq and tq[0] == 1 and abs(tq[1] - 40) < 0.5 and abs(tq[2] - 40) < 0.5 and tq[3] > 8,
       "o TQ 40×40 sai quadrado e oco na seção do próprio editor (modo leve): %s" % (tq,))
    aba.avaliar("editor.ativarFerramenta('encaixar'); 1"); aba.drenar(0.3)
    ok(aba.avaliar("editor.idAtiva") == "encaixar", "a ferramenta liga")
    antes = aba.avaliar(MALHA % diag.id)
    # 1: a diagonal; 2: a face de cima das abas do banzo (z = 30,1)
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [1800, 0, 800], normal: [0.7, 0, -0.7] }" % diag.id, "false"))
    ok(aba.avaliar("editor.selecao.ids.has('%s')" % diag.id), "o primeiro clique escolhe a barra")
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [1500, 0, 30.1], normal: [0, 0, 1] }" % banzo.id, "false"))
    b = aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % diag.id)
    b = json.loads(b)
    ok(len(b.get("cortes_inicio") or []) == 1 and not b.get("cortes_fim"), "a ponta de baixo (a mais perto da face) ganhou o corte")
    depois = aba.avaliar(MALHA % diag.id)
    ok(abs(depois[1] - 30.1) < 0.5 and antes[1] > 100, "a diagonal curta foi esticada até deitar na face do banzo (z mín. %.1f → %.1f)" % (antes[1], depois[1]))
    # 3: de novo na diagonal, Shift + a face do montante (x = 1000 + 30,1: a face para o lado da diagonal)
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [1800, 0, 800], normal: [0.7, 0, -0.7] }" % diag.id, "false"))
    face_m = aba.avaliar("""(() => { const b = editor.documento.get('%s'); const r = editor.cena._geometriaBarra(b);
      const p = r.geom.getAttribute('position'); const e = r.matriz.elements; let M = -1e9;
      for (let i = 0; i < p.count; i++) { const x = p.getX(i), y = p.getY(i), z = p.getZ(i); M = Math.max(M, e[0]*x + e[4]*y + e[8]*z + e[12]); }
      return M; })()""" % mont.id)
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [%s, 0, 300], normal: [1, 0, 0] }" % (mont.id, face_m), "true"))
    b = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % diag.id))
    ok(len(b.get("cortes_inicio") or []) == 2, "Shift + a face do montante soma o plano (o bico)")
    bico = aba.avaliar(MALHA % diag.id)
    ok(bico[0] >= face_m - 0.5 and abs(bico[1] - 30.1) < 0.5, "com o bico a diagonal não entra no montante (x mín. %.1f, face %.1f)" % (bico[0], face_m))
    # Del tira os cortes; Ctrl+Z volta
    aba.avaliar("editor.ativa.onTecla({ key: 'Delete' }); 1"); aba.drenar(0.3)
    b = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % diag.id))
    ok(not b.get("cortes_inicio") and not b.get("cortes_fim"), "Del tira os cortes das pontas")
    aba.avaliar("editor.desfazer(); 1"); aba.drenar(0.3)
    b = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % diag.id))
    ok(len(b.get("cortes_inicio") or []) == 2, "Ctrl+Z devolve os dois planos")
    # a face ao longo da barra não corta ponta nenhuma
    aba.avaliar("editor.ativa.cancelar(); 1")
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [1800, 0, 800], normal: [0.7, 0, -0.7] }" % diag.id, "false"))
    aba.avaliar(CLIQUE % ("{ id: '%s', ponto: [1800, 0, 800], normal: [0.7071, 0, -0.7071] }" % banzo.id, "false"))
    ok("corre ao longo" in (aba.avaliar("document.querySelector('#dica') ? document.querySelector('#dica').textContent : editor.el.dica.textContent") or ""),
       "a face paralela à barra é recusada com o motivo")
    # Virar perfil (V): o giro da seção no próprio eixo, como o Girar do SketchUp preso ao eixo da peça
    aba.avaliar("editor.ativa.cancelar(); editor.selecao.limpar(); editor.ativarFerramenta('virar'); 1"); aba.drenar(0.3)
    ok(aba.avaliar("editor.idAtiva") == "virar", "a ferramenta Virar perfil liga (atalho V)")
    ROT = "editor.documento.get('%s').rotacao"
    VIRA = """(() => { const f = editor.ativa; f.editor.selecao.sob = () => ({ id: '%s', ponto: [2000, 800, 0], normal: [0, 0, 1] });
      f.onPonto({ tela: [1, 1] }, { shiftKey: %s, ctrlKey: %s }); return 1; })()"""
    aba.avaliar("window._sob = editor.selecao.sob.bind(editor.selecao); 1")
    aba.avaliar(VIRA % (tubo.id, "false", "false"))
    r1 = aba.avaliar(ROT % tubo.id)
    aba.avaliar(VIRA % (tubo.id, "true", "false"))
    r2 = aba.avaliar(ROT % tubo.id)
    aba.avaliar(VIRA % (tubo.id, "false", "true"))
    r3 = aba.avaliar(ROT % tubo.id)
    ok((r1, r2, r3) == (90, 0, 180), "clique gira 90°, Shift volta, Ctrl vira 180° (%s, %s, %s)" % (r1, r2, r3))
    prev = aba.avaliar("""(() => { const f = editor.ativa; f.editor.selecao.sob = () => ({ id: '%s', ponto: [2000, 800, 0], normal: [0, 0, 1] });
      let n = 0; const orig = editor.previa.bind(editor); editor.previa = (o) => { o.traverse(x => { if (x.isLine) n++; }); return orig(o); };
      f.onMover({ tela: [1, 1] }, {}); editor.previa = orig; return n; })()""" % tubo.id)
    ok(prev == 2, "passando o mouse, a prévia mostra a seção de agora e a virada (%s contornos)" % prev)
    aba.avaliar("editor.ativa.onValor('45'); 1")
    aba.avaliar(VIRA % (tubo.id, "false", "false"))
    ok(aba.avaliar(ROT % tubo.id) == 225, "o ângulo digitado vira o passo (180 + 45 = %s)" % aba.avaliar(ROT % tubo.id))
    aba.avaliar("editor.selecao.sob = window._sob; editor.selecao.definir(['%s', '%s']); editor.ativarFerramenta('virar'); editor.ativa.onValor('90'); 1" % (tubo.id, mont.id))
    antes_m = aba.avaliar(ROT % mont.id)
    aba.avaliar(VIRA % (tubo.id, "false", "false"))
    ok(aba.avaliar(ROT % mont.id) == (antes_m + 90) % 360 and aba.avaliar(ROT % tubo.id) == 315,
       "com duas barras selecionadas o clique vira as duas")
    aba.avaliar("editor.desfazer(); 1"); aba.drenar(0.2)
    ok(aba.avaliar(ROT % mont.id) == antes_m and aba.avaliar(ROT % tubo.id) == 225, "Ctrl+Z desfaz as duas de uma vez")
    aba.avaliar("editor.selecao.sob = window._sob; editor.ativarFerramenta('selecionar'); 1")
    # Empurrar/Puxar na barra (pedido de 30/09: "a função puxar não está funcionando... clicar na face do perfil para
    # estender"): a ponta apontada anda no eixo, a outra fica
    aba.avaliar("editor.ativarFerramenta('pushpull'); 1")
    antes_t = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % tubo.id))
    aba.avaliar("""(() => { const f = editor.ativa; f.iniciar({ entidade: '%s', ponto: [3990, 800, 0], tela: [1, 1] }, {}); f.aplicar(150); return 1; })()""" % tubo.id)
    dep_t = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % tubo.id))
    ok(abs(dep_t["fim"][0] - (antes_t["fim"][0] + 150)) < 0.1 and dep_t["inicio"] == antes_t["inicio"],
       "Puxar na ponta da barra estica 150 no eixo, a outra ponta parada (%s → %s)" % (antes_t["fim"][0], dep_t["fim"][0]))
    aba.avaliar("""(() => { const f = editor.ativa; f.iniciar({ entidade: '%s', ponto: [300, 820, 5], tela: [1, 1] }, {}); f.aplicar(-100); return 1; })()""" % tubo.id)
    dep2 = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % tubo.id))
    ok(abs(dep2["inicio"][0] - (antes_t["inicio"][0] + 100)) < 0.1, "o clique na lateral perto do início encurta pelo início (%s)" % dep2["inicio"][0])
    aba.avaliar("editor.desfazer(); editor.desfazer(); 1"); aba.drenar(0.2)
    dep3 = json.loads(aba.avaliar("JSON.stringify(editor.documento.get('%s'))" % tubo.id))
    ok(dep3["inicio"] == antes_t["inicio"] and dep3["fim"] == antes_t["fim"], "Ctrl+Z volta a barra")
    aba.avaliar("editor.ativarFerramenta('selecionar'); 1")
    aba.avaliar("editor.ativarFerramenta('encaixar'); 1")
    # grava e confere no disco
    aba.avaliar("editor.ativa.cancelar(); editor.ativarFerramenta('selecionar'); 1")
    aba.avaliar("(async () => { await editor.salvar(); return 1; })()"); aba.drenar(1.5)
    salvo = json.load(open(os.path.join(PASTA, "modelo.json"), encoding="utf-8"))
    d = next(e for e in salvo["entidades"] if e["id"] == diag.id)
    ok(len(d.get("cortes_inicio") or []) == 2, "o modelo gravado leva os cortes")
    aba.avaliar("editor.camera.vista('frente', editor.documento.caixa()); 1"); aba.drenar(2.5)
    open(os.path.join(os.path.dirname(__file__), "_encaixar.png"), "wb").write(
        base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    # a faixa da área de trabalho
    aba.navegar(base + "/dividida?projeto=encx&vista=3d&editar=1", limite=60)      # o editor, não o modo ver
    t0 = time.time()
    while time.time() - t0 < 40 and not aba.avaliar("!!document.querySelector('#faixa-ferramentas .fx-bt[data-chave=\"encaixar\"]')"):
        aba.drenar(0.5)
    ok(aba.avaliar("!!document.querySelector('#faixa-ferramentas .fx-bt[data-chave=\"encaixar\"]')"), "o botão está na faixa da área de trabalho")
    ok(aba.avaliar("!!document.querySelector('#faixa-ferramentas .fx-bt[data-chave=\"virar\"]')"), "o Virar perfil também está na faixa")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + ("" if not erros else ": " + str(erros[:2])))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
