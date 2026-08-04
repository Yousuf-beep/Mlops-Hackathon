@echo off
rem ===========================================================================
rem  PulseGrid - Kubernetes dashboard tunnels for Windows
rem
rem  QA and dev each run in their own namespace on the local Docker Desktop
rem  Kubernetes cluster (see k8s\README.md), each behind a fixed NodePort.
rem  Docker Desktop does not reliably auto-forward NodePorts to localhost, so
rem  this script keeps a `kubectl port-forward` open per environment instead
rem  - the port numbers match the NodePorts exactly, so it makes no
rem  difference which mechanism is actually serving the port.
rem
rem  Production is NOT deployed here on purpose - `run.bat` (docker compose)
rem  on http://localhost:5173 is the one production server. See
rem  k8s\README.md if you ever want a second, cluster-hosted copy back.
rem
rem    k8s.bat            check the cluster, then open one tunnel per environment
rem    k8s.bat up         same as above
rem    k8s.bat down       close both tunnel windows
rem    k8s.bat status     show PulseGrid pods across the qa and dev namespaces
rem    k8s.bat help       show this list
rem ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "QA_URL=http://localhost:30092"
set "DEV_URL=http://localhost:30091"
set "EXITCODE=0"

if /i "%~1"==""       goto :cmd_up
if /i "%~1"=="up"     goto :cmd_up
if /i "%~1"=="down"   goto :cmd_down
if /i "%~1"=="status" goto :cmd_status
if /i "%~1"=="help"   goto :usage
if /i "%~1"=="-h"     goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="/?"     goto :usage

echo.
echo   Unknown command: %~1
set "EXITCODE=1"
goto :usage


rem ===========================================================================
:cmd_up
echo.
echo  ==========================================================
echo    PulseGrid - Kubernetes dashboard tunnels
echo  ==========================================================
echo.

where kubectl >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] kubectl not found on PATH - is Docker Desktop's Kubernetes enabled?
    set "EXITCODE=1"
    goto :end
)

kubectl get ns pulsegrid-qa pulsegrid-dev >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] One or more namespaces are missing. Deploy them first:
    echo          kubectl apply -k k8s\overlays\qa
    echo          kubectl apply -k k8s\overlays\dev
    set "EXITCODE=1"
    goto :end
)

echo   Opening one tunnel window per environment - closing a window stops
echo   that tunnel. "k8s.bat down" closes both of them at once.
echo.

start "PulseGrid k8s - qa (30092)"         cmd /k kubectl port-forward -n pulsegrid-qa  svc/pulsegrid-web 30092:80 --address 127.0.0.1
start "PulseGrid k8s - dev (30091)"        cmd /k kubectl port-forward -n pulsegrid-dev svc/pulsegrid-web 30091:80 --address 127.0.0.1

echo    QA                          %QA_URL%
echo    Dev                         %DEV_URL%
echo    Production (docker compose) http://localhost:5173  ^(run.bat, not this script^)
echo.
echo    Stop everything    k8s.bat down
echo    Pod status          k8s.bat status
echo.
goto :end


rem ===========================================================================
:cmd_down
echo.
echo  Closing PulseGrid Kubernetes tunnel windows...
taskkill /FI "WINDOWTITLE eq PulseGrid k8s*" /T /F >nul 2>&1
echo  Done. The Deployments/Pods themselves are untouched - only the local
echo  tunnels were closed.
echo.
goto :end


rem ===========================================================================
:cmd_status
echo.
echo  -- qa --
kubectl get pods -n pulsegrid-qa -o wide
echo.
echo  -- dev --
kubectl get pods -n pulsegrid-dev -o wide
echo.
goto :end


rem ===========================================================================
:usage
echo.
echo   PulseGrid Kubernetes tunnel launcher
echo.
echo     k8s.bat            check the cluster, then open one tunnel per environment
echo     k8s.bat up         same as above
echo     k8s.bat down       close both tunnel windows
echo     k8s.bat status     show PulseGrid pods across the qa and dev namespaces
echo     k8s.bat help       show this list
echo.
echo   Deploy or update the environments themselves with kubectl -k
echo   (see k8s\README.md) - this script only opens the local tunnels.
echo.
goto :end


:end
endlocal & exit /b %EXITCODE%
