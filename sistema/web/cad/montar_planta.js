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

function base64DoArquivo(arquivo) {
  return new Promise((ok, erro) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).replace(/^data:[^,]*,/, ''));
    r.onerror = () => erro(r.error || new Error('não foi possível ler o arquivo'));
    r.readAsDataURL(arquivo);
  });
}

const ROTULO_CARGA = { telha: 'Peso das telhas', forro: 'Forro e instalações', sobrecarga: 'Sobrecarga de utilização',
  paineis: 'Painéis solares (reserva)', vento: 'Vento (V0)' };

export class MetodosMontarPlantaCAD {
  /** As folhas do DXF recebido (espaço do papel): número e título, carimbo, considerações de
   *  cálculo, normas e materiais — o servidor lê e grava no projeto (`projeto_recebido`). */
  async lerFolhasRecebidas() {
    if (!this.projeto) { this.aviso('Abra o desenho dentro de um projeto.', 'atencao'); return; }
    const entrada = el('input', { type: 'file', accept: '.dxf' });
    const arquivo = await new Promise((ok) => { entrada.addEventListener('change', () => ok(entrada.files && entrada.files[0])); entrada.click(); });
    if (!arquivo) return;
    this.dica('Lendo as folhas do DXF…');
    let r;
    try {
      r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/projeto-recebido`,
        { arquivo: arquivo.name, conteudo_b64: await base64DoArquivo(arquivo) });
    } catch (e) { this.aviso(`Não foi possível ler as folhas: ${e.message}`, 'erro', 0); this.dica(''); return; }
    this.dica('');
    const d = r.projeto_recebido || {};
    const c = d.carimbo || {};
    const itens = [el('div', { class: 'explica', texto: `"${d.arquivo}": ${d.folhas.length} folha(s), ${d.janelas} janela(s) de vista. Gravado no projeto; o cálculo de esforços parte destas cargas.` })];
    const linhasCarimbo = [['Cliente', c.cliente], ['Obra', c.obra], ['Local', c.local], ['Responsável', [c.responsavel, c.crea].filter(Boolean).join(' — ')],
      ['Revisão / data', [c.revisao, c.data].filter(Boolean).join(' · ')]].filter(([, v]) => v);
    if (linhasCarimbo.length) itens.push(el('table', { class: 'tabela-simples' }, ...linhasCarimbo.map(([k, v]) => el('tr', {}, el('th', { texto: k }), el('td', { texto: v })))));
    const cargas = Object.entries(d.cargas || {});
    if (cargas.length) {
      itens.push(el('h4', { texto: 'Considerações de cálculo' }));
      itens.push(el('table', { class: 'tabela-simples' }, ...cargas.map(([k, v]) => el('tr', {},
        el('th', { texto: ROTULO_CARGA[k] || v.texto }), el('td', { texto: `${numero(v.valor, 2)} ${v.unidade.toLowerCase().replace('m2', 'm²')}` })))));
    } else itens.push(el('div', { class: 'explica atencao', texto: 'Não achei o quadro "Considerações de cálculo" nas folhas.' }));
    if ((d.folhas || []).length) {
      itens.push(el('h4', { texto: 'Folhas' }));
      itens.push(el('table', { class: 'tabela-simples' }, ...d.folhas.map(f => el('tr', {}, el('th', { texto: f.numero }), el('td', { texto: f.titulo || '—' }), el('td', { texto: f.formato || '' })))));
    }
    if ((r.preenchidos || []).length) itens.push(el('div', { class: 'explica', texto: `Preenchido no projeto pelo carimbo: ${r.preenchidos.join(', ')}.` }));
    await this.dialogo({ titulo: 'Folhas do projeto recebido', corpo: el('div', {}, ...itens), ok: 'Fechar' });
  }

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
    // as outras plantas com nível no título (mezanino, base e cobertura da caixa d'água…)
    const RX_NIVEL = /N[ÍI]VEL\s*(?:DE\s*)?\+?\s*(\d{1,3}[.,]\d{1,3})/i;
    const outras = [];
    const tabOutras = el('div', { class: 'campos' });
    for (const t of titulos) {
      const m = t.match(RX_NIVEL);
      if (!m) continue;
      const usar = el('input', { type: 'checkbox', checked: !semAcento(t).startsWith(semAcento(p.planta)) });
      const nv = el('input', { type: 'text', value: m[1].replace('.', ','), size: 6, title: 'Nível, em metros: o banzo inferior das treliças e o topo das vigas dessa planta' });
      outras.push({ titulo: t, usar, nv });
      tabOutras.append(el('label', { class: 'linha' }, usar, ' ' + t), nv);
    }
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
      ...(outras.length ? [el('fieldset', { class: 'montagem' }, el('legend', { texto: 'Outras plantas, cada uma no seu nível' }),
        el('div', { class: 'explica', texto: 'Vigas VM e treliças nomeadas dessas plantas entram no nível ao lado (m), alinhadas pelos balões dos eixos; o pilar sobe até a peça mais alta que tiver em cima. Desmarque a da planta estrutural e as que não são de estrutura.' }),
        tabOutras)] : []),
      el('label', { class: 'linha' }, quadro, ' Desenhar, abaixo do projeto, o quadro com só o que virou modelo (plantas e elevações usadas)'),
      el('label', { class: 'linha' }, ifc, ' Gravar também o IFC'));
    if (await this.dialogo({ titulo: 'Montar o 3D pela planta', corpo, ok: 'Montar' }) !== 'ok') return;
    this.dica('Montando o modelo 3D pela planta…');
    let r;
    try {
      r = await postar(rota, {
        parametros: { planta: planta.value, nivel: lerMetros(nivel.value), locacao: locacao.value, base: lerMetros(base.value), tercas: tercas.value, aco: aco.value.trim(),
          outras: outras.filter(o => o.usar.checked && o.titulo !== planta.value).map(o => ({ planta: o.titulo, nivel: lerMetros(o.nv.value) })) },
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
    const trl = r.trelicas;
    if (trl && trl.total) itens.push(el('div', { class: 'explica' + (trl.conferir ? ' atencao' : '') },
      `Treliças lidas: ${trl.total} elevação(ões), ${trl.conferir ? `${trl.conferir} com algo a conferir` : 'nada a conferir'} — `,
      el('a', { href: `/trelicas?projeto=${encodeURIComponent(this.projeto)}`, target: '_self', texto: 'ver cada elevação ao lado do bloco que entrou' }), '.'));
    const enc = z.encaixe;
    if (enc && enc.blocos) itens.push(el('div', { class: 'explica' + (enc.a_conferir ? ' atencao' : ''), texto: `Encaixe dos blocos (cada treliça como a elevação desenha, sem esticar): ${enc.justos} de ${enc.blocos} com até 5 cm de diferença do vão na planta; ${enc.a_conferir ? `${enc.a_conferir} com mais de 20 cm — estão nos avisos, para conferir com o projeto` : 'nenhum com mais de 20 cm'}.` }));
    if (dif.length) itens.push(el('div', { class: 'explica atencao', texto: 'Quantidade diferente da que o título pede: ' + dif.map(c => `${c.peca} (modelo ${c.modelo}, projeto ${c.projeto})`).join('; ') + '.' }));
    const sem = Object.entries(z.nomes_sem_elevacao || {});
    if (sem.length) itens.push(el('div', { class: 'explica atencao', texto: 'Nome na planta sem elevação no desenho (ficaram de fora): ' + sem.map(([k, q]) => `${k} (${q}×)`).join(', ') + '.' }));
    for (const o of (z.outras_plantas || [])) itens.push(el('div', { class: 'explica', texto: `${o.planta}: ${o.pecas} peça(s) no nível ${numero(o.nivel / 1000, 2)} m (alinhada por ${o.baloes} balões).` }));
    if (z.planta_sem_nome) itens.push(el('div', { class: 'explica', texto: `${z.planta_sem_nome} peça(s) da planta sem nome escrito ficaram de fora.` }));
    const avisos = r.avisos || [];
    for (const a of avisos.slice(0, 8)) itens.push(el('div', { class: 'explica atencao', texto: a }));
    if (avisos.length > 8) {
      const det = el('details', { class: 'explica' }, el('summary', { texto: `… e mais ${avisos.length - 8} aviso(s)` }));
      const ul = el('ul', { class: 'avisos-montagem' });
      for (const a of avisos.slice(8)) ul.append(el('li', { texto: a }));
      det.append(ul);
      itens.push(det);
    }
    if (r.quadro) itens.push(el('div', { class: 'explica', texto: `O quadro "PROJETO CONSIDERADO NO MODELO 3D" está no desenho, abaixo do projeto, com ${(r.quadro.grupos || []).length} grupo(s): as plantas e as elevações que viraram peça, sem o resto (camadas QUADRO …). A próxima montagem refaz o quadro.` }));
    if (r.ifc) itens.push(el('div', { class: 'explica' }, 'IFC: ', el('a', { href: r.ifc.url, download: r.ifc.nome, texto: `${r.ifc.nome} (${numero(r.ifc.tamanho_kb, 0)} kB)` })));
    if (await this.dialogo({ titulo: 'Modelo 3D montado pela planta', corpo: el('div', {}, ...itens), ok: 'Abrir o modelo 3D', cancelar: r.quadro ? 'Ver o quadro no desenho' : undefined }) === 'ok') { (window.metalicaNavegar || ((u) => { location.href = u; }))(this.urlDoEditor()); return; }
    if (r.quadro && r.quadro.caixa) this.tela.enquadrar(r.quadro.caixa, 0.04);
  }
}
