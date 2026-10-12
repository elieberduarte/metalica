# -*- coding: utf-8 -*-
"""OCR interno: o texto de PDFs escaneados e de imagens (normas, folhas de projeto, catálogos).

Pedido do usuário (12/10/2026): "pode criar um OCR para uso interno do sistema, vamos precisar bastante dessa
ferramenta" — a NBR 8800:2024 da pasta Normas é imagem pura (298 páginas sem uma letra de texto) e não dava para
procurar nela.

Usa o OCR que vem no Windows (Windows.Media.Ocr, o mesmo do recorte de tela), em português do Brasil: nada a
instalar, nem no desenvolvimento nem no programa instalado. O Python não fala direto com o WinRT; uma ponte em
PowerShell recebe uma lista de imagens e devolve, para cada uma, as linhas com as palavras e as caixas delas
(pixels da imagem). As páginas do PDF são desenhadas pelo PyMuPDF (o mesmo do leitor de PDF do CAD).

O resultado de cada página fica em cache (pelo conteúdo do arquivo, a página, a resolução e o idioma), em
%LOCALAPPDATA%\\Metalica\\ocr — fora de Documentos, que costuma estar no OneDrive: ler a norma inteira de novo
leva minutos; do cache, segundos.

Uso no código:
    from nucleo import ocr
    paginas = ocr.ler_pdf("Normas/NBR-8800-2024.pdf", paginas=range(1, 21))
    for p in paginas: print(p["pagina"], p["texto"][:80])
    ocr.procurar("Normas/NBR-8800-2024.pdf", r"excentricidade")    # [(página, linha), …]

Linha de comando:
    python -m nucleo.ocr arquivo.pdf [--paginas 10-20,35] [--dpi 200] [--saida texto.txt]
    python -m nucleo.ocr arquivo.pdf --procurar "treliça|excentric"
    python -m nucleo.ocr imagem.png
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Iterable, List, Optional, Sequence, Tuple

IDIOMA = "pt-BR"
#: Resolução padrão da página do PDF: 200 dpi dá a letra de 10 pt com ~28 px, o que o OCR do Windows lê bem
DPI = 200
#: Imagens por chamada do PowerShell (cada chamada custa ~1 s para carregar o WinRT)
LOTE = 12
#: Chamadas em paralelo (o OCR usa um núcleo por chamada)
PARALELO = max(1, min(4, (os.cpu_count() or 2) // 3))

_PONTE = r"""
param([string]$Lista, [string]$Saida, [string]$Idioma = 'pt-BR')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Esperar($op, [Type]$tipo) {
    $t = $asTask.MakeGenericMethod($tipo).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Idioma))
if (-not $motor) { throw "o idioma do OCR nao esta instalado no Windows: $Idioma" }
$caminhos = Get-Content -Raw -Encoding UTF8 $Lista | ConvertFrom-Json
$saidas = @()
foreach ($c in $caminhos) {
    $arq = Esperar ([Windows.Storage.StorageFile]::GetFileFromPathAsync($c)) ([Windows.Storage.StorageFile])
    $fluxo = Esperar ($arq.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Esperar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Esperar ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $r = Esperar ($motor.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $linhas = @()
    foreach ($l in $r.Lines) {
        $ps = @()
        foreach ($w in $l.Words) {
            $b = $w.BoundingRect
            $ps += ,@($w.Text, [math]::Round($b.X, 1), [math]::Round($b.Y, 1), [math]::Round($b.Width, 1), [math]::Round($b.Height, 1))
        }
        $linhas += ,@{ t = $l.Text; p = $ps }
    }
    $saidas += ,@{ arquivo = $c; angulo = $r.TextAngle; linhas = $linhas; largura = $bmp.PixelWidth; altura = $bmp.PixelHeight }
    $bmp.Dispose(); $fluxo.Dispose()
}
$json = ConvertTo-Json -InputObject $saidas -Depth 8 -Compress
[IO.File]::WriteAllText($Saida, $json, (New-Object System.Text.UTF8Encoding($false)))
"""


class ErroOCR(RuntimeError):
    """O OCR do Windows não respondeu (fora do Windows, idioma não instalado, imagem ilegível)."""


def _pasta_cache() -> str:
    local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    pasta = os.path.join(local, "Metalica", "ocr")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _ponte() -> str:
    """o script da ponte, gravado uma vez por versão do texto (na pasta do cache)"""
    h = hashlib.sha1(_PONTE.encode("utf-8")).hexdigest()[:10]
    caminho = os.path.join(_pasta_cache(), "ponte-%s.ps1" % h)
    if not os.path.exists(caminho):
        with open(caminho, "w", encoding="utf-8-sig") as f:           # PowerShell 5.1 lê o UTF-8 com BOM
            f.write(_PONTE)
    return caminho


def disponivel() -> bool:
    """O OCR do Windows existe e lê português?"""
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]; "
                            "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }"],
                           capture_output=True, text=True, timeout=60, creationflags=_SEM_JANELA)
        return IDIOMA in r.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False


_SEM_JANELA = 0x08000000 if os.name == "nt" else 0                     # CREATE_NO_WINDOW: sem piscar o console


def _lote(caminhos: Sequence[str], idioma: str) -> List[dict]:
    with tempfile.TemporaryDirectory(prefix="metalica_ocr_") as tmp:
        lista, saida = os.path.join(tmp, "lista.json"), os.path.join(tmp, "saida.json")
        with open(lista, "w", encoding="utf-8") as f:
            json.dump([os.path.abspath(c) for c in caminhos], f, ensure_ascii=False)
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", _ponte(),
                            "-Lista", lista, "-Saida", saida, "-Idioma", idioma],
                           capture_output=True, text=True, timeout=120 + 30 * len(caminhos), creationflags=_SEM_JANELA)
        if r.returncode != 0 or not os.path.exists(saida):
            raise ErroOCR("o OCR do Windows falhou: %s" % (r.stderr or r.stdout).strip()[:600])
        with open(saida, encoding="utf-8") as f:
            dados = json.load(f)
    if isinstance(dados, dict):                                          # ConvertTo-Json de uma lista de um
        dados = [dados]
    return [_arrumar(d) for d in dados]


def _arrumar(d: dict) -> dict:
    """o que a ponte devolve → {texto, linhas: [{texto, caixa, palavras: [{texto, caixa}]}], largura, altura, angulo};
    caixa = [x, y, largura, altura] em pixels da imagem, y para baixo"""
    linhas = []
    for l in d.get("linhas") or []:
        ps = l.get("p") or []
        if ps and not isinstance(ps[0], list):                           # uma palavra só: o JSON achatou
            ps = [ps]
        palavras = [{"texto": str(p[0]), "caixa": [float(v) for v in p[1:5]]} for p in ps if len(p) >= 5]
        if palavras:
            x0 = min(p["caixa"][0] for p in palavras)
            y0 = min(p["caixa"][1] for p in palavras)
            x1 = max(p["caixa"][0] + p["caixa"][2] for p in palavras)
            y1 = max(p["caixa"][1] + p["caixa"][3] for p in palavras)
            caixa = [x0, y0, x1 - x0, y1 - y0]
        else:
            caixa = [0.0, 0.0, 0.0, 0.0]
        linhas.append({"texto": str(l.get("t") or ""), "caixa": caixa, "palavras": palavras})
    return {"texto": "\n".join(l["texto"] for l in linhas), "linhas": linhas,
            "largura": d.get("largura"), "altura": d.get("altura"), "angulo": d.get("angulo")}


def ler_imagens(caminhos: Sequence[str], idioma: str = IDIOMA) -> List[dict]:
    """O texto de cada imagem (PNG, JPG, BMP, TIFF), na ordem dada. Ver `_arrumar` para o formato."""
    caminhos = list(caminhos)
    lotes = [caminhos[i:i + LOTE] for i in range(0, len(caminhos), LOTE)]
    with concurrent.futures.ThreadPoolExecutor(PARALELO) as ex:
        partes = list(ex.map(lambda lt: _lote(lt, idioma), lotes))
    return [p for parte in partes for p in parte]


def _assinatura(caminho: str) -> str:
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()[:16]


def _paginas_pedidas(paginas, total: int) -> List[int]:
    """None → todas; "10-20,35" ou [1, 2, …] (contando de 1) → as que existem"""
    if paginas is None:
        return list(range(1, total + 1))
    if isinstance(paginas, str):
        out = []
        for pedaco in paginas.split(","):
            pedaco = pedaco.strip()
            if not pedaco:
                continue
            a, _, b = pedaco.partition("-")
            out.extend(range(int(a), int(b or a) + 1))
        paginas = out
    return [p for p in paginas if 1 <= int(p) <= total]


def ler_pdf(caminho: str, paginas=None, dpi: int = DPI, idioma: str = IDIOMA, avisar=None) -> List[dict]:
    """O texto das páginas do PDF (contando de 1), cada uma {pagina, texto, linhas, largura, altura, dpi}.
    A página que já tem texto no PDF também passa pelo OCR: a ideia é ler o que se vê. `avisar(feitas, total)` diz o
    andamento."""
    try:
        import pymupdf
    except ImportError:                                                  # versões antigas
        import fitz as pymupdf                                           # type: ignore
    assinatura = _assinatura(caminho)
    cache = os.path.join(_pasta_cache(), assinatura)
    os.makedirs(cache, exist_ok=True)
    doc = pymupdf.open(caminho)
    try:
        pedidas = _paginas_pedidas(paginas, doc.page_count)
        nome = lambda p: os.path.join(cache, "p%04d-%d-%s.json" % (p, dpi, idioma))
        faltam = [p for p in pedidas if not os.path.exists(nome(p))]
        if faltam:
            with tempfile.TemporaryDirectory(prefix="metalica_ocr_pdf_") as tmp:
                feitas = 0
                for i in range(0, len(faltam), LOTE * PARALELO):
                    grupo = faltam[i:i + LOTE * PARALELO]
                    imgs = []
                    for p in grupo:
                        img = os.path.join(tmp, "p%04d.png" % p)
                        doc[p - 1].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY).save(img)
                        imgs.append(img)
                    for p, r in zip(grupo, ler_imagens(imgs, idioma)):
                        r.update({"pagina": p, "dpi": dpi})
                        with open(nome(p), "w", encoding="utf-8") as f:
                            json.dump(r, f, ensure_ascii=False)
                    for img in imgs:
                        os.remove(img)
                    feitas += len(grupo)
                    if avisar:
                        avisar(feitas, len(faltam))
    finally:
        doc.close()
    out = []
    for p in pedidas:
        with open(nome(p), encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def texto_do_pdf(caminho: str, paginas=None, **kw) -> str:
    """Todo o texto das páginas, com "=== pág N" antes de cada uma."""
    return "".join("\n=== pág %d\n%s\n" % (p["pagina"], p["texto"]) for p in ler_pdf(caminho, paginas, **kw))


def procurar(caminho: str, padrao: str, paginas=None, contexto: int = 0, **kw) -> List[Tuple[int, str]]:
    """As linhas (página, texto) que casam com a expressão `padrao` (sem diferença de maiúsculas e acentos);
    `contexto` linhas antes e depois vão juntas, separadas por " ⏎ "."""
    rx = re.compile(_sem_acento(padrao), re.I)
    achados = []
    for p in ler_pdf(caminho, paginas, **kw):
        linhas = [l["texto"] for l in p["linhas"]]
        for i, t in enumerate(linhas):
            if rx.search(_sem_acento(t)):
                achados.append((p["pagina"], " ⏎ ".join(linhas[max(0, i - contexto):i + contexto + 1])))
    return achados


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def main(argv: Optional[Iterable[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m nucleo.ocr", description="OCR interno (Windows, pt-BR): PDF ou imagem")
    ap.add_argument("arquivo")
    ap.add_argument("--paginas", help="ex.: 10-20,35 (contando de 1); sem isso, todas")
    ap.add_argument("--dpi", type=int, default=DPI)
    ap.add_argument("--procurar", help="expressão regular; mostra página e linha")
    ap.add_argument("--contexto", type=int, default=0, help="linhas antes e depois de cada achado")
    ap.add_argument("--saida", help="grava o texto neste arquivo (UTF-8)")
    a = ap.parse_args(list(argv) if argv is not None else None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    andamento = lambda f, t: print("  OCR: %d de %d páginas" % (f, t), file=sys.stderr, flush=True)
    if not a.arquivo.lower().endswith(".pdf"):
        texto = ler_imagens([a.arquivo])[0]["texto"]
    elif a.procurar:
        for pag, linha in procurar(a.arquivo, a.procurar, a.paginas, a.contexto, dpi=a.dpi, avisar=andamento):
            print("pág %d: %s" % (pag, linha))
        return 0
    else:
        texto = texto_do_pdf(a.arquivo, a.paginas, dpi=a.dpi, avisar=andamento)
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            f.write(texto)
        print("gravado em %s (%d caracteres)" % (a.saida, len(texto)))
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
