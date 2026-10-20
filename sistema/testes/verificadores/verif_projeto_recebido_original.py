# -*- coding: utf-8 -*-
"""Projeto recebido = só leitura (20/10/2026, o usuário: "a primeira importação poderia ser somente a leitura … deixar
esse projeto importado como original que não é mexido"). No Hangar Almayer o "1. Importar" lia e já montava o 3D: sem
malha de eixos, 30 desenhos de fabricação saíram enfileirados no 3D (Projeto/OBRAS/Hangar-Almayer/Caminho-DXF-para-3D-
Hangar-Almayer-2026-10-20.pdf). Com o mouse de verdade (CDP), pelo menu do CAD e pelo campo de arquivo:
  · Desenho → Projeto recebido explica que entra como o Original, sem 3D;
  · o DXF do Hangar entra como o Original (planta de lançamento, camadas do projetista travadas, em tamanho real);
  · NENHUM modelo 3D nem IFC é gerado; o DXF fica em documentos/ e o projeto passa a "recebido";
  · o resultado mostra as 36 folhas pelos carimbos (a 12 é a PLANTA DE LOCAÇÃO) e o botão Identificação para modelagem,
    que abre a Montagem com o Original apontado."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

HANGAR = os.path.join(BASE, "..", "Projeto", "OBRAS", "Hangar-Almayer", "Hangar-Allmayer_Projeto de fabricacao_V5.dxf")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_recebido_original_")
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=120))


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


if not os.path.exists(HANGAR):
    print("  (sem o DXF do Hangar em Projeto/OBRAS/Hangar-Almayer: nada a conferir)")
    sys.exit(0)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_recebido_original_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=60.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if aba.avaliar(expr): return True
            aba.drenar(0.3)
        return False

    def clicar(seletor):
        r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
        if not r: raise RuntimeError("não achei " + seletor)
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1, buttons=1 if tipo == "mousePressed" else 0)
        aba.drenar(0.3)

    def escolher_arquivo(seletor, caminho):
        doc = aba.cmd("DOM.getDocument", depth=-1, pierce=True)
        no = aba.cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=seletor)["nodeId"]
        aba.cmd("DOM.setFileInputFiles", files=[os.path.abspath(caminho)], nodeId=no)
        aba.drenar(0.5)

    s = urllib.parse.quote(post("/api/projetos", {"nome": "Hangar recebido", "tipo": "desenho"})["slug"])
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && document.body.dataset.pronto === '1'")
    aba.console.clear()

    clicar('.menu[data-menu="desenho"] > button')
    ok(aba.avaliar("!!document.querySelector('[data-acao=\"identificacao\"]')"), "o menu Desenho tem Identificação para modelagem")
    clicar('[data-acao="projeto-2d"]')
    t = aba.avaliar("(document.querySelector('dialog[open]') || {}).textContent || ''") or ""
    ok("ORIGINAL" in t and "sem modelo 3D" in t and "Escolher o arquivo" in t, f"Projeto recebido explica que entra como o Original, sem 3D: «{t[:140]}»")
    clicar("#dialogo-ok")
    escolher_arquivo("#arquivo-projeto-2d", HANGAR)
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-ok').textContent === 'Ler o projeto'", 30),
       "o arquivo escolhido pede a confirmação (Ler o projeto)")
    clicar("#dialogo-ok")
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent.includes('o que o programa leu')", 180),
       "o resultado é \"o que o programa leu\"")
    corpo = aba.avaliar("document.querySelector('#dialogo-corpo').textContent") or ""
    botao = aba.avaliar("document.querySelector('#dialogo-ok').textContent") or ""
    ok("36 folha" in corpo and "PLANTA DE LOCAÇÃO" in corpo and "T3 - VISTA GERAL" in corpo, f"as 36 folhas pelos carimbos: «{corpo[:200]}»")
    ok("O Original está no projeto" in corpo, "o bloco diz que o Original está no projeto")
    ok(botao.startswith("Identificação para modelagem"), f"o botão leva à Identificação para modelagem: {botao!r}")

    # o servidor: só o Original — nada de 3D nem de IFC
    p = get(f"/api/projetos/{s}")
    pr = p.get("projeto") or p
    pasta = os.path.join(DADOS, urllib.parse.unquote(s))
    modelo = os.path.join(pasta, "modelo.json")
    n_mod = len((json.load(open(modelo, encoding="utf-8")).get("entidades") or [])) if os.path.exists(modelo) else 0
    ifc = [f for f in os.listdir(os.path.join(pasta, "ifc"))] if os.path.isdir(os.path.join(pasta, "ifc")) else []
    ok(n_mod == 0 and not ifc, f"nenhum modelo 3D nem IFC gerado (entidades {n_mod}, IFC {ifc})")
    ok(pr.get("tipo") == "recebido" and pr.get("dxf_recebido") == os.path.basename(HANGAR),
       f"o projeto passou a recebido e o DXF ficou guardado: {pr.get('tipo')}, {pr.get('dxf_recebido')}")
    ok(os.path.exists(os.path.join(pasta, "documentos", os.path.basename(HANGAR))), "o DXF está em documentos/ (aba Arquivos)")
    orig = json.load(open([os.path.join(pasta, "desenhos-2d", f) for f in os.listdir(os.path.join(pasta, "desenhos-2d")) if "lan" in f][0], encoding="utf-8"))
    arq = {k: c for k, c in orig["camadas"].items() if k.startswith("ARQ ")}
    md = orig["metadados"]["arquitetonico"]
    ok(arq and all(c.get("bloqueada") for c in arq.values()), f"as {len(arq)} camadas do projetista estão travadas no Original")
    ok(abs(md["largura_mm"] - 226_500) < 2_000, f"em tamanho real (a folha toda com 226,5 m; a locação com 27,6 m): {md['largura_mm']}")

    clicar("#dialogo-ok")
    ok(esperar("window.cad.nomeDesenho === 'montagem'", 30), f"o botão abre a Montagem: {aba.avaliar('window.cad.nomeDesenho')}")
    orig_m = aba.avaliar("(window.montagem.m || {}).original || window.montagem.original")
    ok(orig_m == "planta-de-lançamento", f"a Montagem aponta para o Original: {orig_m}")
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
