-- O banco das licenças do Metálica (Cloudflare D1, 11/10/2026).
-- Uma licença é uma chave dada a uma pessoa; cada chave ativa até `maquinas_max` computadores (2 por padrão).
-- Bloquear a chave faz o programa parar na próxima renovação (no máximo 30 dias sem internet).

CREATE TABLE IF NOT EXISTS licencas (
  chave         TEXT PRIMARY KEY,              -- MTL-XXXX-XXXX-XXXX
  pessoa        TEXT NOT NULL,
  email         TEXT NOT NULL DEFAULT '',
  obs           TEXT NOT NULL DEFAULT '',
  maquinas_max  INTEGER NOT NULL DEFAULT 2,
  ativa         INTEGER NOT NULL DEFAULT 1,    -- 0 = bloqueada
  criada        TEXT NOT NULL,
  bloqueada_em  TEXT
);

CREATE TABLE IF NOT EXISTS maquinas (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  chave       TEXT NOT NULL REFERENCES licencas(chave),
  maquina     TEXT NOT NULL,                   -- impressão da máquina (hash do MachineGuid do Windows)
  nome_pc     TEXT NOT NULL DEFAULT '',
  usuario     TEXT NOT NULL DEFAULT '',
  ativada     TEXT NOT NULL,
  ultima_vez  TEXT NOT NULL,
  versao      TEXT NOT NULL DEFAULT '',
  liberada    INTEGER NOT NULL DEFAULT 0,      -- 1 = a vaga foi liberada na tela (a máquina precisa ativar de novo)
  UNIQUE (chave, maquina)
);

CREATE TABLE IF NOT EXISTS eventos (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  quando   TEXT NOT NULL,
  chave    TEXT NOT NULL DEFAULT '',
  maquina  TEXT NOT NULL DEFAULT '',
  tipo     TEXT NOT NULL,                      -- ativou, renovou, recusada, bloqueada, liberada, atualizou, criada…
  detalhe  TEXT NOT NULL DEFAULT '',
  pais     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS eventos_quando ON eventos (quando);
CREATE INDEX IF NOT EXISTS maquinas_chave ON maquinas (chave);
