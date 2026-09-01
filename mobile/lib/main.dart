import 'package:flutter/material.dart';

import 'app.dart';
import 'core/api_client.dart';

/// Backend base URL. `10.0.2.2` is the Android emulator's alias for the host
/// machine's `localhost` where the FastAPI backend runs during development.
const String kDefaultBackendBaseUrl = 'http://10.0.2.2:8000';

void main() {
  runApp(WowAiApp(apiClient: WowApiClient(baseUrl: kDefaultBackendBaseUrl)));
}
