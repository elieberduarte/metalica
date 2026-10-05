/* A barra única da área de trabalho (/dividida): o menu geral do projeto, o mesmo em qualquer vista
 * (2D, 2D + 3D, 3D) e em qualquer projeto — a vista só muda o que aparece embaixo.
 *
 * Os menus não são mais os de cada tela juntados: são um mapa próprio, na ordem da obra (MAPA, abaixo) —
 * Arquivo, Modelo, Cálculo, Desenho, Produção, Ver e ?; submenus para as listas longas, roteiros numerados
 * onde a ordem importa, nenhum 2D/3D à mostra (o item sabe o lado dele). O Editar saiu: desfazer e refazer
 * são as setas da barra (no lado em que se mexeu por último; Ctrl+Z e Ctrl+Y continuam em cada lado).
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

  function S(texto, itens, extra) { var o = { texto: texto, sub: itens }; for (var k in extra || {}) o[k] = extra[k]; return o; }
  function F(texto, fn, extra) { var o = { texto: texto, fn: fn }; for (var k in extra || {}) o[k] = extra[k]; return o; }

  // Os menus da área de trabalho (UI1, 30/09/2026; enxutos em 03/10/2026 — Projeto/Navegacao-analise-e-proposta-2026-10-03.pdf):
  // Arquivo · Modelo (com o cálculo) · Detalhamento · Ver · ?. Ir para outra tela é pela barra de etapas (etapas.js). Sem 2D/3D à mostra: o item sabe o lado dele e a
  // vista troca sozinha. `antes` é onde o item ficava até a 0.8.53 (? › Onde foi parar…); `dica` sai miúda
  // embaixo; `requer: 'sel'` apaga o item, com o motivo, sem peça selecionada no lado dele.
  var MAPA = [
    { nome: 'Arquivo', itens: [
      { texto: 'Salvar', kbd: 'Ctrl+S', varios: [['2d', 'salvar'], ['3d', 'salvar']], dica: 'o modelo e o desenho aberto',
        antes: ['Arquivo › Salvar o modelo 3D', 'Arquivo › Salvar o desenho 2D'] },
      I('Salvar o modelo como…', '3d', 'salvar-como', { antes: 'Arquivo › Salvar o modelo como…' }),
      I('Versões anteriores do modelo…', '3d', 'restaurar-modelo', { antes: 'Arquivo › Restaurar modelo anterior…' }),
      HR,
      S('Novo modelo', [
        I('Em branco', '3d', 'novo', { antes: 'Arquivo › Novo modelo em branco' }),
        I('Do galpão dimensionado…', '3d', 'do-galpao', { antes: 'Arquivo › Gerar do galpão dimensionado…' }),
        I('Modelo de exemplo', '3d', 'exemplo', { antes: 'Arquivo › Modelo de exemplo' }),
      ]),
      I('Abrir modelo de um arquivo…', '3d', 'abrir', { antes: 'Arquivo › Abrir modelo de um arquivo…' }),
      HR,
      S('Importar', [
        I('IFC de outro programa…', '3d', 'importar-ifc', { antes: 'Arquivo › IFC de outro programa…' }),
        I('Arquitetônico do cliente (DXF/PDF)…', '2d', 'arquitetonico', { dica: 'é o passo 1 de Modelo › Lançar pelo arquitetônico', antes: 'Arquivo › Arquitetônico do cliente (DXF/PDF)…' }),
        I('Projeto do projetista (DXF/PDF)…', '2d', 'projeto-2d', { dica: 'é o passo 1 de Modelo › Montar pelo projeto recebido', antes: 'Arquivo › Projeto recebido (DXF/PDF) → modelo 3D e IFC…' }),
        I('DXF ou PDF dentro do desenho aberto…', '2d', 'importar-dxf', { antes: 'Arquivo › DXF ou PDF neste desenho…' }),
        HR,
        I('Só inspecionar um IFC (sem importar)…', '3d', 'inspecionar-ifc', { antes: 'Arquivo › Inspecionar um IFC…' }),
      ]),
      S('Exportar', [
        I('IFC do modelo', '3d', 'exportar-ifc', { antes: 'Arquivo › IFC do modelo' }),
        F('JSON do modelo', 'exportar-json', { dica: 'o modelo 3D inteiro no formato do programa (peças, camadas, materiais)' }),
        I('DXF do desenho aberto…', '2d', 'exportar-dxf', { antes: 'Arquivo › DXF deste desenho…' }),
        I('PDF do desenho aberto', '2d', 'exportar-pdf', { antes: 'Arquivo › PDF deste desenho' }),
        I('PDF de todas as pranchas…', '2d', 'pdf-pranchas', { antes: 'Arquivo › PDF de todas as pranchas…' }),
        I('DXF de todas as pranchas…', '2d', 'dxf-pranchas', { dica: 'todas juntas num arquivo, e uma por arquivo num ZIP', antes: 'Arquivo › DXF de todas as pranchas…' }),
      ]),
      HR,
      I('Abrir a pasta do projeto', '2d', 'abrir-pasta', { antes: 'Arquivo › Abrir a pasta dos desenhos' }),
    ] },
    { nome: 'Modelo', itens: [
      S('Lançar pelo arquitetônico', [
        T('do arquitetônico do cliente ao modelo 3D'),
        I('1. Importar o arquitetônico (DXF/PDF)…', '2d', 'arquitetonico', { antes: 'Arquivo › Arquitetônico do cliente (DXF/PDF)…' }),
        I('2. Abrir a planta de lançamento', '2d', 'planta-lancamento', { antes: 'Estrutura › Abrir a planta de lançamento' }),
        I('3. Calibrar a escala', '2d', 'calibrar', { antes: 'Estrutura › Calibrar escala do arquitetônico' }),
        I('4. Malha de eixos…', '2d', 'malha', { antes: 'Estrutura › Malha de eixos…' }),
        I('5. Gravar os eixos no projeto', '2d', 'gravar-eixos', { antes: 'Estrutura › Gravar eixos no projeto' }),
        I('6. Lançar a estrutura nos eixos…', '3d', 'lancar-estrutura', { antes: 'Estrutura › Lançar estrutura nos eixos…' }),
      ], { dica: 'passo a passo' }),
      S('Montar pelo projeto recebido', [
        T('do DXF do projetista ao modelo 3D'),
        I('1. Importar o projeto (DXF/PDF)…', '2d', 'projeto-2d', { antes: 'Arquivo › Projeto recebido (DXF/PDF) → modelo 3D e IFC…' }),
        I('2. Ler folhas e considerações de cálculo', '2d', 'folhas-recebidas', { antes: 'Estrutura › Ler folhas e considerações de cálculo' }),
        I('3. Reconhecer peças pelos perfis escritos…', '2d', 'reconhecer', { antes: 'Estrutura › Reconhecer peças pelos perfis escritos…' }),
        I('4. Montar o 3D pela planta…', '2d', 'montar-planta', { antes: 'Estrutura › Montar o 3D pela planta…' }),
        I('5. Conferir as treliças lidas…', '3d', 'trelicas-lidas', { antes: 'Estrutura › Treliças lidas…' }),
        HR,
        I('Gerar o 3D do desenho aberto…', '2d', 'gerar-3d', { antes: 'Estrutura › Gerar modelo 3D do desenho…' }),
        I('Peça do catálogo pelas linhas selecionadas…', '2d', 'peca-catalogo', { requer: 'sel', antes: 'Estrutura › Peça do catálogo das linhas selecionadas…' }),
      ], { dica: 'passo a passo' }),
      HR,
      I('Eixos da obra…', '3d', 'eixos-obra', { antes: 'Estrutura › Eixos da obra…' }),
      HR,
      S('Peça selecionada', [
        I('Cantos redondos…', '3d', 'cantos-redondos', { antes: 'Estrutura › Cantos redondos…' }),
        I('Dividir a peça em trechos', '3d', 'explodir', { requer: 'sel', dica: 'antes "Explodir peça": o Explodir do 2D é outro', antes: 'Estrutura › Explodir peça em trechos' }),
        I('Unir peças', '3d', 'juntar', { requer: 'sel', dica: 'antes "Juntar peças": o Juntar do 2D é outro', antes: 'Estrutura › Juntar peças' }),
      ]),
      I('Verificar apoios…', '3d', 'verificar-apoios', { antes: 'Estrutura › Verificar apoios…' }),
      { texto: 'Ligações e acessórios…', link: '/ligacoes', dica: 'abre a tela das ligações', antes: 'Estrutura › Ligações e acessórios…' },
      HR, T('cálculo'),
      I('Calcular a estrutura', '3d', 'mapa-esforcos', { kbd: 'F9', antes: 'Cálculo › Calcular estrutura' }),
      I('Dimensionar: o perfil mais leve que passa…', '3d', 'dimensionar', { antes: 'Cálculo › Dimensionar: o perfil mais leve que passa…' }),
      I('Resultado da análise…', '3d', 'resultado-analise', { antes: 'Cálculo › Resultado da análise…' }),
      I('Esforços da estrutura…', '3d', 'esforcos', { antes: 'Cálculo › Esforços da estrutura…' }),
      HR,
      I('Memorial do dimensionamento (PDF)', '3d', 'memorial-lancamento', { antes: 'Cálculo › Memorial do dimensionamento (PDF)' }),
    ] },
    // Detalhamento (03/10/2026): o Desenho e o detalhar/pranchas da Produção num menu só; Cálculo foi para o Modelo;
    // Produção e Comercial viraram etapas da barra do projeto (web/etapas.js)
    { nome: 'Detalhamento', itens: [
      I('Detalhar peças e conjuntos…', '3d', 'detalhar-pecas', { antes: 'Desenhos › Detalhar peças e conjuntos…' }),
      I('Detalhar as peças de um IFC…', '3d', 'detalhar-ifc', { dica: 'IFC do TecnoMETAL ou de outro programa', antes: 'Arquivo › Detalhar as peças de um IFC…' }),
      HR,
      S('Pranchas', [
        I('Montar pranchas (automático)…', '2d', 'pranchas', { antes: 'Desenhos › Montar pranchas (automático)…' }),
        I('Inserir folha…', '2d', 'inserir-folha', { antes: 'Desenhos › Inserir folha (prancha)…' }),
        I('Gerar pranchas das folhas', '2d', 'pranchas-das-folhas', { antes: 'Desenhos › Gerar pranchas das folhas' }),
        HR,
        I('Atualizar desenhos e pranchas agora', '2d', 'atualizar-desenhos', { antes: 'Desenhos › Atualizar desenhos e pranchas agora' }),
      ]),
      HR, T('desenhos'),
      S('Trocar de desenho', [
        { lista: 'desenhos' },
        HR,
        I('Outro desenho do projeto…', '2d', 'abrir', { antes: 'Desenhos › Abrir desenho do projeto…' }),
      ]),
      I('Novo desenho em branco…', '2d', 'novo', { antes: 'Desenhos › Novo desenho em branco…' }),
      I('Excluir desenhos…', '2d', 'excluir-desenhos', { antes: 'Desenhos › Excluir desenhos…' }),
      HR, T('trazer do modelo 3D'),
      S('Inserir vista do modelo', [
        V('Frente', '2d', 'frente'), V('Trás', '2d', 'tras'), V('Lateral esquerda', '2d', 'esquerda'),
        V('Lateral direita', '2d', 'direita'), V('Planta (topo)', '2d', 'topo'), V('Vista inferior', '2d', 'inferior'),
      ], { antes: 'Desenhos › Inserir vista do modelo no desenho' }),
      I('Corte por plano…', '2d', 'corte', { antes: 'Desenhos › Corte por plano…' }),
      I('Corte da ferramenta Seção', '3d', 'desenho-corte', { kbd: 'G', dica: 'o plano de corte ativo no 3D', antes: 'Desenhos › Desenho do corte atual (ferramenta Seção)' }),
      I('Vistas das peças selecionadas…', '3d', 'desenho-selecao', { requer: 'sel', antes: 'Desenhos › Vistas da seleção…' }),
      HR,
      I('Estilos do desenho…', '2d', 'estilos', { antes: 'Desenhos › Estilos do desenho…' }),
      HR,
      S('Peça do detalhamento selecionada', [
        I('Ver no 3D', '2d', 'ver-3d', { requer: 'sel', antes: 'Desenhos › Ver no 3D a peça selecionada' }),
        I('Selecionar tudo da mesma peça', '2d', 'selecionar-peca', { requer: 'sel', antes: 'Desenhos › Selecionar tudo da mesma peça' }),
        HR, T('levar ao modelo 3D'),
        I('Ajustar o tamanho da chapa…', '2d', 'ajustar-tamanho', { requer: 'sel', antes: 'Desenhos › Ajustar tamanho da chapa…' }),
        I('Aplicar as peças da célula', '2d', 'aplicar-pecas', { antes: 'Desenhos › Aplicar peças da célula ao modelo 3D' }),
        I('Aplicar furos e tamanho', '2d', 'aplicar-furos', { antes: 'Desenhos › Aplicar furos e tamanho ao modelo 3D' }),
      ]),
      HR,
      I('Lista de materiais…', '3d', 'materiais', { dica: 'a etapa Produção, na barra de cima', antes: 'Desenhos › Lista de materiais…' }),
    ] },
    { nome: 'Ver', itens: [
      S('Tela', [
        F('Só o 2D', 'vista-2d'), F('2D + 3D lado a lado', 'vista-ambos'), F('Só o 3D', 'vista-3d'),
        HR,
        F('Trocar os lados', 'trocar', { antes: 'Ver › Trocar os lados' }),
        F('Seguir a seleção de um lado no outro', 'seguir', { antes: 'Ver › Seguir a seleção de um lado no outro' }),
        T('treliça escolhida no 3D: o 2D mostra'),
        F('a planta', 'modo-planta', { antes: 'Ver › Treliça escolhida no 3D: o 2D mostra a planta' }),
        F('a elevação', 'modo-elevacao', { antes: 'Ver › Treliça escolhida no 3D: o 2D mostra a elevação' }),
      ]),
      HR, T('no lado ativo'),
      { texto: 'Zoom na extensão', kbd: 'Z', noAtivo: 'zoom-extensao', antes: ['Ver › Zoom na extensão (3D)', 'Ver › Zoom na extensão (2D)'] },
      { texto: 'Zoom na seleção', noAtivo: 'zoom-selecao', requer: 'sel', antes: ['Ver › Zoom na seleção (3D)', 'Ver › Zoom na seleção (2D)'] },
      I('Isolar a seleção / voltar ao modelo', '3d', 'isolar', { antes: 'Ver › Isolar seleção / voltar ao modelo' }),
      I('Inverter a seleção', '3d', 'inverter-selecao', { antes: 'Ver › Inverter seleção' }),
      HR, T('modelo 3D'),
      S('Olhar de', [
        V('Topo', '3d', 'topo', '1'), V('Frente', '3d', 'frente', '2'), V('Trás', '3d', 'tras', '3'),
        V('Esquerda', '3d', 'esquerda', '4'), V('Direita', '3d', 'direita', '5'), V('Inferior', '3d', 'inferior', '6'),
        V('Isométrica', '3d', 'isometrica', '7'),
        HR,
        I('Perspectiva / ortográfica', '3d', 'alternar-projecao', { antes: 'Ver › Perspectiva / ortográfica' }),
      ], { antes: 'Ver › Topo, Frente, Trás, Esquerda, Direita, Inferior, Isométrica' }),
      S('Estilo', [
        { texto: 'Sombreado', lado: '3d', sel: '#modos-exibicao [data-modo="sombreado"]', marcado: 'aria-pressed', antes: 'Ver › Sombreado' },
        { texto: 'Sombreado com arestas', lado: '3d', sel: '#modos-exibicao [data-modo="sombreado_arestas"]', marcado: 'aria-pressed', antes: 'Ver › Sombreado com arestas' },
        { texto: 'Só arestas', lado: '3d', sel: '#modos-exibicao [data-modo="arestas"]', marcado: 'aria-pressed', antes: 'Ver › Só arestas' },
        { texto: 'Raio-X', lado: '3d', sel: '#modos-exibicao [data-modo="raiox"]', marcado: 'aria-pressed', antes: 'Ver › Raio-X' },
        { texto: 'Esqueleto (só linhas)', lado: '3d', sel: '#modos-exibicao [data-esqueleto]', marcado: 'aria-pressed', antes: 'Ver › Esqueleto (só linhas)' },
        HR,
        I('Sombras', '3d', 'sombras', { antes: 'Ver › Sombras' }),
        HR, T('piso'),
        F('Grade suave', 'piso-grade', { dica: 'o tom do piso e a grade, que somem com a distância' }),
        F('Piso liso', 'piso-liso', { dica: 'só o tom do piso, sem linhas' }),
        F('Sem piso', 'piso-nenhum'),
      ]),
      I('Arquitetônico, eixos e níveis', '3d', 'referencia', { antes: 'Ver › Arquitetônico, eixos e níveis' }),
      HR, T('desenho 2D'),
      I('Grade', '2d', 'grade', { antes: 'Ver › Grade ligada/desligada' }),
      I('Orto', '2d', 'orto', { kbd: 'F8', antes: 'Ver › Orto ligado/desligado' }),
      HR, T('a tela do programa'),
      F('Painéis da direita', 'paineis', { kbd: 'F4', dica: 'propriedades, camadas… dos dois lados' }),
      F('Tema claro / escuro', 'tema', { antes: 'Ver › Tema claro / escuro' }),
    ] },
    { nome: '?', itens: [
      { texto: 'Ajuda do programa…', link: '/ajuda', nova: true, antes: 'Ver › Ajuda do programa…' },
      F('Onde foi parar cada item do menu antigo…', 'mapa', { dica: 'os menus mudaram na 0.8.54' }),
      HR,
      I('Diagnóstico de desempenho…', '3d', 'desempenho', { antes: 'Ver › Diagnóstico de desempenho…' }),
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
    if (it.fn && it.fn.indexOf('vista-') === 0) return vista() === it.fn.slice(6);
    if (it.fn === 'seguir') { var s = $('#seguir'); return !!(s && s.checked); }
    if (it.fn === 'modo-planta' || it.fn === 'modo-elevacao') {
      var b = document.querySelector('.grupo-modo button[data-modo="' + it.fn.slice(5) + '"]');
      return !!(b && b.classList.contains('ativo'));
    }
    if (it.marcado) { var o = original(it, docPronto(it.lado)); return !!(o && o.getAttribute(it.marcado) === 'true'); }
    return null;
  }

  /** há peça selecionada no lado? (tela não carregada: não se sabe — o comando decide) */
  function temSelecao(lado) {
    var w = janela(lado);
    try {
      if (lado === '3d') return !!(w.editor.selecao && w.editor.selecao.tamanho);
      return !!(w.cad.tela && w.cad.tela.selecao && w.cad.tela.selecao.size);
    } catch (e) { return true; }
  }
  /** o motivo de o item estar apagado ('' = pode) */
  function motivo(it) {
    if (it.requer !== 'sel') return '';
    var lado = it.lado || (it.noAtivo ? ladoDasSetas() : null);
    if (!lado || !docPronto(lado)) return '';
    return temSelecao(lado) ? '' : 'selecione uma peça antes';
  }
  function botaoDoItem(texto, miuda, ok) {
    var b = document.createElement('button');
    b.type = 'button';
    var rot = document.createElement('span');
    rot.className = 'rot';
    rot.appendChild(document.createTextNode((ok === null || ok === undefined ? '' : ok ? '✓ ' : '   ') + texto));
    if (miuda) { var s = document.createElement('small'); s.textContent = miuda; rot.appendChild(s); }
    b.appendChild(rot);
    if (ok !== null && ok !== undefined) b.classList.add('marcavel');
    return b;
  }
  /** sem linha no começo, no fim ou duas seguidas; título sem item embaixo some */
  function arrumar(lista) {
    var filhos = [].slice.call(lista.children);
    filhos.forEach(function (c, i) {
      var prox = filhos[i + 1];
      if (c.classList.contains('menu-titulo') && (!prox || prox.tagName === 'HR' || prox.classList.contains('menu-titulo'))) c.remove();
    });
    var anterior = null;
    [].slice.call(lista.children).forEach(function (c) {
      if (c.tagName === 'HR' && (!anterior || anterior.tagName === 'HR')) { c.remove(); return; }
      anterior = c;
    });
    var ult = lista.lastElementChild;
    if (ult && ult.tagName === 'HR') ult.remove();
  }
  function preencher(lista, itens) {
    itens.forEach(function (it) {
      if (it === HR) { lista.appendChild(document.createElement('hr')); return; }
      if (it.lista === 'desenhos') { listaDeDesenhos(lista); return; }
      if (it.titulo) {
        var t = document.createElement('div');
        t.className = 'menu-titulo';
        t.textContent = it.titulo;
        lista.appendChild(t);
        return;
      }
      if (it.sub) {
        var sub = document.createElement('div');
        sub.className = 'menu-lista submenu';
        preencher(sub, it.sub);
        if (!sub.querySelector('button')) return;             // nada do submenu existe nesta versão
        var caixa = document.createElement('div');
        caixa.className = 'item-sub';
        var bs = botaoDoItem(it.texto, it.dica, null);
        bs.classList.add('abre-sub');
        var seta = document.createElement('span');
        seta.className = 'seta-sub';
        seta.textContent = '▸';
        bs.appendChild(seta);
        bs.addEventListener('click', function (ev) {
          ev.stopPropagation();
          var abrir = !caixa.classList.contains('sub-aberto');
          [].forEach.call(lista.querySelectorAll(':scope > .item-sub.sub-aberto'), function (x) { x.classList.remove('sub-aberto'); });
          if (abrir) caixa.classList.add('sub-aberto');
        });
        caixa.append(bs, sub);
        lista.appendChild(caixa);
        return;
      }
      var o = null;
      if (it.lado) {
        var d = docPronto(it.lado);
        o = original(it, d);
        if (d && !o) return;                                    // a tela não tem esse comando (versão, contexto)
        if (o && (o.hidden || o.closest('[hidden]') && !o.closest('header.topo[hidden]'))) return;
      } else if (it.noAtivo) {
        var dl = docPronto(ladoDasSetas());
        if (dl && !original({ acao: it.noAtivo }, dl)) return;
      }
      var falta = motivo(it);
      var b = botaoDoItem(it.texto, falta || it.dica, marcado(it));
      if (it.kbd) { var k = document.createElement('kbd'); k.textContent = it.kbd; b.appendChild(k); }
      if (o && o.title) b.title = o.title;
      if ((o && o.disabled) || falta) b.disabled = true;
      b.addEventListener('click', function (ev) { ev.stopPropagation(); fechar(); executar(it); });
      lista.appendChild(b);
    });
    arrumar(lista);
  }

  function abrir(m, menu) {
    fechar();
    var lista = m.querySelector('.menu-lista');
    lista.replaceChildren();
    preencher(lista, menu.itens);
    m.classList.add('aberto');
    aberto = m;
    // perto da borda direita, os submenus abrem para a esquerda
    lista.classList.toggle('esq', lista.getBoundingClientRect().right + 300 > window.innerWidth);
  }

  /** os desenhos do projeto (o seletor da área, que continua escondido na barra): escolher um abre no 2D */
  function listaDeDesenhos(lista) {
    var sel = $('#desenho');
    if (!sel) return;
    [].forEach.call(sel.options, function (o) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'marcavel';
      var atual = o.value === sel.value;
      b.textContent = (atual ? '✓ ' : '   ') + o.textContent;
      if (sel.disabled) b.disabled = true;
      b.addEventListener('click', function (ev) {
        ev.stopPropagation();
        fechar();
        if (!visivel('2d') && window.mostrarVista) window.mostrarVista('2d');
        if (sel.value !== o.value) { sel.value = o.value; sel.dispatchEvent(new Event('change')); }
      });
      lista.appendChild(b);
    });
  }

  function fechar() {
    if (aberto) aberto.classList.remove('aberto');
    aberto = null;
  }

  // ------------------------------------------------------------ executar
  function executar(it) {
    if (it.link) {
      var proj = new URLSearchParams(location.search).get('projeto') || '';
      var url = it.link.replace('{projeto}', encodeURIComponent(proj));
      if (it.nova) window.open(url, '_blank', 'noopener'); else location.href = url;
      return;
    }
    if (it.fn) { funcao(it.fn); return; }
    if (it.varios) {                       // o mesmo comando em cada lado carregado (Salvar)
      it.varios.forEach(function (par) { var d = docPronto(par[0]); var o = original({ acao: par[1] }, d); if (o) o.click(); });
      return;
    }
    if (it.noAtivo) { executar({ lado: ladoDasSetas(), acao: it.noAtivo }); return; }
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
    if (fn.indexOf('vista-') === 0) { if (window.mostrarVista) window.mostrarVista(fn.slice(6)); return; }
    if (fn === 'paineis') { var p = $('#btn-paineis'); if (p) p.click(); return; }
    if (fn === 'mapa') { ondeFoiParar(); return; }
    if (fn === 'seguir') { var s = $('#seguir'); if (s) s.click(); return; }
    if (fn === 'modo-planta' || fn === 'modo-elevacao') { var b = document.querySelector('.grupo-modo button[data-modo="' + fn.slice(5) + '"]'); if (b) b.click(); return; }
    if (fn === 'trocar') { var t = $('#btn-trocar'); if (t) t.click(); return; }
    if (fn.indexOf('piso-') === 0) {                   // Ver › Estilo › Piso (o 3D guarda a escolha)
      var w3 = janela('3d');
      try { w3.editor.cena.definirPiso(fn.slice(5)); } catch (e) { /* 3D ainda carregando */ }
      return;
    }
    if (fn === 'exportar-json') { exportarJSON(); return; }
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
      iconeDoTema();
    }
  }

  /** Arquivo › Exportar › JSON do modelo (05/10/2026): o modelo aberto no 3D como está na tela, no mesmo formato
   *  do modelo.json do projeto (Documento.paraJSON), baixado como arquivo — vai para a pasta de downloads. */
  function exportarJSON() {
    if (window.mostrarVista && vista() === '2d') window.mostrarVista('3d');
    var t0 = Date.now();
    (function tentar() {
      var w3 = janela('3d'), ed = null;
      try { ed = w3 && w3.editor && w3.editor.documento ? w3.editor : null; } catch (e) { ed = null; }
      if (!ed) { if (Date.now() - t0 < 60000) setTimeout(tentar, 250); return; }
      if (!ed.documento.tamanho) { if (ed.dica) ed.dica('O modelo está vazio: nada para exportar.'); return; }
      var dados = ed.documento.paraJSON();
      var nome = String((ed.el && ed.el.nome && ed.el.nome.value) || dados.nome || 'modelo').trim() || 'modelo';
      var arquivo = nome.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ') + '.json';
      var blob = new Blob([JSON.stringify(dados, null, 1)], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = arquivo;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
      var kb = blob.size / 1024;
      var tam = kb > 1024 ? (kb / 1024).toFixed(1).replace('.', ',') + ' MB' : Math.round(kb) + ' kB';
      if (ed.dica) ed.dica('JSON exportado: ' + arquivo + ' (' + dados.entidades.length + ' objetos, ' + tam + ') — na pasta de downloads.');
    })();
  }

  /** o botão do tema mostra o que o clique faz: a lua no claro, o sol no escuro */
  function iconeDoTema() {
    var b = $('#btn-tema-area');
    if (!b) return;
    var t = document.documentElement.getAttribute('data-tema') ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
    b.innerHTML = t === 'escuro'
      ? '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg>'
      : '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';
    b.title = t === 'escuro' ? 'Tema claro' : 'Tema escuro';
    b.setAttribute('aria-label', b.title);
  }

  // ------------------------------------------------------------ ? › Onde foi parar cada item do menu antigo
  function ondeFoiParar() {
    var linhas = [];
    (function andar(itens, caminho) {
      itens.forEach(function (it) {
        if (!it || it === HR || it.titulo || it.lista) return;
        var aqui = caminho.concat([it.texto]);
        if (it.antes) [].concat(it.antes).forEach(function (a) { linhas.push([a, aqui.join(' › ')]); });
        if (it.sub) andar(it.sub, aqui);
      });
    })(MAPA.map(function (m) { return { texto: m.nome, sub: m.itens }; }), []);
    linhas.sort(function (a, b) { return a[0].localeCompare(b[0], 'pt-BR'); });
    var fundo = document.getElementById('onde-foi-parar');
    if (!fundo) {
      fundo = document.createElement('div');
      fundo.id = 'onde-foi-parar';
      fundo.className = 'onde-foi-parar';
      fundo.innerHTML = '<div class="cx"><div class="cab"><b>Onde foi parar cada item do menu antigo</b><button type="button">Fechar (Esc)</button></div>' +
        '<p>Os menus seguem a ordem da obra: Arquivo · Modelo · Cálculo · Desenho · Produção · Ver. Cada comando vai sozinho para o 2D ou para o 3D. ' +
        'No 3D, "Explodir peça em trechos" virou <b>Dividir a peça em trechos</b> e "Juntar peças" virou <b>Unir peças</b>.</p>' +
        '<input type="search" placeholder="filtrar (ex.: explodir, pranchas, zoom)"><div class="tab"><table><thead><tr><th>Antes</th><th>Agora</th></tr></thead><tbody></tbody></table></div></div>';
      document.body.appendChild(fundo);
      fundo.addEventListener('click', function (ev) { if (ev.target === fundo || ev.target.closest('.cab button')) fundo.hidden = true; });
      fundo.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fundo.hidden = true; });
      fundo.querySelector('input').addEventListener('input', function () { preencherMapa(fundo, linhas); });
    }
    fundo.hidden = false;
    fundo.querySelector('input').value = '';
    preencherMapa(fundo, linhas);
    fundo.querySelector('input').focus();
  }
  function preencherMapa(fundo, linhas) {
    var norm = function (s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
    var q = norm(fundo.querySelector('input').value || '');
    var tb = fundo.querySelector('tbody');
    tb.replaceChildren();
    linhas.forEach(function (l) {
      if (q && norm(l[0] + ' ' + l[1]).indexOf(q) < 0) return;
      var tr = document.createElement('tr');
      l.forEach(function (x) { var td = document.createElement('td'); td.textContent = x; tr.appendChild(td); });
      tb.appendChild(tr);
    });
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
    // fora da área de trabalho (a busca Ctrl+K das outras telas carrega este arquivo só pelo mapa dos menus)
    if (!document.getElementById('menus-unicos')) return;
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
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      var tinhaMenu = !!aberto;
      fechar();
      if (tinhaMenu) return;
      var tag = ev.target && ev.target.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      // o foco ficou aqui em cima (um clique num menu, nas vistas, nas setas): o Esc não chegava ao lado aberto
      // e a ferramenta não soltava, "às vezes sim, às vezes não" (01/10) — vai para o lado em uso, que fica com o foco
      try {
        var w = quadro(ladoDasSetas()).contentWindow;
        w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true, cancelable: true }));
        w.focus();
      } catch (e) { /* lado recarregando */ }
    });
    // o clique dentro de um dos lados: fecha o menu e marca o lado das setas de desfazer
    window.addEventListener('blur', function () {
      fechar();
      setTimeout(function () {
        var a = document.activeElement;
        if (a && a.id === 'f2d') ultimoLado = '2d';
        else if (a && a.id === 'f3d') ultimoLado = '3d';
      }, 0);
    });
    ['2d', '3d'].forEach(function (lado) { quadro(lado).addEventListener('mouseenter', function () { ultimoLado = lado; }); });
    iconeDoTema();
    // voltar: a tela anterior; aberta direto (ou vinda dela mesma), a lista de projetos
    var voltar = $('#btn-voltar-area');
    if (voltar) voltar.addEventListener('click', function () {
      // a tela que abriu a área (o histórico do navegador também guarda as trocas de desenho dos quadros:
      // voltar por ele desfaria essas trocas em vez de sair)
      var r = document.referrer || '';
      var daqui = r.indexOf(location.origin) === 0 && !/\/(dividida|2d-3d)(\/|\?|$)/.test(r.slice(location.origin.length));
      location.href = daqui ? r : '/';
    });
    var tema = $('#btn-tema-area');
    if (tema) tema.addEventListener('click', function () { funcao('tema'); });
    window.addEventListener('resize', function () { requestAnimationFrame(compactar); });
    setTimeout(compactar, 800);
  }

  window.barraUnica = {
    vista: function () { fechar(); requestAnimationFrame(compactar); },
    executar: executar,
    mapa: MAPA,
    ondeFoiParar: ondeFoiParar,
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
