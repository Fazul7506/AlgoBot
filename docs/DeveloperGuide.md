# Developer Guide

Do not store request state in module globals. Add new trading behavior behind services with dependency injection-friendly APIs. Keep risk approval separate from position sizing. Persist lifecycle changes through the state machine instead of directly mutating trade status in new code.
