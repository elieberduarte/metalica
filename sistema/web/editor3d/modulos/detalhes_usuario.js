// Métodos do editor 3D: o detalhe do usuário — a ligação montada à mão salva como modelo e aplicada de novo
// (F14 da análise de 14/10/2026: "o que não está na biblioteca o usuário cria uma vez e reaproveita").
//
// Salvar: a seleção tem as peças do detalhe e a(s) barra(s) de referência (a viga em que a chapa de topo está e o pilar
// em que ela chega; o pilar da base). O servidor (nucleo3d/detalhe_usuario.py) grava as peças no sistema da ponta da
// barra — e o corte da ponta, as soldas e o conjunto — na biblioteca da empresa (detalhes-3d.json, na pasta de dados).
// Aplicar: nas barras selecionadas, na ponta certa; as peças iguais ficam com a mesma marca. Um Ctrl+Z desfaz.

import { el } from '../editor.js';
import { clonar, criar, comprimentoDaBarra } from '../nucleo/documento.js';
import { ComandoAdicionar, ComandoAlterar, ComandoComposto } from '../nucleo/comandos.js';

async function postar(rota, corpo) {
  const r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  const j = await r.json();
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

export class MetodosDetalhesUsuario {
  /** Editar → Salvar como detalhe: as peças selecionadas e a(s) barra(s) de referência. */
  async salvarComoDetalhe() {
    const sel = this.selecao.entidades;
    const barras = sel.filter(e => e.tipo === 'barra');
    if (sel.length < 2 || !barras.length) {
      this.dica('Selecione as peças do detalhe (chapas, cantoneiras, parafusos) e a barra em que ele está (a viga, o pilar).');
      return;
    }
    // sugestão: as barras compridas são as referências; as curtas (cantoneira, chumbador) são peças do detalhe
    const ordem = [...barras].sort((a, b) => comprimentoDaBarra(b) - comprimentoDaBarra(a));
    const marcas = new Map();
    const lista = el('div');
    for (const b of ordem) {
      const ck = el('input', { type: 'checkbox', checked: comprimentoDaBarra(b) > 1000 && ordem.indexOf(b) < 2 });
      marcas.set(b.id, ck);
      const m = (b.atributos && b.atributos.marcas) || {};
      lista.append(el('label', { style: 'display:block;margin:.15em 0' }, ck,
        ` ${m.posicao ? m.posicao + ' — ' : ''}${b.perfil} · ${Math.round(comprimentoDaBarra(b))} mm${b.papel ? ' · ' + b.papel : ''}`));
    }
    const nome = el('input', { type: 'text', placeholder: 'Chapa de topo W310 × pilar W310', style: 'width:100%' });
    const corpo = el('div', {},
      el('label', { texto: 'Nome do detalhe' }), nome,
      el('p', { texto: 'Barras de referência (a peça em que o detalhe vai — uma, ou a que chega e o apoio):' }), lista,
      el('p', { class: 'explica', texto: `${sel.length - barras.length} peça(s) além das barras. As peças ficam gravadas na ponta da barra de referência; o corte da ponta, as soldas e o conjunto vão junto.` }));
    if (await this.dialogo({ titulo: 'Salvar como detalhe', corpo, ok: 'Salvar' }) !== 'ok') return;
    const refs = [...marcas].filter(([, ck]) => ck.checked).map(([id]) => id);
    if (!refs.length || refs.length > 2) { this.aviso('Marque uma ou duas barras de referência.', 'atencao'); return; }
    try {
      const j = await postar('/api/detalhes-3d/salvar', { documento: this.documento.paraJSON(), pecas: sel.map(e => e.id), refs,
                                                           nome: nome.value.trim() || 'Detalhe' });
      this._detalhes3d = j.detalhes;
      this.aviso(`Detalhe "${j.detalhe.nome}" salvo na biblioteca (${j.detalhe.n_refs} barra(s) de referência). Editar → Aplicar detalhe o põe em outras barras.`, 'info', 9000);
    } catch (e) { this.aviso(`Não foi possível salvar o detalhe: ${e.message}`, 'erro', 0); }
  }

  /** Editar → Aplicar detalhe: um detalhe da biblioteca nas barras selecionadas. */
  async aplicarDetalhe() {
    const barras = this.selecao.entidades.filter(e => e.tipo === 'barra');
    if (!barras.length) { this.dica('Selecione a(s) barra(s) em que o detalhe vai.'); return; }
    let lista;
    try {
      const r = await fetch('/api/detalhes-3d');
      lista = (await r.json()).detalhes || [];
    } catch (e) { this.aviso(`Não foi possível ler a biblioteca: ${e.message}`, 'erro', 0); return; }
    if (!lista.length) { this.aviso('A biblioteca está vazia: monte a ligação, selecione as peças e a barra e use Editar → Salvar como detalhe.', 'atencao', 0); return; }
    const escolha = el('select');
    for (const d of lista) escolha.append(el('option', { value: d.id, texto: `${d.nome} — ${d.pecas} peça(s), ${d.n_refs} barra(s) · ${d.perfil || ''}` }));
    const ponta = el('select');
    for (const [v, t] of [['auto', 'automática (a de baixo/de cima como a do detalhe; a que chega no apoio)'], ['inicio', 'início da barra'],
                          ['fim', 'fim da barra'], ['ambas', 'as duas pontas']]) ponta.append(el('option', { value: v, texto: t }));
    const excluir = el('button', { type: 'button', class: 'mini', texto: 'Excluir este detalhe da biblioteca' });
    excluir.addEventListener('click', async () => {
      try {
        const j = await postar('/api/detalhes-3d/excluir', { id: escolha.value });
        if (j.excluido) { escolha.querySelector(`option[value="${CSS.escape(escolha.value)}"]`)?.remove(); this.dica('Detalhe excluído da biblioteca.'); }
      } catch (e) { this.aviso(`Não foi possível excluir: ${e.message}`, 'erro', 0); }
    });
    const corpo = el('div', {}, el('div', { class: 'campos' }, el('label', { texto: 'Detalhe' }), escolha, el('label', { texto: 'Ponta' }), ponta),
      el('p', { class: 'explica', texto: `${barras.length} barra(s) selecionada(s). Detalhe de duas barras: selecione a que chega e o apoio.` }), excluir);
    if (await this.dialogo({ titulo: 'Aplicar detalhe', corpo, ok: 'Aplicar' }) !== 'ok' || !escolha.value) return;
    let r;
    try {
      this.dica('Aplicando o detalhe…');
      r = await postar('/api/detalhes-3d/aplicar', { documento: this.documento.paraJSON(), id: escolha.value, ids: barras.map(b => b.id), ponta: ponta.value });
    } catch (e) { this.aviso(`Não foi possível aplicar: ${e.message}`, 'erro', 0); return; }
    const partes = [];
    const alt = {};
    for (const [id, campos] of Object.entries(r.alterar || {})) if (this.documento.get(id)) alt[id] = clonar(campos);
    if (Object.keys(alt).length) partes.push(new ComandoAlterar(alt));
    const novas = (r.novas || []).map(d => criar(d));
    if (novas.length) partes.push(new ComandoAdicionar(novas));
    if (partes.length) this.executar(new ComandoComposto(partes, 'Aplicar detalhe'));
    if (novas.length) this.selecao.definir(novas.map(e => e.id));
    this.aviso(`Detalhe aplicado: ${novas.length} peça(s).${(r.avisos || []).length ? ' ' + r.avisos.join('; ') : ''}`,
      (r.avisos || []).length ? 'atencao' : 'info', (r.avisos || []).length ? 0 : 8000);
  }
}
