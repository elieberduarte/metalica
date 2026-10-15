# -*- coding: utf-8 -*-
"""Virar e Encaixar no perfil que veio do IFC como malha (revisão 14/10/2026): o U de malha (vértices compartilhados e
repetidos por face, os dois jeitos do IFC) vira 180° no próprio eixo (a boca troca de lado, no mesmo lugar), a ponta
estica até a face e corta a 45°, o Ctrl+Z volta, e a ponta com dois planos (bico) é recusada com aviso."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_malha_")
PASTA = os.path.join(DADOS, "mp")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Malha", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_malha_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=mp", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('encaixar') && editor.ferramentas.get('virar'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    PREP = """const mp = await import('/editor3d/ferramentas/_malha_perfil.js');
      const ed = editor, doc = ed.documento;
      // o U 150×50×3 ao longo de x, boca para +y (alma em y 0–3)
      const sec = [[0, 0], [50, 0], [50, 3], [3, 3], [3, 147], [50, 147], [50, 150], [0, 150]];
      const malhaU = (x0, x1, repetidos, fimDe = null) => {
        const pt = (x, [y, z]) => [x, y, z];
        const a = sec.map(q => pt(x0, q)), b = sec.map(q => fimDe ? fimDe(q) : pt(x1, q));
        if (!repetidos) {
          const vertices = [...a, ...b], n = sec.length, faces = [[...Array(n).keys()].reverse(), [...Array(n).keys()].map(i => i + n)];
          for (let i = 0; i < n; i++) { const j = (i + 1) % n; faces.push([i, j, j + n, i + n]); }
          return { vertices, faces };
        }
        const vertices = [], faces = [];
        const face = (pts) => { const k = vertices.length; vertices.push(...pts.map(p => p.slice())); faces.push(pts.map((_, i) => k + i)); };
        face([...a].reverse()); face(b);
        for (let i = 0; i < sec.length; i++) { const j = (i + 1) % sec.length; face([a[i], a[j], b[j], b[i]]); }
        return { vertices, faces };
      };
      const add = (nome, m) => doc.add({ tipo: 'solido', nome, camada: 'IFC', vertices: m.vertices, faces: m.faces, arestas_vivas: [], atributos: { tipo_ifc: 'IfcMember' } });
      const cx = (e) => { const xs = doc.get(e.id).vertices.map(p => p[0]); return [Math.round(Math.min(...xs) * 10) / 10, Math.round(Math.max(...xs) * 10) / 10]; };
      const chapa = doc.add({ tipo: 'chapa', nome: 'CH alvo', camada: 'Chapas', origem: [2300, -200, -100], eixo_x: [0, 1, 0], eixo_y: [0, 0, 1],
        contorno: [[0, 0], [600, 0], [600, 400], [0, 400]], espessura: 10, centrada: true, furos: [], atributos: {} });"""
    for rep in (False, True):
        r = aba.avaliar("(async () => { " + PREP + """
          const rep = """ + ("true" if rep else "false") + """;
          const U = add('U 150x50x3 (IFC)', malhaU(0, 2000, rep));
          const q = mp.quadroDaMalha(doc.get(U.id));
          const placa = add('placa', malhaU(0, 300, rep, ([y, z]) => [300, y * 6, z * 2]));
          const naoComprida = !mp.quadroDaMalha(doc.get(placa.id)) ? 'recusada' : 'aceita';
          // Virar 180° (Ctrl): a boca para -y, no mesmo lugar
          ed.ativarFerramenta('virar'); let f = ed.ativa;
          f._barraSob = () => ({ e: doc.get(U.id), ponto: [1000, 25, 75], q: mp.quadroDaMalha(doc.get(U.id)) });
          f.onPonto({}, { ctrlKey: true });
          const vs = doc.get(U.id).vertices, ys = vs.map(p => p[1]), zs = vs.map(p => p[2]);
          const caixa = [Math.min(...ys), Math.max(...ys), Math.min(...zs), Math.max(...zs)].map(x => Math.round(x * 10) / 10);
          const alma = vs.filter(p => Math.abs(p[2] - 3) < 0.01 || Math.abs(p[2] - 147) < 0.01).map(p => Math.round(p[1] * 10) / 10);
          ed.desfazer();
          // Encaixar: esticar até a chapa em x 2300 (face de -x em 2295)
          ed.ativarFerramenta('encaixar'); f = ed.ativa;
          f.barra = U.id; f._sob = () => ({ id: chapa.id, ponto: [2295, 0, 0], normal: [-1, 0, 0] });
          f.onPonto({}, {});
          const est = cx(U);
          // a 45° no plano xy pelo ponto (2300, 25)
          f.barra = U.id; f._sob = () => ({ id: chapa.id, ponto: [2300, 25, 75], normal: [Math.SQRT1_2, Math.SQRT1_2, 0] });
          f.onPonto({}, {});
          const vs2 = doc.get(U.id).vertices.filter(p => p[0] > 1000);
          const diag = vs2.every(p => Math.abs(p[0] + p[1] - 2325) < 0.01);
          const est45 = cx(U);
          // bico: a ponta de 45° com um 2º plano não vira (a tampa não é um plano só depois de um corte em V à mão)
          ed.desfazer(); ed.desfazer();
          const volta = cx(U);
          const V = add('U bico', malhaU(0, 2000, rep, ([y, z]) => [2000 + (z > 75 ? 50 : 0), y, z]));
          f.barra = V.id; f._sob = () => ({ id: chapa.id, ponto: [2295, 0, 0], normal: [-1, 0, 0] });
          f.onPonto({}, {});
          const bico = { x: cx(V), dica: ed.el && ed.el.dica ? ed.el.dica.textContent : '' };
          return JSON.stringify({ q: q && [Math.round(q.t1 - q.t0), Math.round(q.largura), Math.round(q.altura)], naoComprida, caixa,
                                  alma: [...new Set(alma)].sort((a, b) => a - b), est, diag, est45, volta, bico }); })()""")
        r = json.loads(r) if r else None
        jeito = "vértices repetidos" if rep else "vértices compartilhados"
        print("     ", jeito, r)
        ok(r and sorted(r["q"]) == [50, 150, 2000] and r["naoComprida"] == "recusada", f"[{jeito}] o quadro do U de malha (2000 × 50 × 150) e a placa curta fora: {r and (r['q'], r['naoComprida'])}")
        ok(r and r["caixa"] == [0, 50, 0, 150] and r["alma"] == [0, 47], f"[{jeito}] Virar 180°: os cantos de dentro (y 3 e 50 antes) foram para y 0 e 47 — a boca para -y, na mesma caixa: {r and (r['caixa'], r['alma'])}")
        ok(r and r["est"] == [0, 2295], f"[{jeito}] Encaixar estica a ponta até a face da chapa: {r and r['est']}")
        ok(r and r["diag"] and r["est45"] == [0, 2325], f"[{jeito}] e corta a 45° (x + y = 2325 na ponta toda): {r and (r['diag'], r['est45'])}")
        ok(r and r["volta"] == [0, 2000], f"[{jeito}] Ctrl+Z volta a ponta: {r and r['volta']}")
        ok(r and r["bico"]["x"] == [0, 2050] and "não é um corte só" in r["bico"]["dica"], f"[{jeito}] a ponta com dois planos fica como está, com o aviso: {r and r['bico']}")
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
