# -*- coding: utf-8 -*-
"""Arestas dos sólidos no editor 3D (web/editor3d/nucleo/arestas.js), rodado no node: as do modelo grande
saem direto das faces, sem o THREE.EdgesGeometry, que levava 9 dos 40 s de abrir o Bella Casa (05/10).
O critério é o dele: borda de uma face só, ou dobra entre faces maior que 24°."""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(os.path.dirname(AQUI), "web", "editor3d", "nucleo", "arestas.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")


def _rodar(corpo: str) -> dict:
    url = "file:///" + MODULO.replace("\\", "/")
    js = textwrap.dedent("""
        const { arestasDoSolido } = await import(%s);
        const n = (vs, fs) => arestasDoSolido(vs, fs).length / 6;
        const caixa = () => ({
          vertices: [[0,0,0],[10,0,0],[10,10,0],[0,10,0],[0,0,10],[10,0,10],[10,10,10],[0,10,10]],
          faces: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],
        });
        // cilindro de k lados: as arestas ao longo dele dobram 360/k graus
        function cilindro(k) {
          const vertices = [], faces = [];
          for (let i = 0; i < k; i++) { const a = 2 * Math.PI * i / k; vertices.push([Math.cos(a), Math.sin(a), 0], [Math.cos(a), Math.sin(a), 5]); }
          for (let i = 0; i < k; i++) { const j = (i + 1) %% k; faces.push([2*i, 2*j, 2*j+1, 2*i+1]); }
          faces.push([...Array(k).keys()].map(i => 2 * i).reverse(), [...Array(k).keys()].map(i => 2 * i + 1));
          return { vertices, faces };
        }
        const saida = {};
        %s
        console.log(JSON.stringify(saida));
    """) % (json.dumps(url), corpo)
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_caixa_tem_as_12_arestas():
    s = _rodar("const c = caixa(); saida.n = n(c.vertices, c.faces);")
    assert s["n"] == 12


def test_face_dividida_no_mesmo_plano_nao_mostra_a_divisao():
    # a tampa de cima em dois triângulos: a diagonal fica escondida, como no EdgesGeometry
    s = _rodar("""
        const c = caixa(); c.faces[1] = [4,5,6]; c.faces.push([4,6,7]);
        saida.n = n(c.vertices, c.faces);
    """)
    assert s["n"] == 12


def test_vertice_repetido_conta_como_um_so():
    # a face de cima com vértices próprios (mesma posição, outros índices): as arestas dela
    # não viram borda solta dobrada
    s = _rodar("""
        const c = caixa(); const base = c.vertices.length;
        c.vertices.push(...[4,5,6,7].map(i => [...c.vertices[i]]));
        c.faces[1] = [base, base+1, base+2, base+3];
        saida.n = n(c.vertices, c.faces);
    """)
    assert s["n"] == 12


def test_cilindro_esconde_as_dobras_suaves():
    # 24 lados: dobra de 15°, menor que o limiar, as geratrizes somem e ficam os dois círculos;
    # 12 lados (vergalhão do Revit): dobra de 30°, as geratrizes aparecem
    s = _rodar("""
        const c24 = cilindro(24), c12 = cilindro(12);
        saida.n24 = n(c24.vertices, c24.faces); saida.n12 = n(c12.vertices, c12.faces);
    """)
    assert s["n24"] == 48
    assert s["n12"] == 36


def test_face_degenerada_e_indice_invalido_nao_quebram():
    s = _rodar("""
        const c = caixa(); c.faces.push([0, 0, 0], [0, 1, 99]);
        saida.n = n(c.vertices, c.faces);
        saida.vazio = n([], []);
    """)
    assert s["n"] == 12 and s["vazio"] == 0
