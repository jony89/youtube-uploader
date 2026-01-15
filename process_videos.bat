@echo off
REM Noise reduction filter chain based on audio analysis
REM Analysis detected low-frequency camera noise at 86-107 Hz
REM Recommended: highpass at 150Hz, double-pass afftdn, and gate
mkdir sound_fixed_highpass 2>nul

for %%f in (806_Induction_5_units_class_1_exercise_1.mp4) do (
    echo Processing: %%f
    ffmpeg -i "%%f" -af "highpass=f=150,afftdn=nr=38:nf=-50:tn=1:om=1:bn=1,afftdn=nr=28:nf=-48:tn=1:om=1:bn=1,afftdn=nr=20:nf=-45:tn=1:om=1,agate=threshold=0.01:ratio=3:attack=1:release=300:makeup=1.5" -c:v copy -c:a aac -b:a 192k ".\sound_fixed_highpass\%%~nf.mp4"
    echo Completed: %%~nf.mp4
    echo.
)

echo All files processed!
pause