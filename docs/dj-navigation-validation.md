# DJ navigation candidate — 12 November 2026

An interactive render could remain playable after reaching `ready`, while its
Next endpoint required an active renderer lease. Android beta7 compounded a
refusal by silently advancing the old classic queue. Prepared web Next also
called the interactive endpoint, and web Previous ignored the DJ transport.

The candidate advertises optional `dj_navigation`. New clients send the current
mix position with Next/Previous. The API validates ownership, feature permission,
native catalogue access and retained private HLS segments before returning
`seek_to_seconds`. Receipts are idempotent; expired markers are explicit failures.
An active renderer follows a confirmed cursor change without changing pause.
An unrendered Next can still request a future safe transition. Older clients can
keep using commands without a position; new clients negotiate this capability.

Both clients retain the selected mix on a refusal and offer an explicit return
to classic playback. Prepared navigation stays in the shared player. Explicit
jumps pass the outgoing overlap tail. No navigation result resumes paused audio.
HLS Previous is limited to the retained window, not the complete historical set.

The candidate also fixes parsing of FFmpeg loudnorm diagnostics: FFmpeg 7 may
append an output summary after its JSON. The bounded parser reads one JSON object
and retains the finite-value checks. All twelve real FFmpeg audio tests passed
after this correction; audio assertions were not removed or skipped.

Deployed genre-centroid ranking and strict boolean preferences are preserved in
a separate source commit. The more recent asynchronous renderer in the source
branch is retained; the older deployed renderer is not copied over it.

Automated evidence includes a distinct MediaController connected to MediaSession,
large shuffled queues, restoration, stale results, pause and command failures.
These simulations are not a separate Android UID, physical car or DHU test.
No Pixel was connected. First-sound cold/warm P95, pause P95 on hardware, twenty
genre-balanced listening comparisons and one continuous qualified hour remain
unmeasured. Two real-model worker integration tests remain separate acceptance.
No resource boost or feature preference change is part of this correction.
