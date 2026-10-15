// Mover: desloca a seleção; com Ctrl, copia.
//
// Depois de uma cópia, digitar "*5" faz cinco cópias igualmente espaçadas na
// mesma direção e "/3" divide o mesmo deslocamento em três — o array linear do
// SketchUp. A medida digitada aceita um comprimento ("3000", "3,5m") na direção
// corrente, ou um deslocamento completo "dx;dy;dz".
// Logo depois de mover ou copiar (e do "*5"/"/3"), digitar outra distância corrige o último movimento na mesma direção
// — o espaçamento das cópias, no array — como no SketchUp; só enquanto o último comando da pilha for o do Mover.

import { Ferramenta, paraMilimetros, listaDeMedidas, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaMover extends Ferramenta {
  static id = 'mover';
  static nome = 'Mover';
  static atalho = 'M';
  static grupo = 'edicao';
  static dica = 'Selecione e clique no ponto de origem do movimento';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 3v18M3 12h18"/><path d="M12 3 9.9 5.1M12 3l2.1 2.1M12 21l-2.1-2.1M12 21l2.1-2.1M3 12l2.1-2.1M3 12l2.1 2.1M21 12l-2.1-2.1M21 12l-2.1 2.1"/></svg>`;

  ativar() {
    this.base = null;
    this.delta = [0, 0, 0];
    this.eixo = null;
    this.copiar = false;
    this.ultimoArray = null;   // { delta, ids, n, modo, cmd }
    this.ultimo = null;        // o último Mover: { delta, ids, cmd }
    this.ids = C.idsSelecionados(this.editor);
    this.dica(this.ids.length ? FerramentaMover.dica
                              : 'Nada selecionado: selecione o que mover (barra de espaço)');
    this.medida('');
  }

  desativar() { this.reiniciar(); this.ultimoArray = null; }

  // ------------------------------------------------------------- eventos

  onMover(p, ev) {
    C.sincronizarEixo(this);
    if (!p || !this.base) return;
    if (ev && ev.ctrlKey) this.copiar = true;
    let alvo = C.copiar(p.ponto);
    if (this.eixo) alvo = C.projetarNoEixo(this.base, alvo, this.eixo);
    this.delta = C.sub(alvo, this.base);
    this.desenhar();
  }

  onPonto(p, ev) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (!this.base) {
      this.ids = C.idsSelecionados(this.editor);
      if (!this.ids.length) {
        this.dica('Nada selecionado: selecione o que mover antes.');
        return;
      }
      this.base = C.copiar(p.ponto);
      C.ancorar(this.editor, this.base);
      this.ultimoArray = null;
      this.ultimo = null;
      this.copiar = !!(ev && ev.ctrlKey);
      this.dica('Clique no destino, digite a distância, ou Ctrl para copiar');
      this.desenhar();
      return;
    }
    let alvo = C.copiar(p.ponto);
    if (this.eixo) alvo = C.projetarNoEixo(this.base, alvo, this.eixo);
    this.aplicar(C.sub(alvo, this.base));
  }

  onValor(texto) {
    const t = String(texto).trim();
    if (this.ultimoArray) {
      const arr = t.match(/^([*/xX])\s*(\d+)$/);
      if (arr) { this.arranjar(arr[1].toLowerCase() === '/' ? 'dividir' : 'multiplicar',
                                parseInt(arr[2], 10)); return true; }
    }
    if (!this.base) return this._corrigirUltimo(t);
    if (t.includes(';')) {
      const m = listaDeMedidas(t);
      if (m.length >= 3 && m.every(isFinite)) { this.aplicar([m[0], m[1], m[2]]); return true; }
      return false;
    }
    const d = paraMilimetros(t);
    if (!isFinite(d) || d === 0) return false;
    let dir = this.eixo ? C.EIXOS[this.eixo].vetor
            : (C.comp(this.delta) > 1e-6 ? this.delta : null);
    if (!dir) return false;
    dir = C.normalizar(dir);
    if (this.eixo && C.comp(this.delta) > 1e-6 && C.dot(this.delta, dir) < 0) dir = C.mul(dir, -1);
    this.aplicar(C.mul(dir, d));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (this.ultimoArray && (ev.key === '*' || ev.key === '/') &&
        C.abrirCaixaDeMedidas(this.editor, ev.key)) return true;
    if (C.teclaDeEixo(this, ev)) { this.desenhar(); return true; }
    if (ev.key === 'Control' && !ev.repeat) { this.copiar = !this.copiar; this.desenhar(); return true; }
    if (ev.key === 'Enter' && this.base && C.comp(this.delta) > 1e-6) {
      this.aplicar(this.delta); return true;
    }
    return false;
  }

  cancelar() {
    if (this.base) { this.reiniciar(); this.dica(FerramentaMover.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  entidades() {
    return this.ids.map(id => this.documento && this.documento.get(id)).filter(Boolean);
  }

  /** Comandos para mover ou copiar a seleção por um deslocamento. */
  comandosPara(delta, copias = 1, rotulo = 'Mover') {
    const fp = (k) => (q) => C.add(q, C.mul(delta, k));
    const fv = (v) => v;
    const cmds = [];
    // os marcadores de furo vão junto com a peça deles; a peça bloqueada não anda (só é copiada)
    const { pecas, bloqueadas } = C.pecasParaTransformar(this.documento, this.entidades(), copias > 0);
    this.bloqueadas = bloqueadas;
    if (copias <= 0) {
      for (const ent of pecas) {
        cmds.push(C.cmdAlterar(ent.id, C.camposTransformados(ent, fp(1), fv), rotulo));
      }
      return { cmds, novos: [] };
    }
    const novos = [];
    for (let k = 1; k <= copias; k++) {
      const lote = C.copiasTransformadas(pecas, fp(k), fv);
      novos.push(...lote.map(c => c.id));
      if (lote.length) cmds.push(C.cmdAdicionar(lote, rotulo));
    }
    return { cmds, novos };
  }

  aplicar(delta) {
    if (!this.ids.length || C.comp(delta) < 1e-6) { this.reiniciar(); return; }
    if (this.copiar) {
      const { cmds, novos } = this.comandosPara(delta, 1, 'Copiar');
      const cmd = C.cmdComposto(cmds, 'Copiar');
      this.executar(cmd);
      this.ultimoArray = { delta: C.copiar(delta), ids: this.ids.slice(), criadas: novos, n: 1, modo: 'multiplicar', cmd };
      this.ultimo = null;
      this.reiniciar();
      this.medida(`cópia a ${formatar(C.comp(delta))}`);
      this.dica('Cópia feita — digite "*5" para repetir ou "/3" para dividir');
      return;
    }
    const { cmds } = this.comandosPara(delta, 0, 'Mover');
    const cmd = cmds.length ? C.cmdComposto(cmds, 'Mover') : null;
    if (cmd) this.executar(cmd);
    C.avisarBloqueadas(this.editor, this.bloqueadas);
    this.ultimoArray = null;
    this.ultimo = cmd ? { delta: C.copiar(delta), ids: this.ids.slice(), cmd } : null;
    this.reiniciar();
    this.dica(cmd ? `Movido ${formatar(C.comp(delta))} — digite outra distância para corrigir` : FerramentaMover.dica);
  }

  /** Array linear: refaz a última cópia como n cópias. */
  arranjar(modo, n) {
    if (!this.ultimoArray || n < 1) return;
    const { delta, ids } = this.ultimoArray;
    if (!this._ehOUltimo(this.ultimoArray.cmd)) { this.ultimoArray = null; this.dica('Outro comando veio depois da cópia: faça a cópia de novo para repetir'); return; }
    if (this.editor && typeof this.editor.desfazer === 'function') this.editor.desfazer();
    this.ids = ids.slice();
    const passo = modo === 'dividir' ? C.mul(delta, 1 / n) : delta;
    const copias = n;
    const { cmds, novos } = this.comandosPara(passo, copias,
      modo === 'dividir' ? `Dividir em ${n}` : `Repetir ${n} vezes`);
    const cmd = C.cmdComposto(cmds, modo === 'dividir' ? 'Dividir cópia' : 'Repetir cópia');
    this.executar(cmd);
    this.ultimoArray = { delta, ids, criadas: novos, n, modo, cmd };
    this.dica(`${copias} cópias. Continue digitando "*n" ou "/n" para ajustar.`);
    this.medida(`${copias} × ${formatar(C.comp(passo))}`);
  }

  /** O comando `cmd` ainda é o último da pilha (nada veio depois dele)? */
  _ehOUltimo(cmd) {
    const p = this.editor && this.editor.pilha;
    return !!(cmd && p && Array.isArray(p.feitos) && p.feitos[p.feitos.length - 1] === cmd);
  }

  /** A distância digitada logo depois de mover ou copiar: refaz o último na mesma direção com ela. */
  _corrigirUltimo(t) {
    if (t.includes(';')) return false;
    const d = paraMilimetros(t);
    if (!isFinite(d) || d <= 0) return false;
    const arr = this.ultimoArray, mov = this.ultimo;
    const ult = arr || mov;
    if (!ult || !this._ehOUltimo(ult.cmd)) return false;
    const dir = C.normalizar(ult.delta);
    this.editor.desfazer();
    this.ids = ult.ids.slice();
    if (arr) {
      // no array: a distância nova é o passo (*n) ou o total dividido (/n)
      const delta = C.mul(dir, d), passo = arr.modo === 'dividir' ? C.mul(delta, 1 / arr.n) : delta;
      const { cmds, novos } = this.comandosPara(passo, arr.n, 'Copiar');
      const cmd = C.cmdComposto(cmds, arr.n > 1 ? 'Repetir cópia' : 'Copiar');
      this.executar(cmd);
      this.ultimoArray = { ...arr, delta, criadas: novos, cmd };
      this.medida(`${arr.n} × ${formatar(C.comp(passo))}`);
      this.dica(`Cópia(s) refeita(s) a ${formatar(C.comp(passo))} — digite outra distância, "*n" ou "/n"`);
      return true;
    }
    const delta = C.mul(dir, d);
    const { cmds } = this.comandosPara(delta, 0, 'Mover');
    const cmd = C.cmdComposto(cmds, 'Mover');
    this.executar(cmd);
    this.ultimo = { ...mov, delta, cmd };
    this.medida(formatar(d));
    this.dica(`Movido ${formatar(d)} — digite outra distância para corrigir`);
    return true;
  }

  /** O fantasma da seleção (montado uma vez por operação). */
  _fantasmaAtual() {
    const chave = this.ids.join('|');
    if (!this._fantasma || this._fantasma.chave !== chave) this._fantasma = { chave, ...C.fantasmaDe(this.editor, this.ids) };
    return this._fantasma;
  }

  reiniciar() {
    C.desancorar(this.editor);
    this._fantasma = null;
    this.base = null;
    this.delta = [0, 0, 0];
    this.eixo = null;
    this.copiar = false;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    if (!this.base) return;
    const fim = C.add(this.base, this.delta);
    const g = C.grupo(
      C.gLinha([this.base, fim], this.eixo ? C.EIXOS[this.eixo].cor : C.CORES.desenho),
      C.gPonto(this.base, C.CORES.guia), C.gPonto(fim, C.CORES.desenho));
    // a própria peça, translúcida, no destino (o fantasma); a silhueta só para a que não tem objeto próprio (modelo grande)
    const f = this._fantasmaAtual();
    C.posicionarFantasma(f, (q) => C.add(q, this.delta), (v) => v);
    g.add(f.obj);
    for (const ent of this.entidades()) {
      if (f.ids.has(ent.id)) continue;
      const pts = C.pontosDaEntidade(ent).map(q => C.add(q, this.delta));
      if (ent.tipo === 'barra' && pts.length === 2) g.add(C.gLinha(pts, C.CORES.ok));
      else if (pts.length >= 3) g.add(C.gLinha(pts, C.CORES.ok, { fechada: ent.tipo === 'chapa' }));
    }
    const d = C.comp(this.delta);
    const texto = formatar(d) +
      (this.eixo ? '  eixo ' + C.EIXOS[this.eixo].nome : '') +
      (this.copiar ? '  ·  cópia' : '');
    this.medida(texto);
    g.add(C.gRotulo(texto, C.meio(this.base, fim)));
    this.previa(g);
  }
}

export default FerramentaMover;
