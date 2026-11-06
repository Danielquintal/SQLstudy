"""Licença de uso: cada instalação precisa de uma chave de ativação feita para aquele computador.

  - Código do computador: tirado do identificador do Windows (MachineGuid), embaralhado: XXXX-XXXX-XXXX.
  - Chave de ativação: os dados da licença (nome, registro, computador, validade) + assinatura Ed25519. Só quem tem a
    chave secreta (ferramentas/licenca/chave_privada.pem, que fica só no computador do autor) consegue emitir; o
    sistema confere com a chave pública abaixo. Copiar a pasta para outro computador: pede nova ativação.
  - Validade: data e hora; vencida, o sistema bloqueia o acesso até receber uma chave nova.
  - Relógio: guarda a maior data já vista; se o relógio do Windows voltar mais de 1 dia, bloqueia.
  - Termo de uso: aceito na ativação (data guardada em sistema/licenca_estado.json).
"""
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ_CHAVE = RAIZ / "sistema" / "licenca.chave"
ARQ_ESTADO = RAIZ / "sistema" / "licenca_estado.json"
PRIVADA = RAIZ / "ferramentas" / "licenca" / "chave_privada.pem"
EMITIDAS = RAIZ / "ferramentas" / "licenca" / "emitidas.json"
PUBLICA = "7wicUR4usCzWDv8BiIfl4zuq/0pLbCNNvpljwaWkbkc="
PREFIXO = "RA1"
FOLGA_RELOGIO = timedelta(days=1)


def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------- computador ----------

def codigo_maquina():
    """XXXX-XXXX-XXXX, igual sempre neste Windows (muda se o Windows for reinstalado)"""
    guid = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
            guid = winreg.QueryValueEx(k, "MachineGuid")[0]
    except OSError:
        guid = os.environ.get("COMPUTERNAME", "") + os.environ.get("PROCESSOR_IDENTIFIER", "")
    d = base64.b32encode(hashlib.sha256(f"licenca:{guid}".encode()).digest()).decode()
    d = d.replace("0", "").replace("1", "").replace("O", "").replace("I", "")
    return "-".join(d[i:i + 4] for i in range(0, 12, 4))


# ---------- chave ----------

def ler_chave(chave):
    """texto colado -> (dados, assinatura) ou erro ValueError"""
    partes = "".join(str(chave or "").split()).split(".")
    if len(partes) != 3 or partes[0] != PREFIXO:
        raise ValueError("a chave não está completa (copie a chave inteira, do RA1 até o fim)")
    try:
        corpo, assin = _unb64(partes[1]), _unb64(partes[2])
        return json.loads(corpo.decode("utf-8")), corpo, assin
    except (ValueError, UnicodeDecodeError):
        raise ValueError("a chave está corrompida (copie de novo)") from None


def conferir(chave, maquina=None, agora=None):
    """devolve os dados da licença se a chave vale neste computador agora; senão ValueError com o motivo"""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    dados, corpo, assin = ler_chave(chave)
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLICA)).verify(assin, corpo)
    except InvalidSignature:
        raise ValueError("chave inválida (não foi emitida pelo autor do sistema)") from None
    if dados.get("maquina") != (maquina or codigo_maquina()):
        raise ValueError(f"esta chave é de outro computador ({dados.get('maquina')}); este é {maquina or codigo_maquina()}")
    ate = dados.get("ate")
    if ate and (agora or datetime.now()) > datetime.fromisoformat(ate):
        raise ValueError(f"licença vencida em {datetime.fromisoformat(ate):%d/%m/%Y às %H:%M}")
    return dados


# ---------- estado deste computador ----------

def _estado():
    try:
        return json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _gravar_estado(**mudou):
    e = _estado()
    e.update(mudou)
    ARQ_ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")


def situacao():
    """{"ok": bool, "motivo": texto, "dados": {...} ou None, "restante": timedelta ou None}"""
    agora = datetime.now()
    try:
        chave = ARQ_CHAVE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return {"ok": False, "motivo": "Este computador ainda não foi ativado.", "dados": None, "restante": None}
    e = _estado()
    maior = e.get("maior_data")
    if maior and agora < datetime.fromisoformat(maior) - FOLGA_RELOGIO:
        return {"ok": False, "dados": None, "restante": None,
                "motivo": "A data do Windows está atrasada. Acerte a data e a hora do computador e abra de novo."}
    try:
        dados = conferir(chave, agora=agora)
    except ValueError as erro:
        try:
            dados = ler_chave(chave)[0]
        except ValueError:
            dados = None
        return {"ok": False, "motivo": str(erro)[0].upper() + str(erro)[1:] + ".", "dados": dados, "restante": None}
    if not maior or agora > datetime.fromisoformat(maior):
        _gravar_estado(maior_data=agora.isoformat(timespec="seconds"))
    ate = dados.get("ate")
    return {"ok": True, "motivo": "", "dados": dados, "restante": (datetime.fromisoformat(ate) - agora) if ate else None}


def ativar(chave, aceite_termo):
    """confere e grava a chave deste computador; devolve os dados ou ValueError"""
    if not aceite_termo:
        raise ValueError("é preciso ler e aceitar o termo de uso")
    dados = conferir(chave)
    ARQ_CHAVE.write_text("".join(chave.split()), encoding="utf-8")
    _gravar_estado(termo_aceito_em=datetime.now().isoformat(timespec="seconds"), termo_versao=TERMO_VERSAO)
    return dados


def dados_licenca():
    """nome e registro travados pela licença (ou {} sem licença válida)"""
    s = situacao()
    return s["dados"] if s["ok"] else {}


# ---------- emissão (só no computador do autor, que tem a chave secreta) ----------

def pode_emitir():
    return PRIVADA.exists()


def emitir(maquina, nome, registro="", dias=2, permanente=False, licenciante="", contato=""):
    from cryptography.hazmat.primitives import serialization
    maquina = maquina.strip().upper()
    if len(maquina.replace("-", "")) != 12:
        raise ValueError("o código do computador tem 12 letras e números (XXXX-XXXX-XXXX)")
    if not nome.strip():
        raise ValueError("preencha o nome do profissional")
    agora = datetime.now()
    dados = {"v": 1, "nome": nome.strip(), "registro": registro.strip(), "maquina": maquina,
             "emitida": agora.isoformat(timespec="seconds"),
             "ate": None if permanente else (agora + timedelta(days=float(dias))).isoformat(timespec="seconds"),
             "licenciante": licenciante.strip(), "contato": contato.strip()}
    corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    privada = serialization.load_pem_private_key(PRIVADA.read_bytes(), password=None)
    chave = f"{PREFIXO}.{_b64(corpo)}.{_b64(privada.sign(corpo))}"
    try:
        lista = json.loads(EMITIDAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        lista = []
    lista.insert(0, {**dados, "chave": chave})
    EMITIDAS.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    return chave, dados


def emitidas():
    try:
        return json.loads(EMITIDAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


TERMO_VERSAO = 1
TERMO = """TERMO DE USO DO SISTEMA

1. Esta licença é pessoal e intransferível: vale só para o profissional e o computador indicados na chave de ativação.
2. É proibido copiar, repassar, emprestar, vender, publicar ou instalar o sistema em outro computador sem uma chave
   emitida pelo autor, e também modificar, descompilar ou retirar a verificação de licença.
3. O sistema e o seu código continuam sendo do autor (Lei nº 9.609/1998, Lei do Software). Esta licença dá apenas o
   direito de uso, pelo prazo da chave.
4. Os dados dos pacientes cadastrados ficam neste computador e são de responsabilidade do profissional licenciado,
   que é o controlador desses dados perante a LGPD (Lei nº 13.709/2018). O autor não tem acesso a eles.
5. Ao fim da validade, o acesso ao sistema é bloqueado até a renovação. Os dados continuam guardados neste computador.
6. O sistema é fornecido como está, para teste e uso profissional, sem garantia de funcionamento ininterrupto.
   Faça cópias de segurança.
7. O descumprimento deste termo encerra a licença, sem prejuízo das medidas legais cabíveis."""
