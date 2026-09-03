import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/wow_theme.dart';
import 'features/splash/splash_screen.dart';

class WowAiApp extends StatelessWidget {
  const WowAiApp({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WOW AI',
      theme: ThemeData(
        colorSchemeSeed: WowColors.primaryBlue,
        scaffoldBackgroundColor: WowColors.background,
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      home: SplashScreen(apiClient: apiClient),
    );
  }
}
