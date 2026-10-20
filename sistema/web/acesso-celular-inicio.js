/* Modo desenvolvimento: o botão "Celular" no topo da tela de projetos, que abre o Acesso pelo celular
 * (celular/web.py), e a chave "Celular" no alto de cada cartão, que liga ou desliga a obra na lista do
 * celular (20/10). Só é carregado com o programa em --dev. */
(function () {
  'use strict';
  var obras = null;                     // slug -> true (no celular) | false (desligada); só as que podem ir

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

  function estilo() {
    if (document.getElementById('estilo-cel-chave')) return;
    var s = document.createElement('style');
    s.id = 'estilo-cel-chave';
    s.textContent =
      '.cel-chave{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:11.5px;padding:2px 8px 2px 4px;' +
      'border-radius:99px;border:1px solid var(--borda);background:var(--painel2);color:var(--texto3);cursor:pointer}' +
      '.cel-chave:hover{border-color:var(--azul2);color:var(--texto)}' +
      '.cel-chave i{position:relative;width:24px;height:13px;border-radius:99px;background:var(--borda-forte,var(--borda));transition:background .12s}' +
      '.cel-chave i::after{content:"";position:absolute;top:2px;left:2px;width:9px;height:9px;border-radius:50%;background:#fff;transition:left .12s}' +
      '.cel-chave[aria-checked="true"]{color:var(--azul);border-color:color-mix(in srgb,var(--azul) 40%,var(--borda))}' +
      '.cel-chave[aria-checked="true"] i{background:var(--azul)}' +
      '.cel-chave[aria-checked="true"] i::after{left:13px}' +
      '.cel-chave:disabled{opacity:.6;cursor:wait}';
    document.head.appendChild(s);
  }

  function pintar(b, ligado) {
    b.setAttribute('aria-checked', ligado ? 'true' : 'false');
    b.lastChild.textContent = ligado ? 'Celular' : 'Fora do celular';
    b.title = ligado
      ? 'Esta obra aparece no celular. Clique para tirá-la da lista do celular (o projeto não muda)'
      : 'Esta obra não aparece no celular. Clique para mostrá-la na lista do celular';
  }

  function chave(slug) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'cel-chave';
    b.setAttribute('role', 'switch');
    b.appendChild(document.createElement('i'));
    b.appendChild(document.createElement('span'));
    pintar(b, obras[slug]);
    b.onclick = function (ev) {
      ev.stopPropagation();                       // o clique no cartão abre o projeto
      var quer = !obras[slug];
      b.disabled = true;
      fetch('/api/celular/obra', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                   body: JSON.stringify({ slug: slug, celular: quer }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || r.status); return j; }); })
        .then(function (j) { obras[slug] = !!j.celular; pintar(b, obras[slug]); })
        .catch(function (e) { alert('Não foi possível mudar a obra no celular: ' + e.message); })
        .then(function () { b.disabled = false; });
    };
    b.onkeydown = function (ev) { ev.stopPropagation(); };
    return b;
  }

  // os cartões são refeitos a cada busca/atualização da lista (inicio.js, desenhar): põe a chave em cada um que não tem
  function chaves() {
    if (!obras) return;
    var cs = document.querySelectorAll('#lista .cartao[data-slug]');
    for (var i = 0; i < cs.length; i++) {
      var slug = cs[i].getAttribute('data-slug');
      var lado = cs[i].querySelector('.cartao-lado');
      if (!lado || !(slug in obras) || lado.querySelector('.cel-chave')) continue;
      lado.insertBefore(chave(slug), lado.firstChild);
    }
  }

  function iniciar() {
    por();
    estilo();
    var lista = document.getElementById('lista');
    if (lista) new MutationObserver(chaves).observe(lista, { childList: true, subtree: true });
    fetch('/api/celular/obras').then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return;
      obras = {};
      (j.obras || []).forEach(function (o) { obras[o.slug] = !!o.celular; });
      chaves();
    }).catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
