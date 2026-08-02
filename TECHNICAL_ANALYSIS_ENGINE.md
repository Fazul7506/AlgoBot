# Technical Analysis Engine

Centralized Django services in `apps.indicators` and `apps.analysis` calculate indicators, cache latest values, publish signal events, and expose analysis APIs. Strategies and AI modules should call `IndicatorService` or `AnalysisService` instead of recalculating indicators locally.
