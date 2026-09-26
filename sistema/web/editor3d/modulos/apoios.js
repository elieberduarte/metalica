// Métodos do editor 3D: Ver → Verificar apoios.
//
// As regras de qualquer estrutura, conferidas no servidor (nucleo3d/apoios.py): nenhuma
// peça voando, treliça apoiada em pilar ou em outra peça, terça apoiada nas pontas e sobre
// os nós, pilar com o que carregar, viga apoiada nas duas pontas. O painel lista os
// achados por regra; clicar num achado seleciona as peças e enquadra a câmera nelas.

import { el } from '../editor.js';

const REGRAS = [
  ['voando', 'Peças voando (sem ligação até a base)'],
  ['ponta_sem_apoio', 'Ponta de treliça sem apoio'],
  ['terca_sem_apoio', 'Terça sem apoio'],
  ['terca_em_balanco', 'Terça passando do último apoio'],
  ['viga_sem_apoio', 'Viga com a ponta sem apoio'],
  ['pilar_sem_carga', 'Pilar sem peça em cima'],
  ['terca_fora_do_no', 'Terça fora do nó da treliça'],
];

export class MetodosApoios {
  async verificarApoios() {
    if (!this.documento.tamanho) { this.aviso('O modelo está vazio.', 'atencao'); return; }
    this.dica('Conferindo os apoios…');
    let r;
    try {
      r = await this.api.apoios(this.documento.paraJSON());
    } catch (e) {
      this.aviso(`Não foi possível conferir os apoios: ${e.message}`, 'erro');
      return;
    }
    this._mostrarApoios(r);
  }

  _fecharApoios() {
    if (this._painelApoios) { this._painelApoios.remove(); this._painelApoios = null; }
  }

  _mostrarApoios(r) {
    this._fecharApoios();
    const achados = r.achados || [];
    const z = r.resumo || {};
    const verAchado = (a) => {
      const ids = (a.ids || []).filter(id => this.documento.entidades.has(id));
      if (!ids.length) { this.aviso('As peças desse achado não estão mais no modelo.', 'atencao'); return; }
      this.selecao.definir(ids);
      this.cena.destacar(ids);
      this._destaqueAtivo = true;
      this.camera.zoomSelecao(ids);
      this.dica(`${a.texto} — (${a.ponto.map(v => (v / 1000).toFixed(2)).join('; ')}) m. Esc limpa a seleção.`);
    };
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    const cabeca = el('p', {
      texto: achados.length
        ? `${achados.length.toLocaleString('pt-BR')} achado(s) em ${(z.pecas || 0).toLocaleString('pt-BR')} peças. ` +
          `Pontas de treliça apoiadas: ${z.pontas_apoiadas || 0} de ${z.pontas_trelica || 0}; terças sem nada a apontar: ` +
          `${z.tercas_ok || 0} de ${z.tercas || 0}.`
        : 'Nenhum achado: toda peça chega à base, as treliças e vigas apoiam nas pontas e as terças nos nós.',
    });
    corpo.append(cabeca);
    for (const [regra, titulo] of REGRAS) {
      const lista = achados.filter(a => a.regra === regra);
      if (!lista.length) continue;
      const det = el('details', { open: regra !== 'terca_fora_do_no' && lista.length <= 40 });
      det.append(el('summary', { texto: `${titulo} (${lista.length})` }));
      const ul = el('ul');
      for (const a of lista.slice(0, 400)) {
        ul.append(el('li', { texto: a.texto, title: 'Selecionar e enquadrar', onclick: () => verAchado(a) }));
      }
      if (lista.length > 400) ul.append(el('li', { class: 'mais', texto: `… e mais ${lista.length - 400}` }));
      det.append(ul);
      corpo.append(det);
    }
    this._painelApoios = el('div', { class: 'painel-apoios' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: 'Verificar apoios' }),
        el('button', { type: 'button', texto: 'Conferir de novo', onclick: () => this.verificarApoios() }),
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharApoios() })),
      corpo);
    (this.el.palco || document.body).append(this._painelApoios);
  }
}
