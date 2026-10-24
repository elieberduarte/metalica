// Revisões das pranchas (usuário, 24/10: a opção A — a tabela inteira em cima do carimbo, a mais nova em cima; "Nova
// revisão" pelo diálogo, marcando as pranchas que mudaram). Arquivo › Revisões das pranchas… (ou REVISOES na linha de
// comando). O servidor (nucleo2d/revisoes.py, rota revisoes-pranchas) numera cada prancha, grava no projeto e põe a
// tabela nos desenhos das pranchas sem remontar; a montagem seguinte a desenha pelo carimbo.

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

async function chamar(rota, corpo) {
  let r;
  try {
    r = await fetch(rota, corpo === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  } catch { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}

const dois = (n) => String(n).padStart(2, '0');

export class MetodosRevisoesCAD {
  async dialogoRevisoes() {
    if (!this.projeto) { this.aviso('Abra um projeto para lançar as revisões das pranchas.', 'atencao'); return; }
    const rota = `/api/projetos/${encodeURIComponent(this.projeto)}/revisoes-pranchas`;
    let dados;
    try { dados = await chamar(rota); } catch (e) { this.aviso('Revisões das pranchas: ' + e.message, 'erro', 0); return; }
    if (!dados.pranchas.length) { this.aviso('O projeto ainda não tem pranchas: monte as pranchas primeiro (Desenho › Montar pranchas).', 'atencao'); return; }
    const revs = JSON.parse(JSON.stringify(dados.revisoes || {}));
    const desc = el('input', { type: 'text', 'data-campo': 'descricao', placeholder: 'o que mudou (ex.: terças Ue 200 no lugar das Ue 150)', style: 'width:100%' });
    const data = el('input', { type: 'text', 'data-campo': 'data', value: dados.hoje, style: 'width:96px' });
    const por = el('input', { type: 'text', 'data-campo': 'por', value: dados.por, style: 'width:110px' });
    const marcas = new Map();
    const lista = el('div', { class: 'lista-opcoes', style: 'max-height:26vh;overflow:auto' });
    for (const p of dados.pranchas) {
      if (marcas.has(p.numero)) continue;
      const c = el('input', { type: 'checkbox', 'data-prancha': p.numero });
      marcas.set(p.numero, c);
      const ult = (revs[String(p.numero)] || []).slice(-1)[0];
      lista.append(el('label', { class: 'linha' }, c, ` ${dois(p.numero)} ${p.titulo || ''}`, el('small', { texto: `  REV. ${ult ? ult.rev : '00'}` })));
    }
    const marcar = (v) => { for (const c of marcas.values()) c.checked = v; };
    // as revisões já lançadas, editáveis (a data da emissão inicial, um erro de digitação, uma linha a tirar)
    const feitas = el('div', { style: 'max-height:24vh;overflow:auto' });
    const ordem = Object.keys(revs).sort((a, b) => +a - +b);
    for (const n of ordem) {
      const linhas = revs[n];
      feitas.append(el('div', { class: 'explica', style: 'margin-top:6px', texto: `Prancha ${dois(n)}` }));
      for (const ln of linhas) {
        const campo = (k, w) => { const i = el('input', { type: 'text', value: ln[k] || '', style: `width:${w}` }); i.addEventListener('input', () => { ln[k] = i.value; }); return i; };
        const fila = el('div', { style: 'display:flex;gap:4px;margin:2px 0' });
        const tirar = el('button', { type: 'button', title: 'Tirar esta linha da tabela', onclick: () => { linhas.splice(linhas.indexOf(ln), 1); fila.remove(); } }, '×');
        fila.append(campo('rev', '40px'), campo('data', '90px'), campo('descricao', '100%'), campo('por', '70px'), tirar);
        feitas.append(fila);
      }
    }
    const corpo = el('div', { style: 'min-width:560px' },
      el('div', { class: 'explica', texto: 'A tabela fica em cima do carimbo de cada prancha, a revisão mais nova em cima (REV. | DATA | DESCRIÇÃO | POR), e o "REV." do carimbo acompanha. Cada prancha tem a sua numeração.' }),
      el('h4', { texto: 'Nova revisão' }),
      el('label', {}, 'Descrição ', desc),
      el('div', { style: 'display:flex;gap:14px;margin:6px 0' }, el('label', {}, 'Data ', data), el('label', {}, 'Por ', por)),
      el('div', { style: 'display:flex;gap:6px;margin:6px 0' }, 'Pranchas que mudaram:',
        el('button', { type: 'button', onclick: () => marcar(true) }, 'Todas'), el('button', { type: 'button', onclick: () => marcar(false) }, 'Nenhuma')),
      lista,
      ordem.length ? el('h4', { texto: 'Revisões já lançadas' }) : null,
      ordem.length ? feitas : null);
    if (await this.dialogo({ titulo: 'Revisões das pranchas', corpo, ok: 'Gravar' }) !== 'ok') return;
    const numeros = [...marcas].filter(([, c]) => c.checked).map(([n]) => n);
    const nova = desc.value.trim();
    if (nova && !numeros.length) { this.aviso('Marque as pranchas que mudaram com a revisão nova.', 'atencao'); return; }
    if (!nova && numeros.length) { this.aviso('Escreva a descrição da revisão nova.', 'atencao'); return; }
    // o desenho das pranchas aberto é gravado antes e recarregado depois (a tabela entra nele no servidor)
    const aberto = dados.pranchas.some(p => p.desenho === this.nomeDesenho);
    if (aberto && this._temPendente()) await this.salvar({ avisar: false });
    let r;
    try {
      r = await chamar(rota, nova ? { acao: 'nova', numeros, descricao: nova, data: data.value, por: por.value, revisoes: revs }
        : { acao: 'gravar', revisoes: revs });
    } catch (e) { this.aviso('Revisões das pranchas: ' + e.message, 'erro', 0); return; }
    if (aberto) await this._recarregarNaVista();
    const ultimas = numeros.map(n => `${dois(n)} (REV. ${((r.revisoes[String(n)] || []).slice(-1)[0] || {}).rev || '?'})`);
    const enc = (r.encostam || []).map(dois);
    this.aviso((nova ? `Revisão lançada nas pranchas ${ultimas.join(', ')}.` : 'Revisões gravadas.')
      + (enc.length ? ` A tabela encosta num detalhe na(s) prancha(s) ${enc.join(', ')}: arraste o detalhe para cima ou para o lado.` : ''),
      enc.length ? 'atencao' : 'info', enc.length ? 0 : 8000);
  }
}
