# -*- coding: utf-8 -*-
"""Desempenho das ferramentas novas do editor 3D num modelo grande (o PRATI CD, ~27 mil peças), 14–15/10/2026.

Abre uma CÓPIA do modelo (o projeto original não é tocado) num servidor próprio, com o Chrome sem tela, e mede dentro da
página o tempo de cada coisa que roda a cada movimento do mouse ou a cada comando: o snap (com pontos lembrados), o Tab
(todas as peças sob o cursor), o clique, a caixa de corte, o fantasma e a prévia do Mover, o menu do botão direito, as
alças, ocultar/mostrar. Imprime a tabela e falha quando o que roda a cada movimento do mouse passa de LIMITE_MOUSE ms.

Uso: python medir_editor_prati.py [pasta do projeto]   (padrão: Documentos\\Metálica\\prati-cd-metálica)
"""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

ORIGEM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica", "prati-cd-metálica")
LIMITE_MOUSE = 60      # ms: o que roda a cada movimento do mouse (snap, Tab, alças, prévia)
if not os.path.exists(os.path.join(ORIGEM, "modelo.json")):
    print("sem o modelo em", ORIGEM); sys.exit(2)

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_prati_")
PASTA = os.path.join(DADOS, "pr")
os.makedirs(PASTA)
for f in ("projeto.json", "modelo.json"):
    shutil.copy2(os.path.join(ORIGEM, f), os.path.join(PASTA, f))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="medir_prati_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    t0 = time.time()
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=pr", limite=300)
    while time.time() - t0 < 400 and not aba.avaliar("!!(window.editor && editor.documento && editor.documento.entidades.size > 1000 && editor.cena.objetos.size > 1000)"):
        aba.drenar(1)
    print(f"  abriu em {time.time() - t0:.0f} s:", aba.avaliar("JSON.stringify({ pecas: editor.documento.entidades.size, objetos: editor.cena.objetos.size, lote: !!editor.cena.lote })"))
    t1 = time.time()
    while time.time() - t1 < 120 and not aba.avaliar("!!editor.inferencia.aquecido"):
        aba.drenar(0.5)
    print(f"  snap aquecido em segundo plano em {time.time() - t1:.1f} s depois de abrir:", aba.avaliar("!!editor.inferencia.aquecido"))
    aba.drenar(1)
    r = aba.avaliar("""(async () => {
      const ed = editor, doc = ed.documento, inf = ed.inferencia, sel = ed.selecao, cena = ed.cena;
      const mc = await import('/editor3d/modulos/menu_contexto.js'), cx = await import('/editor3d/modulos/caixa_corte.js');
      const C = await import('/editor3d/ferramentas/_comum.js');
      ed.camera.zoomExtensao(); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      await new Promise(r => setTimeout(r, 500));
      const W = ed.camera.largura, H = ed.camera.altura;
      const pts = []; for (let i = 0; i < 25; i++) pts.push([W * (0.2 + 0.6 * ((i * 7) % 25) / 25), H * (0.25 + 0.5 * ((i * 11) % 25) / 25)]);
      const medir = (f, n = pts.length) => { const t = []; for (let i = 0; i < n; i++) { const a = performance.now(); f(pts[i % pts.length], i); t.push(performance.now() - a); }
        t.sort((x, y) => x - y); return { med: +(t.reduce((s, x) => s + x, 0) / t.length).toFixed(1), p90: +t[Math.floor(t.length * 0.9)].toFixed(1), max: +t[t.length - 1].toFixed(1) }; };
      const out = {};
      ed.ativarFerramenta('linha');
      inf.limparAncora();
      // a grade da tela (15/10) é montada em segundo plano quando a câmera para; aqui, de uma vez, medindo
      let ag = performance.now(); inf.prepararGrade(); out.grade_montar = +(performance.now() - ag).toFixed(1);
      out.grade_sempre = inf._grade ? inf._grade.sempre.length : -1;
      out.snap_aquecendo = medir(([x, y]) => inf.resolver(x, y, {}));
      out.snap_sem_ancora = medir(([x, y]) => inf.resolver(x, y, {}));
      // o snap sem a grade (a varredura inteira, enquanto ela não está pronta); o ponto achado tem de ser o mesmo
      inf.semGrade = true;
      out.snap_sem_grade = medir(([x, y]) => inf.resolver(x, y, {}));
      inf.semGrade = false;
      const chave = (r) => [r.tipoSnap, r.entidade, ...r.ponto.map(v => Math.round(v))].join('|');
      const dif = [];
      const compara = () => {
        for (let i = 0; i < 300; i++) {
          const x = W * (0.03 + 0.94 * ((i * 37) % 300) / 300), y = H * (0.05 + 0.9 * ((i * 53) % 300) / 300);
          inf.semGrade = true; const a = chave(inf.resolver(x, y, {}));
          inf.semGrade = false; const b = chave(inf.resolver(x, y, {}));
          if (a !== b) dif.push([Math.round(x), Math.round(y), a, b]);
        }
      };
      compara();
      // de perto (a esfera perto da câmera, fora do meio da tela, cresce na perspectiva)
      const b0 = [...doc.entidades.values()].filter(e => e.tipo === 'barra')[50], s0 = inf._esferaDe(b0.id, b0);
      ed.camera.enquadrar([[s0.c[0] - 2 * s0.r, s0.c[1] - 2 * s0.r, s0.c[2] - 2 * s0.r], [s0.c[0] + 2 * s0.r, s0.c[1] + 2 * s0.r, s0.c[2] + 2 * s0.r]]);
      ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      inf.prepararGrade();
      compara();
      ed.camera.zoomExtensao(); ed.camera.concluirAnimacao && ed.camera.concluirAnimacao();
      inf.prepararGrade();
      inf.definirAncora([...doc.entidades.values()].find(e => e.tipo === 'barra').inicio);
      compara();
      inf.limparAncora();
      out.grade_diferencas = dif.length;
      out.grade_exemplos = dif.slice(0, 3);
      // onde vai o tempo do snap: o raio da seleção (sob) é a parte fixa; o resto é a varredura dos pontos
      out.snap_so_raio = medir(([x, y]) => { sel.raioEm(x, y); sel.sob(x, y); });
      // três pontos lembrados e uma âncora (o alinhamento entra em todo movimento)
      const barras = [...doc.entidades.values()].filter(e => e.tipo === 'barra');
      inf.definirAncora(barras[0].inicio);
      for (const b of barras.slice(1, 4)) inf._lembrar(b.inicio, 'Extremidade');
      out.snap_com_alinhamento = medir(([x, y]) => inf.resolver(x, y, {}));
      inf.limparAncora();
      ed.ativarFerramenta('selecionar');
      out.clique_sob = medir(([x, y]) => sel.sob(x, y));
      out.tab_todosSob = medir(([x, y]) => sel.todosSob(x, y));
      // alças: 30 barras selecionadas, o desenho a cada movimento
      sel.definir(barras.slice(0, 30).map(b => b.id));
      const fs = ed.ativa;
      out.alcas_30 = medir(([x, y]) => { fs._desenharAlcas(); fs._alcaEm([x, y]); });
      // menu do botão direito
      out.menu = medir(([x, y]) => mc.itensDoMenu(ed, x, y), 10);
      sel.definir(barras.slice(0, 30).map(b => b.id));
      // prévia do Mover com 200 peças selecionadas (o fantasma; no desenho em lote, a silhueta)
      const ids200 = barras.slice(0, 200).map(b => b.id);
      sel.definir(ids200);
      ed.ativarFerramenta('mover'); const fm = ed.ativa;
      fm.onPonto({ ponto: barras[0].inicio.slice(), tela: [0, 0] }, {});
      const a0 = performance.now(); fm._fantasmaAtual(); out.fantasma_montar_200 = +(performance.now() - a0).toFixed(1);
      out.fantasma_pecas = fm._fantasma.ids.size;
      out.mover_previa_200 = medir((_, i) => { fm.delta = [i * 10, 0, 0]; fm.desenhar(); });
      fm.cancelar(); ed.limparPrevia();
      // caixa de corte em volta de 10 peças, e tirar
      ed.ativarFerramenta('selecionar');
      sel.definir(barras.slice(0, 10).map(b => b.id));
      let a = performance.now(); cx.caixaNaSelecao(ed); out.caixa_ligar = +(performance.now() - a).toFixed(1);
      out.caixa_fora = doc.foraDaCaixa ? doc.foraDaCaixa.size : 0;
      out.clique_com_caixa = medir(([x, y]) => sel.sob(x, y));
      a = performance.now(); cx.definirCaixaDeCorte(ed, null); out.caixa_tirar = +(performance.now() - a).toFixed(1);
      // ocultar 100 e mostrar
      a = performance.now(); mc.ocultarNaVista(ed, barras.slice(0, 100).map(b => b.id)); out.ocultar_100 = +(performance.now() - a).toFixed(1);
      a = performance.now(); mc.mostrarOcultas(ed); out.mostrar = +(performance.now() - a).toFixed(1);
      return JSON.stringify(out); })()""")
    r = json.loads(r) if r else None
    if not r:
        print("  a medição não voltou"); falhas.append("sem medição")
    else:
        for k, v in r.items():
            print(f"  {k:24s} {v}")
        for k in ("snap_sem_ancora", "snap_com_alinhamento", "clique_sob", "tab_todosSob", "alcas_30", "mover_previa_200", "clique_com_caixa"):
            if r[k]["p90"] > LIMITE_MOUSE:
                falhas.append(f"{k}: p90 {r[k]['p90']} ms > {LIMITE_MOUSE} ms")
        if r.get("grade_diferencas"):
            falhas.append(f"a grade do snap achou outro ponto em {r['grade_diferencas']} posições: {r.get('grade_exemplos')}")
        if not r.get("fantasma_pecas"):
            falhas.append("o fantasma do Mover não aparece no desenho em lote")
        if r.get("fantasma_montar_200", 0) > 400:
            falhas.append(f"montar o fantasma levou {r['fantasma_montar_200']} ms")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    if erros: print("  erros no console:", [x[1][:200] for x in erros[:3]])
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
for f in falhas: print("  LENTO ", f)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
