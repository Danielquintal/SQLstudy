# Time Exemplo · Nutrição: passo a passo

## O que tem nesta pasta
| Arquivo | Pra quê |
|---|---|
| `planilha/Time Exemplo - Nutrição.xlsx` | A planilha com os 35 atletas. Vai pro Google Drive. |
| `lembretes.gs` | O script dos lembretes (Telegram + Google Agenda). Vai dentro da planilha. |
| `powerbi/Power BI/Time Exemplo - Consultas.pbip` | O relatório no padrão da diretoria. Abre no Power BI Desktop. |
| `planilha/criar_planilha.py` · `powerbi/ferramentas/` | Programas que geram a planilha e o Power BI. |

## 1. Planilha no Google (uma vez)
1. Em drive.google.com: **Novo › Upload de arquivo** › `planilha/Time Exemplo - Nutrição.xlsx`.
2. Abra o arquivo › **Arquivo › Salvar como Planilhas Google**. Use **essa** cópia daqui pra frente (pode apagar o .xlsx do Drive).
3. **Arquivo › Configurações › Fuso horário**: (GMT-03:00) São Paulo.
4. Na aba **Atletas**: confira os telefones marcados em amarelo e preencha a **Data de nascimento** (precisa dela pro % de gordura por Pollock 7).
5. Mantenha a planilha **restrita** (não compartilhe por link): ela tem telefones dos atletas.

## 2. Lembretes (uma vez)
1. Na planilha: **Extensões › Apps Script**. Apague o que estiver lá, cole o conteúdo de `lembretes.gs` e clique em **Salvar**.
2. Volte pra planilha e recarregue a página (F5). Aparece o menu **🏈 Time Exemplo**.
3. **🏈 Time Exemplo › 1. Configurar Telegram**. O Google pede autorização: *Continuar › escolha sua conta › Avançado › Acessar (não seguro) › Permitir*. É o seu próprio script.
   - **Token:** o do seu robô @seu_robo_bot. No Telegram, abra @BotFather › /mybots › o robô › *API Token*.
   - **Seu Id:** primeiro mande "oi" para @seu_robo_bot. Depois abra @userinfobot e mande /start: ele responde com o seu **Id** (só números).
   - Chega uma mensagem de teste no seu Telegram.
4. **🏈 Time Exemplo › 2. Ativar lembretes automáticos**.

A partir daí, sozinho (mesmo com o computador desligado):
- cada consulta da aba **Consultas** vira evento no seu Google Agenda, com aviso 1 dia e 1 hora antes;
- no Telegram: aviso no dia anterior e 1 hora antes · resumo das consultas às 7h · depois da consulta, o que falta lançar · toda segunda às 8h, atletas sem consulta e retornos atrasados.

## 3. Power BI (uma vez)
1. Abra `powerbi/Power BI/Time Exemplo - Consultas.pbip` no Power BI Desktop.
2. **Página Inicial › Transformar dados › Editar parâmetros › URL_Planilha**: cole o link da planilha do Google (o endereço que aparece no navegador, terminando em `/edit`). **OK**.
3. **Aplicar alterações**. Na primeira vez, o Power BI pede login: escolha **Conta Google** e entre com a mesma conta da planilha.
4. Depois de cada consulta: **Atualizar**.

## No dia a dia
1. Marque a consulta na aba **Consultas** (Atleta, Data, Hora, Tipo, Modalidade, Link do Meet). Status **Agendada** e, quando o atleta confirmar, **Confirmada**.
2. Depois da consulta: Status **Realizada** (ou Faltou), **Resumo e condutas**, **Próximo retorno** e uma linha na aba **Avaliações**.
3. Abra o Power BI e clique em **Atualizar**.

Não renomeie as abas nem os cabeçalhos: o script e o Power BI usam esses nomes.
