# -*- coding: utf-8 -*-
"""Resumos da obra: "Gerar os resumos", sair da tela e voltar (usuário, 06/11, Galpão Novo da Hora Certa: "Se clico para
gerar um novo resumo e saio da tela ele interrompe o processo, preciso que corrija isso para ele continuar gerando em
segundo plano"). O servidor seguia até o fim, mas quem voltava via o resumo antigo com o botão livre.

Agora: o clique diz que pode sair; de volta no meio, a aba diz que os resumos estão sendo gerados e desde quando, com a
etapa do servidor e o botão desligado (sem segunda geração); quando acaba, os resumos novos entram sozinhos. Modelo de
verdade (o galpão de exemplo), com as fotos do 3D e os PDFs."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_res_voltar_")
dst = os.path.join(DADOS, "sala")
os.makedirs(dst)
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(dst, "modelo.json"))
json.dump({"formato": 1, "nome": "Sala", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "", "criado": "2026-11-06T00:00:00",
           "alterado": "2026-11-06T00:00:00", "dados": None}, open(os.path.join(dst, "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
_json(base + "/api/versao")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.5)
    return False


def clicar(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b) return null; b.scrollIntoView({{ block: 'center' }}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r:
        return False
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    return True


BOTAO = "#resumos-corpo .form-resumo button[type=submit]"
ESTADO = "(document.querySelector('#resumo-estado')?.textContent || '')"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_res_")
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

    def abrir_aba_resumos():
        aba.navegar(f"{base}/materiais?projeto=sala", limite=120)
        esperar(aba, "!!document.querySelector('#btn-resumos')", 60)
        aba.drenar(1.0)
        clicar(aba, "#btn-resumos")
        return esperar(aba, f"!!document.querySelector({json.dumps(BOTAO)})", 60)

    ok(abrir_aba_resumos(), "a aba Resumos da obra abriu, com o formulário")
    ok(clicar(aba, BOTAO), "clique em Gerar os resumos")
    ok(esperar(aba, f"/pode sair desta tela/.test({ESTADO})", 10), f"o clique diz que pode sair ({aba.avaliar(ESTADO)[:100]!r})")
    aba.drenar(2.0)
    # sai da tela no meio (a tela inicial) e volta
    aba.navegar(f"{base}/", limite=60)
    aba.drenar(1.0)
    ok(abrir_aba_resumos(), "de volta à aba Resumos")
    em = esperar(aba, f"/sendo gerados \\(começou às \\d\\d:\\d\\d\\)/.test({ESTADO})", 20)
    ok(em, f"de volta no meio: a aba diz que os resumos estão sendo gerados e desde quando ({aba.avaliar(ESTADO)[:140]!r})")
    ok(aba.avaliar(f"document.querySelector({json.dumps(BOTAO)}).disabled"), "o botão fica desligado (sem segunda geração)")
    fim = esperar(aba, f"/Pronto: os resumos novos/.test({ESTADO})", 600)
    ok(fim, f"quando acaba, os resumos novos aparecem sozinhos ({aba.avaliar(ESTADO)[:120]!r})")
    aba.drenar(4.0)
    ok("Pronto" in aba.avaliar(ESTADO), f"o recado do fim fica na aba (a lista recarregada não o apaga: {aba.avaliar(ESTADO)[:80]!r})")
    ok(not aba.avaliar(f"document.querySelector({json.dumps(BOTAO)}).disabled"), "e o botão volta")
    r = _json(base + "/api/projetos/sala/resumos")
    ok((r.get("arquivos") or {}).get("obra") and not r.get("atualizando"), f"o resumo da obra gravado ({list((r.get('arquivos') or {}).keys())})")
    ok(os.path.exists(os.path.join(dst, "detalhamento", "resumo-da-obra.pdf")), "com o PDF")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
