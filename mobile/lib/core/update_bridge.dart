import 'package:flutter/services.dart';

/// Dart-side wrapper for MainActivity's real update-related native
/// plumbing (Phase 6 Part T) - com.wowai.app/update. Covers the pieces
/// that genuinely require native code: reading this APK's own real
/// installed version, a real writable directory for the downloaded
/// release APK, and the real REQUEST_INSTALL_PACKAGES grant/install-intent
/// flow (Android requires the dedicated "install unknown apps" settings
/// screen for that permission, the same pattern as SYSTEM_ALERT_WINDOW).
class WowUpdateBridge {
  static const _channel = MethodChannel('com.wowai.app/update');

  /// This build's real installed version - read from Android's own
  /// PackageManager, never from pubspec.yaml at runtime (Dart code has no
  /// access to that at runtime; this is the actual installed APK's
  /// version).
  static Future<(String versionName, int versionCode)> currentVersion() async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('currentVersion');
    final map = result ?? const {};
    return (
      map['versionName'] as String? ?? '0.0.0',
      (map['versionCode'] as num?)?.toInt() ?? 0,
    );
  }

  /// Real absolute path (getExternalFilesDir()/updates) the downloaded
  /// release APK should be written to - matches the path FileProvider's
  /// file_paths.xml actually shares with the system installer.
  static Future<String> downloadsDir() async {
    final result = await _channel.invokeMethod<String>('downloadsDir');
    if (result == null || result.isEmpty) {
      throw StateError('Native downloadsDir() returned no path');
    }
    return result;
  }

  static Future<bool> hasInstallPermission() async {
    final result = await _channel.invokeMethod<bool>('hasInstallPermission');
    return result ?? false;
  }

  /// Opens Android's real "install unknown apps" settings screen and
  /// returns the real resulting permission state once the user comes back.
  static Future<bool> requestInstallPermission() async {
    final result = await _channel.invokeMethod<bool>('requestInstallPermission');
    return result ?? false;
  }

  /// Launches the real system package installer for the APK at [path].
  /// Throws a PlatformException if REQUEST_INSTALL_PACKAGES isn't granted -
  /// callers must confirm/request permission first.
  static Future<void> installApk(String path) =>
      _channel.invokeMethod<void>('installApk', {'path': path});
}
