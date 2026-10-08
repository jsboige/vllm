' Lanceur cache pour la schtask vllm-po2025-thermal-logger (lane po-2025:vllm) -- NE PAS EDITER A LA MAIN.
' Chantier flicker fleet (mandat user 07/10) : -WindowStyle Hidden affiche conhost PUIS applique le
' style = flash ; Run(cmd, 0, True) passe SW_HIDE dans le STARTUPINFO du CreateProcess -> zero flash.
' Tache : vllm-po2025-thermal-logger (user-level, /5 min, monitor-only - cf. gpu-thermal-logger-po2025.ps1).
Option Explicit
Dim sh, rc
Set sh = CreateObject("WScript.Shell")
rc = sh.Run("powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""D:\dev\vllm\myia_vllm\scripts\gpu-thermal-logger-po2025.ps1""", 0, True)
WScript.Quit rc
