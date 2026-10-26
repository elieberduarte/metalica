# -*- coding: utf-8 -*-
"""O envio à nuvem do celular (celular/nuvem.py) e o PDF das pranchas do pacote.

26/10 (usuário, S25 Ultra: a "Câmera 0,6×" e o "Inteira" não apareciam no celular): desde 21/10 o envio parava no
pranchas.pdf de 0 bytes de uma obra (ME Sooro, uma geração interrompida em 22/10) — o arquivo vazio, mais novo que o
desenho, nunca era refeito, e o erro dele derrubava o envio inteiro: nenhuma obra e nenhuma tela nova subiam.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celular import nuvem as N                          # noqa: E402
from saida import pacote_celular as P                   # noqa: E402


class _CelFalso:
    """O servidor do celular só no que o envio usa: duas obras, a "ruim" com o pacote que não se prepara."""

    def __init__(self, pasta):
        self.pacotes = os.path.join(str(pasta), "pacotes")
        self.conf = {"ligada": True}
        for slug in ("boa", "ruim"):
            os.makedirs(os.path.join(self.pacotes, slug), exist_ok=True)
            with open(os.path.join(self.pacotes, slug, "modelo3d.mcel"), "wb") as f:
                f.write(slug.encode())

    def projetos(self):
        return [{"slug": "boa", "nome": "Obra boa"}, {"slug": "ruim", "nome": "ME Sooro"}]

    def gerar_se_velho(self, slug):
        if slug == "ruim":
            raise RuntimeError("Cannot open empty file: pranchas.pdf")
        return False

    def _manifesto(self, slug):
        return {"gerado": "2026-10-22T16:32", "bytes": 4, "numeros": {"pecas": 1},
                "arquivos": [{"nome": "modelo3d.mcel", "sha1": slug * 10, "bytes": 4}]}

    def _assinatura(self, slug):
        return slug

    def _ler(self, nome, padrao):
        return dict(self.conf) if nome == "nuvem.json" else padrao

    def _gravar(self, nome, dados):
        self.conf = dict(dados)


def _nuvem(tmp_path, ja_na_nuvem=()):
    cel = _CelFalso(tmp_path)
    nv = N.Nuvem(cel, servico="https://nuvem.teste", token=lambda: "MTL-TESTE")
    pedidos = []

    def pedir(metodo, rota, corpo=None, tipo="application/json", timeout=60.0):
        pedidos.append((metodo, rota, corpo))
        if rota == "/pc/estado":
            return {"obras": list(ja_na_nuvem)}
        if rota == "/pc/faltam":
            return {"faltam": []}
        return {}
    nv._pedir = pedir
    return nv, cel, pedidos


def test_a_obra_que_falha_nao_segura_as_telas_nem_as_outras(tmp_path):
    nv, cel, pedidos = _nuvem(tmp_path)
    r = nv.enviar()                                        # não levanta
    rotas = [(m, rt) for m, rt, _ in pedidos]
    assert ("PUT", "/pc/telas") in rotas and ("PUT", "/pc/obra/boa") in rotas and ("PUT", "/pc/obra/ruim") not in rotas
    assert rotas.index(("PUT", "/pc/telas")) < rotas.index(("PUT", "/pc/obra/boa"))     # as telas primeiro
    indice = [c for m, rt, c in pedidos if rt == "/pc/indice"][0]
    assert [p["slug"] for p in indice["projetos"]] == ["boa"]
    assert r["falhas"] and "ME Sooro" in r["falhas"][0] and "pranchas.pdf" in r["falhas"][0]
    assert "ME Sooro" in nv.estado()["erro"] and cel.conf.get("enviado")                 # o aviso, e o envio contou


def test_a_obra_que_falha_continua_na_nuvem_com_a_versao_de_antes(tmp_path):
    nv, cel, pedidos = _nuvem(tmp_path, ja_na_nuvem=("boa", "ruim"))
    cel.conf["obras"] = {"ruim": "versao-de-antes"}
    nv.enviar()
    rotas = [(m, rt) for m, rt, _ in pedidos]
    assert ("DELETE", "/pc/obra/ruim") not in rotas
    indice = [c for m, rt, c in pedidos if rt == "/pc/indice"][0]
    ruim = [p for p in indice["projetos"] if p["slug"] == "ruim"]
    assert ruim and ruim[0]["atual"] is False and ruim[0]["gerado"]
    assert cel.conf["obras"]["ruim"] == "versao-de-antes"


def test_sem_conexao_o_envio_inteiro_para(tmp_path):
    nv, cel, pedidos = _nuvem(tmp_path)

    def sem_rede(*a, **k):
        raise N.ErroNuvem("sem conexão com a nuvem")
    nv._pedir = sem_rede
    with pytest.raises(N.ErroNuvem):
        nv.enviar()
    assert "sem conexão" in nv.estado()["erro"]


def test_pranchas_pdf_vazio_e_refeito(tmp_path, monkeypatch):
    """O pranchas.pdf de 0 bytes mais novo que o desenho (a geração interrompida) é refeito, e o novo só entra pronto."""
    import pymupdf
    from nucleo2d import desenho as D, pranchas as PR
    proj = tmp_path / "obra"
    (proj / "desenhos-2d").mkdir(parents=True)
    (proj / "desenhos-2d" / "pranchas.desenho.json").write_text(
        json.dumps({"metadados": {"pranchas": [{"formato": "A3", "numero": 1, "titulo": "Planta"}]}}), encoding="utf-8")
    destino = tmp_path / "pacote"
    destino.mkdir()
    (destino / "pranchas.pdf").write_bytes(b"")             # vazio e mais novo que o desenho
    feitos = []

    def gerar(desenhos, caminho, **k):
        feitos.append(caminho)
        doc = pymupdf.open()
        doc.new_page(width=420, height=297)
        doc.save(caminho)
        return caminho
    monkeypatch.setattr(PR, "pdf_dos_desenhos", gerar)
    monkeypatch.setattr(D.Desenho, "de_dict", staticmethod(lambda d: d))
    folhas = P._pranchas(str(proj), str(destino))
    assert feitos and not feitos[0].endswith("pranchas.pdf")   # escrito à parte e trocado no fim
    assert len(folhas) == 1 and (destino / "pranchas.pdf").stat().st_size > 0
    assert not (destino / "pranchas.pdf.tmp.pdf").exists()
