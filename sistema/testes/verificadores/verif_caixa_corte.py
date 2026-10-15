# -*- coding: utf-8 -*-
"""Caixa de corte (14/10/2026, o "Section Box" do Revit): na seleção, a peça longe sai da vista, da seleção e do snap;
a que cruza a caixa fica cortada e o pedaço cortado não pega o clique; o menu do botão direito tira a caixa; o plano da
Seção tira a caixa e devolve as peças."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_caixa_")
PASTA = os.path.join(DADOS, "cx")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Caixa", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_caixa_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=cx", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('linha'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    r = aba.avaliar("""(async () => {
      const m = await import('/editor3d/modulos/caixa_corte.js'), mc = await import('/editor3d/modulos/menu_contexto.js');
      const ed = editor, doc = ed.documento, cena = ed.cena;
      const barra = (nome, a, b) => doc.add({ tipo: 'barra', nome, perfil: 'W 250×32,7', inicio: a, fim: b, rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const A = barra('A', [0, 0, 0], [2000, 0, 0]), B = barra('B', [0, 10000, 0], [2000, 10000, 0]), Cc = barra('C', [-5000, 200, 0], [5000, 200, 0]);
      for (let i = 0; i < 40 && ![A, B, Cc].every(e => cena.objetos.has(e.id)); i++) await new Promise(r => setTimeout(r, 100));
      // as malhas refinadas pelo servidor chegam depois e trocam os objetos: espera a troca acabar
      for (let i = 0; i < 50 && (cena._refinando || cena._pedidoAgendado); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 800));
      ed.selecao.definir([A.id]);
      m.caixaNaSelecao(ed);
      await new Promise(r => setTimeout(r, 600)); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      ed.camera.enquadrar([[-6000, -2000, -500], [6000, 2000, 2500]]); ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 300));
      const fora = doc.foraDaCaixa ? [...doc.foraDaCaixa] : [];
      const planos = cena.planosCorte.length;
      const vis = { A: doc.aparece(A), B: doc.aparece(B), C: doc.aparece(Cc) };
      const sobEm = (p) => { const t = ed.camera.paraTela(p); const s = ed.selecao.sob(t[0], t[1]); return s ? s.id : null; };
      const dentro = sobEm([1000, 200, 125]), cortado = sobEm([4000, 200, 125]);
      const itens = mc.itensDoMenu(ed, -1000, -1000).filter(i => i && i.rotulo).map(i => i.rotulo);
      // o plano da Seção tira a caixa
      cena.definirPlanoCorte({ origem: [0, 0, -5000], normal: [0, 0, 1] });
      const aposPlano = { fora: doc.foraDaCaixa, B: doc.aparece(B), caixa: cena.caixaCorte, planos: cena.planosCorte.length };
      cena.definirPlanoCorte(null);
      // e o menu tira
      ed.selecao.definir([A.id]); m.caixaNaSelecao(ed);
      m.definirCaixaDeCorte(ed, null);
      const tirada = { fora: doc.foraDaCaixa, planos: cena.planosCorte.length, B: doc.aparece(B) };
      return JSON.stringify({ fora, B: B.id, planos, vis, dentro, cortado, C: Cc.id, itens, aposPlano, tirada }); })()""")
    r = json.loads(r) if r else None
    print("     ", r)
    ok(r and r["fora"] == [r["B"]] and r["planos"] == 6 and r["vis"] == {"A": True, "B": False, "C": True},
       f"na seleção da viga A: a B (longe) fora da vista, a C (que cruza) cortada, seis planos: {r and (r['fora'], r['planos'], r['vis'])}")
    ok(r and r["dentro"] == r["C"] and r["cortado"] is None, f"o pedaço da C dentro da caixa pega o clique; o cortado, não: {r and (r['dentro'], r['cortado'])}")
    ok(r and "Tirar a caixa de corte" in r["itens"], f"o menu do botão direito oferece tirar a caixa: {r and r['itens']}")
    ok(r and r["aposPlano"]["fora"] is None and r["aposPlano"]["B"] and r["aposPlano"]["caixa"] is None and r["aposPlano"]["planos"] == 1,
       f"o plano da Seção tira a caixa e devolve a B: {r and r['aposPlano']}")
    ok(r and r["tirada"] == {"fora": None, "planos": 0, "B": True}, f"tirar a caixa volta o modelo inteiro: {r and r['tirada']}")
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
