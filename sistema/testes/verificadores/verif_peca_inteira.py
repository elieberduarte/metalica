# -*- coding: utf-8 -*-
"""CAD: o clique numa linha de peça do detalhamento seleciona a peça inteira (contorno,
abas, linha oculta), para girar ou mover sem deixar resquício; Alt+clique pega só a linha."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8793
DADOS = tempfile.mkdtemp(prefix="metalica_peca_")
os.makedirs(os.path.join(DADOS, "p", "desenhos-2d"))
json.dump({"formato": 1, "nome": "P", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-24T00:00:00", "alterado": "2026-09-24T00:00:00", "dados": None},
          open(os.path.join(DADOS, "p", "projeto.json"), "w", encoding="utf-8"))
# uma diagonal de detalhe: contorno + aba (mesma origem) e, colada, outra peça
atr = {"origem": "d1", "posicao": "P7", "conjunto": "M2", "detalhe": "conjunto"}
ents = [
    {"id": "c1", "tipo": "polilinha", "camada": "DIAGONAIS", "atributos": atr, "vertices": [[0, 0], [1000, 800], [1020, 780], [20, -20]], "fechada": True},
    {"id": "c2", "tipo": "polilinha", "camada": "VISTA-FINA", "atributos": atr, "vertices": [[5, -5], [1005, 795]], "fechada": False},
    {"id": "c3", "tipo": "linha", "camada": "VISTA-FINA", "atributos": atr, "a": [10, -10], "b": [1010, 790]},
    {"id": "o1", "tipo": "linha", "camada": "BANZOS", "atributos": {"origem": "b1", "posicao": "P16", "conjunto": "M2", "detalhe": "conjunto"}, "a": [-500, 0], "b": [2000, 0]},
    {"id": "q1", "tipo": "polilinha", "camada": "AUXILIAR", "atributos": {"quadro": "TESOURAS"}, "vertices": [[-3000, -3000], [5000, -3000], [5000, 5000], [-3000, 5000]], "fechada": True},
    {"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 1500], "b": [500, 1500]},
]
json.dump({"nome": "t", "escala": 25, "entidades": ents, "camadas": {}, "vistas": [], "metadados": {}},
          open(os.path.join(DADOS, "p", "desenhos-2d", "t.desenho.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_peca_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=p&desenho=t", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho > 0"): aba.drenar(0.5)
    ids = aba.avaliar("window.cad.pecaDe('c1').sort().join(',')")
    ok(ids == "c1,c2,c3", f"a diagonal inteira: {ids}")
    ok(aba.avaliar("window.cad.pecaDe('o1').join(',')") == "o1", "o banzo encostado é outra peça")
    ok(aba.avaliar("window.cad.pecaDe('l1').join(',')") == "l1", "linha sem origem é só ela")
    # o clique da ferramenta Selecionar
    aba.avaliar("(() => { const f = window.cad.ferramentas.get('selecionar'); window.cad.tela.sob = () => window.cad.doc.get('c2');"
                " f.onPonto([0, 0], { px: [0, 0], shiftKey: false, ctrlKey: false, altKey: false }); return 1; })()")
    ok(aba.avaliar("[...window.cad.tela.selecao].sort().join(',')") == "c1,c2,c3", "clique seleciona a peça inteira")
    aba.avaliar("(() => { const f = window.cad.ferramentas.get('selecionar');"
                " f.onPonto([0, 0], { px: [0, 0], shiftKey: false, ctrlKey: false, altKey: true }); return 1; })()")
    ok(aba.avaliar("[...window.cad.tela.selecao].join(',')") == "c2", "Alt+clique pega só a linha")
    # seleção por cruzamento dentro do quadro não pega a moldura
    ids = aba.avaliar("(() => { const t = window.cad.tela; const a = t.paraTela([600, 300]), b = t.paraTela([400, 500]);"
                      " return t.naJanela(a, b).sort().join(','); })()")
    ok("q1" not in ids and "c1" in ids, f"cruzamento dentro do quadro sem a moldura: {ids}")
    # Ctrl no Mover e no Girar: cópia, o original fica (como no SketchUp)
    n0 = aba.avaliar("window.cad.doc.tamanho")
    aba.avaliar("(() => { window.cad.selecionar(['c1','c2','c3']); window.cad.ativarFerramenta('mover'); const f = window.cad.ferramenta;"
                " f.onPonto([0, 0], { px: [0, 0] }); f.onPonto([0, 2000], { px: [0, 0], ctrlKey: true }); return 1; })()")
    ok(aba.avaliar("window.cad.doc.tamanho") == n0 + 3, "Mover com Ctrl copia as 3 linhas")
    ok(aba.avaliar("window.cad.doc.get('c1').vertices[0][1]") == 0, "o original não saiu do lugar")
    ok(aba.avaliar("[...window.cad.tela.selecao].every(id => !['c1','c2','c3'].includes(id))"), "a cópia fica selecionada")
    # a cópia é outra peça: clicar no original pega só o original, e vice-versa
    ok(aba.avaliar("window.cad.pecaDe('c1').sort().join(',')") == "c1,c2,c3", "depois de copiar, o original continua sendo só as 3 linhas dele")
    r = aba.avaliar("(() => { const ids = [...window.cad.tela.selecao]; const p = window.cad.pecaDe(ids[0]); return [p.length, p.every(i => ids.includes(i))]; })()")
    ok(r[0] == 3 and r[1], f"a cópia é uma peça só (3 linhas), sem o original: {r}")
    n1 = aba.avaliar("window.cad.doc.tamanho")
    aba.avaliar("(() => { window.cad.selecionar(['c1','c2','c3']); window.cad.ativarFerramenta('girar'); const f = window.cad.ferramenta;"
                " f.onPonto([0, 0], { px: [0, 0] }); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Control' }));"
                " document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Control' })); return 1; })()")
    ok("(cópia)" in aba.avaliar("document.querySelector('#dica, .dica') ? document.querySelector('#dica, .dica').textContent : window.cad.el.dica.textContent"),
       "toque no Ctrl liga a cópia (a dica avisa)")
    aba.avaliar("(() => { const f = window.cad.ferramenta; f.onValor('90'); return 1; })()")
    ok(aba.avaliar("window.cad.doc.tamanho") == n1 + 3, "Girar em modo cópia deixa o original e cria a girada")
    ok(aba.avaliar("window.cad.doc.get('c1').vertices[1][0]") == 1000, "original do giro intacto")
    aba.avaliar("(() => { window.cad.selecionar(['o1']); window.cad.ativarFerramenta('girar'); const f = window.cad.ferramenta;"
                " f.onPonto([0, 0], { px: [0, 0] }); f.onValor('90'); return 1; })()")
    ok(aba.avaliar("window.cad.doc.tamanho") == n1 + 3 and abs(aba.avaliar("window.cad.doc.get('o1').b[0]")) < 1e-6,
       "sem Ctrl, Girar gira o próprio objeto")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
