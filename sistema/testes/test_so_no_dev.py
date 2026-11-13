# -*- coding: utf-8 -*-
"""Módulos só do desenvolvimento: o que o app.py carrega pelo `_extensoes_dev` fica fora do instalado.

Até 02/11 o gancho `_extensoes_dev` vivia só no app.py de trabalho, fora do git. Com ele no git (base limpa,
VERSÃO N.2), o PyInstaller acha os `import x.web` dentro da função e levaria o módulo para o programa instalado,
a não ser que ele esteja em MODULOS_SO_DEV (e a pasta das telas dele em TELAS_SO_DEV) do empacotar/construir.py.
A arquitetura (30/10) entrou no gancho sem entrar nas listas.
"""
import ast
import fnmatch
import json
import os
import subprocess
import sys
import tempfile

SISTEMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTRUIR = os.path.join(os.path.dirname(SISTEMA), "empacotar", "construir.py")


def _listas_do_construir():
    arv = ast.parse(open(CONSTRUIR, encoding="utf-8").read())
    listas = {}
    for no in arv.body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
            if no.targets[0].id in ("MODULOS_SO_DEV", "TELAS_SO_DEV"):
                listas[no.targets[0].id] = ast.literal_eval(no.value)
    return listas["MODULOS_SO_DEV"], listas["TELAS_SO_DEV"]


def _modulos_do_gancho():
    arv = ast.parse(open(os.path.join(SISTEMA, "app.py"), encoding="utf-8").read())
    func = next(n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name == "_extensoes_dev")
    return sorted({a.name for n in ast.walk(func) if isinstance(n, ast.Import) for a in n.names})


def test_o_gancho_carrega_os_modulos_do_dev():
    mods = _modulos_do_gancho()
    assert {"premoldado.web", "arquitetura.web", "celular.web", "painel_dev.web"} <= set(mods), mods


def test_todo_modulo_do_gancho_fica_fora_do_instalado():
    modulos, telas = _listas_do_construir()
    faltam = []
    for m in _modulos_do_gancho():
        pacote = m.split(".")[0]
        if pacote not in modulos:                   # o pacote fora leva os submódulos junto (PyInstaller)
            faltam.append("MODULOS_SO_DEV: " + pacote)
        # as telas do módulo (web/<pacote>/) também ficam de fora
        if os.path.isdir(os.path.join(SISTEMA, "web", pacote)) and not any(fnmatch.fnmatch(pacote, t) for t in telas):
            faltam.append("TELAS_SO_DEV: web/" + pacote)
    assert not faltam, "módulo do dev que iria no instalado: " + "; ".join(faltam)


def _modulos_da(funcao):
    arv = ast.parse(open(os.path.join(SISTEMA, "app.py"), encoding="utf-8").read())
    func = next(n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name == funcao)
    return sorted({a.name for n in ast.walk(func) if isinstance(n, ast.Import) for a in n.names})


def test_o_controle_de_producao_vai_no_instalado():
    """13/11 (FERRAMENTA · OBRA COMPARTILHADA, item 3 da 1a): o Controle de produção vai no programa instalado — só para
    a obra compartilhada (a trava está no producao/web.py) — pelo `_extensoes_gerais`; nada dele fica nas listas do dev."""
    modulos, telas = _listas_do_construir()
    gerais = _modulos_da("_extensoes_gerais")
    assert "producao.web" in gerais and "producao.web" not in _modulos_do_gancho()
    for m in gerais:
        assert m.split(".")[0] not in modulos and m not in modulos, "módulo geral deixado fora do instalado: " + m
        assert not any(fnmatch.fnmatch(m.split(".")[0], t) for t in telas), "telas de módulo geral fora do instalado: " + m
    # e o que ele importa também vai (obra_compartilhada, licenca, versao)
    assert not {"obra_compartilhada", "licenca", "versao"} & set(modulos)


#: Os imports de módulo só do dev que o instalado nunca alcança: as rotas barradas pelo COMERCIAL / LICENCAS_DEV antes de
#: chegar à função, o gancho do dev (protegido por try) e as fotos do dossiê e do memorial pelo imagens3d (quem chama
#: pega o erro: no instalado o resumo sai sem as fotos). (arquivo, função em que o import está)
ALCANCE_SO_DEV = {
    ("app.py", "_orcamento_montado"), ("app.py", "rota_orcamento"), ("app.py", "rota_comercial"),
    ("app.py", "_licencas_dev"),
    ("saida/dossie.py", "fotografar"), ("saida/memorial_quantitativo.py", "fotografar"),
}


def _e_so_dev(nome, modulos):
    return any(nome == m or nome.startswith(m + ".") for m in modulos)


def test_o_instalado_nao_importa_modulo_so_do_dev():
    """Conferência da 0.9.3 (13/11): o resumo de compra importava saida.orcamento (a régua das chapas, 9c0c643), as Cenas
    e o carimbo das pranchas importavam saida.comercial (o cadastro das empresas) — fora do instalado (MODULOS_SO_DEV), o
    .exe dava "No module named …" no Resumo da obra, na marca d'água e no Montar pranchas da obra da DEZN. Todo módulo que
    vai no instalado só importa módulo só do dev protegido por try/except ou numa função que só o dev alcança."""
    modulos, _ = _listas_do_construir()
    achados = []
    for raiz, dirs, arqs in os.walk(SISTEMA):
        dirs[:] = [d for d in dirs if d not in ("testes", "__pycache__", "web", "projetos")]
        for a in arqs:
            if not a.endswith(".py"):
                continue
            caminho = os.path.join(raiz, a)
            rel = os.path.relpath(caminho, SISTEMA).replace(os.sep, "/")
            mod = rel[:-3].replace("/__init__", "").replace("/", ".")
            if _e_so_dev(mod, modulos) or rel == "dev.py":
                continue
            arv = ast.parse(open(caminho, encoding="utf-8").read())
            pais = {f: n for n in ast.walk(arv) for f in ast.iter_child_nodes(n)}
            for n in ast.walk(arv):
                if isinstance(n, ast.Import):
                    alvos = [x.name for x in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    alvos = [n.module] + [n.module + "." + x.name for x in n.names]
                else:
                    continue
                if not any(_e_so_dev(x, modulos) for x in alvos):
                    continue
                p, protegido, funcao = pais.get(n), False, None
                while p is not None:
                    if isinstance(p, ast.Try) and any(h.type is None or "Error" in ast.dump(h.type) or "Exception" in ast.dump(h.type)
                                                      for h in p.handlers):
                        protegido = True
                    if funcao is None and isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        funcao = p.name
                    p = pais.get(p)
                if not protegido and (rel, funcao) not in ALCANCE_SO_DEV:
                    achados.append("%s:%d %s (em %s)" % (rel, n.lineno, next(x for x in alvos if _e_so_dev(x, modulos)),
                                                         funcao or "módulo"))
    assert not achados, "o instalado importaria módulo só do dev: " + "; ".join(achados)


_SEM_O_DEV = r"""
import importlib.abc, json, os, sys
SO_DEV = json.loads(os.environ["SO_DEV"])
class Barra(importlib.abc.MetaPathFinder):
    def find_spec(self, nome, caminho=None, alvo=None):
        if any(nome == m or nome.startswith(m + ".") for m in SO_DEV):
            raise ModuleNotFoundError("No module named %r (só do dev)" % nome)
        return None
sys.meta_path.insert(0, Barra())
sys.path.insert(0, os.environ["SISTEMA"])
dados = os.environ["DADOS"]
from saida import resumos, cenas
print(resumos._chapas_por_rotulo([{"espessura": 15.0, "peso": 10.0, "pecas": 1, "material": "A36"}])[0]["t"])
class G:
    raiz = dados
    def ler(self, s): return {"carimbo_pranchas": {"empresa": "dezn"}}
    def pasta(self, s): return os.path.join(dados, s)
print(len(cenas.empresas_da_marca(G(), "obra")))
os.environ["METALICA_DADOS"] = dados
import app
app._logo_do_carimbo({"carimbo_pranchas": {"empresa": "dezn"}})   # o import dentro dela: sem ele, ModuleNotFoundError
print("carimbo")
"""


def test_resumo_marca_e_carimbo_sem_os_modulos_do_dev():
    """O mesmo, rodando: com os módulos só do dev barrados como no .exe, o resumo de compra das chapas, a marca d'água
    das Cenas e o logo do carimbo da empresa do projeto funcionam (13/11, conferência da 0.9.3)."""
    modulos, _ = _listas_do_construir()
    dados = tempfile.mkdtemp(prefix="sem_dev_")
    marca = os.path.join(dados, "fabrica", "empresas", "dezn", "marca")
    os.makedirs(marca)
    with open(os.path.join(dados, "fabrica", "empresas", "dezn", "empresa.json"), "w", encoding="utf-8") as f:
        json.dump({"nome_comercial": "DEZN"}, f)
    with open(os.path.join(marca, "logo.svg"), "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>')
    env = dict(os.environ, SO_DEV=json.dumps(modulos), SISTEMA=SISTEMA, DADOS=dados, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", _SEM_O_DEV], capture_output=True, text=True, encoding="utf-8", env=env,
                       cwd=SISTEMA, timeout=300)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.split() == ["15.88", "2", "carimbo"], r.stdout
