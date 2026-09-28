/* A barra única da área de trabalho (/dividida): o menu geral do projeto, o mesmo em qualquer vista
 * (2D, 2D + 3D, 3D) e em qualquer projeto — a vista só muda o que aparece embaixo.
 *
 * Os menus não são mais os de cada tela juntados: são um mapa próprio, por assunto (MAPA, abaixo) —
 * Arquivo (salvar, importar, exportar; o IFC entrou aqui), Desenhos (o Desenho, os Detalhamentos e as
 * Vistas do modelo de antes), Estrutura (o Lançamento de antes: lançar pelo arquitetônico, o projeto
 * recebido, eixos e apoios), Cálculo e Ver. O Editar saiu: desfazer e refazer são as setas da barra
 * (no lado em que se mexeu por último; Ctrl+Z e Ctrl+Y continuam em cada lado).
 *
 * Cada item aciona o comando original da sua tela (o botão do menu dela, que continua lá, escondido).
 * Tela ainda não carregada ou escondida: a vista troca para mostrar aquele lado, espera a tela ficar
 * pronta e aciona — o diálogo que o comando abre precisa aparecer.
 *
 * O Salvo e a busca de peças do 3D vêm para a barra (os próprios elementos, movidos, ligados ao 3D);
 * antes de o 3D carregar, ficam no lugar deles uma cópia parada, para a barra não mudar.
 */
(function () {
  'use strict';
  var LADOS = {
    '2d': { id: 'f2d', titulo: 'Desenho 2D', pronto: function (w) { return !!(w && w.cad); } },
    '3d': { id: 'f3d', titulo: 'Modelo 3D', pronto: function (w) { return !!(w && w.editor); } },
  };

  function T(t) { return { titulo: t }; }
  var HR = '---';
  function I(texto, lado, acao, extra) { var o = { texto: texto, lado: lado, acao: acao }; for (var k in extra || {}) o[k] = extra[k]; return o; }
  function V(texto, lado, vista, kbd) { return { texto: texto, lado: lado, vista: vista, kbd: kbd }; }

  var MAPA = [
    { nome: 'Arquivo', itens: [
      I('Salvar o modelo 3D', '3d', 'salvar'),
      I('Salvar o desenho 2D', '2d', 'salvar', { kbd: 'Ctrl+S' }),
      I('Salvar o modelo como…', '3d', 'salvar-como'),
      I('Restaurar modelo anterior…', '3d', 'restaurar-modelo'),
      HR, T('Importar'),
      I('IFC de outro programa…', '3d', 'importar-ifc'),
      I('DXF ou PDF neste desenho…', '2d', 'importar-dxf'),
      I('Arquitetônico do cliente (DXF/PDF)…', '2d', 'arquitetonico'),
      I('Projeto recebido (DXF/PDF) → modelo 3D e IFC…', '2d', 'projeto-2d'),
      I('Inspecionar um IFC…', '3d', 'inspecionar-ifc'),
      I('Detalhar as peças de um IFC…', '3d', 'detalhar-ifc'),
      HR, T('Exportar'),
      I('IFC do modelo', '3d', 'exportar-ifc'),
      I('DXF deste desenho…', '2d', 'exportar-dxf'),
      I('PDF deste desenho', '2d', 'exportar-pdf'),
      I('PDF de todas as pranchas…', '2d', 'pdf-pranchas'),
      HR,
      I('Abrir a pasta dos desenhos', '2d', 'abrir-pasta'),
      HR, T('Outros modelos'),
      I('Gerar do galpão dimensionado…', '3d', 'do-galpao'),
      I('Abrir modelo de um arquivo…', '3d', 'abrir'),
      I('Modelo de exemplo', '3d', 'exemplo'),
      I('Novo modelo em branco', '3d', 'novo'),
    ] },
    { nome: 'Desenhos', itens: [
      I('Abrir desenho do projeto…', '2d', 'abrir'),
      I('Novo desenho em branco…', '2d', 'novo'),
      I('Excluir desenhos…', '2d', 'excluir-desenhos'),
      HR, T('Gerar do modelo 3D'),
      I('Detalhar peças e conjuntos…', '3d', 'detalhar-pecas'),
      I('Desenho do corte atual (ferramenta Seção)', '3d', 'desenho-corte', { kbd: 'G' }),
      I('Vistas da seleção…', '3d', 'desenho-selecao'),
      I('Corte por plano…', '2d', 'corte'),
      HR, T('Inserir vista do modelo no desenho'),
      V('Frente', '2d', 'frente'), V('Trás', '2d', 'tras'), V('Lateral esquerda', '2d', 'esquerda'),
      V('Lateral direita', '2d', 'direita'), V('Planta (topo)', '2d', 'topo'), V('Vista inferior', '2d', 'inferior'),
      I('Estilos do desenho…', '2d', 'estilos'),
      HR, T('Pranchas'),
      I('Montar pranchas (automático)…', '2d', 'pranchas'),
      I('Inserir folha (prancha)…', '2d', 'inserir-folha'),
      I('Gerar pranchas das folhas', '2d', 'pranchas-das-folhas'),
      HR, T('Detalhamento ↔ modelo 3D'),
      I('Ver no 3D a peça selecionada', '2d', 'ver-3d'),
      I('Selecionar tudo da mesma peça', '2d', 'selecionar-peca'),
      I('Ajustar tamanho da chapa…', '2d', 'ajustar-tamanho'),
      I('Aplicar peças da célula ao modelo 3D', '2d', 'aplicar-pecas'),
      I('Aplicar furos e tamanho ao modelo 3D', '2d', 'aplicar-furos'),
      HR,
      I('Lista de materiais…', '3d', 'materiais'),
    ] },
    { nome: 'Estrutura', itens: [
      T('Lançar pelo arquitetônico do cliente'),
      I('Abrir a planta de lançamento', '2d', 'planta-lancamento'),
      I('Calibrar escala do arquitetônico', '2d', 'calibrar'),
      I('Malha de eixos…', '2d', 'malha'),
      I('Gravar eixos no projeto', '2d', 'gravar-eixos'),
      I('Lançar estrutura nos eixos…', '3d', 'lancar-estrutura'),
      HR, T('Projeto recebido (DXF do projetista)'),
      I('Montar o 3D pela planta…', '2d', 'montar-planta'),
      I('Ler folhas e considerações de cálculo', '2d', 'folhas-recebidas'),
      I('Reconhecer peças pelos perfis escritos…', '2d', 'reconhecer'),
      I('Peça do catálogo das linhas selecionadas…', '2d', 'peca-catalogo'),
      I('Gerar modelo 3D do desenho…', '2d', 'gerar-3d'),
      I('Treliças lidas…', '3d', 'trelicas-lidas'),
      HR, T('Modelo'),
      I('Eixos da obra…', '3d', 'eixos-obra'),
      I('Cantos redondos…', '3d', 'cantos-redondos'),
      I('Verificar apoios…', '3d', 'verificar-apoios'),
      HR,
      { texto: 'Ligações e acessórios…', link: '/ligacoes' },
    ] },
    { nome: 'Cálculo', itens: [
      I('Calcular estrutura', '3d', 'mapa-esforcos', { kbd: 'F9' }),
      I('Resultado da análise…', '3d', 'resultado-analise'),
      I('Esforços da estrutura…', '3d', 'esforcos'),
      I('Dimensionar: o perfil mais leve que passa…', '3d', 'dimensionar'),
      I('Memorial do dimensionamento (PDF)', '3d', 'memorial-lancamento'),
    ] },
    { nome: 'Ver', itens: [
      T('Modelo 3D'),
      V('Topo', '3d', 'topo', '1'), V('Frente', '3d', 'frente', '2'), V('Trás', '3d', 'tras', '3'),
      V('Esquerda', '3d', 'esquerda', '4'), V('Direita', '3d', 'direita', '5'), V('Inferior', '3d', 'inferior', '6'),
      V('Isométrica', '3d', 'isometrica', '7'),
      I('Perspectiva / ortográfica', '3d', 'alternar-projecao'),
      { texto: 'Sombreado', lado: '3d', sel: '#modos-exibicao [data-modo="sombreado"]', marcado: 'aria-pressed' },
      { texto: 'Sombreado com arestas', lado: '3d', sel: '#modos-exibicao [data-modo="sombreado_arestas"]', marcado: 'aria-pressed' },
      { texto: 'Só arestas', lado: '3d', sel: '#modos-exibicao [data-modo="arestas"]', marcado: 'aria-pressed' },
      { texto: 'Raio-X', lado: '3d', sel: '#modos-exibicao [data-modo="raiox"]', marcado: 'aria-pressed' },
      { texto: 'Esqueleto (só linhas)', lado: '3d', sel: '#modos-exibicao [data-esqueleto]', marcado: 'aria-pressed' },
      I('Sombras', '3d', 'sombras'),
      I('Arquitetônico, eixos e níveis', '3d', 'referencia'),
      I('Isolar seleção / voltar ao modelo', '3d', 'isolar'),
      I('Inverter seleção', '3d', 'inverter-selecao'),
      I('Zoom na extensão', '3d', 'zoom-extensao', { kbd: 'Z' }),
      I('Zoom na seleção', '3d', 'zoom-selecao'),
      I('Diagnóstico de desempenho…', '3d', 'desempenho'),
      HR, T('Desenho 2D'),
      I('Zoom na extensão', '2d', 'zoom-extensao', { kbd: 'Z' }),
      I('Zoom na seleção', '2d', 'zoom-selecao'),
      I('Grade ligada/desligada', '2d', 'grade'),
      I('Orto ligado/desligado', '2d', 'orto', { kbd: 'F8' }),
      HR, T('2D + 3D lado a lado'),
      { texto: 'Seguir a seleção de um lado no outro', fn: 'seguir' },
      { texto: 'Treliça escolhida no 3D: o 2D mostra a planta', fn: 'modo-planta' },
      { texto: 'Treliça escolhida no 3D: o 2D mostra a elevação', fn: 'modo-elevacao' },
      { texto: 'Trocar os lados', fn: 'trocar' },
      HR,
      { texto: 'Tema claro / escuro', fn: 'tema' },
      { texto: 'Ajuda do programa…', link: '/ajuda', nova: true },
    ] },
  ];

  var aberto = null;
  var ultimoLado = null;          // o lado em que se mexeu por último (as setas de desfazer)

  function $(s) { return document.querySelector(s); }
  function quadro(lado) { return document.getElementById(LADOS[lado].id); }
  function janela(lado) { try { return quadro(lado).contentWindow; } catch (e) { return null; } }
  function docPronto(lado) {
    var w = janela(lado);
    try { return w && LADOS[lado].pronto(w) ? w.document : null; } catch (e) { return null; }
  }
  function vista() { return window.vistaAtual ? window.vistaAtual() : 'ambos'; }
  function visivel(lado) { var v = vista(); return v === 'ambos' || v === lado; }

  /** o elemento original de um item na tela dele */
  function original(it, d) {
    if (!d) return null;
    try {
      if (it.sel) return d.querySelector(it.sel);
      if (it.vista) return d.querySelector('header.topo [data-vista="' + it.vista + '"]');
      if (it.acao) return d.querySelector('header.topo [data-acao="' + it.acao + '"]') || d.querySelector('[data-acao="' + it.acao + '"]');
    } catch (e) { return null; }
    return null;
  }

  // ------------------------------------------------------------ os menus
  function montarBarra() {
    var caixa = $('#menus-unicos');
    if (!caixa || caixa.children.length) return;
    MAPA.forEach(function (menu) {
      var m = document.createElement('div');
      m.className = 'menu';
      m.dataset.nome = menu.nome;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'menu-botao';
      b.textContent = menu.nome;
      var lista = document.createElement('div');
      lista.className = 'menu-lista';
      m.append(b, lista);
      b.addEventListener('click', function (ev) { ev.stopPropagation(); if (aberto === m) fechar(); else abrir(m, menu); });
      b.addEventListener('mouseenter', function () { if (aberto && aberto !== m) abrir(m, menu); });
      caixa.appendChild(m);
    });
    // desfazer / refazer: no lado em que se mexeu por último
    var setas = document.createElement('span');
    setas.className = 'setas-desfazer';
    [['desfazer', '↶', 'Desfazer (Ctrl+Z) no lado em que você mexeu por último'],
     ['refazer', '↷', 'Refazer (Ctrl+Y) no lado em que você mexeu por último']].forEach(function (s) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = s[1];
      b.title = s[2];
      b.addEventListener('click', function () { executar({ lado: ladoDasSetas(), acao: s[0] }); });
      setas.appendChild(b);
    });
    caixa.appendChild(setas);
  }

  function ladoDasSetas() {
    var v = vista();
    if (v !== 'ambos') return v;
    return ultimoLado || '3d';
  }

  function marcado(it) {
    if (it.fn === 'seguir') { var s = $('#seguir'); return !!(s && s.checked); }
    if (it.fn === 'modo-planta' || it.fn === 'modo-elevacao') {
      var b = document.querySelector('.grupo-modo button[data-modo="' + it.fn.slice(5) + '"]');
      return !!(b && b.classList.contains('ativo'));
    }
    if (it.marcado) { var o = original(it, docPronto(it.lado)); return !!(o && o.getAttribute(it.marcado) === 'true'); }
    return null;
  }

  function abrir(m, menu) {
    fechar();
    var lista = m.querySelector('.menu-lista');
    lista.replaceChildren();
    menu.itens.forEach(function (it) {
      if (it === HR) { lista.appendChild(document.createElement('hr')); return; }
      if (it.titulo) {
        var t = document.createElement('div');
        t.className = 'menu-titulo';
        t.textContent = it.titulo;
        lista.appendChild(t);
        return;
      }
      var d = it.lado ? docPronto(it.lado) : null;
      var o = original(it, d);
      if (d && it.lado && !o) return;                 // a tela não tem esse comando (versão, contexto)
      if (o && (o.hidden || o.closest('[hidden]') && !o.closest('header.topo[hidden]'))) return;
      var b = document.createElement('button');
      b.type = 'button';
      var ok = marcado(it);
      b.textContent = (ok === null ? '' : ok ? '✓ ' : '   ') + it.texto;
      if (ok !== null) b.classList.add('marcavel');
      if (it.kbd) { var k = document.createElement('kbd'); k.textContent = it.kbd; b.appendChild(k); }
      if (it.lado) b.title = LADOS[it.lado].titulo + (o && o.title ? ' — ' + o.title : '');
      if (o && o.disabled) b.disabled = true;
      b.addEventListener('click', function (ev) { ev.stopPropagation(); fechar(); executar(it); });
      lista.appendChild(b);
    });
    m.classList.add('aberto');
    aberto = m;
  }

  function fechar() {
    if (aberto) aberto.classList.remove('aberto');
    aberto = null;
  }

  // ------------------------------------------------------------ executar
  function executar(it) {
    if (it.link) { if (it.nova) window.open(it.link, '_blank', 'noopener'); else location.href = it.link; return; }
    if (it.fn) { funcao(it.fn); return; }
    if (!visivel(it.lado) && window.mostrarVista) window.mostrarVista(it.lado);
    var inicio = Date.now();
    (function tentar() {
      var d = docPronto(it.lado);
      if (d) {
        var o = original(it, d);
        if (o) { ultimoLado = it.lado; o.click(); }
        else console.warn('barra única: comando não achado na tela', it);
        return;
      }
      if (Date.now() - inicio < 60000) setTimeout(tentar, 200);
    })();
  }

  function funcao(fn) {
    if (fn === 'seguir') { var s = $('#seguir'); if (s) s.click(); return; }
    if (fn === 'modo-planta' || fn === 'modo-elevacao') { var b = document.querySelector('.grupo-modo button[data-modo="' + fn.slice(5) + '"]'); if (b) b.click(); return; }
    if (fn === 'trocar') { var t = $('#btn-trocar'); if (t) t.click(); return; }
    if (fn === 'tema') {
      // o tema efetivo: o escolhido ou, sem escolha, o do sistema (como as telas decidem)
      var efetivo = function (d, w) {
        return d.documentElement.getAttribute('data-tema') || (w.matchMedia && w.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
      };
      var raiz = document.documentElement;
      var novo = efetivo(document, window) === 'escuro' ? 'claro' : 'escuro';
      raiz.setAttribute('data-tema', novo);
      try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* sem armazenamento */ }
      // as duas telas: cada uma pelo próprio comando (o 3D troca também as cores da cena)
      ['2d', '3d'].forEach(function (lado) {
        var d = docPronto(lado);
        if (!d || efetivo(d, janela(lado)) === novo) return;
        var o = d.querySelector('[data-acao="alternar-tema"]');
        if (o) o.click();
      });
    }
  }

  // ------------------------------------------------------------ Salvo e busca do 3D na barra
  var IDS_RAPIDOS = ['btn-salvar', 'busca-pecas'];
  var docRapidos = null;
  function copiasParadas() {
    var caixa = $('#rapidos-3d');
    if (!caixa || caixa.children.length) return;
    fetch('/editor', { cache: 'no-store' }).then(function (r) { return r.text(); }).then(function (html) {
      if (caixa.children.length) return;
      var d = new DOMParser().parseFromString(html, 'text/html');
      IDS_RAPIDOS.forEach(function (id) {
        var e = d.getElementById(id);
        if (!e) return;
        var c = document.importNode(e, true);
        c.dataset.parado = id;
        c.removeAttribute('id');
        c.querySelectorAll('[id]').forEach(function (x) { x.removeAttribute('id'); });
        if (id === 'btn-salvar') { c.title = 'O modelo 3D grava sozinho; o desenho 2D também'; }
        var campo = c.tagName === 'INPUT' ? c : c.querySelector('input');
        if (campo) campo.addEventListener('focus', function () { buscarNo3D(); });
        caixa.appendChild(c);
      });
      compactar();
    }).catch(function () { /* fica sem */ });
  }

  /** a busca procura peças do modelo: sem o 3D à vista, abre o 2D + 3D (a peça escolhida aparece nos dois) */
  function buscarNo3D() {
    if (vista() === '2d' && window.mostrarVista) window.mostrarVista('ambos');
    var t0 = Date.now();
    (function focar() {
      var real = document.getElementById('busca-campo');
      if (real) { real.focus(); return; }
      if (Date.now() - t0 < 60000) setTimeout(focar, 200);
    })();
  }

  function trazerRapidos() {
    var d = docPronto('3d');
    var caixa = $('#rapidos-3d');
    if (!d || !caixa || docRapidos === d) return;
    docRapidos = d;
    [].slice.call(caixa.children).forEach(function (e) { e.remove(); });     // as cópias paradas e os de uma carga anterior
    IDS_RAPIDOS.forEach(function (id) {
      var e = d.getElementById(id);
      if (!e) return;
      e.parentNode.insertBefore(d.createComment('barra única: ' + id), e);
      caixa.appendChild(document.adoptNode(e));
    });
    var campo = document.getElementById('busca-campo');
    if (campo) campo.addEventListener('focus', function () { if (vista() === '2d' && window.mostrarVista) window.mostrarVista('ambos'); });
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
    var busca = document.querySelector('#rapidos-3d input');
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
  function iniciar() {
    montarBarra();
    copiasParadas();
    quadro('3d').addEventListener('load', function () {
      docRapidos = null;
      var t0 = Date.now();
      (function esperar() {
        if (docPronto('3d')) { trazerRapidos(); return; }
        if (Date.now() - t0 < 60000) setTimeout(esperar, 250);
      })();
    });
    document.addEventListener('click', function (ev) {
      if (aberto && !ev.target.closest('#menus-unicos')) fechar();
      var r = document.getElementById('busca-resultados');
      if (r && !r.hidden && !ev.target.closest('#busca-pecas')) r.hidden = true;
    });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fechar(); });
    // o clique dentro de um dos lados: fecha o menu e marca o lado das setas de desfazer
    window.addEventListener('blur', function () {
      fechar();
      setTimeout(function () {
        var a = document.activeElement;
        if (a && a.id === 'f2d') ultimoLado = '2d';
        else if (a && a.id === 'f3d') ultimoLado = '3d';
      }, 0);
    });
    window.addEventListener('resize', function () { requestAnimationFrame(compactar); });
    setTimeout(compactar, 800);
  }

  window.barraUnica = {
    vista: function () { fechar(); requestAnimationFrame(compactar); },
    executar: executar,
    mapa: MAPA,
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
