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

const LETRAS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const indiceLetra = (s) => [...s].reduce((t, ch) => t * 26 + LETRAS.indexOf(ch) + 1, 0) - 1;
const letraDe = (i) => (i < 26 ? LETRAS[i] : letraDe(Math.floor(i / 26) - 1) + LETRAS[i % 26]);

/**
 * O nome do eixo copiado para a posição `s` (lado medido do original `o`) pela ordem da família (06/10: "se copio um
 * eixo central ele não faz a sequência do eixo e sim da quantidade total"): entre o 4 e o 5 ele é o 5, e os seguintes
 * andam um (5→6, 6→7…); além do último, o seguinte; antes do primeiro, o primeiro. O mesmo com letras. Devolve
 * {nome, renomear: Map nome antigo → novo} (vazio quando não cabe na sequência: nomes como 5', família misturada).
 */
function nomeNaSequencia(o, s, eixos, usados) {
  const velho = String(o.atributos.eixo);
  const numero = /^\d+$/.test(velho), letra = /^[A-Z]+$/.test(velho);
  if (!numero && !letra) return { nome: proximoNome(velho, usados), renomear: new Map() };
  const valor = (n) => (numero ? (/^\d+$/.test(n) ? Number(n) : null) : (/^[A-Z]+$/.test(n) ? indiceLetra(n) : null));
  const nomeDe = (v) => (numero ? String(v) : letraDe(v));
  const fam = eixos.filter(e => paralelos(e, o)).map(e => ({ t: lado(o, e.a), v: valor(String(e.atributos.eixo)) })).filter(x => x.v !== null);
  if (!fam.length) return { nome: proximoNome(velho, usados), renomear: new Map() };
  const mn = fam.reduce((a, b) => (b.v < a.v ? b : a)), mx = fam.reduce((a, b) => (b.v > a.v ? b : a));
  // para que lado os nomes crescem (com um eixo só, para o lado da cópia)
  const sentido = Math.sign(mx.t - mn.t) || Math.sign(s) || 1;
  const depois = fam.filter(x => (x.t - s) * sentido > TOL);
  if (!depois.length) return { nome: proximoNome(velho, usados), renomear: new Map() };
  const v0 = Math.min(...depois.map(x => x.v));
  const renomear = new Map();
  for (const x of fam) if (x.v >= v0) renomear.set(nomeDe(x.v), nomeDe(x.v + 1));
  return { nome: nomeDe(v0), renomear };
}
/** o nome seguinte da família do eixo `nome` (7 depois do 6; C depois de B; AA depois de Z) que ainda não está em `usados` */
function proximoNome(nome, usados) {
  if (/^\d+'?$/.test(nome)) {
    let n = Math.max(0, ...[...usados].filter(u => /^\d+$/.test(u)).map(Number)) + 1;
    while (usados.has(String(n))) n++;
    return String(n);
  }
  const indice = (s) => [...s].reduce((t, ch) => t * 26 + LETRAS.indexOf(ch) + 1, 0) - 1;
  const letra = (i) => (i < 26 ? LETRAS[i] : letra(Math.floor(i / 26) - 1) + LETRAS[i % 26]);
  let i = Math.max(-1, ...[...usados].filter(u => /^[A-Z]+$/.test(u)).map(indice)) + 1;
  while (usados.has(letra(i))) i++;
  return letra(i);
}

/**
 * A cópia de um eixo da malha (Copiar, Mover com Ctrl) vira um eixo novo (06/10: "acabaram os eixos, como faço para
 * lançar novos?"): o nome seguinte da família (7, 8… ou C, D…), a bolinha e o nome dele, a cota até o eixo vizinho
 * (além do último eixo, a cadeia cresce e a total vai até ele; entre dois eixos, a cota daquele vão se divide) e, além
 * do último, as pontas dos eixos que o cruzam (as bolinhas vêm pelo acompanhamento). `copias` e `originais` na mesma
 * ordem; muda as cópias no lugar e devolve {novas: as entidades a acrescentar, trocas: as existentes trocadas}.
 */
export function eixosCopiados(doc, copias, originais) {
  const novas = [], trocas = new Map();
  const todas = [...doc.entidades.values()];
  const eixos = todas.filter(ehEixo);
  const usados = new Set(eixos.map(e => String(e.atributos.eixo)));
  const atual = (e) => trocas.get(e.id) || e;
  copias.forEach((c, i) => {
    const o = originais && originais[i];
    if (!ehEixo(c) || !ehEixo(o)) return;
    const s = lado(o, c.a);
    const velho = String(o.atributos.eixo);
    const { nome, renomear } = nomeNaSequencia(o, s, eixos, usados);
    // os eixos seguintes andam um nome (a linha, a bolinha e o texto dela), do mesmo lado da família
    if (renomear.size) {
      const daFamilia = new Set(eixos.filter(e => paralelos(e, o)).map(e => String(e.atributos.eixo)));
      for (const x of todas) {
        const xa = x.atributos || {};
        if (!renomear.has(String(xa.eixo)) || !daFamilia.has(String(xa.eixo)) || !(ehEixo(x) ? paralelos(x, o) : (xa.bolinha || xa.nome_eixo))) continue;
        const cur = atual(x), novo = renomear.get(String(xa.eixo));
        const n = { ...cur, atributos: { ...(cur.atributos || {}), eixo: novo } };
        if (x.tipo === 'texto' && xa.nome_eixo) n.texto = novo;
        trocas.set(x.id, criar(n));
      }
      for (const [a, b] of renomear) { usados.delete(a); usados.add(b); }
    }
    usados.add(nome);
    c.atributos = { ...c.atributos, eixo: nome };
    delete c.atributos.grupo_copia;
    // a bolinha e o nome copiados junto (selecionados com o eixo) ganham o nome novo; senão, são criados
    const juntas = copias.filter(x => x !== c && (x.atributos || {}).eixo === velho && ((x.atributos || {}).bolinha || (x.atributos || {}).nome_eixo) && noEixo(c, x.centro || x.posicao || [Infinity, Infinity]));
    if (juntas.length) {
      for (const x of juntas) { x.atributos = { ...x.atributos, eixo: nome }; if (x.tipo === 'texto') x.texto = nome; }
    } else {
      const uO = dir(o), uC = dir(c);
      for (const b of todas) {
        const ba = b.atributos || {};
        if (b.tipo !== 'circulo' || !ba.bolinha || ba.eixo !== velho || !noEixo(o, b.centro)) continue;
        const ponta = dist(b.centro, o.a) <= dist(b.centro, o.b) ? 'a' : 'b';
        const t = (b.centro[0] - o[ponta][0]) * uO[0] + (b.centro[1] - o[ponta][1]) * uO[1];
        const centro = [c[ponta][0] + uC[0] * t, c[ponta][1] + uC[1] * t];
        const d = [centro[0] - b.centro[0], centro[1] - b.centro[1]];
        novas.push(criar({ ...transladar(b, d), id: undefined, atributos: { ...ba, eixo: nome } }));
        for (const tx of todas) {
          const ta = tx.atributos || {};
          if (tx.tipo === 'texto' && ta.nome_eixo && ta.eixo === velho && dist(tx.posicao, b.centro) < TOL) novas.push(criar({ ...transladar(tx, d), id: undefined, texto: nome, atributos: { ...ta, eixo: nome } }));
        }
      }
    }
    if (Math.abs(s) < TOL || !paralelos(o, c)) return;
    // a família: os eixos paralelos (lado medido a partir do original) e as cotas da malha entre eles
    const n = normal(o);
    const lados = eixos.filter(e => paralelos(e, o)).map(e => lado(o, e.a));
    const emEixo = (q) => lados.find(l => Math.abs(lado(o, q) - l) < TOL);
    const cotas = todas.filter(k => k.tipo === 'cota' && (k.atributos || {}).malha && emEixo(k.p1) !== undefined && emEixo(k.p2) !== undefined && Math.abs(lado(o, k.p1) - lado(o, k.p2)) > TOL);
    const entre = (lo, hi) => lados.some(l => l > lo + TOL && l < hi - TOL);
    const mn = Math.min(...lados), mx = Math.max(...lados);
    const alem = s > mx + TOL ? mx : s < mn - TOL ? mn : null;    // o eixo do lado de onde a cópia passou
    const levarA = (q, alvo) => { const t = alvo - lado(o, q); return [q[0] + n[0] * t, q[1] + n[1] * t]; };
    for (const k of cotas) {
      const cur = atual(k);
      const t1 = lado(o, k.p1), t2 = lado(o, k.p2), lo = Math.min(t1, t2), hi = Math.max(t1, t2);
      const cadeia = !entre(lo, hi);
      if (alem === null) {
        // entre dois eixos: a cota daquele vão se divide em duas
        if (cadeia && s > lo + TOL && s < hi - TOL) {
          trocas.set(k.id, criar({ ...cur, p2: levarA(k.p2, s), texto_pos: null }));
          novas.push(criar({ ...cur, id: undefined, p1: levarA(k.p1, s), texto_pos: null }));
        }
        continue;
      }
      const naPonta = Math.abs(t1 - alem) < TOL ? 'p1' : Math.abs(t2 - alem) < TOL ? 'p2' : null;
      if (!naPonta) continue;
      if (cadeia) {
        // a cadeia cresce: a cota do último vão, repetida do último eixo até o novo (do mesmo lado)
        if (novas.some(x => x.tipo === 'cota' && x.atributos && x.atributos.de_eixo === c.id)) continue;
        const outra = naPonta === 'p1' ? 'p2' : 'p1';
        const nova = { ...cur, id: undefined, texto_pos: null, atributos: { ...(cur.atributos || {}), de_eixo: c.id } };
        nova[outra] = k[naPonta];
        nova[naPonta] = levarA(k[naPonta], s);
        novas.push(criar(nova));
      } else if ((alem === mx && hi === mx && lo === mn) || (alem === mn && lo === mn && hi === mx)) {
        trocas.set(k.id, criar({ ...cur, [naPonta]: levarA(k[naPonta], s), texto_pos: null }));     // a total vai até o novo
      }
    }
    for (const x of novas) if (x.atributos && x.atributos.de_eixo) { x.atributos = { ...x.atributos }; delete x.atributos.de_eixo; }
    if (alem === null) return;
    // além do último: as pontas dos eixos que cruzam vão junto (a mesma folga além do eixo novo)
    for (const x of eixos) {
      if (paralelos(x, o)) continue;
      const cur = atual(x), ux = dir(x);
      const k = ux[0] * n[0] + ux[1] * n[1];
      if (Math.abs(k) < 0.2) continue;
      const nova = { ...cur };
      for (const ponta of ['a', 'b']) {
        const sp = lado(o, x[ponta]);
        if (Math.abs(sp - alem) < TOL || (s - alem) * (sp - alem) <= 0) continue;     // só a ponta além do último
        if ((sp - s) * (s - alem) > TOL) continue;                                  // e que ainda não passa do novo
        const t = (s - alem) / k;
        nova[ponta] = [cur[ponta][0] + ux[0] * t, cur[ponta][1] + ux[1] * t];
      }
      if (nova.a !== cur.a || nova.b !== cur.b) trocas.set(x.id, criar(nova));
    }
  });
  return { novas, trocas: [...trocas.values()] };
}
