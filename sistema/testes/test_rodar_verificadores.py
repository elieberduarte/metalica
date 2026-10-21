# -*- coding: utf-8 -*-
"""O executor dos verificadores (testes/rodar_verificadores.py) na conferência antes de publicar."""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rodar_verificadores as rv  # noqa: E402


def _vivo(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


@pytest.mark.skipif(os.name != "nt", reason="a árvore de processos pelo taskkill do Windows")
def test_tempo_esgotado_leva_a_arvore_junto(tmp_path, monkeypatch):
    """20/10, conferência da 0.9.0: o verif_camera_modelos passava dos 900 s, o executor matava só ele e os dois app.py que
    ele tinha subido ficavam vivos, presos à pasta da cópia limpa — a rodada seguinte da noite parou em "já existe"."""
    arq_pid = tmp_path / "neto.pid"
    verif = tmp_path / "verif_lento.py"
    verif.write_text(
        "import subprocess, sys, time\n"
        "q = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "open(%r, 'w').write(str(q.pid))\n"
        "time.sleep(120)\n" % str(arq_pid), encoding="utf-8")
    monkeypatch.setattr(rv, "LIMITES", {"verif_lento": 3})
    t0 = time.time()
    ok, _dt, falhas, _oks = rv.rodar(str(verif))
    assert not ok and time.time() - t0 < 60
    assert any("tempo esgotado" in f for f in falhas), falhas
    neto = int(arq_pid.read_text())
    for _ in range(20):
        if not _vivo(neto):
            break
        time.sleep(0.25)
    assert not _vivo(neto), "o processo que o verificador subiu ficou vivo"
