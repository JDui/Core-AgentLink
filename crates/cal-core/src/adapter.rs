use crate::protocol::{context, unknown_result, Error, Session, PACKET_LIMIT};
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::Duration,
};
use uuid::Uuid;

/// Implement this in the application. Domain validation/save/undo stays here.
pub trait DomainAdapter {
    fn call(&mut self, session: &Session, command: &str, payload: &Value) -> Result<Value, Error>;
}

/// Bounded JSONL adapter example. Only host startup chooses the executable/script.
pub struct ProcessAdapter {
    child: Child,
    input: ChildStdin,
    output: Receiver<Result<Value, Error>>,
    failed: bool,
}
impl ProcessAdapter {
    pub fn python(executable: &Path, script: &Path) -> Result<Self, Error> {
        let script = std::fs::canonicalize(script)?;
        let mut command = Command::new(executable);
        command
            .arg("-u")
            .arg(script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let mut child = command.spawn()?;
        let input = child
            .stdin
            .take()
            .ok_or_else(|| Error::new("AdapterError", "Missing adapter stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| Error::new("AdapterError", "Missing adapter stdout"))?;
        let (tx, output) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut bytes = Vec::new();
                let read = reader
                    .by_ref()
                    .take((PACKET_LIMIT + 1) as u64)
                    .read_until(b'\n', &mut bytes);
                let item = match read {
                    Ok(0) => break,
                    Ok(_) if bytes.len() > PACKET_LIMIT || !bytes.ends_with(b"\n") => Err(
                        Error::new("AdapterError", "Oversized or incomplete adapter response"),
                    ),
                    Ok(_) => serde_json::from_slice(&bytes).map_err(Error::from),
                    Err(error) => Err(error.into()),
                };
                let failed = item.is_err();
                if tx.send(item).is_err() || failed {
                    break;
                }
            }
        });
        Ok(Self {
            child,
            input,
            output,
            failed: false,
        })
    }
    fn invalidate(&mut self) {
        self.failed = true;
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
impl DomainAdapter for ProcessAdapter {
    fn call(&mut self, session: &Session, command: &str, payload: &Value) -> Result<Value, Error> {
        if self.failed {
            return Err(Error::new(
                "AdapterUnavailable",
                "Adapter stopped; result may require application recovery",
            ));
        }
        let id = Uuid::new_v4();
        let mut data = serde_json::to_vec(
            &json!({"id":id,"context":context(session),"command":command,"payload":payload}),
        )?;
        data.push(b'\n');
        if data.len() > PACKET_LIMIT {
            return Err(Error::new(
                "PacketTooLarge",
                "Adapter request exceeds limit",
            ));
        }
        if self
            .input
            .write_all(&data)
            .and_then(|_| self.input.flush())
            .is_err()
        {
            self.invalidate();
            return Err(unknown_result(command));
        }
        let result = match self.output.recv_timeout(Duration::from_secs(5)) {
            Ok(Ok(value)) => value,
            _ => {
                self.invalidate();
                return Err(unknown_result(command));
            }
        };
        if result["id"].as_str() != Some(id.to_string().as_str()) || !result["ok"].is_boolean() {
            self.invalidate();
            return Err(unknown_result(command));
        }
        if result["ok"] == true {
            Ok(result["result"].clone())
        } else {
            Err(serde_json::from_value(result["error"].clone())
                .unwrap_or_else(|_| Error::new("AdapterError", "Invalid adapter error")))
        }
    }
}
impl Drop for ProcessAdapter {
    fn drop(&mut self) {
        self.invalidate();
    }
}
