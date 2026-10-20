# Celular de qualquer lugar

O serviço que leva as obras ao celular fora da rede do escritório (20/10/2026). É um Worker da Cloudflare com os
arquivos no R2, ligado ao **mesmo banco D1 das licenças** (`servicos/licencas`).

| Peça | Nome | Para quê |
|---|---|---|
| Worker | `metalica-celular` → https://metalica-celular.elieber-lucas.workers.dev | as telas do celular, a entrada (chave ou QR) e os pacotes das obras |
| R2 | `metalica-obras` | `arquivos/<sha1>` (cada arquivo uma vez), `obras/<obra>/manifesto.json`, `indice.json`, `telas.json` |
| D1 | `metalica-licencas` | tabelas `aparelhos` e `codigos_celular` (schema.sql); colunas `celulares_max` e `envia_obras` em `licencas` |

## Como funciona

- **O PC envia** (`sistema/celular/nuvem.py`, ligado em *Projetos → Celular → De qualquer lugar*): as obras com a chave
  **Celular** ligada no cartão, só o que mudou, conferindo a cada minuto. Ele prova quem é com a licença assinada dele;
  só a licença marcada **Envia obras** na tela de licenças pode gravar. Obra desligada (ou arquivada) sai da nuvem.
- **O celular entra** de dois jeitos: o **QR code da nuvem** mostrado num PC com licença (o celular fica na licença daquele
  PC; o código vale uma vez, por 5 minutos) ou a **chave de licença** da pessoa digitada no celular. Até 3 celulares por
  chave (`celulares_max`). No celular fica um cookie com um segredo; no banco, só o SHA-256 dele.
- **Bloquear a chave** corta os computadores e os celulares dela; **liberar a vaga** de um celular na tela de licenças
  corta só aquele (em até 1 minuto, o tempo que o Worker lembra o aparelho).
- Todas as obras enviadas aparecem para todos os celulares liberados (decisão de 20/10; por pessoa pode vir depois).
- O app do celular é o mesmo da rede local (`sistema/web/celular`): o PC envia as telas junto, então atualizar o programa
  no PC atualiza o celular. A cópia para a obra (sem rede) funciona igual — o workers.dev já é HTTPS.
- Sem segredos neste Worker: a chave **pública** das licenças basta para conferir o PC.

## Comandos (wrangler em `%LOCALAPPDATA%\Metalica-ferramentas\cloudflare`, rodando nesta pasta)

Uma vez só (o R2 precisa estar habilitado no painel da Cloudflare — *R2 Object Storage*):

```
wrangler r2 bucket create metalica-obras
wrangler d1 execute metalica-licencas --remote -c wrangler.toml --file schema.sql
wrangler d1 execute metalica-licencas --remote -c wrangler.toml --file migracao-celular.sql
```

Publicar:

```
wrangler deploy -c wrangler.toml
```

Testar sem a Cloudflare: `sistema/testes/verificadores/verif_celular_nuvem.py` sobe este Worker com `wrangler dev --local`
(D1 e R2 locais numa pasta temporária), envia uma obra, entra pelo celular e abre o 3D no Chrome.
