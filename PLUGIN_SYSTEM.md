# Plugin System

`StrategyRegistry.discover()` loads built-ins and scans `apps.strategies.plugins` for classes matching the strategy interface. Plugins should avoid broker SDKs and direct trade execution.
