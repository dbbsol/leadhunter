# Preparacao inicial (PowerShell). Uso:  .\setup.ps1
$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -q -r requirements-dev.txt
if (-not (Test-Path .streamlit\secrets.toml)) {
    Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
    $secret = python -c "import secrets;print(secrets.token_urlsafe(32))"
    $path = (Resolve-Path .streamlit\secrets.toml).Path
    $text = [System.IO.File]::ReadAllText($path).Replace("TROQUE-POR-UMA-STRING-ALEATORIA-LONGA", $secret)
    # grava UTF-8 SEM BOM (o BOM quebra a leitura do TOML)
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Criado .streamlit\secrets.toml com cookie_secret gerado. Agora preencha o restante (SETUP_GUIDE.md)." -ForegroundColor Green
    code .streamlit\secrets.toml 2>$null
} else { Write-Host "secrets.toml ja existe - mantido." -ForegroundColor Yellow }
Write-Host "Proximo passo: python scripts\json_para_toml.py <caminho do JSON>" -ForegroundColor Cyan
