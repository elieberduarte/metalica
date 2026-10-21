// Imprimir pranchas (pedido do usuário, 21/10: "precisamos criar a ferramenta de impressão das pranchas diretamente do
// sistema"): Arquivo › Imprimir pranchas… ou Ctrl+P. Marca as folhas, escolhe a impressora do Windows, o papel (o de
// cada folha — a A1 na A1 da plotter — ou um só, com a folha ajustada a ele), a cor e as cópias, e manda direto, sem
// passar pelo PDF na tela. O servidor (rota_impressao no app.py, saida/impressao.py) gera o PDF das folhas marcadas —
// o mesmo do "PDF de todas as pranchas", com a regra R6 de emissão — e imprime pelo Windows.

const CHAVE = 'impressao.ultima';

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
  if (!r.ok || (dados && dados.erro)) {
    const erro = new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
    erro.dados = dados;                              // a emissão recusada traz as peças (R6)
    throw erro;
  }
  return dados;
}

function lerUltima() { try { return JSON.parse(localStorage.getItem(CHAVE) || '{}') || {}; } catch { return {}; } }
function gravarUltima(v) { try { localStorage.setItem(CHAVE, JSON.stringify(v)); } catch { /* sem armazenamento: só não lembra */ } }

/** "A1" do driver ("ISOA1", "A1 (594 x 841 mm)"): os da série A primeiro, do maior para o menor; depois os outros. */
function ordemDoPapel(p) {
  const m = /^A(\d)\b/i.exec(String(p.nome).replace(/^ISO\s*/i, ''));
  return m ? Number(m[1]) : 10 + 1 / Math.max(1, p.largura * p.altura);
}
const mm = (v) => Math.round(v).toLocaleString('pt-BR');
const porcento = (v) => `${Math.round(v * 100)}%`;

/** Quanto a folha encolhe no papel (o papel inteiro, sem as margens da impressora): a conta do aviso do diálogo. */
function reducao(folha, papel) {
  const [fa, fb] = [folha.largura, folha.altura].sort((x, y) => x - y);
  const [pa, pb] = [papel.largura, papel.altura].sort((x, y) => x - y);
  return Math.min(pa / fa, pb / fb);
}

if (!document.getElementById('estilo-impressao')) {
  document.head.append(el('style', { id: 'estilo-impressao' }, `
    .impressao { min-width: min(560px, 88vw); }
    .impressao .folhas { max-height: 34vh; overflow: auto; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); padding: 4px 0; }
    .impressao .folhas label { flex-direction: row; align-items: center; gap: 8px; padding: 3px 10px; color: var(--texto); font-size: 13px; cursor: pointer; }
    .impressao .folhas label:hover { background: var(--campo-borda); }
    .impressao .folhas .fmt { margin-left: auto; color: var(--texto2); font-variant-numeric: tabular-nums; }
    .impressao .linha { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
    .impressao .linha > label { flex: 1 1 160px; }
    .impressao .botoes-folhas { display: flex; gap: 6px; align-items: center; }
    .impressao .botoes-folhas button { padding: 3px 9px; font-size: 12px; }
    .impressao .botoes-folhas .conta { margin-left: auto; color: var(--texto2); font-size: 12px; }
    .impressao label.opcao { flex-direction: row; align-items: center; gap: 6px; color: var(--texto); }
    .impressao .resumo { color: var(--texto2); font-size: 12px; line-height: 1.45; min-height: 2.9em; }
  `));
}

export class MetodosImpressaoCAD {
  /** Os desenhos de pranchas do projeto, na ordem do PDF de todas as pranchas. */
  async _desenhosParaImprimir() {
    return (await this._listaDesenhos()).filter(d => d.pranchas || /^prancha-\d+$/i.test(d.nome))
      .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { numeric: true })).map(d => d.nome);
  }

  /** O índice da folha que está no meio da tela, quando o desenho aberto é o das pranchas. */
  _folhaNaTela(folhas) {
    const lista = (this.doc.metadados || {}).pranchas;
    if (!Array.isArray(lista) || !this.tela) return null;
    const [cx, cy] = this.tela.paraMundo([this.tela.largura / 2, (this.tela.altura || 0) / 2]);
    const i = lista.findIndex(f => {
      const o = f.origem || [0, 0], t = f.tamanho || [0, 0];
      return cx >= o[0] && cx <= o[0] + t[0] && cy >= o[1] && cy <= o[1] + t[1];
    });
    if (i < 0) return null;
    const f = folhas.find(x => x.desenho === this.nomeDesenho && x.numero === lista[i].numero);
    return f ? f.indice : null;
  }

  async dialogoImprimir() {
    if (!this.projeto) { this.aviso('Imprimir precisa de um projeto aberto.', 'atencao'); return; }
    const base = `/api/projetos/${encodeURIComponent(this.projeto)}/impressao`;
    const desenhos = await this._desenhosParaImprimir();
    if (!desenhos.length) { this.aviso('O projeto não tem pranchas ainda: Desenho → Montar pranchas (automático)… ou Gerar pranchas das folhas.', 'atencao'); return; }
    if (this.nomeDesenho && desenhos.includes(this.nomeDesenho)) await this.salvar({ avisar: false });
    let folhas, imps;
    try {
      [folhas, imps] = await Promise.all([postar(`${base}/folhas`, { desenhos }).then(r => r.folhas || []), postar(`${base}/impressoras`, {})]);
    } catch (e) { this.aviso(`Não foi possível preparar a impressão: ${e.message}`, 'erro', 0); return; }
    if (!folhas.length) { this.aviso('As pranchas do projeto não têm folhas para imprimir.', 'atencao'); return; }
    const lista = imps.impressoras || [];
    if (!lista.length) { this.aviso('Nenhuma impressora instalada no Windows: use Arquivo › Exportar › PDF de todas as pranchas.', 'atencao', 0); return; }
    const ultima = lerUltima();

    // as folhas
    const marcas = folhas.map(f => el('input', { type: 'checkbox', checked: true, 'data-indice': f.indice }));
    const conta = el('span', { class: 'conta' });
    const marcadas = () => folhas.filter((f, i) => marcas[i].checked);
    const marcar = (fn) => { marcas.forEach((c, i) => { c.checked = fn(folhas[i]); }); atualizar(); };
    const naTela = this._folhaNaTela(folhas);
    const caixaFolhas = el('div', { class: 'folhas' }, folhas.map((f, i) => el('label', {}, marcas[i],
      el('span', { texto: `${f.numero != null ? String(f.numero).padStart(2, '0') + ' · ' : ''}${f.titulo}` }),
      el('span', { class: 'fmt', texto: f.formato || `${mm(f.largura)} × ${mm(f.altura)} mm` }))));
    caixaFolhas.addEventListener('change', () => atualizar());

    // impressora, papel, ajuste, cor, cópias
    const selImp = el('select', { name: 'impressora' }, lista.map(p => el('option', { value: p.nome, texto: p.nome + (p.padrao ? ' (padrão)' : '') })));
    selImp.value = lista.some(p => p.nome === ultima.impressora) ? ultima.impressora : (imps.padrao || lista[0].nome);
    const selPapel = el('select', { name: 'papel' });
    const selAjuste = el('select', { name: 'ajuste' },
      el('option', { value: 'real', texto: 'Tamanho real (1:1 — a escala do carimbo)' }),
      el('option', { value: 'ajustar', texto: 'Ajustar ao papel' }));
    selAjuste.value = ultima.ajuste === 'ajustar' ? 'ajustar' : 'real';
    const selCor = el('select', { name: 'cor' },
      el('option', { value: 'preto', texto: 'Preto (as cores saem pretas; o cinza continua cinza)' }),
      el('option', { value: 'cor', texto: 'Colorida (as cores das camadas)' }),
      el('option', { value: 'cinza', texto: 'Tons de cinza' }));
    selCor.value = ['preto', 'cor', 'cinza'].includes(ultima.cor) ? ultima.cor : 'preto';
    const copias = el('input', { type: 'number', name: 'copias', min: 1, max: 99, step: 1, value: 1 });
    const resumo = el('div', { class: 'resumo' });
    let papeis = [];

    const atualizar = () => {
      const m = marcadas();
      conta.textContent = `${m.length} de ${folhas.length} folha(s)`;
      const p = papeis.find(x => String(x.id) === selPapel.value);
      selAjuste.disabled = false;
      if (!m.length) { resumo.textContent = 'Marque ao menos uma folha.'; return; }
      if (!p) {
        resumo.textContent = 'Cada folha no papel do tamanho dela (a A1 na A1), quando a impressora o tem; senão no menor papel em que ela cabe.';
        return;
      }
      const fs = [...new Set(m.map(f => f.formato || `${mm(f.largura)}×${mm(f.altura)}`))];
      const f0 = m[0], k = reducao(f0, p);
      if (selAjuste.value === 'ajustar') {
        const k2 = Math.min(...m.map(f => reducao(f, p)));
        resumo.textContent = Math.abs(k2 - 1) < 0.02
          ? `${fs.join(', ')} no ${p.nome}: no tamanho real.`
          : `${fs.join(', ')} no ${p.nome}: ${k2 < 1 ? 'reduzida' : 'ampliada'} a cerca de ${porcento(k2)} — a escala escrita no carimbo não vale no papel (1:25 vira ~1:${Math.round(25 / k2)}).`;
      } else {
        resumo.textContent = k < 0.98
          ? `A folha ${f0.formato || ''} é maior que o ${p.nome}: em tamanho real só o meio dela sai. Use "Ajustar ao papel".`
          : `${fs.join(', ')} no ${p.nome}, em tamanho real, no meio do papel.`;
      }
    };

    const carregarPapeis = async () => {
      selPapel.replaceChildren(el('option', { value: 'auto', texto: 'carregando os papéis…' }));
      selPapel.disabled = true;
      try {
        const r = await postar(`${base}/papeis`, { impressora: selImp.value });
        papeis = (r.papeis || []).slice().sort((a, b) => ordemDoPapel(a) - ordemDoPapel(b));
      } catch (e) { papeis = []; this.aviso(`A impressora não deu os papéis dela: ${e.message}`, 'atencao'); }
      selPapel.replaceChildren(el('option', { value: 'auto', texto: 'Automático: o tamanho de cada folha' }),
        ...papeis.map(p => el('option', { value: String(p.id), texto: `${p.nome} — ${mm(p.largura)} × ${mm(p.altura)} mm` })));
      selPapel.disabled = false;
      selPapel.value = selImp.value === ultima.impressora && papeis.some(p => String(p.id) === String(ultima.papel)) ? String(ultima.papel) : 'auto';
      atualizar();
    };
    selImp.addEventListener('change', carregarPapeis);
    for (const s of [selPapel, selAjuste]) s.addEventListener('change', atualizar);

    const corpo = el('div', { class: 'impressao' },
      el('div', { class: 'botoes-folhas' },
        el('button', { type: 'button', texto: 'Todas', onclick: () => marcar(() => true) }),
        el('button', { type: 'button', texto: 'Nenhuma', onclick: () => marcar(() => false) }),
        naTela !== null ? el('button', { type: 'button', texto: 'Só a da tela', title: 'a folha que está no meio da tela', onclick: () => marcar(f => f.indice === naTela) }) : null,
        conta),
      caixaFolhas,
      el('label', {}, 'Impressora', selImp),
      el('div', { class: 'linha' }, el('label', {}, 'Papel', selPapel), el('label', {}, 'Tamanho', selAjuste)),
      el('div', { class: 'linha' }, el('label', {}, 'Cor', selCor), el('label', { style: 'flex: 0 0 90px' }, 'Cópias', copias)),
      resumo);
    atualizar();
    carregarPapeis();
    if (await this.dialogo({ titulo: 'Imprimir pranchas', corpo, ok: 'Imprimir' }) !== 'ok') return;

    const escolhidas = marcadas();
    if (!escolhidas.length) { this.aviso('Nenhuma folha marcada: nada foi impresso.', 'atencao'); return; }
    const pedido = {
      desenhos, impressora: selImp.value, papel: selPapel.value === 'auto' ? null : Number(selPapel.value),
      ajuste: selAjuste.value, cor: selCor.value, copias: Math.max(1, Math.min(99, parseInt(copias.value, 10) || 1)),
      folhas: escolhidas.length === folhas.length ? null : escolhidas.map(f => f.indice),
    };
    gravarUltima({ impressora: pedido.impressora, papel: pedido.papel, ajuste: pedido.ajuste, cor: pedido.cor });
    this.dica(`Imprimindo ${escolhidas.length} folha(s) em ${pedido.impressora}…`);
    try {
      const r = await postar(`${base}/imprimir`, pedido);
      const papeisUsados = [...new Set((r.folhas || []).map(f => f.papel))].join(', ');
      const texto = `${r.paginas} folha(s)${r.copias > 1 ? ` × ${r.copias} cópias` : ''} ${r.arquivo ? 'gravada(s) em PDF pela' : 'enviada(s) para'} ${r.impressora}${papeisUsados ? ` (${papeisUsados})` : ''}`;
      const a = r.arquivo;
      this.aviso(el('span', {}, texto, a ? ': ' : '.', a ? el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: a.nome || 'abrir' }) : null,
        ...(r.avisos || []).length ? [el('br'), (r.avisos || []).join(' · ')] : []), (r.avisos || []).length ? 'atencao' : 'info', a || (r.avisos || []).length ? 0 : 12000);
      this.dica(r.arquivo ? 'Impressão gravada em PDF (pasta pranchas/ do projeto).' : 'Impressão enviada: acompanhe na fila da impressora do Windows.');
    } catch (e) { this.dica(''); this._avisoDeEmissao(e, 'Não foi possível imprimir'); }
  }
}
