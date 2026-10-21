# Licenças do Metálica

O serviço que libera o programa instalado (11/10/2026). São dois Workers da Cloudflare no mesmo banco D1:

| Worker | Endereço | Para quê |
|---|---|---|
| `metalica-licencas` | https://metalica-licencas.elieber-lucas.workers.dev | o programa: ativar, renovar, consultar e baixar a atualização |
| `metalica-licencas-admin` | https://metalica-licencas-admin.elieber-lucas.workers.dev | a tela das licenças (atrás do Cloudflare Access) |

Banco D1 `metalica-licencas` (id `cb870249-814d-4c2a-a610-490539a21e65`), tabelas em `schema.sql`.

## Como funciona

- A pessoa recebe uma chave `MTL-XXXX-XXXX-XXXX` e digita na primeira abertura do Metálica (tela `/ativar`).
- O serviço confere se a chave está ativa e se há vaga (2 computadores por chave) e devolve a licença assinada com
  Ed25519. O programa (`sistema/licenca.py`) confere a assinatura com a chave pública, sem internet.
- A licença vale 30 dias e se renova sozinha a cada abertura com rede (e a cada 6 h com o programa aberto).
- Bloquear a chave, ou liberar a vaga de um computador, faz a próxima renovação ser recusada: o programa volta à
  tela de ativação (no máximo 30 dias depois, se o computador ficar sem internet).
- A atualização vem pelo serviço: ele lê a última release do GitHub com o segredo `GITHUB_TOKEN` e entrega o
  instalador só a quem tem licença. Com isso o repositório pode ficar privado.
- Só o programa instalado exige licença; rodando do código (desenvolvimento, testes) não.

## Segredos e chaves

- `LICENCA_CHAVE_PRIVADA` e `LICENCA_CHAVE_PUBLICA` (Worker da API): o par Ed25519. Cópia em
  `%LOCALAPPDATA%\Metalica-ferramentas\cloudflare\licenca-chave-*.txt` — **guardar a privada em lugar seguro**: perdê-la
  obriga a gerar outro par e publicar uma versão do programa com a pública nova.
- `GITHUB_TOKEN` (Worker da API): token *fine-grained* do GitHub, só leitura de "Contents" do repositório metalica.
- `ACCESS_EQUIPE` e `ACCESS_AUD` (Worker da tela, em `wrangler-admin.toml`): o nome da equipe do Zero Trust e o
  "Application Audience (AUD) Tag" do Access. Sem eles a tela não abre (fechada por padrão).

## Comandos (wrangler em `%LOCALAPPDATA%\Metalica-ferramentas\cloudflare`)

```
wrangler deploy -c wrangler.toml                 # o serviço do programa
wrangler deploy -c wrangler-admin.toml           # a tela
wrangler secret put GITHUB_TOKEN -c wrangler.toml
wrangler d1 execute metalica-licencas --remote -c wrangler.toml --command "SELECT * FROM licencas"
```

Criar uma chave sem a tela (emergência):

```
wrangler d1 execute metalica-licencas --remote -c wrangler.toml --command "INSERT INTO licencas (chave, pessoa, email, obs, maquinas_max, ativa, criada) VALUES ('MTL-XXXX-XXXX-XXXX', 'Nome', '', '', 2, 1, '2026-10-11T00:00:00Z')"
```

## Link de instalação (21/10/2026)

Na tela das licenças (dev): **🔗 Link de instalação** em cada licença ativa. O link
(`https://metalica-licencas.elieber-lucas.workers.dev/convite/<código>`) abre uma página com o botão de baixar e a chave;
o instalador sai com a chave no nome (`Metalica-instalador MTL-XXXX-XXXX-XXXX.exe`). O instalador (`empacotar/instalador.iss`,
`[Code]`) lê a chave do próprio nome e a grava em `%LOCALAPPDATA%\Metálica\convite.txt`; o Metálica (`sistema/licenca.py`,
`ativar_pelo_convite`, e a tela `/ativar`) se ativa sozinho com ela na primeira abertura — a partir da versão que levar
essas mudanças (0.9.1); antes, a pessoa cola a chave mostrada na página.

- O código fica na coluna `licencas.convite` (`migracao-convite.sql`; a tela cria a coluna sozinha se faltar).
- O mesmo link a cada clique; bloquear a licença desliga o link (a página diz "convite não encontrado", 404).
- Cada download pelo convite vira o evento `baixou` com a máquina `convite`.
