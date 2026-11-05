# Flag football · acompanhamento nutricional

Sistema leve para acompanhar as consultas de nutrição de um time de flag football, usando só ferramentas gratuitas:
**Google Planilhas** (registro), **Apps Script** (automação), **Telegram** e **Google Agenda** (lembretes) e
**Power BI** (relatório gerado por código).

> Todos os dados deste repositório são **fictícios**: atletas, telefones, nomes do time e da federação, logo e layout.

```
Planilha Google  (abas Atletas · Consultas · Avaliações · Referências · Histórico do atleta)
   │
   ├──► Apps Script (roda no Google, mesmo com o computador desligado)
   │       ├─ cada consulta vira evento no Google Agenda (aviso 1 dia e 1 hora antes)
   │       ├─ Telegram para o nutricionista: dia anterior · 1 hora antes · resumo das 7h ·
   │       │  pendências depois da consulta · resumo semanal (sem consulta / retorno atrasado)
   │       ├─ numera os atendimentos de cada atleta e preenche a aba "Histórico do atleta"
   │       └─ Formulário Google para registrar o atendimento pelo celular
   │
   └──► Power BI (conector Google Planilhas) · 8 páginas geradas por um script Python
```

## O que tem aqui
| Pasta | Conteúdo |
|---|---|
| `planilha/` | `criar_planilha.py` gera a planilha-modelo (.xlsx) com 35 atletas fictícios, listas de opções e validações |
| `apps-script/lembretes.gs` | Script da planilha: Google Agenda, Telegram, numeração, histórico, formulário e dados de teste |
| `powerbi/ferramentas/montar_powerbi.py` | Gera o projeto Power BI (`.pbip`, formato PBIR + TMDL) do zero: modelo, 77 medidas DAX, 20 colunas calculadas e 8 páginas |
| `powerbi/ferramentas/verificar_powerbi.py` | Confere se todos os campos e medidas usados nos visuais existem no modelo |
| `powerbi/Power BI/` | O projeto gerado, pronto para abrir no Power BI Desktop |
| `docs/passo-a-passo.md` | Instalação e uso no dia a dia |

## Destaques técnicos
- **Power BI como código:** o relatório inteiro (tabelas, relações, Power Query/M, DAX e o layout de cada visual) é escrito
  por um script, então dá pra versionar, revisar e recriar com um comando.
- **Power Query robusto:** lê as abas pelo nome, aceita colunas a mais ou a menos (`MissingField.UseNull`) e converte
  números e datas no padrão brasileiro.
- **DAX:** "valor atual" de cada atleta (última avaliação) com média do grupo, variação desde a 1ª avaliação com cor
  (melhorou/piorou), % de gordura por Faulkner e Pollock 7 (Jackson & Pollock + Siri), taxa de comparecimento,
  comparação com valores de referência.
- **Sem dependência circular:** colunas calculadas da dimensão usam `FILTER` + `VAR` em vez de `CALCULATE`.
- **Apps Script idempotente:** os avisos marcam o que já foi enviado (nada repete), os eventos da agenda são criados,
  atualizados ou apagados conforme o status, e o formulário completa a consulta já marcada em vez de duplicar.
- **Privacidade:** o token do robô e o chat do Telegram ficam nas *Script Properties*, nunca no código; o relatório não
  mostra telefones.

## Como usar
Veja [`docs/passo-a-passo.md`](docs/passo-a-passo.md). Resumo:
1. `python planilha/criar_planilha.py`, suba o `.xlsx` no Google Drive e salve como Planilhas Google.
2. Cole `apps-script/lembretes.gs` em **Extensões › Apps Script** e use o menu 🏈 da planilha.
3. `python powerbi/ferramentas/montar_powerbi.py`, abra o `.pbip` e cole o link da planilha no parâmetro `URL_Planilha`.

Requisitos: Python 3 com `openpyxl` (e `Pillow`, opcional), Power BI Desktop com o formato de projeto (PBIP/PBIR) ativado.
