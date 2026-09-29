# -*- coding: utf-8 -*-
"""Desenhos de detalhamento e pranchas que se atualizam sozinhos (pedido do usuário, 28/09: "consegue
atualizar elas sem precisar gerar todas as vezes").

O detalhamento grava um **carimbo** do que ele usou (`detalhamento/carimbo.json`): o modelo 3D (data e
tamanho do arquivo), o código do detalhamento (a impressão dos fontes; no programa instalado, a versão),
a furação ajustada à mão e os eixos. Quando o carimbo não bate mais — o 3D foi gravado, saiu uma versão
nova do detalhamento, a furação mudou —, os desenhos estão velhos e são refeitos em segundo plano, pelo
mesmo caminho do botão Detalhar (que mantém a montagem das folhas). O CAD pergunta o estado
(`estado`) e recarrega o desenho aberto quando a geração dele muda.

As **pranchas** vêm junto: depois de cada atualização, e quando um desenho de trabalho com folhas é
gravado, o desenho "Pranchas" é refeito — das folhas (`pranchas_das_folhas`) ou pela montagem automática
com os mesmos parâmetros da última vez.

O app entrega as funções que fazem o trabalho (`configurar`): este módulo só decide quando.
"""
import hashlib
import json
import os
import sys
import threading
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
#: pastas do código que o detalhamento usa (no modo desenvolvimento, a impressão delas)
FONTES = ("nucleo2d", "saida", "nucleo", "nucleo3d", "ifc")
#: espera depois da última gravação do modelo 3D (o editor grava a cada edição) antes de refazer
ESPERA_MODELO = 8.0
#: espera depois da última gravação de um desenho de trabalho com folhas antes de refazer as pranchas
ESPERA_FOLHAS = 4.0

_trava = threading.Lock()
_estado = {}           # projeto → {"atualizando": bool, "etapa", "desde", "fim", "erro", "motivo"}
_timers = {}           # (projeto, tipo) → threading.Timer
_impressao = None
_funcoes = {}          # "detalhar": fn(s) → dict; "pranchas": fn(s) → geração ou None; "gerente": fn() → Projetos
_travas = {}           # projeto → Lock: o botão Detalhar e a atualização automática nunca juntos


def trava(s: str) -> threading.Lock:
    """a trava do detalhamento do projeto (o botão e a atualização automática passam por ela)"""
    with _trava:
        return _travas.setdefault(s, threading.Lock())


def nova_geracao() -> str:
    """identifica uma geração dos desenhos: o CAD compara com a do desenho aberto para recarregar"""
    return time.strftime("%Y%m%d-%H%M%S") + "-%04d" % (int(time.time() * 1000) % 10000)


def configurar(**funcoes):
    """o app entrega: detalhar(s) (o mesmo do botão), pranchas(s) (refaz o desenho das pranchas),
    gerente() (o Projetos)"""
    _funcoes.update(funcoes)


# ------------------------------------------------------------------ carimbo
def impressao_do_codigo() -> str:
    """dos fontes do detalhamento no modo desenvolvimento; no programa instalado (sem os fontes), a
    versão"""
    global _impressao
    if _impressao:
        return _impressao
    import versao
    if getattr(sys, "frozen", False):
        _impressao = "v" + versao.VERSAO
        return _impressao
    h = hashlib.sha256(versao.VERSAO.encode())
    for pasta in FONTES:
        base = os.path.join(AQUI, pasta)
        for raiz, dirs, arqs in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for nome in sorted(arqs):
                if nome.endswith(".py"):
                    with open(os.path.join(raiz, nome), "rb") as f:
                        h.update(os.path.relpath(os.path.join(raiz, nome), AQUI).encode() + b"\0"
                                 + f.read().replace(b"\r\n", b"\n") + b"\0")
    _impressao = h.hexdigest()[:16]
    return _impressao


def _assinatura_arquivo(caminho: str) -> str:
    try:
        st = os.stat(caminho)
    except OSError:
        return ""
    return "%d:%d" % (int(st.st_mtime), st.st_size)


def carimbo(s: str) -> dict:
    """o que o detalhamento do projeto usa agora"""
    g = _funcoes["gerente"]()
    pasta = g._existente(s)
    eixos = (g.ler(s) or {}).get("eixos")
    return {"modelo": _assinatura_arquivo(g.caminho_modelo(s)),
            "codigo": impressao_do_codigo(),
            "ajustes": _assinatura_arquivo(os.path.join(pasta, "detalhamento", "ajustes-furos.json")),
            "eixos": hashlib.sha256(json.dumps(eixos, sort_keys=True, default=str).encode()).hexdigest()[:12]}


def _arq_carimbo(s: str) -> str:
    return os.path.join(_funcoes["gerente"]()._existente(s), "detalhamento", "carimbo.json")


def _gravar(s: str, c: dict):
    arq = _arq_carimbo(s)
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    tmp = arq + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(tmp, arq)


def gravar_carimbo(s: str, geracoes: dict = None, completo: bool = True, extra: dict = None) -> dict:
    """depois de detalhar (o modelo já regravado com os nomes e as chapas): o que foi usado, e a
    geração de cada desenho gravado ({nome: geração}). `completo` (todos os grupos refeitos): o
    carimbo inteiro passa a valer; parcial, só as gerações dos desenhos refeitos."""
    with _trava:
        c = ler_carimbo(s)
        if completo or not c:
            c.update(carimbo(s))
            c["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
            c.pop("erro", None)
        c.setdefault("desenhos", {}).update(geracoes or {})
        c.update(extra or {})
        _gravar(s, c)
    return c


def registrar_desenho(s: str, nome: str, geracao: str):
    """um desenho (o das pranchas) foi refeito com esta geração"""
    with _trava:
        c = ler_carimbo(s)
        c.setdefault("desenhos", {})[nome] = geracao
        _gravar(s, c)


def ler_carimbo(s: str) -> dict:
    try:
        with open(_arq_carimbo(s), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def tem_detalhamento(s: str) -> bool:
    g = _funcoes["gerente"]()
    try:
        return any(d.get("nome", "").startswith("detalhamento-") for d in g.listar_desenhos(s, contar=False))
    except Exception:                                           # noqa: BLE001
        return False


def por_que_velho(s: str) -> str:
    """"" quando o detalhamento está em dia; senão, o motivo ("o modelo 3D mudou"…). Projeto sem
    detalhamento nunca está velho (o primeiro é pelo botão)."""
    if not tem_detalhamento(s):
        return ""
    antes = ler_carimbo(s)
    if not antes:
        return "detalhamento feito antes da atualização automática"
    agora = carimbo(s)
    for chave, motivo in (("codigo", "o detalhamento do programa mudou"), ("modelo", "o modelo 3D mudou"),
                          ("ajustes", "a furação ajustada mudou"), ("eixos", "os eixos mudaram")):
        if antes.get(chave) != agora.get(chave):
            return motivo
    return ""


# ------------------------------------------------------------------ o trabalho em segundo plano
def estado(s: str, conferir: bool = True) -> dict:
    """o que o CAD pergunta: se está atualizando, a etapa, e a geração de cada desenho (muda quando o
    desenho é refeito). Com `conferir`, começa a atualização se o detalhamento está velho."""
    if conferir:
        motivo = ""
        try:
            motivo = por_que_velho(s)
        except Exception:                                       # noqa: BLE001 — conferir nunca derruba a tela
            motivo = ""
        if motivo:
            atualizar(s, motivo)
    with _trava:
        e = dict(_estado.get(s) or {})
    c = ler_carimbo(s)
    e["desenhos"] = c.get("desenhos") or {}
    if c.get("erro") and not e.get("erro"):
        e["erro"] = c["erro"]
    return e


def atualizar(s: str, motivo: str = "pedido", so_pranchas: bool = False) -> bool:
    """começa a atualização do projeto em segundo plano (uma de cada vez por projeto). Devolve se
    começou agora."""
    with _trava:
        e = _estado.get(s) or {}
        if e.get("atualizando"):
            e["de_novo"] = e.get("de_novo") or not so_pranchas     # o que mudou no meio: refaz ao terminar
            return False
        _estado[s] = {"atualizando": True, "motivo": motivo, "desde": time.time(), "etapa": "começando…",
                      "so_pranchas": so_pranchas}
    threading.Thread(target=_rodar, args=(s, motivo, so_pranchas), daemon=True, name="desenhos-vivos-" + s).start()
    return True


def _rodar(s: str, motivo: str, so_pranchas: bool):
    erro = ""
    try:
        if not so_pranchas:
            _funcoes["detalhar"](s)          # grava o carimbo, com a geração dos desenhos
        if _funcoes.get("pranchas"):
            _funcoes["pranchas"](s)          # refaz o desenho das pranchas, se houver, e registra a geração
    except Exception as exc:                                    # noqa: BLE001 — fica no estado para a tela
        erro = str(exc) or exc.__class__.__name__
        traceback.print_exc()
        if not so_pranchas:
            # não fica tentando de novo a cada pergunta: o carimbo registra a tentativa
            try:
                gravar_carimbo(s, extra={"erro": erro[:300]})
            except Exception:                                   # noqa: BLE001
                pass
    with _trava:
        de_novo = (_estado.get(s) or {}).get("de_novo")
        _estado[s] = {"atualizando": False, "motivo": motivo, "fim": time.time(), "erro": erro}
    if de_novo and not erro:
        atualizar(s, "mudou durante a atualização")


def _agendar(chave, espera, fn):
    with _trava:
        t = _timers.pop(chave, None)
        if t:
            t.cancel()
        t = threading.Timer(espera, fn)
        t.daemon = True
        _timers[chave] = t
    t.start()


def modelo_gravado(s: str):
    """o editor 3D gravou o modelo: com detalhamento feito, refaz depois de ESPERA_MODELO sem gravar"""
    if tem_detalhamento(s):
        _agendar((s, "modelo"), ESPERA_MODELO, lambda: atualizar(s, "o modelo 3D mudou"))


def desenho_gravado(s: str, nome: str, desenho: dict):
    """o CAD gravou um desenho: com folhas e com o desenho das pranchas já feito, refaz as pranchas"""
    if not isinstance(desenho, dict) or (desenho.get("metadados") or {}).get("pranchas") is not None:
        return                                                   # o próprio desenho das pranchas
    if not any((e.get("atributos") or {}).get("folha") for e in (desenho.get("entidades") or [])):
        return
    g = _funcoes["gerente"]()
    try:
        if not any(d.get("pranchas") for d in g.listar_desenhos(s, contar=False)):
            return
    except Exception:                                           # noqa: BLE001
        return
    _agendar((s, "pranchas"), ESPERA_FOLHAS, lambda: atualizar(s, "folhas mudaram", so_pranchas=True))


# ------------------------------------------------------------------ cores escolhidas no CAD
# A cor de uma camada mudada no CAD (a de um perfil: "BANZOS U100X50X#9", pedido do usuário, 28/09) é
# do projeto: fica em `detalhamento/cores-camadas.json` e vale em todo desenho gerado depois (a atualização
# automática refaz os desenhos com as cores de fábrica) e nos desenhos já gravados (as pranchas).
FUNCOES_DE_PERFIL = ("BANZOS", "DIAGONAIS", "MONTANTES")


def _arq_cores(s: str) -> str:
    return os.path.join(_funcoes["gerente"]()._existente(s), "detalhamento", "cores-camadas.json")


def cores_do_usuario(s: str) -> dict:
    """{camada: "#rrggbb"} escolhidas no CAD para o projeto"""
    try:
        with open(_arq_cores(s), encoding="utf-8") as f:
            d = json.load(f)
        return {str(k): str(v) for k, v in d.items() if isinstance(v, str) and v.startswith("#")} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _perfil_da_camada(nome: str) -> str:
    base, _sp, perfil = str(nome).partition(" ")
    return perfil if base in FUNCOES_DE_PERFIL and perfil else ""


def cor_escolhida(cores: dict, nome: str):
    """a cor da camada, ou a do mesmo perfil em outra função (o perfil tem uma cor só); None sem escolha"""
    if nome in cores:
        return cores[nome]
    perfil = _perfil_da_camada(nome)
    if perfil:
        for k, v in cores.items():
            if _perfil_da_camada(k) == perfil:
                return v
    return None


def aplicar_cores(s: str, desenho, cores: dict = None) -> int:
    """põe as cores escolhidas nas camadas do desenho (o objeto Desenho ou o dict gravado); devolve quantas mudaram"""
    cores = cores_do_usuario(s) if cores is None else cores
    if not cores:
        return 0
    camadas = desenho.get("camadas") if isinstance(desenho, dict) else desenho.camadas
    n = 0
    for nome, cam in (camadas or {}).items():
        cor = cor_escolhida(cores, nome)
        if not cor:
            continue
        if isinstance(cam, dict):
            if cam.get("cor") != cor:
                cam["cor"] = cor
                n += 1
        elif getattr(cam, "cor", None) != cor:
            cam.cor = cor
            n += 1
    return n


def gravar_cores(s: str, novas: dict, aberto: str = "") -> dict:
    """POST .../cores-camadas {camadas: {nome: cor}, aberto}: guarda as cores e as põe nos desenhos já
    gravados do projeto (em segundo plano), menos o aberto no CAD — que grava o dele"""
    import re
    cores = cores_do_usuario(s)
    for k, v in (novas or {}).items():
        if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            cores[str(k)] = v.lower()
    arq = _arq_cores(s)
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    tmp = arq + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cores, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, arq)

    def nos_desenhos():
        g = _funcoes["gerente"]()
        with trava(s):                                # nunca junto com a atualização dos desenhos
            for item in g.listar_desenhos(s, contar=False):
                if item["nome"] == aberto:
                    continue
                try:
                    caminho = g._caminho_desenho(s, item["nome"])
                    antes = _assinatura_arquivo(caminho)
                    d = g.abrir_desenho(s, item["nome"])
                    if aplicar_cores(s, d, cores) and _assinatura_arquivo(caminho) == antes:
                        g.salvar_desenho(s, item["nome"], d)
                except Exception:                     # noqa: BLE001 — um desenho que não abre não para os outros
                    traceback.print_exc()
    t = threading.Thread(target=nos_desenhos, daemon=True, name="cores-" + s)
    t.start()
    return {"ok": True, "cores": cores}
