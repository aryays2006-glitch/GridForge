
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_tools_returns_registered_tools():
    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    assert isinstance(response.json(), list)

    tool_names = [tool["name"] for tool in response.json()]
    assert "get_invoice" in tool_names
