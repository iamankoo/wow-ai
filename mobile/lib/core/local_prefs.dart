import 'package:shared_preferences/shared_preferences.dart';

/// Real, persisted device-local preferences (Phase 6 Part D/H) - things
/// that are about *this device*, not the backend user record (which
/// already persists profile/activation/language/voice via the API).
/// Previously the floating-button toggle lived only in HomeScreen's
/// ephemeral State and silently reset to "on" every app restart -
/// "Persist permission state" / floating-button preference (Part D/H)
/// requires it survive that.
class WowLocalPrefs {
  static const _floatingButtonKey = 'floating_button_enabled';

  static Future<bool> getFloatingButtonEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_floatingButtonKey) ?? true;
  }

  static Future<void> setFloatingButtonEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_floatingButtonKey, enabled);
  }
}
