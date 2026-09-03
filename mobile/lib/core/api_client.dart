import 'dart:convert';

import 'package:http/http.dart' as http;

/// Thin client for the WOW AI backend. Talks to the FastAPI service defined
/// in /backend - not to any third-party AI API.
class WowApiClient {
  WowApiClient({required this.baseUrl, http.Client? httpClient})
      : _client = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<bool> checkHealth() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));
    return response.statusCode == 200;
  }

  /// GET /users/{id} - reports the real persisted User row, including
  /// call_assistant_enabled (Phase 2 Block 7's real ANSWER_CALL
  /// authorization flag, also checked by WowAutoAnswer.kt).
  Future<Map<String, dynamic>> getUser(String userId) async {
    final response = await _client.get(Uri.parse('$baseUrl/users/$userId'));
    if (response.statusCode != 200) {
      throw Exception('Get user failed: ${response.statusCode} ${response.body}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> sendBrainCommand({
    required String userId,
    required String text,
    String? conversationId,
    String? callerNumber,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/brain/command'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'user_id': userId,
        'text': text,
        if (conversationId != null) 'conversation_id': conversationId,
        if (callerNumber != null) 'caller_number': callerNumber,
      }),
    );
    if (response.statusCode != 200) {
      throw Exception('Brain command failed: ${response.statusCode} ${response.body}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void dispose() => _client.close();
}
