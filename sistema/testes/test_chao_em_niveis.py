# -*- coding: utf-8 -*-
"""O chão em mais de um nível (03/11, o usuário pelo SESI Chapecó N.10: "uma limitação legal da nossa representação do
terreno, quando temos níveis diferentes"; escolhida a malha pelos pontos de nível — amostras aprovadas em
Projeto/ESTUDOS/Terreno-niveis, caso (b)): os pontos gravados no projeto (saida/local_obra.niveis_do_chao) e as contas do
chão (web/visor3d/chao.js, rodado no node).

Os casos: o SESI (frente sul no térreo −0,50, pátio norte do subsolo −3,98/−4,16, a rua norte em rampa −0,15 → −2,86; os
eixos de 0 a 84,1 m × 0 a 49,46 m) e a obra plana (sem pontos: nada muda — o plano de sempre)."""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from saida import local_obra as L  # noqa: E402

MODULO = os.path.join(os.path.dirname(AQUI), "web", "visor3d", "chao.js")

# as cotas da implantação do SESI (1000/1002) fora do prédio, como o script da obra as grava (mm do projeto)
SESI = [
    (22067, -12624, -500), (22799, -11684, -500), (-1840, 1713, -560), (-1457, 1070, -560), (-1476, -860, -560),
    (35691, -4484, -150), (76783, -6985, 0), (55939, -11113, 10), (33032, -504, -10), (44039, 20203, 0),
    (1292, 56949, -150), (-366, 57841, -150), (-1732, 50361, -150), (-1434, 56739, -3310), (-1334, 53106, -4140),
    (2192, 54656, -4140), (12811, 53344, -4160), (7950, 58921, -700), (15622, 58464, -1240), (7469, 56511, -2080),
    (23396, 57847, -1780), (31008, 57337, -2320), (38776, 55773, -2860), (30714, 55958, -3410), (29671, 51433, -3950),
    (85080, 53156, -3980), (79457, 51574, -3980), (79273, 50671, -3980), (88533, 40715, -3700),
]
EIXOS_SESI = ([{"a": [x, -1500], "b": [x, 50955]} for x in (0, 10700, 24200, 55250, 84100)]
              + [{"a": [-1500, y], "b": [85600, y]} for y in (0, 21645, 39595, 49455)])

node = pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")


def _rodar(corpo: str, **dados) -> dict:
    url = "file:///" + MODULO.replace("\\", "/")
    js = "const C = await import(%s);\n" % json.dumps(url)
    js += "".join("const %s = %s;\n" % (k, json.dumps(v)) for k, v in dados.items())
    js += textwrap.dedent(corpo)
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _sup_sesi():
    return dict(pontos=[{"x": x, "y": y, "z": z} for x, y, z in SESI], eixos=EIXOS_SESI)


# ------------------------------------------------------------------ o projeto guarda os pontos

def test_os_pontos_de_nivel_gravados_no_projeto():
    base = {"lat": -27.09, "lon": -52.63, "ponto": [42000, 24700]}
    assert "niveis" not in L.validar(base) and "niveis" not in L.validar(dict(base, niveis=[]))      # obra plana: nada
    t = L.validar(dict(base, niveis=[{"x": 22067.4, "y": -12624.6, "z": -500.4, "nome": "1000"},
                                     {"x": 1, "y": 2, "z": "x"},                       # sem número: sai
                                     {"x": 5, "y": 5, "z": float("nan")},
                                     {"x": 79457, "y": 51574, "z": -3990},
                                     {"x": 79457, "y": 51574, "z": -3980}]))            # o mesmo lugar: o último vale
    assert t["niveis"] == [{"x": 22067, "y": -12625, "z": -500, "nome": "1000"}, {"x": 79457, "y": 51574, "z": -3980}]
    with pytest.raises(L.ErroTerreno, match="lista"):
        L.validar(dict(base, niveis="-0,50"))
    with pytest.raises(L.ErroTerreno, match="até"):
        L.validar(dict(base, niveis=[{"x": i, "y": 0, "z": 0} for i in range(L.NIVEIS_MAX + 1)]))


def test_os_pontos_vao_e_voltam_pelo_servidor(tmp_path):
    """POST /terreno (o painel e o script da obra) → GET: os pontos ficam no projeto; a busca de outro lugar não os apaga."""
    class G:
        def __init__(self): self.p = {}
        def ler(self, s): return self.p
        def tocar(self, s, **k): self.p.update(k)
        def pasta(self, s): return str(tmp_path)
    g = G()
    niv = [{"x": x, "y": y, "z": z} for x, y, z in SESI[:5]]
    e = L.gravar(g, "sesi", {"lat": -27.09, "lon": -52.63, "ponto": [42000, 24700], "cota": -30, "niveis": niv})
    assert e["terreno"]["niveis"] == niv and g.p["terreno"]["cota"] == -30


# ------------------------------------------------------------------ as contas do chão (chao.js)

@node
def test_triangulacao_de_delaunay():
    r = _rodar("""
        const quadrado = C.triangular([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]]);
        const repetido = C.triangular([[0, 0], [10, 0], [0, 10], [0, 0]]);
        console.log(JSON.stringify({ q: quadrado.length, r: repetido.length, pouco: C.triangular([[0, 0], [1, 1]]).length }));
    """)
    assert r == {"q": 4, "r": 1, "pouco": 0}


@node
def test_sesi_o_chao_passa_pelos_pontos_e_volta_ao_plano_longe():
    r = _rodar("""
        const cont = C.contornoDosEixos(eixos);
        const s = C.superficie(pontos, { base: -30, contorno: cont, centro: [42000, 24700] });
        const em = (x, y) => Math.round(s.cota(x, y));
        console.log(JSON.stringify({ cont, nos: pontos.map(p => em(p.x, p.y) - p.z),
          meio_rua: em(27000, 57600), longe: em(42000 + 450000, 24700) }));
    """, **_sup_sesi())
    assert r["cont"] == [[0, 0], [84100, 0], [84100, 49455], [0, 49455]]          # o contorno pelos cruzamentos dos eixos
    assert all(abs(d) <= 1 for d in r["nos"])                                    # a malha passa por cada ponto
    assert -2320 < r["meio_rua"] < -1780                                         # a rampa da rua norte entre as cotas
    assert abs(r["longe"] + 30) < 5                                              # longe da obra: o plano de antes


@node
def test_sesi_o_chao_encosta_no_predio_pelo_lado_de_fora():
    """A face norte (o pátio do subsolo) fica no nível do pátio, não na rampa que a triangulação faria por baixo do prédio
    até a frente sul; a face sul fica no térreo e a oeste segue a faixa oeste (não a cota do pátio depois da quina)."""
    r = _rodar("""
        const cont = C.contornoDosEixos(eixos);
        const com = C.superficie(pontos, { base: -30, contorno: cont, centro: [42000, 24700] });
        const sem = C.superficie(pontos, { base: -30, contorno: null, centro: [42000, 24700] });
        const em = (s, x, y) => Math.round(s.cota(x, y));
        console.log(JSON.stringify({ norte: [40000, 60000, 75000].map(x => em(com, x, 50500)),
          norte_sem: em(sem, 60000, 50500), sul: [20000, 50000].map(x => em(com, x, -1000)), oeste: em(com, -1200, 30000) }));
    """, **_sup_sesi())
    assert all(-4200 < z < -3500 for z in r["norte"]), r                         # o pátio, −3,98
    assert r["norte_sem"] > r["norte"][1] + 500, r                               # sem a face: a rampa por baixo do prédio
    assert all(-200 < z < 50 for z in r["sul"]), r                               # a frente no térreo
    assert -600 < r["oeste"] < -100, r                                           # a faixa oeste (−0,56 … −0,15)


@node
def test_a_malha_da_imagem_e_a_parede_do_degrau():
    """Os vértices da malha da imagem na cota do chão (a imagem girada como o norte do SESI, −53,1°) e o degrau quase em pé
    (um muro: 3,5 m em 1,5 m) marcado como parede; o chão de rampa suave não."""
    r = _rodar("""
        const pts = [{ x: 0, y: 0, z: 0 }, { x: 20000, y: 0, z: 0 }, { x: 0, y: 20000, z: 0 }, { x: 20000, y: 20000, z: 0 },
                     { x: 0, y: 21500, z: -3500 }, { x: 20000, y: 21500, z: -3500 }];
        const s = C.superficie(pts, { base: 0 });
        const g = { meio: [10000, 10000], largura: 80000, altura: 80000, giro: -53.1 * Math.PI / 180, n: 160 };
        const z = C.cotasDaMalha(s, g), par = C.paredesDaMalha(z, g.n, [500, 500]);
        // o vértice (coluna, linha) → ponto da obra, como o three põe o PlaneGeometry
        const c = Math.cos(g.giro), sn = Math.sin(g.giro), N = g.n + 1;
        let erro = 0, muro = 0, plano = 0;
        for (let l = 0; l < N; l++) for (let col = 0; col < N; col++) {
          const u = (col / g.n - 0.5) * g.largura, w = (0.5 - l / g.n) * g.altura;
          const x = g.meio[0] + c * u - sn * w, y = g.meio[1] + sn * u + c * w, v = l * N + col;
          erro = Math.max(erro, Math.abs(z[v] - s.cota(x, y)));
          if (x > 2000 && x < 18000 && y > 20500 && y < 21000) muro = Math.max(muro, par[v]);
          if (x > 2000 && x < 18000 && y > 5000 && y < 15000) plano = Math.max(plano, par[v]);
        }
        console.log(JSON.stringify({ erro, muro, plano }));
    """)
    assert r["erro"] < 1, r
    assert r["muro"] > 0.9 and r["plano"] == 0, r


@node
def test_obra_plana_um_ponto_so_e_o_plano():
    """Um ponto só (ou todos na mesma cota): o chão é o plano dele — nada de rampa inventada."""
    r = _rodar("""
        const s = C.superficie([{ x: 1000, y: 1000, z: -1200 }], { base: -1200 });
        console.log(JSON.stringify([s.cota(0, 0), s.cota(50000, -30000), s.cota(1000, 1000)].map(Math.round)));
    """)
    assert r == [-1200, -1200, -1200]
