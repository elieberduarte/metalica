# -*- coding: utf-8 -*-
"""CAD: ferramenta Corte (Y) — três cliques numa planta do modelo marcam a linha de corte
(linha, setas, bolinhas com o nome) e geram a vista do corte no 3D pela referência 2D da
planta; o nome sobe (1, 2…); e o diálogo do 3D dos eixos responde pela API."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8806
DADOS = tempfile.mkdtemp(prefix="metalica_cadcorte_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
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
    return json.load(urllib.request.urlopen(req, timeout=120))
def get(rota):
    return json.load(urllib.request.urlopen(base + urllib.parse.quote(rota), timeout=120))
def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False
# uma "planta" sintética do modelo: papel X = x do modelo, Y = y (vista de cima, origem 0, ref2d 0)
ents = [{"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 0], "b": [17000, 0]},
        {"id": "l2", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 31000], "b": [17000, 31000]}]
vistas = [{"origem": [0, 0, 0], "normal": [0, 0, -1], "acima": [0, 1, 0], "profundidade": None, "cortar": False, "entidades": None,
           "rotular": False, "nome": "PLANTA", "tipo": "topo", "pecas_cortadas": 0, "pecas_projetadas": 0,
           "largura": 17000, "altura": 31000, "canto": [0, 0], "avisos": [], "ref2d": [0, 0]}]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadcorte_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    post("/api/projetos/compressores/desenhos/planta", {"desenho": {"nome": "Planta", "escala": 100, "entidades": ents, "vistas": vistas}})
    # os eixos pela API (o diálogo do 3D usa estas rotas)
    r = get("/api/projetos/compressores/eixos")
    ex = r.get("eixos") or {}
    ok(len(ex.get("numeros") or []) >= 3 and len(ex.get("letras") or []) >= 2, f"eixos identificados do modelo: {[n['nome'] for n in ex.get('numeros', [])]} / {[n['nome'] for n in ex.get('letras', [])]}")
    ex["letras"][0]["nome"] = "A'"
    r2 = post("/api/projetos/compressores/eixos", {"eixos": ex})
    ok(r2.get("gravados") and get("/api/projetos/compressores/eixos")["eixos"]["letras"][0]["nome"] == "A'", "eixos gravados no projeto com o nome trocado")
    post("/api/projetos/compressores/eixos", {"apagar": True})
    ok(not get("/api/projetos/compressores/eixos")["gravados"], "apagados: volta ao automático")
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/cad?projeto=compressores&desenho=planta", limite=30)
    ok(esperar(aba, "document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho === 2"), "planta aberta")
    js = lambda s: aba.avaliar("(() => { const c = window.cad; " + s + " })()")
    ok(js("return !!c.ferramentas.find(f => f.id === 'corte');") or js("return c.ativarFerramenta('corte'), c.ferramenta.constructor.id === 'corte';"), "ferramenta Corte existe")
    # a pergunta da profundidade respondida por código; três cliques: começo, fim, lado que se olha
    aba.avaliar("window.cad.perguntar = async () => '2500'; 1")
    js("c.ativarFerramenta('corte'); const f = c.ferramenta; f.onPonto([0, 5000]); f.onPonto([17000, 5000]); return 1;")
    aba.avaliar("window.cad.ferramenta.onPonto([8000, 9000]); 1")
    ok(esperar(aba, "window.cad.doc.vistas.length >= 2", limite=120), "a vista do corte foi gerada e o desenho reaberto")
    marcas = js("return [...c.doc.entidades.values()].filter(e => e.atributos && e.atributos.marca_corte === '1');")
    n_marcas = js("return [...c.doc.entidades.values()].filter(e => e.atributos && e.atributos.marca_corte === '1').length;")
    ok(n_marcas == 11, f"marca do corte 1-1: {n_marcas} entidades (linha, 2 setas com pontas, 2 bolinhas com nome)")
    v = json.loads(js("const v = c.doc.vistas[c.doc.vistas.length - 1]; return JSON.stringify([v.tipo, v.nome, v.pecas_cortadas, v.normal, v.origem, v.profundidade]);"))
    ok(v[0] == "corte" and v[1] == "Corte 1-1" and v[2] > 0 and v[3] == [0, 1, 0] and v[4] == [0, 5000, 0] and v[5] == 2500, f"vista: {v}")
    # estilos do desenho: altura dos textos e terminador das cotas na seleção e no desenho inteiro
    r = json.loads(js("""
      const ids = [...c.doc.entidades.values()].filter(e => e.atributos && e.atributos.marca_corte === '1').map(e => e.id);
      const n1 = c.aplicarEstilos({ altura: 4, terminador: 'bola' }, ids);
      const textos = [...c.doc.entidades.values()].filter(e => e.tipo === 'texto' && e.atributos && e.atributos.marca_corte === '1');
      const cota = c.doc.add ? null : null;
      const n2 = c.aplicarEstilos({ terminador: 'traco' }, null);
      return JSON.stringify([n1, textos.map(t => t.altura), (c.doc.metadados.estilo || {}).terminador, n2]);"""))
    ok(r[0] == 2 and r[1] == [4, 4] and r[2] == "traco", f"estilos: altura na seleção e terminador padrão do desenho: {r}")
    # o próximo corte é o 2
    ok(js("c.ativarFerramenta('corte'); return c.ferramenta._nome();") == "2", "o próximo corte chama-se 2")
    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
    ok(not erros, f"erros de JavaScript: {len(erros)}")
    for t, x in erros[:6]: print("     [%s] %s" % (t, x[:300]))
    aba.ws.close()
finally:
    nav.terminate(); srv.terminate()
shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
