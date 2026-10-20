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
const MAX_TRIANGULOS = 150000;     // o que o Quick Look e o celular abrem sem engasgar (o .usdz em ~20 MB); acima, simplifica

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

/** A maquete do 3D aberto: `ids` (as peças) ou, sem eles, o que está à vista. Devolve o grupo do three.js em metros,
 *  com o Y para cima, centrado e apoiado no chão (o que a realidade aumentada espera), e os números dela. */
export async function montarMaquete(v, buf, ids, aoAndar, maxTriangulos = MAX_TRIANGULOS) {
  const dv = new DataView(buf);
  const cab = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 12, dv.getUint32(8, true))));
  const fichas = v.fichas || [], nP = v.nPecas, obra = !ids;
  const quer = new Uint8Array(nP);
  if (ids) for (const i of ids) quer[i] = 1;
  else for (let i = 0; i < nP; i++) {
    if (v.visivelCamada[v.camadaDe[i]] !== false && !v.ocultas.has(i) && !v.ocultasSistema.has(i)) quer[i] = 1;
  }
  // na obra inteira, as peças pequenas ficam de fora; e, passando do limite, as menores até caber
  const tam = (i) => { const b = (fichas[i] || {}).b; return b ? Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) : Infinity; };
  let deFora = 0;
  if (obra) for (let i = 0; i < nP; i++) if (quer[i] && tam(i) < MIN_PECA_OBRA) { quer[i] = 0; deFora++; }
  const tris = new Uint32Array(nP);
  const idxDe = (d) => new (d.tipo === 'u32' ? Uint32Array : Uint16Array)(buf, d.ofs, d.n);
  for (const b of cab.blocos) {
    const vs = new Uint16Array(buf, b.vertices.ofs, b.vertices.n * 4), ix = idxDe(b.indices);
    for (let t = 0; t < ix.length; t += 3) tris[b.id0 + vs[ix[t] * 4 + 3]]++;
  }
  for (const f of cab.formas) {
    const inst = new Float32Array(buf, f.copias.ofs, f.copias.n * 13), nt = f.indices.n / 3;
    for (let k = 0; k < f.copias.n; k++) tris[inst[k * 13 + 12]] += nt;
  }
  // passando do limite, as peças mais pesadas viram a forma de fora delas (a caixa justa, na direção da peça): a laje
  // alveolar do Mercado são 1.500 triângulos de alvéolos que a maquete não mostra — 590 mil dos 853 mil da obra. Só se
  // ainda não couber saem as menores.
  let total = 0, simplificadas = 0;
  const caixa = new Uint8Array(nP);
  const ordem = [];
  for (let i = 0; i < nP; i++) if (quer[i]) { total += tris[i]; ordem.push(i); }
  if (total > maxTriangulos) {
    ordem.sort((a, b) => tris[b] - tris[a]);
    for (const i of ordem) {
      if (total <= maxTriangulos || tris[i] <= 12) break;
      caixa[i] = 1; total -= tris[i] - 12; simplificadas++;
    }
    if (total > maxTriangulos) {
      ordem.sort((a, b) => tam(b) - tam(a));
      total = 0;
      for (const i of ordem) { const t = caixa[i] ? 12 : tris[i]; if (total + t <= maxTriangulos) total += t; else { quer[i] = 0; deFora++; } }
    }
  }
  const pontosCaixa = new Map();                                       // peça simplificada → os pontos dela (x, y, z…)
  const juntar = (id, pts) => {
    let l = pontosCaixa.get(id);
    if (!l) pontosCaixa.set(id, (l = []));
    for (const p of pts) l.push(p[0], p[1], p[2]);
  };

  // as malhas, uma por cor (a da tela, sem o clareamento do tema): o vértice se repete só onde a face dobra,
  // para o aço sair com as quinas vivas
  const grupos = new Map(), cb = v.corBase;
  const grupo = (i) => {
    const c = (cb[i * 3] << 16) | (cb[i * 3 + 1] << 8) | cb[i * 3 + 2];
    let g = grupos.get(c);
    if (!g) grupos.set(c, (g = { cor: c, pos: [], nor: [], idx: [] }));
    return g;
  };
  const pecas = new Set();
  const P = [new Float64Array(3), new Float64Array(3), new Float64Array(3)];
  const triangulo = (mapa, g, chaves, pts) => {
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
  };
  let feitos = 0;
  const passo = async () => { if (++feitos % 8 === 0) { if (aoAndar) aoAndar(feitos / (cab.blocos.length + cab.formas.length)); await new Promise(r => setTimeout(r)); } };
  for (const b of cab.blocos) {
    const vs = new Uint16Array(buf, b.vertices.ofs, b.vertices.n * 4), ix = idxDe(b.indices), mapa = new Map(), ch = [0, 0, 0];
    for (let t = 0; t < ix.length; t += 3) {
      const id = b.id0 + vs[ix[t] * 4 + 3];
      if (!quer[id]) continue;
      for (let k = 0; k < 3; k++) {
        const q = ix[t + k] * 4;
        ch[k] = ix[t + k];
        P[k][0] = b.min[0] + vs[q] * b.esc[0]; P[k][1] = b.min[1] + vs[q + 1] * b.esc[1]; P[k][2] = b.min[2] + vs[q + 2] * b.esc[2];
      }
      if (caixa[id]) juntar(id, P); else triangulo(mapa, grupo(id), ch, P);
      pecas.add(id);
    }
    await passo();
  }
  for (const f of cab.formas) {
    const vs = new Uint16Array(buf, f.vertices.ofs, f.vertices.n * 4), ix = idxDe(f.indices);
    const inst = new Float32Array(buf, f.copias.ofs, f.copias.n * 13), ch = [0, 0, 0];
    for (let c = 0; c < f.copias.n; c++) {
      const m = c * 13, id = inst[m + 12];
      if (!quer[id]) continue;
      const g = grupo(id), mapa = new Map();
      for (let t = 0; t < ix.length; t += 3) {
        for (let k = 0; k < 3; k++) {
          const q = ix[t + k] * 4, x = vs[q], y = vs[q + 1], z = vs[q + 2];
          ch[k] = ix[t + k];
          for (let r = 0; r < 3; r++) P[k][r] = inst[m + r * 4] * x + inst[m + r * 4 + 1] * y + inst[m + r * 4 + 2] * z + inst[m + r * 4 + 3];
        }
        if (caixa[id]) juntar(id, P); else triangulo(mapa, g, ch, P);
      }
      pecas.add(id);
    }
    await passo();
  }
  for (const [id, l] of pontosCaixa) caixaJusta(l, grupo(id), triangulo);

  // em metros, o Y para cima, no centro e no chão, no tamanho da mesa
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const g of grupos.values()) for (let k = 0; k < g.pos.length; k += 3) for (let r = 0; r < 3; r++) {
    const x = g.pos[k + r]; if (x < min[r]) min[r] = x; if (x > max[r]) max[r] = x;
  }
  if (!pecas.size) return { grupo: new THREE.Group(), pecas: 0, triangulos: 0, deFora, simplificadas, escala: 1, medidas: [0, 0, 0] };
  const cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, lado = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  const s = LADO_MESA / lado;                                            // de mm para os metros da mesa
  const raiz = new THREE.Group();
  raiz.name = 'Maquete';
  let triangulos = 0;
  for (const g of grupos.values()) {
    const n = g.pos.length / 3, pos = new Float32Array(n * 3), nor = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) {
      pos[k * 3] = (g.pos[k * 3] - cx) * s; pos[k * 3 + 1] = (g.pos[k * 3 + 2] - min[2]) * s; pos[k * 3 + 2] = -(g.pos[k * 3 + 1] - cy) * s;
      nor[k * 3] = g.nor[k * 3]; nor[k * 3 + 1] = g.nor[k * 3 + 2]; nor[k * 3 + 2] = -g.nor[k * 3 + 1];
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(g.idx), 1));
    const cor = new THREE.Color().setRGB(((g.cor >> 16) & 255) / 255, ((g.cor >> 8) & 255) / 255, (g.cor & 255) / 255, THREE.SRGBColorSpace);
    const malha = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: cor, roughness: 0.7, metalness: 0.1, side: THREE.DoubleSide }));
    malha.name = 'Cor_' + g.cor.toString(16).padStart(6, '0');
    raiz.add(malha);
    triangulos += g.idx.length / 3;
  }
  return { grupo: raiz, pecas: pecas.size, triangulos, deFora, simplificadas, escala: Math.round(1 / (s * 1000)),
           medidas: [(max[0] - min[0]) / 1000, (max[1] - min[1]) / 1000, (max[2] - min[2]) / 1000] };
}

/** A caixa justa dos pontos `l` (x, y, z…): o menor retângulo em planta que os envolve (pelas arestas do contorno
 *  convexo) e a altura deles — a laje, a parede ou o bloco girados na planta saem girados. Vira 12 triângulos. */
function caixaJusta(l, g, triangulo) {
  const n = l.length / 3;
  let z0 = Infinity, z1 = -Infinity;
  const pts = [];
  for (let k = 0; k < n; k++) { pts.push([l[k * 3], l[k * 3 + 1]]); z0 = Math.min(z0, l[k * 3 + 2]); z1 = Math.max(z1, l[k * 3 + 2]); }
  pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const giro = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const baixo = [], cima = [];
  for (const p of pts) { while (baixo.length >= 2 && giro(baixo[baixo.length - 2], baixo[baixo.length - 1], p) <= 0) baixo.pop(); baixo.push(p); }
  for (let k = pts.length - 1; k >= 0; k--) { const p = pts[k]; while (cima.length >= 2 && giro(cima[cima.length - 2], cima[cima.length - 1], p) <= 0) cima.pop(); cima.push(p); }
  const casco = baixo.slice(0, -1).concat(cima.slice(0, -1));
  let melhor = null;
  for (let k = 0; k < Math.max(1, casco.length); k++) {
    const a = casco[k] || pts[0], b = casco[(k + 1) % casco.length] || pts[0];
    let ux = b[0] - a[0], uy = b[1] - a[1];
    const lu = Math.hypot(ux, uy);
    if (lu < 1e-9) { ux = 1; uy = 0; } else { ux /= lu; uy /= lu; }
    let s0 = Infinity, s1 = -Infinity, t0 = Infinity, t1 = -Infinity;
    for (const p of casco.length ? casco : pts) {
      const s = p[0] * ux + p[1] * uy, t = -p[0] * uy + p[1] * ux;
      s0 = Math.min(s0, s); s1 = Math.max(s1, s); t0 = Math.min(t0, t); t1 = Math.max(t1, t);
    }
    const area = (s1 - s0) * (t1 - t0);
    if (!melhor || area < melhor.area) melhor = { area, ux, uy, s0, s1, t0, t1 };
  }
  const { ux, uy, s0, s1, t0, t1 } = melhor;
  const canto = (s, t, z) => [s * ux - t * uy, s * uy + t * ux, z];
  const c = [canto(s0, t0, z0), canto(s1, t0, z0), canto(s1, t1, z0), canto(s0, t1, z0),
             canto(s0, t0, z1), canto(s1, t0, z1), canto(s1, t1, z1), canto(s0, t1, z1)];
  const mapa = new Map();
  for (const [a, b, cc, d] of [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]) {
    triangulo(mapa, g, [a, b, cc], [c[a], c[b], c[cc]]);
    triangulo(mapa, g, [a, cc, d], [c[a], c[cc], c[d]]);
  }
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
 *  de baixo fazem o mesmo, e Sair volta ao 3D. `escala` é o 1:N da maquete, para o rótulo acompanhar o tamanho. */
export async function abrirWebXR(grupo, escala, aoSair) {
  const sobre = document.createElement('div');
  sobre.id = 'ra-sobre';
  sobre.innerHTML = `<div class="ra-dica">Aponte para a mesa ou o chão e toque para pôr a maquete</div>
    <div class="ra-barra"><button data-ra="menor" aria-label="Menor">−</button><span class="ra-escala"></span>
      <button data-ra="maior" aria-label="Maior">+</button><button data-ra="girar">Girar</button><button data-ra="sair">Sair</button></div>`;
  document.body.appendChild(sobre);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.xr.enabled = true;
  const cena = new THREE.Scene(), camera = new THREE.PerspectiveCamera(60, 1, 0.01, 50);
  cena.add(new THREE.HemisphereLight(0xffffff, 0x77736b, 2.0));
  const sol = new THREE.DirectionalLight(0xffffff, 1.8);
  sol.position.set(1, 2, 0.8);
  cena.add(sol);
  const maquete = new THREE.Group();
  maquete.add(grupo);
  maquete.visible = false;
  cena.add(maquete);
  const mira = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.065, 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  mira.matrixAutoUpdate = false;
  mira.visible = false;
  cena.add(mira);
  const dica = sobre.querySelector('.ra-dica'), rotEscala = sobre.querySelector('.ra-escala');
  let tamanho = 1;
  const mostrarEscala = () => { rotEscala.textContent = '1:' + Math.round(escala / tamanho); };
  mostrarEscala();
  const barra = sobre.querySelector('.ra-barra');
  barra.addEventListener('beforexrselect', e => e.preventDefault());   // tocar num botão não muda a maquete de lugar
  let sessao = null;
  const fechar = () => { if (sessao) sessao.end().catch(() => {}); };
  barra.onclick = (e) => {
    const k = e.target.dataset && e.target.dataset.ra;
    if (k === 'maior' || k === 'menor') { tamanho *= k === 'maior' ? 1.25 : 0.8; maquete.scale.setScalar(tamanho); mostrarEscala(); }
    else if (k === 'girar') maquete.rotation.y += Math.PI / 12;
    else if (k === 'sair') fechar();
  };
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

  let fonteMira;
  try {
    sessao = await navigator.xr.requestSession('immersive-ar', { requiredFeatures: ['hit-test'], optionalFeatures: ['dom-overlay'], domOverlay: { root: sobre } });
    renderer.xr.setReferenceSpaceType('local');
    await renderer.xr.setSession(sessao);
    fonteMira = await sessao.requestHitTestSource({ space: await sessao.requestReferenceSpace('viewer') });
  } catch (e) {                     // a câmera não abriu (recusada, sem ARCore…): nada fica por cima da tela
    if (sessao) sessao.end().catch(() => {});
    maquete.remove(grupo);
    renderer.dispose();
    sobre.remove();
    throw e;
  }
  sessao.addEventListener('select', () => {
    if (pinca || !mira.visible) return;
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
    maquete.remove(grupo);
    renderer.dispose();
    sobre.remove();
    if (aoSair) aoSair();
  });
}

/** Solta a memória da maquete. */
export function descartar(grupo) {
  grupo.traverse(o => { if (o.isMesh) { o.geometry.dispose(); o.material.dispose(); } });
}
