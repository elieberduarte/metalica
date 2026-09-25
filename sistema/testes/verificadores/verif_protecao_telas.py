# -*- coding: utf-8 -*-
"""Proteção dos dados nas telas (0.8.12): nome de desenho repetido pergunta; desenho que
não abriu não é gravado por cima; ir para o 3D grava o pendente antes; o 3D com modelo
que não abre não grava a tela vazia por cima."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8799
DADOS = tempfile.mkdtemp(prefix="metalica_prot_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return json.load(e)


def pedir(rota):
    try:
        return json.load(urllib.request.urlopen(base + urllib.parse.quote(rota), timeout=30))
    except urllib.error.HTTPError as e:
        return {"erro": e.code}


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_prot_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Protecao", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    linha = {"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 0], "b": [1000, 0]}
    post(f"/api/projetos/{slug}/desenhos/existente", {"desenho": {"nome": "Existente", "escala": 50, "entidades": [linha]}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.navegar(base + "/"); aba.console.clear()

    # 1. novo desenho com o nome de um que existe
    aba.navegar(base + f"/cad?projeto={slug}&desenho=existente", limite=30)
    esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad && window.cad.nomeDesenho === 'existente'")
    aba.avaliar("window.cad.perguntar = async () => 'Existente'; window.cad.dialogoNovo(); 1")
    ok(esperar(aba, "(() => { const d = document.querySelector('dialog[open]'); return !!d && d.textContent.includes('Nome já usado'); })()", 10),
       "novo desenho com nome existente pergunta")
    aba.avaliar("document.querySelector('#dialogo-cancelar').click(); 1"); aba.drenar(0.5)
    ok(len(pedir(f"/api/projetos/{slug}/desenhos/existente").get("desenho", {}).get("entidades", [])) == 1, "o desenho existente ficou intacto")

    # 2. desenho que não abre: o que se desenha na tela não vai por cima
    aba.navegar(base + f"/cad?projeto={slug}&desenho=nao-existe", limite=30)
    esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad")
    ok(aba.avaliar("window.cad._desenhoBloqueado()"), "o desenho que não abriu fica bloqueado para gravar")
    aba.avaliar("(() => { window.cad.doc.add ? 0 : 0; window.cad._agendarAutosave(); return 1; })()")
    aba.avaliar("window.cad.salvar({ avisar: false }); 1"); aba.drenar(4)
    ok("erro" in pedir(f"/api/projetos/{slug}/desenhos/nao-existe"), "nada foi gravado com o nome do desenho que não abriu")

    # 3. ir para o 3D grava o pendente antes
    aba.navegar(base + f"/cad?projeto={slug}&desenho=existente", limite=30)
    esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad && window.cad.nomeDesenho === 'existente' && window.cad.doc.tamanho === 1")
    # a forma simples e segura de editar: acrescentar uma linha pelo mesmo caminho do CAD
    aba.avaliar("(() => { const c = window.cad; const j = c.doc.paraJSON(); j.entidades.push({ id: 'l2', tipo: 'linha', camada: 'VISTA', atributos: {}, a: [0, 500], b: [1000, 500] });"
                " c.carregar(j, { enquadrar: false }); c._agendarAutosave(); return c._editado; })()")
    aba.avaliar("document.querySelector('#link-editor').click(); 1")
    ok(esperar(aba, "location.pathname === '/editor'", 30), "foi para o 3D")
    ok(len(pedir(f"/api/projetos/{slug}/desenhos/existente").get("desenho", {}).get("entidades", [])) == 2,
       "a edição foi gravada antes de sair (2 linhas)")

    # 4. 3D com modelo ilegível: não grava a tela por cima
    caminho_modelo = os.path.join(DADOS, slug, "modelo.json")
    with open(caminho_modelo, "w", encoding="utf-8") as f:
        f.write('{"nome": "m", "entidades": [')
    antes = open(caminho_modelo, encoding="utf-8").read()
    aba.navegar(base + f"/editor?projeto={slug}", limite=60)
    esperar(aba, "!!window.editor && window.editor.projeto === %s" % json.dumps(slug), 60)
    ok(esperar(aba, "!!window.editor._modeloNaoAbriu", 30), "o 3D marca que o modelo não abriu")
    aba.avaliar("(() => { const e = window.editor; e._autosavePendente = true; e._autosalvar(); return 1; })()"); aba.drenar(3)
    ok(open(caminho_modelo, encoding="utf-8").read() == antes, "o modelo.json ilegível não foi sobrescrito")
    # o 400 do desenho que não existe e o erro do modelo ilegível são provocados pelo próprio teste
    erros = [c for c in aba.console if c[0] in ("error", "excecao") and "nao-existe" not in c[1] and "/modelo" not in c[1]]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
