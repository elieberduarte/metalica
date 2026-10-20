-- Uma vez só, no banco das licenças (20/10/2026): o limite de celulares por chave e quem pode enviar obras para a nuvem.
-- wrangler d1 execute metalica-licencas --remote -c wrangler.toml --file migracao-celular.sql
ALTER TABLE licencas ADD COLUMN celulares_max INTEGER NOT NULL DEFAULT 3;
ALTER TABLE licencas ADD COLUMN envia_obras INTEGER NOT NULL DEFAULT 0;   -- 1 = os PCs desta chave enviam as obras
