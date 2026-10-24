// Os símbolos à mão das pranchas (usuário, 23/10: "pode seguir" a lista das ferramentas que faltam): solda AWS, balão
// de marca com a quantidade, nível (▽ +5,00) e chamada de detalhe. Cada símbolo é feito das entidades comuns (linha,
// polilinha, círculo, texto) com o mesmo `atributos.simbolo`: o clique pega o símbolo inteiro (cad.pecaDe), mover,
// copiar e apagar levam tudo, e a tela, o PDF e o DXF já sabem desenhar. Os parâmetros ficam em `atributos.params`.
// Medidas em mm de papel × k (a escala do desenho). O de solda é o do detalhamento (nucleo2d/detalhe/base.py,
// simbolo_solda): a linha de referência de 22 mm, o triângulo de 3,2 a 42% dela, a perna à esquerda e o comprimento à
// direita; embaixo da linha é o lado da seta.

import { novoId } from './desenho2d.js';

/** A largura estimada do texto (mm de papel), a mesma conta das cotas do servidor (0,62 × altura por letra). */
export const larguraTexto = (t, h) => 0.62 * h * String(t || '').length;

/** O nível como as pranchas escrevem: 5000 → "+5,00", −150 → "-0,15" (nucleo2d/detalhe/predio.py nivel_txt). */
export function textoDoNivel(mm) {
  const v = Math.round(mm / 10) / 100;
  return (v < 0 ? '-' : '+') + Math.abs(v).toFixed(2).replace('.', ',');
}

function marcar(regs, tipo, params) {
  const atributos = { simbolo: novoId(), simbolo_tipo: tipo, params };
  return regs.map(r => ({ ...r, atributos: { ...(r.atributos || {}), ...atributos } }));
}

/** A ponta de seta aberta (o "V"), como a do detalhamento (_Papel.seta). */
function seta(p, angulo, tam, camada) {
  return { tipo: 'polilinha', camada, fechada: false, vertices: [
    [p[0] - tam * Math.cos(angulo + 0.26), p[1] - tam * Math.sin(angulo + 0.26)], p,
    [p[0] - tam * Math.cos(angulo - 0.26), p[1] - tam * Math.sin(angulo - 0.26)]] };
}

const linha = (a, b, camada) => ({ tipo: 'linha', camada, a, b });
const texto = (posicao, t, h, camada, alinhamento = 'esquerda', vertical = 'base') => ({ tipo: 'texto', camada, posicao, texto: String(t), altura: h, alinhamento, vertical });
const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1).replace('.', ','));

/**
 * Solda AWS A2.4. `alvo` é o cordão (a ponta da seta), `ref` o começo da linha de referência (o lado dela diz para
 * onde a linha vai). `lado`: 'seta' (embaixo), 'outro' (em cima) ou 'ambos'; `forma`: 'filete' ou 'penetracao' (o
 * bisel); `comprimento` ou `intermitente` = [trecho, passo]; `contorno` (todo o contorno: o círculo na quebra),
 * `campo` (a bandeira da solda de campo) e `cauda` (a nota: "TÍP.", o processo).
 */
export function simboloSolda({ alvo, ref, perna = 6, comprimento = 0, intermitente = null, lado = 'seta', forma = 'filete',
  contorno = false, campo = false, cauda = '' }, k = 1, h = 2.5) {
  const C = 'SOLDA', out = [];
  out.push(linha(alvo, ref, C));
  out.push(seta(alvo, Math.atan2(alvo[1] - ref[1], alvo[0] - ref[0]), 2.5 * k, C));
  const dir = ref[0] >= alvo[0] ? 1 : -1;
  const comp = 22 * k * dir, [xr, y] = ref;
  out.push(linha(ref, [xr + comp, y], C));
  const bx = xr + comp * 0.42, larg = 22 * k * 0.16, tri = 3.2 * k;
  const lados = lado === 'ambos' ? [-1, 1] : lado === 'outro' ? [1] : [-1];
  for (const s of lados) {
    if (forma === 'penetracao') {
      out.push(linha([bx, y], [bx, y + tri * s], C));
      out.push(linha([bx, y], [bx + larg, y + tri * s], C));
    } else {
      out.push({ tipo: 'polilinha', camada: C, fechada: true, vertices: [[bx, y], [bx + larg, y], [bx, y + tri * s]] });
    }
    // a perna à esquerda do triângulo e o comprimento (ou trecho-passo) à direita, do mesmo lado da linha
    const yt = s < 0 ? y - 0.6 * k : y + 0.6 * k, v = s < 0 ? 'topo' : 'base';
    if (perna) out.push(texto([bx - 0.8 * k, yt], fmt(perna), h, C, 'direita', v));
    const dirTxt = intermitente ? `${fmt(intermitente[0])}-${fmt(intermitente[1])}` : comprimento ? fmt(comprimento) : '';
    if (dirTxt) out.push(texto([bx + larg + 0.8 * k, yt], dirTxt, h, C, 'esquerda', v));
  }
  if (contorno) out.push({ tipo: 'circulo', camada: C, centro: [xr, y], raio: 1.6 * k });
  if (campo) {
    // a bandeira na quebra, apontando para a cauda
    out.push({ tipo: 'polilinha', camada: C, fechada: false, vertices: [[xr, y], [xr, y + 4.6 * k], [xr + 2.6 * k * dir, y + 3.7 * k], [xr, y + 2.8 * k]] });
  }
  if (cauda) {
    const xc = xr + comp;
    out.push(linha([xc, y], [xc + 1.6 * k * dir, y + 1.6 * k], C));
    out.push(linha([xc, y], [xc + 1.6 * k * dir, y - 1.6 * k], C));
    out.push(texto([xc + 2.4 * k * dir, y], cauda, h, C, dir > 0 ? 'esquerda' : 'direita', 'meio'));
  }
  return marcar(out, 'solda', { perna, comprimento, intermitente, lado, forma, contorno, campo, cauda });
}

/** O raio do balão (mm de papel) que cabe a marca. */
export const raioDoBalao = (marca, h) => Math.max(4, larguraTexto(marca, h) / 2 + 1.5);

/**
 * Balão de marca: a seta na peça (`alvo`), a linha até o círculo em `centro`, a marca dentro e a quantidade ("4x")
 * do lado de fora, do lado oposto à linha. Sem `alvo` (ou com ele dentro do círculo), só o balão.
 */
export function simboloBalao({ alvo, centro, marca, quantidade = '' }, k = 1, h = 2.5) {
  const C = 'TEXTO', out = [];
  const r = raioDoBalao(marca, h) * k;
  out.push({ tipo: 'circulo', camada: C, centro, raio: r });
  out.push(texto(centro, marca, h, C, 'centro', 'meio'));
  const d = alvo ? Math.hypot(alvo[0] - centro[0], alvo[1] - centro[1]) : 0;
  let ladoQtd = 1;
  if (alvo && d > r + 0.5 * k) {
    const a = Math.atan2(alvo[1] - centro[1], alvo[0] - centro[0]);
    const borda = [centro[0] + r * Math.cos(a), centro[1] + r * Math.sin(a)];
    out.push(linha(borda, alvo, C));
    out.push(seta(alvo, a, 2.5 * k, C));
    ladoQtd = Math.cos(a) > 0 ? -1 : 1;
  }
  if (quantidade) {
    const q = /x$/i.test(quantidade) ? quantidade : `${quantidade}x`;
    out.push(texto([centro[0] + (r + 0.8 * k) * ladoQtd, centro[1]], q, h, C, ladoQtd > 0 ? 'esquerda' : 'direita', 'meio'));
  }
  return marcar(out, 'balao', { marca, quantidade });
}

/** Nível: o ▽ com a ponta no `ponto`, a linha por baixo e o valor em cima, à direita ("+5,00"). `valor` em mm. */
export function simboloNivel({ ponto, valor }, k = 1, h = 2.5) {
  const C = 'TEXTO', [x, y] = ponto;
  const t = textoDoNivel(valor);
  const fim = x + (2.6 + larguraTexto(t, h) + 1) * k;
  return marcar([
    { tipo: 'polilinha', camada: C, fechada: true, vertices: [[x, y], [x - 1.6 * k, y + 2.8 * k], [x + 1.6 * k, y + 2.8 * k]] },
    linha([x - 3 * k, y], [fim, y], C),
    texto([x + 2.6 * k, y + 0.8 * k], t, h, C),
  ], 'nivel', { valor });
}

/** O raio da bolha da chamada de detalhe (mm de papel). */
export const raioDaBolha = (numero, prancha, h) => Math.max(5.5, Math.max(larguraTexto(numero, h), larguraTexto(prancha, h)) / 2 + 1.8);

/**
 * Chamada de detalhe: o círculo tracejado em volta do trecho detalhado (`centro`, `raio` em mm do desenho), a linha
 * até a bolha em `bolha` e, nela, o número do detalhe em cima e a prancha embaixo ("1" / "03"; sem prancha, só o número).
 */
export function simboloDetalhe({ centro, raio, bolha, numero, prancha = '' }, k = 1, h = 2.5) {
  const C = 'TEXTO', out = [];
  const rb = raioDaBolha(numero, prancha, h) * k;
  out.push({ tipo: 'circulo', camada: C, centro, raio, tipo_linha: 'DASHED' });
  const a = Math.atan2(bolha[1] - centro[1], bolha[0] - centro[0]);
  const d = Math.hypot(bolha[0] - centro[0], bolha[1] - centro[1]);
  if (d > raio + rb) {
    out.push(linha([centro[0] + raio * Math.cos(a), centro[1] + raio * Math.sin(a)],
      [bolha[0] - rb * Math.cos(a), bolha[1] - rb * Math.sin(a)], C));
  }
  out.push({ tipo: 'circulo', camada: C, centro: bolha, raio: rb });
  if (prancha) {
    out.push(linha([bolha[0] - rb, bolha[1]], [bolha[0] + rb, bolha[1]], C));
    out.push(texto([bolha[0], bolha[1] + rb * 0.45], numero, h, C, 'centro', 'meio'));
    out.push(texto([bolha[0], bolha[1] - rb * 0.45], prancha, h, C, 'centro', 'meio'));
  } else {
    out.push(texto(bolha, numero, h, C, 'centro', 'meio'));
  }
  return marcar(out, 'detalhe', { numero, prancha, raio });
}

/** A marca de ponto (o POINT do AutoCAD, usuário 24/10: "marca de ponto" no Dividir): uma cruz de 3 mm de papel na camada
 *  AUXILIAR, contínua; o snap pega o meio dela (interseção e meio das duas linhas). */
export function simboloPonto(p, k = 1, tipo = 'ponto') {
  const m = 1.5 * k;
  return marcar([
    { tipo: 'linha', camada: 'AUXILIAR', tipo_linha: 'CONTINUOUS', a: [p[0] - m, p[1]], b: [p[0] + m, p[1]] },
    { tipo: 'linha', camada: 'AUXILIAR', tipo_linha: 'CONTINUOUS', a: [p[0], p[1] - m], b: [p[0], p[1] + m] },
  ], tipo, {});
}

/** Os pontos que dividem `e` em `n` partes iguais (o DIVIDE do AutoCAD): na linha, no arco e na polilinha aberta, os n − 1
 *  de dentro; no círculo e na polilinha fechada, n (o primeiro no começo). Outro tipo: []. */
export function pontosDaDivisao(e, n) {
  n = Math.floor(n);
  if (!(n >= 2)) return [];
  const rad = (g) => g * Math.PI / 180;
  if (e.tipo === 'circulo') {
    return Array.from({ length: n }, (_, i) => [e.centro[0] + e.raio * Math.cos(2 * Math.PI * i / n), e.centro[1] + e.raio * Math.sin(2 * Math.PI * i / n)]);
  }
  if (e.tipo === 'arco') {
    let a0 = e.inicio, a1 = e.fim;
    if (a1 < a0) a1 += 360;
    return Array.from({ length: n - 1 }, (_, i) => { const a = rad(a0 + (a1 - a0) * (i + 1) / n); return [e.centro[0] + e.raio * Math.cos(a), e.centro[1] + e.raio * Math.sin(a)]; });
  }
  let v;
  if (e.tipo === 'linha') v = [e.a, e.b];
  else if (e.tipo === 'polilinha') v = e.fechada && e.vertices.length > 2 ? [...e.vertices, e.vertices[0]] : e.vertices;
  else return [];
  const fechada = e.tipo === 'polilinha' && e.fechada && e.vertices.length > 2;
  const lens = v.slice(1).map((p, i) => Math.hypot(p[0] - v[i][0], p[1] - v[i][1]));
  const total = lens.reduce((s, x) => s + x, 0);
  if (!(total > 0)) return [];
  const out = [];
  for (let j = fechada ? 0 : 1; j < n; j++) {
    let falta = total * j / n, i = 0;
    while (i < lens.length - 1 && falta > lens[i]) { falta -= lens[i]; i++; }
    const t = lens[i] > 0 ? falta / lens[i] : 0;
    out.push([v[i][0] + (v[i + 1][0] - v[i][0]) * t, v[i][1] + (v[i + 1][1] - v[i][1]) * t]);
  }
  return out;
}
