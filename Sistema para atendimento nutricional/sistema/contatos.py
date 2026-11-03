"""Lembretes do dia e mensagens de WhatsApp com texto pronto (o envio é sempre feito por você, no WhatsApp).

As mensagens ficam em sistema/config.json, editáveis na tela Configuração.
"""
import json, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

CONFIG = Path(__file__).resolve().parent / "config.json"
PADRAO = {
    "retorno_dias_antes": 1,
    "mensagens": {
        "retorno": "Olá, {primeiro_nome}! Passando para lembrar da sua consulta {quando} ({data_retorno}). "
                   "Se precisar remarcar, é só me avisar por aqui. Daniel Quintal, nutricionista",
        "evolucao": "Olá, {primeiro_nome}! Sua avaliação de {data_avaliacao} já está na sua página de evolução, "
                    "com os gráficos atualizados: {link_evolucao}",
        "aniversario": "Feliz aniversário, {primeiro_nome}! Desejo um ano cheio de saúde e conquistas. "
                       "Um abraço, Daniel Quintal",
        "livre": "Olá, {primeiro_nome}! ",
    },
}
TITULOS = {"retorno": "Lembrete de retorno", "evolucao": "Link da evolução", "aniversario": "Aniversário",
           "livre": "Mensagem livre"}
VARIAVEIS = {
    "{primeiro_nome}": "primeiro nome do paciente",
    "{nome}": "nome completo",
    "{data_retorno}": "data da próxima consulta",
    "{quando}": "hoje, amanhã ou o dia da semana da consulta",
    "{data_avaliacao}": "data da última avaliação",
    "{link_evolucao}": "link publicado da página de evolução",
}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def carregar():
    cfg = json.loads(json.dumps(PADRAO))
    try:
        salvo = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return cfg
    cfg.update({k: v for k, v in salvo.items() if k in PADRAO and k != "mensagens"})
    cfg["mensagens"].update({k: v for k, v in salvo.get("mensagens", {}).items() if k in TITULOS})
    return cfg


def salvar(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def telefone_whatsapp(tel):
    """número no formato do WhatsApp (55 + DDD + número) ou None se não der para usar"""
    d = re.sub(r"\D", "", tel or "")
    if len(d) in (10, 11):
        d = "55" + d
    return d if len(d) in (12, 13) and d.startswith("55") else None


def quando(d, hoje=None):
    hoje = hoje or date.today()
    if d == hoje:
        return "hoje"
    if d == hoje + timedelta(days=1):
        return "amanhã"
    return f"na {DIAS[d.weekday()]}" if d.weekday() < 5 else f"no {DIAS[d.weekday()]}"


def mensagem(cfg, tipo, p, extra=None):
    """texto da mensagem com as variáveis trocadas pelos dados do paciente"""
    v = {"{primeiro_nome}": p["nome"].split()[0].title(), "{nome}": p["nome"]}
    if p.get("retorno_em"):
        v["{data_retorno}"] = p["retorno_em"].strftime("%d/%m")
        v["{quando}"] = quando(p["retorno_em"])
    v.update(extra or {})
    texto = cfg["mensagens"].get(tipo, "")
    for k, val in v.items():
        texto = texto.replace(k, val or "")
    return texto


def link_whatsapp(tel, texto):
    numero = telefone_whatsapp(tel)
    return f"https://wa.me/{numero}?text={quote(texto)}" if numero else None


def pendencias(cur, cfg, hoje=None):
    """o que há para mandar hoje: [(tipo, paciente, detalhe)]"""
    hoje = hoje or date.today()
    campos = "p.id, p.nome, p.telefone, p.retorno_em, p.data_nascimento"
    nomes = ["id", "nome", "telefone", "retorno_em", "data_nascimento"]
    lista = []

    # retornos de hoje até N dias, ainda não lembrados para essa data
    cur.execute(f"""SELECT {campos} FROM paciente p
        WHERE NOT p.whatsapp_bloqueado AND p.retorno_em BETWEEN %s AND %s
          AND NOT EXISTS (SELECT 1 FROM contato c WHERE c.paciente_id = p.id AND c.tipo = 'retorno'
                          AND c.referencia = p.retorno_em::text)
        ORDER BY p.retorno_em, p.nome""", (hoje, hoje + timedelta(days=int(cfg.get("retorno_dias_antes", 1)))))
    for r in cur.fetchall():
        p = dict(zip(nomes, r))
        lista.append(("retorno", p, f"Consulta {quando(p['retorno_em'], hoje)}, {p['retorno_em']:%d/%m}"))

    # aniversário hoje
    cur.execute(f"""SELECT {campos} FROM paciente p
        WHERE NOT p.whatsapp_bloqueado AND extract(month FROM p.data_nascimento) = %s
          AND extract(day FROM p.data_nascimento) = %s
          AND NOT EXISTS (SELECT 1 FROM contato c WHERE c.paciente_id = p.id AND c.tipo = 'aniversario'
                          AND c.referencia = %s)
        ORDER BY p.nome""", (hoje.month, hoje.day, str(hoje.year)))
    for r in cur.fetchall():
        p = dict(zip(nomes, r))
        lista.append(("aniversario", p, f"Faz {hoje.year - p['data_nascimento'].year} anos hoje"))
    return lista


def referencia(tipo, p, hoje=None):
    """o que identifica o lembrete, para não repetir (a data do retorno, o ano do aniversário)"""
    if tipo == "retorno" and p.get("retorno_em"):
        return p["retorno_em"].isoformat()
    if tipo == "aniversario":
        return str((hoje or date.today()).year)
    return None
