# Kazumi GTK4 原生迁移（未完成）

这是独立的 GTK4/libadwaita 原生前端，不加载 Flutter 引擎。**尚未达到原版全功能等价，不能替代原版。**

## 运行

NixOS：在本仓库中运行 `native/run`。首次使用需要可用的 nixpkgs channel。

Kazumi 首先构建规则核心：

```sh
cd native
nix-shell shell.nix --run ./build-core
./run
```

规则核心在构建时从上游 `lib/` 原样复制 XPath/JSONPath 解析代码；只有 Dart 包导出和测试框架适配，没有另写规则解析算法。独立 Dart 进程通过标准输入/输出 JSON 与 GTK 通信。NixOS 使用 steam-run 运行官方 Dart 生成的 ELF；不要对 AOT ELF 使用 patchelf，否则会破坏 snapshot 尾部定位。

常规 Linux 需要 Python 3.12+、PyGObject、GTK 4.12+、libadwaita 1.5+、WebKitGTK 6.0、libmpv、FFmpeg、libsecret 和 qrencode。安装依赖后运行 `native/run`。GTK 浅色/深色及导航由 libadwaita 渲染，无自制 Material 风格控件。

## 已接入的路径

- 原生自适应侧栏、搜索、详情、设置和文件对话框，系统浅色/深色。
- GNOME 原生“关于”、操作日志和键盘快捷键页面；日志只保留最近 200 条消息，不写入账号凭据。
- 设置中的 HTTP/HTTPS 代理可即时启用或清除，网络请求继续共享同一 Cookie 容器。
- 本地收藏、历史、播放进度、原生资料库 JSON 导入导出。
- 原生弹幕叠加：滚动/顶部/底部弹幕、JSON/XML 导入、字体/透明度/显示区域/偏移/关键词屏蔽。高级 BAS 和弹幕发送尚未迁移。
- 内嵌 Gtk.GLArea + libmpv：播放、暂停、跳转、音量、倍速、全屏、外挂字幕、音轨切换、截图。
- FFmpeg 下载队列、取消、任务状态和离线播放；不支持断点恢复。
- Bangumi 榜单、关键字搜索、放送时间表、详情；KazumiRules 商店、安装更新、JSON 编辑、启用禁用；复用上游 XPath/JSONPath 搜索和分集；WebKit 媒体地址捕获；交互验证后将 Cookie 和浏览器 UA 回传规则请求。
- Bangumi token 登录（系统密钥环保存）、远端收藏拉取及本地变更上传；同步不会覆盖待上传的本地修改。
- 复用原版 Hive adapters，从内存副本读取原版数据；映射收藏/历史，保留逐集进度等旧记录，记录源文件 SHA256，不修改源文件。旧下载文件和所有设置尚未映射。
- Dandan 在线弹幕需设置上游所需的 `DANDANAPI_APPID` 和 `DANDANAPI_KEY`；未配置时可导入本地弹幕。

“已接入”表示有实现路径，不等同于所有账号、源站、区域或硬件组合已经验证。网络错误会显示错误状态，不以空列表伪装成功。

## 尚未迁移或未完整验证

- 真实账号登录/收藏同步的交互验收、WebDAV、Syncplay、完整弹幕功能、投屏、画中画、超分辨率。
- 图片搜索、角色/人员/评论完整详情、评分与评论提交、规则结构化编辑和测试界面。
- 所有旧解析器、自动验证码脚本和反爬规则的完整适配、下载恢复与并行策略。
- 原版 Hive 全部数据到原生功能的映射、原版设置全集、所有导航偏好及使用习惯的逐项对照。

完整的上游页面文件清单见 [feature-inventory.json](feature-inventory.json)。状态只有 partial/pending；没有把未做的项目标记为完成。原 Flutter 数据只在用户选择迁移时读取，源文件不会被修改；原生版使用独立的 `$XDG_DATA_HOME/…-gtk` 目录。

## 验证

- `python3 -m unittest discover -s native/tests -p 'test_*.py'`：存储/协议/规则回归。
- `python3 native/tests/smoke.py`：真实 GTK 窗口、导航、收藏详情、设置弹窗与截图；支持 `NATIVE_TEST_WIDTH=460`、`NATIVE_TEST_DARK=1`。
- `python3 native/tests/player_smoke.py /path/to/640x360-test-video.mp4`：真实 GLArea + libmpv 解码、进度、暂停、跳转；可传第二个 AAC 音频文件参数，验证独立 HTTP 音轨。PiliPlus 测试还覆盖画质切换时的进度与暂停状态。
- `python3 native/tests/webview_smoke.py`：本地 HTTP fixture 验证真实 WebKit 媒体探测及 HttpOnly Cookie 回传。运行环境需要可用的 GStreamer media sink；缺失时只会阻塞该项验证，不影响 GTK 播放器。
- `native/build-core`：上游规则测试和真实 Hive fixture 迁移/源文件哈希不变测试。
- 本机 Wayland 上播放器测试通过。自动化不覆盖账号操作、所有在线播放源及完整易用性验收。

## 实现参考

- [libadwaita NavigationSplitView](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.NavigationSplitView.html)
- [GTK GLArea](https://docs.gtk.org/gtk4/class.GLArea.html)
- [mpv Render API](https://github.com/mpv-player/mpv/blob/master/include/mpv/render.h)

沿用本仓库上游许可证；原始 Dart 文件仍是其权威来源。
