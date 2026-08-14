# Jarvis Host

Phase 1 ships a **Mock Jarvis Host Adapter** that implements the exact same
`HostProtocol` as `HarnessHostAdapter`. This is the formal proof target for
host swap (§46, §73):

```text
HarnessHostAdapter → Universal Agent      (production path)
MockJarvisHostAdapter → Universal Agent   (swap test)
```

**Reserved Jarvis capabilities (§11)** — declared, mocked, not yet wired:

| Capability            | Phase 1 |
|-----------------------|---------|
| `voice_intent`        | mocked  |
| `desktop_notification`| mocked  |
| `mobile_notification` | mocked  |
| `approval_request`    | mocked (always pending, never auto-approve) |
| `task_status`         | via HostProtocol |
| `memory_query`        | via Core Memory |
| `watch_query`         | via Core Task Registry |
| `action_status`       | via Action Gateway |
| `agent_health`        | stubbed |

**Acceptance**: `tests/migration/test_host_swap.py` must pass with **0 Core code
changes** when swapping the adapter.
