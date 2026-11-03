/* Ligações pré-moldadas (em desenvolvimento): cálice, consolo e aparelho de apoio de elastômero calculados
 * avulsos pela rota /api/premoldado/ligacao (premoldado/ligacoes.py → nbr9062.py) — as mesmas rotinas do
 * galpão. O formulário, um desenho esquemático com as medidas e as verificações com a memória. */
'use strict';

const MATERIAIS = [
  ['fck', 'f<sub>ck</sub> (MPa)', 35], ['agregado', 'Agregado', 'granito', ['granito', 'basalto', 'gnaisse', 'calcário', 'arenito']],
  ['aco', 'Aço', 'CA-50', ['CA-50', 'CA-60']], ['pre_fabricado', 'Pré-fabricado (γ<sub>c</sub> 1,3 / γ<sub>s</sub> 1,10)', false],
];

const TIPOS = {
  calice: {
    nome: 'Cálice de fundação', norma: 'NBR 9062, 7.7',
    explica: 'Pilar engastado na fundação por cálice com colarinho, interfaces lisas ou rugosas: comprimento de embutimento (Tabela 15 e a ancoragem da armadura do pilar), '
      + 'pressão na parede frontal (H<sub>sfd</sub>, com γ<sub>n</sub> = 1,2), armaduras do colarinho pelo modelo da Figura 27 e as mínimas.',
    campos: [
      ['b', 'Pilar — largura b, fora do plano do momento (cm)', 45], ['h', 'Pilar — altura h, no plano do momento (cm)', 50],
      ['Nd', 'N<sub>d</sub> — normal de cálculo, compressão + (kN)', 150], ['Md', 'M<sub>d</sub> — momento na base (kN·m)', 200],
      ['Vd', 'V<sub>d</sub> — cortante na base (kN)', 30], ['bitola_pilar', 'Bitola longitudinal do pilar (mm)', 16, [10, 12.5, 16, 20, 25]],
      ['interface', 'Interface pilar/cálice', 'rugosa', ['rugosa', 'lisa']], ['parede', 'Parede do colarinho (cm)', 20], ['folga', 'Folga para o graute (cm)', 5],
    ],
  },
  consolo: {
    nome: 'Consolo', norma: 'NBR 9062, 7.3',
    explica: 'Consolo de concreto no pilar: classificação por a/d (muito curto, curto, ou em balanço pela NBR 6118), tirante, biela, costura, estribos, '
      + 'com o coeficiente γ<sub>n</sub> (7.3.1.1) e a força horizontal H<sub>d</sub> pela Tabela da 7.3.9 quando não informada.',
    campos: [
      ['b', 'Largura b (cm)', 40], ['h', 'Altura no engastamento h (cm)', 50], ['a', 'Distância a da carga à face do pilar (cm)', 25],
      ['Fd', 'F<sub>d</sub> — reação vertical de cálculo, sem γ<sub>n</sub> (kN)', 300],
      ['apoio', 'Apoio da viga no consolo', 'elastômero', null], ['Hd', 'H<sub>d</sub> — força horizontal (kN; vazio = pela 7.3.9)', ''],
      ['permanente_preponderante', 'Carga permanente preponderante', false], ['carga_indireta', 'Carga indireta (pendurada)', false],
      ['interface', 'Ligação do consolo ao pilar', 'monolítico', ['monolítico', 'rugosa', 'lisa']],
      ['bitola_tirante', 'Bitola do tirante (mm)', 12.5, [10, 12.5, 16, 20]],
    ],
  },
  elastomero: {
    nome: 'Aparelho de apoio de elastômero', norma: 'NBR 9062, 7.2.1.6',
    explica: 'Almofada simples (uma camada, sem chapas): tensão de contato, distorção, deslizamento, tensão mínima, cisalhamento total e estabilidade, '
      + 'com as cargas características.',
    campos: [
      ['a', 'a — dimensão na direção do vão (cm)', 15], ['b', 'b — dimensão transversal (cm)', 30], ['h', 'h — espessura (cm)', 1.0],
      ['Ngk', 'N<sub>gk</sub> — reação permanente (kN)', 150], ['Nqk', 'N<sub>qk</sub> — reação variável (kN)', 60],
      ['Hk', 'H<sub>k</sub> — força horizontal (kN)', 20], ['shore', 'Dureza Shore A', 60, [50, 60, 70]],
      ['rotacao_g', 'Rotação permanente θ<sub>g</sub> (rad)', 0], ['rotacao_q', 'Rotação variável θ<sub>q</sub> (rad)', 0],
    ],
    semMateriais: true,
  },
};

let TIPO = new URLSearchParams(location.search).get('tipo') || 'calice';
if (!TIPOS[TIPO]) TIPO = 'calice';
let APOIOS = ['elastômero'];

function indice() {
  const nav = $('#indice');
  nav.replaceChildren(...Object.entries(TIPOS).map(([k, t]) => el('button', { type: 'button', class: k === TIPO ? 'atual' : '',
    onclick: () => { TIPO = k; history.replaceState(null, '', '?tipo=' + k); indice(); montar(); } }, t.nome)),
    el('p', { class: 'nota-indice', texto: 'As mesmas rotinas que o galpão pré-moldado usa. Ainda por fazer: chumbadores e ligações de vigas (dente Gerber, pino, chapa soldada).' }));
}

function campo([k, rot, v, ops]) {
  if (k === 'apoio') ops = APOIOS;
  let inp;
  if (ops) inp = el('select', { id: 'c-' + k }, ops.map(o => el('option', { value: String(o), texto: String(o).replace('.', ','), selected: String(o) === String(v) || undefined })));
  else if (typeof v === 'boolean') inp = el('input', { id: 'c-' + k, type: 'checkbox', checked: v || undefined });
  else inp = el('input', { id: 'c-' + k, value: String(v).replace('.', ',') });
  inp.addEventListener('change', calcular);
  return [el('label', { for: 'c-' + k, html: rot }), inp];
}

function ler() {
  const t = TIPOS[TIPO], d = { tipo: TIPO };
  for (const [k] of t.campos.concat(t.semMateriais ? [] : MATERIAIS)) {
    const e = $('#c-' + k);
    if (e) d[k] = e.type === 'checkbox' ? e.checked : e.value.replace(',', '.');
  }
  return d;
}

function montar() {
  const t = TIPOS[TIPO];
  const form = el('div', { class: 'campos' }, ...t.campos.flatMap(campo));
  const mat = t.semMateriais ? null : el('div', { class: 'campos' }, ...MATERIAIS.flatMap(campo));
  $('#conteudo').replaceChildren(
    el('div', { class: 'caixa' }, el('h3', { texto: `${t.nome} — ${t.norma}` }), el('p', { class: 'explica', html: t.explica }),
      el('div', { class: 'lado-a-lado' },
        el('div', { style: 'flex:1; min-width:320px; max-width:520px' }, form, mat ? el('h3', { texto: 'Materiais', style: 'margin-top:12px' }) : null, mat,
          el('div', { class: 'botoes' }, el('button', { type: 'button', class: 'principal', onclick: calcular }, 'Calcular'))),
        el('div', { class: 'desenho', id: 'desenho', style: 'flex:1; min-width:300px' }))),
    el('div', { id: 'resultado' }));
  calcular();
}

// ------------------------------------------------------------------ desenhos esquemáticos
const cota = (x1, y1, x2, y2, txt, lado = 'cima') => {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, vert = Math.abs(x2 - x1) < 1e-6;
  const tx = vert ? mx + (lado === 'esq' ? -6 : 6) : mx, ty = vert ? my + 4 : my + (lado === 'baixo' ? 14 : -5);
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--texto3)" marker-start="url(#seta)" marker-end="url(#seta)"/>`
    + `<text x="${tx}" y="${ty}" font-size="11" fill="var(--texto2)" text-anchor="${vert ? (lado === 'esq' ? 'end' : 'start') : 'middle'}">${txt}</text>`;
};
const DEFS = `<defs><marker id="seta" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
  <path d="M0 2 L5 5 L0 8" fill="none" stroke="var(--texto3)"/></marker>
  <marker id="forca" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#dc2626"/></marker></defs>`;
const svg = (W, H, corpo) => `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="color:var(--texto)">${DEFS}${corpo}</svg>`;

function desenhoCalice(e, d) {
  const h = +e.h, folga = +d.folga, par = +d.parede, L = +d.Lemb, fundo = +d.fundo, hc = +d.h_colarinho;
  const ext = h + 2 * folga + 2 * par, alt = L + fundo + 0.45 * L;
  const esc = Math.min(330 / ext, 380 / alt), ox = 70, oy = 30 + 0.45 * L * esc;     // oy = a boca do cálice
  const X = x => ox + x * esc, Y = y => oy - y * esc;
  const con = 'fill="var(--painel2)" stroke="currentColor"';
  let s = '';
  s += `<rect x="${X(0)}" y="${Y(0)}" width="${par * esc}" height="${L * esc}" ${con}/>`;
  s += `<rect x="${X(ext - par)}" y="${Y(0)}" width="${par * esc}" height="${L * esc}" ${con}/>`;
  s += `<rect x="${X(0)}" y="${Y(-L)}" width="${ext * esc}" height="${fundo * esc}" ${con}/>`;
  s += `<rect x="${X(par)}" y="${Y(0)}" width="${folga * esc}" height="${L * esc}" fill="var(--texto3)" opacity=".25"/>`;
  s += `<rect x="${X(ext - par - folga)}" y="${Y(0)}" width="${folga * esc}" height="${L * esc}" fill="var(--texto3)" opacity=".25"/>`;
  s += `<rect x="${X(par + folga)}" y="${Y(0.45 * L)}" width="${h * esc}" height="${1.45 * L * esc}" fill="none" stroke="var(--azul)" stroke-width="1.6"/>`;
  s += `<text x="${X(ext / 2)}" y="${Y(0.2 * L)}" font-size="12" text-anchor="middle" fill="var(--azul)">pilar</text>`;
  s += `<line x1="${X(-4)}" x2="${X(ext + 4)}" y1="${Y(-L + (L - hc))}" y2="${Y(-L + (L - hc))}" stroke="var(--texto3)" stroke-dasharray="4 3"/>`;
  s += cota(X(ext + 10), Y(0), X(ext + 10), Y(-L), `L<tspan font-size="9">emb</tspan> = ${num(L, 0)} cm`);
  s += cota(X(-10), Y(0), X(-10), Y(-hc), `colarinho ${num(hc, 0)}`, 'esq');
  s += cota(X(-10), Y(-L), X(-10), Y(-L - fundo), `fundo ${num(fundo, 0)}`, 'esq');
  s += cota(X(0), Y(-L - fundo) + 12, X(ext), Y(-L - fundo) + 12, `${num(ext, 0)} cm (parede ${num(par, 0)} + folga ${num(folga, 0)} + h ${num(h, 0)})`, 'baixo');
  // o momento e a pressão na parede frontal
  s += `<line x1="${X(ext - par) + 30}" y1="${Y(-0.1 * L)}" x2="${X(ext - par) + 2}" y2="${Y(-0.1 * L)}" stroke="#dc2626" stroke-width="2" marker-end="url(#forca)"/>`;
  s += `<text x="${X(ext - par) + 34}" y="${Y(-0.1 * L) + 4}" font-size="11" fill="#dc2626">γ<tspan font-size="9">n</tspan>H<tspan font-size="9">sfd</tspan> = ${num(d.Hsfd_gn, 0)} kN</text>`;
  return svg(X(ext) + 190, Y(-L - fundo) + 40, s) + `<p class="mem">Corte no plano do momento (esquema). Colarinho externo ${num(d.externo[0], 0)} × ${num(d.externo[1], 0)} cm, `
    + `interno ${num(d.interno[0], 0)} × ${num(d.interno[1], 0)} cm.</p>`;
}

function desenhoConsolo(e, d, r) {
  const b = +e.b, h = +e.h, a = +e.a, comp = a + Math.max(10, 0.3 * h), pil = Math.max(30, 0.6 * h);
  const esc = Math.min(260 / (comp + pil), 260 / (h * 2)), ox = 40, oy = 40 + 0.5 * h * esc;
  const X = x => ox + (x + pil) * esc, Y = y => oy + y * esc;
  const con = 'fill="var(--painel2)" stroke="currentColor"';
  let s = `<rect x="${X(-pil)}" y="${Y(-0.5 * h)}" width="${pil * esc}" height="${2 * h * esc}" ${con}/>`;
  s += `<polygon points="${X(0)},${Y(0)} ${X(comp)},${Y(0)} ${X(comp)},${Y(0.5 * h)} ${X(0)},${Y(h)}" ${con}/>`;
  s += `<text x="${X(-pil / 2)}" y="${Y(1.2 * h)}" font-size="11" text-anchor="middle" fill="var(--texto2)">pilar</text>`;
  const dd = +d.d || h - 4;
  s += `<line x1="${X(-0.6 * pil)}" x2="${X(comp - 3)}" y1="${Y(h - dd)}" y2="${Y(h - dd)}" stroke="var(--azul)" stroke-width="2"/>`;
  if (d.barras) s += `<text x="${X(comp / 2)}" y="${Y(h - dd) + 14}" font-size="11" text-anchor="middle" fill="var(--azul)">tirante ${d.barras[0]} ø ${num(d.barras[1], 1)}</text>`;
  s += `<line x1="${X(a)}" y1="${Y(0) - 44}" x2="${X(a)}" y2="${Y(0) - 3}" stroke="#dc2626" stroke-width="2" marker-end="url(#forca)"/>`;
  s += `<text x="${X(a) + 5}" y="${Y(0) - 32}" font-size="11" fill="#dc2626">F<tspan font-size="9">d</tspan> = ${num(+e.Fd, 0)} kN</text>`;
  if (d.Hd) {
    s += `<line x1="${X(a) - 40}" y1="${Y(0) - 6}" x2="${X(a) - 3}" y2="${Y(0) - 6}" stroke="#dc2626" stroke-width="2" marker-end="url(#forca)"/>`;
    s += `<text x="${X(a) - 44}" y="${Y(0) - 10}" font-size="11" text-anchor="end" fill="#dc2626">H<tspan font-size="9">d</tspan> = ${num(d.Hd, 0)}</text>`;
  }
  s += cota(X(0), Y(h) + 14, X(a), Y(h) + 14, `a = ${num(a, 0)}`, 'baixo');
  s += cota(X(comp) + 14, Y(0), X(comp) + 14, Y(h), `h = ${num(h, 0)}`);
  return svg(X(comp) + 90, Y(1.5 * h) + 20, s) + `<p class="mem">Elevação (esquema; o comprimento da ponta e a altura na extremidade são ilustrativos). `
    + `b = ${num(b, 0)} cm, d = ${num(dd, 1)} cm, a/d = ${num(d.a_d)}${d.tipo ? ' — ' + d.tipo : ''}.</p>`;
}

function desenhoElastomero(e) {
  const a = +e.a, b = +e.b, h = +e.h;
  const esc = Math.min(220 / b, 160 / a), ox = 40, oy = 30;
  let s = `<rect x="${ox}" y="${oy}" width="${b * esc}" height="${a * esc}" fill="var(--painel2)" stroke="currentColor"/>`;
  s += cota(ox, oy + a * esc + 14, ox + b * esc, oy + a * esc + 14, `b = ${num(b, 0)} cm`, 'baixo');
  s += cota(ox + b * esc + 14, oy, ox + b * esc + 14, oy + a * esc, `a = ${num(a, 0)} cm (vão)`);
  s += `<text x="${ox}" y="${oy - 8}" font-size="11" fill="var(--texto2)">planta</text>`;
  const ey = oy + a * esc + 70, hh = Math.max(h * esc * 4, 8);
  s += `<text x="${ox}" y="${ey - 30}" font-size="11" fill="var(--texto2)">elevação (espessura ampliada ×4)</text>`;
  s += `<rect x="${ox}" y="${ey}" width="${a * esc}" height="${hh}" fill="var(--painel2)" stroke="currentColor"/>`;
  s += `<line x1="${ox + a * esc / 2}" y1="${ey - 24}" x2="${ox + a * esc / 2}" y2="${ey - 2}" stroke="#dc2626" stroke-width="2" marker-end="url(#forca)"/>`;
  s += `<text x="${ox + a * esc / 2 + 5}" y="${ey - 12}" font-size="11" fill="#dc2626">N<tspan font-size="9">k</tspan> = ${num(+e.Ngk + +e.Nqk, 0)} kN</text>`;
  s += cota(ox + a * esc + 14, ey, ox + a * esc + 14, ey + hh, `h = ${num(h, 1)} cm`);
  return svg(ox + Math.max(b, a) * esc + 150, ey + hh + 30, s);
}

// ------------------------------------------------------------------ o cálculo
let pedido = 0;
async function calcular() {
  const meu = ++pedido;
  const e = ler();
  const res = $('#resultado');
  try {
    const r = await pedir('/api/premoldado/ligacao', e);
    if (meu !== pedido) return;
    const d = r.dados || {};
    $('#desenho').innerHTML = TIPO === 'calice' ? desenhoCalice(e, d) : TIPO === 'consolo' ? desenhoConsolo(e, d, r) : desenhoElastomero(e);
    const box = (v, t) => el('div', {}, el('b', { texto: v }), el('span', { texto: t }));
    const resumo = [box(r.ok ? 'atende' : (r.indeterminada ? 'fora do modelo' : 'não passa'), 'situação'), box(num(r.razao), 'maior razão S/R')];
    if (TIPO === 'calice') {
      resumo.push(box(`${num(d.Lemb, 0)} cm`, 'embutimento adotado'), box(`${num(d.externo[0], 0)} × ${num(d.externo[1], 0)} cm`, 'colarinho externo'));
      const br = d.barras || {};
      if (br.horizontal_principal) resumo.push(box(`${br.horizontal_principal[0]} ø ${num(br.horizontal_principal[1], 1)}`, 'horizontal principal (por ramo)'));
      if (br.vertical) resumo.push(box(`${br.vertical[0]} ø ${num(br.vertical[1], 1)}`, 'verticais (total)'));
      if (br.horizontal_secundaria) resumo.push(box(`${br.horizontal_secundaria[0]} ø ${num(br.horizontal_secundaria[1], 1)}`, 'horizontais secundárias'));
    } else if (TIPO === 'consolo') {
      if (d.barras) resumo.push(box(`${d.barras[0]} ø ${num(d.barras[1], 1)}`, 'tirante'));
      if (d.a_d !== undefined) resumo.push(box(num(d.a_d), 'a/d'));
      if (d.gn) resumo.push(box(num(d.gn, 1), 'γn'));
    }
    res.replaceChildren(
      el('div', { class: 'caixa' }, el('h3', { texto: 'Resultado' }), el('div', { class: 'numeros' }, resumo), verificacoes(r)),
      r.hipoteses && r.hipoteses.length ? el('div', { class: 'caixa' }, el('h3', { texto: 'Hipóteses' }),
        el('ul', { class: 'mem' }, r.hipoteses.map(h => el('li', { texto: h.texto })))) : null);
  } catch (err) {
    if (meu !== pedido) return;
    $('#desenho').replaceChildren();
    res.replaceChildren(el('div', { class: 'caixa' }, el('p', { class: 'nao', texto: 'Erro: ' + err.message })));
  }
}

async function iniciar() {
  ligarTema();
  try { APOIOS = (await pedir('/api/premoldado/ligacoes')).apoios || APOIOS; } catch { /* fica o padrão */ }
  indice();
  montar();
}
iniciar();
