use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fmt,
    time::{SystemTime, UNIX_EPOCH},
};
use uuid::Uuid;

pub const VERSION: u32 = 1;
pub const PACKET_LIMIT: usize = 64 * 1024;
pub const LIVE_TTL_MS: u64 = 6_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Error {
    pub code: String,
    pub message: String,
}

impl Error {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(value: std::io::Error) -> Self {
        Self::new("IoError", value.to_string())
    }
}
impl From<serde_json::Error> for Error {
    fn from(value: serde_json::Error) -> Self {
        Self::new("InvalidPacket", value.to_string())
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Session {
    pub version: u32,
    pub session_id: Uuid,
    pub project_id: String,
    pub token: String,
    pub pid: u32,
    pub heartbeat_ms: u64,
}

impl Session {
    pub fn new(project_id: &str) -> Self {
        Self {
            version: VERSION,
            session_id: Uuid::new_v4(),
            project_id: project_id.into(),
            token: format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple()),
            pid: std::process::id(),
            heartbeat_ms: now_ms(),
        }
    }
}

#[derive(Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Request {
    pub version: u32,
    pub id: Uuid,
    pub session_id: Uuid,
    pub project_id: String,
    pub token: String,
    pub command: String,
    pub payload: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Response {
    pub version: u32,
    pub id: Uuid,
    pub ok: bool,
    pub result: Value,
    pub error: Option<Error>,
}
impl Response {
    pub fn from_result(id: Uuid, result: Result<Value, Error>) -> Self {
        match result {
            Ok(value) => Self {
                version: VERSION,
                id,
                ok: true,
                result: value,
                error: None,
            },
            Err(error) => Self {
                version: VERSION,
                id,
                ok: false,
                result: Value::Null,
                error: Some(error),
            },
        }
    }
}

#[derive(Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    Waiting,
    Active,
    Finished,
    Cancelled,
}

pub fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

pub fn fields(payload: &Value, allowed: &[&str]) -> Result<(), Error> {
    let map = payload
        .as_object()
        .ok_or_else(|| Error::new("InvalidPayload", "Expected an object"))?;
    if map.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err(Error::new("InvalidPayload", "Unknown payload field"));
    }
    Ok(())
}
pub fn text(payload: &Value, key: &str, max: usize) -> Result<String, Error> {
    let value = payload[key].as_str().unwrap_or("").trim();
    if value.is_empty() || value.chars().count() > max {
        return Err(Error::new(
            "InvalidPayload",
            format!("Invalid {key} length"),
        ));
    }
    Ok(value.to_string())
}

pub fn unknown_result(command: &str) -> Error {
    Error::new(
        "UnknownResult",
        format!("Result of {command} is unknown; inspect before retrying a mutation"),
    )
}

pub fn context(session: &Session) -> Value {
    json!({"version": VERSION, "sessionId": session.session_id, "projectId": session.project_id})
}
