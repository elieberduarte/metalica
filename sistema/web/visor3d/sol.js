// O sol do modo apresentação (20/10, usuário: "uma opção para o usuário conseguir mudar a posição do sol, tanto no mobile
// quanto no computador"): a direção em volta da obra (0–360°, nos eixos do modelo — o norte do projeto não é conhecido)
// e a altura acima do horizonte. O visor lê a direção do sol a cada sombra que desenha (visor3d.js, ligarApresentacao).

/** O sol de saída: alto (57°), da esquerda e um pouco da frente da vista inicial (o mesmo de antes de haver a escolha). */
export const SOL_PADRAO = { direcao: 255, altura: 57 };
export const ALTURA_MIN = 5, ALTURA_MAX = 85;

/** Põe o sol na `direcao` e na `altura` (graus) e redesenha a sombra. Só depois de o modelo abrir. */
export function definirSol(visor, { direcao, altura }) {
  if (!visor || !visor._luz) return;
  const a = (+direcao || 0) * Math.PI / 180;
  const e = Math.min(Math.max(+altura || SOL_PADRAO.altura, ALTURA_MIN), ALTURA_MAX) * Math.PI / 180;
  visor._luz.uSol.value.set(Math.cos(e) * Math.cos(a), Math.cos(e) * Math.sin(a), Math.sin(e));
  visor._sombraSuja = true;
  visor.pedirQuadro();
}

/** O sol guardado (direção e altura), ou o padrão. */
export function lerSol(chave) {
  try {
    const s = JSON.parse(localStorage.getItem(chave) || 'null');
    if (s && Number.isFinite(+s.direcao) && Number.isFinite(+s.altura)) return { direcao: +s.direcao, altura: +s.altura };
  } catch (e) { /* sem armazenamento */ }
  return { ...SOL_PADRAO };
}

export function gravarSol(chave, sol) {
  try { localStorage.setItem(chave, JSON.stringify(sol)); } catch (e) { /* sem armazenamento: vale até fechar */ }
}

/** Os dois controles (direção e altura) e o Padrão, em HTML; `ligar(raiz, aoMudar)` os põe para funcionar. */
export function controlesDoSol(sol) {
  return `<div class="sol-controles">
    <label>Direção <output data-sol-saida="direcao">${Math.round(sol.direcao)}°</output>
      <input type="range" min="0" max="360" step="1" value="${Math.round(sol.direcao)}" data-sol="direcao" aria-label="Direção do sol"></label>
    <label>Altura <output data-sol-saida="altura">${Math.round(sol.altura)}°</output>
      <input type="range" min="${ALTURA_MIN}" max="${ALTURA_MAX}" step="1" value="${Math.round(sol.altura)}" data-sol="altura" aria-label="Altura do sol"></label>
    <button type="button" data-sol-padrao>Sol padrão</button></div>`;
}

export function ligarControlesDoSol(raiz, sol, aoMudar) {
  const atual = { ...sol };
  const mostrar = () => {
    for (const k of ['direcao', 'altura']) {
      const ent = raiz.querySelector(`[data-sol="${k}"]`), sai = raiz.querySelector(`[data-sol-saida="${k}"]`);
      if (ent) ent.value = Math.round(atual[k]);
      if (sai) sai.textContent = Math.round(atual[k]) + '°';
    }
  };
  raiz.querySelectorAll('[data-sol]').forEach(ent => {
    ent.oninput = () => { atual[ent.dataset.sol] = +ent.value; mostrar(); aoMudar({ ...atual }); };
  });
  const p = raiz.querySelector('[data-sol-padrao]');
  if (p) p.onclick = () => { Object.assign(atual, SOL_PADRAO); mostrar(); aoMudar({ ...atual }); };
}
