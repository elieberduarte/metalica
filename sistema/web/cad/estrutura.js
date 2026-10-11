// CAD 2D: lançar a estrutura na planta (menu Estrutura).
//
// O passo convencional do projeto: sobre o arquitetônico e os eixos da Planta de lançamento, o
// engenheiro põe cada elemento — pilar, viga, fundação, consolo — com a seção e os níveis, e só
// depois gera o 3D para conferir. Os elementos são entidades comuns do desenho (o pilar é uma
// polilinha fechada, a viga uma linha, a fundação e o consolo polilinhas) na camada ESTRUTURA, com
// `atributos.elemento` dizendo o que são; o DXF continua saindo igual. O 3D é gerado no servidor
// (nucleo3d/de_planta_estrutura.py) a partir desses atributos.
//
// Serve para os dois materiais: concreto (seção retangular, T, I ou U, em cm — o catálogo do
// pré-moldado) e aço (perfil do catálogo da Metálica). Os níveis (piso, boca do cálice, topo dos
// pilares…) ficam no projeto e valem para o CAD e para o 3D.
//
// Os métodos são copiados para a classe do CAD (cad.js), como os de lancamento.js. As ferramentas
// ficam na barra da direita, a da disciplina (pedido do usuário, 30/09: a barra da esquerda é só a
// edição geral do desenho): na Metálica, pilar e viga de perfil, chapa, furo e parafuso; no
// pré-moldado, pilar, viga, consolo, fundação e a tesoura de concreto (viga de cobertura). O menu
// Estrutura continua chamando as mesmas.

import { criar, dist } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoAlterar, ComandoComposto, ComandoRemover } from './nucleo/comandos.js';
import { Ferramenta, paraMilimetros, naUnidade, unidadeAtual } from './ferramentas.js';

export const CAMADA_ESTRUTURA = 'ESTRUTURA';
const CHAVE = 'cad.estrutura.medidas';
const $ = (s, r = document) => r.querySelector(s);
const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  let j = null;
  try { j = await r.json(); } catch { j = null; }
  if (!r.ok || (j && j.erro)) throw new Error((j && j.erro) || `${r.status} ${r.statusText}`);
  return j;
}

// as medidas (mm; as seções de concreto em cm): o padrão, o que o usuário mudou por último
const PADRAO = {
  material: 'concreto', secao_tipo: 'retangular', b: 30, h: 40, bf: 30, hf: 10, bw: 12, B: 50, t: 8, tf: 8, vh: 50,
  perfil: 'W 310×38,7', aco: 'ASTM A572 Gr.50', nivel_base: 0, nivel_topo: 5100, rotacao: 0, ancora: 4,
  // a viga: o nível dado é o do eixo, o da face de cima ou o da face de baixo (pedido do usuário, 06/10)
  viga_alinhamento: { aco: 'eixo', concreto: 'topo' },
  // o pilar de aço: um perfil (W, U…) ou um poste circular (tubo TC do catálogo — pedido do usuário, 06/10)
  pilar_aco: 'perfil', perfil_poste: 'TC 168,3×4,5',
  fund_tipo: 'sapata', fund_a: 2000, fund_b: 2000, fund_h: 500, cons_c: 300, cons_h: 400, cons_b: 300,
  // a tesoura de concreto (viga de cobertura, seção I em cm): a altura no apoio e no meio, os níveis do apoio nas pontas
  tes_bf: 30, tes_hf: 10, tes_bw: 12, tes_h: 60, tes_hm: 120, tes_forma: 'duas águas', nivel_fim: 5100,
  // chapa, furo e parafuso (mm)
  chapa_esp: 12.5, chapa_aco: 'ASTM A36', furo_d: 22, paraf_d: 20, paraf_L: 70,
  // placa de fechamento, laje e escada (mm)
  pn_tipo: 'alveolar', pn_orient: 'vertical', pn_esp: 150, pn_mod: 1250,
  laje_tipo: 'alveolar', laje_esp: 200, laje_capa: 50, laje_sentido: 'x', laje_mod: 1250,
  esc_larg: 1200, esc_espelho: 180, esc_t: 120,
};
const SECOES = ['retangular', 'T', 'I', 'U'];
const CAMPOS_SECAO = { retangular: ['b', 'h'], T: ['bf', 'hf', 'bw', 'h'], I: ['bf', 'hf', 'bw', 'h'], U: ['B', 'h', 't', 'tf'] };
const ROTULO = { b: 'b (largura, cm)', h: 'h (altura, cm)', bf: 'mesa b (cm)', hf: 'mesa h (cm)', bw: 'alma (cm)', B: 'largura externa (cm)', t: 'parede (cm)', tf: 'fundo (cm)' };

/** A altura nominal pelo nome ("W 250×17,9" → 250; "U 6"×12,2" → 6×25,4), senão a do catálogo. */
function alturaNominal(p) {
  const m = /^[A-Za-z]+\s*([\d.,]+)\s*(")?/.exec(String(p.nome || ''));
  if (!m) return +p.d || 0;
  const v = parseFloat(m[1].replace(',', '.'));
  return m[2] ? v * 25.4 : v;
}
/** O nome do perfil na lista: a cantoneira em polegada leva junto a medida em mm (aba × espessura), como vem no
 *  projeto ("L38x38") — L 1½"×1/8" (38,1×3,18 mm) (07/10). O valor continua sendo o nome do catálogo. */
export function rotuloPerfil(nome, p) {
  if (!p || !/^L\s/i.test(nome) || !nome.includes('"') || !(+p.bf > 0)) return nome;
  const mm = (v) => String(+(+v).toFixed(2)).replace('.', ',');
  const t = +p.tf || +p.tw || 0;
  return `${nome}  (${mm(p.bf)}×${t ? mm(t) : '?'} mm)`;
}

/** Os perfis do catálogo em grupos, para a lista do painel: cada família na sua seção e, dentro dela, pela altura e
 *  depois pelo peso — o catálogo vem pelo peso, e os W 250 saíam espalhados entre os W 200 e os W 310 (06/10). */
function gruposDePerfis(fam) {
  const ordem = (a, b) => (alturaNominal(a) - alturaNominal(b)) || ((+a.bf || 0) - (+b.bf || 0)) || ((+a.massa || 0) - (+b.massa || 0));
  const nomes = (lista) => [...lista].sort(ordem).map(p => p.nome).filter(Boolean);
  const grupos = [];
  const I = fam.I || [];
  const w = I.filter(p => /^W\s/i.test(p.nome)), hp = I.filter(p => /^HP\s/i.test(p.nome)), outrosI = I.filter(p => !/^(W|HP)\s/i.test(p.nome));
  if (w.length) grupos.push(['W — laminado', nomes(w)]);
  if (hp.length) grupos.push(['HP — laminado', nomes(hp)]);
  if (outrosI.length) grupos.push(['I', nomes(outrosI)]);
  if ((fam.U || []).length) grupos.push(['U — laminado', nomes(fam.U)]);
  if ((fam.Ue || []).length) grupos.push(['U e Ue — dobrado', nomes(fam.Ue)]);
  if ((fam.L || []).length) grupos.push(['L — cantoneira', [...fam.L].sort((a, b) => ((+a.bf || 0) - (+b.bf || 0)) || ((+a.massa || 0) - (+b.massa || 0))).map(p => p.nome)]);
  const tubos = fam.tubo || [];
  for (const [pre, titulo] of [['TC', 'TC — tubo circular'], ['TQ', 'TQ — tubo quadrado'], ['TR', 'TR — tubo retangular']]) {
    const t = tubos.filter(p => new RegExp(`^${pre}\\s`, 'i').test(p.nome));
    if (t.length) grupos.push([titulo, nomes(t)]);
  }
  const usados = new Set(grupos.flatMap(([, n]) => n));
  const resto = Object.values(fam).flat().filter(p => p && p.nome && !usados.has(p.nome));
  if (resto.length) grupos.push(['Outros', nomes(resto)]);
  return grupos;
}

/**
 * A seção do perfil de aço na planta (mm, no sistema do pilar com giro 0°), como o 3D a coloca: a altura d no Y, a mesa
 * no X; o U e o Ue com a alma do lado −X e as abas para +X; a cantoneira com o canto em −X −Y; a peça pelo centro de
 * gravidade — antes o pilar de aço era um retângulo de 150 × 300 qualquer que fosse o perfil (pedido do usuário, 06/10).
 * null sem as medidas.
 */
function secaoNaPlanta(p) {
  if (!p) return null;
  const nome = String(p.nome || ''), d = +p.d || 0, b = +p.bf || 0, tw = +p.tw || 0, tf = +p.tf || tw;
  let pts = null;
  if (/^TC\s/i.test(nome) && d > 0) pts = circulo([0, 0], d);
  else if (p.tipo === 'tubo' && d > 0 && b > 0) pts = [[-b / 2, -d / 2], [b / 2, -d / 2], [b / 2, d / 2], [-b / 2, d / 2]];
  else if (p.tipo === 'I' && d > 0 && b > 0 && tw > 0 && tf > 0) {
    pts = [[-b / 2, -d / 2], [b / 2, -d / 2], [b / 2, -d / 2 + tf], [tw / 2, -d / 2 + tf], [tw / 2, d / 2 - tf], [b / 2, d / 2 - tf],
           [b / 2, d / 2], [-b / 2, d / 2], [-b / 2, d / 2 - tf], [-tw / 2, d / 2 - tf], [-tw / 2, -d / 2 + tf], [-b / 2, -d / 2 + tf]];
  } else if ((p.tipo === 'U' || p.tipo === 'Ue') && d > 0 && b > 0 && tw > 0) {
    const nums = (nome.match(/[\d.,]+/g) || []).map(x => parseFloat(x.replace(',', '.')));
    const aba = /^Ue\s/i.test(nome) && nums.length >= 4 ? nums[2] : 0;          // o enrijecedor do Ue
    pts = aba > tf
      ? [[0, -d / 2], [b, -d / 2], [b, -d / 2 + aba], [b - tf, -d / 2 + aba], [b - tf, -d / 2 + tf], [tw, -d / 2 + tf], [tw, d / 2 - tf],
         [b - tf, d / 2 - tf], [b - tf, d / 2 - aba], [b, d / 2 - aba], [b, d / 2], [0, d / 2]]
      : [[0, -d / 2], [b, -d / 2], [b, -d / 2 + tf], [tw, -d / 2 + tf], [tw, d / 2 - tf], [b, d / 2 - tf], [b, d / 2], [0, d / 2]];
  } else if (p.tipo === 'L' && b > 0 && tw > 0) {
    pts = [[0, 0], [b, 0], [b, tw], [tw, tw], [tw, b], [0, b]];
  }
  if (!pts) return null;
  // pelo centro de gravidade do contorno
  let A = 0, cx = 0, cy = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], k = x0 * y1 - x1 * y0;
    A += k; cx += (x0 + x1) * k; cy += (y0 + y1) * k;
  }
  if (Math.abs(A) < 1e-9) return pts;
  cx /= 3 * A; cy /= 3 * A;
  return pts.map(([x, y]) => [x - cx, y - cy]);
}

/** o pilar de aço que é poste circular (tubo TC) */
const ehPoste = (M) => M.material === 'aco' && M.pilar_aco === 'poste';
/** o diâmetro (mm) do tubo circular pelo nome ("TC 168,3×4,5" → 168,3) */
function diametroDoTubo(nome) {
  const m = /TC\s*([\d.,]+)/i.exec(String(nome || ''));
  return m ? parseFloat(m[1].replace(',', '.')) : 150;
}
/** o círculo de diâmetro d (mm) em c, como polilinha (o contorno do poste na planta) */
function circulo(c, d, n = 32) {
  return Array.from({ length: n }, (_, i) => [c[0] + d / 2 * Math.cos(2 * Math.PI * i / n), c[1] + d / 2 * Math.sin(2 * Math.PI * i / n)]);
}

/** a seção como o 3D e o cálculo leem: {tipo, b, h, …} em cm ou {perfil, aco}; `pilar`: o poste circular vale */
function secaoDe(M, pilar = false) {
  if (pilar && ehPoste(M)) return { perfil: M.perfil_poste, aco: M.aco };
  if (M.material === 'aco') return { perfil: M.perfil, aco: M.aco };
  const s = { tipo: M.secao_tipo };
  for (const k of CAMPOS_SECAO[M.secao_tipo]) s[k] = M[k];
  return s;
}

function textoSecao(a) {
  // a tesoura de aço: os perfis dos banzos e da alma
  if (a.perfis) return [...new Set([a.perfis.banzo_sup, a.perfis.banzo_inf])].filter(Boolean).join(' / ') + (a.perfis.diagonal ? ` · alma ${a.perfis.diagonal}` : '');
  const s = a.secao || {};
  if (s.perfil) return s.perfil;
  if (s.tipo === 'T' || s.tipo === 'I') return `${s.tipo} ${s.bf}×${s.hf} / alma ${s.bw}, h ${s.h}`;
  if (s.tipo === 'U') return `U ${s.B}×${s.h} (par. ${s.t}, fundo ${s.tf})`;
  return `${s.b}×${s.h}`;
}

/** largura em planta da viga (mm) para a prévia e o contorno desenhado */
function larguraViga(M, cat) {
  if (M.material === 'aco') return +((cat && cat.dados && cat.dados[M.perfil]) || {}).bf || 150;
  const s = M.secao_tipo;
  return 10 * (s === 'retangular' ? M.b : s === 'U' ? M.B : M.bf);
}

/** A largura em planta (mm) da viga gravada: a mesa do perfil de aço (bf do catálogo) ou a largura da seção de
 *  concreto (cm); 0 se não se sabe. */
function larguraDaVigaGravada(a, cat) {
  const s = a.secao || {};
  if (s.perfil) return +((cat && cat.dados && cat.dados[s.perfil]) || {}).bf || 0;
  const cm = s.tipo === 'U' ? s.B : s.tipo === 'retangular' || s.b ? s.b : s.bf;
  return cm > 0 ? 10 * cm : 0;
}

/** o que o nível da viga marca: 'eixo', 'topo' (a face de cima) ou 'base' (a face de baixo) */
const ROTULO_ALINHAMENTO = { eixo: 'eixo', topo: 'face de cima', base: 'face de baixo' };
function alinhamentoDaViga(M) {
  const padrao = M.material === 'aco' ? 'eixo' : 'topo';
  return ((M.viga_alinhamento || {})[M.material === 'aco' ? 'aco' : 'concreto']) || padrao;
}

/**
 * O desenho da tesoura em linhas de eixo (a elevação desenhada no CAD: banzos, diagonais, montantes) como as barras do
 * elemento "trelica": [u0, v0, u1, v1, papel], u ao longo do vão (0 no ponto mais à esquerda) e v na altura (0 no banzo
 * inferior — a linha horizontal mais comprida). O arco vira trechos retos entre os nós (as pontas das barras que chegam
 * nele) e o raio fica anotado para a calandra; as linhas no alto do desenho, pouco inclinadas, são o banzo superior; as
 * em pé, montantes; o resto, diagonais. Devolve {barras, vao, altura, raio, n}.
 */
export function desenhoDaTesoura(ents) {
  const segs = [], arcos = [];
  for (const e of ents) {
    if (e.tipo === 'linha') segs.push([e.a, e.b]);
    else if (e.tipo === 'polilinha') { const v = e.vertices; for (let i = 0; i < v.length - 1; i++) segs.push([v[i], v[i + 1]]); if (e.fechada && v.length > 2) segs.push([v[v.length - 1], v[0]]); }
    else if (e.tipo === 'arco') arcos.push(e);
  }
  const ptArco = (a, g) => [a.centro[0] + a.raio * Math.cos(g * Math.PI / 180), a.centro[1] + a.raio * Math.sin(g * Math.PI / 180)];
  const vaoArco = (a) => { let s = a.fim - a.inicio; while (s <= 0) s += 360; return s; };
  const pts = segs.flat();
  for (const a of arcos) for (let i = 0; i <= 16; i++) pts.push(ptArco(a, a.inicio + vaoArco(a) * i / 16));
  if (pts.length < 2) return null;
  const u0 = Math.min(...pts.map(p => p[0])), u1 = Math.max(...pts.map(p => p[0]));
  // o banzo inferior: a linha horizontal mais comprida
  const horiz = segs.filter(([a, b]) => Math.abs(b[1] - a[1]) <= 0.02 * Math.abs(b[0] - a[0]) + 0.5);
  const inf = horiz.sort((x, y) => Math.abs(y[1][0] - y[0][0]) - Math.abs(x[1][0] - x[0][0]))[0];
  // a altura do banzo inferior (para achá-lo) e o apoio: o ponto mais baixo da tesoura (a ponta da peça externa que senta
  // no pilar) — é ele que vai no nível escolhido (06/10: "o suporte era para ter ficado no 7,85")
  const yInf = inf ? (inf[0][1] + inf[1][1]) / 2 : Math.min(...pts.map(p => p[1]));
  const v0 = Math.min(...pts.map(p => p[1]));
  const vMax = Math.max(...pts.map(p => p[1])), H = Math.max(1, vMax - v0);
  const tol = Math.max(2, H * 0.01);
  // a altura do alto do desenho em cada u (para achar o banzo superior desenhado em linhas)
  const topoEm = (u) => {
    let t = -Infinity;
    for (const [a, b] of segs) { const lo = Math.min(a[0], b[0]), hi = Math.max(a[0], b[0]); if (u < lo - 1e-6 || u > hi + 1e-6) continue;
      t = Math.max(t, hi - lo < 1e-6 ? Math.max(a[1], b[1]) : a[1] + (b[1] - a[1]) * (u - a[0]) / (b[0] - a[0])); }
    for (const a of arcos) { const d = u - a.centro[0]; if (Math.abs(d) <= a.raio) t = Math.max(t, a.centro[1] + Math.sqrt(a.raio * a.raio - d * d)); }
    return t;
  };
  const r1 = (x) => Math.round(x * 10) / 10;
  const barras = [];
  const add = (a, b, papel) => { if (Math.hypot(b[0] - a[0], b[1] - a[1]) >= 5) barras.push([r1(a[0] - u0), r1(a[1] - v0), r1(b[0] - u0), r1(b[1] - v0), papel]); };
  // tudo o que foi selecionado entra (a peça externa em pé nas pontas, que desce até o apoio, também — 06/10)
  for (const [a, b] of segs) {
    const dx = b[0] - a[0], dy = b[1] - a[1], m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    let papel;
    if (Math.abs(dy) <= 0.02 * Math.abs(dx) + 0.5 && Math.abs(m[1] - yInf) <= tol) papel = 'banzo_inf';
    else if (m[1] >= topoEm(m[0]) - tol && Math.abs(dy) < Math.tan(35 * Math.PI / 180) * Math.abs(dx)) papel = 'banzo_sup';
    else if (Math.abs(dx) <= 0.05 * Math.abs(dy)) papel = 'montante';
    else papel = 'diagonal';
    add(a, b, papel);
  }
  // o arco: trechos retos entre os nós
  let raio = 0;
  for (const a of arcos) {
    raio = Math.max(raio, a.raio);
    const rel = (q) => ((((Math.atan2(q[1] - a.centro[1], q[0] - a.centro[0]) * 180 / Math.PI) - a.inicio) % 360) + 360) % 360;
    const span = vaoArco(a), ts = new Set([0, span]);
    for (const q of segs.flat()) {
      if (Math.abs(Math.hypot(q[0] - a.centro[0], q[1] - a.centro[1]) - a.raio) > tol) continue;
      const t = rel(q); if (t >= -1e-6 && t <= span + 1e-6) ts.add(Math.round(t * 1e6) / 1e6);
    }
    const lista = [...ts].sort((x, y) => x - y);
    for (let i = 0; i < lista.length - 1; i++) if (lista[i + 1] - lista[i] > 1e-4) add(ptArco(a, a.inicio + lista[i]), ptArco(a, a.inicio + lista[i + 1]), 'banzo_sup');
  }
  return { barras, vao: r1(u1 - u0), altura: r1(H), raio: raio ? r1(raio) : null, n: barras.length, baixoDoBanzo: r1(yInf - v0), origem: [u0, v0] };
}

/** o cruzamento das retas p0–p1 e q0–q1 (infinitas), ou null */
function cruzamentoRetas(p0, p1, q0, q1) {
  const r = [p1[0] - p0[0], p1[1] - p0[1]], s = [q1[0] - q0[0], q1[1] - q0[1]], den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((q0[0] - p0[0]) * s[1] - (q0[1] - p0[1]) * s[0]) / den;
  return [p0[0] + r[0] * t, p0[1] + r[1] * t];
}

/** o ponto `p` dentro do polígono `vs` (par-ímpar) */
function dentroDoContorno(p, vs) {
  let dentro = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const [xi, yi] = vs[i], [xj, yj] = vs[j];
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

/** a menor distância de `p` às arestas do polígono fechado `vs` */
function distanciaAoContorno(p, vs) {
  let m = Infinity;
  for (let i = 0; i < vs.length; i++) {
    const a = vs[i], b = vs[(i + 1) % vs.length], dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
    const t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) : 0;
    m = Math.min(m, Math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t));
  }
  return m;
}

/** o centro de gravidade do polígono; null se degenerado */
function centroDoContorno(vs) {
  let A = 0, cx = 0, cy = 0;
  for (let i = 0; i < vs.length; i++) {
    const [x0, y0] = vs[i], [x1, y1] = vs[(i + 1) % vs.length], k = x0 * y1 - x1 * y0;
    A += k; cx += (x0 + x1) * k; cy += (y0 + y1) * k;
  }
  return Math.abs(A) < 1e-9 ? null : [cx / (3 * A), cy / (3 * A)];
}

/** o retângulo b × h (mm) centrado em c, girado (graus) */
function retangulo(c, b, h, graus) {
  const r = (graus || 0) * Math.PI / 180, co = Math.cos(r), se = Math.sin(r);
  return [[-b / 2, -h / 2], [b / 2, -h / 2], [b / 2, h / 2], [-b / 2, h / 2]].map(([x, y]) => [c[0] + x * co - y * se, c[1] + x * se + y * co]);
}

// ------------------------------------------------------------ as ferramentas

class FerramentaElemento extends Ferramenta {
  static grupo = 'estrutura';
  get M() { return this.editor.medidasEstrutura; }
  /** O nível que vai para o elemento: o nome do nível do projeto escolhido no painel (vinculado: a cota segue o
   *  nível quando ele muda — pedido do usuário, 06/10) ou o número digitado. */
  nv(k) {
    const nome = (this.M.vinculo || {})[k];
    const lista = this.editor._niveisProjeto || [];
    return nome && lista.some(n => n.nome === nome) ? nome : this.M[k];
  }
  ativar() { super.ativar(); this.editor._painelEstrutura(this.constructor.id); }
  desativar() { super.desativar(); this.editor._fecharPainelEstrutura(); }
  cancelar() { this.reiniciar(); this.editor.ativarFerramenta('selecionar'); }
  adicionar(ents, rotulo) {
    this.editor._garantirCamadaEstrutura();
    this.editor.executar(new ComandoAdicionar(ents, rotulo));
  }
}

/** Os 9 pontos de inserção do pilar (07/10, pedido do usuário: "como no Eberick, com o Tab vai mudando o ponto"),
 *  na ordem do Tab: o centro e depois a volta pelos cantos e meios das faces. Índice = (linha + 1) × 3 + (coluna + 1),
 *  com a linha de baixo (−1) para a de cima (+1) e a coluna da esquerda (−1) para a direita (+1), na tela. */
const ANCORAS = ['canto de baixo à esquerda', 'meio da face de baixo', 'canto de baixo à direita', 'meio da face esquerda', 'centro',
  'meio da face direita', 'canto de cima à esquerda', 'meio da face de cima', 'canto de cima à direita'];
const ORDEM_TAB = [4, 6, 7, 8, 5, 2, 1, 0, 3];

/** Pilar: um clique no ponto de inserção (o cruzamento de eixos dá snap) — Tab troca o ponto (centro, cantos, meios das
 *  faces); R gira 90° */
export class FerramentaPilar extends FerramentaElemento {
  static id = 'estr_pilar'; static nome = 'Pilar'; static dica = 'Pilar: clique no ponto de inserção (o cruzamento dos eixos dá snap) · Tab troca o ponto (centro, cantos, meios das faces) · R gira 90° · Esc sai';
  reiniciar() { super.reiniciar(); this.atual = null; }
  onMover(p) { this.atual = p; this.desenhar(); }
  ativar() {
    super.ativar();
    // o cursor entrando no desenho tira o foco do painel: o Tab volta a ser da ferramenta (no campo, ele passa ao
    // campo seguinte, como em qualquer formulário)
    this._soltarFoco = () => { const a = document.activeElement; if (a && this.editor._painelEstr && this.editor._painelEstr.contains(a)) a.blur(); };
    this.editor.el.canvas.addEventListener('pointerenter', this._soltarFoco);
  }
  desativar() { if (this._soltarFoco) this.editor.el.canvas.removeEventListener('pointerenter', this._soltarFoco); super.desativar(); }
  /** o deslocamento do ponto de inserção ao centro do pilar (mm): o canto ou o meio da face pela caixa do contorno */
  _ancora() {
    const a = Number.isInteger(this.M.ancora) ? this.M.ancora : 4;
    if (a === 4) return [0, 0];
    const vs = this.contorno([0, 0]), xs = vs.map(q => q[0]), ys = vs.map(q => q[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const i = (a % 3) - 1, j = Math.floor(a / 3) - 1;
    return [i < 0 ? x0 : i > 0 ? x1 : (x0 + x1) / 2, j < 0 ? y0 : j > 0 ? y1 : (y0 + y1) / 2];
  }
  /** o centro do pilar para o clique em `p` (o ponto de inserção) */
  centroPelo(p) { const d = this._ancora(); return [p[0] - d[0], p[1] - d[1]]; }
  /** o contorno na planta: o retângulo do pilar ou o círculo do poste */
  contorno(c) {
    const M = this.M;
    if (ehPoste(M)) return circulo(c, diametroDoTubo(M.perfil_poste));
    if (M.material === 'aco') {
      const cat = this.editor._catalogoEstrutura;
      const loc = secaoNaPlanta(cat && cat.dados && cat.dados[M.perfil]);
      if (loc) {
        const r = (M.rotacao || 0) * Math.PI / 180, co = Math.cos(r), se = Math.sin(r);
        return loc.map(([x, y]) => [c[0] + x * co - y * se, c[1] + x * se + y * co]);
      }
    }
    const [b, h] = M.material === 'aco' ? [150, 300] : [M.b * 10, M.h * 10];
    return retangulo(c, b, h, M.rotacao);
  }
  desenhar() {
    if (!this.atual) return;
    const M = this.M;
    const c = this.centroPelo(this.atual), vs = this.contorno(c);
    // os 9 pontos de inserção em volta do pilar, o escolhido maior (como no Eberick)
    const xs = vs.map(q => q[0]), ys = vs.map(q => q[1]);
    const X = [Math.min(...xs), (Math.min(...xs) + Math.max(...xs)) / 2, Math.max(...xs)], Y = [Math.min(...ys), (Math.min(...ys) + Math.max(...ys)) / 2, Math.max(...ys)];
    const r = 4 / ((this.editor.tela.vp || {}).z || 1), a = Number.isInteger(M.ancora) ? M.ancora : 4;   // 4 px na tela, em qualquer zoom
    const pontos = [];
    for (let k = 0; k < 9; k++) {
      const q = k === 4 ? c : [X[k % 3], Y[Math.floor(k / 3)]];
      pontos.push(criar({ tipo: 'circulo', camada: CAMADA_ESTRUTURA, centro: q, raio: k === a ? 2.2 * r : r }));
    }
    this.editor.previa([criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, vertices: vs, fechada: true }), ...pontos]);
    this.editor.medida(`${ehPoste(M) ? `poste ${M.perfil_poste}` : M.material === 'aco' ? M.perfil : `${M.b} × ${M.h} cm`} · ${ANCORAS[a]}`);
  }
  onPonto(clique) {
    const M = this.M;
    const p = this.centroPelo(clique);
    const contorno = this.contorno(p);
    const xs = contorno.map(q => q[0]), ys = contorno.map(q => q[1]);
    const [b, h] = [Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
    const marca = this.editor._proximaMarca('pilar');
    const ent = criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, vertices: contorno, fechada: true,
      atributos: { elemento: 'pilar', material: M.material, secao: secaoDe(M, true), nivel_base: this.nv('nivel_base'), nivel_topo: this.nv('nivel_topo'),
                   rotacao: M.rotacao, marca, centro: [p[0], p[1]], ...(ehPoste(M) ? { forma: 'poste circular' } : {}) } });
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [p[0] + b / 2 + 150, p[1] + h / 2 + 100], texto: marca, altura: 2.5,
      atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot], `Pilar ${marca}`);
    this.dica(`${marca} lançado · próximo pilar, ou Esc`);
  }
  onTecla(ev) {
    if (ev.key === 'r' || ev.key === 'R') { this.M.rotacao = (this.M.rotacao + 90) % 180; this.editor._guardarMedidas(); this.editor._painelEstrutura('estr_pilar'); this.desenhar(); return true; }
    if (ev.key === 'Tab') {
      const a = Number.isInteger(this.M.ancora) ? this.M.ancora : 4, i = ORDEM_TAB.indexOf(a);
      this.M.ancora = ORDEM_TAB[(i + (ev.shiftKey ? ORDEM_TAB.length - 1 : 1)) % ORDEM_TAB.length];
      this.editor._guardarMedidas(); this.editor._painelEstrutura('estr_pilar'); this.desenhar();
      this.dica(`Ponto de inserção: ${ANCORAS[this.M.ancora]} (Tab o próximo, Shift+Tab o anterior)`);
      return true;
    }
    return false;
  }
}

/** Viga: dois cliques (centros dos pilares, com snap); a face de cima no nível informado */
export class FerramentaViga extends FerramentaElemento {
  static id = 'estr_viga'; static nome = 'Viga'; static dica = 'Viga: clique no início (o centro do pilar dá snap) · depois no fim · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  /** A ponta da viga dentro do contorno de um pilar vai para o centro dele (o centro de gravidade, de onde o 3D
   *  levanta o pilar): o clique na mesa do pilar deixava a viga fora do eixo (06/10, 129 mm na V1). */
  _noPilar(p) {
    for (const e of this.editor.doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo !== 'polilinha' || a.elemento !== 'pilar' || !e.vertices || e.vertices.length < 3 || !this.editor.doc.visivel(e)) continue;
      // dentro ou na borda (o clique na quina da mesa cai em cima do contorno)
      const tol = Math.max(2, 4 / ((this.editor.tela.vp || {}).z || 1));
      if (!dentroDoContorno(p, e.vertices) && distanciaAoContorno(p, e.vertices) > tol) continue;
      const c = centroDoContorno(e.vertices);
      if (c) return c;
    }
    return p;
  }
  onMover(p) {
    p = this._noPilar(p);
    this.ultimo = p;
    if (!this.a) return;
    const w = larguraViga(this.M, this.editor._catalogoEstrutura), d = dist(this.a, p);
    if (d < 1) return;
    const n = [-(p[1] - this.a[1]) / d * w / 2, (p[0] - this.a[0]) / d * w / 2];
    this.editor.previa([
      criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p }),
      criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true, vertices: [[this.a[0] + n[0], this.a[1] + n[1]], [p[0] + n[0], p[1] + n[1]], [p[0] - n[0], p[1] - n[1]], [this.a[0] - n[0], this.a[1] - n[1]]] }),
    ]);
    this.editor.medida(`${numero(d)} mm`);
  }
  onPonto(p, ev) {
    if (!ev || !ev.digitado) p = this._noPilar(p);
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no fim da viga (ou digite o comprimento e Enter)'); return; }
    if (dist(this.a, p) < 10) return;
    const M = this.M, marca = this.editor._proximaMarca('viga');
    const secao = M.material === 'aco' ? secaoDe(M) : { ...secaoDe(M), h: M.vh, ...(M.secao_tipo === 'retangular' ? { b: M.b } : {}) };
    const ent = criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p,
      atributos: { elemento: 'viga', material: M.material, secao, nivel_topo: this.nv('nivel_topo'), alinhamento: alinhamentoDaViga(M), marca } });
    const m = [(this.a[0] + p[0]) / 2, (this.a[1] + p[1]) / 2];
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [m[0], m[1] + larguraViga(M, this.editor._catalogoEstrutura) / 2 + 120], texto: marca, altura: 2.5, atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot], `Viga ${marca}`);
    this.a = p; this.editor.snap.ultimo = p;
    this.dica(`${marca} lançada · continue do fim, ou Esc`);
  }
  onValor(texto) {
    const L = paraMilimetros(texto);
    if (!this.a || !(L > 0)) return;
    const u = this.ultimo || null;
    if (!u) return;
    const d = dist(this.a, u); if (d < 1) return;
    this.onPonto([this.a[0] + (u[0] - this.a[0]) / d * L, this.a[1] + (u[1] - this.a[1]) / d * L], { digitado: true });
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Fundação (sapata ou bloco): um clique no centro; o topo no nível informado */
export class FerramentaFundacao extends FerramentaElemento {
  static id = 'estr_fundacao'; static nome = 'Fundação'; static dica = 'Fundação: clique no centro (o pilar dá snap) · Esc sai';
  reiniciar() { super.reiniciar(); this.atual = null; }
  onMover(p) { this.atual = p; const M = this.M; this.editor.previa([criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: retangulo(p, M.fund_b, M.fund_a, 0) })]); }
  onPonto(p) {
    const M = this.M, marca = this.editor._proximaMarca('fundacao');
    const ent = criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: retangulo(p, M.fund_b, M.fund_a, 0),
      atributos: { elemento: 'fundacao', material: 'concreto', tipo: M.fund_tipo, altura: M.fund_h, nivel_topo: this.nv('nivel_base'), marca, centro: [p[0], p[1]] } });
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [p[0] - M.fund_b / 2, p[1] - M.fund_a / 2 - 350], texto: marca, altura: 2.5, atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot], `Fundação ${marca}`);
    this.dica(`${marca} lançada · próxima, ou Esc`);
  }
}

/** Consolo: clique na face do pilar (o meio dela), depois a direção para fora */
export class FerramentaConsolo extends FerramentaElemento {
  static id = 'estr_consolo'; static nome = 'Consolo'; static dica = 'Consolo: clique no meio da face do pilar · depois para o lado de fora · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  _contorno(a, p) {
    const M = this.M, d = dist(a, p) || 1, u = [(p[0] - a[0]) / d, (p[1] - a[1]) / d], n = [-u[1], u[0]];
    const c = M.cons_c, w = M.cons_b / 2;
    return [[a[0] + n[0] * w, a[1] + n[1] * w], [a[0] + u[0] * c + n[0] * w, a[1] + u[1] * c + n[1] * w],
            [a[0] + u[0] * c - n[0] * w, a[1] + u[1] * c - n[1] * w], [a[0] - n[0] * w, a[1] - n[1] * w]];
  }
  onMover(p) { if (this.a && dist(this.a, p) > 1) this.editor.previa([criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._contorno(this.a, p) })]); }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique para o lado de fora do pilar (a direção do consolo)'); return; }
    if (dist(this.a, p) < 1) return;
    const M = this.M, marca = this.editor._proximaMarca('consolo');
    const ent = criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._contorno(this.a, p),
      atributos: { elemento: 'consolo', material: 'concreto', altura: M.cons_h, nivel_topo: this.nv('nivel_topo'), marca } });
    this.adicionar([ent], `Consolo ${marca}`);
    this.a = null;
    this.dica(`${marca} lançado · próximo, ou Esc`);
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Tesoura de concreto (a viga de cobertura em I): dois cliques, de pilar a pilar; o apoio nos níveis das pontas,
 *  a altura do apoio até a do meio nas duas águas, ou constante na de uma água (a inclinação pelos níveis) */
export class FerramentaTesoura extends FerramentaElemento {
  static id = 'estr_tesoura'; static nome = 'Tesoura de concreto'; static dica = 'Tesoura: clique no apoio de um lado (o centro do pilar dá snap) · depois no do outro · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  onMover(p) {
    if (!this.a) return;
    const w = this.M.tes_bf * 10, d = dist(this.a, p);
    if (d < 1) return;
    const n = [-(p[1] - this.a[1]) / d * w / 2, (p[0] - this.a[0]) / d * w / 2];
    this.editor.previa([criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p }),
      criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true, vertices: [[this.a[0] + n[0], this.a[1] + n[1]], [p[0] + n[0], p[1] + n[1]], [p[0] - n[0], p[1] - n[1]], [this.a[0] - n[0], this.a[1] - n[1]]] })]);
    this.editor.medida(`${numero(d)} mm`);
  }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no apoio do outro lado'); return; }
    if (dist(this.a, p) < 10) return;
    const M = this.M, marca = this.editor._proximaMarca('tesoura');
    const ent = criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p,
      atributos: { elemento: 'tesoura', material: 'concreto', forma: M.tes_forma,
                   secao: { tipo: 'I', bf: M.tes_bf, hf: M.tes_hf, bw: M.tes_bw, h: M.tes_h, h_meio: M.tes_forma === 'uma água' ? M.tes_h : M.tes_hm },
                   nivel_base: this.nv('nivel_topo'), nivel_fim: this.nv('nivel_fim'), marca } });
    const m = [(this.a[0] + p[0]) / 2, (this.a[1] + p[1]) / 2];
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [m[0] + M.tes_bf * 5 + 120, m[1]], texto: marca, altura: 2.5, atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot], `Tesoura ${marca}`);
    this.a = null;
    this.dica(`${marca} lançada · próxima, ou Esc`);
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Chapa de aço: dois cantos opostos; a espessura e o nível da face de cima */
export class FerramentaChapa extends FerramentaElemento {
  static id = 'estr_chapa'; static nome = 'Chapa'; static dica = 'Chapa: clique num canto · depois no canto oposto · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  _ret(a, p) { return [[a[0], a[1]], [p[0], a[1]], [p[0], p[1]], [a[0], p[1]]]; }
  onMover(p) {
    if (!this.a) return;
    this.editor.previa([criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._ret(this.a, p) })]);
    this.editor.medida(`${numero(Math.abs(p[0] - this.a[0]))} × ${numero(Math.abs(p[1] - this.a[1]))} mm`);
  }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no canto oposto'); return; }
    if (Math.abs(p[0] - this.a[0]) < 1 || Math.abs(p[1] - this.a[1]) < 1) return;
    const M = this.M, marca = this.editor._proximaMarca('chapa');
    const ent = criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._ret(this.a, p),
      atributos: { elemento: 'chapa', material: 'aco', espessura: M.chapa_esp, aco: M.chapa_aco, nivel_topo: this.nv('nivel_topo'), marca } });
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [Math.max(p[0], this.a[0]) + 100, Math.max(p[1], this.a[1]) + 100], texto: `${marca} #${M.chapa_esp}`, altura: 2.5, atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot], `Chapa ${marca}`);
    this.a = null;
    this.dica(`${marca} lançada · próxima, ou Esc`);
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Furo: um clique no centro (dentro de uma chapa: o 3D fura a chapa) */
export class FerramentaFuro extends FerramentaElemento {
  static id = 'estr_furo'; static nome = 'Furo'; static dica = 'Furo: clique no centro (dentro da chapa) · Esc sai';
  onMover(p) { this.editor.previa([criar({ tipo: 'circulo', camada: 'FURO', centro: p, raio: this.M.furo_d / 2 })]); this.editor.medida(`ø ${numero(this.M.furo_d, 1)} mm`); }
  onPonto(p) {
    const M = this.M, marca = this.editor._proximaMarca('furo');
    const ent = criar({ tipo: 'circulo', camada: 'FURO', centro: p, raio: M.furo_d / 2, atributos: { elemento: 'furo', diametro: M.furo_d, marca, centro: [p[0], p[1]] } });
    this.adicionar([ent], `Furo ø${M.furo_d}`);
    this.dica(`furo ø${numero(M.furo_d, 1)} lançado · próximo, ou Esc`);
  }
}

/** Parafuso: um clique no centro; o diâmetro, o comprimento e o nível da cabeça */
export class FerramentaParafuso extends FerramentaElemento {
  static id = 'estr_parafuso'; static nome = 'Parafuso'; static dica = 'Parafuso: clique no centro · Esc sai';
  onMover(p) { this.editor.previa([criar({ tipo: 'circulo', camada: 'PARAFUSO', centro: p, raio: this.M.paraf_d / 2 })]); this.editor.medida(`ø ${numero(this.M.paraf_d, 1)} × ${numero(this.M.paraf_L)} mm`); }
  onPonto(p) {
    const M = this.M, marca = this.editor._proximaMarca('parafuso');
    const ent = criar({ tipo: 'circulo', camada: 'PARAFUSO', centro: p, raio: M.paraf_d / 2,
      atributos: { elemento: 'parafuso', material: 'aco', diametro: M.paraf_d, comprimento: M.paraf_L, nivel_topo: this.nv('nivel_topo'), marca, centro: [p[0], p[1]] } });
    this.adicionar([ent], `Parafuso ø${M.paraf_d}`);
    this.dica(`parafuso ø${numero(M.paraf_d, 1)} lançado · próximo, ou Esc`);
  }
}

/** um elemento de dois cliques (a linha dele) com a faixa da largura na prévia: a placa de fechamento e a escada */
class FerramentaDeLinha extends FerramentaElemento {
  reiniciar() { super.reiniciar(); this.a = null; }
  /** o contorno da largura w em volta da linha a→b e os traços transversais nas distâncias `cortes` (mm, a partir de a) */
  desenhoDaFaixa(a, b, w, cortes, id) {
    const d = dist(a, b), u = [(b[0] - a[0]) / d, (b[1] - a[1]) / d], n = [-u[1] * w / 2, u[0] * w / 2];
    const at = (s, k) => [a[0] + u[0] * s + n[0] * k, a[1] + u[1] * s + n[1] * k];
    const out = [criar({ tipo: 'polilinha', camada: 'VISTA', fechada: true, vertices: [at(0, 1), at(d, 1), at(d, -1), at(0, -1)], atributos: { rotulo_de: id } })];
    for (const s of cortes) if (s > 1 && s < d - 1) out.push(criar({ tipo: 'linha', camada: 'VISTA-FINA', a: at(s, 1), b: at(s, -1), atributos: { rotulo_de: id } }));
    return out;
  }
  largura() { return 100; }
  onMover(p) {
    this.ultimo = p;
    if (!this.a) return;
    const w = this.largura(), d = dist(this.a, p);
    if (d < 1) return;
    const n = [-(p[1] - this.a[1]) / d * w / 2, (p[0] - this.a[0]) / d * w / 2];
    this.editor.previa([criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p }),
      criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true, vertices: [[this.a[0] + n[0], this.a[1] + n[1]], [p[0] + n[0], p[1] + n[1]], [p[0] - n[0], p[1] - n[1]], [this.a[0] - n[0], this.a[1] - n[1]]] })]);
    this.editor.medida(this.medidaDe(d));
  }
  medidaDe(d) { return `${numero(d)} mm`; }
  onValor(texto) {
    const L = paraMilimetros(texto);
    if (!this.a || !(L > 0) || !this.ultimo) return;
    const d = dist(this.a, this.ultimo); if (d < 1) return;
    this.onPonto([this.a[0] + (this.ultimo[0] - this.a[0]) / d * L, this.a[1] + (this.ultimo[1] - this.a[1]) / d * L]);
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Placa de fechamento: dois cliques ao longo da parede (o eixo da placa); painéis em pé ou deitados, na largura do módulo */
export class FerramentaPainel extends FerramentaDeLinha {
  static id = 'estr_painel'; static nome = 'Placa de fechamento'; static dica = 'Placa de fechamento: clique no começo da parede · depois no fim (digite o comprimento e Enter) · Esc sai';
  largura() { return this.M.pn_esp; }
  medidaDe(d) { return `${numero(d)} mm · ${Math.ceil(d / this.M.pn_mod - 1e-6)} painel(is)`; }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no fim da parede'); return; }
    if (dist(this.a, p) < 10) return;
    const M = this.M, marca = this.editor._proximaMarca('painel');
    const ent = criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p,
      atributos: { elemento: 'painel', material: 'concreto', tipo: M.pn_tipo, orientacao: M.pn_orient, espessura: M.pn_esp, modulo: M.pn_mod,
                   nivel_base: this.nv('nivel_base'), nivel_topo: this.nv('nivel_topo'), marca } });
    const m = [(this.a[0] + p[0]) / 2, (this.a[1] + p[1]) / 2];
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [m[0], m[1] + M.pn_esp / 2 + 120], texto: `${marca} ${M.pn_tipo} e=${M.pn_esp}`, altura: 2.5, atributos: { rotulo_de: ent.id } });
    // a espessura em planta e, com os painéis em pé, as juntas na largura do módulo
    const L = dist(this.a, p), juntas = [];
    if (M.pn_orient !== 'horizontal') for (let s = M.pn_mod; s < L - 1; s += M.pn_mod) juntas.push(s);
    this.adicionar([ent, rot, ...this.desenhoDaFaixa(this.a, p, M.pn_esp, juntas, ent.id)], `Placa de fechamento ${marca}`);
    this.a = p; this.editor.snap.ultimo = p;
    this.dica(`${marca} lançada · continue do fim (a próxima parede), ou Esc`);
  }
}

/** Laje: dois cantos opostos; maciça, alveolar ou pré-laje (as placas no sentido escolhido), a capa e o nível do topo */
export class FerramentaLaje extends FerramentaElemento {
  static id = 'estr_laje'; static nome = 'Laje'; static dica = 'Laje: clique num canto · depois no canto oposto · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  _ret(a, p) { return [[a[0], a[1]], [p[0], a[1]], [p[0], p[1]], [a[0], p[1]]]; }
  onMover(p) {
    if (!this.a) return;
    this.editor.previa([criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._ret(this.a, p) })]);
    this.editor.medida(`${numero(Math.abs(p[0] - this.a[0]))} × ${numero(Math.abs(p[1] - this.a[1]))} mm`);
  }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no canto oposto'); return; }
    if (Math.abs(p[0] - this.a[0]) < 10 || Math.abs(p[1] - this.a[1]) < 10) return;
    const M = this.M, marca = this.editor._proximaMarca('laje');
    const ent = criar({ tipo: 'polilinha', camada: CAMADA_ESTRUTURA, fechada: true, vertices: this._ret(this.a, p),
      atributos: { elemento: 'laje', material: 'concreto', tipo: M.laje_tipo, espessura: M.laje_esp, capa: M.laje_tipo === 'maciça' ? 0 : M.laje_capa,
                   sentido: M.laje_sentido, modulo: M.laje_mod, nivel_topo: this.nv('nivel_topo'), marca } });
    const c = [(p[0] + this.a[0]) / 2, (p[1] + this.a[1]) / 2];
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: c, texto: `${marca} ${M.laje_tipo} h=${M.laje_esp}${M.laje_tipo !== 'maciça' && M.laje_capa ? '+' + M.laje_capa : ''}`, altura: 2.5, atributos: { rotulo_de: ent.id } });
    // a laje se desenha com um X de canto a canto, como na planta de fôrmas
    const x1 = criar({ tipo: 'linha', camada: 'VISTA-FINA', a: [this.a[0], this.a[1]], b: [p[0], p[1]], atributos: { rotulo_de: ent.id } });
    const x2 = criar({ tipo: 'linha', camada: 'VISTA-FINA', a: [p[0], this.a[1]], b: [this.a[0], p[1]], atributos: { rotulo_de: ent.id } });
    this.adicionar([ent, rot, x1, x2], `Laje ${marca}`);
    this.a = null;
    this.dica(`${marca} lançada · próxima, ou Esc`);
  }
  cancelar() { if (this.a) { this.reiniciar(); return; } super.cancelar(); }
}

/** Escada: dois cliques, do pé ao topo (o sentido de subida); a largura, os níveis de baixo e de cima, o espelho máximo */
export class FerramentaEscada extends FerramentaDeLinha {
  static id = 'estr_escada'; static nome = 'Escada'; static dica = 'Escada: clique no pé (onde começa a subir) · depois no topo · Esc sai';
  largura() { return this.M.esc_larg; }
  _degraus(L) {
    const M = this.M, H = Math.abs(M.nivel_topo - M.nivel_base);
    const n = Math.max(1, Math.ceil(H / M.esc_espelho - 1e-6));
    return { n, e: H / n, p: L / n };
  }
  medidaDe(d) { const g = this._degraus(d); return `${numero(d)} mm · ${g.n} degraus de ${numero(g.e)} × ${numero(g.p)} (2e + p = ${numero(2 * g.e + g.p)})`; }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no topo da escada (o fim do lance)'); return; }
    if (dist(this.a, p) < 10) return;
    const M = this.M, marca = this.editor._proximaMarca('escada');
    const g = this._degraus(dist(this.a, p));
    const ent = criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: this.a, b: p,
      atributos: { elemento: 'escada', material: 'concreto', largura: M.esc_larg, espelho_max: M.esc_espelho, espessura: M.esc_t,
                   nivel_base: this.nv('nivel_base'), nivel_topo: this.nv('nivel_topo'), marca } });
    const m = [(this.a[0] + p[0]) / 2, (this.a[1] + p[1]) / 2];
    const rot = criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [m[0], m[1] + M.esc_larg / 2 + 120], texto: `${marca} sobe · ${g.n} × ${numero(g.e)}/${numero(g.p)}`, altura: 2.5, atributos: { rotulo_de: ent.id } });
    // a largura e os degraus em planta (um traço por espelho)
    const degraus = [];
    for (let i = 1; i < g.n; i++) degraus.push(i * g.p);
    this.adicionar([ent, rot, ...this.desenhoDaFaixa(this.a, p, M.esc_larg, degraus, ent.id)], `Escada ${marca}`);
    this.a = null;
    this.dica(`${marca}: ${g.n} degraus de ${numero(g.e)} mm × ${numero(g.p)} mm · próxima, ou Esc`);
  }
}

export const FERRAMENTAS_ESTRUTURA = [FerramentaPilar, FerramentaViga, FerramentaFundacao, FerramentaConsolo,
  FerramentaTesoura, FerramentaChapa, FerramentaFuro, FerramentaParafuso, FerramentaPainel, FerramentaLaje, FerramentaEscada];

// ------------------------------------------------------------ a barra da disciplina (à direita do desenho)

const I = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">${d}</svg>`;
const ICONES = {
  rotulos: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="11" width="7" height="9"/><path d="M13 5h3a2 2 0 0 1 0 4h-3V3M13 9l4 4"/><path d="M15 17h6M18 14v6"/></svg>',
  renumerar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6h2v6M3.5 12h3M9 7h11M9 12h11M9 17h11M4 15.5c.5-1 2.5-1 2.5.5S4 18 4 19h3"/></svg>',
  pilar_c: I('<rect x="7" y="6" width="10" height="12"/><path d="M7 12l6-6M9 18l8-8"/>'),
  viga_c: I('<rect x="3" y="9" width="18" height="6"/><path d="M6 15l6-6M12 15l6-6"/>'),
  consolo: I('<path d="M6 3v18"/><path d="M6 9h10v3l-4 4H6"/>'),
  fundacao: I('<rect x="4" y="14" width="16" height="6"/><rect x="9" y="5" width="6" height="9"/>'),
  tesoura: I('<path d="M3 18h18"/><path d="M3 18l9-8 9 8"/><path d="M3 15l9-8 9 8"/>'),
  pilar_a: I('<path d="M7 4h10M7 20h10M12 4v16"/>'),
  viga_a: I('<path d="M4 7v10M20 7v10M4 12h16"/>'),
  chapa: I('<path d="M4 9l11-5 5 11-11 5z"/><circle cx="10" cy="11" r="1.2"/><circle cx="14" cy="13" r="1.2"/>'),
  furo: I('<circle cx="12" cy="12" r="5"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>'),
  parafuso: I('<path d="M8 3h8l2 3-2 3H8L6 6z"/><path d="M12 9v12M10 12h4M10 15h4M10 18h4"/>'),
  niveis: I('<path d="M3 17h18M3 9h18" stroke-dasharray="3 2"/><path d="M8 17l3-4 3 4M14 9l3-4 3 4"/>'),
  gerar3d: I('<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>'),
  do3d: I('<path d="M4 12a8 8 0 0 1 13.7-5.7"/><path d="M18 3v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.7"/><path d="M6 21v-4h4"/>'),
  painel: I('<rect x="3" y="4" width="18" height="16"/><path d="M9 4v16M15 4v16"/>'),
  laje: I('<path d="M3 9l6-4h12l-6 4z"/><path d="M3 9v4h12V9M15 13l6-4V5"/>'),
  escada: I('<path d="M3 20h4v-4h4v-4h4V8h4V4h2"/><path d="M3 20l18-16" stroke-dasharray="2 2"/>'),
  // a malha de eixos (07/10, acesso rápido): duas linhas de eixo com as bolinhas e uma atravessada
  // um eixo só, com a bolinha (a ferramenta Eixo, um por vez — 07/10)
  eixo1: I('<circle cx="12" cy="4.5" r="2.5"/><path d="M12 7v14" stroke-dasharray="3.5 1.5 1 1.5"/><path d="M17 15h4M19 13v4"/>'),
  eixos: I('<circle cx="7" cy="4.5" r="2.3"/><circle cx="17" cy="4.5" r="2.3"/><path d="M7 7v14M17 7v14M3 15h18" stroke-dasharray="3.5 1.5 1 1.5"/>'),
  config: I('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>'),
};

/** os botões de cada disciplina: [ferramenta ou ação, rótulo, ícone, medidas que o botão fixa] */
const DISCIPLINAS = {
  metalica: { rotulo: 'Met', titulo: 'da Metálica', itens: [
    ['estr_pilar', 'Pilar (perfil de aço)', 'pilar_a', { material: 'aco' }],
    ['estr_viga', 'Viga (perfil de aço)', 'viga_a', { material: 'aco' }],
    ['estr_chapa', 'Chapa (dois cantos; espessura e nível no painel)', 'chapa'],
    ['estr_furo', 'Furo (dentro da chapa: o 3D fura a chapa)', 'furo'],
    ['estr_parafuso', 'Parafuso (diâmetro, comprimento e nível da cabeça)', 'parafuso'],
  ] },
  premoldado: { rotulo: 'Pré', titulo: 'do pré-moldado', itens: [
    ['estr_pilar', 'Pilar de concreto', 'pilar_c', { material: 'concreto' }],
    ['estr_viga', 'Viga de concreto', 'viga_c', { material: 'concreto' }],
    ['estr_consolo', 'Consolo (na face do pilar)', 'consolo'],
    ['estr_fundacao', 'Fundação (sapata ou bloco)', 'fundacao'],
    ['estr_tesoura', 'Tesoura de concreto (viga de cobertura em I, do apoio de um pilar ao outro)', 'tesoura'],
    ['estr_painel', 'Placa de fechamento (painel alveolar ou maciço, em pé ou deitado, ao longo da parede)', 'painel'],
    ['estr_laje', 'Laje (maciça, alveolar ou pré-laje, com a capa; dois cantos)', 'laje'],
    ['estr_escada', 'Escada (do pé ao topo; os degraus pelos níveis e o espelho máximo)', 'escada'],
  ] },
};
const ACOES_PLANTA = [
  ['eixo1', 'Eixo, um por vez (clique num eixo e o seguinte vai com o cursor, ou digite o vão: 6000, 3x6000)', 'eixo1', 'ativarEixoUnico'],
  ['eixos', 'Malha de eixos… (lançar os eixos por cima da planta, com as bolinhas e as cotas)', 'eixos', 'dialogoMalha'],
  ['niveis', 'Níveis do projeto…', 'niveis', 'dialogoNiveis'],
  ['rotulos', 'Arrumar os nomes dos elementos (rótulos soltos, faltando ou trocados)', 'rotulos', 'arrumarRotulosComAviso'],
  ['renumerar', 'Renumerar os elementos em ordem (de cima para baixo, da esquerda para a direita)', 'renumerar', 'renumerarElementos'],
  ['gerar3d', 'Gerar 3D da planta…', 'gerar3d', 'gerar3DDaPlanta'],
  ['do3d', 'Atualizar a planta pelo 3D', 'do3d', 'atualizarPlantaPelo3D'],
];
const CHAVE_DISCIPLINA = 'cad.estrutura.disciplina';

// o ícone de cada ferramenta na própria classe (`static icone`, como as de ferramentas.js): a faixa única da área de
// trabalho (web/area.js) lê as ferramentas registradas de fora — o do pilar e o da viga são os do concreto; o botão
// de cada disciplina tem o seu em DISCIPLINAS / itensDaDisciplina()
FerramentaPilar.icone = ICONES.pilar_c;
FerramentaViga.icone = ICONES.viga_c;
FerramentaConsolo.icone = ICONES.consolo;
FerramentaFundacao.icone = ICONES.fundacao;
FerramentaTesoura.icone = ICONES.tesoura;
FerramentaChapa.icone = ICONES.chapa;
FerramentaFuro.icone = ICONES.furo;
FerramentaParafuso.icone = ICONES.parafuso;
FerramentaPainel.icone = ICONES.painel;
FerramentaLaje.icone = ICONES.laje;
FerramentaEscada.icone = ICONES.escada;

// ------------------------------------------------------------ os métodos do CAD

export class MetodosEstruturaCAD {
  _registrarFerramentasDaEstrutura() {
    for (const F of FERRAMENTAS_ESTRUTURA) this.ferramentas.set(F.id, new F(this));
    if (!this._unidadeInstalada) {
      this._unidadeInstalada = true;
      document.addEventListener('change', (ev) => {
        if (!ev.target.closest || !ev.target.closest('#rodape-escala')) return;
        setTimeout(() => {
          const id = this.ferramenta && this.ferramenta.constructor.id;
          if (id && id.startsWith('estr_') && this._painelEstr && !this._painelEstr.hidden) this._painelEstrutura(id);
          if (typeof this._agendarPaineis === 'function') this._agendarPaineis('props');
        }, 0);
      });
    }
    // a planta e o 3D ligados: depois de cada gravação, se os elementos da planta mudaram, o 3D acompanha
    if (!this._sincroniaInstalada) {
      this._sincroniaInstalada = true;
      const gravar = this.salvar.bind(this);
      this.salvar = async (...args) => {
        // Só depois de uma gravação de verdade, e com a planta como foi gravada (07/10, Docas: as 7 tesouras
        // lançadas não chegaram ao 3D). Com outra gravação em curso, o salvar do CAD só marca a pendente e volta na
        // hora: a sincronia lia no disco a planta ainda sem as tesouras, anotava a impressão COM elas e, quando a
        // gravação pendente as gravava, achava que o 3D já estava em dia. A pendente passa por aqui de novo.
        const adiada = !!this._salvando;
        const impressao = this._impressaoDaPlanta();
        const r = await gravar(...args);
        const gravou = !adiada && /^gravado/.test((this.el.estadoSalvo && this.el.estadoSalvo.textContent) || '');
        if (gravou) this._sincronizar3D(false, impressao);
        this._avisarReferencia();
        return r;
      };
      // ao abrir a planta sem elementos, o 3D perde o que sobrou dela (com elementos, a próxima gravação sincroniza)
      if (typeof this.abrirDesenho === 'function') {
        const abrir = this.abrirDesenho.bind(this);
        this.abrirDesenho = async (...args) => {
          const r = await abrir(...args);
          if (this._impressaoDaPlanta() === '[]') this._sincronizar3D();
          return r;
        };
      }
    }
    // a viga gravada é a linha do eixo dela; na tela ela aparece com a largura da mesa (as duas bordas e os
    // topos), como numa planta de estrutura — antes era só uma linha e não se via onde a viga encosta (06/10)
    if (!this._larguraVigasInstalada) {
      this._larguraVigasInstalada = true;
      const antes = this.tela.aoDesenhar;
      this.tela.aoDesenhar = () => { if (antes) antes(); this._desenharLarguraDasVigas(); };
      // o clique na faixa da viga (na mesa, não só na linha do eixo) pega a viga — antes só a linha do meio respondia
      // e o clique na aba não selecionava nada (06/10)
      const sob = this.tela.sob.bind(this.tela);
      this.tela.sob = (px, ...resto) => sob(px, ...resto) || this._vigaSob(px);
      // e o snap pega os cantos e as bordas da faixa (o "cantinho" da viga para copiar, mover…) — 06/10
      if (this.snap) this.snap.virtuais = (p, r) => this._bordasDasVigas(p, r);
      // o elemento e o rótulo dele (a marca escrita: P1, V1) andam juntos — o clique em um pega os dois, e mover,
      // copiar e apagar levam os dois. Antes o rótulo ficava: as cópias saíam sem nome e o apagado deixava o nome
      // solto, sobreposto ao do elemento novo (06/10, "verifique as numerações")
      // no menu Estrutura (e, por ele, no Modelo › Lançar na planta da área de trabalho): arrumar os nomes e renumerar
      const niveisBtn = document.querySelector('[data-acao="estr-niveis"]');
      if (niveisBtn && !document.querySelector('[data-acao="estr-rotulos"]')) {
        const botao = (acao, texto, titulo, fn) => {
          const b = el('button', { type: 'button', 'data-acao': acao, title: titulo, texto });
          b.addEventListener('click', () => { const m = b.closest('details, .menu-aberto'); if (m && m.open !== undefined) m.open = false; fn(); });
          return b;
        };
        niveisBtn.after(
          botao('estr-trelica', 'Tesoura de aço pelo desenho…', 'Selecione a tesoura desenhada em linhas (banzos, diagonais, montantes) e lance-a de um eixo a outro, nos eixos que escolher; o 3D monta as barras', () => this.tesouraPeloDesenho()),
          botao('estr-rotulos', 'Arrumar os nomes dos elementos', 'Um rótulo por elemento, com a marca dele: os soltos (de elemento apagado) saem, os que faltam (cópias antigas) são criados', () => this.arrumarRotulosComAviso()),
          botao('estr-renumerar', 'Renumerar os elementos em ordem', 'P1, P2… de cima para baixo e, na mesma fila, da esquerda para a direita (cada tipo à parte); o rótulo acompanha. Ctrl+Z desfaz', () => this.renumerarElementos()));
      }
      const peca = this.pecaDe.bind(this);
      this.pecaDe = (id) => this._comRotulos(peca(id));
      const apagar = this.apagarSelecao.bind(this);
      this.apagarSelecao = () => { const ids = this._comRotulos([...this.tela.selecao]); if (ids.length !== this.tela.selecao.size) this.tela.selecao = new Set(ids); return apagar(); };
      this.catalogoEstrutura().then(() => this.tela.pedirQuadro()).catch(() => {});
    }
    this.medidasEstrutura = { ...PADRAO };
    try { Object.assign(this.medidasEstrutura, JSON.parse(localStorage.getItem(CHAVE) || '{}')); } catch { /* sem armazenamento */ }
    this._niveisProjeto = null;
    this._catalogoEstrutura = null;
  }

  /** `ids` mais os rótulos dos elementos e os elementos dos rótulos que estão neles. */
  _comRotulos(ids) {
    if (!this.doc.camadas.has(CAMADA_ESTRUTURA)) return ids;
    const set = new Set(ids);
    for (const id of ids) {
      const e = this.doc.get(id), a = (e && e.atributos) || {};
      if (a.rotulo_de && this.doc.get(a.rotulo_de)) set.add(a.rotulo_de);
    }
    const elementos = new Set([...set].filter(id => ((this.doc.get(id) || {}).atributos || {}).elemento));
    if (elementos.size) for (const e of this.doc.entidades.values()) { const r = (e.atributos || {}).rotulo_de; if (r && elementos.has(r)) set.add(e.id); }
    return [...set];
  }

  /**
   * Os rótulos dos elementos da planta em ordem: o solto (o elemento dele foi apagado) sai, o que falta (as cópias
   * feitas antes de 06/10) é criado ao lado do elemento, e o texto é a marca dele. Devolve quantos de cada.
   */
  arrumarRotulos() {
    const tirar = [], novos = [], mud = {};
    const rotulos = new Map();
    for (const e of this.doc.entidades.values()) {
      const r = (e.atributos || {}).rotulo_de;
      if (!r) continue;
      const el = this.doc.get(r);
      if (!el || !(el.atributos || {}).elemento) { tirar.push(e.id); continue; }
      if (rotulos.has(r)) { tirar.push(e.id); continue; }                 // dois rótulos do mesmo elemento
      rotulos.set(r, e);
      if (e.tipo === 'texto' && el.atributos.marca && e.texto !== el.atributos.marca) mud[e.id] = { texto: el.atributos.marca };
    }
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (!a.elemento || !a.marca || rotulos.has(e.id)) continue;
      const pts = e.vertices || (e.a ? [e.a, e.b] : e.centro ? [e.centro] : null);
      if (!pts || !pts.length) continue;
      const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]);
      const pos = e.tipo === 'linha' ? [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2 + 120] : [Math.max(...xs) + 80, Math.max(...ys) + 80];
      novos.push(criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: pos, texto: a.marca, altura: 2.5, atributos: { rotulo_de: e.id } }));
    }
    const cmds = [];
    if (tirar.length) cmds.push(new ComandoRemover(tirar, 'Rótulos soltos'));
    if (Object.keys(mud).length) cmds.push(new ComandoAlterar(mud, 'Texto dos rótulos'));
    if (novos.length) cmds.push(new ComandoAdicionar(novos, 'Rótulos que faltavam'));
    if (cmds.length) this.executar(cmds.length === 1 ? cmds[0] : new ComandoComposto(cmds, 'Arrumar os rótulos'));
    return { soltos: tirar.length, criados: novos.length, corrigidos: Object.keys(mud).length };
  }

  /**
   * Tesoura de aço pelo desenho (pedido do usuário, 06/10): selecione a tesoura desenhada em linhas de eixo (a elevação:
   * banzos, diagonais, montantes, o arco do banzo) e escolha os perfis, o nível do banzo inferior e onde ela vai — de um
   * eixo a outro, em cada eixo marcado. Cada uma vira um elemento "trelica" da planta (a linha de apoio a apoio, com o
   * desenho das barras), que o 3D monta e acompanha como os pilares.
   */
  async tesouraPeloDesenho() {
    const sel = [...this.tela.selecao].map(id => this.doc.get(id)).filter(e => e && ['linha', 'arco', 'polilinha'].includes(e.tipo)
      && !(e.atributos || {}).elemento && !['EIXO', 'COTA', CAMADA_ESTRUTURA].includes(e.camada));
    if (sel.length < 3) {
      this.aviso('Selecione a tesoura desenhada em linhas de eixo (banzos, diagonais e montantes) e use de novo "Tesoura de aço pelo desenho".', 'atencao', 9000);
      return;
    }
    const des = desenhoDaTesoura(sel);
    if (!des || des.n < 3) { this.aviso('Não consegui ler a tesoura nessa seleção: são precisas ao menos três barras.', 'atencao'); return; }
    // a malha de eixos da planta, por famílias (as linhas paralelas)
    const eixos = [...this.doc.entidades.values()].filter(e => e.tipo === 'linha' && (e.atributos || {}).malha && (e.atributos || {}).eixo && dist(e.a, e.b) > 1);
    if (eixos.length < 3) { this.aviso('A planta não tem a malha de eixos (Lançamento › Malha de eixos): a tesoura vai de um eixo a outro.', 'atencao', 9000); return; }
    const dirDe = (e) => { const L = dist(e.a, e.b); return [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L]; };
    const paralelos = (x, y) => { const u = dirDe(x), v = dirDe(y); return Math.abs(u[0] * v[1] - u[1] * v[0]) < 0.03; };
    const nomeDe = (e) => String(e.atributos.eixo);
    // a sugestão: o par de eixos paralelos com a distância mais perto do vão desenhado
    let melhor = null;
    for (const x of eixos) for (const y of eixos) {
      if (x === y || !paralelos(x, y)) continue;
      const n = dirDe(x), d = Math.abs(-(y.a[0] - x.a[0]) * n[1] + (y.a[1] - x.a[1]) * n[0]);
      const err = Math.abs(d - des.vao);
      if (!melhor || err < melhor.err) melhor = { x, y, err };
    }
    const [cat, niveis] = await Promise.all([this.catalogoEstrutura(), this.niveisDoProjeto()]);
    const M = this.medidasEstrutura;
    M.trelica = M.trelica || {};
    const grupos = cat.grupos.length ? cat.grupos : [['Perfis', [M.perfil]]];
    const todos = grupos.flatMap(([, ns]) => ns);
    const perfilSel = (k, padrao) => {
      const v = M.trelica[k] && todos.includes(M.trelica[k]) ? M.trelica[k] : padrao;
      return el('select', { 'data-perfil': k }, ...grupos.map(([g, ns]) => el('optgroup', { label: g }, ...ns.map(n => el('option', { value: n, texto: rotuloPerfil(n, cat.dados[n]), selected: n === v ? 'selected' : undefined })))));
    };
    const umL = todos.find(n => /^L\s*50/.test(n)) || todos.find(n => /^L\s/.test(n)) || M.perfil;
    // a marca: a da tesoura que já veio deste desenho (lançar de novo o desenho corrigido substitui), ou, com um tipo só
    // lançado, a dele; senão a próxima livre
    const trels = this.elementosDaPlanta().filter(e => e.atributos.elemento === 'trelica');
    const idsSel = new Set(sel.map(e => e.id));
    const daFonte = trels.find(e => ((e.atributos.desenho || {}).fonte || []).some(id => idsSel.has(id)));
    const tipos = [...new Set(trels.map(e => e.atributos.marca))];
    const marca = el('input', { type: 'text', size: 6, value: daFonte ? daFonte.atributos.marca : tipos.length === 1 ? tipos[0]
      : (() => { const us = new Set(tipos); let n = 1; while (us.has('T' + n)) n++; return 'T' + n; })() });
    const pSup = perfilSel('banzo_sup', M.perfil), pInf = perfilSel('banzo_inf', M.perfil), pDia = perfilSel('diagonal', umL);
    // cantoneira simples (uma aba do U) ou dupla (uma em cada aba) — o usuário, 07/10: perguntar sempre
    const cantSel = el('select', {},
      el('option', { value: 'simples', texto: 'simples — uma cantoneira, numa aba do U' }),
      el('option', { value: 'dupla', texto: 'dupla — uma em cada aba do U' }));
    cantSel.value = (M.trelica || {}).cantoneira || 'simples';
    const acoSel = el('select', {}, ...(cat.acos.length ? cat.acos : [M.aco]).map(a => el('option', { value: a, texto: a, selected: a === (M.trelica.aco || M.aco) ? 'selected' : undefined })));
    // o nível do banzo inferior: o topo mais comum dos pilares lançados
    const topos = this.elementosDaPlanta().filter(e => e.atributos.elemento === 'pilar').map(e => e.atributos.nivel_topo);
    const cont = new Map(); for (const t of topos) cont.set(t, (cont.get(t) || 0) + 1);
    const topoComum = [...cont.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0])[0];
    const nivSel = el('select', {}, el('option', { value: '', texto: '— número —' }),
      ...niveis.map(n => el('option', { value: n.nome, texto: `${n.nome} (${numero(n.z / 1000, 2)})`, selected: n.nome === topoComum ? 'selected' : undefined })));
    const zoNum = typeof topoComum === 'number' ? topoComum : (niveis.find(n => n.nome === topoComum) || {}).z ?? 0;
    const nivNum = el('input', { type: 'text', value: naUnidade(zoNum || 0), size: 7, title: `nível em ${unidadeAtual()}`, style: 'width:72px;flex:none' });
    nivSel.onchange = () => { const n = niveis.find(x => x.nome === nivSel.value); if (n) nivNum.value = naUnidade(n.z); };
    nivNum.onchange = () => { nivSel.value = ''; };
    const ord = (a, b) => nomeDe(a).localeCompare(nomeDe(b), 'pt-BR', { numeric: true });
    const deSel = el('select', {}, ...[...eixos].sort(ord).map(e => el('option', { value: e.id, texto: nomeDe(e), selected: melhor && melhor.x === e ? 'selected' : undefined })));
    const ateSel = el('select', {}, ...[...eixos].sort(ord).map(e => el('option', { value: e.id, texto: nomeDe(e), selected: melhor && melhor.y === e ? 'selected' : undefined })));
    const caixaEixos = el('div', { style: 'display:flex;flex-wrap:wrap;gap:4px 12px;max-height:120px;overflow:auto;min-width:0' });
    const info = el('div', { class: 'explica' });
    // o apoio em cima da viga que passa sob ele (a viga de aço ao longo dos pilares): o topo dela, pelo nível e pelo
    // alinhamento da viga — pedido do usuário, 06/10: "a base do suporte é em cima do perfil W"
    const sobreViga = el('input', { type: 'checkbox' });
    const sobreVigaRot = el('span', {});
    const linhaViga = el('label', { style: 'display:flex;flex-direction:row;gap:6px;align-items:center;margin:4px 0;color:var(--texto);font-size:13px' }, sobreViga, sobreVigaRot);
    // em qual eixo do vão fica cada ponta da tesoura: pergunta-se no lançamento (o Docas, 07/10, saiu com a ponta alta no eixo
    // da ponta solta e a baixa nos pilares — o desenho ia sempre do primeiro eixo ao segundo). As alturas das pontas, pelo desenho
    const alturaNa = (u0) => Math.max(0, ...des.barras.flatMap(b => [[b[0], b[1]], [b[2], b[3]]]).filter(q => Math.abs(q[0] - u0) <= 0.02 * des.vao).map(q => q[1]));
    const hEsq = alturaNa(0), hDir = alturaNa(des.vao);
    const pontaAlta = Math.abs(hEsq - hDir) > 0.05 * Math.max(hEsq, hDir, 1);
    const pontaSel = el('select', {});
    pontaSel.style.cssText = 'flex:1 1 0;min-width:0;width:100%';
    const pontaRot = pontaAlta ? `Ponta alta (${numero(Math.max(hEsq, hDir) / 1000, 2)} m) no eixo` : 'Começo do desenho no eixo';
    let vigaApoio = null;
    const acharViga = (P) => {
      for (const v of this.elementosDaPlanta()) {
        const va = v.atributos;
        if (va.elemento !== 'viga' || v.tipo !== 'linha') continue;
        const L = dist(v.a, v.b); if (L < 1) continue;
        const t = ((P[0] - v.a[0]) * (v.b[0] - v.a[0]) + (P[1] - v.a[1]) * (v.b[1] - v.a[1])) / (L * L);
        const q = [v.a[0] + (v.b[0] - v.a[0]) * Math.max(0, Math.min(1, t)), v.a[1] + (v.b[1] - v.a[1]) * Math.max(0, Math.min(1, t))];
        if (dist(q, P) > 60) continue;
        const pf = (va.secao || {}).perfil, d = +((cat.dados || {})[pf] || {}).d || 0;
        const alin = va.alinhamento || (va.material === 'aco' ? 'eixo' : 'topo');
        const h = va.material === 'aco' ? d : 10 * (+(va.secao || {}).h || 0);
        const acima = alin === 'base' ? h : alin === 'eixo' ? h / 2 : 0;
        return { viga: v, nivel: va.nivel_topo, acima, perfil: pf || 'concreto' };
      }
      return null;
    };
    const marcarEixos = () => {
      const de = this.doc.get(deSel.value), ate = this.doc.get(ateSel.value);
      caixaEixos.replaceChildren();
      if (de && ate) {
        const antes = pontaSel.value;
        pontaSel.replaceChildren(el('option', { value: de.id, texto: nomeDe(de) }), el('option', { value: ate.id, texto: nomeDe(ate) }));
        // sem escolha ainda: a ponta alta (ou o começo do desenho) no primeiro eixo, como era
        pontaSel.value = [de.id, ate.id].includes(antes) ? antes : (pontaAlta && hDir > hEsq ? ate.id : de.id);
      }
      if (!de || !ate || !paralelos(de, ate)) { info.textContent = 'Escolha dois eixos paralelos (o vão da tesoura).'; return; }
      const n = dirDe(de), d = Math.abs(-(ate.a[0] - de.a[0]) * n[1] + (ate.a[1] - de.a[1]) * n[0]);
      for (const e of [...eixos].filter(e => !paralelos(e, de)).sort(ord)) caixaEixos.append(el('label', { style: 'display:inline-flex;flex-direction:row;align-items:center;gap:4px;color:var(--texto);font-size:13px' }, el('input', { type: 'checkbox', value: e.id, checked: true }), nomeDe(e)));
      // a viga sob o apoio (no primeiro eixo marcado)
      const primeiro = [...eixos].filter(e => !paralelos(e, de)).sort(ord)[0];
      const PA = primeiro && cruzamentoRetas(primeiro.a, primeiro.b, de.a, de.b);
      vigaApoio = PA ? acharViga(PA) : null;
      // sem viga sob o apoio, a linha some (o hidden sozinho perdia para o display:flex do estilo e a caixa ficava vazia)
      linhaViga.style.display = vigaApoio ? 'flex' : 'none';
      if (vigaApoio) {
        const zN = typeof vigaApoio.nivel === 'number' ? vigaApoio.nivel : ((niveis.find(n => n.nome === vigaApoio.nivel) || {}).z ?? 0);
        sobreVigaRot.textContent = `Apoiar em cima da viga ${vigaApoio.viga.atributos.marca} (${vigaApoio.perfil}): o topo dela, em ${numero((zN + vigaApoio.acima) / 1000, 3)} m`;
        sobreViga.checked = true;
      }
      const dif = d - des.vao;
      info.textContent = `Desenho: ${des.n} barras, vão ${numero(des.vao / 1000, 3)} m, altura ${numero(des.altura / 1000, 3)} m${des.raio ? `, banzo em arco R ${numero(des.raio / 1000, 2)} m (trechos retos entre os nós; o raio fica para a calandra)` : ''}. ` +
        `O apoio (o ponto mais baixo da tesoura${des.baixoDoBanzo > 1 ? `, ${numero(des.baixoDoBanzo)} mm abaixo do banzo inferior` : ''}) vai no nível escolhido. ` +
        `Entre ${nomeDe(de)} e ${nomeDe(ate)}: ${numero(d / 1000, 3)} m` + (Math.abs(dif) > 1 ? ` — ${numero(Math.abs(dif))} mm ${dif > 0 ? 'a mais' : 'a menos'} que o desenho: o vão se ajusta aos eixos.` : '.');
    };
    deSel.onchange = marcarEixos; ateSel.onchange = marcarEixos;
    marcarEixos();
    const GRADE = 'display:grid;grid-template-columns:140px minmax(0,1fr);gap:6px;align-items:center;margin:2px 0';
    for (const s of [pSup, pInf, pDia, cantSel, acoSel, nivSel]) s.style.cssText += ';flex:1 1 0;min-width:0;width:100%';
    const linha = (rot, ...x) => el('label', { style: GRADE + ';flex-direction:unset' }, rot, el('div', { style: 'display:flex;gap:6px;align-items:center;min-width:0' }, ...x));
    const corpo = el('div', {}, info,
      linha('Marca', marca), linha('Banzo superior', pSup), linha('Banzo inferior', pInf), linha('Diagonais e montantes', pDia), linha('Cantoneiras', cantSel), linha('Aço', acoSel),
      linha(`Nível do apoio (${unidadeAtual()})`, nivSel, nivNum), linhaViga, linha('Vão entre os eixos', deSel, el('span', { texto: 'e' }), ateSel), linha(pontaRot, pontaSel),
      el('div', { style: GRADE + ';align-items:start;color:var(--texto2);font-size:12px' }, el('span', { style: 'padding-top:2px', texto: 'Tesoura nos eixos' }), caixaEixos));
    // a caixa um pouco mais larga para os nomes dos perfis caberem inteiros (volta ao padrão ao fechar)
    const dlg = document.getElementById('dialogo');
    if (dlg) dlg.style.width = 'min(520px, calc(100vw - 32px))';
    const resp = await this.dialogo({ titulo: 'Tesoura de aço pelo desenho', corpo, ok: 'Lançar' });
    if (dlg) dlg.style.width = '';
    if (resp !== 'ok') return;
    const de = this.doc.get(deSel.value), ate = this.doc.get(ateSel.value);
    const nos = [...caixaEixos.querySelectorAll('input:checked')].map(i => this.doc.get(i.value)).filter(Boolean);
    if (!de || !ate || !paralelos(de, ate) || !nos.length) { this.aviso('Nada lançado: escolha os dois eixos do vão e ao menos um eixo para a tesoura.', 'atencao'); return; }
    const n = dirDe(de), d = Math.abs(-(ate.a[0] - de.a[0]) * n[1] + (ate.a[1] - de.a[1]) * n[0]);
    if (Math.abs(d - des.vao) > 0.05 * des.vao) { this.aviso(`O vão entre ${nomeDe(de)} e ${nomeDe(ate)} (${numero(d)} mm) é muito diferente do desenho (${numero(des.vao)} mm): confira os eixos ou o desenho.`, 'atencao', 12000); return; }
    M.trelica = { banzo_sup: pSup.value, banzo_inf: pInf.value, diagonal: pDia.value, aco: acoSel.value, cantoneira: cantSel.value };
    this._guardarMedidas();
    const apoioViga = sobreViga.checked && vigaApoio;
    const nivel = apoioViga ? vigaApoio.nivel : nivSel.value || (paraMilimetros(nivNum.value) || 0);
    const acima = apoioViga ? Math.round(vigaApoio.acima * 10) / 10 : 0;
    const nomeT = (marca.value || 'T1').trim().toUpperCase();
    const novas = [];
    for (const e of nos) {
      let A = cruzamentoRetas(e.a, e.b, de.a, de.b), B = cruzamentoRetas(e.a, e.b, ate.a, ate.b);
      if (!A || !B) continue;
      // a linha vai do começo do desenho (u = 0) ao fim: o começo no eixo em que fica a ponta escolhida
      const comecoNoDe = pontaAlta ? ((pontaSel.value === de.id) === (hEsq > hDir)) : pontaSel.value === de.id;
      if (!comecoNoDe) [A, B] = [B, A];
      const ent = criar({ tipo: 'linha', camada: CAMADA_ESTRUTURA, a: A, b: B, atributos: { elemento: 'trelica', material: 'aco', marca: nomeT,
        perfis: { banzo_sup: pSup.value, banzo_inf: pInf.value, diagonal: pDia.value }, cantoneira: cantSel.value, aco: acoSel.value, nivel_base: nivel, acima_do_nivel: acima, ...(apoioViga ? { apoio_viga: vigaApoio.viga.atributos.marca } : {}),
        desenho: { barras: des.barras, vao: des.vao, altura: des.altura, raio_banzo_sup: des.raio, fonte: sel.map(x => x.id) }, eixo: nomeDe(e) } });
      const m = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
      novas.push(ent, criar({ tipo: 'texto', camada: CAMADA_ESTRUTURA, posicao: [m[0] + 150, m[1] + 150], texto: nomeT, altura: 2.5, atributos: { rotulo_de: ent.id } }));
    }
    if (!novas.length) { this.aviso('Os eixos escolhidos não se cruzam.', 'atencao'); return; }
    // a mesma marca já lançada (o desenho corrigido, lançado de novo): as antigas saem, com os rótulos
    const antigas = this.elementosDaPlanta().filter(e => e.atributos.elemento === 'trelica' && e.atributos.marca === nomeT).map(e => e.id);
    if (antigas.length) {
      const c = el('div', { class: 'explica', texto: `Já há ${antigas.length} tesoura(s) ${nomeT} lançada(s). Substituir pelas novas (as antigas saem) ou acrescentar as novas?` });
      if (await this.dialogo({ titulo: `Tesoura ${nomeT}`, corpo: c, ok: 'Substituir' }) !== 'ok') { this.aviso(`Nada lançado: use outra marca para acrescentar (T2…).`, 'info'); return; }
    }
    this._garantirCamadaEstrutura();
    const cmds = [];
    if (antigas.length) cmds.push(new ComandoRemover(this._comRotulos(antigas), `Tesouras ${nomeT} antigas`));
    cmds.push(new ComandoAdicionar(novas, `Tesoura ${nomeT}`));
    this.executar(cmds.length > 1 ? new ComandoComposto(cmds, `Tesoura ${nomeT}`) : cmds[0]);
    this.aviso(`Tesoura ${nomeT} lançada em ${novas.length / 2} eixo(s), de ${nomeDe(de)} a ${nomeDe(ate)}: ${des.n} barras cada. O 3D acompanha ao gravar. Ctrl+Z desfaz.`, 'info', 9000);
    await this.salvar({ avisar: false });
  }

  arrumarRotulosComAviso() {
    const r = this.arrumarRotulos();
    const partes = [r.soltos && `${r.soltos} solto(s) apagado(s)`, r.criados && `${r.criados} criado(s)`, r.corrigidos && `${r.corrigidos} corrigido(s)`].filter(Boolean);
    this.aviso(partes.length ? `Rótulos: ${partes.join(', ')}. Ctrl+Z desfaz.` : 'Os rótulos já estão em ordem: um por elemento, com a marca dele.', 'info', 6000);
  }

  /**
   * Renumera cada tipo de elemento (P, V, F…) na ordem da planta — de cima para baixo e, na mesma fila (meio metro),
   * da esquerda para a direita — e o rótulo acompanha. As marcas repetidas e os buracos (P11 entre o P1 e o P2,
   * depois de apagar e copiar) somem. Ctrl+Z desfaz.
   */
  renumerarElementos() {
    const porTipo = new Map();
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (!a.elemento || !a.marca || a.elemento === 'trelica') continue;          // a tesoura repete a marca do tipo
      const pts = e.vertices || (e.a ? [e.a, e.b] : e.centro ? [e.centro] : []);
      if (!pts.length) continue;
      const c = [pts.reduce((t, q) => t + q[0], 0) / pts.length, pts.reduce((t, q) => t + q[1], 0) / pts.length];
      const pref = String(a.marca).replace(/\d+$/, '') || String(this._proximaMarca(a.elemento)).replace(/\d+$/, '');
      if (!porTipo.has(pref)) porTipo.set(pref, []);
      porTipo.get(pref).push({ e, c });
    }
    const mud = {};
    let n = 0;
    for (const [pref, lista] of porTipo) {
      lista.sort((x, y) => (Math.round(y.c[1] / 500) - Math.round(x.c[1] / 500)) || (x.c[0] - y.c[0]));
      lista.forEach(({ e }, i) => {
        const marca = pref + (i + 1);
        if (e.atributos.marca === marca) return;
        n++;
        mud[e.id] = { atributos: { ...e.atributos, marca } };
        for (const r of this.doc.entidades.values()) if ((r.atributos || {}).rotulo_de === e.id && r.tipo === 'texto') mud[r.id] = { texto: marca };
      });
    }
    if (n) this.executar(new ComandoAlterar(mud, 'Renumerar os elementos'));
    const r = this.arrumarRotulos();
    this.aviso(n ? `${n} elemento(s) renumerado(s) em ordem${r.criados || r.soltos ? ` · rótulos: ${r.criados} criado(s), ${r.soltos} solto(s) apagado(s)` : ''}. Ctrl+Z desfaz.`
      : 'Os elementos já estão numerados em ordem.', 'info', 7000);
  }

  /** Para o Esticar: o clique perto da ponta da viga (no último trecho, até a largura dela, ou 12 px) pega aquela
   *  ponta, que anda no eixo da viga; null no meio dela ou em outra coisa. */
  _pontaParaEsticar(e, p) {
    const a = (e && e.atributos) || {};
    if (!e || e.tipo !== 'linha' || a.elemento !== 'viga') return null;
    const L = dist(e.a, e.b);
    if (L < 1) return null;
    const u = [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L];
    const s = (p[0] - e.a[0]) * u[0] + (p[1] - e.a[1]) * u[1];
    const w = larguraDaVigaGravada(a, this._catalogoEstrutura) || 0;
    const perto = Math.max(w, 12 / ((this.tela.vp || {}).z || 1), L * 0.15);
    const naPonta = s <= perto ? 'a' : s >= L - perto ? 'b' : null;
    if (!naPonta) return null;
    const q = e[naPonta], dir = naPonta === 'b' ? u : [-u[0], -u[1]];
    const n = [-u[1] * (w || 1) / 2, u[0] * (w || 1) / 2];
    return { ponto: q, direcao: dir, aresta: [[q[0] + n[0], q[1] + n[1]], [q[0] - n[0], q[1] - n[1]]] };
  }

  /** A viga cuja faixa (a largura da mesa, com 4 px de folga) contém o ponto `px` da tela; a mais perto do eixo. */
  _vigaSob(px) {
    if (!this.doc.camadas.has(CAMADA_ESTRUTURA)) return null;
    const t = this.tela, p = t.paraMundo(px), folga = 4 / (t.vp.z || 1), cat = this._catalogoEstrutura;
    let melhor = null, dm = Infinity;
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo !== 'linha' || a.elemento !== 'viga' || !this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      const w = larguraDaVigaGravada(a, cat), L = dist(e.a, e.b);
      if (!(w > 0) || L < 1) continue;
      const u = [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L];
      const s = (p[0] - e.a[0]) * u[0] + (p[1] - e.a[1]) * u[1], d = Math.abs(-(p[0] - e.a[0]) * u[1] + (p[1] - e.a[1]) * u[0]);
      if (s < -folga || s > L + folga || d > w / 2 + folga) continue;
      if (d < dm) { dm = d; melhor = e; }
    }
    return melhor;
  }

  /** As bordas da faixa de cada viga perto de `p` (até `r` mm): as duas da mesa e os dois topos. */
  _bordasDasVigas(p, r) {
    if (!this.doc.camadas.has(CAMADA_ESTRUTURA)) return [];
    const cat = this._catalogoEstrutura, out = [];
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo !== 'linha' || a.elemento !== 'viga' || !this.doc.visivel(e)) continue;
      const w = larguraDaVigaGravada(a, cat), L = dist(e.a, e.b);
      if (!(w > 0) || L < 1) continue;
      const u = [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L];
      const s = (p[0] - e.a[0]) * u[0] + (p[1] - e.a[1]) * u[1], d = Math.abs(-(p[0] - e.a[0]) * u[1] + (p[1] - e.a[1]) * u[0]);
      if (s < -r || s > L + r || d > w / 2 + r) continue;
      const n = [-u[1] * w / 2, u[0] * w / 2];
      const q = [[e.a[0] + n[0], e.a[1] + n[1]], [e.b[0] + n[0], e.b[1] + n[1]], [e.b[0] - n[0], e.b[1] - n[1]], [e.a[0] - n[0], e.a[1] - n[1]]];
      out.push({ id: e.id, segs: [[q[0], q[1]], [q[1], q[2]], [q[2], q[3]], [q[3], q[0]]] });
    }
    return out;
  }

  _desenharLarguraDasVigas() {
    if (!this.doc.camadas.has(CAMADA_ESTRUTURA)) return;
    const t = this.tela, ctx = t.ctx, cat = this._catalogoEstrutura;
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo !== 'linha' || a.elemento !== 'viga' || !this.doc.visivel(e)) continue;
      const w = larguraDaVigaGravada(a, cat), L = dist(e.a, e.b);
      if (!(w > 0) || L < 1 || w * t.vp.z < 2) continue;            // de longe, menos de 2 px: fica a linha
      const n = [-(e.b[1] - e.a[1]) / L * w / 2, (e.b[0] - e.a[0]) / L * w / 2];
      const q = [[e.a[0] + n[0], e.a[1] + n[1]], [e.b[0] + n[0], e.b[1] + n[1]], [e.b[0] - n[0], e.b[1] - n[1]], [e.a[0] - n[0], e.a[1] - n[1]]].map(p => t.paraTela(p));
      const cam = this.doc.camadas.get(e.camada) || {};
      const sel = t.selecao && t.selecao.has(e.id);
      ctx.save();
      ctx.setLineDash([]); ctx.lineWidth = sel ? 1.6 : 1;
      ctx.strokeStyle = sel ? t.cores().selecao : (cam.cor || '#c0392b');
      ctx.fillStyle = cam.cor || '#c0392b'; ctx.globalAlpha = 0.08;
      ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); for (const p of q.slice(1)) ctx.lineTo(p[0], p[1]); ctx.closePath(); ctx.fill();
      ctx.globalAlpha = 1; ctx.stroke();
      ctx.restore();
    }
  }

  /** A "impressão" do que o 3D desenha no chão desta planta: a malha de eixos (EIXO) e o arquitetônico (ARQ …). */
  _impressaoDaReferencia() {
    let n = 0, soma = 0;
    for (const e of this.doc.entidades.values()) {
      const c = String(e.camada || '');
      if (c !== 'EIXO' && !c.startsWith('ARQ ')) continue;
      const p = e.a || (e.vertices && e.vertices[0]) || e.centro || e.posicao || e.p1;
      const q = e.b || (e.vertices && e.vertices[e.vertices.length - 1]) || p;
      n++;
      if (p) soma += p[0] * 1.31 + p[1] * 0.77 + q[0] * 0.53 + q[1] * 1.13 + n * ((e.atributos || {}).eixo ? String(e.atributos.eixo).charCodeAt(0) : 1);
    }
    return `${n}|${Math.round(soma)}`;
  }

  /** Depois de gravar: se a malha ou o arquitetônico mudaram, o 3D ao lado refaz a planta no chão (06/10). */
  _avisarReferencia() {
    if (window.parent === window || !this.projeto) return;
    const agora = this._impressaoDaReferencia(), chave = `${this.projeto}|${this.nomeDesenho}`;
    if (this._referenciaChave !== chave) { this._referenciaChave = chave; this._referenciaUltima = agora; return; }
    if (agora === this._referenciaUltima) return;
    this._referenciaUltima = agora;
    try { window.parent.postMessage({ metalica: 'referencia-mudou', origem: '2d' }, location.origin); } catch { /* */ }
  }

  /** A "impressão" dos elementos da planta (o que o 3D usa deles): muda quando um é lançado, movido, apagado… */
  _impressaoDaPlanta() {
    return JSON.stringify(this.elementosDaPlanta().map(e => [e.id, e.tipo, e.vertices || [e.a, e.b], e.atributos]).sort((x, y) => (x[0] < y[0] ? -1 : 1)));
  }

  /**
   * Depois de gravar a planta: se os elementos dela mudaram desde a última vez, o 3D do projeto troca as peças que
   * vieram desta planta (POST planta/3d {sincronizar}) e o 3D ao lado recarrega — antes era só pelo "Gerar 3D da
   * planta", e apagar ou mover na planta não mexia no 3D (06/10). Desenho sem elemento nenhum desde que abriu (os de
   * detalhamento, as pranchas) não sincroniza.
   */
  async _sincronizar3D(forcar = false, impressao = null) {
    if (!this.projeto || !this.nomeDesenho) return null;
    const agora = impressao ?? this._impressaoDaPlanta();          // a da planta gravada, quando vem do salvar
    const chave = `${this.projeto}|${this.nomeDesenho}`;
    if (this._sincroniaChave !== chave) { this._sincroniaChave = chave; this._sincroniaUltima = undefined; }
    // fora do dev (11/10, a sincronia passou a valer no instalado): o desenho que abre sem elemento nenhum não pede nada
    // ao servidor — a sincronia abre o modelo 3D, e o IFC grande pesava a cada gravação de qualquer desenho
    if (!forcar && agora === '[]' && this._sincroniaUltima === undefined && !(await this._temPreMoldado())) { this._sincroniaUltima = agora; return null; }
    // a planta sem elemento nenhum também sincroniza (uma vez): as peças que sobraram dela no 3D saem — o pilar apagado
    // numa versão anterior da planta ficava no 3D sem nada no 2D para apagar (07/10). O servidor só tira as peças
    // marcadas com esta planta, então o desenho de detalhamento ou a prancha vazios não mexem em nada.
    if (!forcar && agora === this._sincroniaUltima) return null;
    this._sincroniaUltima = agora;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/estrutura/3d`, { desenho: this.nomeDesenho, sincronizar: true });
    } catch (e) { this.aviso(`O 3D não acompanhou a planta: ${e.message}`, 'atencao', 8000); this._sincroniaUltima = null; return null; }
    if (!r.mudou) return r;
    // a cobertura retrátil redesenhada na planta pelo servidor (as linhas das tesouras): carrega sem mexer na vista
    if (r.desenho && !this._temPendente()) this.carregar(r.desenho, { enquadrar: false });
    this.dica(`3D atualizado pela planta: ${r.entrou} peça(s)${r.saiu ? `, ${r.saiu} trocada(s) ou removida(s)` : ''}.`);
    for (const a of r.avisos || []) this.aviso(a, 'atencao', 10000);
    if (window.parent !== window) { try { window.parent.postMessage({ metalica: 'modelo-mudou', origem: '2d' }, location.origin); } catch { /* */ } }
    return r;
  }

  _guardarMedidas() { try { localStorage.setItem(CHAVE, JSON.stringify(this.medidasEstrutura)); } catch { /* */ } }

  _garantirCamadaEstrutura() {
    if (!this.doc.camadas.has(CAMADA_ESTRUTURA)) {
      this.doc.camadas.set(CAMADA_ESTRUTURA, { nome: CAMADA_ESTRUTURA, cor: '#c0392b', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.5 });
      this.doc.notificar([], 'aparencia');
    }
  }

  /** os elementos lançados neste desenho */
  elementosDaPlanta() { return [...this.doc.entidades.values()].filter(e => (e.atributos || {}).elemento); }

  _proximaMarca(elemento) {
    const pref = { pilar: 'P', viga: 'V', fundacao: 'S', consolo: 'CS', tesoura: 'TC', chapa: 'CH', furo: 'F', parafuso: 'PF', painel: 'PN', laje: 'L', escada: 'E' }[elemento] || 'X';
    const usados = new Set(this.elementosDaPlanta().filter(e => e.atributos.elemento === elemento).map(e => e.atributos.marca));
    let n = 1; while (usados.has(`${pref}${n}`)) n++;
    return `${pref}${n}`;
  }

  /** os níveis do projeto (nome → z mm), lidos uma vez */
  async niveisDoProjeto() {
    if (this._niveisProjeto) return this._niveisProjeto;
    let lista = [];
    if (this.projeto) {
      try { const r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}`); lista = ((r.projeto || r).niveis || []).filter(n => n && n.nome); } catch { lista = []; }
    }
    this._niveisProjeto = lista;
    return lista;
  }

  /** os catálogos: seções de concreto (pré-moldado, no dev) e perfis de aço (Metálica) */
  async catalogoEstrutura() {
    if (this._catalogoEstrutura) return this._catalogoEstrutura;
    const c = { secoes: [], perfis: [], acos: [], grupos: [], dados: {} };
    // o pré-moldado só existe no servidor dev: fora dele nem se pede (o 404 sujava o console)
    if (await this._temPreMoldado()) {
      try { const j = await pedir('/api/premoldado/catalogo'); c.secoes = (j.secoes_pilar || []).map(s => [s.b, s.h]); } catch { /* sem o pré-moldado */ }
    }
    try {
      const j = await pedir('/api/catalogo');
      // o catálogo manda os perfis por família ({I: [...], U: [...], L: [...], Ue, tubo}): a lista antiga esperava um
      // vetor, o .map quebrava calado e o painel do pilar só oferecia o W 310×38,7 padrão (06/10)
      const fam = j.perfis || [];
      c.grupos = Array.isArray(fam) ? [['Perfis', fam.map(p => (typeof p === 'string' ? p : p.nome)).filter(Boolean)]] : gruposDePerfis(fam);
      c.perfis = c.grupos.flatMap(([, nomes]) => nomes).slice(0, 400);
      // as medidas de cada perfil, para desenhar a seção na planta
      for (const p of (Array.isArray(fam) ? fam : Object.values(fam).flat())) if (p && p.nome) c.dados[p.nome] = p;
      c.acos = (j.acos || []).map(a => (typeof a === 'string' ? a : a.nome)).filter(Boolean);
    } catch { /* sem catálogo */ }
    this._catalogoEstrutura = c;
    return c;
  }

  // ---- a barra da disciplina, à direita do desenho
  async _montarBarraDisciplina() {
    const barra = document.getElementById('barra-disciplina');
    if (!barra) return;
    this.el.barraDisciplina = barra;
    // a disciplina: a escolhida por último neste CAD, senão a área do projeto; o pré-moldado só existe no dev
    let area = '';
    if (this.projeto) {
      try { const r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}`); area = (r.projeto || r).area || ''; } catch { area = ''; }
    }
    this._comPreMoldado = await this._temPreMoldado();
    let d = '';
    try { d = localStorage.getItem(`${CHAVE_DISCIPLINA}.${this.projeto || ''}`) || ''; } catch { d = ''; }
    if (!DISCIPLINAS[d]) d = area === 'premoldado' ? 'premoldado' : 'metalica';
    // a configuração do galpão (a tela dos dados e do cálculo) fica num lugar próprio: o menu Estrutura e a barra
    this._obraPreMoldada = area === 'premoldado' && (await this._temPreMoldado());
    for (const b of document.querySelectorAll('[data-acao="pm-configuracao"]')) b.hidden = !this._obraPreMoldada;
    if (d === 'premoldado' && !this._comPreMoldado) d = 'metalica';
    this._disciplina = d;
    this._desenharBarraDisciplina();
  }

  // ---- a disciplina, de fora (a faixa única da área de trabalho: web/area.js)
  /** 'metalica' ou 'premoldado' — a escolhida na barra da direita */
  disciplina() { return this._disciplina || 'metalica'; }

  /** as disciplinas disponíveis aqui (o pré-moldado só no dev), com o rótulo */
  disciplinas() {
    return Object.entries(DISCIPLINAS).filter(([k]) => k !== 'premoldado' || this._comPreMoldado)
      .map(([k, D]) => ({ id: k, rotulo: D.rotulo, titulo: D.titulo }));
  }

  /** troca a disciplina (e a barra da direita, mesmo escondida); devolve a escolhida */
  escolherDisciplina(k) {
    if (!DISCIPLINAS[k] || (k === 'premoldado' && !this._comPreMoldado)) return this.disciplina();
    this._disciplina = k;
    try { localStorage.setItem(`${CHAVE_DISCIPLINA}.${this.projeto || ''}`, k); } catch { /* */ }
    this._desenharBarraDisciplina();
    return k;
  }

  /**
   * os botões da disciplina atual (ou da pedida), como a barra da direita os mostra: {ferramenta, rotulo, icone,
   * material, ativar()} — ativar() fixa o material do botão (o pilar de aço e o de concreto são a mesma
   * ferramenta) e liga a ferramenta; e as ações da planta: {acao, rotulo, icone, executar()}
   */
  itensDaDisciplina(k = this.disciplina()) {
    const D = DISCIPLINAS[k] || DISCIPLINAS.metalica;
    const itens = D.itens.map(([id, rotulo, icone, fixa]) => ({
      ferramenta: id, rotulo, icone: ICONES[icone], material: (fixa && fixa.material) || null,
      ativar: () => {
        if (fixa) { Object.assign(this.medidasEstrutura, fixa); this._guardarMedidas(); }
        if (this.ferramenta && this.ferramenta.constructor.id === id) this.ativarFerramenta('selecionar');
        this.ativarFerramenta(id);
      } }));
    const acoes = (this._obraPreMoldada ? [...ACOES_PLANTA, ['config', 'Configuração do galpão pré-moldado', 'config', 'configuracaoPreMoldado']] : ACOES_PLANTA)
      .map(([acao, rotulo, icone, metodo]) => ({ acao, rotulo, icone: ICONES[icone], executar: () => this[metodo]() }));
    return { disciplina: k, itens, acoes };
  }

  /** o servidor está no modo dev (onde o pré-moldado existe)? — pela /api/versao, uma vez */
  async _temPreMoldado() {
    if (this._ehDev === undefined) {
      try { this._ehDev = !!(await pedir('/api/versao')).dev; } catch { this._ehDev = false; }
    }
    return this._ehDev;
  }

  _desenharBarraDisciplina() {
    const barra = this.el.barraDisciplina;
    if (!barra) return;
    barra.replaceChildren();
    const disc = DISCIPLINAS[this._disciplina];
    // o seletor da disciplina, no topo
    const seletor = el('div', { class: 'seletor-disciplina' });
    for (const [k, D] of Object.entries(DISCIPLINAS)) {
      if (k === 'premoldado' && !this._comPreMoldado) continue;
      seletor.append(el('button', { type: 'button', class: 'disciplina', 'aria-pressed': String(k === this._disciplina), title: `Elementos ${D.titulo}`, texto: D.rotulo,
        onclick: () => this.escolherDisciplina(k) }));
    }
    barra.append(seletor, el('div', { class: 'grupo-rotulo', texto: disc.rotulo }));
    for (const [id, rotulo, icone, fixa] of disc.itens) {
      const b = el('button', { type: 'button', class: 'ferramenta', 'data-ferramenta': id, 'data-material': fixa && fixa.material, 'aria-pressed': 'false', title: rotulo });
      b.innerHTML = ICONES[icone];
      b.addEventListener('click', () => {
        if (fixa) { Object.assign(this.medidasEstrutura, fixa); this._guardarMedidas(); }
        if (this.ferramenta && this.ferramenta.constructor.id === id) this.ativarFerramenta('selecionar');
        this.ativarFerramenta(id);
      });
      barra.append(b);
    }
    barra.append(el('div', { class: 'grupo-rotulo', texto: 'Planta' }));
    const acoes = this._obraPreMoldada ? [...ACOES_PLANTA, ['config', 'Configuração do galpão pré-moldado (dados, cálculo, memorial, pranchas)', 'config', 'configuracaoPreMoldado']] : ACOES_PLANTA;
    for (const [, rotulo, icone, metodo] of acoes) {
      const b = el('button', { type: 'button', class: 'ferramenta acao', title: rotulo });
      b.innerHTML = ICONES[icone];
      b.addEventListener('click', () => this[metodo]());
      barra.append(b);
    }
    this._marcarBarraDisciplina(this.ferramenta ? this.ferramenta.constructor.id : '');
    // quem mostra as ferramentas de fora (a faixa da área de trabalho) fica sabendo: na abertura (a disciplina sai
    // depois de ler o projeto) e a cada troca
    try { window.dispatchEvent(new CustomEvent('cad:disciplina', { detail: { disciplina: this._disciplina } })); } catch { /* */ }
  }

  /** o botão da ferramenta ativa aceso (o pilar de concreto e o de aço são a mesma ferramenta: o material decide) */
  _marcarBarraDisciplina(id) {
    const barra = this.el && this.el.barraDisciplina;
    if (!barra) return;
    const M = this.medidasEstrutura || {};
    for (const b of barra.querySelectorAll('.ferramenta[data-ferramenta]')) {
      const aceso = b.dataset.ferramenta === id && (!b.dataset.material || b.dataset.material === M.material);
      b.setAttribute('aria-pressed', String(aceso));
    }
  }

  // ---- o painel de medidas da ferramenta ativa (flutuante, ao lado da barra da disciplina)
  async _painelEstrutura(id) {
    const M = this.medidasEstrutura;
    if (!this._painelEstr) {
      this._painelEstr = el('div', { class: 'painel-estrutura' });
      this._painelEstr.style.cssText = 'position:fixed;top:96px;z-index:40;background:var(--painel,#1b2433);color:var(--texto,#e6edf7);' +
        'border:1px solid var(--borda,#334155);border-radius:8px;padding:8px 10px;font:12px system-ui;box-shadow:0 6px 18px rgba(0,0,0,.35);min-width:230px';
      document.body.append(this._painelEstr);
    }
    const P = this._painelEstr; P.hidden = false; P.replaceChildren();
    // encostado na barra da disciplina (à direita), ou na da esquerda sem ela
    // na área de trabalho (html.barra-unica: as colunas de ferramentas escondidas, a faixa única no topo, fora deste
    // quadro) o painel vai para o canto de cima à esquerda do desenho
    const bd = this.el && this.el.barraDisciplina;
    const naArea = document.documentElement.classList.contains('barra-unica');
    P.style.top = naArea ? '12px' : '96px';
    if (naArea) { P.style.right = ''; P.style.left = '12px'; }
    else if (bd && bd.offsetParent) { P.style.left = ''; P.style.right = `${Math.max(0, window.innerWidth - bd.getBoundingClientRect().left) + 6}px`; }
    else { P.style.right = ''; P.style.left = '58px'; }
    const [niveis, cat] = await Promise.all([this.niveisDoProjeto(), this.catalogoEstrutura()]);
    const titulo = { estr_pilar: 'Pilar', estr_viga: 'Viga', estr_fundacao: 'Fundação', estr_consolo: 'Consolo', estr_tesoura: 'Tesoura de concreto',
                     estr_chapa: 'Chapa', estr_furo: 'Furo', estr_parafuso: 'Parafuso', estr_painel: 'Placa de fechamento', estr_laje: 'Laje',
                     estr_escada: 'Escada' }[id] || 'Elemento';
    P.append(el('div', { texto: titulo, style: 'font-weight:600;margin-bottom:6px;color:var(--azul,#7fb0ff)' }));
    const linha = (rot, inp) => { const l = el('label', { style: 'display:flex;justify-content:space-between;gap:8px;align-items:center;margin:3px 0' }, rot, inp); P.append(l); return inp; };
    const refazer = () => { this._guardarMedidas(); this._painelEstrutura(id); if (this.ferramenta && this.ferramenta.desenhar) this.ferramenta.desenhar(); };
    const num = (k, passo = 1) => {
      const i = el('input', { type: 'text', value: String(M[k]).replace('.', ','), style: 'width:76px' });
      i.onkeydown = ev => ev.stopPropagation();
      i.onchange = () => { const v = parseFloat(i.value.replace(',', '.')); if (isFinite(v)) { M[k] = v; this._guardarMedidas(); if (this.ferramenta && this.ferramenta.desenhar) this.ferramenta.desenhar(); } };
      return i;
    };
    // os comprimentos e os níveis na unidade das medidas do desenho (mm, cm ou m — 07/10, pedido do usuário); a
    // espessura, o diâmetro e a capa ficam em mm, e as seções de concreto em cm, como se dão
    const U = unidadeAtual();
    const rotU = (s) => (U === 'mm' ? s : s.replace('(mm)', `(${U})`));
    const numMM = (k) => {
      const i = el('input', { type: 'text', value: naUnidade(+M[k] || 0), style: 'width:76px', title: `em ${U}; com a unidade junto (475cm, 4,75m, 4750mm) vale a digitada` });
      i.onkeydown = ev => ev.stopPropagation();
      i.onchange = () => {
        const v = paraMilimetros(i.value);
        if (v === null || !isFinite(v)) return;
        M[k] = v; i.value = naUnidade(v); this._guardarMedidas();
        if (this.ferramenta && this.ferramenta.desenhar) this.ferramenta.desenhar();
      };
      return i;
    };
    const sel = (k, ops, aoMudar) => {
      const s = el('select', {}, ...ops.map(([v, t]) => el('option', { value: v, texto: t, selected: String(M[k]) === String(v) ? 'selected' : undefined })));
      s.onchange = () => { M[k] = isFinite(+s.value) && s.value !== '' && !ops.some(([v]) => typeof v === 'string' && !isFinite(+v)) ? +s.value : s.value; (aoMudar || refazer)(); };
      return s;
    };
    const nivel = (k, rot) => {
      const caixa = el('div', { style: 'display:flex;gap:4px' });
      M.vinculo = M.vinculo || {};
      // o vínculo de outro projeto (nível que não existe aqui) cai: fica o número
      if (M.vinculo[k] && !niveis.some(n => n.nome === M.vinculo[k])) delete M.vinculo[k];
      const vinc = niveis.find(n => n.nome === M.vinculo[k]);
      if (vinc) M[k] = vinc.z;
      const i = numMM(k);
      if (niveis.length) {
        const s = el('select', { title: 'Vincular ao nível do projeto (Estrutura → Níveis…): a cota acompanha o nível quando ele muda. Digitar o número desvincula.' },
          el('option', { value: '', texto: '— número —' }),
          ...niveis.map(n => el('option', { value: n.nome, texto: `${n.nome} (${numero(n.z / 1000, 2)})`, selected: vinc && vinc.nome === n.nome ? 'selected' : undefined })));
        s.onchange = () => {
          const n = niveis.find(x => x.nome === s.value);
          if (n) { M.vinculo[k] = n.nome; M[k] = n.z; i.value = naUnidade(n.z); } else delete M.vinculo[k];
          this._guardarMedidas();
        };
        const digitar = i.onchange;
        i.onchange = () => { delete M.vinculo[k]; s.value = ''; digitar(); };
        caixa.append(s);
      }
      caixa.append(i);
      linha(rotU(rot), caixa);
    };
    if (id === 'estr_pilar' || id === 'estr_viga') {
      linha('material', sel('material', [['concreto', 'concreto'], ['aco', 'aço']]));
      if (M.material === 'aco' && id === 'estr_pilar') {
        linha('tipo', sel('pilar_aco', [['perfil', 'perfil (W, U, L…)'], ['poste', 'poste circular (tubo)']]));
      }
      if (M.material === 'aco' && id === 'estr_pilar' && M.pilar_aco === 'poste') {
        // o poste: os tubos circulares (TC) do catálogo
        const tubos = cat.perfis.filter(p => /^TC\s/i.test(p));
        const lista = tubos.length ? tubos : [M.perfil_poste];
        if (!lista.includes(M.perfil_poste)) M.perfil_poste = lista.find(p => /168,3/.test(p)) || lista[lista.length - 1];
        linha('tubo', sel('perfil_poste', lista.map(p => [p, p]), () => { this._guardarMedidas(); if (this.ferramenta && this.ferramenta.desenhar) this.ferramenta.desenhar(); }));
        const acos = cat.acos.length ? cat.acos : [M.aco];
        linha('aço', sel('aco', acos.map(a => [a, a]), () => this._guardarMedidas()));
      } else if (M.material === 'aco') {
        // a lista em grupos (W, U, cantoneira, tubos…), cada um pela altura e pelo peso
        const grupos = cat.grupos.length ? cat.grupos : [['Perfis', [M.perfil]]];
        const s = el('select', {});
        if (!grupos.some(([, n]) => n.includes(M.perfil))) s.append(el('option', { value: M.perfil, texto: M.perfil, selected: 'selected' }));
        for (const [titulo, nomes] of grupos) {
          s.append(el('optgroup', { label: titulo }, ...nomes.map(p => el('option', { value: p, texto: rotuloPerfil(p, cat.dados[p]), selected: p === M.perfil ? 'selected' : undefined }))));
        }
        s.onchange = () => { M.perfil = s.value; this._guardarMedidas(); if (this.ferramenta && this.ferramenta.desenhar) this.ferramenta.desenhar(); };
        linha('perfil', s);
        const acos = cat.acos.length ? cat.acos : [M.aco];
        linha('aço', sel('aco', acos.map(a => [a, a]), () => this._guardarMedidas()));
      } else {
        linha('seção', sel('secao_tipo', SECOES.map(s => [s, s])));
        if (id === 'estr_pilar' && cat.secoes.length && M.secao_tipo === 'retangular') {
          const s = el('select', {}, el('option', { value: '', texto: 'catálogo…' }), ...cat.secoes.map(([b, h]) => el('option', { value: `${b}x${h}`, texto: `${b} × ${h}` })));
          s.onchange = () => { if (s.value) { const [b, h] = s.value.split('x').map(Number); M.b = b; M.h = h; refazer(); } };
          linha('do catálogo', s);
        }
        for (const k of CAMPOS_SECAO[M.secao_tipo]) if (!(id === 'estr_viga' && k === 'h')) linha(ROTULO[k], num(k));
        if (id === 'estr_viga') linha('h (altura da viga, cm)', num('vh'));
      }
    }
    if (id === 'estr_pilar') {
      nivel('nivel_base', 'nível da base (mm)'); nivel('nivel_topo', 'nível do topo (mm)');
      if (!ehPoste(M)) linha('giro (R)', sel('rotacao', [[0, '0°'], [90, '90°']]));          // o poste é redondo: não gira
      // o ponto de inserção: a grade 3×3 (a linha de cima primeiro, como se vê na tela); o Tab percorre
      const a = Number.isInteger(M.ancora) ? M.ancora : 4;
      const grade = el('div', { style: 'display:grid;grid-template-columns:repeat(3,16px);gap:3px' });
      for (const k of [6, 7, 8, 3, 4, 5, 0, 1, 2]) {
        const b = el('button', { type: 'button', title: ANCORAS[k],
          style: `width:16px;height:16px;padding:0;border-radius:50%;cursor:pointer;border:1.5px solid var(--azul,#7fb0ff);background:${k === a ? 'var(--azul,#7fb0ff)' : 'transparent'}` });
        b.onclick = () => { M.ancora = k; refazer(); };
        grade.append(b);
      }
      // numa div, não num label: o clique no texto de um label vai para o primeiro botão dele
      P.append(el('div', { style: 'display:flex;justify-content:space-between;gap:8px;align-items:center;margin:3px 0' },
        el('span', { title: 'O ponto do pilar que vai no clique (no cruzamento dos eixos): o centro, um canto ou o meio de uma face. Tab troca.' }, `ponto de inserção (Tab):`, el('br'), el('small', { style: 'opacity:.7', texto: ANCORAS[a] })), grade));
    }
    if (id === 'estr_viga') {
      // alinhar pelo eixo, pela face de cima ou pela de baixo: o nível dado é o daquela linha
      const chave = M.material === 'aco' ? 'aco' : 'concreto';
      M.viga_alinhamento = { aco: 'eixo', concreto: 'topo', ...(M.viga_alinhamento || {}) };
      const s = el('select', { title: 'O nível da viga é o do eixo dela, o da face de cima ou o da face de baixo' },
        ...Object.entries(ROTULO_ALINHAMENTO).map(([v, t]) => el('option', { value: v, texto: t, selected: M.viga_alinhamento[chave] === v ? 'selected' : undefined })));
      s.onchange = () => { M.viga_alinhamento[chave] = s.value; refazer(); };
      linha('alinhar pelo(a)', s);
      nivel('nivel_topo', `nível da ${ROTULO_ALINHAMENTO[alinhamentoDaViga(M)]} (mm)`.replace('nível da eixo', 'nível do eixo'));
    }
    if (id === 'estr_fundacao') { linha('tipo', sel('fund_tipo', [['sapata', 'sapata'], ['bloco', 'bloco sobre estacas']])); linha(rotU('lado em X (mm)'), numMM('fund_b')); linha(rotU('lado em Y (mm)'), numMM('fund_a')); linha(rotU('altura (mm)'), numMM('fund_h')); nivel('nivel_base', 'nível do topo (mm)'); }
    if (id === 'estr_consolo') { linha(rotU('comprimento (mm)'), numMM('cons_c')); linha(rotU('largura (mm)'), numMM('cons_b')); linha(rotU('altura (mm)'), numMM('cons_h')); nivel('nivel_topo', 'nível do topo (mm)'); }
    if (id === 'estr_tesoura') {
      linha('forma', sel('tes_forma', [['duas águas', 'duas águas (mais alta no meio)'], ['uma água', 'uma água (altura constante)']]));
      linha('mesa b (cm)', num('tes_bf')); linha('mesa h (cm)', num('tes_hf')); linha('alma (cm)', num('tes_bw'));
      linha('h no apoio (cm)', num('tes_h'));
      if (M.tes_forma !== 'uma água') linha('h no meio (cm)', num('tes_hm'));
      nivel('nivel_topo', 'apoio no 1º clique (mm)'); nivel('nivel_fim', 'apoio no 2º clique (mm)');
    }
    if (id === 'estr_chapa') {
      linha('espessura (mm)', num('chapa_esp'));
      const acos = ['ASTM A36', 'ASTM A572 Gr.50', 'SAE 1020', ...cat.acos.filter(a => !['ASTM A36', 'ASTM A572 Gr.50', 'SAE 1020'].includes(a))];
      linha('aço', sel('chapa_aco', acos.map(a => [a, a]), () => this._guardarMedidas()));
      nivel('nivel_topo', 'nível da face de cima (mm)');
    }
    if (id === 'estr_furo') linha('diâmetro (mm)', num('furo_d'));
    if (id === 'estr_painel') {
      linha('tipo', sel('pn_tipo', [['alveolar', 'alveolar'], ['maciço', 'maciço']]));
      linha('painéis', sel('pn_orient', [['vertical', 'em pé (verticais)'], ['horizontal', 'deitados (horizontais)']]));
      linha('espessura (mm)', num('pn_esp')); linha(rotU('largura do painel (mm)'), numMM('pn_mod'));
      nivel('nivel_base', 'nível da base (mm)'); nivel('nivel_topo', 'nível do topo (mm)');
    }
    if (id === 'estr_laje') {
      linha('tipo', sel('laje_tipo', [['alveolar', 'alveolar'], ['pré-laje', 'pré-laje'], ['maciça', 'maciça']]));
      linha('espessura da placa (mm)', num('laje_esp'));
      if (M.laje_tipo !== 'maciça') { linha('capa (mm)', num('laje_capa')); linha('placas no sentido', sel('laje_sentido', [['x', 'X'], ['y', 'Y']])); linha(rotU('largura da placa (mm)'), numMM('laje_mod')); }
      nivel('nivel_topo', 'nível do topo (mm)');
    }
    if (id === 'estr_escada') {
      linha(rotU('largura (mm)'), numMM('esc_larg')); linha(rotU('espelho máximo (mm)'), numMM('esc_espelho')); linha('espessura da laje (mm)', num('esc_t'));
      nivel('nivel_base', 'nível de baixo (mm)'); nivel('nivel_topo', 'nível de cima (mm)');
    }
    if (id === 'estr_parafuso') { linha('diâmetro (mm)', num('paraf_d')); linha('comprimento (mm)', num('paraf_L')); nivel('nivel_topo', 'nível da cabeça (mm)'); }
    P.append(el('div', { texto: 'o painel vale para o próximo clique; o que já foi lançado se edita nas propriedades', style: 'opacity:.6;margin-top:4px;max-width:240px' }));
  }

  _fecharPainelEstrutura() { if (this._painelEstr) this._painelEstr.hidden = true; }

  /** as propriedades de um elemento selecionado (chamado pelo painel de propriedades do CAD) */
  _propsEstrutura(g, ents) {
    // vários elementos selecionados (os rótulos deles podem vir junto): só os níveis, aplicados a todos — vincular os
    // pilares todos ao nível de uma vez (06/10)
    const elems = ents.filter(x => (x.atributos || {}).elemento);
    const varios = elems.length > 1 && ents.every(x => (x.atributos || {}).elemento || (x.atributos || {}).rotulo_de);
    const soRotulos = elems.length === 1 && ents.every(x => x === elems[0] || (x.atributos || {}).rotulo_de === elems[0].id);
    const e = ents.length === 1 ? ents[0] : soRotulos ? elems[0] : null;
    let a = e && e.atributos;
    if (varios) {
      a = { elemento: elems[0].atributos.elemento };
      for (const k of ['nivel_base', 'nivel_topo', 'nivel_fim']) {
        const vs = elems.filter(x => x.atributos[k] !== undefined).map(x => x.atributos[k]);
        if (vs.length) a[k] = vs.every(v => v === vs[0]) ? vs[0] : null;
      }
    }
    if (!a || !a.elemento) return false;
    const alvos = varios ? elems : [e];
    const alterar = (campos, rotulo) => this.executar(new ComandoAlterar(
      Object.fromEntries(alvos.map(x => [x.id, { atributos: { ...x.atributos, ...Object.fromEntries(Object.entries(campos).filter(([k]) => !varios || x.atributos[k] !== undefined || k === 'nivel_base' && x.atributos.elemento === 'pilar')) } }])), rotulo));
    g.append(el('div', { class: 'origem' }, varios ? el('b', { texto: `${elems.length} elementos (${[...new Set(elems.map(x => x.atributos.marca).filter(Boolean))].slice(0, 8).join(', ')}${elems.length > 8 ? '…' : ''})` })
      : el('b', { texto: `${a.elemento} ${a.marca || ''}` }), varios ? ' · os níveis valem para todos' : ` · ${a.material || ''} · ${textoSecao(a)}`));
    const campo = (rot, chave, valor, aoMudar) => {
      const i = el('input', { type: 'text', value: valor ?? '' });
      i.addEventListener('change', () => aoMudar(i.value));
      g.append(el('label', { texto: rot }), i);
    };
    if (!varios) campo('Marca', 'marca', a.marca, v => {
      // o rótulo acompanha a marca
      const mud = { [e.id]: { atributos: { ...a, marca: v } } };
      for (const r of this.doc.entidades.values()) if ((r.atributos || {}).rotulo_de === e.id && r.tipo === 'texto') mud[r.id] = { texto: v };
      this.executar(new ComandoAlterar(mud, 'Marca'));
    });
    // o nível: vinculado a um nível do projeto (o nome; a cota segue o nível) ou o número — pedido do usuário, 06/10:
    // "vincular o comprimento aos níveis"
    if (!this._niveisProjeto) this.niveisDoProjeto().then(l => { if (l.length) this._agendarPaineis('props'); }).catch(() => {});
    const niveis = this._niveisProjeto || [];
    const campoNivel = (rot, k, rotulo) => {
      const v = a[k], vinc = typeof v === 'string' ? niveis.find(n => n.nome === v) : null;
      const z = vinc ? vinc.z : typeof v === 'string' ? parseFloat(v.replace(',', '.')) || 0 : v;     // null: valores diferentes
      const i = el('input', { type: 'text', value: z == null ? '' : naUnidade(z), title: vinc ? `vinculado ao nível ${vinc.nome}: digitar um número desvincula` : `em ${unidadeAtual()}` });
      if (v === null) i.placeholder = 'vários';
      i.addEventListener('change', () => { const mm = paraMilimetros(i.value); alterar({ [k]: mm !== null && isFinite(mm) ? mm : 0 }, rotulo); });
      if (!niveis.length) { g.append(el('label', { texto: `${rot} (${unidadeAtual()})` }), i); return; }
      const s = el('select', { title: 'Vincular ao nível do projeto: a cota acompanha o nível quando ele muda (Estrutura → Níveis…)' },
        el('option', { value: '', texto: typeof v === 'string' && !vinc ? `${v} (não existe mais)` : v === null ? '— vários —' : '— número —' }),
        ...niveis.map(n => el('option', { value: n.nome, texto: `${n.nome} (${numero(n.z / 1000, 2)})`, selected: vinc && vinc.nome === n.nome ? 'selected' : undefined })));
      s.addEventListener('change', () => { const n = niveis.find(x => x.nome === s.value); if (n || z !== null) alterar({ [k]: n ? n.nome : z }, rotulo); });
      i.style.width = '64px'; s.style.flex = '1'; s.style.minWidth = '0';
      g.append(el('label', { texto: `${rot} (${unidadeAtual()})` }), el('div', { style: 'display:flex;gap:4px;min-width:0' }, s, i));
    };
    if (a.elemento === 'pilar' || a.nivel_base !== undefined) campoNivel(a.elemento === 'pilar' ? 'Nível da base' : 'Nível de baixo', 'nivel_base', 'Nível da base');
    if (a.elemento === 'viga' && !varios) {
      const atual = a.alinhamento || (a.material === 'aco' ? 'eixo' : 'topo');
      const s = el('select', {}, ...Object.entries(ROTULO_ALINHAMENTO).map(([v, t]) => el('option', { value: v, texto: t, selected: atual === v ? 'selected' : undefined })));
      s.addEventListener('change', () => alterar({ alinhamento: s.value }, 'Alinhamento da viga'));
      g.append(el('label', { texto: 'Alinhar pelo(a)' }), s);
    }
    if (a.nivel_topo !== undefined) campoNivel(a.elemento === 'viga' ? (varios ? 'Nível da viga' : `Nível da ${ROTULO_ALINHAMENTO[a.alinhamento || (a.material === 'aco' ? 'eixo' : 'topo')]}`.replace('Nível da eixo', 'Nível do eixo')) : 'Nível do topo', 'nivel_topo', 'Nível do topo');
    if (varios) { if (a.nivel_fim !== undefined) campoNivel('Apoio no fim', 'nivel_fim', 'Apoio no fim'); return true; }
    if (a.secao && !a.secao.perfil) {
      for (const k of Object.keys(a.secao)) if (k !== 'tipo') campo(`${ROTULO[k] || k}`, k, a.secao[k], v => alterar({ secao: { ...a.secao, [k]: parseFloat(v.replace(',', '.')) || a.secao[k] } }, 'Seção'));
    }
    if (a.secao && a.secao.perfil) campo('Perfil', 'perfil', a.secao.perfil, v => alterar({ secao: { ...a.secao, perfil: v } }, 'Perfil'));
    // a tesoura de aço é um tipo (T1 em vários eixos): mudar um perfil pergunta se vale para todas ou só para esta
    // (que vira outro tipo, T1A — decisão do usuário, 11/10)
    if (a.elemento === 'trelica' && a.perfis) {
      const ROT = { banzo_sup: 'Banzo superior', banzo_inf: 'Banzo inferior', diagonal: 'Diagonais e montantes' };
      for (const k of Object.keys(ROT)) campo(ROT[k], k, a.perfis[k] || '', v => this._mudarTipoTrelica(e, { perfis: { ...a.perfis, [k]: v.trim() } }, ROT[k]));
    }
    const emMM = (v, antes) => { const mm = paraMilimetros(v); return mm !== null && isFinite(mm) && mm > 0 ? mm : antes; };
    if (a.altura !== undefined) campo(`Altura (${unidadeAtual()})`, 'altura', naUnidade(a.altura), v => alterar({ altura: emMM(v, a.altura) }, 'Altura'));
    if (a.nivel_fim !== undefined) campoNivel('Apoio no fim', 'nivel_fim', 'Apoio no fim');
    if (a.espessura !== undefined) campo('Espessura (mm)', 'espessura', a.espessura, v => alterar({ espessura: parseFloat(v.replace(',', '.')) || a.espessura }, 'Espessura'));
    if (a.diametro !== undefined) campo('Diâmetro (mm)', 'diametro', a.diametro, v => alterar({ diametro: parseFloat(v.replace(',', '.')) || a.diametro }, 'Diâmetro'));
    if (a.comprimento !== undefined) campo(`Comprimento (${unidadeAtual()})`, 'comprimento', naUnidade(a.comprimento), v => alterar({ comprimento: emMM(v, a.comprimento) }, 'Comprimento'));
    return true;
  }

  /** Muda a tesoura `e` (os perfis): com outras da mesma marca, todas mudam juntas ou esta vira um tipo novo (T1A). */
  async _mudarTipoTrelica(e, campos, rotulo) {
    const a = e.atributos;
    const trels = this.elementosDaPlanta().filter(x => x.atributos.elemento === 'trelica');
    const irmas = trels.filter(x => x !== e && x.atributos.marca === a.marca);
    let alvos = [e], marca = a.marca;
    if (irmas.length) {
      const usadas = new Set(trels.map(x => x.atributos.marca));
      let s = 'A';
      while (usadas.has(a.marca + s)) s = String.fromCharCode(s.charCodeAt(0) + 1);
      const rTodas = el('input', { type: 'radio', name: 'tipo-trelica', checked: true }), rSo = el('input', { type: 'radio', name: 'tipo-trelica' });
      const corpo = el('div', {}, el('div', { class: 'explica', texto: `A ${a.marca} está em ${irmas.length + 1} eixos (${[...new Set([e, ...irmas].map(x => x.atributos.eixo).filter(Boolean))].join(', ')}).` }),
        el('label', { class: 'linha' }, rTodas, ` mudar todas as ${a.marca}`),
        el('label', { class: 'linha' }, rSo, ` só esta — vira o tipo ${a.marca + s}`));
      if (await this.dialogo({ titulo: `${rotulo} da ${a.marca}`, corpo, ok: 'Mudar' }) !== 'ok') { this._agendarPaineis('props'); return; }
      if (rTodas.checked) alvos = [e, ...irmas]; else marca = a.marca + s;
    }
    const mud = {};
    for (const x of alvos) mud[x.id] = { atributos: { ...x.atributos, ...campos, ...(marca !== a.marca ? { marca } : {}) } };
    if (marca !== a.marca) for (const r of this.doc.entidades.values()) if ((r.atributos || {}).rotulo_de === e.id && r.tipo === 'texto') mud[r.id] = { texto: marca };
    this.executar(new ComandoAlterar(mud, `${rotulo} da ${marca}`));
  }

  // ---- os níveis do projeto
  async dialogoNiveis() {
    if (!this.projeto) { this.aviso('Os níveis ficam no projeto: abra um projeto.', 'atencao'); return; }
    const lista = (await this.niveisDoProjeto()).map(n => ({ ...n, _antes: n.nome }));
    const corpo = el('div', {});
    const tab = el('div', { style: 'display:grid;grid-template-columns:1fr 110px 28px;gap:4px;align-items:center' });
    const desenhar = () => {
      tab.replaceChildren(el('b', { texto: 'Nome' }), el('b', { texto: 'z (mm)' }), el('span'));
      lista.forEach((n, i) => {
        const nome = el('input', { type: 'text', value: n.nome }); nome.onchange = () => { n.nome = nome.value; };
        const z = el('input', { type: 'text', value: String(n.z) }); z.onchange = () => { n.z = parseFloat(z.value.replace(',', '.')) || 0; };
        tab.append(nome, z, el('button', { type: 'button', texto: '×', onclick: () => { lista.splice(i, 1); desenhar(); } }));
      });
    };
    desenhar();
    corpo.append(el('div', { class: 'explica', texto: 'Os níveis valem para o CAD (os campos de nível das ferramentas) e para o 3D (as linhas de nível). ±0,00 é a boca do cálice no pré-moldado.' }), tab,
      el('button', { type: 'button', texto: '+ nível', style: 'margin-top:6px', onclick: () => { lista.push({ nome: 'Nível', z: 0 }); desenhar(); } }));
    const r = await this.dialogo({ titulo: 'Níveis do projeto', corpo, ok: 'Gravar' });
    if (r !== 'ok') return;
    // nomes repetidos (todos "Nível"): as ferramentas guardam o nível pelo nome, e o 3D os juntava numa placa só — o
    // repetido ganha a cota no nome (Nível +5,00)
    const vistos = new Set(), cota = (z) => (z >= 0 ? '+' : '−') + (Math.abs(z) / 1000).toFixed(2).replace('.', ',');
    let renomeados = 0;
    for (const n of lista.filter(n => n.nome)) {
      if (vistos.has(n.nome)) { n.nome = `${n.nome} ${cota(n.z)}`; renomeados++; }
      vistos.add(n.nome);
    }
    try {
      await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/niveis`, { niveis: lista.filter(n => n.nome).map(({ _antes, ...n }) => n) });
      this._niveisProjeto = null;
      // os elementos vinculados: o nome trocado vai junto; depois grava e o 3D é refeito (a cota nova chega a eles)
      const trocas = new Map(lista.filter(n => n._antes && n.nome && n._antes !== n.nome).map(n => [n._antes, n.nome]));
      const mud = {};
      for (const e of this.doc.entidades.values()) {
        const ea = e.atributos || {};
        if (!ea.elemento) continue;
        const novo = {};
        for (const k of ['nivel_base', 'nivel_topo', 'nivel_fim']) if (typeof ea[k] === 'string' && trocas.has(ea[k])) novo[k] = trocas.get(ea[k]);
        if (Object.keys(novo).length) mud[e.id] = { atributos: { ...ea, ...novo } };
      }
      if (Object.keys(mud).length) this.executar(new ComandoAlterar(mud, 'Nome do nível'));
      await this.niveisDoProjeto();
      await this.salvar({ avisar: false });
      this._sincronizar3D(true);
      this._agendarPaineis('props');
      this.aviso(`${lista.length} nível(is) gravado(s) no projeto.` + (renomeados ? ` ${renomeados} com o nome repetido ganharam a cota no nome (dê nomes como Base, Topo dos pilares, Beiral…).` : ''), 'info', renomeados ? 10000 : 4000);
      if (window.parent !== window) { try { window.parent.postMessage({ metalica: 'referencia-mudou', origem: '2d' }, location.origin); } catch { /* */ } }
    } catch (e) { this.aviso(`Não foi possível gravar os níveis: ${e.message}`, 'erro', 0); }
  }

  /** a tela do galpão pré-moldado (dados, cálculo, saídas), fora da área de trabalho */
  configuracaoPreMoldado() {
    if (!this.projeto) return;
    const url = `/premoldado?projeto=${encodeURIComponent(this.projeto)}`;
    try { (window.top || window).location.href = url; } catch { location.href = url; }
  }

  // ---- a volta: o que mudou no 3D vem para a planta (R5)
  async atualizarPlantaPelo3D() {
    if (!this.projeto) { this.aviso('Atualizar pelo 3D precisa de um projeto aberto.', 'atencao'); return; }
    await this.salvar({ avisar: false });
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/estrutura/do3d`, { desenho: this.nomeDesenho || '' });
    } catch (e) { this.aviso(`Não foi possível ler o 3D: ${e.message}`, 'erro', 0); return; }
    if (r.desenho) this.carregar(r.desenho, { enquadrar: false });
    const alt = r.alteracoes || [];
    this.aviso(alt.length ? `Planta atualizada pelo 3D: ${alt.join('; ')}.` : 'Nada mudou no 3D em relação a esta planta.', alt.length ? 'info' : 'atencao', alt.length ? 0 : 6000);
    if ((r.sem_peca || []).length) this.aviso(`Sem peça no 3D (apagadas lá? ficam na planta): ${r.sem_peca.join(', ')}.`, 'atencao', 0);
  }

  // ---- gerar o 3D da planta
  async gerar3DDaPlanta() {
    if (!this.projeto) { this.aviso('Gerar o 3D precisa de um projeto aberto.', 'atencao'); return; }
    const n = this.elementosDaPlanta().length;
    if (!n) {
      // a planta vazia: as peças que vieram dela saem do 3D (a planta apagada antes da ligação, 06/10)
      await this.salvar({ avisar: false });
      const r = await this._sincronizar3D(true);
      this.aviso(r && r.mudou ? `A planta não tem elementos: ${r.saiu} peça(s) que vieram dela saíram do 3D.` : 'Nenhum elemento lançado neste desenho: use Estrutura → Pilar, Viga, Fundação, Consolo.', 'atencao', 8000);
      return;
    }
    await this.salvar({ avisar: false });
    let r;
    try {
      // a obra pré-moldada (dev) confere o encaixe da cobertura de outra obra: a rota dela; a Metálica, a do projeto
      r = this._obraPreMoldada
        ? await pedir('/api/premoldado/planta/3d', { projeto: this.projeto, desenho: this.nomeDesenho || '' })
        : await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/estrutura/3d`, { desenho: this.nomeDesenho || '' });
    } catch (e) { this.aviso(`Não foi possível gerar o 3D: ${e.message}`, 'erro', 0); return; }
    for (const a of r.avisos || []) this.aviso(a, 'atencao', 0);
    await this._sairPara(r.url);
  }
}
