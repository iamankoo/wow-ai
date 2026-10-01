import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/api_client.dart';

/// Dev backend base URL. `10.0.2.2` is the Android emulator's alias for the
/// host machine's `localhost` where the FastAPI backend runs during
/// development.
const String kDevBackendBaseUrl = 'http://10.0.2.2:8000';

/// Phase 7 Block 2: the real deployed Render backend - see
/// docs/DEPLOYMENT.md. Release builds use this instead of the developer's
/// own laptop, so the app works without it running.
const String kProdBackendBaseUrl = 'https://wow-ai-backend-4h49.onrender.com';

/// Picked by build mode by default (matches
/// WowCallScreeningService.kt/WowAutoAnswer.kt's BuildConfig.BACKEND_BASE_URL,
/// selected the same way per Gradle build type) - but overridable via
/// `--dart-define=WOW_BACKEND_URL=...` for a real physical-device test
/// against a debug backend, since `10.0.2.2` is an emulator-only alias
/// that doesn't resolve on real hardware. The real, reliable pairing for
/// that case: `adb reverse tcp:8000 tcp:8000` (forwards the device's own
/// `localhost:8000` to the host machine over the existing USB connection,
/// no shared WiFi network required) plus
/// `flutter run --dart-define=WOW_BACKEND_URL=http://127.0.0.1:8000`.
const String kDefaultBackendBaseUrl = String.fromEnvironment(
  'WOW_BACKEND_URL',
  defaultValue: kReleaseMode ? kProdBackendBaseUrl : kDevBackendBaseUrl,
);

/// The backend's shared access key (backend docs/SECURITY.md) - supplied at
/// build time via `--dart-define=WOW_API_KEY=...` (and the same value in the
/// WOW_API_KEY environment variable for the native Android build), NEVER
/// committed. Empty = send no key (an un-keyed local backend).
const String kApiAccessKey = String.fromEnvironment('WOW_API_KEY');

void main() {
  runApp(
    WowAiApp(
      apiClient: WowApiClient(baseUrl: kDefaultBackendBaseUrl, apiKey: kApiAccessKey),
    ),
  );
}
