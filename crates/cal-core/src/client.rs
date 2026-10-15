use crate::{
    protocol::{now_ms, unknown_result, Error, Request, Response, Session, LIVE_TTL_MS, VERSION},
    storage::{atomic_json, packet_name, read_json},
};
use serde_json::Value;
use std::{
    fs,
    path::Path,
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

pub fn live_session(root: &Path, session_id: Uuid, project_id: &str) -> Result<Session, Error> {
    let session: Session = read_json(&root.join("session.json"))?;
    if session.version != VERSION {
        return Err(Error::new("ProtocolVersion", "Unsupported session version"));
    }
    if session.session_id != session_id || session.project_id != project_id {
        return Err(Error::new(
            "StaleSession",
            "Prompt no longer targets the current project/session",
        ));
    }
    let now = now_ms();
    if session.heartbeat_ms > now + 1_000 || now.saturating_sub(session.heartbeat_ms) > LIVE_TTL_MS
    {
        return Err(Error::new(
            "Disconnected",
            "Host heartbeat expired or invalid",
        ));
    }
    Ok(session)
}

pub fn request(
    root: &Path,
    session_id: Uuid,
    project_id: &str,
    command: &str,
    payload: Value,
    timeout: Duration,
    request_id: Option<Uuid>,
) -> Result<Value, Error> {
    let session = live_session(root, session_id, project_id)?;
    let id = request_id.unwrap_or_else(Uuid::new_v4);
    let name = packet_name(session_id, id);
    let control = ["stop-agent", "control", "ack-stop"].contains(&command);
    let request_path = root
        .join(if control {
            "control-requests"
        } else {
            "requests"
        })
        .join(&name);
    let response_path = root
        .join(if control {
            "control-responses"
        } else {
            "responses"
        })
        .join(&name);
    if response_path.exists() {
        fs::remove_file(&response_path)?;
    }
    atomic_json(
        &request_path,
        &Request {
            version: VERSION,
            id,
            session_id,
            project_id: project_id.into(),
            token: session.token.clone(),
            command: command.into(),
            payload,
        },
    )?;
    let start = Instant::now();
    let result = (|| -> Result<Value, Error> {
        while start.elapsed() < timeout {
            // Once a packet is published, loss/rotation makes a mutation's outcome unknown.
            let current =
                live_session(root, session_id, project_id).map_err(|_| unknown_result(command))?;
            if current.token != session.token {
                return Err(unknown_result(command));
            }
            if response_path.exists() {
                let response: Response = read_json(&response_path)?;
                fs::remove_file(&response_path)?;
                if response.id != id || response.version != VERSION {
                    return Err(unknown_result(command));
                }
                return if response.ok {
                    Ok(response.result)
                } else {
                    Err(response
                        .error
                        .unwrap_or_else(|| Error::new("InvalidPacket", "Missing error")))
                };
            }
            thread::sleep(Duration::from_millis(50));
        }
        Err(unknown_result(command))
    })();
    let _ = fs::remove_file(request_path);
    result
}
