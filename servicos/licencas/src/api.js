// O serviço que o programa chama (Worker metalica-licencas, 11/10/2026):
//
//   POST /api/ativar      {chave, maquina, nome_pc, usuario, versao}  → {licenca, validade, pessoa}
//   POST /api/renovar     {licenca, versao, nome_pc, usuario}         → {licenca, validade} | 403 {bloqueada, motivo}
//   GET  /api/atualizacao  Authorization: Licenca <licenca>           → a última versão publicada
//   GET  /api/baixar/<id>?licenca=…                                    → o instalador (do repositório privado)
//
// Cada chave ativa até `maquinas_max` máquinas; a mesma máquina ativando de novo não ocupa outra vaga. O GitHub é lido
// com o segredo GITHUB_TOKEN (só leitura): o programa nunca vê o token.
import { agora, emitirLicenca, lerLicenca, normalizarChave, evento, json } from './comum.js';

const txt = (v, n = 120) => String(v || '').slice(0, n);

async function ativar(req, env) {
  const c = await req.json().catch(() => ({}));
  const chave = normalizarChave(c.chave), maquina = txt(c.maquina, 80);
  if (!chave || !maquina) return json({ erro: 'informe a chave da licença' }, 400);
  const lic = await env.DB.prepare('SELECT * FROM licencas WHERE chave = ?').bind(chave).first();
  if (!lic) {
    await evento(env, req, { chave, maquina, tipo: 'recusada', detalhe: 'chave inexistente' });
    return json({ erro: 'chave de licença não encontrada — confira o que foi digitado' }, 403);
  }
  if (!lic.ativa) {
    await evento(env, req, { chave, maquina, tipo: 'recusada', detalhe: 'chave bloqueada' });
    return json({ erro: 'esta licença está bloqueada — fale com o responsável pelo Metálica', bloqueada: true }, 403);
  }
  const ja = await env.DB.prepare('SELECT * FROM maquinas WHERE chave = ? AND maquina = ?').bind(chave, maquina).first();
  if (!ja || ja.liberada) {
    const { n } = await env.DB.prepare('SELECT COUNT(*) AS n FROM maquinas WHERE chave = ? AND liberada = 0').bind(chave).first();
    if (n >= lic.maquinas_max) {
      await evento(env, req, { chave, maquina, tipo: 'recusada', detalhe: `limite de ${lic.maquinas_max} máquinas (${txt(c.nome_pc, 60)})` });
      return json({ erro: `esta licença já está ativa em ${n} computador(es), o limite dela — peça para liberar um deles na tela de licenças` }, 409);
    }
  }
  const t = agora();
  await env.DB.prepare(`INSERT INTO maquinas (chave, maquina, nome_pc, usuario, ativada, ultima_vez, versao, liberada)
      VALUES (?, ?, ?, ?, ?, ?, ?, 0)
      ON CONFLICT (chave, maquina) DO UPDATE SET nome_pc = excluded.nome_pc, usuario = excluded.usuario,
        ultima_vez = excluded.ultima_vez, versao = excluded.versao,
        ativada = CASE WHEN maquinas.liberada = 1 THEN excluded.ativada ELSE maquinas.ativada END, liberada = 0`)
    .bind(chave, maquina, txt(c.nome_pc, 80), txt(c.usuario, 80), t, t, txt(c.versao, 20)).run();
  await evento(env, req, { chave, maquina, tipo: 'ativou', detalhe: `${txt(c.nome_pc, 60)} · ${txt(c.usuario, 40)} · ${txt(c.versao, 20)}` });
  const r = await emitirLicenca(env, { chave, maquina, pessoa: lic.pessoa });
  return json({ ...r, pessoa: lic.pessoa });
}

/** a licença do pedido, conferida no banco: {lic, maq} ou uma resposta de recusa */
async function conferir(env, token) {
  const p = await lerLicenca(env, token);
  if (!p || !p.chave || !p.maquina) return { recusa: json({ erro: 'licença inválida', bloqueada: true, motivo: 'invalida' }, 403) };
  const lic = await env.DB.prepare('SELECT * FROM licencas WHERE chave = ?').bind(p.chave).first();
  if (!lic || !lic.ativa) return { recusa: json({ erro: 'esta licença foi bloqueada', bloqueada: true, motivo: 'bloqueada' }, 403), p };
  const maq = await env.DB.prepare('SELECT * FROM maquinas WHERE chave = ? AND maquina = ?').bind(p.chave, p.maquina).first();
  if (!maq || maq.liberada) {
    return { recusa: json({ erro: 'este computador foi desligado da licença — ative de novo', bloqueada: true, motivo: 'liberada' }, 403), p };
  }
  return { p, lic, maq };
}

async function renovar(req, env) {
  const c = await req.json().catch(() => ({}));
  const r = await conferir(env, c.licenca);
  if (r.recusa) {
    if (r.p) await evento(env, req, { chave: r.p.chave, maquina: r.p.maquina, tipo: 'recusada', detalhe: 'renovação' });
    return r.recusa;
  }
  const versao = txt(c.versao, 20) || r.maq.versao;
  await env.DB.prepare('UPDATE maquinas SET ultima_vez = ?, versao = ?, nome_pc = COALESCE(NULLIF(?, \'\'), nome_pc), usuario = COALESCE(NULLIF(?, \'\'), usuario) WHERE id = ?')
    .bind(agora(), versao, txt(c.nome_pc, 80), txt(c.usuario, 80), r.maq.id).run();
  if (versao !== r.maq.versao) await evento(env, req, { chave: r.p.chave, maquina: r.p.maquina, tipo: 'versao', detalhe: `${r.maq.versao} → ${versao}` });
  const e = await emitirLicenca(env, { chave: r.p.chave, maquina: r.p.maquina, pessoa: r.lic.pessoa });
  return json({ ...e, pessoa: r.lic.pessoa });
}

async function github(env, caminho, extra = {}) {
  const h = { 'User-Agent': 'metalica-licencas', Accept: 'application/vnd.github+json', ...extra };
  if (env.GITHUB_TOKEN) h.Authorization = `Bearer ${env.GITHUB_TOKEN}`;
  return fetch(`https://api.github.com/repos/${env.REPOSITORIO}${caminho}`, { headers: h, redirect: 'manual' });
}

async function ultimaVersao(env) {
  const cache = caches.default, chave = new Request('https://cache.metalica/ultima-versao');
  const guardada = await cache.match(chave);
  if (guardada) return guardada.json();
  const r = await github(env, '/releases/latest');
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const d = await r.json();
  const exe = (d.assets || []).find(a => String(a.name || '').toLowerCase().endsWith('.exe'));
  const out = { ultima: String(d.tag_name || d.name || '').replace(/^v/i, ''), publicada: String(d.published_at || '').slice(0, 10),
                notas: String(d.body || '').slice(0, 4000), asset: exe ? exe.id : null, nome: exe ? exe.name : null,
                tamanho_mb: exe ? Math.round((exe.size / 1048576) * 10) / 10 : null };
  // o instalador sobe depois da release: sem ele, não guarda (senão ficava 5 min sem o botão de atualizar)
  if (out.asset) await cache.put(chave, new Response(JSON.stringify(out), { headers: { 'Cache-Control': 'max-age=300' } }));
  return out;
}

async function atualizacao(req, env) {
  const tok = (req.headers.get('Authorization') || '').replace(/^Licenca\s+/i, '');
  const r = await conferir(env, tok);
  if (r.recusa) return r.recusa;
  try {
    const u = await ultimaVersao(env);
    return json({ ...u, arquivo: u.asset ? `/api/baixar/${u.asset}` : null });
  } catch (e) { return json({ erro: 'não foi possível consultar a última versão: ' + e.message }, 502); }
}

async function baixar(req, env, id) {
  const url = new URL(req.url);
  const r = await conferir(env, url.searchParams.get('licenca'));
  if (r.recusa) return r.recusa;
  const a = await github(env, `/releases/assets/${encodeURIComponent(id)}`, { Accept: 'application/octet-stream' });
  let corpo = a;
  if (a.status >= 300 && a.status < 400 && a.headers.get('Location')) {
    corpo = await fetch(a.headers.get('Location'));          // a URL assinada do armazenamento: sem o token
  }
  if (!corpo.ok) return json({ erro: `o instalador não veio do GitHub (${corpo.status})` }, 502);
  await evento(env, req, { chave: r.p.chave, maquina: r.p.maquina, tipo: 'baixou', detalhe: `instalador ${id}` });
  const h = new Headers({ 'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store' });
  if (corpo.headers.get('Content-Length')) h.set('Content-Length', corpo.headers.get('Content-Length'));
  return new Response(corpo.body, { status: 200, headers: h });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      if (req.method === 'POST' && url.pathname === '/api/ativar') return await ativar(req, env);
      if (req.method === 'POST' && url.pathname === '/api/renovar') return await renovar(req, env);
      if (req.method === 'GET' && url.pathname === '/api/atualizacao') return await atualizacao(req, env);
      const m = /^\/api\/baixar\/(\d+)$/.exec(url.pathname);
      if (req.method === 'GET' && m) return await baixar(req, env, m[1]);
      if (url.pathname === '/') return new Response('Metálica — serviço de licenças', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
      return json({ erro: 'rota desconhecida' }, 404);
    } catch (e) {
      return json({ erro: 'falha no serviço de licenças: ' + e.message }, 500);
    }
  },
};
