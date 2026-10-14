// Estender / aparar até outra barra (F7 do levantamento de 14/10 — o "Extend" do Tekla).
//
// 1. Clique na barra a ajustar: a ponta mais perto do clique é a que anda.
// 2. Clique na outra barra: a ponta vai até a FACE dela (a viga que chega no pilar para na mesa); com Shift, até o EIXO
//    dela. Se a ponta já passa da outra barra, ela é aparada até lá. Digite a folga em mm antes do segundo clique (ex.:
//    "10": para 10 mm antes da face).
// O corte no ângulo daquela ponta (do Encaixar) sai — ele era relativo ao nó antigo; o Encaixar refaz se precisar. A
// peça com marca fica com a marca a conferir (o Numerar separa). Ctrl+Z desfaz.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
import { baseDaBarra } from '../nucleo/documento.js';

/**
 * A nova posição da ponta `ponta` ('inicio'|'fim') da barra `b` estendida até a barra `alvo`: até a face (ou o eixo,
 * `ateEixo`), com `folga` mm antes. `secao(perfil)` dá o contorno [[x, y]] da seção. Devolve {ponto, s} ou null (as
 * barras são paralelas).
 */
export function pontaEstendida(b, ponta, alvo, secao, { ateEixo = false, folga = 0 } = {}) {
  const fixo = ponta === 'inicio' ? b.fim : b.inicio;
  const anda = ponta === 'inicio' ? b.inicio : b.fim;
  const d = C.normalizar(C.sub(anda, fixo));
  const e = C.normalizar(C.sub(alvo.fim, alvo.inicio));
  // os pontos mais perto entre as duas retas: fixo + s·d e alvo.inicio + r·e
  const w = C.sub(fixo, alvo.inicio);
  const b_ = C.dot(d, e), dd = C.dot(d, w), ee = C.dot(e, w);
  const den = 1 - b_ * b_;
  if (den < 1e-6) return null;                                       // paralelas
  let s = (b_ * ee - dd) / den;
  if (!ateEixo) {
    // a face da outra barra que olha para a ponta: o quanto a seção dela vai, a partir do eixo, contra a direção d
    const dp = C.sub(d, C.mul(e, C.dot(d, e)));                      // a parte de d atravessada ao eixo do alvo
    const k = C.comp(dp);
    if (k > 1e-6) {
      const dpn = C.mul(dp, 1 / k);
      const { u, v } = baseDaBarra(alvo.inicio, alvo.fim, alvo.rotacao || 0);
      let h = 0;
      for (const [x, y] of secao(alvo.perfil) || []) h = Math.max(h, -C.dot(C.add(C.mul(u, x), C.mul(v, y)), dpn));
      s -= h / k;
    }
  }
  s -= folga;
  if (s < 1) return null;                                            // a barra sumiria
  return { ponto: C.add(fixo, C.mul(d, s)), s };
}

export class FerramentaEstender extends Ferramenta {
  static id = 'estender';
  static nome = 'Estender / aparar';
  static atalho = '';
  static grupo = 'estrutura';
  static dica = 'Clique na barra a estender ou aparar (perto da ponta que vai andar)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M19 3v18"/><path d="M3 12h12"/><path d="M12 9l3 3-3 3"/><path d="M3 9.5v5" /></svg>`;
  static folga = 0;

  ativar() {
    this.barra = null;
    this.ponta = null;
    this.dica(FerramentaEstender.dica);
    this.medida(this.constructor.folga ? `folga ${formatar(this.constructor.folga)}` : '');
  }

  desativar() { this.limparPrevia(); }

  cancelar() {
    if (this.barra) { this.barra = null; this.limparPrevia(); this.selecao.limpar(); this.dica(FerramentaEstender.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  _barraSob(p) {
    const t = p && p.tela;
    const s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    const e = s && s.entidade;
    return e && e.tipo === 'barra' ? { e, ponto: s.ponto } : null;
  }

  _secao(perfil) {
    const cena = this.editor && this.editor.cena;
    return C.secaoDoPerfil(null, cena, perfil);
  }

  _resultado(alvo, ev) {
    const b = this.documento.get(this.barra);
    if (!b || !alvo || alvo.id === b.id) return null;
    const r = pontaEstendida(b, this.ponta, alvo, (n) => this._secao(n), { ateEixo: !!(ev && ev.shiftKey), folga: this.constructor.folga || 0 });
    return r ? { b, ...r } : null;
  }

  onMover(p, ev) {
    if (!this.barra) return;
    this.limparPrevia();
    const sob = this._barraSob(p);
    const r = sob && this._resultado(sob.e, ev);
    if (!r) { if (sob && sob.e.id !== this.barra) this.dica('Essa barra corre paralela à que anda: escolha uma que ela cruze'); return; }
    const antes = this.ponta === 'inicio' ? r.b.inicio : r.b.fim;
    const fixo = this.ponta === 'inicio' ? r.b.fim : r.b.inicio;
    const dL = r.s - C.dist(fixo, antes);
    this.previa(C.grupo(C.gLinha([fixo, r.ponto], '#0a8f3c', { tracejada: true }), C.gPonto(r.ponto, '#0a8f3c'),
                        C.gRotulo(`${dL >= 0 ? 'estica' : 'apara'} ${formatar(Math.abs(dL))} · até ${ev && ev.shiftKey ? 'o eixo' : 'a face'}`,
                                  r.ponto, '#0a8f3c')));
    this.medida(`${formatar(r.s)} (${dL >= 0 ? '+' : '−'}${formatar(Math.abs(dL))})`);
  }

  onPonto(p, ev = {}) {
    const sob = this._barraSob(p);
    if (!this.barra) {
      if (!sob) { this.dica('Clique numa barra (perfil do catálogo) perto da ponta que vai andar'); return; }
      if (!C.editavel(this.editor, sob.e)) { this.dica(C.DICA_BLOQUEADA); return; }
      this.barra = sob.e.id;
      this.ponta = C.dist(sob.ponto, sob.e.inicio) <= C.dist(sob.ponto, sob.e.fim) ? 'inicio' : 'fim';
      this.selecao.definir([sob.e.id]);
      this.dica(`Ponta ${this.ponta === 'inicio' ? 'do início' : 'do fim'}: clique na barra até onde ela vai (a face; Shift: o eixo) · digite a folga em mm · Esc volta`);
      return;
    }
    if (!sob || sob.e.id === this.barra) { this.dica('Clique na OUTRA barra, até onde a ponta vai'); return; }
    const r = this._resultado(sob.e, ev);
    if (!r) { this.dica('Não dá para estender até essa barra (paralela, ou a peça sumiria): escolha outra'); return; }
    const k = this.ponta === 'inicio' ? 'inicio' : 'fim';
    const campos = { [k]: r.ponto.map(x => Math.round(x * 100) / 100),
                     [this.ponta === 'inicio' ? 'cortes_inicio' : 'cortes_fim']: [],
                     [this.ponta === 'inicio' ? 'recorte_inicio' : 'recorte_fim']: 0 };
    this.executar(C.cmdAlterar(r.b.id, C.marcarParaConferir(r.b, campos), 'Estender barra'));
    this.limparPrevia();
    this.barra = null;
    this.selecao.limpar();
    this.dica('Feito. Clique na próxima barra a estender (Ctrl+Z desfaz; o Encaixar corta a ponta no ângulo, se precisar)');
  }

  onValor(texto) {
    const v = paraMilimetros(texto);
    if (!isFinite(v)) return false;
    this.constructor.folga = v;
    this.medida(v ? `folga ${formatar(v)}` : '');
    this.dica(`Folga de ${formatar(v)} antes da face (ou do eixo, com Shift)`);
    return true;
  }
}

export default FerramentaEstender;
