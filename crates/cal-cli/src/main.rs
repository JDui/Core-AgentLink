use cal_core::{
    client,
    protocol::{Error, VERSION},
    storage::read_json,
    ProcessAdapter, Runtime,
};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    env,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};

fn options(args: &[String]) -> Result<HashMap<String, String>, Error> {
    let mut values = HashMap::new();
    let mut i = 0;
    while i < args.len() {
        let name = &args[i];
        if !name.starts_with("--") || values.contains_key(name) {
            return Err(Error::new(
                "Arguments",
                "Options must be unique --name value pairs",
            ));
        }
        if name == "--dry-run" {
            values.insert(name.clone(), "true".into());
            i += 1;
        } else {
            let value = args
                .get(i + 1)
                .ok_or_else(|| Error::new("Arguments", format!("Missing value for {name}")))?;
            values.insert(name.clone(), value.clone());
            i += 2;
        }
    }
    Ok(values)
}
fn required<'a>(options: &'a HashMap<String, String>, name: &str) -> Result<&'a str, Error> {
    options
        .get(name)
        .map(String::as_str)
        .ok_or_else(|| Error::new("Arguments", format!("Missing {name}")))
}
fn run(command: &str, opts: &HashMap<String, String>) -> Result<Value, Error> {
    let root = Path::new(required(opts, "--state-dir")?);
    let project = required(opts, "--project-id")?;
    if command == "serve" {
        let allowed = ["--state-dir", "--project-id", "--python", "--adapter"];
        if opts.keys().any(|k| !allowed.contains(&k.as_str())) {
            return Err(Error::new("Arguments", "Unknown serve option"));
        }
        let adapter = ProcessAdapter::python(
            Path::new(required(opts, "--python")?),
            Path::new(required(opts, "--adapter")?),
        )?;
        let mut runtime = Runtime::new(root, project, adapter)?;
        let stop = Arc::new(AtomicBool::new(false));
        let signal = stop.clone();
        ctrlc::set_handler(move || {
            signal.store(true, Ordering::Release);
        })
        .map_err(|e| Error::new("SignalError", e.to_string()))?;
        println!(
            "{}",
            json!({"version":VERSION,"ready":true,"sessionId":runtime.session.session_id,
            "projectId":project,"stateDir":runtime.root()})
        );
        let mut last_cleanup = Instant::now();
        while !stop.load(Ordering::Acquire) {
            // Failing the bridge is visible and terminates instead of silently dropping replies.
            runtime.pump()?;
            if last_cleanup.elapsed() >= Duration::from_secs(10) {
                runtime.cleanup_ipc()?;
                last_cleanup = Instant::now();
            }
            thread::sleep(Duration::from_millis(50));
        }
        return Ok(json!({"stopped":true}));
    }
    let common = [
        "--state-dir",
        "--project-id",
        "--session",
        "--timeout",
        "--request-id",
    ];
    let extra: &[&str] = match command {
        "identify" => &["--name"],
        "log" => &["--message", "--percent"],
        "apply" => &["--proposal", "--dry-run"],
        "undo" => &["--run-id"],
        "finish" => &["--summary"],
        "events" => &["--epoch", "--after"],
        "inspect" | "cancel" | "cleanup" => &[],
        _ => return Err(Error::new("Arguments", "Unknown command")),
    };
    if opts
        .keys()
        .any(|k| !common.contains(&k.as_str()) && !extra.contains(&k.as_str()))
    {
        return Err(Error::new("Arguments", "Unknown command option"));
    }
    let session = required(opts, "--session")?
        .parse()
        .map_err(|_| Error::new("Arguments", "Invalid session UUID"))?;
    let timeout: u64 = opts
        .get("--timeout")
        .map(String::as_str)
        .unwrap_or("10")
        .parse()
        .map_err(|_| Error::new("Arguments", "Invalid timeout"))?;
    if !(1..=60).contains(&timeout) {
        return Err(Error::new("Arguments", "Timeout must be 1–60 seconds"));
    }
    let request_id = opts
        .get("--request-id")
        .map(|id| {
            id.parse()
                .map_err(|_| Error::new("Arguments", "Invalid request UUID"))
        })
        .transpose()?;
    let payload = match command {
        "identify" => json!({"name":required(opts,"--name")?}),
        "log" => {
            let mut payload = json!({"message":required(opts,"--message")?});
            if let Some(percent) = opts.get("--percent") {
                payload["percent"] = json!(percent
                    .parse::<u64>()
                    .map_err(|_| Error::new("Arguments", "Invalid percent"))?);
            }
            payload
        }
        "apply" => {
            let mut payload: Value = read_json(&PathBuf::from(required(opts, "--proposal")?))?;
            if !payload.is_object() {
                return Err(Error::new("Arguments", "Proposal must be an object"));
            }
            payload["dryRun"] = json!(opts.contains_key("--dry-run"));
            payload
        }
        "undo" => json!({"runId":required(opts,"--run-id")?}),
        "finish" => json!({"summary":required(opts,"--summary")?}),
        "events" => {
            let mut payload = json!({"after":opts.get("--after").map(String::as_str).unwrap_or("0").parse::<u64>()
                .map_err(|_| Error::new("Arguments", "Invalid cursor"))?});
            if let Some(epoch) = opts.get("--epoch") {
                payload["epoch"] = json!(epoch);
            }
            payload
        }
        _ => json!({}),
    };
    client::request(
        root,
        session,
        project,
        command,
        payload,
        Duration::from_secs(timeout),
        request_id,
    )
}
fn main() {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() || args[0] == "--help" {
        println!("C-AL v1\ncal serve --state-dir DIR --project-id ID --python PYTHON --adapter SCRIPT\ncal COMMAND --state-dir DIR --project-id ID --session UUID [command options]\nCommands: identify, inspect, log, apply, undo, finish, cancel, events, cleanup\nWrites are live-only. Adapter executable is chosen at host startup, never by a request.");
        return;
    }
    let result = options(&args[1..]).and_then(|opts| run(&args[0], &opts));
    match result {
        Ok(result) => println!("{}", json!({"version":VERSION,"ok":true,"result":result})),
        Err(error) => {
            println!("{}", json!({"version":VERSION,"ok":false,"error":error}));
            std::process::exit(1);
        }
    }
}
