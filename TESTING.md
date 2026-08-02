# VALENCE testing

Run the full suite with:

```bash
pip install -e ".[dev]"
pytest
```

VALENCE v0.7 contains **64 automated tests**. They cover deterministic event
ordering and run hashes, latency distributions and calibration, packet loss,
resource queues, stake-weighted duties and finality, regional topology, frozen
v0.6 experiment designs, and the v0.7 poster-compliance capabilities.

The v0.7 tests specifically verify:

- 100% availability in the healthy oracle;
- missed proposal and attestation duties during scheduled outages;
- count-weighted versus stake-weighted availability under a high-stake outage;
- regional, ISP, explicit-ID, and highest-stake target selection;
- recovery to online status and restart from the last finalized checkpoint;
- explicit incompatible-branch fork detection;
- canonical, orphaned, and unresolved block classification;
- local reorganization depth; and
- finalized and right-censored checkpoint time-to-finality records.

The smoke, outage, and finality demonstration configurations are deterministic
oracles and should be run before large experimental sweeps.
