# Instalador do sistema de atendimento nutricional (Windows 10/11).
# Aberto pelo Instalar.bat. Pode rodar de novo quantas vezes quiser: só faz o que falta.
#   1. Python 3        (se faltar, instala pelo winget)
#   2. PostgreSQL      (se faltar, instala pelo winget com uma senha aleatória, guardada só neste computador)
#   3. Bibliotecas do Python (requirements.txt)
#   4. Banco de dados: cria, aplica a estrutura e carrega a tabela TACO
#   5. Atalho na Área de Trabalho e abre o sistema
param([switch]$Teste)   # -Teste: não cria atalho nem abre o sistema (para conferir o instalador)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $raiz
$Host.UI.RawUI.WindowTitle = 'Instalação do sistema de atendimento nutricional'

function Passo($n, $texto) { Write-Host ''; Write-Host "[$n/5] $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "      $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "      $texto" -ForegroundColor Yellow }
function Parar($texto) {
    Write-Host ''; Write-Host "Não deu para continuar: $texto" -ForegroundColor Red
    Write-Host 'Feche esta janela, resolva o item acima e abra o Instalar.bat de novo.'
    Read-Host 'Aperte Enter para fechar'; exit 1
}
function Recarregar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Achar-Python {
    # o "python" da Microsoft Store que só abre a loja não serve: testa de verdade
    $candidatos = @()
    foreach ($c in @('python', 'py')) { $g = Get-Command $c -ErrorAction SilentlyContinue; if ($g) { $candidatos += $g.Source } }
    $candidatos += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName
    foreach ($p in $candidatos) {
        try {
            $v = & $p -c "import sys; print(sys.executable if sys.version_info >= (3, 11) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
        } catch {}
    }
    return $null
}
function Achar-Postgres {
    Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name -replace '\D', '') } -Descending | Select-Object -First 1
}
function Guardar-Senha($arq, $senha) {
    # guarda a senha do postgres no pgpass.conf, mantendo outras linhas que já existam
    New-Item -ItemType Directory -Force (Split-Path $arq) | Out-Null
    $linhas = @(); if (Test-Path $arq) { $linhas = @(Get-Content $arq | Where-Object { $_ -notlike 'localhost:5432:`*:postgres:*' }) }
    Set-Content -Path $arq -Encoding ascii -Value ($linhas + "localhost:5432:*:postgres:$senha")
}
function Tem-Winget { [bool](Get-Command winget -ErrorAction SilentlyContinue) }

Write-Host '=== Instalação do sistema de atendimento nutricional ===' -ForegroundColor White
Write-Host 'Pode levar de 5 a 15 minutos na primeira vez. Se o Windows perguntar se permite alterações, responda Sim.'

# ---------- 1. Python ----------
Passo 1 'Python'
$python = Achar-Python
if (-not $python) {
    if (-not (Tem-Winget)) { Parar 'instale o Python 3.13 em https://www.python.org/downloads/ (marque "Add python.exe to PATH").' }
    Aviso 'Instalando o Python 3.13...'
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    Recarregar-Path
    $python = Achar-Python
    if (-not $python) { Parar 'o Python não foi encontrado depois da instalação. Reinicie o computador e rode de novo.' }
}
Ok "Python pronto: $python"

# ---------- 2. PostgreSQL ----------
Passo 2 'Banco de dados (PostgreSQL)'
$pgpass = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
$psql = Achar-Postgres
if (-not $psql) {
    if (-not (Tem-Winget)) { Parar 'instale o PostgreSQL 17 em https://www.postgresql.org/download/windows/ e rode de novo.' }
    $senha = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    Aviso 'Instalando o PostgreSQL 17 (o Windows vai pedir permissão)...'
    winget install -e --id PostgreSQL.PostgreSQL.17 --silent --accept-package-agreements --accept-source-agreements `
        --override "--mode unattended --unattendedmodeui minimal --superpassword $senha --serverport 5432" | Out-Host
    $psql = Achar-Postgres
    if (-not $psql) { Parar 'o PostgreSQL não foi encontrado depois da instalação. Reinicie o computador e rode de novo.' }
    Guardar-Senha $pgpass $senha
    Ok 'Senha do banco criada e guardada só neste computador (pgpass.conf).'
}
# confere se entra no banco; se não tiver a senha guardada, pergunta uma vez
$env:PGCONNECT_TIMEOUT = '10'
& $psql.FullName -h localhost -U postgres -d postgres -w -tAc 'select 1' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Aviso 'O PostgreSQL já estava instalado. Digite a senha do usuário "postgres" (a que foi criada na instalação dele):'
    $s = Read-Host -AsSecureString 'Senha do postgres'
    $senha = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
    Guardar-Senha $pgpass $senha
    & $psql.FullName -h localhost -U postgres -d postgres -w -tAc 'select 1' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Parar 'a senha do postgres não confere (ou o serviço do PostgreSQL está parado).' }
}
Ok "PostgreSQL pronto: $($psql.Directory.Parent.Name)"

# ---------- 3. Bibliotecas ----------
Passo 3 'Bibliotecas do Python'
& $python -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Parar 'a instalação das bibliotecas falhou (confira a internet).' }
Ok 'Bibliotecas instaladas.'

# ---------- 4. Banco do sistema ----------
Passo 4 'Banco do sistema (estrutura e tabela TACO)'
$env:PYTHONIOENCODING = 'utf-8'
if ($Teste) { & $python scripts\instalar_banco.py } else { & $python scripts\instalar_banco.py --atalho }
if ($LASTEXITCODE -ne 0) { Parar 'a preparação do banco falhou (mensagens acima).' }

# ---------- 5. Atalho e abertura ----------
Passo 5 'Pronto!'
if ($Teste) { Ok 'Modo teste: sem atalho e sem abrir o sistema.'; exit 0 }
# o Abrir sistema.bat usa o Python encontrado aqui (não depende do PATH)
Set-Content -Path (Join-Path $raiz 'Abrir sistema.bat') -Encoding ascii -Value @"
@echo off
title Sistema de atendimento nutricional
cd /d "%~dp0"
"$python" sistema\app.py
pause
"@
Ok 'Atalho "Atendimento nutricional" na Área de Trabalho. É por ele que você abre o sistema.'
Write-Host ''
Write-Host 'O sistema vai abrir agora. Na primeira vez, preencha seus dados (nome, profissão, registro).' -ForegroundColor White
Start-Process -FilePath (Join-Path $raiz 'Abrir sistema.bat') -WorkingDirectory $raiz
Read-Host 'Aperte Enter para fechar esta janela'
