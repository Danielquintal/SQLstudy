/**
 * Check-in semanal dos pacientes: cria o Formulário Google e entrega as respostas ao sistema local.
 * Também envia, pela sua conta Google, os e-mails do check-in automático e as confirmações de consulta da Agenda,
 * coloca as consultas e os lembretes do sistema no seu Google Agenda (agenda principal), envia os lembretes dos
 * pacientes (Telegram, e-mail e convite no Google Agenda, de 10 em 10 minutos) e mantém o formulário do LEAF-Q
 * (rastreio de RED-S), criado pelo sistema com as mesmas perguntas da tela de rastreio.
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
const VERSAO = 10;                      // o sistema confere para saber se o código está atualizado
const TAG = 'sistemaConsulta';           // marca os eventos criados pelo sistema (não voltam como "outros compromissos")

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
  if (p.cod) return paginaConfirmacao(p);     // link "confirme sua presença" que o paciente abre (sem a chave)
  if (!props.getProperty('CHAVE') || p.chave !== props.getProperty('CHAVE')) return json({ erro: 'chave' });
  if (p.acao === 'confirmacoes') return json({ versao: VERSAO, respostas: respostasConfirmacao() });
  const f = FormApp.openById(props.getProperty('FORM_ID'));
  const campos = JSON.parse(props.getProperty('CAMPOS'));
  if (p.acao === 'info') {
    return json({ titulo: f.getTitle(), link: linkPreenchido(f, campos), marca: MARCA_NOME, versao: VERSAO,
                  respostas: f.getResponses().length, emails: estadoEmails(), leafq_link: linkLeafq() });
  }
  if (p.acao === 'emails') return json({ versao: VERSAO, emails: estadoEmails() });
  if (p.acao === 'leafq') {
    // respostas do formulário do LEAF-Q, com a chave de cada pergunta do sistema
    const id = props.getProperty('LEAFQ_ID');
    if (!id) return json({ versao: VERSAO, respostas: [] });
    const fq = FormApp.openById(id), cq = JSON.parse(props.getProperty('LEAFQ_CAMPOS'));
    const lista = fq.getResponses().map(r => {
      const itens = {};
      for (const i of r.getItemResponses()) itens[cq[i.getItem().getId()] || i.getItem().getTitle()] = i.getResponse();
      return { id: r.getId(), quando: r.getTimestamp().toISOString(), itens: itens };
    });
    return json({ versao: VERSAO, respostas: lista });
  }
  if (p.acao === 'eventos') {
    // seus outros compromissos no Google Agenda, para a agenda do sistema mostrar (os criados pelo sistema ficam de fora)
    const de = new Date(p.de), ate = new Date(p.ate);
    if (isNaN(de) || isNaN(ate)) return json({ erro: 'datas' });
    const eventos = CalendarApp.getDefaultCalendar().getEvents(de, ate)
      .filter(e => !e.getTag(TAG))
      .map(e => ({ titulo: e.getTitle(), inicio: e.getStartTime().toISOString(), fim: e.getEndTime().toISOString(),
                   dia_todo: e.isAllDayEvent() }));
    return json({ versao: VERSAO, eventos: eventos });
  }
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

// ---------- confirmação de presença pelo paciente ----------
// O sistema manda, na mensagem de confirmação, um link para esta URL com: cod = código da consulta (o Google
// reserva o nome "c"), s = assinatura
// (só o sistema, que tem a CHAVE, consegue gerar), n = primeiro nome, q = dia e hora, w = WhatsApp do nutricionista.
// O paciente toca em "Confirmo" ou "Preciso remarcar"; a resposta fica guardada aqui até o sistema buscar.

function assinatura(codigo) {
  const b = Utilities.computeHmacSha256Signature(String(codigo), PropertiesService.getScriptProperties().getProperty('CHAVE'));
  return b.map(x => ('0' + (x & 255).toString(16)).slice(-2)).join('').slice(0, 16);
}

function paginaConfirmacao(p) {
  const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const codigo = String(p.cod || '');
  const valido = /^[A-Za-z0-9]{16,40}$/.test(codigo) && p.s === assinatura(codigo);
  const num = String(p.w || '').replace(/\D/g, '');
  const zap = num ? '<p><a class="b sec" target="_top" href="https://wa.me/' + num + '">Falar comigo no WhatsApp</a></p>' : '';
  let corpo;
  if (!valido) {
    corpo = '<h1>Link inválido</h1><p>Este link de confirmação não está completo. Responda pela mensagem que você recebeu.</p>' + zap;
  } else if (p.r === 'sim' || p.r === 'remarcar') {
    PropertiesService.getScriptProperties().setProperty('CF_' + codigo,
      JSON.stringify({ r: p.r, em: new Date().toISOString() }));
    corpo = p.r === 'sim'
      ? '<h1>Presença confirmada ✓</h1><p>Obrigado, ' + esc(p.n) + '! Te espero ' + esc(p.q) + '.</p>'
      : '<h1>Tudo bem!</h1><p>Recebi o seu pedido para remarcar, ' + esc(p.n) + '. Vou falar com você para combinar um novo horário.</p>' + zap;
  } else {
    const base = ScriptApp.getService().getUrl() + '?cod=' + encodeURIComponent(codigo) + '&s=' + encodeURIComponent(p.s)
      + '&n=' + encodeURIComponent(p.n || '') + '&q=' + encodeURIComponent(p.q || '') + '&w=' + encodeURIComponent(num);
    corpo = '<h1>Olá, ' + esc(p.n) + '!</h1><p>Sua consulta está marcada para <b>' + esc(p.q) + '</b>.</p>'
      + '<p><a class="b" target="_top" href="' + esc(base + '&r=sim') + '">Confirmo minha presença</a></p>'
      + '<p><a class="b sec" target="_top" href="' + esc(base + '&r=remarcar') + '">Preciso remarcar</a></p>';
  }
  const html = '<style>body{font:17px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d2b2f;margin:0;background:#f2f5f4}'
    + '.c{max-width:440px;margin:32px auto;background:#fff;border:1px solid #dfe6e4;border-radius:16px;padding:24px 22px}'
    + 'h1{font-size:22px;margin:0 0 10px}small{color:#6b7b7f;letter-spacing:.1em;text-transform:uppercase;font-size:12px}'
    + '.b{display:block;text-align:center;background:#1A9E8F;color:#fff;text-decoration:none;font-weight:600;padding:14px;border-radius:12px}'
    + '.b.sec{background:#fff;color:#14444f;border:1px solid #c9d6d3}</style>'
    + '<div class="c"><small>Confirmação de consulta</small>' + corpo + '</div>';
  return HtmlService.createHtmlOutput(html).setTitle('Confirmação de consulta')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// respostas guardadas (e limpa as de mais de 120 dias)
function respostasConfirmacao() {
  const props = PropertiesService.getScriptProperties(), todas = props.getProperties(), saida = {};
  const limite = Date.now() - 120 * 86400000;
  for (const k in todas) {
    if (k.indexOf('CF_') !== 0) continue;
    try {
      const v = JSON.parse(todas[k]);
      if (new Date(v.em).getTime() < limite) props.deleteProperty(k); else saida[k.slice(3)] = v;
    } catch (err) { props.deleteProperty(k); }
  }
  return saida;
}

function linkLeafq() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('LEAFQ_ID');
  if (!id) return '';
  return linkPreenchido(FormApp.openById(id), JSON.parse(props.getProperty('LEAFQ_CAMPOS')));
}

function linkPreenchido(f, campos) {
  const idNome = Object.keys(campos).find(id => campos[id] === 'nome');
  const itemNome = f.getItemById(Number(idNome)).asTextItem();
  return f.createResponse().withItemResponse(itemNome.createResponse(MARCA_NOME)).toPrefilledUrl();
}

// ---------- e-mail automático ----------
// O sistema manda (POST) a lista de quem pode receber e o texto; o gatilho diário envia a quem está na vez.

// texto do e-mail -> HTML: protege os caracteres, mantém as quebras de linha e transforma a palavra "WhatsApp"
// num link que abre a conversa com o nutricionista (número vindo do sistema; sem número, fica só o texto)
function htmlTexto(texto, whats) {
  const num = String(whats || '').replace(/\D/g, '');
  return String(texto || '').split('\n').map(l => {
    if (!l) return '&nbsp;';
    l = l.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    // endereços (ex.: link de confirmação) viram links clicáveis
    l = l.replace(/https?:\/\/[^\s<]+/g, u => '<a href="' + u.replace(/"/g, '%22') + '" style="color:#1A9E8F;font-weight:600">' + u + '</a>');
    return num ? l.replace(/\bWhatsApp\b/g, '<a href="https://wa.me/' + num + '" style="color:#1A9E8F;font-weight:600">WhatsApp</a>') : l;
  }).join('<br>');
}

function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return json({ erro: 'formato' }); }
  if (!props.getProperty('CHAVE') || d.chave !== props.getProperty('CHAVE')) return json({ erro: 'chave' });
  if (d.acao === 'email') {
    // e-mail avulso do sistema (ex.: confirmação de consulta), com convite de calendário (.ics) se vier
    if (!d.para) return json({ erro: 'sem_email' });
    const opcoes = { to: d.para, subject: d.assunto || '', name: d.remetente || '', body: d.texto || '',
                     htmlBody: htmlTexto(d.texto, d.whatsapp) };
    if (d.ics) opcoes.attachments = [Utilities.newBlob(d.ics, 'text/calendar', 'consulta.ics')];
    try {
      MailApp.sendEmail(opcoes);
    } catch (err) {
      return json({ erro: 'envio', detalhe: String(err).slice(0, 200) });
    }
    return json({ ok: true, versao: VERSAO, cota: MailApp.getRemainingDailyQuota() });
  }
  if (d.acao === 'criar_leafq') {
    // cria (uma vez) o formulário do LEAF-Q com as perguntas que o sistema mandou
    if (!props.getProperty('LEAFQ_ID')) {
      const fq = FormApp.create('LEAF-Q – questionário de saúde da atleta');
      fq.setDescription('Questionário sobre lesões, função intestinal e ciclo menstrual (LEAF-Q). Leva uns 5 minutos. '
                        + 'Responda com sinceridade: as respostas ficam só com o seu nutricionista.');
      fq.setCollectEmail(false);
      fq.setAllowResponseEdits(false);
      fq.setConfirmationMessage('Recebi suas respostas. Obrigado!');
      const cq = {};
      const nome = fq.addTextItem().setTitle('Seu nome completo').setHelpText('Já vem preenchido pelo link que você recebeu.').setRequired(true);
      cq[nome.getId()] = 'nome';
      let secao = '';
      for (const q of d.perguntas || []) {
        if (q.secao !== secao) { fq.addSectionHeaderItem().setTitle(q.secao); secao = q.secao; }
        let item;
        if (q.tipo === 'texto') item = fq.addTextItem();
        else if (q.tipo === 'multipla') item = fq.addCheckboxItem().setChoiceValues(q.opcoes);
        else item = fq.addMultipleChoiceItem().setChoiceValues(q.opcoes);
        item.setTitle(q.titulo);
        cq[item.getId()] = q.chave;
      }
      props.setProperties({ LEAFQ_ID: fq.getId(), LEAFQ_CAMPOS: JSON.stringify(cq) });
    }
    return json({ ok: true, versao: VERSAO, link: linkLeafq(), marca: MARCA_NOME });
  }
  if (d.acao === 'evento') {
    // cria, atualiza ou apaga o evento da consulta no Google Agenda
    const cal = CalendarApp.getDefaultCalendar();
    let ev = null;
    if (d.evento) { try { ev = cal.getEventById(d.evento); } catch (err) { ev = null; } }
    if (d.excluir) {
      if (ev) ev.deleteEvent();
      return json({ ok: true, versao: VERSAO });
    }
    const ini = new Date(d.inicio), fim = new Date(d.fim);
    if (isNaN(ini) || isNaN(fim)) return json({ erro: 'datas' });
    try {
      if (ev) {
        ev.setTime(ini, fim);
        ev.setTitle(d.titulo || 'Consulta');
        ev.setLocation(d.local || '');
        ev.setDescription(d.descricao || '');
      } else {
        ev = cal.createEvent(d.titulo || 'Consulta', ini, fim, { location: d.local || '', description: d.descricao || '' });
        ev.setTag(TAG, String(d.consulta || ''));
      }
      if (d.aviso !== undefined && d.aviso !== null && d.aviso !== '') {
        // lembrete do sistema: aviso no celular com a antecedência escolhida (minutos)
        ev.removeAllReminders();
        ev.addPopupReminder(Math.max(0, Math.min(40320, Number(d.aviso) || 0)));
      }
      if (d.convidado && !ev.getGuestByEmail(d.convidado)) {
        ev.addGuest(d.convidado);   // o Google manda o convite ao paciente
      }
    } catch (err) {
      return json({ erro: 'agenda', detalhe: String(err).slice(0, 200) });
    }
    return json({ ok: true, versao: VERSAO, evento: ev.getId() });
  }
  if (d.acao === 'lembretes' || d.acao === 'telegram') {
    // lembretes dos pacientes: recebe a lista (acao lembretes) ou só lê o Telegram e devolve o estado (acao telegram)
    const trava = LockService.getScriptLock();
    if (!trava.tryLock(25000)) return json({ erro: 'ocupado' });
    try {
      let erros = [];
      if (d.acao === 'lembretes') erros = lembretesReceber(d);
      else if (d.telegram_token !== undefined) props.setProperty('TG_TOKEN', d.telegram_token || '');
      lerTelegram();
      if (d.desvincular) {
        const links = JSON.parse(props.getProperty('TG_LINKS') || '{}');
        if (links[d.desvincular]) {
          telegram('sendMessage', { chat_id: links[d.desvincular].chat, text: 'Seu nutricionista desligou os lembretes por aqui.' });
          delete links[d.desvincular];
          props.setProperty('TG_LINKS', JSON.stringify(links));
        }
      }
      return json(Object.assign({ ok: true, versao: VERSAO, erros_google: erros }, estadoLembretes()));
    } finally {
      trava.releaseLock();
    }
  }
  if (d.acao === 'pacientes') {
    props.setProperty('EMAIL_CFG', JSON.stringify(d.config || {}));
    const novos = {};
    for (const pac of d.lista || []) novos['P_' + pac.id] = JSON.stringify({ nome: pac.nome, email: pac.email, dia: pac.dia });
    for (const k of props.getKeys()) if (k.indexOf('P_') === 0 && !(k in novos)) props.deleteProperty(k);
    props.setProperties(novos);
    return json({ ok: true, versao: VERSAO, pacientes: Object.keys(novos).length, emails: estadoEmails() });
  }
  return json({ erro: 'acao' });
}

// ---------- lembretes para os pacientes (Telegram, e-mail e convite no Google Agenda) ----------
// O sistema manda (POST acao "lembretes") a lista com as próximas vezes de cada lembrete; o gatilho "rodarLembretes",
// a cada 10 minutos, envia o que chegou na hora, mesmo com o computador desligado. O robô do Telegram é criado por
// você no @BotFather; o paciente toca no link com o código dele e passa a receber.

const LEMB_JANELA = 6 * 3600 * 1000;   // vez atrasada mais de 6 h (script parado) não é mais enviada

function lembretesReceber(d) {
  const props = PropertiesService.getScriptProperties();
  if (d.telegram_token !== undefined) props.setProperty('TG_TOKEN', d.telegram_token || '');
  props.setProperty('LP_CFG', JSON.stringify({ remetente: d.remetente || '', assunto: d.assunto || 'Lembrete', whatsapp: d.whatsapp || '' }));
  const novos = {}, google = {};
  for (const it of d.itens || []) {
    novos['LI_' + it.id] = JSON.stringify({ id: it.id, texto: it.texto, telegram: it.telegram || '', email: it.email || '',
                                             ocorrencias: it.ocorrencias || [] });
    if (it.google) google[it.id] = it.google;
  }
  for (const k of props.getKeys()) if (k.indexOf('LI_') === 0 && !(k in novos)) props.deleteProperty(k);   // LI_ = um lembrete
  props.setProperties(novos);
  const erros = lembretesGoogle(google);
  // o gatilho de 10 em 10 minutos (cria uma vez; sem lembretes, desliga)
  const tem = ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'rodarLembretes');
  if (Object.keys(novos).length && !tem) ScriptApp.newTrigger('rodarLembretes').timeBased().everyMinutes(10).create();
  if (!Object.keys(novos).length && tem) {
    for (const t of ScriptApp.getProjectTriggers()) if (t.getHandlerFunction() === 'rodarLembretes') ScriptApp.deleteTrigger(t);
  }
  return erros;
}

function calendarioLembretes() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('LEMB_CAL');
  let cal = id ? CalendarApp.getCalendarById(id) : null;
  if (!cal) {
    cal = CalendarApp.createCalendar('Lembretes dos pacientes', { summary: 'Criada pelo sistema: os convites de lembrete dos pacientes saem daqui.' });
    props.setProperty('LEMB_CAL', cal.getId());
  }
  return cal;
}

function lembretesGoogle(google) {
  // convite no Google Agenda do paciente: um evento (ou uma série que repete) com o paciente como convidado
  const props = PropertiesService.getScriptProperties(), erros = [];
  const apagar = g => {
    try {
      const cal = calendarioLembretes();
      if (g.unico) { const ev = cal.getEventById(g.serie); if (ev) ev.deleteEvent(); }
      else { const s = cal.getEventSeriesById(g.serie); if (s) s.deleteEventSeries(); }
    } catch (err) {}
  };
  for (const k of props.getKeys()) {
    if (k.indexOf('LG_') !== 0) continue;
    const id = k.slice(3), atual = JSON.parse(props.getProperty(k));
    if (!google[id] || google[id].hash !== atual.hash) { apagar(atual); props.deleteProperty(k); }
  }
  for (const id of Object.keys(google)) {
    const g = google[id];
    if (props.getProperty('LG_' + id)) continue;   // já está no Google, sem mudança
    try {
      const cal = calendarioLembretes();
      const ini = new Date(g.inicio), fim = new Date(g.fim);
      const op = { description: g.descricao || '', guests: g.email, sendInvites: true };
      let ev, unico = !g.repetir;
      if (unico) {
        ev = cal.createEvent(g.titulo, ini, fim, op);
      } else {
        let r = CalendarApp.newRecurrence();
        r = g.repetir === 'diario' ? r.addDailyRule() : g.repetir === 'mensal' ? r.addMonthlyRule()
          : r.addWeeklyRule().interval(g.repetir === 'quinzenal' ? 2 : 1);
        if (g.ate) r = r.until(new Date(g.ate));
        ev = cal.createEventSeries(g.titulo, ini, fim, r, op);
      }
      ev.removeAllReminders();
      props.setProperty('LG_' + id, JSON.stringify({ serie: ev.getId(), hash: g.hash, unico: unico }));
    } catch (err) {
      erros.push({ id: Number(id), erro: String(err).slice(0, 160) });
    }
  }
  return erros;
}

function telegram(metodo, corpo) {
  const token = PropertiesService.getScriptProperties().getProperty('TG_TOKEN');
  if (!token) return { ok: false, description: 'sem robô' };
  const r = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/' + metodo,
    { method: 'post', contentType: 'application/json', payload: JSON.stringify(corpo || {}), muteHttpExceptions: true });
  try { return JSON.parse(r.getContentText()); } catch (err) { return { ok: false, description: 'resposta ' + r.getResponseCode() }; }
}

function lerTelegram() {
  // mensagens que chegaram ao robô: "/start CODIGO" vincula o paciente, "/parar" desliga
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('TG_TOKEN')) return {};
  const links = JSON.parse(props.getProperty('TG_LINKS') || '{}');
  const r = telegram('getUpdates', { offset: Number(props.getProperty('TG_OFFSET') || 0), timeout: 0, allowed_updates: ['message'] });
  if (!r.ok) return links;
  for (const u of r.result) {
    props.setProperty('TG_OFFSET', String(u.update_id + 1));
    const m = u.message;
    if (!m || !m.chat || !m.text) continue;
    const chat = String(m.chat.id), texto = m.text.trim();
    let resposta;
    if (texto.indexOf('/start') === 0) {
      const codigo = texto.slice(6).trim();
      if (codigo && /^[\w-]{6,64}$/.test(codigo)) {
        links[codigo] = { chat: chat, em: new Date().toISOString(), nome: m.chat.first_name || '' };
        resposta = 'Pronto! A partir de agora você recebe aqui os lembretes do seu nutricionista. Para parar, envie /parar.';
      } else {
        resposta = 'Para receber os lembretes, use o link que o seu nutricionista enviou.';
      }
    } else if (/^\/(parar|stop|sair)/i.test(texto)) {
      for (const c of Object.keys(links)) if (links[c].chat === chat) links[c].parou = new Date().toISOString();
      resposta = 'Tudo bem, você não vai mais receber lembretes por aqui. Para voltar, toque de novo no link do seu nutricionista.';
    } else {
      resposta = 'Este canal só envia lembretes. Para falar com o seu nutricionista, use o WhatsApp.';
    }
    telegram('sendMessage', { chat_id: chat, text: resposta });
  }
  props.setProperty('TG_LINKS', JSON.stringify(links));
  return links;
}

function rodarLembretes() {
  const trava = LockService.getScriptLock();
  if (!trava.tryLock(20000)) return;
  try {
    const props = PropertiesService.getScriptProperties();
    const links = lerTelegram();
    const parados = {};
    for (const c of Object.keys(links)) if (links[c].parou) parados[links[c].chat] = true;
    const cfg = JSON.parse(props.getProperty('LP_CFG') || '{}');
    const env = JSON.parse(props.getProperty('LP_ENV') || '{}');   // id -> última vez enviada
    const log = JSON.parse(props.getProperty('LP_LOG') || '[]');
    const agora = Date.now();
    for (const k of props.getKeys()) {
      if (k.indexOf('LI_') !== 0) continue;
      const it = JSON.parse(props.getProperty(k));
      const ja = env[it.id] ? new Date(env[it.id]).getTime() : 0;
      const vez = it.ocorrencias.filter(o => { const t = new Date(o).getTime(); return t <= agora && t > agora - LEMB_JANELA && t > ja; }).pop();
      if (!vez) continue;
      env[it.id] = vez;
      if (it.telegram) {
        if (parados[it.telegram]) {
          log.unshift({ id: it.id, vez: vez, canal: 'telegram', erro: 'o paciente pediu para parar' });
        } else {
          const r = telegram('sendMessage', { chat_id: it.telegram, text: it.texto });
          log.unshift({ id: it.id, vez: vez, canal: 'telegram', erro: r.ok ? '' : String(r.description || 'falhou').slice(0, 120) });
        }
      }
      if (it.email) {
        try {
          if (MailApp.getRemainingDailyQuota() < 1) throw new Error('acabou a cota de e-mails de hoje');
          MailApp.sendEmail({ to: it.email, subject: cfg.assunto || 'Lembrete', name: cfg.remetente || '', body: it.texto,
            htmlBody: htmlTexto(it.texto, cfg.whatsapp) });
          log.unshift({ id: it.id, vez: vez, canal: 'email', erro: '' });
        } catch (err) {
          log.unshift({ id: it.id, vez: vez, canal: 'email', erro: String(err).slice(0, 120) });
        }
      }
    }
    props.setProperty('LP_ENV', JSON.stringify(env));
    props.setProperty('LP_LOG', JSON.stringify(log.slice(0, 300)));
    props.setProperty('LP_ULTIMA', new Date(agora).toISOString());
  } finally {
    trava.releaseLock();
  }
}

function estadoLembretes() {
  const props = PropertiesService.getScriptProperties();
  return { gatilho: ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'rodarLembretes'),
           ultima: props.getProperty('LP_ULTIMA'), log: JSON.parse(props.getProperty('LP_LOG') || '[]'),
           telegram: JSON.parse(props.getProperty('TG_LINKS') || '{}') };
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
  // dia da semana de hoje no fuso do script: 0 = domingo ... 6 = sábado
  const hojeSemana = Number(Utilities.formatDate(new Date(agora), Session.getScriptTimeZone(), 'u')) % 7;
  for (const k of props.getKeys()) {
    if (k.indexOf('P_') !== 0) continue;
    const id = k.slice(2), pac = JSON.parse(props.getProperty(k));
    if (pac.dia !== null && pac.dia !== undefined && pac.dia !== '' && Number(pac.dia) !== hojeSemana) continue;   // dia escolhido na ficha
    if (respondeu[normalizar(pac.nome)] || (enviados[id] && agora - enviados[id] < intervalo - dia / 2)) continue;
    if (MailApp.getRemainingDailyQuota() < 1) break;
    const primeiro = pac.nome.trim().split(/\s+/)[0];
    const nomeFmt = primeiro.charAt(0).toUpperCase() + primeiro.slice(1).toLowerCase();
    const url = link.replace(MARCA_NOME, encodeURIComponent(pac.nome.trim()));
    const troca = t => String(t || '').split('{primeiro_nome}').join(nomeFmt).split('{nome}').join(pac.nome);
    const texto = troca(cfg.texto);
    const html = htmlTexto(texto, cfg.whatsapp) +
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
