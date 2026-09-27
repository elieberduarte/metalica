# -*- coding: utf-8 -*-
"""Roda todos os verificadores das telas (editor 3D, CAD, lista de materiais…), vários ao
mesmo tempo, e diz quais passaram.

Cada verificador sobe o próprio servidor e um Chrome sem janela, faz o que o usuário faria e
confere o resultado; ele falhou se sai com código diferente de zero ou se imprime uma linha
"FALHA". Os scripts de diagnóstico que pedem argumentos (porta de um servidor já aberto,
arquivo de saída) ficam de fora — eles não se verificam sozinhos.

Em paralelo: a máquina tem vários núcleos e cada verificador usa um (o Chrome desenha o 3D
por software). Rodam N de cada vez (`--paralelo N`; sem dizer, metade dos núcleos, até 6), os
mais demorados primeiro (a duração da última rodada fica em `_duracoes.json`). Dois
verificadores com a mesma porta fixa (`PORTA = 8783`) nunca rodam juntos. O que falhar é
repetido uma vez, sozinho, no fim — corrida de porta ou máquina cheia não é erro do programa;
a segunda tentativa fica marcada no resultado.

Uso:
    python testes/rodar_verificadores.py              todos
    python testes/rodar_verificadores.py furo cantos  só os que têm esses pedaços no nome
    python testes/rodar_verificadores.py --lista      só lista quais rodariam
    python testes/rodar_verificadores.py --serie      um depois do outro (como antes)

Sai com código 1 se algum falhou — é o que se roda antes de publicar uma versão
(testes/antes_de_publicar.py).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTAS = [os.path.join(RAIZ, "testes", "verificadores"), os.path.join(RAIZ, "testes")]
DURACOES = os.path.join(RAIZ, "testes", "verificadores", "_duracoes.json")
#: Tempo máximo de um verificador (s): o da lista de materiais gera os resumos em PDF.
LIMITE = 900
_PEDE_ARGUMENTOS = re.compile(r"len\(sys\.argv\)\s*<\s*[23]")
_PORTA_FIXA = re.compile(r"^(?:PORTA|porta)\s*=\s*(\d{4})\s*$", re.M)


def descobrir(filtros=()):
    """(roda, fora): os verificadores que se verificam sozinhos e os de diagnóstico."""
    roda, fora = [], []
    for pasta in PASTAS:
        for nome in sorted(os.listdir(pasta)):
            if not (nome.startswith("verif_") or nome.startswith("verificar_")) or not nome.endswith(".py"):
                continue
            caminho = os.path.join(pasta, nome)
            with open(caminho, encoding="utf-8", errors="replace") as f:
                texto = f.read()
            if filtros and not any(x in nome for x in filtros):
                continue
            (fora if _PEDE_ARGUMENTOS.search(texto) else roda).append(caminho)
    return roda, fora


def _texto(caminho) -> str:
    with open(caminho, encoding="utf-8", errors="replace") as f:
        return f.read()


def _pede_servidor(caminho) -> bool:
    """Os roteiros antigos (testes/verificar_*.py) esperam um servidor já aberto (--porta)."""
    texto = _texto(caminho)
    return "--porta" in texto and "Servidor fora do ar" in texto


def _porta_fixa(caminho):
    """A porta que o verificador abre para o servidor dele, quando é fixa no código."""
    m = _PORTA_FIXA.search(_texto(caminho))
    return int(m.group(1)) if m else None


def _subir_servidor():
    """Um servidor numa porta livre (nunca a 8765 do programa instalado nem a 8766 do
    desenvolvimento) com uma pasta de dados temporária, os modelos de exemplo copiados:
    (processo, porta, pasta) ou None."""
    pasta = tempfile.mkdtemp(prefix="verificadores_")
    origem = os.path.join(RAIZ, "projetos", "modelos")
    if os.path.isdir(origem):
        shutil.copytree(origem, os.path.join(pasta, "modelos"))
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        porta = so.getsockname()[1]
    if porta in (8765, 8766):
        porta = 8799
    proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", pasta],
                            cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/versao", timeout=1) as r:
                dados = json.loads(r.read().decode("utf-8")).get("dados", "")
                if os.path.normcase(os.path.realpath(dados)) == os.path.normcase(os.path.realpath(pasta)):
                    return proc, porta, pasta
        except Exception:                                                  # noqa: BLE001
            pass
        time.sleep(0.5)
    proc.kill()
    shutil.rmtree(pasta, ignore_errors=True)
    return None


def rodar(caminho):
    """(ok, segundos, falhas, resumo): roda um verificador e lê o resultado."""
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, caminho]
    servidor = None
    if _pede_servidor(caminho):
        # servidor próprio, numa porta livre e com pasta de dados temporária: sem --porta
        # estes roteiros usam a 8765, que é a do Metálica instalado — e gravavam modelos e
        # um projeto de teste na pasta de dados do usuário
        servidor = _subir_servidor()
        if servidor is None:
            return False, time.time() - t0, ["não consegui subir o servidor próprio do verificador"], 0
        cmd += ["--porta", str(servidor[1])]
    try:
        r = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=LIMITE)
        saida = (r.stdout or "") + (r.stderr or "")
        codigo = r.returncode
    except subprocess.TimeoutExpired as e:
        saida = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[tempo esgotado]"
        codigo = -1
    finally:
        if servidor:
            servidor[0].kill()
            shutil.rmtree(servidor[2], ignore_errors=True)
    dt = time.time() - t0
    falhas = [l.strip() for l in saida.splitlines() if re.match(r"\s*FALHA\b", l) and not re.match(r"\s*FALHAS\b", l)]
    total = re.search(r"FALHAS:\s*(\d+)", saida) or re.search(r"(\d+)\s+falha\(s\)", saida)
    n_falhas = int(total.group(1)) if total else len(falhas)
    oks = len(re.findall(r"^\s*ok\b", saida, re.M))
    ok = codigo == 0 and n_falhas == 0 and not falhas and "Traceback" not in saida
    if not ok and not falhas:
        linhas = [l for l in saida.strip().splitlines() if l.strip()]
        falhas = linhas[-6:]
    return ok, dt, falhas, oks


def _ler_duracoes() -> dict:
    try:
        with open(DURACOES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _gravar_duracoes(d: dict):
    try:
        with open(DURACOES, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(d.items())), f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _quantos_paralelos(argv) -> int:
    if "--serie" in argv:
        return 1
    if "--paralelo" in argv:
        i = argv.index("--paralelo")
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            return max(1, int(argv[i + 1]))
    # cada verificador é um servidor + um Chrome desenhando o 3D por software: mais de um
    # núcleo cada. Com 6 de cada vez num i7 de 6 núcleos a máquina saturou (o de detalhar
    # levou 534 s em vez de 100) e a rodada não ganhou nada; 3 é o ponto certo
    return max(1, min(3, (os.cpu_count() or 2) // 4))


class _Fila:
    """Os verificadores pendentes; cada trabalhador pega o próximo cuja porta fixa não está
    em uso. Sem nada pegável e ainda com pendentes, espera alguém terminar."""

    def __init__(self, itens):
        self.pendentes = list(itens)               # (caminho, porta fixa)
        self.em_uso = set()
        self.cond = threading.Condition()

    def pegar(self):
        with self.cond:
            while True:
                for k, (c, porta) in enumerate(self.pendentes):
                    if porta is None or porta not in self.em_uso:
                        del self.pendentes[k]
                        if porta is not None:
                            self.em_uso.add(porta)
                        return c, porta
                if not self.pendentes:
                    return None
                self.cond.wait()

    def soltar(self, porta):
        with self.cond:
            if porta is not None:
                self.em_uso.discard(porta)
            self.cond.notify_all()


def main(argv):
    so_lista = "--lista" in argv
    filtros = [a for a in argv if not a.startswith("--") and not a.isdigit()]
    roda, fora = descobrir(filtros)
    if so_lista:
        for c in roda:
            print("roda  ", os.path.relpath(c, RAIZ), f"(porta fixa {_porta_fixa(c)})" if _porta_fixa(c) else "")
        for c in fora:
            print("fora  ", os.path.relpath(c, RAIZ), "(diagnóstico: pede argumentos)")
        return 0
    n = _quantos_paralelos(argv)
    duracoes = _ler_duracoes()
    nome_de = lambda c: os.path.splitext(os.path.basename(c))[0]        # noqa: E731
    # os mais demorados primeiro: o último a começar não segura a rodada inteira
    roda.sort(key=lambda c: -duracoes.get(nome_de(c), 60.0))
    print(f"{len(roda)} verificadores (fora {len(fora)} de diagnóstico), {n} de cada vez\n", flush=True)
    resultados = {}
    tela = threading.Lock()
    fila = _Fila([(c, _porta_fixa(c)) for c in roda])
    t0 = time.time()

    import progresso
    progresso.passo("verificadores das telas", 0, len(roda))

    def mostrar(nome, ok, dt, falhas, oks, nota=""):
        with tela:
            progresso.passo("verificadores das telas", len(resultados), len(roda),
                            ("repetindo " + nome) if nota else nome)
            print(f"{'ok   ' if ok else 'FALHA'}  {nome:28s} {dt:6.0f} s  {oks} verificações{nota}", flush=True)
            for f in falhas[:6]:
                print(f"         {f[:220]}", flush=True)

    def trabalhador():
        while True:
            item = fila.pegar()
            if item is None:
                return
            c, porta = item
            try:
                ok, dt, falhas, oks = rodar(c)
            finally:
                fila.soltar(porta)
            nome = nome_de(c)
            resultados[nome] = (c, ok, dt, falhas, oks)
            duracoes[nome] = round(dt, 1)
            mostrar(nome, ok, dt, falhas, oks)

    fios = [threading.Thread(target=trabalhador, daemon=True) for _ in range(n)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    # o que falhou roda de novo, sozinho: máquina cheia e corrida de porta não são erro do
    # programa — e a segunda tentativa fica dita no resultado
    ruins = [nome for nome, (_c, ok, *_r) in resultados.items() if not ok]
    if ruins and n > 1:
        print(f"\n{len(ruins)} falhou(aram) em paralelo: repetindo um a um…", flush=True)
        for nome in ruins:
            c = resultados[nome][0]
            ok, dt, falhas, oks = rodar(c)
            resultados[nome] = (c, ok, dt, falhas, oks)
            mostrar(nome, ok, dt, falhas, oks, "  (2ª tentativa)" if ok else "  (falhou de novo)")
    _gravar_duracoes(duracoes)
    ruins = [nome for nome, (_c, ok, *_r) in resultados.items() if not ok]
    print(f"\n{len(resultados) - len(ruins)} de {len(resultados)} passaram em {(time.time() - t0) / 60:.1f} min")
    if ruins:
        print("falharam:", ", ".join(sorted(ruins)))
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
