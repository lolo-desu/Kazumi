import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kazumi/modules/my/watch_stats.dart';
import 'package:kazumi/pages/my/my_space_view.dart';
import 'package:kazumi/utils/gnome_theme.dart';
import 'package:kazumi/utils/gnome_sidebar.dart';

void main() {
  for (final width in [420.0, 1440.0]) {
    for (final brightness in Brightness.values) {
      testWidgets('Personal center retains all actions at $width $brightness',
          (tester) async {
        debugDefaultTargetPlatformOverride = TargetPlatform.linux;
        tester.view.physicalSize = Size(width, 1000);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final fontPath = Platform.environment['GNOME_TEST_FONT'];
        if (fontPath != null) {
          final loader = FontLoader('ScreenshotFont');
          loader.addFont(Future.value(
              ByteData.sublistView(File(fontPath).readAsBytesSync())));
          await tester.runAsync(loader.load);
        }
        final iconFont = Platform.environment['GNOME_ICON_FONT'];
        if (iconFont != null) {
          final icons = FontLoader('MaterialIcons');
          icons.addFont(Future.value(
              ByteData.sublistView(File(iconFont).readAsBytesSync())));
          await tester.runAsync(icons.load);
        }
        final opened = <MyDestination>[];
        final captureKey = GlobalKey();
        await tester.pumpWidget(MaterialApp(
          theme: GnomeTheme.apply(ThemeData(
              brightness: brightness,
              colorSchemeSeed: const Color(0xff3584e4),
              fontFamily: fontPath == null ? null : 'ScreenshotFont')),
          home: RepaintBoundary(
              key: captureKey,
              child: Scaffold(
                appBar: AppBar(title: const Text('Kazumi')),
                body: Row(children: [
                  if (width > 600)
                    GnomeSidebar(
                        selectedIndex: 3,
                        labels: const ['推荐', '时间表', '追番', '我的'],
                        icons: const [
                          Icon(Icons.home_outlined),
                          Icon(Icons.timeline),
                          Icon(Icons.favorite_border),
                          Icon(Icons.settings_outlined)
                        ],
                        onSelected: (_) {},
                        header: OutlinedButton.icon(
                            onPressed: () {},
                            icon: const Icon(Icons.search),
                            label: const Text('搜索'))),
                  Expanded(
                      child: MySpaceView(
                          stats: const WatchStats(
                              watchedEpisodeCount: 128,
                              watchedBangumiCount: 16,
                              downloadTaskCount: 3),
                          onOpen: opened.add)),
                ]),
              )),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final captureDirectory = Platform.environment['GNOME_CAPTURE_DIR'];
        if (captureDirectory != null) {
          final boundary = captureKey.currentContext!.findRenderObject()!
              as RenderRepaintBoundary;
          await tester.runAsync(() async {
            final image = await boundary.toImage();
            final bytes =
                await image.toByteData(format: ui.ImageByteFormat.png);
            final file = File(
                '$captureDirectory/kazumi-${width.toInt()}-${brightness.name}.png');
            await file.parent.create(recursive: true);
            await file.writeAsBytes(bytes!.buffer.asUint8List());
            image.dispose();
          });
        }
        final labels = width > 600
            ? [
                '外观',
                '播放',
                '弹幕',
                '规则设置',
                '历史记录',
                '离线下载',
                '同步备份',
                '存储管理',
                '关于 Kazumi'
              ]
            : [
                '外观设置',
                '播放设置',
                '弹幕设置',
                '规则设置',
                '历史记录',
                '离线下载',
                '同步备份',
                '存储管理',
                '关于 Kazumi'
              ];
        for (final label in labels) {
          final destination = find.text(label);
          await tester.ensureVisible(destination);
          await tester.tap(destination);
          await tester.pumpAndSettle();
        }
        expect(opened.toSet(), MyDestination.values.toSet());
        expect(opened.length, MyDestination.values.length);
        expect(tester.takeException(), isNull);
        debugDefaultTargetPlatformOverride = null;
      });
    }
  }
}
