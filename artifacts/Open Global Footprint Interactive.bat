@echo off

REM One-click interactive Global Footprint preview (WebGL) — no Django, local C: drive.

cd /d "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"



echo Building 3D globe bundle (first run may take ~10s)...

call npm run build:world-globe

if errorlevel 1 (

  echo.

  echo ERROR: npm run build:world-globe failed. Install Node.js, run npm install, then retry.

  pause

  exit /b 1

)



echo Starting local preview server on http://localhost:8080 ...

start "RMC Globe Preview Server" /MIN python -m http.server 8080

timeout /t 2 /nobreak >nul

start "" "http://localhost:8080/artifacts/global-footprint-section-preview.html"

echo.

echo Browser opened. Drag the globe to rotate, scroll to zoom.

echo Hard-refresh (Ctrl+Shift+R) if you still see a blank panel.

echo Close the minimized "RMC Globe Preview Server" window to stop the server.

pause

