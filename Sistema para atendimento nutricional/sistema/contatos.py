"""Lembretes do dia e mensagens de WhatsApp com texto pronto (o envio é sempre feito por você, no WhatsApp).

As mensagens ficam em sistema/config.json, editáveis na tela Configuração.
"""
import json, os, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import checkin

CONFIG = Path(os.environ.get("SISTEMA_CONFIG") or Path(__file__).resolve().parent / "config.json")   # outro arquivo só nos testes
PADRAO = {
    "retorno_dias_antes": 1,
    # check-in pelo Formulário Google: url e chave do script; formulario = link com a marca no lugar do nome
    "checkin": {"url": "", "chave": "", "formulario": "", "marca": "NOME_DO_PACIENTE", "dias": 7, "ativo_dias": 90,
                "versao": 0,
                # e-mail automático, enviado pelo script do Google; quem não responde em N dias vai para o WhatsApp
                "email_ativo": False, "email_espera": 2, "email_remetente": "Daniel Quintal · Nutricionista",
                "email_assunto": "Seu check-in da semana, {primeiro_nome}",
                "email_texto": "Oi, {primeiro_nome}!\n\nChegou a hora do check-in da semana. São 2 minutinhos e me "
                               "ajudam muito a acompanhar você até a próxima consulta.\n\nUm abraço,\nDaniel Quintal"},
    # agenda: duração padrão, locais padrão e o e-mail de confirmação (o WhatsApp fica em mensagens > confirmacao)
    "agenda": {"duracao": 60, "local_presencial": "", "local_online": "", "profissional": "Daniel Quintal · Nutricionista",
               "google": False, "google_convidar": False, "google_mostrar": True,
               "email_assunto": "Consulta confirmada: {data_consulta} às {hora_consulta}",
               "email_texto": "Olá, {primeiro_nome}!\n\nSua consulta de nutrição está marcada para {dia_semana}, "
                              "{data_consulta}, às {hora_consulta}.\n{local_consulta}\n\nO convite vai anexo para "
                              "você salvar na sua agenda. Se precisar remarcar, é só responder este e-mail ou me "
                              "chamar no WhatsApp.\n\nAté lá!\nDaniel Quintal, nutricionista"},
    # robô do Telegram (lembretes dos pacientes); o assunto vale para os lembretes por e-mail
    "telegram": {"token": "", "bot": "", "email_assunto": "Lembrete do seu nutricionista"},
    # publicação das páginas dos pacientes pelo próprio sistema (Cloudflare Pages); vazio = fila do Claude
    "cloudflare": {"account_id": "", "token": "", "projeto": "res-athleticae", "url": ""},
    # acesso ao sistema de fora deste computador (Cloudflare Tunnel); senha guardada só como hash
    # totp_segredo: código do celular (2ª etapa); totp_pendente: enquanto você liga o app
    "remoto": {"dominio": "", "token_tunel": "", "tunel_nome": "", "senha_hash": "", "totp_segredo": "", "totp_pendente": ""},
    # cópia de segurança diária (sistema/copia_seguranca.py); a senha tranca a cópia que vai ao OneDrive
    "copia": {"senha": "", "pasta_nuvem": ""},
    "mensagens": {
        "confirmacao": "Olá, {primeiro_nome}! Sua consulta está marcada para {dia_semana}, {data_consulta}, às "
                       "{hora_consulta}. {local_consulta} Se precisar remarcar, é só me avisar por aqui. "
                       "Daniel Quintal, nutricionista",
        "leafq": "Olá, {primeiro_nome}! Para acompanhar sua saúde e sua disponibilidade de energia no esporte, "
                 "responda este questionário (uns 5 minutos, as respostas ficam só comigo): {link_leafq}",
        "retorno": "Olá, {primeiro_nome}! Passando para lembrar da sua consulta {quando} ({data_retorno}). "
                   "Se precisar remarcar, é só me avisar por aqui. Daniel Quintal, nutricionista",
        "evolucao": "Olá, {primeiro_nome}! Sua avaliação de {data_avaliacao} já está na sua página de evolução, "
                    "com os gráficos atualizados: {link_evolucao} . Para entrar: sua data de nascimento e o código "
                    "{codigo_acesso}.",
        "aniversario": "Feliz aniversário, {primeiro_nome}! Desejo um ano cheio de saúde e conquistas. "
                       "Um abraço, Daniel Quintal",
        "checkin": "Oi, {primeiro_nome}! Hora do check-in da semana: são 2 minutinhos e me ajudam muito a "
                   "acompanhar você até a próxima consulta. É só responder por este link: {link_checkin}",
        "livre": "Olá, {primeiro_nome}! ",
    },
}
TITULOS = {"confirmacao": "Confirmação de consulta", "retorno": "Lembrete de retorno", "checkin": "Pedido de check-in",
           "evolucao": "Link da evolução", "aniversario": "Aniversário", "leafq": "Questionário LEAF-Q (RED-S)",
           "livre": "Mensagem livre"}
ROTULOS = dict(TITULOS, checkin_email="Check-in por e-mail", confirmacao_email="Confirmação por e-mail",
               lembrete="Lembrete do paciente")   # histórico
VARIAVEIS = {
    "{primeiro_nome}": "primeiro nome do paciente",
    "{nome}": "nome completo",
    "{data_retorno}": "data da próxima consulta",
    "{quando}": "hoje, amanhã ou o dia da semana da consulta",
    "{data_avaliacao}": "data da última avaliação",
    "{link_evolucao}": "link publicado da página de evolução",
    "{codigo_acesso}": "código de acesso da página (o login é a data de nascimento)",
    "{link_checkin}": "link do formulário de check-in, já com o nome do paciente",
    "{link_leafq}": "link do questionário LEAF-Q, já com o nome da paciente",
    "{data_consulta}": "data da consulta agendada",
    "{hora_consulta}": "horário da consulta",
    "{dia_semana}": "dia da semana da consulta",
    "{local_consulta}": "endereço (presencial) ou link (online) da consulta",
}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def carregar():
    cfg = json.loads(json.dumps(PADRAO))
    try:
        salvo = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return cfg
    cfg.update({k: v for k, v in salvo.items() if k in PADRAO and k not in ("mensagens", "checkin", "agenda", "telegram", "cloudflare", "remoto", "copia")})
    cfg["telegram"].update(salvo.get("telegram", {}))
    cfg["cloudflare"].update(salvo.get("cloudflare", {}))
    cfg["remoto"].update(salvo.get("remoto", {}))
    cfg["copia"].update(salvo.get("copia", {}))
    cfg["checkin"].update(salvo.get("checkin", {}))
    cfg["agenda"].update(salvo.get("agenda", {}))
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
    v = {"{primeiro_nome}": p["nome"].split()[0].title(), "{nome}": p["nome"],
         "{link_checkin}": checkin.link_formulario(cfg, p["nome"]), "{link_leafq}": _link_leafq(cfg, p["nome"])}
    if p.get("retorno_em"):
        v["{data_retorno}"] = p["retorno_em"].strftime("%d/%m")
        v["{quando}"] = quando(p["retorno_em"])
    v.update(extra or {})
    texto = cfg["mensagens"].get(tipo, "")
    for k, val in v.items():
        texto = texto.replace(k, val or "")
    return texto


def _link_leafq(cfg, nome):
    import reds
    return reds.link_leafq(cfg, nome)


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

    # check-in: pacientes ativos (consulta nos últimos N dias ou retorno marcado) sem resposta nem pedido há uma semana.
    # Quem tem e-mail e o e-mail automático ligado recebe primeiro o e-mail; se não responder em N dias, vem para cá.
    if checkin.configurado(cfg):
        ck = cfg["checkin"]
        dias, espera, por_email = int(ck.get("dias", 7)), int(ck.get("email_espera", 2)), checkin.usa_email(cfg)
        cur.execute(f"""SELECT {campos}, p.email, p.checkin_dia,
                (SELECT max(respondido_em)::date FROM checkin k WHERE k.paciente_id = p.id AND NOT k.excluido),
                (SELECT max(feito_em)::date FROM contato c WHERE c.paciente_id = p.id AND c.tipo = 'checkin'),
                (SELECT max(feito_em)::date FROM contato c WHERE c.paciente_id = p.id AND c.tipo = 'checkin_email')
            FROM paciente p WHERE {checkin.ATIVOS} ORDER BY p.nome""",
                    {"hoje": hoje, "desde": hoje - timedelta(days=int(ck.get("ativo_dias", 90)))})
        for r in cur.fetchall():
            p = dict(zip(nomes, r[:len(nomes)]))
            email, ck_dia, respondeu, pedido, enviado = r[len(nomes):]
            ultimo = max([d for d in (respondeu, pedido) if d], default=None)
            if ck_dia is not None:
                # dia da semana escolhido: vale a partir do último desse dia (0 = domingo); igual ao script do Google
                marco = hoje - timedelta(days=((hoje.weekday() + 1) % 7 - ck_dia) % 7)
                if ultimo is not None and (marco - ultimo).days < dias:
                    continue   # respondeu ou recebeu o WhatsApp perto do dia marcado
            elif ultimo is not None and (hoje - ultimo).days < dias:
                continue   # respondeu ou recebeu o WhatsApp nesta semana
            if por_email and checkin.email_valido(email):
                # e-mail desta semana, depois da última resposta, há N dias ou mais: lembrar no WhatsApp
                if enviado and (not respondeu or enviado > respondeu) and espera <= (hoje - enviado).days < dias:
                    lista.append(("checkin", p, f"E-mail enviado em {enviado:%d/%m} e ainda sem resposta"))
                continue   # senão o e-mail automático cuida
            lista.append(("checkin", p, f"Último check-in em {respondeu:%d/%m}" if respondeu
                          else "Ainda não fez check-in"))
    return lista


def referencia(tipo, p, hoje=None):
    """o que identifica o lembrete, para não repetir (a data do retorno, o ano do aniversário)"""
    if tipo == "retorno" and p.get("retorno_em"):
        return p["retorno_em"].isoformat()
    if tipo == "aniversario":
        return str((hoje or date.today()).year)
    return None
