use std::cell::RefCell;
use std::env;
use std::process::{Command, Stdio};
use std::rc::Rc;

use glib::MainLoop;
use gstreamer as gst;
use gst::prelude::*;

const SWITCH_SECONDS: u64 = 10;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    gst::init()?;

    let mut args = env::args().skip(1);
    let channel_one = args.next().ok_or("missing first twitch channel")?;
    let channel_two = args.next().ok_or("missing second twitch channel")?;

    let hls_urls = vec![
        resolve_hls_url(&channel_one)?,
        resolve_hls_url(&channel_two)?,
    ];

    let playbin = gst::ElementFactory::make("playbin")
        .build()
        .map_err(|_| "failed to create gstreamer playbin")?;
    playbin.set_property("uri", hls_urls[0].clone());

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

    let playbin = Rc::new(playbin);
    let state = Rc::new(RefCell::new(SwitchState {
        urls: hls_urls,
        index: 0,
        player: playbin.clone(),
    }));

    glib::timeout_add_seconds_local(SWITCH_SECONDS, move || {
        let mut state = state.borrow_mut();
        state.index = (state.index + 1) % state.urls.len();
        let next_url = state.urls[state.index].clone();
        let _ = state.player.set_state(gst::State::Ready);
        state.player.set_property("uri", next_url);
        let _ = state.player.set_state(gst::State::Playing);
        glib::ControlFlow::Continue
    });

    main_loop.run();
    playbin.set_state(gst::State::Null)?;

    Ok(())
}

struct SwitchState {
    urls: Vec<String>,
    index: usize,
    player: Rc<gst::Element>,
}

fn resolve_hls_url(channel: &str) -> Result<String, Box<dyn std::error::Error>> {
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

    Ok(hls_url)
}
