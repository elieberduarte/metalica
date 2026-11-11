# -*- coding: utf-8 -*-
"""A cópia dos dados para o OneDrive (copia_onedrive.py — DESEMPENHO N.3, 11/11/2026).

Usuário, 11/11: "Preciso que continue salvando os arquivos no OneDrive, tem arquivo que está sendo salvo só no disco C."
A cópia da noite (03:30) não rodou em 10/11 nem em 11/11. Agora, com o programa aberto: a cada hora, os documentos logo
depois de gravados e ao fechar; só acrescenta; sem historico/.3d-leve; o selo da tela inicial diz quando foi ou que falhou."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import pytest                                                    # noqa: E402
import copia_onedrive as C                                        # noqa: E402


def _escrever(caminho, texto="x"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


@pytest.fixture()
def pastas(tmp_path):
    dados, destino = str(tmp_path / "dados"), str(tmp_path / "OneDrive" / "Backup Metálica" / "dados")
    os.makedirs(dados)
    p = os.path.join(dados, "cobertura-filipn-goioêre")
    _escrever(os.path.join(p, "modelo.json"), "{}")
    _escrever(os.path.join(p, "05-ENVIADOS", "Proposta R00.pdf"), "pdf")
    _escrever(os.path.join(p, "historico", "modelo-20261111.json.gz"), "pesado")
    _escrever(os.path.join(p, ".3d-leve", "malha.bin"), "pesado")
    C.ligar(dados, True, destino)
    return dados, destino


def test_desligada_nao_aparece_e_nao_copia(tmp_path):
    dados = str(tmp_path)
    assert C.situacao(dados)["situacao"] == "desligada"
    _escrever(os.path.join(dados, "obra", "05-ENVIADOS", "a.pdf"))
    assert C.copiar_documentos(dados) == 0


def test_a_copia_completa_leva_tudo_menos_o_pesado_e_so_acrescenta(pastas):
    dados, destino = pastas
    s = C.copiar(dados, "hora")
    assert s["situacao"] == "ok", s
    obra = os.path.join(destino, "cobertura-filipn-goioêre")
    assert os.path.exists(os.path.join(obra, "modelo.json"))
    assert os.path.exists(os.path.join(obra, "05-ENVIADOS", "Proposta R00.pdf"))
    assert not os.path.exists(os.path.join(obra, "historico"))
    assert not os.path.exists(os.path.join(obra, ".3d-leve"))
    assert not os.path.exists(os.path.join(destino, C.ESTADO)) and not os.path.exists(os.path.join(destino, C.TRAVA))
    with open(os.path.join(dados, C.REGISTRO), encoding="utf-8") as f:
        assert "hora ok" in f.read()
    # apagado no C: continua no OneDrive (quem limpa é a cópia da noite)
    os.remove(os.path.join(dados, "cobertura-filipn-goioêre", "05-ENVIADOS", "Proposta R00.pdf"))
    assert C.copiar(dados, "hora")["situacao"] == "ok"
    assert os.path.exists(os.path.join(obra, "05-ENVIADOS", "Proposta R00.pdf"))


def test_os_documentos_vao_logo_depois_de_gravados(pastas):
    dados, destino = pastas
    C.copiar(dados, "hora")
    time.sleep(0.05)
    p = os.path.join(dados, "cobertura-filipn-goioêre")
    _escrever(os.path.join(p, "detalhamento", "RESUMO rev3.xlsx"), "novo")
    _escrever(os.path.join(p, "03-PROPOSTA", "proposta.docx"), "novo")
    _escrever(os.path.join(p, "01-RECEBIDOS", "planta do cliente.dwg"), "novo")   # nas pastas 01–05 vai qualquer tipo
    _escrever(os.path.join(p, "modelo.json"), '{"novo": 1}')                       # o modelo espera a hora
    _escrever(os.path.join(p, "03-PROPOSTA", "~$proposta.docx"), "trava do Word")
    agora = time.time()
    assert C.copiar_documentos(dados, agora=agora) == 0                            # ainda "gravando" (< ESTAVEL)
    n = C.copiar_documentos(dados, agora=agora + C.ESTAVEL + 1)
    obra = os.path.join(destino, "cobertura-filipn-goioêre")
    assert n == 3
    assert os.path.exists(os.path.join(obra, "detalhamento", "RESUMO rev3.xlsx"))
    assert os.path.exists(os.path.join(obra, "03-PROPOSTA", "proposta.docx"))
    assert os.path.exists(os.path.join(obra, "01-RECEBIDOS", "planta do cliente.dwg"))
    assert not os.path.exists(os.path.join(obra, "03-PROPOSTA", "~$proposta.docx"))
    with open(os.path.join(obra, "modelo.json"), encoding="utf-8") as f:
        assert f.read() == "{}"
    assert C.copiar_documentos(dados, agora=agora + C.ESTAVEL + 2) == 0             # já foram: não copia de novo


def test_a_falha_aparece_no_selo_e_no_registro(pastas, tmp_path):
    dados, _ = pastas
    arquivo = tmp_path / "um-arquivo"
    arquivo.write_text("x")
    C.ligar(dados, True, str(arquivo / "dados"))                                   # destino impossível
    s = C.copiar(dados, "hora")
    assert s["situacao"] == "falhou" and s["falha"], s
    assert "erro" not in s                                                         # o api() da tela não a toma por erro
    with open(os.path.join(dados, C.REGISTRO), encoding="utf-8") as f:
        assert "FALHOU" in f.read()


def test_atrasada_depois_de_duas_horas(pastas):
    dados, _ = pastas
    C.copiar(dados, "hora")
    assert C.situacao(dados, agora=time.time() + C.ATRASADA + 1)["situacao"] == "atrasada"


def test_dois_programas_nao_copiam_ao_mesmo_tempo(pastas):
    dados, destino = pastas
    outro = subprocess.Popen([sys.executable, "-c", textwrap.dedent('''
        import sys, time
        sys.path.insert(0, %r)
        import copia_onedrive as C
        t = C._trancar(%r)
        print("COPIANDO" if t else "SEM TRAVA", flush=True)
        time.sleep(30)
    ''') % (RAIZ, dados)], stdout=subprocess.PIPE, text=True)
    try:
        assert outro.stdout.readline().strip() == "COPIANDO"
        C.copiar(dados, "hora")
        assert not os.path.exists(destino)                                         # pulou: o outro está copiando
    finally:
        outro.kill(); outro.wait()
    assert C.copiar(dados, "hora")["situacao"] == "ok"


def test_o_selo_pela_rota(pastas, monkeypatch):
    import app
    dados, destino = pastas
    monkeypatch.setattr(app, "PROJETOS", dados)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        with urllib.request.urlopen(base + "/api/copia-onedrive", timeout=10) as r:
            s = json.load(r)
        assert s["ligada"] and s["situacao"] == "atrasada" and s["ha_s"] is None   # nenhuma cópia ainda
        req = urllib.request.Request(base + "/api/copia-onedrive/agora", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            json.load(r)
        for _ in range(100):
            if C.situacao(dados)["situacao"] == "ok":
                break
            time.sleep(0.1)
        assert C.situacao(dados)["situacao"] == "ok"
        assert os.path.exists(os.path.join(destino, "cobertura-filipn-goioêre", "modelo.json"))
    finally:
        srv.shutdown(); srv.server_close()


def test_o_fio_copia_na_hora_e_os_documentos_entre_uma_e_outra(pastas, monkeypatch):
    dados, destino = pastas
    voltas = []
    pronto = threading.Event()

    def dormir(s):
        voltas.append(s)
        if len(voltas) == 2:                                                       # depois da 1ª volta: um documento novo
            _escrever(os.path.join(dados, "cobertura-filipn-goioêre", "05-ENVIADOS", "Lista rev1.pdf"), "novo")
        if len(voltas) >= 3:
            pronto.set()
            return True
        return False
    monkeypatch.setattr(C, "_fio", {"t": None, "parar": None})
    monkeypatch.setattr(C, "ESTAVEL", 0.0)
    t = C.iniciar(dados, dormir=dormir)
    assert pronto.wait(60)
    t.join(10)
    obra = os.path.join(destino, "cobertura-filipn-goioêre")
    assert os.path.exists(os.path.join(obra, "modelo.json"))                       # a completa (nunca tinha copiado)
    assert os.path.exists(os.path.join(obra, "05-ENVIADOS", "Lista rev1.pdf"))     # e o documento, na volta seguinte
