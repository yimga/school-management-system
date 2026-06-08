# Local Voice Accessibility

Local voice is an optional accessibility input/output path for the existing
copilot text field. It is disabled by default.

## Operation

- `Speak` records only after explicit one-action consent, sends a bounded audio
  payload to the operator-configured LAN speech-to-text endpoint, and inserts
  the returned transcript into the editable text field.
- `Read aloud` sends bounded text to the configured LAN text-to-speech endpoint
  and plays the returned audio without caching it.
- The complete keyboard and text path remains available at all times.
- Raw recordings, transcripts, and generated audio are not stored by this
  integration. Audit rows contain operation, language, byte count, and
  `content_retained=false`, never content.
- Endpoint redirects are blocked and endpoint hosts must be explicitly listed
  in `LOCAL_VOICE_ALLOWED_HOSTS`.
- Language allowlists and byte/character limits fail closed.
- Requests are rate-limited per tenant and user.
- `LOCAL_VOICE_ENABLED=0` is the immediate kill switch.

Repository verification does not certify microphone hardware, speech quality,
language accuracy, or a LAN service deployment. Those require signed pilot
evidence before promotion beyond `repository_verified`.
