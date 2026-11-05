/**
 * Time Exemplo · Nutrição — lembretes no Telegram e no Google Agenda.
 *
 * Instalar: na planilha, Extensões › Apps Script, apague o que estiver lá, cole este arquivo e salve.
 * Depois, na planilha: menu 🏈 Time Exemplo › 1. Configurar Telegram e › 2. Ativar lembretes.
 *
 * O que faz (rodando no Google, mesmo com o computador desligado):
 *  - Cada consulta da aba Consultas vira um evento no seu Google Agenda, com aviso 1 dia e 1 hora antes.
 *    Cancelada ou Remarcada: o evento é apagado.
 *  - Telegram (só para você): 1 dia antes · 1 hora antes · resumo às 7h · depois da consulta, lembrete de
 *    marcar Realizada e lançar a avaliação · toda segunda às 8h, atletas sem consulta e retornos atrasados.
 *
 * Não lê mensagens do robô (não usa getUpdates): o mesmo robô pode ser usado por outros sistemas.
 */

var ABA_ATLETAS = 'Atletas', ABA_CONSULTAS = 'Consultas', ABA_AVALIACOES = 'Avaliações';
var ATIVAS = ['Agendada', 'Confirmada'];
var SEM_EVENTO = ['Cancelada', 'Remarcada'];
var JANELA_MIN = 20;          // o gatilho roda a cada 15 min; janela com folga
var MAX_ATRASO_POS_H = 72;    // não cobra avaliação de consulta com mais de 3 dias

// ------------------------------------------------------------------ menu

function onOpen() {
  SpreadsheetApp.getUi().createMenu('🏈 Time Exemplo')
    .addItem('1. Configurar Telegram', 'configurarTelegram')
    .addItem('2. Ativar lembretes automáticos', 'ativarLembretes')
    .addItem('3. Preparar planilha para vários atendimentos', 'prepararAtendimentos')
    .addItem('4. Criar formulário de atendimento (celular)', 'criarFormulario')
    .addSeparator()
    .addItem('Ver histórico do atleta', 'abrirHistorico')
    .addItem('Criar dados de teste', 'criarDadosTeste')
    .addItem('Apagar dados de teste', 'apagarDadosTeste')
    .addItem('Sincronizar Google Agenda agora', 'sincronizarAgenda')
    .addItem('Enviar o resumo de hoje agora', 'resumoManha')
    .addItem('Enviar o resumo semanal agora', 'resumoSemanal')
    .addItem('Mandar mensagem de teste', 'teste')
    .addSeparator()
    .addItem('Desativar lembretes', 'desativarLembretes')
    .addToUi();
}

function configurarTelegram() {
  var ui = SpreadsheetApp.getUi(), props = PropertiesService.getScriptProperties();
  var r = ui.prompt('Telegram (1 de 2): token do robô',
    'Cole o token do seu robô (crie um no @BotFather; o token está em /mybots › API Token). Parece com 1234567890:AAH...', ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  var token = r.getResponseText().trim();
  var me = JSON.parse(UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/getMe', {muteHttpExceptions: true}).getContentText());
  if (!me.ok) { ui.alert('O Telegram não aceitou esse token. Confira e tente de novo.'); return; }
  var r2 = ui.prompt('Telegram (2 de 2): o seu número de chat',
    'No Telegram: (a) abra @' + me.result.username + ' e mande qualquer mensagem (ex.: oi), pra ele poder te escrever;\n' +
    '(b) abra @userinfobot e mande /start: ele responde com o seu "Id" (só números). Cole aqui:', ui.ButtonSet.OK_CANCEL);
  if (r2.getSelectedButton() !== ui.Button.OK) return;
  var chat = r2.getResponseText().replace(/[^\d-]/g, '');
  props.setProperties({TG_TOKEN: token, TG_CHAT: chat});
  var ok = telegram('🏈 <b>Time Exemplo · Nutrição</b>\nPronto! Os lembretes das consultas vão chegar aqui.');
  ui.alert(ok ? 'Mensagem de teste enviada. Agora use "2. Ativar lembretes automáticos".'
              : 'Não consegui mandar a mensagem. Confira se você mandou "oi" para o robô e se o Id está certo.');
}

function ativarLembretes() {
  desativarLembretes(true);
  var ss = SpreadsheetApp.getActive();
  ScriptApp.newTrigger('verificar').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('resumoManha').timeBased().everyDays(1).atHour(7).nearMinute(0).create();
  ScriptApp.newTrigger('resumoSemanal').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
  ScriptApp.newTrigger('aoEditar').forSpreadsheet(ss).onEdit().create();
  var formId = PropertiesService.getScriptProperties().getProperty('FORM_ID');
  if (formId) { try { ScriptApp.newTrigger('aoEnviarFormulario').forForm(formId).onFormSubmit().create(); } catch (e) {} }
  sincronizarAgenda();
  SpreadsheetApp.getUi().alert('Lembretes ativados: verificação a cada 15 min, resumo às 7h e resumo semanal na segunda às 8h. ' +
    'Fuso: ' + ss.getSpreadsheetTimeZone() + ' (Arquivo › Configurações, se precisar mudar).');
}

function desativarLembretes(silencioso) {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  if (silencioso !== true) SpreadsheetApp.getUi().alert('Lembretes desativados.');
}

function teste() {
  var ok = telegram('🏈 Teste do Time Exemplo · ' + fmt(new Date(), "dd/MM 'às' HH:mm"));
  SpreadsheetApp.getUi().alert(ok ? 'Enviado.' : 'Não enviou: use "1. Configurar Telegram".');
}

// ------------------------------------------------------------------ leitura da planilha

function tabela(nome) {
  var sh = SpreadsheetApp.getActive().getSheetByName(nome);
  if (!sh) throw new Error('Aba "' + nome + '" não encontrada.');
  var v = sh.getDataRange().getValues(), cab = v[0].map(function (c) { return String(c).trim(); });
  var linhas = [];
  for (var i = 1; i < v.length; i++) {
    var o = {_linha: i + 1};
    cab.forEach(function (c, j) { o[c] = v[i][j]; });
    linhas.push(o);
  }
  return {sh: sh, cab: cab, linhas: linhas, col: function (c) { return cab.indexOf(c) + 1; }};
}

function atletasPorNome() {
  var m = {};
  tabela(ABA_ATLETAS).linhas.forEach(function (a) { if (a['Atleta']) m[String(a['Atleta']).trim()] = a; });
  return m;
}

function posicoes(a) {
  if (!a) return '';
  return [a['Posição 1'], a['Posição 2'], a['Posição 3']].filter(String).join('/');
}

function inicio(c) {
  var d = c['Data'];
  if (!(d instanceof Date)) return null;
  var h = c['Hora'], hh = 0, mm = 0;
  if (h instanceof Date) { hh = h.getHours(); mm = h.getMinutes(); }
  else if (h) { var p = String(h).match(/(\d{1,2})\D?(\d{2})?/); if (p) { hh = +p[1]; mm = +(p[2] || 0); } }
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), hh, mm);
}

function fim(c, ini) { return new Date(ini.getTime() + (Number(c['Duração (min)']) || 60) * 60000); }

function fmt(d, padrao) { return Utilities.formatDate(d, SpreadsheetApp.getActive().getSpreadsheetTimeZone(), padrao); }

function mesmoDia(a, b) { return fmt(a, 'yyyyMMdd') === fmt(b, 'yyyyMMdd'); }

function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ------------------------------------------------------------------ Google Agenda

function agenda() {
  var id = PropertiesService.getScriptProperties().getProperty('AGENDA_ID');
  return (id && CalendarApp.getCalendarById(id)) || CalendarApp.getDefaultCalendar();
}

function sincronizarAgenda() {
  numerarAtendimentos();
  atualizarListaDoFormulario();
  var t = tabela(ABA_CONSULTAS), cal = agenda(), atl = atletasPorNome();
  var cEv = t.col('ID do evento (Google)'), cId = t.col('ID');
  var proximoId = 1 + Math.max.apply(null, [0].concat(t.linhas.map(function (c) { return Number(c['ID']) || 0; })));
  t.linhas.forEach(function (c) {
    if (!c['Atleta']) return;
    if (!c['ID'] && cId) { t.sh.getRange(c._linha, cId).setValue(proximoId++); }
    var ini = inicio(c), evId = String(c['ID do evento (Google)'] || ''), ev = null;
    if (evId) { try { ev = cal.getEventById(evId); } catch (e) { ev = null; } }
    if (!ini || SEM_EVENTO.indexOf(c['Status']) >= 0) {
      if (ev) ev.deleteEvent();
      if (evId) t.sh.getRange(c._linha, cEv).setValue('');
      return;
    }
    var a = atl[String(c['Atleta']).trim()], pos = posicoes(a);
    var titulo = '🏈 ' + (c['Tipo'] || 'Consulta') + ' · ' + c['Atleta'] + (pos ? ' (' + pos + ')' : '');
    var desc = ['Time Exemplo · Nutrição', 'Status: ' + (c['Status'] || 'Agendada'),
                c['Modalidade'] ? 'Modalidade: ' + c['Modalidade'] : '', c['Link da consulta'] ? 'Link: ' + c['Link da consulta'] : '',
                c['Objetivo / queixa'] ? 'Objetivo: ' + c['Objetivo / queixa'] : ''].filter(String).join('\n');
    var f = fim(c, ini), local = c['Link da consulta'] || '';
    if (!ev) {
      ev = cal.createEvent(titulo, ini, f, {description: desc, location: local});
      t.sh.getRange(c._linha, cEv).setValue(ev.getId());
    } else {
      if (ev.getTitle() !== titulo) ev.setTitle(titulo);
      if (ev.getStartTime().getTime() !== ini.getTime() || ev.getEndTime().getTime() !== f.getTime()) ev.setTime(ini, f);
      if (ev.getDescription() !== desc) ev.setDescription(desc);
      if (ev.getLocation() !== local) ev.setLocation(local);
    }
    var lem = ev.getPopupReminders();
    if (lem.length !== 2 || lem.indexOf(1440) < 0 || lem.indexOf(60) < 0) {
      ev.removeAllReminders(); ev.addPopupReminder(1440); ev.addPopupReminder(60);
    }
  });
}

function aoEditar(e) {
  if (!e || !e.range) return;
  var aba = e.range.getSheet().getName();
  if (aba === ABA_HISTORICO) { if (e.range.getA1Notation() === 'B3') preencherHistorico(); return; }
  if (aba !== ABA_CONSULTAS && aba !== ABA_AVALIACOES) return;
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return;
  try { if (aba === ABA_CONSULTAS) sincronizarAgenda(); preencherHistorico(); } finally { lock.releaseLock(); }
}

// ------------------------------------------------------------------ Telegram

function telegram(texto) {
  var p = PropertiesService.getScriptProperties(), token = p.getProperty('TG_TOKEN'), chat = p.getProperty('TG_CHAT');
  if (!token || !chat) return false;
  var r = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
    method: 'post', muteHttpExceptions: true,
    payload: {chat_id: chat, text: texto, parse_mode: 'HTML', disable_web_page_preview: 'true'}});
  return r.getResponseCode() === 200;
}

function linhaConsulta(c, atl, comData) {
  var ini = inicio(c), a = atl[String(c['Atleta']).trim()], pos = posicoes(a);
  return '• <b>' + fmt(ini, comData ? "dd/MM HH:mm" : 'HH:mm') + '</b> ' + esc(c['Atleta']) + (pos ? ' (' + esc(pos) + ')' : '') +
         ' · ' + esc(c['Tipo'] || 'Consulta') + (c['Status'] === 'Agendada' ? ' · <i>não confirmada</i>' : '') +
         (c['Link da consulta'] ? '\n   ' + esc(c['Link da consulta']) : '');
}

function avaliacaoNoDia(atleta, dia) {
  return tabela(ABA_AVALIACOES).linhas.some(function (v) {
    return String(v['Atleta']).trim() === atleta && v['Data'] instanceof Date && mesmoDia(v['Data'], dia);
  });
}

/** roda a cada 15 min: agenda + avisos de 1 dia, 1 hora e pós-consulta */
function verificar() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    sincronizarAgenda();
    var t = tabela(ABA_CONSULTAS), atl = atletasPorNome(), agora = new Date(), cAv = t.col('Avisos enviados');
    t.linhas.forEach(function (c) {
      if (!c['Atleta']) return;
      var ini = inicio(c); if (!ini) return;
      var feitos = String(c['Avisos enviados'] || ''), novos = [], min = (ini - agora) / 60000;
      var ativa = ATIVAS.indexOf(c['Status'] || 'Agendada') >= 0;
      if (ativa && feitos.indexOf('D1') < 0 && min <= 24 * 60 && min > 2 * 60) {
        var quando = mesmoDia(ini, agora) ? 'Hoje' : 'Amanhã';
        if (telegram('📅 <b>' + quando + '</b>\n' + linhaConsulta(c, atl, true) +
                     (c['Status'] === 'Confirmada' ? '' : '\nConfirme com o atleta (ainda está "Agendada").'))) novos.push('D1');
      }
      if (ativa && feitos.indexOf('H1') < 0 && min <= 60 + JANELA_MIN && min > -10) {
        if (telegram('⏰ <b>Daqui a pouco</b>\n' + linhaConsulta(c, atl, false))) novos.push('H1');
        if (feitos.indexOf('D1') < 0) novos.push('D1');
      }
      var depois = (agora - fim(c, ini)) / 3600000;
      if (feitos.indexOf('POS') < 0 && depois >= 1 && ['Cancelada', 'Remarcada', 'Faltou'].indexOf(c['Status']) < 0) {
        if (depois > MAX_ATRASO_POS_H) novos.push('POS');
        else {
          var falta = [];
          if (c['Status'] !== 'Realizada') falta.push('marcar o status (Realizada ou Faltou)');
          if (!avaliacaoNoDia(String(c['Atleta']).trim(), ini)) falta.push('lançar a avaliação na aba Avaliações');
          if (!c['Resumo e condutas']) falta.push('escrever o resumo e as condutas');
          if (!c['Próximo retorno']) falta.push('definir o próximo retorno');
          if (!falta.length || telegram('📝 <b>Consulta de ' + esc(c['Atleta']) + '</b> (' + fmt(ini, 'dd/MM HH:mm') + ')\nFalta:\n– ' + falta.join('\n– '))) novos.push('POS');
        }
      }
      if (novos.length && cAv) t.sh.getRange(c._linha, cAv).setValue((feitos ? feitos + ',' : '') + novos.join(','));
    });
  } finally { lock.releaseLock(); }
}

/** todo dia às 7h */
function resumoManha() {
  var t = tabela(ABA_CONSULTAS), atl = atletasPorNome(), hoje = new Date();
  var doDia = t.linhas.filter(function (c) {
    var i = inicio(c); return c['Atleta'] && i && mesmoDia(i, hoje) && ATIVAS.indexOf(c['Status'] || 'Agendada') >= 0;
  }).sort(function (a, b) { return inicio(a) - inicio(b); });
  var txt = '☀️ <b>Bom dia! Time Exemplo · ' + fmt(hoje, 'dd/MM') + '</b>\n';
  if (!doDia.length) txt += 'Nenhuma consulta hoje.';
  else {
    txt += doDia.length + (doDia.length === 1 ? ' consulta hoje:\n' : ' consultas hoje:\n') +
           doDia.map(function (c) { return linhaConsulta(c, atl, false); }).join('\n');
    var nc = doDia.filter(function (c) { return (c['Status'] || 'Agendada') === 'Agendada'; }).length;
    if (nc) txt += '\n\n⚠️ ' + nc + ' ainda não confirmada' + (nc > 1 ? 's' : '') + '.';
  }
  telegram(txt);
}

/** toda segunda às 8h */
function resumoSemanal() {
  var cons = tabela(ABA_CONSULTAS).linhas.filter(function (c) { return c['Atleta']; });
  var atletas = tabela(ABA_ATLETAS).linhas.filter(function (a) { return a['Atleta'] && a['Status'] !== 'Inativo'; });
  var agora = new Date(), semConsulta = [], atrasados = [];
  atletas.forEach(function (a) {
    var nome = String(a['Atleta']).trim();
    var dele = cons.filter(function (c) { return String(c['Atleta']).trim() === nome; });
    var futura = dele.some(function (c) { var i = inicio(c); return i && i > agora && ATIVAS.indexOf(c['Status'] || 'Agendada') >= 0; });
    var feita = dele.filter(function (c) { return c['Status'] === 'Realizada'; });
    if (!feita.length && !futura) { semConsulta.push(nome + ' (' + posicoes(a) + ')'); return; }
    var retornos = feita.map(function (c) { return c['Próximo retorno']; }).filter(function (d) { return d instanceof Date; });
    if (retornos.length && !futura) {
      var r = new Date(Math.max.apply(null, retornos));
      if (r < agora) atrasados.push(nome + ' · retorno era ' + fmt(r, 'dd/MM'));
    }
  });
  var txt = '📊 <b>Resumo semanal · Time Exemplo</b>\n' + atletas.length + ' atletas ativos.\n\n';
  txt += semConsulta.length ? '🔴 <b>Sem consulta feita nem marcada (' + semConsulta.length + ')</b>\n' + semConsulta.map(esc).join('\n') + '\n\n'
                            : '✅ Todos já têm consulta marcada ou feita.\n\n';
  txt += atrasados.length ? '🟡 <b>Retorno atrasado (' + atrasados.length + ')</b>\n' + atrasados.map(esc).join('\n')
                          : '✅ Nenhum retorno atrasado.';
  telegram(txt.length > 3900 ? txt.slice(0, 3900) + '\n…' : txt);
}

// ------------------------------------------------------------------ vários atendimentos por atleta

var COL_NUMERO = 'Nº do atendimento';
var CAMPOS_CLINICOS = ['Hábitos / recordatório', 'Plano entregue', 'Suplementação prescrita', 'Adesão (0-10)', 'Sintomas / observações'];
var ABA_HISTORICO = 'Histórico do atleta';
var CAMPOS_AVALIACAO = ['Peso (kg)', 'Altura (cm)', 'Dobra tríceps (mm)', 'Dobra subescapular (mm)', 'Dobra peitoral (mm)',
  'Dobra axilar média (mm)', 'Dobra suprailíaca (mm)', 'Dobra abdominal (mm)', 'Dobra coxa medial (mm)',
  'Circ. braço relaxado (cm)', 'Circ. braço contraído (cm)', 'Circ. cintura (cm)', 'Circ. coxa medial (cm)',
  'Massa muscular (kg)', '% água corporal'];

function letra(n) { var s = ''; while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); } return s; }

function inserirColuna(sh, nome, depoisDe) {
  var cab = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(String);
  if (cab.indexOf(nome) >= 0) return false;
  var ref = cab.indexOf(depoisDe) + 1 || sh.getLastColumn();
  sh.insertColumnAfter(ref);
  sh.getRange(1, ref).copyTo(sh.getRange(1, ref + 1), {formatOnly: true});
  sh.getRange(1, ref + 1).setValue(nome);
  // a coluna nova herda a validação da vizinha (ex.: lista de atletas): limpa
  sh.getRange(2, ref + 1, sh.getMaxRows() - 1, 1).clearDataValidations();
  return true;
}

/** menu 3: colunas novas, numeração e aba de histórico (pode rodar mais de uma vez) */
function prepararAtendimentos() {
  var sh = SpreadsheetApp.getActive().getSheetByName(ABA_CONSULTAS), novas = 0;
  if (inserirColuna(sh, COL_NUMERO, 'Atleta')) { novas++; sh.setColumnWidth(tabela(ABA_CONSULTAS).col(COL_NUMERO), 90); }
  var antes = 'Resumo e condutas';
  CAMPOS_CLINICOS.forEach(function (c) { if (inserirColuna(sh, c, antes)) novas++; antes = c; });
  var t = tabela(ABA_CONSULTAS), cAd = t.col('Adesão (0-10)'), cNum = t.col(COL_NUMERO);
  sh.getRange(2, cNum, sh.getMaxRows() - 1, 1).clearDataValidations().setNumberFormat('0').setHorizontalAlignment('center');
  CAMPOS_CLINICOS.forEach(function (c) { if (c !== 'Adesão (0-10)') sh.getRange(2, t.col(c), sh.getMaxRows() - 1, 1).clearDataValidations(); });
  sh.getRange(2, cAd, sh.getMaxRows() - 1, 1).setDataValidation(
    SpreadsheetApp.newDataValidation().requireNumberBetween(0, 10).setAllowInvalid(false).setHelpText('De 0 a 10').build());
  CAMPOS_CLINICOS.forEach(function (c) { if (c !== 'Adesão (0-10)') sh.setColumnWidth(t.col(c), 220); });
  numerarAtendimentos();
  montarHistorico();
  SpreadsheetApp.getUi().alert('Pronto! ' + (novas ? novas + ' colunas novas na aba Consultas. ' : '') +
    'O "Nº do atendimento" agora é preenchido sozinho, e a aba "' + ABA_HISTORICO + '" mostra tudo de um atleta.\n\n' +
    'Próximo: menu 🏈 › 4. Criar formulário de atendimento (celular).');
}

/** numera os atendimentos de cada atleta pela data; Tipo vazio vira 1ª consulta / Retorno */
function numerarAtendimentos() {
  var t = tabela(ABA_CONSULTAS), cN = t.col(COL_NUMERO), cT = t.col('Tipo');
  if (!cN || !t.linhas.length) return;
  var por = {};
  t.linhas.forEach(function (c) {
    if (!c['Atleta'] || SEM_EVENTO.indexOf(c['Status']) >= 0 || !inicio(c)) return;
    var a = String(c['Atleta']).trim(); (por[a] = por[a] || []).push(c);
  });
  var num = {}, tipo = {};
  Object.keys(por).forEach(function (a) {
    por[a].sort(function (x, y) { return inicio(x) - inicio(y); }).forEach(function (c, i) {
      num[c._linha] = i + 1;
      if (!c['Tipo']) tipo[c._linha] = i === 0 ? '1ª consulta' : 'Retorno';
    });
  });
  var n = t.linhas.length;
  var colN = t.sh.getRange(2, cN, n, 1), atualN = colN.getValues(), mudouN = false;
  var colT = t.sh.getRange(2, cT, n, 1), atualT = colT.getValues(), mudouT = false;
  t.linhas.forEach(function (c, i) {
    var v = num[c._linha] || '';
    if (atualN[i][0] !== v) { atualN[i][0] = v; mudouN = true; }
    if (tipo[c._linha] && !atualT[i][0]) { atualT[i][0] = tipo[c._linha]; mudouT = true; }
  });
  if (mudouN) colN.setValues(atualN);
  if (mudouT) colT.setValues(atualT);
}

/** colunas mostradas na aba Histórico do atleta */
var HIST_CONSULTAS = [COL_NUMERO, 'Data', 'Hora', 'Tipo', 'Status', 'Objetivo / queixa', 'Resumo e condutas'].concat(CAMPOS_CLINICOS).concat(['Próximo retorno']);
var HIST_AVALIACOES = ['Data', 'Peso (kg)', 'Massa muscular (kg)', '% água corporal', 'Dobra tríceps (mm)', 'Dobra subescapular (mm)',
  'Dobra suprailíaca (mm)', 'Dobra abdominal (mm)', 'Circ. cintura (cm)', 'Observações'];
var HIST_LINHAS = 300;

/** aba Histórico do atleta: escolhe o atleta em B3 e o script preenche (sem fórmulas, funciona em qualquer idioma) */
function montarHistorico() {
  var ss = SpreadsheetApp.getActive(), h = ss.getSheetByName(ABA_HISTORICO);
  var escolhido = h ? h.getRange('B3').getValue() : '';
  if (h) { h.clear(); h.getRange('B3').clearDataValidations(); } else h = ss.insertSheet(ABA_HISTORICO, 3);
  h.getRange('A1').setValue('🏈 HISTÓRICO DO ATLETA').setFontSize(16).setFontWeight('bold').setFontColor('#13246B');
  h.getRange('A3:A7').setValues([['Atleta:'], ['Posições:'], ['Atendimentos realizados:'], ['Próximo retorno:'], ['Adesão média (0-10):']])
    .setFontWeight('bold').setHorizontalAlignment('right');
  h.getRange('B3').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInRange(ss.getRange('Atletas!A2:A'), true).build())
    .setBackground('#FFF4CC').setFontWeight('bold').setFontSize(12);
  if (escolhido) h.getRange('B3').setValue(escolhido);
  h.getRange('C3').setValue('◀ escolha o atleta aqui (atualiza sozinho)').setFontColor('#5F6B7A');
  h.getRange(9, 1).setValue('ATENDIMENTOS (mais recente primeiro)').setFontWeight('bold').setFontColor('#13246B');
  h.getRange(10, 1, 1, HIST_CONSULTAS.length).setValues([HIST_CONSULTAS]).setBackground('#13246B').setFontColor('#FFFFFF').setFontWeight('bold').setWrap(true);
  var iniV = HIST_CONSULTAS.length + 2;
  h.getRange(9, iniV).setValue('AVALIAÇÕES').setFontWeight('bold').setFontColor('#13246B');
  h.getRange(10, iniV, 1, HIST_AVALIACOES.length).setValues([HIST_AVALIACOES]).setBackground('#007222').setFontColor('#FFFFFF').setFontWeight('bold').setWrap(true);
  h.getRange(11, 2, HIST_LINHAS, 1).setNumberFormat('dd/MM/yyyy');
  h.getRange(11, 3, HIST_LINHAS, 1).setNumberFormat('HH:mm');
  h.getRange(11, HIST_CONSULTAS.length, HIST_LINHAS, 1).setNumberFormat('dd/MM/yyyy');
  h.getRange(11, iniV, HIST_LINHAS, 1).setNumberFormat('dd/MM/yyyy');
  h.getRange('B6').setNumberFormat('dd/MM/yyyy');
  h.setColumnWidth(1, 190); h.setColumnWidth(2, 110);
  [6, 7, 8, 9, 10, 12].forEach(function (k) { h.setColumnWidth(k, 230); });
  h.getRange(11, 1, HIST_LINHAS, iniV + HIST_AVALIACOES.length).setVerticalAlignment('top').setWrap(true);
  h.setFrozenRows(10);
  preencherHistorico();
}

/** escreve na aba os dados do atleta escolhido em B3 */
function preencherHistorico() {
  var h = SpreadsheetApp.getActive().getSheetByName(ABA_HISTORICO);
  if (!h) return;
  var atleta = String(h.getRange('B3').getValue() || '').trim();
  var iniV = HIST_CONSULTAS.length + 2;
  h.getRange(11, 1, HIST_LINHAS, iniV + HIST_AVALIACOES.length).clearContent();
  h.getRange('B4:B7').clearContent();
  if (!atleta) return;
  var a = atletasPorNome()[atleta];
  var cons = tabela(ABA_CONSULTAS).linhas.filter(function (c) { return String(c['Atleta']).trim() === atleta && c['Data'] instanceof Date; })
    .sort(function (x, y) { return (inicio(y) || 0) - (inicio(x) || 0); });
  var avs = tabela(ABA_AVALIACOES).linhas.filter(function (v) { return String(v['Atleta']).trim() === atleta && v['Data'] instanceof Date; })
    .sort(function (x, y) { return y['Data'] - x['Data']; });
  var feitas = cons.filter(function (c) { return c['Status'] === 'Realizada'; });
  var retornos = feitas.map(function (c) { return c['Próximo retorno']; }).filter(function (d) { return d instanceof Date; });
  var ades = cons.map(function (c) { return c['Adesão (0-10)']; }).filter(function (x) { return x !== '' && !isNaN(Number(x)); }).map(Number);
  h.getRange('B4:B7').setValues([[posicoes(a)], [feitas.length], [retornos.length ? new Date(Math.max.apply(null, retornos)) : '–'],
    [ades.length ? Math.round(ades.reduce(function (s, x) { return s + x; }, 0) / ades.length * 10) / 10 : '–']]);
  var mC = cons.length ? cons.map(function (c) { return HIST_CONSULTAS.map(function (k) { return c[k] === undefined ? '' : c[k]; }); })
                       : [['Nenhum atendimento'].concat(HIST_CONSULTAS.slice(1).map(function () { return ''; }))];
  h.getRange(11, 1, Math.min(mC.length, HIST_LINHAS), HIST_CONSULTAS.length).setValues(mC.slice(0, HIST_LINHAS));
  var mV = avs.length ? avs.map(function (v) { return HIST_AVALIACOES.map(function (k) { return v[k] === undefined ? '' : v[k]; }); })
                      : [['Nenhuma avaliação'].concat(HIST_AVALIACOES.slice(1).map(function () { return ''; }))];
  h.getRange(11, iniV, Math.min(mV.length, HIST_LINHAS), HIST_AVALIACOES.length).setValues(mV.slice(0, HIST_LINHAS));
}

function abrirHistorico() {
  var h = SpreadsheetApp.getActive().getSheetByName(ABA_HISTORICO);
  if (!h) { prepararAtendimentos(); h = SpreadsheetApp.getActive().getSheetByName(ABA_HISTORICO); }
  preencherHistorico(); h.activate(); h.getRange('B3').activate();
}

// ------------------------------------------------------------------ formulário de atendimento (celular)

function nomesDosAtletas() {
  return tabela(ABA_ATLETAS).linhas.filter(function (a) { return a['Atleta'] && a['Status'] !== 'Inativo'; })
    .map(function (a) { return String(a['Atleta']).trim(); }).sort();
}

function criarFormulario() {
  var props = PropertiesService.getScriptProperties(), ui = SpreadsheetApp.getUi();
  if (props.getProperty('FORM_ID')) {
    try {
      var velho = FormApp.openById(props.getProperty('FORM_ID'));
      ui.alert('O formulário já existe:\n' + velho.getPublishedUrl() + '\n\nPra criar outro, apague o antigo no Drive e rode de novo.');
      return;
    } catch (e) { /* foi apagado: cria outro */ }
  }
  var f = FormApp.create('🏈 Atendimento · Time Exemplo');
  f.setDescription('Registro de atendimento nutricional. Grava direto na planilha "Time Exemplo - Nutrição".')
   .setCollectEmail(false).setShowLinkToRespondAgain(true).setConfirmationMessage('Atendimento registrado ✅');
  f.addListItem().setTitle('Atleta').setChoiceValues(nomesDosAtletas()).setRequired(true);
  f.addDateItem().setTitle('Data').setRequired(true);
  f.addTimeItem().setTitle('Hora');
  f.addListItem().setTitle('Tipo').setChoiceValues(['1ª consulta', 'Retorno', 'Avaliação', 'Online rápida']);
  f.addListItem().setTitle('Modalidade').setChoiceValues(['Online', 'Presencial']);
  f.addListItem().setTitle('Status').setChoiceValues(['Realizada', 'Faltou', 'Agendada', 'Confirmada', 'Remarcada', 'Cancelada']).setRequired(true);
  f.addParagraphTextItem().setTitle('Objetivo / queixa');
  f.addParagraphTextItem().setTitle('Resumo e condutas');
  f.addParagraphTextItem().setTitle('Hábitos / recordatório');
  f.addParagraphTextItem().setTitle('Plano entregue');
  f.addParagraphTextItem().setTitle('Suplementação prescrita');
  f.addScaleItem().setTitle('Adesão (0-10)').setBounds(0, 10).setLabels('nenhuma', 'total');
  f.addParagraphTextItem().setTitle('Sintomas / observações');
  f.addDateItem().setTitle('Próximo retorno');
  f.addPageBreakItem().setTitle('Avaliação (opcional)').setHelpText('Preencha só se fez medidas neste atendimento. Use vírgula ou ponto nos decimais.');
  CAMPOS_AVALIACAO.forEach(function (c) { f.addTextItem().setTitle(c); });
  f.addParagraphTextItem().setTitle('Observações da avaliação');
  props.setProperties({FORM_ID: f.getId(), FORM_ATLETAS: nomesDosAtletas().join('|')});
  ScriptApp.newTrigger('aoEnviarFormulario').forForm(f).onFormSubmit().create();
  var url = f.getPublishedUrl();
  telegram('📝 <b>Formulário de atendimento · Time Exemplo</b>\nSalve este link no celular (tela inicial):\n' + url);
  ui.alert('Formulário criado! O link também foi pro seu Telegram:\n\n' + url +
    '\n\nCada envio grava o atendimento na aba Consultas (e, se tiver medidas, na aba Avaliações). ' +
    'Se já existir uma consulta do mesmo atleta na mesma data, ela é completada em vez de duplicada.');
}

/** mantém a lista de atletas do formulário igual à aba Atletas */
function atualizarListaDoFormulario() {
  var props = PropertiesService.getScriptProperties(), id = props.getProperty('FORM_ID');
  if (!id) return;
  var nomes = nomesDosAtletas(), chave = nomes.join('|');
  if (props.getProperty('FORM_ATLETAS') === chave) return;
  try {
    var item = FormApp.openById(id).getItems(FormApp.ItemType.LIST).filter(function (i) { return i.getTitle() === 'Atleta'; })[0];
    if (item) { item.asListItem().setChoiceValues(nomes); props.setProperty('FORM_ATLETAS', chave); }
  } catch (e) { /* formulário apagado */ }
}

function numeroDoTexto(x) {
  if (x === '' || x == null) return '';
  var n = Number(String(x).replace(/\s/g, '').replace(',', '.'));
  return isNaN(n) ? String(x) : n;
}

function aoEnviarFormulario(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var r = {};
    e.response.getItemResponses().forEach(function (ir) { r[ir.getItem().getTitle()] = ir.getResponse(); });
    var atleta = String(r['Atleta'] || '').trim();
    if (!atleta || !r['Data']) return;
    var p = String(r['Data']).split('-'), dia = new Date(+p[0], +p[1] - 1, +p[2]);
    var hora = '';
    if (r['Hora']) { var hp = String(r['Hora']).split(':'); hora = new Date(1899, 11, 30, +hp[0], +hp[1]); }
    var retorno = '';
    if (r['Próximo retorno']) { var rp = String(r['Próximo retorno']).split('-'); retorno = new Date(+rp[0], +rp[1] - 1, +rp[2]); }

    // consulta: completa a do mesmo atleta e dia, ou cria uma linha nova
    var t = tabela(ABA_CONSULTAS);
    var alvo = t.linhas.filter(function (c) {
      return String(c['Atleta']).trim() === atleta && c['Data'] instanceof Date && mesmoDia(c['Data'], dia) && SEM_EVENTO.indexOf(c['Status']) < 0;
    })[0];
    var linha = alvo ? alvo._linha : (t.linhas.filter(function (c) { return c['Atleta']; }).reduce(function (m, c) { return Math.max(m, c._linha); }, 1) + 1);
    var valores = {'Atleta': atleta, 'Data': dia, 'Hora': hora, 'Tipo': r['Tipo'], 'Modalidade': r['Modalidade'], 'Status': r['Status'],
      'Objetivo / queixa': r['Objetivo / queixa'], 'Resumo e condutas': r['Resumo e condutas'], 'Próximo retorno': retorno};
    CAMPOS_CLINICOS.forEach(function (c) { valores[c] = c === 'Adesão (0-10)' ? numeroDoTexto(r[c]) : r[c]; });
    Object.keys(valores).forEach(function (k) {
      var v = valores[k], col = t.col(k);
      if (!col || v === '' || v == null) return;
      t.sh.getRange(linha, col).setValue(v);
    });

    // avaliação, se veio alguma medida
    var med = {};
    CAMPOS_AVALIACAO.forEach(function (c) { var n = numeroDoTexto(r[c]); if (n !== '') med[c] = n; });
    if (Object.keys(med).length) {
      var av = tabela(ABA_AVALIACOES);
      var la = av.linhas.filter(function (x) { return x['Atleta']; }).reduce(function (m, x) { return Math.max(m, x._linha); }, 1) + 1;
      med['Atleta'] = atleta; med['Data'] = dia;
      if (r['Observações da avaliação']) med['Observações'] = r['Observações da avaliação'];
      Object.keys(med).forEach(function (k) { if (av.col(k)) av.sh.getRange(la, av.col(k)).setValue(med[k]); });
    }
    SpreadsheetApp.flush();
    sincronizarAgenda();
    telegram('✅ <b>Atendimento registrado</b>\n' + esc(atleta) + ' · ' + fmt(dia, 'dd/MM') + ' · ' + esc(r['Status'] || '') +
             (Object.keys(med).length ? '\n📏 Avaliação lançada' : '') + (alvo ? '\n(completou a consulta que já estava marcada)' : ''));
  } finally { lock.releaseLock(); }
}

// ------------------------------------------------------------------ dados de teste

var PREFIXO_TESTE = 'TESTE ';

function linhaLivre(t) {
  return t.linhas.filter(function (x) { return x['Atleta']; }).reduce(function (m, x) { return Math.max(m, x._linha); }, 1) + 1;
}

function gravarLinhas(nomeAba, objetos) {
  var t = tabela(nomeAba), ini = linhaLivre(t);
  var matriz = objetos.map(function (o) { return t.cab.map(function (c) { return o[c] === undefined ? '' : o[c]; }); });
  if (matriz.length) t.sh.getRange(ini, 1, matriz.length, t.cab.length).setValues(matriz);
}

/** 3 atletas de teste, 5 atendimentos cada e uma avaliação por atendimento realizado */
function criarDadosTeste() {
  var ui = SpreadsheetApp.getUi();
  if (tabela(ABA_ATLETAS).linhas.some(function (a) { return String(a['Atleta']).indexOf(PREFIXO_TESTE) === 0; })) {
    ui.alert('Os dados de teste já existem. Use "Apagar dados de teste" antes de criar de novo.'); return;
  }
  var H = function (h, m) { return new Date(1899, 11, 30, h, m || 0); };
  var D = function (a, m, d) { return new Date(a, m - 1, d); };
  var atletas = [
    {nome: 'TESTE Alfa Silva', curto: 'Alfa Silva', pos: ['WR', '', ''], nasc: D(2000, 4, 12), peso: 78, alt: 1.80},
    {nome: 'TESTE Beta Souza', curto: 'Beta Souza', pos: ['QB', 'DB', ''], nasc: D(1997, 9, 3), peso: 86, alt: 1.85},
    {nome: 'TESTE Gama Lima', curto: 'Gama Lima', pos: ['BL', '', ''], nasc: D(2002, 1, 25), peso: 92, alt: 1.88}];
  gravarLinhas(ABA_ATLETAS, atletas.map(function (a) {
    return {'Atleta': a.nome, 'Nome curto': a.curto, 'Posição 1': a.pos[0], 'Posição 2': a.pos[1], 'Posição 3': a.pos[2],
      'Data de nascimento': a.nasc, 'Peso informado (kg)': a.peso, 'Altura informada (m)': a.alt, 'QUAEST': 'Respondido',
      'Status': 'Ativo', 'Observações': 'dados de teste'};
  }));

  var datas = [D(2026, 8, 18), D(2026, 9, 8), D(2026, 9, 29), D(2026, 10, 20), D(2026, 11, 24)];
  var resumos = ['Anamnese completa, objetivos para a temporada e cálculo das necessidades.',
    'Ajuste do pré-treino e da hidratação nos treinos noturnos.', 'Revisão do plano: mais proteína no café da manhã.',
    'Boa evolução de composição corporal; manter estratégia.', 'Planejamento para o período competitivo.'];
  var planos = ['Plano alimentar 1 (manutenção)', 'Plano 1 ajustado (pré-treino)', 'Plano 2 (proteína 1,8 g/kg)', 'Plano 2 mantido', 'Plano de competição'];
  var supl = ['—', 'Creatina 5 g/dia', 'Creatina 5 g/dia + whey pós-treino', 'Creatina 5 g/dia + whey pós-treino', 'Creatina + cafeína pré-jogo (3 mg/kg)'];
  // status por atleta: o 5º atendimento é futuro para Alfa e Beta; Gama teve uma falta
  var status = {
    'TESTE Alfa Silva': ['Realizada', 'Realizada', 'Realizada', 'Realizada', 'Confirmada'],
    'TESTE Beta Souza': ['Realizada', 'Realizada', 'Realizada', 'Realizada', 'Agendada'],
    'TESTE Gama Lima': ['Realizada', 'Realizada', 'Faltou', 'Realizada', 'Realizada']};
  var adesao = {'TESTE Alfa Silva': [6, 7, 8, 9, ''], 'TESTE Beta Souza': [5, 6, 6, 7, ''], 'TESTE Gama Lima': [7, 8, '', 8, 9]};
  var consultas = [], avaliacoes = [];
  atletas.forEach(function (a, k) {
    var gamaD = a.nome === 'TESTE Gama Lima';
    datas.forEach(function (d, i) {
      var dia = gamaD && i === 4 ? D(2026, 11, 3) : d, st = status[a.nome][i], feita = st === 'Realizada';
      var prox = i < 4 ? (gamaD && i === 3 ? D(2026, 11, 3) : datas[i + 1]) : D(2026, 12, 15);
      consultas.push({'Atleta': a.nome, 'Data': dia, 'Hora': H(18 + k, 0), 'Duração (min)': 60, 'Tipo': i === 0 ? '1ª consulta' : 'Retorno',
        'Modalidade': 'Online', 'Link da consulta': 'https://meet.google.com/abc-defg-hij', 'Status': st,
        'Objetivo / queixa': i === 0 ? 'Melhorar composição corporal e rendimento' : '',
        'Resumo e condutas': feita ? resumos[i] : (st === 'Faltou' ? 'Não compareceu; remarcar.' : ''),
        'Hábitos / recordatório': feita ? (i === 0 ? '4 refeições/dia, pula o café da manhã, pouca água nos treinos' : 'Seguindo o plano na maior parte da semana') : '',
        'Plano entregue': feita ? planos[i] : '', 'Suplementação prescrita': feita ? supl[i] : '',
        'Adesão (0-10)': feita ? adesao[a.nome][i] : '', 'Sintomas / observações': feita && i === 1 ? 'Desconforto gástrico em jogo noturno' : '',
        'Próximo retorno': feita ? prox : '', 'Avisos enviados': 'D1,H1,POS'});
      if (!feita) return;
      var p = i / 4;   // evolução de 0 a 1
      var f = function (ini, fim) { return Math.round((ini + (fim - ini) * p) * 10) / 10; };
      var dob = [[10, 7], [12, 9.5], [11, 8], [10, 8], [14, 10], [18, 13], [13, 10]].map(function (x) { return f(x[0] + k * 2, x[1] + k * 2); });
      avaliacoes.push({'Atleta': a.nome, 'Data': dia, 'Peso (kg)': f(a.peso, a.peso + (k === 2 ? -3 : 1.5)), 'Altura (cm)': Math.round(a.alt * 100),
        'Dobra tríceps (mm)': dob[0], 'Dobra subescapular (mm)': dob[1], 'Dobra peitoral (mm)': dob[2], 'Dobra axilar média (mm)': dob[3],
        'Dobra suprailíaca (mm)': dob[4], 'Dobra abdominal (mm)': dob[5], 'Dobra coxa medial (mm)': dob[6],
        'Circ. braço relaxado (cm)': f(32 + k, 33.5 + k), 'Circ. braço contraído (cm)': f(35 + k, 37 + k), 'Circ. cintura (cm)': f(80 + k * 4, 78 + k * 4),
        'Circ. coxa medial (cm)': f(56 + k * 2, 58 + k * 2), 'Massa muscular (kg)': f(a.peso * 0.78, a.peso * 0.78 + 2.5),
        '% água corporal': f(58 + k, 61 + k), 'Observações': 'dados de teste'});
    });
  });
  gravarLinhas(ABA_CONSULTAS, consultas);
  gravarLinhas(ABA_AVALIACOES, avaliacoes);
  SpreadsheetApp.flush();
  sincronizarAgenda();
  var h = SpreadsheetApp.getActive().getSheetByName(ABA_HISTORICO);
  if (h) { h.getRange('B3').setValue('TESTE Alfa Silva'); preencherHistorico(); }
  ui.alert('Dados de teste criados: 3 atletas, ' + consultas.length + ' atendimentos e ' + avaliacoes.length + ' avaliações.\n\n' +
    'Veja as abas Consultas, Avaliações e Histórico do atleta. No Power BI, clique em Atualizar.\n' +
    'Pra remover tudo: menu 🏈 › Apagar dados de teste.');
}

/** remove os atletas TESTE, os atendimentos (e os eventos na agenda) e as avaliações */
function apagarDadosTeste() {
  var ehTeste = function (o) { return String(o['Atleta'] || '').indexOf(PREFIXO_TESTE) === 0; };
  var t = tabela(ABA_CONSULTAS), cal = agenda(), n = 0;
  t.linhas.filter(ehTeste).forEach(function (c) {
    var id = String(c['ID do evento (Google)'] || '');
    if (id) { try { var ev = cal.getEventById(id); if (ev) ev.deleteEvent(); } catch (e) {} }
  });
  [ABA_CONSULTAS, ABA_AVALIACOES, ABA_ATLETAS].forEach(function (aba) {
    var tt = tabela(aba);
    tt.linhas.filter(ehTeste).map(function (x) { return x._linha; }).sort(function (a, b) { return b - a; })
      .forEach(function (l) { tt.sh.deleteRow(l); n++; });
  });
  numerarAtendimentos();
  SpreadsheetApp.getUi().alert(n ? 'Dados de teste apagados (' + n + ' linhas e os eventos da agenda). No Power BI, clique em Atualizar.'
                                 : 'Não há dados de teste.');
}
