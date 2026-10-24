// Localizar e substituir (o FIND do AutoCAD; 24/10, a lista das ferramentas que faltam): Editar › Localizar e
// substituir… (Ctrl+H, ou FIND na linha de comando). Procura nos textos, nas chamadas e no texto escrito das cotas;
// a lista leva a cada um (zoom e seleção); "Substituir todos" troca num passo só do Ctrl+Z. As camadas travadas e a
// peça gerada do 3D seguem a trava de sempre (os textos são livres).

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

import { ComandoAlterar } from './nucleo/comandos.js';

const TIPOS_COM_TEXTO = new Set(['texto', 'chamada', 'cota', 'cota_especial']);
const escapar = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** A expressão da busca: o texto literal, com ou sem diferença de maiúsculas, e a palavra inteira. null se vazio. */
export function expressaoDaBusca(busca, { maiusculas = false, palavra = false } = {}) {
  if (!busca) return null;
  const corpo = escapar(busca);
  return new RegExp(palavra ? `(?<![\\p{L}\\p{N}_])${corpo}(?![\\p{L}\\p{N}_])` : corpo, maiusculas ? 'gu' : 'giu');
}

/** As entidades do documento que têm o texto (as visíveis): [{e, n (quantas vezes)}]. */
export function localizar(doc, re) {
  const out = [];
  if (!re) return out;
  for (const e of doc.entidades.values()) {
    if (!TIPOS_COM_TEXTO.has(e.tipo) || e.texto == null || !doc.visivel(e)) continue;
    const n = (String(e.texto).match(re) || []).length;
    if (n) out.push({ e, n });
  }
  return out;
}

export class MetodosLocalizarCAD {
  async dialogoLocalizar() {
    const sel = [...this.tela.selecao].map(id => this.doc.get(id)).find(e => e && e.tipo === 'texto');
    const busca = el('input', { type: 'text', 'data-campo': 'busca', value: sel ? String(sel.texto).split('\n')[0] : '', style: 'width:100%' });
    const troca = el('input', { type: 'text', 'data-campo': 'troca', style: 'width:100%' });
    const mai = el('input', { type: 'checkbox', 'data-campo': 'maiusculas' });
    const pal = el('input', { type: 'checkbox', 'data-campo': 'palavra' });
    const res = el('div', { class: 'lista-opcoes', 'data-campo': 'resultados', style: 'max-height:32vh;overflow:auto;min-height:3em' });
    const opcoes = () => ({ maiusculas: mai.checked, palavra: pal.checked });
    let achados = [];
    const atualizar = () => {
      achados = localizar(this.doc, expressaoDaBusca(busca.value, opcoes()));
      const total = achados.reduce((s, a) => s + a.n, 0);
      res.replaceChildren(el('div', { class: 'explica', texto: busca.value ? `${total} ocorrência(s) em ${achados.length} objeto(s)` : 'Escreva o que procurar.' }),
        ...achados.slice(0, 200).map(({ e }) => el('button', { type: 'button', class: 'linha', style: 'display:block;width:100%;text-align:left', 'data-id': e.id,
          title: 'Mostrar e selecionar', onclick: () => this._mostrarAchado(e) }, `${e.tipo === 'texto' ? 'Texto' : e.tipo === 'chamada' ? 'Chamada' : 'Cota'}: ${String(e.texto).replace(/\n/g, ' ⏎ ').slice(0, 90)}`)));
    };
    for (const c of [busca, mai, pal]) c.addEventListener('input', atualizar);
    for (const c of [mai, pal]) c.addEventListener('change', atualizar);
    const corpo = el('div', { style: 'min-width:460px' },
      el('label', {}, 'Localizar ', busca),
      el('label', {}, 'Substituir por ', troca),
      el('div', { style: 'display:flex;gap:14px;margin:6px 0' }, el('label', {}, mai, ' Maiúsculas e minúsculas'), el('label', {}, pal, ' Palavra inteira')),
      el('div', { style: 'display:flex;gap:6px;margin:6px 0' },
        el('button', { type: 'button', 'data-acao-local': 'selecionar', onclick: () => { this.selecionar(achados.map(a => a.e.id)); this.dica(`${achados.length} objeto(s) selecionado(s)`); } }, 'Selecionar todos')),
      res);
    atualizar();
    if (await this.dialogo({ titulo: 'Localizar e substituir', corpo, ok: 'Substituir todos' }) !== 'ok') return;
    this.substituirTextos(busca.value, troca.value, opcoes());
  }

  /** Troca o texto em todos os achados, num passo só do Ctrl+Z. Devolve {objetos, ocorrencias}. */
  substituirTextos(busca, novo, opcoes = {}) {
    const re = expressaoDaBusca(busca, opcoes);
    const achados = localizar(this.doc, re);
    if (!achados.length) { this.aviso(`"${busca}" não aparece no desenho.`, 'atencao'); return { objetos: 0, ocorrencias: 0 }; }
    const mud = {};
    let n = 0;
    for (const { e, n: k } of achados) { mud[e.id] = { texto: String(e.texto).replace(re, () => novo) }; n += k; }
    this.executar(new ComandoAlterar(mud, `Substituir "${busca}"`));
    // o que a trava deixou de fora (camada travada) não mudou
    const feitos = Object.keys(mud).filter(id => { const e = this.doc.get(id); return e && e.texto === mud[id].texto; }).length;
    this.aviso(`${n} ocorrência(s) de "${busca}" trocada(s) por "${novo}" em ${feitos} objeto(s)${feitos < achados.length ? ` (${achados.length - feitos} em camada travada ficaram)` : ''}. Ctrl+Z desfaz.`, 'info', 9000);
    return { objetos: feitos, ocorrencias: n };
  }

  _mostrarAchado(e) {
    const c = this.doc.caixaDa(e);
    if (c) {
      const m = Math.max(c[1][0] - c[0][0], c[1][1] - c[0][1], 50 * (this.doc.escala || 1));
      this.tela.enquadrar([[c[0][0] - m, c[0][1] - m], [c[1][0] + m, c[1][1] + m]]);
    }
    this.selecionar([e.id]);
  }
}
