"""Quem usa o sistema: nome, profissão, registro (CRN) e marca, em sistema/identidade.json (fora do config.json,
que o sistema regrava inteiro; e fora do GitHub e do pacote de instalação, que levam só o código).

Tudo o que aparece com o nome do profissional (cabeçalho, planos, páginas dos pacientes, mensagens padrão, e-mails)
vem daqui, para o mesmo sistema servir a qualquer profissional. Preenchido na tela de boas-vindas / Configuração.
"""
import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "sistema" / "identidade.json"
PADRAO = {"nome": "", "profissao": "Nutricionista", "registro": "", "marca": ""}
MARCA_PADRAO = "Atendimento nutricional"


def dados():
    d = dict(PADRAO)
    try:
        d.update(json.loads(ARQUIVO.read_text(encoding="utf-8")) or {})
    except (FileNotFoundError, ValueError):
        pass
    d = {k: str(d.get(k) or "").strip() for k in PADRAO}
    try:                                  # com licença, nome e registro são os dela (travados)
        import licenca
        lic = licenca.dados_licenca()
        if lic.get("nome"):
            d["nome"], d["registro"] = lic["nome"], lic.get("registro") or d["registro"]
    except Exception:   # noqa: BLE001 — sem a biblioteca de criptografia, fica o que está no arquivo
        pass
    return d


def salvar(novo):
    d = dados()
    d.update({k: str(novo.get(k, d[k]) or "").strip() for k in PADRAO})
    ARQUIVO.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def preenchida():
    return bool(dados()["nome"])


def nome():
    return dados()["nome"]


def marca():
    d = dados()
    return d["marca"] or d["nome"] or MARCA_PADRAO


def linha():
    """"Nome · Profissão" (cabeçalho, remetente dos e-mails, agenda)"""
    d = dados()
    return " · ".join(x for x in (d["nome"], d["profissao"]) if x)


def completo():
    """"Nome · Profissão · Registro" (rodapé dos planos alimentares)"""
    d = dados()
    return " · ".join(x for x in (d["nome"], d["profissao"], d["registro"]) if x)


def assinatura():
    """"Nome, profissão" (fim das mensagens padrão)"""
    d = dados()
    return ", ".join(x for x in (d["nome"], d["profissao"].lower()) if x)
