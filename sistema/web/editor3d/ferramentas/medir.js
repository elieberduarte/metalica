// Trena: distância entre dois pontos, com as projeções em X, Y e Z.
//
// O segundo clique congela a medida; Enter cria uma linha de construção entre os
// dois pontos (Sólido só de arestas, camada "Referência", `atributos.tipo =
// 'construcao'`), que serve de guia para o snap sem virar geometria do modelo.
//
// Começando na aresta (o snap "Sobre aresta", não no canto nem no meio), como a trena do SketchUp: a medida é a
// distância perpendicular à aresta e a prévia é a guia paralela a ela passando pelo cursor; digite o afastamento
// (150) e Enter cria a guia paralela — "a terça a 150 da borda da mesa". O painel apaga todas as guias.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaMedir extends Ferramenta {
  static id = 'medir';
  static nome = 'Medir';
  static atalho = 'T';
  static grupo = 'medicao';
  static dica = 'Clique no primeiro ponto a medir';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M2.8 14.2 14.2 2.8l7 7L9.8 21.2Z"/><path d="M6.4 10.6l1.8 1.8M9.2 7.8l1.8 1.8M12 5l1.8 1.8M15.6 8.6l1.8 1.8"/></svg>`;

  ativar() {
    this.a = null; this.b = null; this.atual = null;
    this.eixo = null; this.aresta = null;
    this.dica(FerramentaMedir.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (this.b) return;
    this.atual = this.resolver(p.ponto);
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    const q = this.resolver(p.ponto);
    if (!this.a) {
      this.a = q;
      C.ancorar(this.editor, q);
      // na aresta: a guia paralela a ela
      if (p.tipoSnap === 'sobre_aresta' && Array.isArray(p.aresta) && C.dist(p.aresta[0], p.aresta[1]) > 1e-3) {
        this.aresta = { a: C.copiar(p.aresta[0]), b: C.copiar(p.aresta[1]), dir: C.normalizar(C.sub(p.aresta[1], p.aresta[0])) };
        this.dica('Afaste para o lado da guia paralela e clique, ou digite o afastamento (150) · Enter cria a guia');
        this.desenhar();
        return;
      }
      this.dica('Clique no segundo ponto');
      this.desenhar();
      return;
    }
    if (!this.b) {
      if (C.iguais(this.a, q, 1e-6)) return;
      this.b = q;
      this.dica(this.aresta ? 'Enter cria a guia paralela · digite outro afastamento · Esc limpa' : 'Enter cria a linha de construção · Esc limpa');
      this.desenhar();
      return;
    }
    this.aresta = null;
    // já havia medida: recomeça deste ponto
    this.a = q; this.b = null;
    C.ancorar(this.editor, q);
    this.dica('Clique no segundo ponto');
    this.desenhar();
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (C.teclaDeEixo(this, ev)) { this.desenhar(); return true; }
    if (ev.key === 'Enter') {
      const b = this.b || this.atual;
      if (this.aresta && this.a && b) { const g = this.guiaParalela(b); if (g) { this.criarGuia(g[0], g[1], g[2]); return true; } }
      if (this.a && b && !C.iguais(this.a, b, 1e-6)) { this.criarGuia(this.a, b); return true; }
    }
    return false;
  }

  onValor(texto) {
    // uma medida digitada estende o segundo ponto na direção corrente
    const d = paraMilimetros(texto);
    // na guia paralela: o afastamento, para o lado em que o mouse está (pode redigitar)
    if (this.aresta && this.a && isFinite(d)) {
      const ref = this.b || this.atual;
      const off = ref ? this._afastamento(ref) : null;
      if (!off || C.comp(off) < 1e-6) { this.dica('Mova o mouse para o lado da guia antes de digitar o afastamento'); return true; }
      this.b = C.add(this.a, C.mul(C.normalizar(off), d));
      const g = this.guiaParalela(this.b);
      if (g) this.criarGuia(g[0], g[1], g[2]);
      return true;
    }
    if (!this.a || this.b) return false;
    if (!isFinite(d) || !this.atual) return false;
    const dir = C.sub(this.atual, this.a);
    if (C.comp(dir) < 1e-6) return false;
    this.b = C.add(this.a, C.mul(C.normalizar(dir), d));
    this.dica('Enter cria a linha de construção · Esc limpa');
    this.desenhar();
    return true;
  }

  cancelar() {
    if (this.a || this.b) { this.reiniciar(); this.dica(FerramentaMedir.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  resolver(ponto) {
    if (!this.a || !this.eixo) return C.copiar(ponto);
    return C.projetarNoEixo(this.a, ponto, this.eixo);
  }

  /** O vetor do pé na aresta até `q`, perpendicular a ela. */
  _afastamento(q) {
    const r = C.sub(q, this.aresta.a);
    return C.sub(r, C.mul(this.aresta.dir, C.dot(r, this.aresta.dir)));
  }

  /** A guia paralela à aresta passando por `q`: [início, fim, afastamento] — a aresta esticada para os dois lados. */
  guiaParalela(q) {
    if (!this.aresta || !q) return null;
    const off = this._afastamento(q);
    const L = C.dist(this.aresta.a, this.aresta.b), ext = Math.max(1000, 0.5 * L), d = this.aresta.dir;
    return [C.add(C.add(this.aresta.a, off), C.mul(d, -ext)), C.add(C.add(this.aresta.b, off), C.mul(d, ext)), C.comp(off)];
  }

  /** As linhas de construção do modelo (as da trena). */
  _guias() {
    const ents = this.documento && this.documento.entidades;
    return ents ? [...ents.values()].filter(e => e.atributos && e.atributos.tipo === 'construcao') : [];
  }

  /** Painel: quantas guias há e o botão de apagar todas (o "Excluir guias" do SketchUp). */
  painel(raiz, el) {
    const gs = this._guias();
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Trena' }),
                   el('span', { texto: gs.length ? `${gs.length} linha(s) de construção no modelo` : 'Nenhuma linha de construção' })));
    if (gs.length) {
      raiz.append(el('div', { class: 'acoes' }, el('button', { type: 'button', texto: `Apagar as linhas de construção (${gs.length})`,
        title: 'Apaga todas as guias da trena (as peças e as cotas ficam); Ctrl+Z desfaz', onclick: () => this.apagarGuias() })));
    }
  }

  apagarGuias() {
    const ids = this._guias().filter(e => C.editavel(this.editor, e)).map(e => e.id);
    if (!ids.length) return;
    this.executar(C.cmdRemover(ids, 'Apagar linhas de construção'));
    this.dica(`${ids.length} linha(s) de construção apagada(s) (Ctrl+Z desfaz)`);
    if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
  }

  criarGuia(a, b, afastamento = null) {
    const ent = C.solidoDeArestas([a, b], {
      nome: 'Guia', camada: 'Referência',
      atributos: { tipo: 'construcao', exportar: false, comprimento: C.dist(a, b), ...(afastamento !== null ? { afastamento: Math.round(afastamento * 100) / 100 } : {}) },
    });
    this.executar(C.cmdAdicionar(ent, 'Linha de construção'));
    this.reiniciar();
    this.dica(FerramentaMedir.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.a = null; this.b = null; this.atual = null; this.eixo = null; this.aresta = null;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    const a = this.a, b = this.b || this.atual;
    if (a) g.add(C.gPonto(a, C.CORES.desenho));
    if (!a) { if (this.atual) g.add(C.gPonto(this.atual, C.CORES.desenho)); this.previa(g); return; }
    if (!b) { this.previa(g); return; }

    if (this.aresta) {
      // a guia paralela pelo ponto: a aresta de base, o afastamento perpendicular e a guia
      const gp = this.guiaParalela(b), pe = C.sub(b, this._afastamento(b));
      g.add(C.gLinha([this.aresta.a, this.aresta.b], C.CORES.cota));
      if (gp) g.add(C.gLinha([gp[0], gp[1]], C.CORES.desenho, { tracejada: true }));
      g.add(C.gLinha([pe, b], C.CORES.cota));
      g.add(C.gPonto(b, C.CORES.desenho));
      const dd = gp ? gp[2] : 0;
      this.medida(`afastamento da aresta ${formatar(dd)}`);
      g.add(C.gRotulo(formatar(dd), C.meio(pe, b), '#b8860b'));
      this.previa(g);
      return;
    }

    g.add(C.gLinha([a, b], C.CORES.cota));
    g.add(C.gPonto(b, C.CORES.desenho));

    const d = C.sub(b, a);
    const dx = Math.abs(d[0]), dy = Math.abs(d[1]), dz = Math.abs(d[2]);
    // projeções, desenhadas em degrau para dar a leitura de X, Y e Z
    const p1 = [b[0], a[1], a[2]];
    const p2 = [b[0], b[1], a[2]];
    g.add(C.gLinha([a, p1], C.EIXOS.x.cor, { tracejada: true }));
    g.add(C.gLinha([p1, p2], C.EIXOS.y.cor, { tracejada: true }));
    g.add(C.gLinha([p2, b], C.EIXOS.z.cor, { tracejada: true }));

    const total = C.comp(d);
    const texto = `${formatar(total)}   ΔX ${formatar(dx)} · ΔY ${formatar(dy)} · ΔZ ${formatar(dz)}`;
    this.medida(texto);
    g.add(C.gRotulo(formatar(total), C.meio(a, b), '#b8860b'));
    if (dx > 1) g.add(C.gRotulo('X ' + formatar(dx), C.meio(a, p1), '#c0392b'));
    if (dy > 1) g.add(C.gRotulo('Y ' + formatar(dy), C.meio(p1, p2), '#2e8b57'));
    if (dz > 1) g.add(C.gRotulo('Z ' + formatar(dz), C.meio(p2, b), '#0b3d91'));
    this.previa(g);
  }
}

export default FerramentaMedir;
