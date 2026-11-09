# -*- coding: utf-8 -*-
"""Os documentos da obra numa casa só (DECISÃO do usuário, 09/11, Projeto/BRIEFINGS/Briefing-documentos-da-obra.md, parte B1):
todo gerador de documento — do sistema ou script de obra — grava UMA vez, em `<dados>\\<projeto>\\<pasta do padrão>\\`, e a
revisão anterior do mesmo documento vai para `Obsoleto\\` no mesmo passo (regra de 06/11). Acaba a segunda cópia em
Projeto/OBRAS (OneDrive).

As pastas do padrão (Projeto/OBRAS/LEIA-ME.md, "PADRÃO DAS PASTAS"):
    01-RECEBIDOS  do cliente e do projetista, intocado, uma pasta por data
    02-ORCAMENTO  levantamento, análises, RESUMO, memorial, cotação, perguntas
    03-PROPOSTA   proposta e contrato
    04-EXECUCAO   pranchas, DXF/CNC, romaneio, caderno de montagem
    05-ENVIADOS   cópia exata do que saiu, "AAAA-MM-DD destino\\" (a prova)
    _interno      scripts da obra, figuras, dados de trabalho

Uso num script de obra (sistema/ no sys.path):
    from saida import documentos_obra as DO
    r = DO.gravar("hora-certa-galpão-novo", "02", "GalpaoNovo-RESUMO-2026-11-09-rev28.pdf", origem=pdf_temporario)
    # ou, quando o gerador escreve sozinho no caminho:
    destino = DO.caminho("hora-certa-galpão-novo", "02", "GalpaoNovo-memorial-quantitativo-2026-11-09-rev28.pdf")
    printpdf.imprimir(html, destino); r = DO.fechar_revisao(destino)
"""
import datetime
import json
import os
import re
import shutil
from typing import Dict, List, Optional, Union

from saida.entrega import PASTA_OBSOLETO, aviso_dos_presos, para_obsoleto

#: as pastas do padrão: chave curta → (nome da pasta, o que vai nela)
PASTAS: Dict[str, tuple] = {
    "01": ("01-RECEBIDOS", "do cliente e do projetista, intocados"),
    "02": ("02-ORCAMENTO", "levantamento, RESUMO, memorial, perguntas"),
    "03": ("03-PROPOSTA", "proposta e contrato"),
    "04": ("04-EXECUCAO", "pranchas, DXF/CNC, romaneio, caderno de montagem"),
    "05": ("05-ENVIADOS", "cópia exata do que saiu, por data e destino"),
    "interno": ("_interno", "scripts e dados de trabalho"),
}
NOMES_DAS_PASTAS = tuple(v[0] for v in PASTAS.values())

#: o nome de uma revisão: "<prefixo>-<aaaa-mm-dd>[-<revNN|RNN>]<variante>.<ext>" — o mesmo prefixo, variante e extensão é o
#: mesmo documento (o PDF e o Word de uma revisão são dois documentos: cada um leva o seu anterior)
_NOME = re.compile(r"^(?P<pre>.+?)-(?P<data>\d{4}-\d{2}-\d{2})(?:-(?P<rev>(?:rev|R)\d+[a-z]?))?(?P<suf>[^.]*)\.(?P<ext>[^.]+)$", re.I)


def pasta_dos_dados() -> str:
    return os.environ.get("METALICA_DADOS") or os.path.join("C:\\", "Metálica", "dados")


def pasta_da_obra(projeto: str) -> str:
    """O projeto pelo slug (na pasta dos dados) ou por um caminho já pronto."""
    return projeto if os.path.isabs(projeto) else os.path.join(pasta_dos_dados(), projeto)


def nome_da_pasta(pasta: str) -> str:
    """"02" / "02-ORCAMENTO" / "interno" → o nome da pasta do padrão; outro nome dá erro (nada fora do padrão)."""
    if pasta in PASTAS:
        return PASTAS[pasta][0]
    if pasta in NOMES_DAS_PASTAS:
        return pasta
    raise ValueError("pasta fora do padrão da obra: %r (use %s)" % (pasta, ", ".join(PASTAS)))


def caminho(projeto: str, pasta: str, nome: str) -> str:
    """O caminho do documento na pasta do padrão (a pasta é criada)."""
    if os.sep in nome or "/" in nome:
        raise ValueError("o nome do documento não leva pasta: %r" % nome)
    alvo = os.path.join(pasta_da_obra(projeto), nome_da_pasta(pasta))
    os.makedirs(alvo, exist_ok=True)
    return os.path.join(alvo, nome)


def mesmo_documento(a: str, b: str) -> bool:
    """Duas revisões do mesmo documento: o mesmo prefixo, variante e extensão (outra data ou revisão)."""
    m, n = _NOME.match(a), _NOME.match(b)
    return bool(m and n and a != b and m.group("pre").lower() == n.group("pre").lower()
                and m.group("suf").lower() == n.group("suf").lower() and m.group("ext").lower() == n.group("ext").lower())


def revisoes_anteriores(destino: str) -> List[str]:
    """As outras revisões do mesmo documento na pasta do destino (para o Obsoleto)."""
    pasta, nome = os.path.split(os.path.abspath(destino))
    if not os.path.isdir(pasta):
        return []
    return [os.path.join(pasta, x) for x in sorted(os.listdir(pasta))
            if os.path.isfile(os.path.join(pasta, x)) and mesmo_documento(nome, x)]


def fechar_revisao(destino: str) -> dict:
    """Depois de gravar `destino`: as outras revisões do mesmo documento vão para Obsoleto\\ (a aberta no Word fica, com o
    aviso). {"caminho", "obsoletos": [para], "aviso"}."""
    obs = para_obsoleto(revisoes_anteriores(destino))
    return {"caminho": destino, "obsoletos": [b for _a, b in obs["movidos"]], "aviso": aviso_dos_presos(obs["presos"])}


def gravar(projeto: str, pasta: str, nome: str, dados: Union[bytes, str, None] = None, origem: Optional[str] = None,
           mover: bool = False) -> dict:
    """Grava o documento UMA vez na pasta do padrão e fecha a revisão (a anterior para Obsoleto\\). `dados` (bytes ou texto)
    ou `origem` (um arquivo pronto, copiado — ou movido, com `mover`)."""
    if (dados is None) == (origem is None):
        raise ValueError("dê os dados ou o arquivo de origem (um dos dois)")
    destino = caminho(projeto, pasta, nome)
    if origem is not None:
        if os.path.abspath(origem) != os.path.abspath(destino):
            (shutil.move if mover else shutil.copy2)(origem, destino)
    else:
        with open(destino, "wb") as f:
            f.write(dados.encode("utf-8") if isinstance(dados, str) else dados)
    return fechar_revisao(destino)


def registrar_envio(projeto: str, caminhos: List[str], destino: str, data: Optional[datetime.date] = None, meio: str = "",
                    observacao: str = "") -> dict:
    """A prova do que saiu: copia os arquivos, como estão, para `05-ENVIADOS\\AAAA-MM-DD <destino>\\` e deixa ali o envio.json
    (quem, quando, por onde, o quê). Nada é sobrescrito: um nome que já existe lá ganha " (2)". {"pasta", "copiados"}."""
    data = data or datetime.date.today()
    limpo = re.sub(r'[<>:"/\\|?*]+', "-", destino).strip(" .") or "sem destino"
    pasta = os.path.join(pasta_da_obra(projeto), PASTAS["05"][0], "%s %s" % (data.isoformat(), limpo))
    os.makedirs(pasta, exist_ok=True)
    copiados = []
    for c in caminhos:
        base, ext = os.path.splitext(os.path.basename(c))
        alvo, k = os.path.join(pasta, base + ext), 2
        while os.path.exists(alvo):
            alvo, k = os.path.join(pasta, "%s (%d)%s" % (base, k, ext)), k + 1
        shutil.copy2(c, alvo)
        copiados.append(alvo)
    reg = os.path.join(pasta, "envio.json")
    anteriores = []
    if os.path.isfile(reg):
        try:
            anteriores = json.load(open(reg, encoding="utf-8")).get("envios", [])
        except (OSError, ValueError):
            anteriores = []
    anteriores.append({"data": data.isoformat(), "destino": destino, "meio": meio, "observacao": observacao,
                       "registrado": datetime.datetime.now().isoformat(timespec="seconds"),
                       "arquivos": [os.path.basename(c) for c in copiados],
                       "de": [os.path.relpath(c, pasta_da_obra(projeto)) for c in caminhos]})
    with open(reg, "w", encoding="utf-8") as f:
        json.dump({"envios": anteriores}, f, ensure_ascii=False, indent=1)
    return {"pasta": pasta, "copiados": copiados}


__all__ = ["PASTAS", "NOMES_DAS_PASTAS", "PASTA_OBSOLETO", "pasta_da_obra", "nome_da_pasta", "caminho", "mesmo_documento",
           "revisoes_anteriores", "fechar_revisao", "gravar", "registrar_envio"]
