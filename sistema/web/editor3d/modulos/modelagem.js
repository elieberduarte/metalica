// Métodos do editor 3D: a modelagem estrutural pela seleção (14/10/2026), como no Revit e no Tekla — escolhe as peças,
// preenche o diálogo e a estrutura sai no lugar, numa entrada de desfazer:
//
// * Terças por espaçamento — nas tesouras/vigas selecionadas, sentadas no topo, nunca acima do espaçamento pedido;
// * Treliça entre banzos — montantes e diagonais (Pratt, Howe, Warren) entre os dois banzos, com o encaixe das almas;
// * Contraventamento em X — entre duas barras paralelas, num ou em vários painéis;
// * Pilares nos eixos — um pilar em cada cruzamento escolhido dos eixos gravados da obra;
// * Viga entre pilares — no nível pedido, com o topo da viga no nível.
//
// A geometria é do servidor (nucleo3d/modelagem.py); aqui ficam os diálogos e o comando.

import { el, numero } from '../editor.js';

const vert = (b) => {
  const d = [b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1], b.fim[2] - b.inicio[2]];
  return Math.abs(d[2]) / (Math.hypot(...d) || 1) > 0.7;
};

/** os cruzamentos dos eixos em planta, com o nome "A-1" (a letra primeiro) — o mesmo critério do servidor */
function cruzamentosDosEixos(eixos) {
  const fora = [];
  for (let i = 0; i < eixos.length; i++) {
    for (let j = i + 1; j < eixos.length; j++) {
      const e1 = eixos[i], e2 = eixos[j];
      const d1 = [e1.b[0] - e1.a[0], e1.b[1] - e1.a[1]], d2 = [e2.b[0] - e2.a[0], e2.b[1] - e2.a[1]];
      const den = d1[0] * d2[1] - d1[1] * d2[0];
      if (Math.abs(den) < 1e-6 * Math.hypot(...d1) * Math.hypot(...d2)) continue;
      const t = ((e2.a[0] - e1.a[0]) * d2[1] - (e2.a[1] - e1.a[1]) * d2[0]) / den;
      const u = ((e2.a[0] - e1.a[0]) * d1[1] - (e2.a[1] - e1.a[1]) * d1[0]) / den;
      if (t < -0.01 || t > 1.01 || u < -0.01 || u > 1.01) continue;
      const n1 = String(e1.nome || ''), n2 = String(e2.nome || '');
      fora.push(/^[A-Za-z]+$/.test(n1) ? `${n1}-${n2}` : `${n2}-${n1}`);
    }
  }
  return fora.sort();
}

export class MetodosModelagem {
  /** Um formulário de campos simples: [{chave, rotulo, valor, tipo: 'numero'|'texto'|'perfil'|opções[]}] → {corpo, ler()} */
  _formModelagem(campos) {
    const caixa = el('div', { class: 'campos' });
    const entradas = [];
    let lista = null;
    for (const c of campos) {
      let i;
      if (Array.isArray(c.tipo)) {
        i = el('select');
        for (const [v, t] of c.tipo) i.append(el('option', { value: v, texto: t, selected: String(c.valor) === String(v) }));
      } else if (c.tipo === 'perfil') {
        if (!lista) {
          lista = el('datalist', { id: 'perfis-modelagem' });
          for (const p of (this.catalogo.perfis || [])) lista.append(el('option', { value: p.nome }));
        }
        i = el('input', { type: 'text', value: c.valor || '', spellcheck: 'false', list: 'perfis-modelagem' });
      } else {
        i = el('input', { type: c.tipo === 'numero' ? 'number' : 'text', step: 'any', value: c.valor ?? '' });
        if (c.dica) i.placeholder = c.dica;
      }
      entradas.push([c, i]);
      caixa.append(el('label', { texto: c.rotulo }), i);
    }
    if (lista) caixa.append(lista);
    const ler = () => {
      const out = {};
      for (const [c, i] of entradas) {
        const v = String(i.value || '').trim();
        if (!v) continue;
        out[c.chave] = c.tipo === 'numero' ? parseFloat(v.replace(',', '.')) : v;
      }
      return out;
    };
    return { corpo: caixa, ler };
  }

  /** O perfil de partida de um campo: o da peça escolhida do mesmo papel, senão o ativo da barra, senão o padrão. */
  _perfilSugerido(papel, padrao) {
    const doc = [...this.documento.entidades.values()].find(e => e.tipo === 'barra' && String(e.papel).toLowerCase() === papel);
    return (doc && doc.perfil) || padrao;
  }

  /** Manda o pedido, aplica as barras novas e as alterações num comando só e diz o que saiu. */
  async _modelar(pedido, rotulo) {
    let r;
    try {
      this.dica(`${rotulo}…`);
      const resp = await fetch('/api/modelo/modelar', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ documento: this.documento.paraJSON(), ...pedido }) });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { this.aviso(`${rotulo}: ${e.message}`, 'erro', 0); return null; }
    const cmd = this._comandoDaLigacao(r, rotulo);
    if (!cmd) { this.aviso(`${rotulo}: nada a lançar.`, 'info'); return r; }
    this.executar(cmd);
    const novas = (r.novas || []).map(d => d.id).filter(id => this.documento.get(id));
    this.selecao.definir(novas);
    await this._completarPerfis();
    const res = r.resumo || {};
    const partes = [`${novas.length} peça${novas.length === 1 ? '' : 's'}`];
    if (res.passo) partes.push(`passo ${numero(res.passo, 0)} mm`);
    if (res.paineis) partes.push(`${res.paineis} painéis`);
    this.aviso(`${rotulo}: ${partes.join(' · ')}.${(r.avisos || []).length ? ' ' + r.avisos.join('; ') + '.' : ''}`,
      (r.avisos || []).length ? 'atencao' : 'info', 9000);
    return r;
  }

  async dialogoTercas() {
    const apoios = this.selecao.entidades.filter(e => e.tipo === 'barra' && !vert(e));
    if (apoios.length < 2) { this.dica('Selecione os banzos de cima (ou as vigas) de duas ou mais tesouras de uma água: as terças vão de uma à outra.'); return; }
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('terça', 'Ue 150×60×20×2,25') },
      { chave: 'espacamento', rotulo: 'Espaçamento máximo (mm)', tipo: 'numero', valor: 1500 },
      { chave: 'beiral', rotulo: 'Primeira terça, da ponta baixa (mm)', tipo: 'numero', valor: 200 },
      { chave: 'cumeeira', rotulo: 'Última terça, da ponta alta (mm)', tipo: 'numero', valor: 250 },
      { chave: 'continua', rotulo: 'Terça', tipo: [['nao', 'uma por vão'], ['sim', 'contínua sobre os apoios']], valor: 'nao' },
      { chave: 'balanco', rotulo: 'Balanço nas pontas (mm)', tipo: 'numero', valor: 0 },
      { chave: 'boca', rotulo: 'Boca do U para', tipo: [['cumeeira', 'a cumeeira'], ['beiral', 'o beiral']], valor: 'cumeeira' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: `${apoios.length} apoios. As terças saem igualmente espaçadas (nunca acima do máximo), sentadas no topo dos apoios, com a alma perpendicular à água.` }));
    if (await this.dialogo({ titulo: 'Terças por espaçamento', corpo, ok: 'Lançar terças' }) !== 'ok') return;
    await this._modelar({ ferramenta: 'tercas', ids: apoios.map(b => b.id), parametros: f.ler() }, 'Terças');
  }

  async dialogoTrelica() {
    const bs = this.selecao.entidades.filter(e => e.tipo === 'barra');
    if (bs.length !== 2) { this.dica('Selecione os dois banzos da treliça (o de cima e o de baixo).'); return; }
    const perfil = bs[0].perfil;
    const f = this._formModelagem([
      { chave: 'tipo', rotulo: 'Tipo', tipo: [['pratt', 'Pratt (diagonais descem para o meio)'], ['howe', 'Howe (diagonais sobem para o meio)'], ['warren', 'Warren (só diagonais)']], valor: 'pratt' },
      { chave: 'passo', rotulo: 'Painel máximo (mm)', tipo: 'numero', valor: 1500 },
      { chave: 'paineis', rotulo: 'Ou o número de painéis', tipo: 'numero', dica: 'pelo painel máximo' },
      { chave: 'perfil_montante', rotulo: 'Perfil dos montantes', tipo: 'perfil', valor: perfil },
      { chave: 'perfil_diagonal', rotulo: 'Perfil das diagonais', tipo: 'perfil', valor: perfil },
      { chave: 'montantes', rotulo: 'Montantes na Warren', tipo: [['nao', 'não'], ['sim', 'sim']], valor: 'nao' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: 'Os nós igualmente espaçados no trecho em que os banzos correm juntos; as almas encaixam nas faces dos banzos (meia-esquadria), como na montagem pela planta, e tudo entra no mesmo bloco.' }));
    if (await this.dialogo({ titulo: 'Treliça entre banzos', corpo, ok: 'Lançar treliça' }) !== 'ok') return;
    await this._modelar({ ferramenta: 'trelica', ids: bs.map(b => b.id), parametros: f.ler() }, 'Treliça');
  }

  async dialogoContraventoX() {
    const bs = this.selecao.entidades.filter(e => e.tipo === 'barra');
    if (bs.length !== 2) { this.dica('Selecione as duas barras paralelas do vão contraventado: dois pilares, ou os banzos de duas tesouras.'); return; }
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('contraventamento', "FE RED 1/2''") },
      { chave: 'paineis', rotulo: 'Painéis', tipo: 'numero', valor: vert(bs[0]) ? 2 : 1 },
      { chave: 'margem', rotulo: 'Afastamento das pontas (mm)', tipo: 'numero', valor: 0 },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: 'Duas diagonais por painel, de eixo a eixo; a ligação (chapa ou suporte do tirante) vem depois, pelo Aplicar ligação.' }));
    if (await this.dialogo({ titulo: 'Contraventamento em X', corpo, ok: 'Lançar' }) !== 'ok') return;
    await this._modelar({ ferramenta: 'contravento', ids: bs.map(b => b.id), parametros: f.ler() }, 'Contraventamento');
  }

  async dialogoPilaresNosEixos() {
    const ref = (this.inferencia && this.inferencia.referencias) || {};
    const eixos = (ref.eixos || this._eixosRef || []).filter(e => e && e.a && e.b);
    if (eixos.length < 2) { this.aviso('A obra não tem eixos gravados: grave-os em Lançamento → Planta de lançamento (ou Detalhamentos → Eixos da obra).', 'atencao', 0); return; }
    const nomes = cruzamentosDosEixos(eixos);
    const niveis = (ref.niveis || []).map(n => +n.z || 0).filter(z => z > 0);
    const marcas = el('div', { class: 'grade-cruzamentos', style: 'display:flex;flex-wrap:wrap;gap:4px 12px;max-height:180px;overflow:auto' });
    const caixas = nomes.map(n => {
      const c = el('input', { type: 'checkbox', checked: true });
      marcas.append(el('label', { style: 'white-space:nowrap' }, c, ` ${n}`));
      return [n, c];
    });
    const todos = el('button', { type: 'button', texto: 'Todos / nenhum' });
    todos.addEventListener('click', () => { const v = !caixas.every(([, c]) => c.checked); for (const [, c] of caixas) c.checked = v; });
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('pilar', 'W 250×32,7') },
      { chave: 'base', rotulo: 'Base (mm)', tipo: 'numero', valor: 0 },
      { chave: 'topo', rotulo: 'Topo (mm)', tipo: 'numero', valor: niveis.length ? Math.max(...niveis) : 6000 },
      { chave: 'alma', rotulo: 'Alma no plano dos eixos', tipo: [['numerados', 'numerados (o pórtico)'], ['letras', 'com letra']], valor: 'numerados' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: `${nomes.length} cruzamentos dos eixos gravados:` }), marcas, todos);
    if (await this.dialogo({ titulo: 'Pilares nos eixos', corpo, ok: 'Lançar pilares' }) !== 'ok') return;
    const escolhidos = caixas.filter(([, c]) => c.checked).map(([n]) => n);
    if (!escolhidos.length) { this.dica('Nenhum cruzamento escolhido.'); return; }
    await this._modelar({ ferramenta: 'pilares', eixos, cruzamentos: escolhidos, parametros: f.ler() }, 'Pilares');
  }

  async dialogoVigaEntrePilares() {
    const pilares = this.selecao.entidades.filter(e => e.tipo === 'barra' && vert(e));
    if (pilares.length < 2) { this.dica('Selecione dois ou mais pilares: a viga liga um ao outro, na ordem em planta.'); return; }
    const topo = Math.min(...pilares.map(b => Math.max(b.inicio[2], b.fim[2])));
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('viga', 'W 310×38,7') },
      { chave: 'nivel', rotulo: 'Topo da viga no nível (mm)', tipo: 'numero', valor: Math.round(topo) },
      { chave: 'continua', rotulo: 'Viga', tipo: [['nao', 'uma por vão'], ['sim', 'contínua']], valor: 'nao' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: `${pilares.length} pilares. A viga vai de eixo a eixo dos pilares; a ligação (chapa de topo, flexível) vem depois, pelo Aplicar ligação.` }));
    if (await this.dialogo({ titulo: 'Viga entre pilares', corpo, ok: 'Lançar viga' }) !== 'ok') return;
    await this._modelar({ ferramenta: 'viga', ids: pilares.map(b => b.id), parametros: f.ler() }, 'Viga');
  }
}
