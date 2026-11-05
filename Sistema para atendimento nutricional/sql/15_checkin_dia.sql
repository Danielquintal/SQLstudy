-- Dia da semana em que o paciente recebe o pedido de check-in (e-mail automático e lembrete do WhatsApp em Contatos).
-- 0 = domingo ... 6 = sábado; vazio = automático (7 dias depois do último pedido). Pode rodar mais de uma vez.
-- Desfazer: ALTER TABLE paciente DROP COLUMN checkin_dia;
SET client_encoding = 'UTF8';

ALTER TABLE paciente ADD COLUMN IF NOT EXISTS checkin_dia smallint CHECK (checkin_dia BETWEEN 0 AND 6);
