import 'package:flutter/services.dart';

/// Dart-side wrapper for MainActivity's real
/// com.wowai.app/notifications channel (Phase 8) - lets Dart find out
/// whether this app launch/resume was triggered by tapping the real "WOW
/// handled a call" notification (see NotificationHelper.kt), so
/// splash_screen.dart can route straight to call history instead of the
/// usual Home/onboarding destination.
class WowNotificationBridge {
  static const _channel = MethodChannel('com.wowai.app/notifications');

  /// Read-then-clear: returns true at most once per real notification tap.
  static Future<bool> consumePendingOpenCallHistory() async {
    final result = await _channel.invokeMethod<bool>('consumePendingOpenCallHistory');
    return result ?? false;
  }
}
