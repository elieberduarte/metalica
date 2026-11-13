-- A obra compartilhada, 2ª migração (13/11/2026): a "âncora" do apontamento (pedido do FERRAMENTA · CONTROLE DE PRODUÇÃO).
-- Até 12 ids de peças do 3D da unidade apontada: o apontamento segue a peça quando o Detalhar muda o nome do item
-- (o Controle liga o evento ao item de agora pela âncora, depois pelo nome, depois pela marca; nada é reescrito).
-- Roda UMA vez (o SQLite não tem "ADD COLUMN IF NOT EXISTS": a segunda dá "duplicate column", sem estrago).
ALTER TABLE apontamentos ADD COLUMN ancora TEXT NOT NULL DEFAULT '[]';
