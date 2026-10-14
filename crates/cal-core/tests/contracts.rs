use cal_core::{
    journal::Journal,
    protocol::{Error, Request, Session, VERSION},
    storage::managed_packet,
    DomainAdapter, Runtime,
};
use serde_json::{json, Value};
use std::fs;
use tempfile::TempDir;
use uuid::Uuid;

#[derive(Default)]
struct Domain {
    writes: u64,
}
impl DomainAdapter for Domain {
    fn call(&mut self, _: &Session, command: &str, _: &Value) -> Result<Value, Error> {
        match command {
            "inspect" => Ok(json!({"projectRevision":self.writes})),
            "apply" => {
                self.writes += 1;
                Ok(json!({"projectRevision":self.writes}))
            }
            "finish" if self.writes > 0 => Ok(json!({"finished":true})),
            _ => Err(Error::new("IncompleteResult", "No real domain result")),
        }
    }
}
fn packet(runtime: &Runtime<Domain>, command: &str, payload: Value) -> Request {
    Request {
        version: VERSION,
        id: Uuid::new_v4(),
        session_id: runtime.session.session_id,
        project_id: runtime.session.project_id.clone(),
        token: runtime.session.token.clone(),
        command: command.into(),
        payload,
    }
}
fn active(temp: &TempDir) -> Runtime<Domain> {
    let mut runtime = Runtime::new(temp.path(), "demo", Domain::default()).unwrap();
    let req = packet(&runtime, "identify", json!({"name":"Codex"}));
    assert!(runtime.handle(req).ok);
    runtime
}
#[test]
fn authentication_and_version_precede_domain_access() {
    let temp = TempDir::new().unwrap();
    let mut runtime = active(&temp);
    for field in ["version", "session", "project", "token"] {
        let mut req = packet(&runtime, "apply", json!({}));
        match field {
            "version" => req.version = 9,
            "session" => req.session_id = Uuid::new_v4(),
            "project" => req.project_id = "other".into(),
            _ => req.token = "invalid".into(),
        }
        assert!(!runtime.handle(req).ok);
    }
    let req = packet(&runtime, "inspect", json!({}));
    assert_eq!(runtime.handle(req).result["domain"]["projectRevision"], 0);
    let req = packet(&runtime, "apply", Value::Null);
    assert_eq!(runtime.handle(req).error.unwrap().code, "InvalidPayload");
}
#[test]
fn request_cache_prevents_duplicate_writes_and_rejects_collision() {
    let temp = TempDir::new().unwrap();
    let mut runtime = active(&temp);
    let req = packet(&runtime, "apply", json!({}));
    assert_eq!(runtime.handle(req.clone()).result["projectRevision"], 1);
    assert_eq!(runtime.handle(req.clone()).result["projectRevision"], 1);
    let changed = Request {
        payload: json!({"different":true}),
        ..req
    };
    assert_eq!(
        runtime.handle(changed).error.unwrap().code,
        "RequestIdConflict"
    );
}
#[test]
fn cancel_preserves_domain_data_but_rejects_subsequent_mutations() {
    let temp = TempDir::new().unwrap();
    let mut runtime = active(&temp);
    for command in ["apply", "cancel"] {
        let req = packet(&runtime, command, json!({}));
        assert!(runtime.handle(req).ok);
    }
    let req = packet(&runtime, "apply", json!({}));
    assert_eq!(runtime.handle(req).error.unwrap().code, "TerminalSession");
    let req = packet(&runtime, "inspect", json!({}));
    let result = runtime.handle(req).result;
    assert_eq!(result["status"], "cancelled");
    assert_eq!(result["domain"]["projectRevision"], 1);
}
#[test]
fn finish_requires_adapter_confirmation() {
    let temp = TempDir::new().unwrap();
    let mut runtime = active(&temp);
    let req = packet(&runtime, "finish", json!({"summary":"done"}));
    assert!(!runtime.handle(req).ok);
    let req = packet(&runtime, "apply", json!({}));
    assert!(runtime.handle(req).ok);
    let req = packet(&runtime, "finish", json!({"summary":"done"}));
    assert!(runtime.handle(req).ok);
    let req = packet(&runtime, "log", json!({"message":"late"}));
    assert!(!runtime.handle(req).ok);
}
#[test]
fn malformed_progress_is_rejected_without_domain_effects() {
    let temp = TempDir::new().unwrap();
    let mut runtime = active(&temp);
    for payload in [
        json!({"message":"x","percent":true}),
        json!({"message":"x","percent":101}),
        json!({"message":"x","percent":1.5}),
        json!({"message":"x","extra":1}),
    ] {
        let req = packet(&runtime, "log", payload);
        assert!(!runtime.handle(req).ok);
    }
}
#[test]
fn exclusive_host_lock_and_session_cleanup() {
    let temp = TempDir::new().unwrap();
    let runtime = active(&temp);
    assert!(Runtime::new(temp.path(), "demo", Domain::default()).is_err());
    drop(runtime);
    assert!(!temp.path().join("session.json").exists());
    assert!(!temp.path().join("owner.lock").exists());
}
#[test]
fn journal_rotation_is_bounded_and_clear_cursor_does_not_replay() {
    let temp = TempDir::new().unwrap();
    let mut journal = Journal::new(temp.path(), 1024, 2, 3);
    let session = Uuid::new_v4();
    for _ in 0..20 {
        journal.emit(session, "log", "note", &"x".repeat(350), json!({}), None);
    }
    let paths = fs::read_dir(temp.path())
        .unwrap()
        .map(|e| e.unwrap().path())
        .collect::<Vec<_>>();
    assert!(paths.len() <= 3);
    for path in paths {
        assert!(fs::metadata(&path).unwrap().len() <= 1024);
        for line in fs::read_to_string(path).unwrap().lines() {
            serde_json::from_str::<Value>(line).unwrap();
        }
    }
    let cursor = journal.seq;
    assert_eq!(
        journal.since(Some(journal.epoch), cursor)["events"]
            .as_array()
            .unwrap()
            .len(),
        0
    );
    assert_eq!(journal.since(Some(journal.epoch), 0)["gap"], true);
    journal.emit(session, "log", "note", "new", json!({}), None);
    assert_eq!(
        journal.since(Some(journal.epoch), cursor)["events"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    let active = temp.path().join("activity.jsonl");
    fs::write(temp.path().join("user.jsonl"), "preserve").unwrap();
    assert!(journal.cleanup(session).unwrap() > 0);
    assert!(active.exists());
    assert!(temp.path().join("user.jsonl").exists());
}
#[test]
fn events_page_is_bounded_and_exposes_continuation() {
    let temp = TempDir::new().unwrap();
    let mut journal = Journal::new(temp.path(), 2 * 1024 * 1024, 2, 400);
    for _ in 0..30 {
        journal.emit(Uuid::new_v4(), "log", "note", "x", json!({}), None);
    }
    let page = journal.since(None, 0);
    assert_eq!(page["events"].as_array().unwrap().len(), 8);
    assert_eq!(page["seq"], 8);
    assert_eq!(page["latestSeq"], 30);
    assert_eq!(journal.since(Some(journal.epoch), 8)["seq"], 16);
}
#[test]
fn malformed_unicode_packet_filename_does_not_panic() {
    let name = format!("{}{}.json", "é".repeat(18), "x".repeat(37));
    assert!(managed_packet(std::path::Path::new(&name)).is_none());
}

#[test]
fn diagnostic_fields_cannot_make_events_page_exceed_packet_limit() {
    let temp = TempDir::new().unwrap();
    let mut journal = Journal::new(temp.path(), 2 * 1024 * 1024, 2, 400);
    for _ in 0..8 {
        journal.emit(
            Uuid::new_v4(),
            &"🙂".repeat(2000),
            "failed",
            &"🙂".repeat(4000),
            json!({"unbounded":"x".repeat(10000)}),
            None,
        );
    }
    let page = journal.since(None, 0);
    assert!(serde_json::to_vec(&page).unwrap().len() < cal_core::protocol::PACKET_LIMIT - 1024);
    assert_eq!(page["events"][0]["details"]["truncated"], true);
}
