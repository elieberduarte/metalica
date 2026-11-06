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
