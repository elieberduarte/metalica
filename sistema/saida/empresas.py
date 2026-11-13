# -*- coding: utf-8 -*-
"""O cadastro das empresas (a principal em <dados>/fabrica/, as outras em <dados>/fabrica/empresas/<id>/): os dados, a marca
e as linhas de serviço. Saiu do saida/comercial.py em 13/11/2026 (conferência da 0.9.3): a marca d'água das Cenas e o
carimbo das pranchas o usam no programa instalado, e o comercial (proposta, contrato) é só do desenvolvimento
(empacotar/construir.py, MODULOS_SO_DEV) — no .exe o "from saida import comercial" dava "No module named …".
O comercial.py reexporta tudo daqui."""
import copy
import json
import os
import re
from typing import List

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
    "layout": "classico",
    "prefixo_numero": "",
    "linhas": {},
}

#: Várias empresas (27/10): a principal é a de sempre, em <dados>/fabrica/ (empresa.json, marca/, comercial-seq.json),
#: sem mudar de lugar — a proposta dela sai igual. As outras ficam em <dados>/fabrica/empresas/<id>/, cada uma com
#: o seu empresa.json, a sua marca/ e a sua numeração. A proposta grava a escolhida em ``proposta.empresa``.
PRINCIPAL = "principal"
#: O desenho da proposta em PDF: clássico (capa com a foto do 3D, seções — saida/proposta_html.py) ou compacto
#: (cabeçalho da marca, faixa de destaques, escopo incluso × não incluso — saida/proposta_compacta.py; piloto C da DEZN).
LAYOUTS = {"classico": "Clássico — capa com a imagem do 3D e seções", "compacto": "Compacto — 2 páginas, sem capa"}


def _id_empresa(empresa_id) -> str:
    i = str(empresa_id or "").strip().lower()
    if not i or i == PRINCIPAL:
        return PRINCIPAL
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", i):
        raise ValueError("identificador de empresa inválido: %s" % empresa_id)
    return i


def pasta_empresa(dados: str, empresa_id=None) -> str:
    i = _id_empresa(empresa_id)
    return os.path.join(dados, "fabrica") if i == PRINCIPAL else os.path.join(dados, "fabrica", "empresas", i)


def pasta_marca(dados: str, empresa_id=None) -> str:
    return os.path.join(pasta_empresa(dados, empresa_id), "marca")


def ler_empresa(dados: str, empresa_id=None) -> dict:
    i = _id_empresa(empresa_id)
    e = copy.deepcopy(EMPRESA_PADRAO)
    try:
        with open(os.path.join(pasta_empresa(dados, i), "empresa.json"), encoding="utf-8") as f:
            lido = json.load(f)
        for k, v in lido.items():
            if isinstance(v, dict) and isinstance(e.get(k), dict):
                e[k].update(v)
            else:
                e[k] = v
    except (OSError, ValueError):
        if i != PRINCIPAL and not os.path.isdir(pasta_empresa(dados, i)):
            raise ValueError("empresa não cadastrada: %s" % i)
    if e.get("layout") not in LAYOUTS:
        e["layout"] = "classico"
    e["id"] = i
    marca = pasta_marca(dados, i)
    for chave, nomes in (("logo", ("logo.svg", "logo.png", "logo.jpg")), ("logo_claro", ("logo_claro.svg", "logo_claro.png")),
                         ("rodape", ("rodape.png", "rodape.jpg"))):
        e[chave] = next((os.path.join(marca, n) for n in nomes if os.path.exists(os.path.join(marca, n))), "")
    for lin in (e.get("linhas") or {}).values():
        for chave in ("logo", "logo_claro", "logo_carimbo", "logo_carimbo_claro"):
            if lin.get(chave):
                arq = os.path.join(marca, os.path.basename(str(lin[chave])))
                lin[chave] = arq if os.path.exists(arq) else ""
    return e


def empresa_da_linha(e: dict, linha=None) -> dict:
    """A marca de uma linha de serviço da empresa — empresa.json "linhas": {"metalica": {nome_comercial, logo,
    logo_claro}} (arquivos em marca/). A DEZN assina "DEZN", sem o "Construtora", nas propostas de metálica (usuário,
    30/10). Sem linha na proposta vale a "metalica" (o Metálica orça estrutura metálica), quando a empresa a tiver."""
    lin = (e.get("linhas") or {}).get(linha or "metalica")
    if not lin:
        return e
    e2 = dict(e)
    e2.update({k: v for k, v in lin.items() if v not in (None, "")})
    return e2


def listar_empresas(dados: str) -> List[dict]:
    """[{id, nome, layout}] — a principal primeiro, depois as de fabrica/empresas/ em ordem alfabética."""
    ids = [PRINCIPAL]
    try:
        ids += sorted(n for n in os.listdir(os.path.join(dados, "fabrica", "empresas"))
                      if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", n) and n != PRINCIPAL)
    except OSError:
        pass
    saida = []
    for i in ids:
        try:
            e = ler_empresa(dados, i)
        except ValueError:
            continue
        saida.append({"id": i, "nome": e.get("nome_comercial") or e.get("razao_social") or ("Empresa principal" if i == PRINCIPAL else i),
                      "layout": e["layout"]})
    return saida
