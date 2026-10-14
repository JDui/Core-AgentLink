use crate::{
    adapter::DomainAdapter,
    journal::Journal,
    protocol::{fields, now_ms, text, Error, Request, Response, Session, Status, VERSION},
    storage::{atomic_json, managed_packet, packet_name, read_json, regular, OwnerLock},
};
use serde_json::{json, Value};
use std::{
    collections::{HashMap, VecDeque},
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, JoinHandle},
    time::Duration,
};
use uuid::Uuid;

pub struct Runtime<A: DomainAdapter> {
    // Drop stops heartbeat before removing session/ownership.
    root: PathBuf,
    pub session: Session,
    status: Status,
    name: String,
    percent: Option<u8>,
    journal: Journal,
    adapter: A,
    cache: HashMap<Uuid, (Request, Response)>,
    order: VecDeque<Uuid>,
    stop: Arc<AtomicBool>,
    heartbeat: Option<JoinHandle<()>>,
    heartbeat_error: Arc<std::sync::Mutex<Option<String>>>,
    _owner: OwnerLock,
}

impl<A: DomainAdapter> Runtime<A> {
    pub fn new(root: &Path, project_id: &str, adapter: A) -> Result<Self, Error> {
        if project_id.is_empty()
            || project_id.len() > 128
            || project_id.chars().any(char::is_control)
        {
            return Err(Error::new("InvalidProject", "Invalid project ID"));
        }
        let owner = OwnerLock::acquire(root)?;
        let root = owner.root.clone();
        for name in ["requests", "responses"] {
            let directory = root.join(name);
            if fs::symlink_metadata(&directory)
                .is_ok_and(|m| !m.is_dir() || m.file_type().is_symlink())
            {
                return Err(Error::new("InvalidPath", "Invalid IPC directory"));
            }
            fs::create_dir_all(directory)?;
        }
        let session = Session::new(project_id);
        atomic_json(&root.join("session.json"), &session)?;
        let mut journal = Journal::new(&root, 2 * 1024 * 1024, 2, 400);
        journal.emit(
            session.session_id,
            "session",
            "waiting",
            "Waiting for an external agent",
            json!({}),
            None,
        );
        let stop = Arc::new(AtomicBool::new(false));
        let heartbeat_error = Arc::new(std::sync::Mutex::new(None));
        let (hb_root, mut hb_session, hb_stop, hb_error) = (
            root.clone(),
            session.clone(),
            stop.clone(),
            heartbeat_error.clone(),
        );
        let heartbeat = thread::spawn(move || {
            let mut last = 0;
            while !hb_stop.load(Ordering::Acquire) {
                if now_ms().saturating_sub(last) >= 1_000 {
                    // A replaced session must never be resurrected by the old heartbeat.
                    let current: Result<Session, _> = read_json(&hb_root.join("session.json"));
                    if !current.is_ok_and(|s| {
                        s.session_id == hb_session.session_id && s.token == hb_session.token
                    }) {
                        *hb_error.lock().unwrap() = Some("Session ownership was lost".into());
                        hb_stop.store(true, Ordering::Release);
                        break;
                    }
                    hb_session.heartbeat_ms = now_ms();
                    *hb_error.lock().unwrap() =
                        atomic_json(&hb_root.join("session.json"), &hb_session)
                            .err()
                            .map(|e| e.to_string());
                    last = now_ms();
                }
                thread::sleep(Duration::from_millis(50));
            }
        });
        Ok(Self {
            _owner: owner,
            root,
            session,
            status: Status::Waiting,
            name: String::new(),
            percent: None,
            journal,
            adapter,
            cache: HashMap::new(),
            order: VecDeque::new(),
            stop,
            heartbeat: Some(heartbeat),
            heartbeat_error,
        })
    }
    pub fn root(&self) -> &Path {
        &self.root
    }
    fn authenticate(&self, req: &Request) -> Result<(), Error> {
        if req.version != VERSION {
            return Err(Error::new("ProtocolVersion", "Unsupported request version"));
        }
        if req.session_id != self.session.session_id || req.project_id != self.session.project_id {
            return Err(Error::new(
                "StaleSession",
                "Request targets an old or different session/project",
            ));
        }
        if req.token != self.session.token {
            return Err(Error::new(
                "InvalidCredential",
                "Invalid session credential",
            ));
        }
        if self.stop.load(Ordering::Acquire) {
            return Err(Error::new("Disconnected", "Session ownership was lost"));
        }
        let current: Session = read_json(&self.root.join("session.json"))?;
        if current.session_id != req.session_id || current.token != req.token {
            return Err(Error::new("StaleSession", "Session was replaced"));
        }
        Ok(())
    }
    pub fn handle(&mut self, req: Request) -> Response {
        if let Err(error) = self.authenticate(&req) {
            return Response::from_result(req.id, Err(error));
        }
        if !req.payload.is_object() {
            return Response::from_result(
                req.id,
                Err(Error::new("InvalidPayload", "Payload must be an object")),
            );
        }
        if let Some((previous, response)) = self.cache.get(&req.id) {
            return if previous == &req {
                response.clone()
            } else {
                Response::from_result(
                    req.id,
                    Err(Error::new(
                        "RequestIdConflict",
                        "Request ID reused with different content",
                    )),
                )
            };
        }
        let result = self.execute(&req.command, &req.payload);
        if let Err(error) = &result {
            self.journal.emit(
                self.session.session_id,
                &req.command,
                "failed",
                &error.message,
                json!({"code":error.code}),
                self.percent,
            );
        }
        let mut response = Response::from_result(req.id, result);
        if serde_json::to_vec(&response)
            .map(|v| v.len())
            .unwrap_or(usize::MAX)
            > crate::protocol::PACKET_LIMIT
        {
            response = Response::from_result(
                req.id,
                Err(Error::new(
                    "UnknownResult",
                    "Response exceeded limit; inspect before retrying a mutation",
                )),
            );
        }
        self.cache.insert(req.id, (req.clone(), response.clone()));
        self.order.push_back(req.id);
        while self.order.len() > 256 {
            if let Some(id) = self.order.pop_front() {
                self.cache.remove(&id);
            }
        }
        response
    }
    fn execute(&mut self, command: &str, payload: &Value) -> Result<Value, Error> {
        if command == "inspect" {
            fields(payload, &[])?;
            let domain = self.adapter.call(&self.session, "inspect", &json!({}))?;
            return Ok(
                json!({"sessionId":self.session.session_id,"projectId":self.session.project_id,
                "status":self.status,"agentName":self.name,"percent":self.percent,
                "domain":domain,"journalError":self.journal.error,"transportError":*self.heartbeat_error.lock().unwrap()}),
            );
        }
        if command == "events" {
            fields(payload, &["epoch", "after"])?;
            let epoch = match payload.get("epoch") {
                None | Some(Value::Null) => None,
                Some(Value::String(value)) => Some(
                    Uuid::parse_str(value)
                        .map_err(|_| Error::new("InvalidPayload", "Invalid epoch"))?,
                ),
                _ => return Err(Error::new("InvalidPayload", "Invalid epoch")),
            };
            let after = payload
                .get("after")
                .map(|v| {
                    v.as_u64()
                        .ok_or_else(|| Error::new("InvalidPayload", "Invalid cursor"))
                })
                .transpose()?
                .unwrap_or(0);
            return Ok(self.journal.since(epoch, after));
        }
        if command == "cleanup" {
            fields(payload, &[])?;
            return Ok(json!({"removed":self.journal.cleanup(self.session.session_id)?}));
        }
        if command == "cancel" {
            fields(payload, &[])?;
            if self.status == Status::Finished {
                return Err(Error::new(
                    "TerminalSession",
                    "Finished session cannot be cancelled",
                ));
            }
            if self.status != Status::Cancelled {
                self.status = Status::Cancelled;
                self.percent = None;
                self.journal.emit(
                    self.session.session_id,
                    command,
                    "cancelled",
                    "Cancelled; committed changes are retained",
                    json!({}),
                    None,
                );
            }
            return Ok(json!({"cancelled":true}));
        }
        if matches!(self.status, Status::Cancelled | Status::Finished) {
            return Err(Error::new(
                "TerminalSession",
                "Start a new host session before writing",
            ));
        }
        if command == "identify" {
            fields(payload, &["name"])?;
            let name = text(payload, "name", 8)?;
            if name.chars().any(|c| c.is_whitespace() || c.is_control()) {
                return Err(Error::new("InvalidPayload", "Invalid agent name"));
            }
            if self.status == Status::Active && self.name != name {
                return Err(Error::new("IdentityConflict", "An agent is already active"));
            }
            if self.status != Status::Active {
                self.status = Status::Active;
                self.name = name;
                self.journal.emit(
                    self.session.session_id,
                    command,
                    "identified",
                    "Agent connected",
                    json!({"name":self.name}),
                    None,
                );
            }
            return Ok(json!({"name":self.name}));
        }
        if self.status != Status::Active {
            return Err(Error::new("NotIdentified", "Identify before writing"));
        }
        if command == "log" {
            fields(payload, &["message", "percent"])?;
            let message = text(payload, "message", 400)?;
            if let Some(value) = payload.get("percent") {
                self.percent = Some(value.as_u64().filter(|n| *n <= 100).ok_or_else(|| {
                    Error::new("InvalidPayload", "percent must be an integer 0–100")
                })? as u8);
            }
            self.journal.emit(
                self.session.session_id,
                command,
                "progress",
                &message,
                json!({}),
                self.percent,
            );
            return Ok(json!({"recorded":true}));
        }
        if !["apply", "undo", "finish"].contains(&command) {
            return Err(Error::new("UnsupportedCommand", "Command is not allowed"));
        }
        let summary = if command == "finish" {
            fields(payload, &["summary"])?;
            Some(text(payload, "summary", 1000)?)
        } else {
            None
        };
        let result = self.adapter.call(&self.session, command, payload)?;
        if command == "finish" {
            if result["finished"] != true {
                return Err(Error::new(
                    "IncompleteResult",
                    "Adapter did not verify completion",
                ));
            }
            self.status = Status::Finished;
            self.percent = Some(100);
        }
        self.journal.emit(self.session.session_id, command, if command == "finish" { "finished" } else { "completed" },
            summary.as_deref().unwrap_or("Domain operation completed"),
            json!({"runId":result["runId"],"projectRevision":result["projectRevision"],"dryRun":result["dryRun"]}), self.percent);
        Ok(result)
    }
    pub fn pump(&mut self) -> Result<usize, Error> {
        let mut entries = fs::read_dir(self.root.join("requests"))?
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| managed_packet(p).is_some() && regular(p))
            .collect::<Vec<_>>();
        entries.sort();
        let mut count = 0;
        for path in entries.iter().take(8) {
            let (session_id, id) = managed_packet(path).unwrap();
            // Claim the packet before execution: client timeout cannot remove our working copy.
            let claimed = path.with_extension("working");
            match fs::rename(path, &claimed) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(error.into()),
            }
            let response = match read_json::<Request>(&claimed) {
                Ok(req) if req.id == id && req.session_id == session_id => self.handle(req),
                Ok(_) => Response::from_result(
                    id,
                    Err(Error::new(
                        "InvalidPacket",
                        "Filename does not match request IDs",
                    )),
                ),
                Err(error) => Response::from_result(id, Err(error)),
            };
            let _ = fs::remove_file(claimed);
            atomic_json(
                &self
                    .root
                    .join("responses")
                    .join(packet_name(session_id, id)),
                &response,
            )?;
            count += 1;
        }
        Ok(count)
    }
    pub fn cleanup_ipc(&self) -> Result<usize, Error> {
        let mut removed = 0;
        for name in ["requests", "responses"] {
            for entry in fs::read_dir(self.root.join(name))? {
                let path = entry?.path();
                if managed_packet(&path).is_none() || !regular(&path) {
                    continue;
                }
                let metadata = match fs::metadata(&path) {
                    Ok(metadata) => metadata,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                    Err(error) => return Err(error.into()),
                };
                if metadata.modified()?.elapsed().unwrap_or(Duration::ZERO)
                    > Duration::from_secs(60)
                {
                    match fs::remove_file(path) {
                        Ok(()) => removed += 1,
                        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                        Err(error) => return Err(error.into()),
                    }
                }
            }
        }
        Ok(removed)
    }
}
impl<A: DomainAdapter> Drop for Runtime<A> {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(handle) = self.heartbeat.take() {
            let _ = handle.join();
        }
        let path = self.root.join("session.json");
        if read_json::<Session>(&path)
            .is_ok_and(|s| s.session_id == self.session.session_id && s.token == self.session.token)
        {
            let _ = fs::remove_file(path);
        }
    }
}
