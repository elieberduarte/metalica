# -*- coding: utf-8 -*-
"""A parte web do pré-moldado — extensão do modo desenvolvimento (o programa publicado não a carrega).

O app (`app.py`, com --dev) chama `rota_get(h, rota)` e `rota_post(h, rota, corpo)`: devolvem True
quando a rota é daqui (a resposta já foi escrita pelo `h`). Rotas:

* GET  /premoldado[?projeto=…]               a tela do galpão pré-moldado (web/premoldado/)
* GET  /premoldado/<arquivo>                 os arquivos da tela
* GET  /premoldado/catalogo                  o catálogo (materiais, bitolas, cobrimentos, seções)
* GET  /premoldado/ligacoes                  as ligações calculadas avulsas (cálice, consolo, elastômero)
* GET  /api/premoldado/catalogo?agregado=    os dados do catálogo
* GET  /api/premoldado/ligacoes              as listas da tela das ligações
* POST /api/premoldado/ligacao {tipo, ...}   uma ligação calculada
* POST /api/projetos {..., area: "premoldado"} o projeto novo (IFC, arquitetônico, 2D) nasce na área do pré-moldado
* POST /api/premoldado/eixos {projeto}        os vãos do galpão tirados dos eixos lançados na planta

O projeto da área do pré-moldado leva `area: "premoldado"` no projeto.json; a lista (`Projetos.resumo`)
passa a devolver esse campo para a tela inicial separar as duas áreas.
* GET  /api/dev/extensoes.js                 o script que a tela inicial ganha no modo dev
* GET  /api/premoldado/arquivo?projeto=&nome= um arquivo gerado (o memorial em PDF)
* POST /api/premoldado/dimensionar {dados, projeto?}
* POST /api/premoldado/projeto {nome, cliente, local, responsavel, dados}
* POST /api/premoldado/modelo {projeto, dados?}  → grava o 3D no projeto
* POST /api/premoldado/memorial {projeto, dados?}
* POST /api/premoldado/pranchas {projeto, dados?, formato?} as plantas de saída e o jogo de pranchas (R4)
* POST /api/premoldado/planta/dados {projeto, desenho?} os dados do galpão lidos da planta de lançamento (R3)
* POST /api/premoldado/planta/do3d {projeto, desenho?} o que mudou no 3D volta para a planta de lançamento (R5)
"""
from __future__ import annotations

import dataclasses
import os
import sys
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

import projetos
from nucleo.base import ErroDeDados
from nucleo.verificar import serializar_resultado

from . import catalogo as C
from . import galpao as G
from . import ligacoes as L
from . import cobertura as CB
from . import detalhe2d, locacao, memorial, modelo3d, plantas_saida

TIPO = "premoldado"
AREA = "premoldado"
projetos.TIPOS.setdefault(TIPO, "Galpão pré-moldado (em desenvolvimento)")


def _resumo_com_area(original):
    def resumo(self, s):
        r = original(self, s)
        if r.get("tipo") == TIPO:
            r["area"] = AREA
        else:
            try:
                r["area"] = self.ler(s).get("area") or "metalica"
            except Exception:
                r["area"] = "metalica"
        return r
    resumo._com_area = True
    return resumo


if not getattr(projetos.Projetos.resumo, "_com_area", False):
    projetos.Projetos.resumo = _resumo_com_area(projetos.Projetos.resumo)

_AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(_AQUI), "web", "premoldado")


def _app():
    return sys.modules.get("app") or sys.modules["__main__"]


def _dados_de(entrada: Dict[str, Any]) -> G.DadosGalpaoPM:
    """os campos conhecidos, com vírgula decimal aceita; as listas como vêm"""
    campos = {f.name: f for f in dataclasses.fields(G.DadosGalpaoPM)}
    d = {}
    for k, v in (entrada or {}).items():
        if k not in campos or v in (None, ""):
            continue
        padrao = campos[k].default if campos[k].default is not dataclasses.MISSING else None
        if isinstance(padrao, bool):
            v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "sim", "on")
        elif isinstance(padrao, (int, float)) and not isinstance(padrao, bool):
            v = float(str(v).replace(",", "."))
            if isinstance(padrao, int):
                v = int(v)
        elif k == "vaos_longitudinais":
            if isinstance(v, str):
                v = [float(x.replace(",", ".")) for x in v.replace(";", " ").split() if x.strip()]
            v = [float(x) for x in v]
        elif k == "pilares_oitao":
            if isinstance(v, str):
                v = [x.split("@") for x in v.replace(";", " ").split() if "@" in x]
            v = [(int(float(str(e).replace(",", "."))), float(str(y).replace(",", "."))) for e, y in v]
        elif k in ("secoes_pilar", "secoes_calha", "secoes_travamento", "secoes_viga_cobertura", "secoes_terca"):
            v = [tuple(float(y) for y in x) for x in v]
        d[k] = v
    return G.DadosGalpaoPM(**d)


def _finito(o):
    """o JSON do navegador não aceita Infinity/NaN (o do Python aceita): viram null"""
    import math as _m
    if isinstance(o, float):
        return o if _m.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finito(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finito(v) for v in o]
    return o


def para_json(p: G.ProjetoGalpaoPM) -> dict:
    return _finito(_para_json(p))


def _para_json(p: G.ProjetoGalpaoPM) -> dict:
    return {
        "ok": p.ok, "erros": p.erros, "avisos": p.avisos, "hipoteses": p.hipoteses,
        "vento": {k: p.vento.get(k) for k in ("V0", "S1", "S2", "S3", "Vk", "q")} if p.vento else None,
        "pilares": [{"tipo": q.tipo, "b": q.b, "h": q.h, "armadura": q.armadura.texto() if q.armadura else None,
                     "barras": {"n_h": q.armadura.n_h, "n_b": q.armadura.n_b, "bitola": q.armadura.bitola} if q.armadura else None,
                     "estribos": list(q.estribos), "quantidade": q.quantidade, "comprimento_total": q.comprimento_total,
                     "ok": q.ok, "razao": round(q.resultado.razao, 3) if q.resultado else None,
                     "situacoes": q.esforcos.get("situacoes"),
                     "resultado": serializar_resultado(q.resultado) if q.resultado else None} for q in p.pilares],
        "calices": [serializar_resultado(r) | {"dados_calice": {k: v for k, v in r.dados.items() if k in (
            "direcao", "Lemb", "Lemb_adotado", "externo", "interno", "h_colarinho", "fundo", "barras")}} for r in p.calices],
        "transitorias": [serializar_resultado(r) for r in p.icamento],
        "vigas": [_viga_json(v) for v in p.vigas],
        "ligacoes": [serializar_resultado(r) for r in p.ligacoes],
        "fundacoes": [serializar_resultado(r) for r in p.fundacoes],
        "lista": p.lista,
        "dados": dataclasses.asdict(p.dados),
    }


def _viga_json(v) -> dict:
    ser = lambda r: serializar_resultado(r) if r is not None else None
    return {"marca": v.marca, "funcao": v.funcao, "secao": v.secao.texto(), "tipo": v.secao.tipo, "h": v.secao.h,
            "h_apoio": v.secao_apoio.h, "parametros": v.secao.parametros, "contorno": v.secao.contorno(),
            "vao": v.vao, "comprimento": v.comprimento, "armadura": v.armadura, "texto_armadura": v.texto_armadura(),
            "quantidade": v.quantidade, "peso_kN": round(v.peso_kN, 2), "ok": v.ok,
            "razao": round(v.resultado.razao, 3) if v.resultado else None,
            "alternativas": v.alternativas, "reacoes": v.reacoes,
            "resultado": ser(v.resultado), "apoio": ser(v.apoio), "elastomero": ser(v.elastomero)}


def _projeto_e_dados(corpo: dict):
    s = corpo.get("projeto")
    g = _app()._gerente()
    dados = corpo.get("dados")
    if s and dados is None:
        dados = (g.ler(s).get("dados") or {})
    return s, g, _dados_de(dados or {})


def _editor_com_pre_moldado(h) -> None:
    """o editor 3D com o script das ferramentas pré-moldadas (ele só troca as ferramentas se o projeto for
    da área do pré-moldado) — o editor da Metálica não muda"""
    app = _app()
    html = open(os.path.join(app.WEB, "editor3d", "editor.html"), encoding="utf-8").read()
    html = html.replace("</body>", '<script type="module" src="/premoldado/editor_pm.js"></script></body>', 1)
    corpo = html.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(corpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(corpo)


def _aplicar_niveis(g, s: str, mudancas: list, niveis: list) -> dict:
    """os níveis mudados no 3D refazem o modelo do pré-moldado: com a planta de lançamento, os elementos que usam o
    nível pelo nome (o nome trocado vai junto) e o 3D gerado de novo; sem ela, o topo dos pilares do galpão (a
    altura das filas) e o 3D do galpão calculado de novo"""
    from nucleo2d.desenho import Desenho
    from nucleo3d import de_planta_estrutura as DPE
    avisos: list = []
    pj = g.ler(s)
    nome_planta = "planta-de-lançamento"
    try:
        des = Desenho.de_dict(g.abrir_desenho(s, nome_planta))
    except (OSError, KeyError, ValueError, ErroDeDados):
        des = None
    if des is not None and DPE.elementos(des):
        trocas = {str(m["de"]["nome"]): str(m["para"]["nome"]) for m in mudancas if m["de"]["nome"] != m["para"]["nome"]}
        if trocas:
            for e in des.entidades.values():
                a = e.atributos or {}
                for k in ("nivel_base", "nivel_topo", "nivel_fim"):
                    if isinstance(a.get(k), str) and a[k] in trocas:
                        a[k] = trocas[a[k]]
            g.salvar_desenho(s, nome_planta, des.dict())
        doc, av = DPE.modelo_da_planta(des, niveis, nome=pj.get("nome") or s)
        dados = pj.get("dados") or {}
        if isinstance(dados, dict) and dados.get("cobertura_projeto"):
            try:
                CB.trazer(g, dados["cobertura_projeto"], doc)
            except (ErroDeDados, OSError, KeyError) as e:
                av.append("cobertura de outra obra: %s" % e)
        g.salvar_modelo(s, doc.dict(), marco=True)
        usados = sum(1 for e in des.entidades.values() for k in ("nivel_base", "nivel_topo", "nivel_fim")
                     if isinstance((e.atributos or {}).get(k), str))
        if not usados:
            avisos.append("os elementos da planta estão com as cotas em número, não pelo nome do nível: o 3D refeito não muda "
                          "com o nível — escolha o nível no painel da ferramenta para eles seguirem")
        return {"recarregar": True, "avisos": avisos + av}
    dados = pj.get("dados")
    if not isinstance(dados, dict) or not dados:
        return {"recarregar": False, "avisos": avisos}
    d = _dados_de(dados)
    mudou = False
    for m in mudancas:
        nome, z = str(m["de"]["nome"]), float(m["para"]["z"]) / 1000.0
        if nome in ("Topo dos pilares", "Topo dos pilares — fila A"):
            d.altura_pilar, mudou = round(z, 3), True
            if nome == "Topo dos pilares" and d.altura_pilar_b:
                d.altura_pilar_b = round(z, 3)
        elif nome == "Topo dos pilares — fila B":
            d.altura_pilar_b, mudou = round(z, 3), True
    if not mudou:
        avisos.append("os níveis foram gravados; no galpão calculado só o topo dos pilares muda a estrutura (os outros "
                      "níveis saem do cálculo: base, fundo da fundação, apoio das vigas)")
        return {"recarregar": False, "avisos": avisos}
    g.salvar_dados(s, dataclasses.asdict(d))
    p = G.dimensionar(d)
    doc = modelo3d.documento(p)
    info = CB.trazer(g, d.cobertura_projeto, doc) if d.cobertura_projeto else None
    g.salvar_modelo(s, doc.dict(), marco=True)
    g._atualizar(s, niveis=CB.niveis(p, info))
    if p.erros:
        avisos.append("o galpão recalculado com a altura nova tem reprovações: %s" % "; ".join(p.erros[:3]))
    return {"recarregar": True, "avisos": avisos}


def _dividida_com_pre_moldado(h) -> None:
    """a área de trabalho (/dividida) com o script que põe na barra única os itens do lançamento e as armaduras"""
    app = _app()
    html = open(os.path.join(app.WEB, "dividida.html"), encoding="utf-8").read()
    html = html.replace('<script src="/barra_unica.js"></script>',
                        '<script src="/barra_unica.js"></script>\n<script src="/premoldado/dividida_pm.js"></script>', 1)
    corpo = html.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(corpo)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(corpo)


def rota_get(h, rota: str) -> bool:
    if rota in ("/editor", "/editor3d", "/3d", "/editor3d/editor.html"):
        _editor_com_pre_moldado(h)
        return True
    if rota in ("/dividida", "/2d-3d"):
        _dividida_com_pre_moldado(h)
        return True
    if rota == "/premoldado":
        h._arquivo(os.path.join(WEB, "index.html"), WEB)
        return True
    if rota in ("/premoldado/catalogo", "/premoldado/ligacoes"):
        h._arquivo(os.path.join(WEB, rota[len("/premoldado/"):] + ".html"), WEB)
        return True
    if rota == "/api/premoldado/catalogo":
        q = parse_qs(urlparse(h.path).query)
        h._json(C.catalogo((q.get("agregado") or ["granito"])[0]))
        return True
    if rota == "/api/premoldado/ligacoes":
        h._json(L.opcoes())
        return True
    if rota.startswith("/premoldado/"):
        h._arquivo(os.path.join(WEB, rota[len("/premoldado/"):]), WEB)
        return True
    if rota == "/api/dev/extensoes.js":
        h._arquivo(os.path.join(WEB, "dev_inicio.js"), WEB)
        return True
    if rota == "/api/premoldado/arquivo":
        q = parse_qs(urlparse(h.path).query)
        s, nome = (q.get("projeto") or [""])[0], os.path.basename((q.get("nome") or [""])[0])
        pasta = _app()._gerente().pasta(s)
        h._arquivo(os.path.join(pasta, "memorial", nome), pasta)
        return True
    return False


def vaos_dos_eixos(eixos: dict) -> dict:
    """o vão transversal (entre os eixos com letra extremos) e os vãos entre pórticos (entre os eixos
    numerados), em m, dos eixos gravados no projeto (mm)"""
    from nucleo3d import eixos as _eixos
    e = _eixos.de_dict(eixos)
    if not e:
        raise ErroDeDados("o projeto ainda não tem eixos gravados: lance a malha de eixos na planta (Desenho 2D → Malha de eixos…) e grave")
    letras, numeros = e["letras"], e["numeros"]
    avisos = []
    if len(letras) < 2 or len(numeros) < 2:
        raise ErroDeDados("os eixos da planta precisam de ao menos dois eixos com letra (o vão) e dois numerados (os pórticos)")
    vao = (letras[-1]["pos"] - letras[0]["pos"]) / 1000.0
    vaos = [round((b["pos"] - a["pos"]) / 1000.0, 3) for a, b in zip(numeros, numeros[1:])]
    if len(letras) > 2:
        avisos.append("a planta tem %d eixos com letra (%s): o galpão pré-moldado por enquanto é de um vão só, "
                      "com pilares nos extremos %s e %s — os intermediários ficam de fora"
                      % (len(letras), ", ".join(x["nome"] for x in letras), letras[0]["nome"], letras[-1]["nome"]))
    return {"vao": round(vao, 3), "vaos_longitudinais": vaos, "avisos": avisos,
            "letras": [x["nome"] for x in letras], "numeros": [x["nome"] for x in numeros]}


def rota_post(h, rota: str, corpo: dict) -> bool:
    if rota == "/api/projetos" and isinstance(corpo, dict) and corpo.get("area") == AREA:
        g = _app()._gerente()
        r = _app().criar_projeto(corpo)
        g._atualizar(r["slug"], area=AREA)
        h._json(g.resumo(r["slug"]))
        return True
    if not rota.startswith("/api/premoldado/"):
        return False
    acao = rota[len("/api/premoldado/"):]
    if acao == "ligacao":
        h._json(_finito(L.calcular(corpo.get("tipo") or "", corpo)))
        return True
    if acao == "cobertura_geometria":
        slug = corpo.get("cobertura_projeto") or ""
        if not slug:
            raise ErroDeDados("escolha a obra da cobertura primeiro")
        h._json(_finito(CB.geometria(CB.alinhamento(_app()._gerente(), slug))))
        return True
    if acao == "niveis":
        s = corpo.get("projeto")
        if not s:
            raise ErroDeDados("abra um projeto para gravar os níveis")
        lista = [{"nome": str(n.get("nome") or "")[:40], "z": float(str(n.get("z") or 0).replace(",", "."))}
                 for n in (corpo.get("niveis") or []) if isinstance(n, dict) and n.get("nome")]
        g = _app()._gerente()
        g._atualizar(s, niveis=sorted(lista, key=lambda n: n["z"]))
        saida = {"ok": True, "niveis": lista, "avisos": [], "recarregar": False}
        if corpo.get("aplicar") and corpo.get("mudancas"):
            saida.update(_aplicar_niveis(g, s, corpo["mudancas"], lista))
        h._json(saida)
        return True
    if acao == "planta/3d":
        s = corpo.get("projeto")
        nome = corpo.get("desenho") or "planta-de-lançamento"
        if not s:
            raise ErroDeDados("abra um projeto para gerar o 3D")
        from nucleo2d.desenho import Desenho
        from nucleo3d import de_planta_estrutura as DPE
        g = _app()._gerente()
        pj = g.ler(s)
        des = Desenho.de_dict(g.abrir_desenho(s, nome))
        if corpo.get("sincronizar") and not DPE.elementos(des):
            # a planta ficou sem elementos (o último pilar apagado): o 3D tira as peças que vieram dela — antes dava
            # "nenhum elemento da planta virou peça" e o pilar apagado ficava no 3D (06/10)
            from nucleo3d.modelo import Documento
            h._json(_sincronizar_planta(g, s, nome, Documento(nome=pj.get("nome") or s), [], estrito=True))
            return True
        doc, avisos = DPE.modelo_da_planta(des, pj.get("niveis") or [], nome=pj.get("nome") or s)
        for e in doc.entidades.values():
            e.atributos = dict(e.atributos or {}, planta=nome)          # de que planta a peça veio (a sincronização)
        if corpo.get("sincronizar"):
            # a planta e o 3D ligados (06/10, "os dois precisam ser melhor conectados"): cada mudança nos elementos da
            # planta troca no 3D só as peças que vieram dela (as apagadas na planta somem); o que foi feito no 3D fica
            h._json(_sincronizar_planta(g, s, nome, doc, avisos))
            return True
        # a cobertura de outra obra (o pré-moldado), para conferir o encaixe, e os níveis
        dados = pj.get("dados") or {}
        if isinstance(dados, dict) and dados.get("cobertura_projeto"):
            try:
                info = CB.trazer(g, dados["cobertura_projeto"], doc)
                pil = [(str(a.get("marca") or e.id), a["centro"][0], a["centro"][1], float(a.get("nivel_topo") or 0)) for e in des.entidades.values()
                       for a in [e.atributos or {}] if a.get("elemento") == "pilar" and a.get("centro")]
                topo = max((float(a.get("nivel_topo") or 0) for e in des.entidades.values() for a in [e.atributos or {}] if a.get("elemento") == "pilar"), default=0.0)
                if pil:                                     # sem pilar lançado não há o que conferir
                    avisos += ["Cobertura %s: %s" % (info["nome"], t) for t in CB.conferir(info, pil, topo, 0.0) if "vão" not in t]
            except (ErroDeDados, OSError, KeyError) as e:
                avisos.append("cobertura de outra obra: %s" % e)
        g.salvar_modelo(s, doc.dict(), marco=True)
        est = doc.estatisticas()
        h._json({"ok": True, "url": "/editor3d?projeto=%s" % s, "avisos": avisos, "estatisticas": est,
                 "resumo": doc.metadados.get("de_planta_estrutura")})
        return True
    if acao == "planta/do3d":  # noqa: E501
        # R5: o que mudou no 3D volta para a planta de lançamento
        s = corpo.get("projeto")
        nome = corpo.get("desenho") or "planta-de-lançamento"
        if not s:
            raise ErroDeDados("abra um projeto para atualizar a planta")
        from nucleo2d.desenho import Desenho
        from nucleo3d import de_planta_estrutura as DPE
        from nucleo3d.modelo import Documento
        g = _app()._gerente()
        pj = g.ler(s)
        des = Desenho.de_dict(g.abrir_desenho(s, nome))
        m = g.abrir_modelo(s)
        if not m:
            raise ErroDeDados("o projeto não tem modelo 3D: use Estrutura → Gerar 3D da planta")
        doc = Documento.de_dict(m)
        r = DPE.planta_do_modelo(des, doc, pj.get("niveis") or [])
        if r["alteracoes"]:
            g.salvar_desenho(s, nome, des.dict())
        if r["modelo_mudou"]:
            g.salvar_modelo(s, doc.dict(), marco=True)
        h._json({"ok": True, "alteracoes": r["alteracoes"], "novos": r["novos"], "sem_peca": r["sem_peca"],
                 "desenho": des.dict() if r["alteracoes"] else None})
        return True
    if acao == "planta/dados":
        # os dados do galpão lidos da planta de lançamento (o ciclo arquitetônico → lançamento → cálculo)
        s = corpo.get("projeto")
        nome = corpo.get("desenho") or "planta-de-lançamento"
        if not s:
            raise ErroDeDados("abra um projeto para ler a planta")
        from nucleo2d.desenho import Desenho
        from . import da_planta as DP
        g = _app()._gerente()
        pj = g.ler(s)
        try:
            des = Desenho.de_dict(g.abrir_desenho(s, nome))
        except (OSError, KeyError, ValueError):
            raise ErroDeDados("o projeto não tem a planta de lançamento (%s): lance a estrutura no CAD, menu Estrutura" % nome)
        base = _dados_de(pj.get("dados") or {})
        d, avisos = DP.dados_da_planta(des, pj.get("niveis") or [], base)
        g.salvar_dados(s, dataclasses.asdict(d))
        h._json({"ok": True, "dados": dataclasses.asdict(d), "avisos": avisos})
        return True
    if acao == "eixos":
        s = corpo.get("projeto")
        if not s:
            raise ErroDeDados("abra ou crie o projeto pré-moldado primeiro")
        h._json(vaos_dos_eixos(_app()._gerente().ler(s).get("eixos")))
        return True
    if acao == "projeto":
        g = _app()._gerente()
        r = g.criar(corpo.get("nome") or "Galpão pré-moldado", corpo.get("cliente", ""), corpo.get("local", ""),
                    corpo.get("responsavel", ""), tipo=TIPO, dados=corpo.get("dados") or dataclasses.asdict(G.DadosGalpaoPM()))
        h._json(r)
        return True
    s, g, d = _projeto_e_dados(corpo)
    if s and corpo.get("dados") is not None:
        g.salvar_dados(s, dataclasses.asdict(d))
    p = G.dimensionar(d)
    if d.cobertura_projeto:
        try:
            info = CB.alinhamento(g, d.cobertura_projeto)
            p.avisos += ["Cobertura %s: %s" % (info["nome"], t) for t in
                         CB.conferir(info, CB.pilares_em_planta(p), d.altura_pilar * 1000.0, d.vao * 1000.0)] or [
                "Cobertura %s: os apoios caem nos pilares e no topo deles" % info["nome"]]
        except (ErroDeDados, OSError, KeyError) as e:
            p.avisos.append("Cobertura de outra obra: %s" % e)
    p.avisos += plantas_saida.conflitos(p)
    if acao == "dimensionar":
        h._json(para_json(p))
        return True
    if not s:
        raise ErroDeDados("abra ou crie o projeto pré-moldado primeiro")
    if acao == "modelo":
        doc = modelo3d.documento(p)
        info = CB.trazer(g, d.cobertura_projeto, doc) if d.cobertura_projeto else None
        g.salvar_modelo(s, doc.dict(), marco=True)
        atuais = g.ler(s).get("eixos") or {}
        campos = {"niveis": CB.niveis(p, info)}
        if not atuais or atuais.get("origem") == "premoldado":
            campos["eixos"] = modelo3d.eixos(p)
        g._atualizar(s, **campos)
        h._json({"ok": True, "url": "/dividida?projeto=%s&vista=3d" % s, "estatisticas": doc.estatisticas()})
        return True
    if acao == "detalhamento":
        des = detalhe2d.desenho(p)
        g.salvar_desenho(s, "pilares-pre-moldados", des.dict())
        # a locação: a mesma do botão e das pranchas (locacao.py), num nome só — antes saíam duas
        g.salvar_desenho(s, "locacao-pilares", locacao.desenho(p).dict())
        h._json({"ok": True, "url": "/dividida?projeto=%s&vista=2d&desenho=%s" % (s, "locacao-pilares"), "entidades": des.tamanho})
        return True
    if acao == "locacao":
        # a planta de locação dos pilares (eixos, pilares, cálices e fundações; o detalhe de cada tipo em 1:25)
        des = locacao.desenho(p)
        nome = "locacao-pilares"
        g.salvar_desenho(s, nome, des.dict())
        h._json({"ok": True, "url": "/cad?projeto=%s&desenho=%s" % (s, nome), "entidades": des.tamanho})
        return True
    if acao == "pranchas":
        # R4: as plantas de saída (locação, fôrmas da cobertura, cálices e fundações, cortes, pilares) gravadas
        # como desenhos do projeto e montadas no jogo de pranchas (o mesmo da Metálica)
        nomes = ["locacao-pilares"]
        g.salvar_desenho(s, "locacao-pilares", locacao.desenho(p).dict())
        for slug_, des in plantas_saida.desenhos(p):
            g.salvar_desenho(s, slug_, des.dict())
            nomes.append(slug_)
        g.salvar_desenho(s, "pilares-pre-moldados", detalhe2d.desenho(p).dict())
        nomes.append("pilares-pre-moldados")
        r = _app().montar_pranchas_projeto(s, {"desenhos": nomes, "formato": corpo.get("formato") or "A1", "titulo": "Pranchas pré-moldado"})
        h._json({"ok": True, "url": "/cad?projeto=%s&desenho=%s" % (s, r["desenho"]), "pranchas": r["pranchas"], "desenhos": nomes,
                 "avisos": p.avisos})
        return True
    if acao == "memorial":
        pasta = os.path.join(g.pasta(s), "memorial")
        caminho = memorial.gerar(p, pasta)
        nome = os.path.basename(caminho)
        h._json({"ok": True, "arquivo": caminho, "url": "/api/premoldado/arquivo?projeto=%s&nome=%s" % (s, nome)})
        return True
    raise ErroDeDados("rota do pré-moldado desconhecida: %s" % acao)

def _da_planta(e, nome: str, estrito: bool = False) -> bool:
    """A peça do 3D que veio desta planta: marcada com `planta`, ou (gerada antes da marca) com o elemento e o id do
    contorno da planta e sem o eixo das peças do galpão pré-moldado. `estrito`: só a marcada com esta planta — a
    limpeza pela planta vazia não pode levar a peça sem marca de outra planta (um desenho de detalhamento vazio)."""
    a = e.atributos or {}
    if a.get("planta"):
        return a.get("planta") == nome
    if estrito:
        return False
    from nucleo3d import de_planta_estrutura as DPE
    return bool(a.get("origem_2d")) and a.get("elemento") in DPE.ELEMENTOS and not a.get("eixo")


def _sincronizar_planta(g, s: str, nome: str, novo, avisos, estrito: bool = False) -> dict:
    """Troca no modelo 3D do projeto as peças desta planta pelas de agora (`novo`); o resto do modelo fica."""
    from nucleo3d.modelo import Documento
    m = g.abrir_modelo(s)
    doc = Documento.de_dict(m) if m else Documento(nome=novo.nome)
    antes = [k for k, e in doc.entidades.items() if _da_planta(e, nome, estrito)]
    for k in antes:
        del doc.entidades[k]
    for nome_c, c in novo.camadas.items():
        if nome_c not in doc.camadas:
            doc.camadas[nome_c] = c
    for e in novo.entidades.values():
        doc.add(e)
    if not antes and not novo.entidades:
        return {"ok": True, "mudou": False, "avisos": avisos}
    # a cobertura retrátil (06/10, Kaefer): com ela ligada na análise, a tesoura da planta é o molde e o 3D mostra as n
    # tesouras e a sanfona da análise, na situação escolhida (nucleo3d/cobertura_movel.py)
    pj = g.ler(s)
    par = pj.get("analise_parametros") or {}
    desenho_novo = None
    if par.get("cobertura_movel"):
        from nucleo3d import cobertura_movel as CM
        try:
            CM.aplicar(doc, par, pj.get("cobertura_movel_vista") or "aberta")
            # a planta acompanha: as linhas das tesouras na posição da situação (o CAD recarrega pelo "desenho")
            from nucleo2d.desenho import Desenho
            des = Desenho.de_dict(g.abrir_desenho(s, nome))
            if CM.na_planta(des, doc):
                g.salvar_desenho(s, nome, des.dict())
                desenho_novo = des.dict()
        except ErroDeDados as e:
            avisos = list(avisos) + ["cobertura retrátil: %s" % e]
    g.salvar_modelo(s, doc.dict(), marco=False)
    return {"ok": True, "mudou": True, "saiu": len(antes), "entrou": len(novo.entidades), "avisos": avisos,
            "estatisticas": doc.estatisticas(), **({"desenho": desenho_novo} if desenho_novo else {})}
