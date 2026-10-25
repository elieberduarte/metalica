// Os blocos do CAD 2D (usuário, 24/10: "Biblioteca da empresa" e "Como no AutoCAD"). A inserção é a entidade `bloco`
// (nucleo/desenho2d.js filhosDoBloco); a definição fica em `doc.metadados.blocos[nome]` ({entidades, …}, no referencial
// do bloco, o ponto de base na origem) e, marcada, na biblioteca da empresa (nucleo2d/blocos.py, rota
// /api/projetos/<s>/blocos). B cria, I insere, BEDIT (ou o duplo clique) edita — ao concluir, todas as inserções mudam —,
// X explode. O DXF sai com BLOCK/INSERT (nucleo2d/dxf_cad.py).

import { criar, clonar, transladar, transformar, filhosDoBloco, transformacaoDoBloco } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoRemover, ComandoComposto } from './nucleo/comandos.js';

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

/** A entidade como vai na definição: sem id, no referencial do bloco. */
const paraDefinicao = (e) => { const r = JSON.parse(JSON.stringify(e)); delete r.id; if (r.atributos) { delete r.atributos.bloco_edicao; } return r; };
/** Os nomes dos blocos usados pelas entidades (e os de dentro deles). */
export function blocosUsados(ents, defs) {
  const nomes = new Set(), fila = ents.filter(e => e.tipo === 'bloco').map(e => e.nome);
  while (fila.length) {
    const n = fila.pop();
    if (nomes.has(n)) continue;
    nomes.add(n);
    for (const r of ((defs || {})[n] || {}).entidades || []) if (r.tipo === 'bloco') fila.push(r.nome);
  }
  return [...nomes];
}

export class MetodosBlocosCAD {
  /** As definições do desenho (metadados.blocos). */
  _blocos() { const m = this.doc.metadados || (this.doc.metadados = {}); return m.blocos || (m.blocos = {}); }
  _rotaBlocos() { return `/api/projetos/${encodeURIComponent(this.projeto || '_')}/blocos`; }
  async _bibliotecaDeBlocos() { try { return (await chamar(this._rotaBlocos())).blocos || {}; } catch { return {}; } }
  /** As inserções do bloco `nome` neste desenho. */
  _insercoesDe(nome) { return [...this.doc.entidades.values()].filter(e => e.tipo === 'bloco' && e.nome === nome); }
  /** A definição mudou: as inserções (e o índice espacial delas) são refeitas, e o desenho fica para gravar. */
  _blocosMudaram(nome) {
    const ids = this._insercoesDe(nome).map(e => e.id);
    this.doc.notificar(ids, 'tudo');
    this._agendarAutosave();
    this.tela.pedirQuadro();
    return ids.length;
  }

  /** B: o bloco com as entidades `ids`, o ponto de base `base`. */
  async criarBloco(ids, base) {
    const ents = ids.map(id => this.doc.get(id)).filter(Boolean);
    if (!ents.length) return null;
    const defs = this._blocos();
    let n = Object.keys(defs).length + 1;
    while (defs[`BLOCO-${n}`]) n++;
    const nome = el('input', { type: 'text', 'data-campo': 'nome', value: `BLOCO-${n}`, style: 'width:100%' });
    const descricao = el('input', { type: 'text', 'data-campo': 'descricao', placeholder: 'para que serve (aparece na lista do Inserir)', style: 'width:100%' });
    const bib = el('input', { type: 'checkbox', 'data-campo': 'biblioteca', checked: 'checked' });
    const trocar = el('input', { type: 'checkbox', 'data-campo': 'trocar', checked: 'checked' });
    const corpo = el('div', { style: 'min-width:420px' },
      el('div', { class: 'explica', texto: `${ents.length} objeto(s); o ponto de base em x ${Math.round(base[0])} y ${Math.round(base[1])}.` }),
      el('label', {}, 'Nome ', nome), el('label', {}, 'Descrição ', descricao),
      el('label', { style: 'display:block;margin-top:6px' }, bib, ' Guardar na biblioteca da empresa (vale em todas as obras)'),
      el('label', { style: 'display:block' }, trocar, ' Trocar a seleção pelo bloco'));
    if (await this.dialogo({ titulo: 'Criar bloco', corpo, ok: 'Criar' }) !== 'ok') return null;
    const nm = nome.value.trim();
    if (!nm) { this.aviso('Dê um nome ao bloco.', 'atencao'); return null; }
    const biblioteca = bib.checked ? await this._bibliotecaDeBlocos() : {};
    if (defs[nm] || biblioteca[nm]) {
      const n = this._insercoesDe(nm).length;
      const aviso = el('div', { texto: `O bloco "${nm}" já existe${defs[nm] ? ` neste desenho (${n} inserção(ões))` : ''}${biblioteca[nm] ? ' na biblioteca' : ''}. Redefinir: todas as inserções mudam.` });
      if (await this.dialogo({ titulo: 'Redefinir o bloco?', corpo: aviso, ok: 'Redefinir' }) !== 'ok') return null;
    }
    const def = { entidades: ents.map(e => paraDefinicao(transladar(e, [-base[0], -base[1]]))), origem: this.nomeDesenho || '',
      escala_desenho: this.doc.escala || 1, descricao: descricao.value.trim() || undefined, biblioteca: bib.checked || undefined };
    defs[nm] = def;
    if (bib.checked) {
      try { await chamar(this._rotaBlocos(), { acao: 'gravar', nome: nm, definicao: def }); }
      catch (e) { this.aviso('O bloco ficou neste desenho, mas não foi para a biblioteca: ' + e.message, 'atencao', 0); }
    }
    const mudaram = this._blocosMudaram(nm);
    if (trocar.checked) {
      const ins = criar({ tipo: 'bloco', nome: nm, posicao: [base[0], base[1]], camada: this.camadaAtiva });
      this.executar(new ComandoComposto([new ComandoRemover(ents.map(e => e.id)), new ComandoAdicionar([ins])], `Criar o bloco ${nm}`));
      this.selecionar([ins.id]);
    }
    this.aviso(`Bloco "${nm}" criado (${ents.length} objeto(s))${bib.checked ? ' e guardado na biblioteca da empresa' : ''}${mudaram ? ` · ${mudaram} inserção(ões) atualizada(s)` : ''}. I insere.`, 'info', 8000);
    return nm;
  }

  /** I: a lista dos blocos (os deste desenho e os da biblioteca); devolve o nome escolhido (a definição já no desenho). */
  async escolherBloco() {
    const defs = this._blocos();
    const bib = await this._bibliotecaDeBlocos();
    const nomes = [...new Set([...Object.keys(defs), ...Object.keys(bib)])].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    if (!nomes.length) { this.aviso('Ainda não há blocos: selecione o desenho e B (Criar bloco).', 'atencao'); return null; }
    let escolhido = nomes[0];
    const atualizar = el('input', { type: 'checkbox', 'data-campo': 'atualizar' });
    const linhaAtualizar = el('label', { style: 'display:block;margin-top:6px' }, atualizar, ' Usar a versão da biblioteca (as inserções deste desenho mudam)');
    const lista = el('div', { class: 'lista-opcoes', style: 'max-height:40vh;overflow:auto;min-width:440px' });
    const pintar = () => {
      lista.replaceChildren(...nomes.map(n => {
        const d = defs[n] || bib[n];
        const onde = defs[n] && bib[n] ? 'neste desenho e na biblioteca' : defs[n] ? 'neste desenho' : 'biblioteca';
        const r = el('input', { type: 'radio', name: 'bloco', value: n, 'data-bloco': n, checked: n === escolhido ? 'checked' : undefined });
        r.addEventListener('change', () => { escolhido = n; linhaAtualizar.hidden = !(defs[n] && bib[n] && JSON.stringify(defs[n].entidades) !== JSON.stringify(bib[n].entidades)); });
        const tirar = bib[n] ? el('button', { type: 'button', title: 'Tirar da biblioteca (os desenhos que já usam ficam com a cópia deles)', onclick: async (ev) => {
          ev.preventDefault();
          await chamar(this._rotaBlocos(), { acao: 'excluir', nome: n }).catch(() => {});
          delete bib[n];
          if (!defs[n]) nomes.splice(nomes.indexOf(n), 1);
          pintar();
        } }, 'Tirar da biblioteca') : null;
        return el('label', { class: 'linha', style: 'display:flex;gap:8px;align-items:center' }, r, el('b', { texto: n }),
          el('small', { texto: `${(d.entidades || []).length} objeto(s) · ${onde}${d.descricao ? ' · ' + d.descricao : ''}${defs[n] ? ` · ${this._insercoesDe(n).length} inserção(ões)` : ''}` }), tirar);
      }));
      linhaAtualizar.hidden = !(defs[escolhido] && bib[escolhido] && JSON.stringify(defs[escolhido].entidades) !== JSON.stringify(bib[escolhido].entidades));
    };
    pintar();
    if (await this.dialogo({ titulo: 'Inserir bloco', corpo: el('div', {}, lista, linhaAtualizar), ok: 'Inserir' }) !== 'ok') return null;
    if (!defs[escolhido] || (atualizar.checked && bib[escolhido])) {
      defs[escolhido] = JSON.parse(JSON.stringify(bib[escolhido]));
      defs[escolhido].biblioteca = true;
      this._blocosMudaram(escolhido);
    }
    return escolhido;
  }

  /** BEDIT (ou o duplo clique na inserção): a inserção vira as entidades dela, soltas para editar; Concluir redefine o
   *  bloco (todas as inserções mudam, e a biblioteca, se ele é de lá); Cancelar volta a inserção como estava. */
  editarBloco(e) {
    if (!e || e.tipo !== 'bloco') { this.aviso('Selecione uma inserção de bloco para editar (BEDIT).', 'atencao'); return; }
    if (this._edicaoDoBloco) { this.aviso(`Termine antes a edição do bloco "${this._edicaoDoBloco.nome}".`, 'atencao'); return; }
    const filhos = filhosDoBloco(e).map(f => criar({ ...clonar(f), id: undefined, atributos: { ...(f.atributos || {}), bloco_edicao: e.nome } }));
    this._edicaoDoBloco = { nome: e.nome, insercao: clonar(e), antes: new Set(this.doc.entidades.keys()) };
    this.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar(filhos)], `Editar o bloco ${e.nome}`));
    this.selecionar([]);
    const faixa = el('span', {}, `Editando o bloco "${e.nome}": mude, acrescente ou apague o que quiser `,
      el('button', { type: 'button', 'data-acao-bloco': 'concluir', onclick: () => this.concluirEdicaoDoBloco(true) }, 'Concluir (o bloco muda em todas as inserções)'), ' ',
      el('button', { type: 'button', 'data-acao-bloco': 'cancelar', onclick: () => this.concluirEdicaoDoBloco(false) }, 'Cancelar'));
    this.aviso(faixa, 'atencao', 0);
    this._edicaoDoBloco.faixa = faixa;
  }

  editarBlocoSelecionado() {
    const e = [...this.tela.selecao].map(id => this.doc.get(id)).find(x => x && x.tipo === 'bloco');
    this.editarBloco(e);
  }

  /** Fecha a edição do bloco: `gravar` redefine; senão volta como estava. */
  async concluirEdicaoDoBloco(gravar) {
    const s = this._edicaoDoBloco;
    if (!s) return;
    this._edicaoDoBloco = null;
    s.faixa.closest('.aviso')?.remove();
    const ents = [...this.doc.entidades.values()].filter(x => (x.atributos || {}).bloco_edicao === s.nome || !s.antes.has(x.id));
    const ins = criar({ ...s.insercao });
    if (gravar) {
      if (!ents.length) { this.aviso('O bloco ficou vazio: nada foi redefinido.', 'atencao'); gravar = false; }
    }
    if (gravar) {
      // de volta ao referencial do bloco (a conta inversa da inserção)
      const e = s.insercao, [sx, sy] = e.escala || [1, 1], t = (e.angulo || 0) * Math.PI / 180, c = Math.cos(t), sn = Math.sin(t);
      const finv = (q) => { const dx = q[0] - e.posicao[0], dy = q[1] - e.posicao[1]; return [(dx * c + dy * sn) / sx, (-dx * sn + dy * c) / sy]; };
      const fAngInv = (a) => { const r = ((a || 0) - (e.angulo || 0)) * Math.PI / 180; return ((Math.atan2(Math.sin(r) / sy, Math.cos(r) / sx) * 180 / Math.PI) % 360 + 360) % 360; };
      const { k, espelha } = transformacaoDoBloco(e);
      const defs = this._blocos();
      const velha = defs[s.nome] || {};
      const nova = { ...velha, entidades: ents.map(x => {
        const n = transformar(x, finv, fAngInv, 1 / k, espelha);
        if (n.tipo === 'texto') { n.altura = x.altura / k; n.angulo = espelha ? ((((x.angulo || 0) - (e.angulo || 0)) % 360) + 360) % 360 : fAngInv(x.angulo); }
        if (n.tipo === 'chamada' || n.tipo === 'cota' || n.tipo === 'cota_especial') n.altura = x.altura / k;
        if (n.tipo === 'hachura') n.angulo = ((((x.angulo || 0) - (e.angulo || 0)) % 360) + 360) % 360;
        return paraDefinicao(n);
      }) };
      defs[s.nome] = nova;
      if (nova.biblioteca) {
        try { await chamar(this._rotaBlocos(), { acao: 'gravar', nome: s.nome, definicao: nova }); }
        catch (er) { this.aviso('O bloco mudou neste desenho, mas não na biblioteca: ' + er.message, 'atencao', 0); }
      }
    }
    this.executar(new ComandoComposto([new ComandoRemover(ents.map(x => x.id)), new ComandoAdicionar([ins])], gravar ? `Redefinir o bloco ${s.nome}` : `Cancelar a edição do bloco ${s.nome}`));
    const n = this._blocosMudaram(s.nome);
    this.selecionar([ins.id]);
    this.aviso(gravar ? `Bloco "${s.nome}" redefinido: ${n} inserção(ões) neste desenho${(this._blocos()[s.nome] || {}).biblioteca ? ' e a biblioteca da empresa' : ''}.` : `Edição do bloco "${s.nome}" cancelada.`, 'info', 8000);
  }
}
