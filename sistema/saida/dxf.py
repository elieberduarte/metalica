# -*- coding: utf-8 -*-
"""Escritor de arquivos DXF (formato R12 ASCII) para os desenhos de detalhamento.

R12 é o dialeto mais compatível: abre em AutoCAD, BricsCAD, QCAD, LibreCAD, DraftSight
e nos visualizadores online. Não usa biblioteca externa — o formato é uma sequência de
pares (código de grupo, valor), e as entidades que interessam ao detalhamento de
estruturas metálicas são poucas.

Unidade do desenho: milímetro. Escala 1:1 no espaço do modelo; a escala de impressão é
aplicada na prancha.
"""
import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# --- camadas padrão do detalhamento (nome, cor ACI, tipo de linha) ---
CAMADAS = [
    ("0",            7, "CONTINUOUS"),
    ("ACO",          7, "CONTINUOUS"),   # contorno das peças
    ("ACO-FINO",     8, "CONTINUOUS"),   # arestas secundárias
    ("EIXO",         1, "CENTER"),       # eixos e linhas de centro
    ("OCULTA",       8, "HIDDEN"),       # arestas não visíveis
    ("COTA",         3, "CONTINUOUS"),   # cotas e linhas de chamada
    ("TEXTO",        7, "CONTINUOUS"),
    ("FURO",         5, "CONTINUOUS"),
    ("SOLDA",        2, "CONTINUOUS"),
    ("PARAFUSO",     5, "CONTINUOUS"),
    ("CONCRETO",     9, "CONTINUOUS"),
    ("HACHURA",      8, "CONTINUOUS"),
    ("CARIMBO",      7, "CONTINUOUS"),
    ("AUXILIAR",     8, "DASHED"),
]

TIPOS_LINHA = [
    ("CONTINUOUS", "Solida", []),
    ("CENTER", "Linha de centro ____ _ ____ _ ____", [31.75, 0.5, -6.35, 3.175, -6.35]),
    ("HIDDEN", "Tracejada __ __ __ __ __ __", [9.525, 0.5, -6.35, 3.175]),
    ("DASHED", "Tracejada longa ___ ___ ___", [12.7, 0.5, -6.35, 6.35]),
]


def _par(codigo, valor):
    return f"{codigo}\n{valor}\n"


class Desenho:
    """Acumula entidades e grava o arquivo DXF."""

    def __init__(self, nome="desenho", unidade_mm=True):
        self.nome = nome
        self.entidades: List[str] = []
        self.extremos = [1e20, 1e20, -1e20, -1e20]   # xmin, ymin, xmax, ymax
        self.unidade_mm = unidade_mm

    # ---------- controle ----------
    def _limites(self, *pontos):
        for x, y in pontos:
            self.extremos[0] = min(self.extremos[0], x)
            self.extremos[1] = min(self.extremos[1], y)
            self.extremos[2] = max(self.extremos[2], x)
            self.extremos[3] = max(self.extremos[3], y)

    @property
    def largura(self):
        return max(0.0, self.extremos[2] - self.extremos[0])

    @property
    def altura(self):
        return max(0.0, self.extremos[3] - self.extremos[1])

    # ---------- entidades ----------
    def linha(self, x1, y1, x2, y2, camada="ACO"):
        self._limites((x1, y1), (x2, y2))
        self.entidades.append(
            _par(0, "LINE") + _par(8, camada) +
            _par(10, f"{x1:.4f}") + _par(20, f"{y1:.4f}") + _par(30, "0.0") +
            _par(11, f"{x2:.4f}") + _par(21, f"{y2:.4f}") + _par(31, "0.0"))
        return self

    def polilinha(self, pontos, fechada=False, camada="ACO"):
        if len(pontos) < 2:
            return self
        self._limites(*pontos)
        e = (_par(0, "POLYLINE") + _par(8, camada) + _par(66, 1) +
             _par(10, "0.0") + _par(20, "0.0") + _par(30, "0.0") +
             _par(70, 1 if fechada else 0))
        for x, y in pontos:
            e += (_par(0, "VERTEX") + _par(8, camada) +
                  _par(10, f"{x:.4f}") + _par(20, f"{y:.4f}") + _par(30, "0.0"))
        e += _par(0, "SEQEND") + _par(8, camada)
        self.entidades.append(e)
        return self

    def retangulo(self, x, y, larg, alt, camada="ACO"):
        return self.polilinha([(x, y), (x + larg, y), (x + larg, y + alt), (x, y + alt)],
                              fechada=True, camada=camada)

    def circulo(self, xc, yc, raio, camada="FURO"):
        self._limites((xc - raio, yc - raio), (xc + raio, yc + raio))
        self.entidades.append(
            _par(0, "CIRCLE") + _par(8, camada) +
            _par(10, f"{xc:.4f}") + _par(20, f"{yc:.4f}") + _par(30, "0.0") +
            _par(40, f"{raio:.4f}"))
        return self

    def arco(self, xc, yc, raio, ang_ini, ang_fim, camada="ACO"):
        self._limites((xc - raio, yc - raio), (xc + raio, yc + raio))
        self.entidades.append(
            _par(0, "ARC") + _par(8, camada) +
            _par(10, f"{xc:.4f}") + _par(20, f"{yc:.4f}") + _par(30, "0.0") +
            _par(40, f"{raio:.4f}") + _par(50, f"{ang_ini:.4f}") + _par(51, f"{ang_fim:.4f}"))
        return self

    def texto(self, x, y, texto, altura=2.5, camada="TEXTO", angulo=0.0,
              alinhamento="esquerda", vertical="base"):
        """alinhamento: esquerda, centro, direita; vertical: base, meio, topo."""
        hj = {"esquerda": 0, "centro": 1, "direita": 2}[alinhamento]
        vj = {"base": 0, "meio": 2, "topo": 3}[vertical]
        self._limites((x, y), (x + len(str(texto)) * altura * 0.7, y + altura))
        e = (_par(0, "TEXT") + _par(8, camada) +
             _par(10, f"{x:.4f}") + _par(20, f"{y:.4f}") + _par(30, "0.0") +
             _par(40, f"{altura:.4f}") + _par(1, _ascii(str(texto))) +
             _par(50, f"{angulo:.4f}"))
        if hj or vj:
            e += _par(72, hj) + _par(73, vj)
            e += (_par(11, f"{x:.4f}") + _par(21, f"{y:.4f}") + _par(31, "0.0"))
        self.entidades.append(e)
        return self

    def solido(self, p1, p2, p3, p4=None, camada="HACHURA"):
        """Triângulo ou quadrilátero preenchido (usado em setas e filetes de solda)."""
        p4 = p4 or p3
        self._limites(p1, p2, p3, p4)
        self.entidades.append(
            _par(0, "SOLID") + _par(8, camada) +
            _par(10, f"{p1[0]:.4f}") + _par(20, f"{p1[1]:.4f}") + _par(30, "0.0") +
            _par(11, f"{p2[0]:.4f}") + _par(21, f"{p2[1]:.4f}") + _par(31, "0.0") +
            _par(12, f"{p3[0]:.4f}") + _par(22, f"{p3[1]:.4f}") + _par(32, "0.0") +
            _par(13, f"{p4[0]:.4f}") + _par(23, f"{p4[1]:.4f}") + _par(33, "0.0"))
        return self

    # ---------- recursos de desenho técnico ----------
    def seta(self, x, y, angulo_graus, tamanho=3.0, camada="COTA"):
        """Ponta de seta cheia apontando para (x, y)."""
        a = math.radians(angulo_graus)
        bx, by = x - tamanho * math.cos(a), y - tamanho * math.sin(a)
        larg = tamanho * 0.30
        px, py = -math.sin(a) * larg, math.cos(a) * larg
        return self.solido((x, y), (bx + px, by + py), (bx - px, by - py), camada=camada)

    def cota_linear(self, x1, y1, x2, y2, deslocamento=12.0, texto=None,
                    altura=2.5, camada="COTA", extensao=2.0):
        """Cota entre dois pontos, deslocada perpendicularmente. Desenhada com entidades
        simples (linhas, setas e texto), o que garante aparência idêntica em qualquer CAD."""
        dx, dy = x2 - x1, y2 - y1
        comp = math.hypot(dx, dy)
        if comp < 1e-9:
            return self
        ux, uy = dx / comp, dy / comp
        nx, ny = -uy, ux                      # normal unitária à esquerda do sentido 1->2
        s = deslocamento                      # com sinal: para que lado a cota sai
        sg = 1.0 if s >= 0 else -1.0
        a1 = (x1 + nx * s, y1 + ny * s)
        a2 = (x2 + nx * s, y2 + ny * s)
        # linhas de chamada: da peça até um pouco além da linha de cota
        folga = 1.5
        self.linha(x1 + nx * sg * folga, y1 + ny * sg * folga,
                   a1[0] + nx * sg * extensao, a1[1] + ny * sg * extensao, camada)
        self.linha(x2 + nx * sg * folga, y2 + ny * sg * folga,
                   a2[0] + nx * sg * extensao, a2[1] + ny * sg * extensao, camada)
        self.linha(a1[0], a1[1], a2[0], a2[1], camada)
        ang = math.degrees(math.atan2(uy, ux))
        tam_seta = min(3.5, max(1.5, comp / 5))
        self.seta(a1[0], a1[1], ang + 180, tam_seta, camada)
        self.seta(a2[0], a2[1], ang, tam_seta, camada)
        txt = texto if texto is not None else f"{comp:.0f}"
        mx, my = (a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2
        # texto acima da linha de cota, acompanhando o ângulo e sempre legível
        ang_txt = ang if -90 < ang <= 90 else ang + 180
        lado = 1.0 if -90 < ang <= 90 else -1.0
        off = altura * 0.6 * lado
        self.texto(mx + nx * off, my + ny * off, txt, altura, "COTA",
                   angulo=ang_txt, alinhamento="centro")
        return self

    def cota_h(self, x1, x2, y, deslocamento=12.0, texto=None, altura=2.5):
        return self.cota_linear(x1, y, x2, y, deslocamento, texto, altura)

    def cota_v(self, y1, y2, x, deslocamento=12.0, texto=None, altura=2.5):
        """Deslocamento positivo joga a cota para a direita da peça."""
        return self.cota_linear(x, y1, x, y2, -deslocamento, texto, altura)

    def chamada(self, x_alvo, y_alvo, x_texto, y_texto, texto, altura=2.5, camada="TEXTO"):
        """Linha de chamada com seta na peça e texto na ponta."""
        self.linha(x_alvo, y_alvo, x_texto, y_texto, camada)
        ang = math.degrees(math.atan2(y_alvo - y_texto, x_alvo - x_texto))
        self.seta(x_alvo, y_alvo, ang, 2.5, camada)
        direita = x_texto >= x_alvo
        traco = 8.0 if direita else -8.0
        self.linha(x_texto, y_texto, x_texto + traco, y_texto, camada)
        self.texto(x_texto + traco + (1.5 if direita else -1.5), y_texto + 0.8, texto,
                   altura, camada, alinhamento="esquerda" if direita else "direita")
        return self

    def hachura(self, pontos, espacamento=3.0, angulo=45.0, camada="HACHURA", furos=()):
        """Hachura de corte por linhas paralelas dentro de um polígono convexo ou côncavo
        simples (varredura por linhas com interseções ordenadas); `furos`: contornos
        internos que ficam vazios (par-ímpar)."""
        if len(pontos) < 3:
            return self
        a = math.radians(angulo)
        ca, sa = math.cos(a), math.sin(a)
        proj = [(-p[0] * sa + p[1] * ca) for p in pontos]     # coordenada perpendicular
        t_min, t_max = min(proj), max(proj)
        n = int((t_max - t_min) / espacamento) + 1
        arestas = [(c[j], c[(j + 1) % len(c)]) for c in [pontos] + [f for f in furos if len(f) >= 3] for j in range(len(c))]
        for i in range(1, n):
            t = t_min + i * espacamento
            cortes = []
            for p1, p2 in arestas:
                t1 = -p1[0] * sa + p1[1] * ca
                t2 = -p2[0] * sa + p2[1] * ca
                if (t1 - t) * (t2 - t) < 0:
                    f = (t - t1) / (t2 - t1)
                    cortes.append((p1[0] + f * (p2[0] - p1[0]), p1[1] + f * (p2[1] - p1[1])))
            if len(cortes) < 2:
                continue
            cortes.sort(key=lambda p: p[0] * ca + p[1] * sa)
            for k in range(0, len(cortes) - 1, 2):
                (x1, y1), (x2, y2) = cortes[k], cortes[k + 1]
                self.linha(x1, y1, x2, y2, camada)
        return self

    def furo(self, x, y, diametro, camada="FURO", com_centro=True):
        r = diametro / 2
        self.circulo(x, y, r, camada)
        if com_centro:
            c = r + 2.0
            self.linha(x - c, y, x + c, y, "EIXO")
            self.linha(x, y - c, x, y + c, "EIXO")
        return self

    def parafuso(self, x, y, diametro, camada="PARAFUSO"):
        """Parafuso em vista: círculo do furo mais as linhas cruzadas da cabeça."""
        r = diametro / 2
        self.circulo(x, y, r, camada)
        d = r * 0.95
        self.linha(x - d, y - d, x + d, y + d, camada)
        self.linha(x - d, y + d, x + d, y - d, camada)
        return self

    def filete_solda(self, x, y, perna, angulo_graus=0.0, lado=1, camada="SOLDA"):
        """Triângulo do filete de solda, na aresta indicada."""
        a = math.radians(angulo_graus)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy * lado, ux * lado
        p1 = (x, y)
        p2 = (x + ux * perna, y + uy * perna)
        p3 = (x + nx * perna, y + ny * perna)
        return self.solido(p1, p2, p3, camada=camada)

    def simbolo_solda(self, x, y, perna, texto_extra="", em_volta=False, campo=False,
                      camada="SOLDA", comprimento=25.0):
        """Símbolo de solda conforme AWS A2.4: linha de referência, triângulo do filete,
        perna à esquerda e anotações."""
        self.linha(x, y, x + comprimento, y, camada)
        tri = 3.5
        bx = x + comprimento * 0.45
        self.solido((bx, y), (bx + tri, y), (bx, y + tri), camada=camada)
        self.texto(bx - 1.5, y + 0.8, f"{perna:.0f}", 2.5, camada, alinhamento="direita")
        if texto_extra:
            self.texto(x + comprimento + 1.5, y + 0.8, texto_extra, 2.5, camada)
        if em_volta:
            self.circulo(x, y, 1.8, camada)
        if campo:
            self.linha(x, y, x, y + 5.0, camada)
            self.solido((x, y + 5.0), (x + 3.0, y + 5.0), (x, y + 3.5), camada=camada)
        return self

    # ---------- composição ----------
    def inserir(self, outro: "Desenho", dx=0.0, dy=0.0, escala=1.0):
        """Copia as entidades de outro desenho, transladadas (composição de pranchas)."""
        if escala == 1.0 and dx == 0.0 and dy == 0.0:
            self.entidades.extend(outro.entidades)
        else:
            for e in outro.entidades:
                self.entidades.append(_transformar(e, dx, dy, escala))
        e0 = outro.extremos
        if e0[0] < 1e19:
            self._limites((e0[0] * escala + dx, e0[1] * escala + dy),
                          (e0[2] * escala + dx, e0[3] * escala + dy))
        return self

    # ---------- gravação ----------
    def dxf(self) -> str:
        xmin, ymin, xmax, ymax = self.extremos
        if xmin > 1e19:
            xmin = ymin = 0.0
            xmax = ymax = 100.0
        m = 20.0
        s = ""
        # HEADER
        s += _par(0, "SECTION") + _par(2, "HEADER")
        s += _par(9, "$ACADVER") + _par(1, "AC1009")
        s += _par(9, "$INSUNITS") + _par(70, 4)          # 4 = milímetros
        s += _par(9, "$EXTMIN") + _par(10, f"{xmin-m:.4f}") + _par(20, f"{ymin-m:.4f}") + _par(30, "0.0")
        s += _par(9, "$EXTMAX") + _par(10, f"{xmax+m:.4f}") + _par(20, f"{ymax+m:.4f}") + _par(30, "0.0")
        s += _par(9, "$LTSCALE") + _par(40, "1.0")
        s += _par(9, "$TEXTSTYLE") + _par(7, "STANDARD")
        s += _par(0, "ENDSEC")
        # TABLES
        s += _par(0, "SECTION") + _par(2, "TABLES")
        s += _par(0, "TABLE") + _par(2, "LTYPE") + _par(70, len(TIPOS_LINHA))
        for nome, descr, padrao in TIPOS_LINHA:
            s += (_par(0, "LTYPE") + _par(2, nome) + _par(70, 0) + _par(3, descr) +
                  _par(72, 65) + _par(73, len(padrao[1:]) if padrao else 0) +
                  _par(40, f"{padrao[0]:.4f}" if padrao else "0.0"))
            for v in padrao[1:]:
                s += _par(49, f"{v:.4f}")
        s += _par(0, "ENDTAB")
        s += _par(0, "TABLE") + _par(2, "LAYER") + _par(70, len(CAMADAS))
        for nome, cor, tipo in CAMADAS:
            s += (_par(0, "LAYER") + _par(2, nome) + _par(70, 0) +
                  _par(62, cor) + _par(6, tipo))
        s += _par(0, "ENDTAB")
        s += _par(0, "TABLE") + _par(2, "STYLE") + _par(70, 1)
        s += (_par(0, "STYLE") + _par(2, "STANDARD") + _par(70, 0) + _par(40, "0.0") +
              _par(41, "0.85") + _par(50, "0.0") + _par(71, 0) + _par(42, "2.5") +
              _par(3, "txt") + _par(4, ""))
        s += _par(0, "ENDTAB")
        s += _par(0, "ENDSEC")
        # ENTITIES
        s += _par(0, "SECTION") + _par(2, "ENTITIES")
        s += "".join(self.entidades)
        s += _par(0, "ENDSEC") + _par(0, "EOF")
        return s

    def gravar(self, caminho) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        with open(caminho, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write(self.dxf())
        return caminho


def _ascii(texto: str) -> str:
    """DXF R12 não lida bem com acentuação: converte para ASCII preservando a leitura."""
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇºª°",
                           "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUCoa ")
    t = texto.translate(tabela)
    t = (t.replace("Ø", "%%c").replace("ø", "%%c").replace("±", "%%p")
          .replace("×", "x").replace("·", ".").replace("–", "-").replace("—", "-")
          .replace("≤", "<=").replace("≥", ">=").replace("²", "2").replace("³", "3"))
    return "".join(c if ord(c) < 128 or c == "%" else "?" for c in t)


def _transformar(entidade: str, dx: float, dy: float, escala: float) -> str:
    """Translada e escala uma entidade já serializada (usado na montagem de pranchas)."""
    linhas = entidade.split("\n")
    saida = []
    i = 0
    while i < len(linhas) - 1:
        cod = linhas[i].strip()
        val = linhas[i + 1]
        if cod.isdigit():
            c = int(cod)
            try:
                if c in (10, 11, 12, 13):                    # coordenadas x
                    val = f"{float(val) * escala + dx:.4f}"
                elif c in (20, 21, 22, 23):                  # coordenadas y
                    val = f"{float(val) * escala + dy:.4f}"
                elif c in (40, 41, 42):                      # raios e alturas
                    val = f"{float(val) * escala:.4f}"
            except ValueError:
                pass
        saida.append(cod if cod else linhas[i])
        saida.append(val)
        i += 2
    return "\n".join(saida) + "\n"
