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
  const ESTADO = { dados: null, corpo: null, carregando: false, filtroEtapa: '', filtroTipo: '', busca: '', escolhidos: [], marcados: new Set() };

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
    const thead = el('thead', {}, el('tr', {}, colunas.map((c, i) => c.cabeca ? el('th', { class: c.classe || '' }, c.cabeca()) : el('th', {
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
    faixaDosMarcados();                                     // o "todos" vale para o que está à vista
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
    dialog.ctl-dlg { max-width: min(920px, 94vw); }
    /* a janela não pula (14/11): o topo fica preso (o que cresce, cresce para baixo) e a janela do item nasce na largura final —
       a lista dos apontamentos chega depois (/api/producao/historico) e alargava e recentrava a janela: a Pintura andava 110–250 px */
    dialog.ctl-dlg { margin-top: 8vh; }
    #ctl-dialogo, #ctl-dialogo-historico { width: min(680px, 94vw); box-sizing: border-box; }
    .ctl-historico { font-size: 12.5px; }
    .ctl-confirma .ctl-confirma-texto { font-size: 16px; font-weight: 650; margin: 10px 0 6px; }
    .ctl-confirma #ctl-sim:disabled { opacity: .45; cursor: default; }
    form[hidden] { display: none; }
    .ctl-historico .rolagem { max-height: 28vh !important; }
    .ctl-a-mais { color: var(--verm, #b23b3b); font-weight: 600; }
    .controle tbody tr[data-item] { cursor: pointer; }
    th.ctl-marca, td.ctl-marca { width: 30px; padding-left: 8px !important; padding-right: 4px !important; }
    .ctl-marca input { cursor: pointer; width: 15px; height: 15px; margin: 0; }
    .ctl-varios { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 8px; padding: 7px 10px; font-size: 13px;
      border: 1px solid var(--ctl-destaque, #f2b01e); border-radius: var(--raio-p); background: color-mix(in srgb, var(--ctl-destaque, #f2b01e) 14%, var(--painel)); }
    .ctl-varios[hidden] { display: none; }
    .ctl-varios span { color: var(--texto2); }
    .ctl-btn.principal { background: var(--azul-tinta, #1f5fa8); color: #fff; border-color: var(--azul-tinta, #1f5fa8); }
    dialog.ctl-dlg .ctl-varios-lista { max-height: 34vh; overflow: auto; margin-top: 8px; border: 1px solid var(--borda); border-radius: var(--raio-p); font-size: 12.5px; }
    dialog.ctl-dlg .ctl-varios-lista table { width: 100%; border-collapse: collapse; }
    dialog.ctl-dlg .ctl-varios-lista td { padding: 3px 8px; border-bottom: 1px solid var(--borda); }
    dialog.ctl-dlg .ctl-varios-lista td.r { text-align: right; white-space: nowrap; }
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

  /** a célula da etapa: o número é a `conta` do servidor (controle.contagem) — a mesma que pinta o 3D ao lado; a pintura só
   *  conta até o produzido (risco 3, 13/11). O apontado a mais e o pintado sem produção ficam à vista. */
  function situacaoCelula(x, etapa) {
    const total = x.quantidade, apont = (x.feito || {})[etapa] || 0, conta = (x.conta || {})[etapa] || 0;
    const sem = (x.sem_anterior || {})[etapa] || 0;
    if (apont > total) return el('span', { class: 'ctl-a-mais', title: 'Apontado a mais: confira e estorne o que sobrou',
      texto: `✓ ${n(total)} +${n(apont - total)} a mais` });
    const s = conta >= total ? el('span', { class: 'ctl-ok', texto: total > 1 ? `✓ ${n(total)}` : '✓' })
      : conta > 0 ? el('span', { class: 'ctl-meio', texto: `${n(conta)} de ${n(total)}` })
      : el('span', { class: 'ctl-nada', texto: '—' });
    if (!sem) return s;
    const ant = nomeDaAnterior(etapa);
    return el('span', {}, s, el('span', { class: 'ctl-a-mais ctl-sem-anterior', texto: ` · ${n(sem)} sem ${ant}`,
      title: `Apontado na ${nomeDaEtapa(etapa)} sem a ${ant} apontada: não conta até apontar a ${ant}` }));
  }
  const _etapas = () => ((ESTADO.dados && ESTADO.dados.etapas) || []).map(e => e.chave);
  const nomeDaEtapa = (k) => (((ESTADO.dados && ESTADO.dados.etapas) || []).find(e => e.chave === k) || { titulo: k }).titulo.toLowerCase();
  const etapaAnterior = (k) => { const ks = _etapas(), i = ks.indexOf(k); return i > 0 ? ks[i - 1] : null; };
  const nomeDaAnterior = (k) => etapaAnterior(k) ? nomeDaEtapa(etapaAnterior(k)) : '';
  /** o que ainda se pode apontar na etapa: o que falta, e na pintura só o que já tem a produção apontada (o servidor recusa
   *  o resto); a montada inteira ou nada */
  function faltaNa(x, k) {
    const ant = etapaAnterior(k);
    if (x.partes) {
      const faltam = x.partes.filter(p => ((p.feito || {})[k] || 0) < 1);
      if (!faltam.length || (ant && faltam.some(p => ((p.feito || {})[ant] || 0) < 1))) return 0;
      return 1;
    }
    const f = x.feito || {};
    const teto = ant ? Math.min(x.quantidade, f[ant] || 0) : x.quantidade;
    return Math.max(0, teto - (f[k] || 0));
  }
  /** falta na etapa, mas espera a etapa de antes */
  const esperaAnterior = (x, k) => !!etapaAnterior(k) && faltaNa(x, k) <= 0
    && (x.partes ? x.partes.some(p => ((p.feito || {})[k] || 0) < 1) : ((x.feito || {})[k] || 0) < x.quantidade);

  /** a tesoura montada (13/11): feita quando todas as partes estão; antes, "1 de 2 partes" */
  function situacaoMontada(x, etapa) {
    const pf = (x.partes_feitas || {})[etapa] || 0, total = x.partes.length;
    const quais = x.partes.filter(p => ((p.conta || {})[etapa] || 0) >= 1).map(p => p.id);
    if (((x.conta || {})[etapa] || 0) >= 1) return el('span', { class: 'ctl-ok', texto: '✓', title: x.partes.map(p => p.id).join(' + ') });
    if (pf > 0) return el('span', { class: 'ctl-meio', texto: `${n(pf)} de ${n(x.partes.length)} partes`,
      title: `feita${quais.length > 1 ? 's' : ''}: ${quais.join(', ')}; falta${total - pf > 1 ? 'm' : ''}: `
        + x.partes.filter(p => !quais.includes(p.id)).map(p => p.id).join(', ') });
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
      seloDaNuvem(D.nuvem);
      if (D.itens) document.dispatchEvent(new CustomEvent('controle:dados', { detail: D }));   // o 3D ao lado (controle3d.js)
    } catch (e) {
      ESTADO.dados = { erro: e.message };
    } finally {
      ESTADO.carregando = false;
    }
    desenhar();
  }

  // a obra compartilhada (13/11, obra_compartilhada.py): o selo da nuvem embaixo do nome; o Leitor não vê Apontar nem Estornar
  const podeApontar = () => { const nv = ESTADO.dados && ESTADO.dados.nuvem; return !nv || nv.pode_apontar !== false; };
  function seloDaNuvem(nv) {
    let p = $('#ctl-nuvem');
    if (!nv) { if (p) p.remove(); return; }
    if (!p) {
      p = el('p', { id: 'ctl-nuvem', style: 'margin:4px 0 0;font-size:12.5px' });
      $('#obra-sub').after(p);
    }
    const papel = nv.papel_nome ? ` · você é ${nv.papel_nome}` : '';
    const fila = nv.pendentes ? ` · ${n(nv.pendentes)} apontamento${nv.pendentes > 1 ? 's' : ''} esperando a internet` : '';
    const dia = nv.quando ? ` (${horaBR(nv.quando)})` : '';
    p.textContent = '☁ Obra compartilhada' + papel + (fila || (nv.erro ? '' : ' · em dia com a nuvem' + dia)) + (nv.erro ? ' — ' + nv.erro : '');
    p.title = 'Os apontamentos desta obra vão para a nuvem e chegam aos computadores de quem tem acesso. Sem internet, ficam aqui e sobem sozinhos depois.';
    p.className = nv.erro || nv.pendentes ? 'ctl-meio' : 'ctl-ok';
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
      && (!ESTADO.filtroEtapa || ((x.conta || {})[ESTADO.filtroEtapa] || 0) < x.quantidade));
    const colunas = [
      ...(podeApontar() ? [{ titulo: '', classe: 'c ctl-marca', cabeca: caixaDeTodos,
        valor: (x) => el('input', { type: 'checkbox', class: 'ctl-marcar', 'data-item': x.id, title: 'Escolher para apontar vários de uma vez',
          checked: ESTADO.marcados.has(x.id), onchange: (ev) => marcar([x.id], ev.target.checked) }) }] : []),
      { titulo: 'Item', chave: 'id', classe: 'b' },
      { titulo: 'Tipo', chave: 'tipo' },
      { titulo: 'Descrição', chave: 'descricao' },
      { titulo: 'Qtd', chave: 'quantidade', classe: 'r', num: true },
      { titulo: 'kg', chave: 'kg', classe: 'r', num: true, casas: 1 },
      ...etapas.map(et => ({ titulo: et.titulo, classe: 'c', valor: (x) => x.partes ? situacaoMontada(x, et.chave)
        : situacaoCelula(x, et.chave) })),
      { titulo: '', classe: 'c', valor: (x) => podeApontar() ? el('button', { type: 'button', class: 'ctl-btn', 'data-item': x.id, texto: 'Apontar', onclick: () => abrirDialogo(x) }) : '' },
    ];
    const kgLinhas = linhas.reduce((s, x) => s + x.kg, 0);
    const quadro = linhas.length
      ? el('div', { class: 'rolagem' }, tabela(colunas, linhas, [...(podeApontar() ? [''] : []), 'TOTAL', '', `${n(linhas.length)} itens`, '', n(kgLinhas, 1), ...etapas.map(() => ''), ''],
        (x) => `${x.id} ${x.tipo} ${x.descricao} ${(x.refs || []).join(' ')}`))
      : vazio('Nenhum item com este filtro.');

    const partes = [cartoes];
    if ((D.fora_da_lista || []).length) {
      partes.push(el('div', { class: 'aviso-topo', id: 'ctl-fora' },
        'Apontamentos de itens que não estão mais na lista de materiais (o detalhamento foi refeito?): ',
        D.fora_da_lista.flatMap((nome, i) => [i ? ', ' : '', el('button', { type: 'button', class: 'ctl-btn', 'data-fora': nome, texto: nome,
          title: 'Ver os apontamentos deste nome e estornar', onclick: () => dialogoHistorico(nome) })]),
        '. Eles continuam guardados; clique no nome para conferir e estornar se for o caso.'));
    }
    if ((D.seguiram || []).length) {
      // o Detalhar renumerou (o número pela ordem dos eixos, 13/11): o apontamento seguiu a peça, não o nome
      const lista = D.seguiram.slice(0, 8).map(s => `${s.era} → ${s.agora}`).join(', ');
      partes.push(el('div', { class: 'aviso-topo', id: 'ctl-seguiram' },
        `${n(D.seguiram.length)} apontamento(s) seguiram a peça depois que o detalhamento mudou os nomes: ${lista}`
        + (D.seguiram.length > 8 ? '…' : '') + '. Nada foi apagado; o histórico mostra o nome de antes.'));
    }
    partes.push(secao('O que se controla', 'cada tesoura/conjunto pela unidade (T38-1, T38-2); as peças avulsas iguais pela posição, com a quantidade',
      el('div', {}, el('div', { class: 'ctl-barra' }, busca, selEtapa, selTipo,
        el('span', { texto: (D.total.montadas ? `${n(D.total.montadas)} tesouras montadas · ` : '')
          + `${n(D.total.unidades_conjunto)} unidades de conjunto · ${n(D.total.itens - D.total.unidades_conjunto - (D.total.montadas || 0))} grupos de peças · ${n(D.total.kg, 1)} kg` })),
        el('div', { class: 'ctl-varios', id: 'ctl-varios', hidden: true }), quadro)));
    partes.push(secao('Últimos apontamentos', 'os 30 mais novos da obra; os de um item, todos, ficam na janela Apontar dele · estorno não apaga, desfaz',
      tabelaEventos(D.eventos || [])));
    corpo.replaceChildren(...partes);
    filtrar();
    marcarLinhas(ESTADO.escolhidos, false);
    faixaDosMarcados();
  }

  // ------------------------------------------------------------------ apontar vários de uma vez (13/11)
  // as caixinhas da lista (ou Ctrl+clique na linha ou numa peça do 3D) escolhem os itens; "Apontar os escolhidos" aponta
  // tudo o que falta na etapa em cada um (as 6 MT71 de uma vez). As peças deles acendem juntas no 3D ao lado.

  const itemPorId = (id) => ((ESTADO.dados && ESTADO.dados.itens) || []).find(x => x.id === id);
  const visiveis = () => [...document.querySelectorAll('#controle-corpo tbody tr[data-item]:not(.oculta)')].map(tr => tr.dataset.item);

  function caixaDeTodos() {
    const c = el('input', { type: 'checkbox', id: 'ctl-marcar-todos', title: 'Escolher todos os itens à vista (o filtro e a busca valem)' });
    c.addEventListener('change', () => marcar(visiveis(), c.checked));
    return c;
  }

  /** põe (sim) ou tira os itens da escolha; sim = null alterna cada um */
  function marcar(ids, sim) {
    for (const id of ids) {
      const quer = sim === null ? !ESTADO.marcados.has(id) : sim;
      if (quer) ESTADO.marcados.add(id); else ESTADO.marcados.delete(id);
    }
    for (const c of document.querySelectorAll('#controle-corpo input.ctl-marcar')) c.checked = ESTADO.marcados.has(c.dataset.item);
    faixaDosMarcados();
    document.dispatchEvent(new CustomEvent('controle:varios', { detail: { ids: [...ESTADO.marcados] } }));
  }

  function faixaDosMarcados() {
    // o que saiu da lista (outro Detalhar) sai da escolha
    if (ESTADO.dados && ESTADO.dados.itens) for (const id of [...ESTADO.marcados]) if (!itemPorId(id)) ESTADO.marcados.delete(id);
    const todos = $('#ctl-marcar-todos');
    if (todos) {
      const vs = visiveis();
      const m = vs.filter(id => ESTADO.marcados.has(id)).length;
      todos.checked = vs.length > 0 && m === vs.length;
      todos.indeterminate = m > 0 && m < vs.length;
    }
    const f = $('#ctl-varios');
    if (!f) return;
    const ids = [...ESTADO.marcados];
    f.hidden = !ids.length;
    if (!ids.length) { f.replaceChildren(); return; }
    const kg = ids.reduce((s, id) => s + (itemPorId(id).kg || 0), 0);
    f.replaceChildren(
      el('b', { texto: `${n(ids.length)} ${ids.length === 1 ? 'item escolhido' : 'itens escolhidos'}` }),
      el('span', { texto: `${n(kg, 1)} kg · ${ids.slice(0, 6).join(', ')}${ids.length > 6 ? '…' : ''}` }),
      el('button', { type: 'button', class: 'ctl-btn principal', id: 'ctl-apontar-varios', texto: 'Apontar os escolhidos…', onclick: dialogoDeVarios }),
      el('button', { type: 'button', class: 'ctl-btn', id: 'ctl-limpar-escolha', texto: 'Limpar a escolha', onclick: () => marcar(ids, false) }));
  }

  function dialogoDeVarios() {
    const D = ESTADO.dados;
    const etapas = D.etapas || [];
    const its = [...ESTADO.marcados].map(itemPorId).filter(Boolean);
    if (!its.length) return;
    const falta = faltaNa;                                   // na pintura, só o produzido
    let etapa = (etapas.find(et => its.some(x => falta(x, et.chave) > 0)) || etapas[0]).chave;
    const dlg = el('dialog', { class: 'ctl-dlg', id: 'ctl-dialogo-varios' });
    const data = el('input', { type: 'date', id: 'ctl-data', value: hojeISO(), max: hojeISO() });
    const obs = el('textarea', { id: 'ctl-obs', rows: '2', maxlength: '300', placeholder: 'opcional' });
    const erro = el('div', { class: 'erro', hidden: true });
    const resumo = el('div', { class: 'nota', id: 'ctl-varios-resumo' });
    const lista = el('div', { class: 'ctl-varios-lista' });
    const confirmar = el('button', { type: 'submit', class: 'principal', id: 'ctl-confirmar', texto: 'Apontar' });
    const ajustar = () => {
      const vao = its.filter(x => falta(x, etapa) > 0);
      const esperam = its.filter(x => esperaAnterior(x, etapa)), pulam = its.length - vao.length - esperam.length;
      const qtd = vao.reduce((s, x) => s + falta(x, etapa), 0);
      const kg = vao.reduce((s, x) => s + falta(x, etapa) * (x.kg_unidade || 0), 0);
      const nome = ((etapas.find(et => et.chave === etapa) || {}).titulo || etapa).toLowerCase();
      resumo.textContent = (vao.length
        ? `Vai apontar na ${nome} tudo o que falta: ${n(vao.length)} item(ns), ${n(qtd)} peça(s)/unidade(s), ${n(kg, 1)} kg.`
          + (pulam ? ` ${n(pulam)} já completo(s) nesta etapa fica(m) de fora.` : '')
        : esperam.length ? `Nada para apontar na ${nome}.` : `Os ${n(its.length)} itens escolhidos já estão completos na ${nome}.`)
        + (esperam.length ? ` ${n(esperam.length)} sem a ${nomeDaAnterior(etapa)} apontada fica(m) de fora: ${esperam.slice(0, 6).map(x => x.id).join(', ')}${esperam.length > 6 ? '…' : ''}.` : '');
      confirmar.disabled = !vao.length;
      confirmar.textContent = vao.length ? `Apontar ${n(vao.length)}` : 'Apontar';
      lista.replaceChildren(el('table', {}, el('tbody', {}, its.map(x => el('tr', { class: falta(x, etapa) ? '' : 'ctl-estornado' },
        el('td', { class: 'b', texto: x.id }), el('td', { texto: x.descricao || x.tipo }),
        el('td', { class: 'r', texto: !falta(x, etapa) ? (esperaAnterior(x, etapa) ? `falta a ${nomeDaAnterior(etapa)}` : 'completo') : x.partes
          ? x.partes.filter(p => ((p.feito || {})[etapa] || 0) < 1).map(p => p.id).join(' + ')
          : `${n(falta(x, etapa))} de ${n(x.quantidade)}` }))))));
    };
    const radios = el('div', { class: 'etapas' }, etapas.map(et => {
      const r = el('input', { type: 'radio', name: 'ctl-etapa', value: et.chave });
      r.checked = et.chave === etapa;
      r.addEventListener('change', () => { etapa = et.chave; ajustar(); });
      return el('label', {}, r, et.titulo);
    }));
    const form = el('form', { method: 'dialog', novalidate: true },
      el('h3', { texto: `Apontar ${n(its.length)} ${its.length === 1 ? 'item' : 'itens'} de uma vez` }),
      el('label', { texto: 'Etapa' }), radios, resumo, lista,
      el('label', { texto: 'Data em que foi feito' }), data,
      el('label', { texto: 'Observação (vai em todos)' }), obs,
      el('div', { class: 'nota', texto: `Quem aponta: ${D.quem || '—'} · cada item vira um apontamento; o estorno desfaz um por um` }),
      erro,
      el('div', { class: 'acoes' }, el('button', { type: 'button', texto: 'Cancelar', onclick: () => dlg.close() }), confirmar));
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (confirmar.disabled) return;
      erro.hidden = true;
      confirmar.disabled = true;
      const vao = its.filter(x => falta(x, etapa) > 0);
      const qtd = vao.reduce((s, x) => s + falta(x, etapa), 0);
      const kg = vao.reduce((s, x) => s + falta(x, etapa) * (x.kg_unidade || 0), 0);
      if (qtd > 1 && !(await confirmarNoDialogo(dlg, form,
        `Apontar ${n(qtd)} peça(s)/unidade(s) em ${n(vao.length)} ${vao.length === 1 ? 'item' : 'itens'} na ${nomeDaEtapa(etapa)} — ${n(kg, 1)} kg?`,
        `${vao.slice(0, 8).map(x => falta(x, etapa) > 1 ? `${n(falta(x, etapa))} × ${x.id}` : x.id).join(', ')}${vao.length > 8 ? '…' : ''} · feito em ${dataBRc(data.value)}`))) {
        confirmar.disabled = false;
        return;
      }
      try {
        const r = await pedir('/api/producao/apontar-varios', { projeto: PROJETO, itens: its.map(x => x.id), etapa, data: data.value, obs: obs.value });
        dlg.close();
        ESTADO.marcados.clear();
        document.dispatchEvent(new CustomEvent('controle:varios', { detail: { ids: [] } }));
        await carregar();
        aviso(`${n(r.eventos.length)} apontamento(s) gravado(s)`
          + (r.pulados.length ? ` · ${n(r.pulados.length)} já estava(m) completo(s): ${r.pulados.slice(0, 6).join(', ')}` : '')
          + ((r.sem_anterior || []).length ? ` · ${n(r.sem_anterior.length)} sem a ${nomeDaAnterior(etapa)} apontada ficou(aram) de fora: ${r.sem_anterior.slice(0, 6).join(', ')}` : ''));
        setTimeout(() => aviso(''), 6000);
      } catch (e) {
        erro.textContent = e.message;
        erro.hidden = false;
        confirmar.disabled = false;
      }
    });
    dlg.append(form);
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    ajustar();
    dlg.showModal();
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

  /** TODOS os apontamentos de um item, com Estornar (risco 2, 13/11: a tabela de baixo mostra só os 30 últimos da obra;
   *  um erro mais velho se desfaz por aqui). Vai na janela Apontar do item e no aviso "fora da lista". */
  function secaoHistorico(itemId) {
    const caixa = el('div', { class: 'ctl-historico', 'data-item': itemId }, el('div', { class: 'nota', texto: 'Lendo os apontamentos do item…' }));
    pedir(`/api/producao/historico?projeto=${encodeURIComponent(PROJETO)}&item=${encodeURIComponent(itemId)}`)
      .then(r => caixa.replaceChildren(r.eventos.length ? tabelaEventos(r.eventos, r.eventos) : vazio('Nenhum apontamento deste item.')))
      .catch(e => caixa.replaceChildren(el('div', { class: 'erro', texto: e.message })));
    return el('div', {}, el('label', { texto: 'Apontamentos deste item (todos, o mais novo em cima)' }), caixa);
  }

  function dialogoHistorico(itemId) {
    const dlg = el('dialog', { class: 'ctl-dlg', id: 'ctl-dialogo-historico' },
      el('h3', { texto: `Apontamentos de ${itemId}` }),
      el('div', { class: 'nota', texto: 'Este nome não está na lista de materiais atual (o detalhamento mudou). Confira e estorne se for o caso.' }),
      secaoHistorico(itemId),
      el('div', { class: 'acoes' }, el('button', { type: 'button', texto: 'Fechar', onclick: () => dlg.close() })));
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
  }

  function tabelaEventos(eventos, doLote) {
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
        el('td', { class: 'b', texto: (e.montada_atual || e.montada ? `${e.montada_atual || e.montada} · ` : '')
          + (e.item_atual ? `${e.item_atual} (era ${e.item})` : e.item),
          title: e.item_atual ? 'O detalhamento mudou o nome; o apontamento seguiu a peça' : null }),
        el('td', { class: 'r', texto: (estorno ? '−' : '') + n(e.quantidade) }),
        el('td', { class: 'r', texto: n(e.kg, 1) }),
        el('td', { class: 'quebra', texto: e.obs || '' }),
        el('td', { class: 'c' }, (!estorno && !e.estornado && podeApontar())
          ? el('button', { type: 'button', class: 'ctl-btn perigo', texto: 'Estornar', onclick: () => estornar(e, doLote) }) : null));
      tb.append(tr);
    }
    return el('div', { class: 'rolagem', style: 'max-height:40vh' }, el('table', {},
      el('thead', {}, el('tr', {}, ['Quando', 'Data', 'Quem', 'Etapa', 'Item', 'Qtd', 'kg', 'Observação', ''].map(t => el('th', { texto: t })))), tb));
  }

  // ------------------------------------------------------------------ a confirmação de mais de 1 unidade (risco 1, 13/11)
  // A quantidade vem cheia com o que falta (fechar o lote é o caso comum), e um Enter apontava os 331 suportes. Agora mais de
  // 1 unidade pede o 2º passo, que diz a quantidade, a marca e os kg. Ele só ARMA depois de ARMAR_MS: o mesmo Enter, a
  // tecla segurada (repetição) e o 2º clique do clique duplo (no Windows, até 500 ms) não confirmam — o D09 do EDITOR 3D
  // foi o clique duplo atravessando o diálogo. 1 unidade segue sem pergunta.
  const ARMAR_MS = 700;
  function confirmarNoDialogo(dlg, form, texto, detalhe) {
    return new Promise((pronto) => {
      let armado = false, fim = false;
      const sim = el('button', { type: 'button', class: 'principal', id: 'ctl-sim', texto: 'Sim, apontar', disabled: true });
      const voltar = el('button', { type: 'button', id: 'ctl-voltar', texto: 'Voltar' });
      const painel = el('div', { class: 'ctl-confirma', id: 'ctl-confirma' },
        el('h3', { texto: 'Confirme o apontamento' }),
        el('p', { class: 'ctl-confirma-texto', texto }),
        detalhe ? el('div', { class: 'nota', texto: detalhe }) : null,
        el('div', { class: 'acoes' }, voltar, sim));
      const teclas = (ev) => {                                // antes de armar, nenhum Enter/Espaço; depois, só tecla nova
        if ((ev.key === 'Enter' || ev.key === ' ') && (!armado || ev.repeat)) { ev.preventDefault(); ev.stopPropagation(); }
      };
      const acabar = (v) => {
        if (fim) return;
        fim = true;
        dlg.removeEventListener('keydown', teclas, true);
        dlg.removeEventListener('close', aoFechar);
        painel.remove();
        form.hidden = false;
        pronto(v);
      };
      const aoFechar = () => acabar(false);
      sim.addEventListener('click', () => { if (armado) acabar(true); });
      voltar.addEventListener('click', () => acabar(false));
      dlg.addEventListener('keydown', teclas, true);
      dlg.addEventListener('close', aoFechar);
      form.hidden = true;
      form.after(painel);                                     // no lugar do formulário (o histórico do item fica embaixo)
      voltar.focus();                                         // o foco sai do campo: o Enter que vier não grava
      setTimeout(() => { if (fim) return; armado = true; sim.disabled = false; sim.focus(); }, ARMAR_MS);
    });
  }

  function abrirDialogo(item) {
    const D = ESTADO.dados;
    const etapas = D.etapas || [];
    const falta = (k) => faltaNa(item, k);                  // na pintura, só o produzido (o servidor recusa o resto)
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
      const faltamPartes = (item.partes || []).filter(p => ((p.feito || {})[etapa] || 0) < 1).map(p => p.id);
      const nome = nomeDaEtapa(etapa), ant = nomeDaAnterior(etapa);
      const naEtapa = item.quantidade - ((item.feito || {})[etapa] || 0);   // o que falta, sem olhar a etapa de antes
      dica.textContent = esperaAnterior(item, etapa) ? `falta apontar a ${ant} antes da ${nome}`
          + (item.partes ? '' : ` (${n(naEtapa)} sem ${nome}, nenhuma com a ${ant} apontada)`)
        : f <= 0 ? `já está completo na ${nome}`
        : item.partes ? `a montada inteira: aponta ${faltamPartes.join(' + ')} (o que falta na ${nome})`
        : `faltam ${n(naEtapa)} de ${n(item.quantidade)} na ${nome}`
          + (f < naEtapa ? ` — só ${n(f)} com a ${ant} apontada podem ir agora` : '');
      if (confirmar) confirmar.disabled = f <= 0;
    };
    let confirmar = null;
    const radios = el('div', { class: 'etapas' }, etapas.map(et => {
      const r = el('input', { type: 'radio', name: 'ctl-etapa', value: et.chave });
      r.checked = et.chave === etapa;
      r.addEventListener('change', () => { etapa = et.chave; ajustar(); });
      return el('label', {}, r, et.titulo);
    }));
    confirmar = el('button', { type: 'submit', class: 'principal', id: 'ctl-confirmar', texto: 'Apontar' });
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
      if (confirmar.disabled) return;
      erro.hidden = true;
      const q = Number(qtd.value || (item.quantidade === 1 ? 1 : 0));
      confirmar.disabled = true;
      if (q > 1 && !(await confirmarNoDialogo(dlg, form, `Apontar ${n(q)} × ${item.id} na ${nomeDaEtapa(etapa)} — ${n(q * (item.kg_unidade || 0), 1)} kg?`,
        `${item.descricao || item.tipo} · ${n(q)} de ${n(item.quantidade)} · feito em ${dataBRc(data.value)}`))) {
        confirmar.disabled = false;
        return;
      }
      try {
        await pedir('/api/producao/apontar', { projeto: PROJETO, item: item.id, etapa, quantidade: q,
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
    dlg.append(form, secaoHistorico(item.id));
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    ajustar();
    dlg.showModal();
  }

  async function estornar(e, doLote) {
    const titulo = Object.fromEntries((ESTADO.dados.etapas || []).map(x => [x.chave, x.titulo]));
    const lote = e.lote ? (doLote || ESTADO.dados.eventos || []).filter(x => x.lote === e.lote && !x.estorno_de).map(x => x.item) : [];
    const oque = lote.length > 1 ? `da tesoura montada ${e.montada} (${lote.join(' + ')}, apontadas juntas)` : `de ${e.item}`;
    if (!confirm(`Estornar o apontamento ${oque} (${titulo[e.etapa] || e.etapa}, ${e.quantidade}, de ${dataBRc(e.data)})? Ele continua no histórico, riscado.`)) return;
    try {
      await pedir('/api/producao/estornar', { projeto: PROJETO, evento: e.id });
      for (const d of document.querySelectorAll('dialog.ctl-dlg[open]')) d.close();   // a janela do item mostrava o antes
      await carregar();
      aviso(`Estornado: ${e.item} (${titulo[e.etapa] || e.etapa}, ${e.quantidade})`);
      setTimeout(() => aviso(''), 6000);
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
      if ((ev.ctrlKey || ev.shiftKey || ev.metaKey) && podeApontar()) { marcar([tr.dataset.item], null); return; }   // soma à escolha de vários
      marcarLinhas([tr.dataset.item], false);
      document.dispatchEvent(new CustomEvent('controle:item', { detail: { id: tr.dataset.item } }));
    });
    document.addEventListener('controle:marcar', (ev) => marcarLinhas(ev.detail.ids, true));
    document.addEventListener('controle:alternar', (ev) => {         // Ctrl+clique numa peça do 3D
      if (!podeApontar()) return;
      const ids = ev.detail.ids || [];
      marcar(ids, !ids.every(id => ESTADO.marcados.has(id)));
      marcarLinhas(ids.filter(id => ESTADO.marcados.has(id)), true);
    });
    desenhar();
    carregar();
    // a obra compartilhada: o que os outros apontaram chega sozinho, a cada minuto (não no meio de um apontamento)
    setInterval(() => {
      const D = ESTADO.dados;
      if (D && D.nuvem && !document.hidden && !document.querySelector('dialog[open]')) carregar();
    }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
