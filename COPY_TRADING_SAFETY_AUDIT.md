# Copy Trading Safety Audit — Phase 17

Required production execution order:

Provider Signal
-> Provider eligibility
-> Follower active state
-> Allocation/multiplier calculation
-> Follower risk checks
-> Global portfolio risk checks
-> Session/market checks
-> Broker authorization
-> Execution
-> Copy-trade audit event
-> Notification event

Do not allow:
- provider risk settings to override follower limits
- copied trades while follower is paused/stopped
- copied trades above max trade stake
- copied trades beyond max concurrent trades
- copied trades after daily loss/drawdown protection trips
- provider credentials to be exposed to followers
- notification failures to block copied execution

The current frontend deliberately exposes dry-run testing. Real broker execution should be wired through the existing centralized execution/risk pipeline rather than directly from this page.
