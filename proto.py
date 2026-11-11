import flet as ft

def main(page: ft.Page):
    page.bgcolor = "#07080C"
    page.padding = 0
    page.fonts = {"Sora": "fonts/Sora.ttf", "Inter": "fonts/Inter.ttf"}
    page.add(
        ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("MineDeck", font_family="Sora", size=40, weight=ft.FontWeight.BOLD, color="#F6F8FC"),
                ft.Text("Inter body text — The quick brown fox", font_family="Inter", size=16, color="#98A2B3"),
                ft.Image(src="art/hero.png", height=260, fit=ft.BoxFit.COVER, border_radius=24),
                ft.Image(src="art/icon.png", width=80, height=80),
                ft.Container(width=200, height=50, border_radius=14, gradient=ft.LinearGradient(colors=["#4ADE80", "#22C55E"]), alignment=ft.Alignment.CENTER, content=ft.Text("Play", color="#06130A", weight=ft.FontWeight.BOLD)),
            ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
        )
    )

ft.run(main, view=ft.AppView.WEB_BROWSER, port=8550, assets_dir="assets")
