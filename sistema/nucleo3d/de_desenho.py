# -*- coding: utf-8 -*-
"""Caminho inverso: um desenho 2D vira modelo 3D com a informação de cada peça.

    from nucleo3d import de_desenho
    doc = de_desenho.modelo_do_desenho(desenho, plano="frente", repeticoes=5,
                                       espacamento=5000, conjunto="T1")

Quem desenha uma tesoura no CAD marca cada linha com a **peça do catálogo** que ela
representa (perfil, papel, aço). Este módulo lê essas marcas e monta o documento 3D:
cada linha vira uma `Barra` de verdade, com perfil, aço, papel e — o que importa para
tudo o que vem depois — as **marcas por peça** (`atributos["marcas"]`) no mesmo formato
que o importador de IFC produz: `posicao` (P1, P2…), `conjunto` (M1, M2…) e `perfil`.

É isso que faz o desenho render detalhamento, lista de materiais, cálculo e IFC sem
nenhum caminho paralelo: do ponto de vista do resto do sistema, um modelo desenhado aqui
é igual a um modelo importado de fábrica.

**Onde fica a informação da peça**

* na entidade 2D: `atributos["peca"] = {"perfil", "papel", "aco", "rotacao", "espessura"}`;
* por camada, valendo para tudo o que está nela: `desenho.metadados["pecas_por_camada"]`.

A da entidade vence a da camada. Linha sem peça nenhuma é anotação (cota, texto, eixo) e
fica de fora, contada no relatório.

**Onde o desenho entra no espaço** (`plano`)

* `"frente"` — o X do desenho vira X, o Y vira Z; a tesoura fica em pé, vista de frente;
* `"topo"` — X vira X e Y vira Y, deitado no plano horizontal (contraventamento, planta);
* `"lado"` — X vira Y e Y vira Z, em pé, vista de lado.

`repeticoes`/`espacamento` copiam o desenho ao longo da normal do plano — as oito tesouras
de um galpão saem de um desenho só, cada cópia um conjunto (M1, M2…).

Unidades: o desenho 2D está em milímetro, o modelo 3D também; nada é escalado.
"""
from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Desenho, Entidade2D, Linha, Polilinha
from nucleo3d.modelo import Barra, Camada, Chapa, Documento

__all__ = ["modelo_do_desenho", "conferir_desenho", "PLANOS", "PAPEIS", "peca_da_entidade"]

#: Como o plano do desenho é posto no espaço: (eixo do X do desenho, eixo do Y, normal).
PLANOS: Dict[str, dict] = {
    "frente": {"nome": "Frente (em pé, olhando o eixo Y)",
               "u": (1.0, 0.0, 0.0), "v": (0.0, 0.0, 1.0), "n": (0.0, 1.0, 0.0)},
    "lado":   {"nome": "Lado (em pé, olhando o eixo X)",
               "u": (0.0, 1.0, 0.0), "v": (0.0, 0.0, 1.0), "n": (1.0, 0.0, 0.0)},
    "topo":   {"nome": "Topo (deitado no plano horizontal)",
               "u": (1.0, 0.0, 0.0), "v": (0.0, 1.0, 0.0), "n": (0.0, 0.0, 1.0)},
}

#: Papel da peça → camada do modelo 3D (as mesmas do importador de IFC).
CAMADA_DO_PAPEL: Dict[str, str] = {
    "pilar": "Pilares", "viga": "Vigas", "banzo": "Vigas", "diagonal": "Vigas",
    "montante": "Vigas", "terça": "Vigas", "terca": "Vigas", "longarina": "Vigas",
    "contraventamento": "Tirantes", "tirante": "Tirantes", "corrente": "Tirantes",
    "chapa": "Chapas", "barra": "Vigas",
}

#: Papéis que uma peça desenhada pode ter (o que a interface oferece).
PAPEIS: List[str] = ["banzo", "diagonal", "montante", "terça", "longarina", "viga",
                     "pilar", "contraventamento", "tirante", "barra", "chapa"]

TOL_NO = 2.0          # mm: pontas a menos disto são o mesmo nó


@dataclass
class Peca:
    """A informação que uma entidade 2D carrega sobre a peça que ela representa."""
    perfil: str = ""
    papel: str = "barra"
    aco: str = ""
    rotacao: float = 0.0
    espessura: float = 0.0        # chapa: espessura em mm
    material: str = ""

    def valida(self) -> bool:
        return bool(self.perfil) or (self.papel == "chapa" and self.espessura > 0)


def peca_da_entidade(ent: Entidade2D, desenho: Desenho) -> Optional[Peca]:
    """Peça da entidade, ou da camada dela, ou None (anotação)."""
    bruto = (ent.atributos or {}).get("peca")
    if not isinstance(bruto, dict):
        por_camada = (desenho.metadados or {}).get("pecas_por_camada") or {}
        bruto = por_camada.get(ent.camada)
    if not isinstance(bruto, dict):
        return None
    p = Peca(perfil=str(bruto.get("perfil") or ""), papel=str(bruto.get("papel") or "barra"),
             aco=str(bruto.get("aco") or ""), rotacao=float(bruto.get("rotacao") or 0.0),
             espessura=float(bruto.get("espessura") or 0.0),
             material=str(bruto.get("material") or ""))
    return p if p.valida() else None


def _segmentos(ent: Entidade2D) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Trechos retos da entidade: a linha dá um, a polilinha dá um por lado."""
    if isinstance(ent, Linha):
        return [(tuple(ent.a), tuple(ent.b))]
    if isinstance(ent, Polilinha):
        vs = [tuple(v) for v in (ent.vertices or [])]
        if len(vs) < 2:
            return []
        pares = list(zip(vs, vs[1:]))
        if ent.fechada:
            pares.append((vs[-1], vs[0]))
        return pares
    return []


def _no_espaco(plano: dict, origem: Sequence[float], desloc: float, p: Sequence[float]):
    """Ponto 2D do desenho → ponto 3D, no plano escolhido e afastado `desloc` na normal."""
    u, v, n = plano["u"], plano["v"], plano["n"]
    return tuple(origem[i] + u[i] * p[0] + v[i] * p[1] + n[i] * desloc for i in range(3))


def conferir_desenho(desenho: Desenho) -> dict:
    """O que o desenho tem para virar modelo, sem gerar nada.

    Devolve quantas entidades têm peça, quantas são anotação, quais perfis aparecem e
    quais deles o catálogo não conhece — é o que o diálogo mostra antes de gerar.
    """
    from nucleo import catalogo
    com_peca = anotacao = trechos = 0
    perfis: Dict[str, int] = collections.Counter()
    papeis: Dict[str, int] = collections.Counter()
    desconhecidos: List[str] = []
    comprimento = 0.0
    for ent in desenho.entidades.values():
        segs = _segmentos(ent)
        peca = peca_da_entidade(ent, desenho)
        if not segs:
            continue
        if peca is None:
            anotacao += 1
            continue
        com_peca += 1
        trechos += len(segs)
        papeis[peca.papel] += len(segs)
        if peca.perfil:
            perfis[peca.perfil] += len(segs)
            if catalogo.perfil_de(peca.perfil) is None and peca.perfil not in desconhecidos:
                desconhecidos.append(peca.perfil)
        for a, b in segs:
            comprimento += math.dist(a, b)
    return {
        "entidades": len(desenho.entidades), "com_peca": com_peca, "anotacao": anotacao,
        "barras": trechos, "comprimento_m": round(comprimento / 1000.0, 2),
        "perfis": dict(perfis), "papeis": dict(papeis),
        "perfis_desconhecidos": desconhecidos,
        "camadas_com_peca": sorted((desenho.metadados or {}).get("pecas_por_camada") or {}),
    }


def modelo_do_desenho(desenho: Desenho, *, plano: str = "frente",
                      origem: Sequence[float] = (0.0, 0.0, 0.0),
                      repeticoes: int = 1, espacamento: float = 5000.0,
                      conjunto: str = "M", aco_padrao: str = "ASTM A572 Gr.50",
                      nome: str = "", doc: Optional[Documento] = None) -> Documento:
    """Monta o documento 3D do desenho. `doc` acrescenta ao modelo existente.

    Cada cópia (repetição) é um conjunto de montagem, como no IFC: M1, M2… As posições
    (P1, P2…) são numeradas por perfil e comprimento, então duas diagonais iguais em
    tesouras diferentes têm a mesma posição — que é o que a fábrica espera.
    """
    from nucleo import catalogo
    if plano not in PLANOS:
        raise ErroDeDados("plano do desenho deve ser um de: %s" % ", ".join(PLANOS))
    if repeticoes < 1:
        raise ErroDeDados("o número de cópias tem de ser pelo menos 1")
    p = PLANOS[plano]
    info = conferir_desenho(desenho)
    if info["perfis_desconhecidos"]:
        raise ErroDeDados("perfil fora do catálogo: %s. Escolha a peça pelo catálogo no CAD."
                          % ", ".join(info["perfis_desconhecidos"]))
    if not info["barras"]:
        raise ErroDeDados("nenhuma linha do desenho tem peça do catálogo: marque as peças "
                          "(ou a camada) antes de gerar o modelo.")

    doc = doc or Documento(nome=nome or desenho.nome or "Modelo")
    for nome_camada in set(CAMADA_DO_PAPEL.values()):
        doc.camadas.setdefault(nome_camada, Camada(nome=nome_camada))

    # --- 1. levanta os trechos com peça, uma vez (o desenho é o mesmo em toda cópia)
    trechos = []
    for ent in desenho.entidades.values():
        peca = peca_da_entidade(ent, desenho)
        if peca is None:
            continue
        for a, b in _segmentos(ent):
            L = math.dist(a, b)
            if L < 1.0:
                continue
            trechos.append({"ent": ent, "peca": peca, "a": a, "b": b, "L": L})

    # --- 2. posições: mesmo perfil e mesmo comprimento (ao mm) são a mesma peça
    grupos: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for t in trechos:
        grupos[(t["peca"].perfil, t["peca"].papel, round(t["L"]))].append(t)
    ordem = sorted(grupos.items(), key=lambda kv: (-len(kv[1]), -kv[0][2], kv[0][0]))
    posicao_de: Dict[tuple, str] = {}
    for i, (chave, _lista) in enumerate(ordem, start=1):
        posicao_de[chave] = "P%d" % i

    # --- 3. gera as cópias
    criadas = 0
    for k in range(repeticoes):
        desloc = k * float(espacamento)
        marca_conj = "%s%d" % (conjunto, k + 1) if repeticoes > 1 else str(conjunto)
        for t in trechos:
            peca, chave = t["peca"], (t["peca"].perfil, t["peca"].papel, round(t["L"]))
            perfil = catalogo.perfil_de(peca.perfil)
            b = Barra(
                nome=peca.perfil,
                inicio=_no_espaco(p, origem, desloc, t["a"]),
                fim=_no_espaco(p, origem, desloc, t["b"]),
                perfil=perfil.nome if perfil else peca.perfil,
                rotacao=peca.rotacao, papel=peca.papel,
                aco=peca.aco or aco_padrao,
                camada=CAMADA_DO_PAPEL.get(peca.papel, "Vigas"),
                material=peca.material or "",
            )
            b.atributos = {
                "tipo_ifc": b.tipo_ifc(),
                # as mesmas marcas que o IFC de fábrica traz: é o que liga o desenho ao
                # detalhamento, à lista de materiais e ao cálculo
                "marcas": {"posicao": posicao_de[chave], "conjunto": marca_conj,
                           "perfil": perfil.nome if perfil else peca.perfil},
                "origem": {"desenho": desenho.nome, "entidade": t["ent"].id,
                           "camada_2d": t["ent"].camada},
                "peso_kg": round((perfil.massa if perfil else 0.0) * t["L"] / 1000.0, 3),
            }
            doc.add(b)
            criadas += 1

    doc.metadados["de_desenho"] = {
        "desenho": desenho.nome, "plano": plano, "origem": list(origem),
        "repeticoes": repeticoes, "espacamento": espacamento, "conjunto": conjunto,
        "barras": criadas, "posicoes": len(posicao_de),
    }
    return doc
