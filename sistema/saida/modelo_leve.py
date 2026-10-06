# -*- coding: utf-8 -*-
"""O 3D leve de cada projeto para o modo "ver" do computador (e o mesmo arquivo do celular).

Abrir o modelo só para ver não precisa do documento editável: o editor do PC lê o modelo inteiro (o
Bella Casa são 190 MB de texto), monta os vértices como objetos e os triângulos, e leva 7–8 s e ~490 MB.
O visor (web/visor3d) recebe o modelo já pronto para a placa de vídeo (saida/pacote_celular.py): 22 MB,
aberto em menos de um segundo. Editar continua no editor, carregado só quando se pede.

O arquivo fica numa pasta de trabalho fora do OneDrive (é refeito do modelo quando preciso, não há por
que subir para a nuvem) e é refeito:
* quando pedido e o modelo mudou desde a última vez (quem pede um velho recebe "preparando");
* em segundo plano, pouco depois de o modelo ser gravado — só dos projetos já vistos alguma vez, para a
  próxima abertura ser imediata sem gastar o computador com projetos que ninguém abre em "ver".
"""
import gc
import hashlib
import json
import os
import threading
import time
from typing import Dict, Optional

#: Depois de gravar, espera um pouco (o editor grava em sequência) antes de refazer.
ESPERA_DEPOIS_DE_GRAVAR = 8.0

_trava = threading.RLock()
_situacao: Dict[str, dict] = {}        # pasta do cache -> {"situacao", "progresso", "erro"}
_agendados: Dict[str, threading.Timer] = {}
_fila_trava = threading.Lock()          # uma geração por vez (o Bella Casa ocupa memória)


def pasta_de_trabalho(raiz_projetos: str) -> str:
    """Fora do OneDrive, em %LOCALAPPDATA%\\Metálica\\3d-leve, separada por pasta de dados; a de um teste ou
    verificador (pasta de dados temporária) fica dentro dela, para nada de um teste ir parar na do usuário."""
    if os.environ.get("METALICA_3D_LEVE_DIR"):
        return os.environ["METALICA_3D_LEVE_DIR"]
    import tempfile
    raiz = os.path.normcase(os.path.abspath(raiz_projetos))
    temporaria = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    if raiz.startswith(temporaria + os.sep):
        return os.path.join(raiz_projetos, ".3d-leve")
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Metálica", "3d-leve", hashlib.sha1(raiz.encode("utf-8")).hexdigest()[:10])


def _cache(pasta_projeto: str) -> str:
    raiz = os.path.dirname(os.path.abspath(pasta_projeto))
    return os.path.join(pasta_de_trabalho(raiz), os.path.basename(os.path.abspath(pasta_projeto)))


def _assinatura(pasta_projeto: str) -> str:
    try:
        st = os.stat(os.path.join(pasta_projeto, "modelo.json"))
    except OSError:
        return ""
    return hashlib.sha1(("%d:%d" % (int(st.st_mtime * 1000), st.st_size)).encode()).hexdigest()


def arquivos(pasta_projeto: str) -> Optional[dict]:
    """Os arquivos prontos e atuais ({"mcel", "pecas", "versao"}), ou None se faltam ou estão velhos."""
    c = _cache(pasta_projeto)
    ass = _assinatura(pasta_projeto)
    if not ass:
        return None
    try:
        with open(os.path.join(c, "fonte.txt"), encoding="utf-8") as f:
            if f.read().strip() != ass:
                return None
    except OSError:
        return None
    mcel, pecas = os.path.join(c, "modelo3d.mcel"), os.path.join(c, "pecas.json")
    if not (os.path.isfile(mcel) and os.path.isfile(pecas)):
        return None
    return {"mcel": mcel, "pecas": pecas, "versao": ass[:12]}


def situacao(pasta_projeto: str) -> dict:
    a = arquivos(pasta_projeto)
    if a:
        return {"situacao": "pronto", "versao": a["versao"]}
    if not os.path.isfile(os.path.join(pasta_projeto, "modelo.json")):
        return {"situacao": "sem modelo"}
    return dict(_situacao.get(_cache(pasta_projeto)) or {"situacao": "velho"})


def gerar(pasta_projeto: str) -> dict:
    """Gera agora (neste fio). Grava em arquivos novos e troca no fim: quem lê nunca vê um pela metade."""
    from saida.pacote_celular import gerar_3d
    c = _cache(pasta_projeto)
    with _fila_trava:
        if arquivos(pasta_projeto):
            return arquivos(pasta_projeto)
        ass = _assinatura(pasta_projeto)
        os.makedirs(c, exist_ok=True)

        def progresso(k, n):
            _situacao[c] = {"situacao": "preparando", "progresso": round(0.15 + 0.8 * k / max(n, 1), 2)}
        _situacao[c] = {"situacao": "preparando", "progresso": 0.05}
        try:
            with open(os.path.join(pasta_projeto, "modelo.json"), encoding="utf-8") as f:
                modelo = json.load(f)
            binario, fichas, _num = gerar_3d(modelo, progresso)
            del modelo
            for nome, dados in (("modelo3d.mcel", binario),
                                ("pecas.json", json.dumps(fichas, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))):
                with open(os.path.join(c, nome + ".novo"), "wb") as f:
                    f.write(dados)
                os.replace(os.path.join(c, nome + ".novo"), os.path.join(c, nome))
            with open(os.path.join(c, "fonte.txt"), "w", encoding="utf-8") as f:
                f.write(ass)
            _situacao.pop(c, None)
        except Exception as e:                                          # noqa: BLE001 — a tela mostra e abre o editor
            _situacao[c] = {"situacao": "erro", "erro": str(e)[:300]}
            raise
        finally:
            gc.collect()
    return arquivos(pasta_projeto) or {}


def pedir(pasta_projeto: str) -> dict:
    """Pronto → os arquivos; senão começa (em segundo plano) e devolve a situação."""
    a = arquivos(pasta_projeto)
    if a:
        return {"situacao": "pronto", **a}
    c = _cache(pasta_projeto)
    with _trava:
        s = _situacao.get(c)
        if s and s.get("situacao") in ("na fila", "preparando"):
            return dict(s)
        if not os.path.isfile(os.path.join(pasta_projeto, "modelo.json")):
            return {"situacao": "sem modelo"}
        _situacao[c] = {"situacao": "na fila", "progresso": 0.0}
    threading.Thread(target=_gerar_calado, args=(pasta_projeto,), name="3d-leve", daemon=True).start()
    return dict(_situacao[c])


def _gerar_calado(pasta_projeto: str):
    try:
        gerar(pasta_projeto)
    except Exception:                                                   # noqa: BLE001 — já ficou em _situacao
        pass


def gravado(pasta_projeto: str):
    """O modelo acabou de ser gravado: se o projeto já foi visto em "ver", refaz daqui a pouco, em
    segundo plano (gravações seguidas adiam; só a última conta)."""
    c = _cache(pasta_projeto)
    if not os.path.isdir(c):
        return
    with _trava:
        velho = _agendados.pop(c, None)
        if velho:
            velho.cancel()
        t = threading.Timer(ESPERA_DEPOIS_DE_GRAVAR, _gerar_calado, args=(pasta_projeto,))
        t.daemon = True
        _agendados[c] = t
        t.start()
