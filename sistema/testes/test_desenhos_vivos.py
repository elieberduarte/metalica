# -*- coding: utf-8 -*-
"""O carimbo do detalhamento (desenhos_vivos.py, 28/09): quando os desenhos ficam velhos."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import desenhos_vivos as dv  # noqa: E402


class _Gerente:
    def __init__(self, raiz):
        self.raiz = raiz
        self.eixos = {"x": [0, 6000]}
        self.desenhos = []

    def _existente(self, s):
        return os.path.join(self.raiz, s)

    def ler(self, s):
        return {"eixos": self.eixos}

    def caminho_modelo(self, s):
        return os.path.join(self.raiz, s, "modelo.json")

    def listar_desenhos(self, s, contar=True):
        return self.desenhos


def test_quando_o_detalhamento_fica_velho(tmp_path):
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    dv.configurar(gerente=lambda: g)
    assert dv.por_que_velho("p") == ""                                # sem detalhamento: o primeiro é pelo botão
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    assert "antes" in dv.por_que_velho("p")                           # sem carimbo
    c = dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    assert dv.por_que_velho("p") == "" and c["desenhos"] == {"detalhamento-tesouras": "g1"}
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    assert dv.por_que_velho("p") == "o modelo 3D mudou"
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g2"})
    g.eixos = {"x": [0, 7000]}
    assert dv.por_que_velho("p") == "os eixos mudaram"
    # a atualização parcial só registra as gerações: o carimbo (o que foi usado) continua o de antes
    dv.gravar_carimbo("p", {"detalhamento-terças": "g3"}, completo=False)
    assert dv.por_que_velho("p") == "os eixos mudaram"
    dv.registrar_desenho("p", "pranchas", "g4")
    d = json.loads((tmp_path / "p" / "detalhamento" / "carimbo.json").read_text(encoding="utf-8"))["desenhos"]
    assert d == {"detalhamento-tesouras": "g2", "detalhamento-terças": "g3", "pranchas": "g4"}


def test_primeiro_detalhamento_parcial_fica_carimbado(tmp_path):
    """o detalhar grava a geração de cada desenho antes do carimbo: o primeiro parcial (só chaparias e terças) não
    pode ficar sem o código — senão o CAD acha o detalhamento velho e refaz tudo na hora (conferência de 03/10)"""
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    dv.configurar(gerente=lambda: g)
    g.desenhos = [{"nome": "detalhamento-chaparias"}]
    dv.registrar_desenho("p", "detalhamento-chaparias", "g1")
    dv.gravar_carimbo("p", {"detalhamento-chaparias": "g1"}, completo=False, extra={"pendente_3d": {}})
    assert dv.por_que_velho("p") == ""


def test_cores_escolhidas_no_cad_valem_no_projeto(tmp_path):
    """a cor mudada no CAD (um perfil, pedido do usuário, 28/09) fica no projeto: vale nos desenhos gerados
    depois e nos já gravados, menos o aberto no CAD; o mesmo perfil em outra função pega a mesma cor"""
    import time as _t
    from nucleo2d.desenho import Camada2D, Desenho

    class _G(_Gerente):
        def __init__(self, raiz):
            super().__init__(raiz)
            self.gravados = {"pranchas": {"camadas": {"DIAGONAIS U92X30X#13": {"cor": "#e67e22"}, "TEXTO": {"cor": "#000000"}}},
                             "tesouras": {"camadas": {"DIAGONAIS U92X30X#13": {"cor": "#e67e22"}}}}
            self.desenhos = [{"nome": n} for n in self.gravados]

        def _caminho_desenho(self, s, nome):
            return os.path.join(self.raiz, s, nome + ".desenho.json")

        def abrir_desenho(self, s, nome):
            return json.loads(json.dumps(self.gravados[nome]))

        def salvar_desenho(self, s, nome, d):
            self.gravados[nome] = d

    g = _G(str(tmp_path))
    os.makedirs(tmp_path / "p")
    dv.configurar(gerente=lambda: g)
    assert dv.cores_do_usuario("p") == {}
    r = dv.gravar_cores("p", {"DIAGONAIS U92X30X#13": "#123ABC", "X": "vermelho"}, aberto="tesouras")
    assert r["cores"] == {"DIAGONAIS U92X30X#13": "#123abc"}
    for _ in range(50):
        if g.gravados["pranchas"]["camadas"]["DIAGONAIS U92X30X#13"]["cor"] == "#123abc":
            break
        _t.sleep(0.05)
    assert g.gravados["pranchas"]["camadas"]["DIAGONAIS U92X30X#13"]["cor"] == "#123abc"
    assert g.gravados["tesouras"]["camadas"]["DIAGONAIS U92X30X#13"]["cor"] == "#e67e22"     # o aberto: o CAD grava
    d = Desenho(nome="novo")
    d.camadas["MONTANTES U92X30X#13"] = Camada2D("MONTANTES U92X30X#13", "#a855f7")
    d.camadas["BANZOS U100X50X#9"] = Camada2D("BANZOS U100X50X#9", "#2563eb")
    assert dv.aplicar_cores("p", d) == 1
    assert d.camadas["MONTANTES U92X30X#13"].cor == "#123abc" and d.camadas["BANZOS U100X50X#9"].cor == "#2563eb"


def test_editor_aberto_pelo_sinal(monkeypatch):
    """o editor 3D aberto avisa (a cada poucos segundos): enquanto o sinal é recente, a atualização automática não
    grava o modelo por cima dele (02/10)"""
    import time as _t
    assert not dv.editor_aberto("q")
    dv.editor_sinal("q")
    assert dv.editor_aberto("q")
    agora = _t.time()
    monkeypatch.setattr(dv.time, "time", lambda: agora + dv.EDITOR_AUSENTE + 1)
    assert not dv.editor_aberto("q")
