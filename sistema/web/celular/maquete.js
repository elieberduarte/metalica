// A maquete na mesa, pela câmera do celular (usuário, 20/10: "usar o celular para mostrar com a câmera a peça no mundo
// real... tipo uma maquete, e depois evoluímos"): a realidade aumentada da Fase 1. A maquete sai do próprio 3D leve
// aberto (o .mcel que o celular já tem): o que está à vista, com as cores da tela, ou só o conjunto da peça tocada.
//
// * iPhone: o AR Quick Look da Apple abre um .usdz — feito aqui pelo exportador do three.js (lib/USDZExporter.js).
// * Android: a sessão de realidade aumentada do navegador (WebXR, Chrome com o ARCore), dentro desta tela: aponta para
//   a mesa, toca para pôr, dois dedos aumentam e giram.
// Nenhum dos dois precisa do PC nem da rede: o arquivo é montado no aparelho.
import * as THREE from 'three';

export const LADO_MESA = 0.6;      // m: o lado maior da maquete quando ela aparece na mesa
const MIN_PECA_OBRA = 80;          // mm: na obra inteira, as peças menores (parafusos, porcas, arruelas) ficam de fora
/** Os triângulos que cada caminho aguenta: o .usdz do iPhone é texto (~120 bytes por triângulo, ~35 MB em 300 mil);
 *  o Android desenha direto na placa, como o 3D da tela (usuário, 20/10, no S25: "muito simplificado, apenas polígonos"). */
export const LIMITES = { quicklook: 300000, webxr: 1000000 };
const CHEIA = 0.4;                 // volume da peça ÷ a caixa dela: acima disto é maciça (laje, bloco, parede) e vira caixa primeiro
const CLAREAR_NO_CLARO = 0.45;     // o mesmo do visor3d.js: no tema claro o 3D clareia as cores

/** Como este aparelho abre a realidade aumentada: 'quicklook' (iPhone/iPad), 'webxr' (Android com ARCore) ou null. */
export async function comoAbrir() {
  try { if (document.createElement('a').relList.supports('ar')) return 'quicklook'; } catch (e) { /* sem relList */ }
  try { if (navigator.xr && await navigator.xr.isSessionSupported('immersive-ar')) return 'webxr'; } catch (e) { /* sem WebXR */ }
  return null;
}

/** O conjunto da peça `i` para a maquete dele: a peça da montagem pela planta (TESOURA 1#2), ou as peças do mesmo
 *  conjunto que se tocam a partir dela (o conjunto se repete pela obra: só a cópia onde a peça está), ou a peça só. */
export function conjuntoDa(v, i) {
  const fichas = v.fichas, n = Math.min(fichas.length, v.nPecas), f = fichas[i];
  if (f.pc) {
    const ids = [];
    for (let k = 0; k < n; k++) if (fichas[k].pc === f.pc) ids.push(k);
    return { ids, nome: f.pl || f.pc.split('#')[0] };
  }
  if (f.cj && f.b) {
    const resto = [];
    for (let k = 0; k < n; k++) if (k !== i && fichas[k].cj === f.cj && fichas[k].b) resto.push(k);
    const encosta = (a, b) => a[0] <= b[3] + 30 && b[0] <= a[3] + 30 && a[1] <= b[4] + 30 && b[1] <= a[4] + 30 && a[2] <= b[5] + 30 && b[2] <= a[5] + 30;
    const ids = [i], fila = [i];
    while (fila.length) {
      const a = fichas[fila.pop()].b;
      for (let r = resto.length - 1; r >= 0; r--) if (encosta(a, fichas[resto[r]].b)) { ids.push(resto[r]); fila.push(resto[r]); resto.splice(r, 1); }
    }
    return { ids, nome: f.cj };
  }
  return { ids: [i], nome: f.pos || f.mc || f.n || 'Peça' };
}

/** O cabeçalho do .mcel (as camadas, os blocos, as formas). */
export function lerCabecalho(buf) {
  return JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 12, new DataView(buf).getUint32(8, true))));
}

/** A maquete do 3D aberto. Devolve o grupo do three.js em metros, com o Y para cima, centrado e apoiado no chão (o que a
 *  realidade aumentada espera), e os números dela. Opções:
 *  - `ids`: só estas peças (o conjunto da ficha); sem eles, a obra;
 *  - `todas`: a obra com todas as camadas, cada uma na sua malha, para ligar e desligar na câmera (o Android); sem
 *    isso, só o que está à vista (o .usdz do iPhone não liga e desliga nada);
 *  - `limite`: os triângulos que o caminho aguenta (LIMITES); `arestas`: as arestas escuras do 3D da tela;
 *  - `quadro`: o centro e a escala de outra maquete (a outra situação da cobertura retrátil: a parte fixa não pula);
 *  - `aoAndar(fração)`: o andamento. */
export async function montarMaquete(v, buf, opcoes = {}) {
  const { ids = null, todas = false, limite = LIMITES.quicklook, arestas: comArestas = false, quadro = null, aoAndar = null } = opcoes;
  const cab = lerCabecalho(buf);
  const fichas = v.fichas || [], nP = v.nPecas, obra = !ids;
  const cams = (v.cabecalho && v.cabecalho.camadas) || cab.camadas || [];
  const sistemas = v.sistemas || [];
  let sistemaDe = v.sistemaDe;
  if (!sistemaDe) {
    sistemaDe = new Uint8Array(nP).fill(255);
    sistemas.forEach((g, k) => { for (const i of g.ids) sistemaDe[i] = k; });
  }
  const quer = new Uint8Array(nP);
  if (ids) for (const i of ids) quer[i] = 1;
  else for (let i = 0; i < nP; i++) {
    if (todas || (v.visivelCamada[v.camadaDe[i]] !== false && !v.ocultas.has(i) && !v.ocultasSistema.has(i))) quer[i] = 1;
  }
  // na obra inteira, as peças pequenas (parafusos, porcas, arruelas) ficam de fora
  const tam = (i) => { const b = (fichas[i] || {}).b; return b ? Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) : Infinity; };
  let deFora = 0;
  if (obra) for (let i = 0; i < nP; i++) if (quer[i] && tam(i) < MIN_PECA_OBRA) { quer[i] = 0; deFora++; }
  const totalBlocos = cab.blocos.length + cab.formas.length;
  let andou = 0;
  const pausa = async (fase) => {
    if (++andou % 8) return;
    if (aoAndar) aoAndar(Math.min(1, (fase + andou / totalBlocos) / 2));
    await new Promise(r => setTimeout(r));
  };

  // 1ª volta: os triângulos e o volume de cada peça (o volume diz se ela é maciça)
  const tris = new Uint32Array(nP), vol = new Float64Array(nP);
  await percorrer(cab, buf, quer, (id, P) => {
    tris[id]++;
    const [a, b, c] = P;
    vol[id] += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6;
  }, () => pausa(0));
  andou = 0;
  // Passando do limite, peças viram a caixa justa delas — primeiro as maciças (a laje alveolar do Mercado: 590 mil dos
  // 853 mil triângulos, em alvéolos que a maquete não mostra), das mais pesadas para as mais leves; depois, se ainda não
  // couber, as outras (a barra vira uma caixa na direção dela). Só no fim saem as menores.
  const cheia = (i) => {
    const b = (fichas[i] || {}).b;
    if (!b) return 0;
    const cx = Math.max((b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]), 1);
    return Math.abs(vol[i]) / cx >= CHEIA ? 1 : 0;
  };
  let total = 0, simplificadas = 0;
  const caixa = new Uint8Array(nP), ordem = [];
  for (let i = 0; i < nP; i++) if (quer[i]) { total += tris[i]; ordem.push(i); }
  if (total > limite) {
    const ch = new Uint8Array(nP);
    for (const i of ordem) ch[i] = cheia(i);
    ordem.sort((a, b) => (ch[b] - ch[a]) || (tris[b] - tris[a]));
    for (const i of ordem) {
      if (total <= limite) break;
      if (tris[i] <= 12) continue;
      caixa[i] = 1; total -= tris[i] - 12; simplificadas++;
    }
    if (total > limite) {
      ordem.sort((a, b) => tam(b) - tam(a));
      total = 0;
      for (const i of ordem) { const t = caixa[i] ? 12 : tris[i]; if (total + t <= limite) total += t; else { quer[i] = 0; deFora++; } }
    }
  }

  // 2ª volta: as malhas, uma por camada, sistema e cor — a cor da tela, clareada como o 3D a mostra; o vértice se
  // repete só onde a face dobra, para o aço sair com as quinas vivas
  const grupos = new Map(), cb = v.corBase, k0 = v.escuro ? 0 : CLAREAR_NO_CLARO;
  const cl = (x) => Math.trunc(x + (255 - x) * k0);
  const chaveDe = (i) => v.camadaDe[i] * 256 + sistemaDe[i];
  const grupo = (i) => {
    const cor = (cl(cb[i * 3]) << 16) | (cl(cb[i * 3 + 1]) << 8) | cl(cb[i * 3 + 2]), k = chaveDe(i) * 16777216 + cor;
    let g = grupos.get(k);
    if (!g) grupos.set(k, (g = { cor, chave: chaveDe(i), pos: [], nor: [], idx: [] }));
    return g;
  };
  const pecas = new Set(), pontosCaixa = new Map();
  await percorrer(cab, buf, quer, (id, P, chaves, mapa) => {
    pecas.add(id);
    if (caixa[id]) {
      let l = pontosCaixa.get(id);
      if (!l) pontosCaixa.set(id, (l = []));
      for (const p of P) l.push(p[0], p[1], p[2]);
    } else triangulo(mapa, grupo(id), chaves, P);
  }, () => pausa(1));
  const linhas = comArestas ? new Map() : null;                         // camada e sistema → as arestas
  const linhasDe = (id) => { const k = chaveDe(id); let l = linhas.get(k); if (!l) linhas.set(k, (l = [])); return l; };
  for (const [id, l] of pontosCaixa) {
    const c = caixaJusta(l), mapa = new Map(), g = grupo(id);
    for (const [a, b, cc, d] of FACES_CAIXA) {
      triangulo(mapa, g, [a, b, cc], [c[a], c[b], c[cc]]);
      triangulo(mapa, g, [a, cc, d], [c[a], c[cc], c[d]]);
    }
    if (linhas) { const ls = linhasDe(id); for (const [a, b] of ARESTAS_CAIXA) ls.push(c[a][0], c[a][1], c[a][2], c[b][0], c[b][1], c[b][2]); }
  }
  if (linhas) percorrerArestas(cab, buf, quer, caixa, (id, A, B) => { linhasDe(id).push(A[0], A[1], A[2], B[0], B[1], B[2]); });

  // em metros, o Y para cima, no centro e no chão, no tamanho da mesa (ou no quadro da outra maquete)
  if (!pecas.size) return { grupo: new THREE.Group(), pecas: 0, triangulos: 0, arestas: 0, deFora, simplificadas, escala: 1, medidas: [0, 0, 0],
                            camadas: [], sistemas: [], quadro };
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const g of grupos.values()) for (let k = 0; k < g.pos.length; k += 3) for (let r = 0; r < 3; r++) {
    const x = g.pos[k + r]; if (x < min[r]) min[r] = x; if (x > max[r]) max[r] = x;
  }
  const q = quadro || { cx: (min[0] + max[0]) / 2, cy: (min[1] + max[1]) / 2, z0: min[2],
                        s: LADO_MESA / Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]) };    // de mm para os metros da mesa
  const paraMesa = (src, n) => {
    const dst = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) {
      dst[k * 3] = (src[k * 3] - q.cx) * q.s; dst[k * 3 + 1] = (src[k * 3 + 2] - q.z0) * q.s; dst[k * 3 + 2] = -(src[k * 3 + 1] - q.cy) * q.s;
    }
    return dst;
  };
  const marcar = (o, chave) => {
    const c = Math.floor(chave / 256), s = chave % 256;
    o.userData = { camada: (cams[c] || {}).nome || '', sistema: s < 255 && sistemas[s] ? sistemas[s].chave : '' };
  };
  const raiz = new THREE.Group();
  raiz.name = 'Maquete';
  let triangulos = 0;
  for (const g of grupos.values()) {
    const n = g.pos.length / 3, nor = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) { nor[k * 3] = g.nor[k * 3]; nor[k * 3 + 1] = g.nor[k * 3 + 2]; nor[k * 3 + 2] = -g.nor[k * 3 + 1]; }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(paraMesa(g.pos, n), 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(g.idx), 1));
    const cor = new THREE.Color().setRGB(((g.cor >> 16) & 255) / 255, ((g.cor >> 8) & 255) / 255, (g.cor & 255) / 255, THREE.SRGBColorSpace);
    // com as arestas, a face recua um pouco (como no 3D da tela) para a linha não piscar por cima dela
    const malha = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: cor, roughness: 0.7, metalness: 0.1, side: THREE.DoubleSide,
      polygonOffset: !!linhas, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
    malha.name = 'Cor_' + g.cor.toString(16).padStart(6, '0');
    marcar(malha, g.chave);
    raiz.add(malha);
    triangulos += g.idx.length / 3;
  }
  let nArestas = 0;
  if (linhas) {
    // fracas: na escala da maquete as nervuras das telhas ficam juntas e, fortes, escureciam o telhado inteiro (o 3D da
    // tela as esmaece com a distância)
    const material = new THREE.LineBasicMaterial({ color: 0x1b2433, transparent: true, opacity: 0.3, depthWrite: false });
    for (const [chave, l] of linhas) {
      if (!l.length) continue;
      const n = l.length / 3, geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(paraMesa(l, n), 3));
      const a = new THREE.LineSegments(geo, material);
      a.name = 'Arestas';
      marcar(a, chave);
      raiz.add(a);
      nArestas += n / 2;
    }
  }
  // as camadas e os sistemas que a maquete leva, ligados como estão na tela
  const camadas = new Map(), sisUsados = new Map();
  for (const id of pecas) {
    const c = v.camadaDe[id], nome = (cams[c] || {}).nome || '';
    if (!camadas.has(nome)) camadas.set(nome, v.visivelCamada[c] !== false);
    const s = sistemaDe[id];
    if (s < 255 && sistemas[s] && !sisUsados.has(sistemas[s].chave)) {
      sisUsados.set(sistemas[s].chave, { chave: sistemas[s].chave, nome: sistemas[s].nome, cor: sistemas[s].cor, ligado: !v.ocultasSistema.has(id) });
    }
  }
  return { grupo: raiz, pecas: pecas.size, triangulos, arestas: nArestas, deFora, simplificadas, escala: Math.round(1 / (q.s * 1000)),
           medidas: [(max[0] - min[0]) / 1000, (max[1] - min[1]) / 1000, (max[2] - min[2]) / 1000], quadro: q,
           camadas: [...camadas].map(([nome, ligada]) => ({ nome, ligada })), sistemas: [...sisUsados.values()] };
}

/** O 3D da outra situação da cobertura retrátil, para a maquete dela: as fichas e as camadas do arquivo dela, com a
 *  cor, a camada ligada e o sistema da mesma peça (pelo id) no 3D aberto. */
export function visorDaOutra(v, fichas, camadas) {
  const pos = new Map(v.fichas.map((f, i) => [f.id, i])), n = fichas.length;
  const sistemaDe = new Uint8Array(n).fill(255), deV = new Uint8Array(v.nPecas).fill(255);
  (v.sistemas || []).forEach((g, k) => { for (const i of g.ids) deV[i] = k; });
  const corBase = new Uint8Array(n * 3), camadaDe = new Uint16Array(n), ocultasSistema = new Set();
  for (let j = 0; j < n; j++) {
    camadaDe[j] = fichas[j].c || 0;
    const i = pos.get(fichas[j].id);
    if (i === undefined) { corBase.set([138, 148, 166], j * 3); continue; }
    corBase.set(v.corBase.subarray(i * 3, i * 3 + 3), j * 3);
    sistemaDe[j] = deV[i];
    if (v.ocultasSistema.has(i)) ocultasSistema.add(j);
  }
  const visivelCamada = camadas.map(c => {
    const k = v.cabecalho.camadas.findIndex(x => x.nome === c.nome);
    return k >= 0 ? v.visivelCamada[k] !== false : c.visivel !== false;
  });
  return { fichas, nPecas: n, corBase, camadaDe, visivelCamada, ocultas: new Set(), ocultasSistema, escuro: v.escuro,
           cabecalho: { camadas }, sistemas: v.sistemas || [], sistemaDe };
}

/** O desenho do piso na maquete (o arquitetônico, os eixos com os balões e os níveis — referencia.js, o mesmo do 3D),
 *  no quadro dela; os balões e as placas dos níveis no tamanho do modelo (no 3D da tela eles acompanham o zoom). */
export async function pisoDaMaquete(dados, quadro, origem, caixa = null) {
  if (!dados || !quadro) return null;
  const { montarReferencia } = await import('../visor3d/referencia.js');
  const ref = montarReferencia(dados, { escuro: false, caixa, zChao: -2 });           // como o 3D da tela (visor3d.definirReferencia)
  if (!ref.children.length) return null;
  const o = origem || [0, 0, 0];
  ref.position.set(-o[0], -o[1], -o[2]);
  ref.traverse(x => { x.onBeforeRender = () => {}; });
  const meio = new THREE.Group();                                       // mm, z para cima, no centro e no chão
  meio.position.set(-quadro.cx, -quadro.cy, -quadro.z0);
  meio.add(ref);
  const pe = new THREE.Group();                                         // y para cima
  pe.rotation.x = -Math.PI / 2;
  pe.add(meio);
  const piso = new THREE.Group();
  piso.name = 'Piso';
  piso.scale.setScalar(quadro.s);
  piso.add(pe);
  piso.userData.partes = ref.children.map(g => g.name);
  piso.userData.ref = ref;
  return piso;
}

/** Liga e desliga, na maquete, o que a pessoa escolheu: `desligadas` tem 'camada:<nome>', 'sistema:<chave>' e
 *  'piso:<parte>' (arquitetonico, eixos, niveis). */
export function aplicarVisiveis(raiz, desligadas) {
  raiz.traverse(o => {
    const u = o.userData || {};
    if (u.camada !== undefined) o.visible = !desligadas.has('camada:' + u.camada) && !(u.sistema && desligadas.has('sistema:' + u.sistema));
    if (u.ref) for (const g of u.ref.children) g.visible = !desligadas.has('piso:' + g.name);
  });
}

/** Cada triângulo das peças pedidas, já na posição da obra (mm, z para cima): `aoTri(id, [A, B, C], chaves, mapa)` —
 *  `chaves` são os números dos vértices no bloco (ou na forma) e `mapa` é um por bloco (ou por cópia da forma). */
async function percorrer(cab, buf, quer, aoTri, pausa) {
  const P = [new Float64Array(3), new Float64Array(3), new Float64Array(3)], ch = [0, 0, 0];
  for (const b of cab.blocos) {
    const vs = new Uint16Array(buf, b.vertices.ofs, b.vertices.n * 4), ix = _indices(buf, b.indices), mapa = new Map();
    for (let t = 0; t < ix.length; t += 3) {
      const id = b.id0 + vs[ix[t] * 4 + 3];
      if (!quer[id]) continue;
      for (let k = 0; k < 3; k++) {
        const q = ix[t + k] * 4;
        ch[k] = ix[t + k];
        P[k][0] = b.min[0] + vs[q] * b.esc[0]; P[k][1] = b.min[1] + vs[q + 1] * b.esc[1]; P[k][2] = b.min[2] + vs[q + 2] * b.esc[2];
      }
      aoTri(id, P, ch, mapa);
    }
    await pausa();
  }
  for (const f of cab.formas) {
    const vs = new Uint16Array(buf, f.vertices.ofs, f.vertices.n * 4), ix = _indices(buf, f.indices);
    const inst = new Float32Array(buf, f.copias.ofs, f.copias.n * 13);
    for (let c = 0; c < f.copias.n; c++) {
      const m = c * 13, id = inst[m + 12];
      if (!quer[id]) continue;
      const mapa = new Map();
      for (let t = 0; t < ix.length; t += 3) {
        for (let k = 0; k < 3; k++) {
          const q = ix[t + k] * 4, x = vs[q], y = vs[q + 1], z = vs[q + 2];
          ch[k] = ix[t + k];
          for (let r = 0; r < 3; r++) P[k][r] = inst[m + r * 4] * x + inst[m + r * 4 + 1] * y + inst[m + r * 4 + 2] * z + inst[m + r * 4 + 3];
        }
        aoTri(id, P, ch, mapa);
      }
    }
    await pausa();
  }
}

/** As arestas do 3D da tela (as do pacote: borda de face ou dobra) das peças pedidas que não viraram caixa. */
function percorrerArestas(cab, buf, quer, caixa, aoSeg) {
  const A = [0, 0, 0], B = [0, 0, 0], AB = [A, B];
  for (const b of cab.blocos) {
    if (!b.arestas || !b.arestas.n) continue;
    const vs = new Uint16Array(buf, b.vertices.ofs, b.vertices.n * 4), ix = _indices(buf, b.arestas);
    for (let t = 0; t < ix.length; t += 2) {
      const id = b.id0 + vs[ix[t] * 4 + 3];
      if (!quer[id] || caixa[id]) continue;
      for (let k = 0; k < 2; k++) {
        const q = ix[t + k] * 4, X = AB[k];
        X[0] = b.min[0] + vs[q] * b.esc[0]; X[1] = b.min[1] + vs[q + 1] * b.esc[1]; X[2] = b.min[2] + vs[q + 2] * b.esc[2];
      }
      aoSeg(id, A, B);
    }
  }
  for (const f of cab.formas) {
    if (!f.arestas || !f.arestas.n) continue;
    const vs = new Uint16Array(buf, f.vertices.ofs, f.vertices.n * 4), ix = _indices(buf, f.arestas);
    const inst = new Float32Array(buf, f.copias.ofs, f.copias.n * 13);
    for (let c = 0; c < f.copias.n; c++) {
      const m = c * 13, id = inst[m + 12];
      if (!quer[id] || caixa[id]) continue;
      for (let t = 0; t < ix.length; t += 2) {
        for (let k = 0; k < 2; k++) {
          const q = ix[t + k] * 4, x = vs[q], y = vs[q + 1], z = vs[q + 2], X = AB[k];
          for (let r = 0; r < 3; r++) X[r] = inst[m + r * 4] * x + inst[m + r * 4 + 1] * y + inst[m + r * 4 + 2] * z + inst[m + r * 4 + 3];
        }
        aoSeg(id, A, B);
      }
    }
  }
}

const _indices = (buf, d) => new (d.tipo === 'u32' ? Uint32Array : Uint16Array)(buf, d.ofs, d.n);

/** O triângulo na malha da cor, com a normal da face; o vértice se repete só onde a face dobra (a chave junta o número
 *  do vértice e a normal arredondada). */
function triangulo(mapa, g, chaves, pts) {
  const [a, b, c] = pts;
  const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], wx = c[0] - a[0], wy = c[1] - a[1], wz = c[2] - a[2];
  let nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
  const l = Math.hypot(nx, ny, nz);
  if (!(l > 1e-9)) return;
  nx /= l; ny /= l; nz /= l;
  const codigo = ((Math.round(nx * 64) + 64) * 129 + (Math.round(ny * 64) + 64)) * 129 + (Math.round(nz * 64) + 64);
  for (let k = 0; k < 3; k++) {
    const chave = chaves[k] * 2097152 + codigo;
    let j = mapa.get(chave);
    if (j === undefined) {
      j = g.pos.length / 3;
      g.pos.push(pts[k][0], pts[k][1], pts[k][2]);
      g.nor.push(nx, ny, nz);
      mapa.set(chave, j);
    }
    g.idx.push(j);
  }
}

const FACES_CAIXA = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
const ARESTAS_CAIXA = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];

/** A caixa justa dos pontos `l` (x, y, z…), nos eixos principais deles (a barra inclinada da tesoura sai na direção
 *  dela — com a caixa só girada na planta, a diagonal virava uma placa da altura dela: usuário, 20/10, no S25); se a
 *  caixa alinhada aos eixos da obra for menor, vale ela. Os 8 cantos, na ordem de FACES_CAIXA. */
function caixaJusta(l) {
  const n = l.length / 3, m = [0, 0, 0];
  for (let k = 0; k < n; k++) for (let r = 0; r < 3; r++) m[r] += l[k * 3 + r] / n;
  const c = [0, 0, 0, 0, 0, 0];
  for (let k = 0; k < n; k++) {
    const x = l[k * 3] - m[0], y = l[k * 3 + 1] - m[1], z = l[k * 3 + 2] - m[2];
    c[0] += x * x; c[1] += x * y; c[2] += x * z; c[3] += y * y; c[4] += y * z; c[5] += z * z;
  }
  const medir = (eixos) => {
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (let k = 0; k < n; k++) for (let r = 0; r < 3; r++) {
      const e = eixos[r], t = l[k * 3] * e[0] + l[k * 3 + 1] * e[1] + l[k * 3 + 2] * e[2];
      if (t < lo[r]) lo[r] = t;
      if (t > hi[r]) hi[r] = t;
    }
    return { eixos, lo, hi, vol: (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2]) };
  };
  const e = eixosPrincipais(c);
  // a mão direita (o primeiro × o segundo = o terceiro), para as faces saírem viradas para fora
  e[2] = [e[0][1] * e[1][2] - e[0][2] * e[1][1], e[0][2] * e[1][0] - e[0][0] * e[1][2], e[0][0] * e[1][1] - e[0][1] * e[1][0]];
  const principal = medir(e), alinhada = medir([[1, 0, 0], [0, 1, 0], [0, 0, 1]]);
  const { eixos, lo, hi } = alinhada.vol <= principal.vol * 1.001 ? alinhada : principal;
  const ponto = (a, b, cc) => [0, 1, 2].map(r => a * eixos[0][r] + b * eixos[1][r] + cc * eixos[2][r]);
  return [ponto(lo[0], lo[1], lo[2]), ponto(hi[0], lo[1], lo[2]), ponto(hi[0], hi[1], lo[2]), ponto(lo[0], hi[1], lo[2]),
          ponto(lo[0], lo[1], hi[2]), ponto(hi[0], lo[1], hi[2]), ponto(hi[0], hi[1], hi[2]), ponto(lo[0], hi[1], hi[2])];
}

/** Os eixos principais da nuvem de pontos (a matriz de covariância c = [xx, xy, xz, yy, yz, zz]), por Jacobi. */
function eixosPrincipais(c) {
  const a = [[c[0], c[1], c[2]], [c[1], c[3], c[4]], [c[2], c[4], c[5]]], v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let it = 0; it < 24; it++) {
    let p = 0, q = 1;
    if (Math.abs(a[0][2]) > Math.abs(a[p][q])) { p = 0; q = 2; }
    if (Math.abs(a[1][2]) > Math.abs(a[p][q])) { p = 1; q = 2; }
    if (Math.abs(a[p][q]) <= 1e-12 * (Math.abs(a[0][0]) + Math.abs(a[1][1]) + Math.abs(a[2][2])) + 1e-300) break;
    const th = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]), co = Math.cos(th), s = Math.sin(th);
    for (let k = 0; k < 3; k++) { const x = a[k][p], y = a[k][q]; a[k][p] = co * x - s * y; a[k][q] = s * x + co * y; }
    for (let k = 0; k < 3; k++) { const x = a[p][k], y = a[q][k]; a[p][k] = co * x - s * y; a[q][k] = s * x + co * y; }
    for (let k = 0; k < 3; k++) { const x = v[k][p], y = v[k][q]; v[k][p] = co * x - s * y; v[k][q] = s * x + co * y; }
  }
  return [0, 1, 2].map(j => [v[0][j], v[1][j], v[2][j]]);
}

/** O .usdz da maquete (o arquivo do AR Quick Look do iPhone). */
export async function usdz(grupo) {
  const { USDZExporter } = await import('./lib/USDZExporter.js');
  const cena = new THREE.Scene();
  cena.add(grupo);
  const dados = await new USDZExporter().parse(cena, { quickLookCompatible: true });
  cena.remove(grupo);
  return new Blob([dados], { type: 'model/vnd.usdz+zip' });
}

/** O link que abre o AR Quick Look: o iPhone exige um <a rel="ar"> com uma imagem dentro, tocado pela pessoa. */
export function linkQuickLook(blob, rotulo) {
  const a = document.createElement('a');
  a.rel = 'ar';
  a.href = URL.createObjectURL(blob);
  a.className = 'botao forte ra-abrir';
  const img = document.createElement('img');          // a imagem é o que o Safari procura; fica invisível
  img.alt = ''; img.width = 1; img.height = 1;
  img.src = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
  a.append(img, document.createTextNode(rotulo));
  return a;
}

/** A realidade aumentada do Android (WebXR): aponta para a mesa, toca para pôr; dois dedos aumentam e giram; os botões
 *  de baixo fazem o mesmo, e Sair volta ao 3D. `situacoes` = [{rotulo, grupo}] (a cobertura retrátil aberta e
 *  retraída, no mesmo quadro: o botão troca uma pela outra na mesa); `piso` = o desenho do piso (pisoDaMaquete) ou null;
 *  `camadas` = {camadas, sistemas, partes, desligadas} para o botão Camadas (usuário, 20/10: "habilitar os eixos e
 *  níveis, por exemplo"); `escala` é o 1:N da maquete, para o rótulo acompanhar o tamanho. */
export async function abrirWebXR({ situacoes, piso = null, camadas = null, escala, aoSair }) {
  const sobre = document.createElement('div');
  sobre.id = 'ra-sobre';
  sobre.innerHTML = `<div class="ra-dica">Aponte para a mesa ou o chão e toque para pôr a maquete</div>
    <div class="ra-painel" hidden></div>
    <div class="ra-barra ra-barra-cima">${camadas ? '<button data-ra="camadas">Camadas</button>' : ''}${situacoes.length > 1
      ? `<button data-ra="situacao">${situacoes[0].rotulo}</button>` : ''}</div>
    <div class="ra-barra"><button data-ra="menor" aria-label="Menor">−</button><span class="ra-escala"></span>
      <button data-ra="maior" aria-label="Maior">+</button><button data-ra="girar">Girar</button><button data-ra="sair">Sair</button></div>`;
  document.body.appendChild(sobre);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.xr.enabled = true;
  const cena = new THREE.Scene(), camera = new THREE.PerspectiveCamera(60, 1, 0.01, 50);
  // a luz de uma sala clara em volta (o reflexo do aço) mais o sol: só com as duas luzes diretas a maquete saía escura
  const { RoomEnvironment } = await import('./lib/RoomEnvironment.js');
  const pmrem = new THREE.PMREMGenerator(renderer), ambiente = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;
  pmrem.dispose();
  cena.environment = ambiente;
  cena.add(new THREE.HemisphereLight(0xffffff, 0x77736b, 0.9));
  const sol = new THREE.DirectionalLight(0xffffff, 1.4);
  sol.position.set(1, 2, 0.8);
  cena.add(sol);
  const maquete = new THREE.Group();
  situacoes.forEach((s, k) => { s.grupo.visible = k === 0; maquete.add(s.grupo); });
  if (piso) maquete.add(piso);
  maquete.visible = false;
  cena.add(maquete);
  const desligadas = new Set(camadas ? camadas.desligadas : []);
  const aplicar = () => aplicarVisiveis(maquete, desligadas);
  aplicar();
  const mira = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.065, 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  mira.matrixAutoUpdate = false;
  mira.visible = false;
  cena.add(mira);
  const dica = sobre.querySelector('.ra-dica'), rotEscala = sobre.querySelector('.ra-escala'), painel = sobre.querySelector('.ra-painel');
  let tamanho = 1, atual = 0;
  const mostrarEscala = () => { rotEscala.textContent = '1:' + Math.round(escala / tamanho); };
  mostrarEscala();
  // tocar num botão ou no painel não muda a maquete de lugar
  for (const el of sobre.querySelectorAll('.ra-barra, .ra-painel')) el.addEventListener('beforexrselect', e => e.preventDefault());
  let sessao = null;
  const fechar = () => { if (sessao) sessao.end().catch(() => {}); };
  const linha = (chave, nome, cor, ligada) => `<label class="ra-linha"><input type="checkbox" data-chave="${_esc(chave)}" ${ligada ? 'checked' : ''}>
    ${cor ? `<i style="background:${_esc(cor)}"></i>` : ''}<span>${_esc(nome)}</span></label>`;
  const abrirPainel = () => {
    const secoes = [];
    if (camadas.partes.length) secoes.push('<div class="ra-titulo">No piso</div>' + camadas.partes.map(([k, nome, cor]) =>
      linha('piso:' + k, nome, cor, !desligadas.has('piso:' + k))).join(''));
    if (camadas.sistemas.length > 1) secoes.push('<div class="ra-titulo">Sistema</div>' + camadas.sistemas.map(s =>
      linha('sistema:' + s.chave, s.nome, s.cor, !desligadas.has('sistema:' + s.chave))).join(''));
    secoes.push('<div class="ra-titulo">Camadas</div>' + camadas.camadas.map(c => linha('camada:' + c.nome, c.nome, null, !desligadas.has('camada:' + c.nome))).join(''));
    painel.innerHTML = secoes.join('') + '<button data-ra="fechar-painel">Pronto</button>';
    painel.hidden = false;
    painel.querySelectorAll('input[data-chave]').forEach(c => c.onchange = () => {
      if (c.checked) desligadas.delete(c.dataset.chave); else desligadas.add(c.dataset.chave);
      aplicar();
    });
  };
  sobre.addEventListener('click', (e) => {
    const k = e.target.dataset && e.target.dataset.ra;
    if (k === 'maior' || k === 'menor') { tamanho *= k === 'maior' ? 1.25 : 0.8; maquete.scale.setScalar(tamanho); mostrarEscala(); }
    else if (k === 'girar') maquete.rotation.y += Math.PI / 12;
    else if (k === 'sair') fechar();
    else if (k === 'camadas') { if (painel.hidden) abrirPainel(); else painel.hidden = true; }
    else if (k === 'fechar-painel') painel.hidden = true;
    else if (k === 'situacao') {
      atual = (atual + 1) % situacoes.length;
      situacoes.forEach((s, j) => { s.grupo.visible = j === atual; });
      aplicar();
      e.target.textContent = situacoes[atual].rotulo;
    }
  });
  // dois dedos: abrir e fechar muda o tamanho, girar gira; o toque que fez parte do gesto não muda a maquete de lugar
  let gesto = null, pinca = false;
  const medida = (t) => [Math.hypot(t[1].clientX - t[0].clientX, t[1].clientY - t[0].clientY),
                         Math.atan2(t[1].clientY - t[0].clientY, t[1].clientX - t[0].clientX)];
  sobre.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) { const [d, a] = medida(e.touches); gesto = { d, a, tam: tamanho, rot: maquete.rotation.y }; pinca = true; }
  });
  sobre.addEventListener('touchmove', (e) => {
    if (!gesto || e.touches.length !== 2) return;
    const [d, a] = medida(e.touches);
    tamanho = Math.min(20, Math.max(0.1, gesto.tam * d / gesto.d));
    maquete.scale.setScalar(tamanho);
    maquete.rotation.y = gesto.rot - (a - gesto.a);
    mostrarEscala();
  });
  sobre.addEventListener('touchend', (e) => { if (e.touches.length < 2) gesto = null; if (!e.touches.length) setTimeout(() => { pinca = false; }, 350); });

  const limpar = () => {
    for (const s of situacoes) maquete.remove(s.grupo);
    if (piso) maquete.remove(piso);
    ambiente.dispose();
    renderer.dispose();
    sobre.remove();
  };
  let fonteMira;
  try {
    sessao = await navigator.xr.requestSession('immersive-ar', { requiredFeatures: ['hit-test'], optionalFeatures: ['dom-overlay'], domOverlay: { root: sobre } });
    renderer.xr.setReferenceSpaceType('local');
    await renderer.xr.setSession(sessao);
    fonteMira = await sessao.requestHitTestSource({ space: await sessao.requestReferenceSpace('viewer') });
  } catch (e) {                     // a câmera não abriu (recusada, sem ARCore…): nada fica por cima da tela
    if (sessao) sessao.end().catch(() => {});
    limpar();
    throw e;
  }
  sessao.addEventListener('select', () => {
    if (pinca || !mira.visible || !painel.hidden) return;
    maquete.position.setFromMatrixPosition(mira.matrix);
    maquete.visible = true;
    dica.textContent = 'Dois dedos: aumentar e girar · toque em outro ponto para mudar de lugar';
  });
  renderer.setAnimationLoop((t, quadro) => {
    if (quadro) {
      const achou = quadro.getHitTestResults(fonteMira);
      mira.visible = achou.length > 0;
      if (mira.visible) mira.matrix.fromArray(achou[0].getPose(renderer.xr.getReferenceSpace()).transform.matrix);
    }
    renderer.render(cena, camera);
  });
  sessao.addEventListener('end', () => {
    renderer.setAnimationLoop(null);
    fonteMira.cancel();
    limpar();
    if (aoSair) aoSair();
  });
}

const _esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** Solta a memória da maquete. */
export function descartar(grupo) {
  grupo.traverse(o => { if (o.geometry) { o.geometry.dispose(); o.material.dispose(); } });     // as malhas e as arestas
}
