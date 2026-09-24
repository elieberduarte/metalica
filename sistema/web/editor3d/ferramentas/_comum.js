// Apoio comum às ferramentas do editor 3D.
//
// Só contém o que várias ferramentas repetiriam: álgebra de vetores em array,
// construção de prévias no Three.js, geometria de contorno e extrusão, e uma
// camada fina sobre os comandos do núcleo.
//
// Por que uma camada sobre os comandos: o núcleo (`nucleo/comandos.js`) está sendo
// escrito em paralelo. Se ele já existir, usamos as classes dele; se ainda não,
// caímos em comandos equivalentes definidos aqui, que respeitam o mesmo contrato
// (`rotulo`, `aplicar(doc)`, `desfazer(doc)`). Assim nenhuma ferramenta deixa de
// carregar por causa de um arquivo ausente, e o desfazer continua funcionando.

import * as THREE from '../../lib/three.module.js';

export { THREE };

// Comandos do núcleo, com `await` no topo do módulo: as ferramentas só terminam de
// carregar depois dele, então não há corrida entre o primeiro clique e a importação.
// Se o arquivo faltar ou quebrar, seguimos com os comandos de reserva abaixo.
const NUCLEO = await import('../nucleo/comandos.js').catch(() => null);

// --------------------------------------------------------------- vetores

export const ex = () => [1, 0, 0];
export const ey = () => [0, 1, 0];
export const ez = () => [0, 0, 1];

export function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
export function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
export function mul(a, k) { return [a[0] * k, a[1] * k, a[2] * k]; }
export function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
export function cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
export function comp(a) { return Math.hypot(a[0], a[1], a[2]); }
export function dist(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }
export function meio(a, b) { return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]; }
export function normalizar(a) {
  const n = comp(a);
  return n > 1e-9 ? [a[0] / n, a[1] / n, a[2] / n] : [0, 0, 1];
}
export function iguais(a, b, tol = 1e-6) { return dist(a, b) <= tol; }
export function copiar(a) { return [a[0], a[1], a[2]]; }
export function tresJS(a) { return new THREE.Vector3(a[0], a[1], a[2]); }

/** Um vetor unitário qualquer perpendicular a `n`. */
export function perpendicular(n) {
  const a = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  return normalizar(cross(a, n));
}

/** Número no padrão brasileiro, com casas fixas (ângulos, fatores de escala). */
export function num(v, casas = 1) {
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

// --------------------------------------------------------------- identidade

let contador = 0;
export function novoId(prefixo = 'e') {
  contador += 1;
  return prefixo + Date.now().toString(36) + contador.toString(36) +
         Math.floor(Math.random() * 4096).toString(36);
}

// --------------------------------------------------------------- comandos

function clonarProfundo(v) {
  return (typeof structuredClone === 'function') ? structuredClone(v)
                                                 : JSON.parse(JSON.stringify(v));
}

/** Adiciona entidades ao documento. As entidades já vêm com `id` definido. */
export function cmdAdicionar(entidades, rotulo = 'Adicionar') {
  const lista = (Array.isArray(entidades) ? entidades : [entidades]).map(e => {
    if (!e.id) e.id = novoId();
    return e;
  });
  if (NUCLEO && NUCLEO.ComandoAdicionar) return new NUCLEO.ComandoAdicionar(lista, rotulo);
  return {
    rotulo, entidades: lista,
    aplicar(doc) { for (const e of this.entidades) doc.add(clonarProfundo(e)); },
    desfazer(doc) { for (const e of this.entidades) doc.remover(e.id); },
    ids() { return this.entidades.map(e => e.id); },
    selecao() { return this.ids(); },
  };
}

/** Remove entidades pelo id. */
export function cmdRemover(ids, rotulo = 'Apagar') {
  const lista = Array.isArray(ids) ? ids.slice() : [ids];
  if (NUCLEO && NUCLEO.ComandoRemover) return new NUCLEO.ComandoRemover(lista, rotulo);
  return {
    rotulo, alvos: lista, guardadas: [],
    aplicar(doc) {
      this.guardadas = this.alvos.map(id => clonarProfundo(doc.get(id))).filter(Boolean);
      for (const id of this.alvos) doc.remover(id);
    },
    desfazer(doc) { for (const e of this.guardadas) doc.add(clonarProfundo(e)); },
    ids() { return this.alvos.slice(); },
    selecao() { return []; },
  };
}

/**
 * Altera campos de uma entidade; guarda o valor anterior para desfazer.
 * O `ComandoAlterar` do núcleo recebe `{id: campos}`; aqui a assinatura fica
 * `(id, campos)`, que é o caso de todas as ferramentas.
 */
export function cmdAlterar(id, campos, rotulo = 'Alterar') {
  if (NUCLEO && NUCLEO.ComandoAlterar) return new NUCLEO.ComandoAlterar({ [id]: campos }, rotulo);
  return {
    rotulo, alvo: id, depois: clonarProfundo(campos), antes: null,
    aplicar(doc) {
      const e = doc.get(this.alvo);
      if (!e) return;
      if (!this.antes) {
        this.antes = {};
        for (const k of Object.keys(this.depois)) this.antes[k] = clonarProfundo(e[k]);
      }
      gravar(doc, this.alvo, this.depois);
    },
    desfazer(doc) { if (this.antes) gravar(doc, this.alvo, this.antes); },
    ids() { return [this.alvo]; },
    selecao() { return [this.alvo]; },
  };
}

function gravar(doc, id, campos) {
  if (typeof doc.alterar === 'function') { doc.alterar(id, clonarProfundo(campos)); return; }
  const e = doc.get(id);
  if (e) Object.assign(e, clonarProfundo(campos));
}

/** Agrupa vários comandos numa entrada só de desfazer. */
export function cmdComposto(lista, rotulo = 'Operação') {
  const itens = lista.filter(Boolean);
  if (itens.length === 1) return itens[0];
  if (NUCLEO && NUCLEO.ComandoComposto) return new NUCLEO.ComandoComposto(itens, rotulo);
  return {
    rotulo, itens,
    aplicar(doc) { for (const c of this.itens) c.aplicar(doc); },
    desfazer(doc) { for (let i = this.itens.length - 1; i >= 0; i--) this.itens[i].desfazer(doc); },
    ids() { return [...new Set(this.itens.flatMap(c => (c.ids ? c.ids() : [])))]; },
    selecao() { return this.ids(); },
  };
}

// --------------------------------------------------------------- entidades

/** Cópia profunda de uma entidade, com id novo. */
export function clonarEntidade(ent, prefixo = 'e') {
  const c = clonarProfundo(ent);
  c.id = novoId(prefixo);
  return c;
}

/**
 * Aplica uma transformação a uma entidade e devolve só os campos alterados.
 * `fp` transforma pontos (com translação); `fv` transforma direções.
 */
export function camposTransformados(ent, fp, fv) {
  switch (ent.tipo) {
    case 'barra':
      return { inicio: fp(ent.inicio), fim: fp(ent.fim) };
    case 'chapa': {
      const x = fv(ent.eixo_x || [1, 0, 0]);
      const y = fv(ent.eixo_y || [0, 1, 0]);
      const kx = comp(x) || 1, ky = comp(y) || 1;
      const contorno = (ent.contorno || []).map(([u, v]) => [u * kx, v * ky]);
      const furos = (ent.furos || []).map(f => ({
        ...f, x: (f.x || 0) * kx, y: (f.y || 0) * ky,
        diametro: (f.diametro || 0) * Math.min(kx, ky),
      }));
      return { origem: fp(ent.origem || [0, 0, 0]), eixo_x: normalizar(x),
               eixo_y: normalizar(y), contorno, furos };
    }
    case 'solido':
      return { vertices: (ent.vertices || []).map(fp) };
    case 'grupo':
      return { origem: fp(ent.origem || [0, 0, 0]) };
    default:
      return {};
  }
}

/** Pontos representativos de uma entidade, para caixa envolvente e prévia. */
export function pontosDaEntidade(ent) {
  if (!ent) return [];
  if (ent.tipo === 'barra') return [ent.inicio, ent.fim];
  if (ent.tipo === 'solido') return ent.vertices || [];
  if (ent.tipo === 'chapa') {
    const o = ent.origem || [0, 0, 0];
    const x = ent.eixo_x || [1, 0, 0], y = ent.eixo_y || [0, 1, 0];
    return (ent.contorno || [[0, 0]]).map(([u, v]) => add(o, add(mul(x, u), mul(y, v))));
  }
  return [];
}

/** Caixa envolvente de uma lista de ids. */
export function caixaDe(documento, ids) {
  let min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  let houve = false;
  for (const id of ids) {
    for (const p of pontosDaEntidade(documento.get(id))) {
      houve = true;
      for (let i = 0; i < 3; i++) {
        if (p[i] < min[i]) min[i] = p[i];
        if (p[i] > max[i]) max[i] = p[i];
      }
    }
  }
  return houve ? { min, max, centro: meio(min, max) }
               : { min: [0, 0, 0], max: [0, 0, 0], centro: [0, 0, 0] };
}

/** Ids da seleção corrente, seja qual for a forma que o núcleo usa. */
export function idsSelecionados(editor) {
  const s = editor && editor.selecao;
  if (!s) return [];
  const bruto = (typeof s.ids === 'function') ? s.ids()
              : (s.ids instanceof Set) ? [...s.ids]
              : Array.isArray(s.ids) ? s.ids
              : Array.isArray(s) ? s
              : (s.itens || s.entidades || []);
  return Array.from(bruto || []).map(x => (x && x.id) ? x.id : x).filter(Boolean);
}

/** Volta para a ferramenta de seleção, qualquer que seja o nome do método. */
export function voltarParaSelecao(editor) {
  for (const nome of ['usarFerramenta', 'ativarFerramenta', 'selecionarFerramenta',
                      'trocarFerramenta', 'ferramenta']) {
    const fn = editor && editor[nome];
    if (typeof fn === 'function') { try { fn.call(editor, 'selecionar'); return true; } catch { /* segue */ } }
  }
  return false;
}

// --------------------------------------------------------------- planos

/**
 * Plano de trabalho para o ponto recebido: a face sob o cursor, quando houver,
 * senão o plano de trabalho do editor, senão o plano base XY na altura do ponto.
 */
export function planoDoPonto(editor, p) {
  let n = null;
  if (p && p.normal && comp(p.normal) > 1e-6 &&
      (p.tipoSnap === 'sobre_face' || p.face >= 0 || p.entidade)) {
    n = normalizar(p.normal);
  }
  if (!n && editor && editor.planoTrabalho && editor.planoTrabalho.normal) {
    n = normalizar(editor.planoTrabalho.normal);
  }
  if (!n) n = [0, 0, 1];
  const origem = (p && p.ponto) ? copiar(p.ponto) : [0, 0, 0];
  return planoDe(origem, n);
}

/** Monta um plano com eixos locais estáveis a partir de origem e normal. */
export function planoDe(origem, normal) {
  const n = normalizar(normal);
  // Preferimos eixos alinhados aos eixos do mundo, para que medidas digitadas
  // caiam em valores redondos nas situações usuais.
  let u;
  if (Math.abs(n[2]) > 0.999) u = [1, 0, 0];
  else if (Math.abs(n[0]) > 0.999) u = [0, 1, 0];
  else if (Math.abs(n[1]) > 0.999) u = [1, 0, 0];
  else u = perpendicular(n);
  u = normalizar(sub(u, mul(n, dot(u, n))));
  const v = normalizar(cross(n, u));
  return { origem: copiar(origem), normal: n, ex: u, ey: v };
}

export function para2d(plano, p) {
  const d = sub(p, plano.origem);
  return [dot(d, plano.ex), dot(d, plano.ey)];
}

export function para3d(plano, u, v) {
  return add(plano.origem, add(mul(plano.ex, u), mul(plano.ey, v)));
}

/** Projeta um ponto qualquer sobre o plano (útil quando o snap saiu do plano). */
export function projetarNoPlano(plano, p) {
  const d = sub(p, plano.origem);
  return add(plano.origem, sub(d, mul(plano.normal, dot(d, plano.normal))));
}

// --------------------------------------------------------------- eixos

export const EIXOS = {
  x: { vetor: [1, 0, 0], nome: 'X', cor: 0xc0392b },
  y: { vetor: [0, 1, 0], nome: 'Y', cor: 0x2e8b57 },
  z: { vetor: [0, 0, 1], nome: 'Z', cor: 0x0b3d91 },
};

/**
 * Lê as setas do teclado como travamento de eixo. Segue a convenção da inferência
 * do núcleo (← X, → Y, ↑ Z, ↓ solta), para que a ferramenta e o glifo de snap
 * nunca discordem sobre qual eixo está travado.
 */
export function lerEixoTecla(ev) {
  if (ev.key === 'ArrowLeft') return 'x';
  if (ev.key === 'ArrowRight') return 'y';
  if (ev.key === 'ArrowUp') return 'z';
  if (ev.key === 'ArrowDown') return null;   // solta o travamento
  return undefined;                          // não é tecla de eixo
}

/**
 * Trata uma seta como travamento de eixo na ferramenta `f` (que guarda `f.eixo`) e
 * espelha o estado na inferência do núcleo. Alterna: a mesma seta de novo solta.
 * Devolve true se a tecla era de eixo.
 */
export function teclaDeEixo(f, ev) {
  const e = lerEixoTecla(ev);
  if (e === undefined) return false;
  const novo = (e && f.eixo === e) ? null : e;
  f.eixo = novo;
  travarEixoNucleo(f.editor, novo);
  return true;
}

/** Deixa a inferência do núcleo com o mesmo eixo travado (sem alternar). */
export function travarEixoNucleo(editor, eixo) {
  const inf = editor && editor.inferencia;
  if (!inf) return;
  if (!eixo) { if (typeof inf.destravar === 'function') inf.destravar(); return; }
  if (inf.travado !== eixo && typeof inf.travarEixo === 'function') inf.travarEixo(eixo);
}

/** Lê o eixo travado no núcleo — ele pode ter recebido a seta antes da ferramenta. */
export function sincronizarEixo(f) {
  const inf = f.editor && f.editor.inferencia;
  if (!inf || !('travado' in inf)) return;
  if (inf.travado === 'aresta' && inf.direcaoTravada) {
    // Shift sobre uma aresta: paralelo a ela (o banzo inclinado)
    EIXOS.aresta = { vetor: inf.direcaoTravada.slice(0, 3), nome: 'paralelo à aresta', cor: 0xb07cc6 };
  }
  f.eixo = inf.travado || null;
}

/**
 * Abre a caixa de medidas do editor já com um prefixo. O núcleo manda para a caixa
 * só dígitos e separadores; "*5" e "/3" (array depois de uma cópia) começam por um
 * caractere que ele não encaminha, então a ferramenta abre a caixa por conta própria.
 */
export function abrirCaixaDeMedidas(editor, prefixo) {
  const m = editor && editor.el && editor.el.medida;
  if (!m || typeof m.focus !== 'function') return false;
  m.focus();
  m.value = prefixo;
  try { m.setSelectionRange(prefixo.length, prefixo.length); } catch { /* campo sem seleção */ }
  return true;
}

/** Âncora da inferência: base do snap de eixo e altura do plano de trabalho. */
export function ancorar(editor, p) {
  const inf = editor && editor.inferencia;
  if (inf && typeof inf.definirAncora === 'function' && p) inf.definirAncora(p);
}

export function desancorar(editor) {
  const inf = editor && editor.inferencia;
  if (inf && typeof inf.limparAncora === 'function') inf.limparAncora();
}

// --------------------------------------------------------------- raio do cursor

// Snaps que apontam uma feição do modelo: quando o cursor está num deles, vale o
// ponto do snap, não a reta do raio.
const SNAPS_DE_OBJETO = new Set(['extremidade', 'meio', 'centro', 'interseccao', 'sobre_aresta']);

/** Raio do cursor em milímetros, se o núcleo puder dá-lo. */
export function raioDoEvento(editor, p) {
  if (p && p.raio && p.raio.origem && p.raio.direcao) return p.raio;
  const s = editor && editor.selecao;
  if (s && typeof s.raioEm === 'function' && p && p.tela) {
    try { return s.raioEm(p.tela[0], p.tela[1]); } catch { return null; }
  }
  return null;
}

/** Interseção do raio do cursor com um plano (null se paralelo ou atrás). */
export function raioContraPlano(editor, p, plano) {
  const r = raioDoEvento(editor, p);
  if (!r) return null;
  const d = normalizar(r.direcao);
  const den = dot(d, plano.normal);
  if (Math.abs(den) < 1e-6) return null;
  const t = dot(sub(plano.origem, r.origem), plano.normal) / den;
  return t < 0 ? null : add(r.origem, mul(d, t));
}

/**
 * Ponto do evento levado a um plano. Snap de feição (extremidade, meio…) é
 * projetado no plano. Cursor solto — no chão ou sobre uma face que não é a do
 * plano — usa a interseção do raio com o plano: senão, desenhando numa parede ou
 * girando por cima de uma caixa, o ponto cairia em outra superfície e a projeção
 * sairia torta.
 */
export function noPlano(editor, p, plano) {
  const t = p && p.tipoSnap;
  const solto = !t || t === 'plano_base' || t === 'sobre_face';
  const fora = Math.abs(dot(sub(p.ponto, plano.origem), plano.normal)) > 1.0;
  if (solto && fora) {
    const q = raioContraPlano(editor, p, plano);
    if (q) return q;
  }
  return projetarNoPlano(plano, p.ponto);
}

/**
 * Posição do cursor ao longo de uma reta (base + t·dir), devolvendo t. Usada no
 * push/pull e nas alças de escala: arrastar pela normal de uma face horizontal não
 * pode depender do ponto no chão, que não se move na vertical.
 */
export function distanciaNaReta(editor, p, base, dir) {
  const u = normalizar(dir);
  if (p && SNAPS_DE_OBJETO.has(p.tipoSnap)) return dot(sub(p.ponto, base), u);
  const r = raioDoEvento(editor, p);
  if (r) {
    const d = normalizar(r.direcao), w = sub(base, r.origem);
    const b = dot(u, d), den = 1 - b * b;
    if (den > 1e-6) return (b * dot(w, d) - dot(w, u)) / den;
  }
  return dot(sub(p.ponto, base), u);
}

/** Projeta `p` sobre a reta que passa por `base` na direção do eixo travado. */
export function projetarNoEixo(base, p, eixo) {
  if (!eixo) return p;
  const d = EIXOS[eixo] ? EIXOS[eixo].vetor : eixo;
  const k = dot(sub(p, base), d) / (dot(d, d) || 1);
  return add(base, mul(d, k));
}

/** Eixo do mundo mais próximo da direção dada, se estiver bem alinhado. */
export function eixoInferido(v, tol = 0.999) {
  const u = normalizar(v);
  for (const k of ['x', 'y', 'z']) {
    if (Math.abs(dot(u, EIXOS[k].vetor)) > tol) return k;
  }
  return null;
}

// --------------------------------------------------------------- prévias

export const CORES = {
  desenho: 0x0b3d91,
  guia: 0x8a94a6,
  face: 0x4a90d9,
  aviso: 0xc0392b,
  ok: 0x2e8b57,
  cota: 0xb8860b,
  estrutura: 0x4b5563,
};

function materialLinha(cor, tracejada) {
  return tracejada
    ? new THREE.LineDashedMaterial({ color: cor, dashSize: 60, gapSize: 40,
                                     depthTest: false, transparent: true })
    : new THREE.LineBasicMaterial({ color: cor, depthTest: false, transparent: true });
}

/** Polilinha de prévia. `fechada` liga o último ponto ao primeiro. */
export function gLinha(pontos, cor = CORES.desenho, { fechada = false, tracejada = false } = {}) {
  const lista = pontos.map(tresJS);
  if (fechada && lista.length > 2) lista.push(lista[0].clone());
  const geo = new THREE.BufferGeometry().setFromPoints(lista);
  const obj = new THREE.Line(geo, materialLinha(cor, tracejada));
  if (tracejada) obj.computeLineDistances();
  obj.renderOrder = 990;
  return obj;
}

/** Face de prévia, semitransparente, a partir de um contorno fechado. */
export function gPoligono(pontos, cor = CORES.face, opacidade = 0.28) {
  if (pontos.length < 3) return new THREE.Group();
  const pos = [];
  for (let i = 1; i < pontos.length - 1; i++) {
    pos.push(...pontos[0], ...pontos[i], ...pontos[i + 1]);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.computeVertexNormals();
  const mat = new THREE.MeshBasicMaterial({ color: cor, transparent: true,
                                            opacity: opacidade, side: THREE.DoubleSide,
                                            depthWrite: false });
  const obj = new THREE.Mesh(geo, mat);
  obj.renderOrder = 980;
  return obj;
}

/** Malha de prévia a partir de vértices e faces (faces com n lados). */
export function gMalha(vertices, faces, cor = CORES.face, opacidade = 0.35) {
  const pos = [];
  for (const f of faces) {
    for (let i = 1; i < f.length - 1; i++) {
      pos.push(...vertices[f[0]], ...vertices[f[i]], ...vertices[f[i + 1]]);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.computeVertexNormals();
  const g = new THREE.Group();
  g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: cor, transparent: true, opacity: opacidade, side: THREE.DoubleSide,
    depthWrite: false })));
  for (const f of faces) g.add(gLinha(f.map(i => vertices[i]), cor, { fechada: true }));
  g.renderOrder = 980;
  return g;
}

/** Marcador de ponto, sempre do mesmo tamanho na tela. */
export function gPonto(p, cor = CORES.desenho) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute([p[0], p[1], p[2]], 3));
  const obj = new THREE.Points(geo, new THREE.PointsMaterial({
    color: cor, size: 7, sizeAttenuation: false, depthTest: false, transparent: true }));
  obj.renderOrder = 995;
  return obj;
}

/**
 * Rótulo de texto na cena. Usa sprite sem atenuação de tamanho, para ficar
 * legível a qualquer distância — o modelo está em milímetros e a escala varia muito.
 */
export function gRotulo(texto, posicao, cor = '#0b3d91', fundo = 'rgba(255,255,255,0.88)') {
  const escala = 2;
  const cv = document.createElement('canvas');
  const ctx = cv.getContext('2d');
  const fonte = `${13 * escala}px system-ui, "Segoe UI", sans-serif`;
  ctx.font = fonte;
  const larg = Math.ceil(ctx.measureText(texto).width) + 14 * escala;
  const alt = 20 * escala;
  cv.width = Math.max(2, larg); cv.height = alt;
  const c2 = cv.getContext('2d');
  c2.font = fonte;
  c2.fillStyle = fundo;
  c2.fillRect(0, 0, cv.width, cv.height);
  c2.strokeStyle = 'rgba(0,0,0,0.18)';
  c2.lineWidth = 1 * escala;
  c2.strokeRect(0.5, 0.5, cv.width - 1, cv.height - 1);
  c2.fillStyle = cor;
  c2.textBaseline = 'middle';
  c2.fillText(texto, 7 * escala, alt / 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false,
                                                         transparent: true,
                                                         sizeAttenuation: false }));
  const h = 0.018;                // cerca de 22 px de altura na tela
  sp.scale.set(h * (cv.width / cv.height), h, 1);
  sp.position.set(posicao[0], posicao[1], posicao[2]);
  sp.renderOrder = 999;
  return sp;
}

/** Grupo de prévia pronto para entregar ao núcleo. */
export function grupo(...filhos) {
  const g = new THREE.Group();
  for (const f of filhos) if (f) g.add(f);
  return g;
}

// --------------------------------------------------------------- contornos

/** Área assinada de um contorno 2D: positiva quando anti-horário. */
export function areaAssinada(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return s / 2;
}

/** Normal de um polígono 3D pelo método de Newell. */
export function normalDoContorno(pts) {
  let n = [0, 0, 0];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    n = add(n, [(a[1] - b[1]) * (a[2] + b[2]),
                (a[2] - b[2]) * (a[0] + b[0]),
                (a[0] - b[0]) * (a[1] + b[1])]);
  }
  return normalizar(n);
}

export function normalDaFace(solido, iFace) {
  const f = solido.faces[iFace] || [];
  return normalDoContorno(f.map(i => solido.vertices[i]));
}

/** Offset de um contorno 2D fechado, com junta em esquadria limitada. */
export function offsetContorno(pts, d) {
  const n = pts.length;
  if (n < 3 || Math.abs(d) < 1e-9) return pts.map(p => p.slice());
  // sinal: positivo sempre "para fora", independente do sentido do contorno
  const s = areaAssinada(pts) >= 0 ? 1 : -1;
  const dd = d * s;
  const saida = [];
  for (let i = 0; i < n; i++) {
    const a = pts[(i - 1 + n) % n], b = pts[i], c = pts[(i + 1) % n];
    const e1 = [b[0] - a[0], b[1] - a[1]], e2 = [c[0] - b[0], c[1] - b[1]];
    const l1 = Math.hypot(e1[0], e1[1]) || 1, l2 = Math.hypot(e2[0], e2[1]) || 1;
    const n1 = [e1[1] / l1, -e1[0] / l1], n2 = [e2[1] / l2, -e2[0] / l2];
    let bis = [n1[0] + n2[0], n1[1] + n2[1]];
    const lb = Math.hypot(bis[0], bis[1]);
    if (lb < 1e-9) { saida.push([b[0] + n1[0] * dd, b[1] + n1[1] * dd]); continue; }
    bis = [bis[0] / lb, bis[1] / lb];
    const cosm = bis[0] * n1[0] + bis[1] * n1[1];
    const k = Math.min(Math.abs(dd) / Math.max(cosm, 0.2), Math.abs(dd) * 5) * Math.sign(dd || 1);
    saida.push([b[0] + bis[0] * k, b[1] + bis[1] * k]);
  }
  return saida;
}

/** Ponto dentro de um polígono 2D? (par-ímpar) */
export function dentroDoContorno(pts, p) {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i], b = pts[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) &&
        p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1] + 1e-12) + a[0]) dentro = !dentro;
  }
  return dentro;
}

// --------------------------------------------------------------- sólidos

/** Sólido plano (uma face) a partir de um contorno 3D fechado. */
export function solidoDeContorno(pts, extra = {}) {
  const vertices = pts.map(copiar);
  const idx = vertices.map((_, i) => i);
  return {
    tipo: 'solido', id: novoId('s'), nome: '', camada: 'Estrutura',
    vertices, faces: [idx],
    arestas_vivas: idx.map((a, i) => [a, idx[(i + 1) % idx.length]]),
    atributos: {}, ...extra,
  };
}

/** Sólido só de arestas (polilinha aberta ou linha de construção). */
export function solidoDeArestas(pts, extra = {}) {
  const vertices = pts.map(copiar);
  const arestas = [];
  for (let i = 0; i < vertices.length - 1; i++) arestas.push([i, i + 1]);
  return {
    tipo: 'solido', id: novoId('s'), nome: '', camada: 'Estrutura',
    vertices, faces: [], arestas_vivas: arestas, atributos: {}, ...extra,
  };
}

/** Extrusão de um contorno 3D numa direção: devolve {vertices, faces}. */
export function extrudarContorno(pts, direcao, altura) {
  const n = normalDoContorno(pts);
  const d = mul(normalizar(direcao), altura);
  // garante que a tampa de baixo fique com a normal para fora
  const paraCima = dot(d, n) >= 0;
  const base = paraCima ? pts.slice() : pts.slice().reverse();
  const k = base.length;
  const vertices = base.map(copiar).concat(base.map(p => add(p, d)));
  const faces = [base.map((_, i) => k - 1 - i), base.map((_, i) => k + i)];
  for (let i = 0; i < k; i++) {
    const a = i, b = (i + 1) % k;
    faces.push([a, b, k + b, k + a]);
  }
  return { vertices, faces };
}

/** Push/pull: cria volume a partir da face `iFace`, mantendo o resto do sólido. */
export function extrudarFace(solido, iFace, distancia) {
  const verts = solido.vertices.map(copiar);
  const faces = solido.faces.map(f => f.slice());
  const face = faces[iFace];
  const n = normalDoContorno(face.map(i => verts[i]));
  const d = mul(n, distancia);
  const novos = face.map(i => { verts.push(add(verts[i], d)); return verts.length - 1; });
  const laterais = [];
  for (let i = 0; i < face.length; i++) {
    const a = face[i], b = face[(i + 1) % face.length];
    const a2 = novos[i], b2 = novos[(i + 1) % face.length];
    laterais.push(distancia >= 0 ? [a, b, b2, a2] : [a, a2, b2, b]);
  }
  faces[iFace] = face.slice().reverse();              // tampa de trás
  faces.push(novos.slice(), ...laterais);             // tampa nova e laterais
  return { vertices: verts, faces };
}

/** Push/pull sobre sólido fechado: move os vértices da face na direção da normal. */
export function moverFace(solido, iFace, distancia) {
  const face = solido.faces[iFace] || [];
  const n = normalDoContorno(face.map(i => solido.vertices[i]));
  const d = mul(n, distancia);
  const alvo = new Set(face);
  const vertices = solido.vertices.map((v, i) => alvo.has(i) ? add(v, d) : copiar(v));
  return { vertices, faces: solido.faces.map(f => f.slice()) };
}

/**
 * Índice em `solido.faces` a partir do que o núcleo entrega. A seleção devolve o
 * índice do TRIÂNGULO atingido (`faceIndex` do Three.js); a cena tessela cada face
 * em leque, na ordem, com n−2 triângulos. Conferimos que o ponto está no plano da
 * face achada; se não estiver, procuramos a face pelo plano e pela normal.
 */
export function faceDoTriangulo(solido, tri, ponto = null, normal = null) {
  const faces = (solido && solido.faces) || [];
  const vs = solido.vertices || [];
  const noPlanoDaFace = (k) => {
    const pts = (faces[k] || []).map(i => vs[i]).filter(Boolean);
    if (pts.length < 3 || !ponto) return pts.length >= 3;
    return Math.abs(dot(sub(ponto, pts[0]), normalDoContorno(pts))) < 1.0;
  };
  if (tri != null && tri >= 0) {
    let acc = 0;
    for (let k = 0; k < faces.length; k++) {
      const n = Math.max(0, faces[k].length - 2);
      if (tri < acc + n) { if (noPlanoDaFace(k)) return k; break; }
      acc += n;
    }
  }
  if (!ponto) return -1;
  let melhor = -1, menor = Infinity;
  for (let k = 0; k < faces.length; k++) {
    const pts = faces[k].map(i => vs[i]).filter(Boolean);
    if (pts.length < 3) continue;
    const n = normalDoContorno(pts);
    const d = Math.abs(dot(sub(ponto, pts[0]), n));
    const desvio = normal ? (1 - dot(n, normalizar(normal))) * 1000 : 0;
    if (d < 1.0 && d + desvio < menor) { menor = d + desvio; melhor = k; }
  }
  return melhor;
}

/** A face tem vizinhas? Se sim, o sólido já tem volume daquele lado. */
export function faceTemVizinhas(solido, iFace) {
  const face = new Set(solido.faces[iFace] || []);
  return solido.faces.some((f, i) => i !== iFace && f.some(v => face.has(v)));
}

// --------------------------------------------------------------- catálogo

/** Lista de perfis do catálogo do editor, tolerante ao formato. */
export function perfisDoCatalogo(editor) {
  const fontes = [editor && editor.catalogo, editor && editor.cena && editor.cena.catalogo];
  for (const c of fontes) {
    if (!c) continue;
    const bruto = c.perfis instanceof Map ? [...c.perfis.values()]
                : Array.isArray(c.perfis) ? c.perfis : Array.isArray(c) ? c : [];
    const l = bruto.filter(p => p && p.nome);
    if (l.length) return l;
  }
  return [];
}

/** Catálogo de parafusos: o do servidor, quando houver; senão a tabela usual. */
export const PARAFUSOS = [
  { nome: '1/2"', d: 12.7 }, { nome: '5/8"', d: 15.88 }, { nome: '3/4"', d: 19.05 },
  { nome: '7/8"', d: 22.23 }, { nome: '1"', d: 25.4 }, { nome: '1.1/8"', d: 28.58 },
  { nome: '1.1/4"', d: 31.75 }, { nome: 'M12', d: 12 }, { nome: 'M16', d: 16 },
  { nome: 'M20', d: 20 }, { nome: 'M22', d: 22 }, { nome: 'M24', d: 24 },
  { nome: 'M27', d: 27 }, { nome: 'M30', d: 30 },
];

export function parafusosDoCatalogo(editor) {
  const c = editor && editor.catalogo && editor.catalogo.parafusos;
  if (Array.isArray(c) && c.length) {
    return c.map(p => typeof p === 'string' ? { nome: p, d: diametroNominal(p) } : p);
  }
  return PARAFUSOS;
}

function diametroNominal(nome) {
  const achado = PARAFUSOS.find(p => p.nome === nome);
  return achado ? achado.d : 20;
}

/**
 * Contorno aproximado da seção de um perfil, em coordenadas locais (y, z) em mm,
 * para a prévia da ferramenta de barra. Usa a seção que o servidor mandar; se não
 * houver, monta um I a partir de d, bf, tw, tf.
 */
export function secaoDoPerfil(perfil, cena = null, nome = null) {
  // A seção que a cena usa para desenhar a barra, quando disponível: assim a
  // prévia coincide com o que aparece depois de criar.
  const n = nome || (perfil && perfil.nome);
  if (cena && n && typeof cena._secaoDoPerfil === 'function' &&
      (typeof cena.perfil !== 'function' || cena.perfil(n))) {
    try {
      const forma = cena._secaoDoPerfil(n);
      const pts = forma && typeof forma.getPoints === 'function' ? forma.getPoints(24) : null;
      if (pts && pts.length > 2) return pts.map(v => [v.x, v.y]);
    } catch { /* segue com a seção montada aqui */ }
  }
  if (!perfil) return [[-50, -100], [50, -100], [50, 100], [-50, 100]];
  if (Array.isArray(perfil.secao) && perfil.secao.length > 2) {
    return perfil.secao.map(p => Array.isArray(p) ? [p[0], p[1]] : [p.x, p.y]);
  }
  if (perfil.secao && Array.isArray(perfil.secao.contorno)) {
    return perfil.secao.contorno.map(p => Array.isArray(p) ? [p[0], p[1]] : [p.x, p.y]);
  }
  const d = perfil.d || 300, b = perfil.bf || 150;
  const tw = perfil.tw || 7, tf = perfil.tf || 11;
  const h = d / 2, bb = b / 2, w = tw / 2, a = h - tf;
  return [[-bb, -h], [bb, -h], [bb, -a], [w, -a], [w, a], [bb, a],
          [bb, h], [-bb, h], [-bb, a], [-w, a], [-w, -a], [-bb, -a]];
}
