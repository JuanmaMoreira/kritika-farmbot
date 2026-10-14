# MW readiness after rewarded ad: 7ac67227

`lobby.json` preserves snapshot 3796 from local failure
`failure_1e2fd2c2f20c4d4a9030142af55229dc`, captured at monotonic 28404.328.
Log `20261006T201225.383450Z_session_7ac67227.jsonl`, events 758–766:
two OCR observations confirmed 338 Sapphires at confidence .99962, but the
last capture was approximately 2.17 s old at readiness validation.

Tests replay the recorded context and a controlled latency budget, using the
actual fact reader, parser, consensus and factory scope. Synthetic pixels/OCR
are harness inputs, not new physical evidence. The original reduced frames
remain local and do not serve as native CV/OCR calibration.
