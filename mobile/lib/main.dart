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

/// Picked by build mode, not a runtime flag - matches
/// WowCallScreeningService.kt/WowAutoAnswer.kt's BuildConfig.BACKEND_BASE_URL,
/// which is selected the same way per Gradle build type.
const String kDefaultBackendBaseUrl = kReleaseMode ? kProdBackendBaseUrl : kDevBackendBaseUrl;

void main() {
  runApp(WowAiApp(apiClient: WowApiClient(baseUrl: kDefaultBackendBaseUrl)));
}
