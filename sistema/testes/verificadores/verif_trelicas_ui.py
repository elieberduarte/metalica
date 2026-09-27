# -*- coding: utf-8 -*-
"""Tela Treliças lidas (/trelicas): o índice por família com o ponto das que têm algo a conferir,
a elevação do projeto ao lado do bloco lido (lado a lado e uma sobre a outra), o filtro "só as
que têm algo a conferir", a tabela de onde cada cópia entrou com o atalho para o 3D — e o 3D
destacando o bloco pela URL (destacar=peca:…). Dados sintéticos: duas elevações, uma a conferir."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_trelicasui_")
PASTA = os.path.join(DADOS, "posto")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Posto de teste", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-27T00:00:00", "alterado": "2026-09-27T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def elevacao(nome, qtd, no_modelo, L, dif):
    """uma treliça de 4 painéis (banzos, montantes, diagonais) e o desenho dela como o projetista fez"""
    membros = [["banzo", 0, 0, L, 0, 1], ["banzo", 0, 1000, L, 1000, 1]]
    for k in range(5):
        membros.append(["montante", L * k // 4, 0, L * k // 4, 1000, 0])
    for k in range(4):
        membros.append(["diagonal", L * k // 4, 0 if k % 2 else 1000, L * (k + 1) // 4, 1000 if k % 2 else 0, 0])
    desenho = [{"t": "l", "p": [b[1], b[2] - 40, b[3], b[4] - 40]} for b in membros] + \
              [{"t": "l", "p": [b[1], b[2] + 40, b[3], b[4] + 40]} for b in membros if b[0] == "banzo"] + \
              [{"t": "x", "p": [0, -700], "s": "%s - %dX" % (nome, qtd), "h": 250, "g": 0},
               {"t": "x", "p": [0, -350], "s": "BANZO U150X70X4,75", "h": 100, "g": 0},
               {"t": "a", "c": [L // 2, -3000], "r": 3500, "i": 60, "f": 120},
               {"t": "c", "c": [L, 1200], "r": 80}]
    colocadas = [{"conjunto": "%s#%d" % (nome, k + 1), "vao": L + dif, "elevacao": L, "dif": dif, "onde": "eixo %d / entre A e B" % (k + 1),
                  "ponto": [k * 6000, 2500], "deitada": False, "a_conferir": abs(dif) > 200} for k in range(no_modelo)]
    pend = []
    if no_modelo != qtd:
        pend.append("o título pede %d, o modelo tem %d" % (qtd, no_modelo))
    if abs(dif) > 200:
        pend.append("%d cópia(s) com mais de 20 cm de diferença entre a elevação e o vão" % no_modelo)
    return {"nome": nome, "familia": nome.split()[0], "qtd_projeto": qtd, "no_modelo": no_modelo, "comprimento": L, "altura": 1000,
            "banzo": "U 150×70×4,75", "alma": 'L 1"×1/8"', "alma_mult": 2, "membros": membros, "marcas_terca": [0, L],
            "contagem_membros": {"banzo": 2, "montante": 5, "diagonal": 4}, "avisos": ["%s: leitura de teste." % nome],
            "colocadas": colocadas, "pendencias": pend, "situacao": "conferir" if pend else "ok", "desenho": desenho}


json.dump({"desenho": "desenho", "montado_em": "27/09/2026 00:00",
           "trelicas": [elevacao("TESOURA 1", 2, 2, 8000, 20), elevacao("TRANSIÇÃO 14", 1, 1, 12000, 350)]},
          open(os.path.join(PASTA, "trelicas-lidas.json"), "w", encoding="utf-8"), ensure_ascii=False)
# o modelo: as duas cópias da TESOURA 1 e a TRANSIÇÃO 14, como blocos (origem.peca)
doc = Documento()
for conj, y in (("TESOURA 1#1", 0.0), ("TESOURA 1#2", 6000.0), ("TRANSIÇÃO 14#1", 12000.0)):
    for z in (6000.0, 7000.0):
        b = Barra(nome="U 150×70×4,75", inicio=(0.0, y, z), fim=(8000.0, y, z), perfil="U 150×70×4,75", papel="banzo")
        b.atributos = {"origem": {"peca": conj, "planta": conj.split("#")[0]}}
        doc.add(b)
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def foto(aba, nome):
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_trelicasui_")
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
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/trelicas?projeto=posto", limite=30)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("document.body.dataset.pronto === '1'"): aba.drenar(0.3)
    resumo = aba.avaliar("document.querySelector('#resumo').textContent") or ""
    ok("2 elevações lidas" in resumo and "1 com algo a conferir" in resumo, "o resumo do índice: " + resumo)
    ok(aba.avaliar("document.querySelector('#nome-projeto').textContent") == "Posto de teste", "o nome do projeto no topo")
    h2 = aba.avaliar("document.querySelector('.detalhe h2').textContent") or ""
    ok(h2.startswith("TRANSIÇÃO 14"), "abre na primeira que tem algo a conferir: " + h2)
    ok(aba.avaliar("document.querySelectorAll('#lista .pt.conferir').length") == 1, "um ponto laranja no índice")
    pend = aba.avaliar("(document.querySelector('.pendencias') || {}).textContent || ''") or ""
    ok("mais de 20 cm" in pend, "a caixa do que conferir: " + pend[:90])
    n_svg = aba.avaliar("document.querySelectorAll('svg.elev').length")
    n_orig = aba.avaliar("document.querySelectorAll('svg.elev.projeto .orig').length") or 0
    n_lido = aba.avaliar("document.querySelectorAll('svg.elev.lido line.banzo, svg.elev.lido line.montante, svg.elev.lido line.diagonal').length")
    n_tx = aba.avaliar("document.querySelectorAll('svg.elev.projeto .orig-tx').length")
    ok(n_svg == 2 and n_orig >= 15 and n_lido == 11 and n_tx == 2,
       f"lado a lado: o desenho do projeto ({n_orig} traços, {n_tx} textos) e o bloco lido ({n_lido} barras)")
    vb = aba.avaliar("[...document.querySelectorAll('svg.elev')].map(s => s.getAttribute('viewBox'))") or []
    ok(len(vb) == 2 and vb[0] == vb[1], "as duas figuras na mesma escala e posição")
    linha = aba.avaliar("[...document.querySelectorAll('table.tab tr.conferir td')].map(t => t.textContent).join(' | ')") or ""
    ok("+0,35 m" in linha and "eixo 1 / entre A e B" in linha, "a cópia que não cabe, pelos eixos: " + linha[:120])
    href = aba.avaliar("document.querySelector('table.tab a').getAttribute('href')") or ""
    ok("destacar=peca%3ATRANSI%C3%87%C3%83O%2014%231" in href, "o atalho para o 3D leva a cópia: " + href)
    foto(aba, "_trelicas.png")
    aba.avaliar("[...document.querySelectorAll('.caixa h3 .acoes button')].find(b => b.textContent === 'Uma sobre a outra').click(); 1")
    aba.drenar(0.3)
    ok(aba.avaliar("document.querySelectorAll('svg.elev').length") == 1 and aba.avaliar("!!document.querySelector('svg.elev.sobreposto line.banzo')"),
       "uma sobre a outra: uma figura, o desenho apagado com as barras por cima")
    aba.avaliar("document.querySelector('#so-conferir').click(); 1")
    aba.drenar(0.2)
    ok(aba.avaliar("document.querySelectorAll('#lista button').length") == 1, "o filtro deixa só as que têm algo a conferir")
    aba.avaliar("document.querySelector('#so-conferir').click(); document.querySelector('#lista button[data-peca=\"TESOURA 1\"]').click(); 1")
    aba.drenar(0.3)
    h2 = aba.avaliar("document.querySelector('.detalhe h2').textContent") or ""
    ok(h2.startswith("TESOURA 1") and "peca=TESOURA+1" in (aba.avaliar("location.search") or ""), "clicar no índice troca a elevação e a URL: " + h2)
    ok(aba.avaliar("!!document.querySelector('.tudo-ok')") and aba.avaliar("document.querySelectorAll('table.tab tr.conferir').length") == 0,
       "a que cabe fica sem pendência")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
    # o 3D destaca o bloco pela URL (todas as cópias pelo nome)
    aba.console.clear()
    aba.navegar(base + "/editor?projeto=posto&destacar=" + "peca%3ATESOURA%201", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.selecao && window.editor.selecao.ids.size > 0"): aba.drenar(0.5)
    n_sel = aba.avaliar("window.editor.selecao.ids.size") or 0
    ok(n_sel == 4, f"o 3D destaca as duas cópias da TESOURA 1 ({n_sel} barras, esperado 4)")
    n_menu = aba.avaliar("!!document.querySelector('[data-acao=trelicas-lidas]')")
    ok(n_menu, "Ver → Treliças lidas… no menu do 3D")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console do 3D: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
