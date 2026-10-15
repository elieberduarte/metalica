// Ferramenta de seleção — a ferramenta de repouso do editor.
//
// Clique simples escolhe; Shift soma; Ctrl alterna. Arrastar abre uma janela: da
// esquerda para a direita pega só o que está inteiramente dentro; da direita para a
// esquerda pega também o que apenas toca, como em qualquer CAD. Duplo clique amplia a
// seleção para os objetos semelhantes (mesmo tipo e mesmo perfil).
// Tab, com o mouse parado, passa o destaque para a peça de trás (Shift+Tab volta), como no Revit; o clique no mesmo
// lugar seleciona a destacada — a peça escondida atrás da outra sem girar a vista.

import { Ferramenta } from './base.js';

export class Selecionar extends Ferramenta {
  static id = 'selecionar';
  static nome = 'Selecionar';
  static atalho = 'Espaço';
  static grupo = 'navegacao';
  static dica = 'Clique para selecionar; Shift soma, Ctrl alterna. Arraste para a janela de seleção.';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">
      <path d="M5 3l7.5 17 2.2-6.3 6.3-2.2z"/></svg>`;

  ativar() {
    this.arrastando = null;
    this.dica(Selecionar.dica);
    this.editor.cursor('default');
    this.editor.inferencia.ativa = false;   // selecionar não precisa de snap
  }

  desativar() {
    this._fecharJanela();
    this.editor.selecao.realcarSobre(null);
    this.editor.inferencia.ativa = true;
  }

  onMover(p, ev) {
    if (ev && ev.arrasto) {
      // Enquanto o botão está pressionado, desenha a janela.
      this.arrastando = ev.arrasto;
      const modo = ev.arrasto.para[0] >= ev.arrasto.de[0] ? 'dentro' : 'toca';
      this.editor.retanguloSelecao(ev.arrasto.de, ev.arrasto.para, modo);
      this.editor.medida(modo === 'dentro' ? 'janela: inteiramente dentro'
                                           : 'janela: o que tocar');
      return;
    }
    this._tela = p.tela.slice(0, 2);
    // o ciclo do Tab vale enquanto o mouse fica no lugar
    const c = this._noCiclo(p.tela);
    if (c) {
      this.editor.selecao.realcarSobre(c.ids[c.i]);
      const e = this.editor.documento.get(c.ids[c.i]);
      this.editor.medida(e ? this.editor.descreverEntidade(e) : '');
      return;
    }
    this._ciclo = null;
    // Sem arrasto: só destaca o que está sob o cursor.
    const alvo = this.editor.selecao.sob(p.tela[0], p.tela[1]);
    this.editor.selecao.realcarSobre(alvo ? alvo.id : null);
    this.editor.medida(alvo ? this.editor.descreverEntidade(alvo.entidade) : '');
  }

  /** O ciclo do Tab, se o ponto `tela` está onde ele começou (3 px). */
  _noCiclo(tela) {
    const c = this._ciclo;
    return c && tela && Math.hypot(tela[0] - c.pos[0], tela[1] - c.pos[1]) <= 3 ? c : null;
  }

  onPonto(p, ev) {
    const c = this._noCiclo(p.tela);
    if (c) { this.editor.selecao.clicar(c.ids[c.i], ev); this._ciclo = null; return; }
    const alvo = this.editor.selecao.sob(p.tela[0], p.tela[1]);
    this.editor.selecao.clicar(alvo ? alvo.id : null, ev);
  }

  onSoltar(p, ev) {
    const arr = (ev && ev.arrasto) || this.arrastando;
    this._fecharJanela();
    if (!arr) return;
    const modo = arr.para[0] >= arr.de[0] ? 'dentro' : 'toca';
    const achados = this.editor.selecao.porJanela(arr.de, arr.para, modo, ev);
    this.editor.dica(achados.length
      ? `${achados.length} ${achados.length === 1 ? 'objeto selecionado' : 'objetos selecionados'}.`
      : 'Nada na janela.');
  }

  onDuploClique(p, ev) {
    const alvo = this.editor.selecao.sob(p.tela[0], p.tela[1]);
    if (!alvo) { this.editor.selecao.tudo(); return; }
    // peça com marca de posição (IFC) num projeto: o duplo clique abre o detalhe dela
    // no CAD; Shift mantém a seleção dos semelhantes
    const ent = alvo.entidade || this.editor.documento.get(alvo.id);
    const marcas = (ent && ent.atributos && ent.atributos.marcas) || {};
    if (marcas.posicao && this.editor.projeto && !(ev && ev.shiftKey) && this.editor.abrirDetalheDaPeca) {
      this.editor.abrirDetalheDaPeca(ent);
      return;
    }
    this.editor.selecao.semelhantes(alvo.id, !!(ev && ev.shiftKey));
    this.editor.dica('Selecionados os objetos semelhantes.');
  }

  onTecla(ev) {
    if (ev.type !== 'keydown') return false;
    const sel = this.editor.selecao;
    if (ev.key === 'Tab' && !ev.ctrlKey && !ev.altKey) return this._tab(ev.shiftKey ? -1 : 1);
    // Alt + clique de tipo: atalhos de seleção por critério.
    if (ev.altKey && !ev.ctrlKey) {
      const primeira = sel.entidades[0];
      if (ev.key === 'c' && primeira) { sel.porCamada(primeira.camada); return true; }
      if (ev.key === 'p' && primeira && primeira.perfil) { sel.porPerfil(primeira.perfil); return true; }
      if (ev.key === 't' && primeira) { sel.porTipo(primeira.tipo); return true; }
    }
    return false;
  }

  /** Tab: o destaque passa para a próxima peça sob o cursor (de trás); `passo` -1 volta. */
  _tab(passo) {
    const pos = this._tela;
    if (!pos) return true;
    let c = this._noCiclo(pos);
    if (!c) {
      const ids = this.editor.selecao.todosSob(pos[0], pos[1]);
      if (ids.length < 2) { this.editor.dica(ids.length ? 'Só uma peça sob o cursor.' : 'Nada sob o cursor.'); return true; }
      c = this._ciclo = { pos: pos.slice(), ids, i: 0 };
    }
    c.i = (c.i + passo + c.ids.length) % c.ids.length;
    this.editor.selecao.realcarSobre(c.ids[c.i]);
    const e = this.editor.documento.get(c.ids[c.i]);
    const nome = e ? (e.perfil || e.nome || e.tipo) : '';
    this.editor.dica(`Tab: ${c.i + 1} de ${c.ids.length} sob o cursor — ${nome} · clique seleciona esta · Shift+Tab volta`);
    this.editor.medida(e ? this.editor.descreverEntidade(e) : '');
    return true;
  }

  cancelar() {
    this._ciclo = null;
    this._fecharJanela();
    this.editor.selecao.limpar();
  }

  _fecharJanela() {
    this.arrastando = null;
    this.editor.retanguloSelecao(null);
    this.editor.medida('');
  }
}

export default Selecionar;
