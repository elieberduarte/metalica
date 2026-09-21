// Verificador das ferramentas do editor 3D — roda no navegador.
//
// Confere o contrato estático de toda ferramenta registrada (campos obrigatórios,
// ícone SVG válido, atalho único), a conversão das medidas digitadas e, com um
// editor de mentira montado sobre o Documento e a Pilha reais do núcleo, o
// comportamento de cada ferramenta: o que ela cria no documento, a prévia, a dica,
// a caixa de medidas, o desfazer e o Esc duplo.
//
// Como rodar: sirva a pasta `sistema/` por HTTP (módulos ES não carregam por
// file://), por exemplo `python -m http.server 8803` dentro de `sistema/`, e abra
// uma página que contenha
//
//     <div id="saida-ferramentas3d"></div>
//     <script type="module" src="/testes/test_ferramentas3d.js"></script>
//
// O resultado aparece na página (com a galeria de ícones em tamanho real), no
// console e em `window.resultadoFerramentas3d`; o título da página vira
// "OK n/n" ou "FALHOU k/n". Para rodar sob demanda, defina
// `window.FERRAMENTAS3D_MANUAL = true` antes de carregar e chame `verificar()`.

const BASE = new URL('../web/editor3d/ferramentas/', import.meta.url);

const ESPERADAS = ['selecionar', 'linha', 'retangulo', 'circulo', 'poligono', 'arco',
  'pushpull', 'offset', 'mover', 'girar', 'escalar', 'copiar',
  'medir', 'cotar', 'secao', 'barra', 'chapa'];

// Atalhos fixados em GUIA_EDITOR3D.md.
const ATALHOS_DO_CONTRATO = {
  linha: 'L', retangulo: 'R', circulo: 'C', pushpull: 'P', mover: 'M', girar: 'Q',
  escalar: 'E', offset: 'O', medir: 'T', cotar: 'D', secao: 'X', barra: 'B', chapa: 'H',
};

// Teclas globais do editor (vistas e zoom) que nenhuma ferramenta pode tomar.
const RESERVADOS = ['1', '2', '3', '4', '5', '6', '7', 'Z'];

let ultimasFerramentas = [];

// ================================================================ execução

export async function verificar() {
  const itens = [];
  const conferir = (grupo, nome, ok, detalhe = '') =>
    itens.push({ grupo, nome, ok: !!ok, detalhe: detalhe == null ? '' : String(detalhe) });
  const tentar = async (grupo, nome, fn) => {
    try { await fn(); }
    catch (e) { conferir(grupo, `${nome} — exceção`, false, (e && e.stack) || e); }
  };

  // 1. registro --------------------------------------------------------------
  let registro, base;
  try {
    registro = await import(new URL('indice.js', BASE).href);
    base = await import(new URL('base.js', BASE).href);
  } catch (e) {
    conferir('registro', 'indice.js e base.js carregam', false, (e && e.stack) || e);
    return fechar(itens);
  }
  const { ferramentas, falhas } = await registro.carregarFerramentas();
  ultimasFerramentas = ferramentas;
  conferir('registro', 'nenhum arquivo de ferramenta falhou ao carregar', !falhas.length,
           falhas.map(f => `${f.arquivo}: ${f.erro}`).join(' | '));
  const ids = ferramentas.map(F => F.id);
  for (const id of ESPERADAS) conferir('registro', `ferramenta "${id}" registrada`, ids.includes(id));

  // 2. campos estáticos -------------------------------------------------------
  const grupos = new Set((registro.GRUPOS || []).map(g => g[0]));
  for (const F of ferramentas) {
    const g = `ferramenta ${F.id}`;
    conferir(g, 'estende Ferramenta', F.prototype instanceof base.Ferramenta);
    conferir(g, 'id em minúsculas, sem espaços',
             typeof F.id === 'string' && /^[a-z][a-z0-9_-]*$/.test(F.id), F.id);
    conferir(g, 'nome preenchido',
             typeof F.nome === 'string' && F.nome.trim() && F.nome !== 'Ferramenta', F.nome);
    conferir(g, 'atalho preenchido', typeof F.atalho === 'string' && F.atalho.trim(), F.atalho);
    conferir(g, 'grupo válido', grupos.has(F.grupo), F.grupo);
    conferir(g, 'dica preenchida', typeof F.dica === 'string' && F.dica.trim().length > 3, F.dica);
    const svg = validarIcone(F.icone);
    conferir(g, 'ícone SVG válido (24×24, traço 1.5, currentColor)', svg.ok, svg.motivo);
    if (ATALHOS_DO_CONTRATO[F.id]) {
      conferir(g, `atalho do contrato (${ATALHOS_DO_CONTRATO[F.id]})`,
               String(F.atalho || '').toUpperCase() === ATALHOS_DO_CONTRATO[F.id], F.atalho);
    }
  }

  // 3. atalhos únicos ---------------------------------------------------------
  const vistos = new Map();
  let repetidos = 0;
  for (const F of ferramentas) {
    const k = String(F.atalho || '').trim().toUpperCase();
    if (!k) continue;
    if (vistos.has(k)) {
      repetidos++;
      conferir('atalhos', `atalho "${k}" único`, false, `${vistos.get(k)} e ${F.id}`);
    } else vistos.set(k, F.id);
  }
  conferir('atalhos', 'todos os atalhos são únicos', repetidos === 0, [...vistos.keys()].join(' '));
  for (const r of RESERVADOS) {
    conferir('atalhos', `tecla global "${r}" livre`, !vistos.has(r), vistos.get(r) || '');
  }

  // 4. medidas ----------------------------------------------------------------
  const pm = base.paraMilimetros;
  const casos = [['3000', 3000], ['3,5m', 3500], ['350cm', 3500], ['12"', 304.8],
                 ['3.5 m', 3500], ['-200', -200], ['12pol', 304.8], ['25mm', 25],
                 ['abc', NaN], ['', NaN]];
  for (const [t, v] of casos) {
    const r = pm(t);
    conferir('medidas', `paraMilimetros(${JSON.stringify(t)}) = ${v}`,
             Number.isNaN(v) ? Number.isNaN(r) : Math.abs(r - v) < 1e-9, r);
  }
  const lm = base.listaDeMedidas('2000;1000');
  conferir('medidas', 'listaDeMedidas("2000;1000") = [2000, 1000]',
           lm.length === 2 && lm[0] === 2000 && lm[1] === 1000, JSON.stringify(lm));
  conferir('medidas', 'formatar(3500) = "3,50 m"', base.formatar(3500) === '3,50 m', base.formatar(3500));
  conferir('medidas', 'formatar(350) = "350 mm"', base.formatar(350) === '350 mm', base.formatar(350));

  // 5. comportamento ----------------------------------------------------------
  await comportamento(ferramentas, conferir, tentar);

  return fechar(itens);
}

function fechar(itens) {
  const falhas = itens.filter(i => !i.ok);
  const r = { ok: falhas.length === 0, total: itens.length, falhas, itens };
  if (typeof window !== 'undefined') window.resultadoFerramentas3d = r;
  console.info(`Ferramentas 3D: ${itens.length - falhas.length}/${itens.length} verificações passaram.`);
  for (const f of falhas) console.error(`FALHOU [${f.grupo}] ${f.nome}`, f.detalhe);
  return r;
}

// ================================================================ ícones

function validarIcone(texto) {
  const ruim = (motivo) => ({ ok: false, motivo });
  if (typeof texto !== 'string' || !texto.trim().startsWith('<svg')) return ruim('não começa com <svg');
  const fonte = texto.includes('xmlns=') ? texto
              : texto.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
  const doc = new DOMParser().parseFromString(fonte, 'image/svg+xml');
  if (doc.getElementsByTagName('parsererror').length) return ruim('XML inválido');
  const svg = doc.documentElement;
  if (svg.localName !== 'svg') return ruim('raiz não é <svg>');
  const vb = (svg.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
  if (vb.join(',') !== '0,0,24,24') return ruim(`viewBox "${svg.getAttribute('viewBox')}" (esperado 0 0 24 24)`);
  const desenhaveis = [...svg.querySelectorAll('path,line,polyline,polygon,rect,circle,ellipse')];
  if (!desenhaveis.length) return ruim('sem elementos desenháveis');
  const herdado = (el, attr) => {
    for (let e = el; e && e.getAttribute; e = e.parentNode) {
      const v = e.getAttribute(attr);
      if (v != null) return v;
    }
    return null;
  };
  for (const el of desenhaveis) {
    const stroke = herdado(el, 'stroke'), fill = herdado(el, 'fill');
    const sw = herdado(el, 'stroke-width');
    if (stroke && stroke !== 'currentColor' && stroke !== 'none') return ruim(`cor fixa no traço: ${stroke}`);
    if (fill == null) return ruim('sem fill="none": o SVG seria preenchido de preto');
    if (fill !== 'none' && fill !== 'currentColor') return ruim(`preenchimento com cor fixa: ${fill}`);
    if (stroke === 'currentColor' && Number(sw) !== 1.5) return ruim(`traço de ${sw} (esperado 1.5)`);
    if (stroke !== 'currentColor' && fill !== 'currentColor') return ruim(`<${el.localName}> invisível`);
  }
  const caixa = medirIcone(fonte);
  if (caixa && (caixa.x < -0.5 || caixa.y < -0.5 ||
                caixa.x + caixa.width > 24.5 || caixa.y + caixa.height > 24.5)) {
    return ruim(`desenho sai da caixa 24×24 (${[caixa.x, caixa.y, caixa.width, caixa.height].map(v => v.toFixed(1)).join(', ')})`);
  }
  if (caixa && (caixa.width < 8 && caixa.height < 8)) return ruim('desenho pequeno demais para ler');
  return { ok: true, motivo: `${desenhaveis.length} elementos` };
}

function medirIcone(fonte) {
  if (typeof document === 'undefined' || !document.body) return null;
  const div = document.createElement('div');
  div.style.cssText = 'position:absolute;left:-9999px;top:0;width:24px;height:24px';
  div.innerHTML = fonte;
  document.body.appendChild(div);
  try {
    const svg = div.querySelector('svg');
    svg.setAttribute('width', '24'); svg.setAttribute('height', '24');
    const b = svg.getBBox();
    return { x: b.x, y: b.y, width: b.width, height: b.height };
  } catch { return null; }
  finally { div.remove(); }
}

// ================================================================ comportamento

const P = (x, y, z, extra = {}) => ({ ponto: [x, y, z], tela: [0, 0], entidade: null, face: -1,
  aresta: null, tipoSnap: '', normal: [0, 0, 1], ...extra });
const K = (key, extra = {}) => ({ key, type: 'keydown', ...extra });
const perto = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;
const pertoV = (a, b, tol = 1e-6) =>
  !!a && !!b && a.length === b.length && a.every((v, i) => perto(v, b[i], tol));
const ultimo = (doc, tipo) => { const l = doc.porTipo(tipo); return l[l.length - 1]; };

function volume(s) {
  let v = 0;
  for (const f of s.faces) {
    for (let i = 1; i < f.length - 1; i++) {
      const a = s.vertices[f[0]], b = s.vertices[f[i]], c = s.vertices[f[i + 1]];
      v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) +
            a[2] * (b[0] * c[1] - b[1] * c[0])) / 6;
    }
  }
  return Math.abs(v);
}

function areaXY(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return s / 2;
}

const CAIXA_1M = {
  tipo: 'solido', nome: 'Caixa',
  vertices: [[0, 0, 0], [1000, 0, 0], [1000, 1000, 0], [0, 1000, 0],
             [0, 0, 1000], [1000, 0, 1000], [1000, 1000, 1000], [0, 1000, 1000]],
  faces: [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]],
};

/** Editor de mentira: documento e pilha reais, o resto registrando o que recebe. */
function novoEditor(nuc, extras = {}) {
  const doc = new nuc.Documento('Teste');
  const pilha = new nuc.Pilha(doc);
  const sel = new Set();
  const ed = {
    documento: doc, pilha,
    catalogo: { perfis: [
      { nome: 'W 310×38,7', tipo: 'I', d: 310, bf: 165, tw: 5.8, tf: 9.7, massa: 38.7 },
      { nome: 'W 530×85,0', tipo: 'I', d: 535, bf: 166, tw: 10.3, tf: 16.5, massa: 85 },
    ] },
    perfilAtivo: 'W 310×38,7', acoAtivo: 'ASTM A572 Gr.50', papelAtivo: 'pilar',
    selecao: { ids: sel, get entidades() { return [...sel].map(i => doc.get(i)).filter(Boolean); } },
    inferencia: {
      travado: null, ancora: null,
      definirAncora(p) { this.ancora = p ? p.slice(0, 3) : null; },
      limparAncora() { this.ancora = null; this.travado = null; },
      travarEixo(e) { this.travado = e === this.travado ? null : e; return this.travado; },
      destravar() { this.travado = null; },
    },
    cena: { planos: [], definirPlanoCorte(p) { this.planos.push(p); }, raiz: { scale: { x: 0.001 } } },
    previaAtual: null, nPrevias: 0, textoDica: '', textoMedida: '', pedida: null,
    executar(cmd) { return pilha.executar(cmd); },
    desfazer() { return pilha.desfazer(); },
    previa(o) { this.previaAtual = o; this.nPrevias++; return o; },
    limparPrevia() { this.previaAtual = null; },
    dica(t) { this.textoDica = String(t); },
    medida(t) { this.textoMedida = String(t); },
    usarFerramenta(id) { this.pedida = id; },
    ...extras,
  };
  return ed;
}

function usar(ed, F) { const f = new F(ed); f.ativar(ed); return f; }

async function comportamento(ferramentas, conferir, tentar) {
  let nuc;
  try {
    const [d, c] = await Promise.all([
      import(new URL('../nucleo/documento.js', BASE).href),
      import(new URL('../nucleo/comandos.js', BASE).href)]);
    nuc = { ...d, ...c };
  } catch (e) {
    conferir('comportamento', 'núcleo (documento.js e comandos.js) carrega', false, (e && e.stack) || e);
    return;
  }
  const porId = Object.fromEntries(ferramentas.map(F => [F.id, F]));
  const G = (id) => { if (!porId[id]) throw new Error(`ferramenta ${id} ausente`); return porId[id]; };
  const adicionar = (ed, reg) => { ed.executar(new nuc.ComandoAdicionar({ ...reg })); return ultimo(ed.documento, reg.tipo); };
  const retangulo = (ed, u = 2000, v = 1000) => {
    const r = usar(ed, G('retangulo'));
    r.onPonto(P(0, 0, 0)); r.onMover(P(10, 10, 0)); r.onValor(`${u};${v}`); r.desativar();
    return ultimo(ed.documento, 'solido');
  };

  // ---- ciclo de vida de todas as ferramentas (menos selecionar, do núcleo)
  for (const F of ferramentas) {
    if (F.id === 'selecionar') continue;
    const g = `ciclo ${F.id}`;
    await tentar(g, 'ativar/mover/Esc/Esc/desativar', () => {
      if ('ultimo' in F) F.ultimo = null;
      const ed = novoEditor(nuc);
      const f = usar(ed, F);
      conferir(g, 'ativar escreve a dica', ed.textoDica.length > 0, ed.textoDica);
      f.onMover(P(100, 100, 0));
      conferir(g, 'tecla solta (keyup) não é consumida', !f.onTecla({ key: 'Enter', type: 'keyup' }));
      f.cancelar(); f.cancelar();
      conferir(g, 'Esc duplo volta para Selecionar', ed.pedida === 'selecionar', ed.pedida);
      f.desativar();
      conferir(g, 'desativar deixa a prévia limpa', ed.previaAtual === null);
    });
  }

  // ---- linha
  await tentar('linha', 'contorno fechado', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('linha'));
    f.onMover(P(0, 0, 0)); f.onPonto(P(0, 0, 0));
    conferir('linha', 'dica muda depois do primeiro ponto', /próximo ponto/i.test(ed.textoDica), ed.textoDica);
    conferir('linha', 'inferência ancorada no primeiro ponto', pertoV(ed.inferencia.ancora, [0, 0, 0]));
    f.onMover(P(1000, 0, 0));
    conferir('linha', 'caixa de medidas mostra o comprimento', ed.textoMedida.includes('1,00 m'), ed.textoMedida);
    conferir('linha', 'prévia durante o traçado', ed.previaAtual !== null);
    f.onPonto(P(1000, 0, 0)); f.onPonto(P(1000, 1000, 0)); f.onPonto(P(0, 0, 0));
    const s = ed.documento.porTipo('solido');
    conferir('linha', 'contorno fechado vira face', s.length === 1 && s[0].faces.length === 1 &&
             s[0].faces[0].length === 3, JSON.stringify(s[0] && s[0].faces));
    conferir('linha', 'prévia limpa e âncora solta ao fechar',
             ed.previaAtual === null && ed.inferencia.ancora === null);
  });
  await tentar('linha', 'medida digitada e eixo travado', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('linha'));
    f.onPonto(P(0, 0, 0));
    conferir('linha', '↑ trava Z na ferramenta e na inferência',
             f.onTecla(K('ArrowUp')) && ed.inferencia.travado === 'z', ed.inferencia.travado);
    f.onMover(P(300, 200, 1500)); f.onValor('3,5m'); f.onTecla(K('Enter'));
    const s = ultimo(ed.documento, 'solido');
    conferir('linha', '"3,5m" no eixo Z dá o ponto (0, 0, 3500)', s && pertoV(s.vertices[1], [0, 0, 3500]),
             s && JSON.stringify(s.vertices));
    conferir('linha', 'Enter encerra como polilinha (arestas, sem face)',
             s && s.faces.length === 0 && s.arestas_vivas.length === 1);
    const ed2 = novoEditor(nuc); const f2 = usar(ed2, G('linha'));
    f2.onPonto(P(0, 0, 0)); f2.cancelar();
    conferir('linha', 'Esc no meio cancela só o passo', ed2.pedida === null && ed2.previaAtual === null &&
             ed2.documento.tamanho === 0);
  });

  // ---- retângulo
  await tentar('retangulo', '2000;1000', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('retangulo'));
    f.onPonto(P(0, 0, 0));
    conferir('retangulo', 'dica pede o canto oposto ou a medida', /canto oposto/i.test(ed.textoDica), ed.textoDica);
    f.onMover(P(500, 300, 0));
    conferir('retangulo', 'caixa de medidas mostra os dois lados', ed.textoMedida.includes(';'), ed.textoMedida);
    f.onValor('2000;1000');
    const s = ultimo(ed.documento, 'solido');
    conferir('retangulo', 'quatro vértices, uma face', s && s.vertices.length === 4 && s.faces.length === 1);
    conferir('retangulo', 'área 2 m² e contorno anti-horário (normal +Z)',
             s && perto(areaXY(s.faces[0].map(i => s.vertices[i])), 2e6), s && areaXY(s.vertices));
    const f2 = usar(ed, G('retangulo'));
    f2.onPonto(P(0, 0, 0)); f2.onMover(P(-50, -50, 0)); f2.onValor('2000;1000');
    const s2 = ultimo(ed.documento, 'solido');
    conferir('retangulo', 'para o lado negativo continua anti-horário',
             s2 && perto(areaXY(s2.faces[0].map(i => s2.vertices[i])), 2e6));
  });

  // ---- círculo
  await tentar('circulo', 'raio e lados', () => {
    const F = G('circulo'); const antes = F.lados;
    const ed = novoEditor(nuc); const f = usar(ed, F);
    f.onValor('12s'); f.onPonto(P(0, 0, 0)); f.onMover(P(100, 0, 0));
    conferir('circulo', 'caixa de medidas mostra raio e lados', /raio/.test(ed.textoMedida) && /12 lados/.test(ed.textoMedida), ed.textoMedida);
    f.onValor('500');
    const s = ultimo(ed.documento, 'solido');
    conferir('circulo', '"12s" dá 12 lados', s && s.vertices.length === 12, s && s.vertices.length);
    conferir('circulo', 'raio digitado 500', s && s.vertices.every(v => perto(Math.hypot(v[0], v[1]), 500, 1e-6)));
    F.lados = antes;
  });

  // ---- polígono
  await tentar('poligono', 'inscrito e circunscrito', () => {
    const F = G('poligono'); const antes = [F.lados, F.circunscrito];
    const ed = novoEditor(nuc); const f = usar(ed, F);
    f.onPonto(P(0, 0, 0)); f.onValor('300');
    const s = ultimo(ed.documento, 'solido');
    conferir('poligono', 'hexágono inscrito: vértices a 300', s && s.vertices.length === 6 &&
             s.vertices.every(v => perto(Math.hypot(v[0], v[1]), 300, 1e-6)));
    f.onTecla(K('Tab')); f.onPonto(P(0, 0, 0)); f.onValor('300');
    const s2 = ultimo(ed.documento, 'solido');
    conferir('poligono', 'circunscrito: apótema 300', s2 && s2.vertices.every(v =>
             perto(Math.hypot(v[0], v[1]), 300 / Math.cos(Math.PI / 6), 1e-6)));
    F.lados = antes[0]; F.circunscrito = antes[1];
  });

  // ---- arco
  await tentar('arco', 'três pontos', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('arco'));
    f.onPonto(P(0, 0, 0)); f.onMover(P(2000, 0, 0)); f.onPonto(P(2000, 0, 0));
    conferir('arco', 'dica pede o bojo', /bojo/i.test(ed.textoDica), ed.textoDica);
    f.onMover(P(1000, 400, 0)); f.onValor('500');
    const s = ultimo(ed.documento, 'solido');
    conferir('arco', '12 segmentos (13 pontos)', s && s.vertices.length === 13, s && s.vertices.length);
    conferir('arco', 'flecha 500 no meio da corda', s && pertoV(s.vertices[6], [1000, 500, 0], 1e-3),
             s && JSON.stringify(s.vertices[6]));
    conferir('arco', 'extremidades nos cliques', s && pertoV(s.vertices[0], [0, 0, 0], 1e-6) &&
             pertoV(s.vertices[12], [2000, 0, 0], 1e-6));
  });

  // ---- push/pull
  await tentar('pushpull', 'extrusão, mover face, repetir, Ctrl', () => {
    const ed = novoEditor(nuc);
    const id = retangulo(ed).id;
    const f = usar(ed, G('pushpull'));
    const naFace = (z, tri) => P(1000, 500, z, { entidade: id, face: tri, tipoSnap: 'sobre_face' });
    f.onMover(naFace(0, 1));
    conferir('pushpull', 'destaca a face apontada', ed.previaAtual !== null);
    f.onPonto(naFace(0, 1)); f.onMover(P(1000, 500, 800));
    conferir('pushpull', 'caixa de medidas mostra a distância', ed.textoMedida.includes('800'), ed.textoMedida);
    f.onValor('3000');
    let s = ed.documento.get(id);
    conferir('pushpull', 'face solta vira prisma de 6 faces', s.faces.length === 6, s.faces.length);
    conferir('pushpull', 'volume 2 × 1 × 3 m', perto(volume(s), 6e9, 1), volume(s));
    // a tampa nova é faces[1]; a face 0 tem 2 triângulos, então os da tampa são 2 e 3
    f.onPonto(naFace(3000, 3)); f.onValor('1000');
    s = ed.documento.get(id);
    conferir('pushpull', 'índice de triângulo → face certa; sólido fechado estica',
             s.faces.length === 6 && perto(volume(s), 8e9, 1), `${s.faces.length} faces, V=${volume(s)}`);
    ed.desfazer();
    conferir('pushpull', 'desfazer volta ao volume anterior', perto(volume(ed.documento.get(id)), 6e9, 1));
    f.onDuploClique(naFace(3000, 3));
    conferir('pushpull', 'duplo clique repete a última distância', perto(volume(ed.documento.get(id)), 8e9, 1));
    const ed2 = novoEditor(nuc);
    const id2 = retangulo(ed2).id;
    const f2 = usar(ed2, G('pushpull'));
    f2.onPonto(P(1000, 500, 0, { entidade: id2, face: 0, tipoSnap: 'sobre_face' }));
    f2.onMover(P(1000, 500, -1e-9, { tipoSnap: 'sobre_aresta' }));
    f2.onValor('1000');
    conferir('pushpull', 'distância ~0 antes de digitar não inverte o sentido',
             Math.max(...ed2.documento.get(id2).vertices.map(v => v[2])) === 1000);
    f.onPonto(naFace(4000, 3), { ctrlKey: true }); f.onValor('500');
    s = ed.documento.get(id);
    conferir('pushpull', 'Ctrl inicia face nova (+5 faces)', s.faces.length === 11 &&
             Math.max(...s.vertices.map(v => v[2])) === 4500, s.faces.length);
  });

  // ---- offset
  await tentar('offset', 'para fora e para dentro', () => {
    const ed = novoEditor(nuc);
    const id = retangulo(ed).id;
    const f = usar(ed, G('offset'));
    const naFace = P(1000, 500, 0, { entidade: id, face: 0, tipoSnap: 'sobre_face' });
    f.onPonto(naFace); f.onMover(P(2100, 500, 0));
    conferir('offset', 'medida indica "para fora"', /para fora/.test(ed.textoMedida), ed.textoMedida);
    f.onValor('100');
    let s = ultimo(ed.documento, 'solido');
    conferir('offset', '100 para fora: 2,2 × 1,2 m', perto(Math.abs(areaXY(s.vertices)), 2200 * 1200, 1e-3), areaXY(s.vertices));
    f.onPonto(naFace); f.onMover(P(1000, 450, 0)); f.onValor('100');
    s = ultimo(ed.documento, 'solido');
    conferir('offset', '100 para dentro: 1,8 × 0,8 m', perto(Math.abs(areaXY(s.vertices)), 1800 * 800, 1e-3), areaXY(s.vertices));
  });

  // ---- mover
  await tentar('mover', 'mover, copiar, *4, /2, desfazer', () => {
    const ed = novoEditor(nuc);
    const b = adicionar(ed, { tipo: 'barra', inicio: [0, 0, 0], fim: [0, 0, 6000], perfil: 'W 310×38,7' });
    ed.selecao.ids.add(b.id);
    const f = usar(ed, G('mover'));
    f.onPonto(P(0, 0, 0)); f.onMover(P(700, 0, 0));
    conferir('mover', 'caixa de medidas mostra o deslocamento', ed.textoMedida.includes('700'), ed.textoMedida);
    f.onValor('1000');
    conferir('mover', 'move 1000 em X', pertoV(ed.documento.get(b.id).inicio, [1000, 0, 0]));
    f.onPonto(P(0, 0, 0), { ctrlKey: true }); f.onMover(P(0, 500, 0)); f.onValor('2000');
    conferir('mover', 'Ctrl copia', ed.documento.barras.length === 2);
    f.onValor('*4');
    const ys = () => ed.documento.barras.map(x => x.inicio[1]).sort((a, c) => a - c);
    conferir('mover', '"*4" faz 4 cópias espaçadas de 2 m', ed.documento.barras.length === 5 &&
             pertoV(ys(), [0, 2000, 4000, 6000, 8000]), JSON.stringify(ys()));
    f.onValor('/2');
    conferir('mover', '"/2" divide o deslocamento em 2', ed.documento.barras.length === 3 &&
             pertoV(ys(), [0, 1000, 2000]), JSON.stringify(ys()));
    ed.desfazer();
    conferir('mover', 'um desfazer apaga o array inteiro', ed.documento.barras.length === 1);
    ed.desfazer();
    conferir('mover', 'outro desfazer devolve a posição', pertoV(ed.documento.get(b.id).inicio, [0, 0, 0]));
  });

  // ---- girar
  await tentar('girar', 'ângulo, cópia e array radial', () => {
    const ed = novoEditor(nuc);
    const b = adicionar(ed, { tipo: 'barra', inicio: [1000, 0, 0], fim: [1000, 0, 6000] });
    ed.selecao.ids.add(b.id);
    const f = usar(ed, G('girar'));
    f.onPonto(P(0, 0, 0));
    conferir('girar', 'dica pede a referência', /referência/i.test(ed.textoDica), ed.textoDica);
    f.onPonto(P(1000, 0, 0)); f.onMover(P(0, 1000, 0));
    conferir('girar', 'caixa de medidas mostra 90°', ed.textoMedida.includes('90'), ed.textoMedida);
    f.onValor('90');
    const e = ed.documento.get(b.id);
    conferir('girar', '90° em torno de Z', pertoV(e.inicio, [0, 1000, 0], 1e-6) &&
             pertoV(e.fim, [0, 1000, 6000], 1e-6), JSON.stringify(e.inicio));
    f.onPonto(P(0, 0, 0), { ctrlKey: true }); f.onPonto(P(0, 1000, 0)); f.onValor('90');
    conferir('girar', 'Ctrl copia girando', ed.documento.barras.length === 2);
    f.onValor('*3');
    conferir('girar', '"*3" faz o array radial', ed.documento.barras.length === 4, ed.documento.barras.length);
    f.onPonto(P(0, 0, 0));
    conferir('girar', 'depois do array, o próximo clique é um centro novo', /referência/i.test(ed.textoDica), ed.textoDica);
  });

  // ---- escalar
  await tentar('escalar', 'fator uniforme, por eixo e medida', () => {
    const ed = novoEditor(nuc);
    const s0 = adicionar(ed, CAIXA_1M);
    ed.selecao.ids.add(s0.id);
    const f = usar(ed, G('escalar'));
    conferir('escalar', 'alças aparecem ao ativar', ed.previaAtual !== null);
    f.onPonto(P(1000, 1000, 1000)); f.onValor('2');
    let s = ed.documento.get(s0.id);
    conferir('escalar', 'canto: fator 2 uniforme (volume × 8)', perto(volume(s), 8e9, 1), volume(s));
    f.onPonto(P(2000, 1000, 1000)); f.onValor('1,5');
    s = ed.documento.get(s0.id);
    conferir('escalar', 'meio da face X: fator só em X', perto(Math.max(...s.vertices.map(v => v[0])), 3000, 1e-6) &&
             perto(Math.max(...s.vertices.map(v => v[1])), 2000, 1e-6));
    f.onPonto(P(1500, 2000, 1000)); f.onValor('5m');
    s = ed.documento.get(s0.id);
    conferir('escalar', 'medida com unidade vira tamanho final (Y = 5 m)',
             perto(Math.max(...s.vertices.map(v => v[1])), 5000, 1e-6));
  });

  // ---- copiar
  await tentar('copiar', 'copiar e colar posicionado', () => {
    const ed = novoEditor(nuc);
    const s0 = adicionar(ed, CAIXA_1M);
    ed.selecao.ids.add(s0.id);
    const f = usar(ed, G('copiar'));
    conferir('copiar', 'dica confirma o que foi copiado', /1 entidade/.test(ed.textoDica), ed.textoDica);
    f.onMover(P(5000, 0, 0));
    conferir('copiar', 'fantasma da cópia na prévia', ed.previaAtual !== null);
    f.onPonto(P(5000, 0, 0)); f.onPonto(P(0, 5000, 0)); f.onValor('0;0;3000');
    const l = ed.documento.solidos;
    const minimos = l.map(s => [0, 1, 2].map(i => Math.min(...s.vertices.map(v => v[i]))));
    conferir('copiar', 'três colagens nos pontos pedidos', l.length === 4 &&
             minimos.some(m => pertoV(m, [5000, 0, 0])) && minimos.some(m => pertoV(m, [0, 5000, 0])) &&
             minimos.some(m => pertoV(m, [0, 0, 3000])), JSON.stringify(minimos));
    ed.selecao.ids.clear();
    usar(ed, G('copiar')).onPonto(P(9000, 0, 0));
    conferir('copiar', 'sem seleção, cola o que está na área de transferência', ed.documento.solidos.length === 5);
  });

  // ---- medir
  await tentar('medir', 'distância e linha de construção', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('medir'));
    f.onPonto(P(0, 0, 0)); f.onMover(P(3000, 4000, 0));
    conferir('medir', 'distância e projeções', ed.textoMedida.includes('5,00 m') &&
             ed.textoMedida.includes('ΔX 3,00 m') && ed.textoMedida.includes('ΔY 4,00 m'), ed.textoMedida);
    f.onPonto(P(3000, 4000, 0));
    conferir('medir', 'dica oferece a linha de construção', /Enter/.test(ed.textoDica), ed.textoDica);
    f.onTecla(K('Enter'));
    const s = ultimo(ed.documento, 'solido');
    conferir('medir', 'Enter cria guia (atributos.tipo = construcao, camada Referência)', s &&
             s.atributos.tipo === 'construcao' && s.camada === 'Referência' && s.vertices.length === 2);
  });

  // ---- cotar
  await tentar('cotar', 'cota permanente', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('cotar'));
    f.onPonto(P(0, 0, 0)); f.onPonto(P(2000, 0, 0)); f.onMover(P(1000, 300, 0));
    conferir('cotar', 'caixa de medidas mostra a cota', ed.textoMedida.includes('2,00 m'), ed.textoMedida);
    f.onValor('500');
    const s = ultimo(ed.documento, 'solido');
    conferir('cotar', 'vira Sólido com atributos.tipo = cota', s && s.atributos.tipo === 'cota' &&
             s.atributos.cota.texto === '2,00 m' && s.camada === 'Referência');
    conferir('cotar', 'linha de cota afastada 500', s && perto(Math.abs(s.vertices[2][1]), 500, 1e-6),
             s && JSON.stringify(s.vertices[2]));
  });

  // ---- seção
  await tentar('secao', 'plano por eixo, deslocar, inverter, remover', () => {
    const F = G('secao'); F.ultimo = null;
    const ed = novoEditor(nuc); const f = usar(ed, F);
    f.onTecla(K('z'));
    const pl = ed.cena.planos;
    conferir('secao', 'tecla Z define plano horizontal', pl.length === 1 && pertoV(pl[0].normal, [0, 0, 1]));
    f.onValor('1000');
    conferir('secao', 'medida desloca o plano', pertoV(pl[pl.length - 1].origem, [0, 0, 1000]));
    f.onTecla(K('Tab'));
    conferir('secao', 'Tab inverte o lado', pertoV(pl[pl.length - 1].normal, [0, 0, -1]));
    f.cancelar();
    conferir('secao', 'Esc remove o corte', pl[pl.length - 1] === null);
    F.ultimo = null;
    const r = {};
    const ed2 = novoEditor(nuc, { cena: { raiz: { scale: { x: 0.001 } }, renderizador: r } });
    const f2 = usar(ed2, F);
    f2.onTecla(K('z')); f2.onValor('2000');
    const pc = r.clippingPlanes && r.clippingPlanes[0];
    conferir('secao', 'sem definirPlanoCorte: clipping do renderizador, em metros',
             r.localClippingEnabled === true && r.clippingPlanes.length === 1 && pc &&
             perto(pc.constant, -2, 1e-9), pc && pc.constant);
    // O Three.js corta onde n·p + c < 0. Com a normal +Z em z = 2 m, o que está acima
    // (lado da normal, para onde a seta aponta) fica; o que está abaixo some.
    conferir('secao', 'reserva mantém o lado da normal, como a seta e o núcleo',
             pc && pc.distanceToPoint({ x: 0, y: 0, z: 3 }) > 0 && pc.distanceToPoint({ x: 0, y: 0, z: 1 }) < 0,
             pc && `z=3 m: ${pc.distanceToPoint({ x: 0, y: 0, z: 3 })}, z=1 m: ${pc.distanceToPoint({ x: 0, y: 0, z: 1 })}`);
    F.ultimo = null;
  });

  // ---- barra
  await tentar('barra', 'pórtico encadeado e troca de perfil', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('barra'));
    conferir('barra', 'dica mostra o perfil ativo', ed.textoDica.includes('W 310×38,7'), ed.textoDica);
    f.onPonto(P(0, 0, 0)); f.onMover(P(0, 0, 100));
    conferir('barra', 'seção em prévia durante o traçado', ed.previaAtual !== null &&
             ed.previaAtual.children.length > 4, ed.previaAtual && ed.previaAtual.children.length);
    conferir('barra', 'caixa de medidas mostra comprimento e perfil', ed.textoMedida.includes('W 310×38,7'), ed.textoMedida);
    f.onValor('6000');
    const b1 = ultimo(ed.documento, 'barra');
    conferir('barra', 'comprimento digitado: pilar de 6 m', b1 && pertoV(b1.fim, [0, 0, 6000]) &&
             b1.perfil === 'W 310×38,7' && b1.papel === 'pilar' && b1.aco === 'ASTM A572 Gr.50');
    f.onTecla(K('ArrowUp'));
    conferir('barra', '↑ troca o perfil', ed.perfilAtivo === 'W 530×85,0', ed.perfilAtivo);
    ed.papelAtivo = 'viga';
    f.onMover(P(10000, 0, 6000)); f.onPonto(P(10000, 0, 6000));
    const b2 = ultimo(ed.documento, 'barra');
    conferir('barra', 'continua do ponto final, com o perfil novo', ed.documento.barras.length === 2 &&
             pertoV(b2.inicio, [0, 0, 6000]) && b2.perfil === 'W 530×85,0' && b2.papel === 'viga');
    f.cancelar();
    conferir('barra', 'primeiro Esc para a sequência sem sair', ed.pedida === null);
    f.cancelar();
    conferir('barra', 'segundo Esc sai', ed.pedida === 'selecionar');
    ed.desfazer();
    conferir('barra', 'desfazer apaga a última barra', ed.documento.barras.length === 1);
  });

  // ---- chapa
  await tentar('chapa', 'contorno, espessura e furos', () => {
    const ed = novoEditor(nuc); const f = usar(ed, G('chapa'));
    f.onPonto(P(0, 0, 0)); f.onPonto(P(300, 0, 0)); f.onPonto(P(300, 500, 0)); f.onPonto(P(0, 500, 0));
    f.onTecla(K('Enter'));
    conferir('chapa', 'Enter fecha e pede a espessura', /Espessura/i.test(ed.textoDica), ed.textoDica);
    f.onValor('16');
    const c = ultimo(ed.documento, 'chapa');
    conferir('chapa', 'Chapa paramétrica de 16 mm, 300 × 500', c && c.espessura === 16 &&
             c.contorno.length === 4 && perto(nuc.areaDaChapa(c), 150000, 1e-6) &&
             pertoV(c.eixo_x, [1, 0, 0]) && c.camada === 'Chapas');
    f.onMover(P(150, 100, 0));
    conferir('chapa', 'prévia do furo com o diâmetro', /furo/.test(ed.textoMedida), ed.textoMedida);
    f.onPonto(P(150, 100, 0));
    let furos = ed.documento.get(c.id).furos;
    conferir('chapa', 'furo padrão 3/4" = 19,05 + 1,5 mm', furos.length === 1 && perto(furos[0].diametro, 20.55, 1e-9),
             JSON.stringify(furos));
    f.onValor('M20'); f.onPonto(P(150, 400, 0)); f.onPonto(P(1000, 1000, 0));
    furos = ed.documento.get(c.id).furos;
    conferir('chapa', 'troca para M20 e recusa furo fora da chapa', furos.length === 2 &&
             perto(furos[1].diametro, 21.5, 1e-9), JSON.stringify(furos));
    ed.desfazer();
    conferir('chapa', 'desfazer tira o último furo', ed.documento.get(c.id).furos.length === 1);
    f.onTecla(K('Enter'));
    conferir('chapa', 'Enter encerra os furos', ed.textoDica === G('chapa').dica, ed.textoDica);
  });
}

// ================================================================ página

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

export function mostrar(r, ferramentas = ultimasFerramentas) {
  if (typeof document === 'undefined') return;
  document.title = r.ok ? `OK ${r.total}/${r.total}` : `FALHOU ${r.falhas.length}/${r.total}`;
  let alvo = document.getElementById('saida-ferramentas3d');
  if (!alvo) { alvo = document.createElement('div'); alvo.id = 'saida-ferramentas3d'; document.body.appendChild(alvo); }
  const galeria = ferramentas.map(F => `
    <figure>
      <span class="i24">${F.icone || ''}</span><span class="i48">${F.icone || ''}</span>
      <figcaption><b>${esc(F.nome)}</b><kbd>${esc(F.atalho)}</kbd><small>${esc(F.grupo)}</small></figcaption>
    </figure>`).join('');
  const porGrupo = new Map();
  for (const i of r.itens) { if (!porGrupo.has(i.grupo)) porGrupo.set(i.grupo, []); porGrupo.get(i.grupo).push(i); }
  const linhas = [...porGrupo].map(([g, l]) => {
    const ok = l.every(i => i.ok);
    return `<details ${ok ? '' : 'open'}><summary class="${ok ? 'ok' : 'nao'}">${ok ? '✓' : '✗'} ${esc(g)}
      <small>${l.filter(i => i.ok).length}/${l.length}</small></summary><ul>` +
      l.map(i => `<li class="${i.ok ? 'ok' : 'nao'}">${i.ok ? '✓' : '✗'} ${esc(i.nome)}` +
        (i.ok ? '' : `<pre>${esc(i.detalhe)}</pre>`) + '</li>').join('') + '</ul></details>';
  }).join('');
  alvo.innerHTML = `
    <style>
      #saida-ferramentas3d{font:13px/1.45 system-ui,"Segoe UI",sans-serif;color:#1c2836;padding:16px 20px;max-width:1500px}
      #saida-ferramentas3d h1{font-size:18px;margin:0 0 4px;color:#0b3d91}
      #saida-ferramentas3d .resumo{margin:0 0 14px;font-weight:600}
      #saida-ferramentas3d .resumo.nao{color:#c0392b} #saida-ferramentas3d .resumo.ok{color:#2e8b57}
      #saida-ferramentas3d .galeria{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:16px}
      #saida-ferramentas3d figure{margin:0;display:flex;align-items:center;gap:10px;border:1px solid #d5dbe4;border-radius:6px;padding:8px;color:#1c2836}
      #saida-ferramentas3d .i24 svg{width:24px;height:24px;display:block}
      #saida-ferramentas3d .i48 svg{width:48px;height:48px;display:block;color:#0b3d91}
      #saida-ferramentas3d figcaption{display:flex;flex-direction:column;font-size:12px}
      #saida-ferramentas3d kbd{font:11px ui-monospace,monospace;border:1px solid #c3cad5;border-radius:3px;padding:0 4px;width:max-content}
      #saida-ferramentas3d small{color:#6b7686}
      #saida-ferramentas3d details{margin:2px 0} #saida-ferramentas3d summary{cursor:pointer;font-weight:600}
      #saida-ferramentas3d .ok{color:#2e8b57} #saida-ferramentas3d .nao{color:#c0392b}
      #saida-ferramentas3d ul{margin:2px 0 6px;padding-left:22px;list-style:none;color:#1c2836}
      #saida-ferramentas3d pre{white-space:pre-wrap;color:#7a2a20;background:#fbeeec;padding:4px 6px;margin:2px 0;font-size:11px}
    </style>
    <h1>Ferramentas do editor 3D</h1>
    <p class="resumo ${r.ok ? 'ok' : 'nao'}">${r.total - r.falhas.length} de ${r.total} verificações passaram${r.ok ? '.' : ` — ${r.falhas.length} falharam.`}</p>
    <div class="galeria">${galeria}</div>
    ${linhas}`;
}

if (typeof window !== 'undefined' && !window.FERRAMENTAS3D_MANUAL) {
  verificar().then(r => mostrar(r)).catch(e => {
    document.title = 'FALHOU: exceção';
    console.error(e);
    const d = document.createElement('pre'); d.textContent = (e && e.stack) || String(e);
    document.body.appendChild(d);
  });
}
