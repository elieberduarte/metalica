// O 3D nas elevações dos eixos (12/10/2026, pedido do usuário no Posto CB: "gerar os quadros com as elevações de todos os
// eixos … será até mais fácil de conferir certas coisas com o modelo organizado dessa forma").
//
// A obra montada por outro caminho (pela planta, pelo IFC) tem o 3D pronto, mas a elevação do eixo só desenhava as
// tesouras lançadas na própria Montagem. Aqui cada elevação pode mostrar o CORTE DO 3D no plano do eixo:
//   · as barras no plano (até 150 mm dele) em linha cheia, com o nome da peça em cima;
//   · o que atravessa o plano (terça, viga, o banzo da tesoura que cruza) como a marca do corte, com a sigla da terça;
// e a CONFERÊNCIA do eixo, marcada em vermelho no quadro e listada no botão "Conferência" da Implantação:
//   · o pilar perto de um cruzamento, mas fora dele (mais de 100 mm, até 600);
//   · a peça (tesoura, treliça, viga) que corre ao lado do eixo, fora da linha dele (60 a 600 mm; até 60 é a peça com a
//     face no eixo) — desenhada tracejada, e o mesmo alinhamento (peças e pilares juntos) vira uma linha só;
//   · o eixo sem nada do 3D no plano dele.
// O desenho é do programa (refeito com os eixos, os níveis e a escala, como os eixos e os níveis da elevação): liga e
// desliga no título da elevação ("3D"); "Todas as elevações" no título da Implantação abre uma por eixo, já com o 3D.

import { criar } from './nucleo/desenho2d.js';

export const CAMADA_3D = 'IMPL 3D';
export const CAMADA_3D_CORTE = 'IMPL 3D CORTE';
export const CAMADA_3D_LADO = 'IMPL 3D AO LADO';
export const CAMADA_CONFERENCIA = 'IMPL CONFERENCIA';
const CAMADAS_3D = {
  [CAMADA_3D]: { cor: '#0ea5e9', tipo_linha: 'CONTINUOUS', espessura: 0.25 },
  [CAMADA_3D_CORTE]: { cor: '#a855f7', tipo_linha: 'CONTINUOUS', espessura: 0.18 },
  [CAMADA_3D_LADO]: { cor: '#22c55e', tipo_linha: 'DASHED', espessura: 0.18 },
  [CAMADA_CONFERENCIA]: { cor: '#ef4444', tipo_linha: 'CONTINUOUS', espessura: 0.35 },
};
/** mm reais: no plano do eixo; o pilar fora do cruzamento; a peça ao lado do eixo; até onde é a face no eixo */
const NO_PLANO = 150, PILAR_FORA = 100, PERTO = 600, FORA_DA_LINHA = 60;
/** o que não entra no corte: a presilha (a ligação das cantoneiras), os acessórios da terça */
const FORA_DO_CORTE = new Set(['presilha', 'corrente', 'agulha', 'esticador', 'tirante']);
/** o que atravessa o plano e vira marca de corte */
const NO_CORTE = new Set(['terça', 'banzo', 'viga', 'apoio_terca', 'longarina', 'pilar']);
/** mm de papel: o lado da marca do corte, a altura dos nomes */
const MARCA = 1.6, TXT_PECA = 2.6, TXT_SIGLA = 1.8, TXT_CONF = 2.4;

const natural = (a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true, sensitivity: 'base' });
const metros = (mm) => (mm / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' m';

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}
async function pedirJson(rota) {
  const r = await fetch(rota, { cache: 'no-store' });
  if (!r.ok) throw new Error(await r.text() || r.statusText);
  return r.json();
}

export class MetodosCorteEixos {
  // ------------------------------------------------------------------ o modelo
  /** As barras do 3D do projeto, só o que o corte usa: {a, b, papel, nome (a peça do projeto), sigla}. */
  async _carregarModelo3d(forcar = false) {
    const p = this.cad.projeto;
    if (!p) return null;
    if (!forcar && this._modelo3d && this._modelo3d.projeto === p) return this._modelo3d;
    let d;
    try { d = await pedirJson(`/api/projetos/${encodeURIComponent(p)}/modelo`); } catch { this._modelo3d = null; return null; }
    const doc = (d && d.documento) || d || {};             // a rota entrega {documento, …}
    const ents = Array.isArray(doc.entidades) ? doc.entidades : Object.values(doc.entidades || {});
    const barras = [];
    for (const e of ents) {
      if (e.tipo !== 'barra' || !e.inicio || !e.fim || FORA_DO_CORTE.has(e.papel)) continue;
      const o = (e.atributos || {}).origem || {};
      barras.push({ id: e.id, a: e.inicio, b: e.fim, papel: e.papel || '', perfil: e.perfil || '',
        nome: String(o.planta || o.peca || '').split('#')[0], peca: o.peca || '', sigla: o.sigla || (e.atributos || {}).sigla || '' });
    }
    this._modelo3d = { projeto: p, barras };
    return this._modelo3d;
  }

  /** Os eixos gravados no projeto (os do 3D montado pela planta), quando a Montagem ainda não tem os dela. */
  async _eixosDoProjeto() {
    try {
      const r = await pedirJson(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/eixos`);
      const ex = r && r.eixos;
      if (!ex || !((ex.numeros || []).length || (ex.letras || []).length)) return null;
      return { eixo_g: ex.eixo_g || [1, 0], perp_g: ex.perp_g, numeros: ex.numeros || [], letras: ex.letras || [], vista_invertida: false };
    } catch { return null; }
  }

  _camadas3d() {
    const doc = this.cad.doc;
    for (const [nome, c] of Object.entries(CAMADAS_3D)) if (!doc.camadas.has(nome)) doc.camadas.set(nome, { nome, ...c, visivel: true, bloqueada: true });
  }

  // ------------------------------------------------------------------ todas as elevações
  /** "Todas as elevações": uma elevação por eixo (numerados e com letra), com o corte do 3D e a conferência. */
  async todasAsElevacoes() {
    if (!this.m) return;
    if (!this._eixosDaObra()) {
      const ex = await this._eixosDoProjeto();
      if (!ex) { this.cad.aviso('A obra ainda não tem eixos: dê os eixos primeiro ("Eixos…" no título da Implantação).', 'atencao', 9000); return; }
      this.m.eixos = ex;
      await this.garantirImplantacao();
    }
    this.cad.aviso('Lendo o 3D do projeto para as elevações…', 'info', 5000);
    const mod = await this._carregarModelo3d(true);
    const { TIPOS } = await import('./montagem.js');
    const t = TIPOS.elevacao;
    let n = 0;
    for (const fam of ['numero', 'letra']) {
      for (const e of this._familia(fam)) {
        let q = this._elevacoes().find(x => x.eixo === e.nome && x.familia === fam);
        if (!q) {
          q = { id: 'q' + Date.now().toString(36) + 'e' + (n++).toString(36), tipo: 'elevacao', nome: `Elevação ${e.nome}`, eixo: e.nome, familia: fam,
            escala: t.escala, w: t.w, h: t.h, x: 0, y: 0, sombra: null };
          this.m.quadros.push(q);
        }
        if (mod) q.do3d = true;
      }
    }
    // em ordem de eixo: as dos numerados e depois as das letras, logo depois da implantação
    const elevs = this._elevacoes().sort((a, b) => (a.familia === b.familia ? natural(a.eixo, b.eixo) : a.familia === 'numero' ? -1 : 1));
    const resto = this.m.quadros.filter(x => x.tipo !== 'elevacao');
    const i = resto.findIndex(x => x.tipo === 'implantacao');
    this.m.quadros = [...resto.slice(0, i + 1), ...elevs, ...resto.slice(i + 1)];
    await this.refazerQuadrosDaObra([...this._elevacoes(), this._quadroImplantacao()].filter(Boolean));
    const qi = this._quadroImplantacao();
    if (qi) this.cad.tela.enquadrar([[qi.x, qi.y - qi.h], [qi.x + qi.w, qi.y]]);
    const conf = this._elevacoes().reduce((s, q) => s + (q.conferencia_3d || []).length, 0);
    this.cad.aviso(`${elevs.length} elevações${mod ? ', com o corte do 3D' : ' (o projeto não tem 3D)'}.` +
      (mod ? ` Conferência: ${conf} apontamento(s) — botão "Conferência" no título da Implantação.` : ''), conf ? 'atencao' : 'info', 12000);
  }

  // ------------------------------------------------------------------ o corte de uma elevação
  /**
   * O corte do 3D no plano do eixo da elevação `q` (P: real (u, z) → papel), e a conferência dele em `q.conferencia_3d`.
   * Chamado pelo desenho da elevação (implantacao.js, _planejarElevacao) quando `q.do3d`.
   */
  _corteDo3D(q, P) {
    const mod = this._modelo3d, ex = this._eixosDaObra();
    q.conferencia_3d = [];
    if (!mod || !ex) return [];
    const eixo = this._familia(q.familia).find(e => e.nome === q.eixo);
    const cruz = this._cruzamDaElevacao(q);
    if (!eixo || !cruz.length) return [];
    this._camadas3d();
    const eg = ex.eixo_g || [1, 0], pg = ex.perp_g || [-eg[1], eg[0]];
    const G = (r) => r[0] * eg[0] + r[1] * eg[1], Pp = (r) => r[0] * pg[0] + r[1] * pg[1];
    const numero = q.familia === 'numero';
    const nrm = (r) => (numero ? G(r) : Pp(r)) - eixo.pos;           // a distância (com sinal) ao plano do eixo
    const p0 = cruz[0].pos;
    const sent = cruz.length > 1 && cruz[1].u !== cruz[0].u ? Math.sign((cruz[1].pos - cruz[0].pos) / (cruz[1].u - cruz[0].u)) : 1;
    const ao = (r) => ((numero ? Pp(r) : G(r)) - p0) * sent;          // u ao longo da elevação
    // o que está mais perto de outro eixo da mesma família é dele, não "ao lado" deste (os eixos 9 e 10 do Posto, a 0,51 m)
    const outros = this._familia(q.familia).filter(e => e.nome !== q.eixo).map(e => e.pos - eixo.pos);
    const deOutro = (d) => outros.some(o => Math.abs(d - o) < Math.abs(d));
    const U = Math.max(...cruz.map(c => c.u)), MARGEM_U = 3000;
    const dentroU = (u) => u >= -MARGEM_U && u <= U + MARGEM_U;
    const at = (extra = {}) => ({ quadro: q.id, gerado: 'elevacao', do3d: true, ...extra });
    const out = [];

    // 1ª passada: as peças (tesoura, treliça, viga) que correm ao lado do eixo, paralelas a ele — pela média das barras
    // principais (banzo, viga) a até 600 mm do plano. Elas entram no desenho tracejadas, com o afastamento escrito: no
    // Posto as tesouras das filas B, C, D e F correm em linhas próprias do projeto, a 0,22–0,38 m do eixo
    const principais = new Map();   // peça → [{d, b}]
    for (const b of mod.barras) {
      if (!['banzo', 'viga'].includes(b.papel) || !b.peca) continue;
      const da = nrm(b.a), db = nrm(b.b);
      if (Math.abs(da) <= PERTO && Math.abs(db) <= PERTO && Math.abs(da - db) < 50) (principais.get(b.peca) || principais.set(b.peca, []).get(b.peca)).push({ d: (da + db) / 2, b });
    }
    const aoLado = new Map();       // peça → afastamento médio (só as fora da linha)
    for (const [peca, lst] of principais) {
      const dm = lst.reduce((s, x) => s + x.d, 0) / lst.length;
      if (Math.abs(dm) > FORA_DA_LINHA && Math.abs(dm) <= PERTO && !deOutro(dm)) aoLado.set(peca, dm);
    }

    // 2ª passada: o desenho
    const noPlano = new Map();      // peça → {nome, umin, umax, ztopo, d}
    const caixa = (k, b, ua, ub, d) => {
      const r = noPlano.get(k) || { nome: b.nome, umin: Infinity, umax: -Infinity, ztopo: -Infinity, d };
      r.umin = Math.min(r.umin, ua, ub); r.umax = Math.max(r.umax, ua, ub); r.ztopo = Math.max(r.ztopo, b.a[2], b.b[2]);
      noPlano.set(k, r);
    };
    for (const b of mod.barras) {
      const da = nrm(b.a), db = nrm(b.b);
      const ua = ao(b.a), ub = ao(b.b);
      const dLado = b.peca ? aoLado.get(b.peca) : undefined;
      if (dLado !== undefined && Math.abs(da - dLado) <= NO_PLANO && Math.abs(db - dLado) <= NO_PLANO) {
        if (!dentroU(ua) && !dentroU(ub)) continue;
        out.push(criar({ tipo: 'linha', camada: CAMADA_3D_LADO, a: P(ua, b.a[2]), b: P(ub, b.b[2]), atributos: at({ id3d: b.id, papel: b.papel, peca: b.nome, ao_lado: Math.round(dLado) }) }));
        caixa(b.peca, b, ua, ub, dLado);
        continue;
      }
      if (Math.abs(da) <= NO_PLANO && Math.abs(db) <= NO_PLANO) {
        if (!dentroU(ua) && !dentroU(ub)) continue;
        out.push(criar({ tipo: 'linha', camada: CAMADA_3D, a: P(ua, b.a[2]), b: P(ub, b.b[2]), atributos: at({ id3d: b.id, papel: b.papel, peca: b.nome }) }));
        if (b.nome && b.papel !== 'terça') caixa(b.peca || b.nome, b, ua, ub, 0);
        continue;
      }
      // o pilar ao lado do eixo (o do alinhamento próprio das tesouras), tracejado como elas
      if (b.papel === 'pilar' && Math.abs(da) <= PERTO && Math.abs(db) <= PERTO && Math.abs(da - db) < 50 && !deOutro((da + db) / 2)) {
        if (dentroU(ua) || dentroU(ub)) out.push(criar({ tipo: 'linha', camada: CAMADA_3D_LADO, a: P(ua, b.a[2]), b: P(ub, b.b[2]), atributos: at({ id3d: b.id, papel: b.papel, peca: b.nome, ao_lado: Math.round((da + db) / 2) }) }));
        continue;
      }
      // atravessa o plano: a marca do corte
      if (!NO_CORTE.has(b.papel) || da * db > 0 || da === db) continue;
      const t = da / (da - db);
      const r = [b.a[0] + (b.b[0] - b.a[0]) * t, b.a[1] + (b.b[1] - b.a[1]) * t, b.a[2] + (b.b[2] - b.a[2]) * t];
      const u = ao(r);
      if (!dentroU(u)) continue;
      const c = P(u, r[2]);
      const m = MARCA / 2;
      out.push(criar({ tipo: 'polilinha', camada: CAMADA_3D_CORTE, vertices: [[c[0] - m, c[1] - m], [c[0] + m, c[1] - m], [c[0] + m, c[1] + m], [c[0] - m, c[1] + m]], fechada: true,
        atributos: at({ id3d: b.id, papel: b.papel, peca: b.nome, corte: true }) }));
      if (b.papel === 'terça' && b.sigla) {
        out.push(criar({ tipo: 'texto', camada: CAMADA_3D_CORTE, posicao: [c[0], c[1] + m + 0.6], texto: b.sigla, altura: TXT_SIGLA, alinhamento: 'esquerda', vertical: 'meio', angulo: 90,
          atributos: at({ id3d: b.id, corte: true }) }));
      }
    }
    // o nome de cada peça em cima dela (a do lado com o afastamento)
    for (const [, r] of noPlano) {
      if (!isFinite(r.umin)) continue;
      const texto = r.d ? `${r.nome} (${metros(Math.abs(r.d))} ao lado)` : r.nome;
      out.push(criar({ tipo: 'texto', camada: r.d ? CAMADA_3D_LADO : CAMADA_3D, posicao: P((r.umin + r.umax) / 2, r.ztopo), texto, altura: TXT_PECA, alinhamento: 'centro', vertical: 'base',
        atributos: at({ peca: r.nome }) }));
    }

    // a conferência: o que corre ao lado do eixo, agrupado pelo afastamento (o mesmo alinhamento = uma linha só)
    const itens = [];               // {d, u, z, nome, pilar}
    for (const [peca, dm] of aoLado) {
      const lst = principais.get(peca);
      const us = lst.flatMap(x => [ao(x.b.a), ao(x.b.b)]), zs = lst.flatMap(x => [x.b.a[2], x.b.b[2]]);
      itens.push({ d: dm, u: (Math.min(...us) + Math.max(...us)) / 2, z: Math.max(...zs), nome: lst[0].b.nome || peca.split('#')[0], pilar: false });
    }
    // o pilar perto de um cruzamento, mas fora dele — na elevação do eixo de que ele mais se afasta
    for (const b of mod.barras) {
      if (b.papel !== 'pilar') continue;
      const base = b.a[2] <= b.b[2] ? b.a : b.b;
      const d = nrm(base);
      if (Math.abs(d) > PERTO || deOutro(d)) continue;
      const u = ao(base);
      for (const c of cruz) {
        const du = u - c.u;
        if (Math.abs(du) > PERTO || Math.hypot(d, du) <= PILAR_FORA) continue;
        // o deslocado ao longo deste eixo aparece na elevação do outro (o mesmo pilar, uma vez só)
        if (Math.abs(d) >= Math.abs(du)) itens.push({ d, u, z: base[2], nome: b.nome || b.perfil, pilar: true, cruz: c.nome });
      }
    }
    const conf = [];
    const grupos = [];
    for (const it of itens.sort((a, b) => a.d - b.d)) {
      const g = grupos.find(x => Math.abs(x.d - it.d) <= 20);
      if (g) { g.lst.push(it); g.d = (g.d * (g.lst.length - 1) + it.d) / g.lst.length; } else grupos.push({ d: it.d, lst: [it] });
    }
    const lista = (nomes) => { const u = [...new Set(nomes)].sort(natural); return u.length > 1 ? u.slice(0, -1).join(', ') + ' e ' + u[u.length - 1] : u[0]; };
    for (const g of grupos) {
      const pecas = g.lst.filter(x => !x.pilar), pils = g.lst.filter(x => x.pilar);
      const partes = [];
      if (pecas.length) partes.push(lista(pecas.map(x => x.nome)));
      if (pils.length) partes.push(`${pils.length === 1 ? 'o pilar' : pils.length + ' pilares'} de ${lista(pils.map(x => `${q.eixo}/${x.cruz}`))}`);
      const todos = new Set(pecas.map(x => x.nome)).size + pils.length;
      conf.push({ u: g.lst[0].u, z: g.lst[0].z, tipo: pils.length ? 'alinhamento_fora_do_eixo' : 'fora_da_linha',
        texto: `${partes.join(' e ')} ${todos > 1 ? 'correm' : 'corre'} a ${metros(Math.abs(g.d))} do eixo ${q.eixo}` +
          (pecas.length && pils.length ? ' — peças e pilares no mesmo alinhamento, fora da linha do eixo' : '') });
    }
    if (!out.length) conf.push({ u: U / 2, z: 0, texto: `eixo ${q.eixo}: nada do 3D no plano dele`, tipo: 'eixo_vazio' });
    // as marcas da conferência: o círculo e o número (a lista no botão "Conferência" da Implantação)
    conf.forEach((c, i) => {
      const p = P(c.u, c.z);
      out.push(criar({ tipo: 'circulo', camada: CAMADA_CONFERENCIA, centro: p, raio: 3, atributos: at({ conferencia: i }) }));
      out.push(criar({ tipo: 'texto', camada: CAMADA_CONFERENCIA, posicao: [p[0] + 3.6, p[1] + 1], texto: String(i + 1), altura: TXT_CONF, alinhamento: 'esquerda', vertical: 'base',
        atributos: at({ conferencia: i }) }));
    });
    q.conferencia_3d = conf.map(c => ({ ...c, papel: P(c.u, c.z) }));
    return out;
  }

  // ------------------------------------------------------------------ a lista da conferência
  /** "Conferência" no título da Implantação: o que o corte do 3D achou em cada eixo; clique leva ao ponto. */
  async conferenciaDosEixos() {
    const elevs = this._elevacoes().filter(q => q.do3d);
    if (!elevs.length) { this.cad.aviso('Nenhuma elevação com o 3D: use "Todas as elevações" no título da Implantação.', 'atencao', 9000); return; }
    let ir = null;
    const itens = [];
    for (const q of elevs) {
      const lst = q.conferencia_3d || [];
      if (!lst.length) continue;
      itens.push(el('div', { class: 'conferencia-eixo' }, el('b', {}, `Elevação ${q.eixo}`),
        el('ol', {}, lst.map((c, i) => el('li', { value: i + 1, title: 'Ir até o ponto na elevação',
          onclick: () => { ir = { q, c }; const b = document.getElementById('dialogo-cancelar'); if (b) b.click(); } }, c.texto)))));
    }
    const total = elevs.reduce((s, q) => s + (q.conferencia_3d || []).length, 0);
    const corpo = el('div', { class: 'enviar-quadro-dialogo conferencia-eixos' },
      el('div', { class: 'explica', texto: total
        ? `${total} apontamento(s) em ${itens.length} de ${elevs.length} elevações. O número é o da marca vermelha no quadro; clique para ir até ela.`
        : `Nada a apontar nas ${elevs.length} elevações.` }),
      ...itens);
    await this.cad.dialogo({ titulo: 'Conferência dos eixos pelo 3D', corpo, ok: 'Fechar' });
    if (ir && ir.c.papel) {
      const [x, y] = ir.c.papel, r = 60;
      this.cad.tela.enquadrar([[x - r, y - r * 0.6], [x + r, y + r * 0.6]]);
    }
  }
}
