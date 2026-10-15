// Virar perfil: gira a seção da barra em torno do próprio eixo, como o Girar do SketchUp preso ao eixo da peça
// (pedido de 30/09: "a ferramenta de virar o eixo do perfil... algo como a ferramenta virar do SketchUp").
//
// Passe o mouse na barra: aparece a seção de agora (cinza) e como ela fica (laranja), no ponto do cursor.
//   clique ............ gira o passo (90°)
//   Shift + clique .... gira o passo ao contrário
//   Ctrl + clique ..... vira 180° (a boca do U, a aba da cantoneira para o outro lado)
//   digite o ângulo ... e Enter: vira o passo dos próximos cliques (15, 45, 22,5…)
// Com barras já selecionadas, o clique numa delas vira todas (cada uma no próprio eixo). O eixo e os nós não
// mudam — é o campo Rotação do painel de propriedades, a um clique; Ctrl+Z desfaz.
// O perfil que veio do IFC como malha também vira: no eixo dele (o maior eixo principal), pelo meio da caixa da seção
// (revisão 14/10; antes a ferramenta mandava usar o Girar).

import { Ferramenta } from './base.js';
import * as C from './_comum.js';
import { baseDaBarra } from '../nucleo/documento.js';
import { quadroDaMalha, giroNoEixo, caixaDaSecao } from './_malha_perfil.js';

const norm360 = (a) => { let r = a % 360; if (r < 0) r += 360; return Math.round(r * 1000) / 1000; };

export class FerramentaVirar extends Ferramenta {
  static id = 'virar';
  static nome = 'Virar perfil';
  static atalho = 'V';
  static grupo = 'estrutura';
  static dica = 'Clique no perfil (barra ou malha do IFC): gira 90° no próprio eixo · Shift ao contrário · Ctrl vira 180° · digite o ângulo e Enter';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M8 6h8v3h-5v6h5v3H8z"/><path d="M19.5 8.5a8 8 0 0 1 0 7"/><path d="M19.5 15.5l-2.2-.4M19.5 15.5l.6-2.1"/></svg>`;
  static passo = 90;

  ativar() {
    this.alvos = C.idsSelecionados(this.editor).filter(id => { const e = this.documento.get(id); return e && (e.tipo === 'barra' || quadroDaMalha(e)); });
    this._dica();
  }

  desativar() { this.limparPrevia(); }

  // o Virar não tem passo no meio: o Esc solta a ferramenta (antes só limpava a prévia e ela ficava presa — revisão 14/10)
  cancelar() { this.limparPrevia(); this.medida(''); C.voltarParaSelecao(this.editor); }

  _dica(extra = '') {
    const p = this.constructor.passo;
    const quem = this.alvos && this.alvos.length > 1 ? ` (${this.alvos.length} perfis selecionados viram juntos)` : '';
    this.dica(`${extra}Clique no perfil: gira ${String(p).replace('.', ',')}°${quem} · Shift ao contrário · Ctrl vira 180° · digite o ângulo e Enter`);
    this.medida(`${String(p).replace('.', ',')}°`);
  }

  _barraSob(p) {
    const t = p && p.tela;
    const alvo = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    const e = alvo && this.documento.get(alvo.id);
    if (e && e.tipo === 'barra') return { e, ponto: alvo.ponto };
    const q = e && quadroDaMalha(e);
    return q ? { e, ponto: alvo.ponto, q } : null;
  }

  _angulo(ev) {
    if (ev && (ev.ctrlKey || ev.metaKey || ev.altKey)) return 180;
    return (ev && ev.shiftKey ? -1 : 1) * this.constructor.passo;
  }

  /** O contorno da seção da barra girada de `delta`, no ponto do eixo mais perto de `ponto`. */
  _contorno(b, ponto, delta) {
    const forma = this.cena._secaoDoPerfil(b.perfil);
    const pts = forma.extractPoints(8).shape;
    const { t, u, v } = baseDaBarra(b.inicio, b.fim, norm360((b.rotacao || 0) + delta));
    const L = C.dist(b.inicio, b.fim);
    const s = Math.max(0, Math.min(L, C.dot(C.sub(ponto, b.inicio), t)));
    const O = C.add(b.inicio, C.mul(t, s));
    return pts.map(q => C.add(O, C.add(C.mul(u, q.x), C.mul(v, q.y))));
  }

  onMover(p, ev) {
    this.limparPrevia();
    const sob = this._barraSob(p);
    if (!sob) return;
    const d = this._angulo(ev || {});
    try {
      const cont = (a) => (sob.q ? caixaDaSecao(sob.q, sob.ponto, a) : this._contorno(sob.e, sob.ponto, a));
      this.previa(C.grupo(C.gLinha(cont(0), '#9aa4b2', { fechada: true }), C.gLinha(cont(d), '#ff5a1f', { fechada: true })));
    } catch (e) { /* perfil sem seção: sem prévia */ }
    if (sob.q) this.medida(`${sob.e.nome || 'perfil (malha)'} · gira ${String(d).replace('.', ',')}° no eixo`);
    else this.medida(`${sob.e.perfil} · ${String(norm360(sob.e.rotacao || 0)).replace('.', ',')}° → ${String(norm360((sob.e.rotacao || 0) + d)).replace('.', ',')}°`);
  }

  onPonto(p, ev = {}) {
    const sob = this._barraSob(p);
    if (!sob) {
      const t = p && p.tela, s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
      this.dica(s && s.entidade && s.entidade.tipo !== 'barra'
        ? 'Essa peça não é um perfil comprido (chapa, nó, fixador): o Virar gira perfis. Para ela, use o Girar (Q)'
        : 'Clique num perfil (barra ou malha do IFC) para virar a seção dela');
      return;
    }
    const d = this._angulo(ev);
    const todos = this.alvos && this.alvos.length > 1 && this.alvos.includes(sob.e.id) ? this.alvos : [sob.e.id];
    // a peça travada ou em camada bloqueada não vira (revisão 14/10, D4)
    const ids = todos.filter(id => C.editavel(this.editor, this.documento.get(id)));
    if (!ids.length) { this.dica(C.DICA_BLOQUEADA); return; }
    C.avisarBloqueadas(this.editor, todos.length - ids.length);
    const cmds = [];
    for (const id of ids) {
      const e = this.documento.get(id);
      if (e.tipo === 'barra') { cmds.push(C.cmdAlterar(id, { rotacao: norm360((e.rotacao || 0) + d) }, 'Virar perfil')); continue; }
      // a malha: gira no próprio eixo, com os marcadores de furo dela
      const q = quadroDaMalha(e);
      if (!q) continue;
      const { fp, fv } = giroNoEixo(q, d);
      for (const m of C.pecasParaTransformar(this.documento, [e]).pecas) cmds.push(C.cmdAlterar(m.id, C.camposTransformados(m, fp, fv), 'Virar perfil'));
    }
    this.executar(cmds.length === 1 ? cmds[0] : C.cmdComposto(cmds, `Virar ${cmds.length} perfis`));
    this.limparPrevia();
    const e = this.documento.get(sob.e.id);
    this._dica(ids.length > 1 ? `${ids.length} perfis virados. ` : e.tipo === 'barra' ? `${e.nome || e.perfil} a ${String(norm360(e.rotacao || 0)).replace('.', ',')}°. ` : `${e.nome || 'Perfil'} virado ${String(d).replace('.', ',')}°. `);
  }

  onValor(texto) {
    const a = parseFloat(String(texto || '').replace('°', '').replace(',', '.'));
    if (!isFinite(a) || a === 0 || Math.abs(a) > 360) { this.dica('Digite o ângulo do passo em graus (90, 45, 22,5)'); return true; }
    this.constructor.passo = a;
    this._dica();
    return true;
  }
}
