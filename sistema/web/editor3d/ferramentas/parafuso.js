// Parafuso: coloca um parafuso numa ligação que o projeto não detalhou.
//
// Clique numa face (a mesa do banzo, a aba do perfil de fechamento): o parafuso fica
// perpendicular a ela, com a cabeça do lado de fora e o corpo atravessando a ligação, e a
// porca na ponta. O parafuso a lançar (diâmetro, comprimento, classe) fica no painel de
// propriedades enquanto a ferramenta está ativa — com os tamanhos que o modelo já usa a um
// clique —, e também dá para digitar ("M16x40", "16x40", ou só o diâmetro, "16").
//
// Eixos da face: passando o mouse numa face, aparecem a linha de centro dela ao longo da
// peça e a linha de centro atravessada, e o ponto prende nelas; o rótulo diz a distância
// do parafuso às bordas da face e às pontas da peça — é o que se confere no gabarito.
//
// O parafuso sai como os do IFC — sólido na camada Parafusos com o nome "BOLT (A325) 12x35"
// e tipo IfcMechanicalFastener —, então entra na contagem dos conjuntos, nos furos das
// chapas que ele atravessa e na lista de materiais (com a classe).

import { Ferramenta } from './base.js';
import * as C from './_comum.js';

//: Medida entre faces da cabeça sextavada (ISO 4017/4032) por diâmetro nominal, mm.
const ENTRE_FACES = { 8: 13, 10: 16, 12: 18, 14: 21, 16: 24, 18: 27, 20: 30, 22: 34, 24: 36 };
const DIAMETROS = [8, 10, 12, 14, 16, 18, 20, 22, 24];
const CLASSES = ['A307', 'A325', 'A490', '8.8', '5.8'];

/** Prisma de n lados em volta do eixo `a` (unitário), da base `c` até c + a·h. */
function prisma(c, a, raio, n, h, giro = 0) {
  const u = C.normalizar(C.perpendicular(a));
  const v = C.cross(a, u);
  const base = [], topo = [];
  for (let i = 0; i < n; i++) {
    const t = giro + (2 * Math.PI * i) / n;
    const d = C.add(C.mul(u, raio * Math.cos(t)), C.mul(v, raio * Math.sin(t)));
    base.push(C.add(c, d));
    topo.push(C.add(C.add(c, d), C.mul(a, h)));
  }
  const vertices = [...base, ...topo];
  const faces = [base.map((_, i) => n - 1 - i), topo.map((_, i) => n + i)];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    faces.push([i, j, n + j, n + i]);
  }
  return { vertices, faces };
}

/** Número sem unidade: 12, 12.5 (vai no nome "BOLT (A325) 12x35"). */
const num = (x) => String(Math.round(x * 10) / 10);
const mm = (x) => String(Math.round(x));

function juntar(...partes) {
  const vertices = [], faces = [];
  for (const p of partes) {
    const k = vertices.length;
    vertices.push(...p.vertices);
    for (const f of p.faces) faces.push(f.map(i => i + k));
  }
  return { vertices, faces };
}

/** Lê "M16x40", "16x40", "16 x 40" ou "16" → {d, L}. */
function lerTamanho(texto, atual) {
  const t = String(texto || '').toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M?(\d+(?:\.\d+)?)[X×*](\d+(?:\.\d+)?)$/);
  if (m) return { d: +m[1], L: +m[2] };
  m = t.match(/^M?(\d+(?:\.\d+)?)$/);
  if (m) return { d: +m[1], L: atual.L };
  return null;
}

/** "BOLT (A325) 16x50" → {d: 16, L: 50, classe: 'A325'}; "BOLT (A) 12x35" → classe ''. */
export function lerNomeDoParafuso(nome) {
  const m = String(nome || '').match(/^BOLT\s*\(([^)]*)\)\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)/);
  if (!m) return null;
  const d = +m[2].replace(',', '.'), L = +m[3].replace(',', '.');
  if (!(d > 0) || !(L > 0)) return null;
  const c = m[1].trim();
  return { d, L, classe: c.length > 1 ? c : '' };
}

//: entre faces da porca → rosca (a mesma tabela do detalhamento, nucleo2d/detalhe/base._PORCAS)
const PORCAS = [[10, 6], [13, 8], [16, 10], [18, 12], [19, 12], [21, 14], [24, 16], [27, 18], [30, 20], [34, 22], [36, 24]];

/** Autovetores da covariância dos pontos (Jacobi 3×3): os eixos principais da peça. */
function eixosPrincipais(pts) {
  const n = pts.length;
  const m = [0, 1, 2].map(i => pts.reduce((s, q) => s + q[i], 0) / n);
  const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const q of pts) for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) A[i][j] += (q[i] - m[i]) * (q[j] - m[j]);
  const V = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let it = 0; it < 30; it++) {
    let p = 0, r = 1, maior = 0;
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) if (Math.abs(A[i][j]) > maior) { maior = Math.abs(A[i][j]); p = i; r = j; }
    if (maior < 1e-9) break;
    const th = 0.5 * Math.atan2(2 * A[p][r], A[r][r] - A[p][p]);
    const c = Math.cos(th), sn = Math.sin(th);
    for (let k = 0; k < 3; k++) {                      // A ← Jᵀ A J
      const akp = A[k][p], akr = A[k][r];
      A[k][p] = c * akp - sn * akr; A[k][r] = sn * akp + c * akr;
    }
    for (let k = 0; k < 3; k++) {
      const apk = A[p][k], ark = A[r][k];
      A[p][k] = c * apk - sn * ark; A[r][k] = sn * apk + c * ark;
    }
    for (let k = 0; k < 3; k++) {
      const vkp = V[k][p], vkr = V[k][r];
      V[k][p] = c * vkp - sn * vkr; V[k][r] = sn * vkp + c * vkr;
    }
  }
  return [0, 1, 2].map(j => [V[0][j], V[1][j], V[2][j]]);
}

/**
 * Tamanho do fixador do modelo: pelo nome ("BOLT (A) 12x35") ou, sem tamanho no nome
 * ("BOLT () 0x0", a porca do chumbador ou da barra roscada no IFC do TecnoMETAL), pela
 * peça — a medida do meio da caixa é a entre faces da porca, que dá a rosca. Arruela
 * (chata) devolve null.
 */
export function tamanhoDoFixador(ent) {
  const t = lerNomeDoParafuso(ent && ent.nome);
  if (t) return t;
  if (!ent || !/^BOLT/i.test(ent.nome || '') || !(ent.vertices && ent.vertices.length >= 4)) return null;
  // extensões nos eixos principais da peça (a porca vem girada: a caixa do mundo engana)
  const ext = eixosPrincipais(ent.vertices).map(ax => {
    const v = ent.vertices.map(q => C.dot(q, ax));
    return Math.max(...v) - Math.min(...v);
  }).sort((a, b) => a - b);
  if (ext[0] < 0.25 * ext[2]) return null;                  // arruela
  const af = ext[1];
  let d = 0;
  for (const [entre, rosca] of PORCAS) if (af >= entre - 0.6) d = rosca;
  return d ? { d, L: 0, classe: '', semTamanho: true } : null;
}

export class FerramentaParafuso extends Ferramenta {
  static id = 'parafuso';
  static nome = 'Parafuso';
  static atalho = 'U';
  static grupo = 'estrutura';
  static dica = 'Clique na face onde entra o parafuso · o parafuso a lançar está no painel de propriedades';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M8 3h8l2 3-2 3H8L6 6Z"/><path d="M10 9v11M14 9v11M10 12h4M10 15h4M10 18h4"/></svg>`;
  //: o último escolhido vale para a próxima vez que a ferramenta abrir
  static tamanho = null;
  static eixos = true;

  ativar() {
    this._caixas = new Map();
    this.tamanho = { d: 12, L: 35, classe: 'A325', ...(this.constructor.tamanho || {}) };
    // parafuso selecionado ao abrir a ferramenta: lança igual a ele
    const sel = (this.selecao && this.selecao.entidades) || [];
    const modelo = sel.map(e => tamanhoDoFixador(e)).find(Boolean);
    if (modelo) this._definir({ d: modelo.d, L: modelo.L || this.tamanho.L, classe: modelo.classe || this.tamanho.classe });
    this._atualizarDica();
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  get nomeAtual() {
    const { d, L, classe } = this.tamanho;
    return `BOLT (${classe || 'A'}) ${num(d)}x${num(L)}`;
  }

  get rotuloAtual() {
    const { d, L, classe } = this.tamanho;
    return `M${num(d)}x${num(L)}${classe ? ' ' + classe : ''}`;
  }

  _atualizarDica() {
    this.dica(`Parafuso ${this.rotuloAtual}: clique na face onde ele entra (o tamanho e a classe estão no painel de propriedades)`);
    this.medida(this.rotuloAtual);
  }

  _definir(t) {
    this.tamanho = { ...this.tamanho, ...t };
    this.constructor.tamanho = { ...this.tamanho };
    this._atualizarDica();
  }

  onValor(texto) {
    const t = lerTamanho(texto, this.tamanho);
    if (!t || !(t.d > 0) || !(t.L > 0)) { this.dica('Tamanho: M12x35, 16x40 ou só o diâmetro (16)'); return true; }
    this._definir(t);
    if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
    return true;
  }

  /** Tamanhos que o modelo já usa, do mais comum para o menos: {rotulo, t, n}. */
  _usadosNoModelo() {
    const cont = new Map();
    const ents = this.documento && this.documento.entidades;
    if (!ents) return [];
    for (const e of ents.values()) {
      if (e.tipo !== 'solido' || !/^BOLT/.test(e.nome || '')) continue;
      const t = tamanhoDoFixador(e);
      if (!t) continue;
      // sem tamanho no IFC: vale a rosca medida na porca; o comprimento é o da ferramenta
      const k = t.semTamanho ? `M${num(t.d)} porca/chumbador` : `M${num(t.d)}x${num(t.L)}${t.classe ? ' ' + t.classe : ''}`;
      const r = cont.get(k) || { rotulo: k, t, n: 0 };
      r.n++;
      cont.set(k, r);
    }
    return [...cont.values()].sort((a, b) => b.n - a.n).slice(0, 14);
  }

  /** Opções no painel de propriedades (chamado pelo editor). */
  painel(raiz, el) {
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Parafuso a lançar' }),
                   el('span', { texto: this.rotuloAtual })));
    const g = el('div', { class: 'campos' });
    const selD = el('select', { title: 'Diâmetro nominal (rosca)' });
    for (const d of DIAMETROS) selD.append(el('option', { value: String(d), texto: `M${d}` }));
    if (!DIAMETROS.includes(this.tamanho.d)) selD.append(el('option', { value: String(this.tamanho.d), texto: `M${num(this.tamanho.d)}` }));
    selD.value = String(this.tamanho.d);
    selD.addEventListener('change', () => this._definir({ d: +selD.value }));
    const inL = el('input', { type: 'number', min: '10', step: '5', value: String(this.tamanho.L), title: 'Comprimento do parafuso (sem a cabeça), mm' });
    inL.addEventListener('change', () => { const L = +inL.value; if (L > 0) this._definir({ L }); });
    const selC = el('select', { title: 'Classe do parafuso — vai para o nome e para a lista de materiais' });
    for (const c of CLASSES) selC.append(el('option', { value: c, texto: c }));
    selC.value = this.tamanho.classe || 'A325';
    selC.addEventListener('change', () => this._definir({ classe: selC.value }));
    const eixos = el('input', { type: 'checkbox', title: 'Linhas de centro da face sob o cursor; o parafuso prende nelas e mostra a distância às bordas' });
    eixos.checked = !!this.constructor.eixos;
    eixos.addEventListener('change', () => { this.constructor.eixos = eixos.checked; this.limparPrevia(); });
    g.append(el('label', { texto: 'Diâmetro' }), selD,
             el('label', { texto: 'Comprimento (mm)' }), inL,
             el('label', { texto: 'Classe' }), selC,
             el('label', { texto: 'Eixos da face' }), el('span', {}, eixos, ' mostrar e prender'));
    raiz.append(g);
    const usados = this._usadosNoModelo();
    if (usados.length) {
      const box = el('div', { class: 'acoes' });
      for (const u of usados) {
        const dica = u.t.semTamanho
          ? 'Fixador que veio do IFC sem tamanho no nome ("BOLT () 0x0" — porca de chumbador ou de barra roscada): a rosca é medida na porca; o comprimento fica o do campo acima'
          : 'Lançar este, como os que já estão no modelo';
        box.append(el('button', { type: 'button', texto: `${u.rotulo} (${u.n})`, title: dica,
          onclick: () => { this._definir({ d: u.t.d, L: u.t.L || this.tamanho.L, classe: u.t.classe || this.tamanho.classe }); this.editor._agendarPaineis('props'); } }));
      }
      raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Já usados no modelo' }), box));
    }
  }

  /** Geometria do parafuso com a cabeça sobre `ponto`, corpo entrando contra `normal`. */
  geometria(ponto, normal) {
    const { d, L } = this.tamanho;
    const s = ENTRE_FACES[Math.round(d)] || 1.5 * d;
    const rHex = s / Math.sqrt(3);                   // raio do sextavado pelos cantos
    const k = 0.65 * d, m = 0.85 * d;
    const n = C.normalizar(normal);
    const dentro = C.mul(n, -1);
    const cabeca = prisma(ponto, n, rHex, 6, k);
    const corpo = prisma(ponto, dentro, d / 2, 12, L);
    const porca = prisma(C.add(ponto, C.mul(dentro, Math.max(L - m - 2, m))), dentro, rHex, 6, m);
    return juntar(cabeca, corpo, porca);
  }

  normalDoPonto(p) {
    const ent = p.entidade && this.documento && this.documento.get(p.entidade);
    if (ent && ent.tipo === 'chapa') {
      const n = C.normalizar(C.cross(ent.eixo_x, ent.eixo_y));
      return p.normal && C.dot(p.normal, n) < 0 ? C.mul(n, -1) : n;
    }
    return p.normal && C.comp(p.normal) > 0.5 ? C.normalizar(p.normal) : null;
  }

  /**
   * Eixos da face em `p` (normal `n`): direção da peça no plano da face (e1), a
   * atravessada (e2) e a extensão da face nas duas. Os vértices da peça que estão no plano
   * da face dão a extensão; a chapa paramétrica, pelo contorno projetado.
   */
  eixosDaFace(p, n) {
    const ent = p.entidade && this.documento && this.documento.get(p.entidade);
    if (!ent) return null;
    let pts = C.pontosDaEntidade(ent);
    if (pts.length < 2) return null;
    const plano = (q) => C.dot(C.sub(q, p.ponto), n);
    let noPlano = pts.filter(q => Math.abs(plano(q)) < 0.8);
    if (noPlano.length < 3) noPlano = pts.map(q => C.sub(q, C.mul(n, plano(q))));
    // direção da peça: a maior extensão dos vértices, levada para o plano da face
    let e1 = null;
    if (ent.tipo === 'barra') e1 = C.sub(ent.fim, ent.inicio);
    else if (ent.tipo === 'chapa') e1 = ent.eixo_x;
    else {
      let melhor = 0;
      for (const d of [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) {
        const v = pts.map(q => C.dot(q, d));
        const ext = Math.max(...v) - Math.min(...v);
        if (ext > melhor) { melhor = ext; e1 = d; }
      }
      // peça inclinada (banzo): a aresta mais comprida das faces que estão no plano da face
      // (o lado comprido da mesa; a diagonal entre vértices não serve)
      const vs = ent.vertices || [];
      let dm = 0;
      for (const f of ent.faces || []) {
        if (!f.every(i => vs[i] && Math.abs(plano(vs[i])) < 0.8)) continue;
        for (let k = 0; k < f.length; k++) {
          const q = vs[f[k]], r = vs[f[(k + 1) % f.length]];
          const dd = C.dist(q, r);
          if (dd > dm) { dm = dd; e1 = C.sub(r, q); }
        }
      }
    }
    e1 = C.sub(e1, C.mul(n, C.dot(e1, n)));
    if (C.comp(e1) < 1e-6) e1 = C.perpendicular(n);
    e1 = C.normalizar(e1);
    const e2 = C.normalizar(C.cross(n, e1));
    const s1 = noPlano.map(q => C.dot(q, e1)), s2 = noPlano.map(q => C.dot(q, e2));
    return { e1, e2, min1: Math.min(...s1), max1: Math.max(...s1), min2: Math.min(...s2), max2: Math.max(...s2) };
  }

  /** Caixa envolvente da peça (guardada: o mouse passa muitas vezes pelas mesmas). */
  _caixaDe(ent) {
    this._caixas = this._caixas || new Map();
    let c = this._caixas.get(ent.id);
    if (c) return c;
    const pts = C.pontosDaEntidade(ent);
    if (!pts.length) return null;
    const lo = [0, 1, 2].map(i => Math.min(...pts.map(q => q[i])));
    const hi = [0, 1, 2].map(i => Math.max(...pts.map(q => q[i])));
    // a barra paramétrica só tem as duas pontas: a seção entra como folga
    const folga = ent.tipo === 'barra' ? 150 : (ent.tipo === 'chapa' ? (ent.espessura || 10) : 1);
    c = [lo.map(v => v - folga), hi.map(v => v + folga)];
    this._caixas.set(ent.id, c);
    return c;
  }

  /**
   * As peças que o parafuso atravessa abaixo da face (o banzo ou a chapa embaixo da
   * terça), da mais perto para a mais longe: o segmento do corpo do parafuso cruza a caixa
   * delas. Parafusos, porcas e telhas ficam de fora.
   */
  _atravessadas(ponto, n, idAlvo) {
    const ents = this.documento && this.documento.entidades;
    if (!ents) return [];
    const L = this.tamanho.L + 30;
    const fim = C.add(ponto, C.mul(n, -L));
    const lo = [0, 1, 2].map(i => Math.min(ponto[i], fim[i]));
    const hi = [0, 1, 2].map(i => Math.max(ponto[i], fim[i]));
    const achadas = [];
    for (const e of ents.values()) {
      if (e.id === idAlvo || e.visivel === false) continue;
      if (/^BOLT|PORCA|ARRUELA|TELHA/i.test(e.nome || '') || e.camada === 'Parafusos' || e.camada === 'Telhas') continue;
      const c0 = this._caixaDe(e);
      if (!c0) continue;
      // folga de 80 mm para os lados: o banzo aparece mesmo com o parafuso fora dele (é
      // quando mais importa ver onde está o eixo)
      const c = [c0[0].map(v => v - 80), c0[1].map(v => v + 80)];
      if ([0, 1, 2].some(i => c[1][i] < lo[i] || c[0][i] > hi[i])) continue;
      // o segmento cruza a caixa (slab)?
      let t0 = 0, t1 = L, d = C.mul(n, -1);
      let fora = false;
      for (let i = 0; i < 3 && !fora; i++) {
        if (Math.abs(d[i]) < 1e-9) { if (ponto[i] < c[0][i] || ponto[i] > c[1][i]) fora = true; continue; }
        let ta = (c[0][i] - ponto[i]) / d[i], tb = (c[1][i] - ponto[i]) / d[i];
        if (ta > tb) [ta, tb] = [tb, ta];
        t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
        if (t0 > t1) fora = true;
      }
      if (!fora) achadas.push({ e, t: t0 });
    }
    return achadas.sort((a, b) => a.t - b.t).slice(0, 2).map(x => x.e);
  }

  /**
   * Eixo da peça de baixo no plano da face: direção dela levada ao plano e o centro da
   * largura dela ali perto do parafuso (só os vértices a menos de 400 mm, para a seção
   * local de uma peça comprida ou inclinada). Devolve {d, q, larg, min, max} em que q é a
   * coordenada do eixo ao longo da atravessada f = n × d.
   */
  _eixoDaPeca(ent, ponto, n) {
    let pts = C.pontosDaEntidade(ent);
    if (pts.length < 2) return null;
    let d;
    if (ent.tipo === 'barra') d = C.sub(ent.fim, ent.inicio);
    else if (ent.tipo === 'chapa') d = ent.eixo_x;
    else {
      const vs = ent.vertices || [];
      let dm = 0;
      for (const f of ent.faces || []) for (let k = 0; k < f.length; k++) {
        const q = vs[f[k]], r = vs[f[(k + 1) % f.length]];
        if (!q || !r) continue;
        const dd = C.dist(q, r);
        if (dd > dm) { dm = dd; d = C.sub(r, q); }
      }
    }
    if (!d) return null;
    d = C.sub(d, C.mul(n, C.dot(d, n)));
    if (C.comp(d) < 1e-6) return null;
    d = C.normalizar(d);
    const f = C.normalizar(C.cross(n, d));
    const perto = pts.filter(q => Math.abs(C.dot(C.sub(q, ponto), d)) <= 400);
    const usar = perto.length >= 3 ? perto : pts;
    if (ent.tipo === 'barra') {
      const q = C.dot(ent.inicio, f);
      return { d, f, q, min: q - 50, max: q + 50 };
    }
    const vs = usar.map(q => C.dot(q, f));
    const min = Math.min(...vs), max = Math.max(...vs);
    return { d, f, q: (min + max) / 2, min, max };
  }

  /** Ponto ajustado aos eixos da face, com o desenho dos eixos e o rótulo das distâncias. */
  ajustar(p, n) {
    if (!this.constructor.eixos) return { ponto: p.ponto, extra: [] };
    const f = this.eixosDaFace(p, n);
    if (!f) return { ponto: p.ponto, extra: [] };
    const { e1, e2 } = f;
    let a = C.dot(p.ponto, e1), b = C.dot(p.ponto, e2);
    const c1 = (f.min1 + f.max1) / 2, c2 = (f.min2 + f.max2) / 2;
    const larg = f.max2 - f.min2;
    const tol2 = Math.min(25, Math.max(3, 0.12 * larg));
    const tol1 = Math.min(40, Math.max(5, 0.03 * (f.max1 - f.min1)));
    let presoC2 = false, presoC1 = false;
    if (Math.abs(b - c2) <= tol2) { b = c2; presoC2 = true; }
    if (Math.abs(a - c1) <= tol1) { a = c1; presoC1 = true; }
    let ponto = C.add(p.ponto, C.add(C.mul(e1, a - C.dot(p.ponto, e1)), C.mul(e2, b - C.dot(p.ponto, e2))));
    // a peça de baixo (o banzo sob a terça): o eixo dela também prende o parafuso; com os
    // dois eixos presos, o parafuso vai para o cruzamento deles
    const baixo = [];
    for (const e of this._atravessadas(ponto, n, p.entidade)) {
      const ax = this._eixoDaPeca(e, ponto, n);
      if (!ax) continue;
      const larg_b = ax.max - ax.min;
      const tol = Math.min(25, Math.max(3, 0.12 * larg_b));
      const dist_ = C.dot(ponto, ax.f) - ax.q;
      let preso = false;
      if (Math.abs(dist_) <= tol) {
        // anda na direção atravessada ao eixo de baixo; se o eixo da face estava preso e as
        // duas linhas não são paralelas, fica no cruzamento (anda ao longo do eixo da face)
        if (presoC2 && Math.abs(C.dot(ax.f, e1)) > 0.2) ponto = C.add(ponto, C.mul(e1, -dist_ / C.dot(ax.f, e1)));
        else ponto = C.add(ponto, C.mul(ax.f, -dist_));
        preso = true;
      }
      baixo.push({ e, ax, preso });
      if (baixo.length >= 1) break;              // o primeiro de baixo basta (o banzo)
    }
    a = C.dot(ponto, e1); b = C.dot(ponto, e2);
    const em = (s1, s2) => C.add(ponto, C.add(C.mul(e1, s1 - a), C.mul(e2, s2 - b)));
    const folga = Math.max(20, 0.1 * larg);
    const extra = [
      // linha de centro ao longo da peça e a atravessada no centro da face
      C.gLinha([em(f.min1 - folga, c2), em(f.max1 + folga, c2)], presoC2 ? '#0a8f3c' : '#2a63c8', { tracejada: true }),
      C.gLinha([em(c1, f.min2 - folga), em(c1, f.max2 + folga)], presoC1 ? '#0a8f3c' : '#2a63c8', { tracejada: true }),
      // a atravessada que passa pelo parafuso
      C.gLinha([em(a, f.min2), em(a, f.max2)], '#8a94a6'),
    ];
    const txt = `face: bordas ${mm(b - f.min2)} | ${mm(f.max2 - b)} · pontas ${mm(a - f.min1)} | ${mm(f.max1 - a)} mm`
      + (presoC2 ? ' · no eixo' : '');
    extra.push(C.gRotulo(txt, C.add(ponto, C.add(C.mul(n, 60), C.mul(e2, -0.5 * larg - 40))), '#0b3d91'));
    for (const { e, ax, preso } of baixo) {
      // o eixo da peça de baixo, levado ao plano da face, perto do parafuso
      const s = C.dot(ponto, ax.f) - ax.q;
      const base = C.add(ponto, C.mul(ax.f, -s));
      const meia = Math.max(150, 2 * (ax.max - ax.min));
      extra.push(C.gLinha([C.add(base, C.mul(ax.d, -meia)), C.add(base, C.mul(ax.d, meia))],
                          preso ? '#0a8f3c' : '#b8860b', { tracejada: true }));
      const q = C.dot(ponto, ax.f);
      const nomeB = (e.atributos && e.atributos.marcas && (e.atributos.marcas.nome || e.atributos.marcas.posicao)) || e.nome || 'peça de baixo';
      const t2 = `${nomeB}: ${preso ? 'no eixo' : mm(Math.abs(s)) + ' mm do eixo'} · bordas ${mm(q - ax.min)} | ${mm(ax.max - q)} mm`;
      extra.push(C.gRotulo(t2, C.add(ponto, C.add(C.mul(n, 60), C.mul(ax.f, 0.5 * (ax.max - ax.min) + 60))), '#7a5a00'));
    }
    return { ponto, extra };
  }

  onMover(p) {
    this.limparPrevia();
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const { ponto, extra } = this.ajustar(p, n);
    const g = this.geometria(ponto, n);
    this.previa(C.grupo(C.gMalha(g.vertices, g.faces, '#d62728', 0.55),
                        C.gRotulo(this.rotuloAtual, C.add(ponto, C.mul(n, 30))), ...extra));
  }

  onPonto(p) {
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const { ponto } = this.ajustar(p, n);
    const g = this.geometria(ponto, n);
    const { d, L, classe } = this.tamanho;
    const alvo = this.documento.get(p.entidade);
    const marcas = (alvo && alvo.atributos && alvo.atributos.marcas) || {};
    const nome = this.nomeAtual;
    const ent = {
      tipo: 'solido', id: C.novoId('paraf'), nome, camada: 'Parafusos', material: 'Cor #ff0000',
      visivel: true, bloqueada: false, grupo: '',
      vertices: g.vertices, faces: g.faces, arestas_vivas: [],
      atributos: {
        tipo_ifc: 'IfcMechanicalFastener',
        marcas: { perfil: nome, ...(marcas.conjunto ? { conjunto: marcas.conjunto } : {}) },
        criado_no_editor: true,
        parafuso: { d, L, classe: classe || '', ponto: C.copiar(ponto), eixo: C.mul(n, -1) },
      },
    };
    this.executar(C.cmdAdicionar(ent, 'Parafuso'));
    this.dica(`${this.rotuloAtual} colocado · clique no próximo, ou troque o parafuso no painel (Esc sai)`);
  }

  cancelar() { this.limparPrevia(); C.voltarParaSelecao(this.editor); }
}

export default FerramentaParafuso;
