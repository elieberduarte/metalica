# -*- coding: utf-8 -*-
"""Editor 3D: Barras e perfis do bloco (12/10) — o clique na treliça abre o painel do bloco, "Barras e perfis…" desenha a
elevação, "Banzo de cima" escolhe as barras dele, "Virar a boca" vale em todas as cópias do tipo (também na espelhada),
trocar o perfil "só nesta" muda só ela, as presilhas não mudam e o Ctrl+Z desfaz."""
import base64, copy, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_barras_bloco_")
os.makedirs(os.path.join(DADOS, "compressores"))
_m = json.load(open(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), encoding="utf-8"))


def tesoura(k, y, espelho):
    """uma treliça de 6 m × 1 m em x, no plano y: banzos em U, montantes e diagonais em 2L com presilhas"""
    X = (lambda x: 6000.0 - x) if espelho else (lambda x: x)
    org = {"planta": "TESOURA 9", "peca": "TESOURA 9#%d" % k}
    out = []
    def barra(i, a, b, perfil, papel, rot=0.0, dy=0.0):
        out.append({"id": "t%d-%s" % (k, i), "tipo": "barra", "nome": perfil, "camada": "Treliças", "perfil": perfil, "papel": papel,
                    "rotacao": rot, "inicio": [X(a[0]), y + dy, 20000.0 + a[1]], "fim": [X(b[0]), y + dy, 20000.0 + b[1]],
                    "atributos": {"origem": dict(org)}})
    barra("bs", (0, 1000), (6000, 1000), 'U 100×40×2,25 (FF)', "banzo", 270.0)
    barra("bi", (0, 0), (6000, 0), 'U 100×40×2,25 (FF)', "banzo", 90.0)
    for j, x in enumerate((0, 2000, 4000, 6000)):
        for lado, dy in (("a", -16.0), ("b", 16.0)):
            barra("m%d%s" % (j, lado), (x, 0), (x, 1000), 'L 1"×1/8"', "montante", 0.0, dy)
    for j, (x0, x1) in enumerate(((0, 2000), (2000, 4000), (4000, 6000))):
        for lado, dy in (("a", -16.0), ("b", 16.0)):
            barra("d%d%s" % (j, lado), (x0, 0), (x1, 1000), 'L 1"×1/8"', "diagonal", 0.0, dy)
        barra("p%d" % j, ((x0 + x1) / 2, 500), ((x0 + x1) / 2, 500.1), 'L 1"×1/8"', "presilha")
    return out


_novas = tesoura(1, -40000.0, False) + tesoura(2, -46000.0, True)
if isinstance(_m["entidades"], dict):
    for e in _novas:
        _m["entidades"][e["id"]] = e
else:
    _m["entidades"].extend(_novas)
json.dump(_m, open(os.path.join(DADOS, "compressores", "modelo.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_barras_bloco_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ROT = "JSON.stringify(Object.fromEntries(['t1-bs','t2-bs','t1-bi','t2-bi','t1-m0a','t2-m0a','t1-p0'].map(i => [i, window.editor.documento.get(i).rotacao])))"
PERF = "JSON.stringify(Object.fromEntries(['t1-d0a','t1-d0b','t2-d0a','t1-p0','t1-m1a'].map(i => [i, window.editor.documento.get(i).perfil])))"
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("window.editor && window.editor.documento && !!window.editor.documento.get('t1-bs')"): aba.drenar(0.5)
    # o clique na treliça pega o bloco inteiro e abre o painel dele, com o botão novo
    aba.avaliar("window.editor.selecao.definir(window.editor.blocoDe('t1-bs')); 1")
    aba.drenar(0.6)
    ok(aba.avaliar("!!document.querySelector('.painel-bloco .bloco-barras')"), "o painel do bloco tem \"Barras e perfis…\"")
    aba.avaliar("document.querySelector('.painel-bloco .bloco-barras').click(); 1")
    aba.drenar(0.6)
    n_pos = aba.avaliar("document.querySelectorAll('.painel-barras .barras-elevacao .barra:not(.solido)').length")
    ok(n_pos == 9, f"a elevação desenha 9 posições (2 banzos, 4 montantes e 3 diagonais em par; presilhas fora): {n_pos}")
    ok(aba.avaliar("document.querySelectorAll('.painel-barras .barras-legenda .perfil').length") == 2,
       "a legenda tem os 2 perfis do bloco")
    # banzo de cima, em todas as TESOURA 9: a espelhada também vira
    antes = json.loads(aba.avaliar(ROT))
    aba.avaliar("[...document.querySelectorAll('.painel-barras .barras-funcoes button')].find(b => b.textContent === 'Banzo de cima').click(); 1")
    aba.drenar(0.3)
    ok(aba.avaliar("window.editor._barrasBloco.escolha.size") == 1, "\"Banzo de cima\" escolhe 1 posição")
    aba.avaliar("[...document.querySelectorAll('.painel-barras .barras-acoes button')].find(b => b.textContent.startsWith('Virar a boca')).click(); 1")
    aba.drenar(0.5)
    depois = json.loads(aba.avaliar(ROT))
    ok(depois["t1-bs"] == 90 and depois["t2-bs"] == 90, f"a boca do banzo de cima virou nas duas cópias (a 2ª espelhada): {depois}")
    ok(depois["t1-bi"] == antes["t1-bi"] and depois["t2-bi"] == antes["t2-bi"] and depois["t1-m0a"] == antes["t1-m0a"],
       "o banzo de baixo e a alma não mudaram")
    # Ctrl+Z desfaz as duas de uma vez
    aba.avaliar("window.editor.desfazer(); 1")
    aba.drenar(0.4)
    ok(json.loads(aba.avaliar(ROT)) == antes, "um Ctrl+Z desfaz a mudança nas duas cópias")
    # diagonais, perfil novo só nesta: as duas L do par mudam, a outra cópia e as presilhas não
    aba.avaliar("[...document.querySelectorAll('.painel-barras .barras-funcoes button')].find(b => b.textContent === 'Diagonais').click(); 1")
    aba.drenar(0.3)
    aba.avaliar("const s = document.querySelector('.painel-barras .barras-acoes select'); s.value = 'esta'; s.dispatchEvent(new Event('change')); 1")
    aba.avaliar("window.editor._aplicarNasBarras(window.editor._barrasBloco.dados.posicoes.filter(p => p.funcao === 'diagonal'), e => ({ perfil: 'L 1.1/2\"×1/8\"' }), 'Perfil'); 1")
    aba.drenar(0.4)
    pf = json.loads(aba.avaliar(PERF))
    ok(pf["t1-d0a"] == pf["t1-d0b"] == 'L 1.1/2"×1/8"', f"as duas cantoneiras da diagonal trocaram de perfil: {pf}")
    ok(pf["t2-d0a"] == 'L 1"×1/8"' and pf["t1-p0"] == 'L 1"×1/8"' and pf["t1-m1a"] == 'L 1"×1/8"',
       "\"só nesta\": a outra cópia, as presilhas e os montantes ficaram")
    foto(aba, "barras_bloco.png")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
