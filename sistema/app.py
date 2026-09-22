# -*- coding: utf-8 -*-
"""Servidor web local do sistema de dimensionamento de galpões.

Roda sem framework: apenas a biblioteca padrão. Sobe em http://localhost:8765 e serve
a interface de `web/` mais uma API JSON.

    python app.py              sobe o servidor e abre o navegador
    python app.py --porta 9000 outra porta
    python app.py --sem-navegador

Rotas da API:
    GET  /api/catalogo              perfis, aços, parafusos, eletrodos, cidades
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
    GET  /api/projetos/<slug>/desenhos[/<nome>]      desenhos 2D do CAD
    POST /api/projetos/<slug>/desenhos/<nome>[/dxf|/excluir]
    GET  /saida/<projeto>/<arquivo> baixa um arquivo gerado
"""
import json
import mimetypes
import os
import posixpath
import socket
import re
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

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
        return g.salvar_modelo(s, corpo.get("documento", corpo))
    if acao == "importar-ifc":
        return importar_ifc_no_projeto(s, corpo)
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
    with open(destino, "wb") as f:
        f.write(base64.b64decode(dados))
    doc = imp.importar(destino)
    g.salvar_modelo(s, doc.dict())
    g.tocar(s, tipo="ifc", origem_ifc=nome)
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


def modelo_do_projeto(s: str) -> dict:
    doc = _gerente().abrir_modelo(s)
    return {"documento": doc, "existe": doc is not None}



# ----------------------------------------------------------- modelo 3D e IFC

MODELOS = os.path.join(PROJETOS, "modelos")


def _documento_de(corpo: dict):
    from nucleo3d.modelo import Documento
    d = corpo.get("documento", corpo)
    if not isinstance(d, dict):
        raise ErroDeDados("documento 3D ausente ou inválido.")
    return Documento.de_dict(d)


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
        dados = open(caminho, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
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
            if rota in ("/api/vivo", "/api/fechou"):
                _sinal_de_vida(self.path, rota == "/api/fechou")
                return self._json({"ok": True})
            if rota == "/api/versao":
                return self._json({"programa": versao.NOME, "versao": versao.VERSAO,
                                   "nucleo": versao.impressao_do_nucleo(),
                                   "dados": PROJETOS, "instalado": versao.CONGELADO,
                                   "janela": JANELA_PROPRIA})
            if rota == "/api/catalogo":
                return self._json(catalogo())
            if rota == "/api/projetos":
                return self._json(_gerente().listar())
            if rota.startswith("/api/projetos/"):
                partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
                if len(partes) == 2 and partes[1] == "modelo":
                    return self._json(modelo_do_projeto(partes[0]))
                if len(partes) == 2 and partes[1] == "desenhos":
                    return self._json(_gerente().listar_desenhos(partes[0]))
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
            if rota == "/api/projetos":
                return self._json(criar_projeto(corpo))
            if rota.startswith("/api/projetos/"):
                partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
                if len(partes) == 2 and partes[1] == "vista2d":
                    return self._json(gerar_vista_2d(partes[0], corpo))
                if len(partes) == 3 and partes[1] == "desenhos":
                    return self._json(_gerente().salvar_desenho(partes[0], partes[2],
                                                                corpo.get("desenho", corpo)))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "dxf":
                    return self._json(exportar_desenho_dxf(partes[0], partes[2], corpo))
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
    j = (parse_qs(urlparse(rota_completa).query).get("j") or [""])[0][:64]
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
             "--disable-features=Translate"],
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
    url = f"http://localhost:{porta}/"
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
