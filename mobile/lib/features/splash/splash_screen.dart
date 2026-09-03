import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/wow_theme.dart';
import '../home/home_screen.dart';

/// Shows assets/splash_screen.png (bundled as assets/splash_screen.png) for
/// a fixed 3 seconds on every app start, then replaces itself with
/// HomeScreen - matches the supplied splash design exactly rather than a
/// recreated approximation.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  static const duration = Duration(seconds: 3);

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    Future.delayed(SplashScreen.duration, () {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => HomeScreen(apiClient: widget.apiClient),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: WowColors.background,
      body: Center(
        child: Image(
          image: AssetImage('assets/splash_screen.png'),
          fit: BoxFit.cover,
          width: double.infinity,
          height: double.infinity,
        ),
      ),
    );
  }
}
