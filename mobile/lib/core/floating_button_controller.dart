import 'package:flutter/material.dart';

import 'local_prefs.dart';
import 'overlay_bridge.dart';

/// Shared real on/off logic for the floating WOW button (Phase 6 Part H),
/// used by both the home screen's quick-action tile and the settings
/// screen's switch so the two never drift into different behavior. Turning
/// this on actually starts a live Android overlay Window
/// (WowFloatingButtonService) - it is never just a stored preference with
/// no effect.
class FloatingButtonController {
  /// Attempts to reach the requested [value]. Handles the real
  /// SYSTEM_ALERT_WINDOW permission flow (Android's dedicated "display over
  /// other apps" settings screen, not a runtime dialog) when turning on,
  /// starts/stops the real service, and persists the result. Returns the
  /// actual resulting state, which may be false even if [value] was true
  /// (permission denied) - callers must apply the returned value, not
  /// assume [value] took effect.
  static Future<bool> setEnabled(BuildContext context, bool value) async {
    if (!value) {
      await WowOverlayBridge.stop();
      await WowLocalPrefs.setFloatingButtonEnabled(false);
      return false;
    }

    var granted = await WowOverlayBridge.hasPermission();
    if (!granted) {
      granted = await WowOverlayBridge.requestPermission();
    }
    if (!granted) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'WOW needs "Display over other apps" permission to show the floating button.',
            ),
          ),
        );
      }
      await WowLocalPrefs.setFloatingButtonEnabled(false);
      return false;
    }

    await WowOverlayBridge.start();
    await WowLocalPrefs.setFloatingButtonEnabled(true);
    return true;
  }

  /// Re-syncs the persisted preference with real platform state at screen
  /// load: if the preference says "on" but the overlay permission has since
  /// been revoked in system settings, this honestly reports/persists off
  /// rather than showing an enabled switch that isn't actually doing
  /// anything. If genuinely still permitted, defensively re-starts the
  /// service (safe to call when it's already running).
  static Future<bool> resync() async {
    final wanted = await WowLocalPrefs.getFloatingButtonEnabled();
    if (!wanted) return false;
    final granted = await WowOverlayBridge.hasPermission();
    if (!granted) {
      await WowLocalPrefs.setFloatingButtonEnabled(false);
      return false;
    }
    await WowOverlayBridge.start();
    return true;
  }
}
