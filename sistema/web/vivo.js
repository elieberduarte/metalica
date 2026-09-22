// Sinal de vida das janelas do programa.
//
// No programa instalado não há console nem Ctrl+C: o servidor precisa saber sozinho
// quando a última janela fechou. Vigiar o processo do navegador não serve — se já
// existe um Chrome com o mesmo perfil, o processo que o programa lançou entrega a
// janela ao outro e sai na hora, e o programa se encerraria com a janela aberta.
//
// Então cada página avisa que está aberta a cada poucos segundos e avisa quando fecha.
// O servidor encerra quando nenhuma responde mais. Navegar de uma página a outra manda
// "fechou" e logo em seguida o sinal da página nova; o servidor espera alguns segundos
// antes de concluir que acabou. Fora do programa (servidor de desenvolvimento) estes
// pedidos são ignorados pelo servidor e não custam nada.
(function () {
  'use strict';
  var id = Math.random().toString(36).slice(2) + Date.now().toString(36);
  function sinal() {
    try { fetch('/api/vivo?j=' + id, { cache: 'no-store', keepalive: true }).catch(function () {}); }
    catch (e) { /* servidor fora do ar: nada a fazer */ }
  }
  sinal();
  setInterval(sinal, 5000);
  // aba em segundo plano tem o temporizador freado pelo navegador; ao voltar, avisa já
  document.addEventListener('visibilitychange', function () { if (!document.hidden) sinal(); });
  window.addEventListener('pagehide', function () {
    try { navigator.sendBeacon('/api/fechou?j=' + id); } catch (e) { /* idem */ }
  });
})();
