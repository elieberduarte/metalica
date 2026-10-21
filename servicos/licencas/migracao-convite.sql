-- O link de instalação com a chave (21/10/2026): o código do convite de cada licença.
ALTER TABLE licencas ADD COLUMN convite TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS licencas_convite ON licencas (convite);
