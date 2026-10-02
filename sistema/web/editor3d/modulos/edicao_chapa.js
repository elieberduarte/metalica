// Editar chapa a partir do 3D (pedido do usuário, 02/10): a chapa selecionada abre no ambiente de edição do 2D —
// "isolada" (só a peça) ou "no local" (com as peças em volta cortadas no plano dela, como referência). A edição em si
// mora no CAD (web/cad/edicao_chapa.js); Concluir leva furos e contorno a todas as chapas da posição e volta para cá.

/** A chapa (paramétrica ou a placa sólida do IFC, que vira paramétrica ao abrir) com marca de posição, ou null. */
export function chapaEditavel(ent) {
  if (!ent) return null;
  const m = (ent.atributos && ent.atributos.marcas) || {};
  if (!m.posicao) return null;
  const placa = ent.tipo === 'chapa' || (ent.atributos && ent.atributos.tipo_ifc === 'IfcPlate');
  return placa ? { marca: String(m.posicao), nome: m.nome || String(m.posicao) } : null;
}

export class MetodosEdicaoChapa {
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
