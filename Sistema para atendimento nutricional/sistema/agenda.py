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
VERSAO_CONFIRMAR = 9   # versão com a página "confirme sua presença" para o paciente
STATUS = {"agendada": "Agendada", "confirmada": "Confirmada", "realizada": "Realizada", "faltou": "Faltou",
          "cancelada": "Cancelada"}
MODALIDADES = {"presencial": "Presencial", "online": "Online"}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
CAMPOS = ["id", "paciente_id", "nome", "telefone", "email", "inicio", "duracao_min", "modalidade", "local", "status",
          "observacao", "whatsapp_enviado_em", "email_enviado_em", "google_evento_id", "token_confirmacao",
          "resposta_paciente", "resposta_em"]


def lista(cur, onde, args):
    cur.execute(f"""SELECT c.id, c.paciente_id, p.nome, p.telefone, p.email, c.inicio, c.duracao_min, c.modalidade,
                           c.local, c.status, c.observacao, c.whatsapp_enviado_em, c.email_enviado_em, c.google_evento_id,
                           c.token_confirmacao, c.resposta_paciente, c.resposta_em
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


def texto(modelo, c, cfg, com_link=True):
    """com_link=False no assunto do e-mail: o link só entra no corpo da mensagem"""
    link = link_confirmacao(c, cfg) if com_link else ""
    if link and "{link_confirmacao}" not in modelo:     # mensagens antigas, sem a variável: o link vai no fim
        modelo = modelo.rstrip() + "\n\nConfirme sua presença por aqui: {link_confirmacao}"
    v = {"{primeiro_nome}": c["nome"].split()[0].title(), "{nome}": c["nome"], **variaveis(c, cfg),
         "{link_confirmacao}": link}
    for k, val in v.items():
        modelo = modelo.replace(k, val)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", modelo)).strip()


# ---------- confirmação pelo próprio paciente (página do script do Google) ----------

def confirmar_pronto(cfg):
    ck = cfg.get("checkin", {})
    return bool(ck.get("url") and ck.get("chave")) and int(ck.get("versao") or 0) >= VERSAO_CONFIRMAR


def garantir_token(cur, c):
    """código aleatório do link de confirmação desta consulta (criado uma vez)"""
    if not c.get("token_confirmacao"):
        import secrets, string
        c["token_confirmacao"] = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))
        cur.execute("UPDATE consulta SET token_confirmacao = %s WHERE id = %s", (c["token_confirmacao"], c["id"]))
    return c["token_confirmacao"]


def assinatura(chave, token):
    import hashlib, hmac
    return hmac.new(chave.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def link_confirmacao(c, cfg):
    """link para o paciente tocar em "Confirmo" ou "Preciso remarcar" (vazio se o script não estiver pronto)"""
    if not (confirmar_pronto(cfg) and c.get("token_confirmacao")):
        return ""
    from urllib.parse import urlencode
    ck, tok = cfg["checkin"], c["token_confirmacao"]
    quando = f"{DIAS[c['inicio'].weekday()]}, {c['inicio']:%d/%m} às {c['inicio']:%H:%M}"
    return ck["url"] + "?" + urlencode({"c": tok, "s": assinatura(ck["chave"], tok), "n": c["nome"].split()[0].title(),
                                        "q": quando, "w": checkin.whatsapp_prof(cfg)})


_ultima_busca = [0.0]


def buscar_respostas(con, cfg, minutos=1):
    """traz do script as respostas dos pacientes: "sim" confirma a consulta; "remarcar" fica marcado na agenda"""
    import time
    if not (cfg.get("checkin", {}).get("url") and cfg["checkin"].get("chave")) or time.time() - _ultima_busca[0] < minutos * 60:
        return 0
    _ultima_busca[0] = time.time()
    ck = cfg["checkin"]
    r = checkin._chamar(ck["url"], ck["chave"], acao="confirmacoes")
    if "versao" not in r or not isinstance(r.get("respostas"), dict):
        return 0                                   # script antigo (sem a página de confirmação)
    if int(r["versao"]) > int(ck.get("versao") or 0):
        import contatos                            # o script foi atualizado: guarda a versão nova
        novo = contatos.carregar()
        novo["checkin"]["versao"] = int(r["versao"])
        contatos.salvar(novo)
    cur, n = con.cursor(), 0
    for token, v in r["respostas"].items():
        if v.get("r") not in ("sim", "remarcar"):
            continue
        cur.execute("""UPDATE consulta SET resposta_paciente = %(r)s, resposta_em = %(em)s,
                           status = CASE WHEN %(r)s = 'sim' AND status = 'agendada' THEN 'confirmada' ELSE status END
                       WHERE token_confirmacao = %(t)s AND resposta_em IS DISTINCT FROM %(em)s""",
                    {"r": v["r"], "em": v.get("em"), "t": token})
        n += cur.rowcount
    return n


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


_cache_eventos = {}       # (ini, fim) -> (quando buscou, eventos)
_atualizando = set()


def eventos_google(cfg, ini, fim):
    """seus outros compromissos do Google Agenda entre as datas, sem esperar o Google a cada página: devolve na
    hora o que já foi buscado e atualiza em segundo plano se tiver mais de 2 minutos (a primeira vez espera)"""
    import threading, time
    chave = (ini, fim)
    guardado = _cache_eventos.get(chave)
    if guardado:
        if time.time() - guardado[0] > 120 and chave not in _atualizando:
            _atualizando.add(chave)
            def atualizar():
                try:
                    _cache_eventos[chave] = (time.time(), _buscar_eventos(cfg, ini, fim))
                except Exception:   # noqa: BLE001 — sem internet: fica o que já tinha
                    pass
                finally:
                    _atualizando.discard(chave)
            threading.Thread(target=atualizar, daemon=True).start()
        return guardado[1]
    ev = _buscar_eventos(cfg, ini, fim)
    _cache_eventos[chave] = (time.time(), ev)
    return ev


def _buscar_eventos(cfg, ini, fim):
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
                                    "remetente": cfg["agenda"].get("profissional") or "",
                                    "whatsapp": checkin.whatsapp_prof(cfg)})
    if r.get("erro"):
        detalhe = {"sem_email": "o e-mail do paciente está vazio", "acao": "o script do Google está desatualizado",
                   "envio": r.get("detalhe", "o Gmail recusou o envio")}.get(r["erro"], r["erro"])
        raise checkin.ErroGoogle(f"O e-mail não foi enviado: {detalhe}.")
    return r
