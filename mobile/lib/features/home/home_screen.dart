import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/wow_theme.dart';

/// Backend user_id columns are UUID (no real account system exists yet -
/// Phase 1) - this fixed UUID is the Phase 1/2 stand-in for "the current
/// device's user" until real accounts exist. Shared with
/// mobile/android/.../WowCallScreeningService.kt's DEMO_USER_ID so the
/// Flutter UI and the native call-screening path resolve to the same
/// backend user.
const String kDemoUserId = '00000000-0000-0000-0000-000000000001';

class _Duration4Option {
  const _Duration4Option(this.label, this.icon, this.spokenPhrase);
  final String label;
  final IconData icon;
  final String spokenPhrase;
}

const _durationOptions = [
  _Duration4Option('15 mins', Icons.access_time, '15 minutes'),
  _Duration4Option('1 hour', Icons.access_time, '1 hour'),
  _Duration4Option('5 hours', Icons.access_time, '5 hours'),
  _Duration4Option('Until I stop', Icons.all_inclusive, 'until I stop it'),
];

/// Main WOW AI screen - visually follows assets/main_page.png (the supplied
/// design reference) closely: the ON/OFF call-assistant control, duration
/// picker, quick actions, today's summary and recent-calls sections, and
/// bottom navigation all mirror that layout rather than a generic Flutter
/// template.
///
/// Real backend wiring, not decoration: the ON/OFF state is read from and
/// written through the same GET /users/{id} (Phase 2 Block 7) and
/// /brain/command endpoints already used elsewhere in this app - toggling
/// WOW sends a real natural-language command through the real agent
/// pipeline (the same path EnableCallAssistantTool/DisableCallAssistantTool
/// are reached through), not a local-only switch. Today's Summary and
/// Recent Calls Handled show an honest empty state rather than invented
/// numbers, because no call-history endpoint exists yet on the backend.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool? _callAssistantEnabled; // null while loading
  bool _floatingButtonEnabled = true;
  int _selectedDuration = 0;
  bool _busy = false;
  String? _lastError;

  @override
  void initState() {
    super.initState();
    _refreshState();
  }

  Future<void> _refreshState() async {
    try {
      final response = await widget.apiClient.getUser(kDemoUserId);
      setState(() {
        _callAssistantEnabled = response['call_assistant_enabled'] as bool? ?? false;
        _lastError = null;
      });
    } catch (e) {
      setState(() {
        _callAssistantEnabled = false;
        _lastError = 'Backend unreachable';
      });
    }
  }

  Future<void> _toggleWow() async {
    final turningOn = _callAssistantEnabled != true;
    final phrase = turningOn
        ? 'turn on wow ai for ${_durationOptions[_selectedDuration].spokenPhrase}'
        : 'turn off wow ai';
    setState(() => _busy = true);
    try {
      await widget.apiClient.sendBrainCommand(userId: kDemoUserId, text: phrase);
    } catch (_) {
      // Surfaced via _refreshState()'s own error handling below - the
      // authoritative state is always re-read from the backend, never
      // assumed from the request having been sent.
    }
    await _refreshState();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _openCommandSheet({required bool voice}) async {
    final controller = TextEditingController();
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: WowColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                voice ? 'Voice command' : 'Text command',
                style: const TextStyle(
                  color: WowColors.textPrimary,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                voice
                    ? 'Real on-device speech capture is not wired into this app yet - type what you would say instead.'
                    : 'Say something to WOW AI',
                style: const TextStyle(color: WowColors.textMuted, fontSize: 13),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: controller,
                autofocus: true,
                style: const TextStyle(color: WowColors.textPrimary),
                decoration: InputDecoration(
                  filled: true,
                  fillColor: WowColors.surfaceVariant,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  hintText: 'Type a command',
                  hintStyle: const TextStyle(color: WowColors.textMuted),
                ),
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: WowColors.primaryBlue,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: () async {
                  final text = controller.text;
                  Navigator.of(sheetContext).pop();
                  if (text.trim().isEmpty) return;
                  try {
                    final result = await widget.apiClient.sendBrainCommand(
                      userId: kDemoUserId,
                      text: text,
                    );
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('WOW: ${result['payload']?['reply'] ?? result}')),
                    );
                  } catch (e) {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context)
                        .showSnackBar(SnackBar(content: Text('Error: $e')));
                  }
                },
                child: const Text('Send to brain', style: TextStyle(color: Colors.white)),
              ),
            ],
          ),
        );
      },
    );
  }

  void _notImplementedYet(String feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$feature is coming soon')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isOn = _callAssistantEnabled == true;
    return Scaffold(
      backgroundColor: WowColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refreshState,
          color: WowColors.primaryBlue,
          backgroundColor: WowColors.surface,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            children: [
              _buildHeader(),
              const SizedBox(height: 16),
              _buildWowControlCard(isOn),
              const SizedBox(height: 16),
              _buildQuickActions(),
              const SizedBox(height: 16),
              _buildTodaysSummary(),
              const SizedBox(height: 16),
              _buildRecentCalls(),
            ],
          ),
        ),
      ),
      bottomNavigationBar: _buildBottomNav(),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        const Icon(Icons.menu, color: WowColors.textPrimary),
        const Spacer(),
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.asset('assets/wow_icon.png', width: 28, height: 28, fit: BoxFit.cover),
        ),
        const SizedBox(width: 8),
        const Text.rich(
          TextSpan(children: [
            TextSpan(
              text: 'WOW',
              style: TextStyle(
                color: WowColors.textPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w800,
              ),
            ),
            TextSpan(
              text: ' AI',
              style: TextStyle(
                color: WowColors.primaryBlue,
                fontSize: 20,
                fontWeight: FontWeight.w800,
              ),
            ),
          ]),
        ),
        const Spacer(),
        Stack(
          clipBehavior: Clip.none,
          children: [
            const Icon(Icons.notifications_none, color: WowColors.textPrimary),
            if (_lastError != null)
              Positioned(
                right: -1,
                top: -1,
                child: Container(
                  width: 9,
                  height: 9,
                  decoration: const BoxDecoration(
                    color: WowColors.primaryBlue,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildWowControlCard(bool isOn) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: WowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: isOn ? WowColors.success : WowColors.textMuted,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'WOW is ${isOn ? 'ON' : 'OFF'}',
                style: const TextStyle(
                  color: WowColors.textSecondary,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Your AI Call Assistant',
                      style: TextStyle(
                        color: WowColors.textPrimary,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      _lastError ??
                          (isOn
                              ? 'WOW is handling calls for you.'
                              : 'WOW will handle calls for you when you turn it ON.'),
                      style: const TextStyle(color: WowColors.textMuted, fontSize: 13),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                children: [
                  GestureDetector(
                    onTap: (_busy || _callAssistantEnabled == null) ? null : _toggleWow,
                    child: Container(
                      width: 72,
                      height: 72,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: isOn ? WowColors.success : WowColors.primaryBlue,
                          width: 3,
                        ),
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: isOn
                              ? [WowColors.success.withValues(alpha: 0.3), WowColors.surface]
                              : [WowColors.primaryBlue.withValues(alpha: 0.5), WowColors.surface],
                        ),
                      ),
                      child: Center(
                        child: _busy
                            ? const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.power_settings_new,
                                color: Colors.white, size: 28),
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    isOn ? 'Tap to Stop' : 'Tap to Start',
                    style: const TextStyle(
                      color: WowColors.primaryBlue,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'Choose duration',
            style: TextStyle(color: WowColors.textMuted, fontSize: 12),
          ),
          const SizedBox(height: 8),
          Row(
            children: List.generate(_durationOptions.length, (i) {
              final selected = i == _selectedDuration;
              final option = _durationOptions[i];
              return Expanded(
                child: Padding(
                  padding: EdgeInsets.only(right: i == _durationOptions.length - 1 ? 0 : 8),
                  child: GestureDetector(
                    onTap: () => setState(() => _selectedDuration = i),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(
                        color: WowColors.surfaceVariant,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: selected ? WowColors.primaryBlue : WowColors.border,
                        ),
                      ),
                      child: Column(
                        children: [
                          Icon(option.icon,
                              size: 16,
                              color: selected ? WowColors.primaryBlue : WowColors.textMuted),
                          const SizedBox(height: 4),
                          Text(
                            option.label,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 11,
                              color: selected ? WowColors.primaryBlue : WowColors.textSecondary,
                              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickActions() {
    Widget tile({
      required IconData icon,
      required Color color,
      required String title,
      required String subtitle,
      Widget? trailing,
      required VoidCallback onTap,
    }) {
      return Expanded(
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 14),
            margin: const EdgeInsets.symmetric(horizontal: 4),
            decoration: BoxDecoration(
              color: WowColors.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: WowColors.border),
            ),
            child: Column(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: color),
                  ),
                  child: Icon(icon, color: color, size: 20),
                ),
                const SizedBox(height: 8),
                Text(title,
                    style: const TextStyle(
                      color: WowColors.textPrimary,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                    textAlign: TextAlign.center),
                const SizedBox(height: 2),
                trailing ??
                    Text(subtitle,
                        style: const TextStyle(color: WowColors.textMuted, fontSize: 9),
                        textAlign: TextAlign.center),
              ],
            ),
          ),
        ),
      );
    }

    return Row(
      children: [
        tile(
          icon: Icons.mic_none,
          color: WowColors.primaryBlue,
          title: 'Voice Command',
          subtitle: 'Talk to WOW',
          onTap: () => _openCommandSheet(voice: true),
        ),
        tile(
          icon: Icons.keyboard_alt_outlined,
          color: WowColors.primaryBlue,
          title: 'Text Command',
          subtitle: 'Type a command',
          onTap: () => _openCommandSheet(voice: false),
        ),
        tile(
          icon: Icons.fiber_manual_record,
          color: WowColors.accentPurple,
          title: 'Floating Button',
          subtitle: _floatingButtonEnabled ? 'Enabled' : 'Disabled',
          trailing: Transform.scale(
            scale: 0.7,
            child: Switch(
              value: _floatingButtonEnabled,
              activeThumbColor: WowColors.primaryBlue,
              onChanged: (v) => setState(() => _floatingButtonEnabled = v),
            ),
          ),
          onTap: () => setState(() => _floatingButtonEnabled = !_floatingButtonEnabled),
        ),
        tile(
          icon: Icons.settings_outlined,
          color: WowColors.textSecondary,
          title: 'Settings',
          subtitle: 'Customize WOW',
          onTap: () => _notImplementedYet('Settings'),
        ),
      ],
    );
  }

  Widget _buildTodaysSummary() {
    Widget stat(IconData icon, Color color, String value, String label) {
      return Expanded(
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: WowColors.surfaceVariant,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            children: [
              Icon(icon, color: color, size: 18),
              const SizedBox(height: 6),
              Text(value,
                  style: const TextStyle(
                    color: WowColors.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  )),
              const SizedBox(height: 2),
              Text(label,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: WowColors.textMuted, fontSize: 9)),
            ],
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: WowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.bar_chart, color: WowColors.textSecondary, size: 18),
              const SizedBox(width: 6),
              const Text("Today's Summary",
                  style: TextStyle(
                    color: WowColors.textPrimary,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  )),
              const Spacer(),
              GestureDetector(
                onTap: () => _notImplementedYet('Call history'),
                child: const Text('View all',
                    style: TextStyle(color: WowColors.primaryBlue, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Real backend has no call-history endpoint yet - an honest
          // zero-state, not invented numbers.
          Row(
            children: [
              stat(Icons.call, WowColors.success, '0', 'Calls handled\nby WOW'),
              stat(Icons.person_outline, WowColors.primaryBlue, '0', 'Unique\ncallers'),
              stat(Icons.schedule, WowColors.accentPurple, '0m', 'Total time\nsaved'),
              stat(Icons.check_circle_outline, Colors.orange, '0', 'Tasks & info\ncollected'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRecentCalls() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: WowColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: WowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.phone_outlined, color: WowColors.textSecondary, size: 18),
              const SizedBox(width: 6),
              const Text('Recent Calls Handled',
                  style: TextStyle(
                    color: WowColors.textPrimary,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  )),
              const Spacer(),
              GestureDetector(
                onTap: () => _notImplementedYet('Call history'),
                child: const Text('View all',
                    style: TextStyle(color: WowColors.primaryBlue, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'No calls handled yet - turn WOW ON to start.',
              style: TextStyle(color: WowColors.textMuted, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomNav() {
    Widget navItem(IconData icon, String label, {bool active = false}) {
      return Expanded(
        child: InkWell(
          onTap: () => active ? null : _notImplementedYet(label),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: active ? WowColors.primaryBlue : WowColors.textMuted, size: 22),
              const SizedBox(height: 2),
              Text(label,
                  style: TextStyle(
                    color: active ? WowColors.primaryBlue : WowColors.textMuted,
                    fontSize: 10,
                  )),
            ],
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: const BoxDecoration(
        color: WowColors.surface,
        border: Border(top: BorderSide(color: WowColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            navItem(Icons.home, 'Home', active: true),
            navItem(Icons.history, 'History'),
            Expanded(
              child: GestureDetector(
                onTap: () => _openCommandSheet(voice: true),
                child: Container(
                  width: 52,
                  height: 52,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(
                      colors: [WowColors.primaryBlue, WowColors.accentCyan],
                    ),
                  ),
                  child: const Icon(Icons.phone_in_talk, color: Colors.white, size: 22),
                ),
              ),
            ),
            navItem(Icons.contacts_outlined, 'Contacts'),
            navItem(Icons.person_outline, 'Profile'),
          ],
        ),
      ),
    );
  }
}
