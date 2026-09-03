import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'update_bridge.dart';

class WowUpdateInfo {
  const WowUpdateInfo({
    required this.version,
    required this.downloadUrl,
    required this.releaseNotes,
  });

  final String version;
  final String downloadUrl;
  final String releaseNotes;
}

/// Real GitHub-Release-based update checker (Phase 6 Part S/T) - talks to
/// the real GitHub REST API for this actual repository, never a made-up or
/// self-hosted update server. No API token used or needed: this only reads
/// a public repo's public releases.
class WowUpdateChecker {
  static const _releasesUrl = 'https://api.github.com/repos/iamankoo/wow-ai/releases/latest';

  /// Returns real info about a newer release if one exists, or null if
  /// this installed build is already current (or newer than what's
  /// published, e.g. a dev build) - never fabricates an update. [client]
  /// is injectable (defaults to a real http.Client) so tests can supply a
  /// MockClient instead of hitting the real GitHub API.
  static Future<WowUpdateInfo?> checkForUpdate({http.Client? client}) async {
    final httpClient = client ?? http.Client();
    final response = await httpClient.get(
      Uri.parse(_releasesUrl),
      headers: {'Accept': 'application/vnd.github+json'},
    );
    if (response.statusCode != 200) {
      throw StateError('GitHub releases check failed: HTTP ${response.statusCode}');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final tag = (body['tag_name'] as String? ?? '').trim();
    final latestVersion = tag.startsWith('v') ? tag.substring(1) : tag;
    if (latestVersion.isEmpty) return null;

    final assets = (body['assets'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final apkAsset = assets.firstWhere(
      (a) => (a['name'] as String? ?? '').toLowerCase().endsWith('.apk'),
      orElse: () => const {},
    );
    final downloadUrl = apkAsset['browser_download_url'] as String?;
    if (downloadUrl == null) return null; // a real release with no APK attached - nothing to offer

    final (currentVersion, _) = await WowUpdateBridge.currentVersion();
    if (!_isNewer(latestVersion, currentVersion)) return null;

    return WowUpdateInfo(
      version: latestVersion,
      downloadUrl: downloadUrl,
      releaseNotes: (body['body'] as String? ?? '').trim(),
    );
  }

  static bool _isNewer(String candidate, String current) {
    final c = _parts(candidate);
    final r = _parts(current);
    for (var i = 0; i < 3; i++) {
      if (c[i] != r[i]) return c[i] > r[i];
    }
    return false;
  }

  static List<int> _parts(String version) {
    final segments = version.split('.');
    return List.generate(3, (i) {
      if (i >= segments.length) return 0;
      return int.tryParse(segments[i].replaceAll(RegExp(r'[^0-9]'), '')) ?? 0;
    });
  }

  /// Downloads [url] to the real native updates directory, reporting
  /// progress via [onProgress] (0.0-1.0, or never called if content-length
  /// is unknown), and returns the real local file path.
  static Future<String> downloadApk(
    String url, {
    void Function(double)? onProgress,
    http.Client? client,
  }) async {
    final dir = await WowUpdateBridge.downloadsDir();
    final path = '$dir/wow-ai-update.apk';
    final file = File(path);

    final request = http.Request('GET', Uri.parse(url));
    final response = await (client ?? http.Client()).send(request);
    if (response.statusCode != 200) {
      throw StateError('Download failed: HTTP ${response.statusCode}');
    }

    final total = response.contentLength;
    var received = 0;
    final sink = file.openWrite();
    await response.stream.map((chunk) {
      received += chunk.length;
      if (total != null && total > 0) onProgress?.call(received / total);
      return chunk;
    }).pipe(sink);

    return path;
  }
}
