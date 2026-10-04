# start-servers.ps1 - Simple, robust server starter
# Runs both servers directly in this window

Write-Host "🧹 Cleaning up old processes..." -ForegroundColor Yellow

# Kill leftover processes
Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'vite' } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; Write-Host "  Killed Vite (PID: $($_.Id))" -ForegroundColor Gray }
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'uvicorn' } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; Write-Host "  Killed Uvicorn (PID: $($_.Id))" -ForegroundColor Gray }

# Check ports
$port5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($port5173 -or $port8000) {
    Write-Host "⚠️ Ports still in use, waiting..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}

Write-Host "✅ Cleanup complete" -ForegroundColor Green

# Start Backend in background
Write-Host "🚀 Starting Backend on port 8000..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "F:\Kahoot Game\venv\Scripts\python.exe" `
    -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" `
    -WorkingDirectory "F:\Kahoot Game\backend" `
    -PassThru

# Wait for backend
Write-Host "⏳ Waiting for backend..." -ForegroundColor Yellow
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $port = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($port) { break }
}
if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Backend failed" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Backend ready" -ForegroundColor Green

# Start Frontend in background
Write-Host "🚀 Starting Frontend on port 5173..." -ForegroundColor Cyan
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c npm run dev" `
    -WorkingDirectory "F:\Kahoot Game\frontend" `
    -PassThru

# Wait for frontend
Write-Host "⏳ Waiting for frontend..." -ForegroundColor Yellow
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $port = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if ($port) { break }
}
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Frontend failed" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "✅ Frontend ready" -ForegroundColor Green

Write-Host "`n✅ Both servers running!" -ForegroundColor Green
Write-Host "   Backend:  http://localhost:8000 (PID: $($backend.Id))" -ForegroundColor Cyan
Write-Host "   Frontend: http://localhost:5173 (PID: $($frontend.Id))" -ForegroundColor Cyan
Write-Host "`nPress Ctrl+C to stop both servers..." -ForegroundColor Yellow

# Wait indefinitely - keep processes alive
try {
    while ($true) {
        Start-Sleep -Seconds 5
        # Verify both still running
        $b = Get-Process -Id $backend.Id -ErrorAction SilentlyContinue
        $f = Get-Process -Id $frontend.Id -ErrorAction SilentlyContinue
        if (-not $b -or -not $f) {
            Write-Host "⚠️ A server died, restarting..." -ForegroundColor Red
            exit 1
        }
    }
} finally {
    Write-Host "`n🛑 Stopping servers..." -ForegroundColor Yellow
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    Write-Host "✅ Servers stopped" -ForegroundColor Green
}