# -*- coding: utf-8 -*-
"""DXF do CAD 2D para abrir e continuar editando no AutoCAD (DXF R2010, pela ezdxf).

O que o `Desenho.para_dxf` antigo (R12, saida/dxf.py) não fazia e a fábrica pediu:

* **Cotas funcionais**: cada `Cota` vira uma entidade DIMENSION (linear, alinhada ou
  rotacionada) com o estilo de cota METALICA — no AutoCAD ela estica, muda de texto e
  responde ao DIMSTYLE, em vez de chegar "explodida" em linhas, setas e texto soltos.
  O estilo tem a escala do desenho (DIMSCALE), texto de 2,5 mm de papel acima da
  linha, setas cheias, decimal com vírgula e zeros à direita suprimidos (125, 40,5).
* **Cores**: cada camada sai com a cor dela (cor verdadeira RGB e a ACI mais próxima);
  as quase pretas vão para a ACI 7, que o AutoCAD mostra preta no fundo branco e branca
  no fundo preto. Tipo de linha e espessura também.
* **Texto**: o número das cotas sai na ACI 7 (branco no fundo preto), não na cor da cota;
  estilo METALICA com a fonte da tela do CAD (Segoe UI), altura = altura de
  papel × escala, alinhamento e rotação iguais.
* **Grupos**: tudo o que é de uma peça ou de um conjunto (contorno, furos, cotas, título)
  vira um GROUP com o nome de produção (S_T_2, T1…): um clique no AutoCAD pega a peça
  inteira. Os quadros (TESOURAS, TERÇAS DE COBERTURA…) já agrupam as peças do mesmo tipo.

Unidades: milímetro 1:1 (o "de papel" multiplicado pela escala), como o DXF antigo.
"""
import collections
import math
import re
from typing import Optional

from nucleo2d.desenho import (Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota, Hachura, Chamada)

FONTE = "segoeui.ttf"
ESTILO = "METALICA"
PESOS = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]


def _rgb(hexa: str):
    h = str(hexa or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def _aci_proxima(rgb) -> int:
    from ezdxf.colors import DXF_DEFAULT_COLORS, int2rgb
    melhor, dm = 7, float("inf")
    for i in range(1, 256):
        r, g, b = int2rgb(DXF_DEFAULT_COLORS[i])
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < dm:
            melhor, dm = i, d
    return melhor


def _nome_grupo(texto: str, usados: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_\-$]", "_", str(texto or "PECA")).strip("_")[:28] or "PECA"
    nome, n = base, 1
    while nome.upper() in usados:
        n += 1
        nome = "%s_%d" % (base[:25], n)
    usados.add(nome.upper())
    return nome


def exportar(desenho: Desenho, caminho: str, escala: Optional[float] = None) -> str:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    k = float(escala or desenho.escala or 1.0)
    doc = ezdxf.new("R2010", setup=["linetypes"])
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = k               # tracejados com o tamanho do papel
    doc.header["$DIMSCALE"] = k
    doc.styles.add(ESTILO, font=FONTE)

    ds = doc.dimstyles.new(ESTILO)
    for chave, valor in {"dimscale": k, "dimtxt": 2.5, "dimasz": 2.5, "dimexe": 2.0, "dimexo": 1.5,
                         "dimgap": 1.0, "dimtad": 1, "dimtih": 0, "dimtoh": 0, "dimdec": 1, "dimzin": 8,
                         # linhas e chamadas na cor da camada; o número na ACI 7 (branco no fundo preto),
                         # como os textos — com 0 (PorBloco) ele herdava a cor da camada da cota
                         "dimdsep": ord(","), "dimlunit": 2, "dimclrd": 0, "dimclre": 0, "dimclrt": 7,
                         "dimtix": 0, "dimsah": 0, "dimtmove": 2, "dimatfit": 3}.items():
        ds.dxf.set(chave, valor)
    ds.dxf.dimtxsty = ESTILO

    # camadas com a cor, o tipo de linha e a espessura do CAD
    tipos = {lt.dxf.name.upper(): lt.dxf.name for lt in doc.linetypes}
    for nome, cam in desenho.camadas.items():
        if nome in doc.layers:
            lay = doc.layers.get(nome)
        else:
            lay = doc.layers.add(nome)
        rgb = _rgb(cam.cor)
        lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0
        if lum < 0.25:
            lay.color = 7                   # preto no fundo branco, branco no fundo preto
        else:
            lay.color = _aci_proxima(rgb)
            lay.rgb = rgb
        lt = tipos.get(str(cam.tipo_linha or "CONTINUOUS").upper())
        lay.dxf.linetype = lt or "Continuous"
        lay.dxf.lineweight = min(PESOS, key=lambda p: abs(p - float(cam.espessura or 0.25) * 100))
        if not cam.visivel:
            lay.off()

    msp = doc.modelspace()
    terminador = (desenho.metadados.get("estilo") or {}).get("terminador") or "traco"
    alinhar = {("esquerda", "base"): TextEntityAlignment.LEFT, ("centro", "base"): TextEntityAlignment.CENTER,
               ("direita", "base"): TextEntityAlignment.RIGHT, ("esquerda", "meio"): TextEntityAlignment.MIDDLE_LEFT,
               ("centro", "meio"): TextEntityAlignment.MIDDLE_CENTER, ("direita", "meio"): TextEntityAlignment.MIDDLE_RIGHT,
               ("esquerda", "topo"): TextEntityAlignment.TOP_LEFT, ("centro", "topo"): TextEntityAlignment.TOP_CENTER,
               ("direita", "topo"): TextEntityAlignment.TOP_RIGHT}
    grupos = collections.OrderedDict()          # chave → [entidades DXF]
    nomes = {}

    def camada_de(e):
        nome = e.camada or "0"
        if nome not in doc.layers:
            doc.layers.add(nome)
        return nome

    for e in desenho.entidades.values():
        cam = desenho.camadas.get(e.camada)
        if cam is not None and not cam.visivel:
            continue
        at = {"layer": camada_de(e)}
        feitas = []
        if isinstance(e, Linha):
            feitas.append(msp.add_line(e.a, e.b, dxfattribs=at))
        elif isinstance(e, Polilinha):
            if len(e.vertices) >= 2:
                feitas.append(msp.add_lwpolyline(e.vertices, close=bool(e.fechada), dxfattribs=at))
        elif isinstance(e, Circulo):
            feitas.append(msp.add_circle(e.centro, e.raio, dxfattribs=at))
        elif isinstance(e, Arco):
            feitas.append(msp.add_arc(e.centro, e.raio, e.inicio, e.fim, dxfattribs=at))
        elif isinstance(e, Texto):
            if str(e.texto or "").strip():
                t = msp.add_text(str(e.texto), height=float(e.altura) * k, rotation=float(e.angulo or 0.0),
                                 dxfattribs=dict(at, style=ESTILO))
                t.set_placement(e.posicao, align=alinhar.get((e.alinhamento, e.vertical), TextEntityAlignment.LEFT))
                feitas.append(t)
        elif isinstance(e, Cota):
            d = _dimensao(msp, e, k, at, e.terminador or terminador)
            if d is not None:
                feitas.append(d)
        elif isinstance(e, Hachura):
            if e.contornos and len(e.contornos[0]) >= 3:
                h = msp.add_hatch(dxfattribs=at)
                if e.padrao == "solido":
                    h.set_solid_fill()
                else:
                    h.set_pattern_fill("ANSI31", scale=max(float(e.espacamento) * k / 3.175, 1e-3),
                                       angle=float(e.angulo or 45.0) - 45.0)
                for contorno in e.contornos:
                    if len(contorno) >= 3:
                        h.paths.add_polyline_path(contorno, is_closed=True)
                feitas.append(h)
        elif isinstance(e, Chamada):
            ld = msp.add_leader([e.posicao, e.alvo][::-1], dimstyle=ESTILO, dxfattribs=at)
            t = msp.add_text(str(e.texto or ""), height=float(e.altura) * k, dxfattribs=dict(at, style=ESTILO))
            t.set_placement((e.posicao[0], e.posicao[1] + 0.8 * k), align=TextEntityAlignment.LEFT)
            feitas += [ld, t]
        a = e.atributos or {}
        # a mesma peça em duas pranchas (o desenho das pranchas lado a lado) são dois grupos
        chave = (("posicao", a["posicao"], a.get("prancha_numero")) if a.get("posicao") and a.get("detalhe") == "posicao"
                 else ("conjunto", a["conjunto"], a.get("prancha_numero")) if a.get("conjunto") else None)
        if chave and feitas:
            grupos.setdefault(chave, []).extend(feitas)
            if a.get("nome"):
                nomes.setdefault(chave, a["nome"])
    usados = set()
    for chave, ents in grupos.items():
        if len(ents) < 2:
            continue
        g = doc.groups.new(_nome_grupo(nomes.get(chave) or chave[1], usados),
                           description="%s %s" % (chave[0], chave[1]))
        g.extend(ents)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    doc.saveas(caminho)
    return caminho


def _nome_arquivo(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s-]", "", s).strip().lower())[:50]


def exportar_pranchas(desenhos, pasta: str, base: str = "pranchas") -> dict:
    """O DXF completo com todas as pranchas lado a lado num arquivo só (`pasta/<base>.dxf`) e um
    DXF por prancha, em papel 1:1 com a folha na origem, num ZIP.

    O desenho das pranchas lado a lado é repartido por folha (o mesmo corte do PDF de todas
    as pranchas); a prancha solta antiga ("Prancha NN") sai inteira. Os arquivos ficam em
    `pasta/<base>-dxf/` com o número e o título (01-tesouras.dxf) e o ZIP em `pasta/<base>-dxf.zip`."""
    import os
    import shutil
    import zipfile
    from nucleo2d.desenho import transladar
    from nucleo2d.pranchas import _por_folha, FOLHAS
    folhas = []                                   # (numero, titulo, Desenho na origem, largura da folha)
    for d in desenhos:
        if d.metadados.get("pranchas"):
            infos = [f for f in d.metadados["pranchas"] if f.get("formato") in FOLHAS]
            for info, parte in zip(infos, _por_folha(d)):
                ox, oy = (info.get("origem") or [0.0, 0.0])[:2]
                p = Desenho(nome=parte.nome, escala=1.0)
                p.camadas.update(parte.camadas)
                for e in parte.entidades.values():
                    p.add(transladar(e, -float(ox), -float(oy)))
                folhas.append((int(info.get("numero") or len(folhas) + 1), str(info.get("titulo") or ""), p,
                               FOLHAS[info["formato"]][0]))
        else:
            info = d.metadados.get("prancha") or {}
            caixa = d.caixa()
            larg = FOLHAS[info["formato"]][0] if info.get("formato") in FOLHAS else (caixa[1][0] if caixa else 0.0)
            folhas.append((int(info.get("numero") or len(folhas) + 1), str(info.get("titulo") or d.nome or ""), d, larg))
    destino = os.path.join(pasta, base + "-dxf")
    shutil.rmtree(destino, ignore_errors=True)    # sem as pranchas de uma montagem anterior
    os.makedirs(destino, exist_ok=True)
    arquivos, usados = [], set()
    for numero, titulo, p, _larg in folhas:
        nome = "%02d" % numero + ("-" + _nome_arquivo(titulo) if _nome_arquivo(titulo) else "")
        while nome in usados:
            nome += "-b"
        usados.add(nome)
        arquivos.append(exportar(p, os.path.join(destino, nome + ".dxf"), 1.0))     # prancha: papel 1:1
    zipado = os.path.join(pasta, base + "-dxf.zip")
    with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
        for a in arquivos:
            z.write(a, os.path.basename(a))
    # o completo: as folhas lado a lado, na ordem, com 50 mm entre elas
    junto, x, n = Desenho(nome=base, escala=1.0), 0.0, 0
    for numero, _titulo, p, larg in folhas:
        for k, cam in p.camadas.items():
            junto.camadas.setdefault(k, cam)
        for e in p.entidades.values():
            q = transladar(e, x, 0.0)
            q.atributos = dict(q.atributos or {}, prancha_numero=numero)
            if q.id in junto.entidades:
                n += 1
                q.id = "%s-%d" % (q.id, n)
            junto.add(q)
        x += larg + 50.0
    completo = exportar(junto, os.path.join(pasta, base + ".dxf"), 1.0)
    return {"completo": completo, "zip": zipado, "pasta": destino, "arquivos": arquivos}


#: o traço oblíquo do DXF (o bloco _OBLIQUE, de -0,5 a +0,5 nos dois eixos, na escala de 2 × DIMTSZ) com o
#: comprimento do da tela, que é o da seta
FATOR_TRACO = 1.0 / (2.0 * math.sqrt(2.0))


def _dimensao(msp, c: Cota, k: float, at: dict, terminador: str = "traco"):
    """DIMENSION linear (h, v) ou rotacionada na direção p1→p2 (alinhada), com a linha de
    cota onde o CAD a desenha: deslocamento de papel × escala, à esquerda de p1→p2.

    A ponta, o tamanho dela e o lugar do número são os da tela do CAD (`Tela._cota` e
    `Tela.textoCota`, web/cad/nucleo/tela.js): o traço oblíquo da produção (ou a seta, a bola),
    do tamanho que encolhe na cota curta (¼ do comprimento, entre 1 e 2,5 mm de papel); o
    número no meio, acima da linha; na cota curta demais, ao lado, fora das chamadas; quando
    só o número não cabe, um degrau para fora; e onde foi posto à mão. Antes a ponta era a
    seta cheia de 2,5 mm, que o AutoCAD jogava para fora, e o número ia para outro lugar (01/10)."""
    x1, y1 = c.p1
    x2, y2 = c.p2
    if c.modo == "h":
        y2p, x2p = y1, x2
    elif c.modo == "v":
        y2p, x2p = y2, x1
    else:
        x2p, y2p = x2, y2
    dx, dy = x2p - x1, y2p - y1
    comp = math.hypot(dx, dy)
    if comp < 1e-6:
        return None
    ux, uy = dx / comp, dy / comp
    nx, ny = -uy, ux
    desl = float(c.deslocamento or 0.0) * k
    base = (x1 + nx * desl, y1 + ny * desl)
    ang = 0.0 if c.modo == "h" else 90.0 if c.modo == "v" else math.degrees(math.atan2(dy, dx))
    altura = float(c.altura or 2.5)
    h = altura * k
    seta = min(2.5 * k, max(1.0 * k, comp / 4))            # mm do desenho
    override = {"dimtxt": altura, "dimasz": seta / k,
                # o número a 0,55 da altura acima da linha, como na tela
                "dimgap": 0.55 * altura}
    if terminador == "traco":
        override.update(dimtsz=FATOR_TRACO * seta / k, dimdle=0.0)
    elif terminador == "bola":
        override.update(dimblk="DOT", dimblk1="DOT", dimblk2="DOT")
    texto = str(c.texto) if c.texto not in (None, "") else "<>"
    n_txt = len(str(c.texto)) if c.texto not in (None, "") else len("%g" % round(comp, 1))
    # o lado de leitura do número (o "de cima" dele): a esquerda de p1→p2, ou a direita quando a cota
    # aponta para trás (o texto gira 180° para não ficar de cabeça para baixo)
    ang_g = math.degrees(math.atan2(uy, ux))
    lado = 1.0 if -90.0 < ang_g <= 90.0 else -1.0
    sobe = 1.05 * h * lado                                  # da linha ao meio do número (base a 0,55 h)
    fora = comp < 3 * seta
    local = None
    if c.texto_pos:
        # a tela guarda a base do número; o DXF, o meio
        local = (c.texto_pos[0] + nx * lado * 0.5 * h, c.texto_pos[1] + ny * lado * 0.5 * h)
    else:
        mx, my = base[0] + dx / 2, base[1] + dy / 2
        if fora:
            avanco = 2.4 * seta + 0.4 * h * n_txt
            local = (mx + ux * avanco + nx * sobe, my + uy * avanco + ny * sobe)
        elif 0.62 * h * n_txt + 2 * seta > comp:
            sg = 1.0 if desl >= 0 else -1.0
            local = (mx + nx * (sg * 1.9 * h + sobe), my + ny * (sg * 1.9 * h + sobe))
    if local is not None:
        override["dimtmove"] = 2                            # o número solto, sem puxar a linha nem chamada
    dim = msp.add_linear_dim(base=base, p1=c.p1, p2=c.p2, angle=ang, dimstyle=ESTILO, text=texto,
                             location=local, override=override, dxfattribs=at)
    dim.render()
    return dim.dimension
