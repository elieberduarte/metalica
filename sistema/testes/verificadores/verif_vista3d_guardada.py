# -*- coding: utf-8 -*-
"""Os grupos ocultos e as cores do "Colorir por" ficam (usuário, 16/10/2026): ao recarregar o editor eles voltavam a
aparecer, o modo ver não sabia deles, e a cor de um perfil no ver era outra que no editor. Num projeto com três perfis:
  1. no editor, Colorir por perfil e ocultar um perfil; recarregar: o perfil continua oculto e as cores são as mesmas;
  2. no modo ver: as peças do perfil oculto somem, o Pintar abre "como no editor" e cada peça tem a cor do editor;
  3. "por perfil" no ver usa a mesma paleta e a mesma ordem do editor."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_vista3d_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Obra", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-16T00:00:00", "alterado": "2026-10-16T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
PERFIS = ["W 250×32,7", "TQ 100×100×4,75", "U 127×50×2,00 (FF)"]
doc = Documento()
for k, p in enumerate(PERFIS):
    for j in range(2):
        doc.add(Barra(nome=f"b{k}{j}", inicio=(0.0, 1000.0 * k, 1000.0 * j), fim=(3000.0, 1000.0 * k, 1000.0 * j), perfil=p, rotacao=0.0, papel="viga"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_vista3d_")
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
    base = f"http://localhost:{PORTA}"

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    def abrir_editor():
        aba.navegar(base + "/editor?projeto=obra", limite=60)
        t0 = time.time()
        while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size >= 6)"):
            aba.drenar(0.5)
        aba.drenar(1.5)

    CORES = ("const m = new Map(); for (const e of editor.documento.entidades.values()) m.set(e.nome, editor._coresGrupo ? editor._coresGrupo.get(e.perfil) : null);"
             " return {corPor: editor.corPor, ocultos: [...(editor._gruposOcultos || [])], vista: [...(editor.documento.ocultosNaVista || [])].map(i => editor.documento.get(i).nome).sort(), cores: Object.fromEntries(m)};")
    abrir_editor()
    aba.avaliar("editor.corPor = 'perfil'; editor._aplicarCorPor(); editor._ocultarGrupos(new Set([%s])); 1" % json.dumps(PERFIS[1]))
    t0 = time.time()                       # o salvamento automático da aparência termina antes de recarregar
    while time.time() - t0 < 20 and aba.avaliar("!!(editor._autosavePendente || editor._autosalvando)"):
        aba.drenar(0.3)
    antes = jsj(CORES)
    ok(antes["vista"] == ["b10", "b11"], f"editor: o TQ oculto ({antes['vista']})")
    abrir_editor()
    depois = jsj(CORES)
    ok(depois["corPor"] == "perfil" and depois["ocultos"] == [PERFIS[1]] and depois["vista"] == ["b10", "b11"],
       f"recarregado: Colorir por perfil e o TQ continua oculto ({depois['corPor']}, {depois['ocultos']}, {depois['vista']})")
    ok(depois["cores"] == antes["cores"], "recarregado: as mesmas cores por peça")

    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar("!!window.ver3dPronto"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    v = jsj("const out = {}; visor.fichas.forEach((f, i) => { if (i < visor.nPecas) out[f.n] = {oculta: visor.ocultas.has(i),"
            " cor: '#' + [0, 1, 2].map(k => visor.corBase[i * 3 + k].toString(16).padStart(2, '0')).join('')}; });"
            " return {pecas: out, pintar: document.querySelector('#pintar').value};")
    ok(v is not None, "modo ver abriu")
    if v:
        ocultas = sorted(n for n, x in v["pecas"].items() if x["oculta"])
        ok(ocultas == ["b10", "b11"], f"modo ver: as peças ocultas no editor somem ({ocultas})")
        ok(v["pintar"] == "editor", f"modo ver: o Pintar abre como no editor ({v['pintar']})")
        dif = {n: (x["cor"], antes["cores"][n]) for n, x in v["pecas"].items() if x["cor"].lower() != str(antes["cores"][n]).lower()}
        ok(not dif, f"modo ver: cada peça com a cor do editor ({dif or 'iguais'})")
        p = jsj("const s = document.querySelector('#pintar'); s.value = 'perfil'; s.dispatchEvent(new Event('change'));"
                " const out = {}; visor.fichas.forEach((f, i) => { if (i < visor.nPecas) out[f.n] = '#' + [0, 1, 2].map(k => visor.corBase[i * 3 + k].toString(16).padStart(2, '0')).join(''); });"
                " return out;")
        dif = {n: (c, antes["cores"][n]) for n, c in p.items() if c.lower() != str(antes["cores"][n]).lower()}
        ok(not dif, f"modo ver por perfil: a paleta e a ordem do editor ({dif or 'iguais'})")
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
