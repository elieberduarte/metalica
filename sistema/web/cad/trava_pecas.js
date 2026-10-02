// Trava da peça gerada (regra R5, combinada com o usuário em 02/10): nos desenhos que o sistema gera do 3D —
// detalhamento, "Detalhe – marca" e pranchas —, a geometria da peça (vista, contorno, furo) é do 3D e não se edita
// no desenho: furo apagado ou contorno esticado ali não voltava ao 3D e sumia na próxima atualização. Para mudar a
// peça: "Editar peça" (o ambiente de edição, faixa EDITANDO … Concluir, que leva ao 3D). Continua livre o que é
// apresentação: mover, copiar ou apagar a célula inteira, cotas, textos, chamadas, a aparência (cor, espessura) e
// o que se desenha por cima. A camada travada (a REFERENCIA do Editar chapa, o arquitetônico) também passa a valer
// para tudo: Ctrl+A, duplo clique na camada e "Mesma peça" selecionavam e apagavam o travado.
//
// Toda edição passa por `executar` (cad.js), que pergunta aqui antes.

import { ComandoAdicionar, ComandoAlterar, ComandoComposto, ComandoRemover, ComandoSubstituir } from './nucleo/comandos.js';

/** Camadas de anotação: livres mesmo no desenho gerado. */
const LIVRES = new Set(['COTA', 'TEXTO', 'AUXILIAR', 'PRANCHA', 'EIXO', 'LEGENDA', 'CARIMBO']);
/** Campos que só mudam a aparência (livres). */
const APARENCIA = new Set(['cor', 'espessura', 'tipo_linha', 'escala_tipo']);

export class MetodosTravaPecasCAD {
  /** Desenho gerado do 3D (e não o ambiente de edição da peça, onde ela é livre). */
  _desenhoGerado() {
    const m = this.doc.metadados || {};
    if (m.edicao) return false;
    return !!(m.gerado_por || m.detalhe_posicao || m.detalhamento || m.pranchas || m.prancha);
  }

  /** A entidade é geometria de peça gerada: detalhe de uma posição ou conjunto, fora das camadas de anotação. */
  _pecaTravada(e) {
    if (!e) return false;
    const a = e.atributos || {};
    if (!a.detalhe || !(a.posicao || a.conjunto)) return false;
    if (LIVRES.has(String(e.camada || '').toUpperCase())) return false;
    return e.tipo !== 'texto' && e.tipo !== 'cota' && e.tipo !== 'chamada';
  }

  /** A célula da peça: a da prancha, senão o detalhe/posição/conjunto. */
  _celulaDaPeca(e) {
    const a = e.atributos || {};
    return a.cel || `${a.detalhe}|${a.posicao || ''}|${a.conjunto || ''}`;
  }

  /** Quantas peças travadas cada célula tem no desenho (para conferir "a célula inteira"). */
  _contagemDasCelulas() {
    const n = new Map();
    for (const e of this.doc.entidades.values()) if (this._pecaTravada(e)) { const k = this._celulaDaPeca(e); n.set(k, (n.get(k) || 0) + 1); }
    return n;
  }

  /** As células inteiras entre os ids (todas as peças travadas delas estão no conjunto). */
  _soCelulasInteiras(ids) {
    const por = new Map();
    for (const id of ids) {
      const e = this.doc.get(id);
      if (this._pecaTravada(e)) { const k = this._celulaDaPeca(e); por.set(k, (por.get(k) || 0) + 1); }
    }
    if (!por.size) return true;
    const total = this._contagemDasCelulas();
    for (const [k, q] of por) if (q < (total.get(k) || 0)) return false;
    return true;
  }

  _nomeDaPeca(ids) {
    for (const id of ids) {
      const e = this.doc.get(id);
      if (this._pecaTravada(e)) { const a = e.atributos || {}; return a.nome || a.posicao || a.conjunto || ''; }
    }
    return '';
  }

  /** null se pode; senão o motivo (o comando não roda). */
  _recusaDaTrava(cmd) {
    if (cmd instanceof ComandoComposto) {
      for (const c of cmd.comandos) { const r = this._recusaDaTrava(c); if (r) return r; }
      return null;
    }
    const ids = cmd instanceof ComandoRemover ? cmd.ids
      : cmd instanceof ComandoAlterar ? Object.keys(cmd.mudancas || {})
      : cmd instanceof ComandoSubstituir ? (cmd.novas || []).map(n => n.id) : [];
    // a camada travada vale para tudo (também para o desenho de trabalho): o que está nela sai da operação, como no
    // AutoCAD (Ctrl+A e apagar leva o resto e deixa o travado); só ele, nada acontece
    const travadas = new Set(ids.filter(id => { const e = this.doc.get(id); return e && this.doc.bloqueada(e); }));
    if (travadas.size) {
      if (travadas.size === ids.length) return 'Camada travada: destrave a camada para mexer nesses objetos.';
      if (cmd instanceof ComandoRemover) cmd.ids = cmd.ids.filter(id => !travadas.has(id));
      else if (cmd instanceof ComandoAlterar) for (const id of travadas) delete cmd.mudancas[id];
      else if (cmd instanceof ComandoSubstituir) cmd.novas = cmd.novas.filter(n => !travadas.has(n.id));
      return this._recusaDaTrava(cmd);
    }
    if (!this._desenhoGerado()) return null;
    const editarPeca = 'Para mudar furos, tamanho ou recortes, selecione a peça e use "Editar isolada" ou "Editar no local" (vai ao 3D); para arrumar a prancha, mova ou apague a célula inteira.';
    if (cmd instanceof ComandoAdicionar) {
      // cópia de pedaço de peça gerada (um furo, uma linha da vista) solta no desenho: não vira peça nem volta ao 3D
      const pedaco = (cmd.entidades || []).filter(e => this._pecaTravada(e));
      if (pedaco.length && !this._copiaDeCelulasInteiras(pedaco)) return `Peça gerada do 3D: copiar um pedaço dela não muda a peça. ${editarPeca}`;
      return null;
    }
    if (cmd instanceof ComandoAlterar) {
      for (const [id, m] of Object.entries(cmd.mudancas || {})) {
        const e = this.doc.get(id);
        if (!this._pecaTravada(e)) continue;
        for (const k of Object.keys(m)) {
          if (APARENCIA.has(k)) continue;
          if (k === 'atributos') {
            const a = m.atributos || {};
            if (a.detalhe === (e.atributos || {}).detalhe && a.posicao === (e.atributos || {}).posicao) continue;
          }
          const n = this._nomeDaPeca([id]);
          return `Peça gerada do 3D${n ? ` (${n})` : ''}: não se edita no desenho. ${editarPeca}`;
        }
      }
      return null;
    }
    if (cmd instanceof ComandoRemover || cmd instanceof ComandoSubstituir) {
      if (this._soCelulasInteiras(ids)) return null;
      const n = this._nomeDaPeca(ids);
      const o_que = cmd instanceof ComandoRemover ? 'apagar parte dela' : 'mexer em parte dela';
      return `Peça gerada do 3D${n ? ` (${n})` : ''}: ${o_que} não muda a peça. ${editarPeca}`;
    }
    return null;
  }

  /** As peças copiadas formam células inteiras (a cópia de um detalhe inteiro, para arrumar a prancha). */
  _copiaDeCelulasInteiras(ents) {
    const por = new Map();
    for (const e of ents) { const k = this._celulaDaPeca(e); por.set(k, (por.get(k) || 0) + 1); }
    const total = this._contagemDasCelulas();
    for (const [k, q] of por) if (q < (total.get(k) || 0)) return false;
    return true;
  }

  /** Os avisos da atualização automática que antes ficavam só no relatório (regra B4, 02/10): o 3D fora do padrão de
   * fábrica (o editor estava aberto), terça com o par fora do passo da máquina e a arrumação da prancha descartada
   * porque o detalhe mudou. Cada situação avisa uma vez. */
  _avisarPendencias(e) {
    const pend = ((e && e.pendente_3d) || {}).posicoes || [];
    const fora = (e && e.fora_da_maquina) || [];
    const desc = (e && e.pranchas_descartadas) || [];
    const chave = JSON.stringify([pend, fora, desc]);
    if (chave === this._pendenciasAvisadas) return;
    this._pendenciasAvisadas = chave;
    const partes = [];
    if (pend.length) partes.push(`o 3D está fora do padrão de fábrica em ${pend.length} posição(ões) (${pend.slice(0, 8).join(', ')}${pend.length > 8 ? '…' : ''}): os desenhos mostram o 3D como está — no editor 3D, "Aplicar no 3D"`);
    if (fora.length) partes.push(`terça(s) com o par de furos fora do passo da máquina, ligadas sem chapa: ${fora.slice(0, 5).join('; ')}${fora.length > 5 ? '…' : ''} — acerte a ligação no 3D`);
    if (pend.length || fora.length) partes.push('as pranchas não são emitidas até resolver');
    if (desc.length) partes.push(`a arrumação feita à mão em ${desc.length} célula(s) da prancha foi descartada porque o detalhe mudou (${desc.slice(0, 6).join(', ')}${desc.length > 6 ? '…' : ''}): arrume de novo`);
    if (partes.length) this.aviso(partes.join(' · ') + '.', 'atencao', 0);
  }
}
