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

import { FerramentaParafuso, prisma, tamanhoDoFixador } from './parafuso.js';
import * as C from './_comum.js';

//: diâmetros usuais de furo (parafuso + 1 mm, e os oblongos da terça abertos por broca)
const DIAMETROS = [9, 11, 13, 14, 15, 17.5, 18, 20, 22, 24, 26, 28];
//: lados do laço do furo na malha
const LADOS = 16;
const num = (x) => String(Math.round(x * 10) / 10);
const mm = (x) => String(Math.round(x));

/** Lê "14", "17,5", "Ø14" ou "M12" (o furo do parafuso: d + 1) → diâmetro do furo. */
export function lerDiametroDoFuro(texto) {
  const t = String(texto || '').toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M(\d+(?:\.\d+)?)$/);
  if (m) return +m[1] + 1;
  m = t.match(/^[ØO]?(\d+(?:\.\d+)?)(?:MM)?$/);
  if (m) return +m[1];
  return null;
}

/** Área assinada de um polígono 2D (positiva = anti-horária). */
function areaAssinada(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; a += p[0] * q[1] - q[0] * p[1]; }
  return a / 2;
}

function dentroDoPoligono(pt, pts) {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

function distPontoSegmento2d(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L2 = dx * dx + dy * dy;
  const t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
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

  ativar() {
    this._caixas = new Map();
    // o tamanho herdado só serve à sonda da peça de baixo (o alcance do eixo)
    this.tamanho = { d: 12, L: 40, classe: '' };
    this.diametro = this.constructor.diametro || 14;
    this._atualizarDica();
  }

  get rotuloAtual() { return `Ø${num(this.diametro)}`; }

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
      else if (/^BOLT/.test(e.nome || '')) { const t = tamanhoDoFixador(e); if (t) soma(t.d + 1, 'parafuso + 1 mm'); }
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
    const selD = el('select', { title: 'Diâmetros usuais (parafuso + 1 mm)' });
    selD.append(el('option', { value: '', texto: 'usuais…' }));
    for (const d of DIAMETROS) selD.append(el('option', { value: String(d), texto: `Ø${num(d)}` }));
    selD.addEventListener('change', () => { if (selD.value) { this._definir(+selD.value); inD.value = selD.value; } });
    const eixos = el('input', { type: 'checkbox', title: 'Linhas de centro da face sob o cursor e os furos da peça de baixo; o furo prende neles' });
    eixos.checked = !!this.constructor.eixos;
    eixos.addEventListener('change', () => { this.constructor.eixos = eixos.checked; this.limparPrevia(); });
    g.append(el('label', { texto: 'Diâmetro (mm)' }), inD,
             el('label', { texto: 'Usuais' }), selD,
             el('label', { texto: 'Eixos e furos' }), el('span', {}, eixos, ' mostrar e prender'));
    raiz.append(g);
    const usados = this._usadosNoModelo();
    if (usados.length) {
      const box = el('div', { class: 'acoes' });
      for (const u of usados) {
        box.append(el('button', { type: 'button', texto: `Ø${num(u.d)} (${u.n})`, title: `${u.origem}: usar este diâmetro`,
          onclick: () => { this._definir(u.d); this.editor._agendarPaineis('props'); } }));
      }
      raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Já usados no modelo' }), box));
    }
    raiz.append(el('p', { class: 'nota', texto: 'O furo é aberto na própria malha da peça (na chapa desenhada no editor, entra na chapa). Perto de um furo da peça de baixo, o novo prende no mesmo alinhamento.' }));
  }

  /** Espessura da parede furada: a camada de vértices da peça logo atrás da face. */
  _profundidade(ent, ponto, n) {
    if (!ent) return 10;
    if (ent.tipo === 'chapa') return ent.espessura || 10;
    const pts = C.pontosDaEntidade(ent);
    let melhor = null;
    for (const q of pts) {
      const t = C.dot(C.sub(ponto, q), n);
      if (t > 0.5 && (melhor === null || t < melhor)) melhor = t;
    }
    return melhor ? Math.min(melhor, 60) : 10;
  }

  /** Cilindro do marcador: entra pela face em `ponto` (normal `n`) e atravessa a parede. */
  geometria(ponto, n, prof = 10) {
    const u = C.normalizar(n);
    return prisma(C.add(ponto, C.mul(u, 0.3)), C.mul(u, -1), this.diametro / 2, LADOS, prof + 0.6);
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
    for (const m of this.documento.entidades.values()) if (m.atributos && m.atributos.furo && m.atributos.furo.peca) marcadores.push(m);
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
        if (dd <= tol && (!preso || dd < preso.dd)) preso = { q, dd, f, e };
        else extra.push(this._circulo(C.add(q, C.mul(n, 0.5)), n, Math.max(f.d, 6) / 2, '#8a94a6'));
      }
    }
    if (preso) {
      ponto = preso.q;
      extra.push(this._circulo(C.add(ponto, C.mul(n, 0.5)), n, Math.max(preso.f.d, 6) / 2 + 2, '#0a8f3c'));
      const nomeB = (preso.e.atributos && preso.e.atributos.marcas && (preso.e.atributos.marcas.nome || preso.e.atributos.marcas.posicao)) || preso.e.nome || 'peça de baixo';
      extra.push(C.gRotulo(`no furo Ø${mm(preso.f.d)} de ${nomeB}`, C.add(ponto, C.mul(n, 90)), '#0a8f3c'));
    }
    return { ponto, extra };
  }

  /**
   * Abre o furo na malha: o laço costurado na face clicada e na face de trás da parede,
   * e o cilindro entre elas. Devolve {vertices, faces, profundidade} ou null (a face de
   * trás não foi reconhecida, ou o furo não cabe na face).
   */
  _furarMalha(ent, iFace, ponto, n, d) {
    if (!ent || ent.tipo !== 'solido' || !(iFace >= 0) || !ent.faces[iFace]) return null;
    const nf = C.normalizar(C.normalDaFace(ent, iFace));
    if (C.dot(nf, n) < 0.7) return null;
    const r = d / 2;
    const e1 = C.normalizar(C.perpendicular(nf)), e2 = C.normalizar(C.cross(nf, e1));
    const em2d = (q) => [C.dot(C.sub(q, ponto), e1), C.dot(C.sub(q, ponto), e2)];
    const poli = (f) => f.map(i => em2d(ent.vertices[i]));
    const frente = ent.faces[iFace];
    const p2 = poli(frente);
    if (!dentroDoPoligono([0, 0], p2)) return null;
    for (let i = 0; i < p2.length; i++) if (distPontoSegmento2d([0, 0], p2[i], p2[(i + 1) % p2.length]) < r + 0.5) return null;
    // a face de trás: paralela, olhando para o outro lado, logo atrás, com o centro dentro dela
    let iTras = -1, prof = null;
    for (let k = 0; k < ent.faces.length; k++) {
      if (k === iFace || ent.faces[k].length < 3) continue;
      const nk = C.normalizar(C.normalDaFace(ent, k));
      if (C.dot(nk, nf) > -0.9) continue;
      const t = -C.dot(C.sub(ent.vertices[ent.faces[k][0]], ponto), nf);      // profundidade da face k
      if (!(t > 0.5) || t > 80) continue;
      if (!dentroDoPoligono([0, 0], poli(ent.faces[k]))) continue;
      if (prof === null || t < prof) { prof = t; iTras = k; }
    }
    if (iTras < 0) return null;
    const vertices = ent.vertices.map(v => v.slice());
    const faces = ent.faces.map(f => f.slice());
    const H = [], B = [];
    for (let i = 0; i < LADOS; i++) {
      const t = (2 * Math.PI * i) / LADOS;
      const h = C.add(ponto, C.add(C.mul(e1, r * Math.cos(t)), C.mul(e2, r * Math.sin(t))));
      H.push(vertices.length); vertices.push(h);
      B.push(vertices.length); vertices.push(C.add(h, C.mul(nf, -prof)));
    }
    const costurar = (f, laco) => {
      // o laço gira ao contrário do contorno; a ponte sai do vértice do contorno mais perto
      const pts = poli(f);
      const horario = areaAssinada(pts) > 0;                        // contorno anti-horário → furo horário
      const ordem = horario ? laco.slice().reverse() : laco.slice();
      let k = 0, dm = Infinity;
      for (let i = 0; i < f.length; i++) { const dd = Math.hypot(pts[i][0], pts[i][1]); if (dd < dm) { dm = dd; k = i; } }
      const pk = vertices[f[k]];
      let j = 0; dm = Infinity;
      for (let i = 0; i < ordem.length; i++) { const dd = C.dist(vertices[ordem[i]], pk); if (dd < dm) { dm = dd; j = i; } }
      const giro = ordem.slice(j).concat(ordem.slice(0, j));
      return f.slice(0, k + 1).concat(giro, [giro[0], f[k]], f.slice(k + 1));
    };
    faces[iFace] = costurar(frente, H);
    faces[iTras] = costurar(ent.faces[iTras], B);
    const eixo = C.add(ponto, C.mul(nf, -prof / 2));
    for (let i = 0; i < LADOS; i++) {
      const j = (i + 1) % LADOS;
      let q = [H[i], H[j], B[j], B[i]];
      const nq = C.normalDoContorno(q.map(k => vertices[k]));
      const cq = [0, 1, 2].map(a => q.reduce((s, k) => s + vertices[k][a], 0) / 4);
      if (C.dot(nq, C.sub(eixo, cq)) < 0) q = [H[i], B[i], B[j], H[j]];   // a normal olha para o vazio do furo
      faces.push(q);
    }
    return { vertices, faces, profundidade: prof };
  }

  onMover(p) {
    this.limparPrevia();
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const { ponto, extra } = this.ajustar(p, n);
    const alvo = this.documento.get(p.entidade);
    const g = this.geometria(ponto, n, this._profundidade(alvo, ponto, n));
    this.previa(C.grupo(C.gMalha(g.vertices, g.faces, '#1f2430', 0.85),
                        C.gRotulo(this.rotuloAtual, C.add(ponto, C.mul(n, 30))), ...extra));
  }

  onPonto(p) {
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const { ponto } = this.ajustar(p, n);
    const d = this.diametro;
    const alvo = this.documento.get(p.entidade);
    if (alvo && alvo.tipo === 'chapa') {
      // chapa paramétrica: o furo entra na própria chapa (é o que o IFC e a lista leem)
      const rel = C.sub(ponto, alvo.origem);
      const furos = (alvo.furos || []).map(f => ({ ...f }));
      furos.push({ x: C.dot(rel, alvo.eixo_x), y: C.dot(rel, alvo.eixo_y), diametro: d });
      this.executar(C.cmdAlterar(alvo.id, { furos }, 'Furar chapa'));
      this.dica(`Furo ${this.rotuloAtual} na chapa · clique no próximo (Esc sai)`);
      return;
    }
    const malha = alvo ? this._furarMalha(alvo, p.face, ponto, n, d) : null;
    if (malha) {
      const registro = { d, ponto: C.copiar(ponto), eixo: C.mul(C.normalizar(n), -1), profundidade: malha.profundidade };
      const atributos = { ...(alvo.atributos || {}), furos_editor: [...((alvo.atributos && alvo.atributos.furos_editor) || []), registro] };
      this.executar(C.cmdAlterar(alvo.id, { vertices: malha.vertices, faces: malha.faces, atributos }, 'Furo'));
      this.dica(`Furo ${this.rotuloAtual} aberto na peça (parede de ${mm(malha.profundidade)} mm) · clique no próximo, ou troque o diâmetro no painel (Esc sai)`);
      return;
    }
    // sem a face de trás (parede não reconhecida, barra paramétrica): o marcador
    const prof = this._profundidade(alvo, ponto, n);
    const g = this.geometria(ponto, n, prof);
    const ent = {
      tipo: 'solido', id: C.novoId('furo'), nome: this.nomeAtual, camada: 'Furos', material: 'Cor #1f2430',
      visivel: true, bloqueada: false, grupo: '',
      vertices: g.vertices, faces: g.faces, arestas_vivas: [],
      atributos: {
        tipo_ifc: 'IfcOpeningElement', exportar: false, criado_no_editor: true,
        furo: { d, ponto: C.copiar(ponto), eixo: C.mul(C.normalizar(n), -1), profundidade: prof, peca: alvo ? alvo.id : null },
      },
    };
    this.executar(C.cmdAdicionar(ent, 'Furo'));
    this.dica(`Furo ${this.rotuloAtual} marcado (a parede de trás não foi reconhecida: fica o marcador, que o detalhamento lê como furo) · clique no próximo (Esc sai)`);
  }
}

export default FerramentaFuro;
