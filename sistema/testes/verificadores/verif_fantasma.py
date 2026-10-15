# -*- coding: utf-8 -*-
"""Prévia fantasma (14/10/2026): no Mover, Girar, Espelhar e Copiar a própria peça aparece translúcida no destino (não só a silhueta),
com as malhas da cena — limpar a prévia não as descarta —, sem pegar o clique nem o snap."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fantasma_")
PASTA = os.path.join(DADOS, "fm")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fantasma", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fantasma_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=fm", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('mover'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    r = jsj("""const ed = editor, doc = ed.documento, cena = ed.cena;
      const v = doc.add({ tipo: 'barra', nome: 'viga', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [2000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const obj = cena.objetos.get(v.id);
      let descartadas = 0; obj.traverse(x => { if (x.geometry) x.geometry.addEventListener('dispose', () => descartadas++); });
      ed.selecao.definir([v.id]); ed.ativarFerramenta('mover'); const f = ed.ativa;
      f.onPonto({ ponto: [0, 0, 0], tela: [0, 0] }, {});
      f.onMover({ ponto: [0, 1500, 0], tela: [0, 0] });
      const achar = () => { let fan = null; cena.previa.traverse(x => { if (!fan && x.isMesh && x.material && x.material.userData.compartilhada) fan = x; }); return fan; };
      const fan = achar();
      const pos = new ed.cena.raiz.position.constructor(); if (fan) { fan.updateWorldMatrix(true, false); pos.setFromMatrixPosition(fan.parent.parent.matrix); }
      f.onMover({ ponto: [0, 1600, 0], tela: [0, 0] });
      const fan2 = achar(); let t2 = null; if (fan2) t2 = fan2.parent.parent.matrix.elements.slice(12, 15).map(Math.round);
      // o fantasma não pega o raio
      const rc = []; if (fan2) fan2.raycast({}, rc);
      f.cancelar(); ed.limparPrevia();
      // Girar 90° no centro (0,0): o fantasma na posição girada
      ed.selecao.definir([v.id]); ed.ativarFerramenta('girar'); const g = ed.ativa;
      const P = (q) => ({ ponto: q, tela: [0, 0], normal: [0, 0, 1], tipoSnap: 'extremidade' });
      g.onPonto(P([0, 0, 0]), {}); g.onPonto(P([1000, 0, 0]), {});
      g.angulo = 90; g.desenhar();
      const fg = achar(); let mg = null; if (fg) mg = fg.parent.parent.matrix.elements.map(x => Math.round(x * 1000) / 1000);
      g.cancelar(); ed.limparPrevia();
      return { tem: !!fan, t1: pos.toArray().map(Math.round), t2, rc: rc.length, descartadas, geoOk: !!(cena.objetos.get(v.id)), mg };""")
    print("     ", r)
    ok(r and r["tem"] and r["t1"] == [0, 1500, 0] and r["t2"] == [0, 1600, 0], f"no Mover, a peça translúcida anda com o mouse: {r and (r['t1'], r['t2'])}")
    ok(r and r["descartadas"] == 0, f"limpar a prévia não descarta a malha da cena: {r and r['descartadas']}")
    ok(r and r["rc"] == 0, "o fantasma não pega o raio (clique/snap)")
    ok(r and r["mg"] and abs(r["mg"][1] - 1) < 1e-3 and abs(r["mg"][4] + 1) < 1e-3, f"no Girar, o fantasma girado 90° (x vira y): {r and r['mg'] and r['mg'][:6]}")
    r = jsj("""const ed = editor, doc = ed.documento, cena = ed.cena;
      const v = doc.add({ tipo: 'barra', nome: 'viga3', perfil: 'W 250×32,7', inicio: [0, 9000, 0], fim: [2000, 9000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const achar = () => { let fan = null; cena.previa.traverse(x => { if (!fan && x.isMesh && x.material && x.material.userData.compartilhada) fan = x; }); return fan; };
      ed.selecao.definir([v.id]); ed.ativarFerramenta('copiar'); let f = ed.ativa;
      f.onPonto({ ponto: [0, 9000, 0], tela: [0, 0] }); f.onMover({ ponto: [0, 9800, 0], tela: [0, 0] });
      const fa = achar(); const t = fa ? fa.parent.parent.matrix.elements.slice(12, 15).map(Math.round) : null;
      f.cancelar(); ed.limparPrevia();
      // a peça mudou depois de copiada: a área de transferência ficou com a forma de antes — sem fantasma, com o desenho de antes
      doc.alterar(v.id, { fim: [2500, 9000, 0] });
      ed.selecao.limpar(); ed.ativarFerramenta('copiar'); f = ed.ativa;
      f.onPonto({ ponto: [0, 9000, 0], tela: [0, 0] }); f.onMover({ ponto: [0, 9800, 0], tela: [0, 0] });
      const sem = !achar(); let linhas = 0; cena.previa.traverse(x => { if (x.isLine) linhas++; });
      f.cancelar(); ed.limparPrevia();
      return { t, sem, linhas };""")
    print("     ", r)
    ok(r and r["t"] == [0, 800, 0], f"no Copiar, a cópia translúcida segue o mouse: {r and r['t']}")
    ok(r and r["sem"] and r["linhas"] > 0, f"a peça que mudou depois de copiada fica com o desenho de antes (sem fantasma errado): {r and (r['sem'], r['linhas'])}")
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
