"""Agenda de consultas (tabela consulta, sql/09_agenda.sql) e confirmação por WhatsApp e e-mail.

A confirmação por WhatsApp abre a conversa com o texto pronto (você aperta enviar). A por e-mail sai pela sua conta
Google, pelo mesmo script do check-in (sistema/checkin_google.gs, versão 3 ou mais), com um convite de calendário
(.ics) anexo. A próxima consulta marcada vira a "Próxima consulta" do paciente, que alimenta o lembrete de retorno.
Com o Google Agenda ligado (script versão 4), cada consulta vira um evento na sua agenda principal do Google (e muda
ou some junto), e os seus outros compromissos do Google aparecem na semana da Agenda.
"""
import re
from datetime import datetime, timedelta, timezone

import checkin

VERSAO_EMAIL = 3   # versão do checkin_google.gs que envia e-mail avulso
VERSAO_GOOGLE = 4  # versão que mexe no Google Agenda
STATUS = {"agendada": "Agendada", "confirmada": "Confirmada", "realizada": "Realizada", "faltou": "Faltou",
          "cancelada": "Cancelada"}
MODALIDADES = {"presencial": "Presencial", "online": "Online"}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
CAMPOS = ["id", "paciente_id", "nome", "telefone", "email", "inicio", "duracao_min", "modalidade", "local", "status",
          "observacao", "whatsapp_enviado_em", "email_enviado_em", "google_evento_id"]


def lista(cur, onde, args):
    cur.execute(f"""SELECT c.id, c.paciente_id, p.nome, p.telefone, p.email, c.inicio, c.duracao_min, c.modalidade,
                           c.local, c.status, c.observacao, c.whatsapp_enviado_em, c.email_enviado_em, c.google_evento_id
                    FROM consulta c JOIN paciente p ON p.id = c.paciente_id
                    WHERE {onde} ORDER BY c.inicio""", args)
    consultas = [dict(zip(CAMPOS, r)) for r in cur.fetchall()]
    for c in consultas:
        c["fim"] = c["inicio"] + timedelta(minutes=c["duracao_min"])
    return consultas


def buscar(cur, cid):
    r = lista(cur, "c.id = %s", (cid,))
    return r[0] if r else None


def conflitos(cur, inicio, duracao, ignorar=None):
    """outras consultas (não canceladas) no mesmo horário"""
    fim = inicio + timedelta(minutes=duracao)
    return lista(cur, """c.status <> 'cancelada' AND c.id <> %s AND c.inicio < %s
                         AND c.inicio + make_interval(mins => c.duracao_min) > %s""", (ignorar or 0, fim, inicio))


def atualizar_retorno(cur, pid):
    """a próxima consulta marcada (não cancelada) vira a "Próxima consulta" da ficha; sem nenhuma, fica vazia"""
    cur.execute("""UPDATE paciente SET retorno_em = (
                       SELECT min(inicio)::date FROM consulta
                       WHERE paciente_id = %(p)s AND status IN ('agendada', 'confirmada') AND inicio >= current_date)
                   WHERE id = %(p)s""", {"p": pid})


def variaveis(c, cfg):
    """palavras entre chaves das mensagens de confirmação"""
    local = (c.get("local") or "").strip()
    if c["modalidade"] == "online":
        texto_local = f"A consulta será online{': ' + local if local else ''}."
    else:
        texto_local = f"Endereço: {local}." if local else ""
    return {"{data_consulta}": c["inicio"].strftime("%d/%m/%Y"), "{hora_consulta}": c["inicio"].strftime("%H:%M"),
            "{dia_semana}": DIAS[c["inicio"].weekday()], "{local_consulta}": texto_local}


def texto(modelo, c, cfg):
    v = {"{primeiro_nome}": c["nome"].split()[0].title(), "{nome}": c["nome"], **variaveis(c, cfg)}
    for k, val in v.items():
        modelo = modelo.replace(k, val)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", modelo)).strip()


def ics(c, cfg):
    """convite de calendário da consulta (horário em UTC, vale em qualquer fuso)"""
    utc = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # hora local do computador -> UTC
    esc = lambda s: str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    profissional = cfg["agenda"].get("profissional") or "Consulta de nutrição"
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sistema de avaliacoes//Agenda//PT", "METHOD:PUBLISH",
              "BEGIN:VEVENT", f"UID:consulta-{c['id']}@sistema-avaliacoes", f"DTSTAMP:{utc(datetime.now())}",
              f"DTSTART:{utc(c['inicio'])}", f"DTEND:{utc(c['fim'])}",
              f"SUMMARY:{esc('Consulta de nutrição - ' + profissional)}",
              f"LOCATION:{esc(c.get('local') or ('Online' if c['modalidade'] == 'online' else ''))}",
              f"DESCRIPTION:{esc(c.get('observacao') or '')}",
              "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", "DESCRIPTION:Consulta de nutrição", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(linhas) + "\r\n"


def _local_iso(d):
    return d.astimezone().isoformat()   # hora deste computador, com o fuso (o Google entende)


def google_pronto(cfg):
    """o Google Agenda está ligado na Configuração e o script tem a versão que mexe na agenda"""
    ck = cfg.get("checkin", {})
    return (bool(cfg.get("agenda", {}).get("google")) and bool(ck.get("url") and ck.get("chave"))
            and int(ck.get("versao") or 0) >= VERSAO_GOOGLE)


def _evento(cfg, corpo):
    ck = cfg["checkin"]
    r = checkin._postar(ck["url"], {"chave": ck["chave"], "acao": "evento", **corpo})
    if r.get("erro"):
        raise checkin.ErroGoogle("O Google Agenda não foi atualizado: "
                                 + {"acao": "o script do Google está desatualizado"}.get(r["erro"], r.get("detalhe") or r["erro"]) + ".")
    return r


def sincronizar_evento(cur, cfg, c):
    """leva a consulta para o Google Agenda: cria ou atualiza o evento; cancelada, apaga. Devolve True se mexeu."""
    if not google_pronto(cfg):
        return False
    if c["status"] == "cancelada":
        if c.get("google_evento_id"):
            _evento(cfg, {"evento": c["google_evento_id"], "excluir": True})
            cur.execute("UPDATE consulta SET google_evento_id = NULL WHERE id = %s", (c["id"],))
        return True
    ag = cfg["agenda"]
    linhas = [f"Paciente: {c['nome']}", f"Telefone: {c['telefone']}" if c.get("telefone") else "",
              f"Modalidade: {MODALIDADES.get(c['modalidade'], c['modalidade'])}", f"Situação: {STATUS.get(c['status'], c['status'])}",
              f"Observação: {c['observacao']}" if c.get("observacao") else "", "", "Criada pelo sistema de avaliações."]
    convidado = c["email"].strip() if ag.get("google_convidar") and checkin.email_valido(c.get("email")) else ""
    r = _evento(cfg, {"evento": c.get("google_evento_id") or "", "consulta": c["id"],
                      "titulo": f"Consulta · {c['nome']}" + (" (online)" if c["modalidade"] == "online" else ""),
                      "inicio": _local_iso(c["inicio"]), "fim": _local_iso(c["fim"]), "local": c.get("local") or "",
                      "descricao": "\n".join(l for l in linhas if l is not None), "convidado": convidado})
    if r.get("evento") and r["evento"] != c.get("google_evento_id"):
        cur.execute("UPDATE consulta SET google_evento_id = %s WHERE id = %s", (r["evento"], c["id"]))
    return True


def excluir_evento(cfg, evento_id):
    if evento_id and google_pronto(cfg):
        _evento(cfg, {"evento": evento_id, "excluir": True})


def eventos_google(cfg, ini, fim):
    """seus outros compromissos do Google Agenda entre as datas (os criados pelo sistema ficam de fora)"""
    ck = cfg["checkin"]
    r = checkin._chamar(ck["url"], ck["chave"], acao="eventos", de=_local_iso(datetime.combine(ini, datetime.min.time())),
                        ate=_local_iso(datetime.combine(fim, datetime.min.time())))
    saida = []
    for e in r.get("eventos", []):
        conv = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        saida.append({"titulo": e.get("titulo") or "(sem título)", "inicio": conv(e["inicio"]), "fim": conv(e["fim"]),
                      "dia_todo": bool(e.get("dia_todo"))})
    return saida


def email_pronto(cfg):
    """o e-mail sai pelo script do Google: precisa estar ligado e na versão 3"""
    ck = cfg.get("checkin", {})
    return bool(ck.get("url") and ck.get("chave")) and int(ck.get("versao") or 0) >= VERSAO_EMAIL


def enviar_email(c, cfg, assunto, corpo):
    if not checkin.email_valido(c.get("email")):
        raise checkin.ErroGoogle("O paciente não tem um e-mail válido cadastrado.")
    if not email_pronto(cfg):
        raise checkin.ErroGoogle("Para enviar e-mail, atualize o código do script do Google (Configuração › Agenda).")
    ck = cfg["checkin"]
    r = checkin._postar(ck["url"], {"chave": ck["chave"], "acao": "email", "para": c["email"].strip(),
                                    "assunto": assunto, "texto": corpo, "ics": ics(c, cfg),
                                    "remetente": cfg["agenda"].get("profissional") or ""})
    if r.get("erro"):
        detalhe = {"sem_email": "o e-mail do paciente está vazio", "acao": "o script do Google está desatualizado",
                   "envio": r.get("detalhe", "o Gmail recusou o envio")}.get(r["erro"], r["erro"])
        raise checkin.ErroGoogle(f"O e-mail não foi enviado: {detalhe}.")
    return r
