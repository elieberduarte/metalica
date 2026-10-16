# -*- coding: utf-8 -*-
"""Regressões da seleção por peça e da legenda do "Colorir por" no editor 3D (15–16/10/2026, Kaefer e Mercado):
  1. 2e3414c — "com Alt pressionado não seleciona mais de uma peça, apenas uma de cada vez": com o Alt seguro, cada
     clique soma a peça (e tira, se já estava);
  2. 2499ca6 — "quando clico com Alt na segunda barra ele seleciona o grupo inteiro": duas barras do mesmo bloco pegas
     com Alt não abrem o painel do bloco nem pintam as vizinhas (o clique sem Alt continua pegando o bloco);
  3. 7f22cc7 — "quando desabilito a visualização de uma camada a lista rola para o início": ocultar um grupo na
     legenda mantém a rolagem.
O modelo é como o importado do Kaefer/Mercado: longe da origem (x ~3 km, y ~35 m), barras de um bloco (a mesma peça
de origem) e muitos perfis diferentes para a legenda rolar."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_selpeca_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Obra", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-16T00:00:00", "alterado": "2026-10-16T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
X0, Y0, Z0 = 3000000.0, 35000.0, 4000.0
PERFIS = ["W 150×13,0", "W 150×18,0", "W 200×15,0", "W 200×19,3", "W 250×17,9", "W 250×22,3", "W 250×32,7",
          "W 310×21,0", "W 310×28,3", "W 310×38,7", "W 360×32,9", "W 360×44,0", "W 410×38,8", "W 410×46,1",
          "W 460×52,0", "W 530×66,0", "U 127×50×2,00 (FF)", "TQ 100×100×4,75"]
doc = Documento()
# o bloco: duas barras paralelas da mesma peça de origem (as travessas TR25 do Kaefer)
for k in range(2):
    doc.add(Barra(nome="TR25-%d" % k, inicio=(X0, Y0 + 400.0 * k, Z0), fim=(X0 + 5900.0, Y0 + 400.0 * k, Z0),
                  perfil="U 127×50×2,00 (FF)", rotacao=0.0, papel="longarina", atributos={"origem": {"peca": "TR25#1"}}))
for i, p in enumerate(PERFIS):
    doc.add(Barra(nome="b%d" % i, inicio=(X0, Y0 + 3000.0 + 800.0 * i, Z0), fim=(X0 + 4000.0, Y0 + 3000.0 + 800.0 * i, Z0),
                  perfil=p, rotacao=0.0, papel="viga"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_selpeca_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=obra", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= %d)" % (2 + len(PERFIS))):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    ids = jsj("const m = {}; for (const e of editor.documento.entidades.values()) m[e.nome] = e.id; return m;")
    a, b = ids["TR25-0"], ids["TR25-1"]
    sel = "return [...editor.selecao.ids].sort();"
    # sem Alt: o clique pega o bloco inteiro e abre o painel dele (o comportamento que fica)
    aba.avaliar(f"editor.selecao.clicar({json.dumps(a)}, {{}}); 1"); aba.drenar(0.3)
    ok(jsj(sel) == sorted([a, b]) and bool(aba.avaliar("!!editor._painelBloco")), "sem Alt: o clique pega o bloco e abre o painel dele")
    aba.avaliar("editor.selecao.limpar(); 1"); aba.drenar(0.2)
    # 1. com Alt seguro: soma, e tira a que já estava
    aba.avaliar(f"editor.selecao.clicar({json.dumps(a)}, {{altKey: true}}); 1"); aba.drenar(0.2)
    ok(jsj(sel) == [a], "Alt+clique na primeira barra: só ela")
    aba.avaliar(f"editor.selecao.clicar({json.dumps(b)}, {{altKey: true}}); 1"); aba.drenar(0.3)
    ok(jsj(sel) == sorted([a, b]), "Alt+clique na segunda: as duas (antes trocava e ficava só a segunda)")
    # 2. as duas barras do mesmo bloco pegas com Alt não viram o bloco
    ok(not aba.avaliar("!!editor._painelBloco"), "duas barras do bloco com Alt: o painel do bloco não abre (antes pintava o grupo inteiro)")
    aba.avaliar(f"editor.selecao.clicar({json.dumps(b)}, {{altKey: true}}); 1"); aba.drenar(0.2)
    ok(jsj(sel) == [a], "Alt+clique de novo na segunda: ela sai")
    aba.avaliar("editor.selecao.limpar(); 1"); aba.drenar(0.2)

    # 3. a legenda do Colorir por perfil: ocultar um grupo lá embaixo mantém a rolagem
    aba.avaliar("editor.corPor = 'perfil'; editor._aplicarCorPor(); editor._agendarPaineis('camadas'); 1")
    t0 = time.time()
    while time.time() - t0 < 10 and not aba.avaliar("!!document.querySelector('.legenda-grupos .linha')"):
        aba.drenar(0.3)
    antes = jsj("const l = document.querySelector('.legenda-grupos'); l.scrollTop = l.scrollHeight; return {topo: l.scrollTop, max: l.scrollHeight - l.clientHeight};")
    ok(antes and antes["max"] > 40, f"a legenda rola (cabe menos que os {len(PERFIS) + 1} grupos: {antes})")
    aba.avaliar("const l = document.querySelector('.legenda-grupos'); const ls = l.querySelectorAll('.linha');"
                " ls[ls.length - 1].querySelector('button.alternador').click(); 1")
    aba.drenar(1.0)
    depois = jsj("const l = document.querySelector('.legenda-grupos'); const ls = l.querySelectorAll('.linha');"
                 " return {topo: l.scrollTop, oculta: ls[ls.length - 1].hasAttribute('data-oculta')};")
    ok(depois and depois["oculta"], "o último grupo ficou oculto")
    ok(depois and antes and abs(depois["topo"] - antes["topo"]) <= 2, f"a lista ficou rolada no mesmo lugar ({antes and antes['topo']} → {depois and depois['topo']}; antes voltava ao 0)")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:3]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
