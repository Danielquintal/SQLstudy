"""Atualiza um paciente a partir da planilha dele.

Uso:  python scripts/atualizar_paciente.py "Nome do paciente" [--id N] [--simular]
1. Lê a aba Tabela de Downloads\\Antropometria por paciente\\<nome>.xlsx
2. Insere no banco as avaliações de datas novas e corrige os valores alterados nas datas que já existem
3. Gera de novo a planilha (abas Evolução, Tabela, Gráficos) e a página web/paginas/<nome>.html
Nada é apagado do banco: uma linha removida da planilha volta na próxima geração.
--simular mostra o que mudaria sem gravar nada. --id escolhe entre pacientes de mesmo nome.
"""
import argparse, json, os, re, sys, unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import psycopg

from campos import CAMPOS, TEXTO
from montar_pagina import montar
from plano import plano_do_banco
from planilha_paciente import SECTIONS, build, safe_name

RAIZ = Path(__file__).resolve().parent.parent
PLANILHAS = Path.home() / "Downloads" / "Antropometria por paciente"
TEMPLATE = RAIZ / "web" / "template.html"
ARTEFATOS = RAIZ / "web" / "artefatos.json"
PAGINAS = RAIZ / "web" / "paginas"
# outro banco (ex.: o de demonstração): variável de ambiente APP_NAIVE_CONEXAO
CONEXAO = os.environ.get("APP_NAIVE_CONEXAO", "host=localhost port=5432 dbname=app_naive user=postgres")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


# cabeçalho da aba Tabela (como planilha_paciente.py escreve) -> coluna do banco
COLUNA = {v: k for k, v in CAMPOS.items()}
CABECALHOS, ROTULO = {}, {}
for titulo, itens in SECTIONS:
    for rotulo, chave in itens:
        h = rotulo if titulo == "Análises básicas" else f"{rotulo} [{titulo.split(' (')[0]}]"
        CABECALHOS[norm(h)] = COLUNA[chave]
        ROTULO[COLUNA[chave]] = h


def sair(msg):
    print(msg)
    sys.exit(1)


def para_data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    v = str(v or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    return None


def converter(col, v):
    """valor da célula -> valor do banco; levanta ValueError se não for número"""
    if v is None or str(v).strip() in ("", "-"):
        return None
    if col in TEXTO:
        return str(v).strip()
    if isinstance(v, (int, float)):
        return float(v)
    return float(re.sub(r"\s*(Kg/L|kg/l|Kg|kg|%)$", "", str(v).strip()).replace(",", "."))


def igual(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip() == str(b).strip()
    return abs(float(a) - float(b)) < 1e-9


def mostrar(v):
    if v is None:
        return "(vazio)"
    if isinstance(v, (float, Decimal)):
        return format(Decimal(str(v)).normalize(), "f")
    return str(v)


def ler_tabela(arq):
    wb = openpyxl.load_workbook(arq, data_only=True)
    if "Tabela" not in wb.sheetnames:
        sair(f"A planilha {arq.name} não tem a aba Tabela.")
    ws = wb["Tabela"]
    cab = [norm(c.value) if c.value is not None else "" for c in ws[1]]
    ignoradas = [ws.cell(1, j + 1).value for j, h in enumerate(cab[1:], 1) if h and h not in CABECALHOS]
    linhas, erros = [], []
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if all(v is None or str(v).strip() == "" for v in r):
            continue
        d = para_data(r[0])
        if d is None:
            erros.append(f"linha {i}: data inválida {r[0]!r}")
            continue
        valores = {}
        for j, (h, v) in enumerate(zip(cab[1:], r[1:]), 1):
            col = CABECALHOS.get(h)
            if not col:
                continue
            try:
                valores[col] = converter(col, v)
            except ValueError:
                erros.append(f"linha {i}, {ws.cell(1, j + 1).value}: {v!r} não é número")
        linhas.append((i, d, valores))
    return linhas, ignoradas, erros


def achar_paciente(cur, nome, pid):
    cur.execute("SELECT p.id, p.nome, count(a.id) FROM paciente p LEFT JOIN avaliacao a ON a.paciente_id = p.id "
                "GROUP BY p.id ORDER BY p.nome, p.id")
    todos = cur.fetchall()
    if pid is not None:
        achados = [p for p in todos if p[0] == pid]
    else:
        achados = [p for p in todos if norm(p[1]) == norm(nome)] or [p for p in todos if norm(nome) in norm(p[1])]
    if not achados:
        sair(f"Nenhum paciente encontrado com \"{nome}\".")
    if len(achados) > 1:
        sair("Mais de um paciente encontrado. Escreva o nome completo ou use --id:\n"
             + "\n".join(f"  --id {i}  {n} ({q} avaliações)" for i, n, q in achados))
    return achados[0]


def avaliacoes_do_banco(cur, pid):
    cols = ["id", "data_avaliacao"] + list(CAMPOS)
    cur.execute(f"SELECT {', '.join(cols)} FROM avaliacao WHERE paciente_id = %s ORDER BY data_avaliacao, id", (pid,))
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def achar_planilha(nome, datas_banco, homonimo):
    base = safe_name(nome)
    candidatos = [PLANILHAS / f"{base}.xlsx"] + sorted(PLANILHAS.glob(f"{glob_escape(base)} (*).xlsx"))
    candidatos = [c for c in candidatos if c.exists()]
    if not homonimo:
        return (candidatos[0], candidatos[0]) if candidatos else (None, PLANILHAS / f"{base}.xlsx")
    # outro paciente com o mesmo nome: só vale a planilha com datas em comum com as avaliações deste
    def em_comum(arq):
        return len({d for _, d, _ in ler_tabela(arq)[0]} & datas_banco)
    melhor = max(candidatos, key=em_comum, default=None)
    if melhor is None or em_comum(melhor) == 0:
        livre = next(PLANILHAS / f"{base} ({n}).xlsx" for n in range(1, 100)
                     if not (PLANILHAS / f"{base} ({n}).xlsx").exists())
        return None, livre
    return melhor, melhor


def glob_escape(s):
    return re.sub(r"([\[\]*?])", r"[\1]", s)


def para_app_naive(reg):
    """linha do banco -> dicionário com as chaves do App Naive, como build() e montar() esperam"""
    d = reg["data_avaliacao"]
    a = {"dataAvaliacao": d.strftime("%d/%m/%Y"), "dataOrdem": d.strftime("%Y%m%d")}
    for col, chave in CAMPOS.items():
        a[chave] = "" if reg[col] is None else mostrar(reg[col])
    if a["cmb_cm"] and a["cmb_pct"]:
        a["cmb"] = f"{a['cmb_cm']} ({a['cmb_pct']}%)"
    return a


def plano_do_paciente(nome):
    pacs = json.load(open(ARTEFATOS, encoding="utf-8"))["pacientes"]
    for n, info in pacs.items():
        if norm(n) == norm(nome):
            plano = json.load(open(RAIZ / "web" / info["plano"], encoding="utf-8")) if info.get("plano") else None
            return plano, info.get("url")
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Atualiza um paciente a partir da aba Tabela da planilha dele.")
    ap.add_argument("nome", nargs="?", default="")
    ap.add_argument("--id", type=int)
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()
    if not args.nome.strip() and args.id is None:
        sair("Informe o nome do paciente.")

    try:
        con = psycopg.connect(CONEXAO)
    except psycopg.OperationalError as e:
        sair(f"Não consegui conectar ao banco app_naive: {e}")

    with con:
        cur = con.cursor()
        pid, nome, _ = achar_paciente(cur, args.nome, args.id)
        banco = avaliacoes_do_banco(cur, pid)
        print(f"Paciente: {nome} (id {pid}), {len(banco)} avaliações no banco")

        cur.execute("SELECT nome FROM paciente WHERE id <> %s", (pid,))
        homonimo = any(norm(n) == norm(nome) for n, in cur.fetchall())
        arq, destino = achar_planilha(nome, {r["data_avaliacao"] for r in banco}, homonimo)
        if arq is None:
            print(f"Planilha não encontrada: {destino}")
            if not banco:
                sair("O paciente também não tem avaliações no banco; não há o que gerar.")
            linhas = []
        else:
            print(f"Planilha: {arq}")
            linhas, ignoradas, erros = ler_tabela(arq)
            if ignoradas:
                print("Colunas não reconhecidas (ignoradas): " + "; ".join(map(str, ignoradas)))
            if erros:
                sair("Corrija a planilha e rode de novo. Nada foi gravado.\n  " + "\n  ".join(erros))

        # pareia por data, na ordem: planilha (linhas) x banco (id)
        por_data = {}
        for r in banco:
            por_data.setdefault(r["data_avaliacao"], []).append(r)
        novas, alteracoes, usadas = [], [], set()
        for i, d, valores in linhas:
            fila = [r for r in por_data.get(d, []) if r["id"] not in usadas]
            if not fila:
                novas.append((d, valores))
                continue
            reg = fila[0]
            usadas.add(reg["id"])
            mud = {c: v for c, v in valores.items() if not igual(v, reg[c])}
            if mud:
                alteracoes.append((reg, mud))
        fora = [r for r in banco if r["id"] not in usadas] if linhas else []

        for d, valores in novas:
            preenchidos = sum(v is not None for v in valores.values())
            print(f"+ nova avaliação {d:%d/%m/%Y} ({preenchidos} campos)")
        for reg, mud in alteracoes:
            print(f"~ {reg['data_avaliacao']:%d/%m/%Y}: " + "; ".join(
                f"{ROTULO[c]}: {mostrar(reg[c])} -> {mostrar(v)}" for c, v in mud.items()))
        for r in fora:
            print(f"! {r['data_avaliacao']:%d/%m/%Y} está no banco mas não na planilha (continua no banco)")
        if not novas and not alteracoes:
            print("Nenhuma mudança na planilha.")

        if args.simular:
            print("Simulação: nada foi gravado.")
            return

        if arq is not None:
            try:
                open(arq, "r+b").close()
            except PermissionError:
                sair("A planilha está aberta no Excel. Feche e rode de novo. Nada foi gravado.")

        for d, valores in novas:
            cols = ["paciente_id", "data_avaliacao"] + list(valores)
            cur.execute(f"INSERT INTO avaliacao ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                        [pid, d] + list(valores.values()))
        for reg, mud in alteracoes:
            cur.execute(f"UPDATE avaliacao SET {', '.join(f'{c} = %s' for c in mud)} WHERE id = %s",
                        list(mud.values()) + [reg["id"]])
        con.commit()
        if novas or alteracoes:
            print(f"Banco: {len(novas)} inseridas, {len(alteracoes)} alteradas")

        avs = [para_app_naive(r) for r in avaliacoes_do_banco(cur, pid)]
        plano = plano_do_banco(cur, pid)

    if not avs:
        print("Sem avaliações: planilha e página não foram geradas.")
        return
    build(nome.strip(), [dict(a) for a in avs], str(destino))
    print(f"Planilha gerada: {destino}")

    _, url = plano_do_paciente(nome)
    PAGINAS.mkdir(parents=True, exist_ok=True)
    pagina = PAGINAS / f"{safe_name(nome)}.html"
    montar(str(TEMPLATE), nome, avs, plano, str(pagina))
    print(f"Página gerada: {pagina}")
    print(f"Link publicado: {url}" if url else "Paciente ainda sem link publicado em web/artefatos.json")


if __name__ == "__main__":
    main()
