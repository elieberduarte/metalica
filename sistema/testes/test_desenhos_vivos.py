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


def test_avisos_de_um_detalhamento_feito_com_outro_3d(tmp_path):
    """Posto, 27/10: o aviso das 79 terças fora do passo da máquina era do Detalhar de 24/10; a remontagem de 26/10 trocou
    todos os ids e o "Ver no 3D" procurava peças que não existem mais. O estado diz de quando é e se o 3D mudou depois."""
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    g.desenhos = [{"nome": "detalhamento-tercas"}]
    dv.configurar(gerente=lambda: g)
    dv.gravar_carimbo("p", {"detalhamento-tercas": "g1"}, extra={"fora_da_maquina": ["T.C.9: furos a 40 mm"],
                      "fora_da_maquina_pecas": [{"nome": "T.C.9", "marca": "P211 / P670", "ids": ["e1"], "texto": "T.C.9"}]})
    e = dv.estado("p", conferir=False)
    assert e["fora_da_maquina"] and e["pendencias_de"] and e["pendencias_de_outro_3d"] is False
    # remontado (e a atualização cancelada): os avisos ficam, mas são de outro 3D
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    e = dv.estado("p", conferir=False)
    assert e["fora_da_maquina"] and e["pendencias_de_outro_3d"] is True


def _pid_morto():
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _marca_de_quem_morreu(tmp_path, pid):
    arq = tmp_path / "p" / "detalhamento" / "carimbo.json"
    c = json.loads(arq.read_text(encoding="utf-8"))
    c["em_andamento"] = {"desde": 1761550800.0, "motivo": "o modelo 3D mudou", "pid": pid, "pid_inicio": 1.0}
    arq.write_text(json.dumps(c), encoding="utf-8")


def test_reinicio_no_meio_e_interrompida_nao_concluida(tmp_path):
    """Posto, 27/10: o dev reiniciou no meio dos 35 min do Detalhar em segundo plano; a thread morreu, o estado (só em
    memória) sumiu e a tela leu "não está atualizando" = concluído; cada abertura recomeçava do zero sem dizer por quê.
    Agora a marca de início fica no carimbo até o fim: sobrando, é "interrompida"; recomeça uma vez dizendo o porquê, e
    na segunda seguida espera o "Atualizar agora" (ou uma mudança da obra)."""
    import threading
    import time as _t
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    dv.configurar(gerente=lambda: g)
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    e = dv.estado("p", conferir=False)
    assert e["interrompida"] is None and dv.por_que_velho("p") == ""
    # o processo que atualizava morreu no meio
    _marca_de_quem_morreu(tmp_path, _pid_morto())
    e = dv.estado("p", conferir=False)
    assert not e.get("atualizando") and e["interrompida"] and e["interrompida"]["vezes"] == 1 and not e["interrompida"]["parada"]
    assert dv.por_que_velho("p").startswith("recomeçando: a de ") and "interrompida" in dv.por_que_velho("p")
    # de novo: parada, não recomeça sozinha
    _marca_de_quem_morreu(tmp_path, _pid_morto())
    e = dv.estado("p", conferir=False)
    assert e["interrompida"]["vezes"] == 2 and e["interrompida"]["parada"] and dv.por_que_velho("p") == ""
    # a obra mudou depois de parada: atualiza como sempre
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    assert dv.por_que_velho("p").startswith("recomeçando")
    # a marca de um programa vivo (outro processo na mesma pasta) não é interrompida
    import subprocess
    vivo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _t.sleep(0.3)
        from projetos import _inicio_processo
        arq = tmp_path / "p" / "detalhamento" / "carimbo.json"
        c = json.loads(arq.read_text(encoding="utf-8"))
        c["em_andamento"] = {"desde": _t.time(), "motivo": "x", "pid": vivo.pid, "pid_inicio": _inicio_processo(vivo.pid)}
        arq.write_text(json.dumps(c), encoding="utf-8")
        assert dv.estado("p", conferir=False)["interrompida"]["vezes"] == 2
        assert "em_andamento" in json.loads(arq.read_text(encoding="utf-8"))
    finally:
        vivo.kill(); vivo.wait()
    # a marca deste mesmo processo (a atualização acabando: o estado já diz que não) não é interrompida; a de um processo
    # novo com o número deste (o programa reiniciado ganhou o mesmo PID), é
    from projetos import _inicio_processo as _ini
    arq = tmp_path / "p" / "detalhamento" / "carimbo.json"
    c = json.loads(arq.read_text(encoding="utf-8"))
    c["em_andamento"] = {"desde": _t.time(), "motivo": "x", "pid": os.getpid(), "pid_inicio": _ini(os.getpid())}
    arq.write_text(json.dumps(c), encoding="utf-8")
    assert dv.estado("p", conferir=False)["interrompida"]["vezes"] == 2
    c["em_andamento"]["pid_inicio"] = _ini(os.getpid()) - 3600
    arq.write_text(json.dumps(c), encoding="utf-8")
    assert dv.estado("p", conferir=False)["interrompida"]["vezes"] == 3
    # a atualização deste processo: a marca fica no disco enquanto roda e sai no fim; terminada, a interrompida some
    _marca_de_quem_morreu(tmp_path, _pid_morto())
    dv.estado("p", conferir=False)
    durante = {}
    pode = threading.Event()

    def detalhar(s):
        durante.update(json.loads((tmp_path / "p" / "detalhamento" / "carimbo.json").read_text(encoding="utf-8")))
        pode.wait(10)
        dv.gravar_carimbo(s, {"detalhamento-tesouras": "g2"})
    dv.configurar(gerente=lambda: g, detalhar=detalhar, pranchas=None, resumos=None)
    assert dv.atualizar("p", "pedido na tela")
    _t.sleep(0.5)
    assert dv.estado("p", conferir=False)["interrompida"] is None          # rodando aqui: não é interrompida
    pode.set()
    for _ in range(100):
        if not dv.estado("p", conferir=False).get("atualizando"):
            break
        _t.sleep(0.05)
    c = json.loads((tmp_path / "p" / "detalhamento" / "carimbo.json").read_text(encoding="utf-8"))
    assert durante["em_andamento"]["pid"] == os.getpid() and durante["em_andamento"]["motivo"] == "pedido na tela"
    assert "em_andamento" not in c and "interrompida" not in c
    assert dv.estado("p", conferir=False)["interrompida"] is None and dv.por_que_velho("p") == ""


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


def test_programa_novo_nao_refaz_os_desenhos(tmp_path, monkeypatch):
    """Vicente, 21/10 (usuário: "todas as vezes que abro o projeto ele está em atualização… o que mexemos foi em outra
    estrutura… essa está em teoria fechada"): o programa mudou (no dev, qualquer arquivo; no instalado, a versão) e nada
    da obra mudou — os desenhos ficam como estão, o estado diz programa_novo; o 3D gravado refaz como sempre."""
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    pedidos = []
    dv.configurar(gerente=lambda: g, detalhar=lambda s: pedidos.append(s))
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    monkeypatch.setattr(dv, "AVISAR_PROGRAMA_NOVO", True)        # o instalado (no dev o aviso não aparece)
    monkeypatch.setattr(dv, "_impressao", "programa-de-ontem")
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    monkeypatch.setattr(dv, "_impressao", "programa-de-hoje")
    assert dv.por_que_velho("p") == ""
    assert dv.programa_novo("p") is True
    monkeypatch.setattr(dv, "atualizar", lambda s, motivo="", so_pranchas=False: pedidos.append(motivo) or True)
    e = dv.estado("p")
    assert e["programa_novo"] is True and not e.get("atualizando") and pedidos == []
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    assert dv.por_que_velho("p") == "o modelo 3D mudou"
    dv.estado("p")
    assert pedidos == ["o modelo 3D mudou"]
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g2"})        # detalhado de novo: com o programa de hoje
    assert dv.programa_novo("p") is False


def test_cancelar_a_atualizacao(tmp_path):
    """Usuário, 21/10: "cliquei para atualizar sem querer, tem como criar um botão para cancelar". A atualização para no
    próximo passo do cálculo, sem gravar desenho; não recomeça sozinha no mesmo estado da obra; o 3D mudado de novo
    atualiza como sempre."""
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    gravados = []

    def detalhar(s):
        dv.cancelar(s)                    # o usuário clica no meio do cálculo
        dv.conferir_cancelamento(s)       # o próximo passo do detalhamento
        gravados.append(s)                # não chega aqui
    dv.configurar(gerente=lambda: g, detalhar=detalhar)
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    os.utime(tmp_path / "p" / "modelo.json", (1, 1))
    assert dv.por_que_velho("p") == "o modelo 3D mudou"
    dv._estado["p"] = {"atualizando": True}
    dv._rodar("p", "o modelo 3D mudou", False)
    e = dv.estado("p", conferir=False)
    assert gravados == [] and e["atualizando"] is False and e["cancelada"] is True and not e.get("erro")
    assert dv.por_que_velho("p") == ""                        # não recomeça na próxima pergunta da tela
    assert dv.cancelar("p") is False                          # nada rodando: nada a cancelar
    os.utime(tmp_path / "p" / "modelo.json", (2, 2))
    assert dv.por_que_velho("p") == "o modelo 3D mudou"       # mudou de novo: atualiza
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g2"})
    assert dv.estado("p", conferir=False)["cancelada"] is False


def test_no_dev_o_programa_novo_nao_avisa(tmp_path, monkeypatch):
    """No desenvolvimento o código muda a cada minuto: o aviso aparecia em toda abertura e o usuário clicou "Atualizar
    agora" sem querer (21/10). Só o instalado avisa, a cada versão."""
    g = _Gerente(str(tmp_path))
    os.makedirs(tmp_path / "p" / "detalhamento")
    (tmp_path / "p" / "modelo.json").write_text("{}", encoding="utf-8")
    dv.configurar(gerente=lambda: g)
    g.desenhos = [{"nome": "detalhamento-tesouras"}]
    monkeypatch.setattr(dv, "_impressao", "programa-de-ontem")
    dv.gravar_carimbo("p", {"detalhamento-tesouras": "g1"})
    monkeypatch.setattr(dv, "_impressao", "programa-de-hoje")
    monkeypatch.setattr(dv, "AVISAR_PROGRAMA_NOVO", False)
    assert dv.programa_novo("p") is False and dv.estado("p", conferir=False)["programa_novo"] is False
