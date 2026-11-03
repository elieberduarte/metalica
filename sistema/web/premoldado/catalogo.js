/* Catálogo de peças pré-moldadas (em desenvolvimento): o que o programa conhece de materiais e seções,
 * pela rota /api/premoldado/catalogo (premoldado/catalogo.py — valores das normas), e a calculadora das
 * propriedades geométricas das seções de vigas e terças (retangular, T, T invertido, I). */
'use strict';

const tabela = (cab, linhas) => el('div', { class: 'rolagem' }, el('table', { class: 'tab' },
  el('tr', {}, cab.map(t => el('th', { html: t }))),
  linhas.map(l => el('tr', {}, l.map((c, i) => el('td', { class: i ? 'r' : '', html: String(c) }))))));

function caixa(id, titulo, explica, ...conteudo) {
  return el('div', { class: 'caixa', id }, el('h3', { texto: titulo }), explica ? el('p', { class: 'explica', html: explica }) : null, ...conteudo);
}

// ------------------------------------------------------------------ seções de vigas e terças
const FORMAS = {
  retangular: { nome: 'Retangular', campos: [['h', 'Altura h', 60], ['bw', 'Largura b', 25]] },
  T: { nome: 'T (mesa em cima)', campos: [['h', 'Altura total h', 60], ['bf', 'Largura da mesa', 60], ['hf', 'Espessura da mesa', 10], ['bw', 'Largura da alma', 15]] },
  Tinv: { nome: 'T invertido (mesa embaixo)', campos: [['h', 'Altura total h', 60], ['bf', 'Largura da mesa', 50], ['hf', 'Espessura da mesa', 15], ['bw', 'Largura da alma', 20]] },
  I: { nome: 'I', campos: [['h', 'Altura total h', 80], ['bs', 'Mesa superior — largura', 40], ['hs', 'Mesa superior — espessura', 10],
    ['bw', 'Largura da alma', 12], ['bi', 'Mesa inferior — largura', 30], ['hi', 'Mesa inferior — espessura', 15]] },
};

/** retângulos (x0 centrado, y0 da base, b, h) de cada forma, em cm */
function retangulos(forma, v) {
  const R = (b, h, y) => ({ b, h, y });
  if (forma === 'retangular') return [R(v.bw, v.h, 0)];
  if (forma === 'T') return [R(v.bw, v.h - v.hf, 0), R(v.bf, v.hf, v.h - v.hf)];
  if (forma === 'Tinv') return [R(v.bf, v.hf, 0), R(v.bw, v.h - v.hf, v.hf)];
  return [R(v.bi, v.hi, 0), R(v.bw, v.h - v.hi - v.hs, v.hi), R(v.bs, v.hs, v.h - v.hs)];
}

function propriedades(rs, h) {
  const A = rs.reduce((s, r) => s + r.b * r.h, 0);
  const yc = rs.reduce((s, r) => s + r.b * r.h * (r.y + r.h / 2), 0) / A;
  const I = rs.reduce((s, r) => s + r.b * r.h ** 3 / 12 + r.b * r.h * (r.y + r.h / 2 - yc) ** 2, 0);
  return { A, yc, I, Wi: I / yc, Ws: I / (h - yc), i: Math.sqrt(I / A), peso: A / 1e4 * 25 };
}

function svgForma(rs, h, yc) {
  const bmax = Math.max(...rs.map(r => r.b));
  const esc = Math.min(260 / h, 300 / bmax), pad = 28;
  const W = bmax * esc + 2 * pad, H = h * esc + 2 * pad, cx = W / 2;
  const Y = y => pad + (h - y) * esc;
  const ret = rs.filter(r => r.h > 0 && r.b > 0).map(r =>
    `<rect x="${cx - r.b * esc / 2}" y="${Y(r.y + r.h)}" width="${r.b * esc}" height="${r.h * esc}" fill="var(--painel2)" stroke="currentColor"/>`).join('');
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="color:var(--texto)">${ret}
    <line x1="${pad / 2}" x2="${W - pad / 2}" y1="${Y(yc)}" y2="${Y(yc)}" stroke="var(--azul)" stroke-dasharray="5 3"/>
    <text x="${W - pad / 2}" y="${Y(yc) - 4}" font-size="11" text-anchor="end" fill="var(--azul)">CG (y = ${num(yc, 1)} cm)</text>
    <text x="${pad / 2 - 2}" y="${H / 2}" font-size="11" text-anchor="middle" fill="currentColor" transform="rotate(-90 ${pad / 2 - 2} ${H / 2})">h = ${num(h, 0)} cm</text></svg>`;
}

function calculadora() {
  const sel = el('select', { id: 's-forma' }, Object.entries(FORMAS).map(([k, f]) => el('option', { value: k, texto: f.nome })));
  const campos = el('div', { class: 'campos estreitos' });
  const saida = el('div', {});
  const desenho = el('div', { class: 'desenho' });
  const montar = () => {
    const f = FORMAS[sel.value];
    campos.replaceChildren(el('label', { for: 's-forma', texto: 'Forma' }), sel,
      ...f.campos.flatMap(([k, rot, v]) => [el('label', { for: 's-' + k, texto: rot + ' (cm)' }),
        el('input', { id: 's-' + k, value: String(v), oninput: calcular })]));
    calcular();
  };
  function calcular() {
    const f = FORMAS[sel.value], v = {};
    for (const [k] of f.campos) v[k] = parseFloat(($('#s-' + k, campos).value || '').replace(',', '.'));
    const rs = retangulos(sel.value, v);
    if (Object.values(v).some(x => !(x > 0)) || rs.some(r => r.h <= 0)) {
      saida.replaceChildren(el('p', { class: 'nao', texto: 'Medidas inválidas: as espessuras das mesas não podem passar da altura total.' }));
      desenho.replaceChildren();
      return;
    }
    const p = propriedades(rs, v.h);
    desenho.innerHTML = svgForma(rs, v.h, p.yc);
    saida.replaceChildren(tabela(['Propriedade', 'Valor'], [
      ['Área A<sub>c</sub>', num(p.A, 0) + ' cm²'], ['Peso próprio (25 kN/m³)', num(p.peso, 2) + ' kN/m'],
      ['Centro de gravidade (da base)', num(p.yc, 1) + ' cm'], ['Momento de inércia I<sub>c</sub>', num(p.I, 0) + ' cm⁴'],
      ['Módulo resistente — fibra inferior W<sub>i</sub>', num(p.Wi, 0) + ' cm³'], ['Módulo resistente — fibra superior W<sub>s</sub>', num(p.Ws, 0) + ' cm³'],
      ['Raio de giração i', num(p.i, 1) + ' cm']]));
  }
  sel.addEventListener('change', montar);
  montar();
  return el('div', { class: 'lado-a-lado' }, el('div', {}, campos), desenho, el('div', { style: 'flex:1; min-width:280px' }, saida));
}

// ------------------------------------------------------------------ o catálogo
async function carregar(agregado) {
  const c = await pedir('/api/premoldado/catalogo?agregado=' + encodeURIComponent(agregado || 'granito'));
  const raiz = $('#conteudo');
  const selAg = el('select', { id: 'c-agregado', onchange: () => carregar(selAg.value) },
    c.agregados.map(a => el('option', { value: a, texto: a, selected: a === c.agregado || undefined })));
  raiz.replaceChildren(
    caixa('concretos', 'Concretos', 'Classes C20 a C90 (NBR 6118, 8.2). f<sub>cd</sub> com γ<sub>c</sub> = 1,4 (pré-moldado) e 1,3 (pré-fabricado com o controle da NBR 9062, 8.1); '
      + 'os módulos dependem do agregado (α<sub>E</sub>, 8.2.8).',
      el('div', { class: 'campos estreitos' }, el('label', { for: 'c-agregado', texto: 'Agregado graúdo' }), selAg),
      tabela(['Classe', 'f<sub>ck</sub> (MPa)', 'f<sub>cd</sub> γ 1,4', 'f<sub>cd</sub> γ 1,3', 'f<sub>ct,m</sub>', 'f<sub>ctk,inf</sub>', 'f<sub>ctk,sup</sub>',
        'E<sub>ci</sub> (MPa)', 'E<sub>cs</sub> (MPa)', 'ε<sub>c2</sub> (‰)', 'ε<sub>cu</sub> (‰)'],
      c.concretos.map(k => [k.classe + (k.grupo === 'II' ? ' <span class="mem">(grupo II)</span>' : ''), k.fck, num(k.fcd_14), num(k.fcd_13), num(k.fctm), num(k.fctk_inf),
        num(k.fctk_sup), num(k.Eci, 0), num(k.Ecs, 0), num(k.eps_c2), num(k.eps_cu)]))),
    caixa('acos', 'Aços para armadura', 'NBR 6118, 8.3 e NBR 7480. f<sub>yd</sub> com γ<sub>s</sub> = 1,15 (pré-moldado) e 1,10 (pré-fabricado, NBR 9062, 8.1).',
      tabela(['Aço', 'f<sub>yk</sub> (MPa)', 'f<sub>yd</sub> γ 1,15', 'f<sub>yd</sub> γ 1,10', 'E<sub>s</sub> (MPa)', 'ε<sub>yd</sub> (‰)'],
        c.acos.map(a => [a.nome, num(a.fyk, 0), num(a.fyd_115, 1), num(a.fyd_110, 1), num(a.Es, 0), num(a.eps_yd)]))),
    caixa('bitolas', 'Bitolas e comprimento de ancoragem', 'Área e massa nominais (NBR 7480). ℓ<sub>b</sub> = (ø/4)·f<sub>yd</sub>/f<sub>bd</sub> para CA-50 nervurado, '
      + 'boa aderência, sem gancho, γ<sub>c</sub> = 1,4 (NBR 6118, 9.4.2.4) — em cm, arredondado para cima. Má aderência (η<sub>2</sub> = 0,7): ℓ<sub>b</sub>/0,7.',
      tabela(['ø (mm)', 'Área (cm²)', 'Massa (kg/m)', ...c.classes_ancoragem.map(k => 'ℓ<sub>b</sub> ' + k)],
        c.bitolas.map(b => [num(b.bitola, 1), num(b.area, 3), num(b.massa, 3), ...c.classes_ancoragem.map(k => b.lb[k])]))),
    caixa('cobrimentos', 'Cobrimentos nominais', 'NBR 6118, Tabela 7.2 (concreto armado), em mm. Pré-fabricado com controle rigoroso: Δc = 5 mm (7.4.7.4) — a coluna "pré-fabricado" já desconta. '
      + 'Em contato com o solo não se reduz. A classe mínima de concreto é a da Tabela 7.1.',
      tabela(['Classe de agressividade', 'Laje', 'Viga / pilar', 'Laje — pré-fabricado', 'Viga / pilar — pré-fabricado', 'Contato com o solo', 'Concreto mínimo'],
        c.cobrimentos.map(k => [k.caa, k.laje, k.viga_pilar, k.laje_pf, k.viga_pilar_pf, k.solo, k.classe_minima]))),
    caixa('pilares', 'Seções de pilar', 'As seções retangulares que o dimensionamento do galpão experimenta (da mais leve para a mais pesada). '
      + 'Pilar engastado na base e livre no topo (ℓ<sub>e</sub> = 2L): a altura máxima pela esbeltez — até λ = 90 vale o método da curvatura aproximada; '
      + 'até 140, o pilar-padrão acoplado ao diagrama M-N-1/r; acima de 140 a NBR 6118 (15.8.1) não admite pilar. '
      + 'Armadura longitudinal: mínima 0,15·N<sub>d</sub>/f<sub>yd</sub> ≥ 0,4 % de A<sub>c</sub>; máxima 8 % contando as emendas, isto é, 4 % fora delas (17.3.5.3).',
      tabela(['b × h (cm)', 'A<sub>c</sub> (cm²)', 'Peso (kN/m)', 'I<sub>x</sub> (cm⁴)', 'I<sub>y</sub> (cm⁴)', 'i<sub>mín</sub> (cm)', 'L máx λ 90 (m)', 'L máx λ 140 (m)',
        'A<sub>s,mín</sub> (cm²)', 'A<sub>s,máx</sub> (cm²)'],
        c.secoes_pilar.map(s => [`${num(s.b, 0)} × ${num(s.h, 0)}`, num(s.A, 0), num(s.peso), num(s.Ix, 0), num(s.Iy, 0), num(s.i_min, 1),
          num(s.L90), num(s.L140), num(s.As_min), num(s.As_max, 1)]))),
    caixa('vigas', 'Seções de vigas e terças', 'Propriedades geométricas da seção bruta de concreto. As fôrmas padrão da fábrica ainda não estão cadastradas: '
      + 'informe as medidas para ver área, peso, centro de gravidade, inércia e módulos resistentes.', calculadora()),
  );
  if (location.hash) { const alvo = document.getElementById(location.hash.slice(1)); if (alvo) alvo.scrollIntoView(); }
}

ligarTema();
carregar('granito').catch(e => { $('#conteudo').replaceChildren(el('div', { class: 'caixa' }, el('p', { class: 'nao', texto: 'Erro: ' + e.message }))); });
