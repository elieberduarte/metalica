// Trena: distância entre dois pontos, com as projeções em X, Y e Z.
//
// O segundo clique congela a medida; Enter cria uma linha de construção entre os
// dois pontos (Sólido só de arestas, camada "Referência", `atributos.tipo =
// 'construcao'`), que serve de guia para o snap sem virar geometria do modelo.

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
    this.eixo = null;
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
      this.dica('Clique no segundo ponto');
      this.desenhar();
      return;
    }
    if (!this.b) {
      if (C.iguais(this.a, q, 1e-6)) return;
      this.b = q;
      this.dica('Enter cria a linha de construção · Esc limpa');
      this.desenhar();
      return;
    }
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
      if (this.a && b && !C.iguais(this.a, b, 1e-6)) { this.criarGuia(this.a, b); return true; }
    }
    return false;
  }

  onValor(texto) {
    // uma medida digitada estende o segundo ponto na direção corrente
    if (!this.a || this.b) return false;
    const d = paraMilimetros(texto);
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

  criarGuia(a, b) {
    const ent = C.solidoDeArestas([a, b], {
      nome: 'Guia', camada: 'Referência',
      atributos: { tipo: 'construcao', comprimento: C.dist(a, b) },
    });
    this.executar(C.cmdAdicionar(ent, 'Linha de construção'));
    this.reiniciar();
    this.dica(FerramentaMedir.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.a = null; this.b = null; this.atual = null; this.eixo = null;
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
