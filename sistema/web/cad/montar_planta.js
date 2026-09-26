// CAD 2D: projeto recebido sem 3D → modelo montado pela planta (nucleo3d/de_planta.py).
//
// O desenho do projetista traz a planta estrutural com o nome de cada treliça escrito na
// linha dela, a elevação de cada treliça com o título "TESOURA 1 - 7X", a locação dos
// pilares e a planta das terças. O diálogo só pergunta quais são essas plantas (pelos
// títulos que o desenho tem) e o nível do banzo inferior; o servidor monta o modelo e
// devolve a conferência com as quantidades que o próprio projeto pede.

const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

async function postar(rota, corpo) {
  let r;
  try {
    r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo || {}) });
  } catch (e) { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}

const semAcento = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/\s+/g, '');
const metros = (mm) => numero((Number(mm) || 0) / 1000, 2);
const lerMetros = (s) => Math.round(parseFloat(String(s || '0').replace(',', '.')) * 1000) || 0;

function seletor(titulos, padrao, comNenhuma) {
  const s = el('select', {});
  if (comNenhuma) s.append(el('option', { value: '', texto: '(nenhuma)' }));
  const alvo = semAcento(padrao);
  let escolhido = false;
  for (const t of titulos) {
    const o = el('option', { value: t, texto: t });
    if (!escolhido && alvo && semAcento(t).startsWith(alvo)) { o.selected = true; escolhido = true; }
    s.append(o);
  }
  return s;
}

export class MetodosMontarPlantaCAD {
  async dialogoMontarPelaPlanta() {
    if (!this.projeto) { this.aviso('Abra o desenho dentro de um projeto.', 'atencao'); return; }
    await this.salvar({ avisar: false });
    const rota = `/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho || 'desenho')}/montar-pela-planta`;
    let sug;
    try { sug = await postar(rota, { sugerir: true }); } catch (e) { this.aviso(`Não foi possível ler o desenho: ${e.message}`, 'erro', 0); return; }
    const p = sug.padrao || {};
    const titulos = sug.titulos || [];
    if (!titulos.length) { this.aviso('Este desenho não tem nenhum título de planta ("PLANTA …", "LOCAÇÃO …").', 'atencao', 0); return; }
    const planta = seletor(titulos, p.planta, false);
    const nivel = el('input', { type: 'text', value: metros(p.nivel), size: 6, title: 'Nível do eixo do banzo inferior das treliças, em metros' });
    const locacao = seletor(titulos, p.locacao, true);
    const base = el('input', { type: 'text', value: metros(p.base), size: 6, title: 'Nível da base dos pilares, em metros' });
    const tercas = seletor(titulos, p.tercas, true);
    const aco = el('input', { type: 'text', value: p.aco || 'ASTM A36', size: 14 });
    const modo = el('select', {}, el('option', { value: 'substituir', texto: 'Substituir o modelo 3D (o atual vai para o histórico)' }),
      el('option', { value: 'acrescentar', texto: 'Acrescentar ao modelo 3D' }));
    const ifc = el('input', { type: 'checkbox' });
    const quadro = el('input', { type: 'checkbox', checked: true });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'O modelo sai da planta estrutural: cada linha com nome ("TESOURA 1", "PAINEL 8", "TRANSIÇÃO 4") recebe a treliça da elevação de mesmo nome ("TESOURA 1 - 7X"), em pé, com o banzo inferior no nível abaixo. A peça curva na planta sai calandrada. Os pilares vêm da locação (nome "PM3(200X70X20X2,65)" sobre a placa) e as terças, correntes e contraventos da planta das terças; as plantas são alinhadas pelos balões dos eixos.' }),
      el('div', { class: 'campos' },
        el('label', { texto: 'Planta estrutural' }), planta,
        el('label', { texto: 'Banzo inferior (m)' }), nivel,
        el('label', { texto: 'Locação dos pilares' }), locacao,
        el('label', { texto: 'Base dos pilares (m)' }), base,
        el('label', { texto: 'Planta das terças' }), tercas,
        el('label', { texto: 'Aço' }), aco,
        el('label', { texto: 'Modelo' }), modo),
      el('label', { class: 'linha' }, quadro, ' Desenhar, abaixo do projeto, o quadro com só o que virou modelo (plantas e elevações usadas)'),
      el('label', { class: 'linha' }, ifc, ' Gravar também o IFC'));
    if (await this.dialogo({ titulo: 'Montar o 3D pela planta', corpo, ok: 'Montar' }) !== 'ok') return;
    this.dica('Montando o modelo 3D pela planta…');
    let r;
    try {
      r = await postar(rota, {
        parametros: { planta: planta.value, nivel: lerMetros(nivel.value), locacao: locacao.value, base: lerMetros(base.value), tercas: tercas.value, aco: aco.value.trim() },
        modo: modo.value, ifc: ifc.checked, quadro: quadro.checked,
      });
    } catch (e) { this.dica(''); this.aviso(`Não foi possível montar: ${e.message}`, 'erro', 0); return; }
    this.dica('Modelo 3D montado.');
    // o servidor desenhou o quadro no desenho: a tela passa a mostrar o que está gravado
    if (r.quadro) await this.abrirDesenho(this.nomeDesenho);
    const z = r.resumo || {};
    const pj = z.projeto || {};
    const o = z.orientacao || {};
    const linha = (rotulo, modelo, projeto) => el('tr', { class: projeto === undefined || projeto === null ? '' : (modelo === projeto ? 'ok' : 'difere') },
      el('td', { texto: rotulo }), el('td', { texto: numero(modelo || 0) }), el('td', { texto: projeto === undefined || projeto === null ? '—' : numero(projeto) }));
    const tabela = el('table', { class: 'conferencia' },
      el('tr', {}, el('th', { texto: 'Peças' }), el('th', { texto: 'No modelo' }), el('th', { texto: 'O projeto pede' })),
      linha('Treliças (todas as famílias)', z.trelicas),
      linha('Pilares', z.pilares, pj.pilares),
      linha('Terças', z.tercas, pj.tercas),
      linha('Correntes', z.correntes, pj.correntes),
      linha('Esticadores', z.esticadores, pj.esticadores),
      linha('Contraventos', z.contraventamentos, pj.contraventos),
      linha('Vigas VM', z.vigas));
    const dif = (r.conferencia || []).filter(c => !c.ok);
    const itens = [
      el('div', { class: 'explica', texto: `${numero(z.barras || 0)} barra(s), ${numero(z.calandradas || 0)} peça(s) calandrada(s), ${numero(z.posicoes || 0)} posição(ões), ${numero(z.conjuntos || 0)} conjunto(s), ${numero(z.peso_kg || 0)} kg de aço.` }),
      tabela,
      el('div', { class: 'explica', texto: `Sentido das treliças: ${o.pelas_marcas || 0} decidida(s) pelas marcas de apoio de terça (ST) da elevação, ${o.pelas_alturas || 0} pelo encontro dos banzos; as outras seguem o costume do desenho (ponta esquerda da elevação no menor x). Confira no 3D as de uma água só.` }),
    ];
    if (dif.length) itens.push(el('div', { class: 'explica atencao', texto: 'Quantidade diferente da que o título pede: ' + dif.map(c => `${c.peca} (modelo ${c.modelo}, projeto ${c.projeto})`).join('; ') + '.' }));
    const sem = Object.entries(z.nomes_sem_elevacao || {});
    if (sem.length) itens.push(el('div', { class: 'explica atencao', texto: 'Nome na planta sem elevação no desenho (ficaram de fora): ' + sem.map(([k, q]) => `${k} (${q}×)`).join(', ') + '.' }));
    if (z.planta_sem_nome) itens.push(el('div', { class: 'explica', texto: `${z.planta_sem_nome} peça(s) da planta sem nome escrito ficaram de fora.` }));
    for (const a of (r.avisos || []).slice(0, 8)) itens.push(el('div', { class: 'explica atencao', texto: a }));
    if (r.quadro) itens.push(el('div', { class: 'explica', texto: `O quadro "PROJETO CONSIDERADO NO MODELO 3D" está no desenho, abaixo do projeto, com ${(r.quadro.grupos || []).length} grupo(s): as plantas e as elevações que viraram peça, sem o resto (camadas QUADRO …). A próxima montagem refaz o quadro.` }));
    if (r.ifc) itens.push(el('div', { class: 'explica' }, 'IFC: ', el('a', { href: r.ifc.url, download: r.ifc.nome, texto: `${r.ifc.nome} (${numero(r.ifc.tamanho_kb, 0)} kB)` })));
    if (await this.dialogo({ titulo: 'Modelo 3D montado pela planta', corpo: el('div', {}, ...itens), ok: 'Abrir o modelo 3D', cancelar: r.quadro ? 'Ver o quadro no desenho' : undefined }) === 'ok') { location.href = this.urlDoEditor(); return; }
    if (r.quadro && r.quadro.caixa) this.tela.enquadrar(r.quadro.caixa, 0.04);
  }
}
