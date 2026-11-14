# -*- coding: utf-8 -*-
"""A resposta atrasada da gravação do terreno não apaga o que a tela mudou com o pedido no ar (14/11, conferência da
0.9.4: o verif_ver3d_chao_sem_imagem caía com a máquina carregada — dois cliques no +5 cm davam 5 cm). Regra: a volta do
servidor não desfaz a mudança feita na tela enquanto o pedido estava no ar; a tela vale e o que mudou é gravado em seguida.

Sem navegador: a classe Terreno de web/visor3d/terreno.js rodada no Node, com um fetch falso que guarda o que chega e
responde 0,4 s depois. O clique no +5 cm é o do painel (`ajustar(aj0() + 50)`: soma em cima de `altura.ajuste`). A tela de
verdade (cliques do mouse, o F5, o fechar da página) é o verif_terreno_resposta_atrasada.py."""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

WEB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))

NODE = r"""
import { Terreno } from %(terreno)s;
const API = '/api/projetos/obra/terreno';
const espera = ms => new Promise(ok => setTimeout(ok, ms));
const servidor = { terreno: %(local)s, chao: null, fontes: [] };
const chegou = [];
globalThis.fetch = async (url, op) => {
  const corpo = JSON.parse(op.body), rota = String(url).replace(API, '');
  chegou.push([rota, corpo]);
  if (rota === '/chao') servidor.chao = Object.keys(corpo).length ? corpo : null;
  else servidor.terreno = corpo;
  const resp = JSON.parse(JSON.stringify(servidor));
  await espera(400);                                   // a resposta atrasada (o pedido já chegou)
  return { ok: true, status: 200, json: async () => resp };
};
const avisos = [];
const t = new Terreno({}, 'obra', { chaveLigado: null, situacao: m => avisos.push(m) });
t.estado = JSON.parse(JSON.stringify(servidor));
const clique = mm => { const a = t._alvoAltura(); a.ajuste = (t.altura.ajuste || 0) + mm; t._gravarAltura(); };
t._alvoAltura().cota = -500; t._gravarAltura();       // Outra cota −0,50
await espera(600);                                     // o pedido saiu aos 0,5 s e responde aos 0,9 s
clique(50);                                            // o 1º clique, com ele no ar
await espera(450);                                     // a resposta do 1º pedido voltou
clique(50);                                            // o 2º clique
const logo = t.altura.ajuste;
await espera(2500);                                    // todas as respostas de volta
const guardado = t.t ? servidor.terreno : servidor.chao;
console.log(JSON.stringify({ logo, tela: t.altura, guardado, chegou: chegou.length, avisos }));
"""


def _rodar(local):
    pasta = tempfile.mkdtemp(prefix="terreno_atrasado_")
    try:
        three = os.path.join(WEB, "lib", "three.module.js")
        js = open(os.path.join(WEB, "visor3d", "terreno.js"), encoding="utf-8").read()
        js = js.replace("from 'three'", "from " + json.dumps("file:///" + three.replace("\\", "/")))
        open(os.path.join(pasta, "terreno.mjs"), "w", encoding="utf-8", newline="").write(js)
        shutil.copy(os.path.join(WEB, "visor3d", "chao.js"), os.path.join(pasta, "chao.js"))
        script = os.path.join(pasta, "t.mjs")
        open(script, "w", encoding="utf-8", newline="").write(NODE % {"terreno": json.dumps("./terreno.mjs"), "local": json.dumps(local)})
        r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=pasta)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node no computador")
@pytest.mark.parametrize("local", [None, {"lat": -24.956, "lon": -53.456, "ponto": [0, 0], "norte": 0, "fonte": "teste"}],
                         ids=["sem-local (o chao)", "com-local (o terreno)"])
def test_dois_cliques_com_a_gravacao_no_ar_dao_10_cm(local):
    a = _rodar(local)
    assert a["logo"] == 100, a                           # a frase e o chão logo depois do 2º clique
    assert a["tela"].get("cota") == -500 and a["tela"].get("ajuste") == 100, a
    assert a["guardado"].get("cota") == -500 and a["guardado"].get("ajuste") == 100, a
    assert not a["avisos"], a
