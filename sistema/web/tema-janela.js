// Barra de título da janela do aplicativo na cor do topo da página (meta theme-color),
// acompanhando o tema claro/escuro: a janela do Chrome em modo aplicativo usa essa cor.
(function () {
  function corDoTopo() {
    const v = getComputedStyle(document.documentElement).getPropertyValue('--topo').trim();
    return v || '#101b2e';
  }
  function aplicar() {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.appendChild(meta); }
    meta.content = corDoTopo();
  }
  const obs = new MutationObserver(aplicar);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', aplicar);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', aplicar); else aplicar();
})();
