# -*- coding: utf-8 -*-
"""O clique duplo não atravessa o diálogo (D09 do usuario-desastrado, 13/11: clique duplo no "Cancelar a tarefa" da lista
abriu o projeto do cartão de baixo; no 3D, o clique duplo no "Detalhar e abrir" começou uma seleção por janela).

progresso.segurarCliqueAtras(ret, ms): por `ms` depois de o diálogo fechar, o clique que cai ONDE ELE ESTAVA não chega ao
que está atrás; o clique noutro ponto da tela, o de dentro de outro diálogo aberto e o que vem depois do tempo passam.
Usada pelo _confirmar do progresso.js (o Cancelar da tarefa, em toda tela) e pelo dialogo() do editor 3D."""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))

SCRIPT = r"""
const ouvintes = [];
globalThis.window = {
  addEventListener(t, f, cap) { ouvintes.push([t, f, cap]); },
  removeEventListener(t, f, cap) { const i = ouvintes.findIndex(o => o[0] === t && o[1] === f && o[2] === cap); if (i >= 0) ouvintes.splice(i, 1); },
};
const { segurarCliqueAtras } = await import(%s);
function disparar(tipo, x, y, dentroDeDialogo = false) {
  const ev = { type: tipo, clientX: x, clientY: y, parado: false,
               target: { closest: (s) => (dentroDeDialogo && s === 'dialog[open]' ? {} : null) },
               preventDefault() { this.parado = true; }, stopImmediatePropagation() { this.parado = true; } };
  for (const [t, f, cap] of [...ouvintes]) if (t === tipo && cap) f(ev);
  return ev.parado;
}
const ret = { left: 500, top: 300, right: 800, bottom: 450, width: 300, height: 150 };
segurarCliqueAtras(ret, 400);
const r = {};
r.mesmo_lugar = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'dblclick'].map(t => disparar(t, 700, 430));
r.na_borda = disparar('pointerdown', 803, 452);
r.noutro_ponto = disparar('pointerdown', 100, 100);
r.noutro_dialogo = disparar('pointerdown', 700, 430, true);
r.ouvintes_durante = ouvintes.length;
await new Promise(ok => setTimeout(ok, 480));
r.depois = disparar('pointerdown', 700, 430);
r.ouvintes_depois = ouvintes.length;
segurarCliqueAtras({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 });
r.sem_retangulo = ouvintes.length;
console.log(JSON.stringify(r));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node no computador")
def test_o_segundo_clique_no_lugar_do_dialogo_nao_chega_atras():
    pasta = tempfile.mkdtemp(prefix="clique_atras_")
    try:
        script = os.path.join(pasta, "t.mjs")
        url = "file:///" + os.path.join(WEB, "progresso.js").replace("\\", "/")
        open(script, "w", encoding="utf-8").write(SCRIPT % json.dumps(url))
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        a = json.loads(r.stdout)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    assert a["mesmo_lugar"] == [True] * 6, a            # o 2º clique do clique duplo, onde estava o botão
    assert a["na_borda"] is True, a                     # 4 px de folga
    assert a["noutro_ponto"] is False, a                # o clique legítimo noutro ponto passa
    assert a["noutro_dialogo"] is False, a              # dentro de outro diálogo aberto passa
    assert a["ouvintes_durante"] > 0 and a["depois"] is False and a["ouvintes_depois"] == 0, a
    assert a["sem_retangulo"] == 0, a


def test_os_dois_dialogos_usam_a_trava():
    """O "Cancelar a tarefa" (progresso.js, toda tela) e o diálogo do editor 3D ("Detalhar e abrir") seguram o clique."""
    prog = open(os.path.join(WEB, "progresso.js"), encoding="utf-8").read()
    corpo = prog[prog.index("function _confirmar("):]
    corpo = corpo[:corpo.index("\n}\n") if "\n}\n" in corpo else len(corpo)]
    assert "segurarCliqueAtras(dlg.getBoundingClientRect())" in corpo
    ed = open(os.path.join(WEB, "editor3d", "editor.js"), encoding="utf-8").read()
    m = re.search(r"\n  dialogo\(\{ titulo, corpo.*?\n  \}\n", ed, re.S)
    assert m and "segurarCliqueAtras(ret)" in m.group(0)
