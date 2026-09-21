// Polígono regular: centro, raio e número de lados, inscrito ou circunscrito.
//
// "Inscrito" é o polígono dentro do círculo de raio dado (o raio vai até o
// vértice); "circunscrito" é o polígono em volta dele (o raio vai até o meio do
// lado) — é o caso de porcas e cabeças de parafuso. A tecla Tab alterna.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaPoligono extends Ferramenta {
  static id = 'poligono';
  static nome = 'Polígono';
  static atalho = 'G';
  static grupo = 'desenho';
  static dica = 'Clique para o centro (Tab alterna inscrito/circunscrito)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 3.4 19.4 7.7v8.6L12 20.6 4.6 16.3V7.7Z"/><circle cx="12" cy="12" r="1.2"/></svg>`;

  ativar() {
    this.plano = null;
    this.centro = null;
    this.atual = null;
    this.raio = 0;
    this.dica(this.dicaInicial());
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  get lados() { return this.constructor.lados || 6; }
  get circunscrito() { return !!this.constructor.circunscrito; }

  dicaInicial() {
    return `Clique para o centro — ${this.lados} lados, ` +
           (this.circunscrito ? 'circunscrito' : 'inscrito') + ' (Tab alterna)';
  }

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
      this.dica('Clique para o raio ou digite o raio (ex.: 300, ou "8s" para os lados)');
      this.desenhar();
      return;
    }
    this.criar(C.dist(this.centro, C.noPlano(this.editor, p, this.plano)));
  }

  onValor(texto) {
    const t = String(texto).trim().toLowerCase();
    const ml = t.match(/^(\d+)\s*(s|l|lados?)$/);
    if (ml) {
      this.constructor.lados = Math.max(3, Math.min(360, parseInt(ml[1], 10)));
      this.dica(this.dicaInicial());
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
    if (ev.key === 'Tab') {
      this.constructor.circunscrito = !this.constructor.circunscrito;
      this.dica(this.dicaInicial());
      this.desenhar();
      return true;
    }
    if (ev.key === 'Enter' && this.centro && this.raio > 0) { this.criar(this.raio); return true; }
    return false;
  }

  cancelar() {
    if (this.centro) { this.reiniciar(); this.dica(this.dicaInicial()); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  contorno(raio) {
    const n = this.lados;
    // circunscrito: o raio informado é o apótema, então o raio dos vértices cresce
    const rv = this.circunscrito ? raio / Math.cos(Math.PI / n) : raio;
    const giro = this.circunscrito ? Math.PI / n : 0;
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = (2 * Math.PI * i) / n + giro;
      pts.push(C.para3d(this.plano, rv * Math.cos(a), rv * Math.sin(a)));
    }
    return pts;
  }

  criar(raio) {
    if (!isFinite(raio) || raio <= 1e-6) return;
    const ent = C.solidoDeContorno(this.contorno(raio), {
      nome: 'Polígono',
      camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura',
      atributos: { forma: 'poligono', raio, lados: this.lados,
                   ajuste: this.circunscrito ? 'circunscrito' : 'inscrito' },
    });
    this.executar(C.cmdAdicionar(ent, 'Desenhar polígono'));
    this.reiniciar();
    this.dica(this.dicaInicial());
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
    const texto = `${this.lados} lados · raio ${formatar(r)} · ` +
                  (this.circunscrito ? 'circunscrito' : 'inscrito');
    this.medida(texto);
    g.add(C.gRotulo(`R ${formatar(r)}`, C.meio(this.centro, pts[0])));
    this.previa(g);
  }
}

FerramentaPoligono.lados = 6;
FerramentaPoligono.circunscrito = false;

export default FerramentaPoligono;
