# -*- coding: utf-8 -*-
"""O IFC do modelo pelo modo ver com as cores do Pintar (usuário, 19/10: "como fazer para exportar ... com a estrutura de
uma cor e a cobertura de outra, igual temos no modo ver"), no navegador de verdade: a tela dividida abre o 3D leve com o
Pintar "por sistema" e a metálica em roxo (o que o usuário escolheu); Arquivo › Exportar › IFC do modelo; o arquivo gerado
tem as camadas (layers) Metálica e Pré-moldado e a cor roxa; nenhum erro no console."""
import glob, json, os, re, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento, Material, Solido
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ifcpint_")
PASTA = os.path.join(DADOS, "pint")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Pintura", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
doc.materiais["CONCRETE/Fck-40"] = Material(nome="CONCRETE/Fck-40", cor="#1f77b4")
for i in range(3):
    doc.add(Barra(nome="T%d" % i, inicio=(i * 3000, 0, 5000), fim=(i * 3000, 9000, 5000), perfil="U 100×50×3,00 (FF)",
                  papel="banzo", camada="Tesouras"))
    doc.add(Solido(nome="Pilar %d" % i, camada="200 Pré-Fabricado", material="CONCRETE/Fck-40",
                   vertices=[(i * 3000, 0, 0), (i * 3000 + 300, 0, 0), (i * 3000 + 300, 300, 0), (i * 3000, 300, 0),
                             (i * 3000, 0, 5000), (i * 3000 + 300, 0, 5000), (i * 3000 + 300, 300, 5000), (i * 3000, 300, 5000)],
                   faces=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ifcpint_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    # o Pintar "por sistema" com a metálica roxa, como o usuário deixou o modo ver (guardado no navegador, por projeto)
    aba.navegar(f"http://localhost:{PORTA}/inicio", limite=60)
    aba.avaliar("""localStorage.setItem('ver3d:pint', JSON.stringify({ pintar: 'sistema',
        cores: { sistema: { metalica: '#8b5cf6' } } })); 1""")
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=pint", limite=90)

    def esperar(cond, limite=60.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(0.4)
        return False
    VER = "([...document.querySelectorAll('iframe')].map(f => { try { return f.contentWindow.pinturaParaIfc ? f.contentWindow : null; } catch (e) { return null; } }).find(Boolean))"
    ok(esperar(f"!!{VER} && !!{VER}.pinturaParaIfc()", 120), "o modo ver abriu pintado por sistema")
    p = json.loads(aba.avaliar(f"JSON.stringify({VER}.pinturaParaIfc())") or "null")
    nomes = {g["nome"]: g for g in (p or {}).get("grupos", [])}
    ok(p and p["modo"] == "sistema" and "Metálica" in nomes and nomes["Metálica"]["cor"] == "#8b5cf6" and len(nomes["Metálica"]["ids"]) == 3,
       f"a pintura da tela: a metálica roxa com as 3 barras ({[(g['nome'], g['cor'], len(g['ids'])) for g in (p or {}).get('grupos', [])]})")
    aba.console.clear()
    r = aba.avaliar("""(() => {
        const b = document.querySelector('#menus-unicos .menu[data-nome="Arquivo"] .menu-botao'); if (b) b.click();
        const m = document.querySelector('#menus-unicos .menu[data-nome="Arquivo"]');
        const it = [...m.querySelectorAll('button, a, li, div')].find(e => e.children.length <= 3 && /^IFC do modelo/.test((e.textContent || '').trim()));
        if (!it) return 'sem item'; it.click(); return 'ok'; })()""")
    ok(r == "ok", f"Arquivo › Exportar › IFC do modelo ({r})")
    ok(esperar("(() => { const c = document.getElementById('aviso-ifc-gravado'); return !!(c && c.querySelector('a')); })()", 90),
       "o aviso trouxe o link do IFC: " + str(aba.avaliar("(document.getElementById('aviso-ifc-gravado') || {}).textContent || ''")))
    arqs = glob.glob(os.path.join(PASTA, "ifc", "*.ifc"))
    texto = open(arqs[0], encoding="ascii").read() if arqs else ""
    camadas = set(re.findall(r"IFCPRESENTATIONLAYERWITHSTYLE\('([^']*)'", texto))
    ok(any(c.startswith("Met") for c in camadas) and any(c.startswith("Pr") for c in camadas),
       f"o IFC tem as camadas da pintura (Metálica, Pré-moldado): {sorted(camadas)}")
    ok(bool(re.search(r"IFCCOLOURRGB\(\$,0\.545\d*,0\.36\d*,0\.96\d*\)", texto)), "o IFC tem a metálica em roxo")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
