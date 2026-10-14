use crate::protocol::{Error, PACKET_LIMIT};
use serde::{de::DeserializeOwned, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};
use uuid::Uuid;

pub fn regular(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|meta| meta.is_file() && !meta.file_type().is_symlink())
}

pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T, Error> {
    if !regular(path) {
        return Err(Error::new("InvalidPath", "Packet must be a regular file"));
    }
    let mut data = Vec::new();
    fs::File::open(path)?
        .take((PACKET_LIMIT + 1) as u64)
        .read_to_end(&mut data)?;
    if data.len() > PACKET_LIMIT {
        return Err(Error::new("PacketTooLarge", "Packet exceeds 64 KiB"));
    }
    let bytes = data.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&data);
    Ok(serde_json::from_slice(bytes)?)
}

pub fn atomic_json(path: &Path, value: &impl Serialize) -> Result<(), Error> {
    let data = serde_json::to_vec(value)?;
    if data.len() > PACKET_LIMIT {
        return Err(Error::new("PacketTooLarge", "Packet exceeds 64 KiB"));
    }
    if fs::symlink_metadata(path).is_ok_and(|meta| meta.file_type().is_symlink()) {
        return Err(Error::new("InvalidPath", "Refusing symlink target"));
    }
    let parent = path
        .parent()
        .ok_or_else(|| Error::new("InvalidPath", "Missing parent"))?;
    let temporary = parent.join(format!("{}.tmp", Uuid::new_v4()));
    let result = (|| -> Result<(), Error> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(&data)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)?;
        Ok(())
    })();
    let _ = fs::remove_file(temporary);
    result
}

pub fn packet_name(session: Uuid, request: Uuid) -> String {
    format!("{session}-{request}.json")
}

pub fn managed_packet(path: &Path) -> Option<(Uuid, Uuid)> {
    let name = path.file_name()?.to_str()?;
    if !name.is_ascii() || name.len() != 78 || &name[36..37] != "-" || !name.ends_with(".json") {
        return None;
    }
    let session = Uuid::parse_str(name.get(..36)?).ok()?;
    let request = Uuid::parse_str(name.get(37..73)?).ok()?;
    (packet_name(session, request) == name).then_some((session, request))
}

pub struct OwnerLock {
    pub root: PathBuf,
    path: PathBuf,
}
impl OwnerLock {
    pub fn acquire(root: &Path) -> Result<Self, Error> {
        if fs::symlink_metadata(root).is_ok_and(|meta| meta.file_type().is_symlink()) {
            return Err(Error::new(
                "InvalidPath",
                "State directory must not be a symlink",
            ));
        }
        fs::create_dir_all(root)?;
        let root = fs::canonicalize(root)?;
        let path = root.join("owner.lock");
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(|e| Error::new("HostOwnership", format!("Cannot acquire owner.lock: {e}")))?;
        if let Err(error) = write!(file, "{}", std::process::id()) {
            let _ = fs::remove_file(&path);
            return Err(error.into());
        }
        Ok(Self { root, path })
    }
}
impl Drop for OwnerLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}
