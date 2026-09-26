// Métodos do editor 3D: Diálogos dos cantos redondos e dos eixos da obra.
//
// Saíram de editor.js (que tinha quase 5 mil linhas) sem mudar o corpo: esta classe só
// guarda os métodos, e editor.js os copia para Editor.prototype (aplicarMetodos).

import { $, el, mover } from '../editor.js';

export class MetodosCantosEixos {
  /**
   * Detalhamento para produção: uma célula por posição (peças iguais contadas uma vez)
   * e a elevação de cada conjunto, em desenhos por grupo, mais o romaneio.
   */
  /**
   * Eixos da obra: os numerados (as tesouras, atravessados ao galpão) e os com letra (os
   * apoios — chumbadores ou chapas de base), identificados do modelo (nucleo3d/eixos.py)
   * e gravados no projeto para renomear, mover e acrescentar. As plantas de localização e
   * de chumbação desenham os eixos gravados (bolinhas e cotas entre eixos).
   */
  async dialogoEixos() {
    if (!this.projeto) { this.aviso('Abra um projeto para identificar os eixos.', 'atencao'); return; }
    let dados;
    try { await this._gravarAntesDeGerar(); dados = await this.api.eixosDoProjeto(this.projeto); }
    catch (e) { this.aviso(`Não deu para identificar os eixos: ${e.message}`, 'erro', 0); return; }
    const mm = (x) => Number(x).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
    const corpo = el('div', { class: 'eixos' });
    const cabecalho = el('p', {});
    corpo.append(cabecalho);
    const tabelas = el('div', { class: 'eixos-tabelas' });
    corpo.append(tabelas);
    let atual = dados.eixos;
    const linhas = { letras: [], numeros: [] };
    const proximoNome = (chave) => {
      const nomes = linhas[chave].map(l => l.nome.value.trim());
      if (chave === 'numeros') { let n = 1; while (nomes.includes(String(n))) n++; return String(n); }
      for (let i = 0; i < 26; i++) { const c = String.fromCharCode(65 + i); if (!nomes.includes(c)) return c; }
      return 'Z' + nomes.length;
    };
    const montar = () => {
      tabelas.replaceChildren();
      cabecalho.textContent = (dados.gravados ? 'Eixos gravados no projeto. ' : `Eixos identificados do modelo agora (as letras: ${atual.fonte_letras || 'apoios'}); grave para as plantas usarem sempre estes. `)
        + 'Posição em mm: os numerados ao longo do galpão, os com letra atravessados. Renomeie, mova, acrescente ou apague.';
      for (const [chave, titulo] of [['letras', 'Eixos com letra (apoios, atravessados)'], ['numeros', 'Eixos numerados (tesouras, ao longo)']]) {
        linhas[chave] = [];
        const t = el('table', { class: 'tabela-cantos' });
        t.append(el('thead', {}, el('tr', {}, el('th', { texto: titulo }), el('th', { texto: 'Posição (mm)' }), el('th', { texto: '' }))));
        const tb = el('tbody');
        const addLinha = (nome, pos) => {
          const inNome = el('input', { type: 'text', value: nome, size: '4', maxlength: '6' });
          const inPos = el('input', { type: 'number', step: '1', value: String(Math.round(pos)) });
          const tr = el('tr', {}, el('td', {}, inNome), el('td', {}, inPos), el('td', {}, el('button', { type: 'button', class: 'mini', texto: '×', title: 'Apagar este eixo', onclick: () => { linhas[chave] = linhas[chave].filter(l => l.tr !== tr); tr.remove(); } })));
          tb.append(tr);
          linhas[chave].push({ tr, nome: inNome, pos: inPos });
        };
        for (const e of (atual[chave] || [])) addLinha(e.nome, e.pos);
        t.append(tb);
        tabelas.append(t, el('div', { class: 'acoes' }, el('button', { type: 'button', texto: '+ eixo', onclick: () => {
          const ult = linhas[chave].length ? parseFloat(linhas[chave][linhas[chave].length - 1].pos.value) || 0 : 0;
          addLinha(proximoNome(chave), ult + 5000);
        } })));
      }
    };
    montar();
    const ler = () => ({ eixo_g: atual.eixo_g, perp_g: atual.perp_g, z_base: atual.z_base, fonte_letras: atual.fonte_letras,
      letras: linhas.letras.map(l => ({ nome: l.nome.value.trim(), pos: parseFloat(l.pos.value) })).filter(x => x.nome && isFinite(x.pos)),
      numeros: linhas.numeros.map(l => ({ nome: l.nome.value.trim(), pos: parseFloat(l.pos.value) })).filter(x => x.nome && isFinite(x.pos)) });
    const acoes = el('div', { class: 'acoes' },
      el('button', { type: 'button', texto: 'Identificar de novo do modelo', onclick: async () => {
        try { const r = await this.api.gravarEixos(this.projeto, { identificar: true }); atual = r.eixos; dados.gravados = false; montar(); }
        catch (e) { this.aviso(`Não deu para identificar: ${e.message}`, 'erro'); }
      } }),
      el('button', { type: 'button', texto: 'Apagar do projeto (voltar ao automático)', onclick: async () => {
        try { await this.api.gravarEixos(this.projeto, { apagar: true }); const r = await this.api.eixosDoProjeto(this.projeto); atual = r.eixos; dados.gravados = false; montar(); this.aviso('Eixos apagados do projeto: as plantas voltam a identificar do modelo.', 'info'); }
        catch (e) { this.aviso(`Não deu para apagar: ${e.message}`, 'erro'); }
      } }));
    corpo.append(acoes);
    corpo.append(el('p', { class: 'nota', texto: `Eixo do galpão: (${mm(atual.eixo_g[0] * 1000) / 1000}, ${mm(atual.eixo_g[1] * 1000) / 1000}); nível de base ${mm(atual.z_base)} mm. Depois de gravar, gere o detalhamento de novo (planta de localização e de chumbação).` }));
    if (await this.dialogo({ titulo: 'Eixos da obra', corpo, ok: 'Gravar no projeto' }) !== 'ok') return;
    try {
      const r = await this.api.gravarEixos(this.projeto, { eixos: ler() });
      this.aviso(`Eixos gravados: ${(r.eixos.letras || []).map(e => e.nome).join(', ')} e ${(r.eixos.numeros || []).map(e => e.nome).join(', ')}. Gere o detalhamento de novo para as plantas saírem com eles.`, 'info', 12000);
    } catch (e) { this.aviso(`Não foi possível gravar os eixos: ${e.message}`, 'erro', 0); }
  }

  /**
   * Cantos redondos: as barras calandradas do modelo (o joelho da tesoura vem do
   * TecnoMETAL como um arco facetado) com raio, ângulo e as opções de quebra em N retas
   * tangentes — o canto quinado da fábrica —, com o desvio de cada opção. A quebra vai
   * para o modelo 3D em todas as instâncias; o modelo anterior fica no histórico.
   */
  async dialogoCantosRedondos() {
    if (!this.projeto) { this.aviso('Abra um projeto para analisar os cantos.', 'atencao'); return; }
    let dados;
    try {
      await this._gravarAntesDeGerar();
      dados = await this.api.cantosDoProjeto(this.projeto);
    } catch (e) { this.aviso(`Não deu para analisar os cantos: ${e.message}`, 'erro', 0); return; }
    const pecas = dados.pecas || [];
    const quebradas = dados.quebradas || [];
    const mm = (x, c = 0) => Number(x).toLocaleString('pt-BR', { maximumFractionDigits: c });
    if (!pecas.length && !quebradas.length) {
      await this.dialogo({ titulo: 'Cantos redondos', corpo: el('p', { texto: 'Nenhuma barra calandrada com canto foi reconhecida no modelo (barra redonda com gancho não é canto).' }), ok: null });
      return;
    }
    const corpo = el('div', { class: 'cantos' });
    const selects = new Map();
    const voltar = new Map();
    if (quebradas.length) {
      // as posições já quebradas: dá para voltar ao arco (a malha original fica guardada
      // na peça; quebrada por uma versão anterior, vem do histórico do projeto)
      corpo.append(el('p', { texto: `${quebradas.length} posição(ões) já quebradas em retas. Marque as que devem voltar ao canto redondo — a peça, o banzo esticado e a diagonal do canto voltam como eram.` }));
      const tq = el('table', { class: 'tabela-cantos' });
      tq.append(el('thead', {}, el('tr', {}, ...['Posição', 'Perfil', 'Inst.', 'Raio', 'Ângulo', 'Retas', 'Voltar ao canto redondo'].map(t => el('th', { texto: t })))));
      const cq = el('tbody');
      for (const p of quebradas) {
        const cx = el('input', { type: 'checkbox', title: p.original ? 'A malha original está guardada na peça' : 'Quebrada por uma versão anterior: a malha original vem do histórico do projeto' });
        voltar.set(p.marca, cx);
        cq.append(el('tr', {},
          el('td', { texto: p.nome ? `${p.nome} (${p.marca})` : p.marca }), el('td', { texto: p.perfil }), el('td', { texto: String(p.instancias) }),
          el('td', { texto: p.raio ? `${mm(p.raio)} mm` : '' }), el('td', { texto: p.angulo ? `${mm(p.angulo, 1)}°` : '' }), el('td', { texto: String(p.n || '') }),
          el('td', {}, cx)));
      }
      tq.append(cq);
      corpo.append(tq);
    }
    if (pecas.length) corpo.append(el('p', { texto: `${pecas.length} posição(ões) com canto redondo. Cada arco vira N retas tangentes (o canto quinado da fábrica: os trechos retos se prolongam até a primeira e a última reta). O desvio é quanto o nó sai do arco — escolha N e aplique.` }));
    const tabela = el('table', { class: 'tabela-cantos' });
    tabela.append(el('thead', {}, el('tr', {}, ...['Posição', 'Perfil', 'Inst.', 'Raio', 'Ângulo', 'Arco', 'Quebrar em'].map(t => el('th', { texto: t })))));
    const corpoT = el('tbody');
    // pré-visualização: o canto da primeira instância antes (cinza tracejado) e depois
    // (cor) da quebra escolhida, no plano do arco — muda junto com a opção
    const previa = el('div', { class: 'previa-canto' });
    const legenda = el('p', { class: 'nota' });
    const svgNS = 'http://www.w3.org/2000/svg';
    const cacheP = new Map();
    let pedido = 0;
    const mostrar = async (marca, n, rotulo) => {
      const meu = ++pedido;
      for (const tr of corpoT.children) tr.classList.toggle('em-previa', tr.dataset.marca === marca);
      legenda.textContent = `Pré-visualização de ${rotulo}: carregando…`;
      const chave = marca + '|' + n;
      let r = cacheP.get(chave);
      try { if (!r) { r = await this.api.previaCanto(this.projeto, marca, n); cacheP.set(chave, r); } }
      catch (e) { if (meu === pedido) legenda.textContent = `Pré-visualização de ${rotulo}: ${e.message}`; return; }
      if (meu !== pedido) return;
      const [x0, y0, x1, y1] = r.caixa;
      const svg = document.createElementNS(svgNS, 'svg');
      svg.setAttribute('viewBox', `${x0} ${-y1} ${x1 - x0} ${y1 - y0}`);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      const grupo = (segs, cor, larg, tracejado) => {
        if (!segs || !segs.length) return;
        const p = document.createElementNS(svgNS, 'path');
        p.setAttribute('d', segs.map(s => `M${s[0]} ${-s[1]}L${s[2]} ${-s[3]}`).join(''));
        p.setAttribute('stroke', cor); p.setAttribute('stroke-width', larg); p.setAttribute('fill', 'none');
        p.setAttribute('vector-effect', 'non-scaling-stroke');
        if (tracejado) p.setAttribute('stroke-dasharray', '4 3');
        svg.append(p);
      };
      if (r.depois) {
        grupo(r.antes.peca, '#9aa3ad', 1, true);
        grupo(r.depois.outras, 'var(--previa-outras, #3b6fd1)', 0.8, false);
        grupo(r.depois.peca, '#e67e22', 1.6, false);
      } else {
        grupo(r.antes.outras, 'var(--previa-outras, #3b6fd1)', 0.8, false);
        grupo(r.antes.peca, '#e67e22', 1.6, false);
      }
      for (const [x, y] of r.nos || []) {
        const c = document.createElementNS(svgNS, 'circle');
        c.setAttribute('cx', x); c.setAttribute('cy', -y); c.setAttribute('r', Math.max((x1 - x0), (y1 - y0)) / 150);
        c.setAttribute('fill', '#d62728');
        svg.append(c);
      }
      previa.replaceChildren(svg);
      const extra = [];
      if (r.depois) {
        extra.push(`nó sai ${mm(r.desvio)} mm do arco`);
        if (r.estendidas) extra.push('banzo esticado até o nó');
        if (r.pontas_mantidas) extra.push('ponta mantida (sem banzo alinhado para vir até o nó)');
        if (r.diagonais) extra.push(`${r.diagonais} diagonal(is) do nó de baixo a cada nó`);
      }
      legenda.textContent = r.depois
        ? `Pré-visualização de ${rotulo} em ${r.n} reta${r.n > 1 ? 's' : ''}: laranja como fica, cinza tracejado o arco de hoje, pontos vermelhos os nós — ${extra.join(' · ')}. Mude a opção para comparar.`
        : `Pré-visualização de ${rotulo}: como está hoje (não quebrar).`;
    };
    for (const p of pecas) {
      const sel = el('select', { title: 'Em quantas retas quebrar o arco' });
      sel.append(el('option', { value: '', texto: 'não quebrar' }));
      for (const o of p.opcoes) sel.append(el('option', { value: String(o.n), texto: `${o.n} reta${o.n > 1 ? 's' : ''} · sai ${mm(o.desvio)} mm` }));
      // sugestão: a menor N com desvio até a altura do perfil (o que o 2D já desenha é N = 1)
      const alt = parseFloat((p.perfil.match(/(\d+(?:[.,]\d+)?)/) || [0, 100])[1]) || 100;
      const sug = p.opcoes.find(o => o.desvio <= alt) || p.opcoes[0];
      sel.value = String(sug.n);
      selects.set(p.marca, sel);
      const rotulo = p.nome ? `${p.nome} (${p.marca})` : p.marca;
      sel.addEventListener('change', () => mostrar(p.marca, +sel.value || 0, rotulo));
      sel.addEventListener('focus', () => mostrar(p.marca, +sel.value || 0, rotulo));
      corpoT.append(el('tr', { 'data-marca': p.marca, title: 'Clique para ver este canto na pré-visualização', onclick: (ev) => { if (ev.target !== sel) mostrar(p.marca, +sel.value || 0, rotulo); } },
        el('td', { texto: p.nome ? `${p.nome} (${p.marca})` : p.marca }), el('td', { texto: p.perfil }), el('td', { texto: String(p.instancias) }),
        el('td', { texto: `${mm(p.raio)} mm` }), el('td', { texto: `${mm(p.angulo, 1)}°` }), el('td', { texto: `${mm(p.comprimento_arco)} mm` }),
        el('td', {}, sel)));
    }
    tabela.append(corpoT);
    if (pecas.length) {
      corpo.append(tabela);
      corpo.append(previa, legenda);
      const p0 = pecas[0];
      mostrar(p0.marca, +selects.get(p0.marca).value || 0, p0.nome ? `${p0.nome} (${p0.marca})` : p0.marca);
      corpo.append(el('p', { class: 'nota', texto: 'A malha nova reaproveita a seção da própria peça, com os nós em meia-esquadria; quando o joelho encosta no banzo, ele termina no nó, o banzo é esticado até ele e a diagonal do canto é refeita do nó de baixo a cada nó. A elevação ganha a linha de emenda em cada nó. Gere o detalhamento de novo depois.' }));
    }
    if (await this.dialogo({ titulo: 'Cantos redondos', corpo, ok: pecas.length ? 'Quebrar no modelo' : 'Aplicar' }) !== 'ok') return;
    const escolhas = {};
    for (const [marca, sel] of selects) if (sel.value) escolhas[marca] = +sel.value;
    const marcasVoltar = [...voltar].filter(([, cx]) => cx.checked).map(([marca]) => marca);
    if (!Object.keys(escolhas).length && !marcasVoltar.length) { this.aviso('Nenhuma posição marcada para quebrar ou voltar.', 'info'); return; }
    const avisos = [];
    try {
      if (marcasVoltar.length) {
        this.dica('Voltando ao canto redondo…');
        const r = await this.api.desfazerCantos(this.projeto, marcasVoltar);
        avisos.push(`${r.pecas} peça(s) de ${(r.posicoes || []).join(', ') || '—'} voltaram ao canto redondo.` +
                    ((r.falhas || []).length ? ` Avisos: ${r.falhas.slice(0, 4).join(' · ')}` : ''));
      }
      if (Object.keys(escolhas).length) {
        this.dica('Quebrando os cantos no modelo…');
        const r = await this.api.quebrarCantos(this.projeto, escolhas);
        avisos.push(`${r.pecas} peça(s) de ${(r.posicoes || []).join(', ')} quebradas em retas no modelo 3D (o anterior está no histórico).` +
                    ((r.falhas || []).length ? ` Avisos: ${r.falhas.slice(0, 4).join(' · ')}` : ''));
      }
      await this._abrirProjeto();
      this.dica('');
      this.aviso(avisos.join(' ') + ' Gere o detalhamento de novo: Detalhamentos → Detalhar peças e conjuntos.', 'info', 16000);
    } catch (e) { this.dica(''); this.aviso(`Não foi possível aplicar nos cantos: ${e.message}`, 'erro', 0); }
  }
}
