/* A faixa de ferramentas da área de trabalho (/dividida): uma linha só de ícones embaixo da barra única, a
 * mesma nas três vistas (2D, 2D + 3D, 3D) — no lugar das colunas de cada tela, que ficam escondidas dentro da
 * área (html.barra-unica, web/area.js). Aprovada no protótipo Projeto/Prototipo-faixa-e-menus-v3.html (UI1,
 * 30/09/2026): sem títulos de grupo e sem etiqueta 2D/3D; o ícone que não é do lado ativo fica apagado.
 *
 * A faixa é um controle das colunas originais: cada botão dela aciona (click) o botão da coluna de uma das
 * telas, que continua no documento, e acompanha o aria-pressed dele. Assim o que cada botão faz (a barra da
 * disciplina fixa o material do pilar, por exemplo) continua sendo da tela, e ferramenta nova aparece sozinha
 * (a que a tabela de grupos não conhece entra no ▾ de Modificar: nenhuma se perde).
 *
 * O lado ativo é o último em que o mouse entrou (ou a vista, com um lado só): a faixa age nele. A ferramenta que
 * existe só no outro lado fica apagada, e o clique passa o lado ativo para lá e começa a ferramenta.
 */
(function () {
  'use strict';
  var QUADRO = { '2d': 'f2d', '3d': 'f3d' };
  var NOME_LADO = { '2d': '2D', '3d': '3D' };
  // [chave, [ids no 2D], [ids no 3D]] — a mesma ferramenta nos dois lados vira um botão só
  function F(chave, d2, d3) { return { chave: chave, d2: d2 || [], d3: d3 || [] }; }
  var GRUPOS = [
    { nome: 'Selecionar', itens: [F('selecionar', ['selecionar'], ['selecionar'])] },
    { nome: 'Desenhar', recolhe: 4, itens: [F('linha', ['linha'], ['linha']), F('polilinha', ['polilinha']), F('retangulo', ['retangulo'], ['retangulo']),
      F('circulo', ['circulo'], ['circulo']), F('arco', ['arco'], ['arco']), F('poligono', null, ['poligono'])] },
    { nome: 'Modificar', recolhe: 3, itens: [F('mover', ['mover'], ['mover']), F('copiar', ['copiar'], ['copiar']), F('girar', ['girar'], ['girar']),
      F('espelhar', ['espelhar']), F('escalar', ['escalar'], ['escalar']), F('offset', ['offset'], ['offset']), F('empurrar', ['esticar'], ['pushpull']), F('apagar', ['apagar'])],
      mais: [F('aparar', ['aparar']), F('estender', ['estender']), F('concordar', ['concordar']),
        F('juntar', ['juntar']), F('explodir', ['explodir']), F('copiar_propriedades', ['copiar_propriedades'])] },
    { nome: 'Anotar', recolhe: 2, itens: [F('texto', ['texto']), F('cota', ['cota'], ['cotar']), F('chamada', ['chamada']), F('hachura', ['hachura']),
      F('corte', ['corte'])], mais: [F('mover_cota', ['mover_cota'])] },
    { nome: 'Medir', itens: [F('medir', ['medir'], ['medir']), F('secao', null, ['secao'])] },
  ];
  // a disciplina (a barra da direita do 2D, quando existe): o elemento de aço e o do 3D são o mesmo botão
  var DO_3D = { estr_chapa: 'chapa', estr_furo: 'furo', estr_parafuso: 'parafuso' };
  var ESTRUTURA_3D = ['barra', 'chapa', 'furo', 'parafuso', 'encaixar', 'virar'];

  var ativo = '3d';               // o lado em que a faixa age
  var escolhido = {};             // lado → a chave clicada por último (o pilar e a viga de aço usam a Barra do 3D)
  var ultima = {};                // grupo → a última ferramenta usada nele (o botão do grupo recolhido)
  var observados = {};            // lado → o documento cujas colunas já estão sendo observadas
  var contexto = '';
  var agendado = null;

  function $(s) { return document.querySelector(s); }
  function vista() { return window.vistaAtual ? window.vistaAtual() : 'ambos'; }
  function janela(lado) { try { return document.getElementById(QUADRO[lado]).contentWindow; } catch (e) { return null; } }
  function docDe(lado) {
    var w = janela(lado);
    try { return w && (lado === '2d' ? w.cad : w.editor) ? w.document : null; } catch (e) { return null; }
  }
  function visivel(lado) { var v = vista(); return v === 'ambos' || v === lado; }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt) e.textContent = txt; return e; }

  // ------------------------------------------------------------ os botões das colunas originais
  function sel2d(id, material) {
    return '#barra-ferramentas [data-ferramenta="' + id + '"], #barra-disciplina [data-ferramenta="' + id + '"]' +
      (material ? '[data-material="' + material + '"]' : '');
  }
  function sel3d(id) { return '#barra-ferramentas [data-id="' + id + '"]'; }
  function original(item, lado) {
    if (item.acao) return lado === '2d' && item.acao.isConnected ? item.acao : null;     // ação da planta: o próprio botão
    var d = docDe(lado);
    if (!d) return null;
    var sels = lado === '2d' ? (item.d2 || []).map(function (id) { return item.material ? sel2d(id, item.material).split(', ')[1] : sel2d(id); })
      : (item.d3 || []).map(sel3d);
    for (var i = 0; i < sels.length; i++) { var o = d.querySelector(sels[i]); if (o) return o; }
    return null;
  }
  function existe(item, lado) { return !!original(item, lado); }

  /** a estrutura (da barra da disciplina do 2D, ou só a do 3D) e a planta (as ações da barra da disciplina) */
  function gruposDaDisciplina() {
    var d = docDe('2d');
    var barra = d && d.getElementById('barra-disciplina');
    var est = { nome: 'Estrutura', itens: [], seletor: [] };
    var planta = { nome: 'Planta', recolhe: 1, itens: [] };
    var usados3d = {};
    if (barra && barra.querySelector('[data-ferramenta]')) {
      [].forEach.call(barra.querySelectorAll('.seletor-disciplina .disciplina'), function (b) { est.seletor.push(b); });
      [].forEach.call(barra.querySelectorAll('.ferramenta[data-ferramenta]'), function (b) {
        var id = b.dataset.ferramenta, mat = b.dataset.material || '';
        var d3 = DO_3D[id] ? [DO_3D[id]] : ((id === 'estr_pilar' || id === 'estr_viga') && mat === 'aco' ? ['barra'] : []);
        d3.forEach(function (x) { usados3d[x] = 1; });
        est.itens.push({ chave: id + (mat ? '|' + mat : ''), d2: [id], d3: d3, material: mat, rotulo: b.title });
      });
      [].forEach.call(barra.querySelectorAll('.ferramenta.acao'), function (b, i) {
        planta.itens.push({ chave: 'acao' + i, acao: b, rotulo: b.title, icone: b.innerHTML });
      });
    }
    ESTRUTURA_3D.forEach(function (id) { if (!usados3d[id]) est.itens.push(F(id, null, [id])); });
    return [est, planta];
  }

  /** as ferramentas das colunas que a tabela não conhece: vão para o ▾ de Modificar (nenhuma se perde) */
  function sobras(grupos) {
    var conhecidos = { '2d': {}, '3d': {} };
    grupos.forEach(function (g) {
      (g.itens || []).concat(g.mais || []).forEach(function (it) {
        (it.d2 || []).forEach(function (id) { conhecidos['2d'][id] = 1; });
        (it.d3 || []).forEach(function (id) { conhecidos['3d'][id] = 1; });
      });
    });
    var out = [];
    ['2d', '3d'].forEach(function (lado) {
      var d = docDe(lado);
      if (!d) return;
      [].forEach.call(d.querySelectorAll('#barra-ferramentas .ferramenta'), function (b) {
        var id = lado === '2d' ? b.dataset.ferramenta : b.dataset.id;
        if (!id || conhecidos[lado][id]) return;
        conhecidos[lado][id] = 1;
        out.push(lado === '2d' ? F('x2-' + id, [id]) : F('x3-' + id, null, [id]));
      });
    });
    return out;
  }

  // ------------------------------------------------------------ informações de uma ferramenta
  function classe(item, lado) {
    var w = janela(lado);
    var id = lado === '2d' ? item.d2[0] : item.d3[0];
    try {
      if (lado === '2d') { var f = w.cad.ferramentas.get(id); return f && f.constructor; }
      return w.editor.ferramentas.get(id);
    } catch (e) { return null; }
  }
  function info(item) {
    var o2 = existe(item, '2d') ? original(item, '2d') : null;
    var o3 = existe(item, '3d') ? original(item, '3d') : null;
    var c2 = o2 && !item.acao ? classe(item, '2d') : null;
    var c3 = o3 && !item.acao ? classe(item, '3d') : null;
    var nome = item.rotulo || (c2 && c2.nome) || (c3 && c3.nome) || (o2 && o2.title) || (o3 && (o3.getAttribute('aria-label') || '')) || item.chave;
    return { o2: o2, o3: o3, c2: c2, c3: c3, nome: String(nome).replace(/\s*\(([^)]{1,8})\)\s*$/, ''),
             icone: item.icone || (o2 || o3 || {}).innerHTML || '' };
  }

  // ------------------------------------------------------------ desenhar
  var balao = null;
  function mostrarBalao(b, item, inf, grupo) {
    if (!balao) { balao = el('div', 'faixa-balao'); document.body.appendChild(balao); }
    var a2 = inf.c2 && inf.c2.atalho && inf.c2.atalho !== ' ' ? String(inf.c2.atalho).toUpperCase() : '';
    var a3 = inf.c3 && inf.c3.atalho && !/espa/i.test(inf.c3.atalho) ? String(inf.c3.atalho).toUpperCase() : '';
    var lados = inf.o2 && inf.o3 ? '' : inf.o2 ? 'só no 2D' : 'só no 3D';
    var atalho = a2 && a3 ? (a2 === a3 ? 'atalho ' + a2 : 'atalho ' + a2 + ' no 2D, ' + a3 + ' no 3D') : (a2 || a3) ? 'atalho ' + (a2 || a3) : '';
    var dica = (ativo === '3d' ? (inf.c3 && inf.c3.dica) : (inf.c2 && inf.c2.dica)) || (inf.c2 && inf.c2.dica) || (inf.c3 && inf.c3.dica) || '';
    balao.replaceChildren();
    var t = el('b', '', inf.nome);
    balao.appendChild(t);
    if (grupo) balao.appendChild(el('span', 'g', ' · ' + grupo));
    [[lados, atalho].filter(Boolean).join(' · '), dica,
     (!ladoTem(item, ativo) && lados) ? 'o clique passa para o ' + (inf.o2 ? '2D' : '3D') + ' e começa lá' : ''].forEach(function (linha) {
      if (linha) balao.appendChild(el('div', 'l', linha));
    });
    var r = b.getBoundingClientRect();
    balao.style.left = Math.min(r.left, window.innerWidth - 340) + 'px';
    balao.style.top = (r.bottom + 6) + 'px';
    balao.hidden = false;
  }
  function esconderBalao() { if (balao) balao.hidden = true; }

  function ladoTem(item, lado) { return item.acao ? lado === '2d' : existe(item, lado); }

  function acionar(item, grupo) {
    esconderBalao();
    fecharLista();
    if (item.acao) {                                  // ação da planta (no 2D)
      if (!visivel('2d') && window.mostrarVista) window.mostrarVista('ambos');
      item.acao.click();
      return;
    }
    var lado = ladoTem(item, ativo) ? ativo : (ativo === '2d' ? '3d' : '2d');
    if (!ladoTem(item, lado)) return;
    if (!visivel(lado) && window.mostrarVista) window.mostrarVista('ambos');
    ativo = lado;
    escolhido[lado] = item.chave;
    if (grupo) ultima[grupo] = item.chave;
    var o = original(item, lado);
    if (o) o.click();
    pedirDesenho();
  }

  function botao(item, grupo) {
    var inf = info(item);
    var b = el('button', 'fx-bt');
    b.type = 'button';
    b.dataset.chave = item.chave;
    if (inf.o2) b.dataset.id2 = item.d2 ? item.d2[0] || '' : '';
    if (inf.o3) b.dataset.id3 = item.d3 ? item.d3[0] || '' : '';
    b.innerHTML = inf.icone;
    b.setAttribute('aria-label', inf.nome);
    var noLado = ladoTem(item, ativo);
    if (vista() === 'ambos' && !noLado) b.classList.add('fora');
    var o = !item.acao && noLado ? original(item, ativo) : null;
    var marcado = o && o.getAttribute('aria-pressed') === 'true';
    // a Barra do 3D é o pilar e a viga de aço do 2D: marca só o que foi clicado por último
    if (marcado && item.d3 && item.d3[0] === 'barra' && ativo === '3d' && escolhido['3d'] && escolhido['3d'] !== item.chave &&
        /^estr_/.test(escolhido['3d'])) marcado = false;
    if (marcado) b.classList.add('on');
    b.addEventListener('click', function (ev) { ev.stopPropagation(); acionar(item, grupo); });
    b.addEventListener('mouseenter', function () { mostrarBalao(b, item, inf, grupo); });
    b.addEventListener('mouseleave', esconderBalao);
    return b;
  }

  // a lista do ▾ (os menos usados, ou o grupo recolhido)
  var lista = null;
  function fecharLista() { if (lista) { lista.remove(); lista = null; } }
  function abrirLista(ancora, itens, grupo) {
    fecharLista();
    lista = el('div', 'faixa-lista');
    itens.forEach(function (item) {
      var inf = info(item);
      var li = el('button', 'fx-li' + (vista() === 'ambos' && !ladoTem(item, ativo) ? ' fora' : ''));
      li.type = 'button';
      if (inf.o2 && item.d2) li.dataset.id2 = item.d2[0] || '';
      if (inf.o3 && item.d3) li.dataset.id3 = item.d3[0] || '';
      li.innerHTML = inf.icone;
      li.appendChild(el('span', '', inf.nome));
      li.addEventListener('click', function (ev) { ev.stopPropagation(); acionar(item, grupo); });
      lista.appendChild(li);
    });
    document.body.appendChild(lista);
    var r = ancora.getBoundingClientRect();
    lista.style.left = Math.min(r.left - 8, window.innerWidth - 260) + 'px';
    lista.style.top = (r.bottom + 4) + 'px';
  }

  function presente(item) {
    if (item.acao) return visivel('2d');
    var v = vista();
    return (v !== '3d' && existe(item, '2d')) || (v !== '2d' && existe(item, '3d'));
  }

  function desenhar() {
    agendado = null;
    var caixa = $('#faixa-ferramentas');
    if (!caixa) return;
    ligarColunas();
    esconderBalao();
    var disc = gruposDaDisciplina();
    var grupos = GRUPOS.concat(disc);
    var extra = sobras(grupos);
    caixa.replaceChildren();
    var blocos = [];
    grupos.forEach(function (g) {
      var mais = (g.mais || []).concat(g.nome === 'Modificar' ? extra : []).filter(presente);
      var itens = (g.itens || []).filter(presente);
      if (!itens.length && !mais.length && !(g.seletor && g.seletor.length)) return;
      var bl = el('div', 'fx-grupo');
      bl.dataset.grupo = g.nome;
      if (g.seletor && g.seletor.length && visivel('2d')) {
        var s = el('span', 'fx-disc');
        g.seletor.forEach(function (ob) {
          var sb = el('button', ob.getAttribute('aria-pressed') === 'true' ? 'on' : '', ob.textContent);
          sb.type = 'button';
          sb.title = ob.title;
          sb.addEventListener('click', function (ev) { ev.stopPropagation(); ob.click(); pedirDesenho(); });
          s.appendChild(sb);
        });
        bl.appendChild(s);
      }
      itens.forEach(function (it) { bl.appendChild(botao(it, g.nome)); });
      if (mais.length) {
        var m = el('button', 'fx-mais', '▾');
        m.type = 'button';
        m.title = 'mais ferramentas';
        m.addEventListener('click', function (ev) { ev.stopPropagation(); abrirLista(m, mais, g.nome); });
        bl.appendChild(m);
      }
      bl._itens = itens.concat(mais);
      bl._recolhe = g.recolhe || 0;
      caixa.appendChild(bl);
      blocos.push(bl);
    });
    desenharContexto(caixa);
    // nada a mostrar (o 3D no modo ver, sozinho na tela): a faixa sai; volta quando o editor ou o 2D aparecem
    caixa.style.display = caixa.children.length ? '' : 'none';
    // não cabe: recolhe os grupos (Planta, Anotar, Modificar, Desenhar) num botão com a última usada + ▾
    var ordem = blocos.filter(function (b) { return b._recolhe; }).sort(function (a, b) { return a._recolhe - b._recolhe; });
    for (var i = 0; i < ordem.length && caixa.scrollWidth > caixa.clientWidth + 1; i++) recolher(ordem[i]);
    marcarLado();
  }

  function recolher(bl) {
    var g = bl.dataset.grupo;
    var itens = bl._itens;
    var it = itens.filter(function (x) { return x.chave === ultima[g]; })[0] ||
      itens.filter(function (x) { var o = !x.acao && ladoTem(x, ativo) ? original(x, ativo) : null; return o && o.getAttribute('aria-pressed') === 'true'; })[0] || itens[0];
    bl.replaceChildren(botao(it, g));
    var m = el('button', 'fx-mais', '▾');
    m.type = 'button';
    m.title = g;
    m.addEventListener('click', function (ev) { ev.stopPropagation(); abrirLista(m, itens, g); });
    bl.appendChild(m);
    bl.classList.add('recolhido');
  }

  // ------------------------------------------------------------ a peça selecionada: o grupo verde
  function selecaoDe(lado) {
    var w = janela(lado);
    try {
      if (lado === '3d') {
        var ids = Array.from(w.editor.selecao.ids || []);
        var e = ids.length === 1 ? w.editor.documento.get(ids[0]) : null;
        return { n: ids.length, nome: e ? (e.nome || e.perfil || e.tipo) : '' };
      }
      var sel = Array.from(w.cad.tela.selecao || []);
      var d = sel.length === 1 ? w.cad.doc.get(sel[0]) : null;
      var at = (d && d.atributos) || {};
      return { n: sel.length, nome: at.posicao || at.marca || at.elemento || '' };
    } catch (e) { return { n: 0, nome: '' }; }
  }
  function desenharContexto(caixa) {
    var s = visivel(ativo) ? selecaoDe(ativo) : { n: 0 };
    contexto = ativo + ':' + s.n + ':' + s.nome;
    if (!s.n) return;
    var w = janela(ativo);
    var bl = el('div', 'fx-grupo fx-ctx');
    bl.dataset.grupo = 'contexto';
    bl.appendChild(el('span', 'fx-ctx-nome', s.n === 1 ? (s.nome || '1 selecionado') : s.n + ' selecionados'));
    function acao(txt, fn, titulo) {
      var b = el('button', 'fx-txt', txt);
      b.type = 'button';
      if (titulo) b.title = titulo;
      b.addEventListener('click', function (ev) { ev.stopPropagation(); try { fn(); } catch (e) { /* a tela decide */ } pedirDesenho(); });
      bl.appendChild(b);
    }
    acao('Propriedades', function () { if (w.metalicaPaineis) w.metalicaPaineis(true); }, 'Mostra o painel de propriedades deste lado (F4)');
    var d = docDe(ativo);
    var ver = ativo === '2d' && d && d.querySelector('header.topo [data-acao="ver-3d"]');
    if (ver) acao('Ver no 3D', function () { ver.click(); }, ver.title);
    acao('Apagar', function () { (ativo === '2d' ? w.cad : w.editor).apagarSelecao(); }, 'Apaga a seleção (Del)');
    caixa.appendChild(bl);
  }

  // ------------------------------------------------------------ o lado ativo
  function marcarLado() {
    ['2d', '3d'].forEach(function (lado) {
      var l = document.getElementById('lado-' + lado);
      if (l) l.classList.toggle('faixa-ativo', vista() === 'ambos' && ativo === lado);
    });
    var caixa = $('#faixa-ferramentas');
    if (caixa) caixa.dataset.lado = ativo;
  }
  function mudarLado(lado) {
    if (ativo === lado) return;
    ativo = lado;
    pedirDesenho();
  }

  // ------------------------------------------------------------ acompanhar as telas
  function pedirDesenho() { if (!agendado) agendado = requestAnimationFrame(desenhar); }
  // cada coluna é observada uma vez (a barra da disciplina pode aparecer depois: o contêiner delas também)
  var ligadas = new WeakSet();
  function ligarColunas() {
    ['2d', '3d'].forEach(function (lado) {
      var d = docDe(lado);
      if (!d) return;
      observados[lado] = d;
      var area = d.querySelector('.area');
      if (area && !ligadas.has(area)) { ligadas.add(area); new MutationObserver(pedirDesenho).observe(area, { childList: true }); }
      ['barra-ferramentas', 'barra-disciplina'].forEach(function (id) {
        var c = d.getElementById(id);
        if (!c || ligadas.has(c)) return;
        ligadas.add(c);
        new MutationObserver(pedirDesenho).observe(c, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-pressed', 'hidden'] });
      });
    });
  }
  function iniciar() {
    var caixa = $('#faixa-ferramentas');
    if (!caixa) return;
    ['2d', '3d'].forEach(function (lado) {
      var f = document.getElementById(QUADRO[lado]);
      if (!f) return;
      f.addEventListener('mouseenter', function () { mudarLado(lado); });
      f.addEventListener('load', function () {
        observados[lado] = null;
        pedirDesenho();                      // a tela trocou (o editor virou o modo ver): os botões da anterior saem
        var t0 = Date.now();
        (function esperar() {
          var d = docDe(lado);
          if (d && d.querySelector('#barra-ferramentas .ferramenta')) { pedirDesenho(); return; }
          if (Date.now() - t0 < 60000) setTimeout(esperar, 250);
        })();
      });
    });
    document.addEventListener('click', function () { fecharLista(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fecharLista(); });
    window.addEventListener('resize', pedirDesenho);
    // a seleção muda dentro das telas: confere a cada meio segundo (só redesenha quando muda)
    setInterval(function () {
      var s = visivel(ativo) ? selecaoDe(ativo) : { n: 0, nome: '' };
      if (ativo + ':' + s.n + ':' + s.nome !== contexto) pedirDesenho();
    }, 500);
    pedirDesenho();
  }

  window.faixaFerramentas = {
    lado: function () { return ativo; },
    usarLado: function (lado) { mudarLado(lado); },
    vista: function (v) { if (v !== 'ambos') ativo = v; pedirDesenho(); },
    redesenhar: pedirDesenho,
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
