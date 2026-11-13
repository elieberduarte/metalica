# -*- coding: utf-8 -*-
"""A altura do chão sem a imagem de satélite (usuário, 13/11, Posto no modo ver, painel Terreno sem local: "o terreno não
habilita a parte de ajuste fino que já temos quando não tem uma imagem de satélite importada, poderia deixar essa ferramenta
disponível a mão para isso mesmo sem ter um terreno importado"; escolhido o caso A: a altura e o ajuste de 5 cm valem para
o chão liso do 3D e a sombra; os planos do chão seguem só com imagem; o Norte segue só com o local).

No modo ver, com cliques de verdade:
  A. sem local, o painel Terreno tem a Altura do chão (o nível e o Ajuste ±5 cm); o chão liso (e a sombra) sobe e desce;
     a frase diz onde o chão ficou; grava no projeto (`chao`); depois do F5 o chão volta na mesma altura;
  B. o local escolhido (coordenada colada, imagem de teste sem internet): a imagem vem na altura do chão (herda);
  C. Tirar o local: a altura fica (volta a ser a do chão sem local);
  D. o automático: o chão no pé da obra; sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_chao_sem_imagem_")
proj = os.path.join(DADOS, "obra")
os.makedirs(proj)
json.dump({"nome": "Obra sem imagem", "tipo": "ifc", "alterado": "2026-11-13T09:00:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
# com chumbadores 0,80 m abaixo da chapa (o Posto, 13/11): o pé da obra é a chapa, não a ponta deles
MODELO = _modelo()
if isinstance(MODELO.get("camadas"), dict):
    MODELO["camadas"]["Chumbadores"] = {"nome": "Chumbadores", "cor": "#9aa1ab", "visivel": True, "bloqueada": False}
_ch = next(e for e in MODELO["entidades"] if e.get("camada") == "Chapas" and e.get("vertices"))
_z0 = min(v[2] for v in _ch["vertices"])
_cx = sum(v[0] for v in _ch["vertices"]) / len(_ch["vertices"]); _cy = sum(v[1] for v in _ch["vertices"]) / len(_ch["vertices"])
for dx in (-60, 60):
    MODELO["entidades"].append({"id": f"chumb{dx}", "tipo": "barra", "nome": "CH1", "camada": "Chumbadores", "inicio": [_cx + dx, _cy, _z0 - 800],
                                "fim": [_cx + dx, _cy, _z0 + 40], "perfil": "FE RED 3/4''", "papel": "chumbador", "atributos": {}})
json.dump(MODELO, open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
amb = dict(os.environ, METALICA_TERRENO="1", METALICA_TERRENO_FALSO="1")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
API = base + "/api/projetos/obra/terreno"
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
        aba.drenar(0.25)
    return False


def clicar_no(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    aba.drenar(0.2)
    return True


def digitar(aba, sel, texto):
    aba.avaliar(f"(i => {{ i.focus(); i.select(); return 1; }})(document.querySelector({json.dumps(sel)}))")
    aba.cmd("Input.insertText", text=texto)
    aba.drenar(0.2)


# o chão liso no projeto (mm): o piso do visor fica 10 mm abaixo do chão
PISO = "(v => v.piso.position.z + v.cabecalho.origem[2] + 10)(window.visor)"
PE = "(v => v.zDoPiso(v._caixaModelo.clone()) + v.cabecalho.origem[2])(window.visor)"


def abrir_painel(aba):
    if not aba.avaliar("!!document.getElementById('terreno-q')"):
        aba.avaliar("document.getElementById('btn-terreno').click()")
    return esperar(aba, "!!document.getElementById('terreno-q')", 10)


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_chao_sem_imagem_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
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
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=860, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.estado)", 90), "o modo ver abre com o terreno carregado")
    aba.avaliar("window.__erros = []; addEventListener('error', e => __erros.push(String(e.message))); 1")
    pe = aba.avaliar(PE)

    print("A — sem local: a altura do chão")
    ok(_json(API)["terreno"] is None, "projeto sem local")
    ok(abrir_painel(aba), "o painel Terreno abre")
    ok(aba.avaliar("!!document.getElementById('terreno-cota-sel') && !!document.getElementById('terreno-ajuste')"),
       "sem local, o painel tem a Altura do chão e o Ajuste")
    ok(aba.avaliar("[...document.querySelectorAll('.painel-terreno .titulo-secao')].some(p => p.textContent === 'Altura do chão')"),
       "o título diz Altura do chão")
    ok(not aba.avaliar("!!document.getElementById('terreno-norte') || !!document.getElementById('terreno-plano-novo')"),
       "o Norte e os planos do chão só com o local/imagem")
    ok(abs(aba.avaliar(PISO) - pe) < 1, f"no automático, o chão no pé da obra ({aba.avaliar(PISO):.0f} mm)")
    # Outra cota… −0,50 e duas vezes +5 cm
    aba.avaliar("(s => { s.value = 'outra'; s.dispatchEvent(new Event('change')); return 1; })(document.getElementById('terreno-cota-sel'))")
    digitar(aba, "#terreno-cota", "-0,50")
    ok(abs(aba.avaliar(PISO) + 500) < 1, f"Outra cota −0,50: o chão desce para −0,50 ({aba.avaliar(PISO):.0f} mm)")
    clicar_no(aba, "[data-ajuste='50']"); clicar_no(aba, "[data-ajuste='50']")
    ok(abs(aba.avaliar(PISO) + 400) < 1, f"+5 cm duas vezes: −0,40 ({aba.avaliar(PISO):.0f} mm)")
    frase = aba.avaliar("document.getElementById('terreno-cota-final').textContent")
    ok(frase == "Chão em −0,40 (cota −0,50 + 10 cm).", f"a frase diz onde o chão ficou ({frase!r})")
    aba.drenar(1.2)                                     # o painel grava meio segundo depois do último clique
    e = _json(API)
    ok(e["terreno"] is None and e["chao"] == {"cota": -500.0, "ajuste": 100.0}, f"gravado no projeto sem local ({e['chao']})")
    # a sombra: o chão das Cenas e a sombra no piso usam a mesma altura
    ok(abs(aba.avaliar("window.visor.zDoChao() + window.visor.cabecalho.origem[2]") + 400) < 1, "o chão do visor (a sombra) em −0,40")

    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, "!!(window.ver3dPronto && window.terreno && window.terreno.estado)", 90), "F5")
    aba.avaliar("window.__erros = []; addEventListener('error', e => __erros.push(String(e.message))); 1")
    ok(esperar(aba, f"Math.abs({PISO} + 400) < 1", 10), f"depois do F5, o chão em −0,40 ({aba.avaliar(PISO):.0f} mm)")
    abrir_painel(aba)
    ok(aba.avaliar("document.getElementById('terreno-cota-sel').value") == "outra"
       and aba.avaliar("document.getElementById('terreno-ajuste').value") == "10", "o painel volta com −0,50 e 10 cm")

    print("B — o local escolhido herda a altura")
    aba.avaliar("""(() => { document.getElementById('terreno-q').value = '-24.956206, -53.4556926';
      document.getElementById('terreno-busca').requestSubmit(); return 1; })()""")
    ok(esperar(aba, "document.querySelectorAll('#terreno-resultados [data-i]').length === 1", 15), "a coordenada colada vira um resultado")
    aba.avaliar("document.querySelector('#terreno-resultados [data-i]').click()")
    ok(esperar(aba, "!!window.terreno.malha && !!window.terreno.imagem", 60), "a imagem de teste no chão")
    t = _json(API)
    ok(t["terreno"].get("cota") == -500.0 and t["terreno"].get("ajuste") == 100.0 and not t.get("chao"),
       f"o local herdou a altura ({t['terreno'].get('cota')}, {t['terreno'].get('ajuste')})")
    z = aba.avaliar("window.terreno.zChao")
    ok(abs(z - (-500 - 3 + 100)) < 1, f"a imagem em −0,40 ({z:.0f} mm)")
    ok(abs(aba.avaliar(PISO) + 400) < 1, "o chão liso continua em −0,40, embaixo da imagem")
    ok(aba.avaliar("[...document.querySelectorAll('.painel-terreno .titulo-secao')].some(p => p.textContent === 'Altura da imagem')"),
       "com imagem, o título volta a ser Altura da imagem")
    # a imagem no automático: no pé da obra = a chapa de base, não a ponta dos chumbadores (13/11, o mesmo do chão liso)
    aba.avaliar("(s => { s.value = 'auto'; s.dispatchEvent(new Event('change')); return 1; })(document.getElementById('terreno-cota-sel'))")
    aba.avaliar("(i => { i.value = '0'; i.dispatchEvent(new Event('input')); return 1; })(document.getElementById('terreno-ajuste'))")
    z, ponta = aba.avaliar("window.terreno.zChao"), aba.avaliar("(v => v._caixaModelo.min.z + v.cabecalho.origem[2])(window.visor)")
    ok(abs(z - (pe - 6)) < 1 and pe - ponta > 500, f"no automático, a imagem na chapa ({z:.0f} mm), não na ponta dos chumbadores ({ponta:.0f} mm)")
    ok(abs(aba.avaliar(PISO) - pe) < 1, "e o chão liso também")
    aba.avaliar("(s => { s.value = 'outra'; s.dispatchEvent(new Event('change')); return 1; })(document.getElementById('terreno-cota-sel'))")
    digitar(aba, "#terreno-cota", "-0,50")
    clicar_no(aba, "[data-ajuste='50']"); clicar_no(aba, "[data-ajuste='50']")
    aba.drenar(1.2)
    ok(abs(aba.avaliar("window.terreno.zChao") + 403) < 1, "de volta a −0,50 + 10 cm")

    print("C — Tirar o local")
    aba.avaliar("window.confirm = () => true; 1")
    clicar_no(aba, "#terreno-esquecer")
    ok(esperar(aba, "!window.terreno.t && !window.terreno.malha", 15), "o local saiu")
    e = _json(API)
    ok(e["terreno"] is None and e["chao"] == {"cota": -500.0, "ajuste": 100.0}, f"a altura ficou, no chão ({e['chao']})")
    ok(abs(aba.avaliar(PISO) + 400) < 1, "o chão liso continua em −0,40")

    print("D — o automático")
    abrir_painel(aba)
    aba.avaliar("(s => { s.value = 'auto'; s.dispatchEvent(new Event('change')); return 1; })(document.getElementById('terreno-cota-sel'))")
    aba.avaliar("(i => { i.value = '0'; i.dispatchEvent(new Event('input')); return 1; })(document.getElementById('terreno-ajuste'))")
    aba.drenar(1.2)
    ok(abs(aba.avaliar(PISO) - pe) < 1, f"de volta ao pé da obra ({aba.avaliar(PISO):.0f} mm)")
    ok(_json(API).get("chao") is None, "nada de chão no projeto")
    ok(not aba.avaliar("window.__erros"), f"sem erro no console ({aba.avaliar('window.__erros')})")
finally:
    for p in (nav, srv):
        try: p.kill()
        except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True)

print("FALHAS:", len(falhas))
for f in falhas: print("  -", f)
sys.exit(1 if falhas else 0)
