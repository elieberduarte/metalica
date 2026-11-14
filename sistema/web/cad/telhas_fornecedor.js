// Telhas para o fornecedor (usuário, 13/11: o padrão do Fábio; o "é assim?" aprovado no dia 14): Arquivo › Telhas para o
// fornecedor (DXF + Word)…. O desenho em tamanho real e a relação saem do Detalhar (desenho "Telhas para o fornecedor");
// aqui o acabamento e a cor de cada tipo de telha (as opções da obra, preenchidas uma vez) e a revisão, e o servidor
// grava o DXF e o Word na pasta da obra (04-EXECUCAO), com a revisão anterior para Obsoleto\ (app.telhas_fornecedor_projeto).

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

async function postar(rota, corpo) {
  let r;
  try {
    r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo || {}) });
  } catch { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}

export class MetodosTelhasFornecedorCAD {
  async dialogoTelhasFornecedor() {
    if (!this.projeto) { this.aviso('As telhas para o fornecedor precisam de um projeto aberto.', 'atencao'); return; }
    const rota = `/api/projetos/${encodeURIComponent(this.projeto)}/telhas-fornecedor`;
    let info;
    try { info = await postar(rota, {}); } catch (e) { this.aviso(`Telhas para o fornecedor: ${e.message}`, 'atencao', 0); return; }
    // um campo por tipo de telha: o acabamento e a cor (GALVALUME NATURAL, pré-pintada CINZA RAL 7035…), guardados na obra
    const campos = (info.tipos || []).map(t => ({ perfil: t.perfil,
      input: el('input', { type: 'text', name: 'acabamento', value: t.acabamento || '', placeholder: 'ex.: GALVALUME NATURAL ou pré-pintada CINZA RAL 7035',
                           'data-perfil': t.perfil }) }));
    const revisao = el('input', { type: 'text', name: 'revisao', value: info.revisao || 'R00', style: 'width: 6em' });
    const corpo = el('div', { class: 'impressao' },
      el('div', { class: 'explica', texto: 'O DXF em tamanho real (1 unidade = 1 mm, cotas de verdade) e a relação em Word, no padrão do Fábio, '
        + `gravados na pasta da obra (${info.pasta || '04-EXECUCAO'}); a revisão anterior vai para Obsoleto. Os números são os do último Detalhar.` }),
      el('div', { class: 'explica', texto: `Obra: ${info.obra || '—'} · local: ${info.local || '(em branco: o título da relação sai sem a cidade)'}` }),
      campos.length ? el('div', { class: 'explica', texto: 'Acabamento e cor de cada tipo de telha (fica guardado na obra):' }) : null,
      ...campos.map(c => el('label', {}, c.perfil, c.input)),
      el('label', {}, 'Revisão', revisao));
    // o Enter num campo não gera (como no Imprimir, D04)
    corpo.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target && ev.target.tagName === 'INPUT') ev.preventDefault(); });
    if (await this.dialogo({ titulo: 'Telhas para o fornecedor', corpo, ok: 'Gerar' }) !== 'ok') return;
    const acabamentos = Object.fromEntries(campos.map(c => [c.perfil, c.input.value.trim()]));
    this.dica('Gerando as telhas para o fornecedor…');
    try {
      const r = await postar(rota, { acao: 'gerar', acabamentos, revisao: revisao.value.trim() });
      this.dica('');
      const nomes = (r.arquivos || []).map(a => a.split(/[\\/]/).pop()).join(' e ');
      this.aviso(`Telhas para o fornecedor ${r.revisao}: ${nomes}, na pasta da obra${(r.obsoletos || []).length ? ` (a revisão anterior foi para Obsoleto)` : ''}.`, 'info', 15000);
      for (const a of r.avisos || []) this.aviso(`Telhas para o fornecedor: ${a}.`, 'atencao', 0);
    } catch (e) { this.dica(''); this.aviso(`Não foi possível gerar as telhas para o fornecedor: ${e.message}`, 'erro', 0); }
  }
}
