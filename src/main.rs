use std::env;
use wry::application::event::{Event, WindowEvent};
use wry::application::event_loop::{ControlFlow, EventLoop};
use wry::application::window::WindowBuilder;
use wry::webview::WebViewBuilder;

fn main() -> wry::Result<()> {
    let channel = env::args().nth(1).unwrap_or_else(|| "twitch".to_string());
    let html = format!(
        r#"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
html, body, iframe {{
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}}
</style>
</head>
<body>
<iframe
  src="https://player.twitch.tv/?channel={channel}&parent=localhost&autoplay=true&muted=false&controls=false"
  frameborder="0"
  scrolling="no"
  allow="autoplay; fullscreen"
  allowfullscreen
></iframe>
</body>
</html>"#
    );

    let event_loop = EventLoop::new();
    let window = WindowBuilder::new()
        .with_title("TRS")
        .build(&event_loop)
        .expect("failed to build window");

    let _webview = WebViewBuilder::new(window)?.with_html(&html)?.build()?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        if let Event::WindowEvent {
            event: WindowEvent::CloseRequested,
            ..
        } = event
        {
            *control_flow = ControlFlow::Exit;
        }
    });
}
