use std::env;
use std::process::{Command, Stdio};

fn main() -> Result<(), Box<dyn std::error::Error>> {
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

    let status = Command::new("mpv")
        .arg(hls_url)
        .status()?;

    if !status.success() {
        return Err("mpv failed to play stream".into());
    }

    Ok(())
}
