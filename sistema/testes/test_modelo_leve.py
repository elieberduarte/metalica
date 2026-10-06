# -*- coding: utf-8 -*-
"""O 3D leve do modo "ver" (saida/modelo_leve.py): preparado quando pedido, refeito depois de o modelo ser
gravado (só de quem já foi visto), guardado fora da pasta do usuário num teste."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import modelo_leve as L                      # noqa: E402
from test_pacote_celular import _modelo                 # noqa: E402


def _projeto(raiz, nome="obra"):
    p = raiz / nome
    p.mkdir(parents=True)
    (p / "projeto.json").write_text(json.dumps({"nome": nome}), encoding="utf-8")
    (p / "modelo.json").write_text(json.dumps(_modelo()), encoding="utf-8")
    return str(p)


def _esperar_pronto(pasta, prazo=60):
    t0 = time.time()
    while time.time() - t0 < prazo:
        s = L.situacao(pasta)
        if s["situacao"] == "pronto":
            return s
        assert s["situacao"] != "erro", s
        time.sleep(0.1)
    raise AssertionError("não ficou pronto")


def test_prepara_quando_pedido_e_guarda_na_pasta_temporaria(tmp_path):
    pasta = _projeto(tmp_path)
    assert L.pasta_de_trabalho(str(tmp_path)) == os.path.join(str(tmp_path), ".3d-leve")       # teste: nada na pasta do usuário
    r = L.pedir(pasta)
    assert r["situacao"] in ("na fila", "preparando", "pronto")
    s = _esperar_pronto(pasta)
    a = L.arquivos(pasta)
    assert open(a["mcel"], "rb").read(4) == b"MCEL"
    assert len(json.load(open(a["pecas"], encoding="utf-8"))["pecas"]) == 67
    assert L.pedir(pasta)["situacao"] == "pronto" and s["versao"] == a["versao"]


def test_modelo_mudou_fica_velho_e_gravar_refaz(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "ESPERA_DEPOIS_DE_GRAVAR", 0.05)
    pasta = _projeto(tmp_path)
    L.gerar(pasta)
    v1 = L.arquivos(pasta)["versao"]
    m = _modelo()
    m["entidades"] = m["entidades"][:10]
    time.sleep(0.01)
    with open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)
    assert L.arquivos(pasta) is None                         # velho: quem pede recebe "preparando"
    L.gravado(pasta)                                         # o que o projetos.py chama depois de gravar
    s = _esperar_pronto(pasta)
    assert s["versao"] != v1
    assert len(json.load(open(L.arquivos(pasta)["pecas"], encoding="utf-8"))["pecas"]) == 10


def test_projeto_nunca_visto_nao_gasta(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "ESPERA_DEPOIS_DE_GRAVAR", 0.05)
    pasta = _projeto(tmp_path)
    L.gravado(pasta)
    time.sleep(0.4)
    assert not os.path.isdir(os.path.join(str(tmp_path), ".3d-leve", "obra"))


def test_gravar_pelo_gerente_refaz(tmp_path, monkeypatch):
    from projetos import Projetos
    monkeypatch.setattr(L, "ESPERA_DEPOIS_DE_GRAVAR", 0.05)
    pasta = _projeto(tmp_path)
    L.gerar(pasta)
    v1 = L.arquivos(pasta)["versao"]
    m = _modelo()
    m["entidades"] = m["entidades"][:20]
    time.sleep(0.01)
    Projetos(str(tmp_path)).salvar_modelo("obra", m)
    assert _esperar_pronto(pasta)["versao"] != v1


def test_sem_modelo(tmp_path):
    p = tmp_path / "vazio"
    p.mkdir()
    (p / "projeto.json").write_text("{}", encoding="utf-8")
    assert L.pedir(str(p))["situacao"] == "sem modelo"


def test_gravar_sem_mudar_nao_refaz_e_o_velho_abre_na_hora(tmp_path):
    """O editor grava o modelo igual (só a data muda): continua pronto. Mudou de verdade: o anterior sai na
    hora ("atualizando") e o novo é feito em segundo plano."""
    pasta = _projeto(tmp_path)
    L.gerar(pasta)
    caminho = os.path.join(pasta, "modelo.json")
    texto = open(caminho, encoding="utf-8").read()
    time.sleep(0.02)
    open(caminho, "w", encoding="utf-8").write(texto)            # mesma coisa, data nova
    assert L.arquivos(pasta) is not None
    m = _modelo()
    m["entidades"] = m["entidades"][:5]
    open(caminho, "w", encoding="utf-8").write(json.dumps(m))
    r = L.pedir(pasta)
    with open(r["mcel"], "rb") as f:
        assert r["situacao"] == "atualizando" and f.read(4) == b"MCEL"
    s = _esperar_pronto(pasta)
    assert s["versao"] != r["versao"]
