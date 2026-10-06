/* Modo desenvolvimento: o botão "Celular" no topo da tela de projetos, que abre o Acesso pelo celular
 * (celular/web.py). Só é carregado com o programa em --dev. */
(function () {
  'use strict';
  function por() {
    var acoes = document.querySelector('.topo .acoes');
    if (!acoes || document.getElementById('btn-celular')) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.id = 'btn-celular';
    b.textContent = 'Celular';
    b.title = 'Acesso pelo celular: consultar os projetos no celular e no tablet pela rede Wi-Fi';
    b.onclick = function () { location.href = '/acesso-celular'; };
    var ajuda = acoes.querySelector('button[onclick*="/ajuda"]');
    acoes.insertBefore(b, ajuda || null);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', por); else por();
})();
