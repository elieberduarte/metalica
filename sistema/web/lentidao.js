// Registro de lentidão e de erros das telas, para achar depois o que travou.
//
// O usuário viu o Desenho 2D parar ("Página sem resposta") ao puxar uma cota num desenho de
// 77 mil objetos, e ninguém conseguiu reproduzir. A partir daqui a própria janela conta: o
// navegador avisa cada tarefa que segurou a tela por mais de meio segundo (PerformanceObserver
// de "longtask"), e cada erro de JavaScript; a janela manda isso para o servidor com a tela, a
// ferramenta ativa e o tamanho do desenho, e o servidor grava no metalica.log ("[lento] …").
// Vai por sendBeacon: não segura nada e sai mesmo com a página travando logo depois.
(function () {
  'use strict';
  var ultimo = 0;

  function contexto() {
    var d = { tela: location.pathname + location.search.slice(0, 120), quando: new Date().toISOString().slice(11, 19) };
    try {
      var cad = window.cad, ed = window.editor;
      if (cad) {
        d.ferramenta = (cad.ativa && cad.ativa.constructor && cad.ativa.constructor.id) || (cad.ferramenta && cad.ferramenta.constructor && cad.ferramenta.constructor.id) || '';
        d.objetos = (cad.doc && cad.doc.entidades && cad.doc.entidades.size) || 0;
      } else if (ed) {
        d.ferramenta = (ed.ativa && ed.ativa.constructor && ed.ativa.constructor.id) || '';
        d.objetos = (ed.documento && ed.documento.tamanho) || 0;
      }
    } catch (e) { /* a tela pode não ter esses objetos */ }
    return d;
  }

  // a placa de vídeo que desenha esta página (12/10): no notebook com duas placas, o navegador na integrada ou no
  // desenho por software (SwiftShader) deixa o 3D segundos atrás do mouse — e o registro não dizia qual era
  var placaCache = null;
  function placa() {
    if (placaCache !== null) return placaCache;
    placaCache = '';
    try {
      var c = document.createElement('canvas'), gl = c.getContext('webgl') || c.getContext('experimental-webgl');
      if (!gl) { placaCache = 'sem WebGL'; return placaCache; }
      var x = gl.getExtension('WEBGL_debug_renderer_info');
      placaCache = String(x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)).slice(0, 120);
      var perder = gl.getExtension('WEBGL_lose_context');
      if (perder) perder.loseContext();
    } catch (e) { /* sem como saber */ }
    return placaCache;
  }

  function enviar(dados) {
    var agora = Date.now();
    if (agora - ultimo < 1000 && dados.tipo === 'tarefa longa') return;   // uma por segundo basta
    ultimo = agora;
    var d = contexto();
    for (var k in dados) d[k] = dados[k];
    try {
      var corpo = JSON.stringify(d);
      if (navigator.sendBeacon) navigator.sendBeacon('/api/lento', corpo);
      else fetch('/api/lento', { method: 'POST', body: corpo, keepalive: true }).catch(function () {});
    } catch (e) { /* sem registro, sem drama */ }
  }

  try {
    if ('PerformanceObserver' in window) {
      var po = new PerformanceObserver(function (lista) {
        lista.getEntries().forEach(function (e) {
          if (e.duration < 500) return;
          var atrib = (e.attribution || []).map(function (a) { return a.containerType + (a.containerName ? ':' + a.containerName : ''); }).join(',');
          enviar({ tipo: 'tarefa longa', ms: Math.round(e.duration), atribuicao: (atrib ? atrib + '; ' : '') + 'placa: ' + placa() });
        });
      });
      po.observe({ entryTypes: ['longtask'] });
    }
  } catch (e) { /* navegador sem longtask */ }

  window.addEventListener('error', function (ev) {
    enviar({ tipo: 'erro', mensagem: String(ev.message || '').slice(0, 300), onde: (ev.filename || '') + ':' + (ev.lineno || 0) });
  });
  window.addEventListener('unhandledrejection', function (ev) {
    var r = ev.reason;
    enviar({ tipo: 'erro', mensagem: String((r && (r.message || r)) || '').slice(0, 300), onde: 'promessa' });
  });
  window.__registrarLento = enviar;          // as telas podem registrar uma ação lenta por conta própria
})();
