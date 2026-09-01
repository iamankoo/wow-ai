import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'features/home/home_screen.dart';

class WowAiApp extends StatelessWidget {
  const WowAiApp({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WOW AI',
      theme: ThemeData(colorSchemeSeed: Colors.deepPurple, useMaterial3: true),
      home: HomeScreen(apiClient: apiClient),
    );
  }
}
