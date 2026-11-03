/* Pré-moldado no editor 3D (em desenvolvimento, só no modo dev): num projeto da área do pré-moldado, as
 * ferramentas de estrutura do aço (Barra, Chapa, Parafuso, Furo) dão lugar às peças de concreto — pilar (com
 * o cálice), viga (retangular, T, I, U), consolo e sapata. Cada uma com um painel de medidas que começa com o
 * que o galpão dimensionou; as peças entram com desfazer, nas camadas do galpão (premoldado/modelo3d.py) e
 * com os atributos de peça pré-moldada. O editor não muda: este módulo usa a API das ferramentas
 * (ferramentas/base.js e _comum.js) e troca o registro depois que o editor carregou. */
import { Ferramenta, paraMilimetros, formatar } from '/editor3d/ferramentas/base.js';
import * as C from '/editor3d/ferramentas/_comum.js';

const CAM = { pilar: 'Pilares pré-moldados', calice: 'Cálices', viga: 'Vigas pré-moldadas', consolo: 'Consolos', fundacao: 'Fundações' };
const CHAVE = 'premoldado.editor.medidas';

// as medidas (mm) — o padrão, o que o galpão dimensionou e o que o usuário mudou por último
const M = {
  b: 450, h: 500, H: 9000, Lemb: 1100, calice: true, parede: 200, folga: 50, fundo: 200, girar: false,
  viga_tipo: 'retangular', vb: 200, vh: 500, vbf: 400, vhf: 120, vbw: 150, vB: 500, vt: 80, vtf: 80,
  cons_c: 300, cons_h: 400, cons_b: 450,
  sap_a: 2000, sap_b: 2000, sap_h: 500,
};
try { Object.assign(M, JSON.parse(localStorage.getItem(CHAVE) || '{}')); } catch (e) { /* sem armazenamento */ }
const guardar = () => { try { localStorage.setItem(CHAVE, JSON.stringify(M)); } catch (e) { /* */ } };

// ------------------------------------------------------------------ o painel de medidas

let painel = null;
function mostrarPainel(titulo, campos, aoMudar) {
  if (!painel) {
    painel = document.createElement('div');
    painel.style.cssText = 'position:fixed;left:58px;top:86px;z-index:50;background:var(--painel,#1b2433);color:var(--texto,#e6edf7);' +
      'border:1px solid var(--borda,#334155);border-radius:8px;padding:8px 10px;font:12px system-ui;box-shadow:0 6px 18px rgba(0,0,0,.35);min-width:210px';
    document.body.append(painel);
  }
  painel.replaceChildren();
  const h = document.createElement('div');
  h.textContent = titulo;
  h.style.cssText = 'font-weight:600;margin-bottom:6px;color:var(--azul,#7fb0ff)';
  painel.append(h);
  for (const [k, rot, tipo, ops] of campos) {
    const lin = document.createElement('label');
    lin.style.cssText = 'display:flex;justify-content:space-between;gap:8px;align-items:center;margin:3px 0';
    lin.append(document.createTextNode(rot));
    let inp;
    if (tipo === 'bool') {
      inp = document.createElement('input'); inp.type = 'checkbox'; inp.checked = !!M[k];
      inp.onchange = () => { M[k] = inp.checked; guardar(); aoMudar && aoMudar(); };
    } else if (tipo === 'sel') {
      inp = document.createElement('select');
      for (const o of ops) { const op = document.createElement('option'); op.value = o; op.textContent = o; op.selected = M[k] === o; inp.append(op); }
      inp.onchange = () => { M[k] = inp.value; guardar(); aoMudar && aoMudar(true); };
    } else {
      inp = document.createElement('input'); inp.value = String(M[k] / 10).replace('.', ','); inp.style.width = '70px';
      inp.title = 'cm';
      inp.onchange = () => { const v = paraMilimetros(inp.value + 'cm'); if (v > 0) { M[k] = v; guardar(); aoMudar && aoMudar(); } };
      inp.onkeydown = ev => ev.stopPropagation();
    }
    lin.append(inp);
    painel.append(lin);
  }
  const n = document.createElement('div');
  n.textContent = 'medidas em cm';
  n.style.cssText = 'opacity:.6;margin-top:4px';
  painel.append(n);
  painel.hidden = false;
}
const esconderPainel = () => { if (painel) painel.hidden = true; };

// ------------------------------------------------------------------ geometria

function caixa(x0, x1, y0, y1, z0, z1) {
  return C.extrudarContorno([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], [0, 0, 1], z1 - z0);
}

function solido(geo, camada, nome, atributos) {
  return { tipo: 'solido', id: C.novoId('s'), nome, camada, material: 'Concreto', visivel: true, bloqueada: false, grupo: '',
           vertices: geo.vertices, faces: geo.faces, arestas_vivas: [], atributos: { pre_moldado: true, ...atributos } };
}

/** o pilar e o cálice no ponto p (a boca do cálice no z do clique) */
function pecasDoPilar(p) {
  const [bx, hy] = M.girar ? [M.h, M.b] : [M.b, M.h];
  const [x, y, z] = p;
  const out = [solido(caixa(x - bx / 2, x + bx / 2, y - hy / 2, y + hy / 2, z - M.Lemb, z + M.H), CAM.pilar,
                      `Pilar ${M.b / 10} × ${M.h / 10}`, { peca: 'P', tipo_ifc: 'IfcColumn', b_cm: M.b / 10, h_cm: M.h / 10 })];
  if (M.calice) {
    const ib = bx / 2 + M.folga, ih = hy / 2 + M.folga, eb = ib + M.parede, eh = ih + M.parede;
    const zb = z - M.Lemb;
    const paredes = [caixa(x - eb, x - ib, y - eh, y + eh, zb, z), caixa(x + ib, x + eb, y - eh, y + eh, zb, z),
                     caixa(x - ib, x + ib, y - eh, y - ih, zb, z), caixa(x - ib, x + ib, y + ih, y + eh, zb, z),
                     caixa(x - eb, x + eb, y - eh, y + eh, zb - M.fundo, zb)];
    paredes.forEach((g, i) => out.push(solido(g, CAM.calice, i < 4 ? 'Cálice — parede' : 'Cálice — fundo', { peca: 'CL', tipo_ifc: 'IfcFooting' })));
  }
  return out;
}

/** o contorno da seção da viga (u horizontal centrado, v da face de baixo) */
function contornoViga() {
  const t = M.viga_tipo;
  if (t === 'T') {
    const bf = M.vbf, hf = M.vhf, bw = M.vbw, h = M.vh;
    return [[-bw / 2, 0], [bw / 2, 0], [bw / 2, h - hf], [bf / 2, h - hf], [bf / 2, h], [-bf / 2, h], [-bf / 2, h - hf], [-bw / 2, h - hf]];
  }
  if (t === 'I') {
    const bf = M.vbf, hf = M.vhf, bw = M.vbw, h = M.vh;
    return [[-bf / 2, 0], [bf / 2, 0], [bf / 2, hf], [bw / 2, hf], [bw / 2, h - hf], [bf / 2, h - hf], [bf / 2, h], [-bf / 2, h],
            [-bf / 2, h - hf], [-bw / 2, h - hf], [-bw / 2, hf], [-bf / 2, hf]];
  }
  if (t === 'U') {
    const B = M.vB, h = M.vh, tp = M.vt, tf = M.vtf;
    return [[-B / 2, 0], [B / 2, 0], [B / 2, h], [B / 2 - tp, h], [B / 2 - tp, tf], [-B / 2 + tp, tf], [-B / 2 + tp, h], [-B / 2, h]];
  }
  return [[-M.vb / 2, 0], [M.vb / 2, 0], [M.vb / 2, M.vh], [-M.vb / 2, M.vh]];
}

function alturaViga() { return M.viga_tipo === 'U' || M.viga_tipo === 'retangular' ? M.vh : M.vh; }

/** a viga de a a b com a face de cima na reta a–b */
function geoViga(a, b) {
  const d = C.normalizar(C.sub(b, a));
  let e = C.cross([0, 0, 1], d);
  if (C.comp(e) < 1e-6) e = [1, 0, 0];
  e = C.normalizar(e);
  const w = C.normalizar(C.cross(d, e));
  const h = alturaViga();
  const pts = contornoViga().map(([u, v]) => C.add(C.add(a, C.mul(e, u)), C.mul(w, v - h)));
  return C.extrudarContorno(pts, d, C.dist(a, b));
}

/** o consolo na face de normal n, com o topo no ponto p */
function geoConsolo(p, n) {
  let nh = [n[0], n[1], 0];
  if (C.comp(nh) < 1e-6) nh = [1, 0, 0];
  nh = C.normalizar(nh);
  const t = C.normalizar(C.cross([0, 0, 1], nh));
  const b2 = M.cons_b / 2;
  const topo = p[2], base = p[2] - M.cons_h;
  const pts = [C.add([p[0], p[1], base], C.mul(t, -b2)), C.add([p[0], p[1], base], C.mul(t, b2)),
               C.add([p[0], p[1], topo], C.mul(t, b2)), C.add([p[0], p[1], topo], C.mul(t, -b2))];
  return C.extrudarContorno(pts, nh, M.cons_c);
}

function geoSapata(p) {
  const [x, y, z] = p;
  return caixa(x - M.sap_b / 2, x + M.sap_b / 2, y - M.sap_a / 2, y + M.sap_a / 2, z - M.sap_h, z);
}

// ------------------------------------------------------------------ as ferramentas

const ICONE = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;

class FerramentaPilarPM extends Ferramenta {
  static id = 'pm_pilar';
  static nome = 'Pilar pré-moldado';
  static atalho = 'P';
  static grupo = 'estrutura';
  static dica = 'Clique no ponto do pilar (a boca do cálice); R gira 90°';
  static icone = ICONE('<rect x="9" y="3" width="6" height="15"/><path d="M5 21h14M6 18h12v3H6z"/>');

  ativar() {
    mostrarPainel('Pilar pré-moldado', [['b', 'b (em X)'], ['h', 'h (em Y)'], ['H', 'altura acima do cálice'], ['Lemb', 'embutimento'],
      ['calice', 'com o cálice', 'bool'], ['parede', 'parede do cálice'], ['folga', 'folga do cálice'], ['fundo', 'fundo do cálice'],
      ['girar', 'girado 90° (R)', 'bool']], () => this.desenhar());
    this.dica(FerramentaPilarPM.dica);
  }
  desativar() { esconderPainel(); this.limparPrevia(); }
  onMover(p) { if (p) { this.atual = C.copiar(p.ponto); this.desenhar(); } }
  desenhar() {
    this.limparPrevia();
    if (!this.atual) return;
    const g = C.grupo();
    for (const s of pecasDoPilar(this.atual)) g.add(C.gMalha(s.vertices, s.faces));
    g.add(C.gRotulo(`${M.b / 10} × ${M.h / 10} · ${formatar(M.H)} + ${formatar(M.Lemb)}`, this.atual));
    this.previa(g);
  }
  onPonto(p) {
    this.executar(C.cmdAdicionar(pecasDoPilar(C.copiar(p.ponto)), 'Pilar pré-moldado'));
    this.medida(`pilar ${M.b / 10} × ${M.h / 10}`);
  }
  onTecla(ev) {
    if (ev.key === 'r' || ev.key === 'R') { M.girar = !M.girar; guardar(); this.ativar(); this.desenhar(); return true; }
    return false;
  }
  cancelar() { C.voltarParaSelecao(this.editor); }
}

class FerramentaVigaPM extends Ferramenta {
  static id = 'pm_viga';
  static nome = 'Viga pré-moldada';
  static atalho = 'V';
  static grupo = 'estrutura';
  static dica = 'Clique no início e no fim da viga (a face de cima passa pelos pontos)';
  static icone = ICONE('<path d="M3 9h18v5H3z"/><path d="M5 14v5M19 14v5"/>');

  ativar() { this.inicio = null; this.atual = null; this.painel(); this.dica(FerramentaVigaPM.dica); }
  painel() {
    const t = M.viga_tipo;
    const campos = [['viga_tipo', 'seção', 'sel', ['retangular', 'T', 'I', 'U']], ['vh', 'altura h']];
    if (t === 'retangular') campos.push(['vb', 'largura b']);
    if (t === 'T' || t === 'I') campos.push(['vbf', 'mesa b'], ['vhf', 'mesa h'], ['vbw', 'alma']);
    if (t === 'U') campos.push(['vB', 'largura externa'], ['vt', 'parede'], ['vtf', 'fundo']);
    mostrarPainel('Viga pré-moldada', campos, (troca) => { if (troca) this.painel(); this.desenhar(); });
  }
  desativar() { esconderPainel(); this.limparPrevia(); }
  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    this.atual = this.inicio && this.eixo ? C.projetarNoEixo(this.inicio, p.ponto, this.eixo) : C.copiar(p.ponto);
    this.desenhar();
  }
  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.atual) g.add(C.gPonto(this.atual));
    if (this.inicio && this.atual && C.dist(this.inicio, this.atual) > 1) {
      const geo = geoViga(this.inicio, this.atual);
      g.add(C.gMalha(geo.vertices, geo.faces));
      g.add(C.gRotulo(formatar(C.dist(this.inicio, this.atual)), C.meio(this.inicio, this.atual)));
      this.medida(formatar(C.dist(this.inicio, this.atual)));
    }
    this.previa(g);
  }
  onPonto(p) {
    const q = this.inicio && this.eixo ? C.projetarNoEixo(this.inicio, p.ponto, this.eixo) : C.copiar(p.ponto);
    if (!this.inicio) { this.inicio = q; C.ancorar(this.editor, q); this.dica('Clique no fim da viga'); return; }
    if (C.dist(this.inicio, q) < 10) return;
    const geo = geoViga(this.inicio, q);
    const nome = `Viga ${M.viga_tipo} h ${M.vh / 10}`;
    this.executar(C.cmdAdicionar(solido(geo, CAM.viga, nome, { peca: 'V', tipo_ifc: 'IfcBeam', secao: M.viga_tipo, comprimento_mm: Math.round(C.dist(this.inicio, q)) }),
                                 'Viga pré-moldada'));
    this.inicio = null;
    C.desancorar(this.editor);
    this.limparPrevia();
    this.dica(FerramentaVigaPM.dica);
  }
  onValor(texto) {
    const L = paraMilimetros(texto);
    if (!this.inicio || !this.atual || !(L > 0)) return false;
    const d = C.normalizar(C.sub(this.atual, this.inicio));
    this.onPonto({ ponto: C.add(this.inicio, C.mul(d, L)) });
    return true;
  }
  onTecla(ev) {
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight' || ev.key === 'ArrowUp') { C.teclaDeEixo(this, ev); this.desenhar(); return true; }
    return false;
  }
  cancelar() {
    if (this.inicio) { this.inicio = null; C.desancorar(this.editor); this.limparPrevia(); this.dica(FerramentaVigaPM.dica); return; }
    C.voltarParaSelecao(this.editor);
  }
}

class FerramentaConsoloPM extends Ferramenta {
  static id = 'pm_consolo';
  static nome = 'Consolo';
  static atalho = 'K';
  static grupo = 'estrutura';
  static dica = 'Clique na face do pilar, na altura do topo do consolo';
  static icone = ICONE('<path d="M8 3v18"/><path d="M8 9h8v4l-3 3H8"/>');

  ativar() {
    mostrarPainel('Consolo', [['cons_c', 'comprimento'], ['cons_h', 'altura'], ['cons_b', 'largura']], () => this.desenhar());
    this.dica(FerramentaConsoloPM.dica);
  }
  desativar() { esconderPainel(); this.limparPrevia(); }
  onMover(p) { if (p) { this.atual = p; this.desenhar(); } }
  desenhar() {
    this.limparPrevia();
    if (!this.atual) return;
    const geo = geoConsolo(this.atual.ponto, this.atual.normal || [1, 0, 0]);
    const g = C.grupo();
    g.add(C.gMalha(geo.vertices, geo.faces));
    this.previa(g);
  }
  onPonto(p) {
    const geo = geoConsolo(p.ponto, p.normal || [1, 0, 0]);
    this.executar(C.cmdAdicionar(solido(geo, CAM.consolo, 'Consolo', { peca: 'CS', tipo_ifc: 'IfcMember' }), 'Consolo'));
  }
  cancelar() { C.voltarParaSelecao(this.editor); }
}

class FerramentaSapataPM extends Ferramenta {
  static id = 'pm_sapata';
  static nome = 'Sapata';
  static atalho = 'F';
  static grupo = 'estrutura';
  static dica = 'Clique no ponto da sapata (o topo dela no z do clique)';
  static icone = ICONE('<path d="M4 15h16v4H4z"/><path d="M9 15V9h6v6"/>');

  ativar() {
    mostrarPainel('Sapata', [['sap_a', 'lado em Y'], ['sap_b', 'lado em X'], ['sap_h', 'altura']], () => this.desenhar());
    this.dica(FerramentaSapataPM.dica);
  }
  desativar() { esconderPainel(); this.limparPrevia(); }
  onMover(p) { if (p) { this.atual = C.copiar(p.ponto); this.desenhar(); } }
  desenhar() {
    this.limparPrevia();
    if (!this.atual) return;
    const geo = geoSapata(this.atual);
    const g = C.grupo();
    g.add(C.gMalha(geo.vertices, geo.faces));
    this.previa(g);
  }
  onPonto(p) {
    this.executar(C.cmdAdicionar(solido(geoSapata(C.copiar(p.ponto)), CAM.fundacao, 'Sapata', { peca: 'SP', tipo_ifc: 'IfcFooting', moldado_no_local: true }), 'Sapata'));
  }
  cancelar() { C.voltarParaSelecao(this.editor); }
}

const FERRAMENTAS = [FerramentaPilarPM, FerramentaVigaPM, FerramentaConsoloPM, FerramentaSapataPM];
const DO_ACO = ['barra', 'chapa', 'parafuso', 'furo'];

// ------------------------------------------------------------------ a troca, só nos projetos do pré-moldado

const esperar = ms => new Promise(r => setTimeout(r, ms));

async function medidasDoGalpao(slug) {
  try {
    const r = await fetch('/api/premoldado/dimensionar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projeto: slug }) });
    const j = await r.json();
    const pil = (j.pilares || []).find(q => q.tipo === 'intermediário') || (j.pilares || [])[0];
    if (pil) Object.assign(M, { b: pil.b * 10, h: pil.h * 10, cons_b: pil.b * 10 });
    if (j.dados) M.H = j.dados.altura_pilar * 1000;
    const cal = (j.calices || []).find(c => c.dados_calice && c.dados_calice.direcao === 'x');
    if (cal) Object.assign(M, { Lemb: cal.dados_calice.Lemb_adotado * 10, fundo: cal.dados_calice.fundo * 10 });
    guardar();
  } catch (e) { /* fica o padrão */ }
}

// ------------------------------------------------------------------ Ver → Armaduras (pedido do usuário, 30/09)

/** liga/desliga a camada das armaduras dos pilares (premoldado/modelo3d.py) e deixa o concreto translúcido para vê-las */
async function alternarArmaduras() {
  const ed = window.editor;
  const doc = ed && ed.documento;
  if (!doc) return;
  const cam = doc.camadas.get('Armaduras');
  const arm = [...doc.entidades.values()].filter(e => e.camada === 'Armaduras');
  const temPecas = arm.length > 0;
  // gerado antes das armaduras dos cálices e das fundações (30/09): só a dos pilares
  const temCalices = [...doc.entidades.values()].some(e => e.camada === 'Cálices');
  const soPilares = temPecas && temCalices && !arm.some(e => /^(CL|SP|BL)-/.test(String((e.atributos || {}).peca || '')));
  if (!cam || !temPecas || soPilares) {
    // o 3D foi gerado antes das armaduras (ou não veio do galpão): oferece gerar de novo pelo galpão calculado
    const slug = new URLSearchParams(location.search).get('projeto');
    const corpo = document.createElement('div');
    corpo.className = 'explica';
    corpo.textContent = (soPilares ? 'Este modelo 3D tem só as armaduras dos pilares. Gerar o 3D do galpão de novo, com as dos cálices e das fundações também? '
      : 'Este modelo 3D foi gerado sem as armaduras. Gerar o 3D do galpão de novo, com as barras dos pilares, dos cálices e das fundações? ') +
      'O modelo atual vai para o histórico (Arquivo → Restaurar modelo anterior…); o que foi mexido à mão neste 3D não vem junto.';
    if (!slug || await ed.dialogo({ titulo: 'Armaduras dos pilares', corpo, ok: 'Gerar com as armaduras' }) !== 'ok') return;
    ed.dica('Calculando o galpão e gerando o 3D com as armaduras…');
    try {
      const r = await fetch('/api/premoldado/modelo', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ projeto: slug }) });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    } catch (e) { ed.aviso(`Não foi possível gerar o 3D: ${e.message}`, 'erro', 0); return; }
    try { sessionStorage.setItem('premoldado.ligarArmaduras', slug); } catch (e) { /* */ }
    location.reload();
    return;
  }
  const ligar = cam.visivel === false;
  const { ComandoAparencia } = await import('/editor3d/editor.js');
  ed.executar(new ComandoAparencia('camadas', 'Armaduras', { visivel: ligar }, ligar ? 'Mostrar as armaduras' : 'Ocultar as armaduras'));
  // o modelo grande abre no modo leve (as peças juntas em lotes, só com a cor): lá não há concreto translúcido, então
  // o concreto dos pilares sai de cena enquanto as armaduras aparecem; no modelo pequeno, o concreto fica translúcido
  const leve = !!(ed.cena && ed.cena.emLote);
  if (leve || !ligar) {
    for (const nome of ['Pilares pré-moldados', 'Cálices', 'Fundações']) {
      if (doc.camadas.get(nome)) ed.executar(new ComandoAparencia('camadas', nome, { visivel: !ligar }, `${ligar ? 'Ocultar' : 'Mostrar'} o concreto: ${nome}`));
    }
  }
  if (!leve || !ligar) {
    const conc = doc.materiais.get('Concreto');
    const base = conc ? {} : { cor: '#b7b0a4', metalico: 0, rugosidade: 0.9 };
    ed.executar(new ComandoAparencia('materiais', 'Concreto', { ...base, opacidade: ligar ? 0.22 : 1 }, ligar ? 'Concreto translúcido' : 'Concreto opaco'));
  }
  marcarArmaduras();
  ed.dica(!ligar ? 'Armaduras ocultas.' : leve
    ? 'Armaduras à mostra (pilares, cálices e fundações); no modo leve o concreto sai de cena enquanto elas aparecem.'
    : 'Armaduras à mostra (pilares, cálices e fundações); o concreto ficou translúcido.');
}

function marcarArmaduras() {
  const b = document.querySelector('[data-acao="pm-armaduras"]');
  const cam = window.editor && window.editor.documento && window.editor.documento.camadas.get('Armaduras');
  if (b) b.textContent = `${cam && cam.visivel !== false ? '✓ ' : ''}Armaduras (pré-moldado)`;
}

function menuArmaduras() {
  const ref = document.querySelector('[data-menu="ver"] [data-acao="referencia"]');
  if (!ref || document.querySelector('[data-acao="pm-armaduras"]')) return;
  const b = document.createElement('button');
  b.type = 'button';
  b.dataset.acao = 'pm-armaduras';
  b.title = 'As armaduras calculadas: pilares (barras e estribos), cálices (laços e verticais) e fundações (malha da sapata, tirantes do bloco)';
  b.addEventListener('click', () => { alternarArmaduras(); });
  ref.after(b);
  marcarArmaduras();
  // os níveis do projeto, editáveis no 3D (o duplo clique na cabeça de um nível abre o mesmo diálogo)
  const n = document.createElement('button');
  n.type = 'button';
  n.dataset.acao = 'pm-niveis';
  n.textContent = 'Níveis do projeto…';
  n.title = 'Nome e cota de cada nível; mudar a cota refaz o 3D (duplo clique na cabeça do nível abre o mesmo)';
  n.addEventListener('click', () => { if (window.editor && window.editor.dialogoNiveis) window.editor.dialogoNiveis(); });
  b.after(n);
}

// ------------------------------------------------------------------ Raio-X com as armaduras (pedido do usuário, 30/09)

/**
 * No Raio-X o concreto fica translúcido e as armaduras aparecem cheias: (1) elas não entram nos lotes do modo leve
 * (o lote é translúcido inteiro no Raio-X) — cada barra vira um objeto da cena; (2) o material delas no Raio-X é o
 * do sombreado (opaco); (3) entrar no Raio-X liga a camada Armaduras, e sair desliga se foi o Raio-X que ligou.
 * Tudo por fora da cena (web/editor3d/nucleo), sem mudar o editor da Metálica.
 */
async function raioXComArmaduras(ed) {
  const cena = ed.cena;
  if (!cena || cena._pmRaioX) return;
  cena._pmRaioX = true;
  const ehArmadura = (ent) => !!ent && ent.material === 'Armadura';
  try {
    const { Lote } = await import('/editor3d/nucleo/lote.js');
    const aceita = Lote.aceita;
    Lote.aceita = (ent) => !ehArmadura(ent) && aceita.call(Lote, ent);
  } catch (e) { /* sem o módulo do lote: tudo em objetos, segue */ }
  const matOrig = cena._materialDe.bind(cena);
  cena._materialDe = (ent) => {
    if (ehArmadura(ent) && cena.modo === 'raiox') {
      const m = cena.modo;
      cena.modo = 'sombreado';
      try { return matOrig(ent); } finally { cena.modo = m; }
    }
    return matOrig(ent);
  };
  // armaduras já à mostra ao abrir (entraram no lote antes do ajuste): refeitas como objetos
  const doc = ed.documento;
  const ids = [...doc.entidades.values()].filter(ehArmadura).map(e => e.id);
  if (ids.length && cena.lote && doc.camadas.get('Armaduras') && doc.camadas.get('Armaduras').visivel !== false) cena.atualizar(ids);
  const definir = ed.definirModo.bind(ed);
  let ligouNoRaioX = false;
  ed.definirModo = (modo) => {
    const cam = doc.camadas.get('Armaduras');
    const tem = cam && [...doc.entidades.values()].some(ehArmadura);
    if (modo === 'raiox' && tem && cam.visivel === false) {
      cam.visivel = true; ligouNoRaioX = true; doc.notificarAparencia();
      ed.dica('Raio-X: as armaduras aparecem por dentro do concreto (Ver → Armaduras liga e desliga).');
    } else if (modo !== 'raiox' && ligouNoRaioX && cam) {
      cam.visivel = false; ligouNoRaioX = false; doc.notificarAparencia();
    }
    definir(modo);
    marcarArmaduras();
  };
}

async function instalar() {
  const slug = new URLSearchParams(location.search).get('projeto');
  if (!slug) return;
  let pj = null;
  try { const r = await (await fetch('/api/projetos/' + encodeURIComponent(slug), { cache: 'no-store' })).json(); pj = r.projeto || r; } catch (e) { return; }
  if (!pj || !(pj.tipo === 'premoldado' || pj.area === 'premoldado')) return;
  for (let i = 0; i < 300; i++) {
    const e = window.editor;
    if (e && e.ferramentas && e.ferramentas.size && e.el && e.el.barra && e.el.barra.children.length) break;
    await esperar(100);
  }
  const ed = window.editor;
  if (!ed || !ed.ferramentas) return;
  for (const id of DO_ACO) ed.ferramentas.delete(id);
  for (const [tecla, id] of [...ed.atalhos.entries()]) if (DO_ACO.includes(id)) ed.atalhos.delete(tecla);
  for (const F of FERRAMENTAS) {
    ed.ferramentas.set(F.id, F);
    const t = F.atalho.toLowerCase();
    if (!ed.atalhos.has(t)) ed.atalhos.set(t, F.id);
  }
  ed._montarBarra();
  menuArmaduras();
  raioXComArmaduras(ed);
  let pedido = null;
  try { pedido = sessionStorage.getItem('premoldado.ligarArmaduras'); sessionStorage.removeItem('premoldado.ligarArmaduras'); } catch (e) { pedido = null; }
  if (pedido === slug) {
    for (let i = 0; i < 300 && !(ed.documento && ed.documento.camadas.get('Armaduras') && ed.documento.entidades.size); i++) await esperar(100);
    await esperar(800);
    alternarArmaduras();
  }
  window.premoldadoEditor = { medidas: M, ferramentas: FERRAMENTAS.map(F => F.id), alternarArmaduras };
  medidasDoGalpao(slug);
}

instalar();
