# -*- coding: utf-8 -*-
"""Mapa de esforços do galpão, no formato que o editor 3D desenha.

O dimensionamento já resolve o pórtico pelo método da rigidez e guarda o modelo em
`projeto.esforcos["modelo"]`. Aqui esse resultado é traduzido para o mundo do editor:

* coordenadas em **milímetros**, Z para cima, X ao longo do galpão e Y no vão — as
  mesmas de `de_projeto.py`, e o pórtico descrito uma vez, no plano x = 0;
* diagramas de N, V e M amostrados em estações iguais, para o desenho não depender da
  amostragem adaptativa do solver, mais a envoltória estação por estação;
* a deformada de cada combinação, interpolada ao longo da barra (Hermite) a partir dos
  deslocamentos e das rotações dos nós, em milímetros reais — o exagero é do editor;
* as cargas de cada combinação, somadas por barra e direção, em kN/m;
* o aproveitamento de cada elemento dimensionado, que é o que pinta as peças.

Quem lê isto é `web/editor3d/nucleo/analise3d.js`, pela rota `/api/modelo/analise`.
Unidades do cálculo: o modelo de análise trabalha em kN e cm, com momento em kN·cm;
aqui tudo sai em kN, kN·m e milímetros, que é como o projetista lê.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from nucleo import analise
from nucleo.modelo_galpao import ProjetoGalpao
from saida import desenhos as dsn

#: Estações por barra nos diagramas e na deformada (21 = a cada 5 % do vão).
ESTACOES = 21

#: Chave da envoltória nos dicionários por combinação.
ENVOLTORIA = "envoltoria"

#: Grandezas que o editor sabe pintar, na ordem em que aparecem no seletor.
GRANDEZAS = [
    {"chave": "aproveitamento", "nome": "Aproveitamento", "unidade": "", "percentual": True},
    {"chave": "M", "nome": "Momento fletor", "unidade": "kN·m"},
    {"chave": "V", "nome": "Esforço cortante", "unidade": "kN"},
    {"chave": "N", "nome": "Força normal", "unidade": "kN"},
]

UNIDADES = {"M": "kN·m", "V": "kN", "N": "kN", "u": "cm", "q": "kN/m", "comprimento": "mm"}

#: Barras do pórtico que cada elemento ocupa — é o que o editor pinta e onde o
#: diagrama é desenhado. A mísula faz parte da viga.
BARRAS_DO_ELEMENTO = {
    "Pilar": ("pilar_esq", "pilar_dir"),
    "Viga": ("misula_esq", "viga_esq", "viga_dir", "misula_dir"),
}

#: Barras que contam para o esforço de projeto do elemento. A viga é dimensionada pelo
#: momento **fora** da mísula: no trecho de mísula a seção é maior, e aquele momento,
#: bem maior, é o que dimensiona a ligação de joelho, não a viga. Misturar os dois faria
#: o painel mostrar 273 kN·m onde o memorial mostra 179 kN·m.
BARRAS_PARA_VALOR = {
    "Pilar": ("pilar_esq", "pilar_dir"),
    "Viga": ("viga_esq", "viga_dir"),
}


def mapa_de_esforcos(projeto: ProjetoGalpao, estacoes: int = ESTACOES) -> dict:
    """Todo o material do mapa de esforços de um galpão já dimensionado."""
    esf = getattr(projeto, "esforcos", None) or {}
    modelo = esf.get("modelo")
    if modelo is None:
        return {"ok": False,
                "motivo": "este modelo não tem análise de pórtico; abra um galpão "
                          "dimensionado para ver o mapa de esforços."}

    combos: Dict[str, str] = dict(esf.get("combinacoes") or {})
    casos = [c for c in combos if c in getattr(modelo, "casos", {})]
    ultimas = [c for c in casos if c.startswith("C")]
    servico = [c for c in casos if c.startswith("S")]

    resultados = {}
    for caso in casos:
        try:
            resultados[caso] = analise.resolver(modelo, caso, estacoes)
        except Exception:
            continue          # um caso que não resolve não impede os outros
    if not resultados:
        return {"ok": False, "motivo": "nenhuma combinação pôde ser resolvida."}

    g = dsn._Geo(projeto)
    barras = _barras(modelo, resultados, ultimas, estacoes)
    do_elemento, para_valor = _mapa_de_barras(modelo)
    por_elemento = _valores_por_elemento(barras, resultados, ultimas, para_valor)

    return {
        "ok": True,
        "unidades": dict(UNIDADES),
        "grandezas": [dict(x) for x in GRANDEZAS],
        "combinacoes": _combinacoes(combos, ultimas, servico),
        "elementos": _elementos(projeto, por_elemento, list(resultados) + [ENVOLTORIA],
                                do_elemento),
        "portico": {
            "xs_mm": _posicoes_dos_porticos(g),
            "nos": [{"nome": n.nome or f"n{i}", "p": _ponto(n), "apoiado": bool(n.apoiado)}
                    for i, n in enumerate(modelo.nos)],
            "barras": barras,
        },
        "deformada": {caso: _deformada(modelo, r, estacoes, g)
                      for caso, r in resultados.items()},
        "cargas": {caso: _cargas(modelo, caso, _eixos_das_barras(modelo))
                   for caso in resultados},
        "servico": {"deslocamento": dict(esf.get("deslocamento") or {})},
    }


# =====================================================================================
# Combinações e geometria
# =====================================================================================

def _combinacoes(combos: Dict[str, str], ultimas: List[str],
                 servico: List[str]) -> List[dict]:
    """A envoltória primeiro; depois as combinações últimas e as de serviço."""
    saida = [{"chave": ENVOLTORIA, "nome": "Envoltória",
              "descricao": "pior caso de cada seção, entre as combinações últimas",
              "tipo": ENVOLTORIA}]
    for chave in ultimas + servico:
        saida.append({"chave": chave, "nome": chave, "descricao": combos.get(chave, ""),
                      "tipo": "ultima" if chave in ultimas else "servico"})
    return saida


def _posicoes_dos_porticos(g) -> List[float]:
    """Onde cada pórtico está ao longo do galpão (mm) — o mesmo de `de_projeto`."""
    xs = [k * g.esp_port for k in range(g.n_porticos)]
    if xs and abs(xs[-1] - g.comprimento) > 1.0:
        xs[-1] = g.comprimento
    return [round(x, 1) for x in xs]


def _ponto(no) -> List[float]:
    """Nó do pórtico (cm, plano xy) no espaço do editor (mm): x = 0, Y = vão, Z = altura."""
    return [0.0, round(no.x * 10.0, 1), round(no.y * 10.0, 1)]


# =====================================================================================
# Diagramas
# =====================================================================================

def _barras(modelo, resultados: dict, ultimas: List[str], estacoes: int) -> List[dict]:
    saida = []
    for k, b in enumerate(modelo.barras):
        ni, nf = modelo.nos[b.ni], modelo.nos[b.nf]
        ini, fim = _ponto(ni), _ponto(nf)
        dy, dz = fim[1] - ini[1], fim[2] - ini[2]
        L = math.hypot(dy, dz) or 1.0
        # Normal do diagrama: a direção para onde o momento positivo traciona — face
        # inferior da viga e face interna do pilar, como o modelo do pórtico define.
        normal = [0.0, round(dz / L, 6), round(-dy / L, 6)]

        diagramas = {}
        for caso, r in resultados.items():
            try:
                diagramas[caso] = _amostrar(r.barras[k], estacoes)
            except Exception:
                continue
        diagramas[ENVOLTORIA] = _envoltoria(diagramas, ultimas, estacoes)

        saida.append({
            "rotulo": b.rotulo or f"barra {k + 1}",
            "elemento": _elemento_da_barra(b.rotulo or ""),
            "ini": ini, "fim": fim, "normal": normal, "L_mm": round(L, 1),
            "diagramas": diagramas,
        })
    return saida


def _amostrar(rb, estacoes: int) -> dict:
    """N, V e M em estações iguais ao longo da barra, lidos da solução exata.

    O solver amostra onde precisa (cargas concentradas, ponto de cortante nulo); para
    desenhar e para tirar envoltória estação a estação convém a malha uniforme, e
    `ResultadoBarra.esforcos` dá o valor exato em qualquer seção.
    """
    passos = [i / (estacoes - 1) for i in range(estacoes)]
    N, V, M = [], [], []
    for t in passos:
        # na ponta final lê-se imediatamente à esquerda, para não cair depois de uma
        # carga concentrada que esteja exatamente no nó
        n, v, m = rb.esforcos(t * rb.L, lado=-1 if t >= 1.0 else 1)
        N.append(round(n, 2))
        V.append(round(v, 2))
        M.append(round(m / 100.0, 2))          # kN·cm -> kN·m
    return {"s": [round(t, 4) for t in passos], "N": N, "V": V, "M": M}


def _envoltoria(diagramas: Dict[str, dict], ultimas: List[str], estacoes: int) -> dict:
    """Máximo e mínimo de cada estação entre as combinações últimas."""
    casos = [c for c in ultimas if c in diagramas] or list(diagramas)
    if not casos:
        return {"s": [], "M_max": [], "M_min": [], "V_max": [], "V_min": [],
                "N_max": [], "N_min": []}
    saida = {"s": diagramas[casos[0]]["s"]}
    for g in ("M", "V", "N"):
        maximos, minimos = [], []
        for i in range(estacoes):
            valores = [diagramas[c][g][i] for c in casos if i < len(diagramas[c][g])]
            maximos.append(round(max(valores), 2) if valores else 0.0)
            minimos.append(round(min(valores), 2) if valores else 0.0)
        saida[g + "_max"] = maximos
        saida[g + "_min"] = minimos
    return saida


def _elemento_da_barra(rotulo: str) -> str:
    for elemento, rotulos in BARRAS_DO_ELEMENTO.items():
        if rotulo in rotulos:
            return elemento
    return ""


# =====================================================================================
# Deformada
# =====================================================================================

def _deformada(modelo, r, estacoes: int, g) -> dict:
    """Deslocamento ao longo de cada barra, em milímetros reais.

    Entre os nós a barra não anda em linha reta: a flecha vem das rotações das
    extremidades. Por isso o deslocamento transversal é interpolado pelas funções de
    forma de Hermite — as mesmas que o elemento de pórtico usa —, e o axial, linear.
    """
    barras = []
    maior = 0.0
    for b in modelo.barras:
        ni, nf = modelo.nos[b.ni], modelo.nos[b.nf]
        dx, dy = nf.x - ni.x, nf.y - ni.y
        L = math.hypot(dx, dy) or 1.0
        cx, cy = dx / L, dy / L
        try:
            uix, uiy, riz = r.deslocamento(b.ni)
            ufx, ufy, rfz = r.deslocamento(b.nf)
        except Exception:
            continue
        # deslocamentos das pontas em eixos locais (axial e transversal)
        u1, v1 = uix * cx + uiy * cy, -uix * cy + uiy * cx
        u2, v2 = ufx * cx + ufy * cy, -ufx * cy + ufy * cx

        passos, pontos = [], []
        for i in range(estacoes):
            t = i / (estacoes - 1)
            u = u1 + (u2 - u1) * t
            h1 = 1 - 3 * t * t + 2 * t ** 3
            h2 = L * (t - 2 * t * t + t ** 3)
            h3 = 3 * t * t - 2 * t ** 3
            h4 = L * (-t * t + t ** 3)
            v = h1 * v1 + h2 * riz + h3 * v2 + h4 * rfz
            gx = u * cx - v * cy                  # de volta aos eixos do pórtico
            gy = u * cy + v * cx
            maior = max(maior, math.hypot(gx, gy))
            passos.append(round(t, 4))
            pontos.append([0.0, round(gx * 10.0, 3), round(gy * 10.0, 3)])
        barras.append({"rotulo": b.rotulo or "", "s": passos, "d": pontos})

    # exagero que faz o maior deslocamento valer uns 3 % do vão: é o que se enxerga
    maior_mm = maior * 10.0
    escala = 40.0
    if maior_mm > 1e-6:
        escala = max(1.0, min(500.0, 0.03 * g.vao / maior_mm))
    return {"escala_sugerida": round(escala, 1),
            "maior_mm": round(maior_mm, 2), "barras": barras}


# =====================================================================================
# Cargas
# =====================================================================================

#: Como cada direção do modelo de análise é lida no editor.
DIRECOES = {
    "perpendicular": "perpendicular à barra",
    "axial": "ao longo da barra",
    "global_x": "horizontal",
    "global_y": "vertical",
    "projetada_x": "horizontal, por projeção",
    "projetada_y": "vertical, por projeção horizontal",
}


def _eixos_das_barras(modelo) -> Dict[str, Dict[str, List[float]]]:
    """Para cada barra, os eixos do modelo plano escritos no espaço do editor.

    O quadro do pórtico é plano: x é o vão e y é a altura. No editor, x do quadro é o
    **Y** do mundo e y do quadro é o **Z**. Sem essa tradução, "global_y" — que no
    quadro é a vertical — seria desenhado deitado, ao longo do vão.

    `axial` segue a barra; `perpendicular` é o eixo local y do solver, o mesmo que ele
    usa para a carga positiva: a direção da barra girada 90° no sentido anti-horário
    (é o oposto da normal dos diagramas, que aponta para a face tracionada).
    """
    saida: Dict[str, Dict[str, List[float]]] = {}
    for b in modelo.barras:
        ni, nf = modelo.nos[b.ni], modelo.nos[b.nf]
        dx, dy = nf.x - ni.x, nf.y - ni.y
        L = math.hypot(dx, dy) or 1.0
        c, s = dx / L, dy / L
        saida[b.rotulo or ""] = {
            "axial": [0.0, round(c, 6), round(s, 6)],
            "perpendicular": [0.0, round(-s, 6), round(c, 6)],
        }
    return saida


#: Direção de cada carga do modelo plano no espaço do editor (vetor do q positivo).
#: As de barra dependem da barra e saem de `_eixos_das_barras`.
EIXOS_GLOBAIS = {
    "global_x": [0.0, 1.0, 0.0],        # horizontal, ao longo do vão
    "global_y": [0.0, 0.0, 1.0],        # vertical
    "projetada_x": [0.0, 1.0, 0.0],
    "projetada_y": [0.0, 0.0, 1.0],
}


def _cargas(modelo, caso: str, eixos: Dict[str, Dict[str, List[float]]]) -> List[dict]:
    """Cargas da combinação, somadas por barra e direção, em kN/m.

    A combinação é montada copiando as cargas dos casos elementares com seus fatores,
    então a mesma barra aparece várias vezes (peso próprio, sobrecarga, vento). Somar
    por direção devolve a carga que o projetista espera ver desenhada.

    Cada carga leva `eixo`: o vetor unitário, já no espaço do editor, para onde aponta
    um `q` positivo. O desenho é `q · eixo`, sem precisar interpretar o nome da direção.
    """
    def eixo_de(rotulo: str, direcao: str) -> List[float]:
        if direcao in EIXOS_GLOBAIS:
            return list(EIXOS_GLOBAIS[direcao])
        return list((eixos.get(rotulo) or {}).get(direcao, [0.0, 0.0, 1.0]))

    soma: Dict[tuple, float] = {}
    pontuais: List[dict] = []
    for c in modelo.casos.get(caso, []):
        try:
            rotulo = modelo.barras[modelo.indice_barra(c.alvo)].rotulo
        except Exception:
            rotulo = str(c.alvo)
        if c.tipo == "distribuida":
            chave = (rotulo, c.direcao)
            soma[chave] = soma.get(chave, 0.0) + c.q * 100.0     # kN/cm -> kN/m
        elif c.tipo == "concentrada":
            pontuais.append({"barra": rotulo, "tipo": "concentrada", "P_kN": round(c.P, 2),
                             "a_mm": round(c.a * 10.0, 1), "direcao": c.direcao,
                             "eixo": eixo_de(rotulo, c.direcao),
                             "descricao": DIRECOES.get(c.direcao, c.direcao)})

    saida = [{"barra": rotulo, "tipo": "distribuida", "q_kN_m": round(q, 3),
              "direcao": direcao, "eixo": eixo_de(rotulo, direcao),
              "descricao": DIRECOES.get(direcao, direcao)}
             for (rotulo, direcao), q in sorted(soma.items()) if abs(q) > 1e-9]
    return saida + pontuais


# =====================================================================================
# Elementos dimensionados
# =====================================================================================

def _mapa_de_barras(modelo):
    """(barras de cada elemento, barras que contam para o valor), conforme o pórtico.

    No pórtico de alma cheia é a tabela fixa deste módulo. Na tesoura as famílias são
    outras — banzos, diagonais e montantes — e quem as publica é o próprio modelo, em
    `dados["barras_por_papel"]`: assim o painel do editor mostra a mesma peça que o
    memorial dimensionou, sem tabela paralela.
    """
    dd = getattr(modelo, "dados", None) or {}
    por_papel = dd.get("barras_por_papel")
    if not por_papel:
        return dict(BARRAS_DO_ELEMENTO), dict(BARRAS_PARA_VALOR)
    mapa = {"Pilar": tuple(dd.get("barras_pilar") or ())}
    for papel, rotulos in por_papel.items():
        mapa[str(papel).capitalize()] = tuple(rotulos)
    return mapa, dict(mapa)


def _valores_por_elemento(barras: List[dict], resultados: dict, ultimas: List[str],
                          para_valor=None) -> Dict[str, Dict[str, dict]]:
    """Maior N, V e M em módulo de cada elemento do pórtico, por combinação."""
    saida: Dict[str, Dict[str, dict]] = {}
    casos = list(resultados) + [ENVOLTORIA]
    for elemento, rotulos in (para_valor or BARRAS_PARA_VALOR).items():
        minhas = [b for b in barras if b["rotulo"] in rotulos]
        if not minhas:
            continue
        por_caso: Dict[str, dict] = {}
        for caso in casos:
            valores = {}
            for g in ("M", "V", "N"):
                pico = 0.0
                for b in minhas:
                    d = b["diagramas"].get(caso) or {}
                    serie = (d.get(g) if caso != ENVOLTORIA
                             else (d.get(g + "_max", []) + d.get(g + "_min", [])))
                    for v in serie or []:
                        pico = max(pico, abs(v))
                valores[g] = round(pico, 2)
            por_caso[caso] = valores
        saida[elemento] = por_caso
    return saida


def _elementos(projeto: ProjetoGalpao, por_elemento: Dict[str, Dict[str, dict]],
               casos: List[str], do_elemento=None) -> Dict[str, dict]:
    """Um verbete por elemento dimensionado, na chave que o modelo 3D usa.

    A chave é o nome do elemento — o mesmo que `de_projeto.py` grava em
    `atributos["elemento"]` de cada peça —, e é por ele que o editor casa peça e valor.
    """
    saida: Dict[str, dict] = {}
    do_elemento = do_elemento or BARRAS_DO_ELEMENTO
    for e in projeto.elementos:
        chave_portico = _chave_do_portico(e.nome, do_elemento)
        valores = dict(por_elemento.get(chave_portico, {})) if chave_portico else {}
        if not valores:
            # elemento fora do pórtico (terça, longarina, contraventamento): o cálculo
            # dá um único conjunto de esforços, o que governa; vale para toda combinação
            fixos = _esforcos_do_elemento(e)
            valores = {caso: dict(fixos) for caso in casos}

        resultado = e.resultado
        critica = resultado.critica if resultado else None
        saida[e.nome] = {
            "perfil": e.perfil,
            "material": e.material,
            "aproveitamento": round(e.razao, 3),
            "ok": bool(e.ok),
            "governa": critica.titulo if critica else "",
            "norma": getattr(critica, "norma", "") if critica else "",
            "Sd": round(critica.Sd, 2) if critica else 0.0,
            "Rd": round(critica.Rd, 2) if critica else 0.0,
            "unidade": getattr(critica, "unidade", "") if critica else "",
            "barras": list(do_elemento.get(chave_portico, ())),
            "no_portico": bool(chave_portico),
            "dimensionamento": _esforcos_do_elemento(e),
            # quem está no pórtico já tem o diagrama em `portico.barras`; as demais peças
            # levam aqui o seu próprio, para o editor desenhar sobre a peça típica
            "diagrama": None if chave_portico else _diagrama_de_viga(e, ESTACOES),
            "valores": valores,
        }
    return saida


def _diagrama_de_viga(e, estacoes: int) -> Optional[dict]:
    """Diagrama da peça verificada fora do pórtico: viga biapoiada com carga uniforme.

    Terça e longarina são verificadas assim — vão igual ao espaçamento dos pórticos,
    carga uniforme, apoios nas pontas —, então o diagrama é a parábola clássica e o pico
    fecha com o momento que dimensionou a peça (q·L²/8). Publicá-lo aqui evita que o
    editor refaça a conta e garante que a tela mostre o mesmo que o memorial.

    Devolve `None` para quem não tem esse modelo: os contraventamentos só trabalham à
    tração, e um diagrama de normal constante não diria nada.
    """
    geo = e.geometria if isinstance(e.geometria, dict) else {}
    esf = e.esforcos if isinstance(e.esforcos, dict) else {}
    L = float(geo.get("vao_m") or 0.0)
    if L <= 0:
        return None
    cargas = {"gravidade": esf.get("q_gravidade_kN_m"),
              "sucção": esf.get("q_succao_kN_m"),
              "pressão do vento": esf.get("q_pressao_kN_m")}
    cargas = {k: abs(float(v)) for k, v in cargas.items()
              if isinstance(v, (int, float)) and abs(v) > 1e-9}
    if not cargas:
        return None
    caso, q = max(cargas.items(), key=lambda kv: kv[1])
    passos = [i / (estacoes - 1) for i in range(estacoes)]
    return {
        "modelo": "viga biapoiada",
        "vao_m": round(L, 3),
        "caso": caso,
        "q_kN_m": round(q, 3),
        "s": [round(t, 4) for t in passos],
        "M": [round(q * L * L * t * (1.0 - t) / 2.0, 3) for t in passos],
        "V": [round(q * L * (0.5 - t), 3) for t in passos],
    }


def _chave_do_portico(nome: str, do_elemento=None) -> Optional[str]:
    for chave in (do_elemento or BARRAS_DO_ELEMENTO):
        if nome.lower().startswith(chave.lower()):
            return chave
    return None


def _esforcos_do_elemento(e) -> dict:
    """M (kN·m), V e N (kN) que dimensionaram o elemento.

    O cálculo publica os esforços de dois jeitos: terça e longarina guardam os momentos
    nos dados da verificação, em kN·cm, e só as cargas distribuídas em `esforcos`; os
    demais guardam N, V e M direto em `esforcos`. Aqui os dois viram a mesma tripla, na
    unidade que o projetista lê.
    """
    esf = dict(e.esforcos or {})
    dados = (dict(e.resultado.dados)
             if e.resultado and isinstance(getattr(e.resultado, "dados", None), dict)
             else {})

    def maior(fonte: dict, chaves, divisor: float = 1.0) -> float:
        valores = [abs(float(fonte[k])) for k in chaves
                   if isinstance(fonte.get(k), (int, float))]
        return round(max(valores) / divisor, 2) if valores else 0.0

    M = (maior(esf, ("M_kNm",))
         or maior(esf, ("M_kNcm",), 100.0)
         or maior(dados, ("M_Sd", "Mx_Sd", "Mx_gravidade_kNcm", "Mx_succao_kNcm"), 100.0))
    V = maior(esf, ("V_kN",)) or maior(dados, ("V_Sd", "V_Sd_kN"))
    N = maior(esf, ("N_kN",)) or maior(dados, ("N_Sd", "N_Sd_kN"))
    return {"M": M, "V": V, "N": N, "caso": str(esf.get("caso", ""))}
