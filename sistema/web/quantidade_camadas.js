// A quantidade de cada camada no painel Camadas — do modo ver e do editor 3D (usuário, 06/11, pelo GESTÃO: "criar na
// ferramenta de camadas uma informação a mais ao lado, por ex. dos isopainéis, telhas (m²) — perfil, chapa (kg)").
//
// O peso é o do RESUMO DA OBRA, não uma conta do 3D: "preciso que ambos sejam iguais, não posso mostrar para o fornecedor um
// peso na apresentação e na proposta outro" (usuário, 06/11). O servidor guarda, a cada Resumo da obra, o aço (kg), as telhas
// (m²) e a funilaria (m) de cada camada — a soma é o número do resumo — e diz se o modelo mudou depois dele. O arquitetônico
// (referência, fora da proposta) vem da conta do 3D: parede, laje e esquadria em m², o resto em unidades.
// Rota: GET /api/projetos/<projeto>/camadas-quantidade (app.quantidade_das_camadas).

const inteiro = (v) => Math.round(v).toLocaleString('pt-BR');

/** Busca as quantidades do projeto; null quando não há (servidor antigo, projeto sem pasta). */
export async function carregarQuantidades(projeto) {
  if (!projeto) return null;
  try {
    const r = await fetch(`/api/projetos/${encodeURIComponent(projeto)}/camadas-quantidade`, { cache: 'no-store' });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  }
}

/** {kg, m2, m, un} da camada, ou null quando o resumo e o arquitetônico não falam dela. */
export function quantidadeDa(dados, camada) {
  if (!dados) return null;
  const r = (dados.camadas || {})[camada], a = (dados.arq || {})[camada];
  if (!r && !a) return null;
  return { kg: (r && r.kg) || 0, m2: ((r && r.m2) || 0) + ((a && a.m2) || 0), m: (r && r.m) || 0, un: (a && a.un) || 0 };
}

/** A soma de um grupo: cada unidade separada (o grupo com unidades misturadas mostra "10.729 m² · 104 un"). */
export function somarQuantidades(lista) {
  const t = { kg: 0, m2: 0, m: 0, un: 0 };
  let alguma = false;
  for (const q of lista) {
    if (!q) continue;
    alguma = true;
    for (const k in t) t[k] += q[k] || 0;
  }
  return alguma ? t : null;
}

/** "12.280 kg", "8.641 m²", "10.729 m² · 104 un" — só as unidades que a camada tem; "" sem quantidade. */
export function textoQuantidade(q) {
  if (!q) return '';
  const p = [];
  if (q.kg >= 0.5) p.push(`${inteiro(q.kg)} kg`);
  if (q.m2 >= 0.5) p.push(`${inteiro(q.m2)} m²`);
  if (q.m >= 0.5) p.push(`${inteiro(q.m)} m`);
  if (q.un) p.push(`${inteiro(q.un)} un`);
  return p.join(' · ');
}

/**
 * O que a coluna mostra para a camada: {texto, dica}. Sem resumo com as camadas, a camada que não é do arquitetônico fica com
 * "—" e a dica do porquê (usuário, 06/11, no GN: "porque tem várias camadas sem informação?" — o resumo era de antes das
 * camadas e as linhas ficavam vazias, sem explicação à vista).
 */
export function textoDaCamada(dados, camada) {
  const q = quantidadeDa(dados, camada);
  if (q) return { texto: textoQuantidade(q), dica: '' };
  const nota = notaDoResumo(dados);
  if (nota && nota.situacao === 'sem') return { texto: '—', dica: 'Sem o peso desta camada: gere o Resumo da obra (o peso é o dele, o mesmo da proposta).' };
  return { texto: '', dica: '' };
}

/** O mesmo, para o grupo: a soma do que as camadas têm (a camada sem número mostra o "—" dela); "—" quando nenhuma tem e
 *  falta o resumo. */
export function textoDoGrupo(dados, camadas) {
  const q = somarQuantidades(camadas.map(c => quantidadeDa(dados, c)));
  const nota = notaDoResumo(dados);
  const falta = nota && nota.situacao === 'sem' && camadas.some(c => !quantidadeDa(dados, c));
  if (q) return { texto: textoQuantidade(q), dica: falta ? 'Só a soma das camadas que têm quantidade: as outras esperam o Resumo da obra.' : '' };
  return falta ? { texto: '—', dica: 'Sem o peso destas camadas: gere o Resumo da obra (o peso é o dele, o mesmo da proposta).' } : { texto: '', dica: '' };
}

/** O nível do piso (±0,00) entre os níveis do projeto: o que diz "±0" ou "piso" mais perto do zero, ou o de z = 0; null sem. */
export function nivelDoPiso(niveis) {
  const l = (niveis || []).filter(n => n && Number.isFinite(+n.z));
  const zero = l.filter(n => /±\s*0|\+\/-\s*0/.test(n.nome || ''));
  const piso = zero.length ? zero : l.filter(n => /\bpiso\b/i.test(n.nome || ''));
  if (piso.length) return +piso.reduce((a, b) => (Math.abs(+b.z) < Math.abs(+a.z) ? b : a)).z;
  return l.some(n => +n.z === 0) ? 0 : null;
}

/**
 * A linha do rodapé do modo ver (usuário, 10/11, no GN: "preciso que revise isso para aparecer algumas informações rápidas
 * aqui: Área obra - Altura - Qtd peças - Peso estrutura"). A área e o peso são os do resumo da obra — os da proposta e do kg/m²
 * (peso-na-tela-igual-ao-resumo); a altura, do piso (±0,00 dos níveis; sem ele, o pé do modelo) ao ponto mais alto do modelo;
 * as peças, as do modelo. o = {pecas, zTopo, zPe, niveis} (z em mm do projeto).
 */
export function linhaDaObra(dados, o) {
  const p = [];
  const ob = (dados && dados.obra) || {}, r = (dados && dados.resumo) || {};
  if (ob.area_m2 >= 0.5) p.push(`Área ${inteiro(ob.area_m2)} m²`);
  const z0 = nivelDoPiso(o.niveis);
  const base = z0 !== null ? z0 : o.zPe;
  if (Number.isFinite(o.zTopo) && Number.isFinite(base) && o.zTopo > base) {
    p.push(`Altura ${((o.zTopo - base) / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} m`);
  }
  if (o.pecas) p.push(`${inteiro(o.pecas)} peças`);
  if (ob.peso_aco >= 0.5) p.push(`Estrutura ${inteiro(ob.peso_aco)} kg${r.atual ? '' : ` (resumo de ${quando(r.gerado)}, antes da última mudança do modelo)`}`);
  else if (dados) p.push('área e peso: gere o Resumo da obra');
  return p.join(' · ');
}

/** A tela que gera o Resumo da obra (a lista de materiais, aba Resumos). */
export const linkDoResumo = (projeto) => `/materiais?projeto=${encodeURIComponent(projeto || '')}#resumos`;

function quando(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || '';
  const dois = (n) => String(n).padStart(2, '0');
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)} ${dois(d.getHours())}:${dois(d.getMinutes())}`;
}

/**
 * A linha de cima do painel: de onde vêm os números. {texto, situacao} — situacao 'atual' (o resumo é do modelo de agora),
 * 'velho' (o modelo mudou depois: os números são os do resumo, que é o da proposta, e o painel os mostra apagados) ou
 * 'sem' (sem resumo com as camadas: o peso não aparece). null sem dados.
 */
export function notaDoResumo(dados) {
  if (!dados) return null;
  const r = dados.resumo || {};
  if (!r.gerado) {
    return { situacao: 'sem', texto: 'Sem resumo da obra: o peso de cada camada aparece depois do Resumo da obra (o mesmo número da proposta).' };
  }
  if (!r.tem_camadas) {
    return { situacao: 'sem', texto: `O resumo da obra de ${quando(r.gerado)} é de antes das quantidades por camada: gere o Resumo da obra de novo para ver o peso de cada camada.` };
  }
  if (!r.atual) {
    return { situacao: 'velho', texto: `O modelo mudou depois do resumo da obra de ${quando(r.gerado)}: as quantidades são as dele (as da proposta). Gere o Resumo de novo para atualizar.` };
  }
  return { situacao: 'atual', texto: `Quantidades do resumo da obra de ${quando(r.gerado)} — as mesmas da proposta.` };
}
