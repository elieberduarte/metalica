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

  if (embutida) {
    // os links internos que levam ao 2D ou ao 3D também passam pela área
    document.addEventListener('click', function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
      if (!a || a.target === '_blank' || a.hasAttribute('download') || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      var u = destino(a.getAttribute('href'));
      if (!u || u.origin !== location.origin || u.pathname === location.pathname && u.search === location.search) return;
      if (a.getAttribute('href').charAt(0) === '#') return;
      ev.preventDefault();
      window.metalicaNavegar(u.pathname + u.search);
    }, true);
    return;
  }

  // sozinha: o seletor de vista no começo da barra
  function montarSeletor() {
    var topo = document.querySelector('header.topo');
    var marca = topo && topo.querySelector('.marca');
    var p = new URLSearchParams(location.search);
    var projeto = p.get('projeto');
    if (!topo || !marca || !projeto || document.querySelector('.seletor-vista')) return;
    var aqui = location.pathname.indexOf('/cad') === 0 || location.pathname === '/desenho' ? '2d' : '3d';
    var nav = document.createElement('nav');
    nav.className = 'seletor-vista';
    nav.setAttribute('aria-label', 'Vista do projeto');
    [['2d', '2D', 'O desenho do projeto'], ['3d', '3D', 'O modelo 3D do projeto'],
     ['ambos', '2D + 3D', 'O desenho e o modelo lado a lado: escolher uma peça num mostra ela no outro']].forEach(function (v) {
      var a = document.createElement('a');
      a.textContent = v[1];
      a.title = v[2] + ' — troca de vista sem recarregar';
      a.dataset.vista = v[0];
      if (v[0] === aqui) { a.className = 'ativo'; a.setAttribute('aria-current', 'page'); a.href = '#'; }
      else {
        var q = new URLSearchParams({ projeto: projeto, vista: v[0] });
        var desenho = p.get('desenho') || (window.cad && window.cad.nomeDesenho) || '';
        if (desenho) q.set('desenho', desenho);
        a.href = '/dividida?' + q.toString();
        // o 2D sai gravando o desenho (e o 3D, o modelo): o mesmo caminho dos outros "sair"
        a.addEventListener('click', function (ev) {
          ev.preventDefault();
          var sair = (window.cad && window.cad._sairPara) ? window.cad._sairPara.bind(window.cad)
            : (window.editor && window.editor._irPara) ? window.editor._irPara.bind(window.editor) : null;
          var q2 = new URLSearchParams(q);
          var d2 = (window.cad && window.cad.nomeDesenho) || p.get('desenho') || '';
          if (d2) q2.set('desenho', d2);
          var url = '/dividida?' + q2.toString();
          if (sair) sair(url); else location.href = url;
        });
      }
      nav.appendChild(a);
    });
    marca.insertAdjacentElement('afterend', nav);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montarSeletor);
  else montarSeletor();
})();
