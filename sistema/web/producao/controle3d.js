/* O modelo 3D ao lado do Controle de produção (FERRAMENTA · CONTROLE DE PRODUÇÃO, 12/11/2026).
 *
 * Pedido do usuário: "trazer o modelo 3D para cá, e deixar essa lista ao lado, onde clicamos na peça e ela aparece
 * destacada no modelo 3D, e conforme formos medindo ela vai ficando com cores diferentes" — não feita cinza, produzida
 * azul, pintada verde, com a ferramenta para escolher os tons (gravados para todas as obras: /api/producao/cores).
 *
 * O 3D é o modo ver de sempre (visor3d/ver3d.html) num quadro ao lado; esta página fala com ele direto (a mesma origem):
 * `visor.fichas` dá a marca de cada peça (cj = conjunto, pos = posição), `visor.pintarComCores` pinta, e o clique numa
 * peça chega como a mensagem 'sel3d' (a mesma do 2D na tela dividida). Com a lista (controle.js) a conversa é por
 * eventos: 'controle:dados' (a situação carregada), 'controle:item' (clicou na linha), 'controle:marcar' (o 3D pede a
 * linha).
 *
 * Unidades iguais da mesma marca (TESOURA 1 × 7): enquanto o detalhamento não grava a unidade de cada peça, elas se
 * separam aqui pelas peças que se tocam, e a ordem segue a obra (pela direção em que as unidades se repetem). Se não der
 * o mesmo número de unidades da lista, ficam juntas: as peças pintam na proporção do que foi feito.
 * Peças iguais avulsas (T.C.1: 46): pintam na proporção — 20 de 46 produzidas = 20 das 46 peças azuis.
 */
(function () {
  'use strict';
  const PROJETO = new URLSearchParams(location.search).get('projeto') || '';
  const NOMES = { falta: 'Não feita', producao: 'Produzida', pintura: 'Pintada', destaque: 'Escolhida' };
  const DICAS = { falta: 'a peça ainda não foi produzida', producao: 'produzida, falta pintar', pintura: 'produzida e pintada',
    destaque: 'a peça escolhida na lista ou no 3D' };
  const SUGESTOES = [
    { nome: 'Padrão', cores: null },
    { nome: 'Forte', cores: { falta: '#7b838d', producao: '#1d5fd6', pintura: '#15a04a', destaque: '#f59e0b' } },
    { nome: 'Suave', cores: { falta: '#c4cad2', producao: '#7ea6e6', pintura: '#82c79b', destaque: '#f2c14e' } },
    { nome: 'Daltonismo', cores: { falta: '#a3a3a3', producao: '#0072b2', pintura: '#e69f00', destaque: '#cc79a7' } },
  ];
  const ESTADOS = ['fora', 'falta', 'producao', 'pintura'];
  const S = { dados: null, cores: null, padrao: null, visor: null, quadro: null, mapa: null, estado: null,
    mostrar: 'tudo', ligado: true, escolhido: null, espera: null, varios: [], somar: false };
  window.controle3d = S;                                  // os testes de tela leem o mapa e a situação

  const $ = (s, raiz = document) => raiz.querySelector(s);
  const nf = (v) => Number(v || 0).toLocaleString('pt-BR');
  const rgb = (hex) => { const v = parseInt(String(hex).slice(1), 16); return [(v >> 16) & 255, (v >> 8) & 255, v & 255]; };
  const lembrar = (k, v) => { try { localStorage.setItem('controle3d.' + k, v); } catch (e) { /* janela privativa */ } };
  const lembrado = (k) => { try { return localStorage.getItem('controle3d.' + k); } catch (e) { return null; } };
  function situacao(t) { const s = $('#p3-situacao'); if (s) s.textContent = t; }

  // ------------------------------------------------------------------ as unidades e as peças de cada item

  /** as peças de uma marca com várias unidades separadas pelas que se tocam; null quando não dá o número da lista */
  function separarUnidades(ps, F, k) {
    if (ps.length < k) return null;
    const caixa = (i) => { const f = F[i]; return f.b || [f.x[0] - 30, f.x[1] - 30, f.x[2] - 30, f.x[0] + 30, f.x[1] + 30, f.x[2] + 30]; };
    const cx = ps.map(caixa);
    const pai = ps.map((_, j) => j);
    const raiz = (j) => { while (pai[j] !== j) { pai[j] = pai[pai[j]]; j = pai[j]; } return j; };
    const folga = 5;
    const ordem = ps.map((_, j) => j).sort((a, b) => cx[a][0] - cx[b][0]);
    for (let a = 0; a < ordem.length; a++) {
      const A = cx[ordem[a]];
      for (let b = a + 1; b < ordem.length; b++) {
        const B = cx[ordem[b]];
        if (B[0] > A[3] + folga) break;
        if (B[1] <= A[4] + folga && A[1] <= B[4] + folga && B[2] <= A[5] + folga && A[2] <= B[5] + folga) {
          const ra = raiz(ordem[a]), rb = raiz(ordem[b]);
          if (ra !== rb) pai[ra] = rb;
        }
      }
    }
    const grupos = new Map();
    ps.forEach((i, j) => { const r = raiz(j); if (!grupos.has(r)) grupos.set(r, []); grupos.get(r).push(j); });
    let lista = [...grupos.values()].sort((a, b) => b.length - a.length);
    if (lista.length < k) return null;
    if (lista.length > k) {
      // pedacinhos soltos (uma chapa que não encosta por um fio): vão para a unidade mais perto; as k maiores precisam
      // ser parecidas, senão não são unidades iguais
      const grandes = lista.slice(0, k);
      if (grandes[k - 1].length < 0.5 * grandes[0].length) return null;
      const meio = (g) => { const m = [0, 0, 0]; for (const j of g) for (let d = 0; d < 3; d++) m[d] += (cx[j][d] + cx[j][d + 3]) / 2; return m.map(v => v / g.length); };
      const centros = grandes.map(meio);
      for (const g of lista.slice(k)) {
        const c = meio(g);
        let melhor = 0, dist = Infinity;
        centros.forEach((o, t) => { const dd = Math.hypot(o[0] - c[0], o[1] - c[1], o[2] - c[2]); if (dd < dist) { dist = dd; melhor = t; } });
        grandes[melhor].push(...g);
      }
      lista = grandes;
    }
    // a ordem na obra: pela direção em que as unidades se repetem (a de maior espalhamento), depois a outra, depois a altura
    const centros = lista.map(g => {
      const m = [0, 0, 0];
      for (const j of g) for (let d = 0; d < 3; d++) m[d] += (cx[j][d] + cx[j][d + 3]) / 2;
      return m.map(v => v / g.length);
    });
    const espalha = (d) => Math.max(...centros.map(c => c[d])) - Math.min(...centros.map(c => c[d]));
    const prim = espalha(0) >= espalha(1) ? 0 : 1, seg = 1 - prim;
    const idx = lista.map((_, t) => t).sort((a, b) =>
      (Math.abs(centros[a][prim] - centros[b][prim]) > 200 ? centros[a][prim] - centros[b][prim] : 0)
      || (Math.abs(centros[a][seg] - centros[b][seg]) > 200 ? centros[a][seg] - centros[b][seg] : 0)
      || centros[a][2] - centros[b][2]);
    return idx.map(t => lista[t].map(j => ps[j]));
  }

  /** {itemDaPeca, pecas[k], grupos: [{itens: [k], pecas}]} — cada grupo pinta junto: um item, ou as unidades que não se
   *  separaram */
  function montarMapa() {
    const V = S.visor, D = S.dados;
    if (!V || !V.fichas || !D || !D.itens) { S.mapa = null; return; }
    const F = V.fichas, n = Math.min(F.length, V.nPecas), itens = D.itens;
    const itemDaPeca = new Int32Array(n).fill(-1);
    const pecas = itens.map(() => []);
    const grupos = [];
    const porCj = new Map(), porPos = new Map();
    for (let i = 0; i < n; i++) {
      const f = F[i];
      if (f.cj) { if (!porCj.has(f.cj)) porCj.set(f.cj, []); porCj.get(f.cj).push(i); }
      // a peça sem marca de posição é chamada pelo nome, como no detalhamento (posicao_base) e no modo ver: as chapas
      // dos suportes de terça do Posto ("Suporte de terça ST1 (aa)") ficavam sem peça no 3D
      const pos = f.pos || (f.cj ? '' : f.n);
      if (pos) { if (!porPos.has(pos)) porPos.set(pos, []); porPos.get(pos).push(i); }
    }
    const unidades = new Map();
    itens.forEach((x, k) => {
      if (x.origem !== 'conjunto') return;
      const m = String((x.refs || [])[0] || '');
      if (!unidades.has(m)) unidades.set(m, []);
      unidades.get(m).push(k);
    });
    let juntas = 0;
    // as peças de cada unidade gravadas pelo Detalhar (nomes.json → unidades, 13/11: o número pela ordem dos eixos):
    // valem primeiro; sem elas, as unidades se separam aqui pelas peças que se tocam
    let porId = null;
    const gravadas = (ks) => {
      if (!ks.every(k => (itens[k].pecas3d || []).length)) return null;
      if (!porId) { porId = new Map(); for (let i = 0; i < n; i++) if (F[i].id != null) porId.set(String(F[i].id), i); }
      const gs = ks.map(k => itens[k].pecas3d.map(id => porId.get(String(id))).filter(i => i !== undefined && itemDaPeca[i] < 0));
      return gs.every(g => g.length) ? gs : null;
    };
    // as tesouras montadas (13/11): cada parte com as peças da meia dela, pintada pela situação da parte
    itens.forEach((x, k) => {
      if (x.origem !== 'montada' || !x.partes) return;
      if (!porId) { porId = new Map(); for (let i = 0; i < n; i++) if (F[i].id != null) porId.set(String(F[i].id), i); }
      for (const pt of x.partes) {
        const g = [];
        for (const id of pt.pecas3d || []) {
          const i = porId.get(String(id));
          if (i === undefined || itemDaPeca[i] >= 0) continue;
          itemDaPeca[i] = k;
          pecas[k].push(i);
          g.push(i);
        }
        grupos.push({ itens: [k], pecas: g, parte: pt });
      }
    });
    for (const [m, ks] of unidades) {
      const ps = (porCj.get(m) || []).filter(i => itemDaPeca[i] < 0);
      const separadas = ks.length > 1 ? (gravadas(ks) || separarUnidades(ps, F, ks.length)) : [ps];
      if (separadas) {
        separadas.forEach((g, j) => {
          pecas[ks[j]] = g;
          for (const i of g) itemDaPeca[i] = ks[j];
          grupos.push({ itens: [ks[j]], pecas: g });
        });
      } else {
        juntas++;
        for (const k of ks) pecas[k] = ps;
        for (const i of ps) itemDaPeca[i] = ks[0];
        grupos.push({ itens: ks, pecas: ps });
      }
    }
    const partes = (x) => String((x.refs || [])[0] || '').split(' / ').map(p => p.trim()).filter(Boolean);
    const avulsos = [];
    // as variantes com as peças gravadas pelo Detalhar (nomes.json → variantes): primeiro, antes que a peça-base do mesmo
    // nome no 3D ("Suporte de terça ST1", CH36) pegue todas
    itens.forEach((x, k) => {
      if (x.origem !== 'pecas' || !(x.pecas3d || []).length) return;
      if (!porId) { porId = new Map(); for (let i = 0; i < n; i++) if (F[i].id != null) porId.set(String(F[i].id), i); }
      for (const id of x.pecas3d) {
        const i = porId.get(String(id));
        if (i === undefined || itemDaPeca[i] >= 0) continue;
        itemDaPeca[i] = k;
        pecas[k].push(i);
      }
    });
    itens.forEach((x, k) => {
      if (x.origem !== 'pecas') return;
      avulsos.push(k);
      if (pecas[k].length) return;
      for (const p of partes(x)) {
        for (const i of porPos.get(p) || []) {
          if (unidades.has(String(F[i].cj || '')) || itemDaPeca[i] >= 0) continue;
          itemDaPeca[i] = k;
          pecas[k].push(i);
        }
      }
    });
    // variantes da mesma peça que o 3D não distingue: a lista separa "Suporte de terça ST1 (aa)", "(ab)"… pela forma, e
    // no 3D todas se chamam "Suporte de terça ST1", sem marca de posição (Posto, 12/11) — ficam juntas, na proporção
    const variantes = new Map();
    for (const k of avulsos) {
      if (pecas[k].length) continue;
      for (const p of partes(itens[k])) {
        const raiz = p.replace(/\s*\([^()]*\)$/, '');
        if (raiz === p || !porPos.has(raiz)) continue;
        if (!variantes.has(raiz)) variantes.set(raiz, []);
        variantes.get(raiz).push(k);
        break;
      }
    }
    const naVariante = new Set();
    for (const [raiz, ks] of variantes) {
      // a peça-base com o mesmo nome ("Suporte de terça ST1", CH36) já pegou as peças: ela entra no grupo
      const ps = (porPos.get(raiz) || []).filter(i => !unidades.has(String(F[i].cj || '')));
      if (!ps.length) continue;
      const todos = [...new Set([...ps.map(i => itemDaPeca[i]).filter(k => k >= 0 && !naVariante.has(k)), ...ks])];
      for (const k of todos) { pecas[k] = ps; naVariante.add(k); }
      for (const i of ps) itemDaPeca[i] = todos[0];
      grupos.push({ itens: todos, pecas: ps });
      if (todos.length > 1) juntas++;
    }
    for (const k of avulsos) if (!naVariante.has(k)) grupos.push({ itens: [k], pecas: pecas[k] });
    // a proporção pinta as peças numa ordem fixa (pela posição na obra), para não pularem a cada apontamento
    const meio = (i) => { const f = F[i]; return f.b ? [(f.b[0] + f.b[3]) / 2, (f.b[1] + f.b[4]) / 2, (f.b[2] + f.b[5]) / 2] : f.x; };
    for (const g of grupos) {
      if (g.pecas.length < 2 || (g.itens.length === 1 && itens[g.itens[0]].quantidade === 1)) continue;
      g.pecas = g.pecas.slice().sort((a, b) => { const A = meio(a), B = meio(b); return A[0] - B[0] || A[1] - B[1] || A[2] - B[2]; });
    }
    const juntasDe = new Map();
    for (const g of grupos) if (g.itens.length > 1) for (const k of g.itens) juntasDe.set(k, g.itens);
    S.mapa = { itemDaPeca, pecas, grupos, juntas, juntasDe, semPeca: itens.filter((x, k) => !pecas[k].length).length };
  }

  // ------------------------------------------------------------------ pintar

  function pintar() {
    const V = S.visor, M = S.mapa;
    if (!V || !M || !S.cores) return;
    const n = V.nPecas, itens = S.dados.itens;
    const estado = new Uint8Array(n);                      // 0 fora do controle, 1 falta, 2 produzida, 3 pintada
    for (const g of M.grupos) {
      let q = 0, prod = 0, pint = 0;
      for (const k of g.itens) {
        const x = g.parte || itens[k], f = x.feito || {};
        q += x.quantidade;
        pint += Math.min(f.pintura || 0, x.quantidade);
        prod += Math.min(Math.max(f.producao || 0, f.pintura || 0), x.quantidade);
      }
      const N = g.pecas.length;
      const nPint = q ? Math.round(N * pint / q) : 0, nProd = q ? Math.round(N * prod / q) : 0;
      g.pecas.forEach((i, j) => { estado[i] = j < nPint ? 3 : j < nProd ? 2 : 1; });
    }
    const paleta = [V.corFantasma || [215, 220, 230], rgb(S.cores.falta), rgb(S.cores.producao), rgb(S.cores.pintura)];
    const cor = new Uint8Array(n * 3);
    const conta = [0, 0, 0, 0];
    for (let i = 0; i < n; i++) {
      const c = paleta[estado[i]];
      cor[i * 3] = c[0]; cor[i * 3 + 1] = c[1]; cor[i * 3 + 2] = c[2];
      conta[estado[i]]++;
    }
    V.pintarComCores(cor, rgb(S.cores.destaque));
    S.estado = estado;
    const esconder = S.mostrar === 'falta-producao' ? [2, 3] : S.mostrar === 'falta-pintura' ? [3] : [];
    if (esconder.length) {
      const ids = [];
      for (let i = 0; i < n; i++) if (esconder.includes(estado[i])) ids.push(i);
      V.ocultarPecas(ids, true);
    }
    S.conta = conta;
    legenda(conta);
    if (S.varios.length) destacarVarios(S.varios);
    else if (S.escolhido !== null) destacarItem(S.escolhido, false);
  }

  function legenda(conta) {
    const L = $('#p3-legenda');
    if (!L) return;
    L.replaceChildren(...['falta', 'producao', 'pintura'].map((k, j) => {
      const e = document.createElement('span');
      e.className = 'p3-chave';
      e.title = `${DICAS[k]} — ${nf(conta[j + 1])} peças do modelo`;
      e.innerHTML = `<i style="background:${S.cores[k]}"></i>${NOMES[k]} <em>${nf(conta[j + 1])}</em>`;
      return e;
    }));
    document.documentElement.style.setProperty('--ctl-destaque', S.cores.destaque);
    const M = S.mapa;
    const notas = [];
    if (M && M.juntas) notas.push(`${nf(M.juntas)} grupo(s) de itens juntos no 3D (unidades ou variantes que o modelo não separa)`);
    if (M && M.semPeca) notas.push(`${nf(M.semPeca)} item(ns) sem peça no 3D`);
    situacao((notas.length ? notas.join(' · ') + ' · ' : '') + 'Clique numa linha da lista ou numa peça do modelo; Ctrl+clique soma à escolha para apontar vários de uma vez.');
  }

  // ------------------------------------------------------------------ escolher

  function destacarItem(k, enquadrar) {
    const V = S.visor, M = S.mapa;
    if (!V || !M) return;
    const ids = M.pecas[k] || [];
    const x = S.dados.itens[k];
    S.escolhido = k;
    if (!ids.length) {
      V.selecionarVarias([], false);
      situacao(`${x.id}: sem peça no modelo 3D (a marca ${(x.refs || []).join(', ')} não está nas peças do 3D).`);
      return;
    }
    V.ocultarPecas(ids, false);                          // o filtro "só o que falta" não esconde a escolhida
    V.selecionarVarias(ids, false);
    if (enquadrar) V.enquadrarPecas(ids);
    const f = x.feito || {};
    const juntas = M.juntasDe.get(k);
    situacao(`${x.id} · ${nf(ids.length)} peça(s) no 3D · produção ${nf(f.producao)}/${nf(x.quantidade)} · pintura ${nf(f.pintura)}/${nf(x.quantidade)}`
      + (juntas ? ` · junto com mais ${nf(juntas.length - 1)} item(ns) que o modelo não separa (${juntas.filter(t => t !== k).slice(0, 4).map(t => S.dados.itens[t].id).join(', ')}${juntas.length > 5 ? '…' : ''})` : ''));
  }

  /** os itens marcados na lista para apontar de uma vez (ids): todas as peças deles acendem juntas */
  function destacarVarios(ids) {
    const V = S.visor, M = S.mapa;
    S.varios = ids || [];
    if (!V || !M || !S.dados) return;
    const ks = S.varios.map(id => S.dados.itens.findIndex(x => x.id === id)).filter(k => k >= 0);
    if (!ks.length) { V.selecionarVarias([], false); if (S.conta) legenda(S.conta); return; }
    const pecas = [...new Set(ks.flatMap(k => M.pecas[k] || []))];
    const sem = ks.filter(k => !(M.pecas[k] || []).length).length;
    V.ocultarPecas(pecas, false);
    V.selecionarVarias(pecas, false);
    S.escolhido = null;
    situacao(`${nf(ks.length)} item(ns) escolhido(s) para apontar · ${nf(pecas.length)} peça(s) no 3D`
      + (sem ? ` · ${nf(sem)} sem peça no modelo` : '') + ' · Ctrl+clique numa peça põe ou tira o item dela');
  }

  function aoClicarNo3D() {
    const V = S.visor, M = S.mapa;
    if (!V || !M) return;
    const i = V.selecionada;
    // Ctrl (ou Shift) + clique: o item da peça entra ou sai da escolha de vários (a lista marca e o 3D acende todos)
    if (S.somar) {
      S.somar = false;
      const k = i === undefined || i < 0 ? -1 : M.itemDaPeca[i];
      if (k >= 0) {
        const ks = M.juntasDe.get(k) || [k];
        document.dispatchEvent(new CustomEvent('controle:alternar', { detail: { ids: ks.map(t => S.dados.itens[t].id) } }));
      } else destacarVarios(S.varios);                   // clicou no vazio ou fora do controle: a escolha fica
      return;
    }
    if (i === undefined || i < 0) {
      S.escolhido = null;
      if (!V.selecaoVarias || !V.selecaoVarias.size) document.dispatchEvent(new CustomEvent('controle:marcar', { detail: { ids: [] } }));
      return;
    }
    const k = M.itemDaPeca[i];
    if (k < 0) {
      const f = V.fichas[i] || {};
      S.escolhido = null;
      situacao(`${f.n || 'Esta peça'} não está no controle de produção${f.pos || f.cj ? ` (${[f.cj, f.pos].filter(Boolean).join(' · ')})` : ''}.`);
      document.dispatchEvent(new CustomEvent('controle:marcar', { detail: { ids: [] } }));
      return;
    }
    destacarItem(k, false);
    const itens = S.dados.itens;
    const ks = M.juntasDe.get(k) || [k];
    document.dispatchEvent(new CustomEvent('controle:marcar', { detail: { ids: ks.map(t => itens[t].id) } }));
  }

  // ------------------------------------------------------------------ o quadro do 3D

  function abrirQuadro() {
    if (S.quadro || !PROJETO) return;
    const q = document.createElement('iframe');
    q.id = 'p3-quadro';
    q.title = 'Modelo 3D da obra';
    q.src = `/visor3d/ver3d.html?projeto=${encodeURIComponent(PROJETO)}&producao=1`;
    $('#p3-palco').append(q);
    S.quadro = q;
    situacao('Abrindo o modelo 3D…');
    const t0 = Date.now();
    clearInterval(S.espera);
    S.espera = setInterval(() => {
      let w = null;
      try { w = q.contentWindow; } catch (e) { /* recarregando */ }
      if (w && w.ver3dPronto && w.visor && w.visor.fichas && typeof w.visor.pintarComCores === 'function') {
        clearInterval(S.espera);
        S.visor = w.visor;
        enxugar(w.document);
        // a tecla no clique: Ctrl/Shift soma à escolha de vários (o modo ver sozinho troca a escolhida)
        const tecla = (e) => { S.somar = !!(e.ctrlKey || e.shiftKey || e.metaKey); };
        w.document.addEventListener('pointerdown', tecla, true);
        w.document.addEventListener('pointerup', tecla, true);
        montarMapa();
        pintar();
      } else if (Date.now() - t0 > 900000) {
        clearInterval(S.espera);
        situacao('O modelo 3D não abriu. Abra pelo menu Engenharia para ver o que houve.');
      } else if (Date.now() - t0 > 60000) {
        // obra grande com a máquina ocupada (o 3D leve do Posto passou de 6 min com 17 chats abertos): segue esperando
        situacao(`Abrindo o modelo 3D… (${Math.round((Date.now() - t0) / 60000)} min; obra grande, a primeira vez demora)`);
      }
    }, 300);
  }

  /** só o que serve aqui: sem Editar, Pintar, Terreno, Cenas e Apresentação (a pintura é a da produção) */
  function enxugar(doc) {
    try {
      const st = doc.createElement('style');
      st.textContent = '#btn-editar, label.pintar, #btn-terreno, #btn-cenas, #btn-apresentacao, #cobertura, [data-cobertura], #abas-cenas,'
        + ' #ferramentas > .sep:first-of-type { display: none !important; }';
      doc.head.append(st);
    } catch (e) { /* outra origem */ }
  }

  /** a obra tem modelo 3D? (a situação do controle diz: tem_3d) — sem ele o painel nem aparece */
  const semModelo = () => !!S.dados && S.dados.tem_3d === false;

  function ligar(sim, guardar = true) {
    S.ligado = !!sim;
    if (guardar) lembrar('ligado', sim ? '1' : '0');
    const mostra = S.ligado && !semModelo();
    document.body.classList.toggle('com-3d', mostra);
    $('#painel3d').hidden = !mostra;
    const b = $('#btn-3d');
    if (b) {
      b.classList.toggle('ligado', mostra);
      b.setAttribute('aria-pressed', String(mostra));
      b.disabled = semModelo();
      b.title = semModelo() ? 'Esta obra não tem modelo 3D' : 'Mostrar ou esconder o modelo 3D ao lado da lista';
    }
    if (mostra && S.dados) abrirQuadro();                // o quadro abre quando se sabe que a obra tem 3D
  }

  // ------------------------------------------------------------------ as cores

  async function carregarCores() {
    try {
      const r = await fetch('/api/producao/cores', { cache: 'no-store' });
      const j = await r.json();
      S.cores = j.cores; S.padrao = j.padrao;
    } catch (e) {
      S.padrao = { falta: '#9aa3ad', producao: '#2f6fd6', pintura: '#2e9d57', destaque: '#f2b01e' };
      S.cores = { ...S.padrao };
    }
    pintar();
    legenda([0, 0, 0, 0]);
  }

  function ferramentaDeCores() {
    const antes = { ...S.cores };
    const dlg = document.createElement('dialog');
    dlg.className = 'ctl-dlg p3-dlg';
    dlg.id = 'p3-dlg-cores';
    const linhas = Object.keys(NOMES).map(k => `
      <div class="p3-cor" data-cor="${k}">
        <input type="color" id="p3-cor-${k}" value="${S.cores[k]}" aria-label="${NOMES[k]}">
        <label for="p3-cor-${k}"><b>${NOMES[k]}</b><small>${DICAS[k]}</small></label>
        <input type="text" class="p3-hex" value="${S.cores[k]}" maxlength="7" spellcheck="false" aria-label="${NOMES[k]} em #rrggbb">
      </div>`).join('');
    const sug = SUGESTOES.map((s, t) => {
      const c = s.cores || S.padrao;
      return `<button type="button" data-sugestao="${t}" title="Usar as cores ${s.nome.toLowerCase()}">${['falta', 'producao', 'pintura', 'destaque']
        .map(k => `<i style="background:${c[k]}"></i>`).join('')} ${s.nome}</button>`;
    }).join('');
    dlg.innerHTML = `<form method="dialog">
      <h3>Cores do modelo 3D</h3>
      <div class="nota">O modelo muda na hora. <b>Gravar</b> guarda para todas as obras.</div>
      ${linhas}
      <div class="p3-sug-titulo">Sugestões</div>
      <div class="p3-sugestoes">${sug}</div>
      <div class="erro" hidden></div>
      <div class="acoes"><button type="button" data-acao="cancelar">Cancelar</button><button type="submit" class="principal" id="p3-gravar">Gravar</button></div>
    </form>`;
    const aplicar = (k, v, deOnde) => {
      if (!/^#[0-9a-fA-F]{6}$/.test(v)) return;
      S.cores[k] = v.toLowerCase();
      const linha = dlg.querySelector(`[data-cor="${k}"]`);
      if (deOnde !== 'cor') linha.querySelector('input[type=color]').value = S.cores[k];
      if (deOnde !== 'hex') linha.querySelector('.p3-hex').value = S.cores[k];
      pintar();
    };
    dlg.querySelectorAll('.p3-cor').forEach(l => {
      const k = l.dataset.cor;
      l.querySelector('input[type=color]').addEventListener('input', ev => aplicar(k, ev.target.value, 'cor'));
      l.querySelector('.p3-hex').addEventListener('input', ev => aplicar(k, ev.target.value.trim(), 'hex'));
    });
    dlg.querySelectorAll('[data-sugestao]').forEach(b => b.addEventListener('click', () => {
      const c = SUGESTOES[+b.dataset.sugestao].cores || S.padrao;
      for (const k of Object.keys(NOMES)) aplicar(k, c[k]);
    }));
    dlg.querySelector('[data-acao=cancelar]').addEventListener('click', () => { S.cores = antes; pintar(); dlg.close(); });
    dlg.addEventListener('cancel', () => { S.cores = antes; pintar(); });
    dlg.querySelector('form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const erro = dlg.querySelector('.erro');
      erro.hidden = true;
      // igual ao padrão: não grava nada (o padrão pode mudar com o programa)
      const iguais = Object.keys(NOMES).every(k => S.cores[k] === S.padrao[k]);
      try {
        const r = await fetch('/api/producao/cores', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
          body: JSON.stringify({ cores: iguais ? {} : S.cores }) });
        const j = await r.json();
        if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
        S.cores = j.cores;
        pintar();
        dlg.close();
      } catch (e) {
        erro.textContent = 'Não foi possível gravar: ' + e.message;
        erro.hidden = false;
      }
    });
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
  }

  // ------------------------------------------------------------------ começo

  const estilo = document.createElement('style');
  estilo.textContent = `
    #painel3d[hidden] { display: none !important; }
    #painel3d { position: sticky; top: var(--p3-topo, 0px); height: calc(100vh - var(--p3-topo, 0px)); display: flex; flex-direction: column; border-left: 1px solid var(--borda); background: var(--painel); min-width: 0; }
    .p3-topo { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 8px 12px; border-bottom: 1px solid var(--borda); font-size: 13px; }
    .p3-topo > b { font-size: 14px; color: var(--azul); }
    .p3-topo select, .p3-topo button { font: inherit; font-size: 12.5px; padding: 3px 9px; border: 1px solid var(--borda-forte); border-radius: var(--raio-p); background: var(--painel); color: var(--texto); cursor: pointer; }
    .p3-topo button:hover { border-color: var(--azul2); color: var(--azul2); }
    #p3-legenda { display: flex; flex-wrap: wrap; gap: 4px 12px; flex: 1; min-width: 200px; }
    .p3-chave { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; color: var(--texto2); }
    .p3-chave i, .p3-sugestoes i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,.18); }
    .p3-chave em { font-style: normal; color: var(--texto3); font-variant-numeric: tabular-nums; }
    #p3-situacao { padding: 5px 12px; font-size: 12.5px; color: var(--texto2); border-bottom: 1px solid var(--borda); min-height: 18px; }
    #p3-palco { flex: 1; position: relative; min-height: 0; }
    #p3-quadro { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
    body.com-3d .palco-ctl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 46%); align-items: start; }
    body.com-3d .controle { max-width: none; margin: 0; }
    #btn-3d.ligado { background: var(--azul-fraco); border-color: var(--azul2); }
    .p3-dlg { width: 420px; max-width: calc(100vw - 32px); }
    .p3-cor { display: grid; grid-template-columns: 44px 1fr 86px; gap: 10px; align-items: center; margin: 10px 0; }
    .p3-cor input[type=color] { width: 44px; height: 32px; padding: 2px; border: 1px solid var(--campo-borda); border-radius: var(--raio-p); background: var(--campo-fundo); cursor: pointer; }
    .p3-cor label { margin: 0 !important; color: var(--texto) !important; }
    .p3-cor label small { display: block; color: var(--texto3); font-size: 12px; }
    .p3-cor .p3-hex { font-family: ui-monospace, Consolas, monospace; font-size: 13px; text-transform: lowercase; }
    .p3-sug-titulo { font-size: 12.5px; color: var(--texto2); margin: 14px 0 6px; }
    .p3-sugestoes { display: flex; flex-wrap: wrap; gap: 6px; }
    .p3-sugestoes button { font: inherit; font-size: 12.5px; padding: 4px 9px; border: 1px solid var(--borda-forte); border-radius: var(--raio-p); background: var(--painel); color: var(--texto); cursor: pointer; display: inline-flex; gap: 3px; align-items: center; }
    .p3-sugestoes button i { width: 10px; height: 10px; }
    @media (max-width: 1000px) {
      body.com-3d .palco-ctl { grid-template-columns: 1fr; }
      #painel3d { position: relative; height: 70vh; border-left: 0; border-top: 1px solid var(--borda); }
    }
    @media print { #painel3d { display: none !important; } body.com-3d .palco-ctl { display: block; } }
  `;
  document.head.append(estilo);

  function iniciar() {
    const painel = $('#painel3d');
    if (!painel || !PROJETO) return;
    painel.innerHTML = `
      <div class="p3-topo">
        <b>Modelo 3D</b>
        <span id="p3-legenda"></span>
        <select id="p3-mostrar" title="Esconder do modelo o que já foi feito">
          <option value="tudo">Mostrar tudo</option>
          <option value="falta-producao">Só o que falta produzir</option>
          <option value="falta-pintura">Só o que falta pintar</option>
        </select>
        <button type="button" id="p3-cores" title="Escolher as cores de cada situação">Cores…</button>
      </div>
      <div id="p3-situacao"></div>
      <div id="p3-palco"></div>`;
    const sel = $('#p3-mostrar');
    S.mostrar = lembrado('mostrar') || 'tudo';
    sel.value = S.mostrar;
    sel.addEventListener('change', () => { S.mostrar = sel.value; lembrar('mostrar', S.mostrar); pintar(); });
    $('#p3-cores').addEventListener('click', () => { if (S.cores) ferramentaDeCores(); });
    const b = $('#btn-3d');
    if (b) b.addEventListener('click', () => ligar(!S.ligado));
    // o painel fica preso logo abaixo da barra de cima (ela fica fixa no alto e cobria a legenda e o Cores…)
    const medirTopo = () => {
      const t = document.querySelector('header.topo');
      const pos = t ? getComputedStyle(t).position : '';
      const h = t && (pos === 'sticky' || pos === 'fixed') ? Math.round(t.getBoundingClientRect().height) : 0;
      document.documentElement.style.setProperty('--p3-topo', h + 'px');
    };
    medirTopo();
    addEventListener('resize', medirTopo);
    setTimeout(medirTopo, 800);                            // a barra única (etapas.js) se monta depois

    document.addEventListener('controle:dados', (ev) => {
      S.dados = ev.detail;
      if (S.visor) { montarMapa(); pintar(); }
      else ligar(S.ligado, false);
    });
    document.addEventListener('controle:varios', (ev) => destacarVarios(ev.detail.ids));
    document.addEventListener('controle:item', (ev) => {
      if (!S.dados || !S.mapa) return;
      const k = S.dados.itens.findIndex(x => x.id === ev.detail.id);
      if (k >= 0) destacarItem(k, true);
    });
    window.addEventListener('message', (ev) => {
      if (ev.origin !== location.origin || !ev.data || !S.quadro || ev.source !== S.quadro.contentWindow) return;
      if (ev.data.metalica === 'sel3d') aoClicarNo3D();
    });
    // o tema muda: o cinza das peças fora do controle acompanha o fundo
    new MutationObserver(() => setTimeout(pintar, 60)).observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });

    if (window.controleDados && window.controleDados.itens) S.dados = window.controleDados;   // chegou antes deste script
    carregarCores();
    ligar(lembrado('ligado') !== '0');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
