# -*- coding: utf-8 -*-
"""Os arquivos de um projeto para a aba Arquivos, lidos do disco a cada abertura (15/10: "sempre que for gerado um novo
arquivo ou atualização isso ser atualizado automaticamente na lista de arquivos, pois vou usar isso como caminho padrão
de procura de informações").

Antes a aba tinha uma lista fixa (os CSVs e os resumos de detalhamento/): o que o programa gravava noutra pasta (pranchas,
análise, memorial, IFC exportado, proposta) e todo arquivo novo ficavam de fora até alguém cadastrá-lo. Agora vale a regra:
**todo arquivo de entrega que estiver na pasta do projeto aparece**, com a descrição conhecida ou uma pela pasta. Ficam de fora
só os de trabalho do programa (JSON, histórico, backups, lixeira, as fotos do dossiê)."""
import os
import re
import time
from typing import Callable, Dict, List

#: Extensões de arquivo de entrega (o que se abre fora do programa).
EXTENSOES = (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".dxf", ".dwg", ".ifc", ".zip", ".html", ".md", ".txt",
             ".png", ".jpg", ".jpeg")
#: Imagem só conta em documentos/ (no resto são as fotos e miniaturas que o programa usa).
SO_EM_DOCUMENTOS = (".png", ".jpg", ".jpeg", ".md", ".txt")
#: Pastas de trabalho do programa, nunca listadas.
IGNORAR = {"historico", "dossie", "fotos", "miniaturas", "cache", "__pycache__", "desenhos-2d", "conferencias"}
PASTA_DOCUMENTOS = "documentos"

#: Descrição pelo nome do arquivo (os que o programa gera sempre com o mesmo nome).
CONHECIDOS: Dict[str, tuple] = {
    "lista-de-materiais.pdf": ("Lista de materiais (PDF)", "A lista de materiais em PDF, para imprimir"),
    "lista-de-materiais.html": ("Lista de materiais (HTML)", "A lista de materiais no navegador"),
    "resumo-de-materiais.pdf": ("Resumo de materiais (PDF)", "Compra: perfis e barras, chapas, parafusos, telhas"),
    "resumo-de-materiais.xlsx": ("Resumo de materiais (Excel)", "Os mesmos números em planilha, para o comprador"),
    "resumo-de-materiais.html": ("Resumo de materiais (HTML)", "O resumo de materiais no navegador"),
    "resumo-da-obra.pdf": ("Resumo da obra (PDF)", "Dossiê da obra: implantação, tipos de estrutura e pendências"),
    "resumo-da-obra.html": ("Resumo da obra (HTML)", "O resumo da obra no navegador"),
    "romaneio.csv": ("Romaneio", "Romaneio por posição (Excel)"),
    "resumo-perfis.csv": ("Resumo de perfis", "Perfis com barras de compra (Excel)"),
    "peso-dobras.csv": ("Peso dos dobrados", "Perfis dobrados: peso teórico × com desconto (Excel)"),
    "resumo-chapas.csv": ("Resumo de chapas", "Chapas por espessura (Excel)"),
    "conjuntos.csv": ("Conjuntos", "Conjuntos e composição (Excel)"),
    "plano-de-corte.csv": ("Plano de corte", "O que sai de cada barra (Excel)"),
    "soldas.csv": ("Soldas", "Soldas de fábrica por conjunto (Excel)"),
    "pre-moldados.csv": ("Pré-moldados", "Peças de concreto e aço fora das peças (Excel)"),
    "estrutura-a-conferir.csv": ("Estrutura a conferir", "Peças da estrutura a conferir (Excel)"),
    "pranchas.pdf": ("Pranchas (PDF)", "Todas as pranchas de fabricação num PDF"),
    "pranchas.dxf": ("Pranchas (DXF)", "Todas as pranchas num DXF só"),
    "pranchas-dxf.zip": ("Pranchas (DXF, uma por arquivo)", "Um DXF por prancha, num ZIP"),
}
#: Descrição pela pasta, para o que não está em CONHECIDOS.
POR_PASTA = {
    PASTA_DOCUMENTOS: "Documento da obra", "detalhamento": "Detalhamento", "pranchas": "Pranchas de fabricação",
    "analise": "Análise estrutural", "memorial": "Memorial de cálculo", "ifc": "IFC exportado", "comercial": "Comercial",
    "origem": "Arquivo recebido (origem)", "": "Projeto",
}
#: A data no fim do nome (…-2026-10-14, …_20261014): versões do mesmo documento.
_DATA = re.compile(r"[-_ ]?(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})(?:[-_]\d{4,6})?$")


def _base_sem_data(nome: str) -> str:
    raiz, ext = os.path.splitext(nome)
    return _DATA.sub("", raiz).lower() + ext.lower()


def listar(pasta_projeto: str, url_de: Callable[[str], str]) -> List[dict]:
    """Os arquivos de entrega do projeto, o mais novo primeiro: {nome, pasta, url, tamanho_kb, alterado, rotulo, descricao,
    documento (de documentos/), anterior (o nome da versão mais nova do mesmo documento, quando há)}. `url_de(caminho)` dá
    o endereço de download. As DXF soltas de pranchas/pranchas-dxf/ entram só quando não há o ZIP delas."""
    if not os.path.isdir(pasta_projeto):
        return []
    tem_zip_pranchas = os.path.exists(os.path.join(pasta_projeto, "pranchas", "pranchas-dxf.zip"))
    saida = []
    for raiz, pastas, arquivos in os.walk(pasta_projeto):
        rel = os.path.relpath(raiz, pasta_projeto).replace("\\", "/")
        rel = "" if rel == "." else rel
        pastas[:] = [p for p in pastas if not (p.startswith(".") or p.startswith("backup") or p in IGNORAR)]
        if tem_zip_pranchas and rel == "pranchas/pranchas-dxf":
            continue
        topo = rel.split("/")[0]
        for nome in arquivos:
            ext = os.path.splitext(nome)[1].lower()
            if nome.startswith((".", "~$")) or ext not in EXTENSOES:
                continue
            if ext in SO_EM_DOCUMENTOS and topo != PASTA_DOCUMENTOS:
                continue
            cam = os.path.join(raiz, nome)
            try:
                st = os.stat(cam)
            except OSError:
                continue
            rot, desc = CONHECIDOS.get(nome.lower(), (None, None))
            if not rot:
                rot = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", os.path.splitext(nome)[0])).strip()
                desc = POR_PASTA.get(topo, POR_PASTA[""]) + (" — " + rel if rel and rel != topo else "")
            saida.append({"nome": nome, "pasta": rel, "url": url_de(cam), "tamanho_kb": round(st.st_size / 1024, 1),
                          "alterado": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
                          "rotulo": rot, "descricao": desc, "documento": topo == PASTA_DOCUMENTOS})
    # versões: o mesmo documento com outra data no nome — a mais nova vale, as outras ficam marcadas
    grupos: Dict[tuple, list] = {}
    for a in saida:
        if _DATA.search(os.path.splitext(a["nome"])[0]):
            grupos.setdefault((a["pasta"], _base_sem_data(a["nome"])), []).append(a)
    for lista in grupos.values():
        if len(lista) > 1:
            lista.sort(key=lambda a: (_DATA.search(os.path.splitext(a["nome"])[0]).groups(), a["alterado"]), reverse=True)
            for a in lista[1:]:
                a["anterior"] = lista[0]["nome"]
    saida.sort(key=lambda a: a["alterado"], reverse=True)
    return saida
