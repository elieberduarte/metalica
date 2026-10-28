# -*- coding: utf-8 -*-
"""Leitura de PDF vetorial (projeto exportado do CAD) para o desenho 2D.

O PDF de um projeto estrutural feito no AutoCAD, no TQS ou no Revit guarda as linhas
como caminhos vetoriais e os textos como texto — é isso que se lê aqui (PyMuPDF):

* traços retos viram `Linha` (ou `Polilinha` quando o caminho é contínuo);
* curvas de Bézier são aproximadas; o caminho fechado que é um círculo (as quatro
  Béziers que o CAD usa para o balão do eixo) vira `Circulo`;
* textos, com a rotação da linha de texto e a altura pela fonte;
* camada: a camada do PDF (OCG) quando o exportador a grava; senão a cor do traço
  ("PDF 1f5fbf"), que já separa bem estrutura, cotas e eixos.

Unidades: as coordenadas saem em **milímetro de papel** (1 pt = 25,4/72 mm), com o Y
para cima. A escala de cada vista (1:50, 1:100…) não está no PDF como número: quem a
descobre é o reconhecimento (`nucleo2d.reconhecer`), pelas cotas e pelo título da vista.

Várias páginas entram lado a lado, da esquerda para a direita, com 20 mm entre elas.

PDF digitalizado (só imagem) não tem vetores: o resumo avisa e nada é inventado. Texto
que o CAD exportou desenhado como linhas (fonte SHX) também não se lê — o resumo avisa
quando há muito traço miúdo e pouco texto.
"""
import collections
import math
from typing import List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Camada2D, Circulo, Desenho, Hachura, Linha, Polilinha, Texto

__all__ = ["para_desenho", "PT_MM"]

PT_MM = 25.4 / 72.0          # mm por ponto tipográfico
ESPACO_PAGINAS = 20.0        # mm entre páginas lado a lado

Ponto2 = Tuple[float, float]


def _hex(cor) -> str:
    if not cor:
        return "#16202e"
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in cor[:3])
    return "#%02x%02x%02x" % (r, g, b)


def _bezier(p0, p1, p2, p3, n=8) -> List[Ponto2]:
    pts = []
    for i in range(1, n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _circulo(pts: Sequence[Ponto2]) -> Optional[Tuple[Ponto2, float]]:
    """(centro, raio) quando os pontos estão todos à mesma distância do centróide."""
    if len(pts) < 8:
        return None
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    ds = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    r = sum(ds) / len(ds)
    if r <= 0 or max(abs(d - r) for d in ds) > 0.04 * r + 0.02:
        return None
    return (cx, cy), r


def _contornos(itens, P) -> List[List[Ponto2]]:
    """os subcaminhos de um caminho do PDF (linhas, curvas, retângulos, quadriláteros) como contornos fechados"""
    saida: List[List[Ponto2]] = []
    atual: List[Ponto2] = []

    def fechar():
        nonlocal atual
        if len(atual) >= 3:
            if math.hypot(atual[0][0] - atual[-1][0], atual[0][1] - atual[-1][1]) < 1e-3:
                atual = atual[:-1]
            if len(atual) >= 3:
                saida.append(atual)
        atual = []
    for it in itens or []:
        op = it[0]
        if op in ("l", "c"):
            pts = [P(q.x, q.y) for q in (it[1:3] if op == "l" else it[1:5])]
            if atual and math.hypot(atual[-1][0] - pts[0][0], atual[-1][1] - pts[0][1]) > 1e-3:
                fechar()
            if not atual:
                atual.append(pts[0])
            atual.extend([pts[1]] if op == "l" else [(round(x, 3), round(y, 3)) for x, y in _bezier(*pts)])
        elif op == "re":
            fechar()
            r = it[1]
            atual = [P(r.x0, r.y0), P(r.x1, r.y0), P(r.x1, r.y1), P(r.x0, r.y1)]
            fechar()
        elif op == "qu":
            fechar()
            q = it[1]
            atual = [P(q.ul.x, q.ul.y), P(q.ur.x, q.ur.y), P(q.lr.x, q.lr.y), P(q.ll.x, q.ll.y)]
            fechar()
    fechar()
    return saida


def para_desenho(dados: bytes, destino: Optional[Desenho] = None, paginas: Optional[Sequence[int]] = None,
                 deslocamento: Ponto2 = (0.0, 0.0), prefixo_camada: str = "",
                 preenchimentos: bool = False) -> Tuple[Desenho, dict]:
    """PDF (bytes) → entidades do desenho, em mm de papel. Devolve (desenho, resumo).

    `preenchimentos`: o caminho só preenchido (traço grosso desenhado como polígono cheio, ponta de seta, hachura
    sólida) entra como hachura sólida na cor dele — a folha como foi impressa (Original das obras: na 940 do Edifício
    Administrativo Hora Certa as treliças da marquise são polígonos cheios e sumiam, 28/10). Sem ele (leitura do
    projeto para montar o 3D) fica de fora, como antes. O preenchimento branco (máscara) fica de fora sempre."""
    try:
        import pymupdf
    except ImportError:                                            # pragma: no cover
        import fitz as pymupdf                                     # type: ignore
    if not dados or not bytes(dados[:5]).startswith(b"%PDF"):
        raise ErroDeDados("o arquivo não parece um PDF.")
    try:
        pdf = pymupdf.open(stream=bytes(dados), filetype="pdf")
    except Exception as e:                                         # noqa: BLE001
        raise ErroDeDados("não foi possível abrir o PDF: %s" % e)
    des = destino if destino is not None else Desenho(nome="PDF importado", escala=1.0)
    k_txt = 1.0 / float(des.escala or 1.0)       # altura de texto do papel → a do desenho de destino
    contagem = collections.Counter()
    avisos: List[str] = []
    camadas_novas = set()
    ids: List[str] = []
    x0 = float(deslocamento[0])
    lista = list(paginas) if paginas else list(range(pdf.page_count))
    pags = []

    def camada(nome: str, cor: str) -> str:
        nome = (prefixo_camada + nome).strip() or "0"
        if nome not in des.camadas:
            des.camadas[nome] = Camada2D(nome, cor)
            camadas_novas.add(nome)
        return nome

    def add(ent):
        des.add(ent)
        ids.append(ent.id)
        contagem[ent.tipo] += 1

    for num in lista:
        if num < 0 or num >= pdf.page_count:
            continue
        pg = pdf[num]
        W, H = pg.rect.width, pg.rect.height
        oy = float(deslocamento[1])

        def P(x, y, _x0=x0, _H=H, _oy=oy):
            return (round(_x0 + x * PT_MM, 3), round(_oy + (_H - y) * PT_MM, 3))

        tracos_miudos = 0
        n_antes = len(ids)
        folha = pg.rect
        for d in pg.get_drawings():
            # o caminho todo fora da página não aparece no PDF (o que o CAD deixou fora da janela da folha): não entra —
            # no SESI, 8.811 traços da EMT21 caíam em cima da EMT20 e 9.231 da EMT08 embaixo das folhas (23/10)
            r_d = d.get("rect")
            if r_d is not None and (r_d.x1 < folha.x0 or r_d.x0 > folha.x1 or r_d.y1 < folha.y0 or r_d.y0 > folha.y1):
                contagem["ignorado:fora da página"] += 1
                continue
            cor = d.get("color")
            if cor is None:
                # só preenchimento: ponta de seta, hachura sólida, traço grosso cheio — fica de fora, a não ser que
                # se peçam os preenchimentos (a folha como foi impressa)
                fill = d.get("fill")
                if not preenchimentos or fill is None:
                    contagem["ignorado:preenchimento"] += 1
                    continue
                if all(float(c_) > 0.98 for c_ in fill):
                    contagem["ignorado:preenchimento branco"] += 1
                    continue
                cts = _contornos(d.get("items"), P)
                if not cts:
                    contagem["ignorado:preenchimento"] += 1
                    continue
                cam = camada(str(d.get("layer") or ("PDF " + _hex(fill)[1:])), _hex(fill))
                add(Hachura(camada=cam, contornos=cts, padrao="solido",
                            atributos={"origem": "pdf", "cor": _hex(fill), "preenchimento": True}))
                continue
            nome_cam = d.get("layer") or ("PDF " + _hex(cor)[1:])
            cam = camada(str(nome_cam), _hex(cor))
            atr = {"origem": "pdf", "largura": round(float(d.get("width") or 0.0) * PT_MM, 3)}
            if d.get("dashes") and str(d.get("dashes")).strip() not in ("[] 0", "", "None"):
                atr["tracejado"] = True
            # o caminho é uma sequência de itens; os contíguos formam uma polilinha
            corrida: List[Ponto2] = []

            def fechar_corrida(fechada=False):
                nonlocal corrida, tracos_miudos
                pts = corrida
                corrida = []
                if len(pts) < 2:
                    return
                if fechada or (len(pts) > 3 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-3):
                    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-3:
                        pts = pts[:-1]
                    c = _circulo(pts)
                    if c is not None:
                        add(Circulo(camada=cam, centro=(round(c[0][0], 3), round(c[0][1], 3)), raio=round(c[1], 3),
                                    atributos=dict(atr)))
                        return
                    if len(pts) >= 3:
                        add(Polilinha(camada=cam, vertices=pts, fechada=True, atributos=dict(atr)))
                        return
                comp = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
                if comp < 1.2:
                    tracos_miudos += 1
                if len(pts) == 2:
                    add(Linha(camada=cam, a=pts[0], b=pts[1], atributos=dict(atr)))
                else:
                    add(Polilinha(camada=cam, vertices=pts, fechada=False, atributos=dict(atr)))

            for it in d.get("items") or []:
                op = it[0]
                if op == "l":
                    a, b = P(it[1].x, it[1].y), P(it[2].x, it[2].y)
                    if corrida and math.hypot(corrida[-1][0] - a[0], corrida[-1][1] - a[1]) > 1e-3:
                        fechar_corrida()
                    if not corrida:
                        corrida.append(a)
                    corrida.append(b)
                elif op == "c":
                    p0, p1, p2, p3 = (P(q.x, q.y) for q in it[1:5])
                    if corrida and math.hypot(corrida[-1][0] - p0[0], corrida[-1][1] - p0[1]) > 1e-3:
                        fechar_corrida()
                    if not corrida:
                        corrida.append(p0)
                    corrida.extend((round(x, 3), round(y, 3)) for x, y in _bezier(p0, p1, p2, p3))
                elif op == "re":
                    fechar_corrida()
                    r = it[1]
                    corrida = [P(r.x0, r.y0), P(r.x1, r.y0), P(r.x1, r.y1), P(r.x0, r.y1)]
                    fechar_corrida(True)
                elif op == "qu":
                    fechar_corrida()
                    q = it[1]
                    corrida = [P(q.ul.x, q.ul.y), P(q.ur.x, q.ur.y), P(q.lr.x, q.lr.y), P(q.ll.x, q.ll.y)]
                    fechar_corrida(True)
            fechar_corrida(bool(d.get("closePath")))

        # textos: uma entidade por trecho (span) com a direção da linha
        n_textos = 0
        for bloco in pg.get_text("dict").get("blocks", []):
            for linha in bloco.get("lines", []):
                cx, sy = linha.get("dir", (1.0, 0.0))
                ang = math.degrees(math.atan2(-sy, cx)) % 360.0
                for sp in linha.get("spans", []):
                    txt = (sp.get("text") or "").strip()
                    if not txt:
                        continue
                    ox, oy_ = sp.get("origin", (sp["bbox"][0], sp["bbox"][3]))
                    alt = float(sp.get("size") or 8.0) * PT_MM * 0.72
                    cam = camada("PDF TEXTO", _hex(_cor_int(sp.get("color"))))
                    add(Texto(camada=cam, posicao=P(ox, oy_), texto=txt, altura=round(max(alt * k_txt, 0.2), 3),
                              angulo=round(ang, 2), alinhamento="esquerda", vertical="base",
                              atributos={"origem": "pdf"}))
                    n_textos += 1
        n_obj = len(ids) - n_antes
        if n_obj == 0 and pg.get_images():
            avisos.append("página %d é imagem (digitalizada): não há linhas nem textos para ler — peça o PDF "
                          "exportado do CAD ou o DXF." % (num + 1))
        elif tracos_miudos > 400 and n_textos < tracos_miudos / 50:
            avisos.append("página %d: os textos parecem ter vindo desenhados como traços (fonte SHX do CAD) — "
                          "os perfis escritos não serão lidos. Exporte o PDF com fontes TrueType ou mande o DXF."
                          % (num + 1))
        pags.append({"pagina": num + 1, "x0": round(x0, 3), "largura_mm": round(W * PT_MM, 1),
                     "altura_mm": round(H * PT_MM, 1), "objetos": n_obj, "textos": n_textos})
        x0 += W * PT_MM + ESPACO_PAGINAS
    resumo = {"entidades": len(ids), "ids": ids, "por_tipo": dict(contagem), "camadas_novas": sorted(camadas_novas),
              "paginas": pags, "avisos": avisos, "unidade": "mm de papel"}
    return des, resumo


def _cor_int(c) -> Optional[Tuple[float, float, float]]:
    if c is None:
        return None
    if isinstance(c, (tuple, list)):
        return tuple(c)[:3]
    c = int(c)
    return ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0
