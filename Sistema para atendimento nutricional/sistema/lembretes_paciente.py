"""Lembretes para os pacientes (tabelas lembrete_paciente e lembrete_envio, sql/14_lembretes_paciente.sql).

Canais:
- WhatsApp: na hora marcada o lembrete aparece em Contatos com a mensagem pronta; você abre e envia (nunca automático).
- Telegram: automático, pelo robô que você cria no @BotFather. O paciente toca uma vez no link com o código dele.
- E-mail: automático, pela sua conta Google.
- Google Agenda: convite (um evento, ou uma série que repete) na agenda "Lembretes dos pacientes", com o paciente
  convidado; o celular dele avisa pelo Google Agenda.
Os automáticos saem pelo script do Google (sistema/checkin_google.gs, versão 7), de 10 em 10 minutos, mesmo com o
computador desligado: o sistema manda ao script as próximas vezes de cada lembrete (90 dias) sempre que algo muda e,
com o sistema aberto, uma vez por dia.
"""
import calendar
import hashlib
import json
import re
import secrets
import time as _time
from datetime import date, datetime, time, timedelta
from urllib.error import HTTPError
from urllib.request import urlopen

import agenda
import checkin
import contatos
import lembretes

VERSAO = 7               # versão do checkin_google.gs que envia os lembretes dos pacientes
DIAS_A_FRENTE = 90       # o script recebe as vezes dos próximos 90 dias
MAX_VEZES = 150
ATRASO_WHATSAPP = timedelta(days=3)   # vez do WhatsApp mais antiga que isso não aparece mais em Contatos
REPETIR = lembretes.REPETIR
CANAIS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "E-mail", "google": "Google Agenda"}
MODELOS = {
    "agua": ("Beber água", "Oi, {primeiro_nome}! Hora de beber água 💧 Lembre da sua meta de hoje."),
    "suplemento": ("Suplemento", "Oi, {primeiro_nome}! Lembrete: tomar o seu suplemento agora (creatina/whey, conforme o plano)."),
    "refeicao": ("Refeição", "Oi, {primeiro_nome}! Hora do lanche. Confira as opções no seu plano alimentar."),
    "treino": ("Pré-treino", "Oi, {primeiro_nome}! Daqui a pouco é o treino: faça a refeição pré-treino do seu plano."),
    "checkin": ("Pesagem", "Oi, {primeiro_nome}! Amanhã cedo, em jejum, se pese e anote o peso para o check-in."),
}
CAMPOS = ["id", "paciente_id", "nome", "telefone", "email", "telegram_chat", "texto", "inicio", "repetir", "ate",
          "whatsapp", "telegram", "email_ligado", "google", "ativo", "whatsapp_ate", "criado_em"]

_ultima_sinc = 0.0
aviso = None   # último problema ao falar com o script (mostrado na ficha do paciente)


def lista(cur, onde="true", args=()):
    cur.execute(f"""SELECT l.id, l.paciente_id, p.nome, p.telefone, p.email, p.telegram_chat, l.texto, l.inicio,
                           l.repetir, l.ate, l.whatsapp, l.telegram, l.email, l.google, l.ativo, l.whatsapp_ate, l.criado_em
                    FROM lembrete_paciente l JOIN paciente p ON p.id = l.paciente_id
                    WHERE {onde} ORDER BY p.nome, l.inicio""", args)
    return [dict(zip(CAMPOS, r)) for r in cur.fetchall()]


def buscar(cur, lid):
    r = lista(cur, "l.id = %s", (lid,))
    return r[0] if r else None


# ---------- as vezes de cada lembrete ----------

def _mais_meses(d, k):
    m = d.month - 1 + k
    ano, mes = d.year + m // 12, m % 12 + 1
    return d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))


def _vez(l, k):
    """a k-ésima vez (0 = a primeira); no mensal, sempre o dia da primeira (31 vira o último dia do mês curto)"""
    if l["repetir"] == "mensal":
        return datetime.combine(_mais_meses(l["inicio"].date(), k), l["inicio"].time())
    passo = {"diario": 1, "semanal": 7, "quinzenal": 14}.get(l["repetir"], 0)
    return l["inicio"] + timedelta(days=passo * k)


def _passou_do_fim(l, v):
    return bool(l.get("ate")) and v.date() > l["ate"]


def vezes(l, de, ate, limite=MAX_VEZES):
    """as vezes entre as duas datas (de < vez <= ate)"""
    saida, k = [], 0
    if not l["repetir"]:
        return [l["inicio"]] if de < l["inicio"] <= ate else []
    # pula direto para perto de "de" nos que repetem por dias
    passo = {"diario": 1, "semanal": 7, "quinzenal": 14}.get(l["repetir"])
    if passo and de > l["inicio"]:
        k = max(0, (de - l["inicio"]).days // passo - 1)
    while len(saida) < limite:
        v = _vez(l, k)
        if v > ate or _passou_do_fim(l, v):
            break
        if v > de:
            saida.append(v)
        k += 1
        if k > 5000:
            break
    return saida


def ultima_ate(l, t):
    """a última vez marcada até o momento t (ou None)"""
    if l["inicio"] > t:
        return None
    if not l["repetir"]:
        return l["inicio"]
    anteriores = vezes(l, t - timedelta(days=40), t, limite=MAX_VEZES)
    return anteriores[-1] if anteriores else None


def proxima(l, agora=None):
    agora = agora or datetime.now()
    v = vezes(l, agora, agora + timedelta(days=400), limite=1)
    return v[0] if v else None


def descricao(l):
    """'todo dia às 08:00 (até 30/11)', 'qua 05/11 às 10:00'"""
    if not l["repetir"]:
        return lembretes.quando_texto(l["inicio"])
    dia_sem = ["toda segunda", "toda terça", "toda quarta", "toda quinta", "toda sexta", "todo sábado",
               "todo domingo"][l["inicio"].weekday()]
    base = {"diario": "todo dia", "semanal": dia_sem, "quinzenal": "a cada 15 dias",
            "mensal": f"todo dia {l['inicio'].day}"}[l["repetir"]]
    texto = f"{base} às {l['inicio']:%H:%M}"
    if l["inicio"] > datetime.now():
        texto += f", a partir de {l['inicio']:%d/%m}"
    if l.get("ate"):
        texto += f", até {l['ate']:%d/%m/%Y}"
    return texto


# ---------- mensagem ----------

def texto_final(cfg, l, canal):
    """mensagem com o nome trocado; nos automáticos vai a sua assinatura no fim"""
    primeiro = (l["nome"] or "").split()[0].title() if l.get("nome") else ""
    t = (l["texto"] or "").replace("{primeiro_nome}", primeiro).replace("{nome}", l.get("nome") or "").strip()
    if canal in ("telegram", "email", "google"):
        assinatura = cfg["agenda"].get("profissional") or ""
        if assinatura and assinatura not in t:
            t += "\n\n— " + assinatura
    return t


# ---------- WhatsApp (Contatos) ----------

def pendentes_whatsapp(cur, agora=None):
    """lembretes com WhatsApp cuja hora chegou e que você ainda não mandou: [(lembrete, vez)]"""
    agora = agora or datetime.now()
    saida = []
    for l in lista(cur, "l.ativo AND l.whatsapp AND NOT p.whatsapp_bloqueado AND l.inicio <= %s", (agora,)):
        v = ultima_ate(l, agora)
        if v and (not l["whatsapp_ate"] or v > l["whatsapp_ate"]) and v >= agora - ATRASO_WHATSAPP:
            saida.append((l, v))
    saida.sort(key=lambda x: x[1])
    return saida


def contar_whatsapp(cur):
    return len(pendentes_whatsapp(cur))


# ---------- Telegram ----------

def codigo(cur, pid):
    """código do paciente para o link do robô (criado na primeira vez)"""
    cur.execute("SELECT telegram_codigo FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    if r and r[0]:
        return r[0]
    novo = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    cur.execute("UPDATE paciente SET telegram_codigo = %s WHERE id = %s", (novo, pid))
    return novo


def link_telegram(cfg, cod):
    bot = cfg.get("telegram", {}).get("bot")
    return f"https://t.me/{bot}?start={cod}" if bot and cod else None


def telegram_pronto(cfg):
    return bool(cfg.get("telegram", {}).get("token") and cfg.get("telegram", {}).get("bot"))


def robo(token):
    """confere o token no Telegram e devolve o nome de usuário do robô"""
    token = (token or "").strip()
    if not re.fullmatch(r"\d{5,15}:[\w-]{20,}", token):
        raise checkin.ErroGoogle("Esse token está incompleto. Copie da mensagem do @BotFather o trecho inteiro "
                                 "parecido com 1234567890:AAH... (números, dois-pontos e letras, sem espaços).")
    falha = None
    for tentativa in range(3):   # a conexão com o Telegram às vezes demora: tenta até 3 vezes
        try:
            with urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=45) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("ok"):
                return d["result"]["username"]
            raise checkin.ErroGoogle("O Telegram não aceitou esse token.")
        except HTTPError as e:
            if e.code in (401, 404):
                raise checkin.ErroGoogle("O Telegram não aceitou esse token: ele está errado ou foi trocado no @BotFather. "
                                         "Copie de novo o trecho parecido com 1234567890:AAH...")
            falha = e
        except (OSError, ValueError) as e:
            falha = e
        _time.sleep(2)
    raise SemConexao("A internet demorou demais para falar com o Telegram (o token pode estar certo). "
                     f"Tente salvar de novo daqui a pouco. Detalhe: {falha}")


class SemConexao(checkin.ErroGoogle):
    """o Telegram não respondeu (internet), diferente de token errado"""


# ---------- script do Google ----------

def script_pronto(cfg):
    ck = cfg.get("checkin", {})
    return bool(ck.get("url") and ck.get("chave")) and int(ck.get("versao") or 0) >= VERSAO


def _iso(d):
    return agenda._local_iso(d)


def _item(cfg, l, agora):
    ini, fim = agora - timedelta(hours=7), agora + timedelta(days=DIAS_A_FRENTE)
    item = {"id": l["id"], "texto": texto_final(cfg, l, "telegram"),
            "telegram": l["telegram_chat"] if l["telegram"] and l["telegram_chat"] else "",
            "email": l["email"].strip() if l["email_ligado"] and checkin.email_valido(l["email"]) else "",
            "ocorrencias": [_iso(v) for v in vezes(l, ini, fim)]}
    if l["google"] and checkin.email_valido(l["email"]):
        g = {"email": l["email"].strip(), "inicio": _iso(l["inicio"]), "fim": _iso(l["inicio"] + timedelta(minutes=15)),
             "repetir": l["repetir"], "ate": _iso(datetime.combine(l["ate"], time(23, 59))) if l.get("ate") else "",
             "titulo": "Lembrete: " + texto_final(cfg, l, "whatsapp").split("\n")[0][:90],
             "descricao": texto_final(cfg, l, "google")}
        g["hash"] = hashlib.sha1(json.dumps(g, sort_keys=True).encode()).hexdigest()[:16]
        item["google"] = g
    if not (item["telegram"] or item["email"] or item.get("google")):
        return None
    return item


def sincronizar(con, cfg, desvincular=None):
    """manda ao script a lista dos lembretes automáticos e traz de volta os envios e os vínculos do Telegram.
    Devolve o estado (ou levanta checkin.ErroGoogle)."""
    global _ultima_sinc, aviso
    if not script_pronto(cfg):
        return None
    cur = con.cursor()
    agora = datetime.now()
    itens = [i for i in (_item(cfg, l, agora) for l in lista(cur, "l.ativo")) if i]
    ck = cfg["checkin"]
    corpo = {"chave": ck["chave"], "acao": "lembretes", "itens": itens,
             "telegram_token": cfg.get("telegram", {}).get("token", ""),
             "remetente": cfg["agenda"].get("profissional") or "",
             "whatsapp": checkin.whatsapp_prof(cfg),
             "assunto": cfg.get("telegram", {}).get("email_assunto") or "Lembrete do seu nutricionista"}
    if desvincular:
        corpo["desvincular"] = desvincular
    try:
        r = checkin._postar(ck["url"], corpo)
    except checkin.ErroGoogle as e:
        aviso = str(e)
        _ultima_sinc = _time.time()
        raise
    if r.get("erro"):
        aviso = {"acao": "o script do Google está desatualizado (precisa da versão 7)",
                 "ocupado": "o script do Google estava ocupado; tente de novo"}.get(r["erro"], r["erro"])
        _ultima_sinc = _time.time()
        raise checkin.ErroGoogle(f"Os lembretes automáticos não foram atualizados: {aviso}.")
    registrar(cur, r)
    con.commit()
    _ultima_sinc = _time.time()
    aviso = ("; ".join(f"convite do Google Agenda não criado ({e['erro']})" for e in r.get("erros_google", [])) or None)
    return r


def sincronizar_se_preciso(con, cfg, horas=6):
    """com o sistema aberto: atualiza o script de tempos em tempos (para ele ter sempre os próximos 90 dias)"""
    if not script_pronto(cfg) or _time.time() - _ultima_sinc < horas * 3600:
        return None
    try:
        return sincronizar(con, cfg)
    except checkin.ErroGoogle:
        return None


def registrar(cur, estado):
    """grava os envios feitos pelo script e os vínculos do Telegram"""
    for e in estado.get("log", []):
        try:
            vez = datetime.fromisoformat(e["vez"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        cur.execute("""INSERT INTO lembrete_envio (lembrete_id, canal, ocorrencia, erro, feito_em)
                       SELECT %s, %s, %s, %s, %s WHERE EXISTS (SELECT 1 FROM lembrete_paciente WHERE id = %s)
                       ON CONFLICT (lembrete_id, canal, ocorrencia) DO NOTHING""",
                    (e.get("id"), e.get("canal"), vez, e.get("erro") or None, vez, e.get("id")))
    for cod, v in (estado.get("telegram") or {}).items():
        if v.get("parou"):
            cur.execute("UPDATE paciente SET telegram_chat = NULL, telegram_desde = NULL WHERE telegram_codigo = %s", (cod,))
        else:
            em = datetime.fromisoformat(v["em"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None) if v.get("em") else None
            cur.execute("""UPDATE paciente SET telegram_chat = %s, telegram_desde = coalesce(telegram_desde, %s)
                           WHERE telegram_codigo = %s AND telegram_chat IS DISTINCT FROM %s""", (str(v["chat"]), em, cod, str(v["chat"])))


def historico(cur, pid, limite=12):
    cur.execute("""SELECT e.feito_em, e.canal, e.ocorrencia, e.erro, l.texto FROM lembrete_envio e
                   JOIN lembrete_paciente l ON l.id = e.lembrete_id WHERE l.paciente_id = %s
                   ORDER BY e.feito_em DESC LIMIT %s""", (pid, limite))
    return [dict(zip(["feito_em", "canal", "ocorrencia", "erro", "texto"], r)) for r in cur.fetchall()]
