// Ferramenta de seleção — a ferramenta de repouso do editor.
//
// Clique simples escolhe; Shift soma; Ctrl alterna. Arrastar abre uma janela: da
// esquerda para a direita pega só o que está inteiramente dentro; da direita para a
// esquerda pega também o que apenas toca, como em qualquer CAD. Duplo clique amplia a
// seleção para os objetos semelhantes (mesmo tipo e mesmo perfil).
// Tab, com o mouse parado, passa o destaque para a peça de trás (Shift+Tab volta), como no Revit; o clique no mesmo
// lugar seleciona a destacada — a peça escondida atrás da outra sem girar a vista.
// Alças (14/10): a barra selecionada mostra um quadradinho em cada ponta; arrastar a alça leva a ponta com o snap (o
// canto, o meio, o eixo da obra, o alinhamento) ou, sem snap forte, ao longo da própria barra — esticar e encurtar
// sem trocar de ferramenta, como as alças do Revit. Ctrl+Z desfaz.

import { Ferramenta, formatar } from './base.js';
import * as C from './_comum.js';
import { pontoNoEixo } from '../nucleo/inferencia.js';
import { ocultarNaVista, mostrarOcultas } from '../modulos/menu_contexto.js';

const MAX_ALCAS = 30;          // barras selecionadas com alça (mais que isso, nenhuma: a tela vira confete)
const RAIO_ALCA = 8;           // px
//: o snap que leva a ponta para fora do eixo da barra; com os outros ela corre ao longo dele
const SNAP_FORTE = new Set(['extremidade', 'meio', 'interseccao', 'centro', 'eixo_obra', 'nivel', 'alinhado', 'perpendicular']);

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
    this._alca = null;
    this._comAlcas = false;
    this.limparPrevia();
    this._fecharJanela();
    this.editor.selecao.realcarSobre(null);
    this.editor.inferencia.ativa = true;
  }

  onMover(p, ev) {
    // arrastando uma alça: a ponta da barra vai junto
    if (ev && ev.arrasto && (this._alca || (!this.arrastando && (this._alca = this._alcaEm(ev.arrasto.de))))) {
      this._arrastarAlca(ev.arrasto.para, ev);
      return;
    }
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
    this._desenharAlcas();
    // em cima de uma alça: a mão de arrastar
    const sobreAlca = !!this._alcaEm(p.tela);
    this.editor.cursor(sobreAlca ? 'grab' : 'default');
    if (sobreAlca) { this.editor.medida('arraste a ponta (snap, ou ao longo da barra)'); return; }
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
    if (c) { this.editor.selecao.clicar(c.ids[c.i], ev); this._ciclo = null; this._desenharAlcas(); return; }
    const alvo = this.editor.selecao.sob(p.tela[0], p.tela[1]);
    this.editor.selecao.clicar(alvo ? alvo.id : null, ev);
    this._desenharAlcas();
  }

  onSoltar(p, ev) {
    if (this._alca) { this._soltarAlca(); return; }
    const arr = (ev && ev.arrasto) || this.arrastando;
    this._fecharJanela();
    if (!arr) return;
    const modo = arr.para[0] >= arr.de[0] ? 'dentro' : 'toca';
    const achados = this.editor.selecao.porJanela(arr.de, arr.para, modo, ev);
    this.editor.dica(achados.length
      ? `${achados.length} ${achados.length === 1 ? 'objeto selecionado' : 'objetos selecionados'}.`
      : 'Nada na janela.');
    this._desenharAlcas();
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
      // ocultar e isolar pelo teclado (o mesmo do menu do botão direito): Alt+H oculta, Alt+Shift+H mostra, Alt+I isola
      const k = String(ev.key).toLowerCase();
      if (k === 'h') { if (ev.shiftKey) mostrarOcultas(this.editor); else ocultarNaVista(this.editor, [...sel.ids]); this.limparPrevia(); this._comAlcas = false; return true; }
      if (k === 'i') { if (this.editor._isolamento) this.editor.sairDoIsolamento(); else if (sel.ids.size) this.editor.isolarSelecao(); return true; }
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

  // ------------------------------------------------------------- alças

  /** As alças das barras selecionadas: [{id, ponta, ponto, tela}]. */
  _alcas() {
    const sel = this.editor.selecao, doc = this.editor.documento;
    const ids = sel && sel.ids ? [...sel.ids] : [];
    if (!ids.length || ids.length > MAX_ALCAS) return [];
    const out = [];
    for (const id of ids) {
      const b = doc.get(id);
      if (!b || b.tipo !== 'barra' || !C.editavel(this.editor, b) || !doc.aparece(b)) continue;
      for (const ponta of ['inicio', 'fim']) {
        const t = this.editor.camera.paraTela(b[ponta]);
        if (t[2] <= 1 && isFinite(t[0])) out.push({ id, ponta, ponto: b[ponta].slice(), tela: [t[0], t[1]] });
      }
    }
    return out;
  }

  /** A alça em `tela` (até RAIO_ALCA px), ou null. */
  _alcaEm(tela) {
    if (!tela) return null;
    let melhor = null, dm = RAIO_ALCA;
    for (const a of this._alcas()) {
      const d = Math.hypot(a.tela[0] - tela[0], a.tela[1] - tela[1]);
      if (d <= dm) { dm = d; melhor = a; }
    }
    return melhor;
  }

  _desenharAlcas(destaque = null) {
    const alcas = this._alcas();
    if (!alcas.length && !this._comAlcas) return;
    this.limparPrevia();
    this._comAlcas = alcas.length > 0;
    if (!alcas.length) return;
    const g = C.grupo();
    for (const a of alcas) g.add(C.gPonto(a.ponto, destaque && destaque.id === a.id && destaque.ponta === a.ponta ? '#f59e0b' : '#2563eb'));
    this.previa(g);
  }

  /** A ponta da barra seguindo o mouse: o snap forte leva para onde ele aponta; sem ele, ao longo da barra. */
  _arrastarAlca(tela, ev) {
    const a = this._alca, ed = this.editor, inf = ed.inferencia;
    const b = ed.documento.get(a.id);
    if (!b) { this._alca = null; return; }
    const outra = a.ponta === 'inicio' ? b.fim : b.inicio;
    const ativa = inf.ativa;
    inf.ativa = true;
    inf.definirAncora(a.ponto);
    let r;
    try { r = inf.resolver(tela[0], tela[1], ev || {}); } finally { inf.ativa = ativa; }
    let q = r.ponto;
    // o snap na própria barra (a ponta que está sendo levada) não conta
    const forte = SNAP_FORTE.has(r.tipoSnap) && r.entidade !== a.id;
    if (!forte) {
      const dir = C.normalizar(C.sub(a.ponto, outra));
      q = pontoNoEixo(outra, dir, ed.selecao.raioEm(tela[0], tela[1])) || q;
    }
    if (C.dist(q, outra) < 1) return;
    a.novo = q.map(x => Math.round(x * 100) / 100);
    this.limparPrevia();
    const g = C.grupo(C.gLinha([outra, a.novo], C.CORES.ok), C.gLinha([a.ponto, a.novo], C.CORES.guia, { tracejada: true }),
                      C.gPonto(a.novo, '#f59e0b'));
    this.previa(g);
    if (forte) inf.desenhar(r); else inf.limpar();
    ed.cursor('grabbing');
    ed.medida(`${b.perfil || 'barra'} · ${formatar(C.dist(outra, a.novo))}` + (forte ? ` · ${r.rotulo}` : ' · ao longo da barra'));
  }

  _soltarAlca() {
    const a = this._alca;
    this._alca = null;
    this.editor.inferencia.limpar();
    this.editor.inferencia.limparAncora();
    this.editor.cursor('default');
    const b = a && this.editor.documento.get(a.id);
    if (!b || !a.novo || C.dist(a.novo, a.ponto) < 0.01) { this._desenharAlcas(); return; }
    this.executar(C.cmdAlterar(b.id, C.marcarParaConferir(b, { [a.ponta]: a.novo }), 'Esticar pela alça'));
    const outra = a.ponta === 'inicio' ? b.fim : b.inicio;
    this.editor.dica(`Ponta levada: ${formatar(C.dist(outra, a.novo))} (Ctrl+Z desfaz)`);
    this._desenharAlcas();
  }

  cancelar() {
    this._ciclo = null;
    if (this._alca) { this._alca = null; this.editor.inferencia.limpar(); this.editor.inferencia.limparAncora(); }
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
