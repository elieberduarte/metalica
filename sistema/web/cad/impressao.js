// Imprimir pranchas (pedido do usuário, 21/10: "precisamos criar a ferramenta de impressão das pranchas diretamente do
// sistema"): Arquivo › Imprimir pranchas… ou Ctrl+P. Marca as folhas, escolhe a impressora do Windows, o papel (o de
// cada folha — a A1 na A1 da plotter — ou um só, com a folha ajustada a ele), a cor e as cópias, e manda direto, sem
// passar pelo PDF na tela. O servidor (rota_impressao no app.py, saida/impressao.py) gera o PDF das folhas marcadas —
// o mesmo do "PDF de todas as pranchas", com a regra R6 de emissão — e imprime pelo Windows.

import { ESPESSURAS } from './nucleo/tipos_linha.js';
import { Tela } from './nucleo/tela.js';

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

// o Enter num campo do diálogo (Cópias, Escala…) não imprime: o diálogo é um <form>, e o Enter num campo o enviava na
// hora, com a plotter marcada (D04 do usuario-desastrado, 13/11). Só o botão Imprimir manda; o Enter num botão segue.
function semEnterNosCampos(corpo) {
  corpo.addEventListener('keydown', (ev) => {
    const t = ev.target;
    if (ev.key === 'Enter' && t && (t.tagName === 'INPUT' || t.tagName === 'SELECT')) ev.preventDefault();
  });
  return corpo;
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
/** A plotter da fábrica (a HP Designjet T120, memória impressao-das-pranchas): vem marcada sempre (DECISÃO 12/11). */
export const ehPlotter = (p) => /designjet|t120|plotter/i.test(`${p && p.nome || ''} ${p && p.driver || ''}`.replace(/Microsoft IPP Class Driver/i, ''));
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
    dialog.dialogo:has(.impressao-folhas) { width: min(1180px, calc(100vw - 32px)); max-width: none; }   /* o editor.css do 3D limita todo diálogo a 540 px */
    .impressao:not(.impressao-folhas) { min-width: min(560px, 88vw); }
    .impressao { display: flex; flex-direction: column; gap: 8px; }
    .impressao .grade-impressao { display: grid; grid-template-columns: minmax(0, 1fr) 270px; gap: 12px; align-items: start; }
    .impressao .folhas { max-height: 52vh; overflow-y: auto; overflow-x: hidden; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); }
    .impressao .folhas table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .impressao .folhas th { position: sticky; top: 0; background: var(--painel); text-align: left; font-weight: 600; color: var(--texto2); font-size: 11px; padding: 5px 6px; border-bottom: 1px solid var(--campo-borda); }
    .impressao .folhas td { padding: 4px 6px; border-bottom: 1px solid color-mix(in srgb, var(--campo-borda) 55%, transparent); vertical-align: middle; color: var(--texto); }
    .impressao .folhas td.titulo { white-space: normal; overflow-wrap: anywhere; }
    .impressao .folhas td.num, .impressao .folhas td.rev, .impressao .folhas td.escala { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .impressao .folhas tr { cursor: pointer; }
    .impressao .folhas tr.foco td { background: color-mix(in srgb, var(--azul) 12%, transparent); }
    .impressao .folhas select.papel-folha { padding: 2px 4px; font-size: 12px; max-width: 190px; }
    .impressao .chip { display: inline-block; border-radius: 9px; padding: 1px 8px; font-size: 11px; white-space: nowrap; }
    .impressao .chip.nunca { background: color-mix(in srgb, var(--texto2) 15%, transparent); color: var(--texto2); }
    .impressao .chip.ok { background: color-mix(in srgb, #15803d 16%, transparent); color: #15803d; }
    .impressao .chip.mudou { background: color-mix(in srgb, #d97706 20%, transparent); color: #b45309; font-weight: 600; }
    .impressao .lado { display: flex; flex-direction: column; gap: 8px; }
    .impressao .previa { border: 1px solid var(--campo-borda); border-radius: var(--raio-p); padding: 6px; text-align: center; }
    .impressao .previa canvas { display: block; width: 100%; height: 180px; }
    .impressao .previa .leg { color: var(--texto2); font-size: 11px; margin-top: 4px; }
    .impressao .botoes-folhas .espaco { flex: 1; }
    .impressao .botoes-folhas .rotulo { color: var(--texto2); font-size: 12px; }
    .impressao .botoes-folhas select, .impressao .botoes-folhas input[type=text] { padding: 3px 6px; font-size: 12px; }
    .impressao .rodape-impressao { display: flex; gap: 10px; align-items: baseline; }
    .impressao .rodape-impressao .conta { margin-left: auto; color: var(--texto2); font-size: 12px; }
    .impressao .linha { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
    .impressao .linha > label { flex: 1 1 160px; }
    .impressao .botoes-folhas { display: flex; gap: 6px; align-items: center; }
    .impressao .botoes-folhas button { padding: 3px 9px; font-size: 12px; }
    .impressao .botoes-folhas .conta { margin-left: auto; color: var(--texto2); font-size: 12px; }
    .impressao label.opcao { flex-direction: row; align-items: center; gap: 6px; color: var(--texto); }
    .impressao .resumo { color: var(--texto2); font-size: 12px; line-height: 1.45; }
    dialog.dialogo:has(.penas) { width: min(760px, calc(100vw - 32px)); }
    .penas { min-width: 0; }
    .penas .tabela { max-height: 46vh; overflow: auto; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); }
    .penas .pena { display: grid; grid-template-columns: 18px 72px 1fr 120px 150px; gap: 8px; align-items: center; padding: 4px 8px; font-size: 12.5px; }
    .penas .pena:nth-child(odd) { background: color-mix(in srgb, var(--campo-borda) 35%, transparent); }
    .penas .pena .amostra { width: 16px; height: 16px; border-radius: 3px; border: 1px solid var(--borda-forte, #888); }
    .penas .pena .hex { font: 11.5px var(--mono, monospace); }
    .penas .pena .camadas { color: var(--texto2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .penas .pena .saida { display: flex; gap: 4px; align-items: center; }
    .penas .pena .saida input[type=color] { width: 28px; height: 22px; padding: 0; border: 0; background: none; }
    .penas .botoes-folhas { margin-bottom: 6px; }
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

  /**
   * Imprimir pranchas (Ctrl+P) — a tela A aprovada pelo usuário em 12/11 ("precisamos melhorar a ferramenta de gestão das
   * impressões"; Projeto/ANALISES/Interface/Impressao-gerenciador-proposta-2026-11-12.pdf): o diálogo largo, com o título
   * inteiro; em cada folha o formato, a escala, a revisão, a situação (nunca impressa, impressa, mudou depois) e o papel
   * dela; "só as que mudaram"; os conjuntos de folhas guardados da obra; a pré-visualização da folha em foco; a plotter da
   * fábrica sempre marcada (DECISÃO 12/11), mesmo com outra padrão no Windows.
   */
  async dialogoImprimir(soPranchas = false) {
    if (!this.projeto) { this.aviso('Imprimir precisa de um projeto aberto.', 'atencao'); return; }
    const base = `/api/projetos/${encodeURIComponent(this.projeto)}/impressao`;
    const desenhos = await this._desenhosParaImprimir();
    // o desenho aberto não é das pranchas (o Original do projeto recebido, um detalhamento): imprime ele — a vista da
    // tela ou o desenho inteiro (usuário, 23/10: "se dou um ctrl + p nessa tela original ele não deixa imprimir")
    if (!soPranchas && this.nomeDesenho && !desenhos.includes(this.nomeDesenho)) return this._imprimirEsteDesenho(base, desenhos);
    if (!desenhos.length) { this.aviso('O projeto não tem pranchas ainda: Desenho → Montar pranchas (automático)… ou Gerar pranchas das folhas.', 'atencao'); return; }
    if (this.nomeDesenho && desenhos.includes(this.nomeDesenho)) await this.salvar({ avisar: false });
    let folhas, imps, conjuntos;
    try {
      const [rf, ri] = await Promise.all([postar(`${base}/folhas`, { desenhos }), postar(`${base}/impressoras`, {})]);
      folhas = rf.folhas || []; conjuntos = rf.conjuntos || {}; imps = ri;
    } catch (e) { this.aviso(`Não foi possível preparar a impressão: ${e.message}`, 'erro', 0); return; }
    if (!folhas.length) { this.aviso('As pranchas do projeto não têm folhas para imprimir.', 'atencao'); return; }
    const lista = imps.impressoras || [];
    if (!lista.length) { this.aviso('Nenhuma impressora instalada no Windows: use Arquivo › Exportar › PDF de todas as pranchas.', 'atencao', 0); return; }
    const ultima = lerUltima();
    const plotter = lista.find(ehPlotter);

    // ---- as folhas: uma linha cada, com o papel dela
    const marcas = folhas.map(f => el('input', { type: 'checkbox', checked: true, 'data-indice': f.indice }));
    const papelDe = folhas.map(f => el('select', { class: 'papel-folha', 'data-indice': f.indice, title: 'o papel desta folha' }));
    const conta = el('span', { class: 'conta' });
    const marcadas = () => folhas.filter((f, i) => marcas[i].checked);
    const marcar = (fn) => { marcas.forEach((c, i) => { c.checked = fn(folhas[i]); }); atualizar(); };
    const naTela = this._folhaNaTela(folhas);
    const linhas = folhas.map((f, i) => {
      const s = f.situacao || { estado: 'nunca' };
      const chip = s.estado === 'impressa' ? el('span', { class: 'chip ok', texto: `impressa ${s.quando} · ${s.onde}` })
        : s.estado === 'mudou' ? el('span', { class: 'chip mudou', texto: `mudou depois da impressão de ${s.quando}` })
          : el('span', { class: 'chip nunca', texto: 'nunca impressa' });
      const tr = el('tr', { 'data-indice': f.indice },
        el('td', {}, marcas[i]),
        el('td', { class: 'num', texto: f.numero != null ? String(f.numero).padStart(2, '0') : '' }),
        el('td', { class: 'titulo', texto: f.titulo }),
        el('td', { texto: f.formato || `${mm(f.largura)} × ${mm(f.altura)}` }),
        el('td', { class: 'escala', texto: f.escala || '—' }),
        el('td', { class: 'rev', texto: f.revisao || '—' }),
        el('td', { class: 'situacao', 'data-estado': s.estado }, chip),
        el('td', {}, papelDe[i]));
      tr.addEventListener('click', (ev) => { if (ev.target.tagName !== 'INPUT' && ev.target.tagName !== 'SELECT') focar(i); });
      return tr;
    });
    const tabela = el('div', { class: 'folhas' }, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}), el('th', { texto: 'Nº' }), el('th', { texto: 'Folha' }), el('th', { texto: 'Formato' }),
        el('th', { texto: 'Escala' }), el('th', { texto: 'Rev.' }), el('th', { texto: 'Situação' }), el('th', { texto: 'Papel' }))),
      el('tbody', {}, linhas)));
    tabela.addEventListener('change', () => atualizar());

    // ---- os filtros e os conjuntos
    const mudaram = folhas.filter(f => (f.situacao || {}).estado === 'mudou');
    const selConj = el('select', { name: 'conjunto' });
    const montarConjuntos = () => {
      selConj.replaceChildren(el('option', { value: '', texto: Object.keys(conjuntos).length ? '— conjunto —' : '(nenhum guardado)' }),
        ...Object.keys(conjuntos).sort((a, b) => a.localeCompare(b, 'pt-BR')).map(n => el('option', { value: n, texto: `${n} (${conjuntos[n].length})` })));
      apagarConj.hidden = !selConj.value;
    };
    selConj.addEventListener('change', () => {
      apagarConj.hidden = !selConj.value;
      if (!selConj.value) return;
      const ch = new Set(conjuntos[selConj.value] || []);
      marcar(f => ch.has(f.chave));
    });
    const gravarConjuntos = async (novos) => {
      try { conjuntos = (await postar(`${base}/conjuntos`, { conjuntos: novos })).conjuntos || {}; }
      catch (e) { this.aviso(`Não foi possível gravar o conjunto: ${e.message}`, 'erro'); }
    };
    const nomeConj = el('input', { type: 'text', name: 'nome-conjunto', placeholder: 'nome do conjunto (Fabricação, Montagem…)', hidden: true });
    const okConj = el('button', { type: 'button', texto: 'Guardar', hidden: true });
    const salvarConj = el('button', { type: 'button', texto: 'Salvar a seleção como…', title: 'guarda as folhas marcadas com um nome, nesta obra' });
    const apagarConj = el('button', { type: 'button', texto: '×', title: 'apagar este conjunto', hidden: true });
    salvarConj.addEventListener('click', () => { nomeConj.hidden = okConj.hidden = false; salvarConj.hidden = true; nomeConj.focus(); });
    const guardar = async () => {
      const nome = nomeConj.value.trim();
      if (!nome) return;
      await gravarConjuntos({ ...conjuntos, [nome]: marcadas().map(f => f.chave) });
      nomeConj.value = ''; nomeConj.hidden = okConj.hidden = true; salvarConj.hidden = false;
      montarConjuntos(); selConj.value = nome; apagarConj.hidden = false;
    };
    okConj.addEventListener('click', guardar);
    nomeConj.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); ev.stopPropagation(); guardar(); } });
    apagarConj.addEventListener('click', async () => {
      const n = selConj.value; if (!n) return;
      const novos = { ...conjuntos }; delete novos[n];
      await gravarConjuntos(novos); montarConjuntos();
    });
    montarConjuntos();

    // ---- impressora, cor, cópias, o papel das marcadas
    const selImp = el('select', { name: 'impressora' }, lista.map(p => el('option', { value: p.nome,
      texto: (p === plotter ? `★ Plotter da fábrica — ${p.nome.split(String.fromCharCode(92)).pop()}` : p.nome) + (p.padrao ? ' (padrão do Windows)' : ''), title: p.nome })));
    // a plotter da fábrica sempre (DECISÃO do usuário, 12/11); sem ela, a padrão do Windows
    selImp.value = plotter ? plotter.nome : (imps.padrao || lista[0].nome);
    const selCor = el('select', { name: 'cor' },
      el('option', { value: 'preto', texto: 'Preto (as cores saem pretas; o cinza continua cinza)' }),
      el('option', { value: 'cor', texto: 'Colorida (as cores das camadas)' }),
      el('option', { value: 'cinza', texto: 'Tons de cinza' }));
    selCor.value = ['preto', 'cor', 'cinza'].includes(ultima.cor) ? ultima.cor : 'preto';
    const copias = el('input', { type: 'number', name: 'copias', min: 1, max: 99, step: 1, value: 1 });
    const papelTodas = el('select', { name: 'papel-marcadas' });
    papelTodas.addEventListener('change', () => {
      if (papelTodas.value === '') return;
      marcas.forEach((c, i) => { if (c.checked) papelDe[i].value = papelTodas.value; });
      papelTodas.value = ''; atualizar();
    });
    const resumo = el('div', { class: 'resumo' });
    let papeis = [];

    const opcoesDoPapel = (f) => [el('option', { value: 'auto', texto: 'o da folha' }),
      ...papeis.map(p => {
        const k = reducao(f, p);
        return el('option', { value: String(p.id), texto: k >= 0.98 ? `${p.nome} — tamanho real` : `${p.nome} — ajustada (${porcento(k)})` });
      })];
    const nomeDoPapel = (f, i) => {
      const v = papelDe[i].value;
      if (v === 'auto' || !v) return { texto: `${f.formato || 'folha'} no papel dela`, chave: 'auto' };
      const p = papeis.find(x => String(x.id) === v), k = p ? reducao(f, p) : 1;
      return { texto: p ? (k >= 0.98 ? `${p.nome}` : `${p.nome} ajustada`) : v, chave: v };
    };

    const atualizar = () => {
      const m = marcadas();
      conta.textContent = `${m.length} de ${folhas.length} folha(s)`;
      linhas.forEach((tr, i) => tr.classList.toggle('marcada', marcas[i].checked));
      if (!m.length) { resumo.textContent = 'Marque ao menos uma folha.'; return; }
      const grupos = new Map();
      for (const f of m) { const i = folhas.indexOf(f), n = nomeDoPapel(f, i).texto; grupos.set(n, (grupos.get(n) || 0) + 1); }
      const revs = [...new Set(m.map(f => f.revisao).filter(Boolean))];
      const imp = selImp.value === (plotter && plotter.nome) ? 'na plotter' : `em ${selImp.value}`;
      resumo.textContent = `${m.length} folha(s) marcada(s) ${imp}: ${[...grupos].map(([n, q]) => `${q} ${n}`).join(' + ')}`
        + (revs.length ? ` · revisão ${revs.join(', ')}` : '');
    };

    const carregarPapeis = async () => {
      const antes = papelDe.map(s => s.value);
      papelTodas.disabled = true;
      papelDe.forEach(s => { s.replaceChildren(el('option', { value: 'auto', texto: 'carregando…' })); s.disabled = true; });
      try {
        const r = await postar(`${base}/papeis`, { impressora: selImp.value });
        papeis = (r.papeis || []).slice().sort((a, b) => ordemDoPapel(a) - ordemDoPapel(b));
      } catch (e) { papeis = []; this.aviso(`A impressora não deu os papéis dela: ${e.message}`, 'atencao'); }
      folhas.forEach((f, i) => {
        papelDe[i].replaceChildren(...opcoesDoPapel(f));
        papelDe[i].disabled = false;
        papelDe[i].value = papeis.some(p => String(p.id) === antes[i]) ? antes[i] : 'auto';
      });
      papelTodas.replaceChildren(el('option', { value: '', texto: 'escolher…' }), el('option', { value: 'auto', texto: 'o de cada folha' }),
        ...papeis.map(p => el('option', { value: String(p.id), texto: `${p.nome} — ${mm(p.largura)} × ${mm(p.altura)} mm` })));
      papelTodas.disabled = false;
      atualizar();
    };
    selImp.addEventListener('change', carregarPapeis);

    // ---- a pré-visualização da folha em foco (desenhada pela própria tela do CAD, num canvas pequeno)
    const previa = el('canvas', { class: 'previa-folha' });
    const legenda = el('div', { class: 'leg' });
    let telaPrevia = null;
    const focar = (i) => {
      linhas.forEach((tr, j) => tr.classList.toggle('foco', j === i));
      const f = folhas[i];
      legenda.textContent = `${f.numero != null ? String(f.numero).padStart(2, '0') + ' · ' : ''}${f.titulo}`;
      if (f.desenho !== this.nomeDesenho || !f.origem || !f.tamanho) {
        previa.hidden = true;
        legenda.textContent += ' — a pré-visualização é das folhas do desenho aberto';
        return;
      }
      previa.hidden = false;
      try {
        if (!telaPrevia) { telaPrevia = new Tela(previa, this.doc); telaPrevia.grade = false; }
        telaPrevia.escuro = this.tela.escuro;
        telaPrevia.redimensionar();
        telaPrevia.enquadrar([[f.origem[0], f.origem[1]], [f.origem[0] + f.tamanho[0], f.origem[1] + f.tamanho[1]]], 0.02);
        telaPrevia.desenhar();
      } catch (e) { previa.hidden = true; legenda.textContent += ` — sem pré-visualização (${e.message})`; }
    };
    this._previaImpressao = () => telaPrevia;              // para o verificador

    const corpo = el('div', { class: 'impressao impressao-folhas' },
      el('div', { class: 'botoes-folhas' },
        el('button', { type: 'button', texto: 'Todas', onclick: () => marcar(() => true) }),
        el('button', { type: 'button', texto: 'Nenhuma', onclick: () => marcar(() => false) }),
        naTela !== null ? el('button', { type: 'button', texto: 'Só a da tela', title: 'a folha que está no meio da tela', onclick: () => marcar(f => f.indice === naTela) }) : null,
        el('button', { type: 'button', name: 'so-mudaram', texto: `Só as que mudaram desde a última impressão (${mudaram.length})`, disabled: !mudaram.length,
          title: 'as folhas que mudaram depois da última vez que foram impressas', onclick: () => marcar(f => (f.situacao || {}).estado === 'mudou') }),
        el('span', { class: 'espaco' }),
        el('span', { class: 'rotulo', texto: 'Conjunto:' }), selConj, apagarConj, salvarConj, nomeConj, okConj),
      el('div', { class: 'grade-impressao' },
        tabela,
        el('div', { class: 'lado' },
          el('label', {}, 'Impressora', selImp),
          el('label', {}, 'Cor', selCor),
          el('div', { class: 'linha' }, el('label', { style: 'flex: 0 0 80px' }, 'Cópias', copias), el('label', {}, 'Papel das marcadas', papelTodas)),
          el('div', { class: 'previa' }, previa, legenda),
          el('button', { type: 'button', texto: 'Penas de impressão…', title: 'A espessura e a cor de cada cor do desenho no papel (o CTB do AutoCAD)',
            onclick: () => { irPenas = true; document.getElementById('dialogo-cancelar').click(); } }))),
      el('div', { class: 'rodape-impressao' }, resumo, conta));
    let irPenas = false;
    atualizar();
    carregarPapeis();
    // a folha em foco: a da tela, senão a primeira (depois que o diálogo está na tela, para o canvas ter tamanho)
    const inicial = Math.max(0, folhas.findIndex(f => f.indice === naTela));
    requestAnimationFrame(() => requestAnimationFrame(() => focar(inicial)));
    semEnterNosCampos(corpo);
    const resposta = await this.dialogo({ titulo: 'Imprimir pranchas', corpo, ok: 'Imprimir' });
    this._previaImpressao = null;
    if (irPenas) { if (await this.dialogoPenas()) return this.dialogoImprimir(true); return; }
    if (resposta !== 'ok') return;

    const escolhidas = marcadas();
    if (!escolhidas.length) { this.aviso('Nenhuma folha marcada: nada foi impresso.', 'atencao'); return; }
    const papeisDasFolhas = {};
    for (const f of escolhidas) { const v = papelDe[folhas.indexOf(f)].value; if (v && v !== 'auto') papeisDasFolhas[f.indice] = Number(v); }
    const pedido = {
      desenhos, impressora: selImp.value, papel: null, ajuste: 'real', papeis: papeisDasFolhas,
      cor: selCor.value, copias: Math.max(1, Math.min(99, parseInt(copias.value, 10) || 1)),
      folhas: escolhidas.length === folhas.length ? null : escolhidas.map(f => f.indice),
    };
    gravarUltima({ ...ultima, cor: pedido.cor });
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

  /**
   * As penas de impressão, como o CTB do AutoCAD (pedido do usuário, 23/10: "criar as penas igual existe no autocad para
   * configurar como vai para impressão"): para cada cor do desenho, a espessura com que ela sai no papel (ou a do objeto)
   * e a cor de saída (a própria, preta, cinza ou outra). A tabela é do programa — vale para todas as obras, na impressão
   * e no PDF. As cores da lista são as do desenho aberto (das camadas e as próprias dos objetos), as mais usadas
   * primeiro, e as que já têm pena. Devolve true quando gravou.
   */
  async dialogoPenas() {
    if (!this.projeto) { this.aviso('As penas precisam de um projeto aberto.', 'atencao'); return false; }
    const base = `/api/projetos/${encodeURIComponent(this.projeto)}/impressao`;
    let penas;
    try { penas = (await postar(`${base}/penas`, {})).penas || {}; } catch (e) { this.aviso(`Não foi possível ler as penas: ${e.message}`, 'erro', 0); return false; }
    // as cores do desenho: quantos objetos e quais camadas
    const usos = new Map();
    for (const e of this.doc.entidades.values()) {
      const cam = this.doc.camadas.get(e.camada);
      const cor = String((e.atributos && e.atributos.cor) || (cam && cam.cor) || '#4b5563').toLowerCase();
      if (!/^#[0-9a-f]{6}$/.test(cor)) continue;
      let u = usos.get(cor); if (!u) usos.set(cor, u = { n: 0, camadas: new Set() });
      u.n++; u.camadas.add(e.camada);
    }
    for (const c of Object.keys(penas)) if (!usos.has(c)) usos.set(c, { n: 0, camadas: new Set() });
    const cores = [...usos.entries()].sort((a, b) => b[1].n - a[1].n);
    const fmtEsp = (v) => `${String(Math.round(v * 100) / 100).replace('.', ',')} mm`;
    const linhas = cores.map(([cor, u]) => {
      const p = penas[cor] || {};
      const esp = el('select', { name: 'espessura', 'data-cor': cor },
        el('option', { value: '', texto: 'a do objeto' }), ...ESPESSURAS.map(v => el('option', { value: String(v), texto: fmtEsp(v) })));
      esp.value = p.espessura == null ? '' : String(ESPESSURAS.reduce((m, v) => (Math.abs(v - p.espessura) < Math.abs(m - p.espessura) ? v : m), ESPESSURAS[0]));
      const outra = el('input', { type: 'color', value: p.cor || cor, title: 'a cor de saída' });
      const saida = el('select', { name: 'cor', 'data-cor': cor },
        el('option', { value: '', texto: 'a própria' }), el('option', { value: '#000000', texto: 'preta' }),
        el('option', { value: '#808080', texto: 'cinza' }), el('option', { value: 'outra', texto: 'outra…' }));
      saida.value = !p.cor ? '' : p.cor === '#000000' || p.cor === '#808080' ? p.cor : 'outra';
      const mostrar = () => { outra.hidden = saida.value !== 'outra'; };
      saida.addEventListener('change', mostrar); mostrar();
      const nomes = [...u.camadas];
      const linha = el('div', { class: 'pena', 'data-cor': cor },
        el('span', { class: 'amostra', style: `background:${cor}` }), el('span', { class: 'hex', texto: cor }),
        el('span', { class: 'camadas', title: nomes.join(', '), texto: u.n ? `${nomes.slice(0, 3).join(', ')}${nomes.length > 3 ? ` e mais ${nomes.length - 3}` : ''} · ${u.n.toLocaleString('pt-BR')} obj.` : 'não está neste desenho' }),
        esp, el('span', { class: 'saida' }, saida, outra));
      linha._ler = () => {
        const v = { espessura: esp.value === '' ? null : +esp.value, cor: saida.value === '' ? null : saida.value === 'outra' ? outra.value : saida.value };
        return v.espessura == null && !v.cor ? null : v;
      };
      linha._todas = (corSaida, espessura) => {
        if (corSaida !== undefined) { saida.value = corSaida || ''; mostrar(); }
        if (espessura !== undefined) esp.value = espessura == null ? '' : String(espessura);
      };
      return linha;
    });
    const corpo = el('div', { class: 'penas' },
      el('div', { class: 'explica', texto: 'Como as penas (CTB) do AutoCAD: cada cor do desenho sai no papel com a espessura e a cor escolhidas aqui. "A do objeto" usa a espessura da camada ou do próprio objeto. Vale para todas as obras, na impressão e no PDF.' }),
      el('div', { class: 'botoes-folhas' },
        el('button', { type: 'button', texto: 'Todas pretas', onclick: () => linhas.forEach(l => l._todas('#000000')) }),
        el('button', { type: 'button', texto: 'Tudo como no objeto', onclick: () => linhas.forEach(l => l._todas('', null)) })),
      el('div', { class: 'tabela' }, linhas));
    if (await this.dialogo({ titulo: 'Penas de impressão', corpo, ok: 'Gravar' }) !== 'ok') return false;
    const novas = { ...penas };
    for (const l of linhas) { const v = l._ler(); if (v) novas[l.dataset.cor] = v; else delete novas[l.dataset.cor]; }
    try {
      const r = await postar(`${base}/penas`, { penas: novas });
      const n = Object.keys(r.penas || {}).length;
      this.aviso(n ? `Penas gravadas: ${n} cor(es) com pena própria — valem na impressão e no PDF.` : 'Sem penas: tudo sai com a espessura e a cor dos objetos.', 'info');
      return true;
    } catch (e) { this.aviso(`Não foi possível gravar as penas: ${e.message}`, 'erro', 0); return false; }
  }

  /** Imprimir o desenho aberto (que não é das pranchas): a vista da tela ou o desenho inteiro, numa escala 1:n — a
   *  folha mede o trecho ÷ n — ou ajustado ao papel. Com pranchas no projeto, um botão leva ao Imprimir pranchas. */
  async _imprimirEsteDesenho(base, desenhosPranchas) {
    let imps;
    try { imps = await postar(`${base}/impressoras`, {}); } catch (e) { this.aviso(`Não foi possível preparar a impressão: ${e.message}`, 'erro', 0); return; }
    const lista = imps.impressoras || [];
    if (!lista.length) { this.aviso('Nenhuma impressora instalada no Windows: use Arquivo › Exportar › PDF.', 'atencao', 0); return; }
    const ultima = lerUltima();
    const t = this.tela;
    const caixaDaTela = () => { const a = t.paraMundo([0, t.altura]), b = t.paraMundo([t.largura, 0]); return [[a[0], a[1]], [b[0], b[1]]]; };
    const selArea = el('select', { name: 'area' },
      el('option', { value: 'tela', texto: 'A vista da tela (o que aparece agora)' }),
      el('option', { value: 'tudo', texto: 'O desenho inteiro' }));
    selArea.value = ultima.area === 'tudo' ? 'tudo' : 'tela';
    const escala = el('input', { type: 'number', name: 'escala', min: '0.01', step: 'any', value: String(this.doc.escala || 1) });
    const selImp = el('select', { name: 'impressora' }, lista.map(p => el('option', { value: p.nome, texto: p.nome + (p.padrao ? ' (padrão)' : '') })));
    selImp.value = lista.some(p => p.nome === ultima.impressora) ? ultima.impressora : (imps.padrao || lista[0].nome);
    const selPapel = el('select', { name: 'papel' });
    const selAjuste = el('select', { name: 'ajuste' },
      el('option', { value: 'real', texto: 'Na escala (1:n no papel)' }),
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
    const folha = () => {
      const c = selArea.value === 'tudo' ? this.doc.caixa() : caixaDaTela();
      const n = parseFloat(String(escala.value).replace(',', '.'));
      if (!c || !(n > 0)) return null;
      return { caixa: c, escala: n, largura: (c[1][0] - c[0][0]) / n, altura: (c[1][1] - c[0][1]) / n };
    };
    const atualizar = () => {
      const f = folha();
      if (!f) { resumo.textContent = selArea.value === 'tudo' ? 'O desenho está vazio.' : 'Escreva a escala (1:n).'; return; }
      const p = papeis.find(x => String(x.id) === selPapel.value);
      const tam = `Folha de ${mm(f.largura)} × ${mm(f.altura)} mm (1:${String(f.escala).replace('.', ',')})`;
      if (!p) { resumo.textContent = `${tam}: no papel do tamanho dela, quando a impressora o tem; senão no menor em que ela cabe.`; return; }
      const k = reducao(f, p);
      resumo.textContent = selAjuste.value === 'ajustar'
        ? `${tam}, no ${p.nome}: ${Math.abs(k - 1) < 0.02 ? 'no tamanho real' : `${k < 1 ? 'reduzida' : 'ampliada'} a cerca de ${porcento(k)} — a escala 1:${f.escala} não vale no papel`}.`
        : k < 0.98 ? `${tam}: maior que o ${p.nome}, só o meio dela sai. Use "Ajustar ao papel" ou uma escala maior.` : `${tam}, no ${p.nome}, no meio do papel.`;
    };
    const carregarPapeis = async () => {
      selPapel.replaceChildren(el('option', { value: 'auto', texto: 'carregando os papéis…' }));
      selPapel.disabled = true;
      try {
        const r = await postar(`${base}/papeis`, { impressora: selImp.value });
        papeis = (r.papeis || []).slice().sort((a, b) => ordemDoPapel(a) - ordemDoPapel(b));
      } catch (e) { papeis = []; this.aviso(`A impressora não deu os papéis dela: ${e.message}`, 'atencao'); }
      selPapel.replaceChildren(el('option', { value: 'auto', texto: 'Automático: o tamanho da folha' }),
        ...papeis.map(p => el('option', { value: String(p.id), texto: `${p.nome} — ${mm(p.largura)} × ${mm(p.altura)} mm` })));
      selPapel.disabled = false;
      selPapel.value = selImp.value === ultima.impressora && papeis.some(p => String(p.id) === String(ultima.papel)) ? String(ultima.papel) : 'auto';
      atualizar();
    };
    selImp.addEventListener('change', carregarPapeis);
    for (const c of [selPapel, selAjuste, selArea]) c.addEventListener('change', atualizar);
    escala.addEventListener('input', atualizar);
    let irPranchas = false;
    const corpo = el('div', { class: 'impressao' },
      el('div', { class: 'explica', texto: `"${this.doc.nome || this.nomeDesenho}" não é um desenho das pranchas: sai uma folha com o trecho escolhido.` }),
      el('div', { class: 'linha' }, el('label', {}, 'O que imprimir', selArea), el('label', { style: 'flex: 0 0 130px' }, 'Escala 1:', escala)),
      el('label', {}, 'Impressora', selImp),
      el('div', { class: 'linha' }, el('label', {}, 'Papel', selPapel), el('label', {}, 'Tamanho', selAjuste)),
      el('div', { class: 'linha' }, el('label', {}, 'Cor', selCor), el('label', { style: 'flex: 0 0 90px' }, 'Cópias', copias)),
      resumo,
      el('div', { class: 'botoes-folhas' },
        el('button', { type: 'button', texto: 'Penas de impressão…', title: 'A espessura e a cor de cada cor do desenho no papel (o CTB do AutoCAD)',
          onclick: () => { irPenas = true; document.getElementById('dialogo-cancelar').click(); } }),
        desenhosPranchas.length ? el('button', { type: 'button', texto: 'Imprimir as pranchas do projeto…',
          onclick: () => { irPranchas = true; document.getElementById('dialogo-cancelar').click(); } }) : null));
    let irPenas = false;
    atualizar();
    carregarPapeis();
    semEnterNosCampos(corpo);
    const r = await this.dialogo({ titulo: 'Imprimir este desenho', corpo, ok: 'Imprimir' });
    if (irPranchas) return this.dialogoImprimir(true);
    if (irPenas) { if (await this.dialogoPenas()) return this._imprimirEsteDesenho(base, desenhosPranchas); return; }
    if (r !== 'ok') return;
    const f = folha();
    if (!f) { this.aviso('Nada para imprimir: o desenho está vazio ou a escala está em branco.', 'atencao'); return; }
    const pedido = {
      desenhos: [], area: { desenho: this.nomeDesenho, caixa: f.caixa, escala: f.escala }, desenho_atual: this.doc.paraJSON(),
      impressora: selImp.value, papel: selPapel.value === 'auto' ? null : Number(selPapel.value), ajuste: selAjuste.value, cor: selCor.value,
      copias: Math.max(1, Math.min(99, parseInt(copias.value, 10) || 1)),
    };
    gravarUltima({ ...lerUltima(), impressora: pedido.impressora, papel: pedido.papel, ajuste: pedido.ajuste, cor: pedido.cor, area: selArea.value });
    this.dica(`Imprimindo "${this.doc.nome || this.nomeDesenho}" em ${pedido.impressora}…`);
    try {
      const res = await postar(`${base}/imprimir`, pedido);
      const a = res.arquivo;
      const papeisUsados = [...new Set((res.folhas || []).map(x => x.papel))].join(', ');
      this.aviso(el('span', {}, `A folha ${a ? 'foi gravada em PDF pela' : 'foi enviada para'} ${res.impressora}${papeisUsados ? ` (${papeisUsados})` : ''}`,
        a ? ': ' : '.', a ? el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: a.nome || 'abrir' }) : null,
        ...(res.avisos || []).length ? [el('br'), (res.avisos || []).join(' · ')] : []), (res.avisos || []).length ? 'atencao' : 'info', a || (res.avisos || []).length ? 0 : 12000);
      this.dica(a ? 'Impressão gravada em PDF (pasta pranchas/ do projeto).' : 'Impressão enviada: acompanhe na fila da impressora do Windows.');
    } catch (e) { this.dica(''); this._avisoDeEmissao(e, 'Não foi possível imprimir'); }
  }
}
