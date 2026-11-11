"""MineDeck application shell and shared state."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import flet as ft

from core import config
from core.auth import AccountManager, AuthError, offline_account
from core.controls import preset as control_preset
from core.http import human_size
from core.installer import Installer
from core.java import detect_java
from core.launcher import LaunchError, Launcher
from core.modrinth import ModrinthClient
from core.mojang import MojangClient
from core.store import Store

from ui.components import account_avatar, account_chip, logo, nav_item, wordmark
from ui.theme import BG, BODY, DIM, HEAD, LINE, MUTED, OK, SURFACE, SURFACE_2, TEXT, WARNING, Palette, divider, rgba

NAV_ITEMS = [
    ("home", "Home", "home_rounded"),
    ("versions", "Versions", "grid_view_rounded"),
    ("mods", "Mods", "extension_rounded"),
    ("packs", "Resource packs", "palette_rounded"),
    ("installed", "Installed", "inventory_2_rounded"),
    ("controls", "Touch controls", "sports_esports_rounded"),
    ("settings", "Settings", "tune_rounded"),
]

MOBILE_ITEMS = [
    ("home", "Home", "home_rounded"),
    ("versions", "Versions", "grid_view_rounded"),
    ("mods", "Content", "extension_rounded"),
    ("installed", "Installed", "inventory_2_rounded"),
    ("settings", "Settings", "tune_rounded"),
]


class MineDeckApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.store = Store()
        self.palette = Palette.from_store(self.store)
        self.mojang = MojangClient(self.store)
        self.accounts = AccountManager(self.store)
        self.launcher = Launcher(self.store, self.mojang, self.accounts)
        self.installer = Installer(self.store, self.mojang)
        self.modrinth = ModrinthClient()
        self.versions = []
        self.versions_loading = False
        self.versions_error = ""
        self._version_waiters: list = []
        self.session = None
        self.is_mobile = True
        self.route = "home"
        self.views: dict = {}
        self.content_host: ft.AnimatedSwitcher | None = None
        self.nav_host: ft.Container | None = None
        self.rail_host: ft.Container | None = None
        self.url_launcher = ft.UrlLauncher()
        self.clipboard = ft.Clipboard()
        page.services.append(self.url_launcher)
        page.services.append(self.clipboard)

        self.palette.apply(page)
        page.title = "MineDeck — Minecraft Java Launcher"
        page.on_resize = self._on_resize
        page.on_error = lambda e: self.toast(f"UI error: {getattr(e, 'data', e)}", error=True)

        width = page.width or 390
        self.is_mobile = width < 820
        self._build_shell()
        self.navigate("home")
        self.ensure_versions()

    # ---------------------------------------------------------------- layout
    def _build_shell(self) -> None:
        self.content_host = ft.AnimatedSwitcher(
            content=ft.Container(expand=True),
            duration=220,
            transition=ft.AnimatedSwitcherTransition.FADE,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
            switch_out_curve=ft.AnimationCurve.EASE_IN,
            expand=True,
        )
        self.nav_host = ft.Container(content=self._bottom_nav(), bgcolor="#090B11F2")
        if self.is_mobile:
            body = ft.Column(
                [
                    self._topbar(),
                    ft.Container(content=self.content_host, expand=True),
                    self.nav_host,
                ],
                spacing=0,
                expand=True,
            )
        else:
            body = ft.Row(
                [
                    self._rail(),
                    ft.Container(content=self.content_host, expand=True, bgcolor=BG),
                ],
                spacing=0,
                expand=True,
            )
        self.page.clean()
        self.page.add(ft.Container(content=ft.SafeArea(content=body, expand=True), bgcolor=BG, expand=True))
        self.page.update()

    def _on_resize(self, event: ft.PageResizeEvent) -> None:
        mobile = event.width < 820
        if mobile != self.is_mobile:
            self.is_mobile = mobile
            self._build_shell()
            self._render_current()

    def _topbar(self) -> ft.Control:
        return ft.Container(
            height=66,
            padding=ft.Padding.only(left=16, right=12, top=8, bottom=8),
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Row([logo(34), wordmark(self.palette)], spacing=10, tight=True),
                        on_click=lambda e: self.navigate("home"),
                    ),
                    ft.Container(expand=True),
                    account_chip(self.palette, self.accounts.account, lambda e: self.open_account()),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _rail(self) -> ft.Control:
        nav_column = ft.Column(spacing=4)
        for route, label, icon in NAV_ITEMS:
            nav_column.controls.append(
                nav_item(
                    self.palette,
                    icon,
                    label,
                    self._is_selected(route),
                    lambda e, r=route: self.navigate(r),
                )
            )
        usage = self._disk_summary()
        self.rail_host = ft.Container(
            width=242,
            bgcolor="#0A0C12",
            border=ft.Border.only(right=ft.BorderSide(1, LINE)),
            padding=ft.Padding.only(left=16, right=16, top=20, bottom=18),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row([logo(40), wordmark(self.palette)], spacing=12, tight=True),
                        on_click=lambda e: self.navigate("home"),
                        padding=ft.Padding.only(bottom=18),
                    ),
                    ft.Container(content=nav_column, expand=True),
                    ft.Container(
                        content=ft.Column(
                            [
                                account_chip(self.palette, self.accounts.account, lambda e: self.open_account()),
                                ft.Container(height=6),
                                ft.Row(
                                    [
                                        ft.Icon("storage_rounded", size=13, color=DIM),
                                        ft.Text(usage, size=9, color=DIM, font_family=BODY),
                                    ],
                                    spacing=5,
                                ),
                                ft.Text(f"v{config.APP_VERSION} · Flet", size=8, color="#3D4556", font_family=BODY),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                        bgcolor="#11141D",
                        border=ft.Border.all(1, LINE),
                        border_radius=16,
                        padding=12,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
        )
        return self.rail_host

    def _bottom_nav(self) -> ft.Control:
        items = []
        for route, label, icon in MOBILE_ITEMS:
            active = self._is_selected(route)
            items.append(
                ft.Container(
                    expand=True,
                    height=58,
                    border_radius=15,
                    on_click=lambda e, r=route: self.navigate(r),
                    content=ft.Column(
                        [
                            ft.Icon(icon, size=21, color=self.palette.accent if active else "#6B7487"),
                            ft.Text(
                                label,
                                size=9,
                                color=self.palette.accent if active else "#6B7487",
                                weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                                font_family=BODY,
                            ),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
        return ft.Container(
            border=ft.Border.only(top=ft.BorderSide(1, LINE)),
            padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
            content=ft.Row(items, spacing=0),
        )

    def _is_selected(self, route: str) -> bool:
        if route == "mods":
            return self.route in ("mods", "packs", "shaders")
        if route == "packs":
            return self.route == "packs"
        return self.route == route

    def _disk_summary(self) -> str:
        try:
            usage = self.mojang.disk_usage()
            return f"{usage['human']} used"
        except Exception:
            return "No game files"

    # -------------------------------------------------------------- navigation
    def navigate(self, route: str) -> None:
        self.route = route
        if route == "mods" and "content" in self.views:
            self.views["content"].tab = "mod"
        if route == "packs" and "content" in self.views:
            self.views["content"].tab = "resourcepack"
        self._render_current()
        if route in ("mods", "packs", "shaders"):
            self.ensure_versions()

    def _render_current(self) -> None:
        view = self._get_view(self.route)
        self.content_host.content = view
        self.content_host.update()
        self.nav_host.content = self._bottom_nav()
        try:
            self.nav_host.update()
        except Exception:
            pass
        if not self.is_mobile and self.rail_host is not None:
            try:
                self.rail_host.update()
            except Exception:
                pass

    def _get_view(self, route: str) -> ft.Control:
        from ui.pages.content import ContentView
        from ui.pages.controls import ControlsView
        from ui.pages.home import build_home
        from ui.pages.installed import build_installed
        from ui.pages.settings import build_settings
        from ui.pages.versions import VersionsView

        if route == "home":
            return build_home(self)
        if route == "versions":
            if "versions" not in self.views:
                self.views["versions"] = VersionsView(self)
            return self.views["versions"].build()
        if route in ("mods", "packs", "shaders"):
            if "content" not in self.views:
                self.views["content"] = ContentView(self)
            self.views["content"].tab = {"mods": "mod", "packs": "resourcepack", "shaders": "shader"}[route]
            return self.views["content"].build()
        if route == "installed":
            return build_installed(self)
        if route == "controls":
            if "controls" not in self.views:
                self.views["controls"] = ControlsView(self)
            return self.views["controls"].build()
        if route == "settings":
            return build_settings(self)
        return build_home(self)

    def rebuild(self) -> None:
        self._render_current()

    # ------------------------------------------------------------------ data
    def ensure_versions(self, waiter=None) -> None:
        if waiter:
            self._version_waiters.append(waiter)
        if self.versions:
            if waiter:
                waiter(self.versions, "")
            return
        if self.versions_loading:
            return
        self.versions_loading = True

        def work():
            return self.mojang.manifest()

        def done(result):
            self.versions = result
            self.versions_loading = False
            self.versions_error = ""
            waiters, self._version_waiters = self._version_waiters, []
            for item in waiters:
                try:
                    item(result, "")
                except Exception:
                    pass
            if "versions" in self.views:
                self.views["versions"].on_manifest(result)

        def fail(exc):
            self.versions_loading = False
            self.versions_error = str(exc)
            waiters, self._version_waiters = self._version_waiters, []
            for item in waiters:
                try:
                    item([], str(exc))
                except Exception:
                    pass
            self.toast(f"Could not load versions: {exc}", error=True)

        self.run_worker(work, done, fail)

    def latest_release(self) -> str:
        if self.versions:
            manifest = getattr(self.mojang, "_manifest", {}) or {}
            return (manifest.get("latest") or {}).get("release", self.versions[0].id)
        return "—"

    def installed_count(self) -> int:
        return len(self.store.instances)

    def java_summary(self) -> tuple[str, str]:
        java = detect_java(self.store.get("java_path", ""))
        if not java:
            return "Missing", WARNING
        return f"Java {java.major}" if java.major else "Ready", OK

    def disk_human(self) -> str:
        try:
            return self.mojang.disk_usage()["human"]
        except Exception:
            return "0 B"

    def active_instance(self) -> dict | None:
        last = self.store.get("last_instance", "")
        instance = self.store.get_instance(last) if last else None
        if instance:
            return instance
        items = self.store.sorted_instances()
        return items[0] if items else None

    # --------------------------------------------------------------- workers
    def run_worker(self, work, on_done=None, on_error=None) -> None:
        def runner():
            try:
                result = work()
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__

                def fail():
                    if on_error:
                        on_error(exc)
                    else:
                        self.toast(message, error=True)

                try:
                    self.page.run_thread(fail)
                except Exception:
                    pass
                return
            if on_done:
                try:
                    self.page.run_thread(lambda: on_done(result))
                except Exception:
                    on_done(result)

        self.page.run_thread(runner)

    # ------------------------------------------------------------------- dialogs
    def toast(self, message: str, *, error: bool = False, success: bool = False) -> None:
        color = "#FEE2E2" if error else ("#DCFCE7" if success else TEXT)
        bg = "#3A1215" if error else ("#0E2A19" if success else SURFACE_2)
        dialog = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(
                        "error_outline_rounded" if error else ("check_circle_outline_rounded" if success else "info_outline_rounded"),
                        size=18,
                        color=("#F87171" if error else (OK if success else self.palette.accent)),
                    ),
                    ft.Text(message, size=12, color=color, font_family=BODY, max_lines=3),
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=bg,
            open=True,
            duration=4200,
        )
        try:
            self.page.show_dialog(dialog)
        except Exception:
            pass

    def open_url(self, url: str) -> None:
        try:
            self.page.run_task(self.url_launcher.launch_url, url)
        except Exception:
            self.toast(f"Open this link: {url}")

    def copy(self, value: str) -> None:
        try:
            self.page.run_task(self.clipboard.set, value)
            self.toast("Copied to clipboard", success=True)
        except Exception:
            self.toast(f"Copy manually: {value}")

    def close_dialog(self) -> None:
        try:
            self.page.pop_dialog()
        except Exception:
            pass

    def confirm(self, title: str, message: str, on_confirm, *, confirm_label: str = "Delete", danger: bool = True) -> None:
        def run(e=None):
            self.close_dialog()
            on_confirm()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=24),
            title=ft.Text(title, font_family=HEAD, size=18, color=TEXT),
            content=ft.Container(
                width=380,
                content=ft.Text(message, size=13, color=MUTED, font_family=BODY),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog()),
                ft.FilledButton(
                    confirm_label,
                    on_click=run,
                    style=ft.ButtonStyle(
                        bgcolor="#F87171" if danger else self.palette.accent,
                        color="#1A0505" if danger else "#04120A",
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                ),
            ],
            open=True,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ account
    def open_account(self) -> None:
        from ui.login import account_dialog

        account_dialog(self)

    def sign_in_local(self) -> None:
        field = ft.TextField(
            label="Username",
            hint_text="3–16 letters, numbers or underscore",
            value=(self.accounts.account or {}).get("name", ""),
            autofocus=True,
            bgcolor="#0B0E15",
            border_color="#FFFFFF18",
            focused_border_color=self.palette.accent,
            border_radius=12,
            text_size=13,
            content_padding=14,
        )
        error = ft.Text("", size=11, color="#F87171")

        def submit(e=None):
            try:
                account = offline_account(field.value, self.store)
            except AuthError as exc:
                error.value = str(exc)
                error.update()
                return
            self.close_dialog()
            self.toast(f"Playing as {account['name']}", success=True)
            self._refresh_after_account()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=24),
            title=ft.Text("Local profile", font_family=HEAD, size=19, color=TEXT),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    [
                        ft.Text(
                            "An offline profile launches without contacting Microsoft. "
                            "Use it for a game you own, LAN worlds or mod testing.",
                            size=12,
                            color=MUTED,
                            font_family=BODY,
                        ),
                        field,
                        error,
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog()),
                ft.FilledButton(
                    "Use local profile",
                    on_click=submit,
                    style=ft.ButtonStyle(bgcolor=self.palette.accent, color="#04120A", shape=ft.RoundedRectangleBorder(radius=12)),
                ),
            ],
            open=True,
        )
        self.page.show_dialog(dialog)

    def _refresh_after_account(self) -> None:
        self._build_shell()
        self._render_current()

    def sign_out(self) -> None:
        self.accounts.logout()
        self.close_dialog()
        self.toast("Signed out")
        self._refresh_after_account()

    # ------------------------------------------------------------------ launch
    def launch(self, instance: dict) -> None:
        if self.session and self.session.running:
            self.show_session(instance)
            return
        status = ft.Text("Checking Java, account and game files…", size=12, color=MUTED, font_family=BODY)
        ring = ft.ProgressRing(width=18, height=18, stroke_width=2, color=self.palette.accent)
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=24),
            title=ft.Text(f"Launching {instance.get('name', 'Minecraft')}", font_family=HEAD, size=18, color=TEXT),
            content=ft.Container(
                width=400,
                content=ft.Column(
                    [
                        ft.Row([ring, ft.Text(f"Minecraft {instance.get('mc_version')}", size=12, color=TEXT, font_family=BODY)], spacing=10),
                        status,
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            open=True,
        )
        self.page.show_dialog(dialog)

        def work():
            readiness = self.launcher.readiness(instance)
            if not readiness["ready"]:
                return {"ok": False, "readiness": readiness}
            session = self.launcher.start(instance)
            time.sleep(1.2)
            alive = session.running
            return {"ok": alive, "session": session, "log": session.tail(8), "exit": session.exit_code}

        def done(result):
            self.close_dialog()
            if not result["ok"]:
                self._launch_problem(instance, result)
                return
            self.session = result["session"]
            self.store.update_settings(last_instance=instance["id"])
            self.toast("Minecraft launched — check the game window", success=True)
            if self.route in ("home", "installed"):
                self._render_current()

        def fail(exc):
            self.close_dialog()
            if isinstance(exc, LaunchError):
                self._launch_problem(instance, {"ok": False, "error": str(exc)})
            else:
                self.toast(str(exc), error=True)

        self.run_worker(work, done, fail)

    def _launch_problem(self, instance: dict, result: dict) -> None:
        issues = result.get("readiness", {}).get("issues", [])
        if result.get("error"):
            issues = [result["error"]] + issues
        log = result.get("log") or []
        lines = [ft.Text(f"• {issue}", size=12, color="#FCA5A5" if index == 0 else MUTED, font_family=BODY) for index, issue in enumerate(issues)]
        content = [
            ft.Text("This launch was blocked. MineDeck does not simulate a launch when the runtime is missing.", size=12, color=MUTED, font_family=BODY),
            ft.Column(lines, spacing=5, tight=True),
        ]
        if log:
            content.append(
                ft.Container(
                    bgcolor="#0A0C12",
                    border_radius=12,
                    padding=10,
                    content=ft.Column([ft.Text(line, size=10, color="#8FA0B8", font_family="monospace") for line in log[-8:]], spacing=1, tight=True),
                )
            )
        android = config.is_android()
        actions = []
        if not android:
            actions.append(ft.TextButton("Settings", on_click=lambda e: (self.close_dialog(), self.navigate("settings"))))
        actions.append(ft.TextButton("Close", on_click=lambda e: self.close_dialog()))
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=24),
            title=ft.Row(
                [
                    ft.Container(
                        width=36,
                        height=36,
                        border_radius=12,
                        bgcolor="#F8717118",
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon("warning_amber_rounded", size=20, color="#F87171"),
                    ),
                    ft.Text("Launch blocked", font_family=HEAD, size=18, color=TEXT),
                ],
                spacing=10,
            ),
            content=ft.Container(
                width=440,
                content=ft.Column(content, spacing=12, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=actions,
            open=True,
        )
        self.page.show_dialog(dialog)

    def show_session(self, instance: dict) -> None:
        if not self.session:
            return
        logs = self.session.tail(120)
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_2,
            shape=ft.RoundedRectangleBorder(radius=24),
            title=ft.Row(
                [
                    ft.Container(width=8, height=8, border_radius=99, bgcolor=OK if self.session.running else "#F87171"),
                    ft.Text("Minecraft is running" if self.session.running else "Minecraft exited", font_family=HEAD, size=17, color=TEXT),
                ],
                spacing=10,
            ),
            content=ft.Container(
                width=620,
                height=360,
                content=ft.Column(
                    [ft.Text(line, size=10, color="#8FA0B8", font_family="monospace", selectable=True) for line in logs],
                    scroll=ft.ScrollMode.AUTO,
                    spacing=0,
                ),
            ),
            actions=[
                ft.TextButton("Open folder", on_click=lambda e: self.toast(instance.get("path", ""))),
                ft.TextButton("Stop", on_click=lambda e: (self.session.terminate(), self.close_dialog())),
                ft.TextButton("Close", on_click=lambda e: self.close_dialog()),
            ],
            open=True,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ control
    def current_layout(self) -> dict:
        name = self.store.get("controls_preset", "classic")
        saved = self.store.get_control_layout(name)
        return saved or control_preset(name)


def main(page: ft.Page) -> None:
    MineDeckApp(page)


if __name__ == "__main__":
    if os.environ.get("FLET_PLATFORM"):
        # Native Android/iOS build: let the embedded Flutter host render the app.
        ft.run(main, assets_dir="assets")
    else:
        ft.run(
            main,
            view=ft.AppView.WEB_BROWSER,
            host="0.0.0.0",
            port=int(os.environ.get("MINEDECK_PORT", "8550")),
            assets_dir="assets",
        )
