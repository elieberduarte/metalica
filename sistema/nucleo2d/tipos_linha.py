"""Tipos de linha e espessuras do CAD 2D, como no AutoCAD (pedido do usuário, 23/10: "precisamos criar outros tipos de
linhas (tracejada, pontilhada....) igual existe no autocad, e a opção de mexer nas espessuras").

Espelho de web/cad/nucleo/tipos_linha.js: os nomes do acadiso.lin (o AutoCAD os reconhece no DXF), o padrão em mm de
papel (+ traço, − espaço, 0 ponto) e as espessuras do AutoCAD. O padrão sai no papel × a escala dos tracejados do
desenho (metadados.estilo.escala_tracejado; vazio = ESCALA_TRACEJADO) — no PDF, e no DXF pelo $LTSCALE."""
from typing import Dict, List, Optional, Tuple

_P = {
    "DASHED": [12.7, -6.35], "HIDDEN": [6.35, -3.175], "CENTER": [31.75, -6.35, 6.35, -6.35], "DOT": [0.0, -6.35],
    "DASHDOT": [12.7, -6.35, 0.0, -6.35], "DIVIDE": [12.7, -6.35, 0.0, -6.35, 0.0, -6.35],
    "PHANTOM": [31.75, -6.35, 6.35, -6.35, 6.35, -6.35], "BORDER": [12.7, -6.35, 12.7, -6.35, 0.0, -6.35],
}
_ROTULOS = {"DASHED": "Tracejada", "HIDDEN": "Oculta", "DOT": "Pontilhada", "DASHDOT": "Traço e ponto", "CENTER": "Centro",
            "DIVIDE": "Traço e dois pontos", "PHANTOM": "Fantasma", "BORDER": "Borda"}

#: nome → (rótulo, padrão em mm de papel)
TIPOS_DE_LINHA: Dict[str, Tuple[str, List[float]]] = {"CONTINUOUS": ("Contínua", [])}
for _n in ("DASHED", "HIDDEN", "DOT", "DASHDOT", "CENTER", "DIVIDE", "PHANTOM", "BORDER"):
    TIPOS_DE_LINHA[_n] = (_ROTULOS[_n], list(_P[_n]))
    TIPOS_DE_LINHA[_n + "2"] = (_ROTULOS[_n] + " (curta)", [v / 2 for v in _P[_n]])
    TIPOS_DE_LINHA[_n + "X2"] = (_ROTULOS[_n] + " (longa)", [v * 2 for v in _P[_n]])

#: as espessuras de linha do AutoCAD, em mm
ESPESSURAS = [0.0, 0.05, 0.09, 0.13, 0.15, 0.18, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.53, 0.6, 0.7, 0.8, 0.9, 1.0, 1.06,
              1.2, 1.4, 1.58, 2.0, 2.11]

#: a escala dos tracejados padrão (o LTSCALE ÷ a escala do desenho): o DASHED de 12,7 mm sai com 6,35 mm no papel
ESCALA_TRACEJADO = 0.5


def padrao(nome: Optional[str]) -> List[float]:
    return list(TIPOS_DE_LINHA.get(str(nome or "CONTINUOUS").upper(), TIPOS_DE_LINHA["CONTINUOUS"])[1])


def escala_tracejado(estilo: Optional[dict]) -> float:
    try:
        v = float((estilo or {}).get("escala_tracejado") or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else ESCALA_TRACEJADO


def estilo_da_linha(e, cam) -> Tuple[str, float]:
    """(tipo de linha, espessura em mm) de um objeto: os dele, senão os da camada ("pela camada")."""
    tl = getattr(e, "tipo_linha", None) or (getattr(cam, "tipo_linha", None) if cam is not None else None) or "CONTINUOUS"
    esp = getattr(e, "espessura", None)
    if esp is None:
        esp = getattr(cam, "espessura", None) if cam is not None else None
    return str(tl).upper(), float(0.25 if esp is None else esp)
