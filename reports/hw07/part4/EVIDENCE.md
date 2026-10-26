# Part 4 - saved pricing-page evidence

Each acceptance run fetched the live page, froze the extracted text, and hashed it. The agent searched only that frozen text.
SHA-256 is of the saved `.txt` file exactly as stored here (re-checked when this index was written).

| Scenario | Run id | Source URL | Access date/time (local) | Snapshot file | SHA-256 |
|---|---|---|---|---|---|
| Membership wins | c7c432ff74 | https://www.lyft.com/bikes/bay-wheels/pricing | 2026-10-25T23:49:53 | `snapshots/c7c432ff74_pricing.txt` | `6c1f6af90eab9bb7374b8041b4289164c9e25ade9933104bf99b2ac133a37e90` |
| Pay-per-use wins | c31a74735b | https://www.lyft.com/bikes/bay-wheels/pricing | 2026-10-25T23:52:09 | `snapshots/c31a74735b_pricing.txt` | `6c1f6af90eab9bb7374b8041b4289164c9e25ade9933104bf99b2ac133a37e90` |

`snapshots/<run id>_pricing.meta.json` also records the SHA-256 of the raw HTML. The measurement runs (v1 to v4) recorded their text
hashes in `raw/part4_v*_measure_summary.json`; they were all identical to the one above when the page text did not change.
