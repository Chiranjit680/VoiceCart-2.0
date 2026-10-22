<#
.SYNOPSIS
    Start (or stop) every VoiceCart service, each in its own window.

.DESCRIPTION
    Start order follows the dependencies:
        Product Service (8000) -> MCP server (8004) -> Agent (8002)
        STT (8001), TTS (8006, optional: without it replies are text only)
        Manager (8003, needs STT + Agent)
        Frontend (8080, or 5173 if 8080 is taken by another program)

    - If the repo has no .venv / venv, one is created and the dependencies are installed into it.
    - Before opening a window the script checks that the service's Python packages are installed;
      a service with missing packages is reported and skipped instead of crashing.
    - A service whose port is already in use is skipped, so the script can be re-run safely.

.EXAMPLE
    .\run-all.ps1              # start everything
    .\run-all.ps1 -Install     # (re)install Python + npm dependencies first, then start
    .\run-all.ps1 -NoFrontend  # backend services only
    .\run-all.ps1 -Stop        # stop everything this script starts
    .\run-all.ps1 -Python C:\envs\voicecart\Scripts\python.exe
#>
param(
    [switch]$Install,
    [switch]$Stop,
    [switch]$NoFrontend,
    [string]$Python
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        return ($connect.AsyncWaitHandle.WaitOne(300) -and $client.Connected)
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-PortOwner([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue }
}

# --- Stop ---
if ($Stop) {
    foreach ($port in 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8080, 5173) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $listeners) { continue }
        foreach ($procId in ($listeners.OwningProcess | Sort-Object -Unique)) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            # Only touch our own kinds of process; port 8080 may belong to an unrelated program.
            if ($proc -and $proc.ProcessName -match '^(python|node)') {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "  port ${port}: stopped $($proc.ProcessName)" -ForegroundColor Yellow
            } elseif ($proc) {
                Write-Host "  port ${port}: left alone ($($proc.ProcessName) is not a VoiceCart service)" -ForegroundColor DarkGray
            }
        }
    }
    # Close the now-idle service windows.
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like "*WindowTitle = 'VoiceCart - *" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    return
}

# --- Python: -Python, else a repo virtualenv, else create .venv ---
if (-not $Python) {
    foreach ($candidate in @(".venv\Scripts\python.exe", "venv\Scripts\python.exe")) {
        $path = Join-Path $Root $candidate
        if (Test-Path $path) { $Python = $path; break }
    }
}
if (-not $Python) {
    Write-Host "No virtualenv found; creating .venv ..." -ForegroundColor Cyan
    try { & python --version | Out-Null } catch { throw "Python was not found on PATH. Install Python 3.11+ or pass -Python <path>." }
    & python -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv" }
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    $Install = $true
}

# --- Install ---
$UsingRepoVenv = -not $PSBoundParameters.ContainsKey("Python")
$Installed = $false

function Install-PythonDeps {
    # Windows can't replace files that a running Python still has open, which makes pip fail halfway
    # and leaves the venv incomplete (so the next run would try again).
    $running = @(8000, 8001, 8002, 8003, 8004, 8005, 8006) | Where-Object {
        $owner = Get-PortOwner $_
        $owner -and $owner.ProcessName -match '^python'
    }
    if ($running) {
        throw "Services are still running (ports $($running -join ', ')). Run .\run-all.ps1 -Stop first, then try again."
    }
    Write-Host "Installing Python dependencies into $Python ..." -ForegroundColor Cyan
    $requirements = @("Product Service", "agent", "mcp_server", "manager", "STT", "TTS") |
        ForEach-Object { "-r"; (Join-Path $Root "$_\requirements.txt") }
    & $Python -m pip install @requirements
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    $script:Installed = $true
}

if ($Install) { Install-PythonDeps }
if (-not $NoFrontend -and ($Install -or -not (Test-Path (Join-Path $Root "frontend\node_modules")))) {
    Write-Host "Installing frontend dependencies ..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    try { npm install; if ($LASTEXITCODE -ne 0) { throw "npm install failed" } } finally { Pop-Location }
}

function Get-MissingModules([string[]]$Modules) {
    # find_spec() raises (instead of returning None) for a dotted name whose parent package is missing.
    $code = @"
import importlib.util as u
def present(name):
    try:
        return u.find_spec(name) is not None
    except ImportError:
        return False
print(' '.join(m for m in '$($Modules -join ',')'.split(',') if not present(m)))
"@
    return @(($code | & $Python -) -split '\s+' | Where-Object { $_ })
}

# --- Services ---
$Services = @(
    @{ Name = "Product Service"; Port = 8000; Dir = $Root
       Modules = @("fastapi", "uvicorn", "sqlalchemy", "psycopg", "psycopg2", "jose", "passlib", "pydantic_settings", "email_validator", "multipart")
       Command = "& '$Python' -m uvicorn app.main:app --app-dir 'Product Service' --port 8000" },
    # Long-term memory: judges conversations in the background and answers the agent about each shopper's memories.
    # Needs chromadb, which is never installed automatically (it is large): install it yourself, see Hint.
    @{ Name = "Memory"; Port = 8005; Dir = $Root; WaitFor = @(8000); NeedsMemoryKey = $true
       Modules = @("fastapi", "uvicorn", "chromadb", "psycopg", "dotenv", "langchain_openai")
       Hint = "'chromadb' is not installed automatically. Install it yourself: $Python -m pip install -r longterm_memory/requirements.txt"
       Command = "& '$Python' -m uvicorn longterm_memory.api:create_app --factory --host 127.0.0.1 --port 8005" },
    @{ Name = "MCP Server"; Port = 8004; Dir = $Root; WaitFor = @(8000)
       Modules = @("mcp", "httpx", "dotenv")
       Command = "`$env:MCP_TRANSPORT = 'streamable-http'; & '$Python' mcp_server/server.py" },
    @{ Name = "Agent"; Port = 8002; Dir = $Root; WaitFor = @(8004)
       Modules = @("fastapi", "uvicorn", "langgraph", "langchain", "langchain_openai", "langchain_mcp_adapters", "langgraph.checkpoint.postgres", "psycopg_pool")
       Command = "& '$Python' -m uvicorn agent.main:app --port 8002 --loop agent.loop:selector_loop_factory" },
    @{ Name = "STT"; Port = 8001; Dir = $Root
       Modules = @("fastapi", "uvicorn", "dotenv", "multipart", "gnani")
       Hint = "'gnani' is the Gnani STT SDK; it is not on PyPI under a known name, so install it into $Python yourself."
       Command = "& '$Python' STT/stt_new.py" },
    @{ Name = "TTS"; Port = 8006; Dir = (Join-Path $Root "TTS")
       Modules = @("fastapi", "uvicorn", "dotenv", "gnani")
       Hint = "'gnani' is the Gnani SDK (gnani-vachana); install it into $Python yourself."
       Command = "& '$Python' -m uvicorn tts_service:app --port 8006" },
    @{ Name = "Manager"; Port = 8003; Dir = (Join-Path $Root "manager"); WaitFor = @(8001, 8002)
       Modules = @("fastapi", "uvicorn", "httpx", "dotenv", "websockets")
       Command = "& '$Python' -m uvicorn main:app --port 8003" }
)
if (-not $NoFrontend) {
    # Vite's default here is 8080, which other programs also use; fall back to 5173 if it is taken by a non-node process.
    $frontendPort = 8080
    $owner = Get-PortOwner 8080
    if ($owner -and $owner.ProcessName -notmatch '^node') {
        Write-Warning "Port 8080 is used by $($owner.ProcessName); starting the frontend on 5173 instead."
        $frontendPort = 5173
    }
    $Services += @{ Name = "Frontend"; Port = $frontendPort; Dir = (Join-Path $Root "frontend")
                    Command = "npm run dev -- --port $frontendPort --strictPort" }
}

# --- Pre-flight ---
if (-not (Test-Port 5432)) {
    Write-Warning "PostgreSQL is not listening on localhost:5432; the Product Service will fail to start."
}
foreach ($envFile in @(".env", "agent\.env", "STT\.env", "manager\.env")) {
    if (-not (Test-Path (Join-Path $Root $envFile))) { Write-Warning "Missing $envFile (see README)." }
}
Write-Host "Using Python: $Python" -ForegroundColor Cyan

function Find-MissingPackages {
    foreach ($svc in $Services) {
        $svc.Skip = $false
        $svc.Missing = @()
        # @() matters: an empty result would otherwise be stored as $null, and piping $null still yields one item.
        if ($svc.Modules) { $svc.Missing = @(Get-MissingModules $svc.Modules) }
    }
}

Find-MissingPackages
# The repo's own venv is ours to fill in; an explicit -Python is left alone.
# Packages the script never installs itself: gnani is not on PyPI, and chromadb is large and left to the user.
$notAutoInstalled = @("gnani", "chromadb")
$installable = @($Services | Where-Object { @($_.Missing | Where-Object { $_ -and $_ -notin $notAutoInstalled }).Count -gt 0 })
if ($installable.Count -gt 0 -and $UsingRepoVenv -and -not $Installed) {
    $detail = ($installable | ForEach-Object { "$($_.Name): $($_.Missing -join ', ')" }) -join "; "
    Write-Host "Some Python packages are missing ($detail)." -ForegroundColor Yellow
    Install-PythonDeps
    Find-MissingPackages
}
foreach ($svc in $Services) {
    if ($svc.Missing.Count -gt 0) {
        $svc.Skip = $true
        Write-Host "  $($svc.Name): SKIPPED, missing Python packages: $($svc.Missing -join ', ')" -ForegroundColor Red
        if ($svc.Hint -and @($svc.Missing | Where-Object { $_ -in $notAutoInstalled }).Count -gt 0) { Write-Host "      $($svc.Hint)" -ForegroundColor Red }
        elseif (-not $UsingRepoVenv) { Write-Host "      Install them into $Python (see each folder's requirements.txt)." -ForegroundColor Red }
    }
}
# The memory service refuses to start without its key (it guards every shopper's memories).
$envFile = Join-Path $Root ".env"
$hasMemoryKey = (Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^\s*MEMORY_SERVICE_KEY\s*=\s*\S' -Quiet)
foreach ($svc in $Services) {
    if ($svc.NeedsMemoryKey -and -not $svc.Skip -and -not $hasMemoryKey) {
        $svc.Skip = $true
        $svc.SkipReason = "MEMORY_SERVICE_KEY is not set"
        Write-Host "  $($svc.Name): SKIPPED, MEMORY_SERVICE_KEY is not set in .env (see README)." -ForegroundColor Red
    }
}
$skippedPorts = @($Services | Where-Object { $_.Skip } | ForEach-Object { $_.Port })

# --- Start ---
foreach ($svc in $Services) {
    if ($svc.Skip) { continue }
    if (Test-Port $svc.Port) {
        Write-Host "  $($svc.Name) ($($svc.Port)): already running, skipped" -ForegroundColor DarkGray
        continue
    }
    foreach ($dep in @($svc.WaitFor)) {
        if (-not $dep) { continue }
        if ($skippedPorts -contains $dep) {
            Write-Warning "$($svc.Name): a service it depends on (port $dep) was skipped, so some features will not work."
        } elseif (-not (Wait-Port $dep)) {
            Write-Warning "$($svc.Name): port $dep is still not up; starting anyway (check that service's window)."
        }
    }

    # -NoExit keeps the window open so a crash's traceback stays readable.
    $script = "`$Host.UI.RawUI.WindowTitle = 'VoiceCart - $($svc.Name) :$($svc.Port)'; $($svc.Command)"
    Start-Process powershell -WorkingDirectory $svc.Dir -ArgumentList @("-NoExit", "-Command", $script) | Out-Null
    Write-Host "  $($svc.Name) ($($svc.Port)): starting" -ForegroundColor Green
}

# --- Report ---
Write-Host ""
foreach ($svc in $Services) {
    if ($svc.Skip) {
        $state = if ($svc.SkipReason) { "SKIPPED ($($svc.SkipReason))" } else { "SKIPPED (missing packages)" }; $color = "Red"
    } elseif (Wait-Port $svc.Port 60) {
        $state = "up"; $color = "Green"
    } else {
        $state = "NOT UP - check its window"; $color = "Red"
    }
    Write-Host ("  {0,-16} http://localhost:{1,-5} {2}" -f $svc.Name, $svc.Port, $state) -ForegroundColor $color
}
Write-Host ""
if (-not $NoFrontend) {
    Write-Host "Open http://localhost:$frontendPort, log in, then use the voice page. Stop everything with: .\run-all.ps1 -Stop"
}
