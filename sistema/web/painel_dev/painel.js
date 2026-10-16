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

  function iniciais(c) {
    if (c.nome) return c.nome.split('-').pop().toUpperCase();
    return (c.titulo || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase();
  }
  function avatar(c, pend) {
    return el('div', { class: 'pd-avatar ' + (c.estado || ''), title: ESTADO[c.estado] || '' }, iniciais(c),
      pend ? el('span', { class: 'balao', texto: '?', title: 'tem uma pergunta para você na caixa de entrada' }) : null);
  }
  const vscode = (id) => 'vscode://anthropic.claude-code/open?session=' + encodeURIComponent(id);

  function card(c) {
    const quentes = new Set((dados.alertas || []).filter(a => a.tipo === 'conflito').map(a => a.texto.replace(/^.* editaram (.*) e ele está sem commit$/, '$1')));
    const corpo = [
      el('div', { class: 'pd-mesa-cab' }, avatar(c, c.pendencia), el('div', { style: 'flex:1;min-width:0' },
      el('div', { class: 'pd-cab' },
        c.nome ? el('span', { class: 'pd-nome', texto: c.nome, title: 'o nome curto que os outros chats usam' }) : null,
        el('span', { class: 'pd-titulo', texto: c.titulo }),
        el('span', { class: 'pd-estado ' + c.estado, texto: `${ESTADO[c.estado] || c.estado} · ${ha(c.parado_s)}`,
                     title: c.estado === 'parado' ? 'não terminou a vez e não mexe há alguns minutos: pode estar esperando uma permissão ou numa conta longa' : '' })),
        c.estado === 'trabalhando' && c.ferramenta ? el('div', { class: 'pd-rot', texto: 'agora: ' + c.ferramenta }) : null)),
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
      el('a', { href: vscode(c.id), class: 'botao', texto: 'Abrir no VS Code', title: 'foca a aba deste chat no VS Code' }),
      el('button', { type: 'button', texto: 'Copiar id', title: 'o id da sessão (para /resume no Claude Code)', onclick: (ev) => { ev.stopPropagation(); navigator.clipboard && navigator.clipboard.writeText(c.id); } })));
    return el('article', { class: `pd-card ${c.estado}` + (filtro === c.id ? ' selecionado' : ''), id: 'chat-' + c.id }, corpo);
  }

  // ------------------------------------------------------------ caixa de entrada
  const naCaixa = new Map();          // chave → elemento: a atualização não refaz o que você está digitando
  async function postar(rota, corpo) {
    const r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.erro) throw new Error(d.erro || r.statusText);
    return d;
  }
  function itemCaixa(i) {
    const c = (dados.chats || []).find(x => x.id === i.sessao) || { id: i.sessao, nome: i.nome, titulo: i.titulo, estado: 'sua_vez' };
    const status = el('span', { class: 'dica' });
    const erro = el('div', { class: 'pd-erro', hidden: true });
    const tipo = i.tipo === 'pergunta' ? 'pergunta' : i.tipo === 'permissao' ? 'pedindo permissão' : 'terminou a vez';
    const corpo = [el('div', { class: 'pd-cab' },
      c.nome ? el('span', { class: 'pd-nome', texto: c.nome }) : null,
      el('span', { class: 'pd-titulo', texto: c.titulo || i.titulo }),
      el('span', { class: 'pd-estado sua_vez', texto: `${tipo} · ${hora(i.t)}` }))];
    let caixaEl = null;
    const enviar = async (carga, botao) => {
      erro.hidden = true; if (botao) botao.disabled = true;
      try {
        await postar('/api/dev/chats/responder', { id: i.sessao, token: i.token, ...carga });
        status.textContent = '✓ enviada — o chat vai continuar em alguns segundos';
        caixaEl.classList.add('enviada');
        try { sessionStorage.removeItem('pd-rascunho-' + i.token); } catch (e) { /* privado */ }
      } catch (e) { erro.textContent = e.message; erro.hidden = false; if (botao) botao.disabled = false; }
    };
    if (i.tipo === 'permissao') {
      corpo.push(el('div', { class: 'msg', texto: i.texto || 'O chat está pedindo permissão para usar uma ferramenta.' }),
        el('div', { class: 'linha-acoes' }, el('a', { href: vscode(i.sessao), class: 'botao principal', texto: 'Abrir no VS Code para aprovar' }),
          el('span', { class: 'dica', texto: 'aprovar ou negar continua no VS Code' })));
    } else if (i.tipo === 'pergunta') {
      const escolhas = {};
      for (const q of i.perguntas) {
        const outra = el('input', { type: 'text', placeholder: 'outra resposta (opcional)', style: 'width:100%;box-sizing:border-box;padding:6px 8px' });
        const ops = el('div', { class: 'pd-op' }, (q.options || []).map(o => {
          const b = el('button', { type: 'button' }, el('b', { texto: o.label }), o.description ? el('small', { texto: o.description }) : null);
          b.addEventListener('click', () => {
            const atual = new Set((escolhas[q.question] || '').split(', ').filter(Boolean));
            if (q.multiSelect) { if (atual.has(o.label)) atual.delete(o.label); else atual.add(o.label); }
            else { atual.clear(); atual.add(o.label); }
            escolhas[q.question] = [...atual].join(', ');
            outra.value = '';
            for (const x of ops.children) x.classList.toggle('escolhida', atual.has(x.querySelector('b').textContent));
          });
          return b;
        }));
        outra.addEventListener('input', () => {
          if (outra.value.trim()) { escolhas[q.question] = outra.value.trim(); for (const x of ops.children) x.classList.remove('escolhida'); }
        });
        corpo.push(el('div', { class: 'pd-q', texto: q.question }), ops, outra);
      }
      const ok = el('button', { type: 'button', class: 'principal', texto: 'Enviar' });
      ok.addEventListener('click', () => {
        const falta = i.perguntas.find(q => !escolhas[q.question]);
        if (falta) { erro.textContent = 'Responda: ' + falta.question; erro.hidden = false; return; }
        enviar({ respostas: escolhas }, ok);
      });
      const resta = i.prazo ? Math.max(0, Math.round((i.prazo - Date.now() / 1000) / 60)) : null;
      corpo.push(el('div', { class: 'linha-acoes' }, ok, el('a', { href: vscode(i.sessao), class: 'botao', texto: 'Responder no VS Code' }),
        status, el('span', { class: 'dica', texto: resta != null ? `sem resposta aqui, em ${resta} min a pergunta aparece no VS Code` : '' })));
    } else {
      const msg = el('div', { class: 'msg', texto: i.texto || '(sem texto)' });
      const ver = el('button', { type: 'button', texto: 'ver tudo' });
      ver.addEventListener('click', () => { msg.classList.toggle('aberta'); ver.textContent = msg.classList.contains('aberta') ? 'recolher' : 'ver tudo'; });
      const caixaTexto = el('textarea', { placeholder: 'Sua resposta para este chat (Ctrl+Enter envia)' });
      try { caixaTexto.value = sessionStorage.getItem('pd-rascunho-' + i.token) || ''; } catch (e) { /* privado */ }
      caixaTexto.addEventListener('input', () => { try { sessionStorage.setItem('pd-rascunho-' + i.token, caixaTexto.value); } catch (e) { /* privado */ } });
      const ok = el('button', { type: 'button', class: 'principal', texto: 'Enviar' });
      const mandar = () => { if (caixaTexto.value.trim()) enviar({ texto: caixaTexto.value }, ok); };
      ok.addEventListener('click', mandar);
      caixaTexto.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); mandar(); } });
      const dispensar = el('button', { type: 'button', texto: 'Tirar da caixa', title: 'não precisa de resposta agora (o chat continua parado)' });
      dispensar.addEventListener('click', async () => {
        try { await postar('/api/dev/chats/descartar', { id: i.sessao, token: i.token }); caixaEl.remove(); naCaixa.delete(i.token); }
        catch (e) { erro.textContent = e.message; erro.hidden = false; }
      });
      corpo.push(msg, caixaTexto, el('div', { class: 'linha-acoes' }, ok, ver, el('a', { href: vscode(i.sessao), class: 'botao', texto: 'Abrir no VS Code' }), dispensar, status));
    }
    corpo.push(erro);
    caixaEl = el('article', { class: 'pd-pend ' + i.tipo + (i.enviada ? ' enviada' : '') }, avatar(c, false), el('div', {}, corpo));
    caixaEl._status = status;
    return caixaEl;
  }
  function desenharCaixa() {
    const itens = dados.caixa || [];
    const chave = (i) => i.token || ('perm-' + i.sessao + '-' + i.t);
    const vivos = new Set(itens.map(chave));
    for (const [k, e] of naCaixa) if (!vivos.has(k)) { e.remove(); naCaixa.delete(k); }
    const lugar = $('#caixa');
    for (const i of itens) {
      let e = naCaixa.get(chave(i));
      if (!e) { e = itemCaixa(i); naCaixa.set(chave(i), e); lugar.append(e); }
      if (i.nao_entregue) e._status.textContent = '⚠ o chat não pegou a resposta (fechado ou reaberto?): mande pelo VS Code';
      else if (i.enviada) { e._status.textContent = '✓ enviada — esperando o chat pegar'; e.classList.add('enviada'); }
    }
    $('#caixa-sec').hidden = !itens.length;
    $('#caixa-n').textContent = itens.length;
    document.title = (itens.length ? `(${itens.length}) ` : '') + 'Painel DEV — Metálica';
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
    desenharCaixa();
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
