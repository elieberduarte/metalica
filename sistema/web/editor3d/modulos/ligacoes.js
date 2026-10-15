// Métodos do editor 3D: as ligações da biblioteca aplicadas no modelo (F13 da análise de 14/10/2026).
//
// A tela /ligacoes calcula 23 ligações pela NBR, mas não punha nada no 3D. Aqui o usuário escolhe as barras, o tipo e
// os parâmetros, e o servidor (nucleo3d/ligacoes3d.py) devolve as peças no lugar — placa de base com chumbadores, chapa
// de topo com os parafusos, chapas do topo do pilar —, com marca, conjunto e solda, e a barra cortada ou encurtada.
//
// Decisão do usuário (14/10): a ligação continua paramétrica. Cada peça gerada leva `atributos.ligacao` (id, tipo,
// parâmetros, barras, os campos das barras antes, a geometria delas na hora): o painel edita os parâmetros e refaz, o
// "Apagar ligação" tira tudo e devolve as barras, e quando uma barra da ligação muda (moveu, trocou de perfil) a faixa
// "ligações desatualizadas" oferece refazer todas de uma vez. Uma entrada de desfazer por ação.

import { el, numero } from '../editor.js';
import { clonar, criar } from '../nucleo/documento.js';
import { ComandoAdicionar, ComandoRemover, ComandoAlterar, ComandoComposto } from '../nucleo/comandos.js';

/** Os parâmetros que vêm das barras (não se pedem) e os que o servidor calcula pela seção quando ficam em branco. */
const DAS_BARRAS = new Set(['pilar', 'viga']);
const AUTOMATICOS = new Set(['B', 'L', 'H', 'gab_B', 'gab_L']);

const regDe = (e) => (e && e.atributos && e.atributos.ligacao) || null;

export class MetodosLigacoes {
  async _tiposDeLigacao() {
    if (!this._tiposLig) {
      const r = await fetch('/api/modelo/ligacoes-3d');
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      this._tiposLig = j.tipos || [];
    }
    return this._tiposLig;
  }

  /** O formulário dos parâmetros de um tipo: {corpo, ler()} — `valores` preenche (a ligação aplicada). */
  _formParametros(tipo, valores = {}) {
    const campos = el('div', { class: 'campos' });
    const entradas = [];
    for (const p of tipo.parametros || []) {
      if (DAS_BARRAS.has(p.chave)) continue;
      let i;
      const atual = valores[p.chave];
      if (p.opcoes && p.opcoes.length) {
        i = el('select');
        if (AUTOMATICOS.has(p.chave)) i.append(el('option', { value: '', texto: 'automático' }));
        for (const o of p.opcoes) i.append(el('option', { value: String(o), texto: String(o), selected: String(atual ?? p.padrao) === String(o) }));
      } else {
        i = el('input', { type: typeof p.padrao === 'number' ? 'number' : 'text', step: 'any' });
        if (atual !== undefined && atual !== null && atual !== '') i.value = atual;
        else if (AUTOMATICOS.has(p.chave)) i.placeholder = 'pela seção';
        else i.value = p.padrao ?? '';
      }
      entradas.push([p, i]);
      campos.append(el('label', { html: p.rotulo + (p.unidade ? ` (${p.unidade})` : '') }), i);
    }
    const ler = () => {
      const out = {};
      for (const [p, i] of entradas) {
        const v = String(i.value || '').trim();
        if (!v) continue;
        out[p.chave] = typeof p.padrao === 'number' && isFinite(parseFloat(v.replace(',', '.'))) ? parseFloat(v.replace(',', '.')) : v;
      }
      return out;
    };
    return { corpo: campos, ler };
  }

  /** Editar → Aplicar ligação: o tipo, os parâmetros e as peças no lugar, nas barras selecionadas. */
  async dialogoAplicarLigacao() {
    const barras = this.selecao.entidades.filter(e => e.tipo === 'barra');
    const chapas = this.selecao.entidades.filter(e => e.tipo === 'chapa');
    if (!barras.length && !chapas.length) { this.dica('Selecione as peças da ligação: o pilar (para a base), a viga e o pilar (chapa de topo), a diagonal e o apoio (chapa de nó), a placa (chumbadores)…'); return; }
    let tipos;
    try { tipos = await this._tiposDeLigacao(); } catch (e) { this.aviso(`Não foi possível ler as ligações: ${e.message}`, 'erro', 0); return; }
    const escolha = el('select');
    for (const t of tipos) escolha.append(el('option', { value: t.id, texto: t.nome }));
    const pede = el('p', { class: 'explica' });
    const lugar = el('div');
    let form = null;
    const trocar = () => {
      const t = tipos.find(x => x.id === escolha.value);
      pede.textContent = `Pede: ${t.pede}. ${t.descricao || ''}`;
      form = this._formParametros(t);
      lugar.replaceChildren(form.corpo);
    };
    escolha.addEventListener('change', trocar);
    // sugestão pelo que está selecionado
    const vert = barras.filter(b => Math.abs((b.fim[2] - b.inicio[2]) / (Math.hypot(b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1], b.fim[2] - b.inicio[2]) || 1)) > 0.7);
    const dir = (b) => { const d = [b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1], b.fim[2] - b.inicio[2]];
                         const n = Math.hypot(...d) || 1; return d.map(x => x / n); };
    const paralelas = barras.length === 2 && Math.abs(dir(barras[0]).reduce((s, x, i) => s + x * dir(barras[1])[i], 0)) > 0.999;
    // na mesma reta (a emenda) ou lado a lado (o perfil duplo: as presilhas)
    const afastamento = paralelas ? (() => {
      const d0 = dir(barras[0]), r = [0, 1, 2].map(k => barras[1].inicio[k] - barras[0].inicio[k]);
      const t = r.reduce((s, x, k) => s + x * d0[k], 0);
      return Math.hypot(...r.map((x, k) => x - t * d0[k]));
    })() : Infinity;
    const colineares = paralelas && afastamento < 1;
    const diagonal = (b) => String(b.papel).toLowerCase().startsWith('contravent') || /^L\s|FE RED|TIRANTE/i.test(String(b.perfil));
    if (!barras.length && chapas.length) escolha.value = 'chumbador_gancho';
    else if (barras.length === 2 && barras.some(diagonal) && !barras.every(diagonal)) escolha.value = 'gusset_contravento';
    else if (barras.some(b => ['terça', 'terca', 'longarina'].includes(String(b.papel).toLowerCase()))) escolha.value = 'suporte_terca_cadeirinha';
    else if (barras.length === 2 && vert.length === 1) escolha.value = 'chapa_topo_joelho';
    else if (colineares) escolha.value = 'emenda_banzo';
    else if (paralelas) escolha.value = 'presilhas';
    else if (barras.length === 2 && !vert.length) escolha.value = 'ligacao_flexivel';
    else if (vert.length === barras.length) escolha.value = 'placa_base_rotulada';
    trocar();
    const corpo = el('div', {}, el('div', { class: 'campos' }, el('label', { texto: 'Ligação' }), escolha), pede, lugar,
      el('p', { class: 'explica', texto: 'As peças saem com marca, conjunto e solda; a ligação fica paramétrica: selecione uma peça dela para mudar os parâmetros, refazer ou apagar.' }));
    if (await this.dialogo({ titulo: 'Aplicar ligação', corpo, ok: 'Aplicar' }) !== 'ok') return;
    await this._pedirLigacao({ tipo: escolha.value, ids: [...barras, ...chapas].map(b => b.id), parametros: form.ler() }, 'Aplicar ligação');
  }

  /** Manda o pedido, aplica a resposta num comando só e mostra a verificação. */
  async _pedirLigacao(pedido, rotulo, rota = '/api/modelo/ligacao') {
    let r;
    try {
      this.dica(`${rotulo}…`);
      const resp = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ documento: this.documento.paraJSON(), projeto: this.projeto || null, ...pedido }) });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { this.aviso(`Não foi possível ${rotulo.toLowerCase()}: ${e.message}`, 'erro', 0); return null; }
    const cmd = this._comandoDaLigacao(r, rotulo);
    if (cmd) {
      this._refazendoLigacao = true;
      try { this.executar(cmd); } finally { this._refazendoLigacao = false; }
    }
    const novas = (r.novas || []).map(d => d.id);
    if (novas.length) this.selecao.definir(novas.filter(id => this.documento.get(id)));
    this._resumoDaVerificacao(r.ligacoes || [], rotulo);
    this._conferirLigacoes();
    return r;
  }

  _comandoDaLigacao(r, rotulo) {
    const partes = [];
    const remover = (r.remover || []).filter(id => this.documento.get(id));
    if (remover.length) partes.push(new ComandoRemover(remover));
    const alt = {};
    for (const [id, campos] of Object.entries(r.alterar || {})) if (this.documento.get(id)) alt[id] = clonar(campos);
    if (Object.keys(alt).length) partes.push(new ComandoAlterar(alt));
    const novas = (r.novas || []).map(d => criar(d));
    if (novas.length) partes.push(new ComandoAdicionar(novas));
    return partes.length ? new ComandoComposto(partes, rotulo) : null;
  }

  _resumoDaVerificacao(ligs, rotulo) {
    if (!ligs.length) return;
    const linhas = ligs.map(l => {
      const v = l.verificacao;
      const nome = (this._tiposLig || []).find(t => t.id === l.tipo)?.nome || l.tipo;
      let txt = nome;
      if (v && typeof v.razao === 'number') txt += `: aproveitamento ${numero(v.razao, 2)} — ${v.ok ? 'passa' : 'NÃO PASSA'} (esforços: ${l.origem_esforcos || 'padrão da biblioteca'})`;
      else if (v && v.erro) txt += `: sem verificação (${v.erro})`;
      if ((l.avisos || []).length) txt += ` · ${l.avisos.join('; ')}`;
      return txt;
    });
    const algumFalha = ligs.some(l => l.verificacao && l.verificacao.ok === false) || ligs.some(l => (l.avisos || []).length);
    this.aviso(`${rotulo} — ${ligs.length} ligação(ões). ${linhas.slice(0, 3).join(' | ')}${linhas.length > 3 ? ' …' : ''}`,
      algumFalha ? 'atencao' : 'info', algumFalha ? 0 : 10000);
  }

  /** Refaz a ligação `lid` com `parametros` (os que mudaram). */
  refazerLigacao(lid, parametros = {}) {
    const e = [...this.documento.entidades.values()].find(x => regDe(x)?.id === lid);
    if (!e) return null;
    return this._pedirLigacao({ tipo: regDe(e).tipo, ids: [], ligacao: lid, parametros }, 'Refazer ligação');
  }

  apagarLigacao(lid) {
    return this._pedirLigacao({ ligacao: lid }, 'Apagar ligação', '/api/modelo/ligacao/remover');
  }

  selecionarLigacao(lid) {
    const ids = [...this.documento.entidades.values()].filter(x => regDe(x)?.id === lid).map(x => x.id);
    if (ids.length) this.selecao.definir(ids);
  }

  // ---------------------------------------------------------------- ligações desatualizadas

  /** As ligações cujas barras mudaram (pontas, perfil, rotação) ou sumiram desde que foram feitas. */
  ligacoesDesatualizadas() {
    const vistas = new Map();
    for (const e of this.documento.entidades.values()) {
      const reg = regDe(e);
      if (!reg || vistas.has(reg.id)) continue;
      vistas.set(reg.id, reg);
    }
    const fora = [];
    const perto = (a, b) => Math.abs(a - b) < 0.25;
    for (const reg of vistas.values()) {
      const geo = reg.geometria || {};
      let mudou = false, sumiu = false;
      for (const bid of reg.pecas || []) {
        const b = this.documento.get(bid);
        if (!b) { sumiu = true; continue; }
        const g = geo[bid];
        if (!g) continue;
        const [i, f, perfil, rot] = g;
        // a chapa (os chumbadores): a origem, o eixo x × 1000 e a espessura, como nucleo3d/ligacoes3d.assinatura
        const ehChapa = b.tipo === 'chapa';
        const pi = ehChapa ? b.origem : b.inicio;
        const pf = ehChapa ? b.eixo_x.map(v => v * 1000) : b.fim;
        const pp = ehChapa ? String(Number(b.espessura || 0)) : String(b.perfil);
        const pr = ehChapa ? 0 : Number(b.rotacao || 0);
        if (!(i.every((x, k) => perto(x, pi[k])) && f.every((x, k) => perto(x, pf[k]))) || pp !== perfil || !perto(pr, rot)) mudou = true;
      }
      if (mudou || sumiu) fora.push({ id: reg.id, tipo: reg.tipo, sumiu });
    }
    return fora;
  }

  _agendarConferenciaDasLigacoes() {
    if (this._refazendoLigacao) return;
    clearTimeout(this._timerLigacoes);
    this._timerLigacoes = setTimeout(() => this._conferirLigacoes(), 600);
  }

  _conferirLigacoes() {
    let lista = [];
    try { lista = this.ligacoesDesatualizadas(); } catch (e) { console.error('conferência das ligações:', e); }
    if (!lista.length) { if (this._faixaLigacoes) { this._faixaLigacoes.remove(); this._faixaLigacoes = null; } return; }
    const orfas = lista.filter(l => l.sumiu).length;
    const texto = `${lista.length} ligação(ões) com barra que mudou${orfas ? ` (${orfas} com barra apagada)` : ''}: as peças estão no lugar antigo.`;
    if (this._faixaLigacoes) { this._faixaLigacoes.querySelector('span').textContent = texto; return; }
    const botao = el('button', { texto: 'Refazer as ligações', title: 'Refaz cada ligação nas barras como estão agora; a de barra apagada sai' });
    botao.style.cssText = 'background:#fff;color:#1e40af;border:0;border-radius:4px;padding:4px 10px;font-weight:600;cursor:pointer';
    botao.addEventListener('click', () => this.refazerLigacoesDesatualizadas());
    const f = el('div', { class: 'faixa-ligacoes' }, el('span', { texto }), botao);
    f.style.cssText = 'position:fixed;left:50%;top:104px;transform:translateX(-50%);z-index:50;display:flex;gap:12px;' +
      'align-items:center;max-width:80vw;background:#1d4ed8;color:#fff;padding:6px 12px;border-radius:6px;' +
      'font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.25)';
    document.body.append(f);
    this._faixaLigacoes = f;
  }

  async refazerLigacoesDesatualizadas() {
    const lista = this.ligacoesDesatualizadas();
    for (const l of lista) {
      if (l.sumiu) await this.apagarLigacao(l.id);
      else await this.refazerLigacao(l.id);
    }
    this._conferirLigacoes();
  }

  // ---------------------------------------------------------------- painel

  /** O grupo "Ligação" no painel: o tipo, os parâmetros editáveis (refaz ao mudar) e os botões. */
  _painelLigacao(raiz, ents) {
    const regs = new Map();
    for (const e of ents) { const r = regDe(e); if (r) regs.set(r.id, r); }
    if (regs.size !== 1) return;
    const reg = [...regs.values()][0];
    const g = this._grupo(raiz, 'Ligação');
    const tipos = this._tiposLig || [];
    const tipo = tipos.find(t => t.id === reg.tipo);
    g.append(el('label', { texto: 'Tipo' }), el('span', { class: 'valor', texto: tipo ? tipo.nome : reg.tipo }));
    if (tipo) {
      const form = this._formParametros(tipo, reg.parametros || {});
      for (const i of form.corpo.querySelectorAll('input, select')) {
        i.addEventListener('change', () => {
          const novos = form.ler();
          const mudou = {};
          for (const [k, v] of Object.entries(novos)) if (String((reg.parametros || {})[k]) !== String(v)) mudou[k] = v;
          if (Object.keys(mudou).length) this.refazerLigacao(reg.id, mudou);
        });
      }
      g.append(...form.corpo.childNodes);
    } else {
      this._tiposDeLigacao().then(() => this._agendarPaineis('props')).catch(() => {});
    }
    const botoes = el('div', { class: 'acoes-painel', style: 'grid-column:1/-1' });
    const botao = (texto, fn, titulo) => botoes.append(el('button', { type: 'button', class: 'mini', texto, title: titulo, onclick: fn }));
    botao('Selecionar a ligação', () => this.selecionarLigacao(reg.id), 'Todas as peças desta ligação');
    botao('Refazer', () => this.refazerLigacao(reg.id), 'Refaz as peças nas barras como estão agora');
    botao('Apagar ligação', () => this.apagarLigacao(reg.id), 'Tira todas as peças da ligação e devolve as barras como eram');
    g.append(botoes);
  }
}
