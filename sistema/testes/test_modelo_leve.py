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


def test_modelo_vazio_nao_mostra_o_anterior(tmp_path):
    """O modelo ficou sem peças (a planta da Estrutura apagada, 06/10): o 3D leve fica "sem modelo" (vazio) em vez de dar
    erro e o modo ver continuar com a versão anterior; com peça de novo, volta a ficar pronto."""
    pasta = _projeto(tmp_path)
    L.gerar(pasta)
    m = _modelo()
    vazio = dict(m, entidades=[])
    time.sleep(0.01)
    with open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(vazio, f)
    assert L.gerar(pasta) == {}
    assert L.situacao(pasta) == {"situacao": "sem modelo", "vazio": True}
    assert L.pedir(pasta) == {"situacao": "sem modelo", "vazio": True}         # nada da versão anterior
    time.sleep(0.01)
    with open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)
    assert L.pedir(pasta)["situacao"] in ("na fila", "preparando", "atualizando")
    _esperar_pronto(pasta)


def test_o_estado_traz_a_fracao_e_a_etapa_para_a_barra(tmp_path, monkeypatch):
    """usuário, 19/10 (Mercado, modo ver "o modelo mudou: atualizando o 3D"): "conseguimos colocar uma barrinha de
    carregamento quando a estrutura está atualizando o modelo?" — o /estado traz {fracao, etapa}, o que a barra de
    andamento padrão (web/progresso.js) lê"""
    from saida import pacote_celular
    pasta = _projeto(tmp_path)
    vistos = []
    original = pacote_celular.gerar_3d

    def devagar(modelo, progresso=None):
        def prog(k, n):
            progresso(k, n)
            vistos.append(L.situacao(pasta))
        return original(modelo, prog)
    monkeypatch.setattr(pacote_celular, "gerar_3d", devagar)
    L.gerar(pasta)
    meio = [s for s in vistos if s.get("situacao") == "preparando"]
    assert meio and all(isinstance(s.get("fracao"), float) and 0.0 <= s["fracao"] <= 1.0 for s in meio)
    assert all("montando as peças" in s.get("etapa", "") for s in meio)
    assert L.situacao(pasta)["situacao"] == "pronto"


def _projeto_cobertura(raiz, nome="cobertura"):
    """a cobertura retrátil pequena de test_cobertura_movel, gravada aberta"""
    from nucleo3d import cobertura_movel as CM
    from test_cobertura_movel import PAR, _modelo as _modelo_cobertura
    doc = _modelo_cobertura()
    CM.aplicar(doc, PAR, "aberta")
    p = raiz / nome
    p.mkdir(parents=True)
    (p / "projeto.json").write_text(json.dumps({"nome": nome, "analise_parametros": dict(PAR, cobertura_movel=True),
                                                "cobertura_movel_vista": "aberta"}), encoding="utf-8")
    (p / "modelo.json").write_text(json.dumps(doc.dict()), encoding="utf-8")
    return str(p)


def _esperar_situacao(pasta, sit, prazo=60):
    t0 = time.time()
    while time.time() - t0 < prazo:
        s = L.pedir_situacao(pasta, sit, iniciar=False)
        if s["situacao"] == "pronto":
            return L.pedir_situacao(pasta, sit)
        assert s["situacao"] != "erro", s
        time.sleep(0.1)
    raise AssertionError("a situação não ficou pronta")


def _ys_das_pecas(caminho_pecas):
    return sorted(round(f["x"][1]) for f in json.load(open(caminho_pecas, encoding="utf-8"))["pecas"])


def test_cobertura_retratil_a_outra_situacao_so_para_ver(tmp_path):
    """usuário, Kaefer, 20/10: "a visualização da cobertura aberta e retraída está bem demorada de mudar na versão do
    computador, preciso clicar duas vezes… é apenas para demonstração". O botão do modo ver gravava o modelo inteiro na
    situação e o 3D leve era refeito. Agora a outra situação sai pronta junto com o 3D leve (numa cópia do modelo) e o
    modelo gravado não muda."""
    pasta = _projeto_cobertura(tmp_path)
    caminho = os.path.join(pasta, "modelo.json")
    antes = open(caminho, encoding="utf-8").read()
    L.gerar(pasta)
    assert L.situacao_gravada(pasta) == "aberta"
    aberta = L.pedir_situacao(pasta, "aberta")
    assert aberta["situacao"] == "pronto" and aberta["mcel"] == L.arquivos(pasta)["mcel"]     # a gravada é o 3D de sempre
    retraida = _esperar_situacao(pasta, "retraida")                    # feita sozinha, em segundo plano, depois do principal
    assert retraida["mcel"] != aberta["mcel"] and open(retraida["mcel"], "rb").read(4) == b"MCEL"
    assert _ys_das_pecas(retraida["pecas"]) != _ys_das_pecas(aberta["pecas"])               # as tesouras mudaram de lugar
    assert open(caminho, encoding="utf-8").read() == antes                                  # e o modelo gravado não
    assert retraida["versao"] != aberta["versao"]


def test_cobertura_retratil_pedida_antes_de_pronta_e_obra_comum(tmp_path):
    """o 3D leve feito antes (sem a situação guardada) descobre a gravada pelo modelo; pedida e ainda por fazer, a
    situação vem com o andamento para a barra; numa obra comum, a situação pedida é o 3D de sempre"""
    pasta = _projeto_cobertura(tmp_path)
    L.gerar(pasta)
    c = os.path.join(str(tmp_path), ".3d-leve", "cobertura")
    os.remove(os.path.join(c, "cobertura.json"))
    _esperar_situacao(pasta, "retraida")
    for n in ("modelo3d-retraida.mcel", "pecas-retraida.json", "fonte-retraida.txt"):
        os.remove(os.path.join(c, n))
    assert L.situacao_gravada(pasta) == "aberta"
    r = L.pedir_situacao(pasta, "retraida")
    assert r["situacao"] in ("na fila", "preparando") and "fracao" in r
    _esperar_situacao(pasta, "retraida")
    comum = _projeto(tmp_path)
    L.gerar(comum)
    assert L.pedir_situacao(comum, "retraida")["mcel"] == L.arquivos(comum)["mcel"]
