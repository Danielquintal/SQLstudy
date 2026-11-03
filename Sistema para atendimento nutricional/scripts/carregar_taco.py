"""Carrega a TACO (dados/taco/*.csv) na tabela alimento do banco (sql/06_alimentos.sql).

Uso:  python scripts/carregar_taco.py
Pode rodar de novo: atualiza os 597 alimentos da TACO pelo número de cada um, sem duplicar e sem mexer
nos alimentos próprios nem nas medidas caseiras já cadastradas.
"""
import csv
from pathlib import Path

import psycopg

from atualizar_paciente import CONEXAO

TACO = Path(__file__).resolve().parent.parent / "dados" / "taco"

# coluna do CSV -> coluna da tabela alimento
NUTRIENTES = {
    "moisture": "umidade_pct", "kcal": "kcal", "kJ": "kj", "protein": "proteina_g", "lipids": "lipidios_g",
    "carbohydrates": "carboidrato_g", "dietaryFiber": "fibra_g", "ash": "cinzas_g", "cholesterol": "colesterol_mg",
    "calcium": "calcio_mg", "magnesium": "magnesio_mg", "manganese": "manganes_mg", "phosphorus": "fosforo_mg",
    "iron": "ferro_mg", "sodium": "sodio_mg", "potassium": "potassio_mg", "copper": "cobre_mg", "zinc": "zinco_mg",
    "retinol": "retinol_mcg", "re": "vit_a_re_mcg", "rae": "vit_a_rae_mcg", "thiamin": "tiamina_mg",
    "riboflavin": "riboflavina_mg", "pyridoxine": "piridoxina_mg", "niacin": "niacina_mg", "vitaminC": "vit_c_mg",
}
GORDURAS = {"saturated": "ag_saturados_g", "monounsaturated": "ag_monoinsaturados_g",
            "polyunsaturated": "ag_poliinsaturados_g"}
TRANS = ("18:1t", "18:2t")


def ler(nome):
    with open(TACO / nome, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def numero(v):
    v = (v or "").strip()
    return float(v) if v else None


def main():
    grupos = ler("categories.csv")
    alimentos = {int(r["id"]): r for r in ler("food.csv")}
    nutrientes = {int(r["foodId"]): r for r in ler("nutrients.csv")}
    gorduras = {int(r["foodId"]): r for r in ler("fatty-acids.csv")}
    colunas = ["fonte", "codigo_taco", "nome", "grupo_id"] + list(NUTRIENTES.values()) + list(GORDURAS.values()) + ["ag_trans_g"]
    with psycopg.connect(CONEXAO) as con:
        cur = con.cursor()
        for g in grupos:
            cur.execute("INSERT INTO alimento_grupo (id, nome) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome",
                        (int(g["id"]), g["name"]))
        for cod, a in sorted(alimentos.items()):
            n, g = nutrientes.get(cod, {}), gorduras.get(cod, {})
            trans = [numero(g.get(c)) for c in TRANS if numero(g.get(c)) is not None]
            valores = (["TACO", cod, a["name"], int(a["categoryId"])]
                       + [numero(n.get(c)) for c in NUTRIENTES] + [numero(g.get(c)) for c in GORDURAS]
                       + [sum(trans) if trans else None])
            cur.execute(f"""INSERT INTO alimento ({', '.join(colunas)}) VALUES ({', '.join(['%s'] * len(colunas))})
                            ON CONFLICT (codigo_taco) DO UPDATE SET
                            {', '.join(f'{c} = EXCLUDED.{c}' for c in colunas[2:])}""", valores)
        cur.execute("SELECT count(*) FROM alimento WHERE fonte = 'TACO'")
        print(f"TACO no banco: {cur.fetchone()[0]} alimentos em {len(grupos)} grupos")


if __name__ == "__main__":
    main()
