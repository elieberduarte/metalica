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
    POST /api/projetos/<slug>/atualizar-pecas {marcas}   furos das barras e células dessas peças, sem refazer tudo
    GET  /api/fabrica                     regras da fábrica (bobinas, dobradeira) e os perfis da fábrica em uso
    POST /api/fabrica/{regras|validar|perfis|perfis/remover}
    POST /api/projetos/<slug>/calcular {parametros, trocas, comparar}  cálculo estrutural do modelo importado
    POST /api/projetos/<slug>/dimensionar {parametros, aplicar}  o perfil mais leve que passa em cada posição
    GET  /api/projetos/<slug>/calculo[/geometria]        último cálculo gravado / dados para o diálogo
    GET  /api/projetos/<slug>/calculo/alternativas?marca=  perfis que podem substituir a peça, verificados
    POST /api/projetos/<slug>/desenhos/<nome>/aplicar-furos   furos do detalhe → chapas do modelo
    POST /api/projetos/<slug>/desenhos/<nome>/aplicar-pecas {desenho}  barras movidas/esticadas/copiadas/apagadas nas elevações → modelo 3D
    POST /api/projetos/<slug>/desenhos/<nome>/gerar-3d       desenho 2D → modelo 3D (peças do catálogo)
    GET  /api/projetos/<slug>/materiais[?recalcular=1]  lista de materiais (romaneio, perfis, chapas, conjuntos)
    POST /api/projetos/<slug>/materiais[/pdf]           recalcula do modelo (barra, regra_tercas) / imprime o PDF
    GET  /api/projetos/<slug>/resumos                    dados dos resumos (revisão, telha, eixos…) e sugestões
    POST /api/projetos/<slug>/resumos {dados}            grava os dados e gera o resumo da obra e o de materiais (HTML + PDF)
    POST /api/projetos/<slug>/pranchas  pranchas (folhas com carimbo) a partir dos desenhos 2D
    POST /api/projetos/<slug>/importar-dxf  DXF em texto → entidades do CAD
    POST /api/projetos/<slug>/importar-pdf  PDF vetorial (base64) → entidades do CAD, em mm de papel
    POST /api/projetos/<slug>/desenhos/<nome>/reconhecer  perfis escritos do projeto recebido → peças
    POST /api/projetos/<slug>/projeto-2d    DXF/PDF de projeto → desenho, peças, modelo 3D e IFC de uma vez
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
import shutil
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
    # nomes do catálogo completo (laminados e formados a frio) por família, para as
    # listas de "perfil por elemento" do formulário
    try:
        from nucleo import catalogo as _cat
        dados["pecas"] = {fam: [it.nome for it in _cat.itens(fam)] for fam in ("I", "U", "Ue", "L", "tubo")}
    except Exception as e:
        dados["pecas"] = {"erro": str(e)}
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
        "sistema": ("Sistema estrutural", ["tipo_portico", "base_rotulada",
                                           "formato_tesoura", "diagonais_tesoura",
                                           "ligacao_tesoura", "altura_tesoura",
                                           "paineis_tesoura", "com_misula",
                                           "comprimento_misula", "altura_misula"]),
        "materiais": ("Materiais", ["aco_perfis", "aco_tercas", "aco_chapas", "parafuso",
                                    "eletrodo", "fck_MPa"]),
        "perfis": ("Perfis por elemento", ["perfil_terca", "perfil_longarina", "perfil_viga",
                                           "perfil_pilar", "perfil_banzo_superior",
                                           "perfil_banzo_inferior", "perfil_diagonal",
                                           "perfil_montante", "banzos_duplos",
                                           "diagonais_duplas"]),
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
    "formato_tesoura": "Formato da tesoura", "diagonais_tesoura": "Diagonais da tesoura",
    "ligacao_tesoura": "Ligação da tesoura no pilar",
    "altura_tesoura": "Altura da tesoura no apoio (m) — 0 = automática, vão/25",
    "paineis_tesoura": "Painéis por água (0 = pelo passo das terças)",
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
    "perfil_terca": "Terça", "perfil_longarina": "Longarina de fechamento",
    "perfil_viga": "Viga do pórtico (alma cheia)", "perfil_pilar": "Pilar",
    "perfil_banzo_superior": "Banzo superior (tesoura)", "perfil_banzo_inferior": "Banzo inferior (tesoura)",
    "perfil_diagonal": "Diagonais (tesoura)", "perfil_montante": "Montantes (tesoura)",
    "banzos_duplos": "Banzos com perfil duplo (2 peças costas com costas)",
    "diagonais_duplas": "Diagonais e montantes com perfil duplo",
}


def _rotulo(campo: str) -> str:
    return ROTULOS.get(campo, campo.replace("_", " ").capitalize())


def geometria_da_tesoura(entrada: dict) -> dict:
    """Malha da tesoura para a pré-visualização do formulário, em metros.

    Sai do mesmo gerador do cálculo (`nucleo/tesouras.geometria`), e não de uma cópia
    das regras no JavaScript: assim o desenho da tela nunca mostra uma tesoura
    diferente da que vai ser dimensionada.
    """
    from nucleo import tesouras
    d = _dados_de(entrada or {}, validar=False)
    if not d.eh_trelicado:
        return {"trelicado": False}
    try:
        t = tesouras.geometria(
            vao=d.vao * 100, inclinacao=d.inclinacao / 100.0, formato=d.formato_tesoura,
            diagonais=d.diagonais_tesoura, altura_apoio=d.altura_tesoura * 100,
            paineis=d.paineis_tesoura, espacamento_tercas=d.espacamento_tercas * 100)
    except Exception as e:
        return {"trelicado": True, "erro": str(e)}
    pular = {"mont_esq", "mont_dir"} if d.ligacao_tesoura == "rígida" else set()
    return {
        "trelicado": True,
        "ligacao": d.ligacao_tesoura,
        "altura_apoio_m": round(t.altura_apoio / 100.0, 3),
        "nos": {n.nome: [round(n.x / 100.0, 4), round(n.y / 100.0, 4)] for n in t.nos},
        "barras": [{"i": b.i, "j": b.j, "papel": b.papel} for b in t.barras
                   if b.rotulo not in pular],
        "resumo": t.resumo(),
    }


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


def _dados_de(entrada: dict, validar: bool = True) -> DadosGalpao:
    """Converte o corpo da requisição em `DadosGalpao`.

    `validar=False` serve à pré-visualização do formulário, que desenha enquanto o
    projetista ainda está escolhendo e não pode recusar um estado intermediário.
    """
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
    return d.validar() if validar else d


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
        _regravar_modelo(s, doc)
        g.tocar(s, tipo="ifc", origem_ifc=nome)
    finally:
        _fim_progresso(s)
    return {"projeto": s, "estatisticas": doc.estatisticas(),
            "relatorio": doc.metadados.get("importacao", {})}


# ---- desenhos 2D (CAD): ver nucleo2d/

def _mtime_do_modelo(s: str):
    caminho = _gerente().caminho_modelo(s)
    try:
        return os.stat(caminho).st_mtime_ns
    except OSError:
        return None


def _documento3d_do_projeto(s: str):
    from nucleo3d.modelo import Documento
    lido = _mtime_do_modelo(s)
    d = _gerente().abrir_modelo(s)
    if d is None:
        raise ErroDeDados("o projeto ainda não tem modelo 3D: importe o IFC ou gere o galpão.")
    doc = Documento.de_dict(d)
    doc._mtime_lido = lido               # para a regravação conferir que ninguém gravou no meio
    return doc


class ModeloMudouNoMeio(ErroDeDados):
    pass


def _regravar_modelo(s: str, doc, marco: bool = True) -> dict:
    """Grava o modelo que uma operação leu, mudou e devolve (detalhar, aplicar furos,
    dimensionar…). Se o editor 3D gravou o modelo enquanto a operação rodava, não grava
    por cima: aquela edição se perderia calada."""
    lido = getattr(doc, "_mtime_lido", None)
    if lido is not None:
        agora = _mtime_do_modelo(s)
        if agora is not None and agora != lido:
            raise ModeloMudouNoMeio(
                "o modelo 3D foi gravado por outra tela enquanto esta operação rodava; para não desfazer aquela "
                "edição, esta operação não regravou o modelo. Rode de novo.")
    r = _gerente().salvar_modelo(s, doc.dict(), marco=marco)
    doc._mtime_lido = _mtime_do_modelo(s)
    return r


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


def gerar_3d_do_desenho(s: str, nome: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/desenhos/<nome>/gerar-3d: o desenho 2D vira modelo 3D.

    corpo: {conferir: bool, plano, origem: [x,y,z], repeticoes, espacamento, conjunto,
            aco, modo: "acrescentar"|"substituir"}

    Cada linha marcada com uma peça do catálogo vira uma `Barra` com perfil, aço, papel e
    as marcas de posição e conjunto — o mesmo que um IFC de fábrica traz. Com
    `conferir`, só devolve o que o desenho tem, sem gerar nada."""
    from nucleo2d.desenho import Desenho
    from nucleo3d import de_desenho
    from nucleo3d.modelo import Documento
    g = _gerente()
    bruto = g.abrir_desenho(s, nome)
    if not bruto:
        raise ErroDeDados("desenho não encontrado: %s" % nome)
    desenho = Desenho.de_dict(bruto)
    if corpo.get("conferir"):
        info = de_desenho.conferir_desenho(desenho)
        info["desenho"] = desenho.nome
        info["planos"] = [{"chave": k, "nome": v["nome"]} for k, v in de_desenho.PLANOS.items()]
        info["papeis"] = de_desenho.PAPEIS
        return info
    modo = str(corpo.get("modo") or "acrescentar")
    base = None
    if modo == "acrescentar":
        atual = g.abrir_modelo(s)
        base = Documento.de_dict(atual) if atual else None
    if corpo.get("montagens"):
        # projeto recebido (DXF/PDF reconhecido): cada vista no seu lugar
        from nucleo3d import de_vistas
        doc = de_vistas.modelo_das_vistas(desenho, corpo["montagens"], aco_padrao=str(corpo.get("aco") or "ASTM A572 Gr.50"),
                                          nome=str(corpo.get("nome") or "") or desenho.nome, doc=base,
                                          perfis=corpo.get("perfis") if isinstance(corpo.get("perfis"), dict) else None)
        _regravar_modelo(s, doc)
        g.tocar(s)
        r = {"modelo": {"entidades": len(doc.entidades), "barras": len(doc.barras)},
             "gerado": {k: v for k, v in doc.metadados.get("de_desenho", {}).items() if k != "montagens"},
             "modo": modo, "estatisticas": doc.estatisticas()}
        if corpo.get("ifc"):
            r["ifc"] = _exportar_ifc_do_projeto(s, doc, str(corpo.get("nome") or "") or desenho.nome)
        return r
    doc = de_desenho.modelo_do_desenho(
        desenho, plano=str(corpo.get("plano") or "frente"),
        origem=[float(x) for x in (corpo.get("origem") or [0, 0, 0])],
        repeticoes=int(corpo.get("repeticoes") or 1),
        espacamento=float(corpo.get("espacamento") or 5000.0),
        conjunto=str(corpo.get("conjunto") or "M"),
        aco_padrao=str(corpo.get("aco") or "ASTM A572 Gr.50"),
        nome=str(corpo.get("nome") or "") or None, doc=base)
    _regravar_modelo(s, doc)      # o modelo anterior vai para o histórico
    g.tocar(s)
    info = doc.metadados.get("de_desenho", {})
    return {"modelo": {"entidades": len(doc.entidades), "barras": len(doc.barras)},
            "gerado": info, "modo": modo,
            "estatisticas": doc.estatisticas()}


def detalhar_projeto(s: str, corpo: dict) -> dict:
    """Detalhamento de peças e conjuntos do modelo do projeto: um desenho 2D por família
    (tesouras, conjuntos, terças, contraventamentos, agulhamentos, extras), mais telhas,
    chaparias, localização e completo, gravados em desenhos-2d/, com o romaneio (CSV) e o
    relatório em detalhamento/.

    corpo: {grupos: [...], regra_tercas: bool, rotular: bool, substituir: bool}"""
    from nucleo2d.detalhar import detalhar, GRUPOS, _categoria  # noqa: F401
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
    _alinhar_furos_das_barras(s, doc)
    grupos = corpo.get("grupos") or list(GRUPOS.keys())
    r = detalhar(doc, grupos=grupos, regra_tercas=corpo.get("regra_tercas", True) is not False,
                 rotular=bool(corpo.get("rotular", False)),
                 converter=corpo.get("converter", True) is not False, ajustes=_ajustes_furos(s),
                 nomes=_nomes_producao(s), eixos=g.ler(s).get("eixos"),
                 avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
    _gravar_nomes_producao(s, r.get("nomes") or {})
    nomeadas = _nomes_no_modelo(doc, r.get("nomes") or {})
    # a furação padrão de fábrica (regra das terças) também nas chapas do 3D, e as terças
    # parafusadas nelas acompanham
    from nucleo2d.detalhar import padronizar_furos_das_chapas, alinhar_furos_das_barras_as_chapas
    padr = padronizar_furos_das_chapas(doc, r.get("objetos_posicoes") or [])
    if padr["chapas"]:
        alinhar_furos_das_barras_as_chapas(doc)
        r.setdefault("avisos", []).append("furação padrão de fábrica aplicada no 3D a %d chapa(s): %s"
                                          % (padr["chapas"], ", ".join(padr["posicoes"][:12])))
    if r.get("convertidas") or nomeadas or padr["chapas"]:
        _progresso(s, "gravando o modelo…")
        try:
            _regravar_modelo(s, doc)            # chapas planas viraram paramétricas / nomes nas peças
        except ModeloMudouNoMeio:
            # o detalhamento em si vale (sai dos desenhos); só os nomes e as chapas
            # paramétricas não foram para o modelo, que o editor gravou no meio
            r.setdefault("avisos", []).append(
                "o modelo 3D foi gravado pelo editor durante o detalhamento: os nomes de produção e as chapas "
                "paramétricas não foram gravados nele (detalhe de novo para levá-los)")
    _progresso(s, "gravando os desenhos…")
    substituir = corpo.get("substituir", True) is not False
    if substituir:
        # os desenhos por classe de antes da 0.7.22 (chapas, barras e terças, tirantes) não
        # são mais gerados: saem, para não ficarem ao lado dos novos com conteúdo velho
        from nucleo2d.detalhar import TITULOS_ANTIGOS
        for nome in TITULOS_ANTIGOS:
            if os.path.exists(g._caminho_desenho(s, nome)):
                g.excluir_desenho(s, nome)
    desenhos = []
    for chave, desenho in r["desenhos"].items():
        nome = desenho.nome
        if substituir and os.path.exists(g._caminho_desenho(s, nome)):
            g.excluir_desenho(s, nome)
        desenho.metadados["gerado_por"] = "detalhamento"
        desenho.metadados["versao"] = versao.VERSAO
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
    lista["pre_moldados"] = r.get("fora_do_aco") or []
    lista["estrutura_a_conferir"] = r.get("estrutura_a_conferir") or []
    arquivos = lista_producao.gravar(pasta, lista, r["objetos_posicoes"], r["acessorios"])
    relatorio = {k: v for k, v in r.items() if k not in ("desenhos", "objetos_posicoes", "objetos_pecas", "camadas")}
    relatorio["desenhos"] = desenhos
    _gravar_ajuste(os.path.join(pasta, "relatorio.json"), relatorio)
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


def _nomes_para_calculo(s: str, doc) -> dict:
    """Os nomes do detalhamento; sem eles, num modelo desenhado (2D → 3D), a
    classificação que o papel das barras já dá (o conjunto com banzo é tesoura)."""
    from nucleo3d import calculo_ifc
    return _nomes_producao(s) or calculo_ifc.nomes_das_barras(doc)


def geometria_para_calculo(s: str) -> dict:
    """GET /api/projetos/<s>/calculo/geometria: o que o diálogo precisa saber do modelo
    antes de calcular (tesouras, vão, cota do apoio, peso da telha)."""
    from nucleo3d import calculo_ifc
    doc = _documento3d_do_projeto(s)
    nomes = _nomes_para_calculo(s, doc)
    g = calculo_ifc.geometria_do_modelo(doc, nomes) if nomes else {"tesouras": 0, "avisos": []}
    g["detalhado"] = bool(nomes)
    g["padrao"] = {k: v for k, v in calculo_ifc.PARAMETROS_PADRAO.items() if k != "trocas"}
    anterior = calculo_do_projeto(s)
    g["parametros"] = anterior.get("parametros") or {}
    return g


def alternativas_de_perfil(s: str, marca: str, limite: int = 10, todas: bool = False) -> dict:
    """GET /api/projetos/<s>/calculo/alternativas?marca=P42: perfis do catálogo que podem
    entrar no lugar do desta posição, verificados com os esforços do cálculo gravado."""
    from nucleo3d import calculo_ifc
    if not marca:
        raise ErroDeDados("informe a posição (marca) da peça")
    guardado = calculo_do_projeto(s).get("calculo")
    if not guardado:
        raise ErroDeDados("este projeto ainda não tem cálculo: use Calcular estrutura")
    return calculo_ifc.alternativas(guardado, marca, limite=limite, todas=todas)


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
        nomes = _nomes_para_calculo(s, doc)
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


def dimensionar_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/dimensionar {parametros, aplicar}: escolhe, em cada posição
    verificada, o perfil mais leve do catálogo que passa (repetindo o cálculo até a escolha
    se repetir) e, com `aplicar`, põe esses perfis nas barras do modelo — o anterior vai
    para o histórico — e grava o cálculo do modelo novo em calculo.json."""
    from nucleo3d import calculo_ifc
    from projetos import _gravar_json
    try:
        _progresso(s, "abrindo o modelo…")
        doc = _documento3d_do_projeto(s)
        nomes = _nomes_para_calculo(s, doc)
        if not nomes:
            raise ErroDeDados("gere o detalhamento primeiro (Desenho 2D → Detalhar peças e conjuntos): "
                              "é ele que classifica tesouras, terças e contraventamentos.")
        anterior = calculo_do_projeto(s)
        par = dict(anterior.get("parametros") or {})
        par.update({k: v for k, v in (corpo.get("parametros") or {}).items()})
        par["trocas"] = {}
        d = calculo_ifc.dimensionar(doc, nomes, par, avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
        saida = {k: v for k, v in d.items() if k != "calculo"}
        r = d["calculo"]
        if corpo.get("aplicar", True) and d["trocas"]:
            _progresso(s, "trocando os perfis no modelo…")
            ap = calculo_ifc.aplicar_perfis(doc, d["trocas"])
            g = _gerente()
            _regravar_modelo(s, doc)        # o modelo anterior vai para o histórico
            saida["aplicado"] = ap
            _progresso(s, "calculando o modelo com os perfis novos…")
            r = calculo_ifc.calcular(doc, nomes, dict(par, trocas=ap["so_calculo"]))
            par["trocas"] = dict(ap["so_calculo"])
        elif d["trocas"]:
            par["trocas"] = dict(d["trocas"])
        r["parametros"] = par
        _gravar_json(_caminho_calculo(s), {"parametros": par, "resultado": r,
                                          "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
        _gerente().tocar(s)
        saida["calculo"] = r
        saida["reprovadas"] = list((r.get("resumo") or {}).get("reprovadas") or [])
        saida["peso_depois_kg"] = (r.get("resumo") or {}).get("peso_verificado_kg")
        return saida
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


def _alinhar_furos_das_barras(s: str, doc) -> dict:
    """Furos das terças no lugar (e no formato) dos furos das chapas de suporte
    parafusadas nelas — nucleo2d.detalhar.alinhar_furos_das_barras_as_chapas. Grava o
    modelo quando algo mudou."""
    from nucleo2d import detalhar as det
    _progresso(s, "conferindo os furos das terças com os das chapas de suporte…")
    r = det.alinhar_furos_das_barras_as_chapas(doc)
    # e o furo que ficou longe (chapa esticada, parafusos levados à mão) vai até o parafuso
    rp = det.alinhar_furos_das_barras_aos_parafusos(doc)
    if rp["barras"]:
        r = dict(r, barras=r["barras"] + rp["barras"], furos=r["furos"] + rp["furos"],
                 posicoes=sorted(set(r["posicoes"]) | set(rp["posicoes"])))
    # e os furos das terças em que não passa nada saem (a produção furaria à toa)
    _progresso(s, "retirando das terças os furos sem parafuso nem barra…")
    r2 = det.retirar_furos_sem_uso(doc)
    # e os que ficam, oblongos como a regra manda (a chapa parafusada neles também)
    r3 = det.oblongar_furos_das_tercas(doc)
    if r.get("barras") or r2.get("furos") or r2.get("limpas") or r3.get("furos") or r3.get("chapas"):
        _regravar_modelo(s, doc)
        print("[detalhamento] %s: %d furo(s) de %d barra(s) alinhados às chapas (%d oblongos); %d furo(s) sem uso retirados de %d terça(s)"
              % (s, r["furos"], r["barras"], r["oblongos"], r2["furos"], r2["barras"]))
    r["retirados"] = r2
    r["oblongados"] = r3
    return r


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
        _regravar_modelo(s, doc)
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
        _regravar_modelo(s, doc)
    desenho, pos = det.detalhar_posicao(doc, marca, ajustes=_ajustes_furos(s), nomes=_nomes_producao(s))
    nome = desenho.nome
    if corpo.get("substituir", True) is not False and os.path.exists(g._caminho_desenho(s, nome)):
        g.excluir_desenho(s, nome)
    desenho.metadados["gerado_por"] = "detalhamento"
    desenho.metadados["versao"] = versao.VERSAO
    salvo = g.salvar_desenho(s, nome, desenho.dict())
    return {"nome": salvo["nome"], "titulo": nome, "marca": marca, "classe": pos.classe,
            "convertidas": convertidas, "reorientadas": reorientadas.get("chapas", 0),
            "editavel": desenho.metadados["detalhe_posicao"]["editavel"],
            "furos": len(desenho.metadados["detalhe_posicao"]["furos"]), "quantidade": pos.quantidade}


def _rota_fabrica(rota: str, corpo: dict) -> dict:
    """POST /api/fabrica/{regras | validar | perfis | perfis/remover}: as regras da fábrica
    (bobinas e limites da dobradeira), a validação de um perfil dobrado e a lista dos
    perfis da fábrica em uso (ver fabrica.py)."""
    import fabrica
    try:
        if rota == "/api/fabrica/regras":
            return {"regras": fabrica.gravar_regras(PROJETOS, corpo.get("regras") or corpo)}
        if rota == "/api/fabrica/validar":
            v = fabrica.validar(str(corpo.get("perfil") or ""), PROJETOS)
            v.pop("geometria", None)
            return v
        if rota == "/api/fabrica/perfis":
            return {"registro": fabrica.registrar(PROJETOS, str(corpo.get("perfil") or ""),
                                                  projeto=str(corpo.get("projeto") or ""), usuario=USUARIO, maquina=MAQUINA)}
        if rota == "/api/fabrica/perfis/remover":
            return {"removido": fabrica.remover(PROJETOS, str(corpo.get("perfil") or ""))}
    except ValueError as e:
        raise ErroDeDados(str(e))
    raise ErroDeDados("rota desconhecida: %s" % rota)


def atualizar_pecas_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/atualizar-pecas {marcas: [...]}: atualiza só essas peças, sem
    refazer o detalhamento inteiro. Os furos das barras vão para os das chapas e para os
    parafusos (a ligação mexida à mão no 3D) e o modelo é gravado; depois, em cada desenho
    de detalhamento gravado, a célula de cada posição pedida é redesenhada no mesmo lugar
    (o canto de baixo à esquerda fica onde estava), e o "Detalhe – <peça>", se existir, é
    refeito. A elevação dos conjuntos (tesouras) não muda aqui: para ela, gerar de novo."""
    from collections import Counter
    from nucleo2d import detalhar as det
    from nucleo2d.desenho import Desenho, transladar
    marcas = [str(m).strip() for m in (corpo.get("marcas") or []) if str(m).strip()]
    if not marcas:
        raise ErroDeDados("selecione a peça (ou as peças) no 3D.")
    g = _gerente()
    doc = _documento3d_do_projeto(s)
    _progresso(s, "furos das barras nas chapas e nos parafusos…")
    try:
        r1 = det.alinhar_furos_das_barras_as_chapas(doc)
        r2 = det.alinhar_furos_das_barras_aos_parafusos(doc)
        if r1["barras"] or r2["barras"]:
            _regravar_modelo(s, doc)
        _progresso(s, "levantando as peças…")
        lev = det.levantar(doc, ajustes=_ajustes_furos(s), nomes=_nomes_producao(s))
        pedidas = []
        for p in lev["posicoes"]:
            ms = det.marcas_de(p)
            if any(m in ms or m == p.marca or m == p.nome for m in marcas):
                pedidas.append(p)
        if not pedidas:
            raise ErroDeDados("as peças pedidas (%s) não foram achadas no levantamento." % ", ".join(marcas[:8]))
        atualizados = []
        for info in g.listar_desenhos(s, contar=False):
            nome = info["nome"]
            try:
                d = Desenho.de_dict(g.abrir_desenho(s, nome))
            except Exception:                                  # noqa: BLE001
                continue
            if not d.metadados.get("detalhamento"):
                continue
            mudou = False
            for p in pedidas:
                velhas = [e for e in d.entidades.values()
                          if (e.atributos or {}).get("detalhe") == "posicao" and (e.atributos or {}).get("posicao") == p.marca]
                if not velhas:
                    continue
                _progresso(s, "redesenhando %s em %s…" % (p.nome or p.marca, d.nome))
                pts = [q for e in velhas for q in e.pontos()]
                x0, y0 = min(q[0] for q in pts), min(q[1] for q in pts)
                # a camada da peça é a que o desenho já usa para ela (banzo, diagonal…)
                cams = Counter(e.camada for e in velhas if e.camada not in ("COTA", "TEXTO", "FURO", "EIXO", "VISTA-FINA", "OCULTA"))
                if cams:
                    p.camada_2d = cams.most_common(1)[0][0]
                tmp = Desenho(nome="tmp", escala=d.escala)
                tmp.camadas = dict(d.camadas)
                editavel = p.marca in ((d.metadados.get("detalhamento") or {}).get("editaveis") or [])
                det.desenho_da_posicao(p, tmp, 0.0, 0.0, editavel=editavel)
                novas = list(tmp.entidades.values())
                pts_n = [q for e in novas for q in e.pontos()]
                if not pts_n:
                    continue
                nx0, ny0 = min(q[0] for q in pts_n), min(q[1] for q in pts_n)
                for e in velhas:
                    d.remover(e.id)
                for e in novas:
                    d.add(transladar(e, x0 - nx0, y0 - ny0))
                mudou = True
            if mudou:
                g.salvar_desenho(s, nome, d.dict())
                atualizados.append(d.nome)
        # o "Detalhe – <peça>" gravado, refeito do modelo
        detalhes = []
        for p in pedidas:
            titulo = "Detalhe – %s" % p.marca
            if any(i.get("titulo") == titulo or i["nome"] == _slug(titulo) for i in g.listar_desenhos(s, contar=False)):
                desenho, _ = det.detalhar_posicao(doc, det.marcas_de(p)[0], ajustes=_ajustes_furos(s), nomes=_nomes_producao(s))
                if os.path.exists(g._caminho_desenho(s, desenho.nome)):
                    g.excluir_desenho(s, desenho.nome)
                desenho.metadados["gerado_por"] = "detalhamento"
                desenho.metadados["versao"] = versao.VERSAO
                g.salvar_desenho(s, desenho.nome, desenho.dict())
                detalhes.append(desenho.nome)
        g.tocar(s)
        return {"pecas": [p.nome or p.marca for p in pedidas], "furos_barras": r1["furos"] + r2["furos"],
                "barras": sorted(set(r1["posicoes"]) | set(r2["posicoes"])),
                "desenhos": atualizados, "detalhes": detalhes}
    finally:
        _fim_progresso(s)


def aplicar_pecas_do_desenho(s: str, nome: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/desenhos/<nome>/aplicar-pecas {desenho}: as barras que o
    usuário moveu, espelhou, esticou, copiou ou apagou nas elevações dos conjuntos mudam
    igual no modelo 3D, em todas as instâncias de cada tipo de conjunto; o modelo anterior
    vai para o histórico. Depois, os desenhos de detalhamento são gerados de novo a partir
    do 3D corrigido (`regerar`, ligado por padrão) — o completo e os demais passam a ter a
    mesma correção — e este desenho fica como o usuário o deixou. Desenho de antes da
    0.8.17 (sem versão gravada) é recusado; de outra versão desde então, aplica com aviso."""
    from nucleo2d.desenho import Desenho
    from nucleo2d.detalhar import detalhar, GRUPOS, _categoria
    from nucleo2d.detalhe.aplicar_pecas import aplicar_desenho_ao_modelo
    from saida import lista_producao
    g = _gerente()
    try:
        _progresso(s, "lendo o desenho…")
        d = Desenho.de_dict(corpo["desenho"]) if isinstance(corpo.get("desenho"), dict) else Desenho.de_dict(g.abrir_desenho(s, nome))
        gerado_por = str(d.metadados.get("versao") or "")
        if not gerado_por:
            raise ErroDeDados("este desenho foi gerado antes da 0.8.17, sem a versão gravada: gere o detalhamento de "
                              "novo, faça a correção nele e aplique — senão as diferenças de geração iriam para o 3D "
                              "como se fossem edição sua.")
        doc = _documento3d_do_projeto(s)
        # o mesmo modelo detalhado agora, pelo mesmo código: só a edição feita à mão sobra
        _progresso(s, "detalhando de novo o modelo para comparar…")
        r0 = detalhar(doc, grupos=["tesouras", "conjuntos", "contraventamentos", "agulhamentos", "extras"],
                      nomes=_nomes_producao(s), converter=False, ajustes=_ajustes_furos(s),
                      avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
        _progresso(s, "comparando e aplicando no modelo…")
        r = aplicar_desenho_ao_modelo(doc, d, list(r0["desenhos"].values()), todas_instancias=corpo.get("todas", True) is not False)
        if gerado_por != versao.VERSAO:
            r.setdefault("avisos", []).append("desenho gerado pela versão %s (esta é a %s): se a geração mudou entre elas, "
                                              "a diferença foi para o 3D como se fosse edição — confira" % (gerado_por, versao.VERSAO))
        if r["celulas"]:
            _regravar_modelo(s, doc, marco=True)
            g.tocar(s)
            if corpo.get("regerar", True) is not False:
                # os outros desenhos (o completo, os conjuntos…) saem do 3D corrigido; o
                # desenho editado volta a ser gravado como o usuário o deixou
                _progresso(s, "gerando os desenhos de detalhamento de novo…")
                res = _detalhar_projeto(s, {"grupos": list(GRUPOS.keys())}, g, detalhar, GRUPOS, _categoria, lista_producao)
                g.salvar_desenho(s, nome, d.dict())
                r["regenerados"] = [x["nome"] for x in res.get("desenhos", [])]
                r["avisos"].extend(res.get("avisos") or [])
        return r
    finally:
        _fim_progresso(s)


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
        # e pela geometria: o furo da terça vai para o furo da chapa encostada nela (vale
        # também para furo oblongo, que o vínculo por passos não compara)
        r4 = det.alinhar_furos_das_barras_as_chapas(doc)
        if r4["barras"]:
            r3 = dict(r3, barras=r3["barras"] + r4["barras"], furos=r3.get("furos", 0) + r4["furos"],
                      posicoes=sorted(set(r3.get("posicoes", [])) | set(r4["posicoes"])))
        if r3["barras"]:
            barras3d.update(r3)
            _regravar_modelo(s, doc)
        return sorted(vinc)
    def aplicar_em_barra(marca_, furos_):
        # barra (terça, diagonal…): a furação nova fica como ajuste do projeto e os furos
        # da malha 3D são movidos, furo a furo; furo novo ou apagado só vale no desenho
        r_ = det.aplicar_furos_de_barra(doc, marca_, furos_, ajustes)
        _gravar_ajustes_furos(s, ajustes)
        if r_["barras3d"].get("barras"):
            _regravar_modelo(s, doc)
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
            _regravar_modelo(s, doc)
            vinculadas = vincular(marca, meta.get("furos") or [], furos)
        novo, pos = det.detalhar_posicao(doc, marca, ajustes=ajustes, nomes=_nomes_producao(s))
        if os.path.exists(g._caminho_desenho(s, novo.nome)):
            g.excluir_desenho(s, novo.nome)
        novo.metadados["gerado_por"] = "detalhamento"
        novo.metadados["versao"] = versao.VERSAO
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
        _regravar_modelo(s, doc)
        vinculadas = vincular(marca, originais, furos)
    det.regenerar_celula(d, doc, marca, ajustes=ajustes, nomes_producao=_nomes_producao(s))
    salvo = g.salvar_desenho(s, nome, d.dict())
    return dict(r, nome=salvo["nome"], marca=marca, vinculadas=vinculadas, barras3d=barras3d)


def _ler_ajuste(caminho: str, rotulo: str) -> dict:
    """Um arquivo de ajuste do projeto (nomes de produção, furação ajustada à mão).
    Ausente é vazio; existente e ilegível NÃO é vazio calado — antes a furação ajustada à
    mão e os nomes dados sumiam sem aviso. Tenta três vezes (OneDrive e antivírus seguram
    o arquivo por instantes); depois guarda uma cópia e para com a explicação."""
    if not os.path.exists(caminho):
        return {}
    erro = None
    for tentativa in range(3):
        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError) as e:
            erro = e
            time.sleep(0.3 * (tentativa + 1))
    copia = "%s.ilegivel-%s" % (caminho, time.strftime("%Y%m%d-%H%M%S"))
    try:
        shutil.copy2(caminho, copia)
    except OSError:
        copia = ""
    raise ErroDeDados("%s (%s) não pôde ser lido: %s. Nada foi feito, para não perder o que estava nele%s."
                      % (rotulo, caminho, erro, ("; há uma cópia em " + copia) if copia else ""))


def _gravar_ajuste(caminho: str, dados: dict):
    from projetos import _gravar_json
    _gravar_json(caminho, dados, indent=1)            # temporário + troca: nunca meio arquivo


def _nomes_producao(s: str) -> dict:
    """Nomes de produção já dados (detalhamento/nomes.json): {"posicoes": {marca: nome}, "conjuntos": {...}}."""
    return _ler_ajuste(os.path.join(_gerente()._existente(s), "detalhamento", "nomes.json"), "Os nomes de produção")


def _gravar_nomes_producao(s: str, nomes: dict):
    pasta = os.path.join(_gerente()._existente(s), "detalhamento")
    _gravar_ajuste(os.path.join(pasta, "nomes.json"),
                   {k: nomes.get(k) or {} for k in ("posicoes", "conjuntos", "tipos", "tipos_conjuntos", "ifc", "ifc_conjuntos", "camadas_2d")})


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
    return _ler_ajuste(os.path.join(_gerente()._existente(s), "detalhamento", "ajustes-furos.json"),
                       "A furação ajustada à mão")


def _gravar_ajustes_furos(s: str, ajustes: dict):
    _gravar_ajuste(os.path.join(_gerente()._existente(s), "detalhamento", "ajustes-furos.json"), ajustes)


def eixos_do_projeto(s: str) -> dict:
    """GET /api/projetos/<s>/eixos: os eixos gravados no projeto, ou identificados do modelo
    (com o nomes.json do detalhamento, quando há)."""
    from nucleo3d import eixos as _eixos
    p = _gerente().ler(s)
    gravados = _eixos.de_dict(p.get("eixos"))
    if gravados:
        return {"eixos": gravados, "gravados": True}
    doc = _documento3d_do_projeto(s)
    try:
        return {"eixos": _eixos.identificar_eixos(doc, _nomes_producao(s)), "gravados": False}
    except ValueError as e:
        raise ErroDeDados(str(e))


def gravar_eixos_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/eixos {eixos} grava; {identificar: true} identifica de novo do
    modelo e devolve (sem gravar); {apagar: true} volta ao automático."""
    from nucleo3d import eixos as _eixos
    g = _gerente()
    if corpo.get("identificar"):
        doc = _documento3d_do_projeto(s)
        try:
            return {"eixos": _eixos.identificar_eixos(doc, _nomes_producao(s)), "gravados": False}
        except ValueError as e:
            raise ErroDeDados(str(e))
    if corpo.get("apagar"):
        g._atualizar(s, eixos=None)
        return {"eixos": None, "gravados": False}
    ex = _eixos.de_dict(corpo.get("eixos"))
    if not ex:
        raise ErroDeDados("eixos inválidos: informe ao menos um eixo com nome e posição.")
    ex["origem"] = "usuario"
    g._atualizar(s, eixos=ex)
    return {"eixos": ex, "gravados": True}


def cantos_do_projeto(s: str) -> dict:
    """GET /api/projetos/<s>/cantos: as posições com canto redondo (barra calandrada) do
    modelo, com raio, ângulo e as opções de quebra em retas (nucleo3d.cantos)."""
    from nucleo3d import cantos
    doc = _documento3d_do_projeto(s)
    return {"pecas": cantos.analisar_modelo(doc), "quebradas": cantos.quebradas_do_modelo(doc)}


def _buscar_no_historico(s: str):
    """buscar(id, chave) para `cantos.desfazer_modelo`: a entidade `id` na gravação mais
    nova do histórico em que ela ainda não tinha `chave` nos atributos (peça quebrada por
    uma versão que não guardava a malha original)."""
    import gzip
    g = _gerente()
    pasta = g._pasta_historico(s)
    arquivos = [h["arquivo"] for h in g.listar_historico(s)]
    lidos: dict = {}

    def entidades_de(arquivo):
        if arquivo not in lidos:
            try:
                with gzip.open(os.path.join(pasta, arquivo), "rb") as f:
                    d = json.loads(f.read().decode("utf-8"))
                lidos[arquivo] = {e.get("id"): e for e in (d.get("entidades") or []) if isinstance(e, dict)}
            except (OSError, ValueError):
                lidos[arquivo] = {}
        return lidos[arquivo]

    def buscar(id_, chave):
        for arquivo in arquivos:
            e = entidades_de(arquivo).get(id_)
            if e is not None and not (e.get("atributos") or {}).get(chave):
                return e
        return None
    return buscar


def quebrar_cantos_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/cantos {escolhas: {marca: n}}: troca o arco de cada instância
    dessas posições por n retas tangentes no modelo 3D (o anterior vai para o histórico).
    Com {desfazer: true, marcas: [...]}: volta ao canto redondo nessas posições (todas as
    quebradas, sem `marcas`) — pela malha guardada na peça ou, faltando, pelo histórico."""
    from nucleo3d import cantos
    if corpo.get("desfazer"):
        marcas = corpo.get("marcas") or None
        try:
            _progresso(s, "voltando ao canto redondo…")
            doc = _documento3d_do_projeto(s)
            r = cantos.desfazer_modelo(doc, marcas, buscar=_buscar_no_historico(s))
            if r["pecas"]:
                _regravar_modelo(s, doc, marco=True)
                _gerente().tocar(s)
            return r
        finally:
            _fim_progresso(s)
    escolhas = corpo.get("escolhas") or {}
    if not isinstance(escolhas, dict) or not escolhas:
        raise ErroDeDados("escolha ao menos uma posição e o número de retas.")
    try:
        _progresso(s, "quebrando os cantos…")
        doc = _documento3d_do_projeto(s)
        r = cantos.quebrar_modelo(doc, escolhas)
        if r["pecas"]:
            _regravar_modelo(s, doc, marco=True)
            _gerente().tocar(s)
        return r
    finally:
        _fim_progresso(s)


CAMPOS_RESUMO = ("revisao", "descricao", "telha", "eixos", "notas_tesouras", "data")


def dados_dos_resumos(s: str) -> dict:
    """GET /api/projetos/<s>/resumos: o que o IFC não traz (revisão, descrição do projeto,
    descrição comercial da telha, letras dos eixos, notas das tesouras) e as sugestões."""
    p = _gerente().ler(s)
    dados = dict(p.get("dados_resumo") or {})
    origem = str(p.get("origem_ifc") or "")
    m = re.search(r"\.(R\d+)", origem, re.I)
    sug = {"revisao": (m.group(1).upper() if m else ""), "descricao": "Projeto de fabricação da cobertura metálica",
           "telha": "", "eixos": "", "notas_tesouras": "", "data": time.strftime("%d/%m/%Y")}
    lista = None
    caminho = os.path.join(_gerente()._existente(s), "detalhamento", "lista-de-materiais.json")
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                lista = json.load(f)
        except (OSError, ValueError):
            lista = None
    if lista:
        telhas = [t.get("perfil") for t in (lista.get("telhas") or []) if t.get("perfil")]
        if telhas:
            sug["telha"] = "Telha %s" % telhas[0]
    return {"dados": dados, "sugestoes": sug, "campos": list(CAMPOS_RESUMO)}


def gerar_resumos_projeto(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/resumos {dados}: grava `dados_resumo` no projeto e gera os
    dois documentos do mesmo levantamento da lista de materiais (nomes de produção
    atualizados e gravados; peso teórico), em detalhamento/."""
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    g = _gerente()
    dados = {k: str((corpo.get("dados") or {}).get(k) or "") for k in CAMPOS_RESUMO}
    if any(dados.values()):
        g._atualizar(s, dados_resumo=dados)
    else:
        dados = dict(g.ler(s).get("dados_resumo") or {})
    try:
        _progresso(s, "levantando as peças do modelo…")
        doc = _documento3d_do_projeto(s)
        r = detalhar(doc, grupos=["localizacao"], nomes=_nomes_producao(s), converter=False, ajustes=_ajustes_furos(s),
                     avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
        nomes = r.get("nomes") or {}
        _gravar_nomes_producao(s, nomes)
        _progresso(s, "lista de materiais…")
        categorias = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
        lista = lista_producao.montar(r["objetos_posicoes"], categorias, r["acessorios"], pecas=r["objetos_pecas"],
                                      projeto=_identificacao_do_projeto(s), nomes_conjuntos=nomes.get("ifc_conjuntos"))
        lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
        _progresso(s, "montando os resumos…")
        R = resumos.levantar_resumos(doc, lev, lista, nomes, dados)
        _progresso(s, "imprimindo os PDFs…")
        pasta = os.path.join(g._existente(s), "detalhamento")
        arquivos = resumos.gerar_resumos(pasta, R)
        g.tocar(s)
        saida = {"numeros": R["numeros"], "avisos": R.get("avisos") or [], "dados": dados}
        for k, v in arquivos.items():
            saida[k] = {n: _descrever_arquivo(c, pasta) for n, c in v.items() if n in ("html", "pdf")}
            if v.get("erro_pdf"):
                saida[k]["erro_pdf"] = v["erro_pdf"]
        return saida
    finally:
        _fim_progresso(s)


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
        lista["pre_moldados"] = lev.get("fora_do_aco") or []
        lista["estrutura_a_conferir"] = lev.get("estrutura_a_conferir") or []
        lista_producao.gravar(pasta, lista, lev["posicoes"], lev["acessorios"])
        g.tocar(s)
    arquivos = {}
    for chave, nome in (("json", lista_producao.ARQUIVO_JSON), ("html", lista_producao.ARQUIVO_HTML),
                        ("pdf", lista_producao.ARQUIVO_PDF), ("romaneio", "romaneio.csv"),
                        ("perfis", "resumo-perfis.csv"), ("dobras", "peso-dobras.csv"), ("chapas", "resumo-chapas.csv"),
                        ("conjuntos", "conjuntos.csv")):
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


_ULTIMA_CONSULTA = {"quando": 0.0, "dados": None}
#: Resposta do GitHub reaproveitada por este tempo (s): as telas perguntam ao ganhar foco,
#: e a API sem autenticação aceita 60 consultas por hora.
CACHE_ATUALIZACAO = 300.0


def verificar_atualizacao() -> dict:
    """Consulta a última versão publicada no GitHub (releases) e diz se há uma mais nova
    que esta. Sem internet, devolve `disponivel: None` em vez de erro: a tela segue."""
    if _ULTIMA_CONSULTA["dados"] is not None and time.time() - _ULTIMA_CONSULTA["quando"] < CACHE_ATUALIZACAO:
        return dict(_ULTIMA_CONSULTA["dados"])
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
    # versão nova ainda sem o instalador anexado (a publicação sobe o .exe depois de criar a
    # release): não guarda, senão a tela ficava a tarde toda com "Ver no GitHub" e sem o
    # botão de atualizar
    if not (fora["nova"] and not fora.get("arquivo")):
        _ULTIMA_CONSULTA.update(quando=time.time(), dados=dict(fora))
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


#: True quando este processo é o que a atualização reabriu (a tela de antes está aberta).
REABERTO_POR_ATUALIZACAO = [False]


def _url_para_reabrir(base: str) -> str:
    """A URL inicial: a tela gravada por _gravar_reabrir, se foi há menos de 15 min."""
    arq = os.path.join(PROJETOS, ARQUIVO_REABRIR)
    try:
        with open(arq, encoding="utf-8") as f:
            dados = json.load(f)
        os.remove(arq)
        caminho = str(dados.get("caminho") or "")
        if caminho.startswith("/") and time.time() - float(dados.get("quando") or 0) < 900:
            REABERTO_POR_ATUALIZACAO[0] = True
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
    lote = gravar_lote_de_atualizacao(os.path.join(tempfile.gettempdir(), "metalica-atualizar.cmd"), destino, exe_atual)
    # CREATE_NO_WINDOW (console escondido, herdado por timeout/tasklist/find): com
    # DETACHED_PROCESS cada um desses filhos abria o próprio console — a janela preta
    # "find /i Metalica.exe" que ficava na tela até o usuário fechar
    subprocess.Popen(["cmd.exe", "/c", lote], creationflags=0x08000000 | 0x00000200,   # NO_WINDOW | NEW_PROCESS_GROUP
                     close_fds=True, cwd=tempfile.gettempdir(),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def sair():
        time.sleep(1.5)
        os._exit(0)
    threading.Thread(target=sair, daemon=True).start()
    return {"baixado": destino, "tamanho_mb": round(tamanho / 1048576, 1), "versao": info["ultima"],
            "mensagem": "Instalando a versão %s: o programa vai fechar e reabrir sozinho." % info["ultima"]}


def gravar_lote_de_atualizacao(lote: str, instalador: str, exe_atual: str, espera: int = 2) -> str:
    r"""O .cmd que instala em silêncio e reabre o programa. Gravado em UTF-8 com `chcp 65001`
    na frente: o usuário com acento no nome (C:\Users\José\…) tem acento nos caminhos, e o
    cmd lê o arquivo na página de código ativa. Separado de `instalar_atualizacao` para o
    teste rodar o arquivo de verdade (testes/test_atualizacao_lote.py)."""
    linhas = [
        "@echo off",
        "chcp 65001 >nul",                                 # as linhas abaixo são UTF-8
        "timeout /t %d /nobreak >nul" % espera,
        '"%s" /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS' % instalador,
        "timeout /t %d /nobreak >nul" % (espera + 1),
        'del /q "%s" >nul 2>&1' % instalador,              # o instalador já cumpriu o papel
        'if not exist "%s" exit /b 1' % exe_atual,
        'tasklist /fi "imagename eq Metalica.exe" | find /i "Metalica.exe" >nul || start "" "%s"' % exe_atual,
    ]
    with open(lote, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(linhas) + "\r\n")
    return lote


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


def _texto_do_dxf(corpo: dict) -> str:
    """O DXF vem em texto (`conteudo`) ou em base64 (`conteudo_b64`, que preserva os
    acentos dos DXF antigos, gravados em ANSI/cp1252 e não em UTF-8)."""
    if corpo.get("conteudo_b64"):
        import base64
        from nucleo2d.dxf_ler import texto_de_bytes
        return texto_de_bytes(base64.b64decode(corpo["conteudo_b64"]))
    texto = corpo.get("conteudo")
    if not isinstance(texto, str) or not texto.strip():
        raise ErroDeDados("mande o conteúdo do DXF em texto.")
    return texto


def importar_pdf_no_desenho(s: str, corpo: dict) -> dict:
    """PDF vetorial (base64) → entidades do CAD, em mm de papel, para o desenho aberto
    acrescentar como um comando. corpo: {conteudo_b64, escala, deslocamento, paginas}"""
    import base64
    from dataclasses import asdict
    from nucleo2d.desenho import Desenho
    from nucleo2d.pdf_ler import para_desenho
    if not corpo.get("conteudo_b64"):
        raise ErroDeDados("mande o PDF em base64.")
    d = Desenho(nome="importado", escala=float(corpo.get("escala") or 1.0))
    desl = corpo.get("deslocamento") or [0.0, 0.0]
    _, resumo = para_desenho(base64.b64decode(corpo["conteudo_b64"]), destino=d,
                             paginas=corpo.get("paginas") or None,
                             deslocamento=(float(desl[0]), float(desl[1])),
                             prefixo_camada=str(corpo.get("prefixo_camada") or ""))
    return {"entidades": [asdict(e) for e in d.entidades.values()],
            "camadas": {k: asdict(v) for k, v in d.camadas.items() if k in resumo["camadas_novas"]},
            "resumo": {k: v for k, v in resumo.items() if k != "ids"}}


def reconhecer_no_desenho(s: str, nome: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/desenhos/<nome>/reconhecer: lê os perfis escritos no
    projeto recebido (DXF/PDF importado) e devolve as peças reconhecidas como linhas da
    camada "PEÇAS RECONHECIDAS", mais as vistas e a montagem sugerida.

    corpo: {desenho: o desenho aberto no CAD (senão o gravado), fator: força a escala}.
    Não grava: o CAD acrescenta as linhas como um comando (Ctrl+Z desfaz)."""
    from dataclasses import asdict
    from nucleo2d import reconhecer
    from nucleo2d.desenho import Desenho
    bruto = corpo.get("desenho") if isinstance(corpo.get("desenho"), dict) else _gerente().abrir_desenho(s, nome)
    des = Desenho.de_dict(bruto)
    _progresso(s, "reconhecendo as peças do desenho…")
    try:
        r = reconhecer.reconhecer(des, fator=float(corpo["fator"]) if corpo.get("fator") else None,
                                  avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
    finally:
        _fim_progresso(s)
    antigas = [k for k, e in des.entidades.items() if (e.atributos or {}).get("reconhecido")]
    novas = reconhecer.aplicar(des, r)
    mont = reconhecer.sugerir_montagem(r)
    rec = dict(des.metadados.get("reconhecimento") or {})
    rec["montagens"] = mont["montagens"]
    return {"entidades": [asdict(e) for e in novas], "remover": antigas,
            "camadas": {k: asdict(des.camadas[k]) for k in (reconhecer.CAMADA_OK, reconhecer.CAMADA_CONFERIR)},
            "reconhecimento": rec, "vistas": r["vistas"], "resumo": r["resumo"],
            "avisos": r["avisos"] + mont["avisos"], "textos_sem_linha": r["textos_sem_linha"][:60],
            "montagens": mont["montagens"]}


def _exportar_ifc_do_projeto(s: str, doc, nome: str) -> dict:
    from ifc import exportar as exp
    g = _gerente()
    pasta = os.path.join(g._existente(s), "ifc")
    os.makedirs(pasta, exist_ok=True)
    caminho = exp.exportar(doc, os.path.join(pasta, _slug(nome or doc.nome or "modelo") + ".ifc"),
                           projeto_nome=doc.nome)
    return _descrever_arquivo(caminho, pasta)


def projeto_2d_para_modelo(s: str, corpo: dict) -> dict:
    """POST /api/projetos/<s>/projeto-2d: o projeto recebido em DXF ou PDF vira, de uma
    vez, um desenho no CAD (com as peças reconhecidas numa camada própria), o modelo 3D
    do projeto e o IFC.

    corpo: {arquivo: nome do arquivo, conteudo_b64, tipo: "dxf"|"pdf" (pela extensão),
            modo: "substituir"|"acrescentar", ifc: true, fator: força a escala,
            perfis: {papel: perfil} para as peças reconhecidas só pela forma (sem perfil escrito)}"""
    import base64
    from nucleo2d import reconhecer
    from nucleo2d.desenho import Desenho
    from nucleo3d import de_vistas
    from nucleo3d.modelo import Documento
    g = _gerente()
    arquivo = str(corpo.get("arquivo") or "projeto")
    tipo = str(corpo.get("tipo") or os.path.splitext(arquivo)[1].lstrip(".")).lower()
    if not corpo.get("conteudo_b64"):
        raise ErroDeDados("mande o arquivo em base64.")
    dados = base64.b64decode(corpo["conteudo_b64"])
    try:
        _progresso(s, "lendo %s…" % arquivo)
        if tipo == "pdf":
            from nucleo2d.pdf_ler import para_desenho as ler_pdf
            des, lido = ler_pdf(dados, destino=Desenho(nome="Projeto recebido", escala=1.0))
            des.metadados["origem_arquivo"] = "pdf"
        elif tipo == "dxf":
            from nucleo2d.dxf_ler import para_desenho as ler_dxf, texto_de_bytes
            des, lido = ler_dxf(texto_de_bytes(dados), escala=50.0, destino=Desenho(nome="Projeto recebido", escala=50.0))
            des.metadados["origem_arquivo"] = "dxf"
        else:
            raise ErroDeDados("o projeto tem de vir em DXF ou PDF (DWG: salve como DXF no CAD de origem).")
        des.metadados["arquivo_recebido"] = arquivo
        r = reconhecer.reconhecer(des, fator=float(corpo["fator"]) if corpo.get("fator") else None,
                                  avisar=lambda *a: _progresso(s, " ".join(str(x) for x in a)))
        reconhecer.aplicar(des, r)
        mont = reconhecer.sugerir_montagem(r)
        des.metadados["reconhecimento"]["montagens"] = mont["montagens"]
        nome_des = "Projeto recebido – " + os.path.splitext(arquivo)[0]
        des.nome = nome_des
        _progresso(s, "gravando o desenho…")
        g.salvar_desenho(s, nome_des, des.dict())
        saida = {"desenho": nome_des, "lido": {k: v for k, v in lido.items() if k != "ids"},
                 "vistas": r["vistas"], "resumo": r["resumo"], "textos_sem_linha": r["textos_sem_linha"][:60],
                 "avisos": list(lido.get("avisos") or []) + r["avisos"] + mont["avisos"], "montagens": mont["montagens"],
                 "sem_perfil": des.metadados["reconhecimento"].get("sem_perfil") or {},
                 "perfis_padrao": des.metadados["reconhecimento"].get("perfis_padrao") or {}}
        if not r["barras"] or corpo.get("gerar") is False:
            return saida
        _progresso(s, "montando o modelo 3D…")
        base = None
        if str(corpo.get("modo") or "substituir") == "acrescentar":
            atual = g.abrir_modelo(s)
            base = Documento.de_dict(atual) if atual else None
        doc = de_vistas.modelo_das_vistas(des, mont["montagens"], nome=os.path.splitext(arquivo)[0], doc=base,
                                          perfis=corpo.get("perfis") if isinstance(corpo.get("perfis"), dict) else None)
        _regravar_modelo(s, doc)
        g.tocar(s)
        saida["modelo"] = {"entidades": len(doc.entidades), "barras": len(doc.barras)}
        saida["gerado"] = {k: v for k, v in doc.metadados.get("de_desenho", {}).items() if k != "montagens"}
        if corpo.get("ifc", True):
            _progresso(s, "gravando o IFC…")
            saida["ifc"] = _exportar_ifc_do_projeto(s, doc, os.path.splitext(arquivo)[0])
        return saida
    finally:
        _fim_progresso(s)


def importar_dxf_no_desenho(s: str, corpo: dict) -> dict:
    """DXF (texto) → entidades do CAD, para o desenho aberto acrescentar como um comando.

    corpo: {conteudo: texto do DXF, escala: do desenho de destino, fator: mm por unidade
            (None = pelo $INSUNITS), deslocamento: [x, y], prefixo_camada: ""}"""
    from nucleo2d.desenho import Desenho
    from nucleo2d.dxf_ler import para_desenho
    from dataclasses import asdict
    texto = _texto_do_dxf(corpo)
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
    # o nome vem da tela: sem pasta nem caracteres de caminho, e com a extensão só uma vez
    base = _slug(re.sub(r"\.pdf$", "", os.path.basename(str(base).replace("\\", "/")), flags=re.I)) or "desenho"
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
    destino = os.path.join(pasta, _slug(nome) + ".dxf")
    try:
        # R2010 pela ezdxf: cotas DIMENSION, cores e estilo de texto do CAD, grupos por peça
        from nucleo2d import dxf_cad
        caminho = dxf_cad.exportar(desenho, destino, float(escala) if escala else None)
    except ImportError:
        caminho = desenho.para_dxf(float(escala) if escala else None).gravar(destino)
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
    saida = {"perfis": [], "materiais": [], "acos": [a.nome for a in mat.ACOS.values()],
             "parafusos": [p.nome for p in mat.PARAFUSOS.values() if "chumbador" not in (p.norma or "")],
             "eletrodos": [e.nome for e in mat.ELETRODOS.values()]}
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
        raiz_abs = os.path.abspath(raiz)
        try:
            dentro = os.path.commonpath([os.path.normcase(caminho), os.path.normcase(raiz_abs)]) == os.path.normcase(raiz_abs)
        except ValueError:                                   # outro disco
            dentro = False
        if not dentro:
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
        if self._de_fora():
            return self._erro("pedido de fora do programa recusado", 403)
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
            if rota == "/api/fabrica":
                import fabrica
                return self._json({"regras": fabrica.regras(PROJETOS), "padrao": fabrica.REGRAS_PADRAO,
                                   "perfis": fabrica.perfis(PROJETOS)})
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
                if len(partes) == 3 and partes[1] == "calculo" and partes[2] == "alternativas":
                    q = parse_qs(urlparse(self.path).query)
                    return self._json(alternativas_de_perfil(
                        partes[0], (q.get("marca") or [""])[0],
                        int((q.get("limite") or ["10"])[0] or 10),
                        (q.get("todas") or ["0"])[0] in ("1", "true")))
                if len(partes) == 2 and partes[1] == "desenhos":
                    return self._json(_gerente().listar_desenhos(partes[0]))
                if len(partes) == 2 and partes[1] == "resumos":
                    return self._json(dados_dos_resumos(partes[0]))
                if len(partes) == 2 and partes[1] == "cantos":
                    return self._json(cantos_do_projeto(partes[0]))
                if len(partes) == 2 and partes[1] == "eixos":
                    return self._json(eixos_do_projeto(partes[0]))
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
            if rota in ("/analise", "/resultado-da-analise"):
                return self._arquivo(os.path.join(WEB, "analise.html"), WEB)
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

    def _de_fora(self) -> bool:
        """O pedido não veio das telas do programa? O servidor local não pode obedecer a
        uma página qualquer aberta no navegador (excluir projeto, sobrescrever modelo pelo
        127.0.0.1): o navegador manda Origin nos pedidos de outro site, e o Host de um
        nome que aponta para cá (troca de DNS) não é o nosso."""
        porta = self.server.server_address[1]
        nossos = {"localhost", "127.0.0.1", "[::1]"}
        host = (self.headers.get("Host") or "").strip().lower()
        if host:
            nome, _, p = host.rpartition(":") if not host.endswith("]") else (host, "", "")
            if (nome or host) not in nossos or (p and p != str(porta)):
                return True
        origem = (self.headers.get("Origin") or "").strip().lower()
        if origem and origem not in {"http://%s:%d" % (h, porta) for h in nossos}:
            return True
        return False

    def do_POST(self):
        rota = unquote(urlparse(self.path).path)
        if self._de_fora():
            return self._erro("pedido de fora do programa recusado", 403)
        if rota in ("/api/vivo", "/api/fechou"):
            _sinal_de_vida(self.path, rota == "/api/fechou")
            return self._json({"ok": True})
        # pedido em curso segura o encerramento automático (fechar a janela no meio do
        # Detalhar deixava o projeto com os desenhos antigos na lixeira e os novos por gravar)
        _em_curso(+1)
        try:
            return self._do_post(rota)
        finally:
            _em_curso(-1)

    def _do_post(self, rota):
        try:
            corpo = self._corpo()
            if rota == "/api/dimensionar":
                return self._json(dimensionar(corpo))
            if rota == "/api/tesoura":
                return self._json(geometria_da_tesoura(corpo))
            if rota == "/api/gerar":
                return self._json(gerar_saidas(corpo))
            if rota == "/api/pasta-de-dados":
                _abrir_no_explorador(PROJETOS)
                return self._json({"aberta": PROJETOS})
            if rota == "/api/atualizacao/instalar":
                return self._json(instalar_atualizacao(corpo if isinstance(corpo, dict) else None))
            if rota == "/api/projetos":
                return self._json(criar_projeto(corpo))
            if rota.startswith("/api/fabrica/"):
                return self._json(_rota_fabrica(rota, corpo if isinstance(corpo, dict) else {}))
            if rota.startswith("/api/projetos/"):
                partes = rota.split("/api/projetos/", 1)[1].strip("/").split("/")
                if len(partes) == 2 and partes[1] == "vista2d":
                    return self._json(gerar_vista_2d(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "detalhar":
                    return self._json(detalhar_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "calcular":
                    return self._json(calcular_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "dimensionar":
                    return self._json(dimensionar_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "materiais":
                    return self._json(lista_de_materiais(partes[0], recalcular=True, corpo=corpo))
                if len(partes) == 2 and partes[1] == "resumos":
                    return self._json(gerar_resumos_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "cantos":
                    return self._json(quebrar_cantos_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "eixos":
                    return self._json(gravar_eixos_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "detalhar-posicao":
                    return self._json(detalhar_posicao_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "atualizar-pecas":
                    return self._json(atualizar_pecas_projeto(partes[0], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "gerar-3d":
                    return self._json(gerar_3d_do_desenho(partes[0], partes[2], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "aplicar-furos":
                    return self._json(aplicar_furos_do_desenho(partes[0], partes[2], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "aplicar-pecas":
                    return self._json(aplicar_pecas_do_desenho(partes[0], partes[2], corpo))
                if len(partes) == 3 and partes[1] == "materiais" and partes[2] == "pdf":
                    return self._json(pdf_da_lista_de_materiais(partes[0]))
                if len(partes) == 2 and partes[1] == "pranchas":
                    return self._json(montar_pranchas_projeto(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "importar-dxf":
                    return self._json(importar_dxf_no_desenho(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "importar-pdf":
                    return self._json(importar_pdf_no_desenho(partes[0], corpo))
                if len(partes) == 2 and partes[1] == "projeto-2d":
                    return self._json(projeto_2d_para_modelo(partes[0], corpo))
                if len(partes) == 4 and partes[1] == "desenhos" and partes[3] == "reconhecer":
                    return self._json(reconhecer_no_desenho(partes[0], partes[2], corpo))
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


_PEDIDOS_EM_CURSO = [0]


def _em_curso(delta: int):
    with _TRAVA_JANELAS:
        _PEDIDOS_EM_CURSO[0] = max(0, _PEDIDOS_EM_CURSO[0] + delta)


def _trabalho_em_curso() -> bool:
    """Há gravação ou operação longa (Detalhar, cálculo, importação) em andamento?"""
    with _TRAVA_JANELAS:
        if _PEDIDOS_EM_CURSO[0]:
            return True
    return bool(PROGRESSO)


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

    def lixeira():
        try:
            from projetos import esvaziar_lixeira_antiga
            n = esvaziar_lixeira_antiga(PROJETOS)               # desenhos apagados há mais de 30 dias
            if n:
                print("  lixeira: %d desenho(s) apagado(s) há mais de 30 dias removido(s)" % n, flush=True)
        except Exception:                                       # noqa: BLE001
            pass
    threading.Thread(target=lixeira, daemon=True).start()
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
            # Reaberto pela atualização: a janela de antes continua na tela, com o aviso
            # de instalação, e volta sozinha para onde estava assim que este servidor
            # responde (web/atualizacao.js). Se ela dá sinal de vida, não se abre outra;
            # se o usuário a fechou no meio, abre-se uma nova como sempre.
            espera = 10.0 if REABERTO_POR_ATUALIZACAO[0] else 0.0
            inicio_espera = time.time()
            while time.time() - inicio_espera < espera and not _janelas_abertas():
                time.sleep(0.25)
            if not _janelas_abertas():
                if _abrir_janela(url) is None:
                    webbrowser.open(url)        # sem Edge nem Chrome: navegador padrão
            # Encerra quando nenhuma janela dá sinal de vida (web/vivo.js). O processo do
            # navegador não serve de referência: havendo outro Chrome com o mesmo perfil,
            # o que lançamos entrega a janela a ele e sai na hora, com a janela aberta.
            inicio, vazio_desde, ja_abriu = time.time(), None, False
            while True:
                time.sleep(1.0)
                abertas = _janelas_abertas()
                if abertas or _trabalho_em_curso():
                    # janela aberta, ou operação em andamento com a janela já fechada:
                    # termina o que começou antes de sair
                    ja_abriu, vazio_desde = ja_abriu or bool(abertas), None
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
