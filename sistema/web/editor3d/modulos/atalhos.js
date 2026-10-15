// Atalhos de teclado das ferramentas, configuráveis pelo usuário (15/10, decisão do usuário: "Shift+letra +
// configurável", como o SketchUp deixa).
//
// Cada ferramenta traz o atalho padrão em `static atalho` ('B', 'Shift+E', 'Espaço' ou ''). O usuário troca pelo guia
// (F1: clique no atalho e aperte a tecla nova) e a troca fica neste navegador (localStorage). Vale letra solta ou
// Shift+letra; os números são medida e vista, o Espaço é a Seleção, o Z é o zoom em tudo, Ctrl e Alt já têm dono.

const CHAVE = 'editor3d.atalhos';
//: teclas que não se dão a ferramenta nenhuma (o porquê vai para o aviso)
const RESERVADAS = { z: 'o Z é o zoom em tudo' };

/** 'Shift+E' → 'shift+e', 'B' → 'b', 'Espaço' → ' ', '' → ''. */
export function normalizarAtalho(s) {
  const t = String(s || '').trim();
  if (!t) return '';
  if (/^espa[cç]o$/i.test(t) || t === ' ') return ' ';
  const m = /^shift\s*\+\s*(.)$/i.exec(t);
  if (m) return 'shift+' + m[1].toLowerCase();
  return t.length === 1 ? t.toLowerCase() : '';
}

/** 'shift+e' → 'Shift+E', ' ' → 'Espaço'. */
export function rotuloAtalho(n) {
  if (!n) return '';
  if (n === ' ') return 'Espaço';
  if (n.startsWith('shift+')) return 'Shift+' + n.slice(6).toUpperCase();
  return n.toUpperCase();
}

/** A tecla do evento no formato normalizado (só letra, Espaço e Shift+letra; o resto: null). */
export function teclaDoEvento(ev) {
  if (!ev || ev.ctrlKey || ev.metaKey || ev.altKey || !ev.key || ev.key.length !== 1) return null;
  const k = ev.key.toLowerCase();
  return ev.shiftKey && /^[a-z]$/.test(k) ? 'shift+' + k : k;
}

/** Os atalhos trocados pelo usuário: {id: 'shift+e' | ''} ('' = sem atalho). */
export function lerPersonalizados() {
  try {
    const o = JSON.parse(localStorage.getItem(CHAVE) || '{}');
    return o && typeof o === 'object' ? o : {};
  } catch { return {}; }
}

function gravarPersonalizados(o) {
  try { localStorage.setItem(CHAVE, JSON.stringify(o)); } catch { /* janela privativa: vale só nesta sessão */ }
}

const proprio = (F, k) => Object.prototype.hasOwnProperty.call(F, k);

/**
 * Monta editor.atalhos (tecla → id) a partir dos padrões das ferramentas e das trocas do usuário, e põe em
 * `F.atalho` o rótulo que vale (o balão da barra e o guia mostram esse).
 */
export function aplicarAtalhos(editor) {
  const pers = lerPersonalizados();
  const lista = [...editor.ferramentas.values()];
  for (const F of lista) {
    // o padrão é guardado uma vez, na própria classe (o Furo é filho do Parafuso: não herdar o do pai)
    if (!proprio(F, 'atalhoPadrao')) F.atalhoPadrao = normalizarAtalho(F.atalho);
  }
  const mapa = new Map();
  // as trocas do usuário primeiro: a tecla que ele deu a uma ferramenta sai do padrão de outra
  for (const F of lista) {
    if (!proprio(pers, F.id)) continue;
    const t = normalizarAtalho(pers[F.id]);
    if (t && !mapa.has(t)) mapa.set(t, F.id);
  }
  for (const F of lista) {
    if (proprio(pers, F.id)) continue;
    const t = F.atalhoPadrao;
    if (t && !mapa.has(t)) mapa.set(t, F.id);
  }
  editor.atalhos = mapa;
  const deId = new Map([...mapa].map(([t, id]) => [id, t]));
  for (const F of lista) {
    F.atalho = rotuloAtalho(deId.get(F.id) || '');
    const b = document.querySelector(`#barra-ferramentas [data-id="${F.id}"]`);
    if (b) b.setAttribute('aria-label', F.atalho ? `${F.nome} (${F.atalho})` : F.nome);
  }
  return mapa;
}

/** Por que esta tecla não pode ser atalho (ou null se pode). */
export function motivoRecusa(t) {
  if (!t) return null;
  if (t === ' ') return 'o Espaço é a Seleção';
  const letra = t.startsWith('shift+') ? t.slice(6) : t;
  if (!/^[a-z]$/.test(letra)) return 'use uma letra ou Shift+letra (números são medida e vista)';
  if (!t.startsWith('shift+') && RESERVADAS[letra]) return RESERVADAS[letra];
  return null;
}

/**
 * Dá a tecla `t` (normalizada; '' tira o atalho) à ferramenta `id`. Se outra ferramenta tinha a tecla, ela fica sem.
 * Devolve {ok, tirado: id da que perdeu, motivo}.
 */
export function definirAtalho(editor, id, t) {
  const motivo = motivoRecusa(t);
  if (motivo) return { ok: false, motivo };
  const pers = lerPersonalizados();
  const dono = t ? editor.atalhos.get(t) : null;
  pers[id] = t;
  if (dono && dono !== id) pers[dono] = '';
  // voltou ao padrão: não guarda a troca (o padrão pode mudar numa versão nova)
  for (const F of editor.ferramentas.values()) {
    if (proprio(pers, F.id) && normalizarAtalho(pers[F.id]) === (F.atalhoPadrao || '')) delete pers[F.id];
  }
  gravarPersonalizados(pers);
  aplicarAtalhos(editor);
  return { ok: true, tirado: dono && dono !== id ? dono : null };
}

/** Volta todos os atalhos ao padrão. */
export function restaurarAtalhos(editor) {
  gravarPersonalizados({});
  aplicarAtalhos(editor);
}

/** Há alguma troca do usuário? */
export function temPersonalizados() { return Object.keys(lerPersonalizados()).length > 0; }
