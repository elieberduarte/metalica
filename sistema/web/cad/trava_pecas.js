// Trava da peça gerada (regra R5, combinada com o usuário em 02/10): nos desenhos que o sistema gera do 3D —
// detalhamento e "Detalhe – marca" (as pranchas saíram em 13/11: nelas a peça é uma fotografia, livre) —, a geometria da peça (vista, contorno, furo) é do 3D e não se edita
// no desenho: furo apagado ou contorno esticado ali não voltava ao 3D e sumia na próxima atualização. Para mudar a
// peça: "Editar peça" (o ambiente de edição, faixa EDITANDO … Concluir, que leva ao 3D). Continua livre o que é
// apresentação: mover, copiar ou apagar a célula inteira, cotas, textos, chamadas, a aparência (cor, espessura) e
// o que se desenha por cima. A camada travada (a REFERENCIA do Editar chapa, o arquitetônico) também passa a valer
// para tudo: Ctrl+A, duplo clique na camada e "Mesma peça" selecionavam e apagavam o travado.
//
// Toda edição passa por `executar` (cad.js), que pergunta aqui antes.

import { ComandoAdicionar, ComandoAlterar, ComandoComposto, ComandoRemover, ComandoSubstituir } from './nucleo/comandos.js';

/** Camadas de anotação: livres mesmo no desenho gerado. */
// o símbolo de solda é anotação como a chamada (Sooro, T1 da Sala, 09/11: "não estou conseguindo apagar esse detalhe da
// solda" — as linhas e a seta dele caíam na trava da peça)
const LIVRES = new Set(['COTA', 'TEXTO', 'AUXILIAR', 'PRANCHA', 'EIXO', 'LEGENDA', 'CARIMBO', 'SOLDA']);
/** Campos que só mudam a aparência (livres). */
const APARENCIA = new Set(['cor', 'espessura', 'tipo_linha', 'escala_tipo']);

export class MetodosTravaPecasCAD {
  /** Desenho gerado do 3D (e não o ambiente de edição da peça, onde ela é livre). */
  _desenhoGerado() {
    const m = this.doc.metadados || {};
    if (m.edicao || this._ePrancha()) return false;
    return !!(m.gerado_por || m.detalhe_posicao || m.detalhamento);
  }

  /** As pranchas: a peça nelas é uma fotografia do projeto (usuário, 13/11, Sooro Sala: "a prancha seria uma fotografia
   *  do projeto") — move, apaga, estica, recorta à mão; a remontagem guarda o que foi feito (nucleo2d/ajustes_pranchas,
   *  também a forma) e nada disso muda o 3D nem a lista. A trava da peça fica nos desenhos de detalhamento. */
  _ePrancha() {
    const m = this.doc.metadados || {};
    return !!(m.pranchas || m.prancha);
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
    if (!this._desenhoGerado()) {
      if (this._ePrancha() && !this._fotografiaAvisada && this._mexeEmPeca(cmd, ids)) {
        // na 1ª vez que mexe numa peça da prancha, um aviso discreto (a escolha do usuário, 13/11)
        this._fotografiaAvisada = true;
        this.aviso('Na prancha a peça é uma fotografia do projeto: o que você mudar aqui fica na prancha (e volta nas próximas montagens), mas não muda a peça no 3D nem a lista. Para mudar a peça, "Editar isolada" ou "Editar no local".', 'info', 12000);
      }
      return null;
    }
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

  /** O comando mexe em geometria de peça gerada (não só em anotação). */
  _mexeEmPeca(cmd, ids) {
    if (cmd instanceof ComandoAdicionar) return (cmd.entidades || []).some(e => this._pecaTravada(e));
    return (ids || []).some(id => this._pecaTravada(this.doc.get(id)));
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
    // FAB-01 (04/11): o suporte de terça com o par fora do passo — vai ao corte das chapas assim
    const sup = (e && e.suportes_fora_da_maquina) || [];
    const desc = (e && e.pranchas_descartadas) || [];
    // os avisos são do último detalhamento: com o 3D mudado depois, a tela diz de quando (Posto, 27/10: as 79 terças eram
    // de um detalhamento de 3 dias antes, de um 3D já remontado, e nada dizia isso)
    const antigo = !!(e && e.pendencias_de_outro_3d);
    const chave = JSON.stringify([pend, fora, sup, desc, antigo]);
    if (chave === this._pendenciasAvisadas) return;
    this._pendenciasAvisadas = chave;
    // o aviso de antes sai: depois de um Detalhar que resolveu, ficava o amarelo velho na tela (Q18, primeiro uso 16/10)
    if (this._avisoPendencias) { this._avisoPendencias.closest('.aviso')?.remove(); this._avisoPendencias = null; }
    const partes = [];
    if (pend.length) partes.push(`o 3D está fora do padrão de fábrica em ${pend.length} posição(ões) (${pend.slice(0, 8).join(', ')}${pend.length > 8 ? '…' : ''}): os desenhos mostram o 3D como está — no editor 3D, "Aplicar no 3D"`);
    if (fora.length) partes.push(`${fora.length} terça(s) com o par de furos fora do passo da máquina, ligadas sem chapa — no 3D, ponha a chapa de ligação (suporte de terça) ou leve o par ao passo da máquina`);
    if (sup.length) partes.push(`${sup.length} suporte(s) de terça com o par de furos fora do passo da máquina — no 3D, leve o par do suporte ao passo da terça (50 mm até 200 de altura, 100 acima)`);
    if (pend.length || fora.length || sup.length) partes.push(sup.length ? 'as pranchas e o corte das chapas não saem até resolver' : 'as pranchas não são emitidas até resolver');
    // desde 12/11 a célula mudada pelo gerador continua onde o usuário a pôs; sai só o movimento da que ele pôs noutro canto
    if (desc.length) partes.push(`${desc.length} célula(s) da prancha voltaram para onde a montagem as pôs, porque ela as pôs em outro lugar da folha (${desc.slice(0, 6).join(', ')}${desc.length > 6 ? '…' : ''}): confira e, se for o caso, leve de novo`);
    if (!partes.length) return;
    if (antigo) partes.unshift(`Aviso do detalhamento de ${String(e.pendencias_de || '').replace(/^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d).*$/, '$3/$2 às $4') || 'antes'}, feito com o 3D de antes (o 3D mudou depois; o próximo Detalhar confere de novo)`);
    const pecas = ((e && e.fora_da_maquina_pecas) || []).concat((e && e.suportes_fora_da_maquina_pecas) || []);
    // cada terça com o caminho até ela (Q01, primeiro uso 16/10: o aviso dizia "T.O.6" e nada levava à peça)
    const caixa = document.createElement('span');
    caixa.append(partes.join(' · ') + '.');
    if (fora.length || sup.length) caixa.append(this._listaVerNo3D(pecas.length ? pecas : fora.concat(sup).map(t => ({ texto: t, ids: [] }))));
    this.aviso(caixa, 'atencao', 0);
    this._avisoPendencias = caixa;
  }

  /** O erro de emitir as pranchas (PDF/DXF recusado, regra R6): a mensagem e, para cada peça que o servidor mandou
   *  (`pecas` no erro), um "Ver no 3D" que abre o editor com ela e a barra em que se liga em destaque (Q01). */
  _avisoDeEmissao(erro, titulo) {
    const pecas = (erro && erro.dados && erro.dados.pecas) || [];
    if (!pecas.length) { this.aviso(`${titulo}: ${erro.message}`, 'erro', 0); return; }
    const caixa = document.createElement('span');
    caixa.append(`${titulo}: ${erro.message}`);
    caixa.append(this._listaVerNo3D(pecas));
    this.aviso(caixa, 'erro', 0);
  }

  /** <ul> com uma linha por peça ("T.O.6: furos a 60 mm na altura (máquina: 50)") e o botão "Ver no 3D". */
  _listaVerNo3D(pecas) {
    const ul = document.createElement('ul');
    ul.className = 'lista-ver-no-3d';
    for (const p of pecas.slice(0, 30)) {
      const li = document.createElement('li');
      li.append(p.texto || p.nome || '');
      const ids = [...(p.ids || []), ...(p.ligadas || [])];
      if (ids.length && this.projeto) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'ver-no-3d';
        b.textContent = 'Ver no 3D';
        b.title = `Abre o 3D com ${p.nome || 'a peça'} (${(p.ids || []).length} peça(s))${(p.ligadas || []).length ? ' e a barra em que ela se liga' : ''} em destaque`;
        b.dataset.ids = ids.join(',');
        // sem as peças no 3D (ele mudou depois do detalhamento), o editor procura pela posição (Posto, 27/10)
        const posicoes = String(p.marca || '').split(/\s*\/\s*/).filter(Boolean);
        const senao = posicoes.length ? `&senao=${encodeURIComponent('posicao:' + posicoes.join(','))}` : '';
        b.addEventListener('click', () => this._sairPara(this.urlDoEditor(`&destacar=${encodeURIComponent('ids:' + ids.join(','))}${senao}`)));
        li.append(' ', b);
      }
      ul.append(li);
    }
    if (pecas.length > 30) { const li = document.createElement('li'); li.textContent = `… e mais ${pecas.length - 30}`; ul.append(li); }
    return ul;
  }
}
