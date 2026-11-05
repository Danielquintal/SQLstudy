"""Assistente dos lembretes: entende uma frase em português e tira dela o lembrete (o quê, dia, hora, paciente,
repetição). Funciona só neste computador, sem internet e sem inteligência artificial: são regras para as formas
comuns de falar ("amanhã às 10", "daqui a 2 semanas", "toda segunda", "dia 15", "15/11", "de tarde"...).

Exemplo: interpretar("me lembra de pedir exames da Alanis daqui a 2 semanas às 10h", pacientes)
  -> texto "Pedir exames da Alanis", dia = hoje + 14, hora 10:00, paciente Alanis ..., não repete.
"""
import calendar
import re
import unicodedata
from datetime import date, datetime, time, timedelta

HORA_PADRAO = time(9, 0)
NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
           "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30,
           "quarenta": 40, "quarenta e cinco": 45, "sessenta": 60, "noventa": 90}
NUM = r"(\d{1,3}|" + "|".join(sorted(NUMEROS, key=len, reverse=True)) + r")"
DIAS_SEMANA = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
SEMANA = r"(segunda|terca|quarta|quinta|sexta|sabado|domingo)"
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
MES = r"(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
REPETIR_ROTULO = {"diario": "todo dia", "semanal": "toda semana", "quinzenal": "a cada 15 dias", "mensal": "todo mês"}
PARTICULAS = {"da", "de", "do", "das", "dos", "e"}
NOMES_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _sem_acento(s):
    """minúsculas e sem acento, com o MESMO tamanho do texto original (para recortar o original pelas posições)"""
    saida = []
    for ch in s:
        b = unicodedata.normalize("NFKD", ch)[:1] or ch
        b = b.lower()
        saida.append(b if len(b) == 1 else ch)
    return "".join(saida)


def _numero(s):
    return int(s) if s.isdigit() else NUMEROS[s]


def _mais_meses(d, n):
    m = d.month - 1 + n
    ano, mes = d.year + m // 12, m % 12 + 1
    return d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))


def _proximo_dia_semana(hoje, dia, incluir_hoje=False):
    falta = (dia - hoje.weekday()) % 7
    if falta == 0 and not incluir_hoje:
        falta = 7
    return hoje + timedelta(days=falta)


def _data_valida(ano, mes, dia):
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


class _Frase:
    def __init__(self, frase):
        self.orig = frase
        self.n = _sem_acento(frase)
        self.usado = [False] * len(frase)

    def achar(self, padrao):
        """primeira ocorrência do padrão que não encosta em parte já usada; marca como usada"""
        for m in re.finditer(padrao, self.n):
            if not any(self.usado[m.start():m.end()]):
                for i in range(m.start(), m.end()):
                    self.usado[i] = True
                return m
        return None

    def resto(self):
        return "".join(" " if u else c for c, u in zip(self.orig, self.usado))


def _limpar_texto(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", s)
    ligas = r"(?:,|\.|;|:|-|de|que|e|para|pra|pro|as|às|a|à|o|no|na|em|do|da|ao|aos|pelas|por volta d[ae]s?)"
    for _ in range(4):
        s = re.sub(rf"^(?:{ligas})(?:\s+|$)", "", s, flags=re.I).strip()
        s = re.sub(rf"(?:^|\s+){ligas}$", "", s, flags=re.I).strip()
        s = s.strip(" ,.;:-")
    return s[:1].upper() + s[1:]


def _achar_paciente(n, pacientes):
    """procura o nome de um paciente na frase (nome completo, nome e sobrenome ou só o primeiro nome).
    Devolve (paciente, outros com o mesmo nome achado)."""
    achados = []   # (tamanho do trecho, id, nome)
    for pid, nome in pacientes:
        partes = _sem_acento(nome).split()
        if not partes:
            continue
        fortes = [p for p in partes if p not in PARTICULAS]
        variantes = {" ".join(partes), " ".join(fortes)}
        if len(fortes) > 1:
            variantes |= {f"{fortes[0]} {fortes[-1]}", f"{fortes[0]} {fortes[1]}"}
        variantes.add(fortes[0] if fortes else partes[0])
        melhor = 0
        for v in variantes:
            if len(v) < 3:
                continue
            if re.search(r"(?<![\w])" + r"\s+".join(map(re.escape, v.split())) + r"(?![\w])", n):
                melhor = max(melhor, len(v))
        if melhor:
            achados.append((melhor, pid, nome))
    if not achados:
        return None, []
    maior = max(a[0] for a in achados)
    topo = [(pid, nome) for t, pid, nome in achados if t == maior]
    if len(topo) == 1:
        return topo[0], []
    return None, sorted(n for _, n in topo)


def interpretar(frase, pacientes=(), agora=None):
    """tira o lembrete da frase. pacientes: [(id, nome)]. Devolve um dicionário com texto, data (AAAA-MM-DD ou ""),
    hora (HH:MM), repetir, paciente/paciente_id, e o que faltou ou ficou em dúvida."""
    agora = (agora or datetime.now()).replace(second=0, microsecond=0)
    hoje = agora.date()
    f = _Frase(frase or "")
    avisos = []

    # pedido no começo: "me lembra de", "lembrar de", "lembrete:", "não me deixa esquecer de"
    f.achar(r"^\s*(?:por favor\s*,?\s*)?(?:(?:me\s+)?lembr(?:a|e|ar|ete)(?:[\s-]*me)?|nao\s+(?:me\s+)?deix(?:a|e|ar)\s+(?:eu\s+)?esquecer)"
            r"(?:\s*:)?(?:\s+(?:de|que|do|da))?(?![\w])")

    # repetição
    repetir, dia_mes, dia_sem = "", None, None
    if m := f.achar(r"(?<![\w])tod[oa]s?\s+(?:os\s+)?dias?\s+(\d{1,2})(?![\w/])(?:\s+de\s+cada\s+mes)?"):
        repetir, dia_mes = "mensal", int(m.group(1))
    elif m := f.achar(rf"(?<![\w])tod[ao]s?\s+(?:as\s+|os\s+)?{SEMANA}s?(?:[\s-]*feiras?)?(?![\w])"):
        repetir, dia_sem = "semanal", DIAS_SEMANA.index(m.group(1))
    elif f.achar(r"(?<![\w])(?:a\s+cada\s+(?:15|quinze)\s+dias|de\s+(?:15|quinze)\s+em\s+(?:15|quinze)\s+dias|quinzenalmente"
                 r"|a\s+cada\s+(?:2|duas)\s+semanas)(?![\w])"):
        repetir = "quinzenal"
    elif f.achar(r"(?<![\w])(?:todos\s+os\s+dias|todo\s+dia|diariamente|a\s+cada\s+dia)(?![\w])"):
        repetir = "diario"
    elif f.achar(r"(?<![\w])(?:toda\s+semana|todas\s+as\s+semanas|semanalmente|uma\s+vez\s+por\s+semana|a\s+cada\s+(?:7|sete)\s+dias"
                 r"|a\s+cada\s+semana)(?![\w])"):
        repetir = "semanal"
    elif f.achar(r"(?<![\w])(?:todo\s+mes|todos\s+os\s+meses|mensalmente|uma\s+vez\s+por\s+mes|a\s+cada\s+mes)(?![\w])"):
        repetir = "mensal"

    # quando: "daqui a 2 semanas", "em 3 dias", "daqui a meia hora"
    dia, exato, hora = None, None, None
    if f.achar(r"(?<![\w])(?:daqui\s+(?:a\s+)?|em\s+|dentro\s+de\s+)meia\s+hora(?![\w])"):
        exato = agora + timedelta(minutes=30)
    elif m := f.achar(rf"(?<![\w])(?:daqui\s+(?:a\s+)?|em\s+|dentro\s+de\s+|apos\s+|depois\s+de\s+){NUM}\s+"
                      r"(minutos?|min|horas?|h|dias?|semanas?|mes|meses|anos?)(?![\w])"):
        q, u = _numero(m.group(1)), m.group(2)
        if u.startswith("min"):
            exato = agora + timedelta(minutes=q)
        elif u.startswith("h"):
            exato = agora + timedelta(hours=q)
        elif u.startswith("dia"):
            dia = hoje + timedelta(days=q)
        elif u.startswith("semana"):
            dia = hoje + timedelta(weeks=q)
        elif u.startswith("mes"):
            dia = _mais_meses(hoje, q)
        else:
            dia = _mais_meses(hoje, 12 * q)
    elif m := f.achar(r"(?<![\w])daqui\s+(?:a\s+)?(?:um|uma)\s+(semana|mes|ano)(?![\w])"):
        dia = {"semana": hoje + timedelta(weeks=1), "mes": _mais_meses(hoje, 1), "ano": _mais_meses(hoje, 12)}[m.group(1)]
    elif m := f.achar(r"(?<![\w])(?:(?:n?a\s+)?semana\s+que\s+vem|(?:n?a\s+)?proxima\s+semana|(?:n?o\s+)?mes\s+que\s+vem|(?:n?o\s+)?proximo\s+mes"
                      r"|(?:n?o\s+)?ano\s+que\s+vem|(?:n?o\s+)?proximo\s+ano)(?![\w])"):
        t = m.group(0)
        dia = hoje + timedelta(weeks=1) if "semana" in t else _mais_meses(hoje, 1 if "mes" in t else 12)

    if dia is None and exato is None:
        if f.achar(r"(?<![\w])depois\s+de\s+amanha(?![\w])"):
            dia = hoje + timedelta(days=2)
        elif f.achar(r"(?<![\w])amanha(?![\w])"):
            dia = hoje + timedelta(days=1)
        elif f.achar(r"(?<![\w])(?:hoje|hj)(?![\w])"):
            dia = hoje
    if dia is None and exato is None:
        # data escrita: 15/11, 15/11/2026, 15 de novembro, dia 15
        if m := f.achar(r"(?<![\w/])(?:(?:n?o\s+)?dia\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\w/])"):
            d_, m_, a_ = int(m.group(1)), int(m.group(2)), m.group(3)
            ano = (2000 + int(a_) if len(a_) == 2 else int(a_)) if a_ else hoje.year
            dia = _data_valida(ano, m_, d_)
            if dia and not a_ and dia < hoje:
                dia = _data_valida(ano + 1, m_, d_)
            if not dia:
                avisos.append(f"A data {m.group(0).strip()} não existe.")
        elif m := f.achar(rf"(?<![\w])(?:(?:n?o\s+)?dia\s+)?(\d{{1,2}})\s+de\s+{MES}(?:\s+de\s+(\d{{4}}))?(?![\w])"):
            mes = next(i + 1 for i, nm in enumerate(MESES) if nm.startswith(m.group(2)))
            ano = int(m.group(3)) if m.group(3) else hoje.year
            dia = _data_valida(ano, mes, int(m.group(1)))
            if dia and not m.group(3) and dia < hoje:
                dia = _data_valida(ano + 1, mes, int(m.group(1)))
            if not dia:
                avisos.append(f"A data “{m.group(0).strip()}” não existe.")
        elif m := f.achar(r"(?<![\w])(?:(?:n?o|para\s+o|pro)\s+)?dia\s+(\d{1,2})(?![\w/:h])"):
            d_ = int(m.group(1))
            dia = _data_valida(hoje.year, hoje.month, d_)
            if not dia or dia < hoje:
                prox = _mais_meses(hoje.replace(day=1), 1)
                dia = _data_valida(prox.year, prox.month, d_)
            if not dia:
                avisos.append(f"Não existe dia {d_} no mês.")
        elif m := f.achar(rf"(?<![\w])(?:(?:n[ao]|nest[ae]|ness[ae]|(?:n[ao]\s+)?proxim[ao])\s+){SEMANA}(?:[\s-]*feira)?(\s+que\s+vem)?(?![\w])"
                          rf"|(?<![\w]){SEMANA}(?:[\s-]*feira)(\s+que\s+vem)?(?![\w])"
                          rf"|(?<![\w]){SEMANA}(\s+que\s+vem)?(?=\s*(?:,|$|as\s|a\s|ao\s|\d))"):
            nome = m.group(1) or m.group(3) or m.group(5)
            dia = _proximo_dia_semana(hoje, DIAS_SEMANA.index(nome))

    # hora
    periodo = None
    if m := f.achar(r"(?<![\w])(?:(?:as|a|ao|pelas|por\s+volta\s+das)\s+)?(\d{1,2})(?::|h)(\d{2})(?:\s*(?:h|hs|horas))?(?![\w])"
                    r"(?:\s+(da\s+manha|da\s+tarde|da\s+noite))?"):
        hora, periodo = (int(m.group(1)), int(m.group(2))), m.group(3)
    elif m := f.achar(r"(?<![\w])(?:(?:as|pelas|por\s+volta\s+das)\s+)(\d{1,2})(?:\s*(?:h|hs|horas?))?(?![\w])(?:\s+(da\s+manha|da\s+tarde|da\s+noite))?"
                      r"|(?<![\w])(\d{1,2})\s*(?:h|hs|horas)(?![\w])(?:\s+(da\s+manha|da\s+tarde|da\s+noite))?"
                      r"|(?<![\w])(\d{1,2})\s+(da\s+manha|da\s+tarde|da\s+noite)(?![\w])"):
        h = m.group(1) or m.group(3) or m.group(5)
        periodo = m.group(2) or m.group(4) or m.group(6)
        hora = (int(h), 0)
        if not periodo and 1 <= hora[0] <= 6:
            hora = (hora[0] + 12, 0)   # "às 3" num dia de trabalho é 15h
    elif f.achar(r"(?<![\w])(?:a[os]?\s+)?meio[\s-]dia(?![\w])"):
        hora = (12, 0)
    elif f.achar(r"(?<![\w])(?:a\s+)?meia[\s-]noite(?![\w])"):
        hora = (0, 0)
    if hora and periodo and ("tarde" in periodo or "noite" in periodo) and hora[0] < 12:
        hora = (hora[0] + 12, hora[1])
    if not hora:
        if f.achar(r"(?<![\w])(?:de|pela|na|a)\s+manha(?:\s+cedo)?(?![\w])|(?<![\w])cedo(?![\w])"):
            hora = (9, 0)
        elif f.achar(r"(?<![\w])(?:de|pela|na|a|a\s+)\s*tarde(?![\w])"):
            hora = (14, 0)
        elif f.achar(r"(?<![\w])(?:de|pela|na|a|a\s+)\s*noite(?![\w])"):
            hora = (19, 0)
    if hora and not (0 <= hora[0] <= 23 and 0 <= hora[1] <= 59):
        avisos.append(f"A hora {hora[0]}:{hora[1]:02d} não existe.")
        hora = None

    # juntar dia e hora
    hora_padrao = False
    if exato:
        quando = exato
    else:
        dia_dito = dia is not None   # a frase disse o dia (hoje, amanhã, 15/11...)
        if dia is None:
            if dia_mes:
                dia = _data_valida(hoje.year, hoje.month, dia_mes)
                if not dia or dia < hoje:
                    prox = _mais_meses(hoje.replace(day=1), 1)
                    dia = _data_valida(prox.year, prox.month, min(dia_mes, calendar.monthrange(prox.year, prox.month)[1]))
            elif dia_sem is not None:
                dia = _proximo_dia_semana(hoje, dia_sem, incluir_hoje=True)
            elif hora or repetir:
                dia = hoje
        if dia is None:
            quando = None
        else:
            if hora:
                h = time(*hora)
            else:
                h, hora_padrao = HORA_PADRAO, True
            quando = datetime.combine(dia, h)
            if quando <= agora and dia == hoje:
                if hora_padrao:   # hoje, sem hora: daqui a pouco, na próxima hora cheia
                    quando = (agora + timedelta(hours=1)).replace(minute=0)
                elif not dia_dito:   # "às 10" (ou "toda segunda às 10") e já passou: a próxima vez
                    if dia_sem is not None:
                        quando += timedelta(weeks=1)
                    elif dia_mes:
                        quando = datetime.combine(_mais_meses(dia, 1), quando.time())
                    else:
                        quando += timedelta(days=1)
            if quando < agora:
                avisos.append("Esse dia e hora já passaram.")

    paciente, mesmo_nome = _achar_paciente(f.n, pacientes)
    if mesmo_nome:
        avisos.append("Há mais de um paciente com esse nome (" + ", ".join(mesmo_nome) + "): escolha no campo Paciente.")
    texto = _limpar_texto(f.resto())

    resumo = []
    if quando:
        resumo.append(f"{NOMES_SEMANA[quando.weekday()]}, {quando.strftime('%d/%m/%Y')} às {quando.strftime('%H:%M')}"
                      + (" (hora padrão)" if hora_padrao else ""))
    if repetir:
        resumo.append("repete " + REPETIR_ROTULO[repetir])
    if paciente:
        resumo.append(paciente[1])
    return {"texto": texto, "data": quando.date().isoformat() if quando else "", "hora": quando.strftime("%H:%M") if quando else "",
            "repetir": repetir, "paciente_id": paciente[0] if paciente else None, "paciente": paciente[1] if paciente else "",
            "mesmo_nome": mesmo_nome, "falta_dia": quando is None, "hora_padrao": hora_padrao, "resumo": resumo,
            "avisos": avisos}
