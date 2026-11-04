"""Importa a planilha de suplementação para o sistema (aba Suplementação do editor de planos).

Lê protocolos (doses, impacto, mecanismo, efeitos), categorias, a matriz suplemento x modalidade (abas Suplementos A
e B), as cepas de probióticos, a dose de saturação da creatina e as tabelas de carboidratos, e grava
sistema/suplementos.json. Os dados do atleta (aba Cadastro) não são lidos.

Uso: python scripts/importar_suplementos.py ["caminho da planilha.xlsx"]
     (padrão: Downloads/Planilha_Suplementacao_Atletas_Final.xlsx)
Rodar de novo sempre que mudar a planilha.
"""
import json, re, sys, unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl

RAIZ = Path(__file__).resolve().parent.parent
PADRAO = Path.home() / "Downloads" / "Planilha_Suplementacao_Atletas_Final.xlsx"
SAIDA = RAIZ / "sistema" / "suplementos.json"
# cabeçalho da matriz que não tem o mesmo nome do protocolo
APELIDOS = {"sodio": "repositor de eletrolitos"}
# lacunas da planilha: unidade e texto de dose de quem não tem número
UNIDADE_FALTANDO = {"fibras": "g/dia"}
TEXTO_FALTANDO = {"ferro": "Definir pelos exames (ferritina)", "vitamina_e": "Não recomendada para desempenho",
                  "probioticos": "Conforme a cepa escolhida"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def chave(s):
    return re.sub(r"[^a-z0-9]+", "_", norm(s)).strip("_")


def numero(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def faixa(txt):
    """"3–5" / "10-12" / "1-1.2 por h" -> [3, 5]"""
    m = re.findall(r"\d+(?:[.,]\d+)?", str(txt or ""))
    return [float(x.replace(",", ".")) for x in m[:2]] if m else None


def texto(v):
    return re.sub(r"[ \t]+", " ", str(v)).strip() if v not in (None, "") else ""


def importar(arquivo):
    wb = openpyxl.load_workbook(arquivo, data_only=False)
    pr = wb["Protocolos"]
    # categoria de cada protocolo, pela aba Suplementação (coluna F aponta para a linha do protocolo)
    categorias = {}
    su = wb["Suplementação"]
    for r in range(2, su.max_row + 1):
        m = re.match(r"=Protocolos!A(\d+)", str(su[f"F{r}"].value or ""))
        if m and su[f"G{r}"].value:
            categorias[int(m.group(1))] = texto(su[f"G{r}"].value)

    suplementos = []
    for r in range(3, pr.max_row + 1):
        nome_bruto = texto(pr[f"A{r}"].value)
        if not nome_bruto:
            continue
        m = re.match(r"(.*?)\s*\(([^)]*)\)\s*$", nome_bruto)
        nome, unidade = (m.group(1), m.group(2)) if m else (nome_bruto, "")
        doses = [numero(pr[f"{c}{r}"].value) for c in "BCDE"]
        doses = [d for d in doses if d is not None]
        texto_dose = "" if doses else texto(pr[f"B{r}"].value).replace("---", "")
        k = chave(nome)
        unidade = unidade or UNIDADE_FALTANDO.get(k, "")
        texto_dose = texto_dose or ("" if doses else TEXTO_FALTANDO.get(k, ""))
        suplementos.append({
            "chave": k, "nome": nome, "unidade": unidade, "por_kg": "/kg" in unidade,
            "doses": doses, "texto_dose": texto_dose, "categoria": categorias.get(r, ""),
            "impacto": texto(pr[f"F{r}"].value), "mecanismo": texto(pr[f"M{r}"].value),
            "efeitos": texto(pr[f"Q{r}"].value).replace("---", ""),
        })
    por_nome = {norm(s["nome"]): s["chave"] for s in suplementos}

    # matriz suplemento x modalidade (abas Suplementos A e B): ✔️ = indicado
    modalidades = {}
    for aba in ("Suplementos A x Modalidades", "Suplementos B"):
        ws = wb[aba]
        colunas = {}
        for c in ws[2][2:]:
            if c.value:
                n = norm(c.value)
                colunas[c.column_letter] = por_nome.get(APELIDOS.get(n, n))
        grupo = ""
        for r in range(3, ws.max_row + 1):
            grupo = texto(ws[f"A{r}"].value) or grupo
            mod = texto(ws[f"B{r}"].value)
            if not mod:
                continue
            item = modalidades.setdefault(mod, {"grupo": grupo, "indicados": []})
            for col, k in colunas.items():
                if k and "✔" in str(ws[f"{col}{r}"].value or "") and k not in item["indicados"]:
                    item["indicados"].append(k)

    # cepas de probióticos
    cepas = []
    pb = wb["🧬Formulação de probióticos"]
    for r in range(9, pb.max_row + 1):
        if pb[f"A{r}"].value:
            cepas.append({"cepa": texto(pb[f"A{r}"].value), "dose": texto(pb[f"B{r}"].value),
                          "uso": texto(pb[f"C{r}"].value), "obs": texto(pb[f"D{r}"].value)})

    cr = wb["🔬 Saturação de Creatina"]
    saturacao = {"g_kg_dia": numero(cr["B9"].value) or 0.3, "dias": int(numero(cr["B8"].value) or 5)}

    cb = wb["🏆 Reposição de Carboidratos"]
    diario = [{"nivel": texto(cb[f"A{r}"].value), "descricao": texto(cb[f"B{r}"].value),
               "g_kg": faixa(cb[f"C{r}"].value), "obs": texto(cb[f"F{r}"].value)}
              for r in range(9, 13) if cb[f"A{r}"].value]
    prova = []
    for r in range(16, 21):
        if not cb[f"A{r}"].value:
            continue
        rec = texto(cb[f"C{r}"].value)
        prova.append({"fase": texto(cb[f"A{r}"].value), "objetivo": texto(cb[f"B{r}"].value), "recomendacao": rec,
                      "g_kg": faixa(cb[f"D{r}"].value) if "kg" in rec else None,
                      "por_hora": "/h" in rec, "obs": texto(cb[f"F{r}"].value)})

    return {"fonte": Path(arquivo).name, "importado_em": datetime.now().isoformat(timespec="minutes"),
            "suplementos": suplementos, "modalidades": modalidades, "cepas": cepas, "saturacao_creatina": saturacao,
            "carboidratos": {"diario": diario, "prova": prova}}


if __name__ == "__main__":
    arq = Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO
    dados = importar(arq)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(dados['suplementos'])} suplementos, {len(dados['modalidades'])} modalidades, "
          f"{len(dados['cepas'])} cepas -> {SAIDA}")
