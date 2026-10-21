-- Uma obra para outro usuário (21/10/2026): os envios entre licenças (servicos/celular, rotas /pc/envio…, /pc/recebidos…).
CREATE TABLE IF NOT EXISTS envios (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  de_chave     TEXT NOT NULL,
  de_pessoa    TEXT NOT NULL DEFAULT '',
  de_maquina   TEXT NOT NULL DEFAULT '',          -- o PC que enviou (para si mesmo: só os outros PCs da chave recebem)
  de_pc        TEXT NOT NULL DEFAULT '',
  para_chave   TEXT NOT NULL,
  nome         TEXT NOT NULL DEFAULT '',          -- o nome da obra
  slug         TEXT NOT NULL DEFAULT '',
  bytes        INTEGER NOT NULL DEFAULT 0,
  sha1         TEXT NOT NULL DEFAULT '',          -- o SHA-1 do pacote inteiro (conferido ao juntar as partes)
  partes       TEXT NOT NULL DEFAULT '[]',        -- [{sha1, bytes}] em ordem (R2: envios/partes/<sha1>)
  criado       TEXT NOT NULL,
  estado       TEXT NOT NULL DEFAULT 'pendente',  -- pendente, recebido, recusado, vencido (30 dias)
  fim          TEXT,
  recebido_pc  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS envios_para ON envios (para_chave, estado);
