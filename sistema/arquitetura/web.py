# -*- coding: utf-8 -*-
"""As rotas do módulo de arquitetura no desenvolvimento (o gancho `_extensoes_dev` do app.py, como o pré-moldado).

* GET  /api/dev/arquitetura.js           a área "Arquitetura" na tela de projetos (antes do script do pré-moldado)
* GET  /arquitetura/<arquivo>            os arquivos de web/arquitetura
* POST /api/projetos {..., area: "arquitetura"}   o projeto novo nasce na área da arquitetura, com os níveis padrão
* POST /api/arquitetura/piloto           monta (ou remonta) a casa piloto num projeto próprio
* POST /api/arquitetura/regenerar {projeto}   refaz as paredes, esquadrias, lajes e ambientes pelas definições
"""
import json
import os
import sys

import projetos
from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento

from . import modelo as M
from . import piloto

TIPO = AREA = "arquitetura"
projetos.TIPOS.setdefault(TIPO, "Projeto de arquitetura (em desenvolvimento)")

_AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(_AQUI), "web", "arquitetura")
NIVEIS_PADRAO = [{"nome": "Térreo", "cota": 0, "laje": 100}, {"nome": "Superior", "cota": 3000, "laje": 150},
                 {"nome": "Cobertura", "cota": 6000, "laje": 150}]


def _app():
    return sys.modules.get("app") or sys.modules["__main__"]


def _gravar(g, s: str, doc: Documento, marco=True):
    g.salvar_modelo(s, doc.dict(), marco=marco)


def _ler(g, s: str) -> Documento:
    caminho = g.caminho_modelo(s)
    if not os.path.exists(caminho):
        raise ErroDeDados("o projeto ainda não tem modelo 3D")
    with open(caminho, encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def _criar(g, corpo: dict) -> str:
    r = _app().criar_projeto(dict(corpo, tipo=TIPO))
    g._atualizar(r["slug"], area=AREA)
    return r["slug"]


def rota_get(h, rota: str) -> bool:
    if rota == "/api/dev/arquitetura.js":
        h._arquivo(os.path.join(WEB, "dev_inicio_arq.js"), WEB)
        return True
    if rota.startswith("/arquitetura/"):
        h._arquivo(os.path.join(WEB, rota[len("/arquitetura/"):]), WEB)
        return True
    return False


def rota_post(h, rota: str, corpo: dict) -> bool:
    g = None
    if rota == "/api/projetos" and isinstance(corpo, dict) and corpo.get("area") == AREA:
        g = _app()._gerente()
        s = _criar(g, corpo)
        doc = Documento(nome=corpo.get("nome") or "Arquitetura")
        M.definir_niveis(doc, NIVEIS_PADRAO)
        M.regenerar(doc)
        M.so_camadas_da_arquitetura(doc)
        _gravar(g, s, doc, marco=False)
        h._json(g.resumo(s))
        return True
    if rota == "/api/arquitetura/piloto":
        g = _app()._gerente()
        s = next((p["slug"] for p in g.listar() if p.get("nome") == piloto.NOME_PROJETO), None)
        if not s:
            s = _criar(g, {"nome": piloto.NOME_PROJETO, "local": "demonstração (sem endereço)"})
        doc = piloto.montar_casa()
        _gravar(g, s, doc)
        r = g.resumo(s)
        r["arquitetura"] = doc.metadados["arquitetura"]["piloto"]["resumo"]
        h._json(r)
        return True
    if rota == "/api/arquitetura/regenerar":
        g = _app()._gerente()
        s = (corpo or {}).get("projeto") or ""
        if not s:
            raise ErroDeDados("diga o projeto")
        doc = _ler(g, s)
        r = M.regenerar(doc)
        _gravar(g, s, doc)
        h._json(r)
        return True
    return False
