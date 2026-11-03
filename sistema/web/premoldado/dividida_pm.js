/* A área de trabalho (/dividida) no modo dev: a barra única ganha os itens do lançamento da estrutura (os
 * mesmos da barra da direita do 2D) no menu Estrutura e, no Ver, as armaduras dos pilares do pré-moldado.
 * Roda logo depois de /barra_unica.js e antes de ela montar os menus (DOMContentLoaded): só acrescenta ao
 * mapa exposto em window.barraUnica.mapa — a barra da Metálica não muda. */
(function () {
  'use strict';
  var B = window.barraUnica;
  if (!B || !B.mapa) return;
  function I(texto, lado, acao, extra) { var o = { texto: texto, lado: lado, acao: acao }; for (var k in extra || {}) o[k] = extra[k]; return o; }
  function menu(nome) { for (var i = 0; i < B.mapa.length; i++) if (B.mapa[i].nome === nome) return B.mapa[i]; return null; }

  // o menu do modelo (era "Estrutura"; "Modelo" desde a faixa única, UI1): os elementos da planta num submenu no começo
  var est = menu('Modelo') || menu('Estrutura');
  if (est) {
    var elementos = [
      I('Pilar', '2d', 'estr-pilar'),
      I('Viga', '2d', 'estr-viga'),
      I('Consolo', '2d', 'estr-consolo'),
      I('Fundação', '2d', 'estr-fundacao'),
      I('Tesoura de concreto', '2d', 'estr-tesoura'),
      I('Placa de fechamento', '2d', 'estr-painel'),
      I('Laje', '2d', 'estr-laje'),
      I('Escada', '2d', 'estr-escada'),
      I('Chapa', '2d', 'estr-chapa'),
      I('Furo', '2d', 'estr-furo'),
      I('Parafuso', '2d', 'estr-parafuso'),
      '---',
      I('Tesoura de aço pelo desenho…', '2d', 'estr-trelica', { dica: 'selecione a tesoura em linhas e lance de eixo a eixo' }),
      '---',
      I('Níveis do projeto…', '2d', 'estr-niveis'),
      I('Arrumar os nomes dos elementos', '2d', 'estr-rotulos', { dica: 'um rótulo por elemento, com a marca dele' }),
      I('Renumerar os elementos em ordem', '2d', 'estr-renumerar', { dica: 'P1, P2… de cima para baixo, da esquerda para a direita' }),
      I('Gerar 3D da planta…', '2d', 'estr-gerar-3d'),
      I('Atualizar a planta pelo 3D', '2d', 'estr-do-3d'),
    ];
    // sem o submenu (a barra antiga), os itens soltos com um título
    // o submenu da barra da Metálica com os mesmos comandos ("Lançar na planta (Estrutura)") sai: um só, este (06/10)
    for (var j = est.itens.length - 1; j >= 0; j--) if (est.itens[j] && est.itens[j].sub && /^Lançar na planta/.test(est.itens[j].texto || '')) est.itens.splice(j, 1);
    var comSub = typeof B.executar === 'function' && est.itens.some(function (i) { return i && i.sub; });
    if (comSub || est.nome === 'Modelo') {
      est.itens.unshift({ texto: 'Lançar os elementos na planta', sub: elementos },
        I('Configuração do galpão pré-moldado…', '2d', 'pm-configuracao'), '---');
    } else {
      est.itens.unshift.apply(est.itens, [{ titulo: 'Lançar os elementos na planta' }].concat(elementos,
        [I('Configuração do galpão pré-moldado…', '2d', 'pm-configuracao'), '---']));
    }
  }
  var ver = menu('Ver');
  if (ver) {
    var k = 0;
    for (var i = 0; i < ver.itens.length; i++) if (ver.itens[i] && ver.itens[i].acao === 'referencia') { k = i + 1; break; }
    ver.itens.splice(k, 0, I('Armaduras (pré-moldado)', '3d', 'pm-armaduras'), I('Níveis do projeto…', '3d', 'pm-niveis'));
  }
})();
