# -*- coding: utf-8 -*-
"""A cópia dos dados para o OneDrive (DESEMPENHO N.3, 11/11/2026).

Usuário, 11/11 (pelo GESTÃO N.7): "Preciso que continue salvando os arquivos no OneDrive, tem arquivo que está sendo salvo
só no disco C." Desde 04/11 os dados ficam em C:\\Metálica\\dados (fora do OneDrive, opção A de 03/11), e a única cópia era a
tarefa "Metalica backup" da noite (03:30, robocopy /MIR) — a de 10/11 foi interrompida e a de 11/11 não rodou.

Com o programa aberto (o dev ou o instalado), um fio em segundo plano:
- a cada hora copia a pasta de dados inteira para OneDrive\\Backup Metálica\\<pasta> — só ACRESCENTA (robocopy /E): o que
  foi apagado no C: continua no OneDrive; quem limpa é a cópia da noite (/MIR);
- os documentos da obra (docx/pdf/xlsx em qualquer pasta do projeto, e tudo nas pastas 01–05 e documentos/) vão logo
  depois de gravados (olhados a cada minuto);
- ao fechar o programa, uma última cópia;
- sem historico\\, .3d-leve e __pycache__; prioridade mínima (só o que sobra da máquina);
- cada cópia deixa uma linha em copia-onedrive.log; o estado (a última que deu certo, a falha) fica em
  copia-onedrive.json e aparece no selo da tela inicial.

Só funciona LIGADA ("ligada": true no copia-onedrive.json da pasta de dados): na máquina de outro usuário, sem pedir,
nada é copiado. Dois programas abertos (dev e instalado) não copiam ao mesmo tempo (a trava copia-onedrive.trava)."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

ESTADO = "copia-onedrive.json"
REGISTRO = "copia-onedrive.log"
TRAVA = "copia-onedrive.trava"
INTERVALO_COMPLETA = 3600.0     # s entre cópias completas
INTERVALO_OLHAR = 60.0          # s entre olhadas nos documentos
ESPERA_INICIO = 120.0           # s depois de abrir o programa antes da primeira cópia (não disputa com a abertura)
REPETIR_FALHA = 600.0           # s até tentar de novo uma cópia completa que falhou
ATRASADA = 2 * 3600.0           # s sem cópia boa: o selo fica amarelo
ESTAVEL = 5.0                   # s sem mudar antes de copiar um documento (não pega o arquivo no meio da gravação)
LIMITE_ROBOCOPY = 1800.0        # s, no máximo, para uma cópia completa
FORA = ("historico", ".3d-leve", "__pycache__")
NAO_COPIAR = (ESTADO, TRAVA, "atualizando.json", "cancelar.json")
DOCUMENTOS = {".docx", ".doc", ".pdf", ".xlsx", ".xls"}
PASTA_DE_DOCUMENTOS = re.compile(r"^(0[1-5]([-_ ].*)?|documentos)$", re.I)

_trava_local = threading.Lock()
_copiando = {"o_que": "", "desde": 0.0}


# ------------------------------------------------------------------ onde

def pasta_onedrive() -> str:
    """a pasta do OneDrive pessoal do usuário ('' se não há)"""
    for v in ("OneDriveConsumer", "OneDrive"):
        p = os.environ.get(v)
        if p and os.path.isdir(p):
            return p
    p = os.path.join(os.path.expanduser("~"), "OneDrive")
    return p if os.path.isdir(p) else ""


def destino_padrao(dados: str) -> str:
    """OneDrive\\Backup Metálica\\<nome da pasta de dados> — a mesma da cópia da noite"""
    od = pasta_onedrive()
    return os.path.join(od, "Backup Metálica", os.path.basename(os.path.normpath(dados))) if od else ""


def _dentro(pasta: str, raiz: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(pasta)), os.path.normcase(os.path.abspath(raiz))]) \
            == os.path.normcase(os.path.abspath(raiz))
    except ValueError:
        return False


# ------------------------------------------------------------------ estado

def ler_estado(dados: str) -> dict:
    try:
        with open(os.path.join(dados, ESTADO), encoding="utf-8") as f:
            e = json.load(f)
        return e if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_estado(dados: str, **mudancas) -> dict:
    with _trava_local:
        e = ler_estado(dados)
        e.update(mudancas)
        tmp = os.path.join(dados, ESTADO + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(dados, ESTADO))
        return e


def ligar(dados: str, ligada: bool = True, destino: str = "") -> dict:
    return _gravar_estado(dados, ligada=bool(ligada), destino=destino or ler_estado(dados).get("destino") or "")


def _destino(dados: str, estado: Optional[dict] = None) -> str:
    e = ler_estado(dados) if estado is None else estado
    return e.get("destino") or destino_padrao(dados)


def situacao(dados: str, agora: Optional[float] = None) -> dict:
    """o que o selo da tela inicial mostra: desligada / copiando / ok / atrasada / falhou"""
    # (a falha vai em "falha", não em "erro": o api() das telas trata um "erro" na resposta como pedido que falhou)
    agora = time.time() if agora is None else agora
    e = ler_estado(dados)
    destino = _destino(dados, e)
    out = {"ligada": bool(e.get("ligada")), "destino": destino, "ultima_ok": e.get("ultima_ok"),
           "falha": e.get("erro") or "", "falhou_em": e.get("falhou_em"), "copiando": _copiando["o_que"],
           "ha_s": None if not e.get("ultima_ok") else max(0.0, agora - float(e["ultima_ok"]))}
    if not out["ligada"]:
        out["situacao"] = "desligada"
    elif out["copiando"]:
        out["situacao"] = "copiando"
    elif out["falha"] and float(e.get("falhou_em") or 0) >= float(e.get("ultima_ok") or 0):
        out["situacao"] = "falhou"
    elif out["ha_s"] is None or out["ha_s"] >= ATRASADA:
        out["situacao"] = "atrasada"
    else:
        out["situacao"] = "ok"
    return out


def _registrar(dados: str, linha: str):
    try:
        with open(os.path.join(dados, REGISTRO), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + linha + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ a trava entre programas

def _trancar(dados: str):
    try:
        f = open(os.path.join(dados, TRAVA), "a+b")
    except OSError:
        return None
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _soltar(f):
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    f.close()


# ------------------------------------------------------------------ as cópias

def _robocopy(origem: str, destino: str, limite: float) -> tuple:
    """(ok, arquivos copiados, bytes, erro)"""
    cmd = ["robocopy", origem, destino, "/E", "/COPY:DAT", "/DCOPY:T", "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/NJH",
           "/XD", *FORA, "/XF", *NAO_COPIAR, "*.tmp", "~$*"]
    flags = 0
    if os.name == "nt":
        flags = 0x00000040 | 0x08000000                  # IDLE_PRIORITY_CLASS | CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=limite, creationflags=flags)
    except FileNotFoundError:
        return _copiar_em_python(origem, destino)
    except subprocess.TimeoutExpired:
        return False, 0, 0, "a cópia passou de %d min e foi interrompida" % (limite // 60)
    saida = r.stdout.decode("cp850", "replace")
    arquivos, tamanho = _resumo_robocopy(saida)
    if r.returncode >= 8:
        erros = [l.strip() for l in saida.splitlines() if "ERRO" in l.upper() or "ERROR" in l.upper()]
        return False, arquivos, tamanho, (erros[0] if erros else "robocopy terminou com o código %d" % r.returncode)[:300]
    return True, arquivos, tamanho, ""


def _resumo_robocopy(saida: str) -> tuple:
    """(arquivos copiados, bytes copiados) do quadro final do robocopy (pt-BR ou inglês)"""
    arquivos = tamanho = 0
    for l in saida.splitlines():
        partes = l.split(":", 1)
        if len(partes) != 2:
            continue
        nome = partes[0].strip().lower()
        valores = re.findall(r"([\d.,]+)(?:\s([kmgt])(?=\s|$))?", partes[1])
        if len(valores) < 2:
            continue
        try:
            if nome in ("arquivos", "files"):
                arquivos = int(valores[1][0].replace(".", "").replace(",", ""))
            elif nome == "bytes":
                n, u = valores[1]
                tamanho = int(float(n.replace(",", ".")) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9, "t": 1e12}[u])
        except (ValueError, KeyError):
            pass
    return arquivos, tamanho


def _arquivos(origem: str):
    """(caminho relativo, caminho, quando mudou ou chegou, tamanho, mtime) de tudo que a cópia leva"""
    for raiz, pastas, nomes in os.walk(origem):
        pastas[:] = [p for p in pastas if p not in FORA]
        for n in nomes:
            if n in NAO_COPIAR or n.startswith("~$") or n.endswith(".tmp"):
                continue
            c = os.path.join(raiz, n)
            try:
                st = os.stat(c)
            except OSError:
                continue
            # no Windows o st_ctime é a criação: o PDF antigo posto agora em 01-RECEBIDOS também conta como novo
            quando = max(st.st_mtime, st.st_ctime) if os.name == "nt" else st.st_mtime
            yield os.path.relpath(c, origem), c, quando, st.st_size, st.st_mtime


def _copiar_um(c: str, destino_arq: str):
    os.makedirs(os.path.dirname(destino_arq), exist_ok=True)
    shutil.copy2(c, destino_arq)


def _copiar_em_python(origem: str, destino: str) -> tuple:
    """sem robocopy (fora do Windows): o novo ou mudado, arquivo por arquivo"""
    n = b = 0
    try:
        for rel, c, _, tam, mt in _arquivos(origem):
            d = os.path.join(destino, rel)
            try:
                st = os.stat(d)
                if int(st.st_mtime) == int(mt) and st.st_size == tam:
                    continue
            except OSError:
                pass
            _copiar_um(c, d)
            n, b = n + 1, b + tam
    except OSError as e:
        return False, n, b, str(e)[:300]
    return True, n, b, ""


def _e_documento(rel: str) -> bool:
    partes = rel.replace("\\", "/").split("/")
    if os.path.splitext(partes[-1])[1].lower() in DOCUMENTOS:
        return True
    return any(PASTA_DE_DOCUMENTOS.match(p) for p in partes[1:-1])


def copiar(dados: str, o_que: str = "hora", destino: str = "", limite: float = LIMITE_ROBOCOPY) -> dict:
    """uma cópia completa agora (o_que: 'hora', 'fechar', 'agora'); devolve a situação. Pulada se outro programa
    está copiando."""
    destino = destino or _destino(dados)
    if not destino:
        _gravar_estado(dados, erro="não achei a pasta do OneDrive neste computador", falhou_em=time.time())
        _registrar(dados, "%s FALHOU: não achei a pasta do OneDrive" % o_que)
        return situacao(dados)
    trava = _trancar(dados)
    if trava is None:
        return situacao(dados)                           # o outro programa (dev/instalado) está copiando
    t0 = time.time()
    _copiando.update(o_que=o_que, desde=t0)
    try:
        os.makedirs(destino, exist_ok=True)
        ok, n, b, erro = _robocopy(dados, destino, limite)
    except OSError as e:
        ok, n, b, erro = False, 0, 0, str(e)[:300]
    finally:
        _copiando.update(o_que="", desde=0.0)
        _soltar(trava)
    dur = time.time() - t0
    if ok:
        _gravar_estado(dados, ultima_ok=t0, o_que=o_que, arquivos=n, bytes=b, erro="", documentos_ate=t0)
        _registrar(dados, "%s ok: %d arquivo(s), %.1f MB, %.1f s → %s" % (o_que, n, b / 1e6, dur, destino))
    else:
        _gravar_estado(dados, erro=erro, falhou_em=time.time())
        _registrar(dados, "%s FALHOU (%.1f s): %s" % (o_que, dur, erro))
        print("[cópia no OneDrive] %s a cópia falhou: %s" % (time.strftime("%H:%M:%S"), erro), flush=True)
    return situacao(dados)


def copiar_documentos(dados: str, agora: Optional[float] = None) -> int:
    """os documentos gravados desde a última olhada, logo (sem esperar a hora). Devolve quantos foram."""
    agora = time.time() if agora is None else agora
    e = ler_estado(dados)
    destino = _destino(dados, e)
    desde = float(e.get("documentos_ate") or e.get("ultima_ok") or 0)
    if not destino or not desde:
        return 0                                         # sem cópia completa ainda: a completa leva tudo
    trava = _trancar(dados)
    if trava is None:
        return 0
    n, erro = 0, ""
    try:
        for rel, c, mt, tam, _ in _arquivos(dados):
            if mt <= desde or not _e_documento(rel):
                continue
            if agora - mt < ESTAVEL:                     # ainda gravando: fica para a próxima olhada
                continue
            try:
                _copiar_um(c, os.path.join(destino, rel))
                n += 1
            except OSError as ex:
                erro = "%s: %s" % (rel, ex)
    finally:
        _soltar(trava)
    # a marca anda até onde tudo está estável; o que ainda gravava entra na próxima
    novos_ate = agora - ESTAVEL
    if erro:
        _gravar_estado(dados, erro=erro[:300], falhou_em=time.time())
        _registrar(dados, "documentos FALHOU: %s" % erro[:300])
        print("[cópia no OneDrive] %s documento não copiado: %s" % (time.strftime("%H:%M:%S"), erro[:200]), flush=True)
    else:
        mud = {"documentos_ate": max(desde, novos_ate)}
        if n:
            mud.update(documentos_ok=agora)
            _registrar(dados, "documentos ok: %d arquivo(s)" % n)
        _gravar_estado(dados, **mud)
    return n


# ------------------------------------------------------------------ o fio

_fio = {"t": None, "parar": None}


def iniciar(dados: str, dormir: Callable[[float], bool] = None):
    """o fio da cópia, uma vez por processo; não faz nada enquanto a cópia estiver desligada"""
    if _fio["t"] is not None:
        return _fio["t"]
    parar = threading.Event()
    dormir = dormir or parar.wait

    def laco():
        if dormir(ESPERA_INICIO):
            return
        while True:
            try:
                e = ler_estado(dados)
                if e.get("ligada"):
                    agora = time.time()
                    ultima = float(e.get("ultima_ok") or 0)
                    falhou = float(e.get("falhou_em") or 0) if e.get("erro") else 0.0
                    if agora - ultima >= INTERVALO_COMPLETA and agora - falhou >= REPETIR_FALHA:
                        copiar(dados, "hora")
                    else:
                        copiar_documentos(dados)
            except Exception as ex:                       # noqa: BLE001 — a cópia nunca derruba o programa
                print("[cópia no OneDrive] erro: %r" % ex, file=sys.stderr, flush=True)
            if dormir(INTERVALO_OLHAR):
                return
    t = threading.Thread(target=laco, name="copia-onedrive", daemon=True)
    _fio.update(t=t, parar=parar)
    t.start()
    return t


def ao_fechar(dados: str, limite: float = 300.0):
    """a última cópia, ao fechar o programa (só se ligada)"""
    try:
        if ler_estado(dados).get("ligada"):
            copiar(dados, "fechar", limite=limite)
    except Exception as ex:                               # noqa: BLE001
        print("[cópia no OneDrive] erro ao fechar: %r" % ex, file=sys.stderr, flush=True)
