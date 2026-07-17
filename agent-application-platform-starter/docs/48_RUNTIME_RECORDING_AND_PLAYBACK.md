# Runtime Recording and Playback

## Separation

RuntimeSession is a short-lived live connection. RuntimeRecording is a Platform-owned, immutable playback resource. Sandbox Snapshot captures state; it is not a recording.

Runtime Gateway records authorized channels because it already mediates Terminal, Browser and Desktop traffic. Sandbox Provider supplies the internal stream endpoint but does not decide user consent, retention or playback authorization.

Lifecycle follows `contracts/state-machines/runtime-recording-v1.json`; `ready` is reachable only after the complete immutable manifest is committed, while failed finalization remains explicitly failed.

## Data model

```text
RuntimeRecording
 -> channels[]
 -> RuntimeRecordingChunk[]
    -> immutable ArtifactVersion
 -> RuntimeRecordingManifest
```

Supported channels are terminal, browser, desktop and file delta. Each chunk has channel-local sequence, wall-clock range and WorkOrder `work_sequence` range. Playback synchronizes on `work_sequence`; timestamps are presentation metadata.

## Formats

- Terminal: asciicast-compatible or another registered media type with UTF-8/redaction profile.
- Browser/Desktop: segmented WebM/MP4 or registered event/screenshot format.
- File changes: digest-addressed deltas or ArtifactVersion references.

Large bytes never enter PostgreSQL, Temporal History or CanonicalEvent. Events only reference recording/chunk Artifacts.

The ready `RuntimeRecording.manifest_digest` and the root `RuntimeRecordingManifest.manifest_digest` are detached digest slots containing the same value. Compute that value with RFC 8785 JCS plus SHA-256 after removing both slots; excluding both avoids a circular self-reference while still binding the complete recording metadata and chunk list.

## Security and lifecycle

- Recording policy, classification, retention and consent are fixed before capture.
- Runtime Gateway redacts secrets and authorization material before finalization.
- Chunks use encrypted Artifact storage and object-scoped grants.
- `recording:read` is separate from `runtime:view`.
- deletion and legal hold follow Artifact policy; Audit retains the decision, not deleted content.
- partial/finalization failure is visible and cannot be represented as a complete recording.
