import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:hive_ce/hive.dart';
import 'package:kazumi/hive_registrar.g.dart';
import 'package:kazumi/modules/bangumi/bangumi_item.dart';
import 'package:kazumi/modules/bangumi/bangumi_tag.dart';
import 'package:kazumi/modules/collect/collect_module.dart';
import 'package:kazumi/modules/collect/collect_change_module.dart';
import 'package:kazumi/modules/history/history_module.dart';
import 'package:kazumi/modules/download/download_module.dart';
import 'package:kazumi/modules/search/search_history_module.dart';

final _credential = RegExp(r'token|password|cookie|secret|access.?key|credential',caseSensitive:false);

Object? portable(Object? value) {
  if (value == null || value is String || value is num || value is bool) return value;
  if (value is DateTime) return value.toIso8601String();
  if (value is List) return value.map(portable).toList();
  if (value is Map) return {for (final e in value.entries)
    if (!_credential.hasMatch(e.key.toString())) e.key.toString(): portable(e.value)};
  if (value is BangumiItem) return {'id':value.id,'type':value.type,'name':value.name,
    'name_cn':value.nameCn,'summary':value.summary,'date':value.airDate,'air_weekday':value.airWeekday,
    'images':value.images,'rating':{'rank':value.rank,'score':value.ratingScore,'total':value.votes,'count':value.votesCount},
    'tags':portable(value.tags),'alias':value.alias,'info':value.info};
  if (value is BangumiTag) return {'name':value.name,'count':value.count};
  if (value is CollectedBangumi) return {'subject':portable(value.bangumiItem),'type':value.type,'time':portable(value.time)};
  if (value is CollectedBangumiChange) return {'id':value.id,'bangumiId':value.bangumiID,'action':value.action,'type':value.type,'timestamp':value.timestamp};
  if (value is History) return {'subject':portable(value.bangumiItem),'lastWatchEpisode':value.lastWatchEpisode,
    'adapterName':value.adapterName,'lastWatchTime':portable(value.lastWatchTime),'lastSrc':value.lastSrc,
    'lastWatchEpisodeName':value.lastWatchEpisodeName,'entryKind':value.entryKind,'episodePageUrl':value.episodePageUrl,
    'progresses':portable(value.progresses)};
  if (value is Progress) return {'episode':value.episode,'road':value.road,'progressMs':value.progress.inMilliseconds,'updatedAtMs':value.updatedAtMs};
  if (value is SearchHistory) return {'keyword':value.keyword,'timestamp':value.timestamp};
  if (value is DownloadRecord) return {'bangumiId':value.bangumiId,'bangumiName':value.bangumiName,
    'bangumiCover':value.bangumiCover,'pluginName':value.pluginName,'episodes':portable(value.episodes),'createdAt':portable(value.createdAt)};
  if (value is DownloadEpisode) return {'episodeNumber':value.episodeNumber,'episodeName':value.episodeName,'road':value.road,
    'status':value.status,'progressPercent':value.progressPercent,'totalSegments':value.totalSegments,
    'downloadedSegments':value.downloadedSegments,'localM3u8Path':value.localM3u8Path,'downloadDirectory':value.downloadDirectory,
    'networkM3u8Url':value.networkM3u8Url,'completedAt':portable(value.completedAt),'errorMessage':value.errorMessage,
    'totalBytes':value.totalBytes,'episodePageUrl':value.episodePageUrl,'danmakuData':value.danmakuData,'danDanBangumiID':value.danDanBangumiID};
  throw FormatException('Unsupported Hive value ${value.runtimeType}');
}

Future<Map<String,Object?>> exportHive(String directory) async {
  if (!Hive.isAdapterRegistered(0)) Hive.registerAdapters();
  final boxes=<String,Object?>{};
  final hashes=<String,String>{};
  for (final name in ['favorites','collectibles','histories','setting','collectchanges','shieldList','searchHistory','downloads']) {
    final file=File('$directory/$name.hive');
    if (!await file.exists()) continue;
    final before=await file.stat();
    final bytes=await file.readAsBytes();
    final after=await file.stat();
    if (before.size!=after.size || before.modified!=after.modified) {
      throw StateError('资料库正在变化，请关闭原版 Kazumi 后重试');
    }
    hashes[name]=sha256.convert(bytes).toString();
    // bytes creates an in-memory backend. Never open the user's actual box path.
    final box=await Hive.openBox<dynamic>('native_import_$name',bytes:bytes);
    try {
      boxes[name]=[for(final key in box.keys)
        if (!_credential.hasMatch(key.toString())) {'key':portable(key),'value':portable(box.get(key))}];
    } finally {await box.close();}
  }
  if(boxes.isEmpty) throw FormatException('文件夹中没有可识别的 Kazumi Hive 文件');
  return {'format':'kazumi-hive-snapshot','version':1,'boxes':boxes,'sha256':hashes};
}
