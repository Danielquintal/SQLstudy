# TACO — Tabela Brasileira de Composição de Alimentos, 4ª edição (NEPA/UNICAMP, 2011)

Fonte oficial: https://www.nepa.unicamp.br/taco/ — 597 alimentos, valores por 100 g da parte comestível.
Estes CSVs vêm de https://github.com/raulfdm/taco-api (pasta `references/csv`), que organizou a planilha original
da UNICAMP; os 597 alimentos foram conferidos com a planilha original (kcal, proteína, lipídeos, carboidrato,
fibra, cálcio, ferro e sódio, além dos nomes) antes de entrar no banco.

Convenções herdadas da organização: "Tr" (traço, valor entre 0 e 0,5) virou 0; "NA" (não aplicável) e "*"
(amostra em reavaliação) ficaram em branco (NULL no banco).

Carregar no banco: `python scripts/carregar_taco.py` (pode rodar de novo; atualiza sem duplicar).
