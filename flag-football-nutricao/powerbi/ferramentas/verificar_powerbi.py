"""Confere o projeto gerado: JSON válido, campos dos visuais existem no modelo e referências DAX resolvem."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import montar_powerbi as g  # noqa: E402

erros = []
colunas = {t: {c for c, tp in cols if c != "Hora"} for t, (_, cols, _, _) in g.TABELAS.items()}
colunas["Atletas"].add("Posições")
colunas["Consultas"].add("Início")
for t, cs in g.CALC.items():
    colunas[t] |= {n for n, *_ in cs}
medidas = {n: t for t, ms in g.MEDIDAS.items() for n, _, _ in ms}

# 1. DAX: [Medida] e Tabela[Coluna]
def checar_dax(onde, expr, tabela_atual=None):
    for t, c in re.findall(r"\b(Atletas|Consultas|Avaliacoes|Referencias)\[([^\]]+)\]", expr):
        if c not in colunas[t]:
            erros.append(f"{onde}: coluna inexistente {t}[{c}]")
    sem_tab = re.sub(r"\b(Atletas|Consultas|Avaliacoes|Referencias)\[[^\]]+\]", "", expr)
    for m in re.findall(r"\[([^\]]+)\]", sem_tab):
        if m not in medidas:
            erros.append(f"{onde}: medida inexistente [{m}]")

for t, ms in g.MEDIDAS.items():
    for n, e, _ in ms:
        checar_dax(f"medida {t}.{n}", e)
for t, cs in g.CALC.items():
    for n, e, *_ in cs:
        checar_dax(f"coluna {t}.{n}", e)

# 2. visuais
pastas = g.RP / "definition" / "pages"
n_vis = 0
for f in pastas.rglob("*.json"):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        erros.append(f"JSON inválido {f}: {e}")
        continue
    texto = json.dumps(d, ensure_ascii=False)
    if f.name == "visual.json":
        n_vis += 1
    def andar(o):
        if isinstance(o, dict):
            if "Column" in o and isinstance(o["Column"], dict) and "Entity" in o["Column"]["Expression"].get("SourceRef", {}):
                t, c = o["Column"]["Expression"]["SourceRef"]["Entity"], o["Column"]["Property"]
                if t not in colunas or c not in colunas[t]:
                    erros.append(f"{f.parent.name}: campo inexistente {t}[{c}]")
            if "Measure" in o and isinstance(o["Measure"], dict):
                t, m = o["Measure"]["Expression"]["SourceRef"].get("Entity"), o["Measure"]["Property"]
                if medidas.get(m) != t:
                    erros.append(f"{f.parent.name}: medida {m} não está em {t}")
            for v in o.values():
                andar(v)
        elif isinstance(o, list):
            for v in o:
                andar(v)
    andar(d)

# 3. arquivos do modelo
for p in (g.SM / "definition").rglob("*.tmdl"):
    t = p.read_text(encoding="utf-8")
    if "\t\t\t\t" not in t and p.parent.name == "tables":
        erros.append(f"{p.name}: partição sem o bloco M indentado")

print(f"visuais: {n_vis} · medidas: {len(medidas)} · colunas: {sum(len(v) for v in colunas.values())}")
print("\n".join(sorted(set(erros))) if erros else "nenhum problema encontrado")
