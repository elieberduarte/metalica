// Tipos de linha e espessuras do CAD 2D, como no AutoCAD (pedido do usuário, 23/10: "precisamos criar outros tipos de
// linhas (tracejada, pontilhada....) igual existe no autocad, e a opção de mexer nas espessuras"). Espelho de
// nucleo2d/tipos_linha.py: os mesmos nomes (os do acadiso.lin, que o AutoCAD reconhece no DXF), o mesmo padrão em mm
// de papel (+ traço, − espaço, 0 ponto) e as mesmas espessuras.
//
// O padrão sai no papel × a escala dos tracejados do desenho (metadados.estilo.escala_tracejado, o LTSCALE dele em
// relação à escala; vazio = ESCALA_TRACEJADO): na tela acompanha o zoom, como no AutoCAD, sem ficar menor que alguns
// pixels (senão o tracejado some e parece contínuo).

const A = (nome, rotulo, padrao) => [nome, rotulo, padrao];
const meio = (p) => p.map(v => v / 2), dobro = (p) => p.map(v => v * 2);
const P = {
  DASHED: [12.7, -6.35], HIDDEN: [6.35, -3.175], CENTER: [31.75, -6.35, 6.35, -6.35], DOT: [0, -6.35],
  DASHDOT: [12.7, -6.35, 0, -6.35], DIVIDE: [12.7, -6.35, 0, -6.35, 0, -6.35], PHANTOM: [31.75, -6.35, 6.35, -6.35, 6.35, -6.35],
  BORDER: [12.7, -6.35, 12.7, -6.35, 0, -6.35],
};
const familia = (nome, rotulo) => [A(nome, rotulo, P[nome]), A(nome + '2', `${rotulo} (curta)`, meio(P[nome])), A(nome + 'X2', `${rotulo} (longa)`, dobro(P[nome]))];

/** [nome, rótulo, padrão em mm de papel] */
export const TIPOS_DE_LINHA = [
  A('CONTINUOUS', 'Contínua', []),
  ...familia('DASHED', 'Tracejada'),
  ...familia('HIDDEN', 'Oculta'),
  ...familia('DOT', 'Pontilhada'),
  ...familia('DASHDOT', 'Traço e ponto'),
  ...familia('CENTER', 'Centro'),
  ...familia('DIVIDE', 'Traço e dois pontos'),
  ...familia('PHANTOM', 'Fantasma'),
  ...familia('BORDER', 'Borda'),
];
const POR_NOME = new Map(TIPOS_DE_LINHA.map(t => [t[0], t]));
export const rotuloDoTipo = (nome) => (POR_NOME.get(String(nome || 'CONTINUOUS').toUpperCase()) || POR_NOME.get('CONTINUOUS'))[1];
export const padraoDoTipo = (nome) => (POR_NOME.get(String(nome || 'CONTINUOUS').toUpperCase()) || POR_NOME.get('CONTINUOUS'))[2];

/** As espessuras de linha do AutoCAD, em mm. */
export const ESPESSURAS = [0, 0.05, 0.09, 0.13, 0.15, 0.18, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.53, 0.6, 0.7, 0.8, 0.9, 1, 1.06, 1.2, 1.4, 1.58, 2, 2.11];

/** A escala dos tracejados padrão (o LTSCALE ÷ a escala do desenho): o DASHED de 12,7 mm sai com 6,35 mm no papel. */
export const ESCALA_TRACEJADO = 0.5;
export function escalaTracejado(estilo) {
  const v = estilo && +estilo.escala_tracejado;
  return v > 0 ? v : ESCALA_TRACEJADO;
}

/** O tipo de linha e a espessura de um objeto: os dele, senão os da camada ("pela camada", o ByLayer do AutoCAD). */
export function estiloDaLinha(e, cam) {
  const tl = (e && e.tipo_linha) || (cam && cam.tipo_linha) || 'CONTINUOUS';
  const esp = e && e.espessura != null && e.espessura !== '' ? +e.espessura : (cam && cam.espessura != null ? +cam.espessura : 0.25);
  return { tipo: String(tl).toUpperCase(), espessura: esp };
}

/** A largura do traço na tela, em pixels: a espessura em mm vista como no AutoCAD com a espessura ligada (0,25 = 1 px). */
export const larguraNaTela = (esp) => Math.max(1, Math.min(8, (+esp || 0.25) / 0.25));

/** O padrão do tipo na tela (setLineDash, em pixels): o do papel × a escala dos tracejados × a escala do desenho × o
 *  zoom, nunca com o período menor que 8 px. `z` é px por mm do desenho. */
export function tracosNaTela(nome, k, z, estilo) {
  const p = padraoDoTipo(nome);
  if (!p.length) return [];
  const periodo = p.reduce((s, v) => s + Math.abs(v), 0);
  const f = Math.max(escalaTracejado(estilo) * (k || 1) * z, 8 / periodo);
  // o ponto (0) vira um traço de 0,5 px, que a ponta redonda arredonda
  return p.map(v => Math.max(Math.abs(v) * f, v === 0 ? 0.5 : 1));
}
