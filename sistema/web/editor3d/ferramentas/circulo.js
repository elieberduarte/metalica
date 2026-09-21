// Círculo: centro e raio, aproximado por um polígono regular.
//
// Como no SketchUp, o círculo é um polígono de N lados (padrão 24). Digitar um
// número define o raio; digitar "24s" (ou "24l") troca o número de lados e vale
// para os próximos círculos.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaCirculo extends Ferramenta {
  static id = 'circulo';
  static nome = 'Círculo';
  static atalho = 'C';
  static grupo = 'desenho';
  static dica = 'Clique para o centro';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="1.3"/><path d="M12 12h8.2" stroke-dasharray="2 2"/></svg>`;

  ativar() {
    if (!this.constructor.lados) this.constructor.lados = 24;
    this.plano = null;
    this.centro = null;
    this.atual = null;
    this.raio = 0;
    this.dica(`Clique para o centro (${this.constructor.lados} lados)`);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  get lados() { return this.constructor.lados || 24; }

  onMover(p) {
    if (!p) return;
    if (!this.centro) { this.atual = C.copiar(p.ponto); this.desenhar(); return; }
    this.atual = C.noPlano(this.editor, p, this.plano);
    this.raio = C.dist(this.centro, this.atual);
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.centro) {
      this.plano = C.planoDoPonto(this.editor, p);
      this.centro = C.copiar(p.ponto);
      this.plano.origem = this.centro;
      C.ancorar(this.editor, this.centro);
      this.dica('Clique para o raio ou digite o raio (ex.: 500, ou "24s" para os lados)');
      this.desenhar();
      return;
    }
    const q = C.noPlano(this.editor, p, this.plano);
    this.criar(C.dist(this.centro, q));
  }

  onValor(texto) {
    const t = String(texto).trim().toLowerCase();
    const ml = t.match(/^(\d+)\s*(s|l|lados?)$/);
    if (ml) {
      this.constructor.lados = Math.max(3, Math.min(360, parseInt(ml[1], 10)));
      this.dica(`Lados: ${this.constructor.lados}`);
      this.desenhar();
      return true;
    }
    if (!this.centro) return false;
    const r = paraMilimetros(t);
    if (!isFinite(r) || r <= 0) return false;
    this.criar(r);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.centro && this.raio > 0) { this.criar(this.raio); return true; }
    return false;
  }

  cancelar() {
    if (this.centro) { this.reiniciar(); this.dica(FerramentaCirculo.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  contorno(raio) {
    const n = this.lados;
    const pts = [];
    // o primeiro vértice fica sobre o eixo local X, para que o raio digitado
    // coincida com a distância do centro ao vértice (raio circunscrito)
    for (let i = 0; i < n; i++) {
      const a = (2 * Math.PI * i) / n;
      pts.push(C.para3d(this.plano, raio * Math.cos(a), raio * Math.sin(a)));
    }
    return pts;
  }

  criar(raio) {
    if (!isFinite(raio) || raio <= 1e-6) return;
    const ent = C.solidoDeContorno(this.contorno(raio), {
      nome: 'Círculo',
      camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura',
      atributos: { forma: 'circulo', raio, lados: this.lados },
    });
    this.executar(C.cmdAdicionar(ent, 'Desenhar círculo'));
    this.reiniciar();
    this.dica(FerramentaCirculo.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.centro = null; this.atual = null; this.plano = null; this.raio = 0;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (!this.centro) {
      if (this.atual) g.add(C.gPonto(this.atual, C.CORES.desenho));
      this.previa(g);
      return;
    }
    const r = this.raio || 1;
    const pts = this.contorno(r);
    g.add(C.gPoligono(pts));
    g.add(C.gLinha(pts, C.CORES.desenho, { fechada: true }));
    g.add(C.gPonto(this.centro, C.CORES.desenho));
    if (this.atual) g.add(C.gLinha([this.centro, this.atual], C.CORES.guia, { tracejada: true }));
    const texto = `raio ${formatar(r)}  ·  ${this.lados} lados`;
    this.medida(texto);
    g.add(C.gRotulo(`R ${formatar(r)}`, C.meio(this.centro, pts[0])));
    this.previa(g);
  }
}

FerramentaCirculo.lados = 24;

export default FerramentaCirculo;
