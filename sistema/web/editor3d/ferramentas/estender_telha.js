// Estender / recuar telha (20/10/2026, o usuário no Mercado: "criar uma ferramenta para extender ou recuar as telhas —
// no editar elas viram todas pedaços individuais em trechos, e as ferramentas que criamos não funcionam para as telhas").
//
// A telha lançada (telhas_cobertura.py, _solido_da_chapa) é um Sólido em seções: o perfil trapezoidal em cada terça (ou
// longarina, no fechamento), ligado de uma à outra, sem tampa nas pontas — o Empurrar/Puxar não tem face para pegar e o
// Estender só conhece barra. Aqui a ponta anda pela própria telha (a direção do último trecho); recuar além de uma
// terça tira aquela seção. Vale para todo sólido nesse formato (no Mercado, as 1.157 telhas; rufo, calha e cumeeira não
// são em seções e ficam de fora).
//
// 1. Clique na telha, perto da ponta que vai andar. Se ela está na seleção, andam todas as telhas selecionadas (a faixa
//    inteira, a fiada de cima do fechamento): em cada uma, a ponta do mesmo lado.
// 2. Mova e clique, ou digite quanto (mm; negativo recua) e Enter. Com o cursor num ponto do modelo (a ponta, o meio ou
//    a aresta de outra peça), cada ponta vai até ele: até a altura dele na telha em pé (fechamento), até a linha dele em
//    planta na telha da cobertura. Logo depois, outra medida corrige. Ctrl+Z desfaz.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

const MINIMO = 50;                                   // mm: a telha não fica mais curta que isso
const SNAPS_DE_PONTO = new Set(['extremidade', 'meio', 'centro', 'interseccao', 'sobre_aresta']);

/**
 * As seções do sólido em telha: `m` vértices por seção, `n` seções seguidas e as faces de um trecho (`modelo`, índices
 * nas duas primeiras seções) repetidas trecho a trecho. null quando o sólido não tem esse formato.
 */
export function secoesDaTelha(ent) {
  if (!ent || ent.tipo !== 'solido') return null;
  const vs = ent.vertices || [], fs = ent.faces || [];
  const f0 = fs[0];
  if (!f0 || f0.length < 3 || f0[0] !== 0) return null;
  const m = f0[1];
  if (!(m >= 3) || vs.length % m || vs.length / m < 2) return null;
  const n = vs.length / m;
  const T = fs.findIndex(f => f.some(i => i >= 2 * m));
  const nT = T < 0 ? fs.length : T;
  if (!nT || nT * (n - 1) !== fs.length) return null;
  const modelo = fs.slice(0, nT);
  if (modelo.some(f => f.some(i => !(i >= 0 && i < 2 * m)))) return null;
  for (let j = 1; j < n - 1; j++) {
    for (let k = 0; k < nT; k++) {
      const f = fs[j * nT + k], g = modelo[k];
      if (!f || f.length !== g.length || f.some((i, q) => i !== g[q] + j * m)) return null;
    }
  }
  const secoes = [];
  for (let j = 0; j < n; j++) secoes.push(vs.slice(j * m, (j + 1) * m));
  return { m, n, modelo, secoes };
}

const centro = (sec) => {
  const c = [0, 0, 0];
  for (const p of sec) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  return C.mul(c, 1 / (sec.length || 1));
};

/** As seções na ordem da ponta parada para a que anda, com os centros e o comprimento acumulado. */
function caminho(sd, ponta) {
  const secs = ponta === 'inicio' ? sd.secoes.slice().reverse() : sd.secoes.slice();
  const cs = secs.map(centro);
  const acc = [0];
  for (let i = 1; i < cs.length; i++) acc.push(acc[i - 1] + C.dist(cs[i - 1], cs[i]));
  return { secs, cs, acc, total: acc[acc.length - 1] };
}

/** Para onde a ponta `ponta` ('inicio'|'fim') aponta (do trecho dela para fora) e o centro dela. */
export function pontaDaTelha(ent, ponta, sd = secoesDaTelha(ent)) {
  if (!sd) return null;
  const { cs } = caminho(sd, ponta);
  const a = cs[cs.length - 2], b = cs[cs.length - 1];
  if (C.dist(a, b) < 1e-6) return null;
  return { centro: b, dir: C.normalizar(C.sub(b, a)) };
}

/**
 * A telha com a ponta `ponta` andada `delta` mm pela própria telha (positivo estica, negativo recua — tirando as seções
 * que ficam para fora). Devolve {vertices, faces, delta, antes, depois, centro} ou null (a telha sumiria).
 */
export function telhaAndada(ent, ponta, delta, sd = secoesDaTelha(ent)) {
  if (!sd || !isFinite(delta)) return null;
  const { secs, cs, acc, total } = caminho(sd, ponta);
  const novo = total + delta;
  if (novo < MINIMO) return null;
  let fora;
  if (delta >= 0) {
    const k = secs.length - 1;
    const d = C.normalizar(C.sub(cs[k], cs[k - 1]));
    fora = secs.slice(0, k).concat([secs[k].map(p => C.add(p, C.mul(d, delta)))]);
  } else {
    let k = 0;
    while (k < acc.length - 2 && acc[k + 1] < novo) k++;
    const L = acc[k + 1] - acc[k] || 1;
    const f = (novo - acc[k]) / L;
    const ponto = secs[k].map((p, i) => C.add(p, C.mul(C.sub(secs[k + 1][i], p), f)));
    fora = f < 1e-6 && k >= 1 ? secs.slice(0, k + 1) : secs.slice(0, k + 1).concat([ponto]);
  }
  if (ponta === 'inicio') fora.reverse();
  const vertices = [].concat(...fora).map(p => p.map(x => Math.round(x * 100) / 100));
  const faces = [];
  for (let j = 0; j < fora.length - 1; j++) for (const f of sd.modelo) faces.push(f.map(i => i + j * sd.m));
  const fim = ponta === 'inicio' ? fora[0] : fora[fora.length - 1];
  return { vertices, faces, delta, antes: total, depois: novo, centro: centro(fim), secao: fim };
}

/**
 * Quanto a ponta anda para chegar no plano que passa por `alvo` com a normal `N`, seguindo a telha (e o último trecho
 * prolongado). null se ela não cruza o plano.
 */
export function deltaAtePlano(ent, ponta, alvo, N, sd = secoesDaTelha(ent)) {
  if (!sd) return null;
  const { cs, acc, total } = caminho(sd, ponta);
  const f = (p) => C.dot(C.sub(p, alvo), N);
  let achado = null;
  for (let k = 0; k < cs.length - 1; k++) {
    const a = f(cs[k]), b = f(cs[k + 1]);
    if (Math.abs(b - a) < 1e-9) continue;
    const t = -a / (b - a);
    const ultimo = k === cs.length - 2;
    if (t >= -1e-9 && (t <= 1 + 1e-9 || ultimo)) achado = acc[k] + t * (acc[k + 1] - acc[k]);
  }
  return achado == null ? null : achado - total;
}

/** O plano até onde as pontas vão, pelo ponto: na telha em pé, a altura dele; na deitada, a linha dele em planta. */
export function planoDoAlvo(D) {
  if (Math.abs(D[2]) > 0.7) return [0, 0, Math.sign(D[2]) || 1];
  const h = C.normalizar([D[0], D[1], 0]);
  return h;
}

export class FerramentaEstenderTelha extends Ferramenta {
  static id = 'estender_telha';
  static nome = 'Estender / recuar telha';
  static atalho = 'Shift+T';
  static grupo = 'estrutura';
  static dica = 'Clique na telha perto da ponta que vai andar (com várias selecionadas, andam todas)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M2.5 20l2-3h3l2 3h3l2-3h3l2 3h2"/><path d="M12 13V3.5"/><path d="M9.2 6.3 12 3.5l2.8 2.8"/><path d="M7 13h10"/></svg>`;

  ativar() {
    this.alvo = null;           // { D, base, itens: [{id, ponta}], fora }
    this.delta = 0;
    this.modo = null;           // { ponto, N } com o cursor num ponto do modelo
    this.dica(FerramentaEstenderTelha.dica);
    this.medida('');
  }

  desativar() { this.limparPrevia(); }

  cancelar() {
    if (this.alvo) { this.alvo = null; this.limparPrevia(); this.medida(''); this.dica(FerramentaEstenderTelha.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  reiniciar() { this.alvo = null; this.delta = 0; this.modo = null; this.limparPrevia(); this.medida(''); }

  _telhaSob(p) {
    const t = p && p.tela;
    const s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    const e = s && s.entidade;
    return e && secoesDaTelha(e) ? { e, ponto: s.ponto } : null;
  }

  /** As telhas que andam e a ponta de cada uma, a partir do clique na telha `e` no `ponto`. */
  _escolher(e, ponto) {
    const sd = secoesDaTelha(e);
    const ci = centro(sd.secoes[0]), cf = centro(sd.secoes[sd.n - 1]);
    const ponta = C.dist(ponto, ci) < C.dist(ponto, cf) ? 'inicio' : 'fim';
    const ref = pontaDaTelha(e, ponta, sd);
    if (!ref) return null;
    const sel = C.idsSelecionados(this.editor);
    const ids = sel.includes(e.id) ? sel : [e.id];
    const itens = [];
    let bloqueadas = 0, fora = 0;
    for (const id of ids) {
      const t = this.documento.get(id);
      const s = t && secoesDaTelha(t);
      if (!s) continue;
      if (!C.editavel(this.editor, t)) { bloqueadas++; continue; }
      let melhor = null;
      for (const pt of ['inicio', 'fim']) {
        const r = pontaDaTelha(t, pt, s);
        const k = r ? C.dot(r.dir, ref.dir) : -2;
        if (!melhor || k > melhor.k) melhor = { k, pt };
      }
      if (melhor.k < 0.7) { fora++; continue; }       // corre em outra direção: não é da mesma faixa
      itens.push({ id, ponta: melhor.pt });
    }
    return { D: ref.dir, base: ref.centro, itens, bloqueadas, fora };
  }

  /** O quanto cada telha anda: o mesmo delta para todas, ou até o plano do ponto. */
  _resultados() {
    const a = this.alvo;
    const out = [];
    for (const it of a.itens) {
      const t = this.documento.get(it.id);
      if (!t) continue;
      const d = this.modo ? deltaAtePlano(t, it.ponta, this.modo.ponto, this.modo.N) : this.delta;
      const r = d == null ? null : telhaAndada(t, it.ponta, d);
      out.push({ it, t, r });
    }
    return out;
  }

  _desenhar() {
    this.limparPrevia();
    if (!this.alvo) return;
    const res = this._resultados();
    const pos = [], tra = [];
    for (const { t, it, r } of res) {
      if (!r) continue;
      const s = r.secao;
      for (let i = 0; i < s.length - 1; i++) pos.push(...s[i], ...s[i + 1]);
      const p0 = pontaDaTelha(t, it.ponta);
      if (p0) tra.push(...p0.centro, ...r.centro);
    }
    const linhas = (arr, cor, tracejada) => {
      if (!arr.length) return null;
      const g = new C.THREE.BufferGeometry();
      g.setAttribute('position', new C.THREE.Float32BufferAttribute(arr, 3));
      const mat = tracejada ? new C.THREE.LineDashedMaterial({ color: cor, dashSize: 40, gapSize: 30, depthTest: false, transparent: true })
                            : new C.THREE.LineBasicMaterial({ color: cor, depthTest: false, transparent: true });
      const o = new C.THREE.LineSegments(g, mat);
      if (tracejada) o.computeLineDistances();
      o.renderOrder = 990;
      return o;
    };
    const ok = res.filter(x => x.r);
    const ref = ok.find(x => x.it.id === this._clicada) || ok[0];
    const texto = !ref ? 'a telha sumiria' : this.modo
      ? `até o ponto · ${ok.length} telha(s)`
      : `${this.delta >= 0 ? 'estica' : 'recua'} ${formatar(Math.abs(this.delta))} · ${ok.length} telha(s)`;
    this.previa(C.grupo(linhas(pos, '#0a8f3c', false), linhas(tra, '#0a8f3c', true),
                        C.gRotulo(texto, ref ? ref.r.centro : this.alvo.base, ref ? '#0a8f3c' : '#b00020')));
    if (ref) this.medida(this.modo ? `${formatar(ref.r.depois)} (${ref.r.delta >= 0 ? '+' : '−'}${formatar(Math.abs(ref.r.delta))})`
                                   : `${this.delta >= 0 ? '+' : '−'}${formatar(Math.abs(this.delta))}`);
  }

  onMover(p) {
    if (!this.alvo || !p) return;
    if (SNAPS_DE_PONTO.has(p.tipoSnap) && !this.alvo.itens.some(it => it.id === p.entidade)) {
      this.modo = { ponto: p.ponto, N: planoDoAlvo(this.alvo.D) };
    } else {
      this.modo = null;
      this.delta = C.distanciaNaReta(this.editor, p, this.alvo.base, this.alvo.D);
    }
    this._desenhar();
  }

  onPonto(p) {
    if (!this.alvo) {
      const sob = this._telhaSob(p);
      if (!sob) { this.dica('Clique numa telha lançada, perto da ponta que vai andar (rufo, calha e cumeeira não andam por aqui)'); return; }
      if (!C.editavel(this.editor, sob.e)) { this.dica(C.DICA_BLOQUEADA); return; }
      const a = this._escolher(sob.e, sob.ponto);
      if (!a || !a.itens.length) { this.dica('Essa telha não tem como andar (as seções coincidem)'); return; }
      this.alvo = a;
      this._clicada = sob.e.id;
      this.delta = 0;
      this.modo = null;
      if (!C.idsSelecionados(this.editor).includes(sob.e.id)) this.selecao.definir([sob.e.id]);
      C.avisarBloqueadas(this.editor, a.bloqueadas);
      const n = a.itens.length;
      this.dica(`${n} telha(s) ${n > 1 ? 'andam' : 'anda'}${a.fora ? ` (${a.fora} em outra direção ficam)` : ''}: mova e clique, ` +
                'ou digite quanto (negativo recua) · no ponto de outra peça, vão até ele · Esc volta');
      this._desenhar();
      return;
    }
    this.onMover(p);
    this._aplicar();
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.alvo && (this.modo || this.delta)) { this._aplicar(); return true; }
    return false;
  }

  onValor(texto) {
    if (!this.alvo) return C.corrigirUltimo(this, texto);
    const v = paraMilimetros(texto);
    if (!isFinite(v) || v === 0) return false;
    this.modo = null;
    this.delta = v;
    this._aplicar();
    return true;
  }

  _aplicar() {
    const res = this._resultados().filter(x => x.r && Math.abs(x.r.delta) > 0.05);
    if (!res.length) { this.dica('A telha sumiria (ou não anda): escolha outro ponto ou outra medida'); return; }
    const cmds = res.map(({ t, r }) => {
      const at = { ...(t.atributos || {}) };
      if (isFinite(at.comprimento)) at.comprimento = Math.round(at.comprimento + r.delta);
      return C.cmdAlterar(t.id, C.marcarParaConferir(t, { vertices: r.vertices, faces: r.faces, atributos: at }), 'Estender telha');
    });
    const cmd = C.cmdComposto(cmds, res.length > 1 ? `Estender ${res.length} telhas` : 'Estender telha');
    this.executar(cmd);
    const estado = { alvo: this.alvo, _clicada: this._clicada, delta: 0, modo: null };
    // o alvo de "corrigir logo depois": as mesmas telhas a partir de como estavam (o desfazer volta a geometria)
    C.lembrarUltimo(this, cmd, estado);
    const ref = res.find(x => x.t.id === this._clicada) || res[0];
    this.reiniciar();
    this.dica(`${res.length} telha(s): ${ref.r.delta >= 0 ? 'esticou' : 'recuou'} ${formatar(Math.abs(ref.r.delta))} ` +
              '(outra medida agora corrige · Ctrl+Z desfaz) · clique na próxima telha');
  }
}

export default FerramentaEstenderTelha;
