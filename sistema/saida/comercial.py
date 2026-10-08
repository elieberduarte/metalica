# -*- coding: utf-8 -*-
"""Área comercial da obra: proposta técnica comercial, contrato, etapas da obra, parcelas e aditivos.

O fluxo da empresa (levantado em 03/10/2026 das propostas e contratos de 2026): orçamento (resumo)
→ proposta técnica comercial (R00, R01…) → negociação → pedido de obra / aceite → contrato de
empreitada global → sinal → projeto executivo → compras → fabricação → expedição → montagem →
termo de aceite → garantia. Tudo de uma obra fica em ``<projeto>/comercial/comercial.json``:

* ``proposta`` — os campos da proposta (cliente, obra, geometria, escopo por área, condições,
  exclusões, responsabilidades, investimento, pagamento, prazo, validade, imagens 3D) e as revisões;
* ``contrato`` — contratante qualificado, valor negociado, parcelas, prazo, multas, cláusulas
  opcionais, testemunhas, situação (minuta/assinado) e os aditivos;
* ``etapas`` — a linha do tempo da obra, com previsto/realizado, responsável e observação.

Os dados da empresa (razão social, CNPJ, banco, representante, logo, cores) ficam em
``<dados>/fabrica/empresa.json`` e ``<dados>/fabrica/marca/`` — fora do repositório, que é público.
Os textos-padrão (condições, exclusões, cláusulas) são os das propostas e contratos da empresa,
com os erros que se repetiam nos modelos corrigidos (ver ``CORRECOES``).
"""
import copy
import json
import math
import os
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

PASTA = "comercial"
ARQ = "comercial.json"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

# ============================================================ números por extenso

_UN = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze",
       "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos",
        "novecentos"]


def _ate_mil(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    partes = []
    if c:
        partes.append(_CEM[c])
    if r:
        if r < 20:
            partes.append(_UN[r])
        else:
            d, u = divmod(r, 10)
            partes.append(_DEZ[d] + (" e " + _UN[u] if u else ""))
    return " e ".join(partes)


def extenso_inteiro(n: int) -> str:
    if n == 0:
        return "zero"
    grupos = []
    while n:
        n, g = divmod(n, 1000)
        grupos.append(g)
    nomes = [("", ""), ("mil", "mil"), ("milhão", "milhões"), ("bilhão", "bilhões")]
    partes = []
    for i in range(len(grupos) - 1, -1, -1):
        g = grupos[i]
        if not g:
            continue
        txt = "" if (i == 1 and g == 1) else _ate_mil(g)
        sing, plur = nomes[i]
        nome = (sing if g == 1 else plur) if i else ""
        partes.append((txt + " " + nome).strip())
    # "e" antes do último grupo quando ele é menor que 100 ou redondo em centenas (mil e cem; dois mil e quinhentos)
    if len(partes) > 1:
        ultimo = next(g for g in grupos if g)          # o último grupo que não é zero (dois milhões e sessenta mil)
        if ultimo < 100 or ultimo % 100 == 0:
            return ", ".join(partes[:-1]) + " e " + partes[-1]
    return ", ".join(partes)


def extenso_reais(valor: float) -> str:
    """42250 → 'quarenta e dois mil, duzentos e cinquenta reais'; com centavos quando houver."""
    valor = round(float(valor or 0), 2)
    inteiro = int(valor)
    cent = int(round((valor - inteiro) * 100))
    partes = []
    if inteiro:
        txt = extenso_inteiro(inteiro)
        de = " de" if inteiro % 1_000_000 == 0 else ""
        partes.append("%s%s %s" % (txt, de, "real" if inteiro == 1 else "reais"))
    if cent:
        partes.append("%s %s" % (extenso_inteiro(cent), "centavo" if cent == 1 else "centavos"))
    return " e ".join(partes) or "zero reais"


def reais(v, casas: int = 2) -> str:
    if v is None or v == "":
        return ""
    s = "{:,.{c}f}".format(float(v), c=casas)
    return "R$ " + s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def num(v, casas: int = 2) -> str:
    if v is None or v == "":
        return ""
    s = "{:,.{c}f}".format(float(v), c=casas)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def data_extenso(d: Optional[date] = None, maiuscula: bool = True) -> str:
    d = d or date.today()
    mes = MESES[d.month - 1]
    return "%02d de %s de %d" % (d.day, mes.capitalize() if maiuscula else mes, d.year)


def ler_data(txt) -> Optional[date]:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", str(txt or ""))
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(txt or ""))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _f(x) -> Optional[float]:
    if x is None or x == "":
        return None
    if isinstance(x, (int, float)):
        return float(x)
    t = str(x).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


# ============================================================ empresa

EMPRESA_PADRAO = {
    "razao_social": "", "nome_comercial": "", "cnpj": "", "ie": "", "endereco": "", "bairro": "", "cidade": "", "uf": "",
    "cep": "", "telefone": "", "email": "", "site": "", "slogan": "",
    "representante": {"nome": "", "qualificacao": "brasileiro, casado, sócio administrador"},
    "responsavel_tecnico": {"nome": "", "registro": ""},
    "banco": {"banco": "", "agencia": "", "conta": ""},
    "cores": {"primaria": "#35434C", "destaque": "#C3D773"},
    "apresentacao": "Fabricamos, transportamos e montamos estruturas metálicas com engenharia própria — do projeto à "
                    "entrega da obra, com equipe de montagem e fábrica dedicadas.",
    "diferenciais": ["Projeto e cálculo por profissional habilitado, conforme as normas brasileiras",
                     "Fabricação própria com controle de cada peça, do corte à pintura",
                     "Montagem com equipe própria, caminhão munck e plataformas de trabalho em altura",
                     "Modelo 3D da estrutura antes da fabricação: o que você vê é o que será montado"],
    "foro": "",
}


def pasta_marca(dados: str) -> str:
    return os.path.join(dados, "fabrica", "marca")


def ler_empresa(dados: str) -> dict:
    e = copy.deepcopy(EMPRESA_PADRAO)
    try:
        with open(os.path.join(dados, "fabrica", "empresa.json"), encoding="utf-8") as f:
            lido = json.load(f)
        for k, v in lido.items():
            if isinstance(v, dict) and isinstance(e.get(k), dict):
                e[k].update(v)
            else:
                e[k] = v
    except (OSError, ValueError):
        pass
    marca = pasta_marca(dados)
    for chave, nomes in (("logo", ("logo.png", "logo.jpg")), ("logo_claro", ("logo_claro.png",)), ("rodape", ("rodape.png", "rodape.jpg"))):
        e[chave] = next((os.path.join(marca, n) for n in nomes if os.path.exists(os.path.join(marca, n))), "")
    return e


def gravar_empresa(dados: str, empresa: dict) -> dict:
    pasta = os.path.join(dados, "fabrica")
    os.makedirs(pasta, exist_ok=True)
    limpo = {k: v for k, v in (empresa or {}).items() if k in EMPRESA_PADRAO}
    with open(os.path.join(pasta, "empresa.json"), "w", encoding="utf-8") as f:
        json.dump(limpo, f, ensure_ascii=False, indent=1)
    return ler_empresa(dados)


def proximo_numero(dados: str, ano: Optional[int] = None) -> str:
    """Número de controle da proposta: AAAA-NNN (sequência por ano, em <dados>/fabrica/comercial-seq.json)."""
    ano = ano or date.today().year
    cam = os.path.join(dados, "fabrica", "comercial-seq.json")
    try:
        with open(cam, encoding="utf-8") as f:
            seq = json.load(f)
    except (OSError, ValueError):
        seq = {}
    n = int(seq.get(str(ano), 0)) + 1
    seq[str(ano)] = n
    os.makedirs(os.path.dirname(cam), exist_ok=True)
    with open(cam, "w", encoding="utf-8") as f:
        json.dump(seq, f)
    return "%d-%03d" % (ano, n)


# ============================================================ textos-padrão (propostas e contratos da empresa)

ESCOPO_INTRO = ("Nosso escopo compreende a fabricação, transporte e montagem de estrutura metálica, além de serviços de "
                "engenharia necessários para entrega do escopo conforme segue.")
PROJETO_HERMES = "O projeto da estrutura metálica será elaborado por profissional habilitado, atendendo as normas brasileiras vigentes."
PROJETO_CLIENTE = ("Este orçamento foi baseado nos projetos e quantitativos fornecidos pelo cliente; qualquer divergência "
                   "posterior implicará a revisão desta proposta.")

CONDICOES_GERAIS = [
    "A estrutura metálica será confeccionada em perfis metálicos de aço com tensão de escoamento maior ou igual a "
    "3.000 kgf/cm² em perfis laminados ASTM A-36.",
    "Este orçamento considerou alíquota referente ao ISSQN de 3% sobre o valor da mão de obra (10% do valor total da "
    "proposta). Qualquer diferença nesta alíquota, o pagamento será de responsabilidade do contratante.",
]
SEGURANCA = [
    "Relação de equipamentos de proteção individual a serem utilizados: uniforme, botina, cinto de segurança, capacete, "
    "luvas, protetores auriculares, óculos de proteção, máscara para solda.",
    "Programa de Gerenciamento de Riscos (PGR) e Programa de Controle Médico de Saúde Ocupacional (PCMSO), conforme "
    "previsto pela legislação, especialmente para atender o previsto pela NR-7 do Ministério do Trabalho e Emprego.",
]
EXCLUSOES = [
    "Instalação de chumbadores e insertos metálicos e todos os serviços em concreto armado, pré-moldado, piso e alvenaria "
    "(inclusive fundações e todos os materiais necessários);",
    "Plano de rigging para içamento, movimentação e posicionamento da estrutura metálica;",
    "Fornecimento e instalação de condutores para águas pluviais e projeto pluvial;",
    "Todos e quaisquer itens que não são descritos neste orçamento como portas, portões, forro, escadas, escadas "
    "marinheiro, guarda-corpo, linha de vida etc.",
]
EXCLUSOES_OPCIONAIS = [
    "Fornecimento do projeto executivo de fabricação/montagem da estrutura metálica;",
    "Fornecimento e instalação do ACM, inclusive estrutura auxiliar para fixação, acessórios de fixação, vedações e acabamentos;",
    "Fornecimento e instalação de equipamentos como SPK e placas fotovoltaicas, inclusive estruturas auxiliares para fixação dos mesmos;",
    "Fornecimento e instalação de calhas e rufos para vedação e acabamento de todas as coberturas;",
    "Fornecimento das telhas das coberturas;",
    "Fornecimento de munck e/ou PTA para içamento e montagem de toda a estrutura metálica e montagem das telhas da cobertura;",
    "Fornecimento do guindaste e/ou grua para içamento de toda a estrutura metálica até seu ponto de instalação;",
    "Ensaios não destrutivos de líquido penetrante (LP) e ultrassom (US);",
]
RESPONSABILIDADES = [
    "Fornecimento de energia elétrica trifásica (220 V – 100 A) no canteiro de obras;",
    "Fornecimento de local na obra, com revestimento em BTG (brita graduada), para armazenamento da estrutura metálica;",
    "Adequadas condições de acesso, niveladas e compactadas, com revestimento em BTG (brita graduada) em áreas de acesso/montagem;",
    "Legalização da obra e projetos junto aos órgãos e autarquias pertinentes, Municipal (ISSQN), Estadual e Federal;",
    "Permissão de livre acesso dos equipamentos de montagem e do pessoal (equipe de montagem) ao local de trabalho;",
    "Fornecimento de áreas de convívio como: banheiros, refeitório, entre outros obrigatórios constantes na norma regulamentadora NR-18;",
    "Solicitações de autorizações junto aos órgãos competentes para uso da via e/ou passeio público;",
    "Segurança e vigilância do canteiro de obras, inclusive nos finais de semana e feriados, assumindo a responsabilidade "
    "de qualquer ocorrência de dano, extravio e/ou roubo de equipamentos e materiais;",
    "Solicitação junto à COPEL ou empresa responsável, caso necessário, de desligamento de rede de energia ou trabalho em linha viva;",
    "Fornecimento de caçamba para retirada de resíduos e entulhos da obra, quando necessário.",
]
NOTA_ANTIDUMPING = ("*Os valores desta proposta estão sujeitos a reajuste em caso de alterações legais, tributárias ou "
                    "governamentais, especialmente decorrentes da aplicação ou modificação da Lei Antidumping, que impactem "
                    "o custo dos materiais e insumos, não sendo tais variações de responsabilidade da proponente.")
NOTA_DIFAL = ("*Não está incluso nesta proposta qualquer valor referente ao diferencial de ICMS que possa existir em função "
              "da venda para o estado {estado}.")
CARREGAMENTOS_PADRAO = [
    {"carga": "7,00 kgf/m²", "descricao": "Telha singela"},
    {"carga": "25,00 kgf/m²", "descricao": "Sobrecarga acidental (norma)"},
    {"carga": "-", "descricao": "Fotovoltaica"},
    {"carga": "-", "descricao": "SPK"},
    {"carga": "-", "descricao": "Forro"},
    {"carga": "-", "descricao": "Outros"},
]
ESTADOS = {"AC": "do Acre", "AL": "de Alagoas", "AP": "do Amapá", "AM": "do Amazonas", "BA": "da Bahia", "CE": "do Ceará",
           "DF": "do Distrito Federal", "ES": "do Espírito Santo", "GO": "de Goiás", "MA": "do Maranhão", "MT": "do Mato Grosso",
           "MS": "do Mato Grosso do Sul", "MG": "de Minas Gerais", "PA": "do Pará", "PB": "da Paraíba", "PR": "do Paraná",
           "PE": "de Pernambuco", "PI": "do Piauí", "RJ": "do Rio de Janeiro", "RN": "do Rio Grande do Norte",
           "RS": "do Rio Grande do Sul", "RO": "de Rondônia", "RR": "de Roraima", "SC": "de Santa Catarina", "SP": "de São Paulo",
           "SE": "de Sergipe", "TO": "do Tocantins"}

#: Etapas da obra, na ordem (chave, nome, o que marca a etapa).
ETAPAS = [
    ("orcamento", "Orçamento", "resumo de orçamento fechado"),
    ("proposta", "Proposta enviada", "proposta técnica comercial enviada ao cliente"),
    ("negociacao", "Negociação", "revisões, desconto e forma de pagamento"),
    ("aprovacao", "Aprovação / pedido de obra", "proposta aceita ou pedido de obra assinado"),
    ("contrato", "Contrato assinado", "contrato de empreitada assinado pelas partes"),
    ("sinal", "Sinal recebido", "entrada na conta — só então compra de aço e fabricação"),
    ("projeto", "Projeto executivo aprovado", "projeto de fabricação liberado"),
    ("compras", "Compras", "aço, telhas e acessórios pedidos"),
    ("fabricacao", "Fabricação", "corte, solda, furação"),
    ("pintura", "Pintura e expedição", "decapagem, pintura e carregamento"),
    ("montagem", "Montagem", "equipe na obra"),
    ("entrega", "Entrega / termo de aceite", "termo de aceite assinado pelo contratante"),
    ("garantia", "Garantia", "acompanhamento pós-obra"),
]
SITUACOES = ("pendente", "andamento", "concluida")

#: O que o contrato gerado corrige em relação aos modelos usados até 09/2026.
CORRECOES = [
    "o parágrafo do INSS cita a cláusula do preço (Segunda), não a Quinta;",
    "sem a frase de fecho repetida, sem citar \"Condições Gerais\" e \"Acordo de Confidencialidade\" que não existem;",
    "arras limitadas ao valor do contrato e só quando informadas;",
    "\"elaborar os projetos\" só quando o projeto é da contratada;",
    "parcelas somam o preço e não podem vencer antes da assinatura (avisado);",
    "CNPJ com a máscara completa; datas do ano corrente.",
]


# ============================================================ estado da obra

def caminho(pasta_projeto: str) -> str:
    return os.path.join(pasta_projeto, PASTA, ARQ)


def ler(pasta_projeto: str) -> dict:
    try:
        with open(caminho(pasta_projeto), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("proposta", {})
    d.setdefault("contrato", {})
    d.setdefault("etapas", {})
    d.setdefault("historico", [])
    return d


def gravar(pasta_projeto: str, estado: dict) -> dict:
    os.makedirs(os.path.join(pasta_projeto, PASTA), exist_ok=True)
    cam = caminho(pasta_projeto)
    estado = dict(estado)
    estado["alterado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(cam + ".parcial", "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    os.replace(cam + ".parcial", cam)
    return estado


def registrar(estado: dict, texto: str) -> None:
    estado.setdefault("historico", []).append({"quando": datetime.now().strftime("%Y-%m-%d %H:%M"), "texto": texto})
    estado["historico"] = estado["historico"][-200:]


# ============================================================ proposta: valores iniciais

def _cidade_uf(local: str):
    m = re.match(r"\s*(.*?)\s*[-–/]\s*([A-Za-z]{2})\s*$", str(local or ""))
    return (m.group(1), m.group(2).upper()) if m else (str(local or "").strip(), "")


def escopo_sugerido(lista: dict, orc: Optional[dict], numeros: Optional[dict], projeto_por: str) -> List[dict]:
    """Os itens da "Estrutura Metálica" na redação da empresa, a partir da lista de materiais, do resumo da obra
    e do orçamento (o usuário revisa)."""
    pos = (lista or {}).get("posicoes") or []
    cats = {str(p.get("categoria") or "") for p in pos}
    acess = " ".join(str(a.get("nome") or "") for a in (lista or {}).get("acessorios") or []).upper()
    nr = (numeros or {}).get("numeros") or {}
    trechos = ((numeros or {}).get("dimensoes") or {}).get("trechos") or []
    linhas_orc = (orc or {}).get("linhas") or []
    itens: List[dict] = []

    def add(texto, destaque=False):
        itens.append({"texto": texto, "destaque": destaque})

    if projeto_por == "cliente":
        peso = (orc or {}).get("totais", {}).get("aco_kg")
        add("Fabricação de toda a estrutura metálica conforme projetos e quantitativos fornecidos pelo cliente%s;"
            % ((" (%s kg)" % num(peso, 2)) if peso else ""))
    if "CHUMBADOR" in acess or any("chumb" in str(p.get("perfil") or "").lower() for p in pos):
        add("Placas de apoio e chumbadores metálicos para fixação de toda a estrutura metálica;")
    n_tes = int(nr.get("tesouras") or 0)
    if n_tes:
        vao = max((float(t.get("vao") or 0) for t in trechos), default=0.0) / 1000.0
        add("%02d Tesouras metálicas treliçadas%s, compostas por banzos em perfil U e treliçamento em perfil U;"
            % (n_tes, (" com %sm" % num(vao, 2)) if vao else ""))
    if "TERÇAS" in cats:
        add("Terças em perfil U para toda a cobertura;")
    if "TIRANTES" in cats:
        add("Agulhamento para enrijecimento das terças metálicas de cobertura;")
    if n_tes:
        add("Contraventamento para travamento das tesouras metálicas;")
    add("Decapagem química para preparação da estrutura;")
    add("Pintura da estrutura metálica em tinta esmalte sintético cinza N6,5, aplicada sob alta pressão;")
    tem_telha = False
    for li in linhas_orc:
        if li.get("oculta") or li.get("grupo") != "telhas":
            continue
        d = str(li.get("descricao") or "")
        if d.lower().startswith("telha"):
            tem_telha = True
            m = re.search(r"0[.,](\d{2})", d)
            esp = ("0,%smm " % m.group(1)) if m else ""
            add("Telha trapezoidal TP40 %sem aço galvalume para a cobertura;" % esp, True)
        elif d.lower().startswith("multidobra"):
            add("Telha multidobra TP40 em aço galvalume para a cobertura;", True)
        elif d.lower().startswith("cumeeira"):
            add("Cumeeira trapezoidal TP40 em aço galvalume para a cobertura;", True)
        elif d.lower().startswith("rufos"):
            add("Rufos em chapa de aço galvalume para vedação e acabamento;")
        elif d.lower().startswith("calhas"):
            add("Calha metálica em chapa de aço galvalume para a cobertura, com emendas sobrepostas parafusadas e vedadas, "
                "com saídas simples com diâmetros conforme projeto específico, sem funis e/ou vórtex;")
    add("Acessórios de fixação para estrutura metálica (PARAFUSOS);")
    if tem_telha:
        add("Acessórios de fixação das telhas metálicas e instalação das mesmas;")
        add("Fita TACKY-TAPE HARD para vedação na sobreposição das telhas metálicas da cobertura;")
    add("Equipamentos de montagem como caminhão munck e plataformas de trabalho em altura (PTA);")
    return itens


def proposta_inicial(projeto: dict, lista: dict, orc: Optional[dict], numeros: Optional[dict], empresa: dict,
                     numero: str = "", hoje: Optional[date] = None) -> dict:
    hoje = hoje or date.today()
    cid, uf = _cidade_uf(projeto.get("local") or "")
    cab = (orc or {}).get("cabecalho") or {}
    tot = (orc or {}).get("totais") or {}
    dims = (numeros or {}).get("dimensoes") or {}
    geometria = []
    for t in dims.get("trechos") or []:
        pj = t.get("projecao") or [0, 0]
        L, C = float(pj[1] or 0) / 1000.0, float(pj[0] or 0) / 1000.0
        if L and C:
            geometria.append({"nome": str(t.get("nome") or "Cobertura"), "largura": round(L, 2), "comprimento": round(C, 2),
                              "area": round(L * C, 2)})
    if not geometria and (cab.get("area_m2") or dims.get("area_m2")):
        geometria.append({"nome": "Cobertura", "largura": None, "comprimento": None,
                          "area": round(float(cab.get("area_m2") or dims.get("area_m2")), 2)})
    projeto_por = "cliente" if str(projeto.get("tipo") or "") == "ifc" else "hermes"
    valor = tot.get("fechamento") or None
    return {
        "numero": numero, "revisao": "R00", "data": hoje.strftime("%d/%m/%Y"), "validade_dias": 15,
        "cidade_emissao": "%s, %s" % (empresa.get("cidade") or "", empresa.get("uf") or "") if empresa.get("cidade") else "",
        "cliente": {"nome": projeto.get("cliente") or "", "contato": "", "cidade": cid, "uf": uf, "email": "", "telefone": ""},
        "obra": {"nome": projeto.get("nome") or "", "cidade": cid, "uf": uf},
        "ref": "Proposta para execução da estrutura metálica de cobertura.",
        "opcao": cab.get("opcao") or "",
        "projeto_por": projeto_por,
        "carregamentos": copy.deepcopy(CARREGAMENTOS_PADRAO) if projeto_por == "hermes" else [],
        "geometria": geometria,
        "peso_kg": tot.get("aco_kg"),
        "escopo": [{"titulo": "Cobertura", "itens": escopo_sugerido(lista, orc, numeros, projeto_por)}],
        "condicoes": list(CONDICOES_GERAIS) + ([PROJETO_CLIENTE] if projeto_por == "cliente" else []),
        "seguranca": list(SEGURANCA),
        "exclusoes": list(EXCLUSOES),
        "responsabilidades": list(RESPONSABILIDADES),
        "investimento": {"valor": round(valor, 2) if valor else None, "partes": [], "opcionais": [],
                         "notas": [NOTA_DIFAL.format(estado=ESTADOS[uf])] if uf and uf != (empresa.get("uf") or "PR") and uf in ESTADOS else []},
        "pagamento": "A combinar.",
        "parcelas": [],
        "prazo": "A combinar.",
        "prazos_etapas": {"projeto": None, "fabricacao": None, "montagem": None},
        "imagens": [],
        "mostrar_ficha": True,
        "revisoes": [],
    }


def avisos_proposta(P: dict) -> List[str]:
    av = []
    inv = P.get("investimento") or {}
    if not _f(inv.get("valor")):
        av.append("Sem valor de investimento: preencha o fechamento no orçamento ou digite o valor aqui.")
    if not (P.get("cliente") or {}).get("nome"):
        av.append("Sem o nome do cliente.")
    if not (P.get("obra") or {}).get("cidade"):
        av.append("Sem a cidade da obra.")
    soma = sum(_f(p.get("valor")) or 0 for p in P.get("parcelas") or [])
    if P.get("parcelas") and _f(inv.get("valor")) and abs(soma - _f(inv.get("valor"))) > 0.5:
        av.append("As parcelas somam %s e o investimento é %s." % (reais(soma), reais(inv.get("valor"))))
    if not P.get("imagens"):
        av.append("Sem imagens do modelo 3D (use \"Gerar imagens do 3D\").")
    return av


# ============================================================ contrato

def contrato_inicial(P: dict, empresa: dict) -> dict:
    inv = P.get("investimento") or {}
    return {
        "situacao": "minuta", "revisao": "R00", "data": date.today().strftime("%d/%m/%Y"),
        "contratante": {"razao_social": (P.get("cliente") or {}).get("nome", ""), "cnpj": "", "ie": "", "endereco": "",
                        "cep": "", "cidade": (P.get("cliente") or {}).get("cidade", ""), "uf": (P.get("cliente") or {}).get("uf", ""),
                        "representante": "", "representante_qualificacao": "", "representante_cpf": ""},
        "objeto": "cobertura", "valor": inv.get("valor"),
        "parcelas": [{"descricao": p.get("descricao", ""), "vencimento": p.get("vencimento", ""), "valor": p.get("valor"),
                      "paga": False, "pago_em": ""} for p in (P.get("parcelas") or [])],
        "prazo_tipo": "dias", "prazo_dias": 90, "prazo_texto": "de acordo com o cronograma da obra acordado entre as partes",
        "arras": None, "desmobilizacao": 10000.0, "multa_mes": 1.0,
        "seguro_clima": True, "rigging_contratante": True, "pluviais_contratante": True,
        "reajuste_incc_parcela": None,
        "garantia": False,
        "foro": empresa.get("foro") or empresa.get("cidade") or "", "foro_uf": empresa.get("uf") or "",
        "cidade_assinatura": empresa.get("cidade") or "",
        "testemunhas": [{"nome": "", "cpf": ""}, {"nome": "", "cpf": ""}],
        "assinatura_meio": "",
        "assinado_em": "",
        "aditivos": [],
        "extras_contratante": [],
    }


def _ordinal(n: int) -> str:
    nomes = ["PRIMEIRA", "SEGUNDA", "TERCEIRA", "QUARTA", "QUINTA", "SEXTA", "SÉTIMA", "OITAVA", "NONA", "DÉCIMA",
             "DÉCIMA PRIMEIRA", "DÉCIMA SEGUNDA", "DÉCIMA TERCEIRA", "DÉCIMA QUARTA", "DÉCIMA QUINTA", "DÉCIMA SEXTA"]
    return nomes[n - 1] if 0 < n <= len(nomes) else str(n)


def _par(n: int) -> str:
    return ["PRIMEIRO", "SEGUNDO", "TERCEIRO", "QUARTO", "QUINTO", "SEXTO", "SÉTIMO", "OITAVO"][n - 1]


def clausulas_contrato(P: dict, C: dict, empresa: dict) -> List[dict]:
    """O contrato de empreitada global no modelo da empresa (versão de 30/09/2026), como blocos:
    {"titulo", "paragrafos": [texto|{"lista": [...]}|{"tabela": ...}]}. Trechos em **negrito** marcados com **."""
    ct = C.get("contratante") or {}
    valor = _f(C.get("valor")) or _f((P.get("investimento") or {}).get("valor")) or 0.0
    obra = P.get("obra") or {}
    cl: List[dict] = []

    # 1ª objeto
    corpo = ["Constitui objeto do presente contrato a execução de estrutura metálica de %s, em obra a ser executada na "
             "localidade de **%s**, conforme descritivo abaixo:" % (C.get("objeto") or "cobertura",
                                                                     " - ".join(x for x in (obra.get("cidade"), obra.get("uf")) if x))]
    geo = P.get("geometria") or []
    if geo:
        corpo.append("__Geometria das estruturas__")
        corpo.append({"lista": [_linha_geometria(g) for g in geo] + (["**Área total: %s m²**" % num(sum(_f(g.get('area')) or 0 for g in geo))]
                                                                      if len(geo) > 1 else [])})
    for bloco in P.get("escopo") or []:
        if bloco.get("titulo"):
            corpo.append("__%s__" % bloco["titulo"])
        corpo.append({"lista": [("**%s**" % i["texto"]) if i.get("destaque") else i["texto"] for i in bloco.get("itens") or [] if i.get("texto")]})
    corpo.append("**PARÁGRAFO PRIMEIRO:** Todos os materiais discriminados nas cláusulas acima deste instrumento serão por "
                 "conta única e exclusiva da CONTRATADA, exceto os materiais cujo fornecimento seja de responsabilidade da CONTRATANTE.")
    corpo.append("**PARÁGRAFO SEGUNDO:** A proposta técnica comercial nº %s %s, de %s, é parte integrante deste contrato; "
                 "havendo divergência, prevalece o disposto neste instrumento." % (P.get("numero") or "—", P.get("revisao") or "",
                                                                                   P.get("data") or "—"))
    cl.append({"titulo": "OBJETO DO CONTRATO", "paragrafos": corpo})

    # 2ª preço
    corpo = []
    parcelas = [p for p in C.get("parcelas") or [] if _f(p.get("valor"))]
    corpo.append("O preço certo e ajustado entre as partes é de **%s** (%s), que serão pagos pela CONTRATANTE%s"
                 % (reais(valor), extenso_reais(valor), " da seguinte forma:" if parcelas else "."))
    if parcelas:
        corpo.append({"lista": ["%s%s%s" % (reais(p.get("valor")), (" – " + p["descricao"]) if p.get("descricao") else "",
                                            (" – vencimento em %s" % p["vencimento"]) if p.get("vencimento") else "") for p in parcelas]})
    b = empresa.get("banco") or {}
    if b.get("banco"):
        corpo.append("**DADOS PARA DEPÓSITO:** %s – %s – %s, agência %s, conta corrente %s."
                     % (empresa.get("razao_social"), empresa.get("cnpj"), b.get("banco"), b.get("agencia"), b.get("conta")))
    n = 1
    corpo.append("**PARÁGRAFO %s:** Em conformidade com o previsto nos artigos 140 e seguintes da Instrução Normativa INSS/DC "
                 "nº 3, de 14 de julho de 2005, fica avençado entre as partes que 80%% (oitenta por cento) do valor previsto na "
                 "CLÁUSULA SEGUNDA deste contrato refere-se ao material aplicado, 10%% (dez por cento) refere-se à locação e "
                 "utilização de equipamentos sem operador e 10%% (dez por cento) refere-se à aplicação de mão de obra." % _par(n))
    n += 1
    corpo.append("**PARÁGRAFO %s:** Este contrato considerou alíquota referente ao ISSQN de 3%% sobre o valor da mão de obra "
                 "(10%% do valor total do contrato). Qualquer diferença nesta alíquota, o pagamento será de responsabilidade "
                 "da CONTRATANTE." % _par(n))
    arras = _f(C.get("arras"))
    if arras:
        arras = min(arras, valor) if valor else arras
        n += 1
        corpo.append("**PARÁGRAFO %s:** Em caso de desistência deste contrato por parte da CONTRATANTE, ter-se-á, do valor pago, "
                     "a importância de %s (%s) como arras confirmatórias, convertendo-se as mesmas em favor da CONTRATADA, sem "
                     "prejuízo das demais penalidades e indenizações previstas neste contrato para o caso de rescisão."
                     % (_par(n), reais(arras), extenso_reais(arras)))
    if C.get("reajuste_incc_parcela"):
        n += 1
        corpo.append("**PARÁGRAFO %s:** A partir da %sª parcela, o valor deverá ser corrigido mensalmente pela variação do INCC "
                     "do mês imediatamente anterior ao respectivo vencimento." % (_par(n), int(C["reajuste_incc_parcela"])))
    n += 1
    corpo.append("**PARÁGRAFO %s:** Todo e qualquer serviço adicional ou alteração de escopo a ser gerado por responsabilidade "
                 "da CONTRATANTE, por ela solicitado, ou ainda por alteração da técnica necessária à execução dos serviços e que "
                 "não for parte integrante deste contrato deverá ser objeto de Aditivo Contratual, a fim de contemplar valores, "
                 "prazos e demais condições técnicas e comerciais." % _par(n))
    cl.append({"titulo": "PREÇO", "paragrafos": corpo})

    # 3ª prazo
    if C.get("prazo_tipo") == "dias" and C.get("prazo_dias"):
        prazo = ("O prazo para execução do objeto deste contrato será de %d (%s) dias a contar da data de liberação de "
                 "montagem por parte da CONTRATANTE." % (int(C["prazo_dias"]), extenso_inteiro(int(C["prazo_dias"]))))
    else:
        prazo = "O prazo para execução do objeto deste contrato será %s." % (C.get("prazo_texto") or "de acordo com o cronograma da obra acordado entre as partes")
    cl.append({"titulo": "PRAZO", "paragrafos": [
        prazo,
        "**PARÁGRAFO PRIMEIRO:** O prazo deverá ser acrescido dos dias em que não seja possível a execução do objeto em função "
        "de intempéries e/ou motivos que não sejam de responsabilidade da CONTRATADA. Estes fatos devem constar, "
        "necessariamente, no diário de obras.",
        "**PARÁGRAFO SEGUNDO:** Consideram-se justificativas para o parágrafo primeiro tempestades, vendavais, ciclones, chuvas "
        "e outros eventos de natureza que gerem condições prejudiciais ao normal desenvolvimento dos serviços, assim como "
        "greves, boicotes, acentuada e notória falta ou escassez de materiais ou mão de obra no mercado e outras causas fora "
        "da vontade e do controle das partes, devendo a parte prejudicada pela ocorrência dessas causas comunicar o fato à "
        "outra parte, pelo diário de obras ou por simples e-mail, identificando as causas dos dias de atraso."]})

    # 4ª contratada
    itens = ["Executar o escopo deste presente contrato em sua totalidade, observando as boas práticas e normas vigentes;"]
    if P.get("projeto_por") != "cliente":
        itens.append("Elaborar todos os projetos referentes ao escopo deste contrato, observando as normas vigentes;")
    else:
        itens.append("Seguir em sua totalidade o projeto executivo fornecido pela CONTRATANTE;")
    itens += ["Fornecer mão de obra adequada e capacitada para execução do objeto;",
              "Fornecer todos os equipamentos de proteção individual (EPI) que se façam necessários para execução do objeto;",
              "Fornecer alojamento e alimentação para a equipe de montagem durante a execução do objeto;",
              "Assumir responsabilidade integral por qualquer espécie de indenização pleiteada por seus funcionários ou "
              "subcontratados envolvidos na prestação dos serviços contratados;",
              "No caso de subcontratação, responder perante a CONTRATANTE pela regularidade jurídica, fiscal e trabalhista da "
              "empresa subcontratada, assim como pela qualidade dos serviços, permanecendo perante a CONTRATANTE como única "
              "responsável pelo objeto deste contrato."]
    cl.append({"titulo": "RESPONSABILIDADES DA CONTRATADA", "paragrafos": [{"lista": itens}]})

    # 5ª contratante: as exclusões da proposta viram obrigações, mais as fixas
    itens = [x for x in (C.get("extras_contratante") or []) if x]
    for e in P.get("exclusoes") or []:
        if e.startswith("Todos e quaisquer itens"):
            continue
        if "rigging" in e.lower() and C.get("rigging_contratante"):
            continue
        if "pluviais" in e.lower() and C.get("pluviais_contratante"):
            continue
        itens.append(e)
    itens.append("Fornecimento de energia elétrica trifásica (220 V, 100 A) no canteiro de obras, em distância máxima de 20 m do local dos serviços;")
    if C.get("seguro_clima"):
        itens.append("Contratação e manutenção de seguro da obra e da estrutura metálica, inclusive após sua conclusão e entrega, "
                     "abrangendo danos decorrentes de vendavais, tempestades, rajadas de vento, chuvas intensas e demais eventos "
                     "climáticos adversos que resultem em ações ou carregamentos superiores àqueles previstos nas normas técnicas "
                     "brasileiras aplicáveis ao dimensionamento da estrutura;")
    if C.get("pluviais_contratante"):
        itens.append("Dimensionamento, fornecimento e instalação de condutores para águas pluviais;")
    if C.get("rigging_contratante"):
        itens.append("Plano de rigging para içamento, movimentação e posicionamento da estrutura;")
    itens += [r for r in (P.get("responsabilidades") or []) if not r.lower().startswith("fornecimento de energia")]
    itens += ["Fornecimento de equipamentos de proteção coletiva (EPC) que se façam necessários para execução dos serviços;",
              "Fornecimento de local reservado para guarda de equipamentos e ferramentas;",
              "Fornecer, ao término do serviço, termo de aceite assinado, atestando a entrega dos serviços contratados."]
    vistos, unicos = set(), []
    for i in itens:
        k = re.sub(r"\W+", "", i.lower())[:60]
        if k not in vistos:
            vistos.add(k)
            unicos.append(i)
    cl.append({"titulo": "RESPONSABILIDADES DA CONTRATANTE", "paragrafos": [{"lista": unicos}]})

    cl.append({"titulo": "SUBCONTRATAÇÃO E FATURAMENTO DIRETO", "paragrafos": [
        "**PARÁGRAFO PRIMEIRO:** A CONTRATANTE autoriza a CONTRATADA a adquirir serviços técnicos, materiais, locação de "
        "equipamentos e serviços de montagem e faturar diretamente contra a CONTRATANTE, descontando estes valores do valor "
        "total deste contrato.",
        "**PARÁGRAFO SEGUNDO:** A CONTRATANTE autoriza a CONTRATADA a subempreitar, parcialmente, os serviços e atividades do "
        "objeto deste contrato. Ocorrendo a subcontratação, a CONTRATADA responderá perante a CONTRATANTE pela regularidade "
        "jurídica, fiscal e trabalhista das empresas subcontratadas, assim como pela qualidade dos serviços, permanecendo "
        "perante a CONTRATANTE como única responsável pelo objeto deste contrato."]})
    desm = _f(C.get("desmobilizacao")) or 10000.0
    cl.append({"titulo": "DESMOBILIZAÇÃO E PARALISAÇÕES", "paragrafos": [
        "Considerou-se neste contrato que a montagem da estrutura ocorrerá em uma única mobilização de equipe; logo, se houver "
        "necessidade de desmobilização da equipe ou paralisação da montagem por questões sob a responsabilidade da CONTRATANTE, "
        "será cobrado o valor de %s (%s) a fim de cobrir os custos referentes a esta desmobilização, ficando autorizada a "
        "CONTRATADA a emitir a respectiva nota fiscal." % (reais(desm), extenso_reais(desm)),
        "**PARÁGRAFO PRIMEIRO:** Havendo paralisação da obra por questões de responsabilidade da CONTRATANTE, fica autorizada a "
        "entrega e o depósito no canteiro de obras de todos os materiais produzidos, concluindo sua entrega, não se "
        "responsabilizando a CONTRATADA pela sua conservação a partir deste momento."]})
    cl.append({"titulo": "INEXISTÊNCIA DE VÍNCULO", "paragrafos": [
        "A CONTRATADA declara que tem outros contratos em andamento, firmados com outros clientes, afastando qualquer vínculo "
        "trabalhista com a CONTRATANTE, nos termos da legislação do trabalho."]})
    multa = _f(C.get("multa_mes")) or 1.0
    cl.append({"titulo": "DA RESCISÃO CONTRATUAL E MULTAS", "paragrafos": [
        "O não cumprimento de qualquer uma das cláusulas deste instrumento implicará na sua rescisão, condenada a parte que der "
        "causa ao pagamento de indenização, custas judiciais e honorários advocatícios, caso seja necessário à parte recorrer "
        "a estes meios para resguardo de seus direitos.",
        "**PARÁGRAFO PRIMEIRO:** Em caso de não cumprimento, por parte da CONTRATADA, do prazo de entrega da obra, fica "
        "estipulada multa de %s%% (%s por cento) ao mês, incidente sobre os serviços em atraso. E, caso ocorra atraso no "
        "pagamento das parcelas pela CONTRATANTE, fica estipulada multa no mesmo percentual."
        % (num(multa, 1), _porcento_extenso(multa))]})
    if C.get("garantia"):
        cl.append({"titulo": "DA GARANTIA", "paragrafos": [
            "A CONTRATADA garante a solidez e a segurança da estrutura metálica pelo prazo de 5 (cinco) anos a contar do termo "
            "de aceite, nos termos do artigo 618 do Código Civil, e a pintura pelo prazo de 1 (um) ano, desde que observadas as "
            "condições de uso e manutenção. As telhas e acessórios têm a garantia de seus fabricantes."]})
    cl.append({"titulo": "CÓDIGO DE ÉTICA, CONDUTA E COMPLIANCE", "paragrafos": [
        "**PARÁGRAFO PRIMEIRO:** As partes declaram que não têm conhecimento de que, até a presente data, nem a CONTRATADA, nem a "
        "CONTRATANTE, bem como seus representantes e/ou suas afiliadas: (i) usaram seus recursos ou de terceiros para "
        "contribuições, doações ou despesas de representação ilegais ou outras despesas ilegais relativas a atividades "
        "políticas; (ii) efetuaram qualquer pagamento ilegal, direto ou indireto, a empregados ou funcionários públicos, "
        "partidos políticos, políticos ou candidatos políticos (incluindo seus familiares), nacionais ou estrangeiros, ou "
        "praticaram quaisquer atos para obter ou manter qualquer negócio, transação ou vantagem comercial indevida; (iii) "
        "violaram qualquer dispositivo de qualquer lei ou regulamento contra prática de corrupção, atos lesivos à administração "
        "pública ou contra a ética, incluindo, mas não se limitando à Lei nº 12.846/13 e ao Decreto nº 8.420/2015, conforme "
        "aplicável (\"Leis Anticorrupção\"); e (iv) efetuaram qualquer pagamento de propina, abatimento ilícito, remuneração "
        "ilícita, suborno, tráfico de influência, \"caixinha\" ou outro pagamento ilegal (\"Condutas Inadequadas\").",
        "**PARÁGRAFO SEGUNDO:** As partes obrigam-se ainda, enquanto perdurar a vigência deste contrato, a observar, cumprir e/ou "
        "fazer cumprir, por si, por seus representantes e afiliadas, toda e qualquer Lei Anticorrupção, bem como abster-se de "
        "praticar quaisquer das Condutas Inadequadas."]})
    cl.append({"titulo": "DO FORO", "paragrafos": [
        "Fica eleito o foro da comarca de %s, Estado %s, para nele serem dirimidas quaisquer dúvidas suscitadas no presente."
        % (C.get("foro") or "—", ESTADOS.get(str(C.get("foro_uf") or "").upper(), "")),
        "E, por estarem justos e contratados, assinam o presente instrumento em duas vias de igual teor e forma, juntamente com "
        "duas testemunhas, obrigando-se a cumpri-lo em todos os seus termos, por si, seus herdeiros e sucessores."]})
    return cl


def _porcento_extenso(p: float) -> str:
    if abs(p - round(p)) < 1e-9:
        return extenso_inteiro(int(round(p)))
    inteiro = int(p)
    dec = int(round((p - inteiro) * 10))
    if inteiro == 0 and dec == 5:
        return "meio"
    return "%s vírgula %s" % (extenso_inteiro(inteiro), extenso_inteiro(dec))


def _linha_geometria(g: dict) -> str:
    L, C, A = _f(g.get("largura")), _f(g.get("comprimento")), _f(g.get("area"))
    medida = (" %sm x %sm" % (num(L), num(C))) if L and C else ""
    return "%s%s: %s m²" % (g.get("nome") or "Cobertura", medida, num(A) if A else "—")


def qualificacao_contratante(C: dict) -> str:
    ct = C.get("contratante") or {}
    partes = ["**%s**, pessoa jurídica de direito privado, inscrita no CNPJ/MF sob o nº %s" % (
        (ct.get("razao_social") or "—").upper(), ct.get("cnpj") or "—")]
    if ct.get("ie"):
        partes.append(", e Inscrição Estadual nº %s" % ct["ie"])
    end = ", ".join(x for x in (ct.get("endereco"), ("CEP " + ct["cep"]) if ct.get("cep") else "",
                                 " - ".join(y for y in (ct.get("cidade"), ct.get("uf")) if y)) if x)
    partes.append(", com sede na %s" % (end or "—"))
    if ct.get("representante"):
        partes.append(", neste ato representada por %s%s%s" % (ct["representante"],
                                                               (", " + ct["representante_qualificacao"]) if ct.get("representante_qualificacao") else "",
                                                               (", inscrito no CPF/MF sob o nº " + ct["representante_cpf"]) if ct.get("representante_cpf") else ""))
    return "".join(partes)


def qualificacao_contratada(empresa: dict) -> str:
    rep = empresa.get("representante") or {}
    end = ", ".join(x for x in (empresa.get("endereco"), empresa.get("bairro"), " - ".join(
        y for y in (empresa.get("cidade"), empresa.get("uf")) if y)) if x)
    return ("**%s**, pessoa jurídica de direito privado, inscrita no CNPJ/MF sob o nº %s%s, com sede na %s, neste ato "
            "representada por %s%s" % ((empresa.get("razao_social") or "—").upper(), empresa.get("cnpj") or "—",
                                       (" e Inscrição Estadual nº " + empresa["ie"]) if empresa.get("ie") else "", end or "—",
                                       rep.get("nome") or "—", (", " + rep["qualificacao"]) if rep.get("qualificacao") else ""))


def avisos_contrato(P: dict, C: dict) -> List[str]:
    av = []
    valor = _f(C.get("valor"))
    ct = C.get("contratante") or {}
    if not valor:
        av.append("Sem o valor do contrato.")
    if not ct.get("cnpj"):
        av.append("Sem o CNPJ do contratante.")
    elif not re.match(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$", str(ct["cnpj"]).strip()):
        av.append("CNPJ do contratante fora do formato 00.000.000/0000-00.")
    if not ct.get("endereco"):
        av.append("Sem o endereço do contratante.")
    parcelas = [p for p in C.get("parcelas") or [] if _f(p.get("valor"))]
    if not parcelas:
        av.append("Sem forma de pagamento (parcelas): o contrato sai só com o preço.")
    elif valor and abs(sum(_f(p["valor"]) for p in parcelas) - valor) > 0.5:
        av.append("As parcelas somam %s e o contrato é de %s." % (reais(sum(_f(p['valor']) for p in parcelas)), reais(valor)))
    hoje = ler_data(C.get("data")) or date.today()
    for p in parcelas:
        d = ler_data(p.get("vencimento"))
        if d and d < hoje - timedelta(days=1):
            av.append("Parcela de %s vence em %s, antes da data do contrato." % (reais(p.get("valor")), p.get("vencimento")))
    arras = _f(C.get("arras"))
    if arras and valor and arras > valor:
        av.append("As arras (%s) são maiores que o contrato: o documento limita ao valor do contrato." % reais(arras))
    vp = _f((P.get("investimento") or {}).get("valor"))
    if vp and valor and abs(vp - valor) > 0.5:
        av.append("Valor negociado: %s na proposta → %s no contrato (%s%%)." % (reais(vp), reais(valor), num(100 * (valor - vp) / vp, 1)))
    if not all(t.get("nome") for t in C.get("testemunhas") or []):
        av.append("Testemunhas sem nome.")
    return av


# ============================================================ etapas e parcelas

def etapas(estado: dict, pasta_projeto: str) -> List[dict]:
    """A linha do tempo: o gravado pelo usuário, com o que o sistema sabe preenchido (orçamento gravado,
    proposta gerada, contrato assinado, sinal pago)."""
    gravado = estado.get("etapas") or {}
    P, C = estado.get("proposta") or {}, estado.get("contrato") or {}
    auto = {}
    if os.path.exists(os.path.join(pasta_projeto, "orcamento", "orcamento.json")):
        auto["orcamento"] = "concluida"
    if P.get("revisoes"):
        auto["proposta"] = "concluida"
        auto["negociacao"] = "concluida" if len(P["revisoes"]) > 1 or C else "andamento"
    if C.get("situacao") == "assinado":
        auto.update({"aprovacao": "concluida", "contrato": "concluida", "negociacao": "concluida"})
    elif C:
        auto["contrato"] = "andamento"
    parcelas = C.get("parcelas") or []
    if parcelas and parcelas[0].get("paga"):
        auto["sinal"] = "concluida"
    saida = []
    for chave, nome, marco in ETAPAS:
        g = gravado.get(chave) or {}
        sit = g.get("situacao") or auto.get(chave) or "pendente"
        saida.append({"chave": chave, "nome": nome, "marco": marco, "situacao": sit, "automatica": not g.get("situacao") and chave in auto,
                      "previsto": g.get("previsto", ""), "realizado": g.get("realizado", ""), "responsavel": g.get("responsavel", ""),
                      "obs": g.get("obs", "")})
    return saida


def resumo_financeiro(C: dict, hoje: Optional[date] = None) -> dict:
    hoje = hoje or date.today()
    valor = _f(C.get("valor")) or 0.0
    aditivos = sum(_f(a.get("valor")) or 0 for a in C.get("aditivos") or [])
    recebido = atrasado = aberto = 0.0
    proxima = None
    for p in C.get("parcelas") or []:
        v = _f(p.get("valor")) or 0.0
        if p.get("paga"):
            recebido += v
            continue
        aberto += v
        d = ler_data(p.get("vencimento"))
        if d and d < hoje:
            atrasado += v
        elif d and (proxima is None or d < ler_data(proxima["vencimento"])):
            proxima = p
    total = valor + aditivos
    return {"contrato": valor, "aditivos": aditivos, "total": total, "recebido": recebido, "a_receber": max(0.0, total - recebido),
            "em_aberto_parcelas": aberto, "atrasado": atrasado, "proxima": proxima,
            "pct_recebido": round(100 * recebido / total, 1) if total else 0.0}


def gerar_parcelas(valor: float, entrada_pct: float, n: int, primeira: date, dia: Optional[int] = None) -> List[dict]:
    """Entrada (%) + n parcelas mensais iguais; a última ajusta os centavos (como nos contratos da empresa)."""
    valor = float(valor or 0)
    saida = []
    entrada = round(valor * (entrada_pct or 0) / 100.0, 2)
    if entrada:
        saida.append({"descricao": "Entrada (sinal)", "vencimento": primeira.strftime("%d/%m/%Y"), "valor": entrada, "paga": False, "pago_em": ""})
    resto = round(valor - entrada, 2)
    if n > 0:
        base = math.floor(resto / n * 100) / 100.0
        dia = dia or primeira.day
        for i in range(n):
            mes = primeira.month + i + (1 if entrada else 0)
            ano = primeira.year + (mes - 1) // 12
            mes = (mes - 1) % 12 + 1
            d = date(ano, mes, min(dia, 28 if mes == 2 else 30 if mes in (4, 6, 9, 11) else 31))
            v = base if i < n - 1 else round(resto - base * (n - 1), 2)
            saida.append({"descricao": "Parcela %d/%d" % (i + 1, n), "vencimento": d.strftime("%d/%m/%Y"), "valor": v, "paga": False, "pago_em": ""})
    return saida
