# -*- coding: utf-8 -*-
"""GER-04 — o 3D modelado a partir de DXF fica vinculado ao 2D (sistema/testes/REGRAS.md).

Usuário, 26/10/2026: "todas as vezes que montarmos um projeto modelando ele em 3D a partir de projetos dxf, os projetos
dxf utilizados devem ser importados para 2D e o modelo em 3D deve ser vinculado ao 2D para facilitar a verificação do 2D
com 3D". O vínculo é o `planta_modelo` do projeto, que a tela dividida (web/dividida.js) lê:
  {desenho: o desenho 2D com o DXF, deslocamento: [dx, dy] (modelo = desenho + deslocamento),
   fontes: {planta: [dx, dy]} (o deslocamento de cada planta lida, além do geral), camadas: {camada do 3D: planta}}.
  A planta girada no desenho (26/10, Galpão Novo da Hora Certa: as coberturas G1–G4 desenham os eixos A–Q no sentido de x)
  tem fontes[planta] = {deslocamento: [dx, dy], giro: graus}: modelo = gira(desenho, giro) + deslocamento geral + o dela.
A montagem pela planta (app.py, de_planta) e por quadros (de_quadros) já o gravam; o script de obra grava por `gravar`.
O outro jeito de ligar (sem planta_modelo): cada peça com a chave do traço do desenho (atributos.origem_2d), como a
Montagem e a planta de lançamento fazem — vale com MIN_CHAVE das barras ligadas (`_pela_chave`).

`conferir` olha o projeto inteiro:
  - o DXF está no 2D: o desenho do `planta_modelo` existe e tem entidades vindas do DXF;
  - o 3D está ligado: há o deslocamento, e a planta de cada peça (origem.fonte_2d) está nas fontes;
  - o 3D cai em cima do desenho: cada barra, levada ao 2D, tem traço do desenho junto do meio e das duas pontas (grade de
    CEL mm, uma célula em volta). Com o vínculo certo ficam até ~8 % fora (o Posto V2 2,7 %, a Portaria 1,4 %); com o 3D
    1 m fora do lugar, 16–28 %; 5 m, mais de 50 % — o limite é LIMITE_FORA.
Só se aplica ao projeto que veio de DXF (o DXF recebido, o arquitetônico em DXF ou a peça montada pela planta)."""
import json
import math
import os
from typing import Dict, Iterable, List, Optional, Tuple

CEL = 250.0            # mm: a grade dos traços do desenho
LIMITE_FORA = 0.12
#: o traço que veio do projeto recebido: o DXF (espaço do modelo), as folhas do papel do DXF (folhas_papel) e as folhas
#: impressas em PDF (27/10, Hora Certa: o Original passou a ser as pranchas como foram emitidas, regra do usuário)
ORIGEM_RECEBIDA = ("dxf", "dxf-papel", "pdf")     # fração das barras longe de qualquer traço do desenho a partir da qual o vínculo está errado
MIN_CHAVE = 0.80       # sem planta_modelo: a fração das barras com a chave de um traço do desenho (o Hangar 93 %, as Docas 92 %)


def _ler(caminho: str) -> Optional[dict]:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _entidades(modelo: dict) -> list:
    ents = (modelo or {}).get("entidades") or []
    return list(ents.values()) if isinstance(ents, dict) else list(ents)


def veio_de_dxf(projeto: dict, entidades: Iterable[dict] = ()) -> bool:
    """o projeto foi modelado a partir de DXF: o DXF recebido, o arquitetônico em DXF ou peça montada pela planta"""
    arq = projeto.get("arquitetonico") or {}
    if projeto.get("dxf_recebido") or str(arq.get("tipo") or "").lower() == "dxf" or projeto.get("planta_modelo"):
        return True
    for e in entidades:
        o = (e.get("atributos") or {}).get("origem")
        if isinstance(o, dict) and (o.get("fonte_2d") or o.get("planta")):
            return True
    return False


def _pontos(des: dict):
    """os pontos dos traços do desenho, de CEL em CEL mm"""
    def trecho(a, b):
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // CEL))
        for k in range(n + 1):
            yield a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
    for e in des.get("entidades") or []:
        t = e.get("tipo")
        try:
            if t == "linha":
                yield from trecho(e["a"], e["b"])
            elif t == "polilinha":
                vs = e.get("vertices") or []
                for a, b in zip(vs, vs[1:] + (vs[:1] if e.get("fechada") else [])):
                    yield from trecho(a, b)
            elif t in ("circulo", "arco") and e.get("centro"):
                yield e["centro"][0], e["centro"][1]
        except (KeyError, TypeError, IndexError):
            continue


def _transf(v) -> Tuple[float, float, float]:
    """(dx, dy, giro em radianos) de uma planta das fontes: [dx, dy] ou {deslocamento: [dx, dy], giro: graus}"""
    if isinstance(v, dict):
        d = v.get("deslocamento") or (0.0, 0.0)
        return float(d[0]), float(d[1]), math.radians(float(v.get("giro") or 0.0))
    return float(v[0]), float(v[1]), 0.0


def ao_desenho(x: float, y: float, desl, fonte=None) -> Tuple[float, float]:
    """o ponto do modelo levado ao desenho: o inverso de modelo = gira(desenho, giro) + desl + deslocamento da planta"""
    fx, fy, g = _transf(fonte) if fonte is not None else (0.0, 0.0, 0.0)
    u, v = x - desl[0] - fx, y - desl[1] - fy
    c, s = math.cos(g), math.sin(g)
    return u * c + v * s, -u * s + v * c


def conferir(pasta_projeto: str) -> dict:
    """{aplica, barras, fora, apontamentos: [{regra, nivel, texto}]}"""
    projeto = _ler(os.path.join(pasta_projeto, "projeto.json")) or {}
    ents = _entidades(_ler(os.path.join(pasta_projeto, "modelo.json")) or {})
    out = {"aplica": veio_de_dxf(projeto, ents), "barras": 0, "fora": 0, "apontamentos": []}
    if not out["aplica"]:
        return out

    def apontar(texto, nivel="erro"):
        out["apontamentos"].append({"regra": "GER-04", "nivel": nivel, "texto": texto})
    pm = projeto.get("planta_modelo") or {}
    nome = pm.get("desenho")
    des = _ler(os.path.join(pasta_projeto, "desenhos-2d", "%s.desenho.json" % nome)) if nome else None
    if not nome or des is None:
        return _pela_chave(pasta_projeto, ents, out, apontar)
    if not any((e.get("atributos") or {}).get("origem") in ORIGEM_RECEBIDA for e in des.get("entidades") or []):
        apontar('o desenho 2D "%s" do vínculo não tem nada vindo do projeto recebido (DXF ou PDF)' % nome)
    desl = pm.get("deslocamento")
    if not (isinstance(desl, (list, tuple)) and len(desl) == 2):
        apontar('o 3D não está ligado ao desenho "%s": falta o deslocamento' % nome)
        return out
    fontes, camadas = pm.get("fontes") or {}, pm.get("camadas") or {}
    sem_fonte: Dict[str, int] = {}
    grade = {(int(x // CEL), int(y // CEL)) for x, y in _pontos(des)}

    def perto(x, y):
        gx, gy = int(x // CEL), int(y // CEL)
        return any((gx + i, gy + j) in grade for i in (-1, 0, 1) for j in (-1, 0, 1))
    fora_por_camada: Dict[str, int] = {}
    for e in ents:
        if e.get("tipo") != "barra" or not e.get("inicio") or not e.get("fim"):
            continue
        o = (e.get("atributos") or {}).get("origem") or {}
        f = o.get("fonte_2d") if isinstance(o, dict) else None
        if f and f not in fontes and f != "planta":
            sem_fonte[f] = sem_fonte.get(f, 0) + 1
        f = f if f in fontes else camadas.get(e.get("camada") or "")
        fonte = fontes.get(f) if f else None
        a, b = e["inicio"], e["fim"]
        pts = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), (a[0], a[1]), (b[0], b[1])
        out["barras"] += 1
        if not all(perto(*ao_desenho(x, y, desl, fonte)) for x, y in pts):
            out["fora"] += 1
            c = e.get("camada") or "?"
            fora_por_camada[c] = fora_por_camada.get(c, 0) + 1
    for f, n in sorted(sem_fonte.items(), key=lambda kv: -kv[1]):
        apontar('%d peças vêm da planta "%s", que o vínculo não conhece (planta_modelo.fontes)' % (n, f))
    if out["barras"] and out["fora"] > LIMITE_FORA * out["barras"]:
        pior = ", ".join("%s (%d)" % kv for kv in sorted(fora_por_camada.items(), key=lambda kv: -kv[1])[:4])
        apontar('o 3D não cai em cima do desenho "%s": %d de %d barras (%.0f %%) longe de qualquer traço — o deslocamento '
                "do vínculo está errado ou a planta da peça não é a dela. Mais fora: %s"
                % (nome, out["fora"], out["barras"], 100.0 * out["fora"] / out["barras"], pior))
    return out


def _pela_chave(pasta_projeto: str, ents: list, out: dict, apontar) -> dict:
    """o outro jeito de ligar, sem planta_modelo: a peça leva a chave do traço do desenho (atributos.origem_2d = o id do
    traço, ou a mesma origem_2d nele) — a Montagem e a planta de lançamento (o Hangar, o Ortobio, o CD Bom Dia, as Docas;
    o cad.js e o ver3d.js fazem a ida e volta por ela). Vale com MIN_CHAVE das barras ligadas a um desenho com o DXF."""
    chaves, com_dxf = set(), []
    pasta = os.path.join(pasta_projeto, "desenhos-2d")
    for arq in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        if not arq.endswith(".desenho.json"):
            continue
        des = _ler(os.path.join(pasta, arq)) or {}
        n = 0
        for e in des.get("entidades") or []:
            a = e.get("atributos") or {}
            if e.get("id"):
                chaves.add(e["id"])
            if a.get("origem_2d"):
                chaves.add(a["origem_2d"])
            if a.get("origem") in ORIGEM_RECEBIDA:
                n += 1
        if n:
            com_dxf.append(arq[:-len(".desenho.json")])
    barras = [e for e in ents if e.get("tipo") == "barra"]
    ligadas = sum(1 for e in barras if (e.get("atributos") or {}).get("origem_2d") in chaves)
    out.update(barras=len(barras), fora=len(barras) - ligadas, por_chave=ligadas)
    if not com_dxf:
        apontar("o DXF não está no 2D: nenhum desenho do projeto tem traço vindo do DXF — importar o DXF no 2D (o Original)")
    if not barras or ligadas >= MIN_CHAVE * len(barras):
        return out
    if not ligadas:
        apontar("o 3D não está ligado ao 2D: nenhuma barra tem a chave de um traço do desenho e o projeto não tem o "
                "planta_modelo — gravar o vínculo (vinculo_2d.gravar) ou a chave origem_2d em cada peça")
    else:
        apontar("só %d de %d barras (%.0f %%) estão ligadas ao 2D pela chave do desenho (origem_2d)"
                % (ligadas, len(barras), 100.0 * ligadas / len(barras)))
    return out


def gravar(pasta_projeto: str, desenho: str, deslocamento: Tuple[float, float], fontes: Optional[dict] = None,
           camadas: Optional[dict] = None) -> dict:
    """grava o vínculo no projeto (para o script de obra, como a montagem pela planta faz): o 3D = o desenho + deslocamento"""
    caminho = os.path.join(pasta_projeto, "projeto.json")
    projeto = _ler(caminho)
    if projeto is None:
        raise FileNotFoundError(caminho)
    if not os.path.isfile(os.path.join(pasta_projeto, "desenhos-2d", "%s.desenho.json" % desenho)):
        raise FileNotFoundError('o desenho 2D "%s" não existe no projeto (importar o DXF no 2D antes)' % desenho)
    pm = {"desenho": desenho, "deslocamento": [float(deslocamento[0]), float(deslocamento[1])]}
    if fontes:
        pm["fontes"] = {k: ({"deslocamento": [float(v["deslocamento"][0]), float(v["deslocamento"][1])], "giro": float(v.get("giro") or 0.0)}
                            if isinstance(v, dict) else [float(v[0]), float(v[1])]) for k, v in fontes.items()}
    if camadas:
        pm["camadas"] = dict(camadas)
    projeto["planta_modelo"] = pm
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(projeto, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)
    return pm


def conferir_obras(raiz: str) -> List[dict]:
    """todas as obras de uma pasta de dados: [{obra, aplica, barras, fora, apontamentos}]"""
    res = []
    for obra in sorted(os.listdir(raiz)):
        if os.path.isfile(os.path.join(raiz, obra, "projeto.json")):
            res.append({"obra": obra, **conferir(os.path.join(raiz, obra))})
    return res
