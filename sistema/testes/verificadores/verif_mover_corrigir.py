# -*- coding: utf-8 -*-
"""Mover e Girar (14/10/2026): logo depois de mover/girar ou copiar, a distância (o ângulo) digitada corrige o último movimento na mesma direção
(o espaçamento das cópias, depois do "*3"), como no SketchUp; o Ctrl+Z volta ao de antes; com outro comando no meio, não
mexe."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_mover_")
PASTA = os.path.join(DADOS, "mv")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Mover", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mover_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=mv", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('mover'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    r = jsj("""const ed = editor, doc = ed.documento;
      const v = doc.add({ tipo: 'barra', nome: 'viga', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [1000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      ed.selecao.definir([v.id]); ed.ativarFerramenta('mover'); const f = ed.ativa;
      f.onPonto({ ponto: [0, 0, 0], tela: [0, 0] }, {}); f.onPonto({ ponto: [500, 0, 0], tela: [0, 0] }, {});
      const m1 = doc.get(v.id).inicio[0];
      const corr = f.onValor('800'); const m2 = doc.get(v.id).inicio[0];
      ed.desfazer(); const m3 = doc.get(v.id).inicio[0];
      // cópia, *3 e depois o espaçamento 600
      f.onPonto({ ponto: [0, 0, 0], tela: [0, 0] }, { ctrlKey: true }); f.onPonto({ ponto: [0, 1000, 0], tela: [0, 0] }, {});
      f.onValor('*3');
      const ys = () => [...doc.entidades.values()].filter(e => e.tipo === 'barra' && e.id !== v.id).map(e => Math.round(e.inicio[1])).sort((a, b) => a - b);
      const c1 = ys(); f.onValor('600'); const c2 = ys();
      // outro comando no meio: a distância digitada não mexe
      f.onPonto({ ponto: [0, 0, 0], tela: [0, 0] }, {}); f.onPonto({ ponto: [0, 0, 300], tela: [0, 0] }, {});
      ed.executar(ed.ativa.constructor && { rotulo: 'outro', aplicar() {}, desfazer() {} });
      const z1 = doc.get(v.id).inicio[2]; const nada = f.onValor('900'); const z2 = doc.get(v.id).inicio[2];
      return { m1, corr, m2, m3, c1, c2, z1, nada, z2 };""")
    print("     ", r)
    ok(r and r["m1"] == 500 and r["corr"] and r["m2"] == 800, f"moveu 500 e o 800 digitado depois corrigiu para 800: {r}")
    ok(r and r["m3"] == 0, f"o Ctrl+Z volta à origem (a correção substituiu o movimento): {r and r['m3']}")
    ok(r and r["c1"] == [1000, 2000, 3000] and r["c2"] == [600, 1200, 1800], f"cópia *3 a 1000 e depois o 600 refaz as três a cada 600: {r and (r['c1'], r['c2'])}")
    ok(r and r["z1"] == 300 and not r["nada"] and r["z2"] == 300, f"com outro comando no meio, a distância digitada não mexe: {r and (r['z1'], r['nada'], r['z2'])}")
    r = jsj("""const ed = editor, doc = ed.documento;
      const v = doc.add({ tipo: 'barra', nome: 'viga2', perfil: 'W 250×32,7', inicio: [0, 5000, 0], fim: [1000, 5000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      ed.selecao.definir([v.id]); ed.ativarFerramenta('girar'); const f = ed.ativa;
      const P = (q) => ({ ponto: q, tela: [0, 0], normal: [0, 0, 1], tipoSnap: 'extremidade' });
      f.onPonto(P([0, 5000, 0]), {}); f.onPonto(P([1000, 5000, 0]), {});
      const g90 = f.onValor('90'); const a = doc.get(v.id).fim.map(Math.round);
      const g45 = f.onValor('45'); const b = doc.get(v.id).fim.map(Math.round);
      ed.desfazer(); const c = doc.get(v.id).fim.map(Math.round);
      return { g90, a, g45, b, c };""")
    print("     ", r)
    ok(r and r["g90"] and abs(r["a"][0]) <= 1 and abs(abs(r["a"][1] - 5000) - 1000) <= 1, f"girou 90°: {r and r['a']}")
    ok(r and r["g45"] and abs(r["b"][0] - 707) <= 1 and abs(abs(r["b"][1] - 5000) - 707) <= 1, f"o 45 digitado depois corrigiu para 45°: {r and r['b']}")
    ok(r and r["c"] == [1000, 5000, 0], f"o Ctrl+Z volta à posição de antes do giro: {r and r['c']}")
    # Empurrar/Puxar: puxar a face de cima da chapa 20 (10 → 30) e o 30 digitado logo depois corrige (→ 40)
    r = jsj("""const ed = editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [0, 9000, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [300, 0], [300, 200], [0, 200]], espessura: 10, centrada: false, furos: [], atributos: {} });
      ed.ativarFerramenta('pushpull'); const f = ed.ativa;
      f.onPonto({ ponto: [150, 9100, 10], entidade: ch.id, normal: [0, 0, 1], tela: [0, 0], tipoSnap: 'sobre_face' }, {});
      const pegou = !!f.alvo;
      f.onValor('20'); const e1 = doc.get(ch.id).espessura;
      const corr = f.onValor('30'); const e2 = doc.get(ch.id).espessura;
      ed.desfazer(); const e3 = doc.get(ch.id).espessura;
      return { pegou, e1, corr, e2, e3 };""")
    print("     ", r)
    ok(r and r["pegou"] and r["e1"] == 30 and r["corr"] and r["e2"] == 40 and r["e3"] == 10,
       f"Empurrar/Puxar: puxou 20 (10 → 30), o 30 digitado depois corrigiu (→ 40), o Ctrl+Z volta aos 10: {r}")
    # Retângulo e Círculo: a medida digitada logo depois corrige o que acabou de ser desenhado (sem duplicar)
    r = jsj("""const ed = editor, doc = ed.documento;
      const P = (q) => ({ ponto: q, tela: [0, 0], normal: [0, 0, 1], tipoSnap: 'plano_base', entidade: null });
      const formas = (nome) => [...doc.entidades.values()].filter(e => e.nome === nome);
      const ext = (e) => { const xs = e.vertices.map(v => v[0]), ys = e.vertices.map(v => v[1]); return [Math.round(Math.max(...xs) - Math.min(...xs)), Math.round(Math.max(...ys) - Math.min(...ys))]; };
      ed.ativarFerramenta('retangulo'); let f = ed.ativa;
      f.onPonto(P([0, 12000, 0]), {}); f.onMover(P([300, 12200, 0]), {});
      f.onValor('2000;1000'); const r1 = formas('Retângulo').map(ext);
      const c1 = f.onValor('2500;1000'); const r2 = formas('Retângulo').map(ext);
      const ruim = f.onValor('abc'); const r3 = formas('Retângulo').map(ext);
      ed.ativarFerramenta('circulo'); f = ed.ativa;
      f.onPonto(P([0, 15000, 0]), {}); f.onMover(P([100, 15000, 0]), {});
      f.onValor('500'); const k1 = formas('Círculo').map(e => e.atributos.raio);
      f.onValor('800'); const k2 = formas('Círculo').map(e => e.atributos.raio);
      ed.desfazer(); const k3 = formas('Círculo').length;
      return { r1, c1, r2, ruim, r3, k1, k2, k3 };""")
    print("     ", r)
    ok(r and r["r1"] == [[2000, 1000]] and r["c1"] and r["r2"] == [[2500, 1000]], f"Retângulo 2000×1000 e o 2500;1000 digitado depois corrigiu, sem duplicar: {r and (r['r1'], r['r2'])}")
    ok(r and not r["ruim"] and r["r3"] == [[2500, 1000]], f"um texto que não serve não estraga o que foi desenhado: {r and r['r3']}")
    ok(r and r["k1"] == [500] and r["k2"] == [800] and r["k3"] == 0, f"Círculo de raio 500 corrigido para 800; o Ctrl+Z tira o círculo: {r and (r['k1'], r['k2'], r['k3'])}")
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
