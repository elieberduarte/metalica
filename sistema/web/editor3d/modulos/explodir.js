// Métodos do editor 3D: Explodir peça em trechos e Juntar peças (pedido do usuário, 28/09 — como
// no 2D: separar um trecho em partes para apagar um pedaço, e juntar de volta).
//
// A geometria mora em nucleo/explodir.js; aqui só a seleção, os nomes e o comando de desfazer
// (apagar as peças de antes e pôr as novas, numa entrada só).

import { criar, clonar, novoId } from '../nucleo/documento.js';
import { ComandoAparencia } from '../editor.js';
import { ComandoAdicionar, ComandoRemover, ComandoComposto, ComandoAlterar } from '../nucleo/comandos.js';
import { trechosDoSolido, juntarMalhas, juntarBarras } from '../nucleo/explodir.js';

/** "P15" → "P15.2" nas marcas da peça (a posição e o nome de produção), guardando as de antes. */
function marcasDoTrecho(atr, i) {
  const a = clonar(atr || {});
  delete a.quebras;                     // o original de antes da quebra não vale para o pedaço
  const m = a.marcas || null;
  a.trecho_de = a.trecho_de || { marcas: m ? clonar(m) : null };
  if (m) {
    if (m.posicao) m.posicao = `${m.posicao}.${i + 1}`;
    if (m.nome) m.nome = `${m.nome}.${i + 1}`;
  }
  return a;
}

/** As camadas do Explodir com critério e as cores (as mesmas de nucleo3d/explodir_criterio.CAMADAS). */
const CORES_CRITERIO = { 'Treliças': '#c0392b', 'Pilares': '#34495e', 'Vigas': '#2e86c1', 'Contraventos': '#27ae60',
                         'Chapas': '#e67e22', 'A confirmar': '#8e44ad' };

/** O que o Explodir com critério devolveu → as entidades e os grupos (as treliças), prontos para o comando. */
export function pecasDoCriterio(resposta, camadaOriginal = '') {
  const pecas = resposta.pecas || [], ids = pecas.map(() => novoId());
  const grupos = (resposta.grupos || []).map(g => {
    const id = novoId('g'), filhos = g.membros.map(i => ids[i]);
    const vs = g.membros.flatMap(i => (pecas[i].vertices || []).slice(0, 2));
    const origem = vs.length ? [0, 1, 2].map(k => vs.reduce((s, p) => s + p[k], 0) / vs.length) : [0, 0, 0];
    return { tipo: 'grupo', id, nome: g.nome, camada: 'Treliças', filhos, origem, atributos: clonar(g.atributos || {}), membros: g.membros };
  });
  const grupoDe = new Map();
  for (const g of grupos) for (const i of g.membros) grupoDe.set(i, g.id);
  const novas = pecas.map((p, i) => criar({ id: ids[i], tipo: 'solido', nome: p.nome, camada: p.camada || camadaOriginal,
    material: '', vertices: p.vertices, faces: p.faces, arestas_vivas: [], atributos: p.atributos || {},
    ...(grupoDe.has(i) ? { grupo: grupoDe.get(i) } : {}) }));
  for (const g of grupos) delete g.membros;
  return { novas, grupos };
}

export class MetodosExplodir {
  /** Editar → Explodir com critério (usuário, 12/11: "explodir os elementos — não todos peçinha por peçinha, mas com um
   *  critério: o que está junto por um motivo fica junto; a tesoura pode ser UM elemento"): o sólido que chegou do SketchUp
   *  com tudo dentro (o Galpão Viena: 1 peça, 1.903 pedaços) vira as peças, com o perfil lido na seção, e as treliças
   *  inteiras (um grupo cada). A conta é do servidor (nucleo3d/explodir_criterio.py); aqui, um comando só (Ctrl+Z desfaz)
   *  e o resumo para conferir. */
  async explodirComCriterio() {
    let alvos = [...this.selecao.ids].map(i => this.documento.get(i))
      .filter(e => e && e.tipo === 'solido' && this.documento.editavel(e));
    if (!alvos.length) {
      // nada selecionado: o sólido com mais faces do modelo (o "tudo dentro" do SketchUp)
      const s = this.documento.lista.filter(e => e.tipo === 'solido' && this.documento.editavel(e));
      const maior = s.sort((a, b) => (b.faces || []).length - (a.faces || []).length)[0];
      if (!maior) {
        this.dica('Selecione o sólido a explodir (o modelo do SketchUp que chegou numa peça só).');
        return;
      }
      alvos = [maior];
    }
    const cmds = [], remover = [], todas = [], resumos = [];
    const camadasNovas = new Set();
    for (const e of alvos) {
      let r;
      try {
        r = await this.api.explodirComCriterio({ vertices: e.vertices, faces: e.faces, nome: e.nome || '' });
      } catch (err) {
        this.aviso(`Explodir com critério: ${err.message || err}`, 'erro');
        return;
      }
      if (!r || !(r.pecas || []).length || (r.pecas.length < 2 && !(r.grupos || []).length)) continue;
      const { novas, grupos } = pecasDoCriterio(r, e.camada || '');
      for (const nv of novas) if (!this.documento.camadas.has(nv.camada)) camadasNovas.add(nv.camada);
      remover.push(e.id);
      todas.push(...novas, ...grupos);
      resumos.push(r.resumo || {});
    }
    if (!remover.length) { this.dica('Nada para explodir: o sólido já é uma peça só.'); return; }
    for (const nome of camadasNovas) {
      cmds.push(new ComandoAparencia('camadas', nome, { cor: CORES_CRITERIO[nome] || '#8a94a6', visivel: true, bloqueada: false },
                                     `Camada ${nome}`));
    }
    this.selecao.limpar();
    const n = (k) => resumos.reduce((s, x) => s + (x[k] || 0), 0);
    const pl = (v, um, varios) => `${v.toLocaleString('pt-BR')} ${v === 1 ? um : varios}`;
    const porCamada = {};
    for (const x of resumos) for (const [c, v] of Object.entries(x.por_camada || {})) porCamada[c] = (porCamada[c] || 0) + v;
    this.executar(new ComandoComposto([...cmds, new ComandoRemover(remover), new ComandoAdicionar(todas)],
      `Explodir com critério: ${n('trelicas')} treliças + ${n('pecas_soltas')} peças`));
    const linhas = Object.entries(porCamada).sort((a, b) => b[1] - a[1])
      .map(([c, v]) => `${c}: ${pl(v, 'peça', 'peças')}${c === 'Treliças' ? ' dentro das treliças' : ''}`);
    const corpo = document.createElement('div');
    corpo.className = 'explodir-criterio-resumo';
    corpo.innerHTML = `<p><b>${pl(n('pedacos'), 'pedaço', 'pedaços')} → ${pl(n('trelicas'), 'treliça inteira', 'treliças inteiras')} (um grupo cada; o
      clique pega a treliça, Alt+clique uma peça) + ${pl(n('pecas_soltas'), 'peça solta', 'peças soltas')}.</b></p>
      <ul>${linhas.map(l => `<li>${l}</li>`).join('')}</ul>
      ${n('vigas_duplas') ? `<p>${n('vigas_duplas')} viga(s) dupla(s) (dois perfis numa malha só) separada(s) nos dois perfis.</p>` : ''}
      <p>Cada camada tem uma cor. A camada <b>A confirmar</b> tem o que não teve o perfil lido (o nome diz a seção).</p>`;
    window.__explodirCriterio = { resumo: resumos, porCamada };
    if (await this.dialogo({ titulo: 'Explodir com critério', corpo, ok: 'Manter', cancelar: 'Desfazer' }) !== 'ok') {
      this.desfazer();
      this.dica('Explodir com critério desfeito.');
      return;
    }
    this.dica(`${n('trelicas')} treliças + ${n('pecas_soltas')} peças. Ctrl+Z desfaz.`);
  }

  /** Editar → Explodir: cada peça varrida selecionada vira uma peça por trecho reto. */
  explodirSelecao() {
    const ids = [...this.selecao.ids];
    if (!ids.length) { this.dica('Selecione a peça a explodir (a peça dobrada, a barra quebrada em retas).'); return; }
    const remover = [], novas = [];
    let retas = 0, naoDa = 0;
    for (const id of ids) {
      const e = this.documento.get(id);
      if (!e || !this.documento.editavel(e)) continue;
      if (e.tipo !== 'solido') { retas += 1; continue; }
      const trechos = trechosDoSolido(e);
      if (!trechos) { naoDa += 1; continue; }
      if (trechos.length < 2) { retas += 1; continue; }
      const origem = e.id;
      trechos.forEach((t, i) => {
        const c = clonar(e);
        delete c.id;
        c.vertices = t.vertices;
        c.faces = t.faces;
        c.arestas_vivas = [];
        c.atributos = marcasDoTrecho(e.atributos, i);
        c.atributos.trecho_de.id = (e.atributos && e.atributos.trecho_de && e.atributos.trecho_de.id) || origem;
        c.atributos.trecho_de.nome = c.atributos.trecho_de.nome || e.nome || '';
        c.atributos.trecho_de.ordem = i;
        c.nome = `${e.nome || 'peça'} · trecho ${i + 1}/${trechos.length}`;
        novas.push(criar(c));
      });
      remover.push(id);
    }
    if (!novas.length) {
      const partes = [];
      if (retas) partes.push(`${retas} já ${retas > 1 ? 'são' : 'é'} um trecho reto só`);
      if (naoDa) partes.push(`${naoDa} não ${naoDa > 1 ? 'são peças' : 'é peça'} de perfil varrido (furo feito no editor, malha triangulada)`);
      this.dica(`Nada para explodir: ${partes.join('; ') || 'selecione a peça'}.`);
      return;
    }
    this.selecao.limpar();
    this.executar(new ComandoComposto([new ComandoRemover(remover), new ComandoAdicionar(novas)],
      `Explodir ${remover.length} peça(s) em ${novas.length} trechos`));
    this.selecao.definir(novas.map(e => e.id));
    this.dica(`${remover.length} peça(s) → ${novas.length} trechos (cada um com a marca .1, .2…). Selecione um trecho e Del para apagar; Juntar une de volta.`);
  }

  /** Editar → Juntar: as peças selecionadas numa só (os trechos de uma peça explodida voltam a ela). */
  juntarSelecao() {
    const ids = [...this.selecao.ids].filter(i => this.documento.editavel(this.documento.get(i)));
    const ents = ids.map(i => this.documento.get(i)).filter(Boolean);
    if (ents.length < 2) { this.dica('Selecione duas peças ou mais para juntar.'); return; }
    let nova = null;
    if (ents.every(e => e.tipo === 'barra')) {
      const j = juntarBarras(ents);
      if (!j) { this.aviso('As barras só se juntam quando têm o mesmo perfil e estão na mesma reta.', 'atencao'); return; }
      const c = clonar(j.base);
      // a barra unida fica com o id da original (o pedaço sem a marca de emenda: o Dividir deixa o id nele) — a cota presa a
      // ela e o que mais aponta para a peça continuam valendo depois de dividir e juntar (fluxo de 15/10)
      const original = ents.find(e => !(e.atributos && e.atributos.emenda_de)) || ents[0];
      c.id = original.id;
      c.inicio = j.inicio; c.fim = j.fim;
      c.recorte_inicio = 0; c.recorte_fim = 0;
      c.cortes_inicio = []; c.cortes_fim = [];
      // as pontas de fora guardam o corte e o recorte da barra que estava nelas (o Dividir separou, o Unir devolve —
      // revisão 14/10, F7); a emenda some
      const perto = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) < 1.0;
      for (const b of ents) {
        for (const [ponta, alvo] of [['inicio', 'inicio'], ['fim', 'fim']]) {
          for (const [lado, onde] of [['inicio', b.inicio], ['fim', b.fim]]) {
            if (!perto(onde, c[alvo])) continue;
            // a mesma ponta (a barra no mesmo sentido) leva o corte daquele lado
            const k = lado === 'inicio' ? 'cortes_inicio' : 'cortes_fim', r = lado === 'inicio' ? 'recorte_inicio' : 'recorte_fim';
            if ((b[k] || []).length) c[ponta === 'inicio' ? 'cortes_inicio' : 'cortes_fim'] = clonar(b[k]);
            if (b[r]) c[ponta === 'inicio' ? 'recorte_inicio' : 'recorte_fim'] = b[r];
          }
        }
      }
      if (c.atributos) delete c.atributos.emenda_de;
      nova = criar(c);
      // os marcadores de furo das barras unidas passam para a barra nova
      const unidas = new Set(ents.map(e => e.id));
      this._furosReligados = [...this.documento.entidades.values()]
        .filter(m => m.atributos && m.atributos.furo && unidas.has(m.atributos.furo.peca))
        .map(m => ({ id: m.id, atributos: { ...m.atributos, furo: { ...m.atributos.furo, peca: nova.id } } }));
    } else if (ents.every(e => e.tipo === 'solido')) {
      // na ordem dos trechos, quando vieram de um explodir
      const ordem = ents.slice().sort((a, b) => (((a.atributos || {}).trecho_de || {}).ordem || 0) - (((b.atributos || {}).trecho_de || {}).ordem || 0));
      const m = juntarMalhas(ordem.map(e => ({ vertices: e.vertices, faces: e.faces })));
      const c = clonar(ordem[0]);
      delete c.id;
      c.vertices = m.vertices; c.faces = m.faces; c.arestas_vivas = [];
      const td = (c.atributos || {}).trecho_de;
      const mesma = td && ordem.every(e => ((e.atributos || {}).trecho_de || {}).id === td.id);
      if (mesma) {
        // os trechos da mesma peça: volta o nome e as marcas de antes
        if (td.marcas) c.atributos.marcas = clonar(td.marcas);
        if (td.nome !== undefined) c.nome = td.nome;
        delete c.atributos.trecho_de;
      }
      nova = criar(c);
    } else {
      this.aviso('Juntar une sólidos com sólidos ou barras com barras — a seleção mistura os dois.', 'atencao');
      return;
    }
    this.selecao.limpar();
    const religar = (this._furosReligados || []).map(r => new ComandoAlterar(r.id, { atributos: r.atributos }, 'Furo na barra unida'));
    this._furosReligados = null;
    this.executar(new ComandoComposto([new ComandoRemover(ents.map(e => e.id)), new ComandoAdicionar([nova]), ...religar],
      `Juntar ${ents.length} peças`));
    this.selecao.definir([nova.id]);
    this.dica(`${ents.length} peças juntadas em uma.`);
  }
}
