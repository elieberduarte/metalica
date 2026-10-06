// Metálica no celular — o trabalhador de fundo (service worker): a cópia para a obra.
//
// Na rede, tudo vem do computador na hora (as telas novas de um programa atualizado também), e o
// que chega fica guardado. Sem rede, as telas e os projetos guardados abrem da cópia, e a resposta
// leva o cabeçalho X-Metalica-Copia para a tela dizer de quando ela é.
//
// * Telas (html, js, css, bibliotecas): da rede, com a cópia como reserva.
// * Lista de projetos, manifesto e estado: da rede (até 4 s), com a cópia como reserva.
// * Arquivos do pacote com a versão no endereço (?v=SHA-1): não mudam — da cópia, ou da rede uma vez.
// * 401 (aparelho não pareado) e 202 (preparando no computador) nunca são guardados.
//
// Só funciona em conexão segura (HTTPS ou localhost): é a decisão do HTTPS da Fase 2.

const TELAS = 'metalica-telas-1';
const DADOS = 'metalica-dados-1';
const BASE_TELAS = ['./', 'index.html', 'celular.css', 'celular.js', 'visor3d.js', 'lib/pdf.min.mjs', 'lib/pdf.worker.min.mjs',
                    'manifest.webmanifest', 'lib/icone-180.png', 'lib/icone-192.png', 'lib/icone-512.png',
                    '../lib/three.module.js', '../lib/OrbitControls.js'];
const ESPERA_REDE = 4000;

self.addEventListener('install', ev => {
  ev.waitUntil(caches.open(TELAS).then(c => c.addAll(BASE_TELAS)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener('activate', ev => {
  ev.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('metalica-') && k !== TELAS && k !== DADOS)
    .map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function comPrazo(promessa, ms) {
  return new Promise((ok, falha) => {
    const t = setTimeout(() => falha(new Error('prazo')), ms);
    promessa.then(r => { clearTimeout(t); ok(r); }, e => { clearTimeout(t); falha(e); });
  });
}

/** A resposta guardada, marcada como cópia (com a data em que foi guardada). */
async function daCopia(pedido, cache) {
  const r = await (await caches.open(cache)).match(pedido, { ignoreSearch: cache === TELAS });
  if (!r) return null;
  const h = new Headers(r.headers);
  h.set('X-Metalica-Copia', h.get('X-Metalica-Guardado') || '1');
  return new Response(await r.blob(), { status: r.status, statusText: r.statusText, headers: h });
}

async function guardar(cache, pedido, resposta) {
  if (!resposta || resposta.status !== 200) return;
  const h = new Headers(resposta.headers);
  h.set('X-Metalica-Guardado', new Date().toISOString());
  const copia = new Response(await resposta.clone().blob(), { status: 200, statusText: 'OK', headers: h });
  await (await caches.open(cache)).put(pedido, copia);
}

async function redePrimeiro(pedido, cache, prazo) {
  try {
    const r = await comPrazo(fetch(pedido), prazo);
    if (r.status === 200) guardar(cache, pedido, r.clone());
    return r;
  } catch (e) {
    const c = await daCopia(pedido, cache);
    if (c) return c;
    throw e;
  }
}

async function copiaPrimeiro(pedido) {
  const c = await (await caches.open(DADOS)).match(pedido);
  if (c) return c;
  const r = await fetch(pedido);
  if (r.status === 200) await guardar(DADOS, pedido, r.clone());
  return r;
}

self.addEventListener('fetch', ev => {
  const pedido = ev.request;
  if (pedido.method !== 'GET') return;
  const url = new URL(pedido.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/celular/parear')) return;              // o pareamento vai sempre à rede
  if (url.pathname.startsWith('/celular/dados/') || url.pathname.startsWith('/celular/api/')) {
    if (url.searchParams.has('v')) ev.respondWith(copiaPrimeiro(pedido));
    else ev.respondWith(redePrimeiro(pedido, DADOS, ESPERA_REDE));
    return;
  }
  if (url.pathname.startsWith('/celular/') || url.pathname === '/lib/three.module.js' || url.pathname === '/lib/OrbitControls.js') {
    ev.respondWith(redePrimeiro(pedido, TELAS, ESPERA_REDE));
  }
});
