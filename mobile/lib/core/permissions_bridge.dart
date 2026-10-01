import 'package:flutter/services.dart';

/// Real status of the Android permissions/role WOW's telephony and
/// contacts features need - never assumed, always read from the actual
/// platform via MainActivity's PERMISSIONS_CHANNEL (Phase 6 Part D).
class WowPermissionStatus {
  const WowPermissionStatus({
    required this.readPhoneState,
    required this.answerPhoneCalls,
    required this.contacts,
    required this.callScreeningRole,
    required this.callScreeningRoleAvailable,
    required this.microphone,
    required this.notifications,
  });

  factory WowPermissionStatus.fromMap(Map<Object?, Object?> map) {
    return WowPermissionStatus(
      readPhoneState: map['readPhoneState'] as bool? ?? false,
      answerPhoneCalls: map['answerPhoneCalls'] as bool? ?? false,
      contacts: map['contacts'] as bool? ?? false,
      callScreeningRole: map['callScreeningRole'] as bool? ?? false,
      callScreeningRoleAvailable: map['callScreeningRoleAvailable'] as bool? ?? false,
      microphone: map['microphone'] as bool? ?? false,
      notifications: map['notifications'] as bool? ?? false,
    );
  }

  final bool readPhoneState;
  final bool answerPhoneCalls;
  final bool contacts;
  final bool callScreeningRole;
  final bool callScreeningRoleAvailable;
  // WOW Telephony Validation stage: microphone (real STT input - voice
  // commands today, real caller-audio processing once a telephony bridge
  // exists) and notifications (the real "WOW handled a call" alert) -
  // previously granted ad hoc elsewhere in the app but never surfaced to
  // the explicit permission-review UI.
  final bool microphone;
  final bool notifications;

  bool get phonePermissionsGranted => readPhoneState && answerPhoneCalls;

  /// Everything WOW's real telephony architecture needs to actually screen
  /// calls - not just "permission granted" but the CALL_SCREENING role too
  /// (a role, not a runtime permission - see WowCallScreeningService).
  bool get callHandlingReady =>
      phonePermissionsGranted && (!callScreeningRoleAvailable || callScreeningRole);

  /// Everything WOW's real call-handling AND voice pipeline need - the
  /// real gate `_toggleWow` checks before activating the call assistant,
  /// so WOW can never be turned "on" while silently missing a permission
  /// it actually depends on.
  bool get readyForCallAssistant => callHandlingReady && contacts && microphone;

  bool get allGranted => readyForCallAssistant && notifications;
}

/// Dart-side wrapper for MainActivity's real native permission/role
/// plumbing - no permission is ever assumed granted; every call reads or
/// changes real platform state.
class WowPermissionsBridge {
  static const _channel = MethodChannel('com.wowai.app/permissions');

  static Future<WowPermissionStatus> status() async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('status');
    return WowPermissionStatus.fromMap(result ?? const {});
  }

  /// Triggers the real Android runtime-permission dialog for
  /// READ_PHONE_STATE + ANSWER_PHONE_CALLS + READ_CONTACTS (skips any
  /// already granted). Returns the real resulting status.
  static Future<WowPermissionStatus> requestPhoneAndContacts() async {
    final result =
        await _channel.invokeMethod<Map<Object?, Object?>>('requestPhoneAndContacts');
    return WowPermissionStatus.fromMap(result ?? const {});
  }

  /// Triggers ONE real Android multi-permission dialog covering every
  /// runtime-grantable permission WOW's call assistant and voice pipeline
  /// need (phone state, answer calls, contacts, microphone, and
  /// notifications on API 33+) - skips any already granted. This is what
  /// PrivacyPermissionsScreen's single "Grant access" action calls; the
  /// CALL_SCREENING role still needs its own separate step below (a
  /// different Android mechanism - a role, not a runtime permission).
  static Future<WowPermissionStatus> requestCorePermissions() async {
    final result =
        await _channel.invokeMethod<Map<Object?, Object?>>('requestCorePermissions');
    return WowPermissionStatus.fromMap(result ?? const {});
  }

  /// Triggers the real Android CALL_SCREENING role-request system screen
  /// (RoleManager) - a role, not a permission, so this is a different
  /// Android mechanism than requestPhoneAndContacts. No-op if already held
  /// or unavailable (API < 29).
  static Future<WowPermissionStatus> requestCallScreeningRole() async {
    final result =
        await _channel.invokeMethod<Map<Object?, Object?>>('requestCallScreeningRole');
    return WowPermissionStatus.fromMap(result ?? const {});
  }
}
