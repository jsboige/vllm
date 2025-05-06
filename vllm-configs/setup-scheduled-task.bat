@echo off
setlocal enabledelayedexpansion

echo Configuration d'une tâche planifiée pour la mise à jour de vLLM...

REM Définir le chemin du script WSL
set WSL_SCRIPT_PATH=/mnt/d/vllm/vllm-configs/update-vllm.sh

REM Créer le fichier XML de la tâche planifiée
echo ^<?xml version="1.0" encoding="UTF-16"?^> > vllm-updater-task.xml
echo ^<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^> >> vllm-updater-task.xml
echo   ^<RegistrationInfo^> >> vllm-updater-task.xml
echo     ^<Date^>%date:~10,4%-%date:~4,2%-%date:~7,2%T%time:~0,2%:%time:~3,2%:%time:~6,2%^</Date^> >> vllm-updater-task.xml
echo     ^<Author^>%USERNAME%^</Author^> >> vllm-updater-task.xml
echo     ^<Description^>Tâche de mise à jour automatique pour vLLM et ses modèles^</Description^> >> vllm-updater-task.xml
echo   ^</RegistrationInfo^> >> vllm-updater-task.xml
echo   ^<Triggers^> >> vllm-updater-task.xml
echo     ^<CalendarTrigger^> >> vllm-updater-task.xml
echo       ^<StartBoundary^>%date:~10,4%-%date:~4,2%-%date:~7,2%T03:00:00^</StartBoundary^> >> vllm-updater-task.xml
echo       ^<Enabled^>true^</Enabled^> >> vllm-updater-task.xml
echo       ^<ScheduleByWeek^> >> vllm-updater-task.xml
echo         ^<DaysOfWeek^> >> vllm-updater-task.xml
echo           ^<Sunday /^> >> vllm-updater-task.xml
echo         ^</DaysOfWeek^> >> vllm-updater-task.xml
echo         ^<WeeksInterval^>1^</WeeksInterval^> >> vllm-updater-task.xml
echo       ^</ScheduleByWeek^> >> vllm-updater-task.xml
echo     ^</CalendarTrigger^> >> vllm-updater-task.xml
echo   ^</Triggers^> >> vllm-updater-task.xml
echo   ^<Principals^> >> vllm-updater-task.xml
echo     ^<Principal id="Author"^> >> vllm-updater-task.xml
echo       ^<LogonType^>InteractiveToken^</LogonType^> >> vllm-updater-task.xml
echo       ^<RunLevel^>HighestAvailable^</RunLevel^> >> vllm-updater-task.xml
echo     ^</Principal^> >> vllm-updater-task.xml
echo   ^</Principals^> >> vllm-updater-task.xml
echo   ^<Settings^> >> vllm-updater-task.xml
echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^> >> vllm-updater-task.xml
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^> >> vllm-updater-task.xml
echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^> >> vllm-updater-task.xml
echo     ^<AllowHardTerminate^>true^</AllowHardTerminate^> >> vllm-updater-task.xml
echo     ^<StartWhenAvailable^>true^</StartWhenAvailable^> >> vllm-updater-task.xml
echo     ^<RunOnlyIfNetworkAvailable^>true^</RunOnlyIfNetworkAvailable^> >> vllm-updater-task.xml
echo     ^<IdleSettings^> >> vllm-updater-task.xml
echo       ^<StopOnIdleEnd^>false^</StopOnIdleEnd^> >> vllm-updater-task.xml
echo       ^<RestartOnIdle^>false^</RestartOnIdle^> >> vllm-updater-task.xml
echo     ^</IdleSettings^> >> vllm-updater-task.xml
echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^> >> vllm-updater-task.xml
echo     ^<Enabled^>true^</Enabled^> >> vllm-updater-task.xml
echo     ^<Hidden^>false^</Hidden^> >> vllm-updater-task.xml
echo     ^<RunOnlyIfIdle^>false^</RunOnlyIfIdle^> >> vllm-updater-task.xml
echo     ^<DisallowStartOnRemoteAppSession^>false^</DisallowStartOnRemoteAppSession^> >> vllm-updater-task.xml
echo     ^<UseUnifiedSchedulingEngine^>true^</UseUnifiedSchedulingEngine^> >> vllm-updater-task.xml
echo     ^<WakeToRun^>false^</WakeToRun^> >> vllm-updater-task.xml
echo     ^<ExecutionTimeLimit^>PT1H^</ExecutionTimeLimit^> >> vllm-updater-task.xml
echo     ^<Priority^>7^</Priority^> >> vllm-updater-task.xml
echo   ^</Settings^> >> vllm-updater-task.xml
echo   ^<Actions Context="Author"^> >> vllm-updater-task.xml
echo     ^<Exec^> >> vllm-updater-task.xml
echo       ^<Command^>C:\Windows\System32\wsl.exe^</Command^> >> vllm-updater-task.xml
echo       ^<Arguments^>bash -c "%WSL_SCRIPT_PATH% --auto"^</Arguments^> >> vllm-updater-task.xml
echo       ^<WorkingDirectory^>/mnt/d/vllm/vllm-configs^</WorkingDirectory^> >> vllm-updater-task.xml
echo     ^</Exec^> >> vllm-updater-task.xml
echo   ^</Actions^> >> vllm-updater-task.xml
echo ^</Task^> >> vllm-updater-task.xml

REM Créer la tâche planifiée
schtasks /create /tn "vLLM Updater" /xml vllm-updater-task.xml

if %errorlevel% equ 0 (
    echo Tâche planifiée créée avec succès.
    echo La tâche s'exécutera tous les dimanches à 3h du matin.
    del vllm-updater-task.xml
) else (
    echo Erreur lors de la création de la tâche planifiée.
    echo Veuillez vérifier les permissions et réessayer.
)

pause