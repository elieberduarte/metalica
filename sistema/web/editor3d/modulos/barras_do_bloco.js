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
import { baseDaBarra, meioDaBarra } from '../nucleo/documento.js';

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
    // o lado de cada perfil do par em relação ao plano da treliça (−1, +1; 0 no perfil sozinho): é o que a vista da seção
    // escolhe e o que acha o perfil correspondente nas cópias
    const n3 = [ref.n[0], ref.n[1], 0];
    for (const pos of posicoes) {
      if (pos.solido || !pos.ids.length) continue;
      const mids = pos.ids.map(i => meioDaBarra(this.documento.get(i)));
      const c = [0, 1, 2].map(k => mids.reduce((a, m) => a + m[k], 0) / mids.length);
      pos.centro = c;
      pos.lados = mids.map(m => { const d = (m[0] - c[0]) * n3[0] + (m[1] - c[1]) * n3[1]; return Math.abs(d) < 1 ? 0 : Math.sign(d); });
    }
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
    const r = espelhado.erro < direto.erro ? { ...espelhado, espelho: true } : { ...direto, espelho: false };
    this._ultimoEspelho = r.espelho;
    return r.pares;
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
    if (escolhidas.length) corpo.append(this._vistaDaSecao(escolhidas, corDe));
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

  /**
   * A seção da posição escolhida (12/10, croqui do usuário: os perfis vistos de frente, com os eixos e as setas de girar):
   * cada perfil da posição desenhado na seção verdadeira, no giro que tem, olhando ao longo da barra — o plano da treliça
   * na vertical tracejada, o eixo de cada perfil em cruz. O clique num perfil escolhe só ele (uma cantoneira do par);
   * ↺ ↻ giram 90°, ⇄ vira 180° — no escolhido ou nos dois, nas posições escolhidas (e nas cópias, pelo lado do plano).
   */
  _vistaDaSecao(todasEscolhidas, corDe) {
    const est = this._barrasBloco;
    // as escolhidas por configuração (a função, o perfil e quantos perfis a posição tem): os 26 montantes em 2L e os 2 U
    // de ponta da TRANSIÇÃO 16 são seções diferentes — a vista mostra uma de cada vez (a mais numerosa primeiro) e os
    // botões valem só para ela (12/10: "os montantes no 3D estão em 2 cantoneiras e no editor um perfil U")
    const grupos = new Map();
    for (const p of todasEscolhidas) {
      if (p.solido || !p.ids.length) continue;
      const k = `${p.funcao}|${p.perfil}|${p.ids.length}`;
      if (!grupos.has(k)) grupos.set(k, []);
      grupos.get(k).push(p);
    }
    const lista = [...grupos.entries()].sort((a, b) => b[1].length - a[1].length);
    if (!lista.length) return el('div');
    if (!est.grupoSecao || !grupos.has(est.grupoSecao)) est.grupoSecao = lista[0][0];
    const escolhidas = grupos.get(est.grupoSecao);
    const pos = escolhidas[0];
    const ents = pos.ids.map(i => this.documento.get(i)).filter(Boolean);
    if (!ents.length || !pos.centro) return el('div');
    if (est.ladoSecao && !pos.lados.includes(est.ladoSecao)) est.ladoSecao = 0;
    // o referencial da vista, olhando ao longo da barra: x atravessado ao plano da treliça (a normal dele) e y no plano,
    // para cima (no montante em pé, para o lado da ponta 2). O da barra sem giro servia na diagonal e no banzo, mas no
    // montante (barra vertical) o u dela é o −y do mundo, e a seção saía torta em relação ao plano (12/10)
    const t0 = baseDaBarra(ents[0].inicio, ents[0].fim, 0).t;
    const nP = [est.dados.ref.n[0], est.dados.ref.n[1], 0];
    const nt = nP[0] * t0[0] + nP[1] * t0[1];
    let bx = [nP[0] - nt * t0[0], nP[1] - nt * t0[1], -nt * t0[2]];
    const lx = Math.hypot(...bx) || 1;
    bx = bx.map(v => v / lx);
    let by = [t0[1] * bx[2] - t0[2] * bx[1], t0[2] * bx[0] - t0[0] * bx[2], t0[0] * bx[1] - t0[1] * bx[0]];
    const sobe = Math.abs(by[2]) > 0.2 ? by[2] : by[0] * est.dados.ref.u[0] + by[1] * est.dados.ref.u[1];
    if (sobe < 0) by = by.map(v => -v);
    const b0 = { u: bx, v: by };
    const c = pos.centro;
    const no2d = (P) => [P[0] * b0.u[0] + P[1] * b0.u[1] + P[2] * b0.u[2], P[0] * b0.v[0] + P[1] * b0.v[1] + P[2] * b0.v[2]];
    const pts2d = [];
    const contornos = ents.map((e, i) => {
      const base = baseDaBarra(e.inicio, e.fim, e.rotacao || 0);
      const forma = this.cena._secaoDoPerfil(e.perfil);
      const m = meioDaBarra(e);
      const contorno = forma.getPoints(12).map(q => {
        const xy = no2d([0, 1, 2].map(k => m[k] + base.u[k] * q.x + base.v[k] * q.y - c[k]));
        pts2d.push(xy);
        return xy;
      });
      return { e, lado: pos.lados[i], contorno, eixo: no2d([0, 1, 2].map(k => m[k] - c[k])) };
    });
    let R = Math.max(30, ...pts2d.map(([x, y]) => Math.max(Math.abs(x), Math.abs(y)))) * 1.25;
    if (pos.papel !== 'banzo') {
      const bz = (est.dados.posicoes.find(q => q.papel === 'banzo' && !q.solido) || {}).perfil;
      const pbz = bz && this.cena.perfil ? this.cena.perfil(bz) : null;
      if (pbz && pbz.d) R = Math.max(R, (pbz.d / 2) * 1.12);
    }
    const W = 230, esc = (W / 2 - 10) / R, X = (x) => W / 2 + x * esc, Y = (y) => W / 2 - y * esc;
    const vista = svg('svg', { viewBox: `0 0 ${W} ${W}`, class: 'barras-secao' });
    vista.append(svg('line', { x1: X(0), y1: 4, x2: X(0), y2: W - 4, class: 'plano' }));
    const tPlano = svg('text', { x: X(0) + 4, y: 12, class: 'rotulo' });
    tPlano.textContent = 'plano da treliça';
    vista.append(tPlano);
    // na alma: as faces de dentro das abas do U do banzo (paralelas ao plano), onde a cantoneira dupla é soldada
    if (pos.papel !== 'banzo') {
      const banzo = (est.dados.posicoes.find(q => q.papel === 'banzo' && !q.solido) || {}).perfil;
      const pb = banzo && this.cena.perfil ? this.cena.perfil(banzo) : null;
      if (pb && (pb.tipo === 'U' || pb.tipo === 'Ue') && pb.d) {
        const dentro = pb.d / 2 - (pb.tw || 0);
        // a vista mede atravessado ao plano no eixo u da barra; o plano passa pelo centro do par
        for (const sx of [-1, 1]) {
          const x = sx * dentro;
          if (Math.abs(x) * esc > W / 2) continue;
          vista.append(svg('line', { x1: X(x), y1: 18, x2: X(x), y2: W - 4, class: 'aba-banzo' }));
        }
        const tAba = svg('text', { x: 6, y: W - 6, class: 'rotulo' });
        tAba.textContent = `abas do ${banzo} (face de dentro)`;
        vista.append(tAba);
      }
    }
    for (const k of contornos) {
      const sel = est.ladoSecao && k.lado === est.ladoSecao;
      const poly = svg('polygon', { points: k.contorno.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(' '),
        fill: corDe(k.e.perfil), class: 'perfil' + (sel ? ' escolhido' : '') + (est.ladoSecao && !sel ? ' apagado' : '') });
      const t = svg('title');
      t.textContent = `${k.e.perfil} · giro ${Math.round(k.e.rotacao || 0)}°${k.lado ? (k.lado < 0 ? ' · lado −' : ' · lado +') : ''} · clique para escolher só este`;
      poly.append(t);
      poly.addEventListener('click', () => { est.ladoSecao = est.ladoSecao === k.lado ? 0 : k.lado; this._desenharBarrasDoBloco(); });
      vista.append(poly);
      const [ex, ey] = k.eixo;
      vista.append(svg('line', { x1: X(ex) - 9, y1: Y(ey), x2: X(ex) + 9, y2: Y(ey), class: 'eixo' }),
                   svg('line', { x1: X(ex), y1: Y(ey) - 9, x2: X(ex), y2: Y(ey) + 9, class: 'eixo' }));
    }
    const qual = est.ladoSecao ? 'o perfil escolhido' : (ents.length > 1 ? 'os dois perfis' : 'o perfil');
    const girar = (graus, rot) => this._aplicarNasBarras(escolhidas, (e) => ({ rotacao: (((e.rotacao || 0) + graus) % 360 + 360) % 360 }), rot, est.ladoSecao || 0);
    const botoes = el('div', { class: 'secao-botoes' },
      el('button', { type: 'button', texto: '↺ 90°', title: `Gira ${qual} 90° no sentido anti-horário (olhando ao longo da barra)`, onclick: () => girar(90, 'Girar a seção 90° ↺') }),
      el('button', { type: 'button', texto: '↻ 90°', title: `Gira ${qual} 90° no sentido horário`, onclick: () => girar(-90, 'Girar a seção 90° ↻') }),
      el('button', { type: 'button', texto: '⇄ 180°', title: `Vira ${qual} 180° (a boca do U, a aba da cantoneira para o outro lado)`, onclick: () => girar(180, 'Virar a seção 180°') }));
    const nome = (k, ps) => { const [f, perf, n] = k.split('|'); return `${f}: ${+n > 1 ? `${n} × ` : ''}${perf} — ${ps.length}`; };
    const seletor = lista.length > 1
      ? el('div', { class: 'secao-grupos' }, ...lista.map(([k, ps]) => el('button', {
          type: 'button', class: k === est.grupoSecao ? 'on' : '', texto: nome(k, ps),
          title: 'Ver e girar esta configuração (os botões valem só para ela)',
          onclick: () => { est.grupoSecao = k; est.ladoSecao = 0; this._desenharBarrasDoBloco(); } })))
      : null;
    return el('div', { class: 'barras-secao-caixa' },
      el('div', { class: 'secao-titulo', texto: `Seção — ${pos.funcao}: ${ents.length > 1 ? `${ents.length} × ` : ''}${pos.perfil}${escolhidas.length > 1 ? ` (${escolhidas.length} barras iguais; os botões valem para elas)` : ''}` }),
      ...(seletor ? [seletor] : []),
      vista,
      el('div', { class: 'secao-lado' },
        el('p', { class: 'explica', texto: ents.length > 1 ? 'Clique num perfil para girar só ele; clique de novo para voltar aos dois.' : 'Vista ao longo da barra: o tracejado vertical é o plano da treliça; a cruz, o eixo do perfil.' }),
        botoes));
  }

  /** Aplica `campos(e)` nas barras das posições escolhidas — neste bloco ou nos correspondentes de todos do tipo. */
  _aplicarNasBarras(escolhidas, campos, rotulo, lado = 0) {
    const est = this._barrasBloco;
    if (!est || !escolhidas.length) { this.aviso('Escolha antes as barras (clique no desenho ou numa função).', 'atencao'); return; }
    // `lado` (a vista da seção): só o perfil daquele lado do plano em cada posição; 0 = todos
    const doLado = (pos, sinal) => pos.ids.filter((_, i) => !lado || !pos.lados || pos.lados[i] === lado * sinal || pos.lados[i] === 0);
    const alvos = new Set(escolhidas.flatMap(p => doLado(p, 1)));
    let blocosMudados = 1, semPar = 0;
    if (est.escopo === 'todas') {
      for (const [peca, ids] of this._blocosDoTipo(est.tipo)) {
        if (peca === est.peca) continue;
        const outro = this._posicoesDoBloco(ids);
        if (!outro) continue;
        const pares = this._correspondentes(est.dados, escolhidas, outro);
        // na cópia espelhada o lado do plano troca (o comprimento corre ao contrário)
        const sinal = this._ultimoEspelho ? -1 : 1;
        semPar += escolhidas.length - pares.length;
        if (pares.length) blocosMudados++;
        for (const q of pares) for (const id of doLado(q, sinal)) alvos.add(id);
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
