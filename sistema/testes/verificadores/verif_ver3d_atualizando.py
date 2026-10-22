# -*- coding: utf-8 -*-
"""O modo ver atualizando o 3D com a barra de andamento (usuário, 19/10, no Mercado: "conseguimos colocar uma barrinha de
carregamento quando a estrutura está atualizando o modelo?"). No navegador de verdade: o modo ver abre um modelo grande; o
modelo muda no disco; ao abrir de novo, ele mostra o anterior com "o modelo mudou: atualizando o 3D" e agora a barra padrão
(web/progresso.js) ao lado, com a etapa do servidor; quando a versão nova fica pronta, troca sozinho e a barra some."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_veratu_")
PASTA = os.path.join(DADOS, "veratu")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Ver atualizando", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))


def modelo(n):
    doc = Documento()
    for i in range(n):
        x, y = (i % 60) * 1000.0, (i // 60) * 1000.0
        doc.add(Barra(nome="b%d" % i, inicio=(x, y, 0), fim=(x, y, 3000), perfil="U 100×50×3,00 (FF)", papel="pilar"))
    return doc.dict()


json.dump(modelo(6000), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_veratu_")
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
    URL = f"http://localhost:{PORTA}/visor3d/ver3d.html?projeto=veratu"

    def esperar(cond, limite=120.0, passo=0.3):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(passo)
        return False
    aba.navegar(URL, limite=120)
    ok(esperar("!!window.ver3dPronto", 180), "o modo ver abriu o modelo (o 3D leve feito)")
    n0 = aba.avaliar("window.visor && window.visor.nPecas")
    # o modelo muda no disco (como quando o editor ou um script grava)
    time.sleep(1.1)
    json.dump(modelo(5000), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    aba.console.clear()
    aba.navegar(URL, limite=120)
    ok(esperar("!!window.ver3dPronto && /atualizando o 3D/i.test(document.getElementById('situacao').textContent)", 60, 0.1),
       "abriu o anterior com \"Atualizando o 3D\" no aviso do rodapé")
    viu_barra = esperar("!!document.querySelector('.barra-andamento[data-tarefa=\"3d-leve\"]')", 10, 0.1)
    ok(viu_barra, "a barra de andamento aparece ao lado do aviso")
    if viu_barra:
        txt = aba.avaliar("document.querySelector('.barra-andamento').title || ''")
        print("       barra:", txt)
        ok("Atualizando o 3D" in txt, "a barra diz o que está fazendo")
        # 21/10 (usuário, print do Sesi: "corrigir essas mensagens em duas linhas para ficarem em uma linha apenas e
        # retirar esses textos duplicados"): o aviso dizia "o modelo mudou: atualizando o 3D, troca sozinho…" e a barra,
        # na linha de cima, "Atualizando o 3D: lendo o modelo gravado". Agora uma linha: o trilho e o % e, ao lado, o
        # aviso com a etapa, dita uma vez só
        esperar("/ · \\d+ s$/.test(document.getElementById('situacao').textContent)", 15, 0.2)
        aviso = aba.avaliar("document.getElementById('situacao').textContent")
        print("       aviso:", aviso)
        ok(aviso.lower().count("atualizando") == 1 and "troca sozinho" not in aviso and aviso.startswith("Modo ver · "),
           "o aviso diz a etapa uma vez só (sem o texto repetido)")
        barras = aba.avaliar("[...document.querySelectorAll('.barra-andamento')].map(b => b.dataset.tarefa + ' | ' + b.textContent)")
        print("       barras:", barras)
        ok(aba.avaliar("!document.querySelector('.barra-andamento[data-tarefa=\"3d-leve\"] .barra-andamento-texto')"),
           "a barra não repete o texto (só o trilho e o %)")
        # 19/10 (o usuário: "é esse que ficou escondido atrás do reanalisar estrutura?"): a barra entrava no fluxo da
        # página depois do #situacao (que é fixo no rodapé) e subia para o canto de cima, atrás dos botões. Ela fica no
        # rodapé, na linha do aviso, e não cobre nenhum botão
        pos = aba.avaliar("""(() => { const b = document.querySelector('.barra-andamento').getBoundingClientRect();
            const s = document.getElementById('situacao').getBoundingClientRect();
            const bot = [...document.querySelectorAll('button')].filter(x => x.offsetParent).map(x => x.getBoundingClientRect());
            const cobre = bot.some(r => b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top);
            return {topo: b.top, base: b.bottom, esq: b.left, dir: b.right, alt: innerHeight,
                    sit_topo: s.top, sit_base: s.bottom, sit_esq: s.left, sit_alt: s.height, cobre}; })()""")
        print("       posição:", pos)
        ok(pos["topo"] > pos["alt"] - 60 and pos["esq"] < 40, "a barra fica no rodapé (não no alto da tela)")
        meio_b, meio_s = (pos["topo"] + pos["base"]) / 2, (pos["sit_topo"] + pos["sit_base"]) / 2
        ok(abs(meio_b - meio_s) <= 4 and pos["sit_alt"] <= 20,
           "a barra e o aviso numa linha só (o aviso não quebra)")
        ok(pos["dir"] <= pos["sit_esq"], "o aviso começa depois da barra (sem um por cima do outro)")
        ok(not pos["cobre"], "a barra não fica por trás de nenhum botão")
    # a versão nova fica pronta: a página troca sozinha (recarrega) com as peças novas, sem a barra
    ok(esperar("!!window.ver3dPronto && window.visor && window.visor.nPecas === 5000 && !document.querySelector('.barra-andamento')", 120),
       f"trocou sozinho para a versão nova e a barra sumiu (antes {n0} peças)")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
