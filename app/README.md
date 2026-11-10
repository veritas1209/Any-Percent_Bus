# Any% Flutter app

The project setup, architecture, data assumptions and demo guide are in [the main README](../README.md).

```powershell
flutter pub get
flutter run -d chrome --web-port 8080
flutter test
flutter build apk --release
```

The app starts with bundled demonstration data. Data settings switch between the synthetic scenario, recorded GPS passage-time replay, and the separate Any% API. No location permission or API connection is required for the bundled demo.
