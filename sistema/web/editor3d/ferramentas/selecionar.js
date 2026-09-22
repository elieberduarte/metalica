// Ferramenta de seleção — a ferramenta de repouso do editor.
//
// Clique simples escolhe; Shift soma; Ctrl alterna. Arrastar abre uma janela: da
// esquerda para a direita pega só o que está inteiramente dentro; da direita para a
// esquerda pega também o que apenas toca, como em qualquer CAD. Duplo clique amplia a
// seleção para os objetos semelhantes (mesmo tipo e mesmo perfil).

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
    // Sem arrasto: só destaca o que está sob o cursor.
    const alvo = this.editor.selecao.sob(p.tela[0], p.tela[1]);
    this.editor.selecao.realcarSobre(alvo ? alvo.id : null);
    this.editor.medida(alvo ? this.editor.descreverEntidade(alvo.entidade) : '');
  }

  onPonto(p, ev) {
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
    const marcas = (alvo.atributos && alvo.atributos.marcas) || {};
    if (marcas.posicao && this.editor.projeto && !(ev && ev.shiftKey) && this.editor.abrirDetalheDaPeca) {
      this.editor.abrirDetalheDaPeca(alvo);
      return;
    }
    this.editor.selecao.semelhantes(alvo.id, !!(ev && ev.shiftKey));
    this.editor.dica('Selecionados os objetos semelhantes.');
  }

  onTecla(ev) {
    if (ev.type !== 'keydown') return false;
    const sel = this.editor.selecao;
    // Alt + clique de tipo: atalhos de seleção por critério.
    if (ev.altKey && !ev.ctrlKey) {
      const primeira = sel.entidades[0];
      if (ev.key === 'c' && primeira) { sel.porCamada(primeira.camada); return true; }
      if (ev.key === 'p' && primeira && primeira.perfil) { sel.porPerfil(primeira.perfil); return true; }
      if (ev.key === 't' && primeira) { sel.porTipo(primeira.tipo); return true; }
    }
    return false;
  }

  cancelar() {
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
