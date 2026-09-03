import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/wow_theme.dart';
import 'call_detail_screen.dart';

/// Real call history (Phase 6 Part M) - reads GET /users/{id}/calls,
/// populated only by real calls WOW's real telephony pipeline has
/// actually screened. An empty list here is an honest "no calls yet",
/// never padded with invented rows.
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>>? _calls;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final calls = await widget.apiClient.getCalls(kDemoUserId);
      if (mounted) setState(() => _calls = calls);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load call history: $e');
    }
  }

  String _formatTime(String? iso) {
    if (iso == null) return '';
    final dt = DateTime.tryParse(iso)?.toLocal();
    if (dt == null) return '';
    final now = DateTime.now();
    final isToday = dt.year == now.year && dt.month == now.month && dt.day == now.day;
    final hh = dt.hour.toString().padLeft(2, '0');
    final mm = dt.minute.toString().padLeft(2, '0');
    if (isToday) return '$hh:$mm';
    return '${dt.month}/${dt.day} $hh:$mm';
  }

  @override
  Widget build(BuildContext context) {
    final calls = _calls;
    return Scaffold(
      backgroundColor: WowColors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          color: WowColors.primaryBlue,
          backgroundColor: WowColors.surface,
          child: calls == null
              ? Center(
                  child: _error != null
                      ? Text(_error!, style: const TextStyle(color: WowColors.textMuted))
                      : const CircularProgressIndicator(color: WowColors.primaryBlue),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                  children: [
                    const Text('Call History',
                        style: TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 2),
                    const Text('Calls WOW has screened for you',
                        style: TextStyle(color: WowColors.textMuted, fontSize: 13)),
                    const SizedBox(height: 18),
                    if (calls.isEmpty)
                      const Padding(
                        padding: EdgeInsets.only(top: 40),
                        child: Column(
                          children: [
                            Icon(Icons.phone_disabled_outlined, color: WowColors.textMuted, size: 36),
                            SizedBox(height: 12),
                            Text('No calls handled yet',
                                style: TextStyle(color: WowColors.textSecondary, fontSize: 14)),
                            SizedBox(height: 4),
                            Text('Turn WOW ON to start screening incoming calls.',
                                style: TextStyle(color: WowColors.textMuted, fontSize: 12)),
                          ],
                        ),
                      )
                    else
                      ...calls.map((call) => _CallTile(
                            call: call,
                            timeLabel: _formatTime(call['started_at'] as String?),
                            onTap: () {
                              Navigator.of(context).push(MaterialPageRoute(
                                builder: (_) => CallDetailScreen(
                                  apiClient: widget.apiClient,
                                  callId: call['id'] as String,
                                ),
                              ));
                            },
                          )),
                  ],
                ),
        ),
      ),
    );
  }
}

class _CallTile extends StatelessWidget {
  const _CallTile({required this.call, required this.timeLabel, required this.onTap});

  final Map<String, dynamic> call;
  final String timeLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final name = (call['caller_name'] as String?) ?? call['caller_number'] as String;
    final initial = name.isNotEmpty ? name[0].toUpperCase() : '?';
    final hasSummary = call['has_summary'] == true;
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
              width: 40,
              height: 40,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(colors: [WowColors.primaryBlue, WowColors.accentCyan]),
              ),
              alignment: Alignment.center,
              child: Text(initial, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5)),
                  Text(
                    hasSummary ? 'Screened by WOW' : 'Call logged',
                    style: const TextStyle(color: WowColors.textMuted, fontSize: 11.5),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(timeLabel, style: const TextStyle(color: WowColors.textMuted, fontSize: 11)),
                const SizedBox(height: 4),
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(color: WowColors.success, shape: BoxShape.circle),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
