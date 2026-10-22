# -*- coding: utf-8 -*-
"""TEL-02 (sistema/testes/REGRAS.md, aprovada pelo usuário em 22/10): toda peça cai num sistema do modo ver e do celular
cujo nome diz o que ela é (web/visor3d/sistemas.js, rodado no node). Primeiro o nome da peça, depois a camada e o grupo,
por último o material; Outros só com motivo conhecido (no nome: "Outros — PVC"); o material que ninguém reconhece vai
para "Sem material — a definir". conferirSistemas confere o modelo inteiro.

Os 3 exemplos aprovados (Projeto/ANALISES/Interface/TEL-02-sistemas-do-modo-ver-proposta-2026-10-22.pdf):
  1. SESI Chapecó: o arquitetônico de referência (telhas de Concreto, paredes, vidro) — as 4 correções de 22/10;
  2. ME Sooro: os parafusos do IFC só com a cor ("Cor #ff0000") estavam em Outros — vão para a Metálica;
  3. Vicente Residence: vigas, pilares e estacas com o material "Vigas"/"Pilares" estavam em Outros — "Sem material".

E a trava da versão (o usuário: "barra a versão quando piora"): nas obras do desenvolvimento, a conferência não pode
achar mais peças fora do lugar que na fotografia aceita (Projeto/bateria/sistemas-modo-ver.json). Aceitar depois de
conferir: python testes/test_sistemas_modo_ver.py --aceitar"""
import glob
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(os.path.dirname(AQUI), "web", "visor3d", "sistemas.js")
FOTOGRAFIA = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "Projeto", "bateria", "sistemas-modo-ver.json")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")


def _rodar(camadas, pecas) -> dict:
    """{sistemas: {nome do grupo: [ids das peças]}, chaves: {chave: nome}, conferencia: [textos]}"""
    url = "file:///" + MODULO.replace("\\", "/")
    js = textwrap.dedent("""
        const M = await import(%s);
        const pecas = %s, camadas = %s;
        const visor = { fichas: pecas, nPecas: pecas.length, cabecalho: { camadas } };
        const g = M.gruposDeSistema(visor);
        console.log(JSON.stringify({ sistemas: Object.fromEntries(g.map(x => [x.nome, x.ids.map(i => pecas[i].id)])),
          chaves: Object.fromEntries(g.map(x => [x.chave, x.nome])), conferencia: M.conferirSistemas(visor).map(a => a.texto) }));
    """) % (json.dumps(url), json.dumps(pecas, ensure_ascii=False), json.dumps(camadas, ensure_ascii=False))
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _modelo(*itens):
    """itens: (id, nome, material, camada[, grupo]) → (camadas, fichas)"""
    nomes = []
    for it in itens:
        if (it[3], it[4] if len(it) > 4 else "") not in nomes:
            nomes.append((it[3], it[4] if len(it) > 4 else ""))
    camadas = [{"nome": n, "grupo": g} if g else {"nome": n} for n, g in nomes]
    idx = {n: k for k, (n, _g) in enumerate(nomes)}
    return camadas, [{"id": it[0], "n": it[1], "m": it[2], "c": idx[it[3]], "p": ""} for it in itens]


def test_exemplo_1_sesi_o_arquitetonico_de_referencia_e_a_cobertura_dele():
    """As 4 correções do SESI de 22/10 de uma vez: a telha e a calha do arquitetônico (Concreto) na Cobertura; a parede e o
    pilar de Concreto e o forro de Vidro do arquitetônico no Arquitetônico — o vidro do arquitetônico não vira "Outros —
    vidro" (a regra do ARQ vem antes do material); as tesouras do grupo "Cobertura frontal" na Metálica."""
    r = _rodar(*_modelo(("tel", "Cobertura do ginásio", "Concreto", "ARQ — Telhas", "ARQUITETÔNICO"),
                        ("cal", "Calha da borda sul", "Concreto", "ARQ — Outros", "ARQUITETÔNICO"),
                        ("par", "Parede", "Concreto", "ARQ — Paredes", "ARQUITETÔNICO"),
                        ("for", "Forro", "Vidro", "ARQ — Forros", "ARQUITETÔNICO"),
                        ("tes", "banzo", "", "Cobertura frontal e eixo 1 — Tesouras", "Cobertura frontal e eixo 1")))
    s = r["sistemas"]
    assert sorted(s["Cobertura — telhas, calhas e rufos"]) == ["cal", "tel"]
    assert sorted(s["Arquitetônico (referência)"]) == ["for", "par"]
    assert s["Metálica"] == ["tes"]
    assert "outros" not in r["chaves"] and r["conferencia"] == []


def test_exemplo_2_sooro_o_parafuso_do_ifc_so_com_a_cor_e_metalica():
    """O IFC do Sooro grava o material do parafuso como a cor ("Cor #ff0000"): 1.010 parafusos em Outros. Também o
    marcador de furo ("Cor #1f2430") e a peça metálica do Capitão com o material automático ("<auto>7")."""
    r = _rodar(*_modelo(("bol", "BOLT (A) 12x35", "Cor #ff0000", "Parafusos"), ("fur", "furo", "Cor #1f2430", "Furos"),
                        ("cap", "CPLAN_MATERIAL_PIEZA_METALICA_PILAR0", "<auto>7", "CPLAN_MATERIAL_PIEZA_METALICA_PILAR0"),
                        ("ter", "terça", "", "Terças")))
    assert sorted(r["sistemas"]["Metálica"]) == ["bol", "cap", "fur", "ter"]
    assert r["conferencia"] == []


def test_exemplo_3_vicente_o_material_desconhecido_e_sem_material_a_definir():
    """A leitura da Vicente gravou o nome da camada como material ("Vigas", "Pilares", "Estacas"): 3.146 peças caíam em
    Outros, sem ninguém apontar. Agora o sistema diz o problema e a conferência pede o material."""
    r = _rodar(*_modelo(("v1", "V1", "Vigas", "Vigas"), ("p1", "P1", "Pilares", "Pilares"), ("e1", "E1", "Estacas", "Subsolo"),
                        ("aco", "W200", "Aço", "Metálica")))
    assert sorted(r["sistemas"]["Sem material — a definir"]) == ["e1", "p1", "v1"]
    assert r["sistemas"]["Metálica"] == ["aco"]
    assert len(r["conferencia"]) == 3 and all("sem material conhecido" in t for t in r["conferencia"])
    assert any('camada "Vigas", material "Vigas"' in t for t in r["conferencia"])


def test_outros_so_com_motivo_e_o_motivo_no_nome():
    """Decisão 4 (22/10): madeira e argamassa em Outros com o motivo; a armadura no Pré-moldado (também a do material
    "STEEL/CA-50" dos pinos do pré-moldado); a chapa com o material "Aço (CA-60)" continua na Metálica (o nome e a camada
    vêm antes); o neoprene da camada do pré-moldado fica com ele (16/10)."""
    r = _rodar(*_modelo(("pvc", "Descida", "MISCELLANEOUS/PVC", "400 Descidas"), ("mad", "Deck", "Deck madeira", "Deck"),
                        ("arg", "Base", "Argamassa", "Fundação"), ("arm", "Armadura", "Armadura", "Armaduras"),
                        ("pin", "PI1", "STEEL/CA-50", "1 Fase 1"), ("ch", "-", "Aço (CA-60)", "Chapas"),
                        ("pil", "Pilar", "CONCRETE/Fck-40", "200 Pré"), ("pil2", "Pilar", "CONCRETE/Fck-40", "200 Pré"),
                        ("neo", "Neoprene", "STEEL/SHORE A-60", "200 Pré")))
    s = r["sistemas"]
    assert sorted(s["Outros — argamassa, madeira, PVC"]) == ["arg", "mad", "pvc"]
    assert sorted(s["Pré-moldado (concreto)"]) == ["arm", "neo", "pil", "pil2", "pin"]
    assert s["Metálica"] == ["ch"]


def test_conferencia_acusa_o_perfil_de_aco_em_outros():
    """O sinal que não é o da classificação: a peça com perfil de aço (W, U, L…) e material de Outros (PVC) é apontada."""
    camadas, pecas = _modelo(("x", "Viga", "MISCELLANEOUS/PVC", "Importadas"))
    pecas[0]["p"] = "W200x22,5"
    r = _rodar(camadas, pecas)
    assert len(r["conferencia"]) == 1 and "perfil de aço em Outros" in r["conferencia"][0]


# ---- a trava da versão: nas obras do desenvolvimento, a conferência não piora -----------------------------------------

def _obras_do_desenvolvimento() -> dict:
    """o 3D leve guardado de cada obra (o mais novo, se houver mais de uma pasta de dados): {obra: pecas.json}"""
    base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Metálica", "3d-leve")
    obras = {}
    for arq in glob.glob(os.path.join(base, "*", "*", "pecas.json")):
        nome = os.path.basename(os.path.dirname(arq))
        if nome not in obras or os.path.getmtime(arq) > os.path.getmtime(obras[nome]):
            obras[nome] = arq
    return obras


def _conferir_obras(obras: dict) -> dict:
    """{obra: peças fora do lugar}, pela conferirSistemas no node"""
    url = "file:///" + MODULO.replace("\\", "/")
    js = textwrap.dedent("""
        import fs from 'fs';
        const M = await import(%s);
        const obras = %s, saida = {};
        for (const [obra, arq] of Object.entries(obras)) {
          const d = JSON.parse(fs.readFileSync(arq, 'utf8'));
          const visor = { fichas: d.pecas || [], nPecas: (d.pecas || []).length, cabecalho: { camadas: d.camadas || [] } };
          saida[obra] = M.conferirSistemas(visor).reduce((t, a) => t + a.n, 0);
        }
        console.log(JSON.stringify(saida));
    """) % (json.dumps(url), json.dumps(obras, ensure_ascii=False))
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=300, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_obras_do_desenvolvimento_nao_pioram():
    if not os.path.isfile(FOTOGRAFIA):
        pytest.skip("sem a fotografia aceita (Projeto/bateria/sistemas-modo-ver.json)")
    obras = _obras_do_desenvolvimento()
    if not obras:
        pytest.skip("sem 3D leve guardado nesta máquina")
    with open(FOTOGRAFIA, encoding="utf-8") as f:
        aceita = json.load(f)["obras"]
    agora = _conferir_obras({o: a for o, a in obras.items() if o in aceita})
    piores = {o: (aceita[o], n) for o, n in agora.items() if n > aceita[o]}
    assert not piores, ("TEL-02: mais peças fora do lugar no modo ver que na fotografia aceita (aceita → agora): %s. "
                        "Conferir no modo ver; se estiver certo, python testes/test_sistemas_modo_ver.py --aceitar" % piores)


if __name__ == "__main__" and "--aceitar" in sys.argv:
    resultado = _conferir_obras(_obras_do_desenvolvimento())
    os.makedirs(os.path.dirname(FOTOGRAFIA), exist_ok=True)
    with open(FOTOGRAFIA, "w", encoding="utf-8") as f:
        json.dump({"regra": "TEL-02", "obras": resultado}, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("aceita:", FOTOGRAFIA, {o: n for o, n in resultado.items() if n})
