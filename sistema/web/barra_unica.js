/* A barra única da área de trabalho (/dividida): um menu geral, o mesmo nas três vistas (2D, 2D + 3D,
 * 3D) — os menus do Desenho 2D e do modelo 3D juntos pelo nome (Arquivo, Desenho, IFC, Lançamento,
 * Vistas do modelo, Detalhamentos, Editar, Ver); o menu que existe nos dois lados abre com as duas
 * seções. As barras das telas de dentro ficam escondidas (html.barra-unica, web/area.js).
 *
 * O item é o da própria tela: ao abrir o menu, a lista é copiada da tela (com o estado dela: o
 * histórico do Desfazer, o que está desligado…) e o clique aciona o item original lá dentro. Tela
 * ainda não carregada (o 2D quando se abriu no 3D): a lista vem do HTML dela, e o clique troca para a
 * vista daquele lado, espera a tela ficar pronta e aciona o item. Item de um lado escondido também
 * troca para a vista dele — o diálogo que ele abre precisa aparecer.
 *
 * Os controles rápidos do 3D (Salvo, busca de peças, Calcular, modos de exibição, Perspectiva) vêm da
 * barra do 3D para esta: são os próprios elementos, movidos, e continuam ligados ao 3D.
 */
(function () {
  'use strict';
  var LADOS = [
    { id: 'f2d', lado: '2d', titulo: 'Desenho 2D', pagina: '/cad', pronto: function (w) { return !!(w && w.cad); } },
    { id: 'f3d', lado: '3d', titulo: 'Modelo 3D', pagina: '/editor', pronto: function (w) { return !!(w && w.editor); } },
  ];
  var RAPIDOS = ['btn-salvar', 'busca-pecas', 'btn-calcular', 'modos-exibicao', 'btn-projecao'];
  var estaticos = {};          // lado → Document do HTML da tela (antes de ela carregar)
  var aberto = null;           // o menu aberto na barra
  var chaves = new WeakMap();  // item copiado → como achar o original

  function $(s) { return document.querySelector(s); }
  function quadro(L) { return document.getElementById(L.id); }
  function docDe(L) {
    try { var d = quadro(L).contentDocument; return d && d.querySelector('header.topo .menus') ? d : null; } catch (e) { return null; }
  }

  function carregarEstatico(L) {
    if (estaticos[L.lado]) return Promise.resolve(estaticos[L.lado]);
    return fetch(L.pagina, { cache: 'no-store' }).then(function (r) { return r.text(); }).then(function (html) {
      estaticos[L.lado] = new DOMParser().parseFromString(html, 'text/html');
      return estaticos[L.lado];
    });
  }

  /** os menus de um lado: [{nome, lista}] — da tela carregada ou do HTML dela */
  function menusDe(L) {
    var d = docDe(L) || estaticos[L.lado];
    if (!d) return [];
    var out = [];
    d.querySelectorAll('header.topo .menus > .menu').forEach(function (m) {
      var b = m.querySelector('.menu-botao'), lista = m.querySelector('.menu-lista');
      if (b && lista) out.push({ nome: b.textContent.trim(), lista: lista });
    });
    return out;
  }

  /** a ordem da barra: a do 3D, com os menus só do 2D logo depois do vizinho que eles têm no 2D */
  function ordem() {
    var dois = menusDe(LADOS[0]).map(function (m) { return m.nome; });
    var tres = menusDe(LADOS[1]).map(function (m) { return m.nome; });
    var r = tres.slice();
    var anterior = null;
    dois.forEach(function (n) {
      if (r.indexOf(n) < 0) {
        var i = anterior === null ? Math.min(1, r.length) : r.indexOf(anterior) + 1;
        r.splice(i, 0, n);
      }
      anterior = n;
    });
    return r;
  }

  function montarBarra() {
    var caixa = $('#menus-unicos');
    if (!caixa) return;
    var nomes = ordem();
    var atuais = [].map.call(caixa.children, function (m) { return m.dataset.nome; });
    if (nomes.join('|') === atuais.join('|')) return;
    caixa.replaceChildren();
    nomes.forEach(function (n) {
      var m = document.createElement('div');
      m.className = 'menu';
      m.dataset.nome = n;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'menu-botao';
      b.textContent = n;
      var lista = document.createElement('div');
      lista.className = 'menu-lista';
      m.append(b, lista);
      b.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (aberto === m) { fechar(); return; }
        abrir(m);
      });
      b.addEventListener('mouseenter', function () { if (aberto && aberto !== m) abrir(m); });
      caixa.appendChild(m);
    });
    compactar();
  }

  /** como achar o item original: a ação, a vista, o id ou o texto */
  function chaveDe(el, menu) {
    return { menu: menu, acao: el.getAttribute('data-acao'), vista: el.getAttribute('data-vista'),
             id: el.id || null, texto: (el.textContent || '').trim() };
  }

  function abrir(m) {
    fechar();
    var nome = m.dataset.nome;
    var lista = m.querySelector('.menu-lista');
    lista.replaceChildren();
    var fontes = LADOS.map(function (L) {
      var achado = menusDe(L).filter(function (x) { return x.nome === nome; })[0];
      return achado ? { L: L, lista: achado.lista } : null;
    }).filter(Boolean);
    fontes.forEach(function (f) {
      if (fontes.length > 1) {
        var t = document.createElement('div');
        t.className = 'secao-lado';
        t.textContent = f.L.titulo;
        lista.appendChild(t);
      }
      [].forEach.call(f.lista.children, function (orig) {
        var c = document.importNode(orig, true);
        var origs = [orig].concat([].slice.call(orig.querySelectorAll('*')));
        var copias = [c].concat([].slice.call(c.querySelectorAll('*')));
        copias.forEach(function (e, i) {
          var o = origs[i];
          if (!o) return;
          if (e.matches && e.matches('button, a, [data-acao], [data-vista]')) {
            chaves.set(e, { L: f.L, chave: chaveDe(o, nome) });
            e.addEventListener('click', function (ev) {
              ev.preventDefault(); ev.stopPropagation();
              var k = chaves.get(e);
              fechar();
              executar(k.L, k.chave);
            });
          }
          e.removeAttribute('id');
          if (e.tagName === 'INPUT') e.remove();          // os campos de arquivo escondidos ficam na tela
        });
        lista.appendChild(c);
      });
    });
    m.classList.add('aberto');
    aberto = m;
  }

  function fechar() {
    if (aberto) aberto.classList.remove('aberto');
    aberto = null;
  }

  function visivel(L) {
    var v = window.vistaAtual ? window.vistaAtual() : 'ambos';
    return v === 'ambos' || v === L.lado;
  }

  function acharOriginal(d, k) {
    var menus = [].slice.call(d.querySelectorAll('header.topo .menus > .menu')).filter(function (m) {
      var b = m.querySelector('.menu-botao');
      return b && b.textContent.trim() === k.menu;
    });
    var raiz = menus[0] || d;
    var q = function (sel) { try { return raiz.querySelector(sel); } catch (e) { return null; } };
    if (k.acao) { var a = q('[data-acao="' + k.acao + '"]'); if (a) return a; }
    if (k.vista) { var v = q('[data-vista="' + k.vista + '"]'); if (v) return v; }
    if (k.id) { var i = d.getElementById(k.id); if (i) return i; }
    return [].slice.call(raiz.querySelectorAll('button, a')).filter(function (e) { return e.textContent.trim() === k.texto; })[0] || null;
  }

  /** aciona o item na tela dele: o lado escondido aparece antes (e carrega, se ainda não carregou) */
  function executar(L, k) {
    if (!visivel(L) && window.mostrarVista) window.mostrarVista(L.lado);
    var inicio = Date.now();
    (function tentar() {
      var w = null;
      try { w = quadro(L).contentWindow; } catch (e) { w = null; }
      var d = docDe(L);
      if (d && L.pronto(w)) {
        var o = acharOriginal(d, k);
        if (o) { o.click(); return; }
        console.warn('barra única: item não achado na tela', L.lado, k);
        return;
      }
      if (Date.now() - inicio < 60000) setTimeout(tentar, 200);
    })();
  }

  // ------------------------------------------------------------ controles rápidos do 3D
  var marcadores = {};        // id → o comentário que marca o lugar do elemento na barra do 3D
  function trazerRapidos() {
    var d = docDe(LADOS[1]);
    var caixa = $('#rapidos-3d');
    if (!d || !caixa) return;
    // o que veio de uma carga anterior do 3D (a tela recarregou: aqueles elementos morreram com ela)
    [].slice.call(caixa.children).forEach(function (e) { if (!d.contains(marcadores[e.id + '@doc'] || null)) e.remove(); });
    RAPIDOS.forEach(function (id) {
      var e = d.getElementById(id);
      if (!e || caixa.querySelector('#' + id)) return;
      var marca = d.createComment('barra única: ' + id);
      e.parentNode.insertBefore(marca, e);
      marcadores[id + '@doc'] = marca;
      caixa.appendChild(document.adoptNode(e));
    });
    compactar();
  }

  // ------------------------------------------------------------ a barra que não cabe
  var NIVEIS = 4;
  function naoCabe(topo) {
    var r = topo.getBoundingClientRect();
    var limite = r.right - (parseFloat(getComputedStyle(topo).paddingRight) || 0) + 1;
    for (var i = 0; i < topo.children.length; i++) {
      var c = topo.children[i];
      if (c.offsetParent === null) continue;
      if (c.getBoundingClientRect().right > limite) return true;
    }
    var busca = document.getElementById('busca-campo');
    if (busca && busca.offsetParent !== null && !document.documentElement.classList.contains('topo-c2') &&
        document.activeElement !== busca && busca.getBoundingClientRect().width < 140) return true;
    return false;
  }
  function compactar() {
    var topo = $('header.area-topo');
    if (!topo) return;
    var raiz = document.documentElement;
    for (var i = 1; i <= NIVEIS; i++) raiz.classList.remove('topo-c' + i);
    for (var n = 1; n <= NIVEIS && naoCabe(topo); n++) raiz.classList.add('topo-c' + n);
  }

  // ------------------------------------------------------------ ligar
  function aoCarregar(L) {
    quadro(L).addEventListener('load', function () {
      montarBarra();
      if (L.lado === '3d') {
        // o 3D põe os botões dele na barra depois de montar: espera o editor existir
        var t0 = Date.now();
        (function esperar() {
          var w = null;
          try { w = quadro(L).contentWindow; } catch (e) { w = null; }
          if (L.pronto(w)) { trazerRapidos(); return; }
          if (Date.now() - t0 < 60000) setTimeout(esperar, 250);
        })();
      }
    });
  }

  function iniciar() {
    LADOS.forEach(function (L) { aoCarregar(L); carregarEstatico(L).then(montarBarra).catch(function () { /* fica o da tela */ }); });
    document.addEventListener('click', function (ev) {
      if (aberto && !ev.target.closest('#menus-unicos')) fechar();
      // a lista de resultados da busca (movida do 3D) fecha no clique fora dela
      var r = document.getElementById('busca-resultados');
      if (r && !r.hidden && !ev.target.closest('#busca-pecas')) r.hidden = true;
    });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fechar(); });
    window.addEventListener('blur', fechar);           // o clique dentro de um dos quadros
    window.addEventListener('resize', function () { requestAnimationFrame(compactar); });
    setTimeout(compactar, 800);
  }

  window.barraUnica = {
    vista: function () { fechar(); requestAnimationFrame(compactar); },
    executar: executar,
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
