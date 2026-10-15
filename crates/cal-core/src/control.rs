//! Independent cooperative termination channel; never kills an external process.
use crate::{
    protocol::{fields, now_ms, Error, Request, Response, Session, VERSION},
    storage::{atomic_json, managed_packet, packet_name, read_json, regular},
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    sync::{Arc, Mutex},
};
use uuid::Uuid;

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AgentControl {
    pub version: u32,
    pub session_id: Uuid,
    pub project_id: String,
    pub request_id: Uuid,
    pub directive: String,
    pub status: String,
    pub reason: String,
    pub requested_at_ms: u64,
    pub acknowledged_at_ms: Option<u64>,
}

#[derive(Default)]
pub struct ControlState {
    pub signal: Option<AgentControl>,
    pub finished: bool,
}
pub type SharedControl = Arc<Mutex<ControlState>>;

pub fn handle(
    root: &Path,
    session: &Session,
    state: &SharedControl,
    req: &Request,
) -> Result<Value, Error> {
    if req.version != VERSION {
        return Err(Error::new("ProtocolVersion", "Unsupported request version"));
    }
    if req.session_id != session.session_id || req.project_id != session.project_id {
        return Err(Error::new(
            "StaleSession",
            "Control targets an old or different session/project",
        ));
    }
    if req.token != session.token {
        return Err(Error::new(
            "InvalidCredential",
            "Invalid control credential",
        ));
    }
    let current: Session = read_json(&root.join("session.json"))?;
    if current.session_id != session.session_id || current.token != session.token {
        return Err(Error::new("StaleSession", "Session ownership was lost"));
    }
    let mut control = state.lock().unwrap();
    match req.command.as_str() {
        "control" => {
            fields(&req.payload, &[])?;
            Ok(serde_json::to_value(&control.signal)?)
        }
        "stop-agent" => {
            fields(&req.payload, &["reason"])?;
            let reason = match req.payload.get("reason") {
                None => "User requested agent termination".to_string(),
                Some(Value::String(reason))
                    if !reason.trim().is_empty() && reason.chars().count() <= 400 =>
                {
                    reason.trim().to_string()
                }
                _ => return Err(Error::new("InvalidPayload", "Invalid termination reason")),
            };
            if control.finished {
                return Err(Error::new("TerminalSession", "Agent task already finished"));
            }
            if let Some(existing) = &control.signal {
                if existing.request_id == req.id && existing.reason != reason {
                    return Err(Error::new(
                        "RequestIdConflict",
                        "Termination ID reused with another reason",
                    ));
                }
                return Ok(serde_json::to_value(existing)?);
            }
            let signal = AgentControl {
                version: VERSION,
                session_id: session.session_id,
                project_id: session.project_id.clone(),
                request_id: req.id,
                directive: "terminate".into(),
                status: "requested".into(),
                reason,
                requested_at_ms: now_ms(),
                acknowledged_at_ms: None,
            };
            atomic_json(&root.join("agent-control.json"), &Some(&signal))?;
            control.signal = Some(signal.clone());
            Ok(serde_json::to_value(signal)?)
        }
        "ack-stop" => {
            fields(&req.payload, &[])?;
            let mut signal = control.signal.clone().ok_or_else(|| {
                Error::new("NotRequested", "No termination command to acknowledge")
            })?;
            if signal.status != "acknowledged" {
                signal.status = "acknowledged".into();
                signal.acknowledged_at_ms = Some(now_ms());
                atomic_json(&root.join("agent-control.json"), &Some(&signal))?;
                control.signal = Some(signal.clone());
            }
            Ok(serde_json::to_value(signal)?)
        }
        _ => Err(Error::new(
            "UnsupportedCommand",
            "Not an agent control command",
        )),
    }
}

pub fn pump(root: &Path, session: &Session, state: &SharedControl) -> Result<(), Error> {
    let mut paths = fs::read_dir(root.join("control-requests"))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| regular(path) && managed_packet(path).is_some())
        .collect::<Vec<_>>();
    paths.sort();
    for path in paths.into_iter().take(8) {
        let (session_id, id) = managed_packet(&path).unwrap();
        let claimed = path.with_extension("working");
        match fs::rename(&path, &claimed) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error.into()),
        }
        let result = match read_json::<Request>(&claimed) {
            Ok(req) if req.id == id && req.session_id == session_id => {
                handle(root, session, state, &req)
            }
            Ok(_) => Err(Error::new(
                "InvalidPacket",
                "Control filename does not match IDs",
            )),
            Err(error) => Err(error),
        };
        let _ = fs::remove_file(claimed);
        atomic_json(
            &root
                .join("control-responses")
                .join(packet_name(session_id, id)),
            &Response::from_result(id, result),
        )?;
    }
    Ok(())
}

pub fn view(state: &SharedControl) -> Value {
    json!(state.lock().unwrap().signal)
}
