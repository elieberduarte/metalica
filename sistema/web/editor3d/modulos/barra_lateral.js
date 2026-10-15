// A barra lateral das ferramentas em janela baixa (15/10, item 4 do briefing do editor 3D): as últimas ferramentas
// ficavam escondidas e a barra rolava sem mostrar que rolava.
//
// Em vez de rolar, a barra se ajeita, nesta ordem, até caber tudo:
//   1. compacta: botões mais baixos e os nomes dos grupos viram só um traço;
//   2. duas colunas (como a bandeja grande do SketchUp), com os grupos inteiros em linhas de dois;
//   3. se nem assim couber (a janela muito baixa), setas em cima e embaixo mostram que há mais e rolam a barra.
// Refaz a conta quando a janela (ou a área da tela dividida) muda de tamanho e quando a barra é remontada.

const CLASSES = ['barra-compacta', 'barra-duas-colunas'];

export function ligarBarraLateral(editor) {
  const barra = (editor.el && editor.el.barra) || document.getElementById('barra-ferramentas');
  if (!barra) return null;
  estilo();
  const seta = (lado) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `barra-seta barra-seta-${lado}`;
    b.hidden = true;
    b.title = lado === 'cima' ? 'Há mais ferramentas acima' : 'Há mais ferramentas abaixo';
    b.setAttribute('aria-label', b.title);
    b.textContent = lado === 'cima' ? '▲' : '▼';
    b.addEventListener('click', () => barra.scrollBy({ top: (lado === 'cima' ? -1 : 1) * barra.clientHeight * 0.6, behavior: 'smooth' }));
    document.body.append(b);
    return b;
  };
  const cima = seta('cima'), baixo = seta('baixo');
  const sobra = () => barra.scrollHeight - barra.clientHeight > 1;

  const setas = () => {
    const rola = sobra() && barra.offsetParent !== null;
    const r = barra.getBoundingClientRect();
    for (const b of [cima, baixo]) {
      b.style.left = `${r.left}px`;
      b.style.width = `${r.width}px`;
    }
    cima.style.top = `${r.top}px`;
    baixo.style.top = `${r.bottom - 18}px`;
    cima.hidden = !rola || barra.scrollTop <= 1;
    baixo.hidden = !rola || barra.scrollTop + barra.clientHeight >= barra.scrollHeight - 1;
  };

  let medindo = false;
  const ajustar = () => {
    if (medindo || !barra.children.length) return;
    medindo = true;
    try {
      barra.classList.remove(...CLASSES);
      // o modo vale enquanto a barra está à vista (escondida pela faixa de cima, tudo mede zero)
      if (barra.offsetParent !== null && sobra()) {
        barra.classList.add('barra-compacta');
        if (sobra()) {
          barra.classList.remove('barra-compacta');
          barra.classList.add('barra-duas-colunas');
          if (sobra()) barra.classList.add('barra-compacta');
        }
      }
      barra.dataset.modo = barra.classList.contains('barra-duas-colunas')
        ? (barra.classList.contains('barra-compacta') ? 'duas-colunas-compacta' : 'duas-colunas')
        : (barra.classList.contains('barra-compacta') ? 'compacta' : 'normal');
      setas();
    } finally { medindo = false; }
  };

  let agendado = 0;
  const agendar = () => {
    if (agendado) return;
    agendado = requestAnimationFrame(() => { agendado = 0; ajustar(); });
  };
  barra.addEventListener('scroll', setas, { passive: true });
  window.addEventListener('resize', agendar);
  // a área (a tela dividida, os painéis que abrem e fecham) muda a altura sem mudar a janela
  if (typeof ResizeObserver === 'function' && barra.parentElement) new ResizeObserver(agendar).observe(barra.parentElement);
  // a barra é montada depois que as ferramentas carregam
  new MutationObserver(agendar).observe(barra, { childList: true });
  agendar();
  editor.ajustarBarraLateral = ajustar;
  return { ajustar };
}

function estilo() {
  if (document.getElementById('barra-lateral-css')) return;
  const s = document.createElement('style');
  s.id = 'barra-lateral-css';
  s.textContent = `
.ferramentas.barra-compacta { gap: 0; padding: 3px 0; }
.ferramentas.barra-compacta .ferramenta { height: 28px; }
.ferramentas.barra-compacta .ferramenta svg { width: 19px; height: 19px; }
.ferramentas.barra-compacta .grupo-rotulo { font-size: 0; padding: 0; margin: 3px 8px; height: 0; border-top: 1px solid var(--borda); }
.ferramentas.barra-compacta .grupo-rotulo:first-child { border-top: 0; margin: 0; }
.ferramentas.barra-duas-colunas { width: 84px; flex: 0 0 84px; display: grid; grid-template-columns: 38px 38px;
  justify-content: center; align-content: start; gap: 1px 2px; }
.ferramentas.barra-duas-colunas .grupo-rotulo { grid-column: 1 / -1; }
.ferramentas.barra-duas-colunas .ferramenta { margin: 0; }
.barra-seta { position: fixed; z-index: 55; height: 18px; padding: 0; border: 0; cursor: pointer; font-size: 9px; line-height: 18px;
  color: var(--texto2, #555); background: linear-gradient(var(--painel, #fff) 55%, transparent); }
.barra-seta-baixo { background: linear-gradient(transparent, var(--painel, #fff) 45%); }
.barra-seta:hover { color: var(--azul, #1f6fd6); }
`;
  document.head.append(s);
}
