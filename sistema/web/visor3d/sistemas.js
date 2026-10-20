// O sistema de cada peça (metálica, cobertura, pré-moldado, terreno, outros) — o mesmo no modo ver do PC (ver3d.js) e no
// celular (celular.js), 20/10: saiu do ver3d.js para os dois não divergirem. Só lê as fichas e as camadas do visor.

/** O sistema de cada peça (usuário, Mercado Conceito, 16/10: "separar apenas pré-moldado (estrutura) e metálica para
 *  apresentação ao cliente"): pelo material — concreto é pré-moldado; aço (e a barra sem material) é metálica. O aço e o
 *  neoprene que vêm no modelo do pré-moldado (a camada dele é quase toda de concreto: as porcas, arruelas e cantoneiras
 *  das ligações dele) ficam com o pré-moldado. O resto (o PVC das descidas…) é Outros. */
export const SISTEMAS = { metalica: ['Metálica', '#2f6fd6'], cobertura: ['Cobertura — telhas, calhas e rufos', '#3aa69b'],
  outros: ['Outros', '#e08a1e'], premoldado: ['Pré-moldado (concreto)', '#8f969e'], terreno: ['Terreno, rua e calçada', '#b9a27a'] };
// a cobertura num sistema só (usuário, Mercado, 19/10: "não foi criado o grupo com as telhas, calhas e rufos" — as telhas
// caíam em Outros e as calhas e os rufos, de chapa galvanizada, em Metálica): a camada no grupo da cobertura (o que o
// lançamento de telhas faz) ou com o nome de telha, calha, rufo ou cumeeira — antes do material
const COBERTURA_GRUPO = /cobertura/i;
const COBERTURA_CAMADA = /^\s*(telhas?|calhas?|rufos?|cumeeiras?)\b/i;
// o terreno, a rua e a calçada num sistema só (usuário, 16/10: "terreno, rua e calçada como uma camada única; parede
// pode deixar junto com o pré-moldado"): pelo nome da peça, antes do material (no IFC do Mercado são lajes de concreto);
// o muro e as vagas do estacionamento também (usuário, Mercado, 20/10: "colocar esses itens junto com a layer do
// terreno"), e a camada com esses nomes — para mandar à mão uma peça para o terreno: Editar → Camada "Terreno"
const TERRENO = /^\s*(terrenos?|ruas?|cal[çc]adas?|passeios?|muros?|vagas?|estacionamentos?)\b/i;
const CONCRETO = /concret|fck|cimento|\bc\s?[1-9]\d\b/i;
const ACO = /steel|a[çc]o\b|astm|\ba36\b|a5\d\d|a32[05]|a307|s2\d\d|s3\d\d|ar\s?3\d\d|zar|galv|shore|neopren|elast/i;
const NEOPRENE = /shore|neopren|elast/i;
export function gruposDeSistema(visor) {
  const fichas = visor.fichas || [], n = Math.min(fichas.length, visor.nPecas);
  const porCamada = new Map();                                           // camada → [peças, de concreto]
  for (let i = 0; i < n; i++) {
    const q = porCamada.get(fichas[i].c) || [0, 0];
    q[0]++; if (CONCRETO.test(fichas[i].m || '')) q[1]++;
    porCamada.set(fichas[i].c, q);
  }
  const cams = (visor.cabecalho && visor.cabecalho.camadas) || [];
  const daCobertura = cams.map(c => COBERTURA_GRUPO.test(c.grupo || '') || COBERTURA_CAMADA.test(c.nome || ''));
  const doTerreno = cams.map(c => TERRENO.test(c.nome || ''));
  const ids = { metalica: [], cobertura: [], outros: [], premoldado: [], terreno: [] };
  for (let i = 0; i < n; i++) {
    const m = fichas[i].m || '', q = porCamada.get(fichas[i].c);
    let s = 'outros';
    if (daCobertura[fichas[i].c]) s = 'cobertura';
    else if (doTerreno[fichas[i].c] || TERRENO.test(fichas[i].p || '') || TERRENO.test(fichas[i].n || '')) s = 'terreno';
    else if (CONCRETO.test(m)) s = 'premoldado';
    else if (!m || ACO.test(m)) s = q[1] * 2 >= q[0] ? 'premoldado' : NEOPRENE.test(m) ? 'outros' : 'metalica';
    ids[s].push(i);
  }
  return Object.entries(ids).filter(([, l]) => l.length)
    .map(([chave, l]) => ({ chave, nome: SISTEMAS[chave][0], cor: SISTEMAS[chave][1], n: l.length, ids: l }));
}
