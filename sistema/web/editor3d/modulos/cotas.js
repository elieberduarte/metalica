// Cotas que acompanham as peças (F20 do levantamento de 14/10): a cota feita com a ferramenta Cotar guarda, em cada
// ponta, a peça e o ponto dela no sistema da própria peça — na barra, a distância à ponta mais perto ao longo do eixo e
// o ponto na seção; na chapa, o ponto no plano dela; no sólido, o vértice —; quando a peça muda (Mover, Esticar,
// Girar…), a cota se refaz pelas pontas novas, com o texto novo. O refazer não entra no Ctrl+Z: ele sai sempre do
// estado das peças, então desfazer a peça refaz a cota de volta.

import { baseDaBarra, normalDaChapa } from '../nucleo/documento.js';

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const comp = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const n = comp(a) || 1; return [a[0] / n, a[1] / n, a[2] / n]; };
const dist = (a, b) => comp(sub(a, b));

/** A medida no padrão brasileiro (a mesma de ferramentas/base.formatar). */
function formatar(mm) {
  if (!isFinite(mm)) return '—';
  if (Math.abs(mm) >= 1000) return (mm / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 3 }) + ' m';
  return mm.toLocaleString('pt-BR', { maximumFractionDigits: 0 }) + ' mm';
}

/** A referência do ponto `q` na peça `ent` (a que o snap pegou): {id, tipo, ...} ou null. */
export function refDoPonto(ent, q) {
  if (!ent || !q) return null;
  if (ent.tipo === 'barra') {
    const { t, u, v } = baseDaBarra(ent.inicio, ent.fim, ent.rotacao || 0);
    const L = dist(ent.inicio, ent.fim);
    const r = sub(q, ent.inicio);
    const s = dot(r, t);
    const ponta = s <= L - s ? 'inicio' : 'fim';
    return { id: ent.id, tipo: 'barra', ponta, s: ponta === 'inicio' ? s : L - s, x: dot(r, u), y: dot(r, v) };
  }
  if (ent.tipo === 'chapa') {
    const n = normalDaChapa(ent);
    const r = sub(q, ent.origem);
    return { id: ent.id, tipo: 'chapa', x: dot(r, ent.eixo_x), y: dot(r, ent.eixo_y), z: dot(r, n) };
  }
  if (ent.tipo === 'solido' && Array.isArray(ent.vertices) && !(ent.atributos && ent.atributos.tipo === 'cota')) {
    let melhor = -1, dm = Infinity;
    ent.vertices.forEach((p, i) => { const d = dist(p, q); if (d < dm) { dm = d; melhor = i; } });
    if (melhor >= 0 && dm < 0.5) return { id: ent.id, tipo: 'solido', i: melhor };
  }
  return null;
}

/** O ponto no mundo da referência, com a peça como está agora (null: a peça sumiu). */
export function pontoDaRef(doc, ref) {
  const ent = ref && doc.get(ref.id);
  if (!ent) return null;
  if (ref.tipo === 'barra' && ent.tipo === 'barra') {
    const { t, u, v } = baseDaBarra(ent.inicio, ent.fim, ent.rotacao || 0);
    const L = dist(ent.inicio, ent.fim);
    const s = ref.ponta === 'fim' ? L - ref.s : ref.s;
    return add(ent.inicio, add(mul(t, s), add(mul(u, ref.x), mul(v, ref.y))));
  }
  if (ref.tipo === 'chapa' && ent.tipo === 'chapa') {
    const n = normalDaChapa(ent);
    return add(ent.origem, add(mul(ent.eixo_x, ref.x), add(mul(ent.eixo_y, ref.y), mul(n, ref.z))));
  }
  if (ref.tipo === 'solido' && ent.vertices && ent.vertices[ref.i]) return ent.vertices[ref.i].slice();
  return null;
}

/** O desenho da cota de `a` a `b`, afastada `desloc` para o lado `lado`: {vertices, arestas} (o da ferramenta Cotar). */
export function geometriaDaCota(a, b, desloc, lado) {
  const dir = unit(sub(b, a));
  const off = mul(lado, desloc);
  const L = dist(a, b);
  // sobra da chamada e traço a 45° proporcionais à cota (numa cota de 60 mm os 60 e 45 mm fixos de antes eram maiores
  // que a própria medida), com os valores antigos de teto
  const s =Math.max(2, Math.min(60, 0.12 * L)), tr = Math.max(1.5, Math.min(45, 0.07 * L));
  const sobra = mul(lado, desloc >= 0 ? s : -s);
  const a1 = add(a, off), b1 = add(b, off);
  const a2 = add(a1, sobra), b2 = add(b1, sobra);
  const t = mul(add(dir, lado), tr / Math.SQRT2);
  const v = [a, b, a1, b1, a2, b2, sub(a1, t), add(a1, t), sub(b1, t), add(b1, t)];
  return { vertices: v, arestas: [[0, 4], [1, 5], [2, 3], [6, 7], [8, 9]] };
}

/** Os campos da cota refeita pelas referências, ou null quando nada mudou (ou não há referência). */
export function cotaRefeita(doc, cota) {
  const c = cota.atributos && cota.atributos.cota;
  if (!c || !Array.isArray(c.refs) || !c.refs.some(Boolean)) return null;
  const a = (c.refs[0] && pontoDaRef(doc, c.refs[0])) || c.a;
  const b = (c.refs[1] && pontoDaRef(doc, c.refs[1])) || c.b;
  if (!a || !b || dist(a, b) < 1e-6) return null;
  if (dist(a, c.a) < 1e-4 && dist(b, c.b) < 1e-4) return null;
  // o lado de afastamento: perpendicular à cota nova, no plano da normal de antes
  const dir = unit(sub(b, a));
  let n = c.normal || [0, 0, 1];
  if (Math.abs(dot(n, dir)) > 0.99) n = Math.abs(dir[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  n = unit(sub(n, mul(dir, dot(n, dir))));
  let lado = unit(cross(n, dir));
  if (c.lado && dot(lado, c.lado) < 0) { lado = mul(lado, -1); n = mul(n, -1); }
  const g = geometriaDaCota(a, b, c.deslocamento || 0, lado);
  const texto = formatar(dist(a, b));
  return { vertices: g.vertices, arestas_vivas: g.arestas, nome: texto,
           atributos: { ...cota.atributos, cota: { ...c, a, b, texto, normal: n, lado } } };
}

/** A cota está fora das pontas das peças a que foi presa (foi movida sozinha)? */
function saiuDasPecas(doc, c) {
  return [c.a, c.b].some((q, k) => {
    const p = c.refs[k] && pontoDaRef(doc, c.refs[k]);
    return p && q && dist(p, q) > 0.01;
  });
}

/** Liga a regeneração das cotas às mudanças do documento (o documento é o mesmo objeto ao abrir outro modelo). */
export function ligarCotasAssociativas(editor) {
  const doc = editor && editor.documento;
  if (!doc || typeof doc.aoMudar !== 'function') return;
  let refazendo = false;
  doc.aoMudar(({ ids, acao }) => {
    if (refazendo || acao === 'aparencia') return;
    const mudou = new Set(ids || []);
    const todas = acao === 'tudo' || !mudou.size;
    const cotas = [], soltar = [];
    for (const e of doc.entidades.values()) {
      const c = e.tipo === 'solido' && e.atributos && e.atributos.cota;
      if (!c || !Array.isArray(c.refs)) continue;
      if (mudou.has(e.id) && acao !== 'tudo' && !c.refs.some(r => r && mudou.has(r.id))) {
        // a cota mexida sozinha (sem as peças dela) e fora das pontas delas: ela se solta, como no SketchUp; a cota só
        // criada, desfeita ou copiada no lugar continua presa
        if (saiuDasPecas(doc, c)) soltar.push(e);
        continue;
      }
      if (todas || c.refs.some(r => r && mudou.has(r.id))) cotas.push(e);
    }
    if (!cotas.length && !soltar.length) return;
    refazendo = true;
    try {
      for (const e of soltar) doc.alterar(e.id, { atributos: { ...e.atributos, cota: { ...e.atributos.cota, refs: null } } });
      for (const e of cotas) {
        const campos = cotaRefeita(doc, e);
        if (campos) doc.alterar(e.id, campos);
      }
    } finally { refazendo = false; }
  });
}
