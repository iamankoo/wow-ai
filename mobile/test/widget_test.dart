import 'package:flutter_test/flutter_test.dart';
import 'package:wow_ai/app.dart';
import 'package:wow_ai/core/api_client.dart';

void main() {
  testWidgets('HomeScreen renders backend status and controls', (tester) async {
    await tester.pumpWidget(
      WowAiApp(apiClient: WowApiClient(baseUrl: 'http://localhost:8000')),
    );

    expect(find.text('WOW AI'), findsOneWidget);
    expect(find.text('Check backend connection'), findsOneWidget);
    expect(find.text('Send to brain'), findsOneWidget);
  });
}
