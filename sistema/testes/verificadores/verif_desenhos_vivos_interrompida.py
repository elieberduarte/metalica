# -*- coding: utf-8 -*-
"""A atualização automática dos desenhos no Posto (27/10, OBRA · POSTO N.5), na tela:

A. o aviso das terças fora do passo da máquina era de um Detalhar feito com um 3D que mudou depois (a remontagem trocou
   todos os ids): o CAD diz de quando é o aviso, e o "Ver no 3D" — sem nenhum dos ids no 3D — acha as peças pela
   posição e diz que é preciso conferir, em vez de "Nenhuma peça com ids…";
B. interrompida duas vezes seguidas (o programa reiniciou no meio): o CAD diz isso e oferece "Atualizar agora".

Servidor próprio numa pasta temporária (nunca a 8765/8766)."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_vivos_interrompida_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
for _ in range(80):
    try:
        urllib.request.urlopen(base + "/api/versao", timeout=2); break
    except Exception:
        time.sleep(0.5)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


def esperar(aba, expr, limite=60.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


def projeto(nome):
    return post("/api/projetos", {"nome": nome, "tipo": "desenho"})["slug"]


def modelo(s):
    # as duas cópias da terça T.C.9 (posição M92) e a outra parte da marca (M93), com ids novos (a remontagem)
    post(f"/api/projetos/{urllib.parse.quote(s)}/modelo", {"documento": {"nome": "Posto", "entidades": [
        {"tipo": "barra", "id": i, "nome": "terça", "camada": "Vigas", "perfil": "U150X50X2.28", "inicio": [x, 0, 3000],
         "fim": [x, 6000, 3000], "atributos": {"marcas": {"posicao": m}}}
        for i, m, x in (("novo1", "M92", 0), ("novo2", "M92", 2000), ("novo3", "M93", 4000), ("novo4", "M1", 6000))]}})


def carimbo(s, dados):
    det = os.path.join(DADOS, s, "detalhamento")
    os.makedirs(det, exist_ok=True)
    with open(os.path.join(det, "carimbo.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f)


def desenho(s, nome):
    post(f"/api/projetos/{urllib.parse.quote(s)}/desenhos/{nome}", {"desenho": {"nome": nome, "entidades": [
        {"tipo": "linha", "id": "l1", "camada": "0", "a": [0, 0], "b": [100, 100]}]}})


def a_ver_no_3d_do_detalhamento_anterior(aba):
    print("A — aviso das terças de um detalhamento feito com outro 3D")
    s = projeto("Posto antigo")
    modelo(s)
    desenho(s, "pranchas")
    texto = "T.C.9: furos a 40 mm na altura (máquina: 50)"
    # o carimbo de 24/10, de um 3D de antes da remontagem (outra assinatura); os ids dele não existem mais
    carimbo(s, {"desenhos": {}, "modelo": "1:1", "quando": "2026-10-24 21:26:00", "fora_da_maquina": [texto],
                "fora_da_maquina_pecas": [{"nome": "T.C.9", "marca": "M92 / M93", "texto": texto, "ids": ["velho1", "velho2"],
                                           "ligadas": ["velho3"]}]})
    aba.navegar(f"{base}/cad?projeto={urllib.parse.quote(s)}&desenho=pranchas", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'", 60)
    ok(esperar(aba, "!!document.querySelector('.aviso[data-tipo=atencao] button.ver-no-3d')", 30), "o aviso amarelo traz a T.C.9 com Ver no 3D")
    txt = aba.avaliar("[...document.querySelectorAll('.aviso[data-tipo=atencao]')].map(a => a.textContent).join(' ')") or ""
    ok("Aviso do detalhamento de 24/10 às 21:26" in txt and "3D mudou depois" in txt, f"o aviso diz de quando é e que o 3D mudou ({txt[:140]!r})")
    aba.avaliar("document.querySelector('.aviso[data-tipo=atencao] button.ver-no-3d').click(); 1")
    no3d = esperar(aba, "location.pathname === '/editor' && window.editor && window.editor.selecao && window.editor.selecao.ids.size === 3", 60)
    ok(no3d, "sem os ids no 3D, o editor acha as 3 peças das posições M92 e M93 (%s)"
       % aba.avaliar("location.pathname + ' ' + (window.editor && window.editor.selecao ? [...window.editor.selecao.ids].join(',') : '-')"))
    avisos = aba.avaliar("[...document.querySelectorAll('.aviso')].map(a => a.textContent).join(' | ')") or ""
    ok("não existem mais no 3D" in avisos and "confira" in avisos and "Nenhuma peça com ids" not in avisos,
       f"o editor diz que achou pela posição e pede para conferir ({avisos[:200]!r})")
    ok("senao" not in aba.avaliar("location.search"), "a URL fica limpa")


def b_interrompida_duas_vezes(aba):
    print("B — interrompida duas vezes seguidas: o CAD diz e oferece Atualizar agora")
    s = projeto("Posto interrompido")
    modelo(s)
    desenho(s, "detalhamento-tercas")
    # o estado da obra de agora, como o servidor calcula (para a interrompida ser "deste" 3D)
    import desenhos_vivos as dv
    from projetos import Projetos
    g = Projetos(DADOS)
    dv.configurar(gerente=lambda: g)
    agora = dv.carimbo(s)
    carimbo(s, dict(agora, desenhos={"detalhamento-tercas": "g1"}, quando="2026-10-27 09:00:00",
                    interrompida={"desde": time.time() - 900, "motivo": "o modelo 3D mudou", "vezes": 2, "obra": dv._obra(agora)}))
    e = _json(base + f"/api/projetos/{urllib.parse.quote(s)}/desenhos-vivos")
    ok(not e.get("atualizando") and (e.get("interrompida") or {}).get("parada"), f"o estado diz interrompida e parada, sem recomeçar ({e.get('interrompida')})")
    aba.navegar(f"{base}/cad?projeto={urllib.parse.quote(s)}&desenho=detalhamento-tercas", limite=60)
    esperar(aba, "window.cad && document.body.dataset.pronto === '1'", 60)
    achou = esperar(aba, "[...document.querySelectorAll('.aviso')].some(a => /interrompida 2 vezes/.test(a.textContent) && [...a.querySelectorAll('button')].some(b => b.textContent === 'Atualizar agora'))", 30)
    ok(achou, "o aviso diz que foi interrompida 2 vezes e tem Atualizar agora (%s)"
       % (aba.avaliar("[...document.querySelectorAll('.aviso')].map(a => a.textContent).join(' | ')") or "")[:200])
    e = _json(base + f"/api/projetos/{urllib.parse.quote(s)}/desenhos-vivos")
    ok(not e.get("atualizando"), "e não recomeçou sozinha")


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_vivos_")
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
    for passo in (a_ver_no_3d_do_detalhamento_anterior, b_interrompida_duas_vezes):
        try:
            passo(aba)
        except Exception as exc:                    # noqa: BLE001
            ok(False, f"{passo.__name__}: {exc!r}")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
