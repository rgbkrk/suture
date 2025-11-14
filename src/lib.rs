use pyo3::prelude::*;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3_async_runtimes::tokio::future_into_py;
use samod::DocumentId;
use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;
use tokio::task::JoinHandle;

use automerge::{transaction::Transactable, ReadDoc};

type TaskSet = Arc<AsyncMutex<Vec<JoinHandle<()>>>>;

/// A repository for managing Automerge documents with sync capabilities.
///
/// A Repo is similar to a database - it manages documents, storage, and networking.
/// Documents are CRDTs (Conflict-Free Replicated Data Types) that automatically
/// merge concurrent changes from multiple users.
///
/// This repo uses in-memory storage and has no network adapters by default.
///
/// Examples:
///     >>> repo = Repo()
///     >>> doc = await repo.create()
///     >>> await doc.set_string("title", "My Document")
#[pyclass]
struct Repo {
    inner: Arc<samod::Repo>,
    _runtime: Arc<tokio::runtime::Runtime>,
    tasks: TaskSet,
}

#[pymethods]
impl Repo {
    #[new]
    fn new() -> PyResult<Self> {
        // Create a new tokio runtime in a separate thread
        let runtime = tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create runtime: {}", e)))?;

        let repo = runtime.block_on(async {
            samod::Repo::build_tokio()
                .with_storage(samod::storage::InMemoryStorage::new())
                .load()
                .await
        });

        Ok(Repo {
            inner: Arc::new(repo),
            _runtime: Arc::new(runtime),
            tasks: Arc::new(AsyncMutex::new(Vec::new())),
        })
    }

    /// Get this repository's unique peer ID.
    ///
    /// The peer ID identifies this repo instance in sync operations.
    /// Each repo has a unique ID that persists across the lifetime of the Repo.
    ///
    /// Returns:
    ///     str: A unique identifier for this peer
    fn peer_id(&self) -> String {
        self.inner.peer_id().to_string()
    }

    fn __repr__(&self) -> String {
        format!("Repo(peer_id='{}')", self.peer_id())
    }

    /// Connect to a WebSocket sync server for real-time collaboration.
    ///
    /// Establishes a WebSocket connection to sync documents with remote peers.
    /// Changes made locally will be sent to the server, and changes from other
    /// peers will be received and merged automatically.
    ///
    /// The connection runs in the background after this coroutine completes.
    ///
    /// Args:
    ///     url (str): WebSocket URL (e.g., "ws://localhost:3030" or "wss://sync.automerge.org")
    ///
    /// Returns:
    ///     Coroutine: Resolves when the connection is established
    ///
    /// Raises:
    ///     ValueError: If the URL is invalid
    ///     RuntimeError: If the connection fails
    fn connect_websocket<'py>(
        &self,
        py: Python<'py>,
        url: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let repo = self.inner.clone();
        let tasks = self.tasks.clone();

        future_into_py(py, async move {
            // Parse the URL
            let url = url.parse::<tokio_tungstenite::tungstenite::http::Uri>()
                .map_err(|e| PyValueError::new_err(format!("Invalid URL: {}", e)))?;

            // Connect to the WebSocket
            let (ws_stream, _) = tokio_tungstenite::connect_async(url)
                .await
                .map_err(|e| PyRuntimeError::new_err(format!("Failed to connect: {}", e)))?;

            // Spawn the connection in the background
            let handle = tokio::spawn(async move {
                let reason = repo.connect_tungstenite(ws_stream, samod::ConnDirection::Outgoing).await;
                tracing::info!("Connection finished: {:?}", reason);
            });

            tasks.lock().await.push(handle);

            // Small delay to allow initial handshake
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

            Ok(None::<Py<PyAny>>)
        })
    }

    /// Find a document by its ID (AutomergeUrl format)
    fn find<'py>(
        &self,
        py: Python<'py>,
        doc_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let repo = self.inner.clone();

        let id_str = doc_id.strip_prefix("automerge:").unwrap_or(&doc_id);

        let document_id: samod_core::DocumentId = id_str.parse()
            .map_err(|e| PyValueError::new_err(format!("Invalid document ID: {}", e)))?;


        future_into_py(py, async move {
            let result = repo.find(document_id).await;

            match result {
                Ok(Some(handle)) => {
                    let document_id = handle.document_id().clone();
                    Ok(Some(DocHandle {
                        document_id,
                        inner: Arc::new(AsyncMutex::new(handle)),
                    }))
                }
                Ok(None) => Ok(None),
                Err(_) => Err(PyRuntimeError::new_err("Repository stopped")),
            }
        })
    }

    /// Create a new empty Automerge document.
    ///
    /// The document is automatically saved and announced to connected peers.
    /// You can share the document with others using `handle.url()`.
    ///
    /// Returns:
    ///     Coroutine[DocHandle]: A handle to the newly created document
    ///
    /// Raises:
    ///     RuntimeError: If the repository has stopped
    fn create<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let repo = self.inner.clone();

        future_into_py(py, async move {
            let initial_doc = automerge::Automerge::new();
            let result = repo.create(initial_doc).await;

            match result {
                Ok(handle) => {
                    let document_id = handle.document_id().clone();
                    Ok(DocHandle {
                        inner: Arc::new(AsyncMutex::new(handle)),
                        document_id,
                    })
                }
                Err(_) => Err(PyRuntimeError::new_err("Repository stopped")),
            }
        })
    }

    /// Wait until this repo connects to a specific peer.
    ///
    /// Blocks until a connection is established with the peer identified
    /// by the given peer ID. Useful for ensuring sync readiness before
    /// performing operations that depend on a specific peer.
    ///
    /// Args:
    ///     peer_id (str): The peer ID to wait for
    ///
    /// Returns:
    ///     Coroutine: Resolves when connected to the peer
    ///
    /// Raises:
    ///     RuntimeError: If the repository has stopped
    fn when_connected<'py>(
        &self,
        py: Python<'py>,
        peer_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let repo = self.inner.clone();
        let peer_id: samod_core::PeerId = peer_id.into();

        future_into_py(py, async move {
            repo.when_connected(peer_id).await
                .map_err(|_| PyRuntimeError::new_err("Repository stopped"))?;
            Ok(None::<Py<PyAny>>)
        })
    }

    /// Stop the repository and close all document connections
    fn stop<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let repo = self.inner.clone();
        let tasks = self.tasks.clone();

        future_into_py(py, async move {
            for handle in tasks.lock().await.drain(..) {
                handle.abort();
            }
            repo.stop().await;
            Ok(None::<Py<PyAny>>)
        })
    }
}

/// A handle to an Automerge document in the repository.
///
/// DocHandles provide access to CRDT documents that support concurrent editing.
/// Multiple users can make changes simultaneously, and Automerge will automatically
/// merge those changes.
#[pyclass]
struct DocHandle {
    inner: Arc<AsyncMutex<samod::DocHandle>>,
    document_id: DocumentId,
}

#[pymethods]
impl DocHandle {
    /// Get the unique document ID.
    ///
    /// Returns:
    ///     str: The document's ID
    #[getter]
    fn document_id(&self) -> String {
        self.document_id.to_string()
    }

    /// Get the unique document URL.
    ///
    /// Returns the AutomergeUrl that identifies this document.
    /// This URL can be shared with others to give them access to the document.
    ///
    /// Returns:
    ///     str: The document's URL (e.g., "automerge:...")
    #[getter]
    fn url(&self) -> String {
        format!("automerge:{}", self.document_id)
    }

    fn __repr__(&self) -> String {
        format!("DocHandle(url='{}')", self.url())
    }

    /// Retrieve the document as a byte array.
    ///
    /// Returns a compact binary representation of the entire document,
    /// including its complete edit history.
    ///
    /// Returns:
    ///     Coroutine[bytes]: The serialized document
    ///
    /// Raises:
    ///     RuntimeError: If serialization fails
    fn dump<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;
            let bytes = handle.with_document(|doc| {
                Ok::<_, automerge::AutomergeError>(doc.save())
            });

            match bytes {
                Ok(b) => Ok(b),
                Err(e) => Err(PyRuntimeError::new_err(format!("Failed to save document: {}", e))),
            }
        })
    }

    /// Set a string field in the document root.
    ///
    /// In Automerge, strings are collaborative text sequences by default.
    /// Concurrent updates from different users will be merged as intelligently as possible.
    ///
    /// Args:
    ///     key (str): The field name to set
    ///     value (str): The string value to set
    ///
    /// Returns:
    ///     Coroutine: Resolves when the operation completes and is saved/synced
    ///
    /// Raises:
    ///     RuntimeError: If the operation fails
    fn set_string<'py>(
        &self,
        py: Python<'py>,
        key: String,
        value: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            handle.with_document(|doc| {
                doc.transact(|tx| {
                    tx.put(automerge::ROOT, key, value)?;
                    Ok::<_, automerge::AutomergeError>(())
                }).map_err(|e| e.error)?;
                Ok::<_, automerge::AutomergeError>(())
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Document operation failed: {:?}", e)))?;

            Ok(None::<Py<PyAny>>)
        })
    }

    /// Get a string field from the document root.
    ///
    /// Reads the current value of a string field. If the field doesn't exist
    /// or is not a string, returns None.
    ///
    /// Args:
    ///     key (str): The field name to retrieve
    ///
    /// Returns:
    ///     Coroutine[Optional[str]]: The string value if it exists, None otherwise
    ///
    /// Raises:
    ///     RuntimeError: If reading fails
    fn get_string<'py>(
        &self,
        py: Python<'py>,
        key: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let result = handle.with_document(|doc| {
                match doc.get(automerge::ROOT, &key) {
                    Ok(Some((automerge::Value::Scalar(s), _))) => {
                        match s.as_ref() {
                            automerge::ScalarValue::Str(string) => Ok::<_, automerge::AutomergeError>(Some(string.to_string())),
                            _ => Ok(None),
                        }
                    }
                    Ok(Some(_)) => Ok(None),
                    Ok(None) => Ok(None),
                    Err(e) => Err(e),
                }
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to get field: {}", e)))?;

            Ok(result)
        })
    }

    /// Get all keys at the document root.
    ///
    /// Returns a list of all field names currently in the document.
    ///
    /// Returns:
    ///     Coroutine[List[str]]: List of all keys in the document
    ///
    /// Raises:
    ///     RuntimeError: If the operation fails
    fn get_keys<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let keys = handle.with_document(|doc| {
                let mut keys = Vec::new();
                for key in doc.keys(automerge::ROOT) {
                    keys.push(key.to_string());
                }
                Ok::<_, automerge::AutomergeError>(keys)
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to get keys: {}", e)))?;

            Ok(keys)
        })
    }

    /// Create or replace a text field at the document root.
    ///
    /// Creates a new Automerge Text object, which supports character-level
    /// collaborative editing operations like splice, insert, and delete.
    ///
    /// Args:
    ///     key (str): The field name
    ///     value (str): Initial text content
    ///
    /// Returns:
    ///     Coroutine[Text]: A Text handle for performing operations
    ///
    /// Raises:
    ///     RuntimeError: If the operation fails
    ///
    /// Example:
    ///     >>> text = await doc.put_text("content", "Hello World")
    ///     >>> await text.splice(6, 0, "Beautiful ")
    fn put_text<'py>(
        &self,
        py: Python<'py>,
        key: String,
        value: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();
        let document_id = self.document_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let obj_id = handle.with_document(|doc| {
                doc.transact(|tx| {
                    let obj = tx.put_object(automerge::ROOT, &key, automerge::ObjType::Text)?;
                    tx.splice_text(&obj, 0, 0, &value)?;
                    Ok::<_, automerge::AutomergeError>(obj)
                })
            });

            // Extract the obj from the transaction result
            let obj_id = match obj_id {
                Ok(success) => success.result,
                Err(e) => return Err(PyRuntimeError::new_err(format!("Failed to create text: {}", e.error))),
            };

            Ok(Text {
                handle: Arc::new(AsyncMutex::new(handle.clone())),
                obj_id: Arc::new(obj_id),
                document_id,
            })
        })
    }

    /// Get a text field from the document root.
    ///
    /// Returns a Text handle for an existing text field.
    ///
    /// Args:
    ///     key (str): The field name
    ///
    /// Returns:
    ///     Coroutine[Optional[Text]]: Text handle if the field exists and is a text object
    ///
    /// Raises:
    ///     RuntimeError: If reading fails
    ///
    /// Example:
    ///     >>> text = await doc.get_text("content")
    ///     >>> if text:
    ///     >>>     content = await text.get()
    fn get_text<'py>(
        &self,
        py: Python<'py>,
        key: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.inner.clone();
        let document_id = self.document_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let result = handle.with_document(|doc| {
                match doc.get(automerge::ROOT, &key) {
                    Ok(Some((automerge::Value::Object(automerge::ObjType::Text), obj_id))) => {
                        Ok::<_, automerge::AutomergeError>(Some(obj_id))
                    }
                    Ok(_) => Ok(None),
                    Err(e) => Err(e),
                }
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to get text: {}", e)))?;

            Ok(result.map(|obj_id| Text {
                handle: Arc::new(AsyncMutex::new(handle.clone())),
                obj_id: Arc::new(obj_id),
                document_id,
            }))
        })
    }

}

/// A handle to an Automerge Text object for collaborative text editing.
///
/// Text objects support character-level operations that automatically merge
/// concurrent edits from multiple users. All position indices are based on
/// character counts (not byte offsets), making them safe for Unicode text.
///
/// Example:
///     >>> text = await doc.put_text("notes", "Hello World")
///     >>> await text.splice(6, 0, "Beautiful ")  # Insert
///     >>> content = await text.get()
///     >>> print(content)  # "Hello Beautiful World"
#[pyclass]
struct Text {
    handle: Arc<AsyncMutex<samod::DocHandle>>,
    obj_id: Arc<automerge::ObjId>,
    document_id: DocumentId,
}


#[pymethods]
impl Text {
    /// Get the current text content as a string.
    ///
    /// Returns:
    ///     Coroutine[str]: The complete text content
    ///
    /// Raises:
    ///     RuntimeError: If reading fails
    fn get<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.handle.clone();
        let obj_id = self.obj_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let text = handle.with_document(|doc| {
                doc.text(&*obj_id)
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to read text: {}", e)))?;

            Ok(text)
        })
    }

    /// Get the character length of the text.
    ///
    /// Returns:
    ///     Coroutine[int]: Number of characters in the text
    ///
    /// Raises:
    ///     RuntimeError: If reading fails
    fn length<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.handle.clone();
        let obj_id = self.obj_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            let len = handle.with_document(|doc| {
                let text = doc.text(&*obj_id)?;
                Ok::<_, automerge::AutomergeError>(text.chars().count())
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to get length: {}", e)))?;

            Ok(len)
        })
    }

    /// Splice text: insert and/or delete characters at a position.
    ///
    /// This is the universal text editing operation. It can insert, delete,
    /// or replace text at any character position.
    ///
    /// Args:
    ///     pos (int): Character position to start at (0-based)
    ///     delete (int): Number of characters to delete (can be 0)
    ///     insert (str): Text to insert (can be empty string)
    ///
    /// Returns:
    ///     Coroutine: Resolves when the operation completes
    ///
    /// Raises:
    ///     RuntimeError: If the operation fails
    ///
    /// Examples:
    ///     >>> await text.splice(0, 0, "Hello")      # Insert at start
    ///     >>> await text.splice(5, 0, " World")     # Insert at position 5
    ///     >>> await text.splice(5, 6, "")           # Delete 6 chars from position 5
    ///     >>> await text.splice(0, 5, "Hi")         # Replace first 5 chars with "Hi"
    fn splice<'py>(
        &self,
        py: Python<'py>,
        pos: usize,
        delete: isize,
        insert: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.handle.clone();
        let obj_id = self.obj_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            handle.with_document(|doc| {
                doc.transact(|tx| {
                    tx.splice_text(&*obj_id, pos, delete, &insert)?;
                    Ok::<_, automerge::AutomergeError>(())
                }).map_err(|e| e.error)?;
                Ok::<_, automerge::AutomergeError>(())
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Splice failed: {}", e)))?;

            Ok(None::<Py<PyAny>>)
        })
    }

    /// Insert text at a position without deleting anything.
    ///
    /// Convenience method equivalent to splice(pos, 0, text).
    ///
    /// Args:
    ///     pos (int): Character position to insert at
    ///     text (str): Text to insert
    ///
    /// Returns:
    ///     Coroutine: Resolves when the operation completes
    fn insert<'py>(
        &self,
        py: Python<'py>,
        pos: usize,
        text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.splice(py, pos, 0, text)
    }

    /// Delete characters at a position.
    ///
    /// Convenience method equivalent to splice(pos, length, "").
    ///
    /// Args:
    ///     pos (int): Character position to start deleting from
    ///     length (int): Number of characters to delete
    ///
    /// Returns:
    ///     Coroutine: Resolves when the operation completes
    fn delete<'py>(
        &self,
        py: Python<'py>,
        pos: usize,
        length: usize,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.splice(py, pos, length as isize, String::new())
    }

    /// Append text to the end.
    ///
    /// Args:
    ///     text (str): Text to append
    ///
    /// Returns:
    ///     Coroutine: Resolves when the operation completes
    fn append<'py>(
        &self,
        py: Python<'py>,
        text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let handle = self.handle.clone();
        let obj_id = self.obj_id.clone();

        future_into_py(py, async move {
            let handle = handle.lock().await;

            handle.with_document(|doc| {
                let len = doc.text(&*obj_id)?.chars().count();
                doc.transact(|tx| {
                    tx.splice_text(&*obj_id, len, 0, &text)?;
                    Ok::<_, automerge::AutomergeError>(())
                }).map_err(|e| e.error)?;
                Ok::<_, automerge::AutomergeError>(())
            })
            .map_err(|e| PyRuntimeError::new_err(format!("Append failed: {}", e)))?;

            Ok(None::<Py<PyAny>>)
        })
    }

    fn __repr__(&self) -> String {
        format!("Text(doc='{}')", self.document_id)
    }
}


/// Spork
///
/// Library for building local-first collaborative applications using
/// Automerge CRDTs (Conflict-Free Replicated Data Types).
///
/// Key concepts:
///     - **Repo**: Manages documents, storage, and networking
///     - **DocHandle**: A handle to a specific document for reading/writing
///     - **AutomergeUrl**: Unique identifier for documents (automerge:...)
///
/// See also: https://automerge.org/docs/
#[pymodule(name = "spork")]
fn spork_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Repo>()?;
    m.add_class::<DocHandle>()?;
    m.add_class::<Text>()?;
    Ok(())
}
