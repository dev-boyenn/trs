use std::env;
use std::process::{Command, Stdio};

use glib::MainLoop;
use gstreamer as gst;
use gst::prelude::*;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    gst::init()?;

    let channel = env::args().nth(1).ok_or("missing twitch channel name")?;
    let stream_url = format!("https://twitch.tv/{channel}");

    let output = Command::new("streamlink")
        .arg("--stream-url")
        .arg(stream_url)
        .arg("best")
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .output()?;

    if !output.status.success() {
        return Err("streamlink failed to resolve stream URL".into());
    }

    let hls_url = String::from_utf8(output.stdout)?.trim().to_string();
    if hls_url.is_empty() {
        return Err("streamlink returned an empty stream URL".into());
    }

    let playbin = gst::ElementFactory::make("playbin")
        .build()
        .map_err(|_| "failed to create gstreamer playbin")?;
    playbin.set_property("uri", hls_url);

    let bus = playbin.bus().ok_or("missing gstreamer bus")?;
    playbin.set_state(gst::State::Playing)?;

    let main_loop = MainLoop::new(None, false);
    let loop_clone = main_loop.clone();

    bus.add_watch(move |_, msg| {
        use gst::MessageView;

        match msg.view() {
            MessageView::Eos(..) => loop_clone.quit(),
            MessageView::Error(err) => {
                eprintln!("gstreamer error: {}", err.error());
                loop_clone.quit();
            }
            _ => {}
        }

        glib::ControlFlow::Continue
    })?;

    main_loop.run();
    playbin.set_state(gst::State::Null)?;

    Ok(())
}
