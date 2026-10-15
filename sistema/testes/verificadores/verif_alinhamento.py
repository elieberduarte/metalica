# -*- coding: utf-8 -*-
"""Alinhamento por ponto lembrado (14/10/2026, o "a partir do ponto" do SketchUp), pelo raio de verdade da tela: o
canto em que o mouse parou fica lembrado; com âncora, andando no eixo X o snap trava onde x é o do canto ("Alinhado com
extremidade (X)"); sem âncora, a reta Y do canto; o Shift trava o eixo; a linha pontilhada e a marquinha aparecem."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_alinha_")
PASTA = os.path.join(DADOS, "al")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Alinha", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_alinha_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=al", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('linha'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    r = aba.avaliar("""(async () => {
      const ed = editor, inf = ed.inferencia, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [3000, 2000, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 200], [0, 200]], espessura: 10, centrada: false, furos: [], atributos: {} });
      ed.camera.enquadrar([[-500, -1500, -200], [4000, 3000, 800]]); ed.camera.concluirAnimacao();
      for (let i = 0; i < 40 && !ed.cena.objetos.has(ch.id); i++) await new Promise(r => setTimeout(r, 100));
      await new Promise(r => setTimeout(r, 300));
      ed.ativarFerramenta('linha'); inf.limparAncora();
      inf.resolver(10, 10, {});   // a primeira passada monta os contornos
      const tela = (p) => ed.camera.paraTela(p);
      const em = (p, dx = 1, dy = 1) => { const t = tela(p); return inf.resolver(t[0] + dx, t[1] + dy, {}); };
      const pairar = async (p) => { const a = em(p, 0, 0); await new Promise(r => setTimeout(r, 300)); em([1500, -1000, 10], 0, 0); return a.tipoSnap; };
      const canto = await pairar([3000, 2000, 10]);
      const lembrados = inf.lembrados.map(l => l.ponto.map(Math.round));
      inf.definirAncora([0, 0, 10]);
      const a = em([3000, 0, 10], 2, 0);
      const ra = { tipo: a.tipoSnap, p: a.ponto.map(Math.round), rot: a.rotulo, eixo: a.eixoAlinhado, cor: a.cor };
      inf.desenhar(a);
      const svg = inf.svg; const pontilhada = !!svg.querySelector('line[stroke-dasharray="2 4"]'); const marca = svg.querySelectorAll('circle.ponto-lembrado').length;
      inf.onTecla({ type: 'keydown', key: 'Shift' }); const trava = inf.travado; inf.onTecla({ type: 'keyup', key: 'Shift' });
      // sem âncora: a reta Y do canto
      inf.limparAncora(); await pairar([3000, 2000, 10]);
      const b = em([3000, 1000, 10], 2, 0);
      const rb = { tipo: b.tipoSnap, p: b.ponto.map(Math.round), eixo: b.eixoAlinhado };
      // dois pontos lembrados: o X de um e o Y do outro
      inf.limparAncora();
      const ch2 = doc.add({ tipo: 'chapa', nome: 'CH2', camada: 'Chapas', origem: [500, 3500, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 200], [0, 200]], espessura: 10, centrada: false, furos: [], atributos: {} });
      for (let i = 0; i < 40 && !ed.cena.objetos.has(ch2.id); i++) await new Promise(r => setTimeout(r, 100));
      ed.camera.enquadrar([[-500, -1500, -200], [4000, 4200, 800]]); ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 300));
      inf.resolver(10, 10, {});
      await pairar([3000, 2000, 10]); await pairar([500, 3500, 10]);
      inf.definirAncora([0, 0, 10]);
      const c2 = em([3000, 3500, 10], 2, 1);
      inf.desenhar(c2);
      const linhas2 = inf.svg.querySelectorAll('line[stroke-dasharray="2 4"]').length;
      const rc = { tipo: c2.tipoSnap, p: c2.ponto.map(Math.round), rot: c2.rotulo, linhas: linhas2, n: inf.lembrados.length };
      inf.limparAncora(); inf.limpar();
      return JSON.stringify({ canto, lembrados, ra, pontilhada, marca, trava, rb, rc }); })()""")
    r = json.loads(r) if r else None
    print("     ", r)
    ok(r and r["canto"] == "extremidade" and r["lembrados"] == [[3000, 2000, 10]], f"o canto em que o mouse parou ficou lembrado: {r and (r['canto'], r['lembrados'])}")
    ok(r and r["ra"]["tipo"] == "alinhado" and r["ra"]["p"] == [3000, 0, 10] and r["ra"]["eixo"] == "x" and "Alinhado com extremidade (X)" in r["ra"]["rot"] and r["ra"]["cor"] == "#c0392b",
       f"com âncora, no eixo X o snap trava na coordenada do canto, na cor do eixo: {r and r['ra']}")
    ok(r and r["pontilhada"] and r["marca"] == 1, f"a linha pontilhada do canto até o ponto e a marquinha do ponto lembrado: {r and (r['pontilhada'], r['marca'])}")
    ok(r and r["trava"] == "x", f"o Shift trava o eixo do alinhamento: {r and r['trava']}")
    ok(r and r["rc"]["tipo"] == "alinhado2" and r["rc"]["p"] == [3000, 3500, 10] and r["rc"]["linhas"] == 2,
       f"com dois pontos lembrados: o X de um e o Y do outro, com as duas linhas pontilhadas: {r and r['rc']}")
    ok(r and r["rb"]["tipo"] == "alinhado_livre" and r["rb"]["eixo"] == "y" and r["rb"]["p"][0] == 3000 and r["rb"]["p"][2] == 10,
       f"sem âncora, a reta Y que passa pelo canto: {r and r['rb']}")
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
