import 'dart:convert';
import 'dart:io';
import 'hive_export.dart';
import 'package:kazumi/plugins/api_rule_config.dart';
import 'package:kazumi/plugins/anti_crawler_config.dart';
import 'package:kazumi/services/plugin/api_rule_strategy.dart';
import 'package:kazumi/services/plugin/xpath_rule_strategy.dart';
import 'package:kazumi/services/plugin/rule_engine_models.dart';

RuleExecutionConfig config(Map<String, dynamic> p) => RuleExecutionConfig(
  pluginName: p['name'] ?? '', baseUrl: p['baseURL'] ?? '',
  usePost: p['usePost'] ?? false,
  searchMode: RuleMode.normalize(p['searchMode']),
  chapterMode: RuleMode.normalize(p['chapterMode']),
  searchUrl: p['searchURL'] ?? '', searchList: p['searchList'] ?? '',
  searchName: p['searchName'] ?? '', searchResult: p['searchResult'] ?? '',
  chapterRoads: p['chapterRoads'] ?? '', chapterResult: p['chapterResult'] ?? '',
  searchApiConfig: ApiSearchConfig.fromJson(p['searchApiConfig'] ?? {}),
  chapterApiConfig: ApiChapterConfig.fromJson(p['chapterApiConfig'] ?? {}),
  antiCrawlerConfig: AntiCrawlerConfig.fromJson(p['antiCrawlerConfig'] ?? {}),
);

Future<Object> dispatch(Map<String, dynamic> call) async {
  if(call['method']=='hive.export') return exportHive(call['directory']);
  final c = config(Map<String, dynamic>.from(call['plugin']));
  const api = ApiRuleStrategy();
  const xpath = XPathRuleStrategy();
  final method = call['method'] as String;
  if (method.endsWith('.prepare')) {
    final search = method == 'search.prepare';
    final isApi = (search ? c.searchMode : c.chapterMode) == RuleMode.api;
    final input = call['input'] as String;
    final request = isApi
      ? api.prepareRequest(search ? c.searchApiConfig.request : c.chapterApiConfig.request,
          {search ? 'keyword' : 'source': input})
      : search ? xpath.prepareSearchRequest(c, input) : xpath.prepareChapterRequest(c, input);
    return {'url': request.url, 'method': request.method, 'headers': request.headers,
      'query': request.query, 'body': request.body, 'bodyType': request.bodyType,
      'includeCookies': request.includeCookies};
  }
  if (method == 'search.parse') {
    final r = c.searchMode == RuleMode.api
      ? api.parseSearch(call['raw'], c.searchApiConfig) : xpath.parseSearch(call['raw'], c);
    return {'items': r.items.map((i) => {'name': i.name, 'src': i.src}).toList(),
      'diagnostics': r.diagnostics};
  }
  if (method == 'chapters.parse') {
    final r = c.chapterMode == RuleMode.api
      ? api.parseChapters(call['raw'], c.chapterApiConfig, source: call['input'], baseUrl: c.baseUrl)
      : xpath.parseChapters(call['raw'], c);
    return {'roads': r.roads.map((r) => {'name': r.name, 'data': r.data,
      'identifier': r.identifier}).toList(), 'diagnostics': r.diagnostics};
  }
  throw FormatException('Unknown method: $method');
}

Future<void> main() async {
  await for (final line in stdin.transform(utf8.decoder).transform(const LineSplitter())) {
    try {
      stdout.writeln(jsonEncode({'result': await dispatch(jsonDecode(line))}));
    } catch (error) {
      stdout.writeln(jsonEncode({'error': error.toString()}));
    }
  }
}
