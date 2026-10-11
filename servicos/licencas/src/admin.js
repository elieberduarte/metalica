// A tela das licenças (Worker metalica-licencas-admin, 11/10/2026): quem tem licença, em quais computadores, a versão e
// o último contato de cada um; criar chave, bloquear, liberar a vaga de um computador.
//
// Fica atrás do Cloudflare Access (login pelo e-mail). Além do Access, o Worker confere a assinatura do token do Access
// (Cf-Access-Jwt-Assertion) com as chaves da equipe — sem ACCESS_EQUIPE e ACCESS_AUD configurados, não abre (fechado
// por padrão). Mesmo banco D1 do Worker da API.
import { agora, novaChave, normalizarChave, evento, json, deB64url } from './comum.js';

let _certs = null, _certsEm = 0;
async function certificados(env) {
  if (_certs && Date.now() - _certsEm < 3600000) return _certs;
  const r = await fetch(`https://${env.ACCESS_EQUIPE}.cloudflareaccess.com/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error('certificados do Access: ' + r.status);
  _certs = (await r.json()).keys || [];
  _certsEm = Date.now();
  return _certs;
}

/** o e-mail de quem entrou pelo Access, ou null */
async function quemEntrou(req, env) {
  const tok = req.headers.get('Cf-Access-Jwt-Assertion');
  if (!tok) return null;
  const [h, p, s] = tok.split('.');
  if (!h || !p || !s) return null;
  const cab = JSON.parse(new TextDecoder().decode(deB64url(h)));
  const dados = JSON.parse(new TextDecoder().decode(deB64url(p)));
  const jwk = (await certificados(env)).find(k => k.kid === cab.kid);
  if (!jwk) return null;
  const chave = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', chave, deB64url(s), new TextEncoder().encode(`${h}.${p}`));
  const aud = Array.isArray(dados.aud) ? dados.aud : [dados.aud];
  if (!ok || !aud.includes(env.ACCESS_AUD) || !(dados.exp * 1000 > Date.now())) return null;
  if (dados.iss && dados.iss !== `https://${env.ACCESS_EQUIPE}.cloudflareaccess.com`) return null;
  return dados.email || dados.sub || 'access';
}

async function painel(env) {
  const lics = (await env.DB.prepare('SELECT * FROM licencas ORDER BY ativa DESC, pessoa').all()).results || [];
  const maqs = (await env.DB.prepare('SELECT * FROM maquinas ORDER BY ultima_vez DESC').all()).results || [];
  const evs = (await env.DB.prepare('SELECT * FROM eventos ORDER BY id DESC LIMIT 150').all()).results || [];
  for (const l of lics) l.maquinas = maqs.filter(m => m.chave === l.chave);
  return { licencas: lics, eventos: evs, agora: agora() };
}

const txt = (v, n = 120) => String(v || '').trim().slice(0, n);

async function api(req, env, url, email) {
  const corpo = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  if (req.method === 'GET' && url.pathname === '/api/painel') return json(await painel(env));
  if (req.method === 'POST' && url.pathname === '/api/licencas') {
    const pessoa = txt(corpo.pessoa, 80);
    if (!pessoa) return json({ erro: 'informe o nome da pessoa' }, 400);
    const max = Math.max(1, Math.min(10, parseInt(corpo.maquinas_max, 10) || 2));
    let chave = novaChave();
    while (await env.DB.prepare('SELECT 1 FROM licencas WHERE chave = ?').bind(chave).first()) chave = novaChave();
    await env.DB.prepare('INSERT INTO licencas (chave, pessoa, email, obs, maquinas_max, ativa, criada) VALUES (?, ?, ?, ?, ?, 1, ?)')
      .bind(chave, pessoa, txt(corpo.email, 120), txt(corpo.obs, 300), max, agora()).run();
    await evento(env, req, { chave, tipo: 'criada', detalhe: `${pessoa} · por ${email}` });
    return json({ chave });
  }
  let m = /^\/api\/licencas\/([A-Z0-9-]+)\/(bloquear|desbloquear|editar)$/.exec(url.pathname);
  if (req.method === 'POST' && m) {
    const chave = normalizarChave(m[1]);
    const lic = await env.DB.prepare('SELECT * FROM licencas WHERE chave = ?').bind(chave).first();
    if (!lic) return json({ erro: 'licença não encontrada' }, 404);
    if (m[2] === 'editar') {
      const max = Math.max(1, Math.min(10, parseInt(corpo.maquinas_max, 10) || lic.maquinas_max));
      await env.DB.prepare('UPDATE licencas SET pessoa = ?, email = ?, obs = ?, maquinas_max = ? WHERE chave = ?')
        .bind(txt(corpo.pessoa, 80) || lic.pessoa, txt(corpo.email, 120), txt(corpo.obs, 300), max, chave).run();
      await evento(env, req, { chave, tipo: 'editada', detalhe: `por ${email}` });
    } else {
      const ativa = m[2] === 'desbloquear' ? 1 : 0;
      await env.DB.prepare('UPDATE licencas SET ativa = ?, bloqueada_em = ? WHERE chave = ?').bind(ativa, ativa ? null : agora(), chave).run();
      await evento(env, req, { chave, tipo: ativa ? 'desbloqueada' : 'bloqueada', detalhe: `por ${email}` });
    }
    return json({ ok: true });
  }
  m = /^\/api\/maquinas\/(\d+)\/liberar$/.exec(url.pathname);
  if (req.method === 'POST' && m) {
    const maq = await env.DB.prepare('SELECT * FROM maquinas WHERE id = ?').bind(parseInt(m[1], 10)).first();
    if (!maq) return json({ erro: 'computador não encontrado' }, 404);
    await env.DB.prepare('UPDATE maquinas SET liberada = 1 WHERE id = ?').bind(maq.id).run();
    await evento(env, req, { chave: maq.chave, maquina: maq.maquina, tipo: 'liberada', detalhe: `${maq.nome_pc} · por ${email}` });
    return json({ ok: true });
  }
  return json({ erro: 'rota desconhecida' }, 404);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!env.ACCESS_EQUIPE || !env.ACCESS_AUD) {
      return new Response('A tela das licenças está fechada: falta configurar o Cloudflare Access (ACCESS_EQUIPE e ACCESS_AUD).',
        { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
    }
    let email = null;
    try { email = await quemEntrou(req, env); } catch (e) { email = null; }
    if (!email) return new Response('Acesso negado.', { status: 403, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
    try {
      if (url.pathname.startsWith('/api/')) return await api(req, env, url, email);
      if (url.pathname === '/' || url.pathname === '/index.html') {
        return new Response(PAGINA.replace('{{EMAIL}}', email.replace(/[<>&"]/g, '')), {
          headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
      }
      return json({ erro: 'rota desconhecida' }, 404);
    } catch (e) {
      return json({ erro: 'falha: ' + e.message }, 500);
    }
  },
};

const PAGINA = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Licenças do Metálica</title>
<style>
:root { --fundo:#f5f6f8; --painel:#ffffff; --texto:#1c2430; --sub:#5d6877; --borda:#dde2e8; --azul:#1f5fbf; --verde:#1e8e4e;
  --laranja:#b26a00; --vermelho:#c0392b; --chip:#eef1f5; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --fundo:#0f141b; --painel:#171e27; --texto:#e4e9ef; --sub:#97a3b2; --borda:#2a3441;
  --azul:#6aa4ff; --verde:#4cc283; --laranja:#f0a742; --vermelho:#ff7b6b; --chip:#212a35; color-scheme: dark; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--fundo); color: var(--texto); font: 14px/1.45 'Segoe UI', system-ui, sans-serif; }
header { display: flex; align-items: baseline; gap: 12px; padding: 18px 16px 6px; max-width: 1100px; margin: 0 auto; flex-wrap: wrap; }
h1 { font-size: 20px; margin: 0; } .sub { color: var(--sub); font-size: 12.5px; }
main { max-width: 1100px; margin: 0 auto; padding: 8px 16px 40px; }
.cartoes { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0 16px; }
.cartao { background: var(--painel); border: 1px solid var(--borda); border-radius: 10px; padding: 10px 12px; }
.cartao b { display: block; font-size: 22px; } .cartao span { color: var(--sub); font-size: 12px; }
section { background: var(--painel); border: 1px solid var(--borda); border-radius: 10px; padding: 12px; margin-bottom: 14px; }
h2 { font-size: 15px; margin: 0 0 8px; }
.lic { border-top: 1px solid var(--borda); padding: 10px 0; } .lic:first-of-type { border-top: 0; }
.linha { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.nome { font-weight: 600; font-size: 15px; } .chave { font-family: Consolas, monospace; background: var(--chip); padding: 2px 6px; border-radius: 5px; }
.estado { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 10px; background: var(--chip); }
.ok { color: var(--verde); } .medio { color: var(--laranja); } .ruim { color: var(--vermelho); }
.maqs { margin: 6px 0 0 4px; width: 100%; border-collapse: collapse; font-size: 13px; }
.maqs td { padding: 4px 6px; border-top: 1px solid var(--borda); vertical-align: top; }
.maqs td.n { white-space: nowrap; color: var(--sub); }
button { font: inherit; border: 1px solid var(--borda); background: var(--painel); color: var(--texto); border-radius: 7px; padding: 4px 10px; cursor: pointer; }
button.prim { background: var(--azul); border-color: var(--azul); color: #fff; } button.perigo { color: var(--vermelho); }
form.nova { display: grid; grid-template-columns: 2fr 2fr 1fr 2fr auto; gap: 8px; align-items: end; }
@media (max-width: 760px) { form.nova { grid-template-columns: 1fr; } .maqs td.n { white-space: normal; } }
label { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--sub); }
input { font: inherit; padding: 6px 8px; border: 1px solid var(--borda); border-radius: 7px; background: var(--fundo); color: var(--texto); }
.eventos { max-height: 360px; overflow: auto; font-size: 12.5px; } .eventos div { padding: 3px 0; border-top: 1px solid var(--borda); }
.aviso { background: var(--chip); border-left: 3px solid var(--azul); padding: 8px 10px; border-radius: 6px; margin: 8px 0; }
</style></head><body>
<header><h1>Licenças do Metálica</h1><span class="sub">entrou como {{EMAIL}}</span></header>
<main>
  <div class="cartoes" id="cartoes"></div>
  <section><h2>Nova licença</h2>
    <form class="nova" id="nova">
      <label>Pessoa<input name="pessoa" required placeholder="nome"></label>
      <label>E-mail<input name="email" type="email" placeholder="opcional"></label>
      <label>Computadores<input name="maquinas_max" type="number" min="1" max="10" value="2"></label>
      <label>Observação<input name="obs" placeholder="setor, função…"></label>
      <button class="prim" type="submit">Criar chave</button>
    </form>
    <div id="nova-res"></div>
  </section>
  <section><h2>Licenças</h2><div id="lista">Carregando…</div></section>
  <section><h2>Últimos eventos</h2><div class="eventos" id="eventos"></div></section>
</main>
<script>
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const dataBR = (iso) => iso ? new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
const dias = (iso) => iso ? (Date.now() - new Date(iso).getTime()) / 86400000 : Infinity;
function contato(iso) {
  const d = dias(iso);
  if (d < 2) return '<span class="ok">em dia</span>';
  if (d < 30) return '<span class="medio">sem contato há ' + Math.floor(d) + ' dias</span>';
  return '<span class="ruim">sem contato há ' + Math.floor(d) + ' dias (licença vencida no computador)</span>';
}
async function chamar(rota, corpo) {
  const r = await fetch(rota, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}
async function carregar() {
  const d = await chamar('/api/painel');
  const ativas = d.licencas.filter(l => l.ativa), maqs = d.licencas.flatMap(l => l.maquinas.filter(m => !m.liberada));
  const versoes = {}; for (const m of maqs) versoes[m.versao] = (versoes[m.versao] || 0) + 1;
  $('#cartoes').innerHTML = [
    ['licenças ativas', ativas.length], ['bloqueadas', d.licencas.length - ativas.length], ['computadores', maqs.length],
    ['em dia (48 h)', maqs.filter(m => dias(m.ultima_vez) < 2).length],
    ['versões em uso', Object.entries(versoes).sort().map(([v, n]) => esc(v) + (n > 1 ? ' ×' + n : '')).join(' · ') || '—'],
  ].map(([t, v]) => '<div class="cartao"><b>' + v + '</b><span>' + t + '</span></div>').join('');
  $('#lista').innerHTML = d.licencas.length ? d.licencas.map(l => {
    const ativos = l.maquinas.filter(m => !m.liberada);
    const linhas = l.maquinas.map(m => '<tr><td>' + (m.liberada ? '<s>' : '') + '<b>' + esc(m.nome_pc || 'computador') + '</b> · ' + esc(m.usuario) + (m.liberada ? '</s> <span class="sub">(vaga liberada)</span>' : '') +
      '</td><td class="n">versão ' + esc(m.versao || '—') + '</td><td class="n">último contato ' + dataBR(m.ultima_vez) + '<br>' + (m.liberada ? '' : contato(m.ultima_vez)) +
      '</td><td class="n">' + (m.liberada ? '' : '<button data-liberar="' + m.id + '" title="Desliga este computador da licença e libera a vaga">Liberar vaga</button>') + '</td></tr>').join('');
    return '<div class="lic"><div class="linha"><span class="nome">' + esc(l.pessoa) + '</span><span class="chave">' + esc(l.chave) + '</span>' +
      '<span class="estado ' + (l.ativa ? 'ok' : 'ruim') + '">' + (l.ativa ? 'ativa' : 'bloqueada') + '</span>' +
      '<span class="sub">' + ativos.length + ' de ' + l.maquinas_max + ' computador(es)' + (l.email ? ' · ' + esc(l.email) : '') + (l.obs ? ' · ' + esc(l.obs) : '') + '</span>' +
      '<span style="flex:1"></span><button data-copiar="' + esc(l.chave) + '">Copiar chave</button>' +
      (l.ativa ? '<button class="perigo" data-bloquear="' + esc(l.chave) + '">Bloquear</button>' : '<button data-desbloquear="' + esc(l.chave) + '">Desbloquear</button>') +
      '</div>' + (linhas ? '<table class="maqs">' + linhas + '</table>' : '<div class="sub" style="margin-top:4px">ainda não ativada em nenhum computador</div>') + '</div>';
  }).join('') : '<div class="sub">Nenhuma licença ainda. Crie a primeira acima.</div>';
  $('#eventos').innerHTML = d.eventos.map(e => '<div><span class="sub">' + dataBR(e.quando) + '</span> · <b>' + esc(e.tipo) + '</b> ' +
    esc(e.chave) + ' ' + esc(e.detalhe) + (e.pais ? ' <span class="sub">(' + esc(e.pais) + ')</span>' : '') + '</div>').join('') || '<div class="sub">—</div>';
}
document.addEventListener('click', async (ev) => {
  const b = ev.target.closest('button'); if (!b) return;
  try {
    if (b.dataset.copiar) { await navigator.clipboard.writeText(b.dataset.copiar); b.textContent = 'Copiada'; setTimeout(() => { b.textContent = 'Copiar chave'; }, 1500); return; }
    if (b.dataset.bloquear && confirm('Bloquear esta licença? O Metálica para nos computadores dela na próxima conferência (até 30 dias sem internet).')) await chamar('/api/licencas/' + b.dataset.bloquear + '/bloquear', {});
    else if (b.dataset.desbloquear) await chamar('/api/licencas/' + b.dataset.desbloquear + '/desbloquear', {});
    else if (b.dataset.liberar && confirm('Liberar a vaga deste computador? Ele precisa ativar de novo para voltar a usar.')) await chamar('/api/maquinas/' + b.dataset.liberar + '/liberar', {});
    else return;
    await carregar();
  } catch (e) { alert(e.message); }
});
$('#nova').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    const r = await chamar('/api/licencas', Object.fromEntries(f));
    $('#nova-res').innerHTML = '<div class="aviso">Chave criada: <span class="chave">' + esc(r.chave) + '</span> — mande para a pessoa; ela digita na primeira abertura do Metálica.</div>';
    ev.target.reset(); await carregar();
  } catch (e) { alert(e.message); }
});
carregar().catch(e => { $('#lista').textContent = 'Não foi possível carregar: ' + e.message; });
</script></body></html>`;
