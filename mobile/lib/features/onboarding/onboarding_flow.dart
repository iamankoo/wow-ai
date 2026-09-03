import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/permissions_bridge.dart';
import '../../core/wow_theme.dart';
import '../home/home_screen.dart';

/// Phase 6 Part C/D/F - the real profile/verification/permissions gate.
/// WOW cannot become active until this flow's own backend state
/// (User.profile_complete - name + phone + 18+ + both channels actually
/// verified, computed server-side) says so; there is no separate local
/// "onboarding done" flag that could drift from that real state.
class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({super.key, required this.apiClient, required this.initialUser});

  final WowApiClient apiClient;
  final Map<String, dynamic> initialUser;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  late Map<String, dynamic> _user;
  int _step = 0;

  @override
  void initState() {
    super.initState();
    _user = widget.initialUser;
    _step = _initialStepFor(_user);
  }

  static int _initialStepFor(Map<String, dynamic> user) {
    if ((user['display_name'] as String?)?.trim().isEmpty ?? true) return 0;
    if (user['phone_number'] == null || (user['phone_number'] as String).trim().isEmpty) return 0;
    if (user['date_of_birth'] == null) return 0;
    if (user['mobile_verified'] != true) return 1;
    if (user['email_verified'] != true) return 2;
    return 3; // profile itself is complete - permissions/preferences remain
  }

  void _advance(Map<String, dynamic> refreshedUser) {
    setState(() {
      _user = refreshedUser;
      _step += 1;
    });
  }

  void _goToHome() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => HomeScreen(apiClient: widget.apiClient)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final steps = <Widget>[
      _ProfileFormStep(apiClient: widget.apiClient, user: _user, onSaved: _advance),
      _VerifyStep(
        key: const ValueKey('verify-mobile'),
        apiClient: widget.apiClient,
        user: _user,
        channel: 'mobile',
        destinationLabel: _user['phone_number'] as String? ?? '',
        onVerified: _advance,
      ),
      _VerifyStep(
        key: const ValueKey('verify-email'),
        apiClient: widget.apiClient,
        user: _user,
        channel: 'email',
        destinationLabel: _user['email'] as String? ?? '',
        onVerified: _advance,
      ),
      _PermissionsStep(onDone: () => setState(() => _step += 1)),
      _PreferencesStep(apiClient: widget.apiClient, user: _user, onDone: _goToHome),
    ];

    return Scaffold(
      backgroundColor: WowColors.background,
      body: SafeArea(
        child: Column(
          children: [
            _StepHeader(step: _step, totalSteps: steps.length),
            Expanded(child: steps[_step.clamp(0, steps.length - 1)]),
          ],
        ),
      ),
    );
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({required this.step, required this.totalSteps});

  final int step;
  final int totalSteps;

  static const _labels = ['Profile', 'Verify mobile', 'Verify email', 'Permissions', 'Preferences'];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text.rich(
                TextSpan(children: [
                  TextSpan(
                      text: 'WOW',
                      style: TextStyle(
                          color: WowColors.textPrimary, fontWeight: FontWeight.w800, fontSize: 16)),
                  TextSpan(
                      text: ' AI',
                      style: TextStyle(
                          color: WowColors.primaryBlue, fontWeight: FontWeight.w800, fontSize: 16)),
                ]),
              ),
              const Spacer(),
              Text('Step ${(step.clamp(0, totalSteps - 1)) + 1} of $totalSteps',
                  style: const TextStyle(color: WowColors.textMuted, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (step.clamp(0, totalSteps - 1) + 1) / totalSteps,
              minHeight: 6,
              backgroundColor: WowColors.surfaceVariant,
              valueColor: const AlwaysStoppedAnimation(WowColors.primaryBlue),
            ),
          ),
          const SizedBox(height: 4),
          Text(_labels[step.clamp(0, _labels.length - 1)],
              style: const TextStyle(color: WowColors.textSecondary, fontSize: 12)),
        ],
      ),
    );
  }
}

class _StepScaffold extends StatelessWidget {
  const _StepScaffold({
    required this.title,
    required this.subtitle,
    required this.children,
    this.error,
  });

  final String title;
  final String subtitle;
  final List<Widget> children;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  color: WowColors.textPrimary, fontSize: 22, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Text(subtitle, style: const TextStyle(color: WowColors.textMuted, fontSize: 13.5, height: 1.4)),
          const SizedBox(height: 20),
          ...children,
          if (error != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0x33FF6B6B),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(error!, style: const TextStyle(color: Color(0xFFFFB4B4), fontSize: 13)),
            ),
          ],
        ],
      ),
    );
  }
}

InputDecoration _fieldDecoration(String label) => InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: WowColors.textMuted),
      filled: true,
      fillColor: WowColors.surfaceVariant,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
    );

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({required this.label, required this.onPressed, this.busy = false});
  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: WowColors.primaryBlue,
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        onPressed: busy ? null : onPressed,
        child: busy
            ? const SizedBox(
                width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
            : Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Step 1: profile form (name, mobile, email, DOB - 18+ enforced server-side)
// ---------------------------------------------------------------------------

class _ProfileFormStep extends StatefulWidget {
  const _ProfileFormStep({required this.apiClient, required this.user, required this.onSaved});
  final WowApiClient apiClient;
  final Map<String, dynamic> user;
  final void Function(Map<String, dynamic>) onSaved;

  @override
  State<_ProfileFormStep> createState() => _ProfileFormStepState();
}

class _ProfileFormStepState extends State<_ProfileFormStep> {
  late final _name = TextEditingController(text: widget.user['display_name'] as String?);
  late final _mobile = TextEditingController(text: widget.user['phone_number'] as String?);
  late final _email = TextEditingController(text: widget.user['email'] as String?);
  DateTime? _dob;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final dobStr = widget.user['date_of_birth'] as String?;
    if (dobStr != null) _dob = DateTime.tryParse(dobStr);
  }

  Future<void> _pickDob() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dob ?? DateTime(now.year - 25, now.month, now.day),
      firstDate: DateTime(now.year - 100),
      lastDate: now,
      helpText: 'Date of birth',
    );
    if (picked != null) setState(() => _dob = picked);
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty || _mobile.text.trim().isEmpty || _dob == null) {
      setState(() => _error = 'Name, mobile number and date of birth are required.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final updated = await widget.apiClient.updateProfile(
        widget.user['id'] as String,
        displayName: _name.text.trim(),
        phoneNumber: _mobile.text.trim(),
        email: _email.text.trim().isEmpty ? null : _email.text.trim(),
        dateOfBirth: _dob,
      );
      widget.onSaved(updated);
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not save profile: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _StepScaffold(
      title: 'Set up your profile',
      subtitle: 'WOW needs a few real details before it can answer calls on your behalf. '
          'You must be 18 or older to use WOW.',
      error: _error,
      children: [
        TextField(controller: _name, style: const TextStyle(color: Colors.white), decoration: _fieldDecoration('Full name')),
        const SizedBox(height: 12),
        TextField(
          controller: _mobile,
          keyboardType: TextInputType.phone,
          style: const TextStyle(color: Colors.white),
          decoration: _fieldDecoration('Mobile number'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          style: const TextStyle(color: Colors.white),
          decoration: _fieldDecoration('Email address'),
        ),
        const SizedBox(height: 12),
        GestureDetector(
          onTap: _pickDob,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            decoration: BoxDecoration(color: WowColors.surfaceVariant, borderRadius: BorderRadius.circular(12)),
            child: Row(
              children: [
                const Icon(Icons.cake_outlined, color: WowColors.textMuted, size: 18),
                const SizedBox(width: 10),
                Text(
                  _dob == null
                      ? 'Date of birth'
                      : '${_dob!.year.toString().padLeft(4, '0')}-${_dob!.month.toString().padLeft(2, '0')}-${_dob!.day.toString().padLeft(2, '0')}',
                  style: TextStyle(color: _dob == null ? WowColors.textMuted : Colors.white),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        _PrimaryButton(label: 'Continue', onPressed: _submit, busy: _busy),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Step 2/3: mobile / email verification (real request+confirm round trip)
// ---------------------------------------------------------------------------

class _VerifyStep extends StatefulWidget {
  const _VerifyStep({
    super.key,
    required this.apiClient,
    required this.user,
    required this.channel,
    required this.destinationLabel,
    required this.onVerified,
  });

  final WowApiClient apiClient;
  final Map<String, dynamic> user;
  final String channel; // 'mobile' | 'email'
  final String destinationLabel;
  final void Function(Map<String, dynamic>) onVerified;

  @override
  State<_VerifyStep> createState() => _VerifyStepState();
}

class _VerifyStepState extends State<_VerifyStep> {
  final _code = TextEditingController();
  bool _busy = false;
  bool _sent = false;
  String? _devCode;
  String? _error;

  Future<void> _sendCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final devCode =
          await widget.apiClient.requestVerificationCode(widget.user['id'] as String, widget.channel);
      setState(() {
        _sent = true;
        _devCode = devCode;
      });
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not send code: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _confirm() async {
    if (_code.text.trim().isEmpty) {
      setState(() => _error = 'Enter the code you received.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.apiClient
          .confirmVerificationCode(widget.user['id'] as String, widget.channel, _code.text.trim());
      final refreshed = await widget.apiClient.getUser(widget.user['id'] as String);
      widget.onVerified(refreshed);
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not verify code: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final label = widget.channel == 'mobile' ? 'mobile number' : 'email address';
    return _StepScaffold(
      title: 'Verify your $label',
      subtitle: widget.destinationLabel.isEmpty
          ? 'Go back and add a $label first.'
          : 'We\'ll send a 6-digit code to ${widget.destinationLabel}.',
      error: _error,
      children: [
        if (!_sent)
          _PrimaryButton(label: 'Send code', onPressed: widget.destinationLabel.isEmpty ? null : _sendCode, busy: _busy)
        else ...[
          if (_devCode != null)
            Container(
              margin: const EdgeInsets.only(bottom: 14),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: WowColors.accentPurple.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                'Dev mode (no SMS/email service configured yet): your code is $_devCode',
                style: const TextStyle(color: WowColors.textSecondary, fontSize: 12.5),
              ),
            ),
          TextField(
            controller: _code,
            keyboardType: TextInputType.number,
            style: const TextStyle(color: Colors.white, letterSpacing: 4, fontSize: 20),
            textAlign: TextAlign.center,
            decoration: _fieldDecoration('6-digit code'),
          ),
          const SizedBox(height: 16),
          _PrimaryButton(label: 'Verify', onPressed: _confirm, busy: _busy),
          const SizedBox(height: 10),
          TextButton(
            onPressed: _busy ? null : _sendCode,
            child: const Text('Resend code', style: TextStyle(color: WowColors.textMuted)),
          ),
        ],
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Step 4: permissions (real Android prompts via WowPermissionsBridge)
// ---------------------------------------------------------------------------

class _PermissionsStep extends StatefulWidget {
  const _PermissionsStep({required this.onDone});
  final VoidCallback onDone;

  @override
  State<_PermissionsStep> createState() => _PermissionsStepState();
}

class _PermissionsStepState extends State<_PermissionsStep> {
  WowPermissionStatus? _status;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    final status = await WowPermissionsBridge.status();
    if (mounted) setState(() => _status = status);
  }

  Future<void> _requestPhoneAndContacts() async {
    setState(() => _busy = true);
    final status = await WowPermissionsBridge.requestPhoneAndContacts();
    if (mounted) {
      setState(() {
        _status = status;
        _busy = false;
      });
    }
  }

  Future<void> _requestRole() async {
    setState(() => _busy = true);
    final status = await WowPermissionsBridge.requestCallScreeningRole();
    if (mounted) {
      setState(() {
        _status = status;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    return _StepScaffold(
      title: 'Permissions WOW needs',
      subtitle: 'WOW only asks for what it actually uses - contacts, so it can recognize '
          'callers, and call handling, so it can screen and answer calls when you turn it on.',
      children: [
        if (status == null)
          const Center(child: CircularProgressIndicator(color: WowColors.primaryBlue))
        else ...[
          _PermissionTile(
            icon: Icons.contacts_outlined,
            title: 'Contacts',
            subtitle: 'Recognize who is calling you',
            granted: status.contacts && status.phonePermissionsGranted,
          ),
          const SizedBox(height: 10),
          _PermissionTile(
            icon: Icons.phone_in_talk_outlined,
            title: 'Phone state & call answering',
            subtitle: 'Detect incoming calls and (when authorized) answer them',
            granted: status.phonePermissionsGranted,
          ),
          const SizedBox(height: 10),
          _PermissionTile(
            icon: Icons.call_received,
            title: 'Call screening role',
            subtitle: status.callScreeningRoleAvailable
                ? 'A system role Android requires before WOW can screen calls'
                : 'Not available on this Android version',
            granted: status.callScreeningRole,
          ),
          const SizedBox(height: 20),
          if (!status.phonePermissionsGranted || !status.contacts)
            _PrimaryButton(label: 'Grant phone & contacts access', onPressed: _requestPhoneAndContacts, busy: _busy)
          else if (status.callScreeningRoleAvailable && !status.callScreeningRole)
            _PrimaryButton(label: 'Grant call screening role', onPressed: _requestRole, busy: _busy)
          else
            _PrimaryButton(label: 'Continue', onPressed: widget.onDone),
          if (status.allGranted == false && status.phonePermissionsGranted && status.contacts && (!status.callScreeningRoleAvailable || status.callScreeningRole))
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: TextButton(onPressed: widget.onDone, child: const Text('Continue', style: TextStyle(color: WowColors.textMuted))),
            ),
        ],
      ],
    );
  }
}

class _PermissionTile extends StatelessWidget {
  const _PermissionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.granted,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool granted;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: WowColors.surface, borderRadius: BorderRadius.circular(14), border: Border.all(color: WowColors.border)),
      child: Row(
        children: [
          Icon(icon, color: WowColors.primaryBlue, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5)),
                Text(subtitle, style: const TextStyle(color: WowColors.textMuted, fontSize: 11.5)),
              ],
            ),
          ),
          Icon(granted ? Icons.check_circle : Icons.radio_button_unchecked,
              color: granted ? WowColors.success : WowColors.textMuted, size: 20),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Step 5: language + voice preference (real PATCH, persisted server-side)
// ---------------------------------------------------------------------------

class _PreferencesStep extends StatefulWidget {
  const _PreferencesStep({required this.apiClient, required this.user, required this.onDone});
  final WowApiClient apiClient;
  final Map<String, dynamic> user;
  final VoidCallback onDone;

  @override
  State<_PreferencesStep> createState() => _PreferencesStepState();
}

class _PreferencesStepState extends State<_PreferencesStep> {
  late String _language = widget.user['preferred_language'] as String? ?? 'english';
  late String _voice = widget.user['voice_gender'] as String? ?? 'female';
  bool _busy = false;
  String? _error;

  Future<void> _finish() async {
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
      widget.onDone();
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not save preferences: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _choiceRow<T>(List<(String value, String label)> options, String selected, void Function(String) onSelect) {
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

  @override
  Widget build(BuildContext context) {
    return _StepScaffold(
      title: 'How should WOW sound?',
      subtitle: 'WOW speaks Hindi, Hinglish and English using a real local voice model - '
          'no cloud speech service. You can change this later.',
      error: _error,
      children: [
        const Text('Language', style: TextStyle(color: WowColors.textMuted, fontSize: 12)),
        const SizedBox(height: 8),
        _choiceRow(
          [('hindi', 'Hindi'), ('hinglish', 'Hinglish'), ('english', 'English')],
          _language,
          (v) => setState(() => _language = v),
        ),
        const SizedBox(height: 20),
        const Text('Voice', style: TextStyle(color: WowColors.textMuted, fontSize: 12)),
        const SizedBox(height: 8),
        _choiceRow(
          [('female', 'Female'), ('male', 'Male')],
          _voice,
          (v) => setState(() => _voice = v),
        ),
        const SizedBox(height: 28),
        _PrimaryButton(label: 'Finish setup', onPressed: _finish, busy: _busy),
      ],
    );
  }
}
