# -*- coding: utf-8 -*-
"""Regras da fábrica e perfis da fábrica.

Um perfil dobrado (U, Ue/C, Z, cartola, cantoneira dobrada) "existe" quando a fábrica
consegue fazê-lo: a espessura é de uma bobina que ela tem, a tira desenvolvida cabe na
largura que ela corta e as medidas ficam nos limites da dobradeira. Perfil laminado (W,
cantoneira em polegada, tubo, barra redonda) não se inventa: só do catálogo dos
fornecedores. Assim ninguém cadastra perfil que não existe, e ninguém precisa pedir
licença para usar o U92X30X#13 que a fábrica dobra todo dia.

As regras ficam em `<dados>/fabrica/regras.json` (a pasta de instalação não aceita
escrita); os perfis fora do catálogo que foram usados, em `<dados>/fabrica/perfis.json`,
com a data da primeira vez, os projetos e quem usou — a lista "perfis da fábrica".
"""
import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional

#: Valores de partida, típicos de dobradeira de perfis leves — A CONFERIR com a fábrica
#: (a tela do catálogo mostra e deixa editar).
REGRAS_PADRAO = {
    "conferidas": False,
    # espessuras de bobina (mm) — as bitolas usuais; a fábrica tira ou põe
    "espessuras": [1.50, 1.90, 2.00, 2.25, 2.65, 3.00, 3.35, 3.75, 4.25, 4.50, 4.75],
    "largura_max_tira": 600.0,          # maior desenvolvido que se corta da bobina (mm)
    "comprimento_max": 12000.0,         # maior peça que a dobradeira faz (mm)
    "altura_min": 30.0, "altura_max": 400.0,
    "aba_min": 20.0, "aba_max": 150.0,
    "enrijecedor_min": 10.0, "enrijecedor_max": 40.0,
    "raio_interno_em_t": 1.0,           # raio interno da dobra, em espessuras
}

_TRAVA = threading.Lock()


def _pasta(dados: str) -> str:
    p = os.path.join(dados, "fabrica")
    os.makedirs(p, exist_ok=True)
    return p


def _gravar(caminho: str, obj) -> None:
    tmp = caminho + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def regras(dados: str) -> dict:
    caminho = os.path.join(_pasta(dados), "regras.json")
    r = dict(REGRAS_PADRAO)
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                r.update(json.load(f) or {})
        except (OSError, ValueError):
            pass
    return r


def gravar_regras(dados: str, novas: dict) -> dict:
    """Grava as regras (só as chaves conhecidas, com os números conferidos)."""
    r = regras(dados)
    for k, v in (novas or {}).items():
        if k not in REGRAS_PADRAO:
            continue
        if k == "espessuras":
            vals = sorted({round(float(str(x).replace(",", ".")), 3) for x in (v or []) if str(x).strip()})
            if not vals or any(x <= 0 or x > 25 for x in vals):
                raise ValueError("espessuras de bobina inválidas.")
            r[k] = vals
        elif k == "conferidas":
            r[k] = bool(v)
        else:
            x = float(str(v).replace(",", "."))
            if x < 0:
                raise ValueError("%s não pode ser negativo." % k)
            r[k] = x
    with _TRAVA:
        _gravar(os.path.join(_pasta(dados), "regras.json"), r)
    return r


def validar(perfil: str, dados: str) -> dict:
    """{ok, motivos: [...], tipo: "catalogo" | "dobrado" | "desconhecido", geometria,
    desenvolvido}. Perfil do catálogo passa sempre; dobrado passa pelas regras."""
    from saida import dobras
    nome = str(perfil or "").strip()
    if not nome:
        return {"ok": False, "motivos": ["informe o perfil."], "tipo": "desconhecido"}
    import re
    no_catalogo = _no_catalogo(nome)
    g = dobras.geometria(nome)
    if g is None:
        if no_catalogo:
            return {"ok": True, "motivos": [], "tipo": "catalogo"}
        b = re.search(r"#\s*(\d+)", nome)
        from nucleo.perfis_fabrica import BITOLAS
        if b and int(b.group(1)) not in BITOLAS:
            return {"ok": False, "tipo": "desconhecido",
                    "motivos": ["bitola #%s desconhecida (conhecidas: %s)." % (b.group(1), ", ".join("#%d" % k for k in sorted(BITOLAS)))]}
        if re.match(r"(?i)^\s*(UE|ZE|CR|U|C|Z|L)\s*\d", nome):
            return {"ok": False, "tipo": "desconhecido",
                    "motivos": ["medidas incompatíveis: a aba ou a alma é curta demais para a espessura."]}
        return {"ok": False, "tipo": "desconhecido",
                "motivos": ["não é um perfil dobrado reconhecido (U, Ue/C, Z, cartola, L dobrada) nem está no "
                            "catálogo dos fornecedores — perfil laminado só pelo catálogo."]}
    r = regras(dados)
    motivos: List[str] = []
    t = g["t"]
    # a mesma bobina escrita pela MSG (4,18 = #8) ou pela ABNT (4,25 = #8) vale
    from nucleo.perfis_fabrica import BITOLAS
    num_b = dobras.bitola_de(t)
    equivalentes = [t] + ([BITOLAS[num_b]] if num_b in BITOLAS else [])
    if not any(abs(x - e) <= 0.03 for x in equivalentes for e in r["espessuras"]):
        motivos.append("espessura %.2f mm não é de bobina da fábrica (%s)."
                       % (t, ", ".join("%.2f" % e for e in r["espessuras"])))
    raio = r.get("raio_interno_em_t", 1.0) * t
    desc = dobras.desconto_por_dobra(t, ri=raio)
    desenv = g["soma_externa"] - g["dobras"] * desc
    if desenv > r["largura_max_tira"] + 0.5:
        motivos.append("tira desenvolvida de %.0f mm passa da largura máxima da fábrica (%.0f mm)."
                       % (desenv, r["largura_max_tira"]))
    if not (r["altura_min"] - 0.5 <= g["h"] <= r["altura_max"] + 0.5):
        motivos.append("altura %.0f mm fora da dobradeira (%.0f a %.0f mm)." % (g["h"], r["altura_min"], r["altura_max"]))
    if not (r["aba_min"] - 0.5 <= g["b"] <= r["aba_max"] + 0.5):
        motivos.append("aba %.0f mm fora da dobradeira (%.0f a %.0f mm)." % (g["b"], r["aba_min"], r["aba_max"]))
    if g["d"] and not (r["enrijecedor_min"] - 0.5 <= g["d"] <= r["enrijecedor_max"] + 0.5):
        motivos.append("enrijecedor %.0f mm fora da dobradeira (%.0f a %.0f mm)."
                       % (g["d"], r["enrijecedor_min"], r["enrijecedor_max"]))
    # a aba tem de ter onde a dobradeira pegar: pelo menos 2 espessuras além do raio
    if g["b"] < 2 * raio + 2 * t:
        motivos.append("aba curta demais para a espessura (mínimo %.0f mm)." % (2 * raio + 2 * t))
    return {"ok": not motivos, "motivos": motivos, "tipo": "catalogo" if no_catalogo else "dobrado",
            "geometria": g, "desenvolvido": round(desenv, 1), "conferidas": bool(r.get("conferidas"))}


def _no_catalogo(nome: str) -> bool:
    try:
        from nucleo import catalogo
        if catalogo.item(nome) is not None:
            return True
        # nome de exportador (W150X13.00, L 2 1/2'' X 1/4'') que o banco de perfis reconhece
        from nucleo.perfis_fabrica import perfil_de_fabrica
        from saida import dobras
        import re
        dobrado = re.match(r"(?i)^\s*(UE|ZE|CR|U|C|Z)\s*\d", nome)
        if not dobrado and dobras.geometria(nome) is None and perfil_de_fabrica(nome) is not None:
            return True
        # "U100X50X#12" também é "U 100×50×2,65 (FF)": pela geometria
        from saida import dobras
        g = dobras.geometria(nome)
        if g is None:
            return False
        fam = {"U": "U", "UE": "Ue", "ZE": "Ze", "L": "L", "CR": "Cr"}.get(g["familia"])
        for it in catalogo.itens(fam) if fam else []:
            dims = str(it.dados.get("dim") or "").split("×")
            try:
                dims = [float(x.replace(",", ".")) for x in dims]
            except ValueError:
                continue
            if len(dims) >= 3 and abs(dims[0] - g["h"]) < 0.6 and abs(dims[1] - g["b"]) < 0.6 \
                    and abs(dims[-1] - g["t"]) < 0.03 and (len(dims) < 4 or abs(dims[2] - g["d"]) < 0.6):
                return True
    except Exception:                                              # noqa: BLE001
        return False
    return False


def perfis(dados: str) -> List[dict]:
    caminho = os.path.join(_pasta(dados), "perfis.json")
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, encoding="utf-8") as f:
            return list(json.load(f) or [])
    except (OSError, ValueError):
        return []


def registrar(dados: str, perfil: str, projeto: str = "", usuario: str = "", maquina: str = "") -> dict:
    """Registra o uso de um perfil fora do catálogo (validado antes). Devolve o registro."""
    v = validar(perfil, dados)
    if not v["ok"]:
        raise ValueError("; ".join(v["motivos"]))
    if v["tipo"] == "catalogo":
        return {"perfil": perfil, "tipo": "catalogo"}
    nome = str(perfil).strip().upper().replace(" ", "")
    agora = datetime.now().isoformat(timespec="seconds")
    with _TRAVA:
        lista = perfis(dados)
        reg = next((p for p in lista if p.get("perfil") == nome), None)
        if reg is None:
            reg = {"perfil": nome, "primeiro_uso": agora, "usuario": usuario, "maquina": maquina,
                   "projetos": [], "usos": 0, "desenvolvido": v["desenvolvido"]}
            lista.append(reg)
        reg["ultimo_uso"] = agora
        reg["usos"] = int(reg.get("usos", 0)) + 1
        if projeto and projeto not in reg["projetos"]:
            reg["projetos"].append(projeto)
        _gravar(os.path.join(_pasta(dados), "perfis.json"), lista)
    return reg


def remover(dados: str, perfil: str) -> bool:
    nome = str(perfil).strip().upper().replace(" ", "")
    with _TRAVA:
        lista = perfis(dados)
        nova = [p for p in lista if p.get("perfil") != nome]
        if len(nova) == len(lista):
            return False
        _gravar(os.path.join(_pasta(dados), "perfis.json"), nova)
    return True
