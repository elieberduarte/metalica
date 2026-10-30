/* Módulo de arquitetura (em desenvolvimento, só no modo dev): a área "Arquitetura" na tela de projetos, ao lado da
 * Metálica e do Pré-moldado (o menu da marca é o do web/premoldado/dev_inicio.js, que lê window.AREAS_INICIO_EXTRA).
 * Carregado antes dele pelo app.py. */
(function () {
  'use strict';
  /* global perguntar, postar, carregando, recado, CAMPOS_PROJETO */
  var ICONE = '<path d="M5 27V12l11-6 11 6v15H5z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>' +
              '<path d="M9 27v-8h6v8M19 15h5v5h-5z" fill="none" stroke="currentColor" stroke-width="1.3" opacity=".7"/>';

  async function novoProjeto() {
    var v = await perguntar({ titulo: 'Novo projeto de arquitetura',
      texto: 'Cria o projeto com os níveis padrão (térreo, superior e cobertura) e abre o 3D. As ferramentas de desenhar ' +
             'paredes, portas e janelas no editor são a próxima etapa do módulo: por enquanto ele monta a casa piloto.',
      campos: CAMPOS_PROJETO, ok: 'Criar e abrir' });
    if (!v) return;
    try {
      carregando(true, 'Criando o projeto…');
      var p = await postar('/api/projetos', Object.assign({}, v, { tipo: 'arquitetura', area: 'arquitetura' }));
      location.href = '/dividida?projeto=' + encodeURIComponent(p.slug) + '&vista=3d';
    } catch (e) { carregando(false); recado('Não foi possível criar o projeto', e.message, 'erro'); }
  }

  async function casaPiloto() {
    try {
      carregando(true, 'Montando a casa piloto: paredes, esquadrias, lajes e ambientes…');
      var p = await postar('/api/arquitetura/piloto', {});
      location.href = '/dividida?projeto=' + encodeURIComponent(p.slug) + '&vista=3d';
    } catch (e) { carregando(false); recado('Não foi possível montar a casa piloto', e.message, 'erro'); }
  }

  window.AREAS_INICIO_EXTRA = (window.AREAS_INICIO_EXTRA || []).concat([{
    chave: 'arquitetura', tipo: 'arquitetura', nome: 'Arquitetura', sub: 'Projetos arquitetônicos', dev: true,
    titulo: 'Arquitetura — projetos', icone: ICONE,
    vazio: 'nenhum projeto de arquitetura ainda — comece pela "Casa piloto (demonstração)"',
    novos: [
      ['btn-arq-piloto', 'Casa piloto (demonstração)', 'Monta (ou remonta) a casa alto padrão com paredes, portas, janelas, lajes e ambientes pelo motor da arquitetura', casaPiloto],
      ['btn-arq-novo', 'Novo projeto de arquitetura', 'Cria um projeto de arquitetura vazio, com os níveis padrão', novoProjeto, 'principal'],
    ],
    url: function (p) { return '/dividida?projeto=' + encodeURIComponent(p.slug) + '&vista=3d'; },
  }]);
})();
