// A malha de eixos acompanha o eixo (pedido do usuário, 06/10: "movimentei os eixos e as bolotas não vieram junto").
//
// O eixo da malha (Lançamento → Malha de eixos) é a linha na camada EIXO com `atributos.malha` e o nome do eixo; a
// bolinha (círculo `bolinha`) e o nome (texto `nome_eixo`) ficam no prolongamento dela, além de uma ponta, e as cotas
// da malha (`atributos.malha`) têm as pontas nos cruzamentos dos eixos. Quando um comando troca a linha do eixo —
// a alça da ponta ou a do meio, Mover, Girar, Escala —, `acompanharMalha` devolve o resto que vai junto:
//   * a bolinha e o nome, à mesma distância além da ponta nova;
//   * as pontas das cotas da malha que estavam no eixo: no cruzamento do eixo novo com o outro eixo por onde a ponta
//     passa (a medida muda), ou levadas atravessado até o eixo novo;
//   * se o eixo só andou atravessado e é o último daquele lado, as pontas dos eixos que o cruzam (com as bolinhas),
//     para a folga além dele continuar a mesma.
// O que já está no comando (a bolinha selecionada junto, a malha inteira movida) fica como o comando mandou.

import { criar, dist, transladar } from './desenho2d.js';

const TOL = 1;                                         // mm: ponto "no eixo"

const ehEixo = (e) => !!(e && e.tipo === 'linha' && e.atributos && e.atributos.malha && e.atributos.eixo && dist(e.a, e.b) > 1e-6);
const dir = (e) => { const L = dist(e.a, e.b); return [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L]; };
const normal = (e) => { const u = dir(e); return [-u[1], u[0]]; };
const lado = (e, q) => { const n = normal(e); return (q[0] - e.a[0]) * n[0] + (q[1] - e.a[1]) * n[1]; };
const noEixo = (e, q) => Math.abs(lado(e, q)) < TOL;
const paralelos = (x, y) => { const u = dir(x), v = dir(y); return Math.abs(u[0] * v[1] - u[1] * v[0]) < 0.02; };

/** o cruzamento das retas de `x` e `y` (infinitas), ou null se paralelas */
function cruzamento(x, y) {
  const u = dir(x), v = dir(y), den = u[0] * v[1] - u[1] * v[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((y.a[0] - x.a[0]) * v[1] - (y.a[1] - x.a[1]) * v[0]) / den;
  return [x.a[0] + u[0] * t, x.a[1] + u[1] * t];
}

/**
 * O que acompanha os eixos da malha trocados em `novas` (as versões novas das entidades do comando): a lista das
 * entidades a mais (versões novas), sem as que já estão em `novas` e sem as de camada travada.
 */
export function acompanharMalha(doc, novas) {
  const noComando = new Map(novas.map(n => [n.id, n]));
  const mudados = novas.filter(n => {
    const v = doc.get(n.id);
    return ehEixo(v) && ehEixo(n) && (dist(v.a, n.a) > 1e-6 || dist(v.b, n.b) > 1e-6);
  });
  if (!mudados.length) return [];
  const travada = (e) => { const c = doc.camadas && doc.camadas.get ? doc.camadas.get(e.camada) : null; return !!(c && c.bloqueada); };
  const todas = [...doc.entidades.values()];
  const eixos = todas.filter(ehEixo);
  const extra = new Map();                             // id → versão nova (as que este acompanhamento mexe)
  const atual = (e) => noComando.get(e.id) || extra.get(e.id) || e;
  const levar = (e, nova) => { if (!noComando.has(e.id) && !travada(e)) extra.set(e.id, nova); };

  for (const nv of mudados) {
    const velho = doc.get(nv.id), nome = velho.atributos.eixo;
    const uV = dir(velho), uN = dir(nv);
    // a bolinha e o nome: além da ponta mais perto, à mesma distância, na direção nova
    for (const c of todas) {
      const a = c.atributos || {};
      if (c.tipo !== 'circulo' || !a.bolinha || a.eixo !== nome || noComando.has(c.id) || !noEixo(velho, c.centro)) continue;
      const ponta = dist(c.centro, velho.a) <= dist(c.centro, velho.b) ? 'a' : 'b';
      const s = (c.centro[0] - velho[ponta][0]) * uV[0] + (c.centro[1] - velho[ponta][1]) * uV[1];
      const centro = [nv[ponta][0] + uN[0] * s, nv[ponta][1] + uN[1] * s];
      const d = [centro[0] - c.centro[0], centro[1] - c.centro[1]];
      levar(c, transladar(c, d));
      for (const t of todas) {
        const ta = t.atributos || {};
        if (t.tipo === 'texto' && ta.nome_eixo && ta.eixo === nome && dist(t.posicao, c.centro) < TOL) levar(t, transladar(t, d));
      }
    }
    // as pontas das cotas da malha no eixo
    const levarPonto = (q) => {
      for (const y of eixos) {
        if (y.id === velho.id || paralelos(y, velho) || !noEixo(y, q)) continue;
        const p = cruzamento(nv, atual(y));
        if (p) return p;
      }
      // sem outro eixo ali: atravessado até o eixo novo
      const n = normal(velho), den = n[0] * normal(nv)[0] + n[1] * normal(nv)[1];
      if (Math.abs(den) < 1e-9) return q;
      const t = -lado(nv, q) / den;
      return [q[0] + n[0] * t, q[1] + n[1] * t];
    };
    for (const c of todas) {
      if (c.tipo !== 'cota' || !(c.atributos || {}).malha || noComando.has(c.id)) continue;
      const cur = atual(c);
      const q1 = noEixo(velho, c.p1), q2 = noEixo(velho, c.p2);
      if (!q1 && !q2) continue;
      const nova = { ...cur, p1: q1 ? levarPonto(c.p1) : cur.p1, p2: q2 ? levarPonto(c.p2) : cur.p2, texto_pos: null };
      if (dist(nova.p1, nova.p2) < 1e-6) continue;
      levar(c, criar(nova));
    }
    // só andou atravessado: o último eixo daquele lado leva as pontas dos que o cruzam
    const dA = [nv.a[0] - velho.a[0], nv.a[1] - velho.a[1]], dB = [nv.b[0] - velho.b[0], nv.b[1] - velho.b[1]];
    const s = dA[0] * normal(velho)[0] + dA[1] * normal(velho)[1];
    const translacao = Math.hypot(dA[0] - dB[0], dA[1] - dB[1]) < 1e-6 && Math.abs(s) > 1e-6;
    if (!translacao) continue;
    const ladosParalelos = eixos.filter(y => y.id !== velho.id && paralelos(y, velho)).map(y => lado(velho, y.a));
    for (const x of eixos) {
      if (x.id === velho.id || noComando.has(x.id) || paralelos(x, velho)) continue;
      const cur = atual(x), ux = dir(x), n = normal(velho);
      const k = ux[0] * n[0] + ux[1] * n[1];
      if (Math.abs(k) < 0.2) continue;
      const t = s / k, nova = { ...cur };
      const bolinhas = [];
      for (const ponta of ['a', 'b']) {
        const sp = lado(velho, x[ponta]);
        if (Math.abs(sp) < TOL || ladosParalelos.some(l => l * sp > 0 && Math.abs(l) <= Math.abs(sp) + TOL)) continue;
        nova[ponta] = [cur[ponta][0] + ux[0] * t, cur[ponta][1] + ux[1] * t];
        for (const c of todas) {
          const ca = c.atributos || {};
          if (c.tipo === 'circulo' && ca.bolinha && ca.eixo === x.atributos.eixo && !noComando.has(c.id) && dist(c.centro, x[ponta]) <= 1.6 * c.raio) bolinhas.push(c);
        }
      }
      if (nova.a === cur.a && nova.b === cur.b) continue;
      levar(x, criar(nova));
      const d = [ux[0] * t, ux[1] * t];
      for (const c of bolinhas) {
        levar(c, transladar(atual(c), d));
        for (const tx of todas) {
          const ta = tx.atributos || {};
          if (tx.tipo === 'texto' && ta.nome_eixo && ta.eixo === x.atributos.eixo && dist(tx.posicao, c.centro) < TOL) levar(tx, transladar(atual(tx), d));
        }
      }
    }
  }
  return [...extra.values()];
}
