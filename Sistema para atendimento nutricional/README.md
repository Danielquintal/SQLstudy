# Banco de dados App Naive

> **Dados fictícios.** Os pacientes deste repositório têm nomes inventados. CPF, telefone/WhatsApp, e-mail,
> endereço e código do App Naive foram retirados, e as datas de nascimento são fictícias. As avaliações
> antropométricas servem só para demonstrar o sistema e não se ligam a nenhuma pessoa identificável.
> Para usar com dados reais, carregue o seu próprio `sql/02_dados.sql` (gerado por `scripts/gerar_dados.py`).

Pacientes e avaliações antropométricas em PostgreSQL, com as planilhas por paciente e as páginas de evolução (artefatos) geradas a partir do banco.

## Estrutura

| Pasta / arquivo | Conteúdo |
|---|---|
| `sql/01_schema.sql` | Tabelas `paciente` e `avaliacao` e as views `vw_avaliacao` e `vw_resumo_paciente` |
| `sql/02_dados.sql` | Carga inicial (gerada por `scripts/gerar_dados.py`) |
| `scripts/gerar_dados.py` | Gera `02_dados.sql` a partir da exportação do App Naive e do `.json` da coleta |
| `scripts/atualizar_paciente.py` | Passa a aba Tabela da planilha de um paciente para o banco e gera de novo a planilha e a página |
| `scripts/campos.py` | Correspondência entre as colunas do banco e os campos do App Naive |
| `scripts/planilha_paciente.py` | Monta a planilha de um paciente (abas Evolução, Tabela, Gráficos) |
| `scripts/montar_pagina.py` | Monta a página HTML de evolução (artefato) de um paciente |
| `web/template.html` | Modelo da página de evolução |
| `web/planos/` | Planos alimentares antigos em JSON (os atuais ficam no banco, tabela `plano_alimentar`) |
| `sql/04_plano.sql` | Tabela dos planos alimentares enviados em PDF |
| `sql/06_alimentos.sql` | Tabelas de alimentos (TACO e próprios) e medidas caseiras |
| `sql/07_plano_editor.sql` | Guarda a montagem dos planos feitos no sistema, para editar depois |
| `scripts/nutricao.py` | Fórmulas de energia (Harris-Benedict, Mifflin-St Jeor, FAO/OMS) e cálculo dos nutrientes |
| `dados/taco/` | TACO 4ª edição em CSV; `scripts/carregar_taco.py` carrega no banco |
| `web/artefatos.json` | Link publicado de cada paciente; publicar sempre no mesmo link |
| `web/pedidos.json` | Fila de links a publicar (criada pelo sistema) |
| `scripts/publicar_pedidos.py` | Gera as páginas da fila e registra os links publicados |
| `scripts/exportar_github.py` | Gera a cópia do projeto para o GitHub, com dados fictícios |
| `web/paginas/` | Páginas geradas, prontas para publicar |
| `sistema/` | Sistema no navegador (Flask): `app.py` é o servidor, `templates/` as telas, `static/` o estilo |
| `Abrir sistema.bat` | Abre o sistema com dois cliques (o atalho da Área de Trabalho aponta para ele) |
| `scripts/calculos.py` | Fórmulas e tabelas de classificação, iguais às do App Naive |
| `sql/03_whatsapp.sql` | Tabela dos contatos de WhatsApp e data do retorno (`03_whatsapp_desfazer.sql` desfaz) |

As planilhas que você edita ficam em `Downloads\Antropometria por paciente`.

## Passo 1: preparar o ambiente (uma vez só)

1. **Abrir no VS Code:** Arquivo → Abrir Pasta → `Downloads\Banco de dados App Naive`.
   O VS Code vai sugerir as extensões recomendadas (Python, PostgreSQL e Live Preview). Aceite.
2. **Guardar a senha do PostgreSQL** para os scripts não perguntarem toda vez.
   Crie o arquivo `%APPDATA%\postgresql\pgpass.conf` (crie a pasta `postgresql` se não existir) com uma linha:
   ```
   localhost:5432:*:postgres:SUA_SENHA_AQUI
   ```
   Esse arquivo fica só no seu computador e não vai para nenhum script.
3. **Rodar as tarefas, em ordem:** Terminal → Executar Tarefa…
   1. `1. Instalar dependências do Python`
   2. `2. Criar o banco app_naive` (pule se já criou)
   3. `3. Recarregar banco (esquema + dados)`
   4. `4. Testar conexão com o banco`: deve mostrar 358 pacientes e 1297 avaliações
4. **Conectar a extensão PostgreSQL:** ícone do elefante na barra lateral → nova conexão →
   servidor `localhost`, usuário `postgres`, banco `app_naive`.

> A tarefa 3 apaga e recarrega tudo. Depois que o fluxo de atualização por paciente estiver pronto (passo 2), use-a só para refazer o banco do zero.

## Passo 2: atualizar um paciente

1. Abra a planilha do paciente em `Downloads\Antropometria por paciente` e vá na aba **Tabela**.
2. Para uma avaliação nova, preencha uma linha no fim: data na coluna A (dd/mm/aaaa) e as medidas nas colunas.
   Para corrigir um valor, mude a célula. Vírgula ou ponto nos decimais, tanto faz.
   Para uma medida que não tem coluna, copie o cabeçalho de outra planilha que tenha (o texto precisa ser igual).
3. Salve e **feche** a planilha no Excel.
4. Terminal → Executar Tarefa… → `5. Conferir paciente (simular, não grava)` → digite o nome.
   Mostra o que vai mudar: `+` avaliação nova, `~` valor alterado.
5. Se estiver certo: `6. Atualizar paciente` → mesmo nome. Grava no banco e gera de novo a planilha
   (abas Evolução, Tabela, Gráficos) e a página em `web/paginas/`.

Também pelo terminal: `python scripts/atualizar_paciente.py "Nome" [--simular] [--id N]`.

- Nada é apagado do banco: uma linha removida da planilha volta quando a planilha é gerada de novo.
- Com erro na planilha (data ou número inválido), nada é gravado e o script diz a linha.
- Nomes repetidos: o script lista os pacientes com o número de cada um; rode pelo terminal com `--id N`.
- As abas Evolução e Gráficos são refeitas a cada atualização; edite só a aba Tabela.

## Sistema no navegador (recomendado)

Faz o mesmo que o passo 2 sem Excel e sem terminal.

1. Dois cliques no atalho **Avaliações antropométricas** da Área de Trabalho (ou em `Abrir sistema.bat`,
   ou Terminal → Executar Tarefa… → `7. Abrir o sistema`).
   Abre uma janela preta e o navegador em `http://localhost:5000`. **Deixe a janela preta aberta** enquanto usa; fechar ela desliga o sistema.
2. **Pacientes:** digite parte do nome (sem acento mesmo) e Enter para abrir o primeiro da lista.
3. **Nova avaliação:** altura, diâmetros ósseos e protocolo já vêm da última avaliação. Os campos de borda tracejada
   são calculados enquanto você digita, com as fórmulas do App Naive (`scripts/calculos.py`):
   - IMC e classificação (adultos: OMS; 60 anos ou mais: Lipschitz) e peso ideal;
   - RCQ e risco (Bray, por sexo e idade);
   - CMB = braço relaxado esquerdo − π × dobra tricipital, adequação pelo P50 de Frisancho e classificação;
   - somatório, densidade (Pollock 7, Pollock 3 ou Guedes) e % de gordura (Siri ou Brozek), com a classificação por sexo e idade;
   - massas de gordura, livre de gordura, residual, óssea (precisa dos diâmetros do punho e do fêmur) e muscular;
   - classificação do % de gordura da bioimpedância.

   Um campo calculado corrigido à mão é mantido e entra nas contas seguintes. Conferido com as 1297 avaliações do
   App Naive: 99,7% dos valores iguais. Para 56 anos ou mais (e as duas primeiras faixas de mulheres de 46 a 55),
   a classificação do % de gordura tem poucos exemplos no banco: confira.
4. **Gravar:** grava no banco e gera de novo a planilha e a página do paciente. Se a planilha estiver aberta no Excel,
   o sistema avisa; feche o Excel e clique em **Gerar planilha e página**.
5. **Abrir** numa avaliação para corrigir ou excluir (a exclusão pede confirmação).
6. **Ver evolução** mostra a página exatamente como o paciente vê. Para atualizar o link do paciente, peça ao Claude para publicar.

- Só funciona neste computador: ninguém na internet ou na mesma rede Wi-Fi consegue abrir.
- Não dá para lançar duas avaliações na mesma data do mesmo paciente: abra a que já existe.
- Planilha e sistema convivem: se editar a planilha, use as tarefas 5 e 6 como antes.

## Página de evolução e links dos pacientes

- **Ficha do paciente → aba Evolução:** a mesma página que o paciente recebe, gerada na hora com os dados do banco,
  para qualquer paciente com avaliações.
- **Link do paciente:** só quem você escolher. Na ficha, "Pedir link" (ou "Pedir atualização do link") coloca o
  paciente na fila do menu **Links**. Quem já tem link entra sozinho na fila quando você grava ou exclui uma avaliação.
- Para publicar a fila, peça ao Claude: **"publique os links pedidos"**. Quem já tem link continua com o mesmo
  endereço; link novo nasce privado: no claude.ai, compartilhe como "Qualquer pessoa com o link".
- A fila fica em `web/pedidos.json` e os links em `web/artefatos.json` (`sistema/links.py`);
  o Claude usa `scripts/publicar_pedidos.py` para gerar as páginas e registrar cada link publicado.

## Plano alimentar na página do paciente

- **Ficha do paciente → Plano alimentar:** envie o PDF do plano.
  - **PDF do App Naive** (os modelos de exportação conhecidos: em cartões, com horário; em lista, com "Opções de
    substituição"; em lista com "• Alimento" e trocas "Ou ..."; e a exportação completa, com tabela de opções,
    meta de água e "Lista de substituição" por grupos, que aparece na página com botões "N porções do Grupo X"):
    é lido sozinho (`scripts/plano_app_naive.py`) e vira a dieta interativa: refeições, opção principal e substituições,
    observações, calorias e macros por refeição e do dia, micronutrientes, receitas e lista de compras.
    Título e data vêm do próprio PDF, a não ser que você preencha.
  - **PDF feito por você** (ou marcando "mostrar página por página"): cada página vira uma imagem, do jeito que foi
    feito; no celular, tocar na página amplia.
  - **Vários planos** (ex.: dia de treino e dia de descanso): cada PDF enviado vira mais um plano; dê um título para
    diferenciar. Na página do paciente, cada plano é uma faixa (título, data, kcal) que abre ao tocar; com um plano só,
    ele já vem aberto. Para trocar um plano, remova o antigo e envie o novo.
- Quem já tem link entra sozinho na fila de Links ao enviar, trocar ou remover o plano.
- Fica na tabela `plano_alimentar` (`sql/04_plano.sql` e `05_varios_planos.sql`), com o PDF original; a conversão está em `scripts/plano.py`.

## Montar o plano no sistema

Ficha do paciente → **Plano alimentar** → **+ Montar plano no sistema** (planos montados ganham o botão **Editar**).
- **Refeições:** horário, nome e observação; busque o alimento (TACO ou seus) e informe a quantidade em gramas ou numa
  medida caseira (“+ nova medida…” guarda, por exemplo, “Colher de sopa cheia = 25 g” para os próximos planos).
- **Trocas:** “+ troca” em cada alimento; a quantidade vem com a mesma energia da opção principal e acompanha as
  mudanças dela (a não ser que você ajuste a troca à mão).
- **Meta energética** (painel ao lado): TMB por Harris-Benedict (adulto), Mifflin-St Jeor (IMC >= 30) ou FAO/OMS
  (acamado), escolhida sozinha pelo IMC da última avaliação e pela marcação de acamado (dá para trocar);
  GET = TMB x fator atividade; meta = GET + ajuste. O painel mostra kcal do plano x meta, macros em g, % e g/kg,
  fibra e sódio.
- **Salvar:** o plano vai para a aba Plano alimentar do paciente (refeições, trocas, kcal e macros por refeição,
  micronutrientes do dia, lista de compras) e o link entra na fila. Contas em `scripts/nutricao.py`.
- **Alimentos** (menu de cima): cadastre marcas e suplementos pelo rótulo (porção e valores; o sistema converte
  para 100 g).

## Tabela de alimentos (TACO)

A TACO 4ª edição (NEPA/UNICAMP: 597 alimentos em 15 grupos, nutrientes por 100 g) fica no banco, na tabela
`alimento` (`sql/06_alimentos.sql`), para montar e calcular planos. Os arquivos estão em `dados/taco/` (veja o
`LEIAME.md` de lá: origem e conferência com a planilha original); carregar ou recarregar:
`python scripts/carregar_taco.py` (a tarefa 3 já faz). Alimentos próprios (marcas, suplementos) entram na mesma
tabela com `fonte = 'proprio'`, e as medidas caseiras ficam em `medida_caseira`.

## WhatsApp

- **Ficha do paciente → Acompanhamento:** data da próxima consulta, telefone e "não quer receber mensagens".
- **Ficha do paciente → WhatsApp:** mensagens prontas (livre, link da evolução, lembrete de retorno).
- **Contatos** (o número no botão é quantos há hoje): retornos dos próximos dias e aniversários.
  "Abrir no WhatsApp" abre a conversa com o texto pronto; você confere e envia. Nada é enviado sozinho.
- **Configuração:** o texto de cada mensagem (fica em `sistema/config.json`) e quantos dias antes lembrar a consulta.

Tabela e campos: `sql/03_whatsapp.sql` (tabela `contato`; campos `retorno_em` e `whatsapp_bloqueado` em `paciente`);
os lembretes ficam em `sistema/contatos.py`. Para desfazer no banco: `sql/03_whatsapp_desfazer.sql`.

Backups: `_backup/antes_checkin_2026-11-03` (antes do WhatsApp) e `_backup/com_checkin_2026-11-03` (com o check-in
pelo Formulário Google, que foi testado e retirado). Cada um tem os arquivos e a cópia do banco (`app_naive.dump`).


## Próximo passo

- **Passo 3:** publicar a página no link do paciente (`web/artefatos.json`) pelo Claude.
