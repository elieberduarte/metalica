// As obras compartilhadas na tela Licenças do dev (13/11/2026, FERRAMENTA · OBRA COMPARTILHADA; obra_compartilhada_dev.py).
// Só o dono (o usuário, no dev) dá acesso: Editor (aponta e, na 1b, pega a vez de editar), Apontador (aponta) ou Leitor (só vê).
(function () {
  const PAPEIS = [['editor', 'Editor'], ['apontador', 'Apontador'], ['leitor', 'Leitor']];
  const NOME = { dono: 'Dono', editor: 'Editor', apontador: 'Apontador', leitor: 'Leitor' };
  const q = (s, r) => (r || document).querySelector(s);
  const e = (t) => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const dia = (iso) => { if (!iso) return '—'; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); };

  async function pedir(rota, corpo) {
    const r = await fetch(rota, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }

  const sec = document.createElement('section');
  sec.className = 'lic-sec';
  sec.id = 'obras-compartilhadas';
  sec.innerHTML = '<h3>Obras compartilhadas</h3><div class="sub" style="margin:-4px 0 8px">A mesma obra entre as pessoas da equipe. ' +
    'Os apontamentos de produção vão para a nuvem e todos veem; quem pode apontar é quem você escolher aqui (a nuvem confere).</div>' +
    '<div id="oc-corpo">Lendo…</div>';
  const antes = [...document.querySelectorAll('.lic-pagina > .lic-sec')].find(s => /Licenças/.test(s.textContent.slice(0, 20)));
  (antes ? antes.parentNode.insertBefore(sec, antes) : q('.lic-pagina').appendChild(sec));

  let dados = null;
  async function carregar() {
    const corpo = q('#oc-corpo');
    try {
      dados = await pedir('/api/dev/compartilhadas');
    } catch (x) {
      corpo.innerHTML = '<div class="lic-aviso lic-erro">Não foi possível ler as obras compartilhadas: ' + e(x.message) + '</div>';
      return;
    }
    if (dados.sem_tabelas) {
      corpo.innerHTML = '<div class="lic-aviso">As tabelas da obra compartilhada ainda não estão no banco da nuvem ' +
        '(servicos/celular/migracao-obra-compartilhada.sql). Depois da migração, esta seção funciona.</div>';
      return;
    }
    const obras = dados.obras.map(o => {
      const tem = new Set(o.acessos.map(a => a.chave));
      const linhas = o.acessos.map(a => '<tr><td><b>' + e(a.pessoa || a.chave) + '</b></td><td>' +
        (a.papel === 'dono' ? 'Dono' : '<select data-oc-papel="' + e(a.chave) + '" data-obra="' + o.obra_id + '">' +
          PAPEIS.map(([v, t]) => '<option value="' + v + '"' + (a.papel === v ? ' selected' : '') + '>' + t + '</option>').join('') + '</select>') +
        '</td><td class="n">desde ' + dia(a.desde) + '</td><td class="n">último acesso ' + dia(a.ultima_vez) + '</td><td class="n">' +
        (a.papel === 'dono' ? '' : '<button type="button" data-oc-tirar="' + e(a.chave) + '" data-obra="' + o.obra_id + '">Tirar o acesso</button>') +
        '</td></tr>').join('');
      const livres = dados.pessoas.filter(p => !tem.has(p.chave));
      const dar = livres.length ? '<tr><td colspan="5"><span class="sub">Dar acesso:</span> <select data-oc-pessoa="' + o.obra_id + '">' +
        livres.map(p => '<option value="' + e(p.chave) + '">' + e(p.pessoa) + '</option>').join('') + '</select> como <select data-oc-novo-papel="' +
        o.obra_id + '">' + PAPEIS.map(([v, t]) => '<option value="' + v + '">' + t + '</option>').join('') + '</select> ' +
        '<button type="button" data-oc-dar="' + o.obra_id + '">Dar acesso</button></td></tr>' : '';
      return '<div class="lic"><div class="lic-linha"><span class="lic-nome">' + e(o.nome) + '</span>' +
        '<span class="lic-estado ok">☁ compartilhada</span><span class="sub">' + o.apontamentos + ' apontamento(s) na nuvem' +
        (o.ultimo ? ' · o último ' + dia(o.ultimo) : '') + (o.slug ? ' · neste dev: ' + e(o.slug) : ' · não está neste dev') +
        ' · código ' + e(o.obra_id.slice(0, 8)) + '</span></div><table class="lic-maqs">' + linhas + dar + '</table></div>';
    }).join('');
    const locais = dados.locais.filter(l => !l.obra_id);
    const nova = '<div class="lic-linha" style="margin-top:10px"><span class="sub">Compartilhar uma obra deste dev:</span>' +
      '<select id="oc-slug">' + locais.map(l => '<option value="' + e(l.slug) + '">' + e(l.nome) + '</option>').join('') + '</select>' +
      '<button type="button" id="oc-compartilhar"' + (locais.length ? '' : ' disabled') + '>Compartilhar…</button></div>';
    corpo.innerHTML = (obras || '<div class="sub">Nenhuma obra compartilhada ainda.</div>') + nova;
  }

  sec.addEventListener('change', async (ev) => {
    const s = ev.target.closest('select[data-oc-papel]');
    if (!s) return;
    try { await pedir('/api/dev/compartilhadas/acesso', { obra_id: s.dataset.obra, chave: s.dataset.ocPapel, papel: s.value }); }
    catch (x) { alert(x.message); }
    carregar();
  });
  sec.addEventListener('click', async (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    try {
      if (b.id === 'oc-compartilhar') {
        const s = q('#oc-slug'), nome = s.options[s.selectedIndex].text;
        if (!confirm('Compartilhar "' + nome + '"?\n\nA obra ganha um código fixo, entra na nuvem com você como Dono, e os apontamentos ' +
          'dela passam a subir para a nuvem. Depois você escolhe quem tem acesso e com qual papel.')) return;
        b.disabled = true;
        await pedir('/api/dev/compartilhadas/compartilhar', { slug: s.value });
      } else if (b.dataset.ocDar) {
        const o = b.dataset.ocDar;
        await pedir('/api/dev/compartilhadas/acesso', { obra_id: o, chave: q('[data-oc-pessoa="' + o + '"]', sec).value,
                                                        papel: q('[data-oc-novo-papel="' + o + '"]', sec).value });
      } else if (b.dataset.ocTirar) {
        if (!confirm('Tirar o acesso desta pessoa à obra? Ela deixa de ver os apontamentos e de apontar (a cópia que está no computador dela fica lá).')) return;
        await pedir('/api/dev/compartilhadas/acesso', { obra_id: b.dataset.obra, chave: b.dataset.ocTirar, papel: '' });
      } else return;
    } catch (x) { alert(x.message); }
    carregar();
  });
  const bt = q('#btn-atualizar');
  if (bt) bt.addEventListener('click', carregar);
  carregar();
})();
