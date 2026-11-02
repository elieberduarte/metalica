# -*- coding: utf-8 -*-
"""Lista de materiais num projeto sem peças de aço (OBRA · CASA ALTO PADRÃO, 02/11: Arquivo › Arquivos do projeto… abriu
"Não foi possível montar a lista: o modelo não tem peças com marcas de IFC…" e mais nada — as abas Resumos, Conferência e
Arquivos só eram montadas depois da lista, e os PDFs da apresentação, gravados em documentos/, ficavam sem caminho na tela).

Agora: com a lista impossível, a tela continua dizendo por quê, e monta as abas que não dependem dela, abrindo a de
Arquivos com os documentos do projeto. Modelo de verdade do caso: um projeto de arquitetura, sem nenhuma peça de aço."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_mat_sem_aco_")
dst = os.path.join(DADOS, "casa")
os.makedirs(os.path.join(dst, "documentos"))
json.dump(Documento(nome="Casa").dict(), open(os.path.join(dst, "modelo.json"), "w", encoding="utf-8"))
json.dump({"formato": 1, "nome": "Casa", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-02T00:00:00", "alterado": "2026-11-02T00:00:00", "dados": None},
          open(os.path.join(dst, "projeto.json"), "w", encoding="utf-8"))
with open(os.path.join(dst, "documentos", "Casa-apresentacao.pdf"), "wb") as f:
    f.write(b"%PDF-1.4\n%%EOF\n")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


AVISO = "(document.querySelector('#aviso')?.textContent || '')"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mat_sem_aco_")
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
    # o caminho do menu: Arquivo › Arquivos do projeto… (barra_unica.js) → /materiais?projeto=…#arquivos
    aba.navegar(f"{base}/materiais?projeto=casa#arquivos", limite=60)
    ok(esperar(aba, f"/Não foi possível montar a lista/.test({AVISO})", 30),
       f"a tela diz por que não há lista ({aba.avaliar(AVISO)[:100]!r})")
    ok(esperar(aba, "!!document.querySelector('#abas button[data-aba=\"arquivos\"]')", 10), "a aba Arquivos existe sem a lista")
    ok(aba.avaliar("document.querySelector('#abas button[data-aba=\"arquivos\"]')?.classList.contains('ativa')"),
       "e é a aba aberta (veio pelo #arquivos)")
    ok(esperar(aba, "/Casa-apresentacao/.test(document.querySelector('#arquivos-corpo')?.textContent || '')", 15),
       "o PDF de documentos/ aparece na aba")
    ok(aba.avaliar("!!document.querySelector('#abas button[data-aba=\"resumos\"]') && "
                   "!!document.querySelector('#abas button[data-aba=\"conferencia\"]')"), "Resumos e Conferência também ficam")
    ok(not aba.avaliar("!!document.querySelector('#abas button[data-aba=\"perfis\"]')"),
       "as abas que dependem da lista (Perfis…) não aparecem vazias")
    # aberta sem o # (a aba lembrada era uma da lista): cai na de Arquivos
    aba.avaliar("localStorage.setItem('materiais.aba', 'perfis'); 1")
    aba.navegar(f"{base}/materiais?projeto=casa", limite=60)
    ok(esperar(aba, "document.querySelector('#abas button[data-aba=\"arquivos\"]')?.classList.contains('ativa')", 15),
       "sem o #, com a aba lembrada da lista, abre a de Arquivos")
    # o 400 de /materiais é a própria recusa da lista (o aviso acima); qualquer outro erro conta
    erros = [m for m in aba.console if "error" in str(m).lower() and "favicon" not in str(m) and "/materiais" not in str(m)]
    ok(not erros, f"sem erro no console ({erros[:2]})")
finally:
    nav.kill(); srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print("\nVERIFICAÇÃO:", "OK" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
