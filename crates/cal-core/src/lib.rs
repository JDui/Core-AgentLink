//! Language-neutral local control. Domain writes remain in the host adapter.
pub mod adapter;
pub mod client;
pub mod control;
pub mod journal;
pub mod protocol;
pub mod runtime;
pub mod storage;

pub use adapter::{DomainAdapter, ProcessAdapter};
pub use protocol::{Error, Request, Response, Session, VERSION};
pub use runtime::Runtime;
