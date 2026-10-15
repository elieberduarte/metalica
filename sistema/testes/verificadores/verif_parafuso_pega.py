# -*- coding: utf-8 -*-
"""Parafuso: "Recalcular pela pega" (14/10/2026) — o parafuso já colocado mede de novo o pacote que aperta e passa ao
comprimento comercial (M12 com pega 18 → 40; a chapa de baixo engrossa para 16, pega 26 → 45), também o que veio do IFC
(sem registro, lido da malha); o Ctrl+Z volta; o que não encosta em nada fica como estava."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_pega_")
PASTA = os.path.join(DADOS, "pg")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Pega", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_pega_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=pg", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('parafuso'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    r = aba.avaliar("""(async () => { const m = await import('/editor3d/ferramentas/parafuso.js');
      const ed = editor, doc = ed.documento;
      const chapa = (z, e, nome) => doc.add({ tipo: 'chapa', nome, camada: 'Chapas', origem: [0, 0, z], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 200], [0, 200]], espessura: e, centrada: false, furos: [], atributos: {} });
      chapa(0, 10, 'CH cima'); const B = chapa(-8, 8, 'CH baixo');
      const bolt = (p, L, reg) => { const g = m.geometriaDoParafuso(12, L, p, [0, 0, 1], reg ? 18 : null);
        return doc.add({ tipo: 'solido', nome: 'BOLT (A325) 12x' + L, camada: 'Parafusos', vertices: g.vertices, faces: g.faces, arestas_vivas: [],
          atributos: { tipo_ifc: 'IfcMechanicalFastener', marcas: { perfil: 'BOLT (A325) 12x' + L },
                       ...(reg ? { parafuso: { d: 12, L, classe: 'A325', ponto: p, eixo: [0, 0, -1], pega: 18 } } : {}) } }); };
      const p1 = bolt([100, 100, 10], 80, true), p2 = bolt([50, 50, 10], 80, false), p3 = bolt([150, 150, 60], 80, true);
      ed.selecao.definir([p1.id, p2.id, p3.id]); ed.ativarFerramenta('parafuso'); const f = ed.ativa;
      const dica0 = ed.el && ed.el.dica ? ed.el.dica.textContent : '';
      const r1 = f.recalcularPelaPega();
      const n1 = [p1, p2, p3].map(p => doc.get(p.id).nome), pg1 = doc.get(p1.id).atributos.parafuso.pega;
      doc.alterar(B.id, { origem: [0, 0, -16], espessura: 16 });
      const r2 = f.recalcularPelaPega(f._selecionadosParaPega());
      const n2 = [p1, p2].map(p => doc.get(p.id).nome), reg2 = doc.get(p2.id).atributos.parafuso;
      ed.desfazer();
      const n3 = [p1, p2].map(p => doc.get(p.id).nome);
      return JSON.stringify({ r1, n1, pg1, r2, n2, pega2: reg2 && reg2.pega, n3, marca: doc.get(p1.id).atributos.marcas.perfil, dica0 }); })()""")
    r = json.loads(r) if r else None
    print("     ", r)
    ok(r and r["r1"]["recalculados"] == 2 and r["n1"] == ["BOLT (A325) 12x40", "BOLT (A325) 12x40", "BOLT (A325) 12x80"] and r["pg1"] == 18,
       f"pega 18 (10 + 8): M12x80 → M12x40, também o do IFC; o que não encosta fica: {r and r['n1']}")
    ok(r and r["r1"]["semPacote"] == 1, f"o que não encosta em nada é contado e fica como estava: {r and r['r1']}")
    ok(r and r["n2"] == ["BOLT (A325) 12x45", "BOLT (A325) 12x45"] and r["pega2"] == 26,
       f"a chapa de baixo engrossou para 16 (pega 26): → M12x45, e o do IFC ganhou o registro: {r and (r['n2'], r['pega2'])}")
    ok(r and r["n3"] == ["BOLT (A325) 12x40", "BOLT (A325) 12x40"] and r["marca"] == "BOLT (A325) 12x40", f"Ctrl+Z volta, com a marca da lista: {r and (r['n3'], r['marca'])}")
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
