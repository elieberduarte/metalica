// Escalar: alças na caixa envolvente da seleção.
//
// As alças de canto escalam uniformemente; as alças do meio de cada face escalam
// só naquele eixo. A alça oposta à escolhida fica parada, como no SketchUp.
// Digitar "2" aplica o fator 2; digitar "2000" ou "2,5m" (com unidade ou acima de
// 50) é lido como a medida final do lado que está sendo puxado; "2;1;1" dá um
// fator por eixo.

import { Ferramenta, paraMilimetros, listaDeMedidas, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaEscalar extends Ferramenta {
  static id = 'escalar';
  static nome = 'Escalar';
  static atalho = 'E';
  static grupo = 'edicao';
  static dica = 'Selecione e clique numa alça da caixa';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 20V9h11v11Z"/><path d="M9 4h11v11"/><path d="M13.5 10.5 20 4"/><rect x="2.6" y="18.6" width="2.8" height="2.8"/><rect x="18.6" y="2.6" width="2.8" height="2.8"/></svg>`;

  ativar() {
    this.ids = C.idsSelecionados(this.editor);
    this.caixa = C.caixaDe(this.documento, this.ids);
    this.alca = null;
    this.ancora = null;
    this.fatores = [1, 1, 1];
    this.dica(this.ids.length ? FerramentaEscalar.dica
                              : 'Nada selecionado: selecione o que escalar');
    this.medida('');
    this.desenhar();
  }

  desativar() { this.reiniciar(); }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    if (!p) return;
    if (!this.alca) { this.desenhar(); return; }
    this.fatores = this.fatoresDe(p);
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.alca) {
      this.ids = C.idsSelecionados(this.editor);
      this.caixa = C.caixaDe(this.documento, this.ids);
      if (!this.ids.length) { this.dica('Selecione o que escalar antes.'); return; }
      const a = this.alcaMaisProxima(p.ponto);
      if (!a) { this.dica('Clique mais perto de uma das alças da caixa.'); return; }
      this.alca = a;
      this.ancora = this.pontoDaAlca(a.sinais.map(s => -s));
      this.fatores = [1, 1, 1];
      this.dica(a.uniforme ? 'Mova para escalar, ou digite o fator / a medida'
                           : `Escala no eixo ${a.nome}: mova, ou digite o fator / a medida`);
      this.desenhar();
      return;
    }
    this.aplicar(this.fatoresDe(p));
  }

  onValor(texto) {
    if (!this.alca) return false;
    const t = String(texto).trim();
    if (t.includes(';')) {
      const m = listaDeMedidas(t);
      if (m.length >= 3 && m.every(v => isFinite(v) && v !== 0)) {
        this.aplicar([m[0], m[1], m[2]]);
        return true;
      }
      return false;
    }
    const bruto = parseFloat(t.replace(',', '.'));
    const temUnidade = /(mm|cm|m|"|pol)\s*$/i.test(t);
    const tam = this.tamanhos();
    const eixos = this.alca.uniforme ? [0, 1, 2] : [this.alca.eixo];
    let f;
    if (temUnidade || Math.abs(bruto) > 50) {
      const alvo = paraMilimetros(t);
      const ref = tam[this.alca.uniforme ? this.maiorEixo() : this.alca.eixo];
      if (!isFinite(alvo) || !ref) return false;
      f = alvo / ref;
    } else {
      if (!isFinite(bruto) || bruto === 0) return false;
      f = bruto;
    }
    const fat = [1, 1, 1];
    for (const e of eixos) fat[e] = f;
    this.aplicar(fat);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.alca) { this.aplicar(this.fatores); return true; }
    return false;
  }

  cancelar() {
    if (this.alca) { this.alca = null; this.ancora = null; this.fatores = [1, 1, 1];
                     this.dica(FerramentaEscalar.dica); this.desenhar(); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  tamanhos() {
    const { min, max } = this.caixa;
    return [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
  }

  maiorEixo() {
    const t = this.tamanhos();
    return t.indexOf(Math.max(...t));
  }

  /** Ponto da caixa para uma combinação de sinais (-1, 0, +1) por eixo. */
  pontoDaAlca(s) {
    const { min, max, centro } = this.caixa;
    return [0, 1, 2].map(i => s[i] < 0 ? min[i] : s[i] > 0 ? max[i] : centro[i]);
  }

  /** Oito cantos e seis meios de face. */
  alcas() {
    const lista = [];
    for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
      lista.push({ sinais: [x, y, z], uniforme: true, eixo: -1, nome: 'XYZ' });
    }
    const nomes = ['X', 'Y', 'Z'];
    for (let e = 0; e < 3; e++) for (const s of [-1, 1]) {
      const sinais = [0, 0, 0];
      sinais[e] = s;
      lista.push({ sinais, uniforme: false, eixo: e, nome: nomes[e] });
    }
    return lista;
  }

  alcaMaisProxima(ponto) {
    const t = this.tamanhos();
    const diag = Math.hypot(t[0], t[1], t[2]) || 1000;
    let melhor = null, dmin = diag * 0.25;
    for (const a of this.alcas()) {
      const d = C.dist(ponto, this.pontoDaAlca(a.sinais));
      if (d < dmin) { dmin = d; melhor = a; }
    }
    return melhor;
  }

  /** Fator pela posição do cursor ao longo da reta âncora → alça (a diagonal, no canto). */
  fatoresDe(p) {
    const alvo = this.pontoDaAlca(this.alca.sinais);
    const vet = C.sub(alvo, this.ancora);
    const L = C.comp(vet);
    const fat = [1, 1, 1];
    if (L < 1e-9) return fat;
    let f = C.distanciaNaReta(this.editor, p, this.ancora, vet) / L;
    if (!isFinite(f)) f = 1;
    for (const e of (this.alca.uniforme ? [0, 1, 2] : [this.alca.eixo])) fat[e] = f;
    return fat;
  }

  transformador(fat) {
    const a = this.ancora;
    const fp = (q) => [a[0] + (q[0] - a[0]) * fat[0],
                       a[1] + (q[1] - a[1]) * fat[1],
                       a[2] + (q[2] - a[2]) * fat[2]];
    const fv = (v) => [v[0] * fat[0], v[1] * fat[1], v[2] * fat[2]];
    return { fp, fv };
  }

  aplicar(fat) {
    if (!this.ids.length || fat.some(f => !isFinite(f) || Math.abs(f) < 1e-6)) {
      this.reiniciar(); return;
    }
    if (fat.every(f => Math.abs(f - 1) < 1e-9)) { this.reiniciar(); return; }
    const { fp, fv } = this.transformador(fat);
    const cmds = [];
    for (const id of this.ids) {
      const ent = this.documento.get(id);
      if (ent) cmds.push(C.cmdAlterar(id, C.camposTransformados(ent, fp, fv), 'Escalar'));
    }
    this.executar(C.cmdComposto(cmds, 'Escalar'));
    this.caixa = C.caixaDe(this.documento, this.ids);
    this.reiniciar();
    this.dica(FerramentaEscalar.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.alca = null; this.ancora = null; this.fatores = [1, 1, 1];
    this.limparPrevia();
    this.medida('');
  }

  arestasDaCaixa(min, max) {
    const v = [];
    for (const z of [min[2], max[2]]) for (const y of [min[1], max[1]]) for (const x of [min[0], max[0]]) v.push([x, y, z]);
    const l = [[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]];
    return l.map(([a, b]) => [v[a], v[b]]);
  }

  desenhar() {
    this.limparPrevia();
    if (!this.ids.length) return;
    const g = C.grupo();
    const { min, max } = this.caixa;
    for (const [a, b] of this.arestasDaCaixa(min, max)) g.add(C.gLinha([a, b], C.CORES.guia));
    for (const a of this.alcas()) {
      const p = this.pontoDaAlca(a.sinais);
      const ativa = this.alca && a.sinais.join() === this.alca.sinais.join();
      g.add(C.gPonto(p, ativa ? C.CORES.aviso : C.CORES.desenho));
    }
    if (this.alca) {
      const { fp } = this.transformador(this.fatores);
      const nmin = fp(min), nmax = fp(max);
      for (const [a, b] of this.arestasDaCaixa(
            [Math.min(nmin[0], nmax[0]), Math.min(nmin[1], nmax[1]), Math.min(nmin[2], nmax[2])],
            [Math.max(nmin[0], nmax[0]), Math.max(nmin[1], nmax[1]), Math.max(nmin[2], nmax[2])])) {
        g.add(C.gLinha([a, b], C.CORES.ok));
      }
      g.add(C.gPonto(this.ancora, C.CORES.aviso));
      const t = this.tamanhos();
      const texto = this.alca.uniforme
        ? `${C.num(this.fatores[0], 3)} ×  (${formatar(t[this.maiorEixo()] * this.fatores[this.maiorEixo()])})`
        : `${this.alca.nome}: ${C.num(this.fatores[this.alca.eixo], 3)} ×  (${formatar(t[this.alca.eixo] * this.fatores[this.alca.eixo])})`;
      this.medida(texto);
      g.add(C.gRotulo(texto, this.caixa.centro));
    }
    this.previa(g);
  }
}

export default FerramentaEscalar;
