import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/wow_theme.dart';
import '../settings/settings_screen.dart';
import 'edit_profile_screen.dart';

/// Follows assets/profile_page.png's layout - profile card, Account and
/// Preferences sections, bottom nav - but only for rows backed by a real
/// capability (Phase 6 Part N/G: "must either perform its real intended
/// action, OR be removed until its backend capability exists"). The
/// reference design's Plan/Change Password/Devices/Export Data/
/// Notifications/Theme/Log Out rows assume a billing, auth, device-
/// management and notification-preferences system this project doesn't
/// have (Phase 1: "no real account system exists yet") - rather than fake
/// those, this screen keeps only what's real: identity fields (editable),
/// real verification status, real member-since date, and the real
/// language/voice/floating-button/permissions settings.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? _user;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final user = await widget.apiClient.getUser(kDemoUserId);
      if (mounted) setState(() => _user = user);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load profile: $e');
    }
  }

  String _memberSince(String? createdAt) {
    if (createdAt == null) return '';
    final dt = DateTime.tryParse(createdAt);
    if (dt == null) return '';
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    return '${months[dt.month - 1]} ${dt.year}';
  }

  @override
  Widget build(BuildContext context) {
    final user = _user;
    return Scaffold(
      backgroundColor: WowColors.background,
      body: SafeArea(
        child: user == null
            ? Center(
                child: _error != null
                    ? Text(_error!, style: const TextStyle(color: WowColors.textMuted))
                    : const CircularProgressIndicator(color: WowColors.primaryBlue),
              )
            : RefreshIndicator(
                onRefresh: _load,
                color: WowColors.primaryBlue,
                backgroundColor: WowColors.surface,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                  children: [
                    const Text('Profile',
                        style: TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 2),
                    const Text('Manage your account and preferences',
                        style: TextStyle(color: WowColors.textMuted, fontSize: 13)),
                    const SizedBox(height: 18),
                    _buildProfileCard(user),
                    const SizedBox(height: 22),
                    _sectionLabel('Account'),
                    _buildRow(
                      icon: Icons.person_outline,
                      color: WowColors.primaryBlue,
                      title: 'Personal Information',
                      subtitle: 'Update your name, email and phone number',
                      onTap: () async {
                        final updated = await Navigator.of(context).push<Map<String, dynamic>>(
                          MaterialPageRoute(
                            builder: (_) => EditProfileScreen(apiClient: widget.apiClient, user: user),
                          ),
                        );
                        if (updated != null && mounted) setState(() => _user = updated);
                        if (updated == null) _load();
                      },
                    ),
                    const SizedBox(height: 20),
                    _sectionLabel('Preferences'),
                    _buildRow(
                      icon: Icons.settings_outlined,
                      color: WowColors.accentPurple,
                      title: 'WOW Settings',
                      subtitle: 'Language, voice, floating button and permissions',
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => SettingsScreen(apiClient: widget.apiClient, user: user),
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _sectionLabel(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text,
            style: const TextStyle(color: WowColors.textMuted, fontSize: 12.5, fontWeight: FontWeight.w600)),
      );

  Widget _verifiedPill(bool verified) => Container(
        margin: const EdgeInsets.only(left: 8),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: verified ? WowColors.success.withValues(alpha: 0.15) : WowColors.surfaceVariant,
          borderRadius: BorderRadius.circular(100),
        ),
        child: Text(
          verified ? 'Verified' : 'Unverified',
          style: TextStyle(
            color: verified ? WowColors.success : WowColors.textMuted,
            fontSize: 10,
            fontWeight: FontWeight.w600,
          ),
        ),
      );

  Widget _buildProfileCard(Map<String, dynamic> user) {
    final name = (user['display_name'] as String?)?.trim().isNotEmpty == true
        ? user['display_name'] as String
        : 'WOW User';
    final initial = name.isNotEmpty ? name[0].toUpperCase() : 'W';
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: WowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(colors: [WowColors.primaryBlue, WowColors.accentPurple]),
                ),
                alignment: Alignment.center,
                child: Text(initial,
                    style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name,
                        style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Flexible(
                          child: Text(user['phone_number'] as String? ?? '',
                              style: const TextStyle(color: WowColors.textSecondary, fontSize: 12.5)),
                        ),
                        _verifiedPill(user['mobile_verified'] == true),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Flexible(
                          child: Text(user['email'] as String? ?? 'No email',
                              style: const TextStyle(color: WowColors.textSecondary, fontSize: 12.5)),
                        ),
                        _verifiedPill(user['email_verified'] == true),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const Divider(color: WowColors.border, height: 26),
          Row(
            children: [
              const Icon(Icons.calendar_month_outlined, color: WowColors.textMuted, size: 16),
              const SizedBox(width: 6),
              Text('Member since ${_memberSince(user['created_at'] as String?)}',
                  style: const TextStyle(color: WowColors.textMuted, fontSize: 12)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRow({
    required IconData icon,
    required Color color,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: WowColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: WowColors.border),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: color.withValues(alpha: 0.15), shape: BoxShape.circle),
              child: Icon(icon, color: color, size: 18),
            ),
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
            const Icon(Icons.chevron_right, color: WowColors.textMuted, size: 20),
          ],
        ),
      ),
    );
  }
}
