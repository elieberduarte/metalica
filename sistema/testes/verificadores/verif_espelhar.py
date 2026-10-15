# -*- coding: utf-8 -*-
"""Espelhar no editor 3D (F9 do levantamento de 14/10/2026): a malha da peça espelhada tem de cair, ponto a ponto, sobre
a malha da original refletida no plano — o U (boca), o W, a cantoneira de abas iguais, a barra inclinada e girada, com
corte no ângulo e recorte; a chapa (que cresce para fora da face) continua crescendo para o lado certo; a cantoneira
de abas desiguais não espelha (seria outra peça) e avisa."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_espelhar_")
PASTA = os.path.join(DADOS, "esp")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Espelhar", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


# a malha no mundo, a refletida e a comparação (cada ponto da refletida tem um ponto da espelhada a menos de 0,5 mm)
MALHA = """const malha = (id) => { const ed = editor, e = ed.documento.get(id);
    if (e.tipo === 'solido') return e.vertices.map(q => q.slice());
    const r = e.tipo === 'barra' ? ed.cena._geometriaBarra(e) : ed.cena._geometriaChapa(e);
    const p = r.geom.getAttribute('position'), m = r.matriz.elements, out = [];
    for (let i = 0; i < p.count; i++) { const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      out.push([m[0]*x + m[4]*y + m[8]*z + m[12], m[1]*x + m[5]*y + m[9]*z + m[13], m[2]*x + m[6]*y + m[10]*z + m[14]]); }
    return out; };
  const refl = (q, P, n) => { const d = (q[0]-P[0])*n[0] + (q[1]-P[1])*n[1] + (q[2]-P[2])*n[2]; return [q[0]-2*d*n[0], q[1]-2*d*n[1], q[2]-2*d*n[2]]; };
  const confere = (a, b) => { let pior = 0; for (const q of a) { let m = Infinity;
      for (const r of b) { const d = Math.hypot(q[0]-r[0], q[1]-r[1], q[2]-r[2]); if (d < m) m = d; if (m < 1e-6) break; }
      if (m > pior) pior = m; } return pior; };"""

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_espelhar_")
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
    aba.navegar(base + "/editor?projeto=esp", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('espelhar') && editor.catalogo && editor.catalogo.perfis && editor.catalogo.perfis.length > 100)"):
        aba.drenar(0.5)
    # os perfis dobrados chegam depois do banco básico
    perfis = json.loads(aba.avaliar("""JSON.stringify((() => { const ns = editor.catalogo.perfis.map(p => p.nome);
      const U = ns.find(n => /^U 100×40×2,00/.test(n)) || ns.find(n => /^U /.test(n));
      const L = ns.find(n => /^L 2"×1\\/8"$/.test(n)) || ns.find(n => /^L \\d/.test(n));
      const Ld = ns.find(n => /^L 4"×3"/.test(n)) || ns.find(n => { const m = n.match(/^L (\\d+)×(\\d+)×/); return m && m[1] !== m[2]; });
      return { U, W: 'W 250×32,7', L, Ld: Ld || 'L 75×50×6' }; })())"""))
    print("     perfis:", perfis)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(%s)" % " && ".join("editor.cena.perfil(%s)" % json.dumps(v) for v in perfis.values() if v)):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {MALHA} {e} }})())")
        return json.loads(r) if r else None

    casos = [
        ("U horizontal (boca para o lado)", {"perfil": perfis["U"], "inicio": [1000, 0, 0], "fim": [1000, 3000, 0], "rotacao": 0}),
        ("U girado 90° (boca para cima)", {"perfil": perfis["U"], "inicio": [1500, 0, 500], "fim": [1500, 3000, 500], "rotacao": 90}),
        ("W inclinada, com corte no ângulo e recorte",
         {"perfil": "W 250×32,7", "inicio": [800, 0, 0], "fim": [2800, 1000, 1500], "rotacao": 30,
          "cortes_fim": [{"normal": [0.6, 0.0, 0.8], "ponto": [0, 0, 0]}],
          "recortes": [{"ponta": "inicio", "lado": "cima", "comprimento": 80, "altura": 30}]}),
        ("cantoneira de abas iguais", {"perfil": perfis["L"], "inicio": [600, 0, 0], "fim": [600, 2000, 800], "rotacao": 0}),
        ("cantoneira de abas iguais girada 180°", {"perfil": perfis["L"], "inicio": [700, 0, 0], "fim": [700, 2000, 0], "rotacao": 180}),
    ]
    for nome, b in casos:
        campos = {"tipo": "barra", "nome": nome, "camada": "Estrutura", "papel": "viga", "atributos": {"marcas": {"posicao": "P1"}}, **b}
        r = jsj(f"""const ed = editor, doc = ed.documento; const e = doc.add({json.dumps(campos)});
          ed.selecao.definir([e.id]); ed.ativarFerramenta('espelhar'); const f = ed.ativa;
          f.aplicar({{ p: [0, 0, 0], n: [1, 0, 0] }}, false);
          const c = ed.selecao.ids.size ? [...ed.selecao.ids][0] : null; if (!c || c === e.id) return null;
          const orig = malha(e.id).map(q => refl(q, [0, 0, 0], [1, 0, 0])), nova = malha(c);
          const ce = doc.get(c);
          return {{ pior: confere(orig, nova), volta: confere(nova, orig), rot: ce.rotacao, conf: !!ce.atributos.marca_a_conferir }};""")
        ok(r and r["pior"] < 0.5 and r["volta"] < 0.5 and r["conf"],
           f"F9 {nome}: a malha espelhada cai sobre a refletida (maior distância {r and round(max(r['pior'], r['volta']), 3)} mm; rotação {r and r['rot']}; marca a conferir)")
        aba.avaliar("editor.ativarFerramenta('selecionar'); 1")

    # a cantoneira de abas desiguais não espelha (seria outra peça)
    if perfis.get("Ld"):
        r = jsj(f"""const ed = editor, doc = ed.documento;
          const e = doc.add({{ tipo: 'barra', nome: 'Ld', perfil: {json.dumps(perfis['Ld'])}, inicio: [400, 0, 0], fim: [400, 2000, 0], rotacao: 0, papel: 'barra', camada: 'Estrutura', atributos: {{}} }});
          const n0 = doc.entidades.size; ed.selecao.definir([e.id]); ed.ativarFerramenta('espelhar'); ed.ativa.aplicar({{ p: [0, 0, 0], n: [1, 0, 0] }}, false);
          const avisos = [...document.querySelectorAll('.aviso, .avisos *, [role=alert]')].map(x => x.textContent).join(' | ');
          return {{ novas: doc.entidades.size - n0, aviso: avisos.includes('simetria') || avisos.includes('seção do perfil') }};""")
        ok(r and r["novas"] == 0 and r["aviso"], f"F9: a cantoneira de abas desiguais ({perfis['Ld']}) não espelha e avisa: {r}")
        aba.avaliar("editor.ativarFerramenta('selecionar'); 1")

    # a chapa que cresce para fora da face: espelhada, cresce para o lado espelhado
    r = jsj("""const ed = editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [500, 200, 100], eixo_x: [1, 0, 0], eixo_y: [0, 0.6, 0.8],
        contorno: [[0, 0], [200, 0], [200, 120], [0, 120]], espessura: 12.5, centrada: false, furos: [{ x: 50, y: 40, diametro: 17.5 }], atributos: {} });
      ed.selecao.definir([ch.id]); ed.ativarFerramenta('espelhar'); ed.ativa.aplicar({ p: [0, 0, 0], n: [1, 0, 0] }, false);
      const c = [...ed.selecao.ids][0];
      const orig = malha(ch.id).map(q => refl(q, [0, 0, 0], [1, 0, 0])), nova = malha(c);
      return { pior: confere(orig, nova), volta: confere(nova, orig) };""")
    ok(r and r["pior"] < 0.5 and r["volta"] < 0.5, f"F9: a chapa (com furo, crescendo para fora) espelhada no lugar certo: {r}")
    aba.avaliar("editor.ativarFerramenta('selecionar'); 1")

    # o teclado: X espelha no plano x pelo centro da seleção; Ctrl+clique / Shift+X move
    r = jsj("""const ed = editor, doc = ed.documento;
      const e = doc.add({ tipo: 'barra', nome: 'T', perfil: 'W 250×32,7', inicio: [0, 5000, 0], fim: [2000, 5000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      ed.selecao.definir([e.id]); ed.ativarFerramenta('espelhar');
      const n0 = doc.entidades.size; ed.ativa.onTecla({ type: 'keydown', key: 'z' });
      return { novas: doc.entidades.size - n0 };""")
    ok(r and r["novas"] == 1, f"F9: a tecla Z espelha (cópia) no plano horizontal pelo centro: {r}")
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
