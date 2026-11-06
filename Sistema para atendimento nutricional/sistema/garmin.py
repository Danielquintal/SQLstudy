"""Importação de dados do Garmin por arquivo (a API oficial da Garmin não está aceitando novos acessos).

O paciente exporta e manda o arquivo; o sistema lê e guarda (sql/21_garmin.sql):
  - Planilha de atividades (connect.garmin.com › Atividades › Exportar CSV): treinos, em português, inglês ou espanhol.
  - "Exportar seus dados" (garmin.com › Conta › Gerenciamento de dados), um .zip: treinos (summarizedActivities),
    resumo de cada dia com passos, meta, FC de repouso e calorias ativas (UDSFile) e sono (sleepData).
  - Os .json soltos de dentro desse .zip também servem.
Reimportar o mesmo arquivo atualiza (não duplica).
"""
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone

TIPOS = {   # tipo do Garmin -> nome em português
    "running": "Corrida", "treadmill_running": "Corrida na esteira", "trail_running": "Trail", "track_running": "Corrida na pista",
    "cycling": "Ciclismo", "road_biking": "Ciclismo", "mountain_biking": "Mountain bike", "indoor_cycling": "Bicicleta indoor",
    "virtual_ride": "Ciclismo virtual", "lap_swimming": "Natação (piscina)", "open_water_swimming": "Natação (águas abertas)",
    "swimming": "Natação", "walking": "Caminhada", "hiking": "Trilha", "strength_training": "Musculação",
    "fitness_equipment": "Academia", "cardio": "Cardio", "hiit": "HIIT", "yoga": "Yoga", "pilates": "Pilates",
    "elliptical": "Elíptico", "indoor_rowing": "Remo indoor", "rowing": "Remo", "soccer": "Futebol", "tennis": "Tênis",
    "multi_sport": "Multiesporte", "triathlon": "Triatlo", "other": "Outra",
}
# cabeçalhos da planilha (sem acento, minúsculos) em português, inglês e espanhol
COLUNAS = {
    "tipo": ("tipo de atividade", "activity type", "tipo de actividad"),
    "data": ("data", "date", "fecha"),
    "titulo": ("titulo", "title", "nome", "nombre"),
    "distancia": ("distancia", "distance"),
    "calorias": ("calorias", "calories"),
    "tempo": ("tempo", "time", "duracao", "duration", "tiempo", "tempo decorrido"),
    "fc_media": ("fc media", "avg hr", "frecuencia cardiaca media", "fc med", "fc med."),
    "fc_max": ("fc maxima", "fc max", "max hr", "frecuencia cardiaca maxima", "fc max."),
    "passos": ("passos", "steps", "pasos"),
    "subida": ("subida total", "total ascent", "ganho total", "ascenso total", "ganho de elevacao"),
}


class ErroGarmin(Exception):
    pass


def _norm(t):
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().strip().lower()


def _num(s):
    """'1,234.5' / '1.234,5' / '5,03' / '--' -> float ou None"""
    s = str(s if s is not None else "").strip().replace("\xa0", "").replace(" ", "")
    if not s or s in ("--", "-") or not re.search(r"\d", s):
        return None
    s = re.sub(r"[^\d.,-]", "", s)
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", "") if len(partes) > 2 or (len(partes[-1]) == 3 and len(partes[0]) <= 3 and partes[0] != "0") else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _segundos(s):
    """'01:02:03', '45:12', '00:45:12.3', '1:02:03,5' -> segundos"""
    s = str(s or "").strip()
    if not s or s == "--":
        return None
    partes = s.replace(",", ".").split(":")
    try:
        v = [float(x) for x in partes]
    except ValueError:
        return None
    seg = 0
    for x in v:
        seg = seg * 60 + x
    return int(round(seg))


def _tipo(t):
    t = str(t or "").strip()
    return TIPOS.get(_norm(t).replace(" ", "_"), t[:1].upper() + t[1:] if t else "Atividade")


def _id(*partes):
    return "h" + hashlib.sha1("|".join(str(p) for p in partes).encode()).hexdigest()[:16]


# ---------- planilha (Exportar CSV) ----------

def ler_csv(texto):
    texto = texto.lstrip("﻿")
    try:
        dialeto = csv.Sniffer().sniff(texto[:4000], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    linhas = list(csv.reader(io.StringIO(texto), dialeto))
    if not linhas:
        raise ErroGarmin("a planilha está vazia")
    cab = [_norm(c) for c in linhas[0]]
    idx = {}
    for campo, nomes in COLUNAS.items():
        for i, c in enumerate(cab):
            if c in nomes:
                idx[campo] = i
                break
    if "data" not in idx or "tipo" not in idx:
        raise ErroGarmin("não reconheci a planilha: precisa ter as colunas de tipo de atividade e data "
                         "(exporte em connect.garmin.com › Atividades › Exportar CSV)")
    atividades = []
    for l in linhas[1:]:
        g = lambda c: l[idx[c]] if c in idx and idx[c] < len(l) else ""
        quando = _data_hora(g("data"))
        if not quando:
            continue
        tipo = _tipo(g("tipo"))
        dist = _num(g("distancia"))
        if dist is not None:
            # natação vem em metros; o resto, em km (unidade métrica)
            dist = dist if ("nata" in _norm(tipo) or "swim" in _norm(g("tipo"))) and dist > 20 else dist * 1000
        atividades.append({"id_externo": _id(quando.isoformat(), tipo, g("tempo")), "inicio": quando, "tipo": tipo,
                           "titulo": g("titulo").strip() or None, "duracao_s": _segundos(g("tempo")),
                           "distancia_m": round(dist, 1) if dist is not None else None,
                           "calorias": _int(_num(g("calorias"))), "fc_media": _int(_num(g("fc_media"))),
                           "fc_max": _int(_num(g("fc_max"))), "passos": _int(_num(g("passos"))),
                           "subida_m": _num(g("subida"))})
    return atividades


def _int(v):
    return int(round(v)) if v is not None else None


def _data_hora(s):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


# ---------- "Exportar seus dados" (.zip / .json) ----------

def _ms(v):
    """data em milissegundos desde 1970 (como o Garmin exporta) -> datetime local do arquivo"""
    try:
        return datetime(1970, 1, 1) + timedelta(milliseconds=float(v))
    except (TypeError, ValueError, OverflowError):
        return None


def _dia(v):
    if isinstance(v, dict):
        v = v.get("date") or v.get("calendarDate")
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _lista(dados, chave=None):
    """os arquivos vêm como [ {...}, ... ] ou [ {"summarizedActivitiesExport": [...]} ]"""
    if isinstance(dados, dict):
        dados = [dados]
    saida = []
    for x in dados or []:
        if isinstance(x, dict) and chave and isinstance(x.get(chave), list):
            saida += x[chave]
        elif isinstance(x, dict):
            saida.append(x)
    return saida


def ler_atividades_json(dados):
    atividades = []
    for a in _lista(dados, "summarizedActivitiesExport"):
        quando = _ms(a.get("startTimeLocal")) or _ms(a.get("beginTimestamp"))
        if not quando:
            continue
        dur = a.get("duration") or a.get("elapsedDuration")
        dur_s = (dur / 1000 if dur and dur > 86400 * 2 else dur) if dur else None      # vem em milissegundos
        dist, em_cm = a.get("distance"), False
        if dist and dur_s and dist / dur_s > 15:                                         # vem em centímetros
            dist, em_cm = dist / 100, True
        subida = a.get("elevationGain")
        if subida and (em_cm or (dist and subida > dist)):                               # centímetros também
            subida = subida / 100
        atividades.append({"id_externo": str(a.get("activityId") or _id(quando.isoformat(), a.get("activityType"))),
                           "inicio": quando, "tipo": _tipo(a.get("activityType") or a.get("sportType")),
                           "titulo": a.get("name"), "duracao_s": _int(dur_s), "distancia_m": round(dist, 1) if dist else None,
                           "calorias": _int(a.get("calories")), "fc_media": _int(a.get("avgHr")), "fc_max": _int(a.get("maxHr")),
                           "passos": _int(a.get("steps")), "subida_m": round(subida, 1) if subida else None})
    return atividades


def ler_dias_json(dados):
    dias = {}
    for d in _lista(dados):
        dia = _dia(d.get("calendarDate"))
        if not dia:
            continue
        x = dias.setdefault(dia, {"dia": dia})
        if "totalSteps" in d:
            x.update(passos=_int(d.get("totalSteps")), meta_passos=_int(d.get("dailyStepGoal")),
                     fc_repouso=_int(d.get("restingHeartRate")), calorias_ativas=_int(d.get("activeKilocalories")))
        if any(k in d for k in ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds")):
            prof, lev, rem = (d.get(k) or 0 for k in ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds"))
            total = prof + lev + rem
            if total:
                x.update(sono_min=round(total / 60), sono_profundo_min=round(prof / 60), sono_rem_min=round(rem / 60))
    return list(dias.values())


def _json_arquivo(nome, conteudo, saida):
    try:
        dados = json.loads(conteudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return
    n = nome.lower()
    if "summarizedactivities" in n:
        saida["atividades"] += ler_atividades_json(dados)
    elif "udsfile" in n or "sleepdata" in n or "sleep" in n:
        for d in ler_dias_json(dados):
            atual = next((x for x in saida["dias"] if x["dia"] == d["dia"]), None)
            (atual.update(d) if atual else saida["dias"].append(d))


def ler(nome, conteudo):
    """arquivo enviado -> {"atividades": [...], "dias": [...]}; ErroGarmin se não for um arquivo do Garmin"""
    saida = {"atividades": [], "dias": []}
    n = (nome or "").lower()
    if n.endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
        except zipfile.BadZipFile:
            raise ErroGarmin("o arquivo .zip está corrompido") from None
        for info in z.infolist():
            if info.filename.lower().endswith(".json") and info.file_size < 200 * 1024 * 1024:
                _json_arquivo(info.filename, z.read(info), saida)
            elif info.filename.lower().endswith(".csv"):
                try:
                    saida["atividades"] += ler_csv(z.read(info).decode("utf-8-sig", "replace"))
                except ErroGarmin:
                    pass
    elif n.endswith(".json"):
        _json_arquivo(n, conteudo, saida)
        if not (saida["atividades"] or saida["dias"]):      # nome diferente: tenta os dois formatos
            dados = json.loads(conteudo.decode("utf-8-sig"))
            saida["atividades"] = ler_atividades_json(dados)
            saida["dias"] = ler_dias_json(dados)
    elif n.endswith(".csv"):
        for cod in ("utf-8-sig", "latin-1"):
            try:
                saida["atividades"] = ler_csv(conteudo.decode(cod))
                break
            except UnicodeDecodeError:
                continue
    elif n.endswith((".fit", ".gpx", ".tcx")):
        raise ErroGarmin("arquivo de um treino só (.fit/.gpx/.tcx) ainda não é lido: exporte a planilha de atividades (CSV)")
    else:
        raise ErroGarmin("mande a planilha .csv de atividades ou o .zip de “Exportar seus dados”")
    if not (saida["atividades"] or saida["dias"]):
        raise ErroGarmin("não encontrei treinos, passos ou sono neste arquivo")
    return saida


# ---------- banco ----------

CAMPOS_AT = ["id_externo", "inicio", "tipo", "titulo", "duracao_s", "distancia_m", "calorias", "fc_media", "fc_max",
             "passos", "subida_m"]
CAMPOS_DIA = ["passos", "meta_passos", "sono_min", "sono_profundo_min", "sono_rem_min", "fc_repouso", "calorias_ativas"]


def gravar(cur, pid, dados, fonte="garmin"):
    """grava o que foi lido; devolve (treinos novos, treinos atualizados, dias)"""
    novos = atual = 0
    for a in dados["atividades"]:
        cur.execute(f"""INSERT INTO atividade_externa (paciente_id, fonte, {', '.join(CAMPOS_AT)})
                        VALUES (%s, %s, {', '.join(['%s'] * len(CAMPOS_AT))})
                        ON CONFLICT (paciente_id, fonte, id_externo) DO UPDATE SET
                        {', '.join(f'{c} = EXCLUDED.{c}' for c in CAMPOS_AT[1:])}, importado_em = now()
                        RETURNING (xmax = 0)""", [pid, fonte] + [a.get(c) for c in CAMPOS_AT])
        if cur.fetchone()[0]:
            novos += 1
        else:
            atual += 1
    for d in dados["dias"]:
        cols = [c for c in CAMPOS_DIA if d.get(c) is not None]
        if not cols:
            continue
        cur.execute(f"""INSERT INTO diario_externo (paciente_id, fonte, dia, {', '.join(cols)})
                        VALUES (%s, %s, %s, {', '.join(['%s'] * len(cols))})
                        ON CONFLICT (paciente_id, fonte, dia) DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in cols)}""",
                    [pid, fonte, d["dia"]] + [d[c] for c in cols])
    return novos, atual, len(dados["dias"])


def resumo(cur, pid, dias=28):
    """para a ficha: últimas 4 semanas (treinos, minutos, km, passos, sono) e os últimos treinos"""
    cur.execute("SELECT max(inicio)::date, count(*) FROM atividade_externa WHERE paciente_id = %s", (pid,))
    ult_at, n_at = cur.fetchone()
    cur.execute("SELECT max(dia), count(*) FROM diario_externo WHERE paciente_id = %s", (pid,))
    ult_dia, n_dia = cur.fetchone()
    if not (n_at or n_dia):
        return None
    fim = max(x for x in (ult_at, ult_dia) if x)            # conta até o último dado do arquivo, não até hoje
    ini = fim - timedelta(days=dias - 1)
    cur.execute("""SELECT count(*), coalesce(sum(duracao_s), 0), coalesce(sum(distancia_m), 0), avg(fc_media)
                   FROM atividade_externa WHERE paciente_id = %s AND inicio::date BETWEEN %s AND %s""", (pid, ini, fim))
    n, seg, metros, fc = cur.fetchone()
    cur.execute("""SELECT tipo, count(*), sum(duracao_s) FROM atividade_externa
                   WHERE paciente_id = %s AND inicio::date BETWEEN %s AND %s GROUP BY tipo ORDER BY 2 DESC""", (pid, ini, fim))
    por_tipo = [{"tipo": t, "n": q, "min": round((s or 0) / 60)} for t, q, s in cur.fetchall()]
    cur.execute("""SELECT avg(passos), avg(meta_passos), avg(sono_min), avg(fc_repouso), count(passos),
                          count(*) FILTER (WHERE passos >= meta_passos)
                   FROM diario_externo WHERE paciente_id = %s AND dia BETWEEN %s AND %s""", (pid, ini, fim))
    passos, meta, sono, fcr, dias_passos, dias_meta = cur.fetchone()
    cur.execute("""SELECT inicio, tipo, titulo, duracao_s, distancia_m, calorias, fc_media FROM atividade_externa
                   WHERE paciente_id = %s ORDER BY inicio DESC LIMIT 8""", (pid,))
    ultimos = [dict(zip(["inicio", "tipo", "titulo", "duracao_s", "distancia_m", "calorias", "fc_media"], r)) for r in cur.fetchall()]
    sem = dias / 7
    return {"ini": ini, "fim": fim, "n_atividades": n_at, "n_dias": n_dia,
            "treinos_semana": round(n / sem, 1), "min_semana": round(seg / 60 / sem), "km_semana": round(float(metros) / 1000 / sem, 1),
            "fc_media": round(float(fc)) if fc else None, "por_tipo": por_tipo,
            "passos": round(float(passos)) if passos else None, "meta_passos": round(float(meta)) if meta else None,
            "dias_passos": dias_passos, "dias_meta": dias_meta,
            "sono_h": round(float(sono) / 60, 1) if sono else None, "fc_repouso": round(float(fcr)) if fcr else None,
            "ultimos": ultimos}
