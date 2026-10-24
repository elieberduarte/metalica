# -*- coding: utf-8 -*-
"""A Montagem gravada sem `vaga` (o lugar do "+ corte tesoura"), como a que um script de obra escreve (OrtoBio, 23/10:
`montagem.js` `_controles` lia `ret(m.vaga)` sem conferir e a tela dava TypeError a cada quadro). Confere, em cada
SITUACAO: abrir o desenho "montagem" não dá erro de JavaScript, os títulos dos quadros aparecem e o "+ corte tesoura"
fica fora dos quadros."""
import json, os, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

# cada situação: os quadros gravados (sem "vaga") e a escala do desenho
SITUACOES = {
    # a da OrtoBio (montar_ortobio.py): só a Implantação, folha em mm de papel (escala 1), o canto longe da origem
    "ortobio-so-implantacao": (1.0, [
        {"id": "q1", "tipo": "implantacao", "nome": "Implantação", "escala": 100.0, "w": 580, "h": 945, "x": -10.0, "y": 920.0,
         "mapa": {"X0": 0, "Y0": 0, "ox": 10.0, "oy": -920.0, "giro": 0}}]),
    # quadros padrão com duas tesouras, gravados por script
    "com-tesouras": (1.0, [
        {"id": "q1", "tipo": "implantacao", "nome": "Implantação", "escala": 100.0, "w": 420, "h": 297, "x": 0.0, "y": 0.0},
        {"id": "q2", "tipo": "tesoura", "nome": "T1", "escala": 25.0, "w": 297, "h": 210, "x": 0.0, "y": -400.0},
        {"id": "q3", "tipo": "tesoura", "nome": "T2", "escala": 25.0, "w": 297, "h": 210, "x": 322.0, "y": -400.0}]),
}

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_sem_vaga_")
for nome, (esc, qs) in SITUACOES.items():
    pasta = os.path.join(DADOS, nome)
    os.makedirs(os.path.join(pasta, "desenhos-2d"))
    json.dump({"formato": 1, "nome": nome, "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
               "criado": "2026-10-24T00:00:00", "alterado": "2026-10-24T00:00:00", "dados": None},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
    json.dump({"nome": "montagem", "unidade": "mm", "escala": esc, "camadas": {}, "vistas": [],
               "entidades": [{"id": "l1", "tipo": "linha", "camada": "0", "a": [0.0, 0.0], "b": [100.0, 0.0], "atributos": {"quadro": "q1"}}],
               "metadados": {"montagem": {"versao": 1, "original": "planta", "quadros": qs}}},
              open(os.path.join(pasta, "desenhos-2d", "montagem.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_sem_vaga_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    for nome, (esc, qs) in SITUACOES.items():
        print(f"[{nome}]")
        aba.console.clear()
        aba.navegar(f"{base}/cad?projeto={nome}&desenho=montagem", limite=60)
        esperar(aba, "!!(window.montagem && window.cad && cad.nomeDesenho === 'montagem' && montagem.ativa)")
        # navegar pela tela: cada quadro de desenho passa pelo _controles
        aba.avaliar("montagem.enquadrar(); cad.tela.pedirQuadro(); 1"); aba.drenar(1.0)
        aba.avaliar("cad.tela.pedirQuadro(); 1"); aba.drenar(0.8)
        erros = [t for (tp, t) in aba.console if tp in ("error", "excecao")]
        ok(not erros, "abrir a Montagem sem `vaga` não dá erro de JavaScript" + (f": {erros[:2]}" if erros else ""))
        ok(aba.avaliar("document.querySelectorAll('.quadro-titulo').length") == len(qs), f"os títulos dos {len(qs)} quadros aparecem")
        ok(aba.avaliar("!!document.querySelector('.quadro-mais')"), "o \"+ corte tesoura\" aparece")
        vaga = json.loads(aba.avaliar("JSON.stringify(cad.doc.metadados.montagem.vaga || null)") or "null")
        # (os quadros de agora: a Implantação se redesenha ao abrir e pode acomodar os outros)
        qs_agora = json.loads(aba.avaliar("JSON.stringify(cad.doc.metadados.montagem.quadros)") or "[]")
        sobre = vaga and any(vaga["x"] < q["x"] + q["w"] and q["x"] < vaga["x"] + vaga["w"]
                             and vaga["y"] - vaga["h"] < q["y"] and q["y"] - q["h"] < vaga["y"] for q in qs_agora)
        ok(bool(vaga) and not sobre, f"o \"+ corte tesoura\" fica fora dos quadros: {vaga}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()

print("FALHAS: %d" % len(falhas) if falhas else "TUDO OK")
sys.exit(1 if falhas else 0)
