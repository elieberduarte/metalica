/* A barra do projeto: a mesma em todas as telas de um projeto (área de trabalho, orçamento e materiais, comercial,
 * análise, memorial, esforços, treliças). A obra em seis etapas, na ordem em que acontece (decisão de 03/10/2026):
 * Entrada · Modelo 3D (com o cálculo) · Comercial (orçamento, proposta, contrato) · Detalhamento · Produção · Obra.
 * Clicar na etapa vai para a tela dela; o ▾ abre os atalhos. À direita, a busca única (Ctrl+K: comandos de todos os
 * menus, as etapas, os botões da tela aberta, a Biblioteca e as peças do modelo) e a Biblioteca.
 * Dados: GET /api/projetos/<slug>/etapas (saida/etapas_projeto.py). Um comando de menu pedido de outra tela abre a
 * área de trabalho com ?menu=Arquivo›Importar›… e é executado lá (barra_unica.js). */
(function () {
  'use strict';
  if (window.top !== window) return;                         // dentro dos quadros 2D/3D da área de trabalho: nada
  var PROJETO = new URLSearchParams(location.search).get('projeto') || '';
  if (!PROJETO) return;
  var DADOS = null, ABERTO = null;
  var NA_AREA = function () { return !!document.getElementById('menus-unicos'); };

  var CSS = [
    '.barra-etapas{display:flex;align-items:center;gap:6px;height:36px;padding:0 10px;flex-shrink:0;background:#0a1322;color:#cbd5e1;',
    'border-bottom:1px solid rgba(255,255,255,.08);font:12.5px/1 "Segoe UI",Arial,sans-serif;position:relative;z-index:60}',
    '.barra-etapas .be-casa{border:1px solid rgba(255,255,255,.14);background:none;color:#cbd5e1;border-radius:5px;height:26px;width:28px;cursor:pointer;display:grid;place-items:center}',
    '.barra-etapas .be-casa:hover{color:#fff;border-color:rgba(255,255,255,.3)}',
    '.barra-etapas .be-nome{font-weight:600;color:#e2e8f0;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-right:6px}',
    '.barra-etapas .be-trilho{display:flex;align-items:center;gap:1px;flex:1;min-width:0;overflow:hidden}',
    '.barra-etapas .be-seta{color:#475569;font-size:12px;margin:0 1px}',
    '.barra-etapas .be-etapa{display:inline-flex;align-items:center;border-radius:99px;border:1px solid transparent;white-space:nowrap}',
    '.barra-etapas .be-etapa:hover{background:rgba(255,255,255,.06)}',
    '.barra-etapas .be-etapa.ativa{background:#1c3260;border-color:#2f4f8f;color:#fff}',
    '.barra-etapas .be-ir{display:inline-flex;align-items:center;gap:6px;background:none;border:0;color:inherit;font:inherit;padding:4px 4px 4px 7px;cursor:pointer}',
    '.barra-etapas .be-mais{background:none;border:0;color:#64748b;font:inherit;padding:4px 7px 4px 2px;cursor:pointer}',
    '.barra-etapas .be-mais:hover{color:#e2e8f0}',
    '.barra-etapas .be-bola{width:16px;height:16px;border-radius:50%;display:inline-grid;place-items:center;font-size:9.5px;font-weight:700;border:1.5px solid #64748b;color:#64748b}',
    '.barra-etapas .feita .be-bola{background:#3fbf7f;border-color:#3fbf7f;color:#0a1322}',
    '.barra-etapas .andamento .be-bola{border-color:#e3b341;color:#e3b341}',
    '.barra-etapas .be-busca{display:flex;align-items:center;gap:8px;height:26px;width:200px;padding:0 9px;border:1px solid rgba(255,255,255,.14);border-radius:5px;color:#94a3b8;cursor:text;flex-shrink:0;white-space:nowrap}',
    '.barra-etapas .be-busca:hover{border-color:rgba(255,255,255,.3)}',
    '.barra-etapas .be-busca kbd{margin-left:auto;font:10.5px Consolas,monospace;border:1px solid rgba(255,255,255,.18);border-radius:3px;padding:0 4px}',
    '.barra-etapas .be-bib{background:none;border:1px solid rgba(255,255,255,.14);color:#cbd5e1;border-radius:5px;height:26px;padding:0 10px;cursor:pointer;font:inherit;flex-shrink:0}',
    '.be-lista{position:fixed;min-width:260px;background:#131f33;color:#e2e8f0;border:1px solid #26385a;border-radius:7px;box-shadow:0 14px 40px rgba(0,0,0,.45);padding:5px;z-index:1000;font:13px "Segoe UI",Arial,sans-serif}',
    '.be-lista .be-it{display:block;width:100%;text-align:left;background:none;border:0;color:inherit;font:inherit;padding:7px 10px;border-radius:5px;cursor:pointer}',
    '.be-lista .be-it:hover{background:#1c2c48}',
    '.be-lista .be-it small{display:block;color:#7f93b3;font-size:11.5px;margin-top:2px}',
    '.be-lista .be-tit{padding:6px 10px 4px;color:#7f93b3;font-size:11px;text-transform:uppercase;letter-spacing:.07em}',
    '.be-fundo{position:fixed;inset:0;background:rgba(5,10,20,.5);z-index:2000;display:none}',
    '.be-fundo.on{display:block}',
    '.be-paleta{position:fixed;top:80px;left:50%;transform:translateX(-50%);width:660px;max-width:94vw;background:#131f33;color:#e2e8f0;border:1px solid #26385a;border-radius:10px;',
    'box-shadow:0 30px 80px rgba(0,0,0,.6);overflow:hidden;font:13px "Segoe UI",Arial,sans-serif}',
    '.be-paleta input{width:100%;box-sizing:border-box;font:15px "Segoe UI",Arial;padding:14px 16px;background:#182741;border:0;border-bottom:1px solid #26385a;color:#e2e8f0;outline:none}',
    '.be-paleta .be-res{max-height:430px;overflow:auto;padding:6px}',
    '.be-paleta .be-r{display:grid;grid-template-columns:92px 1fr auto;gap:10px;align-items:baseline;padding:8px 10px;border-radius:6px;cursor:pointer}',
    '.be-paleta .be-r.sel,.be-paleta .be-r:hover{background:#1c3260}',
    '.be-paleta .be-tipo{font-size:10.5px;color:#7f93b3;text-transform:uppercase;letter-spacing:.06em}',
    '.be-paleta .be-cam{color:#7f93b3;font-size:11.5px;max-width:270px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.be-paleta .be-vazio{padding:16px;color:#7f93b3}',
    '.be-paleta .be-rod{padding:7px 12px;border-top:1px solid #26385a;color:#7f93b3;font-size:11.5px}',
    '@media print{.barra-etapas{display:none!important}}',
    // o que a barra substitui nos cabeçalhos das telas: a casa, o nome do projeto e os botões de ir para outra tela
    'body.com-etapas #btn-inicio,body.com-etapas #nome-projeto,body.com-etapas header.topo #btn-3d:not([title*="destaque"]),body.com-etapas #btn-cad,body.com-etapas #btn-materiais,',
    "body.com-etapas header.topo button[onclick*=\"location.href='/'\"]{display:none!important}",
  ].join('\n');

  function el(tag, attrs) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) {
      var v = attrs[k];
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v; else if (k === 'texto') e.textContent = v;
      else if (k.indexOf('on') === 0 && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (var i = 2; i < arguments.length; i++) {
      var f = arguments[i];
      if (f === null || f === undefined || f === false) continue;
      (Array.isArray(f) ? f : [f]).forEach(function (x) { if (x !== null && x !== undefined) e.append(x.nodeType ? x : document.createTextNode(String(x))); });
    }
    return e;
  }

  // ------------------------------------------------------------ que etapa é esta tela
  function etapaAtiva() {
    var p = location.pathname, h = (location.hash || '').slice(1);
    if (/^\/(dividida|2d-3d)/.test(p)) {
      var v = window.vistaAtual ? window.vistaAtual() : (new URLSearchParams(location.search).get('vista') || 'ambos');
      return v === '2d' ? 'detalhamento' : 'modelo';
    }
    if (/^\/(materiais|lista-de-materiais)/.test(p)) return h === 'orcamento' ? 'comercial' : 'producao';
    if (/^\/(comercial|proposta|contrato)/.test(p)) return h === 'obra' ? 'obra' : 'comercial';
    if (/^\/(analise|resultado|memorial|esforcos|trelicas|dimensionar)/.test(p)) return 'modelo';
    return '';
  }

  // ------------------------------------------------------------ ações
  function caminhoTexto(c) { return c.join(' › '); }
  function acharNoMapa(caminho) {
    var mapa = (window.barraUnica && window.barraUnica.mapa) || [];
    var menu = mapa.filter(function (m) { return m.nome === caminho[0]; })[0];
    var itens = menu ? menu.itens : [];
    var it = null;
    for (var i = 1; i < caminho.length; i++) {
      it = (itens || []).filter(function (x) { return x && typeof x === 'object' && x.texto === caminho[i]; })[0];
      if (!it) return null;
      itens = it.sub;
    }
    return it;
  }
  function executarMenu(caminho) {
    if (NA_AREA() && window.barraUnica && window.barraUnica.executar) {
      var it = acharNoMapa(caminho);
      if (it) { window.barraUnica.executar(it); return; }
    }
    location.href = '/dividida?projeto=' + encodeURIComponent(PROJETO) + '&menu=' + encodeURIComponent(caminhoTexto(caminho));
  }
  function executarItem(x) {
    fecharLista();
    if (x.menu) executarMenu(x.menu);
    else if (x.link) { if (x.nova) window.open(x.link, '_blank', 'noopener'); else irPara(x.link); }
    else if (x.botao) x.botao.click();
    else if (x.peca) procurarPeca(x.peca);
  }
  function irPara(url) {
    // a mesma tela com outra aba (#): só troca o hash e avisa a tela
    var a = document.createElement('a'); a.href = url;
    if (a.pathname === location.pathname && a.search === location.search && a.hash !== location.hash) { location.hash = a.hash; return; }
    if (/^\/dividida/.test(a.pathname) && NA_AREA()) {
      var vista = new URLSearchParams(a.search).get('vista');
      if (vista && window.mostrarVista) { window.mostrarVista(vista); desenhar(); return; }
    }
    location.href = url;
  }
  function procurarPeca(q) {
    var campo = document.getElementById('busca-campo');
    if (!campo || !NA_AREA()) { location.href = '/dividida?projeto=' + encodeURIComponent(PROJETO) + '&vista=3d&peca=' + encodeURIComponent(q); return; }
    if (window.mostrarVista && window.vistaAtual && window.vistaAtual() === '2d') window.mostrarVista('3d');
    campo.value = q;
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    campo.focus();
  }

  // ------------------------------------------------------------ a barra
  function desenhar() {
    var barra = document.getElementById('barra-etapas');
    if (!barra || !DADOS) return;
    var ativa = etapaAtiva();
    var trilho = el('div', { class: 'be-trilho' });
    DADOS.etapas.forEach(function (e, i) {
      if (i) trilho.append(el('span', { class: 'be-seta', texto: '›' }));
      var pill = el('span', { class: 'be-etapa ' + (e.situacao || '') + (e.chave === ativa ? ' ativa' : ''), title: e.dica || '' },
        el('button', { type: 'button', class: 'be-ir', onclick: function () { irPara(e.url); } },
          el('span', { class: 'be-bola', texto: e.situacao === 'feita' ? '✓' : String(i + 1) }), e.nome),
        el('button', { type: 'button', class: 'be-mais', title: 'Atalhos de ' + e.nome, 'aria-label': 'Atalhos de ' + e.nome,
          onclick: function (ev) { ev.stopPropagation(); abrirLista(ev.currentTarget, e.nome, e.itens); } }, '▾'));
      trilho.append(pill);
    });
    barra.replaceChildren(
      el('button', { type: 'button', class: 'be-casa', title: 'Projetos (tela inicial)', onclick: function () { location.href = '/'; } }, '⌂'),
      el('span', { class: 'be-nome', title: DADOS.projeto.nome + (DADOS.projeto.cliente ? ' · ' + DADOS.projeto.cliente : ''), texto: DADOS.projeto.nome }),
      trilho,
      el('span', { class: 'be-busca', title: 'Buscar comando, tela ou peça (Ctrl+K)', onclick: abrirPaleta }, '⌕ Buscar…', el('kbd', { texto: 'Ctrl K' })),
      el('button', { type: 'button', class: 'be-bib', title: 'O que vale para todas as obras', onclick: function (ev) { ev.stopPropagation(); abrirLista(ev.currentTarget, 'Biblioteca', DADOS.biblioteca); } }, 'Biblioteca ▾'));
  }
  function abrirLista(alvo, titulo, itens) {
    fecharLista();
    var r = alvo.getBoundingClientRect();
    var lista = el('div', { class: 'be-lista' }, el('div', { class: 'be-tit', texto: titulo }),
      (itens || []).map(function (x) { return el('button', { type: 'button', class: 'be-it', onclick: function () { executarItem(x); } }, x.texto, x.dica ? el('small', { texto: x.dica }) : null); }));
    document.body.append(lista);
    var esq = Math.min(r.left, window.innerWidth - lista.offsetWidth - 8);
    lista.style.left = Math.max(8, esq) + 'px';
    lista.style.top = (r.bottom + 4) + 'px';
    ABERTO = lista;
  }
  function fecharLista() { if (ABERTO) { ABERTO.remove(); ABERTO = null; } }

  // ------------------------------------------------------------ a busca única (Ctrl+K)
  var FUNDO = null, ACHADOS = [], SEL = 0;
  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function indice() {
    var lista = [];
    var vistos = {};
    (DADOS ? DADOS.etapas : []).forEach(function (e) {
      lista.push({ tipo: 'etapa', texto: e.nome, cam: e.dica || '', link: e.url });
      (e.itens || []).forEach(function (x) {
        if (x.menu) vistos['menu:' + x.menu.join('›')] = true;          // o mesmo comando não aparece de novo como item de menu
        lista.push(Object.assign({ tipo: 'atalho', cam: e.nome }, x));
      });
    });
    (DADOS ? DADOS.biblioteca : []).forEach(function (x) { lista.push(Object.assign({ tipo: 'biblioteca', cam: 'Biblioteca' }, x)); });
    var mapa = (window.barraUnica && window.barraUnica.mapa) || [];
    function percorrer(itens, caminho) {
      (itens || []).forEach(function (it) {
        if (!it || typeof it !== 'object' || !it.texto) return;
        var c = caminho.concat([it.texto]);
        if (it.sub) { percorrer(it.sub, c); return; }
        if (vistos['menu:' + c.join('›')]) return;
        if (it.link) { lista.push({ tipo: 'comando', texto: it.texto, cam: caminho.join(' › '), link: it.link.replace('{projeto}', encodeURIComponent(PROJETO)), nova: it.nova }); return; }
        lista.push({ tipo: 'comando', texto: it.texto, cam: caminho.join(' › '), menu: c, dica: it.dica });
      });
    }
    mapa.forEach(function (m) { percorrer(m.itens, [m.nome]); });
    // os botões da tela aberta (Gerar a proposta, Atualizar pelo modelo 3D…)
    var titulo = document.title.split('—')[0].trim();
    document.querySelectorAll('header.topo button, .barra button, .acoes-obra button, .doc-barra button, .abas button, main .botao-m').forEach(function (b) {
      var t = (b.textContent || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length < 3 || t.length > 60 || b.disabled || b.offsetParent === null || b.closest('#barra-etapas')) return;
      if (vistos['botao:' + t]) return;
      vistos['botao:' + t] = true;
      lista.push({ tipo: 'nesta tela', texto: t, cam: titulo, botao: b });
    });
    return lista;
  }
  function buscar(q) {
    var termos = semAcento(q).split(/\s+/).filter(Boolean);
    var todos = indice();
    if (!termos.length) ACHADOS = todos.filter(function (x) { return x.tipo === 'etapa'; });
    else {
      ACHADOS = todos.filter(function (x) { var t = semAcento(x.texto + ' ' + (x.cam || '') + ' ' + (x.dica || '')); return termos.every(function (tt) { return t.indexOf(tt) >= 0; }); });
      ACHADOS.sort(function (a, b) { return (semAcento(a.texto).indexOf(termos[0]) === 0 ? 0 : 1) - (semAcento(b.texto).indexOf(termos[0]) === 0 ? 0 : 1); });
      ACHADOS = ACHADOS.slice(0, 16);
      if (q.trim().length >= 2) ACHADOS.push({ tipo: 'peça', texto: 'Procurar a peça “' + q.trim() + '” no modelo 3D', cam: 'nome, posição, conjunto ou perfil', peca: q.trim() });
    }
    SEL = 0;
    pintar();
  }
  function pintar() {
    var r = FUNDO.querySelector('.be-res');
    if (!ACHADOS.length) { r.replaceChildren(el('div', { class: 'be-vazio', texto: 'Nada com esse nome.' })); return; }
    r.replaceChildren.apply(r, ACHADOS.map(function (x, i) {
      return el('div', { class: 'be-r' + (i === SEL ? ' sel' : ''), onclick: function () { escolher(i); } },
        el('span', { class: 'be-tipo', texto: x.tipo }), el('span', {}, x.texto), el('span', { class: 'be-cam', texto: x.cam || '' }));
    }));
    var s = r.querySelector('.sel'); if (s && s.scrollIntoView) s.scrollIntoView({ block: 'nearest' });
  }
  function escolher(i) { var x = ACHADOS[i]; if (!x) return; fecharPaleta(); executarItem(x); }
  function abrirPaleta() {
    fecharLista();
    if (!FUNDO) {
      FUNDO = el('div', { class: 'be-fundo', onclick: function (ev) { if (ev.target === FUNDO) fecharPaleta(); } },
        el('div', { class: 'be-paleta' }, el('input', { placeholder: 'O que você quer fazer? (comando, tela ou peça)', autocomplete: 'off', spellcheck: 'false' }),
          el('div', { class: 'be-res' }), el('div', { class: 'be-rod', texto: '↑ ↓ escolhe · Enter abre · Esc fecha — comandos de todos os menus, as etapas, os botões desta tela e as peças' })));
      document.body.append(FUNDO);
      FUNDO.querySelector('input').addEventListener('input', function (ev) { buscar(ev.target.value); });
    }
    FUNDO.classList.add('on');
    var i = FUNDO.querySelector('input'); i.value = ''; buscar('');
    setTimeout(function () { i.focus(); }, 10);
  }
  function fecharPaleta() { if (FUNDO) FUNDO.classList.remove('on'); }
  function aberta() { return FUNDO && FUNDO.classList.contains('on'); }
  function tecla(ev) {
    if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && !ev.altKey && (ev.key === 'k' || ev.key === 'K')) { ev.preventDefault(); ev.stopPropagation(); abrirPaleta(); return; }
    if (!aberta()) { if (ev.key === 'Escape') fecharLista(); return; }
    if (ev.key === 'Escape') { fecharPaleta(); ev.preventDefault(); }
    else if (ev.key === 'ArrowDown') { SEL = Math.min(ACHADOS.length - 1, SEL + 1); pintar(); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp') { SEL = Math.max(0, SEL - 1); pintar(); ev.preventDefault(); }
    else if (ev.key === 'Enter') { escolher(SEL); ev.preventDefault(); }
  }

  // ------------------------------------------------------------ ligar
  function carregarMapa() {
    if (window.barraUnica && window.barraUnica.mapa) return;
    if (document.querySelector('script[src="/barra_unica.js"]')) return;
    var s = document.createElement('script'); s.src = '/barra_unica.js'; document.head.append(s);
  }
  function ouvirQuadros() {
    // Ctrl+K com o foco dentro do 2D ou do 3D (o teclado de um quadro não chega aqui)
    ['f2d', 'f3d'].forEach(function (id) {
      var f = document.getElementById(id);
      if (!f) return;
      var ligar = function () { try { f.contentWindow.document.addEventListener('keydown', function (ev) { if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) tecla(ev); }, true); } catch (e) { /* recarregando */ } };
      f.addEventListener('load', ligar);
      ligar();
    });
  }
  function pedidoNaUrl() {
    // ?menu=Arquivo › Importar › …: um comando pedido de outra tela; ?peca=…: uma peça procurada de outra tela
    var q = new URLSearchParams(location.search);
    var menu = q.get('menu'), peca = q.get('peca');
    if (!menu && !peca) return;
    q.delete('menu'); q.delete('peca');
    history.replaceState(null, '', location.pathname + '?' + q.toString() + location.hash);
    var t0 = Date.now();
    (function esperar() {
      var pronto = peca ? document.getElementById('busca-campo') : (window.barraUnica && window.barraUnica.executar);
      if (pronto) { if (menu) executarMenu(menu.split(' › ')); else procurarPeca(peca); return; }
      if (Date.now() - t0 < 60000) setTimeout(esperar, 300);
    })();
  }
  function iniciar() {
    var st = document.createElement('style'); st.textContent = CSS; document.head.append(st);
    var barra = el('nav', { class: 'barra-etapas', id: 'barra-etapas', 'aria-label': 'Etapas da obra' });
    document.body.insertBefore(barra, document.body.firstChild);
    document.addEventListener('keydown', tecla, true);
    document.addEventListener('click', function (ev) { if (ABERTO && !ev.target.closest('.be-lista')) fecharLista(); });
    window.addEventListener('hashchange', desenhar);
    window.addEventListener('blur', fecharLista);
    carregarMapa();
    if (NA_AREA()) { ouvirQuadros(); pedidoNaUrl(); }
    fetch('/api/projetos/' + encodeURIComponent(PROJETO) + '/etapas').then(function (r) { return r.json(); }).then(function (j) {
      if (!j || j.erro || !j.etapas) { barra.remove(); return; }
      DADOS = j; desenhar();
      document.body.classList.add('com-etapas');
    }).catch(function () { barra.remove(); });
    // a área de trabalho troca de vista sem recarregar: a etapa ativa acompanha
    document.addEventListener('click', function (ev) { if (ev.target.closest && ev.target.closest('.vistas, [data-vista]')) setTimeout(desenhar, 50); });
  }
  window.etapasProjeto = { abrirBusca: abrirPaleta, atualizar: function () { fetch('/api/projetos/' + encodeURIComponent(PROJETO) + '/etapas').then(function (r) { return r.json(); }).then(function (j) { if (j && j.etapas) { DADOS = j; desenhar(); } }); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
