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
    GET  /api/projetos              lista projetos salvos
    POST /api/projetos              salva um projeto (JSON de entrada)
    GET  /api/projetos/<nome>       carrega um projeto salvo
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
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
PROJETOS = os.path.join(BASE, "projetos")
sys.path.insert(0, BASE)

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
    pasta = os.path.join(PROJETOS, _slug(dados.nome))
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


def salvar_projeto(entrada: dict) -> dict:
    dados = _dados_de(entrada)
    os.makedirs(PROJETOS, exist_ok=True)
    caminho = os.path.join(PROJETOS, _slug(dados.nome) + ".json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados.dict(), f, ensure_ascii=False, indent=1)
    return {"salvo": os.path.basename(caminho), "nome": dados.nome}


def listar_projetos() -> list:
    if not os.path.isdir(PROJETOS):
        return []
    saida = []
    for f in sorted(os.listdir(PROJETOS)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(PROJETOS, f), encoding="utf-8") as fh:
                    d = json.load(fh)
                saida.append({"arquivo": f, "nome": d.get("nome", f),
                              "vao": d.get("vao"), "comprimento": d.get("comprimento")})
            except Exception:
                pass
    return saida


def carregar_projeto(nome: str) -> dict:
    caminho = os.path.join(PROJETOS, os.path.basename(nome))
    if not caminho.endswith(".json"):
        caminho += ".json"
    if not os.path.exists(caminho):
        raise ErroDeDados(f"projeto não encontrado: {nome}")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)



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
    pasta = os.path.join(PROJETOS, nome, "ifc")
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
    pasta = os.path.join(PROJETOS, nome, "detalhamento")
    rel = detalhamento.gerar(destino, pasta)
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
    temporario = caminho + ".parcial"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(doc.dict(), f, ensure_ascii=False)
    os.replace(temporario, caminho)
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
            if rota == "/" or rota == "/index.html":
                return self._arquivo(os.path.join(WEB, "index.html"), WEB)
            if rota == "/api/catalogo":
                return self._json(catalogo())
            if rota == "/api/projetos":
                return self._json(listar_projetos())
            if rota.startswith("/api/projetos/"):
                return self._json(carregar_projeto(rota.split("/api/projetos/", 1)[1]))
            if rota == "/api/modelo/catalogo":
                return self._json(catalogo_3d())
            if rota == "/api/modelo/lista":
                return self._json(listar_modelos())
            if rota.startswith("/api/modelo/abrir/"):
                return self._json(abrir_modelo(rota.split("/api/modelo/abrir/", 1)[1]))
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
            corpo = self._corpo()
            if rota == "/api/dimensionar":
                return self._json(dimensionar(corpo))
            if rota == "/api/gerar":
                return self._json(gerar_saidas(corpo))
            if rota == "/api/projetos":
                return self._json(salvar_projeto(corpo))
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


def main():
    porta = 8765
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    os.makedirs(PROJETOS, exist_ok=True)
    servidor, extras = _servidores(porta)
    for s in extras:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    url = f"http://localhost:{porta}/"
    print(f"Sistema de dimensionamento de estruturas metálicas")
    print(f"  interface: {url}")
    print(f"  projetos:  {PROJETOS}")
    print("  Ctrl+C para encerrar.")
    if "--sem-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
        for s in [servidor, *extras]:
            s.shutdown()


if __name__ == "__main__":
    main()
