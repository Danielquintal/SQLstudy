/**
 * Check-in semanal dos pacientes: cria o Formulário Google e entrega as respostas ao sistema local.
 *
 * Como instalar (uma vez só; o passo a passo também está na tela Configuração do sistema):
 *  1. Em script.google.com, clique em "Novo projeto", apague o que vier escrito e cole este código. Salve.
 *  2. No menu de funções lá em cima escolha "criar" e clique em Executar. O Google pede autorização: permita.
 *     O registro de execução mostra o link do formulário e a CHAVE.
 *  3. Implantar > Nova implantação > tipo "App da Web". Executar como: Eu. Quem pode acessar: Qualquer pessoa.
 *     Copie a URL do app da Web.
 *  4. No sistema, em Configuração > Check-in, cole a URL e a chave e salve.
 *  5. (E-mail automático, opcional) Escolha a função "ativarEmails" e clique em Executar, autorizando o envio de e-mail.
 *     Todo dia por volta das 9h o script manda o pedido de check-in por e-mail a quem está na vez (a lista vem do sistema).
 *
 * Ao trocar este código por uma versão nova: cole por cima, salve e vá em Implantar > Gerenciar implantações >
 * lápis (editar) > Versão: "Nova versão" > Implantar. A URL continua a mesma.
 *
 * A chave é o que impede outra pessoa de ler as respostas pela URL: não a mostre a ninguém.
 * Pode mudar o texto das perguntas no formulário; o sistema reconhece cada uma pelo número interno, não pelo texto.
 */

// [campo no sistema, tipo, título, ajuda, obrigatória, opções]
const PERGUNTAS = [
  ['nome', 'texto', 'Seu nome completo', 'Já vem preenchido pelo link que você recebeu.', true],
  ['secao', 'secao', 'Peso e medidas', ''],
  ['peso_kg', 'texto', 'Peso hoje, em jejum (kg)', 'Ex.: 72,5. Deixe em branco se não se pesou.', false],
  ['cintura_cm', 'texto', 'Cintura (cm), se você mediu', 'Fita métrica na altura do umbigo. Ex.: 81', false],
  ['secao', 'secao', 'Plano alimentar', ''],
  ['adesao', 'escala', 'Quanto você conseguiu seguir o plano nesta semana?', '', true, ['Quase nada', 'Totalmente']],
  ['dificuldades', 'paragrafo', 'O que dificultou? (opcional)', 'Ex.: fim de semana, viagem, falta de tempo, fome à noite.', false],
  ['secao', 'secao', 'Bem-estar', ''],
  ['fome', 'escala', 'Como esteve sua fome?', '', true, ['Muita fome o tempo todo', 'Fome controlada']],
  ['sono', 'escala', 'Como foi seu sono?', '', true, ['Muito ruim', 'Muito bom']],
  ['energia', 'escala', 'Como esteve sua energia e disposição?', '', true, ['Muito baixa', 'Muito alta']],
  ['intestino', 'escolha', 'Como funcionou seu intestino?', '', true,
    ['Normal, todo dia', 'Preso (menos de uma vez por dia)', 'Solto ou com diarreia', 'Irregular']],
  ['agua', 'escolha', 'Quanta água você bebeu por dia, em média?', '', true,
    ['Menos de 1 litro', '1 a 2 litros', '2 a 3 litros', 'Mais de 3 litros']],
  ['secao', 'secao', 'Treino', ''],
  ['treinos', 'escolha', 'Quantos treinos você fez nesta semana?', '', true, ['0', '1', '2', '3', '4', '5', '6', '7 ou mais']],
  ['treino_sensacao', 'escala', 'Como você se sentiu nos treinos? (opcional)', '', false, ['Muito mal', 'Muito bem']],
  ['secao', 'secao', 'Para terminar', ''],
  ['comentario', 'paragrafo', 'Quer me contar mais alguma coisa? (opcional)', '', false],
];
const MARCA_NOME = 'NOME_DO_PACIENTE';   // o sistema troca pelo nome de cada paciente no link
const VERSAO = 2;                        // o sistema confere para saber se o código está atualizado

function criar() {
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('FORM_ID')) {
    Logger.log('O formulário já tinha sido criado.');
    mostrar();
    return;
  }
  const f = FormApp.create('Check-in semanal');
  f.setDescription('Leva uns 2 minutos e me ajuda a acompanhar você entre as consultas. Obrigado!');
  f.setCollectEmail(false);
  f.setAllowResponseEdits(false);
  f.setShowLinkToRespondAgain(false);
  f.setConfirmationMessage('Recebi seu check-in. Obrigado!');
  const campos = {};
  for (const [campo, tipo, titulo, ajuda, obrigatoria, opcoes] of PERGUNTAS) {
    let item;
    if (tipo === 'secao') { f.addSectionHeaderItem().setTitle(titulo); continue; }
    if (tipo === 'texto') item = f.addTextItem();
    if (tipo === 'paragrafo') item = f.addParagraphTextItem();
    if (tipo === 'escala') item = f.addScaleItem().setBounds(1, 5).setLabels(opcoes[0], opcoes[1]);
    if (tipo === 'escolha') item = f.addMultipleChoiceItem().setChoiceValues(opcoes);
    item.setTitle(titulo).setRequired(!!obrigatoria);
    if (ajuda) item.setHelpText(ajuda);
    campos[item.getId()] = campo;
  }
  props.setProperties({
    FORM_ID: f.getId(),
    CAMPOS: JSON.stringify(campos),
    CHAVE: Utilities.getUuid().replace(/-/g, ''),
  });
  mostrar();
}

function mostrar() {
  const props = PropertiesService.getScriptProperties();
  const f = FormApp.openById(props.getProperty('FORM_ID'));
  Logger.log('Formulário: ' + f.getPublishedUrl());
  Logger.log('CHAVE (cole no sistema): ' + props.getProperty('CHAVE'));
}

// o sistema chama esta URL: ?chave=...&acao=info devolve o link do formulário; ?chave=...&desde=... as respostas
function doGet(e) {
  const props = PropertiesService.getScriptProperties();
  const p = (e && e.parameter) || {};
  if (!props.getProperty('CHAVE') || p.chave !== props.getProperty('CHAVE')) return json({ erro: 'chave' });
  const f = FormApp.openById(props.getProperty('FORM_ID'));
  const campos = JSON.parse(props.getProperty('CAMPOS'));
  if (p.acao === 'info') {
    return json({ titulo: f.getTitle(), link: linkPreenchido(f, campos), marca: MARCA_NOME, versao: VERSAO,
                  respostas: f.getResponses().length, emails: estadoEmails() });
  }
  if (p.acao === 'emails') return json({ versao: VERSAO, emails: estadoEmails() });
  const desde = p.desde ? new Date(p.desde) : null;
  const lista = (desde && !isNaN(desde) ? f.getResponses(desde) : f.getResponses()).map(r => {
    const itens = {};
    for (const i of r.getItemResponses()) {
      const it = i.getItem();
      itens[campos[it.getId()] || it.getTitle()] = i.getResponse();
    }
    return { id: r.getId(), quando: r.getTimestamp().toISOString(), itens: itens };
  });
  return json({ respostas: lista });
}

function linkPreenchido(f, campos) {
  const idNome = Object.keys(campos).find(id => campos[id] === 'nome');
  const itemNome = f.getItemById(Number(idNome)).asTextItem();
  return f.createResponse().withItemResponse(itemNome.createResponse(MARCA_NOME)).toPrefilledUrl();
}

// ---------- e-mail automático ----------
// O sistema manda (POST) a lista de quem pode receber e o texto; o gatilho diário envia a quem está na vez.

function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return json({ erro: 'formato' }); }
  if (!props.getProperty('CHAVE') || d.chave !== props.getProperty('CHAVE')) return json({ erro: 'chave' });
  if (d.acao === 'pacientes') {
    props.setProperty('EMAIL_CFG', JSON.stringify(d.config || {}));
    const novos = {};
    for (const pac of d.lista || []) novos['P_' + pac.id] = JSON.stringify({ nome: pac.nome, email: pac.email });
    for (const k of props.getKeys()) if (k.indexOf('P_') === 0 && !(k in novos)) props.deleteProperty(k);
    props.setProperties(novos);
    return json({ ok: true, versao: VERSAO, pacientes: Object.keys(novos).length, emails: estadoEmails() });
  }
  return json({ erro: 'acao' });
}

function normalizar(s) {
  return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function enviarEmails() {
  const props = PropertiesService.getScriptProperties();
  const cfg = JSON.parse(props.getProperty('EMAIL_CFG') || '{}');
  if (!cfg.ativo) return;
  const f = FormApp.openById(props.getProperty('FORM_ID'));
  const campos = JSON.parse(props.getProperty('CAMPOS'));
  const idNome = Object.keys(campos).find(id => campos[id] === 'nome');
  const dia = 24 * 3600 * 1000, agora = Date.now(), intervalo = (Number(cfg.dias) || 7) * dia;
  // quem já respondeu nesta semana não recebe
  const respondeu = {};
  for (const r of f.getResponses(new Date(agora - intervalo))) {
    const it = r.getItemResponses().find(i => String(i.getItem().getId()) === idNome);
    if (it) respondeu[normalizar(it.getResponse())] = true;
  }
  const link = linkPreenchido(f, campos);
  const enviados = JSON.parse(props.getProperty('EMAIL_ENVIOS') || '{}');   // id do paciente -> último envio
  const log = JSON.parse(props.getProperty('EMAIL_LOG') || '[]');
  for (const k of props.getKeys()) {
    if (k.indexOf('P_') !== 0) continue;
    const id = k.slice(2), pac = JSON.parse(props.getProperty(k));
    if (respondeu[normalizar(pac.nome)] || (enviados[id] && agora - enviados[id] < intervalo - dia / 2)) continue;
    if (MailApp.getRemainingDailyQuota() < 1) break;
    const primeiro = pac.nome.trim().split(/\s+/)[0];
    const nomeFmt = primeiro.charAt(0).toUpperCase() + primeiro.slice(1).toLowerCase();
    const url = link.replace(MARCA_NOME, encodeURIComponent(pac.nome.trim()));
    const troca = t => String(t || '').split('{primeiro_nome}').join(nomeFmt).split('{nome}').join(pac.nome);
    const texto = troca(cfg.texto);
    const html = texto.split('\n').map(l => l ? l.replace(/&/g, '&amp;').replace(/</g, '&lt;') : '&nbsp;').join('<br>') +
      '<p style="margin:24px 0"><a href="' + url + '" style="background:#12434F;color:#fff;padding:12px 22px;' +
      'border-radius:8px;text-decoration:none;font-weight:600">Responder o check-in</a></p>' +
      '<p style="color:#5E7178;font-size:12px">Se o botão não abrir, copie este endereço: ' + url + '</p>';
    try {
      MailApp.sendEmail({ to: pac.email, subject: troca(cfg.assunto) || 'Check-in da semana', name: cfg.remetente || '',
                          body: texto + '\n\nResponda por este link: ' + url, htmlBody: html });
      enviados[id] = agora;
      log.unshift({ id: Number(id), quando: new Date(agora).toISOString() });
    } catch (err) {
      log.unshift({ id: Number(id), quando: new Date(agora).toISOString(), erro: String(err).slice(0, 120) });
    }
  }
  props.setProperty('EMAIL_ENVIOS', JSON.stringify(enviados));
  props.setProperty('EMAIL_LOG', JSON.stringify(log.slice(0, 80)));
  props.setProperty('EMAIL_ULTIMA', new Date(agora).toISOString());
}

function ativarEmails() {
  desativarEmails();
  ScriptApp.newTrigger('enviarEmails').timeBased().everyDays(1).atHour(9).create();
  Logger.log('E-mail automático ativado: todo dia por volta das 9h. Cota de hoje: ' + MailApp.getRemainingDailyQuota() + ' e-mails.');
}

function desativarEmails() {
  for (const t of ScriptApp.getProjectTriggers()) if (t.getHandlerFunction() === 'enviarEmails') ScriptApp.deleteTrigger(t);
}

function estadoEmails() {
  const props = PropertiesService.getScriptProperties();
  return {
    gatilho: ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'enviarEmails'),
    ultima: props.getProperty('EMAIL_ULTIMA'),
    envios: JSON.parse(props.getProperty('EMAIL_LOG') || '[]'),
  };
}

function json(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
