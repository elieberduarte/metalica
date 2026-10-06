// Metálica no celular — as telas de consulta (rodada 1: protótipo navegável).
//
// Tudo sai do pacote do projeto: `dados/projetos.json` (a lista) e, por projeto,
// `dados/<slug>/manifesto.json` e os arquivos que ele lista. É o mesmo formato na rede do PC
// (o programa entrega na hora) e na cópia guardada para a obra. Só consulta: nenhuma tela
// grava nada.

const DADOS = 'dados/';
const q = new URLSearchParams(location.search);
const OFFLINE = q.get('offline') === '1';       // só para mostrar no protótipo como fica sem rede

const $ = (s, el = document) => el.querySelector(s);
const tela = $('#tela');
const folha = $('#folha');
const nf = (v, casas = 0) => (v == null || v === '' ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const kg = v => (v >= 10000 ? nf(v / 1000, 1) + ' t' : nf(v, v < 10 ? 2 : 1) + ' kg');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const dataHora = iso => { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); };

const cache = new Map();
async function json(caminho) {
  if (!cache.has(caminho)) cache.set(caminho, fetch(DADOS + caminho).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  return cache.get(caminho);
}

let visor = null;            // o 3D aberto (um por vez: o celular não guarda dois modelos)
let visorSlug = null;

function topo(titulo, sub, voltar) {
  $('#titulo').textContent = titulo;
  $('#subtitulo').textContent = sub || '';
  $('#voltar').hidden = !voltar;
  $('#voltar').onclick = voltar || null;
}

function conexao(manifestoGerado) {
  const c = $('#conexao');
  if (OFFLINE) {
    c.className = 'chip offline';
    c.textContent = 'Sem rede · cópia ' + (manifestoGerado ? dataHora(manifestoGerado).slice(0, 5) : '');
  } else {
    c.className = 'chip';
    c.textContent = 'No PC · Wi-Fi';
  }
  c.onclick = () => abrirFolha(`<div class="ficha"><div class="nome">${OFFLINE ? 'Sem rede' : 'Ligado ao computador'}</div>
    <p class="fraco">${OFFLINE
      ? 'Você está vendo a cópia guardada no aparelho. Quando voltar à rede do escritório, o celular baixa sozinho só os projetos que mudaram.'
      : 'O celular lê os projetos direto do programa no computador, pela rede Wi-Fi. Projeto importado ou corrigido no PC aparece aqui ao atualizar a tela.'}</p>
    <p class="mais-fraco">Só consulta: nada do que você faz aqui altera o projeto.</p></div>`);
}

function abas(slug, ativa) {
  const nav = $('#abas');
  nav.hidden = !slug;
  document.body.classList.toggle('sem-abas', !slug);
  for (const b of nav.querySelectorAll('button')) {
    b.classList.toggle('ativa', b.dataset.aba === ativa);
    b.onclick = () => { location.hash = `#/p/${encodeURIComponent(slug)}/${b.dataset.aba}`; };
  }
}

function abrirFolha(html) {
  $('#folha-corpo').innerHTML = html;
  folha.hidden = false;
}
function fecharFolha() { folha.hidden = true; }
folha.querySelector('.alca').onclick = fecharFolha;

// ------------------------------------------------------------------ roteiro

async function rota() {
  fecharFolha();
  const partes = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  document.body.classList.remove('tela-cheia');
  try {
    if (partes[0] === 'p' && partes[1]) await telaProjeto(partes[1], partes[2] || 'modelo');
    else await telaLista();
  } catch (e) {
    tela.innerHTML = `<div class="vazio"><b>Não foi possível abrir</b>${esc(e.message || e)}<br><br>
      Confira se o computador está ligado e na mesma rede Wi-Fi (a rede de visitantes costuma separar os aparelhos).</div>`;
  }
}
window.addEventListener('hashchange', rota);

// ------------------------------------------------------------------ lista de projetos

async function telaLista() {
  liberar3D();
  topo('Metálica', 'Projetos', null);
  abas(null);
  const idx = await json('projetos.json');
  conexao(idx.projetos[0] && idx.projetos[0].gerado);
  const projetos = idx.projetos.slice().sort((a, b) => String(b.alterado).localeCompare(String(a.alterado)));
  tela.innerHTML = `<div class="busca"><input type="search" placeholder="Buscar projeto" aria-label="Buscar projeto"></div>
    ${OFFLINE ? '<div class="aviso-topo">Sem rede: estes são os projetos guardados no aparelho.</div>' : ''}
    <div class="lista-cartoes"></div>`;
  const lista = $('.lista-cartoes');
  const desenhar = filtro => {
    const f = (filtro || '').toLowerCase();
    lista.innerHTML = projetos.filter(p => !f || (p.nome + ' ' + p.slug + ' ' + (p.cliente || '')).toLowerCase().includes(f)).map(p => {
      const n = p.numeros || {};
      return `<a class="cartao toque projeto" href="#/p/${encodeURIComponent(p.slug)}/modelo" style="display:block;color:inherit;text-decoration:none">
        <div class="linha"><div class="nome">${esc(p.nome || p.slug)}</div>${p.revisao ? `<span class="etiqueta">${esc(p.revisao)}</span>` : ''}</div>
        <div class="mais-fraco">alterado ${dataHora(p.alterado)}</div>
        <div class="numeros"><span><b>${n.peso_kg ? kg(n.peso_kg) : '—'}</b> aço</span><span><b>${nf(n.pecas)}</b> peças</span>
          <span><b>${nf(n.pranchas)}</b> pranchas</span></div>
        <div class="etiquetas">${OFFLINE ? '<span class="etiqueta ok">no aparelho</span>' : `<span class="etiqueta">${nf(p.bytes / 1048576, 1)} MB para a obra</span>`}</div>
      </a>`;
    }).join('') || '<div class="vazio"><b>Nenhum projeto</b>Nada com esse nome.</div>';
  };
  desenhar('');
  $('.busca input').oninput = e => desenhar(e.target.value);
}

// ------------------------------------------------------------------ projeto

async function telaProjeto(slug, aba) {
  const m = await json(`${slug}/manifesto.json`);
  const p = m.projeto;
  topo(p.nome || slug, [p.revisao, 'pacote de ' + dataHora(m.gerado)].filter(Boolean).join(' · '), () => { location.hash = '#/'; });
  conexao(m.gerado);
  abas(slug, aba);
  if (aba !== 'modelo') liberar3D();
  if (aba === 'modelo') return telaModelo(slug, m);
  if (aba === 'quantitativos') return telaQuantitativos(slug, m);
  if (aba === 'resumos') return telaResumos(slug, m);
  if (aba === 'pranchas') return telaPranchas(slug, m);
}

// ------------------------------------------------------------------ Modelo 3D

function liberar3D() {
  if (visor) { visor.descartar(); visor = null; visorSlug = null; }
}

async function telaModelo(slug, m) {
  document.body.classList.add('tela-cheia');
  if (!m.arquivos.some(a => a.nome === 'modelo3d.mcel')) {
    tela.innerHTML = '<div class="vazio" style="padding-top:120px"><b>Sem modelo 3D</b>Este projeto ainda não tem modelo.</div>';
    return;
  }
  tela.innerHTML = `<div class="palco"><canvas></canvas>
    <div class="carregando"><div>Abrindo o 3D…<div class="progresso"><i></i></div><div class="mais-fraco" id="baixado"></div></div></div>
    <div class="contagem" hidden></div>
    <div class="ferramentas" hidden>
      <button data-f="camadas" aria-label="Camadas"><svg viewBox="0 0 24 24"><path d="M12 3l9 5-9 5-9-5z M3 13l9 5 9-5 M3 17.5l9 5 9-5"/></svg></button>
      <button data-f="vistas" aria-label="Vistas"><svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button>
      <button data-f="buscar" aria-label="Buscar peça"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg></button>
      <button data-f="arestas" class="ligado" aria-label="Arestas"><svg viewBox="0 0 24 24"><path d="M4 7l8-4 8 4v10l-8 4-8-4z"/></svg></button>
      <button data-f="enquadrar" aria-label="Enquadrar"><svg viewBox="0 0 24 24"><path d="M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5"/></svg></button>
    </div></div>`;
  const { Visor3D } = await import('./visor3d.js');
  liberar3D();
  const canvas = $('.palco canvas');
  visor = new Visor3D(canvas, { maxPixelRatio: 2 });
  visorSlug = slug;
  const v = visor;
  await v.carregar(DADOS + `${slug}/modelo3d.mcel`, (f, txt) => {
    $('.progresso i').style.width = Math.round(f * 100) + '%';
    $('#baixado').textContent = txt;
  });
  if (v !== visor) return;          // trocou de tela no meio
  v.definirFichas(await json(`${slug}/pecas.json`));
  $('.carregando').remove();
  $('.ferramentas').hidden = false;
  const contagem = $('.contagem');
  contagem.hidden = false;
  contagem.textContent = `${nf(v.nPecas)} peças`;
  window.visor = v;

  // toque: um toque escolhe a peça, dois toques giram em volta dela
  let ini = null, ultimo = 0;
  canvas.addEventListener('pointerdown', e => { ini = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  canvas.addEventListener('pointerup', e => {
    if (!ini) return;
    const mexeu = Math.hypot(e.clientX - ini.x, e.clientY - ini.y) > 8 || performance.now() - ini.t > 400;
    ini = null;
    if (mexeu) return;
    const r = canvas.getBoundingClientRect();
    const id = v.escolher(e.clientX - r.left, e.clientY - r.top);
    const agora = performance.now();
    if (id >= 0 && agora - ultimo < 320) v.centrarEm(id);
    ultimo = agora;
    v.selecionar(id);
    if (id >= 0) mostrarFicha(v, id); else fecharFolha();
  });

  for (const b of tela.querySelectorAll('.ferramentas button')) {
    b.onclick = () => {
      const f = b.dataset.f;
      if (f === 'arestas') { b.classList.toggle('ligado'); v.ligarArestas(b.classList.contains('ligado')); }
      else if (f === 'enquadrar') v.enquadrar('iso');
      else if (f === 'camadas') folhaCamadas(v);
      else if (f === 'vistas') abrirFolha(`<div class="nome">Vistas</div><div class="etiquetas" style="margin-top:12px">
          ${['iso:Perspectiva', 'topo:Planta', 'frente:Frente', 'lado:Lateral'].map(x => { const [k, t] = x.split(':'); return `<button class="botao" data-v="${k}">${t}</button>`; }).join('')}</div>`),
        folha.querySelectorAll('[data-v]').forEach(x => x.onclick = () => { v.enquadrar(x.dataset.v); fecharFolha(); });
      else if (f === 'buscar') folhaBuscar(v);
    };
  }
}

function mostrarFicha(v, i) {
  const f = v.fichas[i];
  const cam = v.cabecalho.camadas[f.c] || {};
  const linhas = [
    ['Perfil', f.p], ['Camada', cam.nome], ['Material', f.m], ['Peso', f.kg ? kg(f.kg) : null],
    ['Posição', f.pos], ['Conjunto', f.cj], ['Marca', f.mc],
  ].filter(x => x[1]);
  abrirFolha(`<div class="ficha"><div class="nome">${esc(f.n || 'Peça sem nome')}</div>
    <dl>${linhas.map(([k, val]) => `<dt>${k}</dt><dd>${esc(val)}</dd>`).join('')}</dl>
    <div class="acoes"><button class="botao forte" id="centrar">Girar em volta</button><button class="botao" id="soltar">Fechar</button></div></div>`);
  $('#centrar').onclick = () => v.centrarEm(i);
  $('#soltar').onclick = () => { v.selecionar(-1); fecharFolha(); };
}

function folhaCamadas(v) {
  const cams = v.cabecalho.camadas;
  abrirFolha(`<div class="nome">Camadas</div><div style="margin-top:6px">${cams.map((c, i) => c.pecas ? `
    <div class="camada" data-i="${i}"><i style="background:${esc(c.cor)}"></i><span>${esc(c.nome)}<br><span class="mais-fraco">${nf(c.pecas)} peças</span></span>
      <div class="chave ${v.visivelCamada[i] !== false ? 'ligada' : ''}"></div></div>` : '').join('')}</div>`);
  folha.querySelectorAll('.camada').forEach(el => el.onclick = () => {
    const i = +el.dataset.i, ch = el.querySelector('.chave');
    ch.classList.toggle('ligada');
    v.mostrarCamada(i, ch.classList.contains('ligada'));
  });
}

function folhaBuscar(v) {
  abrirFolha(`<div class="nome">Buscar peça</div><div class="busca" style="position:static;margin:8px 0;padding:0;background:none">
    <input type="search" placeholder="marca, perfil ou nome" aria-label="Buscar peça"></div><div id="achadas"></div>`);
  const ent = folha.querySelector('input');
  ent.focus();
  ent.oninput = () => {
    const t = ent.value.trim().toLowerCase();
    const out = [];
    if (t.length >= 2) {
      for (let i = 0; i < v.fichas.length && out.length < 40; i++) {
        const f = v.fichas[i];
        if ((f.n + ' ' + f.p + ' ' + (f.pos || '') + ' ' + (f.mc || '')).toLowerCase().includes(t)) out.push(i);
      }
    }
    $('#achadas').innerHTML = out.map(i => `<div class="camada" data-i="${i}"><span>${esc(v.fichas[i].n)}<br><span class="mais-fraco">${esc(v.fichas[i].p)}</span></span></div>`).join('')
      || (t.length >= 2 ? '<div class="mais-fraco">Nenhuma peça.</div>' : '');
    $('#achadas').querySelectorAll('[data-i]').forEach(el => el.onclick = () => {
      const i = +el.dataset.i;
      v.selecionar(i); v.centrarEm(i); mostrarFicha(v, i);
    });
  };
}

// ------------------------------------------------------------------ Quantitativos

async function telaQuantitativos(slug, m) {
  if (!m.arquivos.some(a => a.nome === 'quantitativos.json')) {
    tela.innerHTML = '<div class="vazio"><b>Sem quantitativos</b>O detalhamento deste projeto ainda não foi feito no computador.</div>';
    return;
  }
  const qt = await json(`${slug}/quantitativos.json`);
  const t = qt.totais || {};
  const grupos = [
    ['posicoes', 'Posições', qt.posicoes], ['perfis', 'Perfis', qt.perfis], ['chapas', 'Chapas', qt.chapas],
    ['conjuntos', 'Conjuntos', qt.conjuntos], ['telhas', 'Telhas', qt.telhas], ['acessorios', 'Parafusos e acessórios', qt.acessorios],
  ].filter(g => g[2] && g[2].length);
  let atual = grupos[0][0], filtro = '', limite = 120;
  tela.innerHTML = `<div class="grade-num">
      <div class="cartao"><b>${kg(t.peso || 0)}</b><span>peso total</span></div>
      <div class="cartao"><b>${nf(t.pecas)}</b><span>peças</span></div>
      <div class="cartao"><b>${nf(t.posicoes)}</b><span>posições</span></div>
      <div class="cartao"><b>${nf(t.conjuntos)}</b><span>conjuntos</span></div></div>
    <div class="segmentos">${grupos.map(g => `<button data-g="${g[0]}">${g[1]} <span class="mais-fraco">${g[2].length}</span></button>`).join('')}</div>
    <div class="busca"><input type="search" placeholder="Buscar por marca, nome ou perfil" aria-label="Buscar"></div>
    <div class="lista-cartoes" id="itens"></div><div id="mais"></div>
    <p class="mais-fraco" style="text-align:center">Lista de materiais de ${esc(qt.gerado || '—')}</p>`;
  const desenhar = () => {
    tela.querySelectorAll('.segmentos button').forEach(b => b.classList.toggle('ativa', b.dataset.g === atual));
    const lista = grupos.find(g => g[0] === atual)[2];
    const f = filtro.toLowerCase();
    const filtrada = lista.filter(x => !f || JSON.stringify(x).toLowerCase().includes(f));
    $('#itens').innerHTML = filtrada.slice(0, limite).map(x => cartaoQuant(atual, x)).join('') ||
      '<div class="vazio"><b>Nada encontrado</b></div>';
    $('#mais').innerHTML = filtrada.length > limite ? `<button class="botao" style="width:100%;margin-bottom:12px">Mostrar mais (${filtrada.length - limite})</button>` : '';
    const bm = $('#mais button');
    if (bm) bm.onclick = () => { limite += 200; desenhar(); };
  };
  tela.querySelectorAll('.segmentos button').forEach(b => b.onclick = () => { atual = b.dataset.g; limite = 120; desenhar(); });
  $('.busca input').oninput = e => { filtro = e.target.value; limite = 120; desenhar(); };
  desenhar();
}

function cartaoQuant(tipo, x) {
  if (tipo === 'posicoes') {
    const nome = x.nome && x.nome !== x.marca ? x.nome : '';
    const dim = [x.comprimento && nf(x.comprimento) + ' mm', x.largura && x.classe === 'Chapa' ? '× ' + nf(x.largura) : '', x.espessura && x.classe === 'Chapa' ? '# ' + nf(x.espessura, 1) : ''].filter(Boolean).join(' ');
    return `<div class="cartao"><div class="linha"><div><span class="marca">${esc(nome || x.marca)}</span> ${nome ? `<span class="mais-fraco">${esc(x.marca)}</span>` : ''}</div>
      <div class="num"><b>${nf(x.quantidade)}×</b></div></div>
      <div class="fraco">${esc(x.perfil)}${dim ? ' · ' + dim : ''}</div>
      <div class="linha mais-fraco" style="margin-top:4px"><span>${esc(x.material || '')}</span><span class="num">${kg(x.peso || 0)} un · <b>${kg(x.peso_total || 0)}</b></span></div>
      ${x.furos || x.parafusos ? `<div class="etiquetas">${x.furos ? `<span class="etiqueta">${esc(x.furos)}</span>` : ''}${x.parafusos ? `<span class="etiqueta">${esc(x.parafusos)}</span>` : ''}</div>` : ''}
      ${x.conjuntos && x.conjuntos.length ? `<div class="mais-fraco" style="margin-top:6px">em ${esc(x.conjuntos.slice(0, 8).join(', '))}${x.conjuntos.length > 8 ? '…' : ''}</div>` : ''}</div>`;
  }
  if (tipo === 'perfis') {
    const b = x.barras || {};
    const plano = (b.plano || []).slice(0, 30);
    return `<details class="cartao"><summary><div class="linha"><div class="nome" style="font-size:15px">${esc(x.perfil)}</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.comprimento_m, 1)} m${b.quantidade ? ` · ${nf(b.quantidade)} barras de ${nf((b.comprimento || 0) / 1000)} m` : ''}</div>
      ${b.aproveitamento != null ? `<div class="barra"><i style="width:${Math.min(100, b.aproveitamento)}%"></i></div><div class="mais-fraco">aproveitamento ${nf(b.aproveitamento, 1)}%${plano.length ? ' · toque para o plano de corte' : ''}</div>` : ''}</summary>
      ${plano.length ? `<div class="plano">${plano.map(pl => `<div><b>${nf(pl.barras)}×</b> ${esc((pl.cortes || []).map(c => `${c.qtd || c.quantidade || 1}× ${c.nome || ''} ${nf(c.comprimento)}`).join(' + '))} <span class="mais-fraco">sobra ${nf(pl.sobra)}</span></div>`).join('')}</div>` : ''}</details>`;
  }
  if (tipo === 'chapas') {
    return `<div class="cartao"><div class="linha"><div class="nome" style="font-size:15px">Chapa # ${nf(x.espessura, 2)} mm</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.area_m2, 2)} m² · ${esc(x.material || '')}</div></div>`;
  }
  if (tipo === 'conjuntos') {
    return `<details class="cartao"><summary><div class="linha"><div><span class="marca">${esc(x.nome || x.marca)}</span> <span class="mais-fraco">${esc(x.marca)}</span></div><div class="num"><b>${nf(x.instancias)}×</b></div></div>
      <div class="fraco">${esc(x.categoria || '')} · ${nf(x.pecas_unidade)} peças por unidade</div></summary>
      <div class="plano">${esc(x.composicao_texto || '')}</div></details>`;
  }
  if (tipo === 'telhas') {
    return `<div class="cartao"><div class="linha"><div class="nome" style="font-size:15px">${esc(x.perfil)}</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.comprimento_m, 1)} m · ${nf(x.area_m2, 1)} m²</div></div>`;
  }
  return `<div class="cartao"><div class="linha"><div>${esc(x.nome)}</div><div class="num"><b>${nf(x.quantidade)}</b></div></div></div>`;
}

// ------------------------------------------------------------------ Resumos

async function telaResumos(slug, m) {
  const temNum = m.arquivos.some(a => a.nome === 'resumo-numeros.json');
  const rn = temNum ? await json(`${slug}/resumo-numeros.json`) : null;
  const temQt = m.arquivos.some(a => a.nome === 'quantitativos.json');
  const qt = temQt ? await json(`${slug}/quantitativos.json`) : null;
  const n = (rn && rn.numeros) || {}, d = (rn && rn.dimensoes) || {};
  const cats = (qt && qt.totais && qt.totais.categorias) || [];
  let html = '';
  if (rn) {
    html += `<div class="grade-num">
      <div class="cartao"><b>${kg(n.total || 0)}</b><span>total da obra</span></div>
      <div class="cartao"><b>${kg(n.peso_aco || 0)}</b><span>aço</span></div>
      <div class="cartao"><b>${nf(n.kg_m2, 1)}</b><span>kg/m²</span></div>
      <div class="cartao"><b>${nf(d.area_m2, 0)} m²</b><span>área</span></div>
      <div class="cartao"><b>${nf(n.tesouras)}</b><span>tesouras</span></div>
      <div class="cartao"><b>${nf(n.m2_telhas, 0)} m²</b><span>telhas</span></div>
      <div class="cartao"><b>${nf(n.parafusos)}</b><span>parafusos</span></div>
      <div class="cartao"><b>${nf(n.inclinacao, 1)}°</b><span>inclinação</span></div></div>`;
    if (d.eixos || d.comprimento_total) html += `<div class="cartao"><div class="nome" style="font-size:15px">Dimensões</div>
      <div class="fraco">Eixos ${esc(d.eixos || '—')} · comprimento ${nf((d.comprimento_total || 0) / 1000, 2)} m · apoio a ${nf((d.nivel_apoio || 0) / 1000, 2)} m</div></div>`;
  } else if (qt) {
    html += `<div class="grade-num"><div class="cartao"><b>${kg(qt.totais.peso || 0)}</b><span>peso total</span></div>
      <div class="cartao"><b>${nf(qt.totais.pecas)}</b><span>peças</span></div></div>`;
  }
  if (cats.length) {
    html += `<div class="titulo-secao">Peso por grupo</div><div class="cartao">${cats.map(c => `<div style="margin:6px 0 10px">
      <div class="linha"><span>${esc(c.titulo || c.categoria)}</span><span class="num fraco">${kg(c.peso)} · ${nf(c.pct, 1)}%</span></div>
      <div class="barra"><i style="width:${Math.min(100, c.pct)}%"></i></div></div>`).join('')}</div>`;
  }
  html += '<div class="titulo-secao">Documentos</div>';
  html += (m.resumos || []).map(r => `<a class="cartao toque documento" href="${DADOS}${encodeURIComponent(slug)}/${encodeURIComponent(r.arquivo)}" target="_blank">
      <div class="icone-doc">PDF</div><div><div class="nome" style="font-size:15px">${esc(r.titulo)}</div><div class="mais-fraco">${esc(r.arquivo)}</div></div></a>`).join('')
    || '<div class="cartao fraco">Os resumos em PDF ainda não foram emitidos no computador.</div>';
  tela.innerHTML = html || '<div class="vazio"><b>Sem resumos</b>O detalhamento deste projeto ainda não foi feito.</div>';
}

// ------------------------------------------------------------------ Pranchas

async function telaPranchas(slug, m) {
  const fl = m.pranchas || [];
  if (!fl.length) {
    tela.innerHTML = '<div class="vazio"><b>Sem pranchas</b>As pranchas deste projeto ainda não foram montadas no CAD do computador.</div>';
    return;
  }
  const pdf = `${DADOS}${encodeURIComponent(slug)}/pranchas.pdf`;
  tela.innerHTML = `<div class="linha" style="margin-bottom:12px"><span class="fraco">${fl.length} folhas · PDF de ${dataHora(m.fontes && m.fontes.pranchas)}</span>
      <a class="botao" href="${pdf}" target="_blank" style="text-decoration:none">Abrir o PDF</a></div>
    <div class="folhas">${fl.map(f => `<a href="${pdf}#page=${f.pagina}" target="_blank">
      <img loading="lazy" src="${DADOS}${encodeURIComponent(slug)}/${f.miniatura}" alt="Prancha ${f.numero}">
      <div><b>${String(f.numero).padStart(2, '0')}</b>${esc(f.titulo)} <span class="mais-fraco">${esc(f.formato)}</span></div></a>`).join('')}</div>`;
}

rota();
