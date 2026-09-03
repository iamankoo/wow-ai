import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/wow_theme.dart';
import '../onboarding/onboarding_flow.dart';

/// Real profile editing (Phase 6 Part N) - saves through the same PATCH
/// /users/{id} the onboarding flow uses. If phone_number/email actually
/// changes, the backend resets the corresponding *_verified flag (a
/// verified code only ever proved control over the old destination) -
/// this screen is honest about that rather than silently leaving the old
/// "Verified" badge showing, and routes straight into OnboardingFlow's
/// verify step (which resumes at the correct step from the real backend
/// state) so the user isn't left with an unverified contact and no path
/// to fix it.
class EditProfileScreen extends StatefulWidget {
  const EditProfileScreen({super.key, required this.apiClient, required this.user});

  final WowApiClient apiClient;
  final Map<String, dynamic> user;

  @override
  State<EditProfileScreen> createState() => _EditProfileScreenState();
}

class _EditProfileScreenState extends State<EditProfileScreen> {
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

  Future<void> _save() async {
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
      if (!mounted) return;
      final needsVerification =
          updated['mobile_verified'] != true || updated['email_verified'] != true;
      if (needsVerification) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => OnboardingFlow(apiClient: widget.apiClient, initialUser: updated),
          ),
        );
      } else {
        Navigator.of(context).pop(updated);
      }
    } on WowApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = 'Could not save: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  InputDecoration _decoration(String label) => InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: WowColors.textMuted),
        filled: true,
        fillColor: WowColors.surfaceVariant,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WowColors.background,
      appBar: AppBar(
        backgroundColor: WowColors.background,
        elevation: 0,
        title: const Text('Personal Information', style: TextStyle(color: Colors.white, fontSize: 17)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(controller: _name, style: const TextStyle(color: Colors.white), decoration: _decoration('Full name')),
              const SizedBox(height: 12),
              TextField(
                controller: _mobile,
                keyboardType: TextInputType.phone,
                style: const TextStyle(color: Colors.white),
                decoration: _decoration('Mobile number'),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                style: const TextStyle(color: Colors.white),
                decoration: _decoration('Email address'),
                onChanged: (_) => setState(() {}),
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
              if ((_mobile.text.trim() != (widget.user['phone_number'] as String? ?? '')) ||
                  (_email.text.trim() != (widget.user['email'] as String? ?? '')))
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Text(
                    "Changing your mobile number or email means you'll need to verify it again.",
                    style: TextStyle(color: WowColors.textMuted, fontSize: 12),
                  ),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(_error!, style: const TextStyle(color: Color(0xFFFFB4B4), fontSize: 13)),
                ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _busy ? null : _save,
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
                      : const Text('Save changes', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
