"""Gera uma planilha por paciente (abas Evolução, Tabela e Gráficos)."""
import json, sys, re, os, unicodedata
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference

TEXT = {"class_imc", "risco", "class_cmb", "class_gc", "class_gc_bio", "peso_ideal",
        "formula_escolhida", "refAntropometria", "lado"}

SECTIONS = [
    ("Análises básicas", [
        ("Peso atual (Kg)", "massa"), ("Altura atual (cm)", "estatura"),
        ("Índice de Massa Corporal (Kg/m²)", "imc"), ("Classificação do IMC", "class_imc"),
        ("Peso ideal", "peso_ideal"),
        ("Relação Cintura/Quadril (RCQ)", "razao"), ("Risco Metabólico por RCQ", "risco"),
        ("Circ. Musc. do Braço - CMB (cm)", "cmb_cm"), ("CMB - adequação (%)", "cmb_pct"),
        ("Classificação CMB", "class_cmb"),
        ("Percentual de Gordura (%)", "gc"), ("Classif. do % de Gordura", "class_gc"),
        ("Massa de gordura (Kg)", "peso_g"), ("Massa óssea (Kg)", "peso_o"),
        ("Massa muscular (Kg)", "peso_m"), ("Massa residual (Kg)", "peso_r"),
        ("Massa livre de gordura (Kg)", "mlg"),
        ("Somatório de Dobras (mm)", "somatorio"), ("Densidade Corporal (g/mL)", "densidade"),
        ("Protocolo de dobras", "formula_escolhida"), ("Equação de % gordura", "refAntropometria"),
    ]),
    ("Análises por bioimpedância", [
        ("Percentual de Gordura (%)", "bioimpedancia_gordura"),
        ("Classif. do % de Gordura", "class_gc_bio"),
        ("Percentual de Massa magra (%)", "bioimpedancia_percentualMagra"),
        ("Massa Muscular (Kg)", "bioimpedancia_massa"),
        ("Água Corporal Total (Kg)", "bioimpedancia_agua"),
        ("Massa Óssea (Kg)", "bioimpedancia_osseo"),
        ("Massa de gordura (Kg)", "bioimpedancia_massaGordura"),
        ("Massa livre de gordura (Kg)", "bioimpedancia_massalivre"),
        ("Índice de Gordura Visceral", "bioimpedancia_visceral"),
        ("Idade Metabólica (anos)", "bioimpedancia_idade"),
    ]),
    ("Medidas complementares (cm)", [
        ("Altura sentado", "estatura_sentado"), ("Altura do joelho", "altura_joelho"),
    ]),
    ("Dobras cutâneas (mm)", [
        ("Dobra Tricipital", "dobra_triceptal"), ("Dobra Bicipital", "dobra_biciptal"),
        ("Dobra Subescapular", "dobra_subescapular"), ("Dobra Torácica", "dobra_toraxica"),
        ("Dobra Axilar Média", "dobra_axilar"), ("Dobra Suprailíaca", "dobra_suprailiaca"),
        ("Dobra Supraespinhal", "dobra_supraespinhal"), ("Dobra Abdominal", "dobra_abdominal"),
        ("Dobra da Coxa", "dobra_coxa"), ("Dobra da Panturrilha", "dobra_panturrilha"),
    ]),
    ("Circunferências do tronco (cm)", [
        ("Circunferência do Pescoço", "c_pescoco"),
        ("Circunferência do Tórax", "c_torax"), ("Circunferência do Ombro", "c_ombro"),
        ("Circunferência da Cintura", "c_cintura"), ("Circunferência do Abdomen", "c_abdomen"),
        ("Circunferência do Quadril", "c_quadril"),
    ]),
    ("Circunferências dos membros (cm)", [
        ("Braço relaxado - esquerdo", "c_bracorelaxado"), ("Braço relaxado - direito", "c_bracorelaxado_dir"),
        ("Braço contraído - esquerdo", "c_bracocontraido"), ("Braço contraído - direito", "c_bracocontraido_dir"),
        ("Antebraço - esquerdo", "c_antebraco"), ("Antebraço - direito", "c_antebraco_dir"),
        ("Coxa proximal - esquerda", "c_coxaproximal"), ("Coxa proximal - direita", "c_coxaproximal_dir"),
        ("Coxa medial - esquerda", "c_coxamedial"), ("Coxa medial - direita", "c_coxamedial_dir"),
        ("Coxa distal - esquerda", "c_coxadistal"), ("Coxa distal - direita", "c_coxadistal_dir"),
        ("Panturrilha - esquerda", "c_panturrilha"), ("Panturrilha - direita", "c_panturrilha_dir"),
    ]),
    ("Diâmetros ósseos (cm)", [
        ("Diâmetro do Úmero", "diametro_umero"), ("Diâmetro do Punho", "diametro_punho"),
        ("Diâmetro do Fêmur", "diametro_femur"),
    ]),
]

BLUE = PatternFill("solid", fgColor="1F4E78")
SEC = PatternFill("solid", fgColor="D9E1F2")
ZEBRA = PatternFill("solid", fgColor="F7F9FC")
thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
WHITE_B = Font(bold=True, color="FFFFFF")


def num(v):
    v = str(v if v is not None else "").strip()
    if v in ("", "-"):
        return None
    v = re.sub(r"\s*Kg/L$", "", v)
    try:
        return float(v)
    except ValueError:
        return v


def val(r, key):
    v = r.get(key)
    if key in TEXT:
        v = (v or "").strip()
        return v if v not in ("", "-") else None
    return num(v)


def safe_name(nome):
    s = re.sub(r'[<>:"/\\|?*]', "", nome).strip().rstrip(".")
    return re.sub(r"\s+", " ", s)[:120] or "Paciente"


def build(nome, rows, out):
    rows = [r for r in rows if r.get("dataOrdem")]
    rows.sort(key=lambda r: r["dataOrdem"])
    for r in rows:
        m = re.match(r"([\d.]+)\s*\(([\d.]+)%\)", str(r.get("cmb", "")))
        r["cmb_cm"], r["cmb_pct"] = (m.group(1), m.group(2)) if m else ("", "")
    dates = [datetime.strptime(r["dataAvaliacao"], "%d/%m/%Y") for r in rows]
    N = len(rows)
    # só mantém as linhas com pelo menos um valor para este paciente
    sections = [(t, [(l, k) for l, k in items if any(val(r, k) is not None for r in rows)])
                for t, items in SECTIONS]
    sections = [(t, items) for t, items in sections if items]

    wb = Workbook()
    ws = wb.active
    ws.title = "Evolução"
    ws["A1"] = f"Evolução antropométrica - {nome}"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    periodo = f"de {rows[0]['dataAvaliacao']} a {rows[-1]['dataAvaliacao']}" if N > 1 else f"em {rows[0]['dataAvaliacao']}"
    ws["A2"] = f"{N} {'avaliação' if N == 1 else 'avaliações'} {periodo} · Fonte: App Naive"
    ws["A2"].font = Font(italic=True, color="595959")

    hr = 4
    ws.cell(hr, 1, "Parâmetro")
    for j, d in enumerate(dates):
        ws.cell(hr, 2 + j, d).number_format = "dd/mm/yyyy"
    var_col = 2 + N
    ws.cell(hr, var_col, "Variação (última − primeira)")
    for c in range(1, var_col + 1):
        cell = ws.cell(hr, c)
        cell.font, cell.fill, cell.border = WHITE_B, BLUE, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[hr].height = 32

    r_i = hr + 1
    for title, items in sections:
        ws.cell(r_i, 1, title).font = Font(bold=True, color="1F4E78")
        for c in range(1, var_col + 1):
            ws.cell(r_i, c).fill = SEC
            ws.cell(r_i, c).border = BORDER
        r_i += 1
        for k, (label, key) in enumerate(items):
            ws.cell(r_i, 1, label).border = BORDER
            vals = []
            for j, r in enumerate(rows):
                v = val(r, key)
                c = ws.cell(r_i, 2 + j, v)
                c.border = BORDER
                c.alignment = Alignment(horizontal="center")
                if isinstance(v, float):
                    c.number_format = "0.000" if key == "densidade" else "0.0#"
                vals.append(v)
            nums = [(j, v) for j, v in enumerate(vals) if isinstance(v, float)]
            vc = ws.cell(r_i, var_col)
            vc.border = BORDER
            vc.alignment = Alignment(horizontal="center")
            if key not in TEXT and len(nums) >= 2:
                a = ws.cell(r_i, 2 + nums[0][0]).coordinate
                b = ws.cell(r_i, 2 + nums[-1][0]).coordinate
                vc.value = f"={b}-{a}"
                vc.number_format = '+0.0##;-0.0##;0'
                vc.font = Font(bold=True)
            if k % 2:
                for c in range(1, var_col):
                    ws.cell(r_i, c).fill = ZEBRA
            r_i += 1
    ws.column_dimensions["A"].width = 34
    for j in range(N):
        ws.column_dimensions[get_column_letter(2 + j)].width = 12
    ws.column_dimensions[get_column_letter(var_col)].width = 16
    ws.freeze_panes = ws.cell(hr + 1, 2)

    # Tabela: uma linha por avaliação
    wt = wb.create_sheet("Tabela")
    cols = [("Data", None)] + [(label if title == "Análises básicas" else f"{label} [{title.split(' (')[0]}]", key)
                               for title, items in sections for label, key in items]
    for j, (h, _) in enumerate(cols):
        c = wt.cell(1, 1 + j, h)
        c.font, c.fill, c.border = WHITE_B, BLUE, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        wt.column_dimensions[get_column_letter(1 + j)].width = 14
    wt.column_dimensions["A"].width = 12
    wt.row_dimensions[1].height = 60
    for i, r in enumerate(rows):
        c = wt.cell(2 + i, 1, dates[i])
        c.number_format = "dd/mm/yyyy"
        c.border = BORDER
        for j, (_, key) in enumerate(cols[1:]):
            wt.cell(2 + i, 2 + j, val(r, key)).border = BORDER
    wt.freeze_panes = "B2"
    wt.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{N + 1}"

    # Gráficos
    wg = wb.create_sheet("Gráficos")
    chart_keys = [("Data", None), ("Peso (Kg)", "massa"), ("% Gordura", "gc"),
                  ("Massa de gordura (Kg)", "peso_g"), ("Massa muscular (Kg)", "peso_m"),
                  ("Massa livre de gordura (Kg)", "mlg"), ("Cintura (cm)", "c_cintura"),
                  ("Abdomen (cm)", "c_abdomen"), ("Somatório de dobras (mm)", "somatorio")]
    has = {}
    for j, (h, key) in enumerate(chart_keys):
        wg.cell(1, 1 + j, h).font = Font(bold=True)
        wg.column_dimensions[get_column_letter(1 + j)].width = 14
        col_vals = []
        for i, r in enumerate(rows):
            v = dates[i].strftime("%d/%m/%y") if key is None else val(r, key)
            wg.cell(2 + i, 1 + j, v)
            col_vals.append(v)
        has[1 + j] = any(isinstance(v, float) for v in col_vals)

    anchor_row = 2

    def line(title, ycols, ytitle):
        nonlocal anchor_row
        ycols = [c for c in ycols if has[c]]
        if not ycols:
            return
        ch = LineChart()
        ch.title, ch.y_axis.title, ch.height, ch.width = title, ytitle, 8, 18
        for c in ycols:
            ch.add_data(Reference(wg, min_col=c, min_row=1, max_row=N + 1), titles_from_data=True)
        ch.set_categories(Reference(wg, min_col=1, min_row=2, max_row=N + 1))
        for s in ch.series:
            s.marker.symbol = "circle"
            s.smooth = False
        ch.y_axis.delete = False
        ch.x_axis.delete = False
        wg.add_chart(ch, f"K{anchor_row}")
        anchor_row += 17

    line("Peso corporal", [2], "Kg")
    line("Percentual de gordura (dobras)", [3], "%")
    line("Composição corporal", [4, 5, 6], "Kg")
    line("Cintura e abdomen", [7, 8], "cm")
    line("Somatório de dobras", [9], "mm")

    wb.save(out)


if __name__ == "__main__":
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    pacs = json.load(open(src, encoding="utf-8"))["pacientes"]

    nomes = {}
    for p in pacs:
        nomes.setdefault(safe_name(p["nome"]), []).append(p)

    feitos, sem = 0, []
    for base, grupo in nomes.items():
        for idx, p in enumerate(grupo):
            avs = [a for a in (p.get("avaliacoes") or []) if a.get("dataOrdem")]
            if not avs:
                sem.append(p["nome"])
                continue
            nome_arq = base if len(grupo) == 1 else f"{base} ({idx + 1})"
            build(p["nome"].strip(), avs, os.path.join(outdir, nome_arq + ".xlsx"))
            feitos += 1
    print(f"ok planilhas={feitos} sem_avaliacao={len(sem)} duplicados={sum(1 for g in nomes.values() if len(g) > 1)}")
