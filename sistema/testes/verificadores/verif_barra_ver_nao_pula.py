# -*- coding: utf-8 -*-
"""A barra do modo ver não pula (GESTÃO N.9, 14/11 — a 3ª rodada da conferência da 0.9.3: o botão Terreno aparecia logo
à esquerda do Cenas quando a rota do terreno respondia, e o clique no Cenas caía no Terreno).

Regra: nenhum botão da barra muda de lugar depois que ela já aceita clique. O que só se sabe depois (a cobertura
retrátil, a planta no chão, o terreno) fica na ponta da barra, na ordem (ver3d.js, pontaDaBarra).

Com a resposta do terreno (3 s), a da planta (1,5 s) e a do projeto (0,8 s) atrasadas na página (como na máquina
carregada), em cada situação:
  1. a posição de cada botão no momento em que a barra aparece é a mesma depois que tudo respondeu;
  2. o clique de verdade (mouse) no lugar onde o Cenas estava abre as Cenas, não o Terreno;
  3. sem terreno não fica buraco: nenhum botão invisível ocupando lugar, os vizinhos a 4 px.
Porta livre, nunca a 8765/8766. Chrome sem janela."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

#: (nome, ambiente do servidor, o Terreno aparece no fim?)
SITUACOES = [
    ("com terreno", {"METALICA_TERRENO": "1", "METALICA_TERRENO_FALSO": "1"}, True),
    ("sem terreno (instalado sem a função)", {"METALICA_TERRENO": "0"}, False),
]

#: a página demora a saber o que entra na ponta da barra (a máquina carregada da conferência)
ATRASO = r"""
(() => {
  const f = window.fetch.bind(window);
  const atraso = u => /\/terreno(\?|$)/.test(u) ? 3000 : /\/lancamento\/referencia/.test(u) ? 1500
                    : /\/api\/projetos\/[^/?]+(\?|$)/.test(u) ? 800 : 0;
  window.fetch = (u, o) => { const ms = atraso(String((u && u.url) || u)); return ms ? new Promise(r => setTimeout(r, ms)).then(() => f(u, o)) : f(u, o); };
})();
"""

#: os itens da barra que estão na tela: chave estável -> retângulo
ITENS = r"""
(() => {
  const r = {};
  document.querySelectorAll('#ferramentas button, #ferramentas input, #ferramentas label').forEach((e, i) => {
    if (!e.getClientRects().length) return;
    const k = e.id || (e.dataset.vista && 'vista-' + e.dataset.vista) || (e.dataset.situacao && 'sit-' + e.dataset.situacao)
              || e.getAttribute('data-painel') || ('item-' + i);
    const b = e.getBoundingClientRect();
    r[k] = [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)];
  });
  return JSON.stringify(r);
})()
"""

#: buraco: um filho da barra ocupando lugar sem aparecer, ou dois vizinhos da mesma linha a mais de 4 px
BURACOS = r"""
(() => {
  const fora = [];
  const filhos = [...document.querySelectorAll('#ferramentas > *')].filter(e => e.getClientRects().length);
  for (const e of filhos) {
    const cs = getComputedStyle(e);
    if (cs.visibility !== 'visible' || +cs.opacity === 0) fora.push('invisível ocupando lugar: ' + (e.id || e.textContent.trim()));
  }
  for (let i = 1; i < filhos.length; i++) {
    const a = filhos[i - 1].getBoundingClientRect(), b = filhos[i].getBoundingClientRect();
    if (Math.abs(a.top - b.top) < 2 && b.left - a.right > 5) fora.push(`buraco de ${Math.round(b.left - a.right)} px antes de ` + (filhos[i].id || filhos[i].textContent.trim()));
  }
  return JSON.stringify(fora);
})()
"""

falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.1)
    return False


def clicar_em(aba, x, y):
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button="left", clickCount=1)
    aba.drenar(0.2)


def uma_situacao(nome, ambiente, com_terreno, indice):
    porta = _porta_livre()
    dados = tempfile.mkdtemp(prefix="metalica_barra_ver_")
    proj = os.path.join(dados, "obra")
    os.makedirs(proj)
    json.dump({"nome": "Barra do modo ver", "tipo": "ifc", "alterado": "2026-11-14T09:00:00"},
              open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
    json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, **ambiente))
    base = f"http://localhost:{porta}"
    exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_barra_ver_")
    nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                            "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"\n— {nome}", flush=True)
    try:
        for _ in range(60):
            try: _json(base + "/api/versao"); break
            except Exception: time.sleep(0.5)
        for _ in range(60):
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
            time.sleep(0.5)
        aba = Aba(alvos[0]["webSocketDebuggerUrl"])
        for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)
        aba.cmd("Page.addScriptToEvaluateOnNewDocument", source=ATRASO)
        aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)

        ok(esperar(aba, "!!window.ver3dPronto && !document.getElementById('ferramentas').hidden", 90), "a barra aparece")
        antes = json.loads(aba.avaliar(ITENS))
        ok(not aba.avaliar("!!window.ver3dBarraAssentada")
           and aba.avaliar("document.getElementById('btn-terreno').hidden") is True,
           "a barra já aceita clique e o terreno ainda não respondeu (o atraso pegou a janela da conferência)")
        ok("btn-cenas" in antes, "o Cenas está na barra desde o começo")
        # tudo responde (o terreno por último, 3 s + a imagem)
        ok(esperar(aba, "!!window.ver3dBarraAssentada", 40), "a ponta da barra fica decidida")
        aba.drenar(0.5)
        depois = json.loads(aba.avaliar(ITENS))
        mudou = [f"{k}: {antes[k]} → {depois.get(k)}" for k in antes if depois.get(k) != antes[k]]
        ok(not mudou, "nenhum botão que estava na tela mudou de lugar" + (" — " + "; ".join(mudou) if mudou else ""))
        ok(("btn-terreno" in depois) == com_terreno, "o Terreno " + ("aparece no fim da barra" if com_terreno else "não aparece"))
        if com_terreno:
            ok(depois["btn-terreno"][0] >= max(v[0] for k, v in depois.items() if k != "btn-terreno"),
               "o Terreno é o último da barra")
        buracos = json.loads(aba.avaliar(BURACOS))
        ok(not buracos, "sem buraco na barra" + (" — " + "; ".join(buracos) if buracos else ""))
        open(os.path.join(SCR, f"barra_ver_nao_pula_{indice}.png"), "wb").write(
            base64.b64decode(aba.cmd("Page.captureScreenshot", format="png",
                                     clip={"x": 0, "y": 0, "width": 1400, "height": 60, "scale": 1})["data"]))
        # o clique de quem mirou no Cenas quando a barra apareceu
        x, y, w, h = antes["btn-cenas"]
        clicar_em(aba, x + w / 2, y + h / 2)
        ok(esperar(aba, "document.getElementById('painel').dataset.painel === 'cenas' && !document.getElementById('painel').hidden", 8),
           "o clique onde o Cenas estava abre as Cenas (painel: %r)" % aba.avaliar("document.getElementById('painel').dataset.painel || ''"))
    finally:
        nav.terminate(); srv.terminate()
        for p in (nav, srv):
            try: p.wait(10)
            except Exception: p.kill()
        shutil.rmtree(perfil, ignore_errors=True); shutil.rmtree(dados, ignore_errors=True)


for i, (nome, amb, tem) in enumerate(SITUACOES, 1):
    uma_situacao(nome, amb, tem, i)

print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)), flush=True)
sys.exit(1 if falhas else 0)
