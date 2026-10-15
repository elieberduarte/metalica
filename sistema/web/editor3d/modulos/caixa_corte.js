// Caixa de corte (o "Section Box" do Revit, 14/10): o 3D mostra só a região em volta da seleção — no PRATI CD, com 27 mil
// peças, a ligação de um nó fica à vista sem a cobertura e as fachadas na frente. A cena corta pelos seis planos
// (cena.definirCaixaCorte); a peça inteira fora da caixa sai também da seleção e do snap (documento.foraDaCaixa, conferido
// em documento.aparece). É estado da vista: não entra no Ctrl+Z nem no modelo gravado.

import { pontosDe } from '../nucleo/documento.js';

export const FOLGA = 300;           // mm em volta da seleção (a seção da barra fica fora dos pontos do eixo)

/** A caixa [min, max] dos pontos das peças `ids`, com `folga` mm para cada lado. */
export function caixaDasPecas(doc, ids, folga = FOLGA) {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const id of ids) {
    const e = doc.get(id);
    if (!e) continue;
    for (const p of pontosDe(e)) for (let i = 0; i < 3; i++) { if (p[i] < lo[i]) lo[i] = p[i]; if (p[i] > hi[i]) hi[i] = p[i]; }
  }
  if (!isFinite(lo[0])) return null;
  return [lo.map(v => v - folga), hi.map(v => v + folga)];
}

/** Liga a caixa de corte `caixa` ([min, max] em mm) ou desliga (null). */
export function definirCaixaDeCorte(editor, caixa) {
  const doc = editor.documento, cena = editor.cena;
  if (!caixa) {
    doc.foraDaCaixa = null;
    if (typeof cena.definirCaixaCorte === 'function') cena.definirCaixaCorte(null);
    doc.notificarAparencia();
    return 0;
  }
  // a peça cujos pontos (o eixo da barra, os cantos da chapa, os vértices do sólido) ficam todos do mesmo lado de fora de
  // um dos planos não aparece; a que cruza a caixa aparece cortada
  const [lo, hi] = caixa;
  const fora = new Set();
  for (const [id, e] of doc.entidades) {
    const pts = pontosDe(e);
    if (!pts.length) continue;
    let longe = false;
    for (let i = 0; i < 3 && !longe; i++) {
      if (pts.every(p => p[i] < lo[i] - FOLGA) || pts.every(p => p[i] > hi[i] + FOLGA)) longe = true;
    }
    if (longe) fora.add(id);
  }
  doc.foraDaCaixa = fora.size ? fora : null;
  if (typeof cena.definirCaixaCorte === 'function') cena.definirCaixaCorte(caixa);
  // o que estava selecionado e ficou fora sai da seleção
  const sel = editor.selecao;
  if (fora.size && sel && sel.ids && [...sel.ids].some(i => fora.has(i))) sel.definir([...sel.ids].filter(i => !fora.has(i)));
  doc.notificarAparencia();
  return fora.size;
}

/** A caixa de corte em volta da seleção, e a câmera nela. */
export function caixaNaSelecao(editor) {
  const ids = [...editor.selecao.ids];
  const caixa = caixaDasPecas(editor.documento, ids);
  if (!caixa) { editor.dica('Selecione as peças em volta das quais cortar'); return null; }
  const fora = definirCaixaDeCorte(editor, caixa);
  editor.camera.zoomSelecao(ids);
  const t = caixa[1].map((v, i) => Math.round(v - caixa[0][i]));
  editor.dica(`Caixa de corte ${t.join(' × ')} mm (${fora} peça(s) fora) — botão direito: "Tirar a caixa de corte"`);
  return caixa;
}
