-- A obra compartilhada (13/11/2026, FERRAMENTA · OBRA COMPARTILHADA, passo 1a): a mesma obra entre as pessoas da equipe.
-- Mesmo banco D1 das licenças (metalica-licencas). Só tabelas novas: nada do que já existe muda.
--
-- obras         a obra compartilhada, pelo obra_id fixo (uuid gravado no projeto.json; nunca o slug nem o nome)
-- obra_acessos  quem tem acesso e com qual papel (pessoa = licença): dono, editor, apontador, leitor
-- apontamentos  os apontamentos de produção, um evento por linha, nunca apagado (erro = estorno, outro evento)
--
-- Quem garante é a nuvem: o Worker recusa o apontamento de quem não tem papel para apontar (dono, editor, apontador)
-- e grava a chave e a pessoa da licença que enviou (não a que o PC diz). Dar e tirar acesso: só a tela do dev (API do
-- D1 com o login do wrangler do usuário), nunca por rota do Worker.

CREATE TABLE IF NOT EXISTS obras (
  obra_id     TEXT PRIMARY KEY,                 -- uuid (hex de 32) gravado no projeto.json da obra
  nome        TEXT NOT NULL DEFAULT '',
  dono_chave  TEXT NOT NULL,                    -- a licença do dono (o usuário, no dev)
  criada      TEXT NOT NULL,
  ativa       INTEGER NOT NULL DEFAULT 1        -- 0 = deixou de ser compartilhada (os apontamentos ficam guardados)
);

CREATE TABLE IF NOT EXISTS obra_acessos (
  obra_id     TEXT NOT NULL REFERENCES obras(obra_id),
  chave       TEXT NOT NULL REFERENCES licencas(chave),
  papel       TEXT NOT NULL,                    -- dono, editor, apontador, leitor
  desde       TEXT NOT NULL,
  ultima_vez  TEXT NOT NULL DEFAULT '',         -- o último pedido desta licença sobre esta obra
  PRIMARY KEY (obra_id, chave)
);

CREATE TABLE IF NOT EXISTS apontamentos (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT, -- a ordem de chegada na nuvem (o PC pede "depois de <seq>")
  obra_id     TEXT NOT NULL,
  id          TEXT NOT NULL,                     -- o id do evento, criado no PC (o mesmo do apontamentos.jsonl)
  chave       TEXT NOT NULL,                     -- a licença que enviou (conferida pela assinatura)
  pessoa      TEXT NOT NULL DEFAULT '',          -- a pessoa dessa licença (o "quem" que vale)
  maquina     TEXT NOT NULL DEFAULT '',          -- o nome do PC
  quando      TEXT NOT NULL DEFAULT '',          -- a hora do apontamento no PC
  data        TEXT NOT NULL DEFAULT '',          -- o dia do serviço (AAAA-MM-DD)
  etapa       TEXT NOT NULL,
  item        TEXT NOT NULL,
  refs        TEXT NOT NULL DEFAULT '[]',
  quantidade  INTEGER NOT NULL,
  kg          REAL NOT NULL DEFAULT 0,
  estorno_de  TEXT,
  obs         TEXT NOT NULL DEFAULT '',
  recebido    TEXT NOT NULL,                     -- a hora em que chegou na nuvem
  UNIQUE (obra_id, id)
);

CREATE INDEX IF NOT EXISTS obra_acessos_chave ON obra_acessos (chave);
CREATE INDEX IF NOT EXISTS apontamentos_obra ON apontamentos (obra_id, seq);
