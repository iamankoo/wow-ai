import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/floating_button_controller.dart';
import '../../core/permissions_bridge.dart';
import '../../core/update_bridge.dart';
import '../../core/update_checker.dart';
import '../../core/wow_theme.dart';

/// Phase 6 Part O - "at minimum support: language, voice, floating WOW
/// button on/off, WOW activation/deactivation, permissions/status." WOW
/// activation/deactivation itself lives on the main screen (the power
/// button + duration chips ARE that control); this screen covers the rest.
/// Every control here is wired to something real - the backend PATCH
/// /users/{id} for language/voice, the real permissions MethodChannel for
/// status, and real persisted local storage for the floating-button
/// preference. Nothing here is decorative.
///
/// Phase 6 Part T's ABOUT section adds the real update flow: "Check for
/// Updates" hits GitHub's real Releases API for this repository, and a
/// found update is actually downloaded and handed to the real Android
/// package installer (WowUpdateBridge/WowUpdateChecker) - never a
/// simulated check.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.apiClient, required this.user});

  final WowApiClient apiClient;
  final Map<String, dynamic> user;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late String _language = widget.user['preferred_language'] as String? ?? 'english';
  late String _voice = widget.user['voice_gender'] as String? ?? 'female';
  bool _floatingButtonEnabled = true;
  bool _busy = false;
  String? _error;
  WowPermissionStatus? _permissionStatus;
  String? _currentVersionLabel;
  bool _checkingUpdate = false;
  double? _downloadProgress; // null = not downloading

  @override
  void initState() {
    super.initState();
    FloatingButtonController.resync()
        .then((v) => mounted ? setState(() => _floatingButtonEnabled = v) : null);
    WowPermissionsBridge.status()
        .then((s) => mounted ? setState(() => _permissionStatus = s) : null);
    WowUpdateBridge.currentVersion().then((v) {
      if (mounted) setState(() => _currentVersionLabel = v.$1);
    });
  }

  Future<void> _savePreferences() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.apiClient.updateProfile(
        widget.user['id'] as String,
        preferredLanguage: _language,
        voiceGender: _voice,
      );
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Preferences saved')));
      }
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not save: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleFloatingButton(bool value) async {
    final actual = await FloatingButtonController.setEnabled(context, value);
    if (mounted) setState(() => _floatingButtonEnabled = actual);
  }

  Future<void> _checkForUpdates() async {
    setState(() => _checkingUpdate = true);
    try {
      final update = await WowUpdateChecker.checkForUpdate();
      if (!mounted) return;
      if (update == null) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text("You're on the latest version")));
        return;
      }
      await _offerUpdate(update);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Could not check for updates: $e')));
      }
    } finally {
      if (mounted) setState(() => _checkingUpdate = false);
    }
  }

  Future<void> _offerUpdate(WowUpdateInfo update) async {
    final proceed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: WowColors.surface,
        title: Text('WOW AI v${update.version} available',
            style: const TextStyle(color: Colors.white, fontSize: 16)),
        content: SingleChildScrollView(
          child: Text(
            update.releaseNotes.isEmpty ? 'A new version is available.' : update.releaseNotes,
            style: const TextStyle(color: WowColors.textSecondary, fontSize: 13),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Later', style: TextStyle(color: WowColors.textMuted)),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Download & Install', style: TextStyle(color: WowColors.primaryBlue)),
          ),
        ],
      ),
    );
    if (proceed == true) await _downloadAndInstall(update);
  }

  Future<void> _downloadAndInstall(WowUpdateInfo update) async {
    setState(() => _downloadProgress = 0);
    try {
      final path = await WowUpdateChecker.downloadApk(
        update.downloadUrl,
        onProgress: (p) {
          if (mounted) setState(() => _downloadProgress = p);
        },
      );
      var granted = await WowUpdateBridge.hasInstallPermission();
      if (!granted) granted = await WowUpdateBridge.requestInstallPermission();
      if (!granted) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'WOW needs "Install unknown apps" permission to install the update.',
              ),
            ),
          );
        }
        return;
      }
      await WowUpdateBridge.installApk(path);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Update failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _downloadProgress = null);
    }
  }

  Widget _sectionLabel(String text) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
        child: Text(text,
            style: const TextStyle(
                color: WowColors.textMuted,
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
                letterSpacing: .04)),
      );

  Widget _choiceRow(List<(String, String)> options, String selected, void Function(String) onSelect) {
    return Row(
      children: options.map((o) {
        final isSelected = o.$1 == selected;
        return Expanded(
          child: Padding(
            padding: const EdgeInsets.only(right: 8),
            child: GestureDetector(
              onTap: () => onSelect(o.$1),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: WowColors.surfaceVariant,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: isSelected ? WowColors.primaryBlue : WowColors.border),
                ),
                child: Text(o.$2,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: isSelected ? WowColors.primaryBlue : WowColors.textSecondary,
                        fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                        fontSize: 12.5)),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _permissionRow(String title, bool? granted) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(
            granted == null
                ? Icons.hourglass_empty
                : (granted ? Icons.check_circle : Icons.error_outline),
            size: 16,
            color: granted == null
                ? WowColors.textMuted
                : (granted ? WowColors.success : WowColors.textMuted),
          ),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(color: WowColors.textSecondary, fontSize: 13)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final status = _permissionStatus;
    return Scaffold(
      backgroundColor: WowColors.background,
      appBar: AppBar(
        backgroundColor: WowColors.background,
        elevation: 0,
        title: const Text('WOW Settings', style: TextStyle(color: Colors.white, fontSize: 17)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          children: [
            _sectionLabel('LANGUAGE'),
            _choiceRow(
              [('hindi', 'Hindi'), ('hinglish', 'Hinglish'), ('english', 'English')],
              _language,
              (v) => setState(() => _language = v),
            ),
            _sectionLabel('VOICE'),
            _choiceRow(
              [('female', 'Female'), ('male', 'Male')],
              _voice,
              (v) => setState(() => _voice = v),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: const TextStyle(color: Color(0xFFFFB4B4), fontSize: 12.5)),
              ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _busy ? null : _savePreferences,
                style: ElevatedButton.styleFrom(
                  backgroundColor: WowColors.primaryBlue,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Save', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
              ),
            ),
            _sectionLabel('FLOATING WOW BUTTON'),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
              decoration: BoxDecoration(
                color: WowColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: WowColors.border),
              ),
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _floatingButtonEnabled,
                onChanged: _toggleFloatingButton,
                activeThumbColor: WowColors.primaryBlue,
                title: const Text('Show floating button',
                    style: TextStyle(color: Colors.white, fontSize: 13.5)),
                subtitle: const Text('Quick access to WOW ON/OFF, voice and text commands',
                    style: TextStyle(color: WowColors.textMuted, fontSize: 11.5)),
              ),
            ),
            _sectionLabel('PERMISSIONS'),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: WowColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: WowColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _permissionRow('Contacts', status?.contacts),
                  _permissionRow('Phone state & call answering', status?.phonePermissionsGranted),
                  _permissionRow(
                    'Call screening role',
                    status == null
                        ? null
                        : (status.callScreeningRoleAvailable ? status.callScreeningRole : true),
                  ),
                ],
              ),
            ),
            _sectionLabel('ABOUT'),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: WowColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: WowColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Version ${_currentVersionLabel ?? '...'}',
                      style: const TextStyle(color: WowColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: 12),
                  if (_downloadProgress != null)
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        LinearProgressIndicator(
                          value: _downloadProgress! > 0 ? _downloadProgress : null,
                          color: WowColors.primaryBlue,
                          backgroundColor: WowColors.surfaceVariant,
                        ),
                        const SizedBox(height: 6),
                        const Text('Downloading update...',
                            style: TextStyle(color: WowColors.textMuted, fontSize: 11.5)),
                      ],
                    )
                  else
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        onPressed: _checkingUpdate ? null : _checkForUpdates,
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: WowColors.border),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: _checkingUpdate
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: WowColors.primaryBlue))
                            : const Text('Check for Updates', style: TextStyle(color: Colors.white)),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
