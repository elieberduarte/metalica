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

/** O arquivo como ele é, sem base64 nem JSON: o IFC de 321 MB do Bella Casa, em base64, passava do limite do servidor
 *  e o editor dizia "não foi possível falar com o servidor" (05/10). */
const enviarArquivo = (rota, arquivo, cabecalhos = {}) => pedir(rota, {
  method: 'POST',
  headers: { 'Content-Type': 'application/octet-stream', 'X-Nome-Arquivo': encodeURIComponent(arquivo.name), ...cabecalhos },
  body: arquivo,
});

export class Api {
  constructor(base = '') { this.base = base.replace(/\/$/, ''); }
  _r(caminho) { return this.base + caminho; }

  /** Perfis com dimensões (e seção pronta, quando `nucleo3d/geometria.py` existir). */
  catalogo() { return pedir(this._r('/api/modelo/catalogo')); }

  /** Seção e massa de perfis que o catálogo do editor não traz (dobrados de fábrica, barras redondas…). */
  perfis(nomes) { return postar(this._r('/api/modelo/perfis'), { nomes }); }
  /** Regras de apoio do modelo: peça voando, ponta de treliça sem apoio, terça em balanço… */
  apoios(documentoJSON, eixos) { return postar(this._r('/api/modelo/apoios'), { documento: documentoJSON, eixos: eixos || [] }); }
  analitico(documentoJSON) { return postar(this._r('/api/modelo/analitico'), { documento: documentoJSON }); }
  /** Marcas de posição e de conjunto (nucleo3d/producao.py): devolve as mudanças dos atributos, não grava. */
  numerar(documentoJSON, opcoes = {}) { return postar(this._r('/api/modelo/numerar'), { documento: documentoJSON, ...opcoes }); }
  /** Onde as peças do documento se encostam, com a perna mínima — o diálogo Soldar. */
  contatos(documentoJSON) { return postar(this._r('/api/modelo/contatos'), { documento: documentoJSON }); }
  /** Sólidos desenhados à mão → Chapa paramétrica (contorno, espessura e furos medidos da malha). */
  converterChapa(documentoJSON, ids) { return postar(this._r('/api/modelo/converter-chapa'), { documento: documentoJSON, ids }); }

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

  /** O servidor manda o modelo como está no disco; se não vier um JSON inteiro (arquivo emendado
   *  por gravações antigas), pede de novo pelo caminho completo, que conserta o arquivo. */
  async modeloDoProjeto(slug) {
    // ?cobertura=aberta|retraida na página (as fotos do resumo da obra, 19/10): o modelo com a cobertura retrátil nessa
    // situação, montado pelo servidor só para ver — essa página não grava (salvarModeloDoProjeto recusa)
    const cobertura = this._cobertura();
    if (cobertura) return pedir(this._r('/api/projetos/' + encodeURIComponent(slug) + '/modelo?cobertura=' + encodeURIComponent(cobertura)));
    const rota = this._r('/api/projetos/' + encodeURIComponent(slug) + '/modelo');
    const r = await pedir(rota);
    return r === null ? pedir(rota + '?completo=1') : r;
  }

  _cobertura() {
    try { return new URLSearchParams(location.search).get('cobertura') || ''; } catch { return ''; }
  }

  /** O documento vai como texto JSON e o servidor o grava como veio, sem ler e reescrever (no Bella
   *  Casa, 05/10, eram 200 MB por json.loads e json.dumps a cada gravação automática). */
  salvarModeloDoProjeto(slug, documentoJSON, baseAlterado = null) {
    if (this._cobertura()) return Promise.reject(new Error('o modelo da foto (cobertura em outra situação) não se grava'));
    const cab = { 'Content-Type': 'application/json; charset=utf-8', 'X-Modelo-Cru': '1' };
    if (baseAlterado !== null && baseAlterado !== undefined) cab['X-Base-Alterado'] = String(baseAlterado);
    if (documentoJSON && Array.isArray(documentoJSON.entidades)) cab['X-Entidades'] = String(documentoJSON.entidades.length);
    return pedir(this._r('/api/projetos/' + encodeURIComponent(slug) + '/modelo'),
                 { method: 'POST', headers: cab, body: JSON.stringify(documentoJSON) });
  }

  importarIFCNoProjeto(slug, arquivo) {
    return enviarArquivo(this._r('/api/projetos/' + encodeURIComponent(slug) + '/importar-ifc'), arquivo);
  }

  lista() { return pedir(this._r('/api/modelo/lista')); }

  exportarIFC(documentoJSON, nome, extras = {}) {
    return postar(this._r('/api/modelo/ifc/exportar'),
                  { documento: documentoJSON, nome, ...extras });
  }

  /** Manda o arquivo escolhido pelo usuário como ele é. */
  importarIFC(arquivo) {
    return enviarArquivo(this._r('/api/modelo/ifc/importar'), arquivo);
  }

  inspecionarIFC(arquivo) {
    return enviarArquivo(this._r('/api/modelo/ifc/inspecionar'), arquivo);
  }

  /** Detalhamento de peças para produção: o servidor devolve os links do DXF único,
   *  do romaneio e do relatório. Não mexe no documento aberto. */
  detalharIFC(arquivo, projeto = null) {
    return enviarArquivo(this._r('/api/modelo/ifc/detalhar'), arquivo, projeto ? { 'X-Projeto': encodeURIComponent(projeto) } : {});
  }

  /** Dimensiona o galpão e devolve o modelo 3D correspondente. */
  doGalpao(dados) { return postar(this._r('/api/modelo/do-galpao'), { dados }); }

  /** Cálculo estrutural do modelo importado (sólidos do IFC) do projeto. */
  calcularProjeto(s, corpo) {
    return postar(this._r(`/api/projetos/${encodeURIComponent(s)}/calcular`), corpo || {});
  }
  /** O perfil mais leve que passa em cada posição; com `aplicar`, troca no modelo do projeto. */
  dimensionarProjeto(s, corpo) {
    return postar(this._r(`/api/projetos/${encodeURIComponent(s)}/dimensionar`), corpo || {});
  }
  /** Último cálculo gravado no projeto ({calculo, parametros, quando}). */
  calculoDoProjeto(s) {
    return pedir(this._r(`/api/projetos/${encodeURIComponent(s)}/calculo`), { cache: 'no-store' });
  }
  /** Perfis do catálogo que podem substituir a peça, já verificados nos esforços dela. */
  alternativasDePerfil(s, marca, limite = 10) {
    return pedir(this._r(`/api/projetos/${encodeURIComponent(s)}/calculo/alternativas` +
                         `?marca=${encodeURIComponent(marca)}&limite=${limite}`), { cache: 'no-store' });
  }

  /** O que o diálogo de cálculo precisa saber do modelo (tesouras, vão, cota do apoio…). */
  geometriaParaCalculo(s) {
    return pedir(this._r(`/api/projetos/${encodeURIComponent(s)}/calculo/geometria`), { cache: 'no-store' });
  }

  /** Eixos da obra: gravados no projeto ou identificados do modelo. */
  eixosDoProjeto(s) { return pedir(this._r('/api/projetos/' + encodeURIComponent(s) + '/eixos')); }
  gravarEixos(s, corpo) { return postar(this._r('/api/projetos/' + encodeURIComponent(s) + '/eixos'), corpo); }
  /** Posições com canto redondo (barra calandrada) e as opções de quebra em retas. */
  cantosDoProjeto(s) { return pedir(this._r('/api/projetos/' + encodeURIComponent(s) + '/cantos')); }
  quebrarCantos(s, escolhas) { return postar(this._r('/api/projetos/' + encodeURIComponent(s) + '/cantos'), { escolhas }); }
  previaCanto(s, marca, n) { return pedir(this._r('/api/projetos/' + encodeURIComponent(s) + '/cantos/previa?marca=' + encodeURIComponent(marca) + '&n=' + (n || 0))); }
  desfazerCantos(s, marcas = null) { return postar(this._r('/api/projetos/' + encodeURIComponent(s) + '/cantos'), { desfazer: true, marcas }); }
  // multidobra no 3D (13/10): a telha do beiral reescrita com o raio comercial girando no vértice das retas
  multidobras3dDoProjeto(s) { return pedir(this._r('/api/projetos/' + encodeURIComponent(s) + '/multidobras-3d')); }
  ajustarMultidobras3d(s, corpo) { return postar(this._r('/api/projetos/' + encodeURIComponent(s) + '/multidobras-3d'), corpo || {}); }
}

export const api = new Api();
export default api;
