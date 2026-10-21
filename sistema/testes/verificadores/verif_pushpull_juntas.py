# -*- coding: utf-8 -*-
"""Empurrar/Puxar com barras selecionadas (usuário, 21/10/2026: "a ferramenta empurrar puxar não reage quando estão duas
peças selecionadas; ela deveria puxar ou empurrar as duas juntas, ela puxa apenas uma"): o clique numa barra que está
entre as selecionadas estica todas as selecionadas juntas — cada uma na própria ponta do mesmo lado, a mesma distância,
no próprio eixo —, num desfazer só; a barra clicada fora da seleção estica sozinha; a inclinada e a atravessada vão
no próprio eixo. No editor de verdade (Chrome sem janela), como os dois U do banzo da tela do usuário."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_pushpull_")
PASTA = os.path.join(DADOS, "pp")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Empurrar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pushpull_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=pp", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('pushpull'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    # os dois U do banzo (paralelos, 50 mm um do outro) selecionados; um terceiro U igual fora da seleção.
    # O clique vai sem `tela`: a ferramenta pega a barra pela entidade do ponto, não pelo pixel
    r = jsj("""const ed = editor, doc = ed.documento;
      const U = (nome, y) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: [0, y, 0], fim: [6000, y, 0], rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {} });
      const a = U('U-a', 0), b = U('U-b', 50), c = U('U-c', 500);
      ed.selecao.definir([a.id, b.id]);
      ed.ativarFerramenta('pushpull'); const f = ed.ativa;
      f.onMover({ ponto: [5900, 0, 0], entidade: a.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const medidaAntes = ed._textoMedida || '';
      f.onPonto({ ponto: [5900, 0, 0], entidade: a.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const juntas = f.alvo && f.alvo.juntas ? f.alvo.juntas.length : -1;
      f.onValor('500');
      const fins = () => [a, b, c].map(e => doc.get(e.id).fim.map(Math.round));
      const inicios = () => [a, b, c].map(e => doc.get(e.id).inicio.map(Math.round));
      const f1 = fins(), i1 = inicios();
      const n1 = ed.pilha.feitos.length;
      ed.desfazer(); const f2 = fins();
      // a barra fora da seleção estica sozinha
      f.onPonto({ ponto: [5900, 500, 0], entidade: c.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const sozinha = f.alvo && f.alvo.juntas ? f.alvo.juntas.length : -1;
      f.onValor('300'); const f3 = fins();
      // encurtar pelo começo: a ponta do mesmo lado (o início) das duas selecionadas anda
      f.onPonto({ ponto: [100, 50, 0], entidade: b.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      f.onValor('-200'); const i4 = inicios();
      return { medidaAntes, juntas, f1, i1, n1, f2, sozinha, f3, i4, ids: [a.id, b.id, c.id] };""")
    print("     ", r)
    ok(r and r["juntas"] == 1 and r["f1"] == [[6500, 0, 0], [6500, 50, 0], [6000, 500, 0]] and r["i1"] == [[0, 0, 0], [0, 50, 0], [0, 500, 0]],
       f"as duas barras selecionadas esticam juntas 500 pelo fim; a terceira, fora da seleção, fica: {r and (r['juntas'], r['f1'])}")
    ok(r and r["f2"] == [[6000, 0, 0], [6000, 50, 0], [6000, 500, 0]], f"um Ctrl+Z só devolve as duas: {r and r['f2']}")
    ok(r and r["sozinha"] == 0 and r["f3"] == [[6000, 0, 0], [6000, 50, 0], [6300, 500, 0]],
       f"a barra clicada fora da seleção estica sozinha: {r and (r['sozinha'], r['f3'])}")
    ok(r and r["i4"] == [[200, 0, 0], [200, 50, 0], [0, 500, 0]], f"encurtar 200 pelo início anda o início das duas: {r and r['i4']}")
    ok(r and "juntas" in (r["medidaAntes"] or ""), f"a caixa de medidas avisa que as selecionadas esticam juntas: {r and r['medidaAntes']!r}")

    # a inclinada e a atravessada: cada uma no próprio eixo, na ponta do mesmo lado do puxão
    r = jsj("""const ed = editor, doc = ed.documento;
      const B = (nome, i, f) => doc.add({ tipo: 'barra', nome, perfil: 'U 127×50×3,75', inicio: i, fim: f, rotacao: 0, papel: 'banzo', camada: 'Treliças', atributos: {} });
      const h = B('reta', [0, 2000, 0], [4000, 2000, 0]);
      const d = B('diagonal', [0, 2000, 0], [3000, 2000, 3000]);       // 45°, L = 4242,64
      const t = B('atravessada', [3800, 2000, -1000], [3800, 2000, 1000]); // perpendicular ao puxão
      ed.selecao.definir([h.id, d.id, t.id]);
      ed.ativarFerramenta('pushpull'); const f = ed.ativa;
      f.onPonto({ ponto: [3900, 2000, 100], entidade: h.id, normal: [0, 0, 1], tipoSnap: 'sobre_face' }, {});
      const pontas = f.alvo.juntas.map(j => j.barra);
      f.onValor('1000');
      const L = (e) => { const b = doc.get(e.id); return Math.round(Math.hypot(b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1], b.fim[2] - b.inicio[2])); };
      return { pontas, Lh: L(h), Ld: L(d), Lt: L(t), fimD: doc.get(d.id).fim.map(Math.round), fimT: doc.get(t.id).fim.map(Math.round), iniT: doc.get(t.id).inicio.map(Math.round) };""")
    print("     ", r)
    ok(r and r["Lh"] == 5000 and r["Ld"] == 5243 and r["fimD"] == [3707, 2000, 3707],
       f"a diagonal estica 1000 no próprio eixo (45°), pela ponta do lado do puxão: {r and (r['Ld'], r['fimD'])}")
    ok(r and r["Lt"] == 3000 and r["iniT"] == [3800, 2000, -1000] and r["fimT"] == [3800, 2000, 2000],
       f"a atravessada estica 1000 no próprio eixo, pela ponta mais perto do clique: {r and (r['Lt'], r['iniT'], r['fimT'])}")
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
