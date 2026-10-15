# -*- coding: utf-8 -*-
"""O snap não pega ponto escondido atrás da face sob o cursor (15/10/2026, PRATI: "colocar um perfil posicionado na
face dessa placa, ele pega um ponto de origem nada a ver atrás da placa, no pé da placa de trás"). Uma placa na frente;
atrás dela outra placa cujo canto cai no mesmo pixel; um cruzamento de eixos da obra no chão atrás das duas. Mirando a
face da frente nesses pixels, a ferramenta Barra recebe "Sobre face" na placa da frente; mirando o canto da própria
placa da frente, recebe a extremidade dela. Sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Chapa, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ocl3d_")
PASTA = os.path.join(DADOS, "ocl")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Oclusão", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
# a placa da frente no plano y = 0 (x 0..2000, z 0..2000) e a de trás em y = 1500 (x 1000..3000, z 500..2500)
doc.add(Chapa(nome="frente", origem=(0, 0, 0), eixo_x=(1, 0, 0), eixo_y=(0, 0, 1), contorno=[(0, 0), (2000, 0), (2000, 2000), (0, 2000)],
              espessura=12.5, centrada=False))
doc.add(Chapa(nome="tras", origem=(1000, 1500, 500), eixo_x=(1, 0, 0), eixo_y=(0, 0, 1), contorno=[(0, 0), (2000, 0), (2000, 2000), (0, 2000)],
              espessura=12.5, centrada=False))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ocl3d_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ocl", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 2)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None
    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            if js(cond): return True
            aba.drenar(0.3)
        return False
    def menu(acao):
        js(f"document.querySelector('[data-acao=\"{acao}\"]').click(); 1"); aba.drenar(0.3)
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    ids = jsj("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    def ent(i): return jsj(f"const e = editor.documento.get('{i}'); return e ? JSON.parse(JSON.stringify(e)) : null;")
    def chapas(): return jsj("return [...editor.documento.entidades.values()].filter(e => e.tipo === 'chapa').map(e => JSON.parse(JSON.stringify(e)));")
    def selecionar(*i): js(f"editor.selecao.definir({json.dumps(list(i))}); 1"); aba.drenar(0.3)

    # a vista de frente, um pouco de lado (a perspectiva), e os eixos da obra com um cruzamento no chão atrás das placas
    # a câmera de frente, de longe (y = −8 m, na altura de 1 m): a placa da frente cobre o canto da de trás e o cruzamento
    js("const V = editor.camera.ativa.position.constructor; editor.camera.irPara(new V(1.0, -8.0, 1.0), new V(1.0, 0, 1.0)); editor.camera.concluirAnimacao(); 1")
    aba.drenar(0.6)
    js("editor.inferencia.referencias = {eixos: [{nome: 'A', a: [1500, 800, 0], b: [1500, 3000, 0]}, {nome: '1', a: [-500, 1200, 0], b: [3500, 1200, 0]}], niveis: []}; 1")
    js("editor.ativarFerramenta('barra'); 1"); aba.drenar(0.3)
    def resolver_em(p3):
        return jsj(f"""const t = editor.camera.paraTela({json.dumps(p3)}); const r = editor.inferencia.resolver(t[0], t[1]);
                     return {{tipo: r.tipoSnap, ponto: r.ponto, ent: r.entidade && editor.documento.get(r.entidade).nome}};""")
    # o canto da placa de trás (1000, 1500, 500): no pixel dele, a face da frente está na frente
    r1 = resolver_em([1000, 1500, 500])
    ok(r1 and r1["tipo"] == "sobre_face" and r1["ent"] == "frente" and abs(r1["ponto"][1]) < 20,
       f"no pixel do canto escondido: Sobre face na placa da frente ({r1})")
    # o cruzamento dos eixos A-1 no chão (1500, 1200, 0), atrás da placa da frente
    r2 = resolver_em([1500, 1200, 0])
    ok(r2 and r2["tipo"] != "eixo_obra" and abs(r2["ponto"][1]) < 20, f"o cruzamento dos eixos atrás da placa não pega ({r2})")
    # o canto da própria placa da frente continua valendo
    r3 = resolver_em([2000, 0, 2000])
    ok(r3 and r3["tipo"] == "extremidade" and abs(r3["ponto"][0] - 2000) < 1 and abs(r3["ponto"][2] - 2000) < 1,
       f"o canto da placa da frente continua pegando ({r3})")
    erros("Oclusão")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
