// Versão que esta janela está rodando, e aviso quando ela fica para trás.
//
// Cada janela guarda o código JavaScript que carregou. Depois de uma atualização, a
// janela que o instalador reabre está na versão nova, mas qualquer outra que já estava
// aberta continua com o código antigo até ser recarregada — e é aí que o usuário vê
// comportamentos diferentes em duas janelas do mesmo programa.
//
// Então: a versão do servidor no momento em que a página carregou é a versão do código
// desta janela, e fica escrita no rodapé. De minuto em minuto a página pergunta de novo;
// se o servidor passou a responder outra versão, o programa foi atualizado por baixo e a
// janela avisa, em amarelo, que precisa ser recarregada (um clique recarrega).
//
// O rótulo entra no elemento `#versao-programa`, quando a página tem um; sem ele, num
// cantinho fixo embaixo à direita. Fora do programa (servidor de desenvolvimento) a rota
// responde igual, então isto vale também no navegador comum.
(function () {
  'use strict';
  var minha = null;                 // versão do código desta janela
  var alvo = null;
  var avisada = false;

  function elemento() {
    if (alvo && alvo.isConnected) return alvo;
    alvo = document.getElementById('versao-programa');
    if (!alvo) {
      alvo = document.createElement('span');
      alvo.id = 'versao-programa';
      alvo.style.cssText = 'position:fixed;right:8px;bottom:6px;z-index:60;font:11px/1.4 ' +
        'ui-monospace,Consolas,monospace;color:var(--texto3,#8a94a6);opacity:.85;' +
        'padding:1px 6px;border-radius:5px;pointer-events:auto';
      document.body.appendChild(alvo);
    }
    return alvo;
  }

  function mostrar(nova) {
    var e = elemento();
    if (!nova || nova === minha) {
      e.textContent = 'v' + minha;
      e.title = 'Versão do programa nesta janela';
      e.style.cursor = '';
      e.removeAttribute('data-desatualizada');
      return;
    }
    // O servidor já está noutra versão: o código desta janela é o antigo.
    e.textContent = 'v' + minha + ' → recarregar para v' + nova;
    e.title = 'O programa foi atualizado para ' + nova + ' enquanto esta janela estava aberta. ' +
              'Clique (ou Ctrl+R) para recarregar e usar a versão nova.';
    e.style.cursor = 'pointer';
    e.style.color = '#e9bb23';
    e.style.background = 'rgba(233,187,35,.12)';
    e.dataset.desatualizada = '1';
    e.onclick = function () { location.reload(); };
    if (!avisada) {
      avisada = true;
      try {
        if (window.editor && window.editor.aviso) {
          window.editor.aviso('O programa foi atualizado para ' + nova + '; esta janela ainda está na ' +
                              minha + '. Recarregue (Ctrl+R) para usar a versão nova.', 'atencao', 0);
        } else if (window.cad && window.cad.aviso) {
          window.cad.aviso('O programa foi atualizado para ' + nova + '; recarregue esta janela (Ctrl+R).', 'atencao', 0);
        }
      } catch (err) { /* a página pode não ter caixa de avisos */ }
    }
  }

  function perguntar() {
    fetch('/api/versao', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (v) {
        if (!v || !v.versao) return;
        if (minha === null) { minha = v.versao; window.__versaoPrograma = minha; }
        mostrar(v.versao);
      })
      .catch(function () { /* servidor ocupado: pergunta de novo no próximo minuto */ });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', perguntar);
  else perguntar();
  setInterval(perguntar, 60000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) perguntar(); });
})();
