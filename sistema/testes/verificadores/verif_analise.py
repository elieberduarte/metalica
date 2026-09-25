# -*- coding: utf-8 -*-
"""Tela do resultado da análise (/analise): lê o cálculo gravado, mostra o resumo, a
situação por tipo e todas as peças; a linha abre as verificações com a conta; o filtro
"só as reprovadas" funciona; o 3D tem o caminho para a tela; projeto sem cálculo avisa.

    python testes/verificadores/verif_analise.py [pasta-do-projeto-com-calculo.json]

Sem argumento, usa o projeto "teste-dwg" da pasta de projetos do usuário, se existir."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

ORIGEM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica", "teste-dwg")
if not os.path.exists(os.path.join(ORIGEM, "calculo.json")):
    print("sem projeto com cálculo em %s: passe a pasta de um projeto calculado" % ORIGEM)
    sys.exit(0)
PORTA = 8801
DADOS = tempfile.mkdtemp(prefix="metalica_analise_")
for nome in ("calc", "vazio"):
    os.makedirs(os.path.join(DADOS, nome))
    for arq in ("projeto.json", "modelo.json") + (("calculo.json",) if nome == "calc" else ()):
        if os.path.exists(os.path.join(ORIGEM, arq)):
            shutil.copy(os.path.join(ORIGEM, arq), os.path.join(DADOS, nome, arq))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


calc = json.load(open(os.path.join(ORIGEM, "calculo.json"), encoding="utf-8"))["resultado"]
n_el = len(calc["elementos"])
n_rep = sum(1 for e in calc["elementos"].values() if not e.get("ok"))
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_analise_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.avaliar("localStorage.setItem('galpao.tema','claro'); 1"); aba.console.clear()

    aba.navegar(base + "/analise?projeto=calc", limite=30)
    ok(esperar(aba, "document.querySelectorAll('#cartoes .cartao-n').length >= 4"), "cartões do resumo")
    linhas = aba.avaliar("document.querySelectorAll('.rolagem tbody tr.linha-peca').length")
    ok(linhas == n_el, f"uma linha por posição verificada: {linhas} de {n_el}")
    ok(aba.avaliar("document.querySelector('#cartoes').textContent.includes('%d')" % n_rep), f"o resumo conta {n_rep} que não passam")
    foto(aba, "_analise_1_resumo.png")
    # a primeira linha é a pior; ao clicar, as verificações com a conta
    aba.avaliar("document.querySelector('.rolagem tbody tr.linha-peca').click(); 1"); aba.drenar(0.5)
    ok(aba.avaliar("document.querySelectorAll('tr.detalhe .verif').length") >= 1, "a linha abre as verificações da peça")
    ok(aba.avaliar("!!document.querySelector('tr.detalhe .verif table sub, tr.detalhe .verif table td')"), "com os passos da conta")
    aba.avaliar("document.querySelector('tr.detalhe').scrollIntoView(); 1"); aba.drenar(0.3)
    foto(aba, "_analise_2_detalhe.png")
    aba.avaliar("[...document.querySelectorAll('tr.detalhe button')].find(b => b.textContent.startsWith('Perfis')).click(); 1")
    ok(esperar(aba, "!!document.querySelector('tr.detalhe .alternativas table, tr.detalhe .alternativas .vazio')", 60), "perfis que servem no lugar")
    # só as reprovadas
    aba.avaliar("const s = document.querySelector('#situacao'); s.value = 'nao'; s.dispatchEvent(new Event('change')); 1"); aba.drenar(0.3)
    vis = aba.avaliar("[...document.querySelectorAll('.rolagem tbody tr.linha-peca')].filter(t => !t.classList.contains('oculta') && !t.closest('.detalhe-peca') && t.closest('section').querySelector('h2').textContent.startsWith('Peças')).length")
    ok(vis == n_rep, f"filtro 'só as reprovadas': {vis} de {n_rep}")
    # tema escuro
    aba.avaliar("document.querySelector('#btn-tema').click(); 1"); aba.drenar(0.3)
    aba.avaliar("window.scrollTo(0, 0); 1"); foto(aba, "_analise_3_escuro.png")
    aba.avaliar("document.querySelector('#btn-tema').click(); 1")
    # tela estreita: sem rolagem horizontal da página
    aba.cmd("Emulation.setDeviceMetricsOverride", width=420, height=900, deviceScaleFactor=1, mobile=False); aba.drenar(0.5)
    ok(aba.avaliar("document.documentElement.scrollWidth <= window.innerWidth + 1"), "tela estreita sem rolagem horizontal da página")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)

    # projeto sem cálculo
    aba.navegar(base + "/analise?projeto=vazio", limite=30)
    ok(esperar(aba, "!document.querySelector('#aviso').hidden && document.querySelector('#aviso').textContent.includes('ainda não tem cálculo')"),
       "projeto sem cálculo avisa como calcular")

    # o 3D leva à tela
    aba.navegar(base + "/editor?projeto=calc", limite=60)
    esperar(aba, "!!window.editor && window.editor.projeto === 'calc'", 60)
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"resultado-analise\"]')"), "menu do 3D tem 'Resultado da análise…'")
    aba.avaliar("window.editor._abrirResultadoDaAnalise(); 1")
    ok(esperar(aba, "location.pathname === '/analise'", 30), "o 3D abre a tela do resultado")
    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
