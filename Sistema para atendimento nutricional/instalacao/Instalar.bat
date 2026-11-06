@echo off
title Instalacao do sistema de atendimento nutricional
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
