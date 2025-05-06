@echo off
setlocal enabledelayedexpansion

:: Définition des couleurs pour les messages
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

:: Fonction pour afficher l'aide
:show_help
echo %BLUE%Usage: %0 [options]%NC%
echo.
echo Options:
echo   -h, --help                Affiche cette aide
echo   -a, --all                 Exécute tous les tests
echo   -c, --connection          Teste la connexion aux services
echo   -g, --generation          Teste la génération de texte
echo   -t, --tools               Teste l'utilisation d'outils
echo   -r, --reasoning           Teste le raisonnement
echo   -b, --benchmark           Effectue un benchmark de performance
echo   -p, --parallel            Teste le traitement parallèle
echo   --repeats N               Nombre de répétitions pour le benchmark (défaut: 3)
echo   --parallel-requests N     Nombre de requêtes parallèles (défaut: 5)
echo.
echo Exemples:
echo   %0 --all                  Exécute tous les tests
echo   %0 -c -g                  Teste la connexion et la génération de texte
echo   %0 -b --repeats 5         Effectue un benchmark avec 5 répétitions
echo.
goto :eof

:: Vérifier si Python est installé
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo %RED%Python n'est pas installé ou n'est pas dans le PATH. Veuillez l'installer avant d'utiliser ce script.%NC%
    exit /b 1
)

:: Vérifier si le script Python existe
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%test_vllm_services.py"

if not exist "%PYTHON_SCRIPT%" (
    echo %RED%Le script Python n'existe pas: %PYTHON_SCRIPT%%NC%
    exit /b 1
)

:: Vérifier si les dépendances Python sont installées
echo %BLUE%Vérification des dépendances Python...%NC%
python -c "import requests, dotenv, aiohttp, openai" 2>nul
if %ERRORLEVEL% neq 0 (
    echo %YELLOW%Installation des dépendances Python...%NC%
    pip install requests python-dotenv aiohttp openai
    if %ERRORLEVEL% neq 0 (
        echo %RED%Échec de l'installation des dépendances. Veuillez les installer manuellement:%NC%
        echo pip install requests python-dotenv aiohttp openai
        exit /b 1
    )
)

:: Vérifier si le fichier .env existe
if not exist "%SCRIPT_DIR%..\.env" (
    echo %YELLOW%Le fichier .env n'existe pas. Création d'un fichier .env par défaut...%NC%
    (
        echo # Configuration des endpoints pour les tests vLLM
        echo OPENAI_ENDPOINT_NAME_2="Local Model - Micro"
        echo OPENAI_API_KEY_2=32885271D7845A3839F1AE0274676D87
        echo OPENAI_BASE_URL_2="https://api.micro.text-generation-webui.myia.io/v1"
        echo OPENAI_CHAT_MODEL_ID_2="Qwen/Qwen3-4B-AWQ"
        echo.
        echo OPENAI_ENDPOINT_NAME_3="Local Model - Mini"
        echo OPENAI_API_KEY_3=0EO6JAQITAL2Q0LW0ZUVA55W3YNCX4W9
        echo OPENAI_BASE_URL_3="https://api.mini.text-generation-webui.myia.io/v1"
        echo OPENAI_CHAT_MODEL_ID_3="Qwen/Qwen3-8B-AWQ"
        echo.
        echo OPENAI_ENDPOINT_NAME_4="Local Model - Medium"
        echo OPENAI_API_KEY_4=X0EC4YYP068CPD5TGARP9VQB5U4MAGHY
        echo OPENAI_BASE_URL_4="https://api.medium.text-generation-webui.myia.io/v1"
        echo OPENAI_CHAT_MODEL_ID_4="Qwen/Qwen3-30B-A3B"
    ) > "%SCRIPT_DIR%..\.env"
    echo %GREEN%Fichier .env créé avec succès.%NC%
)

:: Traitement des arguments
set "PYTHON_ARGS="

:parse_args
if "%~1"=="" goto run_tests
if "%~1"=="-h" (
    call :show_help
    exit /b 0
)
if "%~1"=="--help" (
    call :show_help
    exit /b 0
)
if "%~1"=="-a" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --all"
    shift
    goto parse_args
)
if "%~1"=="--all" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --all"
    shift
    goto parse_args
)
if "%~1"=="-c" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --connection"
    shift
    goto parse_args
)
if "%~1"=="--connection" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --connection"
    shift
    goto parse_args
)
if "%~1"=="-g" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --generation"
    shift
    goto parse_args
)
if "%~1"=="--generation" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --generation"
    shift
    goto parse_args
)
if "%~1"=="-t" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --tools"
    shift
    goto parse_args
)
if "%~1"=="--tools" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --tools"
    shift
    goto parse_args
)
if "%~1"=="-r" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --reasoning"
    shift
    goto parse_args
)
if "%~1"=="--reasoning" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --reasoning"
    shift
    goto parse_args
)
if "%~1"=="-b" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --benchmark"
    shift
    goto parse_args
)
if "%~1"=="--benchmark" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --benchmark"
    shift
    goto parse_args
)
if "%~1"=="-p" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --parallel"
    shift
    goto parse_args
)
if "%~1"=="--parallel" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --parallel"
    shift
    goto parse_args
)
if "%~1"=="--repeats" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --repeats %~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--parallel-requests" (
    set "PYTHON_ARGS=!PYTHON_ARGS! --parallel-requests %~2"
    shift
    shift
    goto parse_args
)

echo %RED%Option inconnue: %~1%NC%
call :show_help
exit /b 1

:run_tests
:: Si aucun argument n'est spécifié, exécuter tous les tests
if "%PYTHON_ARGS%"=="" set "PYTHON_ARGS=--all"

:: Exécuter le script Python
echo %GREEN%Exécution des tests...%NC%
echo %BLUE%Commande: python "%PYTHON_SCRIPT%" %PYTHON_ARGS%%NC%
echo.

python "%PYTHON_SCRIPT%" %PYTHON_ARGS%

:: Vérifier le code de retour
if %ERRORLEVEL% equ 0 (
    echo %GREEN%Tests terminés avec succès.%NC%
) else (
    echo %RED%Les tests ont échoué.%NC%
    exit /b 1
)

exit /b 0