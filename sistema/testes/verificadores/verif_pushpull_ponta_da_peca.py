# -*- coding: utf-8 -*-
"""Empurrar/Puxar na ponta de uma peça em sólido (usuário, 03/11/2026, no SESI Chapecó: "o puxar está fixando no eixo
apenas e não seguindo o alinhamento da peça; isso está fazendo o modelo entortar"). O rufo capa 232 é UM sólido com três
chapas (a capa e as duas abas), em caimento de 5,3 %, com a ponta da capa cortada na vertical: a face da ponta andava na
normal dela (o X do mundo, na horizontal) e só a capa andava — as abas ficavam, o rufo entortava. Agora a ponta anda no
comprimento da peça (a direção das arestas que saem da face) e as três chapas andam juntas. A geometria é a do rufo
e9cca35fd069f do modelo do SESI. A caixa comum segue como antes. No editor de verdade (Chrome sem janela)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

# o rufo do SESI (vértices e faces como estão no modelo.json da obra)
RUFO_V = [[11049.91,9208.5,20213.24],[11049.91,9440.12,20213.24],[18714.96,9440.12,19810],[18714.96,9208.5,19810],[11049.91,9208.5,20216.24],[11049.91,9440.12,20216.24],[18714.96,9440.12,19813],[18714.96,9208.5,19813],[11028.6,9208.5,19733.24],[18693.65,9208.5,19330.0],[18714.96,9208.5,19810],[11049.91,9208.5,20213.24],[11028.6,9211.5,19733.24],[18693.65,9211.5,19330.0],[18714.96,9211.5,19810],[11049.91,9211.5,20213.24],[11052.82,9440.12,20143.62],[18717.87,9440.12,19740.38],[18714.96,9440.12,19810],[11049.91,9440.12,20213.24],[11052.82,9443.12,20143.62],[18717.87,9443.12,19740.38],[18714.96,9443.12,19810],[11049.91,9443.12,20213.24]]
# a parede do arquitetônico (e5191d5c6ba73 do SESI): o topo e o fundo em dois triângulos, como as 733 paredes ARQ da obra
PAREDE_V = [[70475, 13403, 15810], [70667, 13403, 15810], [70667, 29866, 15810], [70475, 29866, 15810], [70475, 13403, 20351], [70667, 13403, 20351], [70667, 29866, 20351], [70475, 29866, 20351]]
PAREDE_F = [[7, 4, 5], [1, 0, 3], [5, 6, 7], [3, 2, 1], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
RUFO_F = [[3,2,1,0],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7],[8,9,10,11],[15,14,13,12],[8,12,13,9],[9,13,14,10],[10,14,15,11],[11,15,12,8],[16,17,18,19],[23,22,21,20],[16,20,21,17],[17,21,22,18],[18,22,23,19],[19,23,20,16]]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_pushpull_ponta_")
PASTA = os.path.join(DADOS, "pp")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Ponta", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-03T00:00:00", "alterado": "2026-11-03T00:00:00", "dados": None},
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pushpull_ponta_")
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

    # a ponta da capa (face 4, x = 18714,96, triângulos 8 e 9) puxada 614 mm, como na tela do usuário; o clique vai sem
    # `tela`: a ferramenta pega a face pelo triângulo e pelo ponto
    r = jsj(f"""const ed = editor, doc = ed.documento;
      const V = {json.dumps(RUFO_V)}, F = {json.dumps(RUFO_F)};
      const s = doc.add({{ tipo: 'solido', nome: 'Rufo capa 232 (chapa galv. #0,50)', camada: 'Rufos', vertices: V, faces: F, arestas_vivas: [], atributos: {{}} }});
      ed.selecao.definir([s.id]);
      ed.ativarFerramenta('pushpull'); const f = ed.ativa;
      const clique = {{ ponto: [18714.96, 9300, 19811.5], entidade: s.id, face: 8, normal: [1, 0, 0], tipoSnap: 'sobre_face' }};
      f.onMover(clique, {{}}); f.onPonto(clique, {{}});
      f.onValor('614');
      const W = doc.get(s.id).vertices;
      const rotulo = ed.pilha.feitos[ed.pilha.feitos.length - 1].rotulo || ed.pilha.feitos[ed.pilha.feitos.length - 1].nome || '';
      ed.desfazer();
      const voltou = doc.get(s.id).vertices.every((v, i) => v.every((c, k) => Math.abs(c - V[i][k]) < 1e-6));
      // alinhar no canto da parede (03/11): a ponta da capa, cortada na vertical, fica rente ao plano do canto (x 19.000)
      const parede = doc.add({{ tipo: 'solido', nome: 'parede', camada: 'Estrutura', vertices: [[19000,8000,18000],[19400,8000,18000],[19400,11000,18000],[19000,11000,18000],[19000,8000,21000],[19400,8000,21000],[19400,11000,21000],[19000,11000,21000]],
                               faces: [[3,2,1,0],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: {{}} }});
      f.onPonto(clique, {{}});
      f.onMover({{ ponto: [19000, 8000, 21000], entidade: parede.id, tipoSnap: 'extremidade' }}, {{}});
      f.onPonto({{ ponto: [19000, 8000, 21000], entidade: parede.id, tipoSnap: 'extremidade' }}, {{}});
      const alinhado = doc.get(s.id).vertices.map(v => v.slice());
      ed.desfazer();
      // a caixa comum (sem caimento): a ponta anda na normal, como antes
      const C = doc.add({{ tipo: 'solido', nome: 'caixa', camada: 'Estrutura', vertices: [[0,0,0],[1000,0,0],[1000,200,0],[0,200,0],[0,0,300],[1000,0,300],[1000,200,300],[0,200,300]],
                         faces: [[3,2,1,0],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]], arestas_vivas: [], atributos: {{}} }});
      ed.selecao.definir([C.id]);
      f.onPonto({{ ponto: [1000, 100, 150], entidade: C.id, face: 6, normal: [1, 0, 0], tipoSnap: 'sobre_face' }}, {{}});
      f.onValor('200');
      const caixa = doc.get(C.id).vertices.map(v => v.map(c => Math.round(c)));
      // a parede do arquitetônico (e5191d5c6ba73 do SESI, 03/11): caixa com o topo e o fundo em dois triângulos
      const P = doc.add({{ tipo: 'solido', nome: 'cerâmico 14 cm Reservatórios', camada: 'ARQ — Paredes', vertices: {json.dumps(PAREDE_V)}, faces: {json.dumps(PAREDE_F)}, arestas_vivas: [], atributos: {{ tipo_ifc: 'IfcWall' }} }});
      ed.selecao.definir([P.id]);
      let ultima = null; const previaOrig = ed.previa.bind(ed); ed.previa = (o) => (ultima = o, previaOrig(o));
      f.onMover({{ ponto: [70571, 20000, 20351], entidade: P.id, face: 0, normal: [0, 0, 1], tipoSnap: 'sobre_face' }}, {{}});
      let destaque = 0; if (ultima) ultima.traverse(o => {{ if (o.isMesh) destaque++; }}); ed.previa = previaOrig;
      f.onPonto({{ ponto: [70571, 20000, 20351], entidade: P.id, face: 0, normal: [0, 0, 1], tipoSnap: 'sobre_face' }}, {{}});
      const faces = f.alvo ? (f.alvo.iFaces || [f.alvo.iFace]).slice().sort() : null;
      f.onValor('500');
      const topo = doc.get(P.id).vertices.map(v => v.map(Math.round));
      ed.desfazer();
      // a lateral (x 70.667, triângulos 6 e 7): anda inteira 100
      f.onPonto({{ ponto: [70667, 20000, 18000], entidade: P.id, face: 6, normal: [1, 0, 0], tipoSnap: 'sobre_face' }}, {{}});
      f.onValor('100');
      const lado = doc.get(P.id).vertices.map(v => v.map(Math.round));
      return {{ W, voltou, rotulo, caixa, alinhado, destaque, faces, topo, lado }};""")
    if r:
        V, W = RUFO_V, r["W"]
        u = [V[3][k] - V[0][k] for k in range(3)]
        L = sum(c * c for c in u) ** 0.5
        u = [c / L for c in u]
        ponta = {2, 3, 6, 7, 9, 10, 13, 14, 17, 18, 21, 22}            # a ponta de x 18.7 m das três chapas
        desloc = [[W[i][k] - V[i][k] for k in range(3)] for i in range(len(V))]
        esperado = [614 * c for c in u]
        andaram = all(all(abs(desloc[i][k] - esperado[k]) < 0.05 for k in range(3)) for i in ponta)
        ficaram = all(all(abs(desloc[i][k]) < 1e-6 for k in range(3)) for i in range(len(V)) if i not in ponta)
        print("      ponta da capa:", [round(c, 2) for c in W[3]], "aba:", [round(c, 2) for c in W[9]], "esperado:", [round(c, 2) for c in esperado])
        ok(andaram, f"as três chapas (capa e abas) andam 614 mm no caimento do rufo (desloc. {[round(c, 2) for c in esperado]}): "
                    f"capa {[round(c, 2) for c in desloc[3]]}, aba {[round(c, 2) for c in desloc[9]]}, aba {[round(c, 2) for c in desloc[17]]}")
        ok(ficaram, "a outra ponta (x 11,0 m) fica parada")
        # o rufo segue reto: as 12 arestas do comprimento continuam paralelas ao caimento
        longas = [(0, 3), (1, 2), (4, 7), (5, 6), (8, 9), (11, 10), (12, 13), (15, 14), (16, 17), (19, 18), (20, 21), (23, 22)]
        def paralela(a, b):
            v = [W[b][k] - W[a][k] for k in range(3)]; n = sum(c * c for c in v) ** 0.5
            return sum(v[k] * u[k] for k in range(3)) / n > 0.99999
        ok(all(paralela(a, b) for a, b in longas), "o rufo não entorta: as 12 arestas do comprimento seguem no caimento")
        ok(r["voltou"], "um Ctrl+Z devolve o rufo como estava")
        Al = r["alinhado"]
        xs = [round(Al[i][0], 2) for i in (2, 3, 6, 7)]
        t = (19000 - V[3][0]) / u[0]
        ok(all(abs(x - 19000) < 0.01 for x in xs), f"no canto da parede, a ponta da capa fica rente ao plano dela (x 19.000): {xs}")
        ok(all(all(abs(Al[i][k] - V[i][k] - t * u[k]) < 0.05 for k in range(3)) for i in ponta),
           f"e as três chapas andam o mesmo no caimento ({t:.1f} mm)")
        PV = PAREDE_V
        ok(r["faces"] == [0, 2], f"parede: o topo em dois triângulos é uma face só (as faces 0 e 2): {r['faces']}")
        ok(r["destaque"] >= 2, f"parede: o destaque pinta os dois triângulos do topo: {r['destaque']} malhas na prévia")
        ok(r["topo"] == [v[:2] + [v[2] + (500 if v[2] == 20351 else 0)] for v in PV],
           f"parede: o topo inteiro sobe 500 (os 4 cantos), sem empenar: {r['topo']}")
        ok(r["lado"] == [[v[0] + (100 if v[0] == 70667 else 0)] + v[1:] for v in PV],
           f"parede: a lateral anda 100 inteira: {r['lado']}")
        ok(r["caixa"] == [[0,0,0],[1200,0,0],[1200,200,0],[0,200,0],[0,0,300],[1200,0,300],[1200,200,300],[0,200,300]],
           f"a caixa comum estica 200 na normal da ponta, como antes: {r['caixa']}")
    else:
        ok(False, "o editor respondeu")
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
