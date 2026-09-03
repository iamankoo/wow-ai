import 'package:flutter/services.dart';

/// Dart-side wrapper for the real Android overlay-permission + floating WOW
/// button service (Phase 6 Part H) - MainActivity's com.wowai.app/overlay
/// channel. SYSTEM_ALERT_WINDOW cannot be granted via the normal
/// runtime-permission dialog; Android requires the dedicated "display over
/// other apps" system settings screen instead, which requestPermission()
/// opens.
class WowOverlayBridge {
  static const _channel = MethodChannel('com.wowai.app/overlay');

  static Future<bool> hasPermission() async {
    final result = await _channel.invokeMethod<bool>('hasPermission');
    return result ?? false;
  }

  /// Opens Android's real "display over other apps" settings screen and
  /// returns the real resulting permission state once the user comes back
  /// to the app.
  static Future<bool> requestPermission() async {
    final result = await _channel.invokeMethod<bool>('requestPermission');
    return result ?? false;
  }

  /// Starts the real WowFloatingButtonService (a live overlay Window, not a
  /// preference). Throws a PlatformException if the overlay permission
  /// isn't actually granted - callers must confirm/request permission first.
  static Future<void> start() => _channel.invokeMethod<void>('start');

  static Future<void> stop() => _channel.invokeMethod<void>('stop');
}
