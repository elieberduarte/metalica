# -*- coding: utf-8 -*-
"""O rodapé do CAD 2D na tela dividida e a versão como marca d'água (usuário, 27/10, prints do Sesi Chapecó em 2D + 3D:
"os textos do rodapé estão ficando sobrepostos, acho que poderia tirar essa quantidade de textos (Clique seleciona (…))
isso é intuitivo" e "tirar essa versão desse menu e deixar isso como uma marca d'água no canto inferior direito, para
aparecer em todas as telas"). No navegador de verdade, na largura do quadro 2D da tela dividida e numa mais estreita:
  A. com a Selecionar, o rodapé não mostra o texto longo "Clique seleciona (…)"; ele fica no balão do botão;
  B. a dica, a barra de andamento e a caixa COMANDO não ficam uma por cima da outra — nem com uma dica longa (quem
     encolhe é a dica, com reticências; o trilho da barra não passa por cima do que vem ao lado);
  C. a versão não está no rodapé: é a marca d'água no canto de baixo à direita, acima do rodapé, sem pegar o clique;
     em outra tela (o modo ver, que não trazia o versao.js) também; na tela dividida só uma, na janela de fora."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_rodape_cad_")
PASTA = os.path.join(DADOS, "obra-rodape")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra rodapé", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-27T00:00:00", "alterado": "2026-10-27T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
d = Desenho(nome="Rodapé", escala=10.0)
d.add(Linha(id="l1", a=(0, 0), b=(1000, 0)))
json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", "rodape.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_rodape_cad_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# os pedaços do rodapé que não podem se cobrir (o que existir e estiver visível)
SOBREPOSTOS = """(() => {
  const r = document.querySelector('.rodape');
  const pecas = [...r.children].filter(e => e.offsetParent && e.getBoundingClientRect().width > 0);
  const caixas = pecas.map(e => {
    // a caixa do que se vê: o texto que vaza do elemento também conta
    const b = e.getBoundingClientRect();
    const larg = Math.max(b.width, e.scrollWidth && getComputedStyle(e).overflow === 'visible' ? e.scrollWidth : 0);
    return { nome: e.id || e.className, esq: b.left, dir: b.left + larg };
  });
  const cobre = [];
  for (let i = 0; i < caixas.length; i++) for (let j = i + 1; j < caixas.length; j++) {
    const a = caixas[i], c = caixas[j];
    if (a.esq < c.dir - 1 && c.esq < a.dir - 1) cobre.push(a.nome + ' × ' + c.nome);
  }
  const rr = r.getBoundingClientRect();
  const fora = caixas.filter(c => c.dir > rr.right + 1).map(c => c.nome);
  return JSON.stringify({ cobre, fora, caixas });
})()"""

# a marca d'água da versão (versao.js)
MARCA = """(() => {
  const e = document.getElementById('versao-programa');
  if (!e || !e.isConnected) return JSON.stringify({ existe: false });
  const b = e.getBoundingClientRect(), cs = getComputedStyle(e), r = document.querySelector('.rodape');
  return JSON.stringify({ existe: true, no_rodape: !!(r && r.contains(e)), fixa: cs.position === 'fixed', clique: cs.pointerEvents !== 'none',
    dir: Math.round(b.right), base: Math.round(b.bottom), larg: innerWidth, alt: innerHeight,
    topo_rodape: r ? Math.round(r.getBoundingClientRect().top) : innerHeight, texto: e.textContent });
})()"""

try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                if aba.avaliar(f"!!({cond})"): return True
            except Exception:
                pass
            aba.drenar(0.2)
        return False

    # o quadro 2D da tela dividida do print tem ~1000 px; e uma janela menor, com o quadro de ~860 px
    for largura in (1000, 860):
        aba.cmd("Emulation.setDeviceMetricsOverride", width=largura, height=900, deviceScaleFactor=1, mobile=False)
        aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-rodape&desenho=rodape", limite=60)
        ok(esperar("window.cad && window.cad.doc && (document.getElementById('versao-programa') || {}).isConnected", 40),
           f"[{largura}px] o CAD abriu com a versão")
        # o rótulo da versão como no servidor de desenvolvimento do print (o mais comprido) e uma barra de andamento do
        # progresso.js no rodapé (ela entra logo depois da dica)
        aba.avaliar("""(() => { document.getElementById('versao-programa').textContent = 'v0.9.1 + 173 dev · 6bc2f40* (27/10 08:15)';
            window.__pararBarra = window.metalicaProgresso.acompanhar({ tarefa: 'teste-rodape', rotulo: 'Detalhando',
              onde: document.getElementById('dica') }); return 1; })()""")
        # a Selecionar ativa (como depois do Esc), sem outra mensagem por cima
        aba.avaliar("window.cad.ativarFerramenta('selecionar'), window.cad.dica(window.cad.ferramenta.constructor.dica), 1")
        aba.drenar(0.3)
        dica = aba.avaliar("document.getElementById('dica').textContent")
        ok("Clique seleciona" not in dica, f"[{largura}px] A. com a Selecionar, o rodapé sem o texto longo ({dica[:60]!r})")
        titulo = aba.avaliar("document.querySelector('[data-ferramenta=selecionar]').title")
        ok("Shift soma" in titulo and "Alt+clique" in titulo, f"[{largura}px] A. o como usar fica no balão do botão Selecionar")
        r = json.loads(aba.avaliar(SOBREPOSTOS))
        ok(not r["cobre"] and not r["fora"], f"[{largura}px] B. nada se cobre no rodapé (cobre: {r['cobre']}, fora: {r['fora']})")
        # uma dica longa de outra ferramenta (ou uma mensagem) também não passa por cima da versão
        aba.avaliar("window.cad.dica('Uma mensagem bem comprida no rodapé para ver quem cede lugar: ' + 'texto '.repeat(60)), 1")
        aba.drenar(0.3)
        r = json.loads(aba.avaliar(SOBREPOSTOS))
        ok(not r["cobre"] and not r["fora"], f"[{largura}px] B. com a dica longa, nada se cobre (cobre: {r['cobre']}, fora: {r['fora']})")
        if r["cobre"] or r["fora"]: print("       caixas:", r["caixas"])
        m = json.loads(aba.avaliar(MARCA))
        print("       marca:", m)
        ok(m["existe"] and not m["no_rodape"], f"[{largura}px] C. a versão não está no rodapé")
        ok(m["existe"] and m["fixa"] and m["dir"] >= m["larg"] - 20 and m["base"] <= m["topo_rodape"] + 1 and m["base"] > m["alt"] - 60,
           f"[{largura}px] C. a versão é a marca d'água no canto de baixo à direita, logo acima do rodapé")
        ok(m["existe"] and not m["clique"], f"[{largura}px] C. a marca d'água não pega o clique")
    # outra tela, que não trazia o versao.js: o modo ver do 3D (o vivo.js o carrega)
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto=obra-rodape", limite=60)
    ok(esperar("(document.getElementById('versao-programa') || {}).isConnected && document.getElementById('versao-programa').textContent.length > 2", 30),
       "C. o modo ver também mostra a marca d'água")
    m = json.loads(aba.avaliar(MARCA))
    ok(m["existe"] and m["fixa"] and m["dir"] >= m["larg"] - 20 and m["base"] > m["alt"] - 30, f"C. no modo ver, no canto de baixo à direita ({m})")
    # a tela dividida: a marca uma vez só, na janela de fora; os quadros (o 2D e o 3D) sem a deles
    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=obra-rodape&desenho=rodape", limite=60)
    ok(esperar("(document.getElementById('versao-programa') || {}).isConnected && document.getElementById('f2d').contentWindow.cad", 40),
       "C. a tela dividida abriu (o 2D carregado) com a marca d'água")
    aba.drenar(2.0)
    nos_quadros = aba.avaliar("""[...document.querySelectorAll('iframe')].filter(f => { try { return !!f.contentDocument.getElementById('versao-programa'); }
        catch (e) { return false; } }).map(f => f.id)""")
    ok(nos_quadros == [], f"C. na tela dividida, os quadros sem a marca deles (com marca: {nos_quadros})")
    m = json.loads(aba.avaliar(MARCA))
    ok(m["existe"] and m["dir"] >= m["larg"] - 20 and m["base"] > m["alt"] - 30, f"C. na tela dividida, a marca no canto de baixo à direita ({m})")
    # o modo ver do projeto de teste não tem modelo 3D: os 404 dele (e o do favicon) são esperados
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and not str(x[1]).startswith("Failed to load resource")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
