# -*- coding: utf-8 -*-
"""Perfis pelo **nome de fábrica** — a grafia que o TecnoMETAL (Steel & Graphics) e
programas parecidos gravam no IFC, no Pset "Steel & Graphics Common" → Profile:

    U92X40X2.25          U simples formado a frio, h × bf × t (mm)
    C150X75X20X2.25      Ue (U enrijecido), h × bf × D × t (mm)
    L50X50X2.25          cantoneira em mm, aba × aba × t (formada a frio quando t ≤ 5)
    L1.1/4''X1/8''       cantoneira em polegadas (aba × espessura), catálogo
    L 2 1/2'' X 1/4' '   idem, com a grafia solta que o exportador às vezes usa
    W150X13.00           perfil laminado do catálogo (altura × massa)
    FE RED 3/8''         barra redonda (tirante, contraventamento)
    BARRA ROSCADA Ø 5/8''  barra roscada (a tração é verificada na seção rosqueada)
    TQ50X50X2.00 / TC …  tubos do catálogo

`perfil_de_fabrica(nome)` devolve o `Perfil` de cálculo, ou `None` quando o nome não é
uma barra (chapa, telha, parafuso) ou não é reconhecido — o chamador decide o que
fazer com a peça (o cálculo a exclui e avisa; nada some em silêncio).

O que vem do catálogo (`dados/perfis.json`) sai de lá, com as propriedades tabeladas.
O que não está no catálogo é montado aqui, pelo método linear da linha média (o mesmo
de `nbr14762.propriedades_ue`): U simples e Ue formados a frio, cantoneira formada a
frio e cantoneira de aba desigual. Esses perfis sintéticos ficam registrados em
`nucleo3d.geometria` para o 3D e o resto do sistema os acharem pelo nome.

Unidades: dimensões em mm nos nomes e em `Perfil.dados` (d, bf, t); propriedades em cm.
"""
import math
import re
from typing import Optional, Tuple

from . import nbr14762
from .base import RHO
from .perfis import Perfil, banco

__all__ = ["perfil_de_fabrica", "eh_barra_de_calculo", "polegadas_mm", "secao_frio",
           "perfil_u_frio", "perfil_ue_frio", "perfil_cantoneira", "ESPESSURA_MAX_FRIO"]

#: Até esta espessura (mm) uma cantoneira em milímetro é tratada como formada a frio.
ESPESSURA_MAX_FRIO = 5.0

POLEGADA = 25.4

#: Bitolas de chapa (número → espessura em mm), como o comércio de aço usa no Brasil:
#: "C127X50X17X#14" é um Ue de 2,00 mm (a fábrica usa a bitola da chapa a quente).
BITOLAS = {7: 4.5, 8: 4.25, 9: 3.75, 10: 3.35, 11: 3.0, 12: 2.65, 13: 2.25, 14: 2.0, 15: 1.7, 16: 1.5, 18: 1.2, 20: 0.9}

_NAO_BARRA = ("PLATE", "CH ", "CHAPA", "TELHA", "BOLT", "PARAF", "PORCA", "ARRUELA",
              "GRAUTE", "CHUMB")


def _norm(nome: str) -> str:
    """Grafia única: maiúsculas, '×' → 'X', aspas duplas em vez de '' e "' '", vírgula
    decimal → ponto, espaços comprimidos."""
    s = str(nome or "").strip().upper()
    s = s.replace("×", "X").replace("Ø", " ").replace("Ö", " ").replace("DIAM", " ")
    s = s.replace("' '", '"').replace("''", '"').replace("’’", '"').replace("”", '"')
    s = s.replace("'", '"')
    s = s.replace(",", ".")
    # espessura pela bitola: "X#14" → "X2"
    s = re.sub(r"(\d)\s*#", r"\1X#", s)          # "17#14" = "17X#14"
    s = re.sub(r"#\s*(\d+)", lambda m: ("%g" % BITOLAS[int(m.group(1))]) if int(m.group(1)) in BITOLAS else m.group(0), s)
    # sufixos que o catálogo acrescenta ao nome e não fazem parte da medida
    s = re.sub(r"\((?:FF|MÉTRICA|METRICA)\)", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def polegadas_mm(texto: str) -> Optional[float]:
    """"1.1/4", "1 1/4", "1-1/4", "2", "1/8", com ou sem aspas → mm. None se não é medida."""
    t = _norm(texto).replace('"', "").strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d+)\s*[\s.\-]\s*(\d+)/(\d+)", t)
    if m:
        return (int(m.group(1)) + int(m.group(2)) / int(m.group(3))) * POLEGADA
    m = re.fullmatch(r"(\d+)/(\d+)", t)
    if m:
        return int(m.group(1)) / int(m.group(2)) * POLEGADA
    m = re.fullmatch(r"\d+(?:\.\d+)?", t)
    if m:
        return float(t) * POLEGADA
    return None


def _medida_mm(texto: str) -> Optional[float]:
    """Medida em mm ou em polegadas (com aspas ou fração) → mm."""
    t = _norm(texto)
    if '"' in t or "/" in t:
        return polegadas_mm(t)
    m = re.fullmatch(r"\d+(?:\.\d+)?", t.strip())
    return float(t) if m else None


def eh_barra_de_calculo(nome: str) -> bool:
    """False para chapa, telha, parafuso e afins (que nunca são barra de cálculo)."""
    s = _norm(nome)
    return bool(s) and not any(s.startswith(p) for p in _NAO_BARRA)


# ------------------------------------------------------------------ sintéticos

def _registrar(p: Perfil) -> Perfil:
    try:
        from nucleo3d import geometria
        geometria.registrar_perfil(p)
    except Exception:
        pass
    return p


def _de_secao_frio(sec, tipo_nome: str) -> Perfil:
    """`SecaoUe` (cm) → `Perfil` com os campos que o resto do sistema lê (dados em mm)."""
    dim = "%g×%g×%g" % (sec.h_mm, sec.bf_mm, sec.t_mm) if sec.d_mm <= 0 else \
          "%g×%g×%g×%g" % (sec.h_mm, sec.bf_mm, sec.d_mm, sec.t_mm)
    dados = {"nome": sec.nome, "dim": dim.replace(".", ","), "d": sec.h_mm, "bf": sec.bf_mm,
             "t": sec.t_mm, "tw": sec.t_mm, "tf": sec.t_mm, "massa": round(sec.massa, 3),
             "A": round(sec.A, 4), "Ix": round(sec.Ix, 3), "Wx": round(sec.Wx, 3),
             "rx": round(sec.rx, 4), "Iy": round(sec.Iy, 3), "Wy": round(sec.Wy, 3),
             "ry": round(sec.ry, 4), "J": round(sec.J, 5), "Cw": round(sec.Cw, 4),
             "x0": round(sec.x0, 4), "r0": round(sec.r0, 4), "formado_a_frio": True,
             "sintetico": True}
    return Perfil(nome=sec.nome, tipo="Ue", dados=dados)


def perfil_u_frio(h: float, bf: float, t: float, nome: str = "") -> Perfil:
    """U simples formado a frio (h × bf × t, mm)."""
    sec = nbr14762.propriedades_u(h, bf, t, nome=nome)
    return _registrar(_de_secao_frio(sec, "U"))


def perfil_ue_frio(h: float, bf: float, d: float, t: float, nome: str = "") -> Perfil:
    """Ue formado a frio (h × bf × D × t, mm). Prefere o do catálogo quando existe."""
    nome_cat = ("Ue %g×%g×%g×%.2f" % (h, bf, d, t)).replace(".", ",")
    p = banco().get(nome_cat)
    if p is not None:
        return p
    sec = nbr14762.propriedades_ue(h, bf, d, t, nome=nome or nome_cat)
    return _registrar(_de_secao_frio(sec, "Ue"))


def _props_cantoneira(b1: float, b2: float, t: float, r: float) -> dict:
    """Propriedades (cm) de uma cantoneira pela linha média: aba `b1` vertical, aba
    `b2` horizontal, canto de raio interno `r`. Devolve também os eixos principais."""
    rm = r + t / 2.0
    pts = [(b2 - t / 2.0, t / 2.0), (t / 2.0 + rm, t / 2.0)]
    pts += nbr14762._arco(t / 2.0 + rm, t / 2.0 + rm, rm, -math.pi / 2, -math.pi)
    pts.append((t / 2.0, b1 - t / 2.0))
    P = nbr14762._limpa(pts)
    p = nbr14762._props_pecas([P], t)
    Ix, Iy, Ixy = p["Ix"], p["Iy"], p["Ixy"]
    med = (Ix + Iy) / 2.0
    raio = math.sqrt(((Ix - Iy) / 2.0) ** 2 + Ixy ** 2)
    p["Imin"], p["Imax"] = med - raio, med + raio
    p["J"] = p["L"] * t ** 3 / 3.0
    return p


def perfil_cantoneira(b1: float, b2: float, t: float, nome: str = "",
                      formada_a_frio: Optional[bool] = None) -> Perfil:
    """Cantoneira b1 × b2 × t (mm). Procura no catálogo (aba igual, ±3 %); senão monta
    pela linha média — com canto de raio t quando formada a frio."""
    if formada_a_frio is None:
        formada_a_frio = t <= ESPESSURA_MAX_FRIO
    if abs(b1 - b2) < 0.5:
        for p in banco().lista("L"):
            pb, pt = float(p.dados.get("b") or 0), float(p.dados.get("t") or 0)
            if pb and pt and abs(pb - b1) / pb <= 0.03 and abs(pt - t) / pt <= 0.06:
                return p
    b1c, b2c, tc = b1 / 10.0, b2 / 10.0, t / 10.0
    rc = tc if formada_a_frio else 0.0
    q = _props_cantoneira(b1c, b2c, tc, rc)
    A = q["A"]
    Wx = q["Ix"] / max(b1c - q["yc"], q["yc"])
    Wy = q["Iy"] / max(b2c - q["xc"], q["xc"])
    if not nome:
        nome = ("L %g×%g×%g" % (b1, b2, t)) if abs(b1 - b2) >= 0.5 else ("L %g×%g" % (b1, t))
        nome = nome.replace(".", ",") + (" (FF)" if formada_a_frio else "")
    dados = {"nome": nome, "b": max(b1, b2), "b2": min(b1, b2), "t": t, "tw": t, "tf": t,
             "d": b1, "bf": b2, "massa": round(A * RHO * 1e-4, 3), "A": round(A, 4),
             "Ix": round(q["Ix"], 3), "Iy": round(q["Iy"], 3), "Ixy": round(q["Ixy"], 3),
             "Wx": round(Wx, 3), "Wy": round(Wy, 3),
             "rx": round(math.sqrt(q["Ix"] / A), 4), "ry": round(math.sqrt(q["Iy"] / A), 4),
             "rmin": round(math.sqrt(max(q["Imin"], 1e-12) / A), 4), "J": round(q["J"], 5),
             "formado_a_frio": bool(formada_a_frio), "sintetico": True}
    return _registrar(Perfil(nome=nome, tipo="L", dados=dados))


def _barra_redonda(d_mm: float, nome: str, rosqueada: bool = False) -> Perfil:
    from nucleo3d import geometria
    p = geometria.barra_redonda(d_mm, nome)
    p.dados["rosqueada"] = bool(rosqueada)
    return _registrar(p)


# ------------------------------------------------------------------ leitura do nome

_RE_U = re.compile(r"^U\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)$")
_RE_UE = re.compile(r"^(?:C|UE|U\s*E)\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)$")
_RE_L3 = re.compile(r"^L\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)$")
_RE_L2 = re.compile(r"^L\s*(.+?)\s*X\s*(.+?)$")
_RE_W = re.compile(r"^(W|HP)\s*(\d+)\s*X\s*(\d+(?:\.\d+)?)$")
_RE_RED = re.compile(r"^(?:FE\s*RED\w*|RD|RED\w*|BARRA\s*RED\w*|VERG\w*)\s*(.+)$")
_RE_ROSCA = re.compile(r"^BARRA\s*ROSC\w*\s*(.+)$")
_RE_TUBO = re.compile(r"^(TQ|TR|TC)\s*(.+)$")


def perfil_de_fabrica(nome: str) -> Optional[Perfil]:
    """`Perfil` de cálculo a partir do nome de fábrica; None se não é barra ou não é
    reconhecido."""
    s = _norm(nome)
    if not s or not eh_barra_de_calculo(s):
        return None
    m = _RE_UE.match(s)
    if m:
        h, bf, d, t = (float(x) for x in m.groups())
        return perfil_ue_frio(h, bf, d, t)
    m = _RE_U.match(s)
    if m:
        h, bf, t = (float(x) for x in m.groups())
        if t <= 8.0:
            return perfil_u_frio(h, bf, t)
        return banco().get(s)
    m = _RE_W.match(s)
    if m:
        fam, h, massa = m.group(1), m.group(2), m.group(3)
        p = banco().get("%s %s×%s" % (fam, h, massa))
        if p is None:
            # massa arredondada de outro jeito ("W150X13" vs "W 150×13,0")
            alvo = float(massa)
            for cand in banco().lista("I"):
                if cand.nome.upper().startswith(fam) and abs(cand.d - float(h)) <= 6 \
                        and abs((cand.massa or 0) - alvo) <= 0.6:
                    return cand
        return p
    m = _RE_ROSCA.match(s)
    if m:
        d = _medida_mm(m.group(1))
        if d:
            return _barra_redonda(d, "Barra roscada ø %s" % _rotulo_d(m.group(1), d), rosqueada=True)
        return None
    m = _RE_RED.match(s)
    if m:
        d = _medida_mm(m.group(1))
        return _barra_redonda(d, "Barra redonda ø %s" % _rotulo_d(m.group(1), d)) if d else None
    m = _RE_TUBO.match(s)
    if m:
        return banco().get(s)
    m = _RE_L3.match(s)
    if m:
        b1, b2, t = (float(x) for x in m.groups())
        return perfil_cantoneira(b1, b2, t)
    m = _RE_L2.match(s)
    if m:
        b = _medida_mm(m.group(1))
        t = _medida_mm(m.group(2))
        if b and t:
            return perfil_cantoneira(b, b, t, formada_a_frio=('"' not in s and t <= ESPESSURA_MAX_FRIO))
        return None
    return banco().get(s)


def _rotulo_d(texto: str, d_mm: float) -> str:
    t = _norm(texto)
    if '"' in t or "/" in t:
        return t.replace(" ", "").replace('"', "") + '" (%s mm)' % ("%g" % round(d_mm, 2)).replace(".", ",")
    return ("%g mm" % round(d_mm, 2)).replace(".", ",")


def secao_frio(p: Perfil):
    """`SecaoUe` de um U ou Ue formado a frio (para as rotinas da NBR 14762)."""
    return nbr14762.secao_do_perfil(p)


def tipo_de_verificacao(p: Perfil) -> str:
    """"frio" (NBR 14762: U e Ue formados a frio), "laminado" (NBR 8800) ou "redonda"."""
    if p.tipo == "Ue":
        return "frio"
    if p.tipo == "barra":
        return "redonda"
    return "laminado"
