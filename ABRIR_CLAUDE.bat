@echo off
REM Abre o Claude Code ja dentro do ViralReplicator.
REM O CLAUDE.md da pasta e carregado sozinho, entao a sessao nova ja comeca
REM sabendo o pipeline, as decisoes tomadas e os erros que nao devem voltar.
title ViralReplicator - Claude Code
cd /d "%~dp0"
echo.
echo  ViralReplicator  ^|  canal alemao (Think Science DE)
echo  ------------------------------------------------------
echo  Leia PLAYBOOK.md para o passo a passo de um video novo.
echo.
"%USERPROFILE%\.local\bin\claude.exe" %*
