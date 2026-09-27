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
  var codigoMeu = null;             // desenvolvimento: carimbo do código de tela que esta janela carregou
  var faixa = null;

  // Modo de desenvolvimento: uma faixa laranja no alto da janela e "[DEV]" no título, para
  // não confundir com o programa instalado; e quando o código de tela muda no disco, o
  // rótulo da versão pede para recarregar (F5).
  function marcarDev(v) {
    if (!faixa) {
      faixa = document.createElement('div');
      faixa.id = 'faixa-dev';
      faixa.title = 'Metálica em DESENVOLVIMENTO — rodando do código, porta ' + location.port +
                    '. O programa instalado é outro; não abra o mesmo projeto nos dois.';
      faixa.style.cssText = 'position:fixed;left:0;top:0;right:0;height:4px;z-index:99999;' +
        'background:repeating-linear-gradient(90deg,#f0a050 0 14px,#c0392b 14px 28px);pointer-events:none';
      document.body.appendChild(faixa);
      if (document.title.indexOf('[DEV]') !== 0) document.title = '[DEV] ' + document.title;
    }
    if (codigoMeu === null) codigoMeu = v.codigo;
    mostrarConferencia(v.conferencia);
    var e = elemento();
    if (v.codigo && codigoMeu && v.codigo !== codigoMeu) {
      e.textContent = 'v' + minha + ' dev · código novo — recarregar (F5)';
      e.title = 'Os arquivos de tela mudaram no disco depois que esta janela carregou. Clique (ou F5) para ver a versão nova.';
      e.style.cursor = 'pointer';
      e.style.color = '#f0a050';
      e.style.background = 'rgba(240,160,80,.14)';
      e.onclick = function () { location.reload(); };
      return true;
    }
    e.textContent = 'v' + minha + ' dev';
    e.title = 'DESENVOLVIMENTO: rodando do código (porta ' + location.port + ')';
    e.style.color = '#f0a050';
    e.style.cursor = '';
    e.onclick = null;
    return true;
  }

  // Modo de desenvolvimento: a conferência antes de publicar rodando (testes, verificadores das
  // telas, bateria das obras) numa caixinha embaixo à direita, com a barra, a etapa e quanto
  // falta. Só na janela de cima (a área de trabalho tem o 2D e o 3D em quadros: não repete).
  var caixaConf = null;
  function minutos(s) {
    if (s < 60) return 'menos de 1 min';
    return '~' + Math.round(s / 60) + ' min';
  }
  function mostrarConferencia(c) {
    try { if (window.top !== window) return; } catch (err) { return; }
    if (!c) { if (caixaConf) { caixaConf.remove(); caixaConf = null; } return; }
    if (!caixaConf) {
      caixaConf = document.createElement('div');
      caixaConf.id = 'conferencia-dev';
      caixaConf.style.cssText = 'position:fixed;right:8px;bottom:30px;z-index:99998;width:290px;padding:6px 9px 7px;' +
        'border-radius:7px;font:11px/1.45 system-ui,Segoe UI,sans-serif;color:var(--texto,#e4eaf3);' +
        'background:var(--painel,#1b2230);border:1px solid var(--borda,#33405a);box-shadow:0 4px 14px rgba(0,0,0,.28);' +
        'pointer-events:none;opacity:.96';
      caixaConf.innerHTML = '<div data-l1 style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>' +
        '<div data-l2 style="color:var(--texto3,#8a94a6);white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>' +
        '<div style="margin-top:5px;height:5px;border-radius:3px;background:rgba(128,140,160,.25);overflow:hidden">' +
        '<div data-barra style="height:100%;width:0;border-radius:3px;transition:width .6s"></div></div>';
      document.body.appendChild(caixaConf);
    }
    var cor = c.fim ? (c.ok ? '#3fae6a' : '#d9534f') : (c.parada ? '#8a94a6' : '#f0a050');
    var l1, l2;
    if (c.fim) {
      l1 = c.ok ? 'Conferência concluída: tudo ok' : 'Conferência terminou com falha';
      l2 = (c.falhas && c.falhas.length ? 'falhou: ' + c.falhas.join(', ') + ' · ' : '') + 'em ' + minutos(c.decorrido_s).replace('~', '');
    } else if (c.parada) {
      l1 = 'Conferência parada (sem notícia há 20 min)';
      l2 = c.etapa;
    } else {
      l1 = 'Conferência ' + Math.round(c.pct) + '% · falta ' + minutos(c.resta_s);
      l2 = c.n_etapa + '/' + c.etapas + ' ' + c.etapa + (c.total ? ' ' + c.feito + '/' + c.total : '') + (c.texto ? ' · ' + c.texto : '');
    }
    caixaConf.querySelector('[data-l1]').textContent = l1;
    caixaConf.querySelector('[data-l2]').textContent = l2;
    var b = caixaConf.querySelector('[data-barra]');
    b.style.width = Math.max(2, Math.min(100, c.pct)) + '%';
    b.style.background = cor;
    caixaConf.title = l1 + ' — ' + l2;
  }

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
        if (v.dev) { window.__dev = true; marcarDev(v); return; }
        mostrar(v.versao);
      })
      .catch(function () { /* servidor ocupado: pergunta de novo no próximo minuto */ });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', perguntar);
  else perguntar();
  setInterval(perguntar, 60000);
  // no desenvolvimento, o carimbo do código muda a cada edição: pergunta mais vezes
  setInterval(function () { if (window.__dev) perguntar(); }, 4000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) perguntar(); });
})();
