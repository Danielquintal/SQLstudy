"""Instalação e atualização do banco (usado pelo Instalar.bat do pacote para outros profissionais).

  python scripts/instalar_banco.py            cria o banco (se não existir), aplica as mudanças de estrutura que
                                              faltam (sql/NN_*.sql, em ordem) e carrega a TACO se estiver vazia
  python scripts/instalar_banco.py --atalho   também cria o atalho na Área de Trabalho

Anota cada arquivo aplicado na tabela "migracao": rodar de novo (ou numa atualização do pacote) só aplica os novos.
A conexão vem de SISTEMA_CONEXAO ou do padrão (localhost, usuário postgres, senha no pgpass.conf).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import psycopg  # noqa: E402
from atualizar_paciente import CONEXAO  # noqa: E402

PULAR = re.compile(r"02_dados|_desfazer")      # dados de exemplo / desfazer: nunca numa instalação nova


def _sem_banco(conexao):
    return " ".join(p for p in conexao.split() if not p.startswith("dbname=")) + " dbname=postgres"


def nome_banco(conexao):
    m = re.search(r"dbname=(\S+)", conexao)
    return m.group(1) if m else "atendimento_nutricional"


def criar_banco(conexao=CONEXAO):
    nome = nome_banco(conexao)
    with psycopg.connect(_sem_banco(conexao), autocommit=True) as c:
        if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,)).fetchone():
            return False
        c.execute(f'CREATE DATABASE "{nome}" ENCODING \'UTF8\' TEMPLATE template0')
        return True


def arquivos():
    return [a for a in sorted((RAIZ / "sql").glob("[0-9][0-9]_*.sql")) if not PULAR.search(a.name)]


def aplicar(conexao=CONEXAO):
    """aplica, em ordem, os arquivos sql que ainda não foram aplicados neste banco; devolve a lista aplicada"""
    feitos = []
    with psycopg.connect(conexao) as c:
        tinha_registro = c.execute("SELECT to_regclass('migracao')").fetchone()[0]
        banco_antigo = c.execute("SELECT to_regclass('paciente')").fetchone()[0]
        c.execute("CREATE TABLE IF NOT EXISTS migracao (arquivo text PRIMARY KEY, aplicada_em timestamptz DEFAULT now())")
        if banco_antigo and not tinha_registro:
            # banco que já existia antes do instalador (mantido à mão e em dia): só anota
            c.executemany("INSERT INTO migracao (arquivo) VALUES (%s) ON CONFLICT DO NOTHING", [(a.name,) for a in arquivos()])
            c.commit()
            print("Banco já existente: estrutura anotada como em dia (nada foi recriado).")
            return []
        ja = {a for a, in c.execute("SELECT arquivo FROM migracao")}
        c.commit()
        for arq in arquivos():
            if arq.name in ja:
                continue
            with c.transaction():
                c.execute(arq.read_text(encoding="utf-8"))
                c.execute("INSERT INTO migracao (arquivo) VALUES (%s)", (arq.name,))
            feitos.append(arq.name)
    return feitos


def taco_vazia(conexao=CONEXAO):
    with psycopg.connect(conexao) as c:
        return not c.execute("SELECT 1 FROM alimento WHERE fonte = 'TACO' LIMIT 1").fetchone()


def carregar_taco(conexao=CONEXAO):
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "carregar_taco.py")], check=True,
                   env=dict(os.environ, SISTEMA_CONEXAO=conexao))


def criar_atalho(nome="Atendimento nutricional"):
    """atalho na Área de Trabalho para o Abrir sistema.bat, com o ícone do sistema"""
    bat, icone = RAIZ / "Abrir sistema.bat", RAIZ / "sistema" / "static" / "icone.ico"
    ps = ("$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; "
          f"$a=$w.CreateShortcut((Join-Path $d '{nome}.lnk')); $a.TargetPath='{bat}'; $a.WorkingDirectory='{RAIZ}'; "
          f"$a.IconLocation='{icone}'; $a.WindowStyle=7; $a.Save()")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=True)


def main():
    novo = criar_banco()
    print(f"Banco “{nome_banco(CONEXAO)}” {'criado' if novo else 'já existia'}.")
    feitos = aplicar()
    print(f"Estrutura: {len(feitos)} atualização(ões) aplicada(s)." if feitos else "Estrutura: já estava em dia.")
    if taco_vazia():
        carregar_taco()
    else:
        print("Tabela TACO: já carregada.")
    if "--atalho" in sys.argv:
        criar_atalho()
        print("Atalho “Atendimento nutricional” criado na Área de Trabalho.")


if __name__ == "__main__":
    main()
