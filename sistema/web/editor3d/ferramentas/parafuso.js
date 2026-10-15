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
import { furosDoParafuso, cruzamentosDoEixo, lacoDaForma, refazerFurosEditor, IndiceDeCaixas, pacoteDoEixo,
         comprimentoPelaPega, paredesNoEixo } from './_furar.js';
import { baseDaBarra } from '../nucleo/documento.js';

/** Interseções da reta (x + s·dx, y + s·dy) com um polígono fechado: os valores de s. */
function cortesDaReta(x, y, dx, dy, pts) {
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length];
    const ex = bx - ax, ey = by - ay;
    const den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-12) continue;
    const s = ((ax - x) * ey - (ay - y) * ex) / den;
    const r = ((ax - x) * dy - (ay - y) * dx) / den;
    if (r >= -1e-9 && r < 1 - 1e-9) out.push(s);
  }
  return out;
}

/** O marcador de furo (o tubo escuro da camada Furos, que o detalhamento lê como furo): entra em `ponto` na
 *  direção `d` e atravessa a parede de `prof` mm — o mesmo da ferramenta Furo na barra paramétrica. */
function marcadorDeFuro(ponto, d, prof, forma) {
  const nn = C.mul(C.normalizar(d), -1);
  const u = C.normalizar(C.perpendicular(nn));
  const v = C.normalizar(C.cross(nn, u));
  const laco = lacoDaForma(forma);
  const topo = C.add(ponto, C.mul(nn, 0.3)), h = prof + 0.6;
  const base = laco.map(([x, y]) => C.add(topo, C.add(C.mul(u, x), C.mul(v, y))));
  const fundo = base.map(q => C.add(q, C.mul(nn, -h)));
  const m = laco.length;
  const faces = [base.map((_, i) => i), fundo.map((_, i) => 2 * m - 1 - i)];
  for (let i = 0; i < m; i++) { const j = (i + 1) % m; faces.push([i, m + i, m + j, j]); }
  return { vertices: [...base, ...fundo], faces };
}

//: Medida entre faces da cabeça sextavada (ISO 4017/4032) por diâmetro nominal, mm.
const ENTRE_FACES = { 8: 13, 10: 16, 12: 18, 14: 21, 16: 24, 18: 27, 20: 30, 22: 34, 24: 36 };
export const DIAMETROS = [8, 10, 12, 14, 16, 18, 20, 22, 24];
export const CLASSES = ['A307', 'A325', 'A490', '8.8', '5.8'];

/** Prisma de n lados em volta do eixo `a` (unitário), da base `c` até c + a·h. */
export function prisma(c, a, raio, n, h, giro = 0) {
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

/** Nome do parafuso como o IFC grava: "BOLT (A325) 12x35" (sem classe: "BOLT (A) …"). */
export function nomeDoParafuso(classe, d, L) {
  return `BOLT (${classe || 'A'}) ${num(d)}x${num(L)}`;
}

/** Diâmetro do furo-padrão do parafuso, pela NBR 8800 (o mesmo de fabrica.furo_padrao_mm): d + 1,5 mm até 24 mm e
 *  d + 2 acima (M12 → 13,5, M16 → 17,5, 1" → 27,4). Até 11/10/2026 era d + 1 (auditoria D4). */
export function furoDoParafuso(d) { return Math.round((d + (d <= 24 + 1e-6 ? 1.5 : 2)) * 100) / 100; }

/**
 * Geometria do parafuso: cabeça sextavada do lado de fora de `ponto` (o apoio dela na
 * peça), corpo de comprimento L entrando contra `normal` e a porca — na pega `pega` (a
 * distância do apoio da cabeça à arruela, a espessura do pacote) quando se sabe, senão
 * perto da ponta.
 */
export function geometriaDoParafuso(d, L, ponto, normal, pega = null) {
  const s = ENTRE_FACES[Math.round(d)] || 1.5 * d;
  const rHex = s / Math.sqrt(3);                   // raio do sextavado pelos cantos
  const k = 0.65 * d, m = 0.85 * d;
  const n = C.normalizar(normal);
  const dentro = C.mul(n, -1);
  const cabeca = prisma(ponto, n, rHex, 6, k);
  const corpo = prisma(ponto, dentro, d / 2, 12, L);
  const onde = pega && pega > 0 && pega + m <= L ? pega : Math.max(L - m - 2, m);
  const porca = prisma(C.add(ponto, C.mul(dentro, onde)), dentro, rHex, 6, m);
  return juntar(cabeca, corpo, porca);
}

/**
 * Onde o parafuso está: {ponto, eixo, pega} — o apoio da cabeça, a direção da cabeça para
 * a ponta e a pega. O posto pelo editor guarda isso em `atributos.parafuso`; o do IFC é lido
 * da malha: o eixo é o maior eixo principal, a cabeça é a ponta de raio grande (a outra
 * ponta é o corpo, fino), o apoio é o nível logo depois da cabeça e a pega vai até o
 * próximo nível largo (a arruela ou a porca).
 */
export function quadroDoParafuso(ent) {
  const reg = ent && ent.atributos && ent.atributos.parafuso;
  if (reg && reg.ponto && reg.eixo) return { ponto: reg.ponto.slice(), eixo: C.normalizar(reg.eixo), pega: reg.pega || null };
  const vs = (ent && ent.vertices) || [];
  if (vs.length < 8) return null;
  const c = [0, 1, 2].map(i => vs.reduce((s, q) => s + q[i], 0) / vs.length);
  const eixos = eixosPrincipais(vs);
  let ax = eixos[0], maior = -1;
  for (const e of eixos) {
    const t = vs.map(q => C.dot(C.sub(q, c), e));
    const ext = Math.max(...t) - Math.min(...t);
    if (ext > maior) { maior = ext; ax = e; }
  }
  // níveis ao longo do eixo (1 mm), com o maior raio de cada um
  const niveis = new Map();
  for (const q of vs) {
    const rel = C.sub(q, c);
    const t = C.dot(rel, ax);
    const r = C.comp(C.sub(rel, C.mul(ax, t)));
    const k = Math.round(t);
    let achou = null;
    for (const kk of niveis.keys()) if (Math.abs(kk - k) <= 1) { achou = kk; break; }
    const chave = achou === null ? k : achou;
    niveis.set(chave, Math.max(niveis.get(chave) || 0, r));
  }
  let lista = [...niveis.entries()].sort((a, b) => a[0] - b[0]);
  if (lista.length < 3) return null;
  // cabeça: a ponta com o raio maior
  let dir = ax;
  if (lista[0][1] > lista[lista.length - 1][1]) {
    // a cabeça está em t mínimo: o eixo vai de t mínimo para t máximo (já é `ax`)
  } else {
    dir = C.mul(ax, -1);
    lista = lista.map(([t, r]) => [-t, r]).sort((a, b) => a[0] - b[0]);
  }
  const rCorpo = Math.min(...lista.map(([, r]) => r));
  const tApoio = lista[1][0];
  let pega = null;
  for (let i = 2; i < lista.length; i++) {
    if (lista[i][1] > rCorpo + 1.0) { pega = lista[i][0] - tApoio; break; }
  }
  return { ponto: C.add(c, C.mul(dir, tApoio)), eixo: dir, pega: pega && pega > 0.5 ? pega : null };
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
export function eixosPrincipais(pts) {
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
  //: o ponto anda de `passo` em `passo` mm a partir da ponta e da borda da face (0 = livre)
  static passo = 5;
  //: comprimento pela pega (o pacote que o parafuso aperta) ou o digitado
  static automatico = true;
  //: vários de uma vez: `colunas` ao longo da peça a cada `p` mm (a partir do clique, para longe da ponta mais perto) e
  //: `linhas` atravessadas no gabarito `g` mm, centradas no clique
  static padrao = { linhas: 1, g: 60, colunas: 1, p: 60 };

  ativar() {
    this._indice = new IndiceDeCaixas(this.documento, { folgaBarra: 300 });
    this.tamanho = { d: 12, L: 35, classe: 'A325', ...(this.constructor.tamanho || {}) };
    // parafuso selecionado ao abrir a ferramenta: lança igual a ele
    const sel = (this.selecao && this.selecao.entidades) || [];
    const modelo = sel.map(e => tamanhoDoFixador(e)).find(Boolean);
    if (modelo) this._definir({ d: modelo.d, L: modelo.L || this.tamanho.L, classe: modelo.classe || this.tamanho.classe });
    this._atualizarDica();
    const n = this._selecionadosParaPega().length;
    if (n) this.dica(`${n} parafuso(s) selecionado(s): "Recalcular pela pega" no painel ajusta o comprimento deles · ou clique numa face para lançar`);
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  /** O "M" de "M16x40" e os números vão para a caixa de medidas (não são atalhos de outra ferramenta). */
  teclaDeValor(k) { return /^[0-9Mm]$/.test(k); }

  /** As peças perto da caixa [lo, hi]: um "documento" só com elas, para as varreduras a cada movimento do mouse. */
  _perto(lo, hi, folga = 0) {
    if (!this._indice) this._indice = new IndiceDeCaixas(this.documento, { folgaBarra: 300 });
    return this._indice.perto(lo, hi, folga);
  }

  /** As peças perto do segmento do eixo, de `ponto` até `alcance` mm na direção `d`. */
  _pertoDoEixo(ponto, d, alcance, folga = 2) {
    const fim = C.add(ponto, C.mul(d, alcance));
    return this._perto([0, 1, 2].map(i => Math.min(ponto[i], fim[i])), [0, 1, 2].map(i => Math.max(ponto[i], fim[i])), folga);
  }

  /** A pega (o pacote apertado) e o comprimento para o parafuso em `ponto`, entrando contra `n`. */
  _tamanhoNoPonto(ponto, n) {
    const d = C.normalizar(C.mul(n, -1));
    const alcance = Math.max(200, this.tamanho.L + 60);
    const pac = pacoteDoEixo(this._pertoDoEixo(ponto, d, alcance), ponto, d, alcance,
                             { cena: this.editor && this.editor.cena, caixaDe: (e) => this._caixaDe(e) });
    const pega = pac && pac.pega > 0 ? pac.pega : null;
    const auto = this.constructor.automatico && pega;
    const L = auto ? comprimentoPelaPega(this.tamanho.d, pega) : this.tamanho.L;
    // curto: a porca não cabe depois do pacote (arruela + porca ≈ 1,15 d)
    const curto = !!pega && L < pega + 1.15 * this.tamanho.d;
    // o eixo corre dentro de uma parede (em cima da alma do I, no meio da mesa): não há como passar o parafuso
    let bate = null;
    if (pac && pac.bloqueio) {
      const e = this.documento.get(pac.bloqueio.id);
      const m = (e && e.atributos && e.atributos.marcas) || {};
      bate = (e && (e.perfil || m.nome || m.posicao || e.nome)) || 'a peça de baixo';
    }
    return { ...this.tamanho, L, pega, auto: !!auto, curto, bate, paredes: pac ? pac.paredes.length : 0 };
  }

  /** Os pontos do padrão (vários de uma vez) em volta do clique, nos eixos da face. */
  _pontosDoPadrao(ponto, f) {
    const pd = this.constructor.padrao || {};
    const nl = Math.max(1, Math.round(pd.linhas || 1)), nc = Math.max(1, Math.round(pd.colunas || 1));
    if (!f || (nl === 1 && nc === 1)) return [ponto];
    const a = C.dot(ponto, f.e1);
    // ao longo: do clique para longe da ponta mais perto (o 1º fica onde se clicou — a 50 mm da ponta, p.ex.)
    const sentido = (a - f.min1) <= (f.max1 - a) ? 1 : -1;
    const out = [];
    const b = C.dot(ponto, f.e2);
    for (let j = 0; j < nc; j++) {
      for (let i = 0; i < nl; i++) {
        // 2 na largura de uma mesa de I: um em cada linha de gabarito (o g do perfil, não o do painel)
        const s1 = sentido * j * (pd.p || 0);
        const s2 = f.gab && nl === 2 ? f.gab.linhas[i] - b : (i - (nl - 1) / 2) * (pd.g || 0);
        out.push(C.add(ponto, C.add(C.mul(f.e1, s1), C.mul(f.e2, s2))));
      }
    }
    return out;
  }

  /**
   * O gabarito da mesa de um perfil I/H (a da face clicada ou a da peça de baixo): varre a largura de `lo` a `hi` (na
   * direção `dir`, a partir de `origem`) e acha onde o eixo do furo correria dentro da alma (parede de mais de 60 mm);
   * com a alma no meio e mesa livre dos dois lados, as linhas de gabarito ficam no meio de cada meia-mesa, simétricas à
   * alma e arredondadas de 5 em 5 mm (o g de 75, 80…). {linhas: [b1, b2], g, wc} nas coordenadas de `dir`, ou null — o
   * U, a cantoneira e a chapa não têm alma no meio (pedido do usuário, 14/10: o parafuso no centro da mesa batia na alma).
   */
  _gabaritoDe(ent, origem, n, dir, lo, hi) {
    if (!ent || hi - lo < 40) return null;
    const chave = [ent.id, ...n.map(v => Math.round(v * 50)), ...dir.map(v => Math.round(v * 50)), Math.round(lo / 5), Math.round(hi / 5),
                   ent.tipo === 'barra' ? '' : Math.round(C.dot(origem, C.normalizar(C.cross(n, dir))) / 500)].join('|');
    this._gabaritos = this._gabaritos || new Map();
    if (this._gabaritos.has(chave)) return this._gabaritos.get(chave);
    const so = { entidades: new Map([[ent.id, ent]]), get: (id) => (id === ent.id ? ent : null) };
    const cena = this.editor && this.editor.cena;
    const s0 = C.dot(origem, dir), passo = 2;
    const amostras = [];
    for (let b = lo + 1; b <= hi - 1; b += passo) {
      const q = C.add(C.add(origem, C.mul(dir, b - s0)), C.mul(n, 1));
      const ps = paredesNoEixo(so, q, C.mul(n, -1), 600, { cena });
      amostras.push({ b, peca: ps.length > 0, alma: ps.some(w => w.t1 - w.t0 > 60) });
    }
    let r = null;
    const i0 = amostras.findIndex(x => x.alma);
    if (i0 > 0) {
      let i1 = i0;
      while (i1 + 1 < amostras.length && amostras[i1 + 1].alma) i1++;
      let e0 = i0, e1 = i1;                                    // a mesa livre de cada lado da alma
      while (e0 - 1 >= 0 && amostras[e0 - 1].peca && !amostras[e0 - 1].alma) e0--;
      while (e1 + 1 < amostras.length && amostras[e1 + 1].peca && !amostras[e1 + 1].alma) e1++;
      const esq = [amostras[e0].b, amostras[i0].b - passo], dir_ = [amostras[i1].b + passo, amostras[e1].b];
      if (esq[1] - esq[0] >= 15 && dir_[1] - dir_[0] >= 15) {
        const wc = (amostras[i0].b + amostras[i1].b) / 2;
        const meio = ((esq[0] + esq[1]) / 2 + (dir_[0] + dir_[1]) / 2) / 2;
        const half = Math.round((((dir_[0] + dir_[1]) / 2 - (esq[0] + esq[1]) / 2) / 2) / 2.5) * 2.5;
        const c = Math.abs(meio - wc) < 3 ? wc : meio;
        r = { linhas: [c - half, c + half], g: 2 * half, wc: c };
      }
    }
    this._gabaritos.set(chave, r);
    return r;
  }

  /** "M12x30 A325" de um tamanho. */
  _rotulo(t) { return `M${num(t.d)}x${num(t.L)}${t.classe ? ' ' + t.classe : ''}`; }

  get nomeAtual() {
    const { d, L, classe } = this.tamanho;
    return nomeDoParafuso(classe, d, L);
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

  /** Os parafusos da seleção que dá para recalcular: com o tamanho no nome ("BOLT (A325) 16x50") e o eixo conhecido. */
  _selecionadosParaPega() {
    const sel = (this.selecao && this.selecao.entidades) || [];
    return sel.filter(e => e && e.tipo === 'solido' && lerNomeDoParafuso(e.nome) && quadroDoParafuso(e));
  }

  /**
   * "Recalcular pela pega": o parafuso já colocado (antes da regra dos comprimentos comerciais, ou depois de a peça
   * mudar de espessura) mede de novo o pacote que aperta e passa ao comprimento comercial dele — porca na pega nova,
   * nome e lista de materiais juntos. Só nos escolhidos, nunca sozinho: o comprimento de projeto (o 3/8"×1.1/4" do
   * PRATI) pode ter sido pedido assim. O que bate na alma ou não encosta em nada fica como está. Ctrl+Z desfaz.
   */
  recalcularPelaPega(ents = this._selecionadosParaPega()) {
    const cmds = [];
    const mudou = new Map();
    let iguais = 0, semPacote = 0, travados = 0;
    for (const e of ents) {
      const t = lerNomeDoParafuso(e.nome), q = quadroDoParafuso(e);
      if (!t || !q) continue;
      if (!C.editavel(this.editor, e)) { travados++; continue; }
      const alcance = Math.max(200, t.L + 60);
      const pac = pacoteDoEixo(this._pertoDoEixo(q.ponto, q.eixo, alcance), q.ponto, q.eixo, alcance,
                               { cena: this.editor && this.editor.cena, caixaDe: (x) => this._caixaDe(x) });
      if (!pac || !(pac.pega > 0) || pac.bloqueio) { semPacote++; continue; }
      const reg = (e.atributos && e.atributos.parafuso) || {};
      // o do IFC (lido da malha) tem o apoio da cabeça arredondado ao milímetro: encosta na face da 1ª parede
      let t0 = pac.paredes.length ? pac.paredes[0].t0 : 0;
      if (reg.ponto || Math.abs(t0) > 1.5) t0 = 0;
      if (t0) q.ponto = C.add(q.ponto, C.mul(q.eixo, t0));
      const pega = Math.round((pac.pega - t0) * 100) / 100;
      const L = comprimentoPelaPega(t.d, pega);
      if (Math.abs(L - t.L) < 1e-6 && reg.pega && Math.abs(reg.pega - pega) < 0.05) { iguais++; continue; }
      const g = geometriaDoParafuso(t.d, L, q.ponto, C.mul(q.eixo, -1), pega);
      const nome = nomeDoParafuso(t.classe, t.d, L);
      const marcas = { ...((e.atributos && e.atributos.marcas) || {}), perfil: nome };
      cmds.push(C.cmdAlterar(e.id, {
        nome, vertices: g.vertices, faces: g.faces,
        atributos: { ...e.atributos, marcas,
                     parafuso: { ...reg, d: t.d, L, classe: t.classe || reg.classe || '', ponto: C.copiar(q.ponto), eixo: C.copiar(q.eixo), pega } },
      }, 'Recalcular pela pega'));
      const k = `${num(t.L)} → ${num(L)}`;
      mudou.set(k, (mudou.get(k) || 0) + 1);
    }
    if (cmds.length) this.executar(cmds.length > 1 ? C.cmdComposto(cmds, `${cmds.length} parafusos pela pega`) : cmds[0]);
    C.avisarBloqueadas(this.editor, travados);
    const partes = [];
    if (cmds.length) partes.push(`${cmds.length} recalculado(s) (${[...mudou].map(([k, n]) => (n > 1 ? `${n} × ` : '') + k + ' mm').join(', ')})`);
    if (iguais) partes.push(`${iguais} já no comprimento da pega`);
    if (semPacote) partes.push(`${semPacote} sem pacote no eixo (a cabeça não encosta em nada ou o eixo bate numa parede) — ficaram como estavam`);
    this.dica(partes.length ? partes.join(' · ') + (cmds.length ? ' · Ctrl+Z desfaz' : '') : 'Selecione parafusos (BOLT …) para recalcular pela pega');
    if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
    return { recalculados: cmds.length, iguais, semPacote, travados };
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
    const inL = el('input', { type: 'number', min: '10', step: '5', value: String(this.tamanho.L), title: 'Comprimento do parafuso (sem a cabeça), mm — com "pela pega" marcado, vale só onde a cabeça não encosta em nada' });
    inL.addEventListener('change', () => { const L = +inL.value; if (L > 0) this._definir({ L }); });
    const auto = el('input', { type: 'checkbox', title: 'O comprimento sai do pacote que o parafuso aperta (as paredes encostadas a partir da cabeça) + arruela + porca + 3 fios, arredondado de 5 em 5 mm' });
    auto.checked = !!this.constructor.automatico;
    auto.addEventListener('change', () => { this.constructor.automatico = auto.checked; this.limparPrevia(); });
    const selC = el('select', { title: 'Classe do parafuso — vai para o nome e para a lista de materiais' });
    for (const c of CLASSES) selC.append(el('option', { value: c, texto: c }));
    selC.value = this.tamanho.classe || 'A325';
    selC.addEventListener('change', () => this._definir({ classe: selC.value }));
    const eixos = el('input', { type: 'checkbox', title: 'Linhas de centro da face sob o cursor; o parafuso prende nelas e mostra a distância às bordas' });
    eixos.checked = !!this.constructor.eixos;
    eixos.addEventListener('change', () => { this.constructor.eixos = eixos.checked; this.limparPrevia(); });
    g.append(el('label', { texto: 'Diâmetro' }), selD,
             el('label', { texto: 'Comprimento (mm)' }), inL,
             el('label', { texto: '' }), el('span', {}, auto, ' pela pega (automático)'),
             el('label', { texto: 'Classe' }), selC,
             el('label', { texto: 'Eixos da face' }), el('span', {}, eixos, ' mostrar e prender'));
    raiz.append(g);
    this._painelPosicao(raiz, el);
    const colocados = this._colocados();
    if (colocados.length) {
      raiz.append(el('div', { class: 'acoes' }, el('button', { type: 'button', texto: `Furar pelos parafusos já colocados (${colocados.length})`,
        title: 'Abre o furo em toda peça que cada parafuso atravessa e ainda não tem furo no eixo (malha e barra do catálogo), e fecha os furos sem parafuso: o que ficou fora do corpo dele e o de parafuso apagado — os da ferramenta Furo ficam; Ctrl+Z desfaz tudo',
        onclick: () => this.furarPelosColocados() })));
    }
    const paraPega = this._selecionadosParaPega();
    if (paraPega.length) {
      raiz.append(el('div', { class: 'acoes' }, el('button', { type: 'button', texto: `Recalcular pela pega os selecionados (${paraPega.length})`,
        title: 'Mede de novo o pacote que cada parafuso selecionado aperta e passa ao comprimento comercial dele (a porca vai para a pega nova, o nome e a lista de materiais acompanham) — para os colocados antes da regra dos comprimentos fáceis ou depois de uma peça mudar de espessura; Ctrl+Z desfaz',
        onclick: () => this.recalcularPelaPega(paraPega) })));
    }
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

  /** Passo da posição e o padrão (vários de uma vez) — o mesmo bloco no Parafuso e no Furo. */
  _painelPosicao(raiz, el) {
    const F = this.constructor;
    const g = el('div', { class: 'campos' });
    const selP = el('select', { title: 'O ponto anda de tantos em tantos mm a partir da ponta da peça e da borda da face (as cotas mostram as medidas)' });
    for (const [v, t] of [[0, 'livre'], [1, '1 mm'], [5, '5 mm'], [10, '10 mm']]) selP.append(el('option', { value: String(v), texto: t }));
    selP.value = String(F.passo || 0);
    selP.addEventListener('change', () => { F.passo = +selP.value; this.limparPrevia(); });
    const pd = F.padrao = { linhas: 1, g: 60, colunas: 1, p: 60, ...(F.padrao || {}) };
    const campo = (chave, min, titulo) => {
      const i = el('input', { type: 'number', min: String(min), step: '1', value: String(pd[chave]), title: titulo, style: 'width:4.2em' });
      i.addEventListener('change', () => { const v = +i.value; if (v >= min) { pd[chave] = v; this.limparPrevia(); } });
      return i;
    };
    g.append(el('label', { texto: 'Posição' }), selP,
             el('label', { texto: 'Na largura' }), el('span', {}, campo('linhas', 1, 'Quantos atravessados na face (centrados no clique)'), ' × gab. ',
                                                       campo('g', 0, 'Distância entre eles na largura (gabarito), mm')),
             el('label', { texto: 'Ao longo' }), el('span', {}, campo('colunas', 1, 'Quantos ao longo da peça: o 1º no clique, os outros para longe da ponta mais perto'), ' × passo ',
                                                     campo('p', 0, 'Distância entre eles ao longo da peça, mm')));
    raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Posição e quantidade' }), g));
  }

  /** Geometria do parafuso com a cabeça sobre `ponto`, corpo entrando contra `normal` (`t`: {d, L, pega}). */
  geometria(ponto, normal, t = null) {
    const { d, L, pega } = t || this.tamanho;
    return geometriaDoParafuso(d, L, ponto, normal, pega || null);
  }

  /**
   * A linha do eixo (a direção do furo, através da peça) e onde ela cruza as paredes das
   * peças: mostra na prévia onde o parafuso ou o furo cai na peça de baixo.
   */
  _linhaDoEixo(ponto, n, alvo) {
    const alcance = 600;
    const extra = [C.gLinha([C.add(ponto, C.mul(n, 250)), C.add(ponto, C.mul(n, -alcance))], '#1f6fd6', { tracejada: true })];
    const cruz = cruzamentosDoEixo(this._pertoDoEixo(ponto, C.mul(n, -1), alcance), ponto, C.mul(n, -1), alcance, new Set(), (e) => this._caixaDe(e));
    for (const c of cruz.slice(0, 6)) {
      if (c.id === alvo && c.t < 1) continue;
      extra.push(C.gPonto(c.p, '#1f6fd6'));
    }
    const baixo = cruz.find(c => c.id !== alvo);
    if (baixo) extra.push(C.gRotulo(`eixo cruza a peça de baixo a ${mm(baixo.t)} mm`, C.add(baixo.p, C.mul(n, -25)), '#1f6fd6'));
    return extra;
  }

  /**
   * O ponto de verdade na face sob o cursor. A inferência do editor gruda o cursor em
   * extremidades e arestas perto dele — ótimo para desenhar, errado para furar: clicando na
   * mesa perto da ponta da terça, o furo ia para o vértice do canto. Aqui vale o raio
   * contra a peça (a face, o ponto e a normal dela).
   */
  _naFace(p) {
    if (!p || !p.tela || p.tipoSnap === 'sobre_face') return p;
    const sel = this.editor && this.editor.selecao;
    // o raio que a inferência acabou de lançar no mesmo pixel serve (é o mesmo cálculo)
    const ua = this.editor && this.editor.inferencia && this.editor.inferencia.ultimoAlvo;
    const alvo = ua && ua.x === p.tela[0] && ua.y === p.tela[1] ? ua.alvo
      : (sel && sel.sob ? sel.sob(p.tela[0], p.tela[1]) : null);
    if (!alvo || !alvo.id) return p;
    return { ...p, ponto: alvo.ponto, entidade: alvo.id, face: alvo.face, normal: alvo.normal || p.normal, tipoSnap: 'sobre_face' };
  }

  /** Folga (mm) do centro do furo/parafuso até a borda da face: metade do furo + 1 mm. */
  _margemDaBorda() { return furoDoParafuso(this.tamanho ? this.tamanho.d : 12) / 2 + 1; }

  /** O ponto está dentro da face (a extensão dos vértices no plano dela), com a folga? */
  _dentroDaFace(q, f) {
    if (!f) return true;
    const m = this._margemDaBorda();
    const a_ = C.dot(q, f.e1), b_ = C.dot(q, f.e2);
    return a_ >= f.min1 + m - 0.01 && a_ <= f.max1 - m + 0.01 && b_ >= f.min2 + m - 0.01 && b_ <= f.max2 - m + 0.01;
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
    let pts = this._pontosDaPeca(ent);
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

  /** Os pontos da peça para medir a face: na barra, os cantos da seção nas duas pontas (o contorno do perfil, o mesmo do
   *  snap — `inferencia._contornoDaBarra`); antes eram só as duas pontas do eixo, a face saía com largura zero e o eixo da
   *  aba da cantoneira e as distâncias às bordas não apareciam (PRATI CD, 13/10/2026). */
  _pontosDaPeca(ent) {
    if (ent && ent.tipo === 'barra') {
      const inf = this.editor && this.editor.inferencia;
      const c = inf && typeof inf._contornoDaBarra === 'function' ? inf._contornoDaBarra(ent) : null;
      if (c && c.pontos && c.pontos.length >= 6) return c.pontos;
    }
    return C.pontosDaEntidade(ent);
  }

  /** Caixa envolvente da peça (guardada: o mouse passa muitas vezes pelas mesmas). */
  _caixaDe(ent) {
    // guardada no índice (a peça que muda é refeita); a barra paramétrica só tem as duas pontas: a seção entra como folga
    if (!this._indice) this._indice = new IndiceDeCaixas(this.documento, { folgaBarra: 300 });
    return this._indice.caixaDe(ent);
  }

  /**
   * As peças que o parafuso atravessa abaixo da face (o banzo ou a chapa embaixo da
   * terça), da mais perto para a mais longe: o segmento do corpo do parafuso cruza a caixa
   * delas. Parafusos, porcas e telhas ficam de fora.
   */
  _atravessadas(ponto, n, idAlvo) {
    if (!this.documento || !this.documento.entidades) return [];
    const L = this.tamanho.L + 30;
    const fim = C.add(ponto, C.mul(n, -L));
    const lo = [0, 1, 2].map(i => Math.min(ponto[i], fim[i]));
    const hi = [0, 1, 2].map(i => Math.max(ponto[i], fim[i]));
    const ents = this._perto(lo, hi, 80).entidades;
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
    // a mesa do I/H: o centro da face fica em cima da alma — prende nas linhas de gabarito, não no centro
    const ent = this.documento.get(p.entidade);
    const gab = ent && ent.tipo !== 'chapa' ? this._gabaritoDe(ent, p.ponto, n, e2, f.min2, f.max2) : null;
    f.gab = gab;
    let linhaGab = null;
    if (gab) {
      const alvo = gab.linhas.reduce((m, l) => (Math.abs(b - l) < Math.abs(b - m) ? l : m));
      if (Math.abs(b - alvo) <= Math.max(tol2, 0.25 * gab.g)) { b = alvo; presoC2 = true; linhaGab = alvo; }
    } else if (Math.abs(b - c2) <= tol2) { b = c2; presoC2 = true; }
    if (Math.abs(a - c1) <= tol1) { a = c1; presoC1 = true; }
    // fora das linhas de centro, o ponto anda de `passo` em `passo` mm a partir da ponta mais perto e da borda da face:
    // com as cotas ao vivo, dá para pôr o furo a 50 da ponta e a 30 da borda sem digitar (revisão 14/10)
    const passo = this.constructor.passo || 0;
    if (passo > 0) {
      if (!presoC1) { const ref = (a - f.min1) <= (f.max1 - a) ? f.min1 : f.max1; a = ref + Math.round((a - ref) / passo) * passo; }
      if (!presoC2 && larg > 1) {
        const ref = gab ? gab.wc : f.min2;                     // com a alma no meio, o passo conta do eixo dela
        b = ref + Math.round((b - ref) / passo) * passo;
      }
    }
    let ponto = C.add(p.ponto, C.add(C.mul(e1, a - C.dot(p.ponto, e1)), C.mul(e2, b - C.dot(p.ponto, e2))));
    // a peça de baixo (o banzo sob a terça): o eixo dela também prende o parafuso; com os
    // dois eixos presos, o parafuso vai para o cruzamento deles
    const baixo = [];
    for (const e of this._atravessadas(ponto, n, p.entidade)) {
      let ax = this._eixoDaPeca(e, ponto, n);
      if (!ax) continue;
      if (e.tipo !== 'chapa') {
        const gb = this._gabaritoDe(e, ponto, n, ax.f, ax.q - 260, ax.q + 260);
        if (gb) {
          const s = C.dot(ponto, ax.f);
          const alvo = gb.linhas.reduce((m, l) => (Math.abs(s - l) < Math.abs(s - m) ? l : m));
          ax = { ...ax, q: alvo, gab: gb };
        }
      }
      const larg_b = ax.max - ax.min;
      const tol = Math.min(25, Math.max(3, 0.12 * larg_b));
      const dist_ = C.dot(ponto, ax.f) - ax.q;
      let preso = false;
      if (Math.abs(dist_) <= tol) {
        // anda na direção atravessada ao eixo de baixo; se o eixo da face estava preso e as
        // duas linhas não são paralelas, fica no cruzamento (anda ao longo do eixo da face).
        // Só vale se o ponto continua na face: a terça que termina antes do eixo do banzo
        // levava o furo para fora dela.
        let novo;
        if (presoC2 && Math.abs(C.dot(ax.f, e1)) > 0.2) novo = C.add(ponto, C.mul(e1, -dist_ / C.dot(ax.f, e1)));
        else novo = C.add(ponto, C.mul(ax.f, -dist_));
        if (this._dentroDaFace(novo, f)) { ponto = novo; preso = true; }
      }
      baixo.push({ e, ax, preso });
      if (baixo.length >= 1) break;              // o primeiro de baixo basta (o banzo)
    }
    a = C.dot(ponto, e1); b = C.dot(ponto, e2);
    const em = (s1, s2) => C.add(ponto, C.add(C.mul(e1, s1 - a), C.mul(e2, s2 - b)));
    const folga = Math.max(20, 0.1 * larg);
    const extra = [
      // o eixo do parafuso/furo, atravessando a peça (onde ele cai na de baixo)
      ...this._linhaDoEixo(ponto, n, p.entidade),
      // linha de centro ao longo da peça e a atravessada no centro da face
      ...(gab ? gab.linhas.map(l => C.gLinha([em(f.min1 - folga, l), em(f.max1 + folga, l)], linhaGab === l ? '#0a8f3c' : '#2a63c8', { tracejada: true }))
              : [C.gLinha([em(f.min1 - folga, c2), em(f.max1 + folga, c2)], presoC2 ? '#0a8f3c' : '#2a63c8', { tracejada: true })]),
      ...(gab ? [C.gRotulo(`gab. ${mm(gab.g)}`, C.add(em(f.min1 - folga, gab.linhas[1]), C.mul(n, 15)), '#2a63c8')] : []),
      C.gLinha([em(c1, f.min2 - folga), em(c1, f.max2 + folga)], presoC1 ? '#0a8f3c' : '#2a63c8', { tracejada: true }),
      // a atravessada que passa pelo parafuso
      C.gLinha([em(a, f.min2), em(a, f.max2)], '#8a94a6'),
    ];
    // (o rótulo "face: bordas … pontas …" saiu: as cotas abaixo mostram as mesmas medidas no lugar delas, e os rótulos
    // se sobrepunham em volta do parafuso — revisão 14/10; a linha de centro verde diz que prendeu no eixo)
    // as cotas ao vivo, junto do parafuso (13/10/2026: "mostrar as medidas para posicionar o parafuso de primeira"): até a
    // ponta mais perto da peça e até cada borda da face, cada uma com a medida no meio dela
    const meio = (q, r) => C.mul(C.add(q, r), 0.5);
    const praPonta = (a - f.min1) <= (f.max1 - a) ? f.min1 : f.max1;
    const pPonta = em(praPonta, b), pB0 = em(a, f.min2), pB1 = em(a, f.max2);
    extra.push(C.gLinha([ponto, pPonta], '#c2410c'));
    extra.push(C.gRotulo(mm(Math.abs(a - praPonta)), C.add(meio(ponto, pPonta), C.mul(n, 12)), '#c2410c'));
    if (larg > 1) {
      extra.push(C.gRotulo(mm(b - f.min2), C.add(meio(ponto, pB0), C.mul(n, 12)), '#475569'));
      extra.push(C.gRotulo(mm(f.max2 - b), C.add(meio(ponto, pB1), C.mul(n, 12)), '#475569'));
    }
    for (const { e, ax, preso } of baixo) {
      // o eixo da peça de baixo, levado ao plano da face, perto do parafuso
      const s = C.dot(ponto, ax.f) - ax.q;
      const base = C.add(ponto, C.mul(ax.f, -s));
      const meia = Math.max(150, 2 * (ax.max - ax.min));
      extra.push(C.gLinha([C.add(base, C.mul(ax.d, -meia)), C.add(base, C.mul(ax.d, meia))],
                          preso ? '#0a8f3c' : '#b8860b', { tracejada: true }));
      const q = C.dot(ponto, ax.f);
      const nomeB = (e.atributos && e.atributos.marcas && (e.atributos.marcas.nome || e.atributos.marcas.posicao)) || e.nome || 'peça de baixo';
      const oQue = ax.gab ? `gabarito ${mm(ax.gab.g)}` : 'eixo';
      const t2 = `${nomeB}: ${preso ? 'no ' + oQue : mm(Math.abs(s)) + ' mm do ' + oQue}` + (ax.gab ? '' : ` · bordas ${mm(q - ax.min)} | ${mm(ax.max - q)} mm`);
      extra.push(C.gRotulo(t2, C.add(ponto, C.add(C.mul(n, 60), C.mul(ax.f, 0.5 * (ax.max - ax.min) + 60))), '#7a5a00'));
    }
    return { ponto, extra, face: f };
  }

  /** O texto do parafuso no ponto: o tamanho e de onde veio o comprimento. */
  _textoDoTamanho(t, quantos = 1) {
    const vezes = quantos > 1 ? `${quantos} × ` : '';
    if (t.bate) return `${vezes}${this._rotulo(t)} · BATE NA ALMA de ${t.bate}: vá para o gabarito`;
    if (!t.pega) return `${vezes}${this._rotulo(t)} · sem peça embaixo`;
    const pega = `pega ${String(Math.round(t.pega * 10) / 10).replace('.', ',')}`;
    if (t.curto) return `${vezes}${this._rotulo(t)} · CURTO p/ ${pega}`;
    return `${vezes}${this._rotulo(t)} · ${pega}`;
  }

  onMover(p) {
    this.limparPrevia();
    p = this._naFace(p);
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const { ponto, extra, face } = this.ajustar(p, n);
    const pts = this._pontosDoPadrao(ponto, face);
    const partes = [];
    let t0 = null;
    for (const q of pts) {
      const t = this._tamanhoNoPonto(q, n);
      if (!t0 || (t.bate && !t0.bate)) t0 = t;
      const g = this.geometria(q, n, t);
      partes.push(C.gMalha(g.vertices, g.faces, t.bate ? '#6b7280' : t.curto ? '#b45309' : '#d62728', t.bate ? 0.35 : 0.55));
    }
    const texto = this._textoDoTamanho(t0, pts.length);
    this.medida(this._rotulo(t0));
    // o rótulo ao lado da face (fora dela, do lado da borda de menor coordenada), para não cobrir o parafuso e as cotas
    const lado = face ? C.mul(face.e2, -((C.dot(ponto, face.e2) - face.min2) + 45)) : [0, 0, 0];
    this.previa(C.grupo(...partes, C.gRotulo(texto, C.add(ponto, C.add(C.mul(n, 20), lado)), t0.bate ? '#b91c1c' : t0.curto ? '#b45309' : undefined), ...extra));
  }

  onPonto(p) {
    p = this._naFace(p);
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const { ponto, face } = this.ajustar(p, n);
    const pts = this._pontosDoPadrao(ponto, face);
    const alvo = this.documento.get(p.entidade);
    const marcas = (alvo && alvo.atributos && alvo.atributos.marcas) || {};
    const dir = C.normalizar(C.mul(n, -1));
    // o documento como vai ficando: o 2º parafuso fura em cima do que o 1º já furou na mesma peça
    const lo = [0, 1, 2].map(i => Math.min(...pts.map(q => q[i]))), hi = [0, 1, 2].map(i => Math.max(...pts.map(q => q[i])));
    const alcanceMax = Math.max(200, this.tamanho.L + 60);
    const base = this._perto(lo, hi, alcanceMax + 10);
    const mapa = new Map(base.entidades);
    const doc = { entidades: mapa, get: (id) => mapa.get(id) || this.documento.get(id) };
    const novos = [], alterados = new Map();
    let paredes = 0, curtos = 0, batem = 0, ondeBate = '';
    const tamanhos = new Map();
    for (const q of pts) {
      const t = this._tamanhoNoPonto(q, n);
      // "Como será executado?": o parafuso em cima da alma não passa — não entra no modelo
      if (t.bate) { batem++; ondeBate = t.bate; continue; }
      if (t.curto) curtos++;
      const g = this.geometria(q, n, t);
      const nome = nomeDoParafuso(t.classe, t.d, t.L);
      const id = C.novoId('paraf');
      // os furos: cada parede que o corpo atravessa (a face clicada, a mesa de baixo, a chapa do suporte) ganha o furo
      // da norma; onde a peça já tem furo no eixo, nada muda
      const forma = { d: furoDoParafuso(t.d) };
      const furos = furosDoParafuso(doc, q, dir, t.L, forma, new Set(), id);
      for (const f of furos) {
        mapa.set(f.id, { ...doc.get(f.id), ...f.campos });
        alterados.set(f.id, { ...(alterados.get(f.id) || {}), ...f.campos });
        paredes += f.paredes;
      }
      const furosBarra = this._furosNasBarras(q, dir, t.L, forma, id, doc);
      for (const m of furosBarra) { mapa.set(m.id, m); novos.push(m); }
      paredes += furosBarra.length;
      novos.push({
        tipo: 'solido', id, nome, camada: 'Parafusos', material: 'Cor #ff0000',
        visivel: true, bloqueada: false, grupo: '',
        vertices: g.vertices, faces: g.faces, arestas_vivas: [],
        atributos: {
          tipo_ifc: 'IfcMechanicalFastener',
          marcas: { perfil: nome, ...(marcas.conjunto ? { conjunto: marcas.conjunto } : {}) },
          criado_no_editor: true,
          parafuso: { d: t.d, L: t.L, classe: t.classe || '', ponto: C.copiar(q), eixo: dir, ...(t.pega ? { pega: Math.round(t.pega * 100) / 100 } : {}),
                      furos: [...furos.map(f => f.id), ...furosBarra.map(f => f.id)] },
        },
      });
      const r = this._rotulo(t);
      tamanhos.set(r, (tamanhos.get(r) || 0) + 1);
    }
    if (!tamanhos.size) {
      this.dica(`O eixo do parafuso bate na alma de ${ondeBate} (o ponto está no meio da mesa): mova para o gabarito, fora da alma — nada foi lançado`);
      return;
    }
    const cmds = [C.cmdAdicionar(novos, pts.length > 1 ? 'Parafusos' : 'Parafuso'),
                  ...[...alterados].map(([id, campos]) => C.cmdAlterar(id, campos, 'Furo do parafuso'))];
    this.executar(cmds.length > 1 ? C.cmdComposto(cmds, pts.length > 1 ? `${pts.length} parafusos com furos` : 'Parafuso com furos') : cmds[0]);
    const quais = [...tamanhos].map(([r, k]) => (k > 1 ? `${k} × ` : '') + r).join(', ');
    this.dica(`${quais} colocado(s)` + (paredes ? ` · furo Ø${num(furoDoParafuso(this.tamanho.d))} aberto em ${paredes} parede(s)` : ' (as peças já tinham furo no eixo)')
              + (curtos ? ` · ATENÇÃO: ${curtos} curto(s) para a pega — aumente o comprimento ou marque "pela pega"` : '')
              + (batem ? ` · ${batem} não lançado(s): bate(m) na alma de ${ondeBate}` : '')
              + ' · clique no próximo (Esc sai)');
  }

  /**
   * Os furos nas barras do catálogo que o corpo do parafuso atravessa (a terça, o banzo): a barra não tem malha
   * própria para furar, então cada parede atravessada ganha o marcador de furo, como a ferramenta Furo faz — antes
   * só a peça de malha (a chapa, o sólido) era furada (pedido do usuário, 01/10: "não furou nem a terça nem o banzo
   * onde está posicionado o parafuso"). A parede sai da seção do perfil (a mesma que o 3D desenha) cortada pelo eixo.
   */
  _furosNasBarras(ponto, d, L, forma, idParafuso, documento = null) {
    documento = documento || this.documento;
    const cena = this.editor && this.editor.cena;
    if (!cena || typeof cena._secaoDoPerfil !== 'function') return [];
    const fim = C.add(ponto, C.mul(d, L));
    const r = forma.d / 2;
    const marcados = [...documento.entidades.values()].filter(m => m.atributos && m.atributos.furo && m.atributos.furo.peca);
    const out = [];
    for (const e of documento.entidades.values()) {
      if (e.tipo !== 'barra' || e.visivel === false || !e.inicio || !e.fim) continue;
      // longe do eixo do parafuso: nem calcula
      const lo = [0, 1, 2].map(i => Math.min(e.inicio[i], e.fim[i]) - 400), hi = [0, 1, 2].map(i => Math.max(e.inicio[i], e.fim[i]) + 400);
      if ([0, 1, 2].some(i => Math.max(ponto[i], fim[i]) < lo[i] || Math.min(ponto[i], fim[i]) > hi[i])) continue;
      const forma2 = cena._secaoDoPerfil(e.perfil);
      if (!forma2 || typeof forma2.getPoints !== 'function') continue;
      const poligonos = [forma2.getPoints().map(q => [q.x, q.y]), ...(forma2.holes || []).map(h => h.getPoints().map(q => [q.x, q.y]))];
      const { t, u, v } = baseDaBarra(e.inicio, e.fim, e.rotacao || 0);
      const rel = C.sub(ponto, e.inicio);
      const x = C.dot(rel, u), y = C.dot(rel, v), z = C.dot(rel, t);
      const dx = C.dot(d, u), dy = C.dot(d, v), dz = C.dot(d, t);
      if (Math.hypot(dx, dy) < 0.3) continue;                 // parafuso ao longo da barra
      const comp = C.dist(e.inicio, e.fim);
      const ss = poligonos.flatMap(pts => cortesDaReta(x, y, dx, dy, pts)).sort((a, b) => a - b);
      for (let i = 0; i + 1 < ss.length; i += 2) {
        const s0 = ss[i], s1 = ss[i + 1];
        if (s1 < -2 || s0 > L + 2 || s1 - s0 < 0.2) continue;
        const zq = z + dz * s0;
        if (zq < (e.recorte_inicio || 0) - 1 || zq > comp - (e.recorte_fim || 0) + 1) continue;
        const q = C.add(ponto, C.mul(d, s0));
        if (marcados.some(m => m.atributos.furo.peca === e.id && C.dist(m.atributos.furo.ponto, q) < r + 1)) continue;
        const prof = Math.min(s1 - s0, 60);
        const g = marcadorDeFuro(q, d, prof, forma);
        out.push({
          tipo: 'solido', id: C.novoId('furo'), nome: `FURO Ø${num(forma.d)}`, camada: 'Furos', material: 'Cor #1f2430',
          visivel: true, bloqueada: false, grupo: '', vertices: g.vertices, faces: g.faces, arestas_vivas: [],
          atributos: {
            tipo_ifc: 'IfcOpeningElement', exportar: false, criado_no_editor: true,
            furo: { d: forma.d, ponto: C.copiar(q), eixo: C.copiar(d), profundidade: prof, peca: e.id, parafuso: idParafuso },
          },
        });
      }
    }
    return out;
  }

  /** Os parafusos que já estão no modelo (colocados no editor): os que pedem furo. */
  _colocados() {
    return [...this.documento.entidades.values()].filter(e => e.visivel !== false && e.atributos && e.atributos.parafuso
      && Array.isArray(e.atributos.parafuso.ponto) && Array.isArray(e.atributos.parafuso.eixo) && e.atributos.parafuso.L > 0);
  }

  /**
   * Fura de novo pelos parafusos já colocados: cada um abre o furo d+1 em toda parede que o corpo dele atravessa e
   * ainda não tem furo no eixo (a peça de malha e a barra do catálogo) — os colocados numa versão que furava menos
   * (os da Sala, de 28/09, furaram só o U150 de cima; pedido do usuário, 01/10). Um comando só: Ctrl+Z desfaz tudo.
   */
  furarPelosColocados() {
    const lista = this._colocados();
    if (!lista.length) { this.dica('Nenhum parafuso colocado no editor neste modelo.'); return; }
    // o documento como vai ficando: cada parafuso fura em cima do que os anteriores já furaram
    const mapa = new Map(this.documento.entidades);
    const doc = { entidades: mapa, get: (id) => mapa.get(id) };
    const alterados = new Map(), novos = [], furosDe = new Map();
    // o furo no eixo de um parafuso mas FORA do corpo dele (a ferramenta antiga furava a face clicada, ~150 mm acima
    // da cabeça, e não a ligação): sai — a peça é refeita sem ele, quando guardou a malha de antes do furo
    // e o furo aberto por um parafuso que já foi apagado (o registro diz de qual parafuso ele é): sem parafuso, sai
    // (pedido do usuário, 01/10: "apagar os furos que não têm parafuso"); o furo da ferramenta Furo não tem parafuso e fica
    const semParafuso = (r) => r.parafuso && r.parafuso !== 'x' && !this.documento.get(r.parafuso);
    const foraDoCorpo = (r) => semParafuso(r) || lista.some(pf => {
      const a = pf.atributos.parafuso, d = C.normalizar(a.eixo);
      const w = C.sub(r.ponto, a.ponto), s = C.dot(w, d);
      return C.comp(C.sub(w, C.mul(d, s))) < 1.5 && (s < -3 || s > a.L + 3);
    });
    let tirados = 0, presos = 0;
    for (const e of [...mapa.values()]) {
      const regs = e.atributos && e.atributos.furos_editor;
      if (!regs || !regs.length) continue;
      const fora = regs.filter(foraDoCorpo);
      if (!fora.length) continue;
      const fica = regs.filter(r => !fora.includes(r));
      const refeito = refazerFurosEditor(e, fica);
      if (!refeito) { presos += fora.length; continue; }
      const campos = { vertices: refeito.vertices, faces: refeito.faces, atributos: { ...e.atributos, furos_editor: refeito.registros } };
      mapa.set(e.id, { ...e, ...campos });
      alterados.set(e.id, campos);
      tirados += fora.length;
    }
    // os marcadores de furo (barras) de parafuso apagado
    const orfaos = [...mapa.values()].filter(m => m.camada === 'Furos' && m.atributos && m.atributos.furo && m.atributos.furo.parafuso
      && !this.documento.get(m.atributos.furo.parafuso)).map(m => m.id);
    for (const id of orfaos) mapa.delete(id);
    tirados += orfaos.length;
    for (const pf of lista) {
      const a = pf.atributos.parafuso;
      const forma = { d: furoDoParafuso(a.d || 12) };
      const d = C.normalizar(a.eixo);
      const fs = furosDoParafuso(doc, a.ponto, d, a.L, forma, new Set([pf.id]), pf.id);
      for (const f of fs) {
        const e = { ...mapa.get(f.id), ...f.campos };
        mapa.set(f.id, e);
        alterados.set(f.id, { ...(alterados.get(f.id) || {}), ...f.campos });
      }
      const fb = this._furosNasBarras(a.ponto, d, a.L, forma, pf.id, doc);
      for (const m of fb) { mapa.set(m.id, m); novos.push(m); }
      const ids = [...fs.map(f => f.id), ...fb.map(f => f.id)];
      if (ids.length) furosDe.set(pf.id, ids);
    }
    const aviso = presos ? ` · ${presos} furo(s) antigo(s) fora do corpo do parafuso não puderam ser fechados (a peça não guardou a malha de antes do furo)` : '';
    if (!alterados.size && !novos.length && !orfaos.length) { this.dica(`Os ${lista.length} parafusos já têm os furos em todas as peças que atravessam${aviso}.`); return; }
    const cmds = [];
    if (orfaos.length) cmds.push(C.cmdRemover(orfaos, 'Furos sem parafuso'));
    if (novos.length) cmds.push(C.cmdAdicionar(novos, 'Furos nas barras'));
    for (const [id, campos] of alterados) cmds.push(C.cmdAlterar(id, campos, 'Furo do parafuso'));
    for (const [id, ids] of furosDe) {
      const pf = this.documento.get(id);
      const ant = (pf.atributos.parafuso.furos || []);
      cmds.push(C.cmdAlterar(id, { atributos: { ...pf.atributos, parafuso: { ...pf.atributos.parafuso, furos: [...new Set([...ant, ...ids])] } } }, 'Furos do parafuso'));
    }
    this.executar(C.cmdComposto(cmds, 'Furar pelos parafusos colocados'));
    this.dica(`Furos abertos: ${alterados.size} peça(s) de malha e ${novos.length} parede(s) de barra, por ${furosDe.size} dos ${lista.length} parafusos`
      + (tirados ? ` · ${tirados} furo(s) sem parafuso (fora do corpo dele, ou de parafuso apagado) fechado(s)` : '') + aviso + ' (Ctrl+Z desfaz tudo).');
  }

  cancelar() { this.limparPrevia(); C.voltarParaSelecao(this.editor); }
}

export default FerramentaParafuso;
