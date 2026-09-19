"""Build a pure-Dart projection of upstream parsers, without changing their code."""

from pathlib import Path
import hashlib
import json
import shutil
import re

root = Path(__file__).resolve().parent.parent
target = root / "native/core"
sources = [
    "services/plugin/api_rule_strategy.dart",
    "services/plugin/xpath_rule_strategy.dart",
    "services/plugin/rule_engine_models.dart",
    "plugins/api_rule_config.dart",
    "plugins/anti_crawler_config.dart",
    "modules/roads/road_module.dart",
    "modules/search/plugin_search_module.dart",
    "utils/episode_url.dart",
    "hive_registrar.g.dart",
]
manifest = {}
for source in sources:
    if source in manifest:
        continue
    src, dst = root / "lib" / source, target / "lib" / source
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    for dependency in re.findall(
        r"(?:import|export|part)\s+'([^']+)'", src.read_text()
    ):
        if dependency.startswith("package:kazumi/"):
            sources.append(dependency.removeprefix("package:kazumi/"))
        elif not dependency.startswith(("package:", "dart:")):
            sources.append(
                (src.parent / dependency).resolve().relative_to(root / "lib").as_posix()
            )
    manifest[source] = hashlib.sha256(src.read_bytes()).hexdigest()
(target / "upstream-sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
# The upstream barrel exports a Flutter-coupled HTTP orchestrator. This projection
# uses the exact strategy classes, while GTK owns transport and cookie storage.
(target / "lib/services/plugin/api_rule_engine.dart").write_text(
    "export 'api_rule_strategy.dart';\nexport 'rule_engine_models.dart';\n"
)
for name in ["api_rule_engine_test.dart", "episode_url_test.dart"]:
    dst = target / "test" / name
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(
        (root / "test" / name)
        .read_text()
        .replace("package:flutter_test/flutter_test.dart", "package:test/test.dart")
    )
