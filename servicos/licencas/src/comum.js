// O que os dois Workers das licenças usam (11/10/2026): a licença assinada, a chave nova e o registro de eventos.
//
// A licença é `base64url(payload JSON) + "." + base64url(assinatura Ed25519 do payload)`. A chave privada fica só no
// Worker da API (segredo LICENCA_CHAVE_PRIVADA, PKCS8 em base64); o programa tem a pública (sistema/licenca.py) e confere
// a assinatura sem internet. O payload: {v, chave, maquina, pessoa, emitida, validade} — validade = emitida + 30 dias.

export const DIAS_OFFLINE = 30;
const ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';     // sem 0/O, 1/I: a chave é digitada

export const agora = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

export function b64url(bytes) {
  let s = '';
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function deB64url(txt) {
  const s = atob(String(txt).replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((String(txt).length + 3) % 4));
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

function deB64(txt) {
  const s = atob(String(txt).trim());
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

let _privada = null, _publica = null;
async function chaves(env) {
  if (!env.LICENCA_CHAVE_PRIVADA) throw new Error('o segredo LICENCA_CHAVE_PRIVADA não está configurado');
  if (!_privada) _privada = await crypto.subtle.importKey('pkcs8', deB64(env.LICENCA_CHAVE_PRIVADA), { name: 'Ed25519' }, false, ['sign']);
  if (!_publica && env.LICENCA_CHAVE_PUBLICA) {
    _publica = await crypto.subtle.importKey('raw', deB64(env.LICENCA_CHAVE_PUBLICA), { name: 'Ed25519' }, false, ['verify']);
  }
  return { privada: _privada, publica: _publica };
}

export async function emitirLicenca(env, { chave, maquina, pessoa }) {
  const emitida = new Date();
  const validade = new Date(emitida.getTime() + DIAS_OFFLINE * 86400000);
  const payload = { v: 1, chave, maquina, pessoa, emitida: emitida.toISOString(), validade: validade.toISOString() };
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const { privada } = await chaves(env);
  const sig = await crypto.subtle.sign({ name: 'Ed25519' }, privada, bytes);
  return { licenca: b64url(bytes) + '.' + b64url(sig), validade: payload.validade };
}

/** o payload da licença se a assinatura confere (a validade não importa aqui: o banco é quem manda) */
export async function lerLicenca(env, token) {
  const [p, s] = String(token || '').split('.');
  if (!p || !s) return null;
  const bytes = deB64url(p);
  const { publica } = await chaves(env);
  if (!publica) throw new Error('o segredo LICENCA_CHAVE_PUBLICA não está configurado');
  const ok = await crypto.subtle.verify({ name: 'Ed25519' }, publica, deB64url(s), bytes);
  if (!ok) return null;
  try { return JSON.parse(new TextDecoder().decode(bytes)); } catch (e) { return null; }
}

export function novaChave() {
  const r = crypto.getRandomValues(new Uint8Array(12));
  const c = [...r].map(b => ALFABETO[b % ALFABETO.length]).join('');
  return `MTL-${c.slice(0, 4)}-${c.slice(4, 8)}-${c.slice(8, 12)}`;
}

export const normalizarChave = (c) => String(c || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  .replace(/^MTL/, '').replace(/^(.{4})(.{4})(.{4})$/, 'MTL-$1-$2-$3');

export async function evento(env, req, { chave = '', maquina = '', tipo, detalhe = '' }) {
  const pais = (req && req.cf && req.cf.country) || '';
  await env.DB.prepare('INSERT INTO eventos (quando, chave, maquina, tipo, detalhe, pais) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(agora(), chave, maquina, tipo, String(detalhe).slice(0, 500), pais).run();
}

export const json = (dados, status = 200, extra = {}) => new Response(JSON.stringify(dados), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra },
});
