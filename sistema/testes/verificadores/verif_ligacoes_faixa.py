# -*- coding: utf-8 -*-
"""A faixa "ligação(ões) com barra que mudou" do editor 3D (usuário, 04/11, Galpão Existente, 51 ligações: "não consigo
fechar essa notificação"; depois do "Refazer as ligações": "agora ficou uma salada de fruta de notificação").

  A. a faixa tem ×; fechada, não volta para as mesmas ligações; outra barra que muda a traz de novo;
  B. a faixa azul, a laranja do padrão de fábrica e os avisos ficam numa coluna só, sem se cobrir; o limite de 5 avisos
     não apaga as faixas;
  C. "Refazer as ligações" faz um pedido por tipo de ligação (não um por ligação) e dá um aviso só no fim.
Muitas ligações de dois tipos (placas de base em 8 pilares e chapas de topo), como no Galpão Existente."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ligfaixa_")
PASTA = os.path.join(DADOS, "lig")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Ligações", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-04T00:00:00", "alterado": "2026-11-04T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
W = "W 310×38,7"
doc = Documento()
for i in range(8):
    doc.add(Barra(nome="pilar%d" % i, inicio=(i * 6000, 0, 0), fim=(i * 6000, 0, 4000), perfil=W, rotacao=90, papel="pilar"))
for i in range(4):
    doc.add(Barra(nome="viga%d" % i, inicio=(i * 6000, 0, 3500), fim=(i * 6000, 6000, 3500), perfil=W, papel="viga"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ligfaixa_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=lig", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 12)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def js(e): return aba.avaliar(e)
    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        return json.loads(r) if r else None
    def esperar(cond, limite=30.0):
        t = time.time()
        while time.time() - t < limite:
            if js(cond): return True
            aba.drenar(0.3)
        return False
    def clicar(sel):
        r = js(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
        if not r: return False
        for tipo in ("mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
        aba.drenar(0.3)
        return True
    ids = jsj("const r = {}; for (const e of editor.documento.entidades.values()) r[e.nome] = e.id; return r;")
    pilares = [ids["pilar%d" % i] for i in range(8)]

    # as ligações: uma placa de base em cada pilar (um pedido) e uma chapa de topo em cada viga × pilar
    js(f"editor._pedirLigacao({{ tipo: 'placa_base_rotulada', ids: {json.dumps(pilares)} }}, 'Aplicar ligação'); 1")
    ok(esperar("[...editor.documento.entidades.values()].filter(e => e.nome === 'Placa de base').length === 8", 60), "8 placas de base")
    for i in range(4):
        js(f"editor._pedirLigacao({{ tipo: 'chapa_topo_joelho', ids: ['{ids['viga%d' % i]}', '{ids['pilar%d' % i]}'] }}, 'Aplicar ligação'); 1")
        esperar(f"[...editor.documento.entidades.values()].filter(e => e.nome === 'Chapa de topo').length === {i + 1}", 60)
    n_lig = jsj("return new Set([...editor.documento.entidades.values()].map(e => e.atributos && e.atributos.ligacao && e.atributos.ligacao.id).filter(Boolean)).size;")
    ok(n_lig == 12, f"12 ligações de dois tipos ({n_lig})")
    js("document.querySelectorAll('#avisos > .aviso').forEach(a => a.remove()); 1")

    # baixar o pé de 6 pilares: a faixa azul (6 placas + 4 chapas de topo); e a laranja do padrão de fábrica junto
    def baixar(lista):
        jsj(f"""for (const id of {json.dumps(lista)}) {{ const b = editor.documento.get(id);
                 editor.alterarEntidades([id], {{ inicio: [b.inicio[0], b.inicio[1], -500] }}, 'baixar o pé'); }} return 1;""")
    baixar(pilares[:6])
    ok(esperar("!!document.querySelector('.faixa-ligacoes')", 15), "a faixa das ligações com barra que mudou apareceu")
    js("editor._mostrarPendente3D({ posicoes: ['P831'] }); 1")
    for k in range(7):
        js(f"editor.aviso('aviso de teste {k}', 'info', 0); 1")
    r = jsj("""const av = document.querySelector('#avisos');
      const fx = [...document.querySelectorAll('.faixa-ligacoes, .faixa-padrao-3d')];
      const todos = [...av.children].filter(x => x.getBoundingClientRect().height > 0);
      const rs = todos.map(x => x.getBoundingClientRect());
      let cobre = 0;
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], b = rs[j];
        if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) cobre++;
      }
      return { faixas: fx.length, dentro: fx.every(f => f.parentElement === av), avisos: av.querySelectorAll(':scope > .aviso').length,
               primeiras: [...av.children].slice(0, 2).map(x => x.className), cobre };""")
    print("     ", r)
    ok(r and r["faixas"] == 2 and r["dentro"], f"as duas faixas na coluna dos avisos ({r})")
    ok(r and r["avisos"] == 5, f"o limite de 5 avisos não apagou as faixas ({r and r['avisos']})")
    ok(r and r["primeiras"] and all("faixa" in c for c in r["primeiras"]), f"as faixas no alto, os avisos embaixo ({r and r['primeiras']})")
    ok(r and r["cobre"] == 0, f"nada se cobre ({r and r['cobre']} sobreposições)")
    js("document.querySelectorAll('#avisos > .aviso').forEach(a => a.remove()); 1")

    # A. o × fecha; não volta para as mesmas; outra barra que muda a traz de novo
    ok(clicar(".faixa-ligacoes .fechar") and esperar("!document.querySelector('.faixa-ligacoes')", 5), "o × fecha a faixa das ligações")
    js("editor._conferirLigacoes(); 1"); aba.drenar(1.0)
    ok(not js("!!document.querySelector('.faixa-ligacoes')"), "fechada, não volta para as mesmas ligações")
    baixar([pilares[7]])
    ok(esperar("!!document.querySelector('.faixa-ligacoes')", 15), "outra barra que mudou traz a faixa de novo")

    # C. Refazer as ligações: um pedido por tipo e um aviso só
    js("""window.__pedidos = []; const f0 = window.fetch; window.fetch = (u, o) => { if (String(u).startsWith('/api/modelo/ligacao')) window.__pedidos.push(String(u)); return f0(u, o); }; 1""")
    n_antes = jsj("return editor.ligacoesDesatualizadas().length;")
    ok(clicar(".faixa-ligacoes button:not(.fechar)"), "clique em Refazer as ligações")
    ok(esperar("!document.querySelector('.faixa-ligacoes')", 90), "a faixa sai depois de refazer")
    r = jsj("""return { pedidos: window.__pedidos.length, avisos: [...document.querySelectorAll('#avisos > .aviso')].map(a => a.textContent),
                        desat: editor.ligacoesDesatualizadas().length,
                        placas: [...editor.documento.entidades.values()].filter(e => e.nome === 'Placa de base').map(e => Math.round(e.origem[2])) };""")
    print("     ", n_antes, r)
    ok(r and r["pedidos"] == 2, f"{n_antes} ligações refeitas em 2 pedidos (um por tipo), não um por ligação ({r and r['pedidos']})")
    ok(r and len(r["avisos"]) == 1 and "refeitas" in r["avisos"][0], f"um aviso só no fim ({r and r['avisos']})")
    ok(r and r["desat"] == 0 and sorted(r["placas"]) == [-500] * 7 + [0], f"as 7 placas no pé novo, a do pilar parado no lugar ({r and r['placas']})")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "Failed to load resource" not in m[1]]
    ok(not e, f"sem erros no console {[x[1][:200] for x in e[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
