// Contrato das ferramentas do editor 3D.
//
// Cada ferramenta é uma máquina de estados simples. O núcleo do editor resolve o que
// é difícil (raycast, snap, conversão de tela para 3D) e entrega à ferramenta um ponto
// já pronto. A ferramenta decide o que fazer e, quando conclui, executa um comando —
// nunca altera o documento diretamente, senão o desfazer não funciona.

/** Ponto entregue às ferramentas em cada evento do mouse. */
export const PontoVazio = {
  ponto: [0, 0, 0],      // coordenada 3D em milímetros, já com snap aplicado
  tela: [0, 0],          // pixels, quando a ferramenta precisar
  entidade: null,        // id da entidade sob o cursor, se houver
  face: -1,              // índice da face sob o cursor, se houver
  aresta: null,          // [i, j] da aresta sob o cursor, se houver
  tipoSnap: '',          // extremidade, meio, centro, interseccao, sobre_aresta,
                         // sobre_face, eixo_x, eixo_y, eixo_z, plano_base
  normal: [0, 0, 1],     // normal da face sob o cursor
};

export class Ferramenta {
  static id = 'ferramenta';
  static nome = 'Ferramenta';
  static atalho = '';
  static grupo = 'edicao';       // navegacao, desenho, edicao, medicao, estrutura
  static icone = '';             // SVG 24×24, traço 1.5, currentColor
  static dica = '';

  constructor(editor) {
    this.editor = editor;
  }

  // --- ciclo de vida ---
  ativar() {}
  desativar() {}

  // --- eventos (todos opcionais) ---
  onPonto(p, ev) {}              // clique com o botão principal
  onMover(p, ev) {}              // movimento do mouse
  onSoltar(p, ev) {}             // soltou o botão (arrasto)
  onDuploClique(p, ev) {}
  onTecla(ev) { return false; }  // devolva true se consumiu a tecla
  onValor(texto) { return false; }  // o usuário digitou uma medida e deu Enter
  cancelar() {}                  // Esc: volte ao estado inicial

  // --- atalhos para o contexto ---
  get documento() { return this.editor.documento; }
  get cena() { return this.editor.cena; }
  get selecao() { return this.editor.selecao; }
  executar(cmd) { return this.editor.executar(cmd); }
  previa(obj) { return this.editor.previa(obj); }
  limparPrevia() { return this.editor.limparPrevia(); }
  dica(texto) { return this.editor.dica(texto); }
  medida(texto) { return this.editor.medida(texto); }
}

/** Converte texto digitado pelo usuário em milímetros. Aceita 3000, 3,5m, 350cm, 12". */
export function paraMilimetros(texto) {
  if (texto == null) return NaN;
  const t = String(texto).trim().toLowerCase().replace(',', '.');
  if (!t) return NaN;
  const m = t.match(/^(-?\d*\.?\d+)\s*(mm|cm|m|"|pol)?$/);
  if (!m) return NaN;
  const v = parseFloat(m[1]);
  const u = m[2] || 'mm';
  return u === 'm' ? v * 1000 : u === 'cm' ? v * 10 : (u === '"' || u === 'pol') ? v * 25.4 : v;
}

/** Lê uma lista de medidas separadas por ponto e vírgula: "2000;1000". */
export function listaDeMedidas(texto) {
  return String(texto || '').split(';').map(paraMilimetros);
}

/** Formata milímetros para a caixa de medidas, no padrão brasileiro. */
export function formatar(mm, casas = 0) {
  if (!isFinite(mm)) return '—';
  if (Math.abs(mm) >= 1000) {
    return (mm / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2,
                                                 maximumFractionDigits: 3 }) + ' m';
  }
  return mm.toLocaleString('pt-BR', { maximumFractionDigits: casas }) + ' mm';
}
