// As figuras da cena do 3D (12/11, FERRAMENTA · CENAS): pessoas, carros, caminhão e árvores postos no chão para dar escala e
// vida à imagem — "um galpão sem gente nem carro não diz o tamanho que tem". Feitas de formas simples (sem arquivo de fora),
// em mm, com o pé no ponto (z para cima, a frente para +x), iluminadas como as peças (visor.materialIluminado) e no grupo
// `visor.extras`, que faz sombra no sol. Dois estilos: 'cor' (roupas, carros e copas coloridas) e 'neutro' (maquete branca).
import * as THREE from 'three';

export const TIPOS_FIGURA = {
  pessoa:     { nome: 'Pessoa',      grupo: 'gente' },
  operario:   { nome: 'Operário',    grupo: 'gente' },
  carro:      { nome: 'Carro',       grupo: 'veiculo' },
  caminhonete:{ nome: 'Caminhonete', grupo: 'veiculo' },
  caminhao:   { nome: 'Caminhão',    grupo: 'veiculo' },
  arvore:     { nome: 'Árvore',      grupo: 'verde' },
  araucaria:  { nome: 'Araucária',   grupo: 'verde' },
  arbusto:    { nome: 'Arbusto',     grupo: 'verde' },
};

const ROUPAS = ['#2f5d8a', '#b8433a', '#e2e0d8', '#3f6b45', '#d39b2a', '#5b4a7a', '#2b2f36', '#8a8f96'];
const CALCAS = ['#2a3445', '#3b3b3b', '#5a5248', '#1f2a38'];
const PELES = ['#e0b896', '#c08a63', '#8d5a3b', '#f0cba8'];
const CARROS = ['#d9dcdf', '#2b2e33', '#8e959c', '#7a1f22', '#1f3d66', '#f2f2f0'];
const VERDES = ['#4f7a33', '#5e8a3a', '#3f6a2c', '#6b8f3e'];
const NEUTRO = { claro: '#ecebe7', medio: '#d6d4cf', escuro: '#b9b7b2', vidro: '#9aa3ab' };

/** Um gerador de sorteio fixo (a mesma figura sai sempre igual). */
function sorteio(semente) {
  let s = (Math.abs(Math.floor(semente)) % 2147483646) + 1;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}
const escolher = (r, lista) => lista[Math.floor(r() * lista.length) % lista.length];

/** O desenhador das figuras de um visor: os materiais guardados por cor (um por cor, iluminados como as peças). */
export class Figuras {
  constructor(visor) {
    this.visor = visor;
    this.materiais = new Map();
    this.grupo = null;
  }

  mat(cor) {
    if (!this.materiais.has(cor)) this.materiais.set(cor, this.visor.materialIluminado(cor));
    return this.materiais.get(cor);
  }

  /** Tira as figuras desenhadas. */
  limpar() {
    if (!this.grupo) return;
    this.visor.extras.remove(this.grupo);
    this.grupo.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    this.grupo = null;
  }

  /** Desenha a lista: [{tipo, p: [x,y,z] no mundo (mm), giro: graus, semente}], no estilo 'cor' ou 'neutro'. */
  desenhar(lista, estilo = 'cor') {
    this.limpar();
    if (!lista || !lista.length) { this.visor.pedirQuadro(); return; }
    const g = this.grupo = new THREE.Group();
    for (const f of lista) {
      const fig = this.figura(f.tipo, estilo, f.semente ?? 1);
      if (!fig) continue;
      fig.position.set(f.p[0], f.p[1], f.p[2] || 0);
      fig.rotation.z = (+f.giro || 0) * Math.PI / 180;
      g.add(fig);
    }
    this.visor.extras.add(g);
    this.visor._sombraSuja = true;
    this.visor.pedirQuadro();
  }

  figura(tipo, estilo, semente) {
    const r = sorteio(semente * 7919 + 13), n = estilo === 'neutro';
    if (tipo === 'pessoa' || tipo === 'operario') return this.pessoa(r, n, tipo === 'operario');
    if (tipo === 'carro') return this.carro(r, n);
    if (tipo === 'caminhonete') return this.caminhonete(r, n);
    if (tipo === 'caminhao') return this.caminhao(r, n);
    if (tipo === 'arvore') return this.arvore(r, n);
    if (tipo === 'araucaria') return this.araucaria(r, n);
    if (tipo === 'arbusto') return this.arbusto(r, n);
    return null;
  }

  // ------------------------------------------------------------------ gente

  /** Uma pessoa de ~1,60–1,85 m, andando ou parada; o operário de capacete e colete. */
  pessoa(r, neutro, operario) {
    const g = new THREE.Group(), h = 1600 + r() * 250, k = h / 1750;
    const pele = neutro ? NEUTRO.claro : escolher(r, PELES);
    const camisa = neutro ? NEUTRO.claro : operario ? '#e8742a' : escolher(r, ROUPAS);
    const calca = neutro ? NEUTRO.medio : operario ? '#2a3445' : escolher(r, CALCAS);
    const passo = r() < 0.6 ? (0.25 + r() * 0.15) : 0.03;          // andando ou parada
    const capsula = (raio, comp, cor) => new THREE.Mesh(new THREE.CapsuleGeometry(raio, comp, 4, 10), this.mat(cor));
    for (const lado of [-1, 1]) {                                     // as pernas: o giro no quadril
      const perna = new THREE.Group(), p = capsula(68, 760, calca);
      p.rotation.x = Math.PI / 2; p.position.z = -440;
      perna.add(p); perna.position.set(0, lado * 95, 900); perna.rotation.y = lado * passo;
      g.add(perna);
      const braco = new THREE.Group(), b = capsula(44, 560, camisa);
      b.rotation.x = Math.PI / 2; b.position.z = -310;
      braco.add(b); braco.position.set(0, lado * 235, 1420); braco.rotation.y = -lado * passo * 0.9; braco.rotation.x = lado * 0.06;
      g.add(braco);
      const mao = new THREE.Mesh(new THREE.SphereGeometry(48, 10, 8), this.mat(pele));
      mao.position.set(0, 0, -640); braco.add(mao);
    }
    const tronco = capsula(165, 380, camisa);                         // o tronco, achatado de frente para trás
    tronco.rotation.x = Math.PI / 2; tronco.scale.set(0.62, 1, 1.05); tronco.position.z = 1190;
    g.add(tronco);
    const pescoco = new THREE.Mesh(new THREE.CylinderGeometry(48, 52, 90, 10), this.mat(pele));
    pescoco.rotation.x = Math.PI / 2; pescoco.position.z = 1500; g.add(pescoco);
    const cabeca = new THREE.Mesh(new THREE.SphereGeometry(102, 16, 12), this.mat(pele));
    cabeca.scale.set(1, 0.88, 1.15); cabeca.position.z = 1630; g.add(cabeca);
    if (operario) {
      const capacete = new THREE.Mesh(new THREE.SphereGeometry(118, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), this.mat(neutro ? NEUTRO.claro : '#f2f2ee'));
      capacete.rotation.x = Math.PI / 2; capacete.position.z = 1665; g.add(capacete);
      const aba = new THREE.Mesh(new THREE.CylinderGeometry(150, 150, 14, 16), this.mat(neutro ? NEUTRO.claro : '#f2f2ee'));
      aba.rotation.x = Math.PI / 2; aba.position.set(25, 0, 1665); g.add(aba);
      if (!neutro) {                                                  // a faixa refletiva do colete
        const faixa = new THREE.Mesh(new THREE.CylinderGeometry(172, 172, 45, 16), this.mat('#d9dcd2'));
        faixa.rotation.x = Math.PI / 2; faixa.scale.set(0.64, 1, 1); faixa.position.z = 1120; g.add(faixa);
      }
    } else if (!neutro) {                                             // o cabelo
      const cabelo = new THREE.Mesh(new THREE.SphereGeometry(106, 16, 8, 0, Math.PI * 2, 0, Math.PI * 0.55),
                                    this.mat(escolher(r, ['#2a1f18', '#4a3424', '#1c1c1c', '#7a5a3a', '#b8b0a4'])));
      cabelo.rotation.x = Math.PI / 2; cabelo.scale.set(1.02, 0.9, 1.1); cabelo.position.set(-8, 0, 1648); g.add(cabelo);
    }
    g.scale.setScalar(k);
    return g;
  }

  // ------------------------------------------------------------------ veículos

  /** Um perfil (x, z em mm) puxado na largura, centrado em y, com a borda arredondada. */
  perfil(pontos, largura, cor, chanfro = 60) {
    const s = new THREE.Shape(pontos.map(([x, z]) => new THREE.Vector2(x, z)));
    const geo = new THREE.ExtrudeGeometry(s, { depth: largura - 2 * chanfro, bevelEnabled: true, bevelThickness: chanfro,
                                              bevelSize: chanfro, bevelSegments: 2, curveSegments: 6 });
    geo.translate(0, 0, -(largura - 2 * chanfro) / 2);
    geo.rotateX(Math.PI / 2);                                         // o perfil em pé (x, z), a largura em y
    return new THREE.Mesh(geo, this.mat(cor));
  }

  rodas(g, xs, y, raio, larg, neutro) {
    const pneu = this.mat(neutro ? NEUTRO.escuro : '#1d1f22'), aro = this.mat(neutro ? NEUTRO.medio : '#9ea4aa');
    for (const x of xs) for (const s of [-1, 1]) {
      const p = new THREE.Mesh(new THREE.CylinderGeometry(raio, raio, larg, 18), pneu);
      p.position.set(x, s * y, raio); g.add(p);
      const a = new THREE.Mesh(new THREE.CylinderGeometry(raio * 0.55, raio * 0.55, larg + 10, 14), aro);
      a.position.set(x, s * y, raio); g.add(a);
    }
  }

  carro(r, neutro) {
    const g = new THREE.Group(), cor = neutro ? NEUTRO.claro : escolher(r, CARROS), vidro = neutro ? NEUTRO.vidro : '#2c3540';
    g.add(this.perfil([[-2250, 250], [2230, 250], [2280, 560], [2150, 760], [1150, 840], [-1700, 870], [-2260, 820], [-2290, 450]], 1760, cor, 70));
    g.add(this.perfil([[1120, 820], [380, 1340], [-880, 1360], [-1660, 860]], 1560, vidro, 50));
    this.rodas(g, [1420, -1420], 760, 330, 230, neutro);
    return g;
  }

  caminhonete(r, neutro) {
    const g = new THREE.Group(), cor = neutro ? NEUTRO.claro : escolher(r, ['#f2f2f0', '#8e959c', '#2b2e33', '#7a1f22']), vidro = neutro ? NEUTRO.vidro : '#2c3540';
    g.add(this.perfil([[-2650, 380], [2600, 380], [2660, 720], [2500, 1000], [1500, 1060], [-2660, 1060]], 1880, cor, 70));
    g.add(this.perfil([[1450, 1040], [800, 1640], [-700, 1660], [-850, 1040]], 1700, vidro, 50));
    g.add(this.perfil([[-700, 1040], [-640, 1660], [-860, 1660], [-860, 1040]], 1820, cor, 40));   // a coluna de trás da cabine
    this.rodas(g, [1650, -1750], 820, 390, 270, neutro);
    return g;
  }

  caminhao(r, neutro) {
    const g = new THREE.Group(), cab = neutro ? NEUTRO.claro : escolher(r, ['#f2f2f0', '#b8433a', '#1f3d66']),
          bau = neutro ? NEUTRO.medio : '#e4e4e0', vidro = neutro ? NEUTRO.vidro : '#2c3540';
    g.add(this.perfil([[2300, 600], [4050, 600], [4100, 1400], [3950, 2900], [2300, 2950]], 2450, cab, 80));
    g.add(this.perfil([[3700, 1850], [3920, 1850], [3820, 2700], [3600, 2700]], 2300, vidro, 20));
    const caixa = new THREE.Mesh(new THREE.BoxGeometry(7000, 2550, 2800), this.mat(bau));
    caixa.position.set(-1350, 0, 1000 + 1400); g.add(caixa);
    const chassi = new THREE.Mesh(new THREE.BoxGeometry(8800, 1000, 300), this.mat(neutro ? NEUTRO.escuro : '#2b2e33'));
    chassi.position.set(-300, 0, 750); g.add(chassi);
    this.rodas(g, [3150, -2900, -4000], 1050, 500, 320, neutro);
    return g;
  }

  // ------------------------------------------------------------------ verde

  /** A árvore de copa redonda: tronco e uma copa de 4–6 bolas facetadas, de 5 a 9 m. */
  arvore(r, neutro) {
    const g = new THREE.Group(), h = 5000 + r() * 4000, copa = h * (0.32 + r() * 0.08);
    const tronco = new THREE.Mesh(new THREE.CylinderGeometry(h * 0.018, h * 0.03, h * 0.55, 8), this.mat(neutro ? NEUTRO.medio : '#5a4632'));
    tronco.rotation.x = Math.PI / 2; tronco.position.z = h * 0.275; g.add(tronco);
    const n = 4 + Math.floor(r() * 3);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + r(), d = i === 0 ? 0 : copa * (0.35 + 0.25 * r()), rr = copa * (i === 0 ? 0.75 : 0.5 + 0.2 * r());
      const b = new THREE.Mesh(new THREE.IcosahedronGeometry(rr, 1), this.mat(neutro ? NEUTRO.claro : escolher(r, VERDES)));
      b.position.set(Math.cos(a) * d, Math.sin(a) * d, h - copa * 0.85 + (i === 0 ? 0 : (r() - 0.3) * copa * 0.5));
      b.scale.set(1, 1, 0.82); g.add(b);
    }
    return g;
  }

  /** A araucária (a árvore do Paraná): o tronco reto alto e a copa em taça, achatada em cima, de 12 a 18 m. */
  araucaria(r, neutro) {
    const g = new THREE.Group(), h = 12000 + r() * 6000;
    const tronco = new THREE.Mesh(new THREE.CylinderGeometry(150, 260, h, 8), this.mat(neutro ? NEUTRO.medio : '#5c4a3a'));
    tronco.rotation.x = Math.PI / 2; tronco.position.z = h / 2; g.add(tronco);
    const verde = this.mat(neutro ? NEUTRO.claro : '#33572a'), ramo = this.mat(neutro ? NEUTRO.medio : '#5c4a3a');
    const nRamos = 7 + Math.floor(r() * 3), raio = h * 0.3;
    for (let i = 0; i < nRamos; i++) {                               // os galhos subindo em taça, com o tufo na ponta
      const a = (i / nRamos) * Math.PI * 2 + r() * 0.4, d = raio * (0.7 + 0.3 * r()), z0 = h * 0.82, z1 = h + r() * 400;
      const p0 = new THREE.Vector3(0, 0, z0), p1 = new THREE.Vector3(Math.cos(a) * d, Math.sin(a) * d, z1);
      const c = new THREE.Mesh(new THREE.CylinderGeometry(55, 80, p0.distanceTo(p1), 6), ramo);
      c.position.copy(p0).add(p1).multiplyScalar(0.5);
      c.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), p1.clone().sub(p0).normalize());
      g.add(c);
      const tufo = new THREE.Mesh(new THREE.IcosahedronGeometry(raio * 0.36, 1), verde);
      tufo.position.copy(p1); tufo.scale.set(1.15, 1.15, 0.42); g.add(tufo);
    }
    const topo = new THREE.Mesh(new THREE.IcosahedronGeometry(raio * 0.42, 1), verde);
    topo.position.set(0, 0, h + 300); topo.scale.set(1, 1, 0.4); g.add(topo);
    return g;
  }

  arbusto(r, neutro) {
    const g = new THREE.Group(), n = 3 + Math.floor(r() * 3), t = 600 + r() * 600;
    for (let i = 0; i < n; i++) {
      const a = r() * Math.PI * 2, d = i === 0 ? 0 : t * 0.6 * r();
      const b = new THREE.Mesh(new THREE.IcosahedronGeometry(t * (0.55 + 0.3 * r()), 1), this.mat(neutro ? NEUTRO.claro : escolher(r, VERDES)));
      b.position.set(Math.cos(a) * d, Math.sin(a) * d, t * 0.45); b.scale.set(1, 1, 0.75); g.add(b);
    }
    return g;
  }
}

/** As árvores do fundo (Entorno › Árvores no fundo): numa faixa a 20–70 m do prédio (fora da calçada e do pátio), espaçadas
 *  ~10 m com sorteio fixo, só do lado de trás e dos lados para quem olha da câmera da cena — nenhuma entre a câmera e o
 *  prédio. `caixa` [[x0,y0],[x1,y1]] e `patio` no mundo; `olho` [x,y] = a posição da câmera da cena; `quantas` 1–3. */
export function arvoresDoFundo(caixa, patio, olho, quantas = 2, chaoZ = 0) {
  const [[x0, y0], [x1, y1]] = caixa, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, r = sorteio(4242), out = [];
  const passo = [16000, 10000, 7000][Math.max(0, Math.min(2, (quantas | 0) - 1))];
  let vx = olho ? olho[0] - cx : 0, vy = olho ? olho[1] - cy : -1; const vn = Math.hypot(vx, vy) || 1; vx /= vn; vy /= vn;
  const dentro = (x, y, q, folga) => q && x > Math.min(q[0][0], q[1][0]) - folga && x < Math.max(q[0][0], q[1][0]) + folga &&
                                         y > Math.min(q[0][1], q[1][1]) - folga && y < Math.max(q[0][1], q[1][1]) + folga;
  for (let anel = 0; anel < 3; anel++) {
    const af = 20000 + anel * 22000;                                  // o afastamento do prédio
    const ax0 = x0 - af, ax1 = x1 + af, ay0 = y0 - af, ay1 = y1 + af, per = 2 * ((ax1 - ax0) + (ay1 - ay0));
    const n = Math.round(per / passo);
    for (let i = 0; i < n; i++) {
      let s = (i + r() * 0.6) / n * per, x, y;
      const L1 = ax1 - ax0, L2 = ay1 - ay0;
      if (s < L1) { x = ax0 + s; y = ay0; } else if ((s -= L1) < L2) { x = ax1; y = ay0 + s; }
      else if ((s -= L2) < L1) { x = ax1 - s; y = ay1; } else { s -= L1; x = ax0; y = ay1 - s; }
      x += (r() - 0.5) * 9000; y += (r() - 0.5) * 9000;
      const dx = x - cx, dy = y - cy, d = Math.hypot(dx, dy) || 1;
      if ((dx * vx + dy * vy) / d > -0.15) { r(); r(); continue; }   // do lado da câmera ou quase: fica de fora
      if (dentro(x, y, [[x0, y0], [x1, y1]], 12000) || dentro(x, y, patio, 4000)) { r(); r(); continue; }
      const t = r();
      out.push({ tipo: t < 0.1 ? 'araucaria' : t < 0.25 ? 'arbusto' : 'arvore', p: [x, y, chaoZ], giro: Math.round(r() * 360), semente: 100 + out.length });
    }
  }
  return out;
}
