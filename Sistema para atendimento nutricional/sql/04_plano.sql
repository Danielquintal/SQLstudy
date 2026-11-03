-- Plano alimentar de cada paciente (um por paciente; enviar outro substitui). Pode rodar mais de uma vez.
-- Desfazer: DROP TABLE plano_alimentar;
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS plano_alimentar (
    paciente_id   integer PRIMARY KEY REFERENCES paciente (id) ON DELETE CASCADE,
    titulo        text NOT NULL,
    prescrito     date NOT NULL,
    nome_arquivo  text,
    pdf           bytea,             -- o PDF original, como foi enviado
    plano         jsonb NOT NULL,    -- o que a aba Plano alimentar mostra (páginas do PDF em imagem)
    enviado_em    timestamp NOT NULL DEFAULT now()
);
