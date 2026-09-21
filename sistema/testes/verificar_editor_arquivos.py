# -*- coding: utf-8 -*-
"""Verificação dos menus de arquivo do editor 3D: salvar, abrir, exportar e importar IFC.

Complementa `verificar_editor.py`, que confere a abertura do galpão. Aqui a sequência
passa pelos mesmos métodos que os menus chamam, e não direto pelas rotas:

    1. abre o galpão com ?galpao=1
    2. editor.salvar(nome)                       menu Arquivo → Salvar
    3. apaga uma peça e chama editor.abrirModelo(nome), que deve devolver o modelo inteiro
    4. editor.exportarIFC()                      menu IFC → Exportar
    5. baixa o IFC pelo link do aviso e o entrega a editor._arquivoEscolhido(arquivo),
       o mesmo tratador do seletor de arquivo do menu IFC → Importar

Uso, com o servidor no ar:
    python testes/verificar_editor_arquivos.py --porta 8765

Sai com código 1 se algum passo falhar ou houver erro de JavaScript.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, BASE)

from verificar_editor import Aba, CHAVE_ESTADO, CHROMES, CONTAR_OBJETOS, _json, _porta_livre  # noqa: E402

NOME = "verificacao-arquivos"

SEQUENCIA = r"""
(async () => {
  const ed = window.editor;
  const saida = {passos: []};
  const conta = () => (ed.documento.tamanho ?? Object.keys(ed.documento.entidades || {}).length);
  const passo = (nome, dados) => saida.passos.push(Object.assign({passo: nome}, dados));
  try {
    passo('inicial', {objetos: conta()});

    ed.el.nome.value = NOME;
    await ed.salvar(NOME);
    const lista = await ed.api.lista();
    passo('salvar', {salvo: lista.some(m => m.nome === NOME), modelos: lista.length});

    // as entidades podem estar num Map; a consulta do próprio documento é o jeito seguro
    const barras = ed.documento.porTipo ? ed.documento.porTipo('barra') : [];
    const ents = ed.documento.entidades;
    const primeiro = barras.length ? barras[0].id
      : (ents instanceof Map ? [...ents.keys()][0] : Object.keys(ents || {})[0]);
    if (primeiro && ed.documento.remover) ed.documento.remover(primeiro);
    const antes = conta();
    await ed.abrirModelo(NOME);
    passo('abrir', {antes_de_abrir: antes, depois_de_abrir: conta()});

    await ed.exportarIFC();
    const links = [...document.querySelectorAll('a[download], a[href*=".ifc"]')];
    const url = links.length ? links[links.length - 1].getAttribute('href') : null;
    passo('exportar', {url});

    if (url) {
      const resp = await fetch(url);
      const bytes = await resp.arrayBuffer();
      const arquivo = new File([bytes], NOME + '.ifc', {type: 'application/octet-stream'});
      ed._modoArquivo = 'importar';
      await ed._arquivoEscolhido(arquivo);
      const e = ed.documento.estatisticas ? ed.documento.estatisticas() : {};
      passo('importar', {bytes: bytes.byteLength, objetos: conta(), estatisticas: e});
    }
  } catch (err) {
    saida.excecao = String(err && (err.stack || err.message) || err);
  }
  const avisos = [...document.querySelectorAll('[class*="aviso"], [class*="recado"], [role="alert"], [role="status"]')]
    .map(n => n.innerText.trim()).filter(Boolean);
  saida.avisos = [...new Set(avisos)].slice(-12);
  return JSON.stringify(saida);
})()
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--saida", default=os.path.join(BASE, "projetos", "_editor_arquivos.png"))
    ap.add_argument("--espera", type=float, default=60.0)
    args = ap.parse_args()

    from nucleo.modelo_galpao import DadosGalpao
    dados = DadosGalpao(nome="Verificação de arquivos", vao=20, comprimento=40,
                        pe_direito=6).dict()
    chrome = next((c for c in CHROMES if os.path.exists(c)), None)
    if not chrome:
        print("Chrome ou Edge não encontrado.")
        return 2
    base_url = f"http://localhost:{args.porta}"
    try:
        urllib.request.urlopen(base_url + "/", timeout=3)
    except Exception:
        print(f"Servidor fora do ar em {base_url}.")
        return 2

    porta_cdp = _porta_livre()
    perfil = tempfile.mkdtemp(prefix="verif_arquivos_")
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader",
         "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
         "--remote-allow-origins=*", f"--user-data-dir={perfil}",
         f"--remote-debugging-port={porta_cdp}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    codigo = 0
    try:
        alvo = None
        for _ in range(60):
            alvos = [t for t in _json(f"http://127.0.0.1:{porta_cdp}/json/list")
                     if t.get("type") == "page"]
            if alvos:
                alvo = alvos[0]
                break
            time.sleep(0.5)
        aba = Aba(alvo["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log"):
            aba.cmd(f"{dominio}.enable")
        aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
                deviceScaleFactor=1, mobile=False)

        aba.navegar(base_url + "/")
        aba.avaliar(f"localStorage.setItem({json.dumps(CHAVE_ESTADO)}, "
                    f"{json.dumps(json.dumps(dados, ensure_ascii=False))})")
        aba.console.clear()

        aba.navegar(base_url + "/editor?galpao=1", limite=30)
        t0 = time.time()
        objetos = -1
        while time.time() - t0 < args.espera:
            aba.drenar(1.0)
            objetos = aba.avaliar(CONTAR_OBJETOS)
            if isinstance(objetos, int) and objetos > 0:
                aba.drenar(2.0)
                break
        if not (isinstance(objetos, int) and objetos > 0):
            print("O galpão não carregou; a sequência de arquivos não foi executada.")
            return 1

        bruto = aba.avaliar(SEQUENCIA.replace("NOME", json.dumps(NOME)))
        aba.drenar(3.0)
        resultado = json.loads(bruto) if isinstance(bruto, str) else {"excecao": "sem resposta"}

        png = aba.cmd("Page.captureScreenshot", format="png")["data"]
        with open(args.saida, "wb") as f:
            f.write(base64.b64decode(png))

        p = {x["passo"]: x for x in resultado.get("passos", [])}
        inicial = p.get("inicial", {}).get("objetos")
        checagens = [
            ("salvar grava o modelo no servidor", p.get("salvar", {}).get("salvo") is True),
            ("abrir devolve o modelo inteiro",
             p.get("abrir", {}).get("depois_de_abrir") == inicial
             and p.get("abrir", {}).get("antes_de_abrir") == (inicial or 0) - 1),
            ("exportar gera o link do IFC", bool(p.get("exportar", {}).get("url"))),
            ("importar traz de volta todas as peças", p.get("importar", {}).get("objetos") == inicial),
        ]
        for rotulo, ok in checagens:
            print(f"  {'ok   ' if ok else 'FALHA'} {rotulo}")
            codigo = codigo or (0 if ok else 1)
        print("passos:", json.dumps(resultado.get("passos", []), ensure_ascii=False))
        if resultado.get("excecao"):
            print("exceção na sequência:", resultado["excecao"][:600])
            codigo = 1
        if resultado.get("avisos"):
            print("avisos na tela:")
            for a in resultado["avisos"]:
                print("   -", a.replace("\n", " ")[:200])
        erros = [c for c in aba.console if c[0] in ("error", "excecao")]
        print(f"erros de JavaScript: {len(erros)}")
        for tipo, texto in erros[:10]:
            print(f"   [{tipo}] {texto[:300]}")
        if erros:
            codigo = 1
        print(f"captura: {args.saida}")
        aba.ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
