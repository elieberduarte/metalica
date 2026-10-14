// Furo: fura a peça onde o projeto não furou — no molde da ferramenta Parafuso.
//
// Clique na face onde vai o furo: ele fica perpendicular a ela, atravessando só aquela
// parede (a mesa, a alma, a chapa). O diâmetro fica no painel de propriedades enquanto a
// ferramenta está ativa — com os diâmetros que o modelo já usa a um clique —, e também dá
// para digitar ("14", "17,5", ou o parafuso: "M12" = furo de 13).
//
// Os eixos da face (linha de centro ao longo da peça e a atravessada), o rótulo com as
// distâncias às bordas e o eixo da peça de baixo são os mesmos da ferramenta Parafuso.
// Além deles, os **furos da peça de baixo** (o banzo sob a terça): cada um aparece
// projetado na face como um circulinho, e perto de um deles o furo novo prende no mesmo
// alinhamento — é a furação de cima casada com a de baixo.
//
// O furo é de verdade na malha: a face recebe o laço do furo costurado ao contorno (o
// mesmo formato dos furos do IFC do TecnoMETAL — o vértice da ponte repetido), a face de
// trás da parede também, e a parede ganha o cilindro vazado. O detalhamento lê o laço como
// lê os furos do IFC. Na chapa paramétrica (a desenhada no editor) o furo entra em `furos`,
// como a ferramenta Chapa faz. Só quando a parede de trás não é uma face reconhecível (ou na
// barra paramétrica, que não tem malha) fica o marcador de antes: um cilindro escuro na
// camada Furos, tipo IfcOpeningElement, com `atributos.furo = {d, ponto, eixo,
// profundidade}`, que o detalhamento também lê como furo e que não conta como parafuso.

import { FerramentaParafuso, tamanhoDoFixador, furoDoParafuso } from './parafuso.js';
import * as C from './_comum.js';
import { LADOS, furarMalha, furoNaChapa, lacoDaForma, ehOblongo, rotuloDaForma, comMalhaBase, faceDoPonto, IndiceDeCaixas,
         paredesNoEixo } from './_furar.js';

//: diâmetros usuais de furo: o furo-padrão da NBR 8800 (d + 1,5 até M24) de M8 a M24 e as brocas redondas
const DIAMETROS = [9.5, 11.5, 13.5, 15.5, 17.5, 21.5, 23.5, 25.5, 14, 18, 22, 26];
const num = (x) => String(Math.round(x * 10) / 10);
const mm = (x) => String(Math.round(x));

/** Lê "13x23" / "13 × 23" (oblongo: largura × comprimento) → {d, comp}, ou null. */
export function lerOblongo(texto) {
  const t = String(texto || '').toUpperCase().replace(/,/g, '.').replace(/\s+/g, '');
  const m = t.match(/^[ØO]?(\d+(?:\.\d+)?)[X×*](\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const a = +m[1], b = +m[2];
  return a > 0 && b > 0 ? { d: Math.min(a, b), comp: Math.max(a, b) } : null;
}

/** Lê "14", "17,5", "Ø14" ou "M12" (o furo-padrão do parafuso, pela norma: d + 1,5) → diâmetro do furo. */
export function lerDiametroDoFuro(texto) {
  const t = String(texto || '').toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M(\d+(?:\.\d+)?)$/);
  if (m) return furoDoParafuso(+m[1]);
  m = t.match(/^[ØO]?(\d+(?:\.\d+)?)(?:MM)?$/);
  if (m) return +m[1];
  return null;
}

/**
 * Furos que uma peça já tem: em cada face, o laço entre um vértice repetido e a sua
 * repetição (a ponte da costura, como o IFC do TecnoMETAL e este editor gravam).
 * Devolve [{c, d, n}] — centro, diâmetro aproximado e normal da face.
 */
export function furosDaMalha(ent) {
  const saida = [];
  if (!ent || ent.tipo !== 'solido' || !ent.faces) return saida;
  for (let k = 0; k < ent.faces.length; k++) {
    const f = ent.faces[k];
    if (f.length < 8) continue;
    const primeiro = new Map();
    for (let i = 0; i < f.length; i++) {
      const v = f[i];
      if (primeiro.has(v)) {
        const i0 = primeiro.get(v);
        const laco = f.slice(i0 + 1, i);
        if (laco.length >= 3 && laco.length <= 40) {
          const pts = laco.map(j => ent.vertices[j]).filter(Boolean);
          if (pts.length >= 3) {
            const c = [0, 1, 2].map(a => pts.reduce((s, q) => s + q[a], 0) / pts.length);
            const ext = Math.max(...[0, 1, 2].map(a => Math.max(...pts.map(q => q[a])) - Math.min(...pts.map(q => q[a]))));
            if (ext <= 80) saida.push({ c, d: ext, n: C.normalDaFace(ent, k) });
          }
        }
        primeiro.clear();                        // o próximo furo da mesma face começa depois da ponte
        continue;
      }
      primeiro.set(v, i);
    }
  }
  return saida;
}

export class FerramentaFuro extends FerramentaParafuso {
  static id = 'furo';
  static nome = 'Furo';
  static atalho = 'F';
  static grupo = 'estrutura';
  static dica = 'Clique na face onde vai o furo · o diâmetro está no painel de propriedades';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<rect x="3" y="6" width="18" height="12" rx="1"/><circle cx="12" cy="12" r="3.2"/><path d="M12 3v2M12 19v2"/></svg>`;
  //: o último diâmetro vale para a próxima vez que a ferramenta abrir
  static diametro = null;
  static eixos = true;
  //: oblongo: o comprimento total do rasgo (null = redondo) e a direção ('peca' = ao
  //: longo da peça, 'atravessado' = na largura da face)
  static comp = null;
  static direcao = 'peca';

  ativar() {
    this._indice = new IndiceDeCaixas(this.documento, { folgaBarra: 300 });
    // o tamanho herdado só serve à sonda da peça de baixo (o alcance do eixo)
    this.tamanho = { d: 12, L: 40, classe: '' };
    // o padrão é o furo do parafuso M12 pela norma (13,5); antes 14
    this.diametro = this.constructor.diametro || furoDoParafuso(12);
    this._atualizarDica();
  }

  /** "M12", "Ø14", "13x23" e os números vão para a caixa de medidas. */
  teclaDeValor(k) { return /^[0-9MmØø]$/.test(k); }

  get rotuloAtual() { return rotuloDaForma({ d: this.diametro, comp: this.constructor.comp, dir: [1, 0, 0] }); }

  /** Folga do centro até a borda: metade do furo (do comprimento, no oblongo) + 1 mm. */
  _margemDaBorda() { return (this.oblongo ? Math.max(this.constructor.comp, this.diametro) : this.diametro) / 2 + 1; }

  get oblongo() { return !!(this.constructor.comp && this.constructor.comp > this.diametro + 0.5); }

  /** A forma do furo neste ponto: {d} ou {d, comp, dir} com a direção pelos eixos da face. */
  _forma(p, n) {
    const d = this.diametro;
    if (!this.oblongo) return { d };
    const f = this.eixosDaFace(p, n);
    let dir = f ? (this.constructor.direcao === 'atravessado' ? f.e2 : f.e1) : C.perpendicular(n);
    return { d, comp: this.constructor.comp, dir: C.normalizar(dir) };
  }

  get nomeAtual() { return `FURO ${this.rotuloAtual}`; }

  _atualizarDica() {
    this.dica(`Furo ${this.rotuloAtual}: clique na face onde ele vai (o diâmetro está no painel de propriedades)`);
    this.medida(this.rotuloAtual);
  }

  _definir(d) {
    this.diametro = d;
    this.constructor.diametro = d;
    this._atualizarDica();
  }

  onValor(texto) {
    const ob = lerOblongo(texto);
    if (ob) {
      this.constructor.comp = ob.comp > ob.d + 0.5 ? ob.comp : null;
      this._definir(ob.d);
      if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
      return true;
    }
    const d = lerDiametroDoFuro(texto);
    if (!d || !(d > 0) || d > 200) { this.dica('Diâmetro do furo em mm (14, 17,5) ou o parafuso (M12 = furo de 13)'); return true; }
    this._definir(d);
    if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
    return true;
  }

  /** Diâmetros de furo que o modelo já usa: chapas paramétricas, furos marcados e os
   *  parafusos (d + 1), do mais comum para o menos: {d, n, origem}. */
  _usadosNoModelo() {
    const cont = new Map();
    const ents = this.documento && this.documento.entidades;
    if (!ents) return [];
    const soma = (d, origem) => {
      if (!(d > 0)) return;
      const k = num(d);
      const r = cont.get(k) || { d: +k, n: 0, origem };
      r.n++;
      cont.set(k, r);
    };
    for (const e of ents.values()) {
      if (e.tipo === 'chapa') { for (const f of (e.furos || [])) soma(f.diametro, 'furo de chapa'); continue; }
      if (e.tipo !== 'solido') continue;
      if (e.atributos && e.atributos.furo) soma(e.atributos.furo.d, 'furo marcado');
      else if (/^BOLT/.test(e.nome || '')) { const t = tamanhoDoFixador(e); if (t) soma(furoDoParafuso(t.d), 'parafuso + folga da norma'); }
      for (const fe of ((e.atributos && e.atributos.furos_editor) || [])) soma(fe.d, 'furo feito no editor');
    }
    return [...cont.values()].sort((a, b) => b.n - a.n).slice(0, 12);
  }

  /** Opções no painel de propriedades (chamado pelo editor). */
  painel(raiz, el) {
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Furo a fazer' }),
                   el('span', { texto: this.rotuloAtual })));
    const g = el('div', { class: 'campos' });
    const inD = el('input', { type: 'number', min: '3', step: '0.5', value: String(this.diametro), title: 'Diâmetro do furo, mm' });
    inD.addEventListener('change', () => { const d = +inD.value; if (d > 0) this._definir(d); });
    const selD = el('select', { title: 'Diâmetros usuais: o furo-padrão da norma (parafuso + 1,5 mm) e as brocas redondas' });
    selD.append(el('option', { value: '', texto: 'usuais…' }));
    for (const d of DIAMETROS) {
      const m = [8, 10, 12, 14, 16, 20, 22, 24].find(x => Math.abs(furoDoParafuso(x) - d) < 0.01);
      selD.append(el('option', { value: String(d), texto: `Ø${num(d).replace('.', ',')}${m ? ` (M${m})` : ''}` }));
    }
    selD.addEventListener('change', () => { if (selD.value) { this._definir(+selD.value); inD.value = selD.value; } });
    // oblongo: largura = o diâmetro acima; comprimento total do rasgo e a direção dele
    const forma = el('select', { title: 'Redondo, ou oblongo (rasgo): a largura é o diâmetro' });
    forma.append(el('option', { value: 'redondo', texto: 'redondo' }), el('option', { value: 'oblongo', texto: 'oblongo' }));
    forma.value = this.oblongo ? 'oblongo' : 'redondo';
    const inC = el('input', { type: 'number', min: '3', step: '0.5', value: String(this.constructor.comp || Math.round(this.diametro + 10)),
                             title: 'Comprimento total do oblongo, mm (ex.: furo 13 com 10 mm de folga = 23)' });
    const dirS = el('select', { title: 'Para onde o oblongo corre, na face clicada' });
    dirS.append(el('option', { value: 'peca', texto: 'ao longo da peça' }), el('option', { value: 'atravessado', texto: 'atravessado' }));
    dirS.value = this.constructor.direcao || 'peca';
    const aplicarForma = () => {
      const ob = forma.value === 'oblongo';
      inC.disabled = !ob; dirS.disabled = !ob;
      const c = +inC.value;
      this.constructor.comp = ob && c > this.diametro + 0.5 ? c : null;
      this.constructor.direcao = dirS.value;
      this._atualizarDica();
      this.limparPrevia();
    };
    forma.addEventListener('change', aplicarForma);
    inC.addEventListener('change', aplicarForma);
    dirS.addEventListener('change', aplicarForma);
    inC.disabled = !this.oblongo; dirS.disabled = !this.oblongo;
    const eixos = el('input', { type: 'checkbox', title: 'Linhas de centro da face sob o cursor e os furos da peça de baixo; o furo prende neles' });
    eixos.checked = !!this.constructor.eixos;
    eixos.addEventListener('change', () => { this.constructor.eixos = eixos.checked; this.limparPrevia(); });
    g.append(el('label', { texto: 'Diâmetro (mm)' }), inD,
             el('label', { texto: 'Usuais' }), selD,
             el('label', { texto: 'Forma' }), forma,
             el('label', { texto: 'Comprimento (mm)' }), inC,
             el('label', { texto: 'Direção' }), dirS,
             el('label', { texto: 'Eixos e furos' }), el('span', {}, eixos, ' mostrar e prender'));
    raiz.append(g);
    this._painelPosicao(raiz, el);
    const usados = this._usadosNoModelo();
    if (usados.length) {
      const box = el('div', { class: 'acoes' });
      for (const u of usados) {
        box.append(el('button', { type: 'button', texto: `Ø${num(u.d)} (${u.n})`, title: `${u.origem}: usar este diâmetro`,
          onclick: () => { this._definir(u.d); this.editor._agendarPaineis('props'); } }));
      }
      raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Já usados no modelo' }), box));
    }
    raiz.append(el('p', { class: 'nota', texto: 'O furo é aberto na própria malha da peça (na chapa desenhada no editor, entra na chapa). Perto de um furo da peça de baixo, o novo prende no mesmo alinhamento. Oblongo: a largura é o diâmetro e o comprimento é o total do rasgo; também dá para digitar "13x23".' }));
  }

  /** Espessura da parede furada: a camada de vértices da peça logo atrás da face; na barra do catálogo, a parede da
   *  seção cortada pelo eixo (antes ia 10 mm em qualquer perfil — a barra só tem as duas pontas). */
  _profundidade(ent, ponto, n) {
    if (!ent) return 10;
    if (ent.tipo === 'chapa') return ent.espessura || 10;
    if (ent.tipo === 'barra') {
      const d = C.normalizar(C.mul(n, -1));
      const so = { entidades: new Map([[ent.id, ent]]), get: (id) => (id === ent.id ? ent : null) };
      const ps = paredesNoEixo(so, C.add(ponto, C.mul(d, -1)), d, 600, { cena: this.editor && this.editor.cena });
      // o eixo começa 1 mm antes da face (t = 1 é a face clicada); parede de mais de 60 mm é o eixo correndo dentro da
      // alma (o furo no meio da mesa do I): devolve o comprimento todo, que o clique recusa
      const pr = ps.find(q => q.t1 > 1.2);
      return pr ? Math.max(0.5, pr.t1 - Math.max(1, pr.t0)) : 10;
    }
    const pts = C.pontosDaEntidade(ent);
    let melhor = null;
    for (const q of pts) {
      const t = C.dot(C.sub(ponto, q), n);
      if (t > 0.5 && (melhor === null || t < melhor)) melhor = t;
    }
    return melhor ? Math.min(melhor, 60) : 10;
  }

  /** O tubo do marcador (redondo ou oblongo): entra pela face em `ponto` (normal `n`) e
   *  atravessa a parede. */
  geometria(ponto, n, prof = 10, forma = null) {
    forma = forma || { d: this.diametro };
    const nn = C.normalizar(n);
    let u = ehOblongo(forma) ? C.sub(forma.dir, C.mul(nn, C.dot(forma.dir, nn))) : C.perpendicular(nn);
    u = C.normalizar(C.comp(u) > 1e-6 ? u : C.perpendicular(nn));
    const v = C.normalizar(C.cross(nn, u));
    const laco = lacoDaForma(forma);
    const topo = C.add(ponto, C.mul(nn, 0.3)), h = prof + 0.6;
    const base = laco.map(([x, y]) => C.add(topo, C.add(C.mul(u, x), C.mul(v, y))));
    const fundo = base.map(q => C.add(q, C.mul(nn, -h)));
    const m = laco.length;
    const vertices = [...base, ...fundo];
    const faces = [base.map((_, i) => i), fundo.map((_, i) => 2 * m - 1 - i)];
    for (let i = 0; i < m; i++) { const j = (i + 1) % m; faces.push([i, m + i, m + j, j]); }
    return { vertices, faces };
  }

  /** Circulinho (polilinha) de raio r no plano de normal n, em c. */
  _circulo(c, n, r, cor) {
    const e1 = C.normalizar(C.perpendicular(n)), e2 = C.normalizar(C.cross(n, e1));
    const pts = [];
    for (let i = 0; i < 24; i++) { const t = (2 * Math.PI * i) / 24; pts.push(C.add(c, C.add(C.mul(e1, r * Math.cos(t)), C.mul(e2, r * Math.sin(t))))); }
    return C.gLinha(pts, cor, { fechada: true });
  }

  /**
   * Ponto ajustado: os eixos da face e o eixo da peça de baixo (herdados da Parafuso) e,
   * por cima deles, os furos da peça de baixo projetados na face — perto de um, o furo
   * novo vai para o mesmo alinhamento.
   */
  ajustar(p, n) {
    const base = super.ajustar(p, n);
    if (!this.constructor.eixos) return base;
    let ponto = base.ponto;
    const extra = [...base.extra];
    const tol = Math.max(8, 0.6 * this.diametro);
    let preso = null;
    const marcadores = [];                                             // furos marcados (sem malha) nas peças de baixo
    for (const m of this._perto(ponto, ponto, 450).entidades.values()) if (m.atributos && m.atributos.furo && m.atributos.furo.peca) marcadores.push(m);
    for (const e of this._atravessadas(ponto, n, p.entidade)) {
      const furos = furosDaMalha(e);
      for (const m of marcadores) if (m.atributos.furo.peca === e.id) furos.push({ c: m.atributos.furo.ponto, d: m.atributos.furo.d, n: C.mul(m.atributos.furo.eixo, -1) });
      for (const f of furos) {
        if (Math.abs(C.dot(f.n, n)) < 0.7) continue;                 // furo numa face que não olha para esta
        const t = C.dot(C.sub(f.c, ponto), n);
        if (Math.abs(t) > 120) continue;
        const q = C.sub(f.c, C.mul(n, t));                           // o furo de baixo levado ao plano da face
        const dd = C.dist(q, ponto);
        if (dd > 400) continue;
        if (dd <= tol && (!preso || dd < preso.dd) && this._dentroDaFace(q, base.face)) preso = { q, dd, f, e };
        else extra.push(this._circulo(C.add(q, C.mul(n, 0.5)), n, Math.max(f.d, 6) / 2, '#8a94a6'));
      }
    }
    if (preso) {
      ponto = preso.q;
      extra.push(this._circulo(C.add(ponto, C.mul(n, 0.5)), n, Math.max(preso.f.d, 6) / 2 + 2, '#0a8f3c'));
      const nomeB = (preso.e.atributos && preso.e.atributos.marcas && (preso.e.atributos.marcas.nome || preso.e.atributos.marcas.posicao)) || preso.e.nome || 'peça de baixo';
      extra.push(C.gRotulo(`no furo Ø${mm(preso.f.d)} de ${nomeB}`, C.add(ponto, C.mul(n, 90)), '#0a8f3c'));
    }
    return { ponto, extra, face: base.face };
  }

  /**
   * Abre o furo na malha: o laço costurado na face clicada e na face de trás da parede,
   * e o cilindro entre elas. Devolve {vertices, faces, profundidade} ou null (a face de
   * trás não foi reconhecida, ou o furo não cabe na face).
   */
  onMover(p) {
    this.limparPrevia();
    p = this._naFace(p);
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const { ponto, extra, face } = this.ajustar(p, n);
    const alvo = this.documento.get(p.entidade);
    const forma = this._forma(p, n);
    const pts = this._pontosDoPadrao(ponto, face);
    const prof0 = this._profundidade(alvo, ponto, n);
    const bate = alvo && alvo.tipo === 'barra' && prof0 > 60;
    const prof = Math.min(prof0, 60);
    const partes = pts.map(q => { const g = this.geometria(q, n, prof, forma); return C.gMalha(g.vertices, g.faces, bate ? '#b91c1c' : '#1f2430', 0.85); });
    const rot = `${pts.length > 1 ? pts.length + ' × ' : ''}${this.rotuloAtual} · ` + (bate ? 'EM CIMA DA ALMA: vá para o gabarito' : `parede ${num(prof).replace(".", ",")} mm`);
    const lado = face ? C.mul(face.e2, -((C.dot(ponto, face.e2) - face.min2) + 45)) : [0, 0, 0];
    this.previa(C.grupo(...partes, C.gRotulo(rot, C.add(ponto, C.add(C.mul(n, 20), lado))), ...extra));
  }

  onPonto(p) {
    p = this._naFace(p);
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const { ponto, face } = this.ajustar(p, n);
    const pts = this._pontosDoPadrao(ponto, face);
    const d = this.diametro;
    const forma = this._forma(p, n);
    const extraForma = ehOblongo(forma) ? { comp: forma.comp, dir: C.copiar(forma.dir) } : {};
    const alvo = this.documento.get(p.entidade);
    const vezes = pts.length > 1 ? `${pts.length} furos` : 'Furo';
    if (alvo && alvo.tipo === 'chapa') {
      // chapa paramétrica: o furo entra na própria chapa (é o que o IFC e a lista leem)
      const furos = (alvo.furos || []).map(f => ({ ...f }));
      for (const q of pts) furos.push(furoNaChapa(alvo, q, forma));
      this.executar(C.cmdAlterar(alvo.id, { furos }, 'Furar chapa'));
      this.dica(`${vezes} ${this.rotuloAtual} na chapa · clique no próximo (Esc sai)`);
      return;
    }
    if (alvo && alvo.tipo === 'solido' && alvo.faces && alvo.faces.length) {
      // malha (o perfil do IFC): os furos um depois do outro na mesma malha
      let atual = alvo, feitos = 0, fora = 0, prof = 0;
      const registros = [...((alvo.atributos && alvo.atributos.furos_editor) || [])];
      for (const q of pts) {
        const malha = furarMalha(atual, q === ponto ? p.face : -1, q, n, forma);
        if (!malha) { fora++; continue; }
        registros.push({ d, ...extraForma, ponto: C.copiar(q), eixo: C.mul(C.normalizar(n), -1), profundidade: malha.profundidade });
        atual = { ...atual, vertices: malha.vertices, faces: malha.faces };
        prof = malha.profundidade;
        feitos++;
      }
      if (feitos) {
        const atributos = comMalhaBase(alvo, { ...(alvo.atributos || {}), furos_editor: registros });
        this.executar(C.cmdAlterar(alvo.id, { vertices: atual.vertices, faces: atual.faces, atributos }, vezes));
        this.dica(`${feitos > 1 ? feitos + ' furos' : 'Furo'} ${this.rotuloAtual} aberto(s) na peça (parede de ${num(prof).replace(".", ",")} mm)`
                  + (fora ? ` · ${fora} não coube(ram) na face (borda ou outro furo)` : '') + ' · clique no próximo (Esc sai)');
        return;
      }
      // o furo não coube na face (perto demais da borda, ou em cima de outro furo): nada é criado — antes virava um
      // marcador no canto da peça. Só a parede de trás não reconhecida (a face existe e o furo cabe) cai no marcador.
      const k = faceDoPonto(alvo, ponto, n, p.face);
      if (k < 0 || !this._dentroDaFace(ponto, this.eixosDaFace(p, n))) {
        this.dica(`O furo ${this.rotuloAtual} não cabe aí: fica a menos de ${mm(this._margemDaBorda())} mm da borda da face ou em cima de outro furo — clique mais para dentro`);
        return;
      }
    }
    // a barra do catálogo (a malha dela é feita pela cena, que abre o furo pelo marcador) e a parede de trás não
    // reconhecida: o marcador na camada Furos, que o detalhamento lê como furo
    let prof = this._profundidade(alvo, ponto, n);
    if (alvo && alvo.tipo === 'barra' && prof > 60) {
      this.dica(`O furo ${this.rotuloAtual} cai em cima da alma de ${alvo.perfil} (o meio da mesa): mova para o gabarito, fora da alma — nada foi furado`);
      return;
    }
    prof = Math.min(prof, 60);
    const novos = pts.map(q => {
      const g = this.geometria(q, n, prof, forma);
      return {
        tipo: 'solido', id: C.novoId('furo'), nome: this.nomeAtual, camada: 'Furos', material: 'Cor #1f2430',
        visivel: true, bloqueada: false, grupo: '',
        vertices: g.vertices, faces: g.faces, arestas_vivas: [],
        atributos: {
          tipo_ifc: 'IfcOpeningElement', exportar: false, criado_no_editor: true,
          furo: { d, ...extraForma, ponto: C.copiar(q), eixo: C.mul(C.normalizar(n), -1), profundidade: prof, peca: alvo ? alvo.id : null },
        },
      };
    });
    this.executar(C.cmdAdicionar(novos, vezes));
    this.dica(alvo && alvo.tipo === 'barra'
      ? `${vezes} ${this.rotuloAtual} aberto(s) na barra (parede de ${num(prof).replace(".", ",")} mm) · clique no próximo (Esc sai)`
      : `${vezes} ${this.rotuloAtual} marcado(s) (a parede de trás não foi reconhecida: fica o marcador, que o detalhamento lê como furo) · clique no próximo (Esc sai)`);
  }
}

export default FerramentaFuro;
