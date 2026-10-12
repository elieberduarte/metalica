// Métodos do editor 3D: barras e perfis de um bloco treliçado (tesoura, transição, painel…), em qualquer modelo.
//
// Pedido do usuário (12/10): o painel "Perfis…" da Montagem (web/cad/perfis_tesoura.js) só alcança as tesouras lançadas
// pela Montagem por eixos; no modelo montado pela planta (o Posto CB) ou importado não havia onde arrumar à mão a posição
// dos banzos e o perfil das barras. Com um bloco selecionado, o painel do bloco tem "Barras e perfis…": a elevação dele
// desenhada (cada barra na cor do perfil), a escolha por clique ou por função (banzo de cima, de baixo, montantes,
// diagonais, um perfil da legenda) e, para o que está escolhido: trocar o perfil, virar a boca (180°) ou girar 90° —
// só neste bloco ou em todos os blocos do mesmo nome (TESOURA 16 inteira), com a barra correspondente achada pela posição
// na elevação (também nas cópias espelhadas). Um Ctrl+Z desfaz tudo.
//
// As duas cantoneiras de um par (a alma dupla) são uma posição só; as presilhas não aparecem nem mudam.

import { el } from '../editor.js';
import { pecaDe, eixoDoSolido } from '../nucleo/esqueleto.js';
import { ComandoAlterar } from '../nucleo/comandos.js';

const SVG = 'http://www.w3.org/2000/svg';
const CORES = ['#2f80ed', '#eb5757', '#27ae60', '#f2994a', '#9b51e0', '#00a3a3', '#d4a017', '#e84393', '#6d7f8f', '#8d6e63'];
const CASA = 60;             // mm: a barra correspondente na outra cópia fica a até isso na elevação

function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

function segmentosDe(ent) {
  if (ent.tipo === 'barra' && ent.inicio && ent.fim) return [[ent.inicio, ent.fim]];
  if (ent.tipo === 'solido') {
    const pts = eixoDoSolido(ent);
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) out.push([pts[i], pts[i + 1]]);
    return out;
  }
  return [];
}

/** O nome do tipo do bloco: "TESOURA 16" (a planta de origem), sem o número da cópia. */
function tipoDoBloco(ent) {
  const o = (ent && ent.atributos && ent.atributos.origem) || {};
  return String(o.planta || o.corte || pecaDe(ent) || '').split('#')[0].replace(/ \(tesoura de cima\)$/, '').trim();
}

export class MetodosBarrasDoBloco {
  /**
   * O referencial da elevação do bloco: s ao longo dele (da ponta 1 à 2, em planta) e h na altura; a treliça deitada
   * (altura quase nula) fica em planta, h atravessado. Devolve {u, n, o, deitada, L} ou null.
   */
  _referencialDoBloco(ents) {
    const pts = [];
    const banzos = ents.filter(e => e.papel === 'banzo' || e.tipo === 'solido');
    for (const e of (banzos.length ? banzos : ents)) for (const [a, b] of segmentosDe(e)) pts.push(a, b);
    if (pts.length < 2) return null;
    let e1 = pts[0], e2 = pts[1], dmax = -1;
    for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
      const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
      if (d > dmax) { dmax = d; e1 = pts[i]; e2 = pts[j]; }
    }
    if (dmax < 1) return null;
    const u = [(e2[0] - e1[0]) / dmax, (e2[1] - e1[1]) / dmax];
    const zs = ents.flatMap(e => segmentosDe(e).flatMap(([a, b]) => [a[2], b[2]]));
    const deitada = Math.max(...zs) - Math.min(...zs) < 150;
    return { u, n: [-u[1], u[0]], o: [e1[0], e1[1], Math.min(...zs)], deitada, L: dmax };
  }

  _naElevacao(ref, p) {
    const dx = p[0] - ref.o[0], dy = p[1] - ref.o[1];
    const s = dx * ref.u[0] + dy * ref.u[1];
    const h = ref.deitada ? dx * ref.n[0] + dy * ref.n[1] : p[2] - ref.o[2];
    return [s, h];
  }

  /**
   * As posições do bloco: cada barra (as duas cantoneiras do par juntas) com a linha dela na elevação, a função e os
   * ids. Os sólidos (banzo calandrado) entram desenhados, mas não se alteram por aqui.
   */
  _posicoesDoBloco(ids) {
    const doc = this.documento;
    const ents = ids.map(i => doc.get(i)).filter(e => e && e.papel !== 'presilha');
    const ref = this._referencialDoBloco(ents);
    if (!ref) return null;
    const porChave = new Map();
    let hmin = Infinity, hmax = -Infinity;
    for (const e of ents) {
      for (const [a, b] of segmentosDe(e)) {
        let p = this._naElevacao(ref, a), q = this._naElevacao(ref, b);
        if (p[0] > q[0] || (p[0] === q[0] && p[1] > q[1])) [p, q] = [q, p];
        hmin = Math.min(hmin, p[1], q[1]); hmax = Math.max(hmax, p[1], q[1]);
        if (e.tipo !== 'barra') {
          porChave.set(`s${e.id}${p}`, { linha: [p, q], ids: [], solido: true, papel: e.papel || 'banzo', perfil: e.nome || '', rotacao: 0 });
          continue;
        }
        const chave = [p[0], p[1], q[0], q[1]].map(v => Math.round(v / 8)).join('|') + '|' + e.papel + '|' + e.perfil;
        if (!porChave.has(chave)) porChave.set(chave, { linha: [p, q], ids: [], papel: e.papel || 'barra', perfil: e.perfil || '', rotacao: e.rotacao || 0 });
        porChave.get(chave).ids.push(e.id);
      }
    }
    const meio = (hmin + hmax) / 2;
    const posicoes = [...porChave.values()];
    for (const pos of posicoes) {
      const hm = (pos.linha[0][1] + pos.linha[1][1]) / 2;
      pos.funcao = pos.papel === 'banzo' ? (hm >= meio ? 'banzo de cima' : 'banzo de baixo') : pos.papel;
    }
    return { ref, posicoes, hmin, hmax };
  }

  /** Os blocos do mesmo tipo (o nome da planta), cada um pelas ids: {peca: ids}. */
  _blocosDoTipo(tipo) {
    const out = new Map();
    for (const e of this.documento.entidades.values()) {
      const p = pecaDe(e);
      if (!p || tipoDoBloco(e) !== tipo) continue;
      if (!out.has(p)) out.set(p, []);
      out.get(p).push(e.id);
    }
    return out;
  }

  /**
   * A posição correspondente a cada uma de `escolhidas` (deste bloco) no bloco `outro`: pela linha na elevação, com s
   * proporcional ao comprimento; a cópia espelhada (o mesmo tipo virado) é a que casa melhor ao contrário.
   */
  _correspondentes(base, escolhidas, outro) {
    const casar = (espelho) => {
      let erro = 0;
      const pares = [];
      for (const pos of escolhidas) {
        const conv = (pt) => {
          let s = pt[0] / base.ref.L * outro.ref.L;
          if (espelho) s = outro.ref.L - s;
          return [s, pt[1] - base.hmin + outro.hmin];
        };
        const a = conv(pos.linha[0]), b = conv(pos.linha[1]);
        let melhor = null, dm = Infinity;
        for (const q of outro.posicoes) {
          if (q.solido || q.papel !== pos.papel) continue;
          const [c, d] = q.linha;
          const dd = Math.min(Math.hypot(a[0] - c[0], a[1] - c[1]) + Math.hypot(b[0] - d[0], b[1] - d[1]),
                              Math.hypot(a[0] - d[0], a[1] - d[1]) + Math.hypot(b[0] - c[0], b[1] - c[1]));
          if (dd < dm) { dm = dd; melhor = q; }
        }
        erro += Math.min(dm, 10 * CASA);
        if (melhor && dm <= 2 * CASA) pares.push(melhor);
      }
      return { erro, pares };
    };
    const direto = casar(false), espelhado = casar(true);
    return (espelhado.erro < direto.erro ? espelhado : direto).pares;
  }

  abrirBarrasDoBloco(peca, ids) {
    this._fecharBarrasDoBloco();
    const doc = this.documento;
    const ent0 = doc.get(ids[0]);
    const tipo = tipoDoBloco(ent0) || peca;
    const estado = { peca, ids, tipo, escolha: new Set(), escopo: 'todas' };
    this._barrasBloco = estado;
    this._desenharBarrasDoBloco();
  }

  _fecharBarrasDoBloco() {
    if (this._painelBarras) { this._painelBarras.remove(); this._painelBarras = null; }
    this._barrasBloco = null;
  }

  _desenharBarrasDoBloco() {
    const est = this._barrasBloco;
    if (!est) return;
    const dados = this._posicoesDoBloco(est.ids);
    if (this._painelBarras) this._painelBarras.remove();
    if (!dados) { this._painelBarras = null; return; }
    est.dados = dados;
    const { ref, posicoes, hmin, hmax } = dados;
    // as escolhas sobrevivem ao redesenho pela linha (as posições são refeitas a cada mudança)
    const chaveDe = (pos) => pos.linha.flat().map(v => Math.round(v)).join('|') + pos.papel;
    const escolhidas = posicoes.filter(p => est.escolha.has(chaveDe(p)));

    // as cores por perfil, na ordem do mais usado
    const contagem = new Map();
    for (const p of posicoes) contagem.set(p.perfil, (contagem.get(p.perfil) || 0) + 1);
    const perfis = [...contagem.entries()].sort((a, b) => b[1] - a[1]).map(([n]) => n);
    const corDe = (perfil) => CORES[perfis.indexOf(perfil) % CORES.length];

    // ---- a elevação
    const W = 640, H = Math.max(140, Math.min(300, 640 * (hmax - hmin + 400) / (ref.L + 400)));
    const esc = Math.min((W - 30) / (ref.L || 1), (H - 30) / ((hmax - hmin) || 1));
    const X = (s) => 15 + s * esc, Y = (h) => H - 15 - (h - hmin) * esc;
    const desenho = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'barras-elevacao' });
    for (const pos of posicoes) {
      const [[s0, h0], [s1, h1]] = pos.linha;
      const sel = est.escolha.has(chaveDe(pos));
      const g = svg('g', { class: 'barra' + (sel ? ' escolhida' : '') + (pos.solido ? ' solido' : '') });
      const larg = pos.papel === 'banzo' ? 3.2 : 1.8;
      if (sel) g.append(svg('line', { x1: X(s0), y1: Y(h0), x2: X(s1), y2: Y(h1), class: 'halo', 'stroke-width': larg + 5 }));
      g.append(svg('line', { x1: X(s0), y1: Y(h0), x2: X(s1), y2: Y(h1), stroke: corDe(pos.perfil), 'stroke-width': larg }));
      const alvo = svg('line', { x1: X(s0), y1: Y(h0), x2: X(s1), y2: Y(h1), class: 'alvo', 'stroke-width': 9 });
      const titulo = svg('title');
      titulo.textContent = `${pos.funcao} · ${pos.perfil}${pos.ids.length > 1 ? ` (${pos.ids.length} perfis)` : ''} · ${Math.round(Math.hypot(s1 - s0, h1 - h0))} mm`;
      alvo.append(titulo);
      if (!pos.solido) {
        alvo.addEventListener('click', (ev) => {
          const k = chaveDe(pos);
          if (!ev.shiftKey && !ev.ctrlKey) { const tinha = est.escolha.has(k) && est.escolha.size === 1; est.escolha.clear(); if (!tinha) est.escolha.add(k); }
          else if (est.escolha.has(k)) est.escolha.delete(k); else est.escolha.add(k);
          this._desenharBarrasDoBloco();
        });
      }
      g.append(alvo);
      desenho.append(g);
    }

    // ---- escolher por função ou por perfil
    const funcoes = ['banzo de cima', 'banzo de baixo', 'montante', 'diagonal', 'apoio_terca'].filter(f => posicoes.some(p => p.funcao === f && !p.solido));
    const nomesFuncao = { 'banzo de cima': 'Banzo de cima', 'banzo de baixo': 'Banzo de baixo', montante: 'Montantes', diagonal: 'Diagonais', apoio_terca: 'Apoio das terças' };
    const escolherOnde = (f) => {
      est.escolha.clear();
      for (const p of posicoes) if (!p.solido && f(p)) est.escolha.add(chaveDe(p));
      this._desenharBarrasDoBloco();
    };
    const botoesFuncao = el('div', { class: 'barras-funcoes' },
      ...funcoes.map(f => el('button', { type: 'button', texto: nomesFuncao[f], onclick: () => escolherOnde(p => p.funcao === f) })),
      el('button', { type: 'button', texto: 'Todas', onclick: () => escolherOnde(() => true) }),
      el('button', { type: 'button', texto: 'Nenhuma', onclick: () => escolherOnde(() => false) }));
    const legenda = el('div', { class: 'barras-legenda' },
      ...perfis.map(pf => el('button', { type: 'button', class: 'perfil', title: `Escolher as barras em ${pf}`, onclick: () => escolherOnde(p => p.perfil === pf) },
        el('span', { class: 'cor', style: `background:${corDe(pf)}` }), `${pf} (${contagem.get(pf)})`)));

    // ---- o que fazer com as escolhidas
    const blocos = this._blocosDoTipo(est.tipo);
    const nEscolhidas = escolhidas.length;
    const escopo = el('select', { title: 'Onde a mudança vale' },
      el('option', { value: 'todas' }, `em todas as ${est.tipo} (${blocos.size})`),
      el('option', { value: 'esta' }, `só nesta (${est.peca})`));
    escopo.value = blocos.size > 1 ? est.escopo : 'esta';
    escopo.addEventListener('change', () => { est.escopo = escopo.value; });
    const perfilAtual = nEscolhidas && escolhidas.every(p => p.perfil === escolhidas[0].perfil) ? escolhidas[0].perfil : undefined;
    const acoes = el('div', { class: 'barras-acoes' + (nEscolhidas ? '' : ' apagado') },
      el('div', { class: 'linha' }, el('strong', { texto: nEscolhidas ? `${nEscolhidas} barra(s) escolhida(s)` : 'Clique nas barras do desenho (Shift soma) ou escolha por função' })),
      el('div', { class: 'linha' }, el('label', { texto: 'Perfil' }),
        this._buscaPerfil(perfilAtual, (nome) => this._aplicarNasBarras(escolhidas, (e) => ({ perfil: nome, ...(e.nome === e.perfil ? { nome } : {}) }), `Perfil ${nome}`))),
      el('div', { class: 'linha' },
        el('button', { type: 'button', texto: 'Virar a boca (180°)', title: 'Gira a seção 180° no próprio eixo: a boca do U, a aba da cantoneira para o outro lado',
          onclick: () => this._aplicarNasBarras(escolhidas, (e) => ({ rotacao: ((e.rotacao || 0) + 180) % 360 }), 'Virar a boca (180°)') }),
        el('button', { type: 'button', texto: 'Girar 90°', title: 'Gira a seção 90° no próprio eixo (deita ou levanta o perfil)',
          onclick: () => this._aplicarNasBarras(escolhidas, (e) => ({ rotacao: ((e.rotacao || 0) + 90) % 360 }), 'Girar a seção 90°') }),
        escopo));

    const corpo = el('div', { class: 'painel-apoios-corpo' },
      el('p', { class: 'explica', texto: `${posicoes.filter(p => !p.solido).length} posições de barra (o par de cantoneiras conta uma)${ref.deitada ? ' — treliça deitada, vista de cima' : ''}. Cor = perfil.` }),
      desenho, legenda, botoesFuncao, acoes);
    this._painelBarras = el('div', { class: 'painel-apoios painel-barras' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: `Barras e perfis — ${est.peca}` }),
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharBarrasDoBloco() })),
      corpo);
    (this.el.palco || document.body).append(this._painelBarras);
    // as escolhidas em destaque no 3D
    const destaque = escolhidas.flatMap(p => p.ids);
    this._pintandoBloco = true;
    try { this.cena.destacar(destaque.length ? destaque : est.ids); } finally { this._pintandoBloco = false; }
    this._destaqueAtivo = true;
  }

  /** Aplica `campos(e)` nas barras das posições escolhidas — neste bloco ou nos correspondentes de todos do tipo. */
  _aplicarNasBarras(escolhidas, campos, rotulo) {
    const est = this._barrasBloco;
    if (!est || !escolhidas.length) { this.aviso('Escolha antes as barras (clique no desenho ou numa função).', 'atencao'); return; }
    const alvos = new Set(escolhidas.flatMap(p => p.ids));
    let blocosMudados = 1, semPar = 0;
    if (est.escopo === 'todas') {
      for (const [peca, ids] of this._blocosDoTipo(est.tipo)) {
        if (peca === est.peca) continue;
        const outro = this._posicoesDoBloco(ids);
        if (!outro) continue;
        const pares = this._correspondentes(est.dados, escolhidas, outro);
        semPar += escolhidas.length - pares.length;
        if (pares.length) blocosMudados++;
        for (const q of pares) for (const id of q.ids) alvos.add(id);
      }
    }
    const mud = {};
    let bloqueadas = 0;
    for (const id of alvos) {
      const e = this.documento.get(id);
      if (!e || e.tipo !== 'barra') continue;
      if (!this.documento.editavel(e)) { bloqueadas++; continue; }
      mud[id] = campos(e);
    }
    if (!Object.keys(mud).length) { this.aviso('Nada a alterar: as barras estão bloqueadas.', 'atencao'); return; }
    this.executar(new ComandoAlterar(mud, `${rotulo} — ${est.escopo === 'todas' ? `todas as ${est.tipo}` : est.peca}`));
    const partes = [`${Object.keys(mud).length} barra(s) em ${blocosMudados} bloco(s)`];
    if (semPar) partes.push(`${semPar} sem correspondente em alguma cópia (ficaram como estavam)`);
    if (bloqueadas) partes.push(`${bloqueadas} bloqueada(s)`);
    this.aviso(`${rotulo}: ${partes.join('; ')}. Ctrl+Z desfaz.`, semPar ? 'atencao' : 'info', 8000);
    this._desenharBarrasDoBloco();
  }
}
