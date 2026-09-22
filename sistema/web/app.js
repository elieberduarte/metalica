/* ============================================================================
 * Interface do sistema de dimensionamento de galpões metálicos.
 * JavaScript puro, sem framework e sem CDN — funciona offline.
 *
 * Organização deste arquivo:
 *   1. utilidades          formatação, parsing, HTML seguro
 *   2. estado              dados do formulário, persistência em localStorage
 *   3. catálogo e campos   monta o formulário a partir de GET /api/catalogo
 *   4. validação           mesmas faixas de DadosGalpao.validar()
 *   5. desenho             seção transversal e elevação em SVG, ao vivo
 *   6. vento               prévia de S2, Vk e q (NBR 6123, Tabela 1)
 *   7. API                 chamadas ao servidor + modo de demonstração
 *   8. resultados          painel por elemento e memória de cálculo
 *   9. entrega             arquivos gerados e resumo
 *  10. navegação e início
 * ========================================================================= */

'use strict';

const PARAMS = new URLSearchParams(location.search);
const DEMO = PARAMS.has('demo') && PARAMS.get('demo') !== '0';
const CHAVE_ESTADO = 'galpao.estado.v1';
const ETAPAS = ['projeto', 'cargas', 'materiais', 'resultados', 'entrega'];

/* ------------------------------------------------------------ 1. utilidades */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));

function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, '');
    else n.setAttribute(k, v);
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return n;
}

/** Número no padrão brasileiro. */
function nf(x, casas = 2) {
  if (x === null || x === undefined || x === '' || !Number.isFinite(Number(x))) return '—';
  return Number(x).toLocaleString('pt-BR', {
    minimumFractionDigits: casas, maximumFractionDigits: casas,
  });
}

/** Texto "1.234,5 kg" com unidade opcional. */
function nu(x, casas, unidade) {
  const s = nf(x, casas);
  return unidade && s !== '—' ? `${s} ${unidade}` : s;
}

/** Converte texto do usuário em número (aceita vírgula decimal). */
function num(v) {
  if (typeof v === 'number') return v;
  if (v === null || v === undefined) return NaN;
  const s = String(v).trim().replace(/\s| /g, '').replace(',', '.');
  if (s === '') return NaN;
  const x = Number(s);
  return Number.isFinite(x) ? x : NaN;
}

const TAGS_PERMITIDAS = new Set(['SUB', 'SUP', 'B', 'I', 'EM', 'STRONG', 'BR', 'SPAN', 'SMALL']);

/** As fórmulas vêm em HTML simples do servidor; deixa passar só marcação de texto. */
function htmlSeguro(texto) {
  const modelo = document.createElement('template');
  modelo.innerHTML = String(texto === null || texto === undefined ? '' : texto);
  (function limpa(no) {
    for (const filho of Array.from(no.childNodes)) {
      if (filho.nodeType === Node.ELEMENT_NODE) {
        limpa(filho);
        if (!TAGS_PERMITIDAS.has(filho.tagName)) filho.replaceWith(...filho.childNodes);
        else for (const a of Array.from(filho.attributes)) filho.removeAttribute(a.name);
      } else if (filho.nodeType !== Node.TEXT_NODE) {
        filho.remove();
      }
    }
  })(modelo.content);
  return modelo.innerHTML;
}

function comHtml(tag, attrs, texto) {
  const n = el(tag, attrs);
  n.innerHTML = htmlSeguro(texto);
  return n;
}

/** Classe de cor pela razão de aproveitamento: 0,85 e 1,00 são os cortes. */
function nivel(razao) {
  if (!Number.isFinite(razao)) return 'nivel-dispensada';
  if (razao <= 0.85) return 'nivel-ok';
  if (razao <= 1.0001) return 'nivel-atencao';
  return 'nivel-reprova';
}

/* ---------------------------------------------------------------- 2. estado */

const estado = {
  catalogo: null,
  campos: [],          // descritores vindos do servidor
  dados: {},           // valores do formulário (texto para números, bool para checkbox)
  tipos: {},           // campo -> "float" | "int" | "str" | "bool"
  rotulos: {},
  projeto: null,       // última resposta de /api/dimensionar
  entrega: null,       // última resposta de /api/gerar
  erroCalculo: null,
  etapa: 'projeto',
};

function salvarLocal() {
  /* no modo de demonstração o formulário é do exemplo: não sobrescreve o rascunho real */
  if (DEMO) return;
  try {
    localStorage.setItem(CHAVE_ESTADO, JSON.stringify(estado.dados));
  } catch (e) {
    /* janela privativa ou armazenamento cheio: seguir sem persistir */
  }
}

function lerLocal() {
  try {
    const bruto = localStorage.getItem(CHAVE_ESTADO);
    return bruto ? JSON.parse(bruto) : null;
  } catch (e) {
    return null;
  }
}

function lerTema() {
  try { return localStorage.getItem('galpao.tema'); } catch (e) { return null; }
}

function gravarTema(t) {
  try { localStorage.setItem('galpao.tema', t); } catch (e) { /* ignora */ }
}

/* --------------------------------------------------- 3. catálogo e campos */

/* Configuração por campo: faixas iguais às de DadosGalpao.validar(), passo e dicas.
   `rotuloErro` repete o nome usado na mensagem do servidor, para a mensagem no
   cliente ser idêntica à que viria do back-end. */
const CONFIG = {
  nome: { largo: true },
  responsavel: { largo: true },
  local: { dica: 'cidade / UF da obra' },

  vao: { faixa: [5, 60], un: 'm', rotuloErro: 'Vão' },
  comprimento: { faixa: [5, 300], un: 'm', rotuloErro: 'Comprimento' },
  pe_direito: { faixa: [2.5, 20], un: 'm', rotuloErro: 'Pé-direito' },
  espacamento_porticos: { faixa: [3, 12], un: 'm', rotuloErro: 'Espaçamento entre pórticos' },
  inclinacao: { faixa: [2, 100], un: '%', rotuloErro: 'Inclinação do telhado' },
  balanco_lateral: { faixa: [0, 5], un: 'm', rotuloErro: 'Beiral lateral' },

  tipo_portico: { opcoes: ['alma cheia', 'treliçado'] },
  comprimento_misula: { faixa: [0, 6], un: 'm', rotuloErro: 'Comprimento da mísula' },
  altura_misula: { faixa: [0, 3], un: 'm', rotuloErro: 'Altura da mísula' },

  fck_MPa: { faixa: [15, 50], un: 'MPa', rotuloErro: 'fck do concreto', lista: 'fck' },

  espacamento_tercas: { faixa: [0.8, 3.0], un: 'm', rotuloErro: 'Espaçamento de terças' },
  linhas_correntes: { faixa: [0, 4], inteiro: true, rotuloErro: 'Linhas de correntes' },
  altura_fechamento: { faixa: [0, 20], un: 'm', rotuloErro: 'Altura do fechamento',
                       dica: '0 = até o pé-direito' },

  sobrecarga_cobertura: { faixa: [0, 5], un: 'kN/m²', rotuloErro: 'Sobrecarga de cobertura',
                          dica: 'NBR 8800: 0,25 kN/m² mínimo' },
  carga_forro: { faixa: [0, 5], un: 'kN/m²', rotuloErro: 'Forro' },
  carga_extra: { faixa: [0, 5], un: 'kN/m²', rotuloErro: 'Carga extra' },
  capacidade_ponte_t: { faixa: [0, 200], un: 't', rotuloErro: 'Capacidade da ponte',
                        depende: 'ponte_rolante' },

  v0: { faixa: [25, 55], un: 'm/s', rotuloErro: 'Velocidade básica do vento' },
  fator_topografico: { faixa: [0.9, 1.6], rotuloErro: 'S₁',
                       dica: '1,0 em terreno plano; 0,9 em vale profundo' },
  fator_estatistico: { faixa: [0.8, 1.2], rotuloErro: 'S₃', lista: 's3' },

  flecha_terca: { faixa: [100, 600], inteiro: true, prefixo: 'L /', rotuloErro: 'Flecha da terça' },
  flecha_viga: { faixa: [100, 600], inteiro: true, prefixo: 'L /', rotuloErro: 'Flecha da viga' },
  desloc_horizontal: { faixa: [100, 800], inteiro: true, prefixo: 'H /',
                       rotuloErro: 'Deslocamento do pilar' },
  custo_kg: { faixa: [1, 200], un: 'R$/kg', rotuloErro: 'Custo' },
};

/** Opções de select/datalist por campo, alimentadas pelo catálogo do servidor. */
function fonteOpcoes(campo) {
  const c = estado.catalogo || {};
  const cargas = (c.cargas && !c.cargas.erro) ? c.cargas : {};
  const acos = (c.acos || []).map(a => ({
    valor: a.nome, rotulo: `${a.nome} — f_y ${nf(a.fy, 1)} kN/cm²`,
  }));
  const cfg = CONFIG[campo];
  if (cfg && cfg.opcoes) {
    return { tipo: 'select', itens: cfg.opcoes.map(o => ({ valor: o, rotulo: o })) };
  }
  switch (campo) {
    case 'aco_perfis':
    case 'aco_chapas':
    case 'aco_tercas':
      return { tipo: 'select', itens: acos };
    case 'parafuso':
      return { tipo: 'select', itens: (c.parafusos || []).map(p => ({
        valor: p.nome, rotulo: `${p.nome} — f_ub ${nf(p.fub, 1)} kN/cm²`,
      })) };
    case 'eletrodo':
      return { tipo: 'select', itens: (c.eletrodos || []).map(e => ({
        valor: e.nome, rotulo: `${e.nome} — f_w ${nf(e.fw, 1)} kN/cm²`,
      })) };
    case 'categoria_rugosidade':
      return { tipo: 'select', itens: Object.entries(cargas.categorias_s2 || {})
        .map(([k, d]) => ({ valor: k, rotulo: `${k} — ${d}` })) };
    case 'classe':
      return { tipo: 'select', itens: Object.entries(cargas.classes_s2 || {})
        .map(([k, d]) => ({ valor: k, rotulo: `${k} — ${d}` })) };
    case 'aberturas':
      return { tipo: 'select', itens: Object.entries(cargas.aberturas || {})
        .map(([k, d]) => ({ valor: k, rotulo: d })) };
    case 'telha':
      return { tipo: 'datalist', itens: (cargas.pesos || [])
        .filter(p => /telha/i.test(p.nome))
        .map(p => ({ valor: p.nome, rotulo: `${nf(p.valor, 2)} kN/m²` })) };
    case 'fechamento_lateral':
      return { tipo: 'datalist', itens: [
        { valor: 'telha metálica' }, { valor: 'telha sanduíche' },
        { valor: 'alvenaria cerâmica 14 cm' }, { valor: 'alvenaria de bloco de concreto 14 cm' },
        { valor: 'sem fechamento' },
      ] };
    case 'cidade':
      return { tipo: 'datalist', itens: (cargas.cidades || [])
        .map(ci => ({ valor: ci.nome, rotulo: `V₀ = ${nf(ci.V0, 0)} m/s` })) };
    default:
      return null;
  }
}

function listaAuxiliar(nomeLista) {
  const c = estado.catalogo || {};
  const cargas = (c.cargas && !c.cargas.erro) ? c.cargas : {};
  if (nomeLista === 'fck') {
    return (c.concretos || []).map(x => ({ valor: String(x.fck_MPa), rotulo: x.nome }));
  }
  if (nomeLista === 's3') {
    return Object.entries(cargas.grupos_s3 || {}).map(([g, v]) => ({
      valor: String(v.S3), rotulo: `grupo ${g} — ${v.descricao}`,
    }));
  }
  return [];
}

/** Alinha o valor de `aberturas` com as chaves da tabela do servidor. */
function normalizarAberturas() {
  const cargas = (estado.catalogo && estado.catalogo.cargas) || {};
  const chaves = Object.keys(cargas.aberturas || {});
  if (!chaves.length) return;
  const atual = String(estado.dados.aberturas || '').toLowerCase();
  if (chaves.some(k => k.toLowerCase() === atual)) return;
  const achado = chaves.find(k => atual.startsWith(k.toLowerCase())
    || String(cargas.aberturas[k]).toLowerCase().startsWith(atual));
  estado.dados.aberturas = achado || chaves[0];
}

function montarFormulario() {
  for (const grupo of estado.campos) {
    const alvo = $(`.grade-campos[data-grupo="${grupo.grupo}"]`);
    if (!alvo) continue;
    alvo.textContent = '';
    for (const item of grupo.campos) alvo.append(montarCampo(item));
  }
}

function montarCampo(item) {
  const cfg = CONFIG[item.campo] || {};
  const id = 'c-' + item.campo;

  if (item.tipo === 'bool') {
    const entrada = el('input', { type: 'checkbox', id });
    entrada.checked = Boolean(estado.dados[item.campo]);
    entrada.addEventListener('change', () => {
      estado.dados[item.campo] = entrada.checked;
      aoMudarDados();
    });
    return el('div', { class: 'campo booleano', 'data-campo': item.campo },
      entrada, el('label', { for: id }, item.rotulo));
  }

  const opcoes = fonteOpcoes(item.campo);
  const caixa = el('div', {
    class: 'campo' + (cfg.largo ? ' largo' : '') + (item.tipo === 'str' ? '' : ' num'),
    'data-campo': item.campo,
  });
  caixa.append(el('label', { for: id }, item.rotulo));

  let entrada;
  if (opcoes && opcoes.tipo === 'select') {
    entrada = el('select', { id });
    const valorAtual = String(estado.dados[item.campo] ?? '');
    let achou = false;
    for (const o of opcoes.itens) {
      const op = el('option', { value: o.valor }, o.rotulo || o.valor);
      if (String(o.valor) === valorAtual) { op.selected = true; achou = true; }
      entrada.append(op);
    }
    if (!achou && valorAtual) {
      const op = el('option', { value: valorAtual, selected: true }, valorAtual);
      entrada.prepend(op);
    }
  } else {
    entrada = el('input', {
      type: 'text',
      id,
      inputmode: item.tipo === 'str' ? null : 'decimal',
      autocomplete: 'off',
      spellcheck: 'false',
    });
    entrada.value = estado.dados[item.campo] ?? '';
    const itens = opcoes && opcoes.tipo === 'datalist'
      ? opcoes.itens : (cfg.lista ? listaAuxiliar(cfg.lista) : null);
    if (itens && itens.length) {
      const dl = el('datalist', { id: id + '-lista' });
      for (const o of itens) dl.append(el('option', { value: o.valor }, o.rotulo || ''));
      entrada.setAttribute('list', dl.id);
      caixa.append(dl);
    }
  }

  const evento = entrada.tagName === 'SELECT' ? 'change' : 'input';
  entrada.addEventListener(evento, () => {
    estado.dados[item.campo] = entrada.value;
    if (item.campo === 'cidade') aplicarCidade(entrada.value);
    aoMudarDados();
  });

  if (cfg.prefixo) {
    const linha = el('div', { class: 'prefixo-flecha' }, el('span', {}, cfg.prefixo), entrada);
    caixa.append(linha);
  } else {
    caixa.append(entrada);
  }

  caixa.append(el('div', { class: 'msg-erro', 'data-erro': item.campo }));
  if (cfg.dica) caixa.append(el('div', { class: 'dica' }, cfg.dica));
  return caixa;
}

/** Ao escolher uma cidade da tabela, traz o V₀ correspondente. */
function aplicarCidade(nomeCidade) {
  const cargas = (estado.catalogo && estado.catalogo.cargas) || {};
  const alvo = String(nomeCidade || '').trim().toLowerCase();
  const achado = (cargas.cidades || []).find(c => c.nome.toLowerCase() === alvo);
  if (!achado) return;
  estado.dados.v0 = String(achado.V0);
  const campoV0 = $('#c-v0');
  if (campoV0) campoV0.value = estado.dados.v0;
  recado('V₀ da tabela', `${achado.nome}: V₀ = ${nf(achado.V0, 0)} m/s. `
    + 'Confira o mapa de isopletas da NBR 6123 vigente.', 'ok');
}

/** Desabilita os campos que só fazem sentido com a opção-mãe ligada. */
function aplicarDependencias() {
  for (const [campo, cfg] of Object.entries(CONFIG)) {
    if (!cfg.depende) continue;
    const ctrl = document.getElementById('c-' + campo);
    if (ctrl) ctrl.disabled = !estado.dados[cfg.depende];
  }
  for (const campo of ['comprimento_misula', 'altura_misula']) {
    const ctrl = document.getElementById('c-' + campo);
    if (ctrl) ctrl.disabled = !estado.dados.com_misula;
  }
}

/** Espelha estado.dados nos controles já montados (ao carregar um projeto salvo). */
function refletirNosCampos() {
  for (const grupo of estado.campos) {
    for (const item of grupo.campos) {
      const ctrl = document.getElementById('c-' + item.campo);
      if (!ctrl) continue;
      if (ctrl.type === 'checkbox') ctrl.checked = Boolean(estado.dados[item.campo]);
      else ctrl.value = estado.dados[item.campo] ?? '';
    }
  }
}

/* ------------------------------------------------------------ 4. validação */

/** Mesmas faixas de DadosGalpao.validar(); devolve {campo: mensagem}. */
function validar() {
  const erros = {};
  const d = estado.dados;

  for (const [campo, cfg] of Object.entries(CONFIG)) {
    if (!cfg.faixa) continue;
    if (estado.tipos[campo] !== 'float' && estado.tipos[campo] !== 'int') continue;
    if (cfg.depende && !d[cfg.depende]) continue;
    const v = num(d[campo]);
    const [minimo, maximo] = cfg.faixa;
    const nome = cfg.rotuloErro || estado.rotulos[campo] || campo;
    if (!Number.isFinite(v)) {
      erros[campo] = `${nome}: informe um número.`;
    } else if (v < minimo || v > maximo) {
      erros[campo] = `${nome}: valor ${nf(v, 2)} fora da faixa aceitável `
        + `(${nf(minimo, minimo % 1 ? 1 : 0)} a ${nf(maximo, maximo % 1 ? 1 : 0)}`
        + `${cfg.un ? ' ' + cfg.un : ''}).`;
    } else if (cfg.inteiro && Math.abs(v - Math.round(v)) > 1e-9) {
      erros[campo] = `${nome}: use um número inteiro.`;
    }
  }

  if (!['I', 'II', 'III', 'IV', 'V'].includes(String(d.categoria_rugosidade))) {
    erros.categoria_rugosidade = 'Categoria de rugosidade deve ser I, II, III, IV ou V.';
  }
  if (!['A', 'B', 'C'].includes(String(d.classe))) {
    erros.classe = 'Classe da edificação deve ser A, B ou C.';
  }
  const comp = num(d.comprimento);
  const esp = num(d.espacamento_porticos);
  if (Number.isFinite(comp) && Number.isFinite(esp) && comp < esp) {
    erros.comprimento = 'O comprimento do galpão é menor que o espaçamento entre pórticos.';
  }
  if (!String(d.nome || '').trim()) {
    erros.nome = 'Dê um nome ao projeto: ele nomeia a pasta dos arquivos gerados.';
  }
  return erros;
}

function mostrarErros(erros) {
  for (const caixa of $$('.campo[data-campo]')) {
    const campo = caixa.dataset.campo;
    const msg = erros[campo];
    caixa.classList.toggle('erro', Boolean(msg));
    const alvo = $(`[data-erro="${campo}"]`, caixa);
    if (alvo) alvo.textContent = msg || '';
  }
}

/** Marca cada etapa do menu com o seu estado atual. */
function atualizarSinais(erros) {
  const porEtapa = {
    projeto: ['identificacao', 'geometria', 'sistema'],
    cargas: ['cobertura', 'cargas', 'vento'],
    materiais: ['materiais', 'criterios'],
  };
  for (const [etapa, grupos] of Object.entries(porEtapa)) {
    const campos = estado.campos.filter(g => grupos.includes(g.grupo))
      .flatMap(g => g.campos.map(c => c.campo));
    const n = campos.filter(c => erros[c]).length;
    const sinal = $(`[data-sinal="${etapa}"]`);
    if (!sinal) continue;
    sinal.className = 'sinal ' + (n ? 'nok' : 'ok');
    sinal.textContent = n ? `${n} campo${n > 1 ? 's' : ''} a corrigir` : 'preenchido';
  }
  const sr = $('[data-sinal="resultados"]');
  if (sr) {
    if (estado.projeto) {
      sr.className = 'sinal ' + (estado.projeto.ok ? 'ok' : 'nok');
      sr.textContent = estado.projeto.ok ? 'todas as verificações passam' : 'há verificação reprovada';
    } else {
      sr.className = 'sinal pend';
      sr.textContent = estado.erroCalculo ? 'cálculo indisponível' : 'não calculado';
    }
  }
  const se = $('[data-sinal="entrega"]');
  if (se) {
    const n = estado.entrega && estado.entrega.arquivos ? estado.entrega.arquivos.length : 0;
    se.className = 'sinal ' + (n ? 'ok' : 'pend');
    se.textContent = n ? `${n} arquivo${n > 1 ? 's' : ''}` : 'nada gerado';
  }
}

/* -------------------------------------------------------------- 5. desenho */

/** Geometria derivada, nas mesmas fórmulas de DadosGalpao. */
function geometria() {
  const d = estado.dados;
  const vao = num(d.vao);
  const pe = num(d.pe_direito);
  const incl = num(d.inclinacao);
  const bal = Number.isFinite(num(d.balanco_lateral)) ? num(d.balanco_lateral) : 0;
  if (!(vao > 0) || !(pe > 0) || !(incl > 0)) return null;
  const tg = incl / 100;
  return {
    vao, pe, incl, bal, tg,
    angulo: Math.atan(tg) * 180 / Math.PI,
    cumeeira: pe + (vao / 2) * tg,
    comprimentoAgua: (vao / 2) / Math.cos(Math.atan(tg)),
    comprimento: num(d.comprimento),
    espacamento: num(d.espacamento_porticos),
    espTercas: num(d.espacamento_tercas),
    nPorticos: Math.round(num(d.comprimento) / num(d.espacamento_porticos)) + 1,
    misula: d.com_misula ? (num(d.comprimento_misula) || 0) : 0,
    alturaMisula: d.com_misula ? (num(d.altura_misula) || 0) : 0,
  };
}

const SVGNS = 'http://www.w3.org/2000/svg';

function s(tag, attrs = {}, texto) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    n.setAttribute(k, String(v));
  }
  if (texto !== undefined) n.textContent = texto;
  return n;
}

/** Cota linear com traços inclinados nas extremidades (padrão de desenho técnico). */
function cota(x1, y1, x2, y2, texto, ladoTexto = 'cima') {
  const g = s('g');
  g.append(s('line', { x1, y1, x2, y2, class: 'd-cota' }));
  const horizontal = Math.abs(y2 - y1) < 0.5;
  const dx = horizontal ? 3 : 4, dy = horizontal ? 4 : 3;
  for (const [x, y] of [[x1, y1], [x2, y2]]) {
    g.append(s('line', { x1: x - dx, y1: y + dy, x2: x + dx, y2: y - dy, class: 'd-cota' }));
  }
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  if (horizontal) {
    const t = s('text', {
      x: mx, y: ladoTexto === 'cima' ? my - 5 : my + 13,
      'text-anchor': 'middle', class: 'd-texto forte',
    }, texto);
    g.append(t);
  } else {
    const t = s('text', {
      x: mx, y: my, 'text-anchor': 'middle', class: 'd-texto forte',
      transform: `rotate(-90 ${mx} ${my})`, dy: -5,
    }, texto);
    g.append(t);
  }
  return g;
}

function svgVazio(mensagem, largura = 660, altura = 300) {
  const svg = s('svg', { viewBox: `0 0 ${largura} ${altura}`, role: 'img' });
  svg.append(s('rect', {
    x: 12, y: 12, width: largura - 24, height: altura - 24, rx: 6,
    fill: 'none', stroke: 'var(--borda-forte)', 'stroke-dasharray': '6 5',
  }));
  svg.append(s('text', {
    x: largura / 2, y: altura / 2, 'text-anchor': 'middle', class: 'd-texto',
  }, mensagem));
  return svg;
}

function desenharSecao() {
  const alvo = $('#svg-secao');
  if (!alvo) return;
  alvo.textContent = '';
  const g = geometria();
  if (!g) {
    alvo.append(svgVazio('Informe vão, pé-direito e inclinação para ver o desenho.'));
    atualizarCotasResumo(null);
    return;
  }

  const W = 660;
  const pad = { l: 74, r: 80, t: 30, b: 64 };
  const xMin = -g.bal, xMax = g.vao + g.bal;
  const modeloL = Math.max(xMax - xMin, 0.001);
  const modeloA = Math.max(g.cumeeira, 0.001);
  /* a escala segue a largura disponível; a altura da figura se ajusta ao desenho,
     com um teto para galpões estreitos e altos não estourarem o painel */
  const ALTURA_MAX = 215;
  const escala = Math.min((W - pad.l - pad.r) / modeloL, ALTURA_MAX / modeloA);
  const H = Math.round(pad.t + pad.b + modeloA * escala);
  const larguraDesenho = modeloL * escala;
  const ox = pad.l + Math.max(0, (W - pad.l - pad.r - larguraDesenho) / 2);
  const X = x => ox + (x - xMin) * escala;
  const Y = y => H - pad.b - y * escala;

  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.append(s('title', {}, 'Seção transversal do pórtico com as cotas principais'));

  /* --- terreno --- */
  const y0 = Y(0);
  svg.append(s('line', { x1: X(xMin) - 26, y1: y0, x2: X(xMax) + 26, y2: y0, class: 'd-chao' }));
  for (let x = X(xMin) - 24; x < X(xMax) + 26; x += 11) {
    svg.append(s('line', { x1: x, y1: y0, x2: x - 7, y2: y0 + 7, class: 'd-hachura' }));
  }

  /* --- eixo de simetria --- */
  svg.append(s('line', {
    x1: X(g.vao / 2), y1: Y(g.cumeeira) - 16, x2: X(g.vao / 2), y2: y0 + 12, class: 'd-eixo',
  }));

  /* --- beirais --- */
  if (g.bal > 0) {
    const yb = g.pe - g.bal * g.tg;
    svg.append(s('line', {
      x1: X(-g.bal), y1: Y(yb), x2: X(0), y2: Y(g.pe), class: 'd-aco',
      'stroke-width': 3.5,
    }));
    svg.append(s('line', {
      x1: X(g.vao + g.bal), y1: Y(yb), x2: X(g.vao), y2: Y(g.pe), class: 'd-aco',
      'stroke-width': 3.5,
    }));
  }

  /* --- vigas (águas) --- */
  for (const [x1, x2] of [[0, g.vao / 2], [g.vao, g.vao / 2]]) {
    svg.append(s('line', {
      x1: X(x1), y1: Y(g.pe), x2: X(x2), y2: Y(g.cumeeira), class: 'd-aco', 'stroke-width': 6,
    }));
  }

  /* --- terças sobre as águas --- */
  if (g.espTercas > 0.3) {
    const nTercas = Math.max(1, Math.round(g.comprimentoAgua / g.espTercas));
    for (let i = 0; i <= nTercas; i++) {
      const f = i / nTercas;
      for (const sentido of [1, -1]) {
        const x = sentido > 0 ? f * g.vao / 2 : g.vao - f * g.vao / 2;
        const y = g.pe + Math.abs(x - 0) * 0;
        const yy = g.pe + (sentido > 0 ? x : g.vao - x) * g.tg;
        svg.append(s('rect', {
          x: X(x) - 2.6, y: Y(yy) - 7.5, width: 5.2, height: 5.2, class: 'd-terca',
          transform: `rotate(${sentido > 0 ? -g.angulo : g.angulo} ${X(x)} ${Y(yy)})`,
        }));
        void y;
      }
    }
  }

  /* --- mísulas --- */
  if (g.misula > 0) {
    const hm = g.alturaMisula > 0 ? g.alturaMisula : Math.max(0.35, g.misula * 0.28);
    for (const lado of [0, 1]) {
      const xj = lado ? g.vao : 0;
      const sentido = lado ? -1 : 1;
      const xf = xj + sentido * g.misula;
      const yf = g.pe + g.misula * g.tg;
      const pts = [
        [X(xj), Y(g.pe)], [X(xf), Y(yf)], [X(xf), Y(yf - hm * 0.25)], [X(xj), Y(g.pe - hm)],
      ];
      svg.append(s('polygon', { points: pts.map(p => p.join(',')).join(' '), class: 'd-misula' }));
    }
  }

  /* --- pilares --- */
  const larguraPilar = 7;
  for (const x of [0, g.vao]) {
    svg.append(s('rect', {
      x: X(x) - larguraPilar / 2, y: Y(g.pe), width: larguraPilar, height: y0 - Y(g.pe),
      fill: 'var(--azul)', stroke: 'var(--azul)', 'stroke-width': 1,
    }));
    /* placa de base */
    svg.append(s('line', {
      x1: X(x) - 11, y1: y0, x2: X(x) + 11, y2: y0, class: 'd-aco', 'stroke-width': 3.5,
    }));
  }

  /* --- cotas --- */
  svg.append(cota(X(0), y0 + 30, X(g.vao), y0 + 30, `vão ${nf(g.vao, 2)} m`, 'baixo'));
  if (g.bal > 0) {
    svg.append(cota(X(xMin), y0 + 30, X(0), y0 + 30, `${nf(g.bal, 2)}`, 'baixo'));
    svg.append(cota(X(g.vao), y0 + 30, X(xMax), y0 + 30, `${nf(g.bal, 2)}`, 'baixo'));
  }
  const xEsq = X(xMin) - 34;
  svg.append(s('line', { x1: xEsq - 6, y1: Y(g.pe), x2: X(0), y2: Y(g.pe), class: 'd-aux' }));
  svg.append(cota(xEsq, y0, xEsq, Y(g.pe), `pé-direito ${nf(g.pe, 2)} m`));

  const xDir = X(xMax) + 38;
  svg.append(s('line', {
    x1: X(g.vao / 2), y1: Y(g.cumeeira), x2: xDir + 6, y2: Y(g.cumeeira), class: 'd-aux',
  }));
  svg.append(cota(xDir, y0, xDir, Y(g.cumeeira), `cumeeira ${nf(g.cumeeira, 2)} m`));

  /* --- inclinação: triângulo indicador sobre a água esquerda --- */
  const xa = g.vao * 0.10, xb = g.vao * 0.26;
  const ya = g.pe + xa * g.tg, yb = g.pe + xb * g.tg;
  svg.append(s('polyline', {
    points: `${X(xa)},${Y(ya) - 10} ${X(xb)},${Y(ya) - 10} ${X(xb)},${Y(yb) - 10}`,
    class: 'd-cota',
  }));
  svg.append(s('text', {
    x: X((xa + xb) / 2), y: Y(ya) - 15, 'text-anchor': 'middle', class: 'd-texto forte',
  }, `${nf(g.incl, 1)} % (${nf(g.angulo, 1)}°)`));

  /* --- rótulos --- */
  svg.append(s('text', {
    x: X(0) - 12, y: Y(g.pe / 2), class: 'd-texto', 'text-anchor': 'end',
  }, 'pilar'));
  svg.append(s('text', {
    x: X(g.vao * 0.74), y: Y(g.pe + g.vao * 0.26 * g.tg) - 14, class: 'd-texto',
  }, 'viga do pórtico'));
  if (g.misula > 0) {
    svg.append(s('text', {
      x: X(g.vao) + 8, y: Y(g.pe) + 17, class: 'd-texto',
    }, `mísula ${nf(g.misula, 2)} m`));
  }
  svg.append(s('text', {
    x: X(g.vao / 2), y: Y(g.cumeeira) - 13, 'text-anchor': 'middle', class: 'd-texto',
  }, 'cumeeira'));

  alvo.append(svg);
  atualizarCotasResumo(g);
}

function atualizarCotasResumo(g) {
  const alvo = $('#cotas-resumo');
  if (!alvo) return;
  alvo.textContent = '';
  if (!g) return;
  const itens = [
    ['Altura da cumeeira', nu(g.cumeeira, 2, 'm')],
    ['Ângulo do telhado', nu(g.angulo, 1, '°')],
    ['Comprimento da água', nu(g.comprimentoAgua, 2, 'm')],
    ['Pórticos', Number.isFinite(g.nPorticos) ? String(g.nPorticos) : '—'],
    ['Área coberta', nu(g.vao * g.comprimento, 0, 'm²')],
  ];
  for (const [t, v] of itens) {
    alvo.append(el('div', {}, el('dt', {}, t), el('dd', {}, v)));
  }
}

function desenharLongitudinal() {
  const alvo = $('#svg-longitudinal');
  if (!alvo) return;
  alvo.textContent = '';
  const g = geometria();
  if (!g || !(g.comprimento > 0) || !(g.espacamento > 0)) {
    alvo.append(svgVazio('Informe comprimento e espaçamento entre pórticos.', 660, 170));
    return;
  }

  const W = 660;
  const pad = { l: 46, r: 46, t: 20, b: 66 };
  const escala = Math.min((W - pad.l - pad.r) / g.comprimento,
                          110 / Math.max(g.cumeeira, 0.001));
  const H = Math.round(pad.t + pad.b + Math.max(g.cumeeira, 0.001) * escala);
  const X = x => pad.l + x * escala;
  const Y = y => H - pad.b - y * escala;
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' });
  svg.append(s('title', {}, 'Elevação longitudinal com o espaçamento entre pórticos'));

  const y0 = Y(0);
  svg.append(s('line', { x1: X(0) - 22, y1: y0, x2: X(g.comprimento) + 22, y2: y0, class: 'd-chao' }));
  for (let x = X(0) - 20; x < X(g.comprimento) + 22; x += 11) {
    svg.append(s('line', { x1: x, y1: y0, x2: x - 7, y2: y0 + 7, class: 'd-hachura' }));
  }

  /* silhueta: platibanda na altura do pé-direito e linha de cumeeira ao fundo */
  svg.append(s('line', {
    x1: X(0), y1: Y(g.cumeeira), x2: X(g.comprimento), y2: Y(g.cumeeira),
    class: 'd-aco-leve', 'stroke-dasharray': '7 4',
  }));
  svg.append(s('line', { x1: X(0), y1: Y(g.pe), x2: X(g.comprimento), y2: Y(g.pe), class: 'd-aco', 'stroke-width': 3 }));

  const n = Math.max(2, Math.min(g.nPorticos, 80));
  const passo = g.comprimento / (n - 1);
  for (let i = 0; i < n; i++) {
    const x = i * passo;
    svg.append(s('line', {
      x1: X(x), y1: y0, x2: X(x), y2: Y(g.pe), class: 'd-aco',
      'stroke-width': (i === 0 || i === n - 1) ? 5 : 3,
    }));
  }
  /* contraventamento no primeiro vão */
  if (n > 2) {
    svg.append(s('line', { x1: X(0), y1: y0, x2: X(passo), y2: Y(g.pe), class: 'd-aux' }));
    svg.append(s('line', { x1: X(passo), y1: y0, x2: X(0), y2: Y(g.pe), class: 'd-aux' }));
  }

  svg.append(cota(X(0), y0 + 28, X(passo), y0 + 28, `${nf(passo, 2)} m`, 'baixo'));
  svg.append(cota(X(0), y0 + 50, X(g.comprimento), y0 + 50,
    `comprimento ${nf(g.comprimento, 2)} m — ${n} pórticos`, 'baixo'));

  alvo.append(svg);
}

/* ---------------------------------------------------------------- 6. vento */

/* NBR 6123, Tabela 1 — parâmetros b e p de S₂ = b·F_r·(z/10)^p.
   Repetidos aqui só para a prévia na tela; o cálculo que vale é o do servidor
   (nucleo/cargas.py), que é a fonte destes mesmos valores. */
const PARAM_S2 = {
  'I|A': [1.10, 0.06], 'I|B': [1.11, 0.065], 'I|C': [1.12, 0.07],
  'II|A': [1.00, 0.085], 'II|B': [1.00, 0.09], 'II|C': [1.00, 0.10],
  'III|A': [0.94, 0.10], 'III|B': [0.94, 0.105], 'III|C': [0.93, 0.115],
  'IV|A': [0.86, 0.12], 'IV|B': [0.85, 0.125], 'IV|C': [0.84, 0.135],
  'V|A': [0.74, 0.15], 'V|B': [0.73, 0.16], 'V|C': [0.71, 0.175],
};
const FR_S2 = { A: 1.00, B: 0.98, C: 0.95 };
const ZG_S2 = { I: 250, II: 300, III: 350, IV: 420, V: 500 };

function previaVento() {
  const d = estado.dados;
  const g = geometria();
  const cat = String(d.categoria_rugosidade || '');
  const cl = String(d.classe || '');
  const V0 = num(d.v0), S1 = num(d.fator_topografico), S3 = num(d.fator_estatistico);
  const chave = `${cat}|${cl}`;
  if (!g || !PARAM_S2[chave] || !Number.isFinite(V0) || !Number.isFinite(S1) || !Number.isFinite(S3)) {
    return { erro: 'Preencha a geometria e os parâmetros do vento para ver S₂, V_k e q.' };
  }
  const z = g.cumeeira;
  if (z > ZG_S2[cat]) {
    return { erro: `z = ${nf(z, 1)} m acima da altura gradiente da categoria ${cat}.` };
  }
  const [b, p] = PARAM_S2[chave];
  const fr = FR_S2[cl];
  const zCalc = Math.max(z, 5);
  const S2 = b * fr * Math.pow(zCalc / 10, p);
  const Vk = V0 * S1 * S2 * S3;
  const q = 0.613 * Vk * Vk / 1000;
  return { z, b, p, fr, S1, S2, S3, V0, Vk, q, cat, cl };
}

function renderVento() {
  const ctx = $('#vento-contexto');
  const grade = $('#vento-fatores');
  const erroBox = $('#vento-erro');
  const contas = $('#vento-contas');
  if (!grade) return;
  grade.textContent = '';
  erroBox.textContent = '';
  contas.textContent = '';
  const v = previaVento();
  if (v.erro) {
    ctx.textContent = '';
    erroBox.append(el('div', { class: 'aviso-caixa info' },
      el('div', { class: 'tit' }, 'Faltam dados'), el('div', {}, v.erro)));
    return;
  }
  ctx.innerHTML = htmlSeguro(
    `Altura de referência z = <b>${nf(v.z, 2)} m</b> (cumeeira), categoria ${v.cat}, `
    + `classe ${v.cl}. Prévia pela Tabela 1 da NBR 6123 — o cálculo definitivo, com `
    + `C<sub>e</sub> e C<sub>pi</sub> por região do telhado, é feito no servidor.`);

  const itens = [
    ['V₀', nf(v.V0, 0), 'm/s', 'isopletas'],
    ['S₁', nf(v.S1, 2), '', 'topografia'],
    ['S₂', nf(v.S2, 3), '', 'rugosidade'],
    ['S₃', nf(v.S3, 2), '', 'estatístico'],
    ['V_k', nf(v.Vk, 1), 'm/s', 'característica'],
    ['q', nf(v.q, 3), 'kN/m²', 'dinâmica'],
  ];
  for (const [t, valor, un, legenda] of itens) {
    grade.append(el('div', { class: 'fator' },
      el('dt', {}, t),
      el('dd', {}, valor, un ? el('span', { class: 'un' }, ' ' + un) : null),
      el('div', { class: 'formula' }, legenda)));
  }

  const caixa = el('div', { class: 'contas-vento' });
  for (const linha of [
    `S₂ = b·F_r·(z/10)^p = ${nf(v.b, 2)} · ${nf(v.fr, 2)} · (${nf(Math.max(v.z, 5), 1)}/10)^${nf(v.p, 3)} = ${nf(v.S2, 3)}`,
    `V_k = V₀·S₁·S₂·S₃ = ${nf(v.V0, 0)} · ${nf(v.S1, 2)} · ${nf(v.S2, 3)} · ${nf(v.S3, 2)} = ${nf(v.Vk, 1)} m/s`,
    `q = 0,613·V_k² = 0,613 · ${nf(v.Vk, 1)}² = ${nf(v.q, 3)} kN/m²`,
  ]) caixa.append(el('div', {}, linha));
  contas.append(caixa);
}

function renderTabelaCargas() {
  const tab = $('#tab-cargas');
  if (!tab) return;
  tab.textContent = '';
  const cargas = (estado.catalogo && estado.catalogo.cargas) || {};
  const pesos = cargas.pesos || [];
  const acha = nome => pesos.find(p => p.nome.toLowerCase() === String(nome || '').toLowerCase());

  const telha = acha(estado.dados.telha);
  const tercas = acha('terças');
  const contra = acha('contraventamentos e acessórios');
  const linhas = [
    ['Telha — ' + (estado.dados.telha || '—'), telha ? telha.valor : null,
      telha ? telha.obs : 'não está na tabela: o servidor usa o valor de catálogo'],
    ['Terças', tercas ? tercas.valor : 0.05, tercas ? tercas.obs : ''],
    ['Contraventamentos e acessórios', contra ? contra.valor : 0.05, contra ? contra.obs : ''],
    ['Forro', num(estado.dados.carga_forro) || 0, ''],
    ['Carga extra', num(estado.dados.carga_extra) || 0, 'equipamentos, iluminação'],
  ];
  const permanente = linhas.reduce((a, l) => a + (Number(l[1]) || 0), 0);
  const sobrecarga = num(estado.dados.sobrecarga_cobertura) || 0;

  tab.append(el('caption', {}, 'Estimativa por metro quadrado de projeção horizontal'));
  tab.append(el('thead', {}, el('tr', {},
    el('th', {}, 'Parcela'), el('th', { class: 'n' }, 'kN/m²'), el('th', {}, 'Observação'))));
  const corpo = el('tbody');
  for (const [nome, valor, obs] of linhas) {
    corpo.append(el('tr', {},
      el('td', {}, nome),
      el('td', { class: 'n' }, valor === null ? '—' : nf(valor, 3)),
      el('td', {}, obs || '')));
  }
  corpo.append(el('tr', {},
    el('td', {}, el('b', {}, 'Permanente (g)')),
    el('td', { class: 'n' }, el('b', {}, nf(permanente, 3))),
    el('td', {}, 'NBR 6120')));
  corpo.append(el('tr', {},
    el('td', {}, el('b', {}, 'Sobrecarga (q)')),
    el('td', { class: 'n' }, el('b', {}, nf(sobrecarga, 3))),
    el('td', {}, 'NBR 8800, item B.5.2')));
  tab.append(corpo);
}

function renderTabelaMateriais() {
  const tab = $('#tab-materiais');
  if (!tab) return;
  tab.textContent = '';
  const c = estado.catalogo || {};
  const aco = n => (c.acos || []).find(a => a.nome === n);
  const linhas = [];
  for (const [rotulo, campo] of [['Perfis', 'aco_perfis'], ['Terças', 'aco_tercas'],
                                 ['Chapas', 'aco_chapas']]) {
    const a = aco(estado.dados[campo]);
    linhas.push([rotulo, estado.dados[campo] || '—',
      a ? `f_y = ${nf(a.fy, 1)} kN/cm²` : '—',
      a ? `f_u = ${nf(a.fu, 1)} kN/cm²` : '—']);
  }
  const pf = (c.parafusos || []).find(p => p.nome === estado.dados.parafuso);
  linhas.push(['Parafusos', estado.dados.parafuso || '—',
    pf ? `f_ub = ${nf(pf.fub, 1)} kN/cm²` : '—', pf ? `grupo ${pf.grupo}` : '—']);
  const ele = (c.eletrodos || []).find(e => e.nome === estado.dados.eletrodo);
  linhas.push(['Solda', estado.dados.eletrodo || '—',
    ele ? `f_w = ${nf(ele.fw, 1)} kN/cm²` : '—', 'γ_w2 = 1,35']);
  const fck = num(estado.dados.fck_MPa);
  linhas.push(['Concreto da base', Number.isFinite(fck) ? `C${nf(fck, 0)}` : '—',
    Number.isFinite(fck) ? `f_ck = ${nf(fck / 10, 2)} kN/cm²` : '—',
    Number.isFinite(fck) ? `f_cd = ${nf(fck / 10 / 1.4, 3)} kN/cm²` : '—']);

  tab.append(el('thead', {}, el('tr', {},
    el('th', {}, 'Uso'), el('th', {}, 'Material'), el('th', {}, 'Escoamento'), el('th', {}, 'Ruptura'))));
  const corpo = el('tbody');
  for (const l of linhas) corpo.append(el('tr', {}, ...l.map(x => el('td', {}, x))));
  tab.append(corpo);
}

function renderTabelaCriterios() {
  const tab = $('#tab-criterios');
  if (!tab) return;
  tab.textContent = '';
  const g = geometria();
  const d = estado.dados;
  const linhas = [
    ['Terça', `L / ${d.flecha_terca}`, g ? g.espacamento : NaN,
      g ? (g.espacamento * 100) / num(d.flecha_terca) : NaN],
    ['Viga do pórtico', `L / ${d.flecha_viga}`, g ? g.comprimentoAgua : NaN,
      g ? (g.comprimentoAgua * 100) / num(d.flecha_viga) : NaN],
    ['Pilar (topo)', `H / ${d.desloc_horizontal}`, g ? g.pe : NaN,
      g ? (g.pe * 100) / num(d.desloc_horizontal) : NaN],
  ];
  tab.append(el('caption', {}, 'NBR 8800, Anexo C — Tabela C.1'));
  tab.append(el('thead', {}, el('tr', {},
    el('th', {}, 'Elemento'), el('th', {}, 'Critério'),
    el('th', { class: 'n' }, 'Vão / altura'), el('th', { class: 'n' }, 'Limite'))));
  const corpo = el('tbody');
  for (const [nome, crit, vao, lim] of linhas) {
    corpo.append(el('tr', {},
      el('td', {}, nome), el('td', {}, crit),
      el('td', { class: 'n' }, Number.isFinite(vao) ? nu(vao, 2, 'm') : '—'),
      el('td', { class: 'n' }, Number.isFinite(lim) ? nu(lim, 2, 'cm') : '—')));
  }
  tab.append(corpo);
}

/* ------------------------------------------------------------------ 7. API */

let pendentes = 0;

function carregando(ligado, texto) {
  pendentes = Math.max(0, pendentes + (ligado ? 1 : -1));
  const caixa = $('#carregando');
  if (texto) $('#carregando-texto').textContent = texto;
  caixa.hidden = pendentes === 0;
}

class ErroApi extends Error {
  constructor(mensagem, status, detalhe) {
    super(mensagem);
    this.status = status;
    this.detalhe = detalhe || '';
  }
}

async function api(rota, opcoes = {}) {
  let resposta;
  try {
    resposta = await fetch(rota, {
      ...opcoes,
      headers: opcoes.body ? { 'Content-Type': 'application/json' } : undefined,
    });
  } catch (e) {
    throw new ErroApi('Não foi possível falar com o servidor local. '
      + 'Confira se app.py continua rodando.', 0, String(e));
  }
  const texto = await resposta.text();
  let corpo = null;
  try { corpo = texto ? JSON.parse(texto) : null; } catch (e) { corpo = null; }
  if (!resposta.ok) {
    const msg = (corpo && corpo.erro) ? corpo.erro : `${resposta.status} ${resposta.statusText}`;
    throw new ErroApi(msg, resposta.status, corpo && corpo.detalhe);
  }
  return corpo;
}

/** Recado discreto no canto (nunca alert()). */
function recado(titulo, detalhe, tipo = '') {
  const bandeja = $('#bandeja');
  const n = el('div', { class: 'recado ' + tipo },
    el('div', { class: 'tit' }, titulo),
    detalhe ? el('div', { class: 'detalhe' }, detalhe) : null,
    el('button', { class: 'fechar', type: 'button', title: 'fechar',
      onclick: () => n.remove() }, '×'));
  bandeja.append(n);
  setTimeout(() => n.remove(), tipo === 'erro' ? 14000 : 6000);
}

/** Mensagem clara para os erros previstos do servidor. */
function descreverErro(e) {
  if (e.status === 501 || /módulo ainda não disponível|No module named/i.test(e.message)) {
    return {
      titulo: 'Módulo de cálculo ainda não disponível',
      texto: 'O orquestrador nucleo/galpao.py (ou um módulo de saída) ainda está sendo '
        + 'escrito. Todo o resto da interface continua funcionando: os dados ficam '
        + 'guardados e o cálculo pode ser repetido depois. Para ver a tela de resultados '
        + 'agora, abra a interface com ?demo=1.',
      tipo: 'info',
    };
  }
  if (e.status === 400) {
    return { titulo: 'Dados recusados pelo servidor', texto: e.message, tipo: 'erro' };
  }
  if (e.status === 0) {
    return { titulo: 'Servidor fora do ar', texto: e.message, tipo: 'erro' };
  }
  return {
    titulo: 'Falha no cálculo',
    texto: e.message + (e.detalhe ? '\n\n' + e.detalhe.split('\n').slice(-4).join('\n') : ''),
    tipo: 'erro',
  };
}

/** Dados prontos para o servidor: números como número, texto sem espaço sobrando. */
function dadosParaEnvio() {
  const saida = {};
  for (const [campo, tipo] of Object.entries(estado.tipos)) {
    const v = estado.dados[campo];
    if (tipo === 'bool') saida[campo] = Boolean(v);
    else if (tipo === 'float' || tipo === 'int') {
      const x = num(v);
      if (Number.isFinite(x)) saida[campo] = tipo === 'int' ? Math.round(x) : x;
    } else {
      saida[campo] = String(v ?? '').trim();
    }
  }
  return saida;
}

async function dimensionar({ silencioso = false } = {}) {
  const erros = validar();
  mostrarErros(erros);
  atualizarSinais(erros);
  if (Object.keys(erros).length) {
    const primeiro = Object.keys(erros)[0];
    recado('Corrija os campos marcados', erros[primeiro], 'erro');
    const etapa = etapaDoCampo(primeiro);
    irPara(etapa);
    const ctrl = document.getElementById('c-' + primeiro);
    if (ctrl) ctrl.focus();
    return null;
  }

  irPara('resultados');
  carregando(true, 'Dimensionando o galpão…');
  try {
    const projeto = DEMO
      ? await api('exemplo.json')
      : await api('/api/dimensionar', { method: 'POST', body: JSON.stringify(dadosParaEnvio()) });
    estado.projeto = projeto;
    estado.erroCalculo = null;
    renderResultados();
    renderEntrega();
    atualizarSinais(validar());
    if (!silencioso) {
      recado(projeto.ok ? 'Dimensionamento concluído' : 'Dimensionamento com reprovação',
        projeto.ok ? 'Todas as verificações passaram.'
          : 'Há pelo menos uma verificação acima de 1,00. Veja os cartões vermelhos.',
        projeto.ok ? 'ok' : 'erro');
    }
    return projeto;
  } catch (e) {
    estado.projeto = null;
    estado.erroCalculo = descreverErro(e);
    renderResultados();
    renderEntrega();
    atualizarSinais(validar());
    if (!silencioso) recado(estado.erroCalculo.titulo, estado.erroCalculo.texto,
      estado.erroCalculo.tipo === 'info' ? '' : 'erro');
    return null;
  } finally {
    carregando(false);
  }
}

async function gerarArquivos(quais) {
  const erros = validar();
  mostrarErros(erros);
  if (Object.keys(erros).length) {
    recado('Corrija os campos marcados', 'A geração usa os mesmos dados do dimensionamento.', 'erro');
    return;
  }
  carregando(true, 'Gerando memorial, desenhos e lista…');
  try {
    const resposta = DEMO
      ? await api('exemplo.json')
      : await api('/api/gerar', {
        method: 'POST',
        body: JSON.stringify({ dados: dadosParaEnvio(), saidas: quais }),
      });
    estado.entrega = resposta;
    if (resposta.elementos) estado.projeto = resposta;
    estado.erroCalculo = null;
    renderEntrega();
    renderResultados();
    atualizarSinais(validar());
    const n = (resposta.arquivos || []).length;
    recado('Arquivos gerados', n ? `${n} arquivo(s) na pasta do projeto.`
      : 'O servidor não devolveu arquivos — veja os avisos.', n ? 'ok' : 'erro');
  } catch (e) {
    estado.entrega = null;
    const d = descreverErro(e);
    estado.erroCalculo = d;
    renderEntrega();
    recado(d.titulo, d.texto, d.tipo === 'info' ? '' : 'erro');
  } finally {
    carregando(false);
  }
}

function etapaDoCampo(campo) {
  const grupo = estado.campos.find(g => g.campos.some(c => c.campo === campo));
  const mapa = {
    identificacao: 'projeto', geometria: 'projeto', sistema: 'projeto',
    cobertura: 'cargas', cargas: 'cargas', vento: 'cargas',
    materiais: 'materiais', criterios: 'materiais',
  };
  return (grupo && mapa[grupo.grupo]) || 'projeto';
}

/* ----------------------------------------------------------- 8. resultados */

function renderResultados() {
  const area = $('#resultados-area');
  if (!area) return;
  area.textContent = '';

  if (DEMO) {
    area.append(el('div', { class: 'aviso-caixa info' },
      el('div', { class: 'tit' }, 'Modo de demonstração (?demo=1)'),
      el('div', {}, 'Os números vêm de web/exemplo.json, no formato exato de '
        + 'ProjetoGalpao.para_json(). Servem para conferir a interface, não para projetar.')));
  }

  const p = estado.projeto;
  if (!p) {
    if (estado.erroCalculo) {
      area.append(el('div', { class: 'aviso-caixa ' + (estado.erroCalculo.tipo === 'info' ? 'info' : 'erro') },
        el('div', { class: 'tit' }, estado.erroCalculo.titulo),
        el('div', {}, estado.erroCalculo.texto)));
    }
    area.append(el('div', { class: 'estado-vazio' },
      el('h3', {}, 'Nada dimensionado ainda'),
      el('p', {}, 'Preencha as três primeiras etapas e mande dimensionar. '
        + 'A resposta traz cada elemento com a razão de aproveitamento e a memória de cálculo.'),
      el('button', { class: 'principal', type: 'button', onclick: () => dimensionar() },
        'Dimensionar agora')));
    return;
  }

  /* --- faixa de status geral --- */
  const piorEl = todosOsResultados(p).reduce(
    (a, r) => (r && Number.isFinite(r.razao) && (!a || r.razao > a.razao) ? r : a), null);
  const faixa = el('div', { class: 'barra-status ' + (p.ok ? 'aprovado' : 'reprovado') },
    el('div', { class: 'veredito' }, p.ok ? 'Estrutura verificada' : 'Há verificação reprovada'),
    el('div', { class: 'detalhe' },
      piorEl ? `Elemento mais solicitado: ${piorEl.elemento} — razão ${nf(piorEl.razao, 3)}` : ''),
    el('div', { class: 'detalhe' },
      `Peso total ${nu(p.peso_total_kg, 1, 'kg')} · ${nu(p.consumo_kg_m2, 2, 'kg/m²')}`),
    el('button', { type: 'button', onclick: () => dimensionar() }, 'Recalcular'));
  area.append(faixa);

  if (p.erros && p.erros.length) {
    area.append(el('div', { class: 'aviso-caixa erro' },
      el('div', { class: 'tit' }, 'Erros'),
      el('ul', {}, p.erros.map(x => el('li', {}, x)))));
  }
  if (p.avisos && p.avisos.length) {
    area.append(el('div', { class: 'aviso-caixa' },
      el('div', { class: 'tit' }, `Avisos (${p.avisos.length})`),
      el('ul', {}, p.avisos.map(x => el('li', {}, x)))));
  }

  /* --- cartões --- */
  const cartoes = el('div', { class: 'cartoes' });
  estado.cartoes = [];
  for (const e of (p.elementos || [])) {
    cartoes.append(cartaoElemento({
      nome: e.nome, tag: 'Elemento', perfil: e.perfil, material: e.material,
      razao: e.razao, ok: e.ok, resultado: e.resultado,
      extras: { ...(e.esforcos || {}), ...(e.geometria || {}) },
      alternativas: e.alternativas,
    }));
  }
  for (const [chave, r] of Object.entries(p.ligacoes || {})) {
    if (!r) continue;
    /* a chave do dicionário identifica a ligação; r.elemento costuma ser genérico */
    const nome = /[ ()]/.test(chave) ? chave : chave.replace(/_/g, ' ');
    cartoes.append(cartaoElemento({
      nome, tag: 'Ligação', perfil: r.perfil, material: r.material,
      nota: r.elemento && r.elemento !== nome ? r.elemento : '',
      razao: r.razao, ok: r.ok, resultado: r, extras: r.dados || {},
    }));
  }
  if (p.base) {
    cartoes.append(cartaoElemento({
      nome: p.base.elemento || 'Base do pilar', tag: 'Base', perfil: p.base.perfil,
      material: p.base.material, razao: p.base.razao, ok: p.base.ok,
      resultado: p.base, extras: p.base.dados || {},
    }));
  }
  area.append(cartoes);

  /* o que a resposta não trouxe — evita a impressão de que tudo foi verificado */
  const faltando = [];
  if (!p.base) faltando.push('base do pilar');
  if (!Object.keys(p.ligacoes || {}).length) faltando.push('ligações');
  if (!(p.elementos || []).some(e => /terça/i.test(e.nome))) faltando.push('terça');
  if (!(p.elementos || []).some(e => /contravent/i.test(e.nome))) faltando.push('contraventamento');
  if (faltando.length) {
    cartoes.after(el('div', { class: 'aviso-caixa info' },
      el('div', { class: 'tit' }, 'Sem resultado nesta resposta'),
      el('div', {}, 'O cálculo não devolveu: ' + faltando.join(', ')
        + '. Esses elementos ainda não foram dimensionados.')));
  }

  /* atalho de inspeção: ?memoria=N abre a memória do N-ésimo elemento */
  if (PARAMS.has('memoria')) {
    const i = Math.max(0, Math.min(estado.cartoes.length - 1, Number(PARAMS.get('memoria')) || 0));
    if (estado.cartoes[i]) setTimeout(() => abrirMemoria(estado.cartoes[i]), 0);
  }

  /* --- vento e cargas apurados pelo servidor --- */
  if (p.vento && Object.keys(p.vento).length) {
    area.append(painelChaveValor('Vento apurado no cálculo', p.vento));
  }
  if (p.cargas && Object.keys(p.cargas).length) {
    area.append(painelChaveValor('Cargas apuradas no cálculo', p.cargas));
  }
}

function todosOsResultados(p) {
  const lista = [];
  for (const e of (p.elementos || [])) if (e.resultado) lista.push(e.resultado);
  for (const r of Object.values(p.ligacoes || {})) if (r) lista.push(r);
  if (p.base) lista.push(p.base);
  return lista;
}

const ROTULO_EXTRA = {
  N_Sd_kN: 'N_Sd (kN)', V_Sd_kN: 'V_Sd (kN)', M_Sd_kNm: 'M_Sd (kN·m)',
  M_x_Sd_kNm: 'M_x,Sd (kN·m)', M_y_Sd_kNm: 'M_y,Sd (kN·m)',
  altura_m: 'altura (m)', vao_m: 'vão (m)', vao_inclinado_m: 'vão inclinado (m)',
  espacamento_m: 'espaçamento (m)', quantidade: 'quantidade',
  comprimento_m: 'comprimento (m)', misula_m: 'mísula (m)',
  altura_misula_m: 'altura da mísula (m)', comprimento_flambagem_m: 'K·L (m)',
};

function rotularChave(k) {
  return ROTULO_EXTRA[k] || k.replace(/_/g, ' ');
}

function valorCurto(v) {
  if (typeof v === 'number') return nf(v, Math.abs(v) >= 100 ? 1 : (Math.abs(v) >= 1 ? 2 : 3));
  if (typeof v === 'boolean') return v ? 'sim' : 'não';
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.map(valorCurto).join(' / ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function cartaoElemento(info) {
  if (Array.isArray(estado.cartoes)) estado.cartoes.push(info);
  const razao = Number(info.razao);
  const cls = nivel(razao);
  const largura = Math.min(Math.max(razao, 0), 1.3) / 1.3 * 100;

  const medidor = el('div', { class: 'medidor ' + cls },
    el('div', { class: 'trilho' },
      el('div', { class: 'preenche', style: `width:${largura.toFixed(1)}%` }),
      el('div', { class: 'marca-limite', style: `left:${(100 / 1.3).toFixed(1)}%` })),
    el('div', { class: 'legenda' },
      el('span', {}, 'aproveitamento S', el('sub', {}, 'd'), '/R', el('sub', {}, 'd')),
      el('span', { class: 'valor' }, nf(razao, 3) + (info.ok ? '' : '  ✕'))));

  const critica = info.resultado && info.resultado.critica;
  const extras = Object.entries(info.extras || {}).slice(0, 6);

  const nVerif = info.resultado ? (info.resultado.verificacoes || []).length : 0;
  const botao = el('button', {
    type: 'button',
    disabled: !nVerif,
    onclick: () => abrirMemoria(info),
  }, nVerif ? `Memória de cálculo (${nVerif} verificaç${nVerif > 1 ? 'ões' : 'ão'})`
    : 'Sem memória de cálculo');

  return el('div', { class: 'cartao' },
    el('header', {},
      el('span', { class: 'nome' }, info.nome),
      el('span', { class: 'tag' }, info.tag)),
    el('div', { class: 'corpo-cartao' },
      el('div', {},
        el('div', { class: 'perfil-adotado' }, info.perfil || '—'),
        el('div', { class: 'material-adotado' }, info.material || ''),
        info.nota ? el('div', { class: 'material-adotado' }, info.nota) : null),
      medidor,
      critica ? el('div', { class: 'governa' }, 'Governa: ', el('b', {}, critica)) : null,
      extras.length ? el('dl', { class: 'pares' }, extras.map(([k, v]) =>
        el('div', { class: 'par' },
          el('dt', {}, rotularChave(k)), el('dd', {}, valorCurto(v))))) : null,
      info.alternativas && info.alternativas.length
        ? el('details', { class: 'dados-extra' },
          el('summary', {}, `Perfis testados (${info.alternativas.length})`),
          tabelaAlternativas(info.alternativas))
        : null,
      el('footer', {}, botao)));
}

function tabelaAlternativas(lista) {
  const tab = el('table', { class: 'tab' });
  tab.append(el('thead', {}, el('tr', {},
    el('th', {}, 'Perfil'), el('th', { class: 'n' }, 'Razão'),
    el('th', { class: 'n' }, 'kg/m'), el('th', { class: 'c' }, 'Situação'))));
  const corpo = el('tbody');
  for (const a of lista) {
    corpo.append(el('tr', {},
      el('td', {}, a.perfil || '—'),
      el('td', { class: 'n' }, nf(a.razao, 3)),
      el('td', { class: 'n' }, a.massa === undefined ? '—' : nf(a.massa, 1)),
      el('td', { class: 'c' }, a.ok ? 'passa' : 'não passa')));
  }
  tab.append(corpo);
  return tab;
}

/** Painel para os dicionários livres (vento, cargas): escalares numa grade,
 *  listas de registros viram tabela e listas longas de texto ficam recolhidas. */
function painelChaveValor(titulo, obj) {
  const painel = el('div', { class: 'painel' }, el('h3', {}, titulo));
  const dentro = el('div', { class: 'conteudo-painel' });

  const escalares = [];
  const tabelas = [];
  const textos = [];
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v) && v.length && v.every(x => x && typeof x === 'object' && !Array.isArray(x))) {
      tabelas.push([k, v]);
    } else if (Array.isArray(v) && v.length > 3) {
      textos.push([k, v]);
    } else {
      escalares.push([k, v]);
    }
  }

  if (escalares.length) {
    const grade = el('dl', { class: 'fatores' });
    for (const [k, v] of escalares) {
      grade.append(el('div', { class: 'fator' },
        el('dt', {}, rotularChave(k)), el('dd', {}, valorCurto(v))));
    }
    dentro.append(grade);
  }

  for (const [k, linhas] of tabelas) {
    const colunas = [];
    for (const linha of linhas) {
      for (const c of Object.keys(linha)) if (!colunas.includes(c)) colunas.push(c);
    }
    const tab = el('table', { class: 'tab' });
    tab.append(el('thead', {}, el('tr', {}, colunas.map(c =>
      el('th', { class: typeof linhas[0][c] === 'number' ? 'n' : null }, rotularChave(c))))));
    const tb = el('tbody');
    for (const linha of linhas) {
      tb.append(el('tr', {}, colunas.map(c =>
        el('td', { class: typeof linha[c] === 'number' ? 'n' : null }, valorCurto(linha[c])))));
    }
    tab.append(tb);
    dentro.append(el('details', { class: 'dados-extra', open: linhas.length <= 12 ? true : null },
      el('summary', {}, `${rotularChave(k)} — ${linhas.length} linhas`),
      el('div', { class: 'rolagem' }, tab)));
  }

  for (const [k, itens] of textos) {
    dentro.append(el('details', { class: 'dados-extra' },
      el('summary', {}, `${rotularChave(k)} (${itens.length})`),
      el('ul', {}, itens.map(x => el('li', {}, valorCurto(x))))));
  }

  painel.append(dentro);
  return painel;
}

/* --- memória de cálculo -------------------------------------------------- */

function abrirMemoria(info) {
  const r = info.resultado;
  if (!r) return;
  $('#memoria-titulo').textContent = `${info.nome} — memória de cálculo`;
  $('#memoria-sub').innerHTML = htmlSeguro(
    `${r.perfil || ''}${r.material ? ' · ' + r.material : ''} · razão `
    + `<b>${nf(r.razao, 3)}</b>${r.critica ? ' · governa: ' + r.critica : ''}`);

  const corpo = $('#memoria-corpo');
  corpo.textContent = '';
  for (const v of (r.verificacoes || [])) corpo.append(blocoVerificacao(v));

  if (r.dados && Object.keys(r.dados).length) {
    const det = el('details', { class: 'dados-extra' },
      el('summary', {}, 'Valores guardados para o memorial e os desenhos'));
    const tab = el('table', { class: 'tab' });
    const tb = el('tbody');
    for (const [k, val] of Object.entries(r.dados)) {
      tb.append(el('tr', {}, el('td', {}, rotularChave(k)),
        el('td', { class: 'n' }, valorCurto(val))));
    }
    tab.append(tb);
    det.append(tab);
    corpo.append(det);
  }

  const dlg = $('#dlg-memoria');
  if (typeof dlg.showModal === 'function') dlg.showModal();
  else dlg.setAttribute('open', '');
  corpo.scrollTop = 0;
}

function blocoVerificacao(v) {
  const razao = v.dispensada ? NaN : Number(v.razao);
  const cls = v.dispensada ? 'nivel-dispensada' : nivel(razao);
  const det = el('details', { class: 'verificacao', open: razao > 0.85 || v.dispensada ? true : null });

  det.append(el('summary', {},
    el('span', { class: 'tit-v' }, v.titulo),
    v.norma ? el('span', { class: 'norma-v' }, v.norma) : null,
    el('span', { class: 'razao-v ' + cls },
      v.dispensada ? 'não se aplica' : nf(razao, 3))));

  if (!v.dispensada) {
    const linha = el('div', { class: 'sd-rd' });
    linha.innerHTML = htmlSeguro(
      `S<sub>d</sub> = <b>${nf(v.Sd, 2)} ${v.unidade || ''}</b> &nbsp;·&nbsp; `
      + `R<sub>d</sub> = <b>${nf(v.Rd, 2)} ${v.unidade || ''}</b> &nbsp;·&nbsp; `
      + `folga ${nf((1 - razao) * 100, 1)} %`);
    det.append(linha);
  }
  if (v.observacao) det.append(el('div', { class: 'obs' }, v.observacao));

  if (v.passos && v.passos.length) {
    const tab = el('table', { class: 'passos' });
    tab.append(el('thead', {}, el('tr', {},
      el('th', {}, 'Passo'), el('th', {}, 'Fórmula'), el('th', {}, 'Com os números'),
      el('th', { style: 'text-align:right' }, 'Valor'))));
    const tb = el('tbody');
    for (const p of v.passos) {
      const celulaTexto = comHtml('td', { class: 'p-texto' }, p.texto || '');
      if (p.norma) celulaTexto.append(el('small', {}, p.norma));
      tb.append(el('tr', {},
        celulaTexto,
        comHtml('td', { class: 'p-formula' }, p.formula || ''),
        comHtml('td', { class: 'p-conta' }, p.conta || ''),
        comHtml('td', { class: 'p-valor' }, p.valor || '')));
    }
    tab.append(tb);
    det.append(tab);
  }
  return det;
}

/* -------------------------------------------------------------- 9. entrega */

function renderEntrega() {
  const area = $('#entrega-area');
  if (!area) return;
  area.textContent = '';

  const p = estado.entrega || estado.projeto;

  const opcoes = el('div', { class: 'painel' }, el('h3', {}, 'Gerar os produtos do projeto'));
  const dentro = el('div', { class: 'confundo conteudo-painel' });
  const escolhas = el('div', { class: 'opcoes-saida' });
  const chaves = [['memorial', 'Memorial de cálculo (PDF)'], ['dxf', 'Desenhos (DXF)'],
                  ['pranchas', 'Pranchas (PDF)'], ['lista', 'Lista de material']];
  const caixas = {};
  for (const [k, rotulo] of chaves) {
    const input = el('input', { type: 'checkbox', id: 'saida-' + k });
    input.checked = true;
    caixas[k] = input;
    escolhas.append(el('label', { for: 'saida-' + k }, input, rotulo));
  }
  dentro.append(escolhas);
  dentro.append(el('button', {
    class: 'principal', type: 'button',
    onclick: () => gerarArquivos(Object.keys(caixas).filter(k => caixas[k].checked)),
  }, 'Gerar arquivos'));
  opcoes.append(dentro);
  area.append(opcoes);

  if (estado.erroCalculo && !estado.entrega) {
    area.append(el('div', { class: 'aviso-caixa ' + (estado.erroCalculo.tipo === 'info' ? 'info' : 'erro') },
      el('div', { class: 'tit' }, estado.erroCalculo.titulo),
      el('div', {}, estado.erroCalculo.texto)));
  }

  if (!p) {
    area.append(el('div', { class: 'estado-vazio' },
      el('h3', {}, 'Nenhum arquivo gerado'),
      el('p', {}, 'Depois de dimensionar, gere o memorial, os desenhos e a lista de '
        + 'material. Os arquivos ficam na pasta do projeto e podem ser baixados daqui.')));
    return;
  }

  /* --- resumo numérico --- */
  const custo = p.custo || {};
  const resumo = el('dl', { class: 'resumo-numeros' },
    el('div', {}, el('dt', {}, 'Peso total'),
      el('dd', {}, nf(p.peso_total_kg, 0), el('small', {}, ' kg'))),
    el('div', {}, el('dt', {}, 'Consumo'),
      el('dd', {}, nf(p.consumo_kg_m2, 2), el('small', {}, ' kg/m²'))),
    el('div', {}, el('dt', {}, 'Área de pintura'),
      el('dd', {}, nf(p.area_pintura_m2, 1), el('small', {}, ' m²'))),
    el('div', {}, el('dt', {}, 'Custo estimado'),
      el('dd', {}, custo.total !== undefined ? 'R$ ' + nf(custo.total, 0) : '—')),
    el('div', {}, el('dt', {}, 'Por m² coberto'),
      el('dd', {}, custo.por_m2_coberto !== undefined
        ? 'R$ ' + nf(custo.por_m2_coberto, 0) : '—')));
  const painelResumo = el('div', { class: 'painel' }, el('h3', {}, 'Resumo do projeto'),
    el('div', { class: 'conteudo-painel' }, resumo));
  area.append(painelResumo);

  /* --- arquivos --- */
  const arquivos = (estado.entrega && estado.entrega.arquivos) || [];
  const painelArq = el('div', { class: 'painel' }, el('h3', {}, 'Arquivos gerados'));
  const dentroArq = el('div', { class: 'conteudo-painel' });
  if (!arquivos.length) {
    dentroArq.append(el('p', { class: 'nota' },
      'Nada gerado ainda nesta sessão. Use o botão acima.'));
  } else {
    const lista = el('ul', { class: 'arquivos' });
    for (const a of arquivos) {
      const url = a.url || '';
      const base = decodeURIComponent(url.split('/').pop() || a.nome || 'arquivo');
      const casa = /\.([A-Za-z0-9]{1,5})$/.exec(base);
      const ext = casa ? casa[1].toUpperCase() : 'ARQ';
      const detalhe = [a.titulo, a.descricao, a.escala ? 'escala ' + a.escala : null]
        .filter(Boolean).join(' · ') || url;
      lista.append(el('li', {},
        el('span', { class: 'icone' }, ext),
        el('span', { class: 'nome-arq' },
          el('a', { href: url, download: base, target: '_blank', rel: 'noopener' },
            a.nome || base),
          el('small', {}, detalhe)),
        el('span', { class: 'tam' }, nu(a.tamanho_kb, 1, 'kB'))));
    }
    dentroArq.append(lista);
    if (estado.entrega.pasta) {
      dentroArq.append(el('p', { class: 'nota' }, 'Pasta: ' + estado.entrega.pasta));
    }
  }
  painelArq.append(dentroArq);
  area.append(painelArq);

  /* --- pesos por família --- */
  if (p.resumo_pesos && Object.keys(p.resumo_pesos).length) {
    const tab = el('table', { class: 'tab' });
    tab.append(el('thead', {}, el('tr', {},
      el('th', {}, 'Família'), el('th', { class: 'n' }, 'Peso (kg)'),
      el('th', { class: 'n' }, '% do total'))));
    const tb = el('tbody');
    const total = Object.values(p.resumo_pesos).reduce((a, b) => a + Number(b || 0), 0);
    for (const [k, v] of Object.entries(p.resumo_pesos)) {
      tb.append(el('tr', {}, el('td', {}, k),
        el('td', { class: 'n' }, nf(v, 1)),
        el('td', { class: 'n' }, total ? nf(v / total * 100, 1) + ' %' : '—')));
    }
    tab.append(tb);
    tab.append(el('tfoot', {}, el('tr', {}, el('td', {}, 'Total'),
      el('td', { class: 'n' }, nf(total, 1)), el('td', { class: 'n' }, '100,0 %'))));
    area.append(el('div', { class: 'painel' }, el('h3', {}, 'Peso por família'),
      el('div', { class: 'conteudo-painel' }, el('div', { class: 'rolagem' }, tab))));
  }

  /* --- lista de material --- */
  if (p.lista_material && p.lista_material.length) {
    const tab = el('table', { class: 'tab' });
    tab.append(el('thead', {}, el('tr', {},
      el('th', {}, 'Marca'), el('th', {}, 'Descrição'), el('th', {}, 'Perfil'),
      el('th', {}, 'Material'), el('th', { class: 'n' }, 'Qtd'),
      el('th', { class: 'n' }, 'Comp. (m)'), el('th', { class: 'n' }, 'Unit. (kg)'),
      el('th', { class: 'n' }, 'Total (kg)'))));
    const tb = el('tbody');
    for (const p2 of p.lista_material) {
      tb.append(el('tr', {},
        el('td', {}, p2.marca), el('td', {}, p2.descricao), el('td', {}, p2.perfil),
        el('td', {}, p2.material), el('td', { class: 'n' }, nf(p2.quantidade, 0)),
        el('td', { class: 'n' }, nf(p2.comprimento_m, 2)),
        el('td', { class: 'n' }, nf(p2.peso_unit_kg, 1)),
        el('td', { class: 'n' }, nf(p2.peso_total_kg, 1))));
    }
    tab.append(tb);
    tab.append(el('tfoot', {}, el('tr', {},
      el('td', { colspan: 7 }, 'Peso total'),
      el('td', { class: 'n' }, nf(p.peso_total_kg, 1)))));
    area.append(el('div', { class: 'painel' }, el('h3', {}, 'Lista de material'),
      el('div', { class: 'conteudo-painel' }, el('div', { class: 'rolagem' }, tab))));
  }
}

/* ------------------------------------------------------- projetos salvos */

async function carregarListaProjetos() {
  const lista = $('#projetos-lista');
  lista.textContent = '';
  try {
    const itens = await api('/api/projetos');
    if (!itens || !itens.length) {
      lista.append(el('li', { class: 'vazio' }, 'nenhum projeto salvo'));
      return;
    }
    for (const it of itens) {
      lista.append(el('li', {}, el('button', {
        type: 'button', title: 'abrir ' + it.arquivo,
        onclick: () => abrirProjeto(it.arquivo),
      }, it.nome, el('small', {}, `${nf(it.vao, 1)} × ${nf(it.comprimento, 1)} m`))));
    }
  } catch (e) {
    lista.append(el('li', { class: 'vazio' }, 'não foi possível listar'));
  }
}

async function abrirProjeto(arquivo) {
  carregando(true, 'Carregando projeto…');
  try {
    const dados = await api('/api/projetos/' + encodeURIComponent(arquivo));
    for (const [k, v] of Object.entries(dados)) {
      if (!(k in estado.tipos)) continue;
      estado.dados[k] = (estado.tipos[k] === 'bool') ? Boolean(v) : String(v);
      if (estado.tipos[k] === 'bool') estado.dados[k] = Boolean(v);
    }
    normalizarAberturas();
    refletirNosCampos();
    estado.projeto = null;
    estado.entrega = null;
    aoMudarDados();
    irPara('projeto');
    recado('Projeto carregado', dados.nome || arquivo, 'ok');
  } catch (e) {
    const d = descreverErro(e);
    recado(d.titulo, d.texto, 'erro');
  } finally {
    carregando(false);
  }
}

async function salvarProjeto() {
  const erros = validar();
  mostrarErros(erros);
  if (Object.keys(erros).length) {
    recado('Corrija os campos marcados', 'O servidor valida os mesmos limites.', 'erro');
    irPara(etapaDoCampo(Object.keys(erros)[0]));
    return;
  }
  carregando(true, 'Salvando…');
  try {
    const r = await api('/api/projetos', {
      method: 'POST', body: JSON.stringify(dadosParaEnvio()),
    });
    recado('Projeto salvo', `${r.nome} → ${r.salvo}`, 'ok');
    carregarListaProjetos();
  } catch (e) {
    const d = descreverErro(e);
    recado(d.titulo, d.texto, 'erro');
  } finally {
    carregando(false);
  }
}

/* -------------------------------------------------- 10. navegação e início */

function irPara(etapa) {
  if (!ETAPAS.includes(etapa)) etapa = 'projeto';
  estado.etapa = etapa;
  for (const nome of ETAPAS) {
    const sec = document.getElementById('etapa-' + nome);
    if (sec) sec.hidden = nome !== etapa;
  }
  for (const a of $$('#nav-etapas a')) {
    if (a.dataset.etapa === etapa) a.setAttribute('aria-current', 'step');
    else a.removeAttribute('aria-current');
  }
  if (location.hash.slice(1) !== etapa) {
    history.replaceState(null, '', location.pathname + location.search + '#' + etapa);
  }
  window.scrollTo(0, 0);
  if (etapa === 'projeto') { desenharSecao(); desenharLongitudinal(); }
  if (etapa === 'cargas') { renderVento(); renderTabelaCargas(); }
  if (etapa === 'materiais') { renderTabelaMateriais(); renderTabelaCriterios(); }
}

/** Reage a qualquer mudança nos dados: valida, redesenha, persiste. */
let temporizador = null;
function aoMudarDados() {
  const erros = validar();
  mostrarErros(erros);
  atualizarSinais(erros);
  $('#projeto-atual').textContent = [estado.dados.nome, estado.dados.cliente,
    estado.dados.local].filter(Boolean).join(' · ') || '—';
  aplicarDependencias();
  desenharSecao();
  desenharLongitudinal();
  renderVento();
  renderTabelaCargas();
  renderTabelaMateriais();
  renderTabelaCriterios();
  clearTimeout(temporizador);
  temporizador = setTimeout(salvarLocal, 250);
}

function aplicarTema(tema) {
  if (tema === 'claro' || tema === 'escuro') document.documentElement.setAttribute('data-tema', tema);
  else document.documentElement.removeAttribute('data-tema');
}

function alternarTema() {
  const atual = document.documentElement.getAttribute('data-tema');
  const escuroDoSistema = window.matchMedia('(prefers-color-scheme: dark)').matches;
  let proximo;
  if (!atual) proximo = escuroDoSistema ? 'claro' : 'escuro';
  else proximo = atual === 'escuro' ? 'claro' : 'escuro';
  aplicarTema(proximo);
  gravarTema(proximo);
}

async function iniciar() {
  aplicarTema(PARAMS.get('tema') || lerTema());
  const etapaInicial = location.hash.slice(1) || 'projeto';

  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-salvar').addEventListener('click', salvarProjeto);
  $('#btn-calcular').addEventListener('click', () => dimensionar());
  $('#btn-recarregar-projetos').addEventListener('click', carregarListaProjetos);
  $('#memoria-fechar').addEventListener('click', () => $('#dlg-memoria').close());

  for (const b of $$('[data-ir]')) b.addEventListener('click', () => irPara(b.dataset.ir));
  for (const b of $$('[data-acao="dimensionar"]')) b.addEventListener('click', () => dimensionar());
  for (const a of $$('#nav-etapas a')) {
    a.addEventListener('click', ev => { ev.preventDefault(); irPara(a.dataset.etapa); });
  }
  window.addEventListener('hashchange', () => irPara(location.hash.slice(1)));
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); dimensionar(); }
  });

  carregando(true, 'Carregando catálogo…');
  let catalogo = null;
  try {
    catalogo = await api('/api/catalogo');
  } catch (e) {
    const d = descreverErro(e);
    recado(d.titulo, d.texto, 'erro');
  } finally {
    carregando(false);
  }

  if (!catalogo) {
    $('#conteudo').prepend(el('div', { class: 'aviso-caixa erro' },
      el('div', { class: 'tit' }, 'Catálogo não carregado'),
      el('div', {}, 'O formulário é montado a partir de GET /api/catalogo. '
        + 'Suba o servidor com: python app.py')));
    return;
  }

  estado.catalogo = catalogo;
  estado.campos = catalogo.campos || [];
  for (const grupo of estado.campos) {
    for (const item of grupo.campos) {
      estado.tipos[item.campo] = item.tipo;
      estado.rotulos[item.campo] = item.rotulo;
      estado.dados[item.campo] = (item.tipo === 'bool')
        ? Boolean(item.valor)
        : (item.valor === null || item.valor === undefined ? '' : String(item.valor));
    }
  }

  const salvo = lerLocal();
  if (salvo) {
    for (const [k, v] of Object.entries(salvo)) {
      if (k in estado.tipos) estado.dados[k] = (estado.tipos[k] === 'bool') ? Boolean(v) : v;
    }
  }

  if (DEMO) {
    /* preenche o formulário com o mesmo caso do exemplo, para a tela ficar coerente */
    try {
      const exemplo = await api('exemplo.json');
      for (const [k, v] of Object.entries(exemplo.dados || {})) {
        if (k in estado.tipos) {
          estado.dados[k] = (estado.tipos[k] === 'bool') ? Boolean(v) : String(v);
        }
      }
    } catch (e) { /* segue com os padrões */ }
  }

  normalizarAberturas();
  montarFormulario();
  aoMudarDados();
  carregarListaProjetos();

  renderResultados();
  renderEntrega();
  irPara(etapaInicial);

  /* ?demo=1 calcula de saída para a tela ficar navegável sem o servidor;
     ?auto=1 faz o mesmo contra a API real, útil para conferência automatizada */
  if (DEMO || PARAMS.get('auto') === '1') {
    await dimensionar({ silencioso: true });
    if (DEMO) estado.entrega = estado.projeto;
    renderEntrega();
    atualizarSinais(validar());
    irPara(etapaInicial);
  }
}

document.addEventListener('DOMContentLoaded', iniciar);

/* ------------------------------------------------------------------ editor 3D
 * No navegador o editor abre em outra aba. No programa instalado a janela é o Chrome
 * em modo aplicativo, que não tem abas: um `_blank` viraria uma janela comum do
 * navegador, com barra de endereço. Ali pedimos um popup, que o Chrome abre como outra
 * janela do aplicativo; o nome fixo faz o segundo clique reaproveitar a mesma janela. */
let janelaPropria = false;
fetch('/api/versao').then(r => r.json()).then(v => { janelaPropria = !!v.janela; }).catch(() => {});

function abrirEditor3D() {
  const url = '/editor?galpao=1';
  if (!janelaPropria) { window.open(url, '_blank'); return; }
  const larg = Math.min(1600, screen.availWidth - 80), alt = Math.min(1000, screen.availHeight - 80);
  const j = window.open(url, 'metalica-editor3d', `popup=yes,width=${larg},height=${alt},left=40,top=40`);
  if (j) j.focus(); else window.location.href = url;      // popup bloqueado: mesma janela
}
window.abrirEditor3D = abrirEditor3D;
