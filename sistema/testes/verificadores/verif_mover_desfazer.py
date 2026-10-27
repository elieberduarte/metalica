# -*- coding: utf-8 -*-
"""Ctrl+Z no meio do Mover (Posto, 27/10: "movimentei essa peça do projeto do posto, porém depois de deixar ela na posição
correta não consigo selecionar mais"). Depois de mover, o Mover segue ativo e o clique seguinte começa outro movimento da
mesma seleção: o fantasma azul da chapa passa a seguir o mouse. O Ctrl+Z desfazia o movimento de verdade e deixava a
operação e o fantasma na tela — o fantasma parecia a chapa e o clique nele não a pegava.

Agora o desfazer e o refazer do usuário (teclado e setas) soltam antes a operação em andamento, como o Esc; e a dica
depois de mover diz como voltar a selecionar. No modelo grande (em lote, como o Posto de 22 mil peças) e no pequeno."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

#: as formas de modelo: o grande passa do LIMITE_LOTE (1500) e é desenhado em lote, como o Posto (piso a 6 m, longe da origem)
SITUACOES = [("grande", 1800), ("pequeno", 10)]

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_mover_desfazer_")
for nome, n in SITUACOES:
    pasta = os.path.join(DADOS, nome)
    os.makedirs(pasta)
    json.dump({"formato": 1, "nome": "Mover " + nome, "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
               "criado": "2026-10-27T00:00:00", "alterado": "2026-10-27T00:00:00", "dados": None},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
    doc = Documento().dict()
    ents = []
    for i in range(n):
        ents.append({"id": "b%04d" % i, "tipo": "barra", "nome": "terça", "perfil": "U150X50X2.28", "camada": "Estrutura",
                     "inicio": [30000 + (i % 40) * 1500, 19000 + (i // 40) * 1500, 6000], "fim": [30000 + (i % 40) * 1500, 19000 + (i // 40) * 1500 + 1000, 6000],
                     "rotacao": 0, "papel": "viga", "atributos": {}})
    # a chapa do Posto: Gusset G1, 4,76 × 100 × 300, em pé
    ents.append({"id": "gusset", "tipo": "chapa", "nome": "Gusset G1", "camada": "Chapas", "origem": [30662.76, 19550.68, 6102.0],
                 "eixo_x": [1, 0, 0], "eixo_y": [0, 0, 1], "contorno": [[0, 0], [300, 0], [300, 100], [0, 100]],
                 "espessura": 4.76, "centrada": True, "furos": [], "aco": "ASTM A36", "atributos": {}})
    doc["entidades"] = ents
    json.dump(doc, open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mover_")
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

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    def tecla(k, code, mods=0):
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.3)

    ESTADO = """const ed = editor, f = ed.ativa; let fantasma = 0;
      ed.cena.previa.traverse(x => { if (x.isMesh && x.material && x.material.userData.compartilhada) fantasma++; });
      const g = ed.documento.get('gusset');
      return { ferr: ed.idAtiva, base: !!(f && f.base), fantasma, origem: g.origem.map(Math.round), lote: ed.cena.emLote,
               dica: (document.querySelector('#dica, .dica, [data-dica]') || {}).textContent || '' };"""

    for nome, n in SITUACOES:
        print(f"{nome} ({n + 1} peças)")
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto={nome}", limite=90)
        t0 = time.time()
        while time.time() - t0 < 90 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.get('gusset') && editor.ferramentas && editor.ferramentas.get('mover'))"):
            aba.drenar(0.5)
        aba.drenar(1.0)
        aba.console.clear()
        r = jsj("""const ed = editor; ed.selecao.definir(['gusset']); ed.ativarFerramenta('mover');
          const f = ed.ativa, P = (q) => ({ ponto: q, tela: [0, 0] });
          f.onPonto(P([30662.76, 19550.68, 6102]), {}); f.onPonto(P([30662.76, 19566.68, 6102]), {});      // moveu 16 mm (a posição certa)
          const depois = ed.documento.get('gusset').origem.map(Math.round);
          const dica = ed.el && ed.el.dica ? ed.el.dica.textContent : '';
          // o clique "para selecionar" com o Mover ainda ativo começa outro movimento: o fantasma segue o mouse
          f.onPonto(P([30700, 19560, 6150]), {}); f.onMover(P([31500, 19900, 6150]));
          return { depois, dica };""")
        e = jsj(ESTADO)
        print("     ", r, e)
        ok(r and r["depois"] == [30663, 19567, 6102], f"o Mover levou a chapa à posição certa ({r and r['depois']})")
        ok(e and (e["lote"] if nome == "grande" else not e["lote"]), f"o modelo {nome} {'em lote' if nome == 'grande' else 'peça por peça'} ({e and e['lote']})")
        ok(e and e["base"] and e["fantasma"] > 0, f"o segundo clique começa outro movimento, com o fantasma ({e})")
        tecla("z", 90, 2)                                                       # Ctrl+Z de verdade
        e = jsj(ESTADO)
        print("     ", e)
        ok(e and e["origem"] == [30663, 19551, 6102], f"o Ctrl+Z desfaz o movimento ({e and e['origem']})")
        ok(e and not e["base"] and e["fantasma"] == 0, f"e solta a operação em andamento: sem fantasma na tela ({e})")
        tecla("y", 89, 2)                                                       # Ctrl+Y
        e = jsj(ESTADO)
        ok(e and e["origem"] == [30663, 19567, 6102] and e["fantasma"] == 0 and not e["base"], f"o Ctrl+Y refaz, sem operação pendurada ({e})")
        ok(r and "Esc" in r["dica"] and "selecionar" in r["dica"], f"a dica depois de mover diz como voltar a selecionar ({r and r['dica']!r})")
        # o "*5" e a distância corrigida do próprio Mover desfazem por dentro: continuam funcionando
        r = jsj("""const ed = editor; ed.ativarFerramenta('selecionar'); ed.selecao.definir(['gusset']); ed.ativarFerramenta('mover');
          const f = ed.ativa, P = (q) => ({ ponto: q, tela: [0, 0] });
          f.onPonto(P([0, 0, 0]), {}); f.onPonto(P([0, 0, 100]), {});
          f.onValor('250');
          return ed.documento.get('gusset').origem.map(Math.round);""")
        ok(r == [30663, 19567, 6352], f"a distância digitada depois de mover ainda corrige o último movimento ({r})")
        erros = [m for m in aba.console if m[0] in ("error", "excecao") and "Failed to load resource" not in m[1]]
        ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
        # grava antes de sair: com mudança por gravar, o "sair sem gravar?" do navegador segura a próxima navegação
        aba.avaliar("(async () => { try { await editor.gravarConfirmado(); } catch (e) {} return 1; })()")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
