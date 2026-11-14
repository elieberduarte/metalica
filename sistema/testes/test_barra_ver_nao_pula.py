# -*- coding: utf-8 -*-
"""A barra do modo ver não pula (GESTÃO N.9, 14/11 — conferência da 0.9.3: o Terreno aparecia à esquerda do Cenas quando a
rota do terreno respondia, e o clique no Cenas caía no Terreno). Regra: nenhum botão da barra muda de lugar depois que ela
já aceita clique. A tela de verdade (com as respostas atrasadas e o clique do mouse) é o verif_barra_ver_nao_pula.py;
aqui, sem navegador:
  1. no ver3d.html, o que começa escondido na barra fica todo na ponta (nada escondido antes de um botão que já aparece);
  2. o ver3d.js só mostra/esconde os itens da barra pela pontaDaBarra (nada de `.hidden =` direto num item dela);
  3. a pontaDaBarra (rodada no Node) mostra os itens na ordem, decidam eles na ordem que for: nunca aparece um item à
     esquerda de outro que já estava na tela."""
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "visor3d"))


def _barra():
    html = open(os.path.join(WEB, "ver3d.html"), encoding="utf-8").read()
    bloco = html.split('<div id="ferramentas"', 1)[1].split("\n</div>", 1)[0]
    itens = []                                                   # (id ou texto, escondido) dos filhos diretos
    for linha in bloco.split("\n")[1:]:
        m = re.match(r"  <(button|span|label|input)\b([^>]*)>", linha)
        if not m:
            continue
        attrs = m.group(2)
        nome = re.search(r'id="([^"]+)"', attrs) or re.search(r'(data-[\w-]+)', attrs)
        itens.append((nome.group(1) if nome else linha.strip()[:40], bool(re.search(r"\shidden(\s|$|>)", attrs + " "))))
    return itens


def test_o_que_comeca_escondido_fica_na_ponta():
    itens = _barra()
    assert any(n == "btn-cenas" for n, _ in itens), itens
    primeiro = next(i for i, (_, h) in enumerate(itens) if h)
    depois = [n for n, h in itens[primeiro:] if not h]
    assert not depois, ("escondido antes de um botão que já aparece (vai empurrá-lo quando aparecer): %s antes de %s"
                        % (itens[primeiro][0], depois))
    for n in ("btn-planta", "btn-terreno", "cobertura"):
        assert (n, True) in itens, (n, itens)


def test_o_js_so_mexe_na_ponta_pela_pontadabarra():
    js = open(os.path.join(WEB, "ver3d.js"), encoding="utf-8").read()
    ids = [n for n, _ in _barra() if not n.startswith("data-")] + ["data-cobertura"]
    for n in ids:
        sel = r"\[%s\]" % n if n.startswith("data-") else "#" + re.escape(n)
        direto = re.findall(r"(?:\$|querySelector)\('%s'\)[^;\n]*\.hidden\s*=" % sel, js)
        assert not direto, (n, direto)
    for n in ("cobertura", "planta", "terreno"):
        assert re.search(r"pontaDaBarra\('%s'" % n, js), n
    # o atalho antigo da planta: b = $('#btn-planta') ... b.hidden =
    assert not re.search(r"\bb\.hidden\s*=\s*!?tem", js)


NODE = r"""
const js = %s;
const ini = js.indexOf('const ORDEM_DA_PONTA'), fim = js.indexOf('\n}\n', js.indexOf('function mostrarNaPonta')) + 3;
const ordemDom = ['[data-cobertura]', '#cobertura', '#sep-chao', '#btn-planta', '#btn-terreno'];
const saida = [];
for (const seq of %s) {
  const els = Object.fromEntries(ordemDom.map(s => [s, { hidden: true }]));
  const window = {};
  const $ = s => els[s];
  const f = new Function('$', 'window', js.slice(ini, fim) + '\nreturn pontaDaBarra;')($, window);
  const visto = [];                                   // a ordem em que cada item apareceu
  for (const [nome, ver] of seq) {
    f(nome, ver);
    for (const s of ordemDom) if (!els[s].hidden && !visto.includes(s)) visto.push(s);
  }
  saida.push({ seq, visto, assentada: !!window.ver3dBarraAssentada, final: ordemDom.filter(s => !els[s].hidden) });
}
console.log(JSON.stringify({ ordemDom, saida }));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node no computador")
def test_a_ponta_aparece_na_ordem_decida_ela_como_for():
    js = open(os.path.join(WEB, "ver3d.js"), encoding="utf-8").read()
    seqs = []
    for vers in itertools.product([True, False], repeat=3):
        for perm in itertools.permutations(range(3)):
            nomes = ["cobertura", "planta", "terreno"]
            seqs.append([[nomes[i], vers[i]] for i in perm])
    pasta = tempfile.mkdtemp(prefix="barra_ver_")
    try:
        script = os.path.join(pasta, "t.js")
        open(script, "w", encoding="utf-8").write(NODE % (json.dumps(js), json.dumps(seqs)))
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    ordem = a["ordemDom"]
    for c in a["saida"]:
        pos = [ordem.index(s) for s in c["visto"]]
        assert pos == sorted(pos), ("um item apareceu à esquerda de outro que já estava na tela", c)
        assert c["assentada"], c
        dec = dict(c["seq"])
        quer = [s for s, n in (("[data-cobertura]", "cobertura"), ("#cobertura", "cobertura"), ("#btn-planta", "planta"),
                               ("#btn-terreno", "terreno")) if dec[n]]
        if dec["planta"] or dec["terreno"]:
            quer.append("#sep-chao")
        assert sorted(c["final"], key=ordem.index) == sorted(quer, key=ordem.index), c
