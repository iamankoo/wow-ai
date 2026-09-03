import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/wow_theme.dart';

/// One call's real detail (Phase 6 Part M) - transcript is honestly empty
/// for now (Android doesn't let this app capture live call audio yet -
/// see WowCallScreeningService.kt's class doc), so this screen shows that
/// plainly rather than implying a conversation happened.
class CallDetailScreen extends StatefulWidget {
  const CallDetailScreen({super.key, required this.apiClient, required this.callId});

  final WowApiClient apiClient;
  final String callId;

  @override
  State<CallDetailScreen> createState() => _CallDetailScreenState();
}

class _CallDetailScreenState extends State<CallDetailScreen> {
  Map<String, dynamic>? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    widget.apiClient.getCallDetail(widget.callId).then(
          (d) => mounted ? setState(() => _detail = d) : null,
          onError: (e) => mounted ? setState(() => _error = 'Could not load call: $e') : null,
        );
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      backgroundColor: WowColors.background,
      appBar: AppBar(
        backgroundColor: WowColors.background,
        elevation: 0,
        title: const Text('Call details', style: TextStyle(color: Colors.white, fontSize: 17)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: detail == null
            ? Center(
                child: _error != null
                    ? Text(_error!, style: const TextStyle(color: WowColors.textMuted))
                    : const CircularProgressIndicator(color: WowColors.primaryBlue),
              )
            : ListView(
                padding: const EdgeInsets.all(20),
                children: [
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
                        Text(
                          (detail['caller_name'] as String?) ?? detail['caller_number'] as String,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        if (detail['caller_name'] != null)
                          Text(detail['caller_number'] as String,
                              style: const TextStyle(color: WowColors.textMuted, fontSize: 12)),
                        const SizedBox(height: 8),
                        Text(
                          detail['started_at'] as String? ?? '',
                          style: const TextStyle(color: WowColors.textMuted, fontSize: 12),
                        ),
                        const SizedBox(height: 4),
                        Text('Status: ${detail['status']}',
                            style: const TextStyle(color: WowColors.textSecondary, fontSize: 12)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text('Summary',
                      style: TextStyle(color: WowColors.textMuted, fontSize: 12, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: WowColors.surfaceVariant,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      (detail['summary'] as Map<String, dynamic>?)?['summary_text'] as String? ??
                          'No summary available for this call.',
                      style: const TextStyle(color: WowColors.textSecondary, fontSize: 13.5, height: 1.4),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text('Transcript',
                      style: TextStyle(color: WowColors.textMuted, fontSize: 12, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Builder(builder: (context) {
                    final transcript = (detail['transcript'] as List?) ?? [];
                    if (transcript.isEmpty) {
                      return Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: WowColors.surfaceVariant,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: const Text(
                          'No transcript available - WOW cannot capture live phone call audio on this Android setup yet.',
                          style: TextStyle(color: WowColors.textMuted, fontSize: 12.5, height: 1.4),
                        ),
                      );
                    }
                    return Column(
                      children: transcript.map((seg) {
                        final isCaller = seg['speaker'] == 'caller';
                        return Align(
                          alignment: isCaller ? Alignment.centerLeft : Alignment.centerRight,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 8),
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            constraints: const BoxConstraints(maxWidth: 280),
                            decoration: BoxDecoration(
                              color: isCaller ? WowColors.surfaceVariant : WowColors.primaryBlue.withValues(alpha: 0.25),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(seg['text'] as String,
                                style: const TextStyle(color: Colors.white, fontSize: 13)),
                          ),
                        );
                      }).toList(),
                    );
                  }),
                ],
              ),
      ),
    );
  }
}
