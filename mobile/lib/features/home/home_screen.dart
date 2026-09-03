import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/floating_button_controller.dart';
import '../../core/wow_theme.dart';
import '../history/history_screen.dart';
import '../profile/profile_screen.dart';
import '../settings/settings_screen.dart';
import 'voice_command_sheet.dart';

class _Duration4Option {
  const _Duration4Option(this.label, this.icon, this.apiValue);
  final String label;
  final IconData icon;
  /// Value POST /users/{id}/activation expects - '15m' | '1h' | '5h' |
  /// 'until_stop'.
  final String apiValue;
}

const _durationOptions = [
  _Duration4Option('15 mins', Icons.access_time, '15m'),
  _Duration4Option('1 hour', Icons.access_time, '1h'),
  _Duration4Option('5 hours', Icons.access_time, '5h'),
  _Duration4Option('Until I stop', Icons.all_inclusive, 'until_stop'),
];

String _formatRemaining(int seconds) {
  final h = seconds ~/ 3600;
  final m = (seconds % 3600) ~/ 60;
  final s = seconds % 60;
  if (h > 0) return '${h}h ${m}m left';
  if (m > 0) return '${m}m ${s}s left';
  return '${s}s left';
}

/// Main WOW AI screen - visually follows assets/main_page.png (the supplied
/// design reference) closely: the ON/OFF call-assistant control, duration
/// picker, quick actions, today's summary and recent-calls sections, and
/// bottom navigation all mirror that layout rather than a generic Flutter
/// template.
///
/// Real backend wiring, not decoration: the ON/OFF state and its remaining
/// duration are read from and written through the real GET /users/{id} and
/// POST /users/{id}/activation endpoints (Phase 6 Part G) - the power
/// button and duration chips call the deterministic activation endpoint
/// directly rather than going through the agent/NLU layer (that remains
/// the path for actual voice/text commands via /brain/command). Expiry is
/// enforced server-side (lazily, on the next real read) so restarting the
/// app can never show a stale "still on" state after a duration has
/// actually elapsed. Today's Summary and Recent Calls Handled show an
/// honest empty state rather than invented numbers, because no
/// call-history endpoint exists yet on the backend.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _user; // full real user row, for Profile/Settings navigation
  bool? _callAssistantEnabled; // null while loading
  int? _activeSecondsRemaining; // null = off, or on with no expiry
  bool _floatingButtonEnabled = true;
  int _selectedDuration = 0;
  bool _busy = false;
  String? _lastError;
  Timer? _countdownTimer;
  Map<String, dynamic>? _todaySummary; // real GET .../calls/today-summary
  List<Map<String, dynamic>>? _recentCalls; // real GET .../calls

  @override
  void initState() {
    super.initState();
    _refreshState();
    _loadCallData();
    FloatingButtonController.resync()
        .then((v) => mounted ? setState(() => _floatingButtonEnabled = v) : null);
    // Ticks the displayed countdown locally between real syncs, and
    // re-syncs with the real backend the moment the local countdown would
    // reach zero - that's when server-side lazy expiry actually needs to
    // run to flip call_assistant_enabled off.
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final remaining = _activeSecondsRemaining;
      if (remaining == null) return;
      if (remaining <= 1) {
        _refreshState();
      } else {
        setState(() => _activeSecondsRemaining = remaining - 1);
      }
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadCallData() async {
    try {
      final summary = await widget.apiClient.getCallsTodaySummary(kDemoUserId);
      final calls = await widget.apiClient.getCalls(kDemoUserId);
      if (mounted) {
        setState(() {
          _todaySummary = summary;
          _recentCalls = calls.take(3).toList();
        });
      }
    } catch (_) {
      // Backend unreachable/error - _lastError already surfaces this via
      // the main card. Resolve to an honest empty state here rather than
      // leaving _recentCalls null forever, which would spin the loading
      // indicator indefinitely.
      if (mounted) {
        setState(() {
          _recentCalls = [];
        });
      }
    }
  }

  void _openHistory() {
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => HistoryScreen(apiClient: widget.apiClient)));
  }

  Future<void> _refreshState() async {
    try {
      final response = await widget.apiClient.getUser(kDemoUserId);
      setState(() {
        _user = response;
        _callAssistantEnabled = response['call_assistant_enabled'] as bool? ?? false;
        _activeSecondsRemaining = response['active_seconds_remaining'] as int?;
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
    final duration = turningOn ? _durationOptions[_selectedDuration].apiValue : 'off';
    setState(() => _busy = true);
    try {
      final response = await widget.apiClient.setActivation(kDemoUserId, duration);
      setState(() {
        _callAssistantEnabled = response['call_assistant_enabled'] as bool? ?? false;
        _activeSecondsRemaining = response['active_seconds_remaining'] as int?;
        _lastError = null;
      });
    } catch (e) {
      setState(() => _lastError = 'Could not reach WOW: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openVoiceCommandSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: WowColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) => VoiceCommandSheet(apiClient: widget.apiClient, userId: kDemoUserId),
    );
  }

  Future<void> _openTextCommandSheet() async {
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
              const Text(
                'Text command',
                style: TextStyle(
                  color: WowColors.textPrimary,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Say something to WOW AI',
                style: TextStyle(color: WowColors.textMuted, fontSize: 13),
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

  Future<void> _setFloatingButtonEnabled(bool value) async {
    final actual = await FloatingButtonController.setEnabled(context, value);
    if (mounted) setState(() => _floatingButtonEnabled = actual);
  }

  void _openSettings() {
    final user = _user;
    if (user == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => SettingsScreen(apiClient: widget.apiClient, user: user)),
    );
  }

  void _openProfile() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ProfileScreen(apiClient: widget.apiClient)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isOn = _callAssistantEnabled == true;
    return Scaffold(
      backgroundColor: WowColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => Future.wait([_refreshState(), _loadCallData()]),
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
              if (isOn && _activeSecondsRemaining != null) ...[
                const SizedBox(width: 8),
                Text(
                  '· ${_formatRemaining(_activeSecondsRemaining!)}',
                  style: const TextStyle(color: WowColors.primaryBlue, fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ],
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
                // Fixed-height slot regardless of whether this tile shows
                // plain subtitle text or a trailing control (the Floating
                // Button tile's Switch) - keeps all four tiles the same
                // height instead of the Switch's native size stretching
                // just that one card taller than its siblings.
                SizedBox(
                  height: 24,
                  child: Center(
                    child: trailing ??
                        Text(subtitle,
                            style: const TextStyle(color: WowColors.textMuted, fontSize: 9),
                            textAlign: TextAlign.center,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis),
                  ),
                ),
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
          title: 'Voice',
          subtitle: 'Talk to WOW',
          onTap: _openVoiceCommandSheet,
        ),
        tile(
          icon: Icons.keyboard_alt_outlined,
          color: WowColors.primaryBlue,
          title: 'Text',
          subtitle: 'Type a command',
          onTap: _openTextCommandSheet,
        ),
        tile(
          icon: Icons.fiber_manual_record,
          color: WowColors.accentPurple,
          title: 'WOW Air',
          subtitle: _floatingButtonEnabled ? 'Enabled' : 'Disabled',
          trailing: SizedBox(
            height: 22,
            child: FittedBox(
              fit: BoxFit.contain,
              child: Switch(
                value: _floatingButtonEnabled,
                activeThumbColor: WowColors.primaryBlue,
                onChanged: _setFloatingButtonEnabled,
              ),
            ),
          ),
          onTap: () => _setFloatingButtonEnabled(!_floatingButtonEnabled),
        ),
        tile(
          icon: Icons.settings_outlined,
          color: WowColors.textSecondary,
          title: 'Settings',
          subtitle: 'Customize WOW',
          onTap: _openSettings,
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
                onTap: _openHistory,
                child: const Text('View all',
                    style: TextStyle(color: WowColors.primaryBlue, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Builder(builder: (context) {
            final summary = _todaySummary;
            final calls = summary?['calls_handled']?.toString() ?? '-';
            final callers = summary?['unique_callers']?.toString() ?? '-';
            final seconds = summary?['total_seconds'] as int? ?? 0;
            final minutes = seconds ~/ 60;
            // Real numbers, computed from the same Call rows - not
            // invented. No "Tasks & info collected" tile: there is no
            // real, distinct backend source for that yet.
            return Row(
              children: [
                stat(Icons.call, WowColors.success, calls, 'Calls handled\nby WOW'),
                stat(Icons.person_outline, WowColors.primaryBlue, callers, 'Unique\ncallers'),
                stat(Icons.schedule, WowColors.accentPurple, '${minutes}m', 'Total time\nlogged'),
              ],
            );
          }),
        ],
      ),
    );
  }

  Widget _buildRecentCalls() {
    final calls = _recentCalls;
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
                onTap: _openHistory,
                child: const Text('View all',
                    style: TextStyle(color: WowColors.primaryBlue, fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (calls == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Center(
                  child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: WowColors.primaryBlue))),
            )
          else if (calls.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'No calls handled yet - turn WOW ON to start.',
                style: TextStyle(color: WowColors.textMuted, fontSize: 12),
              ),
            )
          else
            ...calls.map((call) {
              final name = (call['caller_name'] as String?) ?? call['caller_number'] as String;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Container(width: 6, height: 6, decoration: const BoxDecoration(color: WowColors.success, shape: BoxShape.circle)),
                    const SizedBox(width: 10),
                    Expanded(
                        child: Text(name,
                            style: const TextStyle(color: WowColors.textSecondary, fontSize: 12.5))),
                    Text(call['status'] as String? ?? '',
                        style: const TextStyle(color: WowColors.textMuted, fontSize: 11)),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildBottomNav() {
    Widget navItem(IconData icon, String label, {bool active = false, VoidCallback? onTap}) {
      return Expanded(
        child: InkWell(
          onTap: active ? null : (onTap ?? () => _notImplementedYet(label)),
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
            navItem(Icons.history, 'History', onTap: _openHistory),
            Expanded(
              child: GestureDetector(
                onTap: _openVoiceCommandSheet,
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
            navItem(Icons.person_outline, 'Profile', onTap: _openProfile),
          ],
        ),
      ),
    );
  }
}
