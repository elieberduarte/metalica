// Métodos do editor 3D: Ver → Conferir antes de detalhar (onda 4 da análise de 14/10/2026).
//
// A conta mora no servidor (nucleo3d/conferencia_producao.py): colisão pela forma das peças (não pela linha de eixo),
// a execução das ligações (furo perto da borda, passo entre parafusos, parafuso sem furo, furo sem parafuso, espaço
// para a chave) e a produção (peça sem marca, marca a conferir, sólido fora da lista, conjunto sem peça principal).
// Com peças selecionadas, a colisão e a execução olham só a região delas (o modelo grande leva minutos inteiro).
// O painel é o mesmo do Verificar apoios: clicar num achado seleciona as peças e enquadra.

import { el } from '../editor.js';

const ORDEM = ['colisao_funda', 'colisao', 'parafuso_sem_furo', 'borda', 'passo', 'chave', 'furo_sem_parafuso',
  'sem_marca', 'marca_a_conferir', 'fora_da_lista', 'sem_principal'];

export class MetodosConferencia {
  async conferirAntesDeDetalhar() {
    if (!this.documento.tamanho) { this.aviso('O modelo está vazio.', 'atencao'); return; }
    const ids = [...this.selecao.ids];
    this.dica(ids.length ? `Conferindo a região das ${ids.length} peça(s) selecionada(s)…`
                         : 'Conferindo o modelo inteiro: colisão, execução das ligações e produção (o modelo grande leva alguns minutos)…');
    let r;
    try {
      const resp = await fetch('/api/modelo/conferencia', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ documento: this.documento.paraJSON(), ids: ids.length ? ids : null }) });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { this.aviso(`Não foi possível conferir: ${e.message}`, 'erro', 0); return; }
    this.dica('');
    this._mostrarConferencia(r, ids.length);
  }

  _fecharConferencia() {
    if (this._painelConferencia) { this._painelConferencia.remove(); this._painelConferencia = null; }
  }

  _mostrarConferencia(r, nSel) {
    this._fecharConferencia();
    const achados = r.achados || [];
    const regras = r.regras || {};
    const ver = (a) => {
      const ids = (a.ids || []).filter(id => this.documento.entidades.has(id));
      if (!ids.length) { this.aviso('As peças desse achado não estão mais no modelo.', 'atencao'); return; }
      this.selecao.definir(ids);
      this.cena.destacar(ids);
      this._destaqueAtivo = true;
      this.camera.zoomSelecao(ids);
      const p = a.ponto || [0, 0, 0];
      this.dica(`${a.texto}${a.profundidade ? ` — sobreposição de ${a.profundidade} mm` : ''} — (${p.map(v => (v / 1000).toFixed(2)).join('; ')}) m. Esc limpa a seleção.`);
    };
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    const col = (r.info && r.info.colisao) || null;
    let cabeca = achados.length ? `${achados.length.toLocaleString('pt-BR')} achado(s)` : 'Nenhum achado: nada se atravessa, as ligações têm furo, borda, passo e chave, e as peças têm marca.';
    if (nSel) cabeca += ` na região das ${nSel} peça(s) selecionada(s) (a produção é do modelo inteiro).`;
    if (col && col.parcial) cabeca += ` A colisão conferiu ${col.conferidos} de ${col.pares} pares no tempo limite: selecione uma região e confira de novo para o resto.`;
    corpo.append(el('p', { texto: cabeca }));
    for (const regra of ORDEM) {
      const lista = achados.filter(a => a.regra === regra);
      if (!lista.length) continue;
      const det = el('details', { open: lista.length <= 40 });
      det.append(el('summary', { texto: `${regras[regra] || regra} (${lista.length})` }));
      const ul = el('ul');
      for (const a of lista.slice(0, 400)) {
        const extra = a.profundidade ? ` (${String(a.profundidade).replace('.', ',')} mm)` : '';
        ul.append(el('li', { texto: a.texto + extra, title: 'Selecionar e enquadrar', onclick: () => ver(a) }));
      }
      if (lista.length > 400) ul.append(el('li', { class: 'mais', texto: `… e mais ${lista.length - 400}` }));
      det.append(ul);
      corpo.append(det);
    }
    this._painelConferencia = el('div', { class: 'painel-apoios painel-conferencia' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: 'Conferir antes de detalhar' }),
        el('button', { type: 'button', texto: 'Conferir de novo', onclick: () => this.conferirAntesDeDetalhar() }),
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharConferencia() })),
      corpo);
    (this.el.palco || document.body).append(this._painelConferencia);
  }
}
