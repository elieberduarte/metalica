# -*- coding: utf-8 -*-
"""O modo ver separa o pré-moldado da metálica (usuário, Mercado Conceito, 16/10/2026: "criar uma camada nova para
separar apenas pré-moldado (estrutura) e metálica para apresentação ao cliente") e a legenda do Pintar vai em ordem
alfabética ("organizar por ordem alfabética"). Num modelo como o do Mercado — o IFC do pré-moldado (concreto, e as
porcas, arruelas e o neoprene das ligações dele, na mesma camada) com a nossa cobertura (barras sem material) e uma
descida de PVC:
  1. Pintar "por sistema": Metálica, Outros e Pré-moldado (concreto), cada peça no seu;
  2. a seção Sistema no alto de Camadas e do Pintar: desligar a Metálica a esconde em qualquer modo do Pintar e
     continua escondida depois de recarregar (o projeto atualizado);
  3. a legenda por perfil em ordem alfabética;
  4. num projeto só de aço não há "por sistema" nem a seção.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _caixa_solido, _modelo

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ver3d_sistema_")


def _peca(id_, x, nome, material, camada, z=0.0):
    e = _caixa_solido(id_, x, 0.0, z, a=300, b=300, c=300, camada=camada)
    e["material"], e["nome"] = material, nome
    e["atributos"] = {"marcas": {"perfil": nome}}
    return e


PRE = "200 Pré-Fabricado"
ents = [_peca("pil%d" % i, 1000.0 * i, "Pilar", "CONCRETE/Fck-40", PRE) for i in range(3)]
ents += [_peca("laj%d" % i, 1000.0 * i, "Laje Alveolar", "CONCRETE/Fck-40", PRE, z=3000) for i in range(3)]
ents += [_peca("est0", 0.0, "Estaca", "CONCRETE/Fck-25", PRE, z=-2000)]
ents += [_peca("por0", 5000.0, "PORCA 3/4", "STEEL/A325", PRE), _peca("neo0", 6000.0, "Neoprene", "STEEL/SHORE A-60", PRE)]
ents += [_peca("pvc0", 8000.0, "Descida Pluvial", "MISCELLANEOUS/PVC", "400 Descidas pluviais")]
for i, perfil in enumerate(["U 150×60×3,00 (FF)", "L 2\"×3/16\"", "Ue 250×85×25×2,65", "L 1½\"×3/16\""]):
    ents.append({"id": "bar%d" % i, "tipo": "barra", "nome": "banzo", "camada": "Tesouras", "material": "",
                 "inicio": [0, 1000.0 * i, 6000], "fim": [6000, 1000.0 * i, 6000], "perfil": perfil, "rotacao": 0.0})
camadas = {n: {"nome": n, "cor": "#888888", "visivel": True} for n in (PRE, "400 Descidas pluviais", "Tesouras")}
for nome, modelo in (("obra", {"nome": "obra", "unidade": "mm", "entidades": ents, "camadas": camadas, "materiais": {}}), ("aco", _modelo())):
    os.makedirs(os.path.join(DADOS, nome))
    json.dump({"nome": nome, "tipo": "ifc", "alterado": "2026-10-16T09:00:00"}, open(os.path.join(DADOS, nome, "projeto.json"), "w", encoding="utf-8"))
    json.dump(modelo, open(os.path.join(DADOS, nome, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
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


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ver3d_sistema_")
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

    PRONTO = "!!(window.ver3dPronto && window.visor && visor.fichas)"
    PINTAR = "(() => { const s = document.getElementById('pintar'); s.value = '%s'; s.dispatchEvent(new Event('change')); return 1; })()"
    LEGENDA = "JSON.stringify([...document.querySelectorAll('#painel-corpo [data-olho]')].map(c => { const l = c.closest('.linha-lista'); return [l.querySelector('span').textContent, +l.querySelector('em').textContent, c.checked]; }))"
    SISTEMA = "JSON.stringify([...document.querySelectorAll('#painel-corpo input[data-sistema]')].map(c => [c.dataset.sistema, c.checked]))"

    aba.navegar(base + "/visor3d/ver3d.html?projeto=obra", limite=60)
    ok(esperar(aba, PRONTO, 90), "o modo ver abriu (%s peças)" % aba.avaliar("window.visor && visor.nPecas"))

    # 1. por sistema
    ok(aba.avaliar("!!document.querySelector('#pintar option[value=sistema]')"), "o Pintar tem \"por sistema\"")
    aba.avaliar(PINTAR % "sistema")
    leg = json.loads(aba.avaliar(LEGENDA) or "[]")
    ok([x[:2] for x in leg] == [["Metálica", 4], ["Outros", 1], ["Pré-moldado (concreto)", 9]],
       f"por sistema: a metálica (as barras), o PVC em Outros, o concreto com as porcas e o neoprene dele no pré-moldado ({leg})")
    ok(aba.avaliar("document.getElementById('painel-titulo').textContent") == "Pintado por sistema", "o título da legenda")
    ok(aba.avaliar("document.querySelectorAll('#painel-corpo input[data-sistema]').length") == 0,
       "por sistema, a legenda já é o Sistema (sem a seção repetida)")

    # 2. a seção Sistema em Camadas: desligar a metálica, em qualquer modo do Pintar, e depois de recarregar
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    sis = json.loads(aba.avaliar(SISTEMA) or "[]")
    ok([s[0] for s in sis] == ["metalica", "outros", "premoldado"] and all(s[1] for s in sis), f"Camadas: a seção Sistema ({sis})")
    aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=metalica]').click()")
    BARRAS = "visor.fichas.map((f, i) => i).filter(i => /^bar/.test(visor.fichas[i].id))"
    ok(aba.avaliar(f"(() => {{ const b = {BARRAS}; return b.length === 4 && b.every(i => visor.ocultasSistema.has(i)) && visor.ocultasSistema.size === 4; }})()"),
       "desligar a Metálica esconde as 4 barras, e só elas")
    aba.avaliar(PINTAR % "perfil")
    ok(aba.avaliar("visor.ocultasSistema.size") == 4, "trocar o Pintar para por perfil não traz a metálica de volta")
    ok(aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=metalica]').checked") is False,
       "e a seção Sistema no alto da legenda mostra a Metálica desligada")
    # o grupo do perfil oculto e o sistema não se atrapalham: ocultar e mostrar o Pilar não mostra a metálica
    aba.avaliar("(() => { const c = [...document.querySelectorAll('#painel-corpo [data-olho]')].find(c => c.closest('.linha-lista').querySelector('span').textContent === 'Pilar'); c.click(); c.click(); return 1; })()")
    ok(aba.avaliar("visor.ocultasSistema.size") == 4 and aba.avaliar("visor.ocultas.size") == 0, "ocultar e mostrar um perfil não mexe no sistema")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, PRONTO, 60), "recarregado (o projeto atualizado)")
    ok(aba.avaliar(f"(() => {{ const b = {BARRAS}; return b.every(i => visor.ocultasSistema.has(i)) && visor.ocultasSistema.size === 4; }})()"),
       "a Metálica continua desligada depois de recarregar")

    # 3. a legenda por perfil em ordem alfabética (antes: da que tinha mais peças para a que tinha menos)
    aba.avaliar(PINTAR % "perfil")
    nomes = [x[0] for x in json.loads(aba.avaliar(LEGENDA) or "[]")]
    esperado = ["Descida Pluvial", "Estaca", "L 1½\"×3/16\"", "L 2\"×3/16\"", "Laje Alveolar", "Neoprene", "Pilar", "PORCA 3/4",
                "U 150×60×3,00 (FF)", "Ue 250×85×25×2,65"]
    ok(nomes == esperado, f"por perfil, em ordem alfabética ({nomes})")
    aba.avaliar(PINTAR % "camada")
    nomes = [x[0] for x in json.loads(aba.avaliar(LEGENDA) or "[]")]
    ok(nomes == ["200 Pré-Fabricado", "400 Descidas pluviais", "Tesouras"], f"por camada também ({nomes})")

    # 4. só aço: nada a separar
    aba.navegar(base + "/visor3d/ver3d.html?projeto=aco", limite=60)
    ok(esperar(aba, PRONTO, 90), "o projeto só de aço abriu")
    ok(not aba.avaliar("!!document.querySelector('#pintar option[value=sistema]')"), "só aço: sem \"por sistema\" no Pintar")
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    ok(aba.avaliar("document.querySelectorAll('#painel-corpo input[data-sistema]').length") == 0, "só aço: sem a seção Sistema")

    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
