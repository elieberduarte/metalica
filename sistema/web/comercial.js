/* Comercial da obra (/comercial?projeto=<slug>): proposta técnica comercial (com as imagens do modelo 3D),
 * contrato de empreitada, etapas da obra, parcelas, aditivos e termo de aceite. Lê e grava em
 * /api/projetos/<slug>/comercial — ver saida/comercial_servico.py. */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);
const PROJETO = new URLSearchParams(location.search).get('projeto') || '';
const API = `/api/projetos/${encodeURIComponent(PROJETO)}/comercial`;

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'value') e.value = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    e.append(f.nodeType ? f : document.createTextNode(String(f)));
  }
  return e;
}
const n = (x, casas = 2) => (x === null || x === undefined || x === '') ? '—'
  : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const reais = (x) => (x === null || x === undefined || x === '') ? '—' : 'R$ ' + n(x, 2);
const numBR = (s) => {
  if (typeof s === 'number') return s;
  let t = String(s ?? '').trim().replace(/\s/g, '').replace(/^R\$/i, '');
  if (!t) return null;
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
};
const paraCampo = (v, casas = 2) => (v === null || v === undefined || v === '') ? ''
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: casas });
const dataBR = (iso) => { const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/); return m ? `${m[3]}/${m[2]}/${m[1]}${m[4] ? ' ' + m[4] + ':' + m[5] : ''}` : (iso || ''); };

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  let j = {};
  try { j = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}
function aviso(texto, tipo = '') {
  const a = $('#aviso');
  a.hidden = !texto;
  a.className = 'aviso-topo ' + tipo;
  a.replaceChildren(...(Array.isArray(texto) ? texto : [texto || '']));
}

let S = null;             // o estado que veio do servidor (proposta, contrato, etapas…), editado no lugar
let ABA = 'proposta';
let SUJO = false;
try { ABA = (location.hash || '').slice(1) || localStorage.getItem('comercial.aba') || 'proposta'; } catch { /* */ }
const ABAS = [['proposta', 'Proposta'], ['contrato', 'Contrato'], ['obra', 'Obra e pagamentos'], ['documentos', 'Documentos'], ['empresa', 'Empresa']];
const marcar = () => { SUJO = true; const e = document.querySelector('.estado-sujo'); if (e) e.textContent = 'alterações não gravadas'; };

/* ------------------------------------------------------------ campos ligados ao estado */
function campo(obj, chave, rotulo, attrs = {}) {
  const tipo = attrs.tipo || 'text';
  let i;
  if (tipo === 'area') i = el('textarea', { class: attrs.alta ? 'alta' : '', placeholder: attrs.dica || '' });
  else if (tipo === 'select') i = el('select', {}, (attrs.opcoes || []).map(([v, t]) => el('option', { value: v }, t)));
  else i = el('input', { type: 'text', placeholder: attrs.dica || '', inputmode: attrs.num ? 'decimal' : undefined });
  const v = obj[chave];
  i.value = attrs.num ? paraCampo(v) : (v ?? '');
  i.addEventListener(tipo === 'select' ? 'change' : 'input', () => {
    obj[chave] = attrs.num ? numBR(i.value) : (attrs.inteiro ? (parseInt(i.value, 10) || null) : i.value);
    marcar();
    if (attrs.aoMudar) attrs.aoMudar(i.value);
  });
  return el('label', { class: attrs.largo ? 'largo' : '', title: attrs.dica || '' }, rotulo, i);
}
function marcador(obj, chave, rotulo, dica) {
  const c = el('input', { type: 'checkbox' });
  c.checked = !!obj[chave];
  c.addEventListener('change', () => { obj[chave] = c.checked; marcar(); });
  return el('label', { style: 'display:flex;gap:6px;align-items:center;font-size:13px;color:var(--texto)', title: dica || '' }, c, rotulo);
}
/** Lista de textos editada numa caixa (um item por linha). */
function linhasTexto(obj, chave, rotulo, dica) {
  const t = el('textarea', { class: 'alta', placeholder: dica || 'um item por linha' });
  t.value = (obj[chave] || []).join('\n');
  t.addEventListener('input', () => { obj[chave] = t.value.split('\n').map(s => s.trim()).filter(Boolean); marcar(); });
  return el('label', { class: 'largo' }, rotulo, t);
}
/** Tabela de linhas (lista de objetos), com colunas [chave, rótulo, num?]. */
function tabelaLinhas(lista, colunas, classe, nova) {
  const cx = el('div', { class: 'linhas ' + classe });
  const desenhar = () => {
    cx.replaceChildren(el('div', { class: 'linha cab-linha' }, colunas.map(c => el('span', { texto: c[1] })), el('span')));
    lista.forEach((it, k) => {
      cx.append(el('div', { class: 'linha' }, colunas.map(([ch, , num]) => {
        if (num === 'bool') {
          const c = el('input', { type: 'checkbox' }); c.checked = !!it[ch];
          c.addEventListener('change', () => { it[ch] = c.checked; marcar(); });
          return el('span', { style: 'text-align:center' }, c);
        }
        const i = el('input', { type: 'text', inputmode: num ? 'decimal' : undefined, value: num ? paraCampo(it[ch]) : (it[ch] ?? '') });
        i.addEventListener('input', () => { it[ch] = num ? numBR(i.value) : i.value; marcar(); });
        return i;
      }), el('button', { type: 'button', class: 'x', title: 'Tirar a linha', texto: '×', onclick: () => { lista.splice(k, 1); marcar(); desenhar(); } })));
    });
    cx.append(el('div', {}, el('button', { type: 'button', class: 'botao-m', texto: '+ linha', onclick: () => { lista.push(nova()); marcar(); desenhar(); } })));
  };
  desenhar();
  return cx;
}
const caixa = (titulo, sub, ...filhos) => el('div', { class: 'caixa' }, el('h3', {}, titulo, sub ? el('small', { texto: sub }) : null), ...filhos);
const vazio = (t) => el('div', { class: 'vazio', texto: t });

/* ------------------------------------------------------------ abas */
function montarAbas() {
  const P = S.proposta || {}, C = S.contrato || {};
  const estado = {
    proposta: (P.revisoes || []).length ? 'ok' : (S.proposta_nova ? '' : 'meio'),
    contrato: C.situacao === 'assinado' ? 'ok' : (S.tem_contrato ? 'meio' : ''),
    obra: (S.etapas || []).every(e => e.situacao === 'concluida') ? 'ok' : ((S.etapas || []).some(e => e.situacao !== 'pendente') ? 'meio' : ''),
    empresa: S.empresa_incompleta ? 'meio' : 'ok',
  };
  $('#abas').replaceChildren(...ABAS.map(([k, t]) => el('button', { type: 'button', class: k === ABA ? 'ativa' : '', onclick: () => irPara(k) },
    el('i', { class: 'ponto ' + (estado[k] || '') }), t)));
}
function irPara(k) {
  ABA = k;
  try { localStorage.setItem('comercial.aba', k); } catch { /* */ }
  history.replaceState(null, '', location.pathname + location.search + '#' + k);
  desenhar();
}
function desenhar() {
  const p = S.projeto || {};
  $('#sub-projeto').textContent = p.nome || PROJETO;
  document.title = `Comercial — ${p.nome || PROJETO}`;
  $('#obra-nome').textContent = p.nome || PROJETO;
  const P = S.proposta || {};
  $('#obra-sub').textContent = [P.numero ? `Proposta ${P.numero} ${P.revisao || ''}` : 'Proposta ainda não gravada',
    S.tem_contrato ? `contrato ${S.contrato.situacao === 'assinado' ? 'assinado' : 'em minuta'}` : null,
    (P.cliente || {}).nome].filter(Boolean).join(' · ');
  $('#quando').textContent = (S.historico || [])[0] ? `última ação: ${dataBR(S.historico[0].quando)}` : '';
  montarAbas();
  const c = $('#conteudo');
  const f = { proposta: abaProposta, contrato: abaContrato, obra: abaObra, documentos: abaDocumentos, empresa: abaEmpresa }[ABA] || abaProposta;
  c.replaceChildren(f());
}

async function carregar() {
  if (!PROJETO) { aviso('Abra esta tela por um projeto (gerenciador de projetos → Comercial).', 'erro'); return; }
  aviso('Carregando…');
  try { S = await pedir(API); aviso(''); SUJO = false; desenhar(); }
  catch (e) { aviso(`Não foi possível abrir a área comercial: ${e.message}`, 'erro'); }
}

async function acao(nome, corpo, texto) {
  const estado = document.querySelector('.estado-sujo');
  if (estado) estado.replaceChildren(el('span', { class: 'giro' }), ' ' + (texto || 'gravando…'));
  let vigia = null;
  if (nome === 'imagens') {
    vigia = setInterval(async () => {
      try { const p = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/progresso`); if (p.etapa && estado) estado.replaceChildren(el('span', { class: 'giro' }), ' ' + p.etapa); } catch { /* */ }
    }, 1200);
  }
  try {
    const r = await pedir(nome ? `${API}/${nome}` : API, corpo || {});
    if (vigia) clearInterval(vigia);
    if (r.parcelas && !r.proposta) return r;
    S = r; SUJO = false;
    desenhar();
    const links = [];
    for (const [k, a] of Object.entries(r.gerado || {})) links.push(el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: `Abrir ${k.toUpperCase()}` }), ' ');
    if (r.erro_pdf) aviso(`Gravado, mas o PDF falhou: ${r.erro_pdf}`, 'erro');
    else if (links.length) aviso(['Pronto. ', ...links], 'ok');
    else aviso('');
    return r;
  } catch (e) {
    if (vigia) clearInterval(vigia);
    if (estado) estado.textContent = '';
    aviso(`Não foi possível: ${e.message}`, 'erro');
    throw e;
  }
}
const ultimo = (prefixo) => [...(S.arquivos || [])].filter(a => a.nome.startsWith(prefixo) && a.nome.endsWith('.pdf'))
  .sort((a, b) => String(b.alterado).localeCompare(String(a.alterado)))[0];

/* ------------------------------------------------------------ proposta */
function abaProposta() {
  const P = S.proposta;
  P.cliente = P.cliente || {}; P.obra = P.obra || {}; P.investimento = P.investimento || {};
  P.geometria = P.geometria || []; P.carregamentos = P.carregamentos || []; P.escopo = P.escopo || []; P.parcelas = P.parcelas || [];
  P.investimento.partes = P.investimento.partes || []; P.investimento.opcionais = P.investimento.opcionais || [];
  P.prazos_etapas = P.prazos_etapas || {};
  const gravarP = () => acao('', { proposta: P });
  const pdf = ultimo('Proposta_');
  const barra = el('div', { class: 'barra' },
    el('button', { type: 'button', class: 'botao-m', texto: 'Gravar', onclick: gravarP }),
    el('button', { type: 'button', class: 'botao-m', texto: (P.imagens || []).length ? 'Gerar as imagens do 3D de novo' : 'Gerar imagens do 3D',
      title: 'Abre o modelo 3D num navegador invisível e fotografa a estrutura de alguns ângulos (com e sem cobertura) — cerca de 1 minuto',
      onclick: async () => { if (SUJO) await acao('', { proposta: P }); acao('imagens', {}, 'gerando as imagens do modelo 3D…'); } }),
    el('button', { type: 'button', class: 'botao-m principal', texto: 'Gerar a proposta (PDF)', onclick: () => acao('proposta-pdf', { proposta: P }, 'montando a proposta…') }),
    el('button', { type: 'button', class: 'botao-m', texto: 'Nova revisão', title: `Passa de ${P.revisao || 'R00'} para a próxima (o PDF da revisão anterior fica guardado)`,
      onclick: async () => { if (SUJO) await acao('', { proposta: P }); acao('nova-revisao', {}); } }),
    el('span', { class: 'sep' }), el('span', { class: 'estado estado-sujo', texto: P.numero ? '' : 'o número sai ao gravar' }));

  const ident = caixa('Identificação', 'número e revisão aparecem na capa e no cabeçalho', el('div', { class: 'campos' },
    campo(P, 'numero', 'Número', { dica: 'gerado ao gravar (AAAA-NNN)' }), campo(P, 'revisao', 'Revisão'), campo(P, 'data', 'Data', { dica: 'dd/mm/aaaa' }),
    campo(P, 'validade_dias', 'Validade (dias)', { num: true, dica: 'prazo de validade da proposta' }), campo(P, 'cidade_emissao', 'Emitida em', { dica: 'ex.: Cascavel, PR' }),
    campo(P, 'opcao', 'Opção', { dica: 'ex.: Opção 01 – terças pré-galvanizadas' }),
    campo(P, 'ref', 'Referência', { largo: true, dica: 'ex.: Proposta para execução das estruturas metálicas de cobertura e fechamentos.' })));
  const cli = caixa('Cliente e obra', null, el('div', { class: 'campos' },
    campo(P.cliente, 'nome', 'Cliente'), campo(P.cliente, 'contato', 'A/C (contato)'), campo(P.cliente, 'cidade', 'Cidade'), campo(P.cliente, 'uf', 'UF'),
    campo(P.cliente, 'email', 'E-mail'), campo(P.cliente, 'telefone', 'Telefone'),
    campo(P.obra, 'nome', 'Nome da obra'), campo(P.obra, 'cidade', 'Cidade da obra'), campo(P.obra, 'uf', 'UF da obra'),
    campo(P, 'projeto_por', 'Projeto da estrutura', { tipo: 'select', opcoes: [['hermes', 'nosso (elaborado por nós)'], ['cliente', 'do cliente (projetos fornecidos)']] })));
  const geo = caixa('Geometria das estruturas', 'aparece na ficha técnica e no escopo',
    tabelaLinhas(P.geometria, [['nome', 'Estrutura'], ['largura', 'Largura (m)', 1], ['comprimento', 'Comprimento (m)', 1], ['area', 'Área (m²)', 1]], 'geo',
      () => ({ nome: 'Cobertura', largura: null, comprimento: null, area: null })),
    el('div', { class: 'campos', style: 'margin-top:8px' }, campo(P, 'peso_kg', 'Peso de estrutura considerado (kg)', { num: true }),
      marcador(P, 'mostrar_ficha', 'Mostrar a ficha técnica (área, aço, vão…)')));
  const car = caixa('Carregamentos', 'quando o projeto é nosso; a linha do vento (NBR 6123) entra sozinha',
    tabelaLinhas(P.carregamentos, [['carga', 'Carga'], ['descricao', 'Descrição']], 'car', () => ({ carga: '', descricao: '' })));

  // escopo
  const blocos = el('div');
  const desenharEscopo = () => {
    blocos.replaceChildren();
    P.escopo.forEach((b, kb) => {
      b.itens = b.itens || [];
      const tit = el('input', { type: 'text', value: b.titulo || '', placeholder: 'Nome da estrutura (ex.: Cobertura portaria)' });
      tit.addEventListener('input', () => { b.titulo = tit.value; marcar(); });
      const itens = el('div');
      b.itens.forEach((it, ki) => {
        const t = el('input', { type: 'text', value: it.texto || '' });
        t.addEventListener('input', () => { it.texto = t.value; marcar(); });
        const d = el('input', { type: 'checkbox' }); d.checked = !!it.destaque;
        d.addEventListener('change', () => { it.destaque = d.checked; marcar(); });
        itens.append(el('div', { class: 'item-escopo' },
          el('span', { class: 'mover', title: 'Subir', texto: '↑', onclick: () => { if (ki) { b.itens.splice(ki - 1, 0, b.itens.splice(ki, 1)[0]); marcar(); desenharEscopo(); } } }),
          t, el('label', { title: 'Em destaque (negrito), como as telhas' }, d, 'destaque'),
          el('button', { type: 'button', class: 'x', texto: '×', onclick: () => { b.itens.splice(ki, 1); marcar(); desenharEscopo(); } })));
      });
      blocos.append(el('div', { class: 'bloco-escopo' },
        el('div', { class: 'topo-bloco' }, tit, el('button', { type: 'button', class: 'botao-m perigo', texto: 'Tirar bloco', onclick: () => { P.escopo.splice(kb, 1); marcar(); desenharEscopo(); } })),
        itens, el('button', { type: 'button', class: 'botao-m', texto: '+ item', onclick: () => { b.itens.push({ texto: '', destaque: false }); marcar(); desenharEscopo(); } })));
    });
    blocos.append(el('button', { type: 'button', class: 'botao-m', texto: '+ estrutura (bloco)', onclick: () => { P.escopo.push({ titulo: '', itens: [] }); marcar(); desenharEscopo(); } }));
  };
  desenharEscopo();
  const esc = caixa('Estrutura metálica — escopo', 'sugerido pela lista de materiais e pelo orçamento; revise', blocos);

  const exclOpc = el('select', {}, el('option', { value: '' }, 'acrescentar uma exclusão comum…'), (S.exclusoes_opcionais || []).map(x => el('option', { value: x }, x.slice(0, 90))));
  const exclArea = linhasTexto(P, 'exclusoes', 'Não incluso (exclusões de escopo)');
  exclOpc.addEventListener('change', () => {
    if (!exclOpc.value) return;
    P.exclusoes = P.exclusoes || [];
    const ultimoItem = P.exclusoes.findIndex(x => x.startsWith('Todos e quaisquer'));
    if (ultimoItem >= 0) P.exclusoes.splice(ultimoItem, 0, exclOpc.value); else P.exclusoes.push(exclOpc.value);
    exclArea.querySelector('textarea').value = P.exclusoes.join('\n');
    exclOpc.value = ''; marcar();
  });
  const cond = caixa('Condições, exclusões e responsabilidades', 'textos-padrão da empresa; um item por linha', el('div', { class: 'campos' },
    linhasTexto(P, 'condicoes', 'Condições gerais'), linhasTexto(P, 'seguranca', 'Proteção e segurança'), exclArea,
    el('label', { class: 'largo' }, exclOpc), linhasTexto(P, 'responsabilidades', 'Por conta do contratante')));

  const orc = S.orcamento || {};
  const inv = caixa('Investimento', orc.fechamento ? `fechamento do orçamento: ${reais(orc.fechamento)}` : 'preencha o fechamento na aba Orçamento ou digite aqui',
    el('div', { class: 'campos' }, campo(P.investimento, 'valor', 'Investimento total (R$)', { num: true, dica: 'valor global da proposta' }),
      el('label', {}, ' ', el('button', { type: 'button', class: 'botao-m', texto: 'Usar o fechamento do orçamento', disabled: !orc.fechamento,
        onclick: () => { P.investimento.valor = Math.round(orc.fechamento * 100) / 100; marcar(); desenhar(); } }))),
    el('p', { class: 'dica', texto: 'Composição (opcional: um valor por estrutura ou etapa) e opcionais (o total com o item acrescentado):' }),
    tabelaLinhas(P.investimento.partes, [['descricao', 'Composição'], ['valor', 'Valor (R$)', 1]], 'din', () => ({ descricao: '', valor: null })),
    el('p', { class: 'dica', texto: 'Opcionais:' }),
    tabelaLinhas(P.investimento.opcionais, [['descricao', 'Opcional'], ['valor', 'Total com o item (R$)', 1]], 'din', () => ({ descricao: '', valor: null })),
    el('div', { class: 'campos', style: 'margin-top:8px' }, linhasTexto(P.investimento, 'notas', 'Notas (a do antidumping entra sempre)', 'ex.: *Não está incluso … diferencial de ICMS …')));

  const ger = { entrada: 10, n: 8, primeira: '' };
  const pagParc = tabelaLinhas(P.parcelas, [['descricao', 'Parcela'], ['vencimento', 'Vencimento'], ['valor', 'Valor (R$)', 1]], 'parc3', () => ({ descricao: '', vencimento: '', valor: null }));
  const pag = caixa('Pagamento e prazo', 'a empresa costuma pôr "A combinar" na proposta e fechar no contrato',
    el('div', { class: 'campos' }, campo(P, 'pagamento', 'Condições de pagamento (texto)', { dica: 'ex.: 10% de sinal + saldo em 8 parcelas.' }),
      campo(P, 'prazo', 'Prazo de execução (texto)', { dica: 'ex.: Conforme cronograma de obra.' }),
      campo(P.prazos_etapas, 'projeto', 'Projeto (dias)', { num: true }), campo(P.prazos_etapas, 'fabricacao', 'Fabricação (dias)', { num: true }),
      campo(P.prazos_etapas, 'montagem', 'Montagem (dias)', { num: true })),
    el('p', { class: 'dica', texto: 'Parcelas (opcional; com elas a proposta mostra a tabela no lugar do texto):' }), pagParc,
    geradorParcelas(ger, () => P.investimento.valor, (lista) => { P.parcelas.splice(0, P.parcelas.length, ...lista); marcar(); desenhar(); }));

  const imgs = el('div', { class: 'imagens' }, (P.imagens || []).map((im) => {
    const usar = el('input', { type: 'checkbox' }); usar.checked = im.usar !== false;
    const leg = el('input', { type: 'text', value: im.legenda || '', placeholder: 'legenda' });
    const fig = el('figure', { class: usar.checked ? '' : 'fora' }, el('img', { src: im.url + '?t=' + Date.now(), alt: '' }),
      el('figcaption', {}, el('label', {}, usar, (im.arquivo || '').split(/[\\/]/).pop().replace(/\.\w+$/, '') === 'capa' ? 'usar (foto da capa)' : 'usar'), leg));
    usar.addEventListener('change', () => { im.usar = usar.checked; fig.className = usar.checked ? '' : 'fora'; marcar(); });
    leg.addEventListener('input', () => { im.legenda = leg.value; marcar(); });
    return fig;
  }));
  const imagens = caixa('Imagens do modelo 3D', 'capa, destaque e galeria da proposta', (P.imagens || []).length ? imgs : vazio('Sem imagens: use "Gerar imagens do 3D" (o projeto precisa ter o modelo 3D).'));

  const av = (S.avisos_proposta || []).length ? el('ul', { class: 'avisos' }, S.avisos_proposta.map(a => el('li', { texto: a }))) : el('div', { class: 'ok-msg', texto: 'Tudo preenchido.' });
  const revs = (P.revisoes || []).length ? el('table', { class: 't' }, el('tr', {}, ['Rev.', 'Data', 'Valor', 'Arquivo'].map(t => el('th', { texto: t }))),
    [...P.revisoes].reverse().map(r => { const a = (S.arquivos || []).find(x => x.nome === r.arquivo);
      return el('tr', {}, el('td', { texto: r.revisao }), el('td', { texto: r.data || '' }), el('td', { class: 'r', texto: reais(r.valor) }),
        el('td', {}, a ? el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: 'PDF' }) : '—')); })) : vazio('Nenhuma revisão gerada ainda.');
  const previa = el('div', { class: 'caixa previa' }, el('h3', {}, 'Prévia', el('small', { texto: pdf ? `${pdf.nome} · ${dataBR(pdf.alterado)}` : '' })),
    pdf ? el('iframe', { src: pdf.url + '#view=FitH', title: 'Prévia da proposta' }) : vazio('Gere a proposta para ver a prévia aqui.'));

  return el('div', {}, barra, el('div', { class: 'grade2' },
    el('div', {}, ident, cli, imagens, geo, car, esc, cond, inv, pag),
    el('div', {}, caixa('A conferir', null, av), caixa('Revisões', 'cada revisão gerada fica guardada', revs), previa)));
}

function geradorParcelas(ger, valor, aplicar) {
  const e = el('input', { type: 'text', value: String(ger.entrada), inputmode: 'decimal' });
  const q = el('input', { type: 'text', value: String(ger.n), inputmode: 'numeric' });
  const d = el('input', { type: 'text', value: ger.primeira, placeholder: 'dd/mm/aaaa' });
  return el('div', { class: 'campos', style: 'margin-top:8px;align-items:end' },
    el('label', {}, 'Entrada (%)', e), el('label', {}, 'Nº de parcelas', q), el('label', {}, '1º vencimento', d),
    el('label', {}, ' ', el('button', { type: 'button', class: 'botao-m', texto: 'Gerar parcelas', onclick: async () => {
      const v = numBR(valor());
      if (!v) { aviso('Preencha o valor antes de gerar as parcelas.', 'erro'); return; }
      const r = await acao('parcelas', { valor: v, entrada_pct: numBR(e.value) || 0, n: parseInt(q.value, 10) || 0, primeira: d.value });
      aplicar(r.parcelas || []);
    } })));
}

/* ------------------------------------------------------------ contrato */
function abaContrato() {
  if (!S.tem_contrato) {
    return caixa('Contrato', 'contrato de empreitada global no modelo da empresa', el('p', { texto: 'O contrato nasce da proposta: escopo, geometria, exclusões (que viram responsabilidades do contratante) e valor vêm dela. Depois você completa o contratante, a forma de pagamento e as condições.' }),
      el('button', { type: 'button', class: 'botao-m principal', texto: 'Abrir o contrato a partir da proposta', disabled: !(S.proposta || {}).numero,
        title: (S.proposta || {}).numero ? '' : 'Grave a proposta primeiro', onclick: () => acao('contrato', {}) }));
  }
  const C = S.contrato, P = S.proposta || {};
  C.contratante = C.contratante || {}; C.parcelas = C.parcelas || []; C.testemunhas = C.testemunhas || [{}, {}];
  while (C.testemunhas.length < 2) C.testemunhas.push({});
  const pdf = ultimo('Contrato_');
  const docx = [...(S.arquivos || [])].filter(a => a.nome.startsWith('Contrato_') && a.nome.endsWith('.docx')).sort((a, b) => String(b.alterado).localeCompare(String(a.alterado)))[0];
  const barra = el('div', { class: 'barra' },
    el('button', { type: 'button', class: 'botao-m', texto: 'Gravar', onclick: () => acao('', { contrato: C }) }),
    el('button', { type: 'button', class: 'botao-m principal', texto: 'Gerar o contrato (Word e PDF)', onclick: () => acao('contrato-docs', { contrato: C }, 'montando o contrato…') }),
    docx ? el('a', { class: 'botao-m', href: docx.url, texto: 'Baixar o Word', title: docx.nome }) : null,
    el('span', { class: 'sep' }), el('span', { class: 'estado estado-sujo' }));
  const ct = C.contratante;
  const partes = caixa('Contratante', 'como sai na qualificação do contrato', el('div', { class: 'campos' },
    campo(ct, 'razao_social', 'Razão social', { largo: true }), campo(ct, 'cnpj', 'CNPJ', { dica: '00.000.000/0000-00' }), campo(ct, 'ie', 'Inscrição estadual'),
    campo(ct, 'endereco', 'Endereço (rua, nº, bairro)', { largo: true }), campo(ct, 'cep', 'CEP'), campo(ct, 'cidade', 'Cidade'), campo(ct, 'uf', 'UF'),
    campo(ct, 'representante', 'Representante (nome)'), campo(ct, 'representante_qualificacao', 'Qualificação', { dica: 'ex.: brasileiro, casado, sócio administrador' }),
    campo(ct, 'representante_cpf', 'CPF do representante')));
  const vp = (P.investimento || {}).valor;
  const ger = { entrada: 10, n: 8, primeira: '' };
  const preco = caixa('Preço e pagamento', vp ? `proposta: ${reais(vp)}` : null,
    el('div', { class: 'campos' }, campo(C, 'valor', 'Valor do contrato (R$)', { num: true }), campo(C, 'arras', 'Arras confirmatórias (R$)', { num: true, dica: 'vazio = sem arras' }),
      campo(C, 'reajuste_incc_parcela', 'INCC a partir da parcela nº', { num: true, dica: 'vazio = sem reajuste' })),
    el('p', { class: 'dica', texto: 'Parcelas (marque as pagas na aba "Obra e pagamentos"):' }),
    tabelaLinhas(C.parcelas, [['descricao', 'Parcela'], ['vencimento', 'Vencimento'], ['valor', 'Valor (R$)', 1]], 'parc3', () => ({ descricao: '', vencimento: '', valor: null, paga: false, pago_em: '' })),
    geradorParcelas(ger, () => C.valor, (lista) => { C.parcelas.splice(0, C.parcelas.length, ...lista); marcar(); desenhar(); }));
  const prazo = caixa('Prazo, multas e condições', null, el('div', { class: 'campos' },
    campo(C, 'prazo_tipo', 'Prazo', { tipo: 'select', opcoes: [['dias', 'em dias da liberação de montagem'], ['texto', 'texto (cronograma)']] }),
    campo(C, 'prazo_dias', 'Prazo (dias)', { num: true }), campo(C, 'prazo_texto', 'Prazo (texto)', { largo: true, dica: 'de acordo com o cronograma da obra acordado entre as partes' }),
    campo(C, 'desmobilizacao', 'Desmobilização (R$ por evento)', { num: true }), campo(C, 'multa_mes', 'Multa por atraso (% ao mês)', { num: true }),
    campo(C, 'objeto', 'Objeto', { dica: 'ex.: cobertura e fechamento lateral' })),
    el('div', { class: 'campos', style: 'margin-top:10px' },
      marcador(C, 'seguro_clima', 'Seguro da obra contra eventos climáticos por conta do contratante'),
      marcador(C, 'rigging_contratante', 'Plano de rigging por conta do contratante'),
      marcador(C, 'pluviais_contratante', 'Condutores pluviais por conta do contratante'),
      marcador(C, 'garantia', 'Cláusula de garantia (5 anos de solidez, 1 ano de pintura)')),
    el('div', { class: 'campos', style: 'margin-top:10px' }, linhasTexto(C, 'extras_contratante', 'Outras responsabilidades do contratante (opcional)', 'ex.: Fornecimento e instalação do ACM, inclusive estrutura auxiliar…')));
  const fecho = caixa('Assinatura', null, el('div', { class: 'campos' },
    campo(C, 'revisao', 'Revisão'), campo(C, 'data', 'Data do contrato', { dica: 'dd/mm/aaaa' }), campo(C, 'cidade_assinatura', 'Cidade'),
    campo(C, 'foro', 'Foro (comarca)'), campo(C, 'foro_uf', 'UF do foro'),
    campo(C.testemunhas[0], 'nome', '1ª testemunha'), campo(C.testemunhas[0], 'cpf', 'CPF'), campo(C.testemunhas[1], 'nome', '2ª testemunha'), campo(C.testemunhas[1], 'cpf', 'CPF'),
    campo(C, 'situacao', 'Situação', { tipo: 'select', opcoes: [['minuta', 'minuta'], ['enviado', 'enviado ao cliente'], ['assinado', 'assinado']] }),
    campo(C, 'assinado_em', 'Assinado em', { dica: 'dd/mm/aaaa' }), campo(C, 'assinatura_meio', 'Meio', { dica: 'ICP-Brasil, D4Sign, DocuSign, papel' })));
  const av = (S.avisos_contrato || []).length ? el('ul', { class: 'avisos' }, S.avisos_contrato.map(a => el('li', { texto: a }))) : el('div', { class: 'ok-msg', texto: 'Tudo preenchido.' });
  const corr = el('ul', { class: 'hist' }, (S.correcoes || []).map(c => el('li', { texto: c })));
  const previa = el('div', { class: 'caixa previa' }, el('h3', {}, 'Prévia', el('small', { texto: pdf ? `${pdf.nome} · ${dataBR(pdf.alterado)}` : '' })),
    pdf ? el('iframe', { src: pdf.url + '#view=FitH', title: 'Prévia do contrato' }) : vazio('Gere o contrato para ver a prévia aqui.'));
  return el('div', {}, barra, el('div', { class: 'grade2' }, el('div', {}, partes, preco, prazo, fecho),
    el('div', {}, caixa('A conferir', null, av), caixa('O que o modelo novo corrige', 'erros que se repetiam nos contratos', corr), previa)));
}

/* ------------------------------------------------------------ obra e pagamentos */
function abaObra() {
  const C = S.contrato || {}, F = S.financeiro;
  C.parcelas = C.parcelas || []; C.aditivos = C.aditivos || [];
  const gravarTudo = () => acao('', S.tem_contrato ? { etapas: S.etapas, contrato: C } : { etapas: S.etapas });
  const barra = el('div', { class: 'barra' }, el('button', { type: 'button', class: 'botao-m principal', texto: 'Gravar', onclick: gravarTudo }),
    el('span', { class: 'sep' }), el('span', { class: 'estado estado-sujo' }));
  const cart = F ? el('div', { class: 'cartoes' },
    cartao(reais(F.total), 'contrato + aditivos', F.aditivos ? `${reais(F.contrato)} + ${reais(F.aditivos)}` : null),
    cartao(reais(F.recebido), 'recebido', el('div', { class: 'barra-prog' }, el('i', { style: `width:${Math.min(100, F.pct_recebido)}%` })), 'bom'),
    cartao(reais(F.a_receber), 'a receber', `${n(100 - F.pct_recebido, 1)}% do total`),
    cartao(reais(F.atrasado), 'em atraso', F.atrasado ? 'parcelas vencidas sem baixa' : 'nenhuma parcela vencida', F.atrasado ? 'ruim' : ''),
    cartao(F.proxima ? reais(F.proxima.valor) : '—', 'próxima parcela', F.proxima ? `vence em ${F.proxima.vencimento}` : null)) : null;

  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  const venc = (t) => { const m = String(t || '').match(/(\d{2})\/(\d{2})\/(\d{4})/); return m ? new Date(+m[3], +m[2] - 1, +m[1]) : null; };
  const parc = S.tem_contrato ? (C.parcelas.length ? el('table', { class: 't' }, el('tr', {}, ['Parcela', 'Vencimento', 'Valor', 'Paga', 'Pago em'].map((t, i) => el('th', { class: i === 2 ? 'r' : '', texto: t }))),
    C.parcelas.map((p) => {
      const c = el('input', { type: 'checkbox' }); c.checked = !!p.paga;
      const d = el('input', { type: 'text', value: p.pago_em || '', placeholder: 'dd/mm/aaaa', style: 'width:110px' });
      const v = venc(p.vencimento);
      const tr = el('tr', { class: p.paga ? 'paga' : (v && v < hoje ? 'atrasada' : '') }, el('td', { texto: p.descricao || '' }), el('td', { texto: p.vencimento || '' }),
        el('td', { class: 'r', texto: reais(p.valor) }), el('td', {}, c), el('td', {}, d));
      c.addEventListener('change', () => { p.paga = c.checked; if (c.checked && !d.value) { d.value = new Date().toLocaleDateString('pt-BR'); p.pago_em = d.value; } marcar(); });
      d.addEventListener('input', () => { p.pago_em = d.value; marcar(); });
      return tr;
    })) : vazio('O contrato não tem parcelas: preencha na aba Contrato.')) : vazio('Abra o contrato para controlar as parcelas.');

  const tempo = el('div', { class: 'tempo' }, (S.etapas || []).map((e, k) => {
    const sel = el('select', {}, [['pendente', 'pendente'], ['andamento', 'em andamento'], ['concluida', 'concluída']].map(([v, t]) => el('option', { value: v }, t)));
    sel.value = e.situacao;
    const linha = el('div', { class: 'etapa ' + e.situacao });
    sel.addEventListener('change', () => { e.situacao = sel.value; e.automatica = false; linha.className = 'etapa ' + sel.value; marcar(); });
    const ent = (ch, dica, w) => { const i = el('input', { type: 'text', value: e[ch] || '', placeholder: dica }); if (w) i.style.width = w; i.addEventListener('input', () => { e[ch] = i.value; marcar(); }); return i; };
    linha.append(el('span', { class: 'bola', texto: e.situacao === 'concluida' ? '✓' : String(k + 1) }),
      el('span', { class: 'nome' }, el('b', { texto: e.nome }), el('small', { texto: e.marco })),
      el('span', {}, sel, e.automatica ? el('div', { class: 'auto', texto: 'pelo sistema' }) : null),
      el('span', { class: 'opc' }, ent('previsto', 'previsto')), el('span', { class: 'opc' }, ent('realizado', 'realizado')),
      el('span', { class: 'extra' }, ent('responsavel', 'responsável'), ent('obs', 'observação')));
    return linha;
  }));

  const adit = S.tem_contrato ? el('div', {},
    tabelaLinhas(C.aditivos, [['data', 'Data'], ['descricao', 'Descrição do aditivo'], ['valor', 'Valor (R$)', 1], ['prazo_dias', '+ prazo (dias)', 1]], 'adit',
      () => ({ data: new Date().toLocaleDateString('pt-BR'), descricao: '', valor: null, prazo_dias: null })),
    C.aditivos.length ? el('div', { class: 'barra', style: 'margin-top:8px' }, C.aditivos.map((a, i) => el('button', { type: 'button', class: 'botao-m', texto: `Termo aditivo nº ${i + 1} (PDF)`,
      onclick: async () => { await acao('', { contrato: C }); acao('aditivo', { indice: i }, 'gerando o termo aditivo…'); } }))) : null) : vazio('Abra o contrato para registrar aditivos.');

  const termo = { data: new Date().toLocaleDateString('pt-BR'), data_vistoria: '', pendencias: '' };
  const tAceite = caixa('Termo de aceite', 'na entrega da obra (o contrato obriga o contratante a assinar)', el('div', { class: 'campos' },
    campo(termo, 'data_vistoria', 'Data da vistoria', { dica: 'dd/mm/aaaa' }), campo(termo, 'data', 'Data do termo'),
    campo(termo, 'pendencias', 'Pendências (uma por linha; vazio = sem pendências)', { tipo: 'area', largo: true })),
    el('div', { class: 'barra', style: 'margin-top:8px' }, el('button', { type: 'button', class: 'botao-m', texto: 'Gerar o termo de aceite (PDF)', disabled: !S.tem_contrato,
      onclick: () => acao('termo-aceite', termo, 'gerando o termo…') })));
  const hist = (S.historico || []).length ? el('ul', { class: 'hist' }, S.historico.map(h => el('li', {}, el('b', { texto: dataBR(h.quando) + ' ' }), h.texto))) : vazio('Sem registros ainda.');
  return el('div', {}, barra, cart, el('div', { class: 'grade2' },
    el('div', {}, caixa('Etapas da obra', 'do orçamento à garantia; algumas se marcam sozinhas', tempo), caixa('Aditivos', 'alteração de escopo vira termo aditivo, não proposta nova', adit)),
    el('div', {}, caixa('Parcelas', 'marque o que foi recebido', parc), tAceite, caixa('Histórico', null, hist))));
}
function cartao(valor, rotulo, sub, classe = '') {
  return el('div', { class: 'cartao-n ' + classe }, el('b', { texto: valor }), el('span', { texto: rotulo }), sub ? (sub.nodeType ? sub : el('small', { texto: sub })) : null);
}

/* ------------------------------------------------------------ documentos */
function abaDocumentos() {
  const lista = [...(S.arquivos || [])].sort((a, b) => String(b.alterado).localeCompare(String(a.alterado)));
  if (!lista.length) return vazio('Nenhum documento gerado ainda.');
  return caixa('Documentos da obra', 'propostas, contratos, aditivos e termos (pasta comercial/ do projeto)', el('table', { class: 't' },
    el('tr', {}, ['Documento', 'Gerado em', 'Tamanho'].map((t, i) => el('th', { class: i === 2 ? 'r' : '', texto: t }))),
    lista.map(a => el('tr', {}, el('td', {}, el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: a.nome })), el('td', { texto: dataBR(a.alterado) }),
      el('td', { class: 'r', texto: n(a.tamanho_kb, 0) + ' kB' })))));
}

/* ------------------------------------------------------------ empresa */
function abaEmpresa() {
  const E = JSON.parse(JSON.stringify(S.empresa || {}));
  E.representante = E.representante || {}; E.banco = E.banco || {}; E.cores = E.cores || {}; E.responsavel_tecnico = E.responsavel_tecnico || {};
  const logos = {};
  const arquivo = (chave, rotulo) => {
    const i = el('input', { type: 'file', accept: 'image/png,image/jpeg' });
    i.addEventListener('change', () => {
      const f = i.files[0]; if (!f) return;
      const fr = new FileReader(); fr.onload = () => { logos[chave + '_base64'] = fr.result; marcar(); }; fr.readAsDataURL(f);
    });
    return el('label', {}, rotulo, i);
  };
  const prev = el('div', { class: 'marca-prev' },
    S.empresa.logo_url ? el('img', { src: S.empresa.logo_url + '?t=' + Date.now(), alt: 'logo' }) : null,
    S.empresa.logo_claro_url ? el('img', { class: 'claro', src: S.empresa.logo_claro_url + '?t=' + Date.now(), alt: 'logo claro' }) : null);
  return el('div', {}, el('div', { class: 'barra' }, el('button', { type: 'button', class: 'botao-m principal', texto: 'Gravar os dados da empresa',
    onclick: () => acao('empresa', Object.assign({ empresa: E }, logos)) }), el('span', { class: 'sep' }), el('span', { class: 'estado estado-sujo' })),
  el('div', { class: 'grade2' }, el('div', {},
    caixa('Empresa', 'vale para todas as propostas e contratos; fica em Documentos\\Metálica\\fabrica\\empresa.json', el('div', { class: 'campos' },
      campo(E, 'razao_social', 'Razão social', { largo: true }), campo(E, 'nome_comercial', 'Nome comercial'), campo(E, 'cnpj', 'CNPJ'), campo(E, 'ie', 'Inscrição estadual'),
      campo(E, 'endereco', 'Endereço', { largo: true }), campo(E, 'bairro', 'Bairro'), campo(E, 'cidade', 'Cidade'), campo(E, 'uf', 'UF'), campo(E, 'cep', 'CEP'),
      campo(E, 'telefone', 'Telefone'), campo(E, 'email', 'E-mail'), campo(E, 'site', 'Site'), campo(E, 'slogan', 'Slogan'), campo(E, 'foro', 'Foro padrão (comarca)'))),
    caixa('Representante, responsável técnico e banco', null, el('div', { class: 'campos' },
      campo(E.representante, 'nome', 'Representante legal'), campo(E.representante, 'qualificacao', 'Qualificação'),
      campo(E.responsavel_tecnico, 'nome', 'Responsável técnico'), campo(E.responsavel_tecnico, 'registro', 'CREA'),
      campo(E.banco, 'banco', 'Banco'), campo(E.banco, 'agencia', 'Agência'), campo(E.banco, 'conta', 'Conta'))),
    caixa('Apresentação na proposta', null, el('div', { class: 'campos' },
      campo(E, 'apresentacao', '"Quem somos"', { tipo: 'area', largo: true }), linhasTexto(E, 'diferenciais', 'Diferenciais (um por linha)')))),
  el('div', {}, caixa('Identidade visual', 'logo no cabeçalho; o logo claro vai na capa escura',
    el('div', { class: 'campos' }, arquivo('logo', 'Logo (PNG)'), arquivo('logo_claro', 'Logo claro (PNG, para fundo escuro)'),
      campo(E.cores, 'primaria', 'Cor principal', { dica: '#35434C' }), campo(E.cores, 'destaque', 'Cor de destaque', { dica: '#C3D773' })),
    el('p', { class: 'dica', texto: S.empresa.logo ? 'Logo cadastrado.' : 'Sem logo cadastrado.' }), prev))));
}

/* ------------------------------------------------------------ início */
document.addEventListener('DOMContentLoaded', () => {
  $('#btn-tema').addEventListener('click', () => {
    const r = document.documentElement;
    const novo = (r.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro')) === 'escuro' ? 'claro' : 'escuro';
    r.setAttribute('data-tema', novo);
    try { localStorage.setItem('galpao.tema', novo); } catch { /* */ }
  });
  $('#btn-materiais').addEventListener('click', () => { location.href = `/materiais?projeto=${encodeURIComponent(PROJETO)}#orcamento`; });
  $('#btn-3d').addEventListener('click', () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-voltar').addEventListener('click', () => {
    if (document.referrer && new URL(document.referrer).origin === location.origin && history.length > 1) history.back();
    else location.href = '/';
  });
  window.addEventListener('beforeunload', (ev) => { if (SUJO) { ev.preventDefault(); ev.returnValue = ''; } });
  carregar();
});
