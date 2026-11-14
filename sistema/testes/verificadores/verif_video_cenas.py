# -*- coding: utf-8 -*-
"""O vídeo das cenas (usuário, 12/11: "fiz uma sequência de cenas… usar ela como ref. e o sistema ir passeando por elas como se
fosse uma câmera se movimentando"; aprovado: para em cada cena, o visual muda suave no caminho, na janela Exportar). Na tela
das Cenas, com cliques de verdade:
  A. o caminho (video_cenas.js): o voo contínuo (passa por todas, sem parar, a velocidade igual); a linha do tempo com as paradas; a câmera em arco (a distância ao alvo no meio é a média
     geométrica — não atravessa o prédio); o ângulo pelo caminho curto;
  B. Exportar › Vídeo MP4: o bloco Vídeo aparece, Tela e A3 apagados; "esta cena" só não basta (o botão apagado e o porquê);
     Várias com 3 cenas: o resumo diz 3 cenas e a duração;
  C. Gravar o vídeo (2 das 3: Frente no Dia → Topo na Noite, o voo contínuo): o MP4 na pasta cenas da obra ("Vídeo - <obra> (cenas).mp4"), 1920 × 1080, 30 quadros/s, a duração certa;
     o OpenCV lê o arquivo; o quadro do meio do trecho é diferente das duas paradas; o céu escurece suave no caminho (Dia → Noite);
     a abertura B e o fechamento A escolhidos nas miniaturas (12/11: "comparar lado a lado"): a obra escurecida com o logo
     claro; a última vista some no branco, só o logo ("não colocaria esse texto"); o vídeo tocando na janela;
  D. depois do vídeo a tela volta à cena de antes, com a vista dela;
  E. Cancelar no meio para e não grava;
  G. a cena gravada com o alvo a 1,36 km (o zoom na roda apontando o céu; 14/11, Filipin): o voo olha para a obra o tempo todo;
  F. sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_video_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_video_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_video_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
# o logo da empresa (o fechamento do vídeo e a marca d'água): uma faixa como o da Hermes, em cor e claro
from PIL import Image, ImageDraw
os.makedirs(os.path.join(DADOS, "fabrica", "marca"))
for nome, cor in (("logo.png", (53, 67, 76, 255)), ("logo_claro.png", (255, 255, 255, 255))):
    im = Image.new("RGBA", (1772, 229), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle((82, 68, 564, 145), fill=cor); d.rectangle((1621, 68, 1690, 145), fill=(195, 215, 115, 255))
    im.save(os.path.join(DADOS, "fabrica", "marca", nome))
srv =subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
API = f"{base}/api/projetos/obra/terreno/cenas"
PASTA = os.path.join(DADOS, "obra", "cenas")
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def clicar_no(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    aba.drenar(0.2)
    return True


def videos():
    return sorted(n for n in os.listdir(PASTA) if n.lower().endswith(".mp4")) if os.path.isdir(PASTA) else []


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_video_cenas_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")

    print("A — o caminho")
    r = aba.avaliar("""(async () => { const M = await import('/visor3d/video_cenas.js');
        const L = M.linhaDoTempo(3, { porTrecho: 2, parada: 1.5, fps: 30 });
        const a = { posicao: [10000, 0, 0], alvo: [0, 0, 0], fov: 40 }, b = { posicao: [0, 40000, 0], alvo: [0, 0, 0], fov: 60 };
        const m = M.cameraEntre(a, b, 0.5), r = Math.hypot(...m.posicao);
        return JSON.stringify({ total: L.total, seg: L.segundos, q0: L.quadro(0), q44: L.quadro(44), q60: L.quadro(60), q104: L.quadro(104),
          qfim: L.quadro(L.total - 1), r, fov: m.fov, ang: M.anguloEntre(350, 10, 0.5), s0: M.suave(0), s1: M.suave(1), sm: M.suave(0.5) }); })()""")
    r = json.loads(r)
    ok(r["total"] == 3 * 45 + 2 * 60 and abs(r["seg"] - 8.5) < 1e-9, f"a linha do tempo: 3 paradas de 1,5 s e 2 trechos de 2 s ({r['total']} quadros)")
    ok(r["q0"]["k"] == 0 and r["q44"]["parado"] and r["q60"]["i"] == 0 and r["q60"]["j"] == 1 and 0 < r["q60"]["k"] < 1, "parada na 1ª, depois o trecho até a 2ª")
    ok(r["qfim"]["i"] == 2 and r["qfim"]["j"] == 2, "termina parada na última")
    ok(abs(r["r"] - 20000) < 1, f"a câmera em arco: no meio a distância ao alvo é a média geométrica ({r['r']:.0f} mm)")
    ok(abs(r["fov"] - 50) < 1e-6 and abs(r["ang"]) < 1e-6 or abs(r["ang"] - 360) < 1e-6, f"a lente no meio; o sol de 350° a 10° passa por 0° ({r['ang']})")
    ok(r["s0"] == 0 and r["s1"] == 1 and abs(r["sm"] - 0.5) < 1e-9, "sai parada e chega parada")
    # o voo contínuo (12/11, depois da amostra-10: "não precisa nem parar na cena… como se fosse um drone"): três câmeras com
    # trechos bem diferentes (10 m e 60 m): passa por todas, sem parar no meio e com a mesma velocidade
    r = json.loads(aba.avaliar("""(async () => { const M = await import('/visor3d/video_cenas.js');
        const cams = [{ posicao: [30000, 0, 8000], alvo: [0, 0, 0], fov: 45 }, { posicao: [0, 30000, 9000], alvo: [0, 0, 0], fov: 45 },
                      { posicao: [-30000, 2000, 30000], alvo: [5000, 0, 0], fov: 45 }];
        const V = M.caminhoContinuo(cams, { porTrecho: 3, fps: 30 }), pos = [];
        for (let f = 0; f < V.total; f++) pos.push(V.quadro(f).cam.posicao);
        const passo = pos.slice(1).map((p, i) => Math.hypot(p[0] - pos[i][0], p[1] - pos[i][1], p[2] - pos[i][2]));
        const meio = passo.slice(32, -32), med = meio.reduce((a, b) => a + b, 0) / meio.length;
        const perto = Math.min(...pos.map(p => Math.hypot(p[0] - cams[1].posicao[0], p[1] - cams[1].posicao[1], p[2] - cams[1].posicao[2])));
        const d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
        return JSON.stringify({ total: V.total, ini: d(pos[0], cams[0].posicao), fim: d(pos[pos.length - 1], cams[2].posicao), perto, med,
          min: Math.min(...meio) / med, max: Math.max(...meio) / med, primeiro: passo[0] / med }); })()"""))
    ok(r["total"] == 181, f"o voo: 2 trechos de 3 s, sem parada ({r['total']} quadros)")
    ok(r["ini"] < 1 and r["fim"] < 1, "começa na 1ª cena e termina na última")
    ok(r["perto"] < 2 * r["med"], f"passa pela cena do meio ({r['perto']:.0f} mm dela)")
    ok(r["min"] > 0.8 and r["max"] < 1.25, f"a velocidade igual no voo, sem parar na cena do meio ({r['min']:.2f}–{r['max']:.2f} da média)")
    ok(r["primeiro"] < 0.3, "só a saída suave")

    # três cenas do 3D: frente (Dia), lado (Entardecer), topo (Noite)
    for nome, vista, fundo in (("Frente", "frente", "ceu"), ("Lado", "lado", "entardecer"), ("Topo", "iso", "noite")):
        clicar_no(aba, f"#barra-palco [data-vista={vista}]") if aba.avaliar("!!cenaApi.estado().cena") else None
        aba.avaliar(f"cenaApi.novaCena3d('{nome}'); 1")
        esperar(aba, f"cenaApi.estado().cena && cenaApi.estado().cena.nome === '{nome}'", 30)
        clicar_no(aba, f"#barra-palco [data-vista={vista}]"); clicar_no(aba, "#atualizar-vista"); aba.drenar(0.8)
        clicar_no(aba, f"#ambiente3d [data-v={fundo}]"); aba.drenar(0.8)
    ids = aba.avaliar("cenaApi.estado().cenas")
    ok(ids == ["frente", "lado", "topo"], f"as três cenas ({ids})")
    clicar_no(aba, ".cartao-cena[data-cena=lado]")
    esperar(aba, "cenaApi.estado().cena.id === 'lado'", 30); aba.drenar(1)
    cam_lado = aba.avaliar("JSON.stringify(cenaApi.estado().cena.camera)")

    print("B — Exportar › Vídeo MP4")
    aba.avaliar("try { localStorage.removeItem('metalica.exportarCenas'); } catch (e) {} 1")
    clicar_no(aba, "#exportar")
    ok(esperar(aba, "!!document.getElementById('exportar-caixa')", 10), "a janela abriu")
    clicar_no(aba, "input[name=formato][value=mp4]"); aba.drenar(0.3)
    ok(aba.avaliar("!document.getElementById('exportar-video').hidden"), "o bloco Vídeo aparece")
    ok(aba.avaliar("document.querySelector('input[name=lado][value=tela]').disabled && document.querySelector('input[name=lado][value=\"4961\"]').disabled"
                   " && !document.querySelector('input[name=lado][value=\"1920\"]').disabled"), "Tela e A3 apagados; Full HD e 4K valem")
    ok(aba.avaliar("document.getElementById('exportar-ir').disabled") and "duas cenas" in aba.avaliar("document.getElementById('exportar-situacao').textContent"),
       "esta cena só: o botão apagado e o porquê")
    clicar_no(aba, "input[name=quais][value=varias]")
    for c in ("frente", "lado", "topo"):
        if not aba.avaliar(f"document.querySelector('#exportar-varias input[value={c}]').checked"): clicar_no(aba, f"#exportar-varias input[value={c}]")
    clicar_no(aba, "input[name=lado][value=\"1920\"]"); clicar_no(aba, "input[name=qualidade][value=rapida]"); clicar_no(aba, "input[name=velocidade][value=rapido]")
    clicar_no(aba, "#exportar-abrir") if aba.avaliar("document.getElementById('exportar-abrir').checked") else None
    aba.drenar(0.3)
    info = aba.avaliar("document.getElementById('exportar-info').textContent")
    ok("3 cenas" in info and "~8 s" in info and "1.920 × 1.080" in info, f"o resumo: 3 cenas, ~8 s (o voo rápido + o fechamento), Full HD ({info})")
    ok(aba.avaliar("document.getElementById('exportar-ir').textContent") == "Gravar o vídeo", "o botão Gravar o vídeo")
    clicar_no(aba, "#exportar-varias input[value=lado]"); aba.drenar(0.3)     # o vídeo do teste: Frente (Dia) → Topo (Noite)
    info = aba.avaliar("document.getElementById('exportar-info').textContent")
    ok("2 cenas" in info and "~6 s" in info and "Frente → Topo" in info, f"sem a do meio, voo contínuo + fechamento: 2 cenas, ~6 s ({info})")
    # a abertura e o fechamento lado a lado (12/11: "as outras opções de fechamento e abertura escolher lá por dentro também,
    # para comparar lado a lado"): as miniaturas feitas com a vista e o logo; o fechamento A e nenhuma abertura no começo
    ok(esperar(aba, "window.cartoesDoVideo >= 4 && [...document.querySelectorAll('#exportar-cartoes .mini')].every(m => m.style.backgroundImage.startsWith('url'))", 120),
       "as miniaturas: abertura e fechamento (Nenhum, A, B, C)")
    minis = aba.avaliar("[...document.querySelectorAll('#exportar-cartoes .cartoes')].map(c => [...c.querySelectorAll('.mini')].map(m => m.style.backgroundImage.length + ':' + m.style.backgroundImage.slice(-40)))")
    ok(len(minis) == 2 and len(set(minis[1])) == 4, "as quatro do fechamento são diferentes")
    ok(aba.avaliar("document.querySelector('input[name=fecho]:checked').value") == "A" and aba.avaliar("document.querySelector('input[name=abertura]:checked').value") == "nenhuma"
       and not aba.avaliar("document.getElementById('exportar-texto').checked"),
       "o padrão: fechamento A, sem abertura, sem o texto (12/11: \"não colocaria esse texto\")")
    mini = lambda nome, v: f"label.cartao-op:has(input[name={nome}][value={v}]) .mini"
    clicar_no(aba, mini("fecho", "nenhum")); aba.drenar(0.3)
    ok("~2 s" in aba.avaliar("document.getElementById('exportar-info').textContent"), "fechamento Nenhum: ~2 s")
    clicar_no(aba, mini("fecho", "A")); aba.drenar(0.3)
    clicar_no(aba, "#exportar-parar"); aba.drenar(0.3)
    ok("~9 s" in aba.avaliar("document.getElementById('exportar-info').textContent"), "Parar um instante em cada cena: ~9 s")
    clicar_no(aba, "#exportar-parar"); aba.drenar(0.3)
    clicar_no(aba, mini("abertura", "B")); aba.drenar(0.3)
    ok(aba.avaliar("document.querySelector('input[name=abertura]:checked').value") == "B"
       and "~9 s" in aba.avaliar("document.getElementById('exportar-info').textContent"), "abertura B (sobre a obra): ~9 s")

    print("C — gravar o vídeo")
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    t0 = time.time()
    clicar_no(aba, "#exportar-ir")
    ok(esperar(aba, "/Vídeo · quadro/.test(document.getElementById('exportar-situacao').textContent)", 60), "a barra diz o quadro")
    ok(esperar(aba, "!!window.ultimoLoteCenas", 900), f"o vídeo terminou ({time.time() - t0:.0f} s)")
    lote = aba.avaliar("JSON.stringify(window.ultimoLoteCenas)"); lote = json.loads(lote or "{}")
    ok(not lote.get("erro") and lote.get("gravados") == ["Vídeo - Obra Teste (cenas).mp4"], f"gravado na pasta cenas ({lote.get('gravados')}, {lote.get('erro')})")
    v = lote.get("video") or {}
    ok(v.get("w") == 1920 and v.get("h") == 1080 and abs(v.get("segundos", 0) - 271 / 30) < 1e-6 and v.get("abertura") and v.get("fecho"),
       f"1920 × 1080: 3 s de abertura + 2 s de voo + 4 s de fechamento ({v})")
    ok(esperar(aba, "(v => !!v && v.duration > 8.9 && v.duration < 9.2)(document.getElementById('exportar-player'))", 30)
       and aba.avaliar("document.getElementById('exportar-previa').hidden"), "o vídeo pronto tocando na janela, no lugar da prévia")
    arq = os.path.join(PASTA, "Vídeo - Obra Teste (cenas).mp4")
    ok(os.path.isfile(arq) and open(arq, "rb").read(8)[4:8] == b"ftyp", "o arquivo é um MP4")
    ok("Pronto: vídeo de 2 cenas" in aba.avaliar("document.getElementById('exportar-situacao').textContent")
       and aba.avaliar("!document.getElementById('exportar-pasta').hidden"), "Pronto, com o Mostrar na pasta")
    try:
        import cv2
        cap = cv2.VideoCapture(arq)
        n, fps, w = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        ok(n == 271 and abs(fps - 30) < 0.01 and w == 1920, f"o OpenCV lê: {n} quadros, {fps} q/s, {w} px")
        def q(i):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i); _, f = cap.read(); cv2.imwrite(os.path.join(SAIDA, f"quadro-{i}.jpg"), f); return f
        abre, a0, meio, fim, sumindo, fecho = q(30), q(92), q(120), q(148), q(165), q(240)
        cap.release()                                       # o arquivo solto (o E apaga e grava de novo)
        # a abertura B: a obra escurecida e o logo claro no centro
        ca = cv2.cvtColor(abre, cv2.COLOR_BGR2GRAY); hh, ww = ca.shape
        ok(ca[: hh // 4].mean() < 110 and ca[int(hh * 0.45): int(hh * 0.55), int(ww * 0.25): int(ww * 0.75)].max() > 220,
           f"a abertura B: escura, o logo claro no centro ({ca[: hh // 4].mean():.0f})")
        # o fechamento (12/11, amostra-12 A; "não colocaria esse texto"): o fundo branco, só o logo no meio
        cinza = cv2.cvtColor(fecho, cv2.COLOR_BGR2GRAY)
        ok(cinza[: hh // 4].mean() > 245 and cinza[hh * 3 // 4:].mean() > 245, f"o fechamento: fundo branco ({cinza[: hh // 4].mean():.0f})")
        faixa = cinza[int(hh * 0.45): int(hh * 0.55), int(ww * 0.25): int(ww * 0.75)]
        ok(faixa.min() < 100, f"o logo no centro ({faixa.min()})")
        nome = cinza[int(hh * 0.57): int(hh * 0.68), int(ww * 0.3): int(ww * 0.7)]
        ok(nome.min() > 230, f"sem o texto embaixo do logo ({nome.min()})")
        ok(float(fim.mean()) < float(sumindo.mean()) < float(fecho.mean()), f"a última vista some no branco ({fim.mean():.0f} → {sumindo.mean():.0f} → {fecho.mean():.0f})")
        dif = lambda x, y: float(abs(x.astype(int) - y.astype(int)).mean())
        ok(dif(a0, meio) > 3 and dif(meio, fim) > 3, f"o meio do trecho é outro quadro ({dif(a0, meio):.1f}, {dif(meio, fim):.1f})")
        claro = lambda f: float(f[: f.shape[0] // 6].mean())
        ok(claro(a0) > claro(meio) + 10 > claro(fim) + 20, f"o céu escurece suave pelo caminho: Dia {claro(a0):.0f} → meio {claro(meio):.0f} → Noite {claro(fim):.0f}")
    except ImportError:
        ok(False, "o OpenCV (cv2) para ler o vídeo")

    print("D — a tela de volta")
    ok(aba.avaliar("cenaApi.estado().cena.id") == "lado", "a cena aberta de antes")
    cam_agora = aba.avaliar("JSON.stringify(visor.lerCamera())")
    ca, cb = json.loads(cam_lado), json.loads(cam_agora)
    ok(max(abs(ca["posicao"][k] - cb["posicao"][k]) for k in range(3)) < 5, "com a vista dela")

    print("E — Cancelar")
    antes = videos()
    os.remove(arq)
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    clicar_no(aba, "#exportar-ir")
    esperar(aba, "/Vídeo · quadro [1-9]/.test(document.getElementById('exportar-situacao').textContent)", 60)
    clicar_no(aba, "#exportar-cancelar")
    ok(esperar(aba, "!!window.ultimoLoteCenas", 120), "parou")
    ok(aba.avaliar("window.ultimoLoteCenas.erro") == "cancelado" and "cancelado" in aba.avaliar("document.getElementById('exportar-situacao').textContent"),
       "Vídeo cancelado")
    ok(not os.path.exists(arq), f"nada gravado ({videos()})")
    ok(aba.avaliar("cenaApi.estado().cena.id") == "lado", "a cena de antes de volta")

    print("G — a cena com o alvo a quilômetros (14/11, Filipin: 28 dos 55 s do vídeo só de céu)")
    # O zoom na roda apontando o céu leva o alvo da câmera a quilômetros e "Atualizar a cena" grava assim (a Cena 5 do Filipin,
    # 12/11: 1,36 km). Ao abrir a cena o visor o traz para perto; o voo usava o alvo cru e o trecho de 1,3 km comia o vídeo.
    # A câmera do Lado gravada com o alvo a 1,36 km; o voo Frente → Lado → Topo olha para a obra o tempo todo.
    arq_lado = os.path.join(DADOS, "obra", "cenas", "dados", "lado", "cena.json")
    c = json.load(open(arq_lado, encoding="utf-8"))
    p, a = c["camera"]["posicao"], c["camera"]["alvo"]
    d = [a[k] - p[k] for k in range(3)]; n = sum(x * x for x in d) ** 0.5
    c["camera"]["alvo"] = [p[k] + d[k] / n * 1360000 for k in range(3)]
    json.dump(c, open(arq_lado, "w", encoding="utf-8"), ensure_ascii=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&cena=frente", limite=90)
    ok(esperar(aba, "!!window.cenaPronta && !!visor._esferaModelo", 180), "a tela de novo, com o alvo do Lado a 1,36 km")
    aba.avaliar("""window.__alvos = []; window.__vooG = null; const def = visor.definirCamera.bind(visor);
      visor.definirCamera = (c) => { const r = def(c); const k = visor.lerCamera(); window.__alvos.push(k.posicao, k.alvo); return r; };
      const tela = document.createElement('canvas'); tela.width = 320; tela.height = 180;
      cenaApi.videoDasCenas({ ids: ['frente', 'lado', 'topo'], previa: tela, lado: 320, ss: 1, fecho: 'nenhum' })
        .then(r => { window.__vooG = 'ok'; }, e => { window.__vooG = 'erro: ' + e.message; }); 1""")
    ok(esperar(aba, "!!window.__vooG", 600) and aba.avaliar("window.__vooG") == "ok", f"o voo das três cenas ({aba.avaliar('window.__vooG')})")
    r = aba.avaliar("""(() => { const e = visor._esferaModelo, o = visor.cabecalho.origem, c = [e.center.x + o[0], e.center.y + o[1], e.center.z + o[2]];
      const q = window.__alvos.map(a => Math.hypot(a[0] - c[0], a[1] - c[1], a[2] - c[2]) / e.radius);
      return { n: q.length, max: Math.max(...q), longe: q.filter(x => x > 3).length }; })()""")
    ok(r["n"] >= 10 and r["max"] < 6, f"em todo o voo a câmera fica perto da obra e olha para ela ({r['n'] // 2} câmeras; a posição e o alvo a até {r['max']:.1f} raios; além de 3: {r['longe']})")

    print("F — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill(); time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print(f"FALHAS: {len(falhas)}")
for f in falhas: print("  -", f)
sys.exit(1 if falhas else 0)
