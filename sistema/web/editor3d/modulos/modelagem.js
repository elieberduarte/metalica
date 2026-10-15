// Métodos do editor 3D: a modelagem estrutural pela seleção (14/10/2026), como no Revit e no Tekla — escolhe as peças,
// preenche o diálogo e a estrutura sai no lugar, numa entrada de desfazer:
//
// * Terças por espaçamento — nas tesouras/vigas selecionadas, sentadas no topo, nunca acima do espaçamento pedido;
// * Treliça entre banzos — montantes e diagonais (Pratt, Howe, Warren) entre os dois banzos, com o encaixe das almas;
// * Contraventamento em X — entre duas barras paralelas, num ou em vários painéis (na cobertura, já nos suportes SC1);
// * Pilares nos eixos — um pilar em cada cruzamento escolhido dos eixos gravados da obra;
// * Viga entre pilares — no nível pedido, com o topo da viga no nível;
// * Longarinas de fechamento — na face de fora dos pilares de uma parede, alma na horizontal, boca para baixo;
// * Correntes entre terças — no meio (ou nos terços) de cada vão, de centro a centro das terças;
// * Mão-francesa — da alma da terça à mesa de baixo do apoio, a 45°, nos dois lados;
// * Bases nos pilares dos eixos — a placa de base da biblioteca em todos os pilares dos cruzamentos marcados;
// * Copiar para os eixos — a tesoura/o pórtico do eixo dele para os eixos paralelos marcados (aqui mesmo, sem o servidor).
//
// A geometria é do servidor (nucleo3d/modelagem.py); aqui ficam os diálogos e o comando. Enquanto o diálogo está aberto,
// as peças aparecem translúcidas no lugar (a prévia, como o fantasma do Mover) e se refazem a cada campo mudado; o
// diálogo vai para o canto e o fundo clareia para deixar ver o modelo.

import * as THREE from 'three';
import { el, numero } from '../editor.js';
import * as C from '../ferramentas/_comum.js';

// a prévia: materiais da casa (nunca descartados), malhas do cache da cena
const MAT_PREVIA = new THREE.MeshBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.35, depthWrite: false, side: THREE.DoubleSide });
const LIN_PREVIA = new THREE.LineBasicMaterial({ color: 0x1d4ed8, transparent: true, opacity: 0.9 });
MAT_PREVIA.userData.compartilhada = true;
LIN_PREVIA.userData.compartilhada = true;
const ESPERA_PREVIA = 250;          // ms depois do último campo mudado

let estiloPrevia = false;
function garantirEstiloPrevia() {
  if (estiloPrevia) return;
  estiloPrevia = true;
  document.head.append(el('style', { texto:
    'dialog.com-previa { margin: 64px 16px auto auto; max-width: min(420px, calc(100vw - 32px)); }' +
    'dialog.com-previa::backdrop { background: rgba(10, 18, 30, .06); }' +
    'dialog .estado-previa { margin: 8px 0 0; font-size: 12px; color: var(--texto-fraco, #64748b); }' +
    'dialog .estado-previa.erro { color: var(--vermelho, #dc2626); }' }));
}

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

/** os cruzamentos dos eixos com a posição em planta: [{nome, x, y}] */
function nosDosEixos(eixos) {
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
      fora.push({ nome: /^[A-Za-z]+$/.test(n1) ? `${n1}-${n2}` : `${n2}-${n1}`, x: e1.a[0] + d1[0] * t, y: e1.a[1] + d1[1] * t });
    }
  }
  return fora.sort((a, b) => a.nome.localeCompare(b.nome));
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
  async _pedirModelagem(pedido, rota = '/api/modelo/modelar') {
    const resp = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ documento: this.documento.paraJSON(), projeto: this.projeto || null, ...pedido }) });
    const r = await resp.json();
    if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    return r;
  }

  /** O diálogo com a prévia ao vivo: `pedido()` lê o formulário; devolve {pedido, pronto} no OK (pronto = a resposta
   *  da prévia, quando o formulário não mudou depois dela) ou null. */
  async _dialogoComPrevia({ titulo, corpo, ok, pedido, rota }) {
    garantirEstiloPrevia();
    const estado = el('p', { class: 'estado-previa', texto: 'Prévia…' });
    corpo.append(estado);
    const d = this.el.dialogo;
    let grupo = null, timer = null, vez = 0, ultima = null, fechado = false;
    const tirar = () => {
      if (!grupo) return;
      this.cena.previa.remove(grupo);
      grupo.traverse(x => { if (x.isLineSegments && x.geometry) x.geometry.dispose(); });
      grupo = null;
      this.cena.pedirQuadro();
    };
    const atualizar = async () => {
      const minha = ++vez;
      let p;
      try { p = pedido(); } catch (e) {
        tirar();
        ultima = null;
        estado.className = 'estado-previa erro';
        estado.textContent = e.message;
        return;
      }
      const chave = JSON.stringify(p);
      try {
        const r = await this._pedirModelagem(p, rota);
        await this._perfisDaPrevia(r.novas || []);
        if (minha !== vez || fechado) return;
        tirar();
        grupo = this._grupoDaPrevia(r.novas || []);
        this.cena.addPrevia(grupo);
        ultima = { chave, r };
        const res = r.resumo || {};
        const n = (r.novas || []).length;
        const partes = [`${n} peça${n === 1 ? '' : 's'}`];
        if (res.linhas) partes.push(`${res.linhas} linhas`);
        if (res.passo) partes.push(`passo ${numero(res.passo, 0)} mm`);
        if (res.paineis) partes.push(`${res.paineis} painéis`);
        if (res.suportes) partes.push(`${res.suportes} suportes`);
        estado.className = 'estado-previa';
        estado.textContent = `Prévia: ${partes.join(' · ')}` + ((r.avisos || []).length ? ` — ${r.avisos.join('; ')}` : '');
      } catch (e) {
        if (minha !== vez || fechado) return;
        tirar();
        ultima = null;
        estado.className = 'estado-previa erro';
        estado.textContent = e.message;
      }
    };
    const mudou = () => { clearTimeout(timer); timer = setTimeout(atualizar, ESPERA_PREVIA); };
    corpo.addEventListener('input', mudou);
    corpo.addEventListener('change', mudou);
    d.classList.add('com-previa');
    atualizar();
    let res;
    try { res = await this.dialogo({ titulo, corpo, ok }); }
    finally {
      fechado = true;
      clearTimeout(timer);
      corpo.removeEventListener('input', mudou);
      corpo.removeEventListener('change', mudou);
      d.classList.remove('com-previa');
      tirar();
    }
    if (res !== 'ok') return null;
    const p = pedido();
    return { pedido: p, pronto: ultima && ultima.chave === JSON.stringify(p) ? ultima.r : null };
  }

  /** As seções que o catálogo do editor não traz (dobrados, redondos): pedidas ao servidor antes de desenhar. */
  async _perfisDaPrevia(novas) {
    const cat = this.cena.catalogo && this.cena.catalogo.perfis;
    if (!(cat instanceof Map)) return;
    const faltam = [...new Set(novas.filter(d => d.tipo === 'barra').map(d => d.perfil))].filter(n => n && !cat.has(n));
    if (!faltam.length) return;
    try {
      const r = await this.api.perfis(faltam);
      const lista = (r && r.perfis) || [];
      const ja = new Set((this.catalogo.perfis || []).map(p => p.nome));
      for (const p of lista) if (!ja.has(p.nome)) this.catalogo.perfis.push(p);
      this.cena.acrescentarPerfis(lista);
    } catch (e) { /* sem a seção, a prévia sai com a padrão */ }
  }

  /** As barras e as chapas da resposta como malhas translúcidas (do cache da cena) e o eixo de cada barra. */
  _grupoDaPrevia(novas) {
    const g = new THREE.Group();
    g.name = 'previa-modelagem';
    g.renderOrder = 980;
    const eixos = [];
    for (const d of novas) {
      if (d.tipo !== 'barra' && d.tipo !== 'chapa') continue;
      if (d.tipo === 'barra') eixos.push(...d.inicio, ...d.fim);
      let geo;
      try { geo = d.tipo === 'barra' ? this.cena._geometriaBarra(d) : this.cena._geometriaChapa(d); } catch (e) { geo = null; }
      if (!geo || !geo.geom) continue;
      const m = new THREE.Mesh(geo.geom, MAT_PREVIA);
      m.matrixAutoUpdate = false;
      m.matrix.copy(geo.matriz);
      m.userData.compartilhada = true;           // a malha é do cache da cena: limparPrevia não a descarta
      m.raycast = () => {};
      g.add(m);
    }
    if (eixos.length) {
      const bg = new THREE.BufferGeometry();
      bg.setAttribute('position', new THREE.Float32BufferAttribute(eixos, 3));
      const l = new THREE.LineSegments(bg, LIN_PREVIA);
      l.raycast = () => {};
      g.add(l);
    }
    return g;
  }

  async _modelar(pedido, rotulo, pronto = null) {
    let r = pronto;
    if (!r) {
      try {
        this.dica(`${rotulo}…`);
        r = await this._pedirModelagem(pedido);
      } catch (e) { this.aviso(`${rotulo}: ${e.message}`, 'erro', 0); return null; }
    }
    const cmd = this._comandoDaLigacao(r, rotulo);
    if (!cmd) { this.aviso(`${rotulo}: nada a lançar.`, 'info'); return r; }
    this.executar(cmd);
    const novas = (r.novas || []).map(d => d.id).filter(id => this.documento.get(id));
    this.selecao.definir(novas);
    await this._completarPerfis();
    // peças que saem com ligação (o SC1 do contravento): entram na conferência das ligações desatualizadas
    if ((r.novas || []).some(d => d.atributos && d.atributos.ligacao) && typeof this._conferirLigacoes === 'function') this._conferirLigacoes();
    const res = r.resumo || {};
    const partes = [`${novas.length} peça${novas.length === 1 ? '' : 's'}`];
    if (res.passo) partes.push(`passo ${numero(res.passo, 0)} mm`);
    if (res.paineis) partes.push(`${res.paineis} painéis`);
    if (res.suportes) partes.push(`${res.suportes} suportes`);
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
    const e = await this._dialogoComPrevia({ titulo: 'Terças por espaçamento', corpo, ok: 'Lançar terças', pedido: () => ({ ferramenta: 'tercas', ids: apoios.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Terças', e.pronto);
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
    const e = await this._dialogoComPrevia({ titulo: 'Treliça entre banzos', corpo, ok: 'Lançar treliça', pedido: () => ({ ferramenta: 'trelica', ids: bs.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Treliça', e.pronto);
  }

  async dialogoContraventoX() {
    const bs = this.selecao.entidades.filter(e => e.tipo === 'barra');
    if (bs.length !== 2) { this.dica('Selecione as duas barras paralelas do vão contraventado: dois pilares, ou os banzos de duas tesouras.'); return; }
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('contraventamento', "FE RED 1/2''") },
      { chave: 'paineis', rotulo: 'Painéis', tipo: 'numero', valor: vert(bs[0]) ? 2 : 1 },
      { chave: 'margem', rotulo: 'Afastamento das pontas (mm)', tipo: 'numero', valor: 0 },
      { chave: 'suporte', rotulo: 'Nas pontas', tipo: [['sc1', 'suportes SC1 no topo dos banzos (cobertura)'], ['nenhum', 'sem suporte, de eixo a eixo']],
        valor: vert(bs[0]) ? 'nenhum' : 'sc1' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: 'Duas diagonais por painel. Com o SC1 (o detalhe validado na portaria), cada tirante sai esticado de furo a furo nas cantoneiras em pé no topo dos banzos, com marca, conjunto e solda, e a ligação continua editável. Entre pilares, ou com outro detalhe, lance sem suporte e use o Aplicar ligação.' }));
    const e = await this._dialogoComPrevia({ titulo: 'Contraventamento em X', corpo, ok: 'Lançar', pedido: () => ({ ferramenta: 'contravento', ids: bs.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Contraventamento', e.pronto);
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
    // nenhum cruzamento marcado: nada (o servidor, com a lista vazia, lançaria em todos)
    const pedido = () => {
      const escolhidos = caixas.filter(([, c]) => c.checked).map(([n]) => n);
      if (!escolhidos.length) throw new Error('Nenhum cruzamento escolhido.');
      return { ferramenta: 'pilares', eixos, cruzamentos: escolhidos, parametros: f.ler() };
    };
    todos.addEventListener('click', () => corpo.dispatchEvent(new Event('change')));
    let e;
    try { e = await this._dialogoComPrevia({ titulo: 'Pilares nos eixos', corpo, ok: 'Lançar pilares', pedido }); }
    catch (err) { this.dica(err.message); return; }
    if (e) await this._modelar(e.pedido, 'Pilares', e.pronto);
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
    const e = await this._dialogoComPrevia({ titulo: 'Viga entre pilares', corpo, ok: 'Lançar viga', pedido: () => ({ ferramenta: 'viga', ids: pilares.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Viga', e.pronto);
  }

  async dialogoLongarinas() {
    const pilares = this.selecao.entidades.filter(e => e.tipo === 'barra' && vert(e));
    if (pilares.length < 2) { this.dica('Selecione os pilares de uma parede: as longarinas vão de um ao outro, na face de fora.'); return; }
    const base = Math.max(...pilares.map(b => Math.min(b.inicio[2], b.fim[2])));
    const topo = Math.min(...pilares.map(b => Math.max(b.inicio[2], b.fim[2])));
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('longarina', 'Ue 150×60×20×2,25') },
      { chave: 'espacamento', rotulo: 'Espaçamento máximo (mm)', tipo: 'numero', valor: 1900 },
      { chave: 'primeira', rotulo: 'Primeira fiada, altura (mm)', tipo: 'numero', valor: Math.round(base + 1900) },
      { chave: 'ultima', rotulo: 'Última fiada, altura (mm)', tipo: 'numero', valor: Math.round(topo - 300) },
      { chave: 'continua', rotulo: 'Longarina', tipo: [['nao', 'uma por vão'], ['sim', 'contínua']], valor: 'nao' },
      { chave: 'balanco', rotulo: 'Balanço nas pontas (mm)', tipo: 'numero', valor: 0 },
      { chave: 'lado', rotulo: 'Lado', tipo: [['fora', 'de fora (longe do meio do modelo)'], ['dentro', 'de dentro']], valor: 'fora' },
      { chave: 'boca', rotulo: 'Boca do U para', tipo: [['baixo', 'baixo (não junta água)'], ['cima', 'cima']], valor: 'baixo' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: `${pilares.length} pilares. As fiadas encostam na face mais saliente dos pilares (o plano do fechamento), com a alma na horizontal, igualmente espaçadas entre a primeira e a última.` }));
    const e = await this._dialogoComPrevia({ titulo: 'Longarinas de fechamento', corpo, ok: 'Lançar longarinas', pedido: () => ({ ferramenta: 'longarinas', ids: pilares.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Longarinas', e.pronto);
  }

  async dialogoCorrentes() {
    const tercas = this.selecao.entidades.filter(e => e.tipo === 'barra' && !vert(e));
    if (tercas.length < 2) { this.dica('Selecione as terças (duas linhas ou mais, de uma água ou das duas): as correntes vão de uma linha à outra.'); return; }
    const f = this._formModelagem([
      { chave: 'linhas', rotulo: 'Correntes por vão', tipo: [['1', '1 (no meio)'], ['2', '2 (nos terços)'], ['3', '3 (nos quartos)']], valor: '1' },
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('corrente', 'Barra ø 16 mm') },
      { chave: 'cumeeira', rotulo: 'Pela cumeeira', tipo: [['v', 'em V (o tirante de cumeeira do gerador)'], ['reta', 'reta, de terça a terça']], valor: 'v' },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: 'Os vãos saem das tesouras e vigas que passam por baixo das terças (e das pontas delas); a corrente vai de centro a centro das terças vizinhas, pelo furo na alma.' }));
    const e = await this._dialogoComPrevia({ titulo: 'Correntes entre terças', corpo, ok: 'Lançar correntes', pedido: () => ({ ferramenta: 'correntes', ids: tercas.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Correntes', e.pronto);
  }

  /** Copiar para os eixos: a tesoura (o pórtico, o detalhe) selecionada copiada do eixo dela para os eixos marcados,
   *  paralelos — como o "copiar para os níveis" do Revit. Os marcadores de furo e as cotas vão junto; a prévia é o
   *  fantasma das próprias peças em cada eixo marcado. */
  async dialogoCopiarParaEixos() {
    const ids = C.idsSelecionados(this);
    if (!ids.length) { this.dica('Selecione as peças a copiar (a tesoura, o pórtico, o detalhe): elas vão do eixo delas para os eixos que você marcar.'); return; }
    const ref = (this.inferencia && this.inferencia.referencias) || {};
    const eixos = (ref.eixos || this._eixosRef || []).filter(e => e && e.a && e.b && Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1]) > 1);
    if (eixos.length < 2) { this.aviso('A obra não tem eixos gravados: grave-os em Lançamento → Planta de lançamento (ou Detalhamentos → Eixos da obra).', 'atencao', 0); return; }
    const dirDe = (e) => { const d = [e.b[0] - e.a[0], e.b[1] - e.a[1]]; const n = Math.hypot(...d); return [d[0] / n, d[1] / n]; };
    // a distância (com sinal) de um ponto em planta à reta do eixo
    const distA = (e, p) => { const d = dirDe(e); return (p[0] - e.a[0]) * -d[1] + (p[1] - e.a[1]) * d[0]; };
    const centro = C.caixaDe(this.documento, ids).centro;
    const origem0 = eixos.reduce((m, e) => (Math.abs(distA(e, centro)) < Math.abs(distA(m, centro)) ? e : m), eixos[0]);
    const escolha = el('select');
    for (const e of eixos) escolha.append(el('option', { value: e.nome, texto: `${e.nome} (a ${numero(Math.abs(distA(e, centro)), 0)} mm da seleção)`, selected: e === origem0 }));
    const marcas = el('div', { style: 'display:flex;flex-wrap:wrap;gap:4px 12px;max-height:160px;overflow:auto' });
    const estado = el('p', { class: 'estado-previa' });
    let caixas = [];
    const origem = () => eixos.find(e => e.nome === escolha.value) || origem0;
    const paralelos = (o) => { const d0 = dirDe(o); return eixos.filter(e => e !== o && Math.abs(d0[0] * dirDe(e)[0] + d0[1] * dirDe(e)[1]) > 0.999); };
    const montarCaixas = () => {
      marcas.replaceChildren();
      caixas = paralelos(origem()).map(e => {
        const c = el('input', { type: 'checkbox' });
        marcas.append(el('label', { style: 'white-space:nowrap' }, c, ` ${e.nome}`));
        return [e, c];
      });
      if (!caixas.length) marcas.append(el('span', { texto: 'nenhum eixo paralelo ao de origem' }));
    };
    montarCaixas();
    const todos = el('button', { type: 'button', texto: 'Todos / nenhum' });
    todos.addEventListener('click', () => { const v = !caixas.every(([, c]) => c.checked); for (const [, c] of caixas) c.checked = v; atualizar(); });
    // o deslocamento em planta do eixo de origem até o eixo de destino (perpendicular a eles)
    const deslocamento = (o, e) => { const d = dirDe(o); const s = distA(o, e.a); return [-d[1] * s, d[0] * s, 0]; };
    const destinos = () => caixas.filter(([, c]) => c.checked).map(([e]) => e);
    garantirEstiloPrevia();
    const fantasmas = [];
    const tirar = () => { for (const f of fantasmas.splice(0)) this.cena.previa.remove(f.obj); this.cena.pedirQuadro(); };
    const atualizar = () => {
      tirar();
      const o = origem();
      for (const e of destinos()) {
        const dl = deslocamento(o, e);
        const f = C.fantasmaDe(this, ids);
        C.posicionarFantasma(f, (q) => C.add(q, dl), (v) => v);
        this.cena.addPrevia(f.obj);
        fantasmas.push(f);
      }
      const n = destinos().length;
      estado.textContent = n ? `Prévia: ${ids.length} peça${ids.length === 1 ? '' : 's'} × ${n} eixo${n === 1 ? '' : 's'}` : 'Marque os eixos de destino.';
    };
    escolha.addEventListener('change', () => { montarCaixas(); atualizar(); });
    marcas.addEventListener('change', atualizar);
    const corpo = el('div', {}, el('div', { class: 'campos' }, el('label', { texto: 'Eixo de origem' }), escolha),
      el('p', { class: 'explica', texto: `${ids.length} peça${ids.length === 1 ? '' : 's'} selecionada${ids.length === 1 ? '' : 's'}. Copiar para os eixos:` }), marcas, todos, estado);
    atualizar();
    const d = this.el.dialogo;
    d.classList.add('com-previa');
    let r;
    try { r = await this.dialogo({ titulo: 'Copiar para os eixos', corpo, ok: 'Copiar' }); }
    finally { d.classList.remove('com-previa'); tirar(); }
    if (r !== 'ok' || !destinos().length) return;
    const o = origem();
    const { pecas } = C.pecasParaTransformar(this.documento, ids.map(id => this.documento.get(id)).filter(Boolean), true);
    const cmds = [], novos = [];
    for (const e of destinos()) {
      const dl = deslocamento(o, e);
      const lote = C.copiasTransformadas(pecas, (q) => C.add(q, dl), (v) => v);
      // o grupo copiado aponta para as cópias dos filhos (e o filho, para a cópia do grupo)
      const mapa = new Map(pecas.map((p, i) => [p.id, lote[i].id]));
      for (const c of lote) {
        if (Array.isArray(c.filhos)) c.filhos = c.filhos.map(id => mapa.get(id) || id);
        if (c.grupo && mapa.has(c.grupo)) c.grupo = mapa.get(c.grupo);
      }
      novos.push(...lote.map(c => c.id));
      if (lote.length) cmds.push(C.cmdAdicionar(lote, 'Copiar para os eixos'));
    }
    if (!cmds.length) return;
    this.executar(C.cmdComposto(cmds, 'Copiar para os eixos'));
    this.selecao.definir(novos.filter(id => this.documento.get(id)));
    this.aviso(`Copiar para os eixos: ${pecas.length} peça${pecas.length === 1 ? '' : 's'} em ${destinos().map(e => e.nome).join(', ')}.`, 'info', 8000);
  }

  async dialogoMaoFrancesa() {
    const bs = this.selecao.entidades.filter(e => e.tipo === 'barra' && !vert(e));
    const tercas = bs.filter(b => ['terça', 'terca', 'longarina'].includes(String(b.papel).toLowerCase()));
    if (!tercas.length) { this.dica('Selecione as terças (e, se quiser, os apoios): a mão-francesa vai da alma da terça à mesa de baixo da tesoura ou viga por baixo.'); return; }
    const apoios = bs.length - tercas.length;
    const f = this._formModelagem([
      { chave: 'perfil', rotulo: 'Perfil', tipo: 'perfil', valor: this._perfilSugerido('mão-francesa', "L 1 1/2'' X 1/8''") },
      { chave: 'angulo', rotulo: 'Ângulo com a horizontal (°)', tipo: 'numero', valor: 45 },
      { chave: 'lados', rotulo: 'Lados do apoio', tipo: [['ambos', 'os dois'], ['um', 'um só']], valor: 'ambos' },
      { chave: 'recuo', rotulo: 'Furo a partir da face (mm)', tipo: 'numero', valor: 30 },
    ]);
    const corpo = el('div', {}, f.corpo, el('p', { class: 'explica', texto: `${tercas.length} terça${tercas.length === 1 ? '' : 's'}` +
      (apoios ? ` e ${apoios} apoio${apoios === 1 ? '' : 's'} escolhido${apoios === 1 ? '' : 's'}.` : '; os apoios são as tesouras e vigas logo abaixo delas.') +
      ' A cantoneira fica no plano vertical da terça, com uma aba deitada nele (encosta na alma da terça).' }));
    const e = await this._dialogoComPrevia({ titulo: 'Mão-francesa', corpo, ok: 'Lançar', pedido: () => ({ ferramenta: 'mao_francesa', ids: bs.map(b => b.id), parametros: f.ler() }) });
    if (e) await this._modelar(e.pedido, 'Mão-francesa', e.pronto);
  }

  /** Bases nos pilares pelos eixos: a placa de base (a ligação da biblioteca, rotulada ou engastada) em todos os
   *  pilares dos cruzamentos marcados de uma vez — os que já têm base ficam de fora. */
  async dialogoBasesNosEixos() {
    const ref = (this.inferencia && this.inferencia.referencias) || {};
    const eixos = (ref.eixos || this._eixosRef || []).filter(e => e && e.a && e.b);
    if (eixos.length < 2) { this.aviso('A obra não tem eixos gravados: grave-os em Lançamento → Planta de lançamento (ou Detalhamentos → Eixos da obra).', 'atencao', 0); return; }
    const pilares = [...this.documento.entidades.values()].filter(e => e.tipo === 'barra' && vert(e));
    // o pilar de cada cruzamento: o pé (a ponta de baixo) a até 150 mm do nó, em planta
    const pe = (b) => (b.inicio[2] <= b.fim[2] ? b.inicio : b.fim);
    const comBase = new Set();
    for (const e of this.documento.entidades.values()) {
      const l = e.atributos && e.atributos.ligacao;
      if (l && String(l.tipo).startsWith('placa_base')) for (const id of (l.pecas || [])) comBase.add(id);
    }
    const nos = nosDosEixos(eixos).map(n => ({ ...n, pilar: pilares.find(b => Math.hypot(pe(b)[0] - n.x, pe(b)[1] - n.y) <= 150) }))
      .filter(n => n.pilar);
    if (!nos.length) { this.aviso('Nenhum pilar nos cruzamentos dos eixos gravados (o pé a até 150 mm do cruzamento).', 'atencao', 0); return; }
    let tipos;
    try { tipos = await this._tiposDeLigacao(); } catch (e) { this.aviso(`Não foi possível ler as ligações: ${e.message}`, 'erro', 0); return; }
    tipos = tipos.filter(t => String(t.id).startsWith('placa_base'));
    const escolha = el('select');
    for (const t of tipos) escolha.append(el('option', { value: t.id, texto: t.nome }));
    const lugar = el('div');
    let form = null;
    const trocar = () => { form = this._formParametros(tipos.find(t => t.id === escolha.value)); lugar.replaceChildren(form.corpo); };
    escolha.addEventListener('change', trocar);
    trocar();
    const marcas = el('div', { style: 'display:flex;flex-wrap:wrap;gap:4px 12px;max-height:160px;overflow:auto' });
    const caixas = nos.map(n => {
      const ja = comBase.has(n.pilar.id);
      const c = el('input', { type: 'checkbox', checked: !ja, disabled: ja });
      marcas.append(el('label', { style: 'white-space:nowrap', title: ja ? 'já tem placa de base' : n.pilar.perfil }, c, ` ${n.nome}${ja ? ' (já tem)' : ''}`));
      return [n, c];
    });
    const todos = el('button', { type: 'button', texto: 'Todos / nenhum' });
    todos.addEventListener('click', () => {
      const livres = caixas.filter(([, c]) => !c.disabled);
      const v = !livres.every(([, c]) => c.checked);
      for (const [, c] of livres) c.checked = v;
      corpo.dispatchEvent(new Event('change'));
    });
    const corpo = el('div', {}, el('div', { class: 'campos' }, el('label', { texto: 'Base' }), escolha), lugar,
      el('p', { class: 'explica', texto: `${nos.length} pilares nos cruzamentos dos eixos. A placa, os chumbadores, a marca, o conjunto e a solda saem como no Aplicar ligação, e a ligação continua editável.` }),
      marcas, todos);
    const pedido = () => {
      const ids = caixas.filter(([, c]) => c.checked && !c.disabled).map(([n]) => n.pilar.id);
      if (!ids.length) throw new Error('Nenhum pilar marcado.');
      return { tipo: escolha.value, ids, parametros: form.ler() };
    };
    let e;
    try { e = await this._dialogoComPrevia({ titulo: 'Bases nos pilares dos eixos', corpo, ok: 'Lançar bases', pedido, rota: '/api/modelo/ligacao' }); }
    catch (err) { this.dica(err.message); return; }
    if (e) await this._pedirLigacao(e.pedido, 'Bases nos pilares');
  }
}
