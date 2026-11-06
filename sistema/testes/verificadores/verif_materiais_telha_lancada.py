# -*- coding: utf-8 -*-
"""Lista de materiais com a cobertura LANÇADA no modelo (Hora Certa · Galpão Novo, usuário 06/11: "por que não foi incluso
as telhas no resumo se modelamos elas" — as 1.967 telhas TP40 PIR 50 e as 57 calhas/cumeeiras modeladas davam "TELHAS 0,0 kg"
no cartão e a aba "Telhas e rufos" vazia, porque a tela só lia as telhas das posições de produção; a telha lançada fica no
Quadro 8, categoria telha/funilaria, de onde o resumo da obra já a lia).

Agora: o cartão Telhas soma o peso e a área delas, a aba Telhas e rufos tem as duas seções das lançadas e a contagem na aba,
e o aço do primeiro cartão não muda. Modelo: o aço do teste do detalhamento + 3 telhas TP40 PIR 50 (15 kg/m²) e uma calha."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Solido
from test_detalhar2d import _modelo
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass


def _caixa(L, B, H, dy=0.0, dz=0.0):
    v = [(x, y + dy, z + dz) for x in (0, L) for y in (0, B) for z in (0, H)]
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return v, f


doc = _modelo()
for i in range(3):
    v, f = _caixa(7140.0, 955.0, 50.0, dy=i * 1000.0, dz=8000.0)
    t = Solido(nome="TP40 PIR 50", camada="Telhas", vertices=v, faces=f)
    t.material = "Telha branca RAL 9003"
    t.atributos.update({"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": "TP40 PIR 50", "largura": 955, "massa_m2": 15,
                        "comprimento": 7140})
    doc.add(t)
v, f = _caixa(20000.0, 300.0, 150.0, dz=8000.0)
c = Solido(nome="Calha", camada="Calhas", vertices=v, faces=f)
c.atributos["tipo_ifc"] = "IfcPipeSegment"
doc.add(c)

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_telha_lancada_")
dst = os.path.join(DADOS, "galpao")
os.makedirs(dst)
json.dump(doc.dict(), open(os.path.join(dst, "modelo.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "Galpão", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-06T00:00:00", "alterado": "2026-11-06T00:00:00", "dados": None},
          open(os.path.join(dst, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(cond, m):
    print(("  ok    " if cond else "  FALHA ") + m)
    if not cond: falhas.append(m)


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


CARTOES = "[...document.querySelectorAll('#cartoes > *')].map(x => x.textContent)"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_telha_lanc_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/materiais?projeto=galpao#telhas", limite=60)
    ok(esperar(aba, f"{CARTOES}.length >= 2", 90), "a lista abriu")
    cart = aba.avaliar(CARTOES)
    telha = next((x for x in cart if "telhas" in x.lower()), "")
    # 3 telhas de 7,14 × 0,955 m a 15 kg/m²: a área de cada uma como o levantamento a dá (a mesma do resumo da obra)
    ok("306,8 kg" in telha and "20,50 m²" in telha, f"o cartão Telhas soma a telha lançada ({telha!r})")
    aco = cart[0]
    ok("306" not in aco, f"o aço não leva a telha ({aco!r})")
    ok(esperar(aba, "/Telhas e painéis lançados no modelo/.test(document.querySelector('#aba-telhas')?.textContent || '')", 15),
       "a aba Telhas e rufos tem a seção das telhas lançadas")
    txt = aba.avaliar("document.querySelector('#aba-telhas')?.textContent || ''")
    ok("TP40 PIR 50" in txt and "Calhas, rufos e cumeeiras lançados no modelo" in txt and "sem o desenvolvimento da chapa" in txt,
       "a telha pelo nome e a calha (sem desenvolvimento: sem peso) na aba")
    n_aba = aba.avaliar("document.querySelector('#abas button[data-aba=\"telhas\"]')?.textContent || ''")
    ok("2" in n_aba, f"a contagem na aba conta as lançadas ({n_aba!r})")
    erros = [m for m in aba.console if "error" in str(m).lower() and "favicon" not in str(m)]
    ok(not erros, f"sem erro no console ({erros[:2]})")
finally:
    nav.kill(); srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print("\nVERIFICAÇÃO:", "OK" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
