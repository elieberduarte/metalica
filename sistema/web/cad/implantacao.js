// A nova dinâmica da Montagem (11/10/2026, pedido do usuário com os prints do CD Bom Dia): o projeto recebido montado
// por EIXOS e NÍVEIS, como nos programas de BIM, para um ser humano operar sem o Claude.
//
// 1. Implantação — o primeiro quadro da folha: o operador dá os eixos da obra (os vãos, ou lidos do DXF do cliente) e
//    eles se desenham com as bolinhas e as cotas; ao lado, a caixa dos níveis do projeto (−1,00 · 0,00 · +5,00…).
// 2. Elevação — duplo clique num eixo da implantação abre a elevação dele: um quadro com os eixos que o cruzam (em ordem
//    crescente da esquerda para a direita — a, b, c… / 1, 2, 3…, decisão do usuário; inversível nos Eixos…) e as linhas
//    dos níveis. É ali que a tesoura do desenho do cliente vai ser posta.
// 3. Sombra — a elevação mostra, apagada, a do eixo de trás ou da frente (liga e desliga no título), para comparar os
//    níveis e desenhar por cima.
//
// Tudo na folha da Montagem (mm de papel, escala 1): cada quadro tem a sua escala e o seu MAPA, a volta do papel ao
// real — na implantação, (g, p) no sistema dos eixos (g ao longo dos numerados, p ao longo dos com letra); na elevação,
// (u, z): u ao longo do eixo a partir do primeiro que cruza, z a cota. O que o programa desenha nos quadros (os eixos, as
// cotas, os níveis) leva `atributos.gerado` e é refeito quando os eixos, os níveis ou a escala mudam; o que o operador
// pôs dentro (o desenho colado, os elementos) é levado pelo mapa para continuar no mesmo lugar real. O 3D lê os
// elementos da implantação pela medida real (nucleo3d/de_planta_estrutura.planta_real).
//
// Os métodos entram na classe Montagem (montagem.js), como os de estrutura.js entram no CAD.

import { criar, transformar, pontosDe, pontosArco, caixaDe, valorCota, novoId as novoIdEntidade } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoAlterar, ComandoComposto, ComandoRemover } from './nucleo/comandos.js';
import { Ferramenta } from './ferramentas.js';
import { desenhoDaTesoura, rotuloPerfil } from './estrutura.js';

export const CAMADA_EIXOS = 'IMPL EIXOS';
export const CAMADA_NIVEIS = 'IMPL NIVEIS';
export const CAMADA_COTAS = 'IMPL COTAS';
export const CAMADA_ELEMENTOS = 'IMPL ELEMENTOS';
const CAMADAS = {
  [CAMADA_EIXOS]: { cor: '#dc2626', tipo_linha: 'CENTER', espessura: 0.18 },
  [CAMADA_NIVEIS]: { cor: '#dc2626', tipo_linha: 'DASHED', espessura: 0.18 },
  [CAMADA_COTAS]: { cor: '#94a3b8', tipo_linha: 'CONTINUOUS', espessura: 0.13 },
  // as tesouras lançadas, redesenhadas nas elevações dos eixos delas
  [CAMADA_ELEMENTOS]: { cor: '#f59e0b', tipo_linha: 'CONTINUOUS', espessura: 0.35 },
};
/** mm de papel: o raio da bolinha do eixo, a altura dos nomes e quanto o eixo passa do último que ele cruza */
const BOLA = 5, TXT = 4.2, PASSA = 8, TXT_COTA = 3, TXT_NIVEL = 3.2;
const MARGEM = { lado: 8, topo: 20, baixo: 10 };
/** as escalas que a implantação e a elevação escolhem sozinhas (até o operador escolher outra no título) */
const ESCALAS_AUTO = [20, 25, 50, 75, 100, 125, 200, 250, 500, 1000];
/** a largura (mm de papel) da faixa à direita da implantação onde fica a caixa dos níveis */
const FAIXA_NIVEIS = 62;

const natural = (a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true, sensitivity: 'base' });
const numero = (v, casas = 2) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const cota = (z) => (z > 0 ? '+' : z < 0 ? '−' : '') + numero(Math.abs(z) / 1000);

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}
async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  const t = await r.text();
  let d = null; try { d = JSON.parse(t); } catch { /* texto */ }
  if (!r.ok || (d && d.erro)) throw new Error((d && (d.erro || d.mensagem)) || t || r.statusText);
  return d;
}

/** "16x6250", "6000 6000 7500", "3x23,33m" → [mm…]; null se não entendeu */
export function lerVaos(texto) {
  const out = [];
  for (const parte of String(texto || '').trim().split(/[\s;]+/).filter(Boolean)) {
    const m = /^(?:(\d+)\s*[x×*]\s*)?([\d.,]+)\s*(mm|cm|m)?$/i.exec(parte);
    if (!m) return null;
    let v = parseFloat(m[2].replace(/\.(?=\d{3}\b)/g, '').replace(',', '.'));
    const un = (m[3] || '').toLowerCase();
    if (un === 'm') v *= 1000; else if (un === 'cm') v *= 10;
    if (!(v > 0)) return null;
    for (let i = 0; i < (m[1] ? parseInt(m[1], 10) : 1); i++) out.push(v);
  }
  return out.length ? out : null;
}
/** os vãos de volta em texto curto ("16x6250 7500") */
function vaosEmTexto(vaos) {
  const out = [];
  for (let i = 0; i < vaos.length;) {
    let j = i; while (j + 1 < vaos.length && Math.abs(vaos[j + 1] - vaos[i]) < 0.5) j++;
    const v = String(Math.round(vaos[i] * 10) / 10).replace('.', ',');
    out.push(j > i ? `${j - i + 1}x${v}` : v);
    i = j + 1;
  }
  return out.join(' ');
}
/** os nomes a partir do primeiro: 1, 2, 3… ou A, B, C… (depois do Z, AA, AB…) */
function nomesAPartir(primeiro, n) {
  const p = String(primeiro || '1').trim();
  if (/^\d+$/.test(p)) return Array.from({ length: n }, (_, i) => String(parseInt(p, 10) + i));
  const letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', min = p === p.toLowerCase();
  let k = Math.max(0, letras.indexOf(p.toUpperCase()));
  return Array.from({ length: n }, () => {
    let s = '', x = k++;
    do { s = letras[x % 26] + s; x = Math.floor(x / 26) - 1; } while (x >= 0);
    return min ? s.toLowerCase() : s;
  });
}

/** a menor escala da lista em que `largura` × `altura` (mm reais) cabem em `maxL` × `maxA` mm de papel */
function escalaQueCabe(largura, altura, maxL, maxA) {
  return ESCALAS_AUTO.find(s => largura / s <= maxL && altura / s <= maxA) || ESCALAS_AUTO[ESCALAS_AUTO.length - 1];
}

// ------------------------------------------------------------------ copiar e colar por pontos de referência (etapa 2)

/** Marcar uma área no desenho aberto (dois cantos, ou arrastando): para ler os eixos de uma parte do desenho do cliente. */
class MarcarArea extends Ferramenta {
  static id = 'marcar-area'; static nome = 'Marcar área'; static grupo = 'montagem';
  static dica = 'Marque a área: o 1º canto (ou arraste uma janela) · Esc cancela';
  reiniciar() { super.reiniciar(); this.a = null; this.editor.tela.regiao = null; }
  // saiu da ferramenta sem marcar (Esc, outra ferramenta): quem esperava a área fica sabendo
  desativar() { super.desativar(); this.editor.tela.regiao = null; this.editor.tela.pedirQuadro(); const f = window.montagem._areaMarcada; if (f) f(null); }
  onPonto(p) { if (!this.a) { this.a = p; this.dica('Agora o canto oposto · Esc cancela'); return; } this._fim(p); }
  onMover(p) { if (this.a) { this.editor.tela.regiao = [this.a, p]; this.editor.tela.pedirQuadro(); } }
  onSoltar(p, ev) { const de = ev && ev.arrasto ? this.editor.tela.paraMundo(ev.arrasto.de) : null; if (de) { this.a = de; this._fim(p); } }
  _fim(p) {
    const a = this.a;
    this.a = null;
    const caixa = [[Math.min(a[0], p[0]), Math.min(a[1], p[1])], [Math.max(a[0], p[0]), Math.max(a[1], p[1])]];
    const f = window.montagem._areaMarcada;
    if (f) f(caixa);
    this.editor.ativarFerramenta('selecionar');
  }
}

/** Ctrl+C no desenho do cliente: os dois pontos de referência (os apoios da tesoura nos eixos), opcionais. */
class CopiarComBase extends Ferramenta {
  static id = 'copiar-base'; static nome = 'Copiar com pontos de referência'; static grupo = 'montagem';
  static dica = 'Copiar: clique o 1º ponto de referência (o apoio de um lado da tesoura, no eixo) · Enter copia sem pontos · Esc cancela';
  // sem nada selecionado (as camadas do cliente vêm travadas e não se selecionam), primeiro a área: dois cantos ou arrastando
  reiniciar() {
    super.reiniciar(); this.r1 = null; this.c1 = null;
    this.modoArea = !window.montagem._copiaPendente;
    if (this.modoArea) this.dica('Copiar: marque a área do desenho a copiar — o 1º canto (ou arraste uma janela) · Esc cancela');
  }
  desativar() { super.desativar(); this.editor.tela.regiao = null; this.editor.tela.pedirQuadro(); }
  onMover(p) { if (this.modoArea && this.c1) { this.editor.tela.regiao = [this.c1, p]; this.editor.tela.pedirQuadro(); } }
  onSoltar(p, ev) {
    const de = this.modoArea && ev && ev.arrasto ? this.editor.tela.paraMundo(ev.arrasto.de) : null;
    if (de) { this.c1 = de; this._area(p); }
  }
  _area(p) {
    const a = this.c1;
    this.c1 = null;
    this.editor.tela.regiao = null; this.editor.tela.pedirQuadro();
    const caixa = [[Math.min(a[0], p[0]), Math.min(a[1], p[1])], [Math.max(a[0], p[0]), Math.max(a[1], p[1])]];
    if (!window.montagem._prepararCopia(window.montagem._naArea(caixa))) { this.dica('Nada inteiro dentro dessa área: marque de novo, envolvendo o desenho todo · Esc cancela'); return; }
    this.modoArea = false;
    this.dica(CopiarComBase.dica);
  }
  onPonto(p) {
    if (this.modoArea) { if (!this.c1) { this.c1 = p; this.dica('Agora o canto oposto da área · Esc cancela'); return; } this._area(p); return; }
    if (!this.r1) { this.r1 = p; this.dica('Agora o 2º ponto de referência (o apoio do outro lado, no outro eixo) · Enter copia só com o 1º · Esc cancela'); return; }
    window.montagem._guardarCopia([this.r1, p]);
    this.editor.ativarFerramenta('selecionar');
  }
  onTecla(ev) {
    if (ev.key !== 'Enter' || this.modoArea) return false;
    window.montagem._guardarCopia(this.r1 ? [this.r1] : []);
    this.editor.ativarFerramenta('selecionar');
    return true;
  }
}

/** Ctrl+V na Montagem: onde vão os pontos de referência (o snap pega o cruzamento do eixo com o nível). */
class ColarComBase extends Ferramenta {
  static id = 'colar-base'; static nome = 'Colar por pontos de referência'; static grupo = 'montagem';
  static dica = 'Colar: clique onde vai o 1º ponto de referência · M espelha · Esc cancela';
  reiniciar() { super.reiniciar(); this.alvos = []; this.espelho = false; this.ultimo = null; }
  get copia() { return window.montagem._copia; }
  ativar() {
    super.ativar();
    const n = (this.copia.refs || []).length;
    this.dica(n === 2 ? 'Colar: clique onde vai o 1º ponto de referência (o apoio no eixo, na linha do nível) · M espelha · Esc cancela'
      : 'Colar: clique onde vai o ponto de referência (sem ele, o canto de baixo à esquerda do desenho) · M espelha · Esc cancela');
  }
  _previa(p) {
    const t = window.montagem._transformacaoDaColagem(this.copia, p ? [...this.alvos, p] : this.alvos, this.espelho);
    if (!t) return;
    const [[x0, y0], [x1, y1]] = this.copia.caixa;
    const cantos = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(t.f);
    const amostra = this.copia.ents.slice(0, 400).flatMap(e => (e.tipo === 'linha' ? [criar({ tipo: 'linha', camada: 'AUXILIAR', a: t.f(e.a), b: t.f(e.b) })] : []));
    this.editor.previa([criar({ tipo: 'polilinha', camada: 'AUXILIAR', vertices: cantos, fechada: true }), ...amostra]);
    this.editor.medida(`×${(t.k).toFixed(4).replace('.', ',')}${t.espelho ? ' · espelhado' : ''}`);
  }
  onMover(p) { this.ultimo = p; this._previa(p); }
  onPonto(p) {
    this.alvos.push(p);
    const precisa = Math.max(1, Math.min(2, (this.copia.refs || []).length));
    if (this.alvos.length < precisa) { this.dica('Agora onde vai o 2º ponto de referência (o apoio do outro lado) · Enter cola sem ajustar a escala · M espelha · Esc cancela'); return; }
    window.montagem._colar(this.alvos, this.espelho);
    this.editor.ativarFerramenta('selecionar');
  }
  onTecla(ev) {
    if (ev.key === 'm' || ev.key === 'M') { this.espelho = !this.espelho; this._previa(this.ultimo); this.dica(this.espelho ? 'Espelhado (M desfaz)' : 'Sem espelhar (M espelha)'); return true; }
    if (ev.key === 'Enter' && this.alvos.length === 1) { window.montagem._colar(this.alvos, this.espelho); this.editor.ativarFerramenta('selecionar'); return true; }
    return false;
  }
}

export class MetodosImplantacao {
  // ------------------------------------------------------------------ o mapa papel ↔ real
  /** o real (no sistema do quadro) do ponto `p` do papel; `ref` = {x, y, escala, mapa} (o quadro como estava) */
  _paraReal(ref, p) {
    const mp = ref.mapa, s = ref.escala;
    return [mp.X0 + (p[0] - ref.x - mp.ox) * s, mp.Y0 + (p[1] - ref.y - mp.oy) * s];
  }
  _paraPapel(ref, r) {
    const mp = ref.mapa, s = ref.escala;
    return [ref.x + mp.ox + (r[0] - mp.X0) / s, ref.y + mp.oy + (r[1] - mp.Y0) / s];
  }

  // ------------------------------------------------------------------ os dados
  _quadroImplantacao() { return this.m && this.m.quadros.find(q => q.tipo === 'implantacao'); }
  _elevacoes() { return this.m ? this.m.quadros.filter(q => q.tipo === 'elevacao') : []; }
  /** os eixos da implantação: {eixo_g, numeros: [{nome, pos}], letras: [...]} (o formato de nucleo3d/eixos.py) */
  _eixosDaObra() { return (this.m && this.m.eixos) || null; }

  /** os eixos de uma família em ordem de nome (a, b, c… / 1, 2, 3…) */
  _familia(fam) {
    const ex = this._eixosDaObra();
    return ex ? [...(fam === 'numero' ? ex.numeros : ex.letras) || []].sort((a, b) => natural(a.nome, b.nome)) : [];
  }

  async _niveis() {
    try { this.cad._niveisProjeto = null; return [...(await this.cad.niveisDoProjeto())].sort((a, b) => a.z - b.z); } catch { return []; }
  }

  // ------------------------------------------------------------------ refazer o que o programa desenha
  _camadasDaImplantacao() {
    const doc = this.cad.doc;
    let mudou = false;
    for (const [nome, c] of Object.entries(CAMADAS)) {
      if (!doc.camadas.has(nome)) { doc.camadas.set(nome, { nome, ...c, visivel: true, bloqueada: true }); mudou = true; }
    }
    if (mudou) doc.notificar([], 'aparencia');
  }

  /**
   * Refaz a implantação e as elevações (`so`: só estes quadros): o tamanho e o mapa de cada um, os eixos, as cotas e
   * os níveis desenhados; os quadros se acomodam (arrumar) e o que está dentro de cada um vai junto — o que o operador
   * pôs nos refeitos fica no mesmo lugar real.
   */
  async refazerQuadrosDaObra(so = null) {
    const m = this.m;
    if (!m) return;
    const niveis = await this._niveis();
    const alvos = m.quadros.filter(q => (q.tipo === 'implantacao' || q.tipo === 'elevacao') && (!so || so.includes(q)));
    if (!alvos.length) return;
    // o corte do 3D nas elevações (corte_eixos.js): o modelo do projeto antes de desenhar
    if (alvos.some(q => q.tipo === 'elevacao' && q.do3d)) await this._carregarModelo3d();
    const antes = new Map(m.quadros.map(q => [q.id, { x: q.x, y: q.y, escala: q.escala, mapa: q.mapa ? { ...q.mapa } : null }]));
    const desenhos = new Map();
    for (const q of alvos) desenhos.set(q.id, q.tipo === 'implantacao' ? this._planejarImplantacao(q, niveis) : this._planejarElevacao(q, niveis));
    // os quadros se acomodam com os tamanhos novos
    const { arrumar } = await import('./montagem.js');
    arrumar(m);
    const doc = this.cad.doc;
    this._camadasDaImplantacao();
    this._refazendo = true;
    try { doc.lote(() => {
      for (const e of [...doc.entidades.values()]) {
        const a = e.atributos || {};
        if (!a.quadro) continue;
        const q = m.quadros.find(x => x.id === a.quadro), ant = antes.get(a.quadro);
        if (!q || !ant) continue;
        if (desenhos.has(q.id) && a.gerado) { doc.remover(e.id); continue; }
        let f = null;
        if (desenhos.has(q.id) && ant.mapa && q.mapa) f = (p) => this._paraPapel(q, this._paraReal(ant, p));
        else if (q.x !== ant.x || q.y !== ant.y) f = (p) => [p[0] + q.x - ant.x, p[1] + q.y - ant.y];
        if (!f) continue;
        const n = transformar(e, f, (v) => v, ant.escala && q.escala && desenhos.has(q.id) ? ant.escala / q.escala : 1);
        const { id, ...campos } = n;
        doc.alterar(id, campos);
      }
      for (const [, ents] of desenhos) for (const reg of ents()) doc.add(reg);
    }); } finally { this._refazendo = false; }
    this._gravar();
    this.cad.tela.pedirQuadro();
  }

  /** O tamanho e o mapa da implantação pelos eixos; devolve a função que cria o desenho dela (depois do arrumar). */
  _planejarImplantacao(q, niveis) {
    const ex = this._eixosDaObra();
    const nums = this._familia('numero'), lets = this._familia('letra');
    const gs = nums.map(e => e.pos), ps = lets.map(e => e.pos);
    const g0 = gs.length ? Math.min(...gs) : 0, g1 = gs.length ? Math.max(...gs) : 10000;
    const p0 = ps.length ? Math.min(...ps) : 0, p1 = ps.length ? Math.max(...ps) : 10000;
    const L = Math.max(g1 - g0, 1000), H = Math.max(p1 - p0, 1000);
    if (q.escala_auto !== false) q.escala = escalaQueCabe(L, H, 560, 380);
    const s = q.escala;
    const lad = BOLA * 2 + PASSA + 6;                      // a faixa das bolinhas (à esquerda e em cima)
    q.mapa = { X0: g0, Y0: p1, ox: MARGEM.lado + lad, oy: -(MARGEM.topo + lad), giro: ex ? Math.atan2(ex.eixo_g[1], ex.eixo_g[0]) * 180 / Math.PI : 0 };
    q.w = Math.max(140, q.ajuste_w || 0, Math.ceil(q.mapa.ox + L / s + PASSA + 30 + FAIXA_NIVEIS));
    q.h = Math.max(100, q.ajuste_h || 0, Math.ceil(-q.mapa.oy + H / s + PASSA + 30 + MARGEM.baixo));
    return () => {
      const out = [];
      if (!ex) {
        // a implantação nova, sem eixos: o convite
        out.push(criar({ tipo: 'texto', camada: CAMADA_COTAS, posicao: [q.x + MARGEM.lado + 6, q.y - MARGEM.topo - 14], texto: 'Comece pelos eixos da obra: botão "Eixos…" no título.',
          altura: 3.5, atributos: { quadro: q.id, gerado: 'implantacao' } }));
        return out;
      }
      const P = (g, p) => this._paraPapel(q, [g, p]);
      const at = (fam, nome) => ({ quadro: q.id, gerado: 'implantacao', eixo: nome, familia: fam });
      const ext = PASSA * s;
      // os numerados correm ao longo do p (de cima a baixo); a bolinha em cima
      for (const e of nums) {
        const a = P(e.pos, p1 + ext), b = P(e.pos, p0 - ext);
        out.push(criar({ tipo: 'linha', camada: CAMADA_EIXOS, a, b, atributos: at('numero', e.nome) }));
        const c = [a[0], a[1] + BOLA];
        out.push(criar({ tipo: 'circulo', camada: CAMADA_EIXOS, centro: c, raio: BOLA, atributos: at('numero', e.nome) }));
        out.push(criar({ tipo: 'texto', camada: CAMADA_EIXOS, posicao: c, texto: e.nome, altura: TXT, alinhamento: 'centro', vertical: 'meio', atributos: at('numero', e.nome) }));
      }
      // os com letra correm ao longo do g; a bolinha à esquerda
      for (const e of lets) {
        const a = P(g0 - ext, e.pos), b = P(g1 + ext, e.pos);
        out.push(criar({ tipo: 'linha', camada: CAMADA_EIXOS, a, b, atributos: at('letra', e.nome) }));
        const c = [a[0] - BOLA, a[1]];
        out.push(criar({ tipo: 'circulo', camada: CAMADA_EIXOS, centro: c, raio: BOLA, atributos: at('letra', e.nome) }));
        out.push(criar({ tipo: 'texto', camada: CAMADA_EIXOS, posicao: c, texto: e.nome, altura: TXT, alinhamento: 'centro', vertical: 'meio', atributos: at('letra', e.nome) }));
      }
      // as cotas: entre os numerados embaixo, entre os com letra à direita (a medida real: a cota × a escala)
      const cotas = (pts, desl) => {
        for (let i = 0; i + 1 < pts.length; i++) out.push(criar({ tipo: 'cota', camada: CAMADA_COTAS, p1: pts[i], p2: pts[i + 1], deslocamento: desl, escala: s, altura: TXT_COTA, atributos: { quadro: q.id, gerado: 'implantacao' } }));
        if (pts.length > 2) out.push(criar({ tipo: 'cota', camada: CAMADA_COTAS, p1: pts[0], p2: pts[pts.length - 1], deslocamento: desl * 2.4, escala: s, altura: TXT_COTA, atributos: { quadro: q.id, gerado: 'implantacao' } }));
      };
      const gOrd = [...new Set(gs)].sort((a, b) => a - b), pOrd = [...new Set(ps)].sort((a, b) => a - b);
      if (gOrd.length > 1) cotas(gOrd.map(g => P(g, p0 - ext)), -6);
      if (pOrd.length > 1) cotas(pOrd.map(p => P(g1 + ext, p)), -6);
      // as linhas das peças fora dos eixos (corte_eixos.js), tracejadas
      out.push(...this._linhasNaImplantacao(q, P, { g0, g1, p0, p1, ext }));
      return out;
    };
  }

  /** Os eixos que cruzam a elevação `q`, em ordem (a da vista), com u (mm, a partir do primeiro). */
  _cruzamDaElevacao(q) {
    const outra = q.familia === 'letra' ? 'numero' : 'letra';
    const lista = this._familia(outra);
    if (((this.m || {}).eixos || {}).vista_invertida) lista.reverse();
    if (!lista.length) return [];
    const p0 = lista[0].pos, sent = lista.length > 1 && lista[lista.length - 1].pos < p0 ? -1 : 1;
    return lista.map(e => ({ nome: e.nome, u: (e.pos - p0) * sent, pos: e.pos }));
  }

  /** O tamanho e o mapa da elevação pelos eixos que cruzam e pelos níveis; devolve a função do desenho dela. */
  _planejarElevacao(q, niveis) {
    const cruz = this._cruzamDaElevacao(q);
    const us = cruz.map(c => c.u);
    const U = Math.max(us.length ? Math.max(...us) : 0, 3000);
    const zs = [0, ...niveis.map(n => n.z)];
    let z0 = Math.min(...zs), z1 = Math.max(...zs);
    if (z1 - z0 < 3000) z1 = z0 + 3000;
    if (q.escala_auto !== false) q.escala = escalaQueCabe(U, z1 - z0, 560, 300);
    const s = q.escala;
    const topo = BOLA * 2 + PASSA + 4;
    q.mapa = { X0: 0, Y0: z1, ox: MARGEM.lado + PASSA + 6, oy: -(MARGEM.topo + topo) };
    q.cruzam = cruz.map(c => ({ nome: c.nome, u: c.u }));
    q.w = Math.max(160, q.ajuste_w || 0, Math.ceil(q.mapa.ox + U / s + PASSA + 58));
    q.h = Math.max(100, q.ajuste_h || 0, Math.ceil(-q.mapa.oy + (z1 - z0) / s + PASSA + 20 + MARGEM.baixo));
    return () => {
      const out = [];
      const P = (u, z) => this._paraPapel(q, [u, z]);
      const ext = PASSA * s;
      const outra = q.familia === 'letra' ? 'numero' : 'letra';
      for (const c of cruz) {
        const a = P(c.u, z1 + ext), b = P(c.u, z0 - ext);
        const at = { quadro: q.id, gerado: 'elevacao', eixo: c.nome, familia: outra };
        out.push(criar({ tipo: 'linha', camada: CAMADA_EIXOS, a, b, atributos: at }));
        const cc = [a[0], a[1] + BOLA];
        out.push(criar({ tipo: 'circulo', camada: CAMADA_EIXOS, centro: cc, raio: BOLA, atributos: at }));
        out.push(criar({ tipo: 'texto', camada: CAMADA_EIXOS, posicao: cc, texto: c.nome, altura: TXT, alinhamento: 'centro', vertical: 'meio', atributos: at }));
      }
      for (const n of [{ nome: '±0,00', z: 0, zero: true }, ...niveis.filter(n => Math.abs(n.z) > 0.5)]) {
        const a = P(-ext, n.z), b = P(U + ext, n.z);
        const at = { quadro: q.id, gerado: 'elevacao', nivel: n.nome };
        out.push(criar({ tipo: 'linha', camada: n.zero ? CAMADA_EIXOS : CAMADA_NIVEIS, a, b, atributos: at }));
        const rot = n.zero ? (niveis.find(x => Math.abs(x.z) <= 0.5) || {}).nome || '±0,00' : n.nome;
        out.push(criar({ tipo: 'texto', camada: CAMADA_NIVEIS, posicao: [b[0] + 1.5, b[1] + 0.8], texto: rot === cota(n.z) || rot === '±0,00' ? (n.z ? cota(n.z) : '±0,00') : `${rot} (${n.z ? cota(n.z) : '±0,00'})`,
          altura: TXT_NIVEL, alinhamento: 'esquerda', vertical: 'base', atributos: at }));
      }
      const us2 = [...new Set(us)].sort((a, b) => a - b);
      for (let i = 0; i + 1 < us2.length; i++) {
        out.push(criar({ tipo: 'cota', camada: CAMADA_COTAS, p1: P(us2[i], z0 - ext), p2: P(us2[i + 1], z0 - ext), deslocamento: -6, escala: s, altura: TXT_COTA, atributos: { quadro: q.id, gerado: 'elevacao' } }));
      }
      out.push(...this._elementosNaElevacao(q, niveis, P));
      if (q.do3d) out.push(...this._corteDo3D(q, P));
      return out;
    };
  }

  // ------------------------------------------------------------------ a implantação
  /** A implantação na folha (a primeira vez: o quadro entra no topo, os outros descem levando o que têm dentro). */
  async garantirImplantacao() {
    if (!this.m) return null;
    let q = this._quadroImplantacao();
    if (q) return q;
    const { TIPOS } = await import('./montagem.js');
    const t = TIPOS.implantacao;
    q = { id: 'q' + Date.now().toString(36) + 'i', tipo: 'implantacao', nome: t.rotulo, escala: t.escala, w: t.w, h: t.h, x: 0, y: 0 };
    this.m.quadros.unshift(q);
    await this.refazerQuadrosDaObra([q]);
    return q;
  }

  /** Os eixos da obra: os vãos (ou lidos do desenho do cliente), os nomes do primeiro e o lado da vista das elevações. */
  async dialogoEixos(lidos = null) {
    const ex = this._eixosDaObra();
    // os eixos de partida: os lidos de uma área do desenho do cliente (a volta do "Ler de uma área…") ou os gravados
    const ordena = (l) => [...(l || [])].sort((a, b) => natural(a.nome, b.nome));
    const nums = lidos ? ordena(lidos.numeros) : this._familia('numero'), lets = lidos ? ordena(lidos.letras) : this._familia('letra');
    const vaos = (lista) => { const ps = lista.map(e => e.pos).sort((a, b) => a - b); return vaosEmTexto(ps.slice(1).map((p, i) => p - ps[i])); };
    const desce = lets.length > 1 ? lets[lets.length - 1].pos < lets[0].pos : true;     // A em cima, como no desenho
    // a posição do primeiro eixo fica: os eixos lidos do cliente continuam no lugar deles (o 3D casa com o desenho dele)
    const origemN = nums.length ? nums[0].pos : 0, origemL = lets.length ? lets[0].pos : 0;
    const campo = (rot, valor, dica, attrs = {}) => { const i = el('input', { type: 'text', value: valor, title: dica, spellcheck: 'false', ...attrs }); i.addEventListener('keydown', ev => ev.stopPropagation()); return [el('label', { title: dica }, rot, i), i]; };
    const [lNum, iNum] = campo('Vãos entre os eixos numerados', nums.length > 1 ? vaos(nums) : '5x6000', 'Da esquerda para a direita: 16x6250, ou 6000 6000 7500, ou 6,25m');
    const [lP1, iP1] = campo('Primeiro número', nums.length ? nums[0].nome : '1', 'O nome do primeiro eixo numerado', { size: 4 });
    const [lLet, iLet] = campo('Vãos entre os eixos com letra', lets.length > 1 ? vaos(lets) : '15000', 'De cima para baixo (ou de baixo para cima, abaixo): 3x23333, ou 20000 25000');
    const [lL1, iL1] = campo('Primeira letra', lets.length ? lets[0].nome : 'A', 'A, a, ou outra letra para começar', { size: 4 });
    const sDesce = el('select', {}, el('option', { value: '1', texto: 'de cima para baixo (A em cima)' }), el('option', { value: '0', texto: 'de baixo para cima (A embaixo)' }));
    sDesce.value = desce ? '1' : '0';
    const inv = el('input', { type: 'checkbox' }); inv.checked = !!(ex && ex.vista_invertida);
    let marcar = false;
    const lerBtn = el('button', { type: 'button', texto: 'Ler de uma área do desenho do cliente…',
      title: 'Vai para o desenho do cliente: marque a planta com os eixos (a locação) e eles são lidos — as linhas compridas com o nome na ponta, em qualquer camada',
      onclick: () => { marcar = true; const c = document.getElementById('dialogo-cancelar'); if (c) c.click(); } });
    const info = el('div', { class: 'explica', texto: lidos
      ? `Lidos do desenho do cliente: ${nums.length} numerado(s) (${nums.map(x => x.nome).join(', ')}) e ${lets.length} com letra (${lets.map(x => x.nome).join(', ')}). Confira os vãos e grave.` + ((lidos.avisos || []).length ? ' ' + lidos.avisos.join(' ') : '')
      : 'Os numerados são as linhas das tesouras (1, 2, 3… ao longo do galpão); os com letra, as filas de pilares (A, B, C… atravessadas). Ao gravar, os eixos se desenham na Implantação e as elevações abertas se refazem.' });
    const corpo = el('div', { class: 'enviar-quadro-dialogo grade-malha' }, info, lNum, lP1, lLet, lL1,
      el('label', {}, 'Letras ', sDesce),
      el('label', { class: 'linha', title: 'As elevações mostram os eixos em ordem crescente da esquerda para a direita (a, b, c… / 1, 2, 3…). Marque para ver do outro lado.' }, inv, ' elevações vistas do outro lado (ordem decrescente)'),
      this.cad.projeto ? lerBtn : null);
    const r = await this.cad.dialogo({ titulo: 'Eixos da obra', corpo, ok: 'Gravar' });
    if (marcar) {
      const novos = await this._lerEixosDeArea();
      return this.dialogoEixos(novos || lidos);
    }
    if (r !== 'ok') return;
    const vn = lerVaos(iNum.value), vl = lerVaos(iLet.value);
    if (!vn && !vl) { this.cad.aviso('Os vãos não foram entendidos: use 16x6250, ou 6000 6000 7500, ou 6,25m.', 'atencao', 9000); return; }
    const acum = (v) => { const out = [0]; for (const x of v || []) out.push(out[out.length - 1] + x); return out; };
    const pn = acum(vn), pl = acum(vl), sinal = sDesce.value === '1' ? -1 : 1;
    const nomesN = nomesAPartir(iP1.value, pn.length), nomesL = nomesAPartir(iL1.value, pl.length);
    const r1 = (v) => Math.round(v * 10) / 10;
    const eixos = { eixo_g: [1, 0], numeros: vn ? pn.map((p, i) => ({ nome: nomesN[i], pos: r1(origemN + p) })) : [],
      letras: vl ? pl.map((p, i) => ({ nome: nomesL[i], pos: r1(origemL + sinal * p) })) : [], vista_invertida: inv.checked };
    await this.gravarEixos(eixos);
  }

  /** "Ler de uma área do desenho do cliente…": na Original, o operador marca a planta dos eixos (a locação); o servidor lê
   *  as linhas compridas com o nome na ponta, em qualquer camada, sem gravar. Volta à Montagem com {numeros, letras}. */
  async _lerEixosDeArea() {
    await this._gravarJa();
    await this.ir('original');
    if (this.cad.nomeDesenho === 'montagem') return null;            // o projeto sem a planta do cliente
    const caixa = await this._marcarArea('Eixos: marque a planta com os eixos (a locação) — dois cantos ou uma janela em volta dela · Esc cancela');
    let lidos = null;
    if (caixa) {
      const tipos = new Set(['linha', 'polilinha', 'texto', 'circulo']);
      const ents = this._naArea(caixa).filter(e => tipos.has(e.tipo));
      const camadas = {};
      for (const e of ents) if (!camadas[e.camada]) camadas[e.camada] = { ...(this.cad.doc.camadas.get(e.camada) || { nome: e.camada }) };
      this.cad.aviso(`Lendo os eixos em ${ents.length.toLocaleString('pt-BR')} objetos…`, 'info', 4000);
      try {
        const r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/lancamento/eixos`, {
          desenho: { nome: 'area', unidade: 'mm', escala: this.cad.doc.escala || 100, camadas, entidades: ents, vistas: [], metadados: {} },
          qualquer_camada: true, so_ler: true });
        lidos = { numeros: (r.eixos || {}).numeros || [], letras: (r.eixos || {}).letras || [], avisos: r.avisos || [] };
      } catch (e) { this.cad.aviso('Não consegui ler os eixos dessa área: ' + e.message, 'atencao', 12000); }
    }
    await this.ir('montagem');
    return lidos;
  }

  /** Espera o operador marcar uma área (dois cantos ou arrastando) no desenho aberto; null com Esc. */
  _marcarArea(dica) {
    return new Promise((resolver) => {
      this._areaMarcada = (caixa) => { this._areaMarcada = null; resolver(caixa); };
      this.cad.ativarFerramenta('marcar-area');
      this.cad.dica(dica);
      this.cad.aviso(dica, 'info', 10000);
    });
  }

  /** Grava os eixos na folha e no projeto (o 3D os desenha) e refaz a implantação e as elevações. */
  async gravarEixos(eixos) {
    this.m.eixos = eixos;
    await this.garantirImplantacao();
    await this.refazerQuadrosDaObra();
    try {
      const { vista_invertida, ...doProjeto } = eixos;
      await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/eixos`, { eixos: doProjeto });
    } catch (e) { this.cad.aviso('Os eixos ficaram na Implantação, mas não foram gravados no projeto: ' + e.message, 'atencao', 9000); }
    const q = this._quadroImplantacao();
    if (q) this.cad.tela.enquadrar([[q.x, q.y - q.h], [q.x + q.w, q.y]]);
    this.cad.aviso(`Eixos gravados: ${eixos.numeros.map(e => e.nome).join(', ') || '—'} e ${eixos.letras.map(e => e.nome).join(', ') || '—'}. Duplo clique num eixo abre a elevação dele.`, 'info', 9000);
  }

  /** Os níveis do projeto (o diálogo do CAD); depois as elevações se refazem com as linhas novas. */
  async editarNiveis() {
    await this.cad.dialogoNiveis();
    this.cad._niveisProjeto = null;
    this._niveisCache = await this._niveis();
    await this.refazerQuadrosDaObra();
  }

  // ------------------------------------------------------------------ as elevações
  /** Abre a elevação do eixo `nome` (família 'numero' ou 'letra'): a que já existe, ou uma nova logo depois das outras. */
  async abrirElevacao(nome, familia) {
    let q = this._elevacoes().find(x => x.eixo === nome && x.familia === familia);
    if (!q) {
      const { TIPOS } = await import('./montagem.js');
      const t = TIPOS.elevacao;
      q = { id: 'q' + Date.now().toString(36) + 'e', tipo: 'elevacao', nome: `Elevação ${nome}`, eixo: nome, familia, escala: t.escala, w: t.w, h: t.h, x: 0, y: 0, sombra: null };
      const ult = [...this.m.quadros].reverse().find(x => x.tipo === 'elevacao') || this._quadroImplantacao();
      this.m.quadros.splice(ult ? this.m.quadros.indexOf(ult) + 1 : 0, 0, q);
      // em ordem de eixo: as elevações dos numerados e depois as das letras, cada uma em ordem de nome
      const elevs = this._elevacoes().sort((a, b) => (a.familia === b.familia ? natural(a.eixo, b.eixo) : a.familia === 'numero' ? -1 : 1));
      const resto = this.m.quadros.filter(x => x.tipo !== 'elevacao');
      const i = resto.findIndex(x => x.tipo === 'implantacao');
      this.m.quadros = [...resto.slice(0, i + 1), ...elevs, ...resto.slice(i + 1)];
      await this.refazerQuadrosDaObra([q]);
      // os outros quadros andaram com o quadro novo: o que está neles foi junto (refazer leva o de todos)
    }
    this.cad.tela.enquadrar([[q.x, q.y - q.h], [q.x + q.w, q.y]], 0.1);
    this.cad.dica(`Elevação do eixo ${nome}: os eixos que cruzam e os níveis. A sombra (no título) mostra a do eixo de trás ou da frente.`);
    return q;
  }

  async tirarElevacao(q) {
    const dentro = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).quadro === q.id && !(e.atributos || {}).gerado);
    if (dentro.length) {
      const corpo = el('div', { class: 'explica', texto: `Tirar a elevação do eixo ${q.eixo} e os ${dentro.length} objetos postos nela?` });
      if (await this.cad.dialogo({ titulo: 'Tirar a elevação', corpo, ok: 'Tirar' }) !== 'ok') return;
    }
    const doc = this.cad.doc;
    doc.lote(() => { for (const e of [...doc.entidades.values()]) if ((e.atributos || {}).quadro === q.id) doc.remover(e.id); });
    this.m.quadros = this.m.quadros.filter(x => x.id !== q.id);
    this._reacomodar();
  }

  /** O eixo vizinho (de trás ou da frente) da mesma família: 'anterior' ou 'proximo' na ordem dos nomes. */
  _vizinho(q, lado) {
    const lista = this._familia(q.familia), i = lista.findIndex(e => e.nome === q.eixo);
    if (i < 0) return null;
    return lista[lado === 'anterior' ? i - 1 : i + 1] || null;
  }

  // ------------------------------------------------------------------ o duplo clique no eixo
  /** O eixo (gerado) sob o ponto da tela: {nome, familia}, ou null */
  _eixoSob(px) {
    const tela = this.cad.tela, p = tela.paraMundo(px), tol = 6 * tela.mmPorPixel;
    let melhor = null, dm = Infinity;
    for (const e of this.cad.doc.naRegiao([[p[0] - tol - BOLA, p[1] - tol - BOLA], [p[0] + tol + BOLA, p[1] + tol + BOLA]])) {
      const a = e.atributos || {};
      // o eixo desenhado (na implantação ou o que cruza a elevação) e a tesoura lançada (a elevação do eixo dela)
      const fam = a.gerado ? a.familia : a.elemento === 'trelica' ? a.familia_eixo : null;
      if (!a.eixo || !fam) continue;
      let d = Infinity;
      if (e.tipo === 'linha') {
        const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], L2 = dx * dx + dy * dy;
        const t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - e.a[0]) * dx + (p[1] - e.a[1]) * dy) / L2)) : 0;
        d = Math.hypot(p[0] - e.a[0] - dx * t, p[1] - e.a[1] - dy * t);
      } else if (e.tipo === 'circulo') d = Math.max(0, Math.hypot(p[0] - e.centro[0], p[1] - e.centro[1]) - e.raio);
      if (d <= tol && d < dm) { dm = d; melhor = { nome: a.eixo, familia: fam }; }
    }
    return melhor;
  }

  _ligarDuploClique() {
    if (this._duploLigado) return;
    this._duploLigado = true;
    const c = this.cad.el.canvas;
    c.addEventListener('dblclick', (ev) => {
      if (!this.ativa || ev.button !== 0) return;
      const r = c.getBoundingClientRect();
      const alvo = this._eixoSob([ev.clientX - r.left, ev.clientY - r.top]);
      if (!alvo) return;
      ev.preventDefault(); ev.stopImmediatePropagation();
      this.abrirElevacao(alvo.nome, alvo.familia);
    }, true);
  }

  // ------------------------------------------------------------------ o título e a caixa dos níveis
  /** Os controles próprios no título da implantação e da elevação (chamado pelo _controles da Montagem). */
  _extrasDoTitulo(q, c) {
    if (q.tipo === 'implantacao') {
      c.append(' ', el('button', { type: 'button', class: 'quadro-botao', title: 'Os eixos da obra: os vãos, os nomes, ou lidos do desenho do cliente', onclick: () => this.dialogoEixos() }, 'Eixos…'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'Abre a elevação de cada eixo (numerados e com letra), com o corte do 3D do projeto e a conferência', onclick: () => this.todasAsElevacoes() }, 'Todas as elevações'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'As linhas do 3D fora dos eixos (tesouras entre eixos, linhas próprias do projeto): uma elevação para cada uma', onclick: () => this.linhasDasPecas() }, 'Linhas das peças'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'O que o corte do 3D achou nos eixos: pilar fora do cruzamento, peça fora da linha do eixo, eixo vazio', onclick: () => this.conferenciaDosEixos() }, 'Conferência'));
    } else if (q.tipo === 'elevacao') {
      const b = c.querySelector('b');
      if (b) b.textContent = q.linha ? `Linha ${q.eixo}` : `Elevação ${q.eixo}`;
      if (q.linha && (q.pecas || []).length) c.title = `Linha de peças fora dos eixos: ${q.pecas.join(', ')}`;
      const ant = this._vizinho(q, 'anterior'), prox = this._vizinho(q, 'proximo');
      const s = el('select', { class: 'quadro-sombra', title: 'A sombra: a elevação do eixo de trás ou da frente, apagada por baixo desta, para comparar os níveis e desenhar por cima' },
        el('option', { value: '', texto: 'sem sombra' }),
        ant ? el('option', { value: 'anterior', texto: `sombra do ${ant.nome}` }) : null,
        prox ? el('option', { value: 'proximo', texto: `sombra do ${prox.nome}` }) : null);
      s.value = q.sombra || '';
      // o corte do 3D do projeto nesta elevação (corte_eixos.js)
      const c3 = el('input', { type: 'checkbox', title: 'Mostra o corte do 3D do projeto no plano deste eixo (as barras no plano e as marcas do que atravessa)' });
      c3.checked = !!q.do3d;
      c3.addEventListener('change', () => { q.do3d = c3.checked; this.refazerQuadrosDaObra([q]); });
      s.addEventListener('change', () => { q.sombra = s.value || null; this._gravar(); this.cad.tela.pedirQuadro(); });
      s.addEventListener('keydown', ev => ev.stopPropagation());
      c.append(' · ', s, ' ', el('label', { class: 'quadro-3d', title: c3.title }, c3, '3D'), ' ',
        el('button', { type: 'button', class: 'quadro-botao', title: 'Cola aqui o que foi copiado do desenho do cliente (Ctrl+V): clique onde vão os pontos de referência', onclick: () => this.colar() }, 'Colar'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'O desenho selecionado nesta elevação vira a tesoura: lançada neste eixo e nos outros que marcar', onclick: () => this.tesouraDaElevacao(q) }, 'Tesoura…'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'Os perfis de cada barra da tesoura deste eixo: perfil, arranjo (simples, composto, caixa), vão e boca', onclick: () => this.abrirPerfis(q) }, 'Perfis…'),
        el('button', { type: 'button', class: 'quadro-tirar', title: 'Tirar esta elevação', onclick: () => this.tirarElevacao(q) }, '×'));
    }
  }

  /** A caixa dos níveis, na faixa à direita da implantação (posicionada a cada quadro). */
  _caixaNiveis(q, x, y, w, h) {
    let c = this.camada.querySelector(`[data-niveis="${q.id}"]`);
    if (!c) {
      c = el('div', { class: 'quadro-niveis', 'data-niveis': q.id });
      this.camada.append(c);
      this._encherNiveis(c);
    }
    const z = this.cad.tela.vp.z || 1;
    const larg = FAIXA_NIVEIS * z;
    c.style.left = (x + w - larg - 6) + 'px'; c.style.top = (y + 34) + 'px';
    c.style.width = Math.max(120, larg - 8) + 'px';
    c.hidden = w < 260 || h < 120;
  }

  async _encherNiveis(c) {
    const niveis = this._niveisCache || (this._niveisCache = await this._niveis());
    c.replaceChildren(
      el('div', { class: 'quadro-niveis-titulo' }, el('b', {}, 'Níveis'),
        el('button', { type: 'button', class: 'quadro-botao', title: 'Acrescentar ou mudar os níveis do projeto (as elevações se refazem)', onclick: () => this.editarNiveis() }, '+')),
      niveis.length
        ? el('ol', {}, [...niveis].reverse().map(n => el('li', { title: 'Clique para mudar os níveis', onclick: () => this.editarNiveis() }, el('span', {}, n.nome), el('span', {}, n.z ? cota(n.z) : '±0,00'))))
        : el('div', { class: 'explica', texto: 'Nenhum nível ainda: + para dar a base, o topo dos pilares, o apoio das tesouras…' }));
  }

  _renovarCaixasNiveis() {
    this._niveisCache = null;
    for (const c of this.camada.querySelectorAll('[data-niveis]')) this._encherNiveis(c);
  }

  // ------------------------------------------------------------------ a sombra
  /** O que foi posto (não gerado) no quadro `id` — guardado até o desenho mudar: a sombra pinta a cada quadro e não
   *  pode varrer o documento inteiro (CD Bom Dia: 5.484 objetos). */
  _desenhadoNoQuadro(id) {
    const doc = this.cad.doc;
    if (this._docSombraOuvido !== doc) { this._docSombraOuvido = doc; this._cacheSombra = new Map(); doc.aoMudar(() => this._cacheSombra.clear()); }
    let l = this._cacheSombra.get(id);
    if (!l) {
      l = [...doc.entidades.values()].filter(e => { const at = e.atributos || {}; return at.quadro === id && !at.gerado; });
      this._cacheSombra.set(id, l);
    }
    return l;
  }

  /** Desenha, apagado, o que foi posto na elevação do eixo vizinho, no lugar real dela dentro desta. */
  _desenharSombras() {
    const tela = this.cad.tela, ctx = tela.ctx;
    for (const q of this._elevacoes()) {
      if (!q.sombra || !q.mapa) continue;
      const viz = this._vizinho(q, q.sombra);
      const nq = viz && this._elevacoes().find(x => x.familia === q.familia && x.eixo === viz.nome);
      if (!nq || !nq.mapa) continue;
      const f = (p) => tela.paraTela(this._paraPapel(q, this._paraReal(nq, p)));
      const a = tela.paraTela([q.x, q.y]), b = tela.paraTela([q.x + q.w, q.y - q.h]);
      ctx.save();
      ctx.beginPath(); ctx.rect(a[0], a[1], b[0] - a[0], b[1] - a[1]); ctx.clip();
      ctx.globalAlpha = 0.35; ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath();
      for (const e of this._desenhadoNoQuadro(nq.id)) {
        let pts = null;
        if (e.tipo === 'linha') pts = [e.a, e.b];
        else if (e.tipo === 'polilinha') pts = e.fechada ? [...e.vertices, e.vertices[0]] : e.vertices;
        else if (e.tipo === 'arco') pts = pontosArco(e);
        else if (e.tipo === 'circulo') pts = Array.from({ length: 25 }, (_, i) => [e.centro[0] + e.raio * Math.cos(i * Math.PI / 12), e.centro[1] + e.raio * Math.sin(i * Math.PI / 12)]);
        if (!pts || pts.length < 2) continue;
        const t0 = f(pts[0]); ctx.moveTo(t0[0], t0[1]);
        for (const p of pts.slice(1)) { const t = f(p); ctx.lineTo(t[0], t[1]); }
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------ copiar e colar por pontos de referência (etapa 2)
  _ligarCopiarColar() {
    if (this._copiarLigado) return;
    this._copiarLigado = true;
    this.cad.ferramentas.set('copiar-base', new CopiarComBase(this.cad));
    this.cad.ferramentas.set('colar-base', new ColarComBase(this.cad));
    this.cad.ferramentas.set('marcar-area', new MarcarArea(this.cad));
    // o botão na barra de baixo, na Original (o Ctrl+C também vale)
    this.botaoCopiar = el('button', { type: 'button', class: 'enviar-quadro', hidden: true, id: 'btn-copiar-tesoura',
      title: 'Copie a tesoura (ou outra peça) do desenho do cliente com dois pontos de referência — os apoios nos eixos — e cole na elevação da Montagem com Ctrl+V',
      onclick: () => { if (!this.copiarSelecao()) this.cad.aviso('Selecione primeiro o desenho da tesoura (uma janela em volta dela) e depois "Copiar" (ou Ctrl+C).', 'atencao', 8000); } }, 'Copiar (Ctrl+C)');
    if (this.botaoEnviar) this.botaoEnviar.before(this.botaoCopiar); else this.abas.append(this.botaoCopiar);
    document.addEventListener('keydown', (ev) => {
      if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return;
      const k = (ev.key || '').toLowerCase();
      if (k !== 'c' && k !== 'v') return;
      if (document.querySelector('dialog[open]')) return;
      const a = ev.target;
      if (a && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA' || a.isContentEditable)) return;
      if (k === 'c') { if (this.copiarSelecao()) ev.preventDefault(); return; }
      if (this.ativa) { ev.preventDefault(); this.colar(); }
    });
  }

  /** Ctrl+C: o que está selecionado (o desenho do cliente, na Original) — depois os pontos de referência. */
  copiarSelecao() {
    const ids = [...this.cad.tela.selecao];
    const ents = ids.map(id => this.cad.doc.get(id)).filter(e => e && this.cad.doc.visivel(e) && !(e.atributos || {}).gerado);
    this._copiaPendente = null;
    if (!ents.length) {
      // na planta do cliente as camadas vêm travadas: sem seleção, a área. Pelo desenho aberto, não pela marca da aba
      // (ela só vem depois de o servidor responder: com ele ocupado — o 3D de 15 tesouras —, o Copiar não fazia nada)
      if (!this.cad.projeto || this.cad.nomeDesenho === 'montagem') return false;
      this.cad.ativarFerramenta('copiar-base');
      this.cad.aviso('Copiar: marque a área do desenho (dois cantos ou uma janela em volta da tesoura) e depois os dois pontos de referência — os apoios nos eixos.', 'info', 10000);
      return true;
    }
    this._prepararCopia(ents);
    this.cad.ativarFerramenta('copiar-base');
    this.cad.aviso(`${ents.length} objeto(s) a copiar: clique os dois pontos de referência — os apoios da tesoura nos eixos (a ponta do banzo sobre o eixo a e sobre o eixo c, por exemplo) — ou Enter para copiar sem pontos.`, 'info', 10000);
    return true;
  }

  /** o que vai ser copiado (clonado agora: o desenho pode trocar antes do Ctrl+V) */
  _prepararCopia(ents) {
    if (!ents || !ents.length) return false;
    this._copiaPendente = {
      ents: ents.map(e => JSON.parse(JSON.stringify(e))), kOrig: this.cad.doc.escala || 1, desenho: this.cad.nomeDesenho,
      camadas: Object.fromEntries([...new Set(ents.map(e => e.camada))].map(c => [c, { ...(this.cad.doc.camadas.get(c) || { nome: c }) }])),
    };
    return true;
  }

  _guardarCopia(refs) {
    const c = this._copiaPendente;
    if (!c) return;
    this._copiaPendente = null;
    c.refs = refs;
    c.caixa = caixaDe(c.ents.flatMap(e => pontosDe(e)));
    this._copia = c;
    this.cad.selecionar([]);
    this.cad.aviso(`${c.ents.length} objeto(s) copiado(s)${refs.length ? ` com ${refs.length} ponto(s) de referência` : ''}. Na Montagem, Ctrl+V cola na elevação: clique onde vão os pontos (os apoios nos eixos).`, 'info', 10000);
  }

  colar() {
    if (!this._copia) { this.cad.aviso('Nada copiado: no desenho do cliente (aba Original), selecione a tesoura e Ctrl+C.', 'atencao', 8000); return; }
    this.cad.ativarFerramenta('colar-base');
  }

  /** o quadro da folha que contém o ponto `p` (papel) */
  _quadroEm(p) {
    return (this.m && this.m.quadros.find(q => p[0] >= q.x && p[0] <= q.x + q.w && p[1] <= q.y && p[1] >= q.y - q.h)) || null;
  }

  /**
   * A transformação do desenho copiado para a folha: {f, k, ang, espelho, quadro}. Pelos dois pontos, a escala e o giro
   * saem dos pares de pontos (o par no sentido contrário é a tesoura vista do outro lado: espelho, não meia-volta); por
   * um ponto só, a escala do quadro onde ele cai (o desenho do cliente está em mm reais).
   */
  _transformacaoDaColagem(c, alvos, espelho = false) {
    if (!c || !alvos.length) return null;
    const refs = c.refs || [];
    const r1 = refs[0] || [c.caixa[0][0], c.caixa[0][1]];
    const a1 = alvos[0];
    const q = this._quadroEm(a1);
    let k, ang = 0, esp = espelho;
    if (refs.length === 2 && alvos.length === 2) {
      const vs = [refs[1][0] - refs[0][0], refs[1][1] - refs[0][1]], vd = [alvos[1][0] - a1[0], alvos[1][1] - a1[1]];
      const ls = Math.hypot(vs[0], vs[1]), ld = Math.hypot(vd[0], vd[1]);
      if (ls < 1e-6 || ld < 1e-6) return null;
      k = ld / ls;
      if (vs[0] * vd[0] < 0 && Math.abs(vs[0]) > Math.abs(vs[1])) esp = !esp;
      const vs2 = esp ? [-vs[0], vs[1]] : vs;
      ang = Math.atan2(vd[1], vd[0]) - Math.atan2(vs2[1], vs2[0]);
      if (Math.abs(ang) < 1e-9) ang = 0;
    } else {
      // da Montagem para ela mesma, o tamanho fica; do desenho do cliente (mm reais), a escala do quadro
      k = c.desenho === 'montagem' ? 1 : 1 / ((q && q.escala) || 50);
    }
    const co = Math.cos(ang), se = Math.sin(ang);
    const f = (p) => {
      let x = p[0] - r1[0];
      const y = p[1] - r1[1];
      if (esp) x = -x;
      return [a1[0] + k * (x * co - y * se), a1[1] + k * (x * se + y * co)];
    };
    return { f, k, ang, espelho: esp, quadro: q };
  }

  /** Cola o desenho copiado (Ctrl+Z desfaz) e confere a distância entre os pontos com a da elevação. */
  _colar(alvos, espelho) {
    const c = this._copia, t = this._transformacaoDaColagem(c, alvos, espelho);
    if (!t) return;
    const q = t.quadro;
    const graus = t.ang * 180 / Math.PI;
    const fAng = (a) => (t.espelho ? 180 - a : a) + graus;
    const colado = 'c' + Date.now().toString(36);
    const fator = (c.kOrig || 1) * t.k;                   // o que é mm de papel (texto, cota, hachura) acompanha
    const novos = c.ents.map(e => {
      const n = transformar(e, t.f, fAng, t.k, t.espelho);
      n.id = novoIdEntidade();
      if (n.altura != null && (n.tipo === 'texto' || n.tipo === 'cota' || n.tipo === 'chamada')) n.altura = n.altura * fator;
      if (n.tipo === 'cota') {
        n.deslocamento = (n.deslocamento || 0) * fator;
        if (e.texto == null || e.texto === '') n.texto = String(Math.round(valorCota(e) * (e.escala || 1)));
        n.escala = null;
      }
      if (n.tipo === 'hachura' && n.espacamento) n.espacamento = n.espacamento * fator;
      const at = { ...(n.atributos || {}), da_original: e.id, colado, ...(q ? { quadro: q.id } : {}) };
      delete at.gerado;
      n.atributos = at;
      return n;
    });
    for (const [nome, cam] of Object.entries(c.camadas || {})) {
      if (!this.cad.doc.camadas.has(nome)) this.cad.doc.camadas.set(nome, { ...cam, nome, bloqueada: false, visivel: true });
    }
    this.cad.executar(new ComandoAdicionar(novos, `Colar ${novos.length} objeto(s)`));
    if (q && q.tipo === 'elevacao' && q.mapa && (c.refs || []).length) {
      this.m.colagens = { ...(this.m.colagens || {}), [colado]: { quadro: q.id, refs_reais: alvos.map(a => this._paraReal(q, a)), desenho: c.desenho } };
      this._gravar();
    }
    this.cad.selecionar(novos.map(n => n.id));
    const onde = q ? (q.tipo === 'elevacao' ? ` na Elevação ${q.eixo}` : ` no quadro ${q.nome || q.tipo}`) : '';
    let nivel = 'info', conf = '';
    if ((c.refs || []).length === 2 && alvos.length === 2 && q && q.escala) {
      const src = Math.hypot(c.refs[1][0] - c.refs[0][0], c.refs[1][1] - c.refs[0][1]);
      const dst = Math.hypot(alvos[1][0] - alvos[0][0], alvos[1][1] - alvos[0][1]) * q.escala;
      const dif = dst - src;
      if (Math.abs(dif) <= Math.max(5, 0.002 * src)) conf = ` Medida conferida: ${numero(src / 1000, 3)} m entre os pontos, a mesma da elevação.`;
      else {
        nivel = 'atencao';
        conf = ` ATENÇÃO: no desenho do cliente são ${numero(src / 1000, 3)} m entre os pontos e na elevação ${numero(dst / 1000, 3)} m (${dif > 0 ? '+' : '−'}${Math.round(Math.abs(dif))} mm): o desenho foi ajustado aos pontos — confira o projeto.`;
      }
    }
    this.cad.aviso(`${novos.length} objeto(s) colado(s)${onde}${t.espelho ? ', espelhado' : ''}.${conf}` +
      (q && q.tipo === 'elevacao' ? ' Com ele selecionado, "Tesoura…" no título da elevação lança a tesoura nos eixos.' : ''), nivel, 14000);
  }

  // ------------------------------------------------------------------ o desenho colado vira a tesoura (etapa 2)
  /**
   * "Tesoura…" no título da elevação: o desenho selecionado dentro dela (banzos, diagonais, montantes — em linha simples
   * ou dupla) vira o tipo de tesoura (T1…) e é lançado no eixo da elevação e nos outros eixos marcados, como elemento da
   * implantação. O apoio (o ponto mais baixo) fica onde ele foi colado: o nível do projeto mais perto, com a diferença.
   */
  async tesouraDaElevacao(q) {
    const doc = this.cad.doc;
    const todasSel = [...this.cad.tela.selecao].map(id => doc.get(id)).filter(e => e && ['linha', 'polilinha', 'arco'].includes(e.tipo)
      && (e.atributos || {}).quadro === q.id && !(e.atributos || {}).gerado);
    if (todasSel.length < 3) {
      this.cad.aviso(`Selecione na Elevação ${q.eixo} o desenho da tesoura (banzos, diagonais e montantes — uma janela em volta dela) e use "Tesoura…" de novo.`, 'atencao', 10000);
      return;
    }
    const qi = this._quadroImplantacao();
    if (!qi || !qi.mapa || !this._eixosDaObra()) { this.cad.aviso('Dê os eixos da obra na Implantação primeiro (Eixos…).', 'atencao'); return; }
    // as camadas do desenho colado: o corte do cliente traz junto a telha, as cotas, o lanternim, as terças — ficam de fora
    // (o operador marca e desmarca; o CD Bom Dia, 11/10, virava 4.384 "barras" com tudo junto)
    const FORA = /cota|dim|texto|text|telha|lantern|ter[cç]a|hach|corrente|eixo|tracej/i;
    const porCamada = new Map();
    for (const e of todasSel) porCamada.set(e.camada, (porCamada.get(e.camada) || 0) + 1);
    const escolhidas = new Set([...porCamada.keys()].filter(c => !FORA.test(c)));
    if (!escolhidas.size) for (const c of porCamada.keys()) escolhidas.add(c);
    const vezes = new Map();
    for (const e of todasSel) { const c = (e.atributos || {}).colado; if (c) vezes.set(c, (vezes.get(c) || 0) + 1); }
    // duas colagens na seleção: a que traz a legenda de cores ("PERFIL … UE100x50x17x2.25mm", a folha de perfis do projeto,
    // colada por cima e alinhada) dá o perfil de cada barra; a outra (a elevação) dá a geometria — o CD Bom Dia, 11/10:
    // a folha "PERFIS TC1" tem as cores mas o leitor não acha nela o banzo inferior inclinado; a elevação tem a tesoura toda
    const legendaDe = new Map();
    for (const e of doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo === 'texto' && a.quadro === q.id && a.colado && vezes.has(a.colado) && /PERFIL[^]*U[E]?\s*\d/i.test(e.texto || '') && a.cor)
        legendaDe.set(a.colado, (legendaDe.get(a.colado) || 0) + 1);
    }
    const ordem = [...vezes.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0]);
    // as folhas de perfis (uma por meia tesoura, a segunda espelhada) e a geometria: a maior colagem sem legenda
    const perfisSet = new Set([...legendaDe.entries()].filter(([, n]) => n >= 2).map(([c]) => c));
    const idPerfis = perfisSet.size ? [...perfisSet][0] : null;
    const idColado = ordem.length > 1 && perfisSet.size ? (ordem.find(c => !perfisSet.has(c)) || ordem[0]) : ordem[0];
    // o desenho na medida real da elevação (u ao longo do eixo, z a cota). Primeiro o leitor do desenho detalhado (o do
    // quadro de tesoura da leitura por quadros: o banzo em linha dupla, a alma, a legenda dos perfis — o esqueleto em
    // linha de centro); sem tesoura achada, as linhas como linhas de eixo (desenhoDaTesoura)
    const real = (e) => transformar(e, (p) => this._paraReal(q, p), (a) => a, q.escala);
    const textos = [...doc.entidades.values()].filter(e => e.tipo === 'texto' && (e.atributos || {}).quadro === q.id && !(e.atributos || {}).gerado
      && (!idColado || (e.atributos || {}).colado === idColado)).map(real);
    let sel = [], des = null, u0 = 0, z0 = 0, leitura = null, reaisSel = [], legenda = null;
    // a legenda de cores da folha de perfis do projeto ("PERFIL DUPLO (CAIXA) UE127x50x17x2.00mm" escrito na cor das barras
    // daquele perfil, sob "BANZOS" e "MONTANTES E DIAGONAIS"): todos os textos da colagem, de qualquer camada
    const textosColagem = [...doc.entidades.values()].filter(e => e.tipo === 'texto' && (e.atributos || {}).quadro === q.id && !(e.atributos || {}).gerado
      && (!(idPerfis || idColado) || (perfisSet.size ? perfisSet.has((e.atributos || {}).colado) : (e.atributos || {}).colado === idColado))).map(real);
    // os traços coloridos da folha de perfis (todas as camadas dela), quando ela veio à parte
    const coresDaFolha = perfisSet.size && !perfisSet.has(idColado)
      ? todasSel.filter(e => perfisSet.has((e.atributos || {}).colado) && (e.atributos || {}).cor).map(real) : null;
    const ler = async () => {
      sel = todasSel.filter(e => escolhidas.has(e.camada) && (!coresDaFolha || (e.atributos || {}).colado === idColado));
      des = null; leitura = null; legenda = null;
      if (sel.length < 3) return false;
      const reais = sel.map(real);
      reaisSel = reais;
      try {
        // a legenda só das camadas da tesoura: o texto do pilar ao lado (o "W250x32.7" do PM2, CD Bom Dia) virava o banzo
        const r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/montagem/ler-tesoura`,
          { entidades: [...reais, ...textos.filter(x => escolhidas.has(x.camada))], nome: 'T1' });
        if (r && r.ok) { leitura = r; des = this._desenhoDaLeitura(r); }
      } catch { leitura = null; }
      if (!des) des = desenhoDaTesoura(reais);
      if (des) [u0, z0] = des.origem;
      if (des) legenda = this._perfisPelaLegenda(des, coresDaFolha || reaisSel, textosColagem);
      return !!(des && des.n >= 3);
    };
    if (!(await ler())) { this.cad.aviso('Não consegui ler a tesoura nessa seleção: são precisas ao menos três barras.', 'atencao'); return; }
    // o apoio: o ponto de referência da colagem (onde o operador pôs o apoio, no eixo e no nível); sem ele, o ponto mais
    // baixo do desenho — as mãos-francesas que descem até o pilar não puxam o nível para baixo
    const colagem = idColado && ((this.m.colagens || {})[idColado]);
    const refReal = colagem && colagem.quadro === q.id && (colagem.refs_reais || [])[0];
    // o ponto de referência longe da tesoura (colada pelo piso, nos eixos) não é o apoio: vale o ponto mais baixo dela
    const zApoio = () => (refReal && Math.abs(refReal[1] - z0) <= 1500 ? refReal[1] : z0);
    const pelaRef = () => !!(refReal && Math.abs(refReal[1] - z0) <= 1500);
    const [cat, niveis] = await Promise.all([this.cad.catalogoEstrutura(), this._niveis()]);
    const perto = [...niveis].sort((a, b) => Math.abs(a.z - zApoio()) - Math.abs(b.z - zApoio()))[0];
    const casado = perto && Math.abs(perto.z - zApoio()) <= 300 ? perto : null;
    const M = this.cad.medidasEstrutura || {};
    M.trelica = M.trelica || {};
    const grupos = cat.grupos.length ? cat.grupos : [['Perfis', [M.perfil || 'U 150×50×3,0']]];
    const todos = grupos.flatMap(([, ns]) => ns);
    const perfilSel = (k, padrao) => {
      const v = M.trelica[k] && todos.includes(M.trelica[k]) ? M.trelica[k] : padrao;
      const s = el('select', {}, ...grupos.map(([g, ns]) => el('optgroup', { label: g }, ...ns.map(n => el('option', { value: n, texto: rotuloPerfil(n, cat.dados[n]), selected: n === v ? 'selected' : undefined })))));
      s.style.cssText = 'flex:1 1 0;min-width:0;width:100%';
      return s;
    };
    const umU = todos.find(n => /^U(e)?\s*150/.test(n)) || todos.find(n => /^U/.test(n)) || todos[0];
    const umL = todos.find(n => /^L\s*50/.test(n)) || todos.find(n => /^L\s/.test(n)) || todos[0];
    const daLegenda = (k) => { const r = leitura && leitura.leitura && leitura.leitura[k]; const n = r && r.perfil; return n && todos.includes(n) ? n : null; };
    if (daLegenda('banzo')) { M.trelica.banzo_sup = daLegenda('banzo'); M.trelica.banzo_inf = daLegenda('banzo'); }
    if (daLegenda('alma')) M.trelica.diagonal = daLegenda('alma');
    const pSup = perfilSel('banzo_sup', umU), pInf = perfilSel('banzo_inf', umU), pDia = perfilSel('diagonal', umL);
    const cantSel = el('select', {}, el('option', { value: 'simples', texto: 'simples — uma cantoneira, numa aba do U' }), el('option', { value: 'dupla', texto: 'dupla — uma em cada aba do U' }));
    cantSel.value = M.trelica.cantoneira || 'simples';
    const acoSel = el('select', {}, ...(cat.acos.length ? cat.acos : ['ASTM A572 Gr.50']).map(a => el('option', { value: a, texto: a, selected: a === (M.trelica.aco || M.aco) ? 'selected' : undefined })));
    // a marca: a da tesoura que já veio deste desenho (colar de novo e lançar substitui), senão a próxima livre
    const trels = [...doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && (e.atributos || {}).quadro === qi.id);
    const idsSel = new Set(todasSel.map(e => e.id));
    const daFonte = trels.find(e => ((e.atributos.desenho || {}).fonte || []).some(id => idsSel.has(id)));
    const usadas = new Set(trels.map(e => e.atributos.marca));
    const livre = () => { let n = 1; while (usadas.has('T' + n)) n++; return 'T' + n; };
    const marca = el('input', { type: 'text', size: 6, value: daFonte ? daFonte.atributos.marca : livre(), spellcheck: 'false' });
    const nivSel = el('select', {}, el('option', { value: '', texto: '— número —' }),
      ...niveis.map(n => el('option', { value: n.nome, texto: `${n.nome} (${n.z ? cota(n.z) : '±0,00'})`, selected: casado && casado.nome === n.nome ? 'selected' : undefined })));
    const info = el('div', { class: 'explica' });
    const fam = this._familia(q.familia);
    const caixaEixos = el('div', { style: 'display:flex;flex-wrap:wrap;gap:4px 12px;max-height:120px;overflow:auto;min-width:0' },
      ...fam.map(e => el('label', { style: 'display:inline-flex;flex-direction:row;align-items:center;gap:4px;color:var(--texto);font-size:13px' },
        el('input', { type: 'checkbox', value: e.nome, checked: e.nome === q.eixo || trels.some(t => t.atributos.marca === (daFonte && daFonte.atributos.marca) && t.atributos.eixo === e.nome) }), e.nome)));
    const todosBtn = el('button', { type: 'button', texto: 'todos', onclick: () => { for (const c of caixaEixos.querySelectorAll('input')) c.checked = true; } });
    const cruz = this._cruzamDaElevacao(q);
    const escreverInfo = () => {
      if (!des) { info.textContent = 'Com essas camadas não sobram barras: marque a camada da tesoura.'; return; }
      const za = zApoio();
      const entre = cruz.filter(c => c.u >= u0 - 300 && c.u <= u0 + des.vao + 300).map(c => c.nome);
      const c = (leitura && leitura.leitura && leitura.leitura.contagem) || null;
      const modo = c ? `Lida como desenho detalhado: ${c.banzo || 0} trecho(s) de banzo, ${c.diagonal || 0} diagonal(is), ${c.montante || 0} montante(s) — ` : 'Lida como linhas de eixo: ';
      const aps = ((leitura && leitura.apontamentos) || []).filter(a => !/legenda|quantidade/.test(a.msg)).map(a => a.msg);
      info.textContent = modo + `${des.n} barras, ${numero(des.vao / 1000, 3)} m de comprimento e ${numero(des.altura / 1000, 3)} m de altura` +
        (entre.length ? ` (entre os eixos ${entre[0]} e ${entre[entre.length - 1]})` : '') +
        `. O apoio (${pelaRef() ? 'o ponto de referência da colagem' : 'o ponto mais baixo'}) está em ${cota(za)} m` +
        (casado ? (Math.abs(casado.z - za) < 1 ? `, no nível ${casado.nome}` : `, ${Math.round(za - casado.z)} mm ${za > casado.z ? 'acima' : 'abaixo'} do nível ${casado.nome}`) : ', sem nível perto (fica na cota do desenho)') +
        (pelaRef() && z0 < za - 1 ? `; o desenho desce até ${cota(z0)} m (o que vai até o pilar).` : '.') + ' A tesoura fica onde foi colada.' +
        (aps.length ? ` Apontamentos: ${aps.slice(0, 3).join('; ')}.` : '') +
        (legenda && legenda.n ? ` Perfis pela legenda de cores do desenho: ${legenda.n} de ${des.n} barras (${legenda.resumo}).` +
          (legenda.avisos.length ? ` ${legenda.avisos.join(' ')}` : '') : '');
      // as emendas (dois montantes de ponta lado a lado): tesouras encostadas no mesmo desenho
      const achadas = this._emendas(des);
      separar.querySelector('option[value=emendas]').disabled = !achadas.length;
      linhaPartes.style.display = 'grid';
      const cortes = separar.value === 'meio' ? [{ a: des.vao / 2, b: des.vao / 2 }] : separar.value === 'emendas' ? achadas : [];
      rotPartes.textContent = achadas.length ? `emendas achadas: ${achadas.length} (dois montantes de ponta lado a lado)` : '';
      marcasPartes.hidden = !cortes.length;
      if (cortes.length) {
        const ps = this._partesDoDesenho(des, cortes);
        const nomesC = cruz.map(c => c.nome);
        const ondeC = cortes.map(ct => { const cu = (ct.a + ct.b) / 2; const c = cruz.find(x => Math.abs(x.u - (u0 + cu)) < 1500); return c ? c.nome : `${numero((u0 + cu) / 1000, 2)} m`; });
        rotPartes.textContent = `${ps.length} tesouras de ${ps.map(x => numero(x.vao / 1000, 2)).join(' · ')} m (${separar.value === 'meio' ? 'no meio' : 'em ' + ondeC.join(', ')})`;
        if (!marcasPartes.dataset.mexido || marcasPartes.dataset.partes !== String(ps.length)) {
          const b = (marca.value || 'T1').trim().toUpperCase();
          marcasPartes.value = ps.length === 3 ? `${b}, ${b}C, ${b}` : ps.length === 2 ? `${b}, ${b}` : ps.map((_, i) => `${b}-${i + 1}`).join(', ');
          marcasPartes.dataset.partes = String(ps.length);
        }
        void nomesC;
      }
    };
    // separar nas emendas: as marcas das partes, em ordem (as pontas iguais podem ter a mesma marca: o mesmo tipo)
    const separar = el('select', {}, el('option', { value: '', texto: 'não separar' }), el('option', { value: 'emendas', texto: 'nas emendas achadas' }),
      el('option', { value: 'meio', texto: 'no meio (as duas meias tesouras)' }));
    separar.addEventListener('change', () => escreverInfo());
    const rotPartes = el('span', {});
    const marcasPartes = el('input', { type: 'text', spellcheck: 'false', style: 'flex:1 1 0;min-width:0;width:100%',
      title: 'As marcas das tesouras, na ordem da esquerda para a direita, separadas por vírgula (a mesma marca = o mesmo tipo)' });
    marcasPartes.addEventListener('keydown', ev => ev.stopPropagation());
    marcasPartes.addEventListener('input', () => { marcasPartes.dataset.mexido = '1'; });
    const linhaPartes = el('div', { style: 'display:none;grid-template-columns:140px minmax(0,1fr);gap:6px;align-items:start;margin:4px 0;font-size:12.5px' },
      el('span', { style: 'padding-top:3px' }, 'Separar'),
      el('div', { style: 'display:flex;flex-direction:column;gap:4px;min-width:0' }, separar, rotPartes, marcasPartes));
    escreverInfo();
    // as camadas: as escolhidas viram barras (contadas); mudar refaz a leitura
    const caixaCamadas = el('div', { style: 'display:flex;flex-wrap:wrap;gap:2px 12px;max-height:92px;overflow:auto;min-width:0' },
      ...[...porCamada.entries()].sort((a, b) => b[1] - a[1]).map(([c, n]) => {
        const cb = el('input', { type: 'checkbox', value: c, checked: escolhidas.has(c) });
        cb.addEventListener('change', async () => { if (cb.checked) escolhidas.add(c); else escolhidas.delete(c); info.textContent = 'Lendo…'; await ler(); escreverInfo(); });
        return el('label', { style: 'display:inline-flex;flex-direction:row;align-items:center;gap:4px;color:var(--texto);font-size:12.5px', title: `${n} objeto(s) na camada ${c}` }, cb, `${c} (${n})`);
      }));
    const GRADE = 'display:grid;grid-template-columns:140px minmax(0,1fr);gap:6px;align-items:center;margin:2px 0';
    const linha = (rot, ...x) => el('label', { style: GRADE + ';flex-direction:unset' }, rot, el('div', { style: 'display:flex;gap:6px;align-items:center;min-width:0' }, ...x));
    for (const s of [cantSel, acoSel, nivSel]) s.style.cssText = 'flex:1 1 0;min-width:0;width:100%';
    const corpo = el('div', {}, info,
      el('div', { style: GRADE + ';align-items:start;color:var(--texto2);font-size:12px' }, el('span', { style: 'padding-top:2px' }, 'Camadas da tesoura'), caixaCamadas),
      linha('Marca', marca), linhaPartes, linha('Banzo superior', pSup), linha('Banzo inferior', pInf), linha('Diagonais e montantes', pDia),
      linha('Cantoneiras', cantSel), linha('Aço', acoSel), linha('Nível do apoio', nivSel),
      el('div', { style: GRADE + ';align-items:start;color:var(--texto2);font-size:12px' }, el('span', { style: 'padding-top:2px' }, 'Lançar nos eixos ', todosBtn), caixaEixos));
    marca.addEventListener('keydown', ev => ev.stopPropagation());
    marca.addEventListener('input', () => { if (!marcasPartes.dataset.mexido) escreverInfo(); });
    const dlg = document.getElementById('dialogo');
    if (dlg) dlg.style.width = 'min(540px, calc(100vw - 32px))';
    const resp = await this.cad.dialogo({ titulo: `Tesoura da Elevação ${q.eixo}`, corpo, ok: 'Lançar' });
    if (dlg) dlg.style.width = '';
    if (resp !== 'ok') return;
    if (!des || des.n < 3) { this.cad.aviso('Nada lançado: com as camadas marcadas não sobram barras da tesoura.', 'atencao'); return; }
    const eixos = [...caixaEixos.querySelectorAll('input:checked')].map(i => i.value);
    if (!eixos.length) { this.cad.aviso('Nada lançado: marque ao menos um eixo.', 'atencao'); return; }
    M.trelica = { banzo_sup: pSup.value, banzo_inf: pInf.value, diagonal: pDia.value, aco: acoSel.value, cantoneira: cantSel.value };
    if (this.cad._guardarMedidas) this.cad._guardarMedidas();
    // as partes: o desenho inteiro, ou separado nas emendas (cada parte com a marca dela — decisão do usuário, 11/10:
    // no CD Bom Dia, TC1 de A a B, a central de B a C e TC1 de C a D)
    const cortes = separar.value === 'meio' ? [{ a: des.vao / 2, b: des.vao / 2 }] : separar.value === 'emendas' ? this._emendas(des) : [];
    let partes = [{ ...des, u0Rel: 0, v0Rel: 0 }];
    let marcasP = [(marca.value || 'T1').trim().toUpperCase()];
    if (cortes.length) {
      partes = this._partesDoDesenho(des, cortes);
      const ms = marcasPartes.value.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
      marcasP = partes.map((_, i) => ms[i] || ms[ms.length - 1] || `T${i + 1}`);
    }
    // a mesma marca em eixos que não foram marcados: todas mudam juntas, ou as novas viram outro tipo (T1A) — 11/10
    const conjunto = new Set(marcasP);
    const outras = trels.filter(t => conjunto.has(t.atributos.marca) && !eixos.includes(t.atributos.eixo));
    let todasJuntas = false;
    if (outras.length) {
      let s = 'A'; while ([...conjunto].some(m => usadas.has(m + s))) s = String.fromCharCode(s.charCodeAt(0) + 1);
      const rTodas = el('input', { type: 'radio', name: 'tipo-tesoura', value: 'todas', checked: true }), rSo = el('input', { type: 'radio', name: 'tipo-tesoura', value: 'so' });
      const lista = [...conjunto].join(', ');
      const c = el('div', {}, el('div', { class: 'explica', texto: `Já há ${lista} nos eixos ${[...new Set(outras.map(t => t.atributos.eixo))].join(', ')}, que não foram marcados.` }),
        el('label', { class: 'linha' }, rTodas, ` mudar todas para este desenho`),
        el('label', { class: 'linha' }, rSo, ` só os eixos marcados — viram ${[...conjunto].map(m => m + s).join(', ')}`));
      if (await this.cad.dialogo({ titulo: `Tesoura ${lista}`, corpo: c, ok: 'Lançar' }) !== 'ok') return;
      if (rTodas.checked) todasJuntas = true; else marcasP = marcasP.map(m => m + s);
    }
    const nv = niveis.find(n => n.nome === nivSel.value);
    // a ponta do desenho em cada eixo (no sistema dos eixos; o papel da implantação pelo mapa dela)
    const p0 = cruz.length ? cruz[0].pos : 0;
    const sent = cruz.length > 1 && cruz[1].u !== cruz[0].u ? Math.sign((cruz[1].pos - cruz[0].pos) / (cruz[1].u - cruz[0].u)) : 1;
    const posDe = (u) => p0 + u * sent;
    const atribDe = (parte, nomeP) => {
      const zP = z0 + parte.v0Rel;
      return { elemento: 'trelica', material: 'aco', marca: nomeP, quadro: qi.id, familia_eixo: q.familia,
        perfis: { banzo_sup: pSup.value, banzo_inf: pInf.value, diagonal: pDia.value }, cantoneira: cantSel.value, aco: acoSel.value,
        nivel_base: nivSel.value ? nivSel.value : Math.round(zP), acima_do_nivel: nv ? Math.round((zP - nv.z) * 10) / 10 : 0,
        desenho: { barras: parte.barras, vao: parte.vao, altura: parte.altura, raio_banzo_sup: parte.raio || null, fonte: sel.map(x => x.id), elevacao: q.id,
          ...(partes.length > 1 ? { parte: partes.indexOf(parte) + 1, partes: partes.length } : {}) } };
    };
    const novas = [];
    for (const nomeE of eixos) {
      const E = fam.find(e => e.nome === nomeE);
      if (!E) continue;
      partes.forEach((parte, i) => {
        const ua = u0 + parte.u0Rel, ub = ua + parte.vao;
        const ra = q.familia === 'numero' ? [E.pos, posDe(ua)] : [posDe(ua), E.pos];
        const rb = q.familia === 'numero' ? [E.pos, posDe(ub)] : [posDe(ub), E.pos];
        const a = this._paraPapel(qi, ra), b = this._paraPapel(qi, rb);
        const ent = criar({ tipo: 'linha', camada: 'ESTRUTURA', a, b, atributos: { ...atribDe(parte, marcasP[i]), eixo: E.nome } });
        const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
        novas.push(ent, criar({ tipo: 'texto', camada: 'ESTRUTURA', posicao: [m[0] - dy / L * 3 + 1, m[1] + dx / L * 3], texto: marcasP[i], altura: 2.5,
          atributos: { rotulo_de: ent.id, quadro: qi.id } }));
      });
    }
    if (!novas.length) return;
    // saem as tesouras dos eixos marcados que vieram deste desenho ou têm uma destas marcas (um eixo, uma vez cada
    // tesoura deste desenho) e, com "todas", as outras recebem o desenho da parte delas (a de mesma marca mais perto)
    const fonte = new Set(sel.map(x => x.id));
    const ao_ = (r) => ((q.familia === 'numero' ? r[1] : r[0]) - p0) * sent;
    const trecho = (e) => { const a = ao_(this._paraReal(qi, e.a)), b = ao_(this._paraReal(qi, e.b)); return [Math.min(a, b), Math.max(a, b)]; };
    const novosTrechos = partes.map(pt => [u0 + pt.u0Rel, u0 + pt.u0Rel + pt.vao]);
    const sobrepoe = (tr) => novosTrechos.some(([a, b]) => Math.min(b, tr[1]) - Math.max(a, tr[0]) > 0.3 * Math.min(b - a, tr[1] - tr[0]));
    const sair = trels.filter(t => eixos.includes(t.atributos.eixo) && t.atributos.familia_eixo === q.familia
      && (conjunto.has(t.atributos.marca) || ((t.atributos.desenho || {}).fonte || []).some(id => fonte.has(id))) && sobrepoe(trecho(t))).map(t => t.id);
    const cmds = [];
    if (sair.length) cmds.push(new ComandoRemover(this.cad._comRotulos ? this.cad._comRotulos(sair) : sair, `Tesouras antigas`));
    cmds.push(new ComandoAdicionar(novas, `Tesoura ${marcasP.join(', ')}`));
    if (todasJuntas) {
      const mud = {};
      for (const t of outras) {
        const ra = this._paraReal(qi, t.a), rb = this._paraReal(qi, t.b);
        const ao = (r) => ((q.familia === 'numero' ? r[1] : r[0]) - p0) * sent;
        const meio = (ao(ra) + ao(rb)) / 2;
        let melhor = -1, dm = Infinity;
        partes.forEach((parte, i) => { if (marcasP[i] !== t.atributos.marca) return; const d = Math.abs(u0 + parte.u0Rel + parte.vao / 2 - meio); if (d < dm) { dm = d; melhor = i; } });
        if (melhor >= 0) mud[t.id] = { atributos: { ...t.atributos, ...atribDe(partes[melhor], marcasP[melhor]), eixo: t.atributos.eixo } };
      }
      if (Object.keys(mud).length) cmds.push(new ComandoAlterar(mud, `Todas as ${[...conjunto].join(', ')}`));
    }
    if (!this.cad.doc.camadas.has('ESTRUTURA') && this.cad._garantirCamadaEstrutura) this.cad._garantirCamadaEstrutura();
    this.cad.executar(cmds.length > 1 ? new ComandoComposto(cmds, `Tesoura ${marcasP.join(', ')}`) : cmds[0]);
    const tipos = { ...(this.m.tipos || {}) };
    partes.forEach((parte, i) => { tipos[marcasP[i]] = { desenho: atribDe(parte, marcasP[i]).desenho, perfis: { banzo_sup: pSup.value, banzo_inf: pInf.value, diagonal: pDia.value },
      cantoneira: cantSel.value, aco: acoSel.value, elevacao: q.id, eixo: q.eixo }; });
    this.m.tipos = tipos;
    await this.refazerQuadrosDaObra(this._elevacoes());
    await this.cad.salvar({ avisar: false });
    const resumo = partes.length > 1 ? `${partes.length} tesouras por eixo (${marcasP.join(', ')})` : `Tesoura ${marcasP[0]}`;
    this.cad.aviso(`${resumo} lançada(s) nos eixos ${eixos.join(', ')}${todasJuntas ? ' (e as outras de mesma marca mudaram junto)' : ''}: apoio em ${cota(z0)} m. ` +
      'Aparecem na implantação e no 3D; duplo clique numa delas abre a elevação do eixo. Ctrl+Z desfaz.', 'info', 14000);
  }

  /** As emendas do desenho de uma tesoura: onde há dois montantes em pé lado a lado (150 a 800 mm, cada um com ao
   *  menos 0,5 m — o de ponta da TC1 do CD Bom Dia tem 1,5 m numa tesoura de 7 m) — tesouras encostadas no mesmo desenho, como as três do CD Bom Dia nos apoios da viga de
   *  transição. Devolve as emendas [{a, b}]: o montante de ponta de cada lado (u, do começo do desenho). */
  _emendas(des) {
    if (!des || !des.barras) return [];
    const us = [];
    for (const b of des.barras) {
      const du = Math.abs(b[2] - b[0]), dv = Math.abs(b[3] - b[1]);
      if (du <= 0.05 * dv && dv >= 500) us.push((b[0] + b[2]) / 2);
    }
    us.sort((a, b) => a - b);
    const juntos = [];
    for (const u of us) if (!juntos.length || u - juntos[juntos.length - 1][juntos[juntos.length - 1].length - 1] > 60) juntos.push([u]); else juntos[juntos.length - 1].push(u);
    const lin = juntos.map(g => g.reduce((s, x) => s + x, 0) / g.length);
    const cortes = [];
    for (let i = 0; i + 1 < lin.length; i++) {
      const d = lin[i + 1] - lin[i];
      if (d >= 150 && d <= 800 && lin[i] > 1000 && lin[i + 1] < des.vao - 1000) { cortes.push({ a: lin[i] + 30, b: lin[i + 1] - 30 }); i++; }      // ±30: as duas faces do montante em linha dupla ficam
    }
    return cortes;
  }

  /** O desenho separado nas emendas: o que atravessa a emenda é cortado nos montantes de ponta dos dois lados; o que
   *  fica entre eles (a seção da viga de transição em que as duas apoiam) sai; cada barra vai para a parte em que
   *  está. Cada parte com a origem no canto de baixo à esquerda dela ({barras, vao, altura, u0Rel, v0Rel}). */
  _partesDoDesenho(des, cortes) {
    const lim = [{ b: -Infinity }, ...cortes, { a: Infinity }];
    const em = (b, u) => { const t = (u - b[0]) / ((b[2] - b[0]) || 1e-9); return b[1] + (b[3] - b[1]) * t; };
    const r1 = (v) => Math.round(v * 10) / 10;
    const partes = [];
    for (let i = 0; i + 1 < lim.length; i++) {
      const ini = lim[i].b, fim = lim[i + 1].a;
      const bs = [];
      for (const b of des.barras) {
        const lo = Math.min(b[0], b[2]), hi = Math.max(b[0], b[2]);
        if (hi < ini - 1 || lo > fim + 1) continue;
        if (Math.abs(b[2] - b[0]) < 1) { bs.push(b); continue; }              // em pé: dentro (as pontas na emenda ficam)
        // o trecho dentro da parte (cortado nas emendas)
        const ua = Math.max(lo, ini), ub = Math.min(hi, fim);
        if (ub - ua < 5) continue;
        bs.push([ua, em(b, ua), ub, em(b, ub), ...b.slice(4)]);
      }
      if (!bs.length) continue;
      const u0 = Math.min(...bs.flatMap(b => [b[0], b[2]])), v0 = Math.min(...bs.flatMap(b => [b[1], b[3]]));
      const u1 = Math.max(...bs.flatMap(b => [b[0], b[2]])), v1 = Math.max(...bs.flatMap(b => [b[1], b[3]]));
      partes.push({ barras: bs.map(b => [r1(b[0] - u0), r1(b[1] - v0), r1(b[2] - u0), r1(b[3] - v0), ...b.slice(4)]), vao: r1(u1 - u0), altura: r1(v1 - v0),
        n: bs.length, u0Rel: u0, v0Rel: v0 });
    }
    return partes;
  }

  /**
   * Os perfis pela legenda de cores da folha de perfis do projeto (CD Bom Dia, "PERFIS TC1"): os textos "PERFIL
   * [SIMPLES|COMPOSTO|DUPLO (CAIXA)] UE100x50x17x2.25mm", escritos na cor das barras daquele perfil, sob "BANZOS" ou
   * "MONTANTES E DIAGONAIS". Cada barra do desenho lido pega a cor do traço desenhado nela e, pela legenda da função
   * dela, o perfil e a seção (b[5] e b[6] das barras: simples, composto ou caixa). Mexe em `des.barras`; devolve
   * {n, resumo, avisos}, ou null sem legenda.
   */
  _perfisPelaLegenda(des, reais, textos) {
    const RX = /PERFIL\s*(SIMPLES|COMPOSTO|DUPLO\s*\(?\s*CAIXA\s*\)?|DUPLO)?\s*(U[E]?)\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)(?:\s*[xX×]\s*(\d+(?:[.,]\d+)?))?\s*[xX×]\s*(\d+(?:[.,]\d+)?)/i;
    const titulos = textos.filter(e => /^\s*(BANZOS?|MONTANTES?|DIAGONA)/i.test(e.texto || ''));
    const itens = [];
    const num = (s) => String(s).replace('.', ',');
    for (const e of textos) {
      const m = RX.exec(e.texto || '');
      const cor = (e.atributos || {}).cor;
      if (!m || !cor) continue;
      const tipo = !m[1] ? 'simples' : /COMPOSTO/i.test(m[1]) ? 'composto' : /DUPLO/i.test(m[1]) ? 'caixa' : 'simples';
      const fam = m[2].toUpperCase() === 'UE' ? 'Ue' : 'U';
      const perfil = `${fam} ${[m[3], m[4], m[5], m[6]].filter(Boolean).map(num).join('×')}`;
      // a função pelo título mais perto à esquerda/acima (a coluna da legenda)
      let fn = null, dm = Infinity;
      for (const ti of titulos) {
        const dx = Math.abs(ti.posicao[0] - e.posicao[0]), dy = ti.posicao[1] - e.posicao[1];
        if (dy < -200 || dy > 3000) continue;
        const d = dx + dy * 0.3;
        if (d < dm) { dm = d; fn = /BANZO/i.test(ti.texto) ? 'banzo' : 'alma'; }
      }
      const it = { fn: fn || 'qualquer', cor: String(cor).toLowerCase(), tipo, perfil, texto: e.texto.trim() };
      // a mesma legenda duas vezes (a folha colada para cada meia tesoura) conta uma vez
      if (!itens.some(x => x.fn === it.fn && x.cor === it.cor && x.tipo === it.tipo && x.perfil === it.perfil)) itens.push(it);
    }
    if (!itens.length) return null;
    // os traços da seleção, com a cor
    const segs = [];
    for (const e of reais) {
      const cor = String((e.atributos || {}).cor || '').toLowerCase();
      if (!cor) continue;
      const pts = e.tipo === 'linha' ? [e.a, e.b] : e.tipo === 'polilinha' ? (e.fechada ? [...e.vertices, e.vertices[0]] : e.vertices) : [];
      for (let i = 0; i + 1 < pts.length; i++) segs.push([pts[i], pts[i + 1], cor]);
    }
    const [ou, ov] = des.origem;
    let n = 0;
    const conta = new Map(), ambiguas = new Set(), semLegenda = new Set();
    for (const b of des.barras) {
      const P0 = [b[0] + ou, b[1] + ov], P1 = [b[2] + ou, b[3] + ov];
      const L = Math.hypot(P1[0] - P0[0], P1[1] - P0[1]);
      if (L < 1) continue;
      const tu = [(P1[0] - P0[0]) / L, (P1[1] - P0[1]) / L];
      const votos = new Map();
      for (const [a, c, cor] of segs) {
        const ls = Math.hypot(c[0] - a[0], c[1] - a[1]);
        if (ls < 1 || Math.abs(((c[0] - a[0]) * tu[0] + (c[1] - a[1]) * tu[1]) / ls) < 0.998) continue;      // paralelo
        const m = [(a[0] + c[0]) / 2, (a[1] + c[1]) / 2];
        const lado = Math.abs((m[0] - P0[0]) * tu[1] - (m[1] - P0[1]) * tu[0]);
        if (lado > 90) continue;                                                        // as faces de até 180 mm
        const s0 = (a[0] - P0[0]) * tu[0] + (a[1] - P0[1]) * tu[1], s1 = (c[0] - P0[0]) * tu[0] + (c[1] - P0[1]) * tu[1];
        const cobre = Math.min(L, Math.max(s0, s1)) - Math.max(0, Math.min(s0, s1));
        if (cobre > 0) votos.set(cor, (votos.get(cor) || 0) + cobre);
      }
      const cor = [...votos.entries()].sort((x, y) => y[1] - x[1]).map(x => x[0])[0];
      if (!cor) continue;
      const fn = String(b[4]).startsWith('banzo') || b[4] === 'extremidade' ? 'banzo' : 'alma';
      const cand = itens.filter(it => it.cor === cor && (it.fn === fn || it.fn === 'qualquer'));
      if (!cand.length) { semLegenda.add(cor); continue; }
      const it = cand.find(x => x.tipo === 'simples') || cand[0];
      if (cand.length > 1) ambiguas.add(`${fn === 'banzo' ? 'banzo' : 'alma'} ${cand.map(x => x.texto.replace(/^PERFIL\s*/i, '')).join(' ou ')}`);
      b[5] = it.perfil; b[6] = it.tipo === 'simples' ? '' : it.tipo;
      n++;
      const k = `${it.perfil}${it.tipo !== 'simples' ? ' ' + it.tipo : ''}`;
      conta.set(k, (conta.get(k) || 0) + 1);
    }
    const avisos = [];
    if (ambiguas.size) avisos.push(`A mesma cor vale para mais de um perfil da legenda (${[...ambiguas].join('; ')}): usei o simples — confira.`);
    if (semLegenda.size) avisos.push(`${semLegenda.size} cor(es) das barras sem item na legenda: essas ficam com o perfil escolhido abaixo.`);
    return { n, resumo: [...conta.entries()].map(([k, v]) => `${v}× ${k}`).join(', '), avisos };
  }

  /** A leitura detalhada (membros em linha de centro: s ao longo, h acima da base) como o desenho do elemento "trelica":
   *  {barras: [u0, v0, u1, v1, papel], vao, altura, origem, n}. O banzo é o de baixo onde é o mais baixo naquele ponto. */
  _desenhoDaLeitura(r) {
    const ms = ((r.leitura || {}).membros || []).filter(m => !m.moldura);
    if (ms.length < 3) return null;
    const bz = ms.filter(m => m.papel === 'banzo');
    const hEm = (m, s) => (Math.abs(m.s1 - m.s0) < 1e-6 ? Math.min(m.h0, m.h1) : m.h0 + (m.h1 - m.h0) * (s - m.s0) / (m.s1 - m.s0));
    const barras = ms.map(m => {
      let papel = m.papel === 'montante' || m.papel === 'diagonal' ? m.papel : 'diagonal';
      if (m.papel === 'banzo') {
        const s = (m.s0 + m.s1) / 2, h = hEm(m, s);
        const outros = bz.filter(o => o !== m && Math.min(o.s0, o.s1) - 1 <= s && s <= Math.max(o.s0, o.s1) + 1).map(o => hEm(o, s));
        const abaixo = outros.some(x => x < h - 50), acima = outros.some(x => x > h + 50);
        // o trecho em linha dupla entre os dois banzos (a barra no meio do painel da tesoura central do CD Bom Dia, 11/10)
        // é da alma, não um terceiro banzo
        papel = abaixo && acima ? 'diagonal' : abaixo ? 'banzo_sup' : 'banzo_inf';
      }
      return [m.s0, m.h0, m.s1, m.h1, papel];
    });
    const hs = ms.flatMap(m => [m.h0, m.h1]), ss = ms.flatMap(m => [m.s0, m.s1]);
    const s0 = Math.min(...ss), h0 = Math.min(...hs);
    // a origem no canto de baixo à esquerda do esqueleto (o que desce abaixo da base, as mãos-francesas, também)
    const b = barras.map(x => [x[0] - s0, x[1] - h0, x[2] - s0, x[3] - h0, x[4]].map((v, i) => (i < 4 ? Math.round(v * 10) / 10 : v)));
    return { barras: b, vao: Math.round((Math.max(...ss) - s0) * 10) / 10, altura: Math.round((Math.max(...hs) - h0) * 10) / 10, raio: null,
      n: b.length, origem: [r.x_esq + s0, r.y_base + h0] };
  }

  // ------------------------------------------------------------------ os elementos acompanham nas elevações
  /** Quando um elemento da implantação muda (lançado, movido, apagado, desfeito), as elevações se refazem. */
  _ouvirElementos() {
    const doc = this.cad.doc;
    if (this._docOuvido === doc) return;
    this._docOuvido = doc;
    this._idsElementos = new Set([...doc.entidades.values()].filter(e => (e.atributos || {}).elemento).map(e => e.id));
    doc.aoMudar((ev) => {
      if (this._refazendo || !this.ativa || doc !== this.cad.doc) return;
      const mexeu = (ev.ids || []).some(id => this._idsElementos.has(id) || ((doc.get(id) || {}).atributos || {}).elemento);
      if (!mexeu) return;
      this._idsElementos = new Set([...doc.entidades.values()].filter(e => (e.atributos || {}).elemento).map(e => e.id));
      clearTimeout(this._timerElev);
      this._timerElev = setTimeout(() => { if (this.ativa && this._elevacoes().length) this.refazerQuadrosDaObra(this._elevacoes()); }, 450);
    });
  }

  /** As tesouras da implantação no eixo da elevação `q`, desenhadas nela (as barras, na cota do apoio). */
  _elementosNaElevacao(q, niveis, P) {
    const qi = this._quadroImplantacao();
    if (!qi || !qi.mapa) return [];
    const cruz = this._cruzamDaElevacao(q);
    if (!cruz.length) return [];
    const p0 = cruz[0].pos;
    const sent = cruz.length > 1 && cruz[1].u !== cruz[0].u ? Math.sign((cruz[1].pos - cruz[0].pos) / (cruz[1].u - cruz[0].u)) : 1;
    const tab = Object.fromEntries(niveis.map(n => [n.nome, n.z]));
    const out = [];
    for (const e of this.cad.doc.entidades.values()) {
      const a = e.atributos || {};
      if (a.elemento !== 'trelica' || a.quadro !== qi.id || a.eixo !== q.eixo || a.familia_eixo !== q.familia || e.tipo !== 'linha') continue;
      const d = a.desenho || {};
      if (!(d.vao > 0) || !Array.isArray(d.barras)) continue;
      const ao = (r) => ((q.familia === 'numero' ? r[1] : r[0]) - p0) * sent;
      const ua = ao(this._paraReal(qi, e.a)), ub = ao(this._paraReal(qi, e.b));
      const k = (ub - ua) / d.vao;
      const zb = (typeof a.nivel_base === 'string' ? (tab[a.nivel_base] ?? (parseFloat(a.nivel_base) || 0)) : (+a.nivel_base || 0)) + (+a.acima_do_nivel || 0);
      const at = { quadro: q.id, gerado: 'elevacao', elemento_ref: e.id, marca: a.marca };
      d.barras.forEach((b, i) => out.push(criar({ tipo: 'linha', camada: CAMADA_ELEMENTOS, a: P(ua + b[0] * k, zb + b[1]), b: P(ua + b[2] * k, zb + b[3]), atributos: { ...at, barra: i } })));
      const topo = Math.max(...d.barras.flatMap(b => [b[1], b[3]]));
      out.push(criar({ tipo: 'texto', camada: CAMADA_ELEMENTOS, posicao: P((ua + ub) / 2, zb + topo), texto: a.marca || '', altura: TXT, alinhamento: 'centro', vertical: 'base', atributos: at }));
    }
    return out;
  }
}

export { pontosDe };
