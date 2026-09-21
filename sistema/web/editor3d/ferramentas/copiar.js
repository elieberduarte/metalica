// Copiar e colar posicionado.
//
// Ao entrar, se há seleção, ela vai para a área de transferência do editor e o
// ponteiro passa a carregar a cópia: cada clique cola uma vez, no ponto apontado.
// Sem seleção, a ferramenta cola o que já estiver na área de transferência. O
// ponto de referência é o canto inferior da caixa envolvente do que foi copiado,
// de modo que colar sobre uma extremidade encaixa a cópia ali.

import { Ferramenta, listaDeMedidas, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

/** Área de transferência de reserva, quando o núcleo ainda não expõe a dele. */
let RESERVA = null;

function lerAreaTransferencia(editor) {
  const at = editor && editor.areaTransferencia;
  if (at && typeof at.ler === 'function') return at.ler();
  if (at && Array.isArray(at.entidades)) return at;
  if (Array.isArray(at)) return { entidades: at, base: null };
  return RESERVA;
}

function gravarAreaTransferencia(editor, conteudo) {
  RESERVA = conteudo;
  const at = editor && editor.areaTransferencia;
  if (at && typeof at.definir === 'function') { at.definir(conteudo); return; }
  if (editor) {
    try { editor.areaTransferencia = conteudo; } catch { /* só a reserva, então */ }
  }
}

export class FerramentaCopiar extends Ferramenta {
  static id = 'copiar';
  static nome = 'Copiar/Colar';
  static atalho = 'K';
  static grupo = 'edicao';
  static dica = 'Selecione para copiar, depois clique onde colar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<rect x="8.5" y="8.5" width="12" height="12" rx="1.5"/><path d="M15.5 5.5h-11a1 1 0 0 0-1 1v11"/></svg>`;

  ativar() {
    this.delta = [0, 0, 0];
    this.atual = null;
    this.coladas = 0;
    const ids = C.idsSelecionados(this.editor);
    if (ids.length) this.copiarSelecao(ids);
    this.conteudo = lerAreaTransferencia(this.editor);
    if (!this.conteudo || !this.conteudo.entidades || !this.conteudo.entidades.length) {
      this.dica('Área de transferência vazia: selecione algo e chame a ferramenta de novo.');
      this.medida('');
      return;
    }
    this.dica(`${this.conteudo.entidades.length} entidade(s) na área de transferência — ` +
              'clique onde colar, ou digite "dx;dy;dz"');
    this.medida('');
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    if (!p || !this.conteudo) return;
    this.atual = C.copiar(p.ponto);
    this.delta = C.sub(this.atual, this.conteudo.base);
    this.desenhar();
  }

  onPonto(p) {
    if (!p || !this.conteudo) return;
    this.colar(C.sub(C.copiar(p.ponto), this.conteudo.base));
  }

  onValor(texto) {
    if (!this.conteudo) return false;
    const t = String(texto).trim();
    if (t.includes(';')) {
      const m = listaDeMedidas(t);
      if (m.length >= 3 && m.every(isFinite)) { this.colar([m[0], m[1], m[2]]); return true; }
      return false;
    }
    const d = paraMilimetros(t);
    if (!isFinite(d) || !C.comp(this.delta)) return false;
    this.colar(C.mul(C.normalizar(this.delta), d));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.conteudo && C.comp(this.delta) > 0) {
      this.colar(this.delta); return true;
    }
    return false;
  }

  cancelar() {
    this.limparPrevia();
    this.medida('');
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  copiarSelecao(ids) {
    const entidades = ids.map(id => this.documento && this.documento.get(id))
                         .filter(Boolean)
                         .map(e => JSON.parse(JSON.stringify(e)));
    if (!entidades.length) return;
    const caixa = C.caixaDe(this.documento, ids);
    gravarAreaTransferencia(this.editor, { entidades, base: caixa.min });
  }

  colar(delta) {
    if (!this.conteudo) return;
    const fp = (q) => C.add(q, delta);
    const lote = this.conteudo.entidades.map(orig => {
      const c = C.clonarEntidade(orig);
      Object.assign(c, C.camposTransformados(orig, fp, (v) => v));
      return c;
    });
    if (!lote.length) return;
    this.executar(C.cmdAdicionar(lote, 'Colar'));
    this.coladas += 1;
    this.dica(`Colado ${this.coladas}× — clique de novo para repetir, Esc para sair`);
  }

  desenhar() {
    this.limparPrevia();
    if (!this.conteudo) return;
    const g = C.grupo();
    for (const ent of this.conteudo.entidades) {
      const pts = C.pontosDaEntidade(ent).map(q => C.add(q, this.delta));
      if (pts.length === 2) g.add(C.gLinha(pts, C.CORES.ok));
      else if (pts.length >= 3) g.add(C.gLinha(pts, C.CORES.ok, { fechada: true }));
      if (ent.tipo === 'solido' && ent.faces && ent.faces.length) {
        g.add(C.gMalha(ent.vertices.map(q => C.add(q, this.delta)), ent.faces, C.CORES.ok, 0.18));
      }
    }
    if (this.atual) g.add(C.gPonto(this.atual, C.CORES.desenho));
    this.medida(formatar(C.comp(this.delta)));
    this.previa(g);
  }
}

export default FerramentaCopiar;
