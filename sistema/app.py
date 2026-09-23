# -*- coding: utf-8 -*-
"""Servidor web local do sistema de dimensionamento de galpões.

Roda sem framework: apenas a biblioteca padrão. Sobe em http://localhost:8765 e serve
a interface de `web/` mais uma API JSON.

    python app.py              sobe o servidor e abre o navegador
    python app.py --porta 9000 outra porta
    python app.py --sem-navegador

Rotas da API:
    GET  /api/catalogo              perfis, aços, parafusos, eletrodos, cidades
    GET  /api/catalogo/pecas        catálogo de peças (famílias, itens, busca, alternativas)
    GET  /api/atualizacao           última versão publicada no GitHub e se é mais nova
    POST /api/atualizacao/instalar  baixa o instalador da release e o executa (programa instalado)
    POST /api/dimensionar           recebe DadosGalpao, devolve ProjetoGalpao em JSON
    POST /api/gerar                 gera memorial, DXF, pranchas e lista de material
    POST /api/modelo/ifc/detalhar   IFC recebido → DXF de produção, romaneio e relatório
    GET  /api/projetos                  lista os projetos (ver projetos.py)
    POST /api/projetos                  cria um projeto
    GET  /api/projetos/<slug>           projeto.json e resumo
    GET  /api/projetos/<slug>/modelo    documento do editor 3D
    POST /api/projetos/<slug>/<ação>    dados, modelo, importar-ifc, renomear, duplicar,
                                        excluir, abrir-pasta
    POST /api/projetos/<slug>/vista2d   vista 2D do modelo (corte/projeção) → desenho
    POST /api/projetos/<slug>/detalhar  detalhamento de peças e conjuntos → desenhos + lista de materiais
    POST /api/projetos/<slug>/detalhar-posicao {marca}   detalhe de uma peça (chapa vira paramétrica)
    POST /api/projetos/<slug>/calcular {parametros, trocas, comparar}  cálculo estrutural do modelo importado
    GET  /api/projetos/<slug>/calculo[/geometria]        último cálculo gravado / dados para o diálogo
    POST /api/projetos/<slug>/desenhos/<nome>/aplicar-furos   furos do detalhe → chapas do modelo
    GET  /api/projetos/<slug>/materiais[?recalcular=1]  lista de materiais (romaneio, perfis, chapas, conjuntos)
    POST /api/projetos/<slug>/materiais[/pdf]           recalcula do modelo (barra, regra_tercas) / imprime o PDF
    POST /api/projetos/<slug>/pranchas  pranchas (folhas com carimbo) a partir dos desenhos 2D
    POST /api/projetos/<slug>/importar-dxf  DXF em texto → entidades do CAD
    GET  /api/projetos/<slug>/desenhos[/<nome>]      desenhos 2D do CAD
    POST /api/projetos/<slug>/desenhos/<nome>[/dxf|/pdf|/excluir]
    GET  /saida/<projeto>/<arquivo> baixa um arquivo gerado
"""
import json
import mimetypes
import os
import getpass
import platform
import posixpath
import socket
import re
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import unquote, urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
sys.path.insert(0, BASE)

import versao                                  # noqa: E402


def _documentos() -> str:
    """Pasta Documentos do usuário, mesmo quando o OneDrive a redirecionou."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD),
                            ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                       (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            ptr = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(
                    ctypes.byref(fid), 0, None, ctypes.byref(ptr)) == 0 and ptr.value:
                caminho = ptr.value
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                return caminho
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _pasta_de_dados() -> str:
    """Onde ficam projetos, modelos e arquivos gerados.

    `--dados pasta` ou a variável METALICA_DADOS mandam. Sem elas, o programa instalado
    grava em Documentos\\Metálica — a pasta de instalação não aceita escrita, e ali o
    usuário enxerga os arquivos e faz backup —, e o desenvolvimento continua em
    `sistema/projetos`, onde os testes e os verificadores procuram.
    """
    if "--dados" in sys.argv:
        i = sys.argv.index("--dados")
        if i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i + 1])
    if os.environ.get("METALICA_DADOS"):
        return os.path.abspath(os.environ["METALICA_DADOS"])
    if versao.CONGELADO:
        return os.path.join(_documentos(), versao.NOME)
    return os.path.join(BASE, "projetos")


PROJETOS = _pasta_de_dados()

from nucleo.base import ErroDeDados            # noqa: E402
from nucleo.modelo_galpao import DadosGalpao   # noqa: E402


# ----------------------------------------------------------------- serviços

def catalogo() -> dict:
    from nucleo import materiais as mat
    from nucleo.perfis import banco
    b = banco()
    dados = mat.listar()
    dados["perfis"] = {tipo: [p.resumo() for p in lista]
                       for tipo, lista in b.por_tipo.items()}
    try:
        from nucleo.cargas import listar as listar_cargas
        dados["cargas"] = listar_cargas()
    except Exception as e:                      # módulo ainda em desenvolvimento
        dados["cargas"] = {"erro": str(e)}
    dados["campos"] = _campos_formulario()
    return dados


def _campos_formulario() -> list:
    """Descreve os campos de DadosGalpao para a interface montar o formulário."""
    import dataclasses
    grupos = {
        "identificacao": ("Identificação", ["nome", "cliente", "local", "responsavel"]),
        "geometria": ("Geometria", ["vao", "comprimento", "pe_direito",
                                    "espacamento_porticos", "inclinacao", "balanco_lateral"]),
        "sistema": ("Sistema estrutural", ["tipo_portico", "base_rotulada", "com_misula",
                                           "comprimento_misula", "altura_misula"]),
        "materiais": ("Materiais", ["aco_perfis", "aco_tercas", "aco_chapas", "parafuso",
                                    "eletrodo", "fck_MPa"]),
        "cobertura": ("Cobertura e fechamento", ["telha", "espacamento_tercas",
                                                 "linhas_correntes", "fechamento_lateral",
                                                 "altura_fechamento"]),
        "cargas": ("Cargas", ["sobrecarga_cobertura", "carga_forro", "carga_extra",
                              "ponte_rolante", "capacidade_ponte_t"]),
        "vento": ("Vento (NBR 6123)", ["cidade", "v0", "categoria_rugosidade", "classe",
                                       "fator_topografico", "fator_estatistico", "aberturas"]),
        "criterios": ("Critérios de projeto", ["flecha_terca", "flecha_viga",
                                               "desloc_horizontal", "custo_kg"]),
    }
    tipos = {f.name: f.type for f in dataclasses.fields(DadosGalpao)}
    padrao = DadosGalpao()
    saida = []
    for chave, (titulo, campos) in grupos.items():
        itens = []
        for c in campos:
            t = tipos.get(c, str)
            nome_tipo = getattr(t, "__name__", str(t))
            itens.append({"campo": c, "tipo": nome_tipo,
                          "valor": getattr(padrao, c), "rotulo": _rotulo(c)})
        saida.append({"grupo": chave, "titulo": titulo, "campos": itens})
    return saida


ROTULOS = {
    "vao": "Vão livre (m)", "comprimento": "Comprimento total (m)",
    "pe_direito": "Pé-direito (m)", "espacamento_porticos": "Espaçamento entre pórticos (m)",
    "inclinacao": "Inclinação do telhado (%)", "balanco_lateral": "Beiral lateral (m)",
    "tipo_portico": "Tipo de pórtico", "base_rotulada": "Base rotulada",
    "com_misula": "Usar mísula", "comprimento_misula": "Comprimento da mísula (m)",
    "altura_misula": "Altura total no joelho, com a mísula (m, 0 = automática)",
    "aco_perfis": "Aço dos perfis", "aco_tercas": "Aço das terças",
    "aco_chapas": "Aço das chapas", "parafuso": "Parafuso", "eletrodo": "Eletrodo",
    "fck_MPa": "fck do concreto (MPa)", "telha": "Telha",
    "espacamento_tercas": "Espaçamento das terças (m)",
    "linhas_correntes": "Linhas de correntes por água",
    "fechamento_lateral": "Fechamento lateral", "altura_fechamento": "Altura do fechamento (m)",
    "sobrecarga_cobertura": "Sobrecarga de cobertura (kN/m²)",
    "carga_forro": "Forro (kN/m²)", "carga_extra": "Carga extra (kN/m²)",
    "ponte_rolante": "Tem ponte rolante", "capacidade_ponte_t": "Capacidade da ponte (t)",
    "cidade": "Cidade", "v0": "V₀ (m/s)", "categoria_rugosidade": "Categoria de rugosidade",
    "classe": "Classe da edificação", "fator_topografico": "S₁ (topografia)",
    "fator_estatistico": "S₃ (estatístico)", "aberturas": "Aberturas (Cpi)",
    "flecha_terca": "Flecha da terça (L/…)", "flecha_viga": "Flecha da viga (L/…)",
    "desloc_horizontal": "Deslocamento do pilar (H/…)", "custo_kg": "Custo (R$/kg instalado)",
    "nome": "Nome do projeto", "cliente": "Cliente", "local": "Local",
    "responsavel": "Responsável técnico",
}


def _rotulo(campo: str) -> str:
    return ROTULOS.get(campo, campo.replace("_", " ").capitalize())


def dimensionar(entrada: dict) -> dict:
    from nucleo.galpao import dimensionar as calcular
    dados = _dados_de(entrada)
    projeto = calcular(dados)
    return projeto.para_json()


def gerar_saidas(entrada: dict) -> dict:
    """Calcula e grava memorial, desenhos, pranchas e lista de material."""
    from nucleo.galpao import dimensionar as calcular
    dados = _dados_de(entrada.get("dados", entrada))
    quais = entrada.get("saidas") or ["memorial", "dxf", "pranchas", "lista"]
    projeto = calcular(dados)
    do_projeto, pasta = _pasta_do_projeto(entrada, dados.nome)
    os.makedirs(pasta, exist_ok=True)
    arquivos = []

    if "dxf" in quais or "pranchas" in quais:
        try:
            from saida import desenhos
            arquivos += desenhos.gerar_todos(projeto, os.path.join(pasta, "desenhos"))
        except Exception as e:
            projeto.avisos.append(f"Desenhos não gerados: {e}")
    if "pranchas" in quais:
        try:
            from saida import pranchas
            arquivos += pranchas.gerar(projeto, os.path.join(pasta, "pranchas"))
        except Exception as e:
            projeto.avisos.append(f"Pranchas não geradas: {e}")
    if "memorial" in quais:
        try:
            from saida import memorial
            arquivos.append(memorial.gerar(projeto, os.path.join(pasta, "memorial")))
        except Exception as e:
            projeto.avisos.append(f"Memorial não gerado: {e}")
    if "lista" in quais:
        try:
            from saida import lista_material
            arquivos += lista_material.gerar(projeto, os.path.join(pasta, "lista"))
        except Exception as e:
            projeto.avisos.append(f"Lista de material não gerada: {e}")

    resposta = projeto.para_json()
    resposta["arquivos"] = [_descrever_arquivo(a, pasta) for a in arquivos if a]
    resposta["pasta"] = pasta
    if do_projeto:
        _gerente().tocar(do_projeto)
    return resposta


def _descrever_arquivo(caminho, pasta_projeto):
    if isinstance(caminho, dict):
        cam = caminho.get("arquivo") or caminho.get("caminho", "")
        extra = {k: v for k, v in caminho.items() if k not in ("arquivo", "caminho")}
    else:
        cam, extra = caminho, {}
    rel = os.path.relpath(cam, PROJETOS).replace("\\", "/")
    d = {"nome": os.path.basename(cam), "url": "/saida/" + rel,
         "tamanho_kb": round(os.path.getsize(cam) / 1024, 1) if os.path.exists(cam) else 0}
    d.update(extra)
    return d


def _dados_de(entrada: dict) -> DadosGalpao:
    campos = {f.name for f in __import__("dataclasses").fields(DadosGalpao)}
    limpo = {}
    for k, v in (entrada or {}).items():
        if k not in campos:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                continue
        limpo[k] = v
    try:
        d = DadosGalpao(**limpo)
    except TypeError as e:
        raise ErroDeDados(f"dados de entrada inválidos: {e}")
    # converte números que vieram como texto
    import dataclasses
    for f in dataclasses.fields(DadosGalpao):
        v = getattr(d, f.name)
        alvo = f.type if isinstance(f.type, type) else None
        if alvo in (float, int) and isinstance(v, str):
            try:
                setattr(d, f.name, alvo(v.replace(",", ".")))
            except ValueError:
                raise ErroDeDados(f"{_rotulo(f.name)}: '{v}' não é um número.")
        elif alvo is bool and isinstance(v, str):
            setattr(d, f.name, v.lower() in ("true", "1", "sim", "on"))
    return d.validar()


def _slug(nome: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (nome or "projeto"), flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "projeto"


# ---------------------------------------------------------------- projetos
#
# Ver projetos.py: cada projeto é uma pasta com projeto.json, modelo.json, o IFC de
# origem e as entregas. Aqui ficam só as rotas e o que depende do resto do servidor.

def _gerente():
    from projetos import Projetos
    return Projetos(PROJETOS)


def _pasta_do_projeto(corpo: dict, nome_padrao: str):
    """(slug ou None, pasta) onde gravar uma entrega. Com `projeto` no pedido, dentro
    dele; sem, numa pasta com o nome do trabalho, como sempre foi."""
    s = (corpo or {}).get("projeto")
    if s:
        return s, _gerente()._existente(s)
    return None, os.path.join(PROJETOS, _slug(nome_padrao))


def criar_projeto(corpo: dict) -> dict:
    return _gerente().criar(corpo.get("nome"), corpo.get("cliente"), corpo.get("local"),
                            corpo.get("responsavel"), corpo.get("tipo") or "galpao",
                            corpo.get("dados") if isinstance(corpo.get("dados"), dict) else None)


def projeto_completo(s: str) -> dict:
    g = _gerente()
    return {"projeto": g.ler(s), "resumo": g.resumo(s)}


def acao_de_projeto(s: str, acao: str, corpo: dict) -> dict:
    g = _gerente()
    if acao == "dados":
        return g.salvar_dados(s, corpo.get("dados", corpo))
    if acao == "renomear":
        return g.renomear(s, corpo.get("nome"))
    if acao == "duplicar":
        return g.duplicar(s, corpo.get("nome"))
    if acao == "excluir":
        return g.excluir(s)
    if acao == "abrir-pasta":
        pasta = g._existente(s)
        sub = os.path.basename(str(corpo.get("sub") or ""))
        if sub and os.path.isdir(os.path.join(pasta, sub)):
            pasta = os.path.join(pasta, sub)
        _abrir_no_explorador(pasta)
        return {"aberta": pasta}
    if acao == "modelo":
        # o editor manda a data do modelo que carregou: se o arquivo mudou depois disso
        # (o CAD aplicou furos, outra janela ou outra máquina gravou), não sobrescreve
        base = corpo.get("base_alterado")
        if base is not None:
            atual = _alterado_modelo(s)
            if atual - float(base) > 0.5:
                raise ErroDeDados("o modelo deste projeto foi gravado por outra tela, janela ou máquina depois de "
                                  "você abri-lo; recarregue o modelo (F5) antes de continuar. Nada foi gravado.")
        r = g.salvar_modelo(s, corpo.get("documento", corpo))
        r["alterado"] = _alterado_modelo(s)
        return r
    if acao == "importar-ifc":
        return importar_ifc_no_projeto(s, corpo)
    if acao == "restaurar-modelo":
        r = g.restaurar_modelo(s, corpo.get("arquivo"))
        r["alterado"] = _alterado_modelo(s)
        return r
    raise ErroDeDados("ação desconhecida para o projeto: " + acao)


def _abrir_no_explorador(pasta: str):
    """Abre a pasta no gerenciador de arquivos do sistema (o servidor é local)."""
    import subprocess
    os.makedirs(pasta, exist_ok=True)
    if os.name == "nt":
        os.startfile(pasta)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", pasta])
    else:
        subprocess.Popen(["xdg-open", pasta])


def importar_ifc_no_projeto(s: str, corpo: dict) -> dict:
    """Guarda o IFC em <projeto>/origem, importa e grava o modelo do editor. Devolve só
    o relatório: o documento tem dezenas de megabytes e o editor o busca ao abrir."""
    import base64
    from ifc import importar as imp
    g = _gerente()
    pasta = g._existente(s)
    dados = corpo.get("conteudo_b64")
    if not dados:
        raise ErroDeDados("nenhum arquivo IFC recebido.")
    nome = os.path.basename(corpo.get("nome") or "modelo.ifc")
    if not nome.lower().endswith(".ifc"):
        nome += ".ifc"
    destino = os.path.join(pasta, "origem", nome)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        _progresso(s, "gravando o IFC na pasta do projeto…")
        with open(destino, "wb") as f:
            f.write(base64.b64decode(dados))
        _progresso(s, "lendo o IFC (%.0f MB; leva uns 20 s)…" % (os.path.getsize(destino) / 1048576))
        doc = imp.importar(destino)
        _progresso(s, "gravando o modelo 3D…")
        g.salvar_modelo(s, doc.dict(), marco=True)
        g.tocar(s, tipo="ifc", origem_ifc=nome)
    finally:
        _fim_progresso(s)
    return {"projeto": s, "estatisticas": doc.estatisticas(),
            "relatorio": doc.metadados.get("importacao", {})}


# ---- desenhos 2D (CAD): ver nucleo2d/

def _documento3d_do_projeto(s: str):
    from nucleo3d.modelo import Documento
    d = _gerente().abrir_modelo(s)
    if d is None:
        raise ErroDeDados("o projeto ainda não tem modelo 3D: importe o IFC ou gere o galpão.")
    return Documento.de_dict(d)


def gerar_vista_2d(s: str, corpo: dict) -> dict:
    """Vista 2D do modelo do projeto: cria um desenho novo ou acrescenta a um existente.

    corpo: {vista: {origem, normal, acima, profundidade, cortar, entidades, nome, tipo}
                   ou {padrao: "frente"|"topo"|..., profundidade, entidades},
            vistas: [várias definições como acima, geradas de uma vez],
            desenho: nome do desenho (novo ou existente), deslocamento: [x, y]}

    Várias vistas num pedido só saem lado a lado e gravam o desenho uma única vez: um
    desenho do modelo inteiro passa de dezenas de megabytes, e ler e regravar tudo a
    cada vista é o que demora e o que dá "arquivo em uso" com o OneDrive por cima."""
    from nucleo2d.vistas import Vista, gerar, vista_padrao
    from nucleo2d.desenho import Desenho
    g = _gerente()
    doc = _documento3d_do_projeto(s)
    definicoes = corpo.get("vistas")
    if not isinstance(definicoes, list) or not definicoes:
        definicoes = [corpo.get("vista") or {}]
    vistas = []
    for definicao in definicoes:
        if definicao.get("padrao"):
            vista = vista_padrao(str(definicao["padrao"]), doc.caixa())
            for k in ("profundidade", "entidades", "nome", "rotular"):
                if definicao.get(k) is not None:
                    setattr(vista, k, definicao[k])
        else:
            vista = Vista.de_dict(definicao)
        if not vista.nome:
            vista.nome = {"corte": "Corte"}.get(vista.tipo, vista.tipo.capitalize())
        vistas.append(vista)
    nome = corpo.get("desenho") or vistas[0].nome or "desenho"
    desenho = None
    if corpo.get("substituir") and os.path.exists(g._caminho_desenho(s, nome)):
        g.excluir_desenho(s, nome)                  # vai para a lixeira
    if os.path.exists(g._caminho_desenho(s, nome)):
        # arquivo danificado sem recuperação possível sobe como erro, com o caminho,
        # em vez de ser sobrescrito em silêncio
        desenho = Desenho.de_dict(g.abrir_desenho(s, nome))
    novo = desenho is None
    desl = corpo.get("deslocamento")
    for i, vista in enumerate(vistas):
        if desenho is not None and (i > 0 or not desl):
            # vista nova num desenho que já tem coisas: à direita do que existe
            caixa = desenho.caixa()
            desl = [caixa[1][0] + 40.0 * desenho.escala, caixa[0][1]] if caixa else [0.0, 0.0]
        d = desl or [0.0, 0.0]
        desenho = gerar(doc, vista, desenho, (float(d[0]), float(d[1])))
    if novo:
        desenho.nome = corpo.get("titulo") or nome
    r = g.salvar_desenho(s, nome, desenho.dict())
    r["vista"] = desenho.vistas[-1]
    r["vistas"] = desenho.vistas[-len(vistas):]
    r["escala"] = desenho.escala
    return r


def detalhar_projeto(s: str, corpo: dict) -> dict:
    """Detalhamento de peças e conjuntos do modelo do projeto: um desenho 2D por grupo
    (chapas, barras e terças, tirantes, telhas, conjuntos) gravado em desenhos-2d/, mais o
    romaneio (CSV) e o relatório em detalhamento/.

    corpo: {grupos: [...], regra_tercas: bool, rotular: bool, substituir: bool}"""
    from nucleo2d.detalhar import detalhar, GRUPOS, _categoria
    from saida import lista_producao
    g = _gerente()
    try:
        return _detalhar_projeto(s, corpo, g, detalhar, GRUPOS, _categoria, lista_producao)
    finally:
        _fim_progresso(s)


def _detalhar_projeto(s: str, corpo: dict, g, detalhar, GRUPOS, _categoria, lista_producao) -> dict:
    _progresso(s, "abrindo o modelo…")
    doc = _documento3d_do_projeto(s)
    _conferir_eixos_das_chapas(s, doc)
    grupos = corpo.get("grupos") or list(GRUPOS.keys())
    r = detalhar(doc, grupos=grupos, regra_tercas=corpo.get("regra_tercas", True) is not False,
                 rotular=corpo.get("rotular", True) is not False,
                 converter=corpo.get("converter", True) is not False, ajustes=_ajustes_furos(s),
                 nomes=_nomes_producao(s), avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
    _gravar_nomes_producao(s, r.get("nomes") or {})
    nomeadas = _nomes_no_modelo(doc, r.get("nomes") or {})
    if r.get("convertidas") or nomeadas:
        _progresso(s, "gravando o modelo…")
        g.salvar_modelo(s, doc.dict(), marco=True)            # chapas planas viraram paramétricas / nomes nas peças
    _progresso(s, "gravando os desenhos…")
    substituir = corpo.get("substituir", True) is not False
    desenhos = []
    for chave, desenho in r["desenhos"].items():
        nome = desenho.nome
        if substituir and os.path.exists(g._caminho_desenho(s, nome)):
            g.excluir_desenho(s, nome)
        desenho.metadados["gerado_por"] = "detalhamento"
        salvo = g.salvar_desenho(s, nome, desenho.dict())
        desenhos.append({"grupo": chave, "nome": salvo["nome"], "titulo": nome,
                         "entidades": desenho.tamanho, "escala": desenho.escala})
    pasta = os.path.join(g._existente(s), "detalhamento")
    os.makedirs(pasta, exist_ok=True)
    # a lista de materiais sai do mesmo levantamento dos desenhos (romaneio, perfis, chapas…)
    _progresso(s, "lista de materiais…")
    categorias = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], categorias, r["acessorios"], pecas=r["objetos_pecas"],
                                  barra=float(corpo.get("barra") or 0), projeto=_identificacao_do_projeto(s),
                                  nomes_conjuntos=(r.get("nomes") or {}).get("ifc_conjuntos"))
    arquivos = lista_producao.gravar(pasta, lista, r["objetos_posicoes"], r["acessorios"])
    relatorio = {k: v for k, v in r.items() if k not in ("desenhos", "objetos_posicoes", "objetos_pecas", "camadas")}
    relatorio["desenhos"] = desenhos
    with open(os.path.join(pasta, "relatorio.json"), "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=1)
    g.tocar(s)
    return {"desenhos": desenhos, "posicoes": len(r["posicoes"]), "conjuntos": len(r["conjuntos"]),
            "pecas": sum(p["quantidade"] for p in r["posicoes"]), "peso_total": r["peso_total"],
            "regra_tercas": r["regra_tercas"], "avisos": r["avisos"], "convertidas": r.get("convertidas", 0),
            "romaneio": _descrever_arquivo(arquivos["romaneio"], pasta),
            "materiais": {k: _descrever_arquivo(v, pasta) for k, v in arquivos.items()}}


#: Etapa corrente das operações longas, por projeto: {slug: {"etapa", "quando"}}.
PROGRESSO: Dict[str, dict] = {}


# ----------------------------------------------------------- cálculo do modelo importado

def _caminho_calculo(s: str) -> str:
    return os.path.join(_gerente()._existente(s), "calculo.json")


def calculo_do_projeto(s: str) -> dict:
    """GET /api/projetos/<s>/calculo: o último cálculo gravado (parâmetros e resultado)."""
    caminho = _caminho_calculo(s)
    if not os.path.exists(caminho):
        return {"calculo": None}
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {"calculo": None}
    return {"calculo": dados.get("resultado"), "parametros": dados.get("parametros") or {},
            "quando": dados.get("quando")}


def geometria_para_calculo(s: str) -> dict:
    """GET /api/projetos/<s>/calculo/geometria: o que o diálogo precisa saber do modelo
    antes de calcular (tesouras, vão, cota do apoio, peso da telha)."""
    from nucleo3d import calculo_ifc
    doc = _documento3d_do_projeto(s)
    nomes = _nomes_producao(s)
    g = calculo_ifc.geometria_do_modelo(doc, nomes) if nomes else {"tesouras": 0, "avisos": []}
    g["detalhado"] = bool(nomes)
    g["padrao"] = {k: v for k, v in calculo_ifc.PARAMETROS_PADRAO.items() if k != "trocas"}
    anterior = calculo_do_projeto(s)
    g["parametros"] = anterior.get("parametros") or {}
    return g


def calcular_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/calcular {parametros, trocas, comparar}: monta o modelo de
    cálculo a partir dos sólidos do IFC, analisa, verifica e grava em calculo.json.

    `parametros` sobrepõe os do cálculo anterior (os demais ficam); `trocas` {marca: perfil}
    substitui a lista anterior de perfis de cálculo; `comparar` devolve em `antes` o
    aproveitamento e o perfil de cada peça no cálculo anterior."""
    from nucleo3d import calculo_ifc
    try:
        _progresso(s, "abrindo o modelo…")
        doc = _documento3d_do_projeto(s)
        nomes = _nomes_producao(s)
        if not nomes:
            raise ErroDeDados("gere o detalhamento primeiro (Desenho 2D → Detalhar peças e conjuntos): "
                              "é ele que classifica tesouras, terças e contraventamentos.")
        anterior = calculo_do_projeto(s)
        par = dict(anterior.get("parametros") or {})
        par.update({k: v for k, v in (corpo.get("parametros") or {}).items()})
        if "trocas" in corpo:
            par["trocas"] = {str(k): str(v) for k, v in (corpo.get("trocas") or {}).items() if v}
        r = calculo_ifc.calcular(doc, nomes, par,
                                 avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
        r["parametros"] = par
        ant = anterior.get("calculo") or {}
        if corpo.get("comparar") and ant.get("elementos"):
            r["antes"] = {m: {"aproveitamento": el.get("aproveitamento"), "perfil": el.get("perfil"),
                              "ok": el.get("ok")} for m, el in ant["elementos"].items()}
        from projetos import _gravar_json
        _gravar_json(_caminho_calculo(s), {"parametros": par, "resultado": {k: v for k, v in r.items() if k != "antes"},
                                          "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
        _gerente().tocar(s)
        return r
    finally:
        _fim_progresso(s)


def _progresso(s: str, etapa: str):
    PROGRESSO[s] = {"etapa": str(etapa), "quando": time.time()}


def _fim_progresso(s: str):
    PROGRESSO.pop(s, None)


def progresso_do_projeto(s: str) -> dict:
    p = PROGRESSO.get(s)
    if not p:
        return {"etapa": "", "ha_s": 0}
    return {"etapa": p["etapa"], "ha_s": round(time.time() - p["quando"], 1)}


def _conferir_eixos_das_chapas(s: str, doc) -> dict:
    """Chapas convertidas por versões anteriores (eixos por peça, `eixos_conferidos`
    ausente) são refeitas a partir do IFC de origem do projeto, todas no mesmo sistema
    — ver nucleo2d.detalhar.reorientar_chapas. Uma vez por projeto; sem o IFC, ficam
    como estão (o espelhamento continua a ser adivinhado pelos furos)."""
    from nucleo3d.modelo import Chapa
    pendentes = [e for e in doc.entidades.values() if isinstance(e, Chapa)
                 and (e.atributos or {}).get("convertida_de") == "solido" and not (e.atributos or {}).get("eixos_conferidos")]
    if not pendentes:
        return {}
    g = _gerente()
    nome = _identificacao_do_projeto(s).get("origem_ifc") or ""
    caminho = os.path.join(g._existente(s), "origem", nome) if nome else ""
    if not nome or not os.path.exists(caminho):
        return {"aviso": "%d chapa(s) convertidas por versão anterior sem o IFC de origem no projeto: eixos não conferidos" % len(pendentes)}
    from ifc import importar as imp
    from nucleo2d import detalhar as det
    _progresso(s, "conferindo os eixos de %d chapas pelo IFC de origem (leva uns 20 s)…" % len(pendentes))
    doc_ifc = imp.importar(caminho)
    _progresso(s, "reorientando as chapas…")
    r = det.reorientar_chapas(doc, doc_ifc)
    if r.get("chapas"):
        g.salvar_modelo(s, doc.dict(), marco=True)
        print("[detalhamento] %s: %d chapa(s) de %d posição(ões) reorientadas pelo IFC; %d parafuso(s) movidos"
              % (s, r["chapas"], r["posicoes"], r["parafusos"]))
    return r


def detalhar_posicao_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/detalhar-posicao {marca}: desenho "Detalhe – <marca>" da
    peça. Chapa plana vinda do IFC é antes convertida em Chapa paramétrica (contorno +
    furos) no modelo, para o detalhe ser um "bloco" ligado ao 3D: os furos mexidos no
    desenho voltam para as chapas com /aplicar-furos."""
    from nucleo2d import detalhar as det
    marca = str(corpo.get("marca") or "").strip()
    if not marca:
        raise ErroDeDados("informe a marca da posição.")
    g = _gerente()
    doc = _documento3d_do_projeto(s)
    try:
        reorientadas = _conferir_eixos_das_chapas(s, doc)
    finally:
        _fim_progresso(s)
    convertidas = (det.converter_chapas(doc, marca, referencia=str(corpo.get("referencia") or "") or None)
                   if corpo.get("converter", True) is not False else 0)
    if convertidas:
        g.salvar_modelo(s, doc.dict(), marco=True)
    desenho, pos = det.detalhar_posicao(doc, marca, ajustes=_ajustes_furos(s), nomes=_nomes_producao(s))
    nome = desenho.nome
    if corpo.get("substituir", True) is not False and os.path.exists(g._caminho_desenho(s, nome)):
        g.excluir_desenho(s, nome)
    desenho.metadados["gerado_por"] = "detalhamento"
    salvo = g.salvar_desenho(s, nome, desenho.dict())
    return {"nome": salvo["nome"], "titulo": nome, "marca": marca, "classe": pos.classe,
            "convertidas": convertidas, "reorientadas": reorientadas.get("chapas", 0),
            "editavel": desenho.metadados["detalhe_posicao"]["editavel"],
            "furos": len(desenho.metadados["detalhe_posicao"]["furos"]), "quantidade": pos.quantidade}


def aplicar_furos_do_desenho(s: str, nome: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/desenhos/<nome>/aplicar-furos: lê os furos da camada FURO
    do desenho de detalhe (o gravado, ou `desenho` no corpo), escreve nas chapas
    paramétricas da posição e regrava o modelo e o detalhe regenerado."""
    from nucleo2d import detalhar as det
    from nucleo2d.desenho import Desenho
    from nucleo3d.modelo import Chapa
    g = _gerente()
    d = Desenho.de_dict(corpo["desenho"]) if isinstance(corpo.get("desenho"), dict) else Desenho.de_dict(g.abrir_desenho(s, nome))
    meta = d.metadados.get("detalhe_posicao") or {}
    doc = _documento3d_do_projeto(s)
    _conferir_eixos_das_chapas(s, doc)
    ajustes = _ajustes_furos(s)

    barras3d = {"barras": 0, "furos": 0, "posicoes": []}

    def vincular(marca_, originais_, furos_):
        # a chapinha do suporte mudou de furação: as terças com a mesma furação original
        # acompanham; a furação delas fica guardada no projeto e vai também para as
        # malhas das terças no 3D
        lev = det.levantar(doc, ajustes=ajustes)
        vinc = det.vincular_furos_de_ligacao(lev["posicoes"], lev["camadas"], marca_, originais_, furos_)
        if vinc:
            ajustes.update(vinc)
            _gravar_ajustes_furos(s, ajustes)
        r3 = det.aplicar_furos_nas_barras(doc, ajustes)
        if r3["barras"]:
            barras3d.update(r3)
            g.salvar_modelo(s, doc.dict(), marco=True)
        return sorted(vinc)
    def aplicar_em_barra(marca_, furos_):
        # barra (terça, diagonal…): a furação nova fica como ajuste do projeto e os furos
        # da malha 3D são movidos, furo a furo; furo novo ou apagado só vale no desenho
        r_ = det.aplicar_furos_de_barra(doc, marca_, furos_, ajustes)
        _gravar_ajustes_furos(s, ajustes)
        if r_["barras3d"].get("barras"):
            g.salvar_modelo(s, doc.dict(), marco=True)
        barras3d.update(r_["barras3d"])
        return r_
    if meta.get("marca"):
        # desenho "Detalhe – P77": uma célula em (0, 0), furos originais guardados
        if not meta.get("editavel"):
            raise ErroDeDados("os furos desta posição não são editáveis (só chapa plana convertida em chapa paramétrica).")
        marca = meta["marca"]
        contorno, _ = det.contorno_do_desenho(d, marca)
        furos = det.furos_do_desenho(d)
        if meta.get("classe") == "barra":
            r = aplicar_em_barra(marca, furos)
            vinculadas = []
        else:
            r = det.aplicar_furos(doc, marca, furos, meta.get("furos") or [], contorno)
            g.salvar_modelo(s, doc.dict(), marco=True)
            vinculadas = vincular(marca, meta.get("furos") or [], furos)
        novo, pos = det.detalhar_posicao(doc, marca, ajustes=ajustes, nomes=_nomes_producao(s))
        if os.path.exists(g._caminho_desenho(s, novo.nome)):
            g.excluir_desenho(s, novo.nome)
        novo.metadados["gerado_por"] = "detalhamento"
        salvo = g.salvar_desenho(s, novo.nome, novo.dict())
        return dict(r, nome=salvo["nome"], marca=marca, quantidade=pos.quantidade, vinculadas=vinculadas, barras3d=barras3d)
    # desenho geral (Detalhamento – chapas): a célula da posição pedida
    marca = str(corpo.get("marca") or "").strip()
    geral = d.metadados.get("detalhamento") or {}
    if not marca:
        raise ErroDeDados("selecione a chapa (contorno, furo ou título) cujos furos vão para o modelo.")
    if marca not in (geral.get("editaveis") or []):
        raise ErroDeDados("a posição %s não tem furos editáveis neste desenho: gere o detalhamento de novo ou abra a peça pelo 3D." % marca)
    contorno, origem = det.contorno_do_desenho(d, marca)
    if contorno is None:
        origem = det._origem_da_celula(d, marca)
    furos = det.furos_do_desenho(d, marca, origem)
    nomes_m = [m.strip() for m in marca.split(" / ")]
    tem_chapa = any(isinstance(e, Chapa) and str(((e.atributos or {}).get("marcas") or {}).get("posicao")) in nomes_m
                    for e in doc.entidades.values())
    if not tem_chapa:
        r = aplicar_em_barra(marca, furos)
        vinculadas = []
    else:
        originais = (geral.get("furos_originais") or {}).get(marca)
        if originais is None:
            primeira = next((e for e in doc.entidades.values() if isinstance(e, Chapa)
                             and str(((e.atributos or {}).get("marcas") or {}).get("posicao")) == marca), None)
            originais = det.furos_da_chapa(primeira) if primeira else []
        r = det.aplicar_furos(doc, marca, furos, originais, contorno)
        g.salvar_modelo(s, doc.dict(), marco=True)
        vinculadas = vincular(marca, originais, furos)
    det.regenerar_celula(d, doc, marca, ajustes=ajustes, nomes_producao=_nomes_producao(s))
    salvo = g.salvar_desenho(s, nome, d.dict())
    return dict(r, nome=salvo["nome"], marca=marca, vinculadas=vinculadas, barras3d=barras3d)


def _nomes_producao(s: str) -> dict:
    """Nomes de produção já dados (detalhamento/nomes.json): {"posicoes": {marca: nome}, "conjuntos": {...}}."""
    caminho = os.path.join(_gerente()._existente(s), "detalhamento", "nomes.json")
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_nomes_producao(s: str, nomes: dict):
    pasta = os.path.join(_gerente()._existente(s), "detalhamento")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "nomes.json"), "w", encoding="utf-8") as f:
        json.dump({k: nomes.get(k) or {} for k in ("posicoes", "conjuntos", "tipos", "tipos_conjuntos", "ifc", "ifc_conjuntos", "camadas_2d")},
                  f, ensure_ascii=False, indent=1)


def _nomes_no_modelo(doc, nomes: dict) -> int:
    from ifc.importar import pilar_pela_geometria
    """Escreve marcas.nome / marcas.nome_conjunto nas peças do modelo 3D (a busca do
    editor acha "S.T.1"). Devolve quantas mudaram."""
    ifc = nomes.get("ifc") or {}
    ifc_conj = nomes.get("ifc_conjuntos") or {}
    n = 0
    for e in doc.entidades.values():
        m = (e.atributos or {}).get("marcas")
        if not isinstance(m, dict):
            continue
        novo = ifc.get(str(m.get("posicao") or "")) or ""
        novo_c = ifc_conj.get(str(m.get("conjunto") or "")) or ""
        if (m.get("nome") or "") != novo or (m.get("nome_conjunto") or "") != novo_c:
            m["nome"], m["nome_conjunto"] = novo, novo_c
            n += 1
        # modelos importados antes da 0.6.13: montantes e diagonais (IfcColumn do
        # TecnoMETAL) estavam na camada Pilares; a regra da geometria os leva a Vigas
        if getattr(e, "camada", "") == "Pilares" and getattr(e, "vertices", None) and not pilar_pela_geometria(e.vertices):
            e.camada = "Vigas"
            n += 1
    return n


def _ajustes_furos(s: str) -> dict:
    """Furação guardada no projeto (vínculo chapa → terças): detalhamento/ajustes-furos.json."""
    caminho = os.path.join(_gerente()._existente(s), "detalhamento", "ajustes-furos.json")
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_ajustes_furos(s: str, ajustes: dict):
    pasta = os.path.join(_gerente()._existente(s), "detalhamento")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "ajustes-furos.json"), "w", encoding="utf-8") as f:
        json.dump(ajustes, f, ensure_ascii=False, indent=1)


def _identificacao_do_projeto(s: str) -> dict:
    p = _gerente().ler(s)
    return {k: p.get(k, "") for k in ("nome", "cliente", "local", "responsavel", "origem_ifc")}


def lista_de_materiais(s: str, recalcular: bool = False, corpo: Optional[dict] = None) -> dict:
    """A lista de materiais do projeto (GET /api/projetos/<s>/materiais). Lê a gravada pelo
    último detalhamento; sem ela, ou com `recalcular`, levanta de novo do modelo e grava.

    corpo (POST): {barra: 0|6000|12000, regra_tercas: bool}"""
    from nucleo2d.detalhar import levantar
    from saida import lista_producao
    g = _gerente()
    pasta = os.path.join(g._existente(s), "detalhamento")
    caminho = os.path.join(pasta, lista_producao.ARQUIVO_JSON)
    corpo = corpo or {}
    if not recalcular and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            lista = json.load(f)
    else:
        doc = _documento3d_do_projeto(s)
        nomes = _nomes_producao(s)
        lev = levantar(doc, regra_tercas=corpo.get("regra_tercas", True) is not False, ajustes=_ajustes_furos(s), nomes=nomes)
        lista = lista_producao.montar(lev["posicoes"], lev["categorias"], lev["acessorios"], pecas=lev["pecas"],
                                      barra=float(corpo.get("barra") or 0), projeto=_identificacao_do_projeto(s),
                                      nomes_conjuntos=nomes.get("ifc_conjuntos"))
        lista_producao.gravar(pasta, lista, lev["posicoes"], lev["acessorios"])
        g.tocar(s)
    arquivos = {}
    for chave, nome in (("json", lista_producao.ARQUIVO_JSON), ("html", lista_producao.ARQUIVO_HTML),
                        ("pdf", lista_producao.ARQUIVO_PDF), ("romaneio", "romaneio.csv"),
                        ("perfis", "resumo-perfis.csv"), ("chapas", "resumo-chapas.csv"), ("conjuntos", "conjuntos.csv")):
        cam = os.path.join(pasta, nome)
        if os.path.exists(cam):
            arquivos[chave] = _descrever_arquivo(cam, pasta)
    lista["arquivos"] = arquivos
    lista["projeto"] = dict(lista.get("projeto") or {}, slug=s, **_identificacao_do_projeto(s))
    return lista


def pdf_da_lista_de_materiais(s: str) -> dict:
    """POST /api/projetos/<s>/materiais/pdf: imprime a lista gravada (gera se não houver)."""
    from saida import lista_producao
    lista = lista_de_materiais(s)
    pasta = os.path.join(_gerente()._existente(s), "detalhamento")
    pdf = lista_producao.gerar_pdf(pasta, lista)
    return {"pdf": _descrever_arquivo(pdf, pasta)}


REPOSITORIO = "elieberduarte/metalica"


def _versao_tupla(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def verificar_atualizacao() -> dict:
    """Consulta a última versão publicada no GitHub (releases) e diz se há uma mais nova
    que esta. Sem internet, devolve `disponivel: None` em vez de erro: a tela segue."""
    import urllib.request
    fora = {"atual": versao.VERSAO, "ultima": None, "nova": False, "url": None, "arquivo": None, "disponivel": None}
    try:
        req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % REPOSITORIO,
                                     headers={"User-Agent": "Metalica/" + versao.VERSAO, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001 — sem rede, sem release, limite da API
        fora["erro"] = str(e)[:120]
        return fora
    ultima = str(dados.get("tag_name") or dados.get("name") or "").lstrip("vV")
    fora.update({"ultima": ultima, "url": dados.get("html_url"), "disponivel": True,
                 "nova": _versao_tupla(ultima) > _versao_tupla(versao.VERSAO),
                 "publicada": (dados.get("published_at") or "")[:10]})
    for a in dados.get("assets") or []:
        if str(a.get("name", "")).lower().endswith(".exe"):
            fora["arquivo"] = a.get("browser_download_url")
            fora["tamanho_mb"] = round((a.get("size") or 0) / 1048576, 1)
            break
    return fora


ARQUIVO_REABRIR = "reabrir.json"


def limpar_instaladores_antigos() -> int:
    """Apaga da pasta temporária os instaladores baixados pelas atualizações anteriores
    (30 MB cada; sem isto, cada atualização deixava um) e o .cmd da troca. Devolve
    quantos arquivos saíram."""
    import glob
    import tempfile
    n = 0
    pasta = tempfile.gettempdir()
    for padrao in ("Metalica-*-instalador*.exe", "Metalica-*-instalador*.exe.parcial", "metalica-atualizar.cmd"):
        for arq in glob.glob(os.path.join(pasta, padrao)):
            try:
                if time.time() - os.path.getmtime(arq) < 120:
                    continue                          # pode ser o da troca em curso
                os.remove(arq)
                n += 1
            except OSError:
                pass
    return n


def _gravar_reabrir(caminho: str):
    """Guarda em que tela o programa deve reabrir depois da atualização (só caminhos
    desta interface, como "/cad?projeto=x&desenho=y")."""
    if not isinstance(caminho, str) or not caminho.startswith("/") or caminho.startswith("//"):
        return
    try:
        with open(os.path.join(PROJETOS, ARQUIVO_REABRIR), "w", encoding="utf-8") as f:
            json.dump({"caminho": caminho[:2000], "quando": time.time()}, f)
    except OSError:
        pass


def _url_para_reabrir(base: str) -> str:
    """A URL inicial: a tela gravada por _gravar_reabrir, se foi há menos de 15 min."""
    arq = os.path.join(PROJETOS, ARQUIVO_REABRIR)
    try:
        with open(arq, encoding="utf-8") as f:
            dados = json.load(f)
        os.remove(arq)
        caminho = str(dados.get("caminho") or "")
        if caminho.startswith("/") and time.time() - float(dados.get("quando") or 0) < 900:
            return base.rstrip("/") + caminho
    except (OSError, ValueError, TypeError):
        pass
    return base


def instalar_atualizacao(corpo: Optional[dict] = None) -> dict:
    """Baixa o instalador da última release e o executa em silêncio; este processo se
    encerra e o instalador reabre o programa no fim. Só no programa instalado.
    `corpo.reabrir`: caminho da tela em que o programa deve voltar (o desenho aberto)."""
    import subprocess
    import tempfile
    import urllib.request
    if corpo and corpo.get("reabrir"):
        _gravar_reabrir(corpo.get("reabrir"))
    if not versao.CONGELADO:
        raise ErroDeDados("a atualização automática só vale para o programa instalado; "
                          "no desenvolvimento, use git pull.")
    info = verificar_atualizacao()
    if not info.get("nova") or not info.get("arquivo"):
        raise ErroDeDados("não há versão mais nova com instalador publicado.")
    # nome único por tentativa: o instalador anterior pode estar aberto ou preso pelo
    # antivírus, e a troca de nome sobre ele dá "acesso negado" (WinError 5)
    destino = os.path.join(tempfile.gettempdir(), "Metalica-%s-instalador-%d.exe" % (info["ultima"], int(time.time())))
    req = urllib.request.Request(info["arquivo"], headers={"User-Agent": "Metalica/" + versao.VERSAO})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino + ".parcial", "wb") as f:
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
    tamanho = os.path.getsize(destino + ".parcial")
    if tamanho < 5 * 1048576:
        raise ErroDeDados("o instalador baixado veio incompleto (%d bytes)." % tamanho)
    from projetos import trocar_arquivo
    trocar_arquivo(destino + ".parcial", destino, espera=30.0)   # o Defender segura o .exe recém-baixado uns segundos
    exe_atual = sys.executable
    # instala em silêncio e reabre o programa, por um .cmd em disco (a linha de comando
    # com aspas dentro de aspas passada ao cmd /c não era interpretada inteira); roda
    # separado deste processo, que fecha. O instalador também reabre o programa por
    # conta própria quando roda em silêncio ([Run] com Check: WizardSilent).
    lote = os.path.join(tempfile.gettempdir(), "metalica-atualizar.cmd")
    linhas = [
        "@echo off",
        "timeout /t 2 /nobreak >nul",
        '"%s" /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS' % destino,
        "timeout /t 3 /nobreak >nul",
        'del /q "%s" >nul 2>&1' % destino,                # o instalador já cumpriu o papel
        'if not exist "%s" exit /b 1' % exe_atual,
        'tasklist /fi "imagename eq Metalica.exe" | find /i "Metalica.exe" >nul || start "" "%s"' % exe_atual,
    ]
    with open(lote, "w", encoding="cp1252", errors="replace", newline="") as f:
        f.write("\r\n".join(linhas) + "\r\n")
    subprocess.Popen(["cmd.exe", "/c", lote], creationflags=0x00000008 | 0x00000200,   # DETACHED | NEW_PROCESS_GROUP
                     close_fds=True, cwd=tempfile.gettempdir())

    def sair():
        time.sleep(1.5)
        os._exit(0)
    threading.Thread(target=sair, daemon=True).start()
    return {"baixado": destino, "tamanho_mb": round(tamanho / 1048576, 1), "versao": info["ultima"],
            "mensagem": "Instalando a versão %s: o programa vai fechar e reabrir sozinho." % info["ultima"]}


def montar_pranchas_projeto(s: str, corpo: dict) -> dict:
    """Pranchas a partir de desenhos 2D do projeto: uma célula por posição/conjunto dos
    desenhos de detalhamento, ou o desenho inteiro, em folhas ISO com carimbo.

    corpo: {desenhos: [nome | {nome, escala, chaves: [posições/conjuntos]}], formato: "A1", titulo: "Prancha",
            carimbo: {obra, cliente, responsavel, crea, revisao, data, titulo, subtitulo},
            substituir: bool}"""
    from nucleo2d.desenho import Desenho
    from nucleo2d.pranchas import montar_pranchas
    g = _gerente()
    pedidos = corpo.get("desenhos") or []
    if not pedidos:
        raise ErroDeDados("escolha ao menos um desenho para a prancha.")
    fontes = []
    for item in pedidos:
        nome = item.get("nome") if isinstance(item, dict) else str(item)
        d = Desenho.de_dict(g.abrir_desenho(s, nome))
        if d.metadados.get("prancha"):
            raise ErroDeDados("\"%s\" já é uma prancha; escolha os desenhos de origem." % d.nome)
        fontes.append({"nome": _slug(nome), "desenho": d,
                       "escala": (item.get("escala") if isinstance(item, dict) else None),
                       "chaves": (item.get("chaves") if isinstance(item, dict) else None)})
    p = g.ler(s)
    carimbo = {"obra": p.get("nome") or s, "cliente": p.get("cliente") or "",
               "responsavel": p.get("responsavel") or "", "revisao": "00"}
    carimbo.update({k: v for k, v in (corpo.get("carimbo") or {}).items() if v not in (None, "")})
    titulo = (corpo.get("titulo") or "Prancha").strip() or "Prancha"
    folhas = montar_pranchas(fontes, formato=corpo.get("formato") or "A1", carimbo=carimbo, titulo=titulo,
                             indice=corpo.get("indice", True) is not False)
    if corpo.get("substituir", True) is not False:
        # apaga as pranchas anteriores com o mesmo título-base (Prancha 01, 02, …)
        for d in g.listar_desenhos(s, contar=False):
            if d["nome"].startswith(_slug(titulo) + "-") and d["nome"][len(_slug(titulo)) + 1:].isdigit():
                g.excluir_desenho(s, d["nome"])
    saida = []
    for folha in folhas:
        folha.metadados["gerado_por"] = "pranchas"
        salvo = g.salvar_desenho(s, folha.nome, folha.dict())
        saida.append({"nome": salvo["nome"], "titulo": folha.nome, "entidades": folha.tamanho,
                      "celulas": len(folha.metadados["prancha"]["celulas"])})
    g.tocar(s)
    return {"pranchas": saida, "formato": corpo.get("formato") or "A1"}


def importar_dxf_no_desenho(s: str, corpo: dict) -> dict:
    """DXF (texto) → entidades do CAD, para o desenho aberto acrescentar como um comando.

    corpo: {conteudo: texto do DXF, escala: do desenho de destino, fator: mm por unidade
            (None = pelo $INSUNITS), deslocamento: [x, y], prefixo_camada: ""}"""
    from nucleo2d.desenho import Desenho
    from nucleo2d.dxf_ler import para_desenho
    from dataclasses import asdict
    texto = corpo.get("conteudo")
    if not isinstance(texto, str) or not texto.strip():
        raise ErroDeDados("mande o conteúdo do DXF em texto.")
    fator = corpo.get("fator")
    d = Desenho(nome="importado", escala=float(corpo.get("escala") or 1.0))
    desl = corpo.get("deslocamento") or [0.0, 0.0]
    _, resumo = para_desenho(texto, escala=d.escala, fator=float(fator) if fator else None, destino=d,
                             deslocamento=(float(desl[0]), float(desl[1])),
                             prefixo_camada=str(corpo.get("prefixo_camada") or ""))
    return {"entidades": [asdict(e) for e in d.entidades.values()],
            "camadas": {k: asdict(v) for k, v in d.camadas.items() if k in resumo["camadas_novas"]},
            "resumo": {k: v for k, v in resumo.items() if k != "ids"}}


def exportar_desenho_pdf(s: str, nome: str, corpo: dict) -> dict:
    """PDF de um desenho (ou, com `desenhos: [...]`, de vários numa só saída): prancha no
    tamanho da folha, desenho comum no tamanho do desenho na sua escala."""
    from nucleo2d.desenho import Desenho
    from nucleo2d.pranchas import pdf_dos_desenhos
    g = _gerente()
    nomes = corpo.get("desenhos") or [nome]
    desenhos = []
    for n in nomes:
        if n == nome and isinstance(corpo.get("desenho"), dict):
            desenhos.append(Desenho.de_dict(corpo["desenho"]))
        else:
            desenhos.append(Desenho.de_dict(g.abrir_desenho(s, n)))
    pasta = os.path.join(g._existente(s), "pranchas" if any(d.metadados.get("prancha") for d in desenhos) else "desenhos-2d")
    base = corpo.get("arquivo") or (_slug(nome) if len(nomes) == 1 else _slug(corpo.get("titulo") or "pranchas"))
    caminho = pdf_dos_desenhos(desenhos, os.path.join(pasta, base + ".pdf"))
    g.tocar(s)
    return {"arquivo": _descrever_arquivo(caminho, pasta), "paginas": len(desenhos)}


def exportar_desenho_dxf(s: str, nome: str, corpo: dict) -> dict:
    from nucleo2d.desenho import Desenho
    g = _gerente()
    fonte = corpo.get("desenho") if isinstance(corpo.get("desenho"), dict) else g.abrir_desenho(s, nome)
    desenho = Desenho.de_dict(fonte)
    pasta = os.path.join(g._existente(s), "desenhos-2d")
    escala = corpo.get("escala")
    caminho = desenho.para_dxf(float(escala) if escala else None).gravar(
        os.path.join(pasta, _slug(nome) + ".dxf"))
    return {"arquivo": _descrever_arquivo(caminho, pasta), "entidades": desenho.tamanho}


def _alterado_modelo(s: str) -> float:
    caminho = _gerente().caminho_modelo(s)
    try:
        return round(os.path.getmtime(caminho), 3)
    except OSError:
        return 0.0


MAQUINA = platform.node() or "esta máquina"
try:
    USUARIO = getpass.getuser()
except Exception:                                                     # noqa: BLE001
    USUARIO = ""


def modelo_do_projeto(s: str) -> dict:
    g = _gerente()
    outro = g.aberto_por(s)
    if outro and outro.get("maquina") == MAQUINA:
        outro = None                                   # a própria máquina (outra janela) não é aviso
    doc = g.abrir_modelo(s)
    g.marcar_aberto(s, MAQUINA, USUARIO)
    return {"documento": doc, "existe": doc is not None, "alterado": _alterado_modelo(s), "aberto_por": outro}



# ----------------------------------------------------------- modelo 3D e IFC

MODELOS = os.path.join(PROJETOS, "modelos")


def _documento_de(corpo: dict):
    from nucleo3d.modelo import Documento
    d = corpo.get("documento", corpo)
    if not isinstance(d, dict):
        raise ErroDeDados("documento 3D ausente ou inválido.")
    return Documento.de_dict(d)


def catalogo_de_pecas(q: dict) -> dict:
    """GET /api/catalogo/pecas: o catálogo de peças (perfis, chapas, barras, parafusos).

    Sem parâmetros devolve as famílias e o resumo — é o que a tela precisa para abrir.
    `familia` traz os itens de uma família, `q` busca pelo nome ou pelas dimensões e
    `alternativas` devolve o que pode entrar no lugar de uma peça, com a diferença de
    massa por metro."""
    from nucleo import catalogo
    um = lambda k, padrao="": (q.get(k) or [padrao])[0]          # noqa: E731
    nome = um("alternativas")
    if nome:
        return {"peca": (catalogo.item(nome).dict() if catalogo.item(nome) else None),
                "alternativas": catalogo.alternativas(
                    nome, modo=um("modo", "vizinhos"),
                    mesma_altura=um("mesma_altura") in ("1", "true"),
                    limite=int(um("limite", "30") or 30))}
    familia = um("familia")
    texto = um("q")
    if familia or texto:
        lista = catalogo.buscar(texto, familia or None, limite=int(um("limite", "400") or 400)) \
            if texto else catalogo.itens(familia)
        return {"familia": familia, "q": texto, "itens": [i.dict() for i in lista]}
    return {"familias": catalogo.familias(), "resumo": catalogo.resumo()}


def catalogo_3d() -> dict:
    """Perfis com a seção já pronta para o editor desenhar."""
    from nucleo.perfis import banco
    from nucleo import materiais as mat
    from nucleo3d.modelo import Documento
    saida = {"perfis": [], "materiais": [], "acos": [a.nome for a in mat.ACOS.values()]}
    try:
        from nucleo3d import geometria
    except Exception:
        geometria = None
    for tipo, lista in banco().por_tipo.items():
        for perf in lista:
            reg = {"nome": perf.nome, "tipo": tipo, "massa": perf.massa,
                   "d": perf.d, "bf": perf.bf, "tw": perf.tw, "tf": perf.tf,
                   "A": perf.A}
            if geometria is not None:
                try:
                    reg["secao"] = geometria.secao(perf)
                except Exception:
                    pass
            saida["perfis"].append(reg)
    doc = Documento()
    saida["materiais"] = [{"nome": m.nome, "cor": m.cor, "opacidade": m.opacidade,
                           "metalico": m.metalico, "rugosidade": m.rugosidade,
                           "aco": m.aco} for m in doc.materiais.values()]
    saida["camadas"] = [{"nome": c.nome, "cor": c.cor} for c in doc.camadas.values()]
    return saida


def malhas_do_documento(corpo: dict) -> dict:
    """Converte barras e chapas em malhas para a cena do navegador."""
    from nucleo3d import geometria
    doc = _documento_de(corpo)
    somente = set(corpo.get("ids") or [])
    saida = {}
    for ent in doc.entidades.values():
        if somente and ent.id not in somente:
            continue
        try:
            if ent.tipo == "barra":
                v, f = geometria.malha_barra(ent)
            elif ent.tipo == "chapa":
                v, f = geometria.malha_chapa(ent)
            elif ent.tipo == "solido":
                v, f = ent.vertices, ent.faces
            else:
                continue
            saida[ent.id] = {"vertices": [c for p in v for c in p],
                             "faces": f, "tipo": ent.tipo}
        except Exception as e:
            saida[ent.id] = {"erro": str(e)}
    return {"malhas": saida}


def exportar_ifc(corpo: dict) -> dict:
    from ifc import exportar as exp
    doc = _documento_de(corpo)
    nome = _slug(corpo.get("nome") or doc.nome or "modelo")
    do_projeto, base = _pasta_do_projeto(corpo, nome)
    pasta = os.path.join(base, "ifc")
    caminho = exp.exportar(doc, os.path.join(pasta, nome + ".ifc"),
                           projeto_nome=doc.nome,
                           autor=corpo.get("autor") or "",
                           organizacao=corpo.get("organizacao") or "")
    return {"arquivo": _descrever_arquivo(caminho, pasta),
            "entidades": len(doc.entidades)}


def _gravar_ifc_recebido(corpo: dict, nome_padrao: str) -> str:
    """Grava o IFC que veio em base64 e devolve o caminho."""
    import base64
    dados = corpo.get("conteudo_b64")
    if not dados:
        raise ErroDeDados("nenhum arquivo IFC recebido.")
    nome = os.path.basename(corpo.get("nome") or nome_padrao)
    os.makedirs(MODELOS, exist_ok=True)
    destino = os.path.join(MODELOS, _slug(os.path.splitext(nome)[0]) + ".ifc")
    with open(destino, "wb") as f:
        f.write(base64.b64decode(dados))
    return destino


def importar_ifc(corpo: dict) -> dict:
    from ifc import importar as imp
    destino = _gravar_ifc_recebido(corpo, "importado.ifc")
    doc = imp.importar(destino)
    return {"documento": doc.dict(),
            "relatorio": doc.metadados.get("importacao", {}),
            "estatisticas": doc.estatisticas()}


def inspecionar_ifc(corpo: dict) -> dict:
    from ifc import importar as imp
    destino = _gravar_ifc_recebido(corpo, "previa.ifc")
    return imp.inspecionar(destino)


def detalhar_ifc(corpo: dict) -> dict:
    """Detalhamento de peças para produção: DXF único, romaneio e relatório."""
    from saida import detalhamento
    destino = _gravar_ifc_recebido(corpo, "detalhar.ifc")
    nome = _slug(os.path.splitext(os.path.basename(corpo.get("nome") or "modelo"))[0])
    do_projeto, base = _pasta_do_projeto(corpo, nome)
    pasta = os.path.join(base, "detalhamento")
    rel = detalhamento.gerar(destino, pasta)
    if do_projeto:
        _gerente().tocar(do_projeto)
    rel["arquivos"] = {k: _descrever_arquivo(v, pasta) for k, v in rel["arquivos"].items()}
    rel["arquivos"]["relatorio"] = _descrever_arquivo(os.path.join(pasta, "relatorio.json"), pasta)
    rel["pasta"] = pasta
    return rel


def modelo_do_galpao(corpo: dict) -> dict:
    from nucleo3d import de_projeto
    from nucleo.galpao import dimensionar as calcular
    dados = _dados_de(corpo.get("dados", corpo))
    projeto = calcular(dados)
    doc = de_projeto.modelo_do_galpao(projeto)
    # telhas e paredes formam uma caixa fechada que esconde a estrutura: no editor a
    # camada de fechamento começa oculta, e o usuário a liga no painel de camadas
    if "Fechamento" in doc.camadas:
        doc.camadas["Fechamento"].visivel = False
    return {"documento": doc.dict(), "estatisticas": doc.estatisticas(),
            "avisos": projeto.avisos, "erros": projeto.erros}


def analise_do_galpao(corpo: dict) -> dict:
    """Mapa de esforços do galpão: diagramas, deformada, cargas e aproveitamentos.

    Recalcula o galpão a partir dos mesmos dados do modelo 3D. É uma conta cara, por
    isso o editor só a pede quando o usuário manda calcular a estrutura.
    """
    from nucleo3d import mapa_esforcos
    from nucleo.galpao import dimensionar as calcular
    dados = _dados_de(corpo.get("dados", corpo))
    projeto = calcular(dados)
    mapa = mapa_esforcos.mapa_de_esforcos(projeto)
    mapa["avisos"] = projeto.avisos
    mapa["erros"] = projeto.erros
    return mapa


def salvar_modelo(corpo: dict) -> dict:
    doc = _documento_de(corpo)
    os.makedirs(MODELOS, exist_ok=True)
    nome = _slug(corpo.get("nome") or doc.nome or "modelo")
    caminho = os.path.join(MODELOS, nome + ".modelo.json")
    # grava num temporário e troca de uma vez: a gravação automática do editor manda
    # dezenas de megabytes, e quem abrir o modelo no meio não pode ler metade
    from projetos import _gravar_json
    _gravar_json(caminho, doc.dict())
    return {"salvo": os.path.basename(caminho), "entidades": len(doc.entidades)}


def abrir_modelo(nome: str) -> dict:
    caminho = os.path.join(MODELOS, os.path.basename(nome))
    if not caminho.endswith(".modelo.json"):
        caminho += ".modelo.json"
    if not os.path.exists(caminho):
        raise ErroDeDados("modelo não encontrado: " + nome)
    with open(caminho, encoding="utf-8") as f:
        return {"documento": json.load(f)}


def listar_modelos() -> list:
    if not os.path.isdir(MODELOS):
        return []
    saida = []
    for f in sorted(os.listdir(MODELOS)):
        if f.endswith(".modelo.json"):
            caminho = os.path.join(MODELOS, f)
            saida.append({"arquivo": f, "nome": f[:-12],
                          "tamanho_kb": round(os.path.getsize(caminho) / 1024, 1)})
    return saida


# ----------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    server_version = "Metalica/1.0"

    def log_message(self, formato, *args):
        if "--verboso" in sys.argv:
            super().log_message(formato, *args)

    # -- utilidades --
    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, mensagem, status=400, detalhe=""):
        self._json({"erro": str(mensagem), "detalhe": detalhe}, status)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        if n > 400 * 1024 * 1024:
            raise ErroDeDados("arquivo grande demais (limite de 400 MB).")
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ErroDeDados(f"JSON inválido: {e}")

    def _arquivo(self, caminho, raiz):
        caminho = os.path.abspath(caminho)
        if not caminho.startswith(os.path.abspath(raiz)):
            return self._erro("caminho fora da pasta permitida", 403)
        if not os.path.isfile(caminho):
            return self._erro("arquivo não encontrado: " + os.path.basename(caminho), 404)
        tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
        if caminho.endswith(".dxf"):
            tipo = "application/dxf"
        # sempre revalidar: depois de uma atualização do programa a janela do aplicativo
        # não pode continuar com o JavaScript antigo em cache; a etiqueta (data e
        # tamanho) devolve 304 quando nada mudou, então revalidar custa quase nada
        st = os.stat(caminho)
        etag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        dados = open(caminho, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        if tipo == "application/dxf":
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(caminho)}"')
        self.end_headers()
        self.wfile.write(dados)

    # -- rotas --
    def do_GET(self):
        rota = unquote(urlparse(self.path).path)
        try:
            if rota == "/":
                return self._arquivo(os.path.join(WEB, "inicio.html"), WEB)
            if rota in ("/dimensionar", "/index.html"):
                return self._arquivo(os.path.join(WEB, "index.html"), WEB)
            if rota == "/ajuda":
                return self._arquivo(os.path.join(WEB, "ajuda.html"), WEB)
            if rota in ("/api/vivo", "/api/fechou"):
                _sinal_de_vida(self.path, rota == "/api/fechou")
                return self._json({"ok": True})
            if rota == "/api/versao":
                return self._json({"programa": versao.NOME, "versao": versao.VERSAO,
                                   "nucleo": versao.impressao_do_nucleo(),
                                   "dados": PROJETOS, "instalado": versao.CONGELADO,
                                   "janela": JANELA_PROPRIA, "maquina": MAQUINA, "usuario": USUARIO})
            if rota == "/api/atualizacao":
                return self._json(verificar_atualizacao())
            if rota == "/api/catalogo":
                return self._json(catalogo())
            if rota == "/api/catalogo/pecas":
                return self._json(catalogo_de_pecas(parse_qs(urlparse(self.path).query)))
            if rota == "/api/projetos":
                return self._json(_gerente().listar())
            if rota.startswith("/api/projetos/"):
                partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
                if len(partes) == 2 and partes[1] == "modelo":
                    return self._json(modelo_do_projeto(partes[0]))
                if len(partes) == 2 and partes[1] == "historico":
                    return self._json({"historico": _gerente().listar_historico(partes[0])})
                if len(partes) == 2 and partes[1] == "progresso":
                    return self._json(progresso_do_projeto(partes[0]))
                if len(partes) == 2 and partes[1] == "calculo":
                    return self._json(calculo_do_projeto(partes[0]))
                if len(partes) == 3 and partes[1] == "calculo" and partes[2] == "geometria":
                    return self._json(geometria_para_calculo(partes[0]))
                if len(partes) == 2 and partes[1] == "desenhos":
                    return self._json(_gerente().listar_desenhos(partes[0]))
                if len(partes) == 2 and partes[1] == "materiais":
                    q = parse_qs(urlparse(self.path).query)
                    return self._json(lista_de_materiais(partes[0], recalcular=q.get("recalcular", ["0"])[0] in ("1", "true")))
                if len(partes) == 3 and partes[1] == "desenhos":
                    return self._json({"desenho": _gerente().abrir_desenho(partes[0], partes[2])})
                return self._json(projeto_completo(partes[0]))
            if rota == "/api/modelo/catalogo":
                return self._json(catalogo_3d())
            if rota == "/api/modelo/lista":
                return self._json(listar_modelos())
            if rota.startswith("/api/modelo/abrir/"):
                return self._json(abrir_modelo(rota.split("/api/modelo/abrir/", 1)[1]))
            if rota in ("/cad", "/desenho"):
                return self._arquivo(os.path.join(WEB, "cad", "cad.html"), WEB)
            if rota in ("/materiais", "/lista-de-materiais"):
                return self._arquivo(os.path.join(WEB, "materiais.html"), WEB)
            if rota in ("/catalogo", "/pecas"):
                return self._arquivo(os.path.join(WEB, "catalogo.html"), WEB)
            if rota in ("/editor", "/editor3d", "/3d"):
                return self._arquivo(os.path.join(WEB, "editor3d", "editor.html"), WEB)
            if rota.startswith("/saida/"):
                rel = posixpath.normpath(rota[len("/saida/"):]).lstrip("/\\")
                return self._arquivo(os.path.join(PROJETOS, rel), PROJETOS)
            # estáticos da interface
            rel = posixpath.normpath(rota.lstrip("/")).lstrip("/\\")
            return self._arquivo(os.path.join(WEB, rel), WEB)
        except ErroDeDados as e:
            return self._erro(e, 400)
        except Exception as e:
            return self._erro(f"falha interna: {e}", 500, traceback.format_exc())

    def do_POST(self):
        rota = unquote(urlparse(self.path).path)
        try:
            if rota in ("/api/vivo", "/api/fechou"):
                _sinal_de_vida(self.path, rota == "/api/fechou")
                return self._json({"ok": True})
            corpo = self._corpo()
            if rota == "/api/dimensionar":
                return self._json(dimensionar(corpo))
            if rota == "/api/gerar":
                return self._json(gerar_saidas(corpo))
            if rota == "/api/pasta-de-dados":
                _abrir_no_explorador(PROJETOS)
                return self._json({"aberta": PROJETOS})
            if rota == "/api/atualizacao/instalar":
                return self._json(instalar_atualizacao(corpo if isinstance(corpo, dict) else None))
            if rota == "/api/projetos":
                return self._json(criar_projeto(corpo))
            if rota.startswith("/api/projetos/"):
                partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
                if len(partes) == 2 and partes[1] == "vista2d":
                    return self._json(gerar_vista_2d(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "detalhar":
                    return self._json(detalhar_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "calcular":
                    return self._json(calcular_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "materiais":
                    return self._json(lista_de_materiais(partes[0], recalcular=True, corpo=corpo))
                if len(partes) == 2 and partes[1] == "detalhar-posicao":
                    return self._json(detalhar_posicao_projeto(partes[0], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "aplicar-furos":
                    return self._json(aplicar_furos_do_desenho(partes[0], partes[2], corpo))
                if len(partes) == 3 and partes[1] == "materiais" and partes[2] == "pdf":
                    return self._json(pdf_da_lista_de_materiais(partes[0]))
                if len(partes) == 2 and partes[1] == "pranchas":
                    return self._json(montar_pranchas_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "importar-dxf":
                    return self._json(importar_dxf_no_desenho(partes[0], corpo))
                if len(partes) == 3 and partes[1] == "desenhos":
                    return self._json(_gerente().salvar_desenho(partes[0], partes[2],
                                                                corpo.get("desenho", corpo)))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "dxf":
                    return self._json(exportar_desenho_dxf(partes[0], partes[2], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "pdf":
                    return self._json(exportar_desenho_pdf(partes[0], partes[2], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "excluir":
                    return self._json(_gerente().excluir_desenho(partes[0], partes[2]))
                if len(partes) != 2:
                    raise ErroDeDados("rota de projeto inválida: " + rota)
                return self._json(acao_de_projeto(partes[0], partes[1], corpo))
            if rota == "/api/modelo/malha":
                return self._json(malhas_do_documento(corpo))
            if rota == "/api/modelo/ifc/exportar":
                return self._json(exportar_ifc(corpo))
            if rota == "/api/modelo/ifc/importar":
                return self._json(importar_ifc(corpo))
            if rota == "/api/modelo/ifc/inspecionar":
                return self._json(inspecionar_ifc(corpo))
            if rota == "/api/modelo/ifc/detalhar":
                return self._json(detalhar_ifc(corpo))
            if rota == "/api/modelo/do-galpao":
                return self._json(modelo_do_galpao(corpo))
            if rota == "/api/modelo/analise":
                return self._json(analise_do_galpao(corpo))
            if rota == "/api/modelo/salvar":
                return self._json(salvar_modelo(corpo))
            return self._erro("rota desconhecida: " + rota, 404)
        except ErroDeDados as e:
            return self._erro(e, 400)
        except ModuleNotFoundError as e:
            return self._erro(f"módulo ainda não disponível: {e.name}", 501)
        except Exception as e:
            return self._erro(f"falha no cálculo: {e}", 500, traceback.format_exc())


class Servidor(ThreadingHTTPServer):
    """Servidor HTTP que ignora conexões encerradas pelo navegador no meio da resposta."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        erro = sys.exc_info()[1]
        if isinstance(erro, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return                       # o navegador fechou a aba ou cancelou o pedido
        super().handle_error(request, client_address)


class ServidorIPv6(Servidor):
    address_family = socket.AF_INET6


def _servidores(porta: int):
    """Um servidor em 127.0.0.1 e, se a máquina tiver IPv6, outro em ::1.

    Os dois ficam só no loopback. Sem o segundo, cada acesso por "localhost" no Windows
    espera cerca de 2 s pela tentativa IPv6 antes de cair no IPv4.
    """
    principal = Servidor(("127.0.0.1", porta), Handler)
    extras = []
    try:
        extras.append(ServidorIPv6(("::1", porta), Handler))
    except OSError:
        pass                             # sem IPv6: o acesso por 127.0.0.1 continua valendo
    return principal, extras


PORTA_PADRAO = 8765

#: True quando o programa abriu a própria janela (modo aplicativo). A interface usa
#: isto para abrir o editor 3D em outra janela do mesmo tipo, e não numa aba.
JANELA_PROPRIA = False

#: Janelas do programa que deram sinal de vida: id da página -> instante do último sinal.
#: Ver web/vivo.js. Só é usado quando o programa abriu a própria janela.
JANELAS_VIVAS = {}
_TRAVA_JANELAS = threading.Lock()
#: Sem sinal por este tempo, a janela é dada como fechada. Maior que um minuto porque o
#: navegador freia o temporizador de página em segundo plano para uma vez por minuto.
SILENCIO_MAXIMO = float(os.environ.get("METALICA_SILENCIO") or 90.0)   # a variável é para teste


def _sinal_de_vida(rota_completa: str, fechou: bool):
    from urllib.parse import parse_qs
    q = parse_qs(urlparse(rota_completa).query)
    j = (q.get("j") or [""])[0][:64]
    p = (q.get("p") or [""])[0][:80]
    if p:
        # a página de um projeto mantém a marca de "aberto" (e a tira ao fechar)
        try:
            if fechou:
                _gerente().desmarcar_aberto(p, MAQUINA)
            else:
                _gerente().marcar_aberto(p, MAQUINA, USUARIO)
        except Exception:                                             # noqa: BLE001
            pass
    if not j:
        return
    with _TRAVA_JANELAS:
        if fechou:
            JANELAS_VIVAS.pop(j, None)
        else:
            JANELAS_VIVAS[j] = time.time()


def _janelas_abertas() -> int:
    agora = time.time()
    with _TRAVA_JANELAS:
        for j in [k for k, quando in JANELAS_VIVAS.items() if agora - quando > SILENCIO_MAXIMO]:
            del JANELAS_VIVAS[j]
        return len(JANELAS_VIVAS)


def _ja_esta_rodando(porta: int) -> bool:
    """Há outro Metálica respondendo nessa porta? (segundo clique no atalho)"""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/versao", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("programa") == versao.NOME
    except Exception:
        return False


def _porta_livre(preferida: int) -> int:
    """A porta preferida, se estiver livre; senão uma que o sistema escolher.

    Na máquina do usuário a 8765 pode estar ocupada por outro programa, e o Metálica
    não pode deixar de abrir por isso."""
    for candidata in (preferida, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", candidata))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return preferida


def _abrir_janela(url: str):
    """Janela própria do programa: o Edge (ou Chrome) em modo aplicativo, sem abas nem
    barra de endereço, com perfil separado do navegador do usuário.

    Devolve o processo, para o programa encerrar quando a janela fechar, ou None se não
    houver navegador compatível — aí a interface abre no navegador padrão."""
    import subprocess
    try:
        from saida.printpdf import navegador
        exe = navegador()
    except Exception:
        return None
    # o perfil do navegador fica fora da pasta de dados: Documentos costuma estar no
    # OneDrive, que passaria a sincronizar centenas de arquivos temporários do Chrome
    local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    perfil = os.path.join(local, "Metalica", "janela")
    os.makedirs(perfil, exist_ok=True)
    try:
        return subprocess.Popen(
            [exe, f"--app={url}", f"--user-data-dir={perfil}", "--no-first-run",
             "--no-default-browser-check", "--window-size=1500,950",
             "--disable-features=Translate", "--disk-cache-size=104857600",   # cache do perfil limitado a 100 MB
             # O modelo 3D é desenhado pela placa de vídeo. Em placa antiga ou com driver
             # na lista de bloqueio do navegador, ele cai para o desenho por software e a
             # navegação fica lenta mesmo num modelo modesto — estas opções mantêm a
             # aceleração ligada. Ver → Diagnóstico de desempenho mostra o que está em uso.
             "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
             "--enable-zero-copy"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def _registro_em_arquivo():
    """Sem console (programa instalado), print e erros vão para um arquivo de registro:
    `sys.stdout` é None e qualquer escrita nele derrubaria o servidor."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        arq = open(os.path.join(PROJETOS, "metalica.log"), "a", encoding="utf-8", buffering=1)
    except OSError:
        arq = open(os.devnull, "w")
    sys.stdout = sys.stdout or arq
    sys.stderr = sys.stderr or arq


def main():
    global JANELA_PROPRIA
    os.makedirs(PROJETOS, exist_ok=True)
    _registro_em_arquivo()
    com_janela = "--janela" in sys.argv or (versao.CONGELADO and "--sem-navegador" not in sys.argv)
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    else:
        if com_janela and _ja_esta_rodando(PORTA_PADRAO):
            # segundo clique no atalho: mostra o que já está aberto, não sobe outro
            janela = _abrir_janela(f"http://localhost:{PORTA_PADRAO}/")
            if janela is None:
                webbrowser.open(f"http://localhost:{PORTA_PADRAO}/")
            return
        porta = _porta_livre(PORTA_PADRAO)
    servidor, extras = _servidores(porta)
    for s in extras:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    url = _url_para_reabrir(f"http://localhost:{porta}/")     # volta ao desenho de antes da atualização
    try:
        limpar_instaladores_antigos()                           # o que as atualizações anteriores deixaram
    except Exception:                                           # noqa: BLE001
        pass
    # flush: com a saída redirecionada para arquivo o Python retém o texto, e quem lê o
    # registro para descobrir a porta ficaria sem resposta
    print(f"{versao.identificacao()} — dimensionamento de estruturas metálicas", flush=True)
    print(f"  interface: {url}", flush=True)
    print(f"  projetos:  {PROJETOS}", flush=True)

    def encerrar():
        for s in [servidor, *extras]:
            threading.Thread(target=s.shutdown, daemon=True).start()

    JANELA_PROPRIA = com_janela
    if com_janela:
        def vigiar():
            time.sleep(0.6)                     # o servidor já está ouvindo
            if _abrir_janela(url) is None:
                webbrowser.open(url)            # sem Edge nem Chrome: navegador padrão
            # Encerra quando nenhuma janela dá sinal de vida (web/vivo.js). O processo do
            # navegador não serve de referência: havendo outro Chrome com o mesmo perfil,
            # o que lançamos entrega a janela a ele e sai na hora, com a janela aberta.
            inicio, vazio_desde, ja_abriu = time.time(), None, False
            while True:
                time.sleep(1.0)
                abertas = _janelas_abertas()
                if abertas:
                    ja_abriu, vazio_desde = True, None
                    continue
                # nunca abriu: dá dois minutos (máquina lenta, antivírus); depois de aberta,
                # seis segundos sem ninguém cobrem a troca de uma página para outra
                limite = 6.0 if ja_abriu else 120.0
                vazio_desde = vazio_desde or (time.time() if ja_abriu else inicio)
                if time.time() - vazio_desde >= limite:
                    print("nenhuma janela aberta: encerrando.", flush=True)
                    encerrar()
                    return
        threading.Thread(target=vigiar, daemon=True).start()
    elif "--sem-navegador" not in sys.argv:
        print("  Ctrl+C para encerrar.")
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
        encerrar()


if __name__ == "__main__":
    main()
