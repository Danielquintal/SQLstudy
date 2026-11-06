"""Lembretes do profissional (tabela lembrete, sql/13_lembretes.sql): tela Lembretes do sistema.

Cada lembrete tem texto, dia e hora, e pode ser ligado a um paciente e repetir (todo dia, semana, 15 dias ou mês).
Quando chega a hora, aparece no número do menu e num aviso na tela do sistema (se ele estiver aberto). Com o Google
Agenda ligado (Configuração › Agenda), cada lembrete também vira um evento curto na sua agenda do Google, que avisa
no celular; com o script do Google na versão 6, o aviso toca exatamente com a antecedência escolhida.
"""
import calendar
from datetime import datetime, timedelta

import agenda

VERSAO_AVISO = 6   # versão do checkin_google.gs que acerta a antecedência do aviso no Google Agenda
REPETIR = {"": "Não repete", "diario": "Todo dia", "semanal": "Toda semana", "quinzenal": "A cada 15 dias",
           "mensal": "Todo mês"}
AVISOS = {0: "Na hora", 10: "10 min antes", 30: "30 min antes", 60: "1 hora antes", 1440: "1 dia antes"}
DURACAO_EVENTO = 15   # minutos que o lembrete ocupa no Google Agenda
CAMPOS = ["id", "texto", "quando", "paciente_id", "paciente", "repetir", "google", "aviso_min", "google_evento_id",
          "feito_em"]


def lista(cur, onde="true", args=(), ordem="l.quando", limite=500):
    cur.execute(f"""SELECT l.id, l.texto, l.quando, l.paciente_id, p.nome, l.repetir, l.google, l.aviso_min,
                           l.google_evento_id, l.feito_em
                    FROM lembrete l LEFT JOIN paciente p ON p.id = l.paciente_id
                    WHERE {onde} ORDER BY {ordem} LIMIT {int(limite)}""", args)
    return [dict(zip(CAMPOS, r)) for r in cur.fetchall()]


def buscar(cur, lid):
    r = lista(cur, "l.id = %s", (lid,))
    return r[0] if r else None


def vencidos(cur):
    """lembretes cuja hora já chegou e que ainda não foram concluídos"""
    return lista(cur, "l.feito_em IS NULL AND l.quando <= now()")


def contar_vencidos(cur):
    cur.execute("SELECT count(*) FROM lembrete WHERE feito_em IS NULL AND quando <= now()")
    return cur.fetchone()[0]


def _mais_um_mes(d):
    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))


def seguinte(quando, repetir):
    """a próxima vez de um lembrete que repete (depois de agora, pulando as que já passaram)"""
    passo = {"diario": timedelta(days=1), "semanal": timedelta(days=7), "quinzenal": timedelta(days=14)}.get(repetir)
    if not passo and repetir != "mensal":
        return None
    d, agora = quando, datetime.now()
    while True:
        d = _mais_um_mes(d) if repetir == "mensal" else d + passo
        if d > agora:
            return d


def quando_texto(d, agora=None):
    """'hoje 14:00', 'amanhã 09:00', 'ontem', 'seg 10/11 08:30'..."""
    agora = agora or datetime.now()
    dias = (d.date() - agora.date()).days
    hora = d.strftime("%H:%M")
    if dias == 0:
        return f"hoje {hora}"
    if dias == 1:
        return f"amanhã {hora}"
    if dias == -1:
        return f"ontem {hora}"
    dia = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][d.weekday()]
    return f"{dia} {d.strftime('%d/%m' if d.year == agora.year else '%d/%m/%Y')} {hora}"


def avisa_certo(cfg):
    """o script do Google já acerta a antecedência do aviso (versão 6)"""
    return int(cfg.get("checkin", {}).get("versao") or 0) >= VERSAO_AVISO


def sincronizar_evento(cur, cfg, l):
    """leva o lembrete ao Google Agenda (cria ou atualiza); concluído, sem Google ou excluído, apaga o evento.
    Devolve True se mexeu no Google."""
    if not agenda.google_pronto(cfg):
        return False
    if l is None:
        return False
    if l["feito_em"] or not l["google"]:
        if l.get("google_evento_id"):
            agenda._evento(cfg, {"evento": l["google_evento_id"], "excluir": True})
            cur.execute("UPDATE lembrete SET google_evento_id = NULL WHERE id = %s", (l["id"],))
            return True
        return False
    descricao = [f"Paciente: {l['paciente']}" if l.get("paciente") else "",
                 f"Repete: {REPETIR[l['repetir']].lower()}" if l.get("repetir") else "",
                 "", f"Lembrete criado pelo sistema {__import__('identidade').marca()}. Marque como feito na tela Lembretes."]
    titulo = "Lembrete: " + l["texto"] + (f" ({l['paciente']})" if l.get("paciente") else "")
    r = agenda._evento(cfg, {"evento": l.get("google_evento_id") or "", "consulta": f"lembrete-{l['id']}",
                             "titulo": titulo[:250], "inicio": agenda._local_iso(l["quando"]),
                             "fim": agenda._local_iso(l["quando"] + timedelta(minutes=DURACAO_EVENTO)),
                             "local": "", "descricao": "\n".join(descricao).strip(), "convidado": "",
                             "aviso": int(l.get("aviso_min") or 0)})
    if r.get("evento") and r["evento"] != l.get("google_evento_id"):
        cur.execute("UPDATE lembrete SET google_evento_id = %s WHERE id = %s", (r["evento"], l["id"]))
    return True


def excluir_evento(cfg, evento_id):
    if evento_id and agenda.google_pronto(cfg):
        agenda._evento(cfg, {"evento": evento_id, "excluir": True})
