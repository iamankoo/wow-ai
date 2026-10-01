import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wow_ai/core/api_client.dart';

void main() {
  test('sends X-WOW-API-Key on every request when a key is configured', () async {
    final seen = <String?>[];
    final mock = MockClient((request) async {
      seen.add(request.headers['X-WOW-API-Key']);
      return http.Response('{}', 200);
    });
    final client = WowApiClient(baseUrl: 'http://x', httpClient: mock, apiKey: 'k-123');
    await client.checkHealth();
    await client.getUser('u1');
    expect(seen, ['k-123', 'k-123']);
  });

  test('sends no key header when none is configured (un-keyed local backend)', () async {
    final seen = <String?>[];
    final mock = MockClient((request) async {
      seen.add(request.headers['X-WOW-API-Key']);
      return http.Response('{}', 200);
    });
    final client = WowApiClient(baseUrl: 'http://x', httpClient: mock);
    await client.checkHealth();
    expect(seen, [null]);
  });
}
