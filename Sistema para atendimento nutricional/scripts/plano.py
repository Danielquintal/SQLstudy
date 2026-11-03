"""Planos alimentares de cada paciente (tabela plano_alimentar, sql/04_plano.sql e 05_varios_planos.sql).

O PDF enviado no sistema vira imagens (uma por página) que a aba Plano alimentar da página de evolução mostra
do jeito que o PDF foi feito. O plano estruturado (refeições, substituições, macros) usa o mesmo campo `plano`.
"""
import base64, io, json

import pypdfium2

ESCALA = 2.0          # 144 dpi: legível no celular sem deixar a página pesada
QUALIDADE = 72        # JPEG
MAX_PAGINAS = 20


def pdf_para_paginas(dados):
    """bytes do PDF -> lista de imagens JPEG em data URI; ValueError se não for um PDF legível"""
    try:
        pdf = pypdfium2.PdfDocument(dados)
    except pypdfium2.PdfiumError:
        raise ValueError("Não consegui abrir o arquivo. Envie um PDF.")
    if len(pdf) == 0:
        raise ValueError("O PDF não tem páginas.")
    if len(pdf) > MAX_PAGINAS:
        raise ValueError(f"O PDF tem {len(pdf)} páginas; o limite é {MAX_PAGINAS}.")
    paginas = []
    for pagina in pdf:
        img = pagina.render(scale=ESCALA).to_pil().convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=QUALIDADE, optimize=True, progressive=True)
        paginas.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    return paginas


PROFISSIONAL = "Daniel Quintal · Nutricionista · CRN3 54937"


def montar_plano(titulo, prescrito, paginas, profissional=PROFISSIONAL):
    """objeto PLANO que o template entende (versão em páginas de PDF)"""
    return {"titulo": titulo, "prescrito": prescrito.strftime("%d/%m/%Y"), "profissional": profissional,
            "paginas": paginas}


def plano_do_banco(cur, pid):
    """lista de planos do paciente (na ordem em que foram enviados) para o template, ou None se não tiver"""
    cur.execute("SELECT plano FROM plano_alimentar WHERE paciente_id = %s ORDER BY id", (pid,))
    planos = [r[0] for r in cur.fetchall()]
    return planos or None


def gravar(cur, pid, titulo, prescrito, nome_arquivo, pdf, plano):
    """acrescenta um plano ao paciente (cada paciente pode ter vários)"""
    cur.execute("""INSERT INTO plano_alimentar (paciente_id, titulo, prescrito, nome_arquivo, pdf, plano)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (pid, titulo, prescrito, nome_arquivo, pdf, json.dumps(plano, ensure_ascii=False)))
