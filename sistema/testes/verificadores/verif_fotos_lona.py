# -*- coding: utf-8 -*-
"""As fotos do resumo da obra com e sem a lona (Kaefer, 19/10/2026), no navegador de verdade: com a camada Lona LIGADA
no modelo (o usuário a ligou para ver), a foto "sem a lona" saía com ela — a cena das fotos era montada antes da regra
que a esconde. Aqui: o editor das fotos (?render=1) tira "sem" e "com" no mesmo ângulo e as duas têm de diferir; e com
?cobertura=retraida o modelo vem com a cobertura retrátil empilhada na ponta e não se grava."""
import base64, io, json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_cobertura_movel import PAR, _modelo
from nucleo3d import cobertura_movel as CM
from PIL import Image, ImageChops, ImageStat
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fotos_lona_")
PASTA = os.path.join(DADOS, "quadra")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Quadra", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-19T00:00:00", "alterado": "2026-10-19T00:00:00", "dados": None,
           "analise_parametros": dict(PAR, cobertura_movel=True), "cobertura_movel_vista": "aberta"},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
doc = _modelo()
CM.aplicar(doc, PAR, "aberta", lona=True)
doc.camadas["Lona"].visivel = True                       # a situação do defeito: a camada ligada no modelo
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
ANTES = os.path.getmtime(os.path.join(PASTA, "modelo.json"))

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fotos_lona_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1200, height=800, deviceScaleFactor=1, mobile=False)

    def js(e): return aba.avaliar(e)
    def esperar(cond, limite=60.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if js(cond): return True
            except Exception:
                pass
            aba.drenar(0.3)
        return False
    def erros(onde):
        e = [m for m in aba.console if m[0] in ("error", "excecao")]
        aba.console.clear()
        ok(not e, f"{onde}: sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
    def fotos(pedidos):
        r = aba.cmd("Runtime.evaluate", expression="window.__render(%s)" % json.dumps(pedidos), returnByValue=True,
                    awaitPromise=True)
        return {f["nome"]: Image.open(io.BytesIO(base64.b64decode(f["imagem"].split(",", 1)[1]))).convert("L")
                for f in r["result"]["value"]}
    def diferenca(a, b):
        return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]

    # 1) aberta: "sem" e "com" a lona no mesmo ângulo — com a camada ligada, as duas saíam iguais
    aba.cmd("Page.navigate", url=f"http://127.0.0.1:{PORTA}/editor?projeto=quadra&render=1")
    ok(esperar("window.__renderPronto === true"), "o editor das fotos ficou pronto")
    f = fotos([{"nome": "sem", "angulo": "aerea_frente"}, {"nome": "com", "angulo": "aerea_frente+telhas"},
               {"nome": "sem2", "angulo": "aerea_frente"}])
    d_com, d_sem = diferenca(f["sem"], f["com"]), diferenca(f["sem"], f["sem2"])
    ok(d_com > 4 * max(d_sem, 0.5), f"a foto com a lona difere da sem (diferença média {d_com:.2f} × {d_sem:.2f} entre duas sem)")
    erros("fotos da aberta")

    # 2) ?cobertura=retraida: as tesouras empilhadas nos 2 m da ponta, e essa página não grava
    aba.cmd("Page.navigate", url=f"http://127.0.0.1:{PORTA}/editor?projeto=quadra&render=1&cobertura=retraida")
    ok(esperar("window.__renderPronto === true"), "o editor das fotos da retraída ficou pronto")
    ys = json.loads(js("JSON.stringify([...editor.documento.entidades.values()].filter(e => e.atributos && e.atributos.elemento"
                       " === 'trelica').map(e => [e.inicio[1], e.fim[1]]).flat())") or "[]")
    ok(ys and max(ys) <= 2001 and min(ys) >= -1, f"a retraída veio empilhada na ponta (y {min(ys or [0]):.0f} a {max(ys or [0]):.0f})")
    recusou = js("editor.api ? editor.api.salvarModeloDoProjeto('quadra', {entidades: []}).then(() => 'gravou', () => 'recusou') : 'sem api'")
    ok(recusou == "recusou", f"a página da retraída recusa gravar o modelo ({recusou})")
    time.sleep(1)
    ok(os.path.getmtime(os.path.join(PASTA, "modelo.json")) == ANTES, "o modelo do disco ficou como estava (aberto)")
    f = fotos([{"nome": "sem", "angulo": "aerea_frente"}, {"nome": "com", "angulo": "aerea_frente+telhas"}])
    ok(diferenca(f["sem"], f["com"]) > 1.0, "na retraída a foto com a lona também difere da sem")
    erros("fotos da retraída")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
