# -*- coding: utf-8 -*-
"""Desenhos de detalhamento e pranchas que se atualizam sozinhos (pedido do usuário, 28/09: "consegue
atualizar elas sem precisar gerar todas as vezes").

O detalhamento grava um **carimbo** do que ele usou (`detalhamento/carimbo.json`): o modelo 3D (data e
tamanho do arquivo), o código do detalhamento (a impressão dos fontes; no programa instalado, a versão),
a furação ajustada à mão e os eixos. Quando o que é da obra muda — o 3D foi gravado, a furação ou os eixos
mudaram —, os desenhos estão velhos e são refeitos em segundo plano, pelo mesmo caminho do botão Detalhar
(que mantém a montagem das folhas). O CAD pergunta o estado
(`estado`) e recarrega o desenho aberto quando a geração dele muda.

O programa novo, sozinho, não refaz nada (usuário, 21/10, Vicente: "todas as vezes que abro o projeto ele está em
atualização… o que mexemos foi em outra estrutura… essa está em teoria fechada"): a impressão é de todos os fontes, e
no desenvolvimento qualquer arquivo gravado — o telhamento do Posto — refazia o detalhamento e as pranchas de toda obra
aberta; no instalado, toda versão nova. Os desenhos ficam como foram conferidos, o estado diz `programa_novo` e o CAD
oferece "Atualizar agora"; a próxima mudança do 3D já detalha com o programa de hoje.

As **pranchas** vêm junto: depois de cada atualização, e quando um desenho de trabalho com folhas é
gravado, o desenho "Pranchas" é refeito — das folhas (`pranchas_das_folhas`) ou pela montagem automática
com os mesmos parâmetros da última vez.

Os **resumos** (da obra e de materiais) também, quando o projeto já os tem: sem isso eles paravam no dia
em que o botão "Gerar de novo" foi apertado (05/10).

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
_editores = {}         # projeto → hora do último sinal de um editor 3D aberto nele
#: sem sinal do editor há mais que isso (s), ele não está aberto
EDITOR_AUSENTE = 30.0


def editor_sinal(s: str):
    """o editor 3D aberto no projeto avisa que está lá (a cada poucos segundos): enquanto estiver, a
    atualização automática não grava o modelo por cima dele — só aponta o que falta (`pendente_3d`)"""
    with _trava:
        _editores[s] = time.time()


def editor_aberto(s: str) -> bool:
    with _trava:
        return time.time() - _editores.get(s, 0.0) < EDITOR_AUSENTE


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
    # no Windows a troca falha ("acesso negado") enquanto outro leitor (a tela perguntando o estado, o OneDrive
    # sincronizando) está com o arquivo aberto: tenta de novo por um instante antes de desistir (02/10)
    for tentativa in range(20):
        try:
            os.replace(tmp, arq)
            return
        except PermissionError:
            if tentativa == 19:
                raise
            time.sleep(0.1)


def gravar_carimbo(s: str, geracoes: dict = None, completo: bool = True, extra: dict = None) -> dict:
    """depois de detalhar (o modelo já regravado com os nomes e as chapas): o que foi usado, e a
    geração de cada desenho gravado ({nome: geração}). `completo` (todos os grupos refeitos): o
    carimbo inteiro passa a valer; parcial, só as gerações dos desenhos refeitos."""
    with _trava:
        c = ler_carimbo(s)
        # sem o código, o carimbo nunca foi feito: o detalhamento grava a geração de cada desenho antes
        # (registrar_desenho), e o primeiro parcial ficava sem carimbo — e se refazia sozinho na hora
        if completo or not c.get("codigo"):
            c.update(carimbo(s))
            c["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
            c.pop("erro", None)
            c.pop("cancelada", None)
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
    if antes.get("desfeito"):
        return ""          # o Detalhar foi desfeito (Desfazer, Q02): parado até o próximo Detalhar
    if trava(s).locked():
        # o detalhamento está rodando (o botão ou esta atualização): no meio dele o carimbo só tem as gerações dos
        # desenhos já gravados, sem o código, e isto dizia "o programa mudou" — a atualização entrava na fila e refazia
        # tudo logo depois do Detalhar (P24, primeiro uso 16/10); o carimbo completo chega no fim
        return ""
    agora = carimbo(s)
    canc = antes.get("cancelada")
    if canc and all(canc.get(k) == agora.get(k) for k in ("modelo", "ajustes", "eixos")):
        return ""          # cancelada pelo usuário neste mesmo estado da obra: não recomeça sozinha
    # o código do programa não entra (programa_novo): só o que é da obra
    for chave, motivo in (("modelo", "o modelo 3D mudou"), ("ajustes", "a furação ajustada mudou"),
                          ("eixos", "os eixos mudaram")):
        if antes.get(chave) != agora.get(chave):
            return motivo
    return ""


def programa_novo(s: str) -> bool:
    """Os desenhos são de um programa anterior ao de agora (a impressão dos fontes no desenvolvimento, a versão no
    instalado) e nada da obra mudou: não se refazem sozinhos (ver o início do módulo); o CAD oferece atualizar."""
    if not tem_detalhamento(s):
        return False
    antes = ler_carimbo(s)
    if not antes.get("codigo") or antes.get("desfeito"):
        return False
    return antes.get("codigo") != impressao_do_codigo()


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
    # o padrão de fábrica que falta gravar no 3D (o editor estava aberto): o editor mostra "Aplicar"
    e["pendente_3d"] = c.get("pendente_3d") or {}
    e["fora_da_maquina"] = c.get("fora_da_maquina") or []
    e["fora_da_maquina_pecas"] = c.get("fora_da_maquina_pecas") or []      # o "Ver no 3D" de cada terça (Q01)
    e["desfeito"] = c.get("desfeito") or None        # o CAD avisa: os desenhos não são do 3D atual (Q02)
    e["pranchas_descartadas"] = c.get("pranchas_descartadas") or []
    e["cancelada"] = bool(c.get("cancelada")) and not e.get("atualizando")
    try:
        e["programa_novo"] = not e.get("atualizando") and programa_novo(s)
    except Exception:                                           # noqa: BLE001 — conferir nunca derruba a tela
        e["programa_novo"] = False
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


class Cancelada(BaseException):
    """A atualização em segundo plano cancelada pelo usuário (o Cancelar do aviso no CAD; usuário, 21/10: "cliquei para
    atualizar sem querer, tem como criar um botão para cancelar"). BaseException: os `except Exception` do detalhamento
    (o que segue sem uma parte) não a engolem."""


def cancelar(s: str) -> bool:
    """Pede o fim da atualização do projeto: ela para no próximo passo do cálculo, antes de gravar desenho algum (a
    gravação não confere — nada fica pela metade). Devolve se havia o que cancelar."""
    with _trava:
        e = _estado.get(s)
        if not e or not e.get("atualizando"):
            return False
        e["cancelar"] = True
        e["de_novo"] = False
        e["etapa"] = "cancelando…"
    return True


def conferir_cancelamento(s: str):
    """o detalhamento automático chama a cada passo (o avisar do progresso): cancelada, sai com Cancelada"""
    with _trava:
        if (_estado.get(s) or {}).get("cancelar"):
            raise Cancelada("atualização cancelada")


def _rodar(s: str, motivo: str, so_pranchas: bool):
    erro = ""
    try:
        conferir_cancelamento(s)
        if not so_pranchas:
            _funcoes["detalhar"](s)          # grava o carimbo, com a geração dos desenhos
        conferir_cancelamento(s)
        if _funcoes.get("pranchas"):
            _funcoes["pranchas"](s)          # refaz o desenho das pranchas, se houver, e registra a geração
        if not so_pranchas and _funcoes.get("resumos"):
            # os resumos da obra e de materiais, quando já existem: paravam no dia em que o botão foi apertado (a Sala
            # ficou 10 dias atrás das pranchas, 05/10); o erro deles não é do detalhamento
            with _trava:
                if s in _estado:
                    _estado[s]["etapa"] = "resumos da obra e de materiais…"
            try:
                _funcoes["resumos"](s)
            except Exception:                                   # noqa: BLE001
                traceback.print_exc()
    except Cancelada:
        # os desenhos ficam os de antes; o carimbo guarda o estado da obra em que foi cancelada, para a próxima
        # pergunta da tela não recomeçar na hora (por_que_velho) — uma mudança nova da obra atualiza como sempre
        try:
            agora = carimbo(s)
            gravar_carimbo(s, completo=False, extra={"cancelada": {k: agora.get(k) for k in ("modelo", "ajustes", "eixos")}})
        except Exception:                                       # noqa: BLE001
            pass
        with _trava:
            _estado[s] = {"atualizando": False, "motivo": motivo, "fim": time.time(), "erro": "", "cancelada": True}
        return
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
