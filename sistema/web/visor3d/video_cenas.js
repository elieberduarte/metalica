// O vídeo das cenas (12/11, FERRAMENTA · CENAS — usuário: "fiz uma sequência de cenas… usar ela como ref. e o sistema ir
// passeando por elas como se fosse uma câmera se movimentando"; aprovado: para em cada cena, o visual muda suave no caminho,
// na janela Exportar). Aqui o que não depende da tela: a linha do tempo (paradas e trechos), o caminho da câmera entre duas
// cenas e o gravador de MP4 (H.264 pelo WebCodecs do navegador, o arquivo montado aqui — sem programa de fora).

/** A suavização do trecho: sai parada, acelera, chega parada (as cenas são paradas). */
export const suave = (t) => { t = Math.min(1, Math.max(0, t)); return t * t * t * (t * (t * 6 - 15) + 10); };

/** A linha do tempo de `n` cenas: parada na 1ª, trecho até a 2ª, parada nela… parada na última. `quadro(f)` diz, para o
 *  quadro f, as cenas (i → j) e quanto do trecho já andou (k suavizado, 0 numa parada); `parado` = o mesmo quadro de antes. */
export function linhaDoTempo(n, { porTrecho = 3, parada = 1.5, fps = 30 } = {}) {
  const qp = Math.max(1, Math.round(parada * fps)), qt = Math.max(2, Math.round(porTrecho * fps));
  const total = n * qp + Math.max(0, n - 1) * qt;
  function quadro(f) {
    let resto = Math.min(Math.max(0, f), total - 1);
    for (let i = 0; i < n; i++) {
      if (resto < qp) return { i, j: i, k: 0, parado: resto > 0 };
      resto -= qp;
      if (i === n - 1) break;
      if (resto < qt) return { i, j: i + 1, k: suave((resto + 1) / qt), parado: false };
      resto -= qt;
    }
    return { i: n - 1, j: n - 1, k: 0, parado: true };
  }
  return { total, fps, quadro, segundos: total / fps };
}

const lerp = (a, b, k) => a + (b - a) * k;

/** A câmera entre duas cenas ({posicao, alvo, fov}, mm): o alvo anda em linha; a câmera gira em volta dele (o ângulo em volta e
 *  a inclinação pelo caminho mais curto) e a distância muda na proporção — a câmera passa em arco, não atravessa o prédio. */
export function cameraEntre(a, b, k) {
  if (k <= 0) return { posicao: [...a.posicao], alvo: [...a.alvo], fov: a.fov || 45 };
  if (k >= 1) return { posicao: [...b.posicao], alvo: [...b.alvo], fov: b.fov || 45 };
  const esf = (c) => {
    const d = [0, 1, 2].map(x => c.posicao[x] - c.alvo[x]), r = Math.hypot(...d) || 1;
    return { r, az: Math.atan2(d[1], d[0]), el: Math.asin(Math.max(-1, Math.min(1, d[2] / r))) };
  };
  const ea = esf(a), eb = esf(b);
  let daz = eb.az - ea.az;
  while (daz > Math.PI) daz -= 2 * Math.PI;
  while (daz < -Math.PI) daz += 2 * Math.PI;
  const alvo = [0, 1, 2].map(x => lerp(a.alvo[x], b.alvo[x], k));
  const r = Math.exp(lerp(Math.log(ea.r), Math.log(eb.r), k)), az = ea.az + daz * k, el = lerp(ea.el, eb.el, k);
  const posicao = [alvo[0] + r * Math.cos(el) * Math.cos(az), alvo[1] + r * Math.cos(el) * Math.sin(az), alvo[2] + r * Math.sin(el)];
  return { posicao, alvo, fov: lerp(a.fov || 45, b.fov || 45, k) };
}

/** O voo contínuo (usuário, 12/11, depois da amostra-10: "fica muito tempo parado em cada cena, poderia ser algo mais fluído,
 *  não precisa nem parar na cena só mantém a velocidade de transição como se fosse um drone sobrevoando a estrutura"): uma
 *  curva só (Catmull-Rom) passando por todas as câmeras — no alvo, na distância (log), no ângulo em volta, na inclinação e
 *  na lente, para a câmera seguir em arco —, percorrida com a velocidade constante (pelo comprimento do caminho), só a saída
 *  e a chegada suaves. `quadro(f)` dá a câmera e as cenas do trecho (i → j, k = quanto andou nele, para o visual). */
export function caminhoContinuo(cameras, { porTrecho = 3, fps = 30 } = {}) {
  const n = cameras.length;
  const chave = [];
  let azAntes = null;
  for (const c of cameras) {
    const d = [0, 1, 2].map(x => c.posicao[x] - c.alvo[x]), r = Math.hypot(...d) || 1;
    let az = Math.atan2(d[1], d[0]);
    if (azAntes !== null) { while (az - azAntes > Math.PI) az -= 2 * Math.PI; while (az - azAntes < -Math.PI) az += 2 * Math.PI; }
    azAntes = az;
    chave.push([c.alvo[0], c.alvo[1], c.alvo[2], Math.log(r), az, Math.asin(Math.max(-1, Math.min(1, d[2] / r))), c.fov || 45]);
  }
  const P = (m) => m < 0 ? chave[0].map((v, x) => 2 * v - chave[Math.min(1, n - 1)][x])
                  : m >= n ? chave[n - 1].map((v, x) => 2 * v - chave[Math.max(0, n - 2)][x]) : chave[m];
  const ponto = (m, u) => {                                 // o trecho m (da câmera m à m+1), u de 0 a 1
    const a = P(m - 1), b = P(m), c = P(m + 1), d = P(m + 2), u2 = u * u, u3 = u2 * u;
    return b.map((_, x) => 0.5 * (2 * b[x] + (c[x] - a[x]) * u + (2 * a[x] - 5 * b[x] + 4 * c[x] - d[x]) * u2 + (3 * b[x] - a[x] - 3 * c[x] + d[x]) * u3));
  };
  const camera = (v) => {
    const [ax, ay, az_, lr, ang, el0, fov] = v, r = Math.exp(lr), el = Math.max(-0.05, Math.min(1.55, el0));
    return { posicao: [ax + r * Math.cos(el) * Math.cos(ang), ay + r * Math.cos(el) * Math.sin(ang), az_ + r * Math.sin(el)], alvo: [ax, ay, az_], fov };
  };
  // o comprimento do caminho (a câmera e o alvo), em amostras: a velocidade constante vem dele
  const A = 48, tabela = [{ m: 0, u: 0, s: 0 }];
  let s = 0, antes = camera(ponto(0, 0));
  for (let m = 0; m < n - 1; m++) for (let k = 1; k <= A; k++) {
    const c = camera(ponto(m, k / A));
    s += Math.hypot(...[0, 1, 2].map(x => c.posicao[x] - antes.posicao[x])) + 0.5 * Math.hypot(...[0, 1, 2].map(x => c.alvo[x] - antes.alvo[x])) + 1e-6;
    tabela.push({ m, u: k / A, s }); antes = c;
  }
  const T = Math.max(1 / fps, (n - 1) * porTrecho), total = Math.max(2, Math.round(T * fps) + 1), rampa = Math.min(1, T / 4);
  const andado = (t) => {                                   // a fração do caminho no tempo t: velocidade constante, rampas de `rampa` s
    const area = T - rampa;
    if (t <= rampa) return (t * t / (2 * rampa)) / area;
    if (t >= T - rampa) { const q = T - t; return (area - q * q / (2 * rampa)) / area; }
    return (t - rampa / 2) / area;
  };
  function quadro(f) {
    const alvoS = Math.min(1, Math.max(0, andado(Math.min(Math.max(0, f), total - 1) * T / (total - 1)))) * s;
    let lo = 0, hi = tabela.length - 1;
    while (hi - lo > 1) { const md = (lo + hi) >> 1; if (tabela[md].s < alvoS) lo = md; else hi = md; }
    const a = tabela[lo], b = tabela[hi], w = b.s > a.s ? (alvoS - a.s) / (b.s - a.s) : 0;
    let m = b.m, u = a.m === b.m ? a.u + (b.u - a.u) * w : b.u * w;
    if (hi === 0) { m = 0; u = 0; }
    return { i: m, j: Math.min(n - 1, m + 1), k: u, parado: false, cam: camera(ponto(m, u)) };
  }
  return { total, fps, quadro, segundos: total / fps };
}

/** O ângulo (graus) entre dois, pelo caminho mais curto. */
export function anguloEntre(a, b, k) {
  let d = ((b - a) % 360 + 540) % 360 - 180;
  return (a + d * k + 360) % 360;
}

// ------------------------------------------------------------------ o MP4

/** Os codecs H.264 a tentar para o tamanho (o nível sobe com a imagem: 4.0 até Full HD, 5.1 até 4K, 5.2 acima). */
function codecs(w, h) {
  const px = w * h;
  const niveis = px <= 1920 * 1088 ? ['28', '2a', '33'] : px <= 4096 * 2304 ? ['33', '34'] : ['34'];
  return niveis.flatMap(n => ['avc1.6400' + n, 'avc1.4d00' + n]);
}

/** O navegador grava vídeo H.264 nesse tamanho? (o WebCodecs só existe em página segura — localhost conta) */
export async function podeGravar(w, h, fps = 30) {
  if (typeof VideoEncoder === 'undefined') return null;
  for (const codec of codecs(w, h)) {
    const cfg = { codec, width: w, height: h, framerate: fps, bitrate: taxa(w, h, fps), avc: { format: 'avc' } };
    try { if ((await VideoEncoder.isConfigSupported(cfg)).supported) return cfg; } catch (e) { /* o próximo */ }
  }
  return null;
}

/** Dá a vez ao navegador (a barra de andamento, o Cancelar) entre um quadro e outro, também com a janela minimizada.
 *  O setTimeout numa janela minimizada ou escondida espera 1 s ou mais (depois de 5 min, até 1 min) e o requestAnimationFrame
 *  nem dispara: o vídeo parava até o usuário voltar à janela (13/11). A mensagem do MessageChannel não tem esse freio. */
export function ceder() {
  return new Promise(res => { const c = new MessageChannel(); c.port1.onmessage = () => { c.port1.close(); res(); }; c.port2.postMessage(0); });
}

const taxa = (w, h, fps) => Math.round(Math.min(60e6, Math.max(4e6, w * h * fps * 0.2)));   // ~12 Mbit/s em Full HD a 30

/** Grava os quadros (canvas) num MP4: `quadro(canvas, vezes)` põe a imagem `vezes` quadros seguidos (a parada: desenhada uma
 *  vez); `fim()` devolve o Blob. Um quadro-chave a cada 2 s. */
export class GravadorMp4 {
  static async abrir(w, h, fps = 30) {
    const cfg = await podeGravar(w, h, fps);
    if (!cfg) throw new Error(typeof VideoEncoder === 'undefined' ? 'este navegador não grava vídeo (WebCodecs)' : `o navegador não grava vídeo H.264 em ${w} × ${h}`);
    return new GravadorMp4(cfg, fps);
  }

  constructor(cfg, fps) {
    this.cfg = cfg; this.fps = fps; this.w = cfg.width; this.h = cfg.height;
    this.amostras = []; this.chaves = []; this.tempos = []; this.descricao = null; this.erro = null; this.n = 0;
    this.enc = new VideoEncoder({
      output: (chunk, meta) => {
        if (meta && meta.decoderConfig && meta.decoderConfig.description && !this.descricao)
          this.descricao = new Uint8Array(meta.decoderConfig.description instanceof ArrayBuffer ? meta.decoderConfig.description
                                          : meta.decoderConfig.description.buffer.slice(meta.decoderConfig.description.byteOffset, meta.decoderConfig.description.byteOffset + meta.decoderConfig.description.byteLength));
        const dados = new Uint8Array(chunk.byteLength); chunk.copyTo(dados);
        this.amostras.push(dados); this.tempos.push(chunk.timestamp);
        if (chunk.type === 'key') this.chaves.push(this.amostras.length);
      },
      error: (e) => { this.erro = e; if (this.acordar) this.acordar(); },
    });
    this.enc.configure(cfg);
  }

  async quadro(canvas, vezes = 1) {
    for (let v = 0; v < vezes; v++) {
      if (this.erro) throw this.erro;
      while (this.enc.encodeQueueSize > 3 && !this.erro) await this.esperarFila();
      if (this.erro) throw this.erro;
      const vf = new VideoFrame(canvas, { timestamp: Math.round(this.n * 1e6 / this.fps), duration: Math.round(1e6 / this.fps) });
      this.enc.encode(vf, { keyFrame: this.n % (this.fps * 2) === 0 });
      vf.close();
      this.n++;
    }
  }

  /** A fila do codificador andou (o evento dequeue; sem ele, só dá a vez). Sem setTimeout: ver ceder(). */
  esperarFila() {
    if (!('ondequeue' in this.enc)) return ceder();
    return new Promise(r => { this.acordar = r; this.enc.addEventListener('dequeue', r, { once: true }); });
  }

  async fim() {
    await this.enc.flush();
    this.enc.close();
    if (this.erro) throw this.erro;
    if (!this.descricao) throw new Error('o codificador não deu a configuração do H.264');
    return montarMp4({ w: this.w, h: this.h, fps: this.fps, amostras: this.amostras, chaves: this.chaves, avcC: this.descricao, tempos: this.tempos });
  }

  cancelar() { try { this.enc.close(); } catch (e) { /* já fechado */ } }
}

/** O arquivo MP4 (ISO BMFF): ftyp, mdat com as amostras em sequência, moov no fim com uma trilha de vídeo (avc1/avcC). */
export function montarMp4({ w, h, fps, amostras, chaves, avcC, tempos = null }) {
  const caixa = (tipo, ...partes) => {
    const corpo = partes.flat(), tam = 8 + corpo.reduce((s, p) => s + p.length, 0), b = new Uint8Array(tam), dv = new DataView(b.buffer);
    dv.setUint32(0, tam); for (let i = 0; i < 4; i++) b[4 + i] = tipo.charCodeAt(i);
    let o = 8; for (const p of corpo) { b.set(p, o); o += p.length; }
    return b;
  };
  const u = (bits, ...vals) => { const b = new Uint8Array(vals.length * bits / 8), dv = new DataView(b.buffer);
    vals.forEach((v, i) => bits === 32 ? dv.setUint32(i * 4, v) : bits === 16 ? dv.setUint16(i * 2, v) : dv.setUint8(i, v)); return b; };
  const txt = (s) => Uint8Array.from(s, c => c.charCodeAt(0));
  const cheia = (tipo, versaoFlags, ...partes) => caixa(tipo, u(32, versaoFlags), ...partes);
  const matriz = u(32, 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000);
  const escala = fps * 1000, delta = 1000, n = amostras.length, dur = n * delta, durMs = Math.round(n * 1000 / fps);
  const ftyp = caixa('ftyp', txt('isom'), u(32, 512), txt('isomiso2avc1mp41'));
  const dadosTam = amostras.reduce((s, a) => s + a.length, 0);
  const mdatCab = u(32, 8 + dadosTam); const mdatTipo = txt('mdat');
  const inicio = ftyp.length + 8;
  const avc1 = caixa('avc1', u(8, 0, 0, 0, 0, 0, 0), u(16, 1, 0, 0), u(32, 0, 0, 0), u(16, w, h), u(32, 0x480000, 0x480000, 0),
                     u(16, 1), new Uint8Array(32), u(16, 0x18, 0xffff), caixa('avcC', avcC));
  // com quadros B (a placa de vídeo pode usar), a ordem de mostrar não é a de gravar: o desvio de cada amostra (ctts v1, com sinal)
  const desvios = tempos ? tempos.map((t, i) => Math.round(t * fps / 1e6) * delta - i * delta) : [];
  const ctts = desvios.some(d => d !== 0) ? [cheia('ctts', 0x01000000, u(32, n), u(32, ...desvios.flatMap(d => [1, d >>> 0])))] : [];
  const stbl = caixa('stbl',
    cheia('stsd', 0, u(32, 1), avc1),
    cheia('stts', 0, u(32, 1, n, delta)),
    ...ctts,
    cheia('stss', 0, u(32, chaves.length, ...chaves)),
    cheia('stsc', 0, u(32, 1, 1, n, 1)),
    cheia('stsz', 0, u(32, 0, n), u(32, ...amostras.map(a => a.length))),
    cheia('stco', 0, u(32, 1, inicio)));
  const minf = caixa('minf', cheia('vmhd', 1, u(16, 0, 0, 0, 0)), caixa('dinf', cheia('dref', 0, u(32, 1), cheia('url ', 1))), stbl);
  const mdia = caixa('mdia', cheia('mdhd', 0, u(32, 0, 0, escala, dur), u(16, 0x55c4, 0)),
                     cheia('hdlr', 0, u(32, 0), txt('vide'), u(32, 0, 0, 0), txt('Metalica Cenas'), u(8, 0)), minf);
  const tkhd = cheia('tkhd', 3, u(32, 0, 0, 1, 0, durMs, 0, 0), u(16, 0, 0, 0, 0), matriz, u(32, w * 65536, h * 65536));
  const mvhd = cheia('mvhd', 0, u(32, 0, 0, 1000, durMs, 0x10000), u(16, 0x100, 0), u(32, 0, 0), matriz, u(32, 0, 0, 0, 0, 0, 0, 2));
  const moov = caixa('moov', mvhd, caixa('trak', tkhd, mdia));
  return new Blob([ftyp, mdatCab, mdatTipo, ...amostras, moov], { type: 'video/mp4' });
}
