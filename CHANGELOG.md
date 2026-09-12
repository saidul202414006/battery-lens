# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-09-12
### Added
- Initial release of Battery Lens.
- Background `MonitorService` to poll battery state using platform-specific APIs.
- Comprehensive `Database` schema for tracking snapshots, sessions, events, and anomalies.
- `SleepDetector` and `ChargeDetector` for tracking sleep cycles and charging sessions.
- `AnomalyDetector` with baseline calculation to flag unusually high battery drain.
- `RecommendationEngine` to provide evidence-based advice on battery health.
- `CustomTkinter` UI with Dashboard, History, Sleep, Health, Charging, Alerts, and Settings tabs.
- Cross-platform System Tray integration (`pystray`).
- `RuntimeEstimator` for predicting remaining battery life based on actual usage habits.
- `ChargePatternAnalyzer` and `HealthPredictor` for advanced insights.
- CSV export capability for session history.
