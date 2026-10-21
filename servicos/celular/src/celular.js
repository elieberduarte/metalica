// O celular de qualquer lugar (Worker metalica-celular, 20/10/2026).
//
// O PC do escritório (o que tem licença com "envia obras") manda para o R2 as telas do celular e os pacotes das obras
// ligadas na chave "Celular" da tela de projetos; o celular liberado lê daqui, de qualquer rede, com o PC ligado ou não.
// Os endereços que o celular usa são os mesmos do servidor da rede local (sistema/celular/servidor.py): o app é o mesmo.
//
// Celular (cookie `mcel` com um segredo do aparelho; no banco fica só o SHA-256 dele):
//   GET  /celular/parear?c=<código>    o QR mostrado num PC com licença (uso único, 5 min) → o aparelho fica na chave do PC
//   POST /celular/api/entrar            {chave, nome}  a chave de licença digitada no celular
//   GET  /celular/…, /visor3d/…, /lib/… as telas (telas.json → arquivos/<sha1>)
//   GET  /celular/api/estado            quem é o aparelho e quando o PC enviou
//   GET  /celular/dados/projetos.json   a lista (indice.json)
//   GET  /celular/dados/<obra>/<nome>   o manifesto e os arquivos dele (só o que o manifesto lista)
//
// PC (Authorization: Licenca <licença assinada>; a chave da licença precisa estar ativa e o computador não liberado):
//   POST /pc/codigo                      um código de QR para a chave deste PC (qualquer licença)
//   GET  /pc/estado                      as obras na nuvem e os celulares desta chave
//   — e, só com "envia obras" na licença —
//   POST /pc/faltam {sha1s}              quais arquivos ainda não estão no R2
//   PUT  /pc/arquivo/<sha1>              um arquivo (o SHA-1 do corpo tem de bater)
//   PUT  /pc/obra/<obra>  DELETE …       o manifesto de uma obra / tira a obra da nuvem
//   PUT  /pc/indice, PUT /pc/telas       a lista do celular / o mapa das telas
//   POST /pc/limpar                      apaga os arquivos que nada mais usa
//
// — uma obra para outro usuário (21/10, qualquer licença ativa) —
//   GET  /pc/pessoas                     as licenças ativas (id opaco + nome) para escolher a quem enviar
//   POST /pc/envio/faltam {sha1s}        PUT /pc/envio/parte/<sha1>   as partes do pacote da obra
//   POST /pc/envios {para, nome, slug, partes, sha1}                  registra o envio para a pessoa
//   GET  /pc/recebidos                   os pendentes para esta licença (menos os que saíram deste PC)
//   GET  /pc/recebidos/<id>/parte/<sha1>   POST /pc/recebidos/<id>/recebido|recusar
//
// R2: arquivos/<sha1> (o conteúdo, uma vez só), obras/<obra>/manifesto.json, indice.json, telas.json, envios/partes/<sha1>.
import { agora, b64url, deB64url, normalizarChave, evento, json } from '../../licencas/src/comum.js';

const COOKIE = 'mcel';
const VALIDADE_CODIGO = 5 * 60 * 1000;
const PUBLICAS = new Set(['/celular/manifest.webmanifest', '/celular/lib/icone-180.png', '/celular/lib/icone-192.png',
                          '/celular/lib/icone-512.png']);
const TIPOS = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', mjs: 'text/javascript; charset=utf-8',
                css: 'text/css; charset=utf-8', json: 'application/json; charset=utf-8', png: 'image/png', pdf: 'application/pdf',
                mcel: 'application/octet-stream', svg: 'image/svg+xml', txt: 'text/plain; charset=utf-8',
                webmanifest: 'application/manifest+json; charset=utf-8' };
// X-Metalica-Nuvem: o app do celular (o mesmo da rede local) sabe que está na nuvem já no 401
const SEGURANCA = { 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY', 'X-Metalica-Nuvem': '1' };

const tipoDe = (nome) => TIPOS[String(nome).split('.').pop().toLowerCase()] || 'application/octet-stream';
const resposta = (corpo, status, tipo, extra = {}) => new Response(corpo, { status, headers: { ...SEGURANCA, 'Content-Type': tipo, ...extra } });
const vazio = (status, extra = {}) => resposta(null, status, 'text/plain', extra);
const txt = (v, n = 120) => String(v || '').trim().slice(0, n);
const SHA1 = /^[0-9a-f]{40}$/;

async function resumo(algoritmo, dados) {
  const b = typeof dados === 'string' ? new TextEncoder().encode(dados) : dados;
  return [...new Uint8Array(await crypto.subtle.digest(algoritmo, b))].map(x => x.toString(16).padStart(2, '0')).join('');
}

function cookie(req, nome) {
  for (const parte of (req.headers.get('Cookie') || '').split(';')) {
    const [k, ...v] = parte.trim().split('=');
    if (k === nome) return v.join('=');
  }
  return '';
}

/** o nome de uma obra no endereço: um nome de pasta, sem barras nem pontos no começo */
function obraValida(s) {
  let o;
  try { o = decodeURIComponent(s); } catch (e) { return null; }
  if (!o || o.length > 150 || /[\\/\x00-\x1f]/.test(o) || o.startsWith('.') || o.startsWith('_')) return null;
  return o;
}

function nomeDoAparelho(agente) {
  const a = String(agente || '');
  if (a.includes('iPad')) return 'iPad';
  if (a.includes('iPhone')) return 'iPhone';
  const m = /Android [\d.]+; ([^;)]+)/.exec(a);
  if (m) return m[1].trim() && m[1].trim() !== 'K' ? 'Android ' + m[1].trim() : 'Android';
  if (a.includes('Macintosh')) return 'Mac / iPad';
  if (a.includes('Windows')) return 'Computador Windows';
  return 'Aparelho';
}

// ------------------------------------------------------------------ o PC: a licença assinada dele

let _publica = null;
async function lerLicenca(env, token) {
  const [p, s] = String(token || '').split('.');
  if (!p || !s) return null;
  if (!_publica) {
    const raw = Uint8Array.from(atob(env.LICENCA_CHAVE_PUBLICA), c => c.charCodeAt(0));
    _publica = await crypto.subtle.importKey('raw', raw, { name: 'Ed25519' }, false, ['verify']);
  }
  const bytes = deB64url(p);
  if (!await crypto.subtle.verify({ name: 'Ed25519' }, _publica, deB64url(s), bytes)) return null;
  try { return JSON.parse(new TextDecoder().decode(bytes)); } catch (e) { return null; }
}

async function doPC(env, req, escrever) {
  const p = await lerLicenca(env, (req.headers.get('Authorization') || '').replace(/^Licenca\s+/i, ''));
  if (!p || !p.chave || !p.maquina) return { recusa: json({ erro: 'licença inválida' }, 403) };
  const lic = await env.DB.prepare('SELECT * FROM licencas WHERE chave = ?').bind(p.chave).first();
  if (!lic || !lic.ativa) return { recusa: json({ erro: 'a licença deste computador está bloqueada' }, 403) };
  const maq = await env.DB.prepare('SELECT * FROM maquinas WHERE chave = ? AND maquina = ?').bind(p.chave, p.maquina).first();
  if (!maq || maq.liberada) return { recusa: json({ erro: 'este computador foi desligado da licença' }, 403) };
  if (escrever && !lic.envia_obras) {
    return { recusa: json({ erro: 'esta licença não envia obras para a nuvem — ligue "Envia obras" nela, na tela de licenças' }, 403) };
  }
  return { lic, p, maq };
}

// ------------------------------------------------------------------ o celular: o aparelho do cookie

const lembrados = new Map();             // resumo do segredo → {ap, ate}: um minuto sem ir ao banco
async function aparelhoDo(env, req) {
  const v = cookie(req, COOKIE);
  if (!v || v.length > 100) return null;
  const r = await resumo('SHA-256', v);
  const c = lembrados.get(r);
  if (c && c.ate > Date.now()) return c.ap;
  const ap = await env.DB.prepare(`SELECT a.*, l.ativa AS licenca_ativa, l.pessoa FROM aparelhos a JOIN licencas l ON l.chave = a.chave
                                   WHERE a.segredo = ?`).bind(r).first();
  if (!ap || ap.liberado || !ap.licenca_ativa) { lembrados.delete(r); return null; }
  if (Date.now() - Date.parse(ap.ultima_vez) > 3600e3) {
    await env.DB.prepare('UPDATE aparelhos SET ultima_vez = ? WHERE id = ?').bind(agora(), ap.id).run();
  }
  lembrados.set(r, { ap, ate: Date.now() + 60e3 });
  return ap;
}

/** um aparelho novo na chave: {segredo} ou {erro, status} */
async function novoAparelho(env, req, chave, via, nome) {
  const lic = await env.DB.prepare('SELECT * FROM licencas WHERE chave = ?').bind(chave).first();
  if (!lic) return { erro: 'chave de licença não encontrada — confira o que foi digitado', status: 403 };
  if (!lic.ativa) return { erro: 'esta licença está bloqueada — fale com o responsável pelo Metálica', status: 403 };
  const max = lic.celulares_max || 3;
  const { n } = await env.DB.prepare('SELECT COUNT(*) AS n FROM aparelhos WHERE chave = ? AND liberado = 0').bind(chave).first();
  if (n >= max) {
    await evento(env, req, { chave, tipo: 'recusada', detalhe: `celular: limite de ${max} celulares (${nome})` });
    return { erro: `esta licença já tem ${n} celular(es), o limite dela — peça para liberar um na tela de licenças`, status: 409 };
  }
  const segredo = b64url(crypto.getRandomValues(new Uint8Array(24)));
  const t = agora();
  await env.DB.prepare('INSERT INTO aparelhos (chave, segredo, nome, via, criado, ultima_vez, liberado) VALUES (?, ?, ?, ?, ?, ?, 0)')
    .bind(chave, await resumo('SHA-256', segredo), txt(nome, 60), via, t, t).run();
  await evento(env, req, { chave, tipo: 'celular', detalhe: `entrou pelo ${via === 'qr' ? 'QR code' : 'chave digitada'} · ${txt(nome, 60)}` });
  return { segredo };
}

function cookieDo(req, segredo) {
  // Lax e não Strict: o link do QR chega pela câmera como navegação de fora (ver o servidor da rede local)
  const seguro = new URL(req.url).protocol === 'https:' ? '; Secure' : '';
  return `${COOKIE}=${segredo}; Path=/; HttpOnly; SameSite=Lax; Max-Age=34560000${seguro}`;
}

// tentativas erradas de chave por endereço (por instância do Worker; a chave tem 60 bits, isto só freia o abuso)
const erros = new Map();
function freado(req) {
  const ip = req.headers.get('CF-Connecting-IP') || '';
  const t = (erros.get(ip) || []).filter(x => x > Date.now() - 600e3);
  erros.set(ip, t);
  return t.length >= 10;
}
const errou = (req) => { const ip = req.headers.get('CF-Connecting-IP') || ''; erros.set(ip, [...(erros.get(ip) || []), Date.now()]); };

const ENTRADA = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metálica</title><meta name="theme-color" content="#0f1720"><link rel="manifest" href="/celular/manifest.webmanifest">
<style>:root{color-scheme:light dark;--fundo:#f4f6f8;--painel:#fff;--texto:#16202a;--fraco:#5b6773;--borda:#d5dbe1;--azul:#2563eb;--verm:#c0362c}
@media (prefers-color-scheme:dark){:root{--fundo:#0f1720;--painel:#17212c;--texto:#e6edf3;--fraco:#93a1ae;--borda:#2a3644;--azul:#5b8def;--verm:#f0776b}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--fundo);color:var(--texto);
min-height:100vh;display:grid;place-items:center;padding:16px}main{width:100%;max-width:380px;background:var(--painel);border:1px solid var(--borda);
border-radius:14px;padding:22px}h1{font-size:19px;margin:0 0 4px}p{color:var(--fraco);margin:6px 0 16px}label{display:block;font-size:13px;color:var(--fraco)}
input{width:100%;font:inherit;font-size:17px;letter-spacing:.06em;text-transform:uppercase;padding:11px 12px;margin:6px 0 12px;border-radius:9px;
border:1px solid var(--borda);background:var(--fundo);color:var(--texto)}button{width:100%;font:inherit;font-weight:600;padding:11px;border:0;
border-radius:9px;background:var(--azul);color:#fff}button:disabled{opacity:.6}#erro{color:var(--verm);font-size:14px;min-height:1.5em;margin:10px 0 0}
small{display:block;color:var(--fraco);margin-top:16px;font-size:13px}</style></head><body><main>
<h1>Metálica no celular</h1><p>Para ver as obras, digite a chave da sua licença do Metálica (a mesma do computador).</p>
<form id="f"><label for="chave">Chave da licença</label><input id="chave" autocomplete="off" autocapitalize="characters" spellcheck="false"
placeholder="MTL-XXXX-XXXX-XXXX" required><button id="b">Entrar</button></form><div id="erro" role="alert"></div>
<small>No escritório, também dá para entrar lendo o QR code no computador: <i>Projetos → Celular</i>. Este celular fica na sua licença e pode ser
desligado na tela de licenças.</small></main>
<script>document.getElementById('f').onsubmit=async function(ev){ev.preventDefault();var b=document.getElementById('b'),e=document.getElementById('erro');
b.disabled=true;e.textContent='';try{var r=await fetch('/celular/api/entrar',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',
body:JSON.stringify({chave:document.getElementById('chave').value})});var j=await r.json().catch(function(){return{}});if(!r.ok)throw new Error(j.erro||('erro '+r.status));
location.replace('/celular/');}catch(x){e.textContent=x.message;b.disabled=false;}};</script></body></html>`;

const PAGINA = (titulo, texto) => `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metálica</title><style>:root{color-scheme:light dark}body{font:15px/1.5 system-ui,sans-serif;max-width:420px;margin:15vh auto;padding:0 16px}
a{color:#2563eb}</style></head><body><h2>${titulo}</h2><p>${texto}</p><p><a href="/celular/">Entrar com a chave da licença</a></p></body></html>`;

// ------------------------------------------------------------------ R2

async function lerJson(env, chave) {
  const o = await env.OBRAS.get(chave);
  if (!o) return null;
  try { return await o.json(); } catch (e) { return null; }
}

async function servir(env, req, sha1, tipo, cabeca) {
  const etag = `"${sha1}"`;
  if (req.headers.get('If-None-Match') === etag) return vazio(304, { ETag: etag, 'Cache-Control': 'no-cache' });
  const o = await env.OBRAS.get('arquivos/' + sha1);
  if (!o) return vazio(404);
  if (cabeca) { o.body.cancel(); return resposta(null, 200, tipo, { ETag: etag, 'Cache-Control': 'no-cache' }); }
  return resposta(o.body, 200, tipo, { ETag: etag, 'Cache-Control': 'no-cache' });
}

async function tela(env, req, rota, cabeca) {
  const mapa = await lerJson(env, 'telas.json');
  const sha1 = mapa && mapa[rota];
  if (!sha1) return vazio(404);
  return servir(env, req, sha1, tipoDe(rota), cabeca);
}

async function dados(env, req, ap, rel, cabeca) {
  if (rel === 'projetos.json') {
    const ind = await lerJson(env, 'indice.json');
    return json({ formato: 1, projetos: (ind && ind.projetos) || [] });
  }
  const i = rel.indexOf('/');
  const obra = i > 0 ? obraValida(rel.slice(0, i)) : null;
  const arq = i > 0 ? rel.slice(i + 1) : '';
  if (!obra || !arq) return vazio(404);
  const m = await lerJson(env, `obras/${obra}/manifesto.json`);
  if (!m) return vazio(404);
  if (arq === 'manifesto.json') return json(m);
  const item = (m.arquivos || []).find(a => a.nome === arq);           // só o que o manifesto lista
  if (!item || !SHA1.test(item.sha1 || '')) return vazio(404);
  return servir(env, req, item.sha1, tipoDe(arq), cabeca);
}

async function celular(env, req, url, rota) {
  const cabeca = req.method === 'HEAD';
  if (rota === '/celular/parear') {
    const codigo = txt(url.searchParams.get('c'), 40);
    const c = codigo ? await env.DB.prepare('SELECT * FROM codigos_celular WHERE codigo = ?').bind(codigo).first() : null;
    if (c) await env.DB.prepare('DELETE FROM codigos_celular WHERE codigo = ?').bind(codigo).run();     // uso único
    if (!c || c.vence < Date.now()) {
      errou(req);
      return resposta(PAGINA('Código vencido ou já usado', 'No computador, abra <i>Acesso pelo celular</i> e gere um QR code novo. Cada código vale uma vez, por 5 minutos.'),
                      403, TIPOS.html, { 'Cache-Control': 'no-store' });
    }
    const r = await novoAparelho(env, req, c.chave, 'qr', nomeDoAparelho(req.headers.get('User-Agent')));
    if (r.erro) return resposta(PAGINA('Não foi possível entrar', r.erro), r.status, TIPOS.html, { 'Cache-Control': 'no-store' });
    return vazio(302, { Location: '/celular/', 'Set-Cookie': cookieDo(req, r.segredo), 'Cache-Control': 'no-store' });
  }
  if (rota === '/celular/api/entrar') {
    if (req.method !== 'POST') return vazio(405, { Allow: 'POST' });
    if (freado(req)) return json({ erro: 'tentativas demais — espere alguns minutos' }, 429, { 'Retry-After': '600' });
    const corpo = await req.json().catch(() => ({}));
    const chave = normalizarChave(corpo.chave);
    if (!/^MTL-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(chave)) { errou(req); return json({ erro: 'a chave tem o formato MTL-XXXX-XXXX-XXXX' }, 400); }
    const r = await novoAparelho(env, req, chave, 'chave', txt(corpo.nome, 60) || nomeDoAparelho(req.headers.get('User-Agent')));
    if (r.erro) {
      errou(req);
      if (r.status === 403) await evento(env, req, { chave, tipo: 'recusada', detalhe: 'celular: ' + r.erro.split(' — ')[0] });
      return json({ erro: r.erro }, r.status);
    }
    return json({ ok: true }, 200, { 'Set-Cookie': cookieDo(req, r.segredo) });
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') return vazio(405, { Allow: 'GET, HEAD' });
  if (PUBLICAS.has(rota)) return tela(env, req, rota, cabeca);
  if (rota === '/favicon.ico') return tela(env, req, '/celular/lib/icone-192.png', cabeca);
  const ap = await aparelhoDo(env, req);
  if (!ap) {
    if (['/', '/celular', '/celular/', '/celular/index.html'].includes(rota)) return resposta(ENTRADA, 401, TIPOS.html, { 'Cache-Control': 'no-store' });
    return vazio(401, { 'Cache-Control': 'no-store' });
  }
  if (rota === '/' || rota === '/celular') return vazio(302, { Location: '/celular/' });
  if (rota === '/celular/api/estado') {
    const ind = await lerJson(env, 'indice.json') || {};
    return json({ aparelho: ap.nome, pessoa: ap.pessoa, computador: ind.computador || '', programa: ind.programa || '',
                  enviado: ind.enviado || '', nuvem: true, agora: agora() });
  }
  if (rota.startsWith('/celular/dados/')) return dados(env, req, ap, rota.slice('/celular/dados/'.length), cabeca);
  return tela(env, req, rota === '/celular/' ? '/celular/index.html' : rota, cabeca);
}

// ------------------------------------------------------------------ uma obra para outro usuário (21/10/2026)
// O usuário: "ter uma opção de enviar o projeto para outro usuário por dentro do sistema sem precisar exportar o pacote
// da obra e enviar para ele abrir". O PC sobe o pacote da obra (projetos.exportar) em partes (até 40 MB cada: o corpo de
// um pedido ao Worker tem limite) e registra o envio para a pessoa; o PC dela vê em "recebidos", baixa as partes, importa
// e marca recebido (as partes saem do R2). Qualquer licença ativa envia e recebe (não depende de "envia obras"); a
// pessoa é escolhida por um identificador opaco (o SHA-256 da chave), nunca pela chave. Pendente há mais de 30 dias: sai.
// R2: envios/partes/<sha1> — fora de arquivos/, que a limpeza do celular apaga.

const PARTE_MAX = 45 * 1024 * 1024;
const DIAS_ENVIO = 30;

async function idDaPessoa(chave) { return (await resumo('SHA-256', 'metalica-envio:' + chave)).slice(0, 20); }

async function pessoas(env) {
  const r = (await env.DB.prepare('SELECT chave, pessoa FROM licencas WHERE ativa = 1 ORDER BY pessoa').all()).results || [];
  return Promise.all(r.map(async l => ({ id: await idDaPessoa(l.chave), chave: l.chave, pessoa: l.pessoa })));
}

/** apaga do R2 as partes que nenhum envio pendente usa */
async function soltarPartes(env, partes) {
  const pend = (await env.DB.prepare("SELECT partes FROM envios WHERE estado = 'pendente'").all()).results || [];
  const usadas = new Set(pend.flatMap(e => { try { return JSON.parse(e.partes).map(p => p.sha1); } catch (x) { return []; } }));
  const apagar = partes.map(p => p.sha1).filter(s => !usadas.has(s)).map(s => 'envios/partes/' + s);
  if (apagar.length) await env.OBRAS.delete(apagar);
}

async function vencidos(env) {
  const limite = new Date(Date.now() - DIAS_ENVIO * 864e5).toISOString();
  const r = (await env.DB.prepare("SELECT id, partes FROM envios WHERE estado = 'pendente' AND criado < ?").bind(limite).all()).results || [];
  for (const e of r) {
    await env.DB.prepare("UPDATE envios SET estado = 'vencido', fim = ? WHERE id = ?").bind(agora(), e.id).run();
    await soltarPartes(env, JSON.parse(e.partes || '[]'));
  }
}

async function envios(env, req, rota, quem, url) {
  const eu = quem.p.chave;
  if (rota === '/pc/pessoas' && req.method === 'GET') {
    return json({ pessoas: (await pessoas(env)).map(x => ({ id: x.id, pessoa: x.pessoa, eu: x.chave === eu })) });
  }
  if (rota === '/pc/envio/faltam' && req.method === 'POST') {
    const c = await req.json().catch(() => ({}));
    const pedidos = [...new Set((c.sha1s || []).filter(s => SHA1.test(s)))].slice(0, 500);
    const tem = await Promise.all(pedidos.map(s => env.OBRAS.head('envios/partes/' + s)));
    return json({ faltam: pedidos.filter((s, i) => !tem[i]) });
  }
  let m = /^\/pc\/envio\/parte\/([0-9a-f]{40})$/.exec(rota);
  if (m && req.method === 'PUT') {
    const corpo = await req.arrayBuffer();
    if (corpo.byteLength > PARTE_MAX + 1024) return json({ erro: 'parte grande demais' }, 413);
    if (await resumo('SHA-1', corpo) !== m[1]) return json({ erro: 'a parte chegou diferente do SHA-1 dela' }, 400);
    await env.OBRAS.put('envios/partes/' + m[1], corpo);
    return json({ ok: true, bytes: corpo.byteLength });
  }
  if (rota === '/pc/envios' && req.method === 'POST') {
    await vencidos(env);
    const c = await req.json().catch(() => ({}));
    const alvo = (await pessoas(env)).find(x => x.id === c.para);
    if (!alvo) return json({ erro: 'pessoa não encontrada (a licença dela pode ter sido bloqueada)' }, 404);
    const partes = Array.isArray(c.partes) ? c.partes.filter(p => SHA1.test(p.sha1 || '')).map(p => ({ sha1: p.sha1, bytes: +p.bytes || 0 })) : [];
    if (!partes.length || partes.length !== (c.partes || []).length) return json({ erro: 'partes inválidas' }, 400);
    const faltam = (await Promise.all(partes.map(p => env.OBRAS.head('envios/partes/' + p.sha1)))).filter(x => !x).length;
    if (faltam) return json({ erro: `faltam ${faltam} parte(s) do pacote na nuvem` }, 409);
    const r = await env.DB.prepare(`INSERT INTO envios (de_chave, de_pessoa, de_maquina, de_pc, para_chave, nome, slug, bytes, sha1, partes, criado, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente')`)
      .bind(eu, quem.lic.pessoa, quem.p.maquina, quem.maq.nome_pc || '', alvo.chave, txt(c.nome, 150), txt(c.slug, 150),
            partes.reduce((t, p) => t + p.bytes, 0), SHA1.test(c.sha1 || '') ? c.sha1 : '', JSON.stringify(partes), agora()).run();
    await evento(env, req, { chave: eu, maquina: quem.p.maquina, tipo: 'enviou obra', detalhe: `${txt(c.nome, 80)} → ${alvo.pessoa}` });
    return json({ id: r.meta.last_row_id, para: alvo.pessoa, eu: alvo.chave === eu });
  }
  if (rota === '/pc/recebidos' && req.method === 'GET') {
    // os enviados para esta licença, menos os que saíram deste mesmo computador (para si mesmo: só os outros PCs veem)
    // ?incluir_deste=1: também os deste PC (o teste de ponta a ponta numa máquina só)
    const deste = url.searchParams.get('incluir_deste') === '1' ? '' : quem.p.maquina;
    const r = (await env.DB.prepare(`SELECT id, de_pessoa, de_pc, de_chave, nome, slug, bytes, sha1, partes, criado FROM envios
        WHERE para_chave = ? AND estado = 'pendente' AND NOT (de_chave = ? AND de_maquina = ?) ORDER BY id`)
      .bind(eu, eu, deste).all()).results || [];
    return json({ recebidos: r.map(e => ({ id: e.id, de: e.de_pessoa, de_pc: e.de_pc, de_mim: e.de_chave === eu, nome: e.nome,
                                            slug: e.slug, bytes: e.bytes, sha1: e.sha1, criado: e.criado, partes: JSON.parse(e.partes || '[]') })) });
  }
  m = /^\/pc\/recebidos\/(\d+)(?:\/(parte)\/([0-9a-f]{40})|\/(recebido|recusar))$/.exec(rota);
  if (m) {
    const e = await env.DB.prepare("SELECT * FROM envios WHERE id = ? AND para_chave = ? AND estado = 'pendente'").bind(+m[1], eu).first();
    if (!e) return json({ erro: 'envio não encontrado (já recebido, recusado ou vencido)' }, 404);
    const partes = JSON.parse(e.partes || '[]');
    if (m[2] && req.method === 'GET') {
      if (!partes.some(p => p.sha1 === m[3])) return json({ erro: 'parte de outro envio' }, 404);
      const o = await env.OBRAS.get('envios/partes/' + m[3]);
      if (!o) return json({ erro: 'a parte não está mais na nuvem' }, 410);
      return new Response(o.body, { headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': String(o.size), 'Cache-Control': 'no-store' } });
    }
    if (m[4] && req.method === 'POST') {
      await env.DB.prepare('UPDATE envios SET estado = ?, fim = ?, recebido_pc = ? WHERE id = ?')
        .bind(m[4] === 'recebido' ? 'recebido' : 'recusado', agora(), quem.maq.nome_pc || '', e.id).run();
      await soltarPartes(env, partes);
      await evento(env, req, { chave: eu, maquina: quem.p.maquina, tipo: m[4] === 'recebido' ? 'recebeu obra' : 'recusou obra',
                               detalhe: `${e.nome} de ${e.de_pessoa}` });
      return json({ ok: true });
    }
  }
  return null;
}

// ------------------------------------------------------------------ o PC envia

async function pc(env, req, url, rota) {
  // a obra para outro usuário: qualquer licença ativa (não depende de "envia obras")
  if (rota === '/pc/pessoas' || rota === '/pc/envios' || rota.startsWith('/pc/envio/') || rota.startsWith('/pc/recebidos')) {
    const quem = await doPC(env, req, false);
    if (quem.recusa) return quem.recusa;
    return (await envios(env, req, rota, quem, url)) || json({ erro: 'rota desconhecida' }, 404);
  }
  const escrever = !['/pc/codigo', '/pc/estado'].includes(rota);
  const quem = await doPC(env, req, escrever);
  if (quem.recusa) return quem.recusa;
  if (rota === '/pc/codigo' && req.method === 'POST') {
    await env.DB.prepare('DELETE FROM codigos_celular WHERE vence < ?').bind(Date.now()).run();
    const codigo = b64url(crypto.getRandomValues(new Uint8Array(9)));
    await env.DB.prepare('INSERT INTO codigos_celular (codigo, chave, vence) VALUES (?, ?, ?)').bind(codigo, quem.p.chave, Date.now() + VALIDADE_CODIGO).run();
    const u = `${url.origin}/celular/parear?c=${codigo}`;
    return json({ codigo, validade_s: VALIDADE_CODIGO / 1000, url: u, urls: [u] });
  }
  if (rota === '/pc/estado' && req.method === 'GET') {
    const l = await env.OBRAS.list({ prefix: 'obras/', delimiter: '/' });
    const obras = (l.delimitedPrefixes || []).map(p => p.slice('obras/'.length, -1));
    const aps = (await env.DB.prepare('SELECT id, nome, via, criado, ultima_vez FROM aparelhos WHERE chave = ? AND liberado = 0 ORDER BY ultima_vez DESC')
      .bind(quem.p.chave).all()).results || [];
    const ind = await lerJson(env, 'indice.json') || {};
    return json({ obras, aparelhos: aps, enviado: ind.enviado || '', computador: ind.computador || '',
                  envia_obras: !!quem.lic.envia_obras, pessoa: quem.lic.pessoa });
  }
  if (rota === '/pc/faltam' && req.method === 'POST') {
    const c = await req.json().catch(() => ({}));
    const pedidos = [...new Set((c.sha1s || []).filter(s => SHA1.test(s)))].slice(0, 1000);
    const tem = await Promise.all(pedidos.map(s => env.OBRAS.head('arquivos/' + s)));
    return json({ faltam: pedidos.filter((s, i) => !tem[i]) });
  }
  let m = /^\/pc\/arquivo\/([0-9a-f]{40})$/.exec(rota);
  if (m && req.method === 'PUT') {
    const corpo = await req.arrayBuffer();
    if (await resumo('SHA-1', corpo) !== m[1]) return json({ erro: 'o arquivo chegou diferente do SHA-1 dele' }, 400);
    await env.OBRAS.put('arquivos/' + m[1], corpo);
    return json({ ok: true, bytes: corpo.byteLength });
  }
  m = /^\/pc\/obra\/([^/]+)$/.exec(rota);
  if (m) {
    const obra = obraValida(m[1]);
    if (!obra) return json({ erro: 'nome de obra inválido' }, 400);
    if (req.method === 'DELETE') { await env.OBRAS.delete(`obras/${obra}/manifesto.json`); return json({ ok: true }); }
    if (req.method === 'PUT') {
      const man = await req.json().catch(() => null);
      if (!man || !Array.isArray(man.arquivos) || man.arquivos.some(a => !SHA1.test(a.sha1 || ''))) return json({ erro: 'manifesto inválido' }, 400);
      const faltam = (await Promise.all(man.arquivos.map(a => env.OBRAS.head('arquivos/' + a.sha1)))).filter(x => !x).length;
      if (faltam) return json({ erro: `faltam ${faltam} arquivo(s) desta obra na nuvem — envie antes do manifesto` }, 409);
      await env.OBRAS.put(`obras/${obra}/manifesto.json`, JSON.stringify(man));
      return json({ ok: true });
    }
  }
  if ((rota === '/pc/indice' || rota === '/pc/telas') && req.method === 'PUT') {
    const d = await req.json().catch(() => null);
    if (rota === '/pc/indice' && (!d || !Array.isArray(d.projetos))) return json({ erro: 'lista inválida' }, 400);
    if (rota === '/pc/telas' && (!d || typeof d !== 'object' || Object.values(d).some(s => !SHA1.test(s)))) return json({ erro: 'mapa de telas inválido' }, 400);
    if (rota === '/pc/indice') d.enviado = agora();
    await env.OBRAS.put(rota === '/pc/indice' ? 'indice.json' : 'telas.json', JSON.stringify(d));
    return json({ ok: true });
  }
  if (rota === '/pc/limpar' && req.method === 'POST') return json(await limpar(env));
  return json({ erro: 'rota desconhecida' }, 404);
}

/** apaga do R2 os arquivos que nenhum manifesto nem as telas usam (os de menos de 1 h ficam: podem ser de um envio em curso) */
async function limpar(env) {
  const usados = new Set(Object.values(await lerJson(env, 'telas.json') || {}));
  let cursor;
  do {
    const l = await env.OBRAS.list({ prefix: 'obras/', cursor });
    for (const o of l.objects) for (const a of ((await lerJson(env, o.key)) || {}).arquivos || []) usados.add(a.sha1);
    cursor = l.truncated ? l.cursor : undefined;
  } while (cursor);
  const apagar = [];
  do {
    const l = await env.OBRAS.list({ prefix: 'arquivos/', cursor });
    for (const o of l.objects) {
      if (!usados.has(o.key.slice('arquivos/'.length)) && Date.now() - o.uploaded.getTime() > 3600e3) apagar.push(o.key);
    }
    cursor = l.truncated ? l.cursor : undefined;
  } while (cursor);
  for (let i = 0; i < apagar.length; i += 1000) await env.OBRAS.delete(apagar.slice(i, i + 1000));
  return { apagados: apagar.length, usados: usados.size };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    let rota;
    try { rota = decodeURIComponent(url.pathname); } catch (e) { return vazio(404); }
    if (rota.includes('..') || rota.includes('\\')) return vazio(404);
    try {
      if (rota.startsWith('/pc/')) return await pc(env, req, url, rota);
      if (rota === '/' || rota === '/favicon.ico' || rota === '/celular' || rota.startsWith('/celular/') || rota.startsWith('/visor3d/') || rota.startsWith('/lib/')) {
        return await celular(env, req, url, rota);
      }
      return vazio(404);
    } catch (e) {
      return json({ erro: 'falha no serviço do celular: ' + e.message }, 500);
    }
  },
};
