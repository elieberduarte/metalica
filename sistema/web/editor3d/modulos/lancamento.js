// Métodos do editor 3D: lançamento da estrutura sobre o arquitetônico.
//
// O arquitetônico do cliente e os eixos moram na Planta de lançamento do CAD
// (nucleo3d/lancamento.py). Aqui eles aparecem no chão do modelo, em cinza e em vermelho
// com o nome, e o diálogo "Lançar estrutura" monta o galpão nos eixos gravados: o motor
// do galpão dimensiona e o modelo lançado substitui o do projeto (o anterior vai para o
// histórico).

import * as THREE from 'three';
import { el, numero, metros } from '../editor.js';

const ESCALA = 0.001;                  // metros de cena por mm, como a Cena
const COR_REFERENCIA = { claro: 0x9aa3ae, escuro: 0x5b6573 };
const COR_EIXO = 0xc0392b;

/** Sprite com o nome do eixo (bolinha branca, texto vermelho), do tamanho de `raio_mm`. */
function rotuloDoEixo(nome, raio_mm) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff'; g.strokeStyle = '#c0392b'; g.lineWidth = 8;
  g.beginPath(); g.arc(64, 64, 56, 0, Math.PI * 2); g.fill(); g.stroke();
  g.fillStyle = '#c0392b'; g.font = `bold ${nome.length > 2 ? 44 : 60}px Arial, sans-serif`;
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(nome, 64, 68);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  s.scale.setScalar(2 * raio_mm);
  s.renderOrder = 10;
  return s;
}

export class MetodosLancamento {
  /**
   * Arquitetônico e eixos no chão do modelo (só tela: não entram no documento, na lista
   * nem no IFC). Chamado ao abrir o projeto e depois de lançar.
   */
  async _carregarReferencia() {
    if (!this.projeto) return;
    let r;
    try {
      const resp = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento/referencia`, { cache: 'no-store' });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { return; }
    this._descartarReferencia();
    const segs = r.segmentos || [];
    const eixos = r.eixos || [];
    if (!segs.length && !eixos.length) return;
    const grupo = new THREE.Group();
    grupo.name = 'referencia-lancamento';
    grupo.scale.setScalar(ESCALA);
    if (segs.length) {
      const pos = new Float32Array(segs.length * 6);
      segs.forEach((s, i) => { pos.set([s[0], s[1], -2, s[2], s[3], -2], i * 6); });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const escuro = !!(this.cena && this.cena.escuro);
      const linhas = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
        color: escuro ? COR_REFERENCIA.escuro : COR_REFERENCIA.claro, transparent: true, opacity: 0.9 }));
      linhas.name = 'arquitetonico';
      grupo.add(linhas);
    }
    if (eixos.length) {
      const pos = new Float32Array(eixos.length * 6);
      eixos.forEach((e, i) => { pos.set([e.a[0], e.a[1], e.a[2], e.b[0], e.b[1], e.b[2]], i * 6); });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const linhas = new THREE.LineSegments(geo, new THREE.LineDashedMaterial({ color: COR_EIXO, dashSize: 900, gapSize: 250 }));
      linhas.computeLineDistances();
      linhas.name = 'eixos';
      grupo.add(linhas);
      // bolinha com o nome antes da ponta de cada eixo (como a planta)
      const L = Math.max(...eixos.map(e => Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])));
      const raio = Math.min(Math.max(L * 0.012, 250), 700);
      for (const e of eixos) {
        const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], d = Math.hypot(dx, dy) || 1;
        const s = rotuloDoEixo(e.nome, raio);
        s.position.set(e.a[0] - dx / d * raio * 1.2, e.a[1] - dy / d * raio * 1.2, e.a[2]);
        grupo.add(s);
      }
    }
    grupo.visible = this._referenciaVisivel !== false;
    this.cena.cena.add(grupo);
    this._referencia = grupo;
    this._temReferencia = true;
    this.cena.pedirQuadro();
  }

  _descartarReferencia() {
    const g = this._referencia;
    if (!g) return;
    this.cena.cena.remove(g);
    g.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); }
    });
    this._referencia = null;
  }

  /** Ver → Arquitetônico e eixos: liga e desliga o que está no chão. */
  alternarReferencia() {
    this._referenciaVisivel = this._referenciaVisivel === false;
    if (this._referencia) { this._referencia.visible = this._referenciaVisivel; this.cena.pedirQuadro(); }
    else if (this._referenciaVisivel) this._carregarReferencia();
    this.dica(this._referenciaVisivel ? 'Arquitetônico e eixos à mostra.' : 'Arquitetônico e eixos escondidos.');
  }

  /**
   * Lançar estrutura: o galpão nos eixos gravados da planta de lançamento. Pergunta o que
   * um projetista decide (sistema, pé-direito, inclinação, terças, vento, cargas); o motor
   * do galpão dimensiona e o modelo lançado substitui o do projeto.
   */
  async dialogoLancar() {
    if (!this.projeto) { this.aviso('Lançar estrutura precisa de um projeto aberto.', 'atencao'); return; }
    let d;
    try {
      const resp = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento`, { cache: 'no-store' });
      d = await resp.json();
      if (!resp.ok || d.erro && !d.parametros) throw new Error(d.erro || resp.statusText);
    } catch (e) { this.aviso(`Não foi possível ler os eixos do projeto: ${e.message}`, 'erro', 0); return; }
    if (!d.geometria) {
      const corpo = el('div', {},
        el('p', { class: 'explica', texto: d.erro || 'O projeto ainda não tem eixos.' }),
        el('p', { class: 'explica', texto: 'No CAD: Lançamento → Arquitetônico do cliente (DXF/PDF), depois Malha de eixos… (ou desenhe as linhas na camada EIXO) e Gravar eixos no projeto.' }));
      if (await this.dialogo({ titulo: 'Lançar estrutura', corpo, ok: 'Abrir a planta de lançamento' }) === 'ok') {
        this._irPara(`/cad?projeto=${encodeURIComponent(this.projeto)}&desenho=${encodeURIComponent('planta-de-lançamento')}`);
      }
      return;
    }
    const g = d.geometria;
    const p = { ...(d.padrao || {}), ...(d.parametros || {}) };
    const entradas = {};
    const grade = el('div', { class: 'campos lancamento' });
    const titulo = (t) => grade.append(el('h4', { texto: t, style: 'grid-column:1/-1;margin:.4em 0 0' }));
    const num = (k, rot, dica = '') => {
      entradas[k] = el('input', { type: 'text', value: p[k] == null ? '' : String(p[k]).replace('.', ','), title: dica });
      grade.append(el('label', { texto: rot, title: dica }), entradas[k]);
    };
    const sel = (k, rot, opcoes, dica = '') => {
      const atual = p[k] == null ? '' : String(p[k]);
      entradas[k] = this._lista(opcoes, atual, () => atualizar());
      entradas[k].title = dica;
      grade.append(el('label', { texto: rot, title: dica }), entradas[k]);
    };
    titulo('Sistema');
    sel('sistema', 'Pórtico', [['treliçado', 'tesoura treliçada sobre pilares'], ['alma cheia', 'alma cheia (viga e pilar de perfil I)']]);
    sel('ligacao_tesoura', 'Tesoura no pilar', [['apoiada', 'apoiada no topo do pilar (base engastada)'], ['rígida', 'rígida: pilar até o banzo superior']],
      'Apoiada: a tesoura assenta no pilar e o pilar é engastado na base (é o arranjo que o Calcular estrutura do 3D representa igual). Rígida: o pilar sobe até o banzo superior e forma pórtico com a tesoura.');
    const baseSel = this._lista([['', 'pelo sistema'], ['rotulada', 'rotulada'], ['engastada', 'engastada']],
      p.base_rotulada === true ? 'rotulada' : p.base_rotulada === false ? 'engastada' : '', () => {});
    baseSel.title = 'Pelo sistema: engastada na tesoura apoiada, rotulada no resto.';
    grade.append(el('label', { texto: 'Base do pilar' }), baseSel);
    num('pe_direito', 'Pé-direito (m)', 'do piso ao topo do pilar');
    num('inclinacao', 'Inclinação (%)', 'do telhado; 10 % ≈ 5,7°');
    titulo('Cobertura');
    num('espacamento_tercas', 'Espaçamento das terças (m)', 'alvo; na tesoura as terças vão para os nós do banzo superior');
    num('linhas_correntes', 'Linhas de correntes por vão', '');
    sel('telha', 'Telha', ['trapezoidal 0,43 mm', 'trapezoidal 0,50 mm', 'trapezoidal 0,65 mm', 'ondulada 0,50 mm',
      'sanduíche (termoacústica)', 'fibrocimento 6 mm'].map(t => [t, t]));
    num('sobrecarga_cobertura', 'Sobrecarga (kN/m²)', 'NBR 8800, Anexo B: mínimo 0,25 kN/m²');
    num('carga_extra', 'Carga extra (kN/m²)', 'forro, instalações, iluminação');
    titulo('Vento (NBR 6123)');
    num('v0', 'V₀ (m/s)', 'velocidade básica do mapa de isopletas');
    sel('categoria_rugosidade', 'Terreno', [['I', 'I — mar, lago'], ['II', 'II — campo aberto'], ['III', 'III — subúrbio, fazendas'], ['IV', 'IV — cidade, industrial'], ['V', 'V — centro de cidade']]);
    sel('aberturas', 'Fechamento', [['duas faces opostas', 'fechado, duas faces permeáveis'], ['quatro faces permeáveis', 'quatro faces permeáveis'], ['estanque', 'estanque']]);
    titulo('Modelo');
    const dimensionar = el('input', { type: 'checkbox' }); dimensionar.checked = p.dimensionar !== false;
    const fechamento = el('input', { type: 'checkbox' }); fechamento.checked = !!p.fechamento;
    grade.append(el('label', { texto: 'Dimensionar' }), el('label', { class: 'marcar' }, dimensionar, ' escolher os perfis pelo cálculo do galpão'));
    grade.append(el('label', { texto: 'Telhas e paredes' }), el('label', { class: 'marcar' }, fechamento, ' mostrar como sólidos (só visual)'));
    const esp = g.espacamentos || [];
    const iguais = esp.every(v => Math.abs(v - esp[0]) < 1);
    const resumo = el('p', { class: 'explica', texto:
      `Eixos gravados: vão ${metros(g.vao)} m (${g.letras[0]}–${g.letras[g.letras.length - 1]}), ${esp.length} vão(s) ` +
      (iguais ? `de ${metros(esp[0])} m` : `(${esp.map(v => metros(v)).join(' · ')} m)`) +
      ` entre os pórticos ${g.numeros[0]} a ${g.numeros[g.numeros.length - 1]}, ${metros(g.comprimento)} m de comprimento.` });
    const atualizar = () => {
      const tre = String(entradas.sistema.value).startsWith('tre');
      entradas.ligacao_tesoura.disabled = !tre;
    };
    const corpo = el('div', {}, resumo,
      ...(g.avisos || []).map(a => el('p', { class: 'explica atencao', texto: a })),
      el('p', { class: 'explica', texto: 'O motor do galpão dimensiona o pórtico com o maior espaçamento entre eixos (é o que governa), e o modelo 3D é montado nas posições reais dos eixos, com marcas de posição e conjunto: dá para detalhar, listar, calcular e exportar IFC como qualquer modelo. O modelo atual vai para o histórico.' }),
      grade);
    if (d.quando) corpo.append(el('p', { class: 'nota', texto: `Último lançamento: ${d.quando}.` }));
    atualizar();
    if (await this.dialogo({ titulo: 'Lançar estrutura nos eixos', corpo, ok: 'Lançar' }) !== 'ok') return;
    const par = {};
    const numeros = ['pe_direito', 'inclinacao', 'espacamento_tercas', 'linhas_correntes', 'sobrecarga_cobertura', 'carga_extra', 'v0'];
    for (const [k, e] of Object.entries(entradas)) {
      const v = String(e.value ?? '').trim();
      if (numeros.includes(k)) { const n = parseFloat(v.replace(',', '.')); if (v !== '' && isFinite(n)) par[k] = n; }
      else if (v !== '') par[k] = v;
    }
    par.base_rotulada = baseSel.value === '' ? null : baseSel.value === 'rotulada';
    par.dimensionar = dimensionar.checked;
    par.fechamento = fechamento.checked;
    await this._lancar(par);
  }

  async _lancar(par) {
    const parar = this._acompanharProgresso('Lançando: ');
    this.dica('Lançando a estrutura nos eixos…');
    let r;
    try {
      await this._gravarAntesDeGerar();
      const resp = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento/estrutura`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ parametros: par }) });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { parar(); this.dica(''); this.aviso(`Não foi possível lançar: ${e.message}`, 'erro', 0); return; }
    parar();
    const s = r.resumo || {};
    const pct = (v) => (typeof v === 'number' ? `${numero(v * 100, 0)} %` : '—');
    const lista = el('div', { class: 'lista-linhas' });
    for (const e of s.elementos || []) {
      lista.append(el('div', { class: 'linha', title: e.governa || '' },
        el('span', { class: 'nome', texto: `${e.nome} · ${e.perfil}` }),
        el('span', { class: 'aprov', dados: { ok: e.ok ? '1' : '' }, texto: pct(e.aproveitamento) })));
    }
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: `${s.sistema}: vão ${numero(s.vao_m, 2)} m, ${s.porticos} pórticos, pé-direito ${numero(s.pe_direito_m, 2)} m, ` +
        `${numero(s.barras)} barras e ${numero(s.chapas)} chapas em ${s.posicoes} posições e ${s.conjuntos} conjuntos, ${numero(s.peso_kg, 0)} kg de aço.` +
        (s.dimensionado ? (s.ok ? ' Todos os elementos passam no dimensionamento.' : ' Há elemento que não passa: veja a lista.') : ' Perfis padrão, sem dimensionar.') }),
      ...(s.elementos && s.elementos.length ? [lista] : []),
      ...(r.avisos || []).map(a => el('p', { class: 'explica atencao', texto: a })),
      el('p', { class: 'explica', texto: 'Próximos passos: Memorial do dimensionamento (PDF, com cargas, vento, combinações e cada elemento), Detalhamentos → Detalhar peças e conjuntos, e Calcular estrutura para conferir o modelo depois de editar.' }));
    const acao = await this.dialogo({ titulo: 'Estrutura lançada', corpo, ok: 'Abrir o modelo lançado' });
    if (acao === 'ok') location.href = `/editor?projeto=${encodeURIComponent(this.projeto)}`;
  }

  /** O memorial completo do dimensionamento do lançamento, em PDF (pasta memorial/lancamento). */
  async memorialDoLancamento() {
    if (!this.projeto) return;
    const parar = this._acompanharProgresso('Memorial: ');
    this.dica('Refazendo o dimensionamento e imprimindo o memorial…');
    try {
      const resp = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento/memorial`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: '{}' });
      const r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
      this.dica('');
      this.aviso(el('span', {}, `Memorial gravado em memorial/lancamento (${numero(r.pdf.tamanho_kb, 0)} kB). `,
        el('a', { href: r.pdf.url, target: '_blank', rel: 'noopener', texto: 'Abrir o PDF' })), 'info', 0);
    } catch (e) { this.dica(''); this.aviso(`Não foi possível gerar o memorial: ${e.message}`, 'erro', 0); }
    finally { parar(); }
  }
}
