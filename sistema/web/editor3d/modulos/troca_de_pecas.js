// Métodos do editor 3D: Trocar parafuso e trocar perfil.
//
// Saíram de editor.js (que tinha quase 5 mil linhas) sem mudar o corpo: esta classe só
// guarda os métodos, e editor.js os copia para Editor.prototype (aplicarMetodos).

import { refazerFurosEditor } from '../ferramentas/_furar.js';
import { CLASSES as CLASSES_PARAFUSO, DIAMETROS as DIAMETROS_PARAFUSO, furoDoParafuso, geometriaDoParafuso, nomeDoParafuso, quadroDoParafuso, tamanhoDoFixador } from '../ferramentas/parafuso.js';
import { api } from '../nucleo/api.js';
import { ComandoAlterar } from '../nucleo/comandos.js';
import { clonar } from '../nucleo/documento.js';
import { BITOLAS, lerPerfil, nomeDoPerfil, trocarSecao } from '../nucleo/trocar_perfil.js';
import { $, el, numero } from '../editor.js';

export class MetodosTrocaDePecas {
  /**
   * Troca o perfil de peças importadas do IFC (perfis U e Ue/C formados a frio): a malha
   * de cada peça muda de seção (trocar_perfil.js), e a marca `perfil` passa a ser a nova —
   * então o detalhamento, a lista de materiais e o cálculo saem com ela. Alcance: as
   * peças escolhidas, a posição inteira ou todas com o mesmo perfil. Desfaz com Ctrl+Z.
   */
  /** Parafuso com tamanho (do IFC, "BOLT (A) 12x35", ou posto no editor); porca e arruela soltas não. */
  _ehParafuso(e) {
    if (!e || e.tipo !== 'solido') return false;
    const t = tamanhoDoFixador(e);
    return !!(t && !t.semTamanho && t.L > 0);
  }

  /**
   * Troca de parafuso: diâmetro, comprimento e classe dos selecionados (ou de todos com o
   * mesmo nome no modelo). A peça 3D é refeita no mesmo lugar — o apoio da cabeça, o eixo e
   * a pega vêm do registro do editor ou da própria malha do IFC — com o nome "BOLT (classe)
   * dxL" que a lista de materiais e o detalhamento leem. Os furos abertos pelo editor para
   * esses parafusos são refeitos com o diâmetro novo (d + 1), a partir da malha guardada
   * antes deles; os furos que vieram do IFC ficam como estão.
   */
  async dialogoTrocarParafuso(ids) {
    const doc = this.documento;
    const sel = ids.map(i => doc.get(i)).filter(e => this._ehParafuso(e));
    if (!sel.length) { this.aviso('Selecione um parafuso com tamanho (BOLT … dxL).', 'atencao'); return; }
    const t0 = tamanhoDoFixador(sel[0]);
    const nomes = new Set(sel.map(e => e.nome));
    const iguais = nomes.size === 1 ? [...doc.entidades.values()].filter(e => e.tipo === 'solido' && e.nome === sel[0].nome) : sel;
    const num = (x) => String(Math.round(x * 10) / 10).replace('.', ',');
    const selD = el('select', { title: 'Diâmetro nominal (mm)' });
    for (const d of DIAMETROS_PARAFUSO) selD.append(el('option', { value: String(d), texto: `M${d}` }));
    if (!DIAMETROS_PARAFUSO.includes(t0.d)) selD.append(el('option', { value: String(t0.d), texto: `M${num(t0.d)}` }));
    selD.value = String(t0.d);
    const inL = el('input', { type: 'number', min: '10', step: '5', value: String(t0.L), title: 'Comprimento do corpo (mm)' });
    const selC = el('select', { title: 'Classe (vai no nome e na lista de materiais)' });
    selC.append(el('option', { value: '', texto: 'sem classe (A)' }));
    for (const c of CLASSES_PARAFUSO) selC.append(el('option', { value: c, texto: c }));
    selC.value = CLASSES_PARAFUSO.includes(t0.classe) ? t0.classe : '';
    const todos = el('input', { type: 'checkbox' });
    const novoRotulo = el('strong');
    const atualizar = () => { novoRotulo.textContent = nomeDoParafuso(selC.value, +selD.value, +inL.value || t0.L); };
    for (const x of [selD, inL, selC]) x.addEventListener('input', atualizar);
    atualizar();
    const g = el('div', { class: 'campos' },
      el('label', { texto: 'Diâmetro' }), selD,
      el('label', { texto: 'Comprimento (mm)' }), inL,
      el('label', { texto: 'Classe' }), selC);
    const corpo = el('div', {},
      el('p', { texto: sel.length === 1 ? `Parafuso selecionado: ${sel[0].nome}.` : `${sel.length} parafusos selecionados (${[...nomes].slice(0, 4).join(', ')}${nomes.size > 4 ? '…' : ''}).` }),
      g, el('p', {}, 'Fica: ', novoRotulo));
    if (iguais.length > sel.length) {
      corpo.append(el('label', { class: 'linha-opcao' }, todos, ` todos os ${iguais.length} "${sel[0].nome}" do modelo`));
    }
    corpo.append(el('p', { class: 'nota', texto: 'A peça muda no mesmo lugar (a cabeça no mesmo apoio, a porca na mesma pega). Os furos abertos pelo editor para estes parafusos passam para o diâmetro novo (d + 1 mm); os furos que vieram do IFC ficam como estão — confira na peça se o diâmetro subiu.' }));
    if (await this.dialogo({ titulo: 'Trocar parafuso', corpo, ok: 'Trocar' }) !== 'ok') return;
    const d = +selD.value, L = +inL.value, classe = selC.value;
    if (!(d > 0) || !(L > 0)) { this.aviso('Diâmetro e comprimento precisam ser maiores que zero.', 'atencao'); return; }
    const alvo = todos.checked ? iguais : sel;
    const nome = nomeDoParafuso(classe, d, L);
    const mud = {};
    let falhas = 0;
    const agora = new Date().toISOString().slice(0, 19);
    for (const e of alvo) {
      const q = quadroDoParafuso(e);
      if (!q) { falhas++; continue; }
      const gg = geometriaDoParafuso(d, L, q.ponto, q.eixo.map(v => -v), q.pega);
      const atributos = clonar(e.atributos || {});
      atributos.marcas = { ...(atributos.marcas || {}), perfil: nome };
      atributos.parafuso = { ...(atributos.parafuso || {}), d, L, classe, ponto: q.ponto, eixo: q.eixo, ...(q.pega ? { pega: q.pega } : {}) };
      atributos.trocas_de_parafuso = [...(atributos.trocas_de_parafuso || []), { de: e.nome, para: nome, data: agora }];
      mud[e.id] = { vertices: gg.vertices, faces: gg.faces, arestas_vivas: [], nome, atributos };
    }
    // os furos do editor desses parafusos, refeitos com o diâmetro novo
    const trocados = new Set(Object.keys(mud));
    let refeitas = 0, semBase = 0;
    for (const p of doc.entidades.values()) {
      const regs = p.tipo === 'solido' && p.atributos && p.atributos.furos_editor;
      if (!regs || !regs.some(r => trocados.has(r.parafuso))) continue;
      const novos = regs.map(r => (trocados.has(r.parafuso) ? { ...r, d: furoDoParafuso(d) } : r));
      const rf = refazerFurosEditor(p, novos);
      if (!rf) { semBase++; continue; }
      mud[p.id] = { vertices: rf.vertices, faces: rf.faces, atributos: { ...clonar(p.atributos), furos_editor: rf.registros } };
      refeitas++;
    }
    const n = trocados.size;
    if (!n) { this.aviso('Não deu para achar o eixo dos parafusos selecionados; nada mudou.', 'atencao'); return; }
    this.executar(new ComandoAlterar(mud, `Trocar parafuso → ${nome}`));
    this.aviso(`${n} parafuso(s) passaram para ${nome}` +
               (refeitas ? ` · furos refeitos com Ø${num(furoDoParafuso(d))} em ${refeitas} peça(s)` : '') +
               (semBase ? ` · ${semBase} peça(s) com furo feito por versão anterior ficaram com o furo antigo` : '') +
               (falhas ? ` · ${falhas} sem eixo reconhecível ficaram como estavam` : '') + '.', 'info', 12000);
  }

  async dialogoTrocarPerfil(ids) {
    const ents = ids.map(id => this.documento.get(id)).filter(e => e && e.tipo === 'solido');
    if (!ents.length) return;
    const marcas0 = (ents[0].atributos || {}).marcas || {};
    const antigoNome = marcas0.perfil;
    const todas = [...this.documento.entidades.values()].filter(e => e.tipo === 'solido' && e.atributos && e.atributos.marcas);
    const daPosicao = marcas0.posicao ? todas.filter(e => e.atributos.marcas.posicao === marcas0.posicao && e.atributos.marcas.perfil === antigoNome) : [];
    const doPerfil = todas.filter(e => e.atributos.marcas.perfil === antigoNome);
    const campo = el('input', { type: 'text', value: '', placeholder: 'ex.: 127X50X17X#14', spellcheck: 'false', list: 'perfis-do-catalogo' });
    // sugestões: os perfis da mesma família no catálogo (séries e fornecedores), no jeito da fábrica
    const sugestoes = el('datalist', { id: 'perfis-do-catalogo' });
    const pa = lerPerfil(antigoNome);
    if (pa) {
      fetch(`/api/catalogo/pecas?familia=${pa.familia}`).then(r => r.json()).then(d => {
        const vistos = new Set();
        for (const it of (d.itens || [])) {
          const p = lerPerfil(it.nome.replace(/\s*\(FF\)\s*$/, ''));
          if (!p || p.familia !== pa.familia) continue;
          // espessura de bitola vai como a fábrica escreve (#14 = 2,00); as outras em mm
          const bitola = Object.keys(BITOLAS).find(k => Math.abs(BITOLAS[k] - p.t) < 0.005);
          const esp = bitola ? `#${bitola}` : p.t.toFixed(2);
          const nome = pa.prefixo + [p.H, p.B, ...(p.D ? [p.D] : []), esp].join('X');
          if (vistos.has(nome)) continue;
          vistos.add(nome);
          const fab = (it.fabricantes || []).map(f => f.split(/ [(–]/)[0]).filter(Boolean);
          sugestoes.append(el('option', { value: nome,
            texto: `${it.nome}${bitola ? ` (#${bitola} = ${p.t.toFixed(2).replace('.', ',')} mm)` : ''} · ${numero(it.massa, 2)} kg/m${fab.length ? ' · ' + [...new Set(fab)].join(', ') : ''}` }));
        }
      }).catch(() => {});
      // perfis da fábrica já usados (fora do catálogo), da mesma família
      fetch('/api/fabrica').then(r => r.json()).then(d => {
        for (const reg of (d.perfis || [])) {
          const p = lerPerfil(reg.perfil);
          if (!p || p.familia !== pa.familia) continue;
          const desde = String(reg.primeiro_uso || '').slice(0, 10).split('-').reverse().join('/');
          sugestoes.append(el('option', { value: reg.perfil,
            texto: `perfil da fábrica · tira ${numero(reg.desenvolvido || 0, 0)} mm · desde ${desde} · ${(reg.projetos || []).length} projeto(s)` }));
        }
      }).catch(() => {});
    }
    const alcance = el('select', {},
      el('option', { value: 'selecao', texto: ents.length > 1 ? `as ${ents.length} peças selecionadas` : 'só esta peça' }),
      ...(daPosicao.length > ents.length ? [el('option', { value: 'posicao', texto: `a posição ${marcas0.posicao} inteira (${daPosicao.length} peças)`, selected: 'selected' })] : []),
      el('option', { value: 'perfil', texto: `todas as peças ${antigoNome} do modelo (${doPerfil.length})` }));
    const aviso = el('div', { class: 'explica', texto: '' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `Perfil atual: ${antigoNome}. Digite o novo como a fábrica escreve — altura × aba × enrijecedor × espessura; a espessura pode ser a bitola (#14 = 2,00 mm, #13 = 2,25, #12 = 2,65, #11 = 3,00, #10 = 3,35, #9 = 3,75, #8 = 4,25, #16 = 1,50). A peça muda de seção no 3D (as espessuras, abas e enrijecedores ficam exatos; os furos acompanham), e o detalhamento e a lista de materiais passam a sair com o perfil novo — gere-os de novo depois.` }),
      el('div', { class: 'campos' }, el('label', { texto: 'Novo perfil' }), campo, el('label', { texto: 'Aplicar em' }), alcance),
      sugestoes, aviso);
    // a fábrica tem de conseguir dobrar: bobina, largura da tira e limites da dobradeira
    // (regras em Catálogo → Regras da fábrica); perfil do catálogo passa sempre
    let validacao = null, esperaVal = null;
    const validar = (nome) => fetch('/api/fabrica/validar', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ perfil: nome }) }).then(r => r.json()).catch(() => null);
    const conferir = () => {
      const nome = nomeDoPerfil(campo.value, antigoNome);
      const p = lerPerfil(nome), a = lerPerfil(antigoNome);
      validacao = null;
      aviso.textContent = !campo.value.trim() ? '' : !p ? 'Não reconheci esse perfil (U ou Ue/C: 127X50X17X#14, U92X40X2.25).'
        : (a && p.familia !== a.familia) ? `O atual é ${a.familia}; a troca na malha é dentro da mesma família.`
        : `${nome}: ${p.H} × ${p.B}${p.D ? ' × ' + p.D : ''} × ${String(p.t).replace('.', ',')} mm · conferindo com as regras da fábrica…`;
      clearTimeout(esperaVal);
      if (!p || (a && p.familia !== a.familia)) return;
      esperaVal = setTimeout(async () => {
        const v = await validar(nome);
        if (!v || nomeDoPerfil(campo.value, antigoNome) !== nome) return;
        validacao = v;
        const med = `${nome}: ${p.H} × ${p.B}${p.D ? ' × ' + p.D : ''} × ${String(p.t).replace('.', ',')} mm`;
        aviso.textContent = !v.ok ? `A fábrica não faz este perfil: ${v.motivos.join(' ')}`
          : v.tipo === 'catalogo' ? `${med} · do catálogo`
          : `${med} · perfil da fábrica (fora do catálogo), tira de ${numero(v.desenvolvido, 0)} mm` + (v.conferidas ? '' : ' · regras da fábrica ainda não conferidas');
        aviso.style.color = v.ok ? '' : 'var(--erro, #b42318)';
      }, 250);
    };
    campo.addEventListener('input', conferir);
    setTimeout(() => campo.focus(), 50);
    if (await this.dialogo({ titulo: 'Trocar perfil', corpo, ok: 'Trocar' }) !== 'ok') return;
    const novoNome = nomeDoPerfil(campo.value, antigoNome);
    const novo = lerPerfil(novoNome), antigo = lerPerfil(antigoNome);
    if (!novo || !antigo) { this.aviso('Perfil não reconhecido: use U ou Ue/C, como 127X50X17X#14.', 'atencao'); return; }
    const val = validacao || await validar(novoNome);
    if (val && !val.ok) { this.aviso(`${novoNome} não foi trocado — a fábrica não faz este perfil: ${val.motivos.join(' ')} (as regras ficam em Catálogo → Regras da fábrica)`, 'atencao', 15000); return; }
    const alvos = alcance.value === 'posicao' ? daPosicao : alcance.value === 'perfil' ? doPerfil : ents;
    const mud = {}, falhas = [];
    for (const e of alvos) {
      const r = trocarSecao(e, antigo, novo);
      if (r.erro) { falhas.push(`${(e.atributos.marcas || {}).posicao || e.nome}: ${r.erro}`); continue; }
      const atributos = clonar(e.atributos);
      // o perfil original (o do projeto) fica guardado, e cada troca com a data
      const original = atributos.marcas.perfil_original || atributos.marcas.perfil_anterior || antigoNome;
      atributos.marcas = { ...atributos.marcas, perfil: novoNome, perfil_anterior: atributos.marcas.perfil_anterior || antigoNome,
                           perfil_original: original };
      atributos.trocas_de_perfil = [...(atributos.trocas_de_perfil || []),
        { de: (e.atributos.marcas || {}).perfil || antigoNome, para: novoNome, data: new Date().toISOString().slice(0, 19) }];
      mud[e.id] = { vertices: r.vertices, atributos, ...(e.nome === antigoNome ? { nome: novoNome } : {}) };
    }
    const n = Object.keys(mud).length;
    if (n) this.executar(new ComandoAlterar(mud, `Trocar perfil ${antigoNome} → ${novoNome}`));
    // perfil fora do catálogo: entra na lista dos perfis da fábrica (data, projeto, quem usou)
    if (n && val && val.tipo === 'dobrado') {
      fetch('/api/fabrica/perfis', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ perfil: novoNome, projeto: this.projeto || '' }) }).catch(() => {});
    }
    this.aviso(`${n} peça(s) passaram de ${antigoNome} para ${novoNome}` +
               (falhas.length ? `; ${falhas.length} não: ${falhas.slice(0, 3).join(' · ')}` : '') +
               '. Gere o detalhamento de novo para os desenhos saírem com o perfil novo. Ctrl+Z desfaz.',
               falhas.length ? 'atencao' : 'info', 12000);
  }
}
