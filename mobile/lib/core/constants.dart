/// Backend user_id columns are UUID (no real account system exists yet -
/// Phase 1) - this fixed UUID is the Phase 1/2/6 stand-in for "the current
/// device's user" until real accounts exist. Shared with
/// mobile/android/.../WowCallScreeningService.kt's DEMO_USER_ID and
/// WowAutoAnswer.kt so the Flutter UI and the native call-screening path
/// resolve to the same backend user.
const String kDemoUserId = '00000000-0000-0000-0000-000000000001';
