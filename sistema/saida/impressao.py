# -*- coding: utf-8 -*-
"""Impressão das pranchas direto na impressora do Windows (pedido do usuário, 21/10: "criar a ferramenta de
impressão das pranchas diretamente do sistema").

O caminho: o PDF das pranchas (o mesmo do "PDF de todas as pranchas", `nucleo2d.pranchas.pdf_dos_desenhos`) é
rasterizado pelo PyMuPDF em faixas, na resolução da impressora, e cada faixa vai para o GDI do Windows
(`StretchDIBits`) — sem programa de PDF instalado e sem o pywin32: só ctypes. É o que o leitor de PDF faz ao
imprimir; a faixa (e não a folha inteira) segura a memória: uma A1 a 600 dpi seriam 800 MB de uma vez.

O papel: cada folha vai no papel do tamanho dela, quando a impressora o tem (a A1 na plotter), em tamanho real; ou
no papel escolhido, reduzida (ou ampliada) para caber — a A1 numa A3 sai a 1:2 da escala escrita no carimbo.
A cor: colorida; preto (a linha colorida sai preta e o cinza continua cinza: o "monochrome" dos plotters); ou
tons de cinza.

As contas (o papel de cada folha, onde ela cai no papel, a cor) são funções puras, testadas sem impressora
(testes/test_impressao.py); a impressão de verdade é testada pela "Microsoft Print to PDF" gravando num arquivo.
"""
import ctypes
import math
import re
import sys
from ctypes import wintypes
from typing import Callable, Optional, Sequence, Tuple

#: Resolução máxima do que é desenhado; acima disso a faixa é ampliada um número inteiro de vezes pelo GDI (a
#: plotter de 1200 dpi recebe a imagem de 300 × 4) — linha de prancha a 300 dpi já é a da caneta de 0,1 mm.
DPI_MAXIMO = 300
#: Linhas da imagem por faixa mandada à impressora.
LINHAS_POR_FAIXA = 768
#: Tolerância (mm) para dizer que o papel da impressora é do tamanho da folha (o "A1" do driver tem 594 × 841).
FOLGA_PAPEL = 3.0

AJUSTES = ("real", "ajustar")
CORES = ("cor", "preto", "cinza")


class ErroDeImpressao(Exception):
    pass


# ============================================================ contas (sem impressora)

def papel_da_folha(folha: Tuple[float, float], papeis: Sequence[dict], papel: Optional[int] = None,
                   ajuste: str = "real") -> Tuple[Optional[dict], str, str]:
    """O papel da impressora para a folha (largura, altura em mm): (papel, ajuste, aviso).

    `papel` escolhido na tela: ele, com o ajuste pedido. Automático: o papel do tamanho da folha, em tamanho real;
    senão o menor em que ela cabe inteira (em tamanho real, com sobra); senão o maior, com a folha reduzida."""
    a, b = sorted(folha)
    if papel is not None:
        p = next((p for p in papeis if p["id"] == papel), None)
        if p is None:
            raise ErroDeImpressao("a impressora não tem o papel escolhido (%s)." % papel)
        return p, ajuste, ""
    def dims(p):
        return sorted((p["largura"], p["altura"]))
    iguais = [p for p in papeis if abs(dims(p)[0] - a) <= FOLGA_PAPEL and abs(dims(p)[1] - b) <= FOLGA_PAPEL]
    if iguais:
        return min(iguais, key=lambda p: abs(dims(p)[0] - a) + abs(dims(p)[1] - b)), ajuste, ""
    cabem = [p for p in papeis if dims(p)[0] >= a - FOLGA_PAPEL and dims(p)[1] >= b - FOLGA_PAPEL]
    if cabem:
        p = min(cabem, key=lambda p: dims(p)[0] * dims(p)[1])
        return p, ajuste, "a impressora não tem o papel do tamanho da folha: vai no %s" % p["nome"]
    if not papeis:
        raise ErroDeImpressao("a impressora não informou nenhum papel.")
    p = max(papeis, key=lambda p: dims(p)[0] * dims(p)[1])
    return p, "ajustar", "a folha não cabe em nenhum papel da impressora: vai reduzida no %s" % p["nome"]


def colocar(folha: Tuple[float, float], area: dict, ajuste: str) -> dict:
    """Onde a folha (largura, altura em mm) cai no papel. `area`: a medida da impressora em pixels — dpi_x, dpi_y,
    papel (largura, altura do papel inteiro), margem (x, y do começo da área que imprime) e util (largura, altura
    da área que imprime). Devolve girar (90°: a folha deitada no papel em pé), escala (1 = tamanho real), o canto
    (x, y) e o tamanho (largura, altura) na impressora, em pixels a partir do começo da área que imprime, e o que
    fica fora da área (mm, para o aviso)."""
    fw, fh = folha
    dx, dy = area["dpi_x"] / 25.4, area["dpi_y"] / 25.4            # pixels por mm
    uw, uh = area["util"][0] / dx, area["util"][1] / dy             # a área que imprime, em mm
    girar = (fw > fh) != (uw > uh) and abs(fw - fh) > 1e-6 and abs(uw - uh) > 1e-6
    pw, ph = (fh, fw) if girar else (fw, fh)
    escala = min(uw / pw, uh / ph) if ajuste == "ajustar" else 1.0
    largura, altura = pw * escala * dx, ph * escala * dy
    if ajuste == "ajustar":
        x, y = (area["util"][0] - largura) / 2.0, (area["util"][1] - altura) / 2.0
    else:                                                           # no meio do papel inteiro, como a folha cortada
        x = (area["papel"][0] - largura) / 2.0 - area["margem"][0]
        y = (area["papel"][1] - altura) / 2.0 - area["margem"][1]
    fora = max(0.0, -x / dx, -y / dy, (x + largura - area["util"][0]) / dx, (y + altura - area["util"][1]) / dy)
    return {"girar": girar, "escala": escala, "x": int(round(x)), "y": int(round(y)),
            "largura": int(round(largura)), "altura": int(round(altura)), "fora_mm": round(fora, 1)}


def tons(rgb, cor: str):
    """A faixa (numpy, altura × largura × 3, RGB) na cor pedida, ainda em RGB. Preto: cada pixel vale o seu canal
    mais claro — a linha vermelha, azul ou amarela sai preta, a borda suavizada dela sai cinza, e o cinza (hachura,
    camada OCULTA) continua o mesmo cinza. Cinza: a luminância."""
    import numpy as np
    if cor == "preto":
        g = rgb.min(axis=2)
    elif cor == "cinza":
        g = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114 + 0.5).astype(np.uint8)
    else:
        return rgb
    return np.repeat(g[..., None], 3, axis=2)


def fator_de_ampliacao(dpi: float) -> int:
    """Quantas vezes o GDI amplia o desenhado para chegar ao dpi da impressora (inteiro: sem costura entre faixas)."""
    return max(1, int(math.ceil(dpi / float(DPI_MAXIMO) - 1e-9)))


# ============================================================ Windows

if sys.platform == "win32":
    _winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    _gdi = ctypes.WinDLL("gdi32", use_last_error=True)

    class _PRINTER_INFO_2(ctypes.Structure):
        _fields_ = [("pServerName", wintypes.LPWSTR), ("pPrinterName", wintypes.LPWSTR),
                    ("pShareName", wintypes.LPWSTR), ("pPortName", wintypes.LPWSTR),
                    ("pDriverName", wintypes.LPWSTR), ("pComment", wintypes.LPWSTR),
                    ("pLocation", wintypes.LPWSTR), ("pDevMode", ctypes.c_void_p),
                    ("pSepFile", wintypes.LPWSTR), ("pPrintProcessor", wintypes.LPWSTR),
                    ("pDatatype", wintypes.LPWSTR), ("pParameters", wintypes.LPWSTR),
                    ("pSecurityDescriptor", ctypes.c_void_p), ("Attributes", wintypes.DWORD),
                    ("Priority", wintypes.DWORD), ("DefaultPriority", wintypes.DWORD),
                    ("StartTime", wintypes.DWORD), ("UntilTime", wintypes.DWORD),
                    ("Status", wintypes.DWORD), ("cJobs", wintypes.DWORD), ("AveragePPM", wintypes.DWORD)]

    class _DOCINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR), ("lpszOutput", wintypes.LPCWSTR),
                    ("lpszDatatype", wintypes.LPCWSTR), ("fwType", wintypes.DWORD)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    _winspool.EnumPrintersW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
                                        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    _winspool.GetDefaultPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    _winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    _winspool.DocumentPropertiesW.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.LPWSTR, ctypes.c_void_p,
                                              ctypes.c_void_p, wintypes.DWORD]
    _winspool.DocumentPropertiesW.restype = wintypes.LONG
    _winspool.DeviceCapabilitiesW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.WORD, ctypes.c_void_p,
                                              ctypes.c_void_p]
    _winspool.DeviceCapabilitiesW.restype = ctypes.c_int
    _gdi.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
    _gdi.CreateDCW.restype = wintypes.HDC
    _gdi.ResetDCW.argtypes = [wintypes.HDC, ctypes.c_void_p]
    _gdi.ResetDCW.restype = wintypes.HDC
    _gdi.DeleteDC.argtypes = [wintypes.HDC]
    _gdi.StartDocW.argtypes = [wintypes.HDC, ctypes.POINTER(_DOCINFO)]
    _gdi.EndDoc.argtypes = [wintypes.HDC]
    _gdi.AbortDoc.argtypes = [wintypes.HDC]
    _gdi.StartPage.argtypes = [wintypes.HDC]
    _gdi.EndPage.argtypes = [wintypes.HDC]
    _gdi.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    _gdi.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
    _gdi.SetBrushOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    _gdi.StretchDIBits.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                   ctypes.c_void_p, wintypes.UINT, wintypes.DWORD]

# DEVMODEW: os campos que a impressão mexe (deslocamento em bytes)
_DM_FIELDS, _DM_ORIENTATION, _DM_PAPERSIZE, _DM_COPIES, _DM_COLOR = 72, 76, 78, 86, 92
_F_ORIENTATION, _F_PAPERSIZE, _F_COPIES, _F_COLOR = 0x1, 0x2, 0x100, 0x800
_DM_OUT_BUFFER, _DM_IN_BUFFER = 2, 8
_DC_PAPERS, _DC_PAPERSIZE, _DC_PAPERNAMES, _DC_COLORDEVICE = 2, 3, 16, 32
_HORZRES, _VERTRES, _LOGPIXELSX, _LOGPIXELSY = 8, 10, 88, 90
_PHYSICALWIDTH, _PHYSICALHEIGHT, _PHYSICALOFFSETX, _PHYSICALOFFSETY = 110, 111, 112, 113


def _exigir_windows():
    if sys.platform != "win32":
        raise ErroDeImpressao("a impressão direta é só no Windows: use o PDF das pranchas.")


def impressoras() -> dict:
    """As impressoras do Windows: {impressoras: [{nome, porta, driver, padrao}], padrao}."""
    _exigir_windows()
    flags = 0x2 | 0x4                                     # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    precisa, quantas = wintypes.DWORD(0), wintypes.DWORD(0)
    _winspool.EnumPrintersW(flags, None, 2, None, 0, ctypes.byref(precisa), ctypes.byref(quantas))
    lista = []
    if precisa.value:
        buf = ctypes.create_string_buffer(precisa.value)
        if _winspool.EnumPrintersW(flags, None, 2, buf, precisa, ctypes.byref(precisa), ctypes.byref(quantas)):
            infos = ctypes.cast(buf, ctypes.POINTER(_PRINTER_INFO_2))
            for i in range(quantas.value):
                p = infos[i]
                lista.append({"nome": p.pPrinterName or "", "porta": p.pPortName or "", "driver": p.pDriverName or ""})
    n = wintypes.DWORD(0)
    _winspool.GetDefaultPrinterW(None, ctypes.byref(n))
    padrao = ""
    if n.value:
        b = ctypes.create_unicode_buffer(n.value)
        if _winspool.GetDefaultPrinterW(b, ctypes.byref(n)):
            padrao = b.value
    for p in lista:
        p["padrao"] = p["nome"] == padrao
    return {"impressoras": lista, "padrao": padrao}


def _porta(nome: str) -> str:
    p = next((p for p in impressoras()["impressoras"] if p["nome"] == nome), None)
    if p is None:
        raise ErroDeImpressao("a impressora \"%s\" não está instalada neste computador." % nome)
    return p["porta"]


def papeis(nome: str) -> dict:
    """Os papéis da impressora: {papeis: [{id, nome, largura, altura}] (mm, em pé), colorida}."""
    _exigir_windows()
    porta = _porta(nome)
    n = _winspool.DeviceCapabilitiesW(nome, porta, _DC_PAPERS, None, None)
    if n <= 0:
        return {"papeis": [], "colorida": False}
    ids = (wintypes.WORD * n)()
    _winspool.DeviceCapabilitiesW(nome, porta, _DC_PAPERS, ids, None)
    tamanhos = (wintypes.POINT * n)()
    _winspool.DeviceCapabilitiesW(nome, porta, _DC_PAPERSIZE, tamanhos, None)
    nomes = ctypes.create_unicode_buffer(64 * n)
    _winspool.DeviceCapabilitiesW(nome, porta, _DC_PAPERNAMES, nomes, None)
    lista = []
    for i in range(n):
        texto = ctypes.wstring_at(ctypes.addressof(nomes) + i * 64 * ctypes.sizeof(ctypes.c_wchar), 64).split("\0")[0]
        texto = re.sub(r"^ISO\s*(A\d)\b", r"\1", texto.strip())          # o "ISOA1" do driver IPP é a A1
        w, h = tamanhos[i].x / 10.0, tamanhos[i].y / 10.0
        if w > 0 and h > 0:
            lista.append({"id": int(ids[i]), "nome": texto.strip() or ("%g × %g mm" % (w, h)), "largura": w, "altura": h})
    colorida = _winspool.DeviceCapabilitiesW(nome, porta, _DC_COLORDEVICE, None, None) == 1
    return {"papeis": lista, "colorida": colorida}


def _devmode(nome: str, papel: int, deitado: bool, cor: str):
    """O DEVMODE da impressora (o padrão dela) com o papel, a orientação, a cor e 1 cópia (as cópias são nossas)."""
    h = wintypes.HANDLE()
    if not _winspool.OpenPrinterW(nome, ctypes.byref(h), None):
        raise ErroDeImpressao("não foi possível abrir a impressora \"%s\" (erro %d)." % (nome, ctypes.get_last_error()))
    try:
        tam = _winspool.DocumentPropertiesW(None, h, nome, None, None, 0)
        if tam <= 0:
            raise ErroDeImpressao("a impressora \"%s\" não deu as configurações dela." % nome)
        base = ctypes.create_string_buffer(tam)
        if _winspool.DocumentPropertiesW(None, h, nome, base, None, _DM_OUT_BUFFER) < 0:
            raise ErroDeImpressao("a impressora \"%s\" não deu as configurações dela." % nome)
        campos = ctypes.c_uint32.from_buffer(base, _DM_FIELDS)
        campos.value |= _F_ORIENTATION | _F_PAPERSIZE | _F_COPIES | _F_COLOR
        ctypes.c_short.from_buffer(base, _DM_ORIENTATION).value = 2 if deitado else 1
        ctypes.c_short.from_buffer(base, _DM_PAPERSIZE).value = int(papel)
        ctypes.c_short.from_buffer(base, _DM_COPIES).value = 1
        ctypes.c_short.from_buffer(base, _DM_COLOR).value = 2 if cor == "cor" else 1
        final = ctypes.create_string_buffer(tam)
        if _winspool.DocumentPropertiesW(None, h, nome, final, base, _DM_IN_BUFFER | _DM_OUT_BUFFER) < 0:
            return base
        return final
    finally:
        _winspool.ClosePrinter(h)


def _area(hdc) -> dict:
    c = lambda i: _gdi.GetDeviceCaps(hdc, i)                       # noqa: E731
    return {"dpi_x": c(_LOGPIXELSX), "dpi_y": c(_LOGPIXELSY), "papel": (c(_PHYSICALWIDTH), c(_PHYSICALHEIGHT)),
            "margem": (c(_PHYSICALOFFSETX), c(_PHYSICALOFFSETY)), "util": (c(_HORZRES), c(_VERTRES))}


def _desenhar_pagina(hdc, pagina, area: dict, ajuste: str, cor: str) -> dict:
    """A página do PDF (pymupdf) na página aberta da impressora, em faixas."""
    import numpy as np
    import pymupdf
    fw, fh = pagina.rect.width / 72.0 * 25.4, pagina.rect.height / 72.0 * 25.4
    lugar = colocar((fw, fh), area, ajuste)
    nx, ny = fator_de_ampliacao(area["dpi_x"]), fator_de_ampliacao(area["dpi_y"])
    # o que é desenhado: a folha em pixels de (dpi / n), girada se for o caso; o GDI amplia n vezes
    w_px, h_px = max(1, lugar["largura"] // nx), max(1, lugar["altura"] // ny)
    giro = pymupdf.Matrix(90) if lugar["girar"] else pymupdf.Matrix(1, 1)
    t0 = pagina.rect * giro
    m = giro * pymupdf.Matrix(w_px / t0.width, h_px / t0.height)
    t = pagina.rect * m
    ox, oy = int(math.floor(t.x0 + 1e-6)), int(math.floor(t.y0 + 1e-6))
    inversa = ~m
    lista = pagina.get_displaylist()
    _gdi.SetStretchBltMode(hdc, 4)                                  # HALFTONE: a redução sem perder a linha fina
    _gdi.SetBrushOrgEx(hdc, 0, 0, None)
    cab = _BITMAPINFOHEADER()
    cab.biSize, cab.biPlanes, cab.biBitCount, cab.biCompression = ctypes.sizeof(_BITMAPINFOHEADER), 1, 24, 0
    for r0 in range(0, h_px, LINHAS_POR_FAIXA):
        r1 = min(h_px, r0 + LINHAS_POR_FAIXA)
        faixa = pymupdf.Rect(ox - 1, oy + r0 - 1, ox + w_px + 1, oy + r1 + 1) * inversa
        pix = lista.get_pixmap(matrix=m, colorspace=pymupdf.csRGB, alpha=False, clip=faixa)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
        img = img.reshape(pix.height, pix.width, 3)
        # a faixa exata (o recorte do PyMuPDF arredonda para fora): o que faltar fica branco
        saida = np.full((r1 - r0, w_px, 3), 255, dtype=np.uint8)
        ys, xs = oy + r0 - pix.y, ox - pix.x
        a0, b0 = max(0, -ys), max(0, -xs)
        a1, b1 = min(r1 - r0, pix.height - ys), min(w_px, pix.width - xs)
        if a1 > a0 and b1 > b0:
            saida[a0:a1, b0:b1] = img[ys + a0:ys + a1, xs + b0:xs + b1]
        saida = tons(saida, cor)[..., ::-1]                         # BGR, como o DIB quer
        passo = (w_px * 3 + 3) & ~3
        linhas = np.zeros((r1 - r0, passo), dtype=np.uint8)
        linhas[:, :w_px * 3] = saida.reshape(r1 - r0, w_px * 3)
        dados = np.ascontiguousarray(linhas)
        cab.biWidth, cab.biHeight, cab.biSizeImage = w_px, -(r1 - r0), dados.nbytes   # altura negativa: de cima
        feito = _gdi.StretchDIBits(hdc, lugar["x"], lugar["y"] + r0 * ny, w_px * nx, (r1 - r0) * ny,
                                   0, 0, w_px, r1 - r0, dados.ctypes.data, ctypes.byref(cab), 0, 0x00CC0020)
        if feito == 0:
            raise ErroDeImpressao("a impressora não aceitou o desenho da folha (erro %d)." % ctypes.get_last_error())
    return lugar


def imprimir_pdf(caminho_pdf: str, impressora: str, papel: Optional[int] = None, ajuste: str = "real",
                 cor: str = "preto", copias: int = 1, titulo: str = "Pranchas", arquivo: Optional[str] = None,
                 progresso: Optional[Callable[[str, float], None]] = None) -> dict:
    """Manda as páginas do PDF para a impressora, num trabalho só. `papel` None: o de cada folha (ver
    `papel_da_folha`). `arquivo`: imprime nele em vez de no papel (a "Microsoft Print to PDF", os testes).
    Devolve {paginas, folhas: [{pagina, papel, escala, girada, fora_mm}], avisos}."""
    _exigir_windows()
    import pymupdf
    if ajuste not in AJUSTES:
        raise ErroDeImpressao("ajuste desconhecido: %s" % ajuste)
    if cor not in CORES:
        raise ErroDeImpressao("cor desconhecida: %s" % cor)
    copias = max(1, min(99, int(copias or 1)))
    lista = papeis(impressora)["papeis"]               # e confere que a impressora existe
    doc = pymupdf.open(caminho_pdf)
    if not doc.page_count:
        raise ErroDeImpressao("não há folha para imprimir.")
    planos = []
    for i, pg in enumerate(doc):
        fw, fh = pg.rect.width / 72.0 * 25.4, pg.rect.height / 72.0 * 25.4
        p, aj, aviso = papel_da_folha((fw, fh), lista, papel, ajuste)
        planos.append((i, p, aj, aviso, fw >= fh))
    avisos, folhas = [], []
    hdc = None
    total = len(planos) * copias
    feitas = 0
    try:
        for c in range(copias):
            for i, p, aj, aviso, deitado in planos:
                dm = _devmode(impressora, p["id"], deitado, cor)
                if hdc is None:
                    hdc = _gdi.CreateDCW("WINSPOOL", impressora, None, dm)
                    if not hdc:
                        raise ErroDeImpressao("não foi possível falar com a impressora \"%s\" (erro %d)."
                                              % (impressora, ctypes.get_last_error()))
                    info = _DOCINFO(ctypes.sizeof(_DOCINFO), titulo, arquivo, None, 0)
                    if _gdi.StartDocW(hdc, ctypes.byref(info)) <= 0:
                        raise ErroDeImpressao("a impressora \"%s\" recusou o trabalho (erro %d)."
                                              % (impressora, ctypes.get_last_error()))
                else:
                    _gdi.ResetDCW(hdc, dm)                     # o papel e a orientação desta folha
                if progresso:
                    progresso("imprimindo a folha %d de %d" % (feitas + 1, total), feitas / float(total))
                if _gdi.StartPage(hdc) <= 0:
                    raise ErroDeImpressao("a impressora não abriu a folha %d (erro %d)." % (i + 1, ctypes.get_last_error()))
                area = _area(hdc)
                lugar = _desenhar_pagina(hdc, doc[i], area, aj, cor)
                if _gdi.EndPage(hdc) <= 0:
                    raise ErroDeImpressao("a impressora não fechou a folha %d (erro %d)." % (i + 1, ctypes.get_last_error()))
                feitas += 1
                if c == 0:
                    folhas.append({"pagina": i + 1, "papel": p["nome"], "escala": round(lugar["escala"], 3),
                                   "girada": lugar["girar"], "fora_mm": lugar["fora_mm"]})
                    if aviso:
                        avisos.append("folha %d: %s" % (i + 1, aviso))
                    if aj == "real" and lugar["fora_mm"] > 1.0:
                        avisos.append("folha %d: %g mm da beira ficam fora da área que a impressora imprime"
                                      % (i + 1, lugar["fora_mm"]))
        if _gdi.EndDoc(hdc) <= 0:
            raise ErroDeImpressao("a impressora não terminou o trabalho (erro %d)." % ctypes.get_last_error())
    except BaseException:
        if hdc:
            _gdi.AbortDoc(hdc)
        raise
    finally:
        if hdc:
            _gdi.DeleteDC(hdc)
        doc.close()
    return {"paginas": len(planos), "copias": copias, "folhas": folhas, "avisos": avisos, "impressora": impressora}
