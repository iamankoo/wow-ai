import 'package:flutter/material.dart';

import '../../core/api_client.dart';

/// Backend user_id columns are UUID (no real account system exists yet -
/// Phase 1) - this fixed UUID is the Phase 1/2 stand-in for "the current
/// device's user" until real accounts exist. Shared with
/// mobile/android/.../WowCallScreeningService.kt's DEMO_USER_ID so the
/// Flutter UI and the native call-screening path resolve to the same
/// backend user.
const String kDemoUserId = '00000000-0000-0000-0000-000000000001';

/// Minimal Phase 1 screen: confirms connectivity to the WOW AI backend and
/// lets you send a text command to the brain to see the structured action
/// come back. Real call handling / streaming UI lands in Phase 2.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.apiClient});

  final WowApiClient apiClient;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _controller = TextEditingController();
  String _status = 'Unknown';
  String _lastResult = '';

  Future<void> _checkHealth() async {
    try {
      final ok = await widget.apiClient.checkHealth();
      setState(() => _status = ok ? 'Connected' : 'Unreachable');
    } catch (_) {
      setState(() => _status = 'Unreachable');
    }
  }

  Future<void> _sendCommand() async {
    try {
      final result = await widget.apiClient.sendBrainCommand(
        userId: kDemoUserId,
        text: _controller.text,
      );
      setState(() => _lastResult = result.toString());
    } catch (e) {
      setState(() => _lastResult = 'Error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('WOW AI')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Backend status: $_status'),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _checkHealth,
              child: const Text('Check backend connection'),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _controller,
              decoration: const InputDecoration(
                labelText: 'Say something to WOW AI',
              ),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _sendCommand,
              child: const Text('Send to brain'),
            ),
            const SizedBox(height: 16),
            Text(_lastResult),
          ],
        ),
      ),
    );
  }
}
