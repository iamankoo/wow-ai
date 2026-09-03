import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wow_ai/core/update_checker.dart';

/// Phase 6 Part S/T - proves WowUpdateChecker's real comparison logic
/// against a real-shaped GitHub Releases API response (mocked at the HTTP
/// layer, same MockClient technique widget_test.dart already uses for the
/// WOW backend), and against this build's real installed version (mocked
/// at the MainActivity platform-channel layer, since a plain `flutter
/// test` run has no real Android host to ask).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('com.wowai.app/update');

  void mockCurrentVersion(String versionName) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'currentVersion') {
        return {'versionName': versionName, 'versionCode': 1};
      }
      return null;
    });
  }

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  http.Client releaseClient({
    required String tag,
    List<Map<String, String>> assets = const [],
    String body = '',
  }) {
    return MockClient((request) async {
      return http.Response(
        jsonEncode({
          'tag_name': tag,
          'body': body,
          'assets': assets
              .map((a) => {'name': a['name'], 'browser_download_url': a['url']})
              .toList(),
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
  }

  test('a real newer release with an APK asset is reported as an update', () async {
    mockCurrentVersion('1.0.0');
    final client = releaseClient(
      tag: 'v1.2.0',
      assets: [
        {'name': 'wow-ai-release.apk', 'url': 'https://example.com/wow-ai-release.apk'}
      ],
      body: 'Bug fixes and improvements.',
    );

    final update = await WowUpdateChecker.checkForUpdate(client: client);

    expect(update, isNotNull);
    expect(update!.version, '1.2.0');
    expect(update.downloadUrl, 'https://example.com/wow-ai-release.apk');
    expect(update.releaseNotes, 'Bug fixes and improvements.');
  });

  test('the same version as the one installed is not reported as an update', () async {
    mockCurrentVersion('1.0.0');
    final client = releaseClient(
      tag: 'v1.0.0',
      assets: [
        {'name': 'wow-ai-release.apk', 'url': 'https://example.com/wow-ai-release.apk'}
      ],
    );

    final update = await WowUpdateChecker.checkForUpdate(client: client);

    expect(update, isNull);
  });

  test('an older published tag than the installed version is not reported as an update', () async {
    mockCurrentVersion('2.0.0');
    final client = releaseClient(
      tag: 'v1.5.0',
      assets: [
        {'name': 'wow-ai-release.apk', 'url': 'https://example.com/wow-ai-release.apk'}
      ],
    );

    final update = await WowUpdateChecker.checkForUpdate(client: client);

    expect(update, isNull);
  });

  test('a real release with no APK asset attached is not offered as an update', () async {
    mockCurrentVersion('1.0.0');
    final client = releaseClient(tag: 'v1.2.0', assets: const []);

    final update = await WowUpdateChecker.checkForUpdate(client: client);

    expect(update, isNull);
  });
}
