import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(session_app):
    """Set up module-level client for session service"""
    global client
    client = TestClient(session_app)


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "session"
    assert "active_sessions" in data


@pytest.mark.unit
def test_create_session_success():
    """Test successful session creation"""
    request_data = {
        "initial_query": "What is the derivative of x^2?",
    }

    response = client.post("/sessions", json=request_data)

    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert "created_at" in data


@pytest.mark.unit
def test_create_session_auto_id():
    """Test session creation with auto-generated ID"""
    request_data = {"initial_query": "What is integration?"}

    response = client.post("/sessions", json=request_data)

    assert response.status_code == 201
    data = response.json()
    assert data["session_id"].startswith("sess_")


@pytest.mark.unit
def test_get_session_success():
    """Test getting an existing session"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={"initial_query": "Test question"},
    )
    assert create_response.status_code == 201
    session_id = create_response.json()["session_id"]

    # Then get it
    response = client.get(f"/sessions/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["original_query"] == "Test question"


@pytest.mark.unit
def test_get_session_not_found():
    """Test getting a non-existent session"""
    response = client.get("/sessions/non-existent-session")
    assert response.status_code == 404


@pytest.mark.unit
def test_delete_session_success():
    """Test deleting an existing session"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={"initial_query": "Test question"},
    )
    session_id = create_response.json()["session_id"]

    # Then delete it
    response = client.delete(f"/sessions/{session_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 404


@pytest.mark.unit
def test_delete_session_not_found():
    """Test deleting a non-existent session"""
    response = client.delete("/sessions/non-existent-delete")
    assert response.status_code == 404


@pytest.mark.unit
def test_update_tutoring_state():
    """Test updating tutoring state"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={"initial_query": "Test question"},
    )
    session_id = create_response.json()["session_id"]

    # Update tutoring state via PATCH
    response = client.patch(
        f"/sessions/{session_id}/tutoring",
        json={"question_id": "q-123", "current_node_id": "node-1", "depth": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question_id"] == "q-123"
    assert data["current_node_id"] == "node-1"
    assert data["depth"] == 1


@pytest.mark.unit
def test_update_tutoring_state_not_found():
    """Test updating tutoring state for non-existent session"""
    response = client.patch(
        "/sessions/non-existent-tutoring/tutoring",
        json={"question_id": "q-123", "depth": 1},
    )
    assert response.status_code == 404


@pytest.mark.unit
def test_add_message_to_session():
    """Test adding a message to session"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={"initial_query": "Test question"},
    )
    session_id = create_response.json()["session_id"]

    # Add a message
    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": "I understand"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "user"
    assert data["content"] == "I understand"


@pytest.mark.unit
def test_add_multiple_messages():
    """Test adding multiple messages to session"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={},
    )
    session_id = create_response.json()["session_id"]

    # Add messages
    client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": "Message 1"},
    )
    client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "assistant", "content": "Response 1"},
    )

    # Get messages via messages endpoint
    response = client.get(f"/sessions/{session_id}/messages")
    data = response.json()

    assert data["total_count"] == 2
    assert data["messages"][0]["content"] == "Message 1"
    assert data["messages"][1]["content"] == "Response 1"


@pytest.mark.unit
def test_session_phase_update():
    """Test session phase is updated correctly"""
    # Create session
    create_response = client.post(
        "/sessions",
        json={"initial_query": "Test question"},
    )
    session_id = create_response.json()["session_id"]

    # Get session to check initial phase
    get_response = client.get(f"/sessions/{session_id}")
    assert get_response.json()["phase"] == "initial"

    # Update phase via PATCH
    patch_response = client.patch(
        f"/sessions/{session_id}",
        json={"phase": "tutoring"},
    )
    assert patch_response.status_code == 200

    # Verify phase changed
    response = client.get(f"/sessions/{session_id}")
    assert response.json()["phase"] == "tutoring"
