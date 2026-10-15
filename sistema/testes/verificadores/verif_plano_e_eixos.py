# -*- coding: utf-8 -*-
"""Plano de trabalho e snap da obra (F11 do levantamento de 14/10/2026), pela inferência de verdade (o raio da tela):
  o cruzamento de dois eixos num nível ("A-2 · +4,00"), o ponto sobre um eixo, a altura do nível na vertical da âncora;
  o plano de trabalho inclinado (a água de 10 %): o ponto solto cai nele, as direções dele aparecem a partir da âncora,
  a barra de baixo diz o plano, e Z volta ao chão."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_plano_")
PASTA = os.path.join(DADOS, "pl")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Plano", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_plano_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=pl", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('plano'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    PREP = """const ed = editor, inf = ed.inferencia;
      inf.referencias = { eixos: [{ nome: 'A', a: [0, -1000, 0], b: [0, 10000, 0] }, { nome: '1', a: [-1000, 0, 0], b: [10000, 0, 0] },
                                  { nome: '2', a: [-1000, 6000, 0], b: [10000, 6000, 0] }], niveis: [{ nome: '+4,00', z: 4000 }] };
      ed.camera.enquadrar([[-2000, -2000, -500], [8000, 8000, 5000]]); ed.camera.concluirAnimacao();
      const tela = (p) => ed.camera.paraTela(p);
      const em = (p, dx = 2, dy = 1) => { const t = tela(p); const r = inf.resolver(t[0] + dx, t[1] + dy, {}); return { tipo: r.tipoSnap, rot: r.rotulo, p: r.ponto.map(x => Math.round(x)) }; };"""
    r = jsj(PREP + """ed.ativarFerramenta('linha'); inf.limparAncora();
      const no = em([0, 6000, 4000]), no0 = em([0, 0, 0]);
      const sobre = em([0, 3000, 4000], 1, 0);
      inf.definirAncora([3000, 3000, 0]);
      const nivel = em([3000, 3000, 4000]);
      return { no, no0, sobre, nivel };""")
    print("     ", r)
    ok(r and r["no"]["tipo"] == "eixo_obra" and "A-2" in r["no"]["rot"] and "+4,00" in r["no"]["rot"] and r["no"]["p"] == [0, 6000, 4000],
       f"o cruzamento dos eixos A e 2 no nível +4,00: {r and r['no']}")
    ok(r and r["no0"]["tipo"] == "eixo_obra" and "A-1" in r["no0"]["rot"], f"o cruzamento A-1 no chão: {r and r['no0']}")
    ok(r and r["sobre"]["tipo"] == "sobre_eixo_obra" and "Eixo A" in r["sobre"]["rot"] and r["sobre"]["p"][0] == 0, f"o ponto sobre o eixo A: {r and r['sobre']}")
    ok(r and r["nivel"]["tipo"] == "nivel" and r["nivel"]["p"] == [3000, 3000, 4000], f"a altura do nível na vertical da âncora: {r and r['nivel']}")

    # o plano de trabalho: a água de 10 % (sobe em y), pela origem
    pl = aba.avaliar("""(async () => { const m = await import('/editor3d/ferramentas/plano.js');
      const ed = editor; ed.ativarFerramenta('plano'); ed.inferencia.referencias = null; ed.inferencia.limparAncora();
      ed.ativa.definir(m.planoDeTrabalho([0, 0, 0], [0, -0.1, 1]));
      return JSON.stringify({ nome: ed.inferencia.planoTrabalho.nome, trava: ed.el.trava.textContent }); })()""")
    pl = json.loads(pl) if pl else None
    ok(pl and pl["nome"] == "água 10,00 %" and "água 10,00 %" in pl["trava"], f"o plano da água de 10 % e a barra de baixo dizendo: {pl}")
    r = jsj(PREP + """inf.referencias = null; ed.ativarFerramenta('linha'); inf.limparAncora();
      const t = tela([2000, 3000, 300]); const solto = inf.resolver(t[0], t[1], {});
      const n = inf.planoTrabalho.normal, o = inf.planoTrabalho.origem;
      const dist = (solto.ponto[0] - o[0]) * n[0] + (solto.ponto[1] - o[1]) * n[1] + (solto.ponto[2] - o[2]) * n[2];
      inf.definirAncora([2000, 3000, 300]);
      const ey = inf.planoTrabalho.ey; const alvo = [2000 + ey[0] * 2000, 3000 + ey[1] * 2000, 300 + ey[2] * 2000];
      const ao = em(alvo, 1, 0);
      return { tipo: solto.tipoSnap, dist, ao };""")
    ok(r and r["tipo"] == "plano_base" and abs(r["dist"]) < 0.5, f"o ponto solto cai no plano de trabalho (distância {r and round(r['dist'], 3)} mm)")
    ok(r and r["ao"]["tipo"] == "eixo_plano" and "atravessado" in r["ao"]["rot"], f"a direção do caimento a partir da âncora: {r and r['ao']}")
    r = jsj("""const ed = editor; ed.ativarFerramenta('plano'); ed.ativa.onTecla({ type: 'keydown', key: 'z' });
      return { plano: ed.inferencia.planoTrabalho, normal: ed.planoTrabalho.normal };""")
    ok(r and r["plano"] is None and r["normal"] == [0, 0, 1], f"Z volta ao chão: {r}")
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
