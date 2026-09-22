# -*- coding: utf-8 -*-
"""Projetos em disco: o que o gerenciador de projetos lista, cria, abre e apaga.

Um projeto é uma pasta dentro da pasta de dados (Documentos\\Metálica no programa
instalado), com tudo o que pertence a ele:

    <pasta de dados>/
    └── galpao-do-joao/
        ├── projeto.json     identificação, tipo, datas e os dados do dimensionamento
        ├── modelo.json      documento do editor 3D (barras, chapas, sólidos, camadas)
        ├── origem/          o IFC importado, como veio
        ├── memorial/  desenhos/  pranchas/  lista/      entregas do dimensionamento
        ├── detalhamento/    DXF de produção, romaneio e relatório
        └── ifc/             IFC exportado pelo editor

Tudo é arquivo comum: JSON legível, PDF, DXF, CSV, IFC. O usuário copia a pasta para
fazer backup ou mandar o projeto a alguém, e o programa do outro lado a enxerga.

`projeto.json` guarda a **entrada** do dimensionamento, não o resultado: o cálculo leva
poucos segundos e é refeito ao abrir, de modo que um projeto antigo aberto numa versão
nova do programa sai com as verificações da versão nova, e o memorial diz de qual.

Pastas que já existiam antes deste módulo (entregas geradas pelo nome do galpão) são
adotadas: aparecem na lista e ganham o `projeto.json` na primeira vez que são abertas.
"""
import datetime
import itertools
import json
import os
import re
import shutil
import threading
import time
from typing import Dict, List, Optional

from nucleo.base import ErroDeDados
import versao

ARQUIVO = "projeto.json"
HISTORICO = "historico"
#: pasta/limite do histórico do modelo; marca de projeto aberto
MAX_HISTORICO = 8

INTERVALO_HISTORICO = 600.0

ABERTO = "aberto.json"

MODELO = "modelo.json"
LIXEIRA = ".lixeira"
#: Pastas da pasta de dados que não são projetos.
RESERVADAS = {"modelos", LIXEIRA, "_conferencia", "_desenhos"}
#: O que o gerenciador mostra como conteúdo do projeto: pasta -> rótulo.
ENTREGAS = [("memorial", "Memorial"), ("desenhos", "Desenhos DXF"), ("pranchas", "Pranchas"),
            ("lista", "Lista de material"), ("detalhamento", "Detalhamento"),
            ("desenhos-2d", "Desenhos 2D"), ("ifc", "IFC exportado")]
TIPOS = {"galpao": "Galpão dimensionado", "ifc": "Modelo a partir de IFC"}
IDENTIFICACAO = ("nome", "cliente", "local", "responsavel")


def slug(nome: str) -> str:
    """Nome de pasta: minúsculas, sem pontuação, hífen no lugar de espaço."""
    s = re.sub(r"[^\w\s-]", "", (nome or "projeto"), flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60].strip("-") or "projeto"


def _agora() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


_TRAVAS: Dict[str, threading.Lock] = {}
_TRAVA_DAS_TRAVAS = threading.Lock()
_CONTADOR = itertools.count()
#: Quanto tempo insistir na troca do arquivo quando outro processo o segura (s).
ESPERA_TROCA = 12.0


def _trava(caminho: str) -> threading.Lock:
    with _TRAVA_DAS_TRAVAS:
        return _TRAVAS.setdefault(os.path.normcase(os.path.abspath(caminho)), threading.Lock())


def trocar_arquivo(parcial: str, caminho: str, espera: float = ESPERA_TROCA):
    """`os.replace` insistente: no Windows, o OneDrive, o antivírus ou o indexador seguram
    por alguns segundos um arquivo recém-gravado, e a troca falha com "arquivo em uso"
    (WinError 32) ou "acesso negado" (WinError 5). Tenta de novo até `espera` segundos."""
    limite = time.monotonic() + espera
    pausa = 0.05
    while True:
        try:
            os.replace(parcial, caminho)
            return
        except PermissionError:
            if time.monotonic() >= limite:
                raise
            time.sleep(pausa)
            pausa = min(pausa * 2, 1.0)


def _gravar_json(caminho: str, dados, indent=None):
    """Temporário + troca: quem ler no meio da gravação não pega metade do arquivo.

    O temporário tem nome único e a gravação de cada caminho é serializada por uma
    trava: dois pedidos simultâneos (a gravação automática do CAD e uma vista nova, ou
    dois cliques) não escrevem no mesmo temporário nem deixam um arquivo emendado."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    parcial = "%s.%d-%d.parcial" % (caminho, os.getpid(), next(_CONTADOR))
    with _trava(caminho):
        try:
            with open(parcial, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=indent)
            trocar_arquivo(parcial, caminho)
        finally:
            if os.path.exists(parcial):
                try:
                    os.remove(parcial)
                except OSError:
                    pass


def _ler_json(caminho: str, lixeira: Optional[str] = None):
    """Lê um JSON. Com `lixeira`, um arquivo emendado (JSON completo seguido de lixo —
    o que duas gravações simultâneas no mesmo temporário deixavam) é aproveitado pelo
    primeiro documento inteiro e regravado limpo; o original vai para a lixeira. O que
    não tem documento inteiro nenhum vira ErroDeDados, com o caminho, em vez de um
    "Extra data" solto."""
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except ValueError as e:
        if lixeira is None:
            raise
        try:
            dados, _ = json.JSONDecoder().raw_decode(texto.lstrip())
        except ValueError:
            raise ErroDeDados("arquivo danificado, não foi possível ler: %s (%s)" % (caminho, e))
        del texto
        lixo = lixeira
        os.makedirs(lixo, exist_ok=True)
        shutil.copy2(caminho, os.path.join(lixo, "danificado-%s-%s" % (
            time.strftime("%Y%m%d-%H%M%S"), os.path.basename(caminho))))
        _gravar_json(caminho, dados)
        return dados


#: Desenho 2D maior que isto não é lido inteiro só para listar: cabeça e cauda bastam.
DESENHO_GRANDE = 4 * 1048576


def _cabecalho_do_desenho(caminho: str, contar: bool = True) -> dict:
    """Título, escala, nº de entidades e vistas de um desenho 2D, para listagens.

    Um desenho do modelo inteiro passa de 100 MB; ler e decodificar tudo para mostrar
    um nome no menu levaria segundos. `Desenho.dict()` grava as chaves em ordem fixa —
    nome, unidade, escala, camadas, entidades, vistas, metadados —, então o título está
    nos primeiros bytes e as vistas nos últimos; o número de entidades é a contagem de
    `"id": "` nos bytes, sem decodificar JSON (dezenas de ms para 100 MB)."""
    tamanho = os.path.getsize(caminho)
    if tamanho <= DESENHO_GRANDE:
        d = _ler_json(caminho)
        return {"titulo": d.get("nome") or None, "escala": d.get("escala"),
                "entidades": len(d.get("entidades") or []),
                "vistas": [v.get("nome") or v.get("tipo") for v in d.get("vistas") or []]}
    fora: dict = {}
    with open(caminho, "rb") as f:
        if contar:
            tudo = f.read()
            cabeca = tudo[:4096].decode("utf-8", "ignore")
            cauda = tudo[-256 * 1024:].decode("utf-8", "ignore")
            fora["entidades"] = tudo.count(b'"id": "')
            del tudo
        else:                                       # só o que está nas pontas
            cabeca = f.read(4096).decode("utf-8", "ignore")
            f.seek(max(0, tamanho - 256 * 1024))
            cauda = f.read().decode("utf-8", "ignore")
    m = re.match(r'\s*\{"nome":\s*"((?:[^"\\]|\\.)*)"', cabeca)
    if m:
        fora["titulo"] = json.loads('"%s"' % m.group(1))
    m = re.search(r'"escala":\s*([0-9.]+)', cabeca[:2048])
    if m:
        fora["escala"] = float(m.group(1))
    i = cauda.rfind('"vistas": [')
    if i >= 0:
        try:
            fim = json.loads("{" + cauda[i:])
            fora["vistas"] = [v.get("nome") or v.get("tipo") for v in fim.get("vistas") or []]
        except ValueError:
            pass
    return fora


class Projetos:
    """Operações sobre os projetos de uma pasta de dados."""

    def __init__(self, raiz: str):
        self.raiz = raiz

    # ------------------------------------------------------------ caminhos
    def pasta(self, s: str) -> str:
        """Pasta do projeto, recusando qualquer coisa que saia da pasta de dados."""
        s = os.path.basename(str(s or "").replace("\\", "/").rstrip("/"))
        if not s or s.startswith(".") or s in RESERVADAS:
            raise ErroDeDados("projeto inválido: %r" % s)
        return os.path.join(self.raiz, s)

    def _existente(self, s: str) -> str:
        pasta = self.pasta(s)
        if not os.path.isdir(pasta):
            raise ErroDeDados("projeto não encontrado: " + s)
        return pasta

    def _slug_livre(self, nome: str) -> str:
        base = slug(nome)
        if base in RESERVADAS:
            base += "-projeto"
        candidato, n = base, 2
        while os.path.exists(os.path.join(self.raiz, candidato)):
            candidato, n = "%s-%d" % (base, n), n + 1
        return candidato

    # ------------------------------------------------------------ leitura
    def ler(self, s: str) -> dict:
        """`projeto.json`, criado na hora para pasta adotada."""
        pasta = self._existente(s)
        caminho = os.path.join(pasta, ARQUIVO)
        if os.path.exists(caminho):
            try:
                p = _ler_json(caminho)
                if isinstance(p, dict):
                    p.setdefault("nome", s)
                    p.setdefault("tipo", "galpao")
                    return p
            except (OSError, ValueError):
                pass                                  # arquivo estragado: reconstrói abaixo
        quando = datetime.datetime.fromtimestamp(os.path.getmtime(pasta)).replace(
            microsecond=0).isoformat()
        p = {"formato": 1, "nome": s.replace("-", " ").strip().capitalize() or s,
             "cliente": "", "local": "", "responsavel": "",
             "tipo": "ifc" if os.path.isdir(os.path.join(pasta, "origem")) else "galpao",
             "criado": quando, "alterado": quando, "programa": versao.VERSAO,
             "dados": None, "origem_ifc": None, "adotado": True}
        _gravar_json(caminho, p, indent=1)
        return p

    def resumo(self, s: str) -> dict:
        """Uma linha da lista do gerenciador."""
        pasta = self._existente(s)
        p = self.ler(s)
        entregas = []
        for sub, rotulo in ENTREGAS:
            d = os.path.join(pasta, sub)
            if os.path.isdir(d) and any(os.scandir(d)):
                entregas.append({"pasta": sub, "rotulo": rotulo})
        modelo = os.path.join(pasta, MODELO)
        dados = p.get("dados") or {}
        return {"slug": s, "nome": p.get("nome") or s, "cliente": p.get("cliente", ""),
                "local": p.get("local", ""), "responsavel": p.get("responsavel", ""),
                "tipo": p.get("tipo", "galpao"), "tipo_rotulo": TIPOS.get(p.get("tipo"), "Projeto"),
                "criado": p.get("criado"), "alterado": p.get("alterado"),
                "programa": p.get("programa"),
                "tem_dados": bool(dados), "vao": dados.get("vao"),
                "comprimento": dados.get("comprimento"),
                "tem_modelo": os.path.exists(modelo),
                "modelo_mb": round(os.path.getsize(modelo) / 1048576, 1) if os.path.exists(modelo) else 0,
                "origem_ifc": p.get("origem_ifc"), "entregas": entregas, "pasta": pasta,
                "tem_materiais": os.path.exists(os.path.join(pasta, "detalhamento", "lista-de-materiais.json")),
                "aberto_por": self.aberto_por(s),
                "desenhos": [{"nome": d["nome"], "titulo": d.get("titulo") or d["nome"], "vistas": d.get("vistas") or []}
                             for d in self.listar_desenhos(s, contar=False)]}

    def listar(self) -> List[dict]:
        if not os.path.isdir(self.raiz):
            return []
        itens = []
        for nome in os.listdir(self.raiz):
            pasta = os.path.join(self.raiz, nome)
            if not os.path.isdir(pasta) or nome.startswith((".", "_")) or nome in RESERVADAS:
                continue
            conhecido = os.path.exists(os.path.join(pasta, ARQUIVO)) or any(
                os.path.isdir(os.path.join(pasta, sub)) for sub, _ in ENTREGAS) or \
                os.path.isdir(os.path.join(pasta, "origem"))
            if not conhecido:
                continue                              # pasta qualquer do usuário: não é nossa
            try:
                itens.append(self.resumo(nome))
            except (OSError, ErroDeDados):
                continue
        itens.sort(key=lambda i: i.get("alterado") or "", reverse=True)
        return itens

    # ------------------------------------------------------------ escrita
    def criar(self, nome: str, cliente="", local="", responsavel="", tipo="galpao",
              dados: Optional[dict] = None) -> dict:
        nome = re.sub(r"\s+", " ", str(nome or "")).strip()
        if not nome:
            raise ErroDeDados("dê um nome ao projeto.")
        if tipo not in TIPOS:
            raise ErroDeDados("tipo de projeto desconhecido: %r" % tipo)
        s = self._slug_livre(nome)
        agora = _agora()
        p = {"formato": 1, "nome": nome, "cliente": str(cliente or "").strip(),
             "local": str(local or "").strip(), "responsavel": str(responsavel or "").strip(),
             "tipo": tipo, "criado": agora, "alterado": agora, "programa": versao.VERSAO,
             "dados": dados or None, "origem_ifc": None}
        if p["dados"]:
            p["dados"].update({k: p[k] for k in IDENTIFICACAO})
        _gravar_json(os.path.join(self.pasta(s), ARQUIVO), p, indent=1)
        return self.resumo(s)

    def _atualizar(self, s: str, **campos) -> dict:
        p = self.ler(s)
        p.update(campos)
        p["alterado"] = _agora()
        p["programa"] = versao.VERSAO
        p.pop("adotado", None)
        _gravar_json(os.path.join(self._existente(s), ARQUIVO), p, indent=1)
        return p

    def salvar_dados(self, s: str, dados: dict) -> dict:
        """Guarda o formulário do dimensionamento como está, mesmo incompleto: é
        rascunho de trabalho, e quem valida é o cálculo. A identificação do projeto
        acompanha o que está no formulário."""
        if not isinstance(dados, dict):
            raise ErroDeDados("dados do projeto inválidos.")
        campos = {"dados": dados}
        for k in IDENTIFICACAO:
            v = dados.get(k)
            if isinstance(v, str) and (v.strip() or k != "nome"):
                campos[k] = v.strip()
        self._atualizar(s, **campos)
        return self.resumo(s)

    def tocar(self, s: str, **campos):
        """Marca o projeto como alterado agora (entrega gerada, modelo salvo)."""
        self._atualizar(s, **campos)

    def renomear(self, s: str, nome: str) -> dict:
        """Muda o nome e, se der, a pasta junto, para o Explorer mostrar o mesmo nome."""
        nome = re.sub(r"\s+", " ", str(nome or "")).strip()
        if not nome:
            raise ErroDeDados("dê um nome ao projeto.")
        p = self.ler(s)
        dados = p.get("dados")
        if isinstance(dados, dict):
            dados["nome"] = nome
        self._atualizar(s, nome=nome, dados=dados)
        novo = slug(nome)
        if novo != s and novo not in RESERVADAS and not os.path.exists(os.path.join(self.raiz, novo)):
            try:
                os.rename(self._existente(s), os.path.join(self.raiz, novo))
                s = novo
            except OSError:
                pass                                  # arquivo aberto em outro programa: fica o nome antigo
        return self.resumo(s)

    def duplicar(self, s: str, nome: Optional[str] = None) -> dict:
        origem = self._existente(s)
        p = self.ler(s)
        nome = re.sub(r"\s+", " ", str(nome or "")).strip() or (p.get("nome", s) + " (cópia)")
        novo = self._slug_livre(nome)
        shutil.copytree(origem, os.path.join(self.raiz, novo),
                        ignore=shutil.ignore_patterns("*.parcial"))
        dados = p.get("dados")
        if isinstance(dados, dict):
            dados = dict(dados, nome=nome)
        agora = _agora()
        self._atualizar(novo, nome=nome, dados=dados, criado=agora)
        return self.resumo(novo)

    def excluir(self, s: str) -> dict:
        """Não apaga: move para `.lixeira`, com a data no nome. Apagar de verdade é
        decisão do usuário, no Explorer."""
        origem = self._existente(s)
        lixo = os.path.join(self.raiz, LIXEIRA)
        os.makedirs(lixo, exist_ok=True)
        destino = os.path.join(lixo, "%s-%s" % (s, time.strftime("%Y%m%d-%H%M%S")))
        shutil.move(origem, destino)
        return {"excluido": s, "lixeira": destino}

    # ------------------------------------------------------------ desenhos 2D
    #
    # <projeto>/desenhos-2d/<nome>.desenho.json — os desenhos do CAD (ver nucleo2d).
    # A pasta não é `desenhos/`, que já é a das entregas DXF do dimensionamento.

    PASTA_DESENHOS = "desenhos-2d"

    def _pasta_desenhos(self, s: str) -> str:
        return os.path.join(self._existente(s), self.PASTA_DESENHOS)

    def _caminho_desenho(self, s: str, nome: str) -> str:
        nome = slug(nome)
        if not nome:
            raise ErroDeDados("dê um nome ao desenho.")
        return os.path.join(self._pasta_desenhos(s), nome + ".desenho.json")

    def listar_desenhos(self, s: str, contar: bool = True) -> List[dict]:
        pasta = self._pasta_desenhos(s)
        if not os.path.isdir(pasta):
            return []
        fora = []
        for arq in sorted(os.listdir(pasta)):
            if not arq.endswith(".desenho.json"):
                continue
            caminho = os.path.join(pasta, arq)
            try:
                item = {"nome": arq[:-len(".desenho.json")],
                        "alterado": datetime.datetime.fromtimestamp(
                            os.path.getmtime(caminho)).replace(microsecond=0).isoformat(),
                        "kb": round(os.path.getsize(caminho) / 1024, 1)}
            except OSError:
                continue                        # foi excluído (ou movido) entre o listdir e aqui
            item["titulo"] = item["nome"]
            try:
                item.update(_cabecalho_do_desenho(caminho, contar))
            except (OSError, ValueError):
                pass
            fora.append(item)
        fora.sort(key=lambda i: i["alterado"], reverse=True)
        return fora

    def salvar_desenho(self, s: str, nome: str, desenho: dict) -> dict:
        if not isinstance(desenho, dict):
            raise ErroDeDados("desenho 2D ausente ou inválido.")
        caminho = self._caminho_desenho(s, nome)
        _gravar_json(caminho, desenho)
        self.tocar(s)
        return {"salvo": os.path.basename(caminho), "nome": slug(nome), "projeto": s,
                "entidades": len(desenho.get("entidades") or [])}

    def abrir_desenho(self, s: str, nome: str) -> dict:
        caminho = self._caminho_desenho(s, nome)
        if not os.path.exists(caminho):
            raise ErroDeDados("desenho não encontrado: " + nome)
        return _ler_json(caminho, os.path.join(self.raiz, LIXEIRA))

    def excluir_desenho(self, s: str, nome: str) -> dict:
        caminho = self._caminho_desenho(s, nome)
        if os.path.exists(caminho):
            lixo = os.path.join(self.raiz, LIXEIRA)
            os.makedirs(lixo, exist_ok=True)
            shutil.move(caminho, os.path.join(lixo, "%s-%s-%s" % (
                s, os.path.basename(caminho), time.strftime("%Y%m%d-%H%M%S"))))
        return {"excluido": slug(nome)}

    # ------------------------------------------------------------ modelo 3D
    def caminho_modelo(self, s: str) -> str:
        return os.path.join(self._existente(s), MODELO)

    def salvar_modelo(self, s: str, documento: dict, marco: bool = False) -> dict:
        """Grava o modelo. Antes, guarda o modelo anterior no histórico quando `marco`
        (operação que muda peças: furos aplicados, detalhamento, migração) ou quando o
        último guardado tem mais de INTERVALO_HISTORICO."""
        if not isinstance(documento, dict):
            raise ErroDeDados("documento 3D ausente ou inválido.")
        try:
            self._guardar_historico(s, marco)
        except OSError:
            pass
        _gravar_json(self.caminho_modelo(s), documento)
        self.tocar(s)
        return {"salvo": MODELO, "projeto": s,
                "entidades": len(documento.get("entidades") or [])}

    # ---- histórico do modelo: cópias comprimidas das gravações anteriores
    def _pasta_historico(self, s: str) -> str:
        return os.path.join(self._existente(s), HISTORICO)

    def _guardar_historico(self, s: str, marco: bool):
        import gzip
        import shutil
        caminho = self.caminho_modelo(s)
        if not os.path.exists(caminho):
            return
        pasta = self._pasta_historico(s)
        os.makedirs(pasta, exist_ok=True)
        anteriores = sorted(f for f in os.listdir(pasta) if f.startswith("modelo-") and f.endswith(".json.gz"))
        if anteriores and not marco:
            ultimo = os.path.getmtime(os.path.join(pasta, anteriores[-1]))
            if time.time() - ultimo < INTERVALO_HISTORICO:
                return
        base = "modelo-%s%s" % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), "-marco" if marco else "")
        nome, k = base + ".json.gz", 1
        while os.path.exists(os.path.join(pasta, nome)):        # duas gravações no mesmo segundo
            k += 1
            nome = "%s-%d.json.gz" % (base, k)
        with open(caminho, "rb") as f, gzip.open(os.path.join(pasta, nome), "wb", compresslevel=6) as g:
            shutil.copyfileobj(f, g)
        anteriores.append(nome)
        for velho in anteriores[:-MAX_HISTORICO]:
            try:
                os.remove(os.path.join(pasta, velho))
            except OSError:
                pass

    def listar_historico(self, s: str) -> List[dict]:
        """Gravações anteriores do modelo, da mais nova para a mais antiga."""
        pasta = self._pasta_historico(s)
        if not os.path.isdir(pasta):
            return []
        fora = []
        for f in sorted(os.listdir(pasta), reverse=True):
            if not (f.startswith("modelo-") and f.endswith(".json.gz")):
                continue
            m = re.match(r"modelo-(\d{8})-(\d{6})(-marco)?(?:-\d+)?\.json\.gz$", f)
            quando = ""
            if m:
                quando = "%s-%s-%sT%s:%s:%s" % (m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:], m.group(2)[:2], m.group(2)[2:4], m.group(2)[4:])
            fora.append({"arquivo": f, "quando": quando, "marco": bool(m and m.group(3)),
                         "mb": round(os.path.getsize(os.path.join(pasta, f)) / 1048576, 2)})
        return fora

    def restaurar_modelo(self, s: str, arquivo: str) -> dict:
        """Volta o modelo a uma gravação do histórico; a atual vai para o histórico como
        marco antes, então nada se perde."""
        import gzip
        arquivo = os.path.basename(str(arquivo or ""))
        caminho = os.path.join(self._pasta_historico(s), arquivo)
        if not (arquivo.startswith("modelo-") and arquivo.endswith(".json.gz")) or not os.path.exists(caminho):
            raise ErroDeDados("gravação do histórico não encontrada: %s" % arquivo)
        with gzip.open(caminho, "rb") as f:
            documento = json.loads(f.read().decode("utf-8"))
        if not isinstance(documento, dict) or "entidades" not in documento:
            raise ErroDeDados("a gravação %s não é um modelo válido." % arquivo)
        r = self.salvar_modelo(s, documento, marco=True)
        r["restaurado"] = arquivo
        return r

    # ---- projeto aberto: quem está com o modelo na tela (outra máquina no OneDrive)
    def marcar_aberto(self, s: str, maquina: str, usuario: str, minimo: float = 60.0):
        """Grava aberto.json com máquina, usuário e hora; regrava no máximo a cada
        `minimo` s (OneDrive sincroniza cada gravação)."""
        caminho = os.path.join(self._existente(s), ABERTO)
        try:
            if os.path.exists(caminho) and time.time() - os.path.getmtime(caminho) < minimo:
                with open(caminho, encoding="utf-8") as f:
                    atual = json.load(f)
                if atual.get("maquina") == maquina:
                    return
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"maquina": maquina, "usuario": usuario, "quando": time.time()}, f)
        except (OSError, ValueError):
            pass

    def desmarcar_aberto(self, s: str, maquina: str):
        caminho = os.path.join(self._existente(s), ABERTO)
        try:
            with open(caminho, encoding="utf-8") as f:
                atual = json.load(f)
            if atual.get("maquina") == maquina:
                os.remove(caminho)
        except (OSError, ValueError):
            pass

    def aberto_por(self, s: str, limite: float = 180.0) -> Optional[dict]:
        """{maquina, usuario, ha_s} quando alguém marcou o projeto como aberto há menos
        de `limite` s (pela hora gravada no arquivo, que viaja pelo OneDrive)."""
        caminho = os.path.join(self._existente(s), ABERTO)
        try:
            with open(caminho, encoding="utf-8") as f:
                atual = json.load(f)
            ha = time.time() - float(atual.get("quando") or 0)
            if 0 <= ha < limite:
                return {"maquina": atual.get("maquina", ""), "usuario": atual.get("usuario", ""), "ha_s": round(ha)}
        except (OSError, ValueError, TypeError):
            pass
        return None

    def abrir_modelo(self, s: str) -> Optional[dict]:
        caminho = self.caminho_modelo(s)
        if not os.path.exists(caminho):
            return None
        return _ler_json(caminho, os.path.join(self.raiz, LIXEIRA))
