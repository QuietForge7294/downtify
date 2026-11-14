# Fête decoding at unity tempo

Verified on 14 November 2026 against the deployed DJ image and a failed
25-track weekly Fête plan. The seventh source was MP3, stereo, 44,100 Hz,
with cue 0, source end 221.93632653061223 s and speed exactly 1.0.
No active DJ jobs were present during the bounded, read-only source probe.

The absolute timeline required 10,652,944 stereo frames at 48,000 Hz.
The current RubberBand-at-unity chain returned 10,649,043 frames: 3,901
missing, exceeding the existing 2,048-frame tolerance. FFmpeg exited 0.
Using only the volume filter returned exactly 10,652,944 frames. The source
signature was unchanged before and after each probe; no source path, title,
session identifier or copied music is included here.

Elapsed times were 3.073 s and 0.507 s respectively, from one serial pair
of probes with one decoder/filter thread and lower CPU priority. These are
decode timings for one source, not playback latency or a P95 measurement.

The correction bypasses RubberBand only when speed equals 1.0 exactly.
Other speeds retain pitch-preserving time stretching. Complete and
progressive decoding share the filter choice. Duration validation,
sample-grid rounding, source checks and the 2,048-frame tolerance remain.

`tests/music_ai/test_dj_unity_decode.py` runs with unittest or pytest.
It compares complete and progressive MP3 decoding to actual FFmpeg reference
samples and verifies that tempo 1.02 still changes duration without changing
the tone's pitch. Tests preserve the original input hash.

The corrected `AudioIO.decode` was then loaded in a temporary diagnostic
process in the deployed DJ container, independently of its running worker.
On that same real source and plan, it produced exactly 10,652,944 frames in
0.703 s with neutral gain and an unchanged source signature. Temporary PCM
was removed after validation. Two earlier attempts from a separate container
could not open the read-only database mount and stopped before decoding;
permissions were preserved. No production module or service was replaced.

Qualification still requires one complete 25-track Fête preparation followed
by actual playback. Successful decoder checks do not qualify the weekly set
or the phone. No production service was restarted for these probes.
