# -*- coding: utf-8 -*-
"""A obra compartilhada (13/11, passo 1a): os apontamentos na nuvem, de ponta a ponta, com o Worker metalica-celular
rodando NESTA máquina (wrangler dev --local: o mesmo código, com D1 e R2 locais numa pasta temporária — nada vai para
a Cloudflare). Dois "computadores" (o dev do dono e o do Fernando, Editor) com a mesma obra (o mesmo obra_id):

* o Fernando aponta 3 → sobem; o dev recebe os 3, no formato do Controle, com o "quem" da licença (não o que o PC diz);
* sincronizar de novo não duplica nada; o estorno do dev chega no Fernando;
* Leitor recebe tudo e é recusado ao apontar (a fila fica); quem não tem acesso é recusado; licença bloqueada também;
* sem internet: o evento fica na fila ("esperando a internet") e sobe quando a nuvem volta;
* o projeto que chegou num pacote de outro PC começa do zero: os eventos do pacote não sobem em nome de quem recebeu;
* evento inválido é recusado e sai da fila; iniciar põe na fila o que já existia.

Precisa do wrangler em %LOCALAPPDATA%\\Metalica-ferramentas\\cloudflare; sem ele, pula."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import _porta_livre

FERR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Metalica-ferramentas", "cloudflare")
WRANGLER = os.path.join(FERR, "node_modules", ".bin", "wrangler.cmd")
SERV = os.path.join(RAIZ, "servicos", "celular")
if not os.path.isfile(WRANGLER) or not os.path.isdir(SERV):
    print("  pulado: sem o wrangler (ou sem servicos/celular) nesta máquina")
    print()
    print("FALHAS: 0")
    sys.exit(0)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import licenca
import obra_compartilhada as OC

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


PRIV = Ed25519PrivateKey.generate()
PUB = base64.b64encode(PRIV.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def lic(chave, maquina, pessoa):
    p = json.dumps({"v": 1, "chave": chave, "maquina": maquina, "pessoa": pessoa, "emitida": "2026-11-13T00:00:00Z",
                    "validade": "2026-12-13T00:00:00Z"}).encode()
    return b64url(p) + "." + b64url(PRIV.sign(p))


DONO, FERN, LEIT, FORA, BLOQ = ("MTL-DONO-AAAA-AAAA", "MTL-FERN-BBBB-BBBB", "MTL-LEIT-CCCC-CCCC", "MTL-FORA-DDDD-DDDD",
                                "MTL-BLOQ-EEEE-EEEE")
OBRA = "0123456789abcdef0123456789abcdef"
INATIVA = "fedcba9876543210fedcba9876543210"
TMP = tempfile.mkdtemp(prefix="metalica_obra_comp_")
PERSIST = os.path.join(TMP, "wrangler")
amb = dict(os.environ, WRANGLER_SEND_METRICS="false", CI="1", NO_COLOR="1")


def sql(comando=None, arquivo=None):
    args = [WRANGLER, "d1", "execute", "metalica-licencas", "--local", "--persist-to", PERSIST, "-c", "wrangler.toml"]
    args += ["--file", arquivo] if arquivo else ["--command", comando]
    r = subprocess.run(args, cwd=SERV, capture_output=True, text=True, encoding="utf-8", errors="replace", env=amb, timeout=180)
    if r.returncode:
        raise RuntimeError("d1: " + (r.stderr or r.stdout)[-800:])


# ------------------------------------------------------------------ os "computadores"
PCS = {"dev": (DONO, "pc-dev", "Elieber"), "fernando": (FERN, "pc-fab", "Fernando"), "leitor": (LEIT, "pc-leit", "Leitor"),
       "fora": (FORA, "pc-fora", "Fora"), "bloq": (BLOQ, "pc-bloq", "Bloqueado")}


def no_pc(nome):
    ch, maq, pessoa = PCS[nome]
    licenca.token = lambda: lic(ch, maq, pessoa)
    licenca.impressao_da_maquina = lambda: maq


def projeto(nome, obra_id=OBRA):
    p = os.path.join(TMP, "dados-" + nome, "posto-teste")
    os.makedirs(os.path.join(p, "producao"), exist_ok=True)
    json.dump({"nome": "POSTO TESTE", "compartilhada": {"obra_id": obra_id, "nome": "POSTO TESTE"}},
              open(os.path.join(p, "projeto.json"), "w", encoding="utf-8"))
    return p


N = [0]


def apontar(pasta, item, q=1, etapa="producao", quem="?", estorno_de=None, ancora=None):
    """o que o Controle faz: grava a linha no formato dele e põe na fila (a âncora no fim, só quando existe)"""
    N[0] += 1
    ev = {"id": "ev%010d" % N[0], "quando": "2026-11-13T10:%02d:00" % (N[0] % 60), "data": "2026-11-13", "quem": quem,
          "etapa": etapa, "item": item, "refs": ["M1"], "quantidade": q, "kg": 10.5 * q, "estorno_de": estorno_de, "obs": ""}
    if ancora:
        ev["ancora"] = list(ancora)
    OC._acrescentar(pasta, [ev])
    OC.na_fila(pasta, ev["id"])
    return ev


def linhas(pasta):
    return OC._ler_eventos(pasta)


srv = None
try:
    sql(arquivo=os.path.join(RAIZ, "servicos", "licencas", "schema.sql"))
    sql(arquivo="schema.sql")
    sql(arquivo="migracao-celular.sql")
    sql(arquivo="migracao-obra-compartilhada.sql")
    sql(arquivo="migracao-obra-compartilhada.sql")          # de novo: a migração pode rodar duas vezes sem erro
    sql(arquivo="migracao-obra-compartilhada-2.sql")        # a âncora do apontamento (13/11)
    lics = ", ".join(f"('{ch}', '{pes}', 2, {0 if k == 'bloq' else 1}, '2026-11-13')" for k, (ch, _, pes) in PCS.items())
    maqs = ", ".join(f"('{ch}', '{maq}', '2026-11-13', '2026-11-13')" for ch, maq, _ in PCS.values())
    sql(f"INSERT INTO licencas (chave, pessoa, maquinas_max, ativa, criada) VALUES {lics};"
        f"INSERT INTO maquinas (chave, maquina, ativada, ultima_vez) VALUES {maqs};"
        f"INSERT INTO obras (obra_id, nome, dono_chave, criada, ativa) VALUES ('{OBRA}', 'POSTO TESTE', '{DONO}', '2026-11-13', 1),"
        f" ('{INATIVA}', 'VELHA', '{DONO}', '2026-11-13', 0);"
        f"INSERT INTO obra_acessos (obra_id, chave, papel, desde) VALUES ('{OBRA}', '{DONO}', 'dono', '2026-11-13'),"
        f" ('{OBRA}', '{FERN}', 'editor', '2026-11-13'), ('{OBRA}', '{LEIT}', 'leitor', '2026-11-13'),"
        f" ('{OBRA}', '{BLOQ}', 'editor', '2026-11-13'), ('{INATIVA}', '{FERN}', 'editor', '2026-11-13')")
    PORTA = _porta_livre()
    URL = f"http://127.0.0.1:{PORTA}"
    srv = subprocess.Popen([WRANGLER, "dev", "--local", "--persist-to", PERSIST, "-c", "wrangler.toml", "--ip", "127.0.0.1",
                            "--port", str(PORTA), "--var", "LICENCA_CHAVE_PUBLICA:" + PUB, "--show-interactive-dev-session=false"],
                           cwd=SERV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
    for _ in range(120):
        try:
            urllib.request.urlopen(URL + "/celular/", timeout=2)
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.5)
    os.environ["METALICA_COMPARTILHAR"] = URL

    dev, fer, lei = projeto("dev"), projeto("fernando"), projeto("leitor")

    # ------------------------------------------------------------------ as obras de cada um
    no_pc("fernando")
    obs = OC.compartilhadas()
    ok([o["obra_id"] for o in obs] == [OBRA] and obs[0]["papel"] == "editor" and obs[0]["dono"] == "Elieber",
       f"o Fernando vê só a obra ativa, como Editor, dona Elieber: {obs}")

    # ------------------------------------------------------------------ o Fernando aponta 3
    for item in ("TESOURA 14-1", "COMP 18-1", "PAINEL 15"):
        apontar(fer, item, quem="Fernando (o que o PC diz)", ancora=["p14a", "p14b"] if item == "TESOURA 14-1" else None)
    ok(OC.estado(fer)["pendentes"] == 3, "3 apontamentos do Fernando esperando a nuvem")
    r = OC.sincronizar(fer)
    ok(r["enviados"] == 3 and r["pendentes"] == 0 and r["papel"] == "editor" and not r["erro"],
       f"o Fernando sincroniza: 3 sobem, nada pendente, papel editor: {r}")

    no_pc("dev")
    r = OC.sincronizar(dev)
    ls = linhas(dev)
    ok(r["recebidos"] == 3 and len(ls) == 3, f"o dev recebe os 3: {r['recebidos']} recebidos, {len(ls)} linhas")
    ok(all(list(x.keys())[:len(OC._CAMPOS)] == list(OC._CAMPOS) for x in ls), "as linhas recebidas têm o formato do Controle (mesmos campos, mesma ordem)")
    ok(ls[0].get("ancora") == ["p14a", "p14b"] and list(ls[0])[-1] == "ancora" and "ancora" not in ls[1],
       f"a âncora chega no fim do evento, e só no que tinha: {ls[0].get('ancora')}")
    ok({x["quem"] for x in ls} == {"Fernando"}, f"o 'quem' é a pessoa da licença que assinou, não o que o PC disse: {ls[0]['quem']}")
    ok([x["item"] for x in ls] == ["TESOURA 14-1", "COMP 18-1", "PAINEL 15"] and ls[0]["kg"] == 10.5 and ls[0]["refs"] == ["M1"],
       "itens, kg e refs chegam iguais")
    r = OC.sincronizar(dev)
    ok(r["recebidos"] == 0 and len(linhas(dev)) == 3, "sincronizar de novo não duplica")

    # ------------------------------------------------------------------ o estorno do dev chega ao Fernando
    est = apontar(dev, "COMP 18-1", quem="Elieber", estorno_de=ls[1]["id"])
    r = OC.sincronizar(dev)
    ok(r["enviados"] == 1 and len(linhas(dev)) == 4, f"o estorno do dev sobe e não se duplica no próprio dev: {r['enviados']}, {len(linhas(dev))}")
    no_pc("fernando")
    r = OC.sincronizar(fer)
    lf = linhas(fer)
    ok(r["recebidos"] == 1 and len(lf) == 4 and lf[-1]["estorno_de"] == ls[1]["id"] and lf[-1]["id"] == est["id"],
       f"o estorno chega ao Fernando: {r['recebidos']} recebido(s), {len(lf)} linhas")

    # ------------------------------------------------------------------ Leitor
    no_pc("leitor")
    r = OC.sincronizar(lei)
    ok(r["recebidos"] == 4 and r["papel"] == "leitor" and not r["pode_apontar"], f"o Leitor recebe tudo e a tela sabe que ele não aponta: {r}")
    apontar(lei, "PAINEL 15", quem="Leitor")
    r = OC.sincronizar(lei)
    ok(r["pendentes"] == 1 and "leitor" in r["erro"], f"o apontamento do Leitor é recusado pela nuvem e fica só no PC dele: {r['erro']}")
    no_pc("dev")
    ok(OC.sincronizar(dev)["recebidos"] == 0, "nada do Leitor chega ao dev")

    # ------------------------------------------------------------------ sem acesso, bloqueado, obra inativa
    fora = projeto("fora")
    no_pc("fora")
    r = OC.sincronizar(fora)
    ok("acesso" in r["erro"] and r["papel"] is None, f"licença sem acesso à obra é recusada: {r['erro']}")
    bl = projeto("bloq")
    no_pc("bloq")
    r = OC.sincronizar(bl)
    ok("bloqueada" in r["erro"], f"licença bloqueada é recusada: {r['erro']}")
    ina = projeto("inativa", INATIVA)
    no_pc("fernando")
    r = OC.sincronizar(ina)
    ok("acesso" in r["erro"], f"obra que deixou de ser compartilhada é recusada: {r['erro']}")

    # ------------------------------------------------------------------ sem internet
    os.environ["METALICA_COMPARTILHAR"] = f"http://127.0.0.1:{_porta_livre()}"
    apontar(fer, "TESOURA 14-2", quem="Fernando")
    r = OC.sincronizar(fer, timeout=2)
    ok(r["pendentes"] == 1 and "sem conexão" in r["erro"], f"sem internet: fica na fila ({r['pendentes']}) e diz por quê: {r['erro']}")
    os.environ["METALICA_COMPARTILHAR"] = URL
    r = OC.sincronizar(fer)
    ok(r["enviados"] == 1 and r["pendentes"] == 0 and not r["erro"], f"a internet volta: sobe sozinho: {r}")
    no_pc("dev")
    ok(OC.sincronizar(dev)["recebidos"] == 1, "e chega ao dev")

    # ------------------------------------------------------------------ o projeto que veio num pacote de outro PC
    pac = os.path.join(TMP, "dados-mariana", "posto-teste")
    shutil.copytree(fer, pac)
    PCS["mariana"] = (FERN, "pc-mariana", "Fernando")       # outro PC da mesma licença
    sql(f"INSERT INTO maquinas (chave, maquina, ativada, ultima_vez) VALUES ('{FERN}', 'pc-mariana', '2026-11-13', '2026-11-13')")
    no_pc("mariana")
    antes = len(linhas(pac))
    e = OC.estado(pac)
    ok(e["pendentes"] == 0, f"o projeto copiado de outro PC não traz a fila de lá: {e['pendentes']}")
    r = OC.sincronizar(pac)
    ok(r["enviados"] == 0 and len(linhas(pac)) == antes, f"e nada se duplica nem sobe de novo: {r['enviados']} enviados, {antes} -> {len(linhas(pac))} linhas")

    # ------------------------------------------------------------------ evento inválido; iniciar
    no_pc("fernando")
    ruim = apontar(fer, "PAINEL 15", q=0, quem="Fernando")
    r = OC.sincronizar(fer)
    ok(r["pendentes"] == 0 and ruim["id"] in OC._ler_estado(fer, OBRA).get("recusados", []),
       "evento inválido (quantidade 0) é recusado, sai da fila e fica anotado")
    nova = projeto("iniciar")
    shutil.copy(os.path.join(dev, "producao", "apontamentos.jsonl"), os.path.join(nova, "producao", "apontamentos.jsonl"))
    no_pc("dev")
    OC.iniciar(nova)
    ok(OC.estado(nova)["pendentes"] == len(linhas(dev)), "iniciar põe na fila os apontamentos que já existiam")
    r = OC.sincronizar(nova)
    ok(r["pendentes"] == 0 and r["enviados"] == 0, f"os que a nuvem já tem não se repetem (INSERT OR IGNORE): {r}")
finally:
    if srv:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(srv.pid)], capture_output=True)
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
