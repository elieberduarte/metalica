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


_resumos: Dict[str, tuple] = {}          # caminho do modelo -> ((data, tamanho), SHA-1 do conteúdo)


def _resumo_do_modelo(caminho: str) -> str:
    """SHA-1 do conteúdo do modelo, guardado pela data e tamanho (lido de novo só quando eles mudam). Pelo
    conteúdo, e não pela data: o editor grava o modelo sem mudança nenhuma, e isso não pode refazer o 3D leve."""
    st = os.stat(caminho)
    chave = (st.st_mtime_ns, st.st_size)
    m = _resumos.get(caminho)
    if m and m[0] == chave:
        return m[1]
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 22), b""):
            h.update(bloco)
    _resumos[caminho] = (chave, h.hexdigest())
    return _resumos[caminho][1]


def _assinatura(pasta_projeto: str) -> str:
    """O conteúdo do modelo e as versões do formato: mudou um, o 3D leve guardado está velho."""
    from saida.pacote_celular import VERSAO_3D, VERSAO_FICHAS, GERACAO_MALHAS
    try:
        resumo = _resumo_do_modelo(os.path.join(pasta_projeto, "modelo.json"))
    except OSError:
        return ""
    return hashlib.sha1(("%s:%d:%d:%d" % (resumo, VERSAO_3D, VERSAO_FICHAS, GERACAO_MALHAS)).encode()).hexdigest()


def _guardados(pasta_projeto: str) -> Optional[dict]:
    """Os arquivos que estão na pasta de trabalho, atuais ou não."""
    c = _cache(pasta_projeto)
    mcel, pecas = os.path.join(c, "modelo3d.mcel"), os.path.join(c, "pecas.json")
    if not (os.path.isfile(mcel) and os.path.isfile(pecas)):
        return None
    try:
        with open(os.path.join(c, "fonte.txt"), encoding="utf-8") as f:
            versao = f.read().strip()[:12] or "velho"
    except OSError:
        versao = "velho"
    return {"mcel": mcel, "pecas": pecas, "versao": versao}


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


def _vazio(pasta_projeto: str) -> bool:
    """O modelo atual não tem peça com geometria (a planta da Estrutura apagada, o modelo novo em branco): o 3D leve
    fica marcado vazio — antes a geração dava erro e o modo ver ficava mostrando a versão anterior (06/10)."""
    ass = _assinatura(pasta_projeto)
    try:
        with open(os.path.join(_cache(pasta_projeto), "vazio.txt"), encoding="utf-8") as f:
            return bool(ass) and f.read().strip() == ass
    except OSError:
        return False


def situacao(pasta_projeto: str) -> dict:
    if _vazio(pasta_projeto):
        return {"situacao": "sem modelo", "vazio": True}
    a = arquivos(pasta_projeto)
    if a:
        return {"situacao": "pronto", "versao": a["versao"]}
    if not os.path.isfile(os.path.join(pasta_projeto, "modelo.json")):
        return {"situacao": "sem modelo"}
    return dict(_situacao.get(_cache(pasta_projeto)) or {"situacao": "velho", "etapa": "esperando a gravação terminar"})


def _trocar(novo: str, destino: str):
    """No Windows, o arquivo aberto por quem o está lendo (o modo ver baixando) não pode ser trocado: tenta
    de novo por alguns segundos."""
    for k in range(40):
        try:
            os.replace(novo, destino)
            return
        except PermissionError:
            if k == 39:
                raise
            time.sleep(0.1 + 0.02 * k)


def gerar(pasta_projeto: str) -> dict:
    """Gera agora (neste fio). Grava em arquivos novos e troca no fim: quem lê nunca vê um pela metade."""
    from saida.pacote_celular import gerar_3d
    c = _cache(pasta_projeto)
    with _fila_trava:
        if arquivos(pasta_projeto):
            return arquivos(pasta_projeto)
        ass = _assinatura(pasta_projeto)
        os.makedirs(c, exist_ok=True)

        # a fração e a etapa no formato da barra de andamento padrão (web/progresso.js: {etapa, fracao}) — o modo ver
        # mostra a barra enquanto atualiza (usuário, 19/10: "conseguimos colocar uma barrinha de carregamento quando a
        # estrutura está atualizando o modelo?")
        def progresso(k, n):
            f = round(0.15 + 0.8 * k / max(n, 1), 2)
            _situacao[c] = {"situacao": "preparando", "progresso": f, "fracao": f,
                            "etapa": "montando as peças (%d de %d)" % (k, n)}
        _situacao[c] = {"situacao": "preparando", "progresso": 0.05, "fracao": 0.05, "etapa": "lendo o modelo gravado"}
        try:
            with open(os.path.join(pasta_projeto, "modelo.json"), encoding="utf-8") as f:
                modelo = json.load(f)
            try:
                binario, fichas, _num = gerar_3d(modelo, progresso)
            except ValueError as e:
                if "não tem peças" not in str(e):
                    raise
                for nome in ("modelo3d.mcel", "pecas.json"):
                    try:
                        os.remove(os.path.join(c, nome))
                    except OSError:
                        pass
                with open(os.path.join(c, "vazio.txt"), "w", encoding="utf-8") as f:
                    f.write(ass)
                _situacao.pop(c, None)
                return {}
            _gravar_cobertura(c, ass, modelo)
            del modelo
            try:
                os.remove(os.path.join(c, "vazio.txt"))
            except OSError:
                pass
            for nome, dados in (("modelo3d.mcel", binario),
                                ("pecas.json", json.dumps(fichas, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))):
                with open(os.path.join(c, nome + ".novo"), "wb") as f:
                    f.write(dados)
                _trocar(os.path.join(c, nome + ".novo"), os.path.join(c, nome))
            with open(os.path.join(c, "fonte.txt"), "w", encoding="utf-8") as f:
                f.write(ass)
            _situacao.pop(c, None)
        except Exception as e:                                          # noqa: BLE001 — a tela mostra e abre o editor
            _situacao[c] = {"situacao": "erro", "erro": str(e)[:300]}
            raise
        finally:
            gc.collect()
    # a cobertura retrátil: a outra situação já fica pronta para o botão da barra trocar na hora
    for sit in _situacoes_a_preparar(pasta_projeto):
        threading.Thread(target=_gerar_situacao_calado, args=(pasta_projeto, sit), name="3d-leve-" + sit, daemon=True).start()
    return arquivos(pasta_projeto) or {}


def pedir(pasta_projeto: str) -> dict:
    """Pronto → os arquivos. Velho (o modelo mudou) → os arquivos de antes, na hora, com a situação
    "atualizando", e o novo é feito em segundo plano (o modo ver troca quando ficar pronto). Nunca feito →
    começa e devolve a situação ("na fila"/"preparando": o modo ver espera)."""
    if _vazio(pasta_projeto):
        return {"situacao": "sem modelo", "vazio": True}
    a = arquivos(pasta_projeto)
    if a:
        return {"situacao": "pronto", **a}
    c = _cache(pasta_projeto)
    with _trava:
        if not os.path.isfile(os.path.join(pasta_projeto, "modelo.json")):
            return {"situacao": "sem modelo"}
        s = _situacao.get(c)
        if not (s and s.get("situacao") in ("na fila", "preparando")):
            s = _situacao[c] = {"situacao": "na fila", "progresso": 0.0, "fracao": 0.0, "etapa": "na fila"}
            threading.Thread(target=_gerar_calado, args=(pasta_projeto,), name="3d-leve", daemon=True).start()
    velhos = _guardados(pasta_projeto)
    if velhos:
        return {"situacao": "atualizando", **velhos}
    return dict(s)


def _gerar_calado(pasta_projeto: str):
    try:
        gerar(pasta_projeto)
    except Exception:                                                   # noqa: BLE001 — já ficou em _situacao
        pass


# ------------------------------------------------------------------ cobertura retrátil (aberta / retraída)
#
# Ver aberta ou retraída no modo ver é só para mostrar (usuário, Kaefer, 20/10: "é apenas para demonstração"): antes o
# botão gravava o modelo inteiro na situação, o 3D leve ficava velho e era refeito, e a troca levava vários segundos e
# dois cliques. Agora é como no celular (pacote_celular._cobertura_movel): o 3D leve da outra situação é montado numa
# cópia do modelo, pela mesma conta (nucleo3d/cobertura_movel.aplicar), logo depois do principal — o modelo gravado não
# muda e o botão só troca o arquivo que o modo ver lê.

def _projeto(pasta_projeto: str) -> dict:
    try:
        with open(os.path.join(pasta_projeto, "projeto.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def tem_cobertura(pasta_projeto: str) -> bool:
    pj = _projeto(pasta_projeto)
    return bool((pj.get("analise_parametros") or {}).get("cobertura_movel") or pj.get("cobertura_movel_vista"))


def _gravar_cobertura(c: str, ass: str, modelo: dict):
    """a situação em que as peças da cobertura estão gravadas no modelo (atributos["cobertura_movel"]["situacao"])"""
    atual = next((((r.get("atributos") or {}).get("cobertura_movel") or {}).get("situacao")
                  for r in modelo.get("entidades") or [] if ((r.get("atributos") or {}).get("cobertura_movel") or {}).get("situacao")),
                 None)
    with open(os.path.join(c, "cobertura.json"), "w", encoding="utf-8") as f:
        json.dump({"fonte": ass, "atual": atual}, f)


def situacao_gravada(pasta_projeto: str) -> Optional[str]:
    """a situação do modelo gravado, guardada quando o 3D leve principal foi feito (None: sem peças da cobertura); o 3D
    leve feito antes de ela ser guardada lê o modelo uma vez"""
    c, ass = _cache(pasta_projeto), _assinatura(pasta_projeto)
    try:
        with open(os.path.join(c, "cobertura.json"), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("fonte") == ass:
            return d.get("atual")
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(pasta_projeto, "modelo.json"), encoding="utf-8") as f:
            modelo = json.load(f)
        os.makedirs(c, exist_ok=True)
        _gravar_cobertura(c, ass, modelo)
        return situacao_gravada(pasta_projeto) if ass else None
    except (OSError, ValueError):
        return None


def _situacoes_a_preparar(pasta_projeto: str) -> list:
    if not tem_cobertura(pasta_projeto):
        return []
    from nucleo3d.cobertura_movel import SITUACOES
    atual = situacao_gravada(pasta_projeto)
    return [s for s in SITUACOES if s != atual and not _arquivos_situacao(pasta_projeto, s)]


def _nomes(sit: str):
    return "modelo3d-%s.mcel" % sit, "pecas-%s.json" % sit, "fonte-%s.txt" % sit


def _arquivos_situacao(pasta_projeto: str, sit: str, velhos: bool = False) -> Optional[dict]:
    c = _cache(pasta_projeto)
    mcel, pecas, fonte = (os.path.join(c, n) for n in _nomes(sit))
    if not (os.path.isfile(mcel) and os.path.isfile(pecas)):
        return None
    try:
        with open(fonte, encoding="utf-8") as f:
            ass = f.read().strip()
    except OSError:
        ass = ""
    if not velhos and (not ass or ass != _assinatura(pasta_projeto)):
        return None
    return {"mcel": mcel, "pecas": pecas, "versao": (ass[:12] or "velho") + "-" + sit}


def gerar_situacao(pasta_projeto: str, sit: str) -> dict:
    """O 3D leve na situação `sit`, numa cópia do modelo (o gravado não muda). Uma geração por vez, como o principal."""
    from saida.pacote_celular import gerar_3d
    from nucleo3d import cobertura_movel as CM
    from nucleo3d.modelo import Documento
    c = _cache(pasta_projeto)
    chave = c + "#" + sit
    with _fila_trava:
        if _arquivos_situacao(pasta_projeto, sit):
            return _arquivos_situacao(pasta_projeto, sit)
        ass = _assinatura(pasta_projeto)
        os.makedirs(c, exist_ok=True)
        rotulo = "retraída" if sit == "retraida" else sit
        _situacao[chave] = {"situacao": "preparando", "progresso": 0.05, "fracao": 0.05, "etapa": "lendo o modelo gravado"}

        def progresso(k, n):
            f = round(0.3 + 0.65 * k / max(n, 1), 2)
            _situacao[chave] = {"situacao": "preparando", "progresso": f, "fracao": f,
                                "etapa": "cobertura %s: montando as peças (%d de %d)" % (rotulo, k, n)}
        try:
            with open(os.path.join(pasta_projeto, "modelo.json"), encoding="utf-8") as f:
                doc = Documento.de_dict(json.load(f))
            _situacao[chave] = {"situacao": "preparando", "progresso": 0.2, "fracao": 0.2, "etapa": "cobertura %s: posições" % rotulo}
            CM.aplicar(doc, (_projeto(pasta_projeto).get("analise_parametros") or {}), sit)
            binario, fichas, _num = gerar_3d(doc.dict(), progresso)
            del doc
            mcel, pecas, fonte = _nomes(sit)
            for nome, dados in ((mcel, binario),
                                (pecas, json.dumps(fichas, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))):
                with open(os.path.join(c, nome + ".novo"), "wb") as f:
                    f.write(dados)
                _trocar(os.path.join(c, nome + ".novo"), os.path.join(c, nome))
            with open(os.path.join(c, fonte), "w", encoding="utf-8") as f:
                f.write(ass)
            _situacao.pop(chave, None)
        except Exception as e:                                          # noqa: BLE001 — a tela mostra
            _situacao[chave] = {"situacao": "erro", "erro": str(e)[:300]}
            raise
        finally:
            gc.collect()
    return _arquivos_situacao(pasta_projeto, sit) or {}


def _gerar_situacao_calado(pasta_projeto: str, sit: str):
    try:
        gerar_situacao(pasta_projeto, sit)
    except Exception:                                                   # noqa: BLE001 — já ficou em _situacao
        pass


def pedir_situacao(pasta_projeto: str, sit: str, iniciar: bool = True) -> dict:
    """Como `pedir`, na situação `sit` da cobertura retrátil. A situação gravada no modelo (ou um projeto sem cobertura)
    é o 3D leve de sempre; a outra, o arquivo dela — pronta, velha (a de antes, "atualizando", e a nova em segundo
    plano) ou ainda por fazer (a situação de andamento). `iniciar=False`: só pergunta (o /estado)."""
    if not tem_cobertura(pasta_projeto):
        return pedir(pasta_projeto) if iniciar else situacao(pasta_projeto)
    principal = pedir(pasta_projeto) if iniciar else situacao(pasta_projeto)
    if principal.get("situacao") != "pronto":
        return principal                     # o principal primeiro: é ele que diz em que situação o modelo está gravado
    if situacao_gravada(pasta_projeto) == sit:
        return principal
    a = _arquivos_situacao(pasta_projeto, sit)
    if a:
        return {"situacao": "pronto", **a}
    chave = _cache(pasta_projeto) + "#" + sit
    with _trava:
        s = _situacao.get(chave)
        if iniciar and not (s and s.get("situacao") in ("na fila", "preparando")):
            s = _situacao[chave] = {"situacao": "na fila", "progresso": 0.0, "fracao": 0.0, "etapa": "na fila"}
            threading.Thread(target=_gerar_situacao_calado, args=(pasta_projeto, sit), name="3d-leve-" + sit, daemon=True).start()
    velhos = _arquivos_situacao(pasta_projeto, sit, velhos=True)
    if velhos and iniciar:
        return {"situacao": "atualizando", **velhos}
    return dict(s or {"situacao": "velho", "etapa": "na fila"})


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
