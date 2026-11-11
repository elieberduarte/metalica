// A janela Renderizar e exportar da tela das Cenas (11/11, amostra-5 aprovada com a tela: "a tela de tratamento, criação,
// exportação, renderização das cenas"): quais cenas (esta, várias, todas — em lote), o tamanho (tela, Full HD, 4K, A3 a
// 300 dpi), a qualidade (refinada: blocos com supersampling e a sombra maior; rápida: como a tela), o formato (JPG, PNG, PDF
// com uma página por cena) e o destino (a pasta cenas/ da obra; baixar — um ZIP quando forem várias). A prévia mostra a
// cena como vai sair, com a marca d'água; a barra embaixo diz a cena, o bloco e quanto falta, e Cancelar para no bloco.
//
// O render em si é o da tela (cena.js): a janela abre cada cena, pede a imagem e grava. O PDF e o ZIP são montados aqui,
// sem biblioteca (o JPEG entra no PDF como está; o ZIP só guarda — JPEG e PNG já vêm comprimidos).

const enc = new TextEncoder();

// ------------------------------------------------------------------ CRC-32, ZIP e PDF

const TABELA_CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();

export function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) c = TABELA_CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

/** Um ZIP só guardado (sem comprimir): [{nome, dados: Uint8Array}] → Blob. Os nomes em UTF-8 (bit 11). */
export function zipDe(arquivos) {
  const partes = [], central = [];
  let pos = 0;
  const agora = new Date();
  const hora = (agora.getHours() << 11) | (agora.getMinutes() << 5) | (agora.getSeconds() >> 1);
  const dia = ((agora.getFullYear() - 1980) << 9) | ((agora.getMonth() + 1) << 5) | agora.getDate();
  for (const a of arquivos) {
    const nome = enc.encode(a.nome), d = a.dados, crc = crc32(d);
    const loc = new DataView(new ArrayBuffer(30));
    loc.setUint32(0, 0x04034b50, true); loc.setUint16(4, 20, true); loc.setUint16(6, 0x0800, true); loc.setUint16(8, 0, true);
    loc.setUint16(10, hora, true); loc.setUint16(12, dia, true); loc.setUint32(14, crc, true);
    loc.setUint32(18, d.length, true); loc.setUint32(22, d.length, true); loc.setUint16(26, nome.length, true); loc.setUint16(28, 0, true);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true); cen.setUint16(4, 20, true); cen.setUint16(6, 20, true); cen.setUint16(8, 0x0800, true);
    cen.setUint16(10, 0, true); cen.setUint16(12, hora, true); cen.setUint16(14, dia, true); cen.setUint32(16, crc, true);
    cen.setUint32(20, d.length, true); cen.setUint32(24, d.length, true); cen.setUint16(28, nome.length, true);
    cen.setUint32(42, pos, true);
    partes.push(new Uint8Array(loc.buffer), nome, d);
    central.push(new Uint8Array(cen.buffer), nome);
    pos += 30 + nome.length + d.length;
  }
  const tamCentral = central.reduce((s, p) => s + p.length, 0);
  const fim = new DataView(new ArrayBuffer(22));
  fim.setUint32(0, 0x06054b50, true); fim.setUint16(8, arquivos.length, true); fim.setUint16(10, arquivos.length, true);
  fim.setUint32(12, tamCentral, true); fim.setUint32(16, pos, true);
  return new Blob([...partes, ...central, new Uint8Array(fim.buffer)], { type: 'application/zip' });
}

/** Um PDF com uma página por imagem JPEG: [{jpeg: Uint8Array, w, h}] → Blob. A página na proporção da imagem, o lado
 *  maior com 842 pt (o do A4), a imagem inteira nela. */
export function pdfDeJpegs(paginas, titulo = '') {
  const pedacos = [], offsets = [];
  let pos = 0;
  const pôr = (x) => { const b = typeof x === 'string' ? enc.encode(x) : x; pedacos.push(b); pos += b.length; };
  const n = paginas.length, idPagina = (i) => 3 + i * 3;     // 1 catálogo, 2 páginas, depois (página, conteúdo, imagem) por imagem
  const objeto = (id, corpo) => { offsets[id] = pos; pôr(`${id} 0 obj\n`); for (const c of [].concat(corpo)) pôr(c); pôr('\nendobj\n'); };
  pôr('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n');
  const texto = (s) => '(' + String(s).replace(/[\\()]/g, (c) => '\\' + c).replace(/[^\x20-\x7E]/g, '?') + ')';
  objeto(1, `<< /Type /Catalog /Pages 2 0 R >>`);
  objeto(2, `<< /Type /Pages /Count ${n} /Kids [${paginas.map((_, i) => `${idPagina(i)} 0 R`).join(' ')}] >>`);
  paginas.forEach((p, i) => {
    const k = 842 / Math.max(p.w, p.h), W = +(p.w * k).toFixed(2), H = +(p.h * k).toFixed(2);
    const id = idPagina(i), conteudo = `q ${W} 0 0 ${H} 0 0 cm /Im0 Do Q`;
    objeto(id, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /XObject << /Im0 ${id + 2} 0 R >> >> /Contents ${id + 1} 0 R >>`);
    objeto(id + 1, [`<< /Length ${conteudo.length} >>\nstream\n`, conteudo, '\nendstream']);
    objeto(id + 2, [`<< /Type /XObject /Subtype /Image /Width ${p.w} /Height ${p.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.jpeg.length} >>\nstream\n`, p.jpeg, '\nendstream']);
  });
  const idInfo = 3 + n * 3;
  objeto(idInfo, `<< /Title ${texto(titulo)} /Producer (Metalica) >>`);
  const xref = pos, total = idInfo + 1;
  let tabela = `xref\n0 ${total}\n0000000000 65535 f \n`;
  for (let id = 1; id < total; id++) tabela += String(offsets[id]).padStart(10, '0') + ' 00000 n \n';
  pôr(tabela);
  pôr(`trailer\n<< /Size ${total} /Root 1 0 R /Info ${idInfo} 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(pedacos, { type: 'application/pdf' });
}

// ------------------------------------------------------------------ a janela

const LADOS = [['tela', 'Tela', 'rápido, para conferir'], ['1920', 'Full HD', 'WhatsApp, e-mail'],
               ['3840', '4K', 'apresentação, proposta'], ['4961', 'Impressão A3 a 300 dpi', '']];
const CHAVE = 'metalica.exportarCenas';
const BYTES_POR_PX = { jpg: 0.3, png: 1.4, pdf: 0.3 };       // para o "~2,5 MB" da prévia (a média do Filipin)

function lerOpcoes() {
  const padrao = { quais: 'esta', marcadas: [], lado: '3840', qualidade: 'refinada', formato: 'jpg', gravar: true, baixar: false, abrirPasta: true };
  try { return { ...padrao, ...(JSON.parse(localStorage.getItem(CHAVE) || '{}')) }; } catch (e) { return padrao; }
}
function guardarOpcoes(o) { try { localStorage.setItem(CHAVE, JSON.stringify(o)); } catch (e) { /* sem o navegador guardar: tudo bem */ } }

const ESTILO = `
#exportar-fundo { position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; background: rgba(15, 22, 32, .45); }
#exportar-caixa { width: min(940px, calc(100vw - 32px)); max-height: calc(100vh - 32px); display: flex; flex-direction: column; background: var(--painel);
  color: var(--texto); border: 1px solid var(--borda); border-radius: 10px; box-shadow: 0 12px 40px rgba(0,0,0,.35); overflow: clip; }
#exportar-caixa header, #exportar-caixa footer { flex: none; }
#exportar-caixa header { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--borda); }
#exportar-caixa header b { flex: 1; font-size: 15px; }
#exportar-caixa header button { border: 0; background: none; font-size: 18px; padding: 0 6px; }
#exportar-caixa .corpo { display: grid; grid-template-columns: 1fr 1fr; overflow: auto; flex: 1 1 auto; min-height: 0; align-items: stretch; }
#exportar-caixa .col { padding: 10px 16px 14px; display: flex; flex-direction: column; gap: 4px; }
#exportar-caixa .col + .col { border-left: 1px solid var(--borda); background: var(--fundo); }
#exportar-caixa h3 { font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--texto3, #6b7787); margin: 10px 0 2px; }
#exportar-caixa label { display: flex; gap: 6px; align-items: baseline; cursor: pointer; line-height: 1.5; }
#exportar-caixa label small, #exportar-caixa .fraco { color: var(--texto2); font-size: 11.5px; }
#exportar-caixa label.off { opacity: .55; cursor: default; }
#exportar-varias[hidden] { display: none; }
#exportar-varias { display: flex; flex-direction: column; margin: 0 0 2px 22px; max-height: 120px; overflow: auto; }
#exportar-varias label { font-size: 12px; }
#exportar-previa { width: 100%; aspect-ratio: 16 / 9; border: 1px solid var(--borda); border-radius: 6px; background: var(--painel) center/contain no-repeat; }
#exportar-caixa footer { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-top: 1px solid var(--borda); }
#exportar-situacao { flex: 0 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12.5px; }
#exportar-barra { flex: 1; height: 8px; border-radius: 4px; background: var(--borda); overflow: hidden; min-width: 60px; }
#exportar-barra i { display: block; height: 100%; width: 0; background: var(--azul2, #1f5fbf); transition: width .2s; }
#exportar-pasta[hidden] { display: none; }
#exportar-falta { font-size: 12px; color: var(--texto2); min-width: 44px; text-align: right; }
@media (max-width: 700px) { #exportar-caixa .corpo { grid-template-columns: 1fr; } #exportar-caixa .col + .col { border-left: 0; border-top: 1px solid var(--borda); } }
`;

/**
 * ctx: {
 *   cenas(): [{id, nome, tipo, ...}]  — a lista da tela (a ordem dos cartões)
 *   atual(): a cena aberta ({id, nome, tipo, fundo, marca…}) ou null
 *   abrir(id): abre a cena na tela (Promise; false = é da outra situação da cobertura e esta tela não a abre sem recarregar)
 *   podeRender(c): '' se a cena dá imagem nesta tela, senão o porquê
 *   tamanho(lado): [w, h] da cena aberta para o lado ('tela' | número)
 *   imagem({lado, ss, aoBloco}): o canvas da cena aberta, com a marca (Promise)
 *   transparente(): a cena aberta tem fundo transparente
 *   marca(): o texto da marca d'água da cena aberta
 *   enviar(blob, nome): grava a imagem da cena aberta na pasta cenas/ → {nome}
 *   enviarPdf(blob, nome): grava o PDF na pasta cenas/ → {nome}
 *   abrirPasta(nome): abre a pasta cenas/ no Explorador com o arquivo selecionado
 *   terminou(): depois do lote (os cartões, a cena de antes)
 *   nomeObra(): o nome da obra (o do PDF e do ZIP)
 * }
 */
export function ligarExportar(ctx) {
  if (!document.getElementById('exportar-estilo')) {
    const s = document.createElement('style'); s.id = 'exportar-estilo'; s.textContent = ESTILO; document.head.append(s);
  }
  let fundo = null, rodando = null, tempoPrevia = 0;

  function fechar() {
    if (rodando) { rodando.cancelado = true; return; }
    clearTimeout(tempoPrevia);
    if (fundo) { fundo.remove(); fundo = null; }
  }

  function opcoesDaTela() {
    const v = (n) => (fundo.querySelector(`input[name=${n}]:checked`) || {}).value;
    const ch = (id) => fundo.querySelector('#' + id).checked;
    return { quais: v('quais'), marcadas: [...fundo.querySelectorAll('#exportar-varias input:checked')].map(i => i.value),
             lado: v('lado'), qualidade: v('qualidade'), formato: v('formato'), gravar: ch('exportar-gravar'),
             baixar: ch('exportar-baixar'), abrirPasta: ch('exportar-abrir') };
  }

  function escolhidas(o) {
    const todas = ctx.cenas(), atual = ctx.atual();
    if (o.quais === 'todas') return todas;
    if (o.quais === 'varias') return todas.filter(c => o.marcadas.includes(c.id));
    return atual ? todas.filter(c => c.id === atual.id) : [];
  }

  function nomeDoArquivo(c, fmt) {
    return `Cena - ${String(c.nome || c.id).replace(/[<>:"/\\|?*]+/g, '-').trim()} (render).${fmt}`;
  }

  function mostrarResumo() {
    if (!fundo) return;
    const o = opcoesDaTela(), lista = escolhidas(o), atual = ctx.atual();
    const [w, h] = atual ? ctx.tamanho(o.lado) : [0, 0];
    const fmt = o.formato === 'png' ? 'PNG' : o.formato === 'pdf' ? 'PDF' : 'JPG';
    const mb = w * h * BYTES_POR_PX[o.formato] / 1048576;
    fundo.querySelector('#exportar-info').innerHTML = atual
      ? `${esc(atual.nome)} · ${nf(w)} × ${nf(h)} · ${fmt} · ~${nf(mb, mb < 10 ? 1 : 0)} MB` +
        (lista.length > 1 ? `<br><span class="fraco">${lista.length} cenas — cada uma no tamanho e na proporção dela${o.formato === 'pdf' ? ', uma página por cena' : ''}</span>` : '')
      : 'Nenhuma cena aberta.';
    fundo.querySelector('#exportar-marca').textContent = ctx.marca();
    fundo.querySelector('#exportar-varias').hidden = o.quais !== 'varias';
    const transp = atual && ctx.transparente();
    fundo.querySelector('#exportar-aviso-fmt').textContent = transp && o.formato !== 'png'
      ? 'O fundo transparente só fica no PNG; no JPG e no PDF ele sai branco.' : '';
    const pronto = lista.length > 0 && (o.gravar || o.baixar);
    const bt = fundo.querySelector('#exportar-ir');
    bt.disabled = !pronto;
    bt.textContent = lista.length > 1 ? `Renderizar ${lista.length} cenas` : 'Renderizar';
    fundo.querySelector('#exportar-situacao').textContent = !lista.length ? 'Escolha ao menos uma cena.'
      : !(o.gravar || o.baixar) ? 'Escolha gravar na pasta ou baixar.' : '';
    fundo.querySelector('#exportar-abrir').disabled = !o.gravar;
    guardarOpcoes(o);
  }

  async function desenharPrevia() {
    if (!fundo || rodando || !ctx.atual()) return;
    try {
      const img = await ctx.imagem({ lado: 640, ss: 1, aoBloco: null });
      if (!fundo || rodando) return;
      const cv = document.createElement('canvas'); cv.width = img.width; cv.height = img.height;
      const g = cv.getContext('2d');
      const fmt = opcoesDaTela().formato;
      if (fmt !== 'png' || !ctx.transparente()) { g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); }
      g.drawImage(img, 0, 0);
      const el = fundo.querySelector('#exportar-previa');
      el.style.backgroundImage = `url(${cv.toDataURL('image/jpeg', 0.85)})`;
      el.style.aspectRatio = `${img.width} / ${img.height}`;
    } catch (e) { console.warn('prévia do render', e); }
  }

  function agendarPrevia() { clearTimeout(tempoPrevia); tempoPrevia = setTimeout(desenharPrevia, 150); }

  function andamento(txt, fracao, falta) {
    if (!fundo) return;
    fundo.querySelector('#exportar-situacao').textContent = txt;
    fundo.querySelector('#exportar-barra i').style.width = `${Math.round(Math.max(0, Math.min(1, fracao)) * 100)}%`;
    fundo.querySelector('#exportar-falta').textContent = falta;
  }

  async function blobDe(canvas, fmt, transparente) {
    let cv = canvas;
    if (fmt !== 'png' && transparente) {                    // o JPEG não tem transparência: o vazado sobre o branco
      cv = document.createElement('canvas'); cv.width = canvas.width; cv.height = canvas.height;
      const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(canvas, 0, 0);
    }
    return await new Promise((res, rej) => cv.toBlob(b => b ? res(b) : rej(new Error('a imagem é grande demais para o navegador')),
      fmt === 'png' ? 'image/png' : 'image/jpeg', 0.95));
  }

  function baixar(blob, nome) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = nome;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  }

  async function renderizarLote() {
    const o = opcoesDaTela(), lista = escolhidas(o);
    if (!lista.length || rodando) return;
    const antes = ctx.atual() && ctx.atual().id;
    rodando = { cancelado: false };
    const estado = rodando;
    for (const el of fundo.querySelectorAll('.corpo input, #exportar-ir')) el.disabled = true;
    fundo.querySelector('#exportar-pasta').hidden = true;
    fundo.querySelector('#exportar-cancelar').textContent = 'Cancelar';
    const t0 = performance.now(), feitos = [], pulados = [], paginas = [], gravados = [];
    const ss = o.qualidade === 'rapida' ? 1 : 2;
    let erro = null;
    try {
      for (let i = 0; i < lista.length; i++) {
        const c = lista[i];
        const cab = lista.length > 1 ? `Renderizando ${i + 1} de ${lista.length} — ${c.nome}` : `Renderizando ${c.nome}`;
        andamento(`${cab} · abrindo a cena…`, i / lista.length, '');
        if (!ctx.atual() || ctx.atual().id !== c.id) {
          if (await ctx.abrir(c.id) === false) { pulados.push(`${c.nome} (a outra situação da cobertura: abra-a na tela e renderize)`); continue; }
        }
        const porque = ctx.podeRender(ctx.atual());
        if (porque) { pulados.push(`${c.nome} (${porque})`); continue; }
        const transp = ctx.transparente(), [w, h] = ctx.tamanho(o.lado);
        const img = await ctx.imagem({ lado: o.lado, ss, refinada: o.qualidade !== 'rapida', aoBloco: async (k, n) => {
          if (estado.cancelado) throw new Error('cancelado');
          const fr = (i + k / n) / lista.length, gasto = (performance.now() - t0) / 1000;
          const falta = fr > 0.02 ? Math.max(0, gasto / fr - gasto) : NaN;
          andamento(`${cab} · ${nf(w)} × ${nf(h)} · bloco ${k} de ${n}`, fr, isFinite(falta) ? `~${nf(falta)} s` : '');
          await new Promise(res => setTimeout(res, 0));
        } });
        if (estado.cancelado) throw new Error('cancelado');
        andamento(`${cab} · gravando…`, (i + 1) / lista.length, '');
        const fmt = o.formato === 'pdf' ? 'jpg' : o.formato;
        const blob = await blobDe(img, fmt, transp);
        if (o.formato === 'pdf') paginas.push({ jpeg: new Uint8Array(await blob.arrayBuffer()), w: img.width, h: img.height, nome: c.nome });
        else {
          if (o.gravar) gravados.push((await ctx.enviar(blob, fmt === 'png' ? 'render.png' : 'render.jpg')).nome);
          if (o.baixar) feitos.push({ nome: nomeDoArquivo(c, fmt), dados: new Uint8Array(await blob.arrayBuffer()) });
        }
      }
      const obra = String(ctx.nomeObra() || 'obra').replace(/[<>:"/\\|?*]+/g, '-').trim();
      if (o.formato === 'pdf' && paginas.length) {
        const nome = paginas.length === 1 ? nomeDoArquivo({ nome: paginas[0].nome }, 'pdf') : `Cenas - ${obra} (render).pdf`;
        const pdf = pdfDeJpegs(paginas, `Cenas - ${ctx.nomeObra() || ''}`);
        if (o.gravar) gravados.push((await ctx.enviarPdf(pdf, nome)).nome);
        if (o.baixar) baixar(pdf, nome);
      } else if (o.baixar && feitos.length === 1) baixar(new Blob([feitos[0].dados]), feitos[0].nome);
      else if (o.baixar && feitos.length > 1) baixar(zipDe(feitos), `Cenas - ${obra} (render).zip`);
      if (o.gravar && o.abrirPasta && gravados.length) await ctx.abrirPasta(gravados[0]).catch(() => {});
    } catch (e) { erro = e; }
    rodando = null;
    const s = nf((performance.now() - t0) / 1000, 1);
    let fim;
    if (erro && erro.message === 'cancelado') fim = 'Cancelado' + (gravados.length ? ` — já gravadas: ${gravados.join(', ')}` : '.');
    else if (erro) fim = 'O render parou: ' + erro.message;
    else {
      const n = o.formato === 'pdf' ? paginas.length : Math.max(gravados.length, feitos.length);
      fim = `Pronto: ${n} ${n === 1 ? 'cena' : 'cenas'} em ${s} s` + (gravados.length ? ` — na pasta cenas da obra: ${gravados.join(', ')}` : '') + '.';
    }
    if (pulados.length) fim += ` Ficaram de fora: ${pulados.join('; ')}.`;
    if (antes && ctx.atual() && ctx.atual().id !== antes) await ctx.abrir(antes).catch(() => {});
    await ctx.terminou().catch(() => {});
    if (fundo) {
      for (const el of fundo.querySelectorAll('.corpo input, #exportar-ir')) el.disabled = false;
      fundo.querySelector('#exportar-cancelar').textContent = 'Fechar';
      mostrarResumo();
      andamento(fim, erro ? 0 : 1, '');
      fundo.querySelector('#exportar-situacao').title = fim;
      const bt = fundo.querySelector('#exportar-pasta');       // o acesso rápido ao que acabou de sair (11/11)
      bt.hidden = !gravados.length;
      bt.onclick = () => ctx.abrirPasta(gravados[0]).catch(e => andamento('A pasta não abriu: ' + e.message, 1, ''));
      agendarPrevia();
    }
    // o fim do lote (os testes esperam por ele): só depois da tela de volta e do texto final na janela
    window.ultimoLoteCenas = { gravados, pulados, erro: erro ? erro.message : null, paginas: paginas.length, baixados: feitos.map(f => f.nome) };
  }

  function abrirJanela() {
    if (fundo) return;
    const o = lerOpcoes(), todas = ctx.cenas(), atual = ctx.atual();
    const radio = (nome, v, txt, sub = '', marcado = false, off = false) =>
      `<label${off ? ' class="off"' : ''}><input type="radio" name="${nome}" value="${v}"${marcado ? ' checked' : ''}${off ? ' disabled' : ''}> <span>${txt}${sub ? ` <small>${sub}</small>` : ''}</span></label>`;
    const [w0, h0] = atual ? ctx.tamanho('tela') : [0, 0];
    fundo = document.createElement('div');
    fundo.id = 'exportar-fundo';
    fundo.innerHTML = `<div id="exportar-caixa" role="dialog" aria-label="Renderizar e exportar">
      <header><b>Renderizar e exportar</b><button type="button" id="exportar-x" title="Fechar (Esc)">×</button></header>
      <div class="corpo"><div class="col">
        <h3>Quais cenas</h3>
        ${radio('quais', 'esta', `Esta cena${atual ? ' — ' + esc(atual.nome) : ''}`, '', o.quais === 'esta' || !['varias', 'todas'].includes(o.quais), !atual)}
        ${radio('quais', 'varias', 'Várias:', '', o.quais === 'varias')}
        <div id="exportar-varias">${todas.map(c => `<label><input type="checkbox" value="${esc(c.id)}"${(o.marcadas.length ? o.marcadas.includes(c.id) : c.id === (atual && atual.id)) ? ' checked' : ''}> ${esc(c.nome)} <small>${c.tipo === '3d' ? '3D' : 'foto'}</small></label>`).join('')}</div>
        ${radio('quais', 'todas', `Todas as cenas da obra (${todas.length})`, '', o.quais === 'todas')}
        <h3>Tamanho</h3>
        ${LADOS.map(([v, t, sub]) => radio('lado', v, v === 'tela' ? t : `${t} — ${v} px no lado maior`, v === 'tela' && atual ? `${nf(w0)} × ${nf(h0)}, ${sub}` : sub, o.lado === v)).join('')}
        <h3>Qualidade</h3>
        ${radio('qualidade', 'refinada', 'Refinada', 'sombra fina e bordas suaves (em blocos, como o Renderizar)', o.qualidade !== 'rapida')}
        ${radio('qualidade', 'rapida', 'Rápida', 'como está na tela', o.qualidade === 'rapida')}
        <h3>Formato e destino</h3>
        <div class="linha" style="gap:14px">${radio('formato', 'jpg', 'JPG', '(menor)', !['png', 'pdf'].includes(o.formato))}${radio('formato', 'png', 'PNG', '(fundo transparente possível)', o.formato === 'png')}${radio('formato', 'pdf', 'PDF', '(uma página por cena)', o.formato === 'pdf')}</div>
        <span class="fraco" id="exportar-aviso-fmt"></span>
        <label><input type="checkbox" id="exportar-gravar"${o.gravar ? ' checked' : ''}> <span>Gravar na pasta da obra <small>(cenas/ — aparece na aba Arquivos)</small></span></label>
        <label><input type="checkbox" id="exportar-baixar"${o.baixar ? ' checked' : ''}> <span>Baixar também <small>(um ZIP quando forem várias)</small></span></label>
        <span class="fraco">Pôr na prancha: no CAD 2D, Desenhos › Pranchas › Inserir cena da obra… (a imagem viva acompanha o render).</span>
      </div><div class="col">
        <h3>Como vai sair</h3>
        <div id="exportar-previa"></div>
        <div id="exportar-info" class="fraco" style="font-size:12.5px;color:var(--texto)"></div>
        <h3>Marca d'água</h3>
        <span id="exportar-marca"></span>
        <span class="fraco">A de cada cena: muda no painel à direita da tela (Marca d'água).</span>
        <h3>Depois</h3>
        <label><input type="checkbox" id="exportar-abrir"${o.abrirPasta ? ' checked' : ''}> <span>Abrir a pasta quando terminar <small>(com o arquivo selecionado)</small></span></label>
      </div></div>
      <footer><span id="exportar-situacao"></span><span id="exportar-barra"><i></i></span><span id="exportar-falta"></span>
        <button type="button" id="exportar-pasta" hidden title="Abre a pasta cenas da obra com o arquivo selecionado">📁 Mostrar na pasta</button>
        <button type="button" id="exportar-cancelar">Fechar</button><button type="button" id="exportar-ir" class="forte">Renderizar</button></footer></div>`;
    document.body.append(fundo);
    fundo.querySelector('#exportar-x').onclick = fechar;
    fundo.querySelector('#exportar-cancelar').onclick = fechar;
    fundo.querySelector('#exportar-ir').onclick = () => renderizarLote().catch(e => andamento('O render parou: ' + e.message, 0, ''));
    fundo.addEventListener('change', (ev) => {
      if (ev.target.closest('#exportar-varias')) fundo.querySelector('input[name=quais][value=varias]').checked = true;
      mostrarResumo();
      if (ev.target.name === 'formato') agendarPrevia();
    });
    fundo.addEventListener('keydown', (ev) => { ev.stopPropagation(); if (ev.key === 'Escape') fechar(); });
    fundo.addEventListener('pointerdown', (ev) => { if (ev.target === fundo) fechar(); });
    mostrarResumo();
    agendarPrevia();
    fundo.querySelector('#exportar-ir').focus();
  }

  return { abrir: abrirJanela, fechar, rodando: () => !!rodando, aberta: () => !!fundo };
}

const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
