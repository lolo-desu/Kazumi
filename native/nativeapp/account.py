from gi.repository import Adw, Gtk, Gio


def show_account(window):
    dialog = Adw.PreferencesDialog(title="Bangumi 账号")
    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup(
        title="账号",
        description="使用 Bangumi 个人访问令牌登录。令牌保存在系统密钥环中，不进入备份。",
    )
    account = window.store.get("bangumi_account", {})
    identity = Adw.ActionRow(
        title=account.get("nickname") or "未登录",
        subtitle=account.get("username", ""),
        use_markup=False,
    )
    group.add(identity)
    token = Adw.PasswordEntryRow(title="个人访问令牌")
    group.add(token)
    actions = Gtk.Box(spacing=8, margin_top=12)
    login = Gtk.Button(label="验证并登录")
    login.add_css_class("suggested-action")

    def submit(*_):
        value = token.get_text().strip()
        if not value:
            return
        login.set_sensitive(False)

        def done(account):
            token.set_text("")
            identity.set_title(account.get("nickname") or account["username"])
            identity.set_subtitle(account["username"])
            login.set_sensitive(True)
            window.message("已登录 Bangumi")

        window.async_call(
            lambda: window.service.login(value),
            done,
            lambda e: (login.set_sensitive(True), window.message(e)),
            scoped=False,
        )

    login.connect("clicked", submit)
    actions.append(login)
    token_link = Gtk.Button(label="创建令牌")
    token_link.connect(
        "clicked",
        lambda *_: Gio.AppInfo.launch_default_for_uri(
            "https://next.bgm.tv/demo/access-token", None
        ),
    )
    actions.append(token_link)
    logout = Gtk.Button(label="退出本机账号")
    logout.connect(
        "clicked",
        lambda *_: window.async_call(
            window.service.logout,
            lambda _: (
                identity.set_title("未登录"),
                identity.set_subtitle(""),
                window.message("已退出"),
            ),
            scoped=False,
        ),
    )
    actions.append(logout)
    group.add(actions)
    page.add(group)
    sync = Adw.PreferencesGroup(
        title="收藏同步",
        description="拉取会保留本地待上传的修改；上传只处理本地修改，不覆盖其他远端条目。",
    )
    for title, callback in [
        ("拉取远端收藏", window.service.pull_collections),
        ("上传本地收藏修改", window.service.push_collections),
    ]:
        row = Adw.ActionRow(title=title, activatable=True, use_markup=False)

        def run(_, callback=callback, row=row):
            row.set_sensitive(False)
            window.async_call(
                callback,
                lambda count: (
                    row.set_sensitive(True),
                    window.message(f"已同步 {count} 条收藏"),
                ),
                lambda e: (row.set_sensitive(True), window.message(e)),
                scoped=False,
            )

        row.connect("activated", run)
        sync.add(row)
    page.add(sync)
    dialog.add(page)
    dialog.present(window)
