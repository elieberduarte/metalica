# -*- coding: utf-8 -*-
"""O aviso de versão nova em destaque (21/10, o usuário: "colocar essa mensagem de atualização disponível mais destacada na
tela para os outros usuários"): na tela inicial, a faixa no alto (o título, as novidades das notas, Atualizar agora e
Depois — que esconde por 4 h e volta na versão seguinte); nas telas de trabalho, o botão Atualizar amarelo com o ponto.
A resposta "há versão nova" é simulada no navegador (o fetch de /api/atualizacao e /api/versao). Porta livre, nunca a
8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_aviso_atualizacao_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"nome": "Obra", "tipo": "galpao", "alterado": "2026-10-21T09:00:00"}, open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
# as notas como a release as leva (empacotar/publicar_noite.notas_da_versao: os parágrafos do LEIAME, sem o negrito)
NOTAS = ("(21/10/2026) Obras entre usuários, link de instalação e a obra no terreno do cliente.\n\n"
         "Enviar a obra para outro usuário. No cartão do projeto, Enviar para manda a obra.\n\n"
         "Link de instalação. Na tela das licenças, cada licença tem um link.\n\n"
         "A obra no terreno. O botão Terreno do modo ver põe a imagem.\n\n"
         "IFC com o terreno. Com o terreno à vista, o IFC leva a obra georreferenciada.")
SIMULA = """(() => {
  const original = window.fetch.bind(window);
  window.fetch = (u, o) => {
    const url = typeof u === 'string' ? u : (u && u.url) || '';
    if (url.includes('/api/atualizacao') && !url.includes('instalar'))
      return Promise.resolve(new Response(JSON.stringify({ nova: true, atual: '0.9.0', ultima: '0.9.1', tamanho_mb: 63.1,
        arquivo: 'https://exemplo/instalador.exe', url: 'https://exemplo', notas: %s }), { headers: { 'Content-Type': 'application/json' } }));
    if (url.includes('/api/versao'))
      return original(u, o).then(r => r.json()).then(v => new Response(JSON.stringify(Object.assign(v, { janela: true, instalado: true })),
        { headers: { 'Content-Type': 'application/json' } }));
    return original(u, o);
  };
})();""" % json.dumps(NOTAS)


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.5)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_aviso_atual_")
nav = subprocess.Popen([exe, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1300, height=820, deviceScaleFactor=1, mobile=False)
    aba.cmd("Page.addScriptToEvaluateOnNewDocument", source=SIMULA)
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "!!document.querySelector('main.gerenciador > .atualizacao')"), "a faixa da versão nova aparece")
    ok(aba.avaliar("document.querySelector('main.gerenciador').firstElementChild.classList.contains('atualizacao')"), "no alto da tela (antes dos projetos)")
    ok("Nova versão 0.9.1 disponível" in (aba.avaliar("document.querySelector('.atualizacao-titulo').textContent") or ""), "o título com a versão")
    nov = aba.avaliar("[...document.querySelectorAll('.atualizacao-novidades li')].map(l => l.textContent)") or []
    ok(nov == ["Enviar a obra para outro usuário", "Link de instalação", "A obra no terreno"],
       f"as 3 primeiras novidades das notas — o título de cada parágrafo, depois do resumo ({nov})")
    ok(aba.avaliar("[...document.querySelectorAll('.atualizacao button')].some(b => b.textContent === 'Atualizar agora')"), "o Atualizar agora")
    alto = aba.avaliar("document.querySelector('.atualizacao').getBoundingClientRect().height")
    ok(alto >= 80, f"a faixa tem destaque ({alto:.0f} px de altura)")
    foto(aba, "aviso_atualizacao_1_inicio.png")
    aba.avaliar("document.documentElement.setAttribute('data-tema', 'claro'); 1")
    foto(aba, "aviso_atualizacao_2_inicio_claro.png")
    aba.avaliar("[...document.querySelectorAll('.atualizacao button')].find(b => b.textContent === 'Depois').click(); 1")
    ok(not aba.avaliar("!!document.querySelector('.atualizacao')"), "Depois esconde a faixa")
    aba.navegar(base + "/", limite=60)
    aba.drenar(2)
    ok(not aba.avaliar("!!document.querySelector('.atualizacao')"), "e ela continua escondida depois de reabrir (4 h)")
    aba.avaliar("localStorage.setItem('metalica.atualizacao.depois', JSON.stringify({'0.9.0': Date.now() + 9e9})); 1")
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "!!document.querySelector('.atualizacao')"), "o Depois de outra versão não esconde a versão nova")
    # as telas de trabalho: o botão Atualizar em destaque
    aba.navegar(base + "/catalogo", limite=60)
    ok(esperar(aba, "!!document.getElementById('btn-atualizar')", 20), "nas telas de trabalho, o botão Atualizar")
    est = aba.avaliar("(() => { const b = document.getElementById('btn-atualizar'); const c = getComputedStyle(b); return [c.backgroundColor, b.children.length]; })()") or ["", 0]
    ok(est[0] in ("rgb(230, 187, 82)",) and est[1] >= 1, f"amarelo, com o ponto ({est})")
    foto(aba, "aviso_atualizacao_3_tela.png")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
