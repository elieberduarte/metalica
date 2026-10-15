// Plano de trabalho (F11 do levantamento de 14/10 — o "Work plane" do Tekla, os eixos do SketchUp): desenhar na água da
// cobertura, na fachada, num plano qualquer.
//
// Clique numa face (a telha, a mesa da terça): o plano de trabalho passa a ser o dela. Ou clique três pontos soltos: o
// plano por eles. Com o plano definido, o ponto que não pega nada cai nele (não no chão), e a inferência oferece as duas
// direções dele a partir da âncora — ao longo (na horizontal do plano) e atravessado (o caimento); Shift trava a que
// estiver acesa. A barra de baixo mostra o plano ("água 4,24 %"). Z ou Delete voltam ao chão; Esc sai.

import { Ferramenta } from './base.js';
import * as C from './_comum.js';

/** O plano {origem, normal, ex, ey, nome}: ex na horizontal do plano, ey no caimento (ou x e y, no plano deitado). */
export function planoDeTrabalho(origem, normal) {
  let n = C.normalizar(normal);
  if (n[2] < -1e-9) n = C.mul(n, -1);                                 // a normal para cima (ou para fora, na vertical)
  const horiz = Math.hypot(n[0], n[1]);
  let ex, ey, nome;
  if (horiz < 1e-6) { ex = [1, 0, 0]; ey = [0, 1, 0]; nome = `horizontal em ${(origem[2] / 1000).toFixed(2).replace('.', ',')} m`; }
  else {
    ex = C.normalizar(C.cross([0, 0, 1], n));                         // a horizontal do plano
    ey = C.normalizar(C.cross(n, ex));                                 // o caimento (sobe)
    if (Math.abs(n[2]) < 1e-6) nome = 'vertical';
    else nome = `água ${(horiz / Math.abs(n[2]) * 100).toFixed(2).replace('.', ',')} %`;
  }
  return { origem: C.copiar(origem), normal: n, ex, ey, nome };
}

export class FerramentaPlano extends Ferramenta {
  static id = 'plano';
  static nome = 'Plano de trabalho';
  static atalho = '';
  static grupo = 'desenho';
  static dica = 'Clique numa face para desenhar no plano dela (ou três pontos soltos) · Z ou Delete voltam ao chão';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 15 10 7h11l-7 8Z"/><path d="M8 11h11M6 13h11" stroke-dasharray="1.5 1.5"/><path d="M12 15v6"/></svg>`;

  ativar() {
    this.pontos = [];
    const pl = this.editor.inferencia && this.editor.inferencia.planoTrabalho;
    this.dica(pl ? `Plano de trabalho: ${pl.nome}. ${FerramentaPlano.dica}` : FerramentaPlano.dica);
    this.desenhar();
  }

  desativar() { this.limparPrevia(); }
  cancelar() { if (this.pontos.length) { this.pontos = []; this.limparPrevia(); return; } C.voltarParaSelecao(this.editor); }

  definir(plano) {
    const inf = this.editor.inferencia;
    if (inf) inf.planoTrabalho = plano;
    // o plano do editor (o da Chapa e das ferramentas de desenho no ponto solto)
    this.editor.planoTrabalho = plano ? { origem: plano.origem, normal: plano.normal } : { origem: [0, 0, 0], normal: [0, 0, 1] };
    if (typeof this.editor._atualizarTrava === 'function') this.editor._atualizarTrava();
    this.pontos = [];
    this.dica(plano ? `Plano de trabalho: ${plano.nome} — o ponto solto cai nele; as direções dele aparecem na inferência. Z ou Delete voltam ao chão`
                    : 'De volta ao chão (o plano horizontal na altura da âncora)');
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    const t = p.tela, s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    if (!this.pontos.length && s && s.entidade && s.normal) {
      this.definir(planoDeTrabalho(s.ponto, s.normal));
      return;
    }
    this.pontos.push(C.copiar(p.ponto));
    if (this.pontos.length < 3) { this.dica(`Ponto ${this.pontos.length} de 3 do plano`); this.desenhar(); return; }
    const [a, b, c] = this.pontos;
    const n = C.cross(C.sub(b, a), C.sub(c, a));
    if (C.comp(n) < 1e-6) { this.pontos = []; this.dica('Os três pontos estão alinhados: escolha outros'); return; }
    this.definir(planoDeTrabalho(a, n));
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Delete' || ev.key === 'Backspace' || String(ev.key).toLowerCase() === 'z') { this.definir(null); return true; }
    return false;
  }

  desenhar() {
    this.limparPrevia();
    const pl = this.editor.inferencia && this.editor.inferencia.planoTrabalho;
    const g = C.grupo();
    for (const q of this.pontos) g.add(C.gPonto(q, '#7c3aed'));
    if (pl) {
      const s = 2500, q = (a, b) => C.add(pl.origem, C.add(C.mul(pl.ex, a), C.mul(pl.ey, b)));
      g.add(C.gPoligono([q(-s, -s), q(s, -s), q(s, s), q(-s, s)], '#7c3aed', 0.08));
      for (let k = -s; k <= s; k += 500) {
        g.add(C.gLinha([q(k, -s), q(k, s)], '#7c3aed', { tracejada: true }));
        g.add(C.gLinha([q(-s, k), q(s, k)], '#7c3aed', { tracejada: true }));
      }
      g.add(C.gRotulo(pl.nome, pl.origem, '#7c3aed'));
    }
    this.previa(g);
  }
}

export default FerramentaPlano;
