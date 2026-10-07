@echo off
cd /d "%~dp0"
set "CSV="
for %%f in (*Rebanhos*.csv) do set "CSV=%%f"
if "%CSV%"=="" (
  echo Nao achei o CSV de rebanho nesta pasta.
  pause
  exit /b 1
)
echo Usando o arquivo: %CSV%
echo.
python carregar_rebanho.py "%CSV%" --substituir
if errorlevel 1 (
  echo.
  echo DEU ERRO na carga. Copie a mensagem acima e envie para ajuda.
  pause
  exit /b 1
)
python gerar_painel_rebanho.py
if errorlevel 1 (
  echo.
  echo DEU ERRO ao gerar o painel. Copie a mensagem acima e envie para ajuda.
  pause
  exit /b 1
)
echo.
echo Pronto! Abrindo o painel de rebanho...
start "" "painel_rebanho_ceara.html"
pause
