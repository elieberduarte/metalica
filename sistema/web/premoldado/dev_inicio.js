/* Modo desenvolvimento: a tela de projetos ganha duas áreas — Metálica e Pré-moldado — trocadas na marca
 * do canto de cima. Cada área tem a sua lista de obras, os seus botões de "Novo" e os seus menus; os
 * projetos do pré-moldado abrem na tela do pré-moldado (premoldado/web.py). Só é carregado com o programa
 * em --dev. */
(function () {
  'use strict';
  var CHAVE = 'inicio.area';
  var AREAS = {
    metalica: { nome: 'Metálica', sub: 'Projetos de estruturas metálicas', titulo: 'Metálica — projetos',
                icone: '<path d="M4 27V13.5L16 6l12 7.5V27" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/><path d="M4 13.5h24M16 6v21" fill="none" stroke="currentColor" stroke-width="1.1" opacity=".55"/>' },
    premoldado: { nome: 'Pré-moldado', sub: 'Projetos de estruturas pré-moldadas', titulo: 'Pré-moldado — projetos',
                  icone: '<path d="M8 28V9M24 28V9M5 9h22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/><path d="M5 28h6M21 28h6" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".6"/>' },
  };
  // áreas de outros módulos em desenvolvimento (30/10: a Arquitetura, web/arquitetura/dev_inicio_arq.js): cada uma traz
  // nome, ícone, os botões de "Novo" (novos), o texto da lista vazia (vazio) e onde o projeto abre (url)
  var EXTRAS = window.AREAS_INICIO_EXTRA || [];
  EXTRAS.forEach(function (a) { AREAS[a.chave] = a; });
  // os botões de "Novo" e os menus que só valem na Metálica
  var SO_METALICA = ['#btn-novo-ifc', '#btn-novo-cad', '#btn-novo',
                     '.topo .acoes button[onclick*="/catalogo"]', '.topo .acoes button[onclick*="/ligacoes"]'];

  function lerArea() {
    var q = new URLSearchParams(location.search).get('area');
    if (q && AREAS[q]) return q;
    try { var a = localStorage.getItem(CHAVE); if (a && AREAS[a]) return a; } catch (e) { /* sem armazenamento */ }
    return 'metalica';
  }
  var area = lerArea();
  var ehPM = function (p) { return p && (p.tipo === 'premoldado' || p.area === 'premoldado'); };
  var areaDe = function (p) {
    if (ehPM(p)) return 'premoldado';
    return p && p.area && AREAS[p.area] ? p.area : 'metalica';
  };

  function estilo() {
    if (document.getElementById('estilo-areas')) return;
    var s = document.createElement('style');
    s.id = 'estilo-areas';
    s.textContent =
      '.topo .marca.trocavel { cursor: pointer; border-radius: 6px; padding: 2px 8px 2px 4px; margin-left: -4px; position: relative; }' +
      '.topo .marca.trocavel:hover { background: rgba(127,127,127,.14); }' +
      '.topo .marca .seta-area { font-size: 11px; opacity: .7; margin-left: 2px; }' +
      '.menu-areas { position: absolute; top: calc(100% + 6px); left: 0; z-index: 50; min-width: 270px; background: var(--painel); ' +
      '  border: 1px solid var(--borda); border-radius: var(--raio); box-shadow: var(--sombra); padding: 4px; }' +
      '.menu-areas button { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; font: inherit; ' +
      '  background: none; border: 0; color: var(--texto); padding: 7px 9px; border-radius: 5px; cursor: pointer; }' +
      '.menu-areas button:hover { background: var(--painel2); }' +
      '.menu-areas button.atual { background: var(--painel2); }' +
      '.menu-areas b { display: block; font-size: 13.5px; } .menu-areas span { display: block; font-size: 11.5px; color: var(--texto2); }' +
      '.menu-areas .dev { font-size: 10px; color: #d97706; margin-left: 4px; }' +
      '.cartao-icone.premoldado { color: #9ca3af; }';
    document.head.appendChild(s);
  }

  function svg(icone, tam) {
    return '<svg width="' + tam + '" height="' + tam + '" viewBox="0 0 32 32" aria-hidden="true">' + icone + '</svg>';
  }

  function marca() {
    var m = document.querySelector('.topo .marca');
    if (!m) return;
    var a = AREAS[area];
    m.classList.add('trocavel');
    m.title = 'Trocar de área (' + Object.keys(AREAS).map(function (k) { return AREAS[k].nome; }).join(' / ') + ')';
    m.innerHTML = svg(a.icone, 26) + '<h1>' + a.nome + '<span>' + a.sub + '</span></h1><span class="seta-area">▾</span>';
    if (!m.dataset.ligada) {
      m.dataset.ligada = '1';
      m.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var aberto = m.querySelector('.menu-areas');
        if (aberto) { aberto.remove(); return; }
        var menu = document.createElement('div');
        menu.className = 'menu-areas';
        Object.keys(AREAS).forEach(function (k) {
          var b = document.createElement('button');
          b.type = 'button';
          if (k === area) b.className = 'atual';
          b.innerHTML = svg(AREAS[k].icone, 22) + '<div><b>' + AREAS[k].nome +
            (k === 'premoldado' || AREAS[k].dev ? '<em class="dev">em desenvolvimento</em>' : '') + '</b><span>' + AREAS[k].sub + '</span></div>';
          b.addEventListener('click', function (e) { e.stopPropagation(); menu.remove(); trocar(k); });
          menu.appendChild(b);
        });
        m.appendChild(menu);
      });
      document.addEventListener('click', function () {
        var aberto = document.querySelector('.menu-areas');
        if (aberto) aberto.remove();
      });
    }
  }

  // ---- os "Novo" da área do pré-moldado: o projeto nasce com area = "premoldado" (premoldado/web.py marca)
  /* global perguntar, postar, carregando, recado, lerComoBase64, CAMPOS_PROJETO, carregar */
  function criarPM(v, tipo) {
    return postar('/api/projetos', Object.assign({}, v, { tipo: tipo, area: 'premoldado' }));
  }

  async function novoGalpaoPM() {
    var v = await perguntar({ titulo: 'Novo galpão pré-moldado',
      texto: 'Cria o projeto e abre o dimensionamento do galpão de concreto pré-moldado: pilares engastados em cálice, ' +
             'NBR 6118 e NBR 9062. Os dados podem ser mudados depois.',
      campos: CAMPOS_PROJETO, ok: 'Criar e abrir' });
    if (!v) return;
    try {
      var p = await criarPM(v, 'premoldado');
      location.href = '/premoldado?projeto=' + encodeURIComponent(p.slug);
    } catch (e) { recado('Não foi possível criar o projeto', e.message, 'erro'); }
  }

  async function novoArquitetonicoPM() {
    var v = await perguntar({ titulo: 'Novo pré-moldado a partir do arquitetônico',
      texto: 'Abre o Desenho 2D na Planta de lançamento e pede a planta do cliente (DXF ou PDF vetorial). Por cima dela você ' +
             'lança a malha de eixos (Malha de eixos…) e grava. Depois, na tela do galpão pré-moldado, "Usar os eixos da planta" ' +
             'traz o vão (entre os eixos com letra) e os vãos entre pórticos (entre os eixos numerados) para o dimensionamento.',
      campos: CAMPOS_PROJETO, ok: 'Criar e abrir a planta' });
    if (!v) return;
    try {
      carregando(true, 'Criando o projeto…');
      var p = await criarPM(v, 'premoldado');
      location.href = '/cad?projeto=' + encodeURIComponent(p.slug) + '&arquitetonico=1';
    } catch (e) { carregando(false); recado('Não foi possível criar o projeto', e.message, 'erro'); }
  }

  async function novoDesenhoPM() {
    var v = await perguntar({ titulo: 'Novo pré-moldado desenhando em 2D',
      texto: 'Abre o Desenho 2D vazio, com as ferramentas de desenho, cotas e folhas. Gerar as peças de concreto no 3D a partir ' +
             'do desenho ainda não existe no pré-moldado (o "Gerar modelo 3D do desenho" é o da Metálica, com perfis de aço).',
      campos: CAMPOS_PROJETO, ok: 'Criar e desenhar' });
    if (!v) return;
    try {
      carregando(true, 'Criando o projeto…');
      var p = await criarPM(v, 'desenho');
      location.href = '/cad?projeto=' + encodeURIComponent(p.slug);
    } catch (e) { carregando(false); recado('Não foi possível criar o projeto', e.message, 'erro'); }
  }

  function novoIFCPM() {
    var entrada = document.getElementById('arquivo-ifc');
    entrada.value = '';
    entrada.onchange = async function () {
      var arquivo = entrada.files && entrada.files[0];
      if (!arquivo) return;
      var sugestao = arquivo.name.replace(/\.ifc$/i, '').replace(/[._-]+/g, ' ').trim();
      var v = await perguntar({ titulo: 'Novo pré-moldado a partir de IFC',
        texto: arquivo.name + ' · ' + (arquivo.size / 1048576).toFixed(1).replace('.', ',') + ' MB. O modelo de concreto ' +
               '(Tekla, Revit, TQS, Eberick…) é copiado para a pasta do projeto e aberto no editor 3D.',
        campos: CAMPOS_PROJETO.map(function (c) { return c.id === 'nome' ? Object.assign({}, c, { valor: sugestao }) : c; }),
        ok: 'Criar e importar' });
      if (!v) return;
      var criado = null;
      try {
        carregando(true, 'Criando o projeto…');
        criado = await criarPM(v, 'ifc');
        carregando(true, 'Lendo ' + arquivo.name + '… arquivo grande leva um minuto ou dois.');
        var conteudo_b64 = await lerComoBase64(arquivo);
        carregando(true, 'Importando ' + arquivo.name + '… arquivo grande leva um minuto ou dois.');
        await postar('/api/projetos/' + encodeURIComponent(criado.slug) + '/importar-ifc', { nome: arquivo.name, conteudo_b64: conteudo_b64 });
        location.href = window.urlDoProjeto(criado, 'editor');
      } catch (e) {
        carregando(false);
        recado('Não foi possível importar o IFC', e.message, 'erro');
        if (criado) carregar();
      }
    };
    entrada.click();
  }

  var NOVOS_PM = [
    ['btn-pm-ifc', 'Novo a partir de IFC…', 'Cria um projeto pré-moldado a partir de um modelo IFC de concreto de outro programa', novoIFCPM],
    ['btn-pm-arquitetonico', 'Novo a partir do arquitetônico…', 'Cria o projeto a partir da planta do cliente (DXF ou PDF): os eixos lançados por cima dela dão os vãos do galpão pré-moldado', novoArquitetonicoPM],
    ['btn-pm-desenho', 'Novo desenhando em 2D…', 'Cria um projeto pré-moldado vazio e abre o Desenho 2D', novoDesenhoPM],
    ['btn-novo-premoldado', 'Novo galpão pré-moldado', 'Galpão de concreto pré-moldado — pilares em cálice (NBR 6118 e NBR 9062). Em desenvolvimento.', novoGalpaoPM, 'principal'],
  ];
  function botoesNovos() {
    var novo = document.getElementById('btn-novo');
    if (!novo) return [];
    var depois = novo;
    return NOVOS_PM.map(function (n) {
      var b = document.getElementById(n[0]);
      if (!b) {
        b = document.createElement('button');
        b.type = 'button';
        b.id = n[0];
        if (n[4]) b.className = n[4];
        b.textContent = n[1];
        b.title = n[2];
        b.addEventListener('click', function () { n[3](); });
        depois.parentNode.insertBefore(b, depois.nextSibling);
      }
      depois = b;
      return b;
    });
  }

  // os menus do pré-moldado no lugar do Catálogo e das Ligações da Metálica
  var MENUS_PM = [
    ['menu-pm-catalogo', 'Catálogo de peças', '/premoldado/catalogo', 'Concretos, aços, bitolas e ancoragem, cobrimentos e as seções de pilares, vigas e terças'],
    ['menu-pm-ligacoes', 'Ligações pré-moldadas', '/premoldado/ligacoes', 'Cálice, consolo e aparelho de apoio de elastômero calculados avulsos (NBR 9062)'],
  ];
  function menus() {
    var acoes = document.querySelector('.topo .acoes');
    if (!acoes) return [];
    var ajuda = acoes.querySelector('button[onclick*="/ajuda"]');
    return MENUS_PM.map(function (m) {
      var b = document.getElementById(m[0]);
      if (!b) {
        b = document.createElement('button');
        b.type = 'button';
        b.id = m[0];
        b.textContent = m[1];
        b.title = m[3];
        b.addEventListener('click', function () { location.href = m[2]; });
        acoes.insertBefore(b, ajuda || null);
      }
      return b;
    });
  }

  /** os "Novo" das áreas extras, depois dos do pré-moldado; cada um só aparece na área dele */
  function botoesExtras() {
    var novo = document.getElementById('btn-novo');
    if (!novo) return;
    var depois = document.getElementById(NOVOS_PM[NOVOS_PM.length - 1][0]) || novo;
    EXTRAS.forEach(function (a) {
      (a.novos || []).forEach(function (n) {
        var b = document.getElementById(n[0]);
        if (!b) {
          b = document.createElement('button');
          b.type = 'button';
          b.id = n[0];
          if (n[4]) b.className = n[4];
          b.textContent = n[1];
          b.title = n[2];
          b.addEventListener('click', function () { n[3](); });
          depois.parentNode.insertBefore(b, depois.nextSibling);
        }
        depois = b;
        b.hidden = area !== a.chave;
      });
    });
  }

  function aplicar() {
    estilo();
    marca();
    var pm = area === 'premoldado';
    document.title = (/^\[DEV\] /.test(document.title) ? '[DEV] ' : '') + AREAS[area].titulo;
    SO_METALICA.forEach(function (sel) {
      var e = document.querySelector(sel);
      if (e) e.hidden = area !== 'metalica';
    });
    botoesNovos().forEach(function (b) { b.hidden = !pm; });
    botoesExtras();
    menus().forEach(function (m) { m.hidden = !pm; });
    if (typeof window.desenhar === 'function' && typeof projetos !== 'undefined') window.desenhar();
  }

  function trocar(k) {
    area = k;
    try { localStorage.setItem(CHAVE, k); } catch (e) { /* sem armazenamento */ }
    var u = new URL(location.href);
    if (k === 'metalica') u.searchParams.delete('area'); else u.searchParams.set('area', k);
    history.replaceState(null, '', u.pathname + u.search);
    aplicar();
  }

  // a lista: cada área só mostra as suas obras (o inicio.js desenha a partir de `projetos`)
  if (typeof window.desenhar === 'function') {
    var desenharOriginal = window.desenhar;
    window.desenhar = function () {
      /* global projetos:writable */
      var todos = projetos;
      projetos = todos.filter(function (p) { return areaDe(p) === area; });
      try { desenharOriginal(); } finally { projetos = todos; }
      if (area !== 'metalica') {
        // sem obra ainda: o cabeçalho com o "Novo" fica, e o vazio da Metálica não aparece
        var cab = document.querySelector('.gerenciador-cabeca');
        var vazio = document.getElementById('vazio');
        if (cab) cab.hidden = false;
        if (vazio) vazio.hidden = true;
        if (!todos.some(function (p) { return areaDe(p) === area; })) {
          var c = document.getElementById('contagem');
          if (c) c.textContent = area === 'premoldado' ? 'nenhuma obra pré-moldada ainda — comece pelo "Novo galpão pré-moldado"'
                                                       : (AREAS[area].vazio || 'nenhum projeto nesta área ainda');
        }
      }
    };
  }
  if (typeof window.urlDoProjeto === 'function') {
    var original = window.urlDoProjeto;
    window.urlDoProjeto = function (p, destino) {
      // o pré-moldado abre na planta (pedido do usuário, 30/09): a de lançamento, senão a locação dos pilares,
      // senão o primeiro desenho; sem desenho, o 3D; sem nada, a configuração do galpão (o botão próprio do cartão)
      if (p && p.tipo === 'premoldado' && !destino) return urlDaPlanta(p);
      var ar = AREAS[areaDe(p)];
      if (ar && ar.url && !destino) return ar.url(p);
      return original(p, destino);
    };
  }
  if (typeof ICONES === 'object' && ICONES) {
    ICONES.premoldado = svg(AREAS.premoldado.icone, 30);
    EXTRAS.forEach(function (a) { if (a.tipo) ICONES[a.tipo] = svg(a.icone, 30); });
  }

  function urlDaPlanta(p) {
    var s = encodeURIComponent(p.slug);
    var ds = (p.desenhos || []).map(function (d) { return d.nome; });
    var pref = ['planta-de-lançamento', 'locacao-pilares', 'locacao-dos-pilares'];
    var alvo = null;
    for (var i = 0; i < pref.length && !alvo; i++) if (ds.indexOf(pref[i]) >= 0) alvo = pref[i];
    if (!alvo && ds.length) alvo = ds[0];
    if (alvo) return '/dividida?projeto=' + s + '&vista=2d&desenho=' + encodeURIComponent(alvo);
    if (p.tem_modelo) return '/dividida?projeto=' + s + '&vista=3d';
    return '/premoldado?projeto=' + s;
  }

  /** o botão "Configuração" no cartão de cada obra pré-moldada: a tela do galpão (dados, cálculo, saídas) */
  function botoesDeConfiguracao() {
    var lista = (typeof projetos !== 'undefined' && projetos) || [];
    var cartoes = document.querySelectorAll('article.cartao');
    for (var i = 0; i < cartoes.length; i++) {
      var c = cartoes[i];
      if (c.querySelector('[data-acao="pm-configuracao"]')) continue;
      var nome = (c.getAttribute('aria-label') || '').replace(/^Abrir o projeto /, '');
      var p = null;
      for (var k = 0; k < lista.length; k++) if (lista[k].nome === nome && lista[k].tipo === 'premoldado') { p = lista[k]; break; }
      var menu = c.querySelector('.cartao-menu');
      if (!p || !menu) continue;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'discreto';
      b.dataset.acao = 'pm-configuracao';
      b.title = 'A configuração do galpão: geometria, cargas, vento, materiais, o cálculo, o memorial e as pranchas';
      b.textContent = 'Configuração';
      (function (slug) { b.addEventListener('click', function (ev) { ev.stopPropagation(); location.href = '/premoldado?projeto=' + encodeURIComponent(slug); }); })(p.slug);
      menu.insertBefore(b, menu.firstChild);
    }
  }
  new MutationObserver(function () { botoesDeConfiguracao(); }).observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', aplicar);
  else aplicar();
})();
