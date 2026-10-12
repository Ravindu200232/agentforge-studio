# Your own Python 3.10+, for studio.ps1 and run.ps1: `python` (or `python3`) on PATH first, then the
# Windows `py` launcher. A Python bundled inside another application (such as a Codex runtime) is never
# used, and a PATH entry that cannot run Python 3.10+ (the Microsoft Store `python` stub) is skipped.
function Find-Python {
    # No double quotes in Python code passed to an exe: Windows PowerShell 5.1 drops them on the way
    # out, so `else ""` arrived as `else )` and every Python failed this check with a SyntaxError.
    $check = 'import sys; print(sys.executable if sys.version_info >= (3, 10) else '''')'
    foreach ($name in 'python', 'python3') {
        foreach ($command in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
            $path = $command.Source
            if (-not $path -or $path -like '*codex-runtimes*') { continue }
            $found = & $path -c $check 2>$null | Select-Object -Last 1
            if ($LASTEXITCODE -eq 0 -and $found -and $found -notlike '*codex-runtimes*') { return [string]$found }
        }
    }
    $launcher = (Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if ($launcher) {
        $found = & $launcher -3 -c $check 2>$null | Select-Object -Last 1
        if ($LASTEXITCODE -eq 0 -and $found -and $found -notlike '*codex-runtimes*') { return [string]$found }
    }
    return $null
}

# The folder this project's Python packages go in for that Python: one per Python version (`.deps\py312`),
# because compiled packages (pydantic-core, cryptography) built for one version do not load in another.
function Get-PythonDeps([string]$Python, [string]$Root) {
    $tag = & $Python -c 'import sys; print(''py%d%d'' % sys.version_info[:2])' 2>$null | Select-Object -Last 1
    return (Join-Path (Join-Path $Root '.deps') $tag)
}
