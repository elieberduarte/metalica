// O sistema de cada peça (metálica, cobertura, pré-moldado, terreno, outros) — o mesmo no modo ver do PC (ver3d.js) e no
// celular (celular.js), 20/10: saiu do ver3d.js para os dois não divergirem. Só lê as fichas e as camadas do visor.
//
// TEL-02 (sistema/testes/REGRAS.md, aprovada pelo usuário em 22/10, depois de 4 correções no mesmo dia): toda peça cai num
// sistema cujo nome diz o que ela é — primeiro o nome da peça, depois a camada e o grupo, por último o material. Outros
// só com motivo conhecido (o motivo vai no nome: "Outros — PVC"); o material que ninguém reconhece vai para "Sem material
// — a definir", nunca para Outros calado. conferirSistemas confere o modelo inteiro.

/** O sistema de cada peça (usuário, Mercado Conceito, 16/10: "separar apenas pré-moldado (estrutura) e metálica para
 *  apresentação ao cliente"): pelo material — concreto é pré-moldado; aço (e a barra sem material) é metálica. O aço e o
 *  neoprene que vêm no modelo do pré-moldado (a camada dele é quase toda de concreto: as porcas, arruelas e cantoneiras
 *  das ligações dele) ficam com o pré-moldado. O resto com motivo conhecido (o PVC das descidas…) é Outros. */
export const SISTEMAS = { metalica: ['Metálica', '#2f6fd6'], cobertura: ['Cobertura — telhas, calhas e rufos', '#3aa69b'],
  outros: ['Outros', '#e08a1e'], premoldado: ['Pré-moldado (concreto)', '#8f969e'], arquitetonico: ['Arquitetônico (referência)', '#a58fc9'],
  terreno: ['Terreno, rua e calçada', '#b9a27a'], semmaterial: ['Sem material — a definir', '#d62828'] };
// a cobertura num sistema só (usuário, Mercado, 19/10: "não foi criado o grupo com as telhas, calhas e rufos" — as telhas
// caíam em Outros e as calhas e os rufos, de chapa galvanizada, em Metálica): a camada no grupo da cobertura (o que o
// lançamento de telhas faz) ou com o nome de telha, calha, rufo ou cumeeira — antes do material.
// O grupo vale pelas telhas, não pela palavra "cobertura" (usuário, SESI Chapecó, 22/10: as telhas do arquitetônico "não
// somem quando oculto essa camada" — o grupo "Cobertura frontal e eixo 1", de tesouras e pilares, caía na Cobertura e a
// camada "ARQ — Telhas", de material Concreto, no Pré-moldado); a camada pode ter prefixo ("ARQ — Telhas") e o material
// Telha também conta
const COBERTURA_GRUPO = /\b(telhas?|calhas?|rufos?|cumeeiras?)\b/i;
const COBERTURA_CAMADA = /(^|[—–-])\s*(telhas?|calhas?|rufos?|cumeeiras?)\b/i;
const TELHA = /^\s*telha/i;
// a pele da platibanda (o ACM) também é da cobertura (usuário, SESI Chapecó, 22/10: "a platibanda em acm ficou certa mas
// ela não está vinculada a camada da cobertura no sistema"): a camada de platibanda com peça que não é de aço — a
// estrutura metálica da platibanda (barra sem material ou de aço) continua na Metálica
const PLATIBANDA = /(^|[—–-])\s*platibandas?\b/i;
// e pelo nome da PEÇA, em qualquer camada (TEL-02, 3ª vez em 22/10, a verificação do SESI: 7 calhas e 3 rufos do
// arquitetônico na camada "ARQ — Outros", de Concreto, ficavam à vista com a Cobertura desligada) — como o Terreno já
// faz; "Suporte da calha" continua na Metálica (o nome começa pela peça)
const PECA_COBERTURA = /^\s*(telhas?|calhas?|rufos?|cumeeiras?)\b/i;
// o terreno, a rua e a calçada num sistema só (usuário, 16/10: "terreno, rua e calçada como uma camada única; parede
// pode deixar junto com o pré-moldado"): pelo nome da peça, antes do material (no IFC do Mercado são lajes de concreto);
// o muro e as vagas do estacionamento também (usuário, Mercado, 20/10: "colocar esses itens junto com a layer do
// terreno"), e a camada com esses nomes — para mandar à mão uma peça para o terreno: Editar → Camada "Terreno"
const TERRENO = /^\s*(terrenos?|ruas?|cal[çc]adas?|passeios?|muros?|vagas?|estacionamentos?)\b/i;
// o arquitetônico de referência num sistema só (TEL-02, 4ª vez — VER-10 da verificação do SESI Chapecó, 22/10: "o que são
// esses 'outros'?" — os forros, venezianas, brises e guarda-corpos do arquitetônico, de Vidro, caíam em Outros e as lajes,
// paredes e pilares dele, de Concreto, no Pré-moldado de uma obra metálica): a camada "ARQ — …" ou do grupo ARQUITETÔNICO,
// depois da Cobertura (as telhas, calhas, rufos e o ACM da platibanda do arquitetônico continuam saindo com ela) e do
// Terreno, e antes do material (o vidro do arquitetônico é Arquitetônico, não "Outros — vidro"); a camada "3 Arquitetura"
// do IFC do pré-moldado não entra (a parede fica com o pré-moldado, 16/10)
const ARQ_CAMADA = /^\s*ARQ\s*[—–-]/i;
const ARQ_GRUPO = /^\s*arquitet[ôo]nico\b/i;
const CONCRETO = /concret|fck|cimento|\bc\s?[1-9]\d\b/i;
// a armadura é do concreto (TEL-02, 22/10: as 1.876 armaduras do Sooro pré-moldado em Outros)
const ARMADURA = /armadur|rebar|\bca[-\s]?[56]0\b/i;
// o aço também pelo nome do material do IFC ("CPLAN_MATERIAL_PIEZA_METALICA_…", "…_TIRANTE…" do Capitão, 22/10)
const ACO = /steel|a[çc]o\b|astm|\ba36\b|a5\d\d|a32[05]|a307|s2\d\d|s3\d\d|ar\s?3\d\d|zar|galv|shore|neopren|elast|metal|tirante/i;
const NEOPRENE = /shore|neopren|elast/i;
// o IFC sem material, só com a cor ("Cor #ff0000": os parafusos do Sooro; "Cor #1f2430": os marcadores de furo) ou com o
// material automático ("<auto>7": as peças metálicas do Capitão, com o nome do material na camada) é como a barra sem
// material — metálica (TEL-02, decisão do usuário 22/10)
const SO_COR = /^\s*(cor\s*#[0-9a-f]{3,8}|<auto>\s*\d*)\s*$/i;
// a chapa é de aço mesmo com o material de armadura ("Aço (CA-60)" nas chapas do Bellacasa): o nome e a camada vêm antes
const CHAPA = /(^|[—–\s-])chapas?\b/i;
// Outros, com o motivo no nome (TEL-02, 22/10: "madeira e argamassa em Outros com o motivo")
const MOTIVOS = [['PVC', /pvc/i], ['neoprene', NEOPRENE], ['borracha', /borracha|rubber/i], ['madeira', /madeira|wood|timber/i],
  ['argamassa', /argamassa|mortar/i], ['tela', /\btela\b|\bmesh\b/i], ['vidro', /vidro|glass/i]];
const motivo = m => (MOTIVOS.find(([, re]) => re.test(m)) || [null])[0];

/** o sistema de cada peça: [chave por peça, motivo de Outros por peça] */
function classificar(visor) {
  const fichas = visor.fichas || [], n = Math.min(fichas.length, visor.nPecas);
  const porCamada = new Map();                                           // camada → [peças, de concreto]
  for (let i = 0; i < n; i++) {
    const q = porCamada.get(fichas[i].c) || [0, 0];
    q[0]++; if (CONCRETO.test(fichas[i].m || '')) q[1]++;
    porCamada.set(fichas[i].c, q);
  }
  const cams = (visor.cabecalho && visor.cabecalho.camadas) || [];
  const daCobertura = cams.map(c => COBERTURA_GRUPO.test(c.grupo || '') || COBERTURA_CAMADA.test(c.nome || ''));
  const daPlatibanda = cams.map(c => PLATIBANDA.test(c.nome || ''));
  const doTerreno = cams.map(c => TERRENO.test(c.nome || ''));
  const doArq = cams.map(c => ARQ_CAMADA.test(c.nome || '') || ARQ_GRUPO.test(c.grupo || ''));
  const sist = new Array(n), mot = new Array(n);
  for (let i = 0; i < n; i++) {
    const m = fichas[i].m || '', q = porCamada.get(fichas[i].c);
    let s;
    if (daCobertura[fichas[i].c] || TELHA.test(m) || PECA_COBERTURA.test(fichas[i].n || '')
        || (daPlatibanda[fichas[i].c] && m && !ACO.test(m) && !SO_COR.test(m))) s = 'cobertura';
    else if (doTerreno[fichas[i].c] || TERRENO.test(fichas[i].p || '') || TERRENO.test(fichas[i].n || '')) s = 'terreno';
    else if (doArq[fichas[i].c]) s = 'arquitetonico';
    else if (CONCRETO.test(m) || (ARMADURA.test(m) && !CHAPA.test(fichas[i].n || '') && !CHAPA.test((cams[fichas[i].c] || {}).nome || ''))) s = 'premoldado';
    else if (!m || SO_COR.test(m) || ACO.test(m)) {
      s = q[1] * 2 >= q[0] ? 'premoldado' : NEOPRENE.test(m) ? 'outros' : 'metalica';
      if (s === 'outros') mot[i] = 'neoprene';
    } else if ((mot[i] = motivo(m))) s = 'outros';
    else s = 'semmaterial';
    sist[i] = s;
  }
  return [sist, mot];
}

export function gruposDeSistema(visor) {
  const [sist, mot] = classificar(visor);
  const ids = { metalica: [], cobertura: [], outros: [], premoldado: [], arquitetonico: [], terreno: [], semmaterial: [] };
  sist.forEach((s, i) => ids[s].push(i));
  const motivos = [...new Set(ids.outros.map(i => mot[i]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  return Object.entries(ids).filter(([, l]) => l.length)
    .map(([chave, l]) => ({ chave, nome: chave === 'outros' && motivos.length ? `Outros — ${motivos.join(', ')}` : SISTEMAS[chave][0],
      cor: SISTEMAS[chave][1], n: l.length, ids: l }));
}

/** TEL-02, a conferência do modelo inteiro: cada peça comparada com o que os sinais dela dizem (o nome, a camada, o grupo, o
 *  material, o perfil). Um achado por (tipo, camada, material): {tipo, texto, n, ids}. Vazio = nada fora do lugar. */
const PERFIL_ACO = /^\s*(W|HP|IPE|HE[ABM]|UDC|Ue|U|C|Cx|Z|L|TB|Tubo|CH|PERFIL)\s*\d/i;
export function conferirSistemas(visor) {
  const [sist] = classificar(visor);
  const fichas = visor.fichas || [], cams = (visor.cabecalho && visor.cabecalho.camadas) || [];
  const achados = new Map();
  const anotar = (tipo, i, texto) => {
    const c = cams[fichas[i].c] || {}, k = `${tipo}|${c.nome || ''}|${fichas[i].m || ''}`;
    const a = achados.get(k) || { tipo, camada: c.nome || '', material: fichas[i].m || '', n: 0, ids: [], texto };
    a.n++; a.ids.push(i); achados.set(k, a);
  };
  sist.forEach((s, i) => {
    const f = fichas[i], c = cams[f.c] || {}, m = f.m || '', nome = f.n || '';
    const cob = PECA_COBERTURA.test(nome) || COBERTURA_CAMADA.test(c.nome || '') || COBERTURA_GRUPO.test(c.grupo || '') || TELHA.test(m);
    if (s === 'semmaterial') anotar('sem_material', i, 'sem material conhecido — a definir');
    else if (cob && s !== 'cobertura') anotar('cobertura_fora', i, 'telha, calha, rufo ou cumeeira fora da Cobertura');
    else if (!cob && (ARQ_CAMADA.test(c.nome || '') || ARQ_GRUPO.test(c.grupo || '')) && !['arquitetonico', 'terreno', 'cobertura'].includes(s))
      anotar('arquitetonico_fora', i, 'peça do arquitetônico de referência fora do Arquitetônico');
    else if (s === 'outros' && PERFIL_ACO.test(f.p || '')) anotar('aco_em_outros', i, 'perfil de aço em Outros');
  });
  return [...achados.values()].sort((a, b) => b.n - a.n)
    .map(a => ({ ...a, texto: `${a.n} ${a.n === 1 ? 'peça' : 'peças'}: ${a.texto} (camada "${a.camada}", material "${a.material || '—'}")` }));
}
