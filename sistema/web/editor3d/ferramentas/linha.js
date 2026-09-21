// Linha: sequência de segmentos encadeados, como no SketchUp.
//
// Cada clique fecha um segmento e começa o próximo do ponto final. Quando o
// contorno volta ao ponto inicial, o resultado é uma face; quando o usuário
// encerra com Enter ou duplo clique, fica só a polilinha (arestas vivas).

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaLinha extends Ferramenta {
  static id = 'linha';
  static nome = 'Linha';
  static atalho = 'L';
  static grupo = 'desenho';
  static dica = 'Clique para o primeiro ponto';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M6.8 17.2 17.2 6.8"/><circle cx="5.2" cy="18.8" r="1.8"/><circle cx="18.8" cy="5.2" r="1.8"/></svg>`;

  ativar() {
    this.pontos = [];
    this.atual = null;
    this.eixo = null;
    this.dir = null;
    this.dica(FerramentaLinha.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    this.atual = this.resolver(p.ponto);
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    const novo = this.resolver(p.ponto);
    if (!this.pontos.length) {
      this.pontos.push(novo);
      C.ancorar(this.editor, novo);
      this.dica('Clique para o próximo ponto ou digite o comprimento (Enter encerra)');
      this.desenhar();
      return;
    }
    const ultimo = this.pontos[this.pontos.length - 1];
    if (C.iguais(ultimo, novo, 0.5)) return;        // clique repetido: ignora
    this.acrescentar(novo);
  }

  onDuploClique() { this.encerrar(); }

  onValor(texto) {
    if (!this.pontos.length) return false;
    const partes = String(texto).split(';');
    const d = paraMilimetros(partes[0]);
    if (!isFinite(d) || d === 0) return false;
    const base = this.pontos[this.pontos.length - 1];
    let dir = this.eixo ? C.EIXOS[this.eixo].vetor
            : (this.dir && C.comp(this.dir) > 1e-6) ? this.dir : null;
    if (!dir) return false;
    if (this.eixo && this.dir && C.dot(this.dir, dir) < 0) dir = C.mul(dir, -1);
    this.acrescentar(C.add(base, C.mul(C.normalizar(dir), Math.abs(d))));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (C.teclaDeEixo(this, ev)) { this.desenhar(); return true; }
    if (ev.key === 'Enter' || ev.key === 'Return') { this.encerrar(); return true; }
    return false;
  }

  cancelar() {
    if (this.pontos.length) { this.reiniciar(); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  /** Aplica o travamento de eixo em relação ao último ponto confirmado. */
  resolver(ponto) {
    if (!this.pontos.length || !this.eixo) return C.copiar(ponto);
    return C.projetarNoEixo(this.pontos[this.pontos.length - 1], ponto, this.eixo);
  }

  acrescentar(ponto) {
    const primeiro = this.pontos[0];
    this.pontos.push(ponto);
    C.ancorar(this.editor, ponto);
    if (this.pontos.length >= 3 && C.iguais(primeiro, ponto, 1.0)) {
      this.pontos.pop();
      this.fecharFace();
      return;
    }
    this.dica('Clique para o próximo ponto ou digite o comprimento (Enter encerra)');
    this.desenhar();
  }

  fecharFace() {
    const ent = C.solidoDeContorno(this.pontos, { nome: 'Face', camada: this.camadaAtiva() });
    this.executar(C.cmdAdicionar(ent, 'Desenhar face'));
    this.reiniciar();
  }

  encerrar() {
    if (this.pontos.length >= 2) {
      const ent = C.solidoDeArestas(this.pontos, { nome: 'Linha', camada: this.camadaAtiva() });
      this.executar(C.cmdAdicionar(ent, 'Desenhar linha'));
    }
    this.reiniciar();
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.pontos = [];
    this.atual = null;
    this.dir = null;
    this.limparPrevia();
    this.medida('');
    this.dica(FerramentaLinha.dica);
  }

  camadaAtiva() {
    return (this.editor && this.editor.camadaAtiva) || 'Estrutura';
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.pontos.length) g.add(C.gLinha(this.pontos, C.CORES.desenho));
    for (const p of this.pontos) g.add(C.gPonto(p, C.CORES.desenho));

    if (this.pontos.length && this.atual) {
      const base = this.pontos[this.pontos.length - 1];
      this.dir = C.sub(this.atual, base);
      const d = C.comp(this.dir);
      const cor = this.eixo ? C.EIXOS[this.eixo].cor : C.CORES.desenho;
      g.add(C.gLinha([base, this.atual], cor));
      g.add(C.gPonto(this.atual, cor));
      if (this.pontos.length >= 2) {
        g.add(C.gLinha([this.atual, this.pontos[0]], C.CORES.guia, { tracejada: true }));
      }
      const texto = formatar(d) + (this.eixo ? '  eixo ' + C.EIXOS[this.eixo].nome : '');
      this.medida(texto);
      g.add(C.gRotulo(formatar(d), C.meio(base, this.atual)));
    } else if (this.atual) {
      g.add(C.gPonto(this.atual, C.CORES.desenho));
    }
    this.previa(g);
  }
}

export default FerramentaLinha;
