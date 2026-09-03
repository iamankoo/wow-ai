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
  });

  factory WowPermissionStatus.fromMap(Map<Object?, Object?> map) {
    return WowPermissionStatus(
      readPhoneState: map['readPhoneState'] as bool? ?? false,
      answerPhoneCalls: map['answerPhoneCalls'] as bool? ?? false,
      contacts: map['contacts'] as bool? ?? false,
      callScreeningRole: map['callScreeningRole'] as bool? ?? false,
      callScreeningRoleAvailable: map['callScreeningRoleAvailable'] as bool? ?? false,
    );
  }

  final bool readPhoneState;
  final bool answerPhoneCalls;
  final bool contacts;
  final bool callScreeningRole;
  final bool callScreeningRoleAvailable;

  bool get phonePermissionsGranted => readPhoneState && answerPhoneCalls;

  /// Everything WOW's real telephony architecture needs to actually screen
  /// calls - not just "permission granted" but the CALL_SCREENING role too
  /// (a role, not a runtime permission - see WowCallScreeningService).
  bool get callHandlingReady =>
      phonePermissionsGranted && (!callScreeningRoleAvailable || callScreeningRole);

  bool get allGranted => phonePermissionsGranted && contacts && callHandlingReady;
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
