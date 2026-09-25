// Copiar com ponto de referência, como no AutoCAD.
//
// Ao entrar, se há seleção, ela vai para a área de transferência do editor. O primeiro
// clique é o ponto de referência (a base: um canto, um furo, uma extremidade da peça
// copiada); cada clique seguinte cola uma cópia com a base naquele ponto — vários
// cliques, várias cópias, todas medidas da mesma base. Também aceita a distância na
// direção do ponteiro ou "dx;dy;dz". Sem seleção, a ferramenta cola o que já estiver na
// área de transferência (a base pedida do mesmo jeito).

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
  static dica = 'Selecione, clique o ponto de referência e depois onde colar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<rect x="8.5" y="8.5" width="12" height="12" rx="1.5"/><path d="M15.5 5.5h-11a1 1 0 0 0-1 1v11"/></svg>`;

  ativar() {
    this.delta = [0, 0, 0];
    this.atual = null;
    this.base = null;                  // o ponto de referência: o primeiro clique
    this.coladas = 0;
    const ids = C.idsSelecionados(this.editor);
    if (ids.length) this.copiarSelecao(ids);
    this.conteudo = lerAreaTransferencia(this.editor);
    if (!this.conteudo || !this.conteudo.entidades || !this.conteudo.entidades.length) {
      this.dica('Área de transferência vazia: selecione algo e chame a ferramenta de novo.');
      this.medida('');
      return;
    }
    this.dica(`${this.conteudo.entidades.length} entidade(s) para copiar — clique o ponto de referência ` +
              '(um canto, furo ou extremidade da peça); Enter usa o canto da caixa dela');
    this.medida('');
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    if (!p || !this.conteudo) return;
    this.atual = C.copiar(p.ponto);
    if (!this.base) { this.desenharBase(); return; }
    this.delta = C.sub(this.atual, this.base);
    this.desenhar();
  }

  onPonto(p) {
    if (!p || !this.conteudo) return;
    if (!this.base) {
      this.definirBase(C.copiar(p.ponto));
      return;
    }
    this.colar(C.sub(C.copiar(p.ponto), this.base));
  }

  onValor(texto) {
    if (!this.conteudo) return false;
    const t = String(texto).trim();
    if (t.includes(';')) {
      const m = listaDeMedidas(t);
      if (m.length >= 3 && m.every(isFinite)) {
        if (!this.base) this.definirBase(this.baseDaCaixa());
        this.colar([m[0], m[1], m[2]]);
        return true;
      }
      return false;
    }
    const d = paraMilimetros(t);
    if (!isFinite(d) || !this.base || !C.comp(this.delta)) return false;
    this.colar(C.mul(C.normalizar(this.delta), d));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key !== 'Enter' || !this.conteudo) return false;
    if (!this.base) { this.definirBase(this.baseDaCaixa()); return true; }
    if (C.comp(this.delta) > 0) { this.colar(this.delta); return true; }
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

  /** O canto inferior da caixa do que foi copiado: a base quando o usuário não clica uma. */
  baseDaCaixa() {
    if (this.conteudo && this.conteudo.base) return C.copiar(this.conteudo.base);
    const pts = [];
    for (const ent of (this.conteudo ? this.conteudo.entidades : [])) pts.push(...C.pontosDaEntidade(ent));
    if (!pts.length) return [0, 0, 0];
    return [0, 1, 2].map(a => Math.min(...pts.map(q => q[a])));
  }

  definirBase(q) {
    this.base = q;
    this.delta = [0, 0, 0];
    this.limparPrevia();
    this.dica('Referência marcada — clique onde colar (cada clique cola uma cópia medida da referência), ' +
              'ou digite a distância na direção do ponteiro, ou "dx;dy;dz"; Esc sai');
    this.medida('');
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
    this.dica(`Colado ${this.coladas}× — clique de novo para outra cópia (sempre medida da mesma referência), Esc para sair`);
  }

  /** Antes da referência: só o ponto sob o ponteiro, para o usuário ver o snap. */
  desenharBase() {
    this.limparPrevia();
    if (this.atual) this.previa(C.grupo(C.gPonto(this.atual, C.CORES.desenho)));
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
    if (this.base) g.add(C.gPonto(this.base, C.CORES.desenho));
    if (this.atual) {
      g.add(C.gPonto(this.atual, C.CORES.desenho));
      if (this.base && C.comp(this.delta) > 0) g.add(C.gLinha([this.base, this.atual], C.CORES.desenho));
    }
    this.medida(formatar(C.comp(this.delta)));
    this.previa(g);
  }
}

export default FerramentaCopiar;
