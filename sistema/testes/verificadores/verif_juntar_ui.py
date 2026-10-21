# -*- coding: utf-8 -*-
"""Juntar pontas (usuário, 21/10/2026: "criar uma ferramenta similar a essa [Estender] para 'juntar' as peças, algo
similar ao fillet do AutoCAD, porém no 3D, onde ela ligue as peças no ponto médio entre as duas"): o clique em duas
barras leva a ponta de cada uma mais perto do encontro até o cruzamento dos eixos (eixos desencontrados: o meio do
segmento mais curto entre eles), esticando ou aparando, num desfazer só; os cortes da ponta que andou saem; com as duas
barras selecionadas, Enter junta; paralelas são recusadas. No editor de verdade (Chrome sem janela)."""
import json, os, shutil, subprocess, sys, tempfile, time
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_juntar_")
PASTA = os.path.join(DADOS, "jt")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Juntar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-21T00:00:00", "alterado": "2026-10-21T00:00:00", "dados": None},
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_juntar_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=jt", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('juntar'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()
    ok(aba.avaliar("!!(editor.ferramentas && editor.ferramentas.get('juntar'))"), "a ferramenta Juntar pontas está registrada no editor")

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    # o banzo que para antes do montante e o montante que para antes do banzo (os eixos se cruzam em (6000, 0, 0)):
    # os dois esticam até lá; o corte no ângulo da ponta que andou sai; um Ctrl+Z devolve os dois
    r = jsj("""const ed = editor, doc = ed.documento;
      const B = (nome, i, f, extra = {}) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: i, fim: f, rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {}, ...extra });
      const a = B('banzo', [0, 0, 0], [5000, 0, 0], { cortes_fim: [[-20, 0, 0]] });
      const b = B('montante', [6000, -3000, 0], [6000, -500, 0]);
      ed.selecao.limpar();
      ed.ativarFerramenta('juntar'); const f = ed.ativa;
      f.onPonto({ ponto: [4800, 0, 0], entidade: a.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const primeira = f.primeira === a.id;
      f.onMover({ ponto: [6000, -600, 0], entidade: b.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const medida = ed._textoMedida || '';
      f.onPonto({ ponto: [6000, -600, 0], entidade: b.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const A = doc.get(a.id), Bb = doc.get(b.id);
      const n2 = (c) => c && c.normal ? c.normal.map(x => Math.round(x * 100) / 100) : null;
      const depois = { aFim: A.fim.map(Math.round), aIni: A.inicio.map(Math.round), bFim: Bb.fim.map(Math.round), bIni: Bb.inicio.map(Math.round), cortes: (A.cortes_fim || []).length,
                       nA: n2((A.cortes_fim || [])[0]), nB: n2((Bb.cortes_fim || [])[0]), pA: ((A.cortes_fim || [])[0] || {}).ponto, pB: ((Bb.cortes_fim || [])[0] || {}).ponto };
      ed.desfazer();
      const volta = { aFim: doc.get(a.id).fim.map(Math.round), bFim: doc.get(b.id).fim.map(Math.round), cortes: (doc.get(a.id).cortes_fim || []).length };
      return { primeira, medida, depois, volta };""")
    print("     ", r)
    ok(r and r["primeira"] and r["depois"]["aFim"] == [6000, 0, 0] and r["depois"]["bFim"] == [6000, 0, 0]
       and r["depois"]["aIni"] == [0, 0, 0] and r["depois"]["bIni"] == [6000, -3000, 0],
       f"o banzo estica 1000 e o montante 500 até o cruzamento dos eixos (6000, 0, 0): {r and r['depois']}")
    ok(r and r["depois"]["cortes"] == 1 and r["depois"]["nA"] == [-0.71, 0.71, 0] and r["depois"]["nB"] == [0.71, -0.71, 0]
       and r["depois"]["pA"] == [0, 0, 0] and r["depois"]["pB"] == [0, 0, 0],
       f"as duas pontas cortadas em meia-esquadria (45°, normal para dentro de cada uma), no lugar do corte antigo: {r and (r['depois']['cortes'], r['depois']['nA'], r['depois']['nB'])}")
    ok(r and "+1,00 m" in r["medida"] and "+500 mm" in r["medida"] and "meia-esquadria" in r["medida"], f"a caixa de medidas mostra quanto cada uma estica: {r and r['medida']!r}")
    ok(r and r["volta"] == {"aFim": [5000, 0, 0], "bFim": [6000, -500, 0], "cortes": 1}, f"um Ctrl+Z devolve as duas: {r and r['volta']}")

    # aparar: o banzo passa do montante; eixos desencontrados (o montante 100 acima): encontro no meio (z = 50)
    r = jsj("""const ed = editor, doc = ed.documento;
      const B = (nome, i, f) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: i, fim: f, rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {} });
      const a = B('banzo2', [0, 5000, 0], [7000, 5000, 0]);
      const b = B('montante2', [6000, 2000, 100], [6000, 4500, 100]);
      ed.selecao.limpar();
      ed.ativarFerramenta('juntar'); const f = ed.ativa;
      f.onPonto({ ponto: [6500, 5000, 0], entidade: a.id }, {});
      f.onMover({ ponto: [6000, 4000, 100], entidade: b.id }, {});
      const medida = ed._textoMedida || '';
      f.onPonto({ ponto: [6000, 4000, 100], entidade: b.id }, {});
      return { medida, aFim: doc.get(a.id).fim, bFim: doc.get(b.id).fim, dica: ed._textoDica || (document.querySelector('#dica') || {}).textContent || '' };""")
    print("     ", r)
    ok(r and r["aFim"] == [6000, 5000, 50] and r["bFim"] == [6000, 5000, 50],
       f"o banzo apara 1000 e o montante estica 500; eixos a 100 mm: encontro no meio (z = 50): {r and (r['aFim'], r['bFim'])}")
    ok(r and "−1.000 mm" in r["medida"] and "+500 mm" in r["medida"] and "meio" in r["medida"], f"a caixa de medidas avisa o apara e o encontro no meio: {r and r['medida']!r}")

    # com as duas selecionadas, Enter junta; paralelas são recusadas (nada muda)
    r = jsj("""const ed = editor, doc = ed.documento;
      const B = (nome, i, f) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: i, fim: f, rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {} });
      const a = B('diag', [0, 9000, 0], [3000, 9000, 3000]);
      const b = B('pilar', [5000, 9000, 0], [5000, 9000, 3000]);
      ed.selecao.definir([a.id, b.id]);
      ed.ativarFerramenta('juntar'); const f = ed.ativa;
      const par = f.par ? f.par.length : 0;
      const tomou = f.onTecla({ type: 'keydown', key: 'Enter', ctrlKey: true });
      const depois = { aFim: doc.get(a.id).fim.map(Math.round), bFim: doc.get(b.id).fim.map(Math.round), bIni: doc.get(b.id).inicio.map(Math.round),
                       cortes: (doc.get(a.id).cortes_fim || []).length + (doc.get(b.id).cortes_fim || []).length };
      const p1 = B('par1', [0, 12000, 0], [4000, 12000, 0]), p2 = B('par2', [0, 12500, 0], [4000, 12500, 0]);
      ed.selecao.limpar(); ed.ativarFerramenta('juntar'); const g = ed.ativa;
      g.onPonto({ ponto: [3800, 12000, 0], entidade: p1.id }, {}); g.onPonto({ ponto: [3800, 12500, 0], entidade: p2.id }, {});
      const paralelas = { p1: doc.get(p1.id).fim, p2: doc.get(p2.id).fim, presa: g.primeira === p1.id };
      return { par, tomou, depois, paralelas };""")
    print("     ", r)
    ok(r and r["par"] == 2 and r["tomou"] and r["depois"]["aFim"] == [5000, 9000, 5000] and r["depois"]["bFim"] == [5000, 9000, 5000]
       and r["depois"]["bIni"] == [5000, 9000, 0] and r["depois"]["cortes"] == 0,
       f"com as duas selecionadas, Ctrl+Enter junta sem cortar: a diagonal a 45° estica até o pilar e o pilar sobe até ela: {r and r['depois']}")
    ok(r and r["paralelas"]["p1"] == [4000, 12000, 0] and r["paralelas"]["p2"] == [4000, 12500, 0] and r["paralelas"]["presa"],
       f"paralelas: recusa e fica na primeira barra, sem mexer: {r and r['paralelas']}")
    # Shift: o encaixe — o banzo (1º) para na face do montante (2º), cortado rente; o montante passa reto até a face de fora do banzo
    r = jsj("""const ed = editor, doc = ed.documento;
      const B = (nome, i, f) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: i, fim: f, rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {} });
      const a = B('banzo3', [0, 15000, 0], [5000, 15000, 0]);
      const b = B('montante3', [6000, 15000, -3000], [6000, 15000, -500]);
      ed.selecao.limpar(); ed.ativarFerramenta('juntar'); const f = ed.ativa;
      f.onPonto({ ponto: [4800, 15000, 0], entidade: a.id }, {});
      f.onMover({ ponto: [6000, 15000, -600], entidade: b.id }, { shiftKey: true });
      const medida = ed._textoMedida || '';
      f.onPonto({ ponto: [6000, 15000, -600], entidade: b.id }, { shiftKey: true });
      const A = doc.get(a.id), Bb = doc.get(b.id);
      // as bordas da seção do U (no sistema dela): a face em que o banzo para e a de fora do banzo são uma dessas quatro
      const pts = ed.cena._secaoDoPerfil('U 127×50×3,75').getPoints(24);
      const xs = pts.map(q => q.x), ys = pts.map(q => q.y);
      const bordas = [Math.max(...xs), -Math.min(...xs), Math.max(...ys), -Math.min(...ys)].map(v => Math.round(v * 100) / 100);
      return { medida, aFim: A.fim, bFim: Bb.fim, cortesA: A.cortes_fim || [], cortesB: (Bb.cortes_fim || []).length, bordas };""")
    print("     ", r)
    borda = lambda v: r and any(abs(v - b) < 0.05 for b in r["bordas"]) and v > 5
    ok(r and borda(6000 - r["aFim"][0]) and r["aFim"][1:] == [15000, 0] and r["bFim"][0] == 6000 and borda(r["bFim"][2]) and r["cortesB"] == 0,
       f"Shift: o banzo para na face do montante (uma borda da seção do U antes do eixo) e o montante passa reto até a face de fora do banzo, sem corte: {r and (r['aFim'], r['bFim'], r['cortesB'], r['bordas'])}")
    ok(r and len(r["cortesA"]) == 1 and [round(x, 2) for x in r["cortesA"][0]["normal"]] == [-1, 0, 0] and "face" in r["medida"],
       f"o banzo cortado rente à face do montante (plano x, normal para dentro); a caixa de medidas avisa: {r and (r['cortesA'], r['medida'])}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
