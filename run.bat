@echo off
rem ===========================================================================
rem  PulseGrid - one-command local launcher for Windows
rem
rem    run.bat            check prerequisites, build and start the whole stack
rem    run.bat status     show what is running
rem    run.bat logs       follow the API logs
rem    run.bat test       run the backend test suite inside the container
rem    run.bat down       stop the stack (database volume is kept)
rem    run.bat reset      stop the stack AND delete the database volume
rem    run.bat help       show this list
rem ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "API_URL=http://localhost:8000"
set "DEMO_URL=http://localhost:8001"
set "DASHBOARD_URL=http://localhost:5173"
set "EXITCODE=0"

if /i "%~1"==""       goto :cmd_up
if /i "%~1"=="up"     goto :cmd_up
if /i "%~1"=="status" goto :cmd_status
if /i "%~1"=="logs"   goto :cmd_logs
if /i "%~1"=="test"   goto :cmd_test
if /i "%~1"=="down"   goto :cmd_down
if /i "%~1"=="reset"  goto :cmd_reset
if /i "%~1"=="help"   goto :usage
if /i "%~1"=="-h"     goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="/?"     goto :usage

echo.
echo   Unknown command: %~1
set "EXITCODE=1"
goto :usage


rem ===========================================================================
rem  Default: prerequisites -^> build -^> start -^> wait -^> verify
rem ===========================================================================
:cmd_up
echo.
echo  ==========================================================
echo    PulseGrid - API Analytics ^& Performance Management
echo  ==========================================================
echo.
echo  [1/4] Checking prerequisites...
echo.

call :check_prereqs
if errorlevel 1 goto :prereq_failed

echo.
echo  [2/4] Building and starting services...
echo        First run pulls postgres:17-alpine and builds the backend
echo        image ^(pandas/scikit-learn/statsmodels^) - allow a few minutes.
echo.

docker compose up -d --build
if errorlevel 1 (
    echo.
    echo   [FAIL] docker compose failed. Scroll up for the build error.
    set "EXITCODE=1"
    goto :end
)

echo.
echo  [3/4] Waiting for services to report healthy...
echo.

call :wait_healthy pulsegrid-db          "db           postgres:17-alpine" 40
if errorlevel 1 set "EXITCODE=1"
call :wait_healthy pulsegrid-demo-target "demo-target  synthetic upstream" 40
if errorlevel 1 set "EXITCODE=1"
call :wait_healthy pulsegrid-api         "api          migrations then uvicorn" 60
if errorlevel 1 set "EXITCODE=1"
call :wait_healthy pulsegrid-web         "web          nginx + dashboard bundle" 40
if errorlevel 1 set "EXITCODE=1"

if not "%EXITCODE%"=="0" (
    echo.
    echo   One or more services never became healthy. Recent API logs:
    echo   ----------------------------------------------------------
    docker compose logs --tail 40 api
    echo   ----------------------------------------------------------
    echo   Full logs:  run.bat logs
    goto :end
)

echo.
echo  [4/4] Verifying endpoints...
echo.

where curl >nul 2>&1
if errorlevel 1 (
    echo   [SKIP] curl not found - open %API_URL%/health in a browser instead.
) else (
    call :probe "%API_URL%/health"       "GET /health          "
    call :probe "%API_URL%/docs"         "GET /docs            "
    call :probe "%DEMO_URL%/fast"        "GET /fast   upstream "
    call :probe "%DASHBOARD_URL%/"       "GET /       dashboard"
)

echo.
echo  ==========================================================
echo    PulseGrid is up. This is the production stack.
echo  ==========================================================
echo.
echo    Dashboard       %DASHBOARD_URL%
echo    API docs        %API_URL%/docs
echo    Health          %API_URL%/health
echo    Live SSE feed   curl -N %API_URL%/v1/stream
echo    Demo upstream   %DEMO_URL%/fast  ^| /slow ^| /flaky
echo.
echo    Follow logs     run.bat logs
echo    Run tests       run.bat test
echo    Stop            run.bat down
echo.
echo    ^(The "web" container above IS the dashboard - built from
echo    frontend\Dockerfile and served by nginx on port 5173. Use
echo    "cd frontend ^&^& npm run dev" only if you want hot-reload
echo    while editing the frontend, not to view this stack.^)
echo.
goto :end


rem ===========================================================================
rem  Prerequisite checks
rem ===========================================================================
:check_prereqs
set "PREREQ_FAIL=0"

rem --- Docker CLI ---------------------------------------------------------
where docker >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Docker is not installed, or not on PATH.
    echo          Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/
    set "PREREQ_FAIL=1"
) else (
    for /f "tokens=*" %%V in ('docker --version 2^>nul') do set "DOCKER_VER=%%V"
    echo   [OK]   !DOCKER_VER!
)

rem --- Docker daemon actually running -------------------------------------
if "%PREREQ_FAIL%"=="0" (
    docker info >nul 2>&1
    if errorlevel 1 (
        echo   [FAIL] Docker is installed but the daemon is not responding.
        echo          Start Docker Desktop and wait for the whale icon to settle,
        echo          then run this script again.
        set "PREREQ_FAIL=1"
    ) else (
        echo   [OK]   Docker daemon is running
    )
)

rem --- Compose v2 ----------------------------------------------------------
if "%PREREQ_FAIL%"=="0" (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo   [FAIL] "docker compose" ^(v2^) is unavailable.
        echo          The legacy "docker-compose" v1 binary will not work -
        echo          this project uses Compose v2 syntax. Update Docker Desktop.
        set "PREREQ_FAIL=1"
    ) else (
        for /f "tokens=*" %%V in ('docker compose version 2^>nul') do set "COMPOSE_VER=%%V"
        echo   [OK]   !COMPOSE_VER!
    )
)

rem --- Required files ------------------------------------------------------
if not exist "docker-compose.yml" (
    echo   [FAIL] docker-compose.yml not found.
    echo          Run this script from the repository root.
    set "PREREQ_FAIL=1"
)
if not exist "backend\Dockerfile" (
    echo   [FAIL] backend\Dockerfile not found - the checkout looks incomplete.
    set "PREREQ_FAIL=1"
)

rem --- .env (create from the template when missing) ------------------------
if exist ".env" (
    echo   [OK]   .env present
) else (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo   [OK]   .env created from .env.example
        echo          Local dev defaults only - set a real JWT_SECRET before
        echo          exposing this to anything but localhost.
    ) else (
        echo   [FAIL] Neither .env nor .env.example exists.
        set "PREREQ_FAIL=1"
    )
)

rem --- Port availability (warning only) ------------------------------------
call :check_port 5432 "PostgreSQL"
call :check_port 8000 "API"
call :check_port 8001 "demo-target"
call :check_port 5173 "dashboard (web)"

if "%PREREQ_FAIL%"=="1" exit /b 1
exit /b 0


rem ---------------------------------------------------------------------------
rem  :check_port <port> <label>  - warn if something already holds the port
rem ---------------------------------------------------------------------------
:check_port
netstat -an | findstr /c:":%~1 " | findstr /i "LISTENING" >nul 2>&1
if not errorlevel 1 (
    docker compose ps --status running 2>nul | findstr /c:":%~1" >nul 2>&1
    if errorlevel 1 (
        echo   [WARN] Port %~1 ^(%~2^) is already in use by another process.
        echo          If startup fails, stop that process or change the port
        echo          mapping in docker-compose.yml.
    )
)
exit /b 0


rem ---------------------------------------------------------------------------
rem  :wait_healthy <container> <label> <max attempts, 3s apart>
rem
rem  NOTE: written with goto rather than if(...) blocks, and labels must never
rem  contain parentheses. cmd.exe expands %VAR% at parse time, so a ")" inside
rem  an echoed label silently closes the enclosing block.
rem ---------------------------------------------------------------------------
:wait_healthy
set "CNAME=%~1"
set "CLABEL=%~2"
set /a MAXTRY=%~3
set /a TRY=0

:wait_loop
set "HEALTH="
for /f "delims=" %%H in ('docker inspect --format "{{.State.Health.Status}}" !CNAME! 2^>nul') do set "HEALTH=%%H"

if /i "!HEALTH!"=="healthy"   goto :wait_ok
if /i "!HEALTH!"=="unhealthy" goto :wait_unhealthy

set /a TRY+=1
if !TRY! GEQ !MAXTRY! goto :wait_timeout
rem `timeout /t` aborts with "Input redirection is not supported" whenever
rem stdin is not a console - piping this script, or running it from CI. ping
rem is the portable sleep: -n 4 waits ~3 seconds.
ping -n 4 127.0.0.1 >nul 2>&1
goto :wait_loop

:wait_ok
echo   [OK]   !CLABEL!
exit /b 0

:wait_unhealthy
echo   [FAIL] !CLABEL! - container reports unhealthy
exit /b 1

:wait_timeout
if "!HEALTH!"=="" echo   [FAIL] !CLABEL! - container never appeared
if not "!HEALTH!"=="" echo   [FAIL] !CLABEL! - stuck in state "!HEALTH!"
exit /b 1


rem ---------------------------------------------------------------------------
rem  :probe <url> <label>  - report the HTTP status of one endpoint
rem ---------------------------------------------------------------------------
:probe
set "PURL=%~1"
set "PLABEL=%~2"
set "CODE="
for /f "delims=" %%C in ('curl -s -o NUL -w "%%{http_code}" "!PURL!" 2^>nul') do set "CODE=%%C"
if "!CODE!"=="200" goto :probe_ok
echo   [WARN] !PLABEL! - got "!CODE!", expected 200
exit /b 0

:probe_ok
echo   [OK]   !PLABEL! - 200
exit /b 0


rem ===========================================================================
rem  Subcommands
rem ===========================================================================
:cmd_status
echo.
docker compose ps
echo.
goto :end

:cmd_logs
echo.
echo  Following API logs - press Ctrl+C to stop ^(services keep running^).
echo.
docker compose logs -f api
goto :end

:cmd_test
rem The suite runs against SQLite in-memory, so it needs neither Docker nor a
rem database - but it does need the dev dependencies, which the runtime image
rem deliberately omits. So this runs on the host, exactly like CI does.
echo.
echo  Running the backend test suite ^(SQLite in-memory - no Docker needed^)...
echo.

set "VENVPY=backend\.venv\Scripts\python.exe"

if not exist "%VENVPY%" (
    echo   No backend\.venv found - creating one...
    where uv >nul 2>&1
    if errorlevel 1 (
        where python >nul 2>&1
        if errorlevel 1 (
            echo   [FAIL] Neither uv nor python is on PATH.
            echo          Install Python 3.12 ^(https://www.python.org/downloads/^)
            echo          then re-run:  run.bat test
            set "EXITCODE=1"
            goto :end
        )
        pushd backend
        python -m venv .venv
        .venv\Scripts\python.exe -m pip install -q --upgrade pip
        .venv\Scripts\python.exe -m pip install -q -e . pytest pytest-asyncio ruff
        popd
    ) else (
        pushd backend
        uv venv
        uv pip install --python .venv\Scripts\python.exe -r pyproject.toml --group dev
        popd
    )
)

if not exist "%VENVPY%" (
    echo   [FAIL] Could not create backend\.venv - see the errors above.
    set "EXITCODE=1"
    goto :end
)

pushd backend
"..\%VENVPY%" -m pytest
if errorlevel 1 set "EXITCODE=1"
echo.
echo  Lint:
"..\%VENVPY%" -m ruff check .
if errorlevel 1 set "EXITCODE=1"
"..\%VENVPY%" -m ruff format --check .
if errorlevel 1 set "EXITCODE=1"
popd
goto :end

:cmd_down
echo.
echo  Stopping PulseGrid ^(database volume is preserved^)...
echo.
docker compose down
if errorlevel 1 set "EXITCODE=1"
echo.
echo  Stopped. Data kept - "run.bat" brings it straight back.
echo.
goto :end

:cmd_reset
echo.
echo  This deletes the PostgreSQL volume. All registered APIs, users and
echo  collected metrics will be permanently lost.
echo.
set "CONFIRM="
set /p "CONFIRM=Type YES to confirm: "
if /i not "!CONFIRM!"=="YES" (
    echo.
    echo  Cancelled - nothing was deleted.
    echo.
    goto :end
)
echo.
docker compose down -v
if errorlevel 1 set "EXITCODE=1"
echo.
echo  Stack removed and volume deleted. Next "run.bat" starts from a clean database.
echo.
goto :end


rem ===========================================================================
:prereq_failed
echo.
echo   Prerequisites are not satisfied - see the [FAIL] lines above.
echo.
set "EXITCODE=1"
goto :end


:usage
echo.
echo   PulseGrid launcher
echo.
echo     run.bat            check prerequisites, build and start everything
echo     run.bat status     show what is running
echo     run.bat logs       follow the API logs
echo     run.bat test       run the backend test suite in the container
echo     run.bat down       stop the stack, keep the database
echo     run.bat reset      stop the stack and delete the database volume
echo     run.bat help       show this list
echo.
goto :end


:end
endlocal & exit /b %EXITCODE%
