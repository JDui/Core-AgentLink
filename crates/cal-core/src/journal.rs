use crate::{
    protocol::{now_ms, Error},
    storage::regular,
};
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};
use uuid::Uuid;

pub struct Journal {
    root: PathBuf,
    pub epoch: Uuid,
    pub seq: u64,
    rows: VecDeque<Value>,
    max_bytes: u64,
    archives: usize,
    max_rows: usize,
    pub error: Option<String>,
}
impl Journal {
    pub fn new(root: &Path, max_bytes: u64, archives: usize, max_rows: usize) -> Self {
        Self {
            root: root.into(),
            epoch: Uuid::new_v4(),
            seq: 0,
            rows: VecDeque::new(),
            max_bytes: max_bytes.max(1024),
            archives,
            max_rows: max_rows.max(1),
            error: None,
        }
    }
    fn archives(&self) -> Result<Vec<(u64, PathBuf)>, Error> {
        let mut paths = Vec::new();
        for entry in fs::read_dir(&self.root)? {
            let path = entry?.path();
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if let Some(number) = name
                .strip_prefix("archive-")
                .and_then(|n| n.strip_suffix(".jsonl"))
            {
                if !number.is_empty()
                    && number.bytes().all(|b| b.is_ascii_digit())
                    && regular(&path)
                {
                    if let Ok(n) = number.parse::<u64>() {
                        paths.push((n, path));
                    }
                }
            }
        }
        paths.sort_by_key(|(n, _)| *n);
        Ok(paths)
    }
    pub fn emit(
        &mut self,
        session: Uuid,
        operation: &str,
        phase: &str,
        message: &str,
        details: Value,
        percent: Option<u8>,
    ) {
        self.seq += 1;
        let details = if serde_json::to_vec(&details)
            .map(|v| v.len())
            .unwrap_or(usize::MAX)
            <= 1024
        {
            details
        } else {
            json!({"truncated":true})
        };
        let event = json!({"epoch":self.epoch,"seq":self.seq,"timeMs":now_ms(),"sessionId":session,
            "operation":operation.chars().take(80).collect::<String>(),
            "phase":phase.chars().take(32).collect::<String>(),
            "message":message.chars().take(1000).collect::<String>(),
            "details":details,"percent":percent});
        self.rows.push_back(event.clone());
        while self.rows.len() > self.max_rows {
            self.rows.pop_front();
        }
        self.error = self.persist(&event).err().map(|e| e.to_string());
    }
    fn persist(&self, event: &Value) -> Result<(), Error> {
        let mut bytes = serde_json::to_vec(event)?;
        bytes.push(b'\n');
        if bytes.len() as u64 > self.max_bytes {
            return Err(Error::new("LogTooLarge", "Log event exceeds file limit"));
        }
        let current = self.root.join("activity.jsonl");
        if fs::symlink_metadata(&current).is_ok() && !regular(&current) {
            return Err(Error::new("InvalidPath", "Refusing non-regular log"));
        }
        if fs::metadata(&current).map(|m| m.len()).unwrap_or(0) + bytes.len() as u64
            > self.max_bytes
        {
            let old = self.archives()?;
            let next = old.last().map(|(n, _)| n + 1).unwrap_or(1);
            let target = self.root.join(format!("archive-{next:06}.jsonl"));
            if fs::symlink_metadata(&target).is_ok() {
                return Err(Error::new("InvalidPath", "Archive target exists"));
            }
            fs::rename(&current, target)?;
            let old = self.archives()?;
            for (_, path) in old.iter().take(old.len().saturating_sub(self.archives)) {
                fs::remove_file(path)?;
            }
        }
        let mut file = OpenOptions::new().create(true).append(true).open(current)?;
        file.write_all(&bytes)?;
        Ok(())
    }
    pub fn since(&self, epoch: Option<Uuid>, after: u64) -> Value {
        let reset = epoch != Some(self.epoch);
        let after = if reset { 0 } else { after };
        let first = self
            .rows
            .front()
            .and_then(|e| e["seq"].as_u64())
            .unwrap_or(self.seq + 1);
        let events = self
            .rows
            .iter()
            .filter(|e| e["seq"].as_u64().unwrap_or(0) > after)
            .take(8)
            .collect::<Vec<_>>();
        let seq = events
            .last()
            .and_then(|e| e["seq"].as_u64())
            .unwrap_or(after.min(self.seq));
        json!({"epoch":self.epoch,"seq":seq,"latestSeq":self.seq,"reset":reset,"gap":after < first.saturating_sub(1),
            "events": events,
            "error":self.error})
    }
    pub fn cleanup(&mut self, session: Uuid) -> Result<usize, Error> {
        let mut removed = 0;
        let result = (|| -> Result<(), Error> {
            for (_, path) in self.archives()? {
                fs::remove_file(path)?;
                removed += 1;
            }
            Ok(())
        })();
        self.emit(
            session,
            "cleanup",
            if result.is_ok() {
                "completed"
            } else {
                "failed"
            },
            "Managed archive cleanup",
            json!({"removed":removed}),
            None,
        );
        result.map(|_| removed)
    }
}
