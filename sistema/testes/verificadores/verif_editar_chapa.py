# -*- coding: utf-8 -*-
"""Editar chapa (pedido do usuário, 02/10): selecionar a chapa no 3D ou no 2D e abrir o ambiente de edição — isolada
(só a peça) ou no local (com as peças em volta cortadas no plano dela, travadas, como referência) —, com a faixa
EDITANDO … · Concluir · Cancelar; Concluir leva furos e contorno a todas as chapas da posição no 3D e volta; Cancelar
volta sem mexer no 3D."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ec_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c:
        falhas.append(m)


def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))


def furos_p77():
    doc = get("/api/projetos/compressores/modelo")["documento"]
    ch = [e for e in doc["entidades"] if e.get("tipo") == "chapa" and ((e.get("atributos") or {}).get("marcas") or {}).get("posicao") == "P77"]
    return [sorted((round(f.get("x", 0), 1), round(f.get("y", 0), 1)) for f in c["furos"]) for c in ch]


def esperar(aba, cond, limite=90):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(cond):
        aba.drenar(0.5)
    return aba.avaliar(cond)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ec_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos:
            break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"):
        aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    # 1) no 3D: a chapa selecionada mostra Editar isolada / no local
    aba.navegar(base + "/editor?projeto=compressores&destacar=posicao:P77", limite=90)
    esperar(aba, "window.editor && window.editor.selecao && window.editor.selecao.ids.size > 0")
    aba.avaliar("(() => { const ed = window.editor; const id = [...ed.selecao.ids][0]; ed.selecao.definir([id]); ed._agendarPaineis('props'); return 1; })()")
    aba.drenar(1.5)
    botoes = aba.avaliar("[...document.querySelectorAll('.acoes-painel.editar-chapa button')].map(b => b.textContent)")
    ok(botoes == ["Editar isolada", "Editar no local"], f"3D: a chapa selecionada mostra os botões de edição ({botoes})")
    # 2) no local: o servidor gera o ambiente com as referências; o CAD abre com a faixa
    r = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/projetos/compressores/detalhar-posicao",
        data=json.dumps({"marca": "P77", "edicao": True, "modo": "local"}).encode(), headers={"Content-Type": "application/json"}), timeout=600))
    ok(r.get("referencias", 0) > 0, f"no local: {r.get('referencias')} referência(s) em volta da chapa")
    antes = furos_p77()                               # depois da conversão em chapa paramétrica
    aba.navegar(base + f"/cad?projeto=compressores&desenho={r['nome']}&voltar=__3d__", limite=90)
    esperar(aba, "document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 5")
    faixa = aba.avaliar("(document.querySelector('.faixa-edicao') || {}).textContent || ''")
    ok("EDITANDO" in faixa and "P77" in faixa and "no local" in faixa, f"CAD: a faixa do ambiente de edição ({faixa[:80]!r})")
    trav = aba.avaliar("(() => { const c = window.cad.doc.camadas.get('REFERENCIA'); return !!(c && c.bloqueada) && [...window.cad.doc.entidades.values()].filter(e => e.camada === 'REFERENCIA').length; })()")
    ok(trav and trav > 0, f"as referências na camada REFERENCIA travada ({trav})")
    aba.avaliar("window.cad.tela.enquadrar(); 1"); aba.drenar(1.0)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_editar_chapa_local.png"), "wb") as f:
        f.write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    # 3) move o furo 0 em +10 e conclui: as 18 chapas do 3D mudam
    aba.avaliar("""(() => { for (const e of window.cad.doc.entidades.values()) { const a = e.atributos || {};
        if (e.camada === 'FURO' && a.furo === 0) { if (e.tipo === 'circulo') e.centro = [e.centro[0] + 10, e.centro[1]];
          else e.vertices = e.vertices.map(p => [p[0] + 10, p[1]]); } } return 1; })()""")
    msg = aba.avaliar("(async () => { await window.cad.concluirEdicaoChapa(); return [...document.querySelectorAll('.aviso')].map(x => x.textContent).join(' | '); })()")
    print("       ", (msg or "")[:160])
    t0 = time.time()
    while time.time() - t0 < 60 and furos_p77() == antes:
        aba.drenar(1.0)
    depois = furos_p77()
    ok(depois != antes and len(depois) == len(antes) and all(a != d for a, d in zip(antes, depois)), f"Concluir levou o furo às {len(depois)} chapas P77 do 3D")
    aba.drenar(2.0)
    ok("/editor" in aba.avaliar("location.pathname"), "Concluir voltou ao 3D (veio de lá)")
    # 4) isolada aberta pelo 2D e cancelada: nada vai ao 3D
    r2 = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/projetos/compressores/detalhar-posicao",
        data=json.dumps({"marca": "P77", "edicao": True, "modo": "isolada"}).encode(), headers={"Content-Type": "application/json"}), timeout=600))
    aba.navegar(base + f"/cad?projeto=compressores&desenho={r2['nome']}", limite=90)
    esperar(aba, "document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho > 5")
    ok("isolada" in (aba.avaliar("(document.querySelector('.faixa-edicao') || {}).textContent || ''") or ""), "isolada: a faixa diz isolada")
    ok(r2.get("referencias", 0) == 0, "isolada: sem referências")
    aba.avaliar("""(() => { for (const e of window.cad.doc.entidades.values()) { const a = e.atributos || {};
        if (e.camada === 'FURO' && a.furo === 0 && e.tipo === 'circulo') e.centro = [e.centro[0] + 30, e.centro[1]]; } return 1; })()""")
    aba.avaliar("window.cad._editado = false; window.cad.cancelarEdicaoChapa(); 1")
    aba.drenar(2.0)
    ok(furos_p77() == depois, "Cancelar não mexeu no 3D")
    ok(not aba.avaliar("!!document.querySelector('.faixa-edicao')"), "Cancelar tirou a faixa")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + (": %s" % erros[:3] if erros else ""))
finally:
    for p in (nav, srv):
        try:
            p.kill()
        except Exception:                                     # noqa: BLE001
            pass
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
