// Conversa com o servidor local: /api/modelo/*.
//
// O servidor responde JSON sempre; quando algo dá errado, o corpo traz {erro, detalhe}.
// Aqui isso vira um `ErroServidor` com a mensagem em português que o usuário deve ver,
// e o traceback fica em `detalhe` para o console. Nenhuma chamada engole erro em
// silêncio: quem chamou decide se mostra ou se usa um caminho alternativo.

export class ErroServidor extends Error {
  constructor(mensagem, status = 0, detalhe = '', rota = '') {
    super(mensagem);
    this.name = 'ErroServidor';
    this.status = status;
    this.detalhe = detalhe;
    this.rota = rota;
    // 501 é o que o app.py devolve quando um módulo Python ainda não existe.
    this.faltaModulo = status === 501;
  }
}

async function pedir(rota, opcoes = {}) {
  let resposta;
  try {
    resposta = await fetch(rota, opcoes);
  } catch (e) {
    throw new ErroServidor('não foi possível falar com o servidor — ele ainda está no ar?',
                           0, String(e && e.message || e), rota);
  }
  const texto = await resposta.text();
  let dados = null;
  if (texto) {
    try { dados = JSON.parse(texto); }
    catch { dados = null; }
  }
  if (!resposta.ok || (dados && dados.erro)) {
    const msg = (dados && dados.erro) || `${resposta.status} ${resposta.statusText}`;
    throw new ErroServidor(String(msg), resposta.status,
                           (dados && dados.detalhe) || texto.slice(0, 2000), rota);
  }
  return dados;
}

const postar = (rota, corpo) => pedir(rota, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  body: JSON.stringify(corpo),
});

export class Api {
  constructor(base = '') { this.base = base.replace(/\/$/, ''); }
  _r(caminho) { return this.base + caminho; }

  /** Perfis com dimensões (e seção pronta, quando `nucleo3d/geometria.py` existir). */
  catalogo() { return pedir(this._r('/api/modelo/catalogo')); }

  /** Malhas de um documento. `ids` limita o pedido ao que mudou. */
  malhas(documentoJSON, ids = null) {
    const corpo = { documento: documentoJSON };
    if (ids && ids.length) corpo.ids = ids;
    return postar(this._r('/api/modelo/malha'), corpo);
  }

  salvar(documentoJSON, nome) {
    return postar(this._r('/api/modelo/salvar'), { documento: documentoJSON, nome });
  }

  abrir(nome) { return pedir(this._r('/api/modelo/abrir/' + encodeURIComponent(nome))); }

  // ---- projeto: o modelo mora em <projeto>/modelo.json (ver sistema/projetos.py)
  projeto(slug) { return pedir(this._r('/api/projetos/' + encodeURIComponent(slug))); }

  modeloDoProjeto(slug) {
    return pedir(this._r('/api/projetos/' + encodeURIComponent(slug) + '/modelo'));
  }

  salvarModeloDoProjeto(slug, documentoJSON, baseAlterado = null) {
    return postar(this._r('/api/projetos/' + encodeURIComponent(slug) + '/modelo'),
                  { documento: documentoJSON, base_alterado: baseAlterado });
  }

  async importarIFCNoProjeto(slug, arquivo) {
    const conteudo_b64 = await paraBase64(arquivo);
    return postar(this._r('/api/projetos/' + encodeURIComponent(slug) + '/importar-ifc'),
                  { nome: arquivo.name, conteudo_b64 });
  }

  lista() { return pedir(this._r('/api/modelo/lista')); }

  exportarIFC(documentoJSON, nome, extras = {}) {
    return postar(this._r('/api/modelo/ifc/exportar'),
                  { documento: documentoJSON, nome, ...extras });
  }

  /** Lê o arquivo escolhido pelo usuário e manda em base64, como o servidor espera. */
  async importarIFC(arquivo) {
    const conteudo_b64 = await paraBase64(arquivo);
    return postar(this._r('/api/modelo/ifc/importar'),
                  { nome: arquivo.name, conteudo_b64 });
  }

  async inspecionarIFC(arquivo) {
    const conteudo_b64 = await paraBase64(arquivo);
    return postar(this._r('/api/modelo/ifc/inspecionar'),
                  { nome: arquivo.name, conteudo_b64 });
  }

  /** Detalhamento de peças para produção: o servidor devolve os links do DXF único,
   *  do romaneio e do relatório. Não mexe no documento aberto. */
  async detalharIFC(arquivo, projeto = null) {
    const conteudo_b64 = await paraBase64(arquivo);
    return postar(this._r('/api/modelo/ifc/detalhar'),
                  { nome: arquivo.name, conteudo_b64, projeto: projeto || undefined });
  }

  /** Dimensiona o galpão e devolve o modelo 3D correspondente. */
  doGalpao(dados) { return postar(this._r('/api/modelo/do-galpao'), { dados }); }

  /** Catálogo do sistema de cálculo — usado pelo diálogo "gerar do galpão". */
  catalogoCalculo() { return pedir(this._r('/api/catalogo')); }
}

/** Lê um File e devolve só a parte base64 (sem o prefixo data:). */
export function paraBase64(arquivo) {
  return new Promise((ok, falhou) => {
    const leitor = new FileReader();
    leitor.onerror = () => falhou(new ErroServidor('não foi possível ler o arquivo.'));
    leitor.onload = () => {
      const s = String(leitor.result || '');
      ok(s.slice(s.indexOf(',') + 1));
    };
    leitor.readAsDataURL(arquivo);
  });
}

export const api = new Api();
export default api;
