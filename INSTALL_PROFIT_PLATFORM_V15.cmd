@echo off
setlocal EnableExtensions
title Profit Platform v15 installer

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"
where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed or is not in PATH.
  pause
  exit /b 1
)

set "REPO_URL=https://github.com/MrVampir4eg/youtube-automation.git"
set "WORK_DIR=%TEMP%\youtube-automation-profit-v15"

if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
echo Cloning the base repository...
git clone --depth 1 "%REPO_URL%" "%WORK_DIR%"
if errorlevel 1 goto :error

pushd "%WORK_DIR%"
for /f "delims=" %%H in ('git rev-parse --short HEAD') do set "BASE_COMMIT=%%H"
set "BACKUP_BRANCH=backup/pre-profit-v15-%RANDOM%%RANDOM%"
echo Creating a remote backup of current main: %BACKUP_BRANCH%...
git branch "%BACKUP_BRANCH%"
if errorlevel 1 goto :backup_error_pop
git push origin "%BACKUP_BRANCH%"
if errorlevel 1 goto :backup_error_pop
popd

echo Applying the complete v15 update...
set "UPDATE_DIR=%SCRIPT_DIR%\update"
if not exist "%UPDATE_DIR%\." set "UPDATE_DIR=%SCRIPT_DIR%"
if not exist "%UPDATE_DIR%\." (
  echo Update directory was not found beside the installer.
  goto :error
)
robocopy "%UPDATE_DIR%\." "%WORK_DIR%\." /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :error

pushd "%WORK_DIR%"
git add --all
git diff --cached --quiet
if not errorlevel 1 (
  echo No changes to commit. The update may already be installed.
  popd
  goto :done
)

git config user.name "Profit Platform Installer"
git config user.email "installer@localhost"
git commit -m "Install profit-first automation platform v15"
if errorlevel 1 goto :error_pop
git push origin HEAD:main
if errorlevel 1 goto :error_pop
popd

:done
echo.
echo DONE. Render will deploy from the updated main branch if it is connected.
echo Read README_FIRST_V15.txt and configure Render/GitHub secrets before the first run.
pause
exit /b 0

:error_pop
popd
:error
echo.
echo INSTALL FAILED. Check GitHub access, repository permissions, and Git output above.
pause
exit /b 1

:backup_error_pop
popd
echo.
echo INSTALL STOPPED: the safety backup branch could not be pushed.
echo No files were changed and no update commit was created.
pause
exit /b 1
