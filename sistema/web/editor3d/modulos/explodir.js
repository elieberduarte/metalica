// Métodos do editor 3D: Explodir peça em trechos e Juntar peças (pedido do usuário, 28/09 — como
// no 2D: separar um trecho em partes para apagar um pedaço, e juntar de volta).
//
// A geometria mora em nucleo/explodir.js; aqui só a seleção, os nomes e o comando de desfazer
// (apagar as peças de antes e pôr as novas, numa entrada só).

import { criar, clonar } from '../nucleo/documento.js';
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

export class MetodosExplodir {
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
