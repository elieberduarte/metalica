/* A área de trabalho do projeto: o Desenho 2D e o modelo 3D são duas vistas da mesma tela
 * (/dividida?projeto=…&vista=2d|3d|ambos), que mantém as duas abertas — trocar de vista não
 * recarrega nada (o 3D de milhares de peças levava segundos para montar a cada troca).
 *
 * Este script roda no 2D e no 3D:
 *  - sozinha (fora da área), a tela ganha o seletor [2D | 3D | 2D + 3D] no começo da barra, que
 *    leva para a área de trabalho na vista escolhida;
 *  - dentro da área, `metalicaNavegar(url)` troca a vista em vez de a tela virar a outra (o "Abrir
 *    no 3D" do 2D, o "Lançar estrutura", o "Abrir o modelo 3D" depois de montar pela planta…); o que
 *    não é 2D nem 3D (materiais, análise, memorial, a lista de projetos) sai da área, na janela toda.
 */
(function () {
  'use strict';
  var embutida = window.parent !== window;
  // dentro da área de trabalho (/dividida) a barra é a única de fora (web/barra_unica.js): a desta tela some
  try {
    if (embutida && ['/dividida', '/2d-3d'].indexOf(window.parent.location.pathname) >= 0) document.documentElement.classList.add('barra-unica');
  } catch (e) { /* outra origem */ }
  // as ferramentas ficam nas colunas ao lado, como nas telas sozinhas (07/10: o padrão de todas as telas). A faixa de
  // cima (web/faixa_ferramentas.js) é a opção de Ver › Tela: com ela, as colunas desta tela saem da vista — continuam
  // no documento, porque a faixa aciona os botões delas
  var naFaixa = false;
  try { naFaixa = localStorage.getItem('metalica.ferramentas') === 'faixa'; } catch (e) { /* sem armazenamento */ }
  if (naFaixa && document.documentElement.classList.contains('barra-unica')) {
    var sem_colunas = document.createElement('style');
    sem_colunas.textContent = ':root.barra-unica #barra-ferramentas, :root.barra-unica #barra-disciplina { display: none !important; }' +
      ':root.barra-unica { --larg-ferramentas: 0px; }';
    (document.head || document.documentElement).appendChild(sem_colunas);
  }
  var TELAS = { '/editor': '3d', '/editor3d': '3d', '/3d': '3d', '/cad': '2d', '/desenho': '2d', '/dividida': null, '/2d-3d': null };

  function destino(url) {
    try { return new URL(url, location.href); } catch (e) { return null; }
  }

  /** navega para `url`: dentro da área, 2D e 3D viram troca de vista; o resto sai da área */
  window.metalicaNavegar = function (url) {
    var u = destino(url);
    if (embutida && u && u.origin === location.origin) {
      if (Object.prototype.hasOwnProperty.call(TELAS, u.pathname)) {
        try { window.parent.postMessage({ metalica: 'navegar', url: u.pathname + u.search }, location.origin); return; }
        catch (e) { /* sem a área: navega como sempre */ }
      }
      try { window.top.location.href = u.href; return; } catch (e) { /* idem */ }
    }
    window.location.href = url;
  };

  // ---------------------------------------------------------- painéis da direita recolhíveis
  // (Propriedades, Camadas, Snap… no 2D; Propriedades, Camadas, Materiais… no 3D). A escolha fica
  // guardada por tela — e à parte dentro da área de trabalho, onde o espaço é metade
  function ligarPaineis() {
    var aside = document.getElementById('paineis');
    var area = aside && aside.parentElement;
    if (!aside || !area || document.querySelector('.aba-paineis')) return;
    var tela = location.pathname.indexOf('/cad') === 0 || location.pathname === '/desenho' ? '2d' : '3d';
    var chave = 'metalica.paineis.' + tela + (embutida ? '.area' : '');
    var oculto = null;
    try { oculto = localStorage.getItem(chave); } catch (e) { oculto = null; }
    oculto = oculto === null ? window.innerWidth < 900 : oculto === '1';
    var aba = document.createElement('button');
    aba.type = 'button';
    aba.className = 'aba-paineis';
    area.appendChild(aba);
    var itemMenu = null;
    function aplicar(guardar) {
      document.documentElement.classList.toggle('sem-paineis', oculto);
      aba.textContent = oculto ? '‹' : '›';
      aba.title = (oculto ? 'Mostrar' : 'Esconder') + ' os painéis da direita (F4)';
      aba.setAttribute('aria-label', aba.title);
      if (itemMenu) itemMenu.textContent = (oculto ? 'Mostrar' : 'Esconder') + ' os painéis laterais';
      if (guardar) { try { localStorage.setItem(chave, oculto ? '1' : '0'); } catch (e) { /* sem armazenamento */ } }
    }
    window.metalicaPaineis = function (mostrar) {
      oculto = mostrar === undefined ? !oculto : !mostrar;
      aplicar(true);
      return !oculto;
    };
    aba.addEventListener('click', function () { window.metalicaPaineis(); });
    // Ver → Esconder os painéis laterais
    var lista = document.querySelector('.menu[data-menu="ver"] .menu-lista');
    if (lista) {
      itemMenu = document.createElement('button');
      itemMenu.type = 'button';
      itemMenu.title = 'Propriedades, camadas e os outros painéis da direita (F4)';
      itemMenu.addEventListener('click', function () {
        window.metalicaPaineis();
        var m = itemMenu.closest('.menu'); if (m) m.classList.remove('aberto');
      });
      lista.insertBefore(itemMenu, lista.firstChild);
    }
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'F4' || ev.ctrlKey || ev.altKey || ev.metaKey) return;
      ev.preventDefault();
      window.metalicaPaineis();
    });
    // a área de trabalho manda mostrar ou esconder (o botão "Painéis" da barra de fora)
    window.addEventListener('message', function (ev) {
      if (ev.origin !== location.origin || !ev.data || ev.data.metalica !== 'paineis') return;
      window.metalicaPaineis(!!ev.data.mostrar);
    });
    aplicar(false);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ligarPaineis);
  else ligarPaineis();

  var aqui = location.pathname.indexOf('/cad') === 0 || location.pathname === '/desenho' ? '2d' : '3d';
  var paraFora = function (msg) { try { window.parent.postMessage(msg, location.origin); } catch (e) { /* sem a área */ } };

  if (embutida) {
    // os links internos que levam ao 2D ou ao 3D também passam pela área
    document.addEventListener('click', function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
      if (!a || a.target === '_blank' || a.hasAttribute('download') || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      if (a.closest('.seletor-vista')) return;
      var u = destino(a.getAttribute('href'));
      if (!u || u.origin !== location.origin || u.pathname === location.pathname && u.search === location.search) return;
      if (a.getAttribute('href').charAt(0) === '#') return;
      ev.preventDefault();
      window.metalicaNavegar(u.pathname + u.search);
    }, true);
  }

  // O seletor de vista no começo da barra — a mesma linha da tela: sozinha, ele leva à área de
  // trabalho; dentro dela, pede a troca de vista (e, no 2D + 3D, o 2D ganha ao lado os controles da
  // ligação entre os lados: seguir a seleção, planta ou elevação, trocar os lados)
  var estado = { vista: aqui, seguir: true, modo: 'planta' };
  function montarSeletor() {
    var topo = document.querySelector('header.topo');
    var marca = topo && topo.querySelector('.marca');
    var p = new URLSearchParams(location.search);
    var projeto = p.get('projeto');
    if (!topo || !marca || !projeto || document.querySelector('.seletor-vista')) return;
    var nav = document.createElement('nav');
    nav.className = 'seletor-vista';
    nav.setAttribute('aria-label', 'Vista do projeto');
    [['2d', '2D', 'O desenho do projeto'], ['3d', '3D', 'O modelo 3D do projeto'],
     ['ambos', '2D + 3D', 'O desenho e o modelo lado a lado: escolher uma peça num mostra ela no outro']].forEach(function (v) {
      var a = document.createElement('a');
      a.textContent = v[1];
      a.title = v[2] + ' — troca de vista sem recarregar';
      a.dataset.vistaArea = v[0];
      a.href = '#';
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        if (embutida) { paraFora({ metalica: 'vista', vista: v[0] }); return; }
        if (v[0] === aqui) return;
        var q = new URLSearchParams({ projeto: projeto, vista: v[0] });
        var d = (window.cad && window.cad.nomeDesenho) || p.get('desenho') || '';
        if (d) q.set('desenho', d);
        var url = '/dividida?' + q.toString();
        // o 2D sai gravando o desenho (e o 3D, o modelo): o mesmo caminho dos outros "sair"
        var sair = (window.cad && window.cad._sairPara) ? window.cad._sairPara.bind(window.cad)
          : (window.editor && window.editor._irPara) ? window.editor._irPara.bind(window.editor) : null;
        if (sair) sair(url); else location.href = url;
      });
      if (!embutida && v[0] !== aqui) {
        var q0 = new URLSearchParams({ projeto: projeto, vista: v[0] });
        if (p.get('desenho')) q0.set('desenho', p.get('desenho'));
        a.href = '/dividida?' + q0.toString();       // o endereço à mostra (e o clique do meio)
      }
      nav.appendChild(a);
    });
    marca.insertAdjacentElement('afterend', nav);
    if (embutida && aqui === '2d') {
      var lig = document.createElement('div');
      lig.className = 'ligacao-vistas';
      lig.innerHTML = '<button type="button" data-c="seguir" title="Seguir a seleção: escolher uma peça num lado mostra ela no outro">🔗</button>' +
        '<span class="seg"><button type="button" data-c="planta" title="Escolher no 3D mostra o lugar da peça na planta">planta</button>' +
        '<button type="button" data-c="elevacao" title="Escolher uma treliça no 3D mostra a elevação dela, como o projetista desenhou">elevação</button></span>' +
        '<button type="button" data-c="trocar" title="Trocar o 2D e o 3D de lado">⇄</button>';
      lig.addEventListener('click', function (ev) {
        var b = ev.target.closest('button');
        if (!b) return;
        var c = b.dataset.c;
        if (c === 'seguir') paraFora({ metalica: 'controle', seguir: !estado.seguir });
        else if (c === 'planta' || c === 'elevacao') paraFora({ metalica: 'controle', modo: c });
        else if (c === 'trocar') paraFora({ metalica: 'controle', trocar: true });
      });
      nav.insertAdjacentElement('afterend', lig);
    }
    mostrarEstado();
    if (embutida) paraFora({ metalica: 'pedir-estado' });
  }
  function mostrarEstado() {
    var ativa = embutida ? estado.vista : aqui;
    var links = document.querySelectorAll('.seletor-vista a');
    for (var i = 0; i < links.length; i++) {
      var on = links[i].dataset.vistaArea === ativa;
      links[i].classList.toggle('ativo', on);
      if (on) links[i].setAttribute('aria-current', 'page'); else links[i].removeAttribute('aria-current');
    }
    var lig = document.querySelector('.ligacao-vistas');
    if (lig) {
      lig.hidden = estado.vista !== 'ambos';
      lig.querySelector('[data-c="seguir"]').classList.toggle('ativo', !!estado.seguir);
      lig.querySelector('[data-c="planta"]').classList.toggle('ativo', estado.modo === 'planta');
      lig.querySelector('[data-c="elevacao"]').classList.toggle('ativo', estado.modo === 'elevacao');
    }
  }
  if (embutida) {
    window.addEventListener('message', function (ev) {
      if (ev.origin !== location.origin || !ev.data || ev.data.metalica !== 'estado') return;
      estado = { vista: ev.data.vista, seguir: ev.data.seguir !== false, modo: ev.data.modo || 'planta' };
      mostrarEstado();
    });
  }
  // A barra do topo que não cabe: em vez de deixar botões fora da tela, liga níveis de compactação
  // (topo-c1…c4 no <html>, CSS em editor3d/editor.css) até o conteúdo caber na largura
  var NIVEIS = 4;
  function compactarTopo() {
    var topo = document.querySelector('header.topo');
    if (!topo) return;
    var raiz = document.documentElement;
    for (var i = 1; i <= NIVEIS; i++) raiz.classList.remove('topo-c' + i);
    for (var n = 1; n <= NIVEIS && naoCabe(topo); n++) raiz.classList.add('topo-c' + n);
  }
  /** os itens da barra passam da borda direita dela? (pela caixa de cada item: a lista da busca e os
   *  menus abertos flutuam por cima e não contam) */
  function naoCabe(topo) {
    var r = topo.getBoundingClientRect();
    var limite = r.right - (parseFloat(getComputedStyle(topo).paddingRight) || 0) + 1;
    for (var i = 0; i < topo.children.length; i++) {
      var c = topo.children[i];
      if (c.offsetParent === null && getComputedStyle(c).position !== 'fixed') continue;     // escondido
      if (c.getBoundingClientRect().right > limite) return true;
    }
    // a busca espremida (menos de 140 px) não serve para ler: melhor a lupa do nível seguinte
    var busca = document.getElementById('busca-campo');
    var raiz = document.documentElement;
    if (busca && busca.offsetParent !== null && !raiz.classList.contains('topo-c2') && document.activeElement !== busca &&
        busca.getBoundingClientRect().width < 140) return true;
    return false;
  }
  var agendado = null;
  function pedirCompactar() {
    if (agendado) return;
    agendado = requestAnimationFrame(function () { agendado = null; compactarTopo(); });
  }
  function iniciar() {
    montarSeletor();
    compactarTopo();
    window.addEventListener('resize', pedirCompactar);
    // o texto do "Salvo", o nome da tela e os botões que aparecem depois mudam a largura da barra
    var topo = document.querySelector('header.topo');
    if (topo && window.MutationObserver) {
      new MutationObserver(pedirCompactar).observe(topo, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['hidden', 'class'] });
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(pedirCompactar);
    setTimeout(pedirCompactar, 800);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
