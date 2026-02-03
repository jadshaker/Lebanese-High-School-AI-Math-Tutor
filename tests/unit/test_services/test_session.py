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
        "session_id": "test-session-001",
        "original_question": "What is the derivative of x^2?",
    }

    response = client.post("/sessions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-001"
    assert data["original_question"] == "What is the derivative of x^2?"
    assert data["phase"] == "initial"
    assert "created_at" in data


@pytest.mark.unit
def test_create_session_auto_id():
    """Test session creation with auto-generated ID"""
    request_data = {"original_question": "What is integration?"}

    response = client.post("/sessions", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"].startswith("session-")
    assert data["original_question"] == "What is integration?"


@pytest.mark.unit
def test_get_session_success():
    """Test getting an existing session"""
    # First create a session
    create_response = client.post(
        "/sessions",
        json={
            "session_id": "test-get-session",
            "original_question": "Test question",
        },
    )
    assert create_response.status_code == 200

    # Then get it
    response = client.get("/sessions/test-get-session")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-get-session"
    assert data["original_question"] == "Test question"


@pytest.mark.unit
def test_get_session_not_found():
    """Test getting a non-existent session"""
    response = client.get("/sessions/non-existent-session")
    assert response.status_code == 404


@pytest.mark.unit
def test_delete_session_success():
    """Test deleting an existing session"""
    # First create a session
    client.post(
        "/sessions",
        json={
            "session_id": "test-delete-session",
            "original_question": "Test question",
        },
    )

    # Then delete it
    response = client.delete("/sessions/test-delete-session")
    assert response.status_code == 200

    # Verify it's gone
    get_response = client.get("/sessions/test-delete-session")
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
    client.post(
        "/sessions",
        json={
            "session_id": "test-tutoring-state",
            "original_question": "Test question",
        },
    )

    # Update tutoring state
    response = client.put(
        "/sessions/test-tutoring-state/tutoring",
        json={"current_node": "step_1", "depth": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tutoring_state"]["current_node"] == "step_1"
    assert data["tutoring_state"]["depth"] == 1


@pytest.mark.unit
def test_update_tutoring_state_not_found():
    """Test updating tutoring state for non-existent session"""
    response = client.put(
        "/sessions/non-existent-tutoring/tutoring",
        json={"current_node": "step_1", "depth": 1},
    )
    assert response.status_code == 404


@pytest.mark.unit
def test_add_message_to_session():
    """Test adding a message to session"""
    # First create a session
    client.post(
        "/sessions",
        json={
            "session_id": "test-messages",
            "original_question": "Test question",
        },
    )

    # Add a message
    response = client.post(
        "/sessions/test-messages/messages",
        json={"role": "user", "content": "I understand"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 1
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "I understand"


@pytest.mark.unit
def test_add_multiple_messages():
    """Test adding multiple messages to session"""
    # First create a session
    client.post(
        "/sessions",
        json={
            "session_id": "test-multi-messages",
            "original_question": "Test question",
        },
    )

    # Add messages
    client.post(
        "/sessions/test-multi-messages/messages",
        json={"role": "user", "content": "Message 1"},
    )
    client.post(
        "/sessions/test-multi-messages/messages",
        json={"role": "assistant", "content": "Response 1"},
    )

    # Get session and verify messages
    response = client.get("/sessions/test-multi-messages")
    data = response.json()

    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "Message 1"
    assert data["messages"][1]["content"] == "Response 1"


@pytest.mark.unit
def test_session_phase_update():
    """Test session phase is updated correctly"""
    # Create session
    create_response = client.post(
        "/sessions",
        json={
            "session_id": "test-phase",
            "original_question": "Test question",
        },
    )
    assert create_response.json()["phase"] == "initial"

    # Update phase via tutoring state (implicitly moves to tutoring)
    client.put(
        "/sessions/test-phase/tutoring",
        json={"current_node": "step_1", "depth": 1},
    )

    # Verify phase changed
    response = client.get("/sessions/test-phase")
    assert response.json()["phase"] == "tutoring"
