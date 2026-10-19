# -*- coding: utf-8 -*-
"""A barra de andamento padrão (web/progresso.js, 16/10/2026: "criar barras de processo para todas as tarefas que têm
processamentos em segundo plano… tornar isso um padrão do sistema"). Antes só o texto da etapa na linha de dica, e em
muitas telas nem isso. Com o detalhar do galpão de exemplo (~5 s), de verdade, em três telas:

  1. CAD (tem rodapé): a chamada ao servidor ganha a barra sozinha no rodapé, com o rótulo e a etapa; some no fim e a
     duração fica guardada (a próxima vez estima o andamento por ela);
  2. lista de materiais (sem rodapé): a barra flutua embaixo;
  3. editor: com o acompanhamento da própria tela (_acompanharProgresso), uma barra só — a vigilância não põe outra.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_barra_")
os.makedirs(os.path.join(DADOS, "obra"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
json.dump({"formato": 1, "nome": "Obra", "tipo": "ifc", "alterado": "2026-10-16T00:00:00"},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c:
        falhas.append(m)


DISPARAR = """(() => { window.__fim = null;
  fetch('/api/projetos/obra/detalhar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => { window.__fim = r.status; }, () => { window.__fim = -1; }); return 1; })()"""
BARRAS = """JSON.stringify([...document.querySelectorAll('.barra-andamento')].map(b => ({
  flutua: b.classList.contains('flutuante'), no_rodape: !!b.closest('.rodape'), papel: b.getAttribute('role'),
  modo: b.dataset.modo, texto: b.title || b.textContent, ...cores(b) })))"""
# a luminância (0 escuro, 1 claro) do fundo e do texto da barra, para conferir o tema (Mercado, 19/10: a flutuante saía
# escura no tema claro, com o texto escuro por cima)
BARRAS = r"""(() => { const lum = (c) => { const v = (c.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number).map(x => x / 255)
  .map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const cores = (b) => { const e = getComputedStyle(b); return { fundo: lum(e.backgroundColor), letra: lum(e.color) }; };
  return """ + BARRAS + """; })()"""


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.2)
    return False


def disparar_e_ver(aba, rotulo):
    aba.avaliar(DISPARAR)
    viu = None
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("window.__fim") is None:
        b = json.loads(aba.avaliar(BARRAS) or "[]")
        if b and viu is None:
            viu = b
            aba.drenar(1.0)
            viu = json.loads(aba.avaliar(BARRAS) or "[]") or b       # um tique depois, com a etapa do servidor
        aba.drenar(0.15)
    aba.drenar(0.4)
    depois = json.loads(aba.avaliar(BARRAS) or "[]")
    print(f"  [{rotulo}] barra: {viu} · fim {aba.avaliar('window.__fim')} · depois {depois}")
    return viu, depois


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_barra_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/", limite=60)

    # 1. CAD: no rodapé, sozinha
    aba.navegar(base + "/cad?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.cad && document.body.dataset.pronto === '1' && window.__metalicaVigiaChamadas)"),
       "o CAD abriu com a vigilância das chamadas instalada (vivo.js → progresso.js)")
    aba.avaliar("localStorage.removeItem('metalica.duracao.obra|POST detalhar'); 1")
    viu, depois = disparar_e_ver(aba, "CAD")
    ok(bool(viu) and len(viu) == 1 and viu[0]["no_rodape"] and viu[0]["papel"] == "progressbar",
       "CAD: a chamada demorada ganhou uma barra no rodapé, sozinha")
    ok(bool(viu) and "Detalhando" in (viu[0]["texto"] or ""), f"CAD: com o rótulo da tarefa ({viu and viu[0]['texto']!r})")
    ok(aba.avaliar("window.__fim") == 200 and depois == [], "CAD: a barra some quando a tarefa termina")
    dur = aba.avaliar("localStorage.getItem('metalica.duracao.obra|POST detalhar')")
    ok(dur is not None and float(dur) > 1.0, f"CAD: a duração ficou guardada para a próxima estimativa ({dur} s)")
    viu2, _d = disparar_e_ver(aba, "CAD, de novo")
    ok(bool(viu2) and viu2[0]["modo"] in ("estimada", "servidor"),
       f"CAD: a segunda vez a barra tem número (pela duração da primeira): modo {viu2 and viu2[0]['modo']}")

    # 2. lista de materiais: sem rodapé, flutua
    aba.navegar(base + "/materiais?projeto=obra", limite=60)
    ok(esperar(aba, "!!window.__metalicaVigiaChamadas", 30), "a lista de materiais tem a vigilância")
    aba.drenar(1.0)
    viu, depois = disparar_e_ver(aba, "materiais")
    ok(bool(viu) and viu[0]["flutua"] and not viu[0]["no_rodape"], "materiais: a barra flutua embaixo (a tela não tem rodapé)")
    ok(depois == [], "materiais: e some no fim")
    # a flutuante segue o tema da tela: clara no claro, escura no escuro, e o texto legível nas duas (contraste ≥ 4,5)
    for tema in ("claro", "escuro"):
        aba.avaliar("document.documentElement.setAttribute('data-tema', '%s'); 1" % tema)
        viu, _d = disparar_e_ver(aba, "materiais, tema " + tema)
        f_, l_ = (viu[0]["fundo"], viu[0]["letra"]) if viu else (0.0, 0.0)
        contraste = (max(f_, l_) + 0.05) / (min(f_, l_) + 0.05)
        ok(bool(viu) and (f_ > 0.6 if tema == "claro" else f_ < 0.1) and contraste >= 4.5,
           f"materiais, tema {tema}: a barra flutuante no tema (fundo {f_:.2f}, texto {l_:.2f}, contraste {contraste:.1f})")

    # 3. editor: o acompanhamento da tela e a vigilância não fazem duas barras
    aba.navegar(base + "/editor?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.editor && window.editor.documento && window.editor.documento.entidades.size > 0 && window.__metalicaVigiaChamadas)", 90),
       "o editor abriu")
    aba.drenar(1.0)
    aba.avaliar("window.__parar = window.editor._acompanharProgresso('Detalhando: '); 1")
    viu, _d = disparar_e_ver(aba, "editor")
    aba.avaliar("window.__parar(); 1")
    aba.drenar(0.3)
    ok(bool(viu) and len(viu) == 1 and viu[0]["no_rodape"], f"editor: uma barra só, no rodapé ({len(viu or [])})")
    ok(json.loads(aba.avaliar(BARRAS) or "[]") == [], "editor: parar tira a barra")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:160] for x in e[:3]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
