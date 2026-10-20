-- O celular de qualquer lugar (20/10/2026): as tabelas novas no MESMO banco das licenças (D1 metalica-licencas).
-- Um celular entra pela chave de licença de uma pessoa (digitada no celular) ou pelo QR code de um PC com licença;
-- bloquear a chave corta os computadores e os celulares dela. As colunas novas de `licencas` estão em migracao-celular.sql.

CREATE TABLE IF NOT EXISTS aparelhos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  chave       TEXT NOT NULL REFERENCES licencas(chave),
  segredo     TEXT NOT NULL UNIQUE,            -- SHA-256 (hex) do segredo que fica no cookie do celular
  nome        TEXT NOT NULL DEFAULT '',        -- "iPhone", "Android SM-S938B"… (renomeável na tela)
  via         TEXT NOT NULL DEFAULT '',        -- qr (lido num PC) ou chave (digitada no celular)
  criado      TEXT NOT NULL,
  ultima_vez  TEXT NOT NULL,
  liberado    INTEGER NOT NULL DEFAULT 0       -- 1 = a vaga foi liberada na tela (o celular precisa entrar de novo)
);

CREATE TABLE IF NOT EXISTS codigos_celular (
  codigo  TEXT PRIMARY KEY,                    -- o do QR, uso único
  chave   TEXT NOT NULL,                       -- a licença do PC que mostrou o QR
  vence   INTEGER NOT NULL                     -- ms desde 1970
);

CREATE INDEX IF NOT EXISTS aparelhos_chave ON aparelhos (chave);
