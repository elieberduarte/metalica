/* Modo desenvolvimento: o botão "Painel DEV" no topo da tela de projetos, que abre o painel dos chats do Claude Code
 * (painel_dev/web.py). Só é carregado com o programa em --dev. */
(function () {
  'use strict';
  function por() {
    var acoes = document.querySelector('.topo .acoes');
    if (!acoes || document.getElementById('btn-painel-dev')) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.id = 'btn-painel-dev';
    b.textContent = 'Painel DEV';
    b.title = 'O que cada chat do Claude Code está fazendo: quem trabalha, quem espera você, arquivos em conflito, commits e mensagens entre os chats';
    b.style.cssText = 'background:#1f6feb;color:#fff;border-color:#1f6feb;font-weight:600;padding-left:22px;padding-right:22px';
    b.onclick = function () { location.href = '/painel-dev'; };
    acoes.insertBefore(b, acoes.firstChild);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', por); else por();
})();
