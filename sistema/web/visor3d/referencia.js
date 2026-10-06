// O modo ver com a planta no chão (pedido do usuário, 06/10: "trazer a planta baixa para o piso do modelo de
// visualização… e mostrar também os níveis"): o arquitetônico da Planta de lançamento em cinza, os eixos do projeto
// tracejados com o balão do nome nas pontas e os níveis (o contorno na altura e a cabeça com o nome e a cota) — o
// mesmo que o editor desenha (editor3d/modulos/lancamento.js), aqui em mm, a unidade do visor. Só tela: não se
// seleciona nem entra no enquadramento.

import * as THREE from 'three';

const COR_ARQ = { claro: '#9aa3ae', escuro: '#5b6573' };
// os eixos em roxo: o vermelho é o da malha no 2D ao lado, e o 3D com a mesma cor se confundia com ele (06/10)
const TEMA = {
  claro: { linha: '#7c3aed', fundo: '#ffffff', traco: '#6d28d9', nivel: '#1f5fbf' },
  escuro: { linha: '#b197fc', fundo: '#1b2130', traco: '#c4b5fd', nivel: '#7fb0ff' },
};
const cor = (hex) => new THREE.Color().setStyle(hex, THREE.LinearSRGBColorSpace);   // a saída do visor é linear
const semToque = (o) => { o.raycast = () => {}; return o; };

function textura(c) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** O balão do eixo: a bolinha com o nome. */
function balao(nome, cores) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = cores.fundo; g.strokeStyle = cores.traco; g.lineWidth = 8;
  g.beginPath(); g.arc(64, 64, 56, 0, Math.PI * 2); g.fill(); g.stroke();
  g.fillStyle = cores.traco; g.font = `bold ${nome.length > 2 ? 44 : 60}px Arial, sans-serif`;
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(nome, 64, 68);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: textura(c), depthTest: false, transparent: true }));
  s.renderOrder = 10;
  return semToque(s);
}

/** A cabeça do nível, como a do Revit: o triângulo, o nome e a cota. */
function cabecaDoNivel(nome, z, cores) {
  const cota = (z >= 0 ? '+' : '−') + (Math.abs(z) / 1000).toFixed(2).replace('.', ',');
  const c = document.createElement('canvas');
  const g0 = c.getContext('2d');
  g0.font = 'bold 44px Arial, sans-serif';
  const w = Math.ceil(Math.max(g0.measureText(nome).width, g0.measureText(cota).width) + 110);
  c.width = w; c.height = 128;
  const g = c.getContext('2d');
  g.globalAlpha = 0.82; g.fillStyle = cores.fundo;
  g.fillRect(76, 6, w - 78, 54); g.fillRect(76, 66, w - 78, 50);
  g.globalAlpha = 1;
  g.fillStyle = cores.nivel; g.strokeStyle = cores.nivel; g.lineWidth = 5;
  g.beginPath(); g.moveTo(16, 60); g.lineTo(64, 60); g.lineTo(40, 100); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(0, 60); g.lineTo(w, 60); g.stroke();
  g.font = 'bold 44px Arial, sans-serif'; g.textBaseline = 'alphabetic'; g.fillText(nome, 84, 50);
  g.font = '40px Arial, sans-serif'; g.fillText(cota, 84, 104);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: textura(c), depthTest: false, transparent: true }));
  s.center.set(0.02, 60 / 128);
  s.renderOrder = 10;
  s.userData.proporcao = w / 128;
  return semToque(s);
}

/** O tamanho na tela fixo (`px` pixels), nunca maior que `max` mm no modelo; `aplicar(mm)` põe escala e posição. */
function naTela(s, px, max, aplicar) {
  const p = new THREE.Vector3();
  aplicar(max);
  s.onBeforeRender = (renderer, _cena, camera) => {
    const h = renderer.domElement.clientHeight || 800;
    let porPx;
    if (camera.isOrthographicCamera) porPx = (camera.top - camera.bottom) / (camera.zoom || 1) / h;
    else {
      s.getWorldPosition(p);
      const d = p.sub(camera.position).dot(camera.getWorldDirection(new THREE.Vector3()));
      porPx = 2 * Math.max(d, 1) * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / h;
    }
    aplicar(Math.min(px * porPx, max));
    s.updateMatrixWorld();
  };
}

function tracejado(pos, corHex, opacidade, traco, vao) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
  const l = new THREE.LineSegments(geo, new THREE.LineDashedMaterial({ color: cor(corHex), dashSize: traco, gapSize: vao,
    transparent: true, opacity: opacidade, depthWrite: false }));
  l.computeLineDistances();
  return semToque(l);
}

/**
 * O grupo da referência (mm, Z para cima) a partir da resposta de GET …/lancamento/referencia
 * ({segmentos, eixos, niveis}); `caixa` (THREE.Box3 do modelo) contorna os níveis quando não há eixos.
 */
export function montarReferencia(r, { escuro = false, caixa = null, zChao = 0 } = {}) {
  const grupo = new THREE.Group();
  grupo.name = 'referencia';
  const cores = escuro ? TEMA.escuro : TEMA.claro;
  const segs = r.segmentos || [], eixos = r.eixos || [], niveis = r.niveis || [];
  if (segs.length) {
    const pos = new Float32Array(segs.length * 6);
    segs.forEach((s, i) => pos.set([s[0], s[1], zChao, s[2], s[3], zChao], i * 6));
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: cor(escuro ? COR_ARQ.escuro : COR_ARQ.claro), transparent: true, opacity: 0.9 }));
    l.name = 'arquitetonico';
    grupo.add(semToque(l));
  }
  if (eixos.length) {
    const pos = [];
    for (const e of eixos) pos.push(e.a[0], e.a[1], e.a[2] || 0, e.b[0], e.b[1], e.b[2] || 0);
    const l = tracejado(pos, cores.linha, escuro ? 0.6 : 0.7, 900, 600);
    l.name = 'eixos';
    grupo.add(l);
    const L = Math.max(...eixos.map(e => Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])));
    const raio = Math.min(Math.max(L * 0.012, 250), 700);
    for (const e of eixos) {
      const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], d = Math.hypot(dx, dy) || 1;
      for (const [p, sinal] of [[e.a, -1], [e.b, 1]]) {
        const s = balao(e.nome, cores);
        naTela(s, 28, 2 * raio, diam => {
          s.scale.setScalar(diam);
          s.position.set(p[0] + sinal * dx / d * diam * 0.6, p[1] + sinal * dy / d * diam * 0.6, p[2] || 0);
        });
        grupo.add(s);
      }
    }
  }
  if (niveis.length) {
    let x0, y0, x1, y1;
    if (eixos.length) {
      const xs = eixos.flatMap(e => [e.a[0], e.b[0]]), ys = eixos.flatMap(e => [e.a[1], e.b[1]]);
      [x0, y0, x1, y1] = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    } else if (caixa && !caixa.isEmpty()) {
      [x0, y0, x1, y1] = [caixa.min.x - 1500, caixa.min.y - 1500, caixa.max.x + 1500, caixa.max.y + 1500];
    }
    if (x0 !== undefined) {
      const pos = [];
      for (const n of niveis) { const z = n.z; pos.push(x0, y0, z, x1, y0, z, x1, y0, z, x1, y1, z, x1, y1, z, x0, y1, z, x0, y1, z, x0, y0, z); }
      const l = tracejado(pos, cores.nivel, escuro ? 0.3 : 0.55, 1200, 800);
      l.name = 'niveis';
      grupo.add(l);
      // os níveis na mesma cota viram uma cabeça só, com os nomes juntos; os muito perto alternam o canto
      const porCota = new Map();
      for (const n of niveis) { const k = Math.round(n.z); porCota.set(k, [...(porCota.get(k) || []), n.nome]); }
      const cotas = [...porCota.keys()].sort((a, b) => a - b);
      cotas.forEach((z, i) => {
        const nome = porCota.get(z).filter(Boolean).join(' / ') || 'nível';
        const outro = i > 0 && z - cotas[i - 1] < 600 && i % 2 === 1;
        const s = cabecaDoNivel(nome, z, cores);
        const x = outro ? x0 : x1, y = outro ? y1 : y0;
        naTela(s, 34, 1400, alt => { s.scale.set(alt * s.userData.proporcao, alt, 1); s.position.set(x, y, z); });
        grupo.add(s);
      });
    }
  }
  return grupo;
}
