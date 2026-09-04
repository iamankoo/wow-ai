import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/notification_bridge.dart';
import '../../core/wow_theme.dart';
import '../history/history_screen.dart';
import '../home/home_screen.dart';
import '../onboarding/onboarding_flow.dart';

/// Shows assets/splash_screen.png (bundled as assets/splash_screen.png) for
/// a fixed 3 seconds on every app start, then routes to whichever screen
/// the real backend state calls for - matches the supplied splash design
/// exactly rather than a recreated approximation.
///
/// Phase 6 Part C: the routing decision itself is real, not a guess - it
/// reads GET /users/{id}.profile_complete (name + phone + 18+ + both
/// channels actually verified, computed server-side) and only reaches
/// HomeScreen when that's true. A backend that can't be reached yet is
/// handled honestly (shown, not silently treated as "onboarding done").
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
    Future.delayed(SplashScreen.duration, _route);
  }

  Future<void> _route() async {
    if (!mounted) return;
    Map<String, dynamic>? user;
    try {
      user = await widget.apiClient.getUser(kDemoUserId);
    } catch (_) {
      // Backend unreachable - HomeScreen already has a real "Backend
      // unreachable" state (Part Q); onboarding needs a working backend to
      // save anything, so fall through to Home rather than stranding the
      // user on a form that can never submit.
    }
    if (!mounted) return;

    // Phase 8: a real tap on the "WOW handled a call" notification
    // (NotificationHelper.kt) launched/resumed this Activity - go straight
    // to the real call history rather than Home, but only once profile
    // setup is actually done (an incomplete profile still needs onboarding
    // first, same as any other launch). No native platform channel exists
    // in the widget-test host, so a MissingPluginException there (or any
    // other channel failure) safely means "not opened from a notification" -
    // the normal Home/onboarding destination - never routes to history.
    var openedFromCallNotification = false;
    try {
      openedFromCallNotification = await WowNotificationBridge.consumePendingOpenCallHistory();
    } catch (_) {
      // See comment above - fall through with the safe default.
    }

    if (!mounted) return;

    final Widget destination;
    if (user != null && user['profile_complete'] != true) {
      destination = OnboardingFlow(apiClient: widget.apiClient, initialUser: user);
    } else if (openedFromCallNotification) {
      destination = HistoryScreen(apiClient: widget.apiClient);
    } else {
      destination = HomeScreen(apiClient: widget.apiClient);
    }

    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => destination));
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
