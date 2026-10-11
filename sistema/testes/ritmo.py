# -*- coding: utf-8 -*-
"""O ritmo da conferência antes de publicar: calmo ou cheio (pedido do usuário, 11/10/2026: "quando as
verificações começam o PC fica inutilizável… dois modos, um mais calmo para quando estou trabalhando e um
full quando o PC estiver parado, e um botão para mudar isso no painel").

* **calmo** — o computador em uso: a conferência fica em metade dos processadores lógicos (os de cima; a outra
  metade é só de quem está usando a máquina), na prioridade mais baixa do Windows (só pega o que sobra), um
  verificador de tela de cada vez (cada um é um servidor + um Chrome desenhando o 3D por software — é o que mais
  pesa em processador e memória) e o pytest em 3. Demora mais.
* **cheio** — o computador parado: todos os processadores, prioridade abaixo do normal, 3 verificadores de cada
  vez e o pytest em metade dos núcleos (como era).

O modo fica num arquivo (`_conferencia_ritmo.json`, ao lado do `_conferencia.json` da barrinha — na rodada da noite,
o do modo desenvolvimento, pela mesma variável) e o botão da barrinha/da tela inicial do modo desenvolvimento o
troca. A troca vale na hora: `vigiar()` reaplica a cada poucos segundos a prioridade e os processadores em toda a
árvore de processos da conferência (os que já rodam e os que nascem), e os verificadores pegam o próximo só
quando cabe no modo. O pytest já começado segue com o número de trabalhadores com que começou.
"""
import json
import os
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(os.path.dirname(os.environ.get("METALICA_CONFERENCIA_ARQ") or os.path.join(AQUI, "_conferencia.json")),
                   "_conferencia_ritmo.json")
MODOS = ("calmo", "cheio")
PADRAO = "calmo"
INTERVALO = 3.0          # s: de quanto em quanto tempo a árvore é conferida

_IDLE = 0x00000040
_ABAIXO = 0x00004000


def modo(arquivo: str = None) -> str:
    try:
        with open(arquivo or ARQ, encoding="utf-8") as f:
            m = json.load(f).get("modo")
    except (OSError, ValueError, AttributeError):
        m = None
    return m if m in MODOS else PADRAO


def gravar(m: str, arquivo: str = None) -> str:
    if m not in MODOS:
        raise ValueError("modo desconhecido: %r" % m)
    caminho = arquivo or ARQ
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"modo": m, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False)
    os.replace(tmp, caminho)
    return m


def nucleos() -> int:
    return os.cpu_count() or 2


def pytest_n(m: str = None) -> int:
    """os trabalhadores do pytest-xdist (medido: 200 s → 93 s com 6)"""
    meio = max(1, min(6, nucleos() // 2))
    return min(3, meio) if (m or modo()) == "calmo" else meio


def verificadores_n(m: str = None) -> int:
    """quantos verificadores de tela de cada vez (com 6 num i7 de 6 núcleos a máquina saturou; 3 é o ponto certo)"""
    return 1 if (m or modo()) == "calmo" else max(1, min(3, nucleos() // 4))


def mascara(m: str, sistema: int) -> int:
    """os processadores lógicos da conferência: todos no cheio; no calmo, a metade de cima (pelo menos 1, e a de
    baixo — onde o Windows põe primeiro o que o usuário abre — fica livre)"""
    if m != "calmo":
        return sistema
    bits = [i for i in range(64) if sistema >> i & 1]
    if len(bits) < 2:
        return sistema
    fica = bits[len(bits) - max(1, len(bits) // 2):]
    return sum(1 << i for i in fica)


def prioridade(m: str) -> int:
    return _IDLE if m == "calmo" else _ABAIXO


# ------------------------------------------------------------------ a árvore de processos (Windows)
def _win():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    k.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    k.GetCurrentProcess.restype = wintypes.HANDLE
    return ctypes, k, PE


def _processos(ctypes, k, PE) -> dict:
    """{pid: pai}"""
    snap = k.CreateToolhelp32Snapshot(0x2, 0)                 # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return {}
    fora = {}
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            fora[pe.th32ProcessID] = pe.th32ParentProcessID
            ok = k.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k.CloseHandle(snap)
    return fora


def _criado(ctypes, k, pid) -> int:
    h = k.OpenProcess(0x1000, False, pid)                     # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return 0
    try:
        c, x, a, b = (ctypes.c_ulonglong() for _ in range(4))
        return c.value if k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(a), ctypes.byref(b)) else 0
    finally:
        k.CloseHandle(h)


def descendentes(raiz: int) -> list:
    """os processos abertos a partir de `raiz` (filhos, netos…) — o pai conta só se nasceu antes do filho (o número
    de um processo que acabou volta a ser usado pelo Windows)"""
    ctypes, k, PE = _win()
    pais = _processos(ctypes, k, PE)
    filhos = {}
    for pid, pai in pais.items():
        if pid != pai:
            filhos.setdefault(pai, []).append(pid)
    fora, fila = [], [raiz]
    criado = {raiz: _criado(ctypes, k, raiz)}
    while fila:
        p = fila.pop()
        for f in filhos.get(p, []):
            cf = _criado(ctypes, k, f)
            if criado[p] and cf and cf < criado[p]:
                continue
            criado[f] = cf
            fora.append(f)
            fila.append(f)
    return fora


def aplicar(m: str, pids) -> int:
    """a prioridade e os processadores do modo em cada processo; devolve quantos aceitaram"""
    if os.name != "nt":
        return 0
    ctypes, k, _PE = _win()
    proc, sist = ctypes.c_size_t(), ctypes.c_size_t()
    k.GetProcessAffinityMask(k.GetCurrentProcess(), ctypes.byref(proc), ctypes.byref(sist))
    mask, pri = mascara(m, sist.value or proc.value), prioridade(m)
    n = 0
    for pid in pids:
        h = k.OpenProcess(0x0200 | 0x1000, False, pid)        # PROCESS_SET_INFORMATION | QUERY_LIMITED
        if not h:
            continue                                          # o Chrome isolado nem sempre deixa: já nasceu com o do pai
        try:
            a = k.SetPriorityClass(h, pri)
            b = mask and k.SetProcessAffinityMask(h, mask)
            n += bool(a and b)
        finally:
            k.CloseHandle(h)
    return n


def vigiar(raiz: int = None, intervalo: float = INTERVALO, parar: threading.Event = None) -> threading.Thread:
    """um fio que mantém a árvore de `raiz` (este processo) no ritmo do arquivo — a troca do botão vale na hora,
    e o que nasce depois (os servidores e os Chromes dos verificadores) entra no ritmo na volta seguinte"""
    raiz = raiz or os.getpid()

    def volta():
        while not (parar and parar.is_set()):
            try:
                aplicar(modo(), [raiz] + descendentes(raiz))
            except Exception:                                 # noqa: BLE001 — o ritmo nunca derruba a conferência
                pass
            time.sleep(intervalo)

    t = threading.Thread(target=volta, name="ritmo-da-conferencia", daemon=True)
    t.start()
    return t


def descricao(m: str = None) -> str:
    m = m or modo()
    if m == "calmo":
        return ("calmo: metade dos processadores, prioridade mínima, %d verificador de cada vez, pytest em %d"
                % (verificadores_n(m), pytest_n(m)))
    return "cheio: todos os processadores, %d verificadores de cada vez, pytest em %d" % (verificadores_n(m), pytest_n(m))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in MODOS:
        gravar(sys.argv[1])
    print(descricao())
