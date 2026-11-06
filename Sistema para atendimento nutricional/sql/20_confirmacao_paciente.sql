-- Confirmação de presença pelo próprio paciente: a mensagem de confirmação leva um link (página do script do Google)
-- com os botões "Confirmo" e "Preciso remarcar"; o sistema busca as respostas e pinta a agenda.
ALTER TABLE consulta ADD COLUMN IF NOT EXISTS token_confirmacao text UNIQUE;    -- código do link desta consulta
ALTER TABLE consulta ADD COLUMN IF NOT EXISTS resposta_paciente text            -- 'sim' (confirmou) ou 'remarcar'
    CHECK (resposta_paciente IN ('sim', 'remarcar'));
ALTER TABLE consulta ADD COLUMN IF NOT EXISTS resposta_em timestamptz;           -- quando o paciente respondeu
