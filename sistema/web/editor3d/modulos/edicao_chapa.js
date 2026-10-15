// Editar chapa a partir do 3D (pedido do usuário, 02/10): a chapa selecionada abre no ambiente de edição do 2D —
// "isolada" (só a peça) ou "no local" (com as peças em volta cortadas no plano dela, como referência). A edição em si
// mora no CAD (web/cad/edicao_chapa.js); Concluir leva furos e contorno a todas as chapas da posição e volta para cá.
// 15/10: dois cliques na chapa, ou "Editar chapa no 2D" no botão direito, abrem essa tela (antes eram as alças no 3D).

import { ComandoAlterar } from '../nucleo/comandos.js';

/** A chapa (paramétrica ou a placa sólida do IFC, que vira paramétrica ao abrir) com marca de posição, ou null. */
export function chapaEditavel(ent) {
  if (!ent) return null;
  const m = (ent.atributos && ent.atributos.marcas) || {};
  if (!m.posicao) return null;
  const placa = ent.tipo === 'chapa' || (ent.atributos && ent.atributos.tipo_ifc === 'IfcPlate');
  return placa ? { marca: String(m.posicao), nome: m.nome || String(m.posicao) } : null;
}

export class MetodosEdicaoChapa {
  /** A chapa no 2D pelos dois cliques ou pelo botão direito: a chapa desenhada à mão ainda sem marca de posição recebe
   *  a dela (só ela, pelo critério do Numerar) — a edição no 2D trabalha pela posição. */
  async abrirChapaNo2D(ent, modo = 'isolada') {
    const placa = ent && (ent.tipo === 'chapa' || (ent.atributos && ent.atributos.tipo_ifc === 'IfcPlate'));
    if (!placa) return false;
    if (!this.projeto) {
      this.aviso('Para editar a chapa no 2D, abra o modelo pelo projeto (gerenciador): a edição grava nos desenhos dele. ' +
                 'Aqui, use as alças da chapa no 3D (botão direito).', 'atencao', 9000);
      return false;
    }
    let alvo = ent;
    if (!chapaEditavel(ent)) {
      try {
        this.dica('Dando a marca de posição à chapa para abrir no 2D…');
        const r = await this.api.numerar(this.documento.paraJSON(), {});
        const p = (r.mudancas || {})[ent.id];
        if (!p || !(p.marcas && p.marcas.posicao)) throw new Error('a numeração não deu marca à chapa');
        const at = { ...(ent.atributos || {}) };
        for (const [k, v] of Object.entries(p)) { if (v === null || v === undefined) delete at[k]; else at[k] = v; }
        this.executar(new ComandoAlterar({ [ent.id]: { atributos: at } }, `Marca ${p.marcas.posicao} para editar no 2D`));
        alvo = this.documento.get(ent.id);
        this.aviso(`A chapa recebeu a marca ${p.marcas.posicao} para abrir no 2D (as outras peças não mudaram).`, 'info', 7000);
      } catch (e) { this.aviso(`Não foi possível dar a marca à chapa para editar no 2D: ${e.message}`, 'erro', 0); return false; }
    }
    await this.editarChapa(alvo, modo);
    return true;
  }

  /** Abre a edição da chapa no 2D; ao concluir ou cancelar, o CAD volta ao 3D. */
  async editarChapa(ent, modo) {
    const ch = chapaEditavel(ent);
    if (!ch || !this.projeto) return;
    this.dica(`Abrindo a edição de ${ch.nome}${modo === 'local' ? ' no local' : ''}…`);
    try {
      if (this._gravarAntesDeGerar) await this._gravarAntesDeGerar();
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar-posicao`, {
        // a peça clicada é a referência: o desenho sai na orientação dela
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ marca: ch.marca, referencia: ent.id, edicao: true, modo }),
      });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      (window.metalicaNavegar || ((u) => { location.href = u; }))(
        `/cad?projeto=${encodeURIComponent(this.projeto)}&desenho=${encodeURIComponent(j.nome)}&voltar=__3d__`);
    } catch (e) { this.aviso(`Não foi possível abrir a edição de ${ch.nome}: ${e.message}`, 'erro', 0); this.dica(''); }
  }
}
