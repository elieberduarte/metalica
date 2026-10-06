/* O cabeçalho do projeto: o mesmo em todas as telas de um projeto (área de trabalho, comercial, materiais, análise,
 * memorial, esforços, treliças), numa linha só — entra no cabeçalho que a tela já tem, em vez de somar uma faixa.
 *
 *   [⌂ Projeto ▾]  Engenharia · Comercial · Produção · Obra  │  (o que é da tela: menus, vista 2D/3D…)  [☾] [⌕ Buscar Ctrl K]
 *
 * 03/10/2026: a primeira versão (seis etapas numa faixa própria) deixou a área de trabalho com três linhas e o
 * "Modelo 3D" duas vezes (etapa e vista); o usuário achou bagunçado. Ficaram quatro telas, uma por setor:
 * Engenharia é a área de trabalho (entrada, modelo 3D, cálculo e detalhamento — o 2D/3D é só a vista dela),
 * Comercial (orçamento, proposta, contrato), Produção (lista de materiais) e Obra (etapas e pagamentos).
 * O menu do projeto (⌂ ▾) leva à lista de projetos e à Biblioteca; o ☾/☀ troca o tema. A busca única (Ctrl+K) acha comandos de
 * todos os menus, as telas e seus atalhos, os botões da tela aberta, a Biblioteca e as peças do modelo 3D.
 * Dados: GET /api/projetos/<slug>/etapas (saida/etapas_projeto.py). Um comando de menu pedido de outra tela abre a
 * área de trabalho com ?menu=Arquivo›Importar›… e é executado lá (barra_unica.js). */
(function () {
  'use strict';
  if (window.top !== window) return;                         // dentro dos quadros 2D/3D (ou do orçamento no Comercial)
  var PROJETO = new URLSearchParams(location.search).get('projeto') || '';
  if (!PROJETO) return;
  var DADOS = null, ABERTO = null, ULTIMA = null;
  var NA_AREA = function () { return !!document.getElementById('menus-unicos'); };

  var CSS = [
    // as peças do cabeçalho (dentro do header da tela ou, sem ele, numa faixa própria)
    '.be-proj{display:inline-flex;align-items:center;gap:7px;height:28px;max-width:260px;padding:0 9px 0 7px;margin-right:4px;flex-shrink:1;min-width:0;',
    'background:none!important;border:1px solid transparent!important;border-radius:6px;color:inherit!important;font:600 13px "Segoe UI",Arial,sans-serif;cursor:pointer}',
    '.be-proj:hover{background:rgba(255,255,255,.08)!important}',
    '.be-proj svg{flex:none;opacity:.85}',
    '.be-proj .be-nome{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}',
    '.be-proj .be-v{opacity:.55;font-size:10px;flex:none}',
    '.be-abas{display:flex;align-items:stretch;align-self:stretch;flex-shrink:0;gap:2px}',
    '.be-aba{display:inline-flex;align-items:center;gap:7px;padding:0 11px!important;margin:0;background:none!important;border:0!important;border-radius:0!important;',
    'border-bottom:2px solid transparent!important;color:inherit!important;opacity:.7;font:500 13px "Segoe UI",Arial,sans-serif;cursor:pointer;white-space:nowrap}',
    '.be-aba:hover{opacity:1;background:rgba(255,255,255,.06)!important}',
    '.be-aba.ativa{opacity:1;font-weight:600;border-bottom-color:#5b9bff!important}',
    '.be-ponto{width:7px;height:7px;border-radius:50%;flex:none;border:1.5px solid currentColor;opacity:.55;box-sizing:border-box}',
    '.be-aba.feita .be-ponto{background:#3fbf7f;border-color:#3fbf7f;opacity:1}',
    '.be-aba.andamento .be-ponto{border-color:#e3b341;opacity:1}',
    '.be-sep{width:1px;align-self:center;height:20px;background:rgba(255,255,255,.18);flex:none;margin:0 6px}',
    '.be-busca{display:inline-flex;align-items:center;gap:8px;height:28px;width:150px;padding:0 8px!important;flex-shrink:0;white-space:nowrap;',
    'background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.16)!important;border-radius:6px;color:inherit!important;opacity:.85;font:12.5px "Segoe UI",Arial,sans-serif;cursor:text}',
    '.be-busca:hover{opacity:1;border-color:rgba(255,255,255,.32)!important}',
    '.be-tema{display:inline-grid;place-items:center;width:30px;height:28px;padding:0!important;flex-shrink:0;background:none!important;',
    'border:1px solid rgba(255,255,255,.2)!important;border-radius:6px;color:inherit!important;cursor:pointer}',
    '.be-tema:hover{background:rgba(255,255,255,.1)!important}',
    '.barra-etapas .be-tema{margin-left:auto}.barra-etapas .be-tema+.be-busca{margin-left:6px}',
    '.be-busca kbd{margin-left:auto;font:10.5px Consolas,monospace;border:1px solid rgba(255,255,255,.2);border-radius:3px;padding:1px 4px;opacity:.8}',
    // sem cabeçalho na tela: a faixa própria
    '.barra-etapas{display:flex;align-items:center;gap:6px;height:40px;padding:0 10px;flex-shrink:0;background:#0b1a33;color:#e2e8f0;position:relative;z-index:60}',
    // o cabeçalho de cada tela, com as peças dentro
    'body.com-etapas header.topo:not(.area-topo){height:44px;gap:10px;padding:0 10px}',
    'body.com-etapas header.topo:not(.area-topo) .marca svg,body.com-etapas header.topo .marca.be-igual{display:none}',
    'body.com-etapas header.topo:not(.area-topo) h1{font-size:13px;font-weight:600;opacity:.9}',
    'body.com-etapas header.topo:not(.area-topo) .projeto-atual{font-size:12px;opacity:.7;padding-left:10px}',
    'body.com-etapas header.topo:not(.area-topo) .acoes{margin-left:auto}',
    'body.com-etapas header.topo:not(.area-topo) .acoes button{padding:4px 10px;font-size:12.5px}',
    // na área de trabalho: a ordem da linha única (os menus logo depois das telas; a vista, o Salvo e a busca à direita)
    'body.com-etapas .area-topo{gap:4px}',
    'body.com-etapas .area-topo .be-proj{order:0}body.com-etapas .area-topo .be-abas{order:1}body.com-etapas .area-topo .be-sep{order:2}',
    'body.com-etapas .area-topo #menus-unicos{order:3}body.com-etapas .area-topo .controles{order:4}',
    'body.com-etapas .area-topo .vistas{order:5;margin-left:auto}body.com-etapas .area-topo #rapidos-3d{order:6;margin-left:6px}',
    'body.com-etapas .area-topo .be-tema{order:7;margin-left:6px}body.com-etapas .area-topo .be-busca{order:8;margin-left:6px}',
    'body.com-etapas .area-topo .vistas button{padding:3px 11px;font-size:12.5px}',
    // o que o cabeçalho substitui: a casa e o nome, o voltar e o tema da área (ficam no menu do projeto), os painéis
    // (Ver › Painéis, F4), a caixa de peça do 3D (a busca única acha as peças) e os botões de ir para outra tela
    'body.com-etapas .area-topo .marca,body.com-etapas #btn-voltar-area,body.com-etapas #btn-tema-area,body.com-etapas .area-topo .acoes,',
    'body.com-etapas #rapidos-3d .busca-pecas,body.com-etapas #rapidos-3d [data-parado="busca-pecas"],',
    'body.com-etapas #btn-tema,body.com-etapas #sub-projeto,body.com-etapas #btn-inicio,body.com-etapas #nome-projeto,',
    'body.com-etapas header.topo #btn-3d:not([title*="destaque"]),body.com-etapas #btn-cad,body.com-etapas #btn-materiais,body.com-etapas #btn-dividida,',
    "body.com-etapas header.topo button[onclick*=\"location.href='/'\"]{display:none!important}",
    // a linha que não cabe (barra_unica.js põe topo-c1…c4 no <html>): primeiro o nome do projeto, depois a busca vira ícone
    'html.topo-c1 .be-proj{max-width:170px}',
    'html.topo-c1 .be-tema{width:28px}',
    'html.topo-c2 .be-busca{width:32px;padding:0!important;justify-content:center}html.topo-c2 .be-busca .be-txt,html.topo-c2 .be-busca kbd{display:none}',
    'html.topo-c3 .be-proj .be-nome{display:none}html.topo-c3 .be-aba{padding:0 8px!important}',
    'html.topo-c4 .be-aba:not(.ativa) .be-txt{display:none}',
    // as listas e a busca
    '.be-lista{position:fixed;min-width:270px;max-height:80vh;overflow:auto;background:#131f33;color:#e2e8f0;border:1px solid #26385a;border-radius:8px;box-shadow:0 14px 40px rgba(0,0,0,.45);padding:5px;z-index:1000;font:13px "Segoe UI",Arial,sans-serif}',
    '.be-lista .be-it{display:block;width:100%;text-align:left;background:none;border:0;color:inherit;font:inherit;padding:7px 10px;border-radius:5px;cursor:pointer}',
    '.be-lista .be-it:hover{background:#1c2c48}',
    '.be-lista .be-it small{display:block;color:#7f93b3;font-size:11.5px;margin-top:2px}',
    '.be-lista .be-tit{padding:8px 10px 4px;color:#7f93b3;font-size:11px;text-transform:uppercase;letter-spacing:.07em}',
    '.be-lista .be-tit:not(:first-child){border-top:1px solid #22324f;margin-top:4px}',
    '.be-fundo{position:fixed;inset:0;background:rgba(5,10,20,.5);z-index:2000;display:none}',
    '.be-fundo.on{display:block}',
    '.be-paleta{position:fixed;top:70px;left:50%;transform:translateX(-50%);width:660px;max-width:94vw;background:#131f33;color:#e2e8f0;border:1px solid #26385a;border-radius:10px;',
    'box-shadow:0 30px 80px rgba(0,0,0,.6);overflow:hidden;font:13px "Segoe UI",Arial,sans-serif}',
    '.be-paleta input{width:100%;box-sizing:border-box;font:15px "Segoe UI",Arial;padding:14px 16px;background:#182741;border:0;border-bottom:1px solid #26385a;color:#e2e8f0;outline:none}',
    '.be-paleta .be-res{max-height:430px;overflow:auto;padding:6px}',
    '.be-paleta .be-r{display:grid;grid-template-columns:92px 1fr auto;gap:10px;align-items:baseline;padding:8px 10px;border-radius:6px;cursor:pointer}',
    '.be-paleta .be-r.sel,.be-paleta .be-r:hover{background:#1c3260}',
    '.be-paleta .be-tipo{font-size:10.5px;color:#7f93b3;text-transform:uppercase;letter-spacing:.06em}',
    '.be-paleta .be-cam{color:#7f93b3;font-size:11.5px;max-width:270px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.be-paleta .be-amostra{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:7px;vertical-align:0}',
    '.be-paleta .be-vazio{padding:16px;color:#7f93b3}',
    '.be-paleta .be-rod{padding:7px 12px;border-top:1px solid #26385a;color:#7f93b3;font-size:11.5px}',
    '@media print{.barra-etapas,.be-proj,.be-abas,.be-sep,.be-busca{display:none!important}}',
  ].join('\n');

  var CASA = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 9.8V20h5v-5.5h3V20h5V9.8"/></svg>';

  function el(tag, attrs) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) {
      var v = attrs[k];
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v; else if (k === 'texto') e.textContent = v; else if (k === 'html') e.innerHTML = v;
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

  // ------------------------------------------------------------ que tela é esta
  function etapaAtiva() {
    var p = location.pathname, h = (location.hash || '').slice(1);
    if (/^\/(dividida|2d-3d)/.test(p)) return 'engenharia';
    if (/^\/(materiais|lista-de-materiais)/.test(p)) return 'producao';
    if (/^\/(comercial|proposta|contrato)/.test(p)) return h === 'obra' ? 'obra' : 'comercial';
    if (/^\/(analise|resultado|memorial|esforcos|trelicas|dimensionar)/.test(p)) return 'engenharia';
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
    else if (x.grupo) destacarNo3D(x.grupo.ids);
    else if (x.peca) procurarPeca(x.peca);
    else if (x.acao === 'tema') trocarTema();
  }
  function trocarTema() {
    var b = document.getElementById('btn-tema-area') || document.getElementById('btn-tema');
    if (b) b.click();
    setTimeout(iconeDoTema, 30);
  }
  // o botão de tema do cabeçalho (05/10/2026: tinha ido para dentro do menu do projeto e o usuário sentiu falta):
  // o sol no tema escuro (vai para o claro), a lua no claro
  function temaAtual() {
    return document.documentElement.getAttribute('data-tema') ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
  }
  function iconeDoTema() {
    var b = document.querySelector('.be-tema');
    if (!b) return;
    var escuro = temaAtual() === 'escuro';
    b.innerHTML = escuro
      ? '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg>'
      : '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';
    b.title = escuro ? 'Tema claro' : 'Tema escuro';
    b.setAttribute('aria-label', b.title);
  }
  function irPara(url) {
    // a mesma tela com outra aba (#): só troca o hash e avisa a tela
    var a = document.createElement('a'); a.href = url;
    if (a.pathname === location.pathname && a.search === location.search && a.hash !== location.hash) { location.hash = a.hash; return; }
    if (/^\/dividida/.test(a.pathname) && NA_AREA()) {
      var vista = new URLSearchParams(a.search).get('vista');
      if (vista && window.mostrarVista) { window.mostrarVista(vista); return; }
      if (a.search === location.search || !vista) return;
    }
    location.href = url;
  }

  // as peças do modelo 3D (a mesma pesquisa da antiga caixa "Pesquisar peça" do 3D: nome, posição, conjunto, perfil)
  function editor3d() {
    var f = document.getElementById('f3d');
    try { var e = f && f.contentWindow && f.contentWindow.editor; return e && e.pesquisarPecas ? e : null; } catch (x) { return null; }
  }
  // o 3D no modo "ver" (web/visor3d): procura e mostra a peça, sem o editor
  function visorLeve() {
    var f = document.getElementById('f3d');
    try { var w = f && f.contentWindow; return w && w.visorLeve ? w.visorLeve : null; } catch (x) { return null; }
  }
  function verO3D() {
    if (window.mostrarVista && window.vistaAtual && window.vistaAtual() === '2d') window.mostrarVista('ambos');
  }
  function destacarNo3D(ids) {
    var e = editor3d();
    if (!e || !ids || !ids.length) return;
    verO3D();
    e._destacarEncontradas(ids, true);
  }
  function procurarPeca(q) {
    if (!NA_AREA()) { location.href = '/dividida?projeto=' + encodeURIComponent(PROJETO) + '&vista=3d&peca=' + encodeURIComponent(q); return; }
    var e = editor3d();
    if (!e) {
      var v = visorLeve();
      if (v) { verO3D(); v.procurar(q); }
      return;
    }
    var r = e.pesquisarPecas(q);
    if (r.total) destacarNo3D(r.ids);
    else if (e.dica) { verO3D(); e.dica('Nenhuma peça com "' + q + '". Tente parte do nome, a posição (P12), o conjunto (M2) ou o perfil.'); }
  }

  // ------------------------------------------------------------ o cabeçalho
  function pecas() {
    var ativa = etapaAtiva();
    ULTIMA = ativa;
    var proj = el('button', { type: 'button', class: 'be-proj', 'data-be': '1',
      title: DADOS.projeto.nome + (DADOS.projeto.cliente ? ' · ' + DADOS.projeto.cliente : '') + ' — projetos, biblioteca e tema',
      onclick: function (ev) { ev.stopPropagation(); abrirLista(ev.currentTarget, menuProjeto()); } },
      el('span', { html: CASA, style: 'display:inline-flex' }), el('span', { class: 'be-nome', texto: DADOS.projeto.nome }), el('span', { class: 'be-v', texto: '▾' }));
    var abas = el('nav', { class: 'be-abas', 'data-be': '1', 'aria-label': 'Telas do projeto' },
      DADOS.etapas.map(function (e) {
        var s = e.situacao === 'feita' ? ' — feita' : e.situacao === 'andamento' ? ' — em andamento' : '';
        return el('button', { type: 'button', class: 'be-aba ' + (e.situacao || '') + (e.chave === ativa ? ' ativa' : ''), title: e.nome + ': ' + (e.dica || '') + s,
          'aria-current': e.chave === ativa ? 'page' : null, onclick: function () { irPara(e.url); } },
          el('span', { class: 'be-ponto' }), el('span', { class: 'be-txt', texto: e.nome }));
      }));
    var sep = el('span', { class: 'be-sep', 'data-be': '1' });
    var busca = el('button', { type: 'button', class: 'be-busca', 'data-be': '1', title: 'Buscar comando, tela ou peça do modelo (Ctrl+K)', onclick: abrirPaleta },
      '⌕', el('span', { class: 'be-txt', texto: 'Buscar…' }), el('kbd', { texto: 'Ctrl K' }));
    var tema = el('button', { type: 'button', class: 'be-tema', 'data-be': '1', onclick: trocarTema });
    return { proj: proj, abas: abas, sep: sep, tema: tema, busca: busca };
  }
  function menuProjeto() {
    return [{ titulo: DADOS.projeto.nome }, { texto: 'Todos os projetos', link: '/' },
      { titulo: 'Biblioteca — vale para todas as obras' }].concat(DADOS.biblioteca || []);
  }
  function desenhar() {
    if (!DADOS) return;
    document.querySelectorAll('[data-be]').forEach(function (x) { x.remove(); });
    var p = pecas();
    var area = document.querySelector('header.area-topo');
    var topo = area || document.querySelector('header.topo');
    if (topo) {
      // dentro do cabeçalho da tela: as telas à esquerda, a busca à direita (na área de trabalho, a ordem é do CSS)
      topo.insertBefore(p.sep, topo.firstChild);
      topo.insertBefore(p.abas, p.sep);
      topo.insertBefore(p.proj, p.abas);
      if (area) area.append(p.tema, p.busca);
      else { var acoes = topo.querySelector('.acoes'); if (acoes) acoes.append(p.tema, p.busca); else topo.append(p.tema, p.busca); }
      // o título da tela igual ao nome da aba (Comercial): sai
      var marca = topo.querySelector('.marca'), h1 = marca && marca.querySelector('h1');
      if (h1 && !area) {
        var nomeAtiva = (DADOS.etapas.filter(function (e) { return e.chave === ULTIMA; })[0] || {}).nome || '';
        marca.classList.toggle('be-igual', !!nomeAtiva && (h1.firstChild && h1.firstChild.textContent || '').trim() === nomeAtiva);
      }
    } else {
      var barra = el('nav', { class: 'barra-etapas', id: 'barra-etapas', 'data-be': '1', 'aria-label': 'Telas do projeto' }, p.proj, p.abas, p.tema, p.busca);
      [p.proj, p.abas, p.tema, p.busca].forEach(function (x) { x.removeAttribute('data-be'); });
      document.body.insertBefore(barra, document.body.firstChild);
    }
    iconeDoTema();
    if (window.barraUnica && window.barraUnica.vista) window.barraUnica.vista();   // recalcula o que cabe na linha
  }
  function conferirAtiva() { if (DADOS && etapaAtiva() !== ULTIMA) desenhar(); }
  function abrirLista(alvo, itens) {
    fecharLista();
    var r = alvo.getBoundingClientRect();
    var lista = el('div', { class: 'be-lista' },
      (itens || []).map(function (x) {
        if (x.titulo) return el('div', { class: 'be-tit', texto: x.titulo });
        return el('button', { type: 'button', class: 'be-it', onclick: function () { executarItem(x); } }, x.texto, x.dica ? el('small', { texto: x.dica }) : null);
      }));
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
      lista.push({ tipo: 'tela', texto: e.nome, cam: e.dica || '', link: e.url });
      (e.itens || []).forEach(function (x) {
        if (x.menu) vistos['menu:' + x.menu.join('›')] = true;          // o mesmo comando não aparece de novo como item de menu
        lista.push(Object.assign({ tipo: 'atalho', cam: e.nome }, x));
      });
    });
    lista.push({ tipo: 'projeto', texto: 'Todos os projetos', cam: 'tela inicial', link: '/' });
    lista.push({ tipo: 'projeto', texto: 'Tema claro / escuro', cam: 'botão ☾/☀ do cabeçalho', acao: 'tema' });
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
      if (!t || t.length < 3 || t.length > 60 || b.disabled || b.offsetParent === null || b.closest('[data-be], #barra-etapas, #menus-unicos')) return;
      if (vistos['botao:' + t]) return;
      vistos['botao:' + t] = true;
      lista.push({ tipo: 'nesta tela', texto: t, cam: titulo, botao: b });
    });
    return lista;
  }
  function buscar(q) {
    var termos = semAcento(q).split(/\s+/).filter(Boolean);
    var todos = indice();
    if (!termos.length) ACHADOS = todos.filter(function (x) { return x.tipo === 'tela'; });
    else {
      ACHADOS = todos.filter(function (x) { var t = semAcento(x.texto + ' ' + (x.cam || '') + ' ' + (x.dica || '')); return termos.every(function (tt) { return t.indexOf(tt) >= 0; }); });
      ACHADOS.sort(function (a, b) { return (semAcento(a.texto).indexOf(termos[0]) === 0 ? 0 : 1) - (semAcento(b.texto).indexOf(termos[0]) === 0 ? 0 : 1); });
      ACHADOS = ACHADOS.slice(0, 12);
      var e = q.trim().length >= 2 ? editor3d() : null;
      if (e) {
        // as peças do modelo aberto, direto na lista (clique: destaca e enquadra no 3D)
        var r = null;
        try { r = e.pesquisarPecas(q.trim()); } catch (x) { r = null; }
        if (r && r.total) {
          r.grupos.slice(0, 8).forEach(function (g) { ACHADOS.push({ tipo: 'peça', texto: g.chave, cam: (g.detalhe || '') + ' · ' + g.ids.length + ' no modelo', cor: g.cor, grupo: g }); });
          if (r.grupos.length > 1) ACHADOS.push({ tipo: 'peça', texto: 'Destacar todas as ' + r.total + ' peças com “' + q.trim() + '”', cam: r.grupos.length + ' grupos', grupo: { ids: r.ids } });
        }
      } else if (q.trim().length >= 2) ACHADOS.push({ tipo: 'peça', texto: 'Procurar a peça “' + q.trim() + '” no modelo 3D', cam: 'nome, posição, conjunto ou perfil', peca: q.trim() });
    }
    SEL = 0;
    pintar();
  }
  function pintar() {
    var r = FUNDO.querySelector('.be-res');
    if (!ACHADOS.length) { r.replaceChildren(el('div', { class: 'be-vazio', texto: 'Nada com esse nome.' })); return; }
    r.replaceChildren.apply(r, ACHADOS.map(function (x, i) {
      return el('div', { class: 'be-r' + (i === SEL ? ' sel' : ''), onclick: function () { escolher(i); } },
        el('span', { class: 'be-tipo', texto: x.tipo }),
        el('span', {}, x.cor ? el('i', { class: 'be-amostra', style: 'background:' + x.cor }) : null, x.texto),
        el('span', { class: 'be-cam', texto: x.cam || '' }));
    }));
    var s = r.querySelector('.sel'); if (s && s.scrollIntoView) s.scrollIntoView({ block: 'nearest' });
  }
  function escolher(i) { var x = ACHADOS[i]; if (!x) return; fecharPaleta(); executarItem(x); }
  var timer = null;
  function abrirPaleta() {
    fecharLista();
    if (!FUNDO) {
      FUNDO = el('div', { class: 'be-fundo', onclick: function (ev) { if (ev.target === FUNDO) fecharPaleta(); } },
        el('div', { class: 'be-paleta' }, el('input', { placeholder: 'O que você quer fazer? (comando, tela ou peça do modelo)', autocomplete: 'off', spellcheck: 'false' }),
          el('div', { class: 'be-res' }), el('div', { class: 'be-rod', texto: '↑ ↓ escolhe · Enter abre · Esc fecha — comandos de todos os menus, as telas, os botões desta tela e as peças do modelo' })));
      document.body.append(FUNDO);
      FUNDO.querySelector('input').addEventListener('input', function (ev) { clearTimeout(timer); var v = ev.target.value; timer = setTimeout(function () { buscar(v); }, 90); });
    }
    FUNDO.classList.add('on');
    var i = FUNDO.querySelector('input'); i.value = ''; buscar('');
    setTimeout(function () { i.focus(); }, 10);
  }
  function fecharPaleta() { if (FUNDO) FUNDO.classList.remove('on'); }
  function aberta() { return FUNDO && FUNDO.classList.contains('on'); }
  function atalho(ev) {
    // Ctrl+K em qualquer lugar; Ctrl+F (a antiga busca de peça do 3D) também abre a busca única na área de trabalho
    var k = (ev.key || '').toLowerCase();
    return (ev.ctrlKey || ev.metaKey) && !ev.shiftKey && !ev.altKey && (k === 'k' || (k === 'f' && NA_AREA()));
  }
  function tecla(ev) {
    if (atalho(ev)) { ev.preventDefault(); ev.stopPropagation(); abrirPaleta(); return; }
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
    // Ctrl+K / Ctrl+F com o foco dentro do 2D ou do 3D (o teclado de um quadro não chega aqui)
    ['f2d', 'f3d'].forEach(function (id) {
      var f = document.getElementById(id);
      if (!f) return;
      var ligar = function () {
        try { f.contentWindow.document.addEventListener('keydown', function (ev) { if (atalho(ev)) tecla(ev); }, true); } catch (e) { /* recarregando */ }
      };
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
      var e = editor3d();
      var v = visorLeve();
      var pronto = peca ? ((e && e.documento && e.documento.entidades && e.documento.entidades.size) || (v && v.pronto && v.pronto()))
                        : (window.barraUnica && window.barraUnica.executar);
      if (pronto) { if (menu) executarMenu(menu.split(' › ')); else procurarPeca(peca); return; }
      if (Date.now() - t0 < 60000) setTimeout(esperar, 300);
    })();
  }
  function iniciar() {
    var st = document.createElement('style'); st.textContent = CSS; document.head.append(st);
    document.addEventListener('keydown', tecla, true);
    document.addEventListener('click', function (ev) {
      if (ABERTO && !ev.target.closest('.be-lista')) fecharLista();
      // as abas de dentro das telas trocam o # sem avisar (history.replaceState): a aba de cima acompanha
      setTimeout(conferirAtiva, 60);
    });
    window.addEventListener('hashchange', conferirAtiva);
    window.addEventListener('blur', fecharLista);
    carregarMapa();
    if (NA_AREA()) { ouvirQuadros(); pedidoNaUrl(); }
    fetch('/api/projetos/' + encodeURIComponent(PROJETO) + '/etapas').then(function (r) { return r.json(); }).then(function (j) {
      if (!j || j.erro || !j.etapas) return;
      DADOS = j;
      document.body.classList.add('com-etapas');
      desenhar();
    }).catch(function () { /* a tela fica com o cabeçalho dela */ });
  }
  window.etapasProjeto = { abrirBusca: abrirPaleta, atualizar: function () { fetch('/api/projetos/' + encodeURIComponent(PROJETO) + '/etapas').then(function (r) { return r.json(); }).then(function (j) { if (j && j.etapas) { DADOS = j; desenhar(); } }); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
