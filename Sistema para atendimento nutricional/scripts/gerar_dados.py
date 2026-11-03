"""Gera 02_dados.sql (INSERTs) a partir das planilhas do App Naive.

Uso:  python gerar_dados.py
Lê, da pasta Downloads:
  - pacientes_app_naive_02-11-2026.xlsx       -> tabela paciente
  - antropometria_pacientes_app_naive.json    -> tabela avaliacao (mesmos dados da aba "Avaliações",
                                               com o código do App Naive que liga cada avaliação ao paciente)
"""
import json, re, sys
from datetime import datetime
from pathlib import Path

import openpyxl

from campos import CAMPOS, TEXTO

DOWNLOADS = Path.home() / "Downloads"
PACIENTES_XLSX = DOWNLOADS / "pacientes_app_naive_02-11-2026.xlsx"
AVALIACOES_JSON = DOWNLOADS / "antropometria_pacientes_app_naive.json"
SAIDA = Path(__file__).resolve().parent.parent / "sql" / "02_dados.sql"

descartados = []


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def texto(v):
    v = str(v).strip() if v is not None else ""
    return v if v not in ("", "-") else None


def numero(v, onde=""):
    v = texto(v)
    if v is None:
        return None
    limpo = re.sub(r"\s*(Kg/L|kg/l|Kg|kg|%)$", "", v).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        descartados.append(f"{onde}: {v!r}")
        return None


def data(v, fmts=("%d/%m/%Y",)):
    v = texto(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    for f in fmts:
        try:
            return datetime.strptime(v, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def momento(v):
    """'29/10/2026 - 20:00:59' ou '2023-05-25 17:06:11' -> timestamp ISO"""
    v = texto(v)
    if v is None:
        return None
    for f in ("%d/%m/%Y - %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, f).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


# --- cadastro ---
wb = openpyxl.load_workbook(PACIENTES_XLSX, read_only=True)
linhas = list(wb.active.iter_rows(values_only=True))
cab = [str(c).strip() for c in linhas[0]]
cadastro = [dict(zip(cab, r)) for r in linhas[1:] if r and r[0]]

# --- avaliações, indexadas por (nome, modificado em) ---
json_pacs = json.load(open(AVALIACOES_JSON, encoding="utf-8"))["pacientes"]
por_chave = {(p["nome"].strip(), momento(p["atualizacao"])): p for p in json_pacs}

out = ["-- Gerado por gerar_dados.py em " + datetime.now().strftime("%d/%m/%Y %H:%M"),
       "SET client_encoding = 'UTF8';", "BEGIN;", "TRUNCATE avaliacao, paciente RESTART IDENTITY;"]
cols_av = ["paciente_id", "data_avaliacao"] + list(CAMPOS)
n_av, sem_par = 0, []

for pid, c in enumerate(cadastro, 1):
    nome = c["Nome do paciente"].strip()
    mod = momento(c.get("Modificado em"))
    pj = por_chave.get((nome, mod))
    if pj is None:
        sem_par.append(nome)
    genero = texto(c.get("Genero"))
    genero = genero[0].upper() if genero and genero[0].upper() in "MF" else None
    estado = texto(c.get("Estado"))
    vals = [pid, pj["link"] if pj else None, nome, texto(c.get("CPF")), texto(c.get("Telefone")),
            texto(c.get("Email")), genero, data(c.get("Data de Nascimento")), momento(c.get("Criado em")), mod,
            texto(c.get("Etiquetas")), texto(c.get("CEP")), texto(c.get("Endereço")), texto(c.get("Bairro")),
            texto(c.get("Cidade")), estado[:2].upper() if estado else None]
    out.append("INSERT INTO paciente (id, app_naive_id, nome, cpf, telefone, email, genero, data_nascimento, criado_em, "
               "modificado_em, etiquetas, cep, endereco, bairro, cidade, estado) VALUES ("
               + ", ".join(sql(v) for v in vals) + ");")

    for a in (pj or {}).get("avaliacoes") or []:
        d = data(a.get("dataAvaliacao"))
        if not d:
            continue
        m = re.match(r"([\d.]+)\s*\(([\d.]+)%\)", str(a.get("cmb", "")))
        a = dict(a, cmb_cm=m.group(1) if m else None, cmb_pct=m.group(2) if m else None)
        valores = [pid, d] + [texto(a.get(k)) if col in TEXTO else numero(a.get(k), f"{nome} {d} {col}")
                              for col, k in CAMPOS.items()]
        out.append(f"INSERT INTO avaliacao ({', '.join(cols_av)}) VALUES ({', '.join(sql(v) for v in valores)});")
        n_av += 1

out += ["SELECT setval('paciente_id_seq', (SELECT max(id) FROM paciente));",
        "SELECT setval('avaliacao_id_seq', (SELECT coalesce(max(id), 1) FROM avaliacao));", "COMMIT;"]
SAIDA.write_text("\n".join(out) + "\n", encoding="utf-8")

print(f"{len(cadastro)} pacientes, {n_av} avaliações -> {SAIDA.name}")
if sem_par:
    print(f"{len(sem_par)} pacientes do cadastro sem par no arquivo de avaliações: {sem_par[:10]}")
if descartados:
    print(f"{len(descartados)} valores não numéricos viraram NULL, ex.: {descartados[:5]}")
