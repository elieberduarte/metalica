/* Painel DEV: os chats do Claude Code deste projeto (painel_dev/chats.py). Atualiza a cada 15 s; só lê. */
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const ESTADO = { trabalhando: 'trabalhando', sua_vez: 'sua vez', parado: 'parado', inativo: 'inativo' };
  let dados = null, filtro = null, horas = 24;
  try { horas = +localStorage.getItem('painel-dev.horas') || 24; } catch (e) { /* privado */ }

  function el(tag, attrs, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'texto') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    for (const f of filhos.flat()) if (f != null && f !== false) e.append(f.nodeType ? f : document.createTextNode(String(f)));
    return e;
  }
  const hora = (t) => t ? new Date(t * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
  function ha(s) {
    if (s == null) return '';
    if (s < 60) return 'agora';
    if (s < 3600) return `há ${Math.round(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
    return `há ${Math.round(s / 86400)} dia(s)`;
  }
  const rotulo = (c) => c.nome || c.titulo;

  function card(c) {
    const quentes = new Set((dados.alertas || []).filter(a => a.tipo === 'conflito').map(a => a.texto.replace(/^.* editaram (.*) e ele está sem commit$/, '$1')));
    const corpo = [
      el('div', { class: 'pd-cab' },
        c.nome ? el('span', { class: 'pd-nome', texto: c.nome, title: 'o nome curto que os outros chats usam' }) : null,
        el('span', { class: 'pd-titulo', texto: c.titulo }),
        el('span', { class: 'pd-estado ' + c.estado, texto: `${ESTADO[c.estado] || c.estado} · ${ha(c.parado_s)}`,
                     title: c.estado === 'parado' ? 'não terminou a vez e não mexe há alguns minutos: pode estar esperando uma permissão ou numa conta longa' : '' })),
      c.ultimo_pedido ? el('div', { class: 'pd-bloco' }, el('div', { class: 'pd-rot' }, 'Você pediu ', el('span', { texto: hora(c.t_pedido) })),
                           el('div', { class: 'pd-txt', texto: c.ultimo_pedido })) : null,
      c.ultima_resposta ? el('div', { class: 'pd-bloco' }, el('div', { class: 'pd-rot' }, 'Última resposta ', el('span', { texto: hora(c.t_resposta) })),
                             el('div', { class: 'pd-txt', texto: c.ultima_resposta })) : null,
    ];
    if (c.sem_commit.length) {
      corpo.push(el('div', { class: 'pd-bloco' }, el('div', { class: 'pd-rot', texto: `Editou e está sem commit (${c.sem_commit.length})` }),
        el('div', { class: 'pd-chips' }, c.sem_commit.slice(0, 14).map(a => el('span', { class: 'pd-chip' + (quentes.has(a) ? ' quente' : ''), texto: a.replace(/^sistema\//, ''),
          title: quentes.has(a) ? 'outro chat também editou este arquivo' : a })))));
    }
    if (c.commits.length) {
      corpo.push(el('div', { class: 'pd-bloco' }, el('div', { class: 'pd-rot', texto: `Commits (${c.commits.length})` }),
        el('ul', { class: 'pd-lista' }, c.commits.slice(0, 3).map(x => el('li', { texto: `${hora(x.t)} — ${x.texto}` })))));
    }
    if (c.agentes.length) {
      corpo.push(el('div', { class: 'pd-bloco' }, el('div', { class: 'pd-rot', texto: `Agentes (${c.agentes.length})` }),
        el('div', { class: 'pd-chips' }, c.agentes.slice(0, 8).map(a => el('span', {
          class: 'pd-chip ag-' + (a.estado || 'rodando').replace(/\s/g, '-'), texto: `${a.descricao || a.id} · ${a.estado || ''}`,
          title: (a.modelo ? 'modelo ' + a.modelo + ' · ' : '') + (a.relatorio || '') })))));
    }
    corpo.push(el('div', { class: 'pd-acoes' },
      el('button', { type: 'button', texto: `Mensagens (${c.enviadas} ↑ ${c.recebidas} ↓)`, onclick: (ev) => { ev.stopPropagation(); mensagens(c); } }),
      el('button', { type: 'button', texto: filtro === c.id ? 'Mostrar a linha de todos' : 'Só este na linha do tempo',
                     onclick: (ev) => { ev.stopPropagation(); filtro = filtro === c.id ? null : c.id; desenhar(); } }),
      el('button', { type: 'button', texto: 'Copiar id', title: 'o id da sessão (para /resume no Claude Code)', onclick: (ev) => { ev.stopPropagation(); navigator.clipboard && navigator.clipboard.writeText(c.id); } })));
    return el('article', { class: `pd-card ${c.estado}` + (filtro === c.id ? ' selecionado' : ''), id: 'chat-' + c.id }, corpo);
  }

  async function mensagens(c) {
    const d = await (await fetch('/api/dev/chats/mensagens?id=' + encodeURIComponent(c.id), { cache: 'no-store' })).json();
    const todas = [...(d.enviadas || []).map(m => ({ ...m, dir: 'saiu' })), ...(d.recebidas || []).map(m => ({ ...m, dir: 'chegou' }))]
      .sort((a, b) => (b.t || 0) - (a.t || 0));
    $('#dlg-titulo').textContent = `Mensagens de ${rotulo(c)} com os outros chats e agentes`;
    $('#dlg-corpo').replaceChildren(...(todas.length ? todas.map(m => el('div', { class: 'pd-msg ' + m.dir },
      el('div', { class: 'cab', texto: `${hora(m.t)} · ${m.dir === 'saiu' ? '→ para ' + (m.para || '') : '← de ' + (m.de || '')}${m.resumo ? ' · ' + m.resumo : ''}` }),
      el('div', { texto: m.texto }))) : [el('div', { class: 'pd-vazio', texto: 'nenhuma mensagem trocada' })]));
    $('#dlg-msgs').showModal();
  }

  function desenhar() {
    const d = dados;
    const ativos = d.chats.filter(c => c.estado !== 'inativo');
    const inativos = d.chats.filter(c => c.estado === 'inativo');
    const n = (e) => d.chats.filter(c => c.estado === e).length;
    const conflitos = d.alertas.filter(a => a.tipo === 'conflito').length;
    const horasSel = el('select', { onchange: (ev) => { horas = +ev.target.value; try { localStorage.setItem('painel-dev.horas', horas); } catch (e) { /* privado */ } carregar(); } },
      [[6, '6 h'], [24, '24 h'], [72, '3 dias'], [168, '7 dias']].map(([v, t]) => el('option', { value: v, texto: t, selected: v === horas ? 'selected' : null })));
    $('#resumo').replaceChildren(
      el('div', { class: 'pd-num verde' }, el('b', { texto: n('trabalhando') }), 'trabalhando'),
      el('div', { class: 'pd-num amarelo' }, el('b', { texto: n('sua_vez') }), 'esperando você'),
      el('div', { class: 'pd-num' }, el('b', { texto: n('parado') }), 'parados'),
      el('div', { class: 'pd-num verm' }, el('b', { texto: conflitos }), 'arquivos em conflito'),
      el('div', { class: 'pd-num' }, el('b', { texto: d.chats.reduce((s, c) => s + c.agentes.filter(a => a.estado === 'rodando').length, 0) }), 'agentes rodando'),
      el('div', { class: 'dir' }, 'janela', horasSel, `· atualizado ${hora(d.agora)}`));
    $('#alertas').replaceChildren(...d.alertas.map(a => el('div', {
      class: 'pd-alerta ' + a.tipo, onclick: a.id ? () => { const e = document.getElementById('chat-' + a.id); if (e) e.scrollIntoView({ behavior: 'smooth', block: 'center' }); } : null },
      el('b', { texto: a.chat }), el('span', { texto: a.texto }))));
    $('#chats').replaceChildren(...(ativos.length ? ativos.map(card) : [el('div', { class: 'pd-vazio', texto: 'nenhum chat ativo nesta janela' })]));
    $('#inativos-titulo').textContent = `Inativos (${inativos.length})`;
    $('#inativos').replaceChildren(...inativos.map(card));
    const alvo = filtro && d.chats.find(c => c.id === filtro);
    const chave = alvo ? rotulo(alvo) : null;
    $('#filtro-linha').textContent = alvo ? '· ' + chave : '';
    $('#limpar-filtro').hidden = !alvo;
    const evs = d.linha.filter(x => !chave || x.chat === chave || x.para === chave);
    $('#linha').replaceChildren(...(evs.length ? evs.map(x => el('div', { class: 'pd-ev', title: x.completo || '' },
      el('time', { texto: hora(x.t) }),
      el('div', {}, el('span', { class: 'tipo ' + x.tipo, texto: x.tipo }), el('span', { class: 'quem', texto: x.chat + (x.para ? ' → ' + x.para : '') }),
         el('div', { class: 'txt', texto: x.texto })))) : [el('div', { class: 'pd-vazio', texto: 'nada nesta janela' })]));
    $('#frentes').replaceChildren(d.frentes.length ? el('table', { class: 'pd-frentes' },
      el('tr', {}, el('th', { texto: 'Briefing' }), el('th', { texto: 'Itens' }), el('th', { texto: 'Em commits' })),
      ...d.frentes.map(f => el('tr', { title: f.estado || '' },
        el('td', {}, f.arquivo.replace(/^Briefing-/, '').replace(/\.md$/, ''), ...f.decisoes.slice(0, 2).map(x => el('div', { class: 'dec', texto: '⚑ ' + x }))),
        el('td', { texto: f.itens || '—' }), el('td', { texto: f.itens ? f.citados : '—' })))) : el('div', { class: 'pd-vazio', texto: 'nenhum briefing desta semana' }));
  }

  async function carregar() {
    try {
      const r = await fetch('/api/dev/chats?horas=' + horas, { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok || d.erro) throw new Error(d.erro || r.statusText);
      dados = d;
      $('#erro').replaceChildren();
      desenhar();
    } catch (e) {
      $('#erro').replaceChildren(el('div', { class: 'pd-erro', texto: 'Não consegui ler os chats: ' + e.message }));
    }
  }
  $('#limpar-filtro').addEventListener('click', () => { filtro = null; desenhar(); });
  $('#btn-tema').addEventListener('click', () => {
    const atual = document.documentElement.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
    const novo = atual === 'escuro' ? 'claro' : 'escuro';
    document.documentElement.setAttribute('data-tema', novo);
    try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* privado */ }
  });
  carregar();
  setInterval(() => { if (!document.hidden && !$('#dlg-msgs').open) carregar(); }, 15000);
})();
