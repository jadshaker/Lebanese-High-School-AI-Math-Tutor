import pytest

from tests.unit.test_services.conftest import _ensure_env, _ensure_path, _mock_logging

_ensure_env()
_ensure_path()
_mock_logging()

from src.models.schemas import MessageRole, SessionPhase
from src.services.session import service as session_service


@pytest.fixture(autouse=True)
def clear_sessions():
    session_service.sessions.clear()
    yield
    session_service.sessions.clear()


@pytest.mark.unit
def test_create_session_success():
    """Test successful session creation with an initial query."""
    session = session_service.create_session(
        initial_query="What is the derivative of x^2?",
        request_id="req-1",
    )

    assert session.session_id.startswith("sess_")
    assert session.original_query == "What is the derivative of x^2?"
    assert session.phase == SessionPhase.INITIAL
    assert len(session.messages) == 1
    assert session.messages[0].role == MessageRole.USER


@pytest.mark.unit
def test_create_session_auto_id():
    """Test that auto-generated session IDs follow the expected format."""
    s1 = session_service.create_session(request_id="req-2")
    s2 = session_service.create_session(request_id="req-3")

    assert s1.session_id.startswith("sess_")
    assert s2.session_id.startswith("sess_")
    assert s1.session_id != s2.session_id


@pytest.mark.unit
def test_get_session_success():
    """Test retrieving an existing session by ID."""
    created = session_service.create_session(
        initial_query="Test question",
        request_id="req-4",
    )

    fetched = session_service.get_session(created.session_id)

    assert fetched is not None
    assert fetched.session_id == created.session_id
    assert fetched.original_query == "Test question"


@pytest.mark.unit
def test_get_session_not_found():
    """Test that retrieving a non-existent session returns None."""
    result = session_service.get_session("non-existent-session")

    assert result is None


@pytest.mark.unit
def test_delete_session_success():
    """Test deleting a session and verifying it is gone."""
    created = session_service.create_session(
        initial_query="Test question",
        request_id="req-5",
    )

    deleted = session_service.delete_session(created.session_id, request_id="req-5")
    assert deleted is True

    fetched = session_service.get_session(created.session_id)
    assert fetched is None


@pytest.mark.unit
def test_delete_session_not_found():
    """Test that deleting a non-existent session returns False."""
    result = session_service.delete_session("non-existent-delete", request_id="req-6")

    assert result is False


@pytest.mark.unit
def test_update_tutoring_state():
    """Test updating question_id, current_node_id, and depth on a session."""
    created = session_service.create_session(request_id="req-7")

    state = session_service.update_tutoring_state(
        created.session_id,
        question_id="q-123",
        current_node_id="node-1",
        depth=1,
        request_id="req-7",
    )

    assert state is not None
    assert state.question_id == "q-123"
    assert state.current_node_id == "node-1"
    assert state.depth == 1


@pytest.mark.unit
def test_update_tutoring_state_not_found():
    """Test that updating tutoring state for a missing session returns None."""
    result = session_service.update_tutoring_state(
        "non-existent-tutoring",
        question_id="q-123",
        depth=1,
        request_id="req-8",
    )

    assert result is None


@pytest.mark.unit
def test_add_message_to_session():
    """Test adding a user message to a session."""
    created = session_service.create_session(request_id="req-9")

    message = session_service.add_message(
        created.session_id,
        MessageRole.USER,
        "I understand",
        request_id="req-9",
    )

    assert message is not None
    assert message.role == MessageRole.USER
    assert message.content == "I understand"


@pytest.mark.unit
def test_add_multiple_messages():
    """Test adding multiple messages and verifying the count."""
    created = session_service.create_session(request_id="req-10")

    session_service.add_message(
        created.session_id, MessageRole.USER, "Message 1", request_id="req-10"
    )
    session_service.add_message(
        created.session_id, MessageRole.ASSISTANT, "Response 1", request_id="req-10"
    )

    messages = session_service.get_messages(created.session_id)

    assert messages is not None
    assert len(messages) == 2
    assert messages[0].content == "Message 1"
    assert messages[1].content == "Response 1"


@pytest.mark.unit
def test_session_phase_update():
    """Test updating a session phase via update_session."""
    created = session_service.create_session(
        initial_query="Test question",
        request_id="req-11",
    )
    assert created.phase == SessionPhase.INITIAL

    updated = session_service.update_session(
        created.session_id,
        phase=SessionPhase.TUTORING,
        request_id="req-11",
    )

    assert updated is not None
    assert updated.phase == SessionPhase.TUTORING
