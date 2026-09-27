# -*- coding: utf-8 -*-
"""As folhas do projeto recebido: o que o projetista escreveu no espaço do papel do DXF.

A importação do desenho lê o espaço do modelo; as pranchas (molduras, carimbo, notas e as
janelas que mostram o modelo) ficam no espaço do papel e não chegavam ao programa. Daqui sai
o que é dado do projeto:

* as folhas: número ("06/15"), título (o texto do carimbo que muda de uma folha para outra),
  formato da moldura (1189×840…);
* o carimbo: cliente, obra, local, desenhista, escala, data, revisão, responsável técnico;
* as "considerações de cálculo": as cargas por m² e a velocidade do vento que o projetista
  adotou — as mesmas do cálculo dele, para o nosso cálculo partir delas;
* as normas e as especificações de material.

`ler(texto_dxf)` devolve esse dicionário; `cargas_kN(dados)` converte as cargas para kN/m².
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional

from nucleo2d.dxf_ler import codigos_de_texto, ler_dxf, mtext_limpo

KGF = 9.80665e-3          # kN por kgf

# item das considerações de cálculo → chave nossa
_CARGAS = [(r"TELHA", "telha"), (r"FORRO|INSTALA", "forro"), (r"SOBRECARGA DE UTILIZA|SOBRECARGA$|UTILIZA", "sobrecarga"),
           (r"VENTO", "vento"), (r"PAIN[EÉ]IS|SOLAR", "paineis")]
_ROTULOS = {"CLIENTE": "cliente", "OBRA": "obra", "LOCAL": "local"}
_ROTULOS_ABAIXO = {"DESENHO": "desenhista", "ESCALA": "escala", "DATA": "data", "REVIS[ÃA]O": "revisao"}
_ROTULO = re.compile(r"(?i)(DESENHO|ESCALA|DATA|REVIS[ÃA]O|FOLHA|CLIENTE|OBRA|LOCAL)\s*:?")
_NAO_TITULO = re.compile(r"(?i)https?:|www\.|@|\.dxf$|\.dwg$|CNPJ|FONE|CEP|CREA|^ENG\b|^(DESENHO|ESCALA|DATA|REVIS|FOLHA|"
                         r"CLIENTE|OBRA|LOCAL)\b")


def _limpo(e) -> str:
    t = e.get("texto") or ""
    t = mtext_limpo(t) if e["tipo"] == "MTEXT" else codigos_de_texto(t)
    return re.sub(r"%%[uUoOdDcCpP]", "", t).strip()


def _textos_do_papel(dxf: dict) -> List[dict]:
    """os textos do espaço do papel: os da seção ENTITIES marcados como papel (o layout ativo) e
    os dos blocos *Paper_Space* (os outros layouts)"""
    out = []
    ents = [e for e in dxf["entidades"] if e.get("papel")]
    for nome, b in dxf["blocos"].items():
        if nome.upper().startswith("*PAPER_SPACE"):
            ents += b["ents"]
    for e in ents:
        if e["tipo"] in ("TEXT", "MTEXT", "ATTRIB"):
            s = _limpo(e)
            if s:
                out.append({"x": e["p"][0], "y": e["p"][1], "h": e.get("h") or 0.0, "t": s})
    return out, ents


def _molduras(ents) -> List[tuple]:
    out = []
    for e in ents:
        if e["tipo"] in ("LWPOLYLINE", "POLYLINE") and len(e.get("pts") or ()) >= 4:
            xs = [p[0] for p in e["pts"]]
            ys = [p[1] for p in e["pts"]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if w >= 400 and h >= 250:
                out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def _formato(w: float, h: float) -> str:
    for nome, (a, b) in {"A0": (1189, 841), "A1": (841, 594), "A2": (594, 420), "A3": (420, 297)}.items():
        if abs(w - a) <= 3 and abs(h - b) <= 3:
            return nome
    return "%.0f×%.0f" % (w, h)


def _numero(s: str) -> Optional[str]:
    m = re.fullmatch(r"(\d{1,3})\s*/\s*(\d{1,3})", s)
    return "%02d/%02d" % (int(m.group(1)), int(m.group(2))) if m and int(m.group(1)) <= int(m.group(2)) else None


def ler(texto: str) -> dict:
    dxf = ler_dxf(texto)
    tx, ents = _textos_do_papel(dxf)
    molduras = _molduras(ents)

    # --- as folhas: o número embaixo do rótulo FOLHA
    rot_folha = [t for t in tx if re.fullmatch(r"(?i)folha", t["t"])]
    folhas = []
    for t in tx:
        n = _numero(t["t"])
        if not n or not any(abs(r["x"] - t["x"]) < 20 and 3 < r["y"] - t["y"] < 25 for r in rot_folha):
            continue
        # a moldura: a menor que contém o número
        dentro = [m for m in molduras if m[0] <= t["x"] <= m[2] and m[1] <= t["y"] <= m[3]]
        m = max(dentro, key=lambda m: (m[2] - m[0]) * (m[3] - m[1])) if dentro else None
        folhas.append({"numero": n, "x": t["x"], "y": t["y"], "moldura": m,
                       "formato": _formato(m[2] - m[0], m[3] - m[1]) if m else None})
    folhas.sort(key=lambda f: f["numero"])

    def do_carimbo(f):
        return [t for t in tx if -300 < t["x"] - f["x"] < 80 and -45 < t["y"] - f["y"] < 90]

    # --- o título: o texto do carimbo que muda de uma folha para outra
    cont = collections.Counter()
    for f in folhas:
        cont.update({t["t"] for t in do_carimbo(f)})
    fixos = {s for s, n in cont.items() if len(folhas) > 2 and n >= 0.6 * len(folhas)}
    for f in folhas:
        cand = [t for t in do_carimbo(f) if t["t"] not in fixos and not _numero(t["t"]) and not _NAO_TITULO.search(t["t"])
                and not re.search(r"\d+[,.]\d+\s*(KGF|M/S|KN)", t["t"], re.I)]
        cand.sort(key=lambda t: (math.hypot(t["x"] - f["x"], t["y"] - f["y"])))
        f["titulo"] = cand[0]["t"] if cand else None

    # --- o carimbo (o da primeira folha; é o mesmo em todas)
    carimbo: Dict[str, str] = {}
    if folhas:
        c = do_carimbo(folhas[0])
        for t in c:
            chave = next((v for k, v in _ROTULOS.items() if re.fullmatch(r"(?i)%s\s*:?" % k, t["t"])), None)
            if chave:
                # o valor: à direita, na mesma linha ou até duas linhas abaixo (o endereço e a cidade)
                vals = sorted((v for v in c if 3 < v["x"] - t["x"] < 100 and -6 < v["y"] - t["y"] < 3
                               and not _ROTULO.fullmatch(v["t"]) and not _numero(v["t"])), key=lambda v: -v["y"])
                if vals:
                    carimbo[chave] = " — ".join(v["t"] for v in vals)
            chave = next((v for k, v in _ROTULOS_ABAIXO.items() if re.fullmatch(r"(?i)%s\s*:?" % k, t["t"])), None)
            if chave:
                vals = sorted((v for v in c if abs(v["x"] - t["x"]) < 15 and 1.5 < t["y"] - v["y"] < 7), key=lambda v: t["y"] - v["y"])
                if vals:
                    carimbo[chave] = vals[0]["t"]
        crea = next((t for t in c if re.search(r"(?i)CREA", t["t"])), None)
        if crea:
            carimbo["crea"] = crea["t"]
            nome = min((t for t in c if t is not crea and 0 < t["y"] - crea["y"] < 5 and abs(t["x"] - crea["x"]) < 20),
                       key=lambda t: t["y"] - crea["y"], default=None)
            if nome:
                carimbo["responsavel"] = nome["t"]

    # --- as considerações de cálculo: "1- PESO DAS TELHAS ........ 5,00 KGF/M2"
    cargas: Dict[str, dict] = {}
    cab = next((t for t in tx if re.search(r"(?i)CONSIDERA[ÇC][ÕO]ES DE C[ÁA]LCULO", t["t"])), None)
    if cab:
        itens = [t for t in tx if 0 <= t["x"] - cab["x"] < 30 and -40 < t["y"] - cab["y"] < 0 and re.match(r"\d+\s*-", t["t"])]
        for it in itens:
            val = min((v for v in tx if 30 < v["x"] - it["x"] < 150 and -3.5 < v["y"] - it["y"] < 1.0
                       and re.search(r"\d+[,.]?\d*\s*(KGF/M2|KGF/M²|KN/M2|KN/M²|M/S)", v["t"], re.I)),
                      key=lambda v: abs(v["y"] - it["y"]), default=None)
            if not val:
                continue
            m = re.search(r"(\d+[,.]?\d*)\s*(KGF/M2|KGF/M²|KN/M2|KN/M²|M/S)", val["t"], re.I)
            chave = next((k for pad, k in _CARGAS if re.search(pad, it["t"].upper())), None)
            if chave and chave not in cargas:
                cargas[chave] = {"valor": float(m.group(1).replace(",", ".")), "unidade": m.group(2).upper().replace("²", "2"),
                                 "texto": re.sub(r"^\d+\s*-\s*", "", it["t"])}

    # --- normas e especificações (uma vez cada)
    normas = sorted({re.sub(r"^\d+\s*-\s*", "", t["t"]) for t in tx if re.search(r"\bNBR\b", t["t"])})
    materiais = []
    for t in tx:
        if re.search(r"(?i)\bA[ÇC]O\b|PARAFUSO|ELETRODO|PORCAS|ARRUELAS|CHAPAS:", t["t"]) and t["t"] not in materiais \
                and not re.search(r"\bNBR\b", t["t"]):
            materiais.append(t["t"])
    return {
        "folhas": [{"numero": f["numero"], "titulo": f["titulo"], "formato": f["formato"]} for f in folhas],
        "carimbo": carimbo,
        "cargas": cargas,
        "normas": normas,
        "materiais": materiais,
        "janelas": sum(1 for e in ents if e["tipo"] == "VIEWPORT"),
    }


def cargas_kN(dados: dict) -> dict:
    """as cargas do projetista em kN/m² (e o vento em m/s), nas chaves do cálculo de esforços"""
    out = {}
    for k, c in (dados.get("cargas") or {}).items():
        v, u = c["valor"], c["unidade"]
        if u == "M/S":
            out["v0"] = v
        else:
            out[k] = round(v * KGF, 4) if u.startswith("KGF") else v
    return out
