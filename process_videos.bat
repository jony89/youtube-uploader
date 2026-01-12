@echo off
mkdir sound_fixed 2>nul

for %%f in (*.mp4) do (
    echo Processing: %%f
    ffmpeg -i "%%f" -af afftdn=nf=-25:tn=1 -c:v copy -c:a aac -b:a 192k ".\sound_fixed\%%~nf.mp4"
    echo Completed: %%~nf_fixed.mp4
    echo.
)

echo All files processed!
pause