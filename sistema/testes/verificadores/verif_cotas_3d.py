# -*- coding: utf-8 -*-
"""A cota que acompanha as peças (F20 do levantamento de 14/10/2026): feita com a ferramenta Cotar presa à ponta de uma
viga e a uma chapa, ela se refaz quando a viga anda (Mover) e quando é esticada, com o texto novo; o Ctrl+Z volta a
cota junto; movida sozinha, ela se solta das peças."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cotas_")
PASTA = os.path.join(DADOS, "ct")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Cotas", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
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


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cotas_")
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
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=ct", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("!!(window.editor && editor.ferramentas && editor.ferramentas.get('cotar') && editor.cena.perfil('W 250×32,7'))"):
        aba.drenar(0.5)
    aba.drenar(0.5)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    r = jsj("""const ed = editor, doc = ed.documento;
      const v = doc.add({ tipo: 'barra', nome: 'viga', perfil: 'W 250×32,7', inicio: [0, 0, 0], fim: [2000, 0, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      const ch = doc.add({ tipo: 'chapa', nome: 'CH', camada: 'Chapas', origem: [3000, -100, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 200], [0, 200]], espessura: 10, centrada: true, furos: [], atributos: {} });
      ed.ativarFerramenta('cotar'); const f = ed.ativa;
      // a primeira ponta no canto de cima da ponta do fim da viga; a segunda no canto da chapa
      f.onPonto({ ponto: [2000, 73, 129], entidade: v.id, tipoSnap: 'extremidade', normal: [0, 0, 1], tela: [0, 0] });
      f.onPonto({ ponto: [3000, 100, 5], entidade: ch.id, tipoSnap: 'extremidade', normal: [0, 0, 1], tela: [0, 0] });
      f.criar(300);
      const c = [...doc.entidades.values()].find(e => e.atributos && e.atributos.cota);
      return { v: v.id, ch: ch.id, c: c.id, texto: c.atributos.cota.texto, refs: c.atributos.cota.refs.map(r => r && r.tipo) };""")
    ok(r and r["refs"] == ["barra", "chapa"], f"a cota guarda as peças das duas pontas: {r}")
    V, CH, CT = r["v"], r["ch"], r["c"]
    CO = f"const doc = editor.documento; const c = () => doc.get('{CT}').atributos.cota;"

    # mover a viga 500 em x (o comando do Mover): a ponta presa a ela vai junto, o texto muda
    r = jsj(CO + f"""editor.selecao.definir(['{V}']); editor.ativarFerramenta('mover'); const f = editor.ativa;
      editor.executar(f.comandosPara([500, 0, 0], 0, 'Mover').cmds[0]);
      return {{ a: c().a.map(Math.round), texto: c().texto, nome: doc.get('{CT}').nome }};""")
    ok(r and r["a"] == [2500, 73, 129] and r["texto"] == "516 mm" and r["nome"] == "516 mm",
       f"a viga andou 500: a ponta da cota foi junto e o texto refez (de 1,008 m para 516 mm): {r}")
    # esticar a viga 300 no fim: a ponta presa ao fim acompanha
    r = jsj(CO + f"""const v = doc.get('{V}'); editor.documento.alterar('{V}', {{ fim: [v.fim[0] + 300, 0, 0] }});
      return {{ a: c().a.map(Math.round), texto: c().texto }};""")
    ok(r and r["a"] == [2800, 73, 129], f"a viga esticada 300 no fim: a ponta da cota acompanha: {r}")
    # desfazer o Mover: a cota volta junto
    r = jsj(CO + f"""editor.documento.alterar('{V}', {{ fim: [2500, 0, 0] }}); editor.desfazer();
      return {{ a: c().a.map(Math.round), texto: c().texto, fim: doc.get('{V}').fim }};""")
    ok(r and r["a"] == [2000, 73, 129] and r["texto"] == "1,008 m", f"Ctrl+Z na viga: a cota volta junto: {r}")
    # a cota movida sozinha se solta
    r = jsj(CO + f"""editor.selecao.definir(['{CT}']); editor.ativarFerramenta('mover'); const f = editor.ativa;
      editor.executar(f.comandosPara([0, 0, 200], 0, 'Mover').cmds[0]);
      const solta = !c().refs; editor.documento.alterar('{V}', {{ fim: [1000, 0, 0] }});
      return {{ solta, a: c().a.map(Math.round) }};""")
    ok(r and r["solta"] and r["a"] == [2000, 73, 329], f"a cota movida sozinha se solta das peças (não segue mais a viga): {r}")
    # cópia da viga com a cota (Mover com cópia): a cota copiada segue a viga copiada; a de antes, a viga de antes
    r = jsj("""const ed = editor, doc = ed.documento;
      const v = doc.add({ tipo: 'barra', nome: 'viga2', perfil: 'W 250×32,7', inicio: [0, 5000, 0], fim: [3000, 5000, 0], rotacao: 0, papel: 'viga', camada: 'Estrutura', atributos: {} });
      ed.ativarFerramenta('cotar'); let f = ed.ativa;
      f.onPonto({ ponto: [0, 5073, 129], entidade: v.id, tipoSnap: 'extremidade', normal: [0, 0, 1], tela: [0, 0] });
      f.onPonto({ ponto: [3000, 5073, 129], entidade: v.id, tipoSnap: 'extremidade', normal: [0, 0, 1], tela: [0, 0] });
      f.criar(300);
      const c = [...doc.entidades.values()].filter(e => e.atributos && e.atributos.cota).pop();
      ed.selecao.definir([v.id, c.id]); ed.ativarFerramenta('mover'); f = ed.ativa;
      const r = f.comandosPara([0, 1000, 0], 1, 'Mover'); ed.executar(r.cmds[0]);
      const nv = r.novos.map(id => doc.get(id)).find(e => e.tipo === 'barra'), nc = r.novos.map(id => doc.get(id)).find(e => e.atributos.cota);
      const refs = nc.atributos.cota.refs && nc.atributos.cota.refs.map(x => x && x.id);
      doc.alterar(nv.id, { fim: [3500, 6000, 0] });
      const ct = doc.get(nc.id).atributos.cota, co = doc.get(c.id).atributos.cota;
      // espelhar a viga com a cota (cópia): a cota espelhada se solta
      ed.selecao.definir([v.id, c.id]); ed.ativarFerramenta('espelhar'); ed.ativa.ids = [v.id, c.id];
      const antes = new Set(doc.entidades.keys());
      ed.ativa.aplicar({ p: [0, 4000, 0], n: [0, 1, 0] }, false);
      const ec = [...doc.entidades.values()].find(e => !antes.has(e.id) && e.atributos && e.atributos.cota);
      return { refs, nv: nv.id, copia_b: ct.b.map(Math.round), copia_texto: ct.texto, orig_b: co.b.map(Math.round),
               espelhada: ec ? { refs: ec.atributos.cota.refs, a: ec.atributos.cota.a.map(Math.round) } : null };""")
    ok(r and r["refs"] == [r["nv"], r["nv"]], f"a cota copiada junto fica presa à viga copiada: {r and r['refs']}")
    ok(r and r["copia_b"] == [3500, 6073, 129] and r["copia_texto"] == "3,50 m" and r["orig_b"] == [3000, 5073, 129],
       f"esticar a cópia leva a cota copiada, e a de antes fica: {r}")
    ok(r and r["espelhada"] and r["espelhada"]["refs"] is None and r["espelhada"]["a"] == [0, 2927, 129],
       f"a cota espelhada sai solta, no lugar refletido: {r and r['espelhada']}")
    # a cota da aresta: um clique na aresta (não no canto) e o afastamento — a aresta inteira, presa à peça
    r = jsj("""const ed = editor, doc = ed.documento;
      const ch = doc.add({ tipo: 'chapa', nome: 'CH2', camada: 'Chapas', origem: [0, 8000, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
        contorno: [[0, 0], [200, 0], [200, 100], [0, 100]], espessura: 10, centrada: false, furos: [], atributos: {} });
      ed.ativarFerramenta('cotar'); const f = ed.ativa;
      const antes = new Set(doc.entidades.keys());
      f.onPonto({ ponto: [80, 8000, 10], entidade: ch.id, tipoSnap: 'sobre_aresta', aresta: [[0, 8000, 10], [200, 8000, 10]], normal: [0, 0, 1], tela: [0, 0] });
      const modo = !!f.daAresta && !!f.b;
      f.onPonto({ ponto: [80, 7800, 10], entidade: null, tipoSnap: 'plano_base', normal: [0, 0, 1], tela: [0, 0] });
      const c = [...doc.entidades.values()].find(e => !antes.has(e.id) && e.atributos && e.atributos.cota);
      // Esc cancela a cota da aresta inteira
      f.onPonto({ ponto: [80, 8000, 10], entidade: ch.id, tipoSnap: 'sobre_aresta', aresta: [[0, 8000, 10], [200, 8000, 10]], normal: [0, 0, 1], tela: [0, 0] });
      f.cancelar();
      return { modo, texto: c && c.atributos.cota.texto, a: c && c.atributos.cota.a, b: c && c.atributos.cota.b,
               refs: c && c.atributos.cota.refs.map(x => x && x.id === ch.id), limpo: !f.a && !f.b };""")
    ok(r and r["modo"] and r["texto"] == "200 mm" and r["a"] == [0, 8000, 10] and r["b"] == [200, 8000, 10] and r["refs"] == [True, True],
       f"um clique na aresta e o afastamento: a cota da aresta inteira, presa à chapa: {r}")
    ok(r and r["limpo"], f"o Esc cancela a cota da aresta: {r and r['limpo']}")
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
