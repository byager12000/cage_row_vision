@echo off
rem STK-14 cage position test (warehouse belt). Double-click to run.
cd /d "C:\Visron\App Dev\Cage-Row-Vision"
set "PATH=C:\Users\byage\.local\bin;%PATH%"
echo Starting the cage position test (warehouse config)...
echo Keys in the VIDEO window: T = teach target, SPACE = record a move, N = skip, Q = quit
echo Results are saved after every move.
uv run python -m cage_vision --config config_warehouse.yaml cage-live --label belt_test
echo.
echo ============================================================
echo  The test has ended. Results are in the runs folder above.
echo  This window stays open (keys pressed here do nothing).
echo  Close it with the X when you are done.
echo ============================================================
cmd /k
