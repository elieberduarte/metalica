// A sombra suave nos cantos (oclusão de ambiente) do render das Cenas (roteiro de refino aceito em 12/11, item 2): onde as
// peças se encontram, no pé dos pilares no chão, debaixo das vigas e nos cantos de dentro, a luz do céu chega menos — a
// imagem ganha volume sem mudar a luz do sol.
//
// É feita pela tela (como no render dos programas de maquete): o bloco é desenhado de novo só para ter a profundidade de
// cada pixel; para cada pixel, alguns pontos em volta (num raio fixo em mm do mundo) dizem quanto da meia-esfera em cima da
// face está fechada por outras peças. O resultado é uma camada preta com o alfa da oclusão, posta por cima da imagem do
// bloco: o céu e o fundo transparente (sem profundidade) ficam como estão. Um desfoque 4 × 4 tira o granulado do giro dos
// pontos (o mesmo padrão 4 × 4 de pixel a pixel).

import * as THREE from 'three';

const VERT = /* glsl */`
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const OCLUSAO = /* glsl */`
uniform sampler2D tProf;
uniform mat4 uProjInv;
uniform vec2 uTam;          // o tamanho do alvo em px
uniform float uEscalaPx;    // px por mm a 1 mm de distância (proj[1][1] · altura / 2)
uniform float uRaio;        // mm
uniform float uRaioMaxPx;   // a margem do bloco: nenhum ponto fora dela
uniform vec4 uChao;         // o plano do chão na vista (normal, d): o piso do visor não grava profundidade; w = 0 → sem chão
uniform float uTemChao;
varying vec2 vUv;
const int N = 16;

vec3 posVista(vec2 uv, float d) {
  vec4 p = uProjInv * vec4(uv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
  return p.xyz / p.w;
}
// o ponto do pixel: a peça (a profundidade) ou, sem peça, o chão onde o raio dele bate; w = 0 → o céu
vec4 ponto(vec2 uv) {
  float d = texture2D(tProf, uv).x;
  if (d < 1.0) return vec4(posVista(uv, d), 1.0);
  if (uTemChao < 0.5) return vec4(0.0);
  vec3 dir = normalize(posVista(uv, 1.0));
  float dn = dot(uChao.xyz, dir);
  if (dn > -1e-4) return vec4(0.0);                            // o raio não desce até o chão
  return vec4(dir * (-uChao.w / dn), 2.0);                     // w = 2: o chão
}

void main() {
  vec4 P4 = ponto(vUv);
  if (P4.w == 0.0) { gl_FragColor = vec4(0.0); return; }     // o céu: sem oclusão
  vec3 P = P4.xyz, n;
  vec2 px = 1.0 / uTam;
  if (P4.w > 1.5) n = uChao.xyz;                               // no chão: a normal do plano
  else {
    // a normal pelos vizinhos, do lado que muda menos (na borda de uma peça o vizinho de trás daria uma normal torta)
    vec3 pr = ponto(vUv + vec2(px.x, 0.0)).xyz, pl = ponto(vUv - vec2(px.x, 0.0)).xyz;
    vec3 pu = ponto(vUv + vec2(0.0, px.y)).xyz, pd = ponto(vUv - vec2(0.0, px.y)).xyz;
    vec3 dx = abs(pr.z - P.z) < abs(P.z - pl.z) ? pr - P : P - pl;
    vec3 dy = abs(pu.z - P.z) < abs(P.z - pd.z) ? pu - P : P - pd;
    n = normalize(cross(dx, dy));
    if (dot(n, -P) < 0.0) n = -n;
  }
  float rPx = min(uRaio * uEscalaPx / max(-P.z, 1.0), uRaioMaxPx);
  if (rPx < 1.0) { gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }   // tão longe que o raio não chega a um pixel: aberto
  // o giro dos pontos num padrão 4 × 4 (o desfoque 4 × 4 depois o apaga)
  vec2 q = mod(floor(gl_FragCoord.xy), 4.0);
  float giro = (q.x * 4.0 + q.y) * 0.3927 + mod(q.x + q.y, 2.0) * 0.19;
  float soma = 0.0;
  for (int i = 0; i < N; i++) {
    float t = (float(i) + 0.5) / float(N);
    float a = float(i) * 2.39996 + giro;
    vec2 uv = vUv + vec2(cos(a), sin(a)) * (t * rPx) * px;
    vec4 S = ponto(uv);
    if (S.w == 0.0) continue;
    vec3 v = S.xyz - P;
    float vv = dot(v, v);
    float cai = max(0.0, 1.0 - vv / (uRaio * uRaio));         // o que está longe não fecha
    soma += max(0.0, dot(v, n) * inversesqrt(vv + 1.0) - 0.12) * cai;
  }
  gl_FragColor = vec4(vec3(soma / float(N)), 1.0);            // quanto fecha (0 = aberto); alfa 1 = há peça ou chão
}
`;

const SAIDA = /* glsl */`
uniform sampler2D tOclusao;   // r = quanto fecha; a = 1 onde há peça ou chão (0 = o céu)
uniform vec2 uTam;
uniform float uForca;
varying vec2 vUv;
void main() {
  if (texture2D(tOclusao, vUv).a < 0.5) { gl_FragColor = vec4(0.0); return; }
  float s = 0.0, k = 0.0;
  for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) {
    vec4 o = texture2D(tOclusao, vUv + (vec2(float(i), float(j)) - 1.5) / uTam);
    float w = step(0.5, o.a);                                  // o céu em volta não clareia o canto
    s += o.r * w; k += w;
  }
  float a = clamp(uForca * s / max(k, 1.0), 0.0, 0.85);
  gl_FragColor = vec4(0.0, 0.0, 0.0, a);                      // preto com o alfa da oclusão (já multiplicado)
}
`;

export class Oclusao {
  constructor(renderer) {
    this.r = renderer;
    this.camQuad = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const quad = (frag, uniforms) => {
      const m = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: frag, uniforms, depthTest: false, depthWrite: false, transparent: false });
      const cena = new THREE.Scene(); cena.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), m));
      return { cena, u: uniforms };
    };
    this.passeOclusao = quad(OCLUSAO, { tProf: { value: null }, uProjInv: { value: new THREE.Matrix4() }, uTam: { value: new THREE.Vector2() },
      uEscalaPx: { value: 1 }, uRaio: { value: 800 }, uRaioMaxPx: { value: 64 }, uChao: { value: new THREE.Vector4() }, uTemChao: { value: 0 } });
    this.passeSaida = quad(SAIDA, { tOclusao: { value: null }, uTam: { value: new THREE.Vector2() }, uForca: { value: 1.5 } });
    this.alvos = null;
  }

  _alvos(w, h) {
    if (this.alvos && this.alvos.w === w && this.alvos.h === h) return this.alvos;
    this.liberar();
    const prof = new THREE.WebGLRenderTarget(w, h, { depthBuffer: true });
    prof.depthTexture = new THREE.DepthTexture(w, h, THREE.FloatType);
    const ocl = new THREE.WebGLRenderTarget(w, h, { depthBuffer: false });
    this.alvos = { w, h, prof, ocl };
    return this.alvos;
  }

  /** Desenha no canvas do renderer (que deve ter w × h px) a camada da oclusão da `cena` vista por `cam` (com o
   *  setViewOffset do bloco já posto): preto com o alfa de quanto o canto fecha; transparente onde não há peça.
   *  `chaoZ`: a altura do chão no mundo (o piso à vista; null = sem chão — o fundo transparente). */
  desenhar(cena, cam, w, h, { raio = 800, forca = 1.5, raioMaxPx = 64, chaoZ = null } = {}) {
    const r = this.r, A = this._alvos(w, h);
    const corAntes = r.getClearColor(new THREE.Color()), alfaAntes = r.getClearAlpha(), fundoAntes = cena.background;
    cena.background = null;
    try {
      r.setRenderTarget(A.prof);
      r.setClearColor(0x000000, 0); r.clear(true, true, true);
      r.render(cena, cam);
      cam.updateProjectionMatrix();
      const u = this.passeOclusao.u;
      u.tProf.value = A.prof.depthTexture;
      u.uProjInv.value.copy(cam.projectionMatrixInverse);
      u.uTam.value.set(w, h);
      u.uEscalaPx.value = cam.projectionMatrix.elements[5] * h / 2;
      u.uRaio.value = raio; u.uRaioMaxPx.value = raioMaxPx;
      u.uTemChao.value = Number.isFinite(chaoZ) ? 1 : 0;
      if (Number.isFinite(chaoZ)) {                          // o plano z = chaoZ do mundo na vista da câmera
        cam.updateMatrixWorld();
        const vista = cam.matrixWorldInverse;
        const n = new THREE.Vector3(0, 0, 1).transformDirection(vista);
        const p = new THREE.Vector3(0, 0, chaoZ).applyMatrix4(vista);
        u.uChao.value.set(n.x, n.y, n.z, -n.dot(p));
      }
      r.setRenderTarget(A.ocl);
      r.render(this.passeOclusao.cena, this.camQuad);
      const s = this.passeSaida.u;
      s.tOclusao.value = A.ocl.texture; s.uTam.value.set(w, h); s.uForca.value = forca;
      r.setRenderTarget(null);
      r.clear(true, true, true);
      r.render(this.passeSaida.cena, this.camQuad);
    } finally {
      r.setRenderTarget(null);
      r.setClearColor(corAntes, alfaAntes);
      cena.background = fundoAntes;
    }
  }

  liberar() {
    if (!this.alvos) return;
    this.alvos.prof.depthTexture.dispose(); this.alvos.prof.dispose(); this.alvos.ocl.dispose();
    this.alvos = null;
  }
}
