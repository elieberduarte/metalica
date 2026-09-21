# -*- coding: utf-8 -*-
"""Extrai o banco de perfis das tabelas do Anexo do manual (já conferidas) para JSON."""
import re, html, json, os, math

BASE = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(BASE, "..", "..", "manual", "capitulos", "cap17_anexos.html")


def num(s):
    s = s.replace("\xa0", "").replace(" ", "").replace("—", "").strip()
    if not s or s == "-":
        return None
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") == 0 else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def celulas(row):
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def tabelas(texto):
    out = []
    for t in re.findall(r'<table class="tab[^"]*">(.*?)</table>', texto, re.S):
        linhas = [celulas(r) for r in re.findall(r"<tr>(.*?)</tr>", t, re.S)]
        out.append([l for l in linhas if l])
    return out


def main():
    texto = open(FONTE, encoding="utf-8").read()
    tabs = tabelas(texto)
    banco = {"I": [], "U": [], "L": [], "Ue": [], "tubo": []}

    # --- Tabela 17.1: perfis W e HP ---
    for l in tabs[0][1:]:
        if len(l) < 14 or not l[0].startswith(("W ", "HP ")):
            continue
        d, bf, tw, tf, massa, A, Ix, Wx, Zx, rx, Iy, Wy, ry = [num(x) for x in l[1:14]]
        if None in (d, bf, tw, tf, A, Ix, Iy):
            continue
        h = d - 2 * tf                      # altura livre da alma (mm)
        J = (2 * bf * tf ** 3 + h * tw ** 3) / 3 / 1e4       # cm4
        Cw = Iy * ((d - tf) / 10) ** 2 / 4                   # cm6
        Zy = (2 * (bf / 10) ** 2 * (tf / 10) / 4) + ((h / 10) * (tw / 10) ** 2 / 4)  # cm3
        banco["I"].append(dict(nome=l[0], familia="HP" if l[0].startswith("HP") else "W",
                               d=d, bf=bf, tw=tw, tf=tf, massa=massa, A=A,
                               Ix=Ix, Wx=Wx, Zx=Zx, rx=rx, Iy=Iy, Wy=Wy, ry=ry,
                               Zy=round(Zy, 1), J=round(J, 2), Cw=round(Cw, 0)))

    # --- Tabela 17.2: cantoneiras de abas iguais ---
    for l in tabs[1][1:]:
        if len(l) < 8 or not l[0].startswith("L "):
            continue
        m = re.match(r"([\d,\.]+)×([\d,\.]+)", l[1].replace(" ", ""))
        if not m:
            continue
        b, t = num(m.group(1)), num(m.group(2))
        massa, A, Ix, Wx, rx, rmin = [num(x) for x in l[2:8]]
        if None in (b, t, A, Ix):
            continue
        # cantoneira de abas iguais: propriedades derivadas
        J = 2 * (b / 10) * (t / 10) ** 3 / 3          # cm4 (seção aberta de paredes finas)
        banco["L"].append(dict(nome=l[0], b=b, t=t, massa=massa, A=A, Ix=Ix, Iy=Ix,
                               Wx=Wx, rx=rx, ry=rx, rmin=rmin, J=round(J, 3),
                               uso=l[8] if len(l) > 8 else ""))

    # --- Tabela 17.3: U laminados e U/Ue formados a frio ---
    for l in tabs[2][1:]:
        if len(l) < 9:
            continue
        nome = l[0]
        dim = l[1]
        massa, A, Ix, Wx, rx, Iy, ry = [num(x) for x in l[2:9]]
        if A is None or Ix is None:
            continue
        d = bf = t = None
        m = re.match(r"([\d,\.]+)×([\d,\.]+)(?:×([\d,\.]+))?×?([\d,\.]+)?", dim.replace("\xa0", ""))
        if m:
            g = [num(x) if x else None for x in m.groups()]
            d, bf = g[0], g[1]
            t = g[3] if g[3] is not None else g[2]
        reg = dict(nome=nome, dim=dim, d=d, bf=bf, t=t, massa=massa, A=A,
                   Ix=Ix, Wx=Wx, rx=rx, Iy=Iy, ry=ry)
        (banco["Ue"] if nome.startswith(("Ue", "U e", "U 1", "U 2", "U 3")) and "\"" not in nome
         else banco["U"]).append(reg)

    # --- Tabela 17.4: tubos (três grupos lado a lado: redondo, quadrado, retangular) ---
    def props_tubo_ret(a, b, t):
        """Ix, Iy, J de tubo retangular a (altura) x b (largura) x t, cantos vivos (cm)."""
        a, b, t = a / 10, b / 10, t / 10
        Ix = (b * a ** 3 - (b - 2 * t) * (a - 2 * t) ** 3) / 12
        Iy = (a * b ** 3 - (a - 2 * t) * (b - 2 * t) ** 3) / 12
        Am = (a - t) * (b - t)                       # área média da parede
        pm = 2 * ((a - t) + (b - t))
        J = 4 * Am ** 2 * t / pm                     # Bredt
        return Ix, Iy, J

    for l in tabs[3][2:]:
        if len(l) < 12:
            continue
        # redondo: D×t
        m = re.match(r"([\d,\.]+)×([\d,\.]+)", l[0].replace(" ", ""))
        if m:
            D, t = num(m.group(1)), num(m.group(2))
            massa, A, r = num(l[1]), num(l[2]), num(l[3])
            if None not in (D, t, A):
                Dc, tc = D / 10, t / 10
                I = math.pi * (Dc ** 4 - (Dc - 2 * tc) ** 4) / 64
                banco["tubo"].append(dict(nome=f"TC {l[0]}", tipo="redondo", D=D, t=t,
                                          massa=massa, A=A, Ix=round(I, 1), Iy=round(I, 1),
                                          Wx=round(I / (Dc / 2), 1), rx=r, ry=r,
                                          J=round(2 * I, 1)))
        # quadrado e retangular
        for i0, tipo in ((4, "quadrado"), (8, "retangular")):
            m = re.match(r"([\d,\.]+)×([\d,\.]+)×([\d,\.]+)", l[i0].replace(" ", ""))
            if not m:
                continue
            a_, b_, t_ = num(m.group(1)), num(m.group(2)), num(m.group(3))
            massa, A = num(l[i0 + 1]), num(l[i0 + 2])
            if None in (a_, b_, t_, A):
                continue
            # convenção: x é o eixo de maior inércia (altura = maior dimensão)
            h_, w_ = max(a_, b_), min(a_, b_)
            Ix, Iy, J = props_tubo_ret(h_, w_, t_)
            banco["tubo"].append(dict(nome=f"T{'Q' if tipo=='quadrado' else 'R'} {l[i0]}",
                                      tipo=tipo, h=h_, b=w_, t=t_, massa=massa, A=A,
                                      Ix=round(Ix, 1), Iy=round(Iy, 1),
                                      Wx=round(Ix / (h_ / 20), 1), Wy=round(Iy / (w_ / 20), 1),
                                      rx=round(math.sqrt(Ix / A), 2), ry=round(math.sqrt(Iy / A), 2),
                                      J=round(J, 1), uso=l[i0 + 3] if len(l) > i0 + 3 else ""))

    saida = os.path.join(BASE, "perfis.json")
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(banco, f, ensure_ascii=False, indent=1)
    for k, v in banco.items():
        print(f"{k}: {len(v)} perfis")
    print("gravado em", saida)


if __name__ == "__main__":
    main()
