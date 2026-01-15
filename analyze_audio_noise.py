#!/usr/bin/python
"""
Audio Noise Analysis Script
Analyzes video audio to identify background noise characteristics and suggests optimal noise reduction parameters.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Try to import required packages, install if missing
try:
    import numpy as np
    import matplotlib.pyplot as plt
    import librosa
    import soundfile as sf
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "librosa", "soundfile", "matplotlib", "numpy", "scipy"])
    import numpy as np
    import matplotlib.pyplot as plt
    import librosa
    import soundfile as sf


def extract_audio(video_path, output_audio_path):
    """Extract audio from video file using ffmpeg."""
    print(f"Extracting audio from video...")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "44100",  # Sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite output
        output_audio_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Audio extracted to: {output_audio_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e}")
        print(f"FFmpeg stderr: {e.stderr.decode() if e.stderr else 'No stderr'}")
        return False
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        return False


def analyze_audio_spectrum(audio_path):
    """Analyze audio spectrum to identify noise characteristics."""
    print(f"\nLoading audio file: {audio_path}")
    
    # Load audio
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr
    
    print(f"Audio loaded: {duration:.2f} seconds, sample rate: {sr} Hz")
    
    # Calculate spectrogram
    print("Computing spectrogram...")
    S = librosa.stft(y, n_fft=2048, hop_length=512)
    magnitude = np.abs(S)
    power = magnitude ** 2
    
    # Convert to dB
    power_db = librosa.power_to_db(power, ref=np.max)
    
    # Frequency bins
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    
    # Time frames
    times = librosa.frames_to_time(np.arange(power_db.shape[1]), sr=sr, hop_length=512)
    
    return {
        'audio': y,
        'sample_rate': sr,
        'duration': duration,
        'spectrogram': power_db,
        'frequencies': freqs,
        'times': times,
        'magnitude': magnitude
    }


def find_noise_profile(spectrogram, frequencies, times, start_time=0, end_time=2):
    """Extract noise profile from a silent section (first few seconds)."""
    print(f"\nAnalyzing noise profile from {start_time}s to {end_time}s...")
    
    # Find frames in the specified time range
    start_frame = np.argmin(np.abs(times - start_time))
    end_frame = np.argmin(np.abs(times - end_time))
    
    # Extract noise section
    noise_section = spectrogram[:, start_frame:end_frame]
    
    # Calculate average noise level per frequency
    noise_profile = np.mean(noise_section, axis=1)
    noise_std = np.std(noise_section, axis=1)
    
    # Find dominant noise frequencies
    noise_peaks = []
    for i in range(len(noise_profile)):
        if noise_profile[i] > np.mean(noise_profile) + 2 * noise_std[i]:
            noise_peaks.append({
                'frequency': frequencies[i],
                'level_db': noise_profile[i],
                'index': i
            })
    
    # Sort by level
    noise_peaks.sort(key=lambda x: x['level_db'], reverse=True)
    
    return {
        'profile': noise_profile,
        'std': noise_std,
        'frequencies': frequencies,  # Include frequencies for plotting
        'peaks': noise_peaks[:20],  # Top 20 peaks
        'mean_level': np.mean(noise_profile),
        'max_level': np.max(noise_profile),
        'min_level': np.min(noise_profile)
    }


def analyze_voice_sections(spectrogram, frequencies, times):
    """Identify voice sections to understand frequency range."""
    print("\nAnalyzing voice sections...")
    
    # Voice typically in 85-255 Hz (fundamental) and 300-3400 Hz (formants)
    voice_freq_min = 85
    voice_freq_max = 3400
    
    # Find frequency indices
    voice_idx_min = np.argmin(np.abs(frequencies - voice_freq_min))
    voice_idx_max = np.argmin(np.abs(frequencies - voice_freq_max))
    
    # Calculate energy in voice band vs other bands
    voice_band = spectrogram[voice_idx_min:voice_idx_max, :]
    low_band = spectrogram[:voice_idx_min, :]
    high_band = spectrogram[voice_idx_max:, :]
    
    voice_energy = np.mean(voice_band)
    low_energy = np.mean(low_band)
    high_energy = np.mean(high_band)
    
    return {
        'voice_freq_range': (voice_freq_min, voice_freq_max),
        'voice_energy': voice_energy,
        'low_energy': low_energy,
        'high_energy': high_energy,
        'voice_idx_range': (voice_idx_min, voice_idx_max)
    }


def suggest_noise_reduction(noise_profile, voice_analysis):
    """Suggest optimal noise reduction parameters based on analysis."""
    print("\n" + "="*60)
    print("NOISE REDUCTION RECOMMENDATIONS")
    print("="*60)
    
    recommendations = []
    
    # Analyze noise characteristics
    noise_mean = noise_profile['mean_level']
    noise_max = noise_profile['max_level']
    noise_range = noise_max - noise_profile['min_level']
    
    print(f"\nNoise Characteristics:")
    print(f"  Mean noise level: {noise_mean:.2f} dB")
    print(f"  Max noise level: {noise_max:.2f} dB")
    print(f"  Noise range: {noise_range:.2f} dB")
    
    # Check for low-frequency noise
    low_freq_noise = [p for p in noise_profile['peaks'] if p['frequency'] < 200]
    if low_freq_noise:
        print(f"\n  Low-frequency noise detected:")
        for peak in low_freq_noise[:5]:
            print(f"    {peak['frequency']:.1f} Hz at {peak['level_db']:.2f} dB")
        recommendations.append("highpass=f=150")  # Cut below 150 Hz
    
    # Check for high-frequency noise
    high_freq_noise = [p for p in noise_profile['peaks'] if p['frequency'] > 8000]
    if high_freq_noise:
        print(f"\n  High-frequency noise detected:")
        for peak in high_freq_noise[:5]:
            print(f"    {peak['frequency']:.1f} Hz at {peak['level_db']:.2f} dB")
        recommendations.append("lowpass=f=10000")  # Cut above 10 kHz
    
    # Calculate noise reduction needed
    # Convert dB difference to noise reduction parameter
    noise_reduction_db = min(30, max(15, abs(noise_mean) * 0.5))
    noise_floor = max(-50, min(-25, noise_mean - 10))
    
    print(f"\n  Suggested noise reduction: {noise_reduction_db:.1f} dB")
    print(f"  Suggested noise floor: {noise_floor:.1f} dB")
    
    # Build filter chain
    filter_parts = []
    
    # Highpass if low-frequency noise
    if low_freq_noise:
        filter_parts.append("highpass=f=150")
    
    # Main noise reduction
    filter_parts.append(f"afftdn=nr={int(noise_reduction_db)}:nf={int(noise_floor)}:tn=1:om=1:bn=1")
    
    # Second pass if noise is very strong
    if noise_range > 20:
        filter_parts.append(f"afftdn=nr={int(noise_reduction_db * 0.7)}:nf={int(noise_floor + 5)}:tn=1:om=1")
    
    # Lowpass if high-frequency noise
    if high_freq_noise:
        filter_parts.append("lowpass=f=10000")
    
    # Gate to suppress noise when voice isn't present
    filter_parts.append("agate=threshold=0.005:ratio=5:attack=0.1:release=500:makeup=2")
    
    filter_chain = ",".join(filter_parts)
    
    print(f"\n  Recommended FFmpeg filter chain:")
    print(f"    {filter_chain}")
    
    return filter_chain


def plot_analysis(analysis_data, noise_profile, voice_analysis, output_path):
    """Create visualization of the analysis."""
    print(f"\nGenerating analysis plots...")
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    
    # Plot 1: Full spectrogram
    ax1 = axes[0]
    im1 = ax1.imshow(analysis_data['spectrogram'], aspect='auto', origin='lower',
                     extent=[analysis_data['times'][0], analysis_data['times'][-1],
                            analysis_data['frequencies'][0], analysis_data['frequencies'][-1]],
                     cmap='viridis')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Frequency (Hz)')
    ax1.set_title('Full Audio Spectrogram')
    ax1.set_ylim(0, 8000)  # Focus on 0-8kHz range
    plt.colorbar(im1, ax=ax1, label='Power (dB)')
    
    # Plot 2: Noise profile
    ax2 = axes[1]
    ax2.plot(noise_profile['frequencies'], noise_profile['profile'], 'b-', linewidth=2, label='Noise Profile')
    ax2.fill_between(noise_profile['frequencies'], 
                     noise_profile['profile'] - noise_profile['std'],
                     noise_profile['profile'] + noise_profile['std'],
                     alpha=0.3, label='±1 Std Dev')
    
    # Mark voice range
    voice_min, voice_max = voice_analysis['voice_freq_range']
    ax2.axvspan(voice_min, voice_max, alpha=0.2, color='green', label='Voice Range')
    
    # Mark noise peaks
    for peak in noise_profile['peaks'][:10]:
        ax2.axvline(peak['frequency'], color='red', linestyle='--', alpha=0.5)
        ax2.text(peak['frequency'], peak['level_db'], f"{peak['frequency']:.0f}Hz", 
                rotation=90, fontsize=8)
    
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Power (dB)')
    ax2.set_title('Noise Profile (First 2 seconds)')
    ax2.set_xlim(0, 8000)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Frequency bands comparison
    ax3 = axes[2]
    bands = ['Low\n(<85Hz)', 'Voice\n(85-3400Hz)', 'High\n(>3400Hz)']
    energies = [voice_analysis['low_energy'], voice_analysis['voice_energy'], voice_analysis['high_energy']]
    colors = ['red', 'green', 'orange']
    bars = ax3.bar(bands, energies, color=colors, alpha=0.7)
    ax3.set_ylabel('Average Power (dB)')
    ax3.set_title('Energy Distribution by Frequency Band')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar, energy in zip(bars, energies):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{energy:.1f} dB',
                ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Analysis plot saved to: {output_path}")
    plt.close()


def main():
    video_path = r"D:\Emath_Backup\EmathVOD\Videos\806 MP4\sound_fixed_highpass\806_Induction_5_units_class_1_exercise_2.mp4"
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        return
    
    print("="*60)
    print("AUDIO NOISE ANALYSIS")
    print("="*60)
    print(f"Video: {video_path}")
    
    # Create temp directory for intermediate files
    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, "extracted_audio.wav")
    plot_path = os.path.join(os.path.dirname(video_path), "noise_analysis.png")
    
    try:
        # Extract audio
        if not extract_audio(video_path, audio_path):
            return
        
        # Analyze audio
        analysis = analyze_audio_spectrum(audio_path)
        
        # Find noise profile (from first 2 seconds, assuming it's relatively quiet)
        noise_profile_data = find_noise_profile(
            analysis['spectrogram'],
            analysis['frequencies'],
            analysis['times'],
            start_time=0,
            end_time=2
        )
        
        # Analyze voice sections
        voice_data = analyze_voice_sections(
            analysis['spectrogram'],
            analysis['frequencies'],
            analysis['times']
        )
        
        # Generate recommendations
        recommended_filter = suggest_noise_reduction(noise_profile_data, voice_data)
        
        # Create visualization
        plot_analysis(analysis, noise_profile_data, voice_data, plot_path)
        
        # Save recommendations to file
        recommendations_file = os.path.join(os.path.dirname(video_path), "noise_reduction_recommendations.txt")
        with open(recommendations_file, 'w') as f:
            f.write("NOISE REDUCTION RECOMMENDATIONS\n")
            f.write("="*60 + "\n\n")
            f.write(f"Video: {video_path}\n\n")
            f.write("Recommended FFmpeg filter chain:\n")
            f.write(f"{recommended_filter}\n\n")
            f.write("Full FFmpeg command:\n")
            f.write(f'ffmpeg -i "input.mp4" -af "{recommended_filter}" -c:v copy -c:a aac -b:a 192k "output.mp4"\n')
        
        print(f"\nRecommendations saved to: {recommendations_file}")
        print(f"\nAnalysis complete! Check the plot: {plot_path}")
        
    except Exception as e:
        print(f"\nError during analysis: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            os.rmdir(temp_dir)
        except:
            pass


if __name__ == "__main__":
    main()
