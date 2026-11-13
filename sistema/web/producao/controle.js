/* O controle de produção (FERRAMENTA · CONTROLE DE PRODUÇÃO, 12/11/2026): o andamento da obra por etapa (Produção e
 * Pintura), a lista do que se controla e o apontamento. Tela própria (/controle-producao, web/producao/controle.html),
 * aberta pelo menu Produção do topo — até 12/11 era a aba Controle da lista de materiais; o usuário não achou e pediu no
 * menu. Só no modo desenvolvimento (producao/web.py).
 * Itens: cada unidade de tesoura/conjunto (T38-1, T38-2) e cada posição de peças avulsas iguais (T.C.1: 46 peças).
 * O registro fica no projeto (producao/apontamentos.jsonl); erro vira estorno, nada se apaga. */
'use strict';
(function () {
  const $ = (s, raiz = document) => raiz.querySelector(s);
  const PROJETO = new URLSearchParams(location.search).get('projeto') || '';
  const ESTADO = { dados: null, corpo: null, carregando: false, filtroEtapa: '', filtroTipo: '', busca: '', escolhidos: [] };

  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'texto') e.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const f of filhos.flat()) {
      if (f === null || f === undefined || f === false) continue;
      e.append(f.nodeType ? f : document.createTextNode(String(f)));
    }
    return e;
  }
  const n = (x, casas = 0) => (x === null || x === undefined || x === '') ? '—'
    : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  async function pedir(rota, corpo) {
    const r = await fetch(rota, corpo === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
    let j = {};
    try { j = await r.json(); } catch { /* sem corpo */ }
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  function aviso(texto, erro = false) {
    const a = $('#aviso');
    a.hidden = !texto;
    a.textContent = texto || '';
    a.classList.toggle('erro', !!erro);
  }
  const vazio = (texto) => el('div', { class: 'vazio', texto });
  const secao = (titulo, sub, conteudo) => el('section', {}, el('h3', {}, titulo, sub ? el('small', { texto: sub }) : null), conteudo);
  /** tabela ordenável pelo clique no título: colunas = [{titulo, chave|valor(l), classe, num, casas}] */
  function tabela(colunas, linhas, rodape, chaveFiltro) {
    const thead = el('thead', {}, el('tr', {}, colunas.map((c, i) => el('th', {
      class: c.classe || '', texto: c.titulo, title: 'Clique para ordenar', onclick: (ev) => ordenar(ev.currentTarget.closest('table'), i, c) }))));
    const tbody = el('tbody');
    for (const li of linhas) {
      const tr = el('tr', { 'data-filtro': chaveFiltro(li).toLowerCase(), 'data-item': li.origem ? li.id : null });
      for (const c of colunas) {
        const v = c.valor ? c.valor(li) : li[c.chave];
        const td = el('td', { class: c.classe || '' });
        if (v && v.nodeType) td.append(v); else td.textContent = c.num ? n(v, c.casas || 0) : (v ?? '—');
        td.dataset.v = c.num ? String(Number(v) || 0) : (v && v.nodeType ? v.textContent || '' : String(v ?? ''));
        tr.append(td);
      }
      tbody.append(tr);
    }
    const t = el('table', {}, thead, tbody);
    if (rodape) t.append(el('tfoot', {}, el('tr', {}, rodape.map((v, i) => el('td', { class: colunas[i].classe || '', texto: v ?? '' })))));
    return t;
  }
  function ordenar(table, i, c) {
    const th = table.tHead.rows[0].cells[i];
    const asc = !th.classList.contains('ordem-asc');
    for (const x of table.tHead.rows[0].cells) x.classList.remove('ordem-asc', 'ordem-desc');
    th.classList.add(asc ? 'ordem-asc' : 'ordem-desc');
    const linhas = [...table.tBodies[0].rows];
    linhas.sort((a, b) => {
      const va = a.cells[i].dataset.v, vb = b.cells[i].dataset.v;
      const r = c.num ? (Number(va) - Number(vb)) : va.localeCompare(vb, 'pt-BR', { numeric: true });
      return asc ? r : -r;
    });
    table.tBodies[0].append(...linhas);
  }
  function filtrar() {
    const termo = (ESTADO.busca || '').trim().toLowerCase();
    for (const tr of document.querySelectorAll('#controle-corpo tbody tr[data-filtro]')) {
      tr.classList.toggle('oculta', !!termo && !tr.dataset.filtro.includes(termo));
    }
  }

  const estilo = document.createElement('style');
  estilo.textContent = `
    .ctl-cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 0 0 12px; }
    .ctl-trilho { height: 8px; background: var(--painel2); border: 1px solid var(--borda); border-radius: 999px; overflow: hidden; margin-top: 6px; }
    .ctl-trilho i { display: block; height: 100%; background: var(--verde, #1f7a4d); }
    .ctl-ok { color: var(--verde, #1f7a4d); font-weight: 650; }
    .ctl-meio { color: var(--amarelo-tinta, #9a6a00); font-weight: 650; }
    .ctl-nada { color: var(--texto3); }
    .ctl-barra { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 8px; font-size: 13px; color: var(--texto2); }
    .ctl-barra input[type=search] { font: inherit; font-size: 13px; padding: 4px 9px; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); background: var(--campo-fundo); color: var(--texto); width: 230px; }
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
    .ctl-a-mais { color: var(--verm, #b23b3b); font-weight: 600; }
    .controle tbody tr[data-item] { cursor: pointer; }
    .controle tbody tr.escolhida td { background: color-mix(in srgb, var(--ctl-destaque, #f2b01e) 26%, var(--painel)); }
    .controle tbody tr.escolhida td:first-child { box-shadow: inset 3px 0 0 var(--ctl-destaque, #f2b01e); }
  `;
  document.head.append(estilo);

  const hojeISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const dataBRc = (iso) => iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '—';
  const horaBR = (iso) => iso && String(iso).length > 11 ? String(iso).slice(11, 16) : '';

  function situacaoCelula(feito, total) {
    if (feito > total) return el('span', { class: 'ctl-a-mais', title: 'Apontado a mais: confira e estorne o que sobrou',
      texto: `✓ ${n(total)} +${n(feito - total)} a mais` });
    if (feito >= total) return el('span', { class: 'ctl-ok', texto: total > 1 ? `✓ ${n(total)}` : '✓' });
    if (feito > 0) return el('span', { class: 'ctl-meio', texto: `${n(feito)} de ${n(total)}` });
    return el('span', { class: 'ctl-nada', texto: '—' });
  }

  async function carregar() {
    if (ESTADO.carregando) return;
    ESTADO.carregando = true;
    try {
      ESTADO.dados = await pedir(`/api/producao/controle?projeto=${encodeURIComponent(PROJETO)}`);
      const D = ESTADO.dados;
      if (D.obra) { $('#obra-nome').textContent = D.obra; document.title = `Controle de produção — ${D.obra}`; }
      if (D.lista_gerada) $('#quando').textContent = `lista levantada em ${dataBRc(D.lista_gerada)} ${horaBR(D.lista_gerada)}`;
      window.controleDados = D;
      if (D.itens) document.dispatchEvent(new CustomEvent('controle:dados', { detail: D }));   // o 3D ao lado (controle3d.js)
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

    const busca = el('input', { type: 'search', id: 'filtro', placeholder: 'Procurar item, tipo, perfil…', title: 'Filtra as linhas do quadro' });
    busca.value = ESTADO.busca;
    busca.addEventListener('input', () => { ESTADO.busca = busca.value; filtrar(); });

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
      el('div', {}, el('div', { class: 'ctl-barra' }, busca, selEtapa, selTipo,
        el('span', { texto: `${n(D.total.unidades_conjunto)} unidades de conjunto · ${n(D.total.itens - D.total.unidades_conjunto)} grupos de peças · ${n(D.total.kg, 1)} kg` })), quadro)));
    partes.push(secao('Últimos apontamentos', 'o mais novo em cima; estorno não apaga, desfaz', tabelaEventos(D.eventos || [])));
    corpo.replaceChildren(...partes);
    filtrar();
    marcarLinhas(ESTADO.escolhidos, false);
  }

  /** as linhas escolhidas (pelo clique nela ou numa peça do 3D ao lado) ficam marcadas; `rolar` traz a primeira à vista */
  function marcarLinhas(ids, rolar) {
    ESTADO.escolhidos = ids || [];
    const quer = new Set(ESTADO.escolhidos);
    let primeira = null;
    for (const tr of document.querySelectorAll('#controle-corpo tr[data-item]')) {
      const sim = quer.has(tr.dataset.item);
      tr.classList.toggle('escolhida', sim);
      if (sim && !primeira) primeira = tr;
    }
    if (rolar && primeira) {
      if (primeira.classList.contains('oculta')) {          // escondida pela busca: a busca sai
        ESTADO.busca = '';
        const b = $('#filtro');
        if (b) b.value = '';
        filtrar();
      }
      primeira.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } else if (rolar && ESTADO.escolhidos.length) {
      aviso(`${ESTADO.escolhidos.join(', ')} está fora do filtro da lista (etapa ou tipo).`);
      setTimeout(() => aviso(''), 4000);
    }
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

  function alternarTema() {
    const raiz = document.documentElement;
    const atual = raiz.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
    const novo = atual === 'escuro' ? 'claro' : 'escuro';
    raiz.setAttribute('data-tema', novo);
    try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* janela privativa */ }
  }

  function iniciar() {
    $('#btn-tema').addEventListener('click', alternarTema);
    if (!PROJETO) { $('#controle-corpo').replaceChildren(vazio('Abra o controle de produção pelo menu Produção de um projeto.')); return; }
    $('#btn-lista').href = `/materiais?projeto=${encodeURIComponent(PROJETO)}#geral`;
    ESTADO.corpo = $('#controle-corpo');
    // clicar numa linha (fora do botão Apontar) destaca as peças dela no 3D ao lado
    ESTADO.corpo.addEventListener('click', (ev) => {
      const tr = ev.target.closest('tr[data-item]');
      if (!tr || ev.target.closest('button, a, input, select')) return;
      marcarLinhas([tr.dataset.item], false);
      document.dispatchEvent(new CustomEvent('controle:item', { detail: { id: tr.dataset.item } }));
    });
    document.addEventListener('controle:marcar', (ev) => marcarLinhas(ev.detail.ids, true));
    desenhar();
    carregar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
