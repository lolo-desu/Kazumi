import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kazumi/utils/gnome_theme.dart';
import 'package:kazumi/utils/gnome_sidebar.dart';

void main() {
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('Other platforms keep their original theme object', () {
    for (final platform in [
      TargetPlatform.android,
      TargetPlatform.iOS,
      TargetPlatform.windows,
      TargetPlatform.macOS
    ]) {
      debugDefaultTargetPlatformOverride = platform;
      final base = ThemeData();
      expect(identical(GnomeTheme.apply(base), base), isTrue);
    }
  });

  test('Custom accent, typography, dark and OLED preferences survive', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    for (final brightness in Brightness.values) {
      final base = ThemeData(
          brightness: brightness,
          colorSchemeSeed: Colors.purple,
          fontFamily: 'UserFont');
      final theme = GnomeTheme.apply(base);
      expect(theme.colorScheme.primary, base.colorScheme.primary);
      expect(theme.brightness, brightness);
      expect(theme.textTheme, base.textTheme);
      expect(theme.colorScheme.surfaceTint, Colors.transparent);
    }
    final oled = ThemeData(brightness: Brightness.dark)
        .copyWith(scaffoldBackgroundColor: Colors.black);
    expect(GnomeTheme.apply(oled).scaffoldBackgroundColor, Colors.black);
  });

  testWidgets('Sidebar keeps destination order, click and keyboard activation',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    final selections = <int>[];
    await tester.pumpWidget(MaterialApp(
        theme: GnomeTheme.apply(ThemeData()),
        home: Scaffold(
            body: GnomeSidebar(
                selectedIndex: 1,
                labels: const ['推荐', '时间表', '追番', '我的'],
                icons: const [
                  Icon(Icons.home),
                  Icon(Icons.timeline),
                  Icon(Icons.favorite),
                  Icon(Icons.settings)
                ],
                onSelected: selections.add))));
    await tester.tap(find.text('追番'));
    expect(selections, [2]);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    expect(selections.length, 2);
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('Small height and large text keep every destination reachable',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    tester.view.resetPhysicalSize();
    tester.view.physicalSize = const Size(640, 240);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        theme: GnomeTheme.apply(ThemeData()),
        home: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(2)),
            child: Scaffold(
                body: GnomeSidebar(
                    selectedIndex: 0,
                    labels: const ['推荐', '时间表', '追番', '我的'],
                    icons: const [
                      Icon(Icons.home),
                      Icon(Icons.timeline),
                      Icon(Icons.favorite),
                      Icon(Icons.settings)
                    ],
                    onSelected: (_) {})))));
    await tester.ensureVisible(find.text('我的'));
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
  });
}
