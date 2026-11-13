-- A obra compartilhada, 3ª migração (13/11/2026): a tesoura montada no Controle (pedido do FERRAMENTA · CONTROLE DE PRODUÇÃO,
-- 283c7e8). A montada (T52 = TESOURA 1-1 + TESOURA 5) é apontada inteira e grava UMA linha por parte, cada uma com
-- "montada" (o nome da montada, para o histórico) e "lote" (o id comum das partes apontadas juntas: o estorno de uma desfaz
-- o lote inteiro — sem ele, outro computador estornaria só uma parte).
-- Roda UMA vez (o SQLite não tem "ADD COLUMN IF NOT EXISTS": a segunda dá "duplicate column", sem estrago).
ALTER TABLE apontamentos ADD COLUMN montada TEXT NOT NULL DEFAULT '';
ALTER TABLE apontamentos ADD COLUMN lote TEXT NOT NULL DEFAULT '';
