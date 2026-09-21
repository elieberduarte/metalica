# -*- coding: utf-8 -*-
"""Verificação do zoom da roda do mouse no editor 3D.

A roda aproxima e afasta apoiada no ponto sob o cursor: a peça sob o cursor, ou o plano
de trabalho. Sem nada sob o cursor — o céu —, o apoio é o próprio alvo da câmera, e o
zoom vira um avanço na direção da vista. O que se confere aqui, girando a roda de
verdade pelo protocolo do Chrome:

    1. cada clique aproxima ou afasta uma fração parecida (nem 1 %, nem 40 %)
    2. o ponto de apoio fica parado sob o cursor, e o alvo fica parado na tela
    3. a direção da vista não muda com o zoom (era o defeito: o alvo ia para a frente
       da câmera a cada clique e a órbita passava a girar em torno do vazio)
    4. com o cursor no céu o alvo não sai do lugar
    5. a grade não troca de escala para frente e para trás entre cliques vizinhos, as
       linhas ficam na faixa de leitura e não disparam em número
    6. nenhum erro de JavaScript

Uso, com o servidor no ar:
    python testes/verificar_zoom.py --porta 8765

Sai com código 1 se algum passo falhar.
"""
import argparse
import base64
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, BASE)

from verificar_editor import Aba, CHAVE_ESTADO, CHROMES, CONTAR_OBJETOS, _json, _porta_livre  # noqa: E402

#: Limites de tela da grade, os mesmos de `web/editor3d/nucleo/cena.js`.
PX_MIN, PX_MAX = 8.0, 110.0
#: Quanto cada clique da roda pode mudar a distância da câmera.
PASSO_MIN, PASSO_MAX = 0.05, 0.25
#: Folga, em pixels, para o apoio do zoom e o alvo ficarem parados na tela.
FOLGA_PX = 3.0

ESTADO = r"""
(() => {
  const c = window.editor.camera, cn = window.editor.cena;
  const mpp = c.mmPorPixel() / 1000;
  const t = c.controles.target, p = c.ativa.position;
  const d = [p.x - t.x, p.y - t.y, p.z - t.z];
  const n = Math.hypot(d[0], d[1], d[2]) || 1;
  const f = c.focoDoZoom;
  // o canvas não começa no canto da janela: barra do topo e barra de ferramentas
  const r = c.elemento.getBoundingClientRect();
  const naTela = (v) => {
    const s = c.paraTela([v.x * 1000, v.y * 1000, v.z * 1000]);
    return [+s[0].toFixed(1), +s[1].toFixed(1)];
  };
  return JSON.stringify({
    dist: c.distancia,
    // na ortográfica a distância não muda com o zoom; o que muda é a escala
    escala: c.mmPorPixel(),
    direcao: d.map(v => v / n),
    alvo: [t.x, t.y, t.z],
    alvoNaTela: naTela(t),
    apoio: c.apoioDoZoom || '—',
    canvas: [r.left, r.top],
    focoNaTela: f ? naTela(f) : null,
    passo: cn._gradePasso,
    px: cn._gradePasso / mpp,
    opacidade: cn._gradeOpacidadeFina,
    linhas: cn.grade.children.reduce(
      (s, o) => s + o.geometry.attributes.position.count / 2, 0),
  });
})()
"""


def _roda(aba, x, y, delta):
    aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0,
            deltaY=delta, button="none", clickCount=0, modifiers=0)
    aba.drenar(0.25)
    return json.loads(aba.avaliar(ESTADO))


def _conferir(passos, sentido, cursor):
    """Problemas encontrados numa varredura, como pares (assunto, descrição)."""
    fora = []
    for a, b in zip(passos, passos[1:]):
        razao = b["escala"] / a["escala"] if sentido > 0 else a["escala"] / b["escala"]
        if not (1 + PASSO_MIN <= razao <= 1 + PASSO_MAX):
            fora.append(("passo", f"um clique mudou o zoom em {(razao - 1) * 100:.1f} %"
                                  f" ({a['escala']:.1f} → {b['escala']:.1f} mm por pixel)"))
        giro = sum(x * y for x, y in zip(a["direcao"], b["direcao"]))
        if giro < 0.9999:
            fora.append(("direcao", "a direção da vista mudou no zoom "
                                    f"(cosseno {giro:.5f}) com {a['dist']:.1f} m"))
        desvio = math.dist(a["alvoNaTela"], b["alvoNaTela"])
        if desvio > FOLGA_PX:
            fora.append(("alvo", f"o alvo andou {desvio:.1f} px na tela com "
                                 f"{a['dist']:.1f} m de distância"))
        if b["apoio"] == "alvo" and math.dist(a["alvo"], b["alvo"]) > 0.001:
            fora.append(("alvo", "sem apoio sob o cursor, o alvo devia ficar parado, "
                                 f"mas andou {math.dist(a['alvo'], b['alvo']) * 100:.1f} cm"))
    for p in passos[1:]:
        if p["focoNaTela"] and p["apoio"] != "alvo":
            # o cursor vem em coordenadas da janela; o foco, em pixels do canvas
            no_canvas = (cursor[0] - p["canvas"][0], cursor[1] - p["canvas"][1])
            erro = math.dist(p["focoNaTela"], no_canvas)
            if erro > FOLGA_PX:
                fora.append(("apoio", f"o ponto de apoio saiu {erro:.1f} px de baixo do "
                                      f"cursor (apoio: {p['apoio']})"))
        if not (PX_MIN * 0.9 <= p["px"] <= PX_MAX * 1.1):
            fora.append(("grade", f"linhas da grade a {p['px']:.1f} px, fora da faixa"
                                  f" ({PX_MIN:.0f}–{PX_MAX:.0f} px) com {p['dist']:.1f} m"))
        if p["linhas"] > 2500:
            fora.append(("grade", f"grade com {p['linhas']} linhas a {p['dist']:.1f} m"))
        if p["px"] < 10 and p["opacidade"] > 0.35:
            fora.append(("grade", f"linhas quase juntas ({p['px']:.1f} px) ainda opacas"
                                  f" ({p['opacidade']:.2f})"))
    escalas = [p["passo"] for p in passos]
    for i in range(2, len(escalas)):
        if escalas[i] == escalas[i - 2] != escalas[i - 1]:
            fora.append(("escala", f"a grade trocou de escala e voltou: {escalas[i - 2]}"
                                   f" → {escalas[i - 1]} → {escalas[i]} m"))
    return fora


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--saida", default=os.path.join(BASE, "projetos", "_editor_zoom.png"))
    ap.add_argument("--espera", type=float, default=60.0)
    ap.add_argument("--cliques", type=int, default=12)
    args = ap.parse_args()

    from nucleo.modelo_galpao import DadosGalpao
    dados = DadosGalpao(nome="Verificação de zoom", vao=20, comprimento=40,
                        pe_direito=6).dict()
    chrome = next((c for c in CHROMES if os.path.exists(c)), None)
    if not chrome:
        print("Chrome ou Edge não encontrado.")
        return 2
    base_url = f"http://localhost:{args.porta}"
    try:
        urllib.request.urlopen(base_url + "/", timeout=3)
    except Exception:
        print(f"Servidor fora do ar em {base_url}.")
        return 2

    porta_cdp = _porta_livre()
    perfil = tempfile.mkdtemp(prefix="verif_zoom_")
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
         "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
         "--remote-allow-origins=*", f"--user-data-dir={perfil}",
         f"--remote-debugging-port={porta_cdp}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    codigo = 0
    try:
        alvo = None
        for _ in range(60):
            alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list")
                     if t.get("type") == "page"]
            if alvos:
                alvo = alvos[0]
                break
            time.sleep(0.5)
        aba = Aba(alvo["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log"):
            aba.cmd(f"{dominio}.enable")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900,
                deviceScaleFactor=1, mobile=False)

        aba.navegar(base_url + "/")
        aba.avaliar(f"localStorage.setItem({json.dumps(CHAVE_ESTADO)}, "
                    f"{json.dumps(json.dumps(dados, ensure_ascii=False))})")
        aba.console.clear()
        aba.navegar(base_url + "/editor?galpao=1", limite=30)

        t0 = time.time()
        objetos = -1
        while time.time() - t0 < args.espera:
            aba.drenar(1.0)
            objetos = aba.avaliar(CONTAR_OBJETOS)
            if isinstance(objetos, int) and objetos > 0:
                aba.drenar(2.0)
                break
        if not (isinstance(objetos, int) and objetos > 0):
            print("O galpão não carregou; o zoom não foi verificado.")
            return 1

        problemas = []
        varreduras = []
        for rotulo, cursor, projecao in [
                ("cursor sobre o modelo", (520, 430), "perspectiva"),
                ("cursor no céu", (300, 110), "perspectiva"),
                ("cursor sobre o modelo", (520, 430), "ortografica")]:
            aba.avaliar(f"window.editor.camera.definirProjecao('{projecao}'); 1")
            aba.avaliar("window.editor.camera.zoomExtensao(); 1")
            aba.drenar(1.5)
            inicial = json.loads(aba.avaliar(ESTADO))
            fora = [inicial] + [_roda(aba, *cursor, 120) for _ in range(args.cliques)]
            perto = [fora[-1]] + [_roda(aba, *cursor, -120)
                                  for _ in range(args.cliques * 2)]
            problemas += _conferir(fora, +1, cursor) + _conferir(perto, -1, cursor)
            varreduras.append((f"{rotulo} ({projecao})", fora + perto))

        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        with open(args.saida, "wb") as f:
            f.write(base64.b64decode(png))

        for rotulo, passos in varreduras:
            apoios = sorted({p["apoio"] for p in passos[1:]})
            print(f"  {rotulo}: {min(p['dist'] for p in passos):.1f} m a "
                  f"{max(p['dist'] for p in passos):.1f} m, apoio em {apoios}, "
                  f"grade {sorted({p['passo'] for p in passos})} m")
        assuntos = {a for a, _ in problemas}
        for rotulo, assunto in [("o zoom anda o mesmo tanto a cada clique", "passo"),
                                ("o ponto de apoio fica parado sob o cursor", "apoio"),
                                ("o alvo fica parado na tela", "alvo"),
                                ("a direção da vista não muda no zoom", "direcao"),
                                ("a grade não troca de escala e volta", "escala"),
                                ("a grade fica na faixa de leitura", "grade")]:
            ok = assunto not in assuntos
            print(f"  {'ok   ' if ok else 'FALHA'} {rotulo}")
            codigo = codigo or (0 if ok else 1)
        for texto in dict.fromkeys(t for _, t in problemas):
            print("   -", texto)

        erros = [c for c in aba.console if c[0] in ("error", "excecao")]
        print(f"erros de JavaScript: {len(erros)}")
        for tipo, texto in erros[:10]:
            print(f"   [{tipo}] {texto[:300]}")
        if erros:
            codigo = 1
        print(f"captura: {args.saida}")
        aba.ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
