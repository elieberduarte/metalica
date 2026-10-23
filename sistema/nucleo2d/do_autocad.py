"""Colar no CAD 2D o que foi copiado no AutoCAD (pedido do usuário, 23/10: "criar a funcionalidade de copiar elementos de
dentro do autocad e colar na nossa área 2D").

O Ctrl+C do AutoCAD grava a seleção num DWG temporário (A$C….DWG, na pasta Temp) e põe na área de transferência do
Windows o formato dele ("AutoCAD.r25", o ClipboardInfo do ObjectARX: o caminho desse arquivo, o do desenho de origem e
o ponto de base), além de uma imagem. O navegador só enxerga a imagem; o servidor, que roda no Windows, lê o formato do
AutoCAD por ctypes (como a impressão, saida/impressao.py) e converte o DWG em DXF pelo accoreconsole.exe (o AutoCAD sem
janela, que vem com o AutoCAD instalado) — o DXF entra pelo mesmo leitor do Importar DXF (nucleo2d/dxf_ler.py), com as
camadas, as cores e as medidas.

Também vale o arquivo DWG ou DXF copiado no Explorer (Ctrl+C no arquivo)."""
import glob
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import List, Optional, Tuple

from nucleo.base import ErroDeDados

MAX_PATH = 260
#: o formato da área de transferência do AutoCAD: "AutoCAD.r25" (2025/2026), "AutoCAD.r24"…
FORMATO_AUTOCAD = re.compile(r"^AutoCAD\.r\d+$", re.I)
_CAMINHO_DWG = re.compile(r"[A-Za-z]:\\[^\x00\r\n\"<>|*?]{1,240}?\.dwg", re.I)


# ------------------------------------------------------------------ a área de transferência do Windows

def _api():
    import ctypes
    import ctypes.wintypes as w
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    sh = ctypes.WinDLL("shell32", use_last_error=True)
    u.OpenClipboard.argtypes = [w.HWND]
    u.EnumClipboardFormats.argtypes = [w.UINT]; u.EnumClipboardFormats.restype = w.UINT
    u.GetClipboardFormatNameW.argtypes = [w.UINT, w.LPWSTR, ctypes.c_int]
    u.GetClipboardData.argtypes = [w.UINT]; u.GetClipboardData.restype = w.HANDLE
    k.GlobalLock.argtypes = [w.HGLOBAL]; k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [w.HGLOBAL]
    k.GlobalSize.argtypes = [w.HGLOBAL]; k.GlobalSize.restype = ctypes.c_size_t
    sh.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]; sh.DragQueryFileW.restype = w.UINT
    return ctypes, u, k, sh


NOMES_PADRAO = {1: "texto", 2: "imagem", 3: "metafile", 7: "texto", 8: "imagem", 13: "texto", 14: "metafile", 15: "arquivos",
                16: "localidade", 17: "imagem"}


def conteudo() -> dict:
    """O que está na área de transferência: {formatos: [nomes], autocad: {formato, bytes} ou None, arquivos: [caminhos]}"""
    if sys.platform != "win32":
        raise ErroDeDados("colar do AutoCAD só funciona no Windows.")
    ctypes, u, k, sh = _api()
    aberta = False
    for _ in range(10):                                  # outro programa pode estar com ela aberta por um instante
        if u.OpenClipboard(None):
            aberta = True
            break
        time.sleep(0.05)
    if not aberta:
        raise ErroDeDados("a área de transferência do Windows está ocupada por outro programa: tente de novo.")
    out = {"formatos": [], "autocad": None, "arquivos": []}
    try:
        f = 0
        while True:
            f = u.EnumClipboardFormats(f)
            if not f:
                break
            b = ctypes.create_unicode_buffer(256)
            u.GetClipboardFormatNameW(f, b, 256)
            nome = b.value or NOMES_PADRAO.get(f, "formato %d" % f)
            out["formatos"].append(nome)
            if FORMATO_AUTOCAD.match(nome) and out["autocad"] is None:
                h = u.GetClipboardData(f)
                if h:
                    n = k.GlobalSize(h)
                    p = k.GlobalLock(h)
                    if p:
                        try:
                            out["autocad"] = {"formato": nome, "bytes": ctypes.string_at(p, n)}
                        finally:
                            k.GlobalUnlock(h)
            elif f == 15:                                # CF_HDROP: arquivos copiados no Explorer
                h = u.GetClipboardData(15)
                if h:
                    for i in range(sh.DragQueryFileW(h, 0xFFFFFFFF, None, 0)):
                        b = ctypes.create_unicode_buffer(1024)
                        sh.DragQueryFileW(h, i, b, 1024)
                        out["arquivos"].append(b.value)
    finally:
        u.CloseClipboard()
    return out


def sequencia() -> Optional[int]:
    """O número da área de transferência do Windows (GetClipboardSequenceNumber: muda a cada cópia em qualquer programa).
    O Ctrl+C do CAD guarda o de agora; no Ctrl+V, se mudou, a cópia mais nova é a de outro programa (o AutoCAD)."""
    if sys.platform != "win32":
        return None
    import ctypes
    u = ctypes.WinDLL("user32")
    u.GetClipboardSequenceNumber.restype = ctypes.c_uint32
    return int(u.GetClipboardSequenceNumber())


def ler_clipboard_info(dados: bytes) -> Tuple[Optional[str], Optional[Tuple[float, float]]]:
    """O ClipboardInfo do AutoCAD (ObjectARX): szTempFile[MAX_PATH] e szSourceFile[MAX_PATH] em UTF-16, szSignature[4],
    nFlags e dptInsert (o ponto de base, 3 doubles). Devolve (o DWG temporário, o ponto de base ou None). Se a estrutura
    não for a esperada, o caminho é procurado nos bytes."""
    caminho = None
    try:
        t = dados[:2 * MAX_PATH].decode("utf-16-le", "ignore").split("\x00", 1)[0].strip()
        if _CAMINHO_DWG.fullmatch(t):
            caminho = t
    except Exception:                                    # noqa: BLE001
        caminho = None
    if not caminho:
        for txt in (dados.decode("utf-16-le", "ignore"), dados.decode("latin-1", "ignore")):
            m = _CAMINHO_DWG.search(txt)
            if m:
                caminho = m.group(0)
                break
    base = None
    # dptInsert: depois dos dois caminhos (2 × 520 bytes), da assinatura (8) e do nFlags (4), alinhado a 8 bytes
    for ofs in (1056, 1052, 1048):
        if len(dados) >= ofs + 24:
            x, y, z = struct.unpack_from("<3d", dados, ofs)
            if all(v == v and abs(v) < 1e10 for v in (x, y, z)) and abs(z) < 1e10:
                base = (x, y)
                break
    return caminho, base


def temporario_recente(minutos: float = 15.0) -> Optional[str]:
    """o A$C….DWG mais novo da pasta Temp (o Ctrl+C do AutoCAD), se ele foi gravado há pouco"""
    pastas = {tempfile.gettempdir(), os.environ.get("TEMP") or "", os.environ.get("TMP") or ""}
    achados = []
    for p in pastas:
        if p and os.path.isdir(p):
            achados += glob.glob(os.path.join(p, "A$C*.DWG")) + glob.glob(os.path.join(p, "A$C*.dwg"))
    achados = [a for a in set(achados) if time.time() - os.path.getmtime(a) < minutos * 60]
    return max(achados, key=os.path.getmtime) if achados else None


def o_que_colar() -> dict:
    """{tipo: "dwg"|"dxf", caminho, base (x, y) ou None, origem: texto} — o que veio do AutoCAD ou o DWG/DXF copiado
    no Explorer. ErroDeDados com o que a área de transferência tem, quando não é nada disso.

    METALICA_COLAR_TESTE (só nos verificadores): o DWG/DXF que faz as vezes do copiado, sem mexer na área de
    transferência de quem roda o teste."""
    teste = os.environ.get("METALICA_COLAR_TESTE")
    if teste and os.path.exists(teste):
        return {"tipo": "dxf" if teste.lower().endswith(".dxf") else "dwg", "caminho": teste, "base": None,
                "origem": "o arquivo de teste %s" % os.path.basename(teste)}
    c = conteudo()
    if c["autocad"]:
        caminho, base = ler_clipboard_info(c["autocad"]["bytes"])
        if not caminho or not os.path.exists(caminho):
            caminho = temporario_recente()
        if caminho and os.path.exists(caminho):
            return {"tipo": "dwg", "caminho": caminho, "base": base, "origem": "o AutoCAD (%s)" % c["autocad"]["formato"]}
        raise ErroDeDados("a área de transferência tem objetos do AutoCAD, mas o arquivo temporário deles (A$C….DWG) "
                          "não foi achado: copie de novo no AutoCAD (Ctrl+C) e cole sem fechar o AutoCAD.")
    desenhos = [a for a in c["arquivos"] if a.lower().endswith((".dwg", ".dxf"))]
    if desenhos:
        a = desenhos[0]
        return {"tipo": "dxf" if a.lower().endswith(".dxf") else "dwg", "caminho": a, "base": None,
                "origem": "o arquivo %s" % os.path.basename(a)}
    tem = sorted(set(n for n in c["formatos"] if n in ("texto", "imagem", "arquivos", "metafile")))
    raise ErroDeDados("a área de transferência não tem objetos do AutoCAD%s: no AutoCAD, selecione os objetos e Ctrl+C; "
                      "depois Ctrl+V aqui." % (" (tem %s)" % ", ".join(tem) if tem else ""))


# ------------------------------------------------------------------ DWG → DXF pelo AutoCAD sem janela

def accoreconsole() -> Optional[str]:
    """o accoreconsole.exe do AutoCAD instalado mais novo (ou o de METALICA_ACCORECONSOLE)"""
    p = os.environ.get("METALICA_ACCORECONSOLE")
    if p and os.path.exists(p):
        return p
    achados = []
    for raiz in (os.environ.get("ProgramW6432") or r"C:\Program Files", os.environ.get("ProgramFiles") or r"C:\Program Files"):
        achados += glob.glob(os.path.join(raiz, "Autodesk", "AutoCAD *", "accoreconsole.exe"))
    if not achados:
        return None

    def versao(c):
        m = re.search(r"AutoCAD (\d{4})", c)
        return int(m.group(1)) if m else 0
    return max(set(achados), key=versao)


def dwg_para_dxf(dwg: str, tempo_maximo: float = 120.0) -> str:
    """O texto do DXF do DWG, convertido pelo accoreconsole (SAVEAS DXF, numa pasta temporária)."""
    exe = accoreconsole()
    if not exe:
        raise ErroDeDados("para colar do AutoCAD, o programa usa o AutoCAD instalado neste computador para ler o DWG, e "
                          "ele não foi achado (accoreconsole.exe). Sem ele: no AutoCAD, salve a seleção como DXF (WBLOCK) "
                          "e use Arquivo › Importar DXF.")
    with tempfile.TemporaryDirectory(prefix="metalica_colar_") as tmp:
        entrada = os.path.join(tmp, "copiado.dwg")
        saida = os.path.join(tmp, "copiado.dxf")
        shutil.copyfile(dwg, entrada)                    # o A$C… é do AutoCAD: trabalha numa cópia
        roteiro = os.path.join(tmp, "dxf.scr")
        with open(roteiro, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
            f.write("FILEDIA\n0\n_.SAVEAS\nDXF\n16\n%s\n_.QUIT\n_Y\n" % saida)
        cria = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        try:
            subprocess.run([exe, "/i", entrada, "/s", roteiro, "/l", "en-US"], cwd=tmp, timeout=tempo_maximo,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=cria)
        except subprocess.TimeoutExpired:
            raise ErroDeDados("o AutoCAD sem janela (accoreconsole) não converteu o DWG em %d s." % tempo_maximo)
        if not os.path.exists(saida):
            raise ErroDeDados("o AutoCAD sem janela (accoreconsole) não gravou o DXF dos objetos copiados.")
        with open(saida, "rb") as f:
            dados = f.read()
    from nucleo2d.dxf_ler import texto_de_bytes
    return texto_de_bytes(dados)


def texto_para_colar() -> dict:
    """{dxf: texto do DXF, base: (x, y) ou None — nas unidades do arquivo —, origem}"""
    o = o_que_colar()
    if o["tipo"] == "dxf":
        from nucleo2d.dxf_ler import texto_de_bytes
        with open(o["caminho"], "rb") as f:
            dados = f.read()
        texto = texto_de_bytes(dados) if b"\x00" not in dados[:200] else ""
        if not texto:
            raise ErroDeDados("o DXF copiado não é um DXF de texto (DXF binário): salve como DXF ASCII.")
    else:
        texto = dwg_para_dxf(o["caminho"])
    return {"dxf": texto, "base": o["base"], "origem": o["origem"]}
