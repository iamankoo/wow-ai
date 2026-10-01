import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/permissions_bridge.dart';
import '../../core/wow_theme.dart';

/// WOW Call Privacy/Control - the real, explicit permission and privacy
/// review screen (WOW Telephony Validation stage). Reachable at any time
/// from Settings, and shown before WOW's call assistant is ever turned on
/// for the first time (see home_screen.dart's activation-confirmation
/// flow) - not just once during onboarding.
///
/// Real, not decorative: every permission tile reads and requests actual
/// Android platform state via WowPermissionsBridge (no assumed/fake
/// status), the "allow WOW's self-learning pipeline to use approved
/// interactions" toggle writes the real, previously-API-invisible
/// `User.training_data_consent` column (see app/schemas/brain.py), and
/// the ON/OFF control at the bottom calls the same real
/// POST /users/{id}/activation endpoint the main screen uses - so WOW can
/// be turned off completely from here too, not just from Home.
class PrivacyPermissionsScreen extends StatefulWidget {
  const PrivacyPermissionsScreen({super.key, required this.apiClient, required this.user});

  final WowApiClient apiClient;
  final Map<String, dynamic> user;

  @override
  State<PrivacyPermissionsScreen> createState() => _PrivacyPermissionsScreenState();
}

class _PrivacyPermissionsScreenState extends State<PrivacyPermissionsScreen> with WidgetsBindingObserver {
  WowPermissionStatus? _status;
  bool _busyPermissions = false;
  bool _busyRole = false;
  bool _busyConsent = false;
  bool _busyToggle = false;
  late bool _trainingDataConsent =
      widget.user['training_data_consent'] as bool? ?? false;
  late bool _callAssistantEnabled =
      widget.user['call_assistant_enabled'] as bool? ?? false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refreshPermissions();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // A permission granted/revoked via Android's own App Info settings
    // screen (not just WOW's own request dialogs) must be reflected the
    // moment the user comes back to this screen - never a stale reading.
    if (state == AppLifecycleState.resumed) _refreshPermissions();
  }

  Future<void> _refreshPermissions() async {
    final status = await WowPermissionsBridge.status();
    if (mounted) setState(() => _status = status);
  }

  Future<void> _grantCorePermissions() async {
    setState(() => _busyPermissions = true);
    final status = await WowPermissionsBridge.requestCorePermissions();
    if (mounted) {
      setState(() {
        _status = status;
        _busyPermissions = false;
      });
    }
  }

  Future<void> _grantCallScreeningRole() async {
    setState(() => _busyRole = true);
    final status = await WowPermissionsBridge.requestCallScreeningRole();
    if (mounted) {
      setState(() {
        _status = status;
        _busyRole = false;
      });
    }
  }

  Future<void> _setTrainingDataConsent(bool value) async {
    final previous = _trainingDataConsent;
    setState(() {
      _trainingDataConsent = value;
      _busyConsent = true;
      _error = null;
    });
    try {
      await widget.apiClient.updateProfile(
        widget.user['id'] as String,
        trainingDataConsent: value,
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          _trainingDataConsent = previous; // real failure - do not claim it saved
          _error = 'Could not save: $e';
        });
      }
    } finally {
      if (mounted) setState(() => _busyConsent = false);
    }
  }

  Future<void> _turnWowOff() async {
    setState(() {
      _busyToggle = true;
      _error = null;
    });
    try {
      final response = await widget.apiClient.setActivation(kDemoUserId, 'off');
      if (mounted) {
        setState(() {
          _callAssistantEnabled = response['call_assistant_enabled'] as bool? ?? false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not reach WOW: $e');
    } finally {
      if (mounted) setState(() => _busyToggle = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    return Scaffold(
      backgroundColor: WowColors.background,
      appBar: AppBar(
        backgroundColor: WowColors.background,
        elevation: 0,
        title: const Text('Privacy & Permissions', style: TextStyle(color: Colors.white, fontSize: 17)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
          children: [
            _wowStatusBanner(),
            const SizedBox(height: 20),
            const Text(
              'What WOW can access',
              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            const Text(
              'WOW only uses these while it is turned ON. Turning WOW off at any time '
              'stops all of it immediately.',
              style: TextStyle(color: WowColors.textMuted, fontSize: 12.5, height: 1.4),
            ),
            const SizedBox(height: 14),
            if (status == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator(color: WowColors.primaryBlue)),
              )
            else ...[
              _AccessTile(
                icon: Icons.call_received,
                title: 'Call handling',
                description:
                    'Detect incoming calls and, only when you turn WOW on, answer them if you '
                    "don't after a short wait.",
                granted: status.phonePermissionsGranted,
              ),
              _AccessTile(
                icon: Icons.mic_none,
                title: 'Microphone / audio',
                description:
                    'Capture voice commands you give WOW, and (once WOW can join a real call) '
                    'the caller\'s audio, so WOW can understand and respond to speech.',
                granted: status.microphone,
              ),
              _AccessTile(
                icon: Icons.contacts_outlined,
                title: 'Contacts',
                description: 'Recognize who is calling you by matching the number against your contacts.',
                granted: status.contacts,
              ),
              _AccessTile(
                icon: Icons.notifications_none,
                title: 'Notifications',
                description: 'Let you know when WOW has handled a call on your behalf.',
                granted: status.notifications,
              ),
              _AccessTile(
                icon: Icons.shield_outlined,
                title: 'Call-screening role',
                description: status.callScreeningRoleAvailable
                    ? 'A system role Android requires before any app - including WOW - can screen calls.'
                    : 'Not available on this Android version - WOW will skip this step.',
                granted: !status.callScreeningRoleAvailable || status.callScreeningRole,
              ),
              const _AccessTile(
                icon: Icons.psychology_outlined,
                title: 'AI processing',
                description:
                    "Your voice and the caller's speech are transcribed and understood by WOW's "
                    'own self-hosted AI pipeline (speech recognition, WOW Brain, and speech '
                    'synthesis) - never sent to a third-party cloud AI service.',
                granted: true,
                infoOnly: true,
              ),
              const SizedBox(height: 8),
              if (!status.phonePermissionsGranted || !status.contacts || !status.microphone || !status.notifications)
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _busyPermissions ? null : _grantCorePermissions,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: WowColors.primaryBlue,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: _busyPermissions
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Grant access', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                  ),
                ),
              if (status.callScreeningRoleAvailable && !status.callScreeningRole) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: _busyRole ? null : _grantCallScreeningRole,
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: WowColors.border),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: _busyRole
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: WowColors.primaryBlue))
                        : const Text('Grant call-screening role', style: TextStyle(color: Colors.white)),
                  ),
                ),
              ],
            ],
            const SizedBox(height: 28),
            const Text(
              'Data & storage',
              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: WowColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: WowColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Call audio you or a caller speak to WOW is transcribed and processed to decide '
                    'how to respond. Transcripts and a short call summary are saved to your call '
                    'history so you can review them. There is no in-app delete button yet - stored '
                    'call data is removed by the retention cleanup on the server.',
                    style: TextStyle(color: WowColors.textSecondary, fontSize: 12.5, height: 1.45),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Improve WOW with my calls',
                                style: TextStyle(color: Colors.white, fontSize: 13.5, fontWeight: FontWeight.w600)),
                            SizedBox(height: 2),
                            Text(
                              'Optional. Only interactions you or a human reviewer explicitly approve '
                              'are ever used - off by default.',
                              style: TextStyle(color: WowColors.textMuted, fontSize: 11.5, height: 1.3),
                            ),
                          ],
                        ),
                      ),
                      _busyConsent
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: WowColors.primaryBlue))
                          : Switch(
                              value: _trainingDataConsent,
                              activeThumbColor: WowColors.primaryBlue,
                              onChanged: _setTrainingDataConsent,
                            ),
                    ],
                  ),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Text(_error!, style: const TextStyle(color: Color(0xFFFFB4B4), fontSize: 12.5)),
            ],
            const SizedBox(height: 28),
            if (_callAssistantEnabled)
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _busyToggle ? null : _turnWowOff,
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: Color(0xFFEF4444)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  icon: _busyToggle
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFEF4444)))
                      : const Icon(Icons.power_settings_new, color: Color(0xFFEF4444), size: 18),
                  label: const Text('Turn WOW off now',
                      style: TextStyle(color: Color(0xFFEF4444), fontWeight: FontWeight.w600)),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _wowStatusBanner() {
    final isOn = _callAssistantEnabled;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: WowColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 9,
            height: 9,
            decoration: BoxDecoration(
              color: isOn ? WowColors.success : WowColors.textMuted,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 10),
          Text(
            isOn ? 'WOW is currently ON and can handle calls' : 'WOW is currently OFF',
            style: const TextStyle(color: WowColors.textSecondary, fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _AccessTile extends StatelessWidget {
  const _AccessTile({
    required this.icon,
    required this.title,
    required this.description,
    required this.granted,
    this.infoOnly = false,
  });

  final IconData icon;
  final String title;
  final String description;
  final bool granted;
  // AI-processing disclosure has no on/off grant state of its own - it's
  // always true once WOW is on, so its icon communicates "disclosed", not
  // "granted/missing" the way a real permission tile's does.
  final bool infoOnly;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: WowColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: WowColors.primaryBlue, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5)),
                const SizedBox(height: 2),
                Text(description, style: const TextStyle(color: WowColors.textMuted, fontSize: 11.5, height: 1.35)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Icon(
            infoOnly ? Icons.info_outline : (granted ? Icons.check_circle : Icons.radio_button_unchecked),
            color: infoOnly ? WowColors.textMuted : (granted ? WowColors.success : WowColors.textMuted),
            size: 20,
          ),
        ],
      ),
    );
  }
}
