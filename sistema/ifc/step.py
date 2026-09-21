# -*- coding: utf-8 -*-
"""Leitor genérico de arquivos ISO-10303-21 (STEP) — a sintaxe em que o IFC é escrito.

O módulo não sabe nada de IFC: ele lê a gramática do "arquivo de troca" da ISO 10303
parte 21 e devolve entidades numeradas com seus argumentos já convertidos para tipos
Python. Quem dá significado a `IFCWALL` é `ifc/importar.py`.

    from ifc.step import ler
    arq = ler("modelo.ifc")
    arq.schema                      # 'IFC4'
    arq.cabecalho["FILE_NAME"]      # argumentos de FILE_NAME
    arq.entidades[42]               # Entidade(id=42, tipo='IFCWALL', args=[...])
    arq.por_tipo("IfcBeam")         # todas as vigas, sem diferenciar maiúsculas
    arq.resolver(ent.arg(5))        # segue uma referência `#123`
    arq.inversos(42)                # quem aponta para #42 (acha as relações do IFC)

Conversão dos valores:

    '...'      texto, com `''` e os escapes `\\X\\`, `\\X2\\..\\X0\\`, `\\X4\\..\\X0\\`
               e `\\S\\` já decodificados
    123 / 1.5  int / float
    #123       `Ref` (subclasse de int; `arquivo.resolver` devolve a entidade)
    .T. .F.    True / False          .U.  None
    .NOME.     `Enumeracao` (subclasse de str: compara direto com "NOME")
    $          None (valor omitido)
    *          `DERIVADO` (valor derivado na supertipagem)
    (...)      lista Python, aninhada à vontade
    TIPO(v)    `Tipado` — valor com tipo explícito, como `IFCLABEL('x')`

Entidades de instanciação complexa (`#1=(IFCX(...)IFCY(...))`) viram uma `Entidade`
com `partes` preenchido; `tipo` e `args` apontam para a primeira parte, e
`ent.parte("IFCY")` devolve os argumentos de qualquer uma delas. `por_tipo` acha a
entidade por qualquer um dos nomes.

Leitura por streaming: o arquivo é percorrido linha a linha e cada instrução (tudo até
o `;` que não está dentro de texto nem de comentário) é analisada e descartada. O que
fica na memória é só o dicionário de entidades. Índices por tipo e de referências
inversas são construídos sob demanda, na primeira consulta.

Falhas não derrubam a leitura: instrução malformada, arquivo truncado ou id repetido
viram aviso em `arquivo.avisos` e a leitura continua. Um IFC quebrado no meio ainda
entrega tudo que veio antes.
"""
import os
import re
from typing import Dict, Iterable, Iterator, List, Optional, Tuple, Union

__all__ = ["ler", "ler_texto", "ler_cabecalho", "Arquivo", "Entidade", "Ref",
           "Enumeracao", "Tipado", "DERIVADO", "ErroStep"]

MAX_AVISOS = 500


class ErroStep(Exception):
    """Erro que impede completamente a leitura (arquivo inexistente, por exemplo)."""


# --------------------------------------------------------------- tipos de valor

class Ref(int):
    """Referência a outra entidade: `#123` no arquivo."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "#%d" % int(self)

    __str__ = __repr__


class Enumeracao(str):
    """Valor de enumeração: `.ELEMENT.` vira `Enumeracao("ELEMENT")`.

    É uma string, então `ent.arg(8) == "ELEMENT"` funciona sem conversão.
    """
    __slots__ = ()

    def __repr__(self) -> str:
        return ".%s." % str.__str__(self)


class _Derivado:
    """Sentinela do valor derivado `*`. Falso em contexto booleano."""
    _unico = None
    __slots__ = ()

    def __new__(cls):
        if cls._unico is None:
            cls._unico = super().__new__(cls)
        return cls._unico

    def __repr__(self) -> str:
        return "*"

    def __bool__(self) -> bool:
        return False


DERIVADO = _Derivado()


class Tipado:
    """Valor com tipo explícito, como `IFCLABEL('Pilar')` ou `IFCREAL(1.5)`.

    Aparece nos SELECT do IFC (valor de propriedade, por exemplo). `.valor` devolve o
    conteúdo quando há um único argumento, que é o caso normal.
    """
    __slots__ = ("tipo", "args")

    def __init__(self, tipo: str, args: list):
        self.tipo = tipo
        self.args = args

    @property
    def valor(self):
        return self.args[0] if len(self.args) == 1 else self.args

    def __repr__(self) -> str:
        return "%s(%s)" % (self.tipo, ",".join(repr(a) for a in self.args))

    def __eq__(self, outro) -> bool:
        if isinstance(outro, Tipado):
            return self.tipo == outro.tipo and self.args == outro.args
        return NotImplemented

    def __hash__(self):
        return hash((self.tipo, tuple(self.args)))


class Entidade:
    """Uma instância do arquivo: `#12=IFCBEAM('0aX...',#5,$,...);`"""
    __slots__ = ("id", "tipo", "args", "partes")

    def __init__(self, id: int, tipo: str, args: list,
                 partes: Optional[List[Tipado]] = None):
        self.id = id
        self.tipo = tipo                  # sempre em MAIÚSCULAS
        self.args = args
        self.partes = partes              # instanciação complexa, quando houver

    # ---- acesso aos argumentos ----
    def arg(self, i: int, padrao=None):
        """Argumento `i`, ou `padrao` quando não existe ou está omitido (`$`)."""
        if 0 <= i < len(self.args):
            v = self.args[i]
            return padrao if v is None else v
        return padrao

    def __getitem__(self, i):
        return self.args[i]

    def __len__(self) -> int:
        return len(self.args)

    @property
    def tipos(self) -> List[str]:
        """Nomes de tipo da entidade (mais de um só na instanciação complexa)."""
        return [p.tipo for p in self.partes] if self.partes else [self.tipo]

    def parte(self, tipo: str) -> Optional[list]:
        """Argumentos da parte com esse tipo, em instanciação complexa."""
        alvo = tipo.upper()
        if self.partes:
            for p in self.partes:
                if p.tipo == alvo:
                    return p.args
        return self.args if self.tipo == alvo else None

    def e_tipo(self, *tipos: str) -> bool:
        meus = self.tipos
        return any(t.upper() in meus for t in tipos)

    def __repr__(self) -> str:
        return "#%d=%s(%d args)" % (self.id, self.tipo, len(self.args))


# --------------------------------------------------------------- decodificação de texto

_RE_X2 = re.compile(r"\\X2\\((?:[0-9A-Fa-f]{4})+)\\X0\\")
_RE_X4 = re.compile(r"\\X4\\((?:[0-9A-Fa-f]{8})+)\\X0\\")
_RE_X1 = re.compile(r"\\X\\([0-9A-Fa-f]{2})")
_RE_S = re.compile(r"\\S\\(.)", re.S)
_RE_P = re.compile(r"\\P[A-Za-z]\\")


def decodificar_texto(bruto: str) -> str:
    """Converte o miolo de um literal STEP (sem as aspas) em texto Python.

    Trata `''` (aspas escapada), `\\S\\c` (ISO 8859-x, byte + 128), `\\X\\HH`
    (um byte), `\\X2\\HHHH..\\X0\\` (UTF-16) e `\\X4\\HHHHHHHH..\\X0\\` (UTF-32),
    além de `\\PA\\` (troca de página de código, ignorada) e `\\\\`.
    """
    if "'" not in bruto and "\\" not in bruto:
        return bruto
    saida = []
    i, n = 0, len(bruto)
    while i < n:
        c = bruto[i]
        if c == "'":
            # dentro do literal, aspas simples sempre vêm em par
            saida.append("'")
            i += 2 if (i + 1 < n and bruto[i + 1] == "'") else 1
            continue
        if c != "\\":
            saida.append(c)
            i += 1
            continue
        if bruto.startswith("\\\\", i):
            saida.append("\\")
            i += 2
            continue
        m = _RE_X2.match(bruto, i)
        if m:
            try:
                saida.append(bytes.fromhex(m.group(1)).decode("utf-16-be", "replace"))
            except ValueError:
                saida.append(m.group(1))
            i = m.end()
            continue
        m = _RE_X4.match(bruto, i)
        if m:
            try:
                saida.append(bytes.fromhex(m.group(1)).decode("utf-32-be", "replace"))
            except (ValueError, UnicodeDecodeError):
                saida.append(m.group(1))
            i = m.end()
            continue
        m = _RE_X1.match(bruto, i)
        if m:
            saida.append(chr(int(m.group(1), 16)))
            i = m.end()
            continue
        m = _RE_S.match(bruto, i)
        if m:
            saida.append(chr(ord(m.group(1)) + 128))
            i = m.end()
            continue
        m = _RE_P.match(bruto, i)
        if m:                      # diretiva de página de código: sem efeito aqui
            i = m.end()
            continue
        saida.append(c)            # barra solta: mantém como veio
        i += 1
    return "".join(saida)


# --------------------------------------------------------------- tokenização

_RE_TOKEN = re.compile(r"""
    (?P<esp>[\s]+)
  | (?P<txt>'(?:[^']|'')*')
  | (?P<ref>\#[0-9]+)
  | (?P<enum>\.[A-Za-z_][A-Za-z_0-9]*\.)
  | (?P<num>[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?)
  | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<bin>"[0-9A-Fa-f]*")
  | (?P<sim>[(),=$*])
""", re.X)

_ABRE, _FECHA, _VIRGULA, _IGUAL, _CIFRAO, _ASTERISCO = "(", ")", ",", "=", "$", "*"


def _tokens(texto: str) -> List[Tuple[str, str]]:
    """Lista de (espécie, texto). Levanta ValueError em caractere inesperado."""
    fora = []
    pos, n = 0, len(texto)
    while pos < n:
        m = _RE_TOKEN.match(texto, pos)
        if m is None:
            raise ValueError("caractere inesperado %r na coluna %d" % (texto[pos], pos))
        pos = m.end()
        especie = m.lastgroup
        if especie == "esp":
            continue
        fora.append((especie, m.group()))
    return fora


class _Analisador:
    """Descida recursiva sobre a lista de tokens de uma instrução."""

    def __init__(self, tokens: List[Tuple[str, str]]):
        self.t = tokens
        self.i = 0

    def fim(self) -> bool:
        return self.i >= len(self.t)

    def olhar(self) -> Optional[Tuple[str, str]]:
        return self.t[self.i] if self.i < len(self.t) else None

    def pegar(self) -> Tuple[str, str]:
        if self.i >= len(self.t):
            raise ValueError("instrução terminou antes do esperado")
        tk = self.t[self.i]
        self.i += 1
        return tk

    def exigir(self, texto: str):
        especie, valor = self.pegar()
        if valor != texto:
            raise ValueError("esperado %r, veio %r" % (texto, valor))

    # ---- valores ----
    def valor(self):
        especie, texto = self.pegar()
        if especie == "sim":
            if texto == _ABRE:
                return self.lista()
            if texto == _CIFRAO:
                return None
            if texto == _ASTERISCO:
                return DERIVADO
            raise ValueError("símbolo inesperado %r" % texto)
        if especie == "txt":
            return decodificar_texto(texto[1:-1])
        if especie == "ref":
            return Ref(int(texto[1:]))
        if especie == "num":
            if "." in texto or "e" in texto or "E" in texto:
                return float(texto)
            return int(texto)
        if especie == "enum":
            nome = texto[1:-1]
            if nome == "T":
                return True
            if nome == "F":
                return False
            if nome == "U":
                return None
            return Enumeracao(nome)
        if especie == "bin":
            return texto[1:-1]
        if especie == "ident":
            prox = self.olhar()
            if prox and prox[1] == _ABRE:
                self.i += 1
                return Tipado(texto.upper(), self.lista())
            return Enumeracao(texto.upper())      # palavra solta: trata como enum
        raise ValueError("token inesperado %r" % texto)

    def lista(self) -> list:
        """Lê os elementos até o `)` — o `(` já foi consumido."""
        itens: list = []
        prox = self.olhar()
        if prox and prox[1] == _FECHA:
            self.i += 1
            return itens
        while True:
            itens.append(self.valor())
            especie, texto = self.pegar()
            if texto == _FECHA:
                return itens
            if texto != _VIRGULA:
                raise ValueError("esperado ',' ou ')', veio %r" % texto)

    # ---- corpo de entidade ----
    def corpo(self) -> Tuple[str, list, Optional[List[Tipado]]]:
        especie, texto = self.pegar()
        if especie == "ident":
            self.exigir(_ABRE)
            return texto.upper(), self.lista(), None
        if texto == _ABRE:
            # instanciação complexa: (IFCX(...)IFCY(...))
            partes: List[Tipado] = []
            while True:
                prox = self.olhar()
                if prox is None:
                    raise ValueError("instanciação complexa não fechada")
                if prox[1] == _FECHA:
                    self.i += 1
                    break
                especie, nome = self.pegar()
                if especie != "ident":
                    raise ValueError("esperado nome de tipo, veio %r" % nome)
                self.exigir(_ABRE)
                partes.append(Tipado(nome.upper(), self.lista()))
                prox = self.olhar()
                if prox and prox[1] == _VIRGULA:   # alguns escritores separam por vírgula
                    self.i += 1
            if not partes:
                raise ValueError("instanciação complexa vazia")
            return partes[0].tipo, partes[0].args, partes
        raise ValueError("corpo de entidade inesperado: %r" % texto)


# --------------------------------------------------------------- arquivo

class Arquivo:
    """O conteúdo de um arquivo STEP já analisado."""

    def __init__(self, caminho: str = ""):
        self.caminho = caminho
        self.cabecalho: Dict[str, list] = {}
        self.entidades: Dict[int, Entidade] = {}
        self.avisos: List[str] = []
        self.truncado = False
        self._indice: Optional[Dict[str, List[Entidade]]] = None
        self._inversos: Optional[Dict[int, List[int]]] = None

    # ---- cabeçalho ----
    @property
    def schema(self) -> str:
        """Nome do esquema declarado em FILE_SCHEMA, por exemplo 'IFC4'."""
        args = self.cabecalho.get("FILE_SCHEMA") or []
        if args and isinstance(args[0], list) and args[0]:
            return str(args[0][0])
        return ""

    @property
    def descricao(self) -> List[str]:
        args = self.cabecalho.get("FILE_DESCRIPTION") or []
        return [str(x) for x in (args[0] if args and isinstance(args[0], list) else [])]

    @property
    def aplicacao(self) -> str:
        """Programa que escreveu o arquivo: originating_system de FILE_NAME.

        Cai para preprocessor_version quando o campo está vazio, que é o que vários
        exportadores fazem.
        """
        args = self.cabecalho.get("FILE_NAME") or []
        for i in (5, 4):
            if len(args) > i and args[i]:
                return str(args[i])
        return ""

    @property
    def nome_original(self) -> str:
        args = self.cabecalho.get("FILE_NAME") or []
        return str(args[0]) if args and args[0] else ""

    # ---- consultas ----
    def __len__(self) -> int:
        return len(self.entidades)

    def __iter__(self) -> Iterator[Entidade]:
        return iter(self.entidades.values())

    def __contains__(self, id_) -> bool:
        return int(id_) in self.entidades

    def _garantir_indice(self):
        if self._indice is None:
            idx: Dict[str, List[Entidade]] = {}
            for e in self.entidades.values():
                if e.partes:
                    for p in e.partes:
                        idx.setdefault(p.tipo, []).append(e)
                else:
                    idx.setdefault(e.tipo, []).append(e)
            self._indice = idx

    def por_tipo(self, *tipos: str) -> List[Entidade]:
        """Entidades de um ou mais tipos, sem diferenciar maiúsculas."""
        self._garantir_indice()
        if len(tipos) == 1:
            return list(self._indice.get(tipos[0].upper(), ()))
        vistos, fora = set(), []
        for t in tipos:
            for e in self._indice.get(t.upper(), ()):
                if e.id not in vistos:
                    vistos.add(e.id)
                    fora.append(e)
        return fora

    def contagem_por_tipo(self) -> Dict[str, int]:
        self._garantir_indice()
        return {t: len(v) for t, v in sorted(self._indice.items())}

    def tipos(self) -> List[str]:
        self._garantir_indice()
        return sorted(self._indice)

    def resolver(self, ref) -> Optional[Entidade]:
        """Entidade apontada por uma `Ref` (ou por um id inteiro). None se não existe."""
        if isinstance(ref, Entidade):
            return ref
        if isinstance(ref, int) and not isinstance(ref, bool):
            return self.entidades.get(int(ref))
        return None

    def resolver_lista(self, refs) -> List[Entidade]:
        """Resolve uma lista de referências, pulando as que não existem."""
        if not refs:
            return []
        if not isinstance(refs, (list, tuple)):
            refs = [refs]
        fora = []
        for r in refs:
            e = self.resolver(r)
            if e is not None:
                fora.append(e)
        return fora

    # ---- referências inversas ----
    def _garantir_inversos(self):
        if self._inversos is not None:
            return
        inv: Dict[int, List[int]] = {}
        for e in self.entidades.values():
            origem = e.id
            pilha = list(e.args)
            while pilha:
                v = pilha.pop()
                if type(v) is Ref:
                    lst = inv.get(int(v))
                    if lst is None:
                        inv[int(v)] = [origem]
                    elif lst[-1] != origem:
                        lst.append(origem)
                elif isinstance(v, list):
                    pilha.extend(v)
                elif isinstance(v, Tipado):
                    pilha.extend(v.args)
        self._inversos = inv

    def inversos(self, id_) -> List[Entidade]:
        """Entidades que referenciam esta — o caminho para achar as relações do IFC."""
        if isinstance(id_, Entidade):
            id_ = id_.id
        self._garantir_inversos()
        ents = self.entidades
        return [ents[i] for i in self._inversos.get(int(id_), ()) if i in ents]

    def inversos_tipo(self, id_, *tipos: str) -> List[Entidade]:
        alvos = {t.upper() for t in tipos}
        return [e for e in self.inversos(id_) if alvos.intersection(e.tipos)]

    # ---- diagnóstico ----
    def avisar(self, msg: str):
        if len(self.avisos) < MAX_AVISOS:
            self.avisos.append(msg)
        elif len(self.avisos) == MAX_AVISOS:
            self.avisos.append("... mais avisos omitidos")

    def __repr__(self) -> str:
        return "<Arquivo %s: %d entidades, esquema %s>" % (
            os.path.basename(self.caminho) or "(texto)", len(self.entidades),
            self.schema or "?")


# --------------------------------------------------------------- varredura por streaming

def _instrucoes(linhas: Iterable[str]) -> Iterator[Tuple[str, bool]]:
    """Quebra um fluxo de linhas em instruções (o que vem antes de cada `;`).

    Respeita literais de texto e comentários `/* */`, ambos podendo atravessar linhas.
    O último item vem com `completa=False` quando o arquivo acabou no meio de uma
    instrução — é assim que um arquivo truncado é detectado.
    """
    buf: List[str] = []
    em_texto = False
    em_comentario = False
    for linha in linhas:
        i, n, inicio = 0, len(linha), 0
        while i < n:
            c = linha[i]
            if em_comentario:
                if c == "*" and i + 1 < n and linha[i + 1] == "/":
                    em_comentario = False
                    i += 2
                    inicio = i
                    continue
                i += 1
                continue
            if em_texto:
                if c == "'":
                    if i + 1 < n and linha[i + 1] == "'":
                        i += 2
                        continue
                    em_texto = False
                i += 1
                continue
            if c == "'":
                em_texto = True
                i += 1
                continue
            if c == "/" and i + 1 < n and linha[i + 1] == "*":
                buf.append(linha[inicio:i])
                em_comentario = True
                i += 2
                inicio = i
                continue
            if c == ";":
                buf.append(linha[inicio:i])
                yield "".join(buf), True
                buf = []
                i += 1
                inicio = i
                continue
            i += 1
        if not em_comentario:
            buf.append(linha[inicio:n])
            # a quebra física vira espaço, para não colar dois tokens; dentro de um
            # literal ela é conteúdo e vai como está.
            buf.append("\n" if em_texto else " ")
    resto = "".join(buf).strip()
    if resto:
        yield resto, False


_RE_ATRIB = re.compile(r"^\s*#([0-9]+)\s*=\s*(.*)$", re.S)
_MARCAS = {"ISO-10303-21": "inicio", "END-ISO-10303-21": "fim", "HEADER": "cabecalho",
           "DATA": "dados", "ENDSEC": "nenhuma"}


def _analisar_fluxo(linhas: Iterable[str], arq: Arquivo, so_cabecalho=False) -> Arquivo:
    secao = "dados"        # sem marcação explícita, assume seção de dados
    for bruto, completa in _instrucoes(linhas):
        texto = bruto.strip()
        if not texto:
            continue
        if not completa:
            arq.truncado = True
            arq.avisar("arquivo truncado: a última instrução não termina com ';' (%s...)"
                       % texto[:60].replace("\n", " "))
            break
        marca = _MARCAS.get(texto.upper())
        if marca is not None:
            if marca == "fim":
                break
            if marca in ("cabecalho", "dados", "nenhuma"):
                if marca == "dados" and so_cabecalho:
                    break
                secao = marca
            continue
        m = _RE_ATRIB.match(texto)
        try:
            if m:
                if secao == "cabecalho" or so_cabecalho:
                    continue
                ident = int(m.group(1))
                tipo, args, partes = _Analisador(_tokens(m.group(2))).corpo()
                if ident in arq.entidades:
                    arq.avisar("id repetido #%d: a última definição prevalece" % ident)
                arq.entidades[ident] = Entidade(ident, tipo, args, partes)
            else:
                tokens = _tokens(texto)
                if not tokens:
                    continue
                nome, args, _ = _Analisador(tokens).corpo()
                if secao == "cabecalho":
                    arq.cabecalho[nome] = args
                # instrução sem `#id` fora do cabeçalho: não há onde guardar
        except ValueError as erro:
            arq.avisar("instrução ignorada (%s): %s" % (erro, texto[:80].replace("\n", " ")))
    arq._indice = None
    arq._inversos = None
    return arq


# --------------------------------------------------------------- API

def _codificacao(caminho: str) -> str:
    """Descobre a codificação olhando o começo do arquivo.

    A ISO 10303-21 só admite ASCII, mas muitos programas gravam UTF-8 direto e alguns
    gravam ISO-8859-1. Testar os primeiros blocos resolve os dois casos.
    """
    try:
        with open(caminho, "rb") as f:
            amostra = f.read(262144)
    except OSError:
        return "utf-8"
    if amostra.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def ler(caminho: str, *, so_cabecalho: bool = False,
        codificacao: Optional[str] = None) -> Arquivo:
    """Lê um arquivo STEP/IFC e devolve o `Arquivo`.

    `so_cabecalho=True` para quando basta saber esquema e autor: para a leitura no
    começo da seção DATA, o que torna a consulta instantânea mesmo num arquivo enorme.
    """
    if not os.path.isfile(caminho):
        raise ErroStep("arquivo não encontrado: %s" % caminho)
    arq = Arquivo(caminho)
    cod = codificacao or _codificacao(caminho)
    with open(caminho, "r", encoding=cod, errors="replace", newline="") as f:
        _analisar_fluxo(f, arq, so_cabecalho=so_cabecalho)
    return arq


def ler_texto(texto: str, caminho: str = "", *, so_cabecalho: bool = False) -> Arquivo:
    """Mesma leitura, a partir de uma string — útil em testes."""
    arq = Arquivo(caminho)
    _analisar_fluxo(texto.splitlines(True), arq, so_cabecalho=so_cabecalho)
    return arq


def ler_cabecalho(caminho: str) -> Arquivo:
    """Só o cabeçalho: esquema, autor e programa de origem."""
    return ler(caminho, so_cabecalho=True)
