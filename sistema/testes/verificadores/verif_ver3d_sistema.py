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
  4. num projeto só de aço não há "por sistema" nem a seção;
  6. SESI Chapecó (22/10): a Cobertura é a das telhas (o grupo "Cobertura frontal…" de tesouras é Metálica; a camada
     "ARQ — Telhas", de Concreto, e o material Telha são Cobertura) — desligá-la esconde as telhas do arquitetônico;
     o resto do arquitetônico de referência ("ARQ — …": o pilar de Concreto, o forro e o brise de Vidro) é o sistema
     "Arquitetônico (referência)", não Pré-moldado nem Outros (TEL-02, 4ª vez: VER-10, "o que são esses 'outros'?").
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
# o terreno, a rua e a calçada (lajes de concreto no IFC do Mercado) num sistema só; a parede fica no pré-moldado
ents += [_peca("ter0", 0.0, "Terreno", "CONCRETE/Fck-40", PRE, z=-500), _peca("rua0", 2000.0, "Rua ", "CONCRETE/Fck-40", PRE, z=-500),
         _peca("cal0", 4000.0, "Calçada", "CONCRETE/Fck-40", PRE, z=-500), _peca("par0", 9000.0, "Parede", "CONCRETE/Fck-40", "3 Arquitetura")]
# o muro e as vagas também (Mercado, 20/10), e a peça que o usuário mandou à mão para a camada Terreno, pelo nome da camada
ents += [_peca("mur0", 10000.0, "Muro ", "CONCRETE/Fck-40", PRE, z=-500), _peca("vag0", 11000.0, "Vaga", "CONCRETE/Fck-40", PRE, z=-500),
         _peca("blo9", 12000.0, "Bloco", "CONCRETE/Fck-40", "Terreno", z=-500)]
for i, perfil in enumerate(["U 150×60×3,00 (FF)", "L 2\"×3/16\"", "Ue 250×85×25×2,65", "L 1½\"×3/16\""]):
    ents.append({"id": "bar%d" % i, "tipo": "barra", "nome": "banzo", "camada": "Tesouras", "material": "",
                 "inicio": [0, 1000.0 * i, 6000], "fim": [6000, 1000.0 * i, 6000], "perfil": perfil, "rotacao": 0.0})
camadas = {n: {"nome": n, "cor": "#888888", "visivel": True} for n in (PRE, "3 Arquitetura", "400 Descidas pluviais", "Tesouras", "Terreno")}
# o SESI Chapecó (22/10): o grupo "Cobertura frontal e eixo 1" é de tesouras e pilares (metálica, não telha), e as telhas
# do arquitetônico são sólidos de Concreto na camada "ARQ — Telhas" (cobertura, não pré-moldado); o material Telha conta;
# o lançamento de telhas (camadas Telhas/Calhas no grupo dele) continua na cobertura; o suporte da calha é metálica
TES, ARQT, ARQP = "Cobertura frontal e eixo 1 — Tesouras", "ARQ — Telhas", "ARQ — Pilares de concreto"
GLANC = "Cobertura — telhas, calhas e rufos"
sesi = [{"id": "tes%d" % i, "tipo": "barra", "nome": "banzo", "camada": TES, "material": "", "perfil": "L 2\"×3/16\"", "rotacao": 0.0,
         "inicio": [0, 1000.0 * i, 15000], "fim": [6000, 1000.0 * i, 15000]} for i in range(3)]
sesi += [{"id": "sup0", "tipo": "barra", "nome": "suporte", "camada": "Fachadas — Suporte da calha", "material": "", "perfil": "L 2\"×3/16\"",
          "rotacao": 0.0, "inicio": [0, 5000.0, 15000], "fim": [600, 5000.0, 15000]}]
sesi += [_peca("arqt%d" % i, 1000.0 * i, "Cobertura do ginásio", "Concreto", ARQT, z=17000) for i in range(2)]
sesi += [_peca("arqp0", 0.0, "Pilar", "Concreto", ARQP), _peca("tel0", 3000.0, "Telha avulsa", "Telha", "Fechamento", z=17000),
         _peca("lt0", 4000.0, "TP40", "Aço galvanizado", "Telhas", z=17000), _peca("lc0", 5000.0, "Calha", "Aço galvanizado", "Calhas", z=17000)]
# a pele de ACM da platibanda (22/10: "não está vinculada a camada da cobertura no sistema") vai com a Cobertura; a
# estrutura metálica da platibanda, não
sesi += [_peca("acm0", 6000.0, "Platibanda fachada A — ACM e estrutura", "Concreto", "ARQ — Platibandas", z=16000),
         {"id": "plm0", "tipo": "barra", "nome": "montante", "camada": "Fachadas — Platibanda", "material": "", "perfil": "L 2\"×3/16\"",
          "rotacao": 0.0, "inicio": [0, 7000.0, 15000], "fim": [0, 7000.0, 18000]}]
# a peça pelo nome (TEL-02, 3ª vez, 22/10): a calha e o rufo do arquitetônico na camada "ARQ — Outros", de Concreto
sesi += [_peca("cal1", 8000.0, "Calha da borda sul do ginásio", "Concreto", "ARQ — Outros", z=17000),
         _peca("ruf1", 9000.0, "Rufo da platibanda sul", "Concreto", "ARQ — Outros", z=17000)]
# o resto do arquitetônico de referência (VER-10, 22/10: os forros, venezianas e brises de Vidro caíam em Outros)
sesi += [_peca("for0", 10000.0, "Forro P.D. 3.00 Térreo", "Vidro", "ARQ — Forros", z=3000),
         _peca("bri0", 11000.0, "Brise fachada A - módulo 1 (+3,96)", "Vidro", "ARQ — Brises do arquitetônico", z=4000)]
cam_sesi = {TES: {"nome": TES, "cor": "#888888", "visivel": True, "grupo": "Cobertura frontal e eixo 1"},
            "Fachadas — Suporte da calha": {"nome": "Fachadas — Suporte da calha", "cor": "#888888", "visivel": True},
            ARQT: {"nome": ARQT, "cor": "#cfd6e0", "visivel": True, "grupo": "ARQUITETÔNICO"},
            ARQP: {"nome": ARQP, "cor": "#9aa3ad", "visivel": True, "grupo": "ARQUITETÔNICO"},
            "Fechamento": {"nome": "Fechamento", "cor": "#888888", "visivel": True},
            "Telhas": {"nome": "Telhas", "cor": "#888888", "visivel": True, "grupo": GLANC},
            "Calhas": {"nome": "Calhas", "cor": "#888888", "visivel": True, "grupo": GLANC},
            "ARQ — Platibandas": {"nome": "ARQ — Platibandas", "cor": "#bfbfbf", "visivel": True, "grupo": "ARQUITETÔNICO"},
            "Fachadas — Platibanda": {"nome": "Fachadas — Platibanda", "cor": "#888888", "visivel": True},
            "ARQ — Outros": {"nome": "ARQ — Outros", "cor": "#c9c0b0", "visivel": True, "grupo": "ARQUITETÔNICO"},
            "ARQ — Forros": {"nome": "ARQ — Forros", "cor": "#dfe6ee", "visivel": True, "grupo": "ARQUITETÔNICO"},
            "ARQ — Brises do arquitetônico": {"nome": "ARQ — Brises do arquitetônico", "cor": "#6fa8dc", "visivel": True}}
for nome, modelo in (("obra", {"nome": "obra", "unidade": "mm", "entidades": ents, "camadas": camadas, "materiais": {}}), ("aco", _modelo()),
                     ("sesi", {"nome": "sesi", "unidade": "mm", "entidades": sesi, "camadas": cam_sesi, "materiais": {}})):
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
    ok([x[:2] for x in leg] == [["Metálica", 4], ["Outros — PVC", 1], ["Pré-moldado (concreto)", 10], ["Terreno, rua e calçada", 6]],
       f"por sistema: a metálica (as barras), o PVC em 'Outros — PVC' (TEL-02: Outros só com o motivo no nome), o concreto (e a parede) com as porcas e o neoprene dele no pré-moldado, "
       f"o terreno, a rua, a calçada, o muro, a vaga e a camada Terreno juntos ({leg})")
    ok(aba.avaliar("document.getElementById('painel-titulo').textContent") == "Pintado por sistema", "o título da legenda")
    ok(aba.avaliar("document.querySelectorAll('#painel-corpo input[data-sistema]').length") == 0,
       "por sistema, a legenda já é o Sistema (sem a seção repetida)")

    # 2. a seção Sistema em Camadas: desligar a metálica, em qualquer modo do Pintar, e depois de recarregar
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    sis = json.loads(aba.avaliar(SISTEMA) or "[]")
    ok([s[0] for s in sis] == ["metalica", "outros", "premoldado", "terreno"] and all(s[1] for s in sis), f"Camadas: a seção Sistema ({sis})")
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
    esperado = ["Bloco", "Calçada", "Descida Pluvial", "Estaca", "L 1½\"×3/16\"", "L 2\"×3/16\"", "Laje Alveolar", "Muro ", "Neoprene",
                "Parede", "Pilar", "PORCA 3/4", "Rua ", "Terreno", "U 150×60×3,00 (FF)", "Ue 250×85×25×2,65", "Vaga"]
    ok(nomes == esperado, f"por perfil, em ordem alfabética ({nomes})")
    aba.avaliar(PINTAR % "camada")
    nomes = [x[0] for x in json.loads(aba.avaliar(LEGENDA) or "[]")]
    ok(nomes == ["3 Arquitetura", "200 Pré-Fabricado", "400 Descidas pluviais", "Terreno", "Tesouras"], f"por camada também, com os números em ordem ({nomes})")

    # 5. trocar a cor (usuário, 16/10: "não consigo alterar a cor das camadas?"): o quadradinho abre o seletor de cor
    COR = "(() => { const i = visor.fichas.findIndex(f => f.id === '%s'); return [visor.corBase[i * 3], visor.corBase[i * 3 + 1], visor.corBase[i * 3 + 2]]; })()"
    TROCAR = "(() => { const s = document.getElementById('seletor-cor'); s.value = '%s'; s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change')); return 1; })()"
    aba.avaliar(PINTAR % "sistema")
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    aba.avaliar("document.querySelector('#painel-corpo i.cor[data-cor-chave=premoldado]').click()")
    ok(aba.avaliar("!!document.getElementById('seletor-cor')"), "clicar no quadradinho do Pré-moldado abre o seletor de cor")
    ok(aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=premoldado]').checked") is True,
       "e não desmarca a caixinha do lado")
    aba.avaliar(TROCAR % "#ff0000")
    ok(aba.avaliar(COR % "pil0") == [255, 0, 0], f"o pré-moldado fica vermelho ({aba.avaliar(COR % 'pil0')})")
    ok(aba.avaliar(COR % "ter0") != [255, 0, 0], "o terreno não")
    # a cor de um perfil, na legenda
    aba.avaliar(PINTAR % "perfil")
    aba.avaliar("(() => { const l = [...document.querySelectorAll('#painel-corpo .linha-lista')].find(l => l.querySelector('span').textContent === 'Pilar'); l.querySelector('i.cor').click(); return 1; })()")
    ok(aba.avaliar("visor.selecionada") in (None, -1) or aba.avaliar("visor.fichas[visor.selecionada] && visor.fichas[visor.selecionada].id") != "pil0",
       "o clique no quadradinho não vai à peça do grupo")
    aba.avaliar(TROCAR % "#00ff00")
    ok(aba.avaliar(COR % "pil0") == [0, 255, 0], "por perfil, o Pilar verde")
    # a cor de uma camada, com o Pintar em outro modo: passa a pintar por camada
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    aba.avaliar("document.querySelector('#painel-corpo i.cor[data-cor-chave=Tesouras]').click()")
    aba.avaliar(TROCAR % "#0000ff")
    ok(aba.avaliar("document.getElementById('pintar').value") == "camada" and aba.avaliar(COR % "bar0") == [0, 0, 255],
       "trocar a cor da camada Tesouras passa o Pintar para por camada, com as barras azuis")
    aba.avaliar("location.reload(); 1")
    aba.drenar(1.0)
    ok(esperar(aba, PRONTO, 60), "recarregado")
    ok(aba.avaliar(COR % "bar0") == [0, 0, 255], "a cor da camada continua depois de recarregar")
    aba.avaliar(PINTAR % "sistema")
    ok(aba.avaliar(COR % "pil0") == [255, 0, 0], "e a do sistema também")
    aba.avaliar(PINTAR % "perfil")
    ok(aba.avaliar(COR % "pil0") == [0, 255, 0], "e a do perfil também")

    # 4. só aço: nada a separar
    aba.navegar(base + "/visor3d/ver3d.html?projeto=aco", limite=60)
    ok(esperar(aba, PRONTO, 90), "o projeto só de aço abriu")
    ok(not aba.avaliar("!!document.querySelector('#pintar option[value=sistema]')"), "só aço: sem \"por sistema\" no Pintar")
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    ok(aba.avaliar("document.querySelectorAll('#painel-corpo input[data-sistema]').length") == 0, "só aço: sem a seção Sistema")

    # 6. SESI Chapecó (22/10): desligar a Cobertura esconde as telhas (as do arquitetônico também) e não as tesouras
    aba.navegar(base + "/visor3d/ver3d.html?projeto=sesi", limite=60)
    ok(esperar(aba, PRONTO, 90), "o projeto do SESI abriu")
    aba.avaliar(PINTAR % "sistema")
    leg = json.loads(aba.avaliar(LEGENDA) or "[]")
    ok([x[:2] for x in leg] == [["Arquitetônico (referência)", 3], ["Cobertura — telhas, calhas e rufos", 8], ["Metálica", 5]],
       f"SESI por sistema: as 2 telhas do arquitetônico, a de material Telha, a telha e a calha lançadas, o ACM da platibanda e a calha e o rufo do arq em 'ARQ — Outros' (pelo nome) na "
       f"Cobertura; as 3 barras do grupo 'Cobertura frontal', o suporte da calha e o montante da platibanda na Metálica; o pilar de concreto, o forro e o brise de vidro do arq no Arquitetônico — nada em Outros nem no Pré-moldado ({leg})")
    aba.avaliar("document.querySelector('[data-painel=camadas]').click()")
    aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=cobertura]').click()")
    ID = "visor.fichas.findIndex(f => f.id === '%s')"
    ok(aba.avaliar("[%s].every(i => visor.ocultasSistema.has(i))" % ",".join(ID % k for k in ("arqt0", "arqt1", "tel0", "lt0", "lc0", "acm0", "cal1", "ruf1"))),
       "desligar a Cobertura esconde as telhas do arquitetônico (camada 'ARQ — Telhas', de Concreto) o ACM da platibanda e a calha e o rufo de 'ARQ — Outros'")
    ok(aba.avaliar("[%s].every(i => !visor.ocultasSistema.has(i))" % ",".join(ID % k for k in ("tes0", "tes1", "tes2", "sup0", "arqp0", "plm0"))),
       "e não as tesouras do grupo 'Cobertura frontal e eixo 1', o suporte da calha, o montante da platibanda e o pilar")
    aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=cobertura]').click()")
    aba.avaliar("document.querySelector('#painel-corpo input[data-sistema=arquitetonico]').click()")
    ok(aba.avaliar("[%s].every(i => visor.ocultasSistema.has(i))" % ",".join(ID % k for k in ("arqp0", "for0", "bri0")))
       and aba.avaliar("[%s].every(i => !visor.ocultasSistema.has(i))" % ",".join(ID % k for k in ("arqt0", "acm0", "tes0", "plm0"))),
       "desligar o Arquitetônico esconde o pilar, o forro e o brise do arq, e não as telhas do arq (Cobertura) nem a metálica")

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
