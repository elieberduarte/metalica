# -*- coding: utf-8 -*-
"""Explodir e juntar do editor 3D (web/editor3d/nucleo/explodir.js), rodado no node: a peça varrida vira
uma peça por trecho reto, a curva facetada fica inteira, e juntar os trechos devolve a malha de antes."""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(os.path.dirname(AQUI), "web", "editor3d", "nucleo", "explodir.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")


def _rodar(corpo: str) -> dict:
    url = "file:///" + MODULO.replace("\\", "/")
    js = textwrap.dedent("""
        const M = await import(%s);
        // a varredura de um U 100x50 (8 pontos na seção) pelos pontos do caminho, no plano XZ
        function varrer(caminho) {
          const secao = [[-50,0],[50,0],[50,100],[46,100],[46,4],[-46,4],[-46,100],[-50,100]];
          const vertices = [], faces = [];
          for (const [x, z] of caminho) for (const [a, b] of secao) vertices.push([x + b * 0, a, z + b]);
          const k = secao.length, m = caminho.length;
          faces.push([...Array(k).keys()]);
          faces.push([...Array(k).keys()].map(j => (m - 1) * k + j).reverse());
          for (let r = 0; r < m - 1; r++) for (let j = 0; j < k; j++)
            faces.push([r*k + j, r*k + (j+1) %% k, (r+1)*k + (j+1) %% k, (r+1)*k + j]);
          return { vertices, faces };
        }
        const saida = {};
        %s
        console.log(JSON.stringify(saida));
    """) % (json.dumps(url), corpo)
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_peca_dobrada_explode_nos_trechos_e_junta_de_volta():
    s = _rodar("""
        const L = varrer([[0, 0], [1000, 0], [1000, 700]]);          // a peça dobrada do joelho: 2 retas
        const t = M.trechosDoSolido(L);
        saida.n = t.length;
        saida.pontas = t.map(x => x.vertices.length);
        const j = M.juntarMalhas(t);
        saida.junta = [j.vertices.length, j.faces.length, L.vertices.length, L.faces.length, j.emendas];
        saida.reta = M.trechosDoSolido(varrer([[0, 0], [500, 0], [1500, 0]])).length;   // anel no meio da reta
    """)
    assert s["n"] == 2 and s["pontas"] == [16, 16]
    v, f, v0, f0, emendas = s["junta"]
    assert (v, f) == (v0, f0) and emendas == 1
    assert s["reta"] == 1


def test_prisma_em_u_nao_explode_pela_face_do_lado():
    """no prisma todos os vértices têm grau 3 — a tampa é a maior face (a seção), não o lado"""
    s = _rodar("""
        saida.n = M.trechosDoSolido(varrer([[0, 0], [3000, 0]])).length;
    """)
    assert s["n"] == 1


def test_curva_facetada_fica_num_trecho_so():
    """o gancho do tirante (facetas de poucos mm) não vira dezenas de pedaços"""
    s = _rodar("""
        const cam = [[0, 0], [1500, 0]];
        for (let a = 10; a <= 90; a += 10) cam.push([1500 + 40 * Math.sin(a * Math.PI / 180), 40 - 40 * Math.cos(a * Math.PI / 180)]);
        cam.push([1540, 600]);
        saida.n = M.trechosDoSolido(varrer(cam)).length;
    """)
    assert s["n"] == 3                                  # reta, curva, reta


def test_juntar_barras_na_mesma_reta():
    s = _rodar("""
        const b = (i, f) => ({ tipo: 'barra', inicio: i, fim: f, perfil: 'U 100x50', rotacao: 0 });
        const j = M.juntarBarras([b([0,0,0],[1000,0,0]), b([1000,0,0],[2500,0,0])]);
        saida.j = [j.inicio, j.fim];
        saida.torta = M.juntarBarras([b([0,0,0],[1000,0,0]), b([1000,0,0],[2000,300,0])]);
    """)
    assert s["j"] == [[0, 0, 0], [2500, 0, 0]]
    assert s["torta"] is None
