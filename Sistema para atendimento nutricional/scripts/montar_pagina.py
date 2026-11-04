"""Preenche o template com as avaliacoes de um paciente."""
import json, re, sys

from plano import PROFISSIONAL

KEEP = ["dataAvaliacao", "dataOrdem", "massa", "estatura", "gc", "peso_m", "peso_g", "mlg", "somatorio", "razao",
        "c_cintura", "c_abdomen", "c_quadril", "c_torax", "c_ombro",
        "c_bracorelaxado", "c_bracorelaxado_dir", "c_bracocontraido", "c_bracocontraido_dir",
        "c_antebraco", "c_antebraco_dir", "c_coxaproximal", "c_coxaproximal_dir", "c_coxamedial", "c_coxamedial_dir",
        "c_coxadistal", "c_coxadistal_dir", "c_panturrilha", "c_panturrilha_dir",
        "dobra_triceptal", "dobra_subescapular", "dobra_toraxica", "dobra_axilar", "dobra_suprailiaca",
        "dobra_abdominal", "dobra_coxa",
        "imc", "class_imc", "peso_ideal", "risco", "cmb_cm", "cmb_pct", "class_cmb", "class_gc",
        "bioimpedancia_gordura", "class_gc_bio"]
PROTOCOLOS = {"pollock7": "Pollock 7", "pollock3": "Pollock 3", "guedes": "Guedes", "petroski": "Petroski",
              "durnin": "Durnin & Womersley", "faulkner": "Faulkner", "jackson": "Jackson & Pollock"}


def separar_cmb(a):
    """no JSON do App Naive a CMB vem junta: "24.3 (113.4%)" """
    if a.get("cmb_cm"):
        return a
    m = re.match(r"([\d.]+)\s*\(([\d.]+)%\)", str(a.get("cmb", "")))
    return dict(a, cmb_cm=m.group(1) if m else "", cmb_pct=m.group(2) if m else "")


def montar(template, nome, avaliacoes, plano, out, checkin=None):
    t = gerar_html(template, nome, avaliacoes, plano, checkin)
    open(out, "w", encoding="utf-8").write(t)
    return len(avaliacoes), len(t)


def gerar_html(template, nome, avaliacoes, plano, checkin=None):
    """checkin: link do formulário de check-in com o nome do paciente (vira a aba Check-in), ou None"""
    avaliacoes = [separar_cmb(a) for a in avaliacoes]
    rows = sorted(({k: a.get(k) for k in KEEP} for a in avaliacoes), key=lambda r: r["dataOrdem"])
    formulas = {a.get("formula_escolhida") for a in avaliacoes if a.get("formula_escolhida")}
    protocolo = " / ".join(PROTOCOLOS.get(f, f) for f in sorted(formulas)) or "não informado"
    t = (open(template, encoding="utf-8").read()
         .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
         .replace("__PLANO__", json.dumps(plano, ensure_ascii=False))
         .replace("__CHECKIN__", json.dumps(checkin))
         .replace("__NOME__", nome.strip())
         .replace("__PROTOCOLO__", protocolo)
         .replace("__PROFISSIONAL__", PROFISSIONAL))
    return t


if __name__ == "__main__":
    template, src, nome, out = sys.argv[1:5]
    plano = json.load(open(sys.argv[5], encoding="utf-8")) if len(sys.argv) > 5 else None
    d = json.load(open(src, encoding="utf-8"))
    p = [x for x in d["pacientes"] if nome in x["nome"]][0]
    n, tam = montar(template, p["nome"], p["avaliacoes"], plano, out)
    print(n, "avaliacoes", tam, "bytes")
