# -*- coding: utf-8 -*-
"""Apontar mais de 1 unidade pede confirmação, e o mesmo Enter/clique não a aceita (risco 1 do GESTÃO, 13/11/2026, antes de o
Fernando apontar no Posto).

Antes: a quantidade vinha cheia com o que falta, e um Enter na janela apontava tudo — no grupo de 331 suportes de terça,
os 331. Agora (controle.js, confirmarNoDialogo) mais de 1 unidade mostra o 2º passo, que diz a quantidade, a marca e os kg.
O "Sim, apontar" só arma depois de ARMAR_MS (700 ms): o Enter que abriu, a tecla segurada (repetição) e o 2º clique do
clique duplo (Windows: até 500 ms) não confirmam — o D09 do EDITOR 3D (1267a83) foi o clique duplo atravessando o diálogo.
1 unidade segue sem pergunta.

O teste roda a função de verdade do controle.js no Node, com um DOM mínimo; o caminho na tela de verdade (Chrome) está no
verif_controle_producao (passos 3, 4 e 7b)."""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "producao"))
JS = os.path.join(WEB, "controle.js")

ENSAIO = r"""
class E {
  constructor(tag) { this.tag = tag; this.nodeType = 1; this.children = []; this.ls = []; this.hidden = false; this.disabled = false; this.parent = null; this.textContent = ''; }
  setAttribute(k, v) { if (k === 'disabled') this.disabled = true; else if (k === 'id') this.id = v; else this[k] = v; }
  append(...cs) { for (const c of cs) if (c && c.nodeType === 1) { c.parent = this; this.children.push(c); } }
  addEventListener(t, f, cap) { this.ls.push([t, f, !!cap]); }
  removeEventListener(t, f, cap) { const i = this.ls.findIndex(o => o[0] === t && o[1] === f && o[2] === !!cap); if (i >= 0) this.ls.splice(i, 1); }
  dispatch(t, ev = {}) { ev.type = t; ev.parado = false; ev.preventDefault = () => { ev.parado = true; }; ev.stopPropagation = () => {};
    for (const [tt, f] of [...this.ls]) if (tt === t) f(ev); return ev; }
  click() { if (!this.disabled) this.dispatch('click'); }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  after(x) { this.parent.append(x); }
  focus() { globalThis.focado = this; }
  achar(id) { if (this.id === id) return this; for (const c of this.children) { const r = c.achar(id); if (r) return r; } return null; }
}
globalThis.document = { createElement: (t) => new E(t), createTextNode: (s) => ({ nodeType: 3, s }) };
%(el)s
%(confirmar)s
const espera = (ms) => new Promise(ok => setTimeout(ok, ms));
const r = {};
function abrir() {
  const dlg = new E('dialog'), form = new E('form');
  dlg.append(form);
  let valor = null;
  const p = confirmarNoDialogo(dlg, form, 'Apontar 331 × ST1 na produção — 412,3 kg?', 'x').then(v => { valor = v; });
  return { dlg, form, sim: () => dlg.achar('ctl-sim'), voltar: () => dlg.achar('ctl-voltar'), valor: () => valor, p };
}
// 1. o Enter que abriu e o 2º clique do clique duplo, logo em seguida, não confirmam
let a = abrir();
r.form_escondido = a.form.hidden;
r.painel = !!a.dlg.achar('ctl-confirma');
r.enter_logo = a.dlg.dispatch('keydown', { key: 'Enter', repeat: false }).parado;
a.sim().click();
await espera(300);
r.clique_300ms = a.valor();
r.sim_desarmado_300ms = a.sim().disabled;
// 2. armado: a tecla segurada (repetição) ainda não; tecla nova sim (o Enter no botão vira clique no navegador)
await espera(500);
r.sim_armado = !a.sim().disabled && globalThis.focado === a.sim();
r.repeticao = a.dlg.dispatch('keydown', { key: 'Enter', repeat: true }).parado;
r.tecla_nova = a.dlg.dispatch('keydown', { key: 'Enter', repeat: false }).parado;
a.sim().click();
await a.p;
r.confirmou = a.valor();
r.form_volta = !a.form.hidden && !a.dlg.achar('ctl-confirma');
r.ouvintes = a.dlg.ls.length;
// 3. Voltar e fechar a janela não gravam
a = abrir(); a.voltar().click(); await a.p; r.voltar = a.valor();
a = abrir(); a.dlg.dispatch('close'); await a.p; r.fechar = a.valor();
console.log(JSON.stringify(r));
"""


def _trecho(js, de, ate):
    i = js.index(de)
    return js[i:js.index(ate, i)]


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node no computador")
def test_o_mesmo_enter_e_o_clique_duplo_nao_confirmam():
    js = open(JS, encoding="utf-8").read()
    script = ENSAIO % {"el": _trecho(js, "function el(tag", "  const n = (x"),
                       "confirmar": _trecho(js, "const ARMAR_MS", "  function abrirDialogo(")}
    pasta = tempfile.mkdtemp(prefix="confirmar_")
    try:
        arq = os.path.join(pasta, "t.mjs")
        open(arq, "w", encoding="utf-8").write(script)
        r = subprocess.run(["node", arq], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    assert a["form_escondido"] and a["painel"], a                    # o 2º passo no lugar do formulário
    assert a["enter_logo"] is True, a                                 # o Enter logo depois não passa
    assert a["clique_300ms"] is None and a["sim_desarmado_300ms"], a  # o 2º clique do clique duplo não confirma
    assert a["sim_armado"], a                                         # depois de 700 ms arma, com o foco no Sim
    assert a["repeticao"] is True and a["tecla_nova"] is False, a     # tecla segurada não; tecla nova sim
    assert a["confirmou"] is True and a["form_volta"] and a["ouvintes"] == 0, a
    assert a["voltar"] is False and a["fechar"] is False, a


def test_mais_de_uma_unidade_passa_pela_confirmacao_nas_duas_janelas():
    """a janela de um item (quantidade > 1) e a de vários (mais de 1 peça/unidade no total); 1 unidade vai direto"""
    js = open(JS, encoding="utf-8").read()
    um = _trecho(js, "function abrirDialogo(", "async function estornar(")
    assert re.search(r"if \(q > 1 && !\(await confirmarNoDialogo\(dlg, form, `Apontar \$\{n\(q\)\} × \$\{item\.id\}.*kg\?`", um), um
    varios = _trecho(js, "function dialogoDeVarios(", "function marcarLinhas(")
    assert "if (qtd > 1 && !(await confirmarNoDialogo(dlg, form," in varios
    assert "ARMAR_MS = 700" in js
