// Métodos do editor 3D: Trocar perfis por grupo — a ferramenta dos estudos (usuário, 16/10/2026: "se o cliente pede para
// ver uma opção diferente o ajuste é rápido"). Uma linha por grupo e perfil do modelo (terças, banzo superior e inferior,
// montantes, diagonais e os outros papéis); em cada uma, o perfil novo e, na alma, a forma (U ou cantoneira dupla).
//
// A conta é do servidor (nucleo3d/troca_por_grupo.py, rota /api/modelo/trocar-grupos): a terça fica sentada no mesmo
// apoio (também a cartola, de chapéu para cima), o par de cantoneiras sai encostado nas abas do banzo com as presilhas
// da norma, e as treliças tocadas passam pelas regras de montagem. Aqui ficam o diálogo, a prévia (peças e quilos) e o
// comando — uma entrada de desfazer, com o Numerar só nas peças tocadas.

import { el, numero } from '../editor.js';
import { clonar } from '../nucleo/documento.js';

const FAMILIAS_SUGERIDAS = ['Ue', 'U', 'Cr', 'L'];       // as que um estudo troca (terça, banzo, alma, cartola)

export class MetodosTrocaGrupos {
  /** os nomes do catálogo das famílias dos estudos (uma vez por sessão), para a lista do campo */
  async _perfisDosEstudos() {
    if (this._perfisEstudo) return this._perfisEstudo;
    const nomes = new Set((this.catalogo.perfis || []).map(p => p.nome));
    await Promise.all(FAMILIAS_SUGERIDAS.map(f => fetch(`/api/catalogo/pecas?familia=${encodeURIComponent(f)}`)
      .then(r => r.json()).then(d => { for (const it of (d.itens || [])) nomes.add(it.nome); }).catch(() => {})));
    this._perfisEstudo = [...nomes].sort((a, b) => a.localeCompare(b, 'pt-BR', { numeric: true }));
    return this._perfisEstudo;
  }

  async _pedirTrocaGrupos(trocas) {
    const resp = await fetch('/api/modelo/trocar-grupos', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ documento: this.documento.paraJSON(), projeto: this.projeto || null, ...(trocas ? { trocas } : {}) }) });
    const r = await resp.json();
    if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    return r;
  }

  async dialogoTrocarGrupos() {
    let g;
    try { this.dica('Lendo os grupos do modelo…'); g = await this._pedirTrocaGrupos(null); }
    catch (e) { this.aviso(`Trocar perfis por grupo: ${e.message}`, 'erro', 0); return; }
    const grupos = g.grupos || [];
    if (!grupos.length) { this.aviso('O modelo não tem barras para trocar.', 'atencao'); return; }
    const lista = el('datalist', { id: 'perfis-estudo' });
    this._perfisDosEstudos().then(ns => { for (const n of ns) lista.append(el('option', { value: n })); });
    const linhas = [];
    const tabela = el('table', { class: 'troca-grupos', style: 'border-collapse:collapse;width:100%;font-size:12px' },
      el('tr', {}, ...['Grupo', 'Perfil atual', 'Peças', 'kg', 'Perfil novo', 'Forma'].map(t => el('th', { texto: t, style: 'text-align:left;padding:2px 6px;border-bottom:1px solid rgba(127,127,127,.4)' }))));
    for (const gr of grupos) {
      const alma = gr.grupo === 'montantes' || gr.grupo === 'diagonais';
      gr.perfis.forEach((p, i) => {
        const novo = el('input', { type: 'text', list: 'perfis-estudo', spellcheck: 'false', placeholder: 'o mesmo', style: 'width:100%;min-width:150px' });
        let forma = null;
        if (alma) {
          forma = el('select', {},
            el('option', { value: '', texto: 'a mesma' }),
            el('option', { value: 'simples', texto: 'peça só (U)' }),
            el('option', { value: 'dupla', texto: 'cantoneira dupla' }));
        }
        linhas.push({ grupo: gr.grupo, de: p.perfil, tipo: p.tipo || '', novo, forma });
        const primeiraDoTipo = i === 0 || (gr.perfis[i - 1].tipo || '') !== (p.tipo || '');
        tabela.append(el('tr', { 'data-grupo': gr.grupo, 'data-perfil': p.perfil, 'data-tipo': p.tipo || '' },
          el('td', { style: 'padding:2px 6px;white-space:nowrap' },
            el('strong', { texto: i === 0 ? gr.rotulo : '' }),
            el('span', { texto: primeiraDoTipo && p.tipo ? `${i === 0 ? ' — ' : ''}${p.tipo_rotulo || p.tipo}` : '' })),
          el('td', { texto: p.perfil + (p.forma === 'dupla' ? ' (par)' : ''), style: 'padding:2px 6px;white-space:nowrap' }),
          el('td', { texto: String(p.pecas), style: 'padding:2px 6px;text-align:right' }),
          el('td', { texto: numero(p.kg, 0), style: 'padding:2px 6px;text-align:right' }),
          el('td', { style: 'padding:2px 6px' }, novo),
          el('td', { style: 'padding:2px 6px' }, forma || el('span', { texto: '' }))));
      });
    }
    const pedido = () => linhas.map(l => ({ grupo: l.grupo, de: l.de, tipo: l.tipo, para: l.novo.value.trim(), forma: l.forma ? l.forma.value : '' }))
      .filter(t => t.para || t.forma);
    const estado = el('p', { class: 'estado-previa', style: 'margin:8px 0 0;font-size:12px' });
    const botaoPrevia = el('button', { type: 'button', texto: 'Prévia (peças e peso)' });
    let ultima = null;
    const previa = async () => {
      const trocas = pedido();
      if (!trocas.length) { estado.textContent = 'Escolha o perfil novo (ou a forma) de algum grupo.'; return; }
      estado.textContent = 'Calculando…';
      try {
        const r = await this._pedirTrocaGrupos(trocas);
        ultima = { chave: JSON.stringify(trocas), r };
        estado.style.color = '';
        estado.textContent = this._textoDaTroca(r);
      } catch (e) { ultima = null; estado.style.color = 'var(--erro, #b42318)'; estado.textContent = e.message; }
    };
    botaoPrevia.addEventListener('click', previa);
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: 'Para estudos: troca de uma vez todas as peças de um grupo. A terça fica sentada no mesmo apoio (a cartola com o chapéu para cima); a alma pode virar cantoneira dupla (uma em cada aba do banzo, com as presilhas da norma) ou voltar a ser um U só; as pontas seguem o banzo e as treliças tocadas passam pelas regras de montagem. As peças trocadas são numeradas de novo. Ctrl+Z desfaz.' }),
      el('div', { style: 'max-height:52vh;overflow:auto;margin-top:6px' }, tabela), lista,
      el('div', { style: 'margin-top:8px' }, botaoPrevia), estado);
    if (await this.dialogo({ titulo: 'Trocar perfis por grupo', corpo, ok: 'Trocar' }) !== 'ok') return;
    const trocas = pedido();
    if (!trocas.length) return;
    let r = ultima && ultima.chave === JSON.stringify(trocas) ? ultima.r : null;
    if (!r) {
      try { this.dica('Trocando os perfis…'); r = await this._pedirTrocaGrupos(trocas); }
      catch (e) { this.aviso(`Trocar perfis por grupo: ${e.message}`, 'erro', 0); return; }
    }
    r = clonar(r);
    await this._numerarAsNovas(r);                       // as peças novas e as trocadas (marca a conferir) com marca
    const cmd = this._comandoDaLigacao(r, 'Trocar perfis por grupo');
    if (!cmd) { this.aviso('Trocar perfis por grupo: nada mudou.', 'info'); return; }
    this.executar(cmd);
    await this._completarPerfis();
    this.aviso(`Trocar perfis por grupo: ${this._textoDaTroca(r)} Gere o detalhamento de novo para os desenhos saírem com os perfis novos.`,
      (r.avisos || []).length ? 'atencao' : 'info', 15000);
  }

  _textoDaTroca(r) {
    const s = r.resumo || {};
    const dif = (s.kg_depois || 0) - (s.kg_antes || 0);
    const reg = s.regras || {};
    const partes = [`${s.pecas || 0} peça(s) trocada(s)`,
      `peso ${numero(s.kg_antes || 0, 0)} → ${numero(s.kg_depois || 0, 0)} kg (${dif >= 0 ? '+' : ''}${numero(dif, 0)} kg)`];
    if ((r.novas || []).length) partes.push(`${r.novas.length} peça(s) nova(s)`);
    if ((r.remover || []).length) partes.push(`${r.remover.length} saem`);
    if (reg.encaixadas || reg.giradas) partes.push(`regras das tesouras: ${reg.giradas || 0} girada(s), ${reg.encaixadas || 0} encaixada(s)${reg.recuadas ? `, ${reg.recuadas} recuada(s) da platibanda` : ''}`);
    return partes.join(' · ') + '.' + ((r.avisos || []).length ? ' ' + r.avisos.join('; ') + '.' : '');
  }
}
