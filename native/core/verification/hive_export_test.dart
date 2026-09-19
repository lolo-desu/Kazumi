import 'dart:io';
import 'package:test/test.dart';
import 'package:hive_ce/hive.dart';
import 'package:crypto/crypto.dart';
import 'package:kazumi/hive_registrar.g.dart';
import 'package:kazumi/modules/bangumi/bangumi_item.dart';
import 'package:kazumi/modules/collect/collect_module.dart';
import 'package:kazumi/modules/history/history_module.dart';
import '../bin/hive_export.dart';

void main() {
  test('exports original Hive types without changing source files or leaking tokens', () async {
    final directory=await Directory.systemTemp.createTemp('native-hive-test');
    Hive.init(directory.path);
    Hive.registerAdapters();
    try {
      final subject=BangumiItem(id:42,type:2,name:'original',nameCn:'测试',summary:'summary',
        airDate:'2025-01-01',airWeekday:1,rank:3,images:{},tags:[],alias:[],ratingScore:8,
        votes:1,votesCount:[],info:'');
      final collection=await Hive.openBox<CollectedBangumi>('collectibles');
      await collection.put(42,CollectedBangumi(subject,DateTime.utc(2025),1));
      await collection.close();
      final history=await Hive.openBox<History>('histories');
      final item=History(subject,2,'rule',DateTime.utc(2025),'/show','第2集',episodePageUrl:'https://example.org/2');
      item.progresses[1]=Progress(1,0,1000);
      item.progresses[2]=Progress(2,1,90000);
      await history.put(item.key,item);await history.close();
      final settings=await Hive.openBox('setting');
      await settings.put('bangumiAccessToken','private');await settings.put('themeMode','dark');await settings.close();
      final source=File('${directory.path}/histories.hive');
      final before=sha256.convert(await source.readAsBytes()).toString();
      final result=await exportHive(directory.path);
      expect(sha256.convert(await source.readAsBytes()).toString(),before);
      final boxes=result['boxes'] as Map;
      final exported=(boxes['histories'] as List).single['value'] as Map;
      expect(exported['lastWatchEpisode'],2);
      expect(exported['progresses']['1']['progressMs'],1000);
      expect(exported['progresses']['2']['progressMs'],90000);
      expect(exported['adapterName'],'rule');
      expect((boxes['setting'] as List).single['key'],'themeMode');
      expect(result.toString().contains('private'),isFalse);
      expect((boxes['collectibles'] as List).single['value']['type'],1);
    } finally {
      await Hive.close();
      await directory.delete(recursive:true);
    }
  });
}
