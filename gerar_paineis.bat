@echo off
cd /d "%~dp0"
echo Gerando o painel de GTAs...
python gerar_painel.py
if errorlevel 1 (
  echo.
  echo DEU ERRO no painel de GTAs. Copie a mensagem acima e envie para ajuda.
  pause
  exit /b 1
)
echo.
echo Gerando o painel de rebanho...
python gerar_painel_rebanho.py
if errorlevel 1 (
  echo.
  echo DEU ERRO no painel de rebanho. Copie a mensagem acima e envie para ajuda.
  pause
  exit /b 1
)
echo.
echo Pronto! Abrindo os paineis...
start "" "painel_gta_ceara.html"
start "" "painel_rebanho_ceara.html"
pause
