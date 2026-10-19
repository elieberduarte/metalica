# -*- coding: utf-8 -*-
"""Regressão (19/10, anexo do Mercado Hermes): "porque ele pinta as vigas junto?" — com um bloco (a tesoura) selecionado, o
painel destaca no que as pontas encostam; nas peças em lote (modelo com mais de 1.500 peças, o caso do Mercado) o destaque
era o laranja cheio da peça escolhida no 2D, e as vigas pré-moldadas onde a tesoura apoia saíam laranja como a tesoura.
Aqui, no navegador de verdade e com o lote: o clique na tesoura deixa as vigas vizinhas na cor delas (não fantasma, não
laranja), a tesoura no laranja do destaque, e o painel ainda lista as vigas; sem erros no console."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento, Material, Solido
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_blviz_")
PASTA = os.path.join(DADOS, "blviz")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Vizinhas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
doc.materiais["CONCRETE/Fck-40"] = Material(nome="CONCRETE/Fck-40", cor="#7f8c99")
U = "U 100×50×3,00 (FF)"
at = {"origem": {"peca": "T.7"}, "conjunto": "T.7#2"}
tes = []
for a, b, papel in (((0, 0, 3500), (6000, 0, 3500), "banzo"), ((0, 0, 4500), (6000, 0, 4500), "banzo"),
                    ((0, 0, 3500), (0, 0, 4500), "montante"), ((3000, 0, 3500), (3000, 0, 4500), "montante"),
                    ((6000, 0, 3500), (6000, 0, 4500), "montante"), ((0, 0, 4500), (3000, 0, 3500), "diagonal"),
                    ((6000, 0, 4500), (3000, 0, 3500), "diagonal")):
    tes.append(doc.add(Barra(nome=papel, inicio=a, fim=b, perfil=U, papel=papel, camada="Tesouras",
                             atributos=json.loads(json.dumps(at)))))
vigas = []
for x in (0, 6000):                                     # as vigas pré-moldadas sob as pontas, atravessando a tesoura
    x0, x1 = x - 100, x + 100
    vigas.append(doc.add(Solido(nome="Viga", camada="200 Pré-Fabricado", material="CONCRETE/Fck-40",
        vertices=[(x0, -3000, 2900), (x1, -3000, 2900), (x1, 3000, 2900), (x0, 3000, 2900),
                  (x0, -3000, 3450), (x1, -3000, 3450), (x1, 3000, 3450), (x0, 3000, 3450)],
        faces=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])))
for i in range(1600):                                   # o enchimento: o modelo passa das 1.500 peças e entra o lote
    x = 50000 + (i % 40) * 500
    y = 50000 + (i // 40) * 500
    doc.add(Barra(nome="enchimento", inicio=(x, y, 0), fim=(x, y, 300), perfil=U, papel="barra", camada="Enchimento"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_blviz_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=blviz", limite=90)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 1609)"):
        aba.drenar(0.5)
    aba.drenar(2.0)
    ok(aba.avaliar("!!editor.cena.lote"), "o modelo grande está em lote (como o Mercado)")
    aba.console.clear()
    # o clique de verdade no banzo de cima da tesoura (enquadrado no meio da tela)
    for _ in range(3):
        aba.avaliar(f"editor.camera.zoomSelecao(['{tes[1].id}']); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); 1")
        aba.drenar(0.5)
    x, y = json.loads(aba.avaliar("""JSON.stringify((() => { const c = editor.el.canvas || document.querySelector('canvas');
        const r = c.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"""))
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    aba.drenar(0.2)
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
    aba.drenar(1.5)
    sel = json.loads(aba.avaliar("JSON.stringify(editor.selecao.entidades.map(e => e.id))") or "[]")
    ok(set(sel) == {b.id for b in tes}, f"o clique pegou a tesoura ({len(sel)} barras)")
    painel = aba.avaliar("(document.querySelector('.painel-bloco') || {}).textContent || ''")
    ok("Viga" in painel, "o painel do bloco lista as vigas em que a tesoura encosta")
    cores = json.loads(aba.avaliar("""JSON.stringify((() => { const c = editor.cena;
        const cor = (id) => { const it = c.lote && c.lote.itens.get(id); return it ? String(it.corMalha).toLowerCase() : null; };
        return { vigas: %s.map(cor), tesoura: %s.map(cor), destaque: [...(c.destaque || [])].length }; })())""" %
        (json.dumps([v.id for v in vigas]), json.dumps([b.id for b in tes]))))
    print("      ", cores)
    laranja, fantasma = "#ff5a1f", ("#d7dce6", "#2e3642")
    ok(all(c and c != laranja and c not in fantasma for c in cores["vigas"]),
       f"as vigas vizinhas na cor delas, nem laranja nem apagadas ({cores['vigas']})")
    ok(all(c == laranja for c in cores["tesoura"]), f"a tesoura no laranja do destaque ({set(cores['tesoura'])})")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
