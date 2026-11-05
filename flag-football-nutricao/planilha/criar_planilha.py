"""Cria a planilha "Time Exemplo - Nutrição.xlsx" (subir no Google Drive e abrir com o Google Planilhas).

Abas: Atletas · Consultas · Avaliações · Referências · Listas · Como usar
Os nomes das colunas são lidos pelo Apps Script e pelo Power BI: não renomeie os cabeçalhos.
"""
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "Time Exemplo - Nutrição.xlsx"

AZUL, AMARELO, VERDE, CINZA, BRANCO = "13246B", "F2C500", "007222", "F2F4F7", "FFFFFF"

ATLETAS = [  # atletas FICTÍCIOS: nomes, telefones, posições e medidas inventados
    ("Thiago Queiroga Cardoso", "55 900000001", "DB", "", "", 91, 1.83),
    ("Igor Nogueira Farias", "55 (11) 90000-0002", "SN", "WR", "", 83, 1.75),
    ("Felipe Xavier Zanetti", "55 (11) 90000-0003", "DB", "QB", "", 82, 1.91),
    ("Henrique Paiva Siqueira", "55 (11) 90000-0004", "WR", "DB", "", 88, 1.91),
    ("Paulo Queiroga Nogueira", "55 (11) 90000-0005", "BL", "DB", "", 86, 1.83),
    ("Diego Gomes Barbosa", "55 (11) 90000-0006", "BL", "DB", "", 99, 1.70),
    ("Ricardo Nogueira Uchoa", "55 (11) 90000-0007", "WR", "", "", 83, 1.82),
    ("Bruno Xavier Valente", "55 (11) 90000-0008", "QB", "BL", "SN", 79, 1.69),
    ("Eduardo Uchoa Xavier", "55 (11) 90000-0009", "SN", "", "", 67, 1.82),
    ("Diego Valente Esteves", "55 (11) 90000-0010", "BL", "QB", "", 74, 1.69),
    ("Hugo Xavier Macedo", "55 (11) 90000-0011", "SN", "BL", "", 96, 1.79),
    ("Nicolas Queiroga Farias", "55 (11) 90000-0012", "DB", "WR", "SN", 67, 1.80),
    ("Henrique Xavier Zanetti", "55 (11) 90000-0013", "WR", "DB", "", 80, 1.70),
    ("Bruno Jardim Rezende", "55 (11) 90000-0014", "WR", "DB", "SN", 74, 1.92),
    ("Sérgio Ilha Macedo", "55 900000015", "SN", "BL", "", 99, 1.89),
    ("Murilo Queiroga Esteves", "55 (11) 90000-0016", "WR", "SN", "", 91, 1.82),
    ("Leandro Ilha Macedo", "55 (11) 90000-0017", "SN", "BL", "", 82, 1.84),
    ("Samuel Gomes Duarte", "55 (11) 90000-0018", "WR", "", "", 82, 1.78),
    ("Lucas Queiroga Barbosa", "55 (11) 90000-0019", "QB", "BL", "", 79, 1.75),
    ("Samuel Toledo Nogueira", "55 (11) 90000-0020", "QB", "", "", 100, 1.91),
    ("Henrique Cardoso Gomes", "55 (11) 90000-0021", "SN", "DB", "BL", 78, 1.72),
    ("Vitor Xavier Leal", "55 (11) 90000-0022", "BL", "WR", "DB", 69, 1.72),
    ("Tiago Siqueira Leal", "55 (11) 90000-0023", "WR", "DB", "", 72, 1.73),
    ("Murilo Holanda Cardoso", "55 (11) 90000-0024", "WR", "QB", "", 77, 1.79),
    ("Caio Siqueira Esteves", "55 (11) 90000-0025", "QB", "BL", "SN", 98, 1.83),
    ("Gustavo Queiroga Esteves", "55 (11) 90000-0026", "BL", "SN", "", 78, 1.84),
    ("Bruno Gomes Uchoa", "55 (11) 90000-0027", "SN", "QB", "", 80, 1.91),
    ("Vinícius Almeida Farias", "55 (11) 90000-0028", "SN", "DB", "WR", 69, 1.85),
    ("Nicolas Xavier Farias", "55 (11) 90000-0029", "DB", "QB", "", 82, 1.69),
    ("Caio Valente Ilha", "55 (11) 90000-0030", "BL", "SN", "", 84, 1.71),
    ("Caio Zanetti Xavier", "55 (11) 90000-0031", "QB", "", "", 68, 1.90),
    ("Vitor Xavier Toledo", "55 (11) 90000-0032", "SN", "", "", 75, 1.74),
    ("Igor Xavier Rezende", "55 (11) 90000-0033", "SN", "WR", "", 86, 1.83),
    ("Igor Jardim Zanetti", "55 (11) 90000-0034", "DB", "QB", "BL", 88, 1.74),
    ("Vinícius Queiroga Barbosa", "55 (11) 90000-0035", "WR", "BL", "", 98, 1.73),
]

POSICOES = ["QB", "WR", "DB", "BL", "SN", "C"]
POSICOES_NOMES = {"QB": "Quarterback", "WR": "Wide receiver", "DB": "Defensive back", "BL": "Blitzer/Rusher",
                  "SN": "Snapper", "C": "Center"}
QUAEST = ["Respondido", "Pendente"]
STATUS_ATLETA = ["Ativo", "Inativo"]
TIPOS = ["1ª consulta", "Retorno", "Avaliação", "Online rápida"]
MODALIDADES = ["Online", "Presencial"]
STATUS_CONSULTA = ["Agendada", "Confirmada", "Realizada", "Faltou", "Remarcada", "Cancelada"]


def whatsapp(tel):
    """Número no formato internacional (+55...) e um aviso quando parece incompleto ou errado."""
    if "/" in tel:
        return "", "Dois números informados: escolha um"
    d = re.sub(r"\D", "", tel)
    if tel.strip().startswith("+") or (not d.startswith("55") and len(d) in (11, 12) and d[0] in "14"):
        return "+" + d, ("Número do exterior" if not d.startswith("55") else "")
    if d.startswith("55"):
        resto = d[2:]
        if len(resto) == 11:
            return "+55" + resto, ""
        if len(resto) == 10:
            return "+55" + resto, "Sem o 9 na frente? Conferir"
        return "+55" + resto, "Sem DDD ou incompleto: conferir"
    if len(d) == 11:
        return "+55" + d, ""
    return "", "Formato não reconhecido: conferir"


def nome_curto(n):
    p = [x for x in n.split() if x.lower() not in ("de", "da", "do", "dos", "das", "e")]
    return f"{p[0]} {p[-1]}" if len(p) > 1 else n


def estilo_cabecalho(ws, n_colunas, cor=AZUL):
    for c in range(1, n_colunas + 1):
        cel = ws.cell(row=1, column=c)
        cel.font = Font(bold=True, color=BRANCO)
        cel.fill = PatternFill("solid", fgColor=cor)
        cel.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "B2"


def larguras(ws, ls):
    for i, w in enumerate(ls, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def lista(ws, coluna, intervalo, linhas=1000):
    dv = DataValidation(type="list", formula1=intervalo, allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    dv.add(f"{coluna}2:{coluna}{linhas}")


wb = Workbook()

# ---------------- Listas (opções dos menus) ----------------
li = wb.active
li.title = "Listas"
colunas_listas = [("Posições", POSICOES), ("QUAEST", QUAEST), ("Status do atleta", STATUS_ATLETA),
                  ("Tipo de consulta", TIPOS), ("Modalidade", MODALIDADES), ("Status da consulta", STATUS_CONSULTA)]
for j, (titulo, valores) in enumerate(colunas_listas, 1):
    li.cell(row=1, column=j, value=titulo)
    for i, v in enumerate(valores, 2):
        li.cell(row=i, column=j, value=v)
li.cell(row=1, column=8, value="Sigla")
li.cell(row=1, column=9, value="Posição")
for i, (k, v) in enumerate(POSICOES_NOMES.items(), 2):
    li.cell(row=i, column=8, value=k)
    li.cell(row=i, column=9, value=v)
estilo_cabecalho(li, 9, cor=VERDE)
larguras(li, [12, 14, 16, 18, 14, 18, 3, 8, 18])
REF = {t: f"Listas!${get_column_letter(j)}$2:${get_column_letter(j)}${len(v) + 1}" for j, (t, v) in
       enumerate(colunas_listas, 1)}

# ---------------- Atletas ----------------
at = wb.create_sheet("Atletas", 0)
cab = ["Atleta", "Nome curto", "Posição 1", "Posição 2", "Posição 3", "Data de nascimento", "Peso informado (kg)",
       "Altura informada (m)", "Telefone (como veio)", "WhatsApp", "QUAEST", "Status", "Observações"]
at.append(cab)
for nome, tel, p1, p2, p3, peso, alt in ATLETAS:
    wa, aviso = whatsapp(tel)
    at.append([nome, nome_curto(nome), p1, p2 or None, p3 or None, None, peso, alt, tel, wa or None, "Respondido",
               "Ativo", aviso or None])
estilo_cabecalho(at, len(cab))
larguras(at, [38, 20, 10, 10, 10, 14, 12, 12, 24, 17, 12, 10, 34])
for r in range(2, at.max_row + 1):
    at.cell(row=r, column=6).number_format = "DD/MM/YYYY"
    at.cell(row=r, column=8).number_format = "0.00"
    if at.cell(row=r, column=13).value:
        at.cell(row=r, column=13).fill = PatternFill("solid", fgColor="FFF4CC")
for col in "CDE":
    lista(at, col, REF["Posições"])
lista(at, "K", REF["QUAEST"])
lista(at, "L", REF["Status do atleta"])
ATLETAS_REF = f"Atletas!$A$2:$A$200"

# ---------------- Consultas ----------------
co = wb.create_sheet("Consultas", 1)
cab_c = ["ID", "Atleta", "Data", "Hora", "Duração (min)", "Tipo", "Modalidade", "Link da consulta", "Status",
         "Objetivo / queixa", "Resumo e condutas", "Próximo retorno", "ID do evento (Google)", "Avisos enviados"]
co.append(cab_c)
estilo_cabecalho(co, len(cab_c))
for c in (13, 14):   # colunas preenchidas pelo script
    co.cell(row=1, column=c).fill = PatternFill("solid", fgColor="6B7280")
larguras(co, [6, 36, 12, 8, 10, 14, 12, 30, 12, 34, 50, 14, 22, 16])
for r in range(2, 1001):
    co.cell(row=r, column=3).number_format = "DD/MM/YYYY"
    co.cell(row=r, column=4).number_format = "HH:MM"
    co.cell(row=r, column=12).number_format = "DD/MM/YYYY"
lista(co, "B", ATLETAS_REF)
lista(co, "F", REF["Tipo de consulta"])
lista(co, "G", REF["Modalidade"])
lista(co, "I", REF["Status da consulta"])

# ---------------- Avaliações ----------------
av = wb.create_sheet("Avaliações", 2)
cab_a = ["Atleta", "Data", "Peso (kg)", "Altura (cm)",
         "Dobra tríceps (mm)", "Dobra subescapular (mm)", "Dobra peitoral (mm)", "Dobra axilar média (mm)",
         "Dobra suprailíaca (mm)", "Dobra abdominal (mm)", "Dobra coxa medial (mm)",
         "Circ. braço relaxado (cm)", "Circ. braço contraído (cm)", "Circ. cintura (cm)", "Circ. coxa medial (cm)",
         "Massa muscular (kg)", "% água corporal", "Observações"]
av.append(cab_a)
estilo_cabecalho(av, len(cab_a))
larguras(av, [36, 12, 9, 9] + [11] * 7 + [12] * 4 + [11, 10, 30])
for r in range(2, 1001):
    av.cell(row=r, column=2).number_format = "DD/MM/YYYY"
lista(av, "A", ATLETAS_REF)

# ---------------- Referências ----------------
rf = wb.create_sheet("Referências", 3)
rf.append(["Indicador", "Valor", "Unidade", "Fonte"])
fonte = ("Valores de referência de exemplo. Substitua pelos da literatura que você usa (ex.: perfil "
         "cineantropométrico de atletas de elite de flag football).")
rf.append(["Massa muscular (kg)", 40.40, "kg", fonte])
rf.append(["Massa adiposa (kg)", 19.50, "kg", fonte])
estilo_cabecalho(rf, 4, cor=VERDE)
larguras(rf, [24, 10, 10, 110])

# ---------------- Como usar ----------------
cu = wb.create_sheet("Como usar")
texto = [
    "TIME EXEMPLO · NUTRIÇÃO — como usar esta planilha",
    "",
    "1. Atletas: uma linha por atleta. O nome em 'Atleta' é usado em todas as outras abas (escolha pela lista).",
    "   'Observações' em amarelo = telefone que precisa ser conferido.",
    "2. Consultas: uma linha por consulta. Preencha Atleta, Data, Hora, Tipo, Modalidade e o Link (Meet).",
    "   Status: Agendada → Confirmada → Realizada (ou Faltou / Remarcada / Cancelada).",
    "   Depois da consulta, escreva o 'Resumo e condutas' e o 'Próximo retorno'.",
    "   As colunas cinzas (ID do evento, Avisos enviados) são preenchidas sozinhas pelo script: não apague.",
    "3. Avaliações: uma linha por avaliação. Com as 7 dobras e a data de nascimento do atleta, o Power BI calcula",
    "   % de gordura (Pollock 7 e Faulkner), massa adiposa e massa livre de gordura.",
    "4. Referências: valores usados no comparativo 'Time Exemplo × referência'.",
    "",
    "Lembretes: menu 🏈 Time Exemplo (aparece depois de instalar o script). Avisa no Telegram e no Google Agenda.",
    "Não renomeie os cabeçalhos nem as abas: o script e o Power BI usam esses nomes.",
]
for i, t in enumerate(texto, 1):
    cu.cell(row=i, column=1, value=t)
cu["A1"].font = Font(bold=True, size=14, color=AZUL)
cu.column_dimensions["A"].width = 120

wb.move_sheet("Listas", offset=10)
SAIDA.parent.mkdir(parents=True, exist_ok=True)
wb.save(SAIDA)
print("ok:", SAIDA, "| atletas:", len(ATLETAS), "| telefones a conferir:",
      sum(1 for a in ATLETAS if whatsapp(a[1])[1] and whatsapp(a[1])[1] != "Número do exterior"))
