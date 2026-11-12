/* A aba Controle da lista de materiais (FERRAMENTA · CONTROLE DE PRODUÇÃO, 12/11/2026): o andamento da obra por etapa
 * (Produção e Pintura), a lista do que se controla e o apontamento. Só no modo desenvolvimento: producao/web.py põe este
 * script antes do materiais.js, que monta a aba pelo window.ABAS_EXTRA. Usa as funções da tela (el, n, pedir, secao,
 * cartao, vazio), que existem quando a aba abre.
 * Itens: cada unidade de tesoura/conjunto (T38-1, T38-2) e cada posição de peças avulsas iguais (T.C.1: 46 peças).
 * O registro fica no projeto (producao/apontamentos.jsonl); erro vira estorno, nada se apaga. */
'use strict';
(function () {
  const ESTADO = { dados: null, corpo: null, carregando: false, filtroEtapa: '', filtroTipo: '' };

  const estilo = document.createElement('style');
  estilo.textContent = `
    .ctl-cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 0 0 12px; }
    .ctl-trilho { height: 8px; background: var(--painel2); border: 1px solid var(--borda); border-radius: 999px; overflow: hidden; margin-top: 6px; }
    .ctl-trilho i { display: block; height: 100%; background: var(--verde, #1f7a4d); }
    .ctl-ok { color: var(--verde, #1f7a4d); font-weight: 650; }
    .ctl-meio { color: var(--amarelo-tinta, #9a6a00); font-weight: 650; }
    .ctl-nada { color: var(--texto3); }
    .ctl-barra { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 8px; font-size: 13px; color: var(--texto2); }
    .ctl-barra select { font: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); background: var(--campo-fundo); color: var(--texto); }
    .ctl-btn { font: inherit; font-size: 12.5px; padding: 3px 10px; border: 1px solid var(--azul-linha, #8fb3df); border-radius: var(--raio-p); background: var(--azul-fraco, #eef4fc); color: var(--azul-tinta, #1f5fa8); cursor: pointer; }
    .ctl-btn:hover { filter: brightness(.96); }
    .ctl-btn.perigo { border-color: var(--verm, #b23b3b); background: transparent; color: var(--verm, #b23b3b); }
    dialog.ctl-dlg { border: 1px solid var(--borda); border-radius: var(--raio); padding: 16px 18px; background: var(--painel); color: var(--texto); min-width: 360px; box-shadow: var(--sombra); }
    dialog.ctl-dlg::backdrop { background: rgba(0,0,0,.28); }
    dialog.ctl-dlg h3 { margin: 0 0 4px !important; }
    dialog.ctl-dlg label { display: block; font-size: 12.5px; color: var(--texto2); margin: 10px 0 3px; }
    dialog.ctl-dlg input, dialog.ctl-dlg textarea { font: inherit; font-size: 13.5px; padding: 5px 8px; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); background: var(--campo-fundo); color: var(--texto); width: 100%; box-sizing: border-box; }
    dialog.ctl-dlg .etapas { display: flex; gap: 14px; font-size: 13.5px; }
    dialog.ctl-dlg .etapas label { display: inline-flex; gap: 5px; align-items: center; margin: 0; color: var(--texto); }
    dialog.ctl-dlg .etapas input { width: auto; }
    dialog.ctl-dlg .acoes { display: flex; gap: 8px; justify-content: flex-end; margin-top: 14px; }
    dialog.ctl-dlg .erro { color: var(--verm, #b23b3b); font-size: 13px; margin-top: 8px; }
    .ctl-estornado td { text-decoration: line-through; color: var(--texto3); }
  `;
  document.head.append(estilo);

  const hojeISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const dataBRc = (iso) => iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '—';
  const horaBR = (iso) => iso && String(iso).length > 11 ? String(iso).slice(11, 16) : '';

  function situacaoCelula(feito, total) {
    if (feito >= total) return el('span', { class: 'ctl-ok', texto: total > 1 ? `✓ ${n(total)}` : '✓' });
    if (feito > 0) return el('span', { class: 'ctl-meio', texto: `${n(feito)} de ${n(total)}` });
    return el('span', { class: 'ctl-nada', texto: '—' });
  }

  async function carregar() {
    if (ESTADO.carregando) return;
    ESTADO.carregando = true;
    try {
      ESTADO.dados = await pedir(`/api/producao/controle?projeto=${encodeURIComponent(PROJETO)}`);
    } catch (e) {
      ESTADO.dados = { erro: e.message };
    } finally {
      ESTADO.carregando = false;
    }
    desenhar();
  }

  function desenhar() {
    const corpo = ESTADO.corpo;
    if (!corpo) return;
    const D = ESTADO.dados;
    if (!D) { corpo.replaceChildren(vazio('Carregando o controle…')); return; }
    if (D.erro && !D.sem_lista) { corpo.replaceChildren(vazio('Não foi possível ler o controle: ' + D.erro)); return; }
    if (D.sem_lista) { corpo.replaceChildren(vazio(D.erro)); return; }

    const etapas = D.etapas || [];
    const cartoes = el('div', { class: 'ctl-cartoes', id: 'ctl-cartoes' },
      etapas.map(et => {
        const a = D.andamento[et.chave] || {};
        return el('div', { class: 'cartao-n', 'data-etapa': et.chave },
          el('b', { texto: `${n(a.pct, 1)} %` }), el('span', { texto: et.titulo }),
          el('small', { texto: `${n(a.kg, 1)} de ${n(D.total.kg, 1)} kg · ${n(a.itens_completos)} de ${n(D.total.itens)} itens completos` }),
          el('div', { class: 'ctl-trilho' }, el('i', { style: `width:${Math.min(100, a.pct || 0).toFixed(1)}%` })));
      }),
      el('div', { class: 'cartao-n' }, el('b', { texto: n(D.hoje.apontamentos) }), el('span', { texto: 'Apontamentos hoje' }),
        el('small', { texto: `${n(D.hoje.kg, 1)} kg · quem aponta: ${D.quem || '—'}` })));

    const tipos = [...new Set(D.itens.map(x => x.tipo))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    const selEtapa = el('select', { id: 'ctl-filtro-etapa', title: 'Mostrar só os itens que faltam numa etapa' },
      el('option', { value: '', texto: 'Todos os itens' }),
      etapas.map(et => el('option', { value: et.chave, texto: `Falta na ${et.titulo.toLowerCase()}` })));
    selEtapa.value = ESTADO.filtroEtapa;
    selEtapa.addEventListener('change', () => { ESTADO.filtroEtapa = selEtapa.value; desenhar(); });
    const selTipo = el('select', { id: 'ctl-filtro-tipo', title: 'Mostrar só um tipo' },
      el('option', { value: '', texto: 'Todos os tipos' }), tipos.map(t => el('option', { value: t, texto: t })));
    selTipo.value = ESTADO.filtroTipo;
    selTipo.addEventListener('change', () => { ESTADO.filtroTipo = selTipo.value; desenhar(); });

    const linhas = D.itens.filter(x => (!ESTADO.filtroTipo || x.tipo === ESTADO.filtroTipo)
      && (!ESTADO.filtroEtapa || (x.feito[ESTADO.filtroEtapa] || 0) < x.quantidade));
    const colunas = [
      { titulo: 'Item', chave: 'id', classe: 'b' },
      { titulo: 'Tipo', chave: 'tipo' },
      { titulo: 'Descrição', chave: 'descricao' },
      { titulo: 'Qtd', chave: 'quantidade', classe: 'r', num: true },
      { titulo: 'kg', chave: 'kg', classe: 'r', num: true, casas: 1 },
      ...etapas.map(et => ({ titulo: et.titulo, classe: 'c', valor: (x) => situacaoCelula(x.feito[et.chave] || 0, x.quantidade) })),
      { titulo: '', classe: 'c', valor: (x) => el('button', { type: 'button', class: 'ctl-btn', 'data-item': x.id, texto: 'Apontar', onclick: () => abrirDialogo(x) }) },
    ];
    const kgLinhas = linhas.reduce((s, x) => s + x.kg, 0);
    const quadro = linhas.length
      ? el('div', { class: 'rolagem' }, tabela(colunas, linhas, ['TOTAL', '', `${n(linhas.length)} itens`, '', n(kgLinhas, 1), ...etapas.map(() => ''), ''],
        (x) => `${x.id} ${x.tipo} ${x.descricao} ${(x.refs || []).join(' ')}`))
      : vazio('Nenhum item com este filtro.');

    const partes = [cartoes];
    if ((D.fora_da_lista || []).length) {
      partes.push(el('div', { class: 'aviso-topo' },
        `Apontamentos de itens que não estão mais na lista de materiais (o detalhamento foi refeito?): ${D.fora_da_lista.join(', ')}. `
        + 'Eles continuam guardados; confira e estorne se for o caso.'));
    }
    partes.push(secao('O que se controla', 'cada tesoura/conjunto pela unidade (T38-1, T38-2); as peças avulsas iguais pela posição, com a quantidade',
      el('div', {}, el('div', { class: 'ctl-barra' }, selEtapa, selTipo,
        el('span', { texto: `${n(D.total.unidades_conjunto)} unidades de conjunto · ${n(D.total.itens - D.total.unidades_conjunto)} grupos de peças · ${n(D.total.kg, 1)} kg` })), quadro)));
    partes.push(secao('Últimos apontamentos', 'o mais novo em cima; estorno não apaga, desfaz', tabelaEventos(D.eventos || [])));
    corpo.replaceChildren(...partes);
    if (typeof filtrar === 'function') filtrar();
  }

  function tabelaEventos(eventos) {
    if (!eventos.length) return vazio('Nenhum apontamento ainda. Use "Apontar" na linha do item.');
    const tb = el('tbody');
    const titulo = Object.fromEntries((ESTADO.dados.etapas || []).map(e => [e.chave, e.titulo]));
    for (const e of eventos) {
      const estorno = !!e.estorno_de;
      const tr = el('tr', { class: e.estornado ? 'ctl-estornado' : '', 'data-evento': e.id },
        el('td', { texto: `${dataBRc(e.quando)} ${horaBR(e.quando)}` }),
        el('td', { texto: dataBRc(e.data) }),
        el('td', { texto: e.quem || '—' }),
        el('td', { texto: (estorno ? 'estorno · ' : '') + (titulo[e.etapa] || e.etapa) }),
        el('td', { class: 'b', texto: e.item }),
        el('td', { class: 'r', texto: (estorno ? '−' : '') + n(e.quantidade) }),
        el('td', { class: 'r', texto: n(e.kg, 1) }),
        el('td', { class: 'quebra', texto: e.obs || '' }),
        el('td', { class: 'c' }, (!estorno && !e.estornado)
          ? el('button', { type: 'button', class: 'ctl-btn perigo', texto: 'Estornar', onclick: () => estornar(e) }) : null));
      tb.append(tr);
    }
    return el('div', { class: 'rolagem', style: 'max-height:40vh' }, el('table', {},
      el('thead', {}, el('tr', {}, ['Quando', 'Data', 'Quem', 'Etapa', 'Item', 'Qtd', 'kg', 'Observação', ''].map(t => el('th', { texto: t })))), tb));
  }

  function abrirDialogo(item) {
    const D = ESTADO.dados;
    const etapas = D.etapas || [];
    const falta = (k) => item.quantidade - (item.feito[k] || 0);
    const primeira = (etapas.find(et => falta(et.chave) > 0) || etapas[0]).chave;
    const dlg = el('dialog', { class: 'ctl-dlg', id: 'ctl-dialogo' });
    const qtd = el('input', { type: 'number', id: 'ctl-qtd', min: '1', step: '1' });
    const data = el('input', { type: 'date', id: 'ctl-data', value: hojeISO(), max: hojeISO() });
    const obs = el('textarea', { id: 'ctl-obs', rows: '2', maxlength: '300', placeholder: 'opcional' });
    const erro = el('div', { class: 'erro', hidden: true });
    const dica = el('small', { class: 'nota' });
    let etapa = primeira;
    const ajustar = () => {
      const f = falta(etapa);
      qtd.max = String(Math.max(f, 0));
      qtd.value = String(Math.max(f, 0));
      qtd.disabled = f <= 0 || item.quantidade === 1;
      dica.textContent = f > 0 ? `faltam ${n(f)} de ${n(item.quantidade)} na ${etapa === 'producao' ? 'produção' : 'pintura'}` : 'esta etapa já está completa';
    };
    const radios = el('div', { class: 'etapas' }, etapas.map(et => {
      const r = el('input', { type: 'radio', name: 'ctl-etapa', value: et.chave });
      r.checked = et.chave === etapa;
      r.addEventListener('change', () => { etapa = et.chave; ajustar(); });
      return el('label', {}, r, et.titulo);
    }));
    const confirmar = el('button', { type: 'submit', class: 'principal', id: 'ctl-confirmar', texto: 'Apontar' });
    const form = el('form', { method: 'dialog', novalidate: true },
      el('h3', { texto: `Apontar ${item.id}` }),
      el('div', { class: 'nota', texto: `${item.tipo} · ${item.descricao} · ${n(item.kg_unidade, 1)} kg cada` }),
      el('label', { texto: 'Etapa' }), radios,
      el('label', { texto: 'Quantidade' }), qtd, dica,
      el('label', { texto: 'Data em que foi feito' }), data,
      el('label', { texto: 'Observação' }), obs,
      el('div', { class: 'nota', texto: `Quem aponta: ${D.quem || '—'}` }),
      erro,
      el('div', { class: 'acoes' }, el('button', { type: 'button', texto: 'Cancelar', onclick: () => dlg.close() }), confirmar));
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      erro.hidden = true;
      confirmar.disabled = true;
      try {
        await pedir('/api/producao/apontar', { projeto: PROJETO, item: item.id, etapa, quantidade: Number(qtd.value || (item.quantidade === 1 ? 1 : 0)),
          data: data.value, obs: obs.value });
        dlg.close();
        await carregar();
      } catch (e) {
        erro.textContent = e.message;
        erro.hidden = false;
      } finally {
        confirmar.disabled = false;
      }
    });
    dlg.append(form);
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    ajustar();
    dlg.showModal();
  }

  async function estornar(e) {
    const titulo = Object.fromEntries((ESTADO.dados.etapas || []).map(x => [x.chave, x.titulo]));
    if (!confirm(`Estornar o apontamento de ${e.item} (${titulo[e.etapa] || e.etapa}, ${e.quantidade})? Ele continua no histórico, riscado.`)) return;
    try {
      await pedir('/api/producao/estornar', { projeto: PROJETO, evento: e.id });
      await carregar();
    } catch (err) {
      aviso(err.message, true);
    }
  }

  window.ABAS_EXTRA = (window.ABAS_EXTRA || []).concat([{
    chave: 'controle', titulo: 'Controle', filtro: true,
    abrir(corpo) {
      ESTADO.corpo = corpo;
      desenhar();
      carregar();
    },
  }]);
})();
